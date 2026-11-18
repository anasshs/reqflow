"""Activité de l'agent (Cursor, Claude) en temps réel : chaque appel d'outil MCP est publié dans l'atelier
(début, fin, durée, résultat résumé) pour que l'automaticien voie ce que fait l'agent pendant qu'il le fait.

Jamais de secret dans ces événements : le texte saisi (type_text) et toute valeur dont le nom évoque un secret sont
masqués ; les valeurs longues sont tronquées.
"""
from __future__ import annotations

import re

SENSIBLE = re.compile(r"(?i)(password|passwd|mot_?de_?passe|mdp|secret|token|jeton|api_?key|pin|iban|cvv|text|texte|valeurs)")
# outils qui changent ce qu'on voit à l'écran : une image est envoyée à l'atelier juste après
ACTIONS_ECRAN = {"start_session", "open_url", "tap", "type_text", "swipe", "press_back", "wait_for", "goto_screen", "explore",
                 "discovery_demarrer", "screenshot", "element_at", "get_screen_elements", "capture_screen_locators"}
# famille affichée (couleur, icône) dans la vue « Cursor en direct »
FAMILLES = [("ecran", ACTIONS_ECRAN | {"stop_session", "where_am_i", "screen_info", "name_screen", "list_screens", "check_locator"}),
            ("ecriture", {"write_project_file", "studio_construire_test", "studio_generer_depuis_bdd", "studio_corriger_locator",
                          "studio_factoriser_keywords", "generate_locators_resource", "export_screen_resource", "add_screen_locator"}),
            ("revue", {"studio_soumettre_revue", "studio_revue", "propose_step"}),
            ("execution", {"run_robot", "studio_executer_etape", "parse_robot_output", "import_results_to_xray"})]


def famille(nom: str) -> str:
    return next((f for f, noms in FAMILLES if nom in noms), "lecture")


def _court(v, n: int = 120):
    t = v if isinstance(v, str) else repr(v)
    return t if len(t) <= n else t[:n] + "…"


def resumer_arguments(nom: str, args: dict) -> dict:
    out = {}
    for k, v in (args or {}).items():
        if v in (None, "", [], {}):
            continue
        if SENSIBLE.search(k) or (nom == "type_text" and k not in ("key", "locator", "cle")):
            out[k] = "•••"
        elif k in ("content", "contenu"):
            out[k] = f"{len(str(v))} caractères"
        else:
            out[k] = _court(v)
    return out


def resumer_resultat(r) -> str:
    if isinstance(r, dict):
        for k in ("statut", "fichier", "ecrit", "cible", "resultat", "message"):
            if r.get(k) not in (None, "", {}):
                return _court(f"{k} : {r[k] if not isinstance(r[k], dict) else ', '.join(f'{a}={b}' for a, b in list(r[k].items())[:4])}")
        return _court(", ".join(list(r)[:6]))
    if isinstance(r, list):
        return f"{len(r)} élément(s)"
    if isinstance(r, (bytes, bytearray)) or type(r).__name__ == "Image":
        return "image"
    return _court(r)


# =========================================================================== en langage naturel (console Cursor)
def _a(args: dict, *cles: str) -> str:
    """Première valeur présente parmi les arguments (déjà résumés), entre guillemets français."""
    for k in cles:
        v = (args or {}).get(k)
        if v not in (None, "", "•••"):
            return f"« {_court(v if isinstance(v, str) else str(v), 60)} »"
    return ""


# phrases écrites pour les outils les plus fréquents ; les autres sont décrits depuis leur documentation
PHRASES = {
    "testabilite_us_a_traiter": lambda a: "Cursor lit les User Stories à couvrir (texte masqué, réponses de l'équipe)",
    "testabilite_deposer_proposition": lambda a: f"Cursor dépose son analyse et ses cas de test proposés pour l'US {_a(a, 'cle')}",
    "test_design_doublons": lambda a: f"Cursor vérifie qu'un test proche n'existe pas déjà dans Xray {_a(a, 'titre')}",
    "test_design_proposer": lambda a: f"Cursor fait générer les cas par catégorie pour l'US {_a(a, 'cle')}",
    "test_design_cas_us": lambda a: f"Cursor lit les cas de test de l'US {_a(a, 'cle')} pour juger leur granularité",
    "test_design_proposer_regroupements": lambda a: f"Cursor propose de regrouper des cas de l'US {_a(a, 'cle')} (à appliquer ou écarter)",
    "test_design_doublons_a_juger": lambda a: f"Cursor lit les cas de l'US {_a(a, 'cle')} et les tests existants proches pour juger les doublons",
    "test_design_juger_doublons": lambda a: f"Cursor dit pour chaque cas de l'US {_a(a, 'cle')} : réutiliser, faire évoluer ou créer (à décider)",
    "xray_redondances_a_juger": lambda a: "Cursor lit des paires de tests Xray aux titres proches pour juger s'ils font doublon",
    "xray_juger_redondances": lambda a: "Cursor dépose son jugement sur des tests Xray redondants (aucun test modifié)",
    "coverage_liens_a_juger": lambda a: f"Cursor lit des exigences et les tests candidats pour juger la traçabilité {_a(a, 'exigence')}",
    "coverage_juger_liens": lambda a: "Cursor juge quels tests couvrent vraiment quelles exigences (liens à valider)",
    "coverage_orphelins_a_classer": lambda a: "Cursor lit les tests Xray sans exigence",
    "coverage_classer_orphelins": lambda a: "Cursor propose un classement pour des tests sans exigence (à valider)",
    "discovery_correlations_a_juger": lambda a: f"Cursor lit les écrans de la carte et les exigences Jira {_a(a, 'ecran')}",
    "discovery_juger_correlations": lambda a: "Cursor relie des écrans à des exigences (liens à confirmer)",
    "xray_search_tests": lambda a: f"Cursor cherche des tests dans Xray {_a(a, 'jql')}",
    "xray_get_test": lambda a: f"Cursor lit le test Xray {_a(a, 'test_key')}",
    "plan_de_test": lambda a: f"Cursor consulte le plan de test du module {_a(a, 'module')}",
    "knowledge_graph": lambda a: f"Cursor consulte le Knowledge Graph {_a(a, 'recherche', 'centre', 'categorie')}",
    "cerveau_application": lambda a: "Cursor consulte le cerveau de l'application (sources, modules, lacunes)",
    "cerveau_question": lambda a: f"Cursor pose une question au cerveau {_a(a, 'question')}",
    "cursor_regles": lambda a: f"Cursor relit les règles du projet {_a(a, 'regle')}",
    "coverage_intelligence": lambda a: f"Cursor consulte Coverage Intelligence {_a(a, 'vue', 'onglet')}",
    "studio_rapprocher_etapes": lambda a: "Cursor rapproche ses étapes BDD des keywords existants (pas de doublon)",
    "studio_socle": lambda a: "Cursor inventorie le socle à réutiliser (keywords, locators, données)",
    "studio_scenario_bdd": lambda a: f"Cursor lit le scénario BDD et son mapping vers le socle {_a(a, 'cle')}",
    "studio_construire_test": lambda a: f"Cursor assemble un test Robot à partir des keywords existants {_a(a, 'nom')}",
    "studio_generer_depuis_bdd": lambda a: f"Cursor génère la suite Robot depuis le scénario BDD {_a(a, 'cle')}",
    "studio_soumettre_revue": lambda a: f"Cursor soumet un script à la revue technique {_a(a, 'fichier')}",
    "read_project_file": lambda a: f"Cursor lit le fichier du projet {_a(a, 'path')}",
    "list_project_files": lambda a: f"Cursor liste les fichiers du projet {_a(a, 'pattern')}",
    "write_project_file": lambda a: f"Cursor écrit le fichier {_a(a, 'path')}",
    "run_robot": lambda a: f"Cursor lance les tests Robot {_a(a, 'target')}",
    "parcours_etape": lambda a: f"Cursor fait avancer le parcours de fonctionnalité ({_a(a, 'action')} sur l'étape {_a(a, 'etape')})",
    "parcours_initialiser": lambda a: f"Cursor ouvre un parcours de fonctionnalité {_a(a, 'fonctionnalite', 'libelle')}",
    "discovery_proposer": lambda a: f"Cursor propose au Knowledge Graph : {_a(a, 'libelle')} ({_a(a, 'nature')})",
    "start_session": lambda a: f"Cursor ouvre une session {_a(a, 'platform')}",
    "tap": lambda a: f"Cursor touche l'élément {_a(a, 'locator')}",
    "type_text": lambda a: "Cursor saisit du texte" + (f" dans {_a(a, 'locator')}" if _a(a, "locator") else ""),
    "open_url": lambda a: f"Cursor ouvre la page {_a(a, 'url')}",
    "swipe": lambda a: f"Cursor fait défiler l'écran {_a(a, 'direction')}",
    "screenshot": lambda a: "Cursor prend une capture de l'écran",
    "impact_analysis": lambda a: f"Cursor analyse l'impact d'une modification de {_a(a, 'element')}",
    "discovery_ecran_courant": lambda a: "Cursor lit l'écran courant pour l'explorer",
    "get_screen_elements": lambda a: "Cursor lit les éléments de l'écran",
    "where_am_i": lambda a: "Cursor identifie l'écran courant dans la carte",
    "agent_annoncer": lambda a: "Cursor annonce ce qu'il va faire",
}
VERBES = ("liste", "ouvre", "ferme", "lit", "vérifie", "touche", "saisit", "attend", "enregistre", "fusionne", "propose", "écrit",
          "lance", "cherche", "ajoute", "qualifie", "déclare", "change", "indique", "donne", "va", "explore", "demande", "amorce",
          "génère", "fait", "envoie", "dépose", "démarre", "crée", "termine", "assemble", "exécute", "corrige", "factorise",
          "soumet", "renvoie", "calcule", "compare", "relit", "consulte", "analyse", "importe", "rejoue", "sélectionne")


def _premiere_phrase(doc: str) -> str:
    t = " ".join((doc or "").split())
    for sep in (". ", " : ", " ; "):
        if sep in t:
            t = t.split(sep, 1)[0]
    return t.rstrip(".")[:140]


def decrire(nom: str, args: dict | None = None, doc: str = "") -> str:
    """Ce que fait l'agent, en français : phrase dédiée, sinon tirée de la documentation de l'outil."""
    f = PHRASES.get(nom)
    if f:
        return " ".join(f(args or {}).split())
    p = _premiere_phrase(doc)
    if not p:
        return f"Cursor appelle l'outil {nom}"
    premier = p.split(" ", 1)[0].lower()
    if premier in VERBES:
        return f"Cursor {p[0].lower()}{p[1:]}"
    return f"Cursor consulte : {p[0].lower()}{p[1:]}"
