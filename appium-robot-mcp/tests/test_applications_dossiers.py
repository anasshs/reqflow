"""Plusieurs applications dans un projet Xray : chacune rattachée à un ou plusieurs dossiers du Test Repository."""
import pytest


@pytest.fixture
def projet_xray(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.domain import projet
    from atelier.intelligence import patrimoine_xray

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    tests = [{"cle": "DEMO-1", "dossier": "/Mobile/Android", "exigences": ["DEMO-50"]}, {"cle": "DEMO-2", "dossier": "/Mobile"},
             {"cle": "DEMO-3", "dossier": "/Web/Connexion", "exigences": ["DEMO-60"]}, {"cle": "DEMO-4", "dossier": "/Mobile2"},
             {"cle": "DEMO-5"}]
    exig = [{"cle": "DEMO-50", "type": "user_story", "resume": "Virement mobile"}, {"cle": "DEMO-60", "type": "user_story", "resume": "Connexion web"}]
    patrimoine_xray.enregistrer({"projet": "DEMO", "tests": tests, "exigences": exig,
                                 "definitions_xray": {"date": "2026-11-14T10:00:00"}}, "test")
    return carte, patrimoine_xray


def test_dossiers_du_repository(projet_xray):
    carte, px = projet_xray
    carte.creer_app("Banque Mobile", ["android"], tests_xray={"dossiers": ["Mobile/", " /Mobile "]})
    r = px.dossiers_repository()
    par = {d["chemin"]: d for d in r["dossiers"]}
    assert par["/"]["tests"] == 4 and par["/Mobile"]["tests"] == 2 and par["/Web/Connexion"]["profondeur"] == 2
    assert par["/Mobile"]["applications"] == ["Banque Mobile"] and r["tests_sans_dossier"] == 1
    assert carte.config_app()["tests_xray"] == {"dossiers": ["/Mobile"]}


def test_filtre_par_dossier_et_sous_dossiers(projet_xray):
    carte, px = projet_xray
    carte.creer_app("Banque Web", ["web"], web={"url": "https://recette.exemple.fr"}, type_="web", tests_xray={"dossiers": ["/Web"]})
    v = px.charger_vue()
    assert [t["cle"] for t in v["tests"]] == ["DEMO-3"] and [e["cle"] for e in v["exigences"]] == ["DEMO-60"]
    carte.creer_app("Banque Mobile", ["android"], tests_xray={"dossiers": ["/Mobile"]})  # devient active
    assert [t["cle"] for t in px.charger_vue()["tests"]] == ["DEMO-1", "DEMO-2"]  # pas /Mobile2
    carte.creer_app("Tout", ["android"], tests_xray={})
    assert len(px.charger_vue()["tests"]) == 5  # repository dédié : tout le projet


def test_dossiers_prioritaires_et_fusion(projet_xray):
    carte, _ = projet_xray
    tx = carte.normaliser_tests_xray({"dossiers": ["/Mobile"], "valeurs": ["App Mobile"]})
    assert tx == {"dossiers": ["/Mobile"], "valeurs": ["App Mobile"]}
    assert carte.normaliser_tests_xray({"dossiers": [], "valeurs": []}) == {}
    assert carte.normaliser_tests_xray({"composant": "Mobile"}) == {"composant": "Mobile"}
