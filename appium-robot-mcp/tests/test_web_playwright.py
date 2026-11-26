"""Web en réel : Playwright sur un site HTML local (tests/fixtures/sites/), servi en 127.0.0.1."""
from __future__ import annotations

import functools
import http.server
import os
import threading
from pathlib import Path

import pytest

from conftest import FIXTURES

pytest.importorskip("playwright")

if not os.environ.get("WEB_BROWSER_EXECUTABLE") and Path("/opt/pw-browsers/chromium").exists():
    os.environ["WEB_BROWSER_EXECUTABLE"] = "/opt/pw-browsers/chromium"


@pytest.fixture(scope="module")
def site():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(FIXTURES / "sites"))
    handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture
def session_web(projet, site):
    import server

    try:
        server.start_session(platform="web", url=f"{site}/accueil.html")
    except Exception as e:  # navigateur absent sur ce poste
        pytest.skip(f"Navigateur indisponible : {e}")
    yield server
    server.stop_session()


def test_elements_et_locators_browser_library(session_web):
    els = {e["key"]: e for e in session_web.get_screen_elements()["elements"]}
    assert els["lien_lien_comptes"]["locators"][0] == "data-testid=lien-comptes"
    assert els["lien_lienaide"]["locators"][0] == "id=lienAide"
    assert els["champ_montant"]["locators"][:2] == ["id=montant", 'css=input[name="montant"]']
    assert els["case_cgu"]["type"] == "case"
    assert session_web.check_locator("data-testid=lien-comptes")["nb_trouves"] == 1


def test_actions_et_carte_passive(session_web, site):
    s = session_web
    s.map_create_app("Site démo", ["web"], url=f"{site}/accueil.html")
    depart = s.where_am_i()
    s.tap("data-testid=lien-comptes")
    arrivee = s.where_am_i()
    assert arrivee["id"] != depart["id"]
    sorties = s.screen_info(depart["id"])["sorties"]
    assert [x["vers"] for x in sorties] == [arrivee["id"]]
    s.press_back()
    assert s.where_am_i()["id"] == depart["id"]
    assert s.goto_screen(arrivee["id"])["arrive"]


def test_exploration_bornee_par_un_perimetre(session_web, site):
    """Pendant une session bornée au module « Accueil » : l'exploration découvre « comptes » (le delta) et l'explore,
    arrive sur « aide » (déjà connu, hors périmètre), enregistre la transition, mais n'essaie rien depuis cet écran."""
    import app_map
    from atelier.discovery import sessions_discovery

    s = session_web
    s.map_create_app("Site périmètre", ["web"], url=f"{site}/accueil.html")
    accueil = s.where_am_i()["id"]
    s.open_url(f"{site}/aide.html")
    aide = s.where_am_i()["id"]
    app_map.renommer(accueil, "accueil", "Accueil")
    app_map.renommer(aide, "aide", "Aide")
    s.open_url(f"{site}/accueil.html")
    session = sessions_discovery.creer({"plateforme": "web", "perimetre_noeud": "module:Accueil"})
    sessions_discovery.demarrer(session["id"])
    try:
        bilan = s.explore(max_ecrans=6, profondeur=3, duree_max_s=120)
    finally:
        sessions_discovery.arreter(session["id"])
    assert bilan["arret"] == "terminé" and bilan["perimetre"] == "Accueil"
    assert bilan["nouveaux"] >= 1 and bilan["hors_perimetre"] >= 1            # « comptes » découvert ; arrivée sur « aide » comptée
    touches = [t for t in app_map.transitions() if t["action"].get("type") == "tap"]
    assert any(t["vers"] == aide for t in touches)                            # la sortie du périmètre est une connaissance : enregistrée
    assert not [t for t in touches if t["de"] == aide]                        # mais rien n'a été essayé depuis l'écran hors périmètre
    assert not (app_map.ecran(aide).get("essayes") or {}).get("web")
    comptes = next(e["id"] for e in app_map.ecrans() if e["id"] not in (accueil, aide))
    assert [t for t in touches if t["de"] == comptes]                         # l'écran découvert, lui, a été exploré


def test_exploration_respecte_les_invariants(session_web, site):
    s = session_web
    s.map_create_app("Site explo", ["web"], url=f"{site}/accueil.html")
    bilan = s.explore(max_ecrans=6, profondeur=3, duree_max_s=120)
    assert bilan["arret"] == "terminé"
    assert bilan["ignores_liste_rouge"] >= 1           # « Se déconnecter »
    assert bilan["transitions"] >= 2                   # comptes, aide
    s.open_url(f"{site}/accueil.html")
    from web_backend import WebBackend  # noqa: F401  (le backend est celui du MCP)
    stockage = s._webb()._run(lambda: s._webb().page.evaluate("Object.assign({}, localStorage)"))
    assert "saisie" not in stockage, "l'exploration a saisi du texte"
    assert "case" not in stockage, "l'exploration a coché une case"
    assert "deconnexion" not in stockage, "l'exploration a déclenché une action de la liste rouge"
    urls = [e for e in s.list_screens()]
    import app_map
    contextes = [p.get("contexte", "") for e in app_map.ecrans() for p in e["plateformes"].values()]
    assert not any("localhost:9" in c for c in contextes), "un lien externe a été cartographié"
    assert len(urls) >= 3


def test_texte_en_double_locator_borne_et_unique(session_web, site):
    """Même lien « Connexion » en en-tête et en pied de page : le premier locator désigne un seul élément."""
    session_web.open_url(f"{site}/doublon.html")
    liens = [e for e in session_web.get_screen_elements()["elements"] if e.get("libelle") == "Connexion"]
    assert len(liens) == 2
    premiers = sorted(e["locators"][0] for e in liens)
    assert premiers == ['css=footer a[href="/fr/login"]', 'css=nav a[href="/fr/login"]']  # zone la plus proche
    for loc in premiers:
        assert session_web.check_locator(loc)["nb_trouves"] == 1
    aide = next(e for e in session_web.get_screen_elements()["elements"] if e.get("libelle") == "Aide")
    assert 'text="Aide"' in aide["locators"]  # texte unique : inchangé
