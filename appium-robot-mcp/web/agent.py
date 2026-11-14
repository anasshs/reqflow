"""Point d'entrée historique (rétrocompatibilité) : le code vit dans atelier/adapters/web/agent.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import atelier.adapters.web.agent as _module  # noqa: E402

sys.modules[__name__] = _module
