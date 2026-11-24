"""Flux simple : générer le BDD → automatiser → publier dans Xray. Aucune approbation intermédiaire ; la publication
(décision de l'utilisateur) valide le BDD et approuve les scripts. Les contrôles de sécurité restent : contrôle de
gravité haute, test qui crée une donnée réelle."""
import json

import pytest


@pytest.fixture
def simple(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.domain import projet

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    monkeypatch.setenv("ATELIER_FLUX", "simple")
    carte.creer_app("Banque Démo", ["android"])
    return tmp_path


def _scenario(racine, cle="SOLDE", tag="SOLDE", corps="No Operation"):
    from atelier.generation import bdd, lots

    bdd.creer(cle, "Solde")
    bdd.depuis_texte(cle, "# language: fr\nFonctionnalité: Solde\n  Scénario: Masquer le solde\n    Quand je masque le solde\n"
                          "    Alors le solde est masqué\n")
    lot = lots.creer("Lot " + cle)
    lots.rattacher(lot["id"], [cle])
    (racine / "tests").mkdir(exist_ok=True)
    f = racine / "tests" / f"{cle.lower()}.robot"
    f.write_text(f"*** Test Cases ***\nMasquer le solde\n    [Tags]    {tag}\n    {corps}\n", "utf-8")
    return lot["id"], f"tests/{cle.lower()}.robot"


def _en_revue(fichier):
    """Script généré par l'atelier, entré en revue, jamais approuvé."""
    from atelier.generation import studio

    st = studio._stock()
    st[fichier] = {"statut": "Generated", "historique": []}
    studio._ecrire_atomique(studio._dossier() / "revues_scripts.json", json.dumps(st))


def test_reglage_du_flux(simple, monkeypatch):
    from atelier.generation import flux

    assert flux.etat()["etapes"] == ["Générer le BDD", "Automatiser", "Publier dans Xray"] and flux.etat()["impose"]
    monkeypatch.delenv("ATELIER_FLUX")
    assert flux.mode() == "simple"                                       # par défaut
    assert flux.regler("complet")["mode"] == "complet" and flux.mode() == "complet"
    with pytest.raises(ValueError):
        flux.regler("express")


def test_lot_sans_approbation(simple):
    from atelier.generation import bdd, lots

    bdd.creer("NEUF", "Neuf")
    bdd.depuis_texte("NEUF", "# language: fr\nFonctionnalité: N\n  Scénario: N\n    Quand je fais n\n")
    lot = lots.creer("Lot")
    lots.rattacher(lot["id"], ["NEUF"])
    v = lots.vue(lot["id"])
    (s,) = v["scenarios"]
    assert (s["statut"], s["action"]["id"]) == ("Brouillon", "automatiser")   # pas de « Relire et valider »
    assert v["statuts"] == ["Brouillon", "Automatisé", "Dans Xray"] and v["flux"]["mode"] == "simple"
    lid, _ = _scenario(simple)
    (s,) = lots.vue(lid)["scenarios"]
    assert (s["statut"], s["action"]["id"], s["action"]["libelle"]) == ("Automatisé", "publier", "Publier dans Xray")
    assert s["verifie"] is False                                           # le run est une information, pas une étape


def test_publier_valide_et_approuve(simple, monkeypatch):
    from atelier.generation import bdd, flux, studio, tnr

    _, suite = _scenario(simple)
    _en_revue(suite)
    bdd.creer("SANS_SCRIPT", "Sans script")
    appels = []
    monkeypatch.setattr(tnr, "publier", lambda cles, xray=None: appels.append(cles) or
                        {"publies": [{"scenario": c, "xray": "DEMO-1"} for c in cles], "erreurs": [], "plan": None, "campagne": None})
    r = flux.publier(["SOLDE", "SANS_SCRIPT"])
    assert appels == [["SOLDE"]]                                           # seul l'automatisé part dans Xray
    assert [e["scenario"] for e in r["erreurs"]] == ["SANS_SCRIPT"] and "automatiser" in r["erreurs"][0]["erreur"]
    assert bdd.charger("SOLDE")["statut"] == "validé"
    rv = studio.revues_scripts()[suite]
    assert rv["statut"] == "Approved" and "publication" in rv["historique"][-1]["commentaire"]


def test_controle_grave_empeche_la_publication(simple, monkeypatch):
    from atelier.generation import flux, studio, tnr

    _, suite = _scenario(simple)
    _en_revue(suite)
    vrai = studio.revue_script
    monkeypatch.setattr(studio, "revue_script", lambda f: {**vrai(f), "controles": [{"gravite": "haute", "message": "secret en clair"}]})
    monkeypatch.setattr(tnr, "publier", lambda cles, xray=None: pytest.fail("rien ne doit partir"))
    r = flux.publier(["SOLDE"])
    assert "secret en clair" in r["erreurs"][0]["erreur"]


def test_execution_sans_approbation_sauf_donnee_reelle(simple):
    from atelier.execution import centre

    _, suite = _scenario(simple)
    _en_revue(suite)
    assert centre.controle_revue("tests")["non_valides"] == []             # flux simple : pas de revue avant d'exécuter
    _, suite2 = _scenario(simple, "VIREMENT", "VIREMENT    consomme_donnee")
    _en_revue(suite2)
    with pytest.raises(PermissionError, match="Revue requise"):
        centre.controle_revue("tests")                                     # crée une donnée réelle : toujours à valider


def test_le_travail_finit_par_publier(simple, monkeypatch):
    from atelier.execution import orchestrateur
    from atelier.generation import flux

    monkeypatch.setattr(orchestrateur, "demarrer", lambda: None)
    publies = []
    monkeypatch.setattr(flux, "publier", lambda cles, xray=None: publies.append(cles) or {"publies": [{"scenario": cles[0], "xray": "DEMO-9"}], "erreurs": []})
    t = orchestrateur.creer("Masquer le solde", [{"titre": "Publier dans Xray", "type": "humain", "action": "publier_xray", "params": {"bdd": "SOLDE"}}])
    orchestrateur._modifier(t["id"], lambda x: x["etapes"][0].update(statut="attente_decision"))
    t = orchestrateur.decider(t["id"], "E1", True)
    assert publies == [["SOLDE"]] and t["etapes"][0]["statut"] == "fait" and "DEMO-9" in t["etapes"][0]["resultat"]
    monkeypatch.setattr(flux, "publier", lambda cles, xray=None: {"publies": [], "erreurs": [{"scenario": "SOLDE", "erreur": "Xray indisponible"}]})
    t2 = orchestrateur.creer("Autre", [{"titre": "Publier dans Xray", "type": "humain", "action": "publier_xray", "params": {"bdd": "SOLDE"}}])
    orchestrateur._modifier(t2["id"], lambda x: x["etapes"][0].update(statut="attente_decision"))
    t2 = orchestrateur.decider(t2["id"], "E1", True)
    assert t2["statut"] == "echec" and "Xray indisponible" in t2["etapes"][0]["erreur"]   # à reprendre, rien de perdu
