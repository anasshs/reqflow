"""V2, phase 7 : registre de sécurité des outils MCP. Chaque outil est classé ; un outil ajouté sans classement fait
échouer ce test (il faut décider de sa garde côté serveur avant de l'exposer à Cursor).
Nature : L lecture · P proposition validée dans l'atelier · A action device / navigateur · É écriture locale gardée ·
X écriture externe (Jira / Xray) → demande à valider (sauf l'envoi des résultats d'un run, idempotent)."""
import ast
import re
from pathlib import Path

NATURE = {
    # session et actions sur le device / navigateur
    **dict.fromkeys(["list_devices", "screenshot", "get_screen_elements", "element_at", "get_page_source", "check_locator", "wait_for"], "L"),
    **dict.fromkeys(["start_session", "stop_session", "open_url", "tap", "type_text", "swipe", "press_back", "goto_screen", "explore",
                     "stop_exploration"], "A"),
    # carte et locators
    **dict.fromkeys(["map_apps", "list_screens", "screen_info", "map_tags_report"], "L"),
    **dict.fromkeys(["capture_screen_locators", "generate_locators_resource", "add_screen_locator", "map_create_app", "map_select_app",
                     "map_set_build", "where_am_i", "name_screen", "map_import_existing", "export_screen_resource"], "É"),
    # Discovery
    **dict.fromkeys(["discovery_ecran_courant", "discovery_donnees_catalogue"], "L"),
    **dict.fromkeys(["discovery_demarrer", "discovery_terminer", "discovery_donnees_pour_champs", "discovery_donnee", "discovery_donnee_definir",
                     "discovery_donnees_contexte"], "É"),  # données : seul le contexte de la session est écrit, jamais le catalogue
    **dict.fromkeys(["propose_step", "discovery_proposer", "discovery_parcours_vers_bdd"], "P"),
    # dépôt, exécution, données
    **dict.fromkeys(["list_project_files", "read_project_file", "parse_robot_output", "list_jdd", "get_jdd", "find_test_data", "check_jdd"], "L"),
    "write_project_file": "É",
    # Jira / Xray
    **dict.fromkeys(["xray_get_test", "xray_search_tests", "xray_inspect_ticket", "jira_subtasks"], "L"),
    **dict.fromkeys(["jira_transition", "qualify_failure", "import_results_to_xray", "run_robot"], "X"),
    # connaissance, couverture, Test Design
    **dict.fromkeys(["knowledge_graph", "impact_analysis", "coverage_report", "automation_flow", "plan_de_test", "cerveau_application",
                     "cerveau_question", "coverage_intelligence", "testabilite_us_a_traiter"], "L"),
    **dict.fromkeys(["testabilite_deposer_proposition", "coverage_proposer_story", "coverage_proposer_lien"], "P"),
    # Automation Studio
    **dict.fromkeys(["studio_socle", "studio_rapprocher_etapes", "studio_scenario_bdd", "studio_revue", "studio_corrections_locators", "studio_factorisation_keywords"], "L"),
    **dict.fromkeys(["studio_generer_depuis_bdd", "studio_construire_test", "studio_executer_etape", "studio_corriger_locator",
                     "studio_factoriser_keywords"], "É"),
    "studio_soumettre_revue": "P",
    # V2
    **dict.fromkeys(["parcours_lister", "parcours_etat", "cursor_regles", "coverage_ui", "test_design_doublons", "knowledge_entites",
                     "failure_connaissance", "agent_annoncer", "test_design_cas_us", "test_design_doublons_a_juger",
                     "xray_redondances_a_juger", "studio_keywords_a_juger", "coverage_liens_a_juger", "coverage_orphelins_a_classer", "discovery_correlations_a_juger"], "L"),  # agent_annoncer : simple annonce dans la console, rien d'écrit
    **dict.fromkeys(["parcours_initialiser", "parcours_etape", "parcours_reprendre"], "É"),
    **dict.fromkeys(["test_design_proposer", "knowledge_proposer_champ", "test_design_proposer_regroupements", "test_design_juger_doublons",
                     "xray_juger_redondances", "studio_juger_keywords", "coverage_juger_liens", "coverage_classer_orphelins", "discovery_juger_correlations"], "P"),
}
SOURCE = (Path(__file__).resolve().parents[1] / "atelier" / "adapters" / "facade.py").read_text("utf-8")


def _outils() -> dict:
    t = ast.parse(SOURCE)
    return {n.name: ast.get_source_segment(SOURCE, n) for n in t.body if isinstance(n, ast.FunctionDef)
            and any(isinstance(d, ast.Name) and d.id == "outil" for d in n.decorator_list)}


def test_chaque_outil_est_classe():
    o = _outils()
    assert set(o) == set(NATURE), f"non classés : {sorted(set(o) - set(NATURE))} ; disparus : {sorted(set(NATURE) - set(o))}"
    assert len(o) == 109


def test_ecritures_externes_par_demande():
    o = _outils()
    for nom in ("jira_transition", "qualify_failure", "import_results_to_xray"):
        assert "demandes.creer(" in o[nom] and "suivi." not in o[nom].split('"""', 2)[-1], nom  # aucune écriture directe
    assert 'transitions = {"début": jira_transition_start' in o["run_robot"] and '"", "", attach_screenshots' in o["run_robot"]


def test_actions_device_classees_cote_serveur():
    o = _outils()
    for nom in ("tap", "type_text"):
        assert "apprentissage.action_mcp(" in o[nom], nom
    assert "liste rouge" in o["explore"]


def test_aucun_outil_git_ni_fusion():
    """Commit, push et merge request ne se font que dans l'atelier (suites approuvées et stables) : jamais par MCP."""
    assert not [n for n in _outils() if re.search(r"commit|push|merge|fusion_git|merge_request", n)]


def test_decision_humaine_jamais_par_mcp():
    o = _outils()
    for nom, corps in o.items():
        assert "demandes.decider(" not in corps and "decider_revue" not in corps, nom  # accepter / approuver : dans l'atelier seulement
    assert 'origine="mcp"' in o["parcours_etape"]
