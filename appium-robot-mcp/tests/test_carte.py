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


# --------------------------------------------------------------------------- transition Jetpack Compose vers testTag
def test_les_testtag_arrivent_meme_ecran_memes_cles(carte):
    """L'application passe aux testTag : l'écran est reconnu (pas de doublon), chaque élément garde sa clé métier, le
    nouvel identifiant passe en premier et l'ancien locator reste en secours."""
    avant = carte.observer(_els("android_compose"), "android", build="1.0")
    cles = set(carte.ecran(avant["id"])["elements"])
    assert carte.rapport_tags()  # éléments sans identifiant : la liste donnée aux développeurs
    apres = carte.observer(_els("android_compose_testtag"), "android", build="1.1")
    assert not apres["nouveau"] and apres["id"] == avant["id"] and len(carte.ecrans()) == 1
    e = carte.ecran(avant["id"])
    assert set(e["elements"]) == cles  # aucune clé nouvelle, même quand le tag porte un autre nom (continuer_virement)
    bouton = e["elements"]["bouton_continuer"]["locators"]["android"]
    assert bouton[0] == 'android=new UiSelector().resourceId("continuer_virement")' and 'android=new UiSelector().text("Continuer")' in bouton
    champ = e["elements"]["champ_montant"]["locators"]["android"]
    assert champ[0] == 'android=new UiSelector().resourceId("champ_montant")' and champ[1].startswith("xpath=//*[@text='Montant']/following")
    assert carte.robustesse(bouton[0]) == "robuste" and carte.valeur_id(bouton[0]) == "continuer_virement"
    types = [c["type"] for c in e["changements"]]
    assert types.count("amelioration") == 3 and types.count("identifiants") == 1 and not e.get("etats")
    assert {x["cle"] for x in carte.rapport_tags()} == set()  # plus rien d'interactif à demander aux développeurs
    encore = carte.observer(_els("android_compose_testtag"), "android", build="1.1")
    assert encore["id"] == avant["id"] and encore["score"] == 1.0 and len(carte.ecrans()) == 1


def test_un_ecran_avec_testtag_ne_se_confond_pas_avec_un_autre(carte):
    a = carte.observer(_els("android_classique"), "android")["id"]
    b = carte.observer(_els("android_compose_testtag"), "android")
    assert b["nouveau"] and b["id"] != a  # la reconnaissance par libellés ne fusionne pas deux écrans différents
    assert carte.signature(_els("android_compose_testtag"), sans_ids=True) == carte.signature(_els("android_compose"))


def test_studio_classe_un_testtag_stable():
    from atelier.generation import studio

    assert studio.fiabilite('android=new UiSelector().resourceId("champ_montant")') == ("resource-id", "Stable")
    assert studio.fiabilite('android=new UiSelector().text("Continuer")')[1] != "Stable"


def test_studio_propose_le_testtag_meme_pour_un_locator_par_texte(carte, projet):
    """Le dépôt repère le bouton par son texte (« Reliable ») ; son testTag arrive dans la carte sous la même clé :
    le Studio propose de passer à l'identifiant."""
    from atelier.generation import studio_avance

    e = carte.observer(_els("android_compose"), "android")
    carte.renommer(e["id"], "nouveau_virement")
    (projet / "resources").mkdir(exist_ok=True)
    (projet / "resources" / "virement.resource").write_text(
        '*** Variables ***\n&{LOC_NOUVEAU_VIREMENT_ANDROID}    bouton_continuer=android=new UiSelector().text("Continuer")\n', "utf-8")
    assert not [c for c in studio_avance.propositions_correction() if c["proposition"]]
    carte.observer(_els("android_compose_testtag"), "android")
    c = [c for c in studio_avance.propositions_correction() if c["cle"] == "bouton_continuer"][0]
    assert c["proposition"] == 'android=new UiSelector().resourceId("continuer_virement")' and c["fiabilite_proposee"] == "Stable"


def test_un_testtag_renomme_par_les_developpeurs_reste_le_meme_element(carte):
    """L'ancien identifiant disparaît, un autre le remplace (« continuer_virement » devient « Sp_continuer_btn ») : même
    écran, mêmes clés, l'ancien identifiant ne reste pas en secours."""
    a = carte.observer(_els("android_compose_testtag"), "android", build="1.1")
    cles = set(carte.ecran(a["id"])["elements"])
    b = carte.observer(_els("android_compose_testtag_renomme"), "android", build="1.2")
    assert b["id"] == a["id"] and len(carte.ecrans()) == 1
    e = carte.ecran(a["id"])
    assert set(e["elements"]) == cles
    locs = e["elements"]["bouton_continuer_virement"]["locators"]["android"]
    assert locs[0] == 'android=new UiSelector().resourceId("Sp_continuer_btn")' and not [l for l in locs if "continuer_virement" in l]
    assert [c["type"] for c in e["changements"]].count("identifiant_remplace") == 3 and not e.get("etats")
    assert carte.observer(_els("android_compose_testtag_renomme"), "android", build="1.2")["score"] == 1.0


def test_ecran_classique_reecrit_en_compose_avec_testtag(carte):
    """« id=com.exemple.banque:id/valider » devient le testTag « Sp_valider_btn » : aucun identifiant commun, l'écran
    est reconnu par ses libellés et son titre, le bouton par son libellé, le champ par le libellé qui le précède."""
    a = carte.observer(_els("android_classique"), "android", build="1.0")
    b = carte.observer(_els("android_classique_vers_compose"), "android", build="2.0")
    assert b["id"] == a["id"] and len(carte.ecrans()) == 1
    els = carte.ecran(a["id"])["elements"]
    assert els["bouton_valider"]["locators"]["android"][0] == 'android=new UiSelector().resourceId("Sp_valider_btn")'
    assert els["champ_montant"]["locators"]["android"][0] == 'android=new UiSelector().resourceId("Sp_montant_input")'
    assert not [l for k in ("bouton_valider", "champ_montant", "texte_titre") for l in els[k]["locators"]["android"] if l.startswith("id=com.")]
    # limite connue : un champ sans libellé propre (deux champs de suite) n'est pas rapproché, jamais deviné
    assert els["champ_motif"]["locators"]["android"] == ["id=com.exemple.banque:id/motif"] and "champ_sp_motif_input" in els
    autre = carte.observer(_els("android_compose"), "android")
    assert autre["nouveau"] and len(carte.ecrans()) == 2  # un autre écran reste un autre écran
