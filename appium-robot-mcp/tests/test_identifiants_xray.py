"""Identifiants Xray saisis dans l'atelier (Paramètres › Connexions) : utilisés par tous les boutons de synchronisation
(import de l'organisation / des définitions, exécutions Xray), conservés après une bascule de projet, remplacés par
les variables propres d'un projet, hérités par les runs Robot (listener Xray dans le sous-processus)."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from web_app_loader import charger_app_web, module_web  # noqa: E402

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"
NOMS = ("XRAY_CLIENT_ID", "XRAY_CLIENT_SECRET", "XRAY_CLIENT_ID_TAM", "XRAY_CLIENT_SECRET_TAM")


@pytest.fixture
def client(projet, monkeypatch, tmp_path):
    from atelier.domain import projets
    from atelier.integrations.xray import XrayClient

    shutil.copytree(DEMO, projet, dirs_exist_ok=True, ignore=shutil.ignore_patterns("results", "connaissance", "strategie"))
    monkeypatch.setattr(module_web(), "CONFIG_PATH", tmp_path / "atelier.json")
    monkeypatch.setenv("ATELIER_PROJETS", str(tmp_path / "projets.json"))  # liste de projets isolée des autres tests
    for v in ("ROBOT_PROJECT_DIR", "XRAY_BASE_URL", "JIRA_BASE_URL", "JIRA_EMAIL", "GITLAB_URL", "GITLAB_PROJET"):
        monkeypatch.setenv(v, "x")  # la bascule de projet modifie l'environnement du processus : restauré après
        monkeypatch.delenv(v)
    from atelier.domain import projet as projet_mod

    monkeypatch.setattr(projet_mod, "PROJECT_DIR", projet_mod.PROJECT_DIR)
    for n in NOMS:  # aucun identifiant dans l'environnement du poste ; restaurés après le test
        monkeypatch.setenv(n, "x")
        monkeypatch.delenv(n)
        monkeypatch.setitem(projets._ORIGINE, n, None)
    monkeypatch.setattr(projets, "_SAISIS", set())
    vus = []

    def noter(self, *a, **k):
        vus.append((self.cid, self.secret))
        return {"tests": [{"cle": "DEMO-301", "type": "Cucumber", "dossier": "/Web"}], "champs_absents": [], "plans": [], "test_sets": [],
                "absents": [], "executions": []}

    for m in ("definitions_tests", "conteneurs", "executions"):
        monkeypatch.setattr(XrayClient, m, noter)
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/plateforme").status_code == 200
    c.vus = vus
    return c


def _saisir(c, nom, valeur):
    r = c.post("/api/connexions/secret", json={"nom": nom, "valeur": valeur, "memoriser": False})
    assert r.status_code == 200, r.text
    assert valeur not in r.text  # jamais renvoyé


def test_boutons_de_synchro_utilisent_les_identifiants_saisis(client):
    from atelier.domain import projets
    from atelier.integrations.xray import XrayClient

    with pytest.raises(RuntimeError, match="Paramètres › Connexions"):
        XrayClient()
    _saisir(client, "XRAY_CLIENT_ID", "id-saisi")
    _saisir(client, "XRAY_CLIENT_SECRET", "secret-saisi")
    # Suites de test › « Importer l'organisation Xray » (définitions + plans / sets + exécutions)
    r = client.post("/api/patrimoine/xray-definitions", json={})
    assert r.status_code == 200, r.text
    # Execution Center › Test Selection › « Actualiser depuis Xray »
    assert client.post("/api/centre/executions-xray/actualiser", json={}).status_code == 200
    assert client.vus and set(client.vus) == {("id-saisi", "secret-saisi")}
    # les runs Robot (listener Xray dans un sous-processus) héritent des identifiants
    sortie = subprocess.run([sys.executable, "-c", "import os; print(os.environ.get('XRAY_CLIENT_ID'))"], capture_output=True, text=True).stdout
    assert sortie.strip() == "id-saisi"
    # bascule vers un projet sans identifiants propres : les identifiants saisis restent
    b = Path(projets.projet.PROJECT_DIR).parent / "projet_b"
    b.mkdir()
    pb = projets.enregistrer({"nom": "Projet B", "dossier": str(b), "xray_projet": "DEMOB"})
    pid_b = next(p["id"] for p in projets.lister()["projets"] if p["nom"] == "Projet B")
    assert client.post("/api/projets/activer", json={"id": pid_b}).status_code == 200
    assert XrayClient().cid == "id-saisi"
    # projet avec ses propres variables (ex. XRAY_CLIENT_ID_TAM), valeurs saisies dans l'atelier
    t = Path(projets.projet.PROJECT_DIR).parent / "projet_tam"
    t.mkdir()
    projets.enregistrer({"nom": "TAM", "dossier": str(t), "xray_projet": "TAM",
                         "secrets": {"XRAY_CLIENT_ID": "XRAY_CLIENT_ID_TAM", "XRAY_CLIENT_SECRET": "XRAY_CLIENT_SECRET_TAM"}})
    pid_t = next(p["id"] for p in projets.lister()["projets"] if p["nom"] == "TAM")
    assert client.post("/api/projets/activer", json={"id": pid_t}).status_code == 200
    _saisir(client, "XRAY_CLIENT_ID_TAM", "id-tam")
    _saisir(client, "XRAY_CLIENT_SECRET_TAM", "secret-tam")
    assert (XrayClient().cid, XrayClient().secret) == ("id-tam", "secret-tam")
    assert client.post("/api/projets/activer", json={"id": pid_b}).status_code == 200
    assert XrayClient().cid == "id-saisi"  # retour au projet B : identifiants généraux
    del pb
