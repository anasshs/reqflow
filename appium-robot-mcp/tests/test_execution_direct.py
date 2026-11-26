"""Exécution en direct tenue côté serveur : tests connus d'avance « en attente », test et keyword en cours, échec avec
son message, fin du run ; un écran ouvert en cours de run relit tout l'état."""
from __future__ import annotations


def test_suivi_d_un_run_du_lancement_au_bilan():
    from atelier.execution import direct

    direct.reinitialiser()
    direct.demarrer("RUN-20261123-120000", "tests/a.robot", ["tests/a.robot::Test un", "tests/a.robot::Test deux"], "Vérification")
    e = direct.etat()["en_cours"]
    assert e["total"] == 2 and e["compte"]["en attente"] == 2 and e["tests"][0]["fichier"] == "tests/a.robot"

    direct.observer({"type": "run_lance", "run_id": "RUN-20261123-120000"})  # même run : rien n'est remis à zéro
    direct.observer({"type": "run_debut", "tests": [{"id": "s1-t1", "nom": "Test un"}, {"id": "s1-t2", "nom": "Test deux"}]})
    direct.observer({"type": "test_debut", "id": "s1-t1", "nom": "Test un"})
    direct.observer({"type": "kw_debut", "nom": "Given que je suis connecté", "niveau": 1})
    direct.observer({"type": "kw_debut", "nom": "AppiumLibrary.Input Password", "args": ["${LOCATOR}", "${JDD}[mot_de_passe]"], "niveau": 3})
    e = direct.etat()["en_cours"]
    assert e["courant"] == "Test un" and e["etape"] == "Given que je suis connecté"
    assert e["keyword"] == "AppiumLibrary.Input Password" and e["compte"]["en cours"] == 1

    direct.observer({"type": "test_fin", "id": "s1-t1", "nom": "Test un", "statut": "FAIL", "message": "Tableau de bord : non affiché",
                     "keyword_en_echec": "Then le tableau de bord est affiché"})
    direct.observer({"type": "test_debut", "id": "s1-t2", "nom": "Test deux"})
    direct.observer({"type": "test_fin", "id": "s1-t2", "nom": "Test deux", "statut": "PASS"})
    e = direct.etat()["en_cours"]
    assert e["termines"] == 2 and e["compte"]["échec"] == 1 and e["compte"]["réussi"] == 1 and e["courant"] == ""
    un = next(t for t in e["tests"] if t["nom"] == "Test un")
    assert un["message"] == "Tableau de bord : non affiché" and un["keyword_en_echec"].startswith("Then")

    direct.observer({"type": "run_bilan", "run_id": "RUN-20261123-120000", "bilan": {"resultat": {"passes": 1, "echecs": 1}}})
    etat = direct.etat()
    assert etat["en_cours"] is None and etat["dernier"]["statut"] == "terminé"


def test_run_qui_ne_se_lance_pas():
    from atelier.execution import direct

    direct.reinitialiser()
    direct.demarrer("RUN-20261123-130000", "tests/a.robot", ["tests/a.robot::Test un"])
    direct.observer({"type": "run_bilan", "bilan": {"statut": "erreur", "erreur": "mapping values are not allowed"}})
    d = direct.etat()["dernier"]
    assert d["statut"] == "erreur" and "mapping values" in d["erreur"] and d["tests"][0]["statut"] == "non exécuté"


def test_evenements_hors_run_ignores():
    from atelier.execution import direct

    direct.reinitialiser()
    direct.observer({"type": "test_debut", "nom": "orphelin"})
    direct.observer({"type": "mcp_outil", "nom": "tap"})
    assert direct.etat() == {"en_cours": None, "dernier": None}
