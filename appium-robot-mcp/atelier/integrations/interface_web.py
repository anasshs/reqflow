"""Client HTTP de l'interface web locale (utilisé quand le MCP tourne dans un autre processus).

Jeton : ATELIER_JETON_EVENEMENTS (variable d'environnement), envoyé dans l'en-tête X-Atelier-Jeton.
"""
from __future__ import annotations

import json
import os
import urllib.request

ENTETE_JETON = "X-Atelier-Jeton"


def base(events_url: str) -> str:
    return events_url.rsplit("/api/", 1)[0] if events_url else ""


def appeler(base_url: str, method: str, path: str, body: dict | None = None, timeout: float = 2):
    headers = {"Content-Type": "application/json"}
    jeton = os.environ.get("ATELIER_JETON_EVENEMENTS")
    if jeton:
        headers[ENTETE_JETON] = jeton
    req = urllib.request.Request(base_url + path, method=method,
                                 data=json.dumps(body, default=str).encode() if body is not None else None,
                                 headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")
