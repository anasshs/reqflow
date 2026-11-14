"""Faux serveur Xray Cloud (authenticate + GraphQL) pour les tests : aucun appel au vrai service.

Projet fictif DEMO avec deux tests (DEMO-1, DEMO-2). On peut lui demander d'échouer N fois
(HTTP 503) ou d'être totalement indisponible, et il trace chaque opération reçue.
"""
from __future__ import annotations

import http.server
import itertools
import json
import re
import threading

OPERATIONS = ["addTestExecutionsToTestPlan", "addTestsToTestPlan", "addTestsToTestExecution",
              "addEvidenceToTestRun", "updateTestRunStatus", "updateTestRun", "createTestPlan",
              "createTestExecution", "getTestRuns", "getTestPlans", "getTestExecutions", "getTests"]


class FauxXray:
    def __init__(self, tests: dict | None = None):
        self.tests = tests or {"DEMO-1": "1001", "DEMO-2": "1002"}
        self.echecs_restants = 0
        self.indisponible = False
        self.appels: list[str] = []
        self.plans: dict = {}
        self.executions: dict = {}        # issueId -> {"key", "tests": [...]}
        self.runs: dict = {}              # (exec_id, test_id) -> run_id
        self.statuts: dict = {}           # run_id -> [statuts successifs]
        self.maj_runs: dict = {}          # run_id -> dernier updateTestRun
        self.preuves: dict = {}
        self._ids = itertools.count(5000)
        self._verrou = threading.Lock()
        self.srv = None
        self.schema = schema_conforme()

    # ------------------------------------------------------------------ serveur
    def demarrer(self) -> str:
        faux = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                corps = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                code, rep = faux.traiter(self.path, corps)
                data = json.dumps(rep).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self.srv.server_address[1]}/api/v2"

    def arreter(self):
        if self.srv:
            self.srv.shutdown()

    # ------------------------------------------------------------------ logique
    def traiter(self, chemin: str, corps: bytes):
        with self._verrou:
            if self.indisponible:
                return 503, {"error": "indisponible"}
            if self.echecs_restants > 0:
                self.echecs_restants -= 1
                return 503, {"error": "indisponible"}
            if chemin.endswith("/authenticate"):
                return 200, "jeton-de-test"
            req = json.loads(corps)
            q, v = req["query"], req.get("variables") or {}
            if "__schema" in q:
                return 200, {"data": self.schema}
            if "__type" in q:  # types de sortie lus par l'import des définitions (Test Design)
                from atelier.integrations.xray.verification import TYPES_SORTIE

                import re as _re
                nom = v.get("n") or (_re.search(r'__type\(name: "(\w+)"\)', q) or [None, ""])[1]
                from atelier.integrations.xray.verification import TYPES_ENTREE_EXTRA

                if nom in TYPES_ENTREE_EXTRA:
                    return 200, {"data": {"__type": {"inputFields": [{"name": c} for c in TYPES_ENTREE_EXTRA[nom]]}}}
                champs = TYPES_SORTIE.get(nom)
                return 200, {"data": {"__type": {"fields": [{"name": c, "args": []} for c in champs]} if champs else None}}
            op = next(o for o in OPERATIONS if o in q)
            self.appels.append(op)
            try:
                return 200, {"data": {op: self._repondre(op, v)}}
            except RefusXray as e:  # erreur métier GraphQL, comme le vrai Xray
                return 200, {"data": {op: None}, "errors": [{"message": str(e)}]}

    def _cles(self, v) -> list[str]:
        return re.findall(r"[A-Z][A-Z0-9_]+-\d+", v.get("jql", ""))

    def _repondre(self, op: str, v: dict):
        if op == "getTests":
            return {"results": [{"issueId": self.tests[k], "jira": {"key": k, "summary": k}}
                                for k in self._cles(v) if k in self.tests]}
        if op == "getTestPlans":
            return {"results": [{"issueId": i, "jira": {"key": k}} for i, k in self.plans.items()
                                if k in self._cles(v)]}
        if op == "getTestExecutions":
            return {"results": [{"issueId": i, "jira": {"key": e["key"]}} for i, e in self.executions.items()
                                if e["key"] in self._cles(v)]}
        if op == "createTestPlan":
            i = str(next(self._ids))
            self.plans[i] = f"DEMO-{i}"
            return {"testPlan": {"issueId": i, "jira": {"key": self.plans[i]}}, "warnings": []}
        if op == "createTestExecution":
            i = str(next(self._ids))
            self.executions[i] = {"key": f"DEMO-{i}", "tests": list(v.get("t") or [])}
            for t in v.get("t") or []:
                self.runs[(i, t)] = f"run-{i}-{t}"
            return {"testExecution": {"issueId": i, "jira": {"key": self.executions[i]["key"]}}, "warnings": []}
        if op == "addTestsToTestExecution":
            for t in v.get("t") or []:
                self.runs.setdefault((v["e"], t), f"run-{v['e']}-{t}")
            return {"addedTests": v.get("t"), "warning": None}
        if op in ("addTestExecutionsToTestPlan", "addTestsToTestPlan"):
            return {"warning": None}
        if op == "getTestRuns":
            return {"results": [{"id": r, "test": {"issueId": t}} for (e, t), r in self.runs.items()
                                if e in (v.get("e") or []) and t in (v.get("t") or [])]}
        if op == "updateTestRunStatus":
            self.statuts.setdefault(v["id"], []).append(v["s"])
            return None
        if op == "updateTestRun":
            # règle constatée sur Xray Cloud (essai réel du 2026-11-14) : finishedOn exige un statut final
            if "finishedOn" in v and (self.statuts.get(v["id"]) or ["TO DO"])[-1] in ("TODO", "TO DO", "EXECUTING", "BLOCKED"):
                raise RefusXray("Cannot set finishedOn because test run status is not final.")
            self.maj_runs[v["id"]] = {k: v[k] for k in v if k != "id"}
            return {"warnings": []}
        if op == "addEvidenceToTestRun":
            self.preuves.setdefault(v["id"], []).extend(e["filename"] for e in v["ev"])
            return {"addedEvidence": [], "warnings": []}
        raise AssertionError(op)

    def statut_final(self, cle: str) -> str | None:
        tid = self.tests[cle]
        runs = [r for (e, t), r in self.runs.items() if t == tid]
        return self.statuts.get(runs[-1], [None])[-1] if runs else None


class RefusXray(Exception):
    """Refus métier renvoyé dans « errors » d'une réponse GraphQL 200."""


def schema_conforme() -> dict:
    """Schéma d'introspection minimal qui contient tous les appels du client."""
    from atelier.integrations.xray.verification import MUTATIONS, REQUETES

    def champs(table):
        return [{"name": n, "args": [{"name": a, "defaultValue": None, "type": {"kind": "SCALAR", "name": "String"}}
                                     for a in args]} for n, args in table.items()]
    return {"__schema": {"queryType": {"fields": champs(REQUETES)}, "mutationType": {"fields": champs(MUTATIONS)}},
            "attachment": {"inputFields": [{"name": "filename"}, {"name": "mimeType"}, {"name": "data"}]}}
