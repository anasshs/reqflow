"""Claude Code : configuration MCP du projet (.mcp.json) et règles au format Claude Code (CLAUDE.md + skills)."""
import json


def test_mcp_du_projet_pour_claude_code(projet, monkeypatch):
    from atelier.integrations import agents_ia

    monkeypatch.delenv("MCP_HTTP_PORT", raising=False)
    assert agents_ia.fichier_config("claude_code") == projet / ".mcp.json"
    e = agents_ia.entree(8765, "claude_code")
    assert e["type"] == "stdio" and e["args"][0].endswith("server.py")
    r = agents_ia.installer("claude_code", 8765)
    d = json.loads((projet / ".mcp.json").read_text("utf-8"))
    assert d["mcpServers"]["appium-robot"] == e and r["fichier"].endswith(".mcp.json")
    assert agents_ia.etat(8765)["agents"]["claude_code"]["a_jour"]
    monkeypatch.setenv("MCP_HTTP_PORT", "8000")
    assert agents_ia.entree(8765, "claude_code") == {"type": "http", "url": "http://localhost:8000/mcp"}


def test_regles_au_format_claude_code(projet):
    from atelier.integrations import claude_code

    (projet / "CLAUDE.md").write_text("# Notes de l'équipe\nGarder ceci.\n", "utf-8")
    r = claude_code.installer()
    assert "CLAUDE.md" in r["copiees"] and ".claude/skills/atelier-robot-expert/SKILL.md" in r["copiees"]
    md = (projet / "CLAUDE.md").read_text("utf-8")
    assert md.startswith("# Notes de l'équipe\nGarder ceci.") and "@.claude/atelier/security.md" in md
    skill = (projet / ".claude" / "skills" / "atelier-robot-expert" / "SKILL.md").read_text("utf-8")
    assert skill.startswith("---\nname: atelier-robot-expert\ndescription: ") and "automaticien senior" in skill
    assert (projet / ".claude" / "atelier" / "security.md").exists()
    assert claude_code.installer()["copiees"] == []                    # rien à refaire
    f = projet / ".claude" / "skills" / "atelier-discovery" / "SKILL.md"
    f.write_text(f.read_text("utf-8") + "\nAjout local.\n", "utf-8")
    (projet / "CLAUDE.md").write_text(md + "\nAutre note.\n", "utf-8")
    assert all(x["fichier"] != "CLAUDE.md" or x["statut"] == "identique" for x in claude_code.apercu())
    assert {x["fichier"]: x["statut"] for x in claude_code.apercu()}[".claude/skills/atelier-discovery/SKILL.md"] == "modifié localement"
    r = claude_code.installer()
    assert ".claude/skills/atelier-discovery/SKILL.md" in r["ignorees"] and "Ajout local." in f.read_text("utf-8")
    r = claude_code.installer(ecraser=True)
    assert "Ajout local." not in f.read_text("utf-8") and r["sauvegardes"]
