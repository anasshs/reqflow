"""Boîte de demandes à Cursor : dépôt depuis l'atelier, prise par l'agent (MCP), compte rendu ; lancement de l'agent
Cursor en ligne de commande (commande réglable, jamais de shell)."""
from __future__ import annotations

import os
import stat
import sys
import threading
import time

import pytest


@pytest.fixture
def boite(projet, monkeypatch):
    from atelier.integrations import boite_cursor

    monkeypatch.delenv("ATELIER_CURSOR_CLI", raising=False)
    monkeypatch.delenv("ATELIER_CURSOR_CLI_ARGS", raising=False)
    return boite_cursor


def _faux_agent(dossier, code_retour=0):
    """Faux agent en ligne de commande : écrit ses arguments (un par ligne) et son dossier de travail."""
    f = dossier / "faux_agent.py"
    f.write_text(f"#!{sys.executable}\nimport os, sys\nprint('ARGS=' + '|'.join(sys.argv[1:]))\nprint('CWD=' + os.getcwd())\n"
                 f"sys.stderr.write('refus du serveur')\nsys.exit({code_retour})\n", "utf-8")
    f.chmod(f.stat().st_mode | stat.S_IEXEC)
    return str(f)


def test_depot_prise_et_compte_rendu(boite):
    from atelier.adapters import facade

    assert facade.atelier_demande_suivante(0)["demande"] is None and boite.etat()["ecoute"]["active"] is True
    boite.regler_envoi("boite")
    a = boite.deposer("Keywords de DEMO-1", "Vérifie les keywords du scénario DEMO-1.", ["studio_juger_keywords"], "#bdd/DEMO-1")
    b = boite.deposer("Doublons de DEMO-2", "Vérifie les doublons de l'US DEMO-2.")
    assert boite.etat()["en_attente"] == 2 and a["statut"] == "en attente"
    r = facade.atelier_demande_suivante(0)                                   # la plus ancienne d'abord
    assert r["demande"] == {"id": a["id"], "titre": "Keywords de DEMO-1", "texte": "Vérifie les keywords du scénario DEMO-1.",
                            "attendus": ["studio_juger_keywords"]} and r["restantes"] == 1 and "atelier_demande_terminee" in r["consigne"]
    with pytest.raises(ValueError, match="déjà prise"):
        boite.annuler(a["id"])
    assert boite.annuler(b["id"])["statut"] == "annulée"
    assert facade.atelier_demande_suivante(0)["demande"] is None             # une demande annulée n'est jamais servie
    fin = facade.atelier_demande_terminee(a["id"], "2 étapes jugées, 1 keyword à reprendre ; contact : test@exemple.fr")
    assert fin["statut"] == "terminée" and "atelier_demande_suivante" in fin["consigne"]
    d = {x["id"]: x for x in boite.etat()["demandes"]}
    assert d[a["id"]]["resultat"].startswith("2 étapes jugées") and "test@exemple.fr" not in d[a["id"]]["resultat"]   # résumé masqué
    with pytest.raises(ValueError, match="seule une demande prise"):
        facade.atelier_demande_terminee(a["id"], "encore")
    with pytest.raises(KeyError):
        facade.atelier_demande_terminee("DC-inconnue", "x")
    with pytest.raises(ValueError, match="vide"):
        boite.deposer("x", "  ")


def test_l_agent_attend_puis_recoit(boite, monkeypatch):
    threading.Timer(0.3, lambda: boite.deposer("Tardive", "Demande déposée pendant l'attente.", mode="boite")).start()
    t0 = time.time()
    r = boite.suivante(attente_s=5, pause=0.05)
    assert r["demande"]["titre"] == "Tardive" and 0.2 < time.time() - t0 < 3
    t0 = time.time()
    assert boite.suivante(attente_s=1, pause=0.05)["demande"] is None and 0.9 < time.time() - t0 < 2.5   # rend la main
    monkeypatch.setattr(boite, "ATTENTE_MAX_S", 1)                                                         # plafond : jamais plus (40 s en vrai)
    t0 = time.time()
    assert boite.suivante(attente_s=10_000, pause=0.05)["demande"] is None and time.time() - t0 < 2.5
    assert boite.etat()["demandes"][0]["statut"] == "prise"


def test_ligne_de_commande(boite, projet, monkeypatch, tmp_path):
    assert boite.cli()["trouvee"] is False
    with pytest.raises(FileNotFoundError, match="introuvable"):
        boite.deposer("x", "Analyse l'US DEMO-3.", mode="cli")
    assert boite.etat()["demandes"] == []                                    # commande absente : rien n'est déposé
    monkeypatch.setenv("ATELIER_CURSOR_CLI", _faux_agent(tmp_path))
    monkeypatch.setenv("ATELIER_CURSOR_CLI_ARGS", "-p --output-format text")
    with pytest.raises(ValueError, match=r"\{demande\}"):
        boite.deposer("x", "Analyse l'US DEMO-3.", mode="cli")
    monkeypatch.delenv("ATELIER_CURSOR_CLI_ARGS")
    c = boite.cli()
    assert c["trouvee"] and c["arguments"] == "-p {demande} --output-format text --approve-mcps --trust" and "--force" not in c["arguments"]
    piege = 'Analyse l\'US DEMO-3 ; rm -rf / && echo "$(whoami)" `id`'
    d = boite.deposer("Analyse", piege, mode="cli", attendre=True)
    assert d["statut"] == "terminée" and d["mode"] == "cli"
    # la demande est UN argument, tel quel : aucun shell ne l'interprète ; l'agent tourne dans le projet de tests
    assert f"ARGS=-p|{piege}|--output-format|text|--approve-mcps|--trust" in d["resultat"]
    assert f"CWD={os.path.realpath(projet)}" in d["resultat"]
    assert boite.suivante(0)["demande"] is None                              # une demande « cli » n'est jamais servie par la boîte
    monkeypatch.setenv("ATELIER_CURSOR_CLI", _faux_agent(tmp_path, code_retour=3))
    d = boite.deposer("Analyse", "Analyse l'US DEMO-4.", mode="cli", attendre=True)
    assert d["statut"] == "échouée" and d["erreur"] == "refus du serveur"


def test_routes_web(boite, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from web_app_loader import charger_app_web

    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/").status_code == 200
    e = c.get("/api/cursor/boite").json()
    assert e["en_attente"] == 0 and e["ecoute"]["active"] is False and e["cli"]["trouvee"] is False and e["envoi"] == "lien"
    assert c.post("/api/cursor/boite", json={"titre": "x", "texte": "y"}).status_code == 400              # mode « lien » : rien à déposer
    assert c.post("/api/cursor/envoi", json={"envoi": "cli"}).status_code == 400                          # commande absente sur ce poste
    assert c.post("/api/cursor/envoi", json={"envoi": "boite"}).json()["envoi"] == "boite"
    d = c.post("/api/cursor/boite", json={"titre": "Keywords", "texte": "Vérifie les keywords.", "attendus": ["studio_juger_keywords"]}).json()
    assert d["statut"] == "en attente" and c.get("/api/cursor/boite").json()["en_attente"] == 1
    assert c.post("/api/cursor/boite", json={"titre": "x", "texte": "y", "mode": "cli"}).status_code == 400   # commande absente
    assert c.post(f"/api/cursor/boite/{d['id']}/annuler").json()["statut"] == "annulée"
    assert c.post(f"/api/cursor/boite/{d['id']}/annuler").status_code == 400


def test_mode_d_envoi_regle_une_fois_pour_le_projet(boite, projet, monkeypatch, tmp_path):
    assert boite.envoi() == "lien" and set(boite.etat()["envois"]) == {"lien", "boite", "cli"}
    with pytest.raises(ValueError, match="rien n'est déposé"):
        boite.deposer("x", "Analyse l'US DEMO-5.")                           # mode « lien » : la demande s'ouvre dans le chat
    with pytest.raises(ValueError, match="Mode d'envoi"):
        boite.regler_envoi("pigeon")
    with pytest.raises(FileNotFoundError):
        boite.regler_envoi("cli")                                            # refusé tant que la commande manque sur ce poste
    assert boite.regler_envoi("boite")["envoi"] == "boite"
    assert (projet / "atelier_cursor.yaml").read_text("utf-8").strip() == "envoi: boite"      # dans le projet : toute l'équipe
    assert boite.deposer("x", "Analyse l'US DEMO-5.")["mode"] == "boite"                        # plus rien à choisir
    monkeypatch.setenv("ATELIER_CURSOR_CLI", _faux_agent(tmp_path))
    boite.regler_envoi("cli")
    assert boite.deposer("x", "Analyse l'US DEMO-6.", attendre=True)["statut"] == "terminée"
    (projet / "atelier_cursor.yaml").write_text("envoi: [illisible", "utf-8")
    assert boite.envoi() == "lien"                                           # réglage illisible : retour au chat, jamais d'erreur


def test_lanceur_windows_la_demande_passe_par_un_fichier(boite, projet, monkeypatch, tmp_path):
    """Sous Windows « agent » est un script .cmd : l'interpréteur de commandes réinterpréterait guillemets, %, & et |.
    La demande est écrite dans le projet ; l'argument n'est plus qu'une consigne courte sans caractère spécial."""
    import re

    monkeypatch.setenv("ATELIER_CURSOR_CLI", _faux_agent(tmp_path))
    assert boite._lanceur_script("/usr/bin/agent") is False                       # exécutable : argument direct, comme avant
    with monkeypatch.context() as m:                                              # os.name remis tout de suite : le reste du test tourne sous son vrai système
        m.setattr(boite.os, "name", "nt")
        assert boite._lanceur_script(r"C:\Users\x\AppData\Local\cursor-agent\agent.CMD") and not boite._lanceur_script(r"C:\outils\agent.exe")
    monkeypatch.setattr(boite, "_lanceur_script", lambda exe: True)
    piege = 'Analyse l\'US DEMO-3 "plafond" & del /q * | echo %USERPROFILE% ^ fin'
    d = boite.deposer("Analyse", piege, mode="cli", attendre=True)
    arg = d["resultat"].split("ARGS=-p|", 1)[1].split("|--output-format", 1)[0]
    assert arg == f"Lis le fichier studio/demandes_cursor/{d['id']}.md du projet et execute la demande qu il contient, avec les regles de l atelier."
    assert re.fullmatch(r"[A-Za-z0-9 ./_,-]+", arg)                               # rien que l'interpréteur de commandes puisse réinterpréter
    assert (projet / "studio" / "demandes_cursor" / f"{d['id']}.md").read_text("utf-8") == piege
    boite.regler_envoi("cli")                                                     # le réglage n'écrit aucun fichier de demande
    assert len(list((projet / "studio" / "demandes_cursor").glob("*.md"))) == 1


def test_cursor_ia_de_l_atelier_reglable_sans_variable(boite, projet, monkeypatch):
    """Les boutons « Demander à Cursor » dépendent du fournisseur d'IA : réglable dans les paramètres, sans variable
    d'environnement à taper avant de lancer l'atelier ; la variable, quand elle existe, s'impose."""
    from fastapi.testclient import TestClient

    from atelier.intelligence import fournisseur_ia
    from web_app_loader import charger_app_web

    monkeypatch.delenv("IA_FOURNISSEUR", raising=False)
    ia = boite.etat()["ia"]
    assert ia["fournisseur"] == "aucun" and ia["boutons_cursor"] is False and "cocher" in ia["aide"] and ia["impose"] == ""
    boite.regler_envoi("boite")
    assert boite.regler_ia(True)["ia"] == {"fournisseur": "cursor", "boutons_cursor": True, "impose": "", "aide": ""}
    assert fournisseur_ia.fournisseur() == "cursor" and fournisseur_ia.etat()["appel_direct"] is False
    assert (projet / "atelier_cursor.yaml").read_text("utf-8").split() == ["envoi:", "boite", "ia:", "cursor"]   # les deux réglages cohabitent
    assert boite.regler_envoi("lien")["ia"]["boutons_cursor"] is True and boite.envoi() == "lien"                # l'un n'efface pas l'autre
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/").status_code == 200
    assert c.post("/api/cursor/envoi", json={"envoi": "boite", "ia_cursor": False}).json()["ia"]["fournisseur"] == "aucun"
    assert c.post("/api/cursor/envoi", json={"envoi": "boite", "ia_cursor": True}).json()["ia"]["boutons_cursor"] is True
    # la variable de l'entreprise s'impose, et le réglage du projet ne peut pas la contourner
    monkeypatch.setenv("IA_FOURNISSEUR", "aucun")
    assert fournisseur_ia.fournisseur() == "aucun" and boite.etat()["ia"]["impose"] == "aucun"
    with pytest.raises(ValueError, match="imposé par la variable"):
        boite.regler_ia(True)
    monkeypatch.delenv("IA_FOURNISSEUR")
    (projet / "atelier_cursor.yaml").write_text("ia: anthropic\n", "utf-8")       # un fournisseur à clé ne se règle pas par fichier
    assert fournisseur_ia.fournisseur() == "aucun"


def test_agent_de_l_atelier_cursor_ou_claude_code(boite, projet, monkeypatch):
    """Passer à Claude Code : le choix est gardé pour le projet, les libellés prennent son nom, et les modes d'envoi propres
    à Cursor (lien profond, ligne de commande) basculent sur la boîte de demandes."""
    from fastapi.testclient import TestClient

    from atelier.intelligence import fournisseur_ia
    from web_app_loader import charger_app_web

    monkeypatch.delenv("IA_FOURNISSEUR", raising=False)
    assert boite.agent() == "cursor" and boite.etat()["agent_nom"] == "Cursor"          # historique : Cursor par défaut
    boite.regler_envoi("lien")
    boite.regler_ia(True)
    e = boite.regler_agent("claude_code")
    assert e["agent"] == "claude_code" and e["agent_nom"] == "Claude Code" and e["envoi"] == "boite"
    assert e["ia"]["boutons_cursor"] is True                                            # l'IA de l'atelier reste l'agent MCP
    assert fournisseur_ia.etat()["agent_nom"] == "Claude Code" and "l'agent Claude Code" in fournisseur_ia.etat()["detail"]
    with pytest.raises(ValueError, match="propre à Cursor"):
        boite.regler_envoi("lien")
    boite.regler_ia(False)
    assert "Demander à Claude Code" in boite.etat()["ia"]["aide"]
    with pytest.raises(ValueError, match="Agent"):
        boite.regler_agent("autre")
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/").status_code == 200
    r = c.post("/api/cursor/envoi", json={"agent": "cursor", "ia_cursor": True}).json()  # sans mode d'envoi : le mode courant est gardé
    assert r["agent"] == "cursor" and r["envoi"] == "boite" and r["ia"]["boutons_cursor"] is True

def test_ligne_de_commande_serveur_approuve_et_outils_autorises(boite, projet, monkeypatch, tmp_path):
    """Sans fenêtre, l'agent refuse les outils de l'atelier tant que le serveur MCP n'est pas approuvé et que ses outils
    ne sont pas autorisés : l'atelier le vérifie et le dit, au lieu de laisser la demande finir sur des refus."""
    import json
    import types
    from pathlib import Path

    assert boite.verifier_cli()["trouvee"] is False                          # commande absente : dit quoi installer
    monkeypatch.setenv("ATELIER_CURSOR_CLI", _faux_agent(tmp_path))
    vus = []

    def faux(sortie):
        def lanceur(ligne, **kw):
            vus.append((ligne[1:], kw["cwd"]))
            return types.SimpleNamespace(stdout=sortie, stderr="", returncode=0)
        return lanceur

    r = boite.verifier_cli(faux("autre: ready\n\x1b[31mappium-robot: not loaded (needs approval)\x1b[0m\n"))
    assert r["serveur"] == "a_approuver" and r["a_faire"].endswith("mcp enable appium-robot")
    assert vus[-1] == (["mcp", "list"], str(projet))                         # interrogé dans le projet de tests, sans shell
    assert boite.verifier_cli(faux("autre: ready\n"))["serveur"] == "absent"
    assert boite.verifier_cli(faux("appium-robot: error (connection refused)\n"))["serveur"] == "en_erreur"
    r = boite.verifier_cli(faux("appium-robot: ready\n"))
    assert r["serveur"] == "charge" and "Autoriser les outils" in r["a_faire"]   # chargé, mais outils pas encore autorisés

    # autorisation : les seuls outils de l'atelier, les permissions existantes du projet sont conservées
    f = Path(projet) / ".cursor" / "cli.json"
    f.parent.mkdir(exist_ok=True)
    f.write_text(json.dumps({"permissions": {"allow": ["Read(**)"], "deny": ["Shell(rm)"]}, "autre": 1}), "utf-8")
    assert boite.cli()["permissions"]["accordee"] is False
    assert boite.autoriser_outils_cli()["accordee"] is True
    conf = json.loads(f.read_text("utf-8"))
    assert conf == {"permissions": {"allow": ["Read(**)", "Mcp(appium-robot:*)"], "deny": ["Shell(rm)"]}, "autre": 1}
    boite.autoriser_outils_cli()
    assert json.loads(f.read_text("utf-8")) == conf                          # sans doublon
    assert boite.verifier_cli(faux("appium-robot: ready\n"))["a_faire"] == ""
    f.write_text("{pas du json", "utf-8")
    assert boite.cli()["permissions"]["erreur"]
    with pytest.raises(ValueError, match="illisible"):
        boite.autoriser_outils_cli()
    assert f.read_text("utf-8") == "{pas du json"                            # jamais écrasé


def test_routes_ligne_de_commande(boite, projet, monkeypatch):
    from fastapi.testclient import TestClient

    from web_app_loader import charger_app_web

    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/").status_code == 200
    assert c.post("/api/cursor/cli/verifier").json()["trouvee"] is False
    assert c.post("/api/cursor/cli/autoriser").json()["accordee"] is True
    assert c.get("/api/cursor/boite").json()["cli"]["permissions"]["accordee"] is True


def test_option_force_choix_explicite(boite, projet, monkeypatch, tmp_path):
    """--force n'est jamais mis par défaut ; l'automaticien peut l'activer pour le projet quand l'agent refuse les outils."""
    monkeypatch.setenv("ATELIER_CURSOR_CLI", _faux_agent(tmp_path))
    assert boite.cli()["force"] is False and "--force" not in boite.cli()["arguments"]
    assert boite.regler_force(True)["cli"]["force"] is True
    d = boite.deposer("Analyse", "Analyse l'US DEMO-3.", mode="cli", attendre=True)
    assert "ARGS=-p|Analyse l'US DEMO-3.|--output-format|text|--approve-mcps|--trust|--force" in d["resultat"]
    monkeypatch.setenv("ATELIER_CURSOR_CLI_ARGS", "-p {demande} --force")
    assert boite.cli()["arguments"] == "-p {demande} --force"                 # jamais en double
    monkeypatch.delenv("ATELIER_CURSOR_CLI_ARGS")
    assert boite.regler_force(False)["cli"]["force"] is False and "--force" not in boite.cli()["arguments"]
