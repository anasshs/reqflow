"""Validation des steps Gherkin proposés par un agent externe (Cursor, Claude Desktop) : le step
s'affiche dans l'interface web, qui renvoie la décision (validé, corrigé, refusé)."""
from __future__ import annotations

import time

from atelier.integrations import interface_web


def proposer(step: dict, base_url: str, attendre_validation: bool = True, delai_max_s: int = 600,
             pause_s: float = 1.0) -> dict:
    if not base_url:
        return {"decision": "sans validation", "raison": "interface web non configurée"}
    try:
        pid = interface_web.appeler(base_url, "POST", "/api/externe/step", step)["id"]
    except Exception as e:
        return {"decision": "sans validation", "raison": f"interface web injoignable : {e}"}
    if not attendre_validation:
        return {"decision": "proposé", "id": pid}
    fin = time.time() + delai_max_s
    while time.time() < fin:
        try:
            r = interface_web.appeler(base_url, "GET", f"/api/externe/reponse/{pid}")
        except Exception:
            r = {}
        if r.get("decision"):
            return {"decision": r["decision"], "correction": r.get("texte", "")}
        time.sleep(pause_s)
    return {"decision": "sans réponse", "raison": f"pas de validation en {delai_max_s} s"}
