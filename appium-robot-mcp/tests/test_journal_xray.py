"""Phase 1.3 : journal Xray local et synchronisation avec reprise, découplés du run Robot."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from conftest import RACINE
from faux_xray import FauxXray

SUITE = """*** Test Cases ***
Virement Nominal
    [Tags]    DEMO-1    smoke
    Log    ok

Virement En Echec
    [Tags]    DEMO-2
    Fail    Solde insuffisant

Virement Android Aussi
    [Tags]    DEMO-1
    Log    même clé Xray que le premier test
"""


@pytest.fixture
def xray(monkeypatch):
    faux = FauxXray()
    monkeypatch.setenv("XRAY_BASE_URL", faux.demarrer())
    monkeypatch.setenv("XRAY_CLIENT_ID", "id-de-test")
    monkeypatch.setenv("XRAY_CLIENT_SECRET", "secret-de-test")
    monkeypatch.setenv("XRAY_SYNC_BACKOFF", "0.05")
    monkeypatch.setenv("XRAY_SYNC_ESSAIS", "5")
    monkeypatch.setenv("XRAY_SYNC_DELAI_FIN", "3")
    yield faux
    faux.arreter()


def _journal_type(dossier):
    from atelier.execution.journal_xray import Journal

    j = Journal(dossier)
    j.ajouter("r1", "preparation", ticket="DEMO", cles_tests=["DEMO-1", "DEMO-2"], exec_summary="Exécution test")
    j.ajouter("r1", "test_debut", "s1-t1", cle_xray="DEMO-1", debut="2026-11-14T10:00:00+01:00")
    j.ajouter("r1", "test_fin", "s1-t1", cle_xray="DEMO-1", statut="PASSED", debut="2026-11-14T10:00:00+01:00",
              fin="2026-11-14T10:00:05+01:00")
    j.ajouter("r1", "test_debut", "s1-t2", cle_xray="DEMO-2", debut="2026-11-14T10:00:06+01:00")
    j.ajouter("r1", "test_fin", "s1-t2", cle_xray="DEMO-2", statut="FAILED", debut="2026-11-14T10:00:06+01:00",
              fin="2026-11-14T10:00:07+01:00", commentaire="Échec : solde insuffisant")
    return j


# --------------------------------------------------------------------------- journal
def test_cles_d_idempotence_uniques(tmp_path):
    j = _journal_type(tmp_path)
    cles = [e["cle"] for e in j.evenements()]
    assert len(cles) == len(set(cles)) == 5
    assert [e["type"] for e in j.evenements()] == ["preparation", "test_debut", "test_fin", "test_debut", "test_fin"]


def test_ligne_tronquee_ignoree(tmp_path):
    j = _journal_type(tmp_path)
    with j.fichier.open("a") as f:
        f.write('{"cle": "coupé')
    assert len(j.evenements()) == 5


# --------------------------------------------------------------------------- synchroniseur
def test_xray_echoue_3_fois_puis_repond(tmp_path, xray):
    from atelier.execution.journal_xray import Synchroniseur

    j = _journal_type(tmp_path)
    xray.echecs_restants = 3
    attentes = []
    bilan = Synchroniseur(tmp_path, sommeil=attentes.append).envoyer_tout()
    assert bilan == {"envoyes": 5, "ignores": 0, "restants": 0, "erreur": ""}
    assert attentes == [0.05, 0.1, 0.2]                       # backoff exponentiel
    assert xray.appels.count("createTestPlan") == 1           # aucun doublon
    assert xray.appels.count("createTestExecution") == 1
    assert xray.appels.count("updateTestRunStatus") == 4      # 2 tests × (EXECUTING + final)
    assert xray.statut_final("DEMO-1") == "PASSED" and xray.statut_final("DEMO-2") == "FAILED"
    assert len(j.envoyes()) == 5
    # rejeu : rien n'est renvoyé
    avant = list(xray.appels)
    assert Synchroniseur(tmp_path).envoyer_tout()["envoyes"] == 0
    assert xray.appels == avant


def test_xray_indisponible_puis_rejeu(tmp_path, xray):
    from atelier.execution.journal_xray import Synchroniseur

    _journal_type(tmp_path)
    xray.indisponible = True
    bilan = Synchroniseur(tmp_path, sommeil=lambda s: None).envoyer_tout()
    assert bilan["envoyes"] == 0 and bilan["restants"] == 5 and "preparation" in bilan["erreur"]
    xray.indisponible = False
    bilan = Synchroniseur(tmp_path).envoyer_tout()
    assert bilan["envoyes"] == 5 and bilan["restants"] == 0
    assert xray.appels.count("createTestExecution") == 1


def test_creation_jamais_refaite_apres_coupure_au_milieu(tmp_path, xray, monkeypatch):
    """Le plan est créé, puis Xray tombe avant la création de l'exécution : le rejeu ne recrée pas le plan."""
    from atelier.execution.journal_xray import Synchroniseur
    from atelier.integrations.xray import XrayClient

    _journal_type(tmp_path)
    vrai = XrayClient.create_execution

    def coupure(self, *a, **k):
        xray.indisponible = True
        return vrai(self, *a, **k)
    monkeypatch.setattr(XrayClient, "create_execution", coupure)
    assert Synchroniseur(tmp_path, sommeil=lambda s: None).envoyer_tout()["restants"] == 5
    monkeypatch.setattr(XrayClient, "create_execution", vrai)
    xray.indisponible = False
    assert Synchroniseur(tmp_path).envoyer_tout()["restants"] == 0
    assert xray.appels.count("createTestPlan") == 1 and xray.appels.count("createTestExecution") == 1


def test_ticket_qui_est_un_test_abandonne_sans_boucler(tmp_path, xray):
    from atelier.execution.journal_xray import Journal, Synchroniseur

    j = Journal(tmp_path)
    j.ajouter("r1", "preparation", ticket="DEMO-1", cles_tests=["DEMO-1"], exec_summary="x")
    j.ajouter("r1", "test_fin", "t1", cle_xray="DEMO-1", statut="PASSED", fin="x")
    bilan = Synchroniseur(tmp_path).envoyer_tout()
    assert bilan["ignores"] == 2 and bilan["restants"] == 0
    assert "createTestExecution" not in xray.appels


# --------------------------------------------------------------------------- run Robot réel
@pytest.fixture
def suite(projet):
    f = projet / "tests" / "virement.robot"
    f.parent.mkdir()
    f.write_text(SUITE, "utf-8")
    return "tests/virement.robot"


def test_run_avec_xray_en_direct(suite, xray):
    import server

    bilan = server.run_robot(suite, xray_ticket="DEMO", variables={"PLATFORM": "android"})
    assert bilan["resultat"]["echecs"] == 1, bilan["erreurs"]
    rapport = bilan["xray"]
    assert rapport["execution"] and rapport["mode"] == "plan créé + exécution"
    assert rapport["synchro"]["restants"] == 0
    assert xray.statut_final("DEMO-1") == "PASSED" and xray.statut_final("DEMO-2") == "FAILED"
    # plusieurs tests Robot sur DEMO-1 : un seul EXECUTING
    run_demo1 = next(r for (e, t), r in xray.runs.items() if t == "1001")
    assert xray.statuts[run_demo1][0] == "EXECUTING" and xray.statuts[run_demo1].count("EXECUTING") == 1
    assert "solde insuffisant" in xray.maj_runs[next(r for (e, t), r in xray.runs.items() if t == "1002")]["comment"].lower()
    assert all(t["run_id"] for t in rapport["tests"])


def test_run_termine_meme_si_xray_injoignable_puis_rejeu(suite, xray, projet):
    import server

    xray.indisponible = True
    bilan = server.run_robot(suite, xray_ticket="DEMO")
    assert bilan["resultat"]["passes"] == 2 and bilan["resultat"]["echecs"] == 1   # le run est allé au bout
    assert bilan["xray"]["execution"] is None and bilan["xray"]["synchro"]["restants"] == 6
    journal = bilan["xray"]["synchro"]["journal"]
    lignes = [json.loads(x) for x in open(journal, encoding="utf-8")]
    assert [x["type"] for x in lignes].count("test_fin") == 3                        # journal complet

    xray.indisponible = False
    r = subprocess.run([sys.executable, "-m", "atelier", "xray-sync", str(projet / "results" / "mcp")],
                       cwd=RACINE, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    sortie = json.loads(r.stdout.splitlines()[-1])
    assert sortie["envoyes"] == 6 and sortie["restants"] == 0
    assert xray.statut_final("DEMO-1") == "PASSED" and xray.statut_final("DEMO-2") == "FAILED"
    # second rejeu : aucun doublon
    nb = len(xray.appels)
    r = subprocess.run([sys.executable, "-m", "atelier", "xray-sync", str(projet / "results" / "mcp")],
                       cwd=RACINE, capture_output=True, text=True, timeout=60)
    assert json.loads(r.stdout)["envoyes"] == 0 and len(xray.appels) == nb


def test_cli_sans_journal(tmp_path):
    r = subprocess.run([sys.executable, "-m", "atelier", "xray-sync", str(tmp_path)],
                       cwd=RACINE, capture_output=True, text=True, timeout=60)
    assert r.returncode == 2 and "Aucun journal" in r.stderr


def test_xray_injoignable_jamais_pris_pour_introuvable(xray):
    """Défaut du prototype : une coupure pendant resolve / test_ids donnait « ticket autre » ou
    « test inconnu », et les résultats n'étaient jamais remontés."""
    from atelier.integrations.xray import XrayClient

    xray.indisponible = True
    with pytest.raises(RuntimeError):
        XrayClient().resolve("DEMO-77")
    with pytest.raises(RuntimeError):
        XrayClient().test_ids(["DEMO-1"])
    xray.indisponible = False
    assert XrayClient().test_ids(["DEMO-1", "DEMO-404"]) == {"DEMO-1": "1001"}
