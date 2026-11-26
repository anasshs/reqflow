"""Graphes par périmètre (module, parcours, exigence), parcours ordonné, plan de test d'un module."""
import pytest


def _el(cle, libelle, type_="bouton"):
    return {"key": cle, "type": type_, "libelle": libelle, "locators": [f"id={cle}"]}


@pytest.fixture
def deux_modules(tmp_path, monkeypatch):
    from atelier.discovery import carte, sessions_discovery
    from atelier.domain import projet
    from atelier.intelligence import patrimoine_xray

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(sessions_discovery, "active", lambda: None)
    carte.creer_app("Banque Web", ["web"], web={"url": "https://recette.exemple.fr"}, type_="web")
    u = "https://recette.exemple.fr"
    acc = carte.observer([_el("lien_virements", "Virements", "lien"), _el("lien_cartes", "Cartes", "lien")], "web", u + "/")
    vir = carte.observer([_el("bouton_nouveau", "Nouveau virement"), _el("lien_historique", "Historique", "lien")], "web", u + "/virements")
    sai = carte.observer([_el("champ_montant", "Montant", "champ"), _el("bouton_continuer", "Continuer")], "web", u + "/virements/saisie")
    crt = carte.observer([_el("bouton_opposition", "Faire opposition")], "web", u + "/cartes")
    carte.renommer(acc["id"], "accueil")
    carte.renommer(vir["id"], "virements", "Virements")
    carte.renommer(sai["id"], "virement_saisie", "Virements")
    carte.renommer(crt["id"], "cartes", "Cartes")
    carte.enregistrer_transition(acc["id"], vir["id"], "web", {"type": "tap", "cle": "lien_virements", "libelle": "Virements"})
    carte.enregistrer_transition(vir["id"], sai["id"], "web", {"type": "tap", "cle": "bouton_nouveau", "libelle": "Nouveau virement"})
    carte.enregistrer_transition(acc["id"], crt["id"], "web", {"type": "tap", "cle": "lien_cartes", "libelle": "Cartes"})
    patrimoine_xray.enregistrer({"projet": "DEMO", "tests": [{"cle": "DEMO-11", "resume": "Virement simple", "exigences": ["DEMO-2"]}],
                                 "exigences": [{"cle": "DEMO-2", "type": "user_story", "resume": "Saisir un virement", "module": "Virements"},
                                               {"cle": "DEMO-3", "type": "user_story", "resume": "Plafond des virements", "module": "Virements"},
                                               {"cle": "DEMO-9", "type": "user_story", "resume": "Opposition carte", "module": "Cartes"}]}, "test")
    return carte, (acc["id"], vir["id"], sai["id"], crt["id"])


def test_perimetre_module_et_liste(deux_modules):
    from atelier.discovery import espaces

    p = espaces.perimetres()
    assert {x["id"] for x in p["module"]} == {"module:Virements", "module:Cartes"}
    ids = {n["id"] for n in espaces.vue_connaissance(perimetre="module:Virements", patrimoine="tout")["noeuds"]}
    assert {"ecran:virements", "ecran:virement_saisie", "user_story:DEMO-2", "user_story:DEMO-3"} <= ids
    assert not {"ecran:cartes", "user_story:DEMO-9", "module:Cartes"} & ids
    with pytest.raises(KeyError):
        espaces.vue_connaissance(perimetre="module:Inconnu")


def test_parcours_ordonne_et_perimetre_parcours(deux_modules):
    from atelier.discovery import apprentissage, espaces
    from atelier.generation import parcours_bdd

    for e in ("virement_saisie", "accueil", "virements"):
        apprentissage.proposer("parcours", "Virement interne", e)
    r = parcours_bdd.etapes_parcours("parcours:virement_interne")
    assert [e["ecran"] for e in r["etapes"]] == ["accueil", "virements", "virement_saisie"]
    assert [e["action"] for e in r["etapes"]] == ["", "Virements", "Nouveau virement"]
    ids = {n["id"] for n in espaces.vue_connaissance(perimetre="parcours:virement_interne")["noeuds"]}
    assert {"ecran:accueil", "ecran:virements", "ecran:virement_saisie"} <= ids and "ecran:cartes" not in ids


def test_plan_de_test_module(deux_modules):
    from atelier.intelligence import plan_test

    p = plan_test.plan("Virements")
    assert p["id"] == "module:Virements" and p["resume"]["ecrans"] == 2
    ex = {e["cle"]: e for e in p["exigences"]}
    assert set(ex) == {"DEMO-2", "DEMO-3"} and ex["DEMO-3"]["couverture"] == "aucun test"
    assert ex["DEMO-2"]["couverture"] == "manuelle (à automatiser)" and p["a_automatiser"] == ["DEMO-11"]
    assert p["non_couvert"]["us"] == ["DEMO-3"]  # l'epic éventuel est couvert « via ses US » and any("US sans test" in x for x in p["pistes"])
    assert any("bouton_nouveau" in e["actions_sensibles"] for e in p["ecrans"])
    with pytest.raises(KeyError, match="modules : Cartes, Virements"):
        plan_test.plan("Paiements")
