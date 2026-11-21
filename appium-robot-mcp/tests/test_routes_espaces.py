"""Routes des espaces de travail (graphes) : lecture, modifications historisées, IA simulée, sécurité."""
from __future__ import annotations

import json
import shutil
import types

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from conftest import FIXTURES  # noqa: E402
from web_app_loader import charger_app_web, module_web  # noqa: E402


@pytest.fixture
def client(projet, monkeypatch, tmp_path):
    shutil.copytree(FIXTURES / "projet_robot", projet, dirs_exist_ok=True)
    monkeypatch.setattr(module_web(), "CONFIG_PATH", tmp_path / "atelier.json")
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/plateforme").status_code == 200  # la page des espaces pose aussi le cookie
    return c


def _importer(client):
    data = json.loads((FIXTURES / "xray" / "patrimoine.json").read_text("utf-8"))
    r = client.post("/api/patrimoine/importer", json=data)
    assert r.status_code == 200 and r.json()["nb_tests"] == 6


def test_page_et_fichiers_statiques(client):
    assert "AI Test Engineering Platform" in client.get("/plateforme").text
    assert client.get("/static/graphe.js").status_code == 200
    assert client.get("/static/plateforme.css").status_code == 200
    assert client.get("/static/..%2Fapp.py").status_code == 404
    assert client.get("/static/index.html").status_code == 404


def test_api_espaces_exige_la_session(projet):
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/api/graphes/connaissance").status_code == 401


def test_graphes(client):
    _importer(client)
    g = client.get("/api/graphes/connaissance").json()
    assert g["stats"]["noeuds"] > 20 and "XRAY" in g["legende"]["categories"]
    assert {n["categorie"] for n in client.get("/api/graphes/connaissance?categories=JIRA").json()["noeuds"]} == {"JIRA"}
    centre = client.get("/api/graphes/connaissance", params={"centre": "keyword:seconnecter"}).json()
    assert "test_robot:tests/connexion.robot::Connexion Standard" in {n["id"] for n in centre["noeuds"]}
    cv = client.get("/api/graphes/couverture").json()
    assert cv["indicateurs"]["global"]["couverture_automatisee"] == 0.5 and "Virements" in cv["modules"]
    fx = client.get("/api/graphes/flux", params={"cible": "test:DEMO-1"}).json()
    assert "keyword:cliquersur" in {n["id"] for n in fx["noeuds"]}
    assert {c["id"] for c in fx["cibles"]} >= {"test:DEMO-1"}
    imp = client.get("/api/graphes/impact", params={"id": "keyword:seconnecter"}).json()
    assert imp["tnr"]["include_tags"] == ["DEMO-1", "DEMO-2", "DEMO-3"]
    d = client.get("/api/graphes/noeud", params={"id": "keyword:saisirlemontant"}).json()
    assert d["noeud"]["proprietes"]["fichier"] == "resources/socle/commun.resource"
    assert "test:DEMO-1" in d["tests_xray"]
    assert [c["cle"] for c in client.get("/api/graphes/candidats").json()][:2] == ["DEMO-1", "DEMO-2"]
    assert client.get("/api/graphes/noeud", params={"id": "inconnu:x"}).status_code == 400
    assert "Cliquer Sur" in client.get("/api/projet/fichier", params={"chemin": "resources/socle/commun.resource"}).json()["contenu"]
    assert client.get("/api/projet/fichier", params={"chemin": "../../etc/passwd"}).status_code == 400


def test_modifications_historisees(client):
    r = client.post("/api/graphes/noeuds", json={"id": "regle:plafond", "type": "regle", "libelle": "Plafond 10 000"})
    assert r.status_code == 200
    assert client.post("/api/graphes/noeuds", json={"id": "regle:plafond", "type": "regle", "libelle": "x"}).status_code == 400
    assert client.post("/api/graphes/relations", json={"de": "regle:plafond", "vers": "ecran:virement_saisie",
                                                       "type": "verifie"}).status_code == 200
    assert client.post("/api/graphes/relations", json={"de": "regle:plafond", "vers": "ecran:absent",
                                                       "type": "verifie"}).status_code == 400
    assert client.post("/api/graphes/noeuds/modifier", json={"id": "regle:plafond", "libelle": "Plafond journalier"}).status_code == 200
    assert client.post("/api/graphes/noeuds/supprimer", json={"id": "keyword:cliquersur"}).status_code == 200
    ids = {n["id"] for n in client.get("/api/graphes/connaissance").json()["noeuds"]}
    assert "regle:plafond" in ids and "keyword:cliquersur" not in ids
    histo = client.get("/api/graphes/historique").json()
    assert [h["op"] for h in histo][:4] == ["suppression_noeud", "modification_noeud", "ajout_relation", "ajout_noeud"]
    assert client.get("/api/graphes/historique", params={"id": "regle:plafond"}).json()


def test_anomalies_sans_ia(client):
    a = client.get("/api/graphes/anomalies").json()
    assert all({"gravite", "code", "noeud", "message"} <= set(x) for x in a)


def test_ia_indisponible_sans_cle(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.post("/api/graphes/ia", json={"graphe": "connaissance", "intention": "anomalies"}).json()
    assert r["disponible"] is False and "anomalies" in r


def test_ia_contextuelle_simulee(client, monkeypatch):
    from atelier.intelligence import assistant

    vus = {}

    class Faux:
        class messages:
            @staticmethod
            def create(**kw):
                vus.update(kw)
                texte = "Le keyword [keyword:seconnecter] est partagé par 3 tests.\nPropositions à valider :\n1. ..."
                return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=texte)])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "factice")
    monkeypatch.setenv("IA_FOURNISSEUR", "anthropic")  # l'assistant respecte le fournisseur choisi par l'entreprise
    monkeypatch.setattr(assistant, "_client", lambda: Faux())
    r = client.post("/api/graphes/ia", json={"graphe": "flux", "intention": "resumer",
                                             "selection": "keyword:seconnecter"}).json()
    assert r["disponible"] and r["noeuds_cites"] == ["keyword:seconnecter"]
    contexte = vus["messages"][0]["content"]
    assert "keyword:seconnecter" in contexte and "Graphe : flux" in contexte
    assert "n'invente" in vus["system"]
    # rien n'a été modifié par l'IA
    assert client.get("/api/graphes/historique").json() == []


def test_mcp_outils_espaces(projet):
    shutil.copytree(FIXTURES / "projet_robot", projet, dirs_exist_ok=True)
    import server

    assert server.impact_analysis("keyword:saisirlemontant")["tnr"]["include_tags"] == ["DEMO-1", "DEMO-2"]
    assert server.coverage_report()["indicateurs"]["disponible"] is False
    assert server.automation_flow("test_robot:tests/connexion.robot::Connexion Standard")["noeuds"]
    assert server.knowledge_graph(categorie="AUTOMATION")["noeuds"]
