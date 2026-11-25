"""Un test publié dans Xray a son code dans le dépôt Git du projet de tests : suite, pages, scénario BDD, jeux de
données commités sur une branche de travail (jamais sur main), prêts pour la merge request ; le ticket montre ce lien
et les valeurs des jeux au survol, sans jamais un secret."""
import subprocess

import pytest


def _g(racine, *args):
    return subprocess.run(["git", "-C", str(racine), *args], capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


@pytest.fixture
def depot(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.domain import projet
    from atelier.execution import orchestrateur

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    monkeypatch.setenv("ATELIER_FLUX", "simple")
    monkeypatch.setattr(orchestrateur, "demarrer", lambda: None)
    carte.creer_app("Banque Démo", ["android"])
    _g(tmp_path, "init", "-q", "-b", "main")
    _g(tmp_path, "config", "user.email", "atelier@exemple.invalid")
    _g(tmp_path, "config", "user.name", "Atelier")
    (tmp_path / "README.md").write_text("projet\n", "utf-8")
    _g(tmp_path, "add", "README.md")
    _g(tmp_path, "commit", "-q", "-m", "init")
    from atelier.generation import bdd

    bdd.creer("CARTE", "Carte")
    bdd.depuis_texte("CARTE", "# language: fr\nFonctionnalité: Carte\n  Scénario: Carte\n    Quand je fais x\n    Alors c'est fait\n")
    m = bdd.charger("CARTE")
    m["application"] = carte.app_courante()
    bdd.sauver(m)
    bdd.associer_jdd("CARTE", "CLIENT_A")
    (tmp_path / "tests" / "banque_demo").mkdir(parents=True)
    (tmp_path / "tests" / "banque_demo" / "carte.robot").write_text(
        "*** Test Cases ***\nCarte\n    [Tags]    CARTE\n    Initialiser Le Test    &{JDD_CLIENT_A}\n    No Operation\n", "utf-8")
    (tmp_path / "data" / "jdd").mkdir(parents=True)
    (tmp_path / "data" / "jdd" / "recette.yaml").write_text(
        "CLIENT_A:\n  description: Client de démo\n  donnees:\n    identifiant: demo01\n    mot_de_passe: '{{env:MDP_DEMO}}'\n    pin: '1234'\n"
        "AUTRE:\n  donnees: {a: 1}\n", "utf-8")
    (tmp_path / "data" / "jdd" / "preprod.yaml").write_text("AUTRE:\n  donnees: {a: 2}\n", "utf-8")
    return tmp_path


def test_fichiers_et_commit_sur_une_branche_de_travail(depot):
    from atelier.generation import studio, versionnement

    fs = versionnement.fichiers("CARTE")
    assert "tests/banque_demo/carte.robot" in fs and "data/jdd/recette.yaml" in fs
    assert "data/jdd/preprod.yaml" not in fs and any(f.endswith(".feature") for f in fs)        # seulement ce qui porte ses jeux
    e = versionnement.etat("CARTE")
    assert e["branche"] == "main" and set(e["a_commiter"]) == set(fs) and not e["commit"]
    with pytest.raises(PermissionError):                                                          # suite pas encore approuvée
        versionnement.committer(["CARTE"])
    studio.approuver_a_la_publication("tests/banque_demo/carte.robot")
    r = versionnement.committer(["CARTE"], xray={"CARTE": "DEMO-1"})
    assert r["nouvelle_branche"] and r["branche"].startswith("atelier/xray-") and set(r["fichiers"]) == set(fs)
    assert _g(depot, "rev-parse", "--abbrev-ref", "HEAD") == r["branche"]
    assert _g(depot, "log", "-1", "--format=%s", "main") == "init"                               # main jamais touchée
    assert "DEMO-1" in _g(depot, "log", "-1", "--format=%s")
    e = versionnement.etat("CARTE")
    assert not e["a_commiter"] and e["commit"]["hash"] == r["commit"] and not e["pousse"]
    assert versionnement.committer(["CARTE"])["commit"] == ""                                     # pas de commit vide


def test_le_ticket_montre_git_et_les_valeurs_des_jeux(depot):
    from atelier.generation import kanban, studio

    studio.approuver_a_la_publication("tests/banque_demo/carte.robot")
    t = kanban.ticket("CARTE")
    assert t["git"]["depot"] and t["git"]["a_commiter"]
    v = t["jeux_test"]["valeurs"]["CLIENT_A"]
    assert v["valeurs"] == {"identifiant": "demo01", "mot_de_passe": "{{env:MDP_DEMO}}", "pin": "••••"}   # jamais un secret
    r = kanban.committer("CARTE")
    assert r["commit"] and not kanban.ticket("CARTE")["git"]["a_commiter"]


def test_publier_dans_xray_commite_le_code(depot, monkeypatch):
    from atelier.generation import flux, tnr

    monkeypatch.setattr(tnr, "publier", lambda cles, xray=None: {"publies": [{"scenario": c, "xray": "DEMO-2"} for c in cles],
                                                                   "erreurs": [], "plan": None, "campagne": None})
    r = flux.publier(["CARTE"])
    assert r["git"]["commit"] and r["git"]["branche"].startswith("atelier/xray-")
    assert "DEMO-2" in _g(depot, "log", "-1", "--format=%s")


def test_sans_depot_git_la_publication_continue(tmp_path, monkeypatch):
    from atelier.domain import projet
    from atelier.generation import versionnement

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    assert versionnement.committer(["X"]) == {"depot": False, "commit": "", "fichiers": []}
    assert versionnement.etat("X") == {"depot": False}
