"""Projets de l'atelier : un repository de tests Robot + son projet Xray / Jira, et bascule de l'un à l'autre.

Chaque projet a ses propres données (stratégie, conception, instantané Xray, campagnes, échecs, gouvernance,
Knowledge Graph) : elles vivent DANS le dossier du repository, donc changer de projet change tout le contexte.

La liste des projets est une configuration du poste (fichier ATELIER_PROJETS, défaut ~/.atelier-projets.json),
jamais du dépôt. Elle ne contient AUCUN secret : pour un identifiant ou un jeton, seul le NOM de la variable
d'environnement qui le porte est enregistré (ex. « XRAY_CLIENT_ID_TAM ») ; la valeur reste dans l'environnement.
Chaque bascule est journalisée (qui, quand, de quel projet vers lequel).
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path

from atelier.domain import projet

# variables de connexion pilotées par le projet actif ; leurs valeurs de démarrage servent de défaut
VARIABLES = ("JIRA_BASE_URL", "JIRA_EMAIL", "XRAY_BASE_URL")
SECRETS = ("XRAY_CLIENT_ID", "XRAY_CLIENT_SECRET", "JIRA_API_TOKEN")
_ORIGINE = {v: os.environ.get(v) for v in VARIABLES + SECRETS + ("ROBOT_PROJECT_DIR",)}
NOM_VARIABLE = re.compile(r"^[A-Z_][A-Z0-9_]{1,80}$")
CLE_PROJET = re.compile(r"^[A-Z][A-Z0-9_]{0,19}$")
_verrou = threading.Lock()


def _fichier() -> Path:
    return Path(os.environ.get("ATELIER_PROJETS", Path.home() / ".atelier-projets.json")).expanduser()


def _journal() -> Path:
    f = _fichier()
    return f.with_name(f.stem + ".journal.jsonl")


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _auteur() -> str:
    return os.environ.get("USERNAME") or os.environ.get("USER") or "automaticien"


def _charger() -> dict:
    f = _fichier()
    d = json.loads(f.read_text("utf-8")) if f.exists() else {}
    d.setdefault("projets", [])
    d.setdefault("actif", "")
    return d


def _sauver(d: dict):
    f = _fichier()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, f)


def _vue(p: dict) -> dict:
    """Projet tel qu'affiché : chemins résolus, et pour chaque secret seulement s'il est présent dans l'environnement."""
    return {**p, "secrets_presents": {cible: bool(os.environ.get(src)) for cible, src in (p.get("secrets") or {}).items()},
            "dossier_existe": Path(p["dossier"]).is_dir()}


def lister() -> dict:
    d = _charger()
    return {"projets": [_vue(p) for p in d["projets"]], "actif": actif_id(), "fichier": str(_fichier())}


def actif_id() -> str:
    """Projet actif = celui dont le dossier est le PROJECT_DIR courant (vérité du processus)."""
    for p in _charger()["projets"]:
        try:
            if Path(p["dossier"]).expanduser().resolve() == projet.PROJECT_DIR:
                return p["id"]
        except OSError:
            continue
    return ""


def actif() -> dict | None:
    i = actif_id()
    return next((p for p in _charger()["projets"] if p["id"] == i), None)


def cle_xray() -> str:
    """Clé du projet Xray du projet actif (préremplissage des imports, runs, publications) ; vide si aucun."""
    return (actif() or {}).get("xray_projet", "")


def cle_jira() -> str:
    p = actif() or {}
    return p.get("jira_projet") or p.get("xray_projet", "")


def valider(p: dict) -> dict:
    nom = str(p.get("nom") or "").strip()
    if not nom:
        raise ValueError("Nom du projet obligatoire.")
    dossier = Path(str(p.get("dossier") or "")).expanduser()
    if not str(p.get("dossier") or "").strip() or not dossier.is_dir():
        raise ValueError(f"Dossier du repository introuvable : {p.get('dossier')}")
    dossier = dossier.resolve()
    if dossier == Path.home().resolve() or dossier == Path(dossier.anchor):
        raise ValueError("Le dossier du repository ne peut pas être le dossier personnel ni la racine du disque.")
    out = {"id": re.sub(r"[^a-z0-9]+", "-", str(p.get("id") or nom).lower()).strip("-")[:40] or "projet", "nom": nom, "dossier": str(dossier)}
    for k in ("xray_projet", "jira_projet"):
        v = str(p.get(k) or "").strip().upper()
        if v and not CLE_PROJET.match(v):
            raise ValueError(f"{k} : clé de projet Jira attendue (ex. TAM).")
        out[k] = v
    for k in ("jira_url", "xray_url"):
        v = str(p.get(k) or "").strip().rstrip("/")
        if v and not v.startswith("https://"):
            raise ValueError(f"{k} : URL https:// attendue.")
        out[k] = v
    out["jira_email"] = str(p.get("jira_email") or "").strip()
    out["environnements"] = [str(e).strip() for e in (p.get("environnements") or []) if str(e).strip()]
    sec = {}
    for cible, src in (p.get("secrets") or {}).items():
        if cible not in SECRETS:
            raise ValueError(f"Secret inconnu : {cible} (attendus : {', '.join(SECRETS)}).")
        src = str(src or "").strip()
        if not src:
            continue
        if not NOM_VARIABLE.match(src):  # garde-fou : on enregistre un NOM de variable, jamais une valeur
            raise ValueError(f"{cible} : indiquer le NOM d'une variable d'environnement (ex. {cible}_TAM), jamais sa valeur.")
        sec[cible] = src
    out["secrets"] = sec
    return out


def enregistrer(p: dict) -> dict:
    p = valider(p)
    with _verrou:
        d = _charger()
        autres = [x for x in d["projets"] if x["id"] != p["id"]]
        if any(Path(x["dossier"]).resolve() == Path(p["dossier"]) for x in autres):
            raise ValueError("Ce dossier est déjà déclaré pour un autre projet.")
        d["projets"] = autres + [p]
        _sauver(d)
    _tracer("enregistrement", vers=p["id"])
    if p["id"] == actif_id():
        _appliquer(p)  # connexions du projet actif mises à jour sans bascule
    return lister()


def supprimer(pid: str) -> dict:
    if pid == actif_id():
        raise PermissionError("Projet actif : basculer d'abord sur un autre projet.")
    with _verrou:
        d = _charger()
        d["projets"] = [x for x in d["projets"] if x["id"] != pid]
        _sauver(d)
    _tracer("suppression", de=pid)  # seule la déclaration est retirée : le repository et ses données restent
    return lister()


def _appliquer(p: dict):
    """Rend le projet actif dans ce processus : dossier de tests, URL et identifiants de connexion."""
    projet.PROJECT_DIR = Path(p["dossier"]).resolve()
    if not os.environ.get("MCP_SNAPSHOT_DIR"):
        projet.SNAP_DIR = projet.PROJECT_DIR / ".mcp_snapshots"
    os.environ["ROBOT_PROJECT_DIR"] = str(projet.PROJECT_DIR)  # listeners et sous-processus Robot
    valeurs = {"JIRA_BASE_URL": p.get("jira_url"), "JIRA_EMAIL": p.get("jira_email"), "XRAY_BASE_URL": p.get("xray_url")}
    for v in VARIABLES:
        _poser(v, valeurs.get(v) or _ORIGINE.get(v))
    for v in SECRETS:
        src = (p.get("secrets") or {}).get(v)
        _poser(v, os.environ.get(src) if src else _ORIGINE.get(v))


def _poser(nom: str, valeur: str | None):
    if valeur:
        os.environ[nom] = valeur
    else:
        os.environ.pop(nom, None)


def activer(pid: str, occupe: str = "") -> dict:
    """Bascule sur un projet. occupe : raison de refus fournie par l'appelant (run en cours ou en file)."""
    if occupe:
        raise PermissionError(f"Changement de projet impossible : {occupe}.")
    p = next((x for x in _charger()["projets"] if x["id"] == pid), None)
    if not p:
        raise KeyError(f"Projet inconnu : {pid}")
    if not Path(p["dossier"]).is_dir():
        raise FileNotFoundError(f"Dossier du repository introuvable : {p['dossier']}")
    de = actif_id() or str(projet.PROJECT_DIR)
    with _verrou:
        _appliquer(p)
        d = _charger()
        d["actif"] = pid
        _sauver(d)
    _tracer("bascule", de=de, vers=pid)
    return lister()


def au_demarrage():
    """Sans ROBOT_PROJECT_DIR explicite, reprend le dernier projet actif ; sinon applique les connexions du projet
    correspondant au dossier imposé (s'il est déclaré)."""
    d = _charger()
    if not _ORIGINE.get("ROBOT_PROJECT_DIR") and d["actif"]:
        p = next((x for x in d["projets"] if x["id"] == d["actif"]), None)
        if p and Path(p["dossier"]).is_dir():
            _appliquer(p)
            return
    p = actif()
    if p:
        _appliquer(p)


def _tracer(op: str, **d):
    f = _journal()
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": _maintenant(), "auteur": _auteur(), "op": op, **d}, ensure_ascii=False) + "\n")


def journal(limite: int = 100) -> list[dict]:
    f = _journal()
    return [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()][::-1][:limite] if f.exists() else []
