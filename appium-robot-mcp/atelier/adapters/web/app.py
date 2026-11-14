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
from atelier.domain import projets  # noqa: E402
from atelier.execution import jdd  # noqa: E402
from atelier.execution import centre, echecs, historique  # noqa: E402
from atelier.discovery import intelligence_app  # noqa: E402
from atelier.execution import robot as robot_moteur  # noqa: E402
from atelier.generation import bdd, conception, editeur, studio  # noqa: E402
from atelier.intelligence import gouvernance, strategie  # noqa: E402
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
    _call_silencieux(projets.au_demarrage)  # dernier projet actif (sauf ROBOT_PROJECT_DIR imposé)


# --------------------------------------------------------------------------- projets (repository + Xray / Jira)
def _occupation() -> str:
    """Raison de refuser une bascule de projet : un run en cours ou en file s'exécute dans le projet courant."""
    if centre.FILE.en_cours is not None:
        return f"run {centre.FILE.en_cours.get('id', '')} en cours"
    if centre.FILE.attente():
        return f"{len(centre.FILE.attente())} run(s) en file d'attente"
    return ""


@app.get("/api/projets")
def projets_lister():
    return {**_call(projets.lister), "journal": projets.journal(30)}


@app.post("/api/projets")
async def projets_enregistrer(req: Request):
    return _call(projets.enregistrer, await req.json())


@app.post("/api/projets/supprimer")
async def projets_supprimer(req: Request):
    return _call(projets.supprimer, (await req.json()).get("id", ""))


@app.get("/api/connexions")
def connexions_lister():
    return _call(projets.connexions)


@app.post("/api/connexions/general")
async def connexions_general(req: Request):
    r = _call(projets.enregistrer_general, await req.json())
    state["sante_cache"].clear()
    return r


@app.post("/api/connexions/secret")
async def connexions_secret(req: Request):
    """Secret saisi dans l'interface : mémoire du serveur local uniquement (ni disque, ni log, jamais renvoyé)."""
    b = await req.json()
    try:
        r = projets.saisir_secret(str(b.get("nom", "")), str(b.get("valeur", "")), bool(b.get("memoriser", True)))
    except ValueError as e:
        raise HTTPException(400, str(e)) from None  # le message ne contient jamais la valeur
    state["sante_cache"].clear()
    return r


@app.post("/api/connexions/secret/effacer")
async def connexions_secret_effacer(req: Request):
    r = _call(projets.effacer_secret, str((await req.json()).get("nom", "")))
    state["sante_cache"].clear()
    return r


@app.post("/api/projets/activer")
async def projets_activer(req: Request):
    r = _call(projets.activer, (await req.json()).get("id", ""), _occupation())
    state["sante_cache"].clear()  # état des connexions à revérifier pour le nouveau projet
    state["produits"] = []
    emit({"type": "projet_change", "projet": r["actif"]})
    return r


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
            "run_en_cours": centre.FILE.en_cours is not None, "steps": agent.steps,
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
        try:
            from atelier.integrations.gitlab import GitLabClient
            u = GitLabClient().utilisateur()
            cache["gitlab"] = (True, f"{u.get('login')} · {os.environ.get('GITLAB_PROJET', '')}")
        except Exception as e:
            cache["gitlab"] = (False, str(e)[:120])
    item("xray", "Xray", *cache["xray"],
         "Renseigne XRAY_CLIENT_ID / XRAY_CLIENT_SECRET (et XRAY_CA_BUNDLE derrière le proxy).")
    item("jira", "Jira", *cache["jira"],
         "Renseigne JIRA_BASE_URL, JIRA_EMAIL et JIRA_API_TOKEN.", optionnel=True)
    item("gitlab", "GitLab", *cache.get("gitlab", (False, "non vérifié")),
         "URL et projet GitLab dans Paramètres › Projets ; jeton d'accès personnel (portées api, write_repository) "
         "dans GITLAB_TOKEN ou la variable du projet ; GITLAB_CA_BUNDLE pour un certificat interne.", optionnel=True)
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


@app.post("/api/graphes/rejeter")
async def graphe_rejeter(req: Request):
    b = await req.json()
    return _call(espaces.rejeter, b.get("id", ""), b.get("motif", ""))


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


@app.post("/api/patrimoine/xray-definitions")
async def patrimoine_xray_definitions(req: Request):
    """Mode A : définitions des tests (type, étapes, Gherkin, dossier, préconditions) lues dans Xray."""
    b = await req.json()
    return await asyncio.to_thread(_call, patrimoine_xray.completer_depuis_xray, b.get("projet", ""), b.get("jql", ""))


@app.post("/api/patrimoine/synchroniser")
async def patrimoine_synchroniser(req: Request):
    b = await req.json()
    cle = b.get("projet") or projets.cle_jira()
    if not cle:
        raise HTTPException(400, "Projet Jira requis (aucun projet actif avec une clé).")
    return await asyncio.to_thread(_call, patrimoine_xray.synchroniser_jira, cle, b.get("jql", ""))


# --------------------------------------------------------------------------- runs
CLES_JOB = ("contexte", "campagne", "priorite", "retry", "derogation_revue")  # métadonnées d'exécution, hors paramètres de run_robot


def _executer_job(job: dict):
    """Exécuté par la file de l'Execution Center (runner local, un run à la fois)."""
    run_id, params = job["id"], dict(job["params"])
    complet = {**params, "contexte": job["contexte"], "campagne": job["campagne"], "priorite": job["priorite"], "retry": job.get("retry", False)}
    plat = (params.get("variables") or {}).get("PLATFORM", "").lower()
    if plat in ("android", "ios"):
        state["flux"] = {"platform": plat, "udid": (params.get("variables") or {}).get("DEVICE")}
    state["dernier_run"] = params
    debut = time.strftime("%Y-%m-%dT%H:%M:%S")
    _call_silencieux(historique.enregistrer, run_id, complet, None, debut)
    emit({"type": "run_lance", "suite": params.get("target"), "relance": bool(params.get("relancer_echecs")), "run_id": run_id})
    try:
        bilan = centre.executer_avec_retry(outils.run_robot, params, job.get("retry", False))
    except Exception as e:
        bilan = {"statut": "erreur", "erreur": str(e)}
    state["dernier_bilan"] = bilan
    _call_silencieux(historique.enregistrer, run_id, complet, bilan, debut, time.strftime("%Y-%m-%dT%H:%M:%S"))
    emit({"type": "run_bilan", "bilan": bilan, "run_id": run_id})
    emit({"type": "file_execution", "file": centre.FILE.attente()})


centre.FILE.executer = _executer_job


def _mettre_en_file(params: dict, priorite: str = "Normal", campagne: str = "", nom: str = "") -> dict:
    retry = bool(params.get("retry"))
    revue = centre.controle_revue(params.get("target", ""), bool(params.get("dry_run")), str(params.get("derogation_revue") or ""))
    params = {k: v for k, v in params.items() if v not in ("", None, []) and k not in CLES_JOB}
    if params.get("relancer_echecs") and params.get("output_dir"):
        params["source_echecs"] = params.pop("output_dir")  # rejeu : nouveau dossier, le run d'origine n'est jamais réécrit
    params["events_url"] = f"http://127.0.0.1:{PORT}/api/events"
    run_id = historique.nouvel_id()
    while any(j["id"] == run_id for j in centre.FILE.attente()) or historique.dossier(run_id).exists():
        time.sleep(1.05)  # identifiants à la seconde : jamais deux jobs avec le même dossier
        run_id = historique.nouvel_id()
    params.setdefault("output_dir", f"{historique.RACINE}/{run_id}")  # un dossier par run : plus d'écrasement
    job = centre.FILE.ajouter(params, priorite, run_id, campagne, nom, retry)
    state["run"] = centre.FILE._thread  # compatibilité : « un run est-il actif ? » = la file est-elle servie ?
    emit({"type": "file_execution", "file": centre.FILE.attente()})
    return {"ok": True, "run_id": run_id, "etat": "Running" if (centre.FILE.en_cours or {}).get("id") == run_id else "Queued",
            "contexte": job["contexte"], "revue": revue}


@app.post("/api/run")
async def run(req: Request):
    """Met le run dans la file de l'Execution Center (contexte figé) ; il démarre dès que le runner est libre."""
    b = await req.json()
    return await asyncio.to_thread(_call, _mettre_en_file, b, b.get("priorite") or "Normal", b.get("campagne", ""))


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
        _call(studio.entrer_en_revue, chemin, "bdd")  # validation humaine avant exécution
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
    pa = projets.actif() or {}
    return {"projet": pa.get("nom") or projet.PROJECT_DIR.name, "projet_chemin": str(projet.PROJECT_DIR),
            "projet_id": pa.get("id", ""), "projet_xray": pa.get("xray_projet", ""), "projet_jira": pa.get("jira_projet") or pa.get("xray_projet", ""),
            "projets": [{"id": p["id"], "nom": p["nom"]} for p in projets.lister()["projets"]],
            "applications": [{"slug": a["slug"], "nom": a.get("nom", a["slug"])} for a in amap.apps()],
            "application": cfg.get("slug"), "version": cfg.get("build", ""), "plateformes": cfg.get("plateformes", []),
            "session": session.plateforme(), "flux": state["flux"], "environnements": envs,
            "xray": {"configure": bool(os.environ.get("XRAY_CLIENT_ID")), "connecte": xray[0] if xray else None,
                     "detail": xray[1] if xray else "non vérifié"},
            "run_en_cours": centre.FILE.en_cours is not None,
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


# --------------------------------------------------------------------------- Test Design (couche de conception autour de Xray)
@app.get("/api/conception/vue")
async def conception_vue():
    return await asyncio.to_thread(_call, conception.vue_ensemble)


@app.get("/api/conception/cas")
async def conception_cas():
    return await asyncio.to_thread(_call, conception.cas_de_test)


@app.get("/api/conception/exigences")
async def conception_exigences():
    return await asyncio.to_thread(_call, conception.exigences)


@app.get("/api/conception/revue/{cle}")
async def conception_revue(cle: str):
    return await asyncio.to_thread(_call, conception.revue, cle)


@app.post("/api/conception/revue/{cle}")
async def conception_revue_action(cle: str, req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, conception.transition_revue, cle, b.get("action", ""), b.get("commentaire", ""), b.get("reviseur", ""))


@app.get("/api/conception/baselines")
def conception_baselines():
    return _call(conception.baselines)


@app.post("/api/conception/baselines")
async def conception_creer_baseline(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, conception.creer_baseline, b.get("nom", ""), b.get("description", ""))


@app.get("/api/conception/baselines/comparer")
async def conception_comparer(a: str, b: str = "courant"):
    return await asyncio.to_thread(_call, conception.comparer_baselines, a, b)


@app.get("/api/conception/mapping")
def conception_mapping():
    return _call(conception.mapping)


@app.post("/api/conception/mapping")
async def conception_enregistrer_mapping(req: Request):
    return await asyncio.to_thread(_call, conception.enregistrer_mapping, await req.json())


@app.get("/api/conception/mapping/tester")
async def conception_tester_mapping():
    return await asyncio.to_thread(_call, conception.tester_mapping)


@app.get("/api/conception/journal")
def conception_journal():
    return _call(conception.journal)


# --------------------------------------------------------------------------- Execution Center
@app.get("/api/centre/vue")
async def centre_vue():
    return await asyncio.to_thread(_call, centre.vue_ensemble)


@app.get("/api/centre/file")
def centre_file():
    return {"en_cours": {k: v for k, v in (centre.FILE.en_cours or {}).items() if k != "params"} or None, "attente": centre.FILE.attente()}


@app.post("/api/centre/file/annuler")
async def centre_annuler(req: Request):
    rid = (await req.json()).get("id", "")
    if not centre.FILE.annuler(rid):
        raise HTTPException(400, "Job absent de la file (déjà démarré ou terminé : utiliser Arrêter).")
    emit({"type": "file_execution", "file": centre.FILE.attente()})
    return {"ok": True}


@app.get("/api/centre/campagnes")
async def centre_campagnes():
    return await asyncio.to_thread(_call, centre.campagnes)


@app.post("/api/centre/campagnes")
async def centre_enregistrer_campagne(req: Request):
    return await asyncio.to_thread(_call, centre.enregistrer_campagne, await req.json())


@app.post("/api/centre/campagnes/{cid}/executer")
async def centre_executer_campagne(cid: str, req: Request):
    """Un job par plateforme de la campagne, à sa priorité."""
    b = await req.json()
    c = _call(centre.campagne, cid)
    if c["statut"] != "Active":
        raise HTTPException(400, "Campagne archivée.")
    jobs = [await asyncio.to_thread(_call, _mettre_en_file, centre.params_campagne(c, p, bool(b.get("dry_run"))), c["priorite"], cid, f"{c['nom']} · {p}")
            for p in c["plateformes"]]
    return {"ok": True, "jobs": jobs}


def _declencher_campagne(c: dict, origine: str, dry_run: bool = False) -> list[dict]:
    return [_mettre_en_file(centre.params_campagne(c, p, dry_run), c["priorite"], c["id"], f"{c['nom']} · {p} ({origine})") for p in c["plateformes"]]


def _planificateur():
    """Scheduler interne : toutes les 30 s, met en file les campagnes planifiées arrivées à échéance."""
    while True:
        time.sleep(30)
        try:
            for c in centre.campagnes_dues():
                _declencher_campagne(c, "planifié")
                emit({"type": "campagne_planifiee", "campagne": c["id"]})
        except Exception:
            pass  # un problème de planification ne doit jamais arrêter l'interface
        _call_silencieux(gouvernance.instantane)  # au plus un instantané des KPI par jour (Quality Governance › Trends)


@app.on_event("startup")
def _demarrer_planificateur():
    threading.Thread(target=_planificateur, daemon=True, name="planificateur").start()


@app.post("/api/externe/campagnes/{cid}/executer")
async def externe_campagne(cid: str, req: Request):
    """Webhook (CI/CD, après déploiement) : jeton de processus exigé (X-Atelier-Jeton)."""
    b = await req.json() if (await req.body()) else {}
    c = _call(centre.campagne, cid)
    if c["statut"] != "Active":
        raise HTTPException(400, "Campagne archivée.")
    return {"ok": True, "jobs": await asyncio.to_thread(_call, _declencher_campagne, c, "webhook", bool(b.get("dry_run")))}


@app.get("/api/centre/referentiel")
async def centre_referentiel():
    return await asyncio.to_thread(_call, centre.referentiel)


@app.post("/api/centre/verifier")
async def centre_verifier(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, centre.verifier, b.get("tests") or [], b.get("plateforme", ""), b.get("environnement", ""))


@app.get("/api/centre/runners")
async def centre_runners():
    return [await asyncio.to_thread(_call, centre.runner_local)]


@app.get("/api/centre/preuves/{run_id}")
async def centre_preuves(run_id: str):
    return await asyncio.to_thread(_call, centre.preuves, run_id)


@app.get("/api/centre/xray")
async def centre_xray():
    def calcul():
        return [{**centre.etat_xray(r["id"]), "debut": r["debut"], "statut_run": r["statut"], "xray_execution": r.get("xray")}
                for r in historique.lister(50)]
    return await asyncio.to_thread(_call, calcul)


@app.get("/api/centre/comparer")
async def centre_comparer(a: str, b: str):
    return await asyncio.to_thread(_call, centre.comparer, a, b)


@app.get("/api/centre/fichier")
def centre_fichier(chemin: str):
    """Preuve d'un run (lecture seule, sous results/runs uniquement)."""
    if not chemin.startswith(historique.RACINE + "/"):
        raise HTTPException(400, "Chemin hors des résultats d'exécution.")
    f = _call(projet.safe_path, chemin)
    if not f.is_file():
        raise HTTPException(404, "Fichier absent.")
    return FileResponse(f)


# --------------------------------------------------------------------------- Automation Studio
@app.get("/api/studio/vue")
async def studio_vue():
    return await asyncio.to_thread(_call, studio.vue_ensemble)


@app.get("/api/studio/locators")
async def studio_locators():
    return await asyncio.to_thread(_call, studio.locators)


@app.post("/api/studio/locators/tester")
async def studio_tester_locator(req: Request):
    """Teste un locator sur la session ouverte (device ou navigateur) et journalise le résultat."""
    b = await req.json()
    r = await asyncio.to_thread(_call, outils.check_locator, b.get("valeur", ""))
    return {**r, "journal": studio.noter_verification(b.get("id", ""), r)}


@app.get("/api/studio/keywords")
async def studio_keywords():
    return await asyncio.to_thread(_call, studio.keywords)


@app.get("/api/studio/page-objects")
async def studio_page_objects():
    return await asyncio.to_thread(_call, studio.page_objects)


@app.get("/api/studio/frameworks")
async def studio_frameworks():
    return await asyncio.to_thread(_call, studio.frameworks)


@app.get("/api/studio/git")
async def studio_git():
    return await asyncio.to_thread(_call, studio.git)


@app.get("/api/studio/revues")
async def studio_revues():
    return await asyncio.to_thread(_call, studio.revues_scripts)


@app.get("/api/studio/revue")
async def studio_revue(fichier: str):
    return await asyncio.to_thread(_call, studio.revue_script, fichier)


@app.post("/api/studio/revue")
async def studio_revue_action(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, studio.transition_script, b.get("fichier", ""), b.get("action", ""), b.get("commentaire", ""))


@app.get("/api/studio/mapping/{cle}")
async def studio_mapping(cle: str):
    return await asyncio.to_thread(_call, studio.mapping_bdd, cle)


@app.get("/api/studio/espaces")
def studio_espaces():
    return _call(studio.espaces)


@app.post("/api/studio/espaces")
async def studio_enregistrer_espace(req: Request):
    return await asyncio.to_thread(_call, studio.enregistrer_espace, await req.json())


@app.post("/api/studio/git/branche")
async def studio_branche(req: Request):
    return await asyncio.to_thread(_call, studio.creer_branche, (await req.json()).get("nom", ""))


@app.get("/api/studio/gitlab")
async def studio_gitlab():
    return await asyncio.to_thread(_call, studio.gitlab_etat)


@app.get("/api/studio/gitlab/commits")
async def studio_gitlab_commits(jours: int = 14, chemin: str = ""):
    return await asyncio.to_thread(_call, studio.gitlab_commits, jours, chemin)


@app.post("/api/studio/gitlab/mr")
async def studio_gitlab_mr(req: Request):
    """Push de la branche de travail + merge request (jamais de fusion) ; garde-fous dans studio.proposer_mr."""
    b = await req.json()
    return await asyncio.to_thread(_call, studio.proposer_mr, b.get("titre", ""), b.get("description", ""), b.get("cible", ""), b.get("derogation", ""))


@app.post("/api/studio/git/commit")
async def studio_commit(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, studio.commit, b.get("message", ""), b.get("fichiers") or [])


@app.post("/api/studio/builder")
async def studio_builder(req: Request):
    """Prévisualise (ecrire=false) ou écrit (ecrire=true, sans écrasement) un test assemblé depuis le socle."""
    b = await req.json()
    c = await asyncio.to_thread(_call, studio.construire_test, b.get("nom", ""), b.get("cle_xray", ""), b.get("jdd", ""),
                                b.get("etapes") or [], b.get("tags") or [], b.get("fichier", ""))
    if b.get("ecrire"):
        c["ecrit"] = await asyncio.to_thread(_call, studio.ecrire_test, c)
    return c


@app.get("/api/studio/journal")
def studio_journal():
    return _call(studio.journal)


# --------------------------------------------------------------------------- Failure Analysis
@app.get("/api/echecs/vue")
async def echecs_vue():
    return await asyncio.to_thread(_call, echecs.vue_ensemble)


@app.get("/api/echecs")
async def echecs_liste():
    return await asyncio.to_thread(_call, echecs.collecter)


@app.get("/api/echecs/investigation")
async def echecs_investigation(id: str):
    return await asyncio.to_thread(_call, echecs.investigation, id)


@app.post("/api/echecs/decision")
async def echecs_decision(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, echecs.decider, b.get("id", ""), b.get("decision", ""), b.get("categorie", ""), b.get("commentaire", ""))


@app.post("/api/echecs/regrouper")
async def echecs_regrouper(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, echecs.regrouper, b.get("id", ""), b.get("groupe", ""))


@app.post("/api/echecs/jira")
async def echecs_jira(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, echecs.associer_jira, b.get("id", ""), b.get("cle", ""))


@app.get("/api/echecs/ia/historique")
def echecs_ia_historique(id: str):
    return _call(echecs.historique_ia, id)


@app.post("/api/echecs/ia")
async def echecs_ia(req: Request):
    return await asyncio.to_thread(_call, echecs.demander_ia, (await req.json()).get("id", ""))


@app.post("/api/echecs/retest")
async def echecs_retest(req: Request):
    """Relance via la file de l'Execution Center ; l'ancien résultat n'est jamais écrasé."""
    b = await req.json()
    e = _call(echecs._evenement, b.get("id", ""))
    if not e["cle_xray"] and not b.get("tags"):
        raise HTTPException(400, "Test sans clé Xray : relancer la suite depuis l'Execution Center.")
    tags = b.get("tags") or [e["cle_xray"]]
    params = {"target": e["test_id"].split("::")[0] if "::" in e["test_id"] else "tests", "include_tags": tags,
              "variables": {"PLATFORM": e["plateforme"] or "web"}, "jdd_env": e["environnement"]}
    if not params["target"].endswith(".robot"):
        params["target"] = "tests"
    r = await asyncio.to_thread(_call, _mettre_en_file, params, "High", "", f"Retest {e['cle_xray'] or e['nom']}")
    _call(echecs.noter_retest, e["id"], r["run_id"])
    return r


@app.get("/api/echecs/retests")
async def echecs_retests(id: str):
    return await asyncio.to_thread(_call, echecs.resultats_retests, id)


@app.get("/api/echecs/journal")
def echecs_journal():
    return _call(echecs.journal)


# --------------------------------------------------------------------------- Quality Governance
@app.get("/api/gouvernance/vue")
async def gouvernance_vue():
    return await asyncio.to_thread(_call, gouvernance.vue_ensemble)


@app.get("/api/gouvernance/{section}")
async def gouvernance_section(section: str):
    fn = {"couverture": gouvernance.couverture_fonctionnelle, "automatisation": gouvernance.couverture_automatisation,
          "efficacite": gouvernance.efficacite, "sante": gouvernance.sante_automatisation, "stabilite": gouvernance.stabilite,
          "risques": gouvernance.risques, "tendances": gouvernance.tendances, "recommandations": gouvernance.recommandations,
          "releases": lambda: {"evaluations": gouvernance.releases(), "validations": gouvernance.validations_release()},
          "parametres": gouvernance.parametres, "kpis": gouvernance.kpis}.get(section)
    if not fn:
        raise HTTPException(404, "Section inconnue.")
    return await asyncio.to_thread(_call, fn)


@app.post("/api/gouvernance/releases")
async def gouvernance_evaluer(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, gouvernance.evaluer_release, b.get("version", ""), b.get("campagne", ""), b.get("environnement", ""), b.get("commit", ""))


@app.post("/api/gouvernance/releases/valider")
async def gouvernance_valider(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, gouvernance.valider_release, b.get("id", ""), b.get("decision", ""), b.get("commentaire", ""))


@app.post("/api/gouvernance/recommandations")
async def gouvernance_suivre(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, gouvernance.suivre_recommandation, b.get("id", ""), b.get("statut", ""), b.get("responsable", ""), b.get("commentaire", ""))


@app.post("/api/gouvernance/instantane")
async def gouvernance_instantane():
    return await asyncio.to_thread(_call, gouvernance.instantane, True)


@app.get("/api/gouvernance/parametres/historique")
def gouvernance_parametres_historique():
    return _call(gouvernance.historique_parametres)


@app.post("/api/gouvernance/parametres")
async def gouvernance_parametres(req: Request):
    return await asyncio.to_thread(_call, gouvernance.enregistrer_parametres, await req.json())


@app.get("/api/echecs/corrections")
def echecs_corrections():
    return _call(echecs.corrections)


@app.post("/api/echecs/corrections")
async def echecs_proposer(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, echecs.proposer_correction_locator, b.get("id", ""), b.get("valeur", ""), b.get("justification", ""))


@app.post("/api/echecs/corrections/action")
async def echecs_correction_action(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, echecs.faire_avancer_correction, b.get("id", ""), b.get("action", ""), b.get("commentaire", ""))


@app.post("/api/intelligence/analyser-jira")
async def intelligence_analyser():
    """Structure les critères d'acceptation et propose les règles métier candidates (file de validation)."""
    return await asyncio.to_thread(_call, intelligence_app.analyser_jira, True)


@app.get("/api/intelligence/versions/comparer")
async def intelligence_comparer(a: str, b: str = "courant"):
    return await asyncio.to_thread(_call, intelligence_app.comparer_versions, a, b)


@app.post("/api/intelligence/versions")
async def intelligence_creer_version(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, intelligence_app.creer_version, b.get("nom", ""), b.get("description", ""))


@app.post("/api/intelligence/versions/restaurer")
async def intelligence_restaurer(req: Request):
    return await asyncio.to_thread(_call, intelligence_app.restaurer_version, (await req.json()).get("nom", ""))


@app.post("/api/echecs/jira/doublons")
async def echecs_doublons(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, echecs.doublons_jira, b.get("id", ""), b.get("projet", ""))


@app.post("/api/echecs/jira/creer")
async def echecs_creer_jira(req: Request):
    """Création explicite (après consultation des doublons) ; jamais automatique."""
    b = await req.json()
    return await asyncio.to_thread(_call, echecs.creer_anomalie_jira, b.get("id", ""), b.get("projet", ""),
                                   b.get("resume", ""), b.get("description", ""), bool(b.get("lier_test", True)))


@app.post("/api/conception/publier")
async def conception_publier(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, conception.publier_bdd, b.get("cle", ""), b.get("projet", ""), b.get("decision", ""))


@app.get("/api/conception/sync-historique")
def conception_sync_historique():
    return _call(conception.historique_sync)


@app.post("/api/centre/xray/rejouer")
async def centre_rejouer_xray(req: Request):
    return await asyncio.to_thread(_call, centre.rejouer_xray, (await req.json()).get("run", ""))


# --------------------------------------------------------------------------- Application Intelligence
@app.get("/api/intelligence/{section}")
async def intelligence_section(section: str):
    fn = {"vue": intelligence_app.vue_ensemble, "jira": intelligence_app.jira, "ecrans": intelligence_app.ecrans,
          "regles": lambda: intelligence_app.noeuds(["regle"]), "parcours": lambda: intelligence_app.noeuds(["parcours", "action"]),
          "api": intelligence_app.api_endpoints, "changements": intelligence_app.changements, "validation": intelligence_app.validation,
          "criteres": lambda: intelligence_app.analyser_jira(False), "versions": intelligence_app.versions}.get(section)
    if not fn:
        raise HTTPException(404, "Section inconnue.")
    return await asyncio.to_thread(_call, fn)


def main():
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
