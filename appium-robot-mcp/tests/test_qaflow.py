"""QAFlow, phase Q0 (docs/REFONTE_UI_QAFLOW.md) : la nouvelle interface coexiste avec /plateforme, même session, même API."""
import shutil
from pathlib import Path

from fastapi.testclient import TestClient
from web_app_loader import charger_app_web, module_web

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"


def test_page_qaflow_et_agregat_accueil(projet, monkeypatch, tmp_path):
    shutil.copytree(DEMO, projet, dirs_exist_ok=True, ignore=shutil.ignore_patterns("results", "connaissance", "strategie"))
    monkeypatch.setattr(module_web(), "CONFIG_PATH", tmp_path / "atelier.json")
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")

    r = c.get("/qaflow")                                       # la page pose le cookie de session, comme /plateforme
    assert r.status_code == 200 and "qaflow.js" in r.text
    assert "/qaflow" in c.get("/plateforme").text               # raccourci depuis l'interface actuelle

    a = c.get("/api/qaflow/accueil")
    assert a.status_code == 200
    d = a.json()
    assert {"application", "applications", "centre", "executions", "release", "activite"} <= set(d)
    assert not d.get("indisponibles"), d.get("indisponibles")  # chaque source se lit sur le projet de démonstration
    assert d["application"]["slug"] and len(d["executions"]) <= 5


def test_statuts_metier_quatre_seulement():
    from atelier.intelligence import qaflow

    assert qaflow.STATUTS == ("À faire", "En cours", "À valider", "Validé")
    assert qaflow.statut_parcours("Brouillon", 0, []) == "À faire"
    assert qaflow.statut_parcours("Prêt", 1, []) == "En cours"
    assert qaflow.statut_parcours("Prêt", 0, [{"cle": "x"}]) == "En cours"
    assert qaflow.statut_parcours("Exploré", 1, []) == "À valider"
    assert qaflow.statut_parcours("Validé", 1, []) == "Validé"


def test_trois_notions_distinctes():
    from atelier.intelligence import qaflow

    assert qaflow.notions(None) == {"genere": False, "execute": False, "valide_qa": False}
    # généré et exécuté, mais suite encore à valider : jamais présenté comme validé
    assert qaflow.notions({"script": True, "verifie": True, "etat": "À valider"}) == {"genere": True, "execute": True, "valide_qa": False}


def test_parcours_qaflow_liste_et_espace(projet, monkeypatch, tmp_path):
    shutil.copytree(DEMO, projet, dirs_exist_ok=True, ignore=shutil.ignore_patterns("results", "connaissance", "strategie"))
    monkeypatch.setattr(module_web(), "CONFIG_PATH", tmp_path / "atelier.json")
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    c.get("/qaflow")
    plateforme = c.get("/api/discovery/cadrage").json()["options"]["plateformes"][0]
    p = c.post("/api/discovery/cadrage", json={"nom": "Connexion client", "objectif": "Atteindre le tableau de bord",
                                               "plateforme": plateforme}).json()

    l = c.get("/api/qaflow/parcours").json()
    x = next(y for y in l if y["id"] == p["id"])
    assert x["statut"] == "À faire" and x["bdd"] == {"total": 0, "valides": 0}
    assert x["tests"] == {"generes": 0, "executes": 0, "valides_qa": 0}

    d = c.get(f"/api/qaflow/parcours/{p['id']}").json()
    assert d["nom"] == "Connexion client" and d["statut"] == "À faire"
    assert any("Aucune session" in a for a in d["alertes"])   # ce qui manque réellement, jamais « complet » à tort
    assert c.get("/api/qaflow/parcours/PU-inconnu").status_code == 400


def test_session_assistee_et_jeux_de_donnees(projet, monkeypatch, tmp_path):
    shutil.copytree(DEMO, projet, dirs_exist_ok=True, ignore=shutil.ignore_patterns("results", "connaissance", "strategie"))
    monkeypatch.setattr(module_web(), "CONFIG_PATH", tmp_path / "atelier.json")
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    c.get("/qaflow")
    plateforme = c.get("/api/discovery/cadrage").json()["options"]["plateformes"][0]
    p = c.post("/api/discovery/cadrage", json={"nom": "Connexion client", "plateforme": plateforme}).json()

    j = c.get(f"/api/qaflow/parcours/{p['id']}/jdd").json()
    assert {"environnement", "jeux", "sans_jeu", "proposees", "profil", "alertes"} <= set(j)
    assert j["fichier"].startswith("data/jdd/")

    # la session se crée, démarre, s'annote et se termine par les routes existantes ; QAFlow ne fait que lire
    s = c.post("/api/discovery/sessions", json={"parcours": p["id"], "plateforme": plateforme, "device": "navigateur"}).json()
    assert c.post(f"/api/discovery/sessions/{s['id']}/demarrer", json={}).status_code == 200
    assert c.post(f"/api/discovery/sessions/{s['id']}/annoter", json={"texte": "Page de connexion"}).status_code == 200
    d = c.get(f"/api/qaflow/session/{s['id']}").json()
    assert d["statut"] == "En cours" and d["parcours"] == p["id"] and d["compteurs"]["annotations"] == 1
    assert d["resultats"] is None and any(e["type"] == "annotation" for e in d["evenements"])
    assert c.get(f"/api/qaflow/parcours/{p['id']}").json()["session_active"] == s["id"]

    assert c.post(f"/api/discovery/sessions/{s['id']}/arreter", json={}).status_code == 200
    d = c.get(f"/api/qaflow/session/{s['id']}").json()
    assert d["statut"] == "Terminée" and d["resultats"] is not None
    e = c.get(f"/api/qaflow/parcours/{p['id']}").json()
    assert e["statut"] == "À valider" and not e["session_active"]          # exploré : les écrans attendent la validation
    assert not any("Aucune session" in a for a in e["alertes"])


def test_donnees_proposees_sans_secret(monkeypatch):
    from atelier.discovery import donnees
    from atelier.intelligence import qaflow

    monkeypatch.setattr(donnees, "propositions", lambda pid: [
        {"cle": "MDP", "nom": "Mot de passe", "type": "secret", "description": "", "valeur": "s3cret", "par": "agent"},
        {"cle": "MONTANT", "nom": "Montant", "type": "nombre", "description": "", "valeur": 120, "par": "agent"}])
    d = {"id": "PU-x", "environnement": "recette", "sessions": [], "donnees": None}
    j = qaflow.jeux_de_donnees("PU-x", d, scenarios=[])
    valeurs = {x["cle"]: x["valeur"] for x in j["proposees"]}
    assert valeurs == {"MDP": "••••", "MONTANT": 120}
    assert all(x["statut"] == "À valider" for x in j["proposees"]) and any("à confirmer" in a for a in j["alertes"])


def test_api_qaflow_refusee_sans_session():
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/api/qaflow/accueil").status_code in (401, 403)
