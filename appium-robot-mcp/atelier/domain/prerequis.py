"""Prérequis du poste vérifiés au lancement de l'atelier : projet de tests choisi, navigateur web installé.

Le projet de tests est le dossier où l'atelier écrit (carte, locators, scénarios, releases…). Sans réglage, c'est le
dossier courant : lancé depuis `appium-robot-mcp`, l'atelier écrirait dans son propre code. On le dit au lancement
(console), dans la pastille « État de l'atelier » et par un bandeau dans l'interface, avec la façon de corriger.

Le navigateur : `pip install -r requirements.txt` installe la bibliothèque Playwright, pas le navigateur ; il faut
`playwright install chromium` (ou WEB_BROWSER_EXECUTABLE vers un Chrome / Edge déjà installé).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def dossier_atelier() -> Path:
    """Dossier du code de l'atelier (appium-robot-mcp)."""
    return Path(__file__).resolve().parents[2]


def projet() -> dict:
    """{ok, dossier, raison, solution} : le projet de tests est-il un vrai dossier de tests ?"""
    from atelier.domain import projet as p

    d = Path(p.PROJECT_DIR).resolve()
    solution = ("Choisir ou créer un projet de tests dans Paramètres › Projets, ou lancer l'atelier avec ROBOT_PROJECT_DIR vers le dossier "
                "de tests (Windows : set ROBOT_PROJECT_DIR=C:\\…\\mes-tests ; Linux / macOS : export ROBOT_PROJECT_DIR=…).")
    if not d.is_dir():
        return {"ok": False, "dossier": str(d), "raison": "le dossier du projet de tests n'existe pas", "solution": solution}
    if d == dossier_atelier():
        return {"ok": False, "dossier": str(d), "solution": solution,
                "raison": "aucun projet de tests choisi : l'atelier travaille dans son propre dossier (appium-robot-mcp) et y écrirait "
                          "la carte, les locators et les scénarios"}
    if d == Path.home().resolve() or d == Path(d.anchor):
        return {"ok": False, "dossier": str(d), "raison": "le projet de tests est le dossier personnel ou la racine du disque", "solution": solution}
    return {"ok": True, "dossier": str(d), "raison": "", "solution": ""}


def _caches_playwright() -> list[Path]:
    v = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if v and v != "0":
        return [Path(v).expanduser()]
    if sys.platform.startswith("win"):
        return [Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "ms-playwright"]
    if sys.platform == "darwin":
        return [Path.home() / "Library" / "Caches" / "ms-playwright"]
    return [Path.home() / ".cache" / "ms-playwright"]


def navigateur() -> dict:
    """{ok, detail, solution} : un navigateur est-il utilisable pour Discovery et les tests web ?"""
    exe = os.environ.get("WEB_BROWSER_EXECUTABLE", "").strip()
    if exe:
        ok = Path(exe).expanduser().is_file()
        return {"ok": ok, "detail": f"navigateur imposé : {exe}" if ok else f"WEB_BROWSER_EXECUTABLE introuvable : {exe}",
                "solution": "" if ok else "Corriger le chemin de WEB_BROWSER_EXECUTABLE (chrome.exe ou msedge.exe), ou le retirer."}
    try:
        import playwright  # noqa: F401
    except ImportError:
        return {"ok": False, "detail": "bibliothèque Playwright absente",
                "solution": "pip install -r requirements.txt, puis « playwright install chromium »."}
    trouves = [x for c in _caches_playwright() if c.is_dir() for x in c.iterdir() if x.name.startswith(("chromium", "chrome"))]
    if trouves:
        return {"ok": True, "detail": f"Chromium installé ({trouves[0].name})", "solution": ""}
    return {"ok": False, "detail": "Playwright est installé, mais pas son navigateur Chromium",
            "solution": "Lancer une fois « playwright install chromium » (ou « python installer.py »). Si le proxy le bloque : "
                        "WEB_BROWSER_EXECUTABLE vers Chrome ou Edge déjà installé."}


def message_demarrage(port: int) -> str:
    """Bloc affiché dans la console au lancement : adresse, projet de tests, et ce qui manque, avec la correction."""
    pr, nav = projet(), navigateur()
    lignes = [f"Atelier : http://127.0.0.1:{port}", f"Projet de tests : {pr['dossier']}"]
    for titre, x in (("PROJET DE TESTS", pr), ("NAVIGATEUR WEB", nav)):
        if not x["ok"]:
            lignes += ["", f"/!\\ {titre} : {x.get('raison') or x.get('detail')}", f"    → {x['solution']}"]
    return "\n".join(lignes)
