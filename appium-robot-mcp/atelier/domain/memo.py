"""Mémoire d'un seul calcul (un ticket du Kanban, une page) : une lecture coûteuse (index des tests, inventaire du dépôt
Robot) n'est faite qu'une fois pendant ce calcul, puis oubliée. Hors d'une portée, rien n'est gardé : chaque appel
relit, comme avant. Les valeurs gardées ne doivent pas être modifiées par les appelants."""
from __future__ import annotations

import contextvars
from contextlib import contextmanager

_MEMOIRE: contextvars.ContextVar[dict | None] = contextvars.ContextVar("memo_calcul", default=None)


@contextmanager
def portee():
    """Ouvre une portée (imbriquée : la portée extérieure est réutilisée)."""
    if _MEMOIRE.get() is not None:
        yield
        return
    jeton = _MEMOIRE.set({})
    try:
        yield
    finally:
        _MEMOIRE.reset(jeton)


def memoiser(cle, calcul):
    m = _MEMOIRE.get()
    if m is None:
        return calcul()
    if cle not in m:
        m[cle] = calcul()
    return m[cle]
