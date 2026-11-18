"""Execution Center : campagnes, sélection et contrôle préalable, file d'attente, runner, preuves,
synchronisation Xray (cahier des charges « Module Execution Center »).

Ce qui est réel ici :
- une FILE D'ATTENTE à priorités (Critical > High > Normal > Low, puis ordre d'arrivée) servie par le
  runner local (une exécution Robot à la fois sur ce poste : capacité 1, déclarée honnêtement) ;
- le CONTEXTE de chaque exécution est figé à l'entrée dans la file (projet, application, version,
  environnement, plateforme, commit Git du projet, statut de revue des scripts) et conservé dans
  l'historique : changer de projet ensuite ne le modifie pas ;
- les campagnes sont stockées dans le projet (executions/campagnes.yaml) ;
- l'état Xray d'un run vient de son journal de synchronisation (outbox) : Synced / Pending / Partial / Failed ;
- un script entré en revue ne s'exécute qu'approuvé (dérogation justifiée et journalisée) ;
- planification : thread interne de l'interface web et webhook.
Non réalisé : runners distants, Device Farm avec réservation, vidéos (voir la roadmap).
"""
from __future__ import annotations

import heapq
import itertools
import json
import os
import re
import platform
import secrets
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import yaml

from atelier.domain import projet

PRIORITES = {"Critical": 0, "High": 1, "Normal": 2, "Low": 3}
TYPES_CAMPAGNE = ["TNR", "Smoke", "E2E", "Release", "API", "Autre"]
PLATEFORMES = ["web", "android", "ios", "api"]
LIBS_PLATEFORME = {"web": ["Browser", "SeleniumLibrary", "NavigateurDemo"], "android": ["AppiumLibrary"],
                   "ios": ["AppiumLibrary"], "api": ["RequestsLibrary"]}


def _maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


# =========================================================================== contexte figé
def _git(*args) -> str:
    try:
        r = subprocess.run(["git", "-C", str(projet.PROJECT_DIR), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def contexte(params: dict) -> dict:
    """Contexte initial d'une exécution, figé au moment où elle entre dans la file."""
    from atelier.discovery import carte

    app = {}
    try:
        slug = carte.app_courante()
        app = next((x for x in carte.apps() if x.get("slug") == slug), {}) if slug else {}
    except Exception:
        app = {}
    try:
        from atelier.generation import studio

        revues = {k: v["statut"] for k, v in studio.revues_scripts().items()}
    except Exception:
        revues = {}
    cible = params.get("target", "")
    return {"projet": projet.PROJECT_DIR.name, "projet_dir": str(projet.PROJECT_DIR),
            "application": app.get("nom", ""), "version_application": app.get("build", ""),
            "environnement": params.get("jdd_env", ""), "plateforme": (params.get("variables") or {}).get("PLATFORM", ""),
            "commit": _git("rev-parse", "--short", "HEAD") or "(projet hors Git)", "branche": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "revue_scripts": {f: s for f, s in revues.items() if f.startswith(cible)} if cible else revues,
            "fige_le": _maintenant()}


# =========================================================================== file d'attente
class FileExecution:
    """File à priorités ; un seul job exécuté à la fois par le runner local."""

    def __init__(self):
        self._tas: list = []
        self._ordre = itertools.count()
        self._verrou = threading.Lock()
        self.en_cours: dict | None = None
        self.executer = None  # fourni par l'adapter web : fonction(job) -> None (bloquante)
        self._thread: threading.Thread | None = None

    def ajouter(self, params: dict, priorite: str = "Normal", run_id: str = "", campagne: str = "", nom: str = "",
                retry: bool = False) -> dict:
        if priorite not in PRIORITES:
            raise ValueError(f"Priorité : {', '.join(PRIORITES)}.")
        job = {"id": run_id, "nom": nom or params.get("target", ""), "priorite": priorite, "campagne": campagne, "retry": bool(retry),
               "etat": "Queued", "entre_le": _maintenant(), "params": params, "contexte": contexte(params)}
        with self._verrou:
            heapq.heappush(self._tas, (PRIORITES[priorite], next(self._ordre), job))
        self._servir()
        return job

    def annuler(self, run_id: str) -> bool:
        with self._verrou:
            avant = len(self._tas)
            self._tas = [x for x in self._tas if x[2]["id"] != run_id]
            heapq.heapify(self._tas)
            return len(self._tas) < avant

    def attente(self) -> list[dict]:
        with self._verrou:
            return [{k: v for k, v in j.items() if k != "params"} for _, _, j in sorted(self._tas)]

    def _servir(self):
        with self._verrou:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._boucle, daemon=True)
            self._thread.start()

    def _boucle(self):
        while True:
            with self._verrou:
                if not self._tas:
                    self.en_cours = None
                    return
                _, _, job = heapq.heappop(self._tas)
                job["etat"] = "Running"
                self.en_cours = job
            try:
                if self.executer:
                    self.executer(job)
            except Exception:
                pass  # l'adapter enregistre lui-même l'erreur dans l'historique


FILE = FileExecution()


# =========================================================================== retry historisé
def politique_revue() -> str:
    """ATELIER_REVUE_EXECUTION : « bloquante » (défaut) ou « avertissement »."""
    return "avertissement" if os.environ.get("ATELIER_REVUE_EXECUTION", "").strip().lower() == "avertissement" else "bloquante"


def controle_revue(target: str, dry_run: bool = False, derogation: str = "") -> dict:
    """Validation humaine avant exécution : un script entré en revue (généré par l'atelier, ou modifié depuis
    son approbation) ne s'exécute qu'à l'état Approved / Published. Le dry-run reste libre. Une dérogation
    exige une justification (10 caractères au moins) et est journalisée. Le patrimoine existant, jamais
    entré en revue, n'est pas bloqué."""
    from atelier.generation import studio

    cible = str(target or "").strip().rstrip("/")
    revues = studio.revues_scripts()
    concernes = {f: x for f, x in revues.items() if cible and (f == cible or f.startswith(cible + "/"))}
    non_valides = sorted(f for f, x in concernes.items() if x.get("en_workflow") and x["statut"] not in ("Approved", "Published"))
    res = {"politique": politique_revue(), "non_valides": non_valides, "derogation": False}
    if not non_valides or dry_run:
        return res
    detail = ", ".join(f"{f} ({concernes[f]['statut']})" for f in non_valides[:5])
    if politique_revue() == "avertissement":
        _journal_derogation(target, non_valides, "politique « avertissement »")
        return res
    if len(derogation.strip()) < 10:
        raise PermissionError(f"Revue requise : script(s) non approuvé(s) : {detail}. Approuver dans Automation Studio › Review, "
                              "ou lancer avec une dérogation justifiée.")
    _journal_derogation(target, non_valides, derogation.strip())
    return {**res, "derogation": True}


def _journal_derogation(target: str, fichiers: list[str], justification: str):
    from atelier.intelligence.strategie import _auteur, _maintenant

    f = projet.PROJECT_DIR / "executions" / "derogations_revue.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": _maintenant(), "auteur": _auteur(), "cible": target, "fichiers": fichiers,
                             "justification": justification}, ensure_ascii=False) + "\n")


def executer_avec_retry(run_robot, params: dict, retry: bool = False) -> dict:
    """Un run, puis (si retry et échecs) une seconde tentative des seuls tests en échec.
    Les preuves de chaque tentative sont conservées (tentative-1/, tentative-2/), les résultats sont
    fusionnés par « rebot --merge » (Robot y note la ré-exécution) et les tests passés au second essai
    sont déclarés instables : un premier échec n'est jamais effacé."""
    from robot.api import ExecutionResult

    from atelier.execution.robot import parse_robot_output

    params = dict(params)
    source = params.pop("source_echecs", "")
    if source:  # rejeu des échecs d'un autre run : son output.xml est copié, son dossier n'est jamais réécrit
        out = projet.safe_path(params["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        prec = projet.safe_path(source) / "output.xml"
        if not prec.exists():
            raise FileNotFoundError(f"Aucun résultat à rejouer dans {source}.")
        shutil.copy(prec, out / "output.xml")
    premier = run_robot(**params)
    r1 = premier.get("resultat") or {}
    if not retry or not r1.get("echecs") or premier.get("arrete"):
        return premier
    out = projet.safe_path(params["output_dir"])
    t1, t2 = out / "tentative-1", out / "tentative-2"
    t1.mkdir(exist_ok=True)
    for n in ("output.xml", "log.html", "report.html"):
        if (out / n).exists():
            shutil.copy(out / n, t1 / n)
    if (out / "captures").exists():
        shutil.copytree(out / "captures", t1 / "captures", dirs_exist_ok=True)
    exec_creee = (premier.get("xray") or {}).get("execution")
    second = run_robot(**{**params, "relancer_echecs": True, **({"xray_ticket": exec_creee} if exec_creee else {})})
    t2.mkdir(exist_ok=True)
    if (out / "output.xml").exists():
        shutil.copy(out / "output.xml", t2 / "output.xml")
    subprocess.run([sys.executable, "-m", "robot.rebot", "--merge", "--outputdir", str(out), "--output", "output.xml",
                    "--log", "log.html", "--report", "report.html", str(t1 / "output.xml"), str(t2 / "output.xml")],
                   capture_output=True, text=True, errors="replace", timeout=300)

    def statut(f) -> dict:
        try:
            return {t.longname: t.status for t in ExecutionResult(str(f)).suite.all_tests} if f.exists() else {}
        except Exception:  # noqa: BLE001 - tentative interrompue : output.xml illisible
            return {}

    s1, s2 = statut(t1 / "output.xml"), statut(t2 / "output.xml")
    final = {**second, "resultat": parse_robot_output((out / "output.xml").relative_to(projet.PROJECT_DIR).as_posix())}
    final["tentatives"] = [{"n": 1, "resultat": r1, "preuves": "tentative-1/"}, {"n": 2, "resultat": second.get("resultat"), "preuves": "tentative-2/"}]
    final["instables"] = sorted(n.split(".")[-1] for n, st in s2.items() if st == "PASS" and s1.get(n) == "FAIL")
    return final


# =========================================================================== runner local et devices
def runner_local() -> dict:
    """Le seul runner réel : ce poste. Plateformes déduites des outils réellement présents."""
    from importlib import metadata

    def version(p):
        try:
            return metadata.version(p)
        except Exception:
            return ""

    libs = {n: version(p) for n, p in [("Robot Framework", "robotframework"), ("AppiumLibrary", "robotframework-appiumlibrary"),
                                        ("Browser", "robotframework-browser"), ("RequestsLibrary", "robotframework-requests"),
                                        ("SeleniumLibrary", "robotframework-seleniumlibrary"), ("Playwright", "playwright")]}
    navigateur = Path(__import__("os").environ.get("WEB_BROWSER_EXECUTABLE", "") or "/opt/pw-browsers/chromium").exists() or bool(libs["Browser"])
    plats = {"web": bool(libs["Playwright"] or libs["Browser"] or libs["SeleniumLibrary"]) and navigateur,
             "android": bool(libs["AppiumLibrary"] and shutil.which("adb")),
             "ios": bool(libs["AppiumLibrary"] and sys.platform == "darwin" and shutil.which("xcrun")),
             "api": bool(libs["RequestsLibrary"])}
    occupe = FILE.en_cours is not None
    return {"id": "runner-local", "nom": platform.node() or "poste local", "type": "Generic Robot Runner",
            "os": f"{platform.system()} {platform.release()}", "python": platform.python_version(), "capacite": 1,
            "charge": 1 if occupe else 0, "etat": "Busy" if occupe else "Idle", "plateformes": plats, "bibliotheques": libs,
            "derniere_activite": (FILE.en_cours or {}).get("entre_le", "")}


# =========================================================================== campagnes
def _fichier_campagnes() -> Path:
    return projet.PROJECT_DIR / "executions" / "campagnes.yaml"


def campagnes() -> list[dict]:
    f = _fichier_campagnes()
    l = (yaml.safe_load(f.read_text("utf-8")) or []) if f.exists() else []
    from atelier.execution import historique

    runs = historique.lister(200)
    for c in l:
        mes = [r for r in runs if r.get("campagne") == c["id"]]
        reels = [r for r in mes if r.get("passes") is not None and not r.get("dry_run")]
        p, e = sum(r["passes"] for r in reels), sum(r["echecs"] for r in reels)
        c["derniere_execution"] = mes[0]["debut"] if mes else ""
        c["dernier_statut"] = mes[0]["statut"] if mes else ""
        c["taux_reussite"] = round(100 * p / (p + e), 1) if p + e else None
        c["runs"] = [r["id"] for r in mes]
        c["executions"] = list(dict.fromkeys(r["xray"] for r in mes if r.get("xray")))  # Test Executions Xray, plus récente d'abord
    return l


def _ecrire_campagnes(l: list[dict]):
    from atelier.intelligence.strategie import _ecrire_atomique

    propres = [{k: v for k, v in c.items() if k not in ("derniere_execution", "dernier_statut", "taux_reussite", "runs", "executions")} for c in l]
    _ecrire_atomique(_fichier_campagnes(), yaml.safe_dump(propres, allow_unicode=True, sort_keys=False))


def enregistrer_campagne(c: dict) -> list[dict]:
    if not (c.get("nom") or "").strip():
        raise ValueError("Nom de campagne obligatoire.")
    if c.get("type", "TNR") not in TYPES_CAMPAGNE:
        raise ValueError(f"Type : {', '.join(TYPES_CAMPAGNE)}.")
    plats = c.get("plateformes") or []
    if not plats or any(p not in PLATEFORMES for p in plats):
        raise ValueError(f"Plateformes : au moins une parmi {', '.join(PLATEFORMES)}.")
    if c.get("priorite", "Normal") not in PRIORITES:
        raise ValueError(f"Priorité : {', '.join(PRIORITES)}.")
    projet.safe_path(c.get("cible") or "tests")  # cible dans le projet uniquement
    propre = {"id": c.get("id") or f"CAMP-{secrets.token_hex(3).upper()}", "nom": c["nom"].strip(), "description": c.get("description", ""),
              "type": c.get("type", "TNR"), "plateformes": plats, "environnement": c.get("environnement", ""),
              "cible": c.get("cible") or "tests", "tests": [str(t) for t in c.get("tests") or []],
              "tags": [str(t) for t in c.get("tags") or []], "retry": bool(c.get("retry")), "priorite": c.get("priorite", "Normal"),
              "xray_ticket": _ticket_xray(c), "plan_xray": (c.get("plan_xray") or "").strip().upper(),
              "execution_xray": (c.get("execution_xray") or "").strip().upper() if c.get("mode_execution") == "reutiliser" else "",
              "mode_execution": "reutiliser" if c.get("mode_execution") == "reutiliser" else "nouvelle", "statut": c.get("statut", "Active"),
              "exclus": [str(t) for t in c.get("exclus") or []], "planning": _planning(c.get("planning"))}
    l = campagnes()
    i = next((k for k, x in enumerate(l) if x["id"] == propre["id"]), None)
    if i is None:
        l.append(propre)
    else:
        l[i] = propre
    _ecrire_campagnes(l)
    return campagnes()


CLE_JIRA = re.compile(r"[A-Z][A-Z0-9_]+-\d+")


def _ticket_xray(c: dict) -> str:
    """Ticket passé au run : l'exécution à réutiliser, sinon le Test Plan (une nouvelle Test Execution par run,
    rattachée au plan), sinon l'ancien champ libre."""
    plan, exe = (c.get("plan_xray") or "").strip().upper(), (c.get("execution_xray") or "").strip().upper()
    for k in (plan, exe if c.get("mode_execution") == "reutiliser" else ""):
        if k and not CLE_JIRA.fullmatch(k):
            raise ValueError(f"Clé Jira invalide : {k}")
    if c.get("mode_execution") == "reutiliser":
        if not exe:
            raise ValueError("Test Execution à réutiliser : clé obligatoire.")
        return exe
    return plan or (c.get("xray_ticket") or "").strip()


def creer_plan_campagne(nom: str, tests: list[str], xray=None) -> dict:
    """Crée dans Xray un Test Plan pour la campagne (résumé = nom de la campagne, tests choisis s'ils existent dans Xray).
    Action explicite de l'utilisateur ; renvoie la clé à enregistrer dans la campagne."""
    from atelier.domain import projets
    from atelier.integrations.xray import XrayClient

    if not (nom or "").strip():
        raise ValueError("Nom de campagne obligatoire pour nommer le Test Plan.")
    cle = projets.cle_xray()
    if not cle:
        raise ValueError("Projet Xray inconnu (Paramètres › Projets).")
    x = xray or XrayClient()
    ids = x.test_ids([t for t in tests or [] if CLE_JIRA.fullmatch(t)]) if tests else {}
    _, plan = x.create_plan(cle, f"Campagne – {nom.strip()}", list(ids.values()))
    return {"cle": plan, "tests": sorted(ids), "absents": sorted(set(tests or []) - set(ids))}


TYPES_PLANNING = ("aucun", "quotidien", "hebdomadaire", "intervalle")


def _planning(pl: dict | None) -> dict:
    """Planification d'une campagne : quotidien (heure), hebdomadaire (jours 0=lundi … 6 + heure), intervalle (minutes ≥ 15)."""
    pl = dict(pl or {})
    t = pl.get("type") or "aucun"
    if t not in TYPES_PLANNING:
        raise ValueError(f"Planification : {', '.join(TYPES_PLANNING)}.")
    if t in ("quotidien", "hebdomadaire") and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", pl.get("heure") or ""):
        raise ValueError("Heure de planification au format HH:MM.")
    if t == "hebdomadaire" and not [j for j in pl.get("jours") or [] if 0 <= int(j) <= 6]:
        raise ValueError("Au moins un jour (0 = lundi … 6 = dimanche).")
    if t == "intervalle" and int(pl.get("minutes") or 0) < 15:
        raise ValueError("Intervalle minimal : 15 minutes.")
    return {"type": t, "heure": pl.get("heure", ""), "jours": sorted({int(j) for j in pl.get("jours") or []}), "minutes": int(pl.get("minutes") or 0),
            "actif": bool(pl.get("actif", t != "aucun"))}


def _etat_planning() -> dict:
    f = projet.PROJECT_DIR / "executions" / "planning_etat.json"
    return json.loads(f.read_text("utf-8")) if f.exists() else {}


def campagnes_dues(maintenant: datetime | None = None) -> list[dict]:
    """Campagnes dont l'échéance est atteinte et pas encore déclenchée (au plus un déclenchement par échéance)."""
    from atelier.intelligence.strategie import _ecrire_atomique

    maintenant = maintenant or datetime.now()
    etat = _etat_planning()
    dues = []
    for c in campagnes():
        pl = c.get("planning") or {}
        if c["statut"] != "Active" or not pl.get("actif") or pl.get("type") in (None, "aucun"):
            continue
        dernier = datetime.fromisoformat(etat[c["id"]]) if c["id"] in etat else None
        if pl["type"] == "intervalle":
            du = dernier is None or (maintenant - dernier).total_seconds() >= pl["minutes"] * 60
        else:
            h, m = map(int, pl["heure"].split(":"))
            echeance = maintenant.replace(hour=h, minute=m, second=0, microsecond=0)
            jour_ok = pl["type"] == "quotidien" or maintenant.weekday() in pl["jours"]
            du = jour_ok and maintenant >= echeance and (dernier is None or dernier < echeance)
        if du:
            etat[c["id"]] = maintenant.isoformat(timespec="seconds")
            dues.append(c)
    if dues:
        _ecrire_atomique(projet.PROJECT_DIR / "executions" / "planning_etat.json", json.dumps(etat, indent=1))
    return dues


def campagne(cid: str) -> dict:
    c = next((x for x in campagnes() if x["id"] == cid), None)
    if not c:
        raise KeyError(f"Campagne inconnue : {cid}")
    return c


def params_campagne(c: dict, plateforme: str, dry_run: bool = False) -> dict:
    """Paramètres de run_robot pour une plateforme de la campagne (tests choisis = tags clés Xray)."""
    p = {"target": c["cible"], "variables": {"PLATFORM": plateforme}, "dry_run": dry_run,
         "include_tags": sorted(set(c["tests"]) | set(c["tags"])) or None, "retry": c["retry"],
         "exclude_tags": c.get("exclus") or None}  # exclusion temporaire : le test reste au référentiel
    if c.get("environnement"):
        p["jdd_env"] = c["environnement"]
    if c.get("xray_ticket"):
        p["xray_ticket"] = c["xray_ticket"]
    return {k: v for k, v in p.items() if v not in (None, "", [])}


# =========================================================================== référentiel et contrôle préalable
def referentiel() -> list[dict]:
    """Tests automatisés disponibles : dépôt Robot + clés Xray + dernier résultat + statut de revue du script."""
    from atelier.execution.depot_robot import lire_depot
    from atelier.execution.robot import derniers_resultats
    from atelier.intelligence import patrimoine_xray

    inv = lire_depot()
    res = derniers_resultats()
    pat = {t["cle"]: t for t in (patrimoine_xray.charger() or {"tests": []})["tests"]}
    try:
        from atelier.generation import studio

        revues = studio.revues_scripts()
    except Exception:
        revues = {}
    out = []
    for tid, t in inv["tests"].items():
        r = res.get(tid) or {}
        cle = (t.get("cles_xray") or [""])[0]
        out.append({"id": tid, "nom": t["nom"], "fichier": t["fichier"], "cle_xray": cle, "tags": t["tags"],
                    "plateformes": t.get("plateformes", []), "jdd": t.get("jdd", []),
                    "dernier_resultat": r.get("statut", ""), "derniere_fin": r.get("fin", ""),
                    "criticite": (pat.get(cle) or {}).get("criticite", ""), "module": (pat.get(cle) or {}).get("module", ""),
                    "plans": (pat.get(cle) or {}).get("plans", []), "executions": (pat.get(cle) or {}).get("executions", []),
                    "statut_xray": ((pat.get(cle) or {}).get("statut_xray") or {}).get("statut", ""),
                    "execution_xray": ((pat.get(cle) or {}).get("statut_xray") or {}).get("execution", ""),
                    "revue": (revues.get(t["fichier"]) or {}).get("statut", "Generated"),
                    "en_workflow": bool((revues.get(t["fichier"]) or {}).get("en_workflow"))})
    return out


ECHECS_XRAY = ("FAIL", "ABORT", "BLOCK")


def executions_xray() -> dict:
    """Test Executions Xray de la copie locale, rapprochées du dépôt : tests automatisés (un script Robot porte la clé)
    ou non, échecs ; pour sélectionner, rejouer les échecs ou publier dans une exécution existante."""
    from atelier.execution.depot_robot import lire_depot
    from atelier.intelligence import patrimoine_xray

    pat = patrimoine_xray.charger() or {}
    automatises = {c for t in lire_depot()["tests"].values() for c in t.get("cles_xray") or []}
    out = []
    for e in pat.get("executions") or []:
        tests = e.get("tests") or []
        runs = e.get("runs") or {}
        out.append({"cle": e["cle"], "resume": e.get("resume", ""), "statut": e.get("statut", ""), "cree": e.get("cree", ""),
                    "environnements": e.get("environnements") or [], "tests": len(tests), "tests_total": e.get("tests_total") or len(tests),
                    "automatises": sorted(k for k in tests if k in automatises), "non_automatises": sorted(k for k in tests if k not in automatises),
                    "echecs": sorted(k for k, r in runs.items() if any(x in (r.get("statut") or "").upper() for x in ECHECS_XRAY)),
                    "statuts": {k: r.get("statut", "") for k, r in runs.items()}})
    return {"executions": out, "import": pat.get("executions_xray") or {}}


def verifier(ids: list[str], plateforme: str, environnement: str = "") -> dict:
    """Contrôle préalable par test : script, revue, plateforme, framework, données, environnement, runner."""
    from atelier.execution import jdd

    ref = {t["id"]: t for t in referentiel()}
    run = runner_local()
    env_ok, env_detail = True, "aucun environnement de stratégie lié"
    try:
        from atelier.intelligence import strategie

        s = strategie.charger()
        env = next((e for e in (s or {"rubriques": {}}).get("rubriques", {}).get("environnements", []) if e.get("jdd_env") == environnement), None)
        if env and env.get("derniere_verification"):
            env_ok = env["derniere_verification"]["resultat"] != "indisponible"
            env_detail = f"{env['nom']} : {env['derniere_verification']['resultat']}"
    except Exception:
        pass
    out = []
    for i in ids:
        t = ref.get(i)
        if not t:
            out.append({"id": i, "executable": False, "controles": [{"code": "script", "ok": False, "bloquant": True, "message": "Script introuvable dans le dépôt."}]})
            continue
        c = []
        add = lambda code, ok, msg, bloquant=True: c.append({"code": code, "ok": ok, "bloquant": bloquant, "message": msg})  # noqa: E731
        add("script", True, t["fichier"])
        add("revue", t["revue"] in ("Approved", "Published") or not t.get("en_workflow"),
            f"Revue du script : {t['revue']}" if t.get("en_workflow") else "Patrimoine existant (hors workflow de revue)",
            bloquant=politique_revue() == "bloquante")
        add("plateforme", not t["plateformes"] or plateforme in t["plateformes"],
            f"Plateformes du test : {', '.join(t['plateformes']) or 'non déterminées'}")
        add("framework", run["plateformes"].get(plateforme, False), f"Runner local {'compatible' if run['plateformes'].get(plateforme) else 'incompatible'} avec {plateforme}")
        if t["jdd"]:
            if not environnement:
                add("donnees", False, "Jeux de données requis : choisir un environnement.")
            else:
                try:
                    r = jdd.verifier(environnement, t["jdd"])
                    bloques = r.get("bloques") or []
                    add("donnees", not bloques, "Données disponibles" if not bloques else "; ".join(b.get("message", "") for b in bloques))
                except Exception as e:  # noqa: BLE001
                    add("donnees", False, str(e)[:200])
        add("environnement", env_ok, env_detail, bloquant=False)
        out.append({"id": i, "nom": t["nom"], "cle_xray": t["cle_xray"], "controles": c,
                    "executable": all(x["ok"] or not x["bloquant"] for x in c)})
    return {"tests": out, "executables": sum(t["executable"] for t in out), "bloques": sum(not t["executable"] for t in out)}


# =========================================================================== preuves, Xray, comparaison
def preuves(run_id: str) -> dict:
    from atelier.execution import historique

    d = historique.dossier(run_id)
    if not d.exists():
        raise KeyError(f"Run inconnu : {run_id}")
    fichiers = []
    for f in sorted(d.rglob("*")):
        if f.is_file() and not f.name.endswith((".tmp", ".verrou")):
            ext = f.suffix.lower()
            fichiers.append({"chemin": f.relative_to(projet.PROJECT_DIR).as_posix(), "nom": f.name, "taille": f.stat().st_size,
                             "type": "capture" if ext in (".png", ".jpg") else "rapport" if ext in (".html", ".xml") else "journal" if ext in (".jsonl", ".log", ".txt") else "donnée"})
    return {"run": run_id, "fichiers": fichiers, "taille_totale": sum(f["taille"] for f in fichiers)}


def etat_xray(run_id: str) -> dict:
    from atelier.execution import historique
    from atelier.execution.journal_xray import OUTBOX, Journal

    d = historique.dossier(run_id)
    journaux = [p.parent for p in d.rglob(OUTBOX)] if d.exists() else []
    if not journaux:
        return {"run": run_id, "statut": "Non configuré", "evenements": 0, "restants": 0}
    tot = rest = 0
    abandons: list[dict] = []
    for j in journaux:
        jj = Journal(j)
        tot += len(jj.evenements())
        rest += len(jj.restants())
        abandons += [{"cle": c, "detail": d.get("detail", "")} for c, d in jj.envoyes().items() if d.get("statut") == "ignore"]
    statut = ("Failed" if abandons and len(abandons) + rest >= tot else "Partial") if abandons else \
        "Synced" if rest == 0 else "Pending" if rest == tot else "Partial"
    return {"run": run_id, "statut": statut, "evenements": tot, "restants": rest, "abandonnes": len(abandons),
            "erreurs_definitives": [a["detail"] for a in abandons][:5],
            "journaux": [j.relative_to(projet.PROJECT_DIR).as_posix() for j in journaux]}


def comparer(a: str, b: str) -> dict:
    """Deux exécutions : statut et durée de chaque test, tests apparus / disparus, changements de statut."""
    from atelier.execution import historique

    ta = {t["nom"]: t for t in historique.detail(a).get("tests", [])}
    tb = {t["nom"]: t for t in historique.detail(b).get("tests", [])}
    lignes = [{"test": n, "a": (ta.get(n) or {}).get("statut", "—"), "b": (tb.get(n) or {}).get("statut", "—"),
               "duree_a": (ta.get(n) or {}).get("duree_s"), "duree_b": (tb.get(n) or {}).get("duree_s"),
               "change": (ta.get(n) or {}).get("statut") != (tb.get(n) or {}).get("statut")} for n in sorted(set(ta) | set(tb))]
    return {"a": a, "b": b, "tests": lignes, "changements": sum(x["change"] for x in lignes)}


def vue_ensemble() -> dict:
    from atelier.execution import historique

    runs = historique.lister(200)
    reels = [r for r in runs if r.get("passes") is not None and not r.get("dry_run")]
    p, e = sum(r["passes"] for r in reels), sum(r["echecs"] for r in reels)
    durees = [(datetime.fromisoformat(r["fin"]) - datetime.fromisoformat(r["debut"])).total_seconds() for r in reels if r.get("debut") and r.get("fin")]
    try:
        from atelier.intelligence.strategie import mesures

        instables = mesures()["taux_instables"]
    except Exception:
        instables = {"valeur": None, "detail": ""}
    par = lambda k: {v: sum(1 for r in runs if (r.get(k) or "—") == v) for v in {r.get(k) or "—" for r in runs}}  # noqa: E731
    return {"kpi": {"executions": len(runs), "en_cours": sum(r["statut"] == "en cours" for r in runs) if not FILE.en_cours else 1,
                    "en_file": len(FILE.attente()), "passes": p, "echecs": e, "taux_reussite": round(100 * p / (p + e), 1) if p + e else None,
                    "duree_moyenne_s": round(sum(durees) / len(durees), 1) if durees else None, "instables": instables,
                    "runners_actifs": 1},
            "par_plateforme": par("plateforme"), "par_statut": par("statut"),
            "tendance": [{"id": r["id"], "debut": r["debut"], "passes": r["passes"], "echecs": r["echecs"]} for r in reversed(reels[:20])],
            "recents": runs[:10], "file": FILE.attente(), "en_cours": {k: v for k, v in (FILE.en_cours or {}).items() if k != "params"} or None}



def _classe_xray(statut: str) -> str:
    s = (statut or "").upper()
    if "PASS" in s:
        return "reussi"
    if any(x in s for x in ("FAIL", "ABORT", "BLOCK")):
        return "echec"
    if not s or s.replace(" ", "") in ("TODO", "EXECUTING"):
        return "non_execute"
    return "autre"


def vue_xray(limite: int = 20, depuis: str = "", jusqu: str = "") -> dict:
    """Indicateurs des Test Executions Xray (copie locale : import des définitions ou « Actualiser depuis Xray »),
    limités aux tests de l'application sélectionnée : statuts des test runs, taux de réussite, dernier statut de
    chaque test, tendance par exécution, tests automatisés ou non. Rien n'est estimé."""
    from atelier.execution.depot_robot import lire_depot
    from atelier.intelligence import patrimoine_xray

    from atelier.discovery import carte
    from atelier.intelligence import source_tests

    pat = patrimoine_xray.charger() or {}
    vue = patrimoine_xray.charger_vue() or {"tests": []}
    tests_app = {t["cle"] for t in vue.get("tests") or []}
    slug = carte.app_courante() if carte.app_courante() else ""
    par_jql = bool(slug) and not source_tests.source().get("executions_deduite")  # JQL des exécutions de l'application
    filtre = bool((vue.get("filtre_application") or {}).get("valeurs") or (vue.get("filtre_application") or {}).get("champ"))
    automatises = {c for t in lire_depot()["tests"].values() for c in t.get("cles_xray") or []}
    execs, par_statut, dernier = [], {}, {}
    for e in sorted(pat.get("executions") or [], key=lambda x: x.get("cree") or "", reverse=True):  # du plus récent au plus ancien
        jour = (e.get("cree") or "")[:10]
        if (depuis and (not jour or jour < depuis)) or (jusqu and (not jour or jour > jusqu)):
            continue
        if par_jql and slug not in (e.get("applications") or []):
            continue
        runs = {k: r for k, r in (e.get("runs") or {}).items() if not filtre or k in tests_app}
        if filtre and not par_jql and not runs and not any(k in tests_app for k in e.get("tests") or []):
            continue
        n = {"reussi": 0, "echec": 0, "non_execute": 0, "autre": 0}
        for k, r in runs.items():
            c = _classe_xray(r.get("statut"))
            n[c] += 1
            par_statut[r.get("statut") or "—"] = par_statut.get(r.get("statut") or "—", 0) + 1
            if k not in dernier and c != "non_execute":
                dernier[k] = c
        executes = n["reussi"] + n["echec"]
        execs.append({"cle": e["cle"], "resume": e.get("resume", ""), "cree": e.get("cree", ""), "environnements": e.get("environnements") or [],
                      "statut": e.get("statut", ""), "tests": len(runs), **n, "taux": round(100 * n["reussi"] / executes, 1) if executes else None,
                      "automatises": sum(1 for k in runs if k in automatises), "incomplete": bool(e.get("incomplete")),
                      "tests_total": e.get("tests_total") or len(runs)})
    liens = runs_par_execution()
    plans_connus = {p["cle"]: p for p in (pat.get("plans_xray") or {}).get("plans") or []}
    plans_par_exe: dict = {}
    for p in plans_connus.values():
        for k in p.get("executions") or []:
            plans_par_exe.setdefault(k, []).append(p["cle"])
    brut = {e["cle"]: e for e in pat.get("executions") or []}
    for x in execs:
        lien, e = liens.get(x["cle"], {}), brut.get(x["cle"], {})
        x.update({k: lien.get(k) for k in ("campagne", "campagne_nom")}, runs_atelier=len(lien.get("runs") or []))
        # Test Plans : lus dans Xray (TestExecution.testPlans), sinon déduits des plans lus, sinon du run de l'atelier
        cles = [p["cle"] for p in e.get("plans") or []] or plans_par_exe.get(x["cle"]) or ([lien["plan"]] if lien.get("plan") else [])
        titres = {p["cle"]: p.get("resume") for p in e.get("plans") or []}
        x["plans"] = [{"cle": k, "resume": titres.get(k) or (plans_connus.get(k) or {}).get("resume") or ""} for k in dict.fromkeys(cles)]
        x["plan"] = x["plans"][0]["cle"] if x["plans"] else ""
        x["bugs_ouverts"] = [b["cle"] for b in e.get("bugs") or [] if not b.get("ferme")]
        x["bugs_fermes"] = [b["cle"] for b in e.get("bugs") or [] if b.get("ferme")]
        fins = [r.get("fin") for r in (e.get("runs") or {}).values() if r.get("fin")]
        x["assigne"] = e.get("assigne") or ""
        x["fin"] = max(fins) if fins else (e.get("resolu") or "")
    tot = {k: sum(x[k] for x in execs) for k in ("reussi", "echec", "non_execute")}
    executes = tot["reussi"] + tot["echec"]
    imp = pat.get("executions_xray") or {}
    bugs = {"ouverts": sorted({k for x in execs for k in x["bugs_ouverts"]}), "fermes": sorted({k for x in execs for k in x["bugs_fermes"]})}
    return {"bugs": bugs, "bugs_lus": "TestRun.defects" not in (imp.get("absents") or []), "avert_bugs": imp.get("bugs") or "",
            "filtre_executions": "jql" if par_jql else "tests", "import": {"date": imp.get("date"), "nombre": imp.get("nombre"), "erreur": imp.get("erreur"), "absents": imp.get("absents") or [],
                       "periode": imp.get("periode") or {}}, "periode": {"depuis": depuis, "jusqu": jusqu},
            "incompletes": [x["cle"] for x in execs if x["incomplete"]],
            "kpi": {"executions": len(execs), "runs": sum(x["tests"] for x in execs), **tot,
                    "taux_reussite": round(100 * tot["reussi"] / executes, 1) if executes else None,
                    "tests_en_echec": sum(1 for v in dernier.values() if v == "echec"), "tests_reussis": sum(1 for v in dernier.values() if v == "reussi"),
                    "tests_jamais_executes": len(tests_app - set(dernier)) if filtre else None,
                    "part_automatisee": round(100 * sum(x["automatises"] for x in execs) / max(1, sum(x["tests"] for x in execs)), 1) if execs else None},
            "par_statut": dict(sorted(par_statut.items(), key=lambda kv: -kv[1])),
            "tendance": [{"cle": x["cle"], "reussi": x["reussi"], "echec": x["echec"], "non_execute": x["non_execute"]} for x in reversed(execs[:limite])],
            "recentes": execs}


STATUTS_FERMES = re.compile(r"done|termin|closed|ferm|cl[oô]tur|annul|cancel|abandon|rejet|reject", re.I)


def plan_ferme(p: dict) -> bool:
    """Plan fermé : catégorie de statut Jira « done » lue à l'import ; à défaut (copie locale plus ancienne),
    nom du statut (Terminé, Clôturé, Annulé, Closed…)."""
    from atelier.domain import statuts

    regle = statuts.ferme("plan", p.get("statut") or "")  # mapping du projet (Paramètres › Statuts des tickets) : il prime
    if regle is not None:
        return regle
    if p.get("ferme") is not None:
        return bool(p["ferme"])
    return bool(STATUTS_FERMES.search(p.get("statut") or ""))


def vue_plans() -> dict:
    """Test Plans de l'application (copie locale « plans_xray ») : statut Jira, campagne liée, et pour chaque plan le
    dernier statut de chacun de ses tests dans ses Test Executions (la plus récente qui le contient), d'où :
    réussis / en échec / non exécutés, taux de réussite (sur les tests exécutés) et avancement (tests exécutés / tests
    du plan). Exécutions du plan : TestPlan.testExecutions si Xray l'expose, sinon celles des runs de l'atelier."""
    from atelier.discovery import carte
    from atelier.intelligence import patrimoine_xray

    pat = patrimoine_xray.charger() or {}
    px = pat.get("plans_xray") or {}
    slug = carte.app_courante() if carte.app_courante() else ""
    imp = {k: px.get(k) for k in ("date", "jql", "absents", "application")}
    if px and px.get("application") != slug:  # lus pour une autre application : à relire
        px = {}
    execs = {e["cle"]: e for e in pat.get("executions") or []}
    liens = runs_par_execution()
    via_runs: dict = {}
    for k, v in liens.items():
        if v.get("plan"):
            via_runs.setdefault(v["plan"], []).append(k)
    noms = {c.get("plan_xray"): c["nom"] for c in campagnes() if c.get("plan_xray")}
    plans, tot = [], {"reussi": 0, "echec": 0, "non_execute": 0, "tests": 0}
    for p in px.get("plans") or []:
        cles_exe = p.get("executions") if p.get("executions") is not None else via_runs.get(p["cle"], [])
        es = sorted([execs[k] for k in cles_exe if k in execs], key=lambda e: e.get("cree") or "", reverse=True)
        tests = list(dict.fromkeys(p.get("tests") or []))
        dernier = {}
        for t in tests:
            st = next(((e["runs"][t].get("statut") or "") for e in es if t in (e.get("runs") or {}) and _classe_xray(e["runs"][t].get("statut")) != "non_execute"), "")
            dernier[t] = st
        n = {"reussi": 0, "echec": 0, "non_execute": 0, "autre": 0}
        for st in dernier.values():
            n[_classe_xray(st) if st else "non_execute"] += 1
        executes = n["reussi"] + n["echec"]
        for k in ("reussi", "echec", "non_execute"):
            tot[k] += n[k]
        tot["tests"] += len(tests)
        bugs_plan = {b["cle"]: b for e in es for b in e.get("bugs") or []}
        plans.append({"bugs_ouverts": sorted(k for k, b in bugs_plan.items() if not b.get("ferme")),
                      "bugs_fermes": sorted(k for k, b in bugs_plan.items() if b.get("ferme")),
                      "cle": p["cle"], "resume": p.get("resume", ""), "statut": p.get("statut", ""), "ferme": plan_ferme(p),
                      "cree": p.get("cree", ""),
                      "campagne": noms.get(p["cle"], ""), "tests": len(tests), "tests_total": p.get("tests_total") or len(tests),
                      "executions": [e["cle"] for e in es], "executions_inconnues": len([k for k in cles_exe if k not in execs]),
                      "source_executions": "xray" if p.get("executions") is not None else "runs de l'atelier",
                      "derniere_execution": (es[0].get("cree") or "")[:10] if es else "", **{k: n[k] for k in ("reussi", "echec", "non_execute")},
                      "taux_reussite": round(100 * n["reussi"] / executes, 1) if executes else None,
                      "avancement": round(100 * executes / len(tests), 1) if tests else None, "statuts_tests": dernier})
    executes = tot["reussi"] + tot["echec"]
    return {"import": imp, "plans": plans,
            "kpi": {"plans": len(plans), "plans_ouverts": sum(1 for p in plans if not p["ferme"]),
                    "tests": tot["tests"], "reussi": tot["reussi"], "echec": tot["echec"], "non_execute": tot["non_execute"],
                    "taux_reussite": round(100 * tot["reussi"] / executes, 1) if executes else None,
                    "avancement": round(100 * executes / tot["tests"], 1) if tot["tests"] else None}}


def runs_par_execution(limite: int = 500) -> dict:
    """Lien Exécution de l'atelier = Test Execution Xray : {clé: {runs, campagne, campagne_nom, plan}} à partir des runs
    Robot qui y ont écrit (un run = un lancement ; plusieurs runs peuvent alimenter la même exécution : relance des
    échecs, nouvelle tentative)."""
    from atelier.execution import historique

    noms = {}
    try:
        f = _fichier_campagnes()
        noms = {c["id"]: c["nom"] for c in (yaml.safe_load(f.read_text("utf-8")) or [])} if f.exists() else {}
    except (OSError, yaml.YAMLError):
        pass
    out: dict = {}
    for r in historique.lister(limite):  # du plus récent au plus ancien
        if not r.get("xray"):
            continue
        e = out.setdefault(r["xray"], {"runs": [], "campagne": "", "campagne_nom": "", "plan": ""})
        e["runs"].append({k: r.get(k) for k in ("id", "debut", "fin", "statut", "plateforme", "passes", "echecs", "dry_run")})
        e["campagne"] = e["campagne"] or r.get("campagne") or ""
        e["campagne_nom"] = e["campagne_nom"] or noms.get(r.get("campagne") or "", "")
        e["plan"] = e["plan"] or r.get("xray_plan") or ""
    return out


def params_relance(cle: str, echecs: bool = False, plateforme: str = "") -> dict:
    """Paramètres d'un nouveau run qui écrit dans la même Exécution (Test Execution Xray) : tous ses tests, ou ceux en
    échec. Reprend le dernier run de l'atelier dans cette exécution (suite, plateforme, environnement, campagne) ;
    seuls les tests automatisés (présents dans le dépôt Robot) sont lancés, les autres sont signalés."""
    from atelier.execution import historique
    from atelier.execution.depot_robot import lire_depot

    d = detail_execution_xray(cle)
    voulus = [r["test"] for r in d["runs"] if not echecs or _classe_xray(r["statut"]) == "echec"]
    automatises = {c for t in lire_depot()["tests"].values() for c in t.get("cles_xray") or []}
    lances = [k for k in voulus if k in automatises]
    if not lances:
        raise ValueError("Aucun test automatisé à relancer dans cette exécution" + (" (aucun échec)." if echecs and not voulus else "."))
    base: dict = {}
    if d["runs_atelier"]:
        f = historique.dossier(d["runs_atelier"][0]["id"]) / "bilan.json"
        base = (json.loads(f.read_text("utf-8")).get("params") or {}) if f.exists() else {}
    plat = plateforme or ((base.get("variables") or {}).get("PLATFORM")) or next((e for e in d.get("environnements") or [] if e in PLATEFORMES), "")
    if plat not in PLATEFORMES:
        raise ValueError(f"Plateforme à préciser : {', '.join(PLATEFORMES)}.")
    p = {"target": base.get("target") or "tests", "variables": {**(base.get("variables") or {}), "PLATFORM": plat},
         "include_tags": lances, "xray_ticket": cle, "jdd_env": base.get("jdd_env") or ""}
    return {"params": {k: v for k, v in p.items() if v}, "campagne": d.get("campagne") or "", "tests": lances,
            "non_automatises": [k for k in voulus if k not in automatises]}


def detail_execution_xray(cle: str) -> dict:
    """Une Test Execution de la copie locale : ses test runs (statut, fin), avec résumé du test, automatisé ou non."""
    from atelier.execution.depot_robot import lire_depot
    from atelier.intelligence import patrimoine_xray

    pat = patrimoine_xray.charger() or {}
    e = next((x for x in pat.get("executions") or [] if x["cle"] == cle), None)
    if not e:
        raise KeyError(f"Exécution {cle} absente de la copie locale.")
    resumes = {t["cle"]: t.get("resume") or "" for t in pat.get("tests") or []}
    automatises = {c for t in lire_depot()["tests"].values() for c in t.get("cles_xray") or []}
    lien = runs_par_execution().get(cle, {})
    return {**{k: e.get(k) for k in ("cle", "resume", "statut", "cree", "environnements", "tests_total", "incomplete")},
            "campagne": lien.get("campagne", ""), "campagne_nom": lien.get("campagne_nom", ""),
            **{k: v for k, v in (next((x for x in vue_xray()["recentes"] if x["cle"] == cle), None) or {"plans": [], "plan": lien.get("plan", ""), "assigne": e.get("assigne", ""), "fin": ""}).items()
               if k in ("plans", "plan", "assigne", "fin")},
            "runs_atelier": lien.get("runs") or [],
            "runs": [{"test": k, "resume": resumes.get(k, ""), "statut": r.get("statut", ""), "fin": r.get("fin", ""), "modifiable": bool(r.get("id")),
                      "automatise": k in automatises} for k, r in sorted((e.get("runs") or {}).items())]}


def rejouer_xray(run_id: str) -> dict:
    """Renvoie les événements Xray restés en attente d'un run (même mécanisme que « python -m atelier xray-sync »)."""
    from atelier.execution import historique
    from atelier.execution.journal_xray import OUTBOX, Synchroniseur

    d = historique.dossier(run_id)
    dossiers = [p.parent for p in d.rglob(OUTBOX)] if d.exists() else []
    if not dossiers:
        raise KeyError(f"Aucun journal Xray pour {run_id}.")
    bilans = [Synchroniseur(x).envoyer_tout() for x in dossiers]
    return {"run": run_id, "envoyes": sum(b["envoyes"] for b in bilans), "restants": sum(b["restants"] for b in bilans),
            "erreurs": [b["erreur"] for b in bilans if b.get("erreur")], "etat": etat_xray(run_id)}
