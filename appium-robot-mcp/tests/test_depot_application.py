"""Code des tests au niveau de l'APPLICATION : chaque application a son dépôt (dossier, GitLab, branche) ; le code généré
y est écrit, la connaissance de l'atelier reste dans le projet. Sans dépôt déclaré : comportement historique."""
import shutil
from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"


@pytest.fixture
def env(projet, tmp_path):
    shutil.copytree(DEMO, projet, dirs_exist_ok=True, ignore=shutil.ignore_patterns("results", "connaissance", "strategie"))
    depot = tmp_path / "depot_app"
    depot.mkdir()
    return projet, depot


def test_sans_depot_rien_ne_change(env):
    from atelier.domain import projet

    p, _ = env
    assert projet.racine_code() == projet.PROJECT_DIR
    assert projet.safe_path("tests/connexion.robot") == (p / "tests" / "connexion.robot").resolve()


def test_routage_code_et_connaissance(env):
    from atelier.discovery import carte
    from atelier.domain import projet

    p, depot = env
    carte.maj_app(None, depot=carte.normaliser_depot({"dossier": str(depot), "gitlab_url": "https://gitlab.exemple/",
                                                     "gitlab_projet": "/qa/banque-tests/", "branche": "develop"}))
    assert projet.racine_code() == depot.resolve()
    assert projet.safe_path("tests/x.robot") == (depot / "tests" / "x.robot").resolve()           # code : dépôt de l'application
    assert projet.safe_path("data/jdd/recette.yaml").parent == (depot / "data" / "jdd").resolve()
    assert projet.safe_path("bdd/x.feature") == (p / "bdd" / "x.feature").resolve()               # connaissance : projet
    assert projet.safe_path("app_map").is_relative_to(p.resolve())
    assert projet.relatif(depot / "tests" / "a.robot") == "tests/a.robot"
    assert projet.relatif(p / "bdd" / "b.feature") == "bdd/b.feature"
    with pytest.raises(ValueError):
        projet.safe_path("../../ailleurs.txt")
    from atelier.integrations.gitlab import _cible

    assert _cible() == ("https://gitlab.exemple", "qa/banque-tests")                              # GitLab de l'application


def test_generation_ecrite_dans_le_depot_de_l_application(env):
    from atelier.discovery import carte
    from atelier.execution import depot_robot
    from atelier.generation import bdd

    p, depot = env
    carte.maj_app(None, depot={"dossier": str(depot)})
    assert depot_robot.lire_depot()["tests"] == {}                       # dépôt de l'application encore vide
    m = bdd.charger("DEMO-301")
    g = bdd.generer_robot(m, depot_robot.lire_depot(), type_app="web")
    bdd.ecrire_generation(m, g)
    assert (depot / g["chemin"]).is_file() and not (p / g["chemin"]).exists()
    assert any((depot / "resources").rglob("*.resource"))               # pages et locators avec le test
    assert (p / "bdd" / "DEMO-301.yaml").exists() or (p / "bdd" / "DEMO-301.feature").exists()   # le scénario reste au projet


def test_validation_et_route(env, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from web_app_loader import charger_app_web, module_web

    from atelier.discovery import carte

    with pytest.raises(ValueError, match="https"):
        carte.normaliser_depot({"gitlab_url": "http://gitlab.exemple"})
    with pytest.raises(ValueError, match="Jira"):
        carte.normaliser_jira_projets("TAM, 12x")
    assert carte.normaliser_jira_projets("tam, SIMPLE ,tam") == ["TAM", "SIMPLE"]
    _, depot = env
    monkeypatch.setattr(module_web(), "CONFIG_PATH", tmp_path / "atelier.json")
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    c.get("/qaflow")
    r = c.post("/api/apps/maj", json={"projet_xray": "tam", "jira_projets": "TAM, SIMPLE", "android": {"app_package": "com.exemple.app"},
                                      "ios": {"bundle_id": "com.exemple.app"}, "depot": {"dossier": str(depot), "branche": "develop"}})
    assert r.status_code == 200, r.text
    a = carte.config_app()
    assert a["projet_xray"] == "TAM" and a["jira_projets"] == ["TAM", "SIMPLE"] and a["depot"]["branche"] == "develop"
    assert a["android"]["app_package"] == "com.exemple.app" and a["ios"]["bundle_id"] == "com.exemple.app"
    assert c.post("/api/apps/maj", json={"depot": {"gitlab_url": "http://non-securise"}}).status_code == 400
