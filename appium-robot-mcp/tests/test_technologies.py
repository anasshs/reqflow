"""Technologies d'automatisation (phase B, docs/AUTOMATISATION_MULTI_CIBLES.md) : registre, plan neutre, et génération
Robot passée par une technologie SANS changement de sortie."""
from __future__ import annotations

import shutil

import pytest

from conftest import FIXTURES

GHERKIN = """# language: fr
Fonctionnalité: Virement entre comptes
  Scénario: Virement nominal
    Étant donné Se Connecter
    Quand Saisir Le Montant
    Et Valider Le Virement
    Alors le récapitulatif s'affiche
"""


@pytest.fixture
def depot(projet):
    shutil.copytree(FIXTURES / "projet_robot", projet, dirs_exist_ok=True)
    return projet


def _sans_meta(g: dict) -> dict:
    return {k: v for k, v in g.items() if k not in ("technologie", "type_app")}


def test_technologie_par_defaut_genere_le_meme_robot(depot):
    """La technologie déduite de l'application produit exactement la sortie historique de generer_robot."""
    from atelier.generation import bdd, technologies

    m = bdd.creer("DEMO-6", depuis_xray={"gherkin": GHERKIN}, jdd="VIREMENT_STANDARD")
    m["scenarios"][0]["etapes"][3]["locator"] = "id=com.demo:id/recap"
    historique = bdd.generer_robot(m)
    t = technologies.obtenir(technologies.par_defaut())
    g = t.generer(m)
    assert g["technologie"] == t.nom
    assert _sans_meta(g) == historique                                  # suite, pages, locators, imports : identiques


def test_la_technologie_impose_la_bibliotheque(depot):
    from atelier.generation import bdd, technologies

    m = bdd.creer("DEMO-7", depuis_xray={"gherkin": GHERKIN}, jdd="VIREMENT_STANDARD")
    m["scenarios"][0]["etapes"][3]["locator"] = "id=com.demo:id/recap"
    pages = lambda nom: "\n".join(p["contenu"] for p in technologies.obtenir(nom).generer(m)["pages"])  # noqa: E731
    assert "Wait Until Element Is Visible" in pages("robot-appium")     # AppiumLibrary
    assert "Wait For Elements State" in pages("robot-web")               # Browser
    assert "Wait Until Element Is Visible" in pages("robot-selenium") and "Wait For Elements State" not in pages("robot-selenium")
    g = technologies.obtenir("robot-appium").generer(m)
    assert g["type_app"] == "mobile" and g["contenu"] == bdd.generer_robot(m)["contenu"]  # la suite ne dépend pas de la bibliothèque


def test_registre_et_technologie_par_defaut():
    from atelier.generation import technologies

    noms = [t["nom"] for t in technologies.lister()]
    assert noms == ["robot-appium", "robot-web", "robot-selenium", "robot-api", "uiautomator", "espresso", "xcuitest"]
    assert {t["nom"]: t["disponible"] for t in technologies.lister()} == {
        "robot-appium": True, "robot-web": True, "robot-selenium": True, "robot-api": True, "uiautomator": True, "espresso": True,
        "xcuitest": True}
    with pytest.raises(KeyError):
        technologies.obtenir("cobol")
    assert technologies.par_defaut({"type": "mobile", "plateformes": ["android"]}) == "robot-appium"
    assert technologies.par_defaut({"type": "web"}) == "robot-web"
    assert technologies.par_defaut({"type": "mobile", "automatisation": {"technologie_defaut": "uiautomator"}}) == "uiautomator"


def test_plan_d_automatisation_neutre(projet):
    from atelier.generation import bdd, plan_automatisation

    m = bdd.parser("""# language: fr
Fonctionnalité: Virement
  Scénario: Virement vers un bénéficiaire
    Étant donné je suis connecté sur le tableau de bord
    Quand je touche le bouton virement
    Et je saisis le montant
    Et je renseigne mon mot de passe
    Et je saisis le code OTP reçu par SMS
    Et je reviens en arrière
    Alors le récapitulatif affiche le montant
""")
    m["cle"] = "DEMO-20"
    et = m["scenarios"][0]["etapes"]
    et[1]["locator"] = 'android=new UiSelector().resourceId("com.app:id/btnVirement")'
    et[2].update(jdd="montant", locator="id=${APP_ID}:id/editTextInput")
    et[3].update(jdd="mot_de_passe", locator="accessibility_id=Mot de passe")
    p = plan_automatisation.construire(m)
    e = p["scenarios"][0]["etapes"]
    assert [x["intention"] for x in e] == ["ouvrir", "toucher", "saisir", "saisir", "otp", "revenir", "verifier"]
    assert e[1]["element"] == {"resource_id": "btnVirement", "accessibility_id": "", "texte": ""}
    assert e[2]["element"]["resource_id"] == "editTextInput" and not e[2]["secret"]
    assert e[3]["secret"] and e[3]["element"]["accessibility_id"] == "Mot de passe"
    assert p["bilan"]["etapes"] == 7 and p["bilan"]["saisir"] == 2 and p["bilan"]["sans_element"] == 0
    assert "Click Element" not in str(p) and "Fill Text" not in str(p)   # aucune syntaxe de bibliothèque dans le plan


def test_outils_mcp(depot):
    from atelier.adapters import facade
    from atelier.generation import bdd

    bdd.creer("DEMO-8", depuis_xray={"gherkin": GHERKIN}, jdd="VIREMENT_STANDARD")
    assert any(t["defaut"] for t in facade.technologies_disponibles())
    assert facade.studio_plan_automatisation("DEMO-8")["scenarios"][0]["etapes"][0]["intention"] == "ouvrir"
    g = facade.studio_generer_depuis_bdd("DEMO-8", technologie="robot-appium")
    assert g["technologie"] == "robot-appium" and "[Tags]    DEMO-8" in g["contenu"]
    assert "technologie" not in facade.studio_generer_depuis_bdd("DEMO-8")   # sans technologie : sortie historique


GHERKIN_METIER = """# language: fr
Fonctionnalité: Virement entre comptes
  Scénario: Virement nominal
    Étant donné Se Connecter
    Quand Saisir Le Montant
    Et je valide mon virement vers le bénéficiaire
    Alors le récapitulatif s'affiche
"""


def test_reutiliser_sans_reecrire_garde_le_texte_xray(depot):
    """« Réutiliser sans réécrire » : l'étape garde son texte (le Gherkin de Xray ne change pas), le test Robot appelle le
    keyword existant, et l'écriture n'est plus bloquée par le doublon possible."""
    from atelier.generation import bdd, plan_automatisation

    m = bdd.creer("DEMO-30", depuis_xray={"gherkin": GHERKIN_METIER}, jdd="VIREMENT_STANDARD")
    eid = m["scenarios"][0]["etapes"][2]["id"]
    # formulation métier trop éloignée pour le rapprochement par mots : « à créer » alors que « Valider Le Virement » existe
    assert bdd.reutilisation(m)[eid]["statut"] == "à créer"
    assert "je valide mon virement vers le bénéficiaire" in bdd.generer_robot(m)["keywords_a_creer"]
    with pytest.raises(ValueError):
        bdd.modifier_etape("DEMO-30", eid, keyword_lie="Keyword Qui N Existe Pas")
    m = bdd.modifier_etape("DEMO-30", eid, keyword_lie="valider le virement")   # nom normalisé : retrouvé
    assert m["scenarios"][0]["etapes"][2]["texte"] == "je valide mon virement vers le bénéficiaire"
    assert "je valide mon virement vers le bénéficiaire" in (depot / "bdd" / "DEMO-30.feature").read_text("utf-8")
    r = bdd.reutilisation(m)[eid]
    assert r["statut"] == "existant" and r["lie"] and r["keyword"] == "Valider Le Virement"
    bdd.refuser_doublons(m)                                                     # plus de doublon à trancher
    g = bdd.generer_robot(m)
    assert "    # Xray : je valide mon virement vers le bénéficiaire\n    And Valider Le Virement\n" in g["contenu"]
    assert "Valider Le Virement" in g["keywords_reutilises"]
    assert "je valide mon virement vers le bénéficiaire" not in g["keywords_a_creer"]
    assert plan_automatisation.construire(m)["scenarios"][0]["etapes"][2]["reutilise"] == "Valider Le Virement"


def test_lien_retire_si_le_texte_change_et_lien_casse_signale(depot):
    from atelier.generation import bdd

    m = bdd.creer("DEMO-31", depuis_xray={"gherkin": GHERKIN_METIER}, jdd="VIREMENT_STANDARD")
    eid = m["scenarios"][0]["etapes"][2]["id"]
    m = bdd.modifier_etape("DEMO-31", eid, keyword_lie="Valider Le Virement", arguments_lies=["${JDD}[montant]"])
    g = bdd.generer_robot(m)
    assert "    And Valider Le Virement    ${JDD}[montant]\n" in g["contenu"]
    m["scenarios"][0]["etapes"][2]["keyword_lie"]["keyword"] = "Ancien Nom Supprimé"   # keyword renommé depuis
    assert any(c["code"] == "keyword_lie_absent" for c in bdd.controles(m))
    m = bdd.modifier_etape("DEMO-31", eid, texte="je valide autre chose")              # nouveau texte : lien retiré
    assert "keyword_lie" not in m["scenarios"][0]["etapes"][2]
    m = bdd.modifier_etape("DEMO-31", eid, keyword_lie="Valider Le Virement")
    m = bdd.modifier_etape("DEMO-31", eid, keyword_nouveau=True)                       # décisions exclusives
    assert "keyword_lie" not in m["scenarios"][0]["etapes"][2]


class _FauxXray:
    """Test Plan Xray simulé : 3 tests, dont un manuel sans BDD."""
    def gql(self, q, v=None):
        tests = [{"jira": {"key": "DEMO-40", "summary": "Virement"}, "testType": {"name": "Cucumber"}},
                 {"jira": {"key": "DEMO-41", "summary": "Consulter le solde"}, "testType": {"name": "Manual"}},
                 {"jira": {"key": "DEMO-42", "summary": "Paiement facture"}, "testType": {"name": "Cucumber"}}]
        return {"getTestPlans": {"results": [{"tests": {"total": 3, "results": tests}}] if "DEMO-500" in v["j"] else []}}


def test_points_d_entree_parcours_et_plan(depot):
    """Un parcours ou un Test Plan Xray se résout en tests : scénario BDD, implémentations existantes (Robot par tag,
    Kotlin par @Xray ou méthode tam_<n>_), « à concevoir » ; la demande est déposée dans la boîte pour le MCP."""
    from atelier.generation import bdd, perimetre
    from atelier.integrations import boite_cursor

    m = bdd.creer("DEMO-40", depuis_xray={"gherkin": GHERKIN}, jdd="VIREMENT_STANDARD")
    m["parcours"] = "PU-virement"
    bdd.sauver(m)
    kt = depot / "uiautomator" / "app" / "src" / "androidTest" / "java" / "VirementTest.kt"
    kt.parent.mkdir(parents=True)
    kt.write_text('class VirementTest {\n    @Test\n    fun demo_40_virement_nominal() {}\n}\n', "utf-8")
    p = perimetre.resoudre("parcours", "PU-virement")
    assert [t["cle"] for t in p["tests"]] == ["DEMO-40"] and p["tests"][0]["bdd"] == "DEMO-40"
    assert "uiautomator" in p["tests"][0]["implementations"] and p["bilan"]["kotlin"] == 1
    pl = perimetre.resoudre("plan", "demo-500", xray=_FauxXray())
    t = {x["cle"]: x for x in pl["tests"]}
    assert t["DEMO-40"]["bdd"] == "DEMO-40" and t["DEMO-41"]["a_concevoir"] and not t["DEMO-42"]["a_concevoir"]  # Gherkin dans Xray
    assert pl["bilan"] == {"tests": 3, "avec_bdd": 1, "a_concevoir": 1, "robot": 0, "kotlin": 1}
    with pytest.raises(KeyError):
        perimetre.resoudre("plan", "DEMO-999", xray=_FauxXray())
    with pytest.raises(ValueError):
        perimetre.resoudre("sprint", "S1")
    r = perimetre.automatiser("plan", "DEMO-500", "robot-appium", ["DEMO-40", "DEMO-41"], xray=_FauxXray(), mode="boite")
    assert r["tests"] == ["DEMO-40", "DEMO-41"] and r["a_concevoir"] == ["DEMO-41"] and r["mode"] == "boite"
    d = next(x for x in boite_cursor._lire() if x["id"] == r["demande"])
    assert 'technologie="robot-appium"' in d["texte"]
    assert "DEMO-40, DEMO-41" in d["texte"] and "ne publie rien dans Xray" in d["texte"]
    with pytest.raises(KeyError):
        perimetre.automatiser("plan", "DEMO-500", "cobol", xray=_FauxXray(), mode="boite")


def technologies_non_dispo():
    from atelier.generation import technologies

    return technologies.NonDisponible
