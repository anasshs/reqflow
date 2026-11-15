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
import collections
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
from atelier.discovery import sessions_discovery  # noqa: E402  (abonne la timeline au bus d'événements)
from atelier.generation import sessions_agent  # noqa: E402
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
    "jql_candidats": os.environ.get("XRAY_CANDIDATS_JQL", ""),  # vide : tests du projet Xray actif (aucune clé client en dur)
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
    threading.Thread(target=_call_silencieux, args=(_verifier_connexions, True, 0), daemon=True).start()  # page Connexions prête


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


@app.post("/api/connexions/secret/verser")
async def connexions_secret_verser(req: Request):
    """Verse dans le coffre un secret présent seulement comme variable du poste (valeur jamais renvoyée)."""
    r = _call(projets.verser_dans_coffre, str((await req.json()).get("nom", "")))
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
    threading.Thread(target=_call_silencieux, args=(_verifier_connexions, True, 0), daemon=True).start()
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
    if ev.get("type") == "mcp_outil":  # activité de l'agent, gardée pour la vue « Cursor en direct » et pour la revue
        ev = {**ev, "heure": time.strftime("%H:%M:%S")}
        state.setdefault("activite_mcp", collections.deque(maxlen=300)).append(ev)
        _call_silencieux(sessions_agent.enregistrer_appel, ev)
        if ev.get("etat") == "fin" and ev.get("famille") == "ecran" and state["flux"].get("platform") in ("android", "ios"):
            asyncio.get_running_loop().run_in_executor(None, _tracer_ecran_mobile, ev.get("nom", ""))
    if ev.get("type") == "session" and ev.get("etat") == "ouverte":
        state["flux"] = {"platform": ev.get("platform"), "udid": ev.get("udid") or None}
    emit(ev)
    _call_silencieux(sessions_discovery.observer_evenement, ev)  # MCP / listener : timeline de la session Discovery
    return {"ok": True}


SANS_CACHE = {"Cache-Control": "no-cache"}  # le navigateur revalide : après un git pull, les nouveaux écrans apparaissent


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
    return FileResponse(STATIC / "index.html", headers=SANS_CACHE)


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


_pool_sante = None
DELAI_SANTE = 8  # secondes par contrôle : au-delà, la page s'affiche et le résultat arrive au rafraîchissement suivant


def _controles() -> dict:
    """Contrôles de connexion (fonctions sans argument → (ok, détail)), exécutés en parallèle."""
    def appium():
        return _http_ok(session.APPIUM_URL.rstrip("/") + "/status"), session.APPIUM_URL

    def device():
        d = outils.list_devices()
        n = len(d["android"]) + len(d["ios_simulateurs"]) + len(d["ios_physiques"])
        return n > 0, f"{len(d['android'])} Android, {len(d['ios_simulateurs']) + len(d['ios_physiques'])} iOS"

    def xray():
        from atelier.integrations.xray import XrayClient
        XrayClient().token()
        return True, "connecté"

    def jira():
        from atelier.integrations.jira import JiraClient
        return True, JiraClient().myself().get("displayName", "connecté")

    def gitlab():
        from atelier.integrations.gitlab import GitLabClient
        u = GitLabClient().utilisateur()
        return True, f"{u.get('login')} · {os.environ.get('GITLAB_PROJET', '')}"
    return {"appium": appium, "device": device, "xray": xray, "jira": jira, "gitlab": gitlab}


def _verifier_connexions(forcer: bool = False, attendre: float | None = None) -> dict:
    """Lance les contrôles (au plus toutes les 10 min, sauf forcer) en parallèle et attend au plus « attendre »
    secondes : un contrôle plus lent est marqué « en cours » et met le cache à jour quand il se termine."""
    global _pool_sante
    import concurrent.futures

    cache = state["sante_cache"]
    if forcer or time.time() - cache.get("t", 0) > 600 or "futures" not in cache:
        if _pool_sante is None:
            _pool_sante = concurrent.futures.ThreadPoolExecutor(max_workers=6, thread_name_prefix="sante")
        cache["t"] = time.time()
        for cle in _controles():
            cache.pop(cle, None)  # pas d'ancien résultat présenté comme actuel
        futures = {}
        for cle, fn in _controles().items():
            def tache(cle=cle, fn=fn, gen=cache["t"]):
                try:
                    r = fn()
                except Exception as e:  # noqa: BLE001
                    r = (False, str(e)[:160])
                if state["sante_cache"].get("t") == gen:  # pas de résultat périmé après une nouvelle vérification
                    state["sante_cache"][cle] = r
                return r
            futures[cle] = _pool_sante.submit(tache)
        cache["futures"] = futures
    en_cours = [f for f in cache["futures"].values() if not f.done()]
    attendre = DELAI_SANTE if attendre is None else attendre
    if en_cours and attendre > 0:
        concurrent.futures.wait(en_cours, timeout=attendre)
    return cache


def _sante_items() -> list[dict]:
    items = []

    def item(cle, nom, ok, detail, solution, optionnel=False):
        items.append({"cle": cle, "nom": nom, "ok": ok, "detail": detail,
                      "solution": "" if ok else solution, "optionnel": optionnel})

    cache = _verifier_connexions()
    attente = (None, f"pas de réponse en {DELAI_SANTE} s : vérification toujours en cours (réseau, proxy ou certificat ?)")

    def res(cle):
        r = cache.get(cle)
        return r if r else attente

    ok, detail = res("appium")
    item("appium", "Appium", ok, detail, "Lance « appium » dans un terminal (mobile uniquement).", optionnel=True)
    ok, detail = res("device")
    item("device", "Device mobile", ok, detail,
         "Démarre un émulateur Android ou le Simulateur iOS, ou branche un téléphone (débogage USB).",
         optionnel=True)
    try:
        import playwright  # noqa: F401
        pw = True
    except ImportError:
        pw = False
    item("web", "Navigateur web", pw, "Playwright installé" if pw else "",
         "pip install playwright puis « playwright install chromium ».", optionnel=True)
    item("xray", "Xray", *res("xray"),
         "Renseigne XRAY_CLIENT_ID / XRAY_CLIENT_SECRET (et XRAY_CA_BUNDLE derrière le proxy).")
    item("jira", "Jira", *res("jira"),
         "Renseigne JIRA_BASE_URL, JIRA_EMAIL et JIRA_API_TOKEN.", optionnel=True)
    item("gitlab", "GitLab", *res("gitlab"),
         "URL et projet GitLab dans Paramètres › Projets ; jeton d'accès personnel (portées api, write_repository) "
         "dans GITLAB_TOKEN ou la variable du projet ; GITLAB_CA_BUNDLE pour un certificat interne.", optionnel=True)
    envs_db = sorted({k.split("_")[1].lower() for k in os.environ if re.match(r"DB_[A-Z0-9]+_HOST$", k)})
    item("base", "Base de données", bool(envs_db), ", ".join(envs_db) or "",
         "Renseigne DB_<ENV>_HOST, _PORT, _SID, _USER, _PASSWORD pour la recherche de données.",
         optionnel=True)
    age = time.time() - state["dernier_mcp"] if state["dernier_mcp"] else None
    item("cursor", "Cursor / Claude Desktop", age is not None and age < 900,
         f"dernière action il y a {int(age // 60)} min" if age is not None else "pas encore vu",
         "Paramètres › Cursor / Claude : installer le MCP et les règles en un clic.",
         optionnel=True)
    return items


@app.get("/api/sante")
async def sante(rafraichir: bool = False):
    if rafraichir:
        await asyncio.to_thread(_verifier_connexions, True, 0)
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


@app.get("/api/devices/diagnostic")
def devices_diagnostic():
    return _call(session.diagnostic_devices)


@app.get("/api/agents-ia")
def agents_ia_etat():
    from atelier.integrations import agents_ia

    age = time.time() - state["dernier_mcp"] if state["dernier_mcp"] else None
    return {**_call(agents_ia.etat, PORT), "derniere_activite_s": int(age) if age is not None else None}


@app.post("/api/agents-ia/installer")
async def agents_ia_installer(req: Request):
    from atelier.integrations import agents_ia

    b = await req.json()
    if b.get("regles"):
        return _call(agents_ia.installer_regles, bool(b.get("ecraser")))
    return _call(agents_ia.installer, b.get("agent", "cursor"), PORT)


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
            if session.is_web():
                return session.screenshot_png()
            im = state.get("image_mcp")  # navigateur piloté par l'agent dans le processus MCP
            return im["png"] if im and time.time() - im["t"] < 1800 else None
        adb = session.chemin_adb() if p == "android" else None
        if adb:
            cmd = [adb] + (["-s", udid] if udid else []) + ["exec-out", "screencap", "-p"]
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


@app.post("/api/mcp/image")
async def mcp_image(req: Request):
    """Image du navigateur piloté par l'agent (processus MCP), envoyée après chaque action visible."""
    import base64

    b = await req.json()
    png = base64.b64decode(b.get("png") or "")
    if not png or len(png) > 8_000_000:
        raise HTTPException(400, "Image absente ou trop grande.")
    state["image_mcp"] = {"png": png, "t": time.time(), "outil": b.get("outil", "")}
    _call_silencieux(sessions_agent.enregistrer_image, png, b.get("outil", ""))
    emit({"type": "mcp_image", "outil": b.get("outil", "")})
    return {"ok": True}


def _tracer_ecran_mobile(outil: str):
    """Mobile : l'écran après une action de l'agent est lu sur le device (adb / simctl) et gardé dans sa session."""
    png = _grab()
    if png:
        _call_silencieux(sessions_agent.enregistrer_image, png, outil)


@app.get("/api/mcp/controle")
def mcp_controle():
    """Lu par le serveur MCP avant chaque outil : « actif », « pause » ou « arret » (décidé par l'automaticien)."""
    return {"etat": state.get("controle_agent", "actif")}


@app.post("/api/agent/pilotage")
async def agent_pilotage(req: Request):
    """Pause, arrêt ou reprise de l'agent (Cursor) depuis la vue en direct."""
    etat = (await req.json()).get("etat", "")
    if etat not in ("actif", "pause", "arret"):
        raise HTTPException(400, "État : actif, pause ou arret.")
    state["controle_agent"] = etat
    emit({"type": "agent_pilotage", "etat": etat})
    return {"etat": etat}


@app.get("/api/agent/sessions")
async def agent_sessions():
    return await asyncio.to_thread(_call, sessions_agent.lister)


@app.get("/api/agent/sessions/{sid}")
async def agent_session(sid: str):
    return await asyncio.to_thread(_call, sessions_agent.detail, sid)


@app.get("/api/agent/sessions/{sid}/{nom}")
async def agent_session_image(sid: str, nom: str):
    return Response(_call(sessions_agent.image, sid, nom), media_type="image/png", headers={"Cache-Control": "no-store"})


@app.get("/api/mcp/activite")
async def mcp_activite(depuis: int = 0):
    """Appels d'outils de l'agent (Cursor, Claude) : les plus récents, pour la vue « Cursor en direct »."""
    l = list(state.get("activite_mcp") or [])
    actif = time.time() - (state.get("dernier_mcp") or 0) < 120
    im = state.get("image_mcp")
    return {"actif": actif, "dernier": state.get("dernier_mcp"), "evenements": l[-max(1, min(300, depuis or 150)):],
            "controle": state.get("controle_agent", "actif"), "attente": _attente_courante(),
            "flux": state["flux"], "image_agent": {"t": im["t"], "outil": im["outil"]} if im else None}


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
    from atelier.intelligence import source_tests

    jql = jql or (source_tests.source()["jql"] if amap.app_courante() else "") or config()["jql_candidats"] \
        or (f'project = "{projets.cle_xray()}" ORDER BY key' if projets.cle_xray() else "")
    if not jql:
        raise HTTPException(400, "Aucune JQL de tests : déclarer la clé Xray du projet (Paramètres › Projets).")
    return await asyncio.to_thread(_call, outils.xray_search_tests, jql, 80)


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
                b.get("build", ""), b.get("langue", "fr"), None, None,
                b.get("projet_xray") or projets.cle_xray(), b.get("tests_xray") or {}, b.get("type", ""), b.get("api"))
    atelier = config()  # les réglages de connexion suivent l'application
    for p in ("android", "ios", "web"):
        if b.get(p):
            atelier["apps"].setdefault(p, {}).update({k: v for k, v in b[p].items() if v})
    save_config(atelier)
    emit({"type": "app_change", "slug": cfg["slug"]})
    return cfg


@app.get("/api/centre/vue-xray")
async def centre_vue_xray(depuis: str = "", jusqu: str = ""):
    return await asyncio.to_thread(_call, centre.vue_xray, 20, depuis, jusqu)


@app.get("/api/centre/xray/execution/{cle}")
async def centre_xray_execution(cle: str):
    return await asyncio.to_thread(_call, centre.detail_execution_xray, cle)


@app.post("/api/centre/xray/execution/{cle}/relancer")
async def centre_xray_relancer(cle: str, req: Request):
    """Nouveau run dans la même Exécution (Test Execution Xray) : tous ses tests automatisés, ou ses échecs."""
    b = await req.json()
    r = _call(centre.params_relance, cle, bool(b.get("echecs")), b.get("plateforme", ""))
    job = await asyncio.to_thread(_call, _mettre_en_file, r["params"], b.get("priorite") or "Normal", r["campagne"],
                                  f"{cle} · {'échecs' if b.get('echecs') else 'tous les tests'}")
    return {**job, "tests": r["tests"], "non_automatises": r["non_automatises"]}


@app.get("/api/centre/xray/statuts")
async def centre_xray_statuts():
    """Statuts de test run du projet (Xray) ; mis en cache pour la session."""
    from atelier.intelligence import patrimoine_xray

    cle = projets.cle_xray()
    cache = state.setdefault("statuts_xray", {})
    if cle not in cache:
        cache[cle] = await asyncio.to_thread(_call, patrimoine_xray.statuts_runs)
    return cache[cle]


@app.post("/api/centre/xray/run-statut")
async def centre_xray_run_statut(req: Request):
    """Change le statut d'un test run dans Xray (action explicite depuis le tableau de bord)."""
    from atelier.intelligence import patrimoine_xray

    b = await req.json()
    r = await asyncio.to_thread(_call, patrimoine_xray.changer_statut_run, b.get("execution", ""), b.get("test", ""), b.get("statut", ""))
    emit({"type": "xray_change", **r})
    return r


@app.get("/api/centre/xray/execution/{cle}/transitions")
async def centre_xray_transitions(cle: str):
    from atelier.integrations.jira import JiraClient

    return await asyncio.to_thread(_call, lambda: JiraClient().transitions(cle))


@app.post("/api/centre/xray/execution/{cle}/transition")
async def centre_xray_transition(cle: str, req: Request):
    """Statut Jira (workflow) de la Test Execution : transition explicite depuis le tableau de bord."""
    from atelier.integrations.jira import JiraClient
    from atelier.intelligence import patrimoine_xray

    nom = (await req.json()).get("transition", "")
    statut = await asyncio.to_thread(_call, lambda: JiraClient().transition(cle, nom))
    _call(patrimoine_xray.maj_statut_execution, cle, statut or nom)
    return {"execution": cle, "statut": statut or nom}


@app.get("/api/centre/executions-xray")
async def centre_executions_xray():
    return await asyncio.to_thread(_call, centre.executions_xray)


@app.post("/api/centre/executions-xray/actualiser")
async def centre_executions_actualiser(req: Request):
    from atelier.intelligence import patrimoine_xray

    b = await req.json() if (await req.body()) else {}
    return await asyncio.to_thread(_call, patrimoine_xray.importer_executions, "", None, b.get("depuis", ""), b.get("jusqu", ""))


@app.get("/api/conception/repository")
def conception_repository():
    """Dossiers du Test Repository Xray et applications du projet qui s'y rattachent."""
    from atelier.intelligence import patrimoine_xray

    return {**_call(patrimoine_xray.dossiers_repository), "applications": [
        {"slug": a["slug"], "nom": a.get("nom", a["slug"]), "type": a.get("type", ""), "plateformes": a.get("plateformes", []),
         "dossiers": (a.get("tests_xray") or {}).get("dossiers", []), "valeurs": (a.get("tests_xray") or {}).get("valeurs", [])}
        for a in amap.apps()], "active": amap.app_courante()}


@app.get("/api/apps/configuration")
def apps_configuration():
    """Configuration de l'application active : source des tests (JQL + dossiers) et politique des US."""
    from atelier.intelligence import patrimoine_xray, source_tests, testabilite_us

    slug = amap.app_courante()
    if not slug:
        return {"application": None}
    cfg = amap.config_app(slug)
    return {"application": {"slug": slug, "nom": cfg.get("nom", slug), "projet_xray": cfg.get("projet_xray") or projets.cle_xray()},
            "source": _call(source_tests.source, slug), "dossiers": _call(patrimoine_xray.dossiers_repository)["dossiers"],
            "espaces": [e for e in testabilite_us.tous_espaces() if e.get("application") == slug],
            "espaces_non_rattaches": [e for e in testabilite_us.tous_espaces() if not e.get("application")],
            "copie_marquee": patrimoine_xray.charger_brut_marque()}


@app.post("/api/apps/source")
async def apps_source(req: Request):
    from atelier.intelligence import source_tests

    b = await req.json()
    r = _call(source_tests.enregistrer, b.get("slug") or amap.app_courante(), b.get("jql", ""), b.get("dossiers") or [])
    emit({"type": "app_change", "slug": b.get("slug") or amap.app_courante()})
    return r


@app.post("/api/apps/source/conteneurs")
async def apps_source_conteneurs(req: Request):
    """JQL des Test Plans et des Test Executions de l'application."""
    from atelier.intelligence import source_tests

    b = await req.json()
    r = _call(source_tests.enregistrer_conteneurs, b.get("slug") or amap.app_courante(), b.get("jql_plans", ""), b.get("jql_executions", ""))
    emit({"type": "app_change", "slug": b.get("slug") or amap.app_courante()})
    return r


@app.post("/api/apps/source/tester")
async def apps_source_tester(req: Request):
    from atelier.intelligence import source_tests

    return await asyncio.to_thread(_call, source_tests.tester, (await req.json()).get("jql", ""))


@app.post("/api/testabilite/espaces/rattacher")
async def testabilite_rattacher(req: Request):
    from atelier.intelligence import testabilite_us

    b = await req.json()
    return _call(testabilite_us.rattacher_espace, b.get("projet_jira", ""), b.get("application") or amap.app_courante())


@app.post("/api/apps/dupliquer")
async def apps_dupliquer(req: Request):
    b = await req.json()
    r = _call(amap.dupliquer_app, b.get("slug", ""), b.get("nom", ""), bool(b.get("avec_carte")))
    emit({"type": "app_change", "slug": r["slug"]})
    return r


@app.post("/api/apps/archiver")
async def apps_archiver(req: Request):
    """Archive locale (restaurable) : aucun effet sur Xray, Jira ni les tests du dépôt."""
    r = _call(amap.archiver_app, (await req.json()).get("slug", ""))
    emit({"type": "app_change", "slug": r.get("active")})
    return r


@app.get("/api/apps/archives")
def apps_archives():
    return _call(amap.archives_apps)


@app.post("/api/apps/restaurer")
async def apps_restaurer(req: Request):
    return _call(amap.restaurer_app, (await req.json()).get("archive", ""))


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
    champs = {k: b[k] for k in ("build", "comptes", "ecran_depart", "etape_assistant", "langue", "plateformes",
                                "android", "ios", "web", "api") if k in b}
    if str(b.get("nom") or "").strip():
        champs["nom"] = str(b["nom"]).strip()  # le slug (dossier) ne change pas
    if "projet_xray" in b:
        champs["projet_xray"] = str(b["projet_xray"] or "").strip().upper()
    if "tests_xray" in b:  # dossiers et valeurs se complètent : une clé absente garde sa valeur actuelle
        actuel = (amap.config_app(b.get("slug") or None).get("tests_xray") or {})
        nouveau = b["tests_xray"] or {}
        champs["tests_xray"] = amap.normaliser_tests_xray({**{k: actuel[k] for k in ("dossiers", "valeurs") if k in actuel and k not in nouveau}, **nouveau})
    if "liste_rouge" in b:
        champs["liste_rouge"] = {"textes": [t for t in b["liste_rouge"] if t.strip()],
                                 "cles": amap.config_app().get("liste_rouge", {}).get("cles", [])}
    return _call(amap.maj_app, b.get("slug") or None, **champs)


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
    return FileResponse(STATIC / "plateforme.html", headers=SANS_CACHE)


@app.get("/static/{nom}")
def fichier_statique(nom: str):
    if not re.fullmatch(r"[a-z_]+\.(js|css)", nom) or not (STATIC / nom).is_file():
        raise HTTPException(404, "Fichier inconnu.")
    return FileResponse(STATIC / nom, headers=SANS_CACHE)


def _liste(v: str) -> list[str] | None:
    return [x for x in v.split(",") if x] or None


@app.get("/api/graphes/referentiel")
def graphes_referentiel():
    return espaces.referentiel()


@app.get("/api/graphes/connaissance")
async def graphe_connaissance(types: str = "", categories: str = "", plateforme: str = "", recherche: str = "",
                              centre: str = "", profondeur: int = 1, patrimoine: str = "lie", perimetre: str = ""):
    return await asyncio.to_thread(_call, espaces.vue_connaissance, _liste(types), _liste(categories), plateforme,
                                   recherche, centre, profondeur, patrimoine, perimetre)


@app.get("/api/graphes/perimetres")
async def graphes_perimetres():
    return await asyncio.to_thread(_call, espaces.perimetres)


@app.get("/api/graphes/parcours-ordonne")
async def graphes_parcours_ordonne(id: str):
    from atelier.generation import parcours_bdd

    return await asyncio.to_thread(_call, parcours_bdd.etapes_parcours, id)


@app.get("/api/graphes/plan-de-test")
async def graphes_plan_de_test(module: str):
    from atelier.intelligence import plan_test

    return await asyncio.to_thread(_call, plan_test.plan, module)


@app.get("/api/couverture")
async def couverture_calcul(version: str = "", plateforme: str = ""):
    """Couverture des exigences (Test Xray ↔ Story / Requirement) : 4 indicateurs, par niveau."""
    from atelier.intelligence import couverture_exigences

    return await asyncio.to_thread(_call, couverture_exigences.calculer, version, plateforme)


@app.post("/api/couverture/importer")
async def couverture_importer():
    """Lit dans Jira les exigences du périmètre, leurs tests liés et leurs parents (lecture seule, journalisé)."""
    from atelier.intelligence import couverture_exigences

    return await asyncio.to_thread(_call, couverture_exigences.importer)


@app.get("/api/couverture/reglages")
async def couverture_reglages():
    from atelier.intelligence import couverture_exigences

    return _call(couverture_exigences.reglages)


@app.post("/api/couverture/reglages")
async def couverture_reglages_maj(req: Request):
    from atelier.intelligence import couverture_exigences

    b = await req.json()
    return _call(couverture_exigences.enregistrer_reglages, b.get("jql_exigences", ""), b.get("criteres_actifs"))


@app.post("/api/couverture/critere")
async def couverture_critere(req: Request):
    """Tests qui couvrent un critère d'acceptation (enrichissement local, historisé)."""
    from atelier.intelligence import couverture_exigences

    b = await req.json()
    return _call(couverture_exigences.associer_critere, b.get("exigence", ""), int(b.get("index") or 0), b.get("tests") or [])


@app.post("/api/couverture/instantane")
async def couverture_instantane(req: Request):
    from atelier.intelligence import couverture_exigences

    b = await req.json()
    return await asyncio.to_thread(_call, couverture_exigences.enregistrer_instantane, b.get("version", ""), b.get("commentaire", ""))


@app.get("/api/couverture/evolution")
async def couverture_evolution():
    from atelier.intelligence import couverture_exigences

    return _call(couverture_exigences.evolution)


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


# --------------------------------------------------------------------------- Testabilité des US (stratégie actionnable)
@app.get("/api/testabilite/espaces")
def testabilite_espaces(sprint: str = ""):
    from atelier.intelligence import fournisseur_ia, testabilite_us

    return {"espaces": _call(testabilite_us.espaces), "ia": fournisseur_ia.etat(), "indicateurs": _call(testabilite_us.indicateurs, sprint),
            "portees": testabilite_us.PORTEES}


@app.get("/api/testabilite/jira/projets")
async def testabilite_jira_projets(q: str = ""):
    from atelier.intelligence import testabilite_us

    return await asyncio.to_thread(_call, testabilite_us.chercher_projets_jira, q)


@app.get("/api/testabilite/jira/projet")
async def testabilite_jira_projet(cle: str):
    from atelier.intelligence import testabilite_us

    return await asyncio.to_thread(_call, testabilite_us.details_projet_jira, cle)


@app.get("/api/testabilite/sprints")
async def testabilite_sprints():
    from atelier.intelligence import testabilite_us

    return await asyncio.to_thread(_call, testabilite_us.sprints)


@app.post("/api/testabilite/sprints/figer")
async def testabilite_figer(req: Request):
    from atelier.intelligence import testabilite_us

    b = await req.json()
    return _call(testabilite_us.figer_sprint, b.get("espace", ""), str(b.get("sprint", "")))


@app.get("/api/testabilite/sprints/bilan")
def testabilite_bilan(espace: str, sprint: str):
    from atelier.intelligence import testabilite_us

    return _call(testabilite_us.bilan_sprint, espace, sprint)


@app.post("/api/testabilite/espaces")
async def testabilite_enregistrer_espace(req: Request):
    from atelier.intelligence import testabilite_us

    return _call(testabilite_us.enregistrer_espace, await req.json())


@app.post("/api/testabilite/espaces/supprimer")
async def testabilite_supprimer_espace(req: Request):
    from atelier.intelligence import testabilite_us

    return _call(testabilite_us.supprimer_espace, (await req.json()).get("projet_jira", ""))


@app.post("/api/testabilite/detecter")
async def testabilite_detecter(req: Request):
    from atelier.intelligence import testabilite_us

    b = await req.json() if (await req.body()) else {}
    return await asyncio.to_thread(_call, testabilite_us.detecter, None, 500, str(b.get("sprint") or ""), str(b.get("portee") or ""))


@app.post("/api/testabilite/reponses")
async def testabilite_reponses(req: Request):
    from atelier.intelligence import testabilite_us

    return await asyncio.to_thread(_call, testabilite_us.relever_reponses, (await req.json()).get("cle", ""))


@app.get("/api/testabilite/file")
def testabilite_file(espace: str = "", statut: str = "", sprint: str = ""):
    from atelier.intelligence import testabilite_us

    return _call(testabilite_us.file, espace, statut, sprint)


@app.get("/api/testabilite/us/{cle}")
def testabilite_detail(cle: str):
    from atelier.intelligence import testabilite_us

    return _call(testabilite_us.detail, cle)


@app.post("/api/testabilite/us/{cle}/{action}")
async def testabilite_action(cle: str, action: str, req: Request):
    """Actions explicites sur une US ; les écritures Jira / Xray (envoyer, publier) ne partent que d'ici."""
    from atelier.intelligence import testabilite_us as t

    b = await req.json() if (await req.body()) else {}
    actions = {"analyser": lambda: t.analyser(cle), "analyser-ia": lambda: t.analyser_ia(cle),
               "questions": lambda: t.modifier_questions(cle, b.get("texte", "")), "envoyer": lambda: t.envoyer_questions(cle),
               "reponses": lambda: t.relever_reponses(cle), "proposer-cas": lambda: t.proposer_cas(cle),
               "cas": lambda: t.modifier_cas(cle, b.get("id", ""), b), "decision": lambda: t.decider_cas(cle, b.get("id", ""), b.get("decision", ""), b.get("motif", "")),
               "publier": lambda: t.publier_cas(cle), "non-testable": lambda: t.non_testable(cle, b.get("justification", "")),
               "convertir": lambda: t.convertir_cas(cle, b.get("id", ""), b.get("vers", ""))}
    if action not in actions:
        raise HTTPException(404, f"Action inconnue : {action}")
    return await asyncio.to_thread(_call, actions[action])


@app.get("/api/conception/mapping/statuts-jira")
async def conception_statuts_jira(projet: str = ""):
    return await asyncio.to_thread(_call, conception.statuts_workflow_test, projet)


# --------------------------------------------------------------------------- Test Design › Règles de test
# --------------------------------------------------------------------------- Application Discovery
@app.get("/api/graphes/sources")
async def graphes_sources():
    from atelier.discovery import connaissance

    return await asyncio.to_thread(_call, connaissance.sources)


@app.get("/api/discovery/vue")
async def discovery_vue(graphe: int = 1):
    return await asyncio.to_thread(_call, sessions_discovery.vue_ensemble, bool(graphe))


@app.get("/api/discovery/vue-graphe")
async def discovery_vue_graphe():
    return await asyncio.to_thread(_call, sessions_discovery.graphe_ensemble)


@app.get("/api/discovery/sessions")
def discovery_sessions():
    return _call(sessions_discovery.lister)


@app.post("/api/discovery/sessions")
async def discovery_creer(req: Request):
    return _call(sessions_discovery.creer, await req.json())


@app.get("/api/discovery/sessions/{sid}")
def discovery_session(sid: str):
    return _call(sessions_discovery.resultats, sid)


@app.post("/api/discovery/sessions/{sid}/{action}")
async def discovery_action(sid: str, action: str, req: Request):
    b = await req.json() if (await req.body()) else {}
    actions = {"demarrer": lambda: sessions_discovery.demarrer(sid), "pause": lambda: sessions_discovery.pause(sid),
               "arreter": lambda: sessions_discovery.arreter(sid),
               "annoter": lambda: sessions_discovery.annoter(sid, b.get("texte", ""), bool(b.get("sensible")), b.get("ecran", ""),
                                                             b.get("cle", ""))}
    if action not in actions:
        raise HTTPException(404, f"Action inconnue : {action}")
    r = await asyncio.to_thread(_call, actions[action])
    emit({"type": "discovery", "session": sid, "statut": r.get("statut")})
    return r


@app.post("/api/discovery/agir")
async def discovery_agir(req: Request):
    """Action depuis le Studio (tap / retour), classée et autorisée selon l'environnement de la session."""
    b = await req.json()
    r = await asyncio.to_thread(_call, sessions_discovery.agir, b.get("action", "tap"), b.get("locator", ""),
                                b.get("element") or {}, bool(b.get("confirme")))
    emit({"type": "discovery", "agir": r.get("execute")})
    return r


@app.post("/api/discovery/classer")
async def discovery_classer(req: Request):
    from atelier.discovery import classement

    b = await req.json()
    s = sessions_discovery.active()
    el = b.get("element") or {}
    return {**_call(classement.classer, el), "autorisation": _call(classement.autorise, el, "guidee",
                                                                   (s or {}).get("config", {}).get("environnement", ""))}


@app.get("/api/discovery/classement")
def discovery_classement():
    from atelier.discovery import classement

    return {**_call(classement.regles), "classes": classement.CLASSES, "politique_defaut": classement.POLITIQUE_DEFAUT,
            "journal": _call(classement.journal_autorisations, 30)}


@app.post("/api/discovery/classement")
async def discovery_classement_maj(req: Request):
    from atelier.discovery import classement

    b = await req.json()
    if "cle" in b:
        return _call(classement.marquer, b["cle"], b.get("classe", "auto"))
    return _call(classement.maj_regles, b.get("sensibles"), b.get("environnements"), None, b.get("liste_rouge_levee"), b.get("agent_sensible"))


@app.get("/api/discovery/suggestions")
async def discovery_suggestions(ia: int = 1):
    from atelier.discovery import assistance

    return await asyncio.to_thread(_call, assistance.suggerer_courant, bool(ia))


@app.get("/api/discovery/reseau")
def discovery_reseau():
    """Appels réseau observés depuis le début de la session en cours (web), rapprochés du Knowledge Graph."""
    from atelier.discovery import comportements

    s = sessions_discovery.active()
    t0 = min((p.get("t0", 0) for p in (s or {}).get("periodes", [])), default=0) if s else time.time()
    return {"session": (s or {}).get("id"), "endpoints": _call(lambda: comportements.rapprocher(comportements.endpoints(comportements.journal_reseau(t0))))}


@app.get("/api/discovery/correlation")
async def discovery_correlation():
    from atelier.discovery import correlation

    return await asyncio.to_thread(_call, correlation.synthese)


@app.get("/api/discovery/correlation/{eid}")
async def discovery_correlation_ecran(eid: str):
    from atelier.discovery import correlation

    return await asyncio.to_thread(_call, correlation.ecran, eid)


@app.post("/api/discovery/correlation/confirmer")
async def discovery_correlation_confirmer(req: Request):
    from atelier.discovery import correlation

    b = await req.json()
    r = _call(correlation.confirmer, b["ecran"], b["cle"])
    emit({"type": "graphe_change"})
    return r


@app.post("/api/discovery/correlation/gitlab")
async def discovery_correlation_gitlab(req: Request):
    from atelier.discovery import correlation

    return await asyncio.to_thread(_call, correlation.commits_gitlab, (await req.json()).get("fichiers") or [])


@app.get("/api/discovery/propositions")
def discovery_propositions(session: str = ""):
    from atelier.discovery import apprentissage

    return _call(apprentissage.propositions, session)


@app.post("/api/discovery/propositions/decider")
async def discovery_decider(req: Request):
    from atelier.discovery import apprentissage

    b = await req.json()
    r = _call(apprentissage.decider, b.get("id", ""), bool(b.get("valider")), b.get("motif", ""))
    emit({"type": "carte_change"})
    return r


@app.post("/api/discovery/parcours-bdd")
async def discovery_parcours_bdd(req: Request):
    """Brouillon de scénario BDD (Test Design) depuis un chemin d'écrans, un parcours du KG ou une session."""
    from atelier.generation import parcours_bdd

    b = await req.json()
    r = await asyncio.to_thread(_call, parcours_bdd.brouillon, b.get("ecrans") or None, b.get("parcours", ""), b.get("session", ""),
                                b.get("titre", ""), b.get("plateforme", ""))
    emit({"type": "bdd_change", "cle": r["cle"]})
    return r


@app.get("/api/discovery/parcours")
def discovery_parcours():
    """Parcours du Knowledge Graph (nœuds « parcours ») et leurs écrans."""
    from atelier.discovery import connaissance

    g = _call(connaissance.construire)
    return [{"id": n.id, "libelle": n.libelle, "statut": n.statut, "source": n.source,
             "ecrans": [r.vers.split(":", 1)[1] for r in g.sortants(n.id) if r.type == "contient" and r.vers.startswith("ecran:")]}
            for n in g.noeuds.values() if n.type == "parcours"]


@app.get("/api/discovery/comparer")
def discovery_comparer(a: str, b: str):
    return _call(sessions_discovery.comparer, a, b)


@app.get("/api/discovery/navigation")
async def discovery_navigation():
    return await asyncio.to_thread(_call, sessions_discovery.navigation)


@app.get("/api/discovery/chemin")
def discovery_chemin(vers: str, depuis: str = "", plateforme: str = ""):
    return _call(sessions_discovery.chemin, vers, depuis, plateforme)


@app.get("/api/conception/regles")
async def conception_regles():
    from atelier.generation import regles_test

    return await asyncio.to_thread(lambda: {"regles": _call(regles_test.lister), "indicateurs": _call(regles_test.indicateurs),
                                            "categories": regles_test.CATEGORIES, "types_parametre": regles_test.TYPES_PARAMETRE})


@app.get("/api/conception/regles/detail")
async def conception_regle_detail(id: str):
    from atelier.generation import regles_test

    return await asyncio.to_thread(_call, regles_test.detail, id)


@app.post("/api/conception/regles")
async def conception_regle_enregistrer(req: Request):
    from atelier.generation import regles_test

    return await asyncio.to_thread(_call, regles_test.enregistrer, await req.json())


@app.post("/api/conception/regles/supprimer")
async def conception_regle_supprimer(req: Request):
    from atelier.generation import regles_test

    return _call(regles_test.supprimer, (await req.json()).get("id", ""))


@app.post("/api/conception/regles/proposer")
async def conception_regles_proposer():
    from atelier.generation import regles_test

    return await asyncio.to_thread(_call, regles_test.proposer_depuis_exigences)


@app.post("/api/conception/regles/xray")
async def conception_regle_xray(req: Request):
    """Création explicite, dans Xray, des cas limites choisis (tests Manual liés aux exigences de la règle)."""
    from atelier.generation import regles_test

    b = await req.json()
    return await asyncio.to_thread(_call, regles_test.creer_cas_xray, b.get("id", ""), b.get("cas") or [], b.get("projet", ""))


@app.get("/api/conception/organisation-xray")
def conception_organisation_xray():
    return _call(patrimoine_xray.organisation)


@app.post("/api/patrimoine/xray-definitions")
async def patrimoine_xray_definitions(req: Request):
    """Mode A : définitions des tests (type, étapes, Gherkin, dossier, préconditions) lues dans Xray."""
    b = await req.json()
    return await asyncio.to_thread(_call, patrimoine_xray.completer_depuis_xray, b.get("projet", ""), b.get("jql", ""))


@app.post("/api/patrimoine/synchroniser")
async def patrimoine_synchroniser(req: Request):
    """Sans JQL : synchronise l'application active avec sa source (Paramètres › Configuration). Avec JQL : appel
    historique (copie locale remplacée par le résultat)."""
    b = await req.json()
    if not b.get("jql"):
        r = await asyncio.to_thread(_call, patrimoine_xray.synchroniser_application, b.get("application", ""))
        emit({"type": "patrimoine_change"})
        return r
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
    from atelier.generation import rangement

    try:
        rang = {"robot": rangement.chemin_robot(m), "xray": rangement.dossier_xray(m) or "/ (racine)"}
    except Exception as e:  # noqa: BLE001
        rang = {"erreur": str(e)[:200]}
    return {"scenario": m, "gherkin": bdd.serialiser(m), "controles": bdd.controles(m), "statistiques": bdd.statistiques(m), "rangement": rang}


@app.get("/api/conception/rangement")
def conception_rangement():
    from atelier.discovery import connaissance
    from atelier.generation import rangement

    try:
        modules = sorted({n.libelle for n in connaissance.construire().noeuds.values() if n.type == "module"})
    except Exception:  # noqa: BLE001
        modules = []
    return {**rangement.regles(), "defaut": rangement.DEFAUT, "variables": rangement.VARIABLES, "modules": modules}


@app.post("/api/conception/rangement")
async def conception_rangement_maj(req: Request):
    from atelier.generation import rangement

    b = await req.json()
    return _call(rangement.maj, b.get("robot"), b.get("xray"))


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
           "module": lambda: bdd.associer_module(cle, b.get("module", "")),
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
def _filtre_app_ctx() -> dict:
    try:
        f = patrimoine_xray.filtre_application()
        if not f.get("valeurs"):
            return {}
        v = patrimoine_xray.charger_vue() or {}
        return {**f, **(v.get("filtre_application") or {})}
    except Exception:  # noqa: BLE001
        return {}


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
            "projet_id": pa.get("id", ""), "projet_xray": pa.get("xray_projet", ""), "filtre_application": _filtre_app_ctx(), "jira_url": (os.environ.get("JIRA_BASE_URL") or "").rstrip("/"), "projet_jira": pa.get("jira_projet") or pa.get("xray_projet", ""),
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


@app.get("/api/strategie/lot/{rubrique}")
def strategie_options_lot(rubrique: str):
    return _call(strategie.options_lot, rubrique)


@app.post("/api/strategie/lot")
async def strategie_lot(req: Request):
    b = await req.json()
    return await asyncio.to_thread(_call, strategie.ajouter_en_lot, b.get("rubrique", ""), b.get("valeurs") or [], b.get("communs") or {}, b.get("parts") or {})


@app.post("/api/strategie/squads")
async def strategie_squads(req: Request):
    """Squads du périmètre ; option : activer aussi leur testabilité des US (politique par espace Jira)."""
    from atelier.intelligence import testabilite_us

    b = await req.json()
    r = _call(strategie.ajouter_squads, b.get("squads") or [])
    if b.get("testabilite"):  # les squads sont déjà ajoutées : un échec ici n'est qu'un avertissement
        actives = {e["projet_jira"] for e in testabilite_us.espaces()}
        r["testabilite_activee"], r["avertissements"] = [], []
        for q in b.get("squads") or []:
            cle = str(q.get("cle", "")).upper()
            if cle in r["ajoutees"] and cle not in actives:
                try:
                    testabilite_us.enregistrer_espace({"projet_jira": cle, "nom": q.get("nom") or cle})
                    r["testabilite_activee"].append(cle)
                except Exception as e:  # noqa: BLE001
                    r["avertissements"].append(f"{cle} : testabilité non activée ({e})")
    return r


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


@app.get("/api/conception/cycle-vie")
def conception_cycle_vie_config():
    from atelier.generation import cycle_vie

    return {**_call(cycle_vie.config), "etapes": cycle_vie.ETAPES, "libelles": cycle_vie.LIBELLES,
            "etapes_n": {x["etape"]: x["tests"] for x in _call(cycle_vie.synthese)["etapes"]}}


@app.post("/api/conception/cycle-vie")
async def conception_cycle_vie_maj(req: Request):
    from atelier.generation import cycle_vie

    b = await req.json()
    return _call(cycle_vie.maj_config, b.get("statuts"), b.get("champ_candidat"), b.get("valeur_candidat"))


@app.get("/api/conception/cycle-vie/{cle}")
async def conception_cycle_vie_etat(cle: str):
    from atelier.generation import cycle_vie

    return await asyncio.to_thread(_call, cycle_vie.etat, cle)


@app.post("/api/conception/cycle-vie/{cle}")
async def conception_cycle_vie_avancer(cle: str, req: Request):
    from atelier.generation import cycle_vie

    b = await req.json()
    return await asyncio.to_thread(_call, cycle_vie.avancer, cle, b.get("vers", ""), b.get("commentaire", ""))


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


@app.get("/api/centre/plans")
async def centre_vue_plans():
    """Test Plans de l'application avec statut et indicateurs (copie locale)."""
    return await asyncio.to_thread(_call, centre.vue_plans)


@app.post("/api/centre/plans/actualiser")
async def centre_actualiser_plans():
    """Relit dans Xray les Test Plans de l'application et les Test Executions de ces plans."""
    from atelier.intelligence import patrimoine_xray

    return await asyncio.to_thread(_call, patrimoine_xray.importer_plans)


@app.get("/api/centre/plans-xray")
async def centre_plans_xray():
    """Test Plans de l'application (JQL de sa configuration), pour rattacher une campagne."""
    from atelier.intelligence import patrimoine_xray

    return await asyncio.to_thread(_call, patrimoine_xray.plans_application)


@app.post("/api/centre/campagnes/plan-xray")
async def centre_creer_plan_xray(req: Request):
    """Crée un Test Plan Xray pour une campagne (action explicite)."""
    b = await req.json()
    return await asyncio.to_thread(_call, centre.creer_plan_campagne, b.get("nom", ""), b.get("tests") or [])


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
    return await asyncio.to_thread(_call, studio.transition_script, b.get("fichier", ""), b.get("action", ""), b.get("commentaire", ""),
                                   b.get("derogation", ""))


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


@app.post("/api/studio/etape")
async def studio_etape(req: Request):
    """Exécute un seul keyword (INITIALISATION + JDD, puis l'étape) dans une suite temporaire, via la file."""
    from atelier.generation import studio_avance

    b = await req.json()
    e = await asyncio.to_thread(_call, studio_avance.preparer_etape, b.get("keyword", ""), b.get("jdd", ""), b.get("arguments") or [])
    params = {"target": e["cible"], "variables": {"PLATFORM": b.get("plateforme") or "web"}, "jdd_env": b.get("env") or ""}
    job = await asyncio.to_thread(_call, _mettre_en_file, {k: v for k, v in params.items() if v}, "High", "", f"Étape isolée · {e['keyword']}")
    return {**job, **e}


@app.get("/api/studio/qualification")
async def studio_qualification(fichier: str):
    from atelier.generation import studio_avance

    return await asyncio.to_thread(_call, studio_avance.qualification, fichier)


@app.post("/api/studio/qualifier")
async def studio_qualifier(req: Request):
    """3 runs réels de la suite approuvée, à la file : l'invariant « 3 exécutions stables » se vérifie ensuite."""
    from atelier.generation import studio_avance

    b = await req.json()
    l = _call(studio_avance.runs_qualification, b.get("fichier", ""), b.get("plateforme") or "web", b.get("env") or "")
    jobs = [await asyncio.to_thread(_call, _mettre_en_file, p, "Normal", "", f"Qualification {i}/{len(l)} · {b.get('fichier', '')}")
            for i, p in enumerate(l, 1)]
    return {"runs": [j["run_id"] for j in jobs]}


@app.get("/api/studio/productivite")
async def studio_productivite():
    from atelier.generation import studio_avance

    return await asyncio.to_thread(_call, studio_avance.productivite)


@app.get("/api/studio/modeles")
async def studio_modeles():
    from atelier.generation import studio_avance

    return _call(studio_avance.modeles)


@app.post("/api/studio/modeles")
async def studio_modele_enregistrer(req: Request):
    from atelier.generation import studio_avance

    b = await req.json()
    if b.get("supprimer"):
        return _call(studio_avance.supprimer_modele, b.get("cle", ""))
    return _call(studio_avance.enregistrer_modele, b.get("cle", ""), b.get("titre", ""), b.get("texte", ""))


@app.post("/api/studio/modeles/rendre")
async def studio_modele_rendre(req: Request):
    from atelier.generation import studio_avance

    b = await req.json()
    return {"texte": _call(studio_avance.rendre_modele, b.get("cle", ""), b.get("scenario", ""), b.get("titre", ""), b.get("plateforme") or "web")}


@app.get("/api/studio/locators/corrections")
async def studio_corrections():
    from atelier.generation import studio_avance

    return await asyncio.to_thread(_call, studio_avance.propositions_correction)


@app.post("/api/studio/locators/corriger")
async def studio_corriger(req: Request):
    """Applique une correction de locator validée par l'automaticien (éditeur : historique, revue des suites)."""
    from atelier.generation import studio_avance

    b = await req.json()
    return await asyncio.to_thread(_call, studio_avance.appliquer_correction, b.get("id", ""), b.get("valeur", ""))


@app.get("/api/studio/keywords/factorisation")
async def studio_factorisation(ia: bool = False):
    from atelier.generation import studio_avance

    return await asyncio.to_thread(_call, studio_avance.propositions_factorisation, ia)


@app.post("/api/studio/keywords/factoriser")
async def studio_factoriser(req: Request):
    from atelier.generation import studio_avance

    return await asyncio.to_thread(_call, studio_avance.appliquer_factorisation, (await req.json()).get("id", ""))


@app.post("/api/donnees/importer")
async def jdd_importer(req: Request):
    """Aperçu (ecrire=false) ou import (ecrire=true) de jeux de données CSV / JSON."""
    from atelier.execution import jdd as jdd_mod

    b = await req.json()
    return await asyncio.to_thread(_call, jdd_mod.importer, b.get("env", ""), b.get("contenu", ""), b.get("format", ""),
                                   bool(b.get("ecraser")), bool(b.get("ecrire")))


@app.get("/api/donnees/apis")
async def jdd_apis():
    from atelier.execution import jdd as jdd_mod

    return _call(lambda: {n: {k: d.get(k) for k in ("description", "methode", "environnements", "extraire")} for n, d in jdd_mod.apis().items()})


@app.post("/api/donnees/apis/tester")
async def jdd_api_tester(req: Request):
    """Appel réel d'une API de préparation déclarée (environnement autorisé uniquement)."""
    from atelier.execution import jdd as jdd_mod

    b = await req.json()
    return await asyncio.to_thread(_call, jdd_mod.tester_api, b.get("env", ""), b.get("nom", ""), b.get("params") or {})


@app.get("/api/roles")
async def roles_etat():
    from atelier.domain import roles

    return _call(roles.etat)


@app.post("/api/roles")
async def roles_definir(req: Request):
    from atelier.domain import roles

    b = await req.json()
    return _call(roles.definir, b.get("utilisateurs") or {}, bool(b.get("revue_par_un_autre", True)))


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
@app.get("/api/cerveau")
async def cerveau_vue():
    """Cerveau de l'application active : sources et fraîcheur, modules, lacunes, apprentissages."""
    from atelier.intelligence import cerveau

    return await asyncio.to_thread(_call, cerveau.vue)


@app.get("/api/cerveau/module")
async def cerveau_module(module: str):
    from atelier.intelligence import plan_test

    return await asyncio.to_thread(_call, plan_test.plan, module)


@app.post("/api/cerveau/question")
async def cerveau_question(req: Request):
    """Question posée au cerveau : réponse fondée sur ses seules connaissances (IA si configurée, sinon les faits)."""
    from atelier.intelligence import cerveau

    return await asyncio.to_thread(_call, cerveau.demander, (await req.json()).get("question", ""))


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
    # arrêt (Ctrl+C) : les requêtes en cours ont 3 s pour finir, puis sont interrompues (pas de second Ctrl+C)
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning", timeout_graceful_shutdown=3)


if __name__ == "__main__":
    main()
