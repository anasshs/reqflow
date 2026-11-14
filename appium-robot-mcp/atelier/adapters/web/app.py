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
from atelier.execution import historique  # noqa: E402
from atelier.execution import robot as robot_moteur  # noqa: E402
from atelier.generation import bdd, editeur  # noqa: E402
from atelier.intelligence import strategie  # noqa: E402
from atelier.generation import locators as gen_locators  # noqa: E402
from atelier.intelligence import assistant  # noqa: E402
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
    run_id = historique.nouvel_id()
    params.setdefault("output_dir", f"{historique.RACINE}/{run_id}")  # un dossier par run : plus d'écrasement
    plat = (b.get("variables") or {}).get("PLATFORM", "").lower()
    if plat in ("android", "ios"):
        state["flux"] = {"platform": plat, "udid": b["variables"].get("DEVICE")}
    state["dernier_run"] = params

    def worker():
        debut = time.strftime("%Y-%m-%dT%H:%M:%S")
        _call_silencieux(historique.enregistrer, run_id, params, None, debut)
        emit({"type": "run_lance", "suite": params.get("target"), "relance": bool(params.get("relancer_echecs")),
              "run_id": run_id})
        try:
            bilan = outils.run_robot(**params)
        except Exception as e:
            bilan = {"statut": "erreur", "erreur": str(e)}
        state["dernier_bilan"] = bilan
        _call_silencieux(historique.enregistrer, run_id, params, bilan, debut, time.strftime("%Y-%m-%dT%H:%M:%S"))
        emit({"type": "run_bilan", "bilan": bilan, "run_id": run_id})

    state["run"] = threading.Thread(target=worker, daemon=True)
    state["run"].start()
    return {"ok": True, "run_id": run_id}


def _call_silencieux(fn, *a):
    try:
        fn(*a)
    except Exception:
        pass  # l'historique ne doit jamais empêcher un run


@app.post("/api/run/arreter")
def run_arreter():
    return {"message": robot_moteur.arreter_run()}


@app.get("/api/executions")
def executions_liste():
    return _call(historique.lister)


@app.get("/api/executions/{run_id}")
async def execution_detail(run_id: str):
    return await asyncio.to_thread(_call, historique.detail, run_id)


@app.get("/api/executions/{run_id}/test")
async def execution_test(run_id: str, id: str):
    return await asyncio.to_thread(_call, historique.detail_test, run_id, id)


# --------------------------------------------------------------------------- construction BDD
@app.get("/api/bdd")
def bdd_liste():
    return _call(bdd.lister)


def _vue_bdd(m: dict) -> dict:
    return {"scenario": m, "gherkin": bdd.serialiser(m), "controles": bdd.controles(m), "statistiques": bdd.statistiques(m)}


@app.get("/api/bdd/{cle}")
def bdd_lire(cle: str):
    m = _call(bdd.charger, cle)
    if not m:
        raise HTTPException(404, f"Scénario {cle} introuvable.")
    return _vue_bdd(m)


@app.post("/api/bdd")
async def bdd_creer(req: Request):
    b = await req.json()
    depuis = None
    if b.get("depuis_xray"):
        try:
            depuis = await asyncio.to_thread(outils.xray_get_test, b["cle"])
        except Exception as e:
            raise HTTPException(400, f"Lecture du test Xray impossible : {e}")
    return _vue_bdd(_call(bdd.creer, b["cle"], b.get("titre", ""), depuis, b.get("jdd", "")))


@app.post("/api/bdd/{cle}/operation")
async def bdd_operation(cle: str, req: Request):
    """Opérations du graphe de scénario : ajouter / modifier / supprimer / déplacer une étape, branche, texte."""
    b = await req.json()
    op = b.pop("op", "")
    ops = {"ajouter_etape": lambda: bdd.ajouter_etape(cle, b["scenario"], b.get("mot", "Et"), b["texte"], b.get("apres", "")),
           "modifier_etape": lambda: bdd.modifier_etape(cle, b.pop("etape"), **b),
           "supprimer_etape": lambda: bdd.supprimer_etape(cle, b["etape"]),
           "deplacer_etape": lambda: bdd.deplacer_etape(cle, b["etape"], int(b.get("sens", 1))),
           "ajouter_branche": lambda: bdd.ajouter_branche(cle, b["depuis"], b["nom"], b.get("type", "negatif"), b.get("etapes")),
           "supprimer_scenario": lambda: bdd.supprimer_scenario(cle, b["scenario"]),
           "texte": lambda: bdd.depuis_texte(cle, b["gherkin"]),
           "jdd": lambda: bdd.associer_jdd(cle, b.get("jdd", "")),
           "valider": lambda: bdd.valider(cle)}
    if op not in ops:
        raise HTTPException(400, f"Opération inconnue : {op}")
    return _vue_bdd(_call(ops[op]))


@app.post("/api/bdd/{cle}/generer")
async def bdd_generer(cle: str, req: Request):
    """Prévisualise (ecrire=false) ou écrit (ecrire=true, jamais d'écrasement implicite) la suite Robot."""
    b = await req.json()
    m = _call(bdd._exiger, cle)
    g = await asyncio.to_thread(_call, bdd.generer_robot, m)
    if b.get("ecrire"):
        chemin = b.get("chemin") or g["chemin"]
        _call(outils.write_project_file, chemin, g["contenu"], bool(b.get("ecraser")))
        g["ecrit"] = chemin
    return g


@app.post("/api/bdd/{cle}/ia")
async def bdd_ia(cle: str, req: Request):
    b = await req.json()
    m = _call(bdd._exiger, cle)
    return await asyncio.to_thread(_call, assistant.demander_scenario, m, bdd.controles(m), b.get("question", ""))


# --------------------------------------------------------------------------- éditeur de test
@app.get("/api/editeur/arbre")
async def editeur_arbre():
    return await asyncio.to_thread(_call, editeur.arbre)


@app.post("/api/editeur/enregistrer")
async def editeur_enregistrer(req: Request):
    b = await req.json()
    r = _call(editeur.enregistrer, b["chemin"], b["contenu"], b.get("version_lue"))
    emit({"type": "outil", "nom": "write_project_file", "args": {"path": b["chemin"]}, "manuel": True})
    return r


@app.post("/api/editeur/lint")
async def editeur_lint(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, editeur.lint, b["contenu"], b.get("chemin", "suite.robot"))


@app.post("/api/editeur/robocop")
async def editeur_robocop(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, editeur.robocop, b["chemin"])


@app.get("/api/editeur/proprietes")
async def editeur_proprietes(chemin: str):
    return await asyncio.to_thread(_call, editeur.proprietes, chemin)


@app.get("/api/editeur/reutilisation")
async def editeur_reutilisation():
    return await asyncio.to_thread(_call, editeur.reutilisation)


@app.get("/api/editeur/historique")
def editeur_historique(chemin: str):
    return _call(editeur.historique, chemin)


@app.get("/api/resultats/captures")
def resultats_captures(dossier: str = "results", limite: int = 12):
    """Captures d'écran les plus récentes des résultats (preuves)."""
    base = projet.safe_path(dossier)
    fichiers = sorted(base.rglob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)[:limite] if base.exists() else []
    return [{"chemin": str(f.relative_to(base)), "dossier": dossier, "date": time.strftime("%H:%M:%S", time.localtime(f.stat().st_mtime))}
            for f in fichiers]


# --------------------------------------------------------------------------- contexte (en-tête)
@app.get("/api/contexte")
def contexte():
    from atelier.execution import jdd as jdd_mod

    try:
        cfg = amap.config_app() if amap.app_courante() else {}
    except Exception:
        cfg = {}
    try:
        envs = jdd_mod.environnements()
    except Exception:
        envs = []
    cache = state["sante_cache"]
    xray = cache.get("xray")
    return {"projet": projet.PROJECT_DIR.name, "projet_chemin": str(projet.PROJECT_DIR),
            "applications": [{"slug": a["slug"], "nom": a.get("nom", a["slug"])} for a in amap.apps()],
            "application": cfg.get("slug"), "version": cfg.get("build", ""), "plateformes": cfg.get("plateformes", []),
            "session": session.plateforme(), "flux": state["flux"], "environnements": envs,
            "xray": {"configure": bool(os.environ.get("XRAY_CLIENT_ID")), "connecte": xray[0] if xray else None,
                     "detail": xray[1] if xray else "non vérifié"},
            "run_en_cours": bool(state["run"] and state["run"].is_alive()),
            "agent_integre": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "jira_url": (os.environ.get("JIRA_BASE_URL") or "").rstrip("/"),
            "utilisateur": _utilisateur()}


def _utilisateur() -> str:
    """Compte du poste (l'interface est locale, sans authentification) : affiché tel quel, jamais inventé."""
    import getpass

    try:
        return getpass.getuser()
    except Exception:
        return ""


@app.get("/api/depot/suites")
async def depot_suites():
    """Suites du dépôt (arborescence par dossier) avec le dernier statut connu de leurs tests."""
    def calcul():
        from atelier.execution import depot_robot
        from atelier.execution.robot import derniers_resultats

        inv = depot_robot.lire_depot()
        res = derniers_resultats()
        out = []
        for f, s in sorted(inv["suites"].items()):
            statuts = [res.get(t, {}).get("statut") for t in s["tests"]]
            out.append({"fichier": f, "dossier": f.rsplit("/", 1)[0] if "/" in f else "", "nom": s["nom"], "tests": len(s["tests"]),
                        "echecs": statuts.count("FAIL"), "passes": statuts.count("PASS"), "jamais": statuts.count(None)})
        return out
    return await asyncio.to_thread(_call, calcul)


@app.post("/api/resultats/capturer")
async def resultats_capturer():
    """Enregistre l'écran courant (device ou navigateur) dans results/captures/ comme preuve."""
    png = await asyncio.to_thread(_grab)
    if not png:
        raise HTTPException(400, "Aucun écran à capturer : connecter un device ou un navigateur.")
    nom = time.strftime("capture-%Y%m%d-%H%M%S.png")
    d = projet.safe_path("results/captures")
    d.mkdir(parents=True, exist_ok=True)
    (d / nom).write_bytes(png)
    return {"chemin": nom, "dossier": "results/captures"}


@app.get("/api/run/dernier")
def dernier_run():
    return {"params": state["dernier_run"], "bilan": state["dernier_bilan"]}


# --------------------------------------------------------------------------- Test Strategy
@app.get("/api/strategie")
async def strategie_etat():
    """Stratégie, schéma des rubriques, complétude, contrôles et indicateurs calculés (une seule source)."""
    return await asyncio.to_thread(_call, strategie.etat)


@app.post("/api/strategie/creer")
async def strategie_creer(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, strategie.creer, b.get("nom", ""), b.get("application", ""),
                                   b.get("version_application", ""), b.get("responsable", ""))


@app.post("/api/strategie/infos")
async def strategie_infos(req: Request):
    return await asyncio.to_thread(_call, strategie.modifier_infos, await req.json())


@app.post("/api/strategie/elements")
async def strategie_element(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, strategie.enregistrer_element, b.get("rubrique", ""), b.get("element") or {})


@app.post("/api/strategie/elements/supprimer")
async def strategie_supprimer(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, strategie.supprimer_element, b.get("rubrique", ""), b.get("id", ""))


@app.post("/api/strategie/transition")
async def strategie_transition(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, strategie.transition, b.get("action", ""), b.get("commentaire", ""))


@app.post("/api/strategie/commentaires")
async def strategie_commenter(req: Request):
    return await asyncio.to_thread(_call, strategie.commenter, (await req.json()).get("texte", ""))


@app.post("/api/strategie/criteres/valider")
async def strategie_valider_critere(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, strategie.valider_critere, b.get("id", ""), b.get("preuve", ""))


@app.get("/api/strategie/criteres/entree")
async def strategie_criteres_entree():
    """Critères d'entrée obligatoires non satisfaits (avertissement avant le lancement d'un run)."""
    return await asyncio.to_thread(_call, strategie.criteres_entree_non_satisfaits)


@app.post("/api/strategie/environnements/verifier")
async def strategie_verifier_env(req: Request):
    return await asyncio.to_thread(_call, strategie.verifier_environnement, (await req.json()).get("id", ""))


@app.post("/api/strategie/perimetre/importer")
async def strategie_importer_perimetre():
    return await asyncio.to_thread(_call, strategie.importer_perimetre)


@app.get("/api/strategie/plan-automatisation")
async def strategie_plan():
    return await asyncio.to_thread(_call, strategie.plan_automatisation)


@app.post("/api/strategie/plan-automatisation")
async def strategie_decider(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, strategie.decider_candidat, b.get("cle", ""), b.get("statut", ""),
                                   b.get("framework", ""), b.get("effort", ""), b.get("commentaire", ""))


@app.get("/api/strategie/versions/{n}")
def strategie_version(n: int):
    return _call(strategie.version, n)


@app.get("/api/strategie/comparer")
def strategie_comparer(a: str, b: str = "courante"):
    return _call(strategie.comparer, a, b)


@app.post("/api/strategie/restaurer")
async def strategie_restaurer(req: Request):
    return await asyncio.to_thread(_call, strategie.restaurer, int((await req.json()).get("version", 0)))


@app.get("/api/strategie/journal")
def strategie_journal():
    return _call(strategie.journal)


def main():
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
