"""Serveur MCP en HTTP pour Cursor : jamais un silence. Attendu ou non, lancé, joignable, ou pourquoi il ne l'est pas ;
port déjà pris dit clairement ; Cursor configuré par URL sans serveur attendu signalé. Aucun Cursor réel."""
import json
import socket
import types

import pytest


@pytest.fixture
def ai(tmp_path, monkeypatch):
    from atelier.integrations import agents_ia

    monkeypatch.setattr(agents_ia, "fichier_config", lambda agent: tmp_path / "mcp.json")
    monkeypatch.setenv("ATELIER_MCP_JOURNAL", str(tmp_path / "mcp_http.log"))
    monkeypatch.delenv("MCP_HTTP_PORT", raising=False)
    agents_ia._serveur_http.clear()
    return agents_ia


def test_cursor_par_url_sans_serveur_attendu(ai, tmp_path):
    assert ai.etat_serveur_http()["ok"]                                                  # stdio : rien à dire
    (tmp_path / "mcp.json").write_text(json.dumps({"mcpServers": {"appium-robot": {"url": "http://localhost:8000/mcp"}}}), encoding="utf-8")
    e = ai.etat_serveur_http()
    assert not e["ok"] and "MCP_HTTP_PORT" in e["message"] and "lancer-atelier.cmd" in e["message"]


def test_serveur_arrete_au_demarrage_dit_pourquoi(ai, monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_HTTP_PORT", "8000")
    (tmp_path / "mcp_http.log").write_text("ÉCHEC : Port 8000 déjà utilisé ou interdit : le serveur MCP de l'atelier ne peut pas démarrer.\n", encoding="utf-8")
    ai._serveur_http["p"] = types.SimpleNamespace(poll=lambda: 1, returncode=1)
    monkeypatch.setattr(ai, "_joignable", lambda hote, port, delai=0.5: True)          # le port répond… tenu par un autre programme
    e = ai.etat_serveur_http()
    assert not e["ok"] and "n'a pas démarré" in e["message"] and "déjà utilisé" in e["message"]


def test_pret_quand_notre_serveur_a_pris_le_port(ai, monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_HTTP_PORT", "8000")
    (tmp_path / "mcp_http.log").write_text("Serveur MCP de l'atelier : http://localhost:8000/mcp (127.0.0.1)\n", encoding="utf-8")
    ai._serveur_http["p"] = types.SimpleNamespace(poll=lambda: None, returncode=None)
    monkeypatch.setattr(ai, "_joignable", lambda hote, port, delai=0.5: hote == "127.0.0.1")
    e = ai.etat_serveur_http()
    assert e["ok"] and e["message"].startswith("prêt sur http://localhost:8000/mcp")


def test_prises_locales_seulement_et_port_occupe():
    from atelier.adapters.mcp import server

    occupant = socket.socket()
    occupant.bind(("127.0.0.1", 0))
    occupant.listen(1)
    port = occupant.getsockname()[1]
    with pytest.raises(RuntimeError, match="déjà utilisé"):
        server._prises_locales(port)
    occupant.close()
    prises = server._prises_locales(port)
    assert prises and all(s.getsockname()[0] in ("127.0.0.1", "::1") for s in prises)  # jamais une adresse externe
    for s in prises:
        s.close()
