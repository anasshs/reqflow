"""Rétrocompatibilité : la liste des outils MCP (noms, descriptions, paramètres) et les routes
de l'interface web sont figées. Les instantanés ont été produits sur le prototype d'origine."""
from __future__ import annotations

import asyncio
import json

from conftest import FIXTURES


def _outils() -> dict:
    import server

    tools = asyncio.run(server.mcp.list_tools())
    return {t.name: {"description": t.description, "parametres": t.inputSchema} for t in tools}


def test_liste_des_outils_mcp_identique():
    attendu = json.loads((FIXTURES / "outils_mcp.json").read_text("utf-8"))
    actuel = _outils()
    manquants = sorted(set(attendu) - set(actuel))
    assert not manquants, f"Outils MCP supprimés : {manquants}"
    for nom, spec in attendu.items():
        assert actuel[nom]["parametres"] == spec["parametres"], f"Paramètres modifiés : {nom}"
        assert actuel[nom]["description"] == spec["description"], f"Description modifiée : {nom}"


def test_routes_web_presentes():
    from web_app_loader import charger_app_web

    app = charger_app_web()
    attendu = json.loads((FIXTURES / "routes_web.json").read_text("utf-8"))
    actuel = {f"{','.join(sorted(getattr(r, 'methods', None) or ['WS']))} {r.path}" for r in app.routes}
    manquantes = sorted(set(attendu) - actuel)
    assert not manquantes, f"Routes web supprimées : {manquantes}"
