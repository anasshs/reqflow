"""Le coffre du système est la source des secrets : il prime sur une variable du poste, il est lu au moment de l'appel
dans tout processus (MCP compris), il porte les variables propres d'un projet, et une variable du poste peut y être
versée. Aucune valeur n'est renvoyée par l'API."""
import pytest


class FauxKeyring:
    def __init__(self):
        self.d = {}

    def get_password(self, service, nom):
        return self.d.get((service, nom))

    def set_password(self, service, nom, valeur):
        self.d[(service, nom)] = valeur

    def delete_password(self, service, nom):
        del self.d[(service, nom)]

    def get_keyring(self):
        return self


@pytest.fixture
def coffre_sys(tmp_path, monkeypatch):
    from atelier.domain import coffre, projet, projets

    k = FauxKeyring()
    monkeypatch.setattr(coffre, "_kr", lambda: k)
    monkeypatch.setenv("ATELIER_PROJETS", str(tmp_path / "projets.json"))
    for n in ("XRAY_CLIENT_ID", "XRAY_CLIENT_SECRET", "XRAY_CLIENT_ID_TAM", "XRAY_CLIENT_SECRET_TAM", "JIRA_API_TOKEN", "JIRA_EMAIL",
              "JIRA_BASE_URL", "ROBOT_PROJECT_DIR", "XRAY_BASE_URL", "GITLAB_URL", "GITLAB_PROJET"):
        monkeypatch.setenv(n, "x")
        monkeypatch.delenv(n)
        monkeypatch.setitem(projets._ORIGINE, n, None)
    monkeypatch.setattr(projets, "_SAISIS", set())
    monkeypatch.setattr(projets, "_POSTE", {})
    monkeypatch.setattr(projet, "PROJECT_DIR", (tmp_path / "depot").resolve())
    (tmp_path / "depot").mkdir()
    return k, projets


def test_coffre_prime_sur_le_poste_et_est_lu_a_l_appel(coffre_sys, monkeypatch):
    from atelier.integrations.jira import JiraClient
    from atelier.integrations.xray import XrayClient

    k, projets = coffre_sys
    monkeypatch.setenv("XRAY_CLIENT_ID", "ancienne-valeur-du-poste")
    monkeypatch.setenv("XRAY_CLIENT_SECRET", "ancien-secret")
    k.set_password("atelier-automatisation", "XRAY_CLIENT_ID", "id-coffre")
    k.set_password("atelier-automatisation", "XRAY_CLIENT_SECRET", "secret-coffre")
    x = XrayClient()  # sans rechargement : lu dans le coffre au moment de l'appel (cas d'un MCP déjà démarré)
    assert (x.cid, x.secret) == ("id-coffre", "secret-coffre")
    # Jira : jeton dans le coffre, e-mail / URL non secrets
    monkeypatch.setenv("JIRA_BASE_URL", "https://exemple.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "qa@exemple.fr")
    assert not JiraClient().enabled
    k.set_password("atelier-automatisation", "JIRA_API_TOKEN", "jeton-coffre")
    assert JiraClient().enabled
    # chargement dans l'environnement (hérité par les runs Robot)
    assert "XRAY_CLIENT_ID" in projets.charger_coffre()
    import os

    assert os.environ["XRAY_CLIENT_ID"] == "id-coffre"


def test_variables_propres_du_projet_dans_le_coffre(coffre_sys, tmp_path):
    from atelier.integrations.xray import XrayClient

    k, projets = coffre_sys
    k.set_password("atelier-automatisation", "XRAY_CLIENT_ID", "id-general")
    k.set_password("atelier-automatisation", "XRAY_CLIENT_SECRET", "secret-general")
    projets.enregistrer({"nom": "TAM", "dossier": str(tmp_path / "depot"), "xray_projet": "TAM",
                         "secrets": {"XRAY_CLIENT_ID": "XRAY_CLIENT_ID_TAM", "XRAY_CLIENT_SECRET": "XRAY_CLIENT_SECRET_TAM"}})
    with pytest.raises(RuntimeError, match="XRAY_CLIENT_ID_TAM"):
        XrayClient()  # le projet désigne ses propres variables : pas de repli silencieux sur le compte général
    k.set_password("atelier-automatisation", "XRAY_CLIENT_ID_TAM", "id-tam")
    k.set_password("atelier-automatisation", "XRAY_CLIENT_SECRET_TAM", "secret-tam")
    assert (XrayClient().cid, XrayClient().secret) == ("id-tam", "secret-tam")


def test_saisie_toujours_au_coffre_et_versement_du_poste(coffre_sys, monkeypatch):
    k, projets = coffre_sys
    r = projets.saisir_secret("XRAY_CLIENT_ID", "id-saisi", memoriser=False)  # coffre disponible : toujours au coffre
    assert r["mode"] == "coffre" and k.get_password("atelier-automatisation", "XRAY_CLIENT_ID") == "id-saisi"
    monkeypatch.setitem(projets._POSTE, "JIRA_API_TOKEN", '"jeton-du-poste"')
    monkeypatch.setenv("JIRA_API_TOKEN", '"jeton-du-poste"')
    etat = {s["nom"]: s for s in projets.connexions()["secrets"]}
    assert etat["JIRA_API_TOKEN"]["source"] == "poste" and etat["XRAY_CLIENT_ID"]["source"] == "coffre"
    assert "ANTHROPIC_API_KEY" in etat  # clés IA gérées par le coffre aussi
    r = projets.verser_dans_coffre("JIRA_API_TOKEN")
    assert k.get_password("atelier-automatisation", "JIRA_API_TOKEN") == "jeton-du-poste"  # guillemets retirés
    assert {s["nom"]: s for s in r["secrets"]}["JIRA_API_TOKEN"]["source"] == "coffre"
    assert "jeton-du-poste" not in str(r)  # jamais renvoyé
    with pytest.raises(ValueError):
        projets.verser_dans_coffre("PATH")
