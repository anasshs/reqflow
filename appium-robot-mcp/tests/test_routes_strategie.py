"""Routes Test Strategy : cycle complet par l'API web, refus explicites, session obligatoire."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from web_app_loader import charger_app_web, module_web  # noqa: E402

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"


@pytest.fixture
def client(projet, monkeypatch, tmp_path):
    shutil.copytree(DEMO, projet, dirs_exist_ok=True, ignore=shutil.ignore_patterns("results", "connaissance", "strategie"))
    monkeypatch.setattr(module_web(), "CONFIG_PATH", tmp_path / "atelier.json")
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/plateforme").status_code == 200
    return c


def test_session_obligatoire(projet):
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/api/strategie").status_code in (401, 403)


def test_cycle_complet(client):
    assert client.get("/api/strategie").json()["existe"] is False
    assert client.post("/api/strategie/creer", json={"nom": "S"}).status_code == 400  # RG01
    e = client.post("/api/strategie/creer", json={"nom": "S", "application": "Banque Démo Web"}).json()
    assert e["existe"] and e["strategie"]["statut"] == "Draft"
    r = client.post("/api/strategie/elements", json={"rubrique": "objectifs", "element": {"nom": "Auto", "indicateur": "couverture_automatisee", "cible": 80}})
    assert r.status_code == 200
    assert client.post("/api/strategie/elements", json={"rubrique": "inconnue", "element": {}}).status_code == 400
    for c in ({"description": "Couverture", "type": "entrée", "obligatoire": True, "verification": "automatique",
               "indicateur": "couverture_fonctionnelle", "seuil": 90},
              {"description": "Rapport", "type": "sortie", "verification": "manuelle"}):
        client.post("/api/strategie/elements", json={"rubrique": "criteres", "element": c})
    # couverture fonctionnelle 80 % < 90 : avertissement au lancement d'un run
    entree = client.get("/api/strategie/criteres/entree").json()
    assert [c["description"] for c in entree] == ["Couverture"]
    assert client.post("/api/strategie/perimetre/importer").status_code == 200
    plan = client.get("/api/strategie/plan-automatisation").json()
    assert {c["cle"] for c in plan if c["statut_plan"] == "À analyser"} == {"DEMO-308", "DEMO-309"}
    assert client.post("/api/strategie/plan-automatisation", json={"cle": "DEMO-308", "statut": "Approuvé"}).status_code == 200
    for a in ("soumettre", "approuver", "publier"):
        assert client.post("/api/strategie/transition", json={"action": a}).status_code == 200, a
    assert client.get("/api/strategie/versions/1").json()["statut"] == "Published"
    assert client.post("/api/strategie/transition", json={"action": "publier"}).status_code == 400
    assert client.get("/api/strategie/comparer", params={"a": "1"}).json()["rubriques"] == {}
    assert client.post("/api/strategie/restaurer", json={"version": 1}).status_code == 200
    assert any(j["op"] == "restauration" for j in client.get("/api/strategie/journal").json())


def test_routes_test_design(client):
    assert client.get("/api/conception/vue").json()["kpi"]["cas_xray"] == 9
    assert len(client.get("/api/conception/cas").json()) == 9
    assert client.post("/api/conception/revue/DEMO-301", json={"action": "approuver"}).status_code == 400
    assert client.post("/api/conception/revue/DEMO-301", json={"action": "soumettre"}).json()["statut"] == "In Review"
    assert client.post("/api/conception/baselines", json={"nom": "B1"}).status_code == 200
    assert client.post("/api/conception/baselines", json={"nom": "B1"}).status_code == 400  # immuable
    assert client.get("/api/conception/baselines/comparer", params={"a": "B1"}).json()["tests_impactes"] == []
    assert client.post("/api/conception/mapping", json={"mode": "B (bidirectionnel)"}).status_code == 200
    assert client.post("/api/conception/mapping", json={"mode": "Z"}).status_code == 400
    assert client.get("/api/conception/mapping/tester").json()["tests_analyses"] == 9


def test_execution_center_file_et_campagne(client):
    import time

    from web_app_loader import module_web

    corps = {"target": "tests", "dry_run": True, "variables": {"PLATFORM": "web"}, "jdd_env": "recette"}
    r1 = client.post("/api/run", json=corps).json()
    r2 = client.post("/api/run", json={**corps, "priorite": "High"}).json()
    assert r1["run_id"] != r2["run_id"] and r2["etat"] in ("Queued", "Running")
    assert r1["contexte"]["projet"] and r1["contexte"]["plateforme"] == "web"
    c = client.post("/api/centre/campagnes", json={"nom": "Smoke", "type": "Smoke", "plateformes": ["web"], "tags": ["smoke"],
                                                   "environnement": "recette"}).json()[0]
    j = client.post(f"/api/centre/campagnes/{c['id']}/executer", json={"dry_run": True}).json()["jobs"]
    assert len(j) == 1
    fin = time.time() + 90
    while module_web().centre.FILE.en_cours is not None and time.time() < fin:
        time.sleep(0.3)
    runs = {r["id"]: r for r in client.get("/api/executions").json()}
    assert {r1["run_id"], r2["run_id"], j[0]["run_id"]} <= set(runs)
    assert runs[j[0]["run_id"]]["campagne"] == c["id"] and runs[r1["run_id"]]["contexte"]["environnement"] == "recette"
    assert client.get("/api/centre/campagnes").json()[0]["runs"] == [j[0]["run_id"]]
    assert client.get(f"/api/centre/preuves/{r1['run_id']}").json()["fichiers"]
    assert client.get("/api/centre/fichier", params={"chemin": "tests/connexion.robot"}).status_code == 400
    assert client.get("/api/centre/xray").json()[0]["statut"] in ("Non configuré", "Synced", "Pending", "Partial")


def test_routes_integrations_jira_xray(client, monkeypatch):
    """Routes Jira / Xray : historique vide, refus propre sans identifiants (jamais d'appel réseau en test)."""
    for v in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "XRAY_CLIENT_ID", "XRAY_CLIENT_SECRET"):
        monkeypatch.delenv(v, raising=False)
    assert client.get("/api/conception/sync-historique").json() == []
    r = client.post("/api/echecs/jira/doublons", json={"id": "inconnu", "projet": "DEMO"})
    assert r.status_code >= 400
    r = client.post("/api/conception/publier", json={"cle": "INCONNU-1", "projet": "DEMO"})
    assert r.status_code >= 400
    r = client.post("/api/centre/xray/rejouer", json={"run": "inexistant"})
    assert r.status_code in (200, 400, 404)
