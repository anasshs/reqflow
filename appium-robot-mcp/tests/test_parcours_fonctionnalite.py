"""V2, phase 1 : parcours de fonctionnalité (workflow léger, web + MCP)."""
import pytest


@pytest.fixture
def pf(tmp_path, monkeypatch):
    from atelier.domain import projet
    from atelier.intelligence import parcours_fonctionnalite

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path.resolve())
    return parcours_fonctionnalite


def test_creation_idempotente_et_etapes(pf):
    p = pf.creer("Connexion", jira=["tam-12"])
    assert p["fonctionnalite"] == "module:Connexion" and p["jira"] == ["TAM-12"] and p["statut"] == "Draft"
    assert [e["id"] for e in p["etapes"]] == pf.IDS and p["etapes"][1]["bloquee_par"] == ["discovery"]
    assert pf.creer("module:Connexion")["id"] == p["id"]  # un parcours ouvert par fonctionnalité
    with pytest.raises(ValueError):
        pf.creer("")
    with pytest.raises(ValueError, match="CLE-123"):
        pf.creer("Virements", jira=["pas une clé"])


def test_dependances_validation_saut_et_reprise(pf):
    p = pf.creer("Connexion")
    with pytest.raises(PermissionError, match="bloquée par"):
        pf.agir(p["id"], "reconstruction", "demarrer")
    pf.agir(p["id"], "discovery", "referencer", reference={"type": "session_discovery", "id": "DS-1"})
    p = pf.agir(p["id"], "discovery", "referencer", reference={"type": "session_discovery", "id": "DS-1"})  # idempotent
    assert len(p["etapes"][0]["references"]) == 1 and p["etapes"][0]["statut"] == "En cours" and p["statut"] == "In Progress"
    p = pf.agir(p["id"], "discovery", "valider", "carte complète")
    assert p["etapes"][0]["statut"] == "Validée" and p["version"] == 2 and p["versions"][-1]["etapes"]["discovery"]["references"] == ["session_discovery:DS-1"]
    with pytest.raises(ValueError, match="justification"):
        pf.agir(p["id"], "reconstruction", "sauter", "court")
    p = pf.agir(p["id"], "reconstruction", "sauter", "les US existent dans Jira")
    p = pf.agir(p["id"], "couverture", "valider")
    p = pf.agir(p["id"], "discovery", "revenir", "nouvel écran")  # les suivantes restent, à revoir
    assert p["etapes"][0]["statut"] == "En cours" and p["etapes"][1]["a_revoir"] and p["etapes"][2]["statut"] == "Validée"
    d = pf.comparer(p["id"], 2)
    assert {x["etape"] for x in d["differences"]} == {"discovery", "reconstruction", "couverture"}


def test_validation_humaine_imposee_cote_serveur(pf, monkeypatch):
    from atelier.domain import roles

    p = pf.creer("Connexion")
    for eid in ("discovery", "reconstruction", "couverture", "conception"):
        pf.agir(p["id"], eid, "sauter", "sans objet pour ce test")
    p = pf.agir(p["id"], "validation", "valider", "OK pour moi", origine="mcp")  # Cursor ne valide pas une décision humaine
    assert p["etapes"][4]["statut"] == "En attente de validation" and p["statut"] == "Waiting for Validation"
    origine = roles.peut
    monkeypatch.setattr(roles, "peut", lambda droit, u=None: droit != "decider_revue")
    with pytest.raises(PermissionError):
        pf.agir(p["id"], "validation", "valider")  # dans l'atelier : rôle relecteur exigé
    monkeypatch.setattr(roles, "peut", origine)
    assert pf.agir(p["id"], "validation", "valider", "scénarios relus")["etapes"][4]["statut"] == "Validée"


def test_suspendre_reprendre_abandonner(pf):
    p = pf.creer("Connexion")
    p = pf.changer_etat(p["id"], "suspendre")
    assert p["statut"] == "Suspended"
    with pytest.raises(ValueError, match="suspendu"):
        pf.agir(p["id"], "discovery", "demarrer")
    p = pf.changer_etat(p["id"], "reprendre")
    assert pf.agir(p["id"], "discovery", "demarrer")["statut"] == "In Progress"
    with pytest.raises(ValueError, match="justification"):
        pf.changer_etat(p["id"], "abandonner", "non")
    p = pf.changer_etat(p["id"], "abandonner", "fonctionnalité retirée du produit")
    assert p["statut"] == "Abandoned" and pf.creer("Connexion")["id"] != p["id"]  # un nouveau parcours peut repartir


def test_parcours_complet_et_outils_mcp(pf):
    from atelier.adapters import facade

    p = facade.parcours_initialiser("Connexion", jira=["TAM-12"])
    for eid in pf.IDS:
        facade.parcours_etape(p["id"], eid, "referencer", reference_type="autre", reference_id=f"REF-{eid}")
        r = facade.parcours_etape(p["id"], eid, "valider", "fait")
        if r["etapes"][pf.IDS.index(eid)]["validation_humaine"]:  # décision humaine : dans l'atelier
            assert r["etapes"][pf.IDS.index(eid)]["statut"] == "En attente de validation"
            pf.agir(p["id"], eid, "valider", "vu par l'automaticien")
    e = facade.parcours_etat(p["id"])
    assert e["statut"] == "Completed" and all(x["statut"] == "Validée" for x in e["etapes"])
    assert any(h["origine"] == "mcp" for h in e["historique"]) and facade.parcours_lister()[0]["avancement"] == "10/10"
    assert facade.parcours_reprendre(p["id"], "suspendre")["statut"] == "Suspended"


def test_routes_web(projet, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from web_app_loader import charger_app_web, module_web

    monkeypatch.setattr(module_web(), "CONFIG_PATH", tmp_path / "atelier.json")
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/plateforme").status_code == 200  # session web
    p = c.post("/api/parcours", json={"fonctionnalite": "Connexion"}).json()
    assert c.post(f"/api/parcours/{p['id']}/etape", json={"etape": "discovery", "action": "valider"}).json()["etapes"][0]["statut"] == "Validée"
    assert c.post(f"/api/parcours/{p['id']}/etape", json={"etape": "couverture", "action": "demarrer"}).status_code in (400, 403, 409)
    assert c.get(f"/api/parcours/{p['id']}/comparer", params={"a": 2}).json()["differences"] == []
    assert c.get("/api/parcours").json()[0]["id"] == p["id"]
