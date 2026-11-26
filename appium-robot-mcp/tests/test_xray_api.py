"""Phase 1.4 : vérification de l'API Xray par introspection (faux serveur) et statuts personnalisés."""
from __future__ import annotations

import subprocess
import sys

import pytest

from conftest import RACINE
from faux_xray import FauxXray, schema_conforme
from test_journal_xray import SUITE, _journal_type


@pytest.fixture
def xray(monkeypatch):
    faux = FauxXray()
    monkeypatch.setenv("XRAY_BASE_URL", faux.demarrer())
    monkeypatch.setenv("XRAY_CLIENT_ID", "id-de-test")
    monkeypatch.setenv("XRAY_CLIENT_SECRET", "secret-de-test")
    monkeypatch.setenv("XRAY_SYNC_BACKOFF", "0.05")
    yield faux
    faux.arreter()


def test_schema_conforme():
    from atelier.integrations.xray.verification import comparer

    res = comparer(schema_conforme())
    assert res["ok"] and res["requetes_statuts"] == []


def test_ecarts_detectes():
    from atelier.integrations.xray.verification import comparer

    s = schema_conforme()
    mut = s["__schema"]["mutationType"]["fields"]
    s["__schema"]["mutationType"]["fields"] = [m for m in mut if m["name"] != "updateTestRun"]
    run_status = next(m for m in mut if m["name"] == "updateTestRunStatus")
    run_status["args"].append({"name": "projectId", "defaultValue": None, "type": {"kind": "NON_NULL"}})
    s["__schema"]["queryType"]["fields"].append({"name": "getStatuses", "args": []})
    s["attachment"]["inputFields"] = [{"name": "filename"}, {"name": "data"}]
    res = comparer(s)
    lignes = {x["nom"]: x for x in res["appels"]}
    assert not res["ok"]
    assert lignes["updateTestRun"]["present"] is False
    assert lignes["updateTestRunStatus"]["manquants"] == ["projectId"]
    assert res["types"][0]["inconnus"] == ["mimeType"]
    assert res["requetes_statuts"] == ["getStatuses"]


def test_commande_xray_verifier(xray, tmp_path):
    sortie = tmp_path / "XRAY_API_resultat.md"
    r = subprocess.run([sys.executable, "-m", "atelier", "xray-verifier", "--sortie", str(sortie)],
                       cwd=RACINE, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "**conforme**" in sortie.read_text("utf-8")


def test_statuts_personnalises(tmp_path, xray, monkeypatch):
    from atelier.execution.journal_xray import Synchroniseur

    monkeypatch.setenv("XRAY_STATUTS", '{"EXECUTING": "EN COURS"}')
    _journal_type(tmp_path)
    Synchroniseur(tmp_path).envoyer_tout()
    assert all(v[0] == "EN COURS" for v in xray.statuts.values())


def test_statuts_personnalises_dans_un_run(projet, xray, monkeypatch):
    import server

    monkeypatch.setenv("XRAY_STATUTS", '{"PASS": "REUSSI", "FAIL": "ECHOUE"}')
    (projet / "tests").mkdir()
    (projet / "tests" / "v.robot").write_text(SUITE, "utf-8")
    bilan = server.run_robot("tests/v.robot", xray_ticket="DEMO")
    assert xray.statut_final("DEMO-1") == "REUSSI" and xray.statut_final("DEMO-2") == "ECHOUE", bilan["erreurs"]


def test_identifiants_nettoyes_des_guillemets(monkeypatch):
    """Une clé copiée avec ses guillemets ou espaces (Read-Host, .env) ne doit pas provoquer de 401."""
    from atelier.integrations.xray import XrayClient

    monkeypatch.setenv("XRAY_CLIENT_ID", ' "abc" ')
    monkeypatch.setenv("XRAY_CLIENT_SECRET", "'def'\n")
    c = XrayClient()
    assert (c.cid, c.secret) == ("abc", "def")


def test_resultats_robot_joints_apres_le_run(projet, xray, monkeypatch):
    """output.xml, log.html, report.html (n'existant qu'après Robot) sont joints en zip aux test runs."""
    import zipfile

    import server

    (projet / "tests").mkdir()
    (projet / "tests" / "v.robot").write_text(SUITE, "utf-8")
    monkeypatch.setenv("XRAY_ARTEFACTS", "tous")
    bilan = server.run_robot("tests/v.robot", xray_ticket="DEMO")
    art = bilan["xray"]["artefacts"]
    assert art["envoye"] and art["test_runs"] == ["DEMO-1", "DEMO-2"], art
    assert all("robot-resultats.zip" in p for p in xray.preuves.values())
    z = projet / "results" / "mcp" / "robot-resultats.zip"
    assert sorted(zipfile.ZipFile(z).namelist()) == ["log.html", "output.xml", "report.html"]
    monkeypatch.setenv("XRAY_ARTEFACTS", "echecs")
    bilan = server.run_robot("tests/v.robot", xray_ticket="DEMO")
    assert bilan["xray"]["artefacts"]["test_runs"] == ["DEMO-2"]


def test_log_total_joint_au_ticket_test_execution(projet, xray, monkeypatch):
    """En plus des test runs, l'archive des résultats (log, report, output) est jointe au ticket Test Execution."""
    import server
    from atelier.integrations import jira as jira_mod

    joints = []
    monkeypatch.setenv("JIRA_BASE_URL", "https://jira.exemple.invalid")
    monkeypatch.setenv("JIRA_EMAIL", "testeur@exemple.test")
    monkeypatch.setenv("JIRA_API_TOKEN", "jeton-de-test")
    monkeypatch.setattr(jira_mod.JiraClient, "joindre", lambda self, cle, chemin: joints.append((cle, chemin)))
    (projet / "tests").mkdir()
    (projet / "tests" / "v.robot").write_text(SUITE, "utf-8")
    bilan = server.run_robot("tests/v.robot", xray_ticket="DEMO")         # défaut : ticket + test runs en échec
    execution = bilan["xray"]["execution"]
    assert bilan["xray"]["artefacts"]["test_runs"] == ["DEMO-2"]
    assert bilan["xray"]["artefacts"]["envoye"], bilan["xray"]["artefacts"]
    assert joints and joints[0][0] == execution and joints[0][1].endswith("robot-resultats.zip")
