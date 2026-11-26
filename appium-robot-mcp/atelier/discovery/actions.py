"""Actions sur le device ou le navigateur, avec surlignage de la cible et carte passive."""
from __future__ import annotations

from atelier.discovery import session
from atelier.discovery.observation import avec_carte


def open_url(url: str) -> dict:
    if not session.is_web():
        raise RuntimeError("open_url est réservé aux sessions web.")
    info = avec_carte({"type": "open_url", "url": url}, lambda: session.webb().goto(url))
    session.action_faite("open_url", {"url": url})
    return info


def tap(locator: str, timeout: float = 10) -> str:
    session.montrer_cible(locator, "tap")
    avec_carte({"type": "tap", "locator": locator}, lambda: session.click_raw(locator, timeout))
    session.action_faite("tap", {"locator": locator})
    return f"Tap effectué sur {locator}"


def type_text(locator: str, text: str, clear: bool = True, hide_keyboard: bool = True, affiche: str | None = None) -> str:
    """affiche : texte publié à la place de la valeur saisie (référence {{var:CLE}} d'une donnée résolue côté serveur)."""
    session.montrer_cible(locator, "saisie")

    def saisir():
        if session.is_web():
            session.webb().fill(locator, text, clear)
            return
        el = session.find(locator)
        if clear:
            el.clear()
        el.send_keys(text)
        if hide_keyboard:
            try:
                session.driver().hide_keyboard()
            except Exception:
                pass
    avec_carte({"type": "type_text", "locator": locator}, saisir)  # la valeur saisie n'est jamais stockée
    session.action_faite("type_text", {"locator": locator, "text": text if affiche is None else affiche})
    return f"Saisie effectuée dans {locator}"


def swipe(direction: str = "up", ratio: float = 0.6, duration_ms: int = 600) -> str:
    if session.is_web():
        avec_carte({"type": "swipe", "direction": direction}, lambda: session.webb().scroll(direction, ratio))
        session.action_faite("swipe", {"direction": direction})
        return f"Défilement {direction} effectué"
    size = session.driver().get_window_size()
    w, h = size["width"], size["height"]
    cx, cy, dx, dy = w // 2, h // 2, int(w * ratio / 2), int(h * ratio / 2)
    moves = {"up": (cx, cy + dy, cx, cy - dy), "down": (cx, cy - dy, cx, cy + dy),
             "left": (cx + dx, cy, cx - dx, cy), "right": (cx - dx, cy, cx + dx, cy)}
    if direction not in moves:
        raise ValueError("direction : up, down, left ou right")
    avec_carte({"type": "swipe", "direction": direction},
               lambda: session.driver().swipe(*moves[direction], duration_ms))
    session.action_faite("swipe", {"direction": direction})
    return f"Swipe {direction} effectué"


def press_back() -> str:
    avec_carte({"type": "press_back"}, session.back_raw)
    session.action_faite("press_back", {})
    return "Retour effectué"


def wait_for(locator: str, timeout: float = 15) -> str:
    session.montrer_cible(locator, "attente")
    if session.is_web():
        session.webb().wait(locator, timeout)
    else:
        session.find(locator, timeout)
    return f"{locator} présent"
