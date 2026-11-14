"""Lecture du patrimoine de tests Xray (scénarios, candidats à l'automatisation)."""
from __future__ import annotations

from atelier.integrations.xray import XrayClient


GHERKIN = ("given", "when", "then", "and", "but", "soit", "étant donné", "etant donne", "quand", "lorsque", "alors", "et ", "mais",
           "scenario", "scénario", "feature", "fonctionnalité")


def _texte_gherkin(texte: str) -> bool:
    lignes = [l.strip().lower() for l in (texte or "").splitlines() if l.strip()]
    return sum(1 for l in lignes if l.startswith(GHERKIN)) >= 2


def scenario_retenu(t: dict) -> tuple[str, str]:
    """Premier scénario non vide, dans l'ordre : Gherkin Xray (Cucumber), scénario BDD de l'atelier, étapes Xray
    (Manual), définition Generic, description Jira écrite en Given / When / Then. Renvoie (texte, source)."""
    if (t.get("gherkin") or "").strip():
        return t["gherkin"], "Xray (test Cucumber)"
    if (t.get("bdd_local") or "").strip():
        return t["bdd_local"], "Construction BDD de l'atelier"
    if t.get("etapes"):
        return "\n".join(f"{i + 1}. {s.get('action') or ''}" + (f" — {s['data']}" if s.get("data") else "")
                         + (f" → {s['result']}" if s.get("result") else "") for i, s in enumerate(t["etapes"])), "Xray (étapes Manual)"
    if (t.get("generique") or "").strip():
        return t["generique"], "Xray (définition Generic)"
    if _texte_gherkin(t.get("description_texte", "")):
        return t["description_texte"], "description Jira (Given / When / Then)"
    return "", ""


def xray_get_test(test_key: str) -> dict:
    """Test Xray : type, scénario Gherkin (Cucumber) ou étapes manuelles, libellés. Complété par le scénario BDD de
    l'atelier et la description Jira ; si Xray ne répond pas, la copie locale (définitions importées) est utilisée.
    « scenario » / « source_scenario » : le scénario à afficher et d'où il vient."""
    from atelier.generation import bdd
    from atelier.integrations.jira import adf_vers_texte

    cle = test_key.upper()
    q = ('query($jql: String) { getTests(jql: $jql, limit: 1) { results { issueId gherkin unstructured '
         'testType { name kind } steps { action data result } '
         'jira(fields: ["key", "summary", "labels", "description"]) } } }')
    erreur = ""
    try:
        res = XrayClient().gql(q, {"jql": f'key = "{cle}"'})["getTests"]["results"]
    except Exception as e:  # noqa: BLE001 - Xray indisponible : copie locale
        res, erreur = None, str(e)[:300]
    local_bdd = bdd.charger(cle)
    if res:
        t = res[0]
        jira = t.get("jira") or {}
        out = {"cle": jira.get("key"), "resume": jira.get("summary"), "libelles": jira.get("labels"),
               "type": (t.get("testType") or {}).get("name"), "gherkin": t.get("gherkin"),
               "etapes": [{"action": s.get("action") or "", "data": s.get("data") or "", "result": s.get("result") or ""} for s in t.get("steps") or []],
               "generique": t.get("unstructured"), "description": jira.get("description")}
    else:
        from atelier.intelligence import patrimoine_xray

        snap = next((x for x in (patrimoine_xray.charger() or {"tests": []})["tests"] if x["cle"] == cle), None)
        if not snap and not local_bdd:
            raise KeyError(f"Test {test_key} introuvable dans Xray." + (f" ({erreur})" if erreur else ""))
        snap = snap or {}
        out = {"cle": cle, "resume": snap.get("resume") or (local_bdd or {}).get("titre", ""), "libelles": snap.get("libelles"),
               "type": snap.get("type"), "gherkin": snap.get("gherkin"),
               "etapes": [{"action": e.get("action", ""), "data": e.get("donnees", ""), "result": e.get("resultat", "")} for e in snap.get("etapes") or []],
               "generique": snap.get("definition"), "description": None,
               "avertissement": "Xray non joignable : copie locale affichée." if erreur else "Test absent de Xray : scénario de l'atelier."}
    d = out.get("description")
    out["description_texte"] = adf_vers_texte(d) if isinstance(d, (dict, list)) else (d or "")
    if local_bdd:
        out["bdd_local"] = bdd.serialiser(local_bdd)
    out["scenario"], out["source_scenario"] = scenario_retenu(out)
    return out


def xray_search_tests(jql: str, limit: int = 50) -> list[dict]:
    return XrayClient().search_tests(jql, limit)
