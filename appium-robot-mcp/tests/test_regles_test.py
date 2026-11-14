"""Test Design › Règles de test : fiche, paramètres, liens, cas limites, non couvertes, création Xray."""
import pytest


@pytest.fixture
def rg(tmp_path, monkeypatch):
    from atelier.domain import projet
    from atelier.generation import regles_test

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    return regles_test


VIREMENT = {"nom": "Montant maximum d'un virement", "categorie": "Validation", "logique": "Le montant doit rester dans les bornes autorisées.",
            "conditions": ["compte actif", "bénéficiaire valide"], "resultats": ["virement accepté"],
            "parametres": [{"nom": "Montant", "type": "nombre", "min": "1", "max": "50000", "unite": "MAD"},
                           {"nom": "Devise", "type": "liste", "valeurs": "MAD"},
                           {"nom": "Compte actif", "type": "obligatoire"}, {"nom": "Bénéficiaire valide", "type": "obligatoire"}],
            "exigences": ["TAM-10"]}


def test_regle_cas_limites_et_couverture(rg):
    r = rg.enregistrer(VIREMENT)
    assert r["id"] == "regle:montant_maximum_d_un_virement" and r["statut"] == "validé" and r["exigences"] == ["TAM-10"]
    cas = {c["id"]: c for c in r["cas_limites"]}
    assert cas["Montant|0"]["attendu"] == "refusé" and cas["Montant|1"]["attendu"] == "accepté"
    assert cas["Montant|50000"]["attendu"] == "accepté" and cas["Montant|50001"]["attendu"] == "refusé"
    assert cas["Montant|25000"]["donnees"]["Devise"] == "MAD"  # autres paramètres nominaux
    assert cas["Devise|VALEUR_HORS_LISTE"]["attendu"] == "refusé" and cas["Compte actif|non"]["attendu"] == "refusé"
    assert rg.indicateurs()["non_couvertes"] == [r["id"]]
    with pytest.raises(ValueError, match="min supérieur"):
        rg.enregistrer({"nom": "X", "parametres": [{"nom": "a", "type": "nombre", "min": "5", "max": "1"}]})
    # décimales : pas de 0,01
    d = rg.enregistrer({"nom": "Taux", "parametres": [{"nom": "Taux", "type": "nombre", "min": "0.5", "max": "2.75"}]})
    assert {c["donnees"]["Taux"] for c in d["cas_limites"]} >= {"0.49", "2.76"}


def test_creation_xray_et_liens(rg):
    r = rg.enregistrer(VIREMENT)

    class X:
        crees = []

        def creer_test_manuel(self, projet, titre, etapes):
            X.crees.append((projet, titre, etapes))
            return {"cle": f"{projet}-{900 + len(X.crees)}"}

    class J:
        liens = []

        def link(self, a, b, t):
            J.liens.append((a, b, t))

    res = rg.creer_cas_xray(r["id"], ["Montant|50001", "Compte actif|non"], projet="TAM", xray=X(), jira=J())
    assert res["crees"] == ["TAM-901", "TAM-902"] and res["erreurs"] == []
    assert "Montant = 50001" in X.crees[0][2][0]["action"] and X.crees[0][2][1]["resultat"].startswith("refus explicite")
    assert J.liens == [("TAM-901", "TAM-10", "Test"), ("TAM-902", "TAM-10", "Test")]
    assert rg.detail(r["id"])["tests"] == ["TAM-901", "TAM-902"] and rg.indicateurs()["non_couvertes"] == []
    rg.enregistrer({**VIREMENT, "id": r["id"], "exigences": [], "tests": ["TAM-901"]})  # liens réalignés
    d = rg.detail(r["id"])
    assert d["exigences"] == [] and d["tests"] == ["TAM-901"]


def test_regle_proposee_a_valider(rg):
    from atelier.domain import declarations

    declarations.ajouter_noeud("regle:tam-1-1", "regle", "Plafond", proprietes={"ticket_source": "TAM-1", "extrait": "au plus 3 cartes"}, auteur="ia")
    r = rg.detail("regle:tam-1-1")
    assert r["statut"] == "à valider" and r["source"] == "TAM-1"
    with pytest.raises(PermissionError):
        rg.creer_cas_xray("regle:tam-1-1", ["x"], projet="TAM")
