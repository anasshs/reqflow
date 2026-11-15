"""Source des tests d'une application : la SEULE définition de « quels tests Xray appartiennent à l'application »
(Paramètres › Configuration, une configuration par application ; décision de l'utilisateur du 2026-11-15).

- jql      : requête Jira des tests de l'application (ex. project = "DEMO" AND issuetype = "Test" AND component = "Mobile") ;
- dossiers : en option, dossiers du Test Repository Xray pour affiner (Xray ne permet pas de filtrer un dossier en JQL).

La synchronisation Jira ne récupère que l'application active (sa JQL) ; dans la copie locale, chaque test porte les
applications qui l'ont synchronisé, et les écrans ne montrent que ceux de l'application sélectionnée.

Migration : une application sans source déclarée reçoit une JQL déduite des anciens réglages (clé Xray du projet,
champ « application » du Xray Mapping et ses valeurs, composant / libellé) et garde ses dossiers ; elle est marquée
« déduite » jusqu'au premier enregistrement.
"""
from __future__ import annotations

import os
import re


def _cfg(slug: str | None = None) -> dict:
    from atelier.discovery import carte

    return carte.config_app(slug) if (slug or carte.app_courante()) else {}


def _liste(vals: list[str]) -> str:
    return ", ".join('"' + str(v).replace('"', '\\"') + '"' for v in vals)


def jql_deduite(cfg: dict) -> str:
    """JQL équivalente aux anciens réglages de l'application (pour la migration)."""
    from atelier.domain import projets
    from atelier.intelligence import patrimoine_xray

    cle = (cfg.get("projet_xray") or projets.cle_xray() or "").strip().upper()
    if not cle:
        return ""
    parts = [f'project = "{cle}"', f'issuetype = "{os.environ.get("XRAY_TEST_ISSUE_TYPE", "Test")}"']
    tx = cfg.get("tests_xray") or {}
    regle = patrimoine_xray.regle_application()
    if tx.get("valeurs"):
        if regle["champ"] == "libelle":
            parts.append(f"labels in ({_liste(tx['valeurs'])})")
        elif regle["champ"] == "personnalise" and re.fullmatch(r"customfield_\d+", regle.get("champ_jira") or ""):
            parts.append(f"cf[{regle['champ_jira'].split('_')[1]}] in ({_liste(tx['valeurs'])})")
        else:
            parts.append(f"component in ({_liste(tx['valeurs'])})")
    elif tx.get("composant"):
        parts.append(f"component = {_liste([tx['composant']])}")
    elif tx.get("libelle"):
        parts.append(f"labels = {_liste([tx['libelle']])}")
    return " AND ".join(parts) + " ORDER BY key"


def source(slug: str | None = None) -> dict:
    """{"jql", "dossiers", "deduite"} de l'application (active par défaut)."""
    cfg = _cfg(slug)
    s = cfg.get("source_tests") or {}
    if s.get("jql"):
        return {"jql": s["jql"], "dossiers": list(s.get("dossiers") or []), "deduite": False}
    return {"jql": jql_deduite(cfg), "dossiers": list((cfg.get("tests_xray") or {}).get("dossiers") or []), "deduite": True}


def enregistrer(slug: str, jql: str, dossiers: list[str] | None = None) -> dict:
    from atelier.discovery import carte

    jql = (jql or "").strip()
    if not jql:
        raise ValueError("JQL des tests de l'application obligatoire.")
    if re.search(r"\bORDER\s+BY\b", jql, re.I) is None:
        jql += " ORDER BY key"
    d = sorted({carte.normaliser_dossier(x) for x in dossiers or [] if str(x).strip()})
    # les dossiers restent aussi dans tests_xray (rangement des tests publiés, liste des dossiers par application)
    carte.maj_app(slug, source_tests={"jql": jql, "dossiers": d}, tests_xray={"dossiers": d} if d else {})
    return source(slug)


def tester(jql: str, jira=None) -> dict:
    """Nombre de tickets et premiers exemples pour la JQL (lecture seule)."""
    from atelier.integrations.jira import JiraClient

    jira = jira or JiraClient()
    if not getattr(jira, "enabled", True):
        raise RuntimeError("Jira non configuré (Paramètres › Connexions).")
    issues = jira.rechercher(jql, ["summary", "issuetype"], 50)
    return {"nombre": len(issues), "plafond": len(issues) >= 50,
            "exemples": [{"cle": i["key"], "resume": (i.get("fields") or {}).get("summary", ""),
                          "type": ((i.get("fields") or {}).get("issuetype") or {}).get("name", "")} for i in issues[:8]]}
