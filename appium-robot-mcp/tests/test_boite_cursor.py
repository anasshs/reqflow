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
