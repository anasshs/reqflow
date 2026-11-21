"""Exécution de l'atelier = Test Execution Xray : runs qui l'alimentent, campagne et plan, relance dans la même exécution."""
import json

import pytest


@pytest.fixture
def projet(tmp_path, monkeypatch):
    from atelier.domain import projet as p
    from atelier.execution import centre, historique
    from atelier.intelligence import patrimoine_xray

    monkeypatch.setattr(p, "PROJECT_DIR", tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "tnr.robot").write_text("*** Test Cases ***\nT1\n    [Tags]    DEMO-1\n    Log    a\nT2\n    [Tags]    DEMO-2\n    Log    b\n", "utf-8")
    d = {"projet": "DEMO", "tests": [{"cle": "DEMO-1"}, {"cle": "DEMO-2"}, {"cle": "DEMO-3"}], "exigences": []}
    patrimoine_xray._fusionner_executions(d, {"executions": [
        {"cle": "DEMO-90", "resume": "TNR", "statut": "En cours", "cree": "2026-11-12", "environnements": ["android"], "tests": ["DEMO-1", "DEMO-2", "DEMO-3"],
         "runs": {"DEMO-1": {"statut": "FAILED"}, "DEMO-2": {"statut": "PASSED"}, "DEMO-3": {"statut": "FAILED"}}}]})
    patrimoine_xray.enregistrer(d, "test")
    centre.enregistrer_campagne({"id": "CAMP-A", "nom": "TNR quotidienne", "plateformes": ["android"], "plan_xray": "DEMO-50"})
    params = {"target": "tests/tnr.robot", "variables": {"PLATFORM": "android"}, "jdd_env": "recette", "campagne": "CAMP-A", "xray_ticket": "DEMO-50"}
    historique.enregistrer("RUN-20261112-100000", params, {"resultat": {"passes": 1, "echecs": 1}, "xray": {"execution": "DEMO-90", "plan": "DEMO-50"}},
                           "2026-11-12T10:00:00", "2026-11-12T10:05:00")
    historique.enregistrer("RUN-20261112-110000", {"target": "tests"}, {"resultat": {"passes": 1, "echecs": 0}}, "2026-11-12T11:00:00", "2026-11-12T11:01:00")
    return centre


def test_execution_liee_a_ses_runs_sa_campagne_et_son_plan(projet):
    d = projet.detail_execution_xray("DEMO-90")
    assert d["campagne_nom"] == "TNR quotidienne" and d["plan"] == "DEMO-50" and [r["id"] for r in d["runs_atelier"]] == ["RUN-20261112-100000"]
    e = projet.vue_xray()["recentes"][0]
    assert e["campagne"] == "CAMP-A" and e["runs_atelier"] == 1
    assert next(c for c in projet.campagnes() if c["id"] == "CAMP-A")["executions"] == ["DEMO-90"]
    assert "executions" not in json.dumps(projet._fichier_campagnes().read_text("utf-8"))  # calculé, jamais stocké


def test_relance_dans_la_meme_execution(projet):
    r = projet.params_relance("DEMO-90", echecs=True)
    assert r["params"]["xray_ticket"] == "DEMO-90" and r["params"]["include_tags"] == ["DEMO-1"] and r["non_automatises"] == ["DEMO-3"]
    assert r["params"]["target"] == "tests/tnr.robot" and r["params"]["variables"]["PLATFORM"] == "android" and r["params"]["jdd_env"] == "recette"
    assert r["campagne"] == "CAMP-A"
    assert projet.params_relance("DEMO-90")["params"]["include_tags"] == ["DEMO-1", "DEMO-2"]


def test_relance_sans_run_atelier_demande_la_plateforme(projet):
    from atelier.intelligence import patrimoine_xray

    d = patrimoine_xray.charger()
    d["executions"].append({"cle": "DEMO-95", "resume": "Manuelle", "cree": "2026-11-13", "environnements": ["Chrome"], "tests": ["DEMO-2"],
                            "runs": {"DEMO-2": {"statut": "FAILED"}}})
    d["executions"].append({"cle": "DEMO-96", "resume": "Manuelle", "cree": "2026-11-13", "tests": ["DEMO-3"], "runs": {"DEMO-3": {"statut": "TO DO"}}})
    patrimoine_xray.enregistrer(d, "test")
    with pytest.raises(ValueError, match="Plateforme"):
        projet.params_relance("DEMO-95", echecs=True)
    assert projet.params_relance("DEMO-95", echecs=True, plateforme="web")["params"]["variables"] == {"PLATFORM": "web"}
    with pytest.raises(ValueError, match="Aucun test automatisé"):
        projet.params_relance("DEMO-96", echecs=False, plateforme="web")  # que des tests manuels : rien à lancer
