"""Discovery iOS après une Discovery Android : les écrans et les clés métier sont retrouvés (pas de doublons), seuls
les locators iOS s'ajoutent ; un écran iOS différent reste un nouvel écran."""
import pytest


@pytest.fixture
def carte_vide(projet):
    from atelier.discovery import carte

    carte.creer_app("Banque Démo", ["android", "ios"], {"app_package": "com.exemple.banque"}, {"bundle_id": "fr.exemple.banque"})
    return carte


def _els(nom, plateforme):
    import server
    from conftest import lire_fixture

    return server._parse_elements(lire_fixture("hierarchies", f"{nom}.xml"), plateforme)


def test_ecran_ios_rapproche_de_l_ecran_android(carte_vide):
    c = carte_vide
    a = c.observer(_els("android_classique", "android"), "android")
    i = c.observer(_els("ios", "ios"), "ios")
    assert not i["nouveau"] and i["id"] == a["id"]                         # même écran : pas de doublon
    assert len(c.ecrans()) == 1
    e = c.ecran(a["id"])
    assert set(e["plateformes"]) == {"android", "ios"}
    assert any(ch["type"] == "rapprochement_plateforme" and ch["plateforme"] == "ios" for ch in e["changements"])
    els = e["elements"]
    # mêmes clés métier : le champ montant et le titre gardent la clé Android, avec leurs locators iOS en plus
    assert els["champ_montant"]["locators"]["ios"] == ["accessibility_id=amountField", 'nsp=label == "Montant"',
                                                       'chain=**/XCUIElementTypeTextField[`label == "Montant"`]']
    assert "ios" in els["texte_titre"]["locators"] and "ios" in els["bouton_valider"]["locators"]
    assert "ios" not in els["champ_motif"]["locators"]                       # absent de l'écran iOS : à relever


def test_ecran_ios_different_reste_un_nouvel_ecran(carte_vide):
    c = carte_vide
    c.observer(_els("android_classique", "android"), "android")
    autre = [{"key": "texte_mes_cartes", "type": "texte", "libelle": "Mes cartes", "locators": ["accessibility_id=Mes cartes"]},
             {"key": "bouton_opposition", "type": "bouton", "libelle": "Faire opposition", "locators": ["accessibility_id=Faire opposition"]},
             {"key": "bouton_valider", "type": "bouton", "libelle": "Valider", "locators": ['nsp=label == "Valider"']}]
    r = c.observer(autre, "ios")
    assert r["nouveau"] and len(c.ecrans()) == 2


def test_une_seconde_observation_ios_reconnait_par_sa_propre_empreinte(carte_vide):
    c = carte_vide
    a = c.observer(_els("android_classique", "android"), "android")
    c.observer(_els("ios", "ios"), "ios")
    r = c.observer(_els("ios", "ios"), "ios")
    assert r["id"] == a["id"] and not r["nouveau"]
    assert sum(ch["type"] == "rapprochement_plateforme" for ch in c.ecran(a["id"])["changements"]) == 1
