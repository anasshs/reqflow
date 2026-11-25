"""Couverture des écrans et des parcours par les tests : locators « scalaires » du dépôt reliés à la carte par leur
valeur, écrans parcourus par un scénario BDD automatisé, état de couverture posé sur le Knowledge Graph."""
from atelier.domain.graphe import Graphe

LOCATORS = """*** Variables ***
${DASH_CLOCHE}          android=new UiSelector().resourceId("cloche")
${DASH_SOLDE}           xpath=//*[@resource-id="compte_0"]//*[contains(@text,"EUR")]
${URL_RECETTE}          https://recette.exemple.fr
"""
PAGE = """*** Settings ***
Resource    ../locators/dashboard.resource

*** Keywords ***
j'ouvre les notifications
    Click Element    ${DASH_CLOCHE}
"""
SUITE = """*** Settings ***
Library     AppiumLibrary
Resource    ../resources/pages/dashboard.resource

*** Test Cases ***
Ouvrir les notifications
    [Tags]    DEMO-1
    j'ouvre les notifications
"""


def _depot(tmp_path):
    (tmp_path / "resources" / "locators").mkdir(parents=True)
    (tmp_path / "resources" / "pages").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "resources" / "locators" / "dashboard.resource").write_text(LOCATORS, "utf-8")
    (tmp_path / "resources" / "pages" / "dashboard.resource").write_text(PAGE, "utf-8")
    (tmp_path / "tests" / "notifications.robot").write_text(SUITE, "utf-8")
    from atelier.execution import depot_robot

    return depot_robot.lire_depot(tmp_path)


def test_locators_scalaires_du_depot(tmp_path):
    inv = _depot(tmp_path)
    loc = inv["locators"]["dashboard.dash_cloche@android"]
    assert loc["scalaire"] and loc["valeur"].startswith("android=") and "dashboard.url_recette@android" not in inv["locators"]
    kw = next(k for k in inv["keywords"].values() if k["nom"] == "j'ouvre les notifications")
    assert ("dashboard", "dash_cloche") in kw["locators"]


LOCATORS_PAR_PLATEFORME = """*** Variables ***
${CLOCHE}               ${CLOCHE_${PLATFORM}}
${CLOCHE_ANDROID}       id=${APP_ID}:id/cloche
${CLOCHE_IOS}           ${EMPTY}
${TITRE}                ${TITRE_${PLATFORM}}
${TITRE_ANDROID}        xpath=//*[@resource-id="${APP_ID}:id/tvTitle" and contains(@text,"Notifications")]
"""
PAGE_PAR_PLATEFORME = """*** Settings ***
Resource    ../locators/accueil_locators.resource

*** Keywords ***
J'ouvre les notifications
    Click Element    ${CLOCHE}
    Wait Until Page Contains Element    ${TITRE}
"""


def test_locators_declines_par_plateforme(tmp_path):
    """Convention ${NOM}    ${NOM_${PLATFORM}} : ${NOM_ANDROID} a la clé métier « nom » et ${NOM} dans un keyword y renvoie."""
    (tmp_path / "resources" / "locators").mkdir(parents=True)
    (tmp_path / "resources" / "pages").mkdir()
    (tmp_path / "resources" / "locators" / "accueil_locators.resource").write_text(LOCATORS_PAR_PLATEFORME, "utf-8")
    (tmp_path / "resources" / "pages" / "accueil.resource").write_text(PAGE_PAR_PLATEFORME, "utf-8")
    from atelier.execution import depot_robot

    inv = depot_robot.lire_depot(tmp_path)
    assert set(inv["locators"]) == {"accueil_locators.cloche@android", "accueil_locators.titre@android"}  # ${EMPTY} ignoré
    kw = next(k for k in inv["keywords"].values() if k["nom"] == "J'ouvre les notifications")
    assert kw["locators"] == [("accueil_locators", "cloche"), ("accueil_locators", "titre")]


def test_identite_d_un_locator_independante_de_la_syntaxe():
    from atelier.discovery.connaissance import identifiant_locator as i

    assert i('android=new UiSelector().resourceId("cloche")') == i("id=com.exemple:id/cloche") == i('//*[@resource-id="cloche"]') == "rid:cloche"
    # package porté par une variable Robot : même identité que dans la carte
    assert i("id=${APP_ID}:id/cloche") == i('xpath=//*[@resource-id="${APP_ID}:id/cloche" and @enabled="true"]') == "rid:cloche"
    assert i("accessibility_id=Se connecter") == "acc:Se connecter"
    assert i("xpath=//android.widget.Button") == ""


def _graphe_carte():
    g = Graphe("essai")
    for e in ("accueil", "notifications", "aide"):
        g.noeud(f"ecran:{e}", "ecran", e, source="carte")
    # même élément que le dépôt, écrit autrement (id= au lieu de UiSelector) : relié par son resource-id
    g.noeud("locator:accueil.bouton_cloche@android", "locator", "bouton_cloche", source="carte",
            proprietes={"valeur": "id=com.exemple:id/cloche", "plateforme": "android"})
    g.relier("ecran:accueil", "locator:accueil.bouton_cloche@android", "contient")
    g.noeud("parcours:notifs", "parcours", "Lire ses notifications")
    g.relier("parcours:notifs", "ecran:accueil", "contient")
    g.relier("parcours:notifs", "ecran:notifications", "contient")
    g.noeud("parcours:aide", "parcours", "Consulter l'aide")
    g.relier("parcours:aide", "ecran:aide", "contient")
    return g


def test_test_du_depot_relie_a_l_ecran_de_la_carte(tmp_path):
    from atelier.discovery import connaissance
    from atelier.intelligence import couverture_avancee as ca

    g = _graphe_carte()
    connaissance._depuis_depot(g, _depot(tmp_path))
    assert "ecran:dashboard" not in g.noeuds  # le fichier de locators n'est pas un écran
    e = {x["nom"]: x for x in ca.calculer(g)["ecrans"]}
    assert e["accueil"]["niveau"] == "automatisé" and e["accueil"]["tests_robot"] == ["Ouvrir les notifications"]
    assert e["notifications"]["niveau"] == "découvert"


def test_ecran_parcouru_par_un_scenario_bdd_automatise(tmp_path):
    from atelier.discovery import connaissance

    g = _graphe_carte()
    connaissance._depuis_depot(g, _depot(tmp_path))
    tid = next(i for i, n in g.noeuds.items() if n.type == "test_robot")
    g.noeuds[tid].proprietes["dernier_statut"] = "PASS"
    g.noeud("scenario:NOTIFS", "scenario", "Lire ses notifications")
    g.relier("scenario:NOTIFS", "ecran:notifications", "couvre")
    g.relier("scenario:NOTIFS", tid, "implemente_par")
    connaissance._annoter_couverture_tests(g)
    etat = lambda i: g.noeuds[i].proprietes["couverture_tests"]["etat"]  # noqa: E731
    assert etat("ecran:accueil") == etat("ecran:notifications") == "couvert" and etat("ecran:aide") == "non_couvert"
    assert etat("parcours:notifs") == "couvert" and etat("parcours:aide") == "non_couvert"
    g.noeuds[tid].proprietes["dernier_statut"] = "FAIL"
    connaissance._annoter_couverture_tests(g)
    assert etat("ecran:notifications") == "echec"


def test_composant_commun_et_socle_ne_couvrent_pas_tous_les_ecrans():
    """Une barre de navigation présente sur beaucoup d'écrans, ou un keyword du socle appelé par presque tous les tests
    (initialisation, popups au démarrage), ne rendent pas « couverts » tous les écrans où ces éléments existent."""
    from atelier.discovery import connaissance
    from atelier.intelligence import couverture_avancee as ca

    g = Graphe("essai")
    for e in ("e1", "e2", "e3", "e4", "e5"):
        g.noeud(f"ecran:{e}", "ecran", e, source="carte")
        g.noeud(f"locator:{e}.nav_menu@android", "locator", "nav_menu", source="carte",
                proprietes={"valeur": 'android=new UiSelector().resourceId("nav_menu")', "plateforme": "android"})
        g.relier(f"ecran:{e}", f"locator:{e}.nav_menu@android", "contient")
    g.noeud("locator:e1.popup_ok@android", "locator", "popup_ok", source="carte",
            proprietes={"valeur": 'android=new UiSelector().resourceId("popup_ok")', "plateforme": "android"})
    g.relier("ecran:e1", "locator:e1.popup_ok@android", "contient")
    inv = {"locators": {
        "commun.nav_menu@android": {"id": "commun.nav_menu@android", "ecran": "commun", "cle": "nav_menu", "plateforme": "android",
                                    "valeur": 'android=new UiSelector().resourceId("nav_menu")', "secours": [], "fichier": "l.resource", "scalaire": True},
        "commun.popup_ok@android": {"id": "commun.popup_ok@android", "ecran": "commun", "cle": "popup_ok", "plateforme": "android",
                                    "valeur": 'android=new UiSelector().resourceId("popup_ok")', "secours": [], "fichier": "l.resource", "scalaire": True}},
        "fichiers": {}, "suites": {}, "keywords": {}, "tests": {}}
    vide = {"keywords": [], "locators": [], "ecrans": [], "jdd": []}
    inv["keywords"]["ouvrirmenu"] = {**vide, "nom": "ouvrir menu", "fichier": "p.resource", "ligne": 1, "doc": "", "externes": [],
                                     "locators": [("commun", "nav_menu")]}
    inv["keywords"]["initialiser"] = {**vide, "nom": "initialiser", "fichier": "c.resource", "ligne": 1, "doc": "", "externes": [],
                                      "locators": [("commun", "popup_ok")]}
    for i in range(6):
        inv["tests"][f"t{i}"] = {**vide, "nom": f"t{i}", "fichier": "s.robot", "ligne": 1, "doc": "", "tags": [], "cles_xray": [],
                                 "plateformes": ["android"], "bibliotheques": [], "keywords": ["initialiser"] + (["ouvrirmenu"] if i == 0 else [])}
    connaissance._depuis_depot(g, inv)
    assert g.noeuds["locator:commun.nav_menu@android"].proprietes["composant_commun"] == 5
    e = {x["nom"]: x for x in ca.calculer(g)["ecrans"]}
    assert all(e[x]["niveau"] == "découvert" for x in ("e1", "e2", "e3", "e4", "e5"))  # ni la barre de navigation, ni le socle


def test_carte_de_couverture(tmp_path, monkeypatch):
    """Écran « Couverture des tests » : parcours en chaînes d'écrans dans l'ordre de navigation, écrans avec leurs tests,
    matrice tests × écrans (clé Xray, dernier statut)."""
    from atelier.discovery import connaissance
    from atelier.domain import projet as p
    from atelier.intelligence import couverture_avancee as ca

    monkeypatch.setattr(p, "PROJECT_DIR", tmp_path)
    g = _graphe_carte()
    g.relier("ecran:accueil", "ecran:notifications", "navigue_vers")
    connaissance._depuis_depot(g, _depot(tmp_path))
    tid = next(i for i, n in g.noeuds.items() if n.type == "test_robot")
    g.noeuds[tid].proprietes["dernier_statut"] = "PASS"
    connaissance._annoter_couverture_tests(g)
    c = ca.carte(g)
    assert c["indicateurs"] == {"parcours": 2, "parcours_couverts": 0, "ecrans": 3, "couvert": 1, "echec": 0, "partiel": 0, "non_couvert": 2}
    notifs = next(x for x in c["parcours"] if x["libelle"] == "Lire ses notifications")
    assert [(e["nom"], e["etat"]) for e in notifs["etapes"]] == [("accueil", "couvert"), ("notifications", "non_couvert")]
    assert c["tests"] == [{"id": tid, "nom": "Ouvrir les notifications", "cle_xray": "DEMO-1", "statut": "PASS",
                           "fichier": "tests/notifications.robot"}]
    assert next(e for e in c["ecrans"] if e["nom"] == "accueil")["tests"] == [tid]
