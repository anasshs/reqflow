#!/usr/bin/env sh
# Agent Mac de l'atelier : rend les iPhone branchés sur ce Mac utilisables par l'atelier d'un poste du même Wi-Fi.
# Python 3 de macOS suffit (bibliothèque standard) ; Xcode et Appium (avec le pilote xcuitest) doivent être installés.
cd "$(dirname "$0")" || exit 1
for p in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    exec "$p" agent_mac.py "$@"
  fi
done
echo "Python 3.10 ou plus récent est introuvable : brew install python@3.13"
exit 1
