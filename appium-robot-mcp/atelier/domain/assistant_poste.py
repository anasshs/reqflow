"""Assistant du premier lancement (page /assistant) : base, premier compte, espace de travail, connexions.

1. Base : la base locale du poste (défaut ~/.atelier/atelier.db) ou un autre emplacement ; changer d'emplacement peut
   y déplacer le contenu (export puis import, rien n'est supprimé de l'ancienne).
2. Premier compte : responsable ; ensuite il faut se connecter.
3. Espace de travail : un projet (nom, application, Xray / Jira, dépôt Git des tests) et son dossier sur ce poste —
   un dossier existant, ou un clone du dépôt Git (GitLab) des tests. Un projet déjà dans la base (créé sur un autre
   poste) n'a besoin que de son dossier ici.
4. Connexions : Xray, Jira, GitLab, dans Paramètres (les jetons vont dans le coffre du système, jamais dans la base).
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from atelier.domain import magasin, projets, utilisateurs


def etat() -> dict:
    c = magasin.config_base()
    b = {"configuree": magasin.configuree(), "chemin": str(magasin.chemin_base()), "type": c.get("type", "locale"), "url": c.get("url", "")}
    try:
        b.update(magasin.base().info())
        b["ok"] = True
    except Exception as e:  # noqa: BLE001
        b.update(ok=False, erreur=str(e)[:300])
    comptes = utilisateurs.actifs()
    moi = utilisateurs.courant()
    try:
        l = projets.lister()
    except Exception as e:  # noqa: BLE001
        l = {"projets": [], "actif": "", "erreur": str(e)[:300]}
    sans_dossier = [p["id"] for p in l["projets"] if not p.get("dossier")]
    connexions = {v: bool(os.environ.get(v)) for v in ("XRAY_BASE_URL", "JIRA_BASE_URL", "GITLAB_URL", "GITLAB_PROJET")}
    return {"base": b, "comptes": comptes, "moi": moi, "projets": l["projets"], "projet_actif": l["actif"], "sans_dossier": sans_dossier,
            "connexions": connexions,
            "termine": bool(b.get("ok") and b["configuree"] and comptes and l["actif"]),
            "etapes": {"base": bool(b.get("ok") and b["configuree"]), "compte": comptes, "espace": bool(l["actif"]),
                       "connexions": any(connexions.values())}}


def _exiger_responsable():
    if utilisateurs.actifs():
        u = utilisateurs.courant()
        if not u or u.get("role") != "responsable":
            raise PermissionError("Réservé à un responsable.")


def chemin_reseau(chemin: str) -> bool:
    """Chemin sur un partage réseau (\\\\serveur\\partage, //serveur/partage, ou lecteur réseau Windows mappé)."""
    c = chemin.strip()
    if c.startswith(("\\\\", "//")):
        return True
    if os.name == "nt" and len(c) >= 2 and c[1] == ":":
        try:
            import ctypes

            return ctypes.windll.kernel32.GetDriveTypeW(f"{c[0]}:\\") == 4  # DRIVE_REMOTE
        except Exception:  # noqa: BLE001
            return False
    return False


def choisir_serveur(url: str, deplacer: bool = False, ca: str = "") -> dict:
    """Base sur le serveur de données de l'équipe. deplacer : la base de ce poste part sur le serveur, possible tant
    que le serveur n'a encore aucun compte (amorçage : comptes et contenu arrivent ensemble). Ensuite, chacun se
    connecte avec son compte du serveur."""
    url = url.strip().rstrip("/")
    if not (url.startswith("https://") or url.startswith(("http://127.0.0.1", "http://localhost"))):
        raise ValueError("Adresse du serveur : https://… (http seulement pour un serveur sur cette machine).")
    essai = magasin.BaseDistante(url, ca)
    try:
        sans_compte = not essai.appel("comptes/actifs", jeton="")["actifs"]
    except ConnectionError as e:
        raise ValueError(str(e)) from None
    copie = None
    if deplacer:
        if not sans_compte:
            raise ValueError("Le serveur a déjà ses comptes et sa base : s'y connecter plutôt que d'y copier celle de ce poste.")
        export = magasin.dossier_poste() / "exports" / "vers-serveur.jsonl"
        magasin.base().exporter(export)
        copie = essai.importer(export)
    magasin.regler_poste(base={"type": "serveur", "url": url, **({"ca": ca} if ca else {})})
    with utilisateurs._VERROU:  # comptes du serveur désormais : se reconnecter
        utilisateurs._SESSIONS.clear()
    utilisateurs._JETONS_SERVEUR.clear()
    utilisateurs._CACHE.clear()
    return {"base": {"type": "serveur", "url": url}, "copie": copie, "serveur_vide": sans_compte and not deplacer}


def choisir_base(chemin: str = "", deplacer: bool = False, ca: str = "") -> dict:
    """Emplacement de la base : un fichier local, ou l'adresse du serveur de données (https://…) ; deplacer : copier
    le contenu de la base actuelle dans la nouvelle."""
    _exiger_responsable()
    if chemin.strip().startswith(("https://", "http://")):
        return choisir_serveur(chemin, deplacer, ca)
    if chemin_reseau(chemin):
        raise ValueError("Base sur un partage réseau refusée : SQLite ne supporte pas l'écriture de plusieurs postes à travers le "
                         "réseau (base corrompue). Lancer le serveur de données sur la machine qui garde la base "
                         "(lancer-serveur-donnees.cmd), puis donner ici son adresse https://serveur:8443.")
    cible = Path(chemin).expanduser() if chemin.strip() else magasin.dossier_poste() / "atelier.db"
    if cible.suffix.lower() != ".db":
        cible = cible / "atelier.db" if cible.is_dir() or not cible.suffix else cible
    ancienne = magasin.chemin_base()
    copie = None
    if deplacer and ancienne.exists() and ancienne.resolve() != cible.resolve():
        export = magasin.dossier_poste() / "exports" / "deplacement.jsonl"
        magasin.base().exporter(export)
        magasin.regler_poste(base={"type": "locale", "chemin": str(cible)})
        copie = magasin.base().importer(export)
    else:
        magasin.regler_poste(base={"type": "locale", "chemin": str(cible)})
        magasin.base()  # crée le fichier
    return {"base": magasin.base().info(), "copie": copie}


def creer_premier_compte(identifiant: str, mot_de_passe: str, nom: str = "") -> tuple[str, dict]:
    if utilisateurs.actifs():
        raise PermissionError("Un compte existe déjà : se connecter.")
    if not magasin.configuree():
        magasin.regler_poste(base={"type": "locale", "chemin": str(magasin.chemin_base())})
    utilisateurs.creer(identifiant, mot_de_passe, "responsable", nom, ["*"])
    return utilisateurs.connecter(identifiant, mot_de_passe)


URL_GIT = re.compile(r"^(https://[^\s]+|git@[^\s:]+:[^\s]+|file://\S+)$")  # file:// : miroir local du dépôt


def cloner(depot: str, dossier: str, timeout: int = 600) -> dict:
    """Clone du dépôt Git des tests (identifiants : gestionnaire d'identifiants Git du poste, jamais saisis ici)."""
    if not URL_GIT.match(depot or ""):
        raise ValueError("Adresse du dépôt : https://… ou git@hote:groupe/projet.git")
    if "@" in depot.split("//", 1)[-1].split("/", 1)[0] and depot.startswith("https://"):
        raise ValueError("Pas d'identifiant dans l'adresse : Git les demande lui-même (gestionnaire d'identifiants).")
    d = Path(dossier).expanduser()
    if d.exists() and any(d.iterdir()):
        raise ValueError(f"Le dossier {d} existe et n'est pas vide : choisir un dossier vide, ou l'utiliser tel quel.")
    d.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["git", "clone", depot, str(d)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                       env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if r.returncode:
        raise RuntimeError("git clone refusé : " + (r.stderr or r.stdout).strip()[-400:])
    return {"dossier": str(d)}


def espace(p: dict) -> dict:
    """Projet et son dossier sur ce poste (nouveau projet, ou projet partagé dont ce poste n'a pas encore le dossier)."""
    if utilisateurs.actifs():
        u = utilisateurs.courant()
        if not u:
            raise PermissionError("Se connecter d'abord.")
    existant = next((x for x in projets._charger()["projets"] if x["id"] == p.get("id")), None) if p.get("id") else None
    if existant is None:
        _exiger_responsable()  # créer un projet : responsable
    dossier = str(p.get("dossier") or "").strip()
    if not dossier:
        raise ValueError("Dossier du projet sur ce poste obligatoire.")
    depot = str(p.get("depot_git") or (existant or {}).get("depot_git") or "").strip()
    clone = None
    if p.get("cloner"):
        clone = cloner(depot, dossier)
    elif not Path(dossier).expanduser().is_dir():
        raise ValueError(f"Dossier introuvable : {dossier} (ou cocher « cloner le dépôt »).")
    donnees = {**(existant or {}), **{k: v for k, v in p.items() if k not in ("cloner",) and v not in (None, "")}, "dossier": dossier}
    if depot:
        donnees["depot_git"] = depot
    projets.enregistrer(donnees)
    pid = next(x["id"] for x in projets._charger()["projets"] if x.get("dossier") and Path(x["dossier"]).resolve() == Path(dossier).expanduser().resolve())
    projets.activer(pid)
    return {"projet": pid, "clone": clone, "etat": etat()}
