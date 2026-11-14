"""Bus d'événements interne.

Les moteurs publient (session ouverte, action faite, carte modifiée, run lancé…) sans savoir qui
écoute ; les façades s'abonnent (l'interface web dans son processus, le MCP qui relaie vers
l'interface par HTTP). Un abonné qui échoue ne fait jamais échouer l'outil qui publie.
"""
from __future__ import annotations

import threading
from typing import Callable, Iterable

_abonnes: list[tuple[Callable[[dict], None], frozenset | None]] = []
_verrou = threading.Lock()


def abonner(fn: Callable[[dict], None], types: Iterable[str] | None = None) -> Callable[[], None]:
    """Abonne fn aux événements (tous, ou seulement les types donnés). Renvoie le désabonnement."""
    entree = (fn, frozenset(types) if types is not None else None)
    with _verrou:
        _abonnes.append(entree)

    def desabonner():
        with _verrou:
            if entree in _abonnes:
                _abonnes.remove(entree)
    return desabonner


def a_des_abonnes(type_ev: str) -> bool:
    with _verrou:
        return any(t is None or type_ev in t for _, t in _abonnes)


def publier(ev: dict) -> None:
    """Diffuse un événement à chaque abonné intéressé (copie par abonné, erreurs ignorées)."""
    with _verrou:
        cibles = [fn for fn, t in _abonnes if t is None or ev.get("type") in t]
    for fn in cibles:
        try:
            fn(dict(ev))
        except Exception:
            pass


def reinitialiser() -> None:
    """Retire tous les abonnés (tests)."""
    with _verrou:
        _abonnes.clear()
