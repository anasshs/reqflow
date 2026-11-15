"""Coffre des secrets du poste : Gestionnaire d'identifiants Windows (et trousseau macOS / Secret Service Linux)
via la bibliothèque « keyring ». Décision de l'utilisateur du 2026-11-14 (docs/DECISIONS.md).

Règles : le coffre est chiffré et géré par le système, jamais un fichier de l'atelier ; aucune valeur n'est journalisée
ni renvoyée par l'API. Le coffre est la source des secrets (décision du 2026-11-15) : il prime sur une variable
d'environnement du poste, qui ne sert que de repli (et peut être versée dans le coffre depuis Paramètres › Connexions).
Coffre indisponible (pas de backend système) ou ATELIER_COFFRE=non : la saisie reste en mémoire de session.
"""
from __future__ import annotations

import os

SERVICE = "atelier-automatisation"


def _kr():
    if os.environ.get("ATELIER_COFFRE", "").strip().lower() in ("non", "0", "false"):
        return None
    try:
        import keyring
        from keyring.backends import fail
    except ImportError:
        return None
    try:
        k = keyring.get_keyring()
    except Exception:  # noqa: BLE001 - backend système en erreur : comme indisponible
        return None
    return None if isinstance(k, fail.Keyring) else keyring


def disponible() -> bool:
    return _kr() is not None


def nom_backend() -> str:
    k = _kr()
    return type(k.get_keyring()).__name__ if k else ""


def lire(nom: str) -> str | None:
    k = _kr()
    if not k:
        return None
    try:
        return k.get_password(SERVICE, nom)
    except Exception:  # noqa: BLE001 - un coffre illisible n'empêche jamais l'atelier de démarrer
        return None


def present(nom: str) -> bool:
    return bool(lire(nom))


def ecrire(nom: str, valeur: str):
    k = _kr()
    if not k:
        raise RuntimeError("Coffre du système indisponible : secret gardé en mémoire pour cette session seulement.")
    k.set_password(SERVICE, nom, valeur)


def effacer(nom: str) -> bool:
    k = _kr()
    if not k:
        return False
    try:
        k.delete_password(SERVICE, nom)
        return True
    except Exception:  # noqa: BLE001 - absent du coffre
        return False
