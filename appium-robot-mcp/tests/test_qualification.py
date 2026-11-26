"""Accueil de l'application : statut des six étapes de qualification (déduit de ce qui existe), activités récentes."""
from __future__ import annotations


def _bdd(monkeypatch, l):
    from atelier.generation import bdd

    monkeypatch.setattr(bdd, "lister", lambda: l)


def test_concevoir_statut_selon_les_scenarios(monkeypatch):
    from atelier.intelligence import qualification as q

    _bdd(monkeypatch, [])
    assert q._concevoir()["statut"] == "non_demarre"
    _bdd(monkeypatch, [{"cle": "a", "statut": "validé", "scenarios": 4, "maj": "2026-11-22T10:00:00"},
                       {"cle": "b", "statut": "brouillon", "scenarios": 2, "maj": ""}])
    c = q._concevoir()
    assert c["statut"] == "a_completer"
    assert [d["texte"] for d in c["details"]] == ["4 scénario(s) validé(s)", "2 à examiner"]
    _bdd(monkeypatch, [{"cle": "a", "statut": "validé", "scenarios": 4, "maj": ""}])
    assert q._concevoir()["statut"] == "valide"


def test_executer_statut_selon_le_dernier_run(monkeypatch):
    from atelier.execution import centre, historique
    from atelier.intelligence import qualification as q

    monkeypatch.setattr(centre.FILE, "en_cours", None, raising=False)
    monkeypatch.setattr(historique, "lister", lambda n=50: [])
    assert q._executer()["statut"] == "non_demarre"
    run = lambda e, d: {"statut": "échec" if e else "réussi", "passes": 3, "echecs": e, "dry_run": False, "debut": d, "fin": d}  # noqa: E731
    monkeypatch.setattr(historique, "lister", lambda n=50: [run(1, "2026-11-22T10:00:00"), run(0, "2026-11-21T10:00:00")])
    assert q._executer()["statut"] == "a_completer"
    monkeypatch.setattr(historique, "lister", lambda n=50: [run(0, "2026-11-22T10:00:00"), run(1, "2026-11-21T10:00:00")])
    e = q._executer()
    assert e["statut"] == "valide" and e["maj"] == "2026-11-22T10:00:00"


def test_une_etape_illisible_n_empeche_pas_les_autres(monkeypatch):
    from atelier.intelligence import qualification as q

    def casse():
        raise OSError("carte illisible")

    monkeypatch.setattr(q, "CALCULS", {**{k: (lambda: {"statut": "a_la_demande", "details": [], "maj": ""}) for k in q.CALCULS}, "comprendre": casse})
    l = q.etapes()
    assert [e["num"] for e in l] == [1, 2, 3, 4, 5, 6]
    assert l[0]["statut"] == "indisponible" and l[0]["details"][0]["texte"] == "carte illisible"
    assert all(e["statut_libelle"] for e in l)
    assert not any("%" in d["texte"] for e in l for d in e["details"])  # jamais de pourcentage


def test_activites_les_plus_recentes_d_abord(monkeypatch):
    from atelier.intelligence import qualification as q

    _bdd(monkeypatch, [{"cle": "a", "titre": "Connexion", "statut": "validé", "scenarios": 1, "maj": "2026-11-22T09:25:00+00:00"},
                       {"cle": "b", "titre": "Démo", "statut": "brouillon", "scenarios": 1, "maj": "2026-11-21T16:40:00+00:00"}])
    from atelier.execution import historique

    monkeypatch.setattr(historique, "lister", lambda n=50: [{"id": "RUN-1", "statut": "réussi", "suite": "tests/a.robot", "passes": 2, "echecs": 0,
                                                             "dry_run": False, "debut": "2026-11-22T10:00:00+00:00", "fin": "2026-11-22T10:05:00+00:00"}])
    monkeypatch.setattr(q, "_app", lambda: ("", ""))
    l = q.activites(3)
    assert [x["titre"] for x in l] == ["Run réussi", "Scénario BDD validé", "Scénario BDD modifié"]
    assert l[0]["lien"] == "#centre/historique/RUN-1" and l[1]["lien"] == "#bdd/a"
