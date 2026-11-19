"""Ontologie du Knowledge Graph (refonte, phase 1) : trois univers — Business, Testing, Application — reliés par un
vocabulaire contrôlé de relations typées, avec une provenance sur chaque nœud et chaque relation.

Ce module ne change pas le graphe construit par les moteurs (types et relations « historiques » de graphe.py, que
tous les modules lisent encore) : il le TRADUIT, sans perte, vers le modèle cible :
  - type_cible()      type historique d'un nœud → type typé (JiraStory, XrayTest, Screen, BusinessModule…) ;
  - migrer_relation() relation historique → relation métier, selon la PAIRE de types reliés (jamais un « contient »
                      converti en bloc) ; le sens est inversé quand le sens métier l'exige (un test VÉRIFIE une
                      exigence, il n'est pas « testé par » elle) ;
  - property_graph()  export au format nœuds / arêtes indépendant du moteur de stockage (docs/REFONTE_KNOWLEDGE_GRAPH.md) ;
  - rapport_migration() cohérence avant / après : rien de perdu, identifiants uniques, paires à confirmer.

Règles tenues ici :
  - une relation lue dans Jira ou Xray est OFFICIAL et le reste ; une relation déduite (règles ou IA) est PROPOSED tant
    qu'un humain ne l'a pas validée, et ne remplace jamais une relation officielle ;
  - aucune confiance inventée : sans valeur calculée, « confidence » d'une proposition vaut None ;
  - les types et relations hors de la spécification sont marqués « extension » (visibles dans le rapport).
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter

from atelier.domain.graphe import Graphe, Noeud, Relation

UNIVERS = ("BUSINESS", "TESTING", "APPLICATION")
SYSTEMES = ("JIRA", "XRAY", "APPLICATION_DISCOVERY", "AI_INFERENCE", "AUTOMATION_STUDIO", "EXECUTION_CENTER",
            "USER_DECLARATION", "API_CONTRACT",  # extensions : saisie humaine, contrat OpenAPI
            "AUTOMATED_TEST", "CURSOR_VALIDATED")  # corrélation : preuve issue des tests, proposition d'une IA confirmée
STATUTS = ("OFFICIAL", "PROPOSED", "VALIDATED", "REJECTED", "OBSOLETE")

# type cible -> (univers, libellé, extension hors spécification)
TYPES_CIBLES = {
    # Business Graph
    "BusinessDomain": ("BUSINESS", "Domaine métier", False), "BusinessModule": ("BUSINESS", "Module", False),
    "BusinessFeature": ("BUSINESS", "Fonctionnalité", False), "BusinessSubFeature": ("BUSINESS", "Sous-fonctionnalité", False),
    "BusinessRule": ("BUSINESS", "Règle métier", False), "BusinessProcess": ("BUSINESS", "Processus métier", False),
    "UserJourney": ("BUSINESS", "Parcours utilisateur", False),
    "BusinessRole": ("BUSINESS", "Rôle", True), "BusinessEntity": ("BUSINESS", "Entité métier", True),
    # Testing Graph : Jira
    "JiraEpic": ("TESTING", "Epic Jira", False), "JiraFeature": ("TESTING", "Feature Jira", False),
    "JiraStory": ("TESTING", "Story Jira", False), "JiraRequirement": ("TESTING", "Exigence Jira", False),
    "AcceptanceCriterion": ("TESTING", "Critère d'acceptation", False), "JiraBug": ("TESTING", "Bug Jira", False),
    # Testing Graph : Xray (objets distincts, jamais fusionnés)
    "XrayTest": ("TESTING", "Test Xray", False), "XrayTestSet": ("TESTING", "Test Set Xray", False),
    "XrayTestPlan": ("TESTING", "Test Plan Xray", False), "XrayTestExecution": ("TESTING", "Test Execution Xray", False),
    "XrayTestRun": ("TESTING", "Test Run Xray", False), "XrayPrecondition": ("TESTING", "Précondition Xray", False),
    # Testing Graph : automatisation
    "BDDScenario": ("TESTING", "Scénario BDD", False), "AutomationScript": ("TESTING", "Script automatisé", False),
    "RobotSuite": ("TESTING", "Suite Robot", False), "Keyword": ("TESTING", "Keyword", False),
    "PageObject": ("TESTING", "Page Object", False), "TestDataSet": ("TESTING", "Jeu de données", False),
    "BDDFeature": ("TESTING", "Feature BDD", True), "BDDStep": ("TESTING", "Étape BDD", True),
    "AutomationResource": ("TESTING", "Resource Robot", True), "AutomationLibrary": ("TESTING", "Bibliothèque", True),
    "DataQuery": ("TESTING", "Requête de données", True), "DataVariable": ("TESTING", "Variable de données", True), "ExecutionResult": ("TESTING", "Résultat d'exécution", True),
    # Application Graph
    "Application": ("APPLICATION", "Application", False), "Screen": ("APPLICATION", "Écran", False),
    "ScreenState": ("APPLICATION", "État d'écran", False), "UIComponent": ("APPLICATION", "Composant", False),
    "UIAction": ("APPLICATION", "Action", False), "Locator": ("APPLICATION", "Locator", False),
    "APIEndpoint": ("APPLICATION", "Endpoint API", False), "APIRequest": ("APPLICATION", "Requête API", False),
    "APIResponse": ("APPLICATION", "Réponse API", False), "ObservedBehavior": ("APPLICATION", "Comportement observé", False),
    "DiscoveredJourney": ("APPLICATION", "Parcours découvert", False), "ApplicationRule": ("APPLICATION", "Règle observée", False),
    "Platform": ("APPLICATION", "Plateforme", True), "Environment": ("APPLICATION", "Environnement", True),
    "ApplicationVersion": ("APPLICATION", "Version", True),
}

# relation -> (famille, libellé lu de la source vers la cible, extension hors spécification)
RELATIONS = {
    # métier
    "PARENT_OF": ("métier", "Parent de", False), "BELONGS_TO": ("métier", "Appartient à", False),
    "HAS_FEATURE": ("métier", "A la fonctionnalité", False), "REFINES": ("métier", "Précise", False),
    "HAS_BUSINESS_RULE": ("métier", "A la règle métier", False), "HAS_JOURNEY": ("métier", "A le parcours", False),
    # Jira / Xray
    "HAS_ACCEPTANCE_CRITERION": ("jira_xray", "A le critère d'acceptation", False), "VERIFIES": ("jira_xray", "Vérifie", False),
    "COVERS": ("jira_xray", "Couvre", False), "MEMBER_OF": ("jira_xray", "Membre de", False),
    "INCLUDED_IN_PLAN": ("jira_xray", "Planifié dans", False), "EXECUTED_IN": ("jira_xray", "Exécuté dans", False),
    "HAS_TEST_RUN": ("jira_xray", "A le Test Run", False), "HAS_PRECONDITION": ("jira_xray", "A la précondition", False),
    "BLOCKS": ("jira_xray", "Bloque", False),
    # applicatives
    "REALIZED_BY": ("applicative", "Réalisé par", False), "NAVIGATES_TO": ("applicative", "Navigue vers", False),
    "CONTAINS_COMPONENT": ("applicative", "Contient le composant", False), "USES_LOCATOR": ("applicative", "Utilise le locator", False),
    "TRIGGERS": ("applicative", "Déclenche", False), "CALLS_API": ("applicative", "Appelle l'API", False),
    "IMPLEMENTS_RULE": ("applicative", "Applique la règle", False), "PART_OF_JOURNEY": ("applicative", "Fait partie du parcours", False),
    # automatisation
    "AUTOMATED_BY": ("automatisation", "Automatisé par", False), "IMPLEMENTS_SCENARIO": ("automatisation", "Implémente le scénario", False),
    "GENERATED_FROM": ("automatisation", "Généré depuis", False), "USES_KEYWORD": ("automatisation", "Utilise le keyword", False),
    "USES_PAGE_OBJECT": ("automatisation", "Utilise le Page Object", False), "USES_TEST_DATA": ("automatisation", "Utilise le jeu de données", False),
    # extensions : nécessaires pour ne perdre aucune relation existante, absentes de la spécification
    "RUNS_ON": ("extension", "Tourne sur", True), "HAS_VERSION": ("extension", "A la version", True),
    "HAS_MODULE": ("extension", "A le module", True), "HAS_SCREEN": ("extension", "A l'écran", True),
    "HAS_LOCATOR": ("extension", "A le locator", True), "HAS_ACTION": ("extension", "Propose l'action", True),
    "DEFINES": ("extension", "Définit", True), "IMPORTS": ("extension", "Importe", True),
    "USES_LIBRARY": ("extension", "Utilise la bibliothèque", True), "USES_COMPONENT": ("extension", "Agit sur le composant", True),
    "DEPENDS_ON": ("extension", "Dépend de", True), "IMPACTS": ("extension", "Impacte", True),
    "AFFECTS": ("extension", "Affecte", True), "DETECTED_BY": ("extension", "Détecté par", True),
    "RELATED_TO": ("extension", "Lié à", True),
    # preuve issue des tests : un test de l'exigence passe par l'écran (à ne pas confondre avec REALIZED_BY)
    "VERIFIED_ON": ("extension", "Vérifiée sur", True),
}

_CLE_JIRA = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?(?:[+-]\d{2}:\d{2}|Z)?)?")
_JIRA = ("JiraEpic", "JiraFeature", "JiraStory", "JiraRequirement", "JiraBug")
_XRAY = ("XrayTest", "XrayTestSet", "XrayTestPlan", "XrayTestExecution", "XrayTestRun", "XrayPrecondition")
_SIMPLES = {
    "application": "Application", "plateforme": "Platform", "environnement": "Environment", "version": "ApplicationVersion",
    "module": "BusinessModule", "regle": "BusinessRule", "role": "BusinessRole", "entite": "BusinessEntity",
    "ecran": "Screen", "action": "UIAction", "composant": "UIComponent", "locator": "Locator", "endpoint": "APIEndpoint",
    "keyword": "Keyword", "bibliotheque": "AutomationLibrary", "bug": "JiraBug",
    "test": "XrayTest", "test_plan": "XrayTestPlan", "test_set": "XrayTestSet", "test_execution": "XrayTestExecution",
    "feature": "BDDFeature", "scenario": "BDDScenario", "step": "BDDStep",
    "suite": "RobotSuite", "test_robot": "AutomationScript", "jdd": "TestDataSet", "requete": "DataQuery",
    "variable": "DataVariable", "resultat": "ExecutionResult",
}


def _cle(n: Noeud) -> str:
    return str(n.proprietes.get("cle") or n.id.split(":", 1)[-1])


def type_cible(n: Noeud, g: Graphe | None = None) -> str:
    """Type typé d'un nœud historique. Le type Jira d'origine (Feature, Story…) est respecté quand il est connu ;
    une « fonctionnalité » qui porte une clé Jira est une Feature Jira, pas un nœud métier fabriqué."""
    tj = str(n.proprietes.get("type_jira") or "").strip().lower()
    if n.type in ("epic", "user_story"):
        if tj == "feature":
            return "JiraFeature"
        if n.type == "epic":
            return "JiraEpic"
        return "JiraStory" if tj in ("", "story", "user story", "récit") else "JiraRequirement"
    if n.type == "fonctionnalite":
        return "JiraFeature" if _CLE_JIRA.match(_cle(n)) and "jira" in (n.source or "").lower() else "BusinessFeature"
    if n.type == "parcours":
        return "DiscoveredJourney" if n.provenance == "observé" else "UserJourney"
    if n.type == "resource":
        definit_locators = g is not None and any(r.type == "contient" and g.noeuds.get(r.vers) and g.noeuds[r.vers].type == "locator"
                                                 for r in g.sortants(n.id))
        return "PageObject" if definit_locators else "AutomationResource"
    return _SIMPLES.get(n.type, "BusinessEntity")


def id_cible(n: Noeud, t: str) -> str:
    """Identifiant stable : jira:<clé> et xray:<clé> pour les objets des référentiels, identifiant historique sinon."""
    if t in _JIRA:
        return f"jira:{_cle(n)}"
    if t in _XRAY:
        return f"xray:{_cle(n)}"
    return n.id


def systeme(provenance: str, source: str, defaut: str = "") -> str:
    """Système d'origine, déduit de la provenance et du texte de la source."""
    s = (source or "").lower()
    if provenance == "déduit":
        return "AI_INFERENCE"
    if provenance == "déclaré":
        return "CURSOR_VALIDATED" if "proposée par" in s else "USER_DECLARATION"
    if "failure analysis" in s or "tnr" in s or "résultat" in s:
        return "EXECUTION_CENTER"
    if "xray" in s:
        return "XRAY"
    if "jira" in s:
        return "JIRA"
    if "openapi" in s:
        return "API_CONTRACT"
    if s.startswith("carte") or "discovery" in s:
        return "APPLICATION_DISCOVERY"
    if any(m in s for m in ("dépôt", "robot", "data/", "bdd", "jdd")):
        return "AUTOMATION_STUDIO"
    return defaut or "USER_DECLARATION"


def statut_validation(provenance: str, statut: str) -> str:
    """Observé dans une source = OFFICIAL ; déclaré par un humain ou proposition validée = VALIDATED ; le reste = PROPOSED."""
    if statut != "validé":
        return "PROPOSED"
    return "OFFICIAL" if provenance == "observé" else "VALIDATED"


def _systeme_noeud(n: Noeud, t: str) -> str:
    if n.provenance == "observé" and t in _JIRA:
        return "EXECUTION_CENTER" if "failure analysis" in (n.source or "").lower() and not _CLE_JIRA.match(_cle(n)) else "JIRA"
    if n.provenance == "observé" and t in _XRAY:
        return "XRAY"
    return systeme(n.provenance, n.source, {"BUSINESS": "USER_DECLARATION", "TESTING": "AUTOMATION_STUDIO",
                                              "APPLICATION": "APPLICATION_DISCOVERY"}[TYPES_CIBLES[t][0]])


# --------------------------------------------------------------------------- migration des relations
_EXIGENCES = ("JiraEpic", "JiraFeature", "JiraStory", "JiraRequirement")
_PARCOURS = ("UserJourney", "DiscoveredJourney")
_SCRIPTS = ("AutomationScript", "Keyword", "RobotSuite", "AutomationResource", "PageObject")
# (relation historique, types source, types cible, relation métier, sens inversé, système imposé, à confirmer)
# Types = types CIBLES ; None = n'importe lequel. La première règle qui correspond s'applique.
REGLES = [
    # « contient » : six sens différents, jamais convertis en bloc
    ("contient", ("XrayTestPlan",), ("XrayTest",), "INCLUDED_IN_PLAN", True, "XRAY", ""),
    ("contient", ("XrayTestSet",), ("XrayTest",), "MEMBER_OF", True, "XRAY", ""),
    ("contient", ("XrayTestExecution",), ("XrayTestRun",), "HAS_TEST_RUN", False, "XRAY", ""),
    ("contient", ("BusinessModule",), ("XrayTest",) + _EXIGENCES + ("JiraBug",), "BELONGS_TO", True, "JIRA",
     "le module vient du composant Jira : composant = module métier ?"),
    ("contient", _EXIGENCES, _EXIGENCES + ("JiraBug",), "PARENT_OF", False, "JIRA", ""),
    ("contient", _EXIGENCES, ("AcceptanceCriterion",), "HAS_ACCEPTANCE_CRITERION", False, "", ""),
    ("contient", _EXIGENCES + ("BusinessModule", "BusinessFeature", "BusinessSubFeature"), ("BusinessRule",), "HAS_BUSINESS_RULE", False, "", ""),
    ("contient", ("BusinessDomain",), ("BusinessModule",), "PARENT_OF", False, "", ""),
    ("contient", ("BusinessModule",), ("BusinessFeature",), "HAS_FEATURE", False, "", ""),
    ("contient", ("BusinessFeature",), ("BusinessSubFeature",), "PARENT_OF", False, "", ""),
    ("contient", ("BusinessModule", "BusinessFeature"), _PARCOURS, "HAS_JOURNEY", False, "", ""),
    ("contient", ("Application",), ("Platform",), "RUNS_ON", False, "", ""),
    ("contient", ("Application",), ("ApplicationVersion",), "HAS_VERSION", False, "", ""),
    ("contient", ("Application",), ("BusinessModule",), "HAS_MODULE", False, "", ""),
    ("contient", ("Application",), ("Screen",), "HAS_SCREEN", False, "", "écran sans module : simple inventaire"),
    ("contient", ("BusinessModule",), ("Screen",), "BELONGS_TO", True, "", ""),
    ("contient", ("BusinessModule",), ("APIEndpoint",), "BELONGS_TO", True, "", "rattachement par l'étiquette (tags) du contrat OpenAPI"),
    ("contient", ("BusinessFeature", "BusinessSubFeature", "JiraFeature"), ("Screen", "UIComponent", "APIEndpoint"), "REALIZED_BY", False, "", ""),
    ("contient", _PARCOURS, ("Screen", "UIAction"), "PART_OF_JOURNEY", True, "", ""),
    ("contient", ("Screen",), ("UIComponent",), "CONTAINS_COMPONENT", False, "", ""),
    ("contient", ("Screen",), ("Locator",), "HAS_LOCATOR", False, "", ""),
    ("contient", ("Screen",), ("UIAction",), "HAS_ACTION", False, "", ""),
    ("contient", ("Screen", "UIComponent"), ("BusinessRule", "ApplicationRule"), "IMPLEMENTS_RULE", False, "", ""),
    ("contient", ("AutomationResource", "PageObject", "RobotSuite", "BDDFeature"), None, "DEFINES", False, "", ""),
    ("contient", None, None, "RELATED_TO", False, "", "« contient » sans sens métier reconnu pour cette paire"),
    # couverture et exécution
    ("teste_par", _EXIGENCES + ("JiraBug",), ("XrayTest",), "VERIFIES", True, "", ""),
    ("teste_par", None, ("XrayTest", "AutomationScript"), "COVERS", True, "", ""),
    ("teste_par", None, None, "COVERS", True, "", "« testé par » vers un nœud qui n'est pas un test"),
    ("execute_par", ("XrayTest",), ("XrayTestExecution",), "EXECUTED_IN", False, "XRAY", ""),
    ("execute_par", None, None, "EXECUTED_IN", False, "", "« exécuté par » hors Test → Test Execution"),
    ("implemente_par", ("XrayTest",), ("AutomationScript",), "AUTOMATED_BY", False, "", ""),
    ("implemente_par", ("BDDScenario",), ("AutomationScript",), "IMPLEMENTS_SCENARIO", True, "", ""),
    ("implemente_par", None, None, "AUTOMATED_BY", False, "", "« implémenté par » hors Test → script"),
    ("verifie", ("XrayTest",), _EXIGENCES + ("JiraBug",), "VERIFIES", False, "", ""),
    ("verifie", None, None, "COVERS", False, "", ""),
    ("couvre", None, None, "COVERS", False, "", ""),
    # application
    ("navigue_vers", None, None, "NAVIGATES_TO", False, "", ""),
    ("utilise", ("UIComponent",) + _SCRIPTS, ("Locator",), "USES_LOCATOR", False, "", ""),
    ("utilise", _SCRIPTS, ("UIComponent",), "USES_COMPONENT", False, "", ""),
    ("utilise", None, ("AutomationLibrary",), "USES_LIBRARY", False, "", ""),
    ("utilise", _EXIGENCES + ("BusinessFeature",), ("APIEndpoint",), "REALIZED_BY", False, "", ""),
    ("utilise", ("UIAction", "ObservedBehavior", "Screen"), ("APIEndpoint",), "CALLS_API", False, "", ""),
    ("utilise", None, ("TestDataSet",), "USES_TEST_DATA", False, "", ""),
    ("utilise", None, ("DataVariable",), "USES_TEST_DATA", False, "APPLICATION_DISCOVERY", ""),
    ("utilise", None, ("Keyword",), "USES_KEYWORD", False, "", ""),
    ("utilise", None, ("PageObject",), "USES_PAGE_OBJECT", False, "", ""),
    ("utilise", None, None, "DEPENDS_ON", False, "", "« utilise » sans sens métier reconnu pour cette paire"),
    ("verifiee_sur", _EXIGENCES + ("JiraBug",), ("Screen",), "VERIFIED_ON", False, "AUTOMATED_TEST", ""),
    ("impacte", _EXIGENCES + ("BusinessFeature",), ("Screen", "UIComponent"), "REALIZED_BY", False, "", ""),
    ("impacte", None, None, "IMPACTS", False, "", ""),
    ("possede", ("UIComponent", "Screen"), ("BusinessRule", "ApplicationRule"), "IMPLEMENTS_RULE", False, "", ""),
    ("possede", None, None, "RELATED_TO", False, "", "« possède » hors champ → règle"),
    # automatisation
    ("appelle", None, ("Keyword",), "USES_KEYWORD", False, "", ""),
    ("appelle", None, None, "DEPENDS_ON", False, "", "« appelle » vers autre chose qu'un keyword"),
    ("depend_de", None, ("TestDataSet",), "USES_TEST_DATA", False, "", ""),
    ("depend_de", None, ("PageObject",), "USES_PAGE_OBJECT", False, "", ""),
    ("depend_de", ("AutomationResource", "PageObject", "RobotSuite"), ("AutomationResource",), "IMPORTS", False, "", ""),
    ("depend_de", None, None, "DEPENDS_ON", False, "", ""),
    # anomalies (Failure Analysis)
    ("concerne", None, None, "AFFECTS", False, "", ""),
    ("detecte_par", None, None, "DETECTED_BY", False, "", ""),
    ("associe_a", _EXIGENCES + ("JiraBug",), _PARCOURS, "HAS_JOURNEY", False, "", ""),  # cadrage d'un parcours utilisateur
    ("associe_a", None, None, "RELATED_TO", False, "", ""),
]


def migrer_relation(r: Relation, type_de: str, type_vers: str) -> dict:
    """Relation métier d'une relation historique, selon les types (cibles) qu'elle relie."""
    for hist, de, vers, cible, inverse, sys_impose, note in REGLES:
        if hist == r.type and (de is None or type_de in de) and (vers is None or type_vers in vers):
            return {"type": cible, "inverse": inverse, "systeme": sys_impose, "a_confirmer": note,
                    "generique": de is None and vers is None and bool(note)}
    return {"type": "RELATED_TO", "inverse": False, "systeme": "", "a_confirmer": f"relation historique inconnue : {r.type}", "generique": True}


def _date_source(source: str) -> str | None:
    m = _DATE.search(source or "")
    return m.group(0) if m else None


def _id_arete(source: str, type_: str, cible: str) -> str:
    return "rel-" + hashlib.sha1(f"{source}|{type_}|{cible}".encode()).hexdigest()[:16]


def metier(r: Relation, g: Graphe, types: dict[str, str] | None = None) -> dict:
    """Lecture métier d'une relation historique (pour l'affichage et les services) : type typé, sens, provenance."""
    a, b = g.noeuds[r.de], g.noeuds[r.vers]
    ta, tb = (types or {}).get(a.id) or type_cible(a, g), (types or {}).get(b.id) or type_cible(b, g)
    m = migrer_relation(r, ta, tb)
    st = statut_validation(r.provenance, r.statut)
    conf = r.proprietes.get("confiance") if st == "PROPOSED" else 1.0
    return {"type": m["type"], "libelle": RELATIONS[m["type"]][1], "famille": RELATIONS[m["type"]][0], "inverse": m["inverse"],
            "source_system": systeme(r.provenance, r.source) if r.provenance != "observé" else (m["systeme"] or systeme(r.provenance, r.source)),
            "validation_status": st, "confidence": conf, "extension": RELATIONS[m["type"]][2], "a_confirmer": m["a_confirmer"],
            "generique": m["generique"]}


def property_graph(g: Graphe, projet_id: str) -> dict:
    """Le graphe au format cible : nœuds et arêtes typés, indépendants du moteur de stockage. Les dates viennent de la
    source quand elle en porte une (instantané daté) ; sinon None : elles seront réelles avec le stockage (phase 5)."""
    types = {i: type_cible(n, g) for i, n in g.noeuds.items()}
    ids = {i: id_cible(n, types[i]) for i, n in g.noeuds.items()}
    noeuds = []
    for i, n in g.noeuds.items():
        t = types[i]
        st = statut_validation(n.provenance, n.statut)
        noeuds.append({"id": ids[i], "type": t, "universe": TYPES_CIBLES[t][0], "external_id": _cle(n) if t in _JIRA + _XRAY else None,
                       "project_id": projet_id, "source_system": _systeme_noeud(n, t), "source_reference": n.source,
                       "validation_status": st, "confidence": n.confiance if st != "PROPOSED" or n.confiance != 1.0 else None,
                       "platforms": list(n.plateformes), "properties": {"title": n.libelle, **n.proprietes},
                       "legacy": {"id": n.id, "type": n.type}})
    aretes = []
    for r in g.relations.values():
        if r.de not in ids or r.vers not in ids:
            continue
        m = metier(r, g, types)
        de, vers = (ids[r.vers], ids[r.de]) if m["inverse"] else (ids[r.de], ids[r.vers])
        date = _date_source(r.source)
        aretes.append({"id": _id_arete(de, m["type"], vers), "source_node_id": de, "target_node_id": vers, "relation_type": m["type"],
                       "source_system": m["source_system"], "source_reference": r.source, "confidence": m["confidence"],
                       "validation_status": m["validation_status"], "project_id": projet_id,
                       "created_at": date, "updated_at": date, "last_observed_at": date,
                       "evidence_references": list(r.proprietes.get("preuves") or []),
                       "properties": dict(r.proprietes), "legacy": {"id": r.id, "type": r.type, "inverse": m["inverse"]},
                       "extension": m["extension"], "to_confirm": m["a_confirmer"]})
    return {"project_id": projet_id, "nodes": noeuds, "edges": aretes}


def rapport_migration(g: Graphe, projet_id: str = "") -> dict:
    """Cohérence de la migration : volumes avant / après, répartition de chaque relation historique par paire de
    types, relations à confirmer, extensions, contrôles (rien de perdu, identifiants uniques, officiel non écrasé)."""
    pg = property_graph(g, projet_id)
    types_n = Counter(n["type"] for n in pg["nodes"])
    par_id = {n["id"]: n for n in pg["nodes"]}
    lignes = Counter()
    notes = {}
    for e in pg["edges"]:
        a, b = par_id[e["source_node_id"]], par_id[e["target_node_id"]]
        k = (e["legacy"]["type"], e["relation_type"], a["type"], b["type"], e["source_system"], e["validation_status"])
        lignes[k] += 1
        if e["to_confirm"]:
            notes[k] = e["to_confirm"]
    table = [{"historique": k[0], "relation": k[1], "de": k[2], "vers": k[3], "source_system": k[4], "validation_status": k[5],
              "n": n, "extension": RELATIONS[k[1]][2], "a_confirmer": notes.get(k, "")}
             for k, n in sorted(lignes.items(), key=lambda x: (x[0][0], -x[1]))]
    ids_n, ids_e = Counter(n["id"] for n in pg["nodes"]), Counter(e["id"] for e in pg["edges"])
    # une proposition qui double une relation officielle (même extrémités, même type) : l'officielle prime
    officielles = {(e["source_node_id"], e["relation_type"], e["target_node_id"]) for e in pg["edges"] if e["validation_status"] == "OFFICIAL"}
    doublees = sum(1 for e in pg["edges"] if e["validation_status"] == "PROPOSED"
                   and (e["source_node_id"], e["relation_type"], e["target_node_id"]) in officielles)
    repartition = {}
    for l in table:
        repartition.setdefault(l["historique"], Counter())[l["relation"]] += l["n"]
    return {
        "projet": projet_id,
        "avant": {"noeuds": len(g.noeuds), "relations": len(g.relations), "types_relations": dict(Counter(r.type for r in g.relations.values()))},
        "apres": {"noeuds": len(pg["nodes"]), "relations": len(pg["edges"]), "types_noeuds": dict(types_n.most_common()),
                  "univers": dict(Counter(n["universe"] for n in pg["nodes"])),
                  "types_relations": dict(Counter(e["relation_type"] for e in pg["edges"]).most_common()),
                  "source_system": dict(Counter(e["source_system"] for e in pg["edges"])),
                  "validation_status": dict(Counter(e["validation_status"] for e in pg["edges"]))},
        "repartition": {h: dict(c.most_common()) for h, c in repartition.items()},
        "table": table,
        "a_confirmer": [l for l in table if l["a_confirmer"]],
        "controles": {
            "sans_perte": len(pg["nodes"]) == len(g.noeuds) and len(pg["edges"]) == len(g.relations),
            "identifiants_noeuds_uniques": all(v == 1 for v in ids_n.values()),
            "identifiants_relations_uniques": all(v == 1 for v in ids_e.values()),
            "noeuds_en_double": sorted(i for i, v in ids_n.items() if v > 1)[:50],
            "relations_en_double": sum(v - 1 for v in ids_e.values() if v > 1),
            "relations_generiques": sum(l["n"] for l in table if l["relation"] in ("RELATED_TO", "DEPENDS_ON") and l["a_confirmer"]),
            "propositions_doublant_une_officielle": doublees,
            "extensions": sum(l["n"] for l in table if l["extension"]),
        },
    }
