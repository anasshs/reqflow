"""
Interface web « Atelier d'automatisation » — Robot Framework (AppiumLibrary / Browser library)
+ Xray + Jira.

Façade web : routes minces qui appellent les moteurs (aucune logique métier ici).

Lancement (depuis le dossier appium-robot-mcp) :
    python web/app.py            -> http://127.0.0.1:8765

Écoute uniquement en local (127.0.0.1). Sécurité : jeton de session (cookie HttpOnly
SameSite=Strict), contrôle Host / Origin, jeton propre aux processus locaux sur /api/events et
/api/externe/*, taille des requêtes plafonnée (voir securite.py). Ne pas exposer sur le réseau.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.responses import FileResponse, Response  # noqa: E402

from atelier.adapters import facade as outils  # noqa: E402
from atelier.adapters.web.agent import Agent  # noqa: E402
from atelier.adapters.web.securite import SecuriteLocale, jeton_processus  # noqa: E402
from atelier.discovery import carte as amap  # noqa: E402
from atelier.discovery import carte_outils, espaces, exploration, session  # noqa: E402
from atelier.domain import declarations, evenements, projet  # noqa: E402
from atelier.execution import jdd  # noqa: E402
from atelier.generation import locators as gen_locators  # noqa: E402
from atelier.intelligence import patrimoine_xray  # noqa: E402

outils.WEB_EVENTS_URL = ""  # dans ce processus, l'agent intégré émet lui-même ses événements
HOOK_TYPES = {"carte_change", "exploration", "locators_change", "navigation"}

PORT = int(os.environ.get("WEB_PORT", "8765"))
STATIC = Path(__file__).resolve().parent / "static"
CONFIG_PATH = Path(os.environ.get("ATELIER_CONFIG", Path.home() / ".atelier-automatisation.json"))
CONFIG_DEFAUT = {
    "apps": {"android": {}, "ios": {}, "web": {"browser": "chromium", "headless": True}},
    "prereglages": {},
    "jql_candidats": os.environ.get("XRAY_CANDIDATS_JQL", "project = TAM AND labels = candidat_auto ORDER BY key"),
    "statut_sous_tache_fini": "Terminé",
}

app = FastAPI(title="Atelier d'automatisation", docs_url=None, redoc_url=None, openapi_url=None)
JETON_SESSION = secrets.token_urlsafe(32)  # nouveau à chaque démarrage : la page doit être rechargée
JETON_PROCESSUS = jeton_processus()
app.add_middleware(SecuriteLocale, port=PORT, jeton_session=JETON_SESSION, jeton_evenements=JETON_PROCESSUS)
clients: set[WebSocket] = set()
history: deque = deque(maxlen=400)
externes: dict = {}  # steps proposés par Cursor / Claude Desktop via le MCP : id -> {...}
state = {"explo": None, "loop": None, "flux": {"platform": None, "udid": None}, "run": None, "dernier_run": None,
         "dernier_bilan": None, "produits": [], "dernier_mcp": 0.0, "sante_cache": {}}


# --------------------------------------------------------------------------- config
def config() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text("utf-8"))
            return {**CONFIG_DEFAUT, **data, "apps": {**CONFIG_DEFAUT["apps"], **data.get("apps", {})}}
        except json.JSONDecodeError:
            pass
    return json.loads(json.dumps(CONFIG_DEFAUT))


def save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")


# --------------------------------------------------------------------------- diffusion
async def _broadcast(ev: dict):
    for ws in list(clients):
        try:
            await ws.send_text(json.dumps(ev, ensure_ascii=False, default=str))
        except Exception:
            clients.discard(ws)


def emit(ev: dict):
    """Appelable depuis n'importe quel thread (agent, run)."""
    ev.setdefault("heure", time.strftime("%H:%M:%S"))
    if ev.get("type") == "outil" and ev.get("nom") in ("write_project_file", "generate_locators_resource"):
        chemin = (ev.get("args") or {}).get("path") or (ev.get("args") or {}).get("fichier")
        if chemin and chemin not in state["produits"]:
            state["produits"].append(chemin)
            ev = {**ev, "produits": state["produits"]}
    history.append(ev)
    if state["loop"]:
        asyncio.run_coroutine_threadsafe(_broadcast(ev), state["loop"])


agent = Agent(emit)
evenements.abonner(emit, HOOK_TYPES)  # carte et exploration : événements directs vers la page


@app.on_event("startup")
async def _startup():
    state["loop"] = asyncio.get_running_loop()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    for ev in list(history)[-150:]:  # rattrapage après rechargement de la page
        await ws.send_text(json.dumps({**ev, "rejeu": True}, ensure_ascii=False, default=str))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        clients.discard(ws)


@app.post("/api/events")
async def events(req: Request):
    """Reçoit les événements du listener Robot et du MCP (Cursor, Claude Desktop)."""
    ev = await req.json()
    if ev.get("source") == "mcp":
        state["dernier_mcp"] = time.time()
    if ev.get("type") == "session" and ev.get("etat") == "ouverte":
        state["flux"] = {"platform": ev.get("platform"), "udid": ev.get("udid") or None}
    emit(ev)
    return {"ok": True}


def _call(fn, *a, **k):
    try:
        return fn(*a, **k)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))


# --------------------------------------------------------------------------- pilotage externe
@app.post("/api/externe/step")
async def externe_step(req: Request):
    """Step proposé par l'agent externe (Cursor) : affiché puis validé ou corrigé ici."""
    b = await req.json()
    pid = "x" + uuid.uuid4().hex[:7]
    step = {"n": len(agent.steps) + 1, "gherkin": b["gherkin"], "keyword": b.get("keyword", ""),
            "locators": b.get("locators", []), "commentaire": b.get("commentaire", ""),
            "statut": "proposé", "source": "cursor"}
    agent.steps.append(step)
    externes[pid] = {"step": step, "reponse": None}
    state["dernier_mcp"] = time.time()
    emit({"type": "attente", "id": pid, "nature": "step", "step": step})
    return {"id": pid}


@app.get("/api/externe/reponse/{pid}")
def externe_reponse(pid: str):
    e = externes.get(pid)
    if not e:
        raise HTTPException(404, "Step inconnu.")
    if not e["reponse"]:
        return {"decision": None}
    decision, texte = e["reponse"]
    return {"decision": decision, "texte": texte}


# --------------------------------------------------------------------------- page, état, santé
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


def _attente_courante():
    if agent.pending:
        return {"id": agent.pending["id"], **agent.pending["payload"]}
    for pid, e in externes.items():
        if not e["reponse"]:
            return {"id": pid, "nature": "step", "step": e["step"]}
    return None


@app.get("/api/etat")
def etat():
    return {"session": session.plateforme(), "flux": state["flux"], "agent_occupe": agent.busy,
            "run_en_cours": bool(state["run"] and state["run"].is_alive()), "steps": agent.steps,
            "attente": _attente_courante(), "dernier_bilan": state["dernier_bilan"],
            "produits": state["produits"], "projet": str(projet.PROJECT_DIR),
            "jira_url": (os.environ.get("JIRA_BASE_URL") or "").rstrip("/"),
            "agent_integre": bool(os.environ.get("ANTHROPIC_API_KEY")), "config": config(),
            "app_carte": amap.app_courante(), "applications": amap.apps(),
            "exploration": bool(state["explo"] and state["explo"].is_alive())}


def _http_ok(url: str, timeout: float = 3) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status < 500
    except Exception:
        return False


def _sante_items() -> list[dict]:
    items = []

    def item(cle, nom, ok, detail, solution, optionnel=False):
        items.append({"cle": cle, "nom": nom, "ok": ok, "detail": detail,
                      "solution": "" if ok else solution, "optionnel": optionnel})

    appium = _http_ok(session.APPIUM_URL.rstrip("/") + "/status")
    item("appium", "Appium", appium, session.APPIUM_URL,
         "Lance « appium » dans un terminal (mobile uniquement).", optionnel=True)
    devs = outils.list_devices()
    nb_mobile = len(devs["android"]) + len(devs["ios_simulateurs"]) + len(devs["ios_physiques"])
    item("device", "Device mobile", nb_mobile > 0,
         f"{len(devs['android'])} Android, {len(devs['ios_simulateurs']) + len(devs['ios_physiques'])} iOS",
         "Démarre un émulateur Android ou le Simulateur iOS, ou branche un téléphone (débogage USB).",
         optionnel=True)
    try:
        import playwright  # noqa: F401
        pw = True
    except ImportError:
        pw = False
    item("web", "Navigateur web", pw, "Playwright installé" if pw else "",
         "pip install playwright puis « playwright install chromium ».", optionnel=True)

    cache = state["sante_cache"]
    if time.time() - cache.get("t", 0) > 600:  # appels réseau : au plus toutes les 10 min
        cache.clear()
        cache["t"] = time.time()
        try:
            from atelier.integrations.xray import XrayClient
            XrayClient().token()
            cache["xray"] = (True, "connecté")
        except Exception as e:
            cache["xray"] = (False, str(e)[:120])
        try:
            from atelier.integrations.jira import JiraClient
            me = JiraClient().myself()
            cache["jira"] = (True, me.get("displayName", "connecté"))
        except Exception as e:
            cache["jira"] = (False, str(e)[:120])
    item("xray", "Xray", *cache["xray"],
         "Renseigne XRAY_CLIENT_ID / XRAY_CLIENT_SECRET (et XRAY_CA_BUNDLE derrière le proxy).")
    item("jira", "Jira", *cache["jira"],
         "Renseigne JIRA_BASE_URL, JIRA_EMAIL et JIRA_API_TOKEN.", optionnel=True)
    envs_db = sorted({k.split("_")[1].lower() for k in os.environ if re.match(r"DB_[A-Z0-9]+_HOST$", k)})
    item("base", "Base de données", bool(envs_db), ", ".join(envs_db) or "",
         "Renseigne DB_<ENV>_HOST, _PORT, _SID, _USER, _PASSWORD pour la recherche de données.",
         optionnel=True)
    age = time.time() - state["dernier_mcp"] if state["dernier_mcp"] else None
    item("cursor", "Cursor / Claude Desktop", age is not None and age < 900,
         f"dernière action il y a {int(age // 60)} min" if age is not None else "pas encore vu",
         "Ajoute WEB_EVENTS_URL=http://127.0.0.1:%d/api/events dans la config MCP." % PORT,
         optionnel=True)
    return items


@app.get("/api/sante")
async def sante(rafraichir: bool = False):
    if rafraichir:
        state["sante_cache"].clear()
    return await asyncio.to_thread(_sante_items)


@app.get("/api/config")
def get_config():
    return config()


@app.post("/api/config")
async def post_config(req: Request):
    cfg = config()
    b = await req.json()
    for k, v in b.items():
        if k == "apps":
            for p, vals in v.items():
                cfg["apps"].setdefault(p, {}).update(vals)
        elif k == "prereglage":
            cfg["prereglages"][v["nom"]] = v["valeurs"]
        elif k == "supprimer_prereglage":
            cfg["prereglages"].pop(v, None)
        else:
            cfg[k] = v
    save_config(cfg)
    return cfg


# --------------------------------------------------------------------------- device et écran
@app.get("/api/devices")
def devices():
    return _call(outils.list_devices)


@app.post("/api/connecter")
async def connecter(req: Request):
    """Connexion en un clic : device détecté + app mémorisée. Renvoie 'besoin' s'il manque une info."""
    b = await req.json()
    p = b["platform"]
    cfg = config()
    vals = {**cfg["apps"].get(p, {}), **{k: v for k, v in b.get("valeurs", {}).items() if v not in ("", None)}}
    if p == "web" and not vals.get("url"):
        return {"besoin": ["url"]}
    if b.get("valeurs"):
        cfg["apps"].setdefault(p, {}).update(b["valeurs"])
        save_config(cfg)
    udid = b.get("udid") or ""
    if p != "web" and not udid:
        devs = await asyncio.to_thread(outils.list_devices)
        liste = ([d["udid"] for d in devs["android"]] if p == "android"
                 else [d["udid"] for d in devs["ios_simulateurs"]] + devs["ios_physiques"])
        if not liste:
            raise HTTPException(400, "Aucun device détecté : démarre un émulateur ou branche un téléphone.")
        udid = liste[0]
    params = {"platform": p}
    if p == "web":
        params.update(url=vals["url"], browser=vals.get("browser", "chromium"),
                      headless=bool(vals.get("headless", True)))
    else:
        params["udid"] = udid
        for k in (("app_package", "app_activity") if p == "android" else ("bundle_id",)):
            if vals.get(k):
                params[k] = vals[k]
    res = await asyncio.to_thread(_call, outils.start_session, **params)
    state["flux"] = {"platform": p, "udid": udid or None}
    emit({"type": "session", "etat": "ouverte", "platform": p, "udid": udid})
    return res


@app.delete("/api/session")
def session_stop():
    emit({"type": "session", "etat": "fermee"})
    return {"message": _call(outils.stop_session)}


@app.post("/api/flux")
async def flux(req: Request):
    state["flux"] = await req.json()
    return state["flux"]


@app.post("/api/ecran/point")
async def ecran_point(req: Request):
    """Élément touché sur l'image de l'écran, avec sa zone pour le surligner."""
    b = await req.json()
    el = await asyncio.to_thread(_call, outils.element_at, b["x"], b["y"])
    rect = el.get("rect")
    if rect:
        w = await asyncio.to_thread(session.window_size)
        el["zone"] = {"x": rect[0] / w["width"], "y": rect[1] / w["height"],
                      "w": rect[2] / w["width"], "h": rect[3] / w["height"]}
    return el


@app.post("/api/action")
async def action(req: Request):
    body = await req.json()
    nom, args = body["nom"], body.get("args", {})
    if nom not in {"tap", "type_text", "swipe", "press_back", "wait_for", "check_locator", "open_url"}:
        raise HTTPException(400, f"Action non autorisée : {nom}")
    res = await asyncio.to_thread(_call, getattr(outils, nom), **args)
    emit({"type": "outil", "nom": nom, "args": args, "manuel": True})
    return {"resultat": res}


def _grab() -> bytes | None:
    """Image courante : navigateur du MCP en web, adb / simctl en mobile (sans passer par Appium)."""
    p, udid = state["flux"].get("platform"), state["flux"].get("udid")
    try:
        if p == "web":
            return session.screenshot_png() if session.is_web() else None
        if p == "android" and shutil.which("adb"):
            cmd = ["adb"] + (["-s", udid] if udid else []) + ["exec-out", "screencap", "-p"]
            return subprocess.run(cmd, capture_output=True, timeout=8).stdout or None
        if p == "ios" and shutil.which("xcrun"):
            with tempfile.NamedTemporaryFile(suffix=".png") as f:
                r = subprocess.run(["xcrun", "simctl", "io", udid or "booted", "screenshot", f.name],
                                   capture_output=True, timeout=8)
                if r.returncode == 0:
                    return Path(f.name).read_bytes()
            if udid and shutil.which("idevicescreenshot"):
                with tempfile.NamedTemporaryFile(suffix=".png") as f:
                    subprocess.run(["idevicescreenshot", "-u", udid, f.name], capture_output=True, timeout=8)
                    return Path(f.name).read_bytes() or None
        if session.etat["driver"] is not None:
            return session.driver().get_screenshot_as_png()
    except Exception:
        return None
    return None


@app.get("/api/frame.png")
async def frame():
    png = await asyncio.to_thread(_grab)
    if not png:
        raise HTTPException(404, "Rien à afficher.")
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


# --------------------------------------------------------------------------- locators
@app.get("/api/locators")
def locators():
    return gen_locators.captures()


@app.post("/api/locators/ajouter")
async def locators_ajouter(req: Request):
    b = await req.json()
    res = _call(outils.add_screen_locator, b["ecran"], b["cle"], b["locator"], b.get("platform", ""))
    emit({"type": "locators_change"})
    emit({"type": "outil", "nom": "add_screen_locator", "args": b, "manuel": True})
    return res


@app.post("/api/completer")
async def completer(req: Request):
    """Prépare (et lance si demandé) la reprise des steps validés sur une autre plateforme."""
    b = await req.json()
    cible = b["platform"]
    ecrans = locators()
    manquants = {nom: [k for k in {**e["android"], **e["ios"]} if k not in e[cible]]
                 for nom, e in ecrans.items() if (e["android"] or e["ios"])}
    manquants = {k: v for k, v in manquants.items() if v}
    steps = [s["gherkin"] for s in agent.steps if s.get("statut") in ("validé", "corrigé")]
    consigne = (f"Une session {cible} est ouverte. Rejoue les steps validés ci-dessous sur cette plateforme, "
                f"sans les modifier, pour relever les locators manquants avec les mêmes clés métier "
                f"(capture_screen_locators avec selection, ou add_screen_locator). Propose un step uniquement "
                f"si le parcours diffère sur {cible}.\n\nSteps validés :\n"
                + "\n".join(f"- {s}" for s in steps)
                + "\n\nClés à relever par écran :\n"
                + "\n".join(f"- {e} : {', '.join(k)}" for e, k in manquants.items())
                + "\n\nTermine par generate_locators_resource(overwrite=True) pour chaque écran complété.")
    if b.get("lancer"):
        _call(agent.start, consigne)
        emit({"type": "consigne", "texte": f"Compléter les locators sur {cible}"})
    return {"consigne": consigne, "manquants": manquants}


# --------------------------------------------------------------------------- agent intégré
@app.post("/api/agent")
async def agent_start(req: Request):
    body = await req.json()
    _call(agent.start, body["instruction"])
    emit({"type": "consigne", "texte": body["instruction"]})
    return {"ok": True}


@app.post("/api/agent/reponse")
async def agent_reponse(req: Request):
    b = await req.json()
    if b["id"] in externes:
        e = externes[b["id"]]
        statut = {"valider": "validé", "corriger": "corrigé"}.get(b["decision"], "refusé")
        e["step"]["statut"] = statut
        if b.get("texte"):
            e["step"]["correction"] = b["texte"]
        e["reponse"] = (statut, b.get("texte", ""))
        emit({"type": "attente_fin", "id": b["id"], "decision": b["decision"]})
        emit({"type": "step", "step": e["step"]})
        return {"ok": True}
    _call(agent.answer, b["id"], b["decision"], b.get("texte", ""))
    return {"ok": True}


@app.post("/api/agent/stop")
def agent_stop():
    agent.stop()
    return {"ok": True}


@app.post("/api/agent/reset")
def agent_reset():
    agent.reset()
    externes.clear()
    state["produits"].clear()
    emit({"type": "agent_reset"})
    return {"ok": True}


# --------------------------------------------------------------------------- Xray, Jira
@app.get("/api/xray/tests")
async def xray_tests(jql: str = ""):
    return await asyncio.to_thread(_call, outils.xray_search_tests, jql or config()["jql_candidats"], 80)


@app.get("/api/xray/test/{key}")
async def xray_test(key: str):
    return await asyncio.to_thread(_call, outils.xray_get_test, key)


@app.post("/api/xray/inspect")
async def xray_inspect(req: Request):
    b = await req.json()
    info = await asyncio.to_thread(_call, outils.xray_inspect_ticket, b["ticket"])
    try:  # statuts possibles de l'exécution, pour les listes de choix
        from atelier.integrations.jira import JiraClient
        info["statuts"] = await asyncio.to_thread(JiraClient().statuts_projet, info["projet"])
    except Exception:
        info["statuts"] = []
    return info


@app.get("/api/jira/sous-taches/{key}")
async def jira_sous_taches(key: str):
    from atelier.integrations.jira import JiraClient

    jc = JiraClient()
    taches = await asyncio.to_thread(_call, jc.sous_taches, key)
    statuts = []
    if taches:
        statuts = [t["statut_cible"] for t in await asyncio.to_thread(_call, jc.transitions, taches[0]["cle"])]
    return {"sous_taches": taches, "statuts": statuts}


@app.post("/api/jira/transition")
async def jira_transition(req: Request):
    b = await req.json()
    res = []
    for key in b["cles"]:
        try:
            res.append({"cle": key, "ok": True,
                        "statut": await asyncio.to_thread(outils.jira_transition, key, b["statut"])})
        except Exception as e:
            res.append({"cle": key, "ok": False, "erreur": str(e)})
    return res


@app.post("/api/qualifier")
async def qualifier(req: Request):
    b = await req.json()
    return {"message": await asyncio.to_thread(_call, outils.qualify_failure, b["run_id"], b["qualification"],
                                               b.get("commentaire", ""), b.get("message", ""))}


# --------------------------------------------------------------------------- projet, JDD, résultats
@app.get("/api/projet/fichiers")
def fichiers(pattern: str = "**/*.robot"):
    return _call(outils.list_project_files, pattern)


@app.get("/api/projet/fichier")
def projet_fichier(chemin: str):
    """Lecture d'un fichier du projet de tests (limitée au projet)."""
    return {"chemin": chemin, "contenu": _call(projet.lire_fichier, chemin)[:200000]}


@app.get("/api/jdd")
def jdd_envs():
    return _call(outils.list_jdd)


@app.get("/api/jdd/detecter")
def jdd_detecter(target: str, env: str):
    """Jeux de données référencés (JDD_<NOM>) dans les fichiers de la suite choisie."""
    return _call(jdd.detecter, target, env)


@app.get("/api/jdd/{env}")
def jdd_env(env: str):
    return _call(outils.list_jdd, env)


@app.post("/api/jdd/verifier")
async def jdd_verifier(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, outils.check_jdd, b["env"], b["jeux"])


@app.get("/api/resultats/fichier")
def resultat_fichier(chemin: str, dossier: str = "results/mcp"):
    base = projet.safe_path(dossier)
    f = (base / chemin).resolve()
    if base not in f.parents or not f.is_file():
        raise HTTPException(404, "Fichier introuvable.")
    return FileResponse(f)


# --------------------------------------------------------------------------- applications et carte
@app.get("/api/apps")
def apps_liste():
    return {"active": amap.app_courante(), "applications": amap.apps()}


@app.post("/api/apps")
async def apps_creer(req: Request):
    b = await req.json()
    cfg = _call(amap.creer_app, b["nom"], b.get("plateformes") or [], b.get("android"), b.get("ios"), b.get("web"),
                b.get("build", ""), b.get("langue", "fr"))
    atelier = config()  # les réglages de connexion suivent l'application
    for p in ("android", "ios", "web"):
        if b.get(p):
            atelier["apps"].setdefault(p, {}).update({k: v for k, v in b[p].items() if v})
    save_config(atelier)
    emit({"type": "app_change", "slug": cfg["slug"]})
    return cfg


@app.post("/api/apps/choisir")
async def apps_choisir(req: Request):
    b = await req.json()
    cfg = _call(amap.choisir_app, b["slug"])
    atelier = config()
    for p in ("android", "ios", "web"):
        if cfg.get(p):
            atelier["apps"].setdefault(p, {}).update({k: v for k, v in cfg[p].items() if v})
    save_config(atelier)
    emit({"type": "app_change", "slug": b["slug"]})
    return cfg


@app.post("/api/apps/maj")
async def apps_maj(req: Request):
    b = await req.json()
    champs = {k: b[k] for k in ("build", "comptes", "ecran_depart", "etape_assistant", "langue") if k in b}
    if "liste_rouge" in b:
        champs["liste_rouge"] = {"textes": [t for t in b["liste_rouge"] if t.strip()],
                                 "cles": amap.config_app().get("liste_rouge", {}).get("cles", [])}
    return _call(amap.maj_app, None, **champs)


@app.get("/api/carte/graphe")
def carte_graphe():
    if not amap.app_courante():
        return {"app": None, "nodes": [], "edges": [], "depart": ""}
    return _call(amap.graphe)


@app.get("/api/carte/ecran/{eid}")
def carte_ecran(eid: str):
    return _call(carte_outils.ecran_detail, eid)


@app.get("/api/carte/vignette/{nom}")
def carte_vignette(nom: str):
    if not re.fullmatch(r"e_[0-9a-f]{8}_(android|ios|web)\.png", nom):
        raise HTTPException(404, "Vignette inconnue.")
    f = amap._dir() / "vignettes" / nom
    if not f.exists():
        raise HTTPException(404, "Vignette absente.")
    return FileResponse(f)


@app.post("/api/carte/renommer")
async def carte_renommer(req: Request):
    b = await req.json()
    e = _call(amap.renommer, b["id"], b["nom"], b.get("module"))
    emit({"type": "carte_change"})
    return {"id": e["id"], "nom": e.get("nom")}


@app.post("/api/carte/fusionner")
async def carte_fusionner(req: Request):
    b = await req.json()
    e = _call(amap.fusionner, b["source"], b["cible"])
    emit({"type": "carte_change"})
    return {"id": e["id"]}


@app.post("/api/carte/supprimer")
async def carte_supprimer(req: Request):
    b = await req.json()
    _call(amap.supprimer_ecran, b["id"])
    emit({"type": "carte_change"})
    return {"ok": True}


@app.post("/api/carte/transition")
async def carte_transition(req: Request):
    b = await req.json()
    _call(amap.maj_transition, b["id"], b.get("interdite"), bool(b.get("supprimer")))
    emit({"type": "carte_change"})
    return {"ok": True}


@app.post("/api/carte/locators")
async def carte_locators(req: Request):
    b = await req.json()
    return _call(amap.definir_locators, b["id"], b["cle"], b["plateforme"], b["locators"])


@app.post("/api/carte/revu")
async def carte_revu(req: Request):
    b = await req.json()
    _call(amap.marquer_revu, b["id"])
    emit({"type": "carte_change"})
    return {"ok": True}


@app.post("/api/carte/depart")
async def carte_depart(req: Request):
    b = await req.json()
    _call(amap.maj_app, None, ecran_depart=b["id"])
    emit({"type": "carte_change"})
    return {"ok": True}


@app.post("/api/carte/ou-suis-je")
async def carte_ici():
    return await asyncio.to_thread(_call, outils.where_am_i)


@app.post("/api/carte/aller")
async def carte_aller(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, outils.goto_screen, b["ecran"])


@app.post("/api/carte/explorer")
async def carte_explorer(req: Request):
    if state["explo"] and state["explo"].is_alive():
        raise HTTPException(409, "Une exploration est déjà en cours.")
    b = await req.json()
    if b.get("depuis"):
        r = await asyncio.to_thread(_call, outils.goto_screen, b["depuis"])
        if not r.get("arrive"):
            raise HTTPException(400, "Impossible d'atteindre l'écran de départ choisi.")

    def worker():
        try:
            exploration.explorer(int(b.get("max_ecrans", 25)), int(b.get("profondeur", 3)), int(b.get("duree", 900)))
        except Exception as e:
            emit({"type": "exploration", "fin": True, "erreur": str(e)})

    state["explo"] = threading.Thread(target=worker, daemon=True)
    state["explo"].start()
    return {"ok": True}


@app.post("/api/carte/explorer/stop")
def carte_explorer_stop():
    outils.stop_exploration()
    return {"ok": True}


@app.get("/api/carte/noms")
def carte_noms():
    return _call(amap.proposer_noms)


@app.get("/api/carte/tags")
def carte_tags():
    return _call(outils.map_tags_report)


@app.post("/api/carte/tags/ticket")
async def carte_tags_ticket(req: Request):
    b = await req.json()
    from atelier.integrations.jira import JiraClient

    rap = outils.map_tags_report()
    nom = amap.config_app().get("nom", "")
    cle = await asyncio.to_thread(_call, JiraClient().creer_ticket, b["projet"],
                                  f"Ajouter les identifiants de test — {nom} ({rap['nb']} éléments)", rap["texte"])
    return {"cle": cle}


@app.post("/api/carte/importer")
async def carte_importer(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, outils.map_import_existing, b.get("pattern") or "**/*.resource")


@app.post("/api/carte/exporter")
async def carte_exporter(req: Request):
    b = await req.json()
    return {"fichier": _call(outils.export_screen_resource, b["id"])}


# --------------------------------------------------------------------------- espaces de travail (graphes)
@app.get("/plateforme")
def page_plateforme():
    return FileResponse(STATIC / "plateforme.html")


@app.get("/static/{nom}")
def fichier_statique(nom: str):
    if not re.fullmatch(r"[a-z_]+\.(js|css)", nom) or not (STATIC / nom).is_file():
        raise HTTPException(404, "Fichier inconnu.")
    return FileResponse(STATIC / nom)


def _liste(v: str) -> list[str] | None:
    return [x for x in v.split(",") if x] or None


@app.get("/api/graphes/referentiel")
def graphes_referentiel():
    return espaces.referentiel()


@app.get("/api/graphes/connaissance")
async def graphe_connaissance(types: str = "", categories: str = "", plateforme: str = "", recherche: str = "",
                              centre: str = "", profondeur: int = 1):
    return await asyncio.to_thread(_call, espaces.vue_connaissance, _liste(types), _liste(categories), plateforme,
                                   recherche, centre, profondeur)


@app.get("/api/graphes/couverture")
async def graphe_couverture(module: str = "", afficher: str = "tous", recherche: str = ""):
    return await asyncio.to_thread(_call, espaces.vue_couverture, module, afficher, recherche)


@app.get("/api/graphes/candidats")
async def graphe_candidats(module: str = ""):
    return await asyncio.to_thread(_call, espaces.candidats, module)


@app.get("/api/graphes/flux")
async def graphe_flux(cible: str = ""):
    return await asyncio.to_thread(_call, espaces.vue_flux, cible)


@app.get("/api/graphes/noeud")
async def graphe_noeud(id: str):
    return await asyncio.to_thread(_call, espaces.detail, id)


@app.get("/api/graphes/impact")
async def graphe_impact(id: str):
    return await asyncio.to_thread(_call, espaces.impact, id)


@app.get("/api/graphes/anomalies")
async def graphe_anomalies(graphe: str = "connaissance", module: str = ""):
    return await asyncio.to_thread(_call, espaces.anomalies, graphe, module)


@app.get("/api/graphes/historique")
def graphe_historique(id: str = ""):
    return _call(declarations.historique, id)


@app.post("/api/graphes/noeuds")
async def graphe_ajout_noeud(req: Request):
    b = await req.json()
    return _call(espaces.ajouter_noeud, b["id"], b["type"], b["libelle"], b.get("description", ""),
                 b.get("plateformes"))


@app.post("/api/graphes/noeuds/modifier")
async def graphe_modif_noeud(req: Request):
    b = await req.json()
    champs = {k: b[k] for k in ("libelle", "description", "statut", "plateformes") if k in b}
    return _call(espaces.modifier_noeud, b["id"], **champs)


@app.post("/api/graphes/noeuds/supprimer")
async def graphe_supp_noeud(req: Request):
    b = await req.json()
    _call(espaces.supprimer_noeud, b["id"])
    return {"ok": True}


@app.post("/api/graphes/relations")
async def graphe_ajout_relation(req: Request):
    b = await req.json()
    return _call(espaces.ajouter_relation, b["de"], b["vers"], b["type"])


@app.post("/api/graphes/relations/supprimer")
async def graphe_supp_relation(req: Request):
    b = await req.json()
    _call(espaces.supprimer_relation, b["id"])
    return {"ok": True}


@app.post("/api/graphes/valider")
async def graphe_valider(req: Request):
    b = await req.json()
    _call(espaces.valider, b["id"])
    return {"ok": True}


@app.post("/api/graphes/fusionner")
async def graphe_fusionner(req: Request):
    b = await req.json()
    _call(espaces.fusionner, b["source"], b["cible"])
    return {"ok": True}


@app.post("/api/graphes/ia")
async def graphe_ia(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, espaces.demander_ia, b.get("graphe", "connaissance"),
                                   b.get("intention", "expliquer"), b.get("selection", ""), b.get("question", ""),
                                   b.get("cible", ""), b.get("module", ""))


@app.get("/api/patrimoine")
def patrimoine_etat():
    return patrimoine_xray.etat()


@app.post("/api/patrimoine/importer")
async def patrimoine_importer(req: Request):
    b = await req.json()
    return _call(patrimoine_xray.enregistrer, b, "import manuel (interface)")


@app.post("/api/patrimoine/synchroniser")
async def patrimoine_synchroniser(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, patrimoine_xray.synchroniser_jira, b["projet"], b.get("jql", ""))


# --------------------------------------------------------------------------- runs
@app.post("/api/run")
async def run(req: Request):
    if state["run"] and state["run"].is_alive():
        raise HTTPException(409, "Un run est déjà en cours.")
    b = await req.json()
    params = {k: v for k, v in b.items() if v not in ("", None, [])}
    params["events_url"] = f"http://127.0.0.1:{PORT}/api/events"
    plat = (b.get("variables") or {}).get("PLATFORM", "").lower()
    if plat in ("android", "ios"):
        state["flux"] = {"platform": plat, "udid": b["variables"].get("DEVICE")}
    state["dernier_run"] = params

    def worker():
        emit({"type": "run_lance", "suite": params.get("target"), "relance": bool(params.get("relancer_echecs"))})
        try:
            bilan = outils.run_robot(**params)
        except Exception as e:
            bilan = {"statut": "erreur", "erreur": str(e)}
        state["dernier_bilan"] = bilan
        emit({"type": "run_bilan", "bilan": bilan})

    state["run"] = threading.Thread(target=worker, daemon=True)
    state["run"].start()
    return {"ok": True}


@app.get("/api/run/dernier")
def dernier_run():
    return {"params": state["dernier_run"], "bilan": state["dernier_bilan"]}


def main():
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
