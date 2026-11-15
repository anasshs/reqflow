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
        r = subprocess.run(["git", "-C", str(projet.PROJECT_DIR), *args], capture_output=True, text=True, timeout=5)
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
                   capture_output=True, text=True, timeout=300)
    statut = lambda f: {t.longname: t.status for t in ExecutionResult(str(f)).suite.all_tests} if f.exists() else {}  # noqa: E731
    s1, s2 = statut(t1 / "output.xml"), statut(t2 / "output.xml")
    final = {**second, "resultat": parse_robot_output(str((out / "output.xml").relative_to(projet.PROJECT_DIR)))}
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
    return l


def _ecrire_campagnes(l: list[dict]):
    from atelier.intelligence.strategie import _ecrire_atomique

    propres = [{k: v for k, v in c.items() if k not in ("derniere_execution", "dernier_statut", "taux_reussite", "runs")} for c in l]
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
              "xray_ticket": c.get("xray_ticket", ""), "statut": c.get("statut", "Active"),
              "exclus": [str(t) for t in c.get("exclus") or []], "planning": _planning(c.get("planning"))}
    l = campagnes()
    i = next((k for k, x in enumerate(l) if x["id"] == propre["id"]), None)
    if i is None:
        l.append(propre)
    else:
        l[i] = propre
    _ecrire_campagnes(l)
    return campagnes()


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
            fichiers.append({"chemin": str(f.relative_to(projet.PROJECT_DIR)), "nom": f.name, "taille": f.stat().st_size,
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
            "journaux": [str(j.relative_to(projet.PROJECT_DIR)) for j in journaux]}


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


def vue_xray(limite: int = 20) -> dict:
    """Indicateurs des Test Executions Xray (copie locale : import des définitions ou « Actualiser depuis Xray »),
    limités aux tests de l'application sélectionnée : statuts des test runs, taux de réussite, dernier statut de
    chaque test, tendance par exécution, tests automatisés ou non. Rien n'est estimé."""
    from atelier.execution.depot_robot import lire_depot
    from atelier.intelligence import patrimoine_xray

    pat = patrimoine_xray.charger() or {}
    vue = patrimoine_xray.charger_vue() or {"tests": []}
    tests_app = {t["cle"] for t in vue.get("tests") or []}
    filtre = bool((vue.get("filtre_application") or {}).get("valeurs") or (vue.get("filtre_application") or {}).get("champ"))
    automatises = {c for t in lire_depot()["tests"].values() for c in t.get("cles_xray") or []}
    execs, par_statut, dernier = [], {}, {}
    for e in sorted(pat.get("executions") or [], key=lambda x: x.get("cree") or "", reverse=True):  # du plus récent au plus ancien
        runs = {k: r for k, r in (e.get("runs") or {}).items() if not filtre or k in tests_app}
        if filtre and not runs and not any(k in tests_app for k in e.get("tests") or []):
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
                      "automatises": sum(1 for k in runs if k in automatises)})
    tot = {k: sum(x[k] for x in execs) for k in ("reussi", "echec", "non_execute")}
    executes = tot["reussi"] + tot["echec"]
    imp = pat.get("executions_xray") or {}
    return {"import": {"date": imp.get("date"), "nombre": imp.get("nombre"), "erreur": imp.get("erreur"), "absents": imp.get("absents") or []},
            "kpi": {"executions": len(execs), "runs": sum(x["tests"] for x in execs), **tot,
                    "taux_reussite": round(100 * tot["reussi"] / executes, 1) if executes else None,
                    "tests_en_echec": sum(1 for v in dernier.values() if v == "echec"), "tests_reussis": sum(1 for v in dernier.values() if v == "reussi"),
                    "tests_jamais_executes": len(tests_app - set(dernier)) if filtre else None,
                    "part_automatisee": round(100 * sum(x["automatises"] for x in execs) / max(1, sum(x["tests"] for x in execs)), 1) if execs else None},
            "par_statut": dict(sorted(par_statut.items(), key=lambda kv: -kv[1])),
            "tendance": [{"cle": x["cle"], "reussi": x["reussi"], "echec": x["echec"], "non_execute": x["non_execute"]} for x in reversed(execs[:limite])],
            "recentes": execs[:10]}


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
