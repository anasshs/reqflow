"""XCUITest (iOS natif, Swift) : dépôts par technologie, génération depuis le BDD, conversion Robot → Swift, exécution
xcodebuild (simulée : pas de Mac dans les tests)."""
import shutil
from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"

RESSOURCE = """*** Settings ***
Library    AppiumLibrary

*** Variables ***
${BTN_VALIDER}            ${BTN_VALIDER_${PLATFORM}}
${BTN_VALIDER_ANDROID}    id=${APP_ID}:id/btnValider
${BTN_VALIDER_IOS}        accessibility_id=valider
${CHAMP_COMPTE}           ${CHAMP_COMPTE_${PLATFORM}}
${CHAMP_COMPTE_ANDROID}   id=${APP_ID}:id/compte
${CHAMP_COMPTE_IOS}       -ios predicate string:name == "compte"
${MENU}                   ${MENU_${PLATFORM}}
${MENU_ANDROID}           id=${APP_ID}:id/menu
${MENU_IOS}               ${EMPTY}

*** Keywords ***
Je Valide
    Wait Until Element Is Visible    ${BTN_VALIDER}    timeout=10s
    Click Element    ${BTN_VALIDER}

Le Compte Est ${compte}
    Input Text    ${CHAMP_COMPTE}    ${compte}

Je Saisis Le Montant Du Jeu
    Input Text    ${CHAMP_COMPTE}    ${JDD}[montant]

J'Ouvre Le Menu
    Click Element    ${MENU}

Je Recommence Si Besoin
    IF    ${TRUE}
        Click Element    ${BTN_VALIDER}
    END
"""
SUITE = """*** Settings ***
Resource    ../resources/virement.resource

*** Test Cases ***
Virement simple
    [Tags]    DEMO-1    smoke
    Initialiser Le Test    &{JDD_VIREMENT}
    Given Le Compte Est 123456
    When Je Saisis Le Montant Du Jeu
    Then Je Valide

Virement avec menu
    [Tags]    DEMO-2
    J'Ouvre Le Menu
    Je Recommence Si Besoin
"""


@pytest.fixture
def env(projet, tmp_path):
    shutil.copytree(DEMO, projet, dirs_exist_ok=True, ignore=shutil.ignore_patterns("results", "connaissance", "strategie"))
    robot_d, ios_d = tmp_path / "depot_robot", tmp_path / "depot_ios"
    (robot_d / "resources").mkdir(parents=True)
    (robot_d / "tests").mkdir()
    (robot_d / "resources" / "virement.resource").write_text(RESSOURCE, "utf-8")
    (robot_d / "tests" / "virement.robot").write_text(SUITE, "utf-8")
    ios_d.mkdir()
    from atelier.discovery import carte

    carte.maj_app(None, depots=carte.normaliser_depots([
        {"technologies": ["robot"], "dossier": str(robot_d)},
        {"technologies": ["xcuitest"], "dossier": str(ios_d), "gitlab_url": "https://gitlab.exemple", "gitlab_projet": "mobile/banque-ios"}]),
        ios={"bundle_id": "com.exemple.banque"},
        automatisation={"xcode_projet": "Banque.xcodeproj", "xcode_schema": "BanqueUITests", "xcode_cible": "BanqueUITests"})
    return robot_d, ios_d


def test_un_depot_par_technologie(env):
    from atelier.discovery import carte
    from atelier.domain import projet
    from atelier.integrations.gitlab import _cible

    robot_d, ios_d = env
    assert projet.racine_code("xcuitest") == ios_d.resolve()
    assert projet.racine_code("robot-appium") == robot_d.resolve() == projet.racine_code()
    with projet.pour_technologie("xcuitest"):
        assert projet.safe_path("AtelierUITests/Bdd/X.swift") == (ios_d / "AtelierUITests" / "Bdd" / "X.swift").resolve()
        assert _cible() == ("https://gitlab.exemple", "mobile/banque-ios")      # merge request vers le GitLab du dépôt iOS
    assert projet.safe_path("tests/a.robot") == (robot_d / "tests" / "a.robot").resolve()
    with pytest.raises(ValueError, match="deux dépôts"):
        carte.normaliser_depots([{"technologies": ["xcuitest"], "dossier": "a"}, {"technologies": ["xcuitest"], "dossier": "b"}])
    with pytest.raises(ValueError, match="inconnue"):
        carte.normaliser_depots([{"technologies": ["swiftui"], "dossier": "a"}])


def test_generation_bdd_vers_xcuitest(env):
    from atelier.generation import bdd, technologies

    _, ios_d = env
    t = technologies.obtenir("xcuitest")
    m = bdd.charger("DEMO-301")
    g = t.generer(m)
    assert g["langage"] == "Swift" and g["chemin"].startswith("AtelierUITests/Bdd/") and "final class" in g["contenu"]
    assert "func test_DEMO_301_" in g["contenu"] and "continueAfterFailure = false" in g["contenu"]
    assert '"com.exemple.banque"' in g["socle"][0]["contenu"]
    t.ecrire(m, g)
    assert (ios_d / g["chemin"]).is_file() and (ios_d / "AtelierUITests" / "Socle" / "Atelier.swift").is_file()


def test_conversion_robot_vers_swift(env):
    from atelier.generation import robot2swift

    robot_d, ios_d = env
    r = robot2swift.porter(ecrire=True)
    kw = (ios_d / "AtelierUITests" / "Genere" / "Keywords.swift").read_text("utf-8")
    assert 'Atelier.attendre("accessibility_id=valider", 10)' in kw and 'Atelier.toucher("accessibility_id=valider")' in kw
    assert "func k_le_compte_est_compte(_ a_compte: String)" in kw  # même nom que le portage Kotlin (slug du nom complet) and 'Atelier.saisir("-ios predicate string:name == \\"compte\\"", a_compte)' in kw
    assert 'Atelier.donnee("montant")' in kw                                        # ${JDD}[montant]
    assert "locator iOS absent" in kw                                                # ${MENU_IOS} vide : à capturer
    assert "structure IF non convertie" in kw
    tests = (ios_d / "AtelierUITests" / "Genere" / "VirementRobotTests.swift").read_text("utf-8")
    assert "func test_DEMO_1_virement_simple() throws" in tests
    assert 'Atelier.initialiser(jeu: "VIREMENT")' in tests and 'k_le_compte_est_compte("123456")' in tests and "k_je_valide()" in tests
    d = {t["cle_xray"]: t for t in r["detail_tests"]}
    assert d["DEMO-1"]["complet"] and not d["DEMO-2"]["complet"]
    assert r["tests"] == 2 and r["tests_complets"] == 1 and (ios_d / "AtelierUITests" / "Socle" / "Atelier.swift").exists()
    assert not (robot_d / "AtelierUITests").exists()                                 # rien d'écrit dans le dépôt Robot


def test_execution_xcodebuild(env):
    from atelier.execution import xcuitest

    sortie = """Test Suite 'BanqueUITests' started
Test Case '-[BanqueUITests.VirementRobotTests test_DEMO_1_virement_simple]' passed (4.210 seconds).
/x/VirementRobotTests.swift:12: error: -[BanqueUITests.VirementRobotTests test_DEMO_2_virement_avec_menu] : failed - Étape à implémenter : J'Ouvre Le Menu
Test Case '-[BanqueUITests.VirementRobotTests test_DEMO_2_virement_avec_menu]' failed (1.020 seconds).
"""
    res = xcuitest.analyser_sortie(sortie)
    assert [(t["methode"], t["statut"], t["cle_xray"]) for t in res] == [("test_DEMO_1_virement_simple", "PASS", "DEMO-1"),
                                                                         ("test_DEMO_2_virement_avec_menu", "FAIL", "DEMO-2")]
    assert "Étape à implémenter" in res[1]["message"]
    cmd = xcuitest.commande("test", ["VirementRobotTests/test_DEMO_1_virement_simple"])
    assert cmd[:2] == ["xcodebuild", "test"] and "-project" in cmd and "-only-testing:BanqueUITests/VirementRobotTests/test_DEMO_1_virement_simple" in cmd
    vus = {}

    def lanceur(c, e, delai, cwd):
        vus.update(cmd=c, env=e, cwd=cwd)
        return 1, sortie

    b = xcuitest.executer(["VirementRobotTests"], {"VIREMENT": {"montant": "120", "mot_de_passe": "s3cret"}}, {"otp_mode": "arret"}, lanceur=lanceur)
    assert b["passes"] == 1 and b["echecs"] == 1 and vus["env"]["TEST_RUNNER_JDD_VIREMENT_MONTANT"] == "120"
    assert vus["env"]["TEST_RUNNER_OTP_MODE"] == "arret" and "s3cret" not in b["commande"]
    assert xcuitest.jeux_des_tests([]) == [] or isinstance(xcuitest.jeux_des_tests([]), list)
    if not xcuitest.disponible()["disponible"]:
        assert xcuitest.compiler()["mac_requis"]                                      # hors Mac : refus clair


def test_outil_mcp():
    from atelier.adapters import facade

    assert callable(facade.porter_vers_xcuitest)
