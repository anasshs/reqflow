"""
Client Jira Cloud (transitions, sous-tâches, statuts, création de tickets, liens).

Variables d'environnement : JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN.
"""
from __future__ import annotations

import base64
import json
import os

from atelier.integrations.http import http


# =========================================================================== Jira
class JiraClient:
    def __init__(self):
        self.base = (os.environ.get("JIRA_BASE_URL") or "").rstrip("/")
        from atelier.integrations.http import variable_secrete

        email, token = variable_secrete("JIRA_EMAIL"), variable_secrete("JIRA_API_TOKEN")
        self.enabled = bool(self.base and email and token)
        self._auth = ("Basic " + base64.b64encode(f"{email}:{token}".encode()).decode()
                      if self.enabled else "")

    def _h(self) -> dict:
        return {"Authorization": self._auth, "Content-Type": "application/json",
                "Accept": "application/json"}

    def transition(self, key: str, name: str):
        """Applique une transition par son nom OU par le nom du statut cible (insensible à la casse)."""
        if not name:
            return None
        if not self.enabled:
            raise RuntimeError("JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN non configurés.")
        url = f"{self.base}/rest/api/3/issue/{key}/transitions"
        transitions = json.loads(http("GET", url, headers=self._h())).get("transitions", [])
        wanted = name.strip().lower()
        for t in transitions:
            target = (t.get("to") or {}).get("name", "")
            if wanted in (t["name"].lower(), target.lower()):
                http("POST", url, json.dumps({"transition": {"id": t["id"]}}).encode(), self._h())
                return target or t["name"]
        possibles = ", ".join(t["name"] for t in transitions) or "aucune"
        raise RuntimeError(f"Transition « {name} » indisponible sur {key} (possibles : {possibles})")

    def get(self, path: str):
        if not self.enabled:
            raise RuntimeError("JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN non configurés.")
        return json.loads(http("GET", f"{self.base}{path}", headers=self._h()) or "null")

    def myself(self) -> dict:
        return self.get("/rest/api/3/myself")

    def sous_taches(self, key: str) -> list[dict]:
        data = self.get(f"/rest/api/3/issue/{key}?fields=subtasks,summary")
        return [{"cle": t["key"], "resume": t["fields"].get("summary"),
                 "statut": (t["fields"].get("status") or {}).get("name")}
                for t in data["fields"].get("subtasks", [])]

    def transitions(self, key: str) -> list[dict]:
        data = self.get(f"/rest/api/3/issue/{key}/transitions")
        return [{"transition": t["name"], "statut_cible": (t.get("to") or {}).get("name")}
                for t in data.get("transitions", [])]

    def projets(self, recherche: str = "", limite: int = 30) -> list[dict]:
        """Projets visibles par le compte, filtrés par nom ou clé (GET /rest/api/3/project/search?query=)."""
        import urllib.parse

        r = self.get(f"/rest/api/3/project/search?query={urllib.parse.quote(recherche)}&maxResults={limite}&orderBy=name") or {}
        return [{"cle": p.get("key"), "nom": p.get("name"), "type": p.get("projectTypeKey", ""),
                 "geree_par_equipe": p.get("style") == "next-gen"} for p in r.get("values") or []]

    def types_issue_projet(self, projet: str) -> list[str]:
        """Types de ticket du projet (hors sous-tâches), via GET /rest/api/3/project/{clé}."""
        p = self.get(f"/rest/api/3/project/{projet}") or {}
        return [t["name"] for t in p.get("issueTypes") or [] if not t.get("subtask")]

    def statuts_projet(self, project: str, issue_type: str = "") -> list[str]:
        """Statuts du workflow d'un type de ticket (ex. Test Execution) dans un projet."""
        issue_type = issue_type or os.environ.get("XRAY_EXEC_ISSUE_TYPE", "Test Execution")
        data = self.get(f"/rest/api/3/project/{project}/statuses")
        for it in data:
            if it.get("name", "").lower() == issue_type.lower():
                return [st["name"] for st in it.get("statuses", [])]
        return sorted({st["name"] for it in data for st in it.get("statuses", [])})

    def creer_ticket(self, projet: str, resume: str, description: str, type_ticket: str = "") -> str:
        """Crée un ticket (description en texte simple, une ligne = un paragraphe)."""
        if not self.enabled:
            raise RuntimeError("JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN non configurés.")
        type_ticket = type_ticket or os.environ.get("JIRA_TYPE_TICKET_TAGS", "Task")
        doc = {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": ligne}]}
            for ligne in description.splitlines() if ligne.strip()]}
        body = {"fields": {"project": {"key": projet}, "summary": resume, "description": doc,
                           "issuetype": {"name": type_ticket}}}
        r = json.loads(http("POST", f"{self.base}/rest/api/3/issue", json.dumps(body).encode(), self._h()))
        return r["key"]

    # ------------------------------------------------------------ Jira Software (agile) : tableaux et sprints
    def tableaux(self, projet: str) -> list[dict]:
        """Tableaux du projet (GET /rest/agile/1.0/board?projectKeyOrId=) ; seuls les tableaux Scrum ont des sprints."""
        r = self.get(f"/rest/agile/1.0/board?projectKeyOrId={projet}&maxResults=50")
        return [{"id": b.get("id"), "nom": b.get("name"), "type": b.get("type")} for b in (r or {}).get("values") or []]

    def sprints(self, tableau: int, etats: str = "active,future,closed") -> list[dict]:
        """Sprints d'un tableau (GET /rest/agile/1.0/board/{id}/sprint?state=), toutes pages."""
        out, debut = [], 0
        while True:
            r = self.get(f"/rest/agile/1.0/board/{tableau}/sprint?state={etats}&startAt={debut}&maxResults=50") or {}
            for s in r.get("values") or []:
                out.append({"id": s.get("id"), "nom": s.get("name"), "etat": s.get("state"), "debut": s.get("startDate", ""),
                            "fin": s.get("endDate", ""), "objectif": s.get("goal", ""), "tableau": tableau})
            debut += len(r.get("values") or [])
            if r.get("isLast", True) or not r.get("values"):
                return out

    def commenter(self, key: str, texte: str) -> dict:
        """Commentaire (texte simple, une ligne = un paragraphe ; « - » en tête = puce). POST /rest/api/3/issue/{key}/comment."""
        if not self.enabled:
            raise RuntimeError("JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN non configurés.")
        lignes = [l for l in texte.splitlines() if l.strip()]
        contenu, puces = [], []
        for l in lignes + [""]:
            if l.lstrip().startswith("- "):
                puces.append({"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": l.lstrip()[2:]}]}]})
                continue
            if puces:
                contenu.append({"type": "bulletList", "content": puces})
                puces = []
            if l:
                contenu.append({"type": "paragraph", "content": [{"type": "text", "text": l}]})
        corps = {"body": {"type": "doc", "version": 1, "content": contenu}}
        r = json.loads(http("POST", f"{self.base}/rest/api/3/issue/{key}/comment", json.dumps(corps).encode(), self._h()))
        return {"id": r.get("id"), "auteur_id": (r.get("author") or {}).get("accountId"), "date": r.get("created")}

    def commentaires(self, key: str) -> list[dict]:
        """Commentaires d'un ticket, du plus ancien au plus récent (texte extrait de l'ADF)."""
        out, debut = [], 0
        while True:
            r = self.get(f"/rest/api/3/issue/{key}/comment?startAt={debut}&maxResults=100&orderBy=created")
            for c in r.get("comments") or []:
                out.append({"id": c.get("id"), "auteur": (c.get("author") or {}).get("displayName", ""),
                            "auteur_id": (c.get("author") or {}).get("accountId", ""), "date": c.get("created", ""),
                            "texte": adf_vers_texte(c.get("body"))})
            debut += len(r.get("comments") or [])
            if not r.get("comments") or debut >= (r.get("total") or 0):
                return out

    def link(self, issue_a: str, issue_b: str, type_name: str = "Relates"):
        body = {"type": {"name": type_name}, "inwardIssue": {"key": issue_a},
                "outwardIssue": {"key": issue_b}}
        http("POST", f"{self.base}/rest/api/3/issueLink", json.dumps(body).encode(), self._h())

    def joindre(self, key: str, chemin: str) -> None:
        """Pièce jointe (multipart, en-tête X-Atlassian-Token: no-check exigé par Jira)."""
        import mimetypes
        import secrets as _s
        from pathlib import Path

        if not self.enabled:
            raise RuntimeError("JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN non configurés.")
        f = Path(chemin)
        borne = "----atelier" + _s.token_hex(8)
        corps = (f"--{borne}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{f.name}\"\r\n"
                 f"Content-Type: {mimetypes.guess_type(f.name)[0] or 'application/octet-stream'}\r\n\r\n").encode() \
            + f.read_bytes() + f"\r\n--{borne}--\r\n".encode()
        http("POST", f"{self.base}/rest/api/3/issue/{key}/attachments", corps,
             {"Authorization": self._auth, "X-Atlassian-Token": "no-check", "Accept": "application/json",
              "Content-Type": f"multipart/form-data; boundary={borne}"})

    def rechercher(self, jql: str, champs: list[str], limite: int = 1000) -> list[dict]:
        """Recherche JQL paginée (POST /rest/api/3/search/jql, pagination par nextPageToken).
        Point d'API à vérifier sur la documentation Jira Cloud : voir docs/XRAY_API.md."""
        if not self.enabled:
            raise RuntimeError("JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN non configurés.")
        out: list[dict] = []
        jeton = None
        self.tronque = False
        while len(out) < limite:
            corps = {"jql": jql, "fields": champs, "maxResults": min(100, limite - len(out))}
            if jeton:
                corps["nextPageToken"] = jeton
            r = json.loads(http("POST", f"{self.base}/rest/api/3/search/jql", json.dumps(corps).encode(), self._h()))
            out += r.get("issues", [])
            jeton = r.get("nextPageToken")
            if not jeton:
                break
        self.tronque = bool(jeton)  # limite atteinte alors que Jira avait encore des pages : signalé, jamais silencieux
        return out[:limite]


def adf_vers_texte(adf) -> str:
    """Atlassian Document Format (descriptions Jira Cloud v3) -> texte ; listes à puces en lignes « - … »."""
    if adf is None:
        return ""
    if isinstance(adf, str):
        return adf
    lignes: list[str] = []

    def texte(n) -> str:
        return "".join(c.get("text", "") if c.get("type") == "text" else texte(c) for c in n.get("content") or [])

    def parcourir(n, puce=False):
        t = n.get("type")
        if t in ("bulletList", "orderedList"):
            for item in n.get("content") or []:
                parcourir(item, True)
        elif t == "listItem":
            lignes.append("- " + " ".join(texte(c) for c in n.get("content") or []).strip())
        elif t in ("paragraph", "heading"):
            lignes.append(texte(n))
        else:
            for c in n.get("content") or []:
                parcourir(c, puce)
    parcourir(adf)
    return "\n".join(l for l in lignes if l.strip())
