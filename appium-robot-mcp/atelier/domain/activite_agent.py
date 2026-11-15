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
