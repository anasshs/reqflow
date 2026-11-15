"""Couverture : liaison Test Xray ↔ Story / Requirement Jira, Epics / Features en agrégation, 4 indicateurs distincts,
critères d'acceptation, versions, synchronisations journalisées sans perte silencieuse."""
import pytest


def _issue(cle, resume, type_, parent=None, liens=(), versions=(), description=None, statut="À faire"):
    return {"key": cle, "fields": {"summary": resume, "issuetype": {"name": type_}, "status": {"name": statut},
                                   "parent": {"key": parent} if parent else None, "fixVersions": [{"name": v} for v in versions],
                                   "issuelinks": [{"type": {"name": "Test", "inward": "is tested by", "outward": "tests"},
                                                   "inwardIssue": {"key": t, "fields": {"issuetype": {"name": "Test"}}}} for t in liens]
                                   + [{"type": {"name": "Blocks"}, "inwardIssue": {"key": "DEMO-999", "fields": {"issuetype": {"name": "Story"}}}}],
                                   "description": description}}


def _adf(texte):
    return {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": l}]} for l in texte.split("\n")]}


class FauxJira:
    enabled = True

    def __init__(self, exigences):
        self.exigences, self.tronque = exigences, False

    def rechercher(self, jql, champs, limite=1000):
        if jql.startswith("key in"):
            parents = {"DEMO-10": _issue("DEMO-10", "Virement interne", "Feature", parent="DEMO-1"), "DEMO-1": _issue("DEMO-1", "Gestion des virements", "Epic"),
                       "DEMO-20": _issue("DEMO-20", "Virement externe", "Feature", parent="DEMO-1")}
            return [parents[k] for k in jql[8:-1].split(", ") if k in parents]
        return self.exigences


EXIGENCES = [
    _issue("DEMO-11", "Virement interne valide", "Story", parent="DEMO-10", liens=["DEMO-101", "DEMO-102"], versions=["R3"],
           description=_adf("Contexte\nCritères d'acceptation :\n- compte émetteur valide\n- solde suffisant\n- plafond respecté")),
    _issue("DEMO-12", "Plafond dépassé", "Story", parent="DEMO-10", versions=["R3"]),
    _issue("DEMO-21", "Virement externe", "Story", parent="DEMO-20", liens=["DEMO-103"], versions=["R4"]),
]


@pytest.fixture
def projet(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.domain import projet as p
    from atelier.intelligence import patrimoine_xray

    monkeypatch.setattr(p, "PROJECT_DIR", tmp_path)
    carte.creer_app("Banque Mobile", ["android"])
    d = {"projet": "DEMO", "exigences": [], "tests": [
        {"cle": "DEMO-101", "resume": "VIR-001", "statut_xray": {"statut": "PASSED"}, "libelles": ["AC1"]},
        {"cle": "DEMO-102", "resume": "VIR-002", "statut_xray": {"statut": "FAILED"}},
        {"cle": "DEMO-103", "resume": "VIR-004", "statut_xray": None, "exigences": []},
        {"cle": "DEMO-104", "resume": "VIR-005 lié depuis le test", "statut_xray": {"statut": "PASSED"}, "exigences": ["DEMO-12"]},
        {"cle": "DEMO-105", "resume": "Orphelin", "exigences": []}]}
    patrimoine_xray.enregistrer(d, "test")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "vir.robot").write_text("*** Settings ***\nLibrary    AppiumLibrary\n*** Test Cases ***\nT1\n    [Tags]    DEMO-101\n    Log    a\n", "utf-8")
    from atelier.intelligence import couverture_exigences

    couverture_exigences.enregistrer_reglages('project = "DEMO" AND issuetype = Story', criteres_actifs=True)
    return couverture_exigences


def test_import_hierarchie_liens_natifs_et_quatre_indicateurs(projet):
    b = projet.importer(FauxJira(list(EXIGENCES)))
    assert b["exigences"] == 3 and b["ajoutees"] == ["DEMO-11", "DEMO-12", "DEMO-21"]
    c = projet.calculer()
    x = {e["cle"]: e for e in c["exigences"]}
    assert [t["cle"] for t in x["DEMO-11"]["tests"]] == ["DEMO-101", "DEMO-102"]  # lien lu depuis l'exigence (DEMO-999 « Blocks » ignoré)
    assert [t["cle"] for t in x["DEMO-12"]["tests"]] == ["DEMO-104"]  # lien lu depuis le test
    assert x["DEMO-11"]["fonctionnalite"] == "DEMO-10" and x["DEMO-11"]["macro"] == "DEMO-1"
    # 4 indicateurs distincts : DEMO-11 a des tests, tous exécutés, pas tous réussis, un automatisé
    assert (x["DEMO-11"]["existence"], x["DEMO-11"]["execution"], x["DEMO-11"]["resultat"], x["DEMO-11"]["automatisee"]) == (True, True, False, True)
    assert (x["DEMO-21"]["existence"], x["DEMO-21"]["execution"]) == (True, False)  # test jamais exécuté
    g = c["global"]
    assert (g["exigences"], g["existence"], g["execution"], g["resultat"], g["automatisee"]) == (3, 100.0, 66.7, 33.3, 33.3)
    assert c["tests_sans_exigence"] == ["DEMO-105"] and c["en_echec"] == ["DEMO-11"]
    assert [m["cle"] for m in c["macros"]] == ["DEMO-1"] and {f["cle"]: f["exigences"] for f in c["fonctionnalites"]} == {"DEMO-10": 2, "DEMO-20": 1}
    assert c["versions"] == ["R3", "R4"] and [e["cle"] for e in projet.calculer(version="R4")["exigences"]] == ["DEMO-21"]
    assert projet.calculer(plateforme="web")["global"]["automatisee"] == 0.0  # automatisé sur android seulement


def test_criteres_d_acceptation_partielle(projet):
    projet.importer(FauxJira(list(EXIGENCES)))
    x = {e["cle"]: e for e in projet.calculer()["exigences"]}["DEMO-11"]
    assert [c["texte"] for c in x["criteres"]] == ["compte émetteur valide", "solde suffisant", "plafond respecté"]
    assert [c["tests"] for c in x["criteres"]] == [["DEMO-101"], [], []] and x["etat"] == "partielle"  # libellé AC1 sur le test
    projet.associer_critere("DEMO-11", 2, ["DEMO-102"])
    projet.associer_critere("DEMO-11", 3, ["DEMO-102"])
    assert {e["cle"]: e for e in projet.calculer()["exigences"]}["DEMO-11"]["etat"] == "couverte"
    with pytest.raises(ValueError):
        projet.associer_critere("DEMO-11", 9, [])


def test_synchro_sans_perte_silencieuse_et_instantanes(projet):
    projet.importer(FauxJira(list(EXIGENCES)))
    b = projet.importer(FauxJira([EXIGENCES[0], EXIGENCES[2]]))
    assert b["sorties_du_perimetre"] == ["DEMO-12"]
    c = projet.calculer()
    assert [h["cle"] for h in c["hors_perimetre"]] == ["DEMO-12"] and c["global"]["exigences"] == 2  # gardée, marquée, hors calcul
    with pytest.raises(ValueError, match="conservées"):
        projet.importer(FauxJira([]))
    projet.enregistrer_instantane("R3", "fin de sprint")
    ev = projet.evolution()
    assert ev["instantanes"][0]["version"] == "R3" and len(ev["synchros"]) == 2
