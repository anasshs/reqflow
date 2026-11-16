"""V2, phase 5 : entités Champ (composant de genre champ) et Anomalie (bug enrichi par Failure Analysis) dans le
Knowledge Graph, avec leurs relations ; enrichissement uniquement par propositions à valider."""
import pytest

from atelier.domain.graphe import Graphe


def _graphe():
    from atelier.discovery import connaissance

    g = Graphe("essai")
    g.noeud("fonctionnalite:virement", "fonctionnalite", "Virement")
    g.noeud("ecran:saisie", "ecran", "saisie")
    g.relier("fonctionnalite:virement", "ecran:saisie", "contient")
    for cle in ("champ_montant", "message_erreur"):
        g.noeud(f"locator:saisie.{cle}@web", "locator", cle, proprietes={"plateforme": "web"})
        g.relier("ecran:saisie", f"locator:saisie.{cle}@web", "contient")
    g.noeud("composant:saisie.champ_montant", "composant", "Montant", plateformes=["web"],
            proprietes={"genre": "champ", "nom_technique": "champ_montant", "libelle": "Montant", "type": "champ", "ecran": "saisie",
                        "format": None, "obligatoire": None, "valeur_defaut": None, "regles_validation": [], "messages_erreur": []})
    g.relier("ecran:saisie", "composant:saisie.champ_montant", "contient")
    g.relier("composant:saisie.champ_montant", "locator:saisie.champ_montant@web", "utilise")
    g.noeud("regle:plafond", "regle", "Le montant est obligatoire, format 2 décimales, 0 par défaut")
    g.noeud("regle:autre", "regle", "Le solde s'affiche en temps réel")
    g.noeud("keyword:saisir", "keyword", "Saisir Le Montant")
    g.relier("keyword:saisir", "locator:saisie.champ_montant@web", "utilise")
    g.noeud("test_robot:t1", "test_robot", "Virement nominal", proprietes={"cles_xray": ["VIR-1"]})
    g.relier("test_robot:t1", "keyword:saisir", "appelle")
    g.noeud("test:VIR-1", "test", "VIR-1")
    return g, connaissance


def test_champ_enrichi_depuis_regles_messages_et_tests():
    from atelier.discovery import entites

    g, connaissance = _graphe()
    connaissance._enrichir_champs(g)
    c = entites.champs(g=g)[0]
    assert c["obligatoire"] is True and c["format"].startswith("format 2 décimales") and c["valeur_defaut"].startswith("par défaut")
    assert c["regles_validation"] == [{"id": "regle:plafond", "libelle": "Le montant est obligatoire, format 2 décimales, 0 par défaut",
                                       "lien": "déduit", "statut": "à valider"}]  # lien déduit du texte : à valider
    assert c["messages_erreur"] == ["message_erreur"] and c["fonctionnalite"] == "Virement" and c["tests"] == ["Virement nominal"]
    assert any(r.de == "fonctionnalite:virement" and r.vers == c["id"] and r.type == "contient" for r in g.relations.values())


def test_anomalie_depuis_failure_analysis(monkeypatch):
    from atelier.discovery import entites
    from atelier.execution import echecs

    g, connaissance = _graphe()
    connaissance._enrichir_champs(g)
    ctx = {"nom": "Virement nominal", "cle_xray": "VIR-1", "run": "RUN-1", "date": "2026-11-16T10:00:00", "message": "Montant refusé",
           "ecran": "saisie", "composant": "champ_montant", "locator": "id=montant"}
    monkeypatch.setattr(echecs, "_stock", lambda: {
        "RUN-1::s1-t1": {"statut": "Confirmed", "categorie": "Application Defect", "jira": "VIR-99", "anomalie": ctx,
                         "historique": [{"date": "2026-11-16T10:05", "op": "jira", "auteur": "qa"}]},
        "RUN-2::s1-t1": {"statut": "Confirmed", "categorie": "Application Defect", "anomalie": {**ctx, "run": "RUN-2"}},
        "RUN-3::s1-t1": {"statut": "Confirmed", "categorie": "Locator Issue"}})  # pas une anomalie
    connaissance._depuis_anomalies(g)
    a = {x["id"]: x for x in entites.anomalies(g)}
    assert set(a) == {"bug:VIR-99"} | {k for k in a if k.startswith("bug:FA-")} and len(a) == 2
    j = a["bug:VIR-99"]
    assert j["id_jira"] == "VIR-99" and j["ecrans"] == ["saisie"] and j["composants"] == ["Montant"] and j["fonctionnalites"] == ["Virement"]
    assert j["tests"] == ["VIR-1", "Virement nominal"] and j["execution"] == "RUN-1" and j["statut_validation"] == "validé" and j["confiance"] == 1.0
    interne = next(v for k, v in a.items() if k.startswith("bug:FA-"))
    assert interne["id_jira"] == "" and interne["confiance"] == 0.8
    assert sorted(entites.champs(g=g)[0]["anomalies"]) == sorted(a)  # le champ voit les deux anomalies qui le concernent
    assert "resultat:RUN-1" in g.noeuds and any(r.type == "associe_a" for r in g.relations.values())
    connaissance._depuis_anomalies(g)  # identifiants stables, pas de doublon
    assert len(entites.anomalies(g)) == 2


def test_contexte_enregistre_a_la_decision(tmp_path, monkeypatch):
    from atelier.domain import projet
    from atelier.execution import echecs

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path.resolve())
    monkeypatch.setattr(echecs, "_evenement", lambda eid: {"id": eid})
    monkeypatch.setattr(echecs, "contexte_anomalie", lambda eid: {"nom": "T", "run": "RUN-1"})
    s = echecs.decider("RUN-1::t", "confirmer", "Application Defect")
    assert s["anomalie"] == {"nom": "T", "run": "RUN-1"}
    assert "anomalie" not in echecs.decider("RUN-2::t", "confirmer", "Locator Issue")
    assert echecs.associer_jira("RUN-3::t", "VIR-7")["anomalie"]["run"] == "RUN-1"


def test_proposer_une_regle_de_champ(tmp_path, monkeypatch):
    from atelier.adapters import facade
    from atelier.discovery import connaissance, entites
    from atelier.domain import declarations, projet

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path.resolve())
    g, _ = _graphe()
    monkeypatch.setattr(connaissance, "construire", lambda *a, **k: g)
    with pytest.raises(KeyError, match="Champ inconnu"):
        entites.proposer_regle_champ("saisie", "champ_inexistant", "obligatoire")
    r = facade.knowledge_proposer_champ("saisie", "champ_montant", "Montant au format 2 décimales maximum")
    d = declarations.charger()
    assert r["statut"] == "à valider" and d["noeuds"][r["regle"]]["statut"] == "à valider"
    assert any(x["de"] == "composant:saisie.champ_montant" and x["type"] == "possede" and x["statut"] == "à valider" for x in d["relations"].values())
    assert facade.knowledge_entites("champ")[0]["nom_technique"] == "champ_montant"
    with pytest.raises(ValueError):
        facade.knowledge_entites("autre")
