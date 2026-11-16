"""V2, phase 4 : Test Design avancé — cas par catégorie (source, confiance, manques, observé / déduit) et détection
des doublons face aux tests Xray existants (titre, étapes, préconditions, résultats attendus)."""
import pytest

from atelier.domain.graphe import Graphe


@pytest.fixture
def us(tmp_path, monkeypatch):
    from atelier.domain import projet
    from atelier.intelligence import patrimoine_xray, testabilite_us

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path.resolve())
    testabilite_us.importer_exigence({"cle": "VIR-1", "resume": "Faire un virement", "criteres": [
        "Étant donné un compte approvisionné, quand je valide un virement de 50 €, alors le virement est enregistré",
        "Si le montant dépasse 10 000 € alors le virement est refusé",
        "Le virement est réservé au rôle titulaire"]})
    monkeypatch.setattr(patrimoine_xray, "charger_vue", lambda: {"tests": [
        {"cle": "VIR-100", "resume": "Faire un virement — refus au-delà du plafond de 10 000 €", "etapes": [
            {"action": "Saisir un montant de 10 001 € et valider", "donnees": "", "resultat": "le virement est refusé"}]},
        {"cle": "VIR-200", "resume": "Consulter le solde", "etapes": [{"action": "Ouvrir le compte", "resultat": "le solde s'affiche"}]}]})
    g = Graphe("essai")
    g.noeud("fonctionnalite:virement", "fonctionnalite", "Virement")
    g.noeud("user_story:VIR-1", "user_story", "VIR-1")
    g.noeud("regle:plafond", "regle", "Plafond journalier de 10 000 €")
    g.noeud("role:titulaire", "role", "titulaire")
    for e in ("saisie", "confirmation"):
        g.noeud(f"ecran:{e}", "ecran", e)
        g.relier("fonctionnalite:virement", f"ecran:{e}", "contient")
    for cle, cls in (("champ_montant", "controlled"), ("message_erreur", "safe"), ("bouton_valider", "sensitive")):
        g.noeud(f"locator:saisie.{cle}@web", "locator", cle, proprietes={"classe_action": cls})
        g.relier("ecran:saisie", f"locator:saisie.{cle}@web", "contient")
    g.relier("ecran:saisie", "ecran:confirmation", "navigue_vers")
    g.relier("fonctionnalite:virement", "user_story:VIR-1", "contient")
    g.relier("fonctionnalite:virement", "role:titulaire", "contient")
    g.relier("user_story:VIR-1", "regle:plafond", "contient")
    return g


def test_contexte_depuis_le_graphe(us):
    from atelier.intelligence import conception_avancee as ca

    c = ca.contexte("VIR-1", us)
    assert [r["libelle"] for r in c["regles"]] == ["Plafond journalier de 10 000 €"] and c["ecrans"] == ["confirmation", "saisie"]
    assert [x["cle"] for x in c["champs"]] == ["champ_montant"] and [x["cle"] for x in c["messages"]] == ["message_erreur"]
    assert c["transitions"] == [{"de": "saisie", "vers": "confirmation"}] and c["roles"] == ["titulaire"]


def test_cas_par_categorie_avec_source_et_confiance(us):
    from atelier.intelligence import conception_avancee as ca

    r = ca.proposer("VIR-1", g=us)
    cas = [c for c in r["us"]["cas"] if c.get("categorie")]
    cats = {c["categorie"] for c in cas}
    assert cats == set(ca.CATEGORIES) - {"alternatif"} | ({"alternatif"} & cats)  # toutes les catégories sauf, éventuellement, alternatif
    assert {"nominal", "negatif", "limites", "champs", "erreurs", "navigation", "permissions", "regles"} <= cats
    nominal = next(c for c in cas if c["categorie"] == "nominal")
    assert nominal["provenance"] == "observé" and nominal["source_detail"] == "critère d'acceptation 1" and nominal["confiance"] >= 0.6
    champ = next(c for c in cas if c["categorie"] == "champs")
    assert champ["provenance"] == "déduit" and "format attendu" in champ["manquant"] and "champ_montant" in champ["titre"]
    limites = [c for c in cas if c["categorie"] == "limites"]
    assert any("10 000" in c["titre"] for c in limites) and any("50" in c["titre"] for c in limites)
    assert next(c for c in cas if c["categorie"] == "permissions")["titre"].endswith("accès titulaire")
    assert all(c["statut"] == "Proposé" for c in cas) and r["us"]["statut"] == "Cas proposés"
    assert ca.proposer("VIR-1", g=us)["ajoutes"] == 0  # pas de doublon de proposition


def test_doublons_et_recommandations(us):
    from atelier.intelligence import conception_avancee as ca

    d = ca.doublons("Faire un virement refusé au-delà du plafond de 10 000 €",
                    [{"action": "Saisir un montant de 10 001 € et valider", "resultat": "le virement est refusé"}])
    assert d["meilleur"]["cle"] == "VIR-100" and d["recommandation"] == "réutiliser" and set(d["meilleur"]["facettes"]) == {"titre", "etapes", "resultats", "texte complet"}
    assert ca.doublons("Changer le mot de passe", [{"action": "Ouvrir le profil", "resultat": "formulaire affiché"}])["recommandation"] == "créer"
    r = ca.proposer("VIR-1", ["negatif"], g=us)
    neg = next(c for c in r["us"]["cas"] if c.get("categorie") == "negatif")
    assert neg["doublon"]["meilleur"]["cle"] == "VIR-100" and neg["doublon"]["recommandation"] in ("réutiliser", "faire évoluer")
    v = ca.verifier_doublons("VIR-1")
    assert v["verifies"] >= 1 and all("doublon" in c for c in v["us"]["cas"])


def test_outils_mcp(us, monkeypatch):
    from atelier.adapters import facade
    from atelier.discovery import connaissance

    monkeypatch.setattr(connaissance, "construire", lambda *a, **k: us)
    r = facade.test_design_proposer("VIR-1", ["regles", "navigation"])
    assert r["ajoutes"] == 2 and {c["categorie"] for c in r["cas"]} == {"regles", "navigation"}
    assert facade.test_design_doublons("Consulter le solde", [{"action": "Ouvrir le compte", "resultat": "le solde s'affiche"}])["meilleur"]["cle"] == "VIR-200"
