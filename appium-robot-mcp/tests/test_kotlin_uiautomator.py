"""Technologie UI Automator (phase C, docs/AUTOMATISATION_MULTI_CIBLES.md) : génération Kotlin depuis le plan neutre
(Page Objects par écran, classe par parcours, keywords portés réutilisés), complétée sans réécriture, résultats
d'instrumentation lus et remontés dans l'outbox Xray. Ni Gradle ni téléphone : projet Kotlin et sorties simulés."""
from __future__ import annotations

import json
import shutil

import pytest

from conftest import FIXTURES

GHERKIN = """# language: fr
Fonctionnalité: Virement
  Scénario: Virement vers un bénéficiaire
    Étant donné Se Connecter
    Et Le Compte De Connexion Est ${COMPTE_VALIDE}
    Quand je touche le bouton virement
    Et je saisis le montant
    Et je fais une chose inconnue
    Et je saisis le code OTP reçu par SMS
    Alors le récapitulatif affiche le montant
"""
SOCLE = {"Simple.kt": "object Simple", "Cible.kt": "class Cible", "Locators.kt": "object Locators", "R.kt": "object R"}


@pytest.fixture
def kotlin(projet):
    shutil.copytree(FIXTURES / "projet_robot", projet, dirs_exist_ok=True)
    app = projet / "uiautomator" / "app"
    app.mkdir(parents=True)
    (app / "build.gradle.kts").write_text('android {\n    namespace = "ma.demo.tnr"\n}\n', "utf-8")
    src = app / "src" / "androidTest" / "java" / "ma" / "demo" / "tnr"
    (src / "socle").mkdir(parents=True)
    for f, c in SOCLE.items():
        (src / "socle" / f).write_text(f"package ma.demo.tnr.socle\n{c}\n", "utf-8")
    (src / "genere").mkdir()
    (src / "genere" / "Mc_auth.kt").write_text("package ma.demo.tnr.genere\n"
                                               "fun k_se_connecter(vararg a: Any?): Any? = null\n"
                                               "fun k_le_compte_de_connexion_est(vararg a: Any?): Any? = null\n", "utf-8")
    return projet


def _modele(cle="DEMO-60"):
    from atelier.generation import bdd

    m = bdd.charger(cle) or bdd.creer(cle, depuis_xray={"gherkin": GHERKIN}, jdd="VIREMENT_STANDARD")
    m["parcours"] = "PU-virement"
    et = m["scenarios"][0]["etapes"]
    et[2].update(locator='android=new UiSelector().resourceId("com.demo:id/btnVirement")', ecran="ecran:virement")
    et[3].update(locator="id=${APP_ID}:id/editTextInput", jdd="montant", ecran="ecran:virement")
    et[6].update(locator="accessibility_id=Récapitulatif", ecran="ecran:recap", resultat_attendu="100")
    bdd.sauver(m)
    return m


def test_generation_kotlin_depuis_le_plan(kotlin):
    from atelier.generation import technologies

    g = technologies.obtenir("uiautomator").generer(_modele())
    c = g["contenu"]
    assert g["chemin"] == "uiautomator/app/src/androidTest/java/ma/demo/tnr/bdd/VirementBddTest.kt" and g["classe"] == "ma.demo.tnr.bdd.VirementBddTest"
    assert '@Xray("DEMO-60")' in c and "fun demo60VirementVersUnBeneficiaire()" in c
    assert "        k_se_connecter()" in c                                                   # keyword porté réutilisé
    assert '        k_le_compte_de_connexion_est(R.fmt(v, "\\${COMPTE_VALIDE}"))' in c         # argument explicite
    assert "        PageVirement.btnvirement.cliquer()" in c
    assert '        PageVirement.edittextinput.saisir(Bdd.donnee("VIREMENT_STANDARD", "montant"))' in c
    assert '        Bdd.aImplementer("je fais une chose inconnue")' in c and g["a_implementer"] == ["je fais une chose inconnue"]
    assert "        if (Bdd.otp()) return" in c and "Bdd.avantOtp()" in c
    assert '        Bdd.verifier(PageRecap.recapitulatif, "le récapitulatif affiche le montant", "100")' in c
    pages = {p["page"]: p["contenu"] for p in g["pages"]}
    assert 'val btnvirement = Cible(By.res("com.demo:id/btnVirement"))' in pages["PageVirement"]
    assert 'val edittextinput = Cible(By.res(Simple.paquet, "editTextInput"))' in pages["PageVirement"]  # ${APP_ID} -> paquet de l'app
    assert 'val recapitulatif = Cible(By.desc("Récapitulatif"))' in pages["PageRecap"]
    assert "annotation class Xray" in g["socle"][0]["contenu"] and "package ma.demo.tnr.bdd" in g["socle"][0]["contenu"]


def test_ecriture_complete_sans_reecrire(kotlin):
    """Une méthode ou un élément existants ne sont jamais réécrits ; un second scénario du parcours rejoint la classe."""
    from atelier.domain import projet
    from atelier.generation import technologies

    t = technologies.obtenir("uiautomator")
    g = t.ecrire(_modele(), t.generer(_modele()))
    assert g["revue"]["statut"] == "Generated"
    chemin = g["chemin"]
    projet.ecrire_fichier(chemin, projet.lire_fichier(chemin).replace("k_se_connecter()", "k_se_connecter() // retouché à la main"), True)
    g2 = t.generer(_modele("DEMO-61"))
    assert g2["ajout"] and g2["methodes_ajoutees"] == ["demo61VirementVersUnBeneficiaire"]
    t.ecrire(_modele("DEMO-61"), g2)
    c = projet.lire_fichier(chemin)
    assert "// retouché à la main" in c and c.count("@Test") == 2                        # rien de réécrit, méthode ajoutée
    assert t.generer(_modele("DEMO-61"))["methodes_ajoutees"] == []                       # rien à ajouter une seconde fois
    page = projet.lire_fichier("uiautomator/app/src/androidTest/java/ma/demo/tnr/pages/PageVirement.kt")
    assert page.count("val btnvirement") == 1


def test_socle_kotlin_absent(projet):
    from atelier.generation import technologies

    shutil.copytree(FIXTURES / "projet_robot", projet, dirs_exist_ok=True)
    with pytest.raises(ValueError, match="Socle Kotlin absent"):
        technologies.obtenir("uiautomator").generer(_modele())


SORTIE = """INSTRUMENTATION_STATUS: class=ma.demo.tnr.bdd.VirementBddTest
INSTRUMENTATION_STATUS: test=demo60VirementVersUnBeneficiaire
INSTRUMENTATION_STATUS_CODE: 1
INSTRUMENTATION_STATUS: class=ma.demo.tnr.bdd.VirementBddTest
INSTRUMENTATION_STATUS: test=demo60VirementVersUnBeneficiaire
INSTRUMENTATION_STATUS_CODE: 0
INSTRUMENTATION_STATUS: class=ma.demo.tnr.genere.LoginTest
INSTRUMENTATION_STATUS: test=tam_3226_afficher_l_ecran
INSTRUMENTATION_STATUS_CODE: 1
INSTRUMENTATION_STATUS: class=ma.demo.tnr.genere.LoginTest
INSTRUMENTATION_STATUS: stack=java.lang.AssertionError: Élément absent après 15 s : loginSubmitBtn
	at ma.demo.tnr.socle.Cible.exiger(Cible.kt:36)
INSTRUMENTATION_STATUS: test=tam_3226_afficher_l_ecran
INSTRUMENTATION_STATUS_CODE: -2
INSTRUMENTATION_STATUS: class=ma.demo.tnr.genere.LoginTest
INSTRUMENTATION_STATUS: test=tam_3228_sans_identifiants
INSTRUMENTATION_STATUS_CODE: 1
INSTRUMENTATION_STATUS: class=ma.demo.tnr.genere.LoginTest
INSTRUMENTATION_STATUS: test=tam_3228_sans_identifiants
INSTRUMENTATION_STATUS_CODE: -4
INSTRUMENTATION_RESULT: stream=
INSTRUMENTATION_CODE: -1
"""


def test_resultats_d_instrumentation_et_xray(kotlin, tmp_path):
    from atelier.execution import instrumentation
    from atelier.execution.journal_xray import Journal
    from atelier.generation import technologies

    t = technologies.obtenir("uiautomator")
    t.ecrire(_modele(), t.generer(_modele()))
    (kotlin / "uiautomator" / "app" / "src" / "androidTest" / "java" / "ma" / "demo" / "tnr" / "genere" / "LoginTest.kt").write_text(
        "package ma.demo.tnr.genere\nclass LoginTest {\n    fun tam_3226_afficher_l_ecran() {}\n    fun tam_3228_sans_identifiants() {}\n}\n", "utf-8")
    res = instrumentation.analyser_sortie(SORTIE)
    assert [(r["methode"], r["statut"]) for r in res] == [("demo60VirementVersUnBeneficiaire", "PASS"),
                                                          ("tam_3226_afficher_l_ecran", "FAIL"), ("tam_3228_sans_identifiants", "SKIP")]
    assert res[1]["message"].startswith("java.lang.AssertionError: Élément absent")
    cles = instrumentation.cles_xray("uiautomator")
    assert cles["ma.demo.tnr.bdd.VirementBddTest#demo60VirementVersUnBeneficiaire"] == "DEMO-60"   # @Xray
    assert cles["ma.demo.tnr.genere.LoginTest#tam_3226_afficher_l_ecran"] == "TAM-3226"             # test porté
    n = instrumentation.journaliser_xray(res, cles, tmp_path / "outbox", {"ticket": "TAM-5068", "exec_summary": "TNR"})
    ev = Journal(tmp_path / "outbox").evenements()
    assert n == 3 and [e["type"] for e in ev] == ["preparation"] + ["test_debut", "test_fin"] * 3
    fin = {e["donnees"]["cle_xray"]: e["donnees"] for e in ev if e["type"] == "test_fin"}
    assert fin["DEMO-60"]["statut"] == "PASSED" and fin["TAM-3226"]["statut"] == "FAILED" and fin["TAM-3228"]["statut"] == "TO DO"
    assert "Élément absent" in fin["TAM-3226"]["commentaire"]


def test_lancement_simule_et_refus_d_installation(kotlin):
    from atelier.execution import instrumentation

    appels = []

    def lanceur(cmd, cwd=None, delai=0):
        appels.append(cmd)
        if "install" in cmd:
            return 1, "Performing Streamed Install\nadb: failed to install x.apk: Failure [INSTALL_FAILED_USER_RESTRICTED: Install canceled by user]"
        if "instrument" in cmd:
            return 0, SORTIE
        return 0, "BUILD SUCCESSFUL"

    r = instrumentation.lancer("uiautomator", "16f4f7c3", [], lanceur=lanceur)
    assert not r["ok"] and r["etape"] == "installation" and "Installer via USB" in r["message"]
    r = instrumentation.lancer("uiautomator", "16f4f7c3", ["ma.demo.tnr.bdd.VirementBddTest"], jdd={"VIREMENT_STANDARD": {"montant": "1"}},
                               extra={"mot_de_passe": "secret-ne-pas-journaliser"}, construire_avant=False, lanceur=lanceur)
    assert (r["passes"], r["echecs"], r["ignores"]) == (1, 1, 1) and not r["ok"]
    assert "secret-ne-pas-journaliser" not in r["commande"] and "mot_de_passe ***" in r["commande"]
    assert "jdd.VIREMENT_STANDARD.montant 1" in r["commande"] and appels[-1][-1] == "ma.demo.tnr.test/androidx.test.runner.AndroidJUnitRunner"
    assert instrumentation.appareil(lambda c, cwd=None, delai=0: (0, "List of devices attached\nemulator-5554\tdevice\n")) == "emulator-5554"


def test_outils_mcp_kotlin(kotlin):
    from atelier.adapters import facade

    _modele()
    g = facade.studio_generer_depuis_bdd("DEMO-60", ecrire=True, technologie="uiautomator")
    assert g["ecrit"] and g["technologie"] == "uiautomator" and "structure" not in g        # pas de contrôle de structure Robot
    impl = facade.perimetre_automatisation("parcours", "PU-virement")["tests"][0]["implementations"]
    assert list(impl) == ["uiautomator"] and json.dumps(impl).count("VirementBddTest.kt") == 1


TRADUCTEUR = '''import sys
from pathlib import Path
D = Path(sys.argv[1])
g = D / "uiautomator" / "app" / "src" / "androidTest" / "java" / "ma" / "demo" / "tnr" / "genere"
g.mkdir(parents=True, exist_ok=True)
(g / "Mc_page.kt").write_text("""fun k_complet(vararg a: Any?): Any? = null
fun k_attente(vararg a: Any?): Any? {
    R.nonTraduit("condition monotonic")
    return null
}
fun k_parent(vararg a: Any?): Any? { k_attente(); return null }
""", "utf-8")
(g / "LoginTest.kt").write_text("""class LoginTest {
    fun tam_1_ok() { k_complet() }
    fun tam_2_via_keyword() { k_parent() }
    fun tam_3_direct() { R.nonTraduit("expression Python") }
}
""", "utf-8")
(D / "uiautomator" / "A_TRADUIRE.md").write_text(chr(10).join(["# Ce qui reste", "", "Instructions traduites : 90 · non traduites : 10 (90 %)."]), "utf-8")
'''


def test_porter_le_patrimoine_robot(kotlin):
    """Le traducteur du projet Kotlin est lancé ; le bilan suit les keywords appelés (un manque dans un keyword commun
    rend incomplets tous les tests qui l'appellent)."""
    from atelier.generation import portage

    (kotlin / "uiautomator" / "outils").mkdir()
    (kotlin / "uiautomator" / "outils" / "robot2kotlin.py").write_text(TRADUCTEUR, "utf-8")
    r = portage.porter()
    assert r["ok"] and (r["instructions_traduites"], r["non_traduites"], r["taux"]) == (90, 10, 90.0)
    assert (r["tests"], r["tests_complets"]) == (3, 1)
    t = {x["cle"]: x for x in r["a_traduire"]}
    assert t["TAM-2"]["non_traduits"] == 1 and t["TAM-2"]["exemples"] == ["condition monotonic"]   # via k_parent -> k_attente
    assert t["TAM-3"]["exemples"] == ["expression Python"] and "TAM-1" not in t


def test_classe_native_gardee_dans_la_carte(projet):
    from atelier.discovery import carte

    carte.creer_app("Banque Démo", ["android"])
    e = carte.observer([{"key": "btn_valider", "type": "bouton", "libelle": "Valider", "classe": "Button",
                         "locators": ["id=com.demo:id/btnValider"]}], "android")
    assert carte.ecran(e["id"])["elements"]["btn_valider"]["classes"] == {"android": "Button"}


def test_espresso_genere_dans_le_projet_de_tests(kotlin):
    """Espresso : même plan, sélecteurs Espresso (identifiant résolu à l'exécution, sans la classe R de l'application),
    tests écrits dans le projet de tests (espresso/), exécution refusée sans projet Gradle qui inclut l'application."""
    from atelier.adapters import facade
    from atelier.discovery import carte
    from atelier.generation import technologies

    carte.creer_app("Banque Démo", ["android"], android={"app_package": "com.demo.banque.dev"})
    m = _modele()
    m["scenarios"][0]["etapes"][2]["locator"] = "testTagCompose"                    # testTag Compose : pas d'onView
    m["scenarios"][0]["etapes"][2]["element"] = None
    t = technologies.obtenir("espresso")
    g = t.generer(m)
    c = g["contenu"]
    assert g["chemin"] == "espresso/src/androidTest/java/com/demo/banque/tnr/VirementEspressoTest.kt"
    assert "package com.demo.banque.tnr" in c and '@Xray("DEMO-60")' in c and "ActivityScenario.launch<Activity>" in c
    assert 'onView(Vue.id("editTextInput")).perform(replaceText(Vue.donnee("VIREMENT_STANDARD", "montant")), closeSoftKeyboard())' in c
    assert 'onView(withContentDescription("Récapitulatif")).check(matches(withText(containsString("100"))))' in c
    assert 'if (Vue.otpMode() != "validation") return' in c and "je touche le bouton virement" in g["a_implementer"]
    assert "getIdentifier(nom, \"id\", ctx.packageName)" in g["socle"][0]["contenu"]
    t.ecrire(m, g)
    with pytest.raises(ValueError, match="code source de l'application"):
        facade.run_tests(["com.demo.banque.tnr.VirementEspressoTest"], technologie="espresso")
