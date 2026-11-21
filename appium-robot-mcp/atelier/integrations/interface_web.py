"""Client HTTP de l'interface web locale (MCP dans un autre processus, listener Robot).

Jeton des processus locaux : ATELIER_JETON_EVENEMENTS, sinon le fichier écrit par l'interface au
démarrage (ATELIER_JETON_FICHIER, défaut ~/.atelier-automatisation.jeton), envoyé dans
l'en-tête X-Atelier-Jeton.
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

ENTETE_JETON = "X-Atelier-Jeton"
FICHIER_JETON_DEFAUT = "~/.atelier-automatisation.jeton"


def base(events_url: str) -> str:
    return events_url.rsplit("/api/", 1)[0] if events_url else ""


def jeton() -> str:
    j = os.environ.get("ATELIER_JETON_EVENEMENTS")
    if j:
        return j
    try:
        return Path(os.environ.get("ATELIER_JETON_FICHIER", FICHIER_JETON_DEFAUT)).expanduser().read_text().strip()
    except OSError:
        return ""


def entetes() -> dict:
    h = {"Content-Type": "application/json"}
    j = jeton()
    if j:
        h[ENTETE_JETON] = j
    return h


def appeler(base_url: str, method: str, path: str, body: dict | None = None, timeout: float = 2):
    req = urllib.request.Request(base_url + path, method=method,
                                 data=json.dumps(body, default=str).encode() if body is not None else None,
                                 headers=entetes())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")
