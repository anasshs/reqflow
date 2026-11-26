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


def test_lancer_cree_un_travail_qui_avance_seul(banque, monkeypatch):
    """Lancer = un travail de l'orchestrateur : brouillon BDD (atelier), conception et automatisation (agent du projet),
    dry-run et run (atelier), validation (automaticien). Le premier tour crée le BDD puis la demande à l'agent."""
    from atelier.execution import orchestrateur
    from atelier.generation import bdd
    from atelier.integrations import boite_cursor
    from atelier.intelligence import suggestions

    monkeypatch.setattr(orchestrateur, "demarrer", lambda: None)
    s = next(x for x in suggestions.suggestions("ecran:accueil")["suggestions"] if x["titre"].startswith("Aller à"))
    r = suggestions.lancer("ecran:accueil", s["id"])
    assert r["etapes"] == ["Brouillon BDD", "Concevoir et automatiser", "Dry-run", "Run réel", "Valider le BDD et approuver le script"]
    tid = r["travail"]["id"]
    orchestrateur.avancer()                                       # brouillon BDD fait par l'atelier
    t = orchestrateur.obtenir(tid)
    cle = t["contexte"]["bdd"]
    assert t["etapes"][0]["statut"] == "fait" and bdd.charger(cle)["statut"] == "brouillon"
    orchestrateur.avancer()                                       # demande déposée pour l'agent du projet
    d = next(x for x in boite_cursor.etat()["demandes"] if x.get("travail") == tid)
    assert cle in d["texte"] and tid in d["texte"] and "PAS le run réel" in d["texte"] and "jamais d'action sensible" in d["texte"]
    assert d["agent"] == boite_cursor.agent()


def test_actions_sensibles_suggerees_seulement_si_l_environnement_les_autorise(banque, monkeypatch):
    """Recette autorisée (décision journalisée) : « Payer » est suggéré, marqué sensible, et la demande à l'agent impose
    des données de test de l'équipe et le tag consomme_donnee. Sans autorisation : jamais suggéré."""
    from atelier.discovery import classement
    from atelier.execution import orchestrateur
    from atelier.intelligence import suggestions

    monkeypatch.setattr(orchestrateur, "demarrer", lambda: None)
    assert not any("Payer" in s["titre"] for s in suggestions.suggestions("ecran:accueil", "recette")["suggestions"])
    classement.maj_regles(environnements={"recette": ["safe", "controlled", "sensitive"]})
    r = suggestions.suggestions("ecran:accueil", "recette")
    payer = next(s for s in r["suggestions"] if "Payer" in s["titre"])
    assert r["sensibles_autorises"] and payer["sensible"]
    assert not any("Payer" in s["titre"] for s in suggestions.suggestions("ecran:accueil", "production")["suggestions"])
    tid = suggestions.lancer("ecran:accueil", payer["id"], "recette")["travail"]["id"]
    texte = next(e for e in orchestrateur.obtenir(tid)["etapes"] if e["type"] == "ia")["params"]["texte"]
    assert "AUTORISÉES sur l'environnement recette" in texte and "consomme_donnee" in texte and "jamais d'action sensible" not in texte
