"""HTTP bas niveau (bibliothèque standard), avec le certificat racine du proxy TLS de l'entreprise."""
from __future__ import annotations

import os
import ssl
import urllib.error
import urllib.request


def _ctx(cafile: str | None = None):
    ca = cafile or os.environ.get("XRAY_CA_BUNDLE")
    return ssl.create_default_context(cafile=ca) if ca else ssl.create_default_context()


def http(method: str, url: str, data: bytes | None = None, headers: dict | None = None,
         timeout: int = 60, cafile: str | None = None) -> str:
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, context=_ctx(cafile), timeout=timeout) as r:
            return r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:600]
        raise RuntimeError(f"HTTP {e.code} sur {url.split('?')[0]} : {detail}") from None


def variable_secrete(nom: str) -> str:
    """Valeur d'une variable d'environnement de connexion, sans espaces ni guillemets copiés avec elle
    (cause fréquente d'un 401 : Read-Host ou un .env qui conserve les guillemets)."""
    import os

    return (os.environ.get(nom) or "").strip().strip('"').strip("'").strip()
