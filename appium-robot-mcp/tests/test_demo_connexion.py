"""Projet de démonstration : la suite Connexion s'exécute réellement (Robot + Playwright) sur
l'application fictive, avec l'échec volontaire de DEMO-304 et sa capture d'écran."""
import os
import shutil
from pathlib import Path

import pytest

from tests.conftest import pointer_projet

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"
CHROMIUM = os.environ.get("WEB_BROWSER_EXECUTABLE") or "/opt/pw-browsers/chromium"


@pytest.fixture
def projet_demo(tmp_path, monkeypatch):
    d = tmp_path / "demo"
    shutil.copytree(DEMO, d, ignore=shutil.ignore_patterns("results", "connaissance"))
    pointer_projet(d, monkeypatch)
    return d


def test_jdd_detectes_dans_la_suite(projet_demo):
    from atelier.execution import jdd

    r = jdd.detecter("tests", "recette")
    assert r["inconnus"] == []
    assert set(r["detectes"]) == {"CLIENT_ACTIF", "MOT_DE_PASSE_INVALIDE", "IDENTIFIANT_INCONNU", "CHAMPS_VIDES",
                                  "COMPTE_BLOQUE", "TROIS_ECHECS", "DECONNEXION"}


def test_depot_demo_reconnu_comme_web(projet_demo):
    from atelier.execution.depot_robot import lire_depot

    inv = lire_depot()
    tests = list(inv["tests"].values())
    assert len(tests) == 7
    assert all(t["plateformes"] == ["web"] for t in tests)


@pytest.mark.skipif(not Path(CHROMIUM).exists(), reason="Chromium absent")
def test_execution_reelle(projet_demo, monkeypatch):
    from atelier.execution.robot import run_robot

    monkeypatch.setenv("WEB_BROWSER_EXECUTABLE", CHROMIUM)
    b = run_robot("tests", variables={"PLATFORM": "web"}, output_dir="results/essai", xray_mode="aucun", jdd_env="recette")
    assert "7 tests, 6 passed, 1 failed" in b["console_fin"]
    assert "Votre compte est bloqué" in b["console_fin"] and "Identifiant ou mot de passe incorrect" in b["console_fin"]
    captures = list((projet_demo / "results" / "essai" / "captures").glob("*.png"))
    assert len(captures) == 1 and captures[0].name.startswith("Blocage")


@pytest.mark.skipif(not Path(CHROMIUM).exists(), reason="Chromium absent")
def test_detail_echec_enrichi(projet_demo, monkeypatch):
    """Détail du test en échec : seul son jeu de données, locator résolu depuis le dépôt, écran de
    référence de la carte et capture prise au teardown."""
    from atelier.execution import historique
    from atelier.execution.robot import run_robot

    monkeypatch.setenv("WEB_BROWSER_EXECUTABLE", CHROMIUM)
    params = {"target": "tests", "include_tags": ["DEMO-304"], "variables": {"PLATFORM": "web"},
              "output_dir": "results/runs/RUN-20261114-100000", "xray_mode": "aucun", "jdd_env": "recette"}
    bilan = run_robot(**params)
    historique.enregistrer("RUN-20261114-100000", params, bilan, "2026-11-14T10:00:00", "2026-11-14T10:00:10")
    t = historique.detail("RUN-20261114-100000")["tests"][0]
    d = historique.detail_test("RUN-20261114-100000", t["id"])
    assert list(d["donnees"]) == ["TROIS_ECHECS"]
    fautive = d["etapes"][d["etape_en_echec"]]
    assert fautive["locator"] == "id=message_erreur"
    assert fautive["strategie"] == "id (attribut HTML)"
    assert fautive["ecran_reference"]["ecran"] == "connexion"
    assert len(d["captures"]) == 1
