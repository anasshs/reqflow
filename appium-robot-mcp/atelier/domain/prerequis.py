"""Prérequis du poste vérifiés au lancement de l'atelier : projet de tests choisi, navigateur web installé.

Le projet de tests est le dossier où l'atelier écrit (carte, locators, scénarios, releases…). Sans réglage, c'est le
dossier courant : lancé depuis `appium-robot-mcp`, l'atelier écrirait dans son propre code. On le dit au lancement
(console), dans la pastille « État de l'atelier » et par un bandeau dans l'interface, avec la façon de corriger.

Le navigateur : `pip install -r requirements.txt` installe la bibliothèque Playwright, pas le navigateur ; il faut
`playwright install chromium` (ou WEB_BROWSER_EXECUTABLE vers un Chrome / Edge déjà installé).
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def systeme() -> str:
    """« windows », « macos » ou « linux » : les consignes affichées citent les commandes du poste."""
    return "windows" if sys.platform.startswith("win") else "macos" if sys.platform == "darwin" else "linux"


def commande_lancement() -> str:
    """Commande qui lance l'atelier sur ce poste (elle retient le port MCP)."""
    return "lancer-atelier.cmd" if systeme() == "windows" else "./lancer-atelier.sh"


def python_venv() -> str:
    """Python de l'environnement de l'atelier, tel qu'on le tape dans un terminal du poste."""
    return ".venv\\Scripts\\python" if systeme() == "windows" else ".venv/bin/python"


def installer_node() -> str:
    """Façon d'installer Node.js LTS sur ce poste."""
    return {"windows": "https://nodejs.org ou « winget install OpenJS.NodeJS.LTS »",
            "macos": "https://nodejs.org ou « brew install node »"}.get(systeme(), "https://nodejs.org ou le gestionnaire de paquets de la distribution")


def mobile() -> dict:
    """{ok, detail, solution, commandes} : outils pour piloter un téléphone. Android : Appium + pilote uiautomator2 ;
    iOS (macOS seulement) : Xcode, Appium + pilote xcuitest, équipe de signature pour un iPhone réel.
    commandes : ce que le lanceur peut installer lui-même (npm, appium driver)."""
    from atelier.discovery import session

    home = Path(os.environ.get("APPIUM_HOME") or Path.home() / ".appium").expanduser()
    pilote = lambda n: (home / "node_modules" / f"appium-{n}-driver").is_dir()  # noqa: E731
    android, ios = bool(session.chemin_adb()), systeme() == "macos"
    if not android and not ios:
        return {"ok": True, "detail": "aucun outil mobile sur ce poste (adb, Xcode) : web et API seulement", "solution": "", "commandes": []}
    manque, commandes, notes = [], [], []
    if not shutil.which("node"):
        manque.append(f"Node.js ({installer_node()})")
    elif not shutil.which("appium"):
        manque.append("Appium")
        commandes.append(["npm", "install", "-g", "appium"])
    if android and not pilote("uiautomator2"):
        manque.append("pilote Appium uiautomator2")
        commandes.append(["appium", "driver", "install", "uiautomator2"])
    if ios:
        if not (shutil.which("xcrun") and shutil.which("xcodebuild")):
            manque.append("Xcode (App Store, puis « sudo xcode-select -s /Applications/Xcode.app »)")
        if not pilote("xcuitest"):
            manque.append("pilote Appium xcuitest")
            commandes.append(["appium", "driver", "install", "xcuitest"])
        if not os.environ.get("IOS_TEAM_ID"):
            notes.append("iPhone réel : définir IOS_TEAM_ID (équipe Apple qui signe WebDriverAgent) et activer le Mode développeur sur l'iPhone")
    plats = " et ".join(p for p, v in (("Android", android), ("iOS", ios)) if v)
    if manque:
        return {"ok": False, "detail": f"{plats} : manque " + ", ".join(manque), "commandes": commandes,
                "solution": "Relancer " + commande_lancement() + " (il propose d'installer ce qui manque)"
                            + (" ; " + " ; ".join(" ".join(c) for c in commandes) if commandes else "") + ("" if not notes else " ; " + notes[0])}
    return {"ok": True, "detail": f"{plats} : Appium et pilotes prêts" + (f" ({notes[0]})" if notes else ""), "solution": "", "commandes": []}


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
                "solution": "" if ok else "Corriger le chemin de WEB_BROWSER_EXECUTABLE (exécutable de Chrome ou d'Edge), ou le retirer."}
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


def browser_robot() -> dict:
    """{ok, detail, solution} : la bibliothèque Robot « Browser » (tests web générés) est-elle initialisée ? Elle a besoin
    de Node.js et d'une installation à part (« rfbrowser init ») que pip ne fait pas."""
    try:
        import Browser
    except ImportError:
        return {"ok": False, "detail": "bibliothèque Robot Browser absente", "solution": "pip install -r requirements.txt"}
    wrapper = Path(Browser.__file__).parent / "wrapper"
    if (wrapper / "node_modules").is_dir():
        return {"ok": True, "detail": "bibliothèque Browser initialisée", "solution": ""}
    sans_node = not shutil.which("node")
    return {"ok": False, "detail": "bibliothèque Robot Browser installée mais pas initialisée (les tests web échouent au démarrage)"
                                   + (" ; Node.js absent" if sans_node else ""),
            "solution": (f"Installer Node.js LTS ({installer_node()}), puis " if sans_node else "")
                        + f"lancer une fois « {python_venv()} -m Browser.entry init » (ou relancer {commande_lancement()})."}


def suites_web(cible: str = "") -> bool:
    """Le projet de tests (ou la cible d'un run) utilise-t-il la bibliothèque Browser ?"""
    import re

    from atelier.domain import projet as pj

    motif = re.compile(r"^\s*Library\s+Browser\b", re.M)
    base = pj.PROJECT_DIR
    for f in list(base.rglob("*.robot")) + list(base.rglob("*.resource")):
        if any(p.startswith(".") or p in ("results", "node_modules") for p in f.relative_to(base).parts):
            continue
        try:
            if motif.search(f.read_text("utf-8", errors="ignore")):
                return True
        except OSError:
            continue
    return False


def message_demarrage(port: int) -> str:
    """Bloc affiché dans la console au lancement : adresse, projet de tests, et ce qui manque, avec la correction."""
    pr, nav, rfb = projet(), navigateur(), browser_robot()
    lignes = [f"Atelier : http://127.0.0.1:{port}", f"Projet de tests : {pr['dossier']}"]
    for titre, x in (("PROJET DE TESTS", pr), ("NAVIGATEUR WEB", nav), ("TESTS WEB (Robot Browser)", rfb)):
        if not x["ok"]:
            lignes += ["", f"/!\\ {titre} : {x.get('raison') or x.get('detail')}", f"    → {x['solution']}"]
    return "\n".join(lignes)
