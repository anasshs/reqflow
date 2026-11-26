"""
Appium Robot MCP — point d'entrée historique (rétrocompatibilité).

Les configurations Cursor / Claude Desktop existantes lancent `python server.py` : ce fichier
démarre la façade MCP (atelier/adapters/mcp/server.py). Importé, il désigne ce même module.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from atelier.adapters.mcp import server as _serveur  # noqa: E402

if __name__ == "__main__":
    _serveur.main()
else:
    sys.modules[__name__] = _serveur
