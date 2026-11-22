"""Un projet à plusieurs applications : l'analyse comportementale ne les mélange pas ; une adresse sans protocole s'ouvre."""
from __future__ import annotations

import pytest


def test_adresse_sans_protocole():
    from atelier.integrations.playwright import url_complete as u

    assert u("maw3idgo.com") == "https://maw3idgo.com"          # « Cannot navigate to invalid URL » sinon
    assert u("www.klindoc.com/fr") == "https://www.klindoc.com/fr"
    assert u("staging.app.io:8443/login") == "https://staging.app.io:8443/login"
    assert u("localhost:8765/x") == "http://localhost:8765/x"
    for gardee in ("https://a.b", "http://a.b", "file:///c:/x.html", "about:blank", "/fr/docs", ""):
        assert u(gardee) == gardee


@pytest.fixture
def deux_applications(monkeypatch):
    from atelier.discovery import carte
    from atelier.intelligence import mbt

    ecrans = {"klindoc": {"ecran:accueil", "ecran:tarifs"}, "maw3idgo": {"ecran:e_1", "ecran:e_2"}}
    parcours = {"klindoc": {"PU-pied", "parcours:pied"}, "maw3idgo": {"PU-login", "parcours:login"}}
    monkeypatch.setattr(carte, "apps", lambda: [{"slug": "klindoc"}, {"slug": "maw3idgo"}])
    monkeypatch.setattr(mbt, "_ecrans_app", lambda slug="": ecrans[slug or "maw3idgo"])
    monkeypatch.setattr(mbt, "_parcours_app", lambda slug="": parcours[slug or "maw3idgo"])
    monkeypatch.setattr(mbt, "_app_courante", lambda: ("maw3idgo", "Maw3id Go"))
    return mbt


def test_application_d_un_modele(deux_applications):
    mbt = deux_applications
    # ses écrans disent son application, même si le modèle porte l'autre (constat du 2026-11-22)
    assert mbt.application_du_modele({"application": "maw3idgo", "etats": {"E-1": {"ecran": "ecran:accueil"}}}) == "klindoc"
    # vidé, sans écran : le parcours qu'il modélise
    assert mbt.application_du_modele({"application": "maw3idgo", "etats": {}, "perimetre": {"type": "parcours", "id": "parcours:pied"}}) == "klindoc"
    # ni écran ni parcours connu : l'application qu'il porte
    assert mbt.application_du_modele({"application": "Maw3id Go", "etats": {}, "perimetre": {"type": "module", "id": "module:login"}}) == "maw3idgo"


def test_modeles_et_reconstruction_de_l_application_active(deux_applications, monkeypatch):
    from atelier.domain import comportement as cm

    mbt = deux_applications
    modeles = {"parcours-pied": {"id": "parcours-pied", "application": "maw3idgo", "perimetre": {"type": "parcours", "id": "parcours:pied"},
                                 "etats": {"E-1": {"ecran": "ecran:accueil"}}},
               "module-login": {"id": "module-login", "application": "maw3idgo", "perimetre": {"type": "module", "id": "module:login"},
                                "etats": {"E-1": {"ecran": "ecran:e_1"}}}}
    monkeypatch.setattr(cm, "lister", lambda: [{"id": k, "nom": k, "perimetre": v["perimetre"]} for k, v in modeles.items()])
    monkeypatch.setattr(cm, "charger", lambda mid: modeles.get(mid))
    assert [m["id"] for m in mbt.modeles()] == ["module-login"]   # le modèle de klindoc n'apparaît pas quand maw3idgo est active

    class G:
        noeuds = {"parcours:pied": type("N", (), {"libelle": "Pied", "type": "parcours", "proprietes": {}})()}
    with pytest.raises(ValueError, match="appartient à l'application « klindoc »"):
        mbt.construire("parcours", "parcours:pied", G())          # reconstruit depuis maw3idgo, il aurait été vidé
