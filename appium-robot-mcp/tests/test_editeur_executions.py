"""Éditeur de test, historique et arrêt des exécutions, routes de construction BDD (vrais runs Robot)."""
from __future__ import annotations

import json
import shutil
import time

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from conftest import FIXTURES  # noqa: E402
from web_app_loader import charger_app_web, module_web  # noqa: E402


@pytest.fixture
def depot(projet):
    shutil.copytree(FIXTURES / "projet_robot", projet, dirs_exist_ok=True)
    (projet / "patrimoine").mkdir()
    shutil.copy(FIXTURES / "xray" / "patrimoine.json", projet / "patrimoine" / "xray.json")
    return projet


@pytest.fixture
def client(depot, monkeypatch, tmp_path):
    monkeypatch.setattr(module_web(), "CONFIG_PATH", tmp_path / "atelier.json")
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    c.get("/plateforme")
    return c


def _attendre_fin(client, delai=60):
    mod = module_web()
    fin = time.time() + delai
    while mod.state["run"] and mod.state["run"].is_alive() and time.time() < fin:
        time.sleep(0.2)


# --------------------------------------------------------------------------- éditeur
def test_arbre_et_enregistrement(depot):
    from atelier.generation import editeur

    a = editeur.arbre()
    noms = json.dumps(a)
    assert "virement.robot" in noms and "recette.yaml" in noms and "patrimoine" in noms
    chemin = "tests/virement.robot"
    lu = (depot / chemin).read_text("utf-8")
    r = editeur.enregistrer(chemin, lu + "\n# commentaire\n", version_lue=lu)
    assert r["lignes_ajoutees"] == 2 and r["lignes_retirees"] == 0
    with pytest.raises(FileExistsError):  # modifié sur le disque depuis l'ouverture
        editeur.enregistrer(chemin, "x", version_lue=lu)
    with pytest.raises(ValueError):
        editeur.enregistrer("../dehors.robot", "x")
    with pytest.raises(ValueError):
        editeur.enregistrer("tests/binaire.exe", "x")
    assert editeur.historique(chemin)[0]["op"] == "edition_fichier"


def test_lint_syntaxe_et_conventions():
    from atelier.generation import editeur

    r = editeur.lint("*** Test Cases ***\nT\n    [Tagz]    x\n    FOR    ${i}    IN    1\n        Log    x\n")
    msgs = [p["message"] for p in r["problemes"]]
    assert not r["ok"]
    assert any("Tagz" in m for m in msgs) and any("END" in m for m in msgs)
    assert any("clé Xray" in m for m in msgs) and any("INITIALISATION" in m for m in msgs)
    ok = editeur.lint("*** Test Cases ***\nT\n    [Tags]    DEMO-1\n    Initialiser Le Test    &{JDD_X}\n")
    assert ok["ok"] and ok["problemes"] == []


def test_proprietes_d_une_suite(depot):
    from atelier.generation import editeur

    p = editeur.proprietes("tests/virement.robot")
    t = {x["nom"]: x for x in p["tests"]}["Virement Nominal"]
    assert t["xray"][0]["cle"] == "DEMO-1" and t["xray"][0]["criticite"] == "Haute" and t["xray"][0]["plans"] == ["DEMO-50"]
    assert t["jdd"] == ["VIREMENT_STANDARD"] and t["requetes"] == ["compte_avec_solde"]
    assert "Cliquer Sur" in t["keywords"]
    assert {o["nom"] for o in t["autres_tests_impactes"]} == {"Virement Montant Nul", "Connexion Standard"}
    assert p["bibliotheques"] == []


def test_reutilisation(depot):
    from atelier.generation import editeur

    r = editeur.reutilisation()
    k = {x["nom"]: x["appels"] for x in r["keywords"]}
    assert k["Se Connecter"] == 3 and k["Cliquer Sur"] == 1
    assert len(r["locators"]) == 8 and "resources/socle/commun.resource" in r["resources"]


def test_robocop_absent_signale(depot, monkeypatch):
    import builtins

    from atelier.generation import editeur

    monkeypatch.setattr(editeur.shutil, "which", lambda n: None)
    vrai = builtins.__import__
    monkeypatch.setattr(builtins, "__import__", lambda n, *a, **k: (_ for _ in ()).throw(ImportError()) if n == "robocop" else vrai(n, *a, **k))
    assert editeur.robocop("tests/virement.robot")["disponible"] is False


# --------------------------------------------------------------------------- exécutions
def test_historique_et_detail_d_un_test(client, depot):
    (depot / "tests" / "simple.robot").write_text("*** Test Cases ***\nNominal\n    [Tags]    DEMO-1\n    Log    ok\n"
                                                  "Echec\n    [Tags]    DEMO-2\n    Log    avant\n    Should Be Equal    1    2\n",
                                                  "utf-8")
    r = client.post("/api/run", json={"target": "tests/simple.robot"}).json()
    run_id = r["run_id"]
    _attendre_fin(client)
    runs = client.get("/api/executions").json()
    assert runs[0]["id"] == run_id and runs[0]["statut"] == "échec" and runs[0]["passes"] == 1
    d = client.get(f"/api/executions/{run_id}").json()
    assert [t["statut"] for t in d["tests"]] == ["PASS", "FAIL"] and d["tests"][1]["cles_xray"] == ["DEMO-2"]
    t = client.get(f"/api/executions/{run_id}/test", params={"id": d["tests"][1]["id"]}).json()
    assert [e["nom"] for e in t["etapes"]] == ["Log", "Should Be Equal"] and t["etape_en_echec"] == 1
    assert any("1 != 2" in x["message"] for x in t["logs"])
    assert (depot / "results" / "runs" / run_id / "output.xml").exists()
    assert client.get("/api/executions/../etc").status_code in (400, 404)


def test_arret_d_un_run(client, depot):
    (depot / "tests" / "long.robot").write_text("*** Test Cases ***\nLong\n    Sleep    30s\nApres\n    Log    x\n", "utf-8")
    run_id = client.post("/api/run", json={"target": "tests/long.robot"}).json()["run_id"]
    from atelier.execution import robot

    fin = time.time() + 20
    while robot.EN_COURS["proc"] is None and time.time() < fin:
        time.sleep(0.1)
    time.sleep(1.5)
    debut = time.time()
    assert "Arrêt demandé" in client.post("/api/run/arreter").json()["message"]
    _attendre_fin(client)
    assert time.time() - debut < 20
    assert client.get(f"/api/executions/{run_id}").json()["bilan"]["arrete"] is True
    assert client.post("/api/run/arreter").json()["message"] == "Aucun run en cours."


def test_rapport_robot_tronque_reste_consultable(depot):
    """Run arrêté, tué ou planté : output.xml vide ou coupé. Le détail de l'exécution reste lisible (aucun test listé)."""
    from atelier.execution import historique

    historique.enregistrer("RUN-20260101-000000", {"target": "tests/x.robot"}, {"arrete": True}, "2026-01-01T00:00:00", "2026-01-01T00:00:05")
    (historique.dossier("RUN-20260101-000000") / "output.xml").write_text("", "utf-8")
    d = historique.detail("RUN-20260101-000000")
    assert d["bilan"]["arrete"] is True and d["tests"] == []
    (historique.dossier("RUN-20260101-000000") / "output.xml").write_text('<?xml version="1.0"?><robot><suite name="x"><test name="coup', "utf-8")
    assert historique.detail("RUN-20260101-000000")["tests"] == []
    with pytest.raises(KeyError, match="illisible"):
        historique.detail_test("RUN-20260101-000000", "s1-t1")


def test_chemins_du_projet_avec_des_barres_obliques(depot):
    """Chemins relatifs au projet : toujours « / », sous Windows comme sous Linux (clés enregistrées et comparées)."""
    from atelier.domain import projet

    (depot / "tests" / "sous").mkdir(exist_ok=True)
    (depot / "tests" / "sous" / "z.robot").write_text("*** Test Cases ***\nZ\n    Log    z\n", "utf-8")
    assert "tests/sous/z.robot" in projet.lister_fichiers("**/*.robot")
    assert not any("\\" in c for c in projet.lister_fichiers("**/*"))


def test_contexte(client):
    c = client.get("/api/contexte").json()
    assert c["projet"] == "projet" and c["environnements"] == ["recette"] and "xray" in c


# --------------------------------------------------------------------------- construction BDD (routes)
def test_parcours_bdd(client, depot):
    r = client.post("/api/bdd", json={"cle": "DEMO-9", "titre": "Virement SEPA", "jdd": "VIREMENT_STANDARD"}).json()
    sid = r["scenario"]["scenarios"][0]["id"]
    for mot, texte in (("Étant donné", "Se Connecter"), ("Quand", "Saisir Le Montant"), ("Alors", "le récapitulatif s'affiche")):
        r = client.post("/api/bdd/DEMO-9/operation", json={"op": "ajouter_etape", "scenario": sid, "mot": mot, "texte": texte}).json()
    assert r["statistiques"]["etapes"] == 3 and "Alors le récapitulatif s'affiche" in r["gherkin"]
    e1 = r["scenario"]["scenarios"][0]["etapes"][1]["id"]
    r = client.post("/api/bdd/DEMO-9/operation", json={"op": "ajouter_branche", "depuis": e1, "nom": "Solde insuffisant",
                                                       "type": "negatif", "etapes": [{"mot": "Alors", "texte": "une erreur s'affiche"}]}).json()
    assert r["statistiques"]["branches"] == 1
    assert client.post("/api/bdd/DEMO-9/operation", json={"op": "inconnue"}).status_code == 400
    g = client.post("/api/bdd/DEMO-9/generer", json={}).json()
    assert "ecrit" not in g and g["keywords_a_creer"] == ["le récapitulatif s'affiche", "une erreur s'affiche"]
    g = client.post("/api/bdd/DEMO-9/generer", json={"ecrire": True}).json()
    assert (depot / g["ecrit"]).exists()
    assert client.post("/api/bdd/DEMO-9/generer", json={"ecrire": True}).status_code == 400  # pas d'écrasement implicite
    r = client.post("/api/bdd/DEMO-9/operation", json={"op": "valider"}).json()
    assert r["scenario"]["statut"] == "validé"
    assert [x["cle"] for x in client.get("/api/bdd").json()] == ["DEMO-9"]
    ia = client.post("/api/bdd/DEMO-9/ia", json={}).json()
    assert ia["disponible"] is False and "controles" in ia


def test_etape_enrichie_avec_ecran_de_reference(client, depot):
    import server
    from atelier.discovery import carte
    from conftest import lire_fixture

    carte.creer_app("Banque Démo", ["android"])
    obs = carte.observer(server._parse_elements(lire_fixture("hierarchies", "android_classique.xml"), "android"), "android")
    carte.renommer(obs["id"], "virement_saisie")
    (depot / "tests" / "ref.robot").write_text(
        "*** Test Cases ***\nValider\n    [Tags]    DEMO-1\n    Should Be Equal    id=com.exemple.banque:id/valider    autre\n", "utf-8")
    run_id = client.post("/api/run", json={"target": "tests/ref.robot", "variables": {"PLATFORM": "android"}}).json()["run_id"]
    _attendre_fin(client)
    tid = client.get(f"/api/executions/{run_id}").json()["tests"][0]["id"]
    t = client.get(f"/api/executions/{run_id}/test", params={"id": tid}).json()
    e = t["etapes"][0]
    assert e["locator"] == "id=com.exemple.banque:id/valider" and e["type_locator"] == "id"
    assert e["strategie"] == "id (resource-id)" and e["bibliotheque"] == "BuiltIn"
    assert e["ecran_reference"]["ecran"] == "virement_saisie" and e["ecran_reference"]["plateforme"] == "android"
    assert t["fichier"] == "tests/ref.robot" and t["ligne"] == 2 and t["plateforme"] == "android"


def test_suites_capture_et_utilisateur(client, depot):
    suites = client.get("/api/depot/suites").json()
    assert {s["fichier"] for s in suites} == {"tests/connexion.robot", "tests/virement.robot"}
    assert next(s for s in suites if s["fichier"] == "tests/virement.robot")["tests"] == 2
    assert client.post("/api/resultats/capturer", json={}).status_code == 400   # aucun device ni navigateur
    assert "utilisateur" in client.get("/api/contexte").json()
