"""Execution Center (file, contexte figé, campagnes, contrôle préalable) et Automation Studio
(référentiels, revue technique des scripts, mapping BDD)."""
import shutil
import threading
import time
from pathlib import Path

import pytest

from tests.conftest import pointer_projet

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"


@pytest.fixture
def demo(tmp_path, monkeypatch):
    d = tmp_path / "demo"
    shutil.copytree(DEMO, d, ignore=shutil.ignore_patterns("results", "connaissance", "studio", "executions"))
    pointer_projet(d, monkeypatch)
    return d


# --------------------------------------------------------------------------- file d'attente
def test_file_priorites_et_contexte_fige(demo):
    from atelier.execution.centre import FileExecution

    f = FileExecution()
    ordre, bloque = [], threading.Event()

    def executer(job):
        if job["id"] == "A":
            bloque.wait(5)  # le runner est occupé pendant que la file se remplit
        ordre.append(job["id"])
    f.executer = executer
    a = f.ajouter({"target": "tests"}, "Low", "A")
    time.sleep(0.2)
    f.ajouter({"target": "tests"}, "Low", "B")
    f.ajouter({"target": "tests"}, "Critical", "C")
    f.ajouter({"target": "tests"}, "Normal", "D")
    assert [j["id"] for j in f.attente()] == ["C", "D", "B"]
    assert f.annuler("D") and not f.annuler("A")  # A a déjà démarré
    bloque.set()
    fin = time.time() + 5
    while f.en_cours is not None and time.time() < fin:
        time.sleep(0.05)
    assert ordre == ["A", "C", "B"]
    assert a["contexte"]["projet"] == "demo" and a["contexte"]["application"] == "Banque Démo Web"
    with pytest.raises(ValueError):
        f.ajouter({}, "Urgente", "E")


def test_campagne_et_parametres(demo):
    from atelier.execution import centre

    with pytest.raises(ValueError):
        centre.enregistrer_campagne({"nom": "x", "plateformes": ["symbian"]})
    with pytest.raises(ValueError):
        centre.enregistrer_campagne({"nom": "x", "plateformes": ["web"], "cible": "../hors"})
    l = centre.enregistrer_campagne({"nom": "Smoke Connexion", "type": "Smoke", "plateformes": ["web"], "environnement": "recette",
                                     "tags": ["smoke"], "retry": True, "priorite": "High"})
    c = l[0]
    assert c["id"].startswith("CAMP-") and c["taux_reussite"] is None
    p = centre.params_campagne(c, "web")
    assert p == {"target": "tests", "variables": {"PLATFORM": "web"}, "dry_run": False, "include_tags": ["smoke"], "retry": True, "jdd_env": "recette"}


def test_controle_prealable(demo):
    from atelier.execution import centre

    ids = [t["id"] for t in centre.referentiel()]
    assert len(ids) == 7
    v = centre.verifier(ids[:1] + ["tests/absent.robot::X"], "android", "")
    ok, absent = v["tests"]
    assert not absent["executable"]
    codes = {c["code"]: c for c in ok["controles"]}
    assert not codes["plateforme"]["ok"]  # test web demandé sur Android
    assert not codes["donnees"]["ok"]  # JDD requis sans environnement
    assert codes["revue"]["ok"] is True  # patrimoine existant, jamais entré en revue : non bloqué


def test_revue_bloquante_avant_execution(demo, monkeypatch):
    """Invariant : un script généré par l'atelier ne s'exécute qu'approuvé (dry-run libre, dérogation journalisée)."""
    from atelier.domain import projet
    from atelier.execution import centre
    from atelier.generation import studio

    monkeypatch.delenv("ATELIER_REVUE_EXECUTION", raising=False)
    tid = centre.referentiel()[0]["id"]
    fichier = tid.split("::")[0]
    assert centre.controle_revue("tests")["non_valides"] == []
    studio.entrer_en_revue(fichier, "builder")
    codes = {c["code"]: c for c in centre.verifier([tid], "web", "recette")["tests"][0]["controles"]}
    assert codes["revue"]["ok"] is False and codes["revue"]["bloquant"] is True
    with pytest.raises(PermissionError, match="Revue requise"):
        centre.controle_revue("tests")
    assert centre.controle_revue("tests", dry_run=True)["non_valides"] == [fichier]
    with pytest.raises(PermissionError):
        centre.controle_revue("tests", derogation="court")
    assert centre.controle_revue("tests", derogation="correctif urgent validé par le PO")["derogation"] is True
    assert "correctif urgent" in (projet.PROJECT_DIR / "executions" / "derogations_revue.jsonl").read_text("utf-8")
    monkeypatch.setenv("ATELIER_REVUE_EXECUTION", "avertissement")
    assert centre.controle_revue("tests")["derogation"] is False


# --------------------------------------------------------------------------- Automation Studio
def test_referentiels(demo):
    from atelier.generation import studio

    assert studio.fiabilite("id=valider") == ("id", "Stable")
    assert studio.fiabilite("//android.widget.Button[2]")[1] == "Fragile"
    assert studio.fiabilite("text=\"Valider\"")[1] == "Fragile"
    assert studio.fiabilite("css=.carte > .titre")[1] == "Reliable"
    locs = {l["id"]: l for l in studio.locators()}
    assert locs["connexion.bouton_connexion@web"]["utilisations"] == 2 and locs["connexion.bouton_connexion@web"]["etat"] == "Stable"
    kws = {k["nom"]: k for k in studio.keywords()}
    assert kws["Initialiser Le Test"]["utilisations"] == 7 and not kws["Initialiser Le Test"]["inutilise"]
    assert [p["ecran"] for p in studio.page_objects()] == ["accueil", "connexion"]


def test_locator_obsolete_si_absent_de_la_carte(demo):
    from atelier.generation import studio

    f = demo / "resources" / "locators" / "connexion.resource"
    f.write_text(f.read_text("utf-8").replace("message_erreur=id=message_erreur", "message_erreur=id=ancien_message"), "utf-8")
    assert {l["id"]: l for l in studio.locators()}["connexion.message_erreur@web"]["etat"] == "Obsolete"


def test_revue_script_et_retour_en_revue_si_modifie(demo):
    from atelier.generation import studio

    f = "tests/connexion.robot"
    assert studio.revue_script(f)["statut"] == "Generated"
    with pytest.raises(ValueError):
        studio.transition_script(f, "approuver")
    studio.transition_script(f, "soumettre")
    studio.transition_script(f, "approuver")
    r = studio.transition_script(f, "publier", "OK pour la TNR")
    assert r["statut"] == "Published" and all(c["gravite"] == "ok" for c in r["controles"])
    p = demo / f
    p.write_text(p.read_text("utf-8") + "\n", "utf-8")  # toute modification après validation renvoie en revue
    r = studio.revue_script(f)
    assert r["statut"] == "Technical Review" and r["modifie_depuis_validation"]


def test_secret_en_clair_bloque_l_approbation(demo):
    from atelier.generation import studio

    p = demo / "tests" / "connexion.robot"
    p.write_text(p.read_text("utf-8").replace("Documentation", "Documentation    password=Secret123  "), "utf-8")
    studio.transition_script("tests/connexion.robot", "soumettre")
    with pytest.raises(ValueError, match="sensible"):
        studio.transition_script("tests/connexion.robot", "approuver")


def test_mapping_bdd(demo):
    from atelier.generation import studio

    m = studio.mapping_bdd("DEMO-301")
    assert m["a_creer"] == 0
    e = m["scenarios"][0]["etapes"]
    assert e[1]["keyword"] == "je me connecte avec le jeu de données"
    assert [x["id"] for x in e[1]["locators"]] == ["connexion.bouton_connexion", "connexion.champ_identifiant", "connexion.champ_mot_de_passe"]
    assert e[1]["donnees"] == ["identifiant", "mot_de_passe"] and e[2]["assertion"]


def test_retry_conserve_les_tentatives_et_detecte_l_instable(demo):
    """Un test qui échoue puis réussit : 2 tentatives conservées, résultat fusionné, test déclaré instable."""
    from atelier.execution import centre
    from atelier.execution.robot import run_robot

    (demo / "tests" / "instable.robot").write_text(
        "*** Settings ***\nLibrary    OperatingSystem\n\n*** Test Cases ***\nInstable\n    [Tags]    DEMO-999\n"
        "    ${existe}=    Run Keyword And Return Status    File Should Exist    ${CURDIR}/../.marqueur\n"
        "    Create File    ${CURDIR}/../.marqueur    x\n    Should Be True    ${existe}\n", "utf-8")
    params = {"target": "tests/instable.robot", "output_dir": "results/runs/RUN-20261114-110000", "xray_mode": "aucun"}
    b = centre.executer_avec_retry(run_robot, params, retry=True)
    assert [t["resultat"]["echecs"] for t in b["tentatives"]] == [1, 0]
    assert b["instables"] == ["Instable"] and b["resultat"]["echecs"] == 0
    d = demo / "results" / "runs" / "RUN-20261114-110000"
    assert (d / "tentative-1" / "output.xml").exists() and (d / "tentative-2" / "output.xml").exists()
    # sans retry : le premier échec reste un échec
    (demo / ".marqueur").unlink()
    b = centre.executer_avec_retry(run_robot, {**params, "output_dir": "results/runs/RUN-20261114-110001"}, retry=False)
    assert b["resultat"]["echecs"] == 1 and "tentatives" not in b


def test_rejeu_sans_ecraser_le_run_origine(demo, tmp_path):
    from atelier.domain import projet
    from atelier.execution import centre

    orig = projet.PROJECT_DIR / "results" / "runs" / "R1"
    orig.mkdir(parents=True)
    (orig / "output.xml").write_text("<robot/>", "utf-8")
    vus = {}

    def faux_run(**p):
        vus.update(p)
        return {"resultat": {"echecs": 0}}

    centre.executer_avec_retry(faux_run, {"target": "tests", "relancer_echecs": True, "output_dir": "results/runs/R2",
                                          "source_echecs": "results/runs/R1"})
    assert vus["output_dir"] == "results/runs/R2" and "source_echecs" not in vus
    assert (projet.PROJECT_DIR / "results/runs/R2/output.xml").read_text("utf-8") == "<robot/>"
    assert (orig / "output.xml").read_text("utf-8") == "<robot/>"


def test_etat_xray_abandons_non_synced(demo):
    from atelier.domain import projet
    from atelier.execution import centre
    from atelier.execution.journal_xray import Journal

    d = projet.PROJECT_DIR / "results" / "runs" / "RUN-20261114-120000" / "xray" / "a"
    d.mkdir(parents=True)
    j = Journal(d)
    ev = j.ajouter("R3", "test_fin", "T1", cle_xray="DEMO-1")
    j.marquer(ev["cle"], "ignore", "ticket cible de type Test")
    e = centre.etat_xray("RUN-20261114-120000")
    assert e["statut"] == "Failed" and e["abandonnes"] == 1 and "Test" in e["erreurs_definitives"][0]
