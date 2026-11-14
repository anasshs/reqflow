"""Instantané du patrimoine Xray / Jira (exigences, tests, plans, exécutions).

Les graphes de couverture se construisent sur un instantané daté, stocké dans le projet de tests
(`patrimoine/xray.json`), jamais sur des appels en direct à chaque affichage. Règle de
synchronisation explicite : l'instantané n'est remplacé que par une action « Synchroniser »
(ou un import de fichier), et son en-tête dit d'où il vient et quand.

Format (aussi accepté à l'import, ex. export préparé à la main ou par un script) :
{
  "date": "...", "source": "...", "projet": "DEMO",
  "exigences": [{"cle", "type": "epic"|"user_story", "resume", "parent", "module", "statut"}],
  "tests": [{"cle", "resume", "type", "module", "libelles", "statut", "criticite",
             "exigences": [...], "plans": [...], "executions": [...]}],
  "plans": [{"cle", "resume"}], "executions": [{"cle", "resume"}]
}
Champ absent = inconnu : il reste absent (jamais estimé).
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from atelier.domain import projet

CHAMPS_TEST = ("cle", "resume", "type", "module", "libelles", "statut", "criticite", "exigences", "plans",
               "executions")


def fichier() -> Path:
    return projet.PROJECT_DIR / os.environ.get("PATRIMOINE_FICHIER", "patrimoine/xray.json")


def charger() -> dict | None:
    f = fichier()
    return valider(json.loads(f.read_text("utf-8"))) if f.exists() else None


def valider(data: dict) -> dict:
    """Contrôle de forme minimal ; normalise les listes absentes."""
    if not isinstance(data, dict) or not isinstance(data.get("tests"), list):
        raise ValueError("Instantané invalide : liste « tests » attendue.")
    for t in data["tests"]:
        if not t.get("cle"):
            raise ValueError("Instantané invalide : chaque test a une « cle ».")
        for k in ("libelles", "exigences", "plans", "executions"):
            t.setdefault(k, [])
    for k in ("exigences", "plans", "executions"):
        data.setdefault(k, [])
    for e in data["exigences"]:
        if e.get("type") not in ("epic", "user_story", "bug"):
            raise ValueError(f"Exigence {e.get('cle')} : type epic, user_story ou bug attendu.")
    return data


def enregistrer(data: dict, source: str) -> dict:
    data = valider(dict(data))
    data["date"] = data.get("date") or datetime.now().astimezone().isoformat(timespec="seconds")
    data["source"] = source
    f = fichier()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, f)
    return etat()


def etat() -> dict:
    d = charger()
    if not d:
        return {"present": False, "fichier": str(fichier())}
    return {"present": True, "fichier": str(fichier()), "date": d.get("date"), "source": d.get("source"),
            "projet": d.get("projet"), "nb_tests": len(d["tests"]), "nb_exigences": len(d.get("exigences", []))}


# =========================================================================== synchronisation Jira
def synchroniser_jira(projet_cle: str, jql_tests: str = "", jira=None, limite: int = 1000) -> dict:
    """Instantané depuis Jira Cloud (recherche JQL) : tests, exigences liées, epics parents.

    Champs lus (à vérifier, voir docs/XRAY_API.md) : summary, issuetype, labels, status, components,
    priority, issuelinks, parent. Module = premier composant, sinon libellé « module:<nom> ».
    Lien test -> exigence : liens d'issue dont le type contient « test » (lien « Test » de Xray)."""
    from atelier.integrations.jira import JiraClient

    jira = jira or JiraClient()
    if not jira.enabled:
        raise RuntimeError("JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN non configurés.")
    type_test = os.environ.get("XRAY_TEST_ISSUE_TYPE", "Test")
    jql = jql_tests or f'project = "{projet_cle}" AND issuetype = "{type_test}"'
    champs = ["summary", "issuetype", "labels", "status", "components", "priority", "issuelinks", "parent"]
    issues = jira.rechercher(jql, champs, limite)
    tests, ids_exigences = [], set()
    for i in issues:
        f = i["fields"]
        liees = [lien.get("outwardIssue") or lien.get("inwardIssue") for lien in f.get("issuelinks") or []
                 if "test" in ((lien.get("type") or {}).get("name") or "").lower()]
        exig = sorted({x["key"] for x in liees if x})
        ids_exigences |= set(exig)
        tests.append({"cle": i["key"], "resume": f.get("summary"), "type": (f.get("issuetype") or {}).get("name"),
                      "module": _module(f), "libelles": f.get("labels") or [],
                      "statut": (f.get("status") or {}).get("name"),
                      "criticite": (f.get("priority") or {}).get("name"), "exigences": exig})
    exigences, epics = [], set()
    champ_criteres = os.environ.get("JIRA_CHAMP_CRITERES", "").strip()  # ex. customfield_10050 (critères d'acceptation)
    champs_exig = champs + ["description"] + ([champ_criteres] if champ_criteres else [])
    if ids_exigences:
        for i in jira.rechercher(f"key in ({', '.join(sorted(ids_exigences))})", champs_exig, limite):
            f = i["fields"]
            parent = (f.get("parent") or {}).get("key")
            exigences.append({"cle": i["key"], "type": _type_exigence(f), "resume": f.get("summary"),
                              "parent": parent, "module": _module(f), "statut": (f.get("status") or {}).get("name"),
                              **_description_et_criteres(f, champ_criteres)})
            if parent:
                epics.add(parent)
        connues = {e["cle"] for e in exigences}
        manquants = sorted(epics - connues)
        if manquants:
            for i in jira.rechercher(f"key in ({', '.join(manquants)})", champs, limite):
                f = i["fields"]
                exigences.append({"cle": i["key"], "type": "epic", "resume": f.get("summary"), "parent": None,
                                  "module": _module(f), "statut": (f.get("status") or {}).get("name")})
    return enregistrer({"projet": projet_cle, "tests": tests, "exigences": exigences}, f"Jira : {jql}")


def _description_et_criteres(f: dict, champ_criteres: str = "") -> dict:
    """Description (ADF -> texte) et critères d'acceptation : champ dédié s'il est configuré, sinon les puces
    qui suivent un titre « Critères d'acceptation » / « Acceptance criteria » dans la description."""
    import re as _re

    from atelier.integrations.jira import adf_vers_texte

    desc = adf_vers_texte(f.get("description"))
    brut = adf_vers_texte(f.get(champ_criteres)) if champ_criteres and f.get(champ_criteres) else ""
    if not brut:
        m = _re.search(r"(?is)(crit[eè]res? d.acceptation|acceptance criteria)\s*:?\s*\n(.*)", desc)
        brut = m.group(2) if m else ""
    criteres = [_re.sub(r"^\s*[-*•]\s*", "", l).strip() for l in brut.splitlines() if _re.match(r"^\s*[-*•]\s+\S", l)]
    out = {"description": desc[:4000]} if desc else {}
    if criteres:
        out["criteres"] = criteres
    return out


def _module(f: dict) -> str | None:
    comps = f.get("components") or []
    if comps:
        return comps[0].get("name")
    return next((lb.split(":", 1)[1] for lb in f.get("labels") or [] if lb.lower().startswith("module:")), None)


def _type_exigence(f: dict) -> str:
    nom = ((f.get("issuetype") or {}).get("name") or "").lower()
    if "epic" in nom:
        return "epic"
    if "bug" in nom:
        return "bug"
    return "user_story"
