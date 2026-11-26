"""Fixtures communes. Aucun test n'appelle un vrai service (Xray, Jira, Oracle, Appium, Claude)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Avant tout import du code : projet de tests neutre, aucune intégration configurée.
os.environ["ROBOT_PROJECT_DIR"] = tempfile.mkdtemp(prefix="atelier_tests_")
for _var in ("WEB_EVENTS_URL", "XRAY_CLIENT_ID", "XRAY_CLIENT_SECRET", "JIRA_BASE_URL",
             "JIRA_EMAIL", "JIRA_API_TOKEN", "ANTHROPIC_API_KEY"):
    os.environ.pop(_var, None)
os.environ["ATELIER_JETON_FICHIER"] = str(Path(os.environ["ROBOT_PROJECT_DIR"]) / "jeton")
os.environ.pop("ATELIER_JETON_EVENEMENTS", None)
os.environ.setdefault("ATELIER_CONFIG", str(Path(os.environ["ROBOT_PROJECT_DIR"]) / "atelier.json"))
os.environ["ATELIER_PROJETS"] = str(Path(os.environ["ROBOT_PROJECT_DIR"]) / "projets.json")  # jamais la liste du poste
os.environ["ATELIER_DOSSIER"] = str(Path(os.environ["ROBOT_PROJECT_DIR"]) / ".atelier")  # jamais la base ni la config du poste
os.environ.pop("ATELIER_BASE", None)
os.environ["ATELIER_SYNCHRO"] = "non"  # pas de synchronisation de fond pendant les tests
os.environ["ATELIER_IA_JOURNAL"] = str(Path(os.environ["ROBOT_PROJECT_DIR"]) / "ia.sqlite")  # jamais le journal IA du poste
os.environ.pop("ATELIER_IA_CONFIG", None)
os.environ["ATELIER_COFFRE"] = "non"  # jamais le coffre réel du poste (tests : faux coffre explicite)
os.environ["ATELIER_FLUX"] = "complet"  # cycle détaillé (approbations) ; le flux simple a ses propres tests (test_flux.py)
sys.path.insert(0, str(RACINE))


def pointer_projet(chemin: Path, monkeypatch) -> Path:
    """Fait pointer tout le code vers un projet de tests temporaire."""
    chemin = chemin.resolve()
    try:
        from atelier.domain import projet
    except ImportError:  # disposition d'origine (avant la phase 1)
        import app_map
        import jdd
        import server

        for mod in (server, app_map, jdd):
            monkeypatch.setattr(mod, "PROJECT_DIR", chemin)
        monkeypatch.setattr(server, "SNAP_DIR", chemin / ".mcp_snapshots")
        monkeypatch.setattr(app_map, "MAP_ROOT", chemin / "app_map")
        monkeypatch.setattr(jdd, "JDD_DIR", chemin / "data" / "jdd")
        return chemin
    monkeypatch.setattr(projet, "PROJECT_DIR", chemin)
    monkeypatch.setattr(projet, "SNAP_DIR", chemin / ".mcp_snapshots")
    return chemin


@pytest.fixture
def projet(tmp_path, monkeypatch) -> Path:
    """Projet de tests vide et isolé (dossier temporaire)."""
    d = tmp_path / "projet"
    d.mkdir()
    return pointer_projet(d, monkeypatch)


def lire_fixture(*parts: str) -> str:
    return FIXTURES.joinpath(*parts).read_text("utf-8")


def run_reussi(fichier: str, dry_run: bool = True) -> str:
    """Enregistre un run réussi de la suite, postérieur à sa dernière modification (préalable à l'approbation)."""
    from datetime import datetime, timedelta

    from atelier.execution import historique

    rid = f"RUN-{datetime.now():%Y%m%d-%H%M%S}-{abs(hash(fichier)) % 1000}"
    debut = (datetime.now() + timedelta(seconds=2)).isoformat(timespec="seconds")
    historique.enregistrer(rid, {"target": fichier, "dry_run": dry_run}, {"resultat": {"passes": 1, "echecs": 0}}, debut, debut)
    return rid
