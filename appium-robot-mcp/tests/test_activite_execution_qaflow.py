"""QAFlow, phase Q3 : Centre d'activité IA (travaux, demandes à l'agent, session en cours) et centre d'exécution."""
import shutil
from pathlib import Path

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"

TRAVAIL = {"id": "TR-1", "titre": "Automatiser DEMO-306", "cree": "2026-11-26T09:00:00+00:00", "statut": "en_cours",
           "contexte": {"bdd": "connexion_bloquee", "travail": "TR-1", "secret": "x"},
           "etapes": [{"id": "E1", "titre": "Scénario BDD", "type": "ia", "statut": "fait", "resultat": "créé", "erreur": "", "fin": "2026-11-26T09:01:00"},
                      {"id": "E2", "titre": "Relire le scénario", "type": "humain", "statut": "attente_decision", "resultat": "", "erreur": ""},
                      {"id": "E3", "titre": "Run réel", "type": "atelier", "statut": "a_faire", "resultat": "", "erreur": ""}]}


def test_activite(projet, monkeypatch):
    shutil.copytree(DEMO, projet, dirs_exist_ok=True, ignore=shutil.ignore_patterns("results", "connaissance", "strategie"))
    from atelier.execution import orchestrateur
    from atelier.generation import suivi_automatisation
    from atelier.integrations import boite_cursor
    from atelier.intelligence import qaflow

    termine = {**TRAVAIL, "id": "TR-0", "titre": "Ancien", "statut": "echec", "cree": "2026-11-20T09:00:00+00:00",
               "etapes": [{"id": "E1", "titre": "Run", "type": "atelier", "statut": "echec", "erreur": "appareil absent", "fin": "2026-11-20T09:05"}]}
    monkeypatch.setattr(orchestrateur, "lister", lambda actifs_seulement=False: [TRAVAIL, termine])
    monkeypatch.setattr(boite_cursor, "etat", lambda limite=20: {"demandes": [
        {"id": "DC-aaaa0001", "titre": "Automatiser : « virement »", "statut": "prise", "cree": "2026-11-26T08:00:00+00:00"},
        {"id": "DC-aaaa0002", "titre": "Annulée", "statut": "annulée", "cree": "2026-11-26T07:00:00+00:00"},
        {"id": "DC-aaaa0003", "titre": "Étape d'un travail", "statut": "prise", "travail": "TR-1", "cree": "2026-11-26T09:00:00+00:00"}]})
    suivi_automatisation.enregistrer("DC-aaaa0001", "libre", "virement", "robot-web", [])
    a = qaflow.activite()
    ids = [t["id"] for t in a["taches"]]
    assert ids[0] == "TR-1"                                   # ce qui attend l'utilisateur d'abord
    assert "DC-aaaa0002" not in ids and "DC-aaaa0003" not in ids   # annulée masquée ; étape d'un travail suivie dans son travail
    t = a["taches"][0]
    assert t["etat"] == "a_decider" and t["action"] == {"type": "decider", "etape": "E2", "libelle": "Relire le scénario"}
    assert [e["statut"] for e in t["etapes"]] == ["fait", "attente_decision", "a_faire"]
    assert t["livrables"] == {"bdd": "connexion_bloquee"}       # seulement les livrables connus, jamais tout le contexte
    agent = next(x for x in a["taches"] if x["id"] == "DC-aaaa0001")
    assert agent["etat"] == "en_cours" and agent["lien"] == "#automatisation/DC-aaaa0001"   # suivi QAFlow de l'automatisation
    ancien = next(x for x in a["taches"] if x["id"] == "TR-0")
    assert ancien["etat"] == "echec" and ancien["erreur"] == "appareil absent" and ids.index("TR-0") > ids.index("DC-aaaa0001")
    assert a["compteurs"] == {"a_decider": 1, "en_cours": 1}


def test_execution_et_routes(projet, monkeypatch, tmp_path):
    shutil.copytree(DEMO, projet, dirs_exist_ok=True, ignore=shutil.ignore_patterns("connaissance", "strategie"))
    from fastapi.testclient import TestClient
    from web_app_loader import charger_app_web, module_web

    from atelier.intelligence import qaflow

    x = qaflow.execution()
    assert set(x["compteurs"]) == {"en_cours", "en_file", "executions", "reussies", "en_echec", "tests_passes", "tests_echoues"}
    assert all(isinstance(v, int) for v in x["compteurs"].values())   # des nombres, jamais un pourcentage
    assert x["compteurs"]["executions"] == len(x["recents"])
    monkeypatch.setattr(module_web(), "CONFIG_PATH", tmp_path / "atelier.json")
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    c.get("/qaflow")
    assert c.get("/api/qaflow/execution").status_code == 200
    r = c.get("/api/qaflow/activite")
    assert r.status_code == 200 and set(r.json()) == {"taches", "compteurs"}
