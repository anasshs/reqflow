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
               "executions", "type_jira", "issueId", "etapes", "gherkin", "definition", "dossier", "preconditions")


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
            "projet": d.get("projet"), "nb_tests": len(d["tests"]), "nb_exigences": len(d.get("exigences", [])),
            "tronque": d.get("tronque", ""),
            "definitions_xray": d.get("definitions_xray")}


# =========================================================================== synchronisation Jira
TYPES_XRAY = {"test", "test execution", "test plan", "test set", "precondition", "pre-condition", "précondition",
              "sub test execution", "exécution de test", "plan de test"}


def _objet_xray(issue: dict) -> bool:
    """Ticket lié de type Xray (ou de type inconnu : prudence, il n'est pas compté comme exigence)."""
    nom = (((issue.get("fields") or {}).get("issuetype") or {}).get("name") or "").strip().lower()
    types = TYPES_XRAY | {t.strip().lower() for t in (os.environ.get("XRAY_TEST_ISSUE_TYPE") or "").split(",") if t.strip()}
    return not nom or nom in types


def limite_import() -> int:
    """Plafond de sécurité d'un import (tickets) : PATRIMOINE_LIMITE, défaut 20 000. Un import tronqué est signalé."""
    try:
        return max(100, int(os.environ.get("PATRIMOINE_LIMITE") or 20000))
    except ValueError:
        return 20000


def _par_lots(jira, cles: list[str], champs: list[str], taille: int = 100) -> list[dict]:
    """« key in (…) » découpé par lots : un JQL avec des milliers de clés est refusé par Jira."""
    out = []
    for i in range(0, len(cles), taille):
        out += jira.rechercher(f"key in ({', '.join(cles[i:i + taille])})", champs, taille)
    return out


def synchroniser_jira(projet_cle: str, jql_tests: str = "", jira=None, limite: int | None = None) -> dict:
    """Instantané depuis Jira Cloud (recherche JQL) : tests, exigences liées, epics parents.

    Champs lus (à vérifier, voir docs/XRAY_API.md) : summary, issuetype, labels, status, components,
    priority, issuelinks, parent. Module = premier composant, sinon libellé « module:<nom> ».
    Lien test -> exigence : liens d'issue dont le type contient « test » (lien « Test » de Xray)."""
    from atelier.integrations.jira import JiraClient

    proteger_depot_outil()
    jira = jira or JiraClient()
    if not jira.enabled:
        raise RuntimeError("JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN non configurés.")
    type_test = os.environ.get("XRAY_TEST_ISSUE_TYPE", "Test")
    jql = jql_tests or f'project = "{projet_cle}" AND issuetype = "{type_test}"'
    champs = ["summary", "issuetype", "labels", "status", "components", "priority", "issuelinks", "parent"]
    limite = limite or limite_import()
    issues = jira.rechercher(jql, champs, limite)
    tronque = bool(getattr(jira, "tronque", False))
    if not issues:  # rien trouvé : diagnostic, et l'instantané existant n'est jamais écrasé par un résultat vide
        types = sorted({(i["fields"].get("issuetype") or {}).get("name", "?")
                        for i in jira.rechercher(f'project = "{projet_cle}"', ["issuetype"], 200)})
        raise ValueError(f"Aucun ticket pour « {jql} » (instantané inchangé). "
                         + (f"Types de tickets présents dans {projet_cle} : {', '.join(types)}. Si les tests Xray ont un autre nom de type, "
                            f"le préciser dans XRAY_TEST_ISSUE_TYPE ou dans le JQL. Autre voie : Test Design › « Importer les définitions Xray », "
                            "qui interroge directement Xray." if types else
                            f"Aucun ticket visible dans {projet_cle} avec ce compte Jira : vérifier l'e-mail, le jeton et les droits « Parcourir les projets »."))
    tests, ids_exigences = [], set()
    for i in issues:
        f = i["fields"]
        liees = [lien.get("outwardIssue") or lien.get("inwardIssue") for lien in f.get("issuelinks") or []
                 if "test" in ((lien.get("type") or {}).get("name") or "").lower()]
        # une exigence est une US / epic / bug… jamais un objet Xray (Test, Test Execution, Test Plan, Test Set, précondition)
        exig = sorted({x["key"] for x in liees if x and not _objet_xray(x)})
        ids_exigences |= set(exig)
        tests.append({"cle": i["key"], "resume": f.get("summary"), "type": (f.get("issuetype") or {}).get("name"),
                      "module": _module(f), "libelles": f.get("labels") or [],
                      "statut": (f.get("status") or {}).get("name"),
                      "criticite": (f.get("priority") or {}).get("name"), "exigences": exig})
    exigences, epics = [], set()
    champ_criteres = os.environ.get("JIRA_CHAMP_CRITERES", "").strip()  # ex. customfield_10050 (critères d'acceptation)
    champs_exig = champs + ["description"] + ([champ_criteres] if champ_criteres else [])
    if ids_exigences:
        for i in _par_lots(jira, sorted(ids_exigences), champs_exig):
            f = i["fields"]
            parent = (f.get("parent") or {}).get("key")
            exigences.append({"cle": i["key"], "type": _type_exigence(f), "type_jira": (f.get("issuetype") or {}).get("name"),
                              "resume": f.get("summary"),
                              "parent": parent, "module": _module(f), "statut": (f.get("status") or {}).get("name"),
                              **_description_et_criteres(f, champ_criteres)})
            if parent:
                epics.add(parent)
        connues = {e["cle"] for e in exigences}
        manquants = sorted(epics - connues)
        if manquants:
            for i in _par_lots(jira, manquants, champs):
                f = i["fields"]
                exigences.append({"cle": i["key"], "type": _type_exigence(f) if f.get("issuetype") else "epic",
                                  "type_jira": (f.get("issuetype") or {}).get("name"), "resume": f.get("summary"), "parent": None,
                                  "module": _module(f), "statut": (f.get("status") or {}).get("name")})
    return enregistrer({"projet": projet_cle, "tests": tests, "exigences": exigences,
                        "tronque": f"limite de {limite} tickets atteinte (PATRIMOINE_LIMITE)" if tronque else ""}, f"Jira : {jql}")


CHAMPS_DEFINITION = ("type", "type_genre", "issueId", "etapes", "gherkin", "definition", "dossier", "preconditions")


def proteger_depot_outil():
    """Aucune donnée client dans le dépôt de l'outil : un import réel vers un dossier situé dans le dépôt de
    l'atelier (ex. le projet de démonstration) est refusé."""
    if projet.PROJECT_DIR == projet.RACINE_OUTIL or projet.RACINE_OUTIL in projet.PROJECT_DIR.parents:
        raise PermissionError(f"Le projet actif ({projet.PROJECT_DIR}) est dans le dépôt de l'atelier (démonstration) : "
                              "aucune donnée Xray / Jira réelle n'y est importée. Choisir le repository de tests réel "
                              "(Paramètres › Projets, ou ROBOT_PROJECT_DIR).")


def completer_depuis_xray(projet_cle: str = "", jql: str = "", xray=None) -> dict:
    """Mode A (import) réel : complète l'instantané avec les définitions Xray de chaque test (type Xray Manual /
    Cucumber / Generic, étapes, Gherkin, définition, dossier du Test Repository, préconditions, issueId).
    Sans instantané, les tests viennent du JQL (défaut : tous les tests du projet). Lecture seule dans Xray.
    Le type Jira d'origine est conservé (type_jira) ; un champ que le schéma n'expose pas reste absent."""
    from atelier.integrations.xray import XrayClient

    from atelier.domain import projets

    proteger_depot_outil()
    projet_cle = (projet_cle or projets.cle_xray()).upper()
    base = charger()
    if base and not base.get("tests"):
        base = {**base, "tests": []}
    if base and projet_cle and base.get("projet") and base["projet"].upper() != projet_cle and not jql:
        raise ValueError(f"L'instantané de ce repository est celui du projet {base['projet']}, pas {projet_cle} : "
                         f"vérifier le projet actif (ROBOT_PROJECT_DIR = {projet.PROJECT_DIR}).")
    xray = xray or XrayClient()
    completer = bool(base and base["tests"] and not jql)  # compléter les tests connus, sinon lister ceux du projet dans Xray
    if completer:
        d = xray.definitions_tests(cles=[t["cle"] for t in base["tests"]])
    else:
        if not (jql or projet_cle):
            raise ValueError("Projet ou JQL requis (aucun instantané à compléter).")
        d = xray.definitions_tests(jql=jql or f'project = "{projet_cle}"', limite=limite_import())
    defs = {t["cle"]: t for t in d["tests"] if t.get("cle")}
    if not defs:  # rien trouvé : l'instantané n'est pas modifié
        if not completer:
            raise ValueError(f"Aucun test Xray pour « {jql or 'project = ' + projet_cle} » : instantané inchangé.")
        raise ValueError(f"Aucun des {len(base['tests'])} tests de l'instantané n'existe dans Xray : instantané inchangé.")
    if completer:
        data, introuvables = base, []
        for t in data["tests"]:
            x = defs.get(t["cle"])
            if not x:
                introuvables.append(t["cle"])
                continue
            if t.get("type") and t.get("type") != x.get("type"):
                t["type_jira"] = t["type"]
            t.update({k: x[k] for k in CHAMPS_DEFINITION if k in x})
    else:
        data = {**(base or {}), "projet": projet_cle or (base or {}).get("projet"), "tests": list(defs.values())}
        data.setdefault("exigences", [])
        introuvables = []
    source = (data.get("source") or "").split(" + Xray")[0] if completer else ""
    data["date"] = None
    data["definitions_xray"] = {"date": datetime.now().astimezone().isoformat(timespec="seconds"), "importes": len(defs),
                                "introuvables": introuvables, "champs_absents": d["champs_absents"], "tronque": d.get("tronque", False)}
    try:  # organisation du Test Repository : best effort, n'empêche jamais l'import des définitions
        org = xray.conteneurs(projet_cle or data.get("projet") or "")
        data["plans"] = [{k: p[k] for k in ("cle", "resume", "statut", "tests", "tests_total")} for p in org["plans"]]
        data["test_sets"] = [{k: p[k] for k in ("cle", "resume", "statut", "tests", "tests_total")} for p in org["test_sets"]]
        par_test: dict = {}
        for genre in ("plans", "test_sets"):
            for p in data[genre]:
                for k in p["tests"]:
                    par_test.setdefault(k, {}).setdefault(genre, []).append(p["cle"])
        for t in data["tests"]:
            t["plans"] = sorted(set(t.get("plans") or []) | set(par_test.get(t["cle"], {}).get("plans", [])))
            t["test_sets"] = par_test.get(t["cle"], {}).get("test_sets", [])
        data["definitions_xray"]["organisation"] = {"plans": len(data["plans"]), "test_sets": len(data["test_sets"]), "absents": org["absents"]}
    except Exception as e:  # noqa: BLE001
        data["definitions_xray"]["organisation"] = {"erreur": str(e)[:300]}
    etat_ = enregistrer(data, (source + " + Xray (définitions)") if source else f"Xray : {jql or 'project = ' + projet_cle}")
    return {**etat_, **data["definitions_xray"]}


def organisation() -> dict:
    """Suites de test côté Xray : dossiers du Test Repository (depuis les définitions), Test Plans et Test Sets."""
    pat = charger() or {"tests": [], "plans": [], "executions": []}
    dossiers: dict = {}
    for t in pat["tests"]:
        if t.get("dossier") is not None:
            d = t["dossier"] or "/"
            dossiers.setdefault(d, []).append(t["cle"])
    arbre = []
    for chemin in sorted(dossiers):
        arbre.append({"chemin": chemin, "profondeur": 0 if chemin == "/" else chemin.strip("/").count("/") + 1,
                      "nom": chemin.rstrip("/").split("/")[-1] or "Racine", "tests": sorted(dossiers[chemin])})
    defs = pat.get("definitions_xray") or {}
    def normaliser(conteneurs: list[dict], champ: str) -> list[dict]:
        """Format ancien (clé et titre seulement) : tests retrouvés depuis le champ plans / test_sets des tests."""
        out = []
        for c in conteneurs:
            tests = c.get("tests") if isinstance(c.get("tests"), list) else sorted(t["cle"] for t in pat["tests"] if c["cle"] in (t.get(champ) or []))
            out.append({"cle": c["cle"], "resume": c.get("resume", ""), "statut": c.get("statut", ""), "tests": tests,
                        "tests_total": c.get("tests_total", len(tests))})
        return out

    return {"dossiers": arbre, "plans": normaliser(pat.get("plans") or [], "plans"), "test_sets": normaliser(pat.get("test_sets") or [], "test_sets"),
            "definitions_importees": bool(defs.get("date")), "date": defs.get("date"), "organisation": defs.get("organisation"),
            "tests_sans_dossier": sum(1 for t in pat["tests"] if t.get("dossier") is None)}


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
    """Catégorie d'une exigence. Le niveau hiérarchique Jira (1 = Epic) prime sur le nom du type, qui dépend de la
    langue du site (« Epic », « Épopée »…) ; le nom exact reste conservé dans « type_jira »."""
    it = f.get("issuetype") or {}
    nom = (it.get("name") or "").lower()
    niveau = it.get("hierarchyLevel")
    if (isinstance(niveau, int) and niveau >= 1) or any(m in nom for m in ("epic", "épopée", "epopee")):
        return "epic"
    if any(m in nom for m in ("bug", "bogue", "anomalie", "défaut")):
        return "bug"
    return "user_story"
