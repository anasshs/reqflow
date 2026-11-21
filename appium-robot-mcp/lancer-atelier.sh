#!/usr/bin/env sh
# Atelier : assistant d'installation et de lancement (Linux / macOS). « ./lancer-atelier.sh »
# Trouve Python 3.10+, puis lance lanceur.py qui prépare le poste (.venv, dépendances, navigateur, projet de tests)
# et démarre l'atelier.
cd "$(dirname "$0")" || exit 1
for p in python3.13 python3.12 python3.11 python3.10 python3 python; do
  if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    exec "$p" lanceur.py "$@"
  fi
done
echo "Python 3.10 ou plus récent est introuvable."
echo "  macOS : brew install python@3.13   (ou https://www.python.org/downloads/)"
echo "  Linux : sudo apt install python3 python3-venv   (ou l'équivalent de la distribution)"
exit 1
