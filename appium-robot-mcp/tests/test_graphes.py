"""Espaces de travail (MVP) : Knowledge Graph, Coverage Graph, Automation Flow Graph, analyse d'impact,
connaissance déclarée et historisée. Données : application fictive (tests/fixtures)."""
from __future__ import annotations

import shutil

import pytest

from conftest import FIXTURES, lire_fixture

pytest.importorskip("robot")

BOUTON_ANDROID = "locator:virement_saisie.bouton_valider@android"


@pytest.fixture
def depot(projet):
    shutil.copytree(FIXTURES / "projet_robot", projet, dirs_exist_ok=True)
    (projet / "patrimoine").mkdir()
    shutil.copy(FIXTURES / "xray" / "patrimoine.json", projet / "patrimoine" / "xray.json")
    return projet


@pytest.fixture
def avec_carte(depot):
    """Carte : écran virement_saisie (module Virements) observé sur Android."""
    import server
    from atelier.discovery import carte

    carte.creer_app("Banque Démo", ["android", "ios"])
    els = server._parse_elements(lire_fixture("hierarchies", "android_classique.xml"), "android")
    obs = carte.observer(els, "android", test_key="DEMO-1")
    carte.renommer(obs["id"], "virement_saisie", "Virements")
    return depot


def _graphe():
    from atelier.discovery import connaissance

    return connaissance.construire()


# --------------------------------------------------------------------------- Knowledge Graph
def test_graphe_assemble_toutes_les_sources(avec_carte):
    g = _graphe()
    types = {n.type for n in g.noeuds.values()}
    assert {"application", "plateforme", "module", "ecran", "locator", "keyword", "resource", "suite",
            "test_robot", "jdd", "requete", "bibliotheque", "epic", "user_story", "test", "test_plan"} <= types
    assert g.relations.get(f"test:DEMO-1|implemente_par|test_robot:tests/virement.robot::Virement Nominal")
    assert g.relations.get("user_story:DEMO-101|teste_par|test:DEMO-1")
    assert g.relations.get("epic:DEMO-100|contient|user_story:DEMO-101")
    assert g.relations.get("jdd:VIREMENT_STANDARD|depend_de|requete:compte_avec_solde")
    assert g.relations.get("module:Virements|contient|ecran:virement_saisie")
    assert g.relations.get("ecran:virement_saisie|teste_par|test:DEMO-1")  # cartographie TNR
    loc = g.noeuds[BOUTON_ANDROID]
    assert loc.proprietes["valeur"] == "id=com.exemple.banque:id/valider"
    assert loc.proprietes["secours"] == ["accessibility_id=Valider le virement", "xpath=//*[@text='Valider']"]
    assert loc.proprietes["fiabilite"] == "robuste"


def test_automatisation_definie_par_les_tags(depot):
    g = _graphe()
    assert g.noeuds["test:DEMO-1"].proprietes["automatise"] is True
    assert g.noeuds["test:DEMO-4"].proprietes["automatise"] is False


def test_anomalies_visibles(depot):
    (depot / "tests" / "casse.robot").write_text(
        "*** Settings ***\nResource    ../resources/socle/commun.resource\n\n*** Test Cases ***\nCasse\n"
        "    Initialiser Le Test    &{JDD_INEXISTANT}\n    Click Element    ${LOC_LOGIN_ANDROID.bouton_fantome}\n",
        "utf-8")
    g = _graphe()
    assert g.noeuds["locator:login.bouton_fantome@?"].proprietes["non_defini"] is True
    assert g.noeuds["jdd:INEXISTANT"].proprietes["non_defini"] is True


def test_filtres_et_voisinage(depot):
    g = _graphe()
    assert {n.categorie for n in g.filtrer(categories=["JIRA"]).noeuds.values()} == {"JIRA"}
    assert set(g.filtrer(recherche="montant").noeuds) >= {"keyword:saisirlemontant"}
    v = g.voisinage(["keyword:validerlevirement"], 1)
    assert {"keyword:cliquersur", BOUTON_ANDROID, "test_robot:tests/virement.robot::Virement Nominal"} <= set(v.noeuds)


# --------------------------------------------------------------------------- analyse d'impact
def test_impact_d_un_locator(avec_carte):
    from atelier.discovery import connaissance

    imp = connaissance.analyser_impact(_graphe(), BOUTON_ANDROID)
    assert [t["nom"] for t in imp["tests_robot"]] == ["Virement Nominal"]
    assert [t["id"] for t in imp["tests_xray"]] == ["test:DEMO-1"]
    assert [k["nom"] for k in imp["keywords"]] == ["Valider Le Virement"]
    assert imp["plateformes"] == ["android"]
    assert imp["modules"] == ["Virements"]
    assert imp["tnr"] == {"possible": True, "target": "tests/virement.robot", "include_tags": ["DEMO-1"],
                          "tests_sans_cle_xray": [], "explication": imp["tnr"]["explication"]}


def test_impact_d_un_keyword_partage(depot):
    from atelier.discovery import connaissance

    imp = connaissance.analyser_impact(_graphe(), "keyword:seconnecter")
    assert sorted(t["nom"] for t in imp["tests_robot"]) == ["Connexion Standard", "Virement Montant Nul",
                                                             "Virement Nominal"]
    assert imp["tnr"]["include_tags"] == ["DEMO-1", "DEMO-2", "DEMO-3"] and imp["tnr"]["target"] == "tests"
    assert sorted(imp["modules"]) == ["Connexion", "Virements"]


def test_impact_d_un_ecran_et_d_un_jdd(depot):
    from atelier.discovery import connaissance

    g = _graphe()
    assert {t["nom"] for t in connaissance.analyser_impact(g, "ecran:login")["tests_robot"]} == {
        "Connexion Standard", "Virement Montant Nul", "Virement Nominal"}
    assert {t["nom"] for t in connaissance.analyser_impact(g, "jdd:LOGIN_STANDARD")["tests_robot"]} == {
        "Connexion Standard"}
    assert {t["nom"] for t in connaissance.analyser_impact(g, "resource:resources/locators/virement_saisie.resource")
            ["tests_robot"]} == {"Virement Montant Nul", "Virement Nominal"}


# --------------------------------------------------------------------------- Coverage Graph
def test_indicateurs_de_couverture(depot):
    from atelier.intelligence import couverture, patrimoine_xray

    ind = couverture.indicateurs(_graphe(), patrimoine_xray.charger())
    assert ind["global"] == {"tests": 6, "automatises": 3, "manuels": 3, "couverture_automatisee": 0.5,
                             "exigences": 5, "exigences_couvertes": 4, "exigences_couvertes_auto": 4}
    modules = {m["module"]: m for m in ind["modules"]}
    assert modules["Virements"]["couverture_automatisee"] == 1.0
    assert modules["Connexion"]["couverture_automatisee"] == 0.5
    assert modules["Cartes"]["couverture_automatisee"] == 0.0
    assert [e["cle"] for e in ind["exigences_non_couvertes"]] == ["DEMO-102"]
    assert ind["redondances"] == [{"tests": ["DEMO-5", "DEMO-6"], "similarite": 1.0, "module": "Cartes"}]
    assert "test_automatise" in ind["definitions"]


def test_couverture_sans_instantane(projet):
    from atelier.intelligence import couverture

    ind = couverture.indicateurs(_graphe(), None)
    assert ind["disponible"] is False


def test_vue_couverture_filtres(depot):
    from atelier.intelligence import couverture

    g = _graphe()
    v = couverture.vue(g, module="Virements")
    assert {"test:DEMO-1", "test:DEMO-2", "user_story:DEMO-101", "epic:DEMO-100", "test_plan:DEMO-50"} <= set(v.noeuds)
    assert "test:DEMO-3" not in v.noeuds
    manuels = couverture.vue(g, afficher="manuels")
    assert {i for i, n in manuels.noeuds.items() if n.type == "test"} == {"test:DEMO-4", "test:DEMO-5", "test:DEMO-6"}


def test_candidats_sans_score_invente(depot):
    from atelier.intelligence import couverture, patrimoine_xray

    c = {x["cle"]: x for x in couverture.candidats(_graphe(), patrimoine_xray.charger())}
    assert c["DEMO-1"]["recommandation"] == "Déjà automatisé" and c["DEMO-1"]["score"] is None
    assert c["DEMO-6"]["recommandation"] == "À analyser" and "criticite" in c["DEMO-6"]["donnees_manquantes"]


def test_instantane_invalide_refuse(projet):
    from atelier.intelligence import patrimoine_xray

    with pytest.raises(ValueError):
        patrimoine_xray.enregistrer({"tests": [{"resume": "sans clé"}]}, "import")


# --------------------------------------------------------------------------- Automation Flow Graph
def test_flux_d_un_test(depot):
    from atelier.execution import flux

    v = flux.vue(_graphe(), "test:DEMO-1")
    attendus = {"test:DEMO-1", "test_robot:tests/virement.robot::Virement Nominal", "keyword:cliquersur",
                BOUTON_ANDROID, "locator:virement_saisie.bouton_valider@ios", "jdd:VIREMENT_STANDARD",
                "requete:compte_avec_solde", "resource:resources/socle/commun.resource",
                "resource:resources/locators/virement_saisie.resource", "suite:tests/virement.robot",
                "bibliotheque:AppiumLibrary", "plateforme:android", "plateforme:ios"}
    assert attendus <= set(v.noeuds)
    assert "test_robot:tests/connexion.robot::Connexion Standard" not in v.noeuds
    assert "test:DEMO-4" not in v.noeuds


def test_flux_complet_sans_tests_manuels(depot):
    from atelier.execution import flux

    v = flux.vue(_graphe())
    assert "test:DEMO-1" in v.noeuds and "test:DEMO-4" not in v.noeuds


# --------------------------------------------------------------------------- connaissance déclarée
def test_declarations_historisees(depot):
    from atelier.domain import declarations

    declarations.ajouter_noeud("regle:plafond", "regle", "Plafond de virement 10 000", "Règle métier")
    declarations.ajouter_relation("regle:plafond", "ecran:virement_saisie", "verifie")
    g = _graphe()
    assert g.noeuds["regle:plafond"].provenance == "déclaré"
    assert "regle:plafond|verifie|ecran:virement_saisie" in g.relations
    declarations.modifier_noeud("keyword:saisirlemontant", "validé", libelle="Saisir le montant du virement")
    assert _graphe().noeuds["keyword:saisirlemontant"].libelle == "Saisir le montant du virement"
    ops = [h["op"] for h in declarations.historique()]
    assert ops == ["modification_noeud", "ajout_relation", "ajout_noeud"]
    assert (depot / "connaissance" / "declarations.yaml").exists()


def test_masquer_un_element_observe_sans_toucher_la_source(depot):
    from atelier.domain import declarations

    declarations.supprimer_noeud("keyword:cliquersur", "validé")
    assert "keyword:cliquersur" not in _graphe().noeuds
    assert "Cliquer Sur" in (depot / "resources" / "socle" / "commun.resource").read_text("utf-8")


def test_fusion(depot):
    from atelier.domain import declarations

    declarations.ajouter_noeud("fonctionnalite:virement", "fonctionnalite", "Virement")
    declarations.ajouter_noeud("fonctionnalite:virements", "fonctionnalite", "Virements (doublon)")
    declarations.ajouter_relation("fonctionnalite:virements", "test:DEMO-1", "teste_par")
    declarations.fusionner("fonctionnalite:virements", "fonctionnalite:virement")
    g = _graphe()
    assert "fonctionnalite:virements" not in g.noeuds
    assert "fonctionnalite:virement|teste_par|test:DEMO-1" in g.relations


def test_ia_ne_propose_que_des_elements_a_valider(depot):
    from atelier.discovery import connaissance
    from atelier.domain import declarations

    with pytest.raises(PermissionError):
        declarations.modifier_noeud("keyword:saisirlemontant", "validé", auteur="ia", libelle="x")
    with pytest.raises(PermissionError):
        declarations.supprimer_noeud("keyword:saisirlemontant", "validé", auteur="ia")
    with pytest.raises(PermissionError):
        declarations.fusionner("a", "b", auteur="ia")
    # lien déduit par l'IA : visible, mais jamais utilisé par l'analyse d'impact avant validation
    r = declarations.ajouter_relation("test_robot:tests/connexion.robot::Connexion Standard",
                                      "keyword:validerlevirement", "appelle", auteur="ia")
    assert r["provenance"] == "déduit" and r["statut"] == "à valider"
    g = _graphe()
    assert r["id"] in g.relations
    noms = {t["nom"] for t in connaissance.analyser_impact(g, "keyword:validerlevirement")["tests_robot"]}
    assert "Connexion Standard" not in noms
    declarations.valider_relation(r["id"])
    noms = {t["nom"] for t in connaissance.analyser_impact(_graphe(), "keyword:validerlevirement")["tests_robot"]}
    assert "Connexion Standard" in noms


@pytest.mark.parametrize("type_noeud,type_rel", [("inconnu", "contient"), ("regle", "inconnue")])
def test_types_controles(depot, type_noeud, type_rel):
    from atelier.domain import declarations

    with pytest.raises(ValueError):
        if type_noeud == "inconnu":
            declarations.ajouter_noeud("x:1", type_noeud, "x")
        else:
            declarations.ajouter_relation("a", "b", type_rel)
