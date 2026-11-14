"""Point d'entrée historique (rétrocompatibilité) : les clients vivent dans atelier/integrations/."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from atelier.integrations.http import http  # noqa: E402,F401
from atelier.integrations.jira import JiraClient  # noqa: E402,F401
from atelier.integrations.xray import KEY_RE, XRAY_BASE, XrayClient, base_url, now_iso  # noqa: E402,F401
