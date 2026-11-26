"""Lots TNR : un statut unique par scénario, les étapes sautées visibles, la prochaine action, le rattachement."""
import pytest


@pytest.fixture
def appli(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.domain import projet

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    carte.creer_app("Banque Démo", ["android"])
    return tmp_path


def test_statut_unique_et_prochaine_action(appli):
    from atelier.generation import bdd, lots

    bdd.creer("SOLDE", "Solde")
    bdd.depuis_texte("SOLDE", "# language: fr\nFonctionnalité: Solde\n  Scénario: Masquer le solde\n    Quand je masque le solde\n")
    bdd.creer("VIDE", "Vide")  # scénario sans étape : pas suivi
    bdd.creer("AUTRE_APP", "Autre application")
    bdd.depuis_texte("AUTRE_APP", "# language: fr\nFonctionnalité: X\n  Scénario: X\n    Quand je fais x\n")
    assert [s["cle"] for s in lots.vue()["scenarios"]] == []          # sans lot ni application : pas affiché
    lot = lots.creer("Parcours de bout en bout", parcours="PU-bout_en_bout")
    assert lots.rattacher(lot["id"], ["SOLDE"]) == ["SOLDE"]
    v = lots.vue(lot["id"])
    (s,) = v["scenarios"]
    assert (s["statut"], s["action"]["id"], s["lot"]) == ("Brouillon", "valider", lot["id"])
    assert v["lots"][0]["compte"]["Brouillon"] == 1

    # un test Robot porte la clé du scénario : « Automatisé », alors que le scénario n'a jamais été validé
    (appli / "tests").mkdir()
    (appli / "tests" / "solde.robot").write_text("*** Test Cases ***\nMasquer le solde\n    [Tags]    SOLDE\n    No Operation\n", "utf-8")
    (s,) = lots.vue(lot["id"])["scenarios"]
    assert (s["statut"], s["a_revoir"], s["action"]["id"]) == ("Automatisé", ["Validé"], "verifier")
    assert s["tests"][0]["id"].endswith("::Masquer le solde")
    assert lots.scenarios_des_tests([s["tests"][0]["id"]]) == ["SOLDE"]

    with pytest.raises(ValueError, match="existe déjà"):
        lots.creer("Parcours de bout en bout")
    with pytest.raises(KeyError):
        lots.rattacher("inconnu", ["SOLDE"])


def test_cycle_de_reference_unique():
    from atelier.domain import cycle
    from atelier.generation import lots
    from atelier.intelligence import chemin, qualification

    assert lots.STATUTS == cycle.STATUTS_SCENARIO
    assert {e[0] for e in chemin.ETAPES} == set(cycle.DECOUPAGES["chemin"])
    assert {e[0] for e in qualification.ETAPES} == set(cycle.DECOUPAGES["qualification"])
    assert cycle.reference("chemin", "concevoir")["titre"] == "Scénariser"
    assert dict((e[0], e[2]) for e in chemin.ETAPES)["automatiser"] == "#lots"
