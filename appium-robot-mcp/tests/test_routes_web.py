"""Routes de l'interface web : elles répondent sans aucun service externe (Xray, Jira, Appium absents)."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from web_app_loader import charger_app_web, module_web  # noqa: E402


@pytest.fixture
def client(projet, monkeypatch, tmp_path):
    mod = module_web()
    monkeypatch.setattr(mod, "CONFIG_PATH", tmp_path / "atelier.json")
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    if hasattr(mod, "connecter_client_test"):
        mod.connecter_client_test(c)
    return c


@pytest.mark.parametrize("route", [
    "/", "/api/etat", "/api/config", "/api/locators", "/api/apps", "/api/carte/graphe",
    "/api/projet/fichiers", "/api/jdd", "/api/run/dernier", "/api/sante", "/api/devices",
])
def test_routes_lecture(client, route):
    r = client.get(route)
    assert r.status_code == 200, r.text


def test_parcours_carte(client):
    a = client.post("/api/apps", json={"nom": "Démo web", "plateformes": ["web"], "web": {"url": "http://x"}})
    assert a.status_code == 200 and a.json()["slug"] == "demo_web"
    g = client.get("/api/carte/graphe").json()
    assert g["app"]["nom"] == "Démo web" and g["nodes"] == []


def test_action_hors_liste_blanche_refusee(client):
    r = client.post("/api/action", json={"nom": "write_project_file", "args": {"path": "x", "content": "y"}})
    assert r.status_code == 400


def test_fichier_de_resultat_hors_dossier_refuse(client):
    assert client.get("/api/resultats/fichier", params={"chemin": "../../etc/passwd"}).status_code == 404


def test_step_externe_valide_dans_l_interface(client):
    pid = client.post("/api/externe/step", json={"gherkin": "Quand je valide"}).json()["id"]
    assert client.get(f"/api/externe/reponse/{pid}").json() == {"decision": None}
    client.post("/api/agent/reponse", json={"id": pid, "decision": "corriger", "texte": "Quand je confirme"})
    assert client.get(f"/api/externe/reponse/{pid}").json() == {"decision": "corrigé", "texte": "Quand je confirme"}


def test_evenement_carte_diffuse_a_la_page(client):
    from atelier.domain import evenements

    mod = module_web()
    avant = len(mod.history)
    evenements.publier({"type": "carte_change"})
    evenements.publier({"type": "surlignage"})  # non relayé dans le processus web (comme avant)
    assert [e["type"] for e in list(mod.history)[avant:]] == ["carte_change"]
