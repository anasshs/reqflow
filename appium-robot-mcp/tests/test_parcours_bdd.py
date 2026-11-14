"""Du parcours découvert au test : brouillon BDD depuis un chemin, un parcours du Knowledge Graph ou une session."""
import pytest


def _el(cle, libelle, type_="bouton"):
    return {"key": cle, "type": type_, "libelle": libelle, "locators": [f"id={cle}"]}


@pytest.fixture
def carte_virements(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.domain import projet

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    carte.creer_app("Banque Web", ["web"], web={"url": "https://recette.exemple.fr"}, type_="web")
    u = "https://recette.exemple.fr"
    acc = carte.observer([_el("lien_virements", "Virements", "lien"), _el("lien_comptes", "Mes comptes", "lien")], "web", u + "/")
    vir = carte.observer([_el("bouton_nouveau", "Nouveau virement"), _el("lien_historique", "Historique", "lien")], "web", u + "/virements")
    sai = carte.observer([_el("champ_montant", "Montant", "champ"), _el("champ_motif", "Motif", "champ"), _el("bouton_continuer", "Continuer")],
                         "web", u + "/virements/saisie")
    carte.renommer(acc["id"], "accueil")
    carte.renommer(vir["id"], "virements")
    carte.renommer(sai["id"], "virement_saisie", "Virements")
    carte.enregistrer_transition(acc["id"], vir["id"], "web", {"type": "tap", "cle": "lien_virements", "libelle": "Virements"})
    carte.enregistrer_transition(vir["id"], sai["id"], "web", {"type": "tap", "cle": "bouton_nouveau", "libelle": "Nouveau virement"})
    return carte, (acc["id"], vir["id"], sai["id"])


def test_brouillon_depuis_un_chemin(carte_virements):
    from atelier.generation import bdd, parcours_bdd

    _, (acc, _vir, sai) = carte_virements
    r = parcours_bdd.brouillon(ecrans=["accueil", "virement_saisie"], titre="Initier un virement")
    g = r["gherkin"]
    assert "Étant donné que je suis sur l'écran accueil" in g and "Quand je touche virements" in g and "Alors l'écran virement saisie est affiché" in g
    assert r["locators"] == {"connus": 2, "manquants": 0} and r["donnees"] == []
    assert any("Nouveau virement" in a for a in r["avertissements"])  # action sensible signalée
    m = bdd.charger(r["cle"])
    sc = m["scenarios"][0]
    assert "action_sensible" in sc["tags"] and m["statut"] == "brouillon" and not any(e["valide"] for e in sc["etapes"])
    quand = [e for e in sc["etapes"] if e["type"] == "when"]
    assert quand[0]["locator"] == "id=lien_virements" and quand[0]["ecran"] == "accueil"
    assert not [c for c in r["controles"] if c["code"] == "donnee_litterale"]
    assert parcours_bdd.brouillon(ecrans=["accueil", "virement_saisie"], titre="Initier un virement")["cle"] == r["cle"] + "_2"


def test_brouillon_depuis_un_parcours_propose(carte_virements, monkeypatch):
    from atelier.discovery import apprentissage, sessions_discovery
    from atelier.generation import parcours_bdd

    monkeypatch.setattr(sessions_discovery, "active", lambda: None)
    for e in ("virement_saisie", "accueil", "virements"):  # proposés dans le désordre
        apprentissage.proposer("parcours", "Virement interne", e)
    assert parcours_bdd.ecrans_du_parcours("parcours:virement_interne") == [carte_virements[1][i] for i in (0, 1, 2)]
    r = parcours_bdd.brouillon(parcours="parcours:virement_interne")
    assert r["ecrans"] == ["accueil", "virements", "virement_saisie"] and "parcours" in r["cle"]


def test_brouillon_depuis_une_session_et_champs(carte_virements):
    from atelier.discovery import carte, sessions_discovery as ds
    from atelier.generation import parcours_bdd

    _, (acc, vir, sai) = carte_virements
    conf = carte.observer([_el("texte_ok", "Virement enregistré", "texte")], "web", "https://recette.exemple.fr/virements/ok")
    carte.enregistrer_transition(sai, conf["id"], "web", {"type": "tap", "cle": "bouton_continuer", "libelle": "Continuer"})
    s = ds.creer({})
    ds.demarrer(s["id"])
    for de, vers in ((acc, vir), (vir, sai), (sai, conf["id"])):
        ds._evenement(s["id"], {"type": "transition", "de": de, "vers": vers})
    r = parcours_bdd.brouillon(session=s["id"])
    assert "je renseigne montant avec le jeu de données" in r["gherkin"] and r["donnees"] == ["champ_montant", "champ_motif"]
    with pytest.raises(ValueError):
        parcours_bdd.brouillon(ecrans=["accueil"], session=s["id"])
