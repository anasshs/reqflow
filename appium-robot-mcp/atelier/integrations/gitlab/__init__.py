"""Client GitLab (API REST v4, bibliothèque standard), pour une instance d'entreprise ou gitlab.com.

Connexion : jeton d'accès personnel (Personal Access Token, portées « api » et « write_repository »), jamais le mot
de passe LDAP. Le jeton est lu dans l'environnement (GITLAB_TOKEN, ou la variable désignée par le projet actif)
et envoyé dans l'en-tête PRIVATE-TOKEN : il n'apparaît ni dans une URL, ni sur disque, ni dans un log.
Certificat du proxy / de l'autorité interne : GITLAB_CA_BUNDLE (sinon XRAY_CA_BUNDLE).

Aucune fusion (merge) n'est jamais déclenchée par l'atelier : il crée des merge requests, des humains les fusionnent.
"""
from __future__ import annotations

import json
import os
import urllib.parse

from atelier.integrations.http import http, variable_secrete


def configure() -> bool:
    return bool(os.environ.get("GITLAB_URL") and os.environ.get("GITLAB_PROJET") and variable_secrete("GITLAB_TOKEN"))


class GitLabClient:
    def __init__(self):
        self.base = (os.environ.get("GITLAB_URL") or "").rstrip("/")
        self.projet = (os.environ.get("GITLAB_PROJET") or "").strip().strip("/")
        self._jeton = variable_secrete("GITLAB_TOKEN")
        if not (self.base and self.projet and self._jeton):
            raise RuntimeError("GitLab non configuré : URL, projet (Paramètres › Projets) et jeton (GITLAB_TOKEN ou variable du projet).")
        if not self.base.startswith("https://"):
            raise ValueError("GITLAB_URL : https:// attendu.")

    # ------------------------------------------------------------ bas niveau
    def _url(self, chemin: str, params: dict | None = None) -> str:
        q = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v not in (None, "")})
        return f"{self.base}/api/v4{chemin}" + (f"?{q}" if q else "")

    def _appel(self, methode: str, chemin: str, params: dict | None = None, corps: dict | None = None):
        cafile = os.environ.get("GITLAB_CA_BUNDLE") or os.environ.get("XRAY_CA_BUNDLE") or None
        r = http(methode, self._url(chemin, params), json.dumps(corps).encode() if corps is not None else None,
                 {"PRIVATE-TOKEN": self._jeton, "Content-Type": "application/json", "Accept": "application/json"},
                 cafile=cafile)
        return json.loads(r) if r else None

    @property
    def _p(self) -> str:
        return "/projects/" + urllib.parse.quote(self.projet, safe="")  # « groupe/sous-groupe/projet » ou identifiant

    # ------------------------------------------------------------ lecture
    def utilisateur(self) -> dict:
        u = self._appel("GET", "/user")
        return {"login": u.get("username"), "nom": u.get("name")}

    def projet_info(self) -> dict:
        p = self._appel("GET", self._p)
        return {"id": p.get("id"), "chemin": p.get("path_with_namespace"), "branche_defaut": p.get("default_branch"),
                "url": p.get("web_url"), "url_http": p.get("http_url_to_repo")}

    def commits(self, ref: str = "", depuis: str = "", chemin: str = "", limite: int = 50) -> list[dict]:
        l = self._appel("GET", f"{self._p}/repository/commits", {"ref_name": ref, "since": depuis, "path": chemin,
                                                                   "per_page": min(limite, 100)})
        return [{"id": c.get("short_id"), "titre": c.get("title"), "auteur": c.get("author_name"),
                 "date": c.get("created_at"), "url": c.get("web_url")} for c in l or []]

    def mr_ouvertes(self, source: str = "") -> list[dict]:
        l = self._appel("GET", f"{self._p}/merge_requests", {"state": "opened", "source_branch": source, "per_page": 50})
        return [_mr(m) for m in l or []]

    # ------------------------------------------------------------ écriture (sur action explicite uniquement)
    def creer_mr(self, source: str, cible: str, titre: str, description: str, libelles: list[str] | None = None) -> dict:
        m = self._appel("POST", f"{self._p}/merge_requests", corps={
            "source_branch": source, "target_branch": cible, "title": titre[:250], "description": description,
            "labels": ",".join(libelles or []), "remove_source_branch": False, "squash": False})
        return _mr(m)


def _mr(m: dict) -> dict:
    return {"iid": m.get("iid"), "titre": m.get("title"), "etat": m.get("state"), "source": m.get("source_branch"),
            "cible": m.get("target_branch"), "url": m.get("web_url"), "auteur": (m.get("author") or {}).get("username")}
