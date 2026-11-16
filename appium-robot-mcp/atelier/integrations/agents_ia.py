"""Liaison avec les agents IA (Cursor, Claude Desktop) : configuration MCP du poste et règles du projet.

- La configuration MCP ne contient que le Python de l'atelier, server.py et l'adresse de l'interface locale :
  ni chemin de projet (le serveur MCP suit le projet actif de l'atelier), ni secret (variables d'environnement ou
  coffre du système, lus par le serveur lui-même).
- Installer = fusionner l'entrée « appium-robot » dans le fichier de configuration de l'agent sur ce poste, en gardant
  les autres serveurs et une copie de sauvegarde (.bak) du fichier précédent.
- Les règles Cursor (11 fichiers .mdc, versionnés par projet : atelier/integrations/regles_cursor.py) sont copiées
  dans <projet de tests>/.cursor/rules/ : aucun chemin local ; un fichier modifié localement n'est remplacé qu'avec accord.
- verifier() lance réellement le serveur MCP (stdio) et liste ses outils : la connexion est prouvée, pas supposée.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from atelier.domain import projet

NOM = "appium-robot"


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
    from atelier.integrations import regles_cursor

    regles = {x["fichier"]: {"present": x["statut"] != "nouveau", "a_jour": x["statut"] == "identique", "statut": x["statut"]}
              for x in regles_cursor.apercu()}
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
    """Copie les règles Cursor (version active du projet) dans le projet de tests ; un fichier modifié localement
    n'est remplacé qu'avec ecraser=True (sauvegarde .bak ; pas d'écrasement implicite)."""
    from atelier.integrations import regles_cursor

    tous = [r[0] for r in regles_cursor.RUBRIQUES] if ecraser else []
    r = regles_cursor.synchroniser(tous)
    return {"copiees": r["copiees"], "differentes": r["ignorees"], "identiques": r["identiques"], "sauvegardes": r["sauvegardes"]}


def verifier(port: int, delai_s: int = 40) -> dict:
    """Démarre le serveur MCP comme le fera Cursor (même commande, stdio), fait l'initialisation et liste les outils."""
    import subprocess
    import time

    e = entree(port)
    debut = time.monotonic()
    env = {**os.environ, **e["env"], "PYTHONIOENCODING": "utf-8"}
    p = subprocess.Popen([e["command"], *e["args"]], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", env=env)
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                                                           "clientInfo": {"name": "atelier-verification", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    try:
        out, err = p.communicate("".join(json.dumps(m) + "\n" for m in msgs), timeout=delai_s)
    except subprocess.TimeoutExpired:
        p.kill()
        out, err = p.communicate()
    reponses = {}
    for l in (out or "").splitlines():
        try:
            m = json.loads(l)
        except ValueError:
            continue
        if isinstance(m, dict) and "id" in m:
            reponses[m["id"]] = m
    outils = [t["name"] for t in ((reponses.get(2) or {}).get("result") or {}).get("tools", [])]
    ok = bool(outils) and "result" in (reponses.get(1) or {})
    return {"ok": ok, "outils": len(outils), "serveur": ((reponses.get(1) or {}).get("result") or {}).get("serverInfo", {}),
            "duree_s": round(time.monotonic() - debut, 1), "commande": " ".join([e["command"], *e["args"]]),
            "erreur": "" if ok else (err or "")[-600:] or "aucune réponse du serveur MCP"}
