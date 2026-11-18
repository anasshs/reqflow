"""Caractérisation du parsing des hiérarchies mobiles (Android classique, Compose sans testTag, iOS)."""
from __future__ import annotations

import pytest

from conftest import lire_fixture


def _parse(nom: str, plateforme: str) -> dict:
    import server

    return {e["key"]: e for e in server._parse_elements(lire_fixture("hierarchies", f"{nom}.xml"), plateforme)}


def test_android_classique_ids_en_premier():
    els = _parse("android_classique", "android")
    assert list(els) == ["texte_titre", "champ_montant", "champ_motif", "texte_l_operation_est_immediate",
                         "bouton_valider", "bouton_annuler"]
    assert els["champ_montant"]["locators"][0] == "id=com.exemple.banque:id/montant"  # l'ancre du libellé suit, en secours
    assert els["bouton_valider"]["locators"] == ["id=com.exemple.banque:id/valider",
                                                 "accessibility_id=Valider le virement",
                                                 "xpath=//*[@text='Valider']"]
    assert els["bouton_valider"]["rect"] == [40, 2000, 1000, 120]
    assert all(e["locator_unique"] for e in els.values())


def test_android_element_masque_ignore():
    assert not any("cach" in k for k in _parse("android_classique", "android"))


def test_android_apostrophe_xpath_sure():
    el = _parse("android_classique", "android")["texte_l_operation_est_immediate"]
    assert el["locators"][1] == "xpath=//*[@text=\"L'opération est immédiate\"]"


def test_android_sans_id_uiselector_texte():
    el = _parse("android_classique", "android")["bouton_annuler"]
    assert el["locators"][0] == 'android=new UiSelector().text("Annuler")'


def test_compose_champ_relatif_au_libelle():
    els = _parse("android_compose", "android")
    champ = els["champ_montant"]
    assert champ["type"] == "champ"
    assert champ["locators"][0] == "xpath=//*[@text='Montant']/following::android.widget.EditText[1]"


def test_compose_bouton_porte_par_enfant():
    els = _parse("android_compose", "android")
    bouton = els["bouton_continuer"]
    assert bouton["locators"] == ['android=new UiSelector().text("Continuer")',
                                  "xpath=//*[@text='Continuer']/ancestor-or-self::*[@clickable='true'][1]"]
    # le texte enfant porte le même locator principal : signalé comme ambigu
    assert bouton["locator_unique"] is False
    assert els["texte_continuer"]["locator_unique"] is False


def test_compose_texte_dynamique_sans_uiselector():
    el = _parse("android_compose", "android")["texte_solde_1_250_00_dh"]
    assert el["locators"] == ["xpath=//*[@text='Solde : 1 250,00 DH']"]


def test_ios_locators():
    els = _parse("ios", "ios")
    assert list(els) == ["texte_virement", "champ_amountfield", "bouton_valider"]
    assert els["champ_amountfield"]["locators"] == ["accessibility_id=amountField", 'nsp=label == "Montant"',
                                                   'chain=**/XCUIElementTypeTextField[`label == "Montant"`]']
    assert els["bouton_valider"]["locators"][0] == 'nsp=label == "Valider"'
    assert els["bouton_valider"]["rect"] == [16.0, 760.0, 358.0, 50.0]


@pytest.mark.parametrize("valeur,attendu", [
    ("simple", "'simple'"),
    ("l'été", '"l\'été"'),
    ("l'\"x\"", "concat('l', \"'\", '\"x\"')"),
])
def test_quote_xpath(valeur, attendu):
    import server

    assert server._xq(valeur) == attendu


def test_by_strategies():
    pytest.importorskip("appium")
    import server
    from appium.webdriver.common.appiumby import AppiumBy

    assert server._by("id=a:id/b") == (AppiumBy.ID, "a:id/b")
    assert server._by("//x") == (AppiumBy.XPATH, "//x")
    assert server._by('nsp=label == "V"') == (AppiumBy.IOS_PREDICATE, 'label == "V"')
    assert server._by("brut") == (AppiumBy.ID, "brut")


def test_compose_avec_testtag_locator_sans_reglage_appium():
    """Un testTag est lu sans « package:id/ » : le locator id= d'Appium le compléterait avec le package et ne le
    trouverait pas ; le sélecteur UiAutomator marche sans réglage. Le libellé et les locators de secours restent."""
    els = _parse("android_compose_testtag", "android")
    champ = els["champ_montant"]  # tag nommé comme la clé métier : exactement la même clé qu'avant
    assert champ["locators"] == ['android=new UiSelector().resourceId("champ_montant")',
                                 "xpath=//*[@text='Montant']/following::android.widget.EditText[1]"]
    bouton = els["bouton_continuer_virement"]
    assert bouton["libelle"] == "Continuer" and bouton["locator_unique"] is True  # plus d'ambiguïté avec le texte enfant
    assert bouton["locators"][0] == 'android=new UiSelector().resourceId("continuer_virement")'
    classiques = [e["locators"][0] for e in _parse("android_classique", "android").values() if ":id/" in e["locators"][0]]
    assert classiques and all(l.startswith("id=") for l in classiques)  # un resource-id complet garde le locator id=


def test_champ_identifie_garde_l_ancre_du_libelle_qui_precede():
    els = _parse("android_classique", "android")
    assert els["champ_montant"]["locators"] == ["id=com.exemple.banque:id/montant", "xpath=//*[@text='Virement']/following::android.widget.EditText[1]"]
    assert els["champ_motif"]["locators"] == ["id=com.exemple.banque:id/motif"]  # deux champs de suite : pas d'ancre sûre
