"""Configuration de l'application : JQL des Test Plans et Test Executions ; campagne rattachée à un Test Plan Xray."""
import pytest

from tests.test_executions_xray import SCHEMA, FauxSchema, _exec


@pytest.fixture
def app_demo(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.domain import projet, projets
    from atelier.intelligence import patrimoine_xray

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(projets, "cle_xray", lambda: "DEMO")
    carte.creer_app("Banque Mobile", ["android"])
    patrimoine_xray.enregistrer({"projet": "DEMO", "tests": [{"cle": "DEMO-1"}], "exigences": []}, "test")
    return carte.app_courante()


def test_jql_conteneurs_deduites_puis_enregistrees(app_demo):
    from atelier.intelligence import source_tests

    s = source_tests.source()
    assert s["plans_deduite"] and s["jql_plans"].startswith('project = "DEMO" AND issuetype = "Test Plan"')
    source_tests.enregistrer_conteneurs(app_demo, 'project = DEMO AND component = Mobile ORDER BY key', "")
    source_tests.enregistrer(app_demo, 'project = DEMO AND issuetype = Test')  # la JQL des tests ne les efface pas
    s = source_tests.source()
    assert not s["plans_deduite"] and s["executions_deduite"] and "component = Mobile" in s["jql_plans"]
    assert source_tests.jql_pour_xray(s["jql_plans"]) == "project = DEMO AND component = Mobile"


def test_executions_lues_avec_la_jql_de_l_application(app_demo):
    from atelier.execution import centre
    from atelier.intelligence import patrimoine_xray, source_tests

    source_tests.enregistrer_conteneurs(app_demo, "", 'project = DEMO AND component = Mobile ORDER BY created')
    x = FauxSchema(SCHEMA, [{"total": 1, "results": [_exec("DEMO-90", {"DEMO-1": "PASSED"})]}])
    patrimoine_xray.importer_executions(xray=x)
    assert x.requetes[0][1]["jql"] == "(project = DEMO AND component = Mobile) ORDER BY created DESC"
    d = patrimoine_xray.charger()
    d["executions"].append({"cle": "DEMO-70", "resume": "Autre app", "cree": "2026-11-10", "tests": ["DEMO-1"], "runs": {"DEMO-1": {"statut": "FAILED"}}})
    patrimoine_xray.enregistrer(d, "test")
    v = centre.vue_xray()
    assert v["filtre_executions"] == "jql" and [e["cle"] for e in v["recentes"]] == ["DEMO-90"]  # DEMO-70 non lue par la JQL de l'app


def test_plans_de_l_application():
    from atelier.integrations.xray import XrayClient

    class Faux(XrayClient):
        def __init__(self):
            self.jql = []

        def _type_champs(self, nom):
            return {"Query": {"getTestPlans": {"args": {"jql": False, "limit": False}}, "getTestSets": {"args": {}}}}.get(nom, {})

        def gql(self, q, v=None):
            assert "getTestSets" not in q
            self.jql.append(v["jql"])
            return {"getTestPlans": {"total": 1, "results": [{"issueId": "5", "jira": {"key": "DEMO-50", "summary": "Release 3", "status": {"name": "Open"}}}]}}

    x = Faux()
    r = x.conteneurs("DEMO", 300, jql_plans="project = DEMO AND component = Mobile", seulement=("plans",))
    assert x.jql == ["project = DEMO AND component = Mobile"] and r["plans"][0]["cle"] == "DEMO-50" and r["test_sets"] == []


def test_campagne_rattachee_au_plan(app_demo):
    from atelier.execution import centre

    c = centre.enregistrer_campagne({"nom": "TNR", "plateformes": ["web"], "plan_xray": "demo-50"})[0]
    assert c["plan_xray"] == "DEMO-50" and c["xray_ticket"] == "DEMO-50" and c["mode_execution"] == "nouvelle"
    assert centre.params_campagne(c, "web")["xray_ticket"] == "DEMO-50"  # chaque run : nouvelle exécution rattachée au plan
    c = centre.enregistrer_campagne({**c, "mode_execution": "reutiliser", "execution_xray": "DEMO-91"})[0]
    assert c["xray_ticket"] == "DEMO-91" and c["plan_xray"] == "DEMO-50"
    with pytest.raises(ValueError, match="obligatoire"):
        centre.enregistrer_campagne({**c, "mode_execution": "reutiliser", "execution_xray": ""})
    with pytest.raises(ValueError, match="invalide"):
        centre.enregistrer_campagne({**c, "plan_xray": "pas une clé", "mode_execution": "nouvelle"})
    ancienne = centre.enregistrer_campagne({"nom": "Ancienne", "plateformes": ["web"], "xray_ticket": "DEMO-12"})[-1]
    assert ancienne["xray_ticket"] == "DEMO-12"  # ancien champ libre gardé


def test_creer_plan_pour_la_campagne(app_demo):
    from atelier.execution import centre

    class Faux:
        def test_ids(self, cles):
            return {k: "1" + k[-1] for k in cles if k != "DEMO-9"}

        def create_plan(self, projet, resume, ids):
            self.appel = (projet, resume, ids)
            return "77", "DEMO-77"

    x = Faux()
    r = centre.creer_plan_campagne("TNR sprint 12", ["DEMO-1", "DEMO-9"], xray=x)
    assert r == {"cle": "DEMO-77", "tests": ["DEMO-1"], "absents": ["DEMO-9"]} and x.appel == ("DEMO", "Campagne – TNR sprint 12", ["11"])
    with pytest.raises(ValueError):
        centre.creer_plan_campagne(" ", [], xray=x)
