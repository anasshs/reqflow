"""Point d'entrée historique du listener Robot (rétrocompatibilité CI) :
    robot --listener xray_live_listener.py:<argument> tests/
Le code vit dans atelier/execution/listeners/xray_live_listener.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from atelier.execution.listeners.xray_live_listener import xray_live_listener  # noqa: E402,F401
