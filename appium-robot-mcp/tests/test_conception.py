"""Test Design : cas de test, revue interne séparée de Xray, baselines immuables, mapping sans supposition."""
import shutil
from pathlib import Path

import pytest

from tests.conftest import pointer_projet

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"


@pytest.fixture
def td(tmp_path, monkeypatch):
    d = tmp_path / "demo"
    shutil.copytree(DEMO, d, ignore=shutil.ignore_patterns("results", "connaissance", "conception"))
    pointer_projet(d, monkeypatch)
    from atelier.generation import conception

    return conception


def test_cas_de_test_et_editeur_par_type(td):
    cas = {c["cle"]: c for c in td.cas_de_test()}
    assert len(cas) == 9
    assert cas["DEMO-301"]["editeur"] == "bdd" and cas["DEMO-301"]["bdd"] == "DEMO-301"
    assert cas["DEMO-302"]["editeur"] == "etapes" and cas["DEMO-302"]["automatise"]
    assert not cas["DEMO-308"]["automatise"] and cas["DEMO-308"]["revue"] == "Draft"
    assert cas["DEMO-301"]["synchronisation"].startswith("importé")


def test_vue_ensemble_reelle(td):
    v = td.vue_ensemble()
    assert v["kpi"]["cas_xray"] == 9 and v["kpi"]["automatises"] == 7 and v["kpi"]["scenarios_bdd"] == 1
    assert v["exigences_sans_test"] == ["DEMO-300"] and v["kpi"]["couverture_exigences"] == 80.0


def test_revue_workflow_et_controles(td):
    with pytest.raises(ValueError):
        td.transition_revue("DEMO-301", "approuver")  # pas encore en revue
    td.transition_revue("DEMO-301", "soumettre", reviseur="Test Lead")
    with pytest.raises(ValueError):
        td.transition_revue("DEMO-301", "demander_modifications")  # commentaire obligatoire
    r = td.transition_revue("DEMO-301", "approuver")
    assert r["statut"] == "Approved" and r["reviseur"] == "Test Lead"
    assert [h["vers"] for h in r["historique"]] == ["In Review", "Approved"]
    assert any(c["code"] == "jdd" and c["gravite"] == "ok" for c in r["controles"])
    # le statut interne ne modifie pas le statut Xray de l'instantané
    assert {c["cle"]: c for c in td.cas_de_test()}["DEMO-301"]["statut_xray"] == "Prêt"


def test_baseline_immuable_et_comparaison(td):
    import json

    from atelier.domain import projet

    b = td.creer_baseline("RELEASE_1.0", "avant correctif")
    assert b["tests"] == 9 and b["scenarios_bdd"] == 1
    with pytest.raises(FileExistsError):
        td.creer_baseline("RELEASE_1.0")
    with pytest.raises(ValueError):
        td.creer_baseline("../hors")
    f = projet.PROJECT_DIR / "patrimoine" / "xray.json"
    d = json.loads(f.read_text("utf-8"))
    next(e for e in d["exigences"] if e["cle"] == "DEMO-311")["resume"] = "Bloquer après 3 échecs (règle révisée)"
    f.write_text(json.dumps(d, ensure_ascii=False), "utf-8")
    c = td.comparer_baselines("RELEASE_1.0", "courant")
    assert c["exigences"]["modifies"] == {"DEMO-311": ["resume"]}
    assert c["tests_impactes"] == ["DEMO-304", "DEMO-306"]


def test_mapping_sans_supposition(td):
    m = td.mapping()
    assert all(s["externe"] == "" for s in m["statuts"])  # aucun équivalent Jira supposé
    assert "Cucumber" in m["modes"]["B (bidirectionnel)"]  # disponible depuis la vérification du schéma Xray
    t = td.tester_mapping()
    assert set(t["statuts_sans_equivalent"]) == set(td.STATUTS_REVUE)
    champs = {c["interne"]: c for c in t["champs"]}
    assert champs["summary"]["dans_instantane"] and not champs["preconditions"]["dans_instantane"]
    with pytest.raises(ValueError):
        td.enregistrer_mapping({"mode": "D (inconnu)"})
    with pytest.raises(ValueError):
        td.enregistrer_mapping({"champs": [{"interne": "dataset", "externe": "customfield_abc", "sens": "lecture"}]})
    m = td.enregistrer_mapping({"statuts": [{"interne": "Approved", "externe": "Ready"}], "champs": m["champs"] + [
        {"interne": "dataset", "externe": "customfield_10042", "sens": "lecture", "actif": True}]})
    assert m["statuts"] == [{"interne": "Approved", "externe": "Ready"}]
    assert any(c["externe"] == "customfield_10042" for c in m["champs"])



def test_statuts_workflow_test_depuis_jira(td, monkeypatch):
    class J:
        enabled = True

        def get(self, chemin):
            assert chemin == "/rest/api/3/project/TAM/statuses"
            return [{"name": "Story", "statuses": [{"name": "To Do"}]},
                    {"name": "Test", "statuses": [{"name": "Draft"}, {"name": "Ready for review"}, {"name": "Approved"}]}]

    monkeypatch.delenv("XRAY_TEST_ISSUE_TYPE", raising=False)
    w = td.statuts_workflow_test("tam", jira=J())
    assert w["type_trouve"] and w["statuts"] == ["Draft", "Ready for review", "Approved"]
    monkeypatch.setenv("XRAY_TEST_ISSUE_TYPE", "Cas de test")
    w = td.statuts_workflow_test("TAM", jira=J())
    assert not w["type_trouve"] and "To Do" in w["statuts"] and w["types_disponibles"] == ["Story", "Test"]
