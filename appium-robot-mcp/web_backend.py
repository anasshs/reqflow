"""Point d'entrée historique (rétrocompatibilité) : le code vit dans atelier.integrations.playwright."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import atelier.integrations.playwright as _module  # noqa: E402

sys.modules[__name__] = _module
