"""Point d'entrée historique (rétrocompatibilité) : le code vit dans atelier.discovery.carte."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import atelier.discovery.carte as _module  # noqa: E402

sys.modules[__name__] = _module
