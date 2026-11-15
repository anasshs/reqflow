"""Test Plans de l'application : exécutions du plan lues dans Xray, dernier statut par test, avancement et réussite."""
import pytest

from atelier.integrations.xray import XrayClient


class FauxXray(XrayClient):
    """getTestPlans (avec testExecutions) et getTestExecutions simulés."""

    def __init__(self, avec_execs=True):
        self.avec_execs, self.jql = avec_execs, []

    def _type_champs(self, nom):
        if nom == "Query":
            return {"getTestPlans": {"args": {"jql": False, "limit": False}}, "getTestExecutions": {"args": {"jql": False, "limit": False}}}
        if nom == "TestPlan":
            return {"tests": {"args": {"limit": False}}, **({"testExecutions": {"args": {"limit": False}}} if self.avec_execs else {})}
        if nom == "TestExecution":
            return {"testRuns": {"args": {"limit": False}}}
        if nom == "TestRun":
            return {"status": {}, "test": {}}
        return {}

    def gql(self, q, v=None):
        self.jql.append(v.get("jql"))
        if "getTestPlans" in q:
            assert ("testExecutions" in q) == self.avec_execs
            plan = {"issueId": "50", "jira": {"key": "DEMO-50", "summary": "Release 3", "status": {"name": "En cours"}, "created": "2026-11-01T09:00:00"},
                    "tests": {"total": 3, "results": [{"jira": {"key": k}} for k in ("DEMO-1", "DEMO-2", "DEMO-3")]}}
            if self.avec_execs:
                plan["testExecutions"] = {"total": 2, "results": [{"jira": {"key": "DEMO-90"}}, {"jira": {"key": "DEMO-91"}}]}
            return {"getTestPlans": {"total": 1, "results": [plan]}}
        assert v["jql"].startswith("(key in (DEMO-91))")  # seule l'exécution du plan absente de la copie locale est lue
        return {"getTestExecutions": {"total": 1, "results": [{"issueId": "91", "jira": {"key": "DEMO-91", "summary": "Relance", "status": {"name": "Done"}, "created": "2026-11-12T10:00"},
                                                              "testRuns": {"total": 1, "results": [{"status": {"name": "PASSED"}, "test": {"jira": {"key": "DEMO-1"}}}]}}]}}


@pytest.fixture
def projet(tmp_path, monkeypatch):
    from atelier.domain import projet as p, projets
    from atelier.intelligence import patrimoine_xray

    monkeypatch.setattr(p, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(projets, "cle_xray", lambda: "DEMO")
    d = {"projet": "DEMO", "tests": [{"cle": f"DEMO-{i}"} for i in (1, 2, 3)], "exigences": []}
    patrimoine_xray._fusionner_executions(d, {"executions": [
        {"cle": "DEMO-90", "resume": "TNR", "cree": "2026-11-10", "tests": ["DEMO-1", "DEMO-2"], "runs": {"DEMO-1": {"statut": "FAILED"}, "DEMO-2": {"statut": "PASSED"}}}]})
    patrimoine_xray.enregistrer(d, "test")
    return patrimoine_xray


def test_plan_avancement_et_reussite(projet):
    from atelier.execution import centre

    x = FauxXray()
    r = projet.importer_plans(xray=x)
    assert r["nombre"] == 1 and r["executions_lues"] == 1
    v = centre.vue_plans()
    p = v["plans"][0]
    # DEMO-1 : FAILED (DEMO-90) puis PASSED (DEMO-91, plus récente) -> réussi ; DEMO-2 réussi ; DEMO-3 jamais exécuté
    assert p["statuts_tests"] == {"DEMO-1": "PASSED", "DEMO-2": "PASSED", "DEMO-3": ""}
    assert (p["reussi"], p["echec"], p["non_execute"], p["taux_reussite"], p["avancement"]) == (2, 0, 1, 100.0, 66.7)
    assert p["executions"] == ["DEMO-91", "DEMO-90"] and p["statut"] == "En cours" and p["source_executions"] == "xray"
    assert v["kpi"]["plans_ouverts"] == 1 and v["kpi"]["tests"] == 3
    assert projet.charger()["executions_xray"].get("lues") is not None  # métadonnées du tableau de bord conservées


def test_plan_sans_executions_exposees_utilise_les_runs_atelier(projet):
    from atelier.execution import centre, historique

    projet.importer_plans(xray=FauxXray(avec_execs=False))
    historique.enregistrer("RUN-20261110-100000", {"target": "tests"}, {"resultat": {"passes": 1, "echecs": 1}, "xray": {"execution": "DEMO-90", "plan": "DEMO-50"}},
                           "2026-11-10T10:00:00", "2026-11-10T10:05:00")
    p = centre.vue_plans()["plans"][0]
    assert p["source_executions"] == "runs de l'atelier" and p["executions"] == ["DEMO-90"]
    assert (p["reussi"], p["echec"], p["non_execute"]) == (1, 1, 1)
