"""Environnements d'une application : la plateforme fait partie de l'environnement (un seul sélecteur dans le header) ;
l'assistant d'application choisit ses environnements (créés au besoin) et s'y rattache."""
from __future__ import annotations

import pytest


@pytest.fixture
def projet_vide(tmp_path, monkeypatch):
    from atelier.domain import projet

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    return tmp_path


def test_ajouter_cree_le_referentiel_et_rattacher(projet_vide):
    from atelier.intelligence import environnements as E, strategie

    assert strategie.charger() is None and E.lister() == []
    rec = E.ajouter({"nom": "recette", "plateforme": "android", "url": "", "jdd_env": "recette"})  # sans référentiel : il naît
    assert rec["plateforme"] == "Android" and rec["plateforme_id"] == "android" and rec["application"] == ""
    ios = E.ajouter({"nom": "recette", "plateforme": "iOS"})
    web = E.ajouter({"nom": "prod", "plateforme": "web", "url": "https://autre.exemple"}, application="autre")
    assert {e["id"] for e in E.rattacher("banque", [rec["id"], ios["id"]])} == {rec["id"], ios["id"]}
    assert next(e for e in E.lister() if e["id"] == web["id"])["application"] == "autre"  # celui d'une autre application ne bouge pas
    assert {e["id"] for e in E.rattacher("banque", [rec["id"]])} == {rec["id"]}  # retiré de la sélection : détaché
    assert next(e for e in E.lister() if e["id"] == ios["id"])["application"] == ""


def test_entrees_du_header(projet_vide):
    from atelier.intelligence import environnements as E

    # rien de déclaré : les noms connus (Xray, jeux de données) sur chaque plateforme de l'application
    l = E.pour_application("banque", "Banque", ["android", "ios"], ["recette"])
    assert [(e["libelle"], e["plateforme"], e["jdd"], e["declare"]) for e in l] == [
        ("recette · Android", "android", "recette", False), ("recette · iOS", "ios", "recette", False)]
    assert [e["libelle"] for e in E.pour_application("site", "Site", ["web"], ["prod"])] == ["prod"]  # une plateforme : le nom seul

    sans_plat = E.ajouter({"nom": "recette", "jdd_env": "jdd_recette"}, application="banque")  # ne fixe pas sa plateforme
    E.ajouter({"nom": "preprod", "plateforme": "Android", "url": "https://pp.exemple", "par_defaut": True}, application="banque")
    E.ajouter({"nom": "prod", "plateforme": "Web"}, application="site")  # autre application : absent
    l = E.pour_application("banque", "Banque", ["android", "ios"], ["recette"])
    assert [(e["libelle"], e["plateforme"], e["jdd"]) for e in l] == [
        ("recette · Android", "android", "jdd_recette"), ("recette · iOS", "ios", "jdd_recette"), ("preprod", "android", "preprod")]
    assert l[0]["id"] == f"{sans_plat['id']}:android" and l[2]["par_defaut"] and l[2]["url"] == "https://pp.exemple"
