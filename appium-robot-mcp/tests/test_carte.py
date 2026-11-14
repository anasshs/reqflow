"""Caractérisation de la carte de l'application (reconnaissance, transitions, chemins, édition, export)."""
from __future__ import annotations

import pytest
import yaml

from conftest import lire_fixture


@pytest.fixture
def carte(projet):
    import app_map

    app_map.creer_app("Banque Démo", ["android", "ios"], {"app_package": "com.exemple.banque"})
    return app_map


def _els(nom, plat="android"):
    import server

    return server._parse_elements(lire_fixture("hierarchies", f"{nom}.xml"), plat)


def test_application_creee_et_active(carte, projet):
    assert carte.app_courante() == "banque_demo"
    assert (projet / "app_map" / "banque_demo" / "app.yaml").exists()
    with pytest.raises(FileExistsError):
        carte.creer_app("Banque Démo", ["android"])


def test_observer_cree_puis_reconnait(carte):
    a = carte.observer(_els("android_classique"), "android", "com.exemple.Virement")
    assert a["nouveau"] and a["titre"] == "Virement"
    b = carte.observer(_els("android_classique"), "android", "com.exemple.Virement")
    assert not b["nouveau"] and b["id"] == a["id"] and b["score"] == 1.0


def test_ecran_different_non_reconnu(carte):
    a = carte.observer(_els("android_classique"), "android")
    b = carte.observer(_els("android_compose"), "android")
    assert b["nouveau"] and b["id"] != a["id"]


def test_valeurs_dynamiques_ignorees_dans_la_signature():
    import app_map

    sig = app_map.signature([{"type": "texte", "libelle": "Solde : 1 250,00 DH", "locators": []},
                             {"type": "texte", "libelle": "Montant", "locators": []}])
    assert sig == ["texte:montant"]


def test_transitions_et_chemin_le_plus_fiable(carte):
    a = carte.observer(_els("android_classique"), "android")["id"]
    b = carte.observer(_els("android_compose"), "android")["id"]
    c = carte.observer(_els("ios", "ios"), "android")["id"]
    carte.enregistrer_transition(a, b, "android", {"type": "tap", "locator": "id=x"})
    carte.enregistrer_transition(b, c, "android", {"type": "tap", "locator": "id=y"})
    t_direct = carte.enregistrer_transition(a, c, "android", {"type": "tap", "locator": "id=z"}, ok=False)
    for _ in range(5):
        carte.noter(t_direct["id"], False)
    trajet = carte.chemin(a, c, "android")
    assert [t["vers"] for t in trajet] == [b, c]
    assert carte.chemin(a, c, "ios") is None
    assert carte.chemin(a, a, "android") == []


def test_saisie_jamais_rejouee_dans_un_chemin(carte):
    a = carte.observer(_els("android_classique"), "android")["id"]
    b = carte.observer(_els("android_compose"), "android")["id"]
    carte.enregistrer_transition(a, b, "android", {"type": "type_text", "locator": "id=x"})
    assert carte.chemin(a, b, "android") is None


def test_transition_interdite_exclue(carte):
    a = carte.observer(_els("android_classique"), "android")["id"]
    b = carte.observer(_els("android_compose"), "android")["id"]
    t = carte.enregistrer_transition(a, b, "android", {"type": "tap", "locator": "id=x"})
    carte.maj_transition(t["id"], interdite=True)
    assert carte.chemin(a, b, "android") is None


def test_renommer_avec_nom_existant_fusionne(carte):
    a = carte.observer(_els("android_classique"), "android")["id"]
    b = carte.observer(_els("ios", "ios"), "ios")["id"]
    carte.renommer(a, "Virement Saisie")
    fusion = carte.renommer(b, "virement_saisie")
    assert fusion["id"] == a
    assert sorted(fusion["plateformes"]) == ["android", "ios"]
    assert len(carte.ecrans()) == 1


@pytest.mark.parametrize("libelle,interdit", [
    ("Confirmer le virement", True), ("Valider", True), ("Se déconnecter", True),
    ("Payer", True), ("Mes comptes", False), ("Historique", False),
])
def test_liste_rouge(carte, libelle, interdit):
    assert carte.interdit({"key": "bouton_x", "libelle": libelle}) is interdit


def test_export_resource_avec_secours(carte, projet):
    a = carte.observer(_els("android_classique"), "android")["id"]
    carte.renommer(a, "virement_saisie")
    p = carte.exporter_resource(a, projet / "resources" / "locators" / "virement_saisie.resource")
    txt = p.read_text("utf-8")
    assert "&{LOC_VIREMENT_SAISIE_ANDROID}    " in txt
    assert "bouton_valider=id=com.exemple.banque:id/valider" in txt
    assert "&{LOC_VIREMENT_SAISIE_ANDROID_SECOURS}" in txt
    assert "accessibility_id=Valider le virement || xpath=//*[@text='Valider']" in txt


def test_import_resources_existants(carte, projet):
    f = projet / "resources" / "locators" / "login.resource"
    f.parent.mkdir(parents=True)
    f.write_text("*** Variables ***\n&{LOC_LOGIN_ANDROID}    champ_identifiant=id=com.exemple.banque:id/login\n"
                 "...    bouton_connexion=accessibility_id=Se connecter\n"
                 "&{LOC_LOGIN_IOS}    champ_identifiant=accessibility_id=loginField\n", "utf-8")
    res = carte.importer_resources()
    assert res == {"ecrans_crees": 1, "locators_importes": 3}
    e = carte.ecran("login")
    assert e["elements"]["champ_identifiant"]["locators"] == {
        "android": ["id=com.exemple.banque:id/login"], "ios": ["accessibility_id=loginField"]}


def test_rapport_tags_elements_sans_identifiant(carte):
    a = carte.observer(_els("android_compose"), "android", test_key="DEMO-1")["id"]
    lignes = carte.rapport_tags()
    assert {x["cle"] for x in lignes} >= {"champ_montant", "bouton_continuer"}
    assert all(x["ecran_id"] == a and x["usage"] == 1 for x in lignes)


def test_fichiers_yaml_lisibles(carte, projet):
    carte.observer(_els("android_classique"), "android")
    f = next((projet / "app_map" / "banque_demo" / "ecrans").glob("*.yaml"))
    assert yaml.safe_load(f.read_text("utf-8"))["plateformes"]["android"]["signature"]
