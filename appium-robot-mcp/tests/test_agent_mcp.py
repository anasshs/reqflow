"""Attribution de ce que fait un agent par le MCP : le nom déclaré à la poignée de main (clientInfo.name), pas « Cursor »
pour tout le monde."""
from __future__ import annotations

import pytest


@pytest.mark.parametrize("client,cle,libelle", [
    ("cursor-vscode 1.9", "cursor", "Cursor"),
    ("claude-code 2.1.3", "claude_code", "Claude Code"),
    ("claude-ai 0.1", "claude", "Claude Desktop"),
    ("", "cursor", "Cursor"),  # appel direct ou client muet : défaut historique
])
def test_identification_de_l_agent(client, cle, libelle):
    from atelier.domain import agent_mcp

    jeton = agent_mcp.definir(client)
    try:
        assert (agent_mcp.cle(), agent_mcp.libelle(), agent_mcp.source()) == (cle, libelle, f"{libelle} (MCP)")
    finally:
        agent_mcp.reinitialiser(jeton)
    assert agent_mcp.libelle() == "Cursor"  # rien ne déborde sur l'appel suivant


def test_revue_dit_quel_agent_a_genere_le_script(projet):
    from atelier.domain import agent_mcp
    from atelier.generation import studio

    (projet / "tests").mkdir(exist_ok=True)
    (projet / "tests" / "t.robot").write_text("*** Test Cases ***\nT\n    Log    x\n", "utf-8")
    jeton = agent_mcp.definir("claude-code")
    try:
        r = studio.entrer_en_revue("tests/t.robot", "cursor")
    finally:
        agent_mcp.reinitialiser(jeton)
    assert r["historique"][-1]["commentaire"] == "généré (cursor) par Claude Code" and r["historique"][-1]["agent"] == "claude_code"
    assert studio.entrer_en_revue("tests/t.robot", "cursor")["historique"][-1]["commentaire"] == "généré (cursor)"  # Cursor : inchangé
    assert studio.entrer_en_revue("tests/t.robot", "bdd")["historique"][-1]["commentaire"] == "généré (bdd)"
