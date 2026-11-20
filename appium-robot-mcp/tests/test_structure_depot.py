"""Structure du dépôt : ce qui est généré (par l'atelier ou par Cursor) est rangé comme l'équipe range déjà ses fichiers.
Dépôt fictif : tests/, resources/locators/, resources/keywords/, resources/pages/."""
import pytest

LOCATORS = "*** Variables ***\n&{LOC_CONNEXION_WEB}    champ_identifiant=id=identifiant    bouton_valider=id=valider\n"
KEYWORDS = ("*** Settings ***\nResource    ../locators/connexion.resource\n\n*** Keywords ***\nSaisir L'Identifiant\n"
            "    Fill Text    ${LOC_CONNEXION_WEB}[champ_identifiant]    demo\n")
SUITE = ("*** Settings ***\nResource    ../../resources/keywords/connexion.resource\n\n*** Test Cases ***\nConnexion réussie\n"
         "    [Tags]    DEMO-1\n    Saisir L'Identifiant\n")


@pytest.fixture
def depot(tmp_path, monkeypatch):
    from atelier.domain import projet

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    for chemin, contenu in (("resources/locators/connexion.resource", LOCATORS), ("resources/locators/accueil.resource", LOCATORS.replace("CONNEXION", "ACCUEIL")),
                            ("resources/keywords/connexion.resource", KEYWORDS), ("resources/pages/accueil_page.resource", KEYWORDS.replace("L'Identifiant", "Le Solde")),
                            ("tests/connexion/connexion.robot", SUITE)):
        f = tmp_path / chemin
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(contenu, "utf-8")
    return tmp_path


def test_structure_lue_dans_le_depot(depot):
    from atelier.generation import structure_depot as sd

    s = sd.structure()
    g = s["genres"]
    assert (g["tests"]["racine"], g["tests"]["fichiers"]) == ("tests/connexion", 1)
    assert (g["locators"]["racine"], g["locators"]["fichiers"]) == ("resources/locators", 2)
    assert g["keywords"]["racine"] == "resources" and [d["dossier"] for d in g["keywords"]["dossiers"]] == ["resources/keywords", "resources/pages"]
    assert not s["vide"] and s["consigne"]
    r = sd.resume()
    assert r["genres"]["locators"] == {"racine": "resources/locators", "dossiers": ["resources/locators"], "fichiers": 2}


def test_un_fichier_range_ailleurs_est_signale(depot):
    from atelier.generation import structure_depot as sd

    assert sd.genre_du_contenu("x.resource", LOCATORS) == "locators" and sd.genre_du_contenu("x.resource", KEYWORDS) == "keywords"
    assert sd.genre_du_contenu("x.robot", "") == "tests" and sd.genre_du_contenu("notes.txt", "bonjour") == ""
    ok = sd.controler("resources/locators/virement.resource", LOCATORS)
    assert ok["conforme"] and ok["genre"] == "locators" and ok["attendu"] == "resources/locators/"
    assert sd.controler("resources/pages/virement_page.resource", KEYWORDS)["conforme"]            # un dossier de keywords existant
    assert sd.controler("resources/keywords/virement/saisie.resource", KEYWORDS)["conforme"]       # un sous-dossier reste dans la structure
    ko = sd.controler("locators/virement.resource", LOCATORS)                                      # nouveau dossier racine
    assert not ko["conforme"] and "resources/locators/" in ko["message"]
    melange = sd.controler("resources/locators/virement_keywords.resource", KEYWORDS)              # des keywords dans le dossier des locators
    assert not melange["conforme"] and "Locators" in melange["message"]
    assert not sd.controler("suites/virement.robot", SUITE)["conforme"]
    assert sd.controler("notes.txt", "bonjour")["conforme"]                                        # non classé : rien à imposer


def test_depot_vide_rien_n_est_impose(tmp_path, monkeypatch):
    from atelier.domain import projet
    from atelier.generation import structure_depot as sd

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    assert sd.structure()["vide"]
    c = sd.controler("n_importe_ou/premier.robot", SUITE)
    assert c["conforme"] and "Premier fichier" in c["message"]


def test_le_fichier_controle_ne_justifie_pas_sa_propre_place(depot):
    """Une suite déjà écrite hors structure reste signalée : elle ne compte pas dans la structure qui la juge."""
    from atelier.generation import structure_depot as sd

    f = depot / "suites" / "virement.robot"
    f.parent.mkdir()
    f.write_text(SUITE.replace("../../resources", "../resources"), "utf-8")
    c = sd.controler("suites/virement.robot")
    assert not c["conforme"] and c["attendu"] == "tests/connexion/"


def test_cursor_recoit_la_structure_et_la_revue_la_controle(depot):
    from atelier.adapters import facade
    from atelier.generation import studio

    socle = facade.studio_socle()
    assert socle["structure"]["genres"]["locators"]["racine"] == "resources/locators"
    assert any("structure" in c for c in socle["conventions"])
    par_code = {c["code"]: c for c in studio.controles_script("tests/connexion/connexion.robot")}
    assert par_code["structure"]["gravite"] == "ok"
    f = depot / "suites" / "virement.robot"
    f.parent.mkdir()
    f.write_text(SUITE.replace("../../resources", "../resources"), "utf-8")
    c = {x["code"]: x for x in studio.controles_script("suites/virement.robot")}["structure"]
    assert c["gravite"] == "moyenne" and "hors de la structure" in c["message"]


def test_un_dossier_voisin_reste_dans_la_structure(depot):
    """Un nouveau module à côté des tests existants est légitime ; un nouveau dossier à la racine du dépôt ne l'est pas."""
    from atelier.generation import structure_depot as sd

    assert sd.controler("tests/virement/virement.robot", SUITE)["conforme"]                        # voisin de tests/connexion
    assert not sd.controler("virement/virement.robot", SUITE)["conforme"]
    assert sd.controler("resources/keywords/connexion.resource")["conforme"]                       # fichier existant, jugé sans lui-même


def test_l_editeur_signale_un_fichier_hors_structure(depot):
    """Enregistrer depuis l'Éditeur de code rend le constat de structure, sans jamais bloquer l'enregistrement."""
    from atelier.generation import editeur

    r = editeur.enregistrer("resources/locators/virement.resource", LOCATORS.replace("CONNEXION", "VIREMENT"))
    assert r["cree"] and r["structure"]["conforme"]
    r = editeur.enregistrer("locators_bis/virement.resource", LOCATORS.replace("CONNEXION", "VIREMENT2"))
    assert r["cree"] and not r["structure"]["conforme"] and "resources/locators/" in r["structure"]["message"]
    assert (depot / "locators_bis" / "virement.resource").exists()                                  # enregistré quand même
    p = editeur.proprietes("tests/connexion/connexion.robot")
    assert p["suite"]["structure"]["conforme"] and p["suite"]["revue"] == "Generated" and p["suite"]["parcours"] == []  # jamais revue : « Généré »
