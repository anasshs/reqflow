"""Liaison avec les agents IA (Cursor, Claude Desktop) : configuration MCP du poste et règles du projet.

- La configuration MCP ne contient que le Python de l'atelier, server.py et l'adresse de l'interface locale :
  ni chemin de projet (le serveur MCP suit le projet actif de l'atelier), ni secret (variables d'environnement ou
  coffre du système, lus par le serveur lui-même).
- Installer = fusionner l'entrée « appium-robot » dans le fichier de configuration de l'agent sur ce poste, en gardant
  les autres serveurs et une copie de sauvegarde (.bak) du fichier précédent.
- Les règles Cursor (.mdc) sont copiées dans <projet de tests>/.cursor/rules/ : elles ne contiennent aucun chemin
  local et peuvent être versionnées avec le projet ; un fichier existant différent n'est remplacé qu'avec accord.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from atelier.domain import projet

NOM = "appium-robot"
REGLES = {"atelier-automatisation.mdc": "cursor_rules_automatisation.mdc", "atelier-discovery.mdc": "cursor_rules_discovery.mdc"}


def fichier_config(agent: str) -> Path:
    if agent == "cursor":
        return Path.home() / ".cursor" / "mcp.json"
    if agent == "claude":
        if os.name == "nt":
            return Path(os.environ.get("APPDATA", str(Path.home()))) / "Claude" / "claude_desktop_config.json"
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"
    raise ValueError("Agent : cursor ou claude.")


def entree(port: int) -> dict:
    """Entrée « appium-robot » : Python de l'atelier (son environnement virtuel), server.py, interface locale."""
    env = {"WEB_EVENTS_URL": f"http://127.0.0.1:{port}/api/events"}
    for v in ("APPIUM_URL", "ATELIER_JETON_FICHIER", "ATELIER_PROJETS"):  # réglages non secrets du poste, s'ils sont imposés
        if os.environ.get(v):
            env[v] = os.environ[v]
    return {"command": sys.executable, "args": [str(projet.RACINE_OUTIL / "server.py")], "env": env}


def config(port: int) -> dict:
    return {"mcpServers": {NOM: entree(port)}}


def _lire(f: Path) -> dict:
    if not f.exists() or not f.read_text("utf-8").strip():
        return {}
    try:
        return json.loads(f.read_text("utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{f} n'est pas un JSON valide ({e.msg}, ligne {e.lineno}) : le corriger ou le renommer, puis recommencer.")


def etat(port: int) -> dict:
    """Pour chaque agent : fichier, installé ou non, à jour ou non (chemins / port différents) ; règles du projet."""
    attendu = entree(port)
    agents = {}
    for a in ("cursor", "claude"):
        f = fichier_config(a)
        try:
            actuel = (_lire(f).get("mcpServers") or {}).get(NOM)
            erreur = ""
        except ValueError as e:
            actuel, erreur = None, str(e)
        agents[a] = {"fichier": str(f), "installe": bool(actuel), "a_jour": actuel == attendu, "erreur": erreur,
                     "dossier_agent": f.parent.exists()}
    regles = {}
    for cible, source in REGLES.items():
        f = projet.PROJECT_DIR / ".cursor" / "rules" / cible
        src = projet.RACINE_OUTIL / source
        regles[cible] = {"present": f.exists(), "a_jour": f.exists() and src.exists() and f.read_bytes() == src.read_bytes()}
    return {"agents": agents, "regles": regles, "projet": str(projet.PROJECT_DIR), "config": config(port)}


def installer(agent: str, port: int) -> dict:
    """Ajoute / met à jour l'entrée « appium-robot » dans la configuration de l'agent (autres serveurs conservés)."""
    f = fichier_config(agent)
    d = _lire(f)
    sauvegarde = ""
    if f.exists():
        sauvegarde = str(f) + ".bak"
        shutil.copyfile(f, sauvegarde)
    d.setdefault("mcpServers", {})[NOM] = entree(port)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), "utf-8")
    os.replace(tmp, f)
    return {"agent": agent, "fichier": str(f), "sauvegarde": sauvegarde}


def installer_regles(ecraser: bool = False) -> dict:
    """Copie les règles Cursor dans le projet de tests actif ; un fichier modifié localement n'est remplacé qu'avec
    ecraser=True (pas d'écrasement implicite)."""
    dossier = projet.safe_path(".cursor/rules")
    dossier.mkdir(parents=True, exist_ok=True)
    out = {"copiees": [], "differentes": []}
    for cible, source in REGLES.items():
        src, f = projet.RACINE_OUTIL / source, dossier / cible
        if f.exists() and f.read_bytes() != src.read_bytes() and not ecraser:
            out["differentes"].append(cible)
            continue
        shutil.copyfile(src, f)
        out["copiees"].append(cible)
    return out
