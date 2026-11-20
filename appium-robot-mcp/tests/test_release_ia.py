"""Interprétation d'une release et d'un build par Cursor (par défaut) : lecture pour l'IA (texte, Knowledge Graph,
patrimoine de tests, anomalies, périmètre des règles), dépôt contrôlé par le serveur, application comme proposition par
défaut, décisions du QA prioritaires. Cursor est simulé : l'atelier n'appelle aucune IA. Données fictives."""
from datetime import date

import pytest

from tests.test_builds import b  # noqa: F401 — copie Xray de démonstration complétée
from tests.test_releases import rel  # noqa: F401 — projet de démonstration isolé

AUJ = date.today().isoformat()
NOTE = "Release 3.0.0\n\nNouveautés\n- DEMO-312 : réinitialisation du mot de passe par e-mail\n"
# un paragraphe sans clé Jira : les règles n'y voient qu'une évolution non rattachée
BUILD = "Cette livraison simplifie la sortie de l'application : un bouton permet de quitter sa session depuis chaque page.\n"


def test_lecture_pour_cursor(rel, b):  # noqa: F811
    from atelier.intelligence import release_ia

    r = rel.creer(NOTE, nom="Release 3.0")
    v = b.recevoir(r["id"], "b1", AUJ, "", BUILD)
    lu = release_ia.a_interpreter(r["id"], v["id"])
    assert lu["cible"] == "build" and lu["build"]["numero"] == "b1" and "quitter sa session" in lu["texte"]
    assert any(e["id"] == "user_story:DEMO-313" for e in lu["elements"])                   # connaissance de l'application
    assert any(t["test"] == "DEMO-304" and "module" in t for t in lu["tests"])             # patrimoine de tests
    assert lu["anomalies"][0]["cle"] == "DEMO-777" and lu["perimetre_des_regles"] and lu["consigne"]
    assert release_ia.a_interpreter(r["id"])["cible"] == "release_note"


def test_depot_controle_et_applique_par_defaut(rel, b):  # noqa: F811
    from atelier.intelligence import release_ia

    r = rel.creer(NOTE, nom="Release 3.0")
    v = b.recevoir(r["id"], "b1", AUJ, "", BUILD)
    assert v["evolutions"][0]["etat"] != "rattachée"                                         # les règles n'ont rien rattaché
    d = release_ia.deposer(r["id"], v["id"], evolutions=[
        {"evolution": "E1", "type": "modification", "elements": ["user_story:DEMO-313", "ecran:inexistant"], "justification": "quitter sa session = déconnexion"},
        {"evolution": "E9", "elements": ["user_story:DEMO-312"], "justification": "?"},
        {"evolution": "E1", "elements": ["user_story:DEMO-312"], "justification": ""},
    ], tests=[
        {"test": "DEMO-307", "action": "ajouter", "categorie": "ciblee", "justification": "déconnexion depuis le menu"},
        {"test": "DEMO-302", "action": "ecarter", "justification": "réinitialisation non touchée"},
        {"test": "DEMO-999", "action": "ajouter", "justification": "inventé"},
        {"test": "DEMO-301", "action": "supprimer", "justification": "?"},
    ], synthese="Risque limité à la déconnexion.")
    raisons = {x["raison"] for x in d["refus"]}
    assert {"élément inconnu du Knowledge Graph", "justification obligatoire", "test inconnu du patrimoine Xray"} <= raisons
    assert any(x["raison"].startswith("évolution inconnue") for x in d["refus"]) and any(x["raison"].startswith("action") for x in d["refus"])
    assert d["retenus"]["evolutions"] == [{"evolution": "E1", "element": "user_story:DEMO-313"}]

    v = b.vue(r["id"], v["id"])
    e1 = v["evolutions"][0]
    assert e1["etat"] == "rattachée" and e1["interpretation_ia"]["source"] == "Cursor (MCP)"     # utilisé par l'analyse d'impact
    assert [x["noeud"] for x in v["comparaison"]["fonctionnalites_nouvelles"]] == ["user_story:DEMO-313"]
    p = {x["test"]: x for x in v["perimetre"]}
    assert any(m.startswith("Cursor : déconnexion depuis le menu") for m in p["DEMO-307"]["motifs"])
    assert p["DEMO-302"]["decision"] == "rejetée" and p["DEMO-302"]["decision_ia"]                # écarté par défaut
    assert v["interpretation"]["synthese"] == "Risque limité à la déconnexion."

    # le QA garde la main : il garde un test écarté par Cursor, rejette un rattachement, Cursor ne l'écrase pas
    v = b.operer(r["id"], v["id"], "decider", test="DEMO-302", decision="acceptée")
    assert {x["test"]: x for x in v["perimetre"]}["DEMO-302"]["decision"] == "acceptée"
    rel.operer(r["id"], "rejeter", build=v["id"], evolution="E1", noeud="user_story:DEMO-313")
    d = release_ia.deposer(r["id"], v["id"], evolutions=[{"evolution": "E1", "elements": ["user_story:DEMO-313"], "justification": "encore"}])
    assert d["refus"] == [{"objet": "E1 → user_story:DEMO-313", "raison": "rattachement rejeté par le QA"}]

    b.operer(r["id"], v["id"], "valider")
    with pytest.raises(ValueError, match="déjà validé"):
        release_ia.deposer(r["id"], v["id"], tests=[{"test": "DEMO-307", "action": "ecarter", "justification": "x"}])


def test_interpretation_de_la_release_note_et_mode(rel, b, monkeypatch):  # noqa: F811
    from atelier.intelligence import fournisseur_ia, release_ia

    r = rel.creer("Release 3.0.0\n\nLe client peut se déconnecter de partout et réinitialiser son mot de passe.\n", nom="Release 3.0")
    rel.operer(r["id"], "valider")
    d = release_ia.deposer(r["id"], evolutions=[
        {"evolution": "E1", "texte": "", "elements": ["user_story:DEMO-312"], "justification": "réinitialisation du mot de passe"},
        {"texte": "Déconnexion depuis toutes les pages", "type": "nouvelle", "elements": ["user_story:DEMO-313"], "justification": "se déconnecter de partout"}])
    assert len(d["retenus"]["evolutions"]) == 2 and not d["refus"]
    o = rel.obtenir(r["id"])
    assert o["statut"] == "Analysée" and len(o["evolutions"]) == 2 and o["evolutions"][1]["origine"].startswith("interprétée par")
    assert all(e["etat"] == "rattachée" for e in o["evolutions"])

    monkeypatch.setattr(fournisseur_ia, "fournisseur", lambda: "cursor")
    assert release_ia.etat_ia()["mode"] == "cursor"
    assert release_ia.interpreter_ia(r["id"])["disponible"] is False                       # avec Cursor, l'atelier n'appelle rien
