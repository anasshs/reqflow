"""Données des tests : le lien test ↔ jeu de données lu dans le code, et son remplacement permanent (tests et scénarios)."""
import pytest


@pytest.fixture
def depot(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.domain import projet

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    carte.creer_app("Banque Démo", ["android"])
    (tmp_path / "data" / "jdd").mkdir(parents=True)
    (tmp_path / "data" / "jdd" / "recette.yaml").write_text(
        "CONSULTATION:\n  donnees: {identifiant: a, periode: Ce mois}\n"
        "CONSULTATION_PRO:\n  donnees: {identifiant: b, periode: Ce mois}\n"
        "LOGIN:\n  donnees: {identifiant: c}\n", "utf-8")
    d = tmp_path / "tests" / "banque_demo"
    d.mkdir(parents=True)
    (d / "compte.robot").write_text(
        "*** Test Cases ***\nFiltrer\n    [Tags]    DEMO-1\n    Initialiser Le Test    &{JDD_CONSULTATION}\n    No Operation\n"
        "Solde\n    [Tags]    DEMO-2\n    Initialiser Le Test    &{JDD_CONSULTATION}\n    No Operation\n"
        "Démo\n    No Operation\n", "utf-8")
    (d / "login.robot").write_text("*** Test Cases ***\nConnexion\n    Initialiser Le Test    &{JDD_LOGIN}\n    No Operation\n", "utf-8")
    return tmp_path


def test_lien_test_jeu(depot):
    from atelier.execution import donnees_tests as dt

    v = dt.vue("recette")
    jeux = {j["jeu"]: j for j in v["jeux"]}
    assert [t["nom"] for t in jeux["CONSULTATION"]["tests"]] == ["Filtrer", "Solde"]
    assert jeux["CONSULTATION"]["champs"] == ["identifiant", "periode"] and jeux["CONSULTATION_PRO"]["tests"] == []
    assert [t["nom"] for t in v["sans_jeu"]] == ["Démo"] and v["tests"] == 4


def test_remplacement_permanent(depot):
    from atelier.execution import donnees_tests as dt

    r = dt.remplacer("CONSULTATION", "CONSULTATION_PRO", ["tests/banque_demo/compte.robot::Solde"])   # un seul test choisi
    texte = (depot / "tests" / "banque_demo" / "compte.robot").read_text("utf-8")
    assert r["tests_modifies"] == ["tests/banque_demo/compte.robot::Solde"]
    assert texte.count("&{JDD_CONSULTATION_PRO}") == 1 and texte.count("&{JDD_CONSULTATION}") == 1
    jeux = {j["jeu"]: j for j in dt.vue("recette")["jeux"]}
    assert [t["nom"] for t in jeux["CONSULTATION_PRO"]["tests"]] == ["Solde"]
    with pytest.raises(ValueError, match="Aucun test"):
        dt.remplacer("INCONNU", "LOGIN")
    with pytest.raises(ValueError, match="différent"):
        dt.remplacer("LOGIN", "LOGIN")
