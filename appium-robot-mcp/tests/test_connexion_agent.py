"""Quel agent est connecté au MCP (Claude Code, Cursor…) et dans quel état : su dès la poignée de main, avant tout outil."""
from __future__ import annotations

import asyncio
import json
import time

import pytest


def _requete(methode: str, corps: dict | None = None, sid: str = "") -> tuple[dict, list]:
    scope = {"type": "http", "method": methode, "headers": [(b"mcp-session-id", sid.encode())] if sid else []}
    messages = [{"type": "http.request", "body": json.dumps(corps).encode() if corps else b"", "more_body": False}]
    return scope, messages


def _appeler(app, methode, corps=None, sid=""):
    scope, messages = _requete(methode, corps, sid)
    envoyes = []

    async def recevoir():
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def envoyer(m):
        envoyes.append(m)
    asyncio.run(app(scope, recevoir, envoyer))
    return envoyes


async def _faux_serveur(scope, receive, send):
    """Serveur MCP simulé : lit le corps, répond avec un identifiant de session à l'initialize."""
    m = await receive()
    corps = json.loads(m["body"] or b"{}")
    entetes = [(b"mcp-session-id", b"session-123456789")] if corps.get("method") == "initialize" else []
    await send({"type": "http.response.start", "status": 200, "headers": entetes})
    await send({"type": "http.response.body", "body": b"{}"})


def test_suivi_des_connexions_mcp():
    from atelier.adapters.mcp.server import SuiviConnexions

    evts = []
    app = SuiviConnexions(_faux_serveur, publier=evts.append)
    init = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"clientInfo": {"name": "claude-code", "version": "2.1.3"}}}
    rep = _appeler(app, "POST", init)
    assert rep[0]["headers"] == [(b"mcp-session-id", b"session-123456789")]  # la réponse du serveur passe intacte
    assert evts[-1] == {"type": "mcp_connexion", "etat": "connecte", "session": "session-1234", "client": "claude-code 2.1.3",
                        "agent": "Claude Code"}
    _appeler(app, "POST", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, "session-123456789")
    assert len(evts) == 1  # requête dans la minute : pas d'événement de plus
    app.sessions["session-123456789"]["vu"] -= 120
    _appeler(app, "POST", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, "session-123456789")
    assert evts[-1]["etat"] == "vu"
    _appeler(app, "GET", None, "session-123456789")
    assert [e["ouvert"] for e in evts if e["etat"] == "flux"] == [True, False]  # flux ouvert puis fermé
    _appeler(app, "DELETE", None, "session-123456789")
    assert evts[-1]["etat"] == "deconnecte" and "session-123456789" not in app.sessions
    _appeler(app, "POST", {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, "inconnue")  # session inconnue : rien
    assert evts[-1]["etat"] == "deconnecte"


def test_etat_des_agents_cote_interface(monkeypatch):
    pytest.importorskip("fastapi")
    from web_app_loader import module_web

    w = module_web()
    monkeypatch.setitem(w.state, "connexions_mcp", {})
    ev = lambda etat, sid, client, agent, **x: {"type": "mcp_connexion", "etat": etat, "session": sid, "client": client, "agent": agent, **x}  # noqa: E731
    w._noter_connexion(ev("connecte", "s1", "cursor-vscode 1.9", "Cursor"))
    w._noter_connexion(ev("connecte", "s2", "claude-code 2.1.3", "Claude Code"))
    c = {x["agent"]: x for x in w._connexions()}
    assert c["Claude Code"]["etat"] == "connecte" and c["Cursor"]["etat"] == "connecte"
    w.state["connexions_mcp"]["s1"]["vu"] = time.time() - 3600  # silencieux depuis une heure, session gardée
    assert {x["agent"]: x["etat"] for x in w._connexions()} == {"Claude Code": "connecte", "Cursor": "inactif"}
    w._noter_connexion(ev("flux", "s1", "cursor-vscode 1.9", "Cursor", ouvert=True))  # flux ouvert : il écoute
    w.state["connexions_mcp"]["s1"]["vu"] = time.time() - 3600
    assert {x["agent"]: x["etat"] for x in w._connexions()}["Cursor"] == "connecte"
    w._noter_connexion(ev("deconnecte", "s2", "claude-code 2.1.3", "Claude Code"))
    assert [(x["agent"], x["etat"]) for x in w._connexions()] == [("Cursor", "connecte"), ("Claude Code", "deconnecte")]
