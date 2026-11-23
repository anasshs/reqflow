"""Tests automatisés, vue simple : run de tests précis (--test), « vérifié » = run réel postérieur aux modifications,
Valider en un clic, Écarter, maintenance d'une sélection, et vérification permise avant validation sauf donnée réelle."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import pointer_projet

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"
SUITE = "tests/connexion.robot"
INVALIDE = f"{SUITE}::Connexion refusée avec un mot de passe invalide"
INCONNU = f"{SUITE}::Connexion refusée avec un identifiant inconnu"


@pytest.fixture
def demo(tmp_path, monkeypatch):
    d = tmp_path / "demo"
    shutil.copytree(DEMO, d, ignore=shutil.ignore_patterns("results", "connaissance", "studio", "executions"))
    pointer_projet(d, monkeypatch)
    return d


def _suite(v, fichier=SUITE):
    return next(s for s in v["suites"] if s["fichier"] == fichier)


def test_selection_de_tests_precis(demo):
    from atelier.execution.robot import selection_tests

    with pytest.raises(ValueError, match="pas les deux"):
        selection_tests([SUITE, INVALIDE])


def test_run_de_deux_tests_precis_et_verifie_seulement_en_run_reel(demo):
    from atelier.execution.robot import run_robot, selection_tests
    from atelier.generation import maintenance

    assert selection_tests([INVALIDE, INCONNU]) == {"fichiers": [SUITE], "noms": [INVALIDE.split("::")[1], INCONNU.split("::")[1]],
                                                     "cible": SUITE}
    r = run_robot("", tests=[INVALIDE, INCONNU], output_dir="results/verif", xray_mode="aucun")
    assert r["resultat"]["passes"] == 2 and r["resultat"]["echecs"] == 0, r.get("erreurs")  # deux tests, pas la suite (7)
    assert r["jdd"]["env"] == "recette"  # environnement des données déduit
    run_robot(SUITE, dry_run=True, output_dir="results/dry", xray_mode="aucun")  # un dry run ne vérifie rien
    tests = {t["id"]: t for t in _suite(maintenance.vue())["tests"]}
    assert tests[INVALIDE]["verifie"] and tests[INCONNU]["verifie"]
    autre = tests[f"{SUITE}::Déconnexion"]
    assert not autre["verifie"] and autre["dernier"] is None  # seulement un dry run : « jamais exécuté »
    # une page modifiée après le run : la vérification ne vaut plus
    page = demo / "resources" / "socle" / "connexion.resource"
    page.write_text(page.read_text("utf-8") + "\n", "utf-8")
    tests = {t["id"]: t for t in _suite(maintenance.vue())["tests"]}
    assert not tests[INVALIDE]["verifie"] and tests[INVALIDE]["perime"]


def test_valider_exige_la_verification_sinon_une_derogation(demo):
    from atelier.execution.robot import run_robot
    from atelier.generation import maintenance, studio

    studio.entrer_en_revue(SUITE, "cursor")
    assert _suite(maintenance.vue())["etat"] == "À valider"
    r = maintenance.valider([INVALIDE])
    assert not r[0]["ok"] and r[0]["message"].startswith("Vérifier d'abord")
    run_robot(SUITE, output_dir="results/verif", xray_mode="aucun")  # toute la suite en run réel : DEMO-304 échoue (anomalie de la démo)
    r = maintenance.valider([INVALIDE])
    assert not r[0]["ok"] and r[0]["message"] == ("Vérifier d'abord en run réel : Blocage du compte après trois échecs "
                                                  "(bouton « Vérifier »), ou justifier une dérogation.")
    r = maintenance.valider([INVALIDE], derogation="DEMO-304 : anomalie connue de l'application, test conservé")
    assert r[0]["ok"] and r[0]["etat"] == "Validé", r[0]["message"]
    assert studio.revues_scripts()[SUITE]["statut"] == "Published" and _suite(maintenance.vue())["etat"] == "Validé"
    # une page de la suite modifiée depuis : « À valider », et Valider la remet en revue avant de la valider
    page = demo / "resources" / "socle" / "connexion.resource"
    page.write_text(page.read_text("utf-8") + "\n", "utf-8")

    import time

    time.sleep(2.5)  # dates à la seconde : modification nettement après la validation, nouvelle validation après elle
    page.write_text(page.read_text("utf-8") + "\n", "utf-8")
    assert _suite(maintenance.vue())["etat"] == "À valider"
    time.sleep(1.5)
    r = maintenance.valider([SUITE], derogation="ligne vide ajoutée, aucun changement de comportement")
    assert r[0]["ok"] and _suite(maintenance.vue())["etat"] == "Validé"


def test_ecarter_exige_un_motif(demo):
    from atelier.generation import maintenance, studio

    studio.entrer_en_revue(SUITE, "cursor")
    with pytest.raises(ValueError, match="Motif"):
        maintenance.ecarter([SUITE], "")
    assert maintenance.ecarter([INVALIDE], "doublon du test DEMO-303")[0]["etat"] == "Écarté"
    assert _suite(maintenance.vue())["etat"] == "Écarté"


def test_verification_avant_validation_sauf_donnee_reelle(demo):
    from atelier.execution import centre
    from atelier.generation import maintenance, studio

    studio.entrer_en_revue(SUITE, "cursor")
    with pytest.raises(PermissionError):
        centre.controle_revue(SUITE)  # toute la suite, non validée : bloqué comme avant
    assert centre.controle_revue(SUITE, tests=[INVALIDE])["verification"]  # vérification d'un test précis : permise
    f = demo / SUITE
    f.write_text(f.read_text("utf-8").replace("[Tags]    DEMO-307    smoke", "[Tags]    DEMO-307    smoke    consomme_donnee"), "utf-8")
    deco = f"{SUITE}::Déconnexion"
    assert maintenance.controle_verification([deco])["bloquants"] == ["Déconnexion"]
    with pytest.raises(PermissionError, match="donnée réelle"):
        centre.controle_revue(SUITE, tests=[deco])
    assert centre.controle_revue(SUITE, tests=[deco], derogation="compte de démo remis à zéro chaque nuit")["derogation"]
    assert centre.controle_revue(SUITE, dry_run=True, tests=[deco])["non_valides"]  # dry run : libre, comme avant


def test_demande_de_maintenance_pour_une_selection(demo):
    from atelier.execution.robot import run_robot
    from atelier.generation import maintenance

    run_robot("", tests=[INVALIDE], output_dir="results/verif", xray_mode="aucun")
    d = maintenance.demande_maintenance([INVALIDE, "tests/connexion.robot"], "le message d'erreur a changé")
    assert d["titre"] == "Maintenance : 7 test(s)" and len(d["tests"]) == 7
    assert "Consigne de l'automaticien : le message d'erreur a changé" in d["texte"]
    assert f"- {INVALIDE} · PASS le " in d["texte"] and "jamais exécuté en run réel" in d["texte"]
    assert "run_tests" in d["texte"] and "un dry run ne lance aucun keyword" in d["texte"] and d["attendus"] == ["run_tests", "studio_soumettre_revue"]
    with pytest.raises(ValueError, match="Aucun test"):
        maintenance.demande_maintenance(["tests/inconnu.robot::x"])


def test_outil_run_tests_garde_la_donnee_reelle(demo):
    from atelier.adapters import facade
    from atelier.generation import studio

    studio.entrer_en_revue(SUITE, "cursor")
    r = facade.run_tests([INVALIDE], output_dir="results/mcp")
    assert r["resultat"]["passes"] == 1 and r["revue"]["verification"]
    f = demo / SUITE
    f.write_text(f.read_text("utf-8").replace("[Tags]    DEMO-307    smoke", "[Tags]    DEMO-307    smoke    consomme_donnee"), "utf-8")
    with pytest.raises(PermissionError):
        facade.run_tests([f"{SUITE}::Déconnexion"], output_dir="results/mcp")


def test_routes_web_verifier_passe_par_la_file_d_execution(demo, monkeypatch, tmp_path):
    """« Vérifier » met un run de tests précis dans la file de l'Execution Center ; le job de la file l'exécute (moteur,
    --test). Le job est intercepté puis exécuté ici par la même fonction que la file : le fil de la file, partagé entre
    les tests, rendait ce test instable."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from web_app_loader import charger_app_web, module_web

    from atelier.execution import centre
    from atelier.generation import studio

    monkeypatch.setattr(module_web(), "CONFIG_PATH", tmp_path / "atelier.json")
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    c.get("/plateforme")
    jobs = []
    monkeypatch.setattr(centre.FILE, "ajouter", lambda params, priorite="Normal", run_id="", campagne="", nom="", retry=False:
                        jobs.append({"id": run_id, "params": params, "contexte": {}, "campagne": campagne, "priorite": priorite,
                                     "retry": retry}) or jobs[-1])
    studio.entrer_en_revue(SUITE, "cursor")
    assert c.get("/api/tests-automatises").json()["compte"]["À valider"] == 7
    r = c.post("/api/tests-automatises/verifier", json={"tests": [INVALIDE]}).json()
    assert r["revue"]["verification"], r
    job = jobs[0]
    assert job["params"]["tests"] == [INVALIDE] and job["params"]["target"] == SUITE and job["priorite"] == "High"
    bilans = []
    monkeypatch.setattr(module_web(), "emit", lambda ev: bilans.append(ev["bilan"]) if ev.get("type") == "run_bilan" else None)
    module_web()._executer_job(job)  # ce que fait la file : moteur avec tests (l'outil MCP run_robot n'a pas ce paramètre)
    assert bilans[0]["resultat"]["passes"] == 1 and bilans[0]["resultat"]["echecs"] == 0, bilans
    m = c.post("/api/tests-automatises/maintenance", json={"tests": [INVALIDE], "consigne": "x"}).json()
    assert m["titre"] == "Maintenance : 1 test(s)"
    assert c.post("/api/tests-automatises/inconnue", json={"tests": [INVALIDE]}).status_code == 404
    assert c.post("/api/tests-automatises/valider", json={"tests": []}).status_code == 400


def test_run_reel_reconnu_meme_quand_les_keywords_ecrivent_au_journal(projet):
    """Browser écrit des messages dans le journal de chaque keyword : un keyword exécuté reste un keyword exécuté
    (régression : le test de Cursor, réellement passé, était compté comme un dry run)."""
    from atelier.execution.robot import derniers_resultats, run_robot

    (projet / "tests").mkdir(exist_ok=True)
    (projet / "tests" / "t.robot").write_text("*** Test Cases ***\nT\n    Log    bonjour\n    Should Be Equal    1    1\n", "utf-8")
    run_robot("tests/t.robot", dry_run=True, output_dir="results/dry", xray_mode="aucun")
    assert derniers_resultats("results")["tests/t.robot::T"]["reel"] is False
    assert "tests/t.robot::T" not in derniers_resultats("results", reels=True)
    run_robot("tests/t.robot", output_dir="results/reel", xray_mode="aucun")
    assert derniers_resultats("results", reels=True)["tests/t.robot::T"]["statut"] == "PASS"


def test_controle_donnees_ignore_un_test_de_consultation(projet):
    """Contrôle « donnees » de la revue : un test qui ne lit aucune donnée (consultation) n'a pas besoin de jeu ; un test
    qui lit ${JDD} sans jeu associé reste signalé. « Initialiser Le Test » pose &{JDD} : ce n'est pas une lecture."""
    from atelier.generation import studio

    (projet / "tests").mkdir(exist_ok=True)
    (projet / "resources").mkdir(exist_ok=True)
    (projet / "resources" / "socle.resource").write_text(
        "*** Keywords ***\nInitialiser Le Test\n    [Documentation]    x\n    [Arguments]    &{jdd}\n    Set Test Variable    &{JDD}    &{jdd}\n\n"
        "je consulte la page\n    [Documentation]    x\n    Log    page\n\nje saisis le nom\n    [Documentation]    x\n    Log    ${JDD}[nom]\n", "utf-8")
    (projet / "tests" / "consultation.robot").write_text(
        "*** Settings ***\nResource    ../resources/socle.resource\n\n*** Test Cases ***\nConsulter\n    Initialiser Le Test\n    je consulte la page\n", "utf-8")
    (projet / "tests" / "saisie.robot").write_text(
        "*** Settings ***\nResource    ../resources/socle.resource\n\n*** Test Cases ***\nSaisir\n    Initialiser Le Test\n    je saisis le nom\n", "utf-8")
    donnees = lambda f: next(c for c in studio.controles_script(f) if c["code"] == "donnees")  # noqa: E731
    assert donnees("tests/consultation.robot")["gravite"] == "ok"
    assert donnees("tests/saisie.robot") == {"code": "donnees", "gravite": "basse", "message": "Utilise ${JDD} sans jeu de données : Saisir"}


def test_suivi_des_verifications_en_cours_en_file_et_terminees(demo, monkeypatch):
    """Tests automatisés › Exécutions : la vérification en cours (avec ses tests), celles en file, et les dernières
    terminées avec l'erreur d'un run qui n'a pas pu se lancer ; les autres runs (campagnes, suites) n'y figurent pas."""
    from atelier.execution import centre, historique
    from atelier.generation import maintenance

    historique.enregistrer("RUN-20261123-100000", {"target": SUITE, "tests": [INVALIDE]},
                           {"statut": "erreur", "erreur": "mapping values are not allowed in this context"},
                           "2026-11-23T10:00:00", "2026-11-23T10:00:01")
    historique.enregistrer("RUN-20261123-100100", {"target": SUITE}, {"resultat": {"passes": 2, "echecs": 0}},
                           "2026-11-23T10:01:00", "2026-11-23T10:02:00")  # run de suite : hors de ce suivi
    file = centre.FileExecution()
    file.en_cours = {"id": "RUN-20261123-110000", "nom": maintenance.NOM_JOB_VERIFICATION, "etat": "Running",
                     "entre_le": "2026-11-23T11:00:00", "params": {"tests": [INCONNU]}}
    file._tas = [(0, 0, {"id": "RUN-20261123-110100", "nom": maintenance.NOM_JOB_VERIFICATION, "entre_le": "2026-11-23T11:01:00",
                         "params": {}}),
                 (1, 1, {"id": "RUN-20261123-110200", "nom": "Campagne", "entre_le": "2026-11-23T11:02:00", "params": {}})]
    monkeypatch.setattr(centre, "FILE", file)

    e = maintenance.executions_verification()
    assert e["en_cours"]["id"] == "RUN-20261123-110000" and e["en_cours"]["tests"] == [INCONNU]
    assert [j["id"] for j in e["attente"]] == ["RUN-20261123-110100"]
    assert [r["id"] for r in e["recents"]] == ["RUN-20261123-100000"]
    assert e["recents"][0]["statut"] == "erreur" and "mapping values" in e["recents"][0]["erreur"]
    assert e["recents"][0]["nb_tests"] == 1
