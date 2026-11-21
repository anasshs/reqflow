"""Refonte du Knowledge Graph, phase 1 : ontologie (trois univers), relations typées, provenance, migration sans perte.
Données : application fictive (tests/fixtures)."""
from __future__ import annotations

import shutil

import pytest

from conftest import FIXTURES, lire_fixture

pytest.importorskip("robot")


@pytest.fixture
def graphe(projet):
    """Graphe complet : dépôt Robot, instantané Xray, carte (écran virement_saisie du module Virements)."""
    import server
    from atelier.discovery import carte, connaissance

    shutil.copytree(FIXTURES / "projet_robot", projet, dirs_exist_ok=True)
    (projet / "patrimoine").mkdir()
    shutil.copy(FIXTURES / "xray" / "patrimoine.json", projet / "patrimoine" / "xray.json")
    carte.creer_app("Banque Démo", ["android", "ios"])
    els = server._parse_elements(lire_fixture("hierarchies", "android_classique.xml"), "android")
    obs = carte.observer(els, "android", test_key="DEMO-1")
    carte.renommer(obs["id"], "virement_saisie", "Virements")
    return connaissance.construire()


def _aretes(pg, relation):
    return {(e["source_node_id"], e["target_node_id"]): e for e in pg["edges"] if e["relation_type"] == relation}


def test_vocabulaire_controle():
    from atelier.domain import ontologie as o

    # les relations de la spécification existent, et toute règle de migration vise une relation et des types connus
    for rel in ("PARENT_OF", "BELONGS_TO", "HAS_ACCEPTANCE_CRITERION", "VERIFIES", "COVERS", "MEMBER_OF", "INCLUDED_IN_PLAN",
                "EXECUTED_IN", "HAS_TEST_RUN", "HAS_PRECONDITION", "REALIZED_BY", "NAVIGATES_TO", "CONTAINS_COMPONENT",
                "USES_LOCATOR", "CALLS_API", "IMPLEMENTS_RULE", "PART_OF_JOURNEY", "AUTOMATED_BY", "USES_KEYWORD", "USES_TEST_DATA"):
        assert rel in o.RELATIONS and not o.RELATIONS[rel][2]
    for t in ("XrayTest", "XrayTestSet", "XrayTestPlan", "XrayTestExecution", "XrayTestRun", "XrayPrecondition"):
        assert o.TYPES_CIBLES[t][0] == "TESTING"  # objets Xray distincts
    for hist, de, vers, cible, *_ in o.REGLES:
        assert cible in o.RELATIONS
        assert all(t in o.TYPES_CIBLES for t in (de or ()) + (vers or ())), (hist, de, vers)
    assert {u for u, _, _ in o.TYPES_CIBLES.values()} == set(o.UNIVERS)


def test_migration_sans_perte_et_sans_relation_generique(graphe):
    from atelier.domain import ontologie

    r = ontologie.rapport_migration(graphe, "demo")
    c = r["controles"]
    assert c["sans_perte"] and c["identifiants_noeuds_uniques"] and c["identifiants_relations_uniques"]
    assert c["relations_generiques"] == 0 and c["propositions_doublant_une_officielle"] == 0
    assert r["avant"]["relations"] == r["apres"]["relations"] and r["avant"]["noeuds"] == r["apres"]["noeuds"]
    # « contient » n'est jamais converti en bloc : plusieurs relations métier selon la paire de types
    assert len(r["repartition"]["contient"]) >= 5 and "RELATED_TO" not in r["repartition"]["contient"]
    assert set(r["apres"]["univers"]) == {"BUSINESS", "TESTING", "APPLICATION"}


def test_relations_typees_sens_et_provenance(graphe):
    from atelier.domain import ontologie

    pg = ontologie.property_graph(graphe, "demo")
    noeuds = {n["id"]: n for n in pg["nodes"]}
    # identifiants externes conservés, système d'origine et projet sur chaque nœud
    t, us = noeuds["xray:DEMO-1"], noeuds["jira:DEMO-101"]
    assert t["type"] == "XrayTest" and t["external_id"] == "DEMO-1" and t["source_system"] == "XRAY" and t["project_id"] == "demo"
    assert us["type"] == "JiraStory" and us["source_system"] == "JIRA" and us["legacy"] == {"id": "user_story:DEMO-101", "type": "user_story"}
    assert noeuds["jira:DEMO-100"]["type"] == "JiraEpic" and noeuds["xray:DEMO-50"]["type"] == "XrayTestPlan"
    assert noeuds["ecran:virement_saisie"]["type"] == "Screen" and noeuds["ecran:virement_saisie"]["universe"] == "APPLICATION"
    assert noeuds["module:Virements"]["type"] == "BusinessModule" and noeuds["module:Virements"]["universe"] == "BUSINESS"
    # un test VÉRIFIE une exigence (sens inversé par rapport à « testé par »), relation officielle Xray
    v = _aretes(pg, "VERIFIES")[("xray:DEMO-1", "jira:DEMO-101")]
    assert v["source_system"] == "XRAY" and v["validation_status"] == "OFFICIAL" and v["confidence"] == 1.0
    assert v["legacy"] == {"id": "user_story:DEMO-101|teste_par|test:DEMO-1", "type": "teste_par", "inverse": True}
    # un Test Plan ne vérifie pas une story : il contient des tests planifiés
    assert ("xray:DEMO-1", "xray:DEMO-50") in _aretes(pg, "INCLUDED_IN_PLAN")
    assert not any("xray:DEMO-50" in k for k in _aretes(pg, "VERIFIES"))
    assert ("jira:DEMO-100", "jira:DEMO-101") in _aretes(pg, "PARENT_OF")
    assert _aretes(pg, "PARENT_OF")[("jira:DEMO-100", "jira:DEMO-101")]["source_system"] == "JIRA"
    assert ("xray:DEMO-1", "test_robot:tests/virement.robot::Virement Nominal") in _aretes(pg, "AUTOMATED_BY")
    assert ("ecran:virement_saisie", "module:Virements") in _aretes(pg, "BELONGS_TO")
    # carte TNR : le test couvre l'écran (observé à l'exécution), ce n'est pas une vérification d'exigence
    tnr = _aretes(pg, "COVERS")[("xray:DEMO-1", "ecran:virement_saisie")]
    assert tnr["source_system"] == "EXECUTION_CENTER"
    # champs obligatoires de la spécification présents sur chaque arête
    champs = {"id", "source_node_id", "target_node_id", "relation_type", "source_system", "source_reference", "confidence",
              "validation_status", "project_id", "created_at", "updated_at", "last_observed_at"}
    assert all(champs <= set(e) for e in pg["edges"])
    assert all(e["source_node_id"] in noeuds and e["target_node_id"] in noeuds for e in pg["edges"])
    assert all(e["source_system"] in ontologie.SYSTEMES and e["validation_status"] in ontologie.STATUTS for e in pg["edges"])


def test_proposition_jamais_officielle_ni_confiance_inventee(graphe):
    from atelier.domain import ontologie
    from atelier.domain.graphe import Relation

    # une relation proposée par l'IA (lien exigence → écran) : PROPOSED, source AI_INFERENCE, pas de confiance inventée
    graphe.relier("user_story:DEMO-101", "ecran:virement_saisie", "impacte", provenance="déduit", statut="à valider", source="Cursor (MCP)")
    pg = ontologie.property_graph(graphe, "demo")
    p = _aretes(pg, "REALIZED_BY")[("jira:DEMO-101", "ecran:virement_saisie")]
    assert p["validation_status"] == "PROPOSED" and p["source_system"] == "AI_INFERENCE" and p["confidence"] is None
    # confiance fournie par le calcul : reprise telle quelle ; validée par un humain : VALIDATED, jamais OFFICIAL
    r = Relation("user_story:DEMO-101", "ecran:virement_saisie", "impacte", provenance="déduit", statut="à valider", proprietes={"confiance": 0.87})
    assert ontologie.metier(r, graphe)["confidence"] == 0.87
    r.statut = "validé"
    m = ontologie.metier(r, graphe)
    assert m["validation_status"] == "VALIDATED" and m["source_system"] == "AI_INFERENCE"
    # une déclaration humaine est validée, sans devenir une donnée officielle du référentiel
    assert ontologie.statut_validation("déclaré", "validé") == "VALIDATED" and ontologie.statut_validation("observé", "validé") == "OFFICIAL"


def test_feature_jira_et_fonctionnalite_metier_distinctes():
    from atelier.domain import ontologie
    from atelier.domain.graphe import Graphe

    g = Graphe()
    f = g.noeud("epic:SQ-1", "epic", "SQ-1 Paiements", source="instantané Xray (2026-11-16)", proprietes={"cle": "SQ-1", "type_jira": "Feature"})
    j = g.noeud("fonctionnalite:SQ-2", "fonctionnalite", "SQ-2 Virement", source="exigences Jira (2026-11-16)", proprietes={"cle": "SQ-2"})
    m = g.noeud("fonctionnalite:virement_interne", "fonctionnalite", "Virement interne", provenance="déduit", statut="à valider", source="Cursor (MCP)")
    st = g.noeud("user_story:SQ-3", "user_story", "SQ-3 Sous-tâche", source="instantané Xray", proprietes={"cle": "SQ-3", "type_jira": "Sous-tâche"})
    assert [ontologie.type_cible(n, g) for n in (f, j, m, st)] == ["JiraFeature", "JiraFeature", "BusinessFeature", "JiraRequirement"]
    assert ontologie.id_cible(f, "JiraFeature") == "jira:SQ-1" and ontologie.id_cible(m, "BusinessFeature") == "fonctionnalite:virement_interne"
    # une paire inconnue reste visible (relation générique « à confirmer »), jamais perdue ni typée au hasard
    g.relier(m.id, st.id, "contient", provenance="déclaré")
    r = ontologie.rapport_migration(g, "x")
    assert r["controles"]["relations_generiques"] == 1 and r["a_confirmer"][0]["relation"] == "RELATED_TO"


def test_services_et_api_exposent_les_relations_typees(graphe):
    from atelier.discovery import espaces

    d = espaces.detail("test:DEMO-1")
    assert d["noeud"]["metier"]["type"] == "XrayTest" and d["noeud"]["metier"]["id"] == "xray:DEMO-1"
    verifie = next(x for x in d["entrants"] if x["noeud"]["id"] == "user_story:DEMO-101")
    assert verifie["relation"]["metier"]["type"] == "VERIFIES" and verifie["relation"]["metier"]["inverse"] is True
    v = espaces.vue_couverture(module="Virements")
    assert all("metier" in r for r in v["relations"]) and all("metier" in n for n in v["noeuds"])
    o = espaces.ontologie_cible()
    assert {"VERIFIES", "INCLUDED_IN_PLAN", "MEMBER_OF"} <= {r["type"] for r in o["relations"]} and o["univers"] == ["BUSINESS", "TESTING", "APPLICATION"]
    m = espaces.rapport_migration()
    assert m["controles"]["sans_perte"] and m["projet"]
