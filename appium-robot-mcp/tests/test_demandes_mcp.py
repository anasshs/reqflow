"""V2, phase 0 bis : aucun outil MCP n'écrit dans Jira / Xray ni ne modifie la carte sans validation côté serveur.
Chaque outil d'écriture dépose une demande ; rien n'est appelé avant l'acceptation dans l'atelier."""
import pytest


@pytest.fixture
def projet_tmp(tmp_path, monkeypatch):
    from atelier.domain import projet

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path.resolve())
    return tmp_path


@pytest.fixture
def appels(monkeypatch):
    """Les écritures réelles (Jira / Xray) sont espionnées : elles ne doivent partir qu'après acceptation."""
    from atelier.execution import suivi

    faits = []
    monkeypatch.setattr(suivi, "jira_transition", lambda k, t: faits.append(("jira", k, t)) or f"{k} → {t}")
    monkeypatch.setattr(suivi, "qualify_failure", lambda r, q, c="", m="": faits.append(("qualif", r, q)) or "ok")
    monkeypatch.setattr(suivi, "import_results_to_xray", lambda o, e="", p="", tp="": faits.append(("import", o, e)) or {"cle": "TAM-9"})
    return faits


def test_jira_transition_depose_une_demande(projet_tmp, appels):
    from atelier.adapters import facade
    from atelier.domain import demandes

    r = facade.jira_transition("TAM-1", "Done")
    assert "EN ATTENTE DE VALIDATION" in r and appels == []
    assert facade.jira_transition("TAM-1", "Done") and len(demandes.lister("en attente")) == 1  # idempotent
    d = demandes.lister("en attente")[0]
    with pytest.raises(ValueError, match="justifié"):
        demandes.decider(d["id"], False)
    d = demandes.decider(d["id"], True)
    assert d["statut"] == "exécutée" and appels == [("jira", "TAM-1", "Done")]
    with pytest.raises(ValueError, match="déjà traitée"):  # exécutée une seule fois
        demandes.decider(d["id"], True)
    assert [h["action"] for h in d["historique"]] == ["demande", "acceptée"]


def test_qualify_failure_et_rejet(projet_tmp, appels):
    from atelier.adapters import facade
    from atelier.domain import demandes

    assert "EN ATTENTE" in facade.qualify_failure("RUN-1", "locator", "id changé")
    d = demandes.lister("en attente")[0]
    assert demandes.decider(d["id"], False, "doublon")["statut"] == "rejetée" and appels == []


def test_import_xray_avec_apercu(projet_tmp, appels, monkeypatch):
    from atelier.adapters import facade
    from atelier.domain import demandes

    with pytest.raises(ValueError):
        facade.import_results_to_xray("results/mcp/output.xml")
    monkeypatch.setattr(facade, "parse_robot_output", lambda o: {"passes": 3, "echecs": 1})
    r = facade.import_results_to_xray("results/mcp/output.xml", project_key="TAM")
    assert r["statut"] == "en attente de validation" and r["apercu"] == {"passes": 3, "echecs": 1} and appels == []
    assert demandes.decider(r["demande"], True)["resultat"] == {"cle": "TAM-9"}
    assert appels == [("import", "results/mcp/output.xml", "")]


def test_echec_d_execution_conserve(projet_tmp, monkeypatch):
    from atelier.adapters import facade
    from atelier.domain import demandes
    from atelier.execution import suivi

    def ko(k, t):
        raise RuntimeError("Jira indisponible")
    monkeypatch.setattr(suivi, "jira_transition", ko)
    facade.jira_transition("TAM-2", "Done")
    d = demandes.decider(demandes.lister("en attente")[0]["id"], True)
    assert d["statut"] == "échec" and "indisponible" in d["erreur"]


def test_run_robot_transitions_en_demandes(projet_tmp, appels, monkeypatch):
    from atelier.adapters import facade
    from atelier.domain import demandes
    from atelier.execution import robot

    recu = {}

    def faux_run(*a):
        recu["transitions"] = a[11:14]
        return {"code_retour": 1, "resultat": {"passes": 1, "echecs": 1}, "xray": {"execution": "TAM-50"}}
    monkeypatch.setattr(robot, "run_robot", faux_run)
    b = facade.run_robot("tests", xray_ticket="TAM", jira_transition_start="In Progress", jira_transition_end_if_fail="Failed")
    assert recu["transitions"] == ("", "", "")  # aucune transition transmise au run
    assert len(b["transitions_jira"]) == 2 and appels == []
    assert {d["params"]["issue_key"] for d in demandes.lister("en attente")} == {"TAM-50"}


def test_fusion_d_ecrans_et_remplacement_de_locator(projet_tmp, monkeypatch):
    from atelier.adapters import facade
    from atelier.discovery import carte
    from atelier.domain import demandes
    from atelier.generation import locators

    monkeypatch.setattr(carte, "ecran_nomme", lambda nom, sauf="": {"id": "e2", "nom": nom} if nom == "accueil" else None)
    monkeypatch.setattr(facade.carte_outils, "name_screen", lambda e, n, m="": {"id": e, "nom": n})
    assert facade.name_screen("e1", "connexion") == {"id": "e1", "nom": "connexion"}  # simple nommage : direct
    r = facade.name_screen("e1", "accueil")
    assert r["statut"] == "en attente de validation" and demandes.lister("en attente")[0]["type"] == "fusion_ecrans"
    assert facade.add_screen_locator("login", "bouton", "id=ok", "web")["locator"] == "id=ok"  # ajout : direct
    r = facade.add_screen_locator("login", "bouton", "id=valider", "web")
    assert r["statut"] == "en attente de validation" and locators.locator_capture("login", "bouton", "web") == "id=ok"
    d = demandes.decider(r["demande"], True)
    assert d["statut"] == "exécutée" and locators.locator_capture("login", "bouton", "web") == "id=valider"


def test_droit_de_validation_et_boite_a_valider(projet_tmp, appels, monkeypatch):
    from atelier.adapters import facade
    from atelier.domain import demandes, roles
    from atelier.intelligence import cerveau

    facade.jira_transition("TAM-3", "Done")
    l = [x for x in cerveau.a_valider() if x["decision"] == "action"]
    assert len(l) == 1 and l[0]["source"] == "Cursor (action)" and "TAM-3" in l[0]["libelle"]
    (projet_tmp / "atelier_roles.yaml").write_text("utilisateurs:\n  " + roles.utilisateur() + ": automaticien\n", "utf-8")
    with pytest.raises(PermissionError, match="relecteur"):
        demandes.decider(l[0]["id"], True)
    assert appels == []
