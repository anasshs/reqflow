"""Mapping des statuts des tickets (Test, Test Execution, Test Plan, Bug), réglé par projet : rien n'est deviné d'après
le nom d'un statut ; un statut non relié garde l'ancien repli et reste signalé."""
from __future__ import annotations

import pytest

from tests.test_pilotage import pil  # noqa: F401 — projet d'exemple : tests, exécution DEMO-900, bugs DEMO-500 (Ouvert) et DEMO-501 (Terminé)
from tests.test_intelligence_couverture import ci  # noqa: F401


def test_mapping_par_projet(pil, tmp_path):  # noqa: F811
    from atelier.domain import statuts

    e = statuts.etat()
    par = {t["id"]: t for t in e["types"]}
    assert not e["regle"] and [t["libelle"] for t in e["types"]] == ["Test", "Test Execution", "Test Plan", "Bug"]
    assert {s["statut"]: s["tickets"] for s in par["bug"]["statuts"]} == {"Ouvert": 1, "Terminé": 1}      # vus dans les copies locales
    assert par["execution"]["statuts"][0]["statut"] == "En cours" and par["bug"]["sans_correspondance"] == ["Ouvert", "Terminé"]
    assert statuts.categorie("bug", "Ouvert") == "" and statuts.ferme("bug", "Ouvert") is None             # non relié : pas d'avis
    with pytest.raises(ValueError, match="Catégorie inconnue"):
        statuts.enregistrer(correspondances={"bug": {"Ouvert": "en_vacances"}})
    with pytest.raises(ValueError, match="Type de ticket inconnu"):
        statuts.enregistrer(types={"epic": "Epic"})
    e = statuts.enregistrer(types={"bug": "Anomalie"}, correspondances={
        "bug": {"Ouvert": "ouvert", "Terminé": "ferme", "Réouvert": "reouvert", "Rejeté": "rejete", "Sans objet": ""},
        "execution": {"En cours": "en_cours", "Clôturée": "terminee"}, "plan": {"Abandonné": "annule", "Ouvert": "en_cours"},
        "test": {"Prêt": "redige", "À automatiser": "a_automatiser", "Validé": "redige"}})
    assert e["regle"] and (tmp_path / "atelier_statuts.yaml").exists() and e["sans_correspondance"] == 0
    assert {t["id"]: t["type_jira"] for t in e["types"]}["bug"] == "Anomalie"
    assert statuts.categorie("bug", "  réouvert ") == "reouvert" and statuts.ferme("bug", "REJETÉ") is True and statuts.ferme("bug", "Ouvert") is False
    assert statuts.statut_pour("test", "redige") == "Prêt" and statuts.statut_pour("test", "automatise") == ""
    assert "Sans objet" not in statuts.mapping()["correspondances"]["bug"]                                # catégorie vide : pas de correspondance


def test_effets_sur_plans_bugs_executions_et_cycle_de_vie(pil):  # noqa: F811
    from atelier.domain import statuts
    from atelier.execution import centre
    from atelier.generation import cycle_vie
    from atelier.intelligence import patrimoine_xray

    # sans mapping : l'ancien repli (catégorie « terminé » de Jira, puis nom du statut)
    assert centre.plan_ferme({"statut": "Livré", "ferme": False}) is False and centre.plan_ferme({"statut": "Annulé"}) is True
    pat = patrimoine_xray.charger()
    pat["executions"][0]["bugs"] += [{"id": "3", "cle": "DEMO-502", "resume": "Faux positif", "statut": "Rejeté", "ferme": True, "priorite": "Highest", "assigne": ""},
                                     {"id": "4", "cle": "DEMO-503", "resume": "Revient", "statut": "Réouvert", "ferme": False, "priorite": "Low", "assigne": "Bob"}]
    patrimoine_xray.enregistrer(pat, "test")
    pil.vider_memo()
    a = {i["id"]: i for i in pil.execution()["anomalies"]["indicateurs"]}
    assert (a["total"]["valeur"], a["ouverts"]["valeur"]) == (4, 2) and a["reouverts"]["valeur"] is None   # mapping non réglé : dit
    assert "Paramètres › Statuts des tickets" in a["reouverts"]["raison"]
    statuts.enregistrer(correspondances={"bug": {"Ouvert": "ouvert", "Terminé": "ferme", "Réouvert": "reouvert", "Rejeté": "rejete"},
                                         "plan": {"Livré": "cloture", "Annulé": "en_cours"}, "execution": {"En cours": "terminee"},
                                         "test": {"Prêt pour l'auto": "a_automatiser"}})
    pil.vider_memo()
    # le mapping du projet prime sur la catégorie Jira et sur le nom du statut
    assert centre.plan_ferme({"statut": "Livré", "ferme": False}) is True and centre.plan_ferme({"statut": "Annulé"}) is False
    a = {i["id"]: i for i in pil.execution()["anomalies"]["indicateurs"]}
    assert (a["total"]["valeur"], a["ouverts"]["valeur"], a["reouverts"]["valeur"], a["rejetes"]["valeur"]) == (3, 2, 1, 1)   # le rejeté n'est plus compté
    r = {x["responsable"]: x for x in pil.execution()["responsables"]["lignes"]}
    assert r["Alice"]["executions_ouvertes"] == 0 and r["Bob"]["bugs_ouverts"] == 1                       # exécution « En cours » reliée à Terminée
    assert cycle_vie.config()["statuts"]["a_automatiser"] == "Prêt pour l'auto"                           # statut appliqué par le cycle de vie


def test_lecture_jira_et_routes(pil, monkeypatch):  # noqa: F811
    from fastapi.testclient import TestClient

    from atelier.domain import projets, statuts
    from web_app_loader import charger_app_web

    class Jira:
        enabled = True

        def get(self, chemin):
            assert chemin == "/rest/api/3/project/DEMO/statuses"
            return [{"name": "Test", "statuses": [{"name": "Brouillon"}, {"name": "Prêt"}]}, {"name": "Bogue", "statuses": [{"name": "Ouvert"}, {"name": "Corrigé"}]},
                    {"name": "Test Execution", "statuses": [{"name": "À faire"}]}]

    monkeypatch.setattr(projets, "cle_jira", lambda: "DEMO")
    lu = statuts.lire_jira(Jira())
    assert lu["test"]["statuts"] == ["Brouillon", "Prêt"] and lu["bug"]["trouve"] is False and "Bogue" in lu["types_disponibles"]
    statuts.enregistrer(types={"bug": "Bogue"})
    e = statuts.etat(statuts.lire_jira(Jira()))
    bug = next(t for t in e["types"] if t["id"] == "bug")
    assert [s["statut"] for s in bug["statuts"]] == ["Ouvert", "Corrigé", "Terminé"] and bug["type_trouve"] is True
    assert next(s for s in bug["statuts"] if s["statut"] == "Ouvert")["sources"] == ["Jira", "copies locales"]
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/").status_code == 200
    assert len(c.get("/api/statuts").json()["types"]) == 4
    assert c.post("/api/statuts", json={"correspondances": {"bug": {"Ouvert": "nimporte"}}}).status_code == 400
    r = c.post("/api/statuts", json={"correspondances": {"bug": {"Ouvert": "ouvert", "Corrigé": "resolu"}}}).json()
    assert next(t for t in r["types"] if t["id"] == "bug")["sans_correspondance"] == ["Terminé"]
    assert c.post("/api/statuts/lire-jira").status_code == 400                                             # Jira non configuré : dit
