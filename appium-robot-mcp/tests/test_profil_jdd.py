"""Du profil de données de la Discovery au jeu de données des tests : mêmes valeurs, date relative recalculée à chaque run."""
from datetime import date, timedelta


def _referentiel():
    from atelier.discovery import donnees as d

    for cle, type_, extra in [("DEMO_NOM", "texte", {}), ("DEMO_EMAIL", "email", {}), ("DEMO_TELEPHONE", "telephone", {}),
                              ("DEMO_CABINET", "texte", {}), ("DEMO_VILLE", "texte", {}), ("DEMO_CRENEAU", "texte", {}),
                              ("DEMO_DATE", "date", {"source": {"type": "generateur", "generateur": "date", "decalage_jours": 7}}),
                              ("DEMO_JETON", "texte", {"sensibilite": "confidentielle"})]:
        d.enregistrer_variable(cle, {"type": type_, "description": cle, **extra})
    for cle, val in [("DEMO_NOM", "Testeur"), ("DEMO_EMAIL", "testeur@exemple.test"), ("DEMO_TELEPHONE", "+33600000000"),
                     ("DEMO_CABINET", "Cabinet fictif"), ("DEMO_VILLE", "Ville fictive"), ("DEMO_CRENEAU", "14:00")]:
        d.definir_valeur(cle, val, profil="DEMANDE_DEMO") if cle != "DEMO_VILLE" else d.definir_valeur(cle, val)
    d.enregistrer_profil("DEMANDE_DEMO", ["DEMO_NOM", "DEMO_EMAIL", "DEMO_TELEPHONE", "DEMO_CABINET", "DEMO_VILLE",
                                          "DEMO_CRENEAU", "DEMO_DATE", "DEMO_JETON"], "Demande de démo", "profil")
    return d


def test_profil_vers_jeu_de_donnees(projet):
    from atelier.execution import jdd

    d = _referentiel()
    r = d.profil_vers_jdd("DEMANDE_DEMO", "Recette")
    assert r["jeu"] == "DEMANDE_DEMO" and r["env"] == "recette" and r["fichier"] == "data/jdd/recette.yaml"
    assert r["dans_un_keyword"]["DEMO_EMAIL"] == "${JDD}[demo_email]"
    brut = jdd.lire("recette", "DEMANDE_DEMO")["donnees"]
    assert brut["demo_email"] == "testeur@exemple.test" and brut["demo_ville"] == "Ville fictive" and brut["demo_creneau"] == "14:00"
    assert brut["demo_date"] == "{{date:+7:%d/%m/%Y}}"                          # recalculée à chaque run
    assert brut["demo_jeton"] == "{{env:DEMO_JETON}}"                            # sensible : jamais écrite
    import os
    os.environ["DEMO_JETON"] = "x"
    try:
        res = jdd.resoudre("recette", ["DEMANDE_DEMO"])["jeux"]["DEMANDE_DEMO"]
    finally:
        del os.environ["DEMO_JETON"]
    assert res["demo_date"] == (date.today() + timedelta(days=7)).strftime("%d/%m/%Y")


def test_valeur_manquante_et_brouillon_relie(projet):
    import pytest

    d = _referentiel()
    d.enregistrer_variable("DEMO_PAYS", {"type": "texte"})
    p = d.profils_dict()["DEMANDE_DEMO"]
    d.enregistrer_profil("DEMANDE_DEMO", p["variables"] + ["DEMO_PAYS"], "", "profil")
    with pytest.raises(ValueError, match="DEMO_PAYS"):
        d.profil_vers_jdd("DEMANDE_DEMO", "recette")
    d.definir_valeur("DEMO_PAYS", "Pays fictif")
    d.profil_vers_jdd("DEMANDE_DEMO", "recette")
    from atelier.generation import parcours_bdd

    assert parcours_bdd.m_jdd_connu("demande_demo") and not parcours_bdd.m_jdd_connu("AUTRE")


def test_date_relative():
    from atelier.execution import jdd

    assert jdd.date_relative("+7") == (date.today() + timedelta(days=7)).strftime("%d/%m/%Y")
    assert jdd.date_relative("-1:%Y-%m-%d") == (date.today() - timedelta(days=1)).isoformat()
