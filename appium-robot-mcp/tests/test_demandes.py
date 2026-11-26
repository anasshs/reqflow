"""Mes demandes : travaux de l'orchestrateur et demandes déposées à l'agent, en une liste, ce qui attend l'utilisateur
d'abord ; une demande née d'un travail n'est pas listée deux fois."""
from atelier.execution import demandes, orchestrateur
from atelier.integrations import boite_cursor


def _travail(tid, statut, etapes, cree):
    return {"id": tid, "titre": f"Travail {tid}", "statut": statut, "cree": cree, "origine": {"ecran": "#graphe"},
            "etapes": [{"id": f"E{i}", "titre": t, "statut": s, "erreur": ""} for i, (t, s) in enumerate(etapes)]}


def test_liste_unifiee(monkeypatch):
    travaux = [
        _travail("TR-1", "en_cours", [("BDD", "fait"), ("Valider le script", "attente_decision")], "2026-11-24T10:00:00"),
        _travail("TR-2", "termine", [("Run", "fait")], "2026-11-24T09:00:00"),
        _travail("TR-3", "en_cours", [("BDD", "fait"), ("Run", "attente_ressource")], "2026-11-24T11:00:00"),
    ]
    boite = [{"id": "DC-a", "titre": "Automatiser DEMO-12 (MBT)", "statut": "en attente", "cree": "2026-11-24T12:00:00", "ecran": "#comportement", "mode": "boite"},
             {"id": "DC-b", "titre": "Corriger", "statut": "échouée", "cree": "2026-11-24T08:00:00", "ecran": "#tests", "erreur": "agent arrêté", "mode": "cli"},
             {"id": "DC-c", "titre": "Étape d'un travail", "statut": "prise", "cree": "2026-11-24T12:30:00", "travail": "TR-3", "mode": "boite"}]
    monkeypatch.setattr(orchestrateur, "lister", lambda actifs_seulement=False: travaux)
    monkeypatch.setattr(boite_cursor, "etat", lambda limite=20: {"demandes": boite})
    r = demandes.lister()
    ids = [x["id"] for x in r["demandes"]]
    assert ids[0] == "TR-1" and r["demandes"][0]["etat"] == "a_decider"      # ce qui attend l'utilisateur d'abord
    assert "DC-c" not in ids                                                  # suivie dans son travail
    assert ids.index("TR-3") < ids.index("DC-a")                              # en cours avant en attente
    tr3 = next(x for x in r["demandes"] if x["id"] == "TR-3")
    assert "téléphone" in tr3["etape"] and tr3["avancement"] == [1, 2]
    dca = next(x for x in r["demandes"] if x["id"] == "DC-a")
    assert dca["etat"] == "en_attente" and dca["origine"] == "#comportement" and dca["source"] == "agent"
    assert next(x for x in r["demandes"] if x["id"] == "DC-b")["etat"] == "echec"
    assert r["compteurs"] == {"a_decider": 1, "en_cours": 2, "echec": 1}


def test_boite_illisible_les_travaux_restent(monkeypatch):
    monkeypatch.setattr(orchestrateur, "lister", lambda actifs_seulement=False: [_travail("TR-9", "echec", [("Run", "echec")], "2026-11-24T10:00:00")])

    def casse(limite=20):
        raise OSError("illisible")
    monkeypatch.setattr(boite_cursor, "etat", casse)
    r = demandes.lister()
    assert [x["id"] for x in r["demandes"]] == ["TR-9"] and r["demandes"][0]["etat"] == "echec"


def test_demande_a_l_agent_pas_prise_n_est_pas_en_cours(monkeypatch):
    t = _travail("TR-5", "en_cours", [("Écrire le test Robot", "en_cours")], "2026-11-24T10:00:00")
    t["etapes"][0].update(type="ia", demande="DC-x")
    monkeypatch.setattr(orchestrateur, "lister", lambda actifs_seulement=False: [t])
    boite = [{"id": "DC-x", "titre": "Écrire le test Robot", "statut": "en attente", "cree": "2026-11-24T10:00:01", "travail": "TR-5", "mode": "boite"}]
    monkeypatch.setattr(boite_cursor, "etat", lambda limite=20: {"demandes": boite})
    monkeypatch.setattr(boite_cursor, "pret", lambda: {"pret": False, "raison": "Claude Code n'est pas connecté sur ce poste",
                                                       "a_faire": "claude, puis /login", "comment": ""})
    r = demandes.lister()
    (x,) = r["demandes"]
    assert x["etat"] == "en_attente" and "pas connecté" in x["etape"] and x["demande"]["statut"] == "en attente"
    assert r["agent"]["pret"] is False and r["agent"]["en_attente"] == 1
    boite[0].update(statut="prise", pris="2026-11-24T10:01:00")
    (x,) = demandes.lister()["demandes"]
    assert x["etat"] == "en_cours" and "y travaille" in x["etape"]
