"""Failure Analysis, Quality Governance, Application Intelligence : sur de vrais runs de la démo."""
import shutil
from pathlib import Path

import pytest

from tests.conftest import pointer_projet

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"
CHROMIUM = "/opt/pw-browsers/chromium"


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    """Projet de démo avec deux runs réels (DEMO-304 échoue à chaque fois)."""
    d = tmp_path_factory.mktemp("qg") / "demo"
    shutil.copytree(DEMO, d, ignore=shutil.ignore_patterns("results", "connaissance", "analyses", "gouvernance"))
    return d


@pytest.fixture
def demo(runs, monkeypatch):
    pointer_projet(runs, monkeypatch)
    monkeypatch.setenv("WEB_BROWSER_EXECUTABLE", CHROMIUM)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # l'IA ne doit jamais être simulée
    from atelier.execution import historique
    from atelier.execution.robot import run_robot

    if not historique.lister():
        if not Path(CHROMIUM).exists():
            pytest.skip("Chromium absent")
        for rid in ("RUN-20261114-090000", "RUN-20261114-090100"):
            params = {"target": "tests", "variables": {"PLATFORM": "web"}, "output_dir": f"results/runs/{rid}", "xray_mode": "aucun", "jdd_env": "recette"}
            historique.enregistrer(rid, params, run_robot(**params), "2026-11-14T09:00:00", "2026-11-14T09:00:12")
    return runs


def test_classification_par_regles():
    from atelier.execution import echecs

    h = echecs.hypotheses("Element with locator 'id=valider' not found.")
    assert h[0]["categorie"] == "Locator Issue" and h[0]["force"] == "élevée"
    assert echecs.hypotheses("No keyword with name 'Clique Sur' found.")[0]["categorie"] == "Automation Defect"
    assert echecs.hypotheses("Connection refused")[0]["categorie"] == "Network Issue"
    assert echecs.hypotheses("message inédit")[0]["categorie"] == "Unknown"
    assert echecs.signature("Attendu 3 trouvé 4") == echecs.signature("Attendu 7 trouvé 9")


def test_collecte_investigation_et_cloture(demo):
    from atelier.execution import echecs

    ev = echecs.collecter()
    assert [e["cle_xray"] for e in ev] == ["DEMO-304", "DEMO-304"] and ev[0]["recurrent"] and not ev[1]["recurrent"]
    assert ev[0]["groupe"] == ev[1]["groupe"]
    i = echecs.investigation(ev[0]["id"])
    assert i["hypotheses"][0]["categorie"] == "Application Defect" and i["etape_fautive"]["locator"] == "id=message_erreur"
    assert {t["cle_xray"] for t in i["impactes"]} >= {"DEMO-302", "DEMO-303"}  # même locator message_erreur
    assert i["brouillon_jira"]["expected"].startswith("« Votre compte est bloqué")
    with pytest.raises(ValueError):
        echecs.decider(ev[0]["id"], "confirmer")  # catégorie obligatoire
    echecs.decider(ev[0]["id"], "confirmer", "Application Defect")
    with pytest.raises(ValueError, match="retest"):
        echecs.decider(ev[0]["id"], "clore")
    with pytest.raises(ValueError):
        echecs.associer_jira(ev[0]["id"], "pas une clé")
    assert echecs.collecter()[0]["categorie_confirmee"] == "Application Defect"
    assert echecs.demander_ia(ev[0]["id"])["disponible"] is False  # sans clé : jamais simulé


def test_gouvernance(demo):
    from atelier.intelligence import gouvernance as g

    k = {x["id"]: x for x in g.kpis()}
    assert k["automation_coverage"]["valeur"] == 77.8 and k["automation_roi"]["valeur"] is None
    assert all(x["definition"] and x["formule"] and x["source"] for x in k.values())
    st = g.stabilite()
    assert next(t for t in st["tests"] if t["cle_xray"] == "DEMO-304")["classification"] == "Constamment en échec" and st["flaky"] == []
    r = g.risques()["modules"][0]
    assert r["module"] == "Connexion" and r["niveau"] in ("LOW", "MEDIUM", "HIGH")
    ev = g.evaluer_release("1.0.0")
    assert ev["etat"] in ("Ready with Risks", "Not Ready") and "décision" in ev["avertissement"]
    with pytest.raises(ValueError):
        g.valider_release(ev["id"], "approuvée")
    g.valider_release(ev["id"], "refusée", "DEMO-304 bloquant")
    reco = g.recommandations()
    assert any(x["id"] == "echec:Blocage du compte après trois échecs" for x in reco)
    with pytest.raises(ValueError):
        g.suivre_recommandation(reco[0]["id"], "Rejected")
    g.suivre_recommandation(reco[0]["id"], "Accepted", "Automaticien")
    assert g.recommandations()[0]["responsable"] in ("Automaticien", "")
    assert g.instantane(force=True)["kpis"]["automation_coverage"] == 77.8
    p = g.enregistrer_parametres({"minutes_manuelles_par_test": 5})
    assert p["minutes_manuelles_par_test"] == 5 and next(x for x in g.kpis() if x["id"] == "automation_roi")["valeur"] > 0


def test_application_intelligence(demo):
    from atelier.discovery import intelligence_app as a

    v = a.vue_ensemble()
    assert v["application"]["nom"] == "Banque Démo Web" and v["technique"]["ecrans"] == 2 and v["fonctionnel"]["stories"] == 4
    e = {x["nom"]: x for x in a.ecrans()}
    assert "Connexion avec un compte valide" in e["accueil"]["tests"] and e["connexion"]["elements"]
    j = {x["cle"]: x for x in a.jira()}
    assert j["DEMO-300"]["enfants"] and [t["cle"] for t in j["DEMO-312"]["tests"]] == ["DEMO-308"]


def test_masquage_avant_ia():
    from atelier.execution import echecs

    m = echecs.masquer_texte("Text 'jean.dupont@exemple.fr' IBAN FR76 3000 6000 0112 3456 7890 189 carte 4970 1012 3456 7890 "
                             "password: Azerty123 client 12345678 valeur Martin", ["Martin"])
    for fuite in ("jean.dupont", "FR76", "4970", "Azerty123", "12345678", "Martin"):
        assert fuite not in m, (fuite, m)
    assert "‹jdd›" in m and "‹email›" in m
