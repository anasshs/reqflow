"""Opérations QA consommatrices d'IA : identifiant stable, module QA (cahier § 10.3) et niveau de modèle par défaut.

L'opération est déduite du module Python qui appelle le modèle : les points d'appel existants n'ont pas à changer.
"""
from __future__ import annotations

import inspect
from pathlib import Path

MODULES_QA = ("Discovery", "Requirement Analysis", "Impact Analysis", "Non-Regression", "Test Design", "Execution Analysis",
              "Defect Analysis", "QA Decision", "Agent intégré", "Autre")

# module Python appelant -> (opération, module QA, niveau par défaut)
PAR_MODULE = {
    "testabilite_us": ("exigences.testabilite", "Requirement Analysis", "avance"),
    "intelligence_couverture": ("exigences.liens_tests", "Requirement Analysis", "economique"),
    "couverture": ("exigences.redondances", "Requirement Analysis", "economique"),
    "granularite_tests": ("conception.granularite", "Test Design", "economique"),
    "conception_avancee": ("conception.doublons", "Test Design", "economique"),
    "reutilisation": ("automatisation.keywords", "Test Design", "economique"),
    "studio_avance": ("automatisation.relecture", "Test Design", "economique"),
    "correlation": ("discovery.correlation", "Discovery", "economique"),
    "assistance": ("discovery.assistance", "Discovery", "economique"),
    "release_ia": ("non_regression.interpretation", "Non-Regression", "avance"),
    "cerveau": ("decision.question", "QA Decision", "avance"),
    "assistant": ("impact.assistant", "Impact Analysis", "auto"),
    "echecs": ("echecs.analyse", "Defect Analysis", "auto"),
    "agent": ("agent.integre", "Agent intégré", "avance"),
}
INTERMEDIAIRES = {"orchestrateur", "fournisseur_ia", "jugement_ia", "operations", "routeur", "simulateur"}

# outils MCP (Cursor) : module QA d'après le préfixe du nom
PREFIXES_MCP = [("release_", "Non-Regression"), ("discovery_", "Discovery"), ("coverage_", "Requirement Analysis"),
                ("testabilite_", "Requirement Analysis"), ("test_design_", "Test Design"), ("studio_", "Test Design"),
                ("xray_", "Requirement Analysis"), ("failure_", "Defect Analysis"), ("qualify_", "Defect Analysis"),
                ("impact_", "Impact Analysis"), ("knowledge_", "Impact Analysis"), ("parcours_", "Discovery"),
                ("run_", "Execution Analysis"), ("parse_robot", "Execution Analysis"), ("plan_de_test", "QA Decision"),
                ("cerveau_", "QA Decision")]


# Traitements où l'IA peut intervenir : libellé, module QA, fragilité du modèle applicatif, ce que fait l'applicatif seul.
# « fragile » : sans IA, l'atelier ne fait que rapprocher des mots (sans comprendre le texte) : l'IA par défaut.
TRAITEMENTS = {
    "non_regression.interpretation": ("Lecture des Release Notes et des builds", "Non-Regression", True,
                                      "une ligne = une évolution, rattachement par les clés Jira et les mots communs"),
    "exigences.liens_tests": ("Liens exigence ↔ test et tests orphelins", "Requirement Analysis", True, "ressemblance des mots (TF-IDF)"),
    "exigences.redondances": ("Tests redondants (Xray)", "Requirement Analysis", True, "titres presque identiques"),
    "exigences.testabilite": ("Testabilité des US", "Requirement Analysis", True, "ambiguïtés repérées par mots-clés, un cas par critère"),
    "conception.doublons": ("Doublons de cas de test", "Test Design", True, "ressemblance des mots avec les tests Xray"),
    "conception.granularite": ("Granularité des tests", "Test Design", True, "regroupement par mots communs"),
    "automatisation.keywords": ("Réutilisation des keywords", "Test Design", True, "rapprochement des étapes par les mots"),
    "discovery.correlation": ("Corrélation écran ↔ exigence", "Discovery", True, "mots communs entre l'écran et l'exigence"),
    "discovery.assistance": ("Assistance à l'exploration", "Discovery", False, "suggestions explicables (actions sûres jamais essayées)"),
    "automatisation.relecture": ("Relecture des scripts Robot", "Test Design", False, "contrôles calculés (Robocop, structure)"),
    "conception.relecture_scenario": ("Relecture des scénarios BDD", "Test Design", False, "contrôles calculés"),
    "decision.question": ("Question libre sur la connaissance", "QA Decision", False, "recherche dans la connaissance, sans synthèse"),
    "impact.assistant": ("Assistant des graphes", "Impact Analysis", False, "anomalies calculées"),
    "echecs.analyse": ("Analyse des échecs", "Defect Analysis", False, "classement des échecs par règles"),
    "agent.integre": ("Agent intégré de l'interface", "Agent intégré", False, "aucun : sans IA, pas d'agent"),
}
# Toujours le modèle applicatif : calculs déterministes, jamais confiés à l'IA (backend first).
DETERMINISTES = ("Couverture, taux de réussite, agrégation des anomalies", "Analyse d'impact par le Knowledge Graph",
                 "Périmètre de non-régression (retest, ciblée, qualification, plafonds)", "Comparaison entre builds successifs",
                 "Critères de sortie et qualification de la release", "Statuts et résultats d'exécution")


def connues() -> dict:
    """{opération: {module, niveau}} : les opérations que l'atelier sait appeler (pour l'écran de réglages)."""
    return {op: {"module": mod, "niveau": niv} for op, mod, niv in PAR_MODULE.values()}


def module_de(operation: str) -> str:
    return next((mod for op, mod, _ in PAR_MODULE.values() if op == operation), TRAITEMENTS.get(operation, ("", "Autre"))[1])


def niveau_defaut(operation: str) -> str:
    return next((niv for op, _, niv in PAR_MODULE.values() if op == operation), "auto")


def appelante() -> tuple[str, str]:
    """(opération, module QA) du premier appelant connu dans la pile ; (« autre », « Autre ») sinon."""
    for f in inspect.stack(context=0)[1:]:
        nom = Path(f.filename).stem
        if nom in INTERMEDIAIRES:
            continue
        if nom in PAR_MODULE:
            op, mod, _ = PAR_MODULE[nom]
            return op, mod
    return "autre", "Autre"


def module_mcp(outil: str) -> str:
    return next((mod for p, mod in PREFIXES_MCP if outil.startswith(p)), "Autre")
