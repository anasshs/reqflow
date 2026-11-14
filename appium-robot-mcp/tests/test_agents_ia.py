"""Liaison Cursor / Claude Desktop : configuration MCP sans secret ni chemin de projet, fusion avec les autres
serveurs, règles copiées sans écrasement implicite, serveur MCP qui suit le projet actif."""
import json

import pytest


@pytest.fixture
def poste(tmp_path, monkeypatch):
    from atelier.domain import projet
    from atelier.integrations import agents_ia

    maison = tmp_path / "maison"
    maison.mkdir()
    monkeypatch.setenv("HOME", str(maison))
    monkeypatch.setenv("USERPROFILE", str(maison))
    monkeypatch.setenv("APPDATA", str(maison / "AppData"))
    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path / "tests_banque")
    (tmp_path / "tests_banque").mkdir()
    for v in ("XRAY_CLIENT_SECRET", "JIRA_API_TOKEN"):
        monkeypatch.setenv(v, "SECRET-NE-PAS-COPIER")
    return agents_ia


def test_installation_cursor_fusionne_sans_secret(poste):
    f = poste.fichier_config("cursor")
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"mcpServers": {"autre": {"command": "node"}}}), "utf-8")
    assert not poste.etat(8765)["agents"]["cursor"]["installe"]
    r = poste.installer("cursor", 8765)
    d = json.loads(f.read_text("utf-8"))
    assert set(d["mcpServers"]) == {"autre", "appium-robot"} and r["sauvegarde"].endswith(".bak")
    e = d["mcpServers"]["appium-robot"]
    assert e["args"][0].endswith("server.py") and e["env"]["WEB_EVENTS_URL"] == "http://127.0.0.1:8765/api/events"
    assert "SECRET" not in f.read_text("utf-8") and "ROBOT_PROJECT_DIR" not in e["env"]
    assert poste.etat(8765)["agents"]["cursor"]["a_jour"]
    assert not poste.etat(9000)["agents"]["cursor"]["a_jour"]  # port changé : à mettre à jour


def test_fichier_illisible_signale(poste):
    f = poste.fichier_config("claude")
    f.parent.mkdir(parents=True)
    f.write_text("{pas du json", "utf-8")
    assert poste.etat(8765)["agents"]["claude"]["erreur"]
    with pytest.raises(ValueError, match="JSON"):
        poste.installer("claude", 8765)
    assert f.read_text("utf-8") == "{pas du json"  # rien d'écrasé


def test_regles_sans_ecrasement_implicite(poste):
    from atelier.domain import projet

    r = poste.installer_regles()
    assert sorted(r["copiees"]) == ["atelier-automatisation.mdc", "atelier-discovery.mdc"]
    f = projet.PROJECT_DIR / ".cursor" / "rules" / "atelier-discovery.mdc"
    f.write_text("règle adaptée par l'équipe", "utf-8")
    r = poste.installer_regles()
    assert r["differentes"] == ["atelier-discovery.mdc"] and f.read_text("utf-8") == "règle adaptée par l'équipe"
    assert poste.installer_regles(ecraser=True)["copiees"] and poste.etat(8765)["regles"]["atelier-discovery.mdc"]["a_jour"]


def test_mcp_suit_le_projet_actif(tmp_path, monkeypatch):
    from atelier.domain import projet, projets

    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.setenv("ATELIER_PROJETS", str(tmp_path / "projets.json"))  # fichier isolé des autres tests
    for v in ("ROBOT_PROJECT_DIR", "JIRA_BASE_URL", "JIRA_EMAIL", "XRAY_BASE_URL", "GITLAB_URL", "GITLAB_PROJET"):
        monkeypatch.setenv(v, "x")  # restaurées après le test (la bascule modifie l'environnement du processus)
        monkeypatch.delenv(v)
    monkeypatch.setitem(projets._ORIGINE_ENV, "ROBOT_PROJECT_DIR", None)
    monkeypatch.setattr(projet, "PROJECT_DIR", a.resolve())
    pa = projets.enregistrer({"nom": "A", "dossier": str(a), "xray_projet": "DEMOA"})
    pb = projets.enregistrer({"nom": "B", "dossier": str(b), "xray_projet": "DEMOB"})
    projets.activer(pa["id"] if "id" in pa else projets.lister()["projets"][0]["id"])
    projets.suivre_actif()
    assert projet.PROJECT_DIR == a.resolve()
    ids = {p["nom"]: p["id"] for p in projets.lister()["projets"]}
    projets.activer(ids["B"])          # bascule faite dans l'atelier (autre processus) …
    monkeypatch.setattr(projet, "PROJECT_DIR", a.resolve())  # … le processus MCP est encore sur A
    projets.suivre_actif()
    assert projet.PROJECT_DIR == b.resolve()
    del pb
