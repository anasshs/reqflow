"""
Appium Robot MCP — façade MCP (stdio) pour Claude Desktop et Cursor.

Enregistre les outils de atelier.adapters.facade (mêmes noms, paramètres et descriptions que le
prototype) et, si WEB_EVENTS_URL est défini, relaie les événements des moteurs vers l'interface
web (écran de contrôle). Aucune logique métier ici.
"""
from __future__ import annotations

import threading

from mcp.server.fastmcp import FastMCP

from atelier.adapters import facade
from atelier.adapters.facade import *  # noqa: F401,F403  (outils exposés aussi en Python : server.tap…)
from atelier.domain import evenements
from atelier.integrations import interface_web

mcp = FastMCP("appium-robot")
for _fn in facade.OUTILS:
    mcp.tool()(_fn)


def _relayer(ev: dict):
    """Envoie l'événement à l'interface web sans jamais bloquer ni faire échouer l'outil."""
    url = facade.WEB_EVENTS_URL
    if not url:
        return
    ev = {"source": "mcp", **ev}

    def send():
        try:
            interface_web.appeler(interface_web.base(url), "POST", "/api/events", ev)
        except Exception:
            pass
    threading.Thread(target=send, daemon=True).start()


if facade.WEB_EVENTS_URL:
    evenements.abonner(_relayer)


# --------------------------------------------------------------------------- rétrocompatibilité
# Noms internes du prototype encore utilisés par des scripts ou des règles existantes.
from atelier.discovery import carte as _carte_mod  # noqa: E402
from atelier.discovery import session as _session  # noqa: E402
from atelier.discovery.exploration import explorer as _explorer  # noqa: E402,F401
from atelier.discovery.parsing import _xq, parse_elements as _parse_elements  # noqa: E402,F401
from atelier.discovery.session import (  # noqa: E402,F401
    current_elements as _current_elements, driver as _driver, is_web as _is_web, rect_ratio as _rect_ratio,
    screenshot_png, webb as _webb, window_size)
from atelier.domain.projet import safe_path as _safe_path, slug as _slug  # noqa: E402,F401
from atelier.generation.locators import robot_escape as _robot_escape  # noqa: E402,F401
from atelier.integrations.appium import by as _by  # noqa: E402,F401

_state = _session.etat
_ecran_resume = _carte_mod.resume_ecran
APPIUM_URL = _session.APPIUM_URL


def __getattr__(nom: str):
    """PROJECT_DIR, SNAP_DIR et WEB_EVENTS_URL lus en direct (ils peuvent changer après l'import)."""
    from atelier.domain import projet

    if nom in ("PROJECT_DIR", "SNAP_DIR"):
        return getattr(projet, nom)
    if nom == "WEB_EVENTS_URL":
        return facade.WEB_EVENTS_URL
    raise AttributeError(nom)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
