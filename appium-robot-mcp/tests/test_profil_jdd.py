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


def test_env_lu_dans_le_referentiel_discovery_au_run(projet, monkeypatch):
    """{{env:CLE}} sans variable d'environnement : la valeur vient de Discovery › Données (secret du coffre ou valeur
    réglée), sans jamais être écrite dans data/jdd."""
    from atelier.discovery import donnees as d
    from atelier.domain import coffre
    from atelier.execution import jdd

    d.enregistrer_variable("DEMO_LOGIN", {"type": "texte", "description": "identifiant fictif"})
    d.enregistrer_variable("DEMO_MDP", {"type": "texte", "sensibilite": "secrète"})
    monkeypatch.setattr(coffre, "disponible", lambda: False)  # pas de coffre en test : secret gardé en mémoire
    d.definir_valeur("DEMO_LOGIN", "U000001")
    d.definir_valeur("DEMO_MDP", "mdp-de-test", env="recette")
    d.enregistrer_profil("CONNEXION_DEMO", ["DEMO_LOGIN", "DEMO_MDP"], "Connexion fictive", "profil")
    d.profil_vers_jdd("CONNEXION_DEMO", "recette")
    brut = jdd.lire("recette", "CONNEXION_DEMO")["donnees"]
    assert brut["demo_mdp"] == "{{env:DEMO_MDP}}"                                 # jamais écrit
    monkeypatch.delenv("DEMO_MDP", raising=False)
    res = jdd.resoudre("recette", ["CONNEXION_DEMO"])["jeux"]["CONNEXION_DEMO"]
    assert res == {"demo_login": "U000001", "demo_mdp": "mdp-de-test"}
    monkeypatch.setenv("DEMO_MDP", "depuis-environnement")                         # l'environnement reste prioritaire
    assert jdd.resoudre("recette", ["CONNEXION_DEMO"])["jeux"]["CONNEXION_DEMO"]["demo_mdp"] == "depuis-environnement"
    assert jdd.valeur_env("INCONNUE_DU_REFERENTIEL", "recette") is None


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


def test_secret_force_profil_utilise_au_run_et_comptes_masques(projet, monkeypatch):
    """Une variable « mot de passe » est toujours secrète ; un jeu tiré d'un profil rejoue la valeur du profil ;
    securiser_secrets déplace au coffre les valeurs en clair ; map_apps ne renvoie jamais les comptes."""
    from atelier.discovery import carte, carte_outils
    from atelier.discovery import donnees as d
    from atelier.domain import coffre
    from atelier.execution import jdd

    memoire = {}
    monkeypatch.setattr(coffre, "disponible", lambda: True)
    monkeypatch.setattr(coffre, "ecrire", lambda n, v: memoire.__setitem__(n, v))
    monkeypatch.setattr(coffre, "lire", lambda n: memoire.get(n))
    assert d.enregistrer_variable("CLIENT_PASSWORD", {"type": "texte"})["sensibilite"] == "secrète"
    d.enregistrer_variable("CLIENT_LOGIN", {"type": "texte"})
    d.definir_valeur("CLIENT_LOGIN", "U-DEFAUT")
    d.definir_valeur("CLIENT_LOGIN", "U-PROFIL", profil="CLIENT_B")
    d.definir_valeur("CLIENT_PASSWORD", "mdp-b", profil="CLIENT_B")
    d.enregistrer_profil("CLIENT_B", ["CLIENT_LOGIN", "CLIENT_PASSWORD"], "client B", "profil")
    d.profil_vers_jdd("CLIENT_B", "recette")
    assert jdd.lire("recette", "CLIENT_B")["donnees"]["client_login"] == "U-PROFIL"
    monkeypatch.delenv("CLIENT_PASSWORD", raising=False)
    assert jdd.resoudre("recette", ["CLIENT_B"])["jeux"]["CLIENT_B"]["client_password"] == "mdp-b"   # valeur du profil

    # ancienne variable « normale » avec un mot de passe en clair : signalée puis déplacée au coffre
    tout = d._lire("variables")
    tout["OLD_MDP"] = {"nom": "Ancien mot de passe", "type": "texte", "sensibilite": "normale", "source": {"type": "manuelle"}}
    d._ecrire("variables", tout)
    vals = d._lire("valeurs")
    vals["OLD_MDP"] = {"defaut": "en-clair"}
    d._ecrire("valeurs", vals)
    assert [x["cle"] for x in d.secrets_en_clair()] == ["OLD_MDP"]
    assert d.securiser_secrets()["securisees"] == ["OLD_MDP"]
    assert "OLD_MDP" not in d._lire("valeurs") and d.variable("OLD_MDP")["sensibilite"] == "secrète"
    assert d.valeur_pour_run("OLD_MDP", "recette") == "en-clair" and d.secrets_en_clair() == []

    carte.creer_app("Appli", ["android"])
    carte.maj_app(comptes=["${IDENTIFIANT} U1", "${MDP} secret"])
    a = carte_outils.map_apps()["applications"][0]
    assert "secret" not in str(a["comptes"]) and "masquée" in a["comptes"]
