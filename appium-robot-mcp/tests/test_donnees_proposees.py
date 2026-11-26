"""Données proposées par l'agent pendant une Discovery : la variable manquante entre au référentiel « à valider »,
rejoint le profil du parcours et sert tout de suite ; l'automaticien la confirme ou la change."""
import pytest


@pytest.fixture
def ref(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.domain import projet

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    monkeypatch.setenv("ATELIER_COFFRE", "non")
    carte.creer_app("Banque Démo", ["android"])
    from atelier.discovery import donnees

    return donnees


def test_proposer_confirmer_changer(ref):
    from atelier.discovery import parcours_utilisateur as pu

    p = pu.enregistrer("", {"nom": "Ajout bénéficiaire"})
    r = ref.proposer_variable("BENEFICIAIRE_RIB", "011780000012345678901234", "RIB du bénéficiaire", "texte",
                              regles={"format": r"\d{24}"}, parcours=p["id"])
    assert r["a_valider"] and r["saisie"] == "{{var:BENEFICIAIRE_RIB}}"
    profil = pu._lire(p["id"])["profil_donnees"]
    assert profil == r["profil"] == "PARCOURS_AJOUT_BENEFICIAIRE"                       # profil du parcours créé et rattaché
    assert "BENEFICIAIRE_RIB" in ref.profils_dict()[profil]["variables"]
    ref.proposer_variable("BENEFICIAIRE_NOM", "Martin", "Nom du bénéficiaire", parcours=p["id"])
    l = {x["cle"]: x for x in ref.propositions(p["id"])}
    assert set(l) == {"BENEFICIAIRE_RIB", "BENEFICIAIRE_NOM"} and l["BENEFICIAIRE_NOM"]["valeur"] == "Martin"
    with pytest.raises(ValueError):                                                     # format du champ contrôlé
        ref.proposer_variable("BENEFICIAIRE_RIB", "123", parcours=p["id"], regles={"format": r"\d{24}"})

    ref.confirmer_variable("BENEFICIAIRE_NOM", "Durand")                                # l'automaticien change la valeur
    ref.confirmer_variable("BENEFICIAIRE_RIB")                                          # ou la garde
    assert ref.propositions(p["id"]) == []
    assert ref.variables("BENEFICIAIRE_NOM")[0]["valeurs"]["profils"][profil] == "Durand"
    with pytest.raises(ValueError, match="existe déjà"):                                # une variable confirmée ne se repropose pas
        ref.proposer_variable("BENEFICIAIRE_NOM", "Autre", parcours=p["id"])
