"""Saisir et vérifier depuis le miroir de l'écran pendant une session Discovery (QAFlow) : chaque valeur saisie ou
attendue devient une donnée du jeu du parcours (modifiable ensuite), et le scénario BDD généré reprend saisies et
vérifications sans aucune valeur littérale."""
import shutil
from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"

ECRAN = [{"key": "identifiant", "type": "champ", "libelle": "Identifiant", "locators": ["id=identifiant"]},
         {"key": "mot_de_passe", "type": "champ", "libelle": "Mot de passe", "locators": ["id=mot_de_passe"]},
         {"key": "message_erreur", "type": "texte", "libelle": "Identifiant ou mot de passe incorrect.", "locators": ["id=message_erreur"]}]


@pytest.fixture
def env(projet, monkeypatch):
    shutil.copytree(DEMO, projet, dirs_exist_ok=True, ignore=shutil.ignore_patterns("results", "connaissance", "strategie"))
    from atelier.discovery import actions, comportements, observation, parcours_utilisateur, session, sessions_discovery
    from atelier.domain import coffre

    saisies = []
    monkeypatch.setattr(session, "plateforme", lambda: "web")
    monkeypatch.setattr(comportements, "etat_ecran", lambda: [dict(e) for e in ECRAN])
    monkeypatch.setattr(observation, "observer", lambda els: {"id": "ECRAN_CONNEXION"})
    monkeypatch.setattr(actions, "type_text", lambda loc, texte, affiche=None, **k: saisies.append((loc, texte, affiche)))
    monkeypatch.setattr(coffre, "disponible", lambda: False)  # jamais le vrai coffre du poste pendant les tests
    plat = parcours_utilisateur.options()["plateformes"][0]
    p = parcours_utilisateur.enregistrer("", {"nom": "Connexion client", "plateforme": plat})
    s = sessions_discovery.creer({"parcours": p["id"], "plateforme": plat, "device": "navigateur"})
    sessions_discovery.demarrer(s["id"])
    return {"p": p, "s": s, "saisies": saisies, "projet": projet}


def test_saisie_devient_donnee_du_parcours(env):
    from atelier.discovery import donnees, sessions_discovery

    r = sessions_discovery.saisir("id=identifiant", "client.demo", ECRAN[0])
    assert r["variable"] == "IDENTIFIANT" and r["valeur"] == "client.demo" and r["profil"]
    # la saisie se fait avec la vraie valeur, mais seule la référence est journalisée
    assert env["saisies"] == [("id=identifiant", "client.demo", "{{var:IDENTIFIANT}}")]
    v = next(x for x in donnees.variables(profil=r["profil"]) if x["cle"] == "IDENTIFIANT")
    assert v["valeurs"]["profils"][r["profil"]] == "client.demo"
    s = sessions_discovery._lire(env["s"]["id"])
    assert s["saisies"][0]["variable"] == "IDENTIFIANT" and s["saisies"][0]["ecran"] == "ECRAN_CONNEXION"
    assert "client.demo" not in str(s["saisies"])


def test_saisie_secrete_jamais_en_clair(env):
    from atelier.discovery import sessions_discovery

    r = sessions_discovery.saisir("id=mot_de_passe", "Secret#2026", ECRAN[1])
    assert r["secret"] and r["valeur"] == "••••"
    fichiers = "".join(f.read_text("utf-8") for f in (env["projet"] / "data").rglob("*.yaml"))
    assert "Secret#2026" not in fichiers
    assert "Secret#2026" not in (env["projet"] / "discovery").joinpath("sessions", f"{env['s']['id']}.jsonl").read_text("utf-8")


def test_verifications_et_corrections(env):
    from atelier.discovery import donnees, sessions_discovery

    sid = env["s"]["id"]
    t = sessions_discovery.verifier("id=message_erreur", "texte", ECRAN[2], nom="Message erreur")
    assert t["variable"] == "ATTENDU_MESSAGE_ERREUR" and t["conforme"] is True
    assert donnees.variables("ATTENDU_MESSAGE_ERREUR")[0]["valeurs"]["profils"]  # valeur attendue dans le jeu du parcours
    autre = sessions_discovery.verifier("id=message_erreur", "texte", ECRAN[2], attendu="Autre texte", nom="Message erreur bis")
    assert autre["conforme"] is False   # attendu donné par l'automaticien, différent de l'écran : consigné tel quel
    sessions_discovery.verifier("id=identifiant", "visible", ECRAN[0])
    assert len(sessions_discovery._lire(sid)["assertions"]) == 3
    with pytest.raises(ValueError):
        sessions_discovery.verifier("id=identifiant", "inconnu", ECRAN[0])

    r = sessions_discovery.corriger_consigne(sid, "assertions", 1, retirer=True)
    assert [a["element"] for a in r["assertions"]] == ["Message erreur", "Identifiant"]
    r = sessions_discovery.corriger_consigne(sid, "assertions", 1, mode="texte", element="Champ identifiant")
    assert r["assertions"][1]["element"] == "Champ identifiant" and r["assertions"][1]["corrige"]


def test_hors_session_refuse(env):
    from atelier.discovery import sessions_discovery

    sessions_discovery.arreter(env["s"]["id"])
    with pytest.raises(PermissionError):
        sessions_discovery.saisir("id=identifiant", "x", ECRAN[0])


def test_scenario_bdd_reprend_saisies_et_verifications(env):
    from atelier.discovery import sessions_discovery
    from atelier.generation import parcours_bdd

    sid = env["s"]["id"]
    sessions_discovery.saisir("id=identifiant", "client.demo", ECRAN[0])
    # l'action réelle est journalisée par l'observation (type_text simulé ici) : même forme que session.action_faite
    sessions_discovery._evenement(sid, {"type": "action", "detail": 'type_text {"locator": "id=identifiant", "text": "{{var:IDENTIFIANT}}"}'})
    sessions_discovery.verifier("id=message_erreur", "texte", ECRAN[2], nom="Message erreur")
    sessions_discovery.verifier("id=identifiant", "visible", ECRAN[0], nom="Champ identifiant")
    sessions_discovery.corriger_consigne(sid, "assertions", 1, retirer=True)  # retirée : pas d'étape

    etapes, _ = parcours_bdd.etapes_de_session(sid, "web", {"IDENTIFIANT": "Identifiant", "ATTENDU_MESSAGE_ERREUR": "message attendu"})
    textes = [(e["type"], e["texte"]) for e in etapes]
    assert ("and", "je renseigne identifiant avec la donnée Identifiant") in textes
    alors = [e for e in etapes if e["type"] == "then"]
    assert [e["texte"] for e in alors] == ["message erreur affiche la donnée message attendu"]
    assert alors[0]["variable"] == "ATTENDU_MESSAGE_ERREUR" and alors[0]["assertion"] and alors[0]["locator"] == "id=message_erreur"
    assert "client.demo" not in str(etapes) and "incorrect" not in str(etapes)  # aucune donnée littérale


def test_jeu_des_tests_tenu_a_jour(env):
    from atelier.discovery import sessions_discovery
    from atelier.execution import jdd

    r = sessions_discovery.saisir("id=identifiant", "client.demo", ECRAN[0])
    assert r["jdd"]["a_jour"], r["jdd"]
    jeu = r["jdd"]["jeu"]
    assert jdd.lire(r["jdd"]["env"], jeu)["donnees"]["identifiant"] == "client.demo"
    sessions_discovery.saisir("id=mot_de_passe", "Secret#2026", ECRAN[1])
    d = jdd.lire(r["jdd"]["env"], jeu)["donnees"]
    assert d["mot_de_passe"] == "{{env:MOT_DE_PASSE}}"   # secret : jamais la valeur dans le jeu des tests


def test_donnee_existante_du_catalogue_ou_d_un_jeu(env):
    from atelier.discovery import donnees, sessions_discovery

    choix = donnees.donnees_pour_saisie(env["p"]["id"], "Identifiant")
    jeux = {j["jeu"]: {c["champ"]: c for c in j["champs"]} for j in choix["jeux"]}
    assert jeux["CLIENT_ACTIF"]["identifiant"]["valeur"] == "client.demo"
    assert jeux["CLIENT_ACTIF"]["mot_de_passe"]["valeur"] == "••••" and jeux["CLIENT_ACTIF"]["mot_de_passe"]["secret"]

    r = sessions_discovery.saisir("id=identifiant", element=ECRAN[0], depuis={"jdd": "IDENTIFIANT_INCONNU", "champ": "identifiant"})
    assert r["variable"] == "IDENTIFIANT" and r["source"] == "jdd IDENTIFIANT_INCONNU.identifiant"
    assert env["saisies"][-1] == ("id=identifiant", "client.inconnu", "{{var:IDENTIFIANT}}")
    r = sessions_discovery.saisir("id=mot_de_passe", element=ECRAN[1], depuis={"jdd": "CLIENT_ACTIF", "champ": "mot_de_passe"})
    assert r["secret"] and r["valeur"] == "••••"       # repris d'un jeu, mais rangé comme secret

    donnees.enregistrer_variable("LOGIN_COMMUN", {"nom": "Login commun", "type": "texte"})
    donnees.definir_valeur("LOGIN_COMMUN", "commun.demo")
    r = sessions_discovery.saisir("id=identifiant", element=ECRAN[0], depuis={"variable": "LOGIN_COMMUN"})
    assert r["source"] == "catalogue" and env["saisies"][-1] == ("id=identifiant", "commun.demo", "{{var:LOGIN_COMMUN}}")
    assert "LOGIN_COMMUN" in {v["cle"] for v in donnees.variables(profil=r["profil"])}
    assert donnees.variable("LOGIN_COMMUN")["nom"] == "Login commun"   # existante : inchangée
    with pytest.raises(KeyError):
        sessions_discovery.saisir("id=identifiant", element=ECRAN[0], depuis={"variable": "INCONNUE"})


def test_onglet_ajouter_modifier_retirer(env, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from web_app_loader import charger_app_web, module_web

    monkeypatch.setattr(module_web(), "CONFIG_PATH", tmp_path / "atelier.json")
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    c.get("/qaflow")
    pid = env["p"]["id"]
    r = c.post(f"/api/qaflow/parcours/{pid}/donnee", json={"cle": "MONTANT", "nom": "Montant", "valeur": "120"})
    assert r.status_code == 200 and r.json()["jdd"]["a_jour"]
    r = c.post(f"/api/qaflow/parcours/{pid}/donnee", json={"cle": "MONTANT", "valeur": "250"})   # modifier à tout moment
    assert r.status_code == 200
    j = c.get(f"/api/qaflow/parcours/{pid}/jdd").json()
    assert {v["cle"]: v["valeur"] for v in j["variables"]}["MONTANT"] == "250"
    assert j["jeu_du_parcours"]["present"] and "montant" in j["jeu_du_parcours"]["champs"]
    from atelier.discovery import donnees

    donnees.enregistrer_variable("DEVISE", {"nom": "Devise", "type": "texte"})
    donnees.definir_valeur("DEVISE", "MAD")
    assert c.post(f"/api/qaflow/parcours/{pid}/donnee", json={"cle": "DEVISE", "existante": True}).status_code == 200
    assert "DEVISE" in {v["cle"] for v in c.get(f"/api/qaflow/parcours/{pid}/jdd").json()["variables"]}
    r = c.post(f"/api/qaflow/parcours/{pid}/donnee/retirer", json={"cle": "DEVISE"})
    assert r.status_code == 200
    assert "DEVISE" not in {v["cle"] for v in c.get(f"/api/qaflow/parcours/{pid}/jdd").json()["variables"]}
    assert donnees.variable("DEVISE")   # reste au catalogue
    assert c.post(f"/api/qaflow/parcours/{pid}/donnee/retirer", json={"cle": "DEVISE"}).status_code == 400
    s = c.get(f"/api/qaflow/donnees-saisie?parcours={pid}&libelle=Montant").json()
    assert "MONTANT" in {v["cle"] for v in s["du_parcours"]}


def test_routes_web(env, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from web_app_loader import charger_app_web, module_web

    monkeypatch.setattr(module_web(), "CONFIG_PATH", tmp_path / "atelier.json")
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    c.get("/qaflow")
    r = c.post("/api/discovery/saisir", json={"locator": "id=identifiant", "valeur": "client.demo", "element": ECRAN[0]})
    assert r.status_code == 200 and r.json()["variable"] == "IDENTIFIANT"
    r = c.post("/api/discovery/verifier", json={"locator": "id=message_erreur", "mode": "texte", "element": ECRAN[2], "nom": "Message erreur"})
    assert r.status_code == 200 and r.json()["variable"] == "ATTENDU_MESSAGE_ERREUR"
    j = c.get(f"/api/qaflow/parcours/{env['p']['id']}/jdd").json()
    assert {v["cle"] for v in j["variables"]} >= {"IDENTIFIANT", "ATTENDU_MESSAGE_ERREUR"}
    assert len(j["consignes"]["saisies"]) == 1 and len(j["consignes"]["assertions"]) == 1
    sid = env["s"]["id"]
    r = c.post(f"/api/discovery/consignes/{sid}", json={"liste": "assertions", "index": 0, "retirer": True})
    assert r.status_code == 200 and r.json()["assertions"] == []
    assert c.post(f"/api/discovery/consignes/{sid}", json={"liste": "autre", "index": 0}).status_code == 400
