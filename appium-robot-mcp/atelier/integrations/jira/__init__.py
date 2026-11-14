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
        email, token = os.environ.get("JIRA_EMAIL"), os.environ.get("JIRA_API_TOKEN")
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

    def link(self, issue_a: str, issue_b: str, type_name: str = "Relates"):
        body = {"type": {"name": type_name}, "inwardIssue": {"key": issue_a},
                "outwardIssue": {"key": issue_b}}
        http("POST", f"{self.base}/rest/api/3/issueLink", json.dumps(body).encode(), self._h())
