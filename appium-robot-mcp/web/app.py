"""
Interface web « Atelier d'automatisation » — point d'entrée historique (rétrocompatibilité).

    python web/app.py            -> http://127.0.0.1:8765

Le code vit dans atelier/adapters/web/app.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from atelier.adapters.web import app as _module  # noqa: E402

app = _module.app
main = _module.main

if __name__ == "__main__":
    main()
