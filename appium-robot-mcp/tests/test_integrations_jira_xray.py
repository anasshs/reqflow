"""Intégrations Jira / Xray des écrans : import des critères, anomalie Jira, publication BDD (clients simulés)."""
import shutil
from pathlib import Path

import pytest

from tests.conftest import pointer_projet

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"


@pytest.fixture
def demo(tmp_path, monkeypatch):
    d = tmp_path / "demo"
    shutil.copytree(DEMO, d, ignore=shutil.ignore_patterns("results", "connaissance", "conception", "analyses"))
    pointer_projet(d, monkeypatch)
    return d


def test_adf_et_criteres():
    from atelier.integrations.jira import adf_vers_texte
    from atelier.intelligence.patrimoine_xray import _description_et_criteres

    adf = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Critères d'acceptation :"}]},
                                       {"type": "bulletList", "content": [
                                           {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Si le solde est insuffisant, le virement est refusé"}]}]},
                                           {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Le montant doit être positif"}]}]}]}]}
    assert adf_vers_texte(adf) == "Critères d'acceptation :\n- Si le solde est insuffisant, le virement est refusé\n- Le montant doit être positif"
    r = _description_et_criteres({"description": adf})
    assert r["criteres"] == ["Si le solde est insuffisant, le virement est refusé", "Le montant doit être positif"]
    assert _description_et_criteres({"description": adf, "customfield_1": "- A\n- B"}, "customfield_1")["criteres"] == ["A", "B"]


class FauxJira:
    enabled = True

    def __init__(self):
        self.crees, self.jointes, self.liens, self.jql = [], [], [], []

    def rechercher(self, jql, champs, limite=1000):
        self.jql.append(jql)
        return [{"key": "DEMO-900", "fields": {"summary": "Blocage absent", "status": {"name": "Open"}}}]

    def creer_ticket(self, projet, resume, description, type_ticket=""):
        self.crees.append((projet, resume, type_ticket))
        return "DEMO-901"

    def joindre(self, cle, chemin):
        self.jointes.append(Path(chemin).name)

    def link(self, a, b, t="Relates"):
        self.liens.append((a, b, t))


def test_anomalie_jira(demo, monkeypatch):
    from atelier.execution import echecs

    ev = {"id": "RUN-1::t1", "nom": "Blocage", "cle_xray": "DEMO-304", "message": "Attendu : « bloqué ». Trouvé : « incorrect ».",
          "run": "RUN-1", "plateforme": "web", "environnement": "recette", "version": "1.0.0"}
    monkeypatch.setattr(echecs, "_evenement", lambda eid: ev)
    capture = demo / "results" / "runs" / "RUN-1" / "captures"
    capture.mkdir(parents=True)
    (capture / "c.png").write_bytes(b"png")
    monkeypatch.setattr(echecs, "investigation", lambda eid: {**ev, "brouillon_jira": {
        "summary": "[DEMO-304] Blocage", "steps": ["Given a"], "expected": "bloqué", "actual": "incorrect", "environment": "web",
        "version": "1.0.0", "xray": "DEMO-304", "execution": "RUN-1", "evidence": ["results/runs/RUN-1/captures/c.png"]}})
    j = FauxJira()
    d = echecs.doublons_jira("RUN-1::t1", "DEMO", jira=j)
    assert d[0]["cle"] == "DEMO-900" and 'linkedIssues("DEMO-304")' in j.jql[0] and "statusCategory != Done" in j.jql[0]
    r = echecs.creer_anomalie_jira("RUN-1::t1", "DEMO", jira=j)
    assert r == {"cle": "DEMO-901", "pieces_jointes": ["c.png"], "erreurs": []}
    assert j.crees[0][2] == "Bug" and j.liens == [("DEMO-901", "DEMO-304", "Relates")]


class FauxXrayClient:
    def __init__(self, existants=None):
        self.existants = existants or {}
        self.crees, self.maj = [], []

    def lire_gherkin(self, cle):
        return self.existants.get(cle)

    def creer_test_cucumber(self, projet, resume, gherkin):
        self.crees.append((projet, resume, gherkin))
        return {"cle": f"{projet}-77", "issueId": "77", "avertissements": []}

    def maj_gherkin(self, issue_id, gherkin):
        self.maj.append((issue_id, gherkin))


def test_publication_bdd_creation_mise_a_jour_conflit(demo):
    from atelier.generation import conception

    x = FauxXrayClient()
    with pytest.raises(ValueError):
        conception.publier_bdd("DEMO-301", "", xray=x)  # absent de Xray et pas de projet
    r = conception.publier_bdd("DEMO-301", "TAMX", xray=x)
    assert r["mode"].startswith("C") and r["cle_xray"] == "TAMX-77" and x.crees[0][2].startswith("Given que je suis")
    # Xray modifié depuis la publication : conflit, aucune écriture
    x.existants["TAMX-77"] = {"issueId": "77", "gherkin": "Given autre chose", "type": "Cucumber"}
    r = conception.publier_bdd("DEMO-301", xray=x)
    assert r["conflit"] and x.maj == []
    assert conception.publier_bdd("DEMO-301", decision="local", xray=x)["statut"] == "Succès" and len(x.maj) == 1
    # test d'un autre type : jamais converti
    x.existants["TAMX-77"]["type"] = "Manual"
    with pytest.raises(ValueError, match="conversion"):
        conception.publier_bdd("DEMO-301", xray=x)
    assert [h["statut"] for h in conception.historique_sync()][:3] == ["Refusé", "Succès", "Conflit"]

    class XrayEnPanne(FauxXrayClient):
        def lire_gherkin(self, cle):
            raise RuntimeError("Xray indisponible (502)")

    with pytest.raises(RuntimeError):
        conception.publier_bdd("DEMO-301", xray=XrayEnPanne())
    h = conception.historique_sync()[0]
    assert h["statut"] == "Erreur" and "502" in h["resultat"]  # RG-X07 : erreur historisée



def test_outline_examples_conserves_et_publies():
    from atelier.generation import bdd, conception

    texte = """Feature: Connexion
  Background:
    Given l'application est ouverte

  Scenario Outline: Refus des identifiants invalides
    When je saisis <identifiant>
    Then le message <message> est affiché

    Examples:
      | identifiant | message |
      | inconnu     | refusé  |

  Scenario: Autre cas
    Given un compte bloqué
"""
    m = bdd.parser(texte)
    sc = m["scenarios"][0]
    assert sc["plan"] and sc["exemples"] == ["| identifiant | message |", "| inconnu     | refusé  |"]
    ser = bdd.serialiser(m)
    assert "Scenario Outline: Refus" in ser and "| inconnu     | refusé  |" in ser
    assert bdd.parser(ser)["scenarios"][0]["exemples"] == sc["exemples"]  # aller-retour sans perte
    g = conception.gherkin_xray(m)
    assert g.startswith("Given l'application est ouverte") and "Examples:" in g and "| inconnu" in g
    assert conception.non_publies(m) == ["Autre cas"]


class FauxSchemaXray:
    """Réponses GraphQL simulées : introspection (Test sans « unstructured ») puis getTests."""

    def __init__(self):
        from atelier.integrations.xray import XrayClient

        self.requetes = []
        self._client = XrayClient.__new__(XrayClient)
        self._client.gql = self.gql

    def gql(self, q, v=None):
        self.requetes.append((q, v))
        if "__type" in q:
            nom = (v or {}).get("n")
            if nom == "Test":
                return {"__type": {"fields": [{"name": n, "args": [{"name": "limit", "defaultValue": None, "type": {"kind": "NON_NULL"}}] if n == "preconditions" else []}
                                              for n in ("issueId", "jira", "testType", "steps", "gherkin", "folder", "preconditions")]}}
            if nom == "Query":
                return {"__type": {"fields": [{"name": "getTests", "args": [{"name": n, "defaultValue": None, "type": {"kind": "NON_NULL" if n == "limit" else "SCALAR"}}
                                                                            for n in ("jql", "limit", "start")]}]}}
        assert "unstructured" not in q  # champ absent du schéma : jamais demandé
        assert "$l: Int!" in q and "$s: Int)" in q  # comme Xray Cloud : limit obligatoire, start facultatif
        res = [{"issueId": "10", "jira": {"key": "DEMO-301", "summary": "Connexion valide"}, "testType": {"name": "Cucumber", "kind": "Gherkin"},
                "gherkin": "Given x", "folder": {"path": "/Connexion"}, "preconditions": {"results": [{"jira": {"key": "DEMO-PC1", "summary": "Compte actif"}}]}},
               {"issueId": "11", "jira": {"key": "DEMO-302", "summary": "Mot de passe faux"}, "testType": {"name": "Manual", "kind": "Steps"},
                "steps": [{"action": "Saisir", "data": "mdp faux", "result": "Refus"}], "folder": None, "preconditions": {"results": []}}]
        return {"getTests": {"total": 2, "results": res}}


def test_import_definitions_xray(demo):
    from atelier.generation import conception
    from atelier.intelligence import patrimoine_xray

    x = FauxSchemaXray()
    r = patrimoine_xray.completer_depuis_xray(xray=x._client)
    assert r["importes"] == 2 and r["champs_absents"] == ["unstructured"] and "Xray (définitions)" in r["source"]
    assert len(r["introuvables"]) == 7  # tests de l'instantané absents de la réponse : signalés, jamais inventés
    t = {c["cle"]: c for c in conception.cas_de_test()}
    assert t["DEMO-301"]["type"] == "Cucumber" and t["DEMO-301"]["editeur"] == "bdd" and t["DEMO-301"]["dossier"] == "/Connexion"
    assert t["DEMO-301"]["preconditions"][0]["cle"] == "DEMO-PC1" and t["DEMO-301"]["issueId"] == "10"
    assert t["DEMO-302"]["editeur"] == "etapes" and t["DEMO-302"]["etapes"][0]["resultat"] == "Refus" and t["DEMO-302"]["dossier"] == "/"
    assert "définitions Xray importées" in t["DEMO-301"]["synchronisation"]
    assert patrimoine_xray.charger()["tests"][0]["cle"]  # instantané toujours valide


def test_import_refuse_dans_le_depot_de_l_outil_et_projet_different(demo, monkeypatch):
    from atelier.domain import projet
    from atelier.intelligence import patrimoine_xray

    x = FauxSchemaXray()
    with pytest.raises(ValueError, match="projet DEMO, pas TAM"):
        patrimoine_xray.completer_depuis_xray("TAM", xray=x._client)
    monkeypatch.setattr(projet, "PROJECT_DIR", projet.RACINE_OUTIL / "demo" / "banque_connexion")
    with pytest.raises(PermissionError, match="dépôt de l'atelier"):
        patrimoine_xray.completer_depuis_xray("DEMO", xray=x._client)
