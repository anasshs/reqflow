"""Console Cursor : chaque appel d'outil MCP décrit en français, avec les règles .mdc du projet qui l'encadrent ;
annonce de l'agent (intention, modèle) par l'outil agent_annoncer, qui n'écrit rien."""
import pytest


@pytest.fixture
def projet(tmp_path, monkeypatch):
    from atelier.domain import projet as p

    monkeypatch.setattr(p, "PROJECT_DIR", tmp_path)
    return tmp_path


def test_appels_decrits_en_francais():
    from atelier.adapters import facade
    from atelier.domain import activite_agent as a

    docs = {f.__name__: f.__doc__ or "" for f in facade.OUTILS}
    assert a.decrire("testabilite_deposer_proposition", {"cle": "DEMO-1"}) == \
        "Cursor dépose son analyse et ses cas de test proposés pour l'US « DEMO-1 »"
    assert a.decrire("type_text", {"locator": "id=montant", "text": "•••"}) == "Cursor saisit une valeur dans « id=montant »"
    assert a.decrire("type_text", {"locator": "id=montant", "element": "Montant"}) == "Cursor saisit une valeur dans « Montant »"
    assert a.decrire("type_text", {}) == "Cursor saisit une valeur"
    # sans phrase dédiée : tirée de la documentation de l'outil (verbe conjugué, ou « consulte » pour un nom)
    assert a.decrire("get_page_source", {}, docs["get_page_source"]).startswith("Cursor consulte : arbre brut")
    assert a.decrire("coverage_report", {}, docs["coverage_report"]).startswith("Cursor consulte : couverture du patrimoine Xray")
    assert a.decrire("outil_inconnu") == "Cursor appelle l'outil outil_inconnu"
    for f in facade.OUTILS:  # chaque outil a une description lisible, jamais vide
        assert a.decrire(f.__name__, {}, f.__doc__ or "").startswith("Cursor ")


def test_regles_qui_encadrent_chaque_outil(projet):
    from atelier.adapters import facade
    from atelier.integrations import regles_cursor

    r = regles_cursor.regles_par_outil([f.__name__ for f in facade.OUTILS])
    assert "atelier-test-design.mdc" in r["outils"]["testabilite_us_a_traiter"]
    assert "atelier-test-design.mdc" in r["outils"]["test_design_doublons"]
    assert set(r["toujours"]) >= {"atelier-global.mdc", "atelier-security.mdc", "atelier-mcp-usage.mdc"}
    assert all("atelier-mcp-usage.mdc" not in v for v in r["outils"].values())  # les règles toujours appliquées sont à part
    assert not (projet / "atelier_regles").exists()  # lecture seule : aucune version créée dans le projet


def test_agent_annoncer_publie_une_annonce_sans_rien_ecrire(projet):
    from atelier.adapters import facade
    from atelier.domain import evenements

    recus = []
    desabonner = evenements.abonner(recus.append, {"mcp_annonce"})
    try:
        r = facade.agent_annoncer("  J'analyse   les US de la squad DRE  ", modele="modèle-x", etape="Test Design",
                                  regles=["atelier-test-design.mdc"])
        assert r["ok"] and recus == [{"type": "mcp_annonce", "intention": "J'analyse les US de la squad DRE", "modele": "modèle-x",
                                      "etape": "Test Design", "regles": ["atelier-test-design.mdc"]}]
        assert facade.agent_annoncer("   ")["ok"] is False and len(recus) == 1
    finally:
        desabonner()
    assert not any(projet.iterdir())  # aucune écriture dans le projet


def test_agent_reel_etape_du_cycle_et_jalons():
    """La console dit quel agent agit (Claude Code, Cursor), à quelle étape du cycle (du parcours au TNR), et les
    jalons qui méritent une notification ; un appel ordinaire n'en a pas."""
    from atelier.domain import activite_agent as a

    assert a.nom_agent("claude-code 1.0") == "Claude Code" and a.nom_agent("cursor 1.2") == "Cursor" and a.nom_agent("") == "L'agent"
    assert a.decrire("press_back", {}, agent="Claude Code") == "Claude Code revient à l'écran précédent"
    assert a.decrire("tap", {"locator": "id=x", "element": "Identifiant oublié"}, agent="Claude Code") == "Claude Code touche « Identifiant oublié »"
    assert [a.etape_outil(n) for n in ("discovery_parcours_cadre", "tap", "discovery_parcours_vers_bdd", "run_robot", "tnr_demander_publication",
                                       "knowledge_graph")] == ["cadrer", "explorer", "scenariser", "automatiser", "publier", ""]
    assert a.jalon({"nom": "discovery_demarrer", "etat": "debut", "args": {"parcours": "PU-x"}}) == "Discovery lancée « PU-x »"
    assert a.jalon({"nom": "run_robot", "etat": "fin", "resultat": "statut : 2 PASS"}) == "Tests terminés · statut : 2 PASS"
    assert a.jalon({"nom": "tap", "etat": "erreur", "message": "élément introuvable"}) == "Erreur sur tap : élément introuvable"
    assert a.jalon({"nom": "tap", "etat": "fin"}) == "" and a.jalon({"nom": "where_am_i", "etat": "fin"}) == ""
    assert a.famille("discovery_proposer") == "ecriture" and a.famille("run_tests") == "execution"


def test_libelle_de_l_element_vise(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.domain import activite_agent as a, projet as p

    monkeypatch.setattr(p, "PROJECT_DIR", tmp_path)
    carte.creer_app("Banque Web", ["android"], type_="mobile")
    carte.observer([{"key": "lien_oubli", "type": "lien", "libelle": "Identifiant oublié", "locators": ['android=new UiSelector().resourceId("lien_oubli")']},
                    {"key": "bouton_tech", "type": "bouton", "libelle": "bouton_tech_id", "locators": ["id=app:id/tech"]}], "android", "")
    assert a.libelle_element('xpath=//*[@resource-id="lien_oubli"]') == "Identifiant oublié"     # même élément, autre syntaxe
    assert a.libelle_element("id=app:id/tech") == ""                                              # identifiant technique : pas un libellé
    assert a.libelle_element("") == ""
