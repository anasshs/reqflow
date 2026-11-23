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

from atelier.domain import coffre, projet

# variables de connexion pilotées par le projet actif ; leurs valeurs de démarrage servent de défaut
VARIABLES = ("JIRA_BASE_URL", "JIRA_EMAIL", "XRAY_BASE_URL", "GITLAB_URL", "GITLAB_PROJET")
SECRETS = ("XRAY_CLIENT_ID", "XRAY_CLIENT_SECRET", "JIRA_API_TOKEN", "GITLAB_TOKEN")
SECRETS_OUTILS = ("ANTHROPIC_API_KEY", "IA_INTERNE_JETON")  # clés des fournisseurs d'IA, gérées par le coffre aussi
_ORIGINE = {v: os.environ.get(v) for v in VARIABLES + SECRETS + ("ROBOT_PROJECT_DIR",)}
_ORIGINE_ENV = dict(_ORIGINE)  # valeurs réellement fournies par l'environnement au démarrage
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
            "dossier_existe": Path(p["dossier"]).is_dir(), "depot": p.get("depot") or p["dossier"], "sous_dossier": p.get("sous_dossier", "")}


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


def _sous_dossier(v) -> str:
    """Sous-dossier du projet Robot dans le repository : chemin relatif simple (« qa/robot »), jamais « .. » ni absolu."""
    s = str(v or "").strip().replace("\\", "/").strip("/")
    if not s:
        return ""
    if s.startswith("~") or ":" in s or any(x in ("", ".", "..") for x in s.split("/")) or not re.fullmatch(r"[\w .@+-]+(/[\w .@+-]+)*", s):
        raise ValueError("Sous-dossier des tests : chemin relatif au repository attendu (ex. qa/robot), sans « .. ».")
    return s


def _dossier_demande(p: dict) -> dict:
    """Repository local (clone Git, par exemple d'un dépôt GitLab multi-applications) + sous-dossier des tests Robot :
    le dossier du projet est leur réunion. Sans repository, le champ « dossier » historique est gardé tel quel."""
    depot = str(p.get("depot") or "").strip()
    if not depot:
        return p
    sous = _sous_dossier(p.get("sous_dossier"))
    return {**p, "dossier": str(Path(depot).expanduser() / sous) if sous else depot, "sous_dossier": sous}


def preparer_sous_dossier(p: dict) -> list[str]:
    """Crée le sous-dossier des tests s'il n'existe pas encore (action explicite : enregistrement du projet), avec un
    .gitignore pour l'état de travail de l'atelier, propre à chaque poste. Le repository lui-même doit exister."""
    depot = Path(str(p.get("depot") or "")).expanduser()
    sous = _sous_dossier(p.get("sous_dossier"))
    if not sous or not str(p.get("depot") or "").strip():
        return []
    if not depot.is_dir():
        raise ValueError(f"Repository introuvable : {p.get('depot')}")
    cible = depot / sous
    if cible.is_dir():
        return []
    cible.mkdir(parents=True)
    from atelier.generation.studio import ETAT_ATELIER

    (cible / ".gitignore").write_text("# État de travail de l'Atelier d'automatisation (propre à chaque poste)\n"
                                      + "".join(f"/{x}\n" for x in ETAT_ATELIER) + "/.mcp_snapshots/\n", "utf-8")
    return [str(cible), str(cible / ".gitignore")]


def valider(p: dict) -> dict:
    nom = str(p.get("nom") or "").strip()
    if not nom:
        raise ValueError("Nom du projet obligatoire.")
    p = _dossier_demande(p)
    dossier = Path(str(p.get("dossier") or "")).expanduser()
    if not str(p.get("dossier") or "").strip() or not dossier.is_dir():
        raise ValueError(f"Dossier du repository introuvable : {p.get('dossier')}")
    dossier = dossier.resolve()
    if dossier == Path.home().resolve() or dossier == Path(dossier.anchor):
        raise ValueError("Le dossier du repository ne peut pas être le dossier personnel ni la racine du disque.")
    out = {"id": re.sub(r"[^a-z0-9]+", "-", str(p.get("id") or nom).lower()).strip("-")[:40] or "projet", "nom": nom, "dossier": str(dossier)}
    if str(p.get("depot") or "").strip():
        depot = Path(str(p["depot"])).expanduser().resolve()
        if depot == Path.home().resolve() or depot == Path(depot.anchor):
            raise ValueError("Le repository ne peut pas être le dossier personnel ni la racine du disque.")
        out["depot"], out["sous_dossier"] = str(depot), p.get("sous_dossier", "")
    for k in ("xray_projet", "jira_projet"):
        v = str(p.get(k) or "").strip().upper()
        if v and not CLE_PROJET.match(v):
            raise ValueError(f"{k} : clé de projet Jira attendue (ex. DEMO).")
        out[k] = v
    for k in ("jira_url", "xray_url", "gitlab_url"):
        v = str(p.get(k) or "").strip().rstrip("/")
        if v and not v.startswith("https://"):
            raise ValueError(f"{k} : URL https:// attendue.")
        out[k] = v
    out["jira_email"] = str(p.get("jira_email") or "").strip()
    gp = str(p.get("gitlab_projet") or "").strip().strip("/")
    if gp and not re.fullmatch(r"[\w.-]+(/[\w.-]+)*|\d+", gp):
        raise ValueError("gitlab_projet : chemin « groupe/sous-groupe/projet » ou identifiant numérique.")
    out["gitlab_projet"] = gp
    # Les environnements ne se saisissent plus ici : ils sont lus dans le projet Xray (atelier/integrations/xray/environnements.py).
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
    crees = preparer_sous_dossier(p)
    p = valider(p)
    with _verrou:
        d = _charger()
        autres = [x for x in d["projets"] if x["id"] != p["id"]]
        if any(Path(x["dossier"]).resolve() == Path(p["dossier"]) for x in autres):
            raise ValueError("Ce dossier est déjà déclaré pour un autre projet.")
        d["projets"] = autres + [p]
        _sauver(d)
    _tracer("enregistrement", vers=p["id"], **({"cree": ", ".join(crees)} if crees else {}))
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
    valeurs = {"JIRA_BASE_URL": p.get("jira_url"), "JIRA_EMAIL": p.get("jira_email"), "XRAY_BASE_URL": p.get("xray_url"),
               "GITLAB_URL": p.get("gitlab_url"), "GITLAB_PROJET": p.get("gitlab_projet")}
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


def suivre_actif():
    """Processus à longue durée de vie (serveur MCP) : si le projet actif a changé dans l'atelier, il est appliqué
    ici aussi. Sans effet quand ROBOT_PROJECT_DIR est imposé par l'environnement."""
    if _ORIGINE_ENV.get("ROBOT_PROJECT_DIR"):
        return
    d = _charger()
    p = next((x for x in d["projets"] if x["id"] == d.get("actif")), None)  # choix enregistré par l'atelier
    if p and Path(p["dossier"]).is_dir() and Path(p["dossier"]).resolve() != projet.PROJECT_DIR:
        _appliquer(p)


def au_demarrage():
    """Sans ROBOT_PROJECT_DIR explicite, reprend le dernier projet actif ; sinon applique les connexions du projet
    correspondant au dossier imposé (s'il est déclaré). Les connexions générales enregistrées complètent l'environnement."""
    d = _charger()
    charger_coffre()
    for k, var in GENERAUX.items():
        if not _ORIGINE_ENV.get(var) and (d.get("general") or {}).get(k):
            _ORIGINE[var] = d["general"][k]
            os.environ.setdefault(var, d["general"][k])
    if not _ORIGINE.get("ROBOT_PROJECT_DIR") and d["actif"]:
        p = next((x for x in d["projets"] if x["id"] == d["actif"]), None)
        if p and Path(p["dossier"]).is_dir():
            _appliquer(p)
            return
    p = actif()
    if p:
        _appliquer(p)


# =========================================================================== connexions générales et secrets saisis
GENERAUX = {"jira_url": "JIRA_BASE_URL", "jira_email": "JIRA_EMAIL", "xray_url": "XRAY_BASE_URL"}
_SAISIS: set[str] = set()  # noms des secrets saisis dans l'application pendant cette session (valeurs : environnement du processus)


def connexions() -> dict:
    """Connexions générales (valables pour tout projet qui ne les redéfinit pas) et secrets attendus, avec leur seule
    présence : aucune valeur de secret n'est jamais renvoyée."""
    g = _charger().get("general") or {}
    attendus: dict[str, list[str]] = {n: ["général"] for n in SECRETS}
    attendus.update({n: ["IA"] for n in SECRETS_OUTILS})
    for p in _charger()["projets"]:
        for cible, src in (p.get("secrets") or {}).items():
            attendus.setdefault(src, []).append(f"{p['nom']} ({cible})")
    return {"general": {k: g.get(k, "") for k in GENERAUX},
            "general_effectif": {k: os.environ.get(v, "") for k, v in GENERAUX.items()},
            "coffre": {"disponible": coffre.disponible(), "systeme": coffre.nom_backend()},
            "secrets": [_etat_secret(n, u) for n, u in sorted(attendus.items())]}


def _etat_secret(n: str, usages: list[str]) -> dict:
    dans_coffre = coffre.present(n)
    poste = bool(_POSTE.get(n))
    source = "coffre" if dans_coffre else "poste" if poste else "session" if n in _SAISIS and os.environ.get(n) else "absent"
    return {"nom": n, "usages": usages, "present": source != "absent", "source": source, "saisi_dans_l_app": n in _SAISIS,
            "dans_le_coffre": dans_coffre, "environnement_poste": poste}


def enregistrer_general(g: dict) -> dict:
    """URL Jira / Xray et e-mail Jira communs à tous les projets (non secrets : enregistrés dans la liste du poste)."""
    propre = {}
    for k in GENERAUX:
        v = str(g.get(k) or "").strip().rstrip("/")
        if k.endswith("_url") and v and not v.startswith("https://"):
            raise ValueError(f"{k} : URL https:// attendue.")
        propre[k] = v
    with _verrou:
        d = _charger()
        d["general"] = propre
        _sauver(d)
    for k, var in GENERAUX.items():
        if not _ORIGINE_ENV.get(var):  # une variable d'environnement posée au démarrage reste prioritaire
            _ORIGINE[var] = propre[k] or None
    _reappliquer()
    _tracer("connexions_generales")
    return connexions()


_ENV_POSTE = {k for k in os.environ if k.startswith(("XRAY_", "JIRA_", "GITLAB_"))}  # posées hors de l'atelier au démarrage
_POSTE = {k: v for k, v in os.environ.items() if k.startswith(("XRAY_", "JIRA_", "GITLAB_", "ANTHROPIC_", "IA_INTERNE_"))}


def _noms_secrets() -> list[str]:
    noms = set(SECRETS) | set(SECRETS_OUTILS)
    for p in _charger()["projets"]:
        noms |= {src for src in (p.get("secrets") or {}).values() if src}
    return sorted(noms)


def charger_coffre() -> list[str]:
    """Charge les secrets du coffre dans l'environnement du processus (le coffre prime sur une variable du poste ;
    les runs Robot et autres sous-processus en héritent). Renvoie les noms chargés, jamais les valeurs."""
    charges = []
    for n in _noms_secrets():
        v = coffre.lire(n)
        if v and os.environ.get(n) != v:
            os.environ[n] = v
            if n in SECRETS:
                _ORIGINE[n] = v
            _SAISIS.add(n)
            charges.append(n)
    if charges:
        _reappliquer()
    return charges


def valeur_secret(nom: str) -> str:
    """Valeur d'un secret au moment de l'appel, dans n'importe quel processus (interface, MCP, ligne de commande,
    listener d'un run Robot) : variable propre du projet actif s'il en déclare une (ex. XRAY_CLIENT_ID_TAM), lue
    d'abord dans le coffre, puis dans l'environnement (variable du poste, saisie de session)."""
    p = actif()
    n = ((p or {}).get("secrets") or {}).get(nom) or nom
    return coffre.lire(n) or os.environ.get(n) or (os.environ.get(nom, "") if n != nom else "")


def verser_dans_coffre(nom: str) -> dict:
    """Verse dans le coffre la valeur d'un secret présent seulement comme variable du poste (la valeur ne transite
    que du processus vers le coffre : jamais affichée ni journalisée)."""
    if nom not in _noms_secrets():
        raise ValueError(f"{nom} : variable non attendue.")
    v = os.environ.get(nom) or _POSTE.get(nom)
    if not v:
        raise ValueError(f"{nom} : aucune valeur sur le poste à verser.")
    coffre.ecrire(nom, v.strip().strip('"').strip("'").strip())
    _tracer("secret_verse_au_coffre", vers=nom)
    return connexions()


def saisir_secret(nom: str, valeur: str, memoriser: bool = True) -> dict:
    """Secret saisi dans l'application : mémorisé dans le coffre du système (Gestionnaire d'identifiants Windows) si
    memoriser et coffre disponible, sinon gardé en mémoire jusqu'à l'arrêt du serveur. Jamais écrit dans un fichier de
    l'atelier, jamais journalisé, jamais renvoyé. Seuls les noms attendus sont acceptés."""
    autorises = {s["nom"] for s in connexions()["secrets"]}
    if nom not in autorises:
        raise ValueError(f"{nom} : variable non attendue (secrets généraux ou variables déclarées par un projet).")
    valeur = str(valeur or "").strip().strip('"').strip("'").strip()
    if not valeur:
        raise ValueError("Valeur vide.")
    mode = "session"
    if coffre.disponible():  # le coffre est la source des secrets : toujours mémorisé quand il est disponible
        coffre.ecrire(nom, valeur)
        mode = "coffre"
    os.environ[nom] = valeur
    if nom in SECRETS:
        _ORIGINE[nom] = valeur  # secret général : reste le défaut après une bascule de projet
    _SAISIS.add(nom)
    _reappliquer()
    _tracer("secret_saisi", vers=nom, mode=mode)  # le nom seulement
    return {**connexions(), "mode": mode}


def effacer_secret(nom: str) -> dict:
    """Retire le secret de la session ET du coffre du système."""
    du_coffre = coffre.effacer(nom)
    if nom not in _SAISIS and not du_coffre:
        raise ValueError(f"{nom} n'a pas été saisi dans l'application (variable d'environnement du poste : à retirer hors de l'atelier).")
    os.environ.pop(nom, None)
    if nom in SECRETS:
        _ORIGINE[nom] = _ORIGINE_ENV.get(nom)
    _SAISIS.discard(nom)
    _reappliquer()
    _tracer("secret_efface", de=nom)
    return connexions()


def _reappliquer():
    p = actif()
    if p:
        _appliquer(p)
    else:
        for v in VARIABLES + SECRETS:
            if v in GENERAUX.values() or v in SECRETS:
                _poser(v, _ORIGINE.get(v))


def _tracer(op: str, **d):
    f = _journal()
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": _maintenant(), "auteur": _auteur(), "op": op, **d}, ensure_ascii=False) + "\n")


def journal(limite: int = 100) -> list[dict]:
    f = _journal()
    return [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()][::-1][:limite] if f.exists() else []
