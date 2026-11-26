"""Processus d'une release dans QAFlow : la sortie est une Test Execution Xray rangée dans le Test Plan de la release,
puis exécutée (résultats écrits dans cette exécution) jusqu'au verdict du build. Xray est simulé."""
import shutil

from tests.test_releases import DEMO

NOTE = "Release 3.0.0\n\nNouveautés\n- DEMO-312 : réinitialisation du mot de passe par e-mail\n"


class FauxXray:
    def __init__(self):
        self.n, self.plans, self.executions = 100, [], []

    def _cle(self):
        self.n += 1
        return f"id{self.n}", f"DEMO-{self.n}"

    def create_plan(self, projet, resume, tests):
        i, c = self._cle()
        self.plans.append({"cle": c, "resume": resume, "executions": [], "tests": []})
        return i, c

    def test_ids(self, cles):
        return {c: f"t-{c}" for c in cles}

    def create_execution(self, projet, resume, ids, envs):
        i, c = self._cle()
        self.executions.append({"issue": i, "cle": c, "resume": resume, "tests": ids, "envs": envs})
        return i, c

    def add_execs_to_plan(self, plan, execs):
        self.plans[-1]["executions"] += execs

    def add_tests_to_plan(self, plan, ids):
        self.plans[-1]["tests"] += ids


def test_de_la_release_note_a_l_execution_xray(projet, monkeypatch, tmp_path):
    shutil.copytree(DEMO, projet, dirs_exist_ok=True, ignore=shutil.ignore_patterns("results", "connaissance", "strategie"))
    from fastapi.testclient import TestClient
    from web_app_loader import charger_app_web, module_web

    from atelier.domain import projets
    from atelier.intelligence import plan_release

    x = FauxXray()
    monkeypatch.setattr(plan_release, "_xray", lambda xray=None: x)
    monkeypatch.setattr(plan_release, "environnements", lambda: ["recette", "preprod"])
    monkeypatch.setattr(projets, "cle_xray", lambda *a, **k: "DEMO")
    monkeypatch.setattr(module_web(), "CONFIG_PATH", tmp_path / "atelier.json")
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    c.get("/qaflow")

    def etapes(rid):
        p = c.get(f"/api/qaflow/releases/{rid}/processus").json()
        return p, {e["id"]: e["fait"] for e in p["etapes"]}

    rid = c.post("/api/releases", json={"nom": "Release 3.0", "version": "3.0.0", "texte": NOTE}).json()["id"]
    p, f = etapes(rid)
    assert p["courante"] == "build" and f["note"] and not f["build"]
    c.post(f"/api/releases/{rid}/builds", json={"numero": "3.0.0", "date_reception": "2026-11-26"})
    p, f = etapes(rid)
    bid = p["build"]["id"]
    assert p["courante"] == "perimetre"
    assert c.post(f"/api/releases/{rid}/builds/{bid}/operation", json={"op": "valider"}).status_code == 200
    p, f = etapes(rid)
    assert p["courante"] == "plan" and f["perimetre"]

    # sortie de la release : une Test Execution dans le Test Plan (créé au passage), environnement choisi
    g = c.get(f"/api/releases/{rid}/builds/{bid}/executions?decoupage=unique").json()
    r = c.post(f"/api/releases/{rid}/plan", json={"op": "executions", "build": bid,
                                                 "groupes": [dict(x_, environnement="recette") for x_ in g]})
    assert r.status_code == 200, r.text
    assert len(x.plans) == 1 and len(x.executions) == 1 and x.executions[0]["envs"] == ["recette"]
    assert x.plans[0]["executions"] == [x.executions[0]["issue"]]               # l'exécution est rangée dans le plan
    p, f = etapes(rid)
    assert f["plan"] and f["execution"] and p["courante"] == "lancement"
    assert p["executions"][0]["xray"]["cle"] == x.executions[0]["cle"] and p["plan"]["cle"] == x.plans[0]["cle"]

    # exécution : une campagne par Test Execution, qui écrit ses résultats dans CETTE exécution
    r = c.post(f"/api/releases/{rid}/builds/{bid}/operation", json={"op": "campagne", "par_execution": True})
    assert r.status_code == 200, r.text
    p, f = etapes(rid)
    assert f["lancement"] and p["campagnes"][0]["execution"] == x.executions[0]["cle"]
    assert p["courante"] == "resultats" and not f["verdict"]
    assert c.post(f"/api/releases/{rid}/builds/{bid}/operation", json={"op": "failed", "motif": "anomalie bloquante"}).status_code == 200
    p, f = etapes(rid)
    assert f["verdict"] and p["build"]["statut"] == "Failed"


def test_xray_non_configure_reste_lisible(projet):
    shutil.copytree(DEMO, projet, dirs_exist_ok=True, ignore=shutil.ignore_patterns("results", "connaissance", "strategie"))
    from atelier.intelligence import qaflow, releases

    rid = releases.creer(NOTE, nom="Release 3.0")["id"]
    p = qaflow.processus_release(rid)
    assert [e["id"] for e in p["etapes"]] == ["note", "build", "perimetre", "plan", "execution", "lancement", "resultats", "verdict"]
    assert p["courante"] == "build" and p["executions"] == []
