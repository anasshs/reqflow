"""Configuration par application : source des tests (JQL + dossiers) seule à décider, synchronisation de l'application
active (copie locale marquée par application), politique des US (espaces Jira) rattachée à l'application."""
import re

import pytest


class FauxJira:
    enabled = True

    def __init__(self):
        self.jqls = []
        self.tests = {
            "DEMO-1": {"components": [{"name": "Mobile"}], "liens": ["DEMO-50"]},
            "DEMO-2": {"components": [{"name": "Mobile"}], "liens": []},
            "DEMO-3": {"components": [{"name": "Web"}], "liens": ["DEMO-60"]},
        }
        self.exigences = {"DEMO-50": {"type": "Story", "parent": "DEMO-500"}, "DEMO-60": {"type": "Story", "parent": None},
                          "DEMO-500": {"type": "Epic", "parent": None}}

    def _issue(self, k):
        if k in self.tests:
            t = self.tests[k]
            return {"key": k, "fields": {"summary": k, "issuetype": {"name": "Test"}, "components": t["components"], "labels": [], "status": {"name": "Prêt"},
                                         "issuelinks": [{"type": {"name": "Test"}, "outwardIssue": {"key": x, "fields": {"issuetype": {"name": "Story"}}}} for x in t["liens"]]}}
        e = self.exigences[k]
        return {"key": k, "fields": {"summary": k, "issuetype": {"name": e["type"]}, "status": {"name": "À faire"},
                                     **({"parent": {"key": e["parent"]}} if e["parent"] else {})}}

    def rechercher(self, jql, champs, limite):
        self.jqls.append(jql)
        cles = re.findall(r"[A-Z]+-\d+", jql)
        if cles:
            return [self._issue(k) for k in cles if k in self.tests or k in self.exigences]
        comp = re.search(r'component in \("([^"]+)"', jql)
        return [self._issue(k) for k, t in self.tests.items() if not comp or t["components"][0]["name"] == comp.group(1)]


@pytest.fixture
def deux_apps(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.domain import projet, projets
    from atelier.generation import conception

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(projets, "cle_xray", lambda: "DEMO")
    conception.enregistrer_mapping({"application": {"champ": "composant", "champ_jira": ""}})
    m = carte.creer_app("Banque Mobile", ["android"], tests_xray={"valeurs": ["Mobile"]})
    w = carte.creer_app("Portail Web", ["web"], web={"url": "https://recette.exemple.fr"}, type_="web", tests_xray={"valeurs": ["Web"]})
    return carte, m["slug"], w["slug"]


def test_migration_et_enregistrement_de_la_source(deux_apps):
    from atelier.intelligence import source_tests

    carte, mob, web = deux_apps
    s = source_tests.source(mob)
    assert s["deduite"] and s["jql"] == 'project = "DEMO" AND issuetype = "Test" AND component in ("Mobile") ORDER BY key'
    s = source_tests.enregistrer(mob, 'project = "DEMO" AND component = "Mobile"', ["/Mobile/"])
    assert not s["deduite"] and s["jql"].endswith("ORDER BY key") and s["dossiers"] == ["/Mobile"]
    assert carte.config_app(mob)["tests_xray"] == {"dossiers": ["/Mobile"]}  # rangement des tests publiés
    with pytest.raises(ValueError):
        source_tests.enregistrer(mob, "  ")


def test_synchro_par_application_et_filtrage(deux_apps):
    from atelier.intelligence import patrimoine_xray as px

    carte, mob, web = deux_apps
    j = FauxJira()
    carte.choisir_app(mob)
    r = px.synchroniser_application(jira=j)
    assert r["tests_application"] == 2 and 'component in ("Mobile")' in r["jql"]
    carte.choisir_app(web)
    px.synchroniser_application(jira=j)
    d = px.charger()
    apps = {t["cle"]: t["applications"] for t in d["tests"]}
    assert apps == {"DEMO-1": [mob], "DEMO-2": [mob], "DEMO-3": [web]}  # les tests de l'autre application sont conservés
    assert {e["cle"] for e in d["exigences"]} == {"DEMO-50", "DEMO-500", "DEMO-60"}
    assert [t["cle"] for t in px.charger_vue()["tests"]] == ["DEMO-3"]  # application active : Portail Web
    carte.choisir_app(mob)
    assert [t["cle"] for t in px.charger_vue()["tests"]] == ["DEMO-1", "DEMO-2"]
    # un test qui sort de la JQL perd l'application ; ses exigences orphelines disparaissent
    j.tests["DEMO-1"]["components"] = [{"name": "Archive"}]
    px.synchroniser_application(jira=j)
    d = px.charger()
    assert {t["cle"] for t in d["tests"]} == {"DEMO-2", "DEMO-3"} and {e["cle"] for e in d["exigences"]} == {"DEMO-60"}


def test_politique_des_us_rattachee_a_l_application(deux_apps, monkeypatch):
    from atelier.intelligence import testabilite_us as t

    carte, mob, web = deux_apps
    carte.choisir_app(mob)
    t.enregistrer_espace({"projet_jira": "SQM", "nom": "Squad Mobile", "projet_xray": "DEMO"})
    carte.choisir_app(web)
    t.enregistrer_espace({"projet_jira": "SQW", "nom": "Squad Web", "projet_xray": "DEMO"})
    assert [e["projet_jira"] for e in t.espaces()] == ["SQW"]
    with pytest.raises(ValueError, match="rattaché"):
        t.enregistrer_espace({"projet_jira": "SQM", "nom": "x", "projet_xray": "DEMO"})
    # ancienne politique (espace sans application) : vaut pour toutes, jusqu'au rattachement
    import yaml

    l = t.tous_espaces() + [{"projet_jira": "OLD", "nom": "Ancien", "actif": True, "types_issue": ["Story"], "statuts": [], "jql_complement": "",
                             "projet_xray": "DEMO", "type_test": "Manual", "min_tests": 1, "portee": "sprint"}]
    t._ecrire("espaces.yaml", yaml.safe_dump({"espaces": l}, allow_unicode=True))
    assert {e["projet_jira"] for e in t.espaces()} == {"SQW", "OLD"}
    t.rattacher_espace("OLD", mob)
    assert [e["projet_jira"] for e in t.espaces()] == ["SQW"]
    carte.choisir_app(mob)
    assert {e["projet_jira"] for e in t.espaces()} == {"SQM", "OLD"}
