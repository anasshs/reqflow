"""Contrôle avant la bascule vers QAFlow : la conception puis l'automatisation déroulées COMME LE MCP (vrai serveur MCP en
stdio, tests/client_mcp.py), sur une copie de la démo. Aucun agent n'est lancé (commandes Claude Code / Cursor absentes) :
la demande attend dans la boîte, l'outil atelier_demande_suivante la prend, comme le ferait l'agent."""
import shutil
from pathlib import Path

import client_mcp

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"


def test_conception_puis_automatisation_par_le_mcp(projet, tmp_path):
    shutil.copytree(DEMO, projet, dirs_exist_ok=True, ignore=shutil.ignore_patterns("results", "connaissance", "studio", "executions"))
    (tmp_path / "projets.json").write_text("{}", "utf-8")
    env = {"ROBOT_PROJECT_DIR": str(projet), "ATELIER_PROJETS": str(tmp_path / "projets.json"),
           "ATELIER_CLAUDE_CLI": "commande-absente-pour-test", "ATELIER_CURSOR_CLI": "commande-absente-pour-test"}
    etapes = [
        # conception
        ("list_screens", {}),
        ("discovery_donnees_pour_champs", {"champs": [{"libelle": "Identifiant"}], "ecran": "connexion"}),
        ("discovery_etape_predefinie", {"etape": "preparer_sms"}),            # refusée hors session : attendu
        ("knowledge_graph", {"recherche": "connexion"}),
        ("plan_de_test", {"module": "Connexion"}),
        ("discovery_parcours_vers_bdd", {"ecrans": ["connexion", "accueil"], "titre": "Connexion puis accueil"}),
        # automatisation (points d'entrée de QAFlow)
        ("perimetre_automatisation", {"entree": "test", "reference": "DEMO-301"}),
        ("perimetre_automatisation", {"entree": "libre", "reference": "Automatiser la connexion avec un compte bloqué"}),
        ("automatiser_perimetre", {"entree": "test", "reference": "DEMO-301", "technologie": "robot-web"}),
        ("atelier_demande_suivante", {"attente_s": 1}),
        ("studio_plan_automatisation", {"cle": "DEMO-301"}),
        ("studio_generer_depuis_bdd", {"cle": "DEMO-301", "technologie": "robot-web"}),
        ("run_tests", {"tests": ["tests/connexion.robot::Connexion avec un compte valide"], "dry_run": True}),
    ]
    r = dict(zip([f"{i}:{o}" for i, (o, _) in enumerate(etapes)], client_mcp.session(etapes, env, delai_s=240)))
    erreurs = {k: v["valeur"] for k, v in r.items() if v["erreur"] and not k.endswith("discovery_etape_predefinie")}
    assert not erreurs, erreurs
    assert "session" in str(r["2:discovery_etape_predefinie"]["valeur"]).lower()
    assert r["5:discovery_parcours_vers_bdd"]["valeur"]["cle"]                              # brouillon BDD conçu
    assert r["7:perimetre_automatisation"]["valeur"]["tests"][0]["cle"] == "DEMO-306"        # l'existant proche d'abord
    dep = r["8:automatiser_perimetre"]["valeur"]
    assert dep["mode"] == "boite"            # envoi jamais réglé : la demande attend le MCP au lieu d'être refusée
    assert r["9:atelier_demande_suivante"]["valeur"]["demande"]["id"] == dep["demande"]
    assert r["11:studio_generer_depuis_bdd"]["valeur"]["contenu"].startswith("*** Settings ***")
    assert r["12:run_tests"]["valeur"]["code_retour"] == 0

    # QAFlow suit la demande d'après l'atelier : prise par l'agent, scénario BDD présent, jamais validée sans la QA
    from atelier.generation import suivi_automatisation

    s = suivi_automatisation.suivi(dep["demande"])
    etapes_test = {e["id"]: e["fait"] for e in s["tests"][0]["etapes"]}
    assert s["agent"]["etat"] == "en_cours" and etapes_test["prise"] and etapes_test["bdd"] and not etapes_test["valide_qa"]
