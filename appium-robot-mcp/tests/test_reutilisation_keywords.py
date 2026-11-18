"""Réutilisation des keywords du dépôt dès la rédaction des étapes BDD : rapprochement (même nom, arguments intégrés,
libellé proche), contrôle « keyword_proche », décision humaine, garde d'écriture, revue du script, outil MCP."""
from __future__ import annotations

import shutil

import pytest

from conftest import FIXTURES

GHERKIN = """# language: fr
Fonctionnalité: Virement entre comptes
  Scénario: Virement nominal
    Étant donné Se Connecter
    Quand je saisis le montant
    Et je valide le virement
    Et Choisir Le Compte épargne
    Alors le récapitulatif s'affiche
"""


@pytest.fixture
def depot(projet):
    shutil.copytree(FIXTURES / "projet_robot", projet, dirs_exist_ok=True)
    socle = projet / "resources" / "socle" / "commun.resource"
    socle.write_text(socle.read_text("utf-8") + "\nChoisir Le Compte ${type}\n    Log    ${type}\n", "utf-8")
    return projet


def test_rapprochement_existant_proche_a_creer(depot):
    from atelier.generation.reutilisation import Rapprocheur

    r = Rapprocheur()
    assert r.etape("se connecter")["correspondance"] == "nom"                       # casse et espaces ignorés
    assert r.etape("que Valider Le Virement")["keyword"] == "Valider Le Virement"   # « que » retiré
    x = r.etape("Choisir Le Compte épargne")
    assert (x["statut"], x["correspondance"]) == ("existant", "arguments intégrés")
    x = r.etape("je valide le virement")
    assert x["statut"] == "proche" and x["proches"][0]["keyword"] == "Valider Le Virement"
    assert x["proches"][0]["fichier"].startswith("resources/socle/commun.resource:")
    assert r.etape("le récapitulatif s'affiche")["statut"] == "à créer"


@pytest.mark.parametrize("texte", ["je ne valide pas le virement", "le virement est refusé", "je consulte le solde"])
def test_sens_different_jamais_proche(depot, texte):
    """Une négation ou un autre résultat n'est pas un doublon : rien n'est proposé."""
    from atelier.generation.reutilisation import Rapprocheur

    assert Rapprocheur().etape(texte)["statut"] == "à créer"


def test_inventaire_relu_quand_le_depot_change(depot):
    from atelier.generation import reutilisation

    assert reutilisation.Rapprocheur().etape("Consulter Le Solde")["statut"] == "à créer"
    (depot / "resources" / "socle" / "solde.resource").write_text("*** Keywords ***\nConsulter Le Solde\n    No Operation\n", "utf-8")
    assert reutilisation.Rapprocheur().etape("Consulter Le Solde")["statut"] == "existant"


def test_controle_puis_decision_humaine(depot):
    from atelier.generation import bdd

    m = bdd.creer("DEMO-70", depuis_xray={"gherkin": GHERKIN}, jdd="VIREMENT_STANDARD")
    proches = [c for c in bdd.controles(m) if c["code"] == "keyword_proche"]
    assert len(proches) == 2 and all(c["gravite"] == "moyenne" and c["etape"] for c in proches)
    assert "Valider Le Virement" in " ".join(c["message"] for c in proches)
    e_montant, e_valide = m["scenarios"][0]["etapes"][1]["id"], m["scenarios"][0]["etapes"][2]["id"]
    # 1. reprendre le keyword existant : l'étape devient « existant »
    m = bdd.modifier_etape("DEMO-70", e_valide, texte="Valider Le Virement")
    assert bdd.reutilisation(m)[e_valide]["statut"] == "existant"
    # 2. confirmer un nouveau keyword : plus signalé, la décision est gardée dans le modèle
    m = bdd.modifier_etape("DEMO-70", e_montant, keyword_nouveau=True)
    assert bdd.reutilisation(m)[e_montant] | {"proches": []} == {"statut": "à créer", "confirme": True, "keyword": "", "id": "",
                                                                 "fichier": "", "documentation": "", "correspondance": "", "proches": []}
    assert not [c for c in bdd.controles(m) if c["code"] == "keyword_proche"]
    assert bdd.charger("DEMO-70")["scenarios"][0]["etapes"][1]["keyword_nouveau"] is True
    # 3. un texte modifié remet la décision en jeu
    m = bdd.modifier_etape("DEMO-70", e_montant, texte="je saisis le montant du virement")
    assert "keyword_nouveau" not in m["scenarios"][0]["etapes"][1]
    assert [c["etape"] for c in bdd.controles(m) if c["code"] == "keyword_proche"] == [e_montant]


def test_generation_refusee_tant_qu_un_doublon_est_possible(depot):
    from atelier.adapters import facade
    from atelier.generation import bdd

    m = bdd.creer("DEMO-71", depuis_xray={"gherkin": GHERKIN}, jdd="VIREMENT_STANDARD")
    g = facade.studio_generer_depuis_bdd("DEMO-71")  # l'aperçu reste possible et nomme les doublons probables
    assert g["keywords_reutilises"] == ["Choisir Le Compte ${type}", "Se Connecter"]
    assert {(x["etape"], x["keyword"]) for x in g["keywords_proches"]} == {("je saisis le montant", "Saisir Le Montant"),
                                                                          ("je valide le virement", "Valider Le Virement")}
    assert "Doublon probable de « Valider Le Virement »" in g["contenu"]
    with pytest.raises(ValueError, match="ressemble au keyword existant « Saisir Le Montant »"):
        facade.studio_generer_depuis_bdd("DEMO-71", ecrire=True)
    assert not (depot / g["chemin"]).exists()
    for e in m["scenarios"][0]["etapes"][1:3]:
        bdd.modifier_etape("DEMO-71", e["id"], texte={"je saisis le montant": "Saisir Le Montant",
                                                       "je valide le virement": "Valider Le Virement"}[e["texte"]])
    g = facade.studio_generer_depuis_bdd("DEMO-71", ecrire=True)
    assert g["keywords_proches"] == [] and g["keywords_a_creer"] == ["le récapitulatif s'affiche"]
    assert (depot / g["ecrit"]).exists()
    import server

    bilan = server.run_robot(g["ecrit"], dry_run=True)  # l'appel à arguments intégrés est résolu par Robot
    assert bilan["code_retour"] == 0, bilan["console_fin"]


def test_mapping_et_revue_signalent_les_doublons(depot):
    from atelier.generation import bdd, studio

    bdd.creer("DEMO-72", depuis_xray={"gherkin": GHERKIN}, jdd="VIREMENT_STANDARD")
    mp = studio.mapping_bdd("DEMO-72")
    assert (mp["existants"], mp["a_creer"], mp["doublons_possibles"]) == (2, 3, 2)
    etape = mp["scenarios"][0]["etapes"][2]
    assert etape["statut"] == "à créer" and etape["proches"][0]["keyword"] == "Valider Le Virement"
    # un script qui redéfinit un keyword proche du socle est signalé à la revue technique
    suite = depot / "tests" / "doublon.robot"
    suite.write_text("*** Settings ***\nResource    ../resources/socle/commun.resource\n\n*** Test Cases ***\nCas\n"
                     "    [Tags]    DEMO-72\n    Je Valide Le Virement\n\n*** Keywords ***\nJe Valide Le Virement\n    No Operation\n", "utf-8")
    c = {x["code"]: x for x in studio.controles_script("tests/doublon.robot")}["doublons_keywords"]
    assert c["gravite"] == "moyenne" and "« Je Valide Le Virement » ≈ « Valider Le Virement »" in c["message"]
    assert {x["code"]: x for x in studio.controles_script("tests/virement.robot")}["doublons_keywords"]["gravite"] == "ok"


def test_outil_mcp_rapprocher_etapes(depot):
    from atelier.adapters import facade

    r = facade.studio_rapprocher_etapes(["Se Connecter", "je valide le virement", "le récapitulatif s'affiche", " "])
    assert [e["statut"] for e in r["etapes"]] == ["existant", "proche", "à créer"]
    assert (r["existants"], r["proches"], r["a_creer"]) == (1, 1, 1)
    assert r["etapes"][1]["proches"][0]["keyword"] == "Valider Le Virement" and "reprendre le libellé exact" in r["consigne"]


def test_vue_web_expose_le_rapprochement(depot):
    from fastapi.testclient import TestClient

    from web_app_loader import charger_app_web

    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/").status_code == 200  # la page d'accueil pose le cookie de session
    v = c.post("/api/bdd", json={"cle": "DEMO-73", "titre": "Virement"}).json()
    sid = v["scenario"]["scenarios"][0]["id"]
    v = c.post("/api/bdd/DEMO-73/operation", json={"op": "ajouter_etape", "scenario": sid, "mot": "Quand", "texte": "je valide le virement"}).json()
    eid = v["scenario"]["scenarios"][0]["etapes"][0]["id"]
    assert v["reutilisation"][eid]["statut"] == "proche"
    assert c.post("/api/bdd/DEMO-73/generer", json={"ecrire": True}).status_code == 400
    v = c.post("/api/bdd/DEMO-73/operation", json={"op": "modifier_etape", "etape": eid, "keyword_nouveau": True}).json()
    assert v["reutilisation"][eid]["confirme"] is True
    assert c.post("/api/bdd/DEMO-73/generer", json={"ecrire": True}).status_code == 200


# =========================================================================== jugement délégué à une IA (Cursor / LLM)
SYNONYMES = """# language: fr
Fonctionnalité: Virement entre comptes
  Scénario: Virement nominal
    Étant donné Se Connecter
    Quand je confirme l'opération
    Et je valide le virement
    Alors le récapitulatif s'affiche
"""


def _ids(m):
    return {e["texte"]: e["id"] for e in m["scenarios"][0]["etapes"]}


def test_keywords_juges_par_cursor_controles_puis_bloquants(depot):
    from atelier.adapters import facade
    from atelier.generation import bdd

    ids = _ids(bdd.creer("DEMO-80", depuis_xray={"gherkin": SYNONYMES}, jdd="VIREMENT_STANDARD"))
    confirme, valide, recap = ids["je confirme l'opération"], ids["je valide le virement"], ids["le récapitulatif s'affiche"]
    assert bdd.reutilisation(bdd.charger("DEMO-80"))[confirme]["statut"] == "à créer"   # synonyme : invisible pour les mots
    assert "keywords_a_juger" in {c["code"] for c in bdd.controles(bdd.charger("DEMO-80"))}
    vue = facade.studio_keywords_a_juger("DEMO-80")
    assert [e["etape"] for e in vue["etapes"]] == [confirme, valide, recap]              # « Se Connecter » existe : pas à juger
    assert "synonyme" in vue["consigne"] and vue["verdicts"] == ["reutiliser", "creer"]
    assert "Valider Le Virement" in {k["keyword"] for k in vue["socle"]}                 # tout le dépôt est citable
    cand = next(e for e in vue["etapes"] if e["etape"] == valide)["candidats"][0]
    assert cand["keyword"] == "Valider Le Virement" and "Cliquer Sur" in cand["corps"] and cand["proximite_mots"] == 1.0
    r = facade.studio_juger_keywords("DEMO-80", [
        {"etape": confirme, "verdict": "réutiliser", "keyword": "valider le virement", "justification": "Confirmer l'opération = valider le virement saisi"},
        {"etape": recap, "verdict": "creer", "justification": "Aucun keyword ne vérifie l'affichage du récapitulatif"},
        {"etape": recap, "verdict": "creer", "justification": "x"},                                   # déjà jugée dans cet envoi
        {"etape": "inconnue", "verdict": "creer", "justification": "x"},                              # étape inconnue
        {"etape": ids["Se Connecter"], "verdict": "creer", "justification": "x"},                     # keyword existant : non jugeable
        {"etape": valide, "verdict": "fusionner", "justification": "x"},                              # verdict inconnu
        {"etape": valide, "verdict": "reutiliser", "justification": "x"},                             # keyword non cité
        {"etape": valide, "verdict": "reutiliser", "keyword": "Keyword Inventé", "justification": "x"},  # keyword absent du dépôt
        {"etape": valide, "verdict": "creer"},                                                        # sans justification
    ])
    assert (r["retenus"], r["réutiliser"], r["créer"]) == (2, 1, 1) and [x["index"] for x in r["refuses"]] == [3, 4, 5, 6, 7, 8, 9]
    m = bdd.charger("DEMO-80")
    x = bdd.reutilisation(m)[confirme]
    assert x["statut"] == "proche" and x["proches"][0]["keyword"] == "Valider Le Virement" and x["proches"][0]["juge"] is True
    assert x["jugement"]["source"] == "Cursor (MCP)" and x["jugement"]["fichier"].startswith("resources/socle/commun.resource:")
    assert _ids(m) == ids                                                                # aucun texte modifié par l'IA
    c = next(c for c in bdd.controles(m) if c["etape"] == confirme)
    assert c["code"] == "keyword_proche" and "selon Cursor (MCP)" in c["message"]
    assert "keywords_a_juger" not in {c["code"] for c in bdd.controles(m)}                # tout est jugé ou vu par les mots
    with pytest.raises(ValueError, match="fait la même action que le keyword existant « Valider Le Virement » selon Cursor"):
        facade.studio_generer_depuis_bdd("DEMO-80", ecrire=True)
    mp = facade.studio_scenario_bdd("DEMO-80")["mapping"]
    assert mp["scenarios"][0]["etapes"][1]["jugement_keyword"]["verdict"] == "réutiliser" and mp["doublons_possibles"] == 2


def test_jugement_ne_remplace_jamais_la_decision_humaine(depot):
    from atelier.generation import bdd, reutilisation

    ids = _ids(bdd.creer("DEMO-81", depuis_xray={"gherkin": SYNONYMES}, jdd="VIREMENT_STANDARD"))
    confirme, valide = ids["je confirme l'opération"], ids["je valide le virement"]
    # « créer » d'une IA ne lève pas un doublon vu par les mots
    reutilisation.deposer_jugements_keywords("DEMO-81", [{"etape": valide, "verdict": "creer", "justification": "autre écran"}])
    assert bdd.reutilisation(bdd.charger("DEMO-81"))[valide]["statut"] == "proche"
    # l'automaticien tranche contre le verdict « réutiliser » : l'étape n'est plus bloquante ni rejugeable
    reutilisation.deposer_jugements_keywords("DEMO-81", [{"etape": confirme, "verdict": "reutiliser", "keyword": "Valider Le Virement",
                                                          "justification": "même action"}])
    m = bdd.modifier_etape("DEMO-81", confirme, keyword_nouveau=True)
    x = bdd.reutilisation(m)[confirme]
    assert (x["statut"], x["confirme"], x["jugement"]["verdict"]) == ("à créer", True, "réutiliser")
    assert confirme not in {e["etape"] for e in reutilisation.keywords_pour_agent("DEMO-81")["etapes"]}
    # une branche reprend l'étape commune : la décision et le jugement suivent le texte
    m = bdd.ajouter_branche("DEMO-81", confirme, "Refus", "negatif", [{"mot": "Alors", "texte": "un message d'erreur s'affiche"}])
    copie = m["scenarios"][1]["etapes"][1]["id"]
    assert copie != confirme and bdd.reutilisation(m)[copie]["confirme"] is True
    # un texte modifié remet le jugement en jeu
    m = bdd.modifier_etape("DEMO-81", valide, texte="je valide l'envoi du virement")
    assert "jugement_keyword" not in next(e for e in m["scenarios"][0]["etapes"] if e["id"] == valide)


def test_keywords_ia_directe(depot, monkeypatch):
    import json

    from atelier.generation import bdd, reutilisation
    from atelier.intelligence import fournisseur_ia

    confirme = _ids(bdd.creer("DEMO-82", depuis_xray={"gherkin": SYNONYMES}))["je confirme l'opération"]
    monkeypatch.setenv("IA_FOURNISSEUR", "cursor")
    assert reutilisation.juger_keywords_ia("DEMO-82")["disponible"] is False  # Cursor passe par le MCP : l'atelier n'appelle rien
    monkeypatch.setenv("IA_FOURNISSEUR", "interne")
    monkeypatch.setattr(fournisseur_ia, "configure", lambda: True)
    envoye = {}
    monkeypatch.setattr(fournisseur_ia, "completer", lambda s, d, m=0: envoye.setdefault("d", d) and json.dumps(
        {"jugements": [{"etape": confirme, "verdict": "reutiliser", "keyword": "Valider Le Virement", "justification": "synonyme"}]}))
    r = reutilisation.juger_keywords_ia("DEMO-82")
    assert r["disponible"] and r["retenus"] == 1 and confirme in envoye["d"] and "Valider Le Virement" in envoye["d"]
    assert bdd.reutilisation(bdd.charger("DEMO-82"))[confirme]["jugement"]["source"].startswith("IA interne")
