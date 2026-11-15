"""Coverage Intelligence & Functional Reconstruction : qualité documentaire, reconstruction depuis la carte, propositions
de Stories et de liens (validation humaine, synchronisation explicite), tests manquants et orphelins, 4 dimensions."""
import pytest

from tests.test_couverture_exigences import FauxJira, _adf, _issue


@pytest.fixture
def ci(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.domain import projet, projets
    from atelier.intelligence import couverture_exigences, patrimoine_xray

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(projets, "cle_xray", lambda: "DEMO")
    monkeypatch.setenv("IA_FOURNISSEUR", "aucun")
    carte.creer_app("Banque Mobile", ["android"])
    patrimoine_xray.enregistrer({"projet": "DEMO", "exigences": [], "tests": [
        {"cle": "DEMO-101", "resume": "Virement interne valide", "etapes": [{"action": "Saisir le montant du virement interne", "resultat": "Virement confirmé"}],
         "statut_xray": {"statut": "PASSED"}, "exigences": []},
        {"cle": "DEMO-102", "resume": "Plafond de virement dépassé refusé", "etapes": [{"action": "Saisir un montant au-delà du plafond", "resultat": "Refus plafond"}],
         "statut_xray": {"statut": "FAILED"}, "exigences": []},
        {"cle": "DEMO-150", "resume": "Export PDF du relevé de compte", "etapes": [{"action": "Exporter le relevé", "resultat": "PDF téléchargé"}], "exigences": []}]}, "test")
    exigences = [
        _issue("DEMO-11", "Virement interne entre mes comptes", "Story", parent="DEMO-10", liens=["DEMO-101"],
               description=_adf("Le client transfère entre ses comptes.\nCritères d'acceptation :\n- montant supérieur à zéro\n- confirmation affichée")),
        _issue("DEMO-12", "Plafond de virement dépassé", "Story", parent="DEMO-10"),
        _issue("DEMO-13", "Divers", "Story"),
    ]
    couverture_exigences.enregistrer_reglages('project = "DEMO" AND issuetype = Story', criteres_actifs=False)

    class Jira(FauxJira):
        def rechercher(self, jql, champs, limite=1000):
            if "issuetype = Epic" in jql:
                return [_issue("DEMO-1", "Gestion des virements", "Epic"), _issue("DEMO-2", "Gestion des bénéficiaires", "Epic")]
            return super().rechercher(jql, champs, limite)

    couverture_exigences.importer(Jira(exigences))
    # carte : un écran « Virement » observé, non documenté côté Jira par ce nom précis
    e = lambda k, t, l: {"key": k, "type": t, "libelle": l, "locators": [f"id={k}"]}  # noqa: E731
    a = carte.observer([e("champ_montant", "champ", "Montant"), e("bouton_valider", "bouton", "Valider le virement")], "android", "saisie")
    carte.renommer(a["id"], "saisie_virement", "Virements")
    b = carte.observer([e("champ_iban", "champ", "IBAN du bénéficiaire"), e("bouton_ajouter", "bouton", "Ajouter le bénéficiaire")], "android", "benef")
    carte.renommer(b["id"], "ajout_beneficiaire", "Bénéficiaires")
    carte.enregistrer_transition(b["id"], a["id"], "android", {"type": "tap", "cle": "bouton_ajouter", "libelle": "Ajouter"})
    from atelier.intelligence import intelligence_couverture

    return intelligence_couverture


def test_qualite_documentaire(ci):
    doc = ci.qualite_documentaire()
    codes = {(a["cle"], a["code"]) for a in doc}
    assert ("DEMO-12", "sans_description") in codes and ("DEMO-12", "sans_criteres") in codes
    assert ("DEMO-13", "trop_generique") in codes and ("DEMO-13", "sans_rattachement") in codes
    assert ("DEMO-2", "epic_sans_story") in codes and ("DEMO-1", "epic_sans_story") not in codes  # DEMO-1 a une Feature et ses Stories
    assert all({"criticite", "explication", "recommandation", "action"} <= set(a) for a in doc)
    assert doc[0]["criticite"] == "haute"


def test_reconstruction_et_story_proposee(ci):
    caps = {c["nom"]: c for c in ci.capacites()}
    benef = caps["ajout_beneficiaire"]
    assert not benef["documentee"] and any(o["nature"] == "champ" for o in benef["observations"])
    assert any(o["nature"] == "transition" for o in benef["observations"])
    p = ci.proposer_story(benef["id"])
    origines = {c["origine"] for c in p["contenu"]["criteres"]}
    assert {"observe", "a_confirmer"} <= origines and p["statut"] == "proposee" and p["contenu"]["projet_jira"] == "DEMO"
    assert ci.proposer_story(benef["id"])["id"] == p["id"]  # pas de doublon
    with pytest.raises(ValueError, match="motivé"):
        ci.decider(p["id"], "rejeter")
    ci.decider(p["id"], "modifier", modifications={"afin_de": "payer mes proches", "epic": "DEMO-2"})
    ci.decider(p["id"], "valider")

    class Jira:
        enabled = True
        cree = None

        def creer_ticket(self, projet, resume, description, type_ticket="", parent=""):
            Jira.cree = (projet, resume, parent, description)
            return "DEMO-200"

    s = ci.synchroniser(p["id"], Jira())
    assert s["statut"] == "synchronisee" and s["synchronisation"]["cree"] == "DEMO-200"
    assert Jira.cree[2] == "DEMO-2" and "afin de payer mes proches" in Jira.cree[3] and "[observé directement]" in Jira.cree[3]
    assert ci.synchronisations()[0]["cree"] == "DEMO-200"


def test_liens_proposes_valides_puis_synchronises(ci):
    r = ci.analyser_liens()
    liens = {(p["contenu"]["exigence"], p["contenu"]["test"]): p for p in ci.propositions("lien_test")}
    assert ("DEMO-12", "DEMO-102") in liens and ("DEMO-11", "DEMO-101") not in liens  # lien natif déjà présent : jamais reproposé
    p = liens[("DEMO-12", "DEMO-102")]
    assert p["score"] >= 35 and any("termes communs" in j for j in p["justification"]) and r["propositions"] >= 1
    with pytest.raises(ValueError, match="validée"):
        ci.synchroniser(p["id"])
    ci.decider(p["id"], "valider")

    class Jira:
        enabled = True
        liens = []

        def get(self, chemin):
            return {"fields": {"issuelinks": []}}

        def link(self, a, b, t):
            Jira.liens.append((a, b, t))

    assert ci.synchroniser(p["id"], Jira())["synchronisation"]["lie"] == "DEMO-102 → DEMO-12" and Jira.liens == [("DEMO-102", "DEMO-12", "Test")]
    autre = next(x for x in ci.propositions("lien_test") if x["statut"] == "proposee") if ci.propositions("lien_test", "proposee") else None
    if autre:
        ci.decider(autre["id"], "rejeter", "pas le même besoin")
        ci.analyser_liens()
        assert next(x for x in ci.propositions("lien_test") if x["id"] == autre["id"])["statut"] == "rejetee"  # jamais reproposé


def test_manquants_orphelins_et_vue(ci):
    m = ci.tests_manquants()
    diag = {x["exigence"]: x["diagnostic"] for x in m["exigences"]}
    assert diag["DEMO-12"] == "aucun test associé" and diag["DEMO-11"] in ("couvert", "couverture à vérifier")
    us = ci.envoyer_vers_test_design("DEMO-12")
    assert us["cas"] and us["statut"] == "Cas proposés"  # workflow Test Design, aucun test Xray créé
    o = {x["test"]: x for x in ci.orphelins()}
    assert "DEMO-101" not in o and o["DEMO-150"]["statut"] in ("orphelin", "candidat trouvé")
    with pytest.raises(ValueError, match="justification"):
        ci.classer_orphelin("DEMO-150", "conserver")
    c = ci.classer_orphelin("DEMO-150", "technique")
    assert c["type"] == "classement_orphelin" and {x["test"]: x for x in ci.orphelins()}["DEMO-150"]["classement"]["id"] == c["id"]
    v = ci.vue()
    assert v["overview"]["stories"] == 3 and v["documentaire"]["sans_criteres"] == 2
    assert v["tracabilite"]["exigences_sans_tests"] == 2 and v["execution"]["passed"] == 1
    assert set(v["automatisation"]) >= {"automatisees", "partielles", "manuelles_seulement", "sans_test"}


def test_graphe_montre_les_exigences_sans_test(ci):
    from atelier.discovery import connaissance

    g = connaissance.construire()
    assert "user_story:DEMO-12" in g.noeuds and "user_story:DEMO-13" in g.noeuds
    assert any(r.type == "teste_par" and r.de == "user_story:DEMO-11" and r.vers == "test:DEMO-101" for r in g.relations.values())
