"""Activité de l'agent (Cursor, Claude) en temps réel : chaque appel d'outil MCP est publié dans l'atelier
(début, fin, durée, résultat résumé) pour que l'automaticien voie ce que fait l'agent pendant qu'il le fait.

Jamais de secret dans ces événements : le texte saisi (type_text) et toute valeur dont le nom évoque un secret sont
masqués ; les valeurs longues sont tronquées.
"""
from __future__ import annotations

import re

SENSIBLE = re.compile(r"(?i)(password|passwd|mot_?de_?passe|mdp|secret|token|jeton|api_?key|pin|iban|cvv|text|texte|valeurs?)")
# outils qui changent ce qu'on voit à l'écran : une image est envoyée à l'atelier juste après
ACTIONS_ECRAN = {"start_session", "open_url", "tap", "type_text", "swipe", "press_back", "wait_for", "goto_screen", "explore",
                 "discovery_demarrer", "screenshot", "element_at", "get_screen_elements", "capture_screen_locators"}
# famille affichée (couleur, icône) dans la vue « Cursor en direct »
FAMILLES = [("ecran", ACTIONS_ECRAN | {"stop_session", "where_am_i", "screen_info", "name_screen", "list_screens", "check_locator"}),
            ("ecriture", {"write_project_file", "studio_construire_test", "studio_generer_depuis_bdd", "studio_corriger_locator",
                          "studio_factoriser_keywords", "generate_locators_resource", "export_screen_resource", "add_screen_locator",
                          "discovery_proposer", "discovery_parcours_vers_bdd", "discovery_terminer", "discovery_donnee_definir",
                          "discovery_profil_vers_jdd"}),
            ("revue", {"studio_soumettre_revue", "studio_revue", "propose_step", "tnr_demander_publication"}),
            ("execution", {"run_robot", "run_tests", "studio_executer_etape", "parse_robot_output", "import_results_to_xray"})]

# étape du cycle de référence (domain/cycle.py) où l'outil fait avancer le travail ; les lectures générales n'en ont pas
ETAPES_OUTILS = {
    "cadrer": {"discovery_parcours_cadre", "map_apps", "map_create_app", "discovery_donnees_catalogue", "plan_de_test"},
    "explorer": {"start_session", "discovery_demarrer", "discovery_ecran_courant", "where_am_i", "tap", "type_text", "swipe",
                 "press_back", "open_url", "wait_for", "goto_screen", "explore", "screenshot", "get_screen_elements",
                 "get_page_source", "element_at", "capture_screen_locators", "name_screen", "discovery_proposer",
                 "discovery_donnees_pour_champs", "discovery_donnee", "discovery_donnee_definir", "discovery_donnees_contexte",
                 "discovery_terminer", "stop_session", "discovery_correlations_a_juger", "discovery_juger_correlations"},
    "scenariser": {"discovery_parcours_vers_bdd", "studio_scenario_bdd", "test_design_proposer", "test_design_cas_us",
                   "test_design_doublons", "testabilite_deposer_proposition", "discovery_profil_vers_jdd"},
    "automatiser": {"studio_socle", "studio_rapprocher_etapes", "studio_keywords_a_juger", "studio_juger_keywords",
                    "studio_generer_depuis_bdd", "studio_construire_test", "write_project_file", "generate_locators_resource",
                    "studio_soumettre_revue", "run_robot", "run_tests", "check_locator"},
    "publier": {"tnr_conventions", "tnr_demander_publication", "import_results_to_xray", "xray_search_tests", "xray_get_test"},
}
TITRES_ETAPES = {"cadrer": "Cadrer", "explorer": "Explorer", "scenariser": "Scénariser", "automatiser": "Automatiser et vérifier",
                 "publier": "Publier au TNR"}
NOMS_AGENTS = ((re.compile(r"claude[- _]?code", re.I), "Claude Code"), (re.compile(r"claude", re.I), "Claude Desktop"),
               (re.compile(r"cursor", re.I), "Cursor"))


def nom_agent(client: str) -> str:
    """Nom affiché de l'agent d'après le client MCP déclaré (« claude-code 1 » → Claude Code) ; « L'agent » sinon."""
    return next((n for r, n in NOMS_AGENTS if r.search(client or "")), "L'agent")


def etape_outil(nom: str) -> str:
    return next((e for e, noms in ETAPES_OUTILS.items() if nom in noms), "")


def libelle_element(locator: str) -> str:
    """Libellé lisible de l'élément visé (carte de l'application active), sinon « » : « Identifiant oublié » plutôt que
    « android=new UiSelector().resourceId(…) ». Jamais bloquant."""
    if not locator:
        return ""
    try:
        from atelier.discovery import carte
        from atelier.discovery.connaissance import identifiant_locator

        ident = identifiant_locator(locator)
        for e in carte.ecrans() if carte.app_courante() else []:
            for cle, el in (e.get("elements") or {}).items():
                locs = [l for ls in (el.get("locators") or {}).values() for l in ls]
                if locator in locs or (ident and any(identifiant_locator(l) == ident for l in locs)):
                    lib = (el.get("libelle") or "").strip()
                    if lib and not ("_" in lib and " " not in lib):  # un identifiant technique n'est pas un libellé
                        return lib
    except Exception:  # noqa: BLE001
        return ""
    return ""


def jalon(ev: dict) -> str:
    """Ce qui mérite une notification à l'automaticien (popup) : début et fin des grandes étapes, écritures, erreurs.
    « » pour un appel ordinaire (il reste dans la console)."""
    nom, etat, a, res = ev.get("nom", ""), ev.get("etat", ""), ev.get("args") or {}, str(ev.get("resultat") or "")
    if etat == "erreur":
        return f"Erreur sur {nom} : {str(ev.get('message') or '')[:140]}"
    if etat == "debut":
        return {"discovery_demarrer": f"Discovery lancée {_a(a, 'parcours', 'perimetre')}".strip(),
                "run_robot": f"Tests lancés {_a(a, 'target')}".strip(), "run_tests": "Tests lancés"}.get(nom, "")
    if etat != "fin":
        return ""
    return {"start_session": f"Session ouverte {_a(a, 'platform')}".strip(),
            "discovery_terminer": "Discovery terminée : bilan disponible (écrans, transitions, propositions)",
            "discovery_proposer": f"Proposition déposée au Knowledge Graph {_a(a, 'libelle')} (à valider)".replace("  ", " "),
            "discovery_parcours_vers_bdd": "Brouillon BDD créé dans Test Design",
            "discovery_profil_vers_jdd": "Jeu de données des tests créé",
            "write_project_file": f"Fichier écrit {_a(a, 'path')}".strip(),
            "studio_generer_depuis_bdd": "Suite Robot écrite (revue technique)" if str(a.get("ecrire")).lower() == "true" else "",
            "studio_soumettre_revue": f"Script soumis à la revue {_a(a, 'fichier')}".strip(),
            "run_robot": f"Tests terminés · {res}" if res else "Tests terminés",
            "run_tests": f"Tests terminés · {res}" if res else "Tests terminés",
            "tnr_demander_publication": "Publication au TNR demandée : à valider dans l'atelier",
            "stop_session": "Session de test fermée"}.get(nom, "")


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
    "atelier_demande_suivante": lambda a: "Cursor attend la prochaine demande déposée dans l'atelier",
    "atelier_demande_terminee": lambda a: f"Cursor rend compte de la demande {_a(a, 'id')}",
    "discovery_donnees_catalogue": lambda a: "Cursor consulte le référentiel de données (variables, profils, générateurs)",
    "discovery_donnees_pour_champs": lambda a: f"Cursor cherche les données des champs de l'écran {_a(a, 'ecran')}",
    "discovery_donnee": lambda a: f"Cursor demande la variable {_a(a, 'cle')}",
    "discovery_donnee_definir": lambda a: f"Cursor garde la valeur relevée {_a(a, 'cle')} dans le contexte de la session",
    "discovery_donnees_contexte": lambda a: "Cursor lit le contexte de données de la session",
    "studio_keywords_a_juger": lambda a: f"Cursor lit les étapes sans keyword du scénario {_a(a, 'cle')} et les keywords existants",
    "studio_juger_keywords": lambda a: f"Cursor dit pour chaque étape du scénario {_a(a, 'cle')} : réutiliser un keyword ou créer (à décider)",
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
    "tap": lambda a: f"Cursor touche {_a(a, 'element')}" if _a(a, "element") else f"Cursor touche l'élément {_a(a, 'locator')}",
    "type_text": lambda a: "Cursor saisit une valeur" + (f" dans {_a(a, 'element')}" if _a(a, "element") else f" dans {_a(a, 'locator')}" if _a(a, "locator") else ""),
    "press_back": lambda a: "Cursor revient à l'écran précédent",
    "stop_session": lambda a: "Cursor ferme la session de test",
    "discovery_demarrer": lambda a: f"Cursor démarre une Discovery {_a(a, 'parcours', 'perimetre')}",
    "discovery_terminer": lambda a: "Cursor termine la Discovery et en fait le bilan",
    "discovery_parcours_cadre": lambda a: f"Cursor lit le cadrage du parcours {_a(a, 'parcours')}",
    "discovery_parcours_vers_bdd": lambda a: f"Cursor crée le brouillon BDD du parcours {_a(a, 'parcours', 'titre')}",
    "discovery_profil_vers_jdd": lambda a: f"Cursor crée le jeu de données des tests depuis le profil {_a(a, 'profil')}",
    "run_tests": lambda a: f"Cursor lance les tests {_a(a, 'tests')}",
    "coverage_ui": lambda a: f"Cursor consulte la couverture des parcours et des écrans {_a(a, 'module')}",
    "tnr_conventions": lambda a: "Cursor lit les conventions TNR de l'application (étiquette, plan, champs Jira)",
    "tnr_demander_publication": lambda a: "Cursor demande la publication de scénarios au TNR (à valider dans l'atelier)",
    "stop_session_web": lambda a: "Cursor ferme le navigateur",
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


def decrire(nom: str, args: dict | None = None, doc: str = "", agent: str = "Cursor") -> str:
    """Ce que fait l'agent, en français : phrase dédiée, sinon tirée de la documentation de l'outil. agent : nom de
    l'agent connecté (Claude Code, Cursor…), qui remplace « Cursor » en tête de phrase."""
    p = _decrire(nom, args, doc)
    return agent + p[len("Cursor"):] if agent and agent != "Cursor" and p.startswith("Cursor") else p


def _decrire(nom: str, args: dict | None = None, doc: str = "") -> str:
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
