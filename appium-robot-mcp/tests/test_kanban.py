"""Atelier en Kanban : backlog de sujets (parcours, User Stories) et tickets tests, colonne déduite de ce qui existe,
appartenance des tests à leurs sujets, transitions qui lancent des travaux de l'orchestrateur ou publient, refus
expliqués, lancement d'un sujet en un clic (couvrir puis automatiser)."""
import pytest


@pytest.fixture
def atelier(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.domain import projet
    from atelier.execution import orchestrateur

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    monkeypatch.setenv("ATELIER_FLUX", "simple")
    monkeypatch.setattr(orchestrateur, "demarrer", lambda: None)   # pas de boucle : on regarde les travaux créés
    carte.creer_app("Banque Démo", ["android"])
    (tmp_path / "tests").mkdir()
    return tmp_path


def _scenario(cle, parcours="", etapes=True, tag=""):
    from atelier.discovery import carte
    from atelier.generation import bdd

    bdd.creer(cle, cle.title())
    if etapes:
        bdd.depuis_texte(cle, f"# language: fr\n{'@' + tag + chr(10) if tag else ''}Fonctionnalité: {cle}\n  Scénario: {cle}\n"
                              f"    Quand je fais {cle}\n    Alors c'est fait\n")
    m = bdd.charger(cle)
    m["parcours"] = parcours
    m["application"] = carte.app_courante()
    bdd.sauver(m)


def _script(racine, cle):
    (racine / "tests" / f"{cle.lower()}.robot").write_text(f"*** Test Cases ***\n{cle}\n    [Tags]    {cle}\n    No Operation\n", "utf-8")


def _par_id(t):
    return {x["id"]: x for x in t["tickets"]}


def test_backlog_sujets_et_tests(atelier):
    from atelier.discovery import parcours_utilisateur as pu
    from atelier.generation import kanban

    p = pu.enregistrer("", {"nom": "Connexion"})
    vierge = pu.enregistrer("", {"nom": "Virement", "point_depart": "Accueil", "resultat_attendu": "Virement confirmé"})
    _scenario("VIDE", p["id"], etapes=False)
    _scenario("PRET", p["id"])
    _scenario("AUTO", p["id"])
    _script(atelier, "AUTO")
    _scenario("CRITERE", tag="DEMO-12")
    kanban.ajouter_us("demo-12")
    kanban.ajouter_us("DEMO-99", titre="Plafond de virement")
    t = kanban.tableau()
    assert [c["id"] for c in t["colonnes"]] == ["a_faire", "conception", "bdd_pret", "automatisation", "automatise", "en_run", "dans_xray"]
    x = _par_id(t)
    assert {k: v["colonne"] for k, v in x.items() if v["type"] == "test"} == {"VIDE": "a_faire", "PRET": "bdd_pret", "AUTO": "automatise",
                                                                             "CRITERE": "bdd_pret"}
    assert x["PRET"]["sujets"] == [p["id"]] and x["CRITERE"]["sujets"] == ["DEMO-12"]   # parcours / tag @US
    assert x[vierge["id"]]["type"] == "parcours" and x[vierge["id"]]["colonne"] == "a_faire"     # backlog : parcours à explorer
    assert x["DEMO-99"]["type"] == "us" and x["DEMO-99"]["titre"] == "Plafond de virement" and x["DEMO-99"]["colonne"] == "a_faire"
    s = {y["id"]: y for y in t["sujets"]}
    # un sujet garde un écart (tests BDD sans script) : il reste dans le backlog, avec ses tests à automatiser
    assert x[p["id"]]["colonne"] == "a_faire" and sorted(s[p["id"]]["a_automatiser"]) == ["PRET", "VIDE"]
    assert s[p["id"]]["tests"] == 3 and s[p["id"]]["par_colonne"]["automatise"] == 1
    for cle in ("VIDE", "PRET", "CRITERE"):
        kanban.marquer_manuel(cle)
    s = {y["id"]: y for y in kanban.tableau()["sujets"]}
    assert s[p["id"]]["etat"] == "couvert" and s[p["id"]]["a_automatiser"] == [] and s[p["id"]]["manuels"] == 2   # décision actée : hors écart
    assert s["DEMO-12"]["etat"] == "couvert"
    with pytest.raises(ValueError, match="DEMO-123"):
        kanban.ajouter_us("pas une clé")


def test_transitions_d_un_test(atelier, monkeypatch):
    from atelier.execution import orchestrateur
    from atelier.generation import conception, flux, kanban

    _scenario("PRET")
    r = kanban.deplacer("PRET", "automatisation")
    t = orchestrateur.obtenir(r["travail"])
    assert [e["titre"] for e in t["etapes"]] == ["Écrire le test Robot", "Dry-run", "Run local (téléphone)"] and t["etapes"][0]["type"] == "ia"
    c = r["ticket"]
    assert c["colonne"] == "automatisation" and c["colonne_reelle"] == "bdd_pret" and c["indicateur"]["etat"] == "en_cours"
    with pytest.raises(ValueError, match="déjà en cours"):
        kanban.deplacer("PRET", "en_run")
    orchestrateur.annuler(r["travail"])
    with pytest.raises(ValueError, match="Pas encore automatisé"):
        kanban.deplacer("PRET", "en_run")
    with pytest.raises(ValueError, match="automatiser avant"):
        kanban.deplacer("PRET", "dans_xray")
    _script(atelier, "PRET")
    r = kanban.deplacer("PRET", "en_run")
    assert orchestrateur.obtenir(r["travail"])["etapes"][0]["action"] == "run" and r["ticket"]["colonne"] == "en_run"
    orchestrateur.annuler(r["travail"])
    publie = []
    monkeypatch.setattr(flux, "publier", lambda cles, xray=None: publie.append(cles) or {"publies": [{"scenario": "PRET", "xray": "DEMO-7"}], "erreurs": []})
    monkeypatch.setattr(conception, "cle_xray_du_scenario", lambda cle: "DEMO-7" if cle == "PRET" and publie else "")
    r = kanban.deplacer("PRET", "dans_xray")
    assert r["action"] == "publie" and r["ticket"]["colonne"] == "dans_xray"
    with pytest.raises(ValueError, match="se gagne"):
        kanban.deplacer("PRET", "automatise")


def test_concevoir_un_test_vide(atelier):
    from atelier.execution import orchestrateur
    from atelier.generation import kanban

    _scenario("VIDE", etapes=False)
    with pytest.raises(ValueError, match="sans étapes"):
        kanban.deplacer("VIDE", "automatisation")
    r = kanban.deplacer("VIDE", "conception")
    assert "Conçois le scénario BDD VIDE" in orchestrateur.obtenir(r["travail"])["etapes"][0]["params"]["texte"]
    assert r["ticket"]["colonne"] == "conception"


def test_un_clic_sur_un_parcours(atelier):
    from atelier.execution import orchestrateur
    from atelier.generation import kanban

    r = kanban.ajouter_parcours("Virement", point_depart="Accueil", resultat_attendu="Virement confirmé")
    t = orchestrateur.obtenir(r["travail"])
    assert [e["titre"] for e in t["etapes"]] == ["Dérouler le parcours", "Extraire le test", "Compléter et automatiser (agent)", "Dry-run",
                                                 "Run local (téléphone)"]
    assert r["sujet"] in t["etapes"][0]["params"]["texte"] and "{bdd}" in t["etapes"][2]["params"]["texte"]
    assert t["etapes"][4]["params"] == {"sujet": r["sujet"]}
    x = _par_id(kanban.tableau())[r["sujet"]]
    assert x["colonne"] == "conception" and x["indicateur"]["etat"] == "en_cours"
    with pytest.raises(ValueError, match="déjà en cours"):
        kanban.lancer_sujet(r["sujet"])
    seul = kanban.ajouter_parcours("Solde", lancer=False)
    assert "travail" not in seul and _par_id(kanban.tableau())[seul["sujet"]]["colonne"] == "a_faire"


def test_un_clic_sur_une_us(atelier):
    from atelier.execution import orchestrateur
    from atelier.generation import kanban

    r = kanban.ajouter_us("DEMO-5", titre="Masquer le solde", criteres="Le solde se masque d'un geste", lancer=True)
    t = orchestrateur.obtenir(r["travail"])
    assert [e["titre"] for e in t["etapes"]] == ["Concevoir les tests de l'US", "Compléter et automatiser (agent)", "Dry-run", "Run local (téléphone)"]
    assert "@DEMO-5" in t["etapes"][0]["params"]["texte"] and "Le solde se masque" in t["etapes"][0]["params"]["texte"]
    assert "ne crée que les scénarios BDD qui manquent" in t["etapes"][0]["params"]["texte"]   # l'existant d'abord
    _scenario("NOUVEAU")                                                    # créé pendant le travail de l'US
    x = _par_id(kanban.tableau())
    assert x["NOUVEAU"]["sujets"] == ["DEMO-5"] and x["DEMO-5"]["colonne"] == "conception"
    with pytest.raises(ValueError, match="sujet se lance"):
        kanban.deplacer("DEMO-5", "en_run")
    orchestrateur.annuler(r["travail"])
    assert kanban.retirer_us("DEMO-5") == {"retire": "DEMO-5"}


def test_ticket(atelier):
    from atelier.discovery import parcours_utilisateur as pu
    from atelier.generation import kanban

    p = pu.enregistrer("", {"nom": "Connexion"})
    _scenario("PRET", p["id"])
    k = kanban.ticket("PRET")
    assert "Quand je fais PRET" in k["gherkin"] and k["colonne"] == "bdd_pret" and k["sujets_noms"] == [{"id": p["id"], "titre": "Connexion"}]
    s = kanban.ticket(p["id"])
    assert s["tests_du_sujet"] == [{"id": "PRET", "titre": "Pret", "colonne": "bdd_pret", "xray": ""}]


def test_enrichir_par_le_mbt_puis_qualifier(atelier, monkeypatch):
    from atelier.discovery import parcours_utilisateur as pu
    from atelier.generation import kanban, mbt_bdd
    from atelier.intelligence import mbt

    p = pu.enregistrer("", {"nom": "Connexion"})
    with pytest.raises(ValueError, match="pas encore exploré"):
        kanban.enrichir_mbt(p["id"])
    m = pu._lire(p["id"])
    m["noeud"], m["ecrans"] = "parcours:connexion", ["ecran_connexion", "ecran_accueil"]
    pu._ecrire(m)
    monkeypatch.setattr(mbt, "construire", lambda type_, id_, auteur="": {"id": "MOD-1"})
    chemins = [{"id": "C-1", "titre": "Mot de passe faux", "type": "negatif", "priorite": "haute", "valeur_ajoutee": "erreur couverte"},
               {"id": "C-2", "titre": "Session expirée", "type": "alternatif", "priorite": "moyenne", "hypothese": True}]
    monkeypatch.setattr(mbt, "analyser", lambda mid, *a, **k: {"chemins": chemins, "reutilises": [{"id": "C-0"}]})
    r = kanban.enrichir_mbt(p["id"])
    assert [c["id"] for c in r["propositions"]] == ["C-1", "C-2"] and r["reutilises"] == 1
    assert [c["id"] for c in kanban.ticket(p["id"])["propositions"]] == ["C-1", "C-2"]   # à qualifier dans le ticket, pas dans le Kanban
    generes = []
    monkeypatch.setattr(mbt_bdd, "generer", lambda mid, chemins=None, origine="": generes.append((mid, chemins)) or
                        {"crees": [{"cle": "mbt_connexion_1", "titre": "Mot de passe faux"}]})
    q = kanban.qualifier(p["id"], accepter=["C-1"], rejeter=["C-2"])
    assert generes == [("MOD-1", ["C-1"])] and q["crees"][0]["cle"] == "mbt_connexion_1" and q["restantes"] == 0
    assert [c["id"] for c in kanban.enrichir_mbt(p["id"])["propositions"]] == ["C-1"]      # rejetée : plus reproposée


def test_changer_le_jdd_redeploie_la_discovery(atelier, monkeypatch):
    from atelier.discovery import parcours_utilisateur as pu
    from atelier.execution import orchestrateur
    from atelier.generation import kanban

    p = pu.enregistrer("", {"nom": "Connexion"})
    vu = {}
    vrai = pu.enregistrer
    monkeypatch.setattr(pu, "enregistrer", lambda pid="", champs=None: vu.update(champs or {}) or vrai(pid, {k: v for k, v in (champs or {}).items() if k != "profil_donnees"}))
    r = kanban.changer_jdd(p["id"], "client_plus18")
    assert vu == {"profil_donnees": "client_plus18"}
    assert [e["titre"] for e in orchestrateur.obtenir(r["travail"])["etapes"]] == ["Dérouler le parcours", "Extraire le test"]  # sans réautomatiser


def test_rejouer_en_local_ou_en_tnr_xray(atelier, monkeypatch):
    from atelier.discovery import parcours_utilisateur as pu
    from atelier.execution import centre, orchestrateur
    from atelier.generation import conception, kanban, tnr

    p = pu.enregistrer("", {"nom": "Connexion"})
    _scenario("AUTO", p["id"])
    _scenario("PUBLIE", p["id"])
    _script(atelier, "AUTO")
    _script(atelier, "PUBLIE")
    monkeypatch.setattr(conception, "cle_xray_du_scenario", lambda cle: "DEMO-9" if cle == "PUBLIE" else "")
    r = kanban.rejouer(p["id"])
    e = orchestrateur.obtenir(r["travail"])["etapes"][0]
    assert e["action"] == "run" and len(e["params"]["tests"]) == 2 and not e["params"]["run_params"]
    orchestrateur.annuler(r["travail"])
    monkeypatch.setattr(tnr, "conventions", lambda: {"campagne": ""})
    with pytest.raises(ValueError, match="campagne TNR"):
        kanban.rejouer(p["id"], xray=True)
    monkeypatch.setattr(tnr, "conventions", lambda: {"campagne": "CAMP-1", "transition_debut": "En cours"})
    monkeypatch.setattr(centre, "campagne", lambda cid: {"id": cid, "plateformes": ["android"], "cible": "tests", "tests": [], "tags": [],
                                                         "retry": False, "xray_ticket": "DEMO-100", "environnement": "recette"})
    r = kanban.rejouer(p["id"], xray=True)
    e = orchestrateur.obtenir(r["travail"])["etapes"][0]
    assert [t.split("::")[-1] for t in e["params"]["tests"]] == ["PUBLIE"]                # publiés seulement
    assert e["params"]["run_params"] == {"xray_ticket": "DEMO-100", "jdd_env": "recette", "jira_transition_start": "En cours"}


def test_run_d_un_test_publie_retrouve_par_sa_cle_xray(atelier, monkeypatch):
    """Après publication, le test Robot porte la clé Xray au lieu de la clé du scénario : le run le retrouve quand même."""
    from atelier.execution import orchestrateur
    from atelier.generation import conception, kanban

    _scenario("CARTE")
    (atelier / "tests" / "carte.robot").write_text("*** Test Cases ***\nConsulter ma carte\n    [Tags]    DEMO-35\n    No Operation\n", "utf-8")
    monkeypatch.setattr(conception, "cle_xray_du_scenario", lambda cle: "DEMO-35" if cle == "CARTE" else "")
    monkeypatch.setattr(conception, "_publications_xray", lambda: {"CARTE": {"xray": "DEMO-35"}})
    assert [t.split("::")[-1] for t in orchestrateur._tests_du_bdd("CARTE")] == ["Consulter ma carte"]
    r = kanban.deplacer("CARTE", "en_run")
    assert [t.split("::")[-1] for t in orchestrateur.obtenir(r["travail"])["etapes"][0]["params"]["tests"]] == ["Consulter ma carte"]


def test_extraire_le_test_d_un_parcours_utilisateur(atelier, monkeypatch):
    """L'étape « Extraire le test » reçoit un parcours utilisateur (PU-…) : le test vient de sa dernière session déroulée
    et se rattache au parcours (il rejoint son couloir)."""
    from atelier.discovery import parcours_utilisateur as pu
    from atelier.execution import orchestrateur
    from atelier.generation import bdd, kanban, parcours_bdd

    p = pu.enregistrer("", {"nom": "Bout en bout"})
    m = pu._lire(p["id"])
    m["sessions"] = ["DS-1", "DS-2"]
    pu._ecrire(m)
    vus = []

    def brouillon(session="", titre="", **k):
        vus.append(session)
        if session == "DS-2":
            raise ValueError("Un parcours relie au moins deux écrans.")  # dernière session trop courte : la précédente
        bdd.creer("parcours_bout_en_bout", titre)
        return {"cle": "parcours_bout_en_bout"}
    monkeypatch.setattr(parcours_bdd, "brouillon", brouillon)
    t = orchestrateur.creer("Parcours", [{"titre": "Extraire le test", "type": "atelier", "action": "brouillon_bdd",
                                          "params": {"parcours": p["id"], "titre": "Bout en bout"}}])
    orchestrateur._etape_atelier(t, t["etapes"][0])
    assert t["etapes"][0]["statut"] == "fait" and t["contexte"]["bdd"] == "parcours_bout_en_bout" and vus == ["DS-2", "DS-1"]
    assert bdd.charger("parcours_bout_en_bout")["parcours"] == p["id"]
    assert kanban.tableau()["sujets"][0]["tests"] == 1


def test_rattrapage_d_un_sujet_et_ne_pas_automatiser(atelier):
    from atelier.discovery import parcours_utilisateur as pu
    from atelier.execution import orchestrateur
    from atelier.generation import kanban

    p = pu.enregistrer("", {"nom": "Bout en bout"})
    _scenario("BRUT", p["id"])
    _scenario("FAIT", p["id"])
    _script(atelier, "FAIT")
    _scenario("MANUEL", p["id"])
    kanban.marquer_manuel("MANUEL")
    with pytest.raises(ValueError, match="ne pas automatiser"):
        kanban.deplacer("MANUEL", "automatisation")
    r = kanban.rattraper(p["id"])
    assert r["a_automatiser"] == ["BRUT"]
    t = orchestrateur.obtenir(r["travail"])
    texte = t["etapes"][0]["params"]["texte"]
    assert "BRUT" in texte and "MANUEL" in texte and "doublon" in texte and "studio_juger_keywords" in texte   # par le MCP, sans aide
    assert [e["titre"] for e in t["etapes"]] == ["Compléter et automatiser (agent)", "Dry-run", "Run local (téléphone)"]
    assert kanban.tests_du_sujet(p["id"]) == ["tests/fait.robot::FAIT"]
    orchestrateur.annuler(r["travail"])
    kanban.marquer_manuel("BRUT")
    with pytest.raises(ValueError, match="Rien à automatiser"):
        kanban.rattraper(p["id"])


def test_run_avec_un_autre_jeu_puis_remplacement(atelier):
    from atelier.execution import orchestrateur
    from atelier.generation import bdd, kanban

    _scenario("CARTE")
    bdd.associer_jdd("CARTE", "CLIENT_A")
    (atelier / "tests" / "carte.robot").write_text("*** Test Cases ***\nCARTE\n    [Tags]    CARTE\n    Initialiser Le Test    &{JDD_CLIENT_A}\n"
                                                    "    No Operation\nAUTRE\n    Initialiser Le Test    &{JDD_CLIENT_A}\n", "utf-8")
    r = kanban.executer("CARTE", jdd="CLIENT_B")
    e = orchestrateur.obtenir(r["travail"])["etapes"][0]
    assert e["params"]["run_params"] == {"jdd_variantes": {"CLIENT_A": "CLIENT_B"}}            # ce run seulement
    assert "&{JDD_CLIENT_A}" in (atelier / "tests" / "carte.robot").read_text("utf-8")
    orchestrateur.annuler(r["travail"])
    m = kanban.remplacer_jdd("CARTE", "CLIENT_B")
    texte = (atelier / "tests" / "carte.robot").read_text("utf-8")
    assert m["tests_modifies"] == ["tests/carte.robot::CARTE"] and bdd.charger("CARTE")["jdd"] == "CLIENT_B"
    assert texte.count("&{JDD_CLIENT_B}") == 1 and texte.count("&{JDD_CLIENT_A}") == 1        # le test AUTRE garde son jeu


def test_publier_lance_l_execution_tnr(atelier, monkeypatch):
    from atelier.execution import centre, orchestrateur
    from atelier.generation import conception, flux, kanban, tnr

    _scenario("PRET")
    _script(atelier, "PRET")
    publie = []
    monkeypatch.setattr(flux, "publier", lambda cles, xray=None: publie.append(cles) or {"publies": [{"scenario": "PRET", "xray": "DEMO-7"}], "erreurs": []})
    monkeypatch.setattr(conception, "cle_xray_du_scenario", lambda cle: "DEMO-7" if publie else "")
    monkeypatch.setattr(tnr, "conventions", lambda: {"campagne": "CAMP-1"})
    monkeypatch.setattr(centre, "campagne", lambda cid: {"id": cid, "plateformes": ["android"], "cible": "tests", "tests": [], "tags": [],
                                                         "retry": False, "xray_ticket": "DEMO-100", "environnement": "recette"})
    r = kanban.deplacer("PRET", "dans_xray")
    w = orchestrateur.obtenir(r["execution"]["travail"])
    assert r["action"] == "publie" and w["etapes"][0]["params"]["run_params"]["xray_ticket"] == "DEMO-100" and w["env"] == "recette"


def test_mbt_avec_un_autre_jeu_de_donnees(atelier, monkeypatch):
    from atelier.discovery import parcours_utilisateur as pu
    from atelier.execution import orchestrateur
    from atelier.generation import kanban

    p = pu.enregistrer("", {"nom": "Connexion"})
    vu, vrai = {}, pu.enregistrer
    monkeypatch.setattr(pu, "enregistrer", lambda pid="", champs=None: vu.update(champs or {}) or vrai(pid, {k: v for k, v in (champs or {}).items() if k != "profil_donnees"}))
    r = kanban.enrichir_mbt(p["id"], profil="CLIENT_PLUS18")
    t = orchestrateur.obtenir(r["travail"])
    assert [e["titre"] for e in t["etapes"]] == ["Dérouler le parcours", "Extraire le test", "Enrichir par le MBT"]
    assert vu == {"profil_donnees": "CLIENT_PLUS18"}


def test_corriger_un_run_en_echec_par_l_agent(atelier):
    from atelier.execution import orchestrateur
    from atelier.generation import kanban

    _scenario("CARTE")
    _script(atelier, "CARTE")
    r = kanban.corriger("CARTE", "La carte est sous le pli : défiler jusqu'à ce qu'elle soit visible.")
    t = orchestrateur.obtenir(r["travail"])
    assert [e["titre"] for e in t["etapes"]] == ["Corriger le test (agent)", "Dry-run", "Run local (téléphone)"]
    assert "sous le pli" in t["etapes"][0]["params"]["texte"] and t["etapes"][2]["params"]["tests"] == ["tests/carte.robot::CARTE"]


def test_le_parcours_prend_l_environnement_des_runs(atelier, monkeypatch):
    """Sans environnement, la session de Discovery appliquerait la liste rouge complète : le parcours lancé depuis le
    Kanban prend l'environnement de la campagne TNR (recette, où l'application lève la liste rouge)."""
    from atelier.discovery import parcours_utilisateur as pu
    from atelier.execution import orchestrateur
    from atelier.generation import kanban

    monkeypatch.setattr(kanban, "_env", lambda: "recette")
    r = kanban.ajouter_parcours("Bénéficiaires")
    assert pu._lire(r["sujet"])["environnement"] == "recette"
    orchestrateur.annuler(r["travail"])
    ancien = pu.enregistrer("", {"nom": "Ancien"})
    assert not pu._lire(ancien["id"]).get("environnement")
    kanban.lancer_sujet(ancien["id"])
    assert pu._lire(ancien["id"])["environnement"] == "recette"
