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
    assert a.decrire("type_text", {"locator": "id=montant", "text": "•••"}) == "Cursor saisit du texte dans « id=montant »"
    assert a.decrire("type_text", {}) == "Cursor saisit du texte"
    # sans phrase dédiée : tirée de la documentation de l'outil (verbe conjugué, ou « consulte » pour un nom)
    assert a.decrire("stop_session", {}, docs["stop_session"]).startswith("Cursor ferme la session courante")
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
