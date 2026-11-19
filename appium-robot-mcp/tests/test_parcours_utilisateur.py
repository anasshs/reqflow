"""Parcours utilisateur (initiation de Discovery) : cadrage enregistré avant l'exploration, déroulé par une session,
écrans proposés puis validés. Le lien écran ↔ exigence n'est jamais créé par le cadrage. Application fictive."""
import pytest


def _el(cle, libelle, type_="bouton"):
    return {"key": cle, "type": type_, "libelle": libelle, "locators": [f"id={cle}"]}


EXIGENCES = [{"cle": "DEMO-1", "type": "epic", "resume": "Virements"},
             {"cle": "DEMO-2", "type": "user_story", "resume": "Saisir un virement", "description": "En tant que client…",
              "criteres": ["Le montant est obligatoire", "Le plafond est contrôlé"]},
             {"cle": "DEMO-4", "type": "user_story", "resume": "Consulter les comptes"}]


@pytest.fixture
def banque(projet):
    """Trois écrans déjà vus (accueil, saisie, récapitulatif), trois exigences dans la copie locale, un profil de données."""
    from atelier.discovery import carte, connaissance, donnees
    from atelier.intelligence import patrimoine_xray

    donnees._MEMOIRE.clear()
    donnees._CHOIX.clear()
    carte.creer_app("Banque Web", ["web"], web={"url": "https://recette.exemple.fr"}, type_="web")
    ids = {}
    for nom, cle, libelle in (("accueil", "lien_virements", "Virements"), ("virement_saisie", "bouton_valider", "Valider le virement"),
                              ("virement_recap", "bouton_confirmer", "Confirmer")):
        e = carte.observer([_el(cle, libelle)], "web", f"https://recette.exemple.fr/{nom}")
        carte.renommer(e["id"], nom, "Virements")
        ids[nom] = e["id"]
    patrimoine_xray.enregistrer({"projet": "DEMO", "exigences": EXIGENCES, "tests": []}, "test")
    donnees.enregistrer_variable("MONTANT", {"nom": "Montant du virement", "type": "nombre"})
    donnees.enregistrer_variable("BENEFICIAIRE", {"nom": "Bénéficiaire"})
    donnees.definir_valeur("MONTANT", 25)
    donnees.enregistrer_profil("CLIENT_STANDARD", ["MONTANT", "BENEFICIAIRE"], "Client courant", "profil")
    connaissance.vider_cache()
    return ids


def _graphe():
    from atelier.discovery import connaissance

    connaissance.vider_cache()
    return connaissance.construire()


def _derouler(pid, ecrans):
    """Une session rattachée au parcours, qui traverse les écrans dans l'ordre donné (événements de la carte)."""
    from atelier.discovery import carte, sessions_discovery
    from atelier.domain import evenements

    s = sessions_discovery.creer({"plateforme": "web", "parcours": pid, "device": "navigateur"})
    sessions_discovery.demarrer(s["id"])
    for eid in ecrans:
        evenements.publier({"type": "carte_change", "ecran": {"id": eid, "nom": carte.ecran(eid).get("nom")}})
    return sessions_discovery.arreter(s["id"])


def test_cadrage_controle_et_enregistre(banque):
    from atelier.discovery import parcours_utilisateur as pu
    from atelier.domain import ontologie

    with pytest.raises(ValueError, match="nom du parcours"):
        pu.enregistrer("", {"objectif": "sans nom"})
    with pytest.raises(ValueError, match="copie locale Jira"):
        pu.enregistrer("", {"nom": "Virement", "exigences": ["DEMO-999"]})
    with pytest.raises(ValueError, match="Profil de données inconnu"):
        pu.enregistrer("", {"nom": "Virement", "profil_donnees": "INCONNU"})
    with pytest.raises(ValueError, match="non déclarée"):
        pu.enregistrer("", {"nom": "Virement", "plateforme": "android"})
    assert pu.lister() == []                                                 # un refus n'enregistre rien

    p = pu.enregistrer("", {"nom": "Faire un virement interne", "objectif": "Virer entre deux comptes", "exigences": ["demo-2"]})
    assert p["id"] == "PU-faire_un_virement_interne" and p["statut"] == "Brouillon" and p["noeud"] == "parcours:faire_un_virement_interne"
    assert p["controles"]["pret"] is False and "plateforme" in p["controles"]["bloquants"][0]
    assert [x["cle"] for x in p["exigences"]] == ["DEMO-2"] and p["exigences"][0]["criteres"] == ["Le montant est obligatoire", "Le plafond est contrôlé"]
    with pytest.raises(ValueError, match="existe déjà"):
        pu.enregistrer("", {"nom": "faire un virement INTERNE"})

    p = pu.enregistrer(p["id"], {"profil_donnees": "CLIENT_STANDARD", "plateforme": "web", "environnement": "recette", "pilote": "cursor",
                                 "resultat_attendu": "Le virement est confirmé"})
    assert p["statut"] == "Prêt" and p["controles"]["pret"] and p["nom"] == "Faire un virement interne"      # les autres champs restent
    assert [x["cle"] for x in p["donnees"]["pretes"]] == ["MONTANT"] and p["donnees"]["bloquees"][0]["cle"] == "BENEFICIAIRE"
    assert "valeur" not in p["donnees"]["pretes"][0]                          # aucune valeur de donnée dans le cadrage
    assert any("BENEFICIAIRE" in a for a in p["controles"]["avertissements"])
    assert [h["action"] for h in reversed(p["historique"])][:2] == ["création", "modification"]
    assert {h.get("champ") for h in p["historique"]} >= {"profil de données", "plateforme", "qui navigue"}

    # Knowledge Graph : parcours déclaré (validé) et lien exigence → parcours validé d'office, lu « a le parcours »
    g = _graphe()
    n = g.noeuds["parcours:faire_un_virement_interne"]
    assert (n.statut, n.provenance, n.libelle) == ("validé", "déclaré", "Faire un virement interne")
    rel = g.relations["user_story:DEMO-2|associe_a|parcours:faire_un_virement_interne"]
    assert rel.statut == "validé" and ontologie.metier(rel, g)["type"] == "HAS_JOURNEY"
    assert not [r for r in g.relations.values() if r.type == "impacte"]      # aucun « réalisé par » créé par le cadrage
    assert "PU-faire_un_virement_interne" in p["demande_cursor"] and "discovery_parcours_cadre" in p["demande_cursor"]


def test_modifier_un_parcours_enregistre(banque):
    from atelier.discovery import parcours_utilisateur as pu

    p = pu.enregistrer("", {"nom": "Virement", "exigences": ["DEMO-2"], "plateforme": "web"})
    p = pu.enregistrer(p["id"], {"nom": "Virement interne", "exigences": ["DEMO-1", "DEMO-4"]})
    assert p["id"] == "PU-virement" and p["noeud"] == "parcours:virement"      # l'identifiant et le nœud ne changent pas
    g = _graphe()
    assert g.noeuds["parcours:virement"].libelle == "Virement interne"
    liens = sorted(r.de for r in g.relations.values() if r.vers == "parcours:virement" and r.type == "associe_a")
    assert liens == ["epic:DEMO-1", "user_story:DEMO-4"]                     # DEMO-2 retirée, les deux autres ajoutées
    assert [(x["id"], x["nom"]) for x in pu.lister()] == [("PU-virement", "Virement interne")]
    copie = pu.dupliquer(p["id"], "Virement externe")
    assert copie["id"] == "PU-virement_externe" and [x["cle"] for x in copie["exigences"]] == ["DEMO-1", "DEMO-4"] and copie["sessions"] == []
    assert pu.archiver(p["id"])["statut"] == "Archivé" and [x["id"] for x in pu.lister()] == ["PU-virement_externe"]
    assert len(pu.lister(archives=True)) == 2 and pu.archiver(p["id"], False)["statut"] == "Prêt"


def test_deroule_puis_validation_des_ecrans(banque):
    from atelier.discovery import correlation, parcours_utilisateur as pu

    p = pu.enregistrer("", {"nom": "Faire un virement", "exigences": ["DEMO-2"], "profil_donnees": "CLIENT_STANDARD", "plateforme": "web",
                            "environnement": "recette", "point_depart": "accueil"})
    s = _derouler(p["id"], [banque["accueil"], banque["virement_saisie"], banque["virement_saisie"], banque["virement_recap"]])
    c = s["config"]                                                          # le cadrage a complété la configuration de la session
    assert (c["parcours"], c["perimetre"], c["profil_donnees"], c["environnement"], c["point_depart"]) == \
        (p["id"], "Faire un virement", "CLIENT_STANDARD", "recette", "accueil")
    p = pu.obtenir(p["id"])
    assert p["statut"] == "Exploré" and [x["id"] for x in p["sessions"]] == [s["id"]]
    assert [e["nom"] for e in p["ecrans"]] == ["accueil", "virement_saisie", "virement_recap"]             # ordre du déroulé, sans répétition
    assert {e["lien"] for e in p["ecrans"]} == {"à valider"} and p["ecrans_a_valider"] == 3
    g = _graphe()
    rel = g.relations["parcours:faire_un_virement|contient|ecran:virement_saisie"]
    assert rel.statut == "à valider" and s["id"] in rel.source               # proposé, avec le déroulé pour origine

    # Corrélation : l'exigence du parcours est proposée d'abord pour ses écrans, sans jamais devenir un lien
    co = correlation.ecran(banque["virement_recap"])
    assert co["exigences_proposees"][0]["cle"] == "DEMO-2" and co["exigences_proposees"][0]["parcours"] == ["Faire un virement"]
    assert co["realisees"] == [] and not [r for r in g.relations.values() if r.type == "impacte"]
    cand = correlation.correlations_a_juger(banque["virement_recap"])["ecrans"][0]["candidats"][0]
    assert cand["cle"] == "DEMO-2" and cand["parcours"] == ["Faire un virement"]

    # validation humaine : l'accueil n'appartient pas au parcours
    with pytest.raises(ValueError, match="au moins un écran"):
        pu.valider(p["id"], [])
    p = pu.valider(p["id"], [banque["virement_saisie"], banque["virement_recap"]])
    assert p["statut"] == "Validé" and [(e["nom"], e["lien"]) for e in p["ecrans"]] == [("virement_saisie", "validé"), ("virement_recap", "validé")]
    g = _graphe()
    assert "parcours:faire_un_virement|contient|ecran:accueil" not in g.relations
    assert g.relations["parcours:faire_un_virement|contient|ecran:virement_recap"].statut == "validé"

    # nouveau déroulé : l'écran retiré n'est pas reproposé, les écrans validés le restent
    _derouler(p["id"], [banque["accueil"], banque["virement_saisie"]])
    p = pu.obtenir(p["id"])
    assert [e["nom"] for e in p["ecrans"]] == ["virement_saisie", "virement_recap"] and len(p["sessions"]) == 2
    assert {e["lien"] for e in p["ecrans"]} == {"validé"} and [e["au_dernier_deroule"] for e in p["ecrans"]] == [True, False]
    assert "parcours:faire_un_virement|contient|ecran:accueil" not in _graphe().relations


def test_ecran_renomme_reste_dans_le_parcours(banque):
    from atelier.discovery import carte, parcours_utilisateur as pu

    p = pu.enregistrer("", {"nom": "Virement", "plateforme": "web"})
    _derouler(p["id"], [banque["virement_saisie"]])
    carte.renommer(banque["virement_saisie"], "virement_formulaire", "Virements")
    e = pu.obtenir(p["id"])["ecrans"][0]
    assert (e["nom"], e["lien"]) == ("virement_formulaire", "à valider")      # le lien a suivi le renommage
    assert pu.valider(p["id"])["ecrans"][0]["lien"] == "validé"


def test_pour_l_agent_lecture_seule_et_demarrage(banque, monkeypatch):
    from atelier.adapters import facade
    from atelier.discovery import parcours_utilisateur as pu, session, sessions_discovery

    p = pu.enregistrer("", {"nom": "Faire un virement", "objectif": "Virer", "exigences": ["DEMO-2"], "profil_donnees": "CLIENT_STANDARD",
                            "plateforme": "web", "environnement": "recette"})
    assert [x["id"] for x in facade.discovery_parcours_cadre()["parcours"]] == [p["id"]]
    c = facade.discovery_parcours_cadre(p["id"])
    assert c["exigences"][0]["criteres"] and c["donnees"]["bloquees"][0]["cle"] == "BENEFICIAIRE" and "25" not in str(c)   # jamais de valeur
    with pytest.raises(KeyError, match="Parcours inconnu"):
        facade.discovery_parcours_cadre("PU-inconnu")
    with pytest.raises(KeyError):
        pu.obtenir("../../etc")                                              # identifiant contrôlé avant tout accès au disque

    monkeypatch.setattr(session, "plateforme", lambda: "web")
    s = facade.discovery_demarrer(parcours=p["id"])
    assert s["config"]["parcours"] == p["id"] and s["config"]["environnement"] == "recette" and s["config"]["profil_donnees"] == "CLIENT_STANDARD"
    assert pu.obtenir(p["id"])["statut"] == "En cours" and pu.obtenir(p["id"])["session_active"] == s["id"]
    with pytest.raises(ValueError, match="en cours"):
        pu.archiver(p["id"])
    sessions_discovery.arreter(s["id"])
    pu.archiver(p["id"])
    with pytest.raises(ValueError, match="archivé"):
        sessions_discovery.creer({"plateforme": "web", "parcours": p["id"]})
    sans = sessions_discovery.creer({"plateforme": "web"})                   # une Discovery sans parcours reste possible, inchangée
    assert sans["config"]["parcours"] == "" and sans["config"]["perimetre"] == ""


def test_routes_web(banque):
    from fastapi.testclient import TestClient

    from web_app_loader import charger_app_web

    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/").status_code == 200                                     # la page pose le jeton de session
    v = c.get("/api/discovery/cadrage").json()
    assert v["parcours"] == [] and v["options"]["plateformes"] == ["web"] and v["options"]["profils"][0]["nom"] == "CLIENT_STANDARD"
    assert "accueil" in v["options"]["ecrans"]
    assert c.post("/api/discovery/cadrage", json={"objectif": "sans nom"}).status_code == 400
    p = c.post("/api/discovery/cadrage", json={"nom": "Virement", "exigences": ["DEMO-2"], "inconnu": "ignoré"}).json()
    assert p["id"] == "PU-virement"
    p = c.post("/api/discovery/cadrage", json={"id": p["id"], "plateforme": "web"}).json()
    assert p["statut"] == "Prêt" and c.get(f"/api/discovery/cadrage/{p['id']}").json()["nom"] == "Virement"
    assert c.get("/api/discovery/cadrage/PU-inconnu").status_code == 400
    assert c.post(f"/api/discovery/cadrage/{p['id']}/valider", json={}).status_code == 400               # rien à valider avant un déroulé
    assert c.post(f"/api/discovery/cadrage/{p['id']}/archiver", json={"motif": "doublon"}).json()["statut"] == "Archivé"
    assert c.get("/api/discovery/cadrage").json()["parcours"] == [] and len(c.get("/api/discovery/cadrage?archives=true").json()["parcours"]) == 1
    assert c.post(f"/api/discovery/cadrage/{p['id']}/supprimer", json={}).status_code == 404
