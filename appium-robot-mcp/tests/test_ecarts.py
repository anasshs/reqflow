"""Écarts développés : corrections de locator contrôlées, planification, OpenAPI, critères Jira, versions du graphe."""
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from tests.conftest import pointer_projet

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"
CHROMIUM = "/opt/pw-browsers/chromium"


@pytest.fixture
def demo(tmp_path, monkeypatch):
    d = tmp_path / "demo"
    shutil.copytree(DEMO, d, ignore=shutil.ignore_patterns("results", "connaissance", "analyses", "executions", "studio"))
    pointer_projet(d, monkeypatch)
    monkeypatch.setenv("WEB_BROWSER_EXECUTABLE", CHROMIUM)
    return d


def test_planification_une_fois_par_echeance(demo):
    from atelier.execution import centre

    with pytest.raises(ValueError):
        centre.enregistrer_campagne({"nom": "x", "plateformes": ["web"], "planning": {"type": "quotidien", "heure": "25:00"}})
    with pytest.raises(ValueError):
        centre.enregistrer_campagne({"nom": "x", "plateformes": ["web"], "planning": {"type": "intervalle", "minutes": 5}})
    c = centre.enregistrer_campagne({"nom": "TNR nuit", "plateformes": ["web"], "exclus": ["DEMO-304"],
                                     "planning": {"type": "quotidien", "heure": "02:00"}})[0]
    assert centre.params_campagne(c, "web")["exclude_tags"] == ["DEMO-304"]
    assert centre.campagnes_dues(datetime(2026, 11, 14, 1, 59)) == []
    assert [x["id"] for x in centre.campagnes_dues(datetime(2026, 11, 14, 2, 0, 30))] == [c["id"]]
    assert centre.campagnes_dues(datetime(2026, 11, 14, 2, 1)) == []  # pas de double déclenchement
    assert len(centre.campagnes_dues(datetime(2026, 11, 15, 2, 0, 5))) == 1


def test_openapi_criteres_et_versions(demo):
    from atelier.discovery import connaissance, intelligence_app as a

    g = connaissance.construire()
    assert "endpoint:POST /auth/login" in g.noeuds
    assert any(r.de == "user_story:DEMO-311" and r.vers == "endpoint:POST /auth/login" for r in g.relations.values())
    s = a.structurer("Après trois échecs consécutifs, le compte doit être bloqué")
    assert (s["condition"], s["resultat"], s["regle_candidate"]) == ("trois échecs consécutifs", "doit être bloqué", True)
    assert a.structurer("Le client saisit son identifiant")["regle_candidate"] is False
    a.creer_version("v1")
    r = a.analyser_jira()
    props = [x["proposition"] for x in r if x["proposition"]]
    assert "regle:DEMO-311-1" in props and len(a.analyser_jira()) == len(r)  # idempotent
    file = {x["id"] for x in a.validation()}
    assert "regle:DEMO-311-1" in file  # « à valider », jamais validé automatiquement
    c = a.comparer_versions("v1")
    assert "regle:DEMO-311-1" in c["noeuds_ajoutes"]
    with pytest.raises(FileExistsError):
        a.creer_version("v1")
    res = a.restaurer_version("v1")
    assert "regle:DEMO-311-1" not in connaissance.construire().noeuds
    assert res["sauvegarde"] in [v["nom"] for v in a.versions()]  # l'état d'avant est conservé


@pytest.mark.skipif(not Path(CHROMIUM).exists(), reason="Chromium absent")
def test_correction_locator_controlee(demo):
    from atelier.execution import echecs, historique
    from atelier.execution.robot import run_robot

    f = demo / "resources" / "locators" / "connexion.resource"
    f.write_text(f.read_text("utf-8").replace("message_erreur=id=message_erreur", "message_erreur=id=ancien_message"), "utf-8")
    params = {"target": "tests", "include_tags": ["DEMO-302"], "variables": {"PLATFORM": "web"}, "output_dir": "results/runs/RUN-20261114-080000",
              "xray_mode": "aucun", "jdd_env": "recette"}
    historique.enregistrer("RUN-20261114-080000", params, run_robot(**params), "2026-11-14T08:00:00", "2026-11-14T08:00:10")
    e = echecs.collecter()[0]
    i = echecs.investigation(e["id"])
    assert i["locator_etat"] == "Obsolete" and i["hypotheses"][0]["categorie"] == "Locator Issue"
    assert "id=message_erreur" in i["proposition_locator"]["propositions"]  # valeur observée dans la carte
    c = echecs.proposer_correction_locator(e["id"], "id=message_erreur", "observé sur l'écran cartographié")
    assert "-" in c["diff"] and "id=ancien_message" in f.read_text("utf-8")  # rien d'appliqué
    with pytest.raises(ValueError):
        echecs.faire_avancer_correction(c["id"], "appliquer")  # pas encore approuvée
    echecs.faire_avancer_correction(c["id"], "soumettre")
    echecs.faire_avancer_correction(c["id"], "approuver")
    echecs.faire_avancer_correction(c["id"], "appliquer")
    assert "message_erreur=id=message_erreur" in f.read_text("utf-8")
    with pytest.raises(ValueError, match="retest"):
        echecs.faire_avancer_correction(c["id"], "valider")


def test_builder_et_git_encadre(demo):
    import subprocess

    from atelier.generation import studio

    with pytest.raises(ValueError, match="absents du socle"):
        studio.construire_test("X", "DEMO-1", "CLIENT_ACTIF", [{"mot": "Given", "keyword": "keyword inexistant"}])
    c = studio.construire_test("Connexion puis déconnexion", "DEMO-307", "DECONNEXION",
                               [{"mot": "Given", "keyword": "je suis sur la page de connexion"}, {"mot": "Then", "keyword": "je me déconnecte"}])
    assert c["lint"]["ok"] and "Initialiser Le Test    &{JDD_DECONNEXION}" in c["contenu"]
    assert studio.ecrire_test(c)["revue"] == "Generated"
    with pytest.raises(Exception):
        studio.ecrire_test(c)  # jamais d'écrasement
    git = ["git", "-C", str(demo)]
    subprocess.run(git + ["init", "-q", "-b", "main"], check=True)
    subprocess.run(git + ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    with pytest.raises(PermissionError, match="protégée"):
        studio.commit("tests", [c["fichier"]])
    with pytest.raises(ValueError):
        studio.creer_branche("main")
    studio.creer_branche("automatisation/connexion")
    with pytest.raises(PermissionError, match="non approuvée"):
        studio.commit("nouveau test", [c["fichier"]])
