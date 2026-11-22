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
    refus = next(t for t in m["transitions"].values() if t.get("issue") == "fausse")
    assert refus["de"] == "E-connexion" and refus["postconditions_a_confirmer"] is False or refus["postconditions"]
    assert m["conditions"]["C-US-bq_1-1"]["confiance"] == "non vérifiée"
    # reconstruction sans changement : même version ; une décision du QA est conservée
    assert mbt.construire("module", "Comptes")["version"] == 1
    cm.valider(m["id"], "etats", next(k for k, e in m["etats"].items() if e["type"] == "erreur"))
    m2 = mbt.construire("module", "Comptes")
    assert next(e for e in m2["etats"].values() if e["type"] == "erreur")["confiance"] == "confirmée"
    assert m2["version"] == 2 and [v["version"] for v in cm.versions(m["id"])] == [1, 2]


def test_strategies_et_chemins_justifies(appli):
    from atelier.intelligence import mbt

    m = mbt.construire("module", "Comptes")
    a = mbt.analyser(m["id"], "transitions")
    assert a["structure"]["inaccessibles"] == [] and a["structure"]["impasses"] == []
    toutes = set(m["transitions"])
    assert toutes <= {t for p in a["chemins"] for t in p["transitions"]}            # chaque transition parcourue
    neg = [p for p in a["chemins"] if p["type"] == "negatif"]
    assert neg and neg[0]["conditions"][0]["issue"] == "fausse" and neg[0]["manquant"]  # hypothèse signalée, jamais confirmée
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
    assert any("n'est pas remplie" in t and "à confirmer" in t for t in textes)          # condition non confirmée signalée
    r2 = mbt_bdd.generer(m["id"], strategie="transitions")                                # même chemins : doublons, rien recréé
    assert not r2["crees"] and {x["classe"] for x in r2["ignores"]} == {"Doublon"}
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
