"""Dashboard de pilotage : synthèse, conception et Discovery, exécution, TNR (évolutions → impact → tests à rejouer →
décision humaine → campagne), aide à la décision et état de préparation. Rien d'inventé : une mesure impossible est
« indisponible » avec sa raison."""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from tests.test_intelligence_couverture import ci  # noqa: F401 — carte, 3 tests Xray, 3 exigences Jira (DEMO-11 couverte)

AUJ = date.today().isoformat()
HIER = (date.today() - timedelta(days=1)).isoformat()


@pytest.fixture
def pil(ci, tmp_path):  # noqa: F811
    from atelier.intelligence import patrimoine_xray, pilotage

    pat = patrimoine_xray.charger()
    for t, crit, mod, fin in (("DEMO-101", "Highest", "Virements", HIER), ("DEMO-102", "Medium", "Virements", HIER), ("DEMO-150", "Low", "Comptes", "")):
        x = next(x for x in pat["tests"] if x["cle"] == t)
        x.update(criticite=crit, module=mod, libelles=[], preconditions=[], exigences=["DEMO-11"] if t == "DEMO-101" else [])
        if x.get("statut_xray"):
            x["statut_xray"]["fin"] = fin + "T10:00:00"
    pat["tests"].append({"cle": "DEMO-160", "resume": "Virement bloqué par la maintenance", "module": "Virements", "criticite": "Low", "libelles": ["smoke"],
                         "etapes": [{"action": "Lancer", "resultat": ""}], "statut_xray": {"statut": "BLOCKED", "fin": HIER + "T10:00:00"}, "exigences": []})
    pat["executions"] = [{"cle": "DEMO-900", "resume": "Recette sprint 22", "statut": "En cours", "assigne": "Alice", "resolu": "",
                          "runs": {"DEMO-101": {"statut": "PASSED"}, "DEMO-102": {"statut": "FAILED", "defauts": ["1", "2"]}, "DEMO-150": {"statut": "TO DO"}},
                          "bugs": [{"id": "1", "cle": "DEMO-500", "resume": "Plafond non appliqué", "statut": "Ouvert", "ferme": False, "priorite": "Highest", "assigne": "",
                                    "cree": HIER + "T09:00:00", "resolu": ""},
                                   {"id": "2", "cle": "DEMO-501", "resume": "Libellé erroné", "statut": "Terminé", "ferme": True, "priorite": "Low", "assigne": "Bob",
                                    "cree": (date.today() - timedelta(days=3)).isoformat() + "T09:00:00", "resolu": HIER + "T09:00:00"}]}]
    patrimoine_xray.enregistrer(pat, "test")
    (tmp_path / "testabilite").mkdir(exist_ok=True)
    us = lambda cle, statut, assigne, sprint, tests=(), alertes=(), cas=(): {  # noqa: E731
        "cle": cle, "espace": "DEMO", "resume": cle, "statut": statut, "assigne": assigne, "tests_lies": list(tests), "alertes": list(alertes), "cas": list(cas),
        "sprints": {sprint: {"nom": f"Sprint {sprint}", "etat": "active" if sprint == "22" else "closed"}}}
    (tmp_path / "testabilite" / "us.json").write_text(json.dumps({
        "DEMO-11": us("DEMO-11", "Couverte", "Alice", "22", ["DEMO-101"], [{"date": AUJ, "message": "US modifiée dans Jira depuis l'analyse : à revoir."}]),
        "DEMO-12": us("DEMO-12", "Cas proposés", "Alice", "22", cas=[{"id": "c1", "statut": "Proposé"}, {"id": "c2", "statut": "Proposé"}]),
        "DEMO-13": us("DEMO-13", "Détectée", "", "21")}), "utf-8")
    pilotage.vider_memo()
    return pilotage


def _par_id(l):
    return {i["id"]: i for i in l}


def test_synthese_et_definitions(pil):
    s = pil.synthese()
    i = _par_id(s["indicateurs"])
    assert (i["exigences"]["valeur"], i["couvertes"]["valeur"], i["taux_couverture"]["valeur"]) == (3, 1, 33.3)
    assert i["tests"]["valeur"] == 4 and i["bugs_ouverts"]["valeur"] == 1 and i["bugs_critiques"]["valeur"] == 1
    # 1 réussi, 1 échoué, 1 bloqué : le bloqué pèse au dénominateur sans être un échec ; le non exécuté n'est pas compté
    assert i["taux_reussite"]["valeur"] == 33.3
    assert i["automatises"]["valeur"] == 0 and i["instables"]["disponible"] in (True, False)
    assert all(x["definition"] and x["formule"] and x["source"] and x["lien"].startswith("#") for x in s["indicateurs"])
    assert all(x["disponible"] or x["raison"] for x in s["indicateurs"])
    # évolution : comparée au dernier instantané d'un jour antérieur
    assert s["compare_a"] == "" and i["exigences"]["evolution"] is None
    h = pil._dossier() / "historique.jsonl"
    h.write_text(json.dumps({"date": HIER, "valeurs": {"exigences": 2, "bugs_ouverts": 3}}) + "\n" + h.read_text("utf-8"), "utf-8")
    i = _par_id(pil.synthese()["indicateurs"])
    assert (i["exigences"]["evolution"], i["bugs_ouverts"]["evolution"], i["couvertes"]["evolution"]) == (1, -2, None)


def test_sans_donnees_rien_n_est_invente(projet):
    from atelier.intelligence import pilotage

    pilotage.vider_memo()
    i = _par_id(pilotage.synthese()["indicateurs"])
    assert i["exigences"]["valeur"] is None and "jamais importé" in i["exigences"]["raison"]
    assert i["tests"]["valeur"] is None and i["taux_reussite"]["valeur"] is None and i["bugs_critiques"]["valeur"] is None
    assert pilotage.preparation()["statut"] == "DONNÉES INSUFFISANTES"
    assert pilotage.tnr()["recommandations"] == [] and pilotage.execution()["responsables"]["lignes"] == []


def test_conception_couverte_executee_validee_distinctes(pil):
    c = pil.conception()
    i = _par_id(c["couverture"]["indicateurs"])
    assert (i["total"]["valeur"], i["reliees"]["valeur"], i["sans_test"]["valeur"], i["executees"]["valeur"], i["validees"]["valeur"]) == (3, 1, 2, 1, 1)
    assert i["manuelles"]["valeur"] == 1 and c["couverture"]["sans_test"] == ["DEMO-12", "DEMO-13"]
    d = _par_id(c["discovery"]["indicateurs"])
    assert d["ecrans"]["valeur"] == 2 and d["ecrans_non_valides"]["valeur"] == 2 and "pas la preuve" in d["exigences_sans_ecran"]["definition"]
    q = _par_id(c["qualite"]["indicateurs"])
    assert q["tests_xray"]["valeur"] == 4 and q["sans_resultat"]["valeur"] == 1 and q["sans_precondition"]["valeur"] == 4
    sp = c["sprints"]["sprints"]
    assert [(s["nom"], s["exigences"], s["couvertes"], s["non_couvertes"], s["tests_concus"], s["tests_executes"]) for s in sp] == \
        [("Sprint 21", 1, 0, 1, 0, 0), ("Sprint 22", 2, 1, 1, 1, 1)]
    assert sp[1]["ajoutees_en_cours"] is None and any("figé" in x for x in c["sprints"]["non_mesure"])   # périmètre non figé : dit, pas deviné
    # filtre sprint : seules les exigences du sprint
    i = _par_id(pil.conception({"sprint": "22"})["couverture"]["indicateurs"])
    assert (i["total"]["valeur"], i["sans_test"]["valeur"]) == (2, 1)


def test_execution_bloque_et_non_execute_jamais_en_echec(pil):
    e = pil.execution()
    a = _par_id(e["activite"]["indicateurs"])
    assert (a["executes"]["valeur"], a["reussis"]["valeur"], a["echoues"]["valeur"], a["bloques"]["valeur"], a["non_executes"]["valeur"]) == (3, 1, 1, 1, 1)
    t = _par_id(e["taux"]["indicateurs"])
    assert (t["final"]["valeur"], t["echec"]["valeur"], t["blocage"]["valeur"]) == (33.3, 33.3, 33.3)
    assert t["premier_passage"]["valeur"] is None and "aucun run" in t["premier_passage"]["raison"]
    b = _par_id(e["anomalies"]["indicateurs"])
    assert (b["total"]["valeur"], b["ouverts"]["valeur"], b["resolus"]["valeur"], b["critiques"]["valeur"], b["non_affectes"]["valeur"]) == (2, 1, 1, 1, 1)
    assert b["resolution"]["valeur"] == 2.0 and e["anomalies"]["par_module"] == [("Virements", 1)]
    assert e["anomalies"]["ouverts"][0]["tests"] == ["DEMO-102"] and any("réouverts" in x for x in e["anomalies"]["non_mesure"])
    r = {x["responsable"]: x for x in e["responsables"]["lignes"]}
    assert (r["Alice"]["us_a_couvrir"], r["Alice"]["cas_a_valider"], r["Alice"]["executions_ouvertes"]) == (1, 2, 1)
    assert (r["Sans responsable"]["us_a_couvrir"], r["Sans responsable"]["bugs_ouverts"]) == (1, 1)
    assert e["responsables"]["lignes"][-1]["responsable"] == "Sans responsable"


def test_tnr_evolutions_impact_et_decision_humaine(pil):
    t = pil.tnr()
    evo = {e["id"]: e for e in t["evolutions"]}
    assert evo["us:DEMO-11"]["nature"] == "Exigence modifiée dans Jira" and evo["us:DEMO-11"]["tests"] == ["DEMO-101"]
    assert evo["bug:DEMO-501"]["nature"] == "Bug corrigé"
    r = {x["test"]: x for x in t["recommandations"]}
    assert r["DEMO-101"]["categorie"] == "obligatoire" and r["DEMO-101"]["priorite"] == "Très élevée"
    assert r["DEMO-101"]["motifs"] == ["Exigence modifiée dans Jira : DEMO-11"]
    assert r["DEMO-160"]["categorie"] == "securite" and r["DEMO-160"]["motifs"] == ["étiquette « smoke »"]
    assert r["DEMO-101"]["rejoue"] is False                       # exécuté hier, l'exigence a changé aujourd'hui : à rejouer
    i = t["indicateurs"]
    assert r["DEMO-102"]["motifs"] == ["Bug corrigé : DEMO-501"] and r["DEMO-102"]["rejoue"] is True and r["DEMO-102"]["resultat"] == "echec"
    assert (i["obligatoires"], i["securite"], i["impactes_non_executes"], i["couverture_impacts"], i["echoues"]) == (2, 1, 1, 50.0, 1)
    with pytest.raises(ValueError, match="Justifier"):
        pil.decider_tnr("DEMO-160", "rejetée")
    with pytest.raises(ValueError, match="pas un test connu"):
        pil.decider_tnr("DEMO-999", "ajoutée")
    pil.decider_tnr("DEMO-160", "rejetée", "hors périmètre de la livraison")
    pil.decider_tnr("DEMO-101", "acceptée", priorite="Élevée")
    i = pil.decider_tnr("DEMO-150", "ajoutée", "demande du métier")
    assert (i["acceptes"], i["rejetes"], i["selectionnes"]) == (1, 1, 2)
    r = {x["test"]: x for x in pil.tnr()["recommandations"]}
    assert r["DEMO-150"]["categorie"] == "obligatoire" and "ajouté par" in r["DEMO-150"]["motifs"][0] and r["DEMO-101"]["priorite"] == "Élevée"
    assert r["DEMO-160"]["decision_motif"] == "hors périmètre de la livraison"
    with pytest.raises(ValueError, match="Aucun test automatisé"):   # rien n'est automatisé dans ce projet : dit, pas contourné
        pil.creer_campagne_tnr("TNR", ["android"])


def test_campagne_tnr_envoyee_a_execution_center(pil, monkeypatch):
    from atelier.execution import centre

    monkeypatch.setattr(pil, "_publies", lambda: ({"DEMO-101"}, set()))
    pil.decider_tnr("DEMO-150", "ajoutée", "demande du métier")
    c = pil.creer_campagne_tnr("TNR après évolution des virements", ["android"], "RECETTE")
    assert c["tests"] == 1 and c["non_automatises"] == ["DEMO-102", "DEMO-150"] and c["partielle"] is False   # DEMO-102 : test du bug corrigé DEMO-501
    camp = next(x for x in centre.campagnes() if x["id"] == c["campagne"])
    assert (camp["type"], camp["tests"], camp["environnement"]) == ("TNR", ["DEMO-101"], "RECETTE") and "analyse d'impact" in camp["description"]


def test_selection_partielle_dite(pil, monkeypatch):
    monkeypatch.setattr(pil, "_fichiers_modifies", lambda depuis: [{"fichier": "tests/inconnu.robot", "date": AUJ, "auteur": "x"}])
    t = pil.tnr()
    assert t["non_rattachees"] == ["fichier:tests/inconnu.robot"] and "partielle" in t["avertissement"]


def test_preparation_criteres_et_decision(pil):
    p = pil.preparation()
    c = _par_id(p["criteres"])
    assert p["statut"] == "NON PRÊT" and "Bugs critiques ouverts" in p["raison"] and "TNR obligatoires" in p["raison"]
    assert (c["couverture"]["valeur"], c["couverture"]["respecte"], c["bugs_critiques"]["respecte"], c["bloques"]["respecte"]) == (33.3, False, False, False)
    assert "pas autorisation" in p["avertissement"]
    # critères du projet : un bug critique toléré, TNR non bloquant → il reste des réserves, plus de blocage
    assert c["tnr_echecs"]["valeur"] == 1                         # DEMO-102, rejoué après la correction du bug DEMO-501, est encore en échec
    pil.regler_criteres([{"id": "bugs_critiques", "seuil": 1, "bloquant": True}, {"id": "tnr_obligatoires", "seuil": 0, "bloquant": False},
                         {"id": "tnr_echecs", "seuil": 0, "bloquant": False}, {"id": "critiques_non_valides", "seuil": 0, "bloquant": False}])
    assert pil.preparation()["statut"] == "PRÊT AVEC RÉSERVES"
    with pytest.raises(ValueError, match="inconnu"):
        pil.regler_criteres([{"id": "humeur", "seuil": 1}])
    d = pil.decision()
    textes = " | ".join(a["texte"] for a in d["alertes"])
    assert "1 bug(s) critique(s) ouvert(s)" in textes and "2 exigence(s) sans aucun test" in textes and "sans responsable" in textes
    assert d["alertes"][0]["priorite"] == "haute" and all(a["action"] and a["lien"].startswith("#") for a in d["alertes"])
    q = {r["question"]: r for r in d["recommandations"]}
    assert set(q["Quels tests faut-il concevoir en priorité ?"]["elements"]) == {"DEMO-12", "DEMO-13"}
    assert q["Quels tests faut-il rejouer après les dernières évolutions ?"]["confiance"].startswith("déduction")
    assert all({"constat", "elements", "preuves", "priorite", "impact", "action", "confiance"} <= set(r) for r in d["recommandations"])
    assert "Aucun texte n'est généré" in d["methode"]


def test_routes_web(pil):
    from fastapi.testclient import TestClient

    from web_app_loader import charger_app_web

    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/").status_code == 200
    ctx = c.get("/api/pilotage/contexte").json()
    assert [s["nom"] for s in ctx["sprints"]] == ["Sprint 22", "Sprint 21"] and ctx["modules"] == ["Comptes", "Virements"] and ctx["responsables"] == ["Alice", "Bob"]
    for zone in ("synthese", "conception", "execution", "tnr", "decision"):
        assert c.get(f"/api/pilotage/{zone}?module=Virements").status_code == 200, zone
    assert c.get("/api/pilotage/inconnue").status_code == 404
    assert c.post("/api/pilotage/tnr-decision", json={"test": "DEMO-160", "decision": "rejetée"}).status_code == 400
    assert c.post("/api/pilotage/tnr-decision", json={"test": "DEMO-101", "decision": "acceptée"}).json()["acceptes"] == 1
    assert _par_id(c.get("/api/pilotage/synthese?module=Comptes").json()["indicateurs"])["tests"]["valeur"] == 1


def test_le_dashboard_defile():
    """#ecran est en overflow: hidden (sélecteur d'identifiant) : sans règle plus précise, un Dashboard plus haut que la
    fenêtre est coupé et son bas inaccessible (constaté dans un navigateur le 2026-11-18)."""
    import re
    from pathlib import Path

    css = (Path(__file__).resolve().parents[1] / "atelier" / "adapters" / "web" / "static" / "plateforme.css").read_text("utf-8")
    assert re.search(r"#ecran\s*\{[^}]*overflow:\s*hidden", css)
    assert re.search(r"#ecran\.g-dash\s*\{[^}]*overflow-y:\s*auto", css)
