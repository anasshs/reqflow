"""Construction BDD : graphe d'étapes synchronisé avec le .feature, contrôles, génération Robot."""
from __future__ import annotations

import os
import shutil
import time

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


def test_parser_et_serialiser_aller_retour():
    from atelier.generation import bdd

    m = bdd.parser(GHERKIN)
    assert m["langue"] == "fr" and m["feature"] == "Virement entre comptes"
    sc = m["scenarios"][0]
    assert [e["type"] for e in sc["etapes"]] == ["given", "when", "and", "then"]
    assert [e["assertion"] for e in sc["etapes"]] == [False, False, False, True]
    m2 = bdd.parser(bdd.serialiser(m))
    assert [(e["type"], e["texte"]) for e in m2["scenarios"][0]["etapes"]] == \
        [(e["type"], e["texte"]) for e in sc["etapes"]]


def test_anglais_et_branches():
    from atelier.generation import bdd

    m = bdd.parser("Feature: F\n  Scenario: A\n    Given x\n    When y\n    Then z\n\n  @negatif\n  Scenario: B\n"
                   "    Given x\n    Then erreur\n")
    assert [s["type"] for s in m["scenarios"]] == ["principal", "negatif"]
    assert "@negatif" in bdd.serialiser(m)


def test_creation_depuis_etapes_manuelles_xray(projet):
    from atelier.generation import bdd

    m = bdd.creer("DEMO-1", depuis_xray={"resume": "Virement nominal", "etapes": [
        {"action": "Ouvrir les virements", "result": ""}, {"action": "Saisir le montant", "result": "Le récapitulatif s'affiche"}]})
    assert [e["type"] for e in m["scenarios"][0]["etapes"]] == ["given", "when", "then"]
    assert (projet / "bdd" / "DEMO-1.feature").read_text("utf-8").startswith("# language: fr")
    with pytest.raises(FileExistsError):
        bdd.creer("DEMO-1")


def test_edition_synchronise_le_feature(projet):
    from atelier.generation import bdd

    m = bdd.creer("DEMO-2", depuis_xray={"gherkin": GHERKIN})
    sc = m["scenarios"][0]
    e2 = sc["etapes"][1]["id"]
    m = bdd.modifier_etape("DEMO-2", e2, ecran="ecran:virement_saisie", valide=True)
    m = bdd.ajouter_etape("DEMO-2", sc["id"], "Et", "les informations sont correctes", apres=sc["etapes"][-1]["id"])
    m = bdd.ajouter_branche("DEMO-2", e2, "Montant refusé", "negatif", [{"mot": "Alors", "texte": "un message d'erreur s'affiche"}])
    feat = (projet / "bdd" / "DEMO-2.feature").read_text("utf-8")
    assert "Et les informations sont correctes" in feat and "@negatif @depuis:" in feat
    assert bdd.statistiques(m) == {"etapes": 5, "branches": 1, "assertions": 3, "etapes_validees": 2,
                                   "etapes_total": 8, "ecrans_relies": 2}


def test_feature_edite_a_la_main_relu_avec_les_liens(projet):
    from atelier.generation import bdd

    m = bdd.creer("DEMO-3", depuis_xray={"gherkin": GHERKIN})
    eid = m["scenarios"][0]["etapes"][1]["id"]
    bdd.modifier_etape("DEMO-3", eid, ecran="ecran:virement_saisie")
    f = projet / "bdd" / "DEMO-3.feature"
    time.sleep(0.01)
    f.write_text(f.read_text("utf-8").replace("Alors le récapitulatif s'affiche", "Alors le récapitulatif est affiché"), "utf-8")
    future = time.time() + 5
    os.utime(f, (future, future))
    m = bdd.charger("DEMO-3")
    textes = [e["texte"] for e in m["scenarios"][0]["etapes"]]
    assert "le récapitulatif est affiché" in textes
    assert m["scenarios"][0]["etapes"][1]["ecran"] == "ecran:virement_saisie"   # lien conservé


def test_controles_qualite(projet):
    from atelier.generation import bdd

    m = bdd.creer("DEMO-4", depuis_xray={"gherkin": "Feature: F\n  Scenario: S\n    Given je suis connecté\n"
                                                    "    When je saisis 1 500 MAD\n"})
    codes = {c["code"]: c for c in bdd.controles(m)}
    assert codes["assertion_manquante"]["gravite"] == "haute"
    assert codes["donnee_litterale"]["gravite"] == "moyenne"
    assert {"ecran_non_relie", "branche_negative", "jdd_absent", "non_valide"} <= set(codes)
    with pytest.raises(ValueError):
        bdd.valider("DEMO-4")


def test_validation(projet):
    from atelier.generation import bdd

    m = bdd.creer("DEMO-5", depuis_xray={"gherkin": GHERKIN}, jdd="VIREMENT_STANDARD")
    m = bdd.valider("DEMO-5")
    assert m["statut"] == "validé" and bdd.charger("DEMO-5")["statut"] == "validé"
    eid = m["scenarios"][0]["etapes"][0]["id"]
    m = bdd.modifier_etape("DEMO-5", eid, texte="Se Connecter Avec Biométrie")
    assert m["statut"] == "brouillon"   # un texte modifié est à revalider


def test_retouche_du_texte_garde_module_et_parcours(projet):
    """Retoucher le Gherkin (ex. ajouter un tag) garde ce que le texte ne porte pas : module, parcours, jeu de données."""
    from atelier.generation import bdd

    bdd.creer("DEMO-17", depuis_xray={"gherkin": GHERKIN}, jdd="VIREMENT_STANDARD")
    bdd.associer_module("DEMO-17", "Virements")
    m = bdd.charger("DEMO-17")
    m["parcours"] = "parcours:virement"
    bdd.sauver(m)
    m = bdd.depuis_texte("DEMO-17", GHERKIN.replace("  Scénario:", "  @e2e\n  Scénario:"))
    assert (m["module"], m["parcours"], m["jdd"]) == ("Virements", "parcours:virement", "VIREMENT_STANDARD")
    assert m["scenarios"][0]["tags"] == ["e2e"]


def test_generation_robot_reprend_les_tags_fonctionnels(depot):
    """Les tags du Gherkin (e2e, consomme_donnee…) passent en [Tags] après la clé ; un tag de provenance (discovery), non."""
    from atelier.generation import bdd

    texte = GHERKIN.replace("  Scénario: Virement nominal", "  @discovery @e2e @consomme_donnee\n  Scénario: Virement nominal")
    m = bdd.creer("DEMO-16", depuis_xray={"gherkin": "@smoke\n" + texte}, jdd="VIREMENT_STANDARD")
    g = bdd.generer_robot(m)
    assert "    [Tags]    DEMO-16    smoke    e2e    consomme_donnee\n" in g["contenu"]
    assert "discovery" not in g["contenu"]


def test_generation_robot_reutilise_le_socle(depot):
    from atelier.generation import bdd

    m = bdd.creer("DEMO-6", depuis_xray={"gherkin": GHERKIN}, jdd="VIREMENT_STANDARD")
    g = bdd.generer_robot(m)
    assert g["keywords_reutilises"] == ["Saisir Le Montant", "Se Connecter", "Valider Le Virement"]
    assert g["keywords_a_creer"] == ["le récapitulatif s'affiche"]
    assert g["chemin"] == "tests/application/sans_module/virement_entre_comptes.robot"  # tests/{application}/{module}/
    assert "Resource    ../../../resources/socle/commun.resource" in g["contenu"]  # import relatif depuis le dossier du module
    assert "    Initialiser Le Test    &{JDD_VIREMENT_STANDARD}" in g["contenu"]
    assert "    Given Se Connecter" in g["contenu"] and "[Tags]    DEMO-6" in g["contenu"]
    # la suite générée est valide pour Robot (dry run)
    (depot / g["chemin"]).parent.mkdir(parents=True, exist_ok=True)
    (depot / g["chemin"]).write_text(g["contenu"], "utf-8")
    # Page Object Model : aucun keyword dans la suite ; le keyword à créer est dans la page de son écran, importée
    assert "*** Keywords ***" not in g["contenu"]
    from atelier.generation import pom

    assert [p["keywords"] for p in g["pages"]] == [["le récapitulatif s'affiche"]]
    assert g["pages"][0]["chemin"].startswith("resources/pages/") and "Fail    Keyword à implémenter" in g["pages"][0]["contenu"]
    assert pom.ecrire(g["pages"]) == [g["pages"][0]["chemin"]]
    import server

    bilan = server.run_robot(g["chemin"], dry_run=True)
    assert bilan["code_retour"] == 0, bilan["console_fin"]


@pytest.mark.parametrize("texte,litteral", [
    ("un message d'erreur s'affiche", False), ("je saisis 1 500 MAD", True), ('je saisis "Jean"', True),
    ("je choisis « Compte courant »", True), ("l'opération est refusée", False)])
def test_donnee_litterale_et_apostrophes(texte, litteral):
    from atelier.generation import bdd

    assert bool(bdd.LITTERAL.search(texte)) is litteral
