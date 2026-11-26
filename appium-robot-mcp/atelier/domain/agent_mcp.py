"""Agent qui appelle les outils du MCP (Cursor, Claude Code, Claude Desktop) : pour attribuer ce qu'il fait.

Le client MCP déclare son nom à la poignée de main (clientInfo.name : « cursor-vscode », « claude-code »,
« claude-ai »…). Le serveur le pose ici pour la durée de chaque appel d'outil (variable de contexte : en mode HTTP,
plusieurs agents peuvent être connectés en même temps). Les journaux, propositions et revues l'utilisent au lieu
d'écrire « Cursor » pour tout ce qui passe par le MCP. Sans nom déclaré (appel direct, tests), « Cursor » reste le
défaut historique.
"""
from __future__ import annotations

import contextvars

_courant: contextvars.ContextVar[str] = contextvars.ContextVar("agent_mcp", default="")

# (motif dans le nom déclaré, clé, libellé) : le plus précis d'abord
CONNUS = (("claude-code", "claude_code", "Claude Code"), ("claude code", "claude_code", "Claude Code"),
          ("claude", "claude", "Claude Desktop"), ("cursor", "cursor", "Cursor"))
DEFAUT = ("cursor", "Cursor")


def definir(nom_client: str) -> contextvars.Token:
    return _courant.set(str(nom_client or ""))


def reinitialiser(jeton: contextvars.Token) -> None:
    _courant.reset(jeton)


def _identifier(nom_client: str) -> tuple[str, str]:
    n = (nom_client or "").casefold()
    return next(((cle, lib) for motif, cle, lib in CONNUS if motif in n), DEFAUT)


def libelle_de(nom_client: str) -> str:
    """Libellé d'un client déclaré (« claude-code 2.1.3 » → « Claude Code ») : console de l'agent, état de connexion."""
    return _identifier(nom_client)[1] if (nom_client or "").strip() else ""


def cle() -> str:
    """« cursor », « claude_code » ou « claude » (Claude Desktop)."""
    return _identifier(_courant.get())[0]


def libelle() -> str:
    """« Cursor », « Claude Code » ou « Claude Desktop »."""
    return _identifier(_courant.get())[1]


def source() -> str:
    """Provenance d'un dépôt par le MCP : « Claude Code (MCP) », « Cursor (MCP) »…"""
    return f"{libelle()} (MCP)"
