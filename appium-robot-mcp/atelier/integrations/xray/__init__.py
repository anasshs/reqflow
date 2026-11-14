"""
Client Xray Cloud (GraphQL).

Variables d'environnement :
  XRAY_CLIENT_ID / XRAY_CLIENT_SECRET   clé API Xray Cloud
  XRAY_BASE_URL                         (optionnel) base de l'API, défaut Xray Cloud v2
  XRAY_CA_BUNDLE                        certificat racine du proxy TLS de l'entreprise
Les appels GraphQL sont à vérifier sur la documentation officielle : voir docs/XRAY_API.md.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
from datetime import datetime
from typing import TYPE_CHECKING

from atelier.integrations.http import http

if TYPE_CHECKING:
    from atelier.integrations.jira import JiraClient

XRAY_BASE = os.environ.get("XRAY_BASE_URL", "https://xray.cloud.getxray.app/api/v2")
# Tag Robot reconnu comme clé de test Xray (ex. ATTIJARI-100, TAM-1909)
KEY_RE = re.compile(os.environ.get("XRAY_TEST_KEY_REGEX", r"^[A-Z][A-Z0-9_]+-\d+$"))


class ErreurGraphQL(RuntimeError):
    """Erreur renvoyée par l'API GraphQL elle-même (clé inconnue, JQL refusé…), par opposition à une
    erreur de transport (Xray injoignable), qui doit être retentée et jamais prise pour « introuvable »."""


def base_url() -> str:
    """Base de l'API lue au moment de l'appel (permet un faux serveur Xray en test)."""
    return os.environ.get("XRAY_BASE_URL", XRAY_BASE)


def now_iso() -> str:
    """Horodatage ISO 8601 avec fuseau, format attendu par Xray (startedOn / finishedOn)."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


# =========================================================================== Xray
class XrayClient:
    def __init__(self):
        from atelier.integrations.http import variable_secrete

        self.cid = variable_secrete("XRAY_CLIENT_ID")
        self.secret = variable_secrete("XRAY_CLIENT_SECRET")
        if not (self.cid and self.secret):
            raise RuntimeError("XRAY_CLIENT_ID / XRAY_CLIENT_SECRET non configurés.")
        self._token = None

    def token(self) -> str:
        if not self._token:
            body = json.dumps({"client_id": self.cid, "client_secret": self.secret}).encode()
            self._token = json.loads(http("POST", f"{base_url()}/authenticate", body,
                                          {"Content-Type": "application/json"}))
        return self._token

    def gql(self, query: str, variables: dict | None = None) -> dict:
        body = json.dumps({"query": query, "variables": variables or {}}).encode()
        r = json.loads(http("POST", f"{base_url()}/graphql", body,
                            {"Content-Type": "application/json",
                             "Authorization": f"Bearer {self.token()}"}))
        if r.get("errors"):
            raise ErreurGraphQL("Xray GraphQL : " + "; ".join(e.get("message", "") for e in r["errors"]))
        return r["data"]

    # ------------------------------------------------------------ lecture
    def _first(self, entity: str, key: str):
        q = (f'query($jql: String) {{ {entity}(jql: $jql, limit: 1) '
             f'{{ results {{ issueId jira(fields: ["key", "summary"]) }} }} }}')
        try:
            res = self.gql(q, {"jql": f'key = "{key}"'})[entity]["results"]
        except ErreurGraphQL:
            return None  # clé inexistante ou d'un autre type
        return res[0] if res else None

    def resolve(self, ticket: str) -> dict:
        """Détermine le type du ticket : plan, execution, test, autre (US, epic…) ou projet."""
        t = ticket.strip().upper()
        if "-" not in t:
            return {"type": "projet", "key": t, "projet": t}
        projet = t.rsplit("-", 1)[0]
        for typ, entity in (("plan", "getTestPlans"), ("execution", "getTestExecutions"),
                            ("test", "getTests")):
            r = self._first(entity, t)
            if r:
                return {"type": typ, "key": t, "issueId": r["issueId"], "projet": projet,
                        "resume": (r.get("jira") or {}).get("summary", "")}
        return {"type": "autre", "key": t, "projet": projet}

    def search_tests(self, jql: str, limit: int = 50) -> list[dict]:
        """Tests correspondant à un JQL (ex. candidats à l'automatisation)."""
        q = ('query($jql: String, $l: Int!) { getTests(jql: $jql, limit: $l) { results { issueId '
             'testType { name } jira(fields: ["key", "summary", "labels", "status"]) } } }')
        res = self.gql(q, {"jql": jql, "l": min(limit, 100)})["getTests"]["results"]
        return [{"cle": r["jira"]["key"], "resume": r["jira"].get("summary"),
                 "type": (r.get("testType") or {}).get("name"), "libelles": r["jira"].get("labels") or [],
                 "statut": ((r["jira"].get("status") or {}).get("name"))} for r in res]

    def test_ids(self, keys: list[str]) -> dict:
        """{clé de test: issueId} pour les tests existants dans Xray."""
        out: dict = {}
        keys = list(dict.fromkeys(keys))
        q = 'query($jql: String) { getTests(jql: $jql, limit: 100) { results { issueId jira(fields: ["key"]) } } }'
        for i in range(0, len(keys), 100):
            chunk = keys[i:i + 100]
            try:
                res = self.gql(q, {"jql": f"key in ({', '.join(chunk)})"})["getTests"]["results"]
            except ErreurGraphQL:  # une clé inconnue fait échouer le JQL : on passe clé par clé
                res = [r for k in chunk if (r := self._first("getTests", k))]
            for r in res:
                out[r["jira"]["key"]] = r["issueId"]
        return out

    def test_runs(self, exec_id: str, test_ids: list[str]) -> dict:
        """{issueId du test: id du test run} dans l'exécution."""
        out: dict = {}
        q = ('query($t: [String], $e: [String]) { getTestRuns(testIssueIds: $t, testExecIssueIds: $e, '
             'limit: 100) { results { id test { issueId } } } }')
        for i in range(0, len(test_ids), 100):
            for r in self.gql(q, {"t": test_ids[i:i + 100], "e": [exec_id]})["getTestRuns"]["results"]:
                out[r["test"]["issueId"]] = r["id"]
        return out

    # ------------------------------------------------------------ création / rattachement
    def create_plan(self, projet: str, summary: str, test_ids: list[str]):
        q = ('mutation($t: [String], $j: JSON!) { createTestPlan(testIssueIds: $t, jira: $j) '
             '{ testPlan { issueId jira(fields: ["key"]) } warnings } }')
        r = self.gql(q, {"t": test_ids, "j": {"fields": {"summary": summary,
                                                        "project": {"key": projet}}}})["createTestPlan"]
        return r["testPlan"]["issueId"], r["testPlan"]["jira"]["key"]

    def create_execution(self, projet: str, summary: str, test_ids: list[str], envs: list[str]):
        q = ('mutation($t: [String], $env: [String], $j: JSON!) { createTestExecution(testIssueIds: $t, '
             'testEnvironments: $env, jira: $j) { testExecution { issueId jira(fields: ["key"]) } warnings } }')
        r = self.gql(q, {"t": test_ids, "env": envs or [],
                         "j": {"fields": {"summary": summary,
                                          "project": {"key": projet}}}})["createTestExecution"]
        return r["testExecution"]["issueId"], r["testExecution"]["jira"]["key"]

    def add_execs_to_plan(self, plan_id: str, exec_ids: list[str]):
        q = ('mutation($p: String!, $e: [String]) { addTestExecutionsToTestPlan(issueId: $p, '
             'testExecIssueIds: $e) { addedTestExecutions warning } }')
        return self.gql(q, {"p": plan_id, "e": exec_ids})

    def add_tests_to_plan(self, plan_id: str, test_ids: list[str]):
        q = 'mutation($p: String!, $t: [String]) { addTestsToTestPlan(issueId: $p, testIssueIds: $t) { addedTests warning } }'
        return self.gql(q, {"p": plan_id, "t": test_ids})

    def add_tests_to_exec(self, exec_id: str, test_ids: list[str]):
        q = 'mutation($e: String!, $t: [String]) { addTestsToTestExecution(issueId: $e, testIssueIds: $t) { addedTests warning } }'
        return self.gql(q, {"e": exec_id, "t": test_ids})

    # ------------------------------------------------------------ test runs
    def set_status(self, run_id: str, status: str):
        q = 'mutation($id: String!, $s: String!) { updateTestRunStatus(id: $id, status: $s) }'
        return self.gql(q, {"id": run_id, "s": status})

    def update_run(self, run_id: str, started: str | None = None, finished: str | None = None,
                   comment: str | None = None):
        """Met à jour heures de début/fin et commentaire (seuls les champs fournis sont envoyés)."""
        fields = {"startedOn": started, "finishedOn": finished, "comment": comment}
        fields = {k: v for k, v in fields.items() if v is not None}
        if not fields:
            return None
        decl = "".join(f", ${k}: String" for k in fields)
        args = "".join(f", {k}: ${k}" for k in fields)
        q = f"mutation($id: String!{decl}) {{ updateTestRun(id: $id{args}) {{ warnings }} }}"
        return self.gql(q, {"id": run_id, **fields})

    def add_evidence(self, run_id: str, files: list[str]):
        ev = []
        for f in files:
            with open(f, "rb") as fh:
                ev.append({"filename": os.path.basename(f), "mimeType": mimetypes.guess_type(f)[0] or "application/octet-stream",
                           "data": base64.b64encode(fh.read()).decode()})
        q = ('mutation($id: String!, $ev: [AttachmentDataInput]!) { addEvidenceToTestRun(id: $id, '
             'evidence: $ev) { addedEvidence warnings } }')
        return self.gql(q, {"id": run_id, "ev": ev}) if ev else None

    # ------------------------------------------------------------ orchestration
    def prepare(self, ticket: str, test_keys: list[str], exec_summary: str,
                plan_summary: str = "", envs: list[str] | None = None,
                jira: "JiraClient | None" = None) -> dict:
        """[Historique] Préparation en un bloc, conservée pour les scripts existants. Le listener passe
        désormais par atelier/execution/journal_xray.py (étapes mémorisées, reprise sans doublon).
        Prépare la cible Xray à partir d'un seul ticket :
        - Test Plan      -> nouvelle exécution ajoutée au plan (+ tests ajoutés au plan) ;
        - Test Execution -> mise à jour de cette exécution (tests manquants ajoutés) ;
        - autre / projet -> création d'un plan + d'une exécution rattachée."""
        info = self.resolve(ticket)
        if info["type"] == "test":
            raise ValueError(f"{info['key']} est un Test : donner un plan, une exécution, un ticket ou un projet.")
        ids = self.test_ids(test_keys)
        tids = list(ids.values())
        plan_key = None
        warnings: list[str] = []

        if info["type"] == "execution":
            exec_id, exec_key = info["issueId"], info["key"]
            if tids:
                self.add_tests_to_exec(exec_id, tids)
            mode = "mise à jour de l'exécution"
        else:
            if info["type"] == "plan":
                plan_id, plan_key = info["issueId"], info["key"]
                if tids:
                    self.add_tests_to_plan(plan_id, tids)
                mode = "nouvelle exécution ajoutée au plan"
            else:
                summary = plan_summary or (f"Plan de test – {info['key']}" if info["type"] == "autre"
                                           else f"Plan de test auto – {datetime.now():%d/%m/%Y}")
                plan_id, plan_key = self.create_plan(info["projet"], summary, tids)
                mode = "plan créé + exécution"
                if info["type"] == "autre" and jira and jira.enabled:
                    try:
                        jira.link(plan_key, info["key"])
                    except Exception as e:
                        warnings.append(f"Lien {plan_key} ↔ {info['key']} non créé : {e}")
            exec_id, exec_key = self.create_execution(info["projet"], exec_summary, tids, envs or [])
            self.add_execs_to_plan(plan_id, [exec_id])

        by_issue = self.test_runs(exec_id, tids)
        runs = {k: by_issue[i] for k, i in ids.items() if i in by_issue}
        return {"mode": mode, "ticket": info, "plan_key": plan_key, "exec_key": exec_key,
                "exec_id": exec_id, "runs": runs,
                "tests_inconnus_xray": [k for k in test_keys if k not in ids],
                "avertissements": warnings}
