"""Politique de robustesse des locators (web, Android natif et Compose, iOS) et bornage des libellés répétés."""
from atelier.generation import robustesse_locators as r


def test_niveaux_par_plateforme():
    n = lambda l, p="": r.evaluer(l, p)["niveau"]  # noqa: E731
    assert n("data-testid=valider") == n("id=valider") == n("id=com.app:id/valider") == "Stable"
    assert n('android=new UiSelector().resourceId("champ_montant")') == "Stable"   # testTag Compose
    assert n("accessibility_id=Valider", "android") == "Reliable"                     # content-desc : suit la langue
    assert n("accessibility_id=valider", "ios") == "Stable"
    assert n('role=link[name="Connexion"]') == n('css=input[name="montant"]') == n('css=nav a[href="/fr/login"]') == "Reliable"
    assert n('android=new UiSelector().text("Continuer")') == "Reliable"
    assert n('text="Connexion"') == n("xpath=//*[@text='OK']") == n("//android.widget.Button[2]") == "Fragile"
    assert n("id=mui-12345") == n("css=body > div:nth-of-type(2)") == n('css=li:nth-child(3)') == "Fragile"
    assert r.evaluer('id=valider', unique=False)["niveau"] == "Fragile"               # ambigu : jamais livrable seul
    assert "testTag" in r.evaluer("//android.view.View[3]", "android")["conseil"]


def test_classer_et_regles():
    assert r.classer(['text="Connexion"', 'css=nav a[href="/x"]', "data-testid=a"]) == ["data-testid=a", 'css=nav a[href="/x"]', 'text="Connexion"']
    g = r.regles("android")
    assert set(g) == {"android", "commun"} and any("Compose" in x for x in g["android"]["ordre"])


def test_outil_mcp_locator_robustesse():
    from atelier.adapters import facade

    x = facade.locator_robustesse(['text="Connexion"', "data-testid=connexion"], "web")
    assert x["classes"][0] == "data-testid=connexion" and x["evaluations"][0]["niveau"] == "Fragile" and "web" in x["regles"]


def test_android_libelle_repete_borne_au_conteneur():
    from atelier.discovery import parsing

    xml = """<hierarchy><android.widget.FrameLayout>
      <android.view.View resource-id="carte_courant"><android.widget.TextView text="Voir le détail" clickable="true"/></android.view.View>
      <android.view.View resource-id="carte_livret"><android.widget.TextView text="Voir le détail" clickable="true"/></android.view.View>
      <android.widget.Button resource-id="com.app:id/valider" text="Valider"/></android.widget.FrameLayout></hierarchy>"""
    els = {e["key"]: e for e in parsing.parse_elements(xml, "android")}
    a, b = els["texte_voir_le_detail"], els["texte_voir_le_detail_2"]
    assert a["locators"][0] == "xpath=//*[@resource-id='carte_courant']//*[@text='Voir le détail']" and a["locator_unique"]
    assert b["locators"][0].startswith("xpath=//*[@resource-id='carte_livret']") and len(b["locators"]) >= 2  # l'ancien en secours
    assert els["bouton_valider"]["locators"][0] == "id=com.app:id/valider"
    assert not any(k.startswith("_") for e in els.values() for k in e)


def test_correction_proposee_depuis_un_locator_ambigu_a_l_execution(projet):
    """Run en échec « strict mode violation » : la correction est proposée depuis la suggestion de Playwright."""
    from atelier.generation import studio_avance

    (projet / "resources" / "locators").mkdir(parents=True)
    (projet / "resources" / "locators" / "accueil.resource").write_text(
        '*** Variables ***\n&{LOC_ACCUEIL_WEB}    lien_connexion=text="Connexion"    titre=data-testid=titre\n', "utf-8")
    run = projet / "results" / "runs" / "RUN-20261121-184421"
    run.mkdir(parents=True)
    msg = ("Error: locator.waitFor: Error: strict mode violation: locator('text=\"Connexion\"') resolved to 2 elements: "
           "1) <a href=\"/fr/login\">Connexion</a> aka getByRole('banner').getByRole('link', { name: 'Connexion' }) "
           "2) <a href=\"/fr/login\">Connexion</a> aka getByRole('contentinfo').getByRole('link', { name: 'Connexion' }) Call log: x")
    import html
    (run / "output.xml").write_text(f"<robot><msg>{html.escape(msg)}</msg></robot>", "utf-8")
    p = {x["cle"]: x for x in studio_avance.propositions_correction()}
    assert p["lien_connexion"]["proposition"] == 'role=banner >> role=link[name="Connexion"]'
    assert "ambigu" in p["lien_connexion"]["source"] and p["lien_connexion"]["fiabilite_proposee"] == "Reliable"
    assert "titre" not in p
