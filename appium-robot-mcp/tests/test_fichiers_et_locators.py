"""Caractérisation : accès fichiers limités au projet, capture et génération des .resource."""
from __future__ import annotations

import json

import pytest


@pytest.mark.parametrize("chemin", ["../dehors.txt", "/etc/passwd", "a/../../dehors"])
def test_safe_path_refuse_hors_projet(projet, chemin):
    import server

    with pytest.raises(ValueError):
        server._safe_path(chemin)


def test_safe_path_refuse_lien_symbolique_sortant(projet, tmp_path):
    import server

    (tmp_path / "secret.txt").write_text("x")
    try:
        (projet / "lien").symlink_to(tmp_path / "secret.txt")
    except OSError:  # Windows sans le privilège « créer des liens symboliques » : cas non reproductible sur ce poste
        pytest.skip("création de lien symbolique non autorisée sur ce poste")
    with pytest.raises(ValueError):
        server.read_project_file("lien")


def test_ecriture_sans_ecrasement_implicite(projet):
    import server

    server.write_project_file("tests/a.robot", "v1")
    with pytest.raises(FileExistsError):
        server.write_project_file("tests/a.robot", "v2")
    server.write_project_file("tests/a.robot", "v2", overwrite=True)
    assert server.read_project_file("tests/a.robot") == "v2"
    assert server.list_project_files() == ["tests/a.robot"]


def test_generation_resource_android_ios(projet):
    import server

    server.add_screen_locator("Virement saisie", "champ_montant", "id=com.exemple.banque:id/montant", "android")
    server.add_screen_locator("Virement saisie", "bouton_valider", "id=com.exemple.banque:id/valider", "android")
    server.add_screen_locator("Virement saisie", "champ_montant", "accessibility_id=amountField", "ios")
    res = server.generate_locators_resource("Virement saisie")
    assert res["manquants_ios"] == ["bouton_valider"] and res["manquants_android"] == []
    txt = (projet / "resources" / "locators" / "virement_saisie.resource").read_text("utf-8")
    assert "&{LOC_VIREMENT_SAISIE_ANDROID}    champ_montant=id=com.exemple.banque:id/montant" in txt
    assert "...    bouton_valider=id=com.exemple.banque:id/valider" in txt
    assert "# TODO ios : clés à relever -> bouton_valider" in txt
    assert "&{LOC_VIREMENT_SAISIE_IOS}    champ_montant=accessibility_id=amountField" in txt
    with pytest.raises(FileExistsError):
        server.generate_locators_resource("Virement saisie")


def test_generation_echappe_les_espaces_multiples(projet):
    import server

    server.add_screen_locator("e", "t", "xpath=//*[@text='a  b']", "android")
    server.generate_locators_resource("e")
    assert "t=xpath=//*[@text='a \\ b']" in (projet / "resources/locators/e.resource").read_text("utf-8")


def test_generation_sans_capture(projet):
    import server

    with pytest.raises(RuntimeError):
        server.generate_locators_resource("inconnu")


def test_capture_stockee_dans_les_snapshots(projet):
    import server

    server.add_screen_locator("Login", "champ_id", "data-testid=login", "web")
    data = json.loads((projet / ".mcp_snapshots" / "login_web.json").read_text("utf-8"))
    assert data["locators"] == {"champ_id": "data-testid=login"} and data["platform"] == "web"


def test_robot_escape():
    import server

    assert server._robot_escape("a\\b") == "a\\\\b"
    assert server._robot_escape("a   b") == "a \\ \\ b"
