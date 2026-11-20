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


def test_aller_a_la_definition(depot):
    """Ctrl + clic dans l'Éditeur de code : keyword, variable ou fichier importé sous le curseur, dans le fichier ouvert
    (même non enregistré) puis dans le dépôt."""
    from atelier.generation import editeur

    def ou(chemin, contenu, cherche, decalage=1, n=1):
        """Définition de la n-ième occurrence de « cherche » (curseur placé « decalage » caractères après son début)."""
        lignes = contenu.splitlines()
        vus = 0
        for i, l in enumerate(lignes, 1):
            if cherche in l:
                vus += 1
                if vus == n:
                    return editeur.definition(chemin, contenu, i, l.index(cherche) + 1 + decalage)
        raise AssertionError(cherche)

    # keyword défini dans une ressource importée, appelé depuis la suite (préfixe BDD ignoré)
    suite = SUITE.replace("    Saisir L'Identifiant\n", "    Given saisir l'identifiant\n    Log    ${LOC_CONNEXION_WEB}[champ_identifiant]\n    Fill Text    x    y\n")
    d = ou("tests/connexion/connexion.robot", suite, "saisir l'identifiant", 8)
    assert (d["trouve"], d["genre"], d["fichier"], d["ligne"]) == (True, "keyword", "resources/keywords/connexion.resource", 5)
    # variable (dictionnaire de locators) déclarée dans un autre fichier ; le curseur peut être sur la clé entre crochets
    d = ou("tests/connexion/connexion.robot", suite, "${LOC_CONNEXION_WEB}", 3)
    assert (d["genre"], d["fichier"], d["ligne"]) == ("variable", "resources/locators/connexion.resource", 2)
    assert ou("tests/connexion/connexion.robot", suite, "[champ_identifiant]", 2)["fichier"] == "resources/locators/connexion.resource"
    # fichier importé
    d = ou("tests/connexion/connexion.robot", suite, "Resource    ../../resources", 14)
    assert (d["genre"], d["fichier"], d["ligne"]) == ("fichier", "resources/keywords/connexion.resource", 1)
    # keyword d'une bibliothèque, texte libre : rien à ouvrir, avec la raison
    d = ou("tests/connexion/connexion.robot", suite, "Fill Text", 2)
    assert not d["trouve"] and "aucun keyword de ce nom dans le dépôt" in d["message"]
    assert not editeur.definition("tests/connexion/connexion.robot", suite, 999, 1)["trouve"]

    # dans le fichier ouvert, non enregistré : keyword local, argument, affectation, keyword à arguments intégrés
    tampon = ("*** Variables ***\n${DELAI}    5s\n\n*** Test Cases ***\nUn test\n    ${solde}=    Lire Le Solde\n    Vérifier ${solde} Euros    ${DELAI}\n\n"
              "*** Keywords ***\nLire Le Solde\n    RETURN    10\n\nVérifier ${montant} Euros\n    [Arguments]    ${attente}\n    Sleep    ${attente}\n    Log    ${montant}\n")
    assert (ou("x.robot", tampon, "Lire Le Solde", 3)["fichier"], ou("x.robot", tampon, "Lire Le Solde", 3)["ligne"]) == ("x.robot", 10)
    assert ou("x.robot", tampon, "Vérifier ${solde} Euros", 1)["ligne"] == 13            # arguments intégrés
    assert ou("x.robot", tampon, "${DELAI}", 2, n=2)["ligne"] == 2                        # section Variables du même fichier
    assert ou("x.robot", tampon, "${solde} Euros", 2)["ligne"] == 6                       # affectation plus haut dans le test
    assert ou("x.robot", tampon, "Sleep    ${attente}", 11)["ligne"] == 14                # argument du keyword
    d = ou("x.robot", tampon.replace("${DELAI}\n", "&{JDD_CLIENT}\n"), "&{JDD_CLIENT}", 2)
    assert not d["trouve"] and "jeu de données" in d["message"]


def test_l_auto_completion_recoit_les_variables_du_depot(depot):
    """Ce que l'éditeur propose en tapant vient du dépôt : keywords, locators, ressources et variables déclarées."""
    from atelier.generation import editeur

    r = editeur.reutilisation()
    assert {"nom": "LOC_CONNEXION_WEB", "fichier": "resources/locators/connexion.resource"} in r["variables"]
    assert "Saisir L'Identifiant" in [k["nom"] for k in r["keywords"]]
    assert ("connexion", "champ_identifiant", "web") in [(l["ecran"], l["cle"], l["plateforme"]) for l in r["locators"]]
    assert "resources/keywords/connexion.resource" in r["resources"]
