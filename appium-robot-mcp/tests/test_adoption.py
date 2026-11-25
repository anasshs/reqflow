"""Adopter un dépôt Robot existant : les tests Gherkin deviennent des scénarios BDD (clé Xray, jeu de données), les
suites deviennent des parcours (techniques écartées d'office), et un run cartographié donne leurs écrans aux parcours."""
import pytest

SUITE = """*** Settings ***
Documentation    Consulter ses comptes — suite historique de l'équipe
Resource    ../../resources/pages/compte.resource

*** Test Cases ***
Consulter le solde
    [Tags]    DEMO-101    smoke
    [Documentation]    Le solde du compte courant s'affiche
    Initialiser Le Test    &{JDD_CLIENT_A}
    Given the customer is logged in
    When he opens his account
    Then the balance is displayed

Mot de passe technique
    [Tags]    DEMO-102
    Ouvrir L'Application
"""
LOGIN = """*** Test Cases ***
Connexion
    [Tags]    DEMO-103
    Étant donné que l'application est ouverte
    Quand je me connecte
    Alors le tableau de bord s'affiche
"""


@pytest.fixture
def depot(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.domain import projet
    from atelier.execution import orchestrateur

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    monkeypatch.setenv("ATELIER_FLUX", "simple")
    monkeypatch.setattr(orchestrateur, "demarrer", lambda: None)
    carte.creer_app("Banque Démo", ["android"])
    d = tmp_path / "tests" / "banque_demo"
    (d / "comptes").mkdir(parents=True)
    (d / "login").mkdir(parents=True)
    (d / "comptes" / "consulter_comptes.robot").write_text(SUITE, "utf-8")
    (d / "login" / "connexion.robot").write_text(LOGIN, "utf-8")
    return tmp_path


def test_analyse_import_parcours_et_ecrans(depot):
    from atelier.discovery import carte, parcours_utilisateur as pu
    from atelier.generation import adoption, bdd, kanban

    a = adoption.analyser()
    assert a["tests"] == 3 and a["gherkin"] == 2 and a["avec_xray"] == 3
    par = {s["suite"].split("/")[-1]: s for s in a["suites"]}
    assert par["consulter_comptes.robot"]["nom"] == "Consulter ses comptes" and par["consulter_comptes.robot"]["type"] == "parcours"
    assert par["connexion.robot"]["type"] == "technique"                                       # suite de connexion : décochée d'office
    r = adoption.importer_scenarios()
    assert sorted(r["crees"]) == ["DEMO-101", "DEMO-103"] and not r["refus"]                   # le test sans Gherkin n'est pas repris
    m = bdd.charger("DEMO-101")
    assert m["jdd"] == "CLIENT_A" and m["statut"] == "validé" and m["origine"]["type"] == "depot"
    texte = bdd.serialiser(m)
    assert "Given the customer is logged in" in texte and "Then the balance is displayed" in texte and "@smoke" in texte
    assert "Quand je me connecte" in bdd.serialiser(bdd.charger("DEMO-103"))                  # Gherkin français gardé
    t = next(x for x in kanban.tableau()["tickets"] if x["id"] == "DEMO-101")
    assert t["xray"] == "DEMO-101" and t["tests"] == ["tests/banque_demo/comptes/consulter_comptes.robot::Consulter le solde"]
    assert adoption.importer_scenarios()["crees"] == []                                         # rien n'est importé deux fois
    assert all(x["deja"] for s in adoption.analyser()["suites"] for x in s["tests"] if x["gherkin"])
    c = adoption.creer_parcours([{"suite": s["suite"], "nom": s["nom"], "garder": s["type"] == "parcours"} for s in a["suites"]])
    assert len(c["parcours_crees"]) == 1 and c["scenarios_rattaches"] == 1
    pid = c["parcours_crees"][0]
    assert bdd.charger("DEMO-101")["parcours"] == pid and not bdd.charger("DEMO-103").get("parcours")
    assert pid in kanban.tableau()["tickets"][0]["sujets"] or any(pid in x["sujets"] for x in kanban.tableau()["tickets"] if x["id"] == "DEMO-101")
    # run cartographié : la carte retient les tests Xray qui passent par chaque écran
    for nom, tests in (("accueil", ["DEMO-101", "DEMO-103"]), ("compte", ["DEMO-101"]), ("autre", ["DEMO-999"])):
        e = carte.observer([{"key": f"titre_{nom}", "type": "texte", "libelle": nom, "locators": [f"id=titre_{nom}"]}], "android")
        e = carte.ecran(e["id"])
        e["utilise_par"] = tests
        carte._save_ecran(e)
    adoption.ecrans_des_parcours()
    assert len(pu.obtenir(pid)["ecrans"]) == 2                                                # accueil et compte, pas « autre »


def test_apercu_d_un_dossier_sans_l_activer(depot, tmp_path_factory):
    from atelier.generation import adoption

    autre = tmp_path_factory.mktemp("autre")
    a = adoption.apercu(depot)
    assert a["suites"] == 2 and a["tests"] == 3 and a["gherkin"] == 2 and a["avec_xray"] == 3 and a["a_adopter"]
    assert adoption.apercu(autre)["a_adopter"] is False                                       # dossier sans tests Robot


def test_adoption_n_ecrase_pas_la_connaissance(depot):
    from atelier.discovery import carte, parcours_utilisateur as pu
    from atelier.generation import adoption, bdd

    adoption.importer_scenarios()
    p0 = pu.enregistrer("", {"nom": "Parcours déjà conçu", "objectif": "x"})["id"]
    m = bdd.charger("DEMO-101")
    m["parcours"] = p0
    bdd.sauver(m)
    adoption.creer_parcours([{"suite": s["suite"], "nom": s["nom"], "garder": True} for s in adoption.analyser()["suites"]])
    assert bdd.charger("DEMO-101")["parcours"] == p0                                           # rattachement existant gardé
    # locators : celui que la carte connaissait déjà reste le premier
    res = depot / "resources" / "pages"
    res.mkdir(parents=True)
    (res / "compte.resource").write_text("*** Variables ***\n${BTN_SOLDE_ANDROID}    id=demo:id/importe\n", "utf-8")
    adoption.importer_locators()
    e = carte.ecran("compte")
    e["elements"]["btn_solde_android"]["locators"]["android"] = ["id=demo:id/connu"]
    carte._save_ecran(e)
    adoption.importer_locators()
    assert carte.ecran("compte")["elements"]["btn_solde_android"]["locators"]["android"] == ["id=demo:id/connu", "id=demo:id/importe"]


def test_changer_de_depot_reprend_la_connaissance(tmp_path, monkeypatch):
    from atelier.domain import projet, projets

    monkeypatch.setenv("ATELIER_PROJETS", str(tmp_path / "projets.json"))
    ancien, nouveau = tmp_path / "ancien", tmp_path / "nouveau"
    (ancien / "app_map" / "demo").mkdir(parents=True)
    (ancien / "app_map" / "demo" / "ecrans.json").write_text('{"a": 1}', "utf-8")
    (ancien / "parcours").mkdir()
    (ancien / "parcours" / "p1.yaml").write_text("nom: Virement", "utf-8")
    (ancien / "tests").mkdir()
    (ancien / "tests" / "vieux.robot").write_text("*** Test Cases ***", "utf-8")
    (nouveau / "parcours").mkdir(parents=True)
    (nouveau / "parcours" / "p1.yaml").write_text("nom: Autre", "utf-8")              # version du dépôt, différente
    monkeypatch.setattr(projet, "PROJECT_DIR", ancien.resolve())
    pid = projets.enregistrer({"nom": "Banque Démo", "dossier": str(ancien)})["projets"][0]["id"]
    r = projets.enregistrer({"id": pid, "nom": "Banque Démo", "dossier": str(nouveau)})
    b = r["reprise"]
    assert b["copies"] == 2 and b["conflits"] == ["parcours/p1.yaml"]
    assert (nouveau / "app_map" / "demo" / "ecrans.json").read_text("utf-8") == '{"a": 1}'
    assert (nouveau / "parcours" / "p1.yaml").read_text("utf-8") == "nom: Virement"            # la connaissance l'emporte
    assert [f.read_text("utf-8") for f in (nouveau / "parcours").glob("p1.yaml.conflit-depot-*")] == ["nom: Autre"]
    assert not (nouveau / "tests").exists()                                                     # scripts du dépôt : pas touchés
    assert (ancien / "parcours" / "p1.yaml").exists()                                          # ancien dossier intact
    assert projet.PROJECT_DIR == nouveau.resolve() and r["actif"] == pid              # projet actif : suit son dossier
    import pytest as _p
    with _p.raises(PermissionError):
        projets.enregistrer({"id": pid, "nom": "Banque Démo", "dossier": str(ancien)}, occupe="run en cours")
