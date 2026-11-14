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
