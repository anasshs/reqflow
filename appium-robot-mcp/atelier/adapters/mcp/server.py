"""
Appium Robot MCP — façade MCP (stdio) pour Claude Desktop et Cursor.

Enregistre les outils de atelier.adapters.facade (mêmes noms, paramètres et descriptions que le
prototype) et, si WEB_EVENTS_URL est défini, relaie les événements des moteurs vers l'interface
web (écran de contrôle). Aucune logique métier ici.
"""
from __future__ import annotations

import functools
import inspect
import threading

from mcp.server.fastmcp import FastMCP

from atelier.adapters import facade
from atelier.adapters.facade import *  # noqa: F401,F403  (outils exposés aussi en Python : server.tap…)
from atelier.domain import evenements
from atelier.integrations import interface_web

mcp = FastMCP("appium-robot")


_coffre_lu = {"t": 0.0}


_image = {"t": 0.0}


_client = {"v": None}


def _client_mcp() -> str:
    """Client MCP déclaré à la poignée de main (ex. « cursor 1.2.3 ») ; le protocole ne transmet pas le modèle."""
    if _client["v"] is None:
        try:
            info = mcp.get_context().session.client_params.clientInfo
            _client["v"] = f"{info.name} {info.version or ''}".strip()
        except Exception:  # noqa: BLE001 - hors requête ou client muet
            return ""
    return _client["v"]


def _publier_activite(nom: str, etat: str, args: dict | None = None, **extra):
    """Appel d'outil visible en temps réel dans l'atelier (vue « Cursor en direct », console Cursor) ; jamais bloquant."""
    try:
        from atelier.domain import activite_agent

        evenements.publier({"type": "mcp_outil", "nom": nom, "etat": etat, "famille": activite_agent.famille(nom), "client": _client_mcp(),
                            **({"args": activite_agent.resumer_arguments(nom, args or {})} if args is not None else {}), **extra})
    except Exception:  # noqa: BLE001
        pass


def _envoyer_image(nom: str):
    """Navigateur piloté par l'agent : il vit dans ce processus, l'atelier ne peut pas le voir ; une image (JPEG
    réduite) lui est envoyée après chaque action visible. Mobile : l'atelier lit déjà l'écran par adb / simctl."""
    import time

    from atelier.discovery import session
    from atelier.domain import activite_agent

    if nom not in activite_agent.ACTIONS_ECRAN or not facade.WEB_EVENTS_URL or time.time() - _image["t"] < 0.5:
        return
    try:
        if not session.is_web():
            return
        import base64

        _image["t"] = time.time()
        png = session.screenshot_png()
        threading.Thread(target=lambda: interface_web.appeler(interface_web.base(facade.WEB_EVENTS_URL), "POST", "/api/mcp/image",
                                                             {"png": base64.b64encode(png).decode(), "outil": nom}, timeout=5), daemon=True).start()
    except Exception:  # noqa: BLE001
        pass


PAUSE_MAX_S = 900


def _attendre_autorisation(nom: str, delai: float = 1.5):
    """Pilotage par l'automaticien (vue « Avec Cursor (en direct) ») : en pause, l'outil attend la reprise ; arrêté,
    il échoue avec un message que l'agent lit. Atelier injoignable : l'outil continue (jamais bloqué par l'interface)."""
    import time

    if not facade.WEB_EVENTS_URL:
        return
    base = interface_web.base(facade.WEB_EVENTS_URL)
    debut, annonce = time.time(), False
    while True:
        try:
            etat = interface_web.appeler(base, "GET", "/api/mcp/controle", timeout=1).get("etat", "actif")
        except Exception:  # noqa: BLE001
            return
        if etat == "actif":
            return
        if etat == "arret":
            raise RuntimeError("Arrêté par l'automaticien dans l'atelier (Automation Studio › Construire) : ne rien faire de plus, "
                               "attendre ses instructions dans le chat.")
        if not annonce:
            _publier_activite(nom, "pause")
            annonce = True
        if time.time() - debut > PAUSE_MAX_S:
            raise RuntimeError("En pause depuis plus de 15 minutes dans l'atelier : attendre les instructions de l'automaticien.")
        time.sleep(delai)


def _suivre_projet(fn):
    """Avant chaque outil : projet actif de l'atelier et secrets du coffre (même signature et description que l'outil).
    Pendant : début et fin de l'appel publiés à l'atelier (temps réel), image du navigateur après une action."""
    @functools.wraps(fn)
    def outil(*a, **k):
        import inspect
        import time

        try:
            args = dict(inspect.signature(fn).bind_partial(*a, **k).arguments)
        except TypeError:
            args = dict(k)
        _attendre_autorisation(fn.__name__)
        import uuid

        appel = uuid.uuid4().hex[:10]  # relie le début et la fin d'un même appel (console Cursor)
        _publier_activite(fn.__name__, "debut", args, appel=appel)
        t0 = time.time()
        try:
            r = _executer(*a, **k)
        except Exception as e:
            _publier_activite(fn.__name__, "erreur", appel=appel, duree=round(time.time() - t0, 2), message=str(e)[:300])
            raise
        from atelier.domain import activite_agent

        _publier_activite(fn.__name__, "fin", appel=appel, duree=round(time.time() - t0, 2), resultat=activite_agent.resumer_resultat(r))
        _envoyer_image(fn.__name__)
        return r

    def _executer(*a, **k):
        try:
            import time

            from atelier.domain import projets

            projets.suivre_actif()
            if time.time() - _coffre_lu["t"] > 10:
                _coffre_lu["t"] = time.time()
                projets.charger_coffre()
        except Exception:  # noqa: BLE001 - le suivi du projet ne fait jamais échouer un outil
            pass
        return fn(*a, **k)
    return outil


for _fn in facade.OUTILS:
    # description sans l'indentation du code : avant Python 3.13, __doc__ garde les espaces de début des lignes suivantes
    mcp.tool(description=inspect.cleandoc(_fn.__doc__ or ""))(_suivre_projet(_fn))


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


def main(argv: list[str] | None = None):
    """stdio par défaut (Cursor lance le serveur) ; « --http » : HTTP streamable sur http://127.0.0.1:<MCP_HTTP_PORT, 8000>/mcp,
    pour une équipe Cursor qui n'autorise que des URL (l'atelier le démarre lui-même, voir agents_ia)."""
    import os
    import sys

    args = sys.argv[1:] if argv is None else argv
    try:
        from atelier.domain import projets

        projets.au_demarrage()  # dernier projet actif de l'atelier, connexions et coffre (sauf ROBOT_PROJECT_DIR imposé)
    except Exception:  # noqa: BLE001
        pass
    if "--http" in args:
        from atelier.integrations import agents_ia

        mcp.settings.host = "127.0.0.1"  # interface locale uniquement, jamais exposée
        mcp.settings.port = agents_ia.port_http() or 8000
        if os.environ.get("ATELIER_SURVEILLER_PARENT") == "1":  # démarré par l'atelier : s'arrêter avec lui
            def _surveiller():
                try:
                    while sys.stdin.read(4096):
                        pass
                finally:
                    os._exit(0)

            threading.Thread(target=_surveiller, daemon=True, name="surveillance-atelier").start()
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
