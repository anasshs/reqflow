"""Règles d'architecture (CLAUDE.md) vérifiées sur les imports du code."""
from __future__ import annotations

import ast
import json
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
                        "cartographie_listener, json; print(json.dumps([t.name for t in server.mcp._tool_manager.list_tools()]))"],
                       cwd=RACINE, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    noms = json.loads(r.stdout)
    assert len(noms) == 126  # + 2 maintenance (maintenance_modifier_bdd, maintenance_rapporter) ; + discovery_donnee_proposer (données proposées par l'agent) ; + 2 TNR (tnr_conventions, tnr_demander_publication) ; + run_tests (tests précis) ; + 4 Model-Based Testing ; + discovery_profil_vers_jdd + locator_robustesse ; + 2 interprétation des releases ; 48 historiques + 4 espaces de travail + 2 testabilité des US + 5 Discovery + plan_de_test + 11 Construire / Studio + 2 cerveau + 3 Coverage Intelligence + 5 parcours de fonctionnalité + cursor_regles + coverage_ui + 2 Test Design avancé + 2 Champ / Anomalie + failure_connaissance + agent_annoncer + 2 granularité + 10 jugements délégués à Cursor + studio_rapprocher_etapes + 2 jugement des keywords + 5 référentiel de données Discovery + 2 boîte de demandes + discovery_parcours_cadre
    assert {"knowledge_graph", "impact_analysis", "coverage_report", "automation_flow"} <= set(noms)
