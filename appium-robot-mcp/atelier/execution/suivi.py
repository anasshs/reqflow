"""Suivi des exécutions dans Xray et Jira : cible d'un run, transitions, sous-tâches,
qualification des échecs, import de secours d'un output.xml."""
from __future__ import annotations

import json
import urllib.parse

from atelier.domain import projet
from atelier.integrations.http import http
from atelier.integrations.jira import JiraClient
from atelier.integrations.xray import XrayClient, base_url

EFFETS_TICKET = {"plan": "nouvelle exécution créée et ajoutée à ce plan",
                 "execution": "cette exécution sera mise à jour",
                 "test": "c'est un Test : non utilisable comme cible",
                 "autre": "un plan (lié au ticket) + une exécution seront créés",
                 "projet": "un plan + une exécution seront créés dans ce projet"}


def xray_inspect_ticket(ticket: str) -> dict:
    info = XrayClient().resolve(ticket)
    return {**info, "effet_du_run": EFFETS_TICKET[info["type"]]}


def jira_transition(issue_key: str, transition: str) -> str:
    cible = JiraClient().transition(issue_key, transition)
    return f"{issue_key} -> {cible}"


def jira_subtasks(issue_key: str) -> list[dict]:
    return JiraClient().sous_taches(issue_key)


def qualify_failure(run_id: str, qualification: str, commentaire: str = "", message_echec: str = "") -> str:
    texte = f"[Qualification : {qualification}]" + (f" {commentaire}" if commentaire else "")
    if message_echec:
        texte += f"\n---\n{message_echec[:2000]}"
    XrayClient().update_run(run_id, comment=texte)
    return "Qualification enregistrée dans Xray."


def import_results_to_xray(output_xml: str = "results/mcp/output.xml", test_execution_key: str = "",
                           project_key: str = "", test_plan_key: str = "") -> dict:
    if not (test_execution_key or project_key):
        raise ValueError("Renseigner test_execution_key ou project_key.")
    params = {k: v for k, v in {"testExecKey": test_execution_key, "projectKey": project_key,
                                "testPlanKey": test_plan_key}.items() if v}
    url = f"{base_url()}/import/execution/robot?{urllib.parse.urlencode(params)}"
    answer = json.loads(http("POST", url, projet.safe_path(output_xml).read_bytes(),
                             {"Content-Type": "application/xml",
                              "Authorization": f"Bearer {XrayClient().token()}"}))
    return {"statut": "importé", "execution": answer.get("key"), "reponse_xray": answer}
