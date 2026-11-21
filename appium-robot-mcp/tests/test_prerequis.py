"""Prérequis du poste au lancement : projet de tests choisi (jamais le dossier de l'atelier), navigateur web installé."""
from pathlib import Path

from tests.conftest import pointer_projet


def test_projet_de_tests_dans_le_dossier_de_l_atelier(projet, monkeypatch):
    from atelier.domain import prerequis

    assert prerequis.projet()["ok"]                                                    # un dossier de tests : rien à dire
    pointer_projet(prerequis.dossier_atelier(), monkeypatch)                          # lancé depuis appium-robot-mcp sans réglage
    p = prerequis.projet()
    assert not p["ok"] and "propre dossier" in p["raison"] and "Paramètres › Projets" in p["solution"] and "ROBOT_PROJECT_DIR" in p["solution"]
    msg = prerequis.message_demarrage(8765)
    assert "http://127.0.0.1:8765" in msg and "/!\\ PROJET DE TESTS" in msg
    pointer_projet(projet / "absent", monkeypatch)
    assert "n'existe pas" in prerequis.projet()["raison"]


def test_navigateur_installe_ou_non(tmp_path, monkeypatch):
    from atelier.domain import prerequis

    monkeypatch.delenv("WEB_BROWSER_EXECUTABLE", raising=False)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "pw"))
    (tmp_path / "pw").mkdir()
    n = prerequis.navigateur()
    assert not n["ok"] and "playwright install chromium" in n["solution"]           # pip a installé la bibliothèque, pas le navigateur
    (tmp_path / "pw" / "chromium-1200").mkdir()
    assert prerequis.navigateur()["ok"]
    exe = tmp_path / "chrome.exe"
    monkeypatch.setenv("WEB_BROWSER_EXECUTABLE", str(exe))
    assert not prerequis.navigateur()["ok"]
    exe.write_text("")
    assert prerequis.navigateur()["ok"]


def test_contexte_et_sante_signalent_le_projet(monkeypatch):
    from fastapi.testclient import TestClient

    from atelier.domain import prerequis
    from tests.test_routes_web import charger_app_web

    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/").status_code == 200
    assert c.get("/api/contexte").json()["projet_alerte"] is None
    pointer_projet(prerequis.dossier_atelier(), monkeypatch)
    alerte = c.get("/api/contexte").json()["projet_alerte"]
    assert alerte and Path(alerte["dossier"]) == prerequis.dossier_atelier()
    item = next(x for x in c.get("/api/sante").json() if x["cle"] == "projet")
    assert item["ok"] is False and item["optionnel"] is False and item["solution"]
