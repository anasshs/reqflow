"""Charge l'application FastAPI de l'interface web via le point d'entrée historique web/app.py."""
from __future__ import annotations

import importlib.util
import sys

from conftest import RACINE

_cache: dict = {}


def charger_app_web():
    if "mod" not in _cache:
        sys.path.insert(0, str(RACINE / "web"))
        spec = importlib.util.spec_from_file_location("atelier_web_app_test", RACINE / "web" / "app.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _cache["mod"] = mod
    return _cache["mod"].app


def module_web():
    charger_app_web()
    return _cache["mod"]
