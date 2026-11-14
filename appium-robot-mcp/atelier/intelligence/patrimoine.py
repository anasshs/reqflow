"""Lecture du patrimoine de tests Xray (scénarios, candidats à l'automatisation)."""
from __future__ import annotations

from atelier.integrations.xray import XrayClient


def xray_get_test(test_key: str) -> dict:
    """Test Xray : type, scénario Gherkin (Cucumber) ou étapes manuelles, libellés."""
    q = ('query($jql: String) { getTests(jql: $jql, limit: 1) { results { issueId gherkin unstructured '
         'testType { name kind } steps { action data result } '
         'jira(fields: ["key", "summary", "labels", "description"]) } } }')
    res = XrayClient().gql(q, {"jql": f'key = "{test_key.upper()}"'})["getTests"]["results"]
    if not res:
        raise KeyError(f"Test {test_key} introuvable dans Xray.")
    t = res[0]
    jira = t.get("jira") or {}
    return {"cle": jira.get("key"), "resume": jira.get("summary"), "libelles": jira.get("labels"),
            "type": (t.get("testType") or {}).get("name"), "gherkin": t.get("gherkin"),
            "etapes": t.get("steps") or [], "generique": t.get("unstructured"),
            "description": jira.get("description")}


def xray_search_tests(jql: str, limit: int = 50) -> list[dict]:
    return XrayClient().search_tests(jql, limit)
