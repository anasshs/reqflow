"""Observation passive : chaque action faite pendant une session enregistre l'écran courant et la
transition dans la carte de l'application (MAP_PASSIVE=0 pour désactiver)."""
from __future__ import annotations

import os
import time

from atelier.discovery import carte, session
from atelier.domain import evenements

MAP_PASSIF = os.environ.get("MAP_PASSIVE", "1") != "0"


def carte_active() -> bool:
    try:
        return MAP_PASSIF and bool(session.etat["platform"]) and bool(carte.app_courante())
    except Exception:
        return False


def contexte() -> str:
    try:
        if session.is_web():
            return carte.motif_url(session.webb().info()["url"])
        if session.etat["platform"] == "android":
            return session.driver().current_activity or ""
    except Exception:
        pass
    return ""


def attendre_stable(timeout: float = 4.0) -> list[dict]:
    """Attend que l'écran ne bouge plus (fin d'animation / de chargement) avant de l'identifier."""
    els = session.current_elements(150)
    prev, t0 = None, time.time()
    while time.time() - t0 < timeout:
        sig = carte.signature(els)
        if sig == prev:
            return els
        prev = sig
        time.sleep(0.6)
        els = session.current_elements(150)
    return els


def hors_application() -> str:
    """Paquet Android au premier plan quand ce n'est pas celui de l'application (bureau, réglages, autre app) ; vide
    sinon, ou si on ne sait pas le dire (web, iOS, paquet non déclaré, driver muet)."""
    try:
        if session.etat.get("platform") != "android" or session.etat.get("driver") is None:
            return ""
        attendu = ((carte.config_app().get("android") or {}).get("app_package") or "").strip()
        courant = (session.driver().current_package or "").strip()
        return courant if attendu and courant and courant != attendu else ""
    except Exception:  # noqa: BLE001 - dans le doute, on observe comme avant
        return ""


def observer(els: list[dict] | None = None, test_key: str | None = None) -> dict | None:
    """Observe l'écran courant dans la carte (créé s'il est inconnu). Hors de l'application (bureau Android, autre
    app) : rien n'est enregistré, pour ne pas ajouter d'écran fantôme à la carte."""
    if not carte_active() or hors_application():
        return None
    obs = carte.observer(els if els is not None else session.current_elements(150), session.etat["platform"],
                         contexte(), build=carte.config_app().get("build", ""),
                         vignette_cb=session.screenshot_png, test_key=test_key)
    if obs.get("nouveau"):
        evenements.publier({"type": "carte_change", "ecran": obs})
    return obs


def avec_carte(action: dict, fn):
    """Exécute une action et enregistre la transition observée (si l'écran change)."""
    if not carte_active():
        return fn()
    try:
        avant = observer()
    except Exception:
        avant = None
    t0 = time.time()
    res = fn()
    try:
        apres = observer(attendre_stable())
        if avant and apres and avant["id"] != apres["id"]:
            plat = session.etat["platform"]
            action["cle"] = carte.cle_pour_locator(avant["id"], action.get("locator", ""), plat)
            carte.enregistrer_transition(avant["id"], apres["id"], plat, action,
                                         duree_ms=int((time.time() - t0) * 1000))
            evenements.publier({"type": "carte_change", "transition": [avant["id"], apres["id"]]})
    except Exception:
        pass
    return res
