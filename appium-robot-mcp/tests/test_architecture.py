"""Règles d'architecture (CLAUDE.md) vérifiées sur les imports du code."""
from __future__ import annotations

import ast
import subprocess
import sys

import pytest

from conftest import RACINE

ATELIER = RACINE / "atelier"
MOTEURS = ["domain", "discovery", "intelligence", "generation", "execution", "integrations"]


def _imports(fichier) -> set[str]:
    noms: set[str] = set()
    for n in ast.walk(ast.parse(fichier.read_text("utf-8"))):
        if isinstance(n, ast.Import):
            noms |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            noms.add(n.module)
    return noms


def _fichiers(*dossiers):
    for d in dossiers:
        yield from sorted((ATELIER / d).rglob("*.py"))


@pytest.mark.parametrize("fichier", list(_fichiers(*MOTEURS)), ids=lambda f: str(f.relative_to(ATELIER)))
def test_moteur_n_importe_jamais_un_adapter(fichier):
    interdits = {i for i in _imports(fichier)
                 if i.startswith(("atelier.adapters", "mcp", "fastapi", "uvicorn", "starlette"))
                 or i in ("server", "app_map", "jdd", "xray_client", "web_backend")}
    assert not interdits, f"{fichier.name} importe {interdits}"


@pytest.mark.parametrize("fichier", list(_fichiers("adapters")), ids=lambda f: str(f.relative_to(ATELIER)))
def test_adapters_n_importent_pas_les_points_d_entree_historiques(fichier):
    historiques = {"server", "app_map", "jdd", "xray_client", "web_backend", "agent"}
    assert not (_imports(fichier) & historiques)


def test_points_d_entree_historiques_designent_les_moteurs():
    import app_map
    import jdd
    import server
    import web_backend

    from atelier.adapters.mcp import server as serveur_mcp
    from atelier.discovery import carte
    from atelier.execution import jdd as jdd_mod
    from atelier.integrations import playwright

    assert app_map is carte and jdd is jdd_mod and server is serveur_mcp and web_backend is playwright


def test_server_py_se_charge_dans_un_processus_neuf():
    r = subprocess.run([sys.executable, "-c", "import server, xray_client, xray_live_listener, "
                        "cartographie_listener; print(len(server.mcp._tool_manager.list_tools()))"],
                       cwd=RACINE, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "48"
