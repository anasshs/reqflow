"""Projets : un repository de tests + son projet Xray / Jira ; bascule sûre, journalisée, sans secret stocké."""
import json
import os

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    from atelier.domain import projet, projets

    a, b = tmp_path / "repo_a", tmp_path / "repo_b"
    a.mkdir()
    b.mkdir()
    monkeypatch.setenv("ATELIER_PROJETS", str(tmp_path / "conf" / "projets.json"))
    monkeypatch.setattr(projet, "PROJECT_DIR", a.resolve())
    monkeypatch.setattr(projet, "SNAP_DIR", a / ".mcp_snapshots")
    for v in projets.VARIABLES + projets.SECRETS + ("ROBOT_PROJECT_DIR", "XRAY_CLIENT_ID_B"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(projets, "_ORIGINE", {**{v: None for v in projets.VARIABLES + projets.SECRETS}, "ROBOT_PROJECT_DIR": None,
                                              "XRAY_CLIENT_ID": "id-global"})
    return a, b, tmp_path


def test_declaration_sans_secret_et_bascule(env, monkeypatch):
    from atelier.domain import projet, projets

    a, b, tmp = env
    projets.enregistrer({"nom": "Banque A", "dossier": str(a), "xray_projet": "tam"})
    projets.enregistrer({"nom": "Banque B", "dossier": str(b), "xray_projet": "BQB", "jira_url": "https://exemple.atlassian.net",
                         "jira_email": "qa@exemple.fr", "secrets": {"XRAY_CLIENT_ID": "XRAY_CLIENT_ID_B"}})
    with pytest.raises(ValueError, match="NOM"):  # une valeur de secret collée par erreur est refusée
        projets.enregistrer({"nom": "C", "dossier": str(b), "secrets": {"XRAY_CLIENT_SECRET": "a1b2-c3d4.e5/f6"}})
    with pytest.raises(ValueError, match="déjà déclaré"):
        projets.enregistrer({"nom": "Doublon", "dossier": str(a)})
    assert projets.actif_id() == "banque-a" and projets.cle_xray() == "TAM"
    monkeypatch.setenv("XRAY_CLIENT_ID_B", "id-projet-b")
    with pytest.raises(PermissionError, match="run"):
        projets.activer("banque-b", occupe="run RUN-1 en cours")
    assert projet.PROJECT_DIR == a.resolve()
    projets.activer("banque-b")
    assert projet.PROJECT_DIR == b.resolve() and os.environ["ROBOT_PROJECT_DIR"] == str(b.resolve())
    assert os.environ["JIRA_BASE_URL"] == "https://exemple.atlassian.net" and os.environ["XRAY_CLIENT_ID"] == "id-projet-b"
    assert projets.cle_xray() == "BQB"
    projets.activer("banque-a")  # retour : connexions globales d'origine
    assert os.environ["XRAY_CLIENT_ID"] == "id-global" and "JIRA_BASE_URL" not in os.environ
    brut = (tmp / "conf" / "projets.json").read_text("utf-8")
    assert "id-projet-b" not in brut and "XRAY_CLIENT_ID_B" in brut  # nom de variable seulement
    j = projets.journal()
    assert [x["op"] for x in j][:2] == ["bascule", "bascule"] and j[0]["vers"] == "banque-a"
    with pytest.raises(PermissionError):
        projets.supprimer("banque-a")  # projet actif
    projets.supprimer("banque-b")
    assert b.exists()  # le repository n'est jamais touché


def test_donnees_separees_par_projet(env):
    """La stratégie vit dans le repository : deux projets, deux stratégies."""
    from atelier.domain import projets
    from atelier.intelligence import strategie

    a, b, _ = env
    projets.enregistrer({"nom": "A", "dossier": str(a)})
    projets.enregistrer({"nom": "B", "dossier": str(b)})
    strategie.creer("Stratégie A", "App A")
    projets.activer("b")
    assert strategie.charger() is None
    strategie.creer("Stratégie B", "App B")
    projets.activer("a")
    assert strategie.charger()["infos"]["nom"] == "Stratégie A"
    assert (a / "strategie" / "strategie.yaml").exists() and (b / "strategie" / "strategie.yaml").exists()


def test_cle_par_defaut_publication_et_anomalie(env):
    from atelier.domain import projets
    from atelier.execution import echecs

    a, _, _ = env
    projets.enregistrer({"nom": "A", "dossier": str(a), "xray_projet": "TAM"})

    class FauxJira:
        def rechercher(self, jql, champs, limite):
            self.jql = jql
            return []

    j = FauxJira()
    import pytest as _p
    mp = _p.MonkeyPatch()
    mp.setattr(echecs, "_evenement", lambda eid: {"message": "Element bouton_connexion introuvable apres attente", "cle_xray": "TAM-735"})
    assert echecs.doublons_jira("E1", "", jira=j) == [] and 'project = "TAM"' in j.jql
    assert json.loads(json.dumps(projets.lister()))["actif"] == "a"
    mp.undo()


def test_secrets_saisis_dans_l_app_memoire_seule(env, monkeypatch):
    from atelier.domain import projets

    a, b, tmp = env
    monkeypatch.setattr(projets, "_ORIGINE_ENV", {})
    monkeypatch.setattr(projets, "_SAISIS", set())
    for v in ("XRAY_CLIENT_ID_TAM", "XRAY_CLIENT_SECRET_TAM"):
        monkeypatch.delenv(v, raising=False)  # restaurés (absents) après le test
    projets.enregistrer({"nom": "A", "dossier": str(a), "xray_projet": "TAM",
                         "secrets": {"XRAY_CLIENT_ID": "XRAY_CLIENT_ID_TAM", "XRAY_CLIENT_SECRET": "XRAY_CLIENT_SECRET_TAM"}})
    projets.enregistrer({"nom": "B", "dossier": str(b)})
    projets.enregistrer_general({"jira_url": "https://exemple.atlassian.net", "jira_email": "qa@exemple.fr"})
    assert os.environ["JIRA_BASE_URL"] == "https://exemple.atlassian.net"
    with pytest.raises(ValueError, match="non attendue"):
        projets.saisir_secret("PATH", "/tmp")  # seules les variables attendues sont modifiables
    projets.saisir_secret("XRAY_CLIENT_ID_TAM", ' "id-tam-123" ')
    projets.saisir_secret("XRAY_CLIENT_SECRET_TAM", "secret-tam-456")
    projets.saisir_secret("JIRA_API_TOKEN", "jeton-jira-789")
    assert os.environ["XRAY_CLIENT_ID"] == "id-tam-123" and os.environ["JIRA_API_TOKEN"] == "jeton-jira-789"
    c = projets.connexions()
    assert all(s["present"] for s in c["secrets"] if s["nom"] in ("XRAY_CLIENT_ID_TAM", "JIRA_API_TOKEN"))
    projets.activer("b")  # autre projet : Xray global (aucun), Jira général conservé
    assert os.environ["XRAY_CLIENT_ID"] == "id-global" and os.environ["JIRA_API_TOKEN"] == "jeton-jira-789"
    assert os.environ["JIRA_BASE_URL"] == "https://exemple.atlassian.net"
    projets.activer("a")
    assert os.environ["XRAY_CLIENT_SECRET"] == "secret-tam-456"
    disque = "".join(f.read_text("utf-8") for f in (tmp / "conf").iterdir())
    for valeur in ("id-tam-123", "secret-tam-456", "jeton-jira-789"):
        assert valeur not in disque and valeur not in json.dumps(c)  # ni sur disque, ni dans une réponse
    projets.effacer_secret("JIRA_API_TOKEN")
    assert "JIRA_API_TOKEN" not in os.environ


class FauxCoffre:
    """Backend keyring en mémoire (le vrai coffre du poste n'est jamais touché par les tests)."""

    def __init__(self):
        import keyring.backend

        class K(keyring.backend.KeyringBackend):
            priority = 1
            valeurs: dict = {}

            def get_password(self, service, nom):
                return self.valeurs.get((service, nom))

            def set_password(self, service, nom, valeur):
                self.valeurs[(service, nom)] = valeur

            def delete_password(self, service, nom):
                import keyring.errors

                if (service, nom) not in self.valeurs:
                    raise keyring.errors.PasswordDeleteError(nom)
                del self.valeurs[(service, nom)]

        self.k = K()


def test_coffre_du_systeme(env, monkeypatch):
    pytest.importorskip("keyring")
    import keyring

    from atelier.domain import coffre, projets

    a, _, tmp = env
    faux = FauxCoffre()
    precedent = keyring.get_keyring()
    keyring.set_keyring(faux.k)
    monkeypatch.delenv("ATELIER_COFFRE", raising=False)
    monkeypatch.setattr(projets, "_ORIGINE_ENV", {})
    monkeypatch.setattr(projets, "_ENV_POSTE", set())
    monkeypatch.setattr(projets, "_SAISIS", set())
    monkeypatch.delenv("XRAY_CLIENT_SECRET_TAM", raising=False)
    try:
        projets.enregistrer({"nom": "A", "dossier": str(a), "xray_projet": "TAM", "secrets": {"XRAY_CLIENT_SECRET": "XRAY_CLIENT_SECRET_TAM"}})
        assert coffre.disponible()
        r = projets.saisir_secret("XRAY_CLIENT_SECRET_TAM", "secret-coffre-1")
        assert r["mode"] == "coffre" and faux.k.valeurs[(coffre.SERVICE, "XRAY_CLIENT_SECRET_TAM")] == "secret-coffre-1"
        assert next(s for s in r["secrets"] if s["nom"] == "XRAY_CLIENT_SECRET_TAM")["dans_le_coffre"]
        assert "secret-coffre-1" not in json.dumps(r) and "secret-coffre-1" not in "".join(f.read_text("utf-8") for f in (tmp / "conf").iterdir())
        # « redémarrage » : l'environnement est vide, le coffre recharge le secret
        os.environ.pop("XRAY_CLIENT_SECRET_TAM")
        os.environ.pop("XRAY_CLIENT_SECRET", None)
        projets._SAISIS.clear()
        assert projets.charger_coffre() == ["XRAY_CLIENT_SECRET_TAM"]
        projets.au_demarrage()
        assert os.environ["XRAY_CLIENT_SECRET"] == "secret-coffre-1"
        # session seulement : rien dans le coffre
        projets.saisir_secret("JIRA_API_TOKEN", "jeton-session", memoriser=False)
        assert (coffre.SERVICE, "JIRA_API_TOKEN") not in faux.k.valeurs
        projets.effacer_secret("XRAY_CLIENT_SECRET_TAM")
        assert (coffre.SERVICE, "XRAY_CLIENT_SECRET_TAM") not in faux.k.valeurs and "XRAY_CLIENT_SECRET_TAM" not in os.environ
        monkeypatch.setenv("ATELIER_COFFRE", "non")
        assert not coffre.disponible() and projets.saisir_secret("JIRA_API_TOKEN", "x")["mode"] == "session"
    finally:
        keyring.set_keyring(precedent)
        os.environ.pop("JIRA_API_TOKEN", None)
