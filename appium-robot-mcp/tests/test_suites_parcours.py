"""Une suite Robot par parcours métier : les tests d'un même parcours vont dans la même suite. Le premier crée la suite du
parcours, les suivants y sont ajoutés en fin de suite, sans rien réécrire. Application et données fictives."""
import pytest

SUITE = """*** Settings ***
Documentation    Parcours Faire un virement
Resource    ../../resources/socle/commun.resource

*** Test Cases ***
Virement simple
    [Tags]    DEMO-11    smoke
    Given Se Connecter
    Then Le Solde Est Affiché

*** Keywords ***
Le Solde Est Affiché
    Log    solde
"""
GENERE = """*** Settings ***
Documentation    Virement au plafond — généré
Resource    ../../resources/socle/commun.resource
Resource    ../../resources/socle/virement.resource

*** Test Cases ***
Virement au plafond
    [Tags]    DEMO-13
    Given Se Connecter
    When Saisir Le Plafond

*** Keywords ***
Saisir Le Plafond
    [Documentation]    À implémenter : aucun keyword du dépôt ne correspond.
    Fail    Keyword à implémenter : Saisir Le Plafond
"""
GHERKIN = "Étant donné Se Connecter\nQuand Saisir Le Montant\nAlors Valider Le Virement\n"


def test_ajouter_ne_reecrit_rien():
    from atelier.generation import suites_parcours as sp

    a = sp.ajouter(SUITE, GENERE)
    c = a["contenu"]
    assert a["tests"] == ["Virement au plafond"] and a["keywords"] == ["Saisir Le Plafond"]
    assert a["imports"] == ["Resource    ../../resources/socle/virement.resource"]                # l'import déjà présent n'est pas répété
    assert c.count("Resource    ../../resources/socle/commun.resource") == 1
    assert c.index("Virement simple") < c.index("Virement au plafond") < c.index("*** Keywords ***")   # ajouté en fin de section de tests
    assert c.index("Le Solde Est Affiché\n    Log") < c.index("Saisir Le Plafond\n    [Documentation]")
    lignes = iter(c.splitlines())
    assert all(any(x == y for y in lignes) for x in SUITE.splitlines() if x.strip())                # chaque ligne d'origine, dans l'ordre
    assert c.count("*** Test Cases ***") == 1 and c.count("*** Keywords ***") == 1 and c.endswith("\n")


def test_ajouter_refuse_un_test_deja_present():
    from atelier.generation import suites_parcours as sp

    with pytest.raises(FileExistsError, match="déjà dans la suite"):
        sp.ajouter(SUITE, GENERE.replace("Virement au plafond\n", "Virement simple\n"))          # même nom
    with pytest.raises(FileExistsError, match="DEMO-11"):
        sp.ajouter(SUITE, GENERE.replace("DEMO-13", "DEMO-11"))                                    # même clé Xray
    with pytest.raises(ValueError, match="Test Cases"):
        sp.ajouter("*** Keywords ***\nUn Keyword\n    Log    x\n", GENERE)
    sans = sp.ajouter("*** Test Cases ***\nPremier\n    Log    x\n", GENERE)["contenu"]             # suite minimale : sections créées
    assert sans.startswith("*** Settings ***\nResource") and sans.rstrip().endswith("Fail    Keyword à implémenter : Saisir Le Plafond")


@pytest.fixture
def banque(projet):
    """Un parcours « Faire un virement » qui porte l'US DEMO-2 ; trois tests Xray, dont deux couvrent DEMO-2."""
    from atelier.discovery import carte, connaissance, parcours_utilisateur as pu
    from atelier.intelligence import patrimoine_xray

    carte.creer_app("Banque Web", ["web"], web={"url": "https://recette.exemple.fr"}, type_="web")
    patrimoine_xray.enregistrer({"projet": "DEMO", "exigences": [{"cle": "DEMO-2", "type": "user_story", "resume": "Saisir un virement"},
                                                                   {"cle": "DEMO-4", "type": "user_story", "resume": "Consulter les comptes"}],
                                 "tests": [{"cle": "DEMO-11", "resume": "Virement simple", "exigences": ["DEMO-2"]},
                                           {"cle": "DEMO-13", "resume": "Virement au plafond", "exigences": ["DEMO-2"]},
                                           {"cle": "DEMO-15", "resume": "Liste des comptes", "exigences": ["DEMO-4"]}]}, "test")
    connaissance.vider_cache()
    return pu.enregistrer("", {"nom": "Faire un virement", "plateforme": "web", "exigences": ["DEMO-2"]})


def test_les_tests_d_un_parcours_vont_dans_la_meme_suite(banque):
    from atelier.adapters import facade
    from atelier.domain import projet as pj
    from atelier.generation import bdd, studio, suites_parcours as sp

    assert sp.parcours_du_test("DEMO-11")["nom"] == "Faire un virement" and sp.parcours_du_test("DEMO-15") is None
    for cle, titre in (("DEMO-11", "Virement simple"), ("DEMO-13", "Virement au plafond"), ("DEMO-15", "Liste des comptes")):
        bdd.creer(cle, titre, depuis_xray={"gherkin": GHERKIN, "resume": titre})

    # premier test du parcours : nouvelle suite, au nom du parcours
    g = facade.studio_generer_depuis_bdd("DEMO-11")
    assert (g["chemin"], g["parcours"], g["ajout"]) == ("tests/banque_web/sans_module/faire_un_virement.robot", "Faire un virement", False)
    assert "première suite du parcours" in g["raison_suite"]
    facade.studio_generer_depuis_bdd("DEMO-11", ecrire=True)
    premiere = pj.lire_fichier(g["chemin"])

    # deuxième test du même parcours : ajouté à la suite, sans rien réécrire
    g = facade.studio_generer_depuis_bdd("DEMO-13")
    assert g["ajout"] and g["chemin"] == "tests/banque_web/sans_module/faire_un_virement.robot" and g["tests_ajoutes"] == ["Virement au plafond"]
    assert "Virement au plafond" in g["ajoute"] and "Virement simple" not in g["ajoute"]
    facade.studio_generer_depuis_bdd("DEMO-13", ecrire=True)
    suite = pj.lire_fichier(g["chemin"])
    assert suite.startswith(premiere.rstrip()[:200]) and "[Tags]    DEMO-11" in suite and "[Tags]    DEMO-13" in suite
    assert suite.count("*** Test Cases ***") == 1
    assert studio.revues_scripts()[g["chemin"]]["statut"] == "Generated"                            # la suite complétée repasse en revue

    # le même test une seconde fois : refusé, rien n'est écrit
    assert "déjà dans la suite" in facade.studio_generer_depuis_bdd("DEMO-13")["ajout_refuse"]
    with pytest.raises(FileExistsError):
        facade.studio_generer_depuis_bdd("DEMO-13", ecrire=True)
    assert pj.lire_fichier(g["chemin"]) == suite

    # un test sans parcours métier garde sa propre suite ; un chemin imposé n'est jamais un ajout
    g = facade.studio_generer_depuis_bdd("DEMO-15")
    assert (g["chemin"], g["parcours"], g["ajout"]) == ("tests/banque_web/sans_module/liste_des_comptes.robot", "", False)
    g = facade.studio_generer_depuis_bdd("DEMO-15", chemin="tests/banque_web/sans_module/faire_un_virement.robot")
    assert g["ajout"] is False
    with pytest.raises(FileExistsError):
        facade.studio_generer_depuis_bdd("DEMO-15", ecrire=True, chemin="tests/banque_web/sans_module/faire_un_virement.robot")


def test_la_suite_existante_du_parcours_est_retrouvee_par_ses_tests(banque):
    """Dépôt existant : la suite du parcours n'a pas le nom du parcours, elle est reconnue aux clés Xray qu'elle porte."""
    from atelier.domain import projet as pj
    from atelier.generation import bdd

    f = pj.PROJECT_DIR / "tests" / "virements" / "parcours_virement.robot"
    f.parent.mkdir(parents=True)
    f.write_text(SUITE.replace("Resource    ../../resources/socle/commun.resource\n", ""), "utf-8")
    m = bdd.creer("DEMO-13", "Virement au plafond", depuis_xray={"gherkin": GHERKIN, "resume": "Virement au plafond"})
    g = bdd.generer_robot(m)
    assert g["ajout"] and g["chemin"] == "tests/virements/parcours_virement.robot" and "porte déjà des tests du parcours" in g["raison_suite"]
    assert "Virement simple" in g["contenu"] and "Virement au plafond" in g["contenu"]
