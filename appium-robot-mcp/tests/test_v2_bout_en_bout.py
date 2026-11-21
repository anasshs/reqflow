"""V2, phase 7 : critères de succès joués de bout en bout avec un VRAI client MCP (stdio, comme Cursor) et l'API web.
Parcours complet sur le projet de démonstration : piloté depuis Cursor, interrompu, repris sans perte ; les décisions
humaines (validation, qualification, synchronisation) ne passent que par l'atelier ; une écriture Jira demandée par
Cursor reste une demande."""
import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import client_mcp  # noqa: E402
from web_app_loader import charger_app_web, module_web  # noqa: E402

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"
HUMAINES = ("validation", "qualification", "synchronisation")


@pytest.fixture
def env(tmp_path, monkeypatch):
    from tests.conftest import pointer_projet

    d = tmp_path / "projet"
    shutil.copytree(DEMO, d, ignore=shutil.ignore_patterns("results", "connaissance", "studio", "executions"))
    pointer_projet(d, monkeypatch)
    monkeypatch.setattr(module_web(), "CONFIG_PATH", tmp_path / "atelier.json")
    web = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert web.get("/plateforme").status_code == 200
    return {"ROBOT_PROJECT_DIR": str(d), "ATELIER_PROJETS": str(tmp_path / "projets.json")}, web, d


def _etapes(pid, ids):
    out = []
    for e in ids:
        out += [("parcours_etape", {"parcours_id": pid, "etape": e, "action": "referencer", "reference_type": "autre", "reference_id": f"REF-{e}"}),
                ("parcours_etape", {"parcours_id": pid, "etape": e, "action": "valider", "commentaire": "fait par Cursor"})]
    return out


def test_parcours_complet_depuis_cursor_puis_l_atelier(env):
    e, web, d = env
    from atelier.intelligence import parcours_fonctionnalite as pf

    a = client_mcp.session([("parcours_initialiser", {"fonctionnalite": "Connexion", "jira": ["DEMO-11"]})], e)
    assert not a[0]["erreur"]
    pid = a[0]["valeur"]["id"]
    # Cursor fait les étapes 1 à 5 ; la validation des scénarios (humaine) reste en attente
    r = client_mcp.session(_etapes(pid, pf.IDS[:5]), e)
    assert not any(x["erreur"] for x in r)
    p = web.get(f"/api/parcours/{pid}").json()
    st = {x["id"]: x["statut"] for x in p["etapes"]}
    assert all(st[i] == "Validée" for i in pf.IDS[:4]) and st["validation"] == "En attente de validation" and p["statut"] == "Waiting for Validation"
    # interruption depuis Cursor : rien n'avance tant que le parcours est suspendu ; reprise sans perte
    r = client_mcp.session([("parcours_reprendre", {"parcours_id": pid, "action": "suspendre"}),
                            ("parcours_etape", {"parcours_id": pid, "etape": "validation", "action": "valider"})], e)
    assert r[0]["valeur"]["statut"] == "Suspended" and r[1]["erreur"] and "suspendu" in str(r[1]["valeur"])
    assert web.post(f"/api/parcours/{pid}/etat", json={"action": "reprendre"}).json()["statut"] == "Waiting for Validation"
    # décisions humaines dans l'atelier, travail technique par Cursor
    for i, humaine in enumerate(HUMAINES):
        assert web.post(f"/api/parcours/{pid}/etape", json={"etape": humaine, "action": "valider", "commentaire": "relu"}).status_code == 200
        suite = pf.IDS[pf.IDS.index(humaine) + 1:][:2 if humaine != "synchronisation" else 0]
        if humaine == "qualification":
            suite = ["execution", "analyse", "synchronisation"]
        if suite:
            r = client_mcp.session(_etapes(pid, suite), e)
            assert not any(x["erreur"] for x in r)
    fin = client_mcp.session([("parcours_etat", {"parcours_id": pid})], e)[0]["valeur"]
    assert fin["statut"] == "Completed" and all(x["statut"] == "Validée" for x in fin["etapes"])
    assert all(x["references"] for x in fin["etapes"])  # rien de perdu malgré la suspension
    origines = {h["origine"] for h in fin["historique"]}
    assert origines == {"mcp", "web"} and len(fin["versions"]) == 10
    assert all(x["validation"]["par"] != "cursor" for x in fin["etapes"] if x["id"] in HUMAINES)  # décision humaine


def test_cursor_ne_peut_ni_ecrire_dans_jira_ni_valider_une_decision_humaine(env):
    e, web, d = env
    r = client_mcp.session([("jira_transition", {"issue_key": "DEMO-11", "transition": "Done"}),
                            ("qualify_failure", {"run_id": "R1", "qualification": "bug"}),
                            ("parcours_initialiser", {"fonctionnalite": "Comptes"})], e)
    assert all("EN ATTENTE DE VALIDATION" in x["valeur"] for x in r[:2])
    dem = json.loads((d / "validations" / "demandes.json").read_text("utf-8"))
    assert [x["statut"] for x in dem] == ["en attente", "en attente"]
    assert {x["source"] for x in web.get("/api/cerveau/a-valider").json() if x["decision"] == "action"} == {"Cursor (action)"}


def test_outils_et_contrat_mcp(env):
    e, _, _ = env
    noms = client_mcp.lister_outils(e)
    attendu = json.loads((Path(__file__).parent / "fixtures" / "outils_mcp.json").read_text("utf-8"))
    assert set(attendu) <= set(noms) and len(noms) == 114  # + 2 interprétation des releases ; 76 historiques conservés + 12 ajoutés en V2 + agent_annoncer (console Cursor) + 2 granularité + 10 jugements délégués à Cursor + studio_rapprocher_etapes + 2 jugement des keywords + 5 référentiel de données Discovery + 2 boîte de demandes + discovery_parcours_cadre
    r = client_mcp.session([("cursor_regles", {}), ("coverage_ui", {}), ("failure_connaissance", {}), ("knowledge_entites", {"type": "champ"}),
                            ("test_design_doublons", {"titre": "Connexion refusée avec un mot de passe invalide"})], e)
    assert not any(x["erreur"] for x in r), [x for x in r if x["erreur"]]
    assert len(r[0]["valeur"]) == 11 and r[4]["valeur"]["meilleur"]["cle"]
