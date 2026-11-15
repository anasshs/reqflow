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

    def id_projet(self, projet: str) -> str:
        """Identifiant Jira (numérique) du projet, lu sur un test du projet : getStatuses l'exige."""
        if projet.isdigit():
            return projet
        q = 'query($jql: String) { getTests(jql: $jql, limit: 1) { results { jira(fields: ["project"]) } } }'
        res = self.gql(q, {"jql": f'project = "{projet}"'})["getTests"]["results"]
        if not res:
            raise RuntimeError(f"Aucun test Xray dans le projet {projet} : identifiant introuvable.")
        return str(((res[0].get("jira") or {}).get("project") or {}).get("id", ""))

    def statuts(self, project_id: str) -> list[dict]:
        """Statuts de test run du projet (schéma vérifié le 2026-11-14 : getStatuses(projectId))."""
        q = "query($p: String) { getStatuses(projectId: $p) { name description final color } }"
        return self.gql(q, {"p": project_id})["getStatuses"] or []

    # ------------------------------------------------------------ définitions de tests (Test Design, mode A)
    def _type_champs(self, nom: str) -> dict:
        """{champ: {args: {nom: obligatoire}}} d'un type GraphQL, par introspection (rien n'est supposé)."""
        q = ('query($n: String!) { __type(name: $n) { fields { name args { name defaultValue type { kind } } '
             'type { kind name ofType { kind name ofType { kind name } } } } } }')
        t = (self.gql(q, {"n": nom}).get("__type") or {})
        return {f["name"]: {"args": {a["name"]: (a.get("type") or {}).get("kind") == "NON_NULL" and a.get("defaultValue") is None
                                     for a in f.get("args") or []}} for f in t.get("fields") or []}

    def selection_definitions(self) -> tuple[str, list[str]]:
        """Sélection GraphQL des champs de définition réellement présents sur le type Test, et liste des absents."""
        test, absents, sel = self._type_champs("Test"), [], ["issueId", 'jira(fields: ["key", "summary", "components", "labels"])']
        voulus = {"testType": "testType { name kind }", "gherkin": "gherkin", "unstructured": "unstructured",
                  "folder": "folder { path }", "steps": "steps { action data result }",
                  "preconditions": 'preconditions(limit: 20) { results { issueId jira(fields: ["key", "summary"]) } }'}
        for champ, texte in voulus.items():
            if champ not in test:
                absents.append(champ)
                continue
            if champ == "preconditions" and "limit" not in test[champ]["args"]:
                texte = texte.replace("(limit: 20)", "")
            sel.append(texte)
        return " ".join(sel), absents

    def conteneurs(self, projet: str, limite: int = 500) -> dict:
        """Test Plans et Test Sets du projet avec leurs tests (lecture seule). Requêtes et champs choisis par
        introspection : getTestPlans / getTestSets, champ « tests » et ses arguments ; un objet absent du schéma est
        signalé, jamais supposé. Plus de 100 tests dans un conteneur : signalé (tests_total)."""
        requete = self._type_champs("Query")
        out = {"plans": [], "test_sets": [], "absents": []}
        for cle_out, req, type_gql in (("plans", "getTestPlans", "TestPlan"), ("test_sets", "getTestSets", "TestSet")):
            if req not in requete:
                out["absents"].append(req)
                continue
            champs = self._type_champs(type_gql)
            t = "Int!" if requete[req]["args"].get("limit") else "Int"
            sel_tests = ""
            if "tests" in champs:
                a = champs["tests"]["args"]
                sel_tests = ("tests(limit: 100) " if "limit" in a else "tests ") + '{ total results { jira(fields: ["key"]) } }'
            else:
                out["absents"].append(f"{type_gql}.tests")
            pagine = "start" in requete[req]["args"]
            q = (f"query($jql: String, $l: {t}{', $s: Int' if pagine else ''}) {{ {req}(jql: $jql, limit: $l{', start: $s' if pagine else ''}) "
                 f'{{ total results {{ issueId jira(fields: ["key", "summary", "status"]) {sel_tests} }} }} }}')
            debut, brut = 0, []
            while len(brut) < limite:
                page = self.gql(q, {"jql": f'project = "{projet}"', "l": 100, **({"s": debut} if pagine else {})})[req]
                brut += page["results"]
                debut += 100
                if not pagine or not page["results"] or debut >= (page.get("total") or 0):
                    break
            for x in brut:
                j = x.get("jira") or {}
                tests = x.get("tests") or {}
                out[cle_out].append({"cle": j.get("key"), "resume": j.get("summary") or "", "statut": (j.get("status") or {}).get("name", ""),
                                     "issueId": x.get("issueId"), "tests": [(t.get("jira") or {}).get("key") for t in tests.get("results") or []],
                                     "tests_total": tests.get("total")})
        return out

    def executions(self, projet: str, limite: int = 200) -> dict:
        """Test Executions du projet, les plus récentes d'abord : clé, résumé, statut Jira, environnements, tests et
        statut de chaque test run (lecture seule). Requête et champs choisis par introspection (getTestExecutions,
        TestExecution.tests / testRuns / testEnvironments, TestRun.status / test / finishedOn) : un champ absent du
        schéma est signalé, jamais supposé. Plus de 100 tests ou runs dans une exécution : signalé (tests_total)."""
        requete = self._type_champs("Query")
        out = {"executions": [], "absents": []}
        if "getTestExecutions" not in requete:
            out["absents"].append("getTestExecutions")
            return out
        champs = self._type_champs("TestExecution")
        sel = ['issueId', 'jira(fields: ["key", "summary", "status", "created"])']
        if "testEnvironments" in champs:
            sel.append("testEnvironments")
        else:
            out["absents"].append("TestExecution.testEnvironments")
        if "tests" in champs:
            sel.append(("tests(limit: 100) " if "limit" in champs["tests"]["args"] else "tests ") + '{ total results { jira(fields: ["key"]) } }')
        else:
            out["absents"].append("TestExecution.tests")
        if "testRuns" in champs:
            run = self._type_champs("TestRun")
            sel_run = [x for x, c in (("status { name }", "status"), ('test { jira(fields: ["key"]) }', "test"), ("finishedOn", "finishedOn")) if c in run]
            out["absents"] += [f"TestRun.{c}" for c in ("status", "test", "finishedOn") if c not in run]
            if "status" in run and "test" in run:
                sel.append(("testRuns(limit: 100) " if "limit" in champs["testRuns"]["args"] else "testRuns ") + "{ total results { " + " ".join(sel_run) + " } }")
        else:
            out["absents"].append("TestExecution.testRuns")
        t = "Int!" if requete["getTestExecutions"]["args"].get("limit") else "Int"
        pagine = "start" in requete["getTestExecutions"]["args"]
        q = (f"query($jql: String, $l: {t}{', $s: Int' if pagine else ''}) {{ getTestExecutions(jql: $jql, limit: $l{', start: $s' if pagine else ''}) "
             f"{{ total results {{ {' '.join(sel)} }} }} }}")
        debut, brut = 0, []
        while len(brut) < limite:
            page = self.gql(q, {"jql": f'project = "{projet}" ORDER BY created DESC', "l": min(100, limite), **({"s": debut} if pagine else {})})["getTestExecutions"]
            brut += page["results"]
            debut += 100
            if not pagine or not page["results"] or debut >= (page.get("total") or 0):
                break
        for x in brut[:limite]:
            j = x.get("jira") or {}
            tests = x.get("tests") or {}
            runs = {}
            for r in (x.get("testRuns") or {}).get("results") or []:
                cle = ((r.get("test") or {}).get("jira") or {}).get("key")
                if cle:
                    runs[cle] = {"statut": (r.get("status") or {}).get("name", ""), "fin": r.get("finishedOn") or ""}
            out["executions"].append({"cle": j.get("key"), "resume": j.get("summary") or "", "statut": (j.get("status") or {}).get("name", ""),
                                      "cree": j.get("created") or "", "issueId": x.get("issueId"), "environnements": x.get("testEnvironments") or [],
                                      "tests": [(t_.get("jira") or {}).get("key") for t_ in tests.get("results") or []] or sorted(runs),
                                      "tests_total": tests.get("total") or (x.get("testRuns") or {}).get("total"), "runs": runs})
        return out

    def definitions_tests(self, cles: list[str] | None = None, jql: str = "", limite: int = 2000) -> dict:
        """Définitions Xray (type, étapes, Gherkin, définition Generic, dossier, préconditions) des tests donnés
        (par lots de 100 clés) ou d'un JQL (pages de 100). Lecture seule."""
        sel, absents = self.selection_definitions()
        args = self._type_champs("Query").get("getTests", {}).get("args", {})
        pagine = "start" in args
        # types des variables = ceux du schéma (limit est « Int! » sur Xray Cloud, constaté le 2026-11-14)
        t = lambda n: "Int!" if args.get(n) else "Int"  # noqa: E731
        q = (f"query($jql: String, $l: {t('limit')}{', $s: ' + t('start') if pagine else ''}) "
             f"{{ getTests(jql: $jql, limit: $l{', start: $s' if pagine else ''}) {{ total results {{ {sel} }} }} }}")
        brut: list[dict] = []
        if cles is not None and not cles:
            return {"tests": [], "champs_absents": absents, "pagination": pagine}
        if not jql and not cles:
            raise ValueError("Clés de tests ou JQL requis (jamais tous les tests de tous les projets).")
        if cles:
            cles = list(dict.fromkeys(cles))
            for i in range(0, len(cles), 100):
                lot = cles[i:i + 100]
                try:
                    brut += self.gql(q, {"jql": f"key in ({', '.join(lot)})", "l": 100, **({"s": 0} if pagine else {})})["getTests"]["results"]
                except ErreurGraphQL:  # une clé inconnue fait échouer le JQL : clé par clé
                    for k in lot:
                        try:
                            brut += self.gql(q, {"jql": f'key = "{k}"', "l": 1, **({"s": 0} if pagine else {})})["getTests"]["results"]
                        except ErreurGraphQL:
                            pass
        else:
            debut = 0
            while len(brut) < limite:
                page = self.gql(q, {"jql": jql, "l": 100, **({"s": debut} if pagine else {})})["getTests"]
                brut += page["results"]
                debut += 100
                if not pagine or not page["results"] or debut >= (page.get("total") or 0):
                    break
        tronque = not cles and len(brut) >= limite  # par clés : toutes les clés demandées sont lues, sans plafond
        if tronque:
            brut = brut[:limite]
        return {"tests": [_definition(x) for x in brut], "champs_absents": absents, "pagination": pagine, "tronque": tronque}

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

    # ------------------------------------------------------------ tests Cucumber (Test Design, mode C / B)
    def creer_test_cucumber(self, projet: str, resume: str, gherkin: str) -> dict:
        """Crée un Test Xray de type Cucumber (mutation createTest, vérifiée par xray-verifier)."""
        q = ('mutation($tt: UpdateTestTypeInput, $g: String, $j: JSON!) { createTest(testType: $tt, gherkin: $g, jira: $j) '
             '{ test { issueId jira(fields: ["key"]) } warnings } }')
        r = self.gql(q, {"tt": {"name": "Cucumber"}, "g": gherkin, "j": {"fields": {"summary": resume, "project": {"key": projet}}}})
        t = r["createTest"]["test"]
        return {"cle": t["jira"]["key"], "issueId": t["issueId"], "avertissements": r["createTest"].get("warnings") or []}

    def ranger_test(self, projet: str, issue_id: str, chemin: str) -> dict:
        """Range un test dans un dossier du Test Repository, créé au besoin (parents compris). Mutations et arguments
        vérifiés par introspection (createFolder, addTestsToFolder) : absents du schéma = erreur explicite."""
        mut = self._type_champs("Mutation")
        add = mut.get("addTestsToFolder")
        if not add or not {"projectId", "path", "testIssueIds"} <= set(add["args"]):
            raise RuntimeError("Le schéma Xray n'expose pas addTestsToFolder(projectId, path, testIssueIds) : test laissé à la racine.")
        pid = self.id_projet(projet)
        crees = []
        cf = mut.get("createFolder")
        if cf and {"projectId", "path"} <= set(cf["args"]):
            parties = [p for p in chemin.split("/") if p]
            for i in range(1, len(parties) + 1):
                sous = "/" + "/".join(parties[:i])
                try:
                    self.gql("mutation($p: String!, $c: String!) { createFolder(projectId: $p, path: $c) { folder { path } warnings } }",
                             {"p": pid, "c": sous})
                    crees.append(sous)
                except Exception:  # noqa: BLE001 - dossier déjà présent : rien à créer
                    pass
        self.gql("mutation($p: String!, $c: String!, $t: [String]!) { addTestsToFolder(projectId: $p, path: $c, testIssueIds: $t) { folder { path } warnings } }",
                 {"p": pid, "c": chemin, "t": [issue_id]})
        return {"dossier": chemin, "dossiers_crees": crees}

    def creer_test_manuel(self, projet: str, resume: str, etapes: list[dict]) -> dict:
        """Crée un Test Xray de type Manual avec ses étapes (createTest, argument steps : vérifié par xray-verifier)."""
        q = ('mutation($tt: UpdateTestTypeInput, $s: [CreateStepInput], $j: JSON!) { createTest(testType: $tt, steps: $s, jira: $j) '
             '{ test { issueId jira(fields: ["key"]) } warnings } }')
        steps = [{"action": e.get("action") or "", "data": e.get("donnees") or "", "result": e.get("resultat") or ""} for e in etapes]
        r = self.gql(q, {"tt": {"name": "Manual"}, "s": steps, "j": {"fields": {"summary": resume, "project": {"key": projet}}}})
        t = r["createTest"]["test"]
        return {"cle": t["jira"]["key"], "issueId": t["issueId"], "avertissements": r["createTest"].get("warnings") or []}

    def lire_gherkin(self, cle: str) -> dict | None:
        q = 'query($jql: String) { getTests(jql: $jql, limit: 1) { results { issueId gherkin testType { name } jira(fields: ["key"]) } } }'
        res = self.gql(q, {"jql": f"key = {cle}"})["getTests"]["results"]
        return {"issueId": res[0]["issueId"], "gherkin": res[0].get("gherkin") or "", "type": (res[0].get("testType") or {}).get("name")} if res else None

    def maj_gherkin(self, issue_id: str, gherkin: str):
        q = 'mutation($id: String!, $g: String!) { updateGherkinTestDefinition(issueId: $id, gherkin: $g) { issueId } }'
        return self.gql(q, {"id": issue_id, "g": gherkin})

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


def _definition(x: dict) -> dict:
    """Résultat getTests -> champs de l'instantané. Un champ absent de la réponse reste absent."""
    j = x.get("jira") or {}
    out = {"cle": j.get("key"), "resume": j.get("summary"), "issueId": x.get("issueId")}
    if j.get("components"):
        out["composants"] = [c.get("name") if isinstance(c, dict) else str(c) for c in j["components"]]
    if j.get("labels"):
        out["libelles"] = list(j["labels"])
    if x.get("testType"):
        out["type"] = x["testType"].get("name")
        out["type_genre"] = x["testType"].get("kind")
    if "steps" in x and x["steps"] is not None:
        out["etapes"] = [{"action": e.get("action") or "", "donnees": e.get("data") or "", "resultat": e.get("result") or ""}
                         for e in x["steps"]]
    if x.get("gherkin"):
        out["gherkin"] = x["gherkin"]
    if x.get("unstructured"):
        out["definition"] = x["unstructured"]
    if "folder" in x:
        out["dossier"] = (x.get("folder") or {}).get("path") or "/"
    if "preconditions" in x and x["preconditions"] is not None:
        out["preconditions"] = [{"cle": (p.get("jira") or {}).get("key"), "resume": (p.get("jira") or {}).get("summary")}
                                for p in x["preconditions"].get("results") or []]
    return out
