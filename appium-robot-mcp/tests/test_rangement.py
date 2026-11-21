"""Rangement des tests générés par application / module : dépôt Robot et dossier du Test Repository Xray."""
import pytest

from atelier.integrations.xray import XrayClient


@pytest.fixture
def projet_banque(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.domain import projet

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    carte.creer_app("Banque Mobile", ["android"], tests_xray={"dossiers": ["/Mobile"]})
    return tmp_path


def test_chemins_par_application_et_module(projet_banque):
    from atelier.generation import rangement

    m = {"cle": "DEMO-6", "titre": "Virement entre comptes", "module": "Virements"}
    assert rangement.chemin_robot(m) == "tests/banque_mobile/virements/virement_entre_comptes.robot"
    assert rangement.dossier_xray(m) == "/Mobile/Virements"
    assert rangement.chemin_robot({"cle": "DEMO-7"}) == "tests/banque_mobile/sans_module/demo_7.robot"
    rangement.maj(robot="suites/{module}/{scenario}.robot", xray="/Automatisés/{module}")
    assert rangement.chemin_robot(m) == "suites/virements/virement_entre_comptes.robot" and rangement.dossier_xray(m) == "/Automatisés/Virements"
    with pytest.raises(ValueError, match="variable"):
        rangement.maj(robot="tests/{inconnue}/{scenario}.robot")
    with pytest.raises(ValueError, match="hors du projet"):
        rangement.maj(robot="../ailleurs/{scenario}.robot")


class FauxXray(XrayClient):
    def __init__(self, mutations: dict):
        self.mutations, self.appels = mutations, []

    def _type_champs(self, nom):
        return {k: {"args": {a: True for a in v}} for k, v in self.mutations.items()} if nom == "Mutation" else {}

    def id_projet(self, projet):
        return "10001"

    def gql(self, q, v=None):
        self.appels.append((q.split("{")[1].split("(")[0].strip(), v))
        if "createFolder" in q and v["c"] == "/Mobile":
            raise RuntimeError("Folder already exists")
        return {}

    def creer_test_cucumber(self, projet, resume, gherkin):
        return {"cle": "DEMO-500", "issueId": "500", "avertissements": []}

    def lire_gherkin(self, cle):
        return None


def test_ranger_test_par_introspection():
    x = FauxXray({"createFolder": ["projectId", "path"], "addTestsToFolder": ["projectId", "path", "testIssueIds"]})
    r = x.ranger_test("DEMO", "500", "/Mobile/Virements")
    assert r["dossiers_crees"] == ["/Mobile/Virements"]  # /Mobile existait déjà
    assert x.appels[-1] == ("addTestsToFolder", {"p": "10001", "c": "/Mobile/Virements", "t": ["500"]})
    with pytest.raises(RuntimeError, match="addTestsToFolder"):
        FauxXray({}).ranger_test("DEMO", "500", "/Mobile")


def test_publication_rangee_dans_le_dossier_du_module(projet_banque):
    from atelier.generation import bdd, conception

    bdd.creer("DEMO-6", "Virement entre comptes", depuis_xray={"gherkin": "Feature: V\n  Scenario: V\n    Given que je suis connecté\n    Then le solde est affiché\n"})
    bdd.associer_module("DEMO-6", "Virements")
    x = FauxXray({"createFolder": ["projectId", "path"], "addTestsToFolder": ["projectId", "path", "testIssueIds"]})
    r = conception.publier_bdd("DEMO-6", "DEMO", xray=x)
    assert r["cle_xray"] == "DEMO-500" and "dans /Mobile/Virements" in r["resultat"]
    bdd.creer("DEMO-8", "Autre", depuis_xray={"gherkin": "Feature: A\n  Scenario: A\n    Given x\n    Then y\n"})
    bdd.associer_module("DEMO-8", "Cartes")
    r = conception.publier_bdd("DEMO-8", "DEMO", xray=FauxXray({}))  # schéma sans addTestsToFolder : créé, rangement signalé
    assert r["statut"] == "Succès" and "rangement dans /Mobile/Cartes impossible" in r["resultat"]


def test_brouillon_discovery_porte_le_module(projet_banque):
    from atelier.discovery import carte
    from atelier.generation import parcours_bdd

    e = lambda k, l, t="lien": {"key": k, "type": t, "libelle": l, "locators": [f"id={k}"]}  # noqa: E731
    a = carte.observer([e("lien_virements", "Virements")], "android", "accueil")
    b = carte.observer([e("bouton_continuer", "Continuer", "bouton")], "android", "virements")
    carte.renommer(a["id"], "accueil")
    carte.renommer(b["id"], "virements", "Virements")
    carte.enregistrer_transition(a["id"], b["id"], "android", {"type": "tap", "cle": "lien_virements", "libelle": "Virements"})
    r = parcours_bdd.brouillon(ecrans=["accueil", "virements"], titre="Ouvrir les virements")
    assert r["module"] == "Virements" and r["chemin_robot"] == "tests/banque_mobile/virements/ouvrir_les_virements.robot"
    assert r["dossier_xray"] == "/Mobile/Virements"
