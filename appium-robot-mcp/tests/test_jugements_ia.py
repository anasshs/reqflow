"""Jugements délégués à une IA (Cursor via le MCP, ou LLM interne / Claude en appel direct) : doublons, tests redondants,
liens exigence ↔ test, tests orphelins, corrélation écran ↔ exigence. Les règles présélectionnent par les mots ; l'IA juge
le sens avec une justification ; le serveur contrôle et motive ses refus ; l'automaticien décide (rien n'est appliqué)."""
import json

import pytest

from tests.test_intelligence_couverture import ci  # noqa: F401 — fixture : carte, patrimoine Xray, exigences Jira


@pytest.fixture
def us(ci, tmp_path):  # noqa: F811
    from atelier.intelligence import testabilite_us

    (tmp_path / "testabilite").mkdir(exist_ok=True)
    (tmp_path / "testabilite" / "us.json").write_text(json.dumps({"DEMO-12": {
        "cle": "DEMO-12", "espace": "SQ", "resume": "Plafond de virement", "statut": "Analysée", "description": "", "cas": []}}), "utf-8")
    e = lambda a, r: {"action": a, "donnees": "", "resultat": r}  # noqa: E731
    testabilite_us.deposer_proposition("DEMO-12", [], [
        {"titre": "Plafond de virement dépassé : refus", "etapes": [e("Saisir un montant au-delà du plafond", "Virement refusé, message plafond")]},
        {"titre": "Virement sous le plafond accepté", "etapes": [e("Saisir un montant sous le plafond", "Virement confirmé")]},
    ], "Cursor (MCP)")
    return testabilite_us


def _id(u, debut):
    return next(c["id"] for c in u["cas"] if c["titre"].startswith(debut))


def test_doublons_juges_controles_puis_affiches(us):
    from atelier.adapters import facade
    from atelier.intelligence import conception_avancee as ca

    u = us.detail("DEMO-12")
    refus, ok = _id(u, "Plafond"), _id(u, "Virement sous")
    vue = facade.test_design_doublons_a_juger("DEMO-12")
    assert {c["id"] for c in vue["cas"]} == {refus, ok} and "résultat opposé" in vue["consigne"]
    proches = {x["cle"] for c in vue["cas"] for x in c["candidats"] if x["type"] == "test Xray"}
    assert "DEMO-102" in proches and all("proximite_mots" in x for c in vue["cas"] for x in c["candidats"])
    r = facade.test_design_juger_doublons("DEMO-12", [
        {"cas": refus, "verdict": "réutiliser", "test": "DEMO-102", "justification": "Même contrôle : montant au-delà du plafond refusé"},
        {"cas": ok, "verdict": "creer", "justification": "DEMO-101 vérifie un virement interne sans plafond : autre objectif"},
        {"cas": ok, "verdict": "creer", "justification": "x"},                       # déjà jugé dans cet envoi
        {"cas": "inconnu", "verdict": "creer", "justification": "x"},                # cas inconnu
        {"cas": refus, "verdict": "fusionner", "justification": "x"},                # verdict inconnu (et cas déjà jugé)
    ])
    assert (r["retenus"], r["réutiliser"], r["créer"]) == (2, 1, 1) and [x["index"] for x in r["refuses"]] == [3, 4, 5]
    r = ca.deposer_jugements_doublons("DEMO-12", [{"cas": refus, "verdict": "faire_evoluer", "justification": "x"},   # test manquant
                                                  {"cas": refus, "verdict": "reutiliser", "test": "DEMO-999", "justification": "x"},
                                                  {"cas": refus, "verdict": "creer"}])                                 # sans justification
    assert r["retenus"] == 0 and len(r["refuses"]) == 3
    u = us.detail("DEMO-12")
    j = next(c for c in u["cas"] if c["id"] == refus)["doublon"]["jugement"]
    assert j["verdict"] == "réutiliser" and j["test"] == "DEMO-102" and j["source"] == "Cursor (MCP)" and j["titre"].startswith("Plafond")
    assert {c["statut"] for c in u["cas"]} == {"Proposé"}  # rien n'est rejeté par l'IA


def test_doublons_ia_directe(us, monkeypatch):
    from atelier.intelligence import conception_avancee as ca, fournisseur_ia

    monkeypatch.setenv("IA_FOURNISSEUR", "cursor")
    assert ca.juger_doublons_ia("DEMO-12")["disponible"] is False  # Cursor passe par le MCP : l'atelier n'appelle rien
    monkeypatch.setenv("IA_FOURNISSEUR", "interne")
    monkeypatch.setattr(fournisseur_ia, "configure", lambda: True)
    refus = _id(us.detail("DEMO-12"), "Plafond")
    envoye = {}
    monkeypatch.setattr(fournisseur_ia, "completer", lambda s, d, m=0: envoye.setdefault("d", d) and json.dumps(
        {"jugements": [{"cas": refus, "verdict": "faire_evoluer", "test": "DEMO-102", "justification": "même plafond, message à vérifier"}]}))
    r = ca.juger_doublons_ia("DEMO-12")
    assert r["disponible"] and r["retenus"] == 1 and refus in envoye["d"]
    j = next(c for c in r["us"]["cas"] if c["id"] == refus)["doublon"]["jugement"]
    assert j["verdict"] == "faire évoluer" and j["source"].startswith("IA interne")


def test_redondances_jugees(ci):  # noqa: F811
    from atelier.adapters import facade
    from atelier.intelligence import couverture, patrimoine_xray

    tests = patrimoine_xray.charger_vue()["tests"]
    vue = facade.xray_redondances_a_juger()
    assert "redondants" in vue["verdicts"] and all(len(p["tests"]) == 2 for p in vue["paires"])
    r = facade.xray_juger_redondances([
        {"tests": ["DEMO-101", "DEMO-102"], "verdict": "distincts", "justification": "virement accepté / refus plafond : résultat opposé"},
        {"tests": ["DEMO-101", "DEMO-150"], "verdict": "redondants", "justification": "exemple : jugé redondant"},
        {"tests": ["DEMO-101", "DEMO-101"], "verdict": "distincts", "justification": "x"},
        {"tests": ["DEMO-101", "DEMO-999"], "verdict": "distincts", "justification": "x"},
        {"tests": ["DEMO-101", "DEMO-102"], "verdict": "peut-être", "justification": "x"},
    ])
    assert (r["retenus"], r["distincts"], r["redondants"]) == (2, 1, 1) and [x["index"] for x in r["refuses"]] == [3, 4, 5]
    paires = {tuple(sorted(x["tests"])): x for x in couverture.redondances(tests)}
    # paire jugée redondante par l'IA, que les mots ne voyaient pas : ajoutée, avec son jugement
    assert paires[("DEMO-101", "DEMO-150")]["jugement"]["verdict"] == "redondants" and paires[("DEMO-101", "DEMO-150")]["similarite"] is None


def test_liens_juges_proposes_et_avis(ci):  # noqa: F811
    from atelier.adapters import facade

    ci.analyser_liens(seuil=1)  # propositions des règles (mots communs)
    regles = {(p["objet_source"], p["objet_cible"]): p for p in ci.propositions("lien_test")}
    vue = facade.coverage_liens_a_juger()
    assert vue["exigences"][0]["exigence"] in ("DEMO-12", "DEMO-13") and "ne_couvre_pas" in vue["verdicts"]
    d12 = next(x for x in vue["exigences"] if x["exigence"] == "DEMO-12")
    assert "DEMO-102" in {c["cle"] for c in d12["candidats"]}
    r = facade.coverage_juger_liens([
        {"exigence": "DEMO-12", "test": "DEMO-102", "verdict": "couvre", "criteres_couverts": ["refus au-delà du plafond"],
         "justification": "Le test saisit un montant au-delà du plafond et attend le refus"},
        {"exigence": "DEMO-12", "test": "DEMO-150", "verdict": "ne_couvre_pas", "justification": "export PDF : sans rapport"},
        {"exigence": "DEMO-11", "test": "DEMO-101", "verdict": "couvre", "justification": "x"},   # lien déjà présent dans Jira
        {"exigence": "DEMO-99", "test": "DEMO-101", "verdict": "couvre", "justification": "x"},   # exigence inconnue
        {"exigence": "DEMO-12", "test": "DEMO-101", "verdict": "couvre"},                          # justification manquante
    ])
    assert (r["retenus"], r["couvre"], r["ne_couvre_pas"]) == (2, 1, 1) and [x["index"] for x in r["refuses"]] == [3, 4, 5]
    p = next(x for x in ci.propositions("lien_test") if x["cle_unique"] == "lien:DEMO-12:DEMO-102")
    assert p["statut"] == "proposee" and p["avis_ia"]["verdict"] == "couvre" and p["avis_ia"]["criteres_couverts"]
    if ("DEMO-12", "DEMO-102") not in regles:
        assert p["source"] == "cursor" and p["score"] is None  # nouvelle proposition, sans score inventé
    # rejet par l'automaticien : jamais reproposé, même par l'IA
    ci.decider(p["id"], "rejeter", "le test vérifie un autre plafond")
    r = facade.coverage_juger_liens([{"exigence": "DEMO-12", "test": "DEMO-102", "verdict": "couvre", "justification": "x"}])
    assert r["retenus"] == 0 and "rejeté" in r["refuses"][0]["raison"]


def test_orphelins_classes_par_l_ia(ci):  # noqa: F811
    from atelier.adapters import facade

    vue = facade.coverage_orphelins_a_classer()
    assert {t["test"] for t in vue["tests"]} == {"DEMO-102", "DEMO-150"} and "associer" in vue["classes"]
    assert {"DEMO-11", "DEMO-12"} <= {x["cle"] for x in vue["exigences"]}
    r = facade.coverage_classer_orphelins([
        {"test": "DEMO-102", "classe": "associer", "cible": "DEMO-12", "justification": "vérifie le refus au-delà du plafond"},
        {"test": "DEMO-150", "classe": "technique"},                                                   # justification manquante
        {"test": "DEMO-101", "classe": "technique", "justification": "x"},                             # déjà rattaché
        {"test": "DEMO-150", "classe": "associer", "cible": "DEMO-99", "justification": "x"},          # exigence inconnue
        {"test": "DEMO-150", "classe": "supprimer", "justification": "x"},                             # classe inconnue
    ])
    assert r["retenus"] == 1 and [x["index"] for x in r["refuses"]] == [2, 3, 4, 5]
    p = next(x for x in ci.propositions("lien_test") if x["cle_unique"] == "lien:DEMO-12:DEMO-102")
    assert p["statut"] == "proposee" and p["propose_par"] == "Cursor (MCP)" and p["avis_ia"]["cible"] == "DEMO-12"
    assert p["historique"][-1]["auteur"] == "Cursor (MCP)"


def test_correlations_jugees_puis_confirmees(ci):  # noqa: F811
    from atelier.adapters import facade
    from atelier.discovery import carte, correlation
    from atelier.intelligence import patrimoine_xray

    vue = patrimoine_xray.charger_vue()
    patrimoine_xray.enregistrer({**vue, "exigences": [{"cle": "DEMO-12", "type": "user_story", "resume": "Plafond de virement dépassé"},
                                                      {"cle": "DEMO-20", "type": "user_story", "resume": "Ajout d'un bénéficiaire par IBAN"}]}, "test")
    ecran = carte.ecran("saisie_virement")
    lecture = facade.discovery_correlations_a_juger()
    assert {e["nom"] for e in lecture["ecrans"]} == {"saisie_virement", "ajout_beneficiaire"}
    assert any("Montant" in x for e in lecture["ecrans"] for x in e["elements"]) and len(lecture["exigences"]) == 2
    r = facade.discovery_juger_correlations([
        {"ecran": "ajout_beneficiaire", "exigence": "DEMO-20", "verdict": "concerne", "justification": "champ IBAN et bouton « Ajouter le bénéficiaire »"},
        {"ecran": "saisie_virement", "exigence": "DEMO-12", "verdict": "concerne", "justification": "le montant saisi ici est contrôlé par le plafond"},
        {"ecran": "inconnu", "exigence": "DEMO-12", "verdict": "concerne", "justification": "x"},
        {"ecran": "saisie_virement", "exigence": "DEMO-99", "verdict": "concerne", "justification": "x"},
        {"ecran": "saisie_virement", "exigence": "DEMO-20", "verdict": "concerne"},
    ])
    assert (r["retenus"], r["concerne"]) == (2, 2) and [x["index"] for x in r["refuses"]] == [3, 4, 5]
    benef = correlation.ecran(carte.ecran("ajout_beneficiaire")["id"])
    p = benef["exigences_proposees"][0]
    assert p["cle"] == "DEMO-20" and p["jugement"]["verdict"] == "concerne" and not benef["exigences"]  # proposé, pas établi
    correlation.confirmer(ecran["id"], "DEMO-12")
    c = correlation.ecran(ecran["id"])
    assert "DEMO-12" in {x["cle"] for x in c["exigences"]} and "DEMO-12" not in {x["cle"] for x in c["exigences_proposees"]}
    r = facade.discovery_juger_correlations([{"ecran": "saisie_virement", "exigence": "DEMO-12", "verdict": "concerne", "justification": "x"}])
    assert r["refuses"][0]["raison"] == "lien déjà établi ou confirmé"


def test_ia_directe_indisponible_sans_fournisseur(ci):  # noqa: F811
    from atelier.discovery import correlation
    from atelier.intelligence import couverture, patrimoine_xray

    assert ci.juger_liens_ia()["disponible"] is False
    assert ci.classer_orphelins_ia()["disponible"] is False
    assert couverture.juger_redondances_ia(patrimoine_xray.charger_vue()["tests"])["disponible"] in (False,)
    assert correlation.juger_ia()["disponible"] is False


def test_preconditions_xray_en_objets(ci):  # noqa: F811
    """Copie Xray réelle : préconditions en objets {cle, resume} (plantait l'analyse des liens et les orphelins)."""
    from atelier.intelligence import patrimoine_xray

    vue = patrimoine_xray.charger_vue()
    vue["tests"][0]["preconditions"] = [{"cle": "DEMO-PC1", "resume": "Client connecté"}, "Compte actif"]
    patrimoine_xray.enregistrer(vue, "test")
    assert "Client connecté" in ci._texte_test(vue["tests"][0]) and "Compte actif" in ci._texte_test(vue["tests"][0])
    assert ci.liens_a_juger()["exigences"] and ci.analyser_liens()["propositions"] >= 0 and ci.orphelins()
    assert ci.orphelins_a_classer()["exigences_total"] == 3


def test_jugement_conserve_apres_recalcul_des_regles(us):
    """« Doublons par règles (secours) » recalcule la présélection sans effacer le verdict déposé par l'IA."""
    from atelier.intelligence import conception_avancee as ca

    refus = _id(us.detail("DEMO-12"), "Plafond")
    ca.deposer_jugements_doublons("DEMO-12", [{"cas": refus, "verdict": "reutiliser", "test": "DEMO-102", "justification": "même contrôle"}])
    u = ca.verifier_doublons("DEMO-12")["us"]
    d = next(c for c in u["cas"] if c["id"] == refus)["doublon"]
    assert d["jugement"]["verdict"] == "réutiliser" and d["meilleur"]  # jugement gardé, présélection recalculée


def test_les_lots_avancent(ci):  # noqa: F811
    """Ce qu'une IA a déjà jugé n'est pas resservi en tête du lot suivant (liens, orphelins, paires redondantes)."""
    from atelier.intelligence import couverture, patrimoine_xray

    lot = ci.liens_a_juger(limite=1)["exigences"][0]
    premiere, candidat = lot["exigence"], lot["candidats"][0]["cle"]
    r = ci.deposer_jugements_liens([{"exigence": premiere, "test": candidat, "verdict": "ne_couvre_pas", "justification": "sans rapport"}])
    assert r["retenus"] == 1 and not ci.propositions("lien_test")  # rien à afficher : seulement noté comme examiné
    lot = ci.liens_a_juger(limite=1)
    assert lot["exigences"][0]["exigence"] != premiere and lot["exigences_sans_test_deja_jugees"] == 1
    juge = next(c for c in ci.liens_a_juger(premiere)["exigences"][0]["candidats"] if c["cle"] == candidat)
    assert juge["avis_ia"]["verdict"] == "ne couvre pas"  # l'IA voit ce qu'elle a déjà écarté

    assert {t["test"] for t in ci.orphelins_a_classer()["tests"]} == {"DEMO-102", "DEMO-150"}
    ci.deposer_classements_orphelins([{"test": "DEMO-102", "classe": "associer", "cible": "DEMO-12", "justification": "refus au-delà du plafond"},
                                      {"test": "DEMO-150", "classe": "nouvelle_exigence", "justification": "aucune exigence sur l'export"}])
    assert ci.orphelins_a_classer()["tests"] == []

    tests = patrimoine_xray.charger_vue()["tests"]
    paires = couverture.redondances_pour_agent(tests)["paires"]
    if len(paires) >= 2:
        a, b = (x["cle"] for x in paires[0]["tests"])
        couverture.deposer_jugements_redondances(tests, [{"tests": [a, b], "verdict": "distincts", "justification": "résultat opposé"}])
        vue = couverture.redondances_pour_agent(tests)
        assert {x["cle"] for x in vue["paires"][-1]["tests"]} == {a, b} and vue["deja_jugees"] == 1


def test_classement_deja_decide_non_compte_et_historique_garde(ci):  # noqa: F811
    p = ci.classer_orphelin("DEMO-102", "associer", "DEMO-12")           # l'automaticien propose le lien…
    auteur = p["historique"][-1]["auteur"]
    r = ci.deposer_classements_orphelins([{"test": "DEMO-102", "classe": "associer", "cible": "DEMO-12", "justification": "même contrôle"}])
    p = next(x for x in ci.propositions("lien_test") if x["id"] == p["id"])
    assert r["retenus"] == 1 and p["historique"][0]["auteur"] == auteur and p["historique"][-1]["action"] == "avis"  # non réattribué
    ci.decider(p["id"], "rejeter", "pas le même plafond")                  # … puis le rejette : jamais reproposé
    r = ci.deposer_classements_orphelins([{"test": "DEMO-102", "classe": "associer", "cible": "DEMO-12", "justification": "même contrôle"}])
    assert r["retenus"] == 0 and "rejetee" in r["refuses"][0]["raison"]


def test_ecran_vide_refuse(ci):  # noqa: F811
    """Une référence d'écran vide ne désigne pas « le premier écran sans nom »."""
    from atelier.discovery import carte, correlation
    from atelier.intelligence import patrimoine_xray

    carte.observer([{"key": "x", "type": "bouton", "libelle": "X", "locators": ["id=x"]}], "android", "sans_nom")  # écran non nommé
    with pytest.raises(KeyError):
        carte.ecran("")
    vue = patrimoine_xray.charger_vue()
    patrimoine_xray.enregistrer({**vue, "exigences": [{"cle": "DEMO-12", "type": "user_story", "resume": "Plafond"}]}, "test")
    r = correlation.deposer_correlations([{"exigence": "DEMO-12", "verdict": "concerne", "justification": "x"}])
    assert r["retenus"] == 0 and r["refuses"][0]["raison"] == "écran inconnu dans la carte" and correlation.jugements() == {}
