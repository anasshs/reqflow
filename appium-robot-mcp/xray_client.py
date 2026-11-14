"""
Client Xray Cloud (GraphQL) + Jira Cloud (transitions, liens).
Partagé par le serveur MCP et le listener xray_live_listener.py.

Variables d'environnement :
  XRAY_CLIENT_ID / XRAY_CLIENT_SECRET   clé API Xray Cloud
  JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN   (optionnel) transitions et liens Jira
  XRAY_CA_BUNDLE                        certificat racine du proxy TLS de l'entreprise
"""
from __future__ import annotations

import base64
import json
import os
import re
import ssl
import urllib.error
import urllib.request
from datetime import datetime

XRAY_BASE = os.environ.get("XRAY_BASE_URL", "https://xray.cloud.getxray.app/api/v2")
# Tag Robot reconnu comme clé de test Xray (ex. ATTIJARI-100, TAM-1909)
KEY_RE = re.compile(os.environ.get("XRAY_TEST_KEY_REGEX", r"^[A-Z][A-Z0-9_]+-\d+$"))


def now_iso() -> str:
    """Horodatage ISO 8601 avec fuseau, format attendu par Xray (startedOn / finishedOn)."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _ctx():
    ca = os.environ.get("XRAY_CA_BUNDLE")
    return ssl.create_default_context(cafile=ca) if ca else ssl.create_default_context()


def http(method: str, url: str, data: bytes | None = None, headers: dict | None = None,
         timeout: int = 60) -> str:
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, context=_ctx(), timeout=timeout) as r:
            return r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:600]
        raise RuntimeError(f"HTTP {e.code} sur {url.split('?')[0]} : {detail}") from None


# =========================================================================== Xray
class XrayClient:
    def __init__(self):
        self.cid = os.environ.get("XRAY_CLIENT_ID")
        self.secret = os.environ.get("XRAY_CLIENT_SECRET")
        if not (self.cid and self.secret):
            raise RuntimeError("XRAY_CLIENT_ID / XRAY_CLIENT_SECRET non configurés.")
        self._token = None

    def token(self) -> str:
        if not self._token:
            body = json.dumps({"client_id": self.cid, "client_secret": self.secret}).encode()
            self._token = json.loads(http("POST", f"{XRAY_BASE}/authenticate", body,
                                          {"Content-Type": "application/json"}))
        return self._token

    def gql(self, query: str, variables: dict | None = None) -> dict:
        body = json.dumps({"query": query, "variables": variables or {}}).encode()
        r = json.loads(http("POST", f"{XRAY_BASE}/graphql", body,
                            {"Content-Type": "application/json",
                             "Authorization": f"Bearer {self.token()}"}))
        if r.get("errors"):
            raise RuntimeError("Xray GraphQL : " + "; ".join(e.get("message", "") for e in r["errors"]))
        return r["data"]

    # ------------------------------------------------------------ lecture
    def _first(self, entity: str, key: str):
        q = (f'query($jql: String) {{ {entity}(jql: $jql, limit: 1) '
             f'{{ results {{ issueId jira(fields: ["key", "summary"]) }} }} }}')
        try:
            res = self.gql(q, {"jql": f'key = "{key}"'})[entity]["results"]
        except RuntimeError:
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
            except RuntimeError:  # une clé inconnue fait échouer le JQL : on passe clé par clé
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
                ev.append({"filename": os.path.basename(f), "mimeType": "image/png",
                           "data": base64.b64encode(fh.read()).decode()})
        q = ('mutation($id: String!, $ev: [AttachmentDataInput]!) { addEvidenceToTestRun(id: $id, '
             'evidence: $ev) { addedEvidence warnings } }')
        return self.gql(q, {"id": run_id, "ev": ev}) if ev else None

    # ------------------------------------------------------------ orchestration
    def prepare(self, ticket: str, test_keys: list[str], exec_summary: str,
                plan_summary: str = "", envs: list[str] | None = None,
                jira: "JiraClient | None" = None) -> dict:
        """Prépare la cible Xray à partir d'un seul ticket :
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
