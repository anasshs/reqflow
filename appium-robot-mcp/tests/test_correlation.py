"""Corrélation exigences Jira ↔ écrans : « vérifiée sur » (preuve issue des tests, automatique) et « réalisé par »
(association fonctionnelle, décision humaine) ne sont jamais confondues. Application et données fictives."""
import pytest


def _el(cle, libelle, type_="bouton"):
    return {"key": cle, "type": type_, "libelle": libelle, "locators": [f"id={cle}"]}


EXIGENCES = [{"cle": "DEMO-2", "type": "user_story", "resume": "Saisir un virement"},
             {"cle": "DEMO-3", "type": "user_story", "resume": "Plafond des virements"},
             {"cle": "DEMO-4", "type": "user_story", "resume": "Consulter les comptes"},
             {"cle": "DEMO-5", "type": "user_story", "resume": "Ajouter un bénéficiaire"}]
ROBOT = ("*** Settings ***\nResource    ../resources/virement.resource\n\n*** Test Cases ***\nVirement simple\n"
         "    [Tags]    DEMO-11\n    Click    ${LOC_VIREMENT_SAISIE_WEB}[bouton_valider]\n\nVirement au plafond\n"
         "    [Tags]    DEMO-13\n    Click    ${LOC_VIREMENT_SAISIE_WEB}[bouton_valider]\n")


@pytest.fixture
def banque(tmp_path, monkeypatch):
    """Un écran vu pendant une Discovery, deux tests Robot qui utilisent son locator, tous deux liés à DEMO-2 dans Xray."""
    from atelier.discovery import carte, connaissance
    from atelier.domain import projet
    from atelier.intelligence import patrimoine_xray

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    carte.creer_app("Banque Web", ["web"], web={"url": "https://recette.exemple.fr"}, type_="web")
    e = carte.observer([_el("bouton_valider", "Valider le virement")], "web", "https://recette.exemple.fr/virement")
    carte.renommer(e["id"], "virement_saisie", "Virements")
    (tmp_path / "resources").mkdir()
    (tmp_path / "resources" / "virement.resource").write_text(
        "*** Variables ***\n&{LOC_VIREMENT_SAISIE_WEB}    bouton_valider=id=bouton_valider\n&{LOC_HORS_CARTE_WEB}    bouton=id=bouton\n", "utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "virement.robot").write_text(ROBOT, "utf-8")
    patrimoine_xray.enregistrer({"projet": "DEMO", "exigences": EXIGENCES,
                                 "tests": [{"cle": "DEMO-11", "resume": "Virement simple", "exigences": ["DEMO-2"]},
                                           {"cle": "DEMO-13", "resume": "Virement au plafond", "exigences": ["DEMO-2"]}]}, "test")
    connaissance.vider_cache()
    return e["id"]


def _graphe():
    from atelier.discovery import connaissance

    connaissance.vider_cache()
    return connaissance.construire()


def test_verifiee_sur_est_creee_par_les_tests_avec_ses_preuves(banque):
    from atelier.discovery import correlation, espaces
    from atelier.domain import ontologie

    g = _graphe()
    rel = g.relations["user_story:DEMO-2|verifiee_sur|ecran:virement_saisie"]  # une seule relation pour deux tests
    assert [p["test_xray"] for p in rel.proprietes["preuves"]] == ["DEMO-11", "DEMO-13"]
    p = rel.proprietes["preuves"][0]
    assert p["scripts"][0]["fichier"] == "tests/virement.robot" and p["locators"] == ["bouton_valider"] and p["origines"]
    m = ontologie.metier(rel, g)
    assert (m["type"], m["source_system"], m["validation_status"]) == ("VERIFIED_ON", "AUTOMATED_TEST", "OFFICIAL")
    c = correlation.ecran(banque)
    assert [(v["cle"], v["via"]) for v in c["verifiees"]] == [("DEMO-2", "DEMO-11, DEMO-13")] and not c["realisees"]
    # une preuve de test n'est pas une association fonctionnelle : aucun « réalisé par », rien dans le périmètre de l'exigence
    assert not [r for r in g.relations.values() if r.type == "impacte"]
    assert "ecran:virement_saisie" not in g.atteignables("user_story:DEMO-2", "aval", {"teste_par", "impacte", "utilise", "contient"})
    assert correlation.synthese()["ecrans"][0]["etat"] == "vérifié par les tests"
    with pytest.raises(PermissionError):  # jamais déclarée à la main
        espaces.ajouter_relation("user_story:DEMO-3", "ecran:virement_saisie", "verifiee_sur")


def test_une_preuve_de_test_se_promeut_en_realise_par(banque):
    from atelier.discovery import correlation
    from atelier.domain import ontologie

    correlation.confirmer(banque, "DEMO-2")
    c = correlation.ecran(banque)
    lien = c["realisees"][0]
    assert (lien["cle"], lien["origine"]) == ("DEMO-2", "tests") and lien["valide_par"] and lien["valide_le"]
    assert [p["test_xray"] for p in lien["preuves"]] == ["DEMO-11", "DEMO-13"] and not c["verifiees"]  # preuves gardées, pas de doublon
    g = _graphe()
    m = ontologie.metier(g.relations["user_story:DEMO-2|impacte|ecran:virement_saisie"], g)
    assert (m["type"], m["source_system"], m["validation_status"]) == ("REALIZED_BY", "USER_DECLARATION", "VALIDATED")
    with pytest.raises(ValueError):
        correlation.confirmer(banque, "DEMO-2")  # pas de doublon


def test_proposition_ia_incertaine_confirmee_ou_rejetee(banque):
    from atelier.discovery import correlation
    from atelier.domain import ontologie

    r = correlation.deposer_correlations([
        {"ecran": "virement_saisie", "exigence": "DEMO-3", "verdict": "incertain", "justification": "le plafond peut être contrôlé ailleurs",
         "confiance": "faible", "preuves": ["bouton « Valider le virement »"]},
        {"ecran": "virement_saisie", "exigence": "DEMO-5", "verdict": "concerne", "justification": "x", "confiance": "certaine"}])
    assert (r["retenus"], r["incertain"], r["concerne"]) == (2, 1, 1)
    props = {p["cle"]: p for p in correlation.ecran(banque)["exigences_proposees"]}
    assert props["DEMO-3"]["jugement"]["estimation"] == "faible" and props["DEMO-3"]["jugement"]["preuves"]
    assert "estimation" not in props["DEMO-5"]["jugement"]  # estimation inconnue : ignorée, jamais inventée
    assert not [x for x in _graphe().relations.values() if x.type == "impacte"]  # une proposition n'entre pas dans le graphe

    correlation.rejeter(banque, "DEMO-3", "contrôlé sur l'écran de confirmation")
    c = correlation.ecran(banque)
    assert "DEMO-3" not in {p["cle"] for p in c["exigences_proposees"]} and c["rejetees"][0]["motif"].startswith("contrôlé")
    r = correlation.deposer_correlations([{"ecran": "virement_saisie", "exigence": "DEMO-3", "verdict": "concerne", "justification": "x"}])
    assert not r["retenus"] and "rejetée" in r["refuses"][0]["raison"]  # jamais reproposée

    correlation.confirmer(banque, "DEMO-5")
    lien = next(x for x in correlation.ecran(banque)["realisees"] if x["cle"] == "DEMO-5")
    assert lien["origine"] == "ia" and lien["jugement"]["verdict"] == "concerne"  # la proposition d'origine est gardée
    g = _graphe()
    assert ontologie.metier(g.relations["user_story:DEMO-5|impacte|ecran:virement_saisie"], g)["source_system"] == "CURSOR_VALIDATED"
    with pytest.raises(PermissionError):
        correlation.rejeter(banque, "DEMO-5")  # un lien validé se retire, il ne se rejette pas
    journal = correlation.historique(banque)
    assert [x["evenement"] for x in journal][:2] == ["confirmée", "rejetée"] and all(x["par"] for x in journal[:2])


def test_lien_manuel_depuis_le_graphe_puis_retrait(banque):
    from atelier.discovery import correlation, espaces

    espaces.ajouter_relation("ecran:virement_saisie", "user_story:DEMO-4", "impacte")  # sens indifférent : exigence → écran
    g = _graphe()
    assert "user_story:DEMO-4|impacte|ecran:virement_saisie" in g.relations
    lien = next(x for x in correlation.ecran(banque)["realisees"] if x["cle"] == "DEMO-4")
    assert lien["origine"] == "manuel" and lien["valide_par"]
    assert [x["lien"] for x in correlation.chercher_exigences("comptes", banque)] == ["réalisé par"]
    correlation.retirer(banque, "DEMO-4", "erreur d'écran")
    assert "DEMO-4" not in {x["cle"] for x in correlation.ecran(banque)["realisees"]}
    assert correlation.historique(banque)[0]["evenement"] == "retirée"


def test_aucun_lien_sans_ecran_dans_la_carte(banque):
    from atelier.discovery import carte, correlation, espaces

    assert "ecran:hors_carte" in _graphe().noeuds  # connu du dépôt seulement, jamais vu pendant une Discovery
    with pytest.raises(ValueError):
        espaces.ajouter_relation("user_story:DEMO-4", "ecran:hors_carte", "impacte")
    with pytest.raises(KeyError):
        correlation.confirmer("ecran_inconnu", "DEMO-4")
    assert not [r for r in _graphe().relations.values() if r.vers == "ecran:hors_carte" and r.type in ("impacte", "verifiee_sur")]
    carte.supprimer_ecran(banque)
    assert correlation.synthese()["carte_vide"] is True


def test_un_ecran_renomme_garde_ses_liens(banque):
    from atelier.discovery import carte, correlation

    correlation.confirmer(banque, "DEMO-3")
    carte.renommer(banque, "saisie_du_virement")
    g = _graphe()
    assert "user_story:DEMO-3|impacte|ecran:saisie_du_virement" in g.relations and "ecran:virement_saisie" not in {r.vers for r in g.relations.values() if r.type == "impacte"}
    lien = correlation.ecran(banque)["realisees"][0]
    assert (lien["cle"], lien["origine"]) == ("DEMO-3", "manuel")  # la décision, liée à l'identifiant stable de la carte, suit aussi


def test_une_preuve_perdue_est_consignee(banque, tmp_path):
    from atelier.discovery import correlation

    correlation.actualiser()  # premier relevé : rien à signaler
    assert not correlation.historique()
    (tmp_path / "tests" / "virement.robot").write_text(ROBOT.replace("[Tags]    DEMO-13", "[Tags]    sans_cle"), "utf-8")
    assert correlation.actualiser()["preuves_perdues"] == 1
    assert correlation.ecran(banque)["verifiees"][0]["via"] == "DEMO-11"  # le lien garde son autre preuve
    (tmp_path / "tests" / "virement.robot").write_text(ROBOT.replace("DEMO-13", "sans_cle").replace("DEMO-11", "sans_cle_2"), "utf-8")
    assert correlation.actualiser()["perdus"] == 1 and not correlation.ecran(banque)["verifiees"]
    assert [x["evenement"] for x in correlation.historique()] == ["lien vérifié perdu : plus aucune preuve", "preuve perdue"]


def test_tableau_de_bord_avec_un_ecran_relie_a_une_exigence(banque):
    """Le tableau de bord échouait (TypeError) dès qu'un écran portait un lien : la synthèse rend des nombres, et les
    clés des exigences reliées dans « cles_… » (constaté sur le Dashboard le 2026-11-19)."""
    from atelier.discovery import correlation
    from atelier.intelligence import pilotage

    e = correlation.synthese()["ecrans"][0]
    assert (e["verifiees"], e["cles_verifiees"], e["realisees"], e["cles_realisees"]) == (1, ["DEMO-2"], 0, [])
    correlation.confirmer(banque, "DEMO-4", "manuel")
    e = correlation.synthese()["ecrans"][0]
    assert (e["realisees"], e["cles_realisees"]) == (1, ["DEMO-4"])
    pilotage.vider_memo()
    assert "exigences_sans_ecran" in {i["id"] for i in pilotage.conception()["discovery"]["indicateurs"]}   # le calcul aboutit
    assert pilotage.decision()                                                                            # et l'aide à la décision aussi


ESIM = [{"cle": "DEMO-21", "type": "user_story", "resume": "Catalogue des forfaits eSIM"},
        {"cle": "DEMO-22", "type": "user_story", "resume": "Choisir le pays de son eSIM"},
        {"cle": "DEMO-23", "type": "user_story", "resume": "Payer une eSIM"},
        {"cle": "DEMO-24", "type": "user_story", "resume": "Installer son eSIM"},
        {"cle": "DEMO-25", "type": "user_story", "resume": "Consulter l'aide"}]


@pytest.fixture
def esim(tmp_path, monkeypatch):
    """Deux écrans de deux modules ; « esim » est dans le nom d'un écran et dans quatre exigences sur cinq."""
    from atelier.discovery import carte, connaissance
    from atelier.domain import projet
    from atelier.intelligence import patrimoine_xray

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    carte.creer_app("Voyage Web", ["web"], web={"url": "https://recette.exemple.fr"}, type_="web")
    a = carte.observer([_el("bouton_forfait", "Choisir ce forfait")], "web", "https://recette.exemple.fr/esim")
    carte.renommer(a["id"], "esim_catalogue", "eSim")
    b = carte.observer([_el("lien_faq", "Questions fréquentes", "lien")], "web", "https://recette.exemple.fr/aide")
    carte.renommer(b["id"], "aide_accueil", "Aide")
    patrimoine_xray.enregistrer({"projet": "DEMO", "exigences": ESIM, "tests": []}, "test")
    connaissance.vider_cache()
    return a["id"], b["id"]


def test_un_mot_commun_a_trop_d_exigences_ne_preselectionne_rien(esim):
    """« esim » est partout : il ne distingue aucune exigence. Seul « catalogue » fonde une présélection pour l'IA."""
    from atelier.discovery import correlation

    c = correlation.ecran(esim[0])
    assert c["mots_ignores"] == ["esim"]
    assert [(p["cle"], p["mots"]) for p in c["candidats"]] == [("DEMO-21", ["catalogue"])]
    assert correlation._mots_communs([{"esim"}, {"esim"}, {"esim"}]) == set()            # trop peu d'exigences pour parler de proportion
    assert correlation._mots_communs([{"a", "b"}, {"a"}, {"a", "b"}, {"c"}]) == {"a"}    # la moitié exactement ne suffit pas
    # l'IA reçoit cette présélection et peut toujours citer n'importe quelle exigence de la liste
    vue = correlation.correlations_a_juger(esim[0])
    assert [x["cle"] for x in vue["ecrans"][0]["candidats"]] == ["DEMO-21"] and len(vue["exigences"]) == 5


def test_seule_l_ia_propose(esim):
    """Sans jugement d'une IA, aucune proposition : la ressemblance des mots n'est qu'une présélection. « concerne » et
    « incertain » sont des propositions ; « ne concerne pas » est écarté, visible à part. La décision reste humaine."""
    from atelier.discovery import correlation

    avant = correlation.ecran(esim[1])                                                    # « aide » en commun avec DEMO-25
    assert avant["exigences_proposees"] == [] and [p["cle"] for p in avant["candidats"]] == ["DEMO-25"]
    s = {x["nom"]: x for x in correlation.synthese()["ecrans"]}
    assert (s["aide_accueil"]["proposees"], s["aide_accueil"]["a_juger"], s["aide_accueil"]["etat"]) == (0, 1, "à corréler")

    correlation.deposer_correlations([
        {"ecran": "esim_catalogue", "exigence": "DEMO-23", "verdict": "incertain", "justification": "le paiement peut commencer ici"},
        {"ecran": "esim_catalogue", "exigence": "DEMO-24", "verdict": "concerne", "justification": "bouton « Choisir ce forfait »"},
        {"ecran": "esim_catalogue", "exigence": "DEMO-21", "verdict": "ne_concerne_pas", "justification": "liste gérée ailleurs"}])
    c = correlation.ecran(esim[0])
    assert [p["cle"] for p in c["exigences_proposees"]] == ["DEMO-24", "DEMO-23"]          # concerne, puis incertain
    assert [p["cle"] for p in c["ecartees_ia"]] == ["DEMO-21"] and c["candidats"] == []
    s = {x["nom"]: x for x in correlation.synthese()["ecrans"]}
    assert (s["esim_catalogue"]["proposees"], s["esim_catalogue"]["ecartees_ia"], s["esim_catalogue"]["etat"]) == (2, 1, "propositions à trancher")
    # l'IA revoit ses jugements en relisant l'écran : présélection et verdicts déjà déposés
    vus = {x["cle"]: (x["jugement"] or {}).get("verdict") for x in correlation.correlations_a_juger(esim[0])["ecrans"][0]["candidats"]}
    assert vus == {"DEMO-24": "concerne", "DEMO-23": "incertain", "DEMO-21": "ne_concerne_pas"}

    correlation.confirmer(esim[0], "DEMO-24")
    correlation.confirmer(esim[0], "DEMO-21")                                             # l'humain peut contredire l'IA
    correlation.confirmer(esim[1], "DEMO-25")                                             # ou relier sans elle : lien manuel
    origines = {x["cle"]: x["origine"] for e in esim for x in correlation.ecran(e)["realisees"]}
    assert origines == {"DEMO-24": "ia", "DEMO-21": "manuel", "DEMO-25": "manuel"}


def test_perimetre_de_la_correlation(esim):
    """Un module (ou un parcours validé) borne la liste des écrans ; un périmètre inconnu est refusé."""
    from fastapi.testclient import TestClient

    from atelier.discovery import correlation
    from web_app_loader import charger_app_web

    s = correlation.synthese()
    assert len(s["ecrans"]) == 2 and s["perimetre"] is None
    assert [(p["noeud"], p["ecrans"]) for p in s["perimetres"]] == [("module:Aide", 1), ("module:eSim", 1)]
    s = correlation.synthese("module:eSim")
    assert [x["nom"] for x in s["ecrans"]] == ["esim_catalogue"] and s["perimetre"]["libelle"] == "eSim" and not s["carte_vide"]
    assert s["sans_exigence"] == 1                                                        # les compteurs suivent le périmètre
    with pytest.raises(KeyError):
        correlation.synthese("module:Inconnu")
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/").status_code == 200
    assert [x["nom"] for x in c.get("/api/discovery/correlation", params={"perimetre": "module:Aide"}).json()["ecrans"]] == ["aide_accueil"]
    r = c.get("/api/discovery/correlation", params={"perimetre": "parcours:inconnu"})
    assert r.status_code == 400 and "inconnu" in r.json()["detail"].lower()
