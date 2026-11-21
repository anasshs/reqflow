"""Préparer le poste sans lancer l'atelier : équivalent de « python lanceur.py --verifier ».

Voir lanceur.py (assistant d'installation : Python, .venv, dépendances, navigateur, projet de tests). Pour préparer ET
lancer : lancer-atelier.cmd (Windows) ou ./lancer-atelier.sh (Linux / macOS).
"""
import sys

from lanceur import main

if __name__ == "__main__":
    sys.exit(main(["--verifier", *sys.argv[1:]]))
