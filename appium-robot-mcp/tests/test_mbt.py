"""Model-Based Testing : modèle comportemental, moteur de chemins, génération BDD, couverture, impact, automatisation."""
import pytest


def _el(cle, libelle, type_="lien"):
    return {"key": cle, "type": type_, "libelle": libelle, "locators": [f"id={cle}"]}


@pytest.fixture()
def appli(projet, monkeypatch):
    """Banque fictive : accueil → connexion → tableau de bord → virement ; une US « Connexion » avec un critère de refus."""
    for v in ("XRAY_CLIENT_ID", "JIRA_BASE_URL"):
        monkeypatch.delenv(v, raising=False)
    from atelier.discovery import carte, connaissance, espaces

    carte.creer_app("Banque Démo", ["web"], web={"url": "https://banque.exemple.test"}, type_="web", build="1.0")
    u = "https://banque.exemple.test"
    acc = carte.observer([_el("lien_connexion", "Se connecter")], "web", u + "/", build="1.0")
    con = carte.observer([_el("champ_identifiant", "Identifiant", "champ"), _el("bouton_valider", "Valider", "bouton")], "web", u + "/connexion", build="1.0")
    tab = carte.observer([_el("lien_virement", "Effectuer un virement")], "web", u + "/tableau", build="1.0")
    vir = carte.observer([_el("champ_montant", "Montant", "champ")], "web", u + "/virement", build="1.0")
    for x, nom in [(acc, "accueil"), (con, "connexion"), (tab, "tableau_de_bord"), (vir, "virement")]:
        carte.renommer(x["id"], nom, "Comptes")
    carte.enregistrer_transition(acc["id"], con["id"], "web", {"type": "tap", "cle": "lien_connexion", "libelle": "Se connecter"})
    carte.enregistrer_transition(con["id"], tab["id"], "web", {"type": "tap", "cle": "bouton_valider", "libelle": "Valider"})
    carte.enregistrer_transition(tab["id"], vir["id"], "web", {"type": "tap", "cle": "lien_virement", "libelle": "Effectuer un virement"})
    espaces.ajouter_noeud("user_story:BQ-1", "user_story", "Connexion à l'espace client",
                          description="- Quand je valide un identifiant valide, le tableau de bord s'affiche\n"
                                      "- Si l'identifiant est invalide, la connexion est refusée")
    espaces.ajouter_relation("module:Comptes", "user_story:BQ-1", "contient")
    connaissance.vider_cache()
    return carte


def test_modele_construit_depuis_la_discovery_et_les_us(appli):
    from atelier.domain import comportement as cm
    from atelier.intelligence import mbt

    m = mbt.construire("module", "Comptes")
    assert m["id"] == "module-comptes" and m["version"] == 1
    ecrans = {e["nom"] for e in m["etats"].values() if e["type"] == "ecran"}
    assert ecrans == {"accueil", "connexion", "tableau_de_bord", "virement"}
    assert m["etats"]["E-accueil"]["initial"] and m["etats"]["E-virement"]["final"]
    obs = [t for t in m["transitions"].values() if t["provenance"] == "observé"]
    assert len(obs) == 3 and all(t["confiance"] == "confirmée" for t in obs)
    err = [e for e in m["etats"].values() if e["type"] == "erreur"]
    assert len(err) == 1 and err[0]["provenance"] == "déduit" and err[0]["validation"] == "à valider"
    refus = next(t for t in m["transitions"].values() if m["etats"][t["vers"]]["type"] == "erreur")
    assert refus["de"] == "E-connexion" and refus["issue"] == "vraie" and refus["niveau"] == "Déduit"     # rattachement : à valider
    nominal = next(t for t in m["transitions"].values() if t["de"] == "E-connexion" and t["provenance"] == "observé")
    assert nominal["garde"] and nominal["garde_deduite"] and nominal["issue"] == "vraie"                 # critère 1 rattaché par calcul
    cond = m["conditions"][refus["garde"]]
    assert cond["niveau"] == "Confirmé" and cond["libelle"] == "l'identifiant est invalide"              # exigence explicite
    assert nominal["niveau"] == "Observé" and m["etats"]["E-accueil"]["niveau"] == "Observé"
    assert nominal["evenement"].startswith("clic sur")
    # reconstruction sans changement : même version ; une décision du QA est conservée
    assert mbt.construire("module", "Comptes")["version"] == 1
    cm.valider(m["id"], "etats", next(k for k, e in m["etats"].items() if e["type"] == "erreur"))
    m2 = mbt.construire("module", "Comptes")
    assert next(e for e in m2["etats"].values() if e["type"] == "erreur")["niveau"] == "Confirmé"
    assert m2["version"] == 2 and [v["version"] for v in cm.versions(m["id"])] == [1, 2]


def test_strategies_et_chemins_justifies(appli):
    from atelier.intelligence import mbt

    m = mbt.construire("module", "Comptes")
    a = mbt.analyser(m["id"], "transitions")
    assert a["structure"]["inaccessibles"] == [] and a["structure"]["impasses"] == []
    toutes = set(m["transitions"])
    assert toutes <= {t for p in a["chemins"] for t in p["transitions"]}            # chaque transition parcourue
    neg = [p for p in a["chemins"] if p["type"] == "negatif"]
    assert neg and neg[0]["conditions"][-1]["issue"] == "vraie" and neg[0]["manquant"] and neg[0]["hypothese"]  # signalé, jamais exigence
    assert all(p["valeur_ajoutee"].startswith("Couvre") and p["apport"] >= 1 for p in a["chemins"])
    assert all(p["justification"] and p["id"].startswith("P-") for p in a["chemins"])
    nominal = next(p for p in a["chemins"] if p["type"] != "negatif")
    assert nominal["titre"].startswith("accueil → connexion → tableau_de_bord")
    e = mbt.analyser(m["id"], "etats")
    assert {s for p in e["chemins"] for s in p["etats"]} >= {k for k in m["etats"]}
    assert mbt.analyser(m["id"], "chemins")["chemins"] and mbt.analyser(m["id"], "critiques")["chemins"]
    paires = mbt.analyser(m["id"], "paires")["chemins"]
    assert any(len(p["transitions"]) >= 2 for p in paires)
    v = mbt.analyser(m["id"], "transitions", mode="verifie")
    assert all(p["confirme"] for p in v["chemins"])                                 # mode vérifié : éléments confirmés seulement
    with pytest.raises(ValueError):
        mbt.analyser(m["id"], "inconnue")


def test_generation_bdd_tracabilite_et_doublons(appli):
    from atelier.generation import bdd, mbt_bdd
    from atelier.intelligence import mbt

    m = mbt.construire("module", "Comptes")
    r = mbt_bdd.generer(m["id"], strategie="transitions")
    assert len(r["crees"]) >= 2 and not r["ignores"]
    s = bdd.charger(r["crees"][0]["cle"])
    assert s["mbt"]["model_id"] == m["id"] and s["mbt"]["transition_ids"] and s["mbt"]["generation_origin"] == "MBT"
    assert s["scenarios"][0]["etapes"][0]["texte"] == "que je suis sur l'écran accueil"
    neg = next(bdd.charger(c["cle"]) for c in r["crees"] if c["type"] == "negatif")
    textes = [e["texte"] for e in neg["scenarios"][0]["etapes"]]
    assert any("est remplie" in t for t in textes) and neg["scenarios"][0]["tags"] == ["mbt", "a_confirmer"]
    nom = next(bdd.charger(c["cle"]) for c in r["crees"] if c["type"] == "principal" and "tableau" in c["titre"])
    assert any("est remplie" in e["texte"] for e in nom["scenarios"][0]["etapes"])                      # critère du nominal
    assert "user_story:BQ-1" in nom["mbt"]["related_user_story_ids"]
    r2 = mbt_bdd.generer(m["id"], strategie="transitions")                                # tout est couvert : aucun chemin
    assert not r2["crees"] and not r2["ignores"]
    r3 = mbt_bdd.generer(m["id"], strategie="transitions", inclure_couverts=True)         # recibler l'existant : doublons écartés
    assert not r3["crees"] and {x["classe"] for x in r3["ignores"]} == {"Doublon"}
    c = mbt.couverture(m["id"])
    assert c["conception"]["transitions"] == c["modele"]["transitions"] and c["automatisation"]["transitions"] == 0
    assert c["execution"]["transitions"] == 0                                                  # générer n'est pas exécuter


def test_scenario_existant_couvre_par_ses_ecrans(appli):
    from atelier.generation import parcours_bdd
    from atelier.intelligence import mbt

    acc = next(e for e in appli.ecrans() if e["nom"] == "accueil")
    con = next(e for e in appli.ecrans() if e["nom"] == "connexion")
    b = parcours_bdd.brouillon([acc["id"], con["id"]], titre="Aller à la connexion")
    m = mbt.construire("module", "Comptes")
    conc = mbt.couverture_conception(m)
    t = next(k for k, x in m["transitions"].items() if x["de"] == "E-accueil")
    assert conc["par_scenario"][b["cle"]] == [t]                     # écran accueil puis connexion = la transition observée
    assert t not in mbt.analyser(m["id"], "transitions")["structure"]["transitions_non_couvertes"]


def test_impact_entre_versions_et_scenarios(appli):
    from atelier.domain import comportement as cm
    from atelier.generation import mbt_bdd
    from atelier.intelligence import mbt

    m = mbt.construire("module", "Comptes")
    r = mbt_bdd.generer(m["id"], strategie="transitions")
    v1 = cm.exiger(m["id"])["version"]
    t = next(k for k, x in m["transitions"].items() if x["de"] == "E-tableau_de_bord")
    cm.modifier(m["id"], "transitions", t, {"priorite": "haute", "postconditions": "le formulaire de virement est vide"})
    i = mbt.impact(m["id"], v1)
    assert t in [x["id"] for x in i["difference"]["transitions"]["modifies"]]
    from atelier.generation import bdd

    attendus = {c["cle"] for c in r["crees"] if t in bdd.charger(c["cle"])["mbt"]["transition_ids"]}
    assert attendus and {s["cle"] for s in i["scenarios_impactes"]} == attendus
    assert i["actions_proposees"] and i["tags_tnr"]


def test_declarations_validation_et_propositions_ia(appli, monkeypatch):
    from atelier.domain import comportement as cm
    from atelier.intelligence import fournisseur_ia, mbt

    m = mbt.construire("module", "Comptes")
    m = cm.ajouter_condition(m["id"], "Solde suffisant")
    cid = next(k for k, c in m["conditions"].items() if c["libelle"] == "Solde suffisant")
    m = cm.ajouter_etat(m["id"], "Virement refusé", "erreur", final=True)
    eid = next(k for k, e in m["etats"].items() if e["nom"] == "Virement refusé")
    m = cm.ajouter_transition(m["id"], "E-virement", eid, "Confirmer le virement", garde=cid, issue="fausse")
    assert all(x["confiance"] == "confirmée" for x in (m["conditions"][cid], m["etats"][eid]))
    with pytest.raises(PermissionError):
        cm.supprimer(m["id"], "etats", "E-accueil")                                       # observé : se rejette
    with pytest.raises(PermissionError):
        cm.valider(m["id"], "etats", eid, auteur="ia")
    m2 = mbt.construire("module", "Comptes")                                                # la déclaration survit
    assert eid in m2["etats"] and any(t.get("garde") == cid for t in m2["transitions"].values())

    monkeypatch.setattr(fournisseur_ia, "fournisseur", lambda: "interne")
    monkeypatch.setattr(fournisseur_ia, "configure", lambda: True)
    monkeypatch.setattr(fournisseur_ia, "applicatif", lambda op="": False)
    monkeypatch.setattr(fournisseur_ia, "completer", lambda s, d, n=1500: '{"etats": [{"nom": "Plafond dépassé", "type": "erreur", '
                        '"justification": "critère plafond"}], "transitions": [{"de": "virement", "vers": "Plafond dépassé", "action": "Confirmer", '
                        '"garde": "Solde suffisant", "issue": "vraie", "justification": "x"}], "conditions": [], "incoherences": ["exemple"]}')
    r = mbt.proposer_ia(m["id"])
    assert r["disponible"] and len(r["ajoutes"]) == 2
    m3 = cm.exiger(m["id"])
    nouv = next(e for e in m3["etats"].values() if e["nom"] == "Plafond dépassé")
    assert nouv["provenance"] == "déduit" and nouv["validation"] == "à valider" and nouv["confiance"] == "non vérifiée"
    k = next(k for k, e in m3["etats"].items() if e["nom"] == "Plafond dépassé")
    assert k in mbt.construire("module", "Comptes")["etats"]                                  # en attente de décision : gardée
    cm.valider(m["id"], "etats", k)
    assert k in mbt.construire("module", "Comptes")["etats"]                                  # validée par le QA : jamais perdue


def test_mode_automatique_cas_pour_us(appli):
    from atelier.intelligence import mbt

    r = mbt.cas_pour_us("BQ-1")
    assert r["modele"]["id"] == "user_story-bq_1"
    cats = {c["categorie"] for c in r["cas"]}
    assert "negatif" in cats and all(c["mbt"]["generation_origin"] == "US_MBT" for c in r["cas"])
    assert all(c["justification"] and c["etapes"] for c in r["cas"])


def test_preparation_automatisation(appli):
    from atelier.intelligence import mbt

    m = mbt.construire("module", "Comptes")
    p = next(p for p in mbt.analyser(m["id"], "transitions")["chemins"] if p["type"] == "principal")
    a = p["automatisation"]
    assert a["statut"] in ("partiel", "à découvrir") and a["manquant"]                       # jamais « prêt » sans keyword
    assert a["etapes"][0]["locators"] == ["locator:accueil.lien_connexion@web"]


def test_modele_dans_le_knowledge_graph(appli):
    from atelier.discovery import connaissance
    from atelier.domain import ontologie
    from atelier.generation import mbt_bdd
    from atelier.intelligence import mbt

    m = mbt.construire("module", "Comptes")
    r = mbt_bdd.generer(m["id"], strategie="transitions")
    connaissance.vider_cache()
    g = connaissance.construire()
    mid = "modele_comportement:module-comptes"
    assert g.noeuds[mid].type == "modele_comportement" and ("module:Comptes", "associe_a", mid) in {(x.de, x.type, x.vers) for x in g.relations.values()}
    e = g.noeuds["etat:module-comptes/E-accueil"]
    assert ontologie.type_cible(e, g) == "BehaviorState"
    rel = {(x.de, x.type, x.vers): x for x in g.relations.values()}
    assert ("etat:module-comptes/E-accueil", "associe_a", "ecran:accueil") in rel
    t = next(i for i in g.noeuds if i.startswith("transition:module-comptes/") and g.noeuds[i].statut == "validé")
    assert any(k[0] == t and k[1] == "declenchee_par" for k in rel)
    err = next(i for i, n in g.noeuds.items() if n.type == "etat" and n.proprietes.get("genre") == "erreur")
    assert g.noeuds[err].statut == "à valider"                                                 # hypothèse : jamais officielle
    sc = f"scenario:{r['crees'][0]['cle']}"
    assert any(k[0] == sc and k[1] == "derive_de" for k in rel) and any(k[0] == sc and k[1] == "verifie" and k[2].startswith("transition:") for k in rel)
    assert ontologie.metier(next(x for k, x in rel.items() if k[1] == "conduit_a"), g)["type"] == "LEADS_TO"


def test_generation_us_avec_analyse_comportementale(appli):
    """Critère 15 et 17 : la génération depuis l'US continue de fonctionner ; l'analyse comportementale s'y ajoute en
    arrière-plan (désactivable), sans que l'utilisateur voie le modèle."""
    from atelier.intelligence import conception_avancee, testabilite_us as t

    d = t._us()
    d["BQ-1"] = {"cle": "BQ-1", "resume": "Connexion à l'espace client", "statut": "Analysée", "cas": [],
                 "description": "- Quand je valide un identifiant valide, le tableau de bord s'affiche\n- Si l'identifiant est invalide, la connexion est refusée"}
    t._sauver_us(d)
    sans = conception_avancee.proposer("BQ-1", comportement="desactive")
    assert sans["comportement"]["active"] is False and not any(c.get("origine") == "US_MBT" for c in sans["us"]["cas"])
    avec = conception_avancee.proposer("BQ-1")
    mbt_cas = [c for c in avec["us"]["cas"] if c.get("origine") == "US_MBT"]
    assert avec["comportement"]["cas"] == len(mbt_cas) > 0
    assert all(c["statut"] == "Proposé" and c["gherkin"].startswith("Given que je suis sur l'écran") for c in mbt_cas)


def test_hypotheses_comportements_exceptionnels(appli):
    """§ 4 : comportements non documentés proposés comme hypothèses ; acceptés = À confirmer (jamais de résultat
    inventé) ; rejetés = jamais reproposés ; un comportement documenté n'est pas proposé."""
    from atelier.domain import comportement as cm
    from atelier.intelligence import mbt

    from atelier.discovery import connaissance

    u = "https://banque.exemple.test"
    vir = next(e for e in appli.ecrans() if e["nom"] == "virement")
    ok = appli.observer([_el("lien_retour", "Retour aux comptes")], "web", u + "/virement/ok", build="1.0")
    appli.renommer(ok["id"], "virement_effectue", "Comptes")
    appli.enregistrer_transition(vir["id"], ok["id"], "web", {"type": "tap", "cle": "bouton_confirmer", "libelle": "Confirmer le virement"})
    connaissance.vider_cache()
    m = mbt.construire("module", "Comptes")
    cats = {h["categorie"] for h in m["hypotheses"].values()}
    assert {"double_soumission", "perte_connexion", "session_expiree", "interruption", "reprise", "acces_non_autorise"} <= cats
    assert not any("Effectuer un virement" in h["libelle"] for h in m["hypotheses"].values())   # navigation, pas un engagement
    assert sum(h["categorie"] == "session_expiree" for h in m["hypotheses"].values()) == 1
    assert all(h["statut"] == "proposée" for h in m["hypotheses"].values())
    assert not any(e.get("hypothese") for e in m["etats"].values())                      # rien dans le modèle sans décision
    dbl = next(h for h in m["hypotheses"].values() if h["categorie"] == "double_soumission")
    perte = next(h for h in m["hypotheses"].values() if h["categorie"] == "perte_connexion")
    m = cm.decider_hypothese(m["id"], dbl["id"], "accepter")
    t = m["transitions"][m["hypotheses"][dbl["id"]]["transition_id"]]
    assert t["niveau"] == "À confirmer" and t["postconditions"] == "" and t["postconditions_a_confirmer"]
    with pytest.raises(ValueError):
        cm.decider_hypothese(m["id"], perte["id"], "rejeter")                              # motif obligatoire
    cm.decider_hypothese(m["id"], perte["id"], "rejeter", "géré par l'infrastructure")
    m2 = mbt.construire("module", "Comptes")                                                 # reconstruction
    assert m2["hypotheses"][perte["id"]]["statut"] == "rejetée" and m2["hypotheses"][dbl["id"]]["statut"] == "acceptée"
    assert m2["hypotheses"][dbl["id"]]["transition_id"] in m2["transitions"]
    assert "géré par l'infrastructure" not in str(mbt.analyser(m2["id"])["hypotheses"])
    c = mbt.couverture(m2["id"])
    assert c["modele"]["transitions"] == 4                                                   # hypothèses hors indicateurs officiels


def test_comportement_documente_pas_propose(appli):
    from atelier.discovery import connaissance, espaces
    from atelier.intelligence import mbt

    espaces.modifier_noeud("user_story:BQ-1", description="- Si la session a expiré, je suis renvoyé à l'écran de connexion\n"
                                                         "- Je peux annuler la saisie à tout moment")
    connaissance.vider_cache()
    m = mbt.construire("module", "Comptes")
    cats = {h["categorie"] for h in m["hypotheses"].values()}
    assert "session_expiree" not in cats and "annulation" not in cats


def test_minimum_de_chemins_et_valeur_ajoutee(appli):
    from atelier.generation import parcours_bdd
    from atelier.intelligence import mbt

    m = mbt.construire("module", "Comptes")
    a = mbt.analyser(m["id"], "transitions", mode="verifie")
    assert len(a["chemins"]) == 1 and len(a["chemins"][0]["transitions"]) == 3               # un seul chemin couvre les trois
    acc, con = (next(e for e in appli.ecrans() if e["nom"] == n) for n in ("accueil", "connexion"))
    b = parcours_bdd.brouillon([acc["id"], con["id"]], titre="Aller à la connexion")
    a2 = mbt.analyser(m["id"], "transitions", mode="verifie")
    assert a2["chemins"][0]["apport"] == 2 and b["cle"] in [r["scenario"] for r in a2["reutilises"]]   # l'existant n'est pas reciblé


def test_evolution_de_l_us_et_revisions(appli):
    """§ 8 : une nouvelle version d'une US est comparée au modèle ; chemins, scénarios et automatisations impactés ;
    révisions proposées ; aucun scénario supprimé."""
    from atelier.discovery import connaissance, espaces
    from atelier.generation import bdd, mbt_bdd
    from atelier.intelligence import mbt

    m = mbt.construire("module", "Comptes")
    r = mbt_bdd.generer(m["id"], strategie="transitions")
    espaces.modifier_noeud("user_story:BQ-1", description="- Quand je valide un identifiant valide, le tableau de bord s'affiche\n"
                                                         "- Si le mot de passe est expiré, la connexion est refusée")
    connaissance.vider_cache()
    ev = mbt.actualiser_tous(forcer=True)
    assert ev and ev[0]["vers"] == m["version"] + 1
    e = ev[0]["evolutions"]
    assert e["nombre"] and e["etats_modifies"] and e["transitions_modifiees"]                     # refus : nouvelle condition, nouveau résultat
    assert e["chemins_impactes"] and e["scenarios"] and e["revisions"]
    assert all(bdd.charger(c["cle"]) for c in r["crees"])                                       # rien supprimé
    i = mbt.impact(m["id"], m["version"])
    assert i["chemins_impactes"] and (i["tags_tnr"] or i["a_examiner"])


def test_couverture_comportementale_indicateurs(appli):
    from atelier.generation import mbt_bdd
    from atelier.intelligence import mbt

    m = mbt.construire("module", "Comptes")
    mbt_bdd.generer(m["id"], strategie="transitions")
    c = mbt.couverture(m["id"])
    i = c["indicateurs"]
    assert i["transitions"]["etablies"] == 3 and i["transitions"]["verifiees"] == 0            # conçu ≠ vérifié
    assert c["bdd"]["transitions"] == 3 and c["validee"]["transitions"] == 0 and i["scenarios_generes"] >= 1
    assert i["inconnus"] > 0 and i["chemins"]["retenus"] >= 1
    assert set(c) >= {"conception", "bdd", "automatisation", "execution", "validee"}
    gl = mbt.couverture_globale()
    assert gl["modeles"] == 1 and gl["niveaux"]["bdd"] == 3 and gl["transitions_verifiees"] == 0


def test_preparation_donnees_et_tracabilite(appli):
    from atelier.generation import mbt_bdd
    from atelier.intelligence import mbt

    m = mbt.construire("module", "Comptes")
    p = mbt.analyser(m["id"], "transitions", mode="verifie")["chemins"][0]
    a = p["automatisation"]
    assert a["statut"] != "prêt" and a["donnees"]["champs"] >= 1 and "Identifiant" in a["donnees"]["manquantes"]
    assert set(a) >= {"etapes", "preconditions", "environnements", "donnees", "manquant"}
    r = mbt_bdd.generer(m["id"], [p["id"]], "transitions", False, "MBT", None, "automaticien", False)
    t = mbt.tracabilite(r["crees"][0]["cle"])
    maillons = [x["maillon"] for x in t["chaine"]]
    assert maillons == ["Exigence", "Knowledge Graph", "Modèle MBT", "Transitions", "Chemin", "Scénario BDD", "Automatisation", "Exécution"]
    assert t["chaine"][0]["elements"] and t["chaine"][3]["elements"] and not t["chaine"][6]["elements"]
