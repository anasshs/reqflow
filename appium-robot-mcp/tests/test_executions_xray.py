"""Test Executions Xray : lecture par introspection (rien de supposé), copie locale, rapprochement avec le dépôt Robot."""
import pytest

from atelier.integrations.xray import XrayClient


class FauxSchema(XrayClient):
    """Client Xray sans réseau : schéma et réponses GraphQL simulés."""

    def __init__(self, schema: dict, pages: list[dict]):
        self.schema, self.pages, self.requetes = schema, pages, []

    def _type_champs(self, nom: str) -> dict:
        return {c: {"args": {a: False for a in args}} for c, args in self.schema.get(nom, {}).items()}

    def gql(self, query, variables=None):
        self.requetes.append((query, variables))
        return {"getTestExecutions": self.pages.pop(0)}


SCHEMA = {"Query": {"getTestExecutions": ["jql", "limit", "start"]},
          "TestExecution": {"issueId": [], "jira": ["fields"], "tests": ["limit"], "testRuns": ["limit"], "testEnvironments": []},
          "TestRun": {"status": [], "test": [], "finishedOn": []}}


def _exec(cle, runs, envs=("recette",)):
    return {"issueId": cle.split("-")[1], "jira": {"key": cle, "summary": f"TNR {cle}", "status": {"name": "Done"}, "created": "2026-11-10"},
            "testEnvironments": list(envs), "tests": {"total": len(runs), "results": [{"jira": {"key": k}} for k in runs]},
            "testRuns": {"total": len(runs), "results": [{"status": {"name": s}, "test": {"jira": {"key": k}}, "finishedOn": "2026-11-10T10:00"} for k, s in runs.items()]}}


def test_client_executions_par_introspection():
    x = FauxSchema(SCHEMA, [{"total": 2, "results": [_exec("DEMO-90", {"DEMO-1": "FAILED", "DEMO-2": "PASSED"}), _exec("DEMO-80", {"DEMO-1": "PASSED"})]}])
    r = x.executions("DEMO")
    q = x.requetes[0][0]
    assert "testRuns(limit: 100)" in q and "testEnvironments" in q and "ORDER BY created DESC" in x.requetes[0][1]["jql"]
    e = r["executions"][0]
    assert e["cle"] == "DEMO-90" and e["runs"]["DEMO-1"]["statut"] == "FAILED" and e["environnements"] == ["recette"] and not r["absents"]


def test_champ_absent_signale_jamais_suppose():
    schema = {**SCHEMA, "TestExecution": {"issueId": [], "jira": ["fields"], "tests": []}}
    x = FauxSchema(schema, [{"total": 1, "results": [{"issueId": "1", "jira": {"key": "DEMO-90"}, "tests": {"results": [{"jira": {"key": "DEMO-1"}}]}}]}])
    r = x.executions("DEMO")
    assert "testRuns" not in x.requetes[0][0] and "TestExecution.testRuns" in r["absents"] and r["executions"][0]["tests"] == ["DEMO-1"]
    assert FauxSchema({"Query": {}}, []).executions("DEMO")["absents"] == ["getTestExecutions"]


@pytest.fixture
def projet(tmp_path, monkeypatch):
    from atelier.domain import projet as p
    from atelier.intelligence import patrimoine_xray

    monkeypatch.setattr(p, "PROJECT_DIR", tmp_path)
    patrimoine_xray.enregistrer({"projet": "DEMO", "tests": [{"cle": "DEMO-1"}, {"cle": "DEMO-2"}, {"cle": "DEMO-3"}], "exigences": []}, "test")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "tnr.robot").write_text("*** Test Cases ***\nT1\n    [Tags]    DEMO-1\n    Log    a\nT2\n    [Tags]    DEMO-2\n    Log    b\n", "utf-8")
    return patrimoine_xray


def test_import_et_rapprochement_depot(projet):
    from atelier.execution import centre

    class Faux:
        def executions(self, projet_cle, limite):
            assert projet_cle == "DEMO"
            return {"executions": [{"cle": "DEMO-90", "resume": "TNR sprint 12", "statut": "Done", "cree": "", "environnements": ["recette"],
                                    "tests": ["DEMO-1", "DEMO-2", "DEMO-3"], "tests_total": 3,
                                    "runs": {"DEMO-1": {"statut": "FAILED"}, "DEMO-2": {"statut": "PASSED"}, "DEMO-3": {"statut": "FAILED"}}},
                                   {"cle": "DEMO-80", "resume": "TNR sprint 11", "statut": "Done", "cree": "", "environnements": [],
                                    "tests": ["DEMO-1"], "tests_total": 1, "runs": {"DEMO-1": {"statut": "PASSED"}}}], "absents": []}

    r = projet.importer_executions("DEMO", Faux())
    assert r["nombre"] == 2
    t1 = next(t for t in projet.charger()["tests"] if t["cle"] == "DEMO-1")
    assert t1["executions"] == ["DEMO-90", "DEMO-80"] and t1["statut_xray"]["statut"] == "FAILED" and t1["statut_xray"]["execution"] == "DEMO-90"
    e = centre.executions_xray()["executions"][0]
    assert e["automatises"] == ["DEMO-1", "DEMO-2"] and e["non_automatises"] == ["DEMO-3"] and e["echecs"] == ["DEMO-1", "DEMO-3"]
    ref = {t["cle_xray"]: t for t in centre.referentiel()}
    assert ref["DEMO-1"]["statut_xray"] == "FAILED" and "DEMO-90" in ref["DEMO-1"]["executions"]


def test_indicateurs_xray_de_la_vue_d_ensemble(projet):
    from atelier.execution import centre

    class Faux:
        def executions(self, projet_cle, limite):
            return {"executions": [
                {"cle": "DEMO-90", "resume": "TNR sprint 12", "statut": "Done", "cree": "2026-11-12", "environnements": ["recette"],
                 "tests": ["DEMO-1", "DEMO-2", "DEMO-3"], "tests_total": 3,
                 "runs": {"DEMO-1": {"statut": "FAILED"}, "DEMO-2": {"statut": "PASSED"}, "DEMO-3": {"statut": "TO DO"}}},
                {"cle": "DEMO-80", "resume": "TNR sprint 11", "statut": "Done", "cree": "2026-11-01", "environnements": [],
                 "tests": ["DEMO-1", "DEMO-3"], "tests_total": 2, "runs": {"DEMO-1": {"statut": "PASSED"}, "DEMO-3": {"statut": "ABORTED"}}}], "absents": []}

    assert centre.vue_xray()["import"]["date"] is None  # rien d'importé : aucun chiffre inventé
    projet.importer_executions("DEMO", Faux())
    v = centre.vue_xray()
    k = v["kpi"]
    assert (k["executions"], k["runs"], k["reussi"], k["echec"], k["non_execute"]) == (2, 5, 2, 2, 1) and k["taux_reussite"] == 50.0
    # dernier statut par test : l'exécution la plus récente qui l'a exécuté (DEMO-1 échoue en 12, DEMO-3 non exécuté en 12 -> ABORTED en 11)
    assert (k["tests_en_echec"], k["tests_reussis"]) == (2, 1)
    assert [e["cle"] for e in v["recentes"]] == ["DEMO-90", "DEMO-80"] and v["recentes"][0]["taux"] == 50.0 and v["recentes"][0]["automatises"] == 2
    assert [t["cle"] for t in v["tendance"]] == ["DEMO-80", "DEMO-90"] and v["par_statut"]["PASSED"] == 2


def test_plus_de_100_tests_pagination_des_runs():
    class Pagine(FauxSchema):
        def gql(self, query, variables=None):
            self.requetes.append((query, variables))
            if "getTestRuns" in query:  # pages suivantes : 250 runs au total
                s = variables["s"]
                return {"getTestRuns": {"total": 250, "results": [{"status": {"name": "PASSED"}, "test": {"jira": {"key": f"DEMO-{i}"}}}
                                                                   for i in range(s, min(s + 100, 250))]}}
            runs = [{"status": {"name": "FAILED"}, "test": {"jira": {"key": f"DEMO-{i}"}}} for i in range(100)]
            return {"getTestExecutions": {"total": 1, "results": [{"issueId": "9", "jira": {"key": "DEMO-900", "created": "2026-11-10"},
                                                                    "tests": {"total": 250, "results": []}, "testRuns": {"total": 250, "results": runs}}]}}

    schema = {**SCHEMA, "Query": {"getTestExecutions": ["jql", "limit", "start"], "getTestRuns": ["testExecIssueIds", "limit", "start"]}}
    x = Pagine(schema, [])
    r = x.executions("DEMO", 50, depuis="2026-11-01", jusqu="2026-11-30")
    assert 'created >= "2026-11-01"' in x.requetes[0][1]["jql"] and 'created <= "2026-11-30 23:59"' in x.requetes[0][1]["jql"]
    e = r["executions"][0]
    assert len(e["runs"]) == 250 and len(e["tests"]) == 250 and not e["incomplete"]
    # schéma sans pagination des runs : exécution marquée incomplète, jamais complétée en silence
    x2 = Pagine({**SCHEMA}, [])
    e2 = x2.executions("DEMO")["executions"][0]
    assert e2["incomplete"] and len(e2["runs"]) == 100


def test_periode_import_conserve_et_filtre(projet):
    from atelier.execution import centre

    def faux(execs):
        class F:
            def executions(self, projet_cle, limite, depuis="", jusqu=""):
                return {"executions": execs, "absents": []}
        return F()

    e = lambda cle, jour, st: {"cle": cle, "resume": cle, "statut": "Done", "cree": jour, "environnements": [], "tests": ["DEMO-1"],  # noqa: E731
                               "tests_total": 1, "runs": {"DEMO-1": {"statut": st}}}
    projet.importer_executions("DEMO", faux([e("DEMO-80", "2026-09-01T10:00", "PASSED")]))
    r = projet.importer_executions("DEMO", faux([e("DEMO-90", "2026-11-10T10:00", "FAILED")]), depuis="2026-11-01")
    assert r["lues"] == 1 and r["nombre"] == 2  # l'ancienne exécution, hors période, est conservée
    assert centre.vue_xray(depuis="2026-11-01")["kpi"]["executions"] == 1
    assert centre.vue_xray()["kpi"]["executions"] == 2
    with pytest.raises(ValueError, match="AAAA-MM-JJ"):
        projet.importer_executions("DEMO", faux([]), depuis="01/11/2026")


def test_identifiant_du_run_lu_si_expose():
    schema = {**SCHEMA, "TestRun": {"id": [], "status": [], "test": [], "finishedOn": []}}
    e = _exec("DEMO-90", {"DEMO-1": "FAILED"})
    e["testRuns"]["results"][0]["id"] = "run-abc"
    x = FauxSchema(schema, [{"total": 1, "results": [e]}])
    r = x.executions("DEMO")
    assert "testRuns(limit: 100) { total results { id " in x.requetes[0][0] and r["executions"][0]["runs"]["DEMO-1"]["id"] == "run-abc"


def test_changer_statut_depuis_le_tableau_de_bord(projet):
    from atelier.execution import centre

    projet._fusionner_executions(d := projet.charger(), {"executions": [
        {"cle": "DEMO-90", "resume": "TNR", "statut": "En cours", "cree": "2026-11-10", "environnements": [], "tests": ["DEMO-1", "DEMO-2"], "tests_total": 2,
         "runs": {"DEMO-1": {"statut": "FAILED", "id": "r1"}, "DEMO-2": {"statut": "TO DO", "id": ""}}}]})
    projet.enregistrer(d, "test")
    date = projet.charger()["executions_xray"]["date"]

    class Faux:
        appels = []

        def set_status(self, run_id, statut):
            self.appels.append((run_id, statut))

    x = Faux()
    r = projet.changer_statut_run("DEMO-90", "DEMO-1", "PASSED", xray=x)
    assert x.appels == [("r1", "PASSED")] and r["avant"] == "FAILED"
    d = projet.charger()
    assert next(t for t in d["tests"] if t["cle"] == "DEMO-1")["statut_xray"]["statut"] == "PASSED" and d["executions_xray"]["date"] == date
    det = centre.detail_execution_xray("DEMO-90")
    assert [(r["test"], r["statut"], r["modifiable"], r["automatise"]) for r in det["runs"]] == [("DEMO-1", "PASSED", True, True), ("DEMO-2", "TO DO", False, True)]
    with pytest.raises(ValueError, match="Actualiser"):
        projet.changer_statut_run("DEMO-90", "DEMO-2", "PASSED", xray=x)  # import ancien : pas d'identifiant, rien n'est écrit
    with pytest.raises(KeyError):
        projet.changer_statut_run("DEMO-99", "DEMO-1", "PASSED", xray=x)
    assert len(x.appels) == 1
    projet.maj_statut_execution("DEMO-90", "Terminé")
    assert centre.detail_execution_xray("DEMO-90")["statut"] == "Terminé"
