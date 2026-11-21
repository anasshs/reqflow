"""Installation de l'atelier sur le poste, en une commande (Windows, Linux, macOS) :

    python installer.py          (Windows sans « python » : py installer.py)

1. installe les dépendances (requirements.txt) dans le Python qui lance ce script (de préférence un .venv activé) ;
2. installe le navigateur Chromium de Playwright, que pip n'installe pas ;
3. rappelle comment choisir le projet de tests avant de lancer l'atelier.
Aucune donnée n'est envoyée ailleurs que vers les dépôts de paquets (PyPI) et de navigateurs de Playwright.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent


def etape(titre: str, cmd: list[str]) -> bool:
    print(f"\n=== {titre}\n$ {' '.join(cmd)}", flush=True)
    return subprocess.call(cmd, cwd=ICI) == 0


def main() -> int:
    if sys.version_info < (3, 10):
        print(f"Python {sys.version.split()[0]} : l'atelier demande Python 3.10 ou plus récent.")
        return 1
    if sys.prefix == sys.base_prefix:
        print("Conseil : créer et activer un environnement d'abord (python -m venv .venv puis .venv\\Scripts\\activate sous Windows, "
              "source .venv/bin/activate ailleurs). L'installation continue dans le Python courant.")
    if not etape("Dépendances Python", [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]):
        print("\nÉchec de pip : derrière un proxy d'entreprise, régler HTTPS_PROXY (et le certificat avec PIP_CERT), puis relancer.")
        return 1
    if not etape("Navigateur Chromium de Playwright", [sys.executable, "-m", "playwright", "install", "chromium"]):
        print("\nTéléchargement du navigateur impossible (proxy ?). Utiliser Chrome ou Edge déjà installé :\n"
              "  set WEB_BROWSER_EXECUTABLE=C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe   (Windows)\n"
              "  export WEB_BROWSER_EXECUTABLE=/chemin/vers/chrome                         (Linux / macOS)")
    print("\n=== Prêt. Avant de lancer l'atelier, choisir le dossier du projet de tests (où il écrit carte, locators, scénarios) :\n"
          "  set ROBOT_PROJECT_DIR=C:\\Users\\…\\Documents\\GitHub\\mes-tests      (Windows)\n"
          "  export ROBOT_PROJECT_DIR=~/mes-tests                               (Linux / macOS)\n"
          "puis : python web/app.py   →   http://127.0.0.1:8765\n"
          "(Le projet peut aussi être choisi ensuite dans Paramètres › Projets.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
