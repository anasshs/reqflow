"""Rôles et droits de l'atelier (cahier Automation Studio, exigence « rôles »).

L'interface est locale (127.0.0.1) et n'a pas d'authentification : l'utilisateur est le compte du poste
(getpass), comme partout dans les journaux. Les rôles sont déclarés dans le projet de tests, partagé par Git :

  atelier_roles.yaml
    utilisateurs:
      a.martin: relecteur
      b.durand: automaticien
    revue_par_un_autre: true      # quatre yeux : on n'approuve pas un script qu'on a soi-même soumis

Sans ce fichier : mode ouvert (tout le monde peut tout), signalé à l'écran. Avec le fichier, un compte absent de la
liste est « lecteur ». Un refus de droit lève PermissionError (message explicite) et n'est jamais silencieux.
"""
from __future__ import annotations

from atelier.domain.yaml_rapide import charger as charger_yaml

import yaml

from atelier.domain import projet

ROLES = {
    "lecteur": "consulte, ne modifie rien",
    "automaticien": "construit, corrige locators / keywords / données, soumet en revue, commit local",
    "relecteur": "tout ce que fait l'automaticien, plus : approuver, demander des modifications, refuser, publier, merge request",
    "responsable": "tous les droits, y compris la gestion des rôles",
}
ORDRE = ["lecteur", "automaticien", "relecteur", "responsable"]
DROITS = {  # droit -> rôle minimal
    "construire": "automaticien", "corriger_locator": "automaticien", "factoriser_keyword": "automaticien",
    "importer_donnees": "automaticien", "preparer_donnees": "automaticien", "soumettre_revue": "automaticien",
    "commit_local": "automaticien", "executer_etape": "automaticien",
    "decider_revue": "relecteur", "publier": "relecteur", "merge_request": "relecteur", "valider_action": "relecteur",
    "gerer_roles": "responsable",
}
LIBELLES_DROITS = {
    "construire": "construire un test", "corriger_locator": "corriger un locator", "factoriser_keyword": "factoriser des keywords",
    "importer_donnees": "importer des données de test", "preparer_donnees": "appeler une API de préparation de données",
    "soumettre_revue": "soumettre un script en revue", "commit_local": "faire un commit local", "executer_etape": "exécuter une étape isolée",
    "decider_revue": "approuver, refuser ou demander des modifications", "publier": "publier un script",
    "merge_request": "créer une merge request", "valider_action": "accepter une action demandée par Cursor (Jira, Xray, carte)",
    "gerer_roles": "gérer les rôles",
}


def _fichier():
    return projet.PROJECT_DIR / "atelier_roles.yaml"


def _config() -> dict:
    f = _fichier()
    try:
        return (charger_yaml(f.read_text("utf-8")) or {}) if f.exists() else {}
    except (OSError, yaml.YAMLError):
        return {"erreur": "atelier_roles.yaml illisible"}


def utilisateur() -> str:
    import getpass

    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return "inconnu"


def actifs() -> bool:
    c = _config()
    return bool(c.get("utilisateurs")) or bool(c.get("erreur"))


def role(u: str | None = None) -> str:
    c = _config()
    if not actifs():
        return "responsable"  # mode ouvert
    if c.get("erreur"):
        return "lecteur"  # fichier illisible : prudence
    return str((c.get("utilisateurs") or {}).get(u or utilisateur(), "lecteur"))


def peut(droit: str, u: str | None = None) -> bool:
    r = role(u)
    return r in ORDRE and ORDRE.index(r) >= ORDRE.index(DROITS[droit])


def exiger(droit: str):
    """Lève PermissionError si l'utilisateur courant n'a pas le droit."""
    if not peut(droit):
        u, r = utilisateur(), role()
        raise PermissionError(f"Droit refusé : « {LIBELLES_DROITS[droit]} » demande le rôle {DROITS[droit]} ou plus ; "
                              f"{u} est {r} (atelier_roles.yaml du projet).")


def quatre_yeux() -> bool:
    return actifs() and bool(_config().get("revue_par_un_autre", True))


def etat() -> dict:
    u = utilisateur()
    c = _config()
    return {"actifs": actifs(), "utilisateur": u, "role": role(u), "roles": ROLES, "droits": {d: peut(d, u) for d in DROITS},
            "libelles_droits": LIBELLES_DROITS, "utilisateurs": c.get("utilisateurs") or {}, "quatre_yeux": quatre_yeux(),
            "erreur": c.get("erreur", ""), "fichier": "atelier_roles.yaml"}


def definir(utilisateurs: dict, revue_par_un_autre: bool = True) -> dict:
    """Écrit atelier_roles.yaml. Premier enregistrement : l'auteur doit se déclarer responsable (sinon il se bloquerait)."""
    if actifs():
        exiger("gerer_roles")
    propres = {}
    for u, r in (utilisateurs or {}).items():
        u = str(u).strip()
        if not u:
            continue
        if r not in ROLES:
            raise ValueError(f"Rôle inconnu pour {u} : {r} (rôles : {', '.join(ORDRE)}).")
        propres[u] = r
    if propres and propres.get(utilisateur()) != "responsable" and not any(r == "responsable" for r in propres.values()):
        raise ValueError("Au moins un responsable est nécessaire (sinon plus personne ne peut gérer les rôles).")
    if propres and actifs() is False and propres.get(utilisateur()) != "responsable":
        raise ValueError(f"Activation des rôles : se déclarer responsable ({utilisateur()}) pour ne pas se bloquer.")
    f = _fichier()
    tmp = f.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump({"utilisateurs": propres, "revue_par_un_autre": bool(revue_par_un_autre)}, allow_unicode=True, sort_keys=True), "utf-8")
    tmp.replace(f)
    return etat()
