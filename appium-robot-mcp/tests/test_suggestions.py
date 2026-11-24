"""« Que faire ici ? » : suggestions au clic sur un écran, un module ou un parcours du graphe, et lancement en un clic
(brouillon BDD + demande à l'agent : concevoir, automatiser, vérifier, exécuter)."""
import pytest


def _el(cle, libelle, type_="bouton"):
    return {"key": cle, "type": type_, "libelle": libelle, "locators": [f"id={cle}"]}


@pytest.fixture
def banque(tmp_path, monkeypatch):
    from atelier.discovery import carte, connaissance
    from atelier.domain import projet

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    carte.creer_app("Banque Web", ["web"], web={"url": "https://recette.exemple.fr"}, type_="web")
    u = "https://recette.exemple.fr"
    acc = carte.observer([_el("lien_virements", "Virements", "lien"), _el("lien_aide", "Aide", "lien"), _el("bouton_payer", "Payer")], "web", u + "/")
    vir = carte.observer([_el("champ_montant", "Montant", "champ"), _el("bouton_continuer", "Continuer")], "web", u + "/virements")
    pay = carte.observer([_el("texte_paiement", "Paiement", "texte")], "web", u + "/paiement")
    for e, nom in ((acc, "accueil"), (vir, "virement_saisie"), (pay, "paiement")):
        carte.renommer(e["id"], nom, "Virements")
    carte.enregistrer_transition(acc["id"], vir["id"], "web", {"type": "tap", "cle": "lien_virements", "libelle": "Virements"})
    carte.enregistrer_transition(acc["id"], pay["id"], "web", {"type": "tap", "cle": "bouton_payer", "libelle": "Payer"})
    carte.enregistrer_transition(vir["id"], acc["id"], "web", {"type": "press_back"})
    connaissance.vider_cache()
    return carte


def test_suggestions_d_un_ecran(banque):
    from atelier.intelligence import suggestions

    r = suggestions.suggestions("ecran:accueil")
    titres = [s["titre"] for s in r["suggestions"]]
    assert "Aller à « virement saisie » par « Virements »" in titres          # chemin observé vers un écran sans test
    assert not any("Payer" in t or "paiement" in t for t in titres)            # action sensible : jamais suggérée
    assert any(s["famille"] == "derouler" and "Aide" in s["titre"] for s in r["suggestions"])
    s = next(x for x in r["suggestions"] if x["titre"].startswith("Aller à"))
    assert s["oracle"] == "observé" and s["id"] == "S1"                        # résultat attendu observé : en tête

    saisie = suggestions.suggestions("ecran:virement_saisie")["suggestions"]
    inv = next(x for x in saisie if x["titre"].startswith("Saisie invalide"))
    assert inv["oracle"] == "hypothèse" and "Continuer" in inv["attendu"]
    with pytest.raises(ValueError):
        suggestions.suggestions("module:inexistant")


def test_suggestions_d_un_module_sans_doublon(banque):
    from atelier.intelligence import suggestions

    r = suggestions.suggestions("module:Virements")
    assert len(r["suggestions"]) <= suggestions.MAX and len({s["titre"] for s in r["suggestions"]}) == len(r["suggestions"])


def test_lancer_cree_le_bdd_et_la_demande_a_l_agent(banque):
    from atelier.generation import bdd
    from atelier.integrations import boite_cursor
    from atelier.intelligence import suggestions

    s = next(x for x in suggestions.suggestions("ecran:accueil")["suggestions"] if x["titre"].startswith("Aller à"))
    r = suggestions.lancer("ecran:accueil", s["id"])
    assert r["bdd"] and bdd.charger(r["bdd"])["statut"] == "brouillon"
    d = next(x for x in boite_cursor.etat()["demandes"] if x["id"] == r["demande"]["id"])
    assert d["statut"] == "en attente" and d["mode"] == "boite"
    assert r["bdd"] in d["texte"] and "run_tests" in d["texte"] and "jamais d'action sensible" in d["texte"]
    # la même suggestion relancée ne recrée pas le scénario (anti-doublon) : l'agent reprend celui qui existe
    assert suggestions.lancer("ecran:accueil", s["id"])["bdd"] == r["bdd"]


def test_actions_sensibles_suggerees_seulement_si_l_environnement_les_autorise(banque):
    """Recette autorisée (décision journalisée) : « Payer » est suggéré, marqué sensible, et la demande à l'agent impose
    des données de test de l'équipe et le tag consomme_donnee. Sans autorisation : jamais suggéré."""
    from atelier.discovery import classement
    from atelier.integrations import boite_cursor
    from atelier.intelligence import suggestions

    assert not any("Payer" in s["titre"] for s in suggestions.suggestions("ecran:accueil", "recette")["suggestions"])
    classement.maj_regles(environnements={"recette": ["safe", "controlled", "sensitive"]})
    r = suggestions.suggestions("ecran:accueil", "recette")
    payer = next(s for s in r["suggestions"] if "Payer" in s["titre"])
    assert r["sensibles_autorises"] and payer["sensible"]
    assert not any("Payer" in s["titre"] for s in suggestions.suggestions("ecran:accueil", "production")["suggestions"])
    d = suggestions.lancer("ecran:accueil", payer["id"], "recette")["demande"]
    texte = next(x for x in boite_cursor.etat()["demandes"] if x["id"] == d["id"])["texte"]
    assert "AUTORISÉES sur l'environnement recette" in texte and "consomme_donnee" in texte and "jamais d'action sensible" not in texte
