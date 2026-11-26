"""QAFlow, phase Q2 : automatiser depuis une US, un test existant, un parcours, un plan ou une expression libre, puis
suivre l'automatisation d'après l'état réel de l'atelier (le dépôt de la demande à l'agent est simulé)."""
import shutil
from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"


@pytest.fixture
def env(projet, monkeypatch):
    shutil.copytree(DEMO, projet, dirs_exist_ok=True, ignore=shutil.ignore_patterns("results", "connaissance", "strategie"))
    from atelier.integrations import boite_cursor

    deposees = []

    def deposer(titre, texte, attendus=None, ecran="", mode="", **k):
        d = {"id": f"DC-test{len(deposees):04d}", "titre": titre, "texte": texte, "statut": "en attente", "mode": "boite", "ecran": ecran}
        deposees.append(d)
        return d

    monkeypatch.setattr(boite_cursor, "deposer", deposer)
    monkeypatch.setattr(boite_cursor, "etat", lambda limite=20: {"demandes": list(reversed(deposees))})
    return deposees


def test_test_existant_et_expression_libre(env):
    from atelier.generation import perimetre

    p = perimetre.resoudre("test", "demo-301")
    assert [t["cle"] for t in p["tests"]] == ["DEMO-301"] and p["tests"][0]["titre"] == "Connexion avec un compte valide"
    with pytest.raises(KeyError):
        perimetre.resoudre("test", "DEMO-999")
    p = perimetre.resoudre("libre", "Automatiser la connexion avec un compte bloqué")
    assert p["tests"][0]["cle"] == "DEMO-306" and p["tests"][0]["score"] >= perimetre.SEUIL_LIBRE
    assert perimetre.resoudre("libre", "xyz qqq")["tests"] == []


def test_lancer_libre_sans_test_existant(env):
    from atelier.generation import perimetre

    r = perimetre.automatiser("libre", "Automatiser le virement entre deux comptes", "robot-web")
    assert r["libre"] and r["tests"] == []
    texte = env[-1]["texte"]
    assert "« Automatiser le virement entre deux comptes »" in texte and "cherche d'abord l'existant" in texte
    assert "run_tests" in texte and "ne valide rien" in texte
    perimetre.automatiser("libre", "Automatiser le virement", "robot-web", rechercher_existant=False, executer=False)
    assert "cherche d'abord l'existant" not in env[-1]["texte"] and "run_tests" not in env[-1]["texte"]
    # un test existant coché : il est automatisé, pas reconçu
    r = perimetre.automatiser("libre", "connexion compte bloqué", "robot-web", tests=["DEMO-306"])
    assert r["tests"] == ["DEMO-306"] and not r["libre"] and "DEMO-306" in env[-1]["texte"]


def test_suivi_lu_dans_l_atelier(env):
    from atelier.generation import perimetre, suivi_automatisation

    r = perimetre.automatiser("test", "DEMO-301", "robot-web", executer=True)
    s = suivi_automatisation.suivi(r["demande"])
    assert s["agent"]["etat"] == "en_attente" and not s["termine"]
    t = s["tests"][0]
    assert t["cle"] == "DEMO-301" and [e["id"] for e in t["etapes"]] == ["prise", "bdd", "genere", "execute", "valide_qa"]
    etapes = {e["id"]: e["fait"] for e in t["etapes"]}
    assert etapes["prise"] is False and etapes["bdd"] is True           # scénario BDD présent dans la démo
    assert t["notions"]["valide_qa"] is False                             # jamais validé sans l'automaticien
    assert t["en_attente_de"] != "Demande prise par l'agent" or not etapes["bdd"]
    env[-1].update(statut="terminée", resultat="DEMO-301 automatisé et vérifié")
    s = suivi_automatisation.suivi(r["demande"])
    assert s["termine"] and s["agent"]["etat"] == "termine" and "vérifié" in s["agent"]["compte_rendu"]
    assert s["tests"][0]["etapes"][0]["fait"] is True
    l = suivi_automatisation.lister()
    assert l[0]["id"] == r["demande"] and l[0]["tests"] == 1
    with pytest.raises(KeyError):
        suivi_automatisation.suivi("DC-inconnue")


def test_routes(env, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from web_app_loader import charger_app_web, module_web

    monkeypatch.setattr(module_web(), "CONFIG_PATH", tmp_path / "atelier.json")
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    c.get("/qaflow")
    assert c.get("/api/automatisation/perimetre?entree=libre&reference=compte bloqué").json()["tests"][0]["cle"] == "DEMO-306"
    r = c.post("/api/automatisation/lancer", json={"entree": "libre", "reference": "Automatiser le virement", "technologie": "robot-web",
                                                   "executer": False, "ecran": "/qaflow#automatiser"})
    assert r.status_code == 200 and r.json()["libre"]
    assert env[-1]["ecran"] == "/qaflow#automatiser" and "run_tests" not in env[-1]["texte"]
    did = r.json()["demande"]
    assert c.get(f"/api/automatisation/suivis/{did}").json()["entree"] == "libre"
    assert c.get("/api/automatisation/suivis").json()[0]["id"] == did
