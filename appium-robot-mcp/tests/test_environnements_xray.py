"""Environnements du projet : lus dans le projet Xray (paramètres du projet, sinon Test Executions récentes), gardés
dans le projet de tests, jamais saisis dans les paramètres du projet ; Xray indisponible : l'atelier continue."""
from __future__ import annotations

import shutil

import pytest

from atelier.integrations.xray import ErreurGraphQL, XrayClient
from conftest import FIXTURES


class FauxXray(XrayClient):
    """Client Xray sans réseau : schéma et réponses GraphQL simulés."""

    def __init__(self, schema: dict, reglages=None, executions=()):
        self.schema, self.reglages, self._execs, self.requetes = schema, reglages, list(executions), []

    def _type_champs(self, nom: str) -> dict:
        return {c: {"args": dict(args)} for c, args in self.schema.get(nom, {}).items()}

    def gql(self, query, variables=None):
        self.requetes.append((query, variables))
        if "getProjectSettings" in query:
            if isinstance(self.reglages, Exception):
                raise self.reglages
            return {"getProjectSettings": {"testEnvironments": self.reglages}}
        return {"getTestExecutions": {"total": len(self._execs), "results": self._execs}}


COMPLET = {"Query": {"getProjectSettings": {"projectIdOrKey": False}, "getTestExecutions": {"jql": False, "limit": False}},
           "ProjectSettings": {"projectId": {}, "testEnvironments": {}}, "TestExecution": {"issueId": {}, "jira": {}, "testEnvironments": {}}}
SANS_REGLAGES = {"Query": {"getTestExecutions": {"jql": False, "limit": False}}, "TestExecution": {"issueId": {}, "jira": {}, "testEnvironments": {}}}
_exec = lambda cle, envs: {"issueId": cle, "jira": {"key": cle}, "testEnvironments": envs}  # noqa: E731


@pytest.fixture
def depot(projet, monkeypatch):
    from atelier.domain import projets

    shutil.copytree(FIXTURES / "projet_robot", projet, dirs_exist_ok=True)   # data/jdd/recette.yaml
    monkeypatch.setattr(projets, "cle_xray", lambda: "DEMO")
    return projet


def test_client_lit_les_parametres_du_projet_par_introspection():
    x = FauxXray(COMPLET, ["RECETTE", "PREPROD", " ", "RECETTE"])
    r = x.environnements("DEMO")
    assert r == {"environnements": ["RECETTE", "PREPROD"], "source": "paramètres du projet Xray", "absents": []}
    assert x.requetes == [("query($p: String) { getProjectSettings(projectIdOrKey: $p) { testEnvironments } }", {"p": "DEMO"})]
    # l'argument est celui que le schéma annonce, obligatoire ou non : rien n'est supposé
    autre = FauxXray({**COMPLET, "Query": {**COMPLET["Query"], "getProjectSettings": {"projectId": True}}}, ["INT"])
    autre.environnements("DEMO")
    assert autre.requetes[0][0] == "query($p: String!) { getProjectSettings(projectId: $p) { testEnvironments } }"


def test_a_defaut_les_test_executions_recentes():
    execs = [_exec("DEMO-90", ["recette"]), _exec("DEMO-91", ["recette", "android"]), _exec("DEMO-92", []), _exec("DEMO-93", ["preprod"])]
    r = FauxXray(SANS_REGLAGES, executions=execs).environnements("DEMO")
    assert r["environnements"] == ["recette", "android", "preprod"]           # du plus utilisé au moins utilisé
    assert r["source"] == "Test Executions récentes du projet Xray" and "getProjectSettings" in r["absents"]
    r = FauxXray(COMPLET, [], execs).environnements("DEMO")                    # paramètres vides : seconde lecture
    assert r["environnements"][0] == "recette" and r["source"].startswith("Test Executions")
    r = FauxXray(COMPLET, ErreurGraphQL("accès refusé"), execs).environnements("DEMO")
    assert r["environnements"][0] == "recette" and any("refusé" in a for a in r["absents"])
    assert FauxXray(SANS_REGLAGES).environnements("DEMO")["environnements"] == []


def test_liste_gardee_dans_le_projet_et_secours(depot):
    from atelier.execution import jdd
    from atelier.integrations.xray import environnements as envs

    e = envs.etat()                                                            # Xray pas encore lu : secours annoncé
    assert envs.liste() == ["recette"] and e["depuis_xray"] is False and "secours" in e["source"]
    e = envs.synchroniser(FauxXray(COMPLET, ["RECETTE", "PREPROD"]))
    assert envs.liste() == ["RECETTE", "PREPROD"] and e["depuis_xray"] and e["projet"] == "DEMO" and e["source"] == "paramètres du projet Xray"
    assert e["environnements"] == [{"nom": "RECETTE", "jeux_de_donnees": True}, {"nom": "PREPROD", "jeux_de_donnees": False}]
    assert (depot / "studio" / "environnements_xray.json").exists()
    assert [j["jeu"] for j in jdd.lister("RECETTE")] == [j["jeu"] for j in jdd.lister("recette")]   # même fichier, casse ignorée
    with pytest.raises(FileNotFoundError):
        jdd.lister("PREPROD")
    (depot / "data" / "jdd" / "integration.yaml").write_text("{}", "utf-8")
    assert envs.etat()["sans_environnement"] == ["integration"]                # données sans environnement Xray : signalées

    class EnPanne:
        def environnements(self, cle):
            raise RuntimeError("Xray injoignable")

    with pytest.raises(RuntimeError):
        envs.synchroniser(EnPanne())
    assert envs.liste() == ["RECETTE", "PREPROD"]                              # la dernière liste lue reste en place


def test_sans_projet_xray_ni_identifiants(depot, monkeypatch):
    from atelier.domain import projets
    from atelier.integrations.xray import environnements as envs

    envs.assurer()                                                             # pas d'identifiants : ne fait rien, ne lève rien
    assert envs.lire() == {}
    monkeypatch.setattr(projets, "cle_xray", lambda: "")
    with pytest.raises(ValueError, match="Aucun projet Xray"):
        envs.synchroniser(FauxXray(COMPLET, ["RECETTE"]))


def test_parametres_du_projet_et_contexte(depot, tmp_path):
    from fastapi.testclient import TestClient

    from atelier.domain import projets
    from atelier.integrations.xray import environnements as envs
    from web_app_loader import charger_app_web

    p = projets.valider({"nom": "Banque", "dossier": str(tmp_path), "xray_projet": "demo", "environnements": ["recette", "preprod"]})
    assert "environnements" not in p and p["xray_projet"] == "DEMO"           # plus saisis dans les paramètres du projet
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/").status_code == 200
    assert c.get("/api/contexte").json()["environnements"] == ["recette"]     # secours tant que Xray n'est pas lu
    envs.synchroniser(FauxXray(COMPLET, ["RECETTE", "PREPROD"]))
    assert c.get("/api/contexte").json()["environnements"] == ["RECETTE", "PREPROD"]
    e = c.get("/api/xray/environnements").json()
    assert e["source"] == "paramètres du projet Xray" and [x["nom"] for x in e["environnements"]] == ["RECETTE", "PREPROD"]
    assert c.post("/api/xray/environnements/synchroniser").status_code == 400  # Xray non configuré : erreur dite, liste gardée
    assert c.get("/api/discovery/donnees").json()["sources"]["environnements"] == ["RECETTE", "PREPROD"]
