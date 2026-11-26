"""Lecture YAML rapide : l'analyseur en C (libyaml, livré avec PyYAML) quand il est présent, sinon l'analyseur Python.

Constat du 2026-11-22 sur un vrai projet de tests (75 fichiers, 490 Ko) : yaml.safe_load (analyseur Python) prenait
1,9 s là où le même chargeur en C prend 0,24 s, pour un résultat identique. Les écrans de l'atelier relisent la carte et
les réglages des centaines de fois par affichage : #studio attendait jusqu'à 38 s.

lire() garde en mémoire le résultat de l'analyse tant que le texte du fichier ne change pas (comparé au texte, pas à la
date : sous Windows deux écritures rapprochées peuvent garder la même date et la même taille), et rend une copie (un
appelant peut modifier ce qu'il reçoit sans toucher la mémoire). Aucune écriture : le fichier reste la seule source.
"""
from __future__ import annotations

import copy
import threading
from pathlib import Path

import yaml

_CHARGEUR = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
_MEMOIRE: dict[str, tuple[str, object]] = {}
_VERROU = threading.Lock()
_MAX = 4000  # fichiers gardés au plus ; au-delà la mémoire repart de zéro


def charger(texte):
    """Équivalent de yaml.safe_load (même sécurité : aucune construction d'objet Python arbitraire), en C si possible."""
    return yaml.load(texte, Loader=_CHARGEUR)  # noqa: S506 — chargeur « safe » (CSafeLoader / SafeLoader)


def lire(p: Path, defaut=None):
    """Contenu YAML du fichier p (defaut s'il n'existe pas ou s'il est vide), analysé seulement si son texte a changé."""
    try:
        texte = p.read_text("utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return defaut
    cle = str(p)
    with _VERROU:
        m = _MEMOIRE.get(cle)
    if not m or m[0] != texte:
        data = charger(texte)
        with _VERROU:
            if len(_MEMOIRE) >= _MAX:
                _MEMOIRE.clear()
            _MEMOIRE[cle] = m = (texte, data)
    return defaut if m[1] is None else copy.deepcopy(m[1])


def oublier(p: Path) -> None:
    """Après une écriture : la prochaine lecture repart du fichier (même si date et taille semblent inchangées)."""
    with _VERROU:
        _MEMOIRE.pop(str(p), None)
