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


def connues() -> dict:
    """{opération: {module, niveau}} : les opérations que l'atelier sait appeler (pour l'écran de réglages)."""
    return {op: {"module": mod, "niveau": niv} for op, mod, niv in PAR_MODULE.values()}


def module_de(operation: str) -> str:
    return next((mod for op, mod, _ in PAR_MODULE.values() if op == operation), "Autre")


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
