"""Orchestrateur des travaux IA / MCP : étapes atelier, agent et humaines qui avancent seules, téléphones réservés,
reprise sur disque, demandes routées vers Claude Code ou Cursor."""
import pytest


@pytest.fixture
def orch(tmp_path, monkeypatch):
    from atelier.domain import projet
    from atelier.execution import historique, orchestrateur, robot

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(orchestrateur, "demarrer", lambda: None)  # les tours sont joués à la main
    orchestrateur._reservations.clear()
    runs = {}
    file = []

    def mettre_en_file(params, priorite, campagne, nom):
        rid = f"RUN-{len(file) + 1}"
        file.append({"id": rid, **params})
        runs[rid] = "en cours"
        return {"run_id": rid}

    monkeypatch.setattr(orchestrateur, "HOOKS", {"mettre_en_file": mettre_en_file, "emit": None})
    monkeypatch.setattr(historique, "lister", lambda n=50: [{"id": k, "statut": v, "passes": 1, "echecs": 0, "erreur": ""} for k, v in runs.items()])
    monkeypatch.setattr(robot, "selection_tests", lambda tests: {"cible": "tests/x.robot"})
    monkeypatch.setattr(orchestrateur, "telephones", lambda: ["tel-1"])
    monkeypatch.setattr(orchestrateur, "_tests_du_bdd", lambda *tags: ["tests/x.robot::Le test"])
    return orchestrateur, runs, file


def test_un_travail_avance_seul_jusqu_a_la_decision(orch):
    from atelier.integrations import boite_cursor

    o, runs, file = orch
    t = o.creer("Retour arrière", [
        {"titre": "Concevoir et automatiser", "type": "ia", "agent": "claude_code", "params": {"texte": "Scénario {bdd} · tag {travail}"}},
        {"titre": "Dry-run", "type": "atelier", "action": "dry_run", "params": {"bdd": "SC_1"}},
        {"titre": "Run réel", "type": "atelier", "action": "run", "params": {"bdd": "SC_1"}},
        {"titre": "Valider", "type": "humain"}], origine={"ecran": "ecran:x"}, env="recette")
    o.avancer()
    d = boite_cursor.etat()["demandes"][0]
    assert d["agent"] == "claude_code" and d["travail"] == t["id"] and d["texte"] == f"Scénario SC_1 · tag {t['id']}"
    # l'agent (Claude Code) prend la demande et en rend compte : l'étape est faite au tour suivant
    from atelier.domain import agent_mcp

    jeton = agent_mcp.definir("cursor 1.0")
    assert boite_cursor.suivante(0)["demande"] is None          # destinée à Claude Code : Cursor ne la reçoit pas
    agent_mcp.reinitialiser(jeton)
    jeton = agent_mcp.definir("claude-code 2.1")
    pris = boite_cursor.suivante(0)["demande"]
    agent_mcp.reinitialiser(jeton)
    boite_cursor.terminer(pris["id"], "SC_1 automatisé")
    o.avancer()
    assert o.obtenir(t["id"])["etapes"][0]["statut"] == "fait"
    o.avancer()                                                   # dry-run mis en file, sans téléphone
    e = o.obtenir(t["id"])["etapes"][1]
    assert e["statut"] == "en_cours" and file[-1]["dry_run"] and "UDID" not in file[-1]["variables"]
    runs[e["run_id"]] = "réussi"
    o.avancer()
    o.avancer()                                                   # run réel : téléphone réservé, passé au run
    e = o.obtenir(t["id"])["etapes"][2]
    assert e["statut"] == "en_cours" and e["telephone"] == "tel-1" and file[-1]["variables"]["UDID"] == "tel-1"
    assert o._reservations == {"tel-1": t["id"]}
    runs[e["run_id"]] = "réussi"
    o.avancer()
    assert o._reservations == {}                                 # téléphone libéré à la fin du run
    o.avancer()
    assert o.obtenir(t["id"])["etapes"][3]["statut"] == "attente_decision" and o.obtenir(t["id"])["statut"] == "en_cours"
    o.decider(t["id"], "E4", True)
    o.avancer()
    assert o.obtenir(t["id"])["statut"] == "termine"


def test_un_second_run_attend_le_telephone_et_un_echec_arrete_le_travail(orch):
    o, runs, file = orch
    a = o.creer("A", [{"titre": "Run", "type": "atelier", "action": "run", "params": {"bdd": "A"}}])
    b = o.creer("B", [{"titre": "Run", "type": "atelier", "action": "run", "params": {"bdd": "B"}}])
    o.avancer()
    assert o.obtenir(a["id"])["etapes"][0]["statut"] == "en_cours"
    assert o.obtenir(b["id"])["etapes"][0]["statut"] == "attente_ressource"   # un seul téléphone : B attend son tour
    runs[o.obtenir(a["id"])["etapes"][0]["run_id"]] = "échec"
    o.avancer()
    o.avancer()
    assert o.obtenir(a["id"])["statut"] == "echec" and o.obtenir(b["id"])["etapes"][0]["statut"] == "en_cours"
    o.reprendre(a["id"])                                          # relancé depuis l'étape en échec
    assert o.obtenir(a["id"])["statut"] == "en_cours" and o.obtenir(a["id"])["etapes"][0]["statut"] == "a_faire"


def test_une_erreur_interne_est_ecrite_sur_l_etape(orch, monkeypatch):
    o, runs, file = orch

    def casse(*a, **k):
        raise ValueError("priorité inconnue")
    monkeypatch.setitem(o.HOOKS, "mettre_en_file", casse)
    t = o.creer("F", [{"titre": "Run", "type": "atelier", "action": "dry_run", "params": {"bdd": "F"}}])
    for _ in range(3):
        o.avancer()
    e = o.obtenir(t["id"])["etapes"][0]
    assert e["statut"] == "echec" and "priorité inconnue" in e["erreur"]       # jamais avalée, jamais en boucle


def test_annuler_et_refuser(orch):
    o, runs, file = orch
    t = o.creer("C", [{"titre": "Décider", "type": "humain"}, {"titre": "Run", "type": "atelier", "action": "run"}])
    o.avancer()
    o.decider(t["id"], "E1", False, "pas maintenant")
    assert o.obtenir(t["id"])["statut"] == "arrete"
    u = o.creer("D", [{"titre": "Décider", "type": "humain"}])
    assert o.annuler(u["id"])["statut"] == "annule"
    with pytest.raises(ValueError):
        o.creer("E", [])
