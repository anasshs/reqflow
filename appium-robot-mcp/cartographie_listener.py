"""Point d'entrée historique du listener Robot (rétrocompatibilité CI) :
    robot --listener cartographie_listener.py:<argument> tests/
Le code vit dans atelier/execution/listeners/cartographie_listener.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from atelier.execution.listeners.cartographie_listener import cartographie_listener  # noqa: E402,F401
