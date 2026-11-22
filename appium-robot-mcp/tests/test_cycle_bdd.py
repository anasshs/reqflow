"""Avancement d'un test BDD (scénario, script, run réel, validation) : les écrans n'offrent que l'étape suivante."""
from __future__ import annotations

from atelier.generation import maintenance


def _vue(*suites):
    return {"suites": [{"fichier": f, "etat": etat, "tests": [{"id": f"{f}::{i}", "verifie": v, "bdd": [cle]} for i, v in enumerate(verifs)]}
                       for f, etat, cle, verifs in suites]}


def test_cycle_et_etape_suivante():
    v = _vue(("a.robot", "Validé", "parcours_a", [True]), ("b.robot", "À valider", "parcours_b", [True, False]),
             ("c.robot", "À valider", "parcours_c", [True]))
    c = maintenance.cycle_bdd(v)
    assert c["parcours_a"] == {"script": True, "suites": ["a.robot"], "etat": "Validé", "tests": 1, "verifies": 1, "verifie": True}
    assert c["parcours_b"]["verifies"] == 1 and c["parcours_b"]["verifie"] is False
    etape = lambda cle, statut="validé": maintenance.etape_bdd({"statut": statut}, c.get(cle))["etape"]  # noqa: E731
    assert etape("parcours_a") == "fait"
    assert etape("parcours_a", "brouillon") == "fait"        # script écrit, vérifié, validé : rien à refaire, même scénario resté brouillon
    assert etape("parcours_b") == "verifier"
    assert etape("parcours_c") == "valider_test"
    assert etape("sans_script") == "generer"
    assert etape("sans_script", "brouillon") == "valider_bdd"


def test_suite_a_valider_l_emporte_sur_une_suite_validee():
    v = _vue(("a.robot", "Validé", "k", [True]), ("b.robot", "À valider", "k", [True]))
    assert maintenance.cycle_bdd(v)["k"]["etat"] == "À valider"


def test_test_bdd_relie_a_son_parcours():
    p = {"id": "PU-menu_docs", "noeud": "parcours:menu_docs", "nom": "Menu Docs", "sessions_ids": ["DS-1"]}
    assert maintenance.du_parcours({"cle": "x", "parcours": "PU-menu_docs"}, p)
    assert maintenance.du_parcours({"cle": "x", "parcours": "parcours:menu_docs"}, p)
    assert maintenance.du_parcours({"cle": "x", "session": "DS-1"}, p)
    assert maintenance.du_parcours({"cle": "parcours_menu_docs_2"}, p)          # sans lien enregistré : la clé donnée à la création
    assert not maintenance.du_parcours({"cle": "parcours_menu_docs_bis"}, p)
    assert not maintenance.du_parcours({"cle": "parcours_menu_docs", "parcours": "PU-autre"}, p)  # lien enregistré vers un autre parcours


def test_test_design_compte_les_tests_concus_dans_l_atelier(monkeypatch):
    """Sans Xray, la vue d'ensemble de Test Design affichait 0 approuvé, 0 prêt, 0 automatisé : les tests BDD de l'atelier comptent."""
    from atelier.generation import bdd, conception

    l = [{"cle": "a", "statut": "brouillon"}, {"cle": "b", "statut": "validé"}, {"cle": "c", "statut": "validé"},
         {"cle": "d", "statut": "brouillon"}, {"cle": "XR-1", "statut": "validé"}]
    monkeypatch.setattr(bdd, "lister", lambda: l)
    monkeypatch.setattr(maintenance, "cycle_bdd", lambda v=None: {
        "c": {"script": True, "suites": ["c.robot"], "etat": "Validé", "tests": 1, "verifies": 1, "verifie": True},
        "d": {"script": True, "suites": ["d.robot"], "etat": "À valider", "tests": 1, "verifies": 0, "verifie": False}})
    at = conception.tests_atelier({"XR-1"})                        # XR-1 vient d'un cas Xray : compté côté Xray, pas deux fois
    assert at["total"] == 4
    assert (at["a_revoir"], at["approuves"], at["prets_automatisation"], at["automatises"]) == (1, 2, 1, 2)
    assert at["par_etape"] == {"Scénario à valider": 1, "Script à générer": 1, "À vérifier (run réel)": 1, "Test à valider": 0,
                               "Automatisé, vérifié, validé": 1}
