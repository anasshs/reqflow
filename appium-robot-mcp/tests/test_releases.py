"""Release Notes : d'un texte collé au périmètre de non-régression. Les clés d'US citées sont exploitées quand elles sont
là ; sans clé, le rattachement est proposé, jamais décidé. Projet de démonstration (application fictive)."""
import shutil
from pathlib import Path

import pytest

from conftest import pointer_projet

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"
NOTE = """Release 2.4.0 - livraison du 2026-11-25

Nouveautés
- DEMO-312 : réinitialisation du mot de passe par e-mail
- Possibilité de se déconnecter depuis toutes les pages

Corrections
- DEMO-999 : correction d'un libellé sur la page d'aide
* Le blocage du compte après trois échecs ne se déclenchait plus

Technique :
1. Montée de version de la bibliothèque de chiffrement
"""


@pytest.fixture
def rel(tmp_path, monkeypatch):
    d = tmp_path / "demo"
    shutil.copytree(DEMO, d, ignore=shutil.ignore_patterns("results", "connaissance", "strategie"))
    pointer_projet(d, monkeypatch)
    from atelier.discovery import connaissance
    from atelier.intelligence import pilotage, releases

    connaissance.vider_cache()
    pilotage._MEMO.clear()
    return releases


def test_lecture_du_texte_colle(rel):
    a = rel.analyser_texte(NOTE)
    assert (a["version"], a["date"]) == ("2.4.0", "2026-11-25") and a["cles_jira"] == ["DEMO-312", "DEMO-999"]
    ev = a["evolutions"]
    assert [(e["type"], e["ligne"]) for e in ev] == [("nouvelle", 4), ("nouvelle", 5), ("correction", 8), ("correction", 9), ("technique", 12)]
    assert ev[0]["cles_jira"] == ["DEMO-312"] and ev[1]["cles_jira"] == [] and ev[0]["rubrique"] == "Nouveautés"
    assert NOTE.splitlines()[ev[3]["ligne"] - 1].lstrip("* ").startswith(ev[3]["texte"][:30])   # chaque évolution garde sa ligne d'origine
    # sans rubrique ni puce : une évolution par ligne, type lu dans la ligne, « modification » à défaut
    b = rel.analyser_texte("Correction du calcul des frais sur les virements internationaux.\nLe tableau de bord affiche désormais le solde en temps réel.")
    assert [e["type"] for e in b["evolutions"]] == ["correction", "modification"]


def test_rattachement_cle_citee_propositions_et_decisions(rel):
    r = rel.creer(NOTE)
    assert r["statut"] == "Analysée" and r["version"] == "2.4.0" and r["nom"] == "Release 2.4.0" and r["texte"].startswith("Release 2.4.0")
    e = {x["id"]: x for x in r["evolutions"]}
    # clé Jira citée et connue du graphe : rattachement certain, fait d'office, avec ses tests
    l = [x for x in e["E1"]["liens"] if x["etat"] == "confirmé"]
    assert [x["noeud"] for x in l] == ["user_story:DEMO-312"] and "clé Jira citée" in l[0]["origine"]
    assert e["E1"]["etat"] == "rattachée" and "DEMO-308" in e["E1"]["tests"]
    # clé citée mais inconnue : signalée, jamais inventée
    assert e["E3"]["cles_inconnues"] == ["DEMO-999"] and not [x for x in e["E3"]["liens"] if x["etat"] == "confirmé"]
    # sans clé : des éléments sont proposés, aucun n'est confirmé
    assert e["E4"]["etat"] == "à trancher" and all(x["etat"] == "proposé" and x["origine"] == "mots communs" for x in e["E4"]["liens"])
    assert "user_story:DEMO-311" in [x["noeud"] for x in e["E4"]["liens"]]                     # « Bloquer le compte après trois échecs »
    assert e["E5"]["etat"] == "non rattachée"
    assert e["E3"]["etat"] == "non rattachée"                                                   # le préfixe de la clé (« DEMO ») ne rapproche rien
    assert (r["rattachees"], r["a_trancher"], r["non_rattachees"]) == (1, 2, 2)

    # le QA tranche : confirmer une proposition, en rejeter une, relier à la main, corriger une évolution
    r = rel.operer(r["id"], "confirmer", evolution="E4", noeud="user_story:DEMO-311")
    e4 = next(x for x in r["evolutions"] if x["id"] == "E4")
    assert e4["etat"] == "rattachée" and set(e4["tests"]) >= {"DEMO-304", "DEMO-306"}
    autre = next(x["noeud"] for x in e["E1"]["liens"] if x["etat"] == "proposé")                 # une proposition par les mots, à côté de la clé citée
    r = rel.operer(r["id"], "rejeter", evolution="E1", noeud=autre)
    assert next(x for x in next(y for y in r["evolutions"] if y["id"] == "E1")["liens"] if x["noeud"] == autre)["etat"] == "rejeté"
    with pytest.raises(KeyError, match="inconnu du Knowledge Graph"):
        rel.operer(r["id"], "relier", evolution="E5", noeud="module:Inexistant")
    trouve = rel.chercher_noeuds("deconnecter")
    assert "user_story:DEMO-313" in [x["noeud"] for x in trouve]
    r = rel.operer(r["id"], "relier", evolution="E2", noeud="user_story:DEMO-313")
    assert next(x for x in r["evolutions"] if x["id"] == "E2")["etat"] == "rattachée"
    r = rel.operer(r["id"], "modifier_evolution", evolution="E5", type="technique", texte="Montée de version du chiffrement (DEMO-310)")
    e5 = next(x for x in r["evolutions"] if x["id"] == "E5")
    assert e5["cles_jira"] == ["DEMO-310"] and e5["etat"] == "rattachée" and e5["corrigee"]      # la clé ajoutée par le QA rattache l'évolution
    r = rel.operer(r["id"], "ajouter_evolution", texte="Nouveau message d'accueil personnalisé")
    assert r["evolutions"][-1]["origine"] == "ajoutée par le QA" and r["evolutions"][-1]["type"] == "nouvelle"
    r = rel.operer(r["id"], "supprimer_evolution", evolution=r["evolutions"][-1]["id"])
    assert len(r["evolutions"]) == 5 and len(r["historique"]) >= 7 and all(h["par"] for h in r["historique"])

    with pytest.raises(FileExistsError, match="déjà enregistrée"):
        rel.creer(NOTE + "\n\n")                                                                 # même texte, aux espaces près : doublon
    with pytest.raises(ValueError):
        rel.creer("trop court")


def test_une_release_en_cours_alimente_le_tnr(rel):
    """Une release ouverte compte d'office dans le TNR du Dashboard ; qualifiée, elle n'y est plus lue."""
    from atelier.intelligence import builds, pilotage

    r = rel.creer(NOTE)
    rel.operer(r["id"], "confirmer", evolution="E4", noeud="user_story:DEMO-311")
    evo = [e for e in pilotage.evolutions({}) if e["id"].startswith("release:")]
    assert {e["noeud"] for e in evo} >= {"user_story:DEMO-312", "user_story:DEMO-311", ""}       # rattachées, et « hors graphe »
    assert all(e["source"] == "Release Note · Release 2.4.0" for e in evo)
    t = pilotage.tnr({})
    reco = {x["test"]: x for x in t["recommandations"]}
    assert reco["DEMO-308"]["categorie"] == "obligatoire" and any("Release Note" in m for m in reco["DEMO-308"]["motifs"])
    assert {"DEMO-304", "DEMO-306"} <= set(reco)
    assert t["avertissement"]                                                                    # des évolutions hors graphe : sélection partielle, dite
    # qualifiée : la livraison est close, le TNR ne la lit plus
    builds.qualifier(r["id"], motif="mise en production décidée par le comité de release")
    pilotage.vider_memo()
    assert rel.evolutions_tnr() == [] and not [e for e in pilotage.evolutions({}) if e["id"].startswith("release:")]
    assert rel.operer(r["id"], "supprimer_release") == {"supprimee": r["id"]} and rel.lister() == []


def test_routes(rel, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from web_app_loader import charger_app_web, module_web

    monkeypatch.setattr(module_web(), "CONFIG_PATH", tmp_path / "atelier.json")
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/plateforme").status_code == 200
    assert c.get("/api/releases").json() == []
    assert c.post("/api/releases", json={"texte": "court"}).status_code == 400
    r = c.post("/api/releases", json={"texte": NOTE, "nom": "Livraison de novembre"}).json()
    assert r["nom"] == "Livraison de novembre" and len(r["evolutions"]) == 5
    assert c.get("/api/releases").json()[0]["evolutions"] == 5
    assert c.get("/api/releases/" + r["id"]).json()["tests"]
    assert "user_story:DEMO-313" in [x["noeud"] for x in c.get("/api/releases/noeuds", params={"q": "deconnecter"}).json()]
    assert c.post(f"/api/releases/{r['id']}/operation", json={"op": "valider"}).json()["statut"] == "Validée"
    assert c.post(f"/api/releases/{r['id']}/operation", json={"op": "inconnue", "evolution": "E1"}).status_code == 400
    assert c.get("/api/releases/REL-00000000-aaaaaa").status_code == 400
