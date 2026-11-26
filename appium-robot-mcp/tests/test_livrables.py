"""Livrables de l'Accueil : volumes réels (créé / validé / en attente), date de mise à jour, une source illisible n'empêche
pas les autres cartes, jamais de pourcentage."""
from __future__ import annotations


def test_scenarios_bdd_en_volumes(monkeypatch):
    from atelier.generation import bdd
    from atelier.intelligence import livrables

    monkeypatch.setattr(bdd, "lister", lambda: [{"cle": "a", "statut": "validé", "scenarios": 3, "maj": "2026-11-20T10:00:00"},
                                                {"cle": "b", "statut": "brouillon", "scenarios": 2, "maj": "2026-11-22T09:25:00"}])
    c = livrables.scenarios_bdd()
    assert {i["cle"]: i["valeur"] for i in c["indicateurs"]} == {"total": 5, "valides": 3, "en_attente": 2}
    assert c["maj"] == "2026-11-22T09:25:00" and "2 test(s) BDD" in c["note"]


def test_anomalies_ouvertes_en_cours_cloturees(monkeypatch):
    from atelier.discovery import entites
    from atelier.intelligence import livrables, pilotage

    monkeypatch.setattr(pilotage, "_bugs", lambda: [{"cle": "BUG-1", "statut": "Done", "ferme": True}])
    monkeypatch.setattr(pilotage, "_etat_bug", lambda b: "ferme")
    monkeypatch.setattr(entites, "anomalies", lambda g=None: [
        {"id": "bug:BUG-1", "id_jira": "BUG-1", "statut": "Ouvert"},           # déjà compté depuis Xray
        {"id": "bug:FA-1", "id_jira": "", "statut": "", "date_detection": "2026-11-21"},
        {"id": "bug:FA-2", "id_jira": "", "statut": "En cours d'analyse"},
        {"id": "bug:FA-3", "id_jira": "", "statut": "Corrigé"}])
    c = livrables.anomalies()
    assert {i["cle"]: i["valeur"] for i in c["indicateurs"]} == {"ouvertes": 1, "en_cours": 1, "cloturees": 2}


def test_une_source_illisible_n_empeche_pas_les_autres(monkeypatch):
    from atelier.intelligence import livrables

    def casse():
        raise OSError("carte illisible")

    ok = lambda: {"indicateurs": [livrables._ind("x", "X", 4, "#x", "déf")], "maj": ""}  # noqa: E731
    monkeypatch.setattr(livrables, "CARTES", (("discovery", "Discovery", "recherche", "#discovery", "application", casse),
                                              ("bdd", "Scénarios BDD", "bdd", "#bdd", "projet", ok)))
    monkeypatch.setattr(livrables, "_app", lambda: ("app", "App"))
    r = livrables.livrables()
    assert [c["disponible"] for c in r["cartes"]] == [False, True]
    assert r["cartes"][0]["raison"] == "carte illisible"
    assert all(isinstance(i["valeur"], int) and "%" not in i["libelle"] for c in r["cartes"] for i in c["indicateurs"])
    assert all(c["lien"].startswith("#") for c in r["cartes"])
