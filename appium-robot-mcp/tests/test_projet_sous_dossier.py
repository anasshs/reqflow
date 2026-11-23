"""Projet de tests dans un sous-dossier d'un repository multi-applications (clone local d'un dépôt GitLab) :
le dossier est créé à l'enregistrement, et l'état Git, les commits et la merge request de l'atelier se limitent à lui."""
import subprocess

import pytest

from tests.test_gitlab import FauxGitLab


@pytest.fixture
def mono(tmp_path, monkeypatch):
    """Dépôt d'entreprise : le code de deux applications et, en qa/robot, les tests Robot ; un origin nu local."""
    from atelier.domain import projet, projets

    distant, repo = tmp_path / "distant.git", tmp_path / "banque"
    g = lambda *a, cwd=repo: subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True)  # noqa: E731
    subprocess.run(["git", "init", "--bare", "-b", "main", str(distant)], check=True, capture_output=True)
    for d in ("app-mobile", "app-web"):
        (repo / d).mkdir(parents=True)
        (repo / d / "main.kt").write_text("fun main() {}\n", "utf-8")
    g("init", "-b", "main")
    g("config", "user.email", "dev@exemple.fr")
    g("config", "user.name", "Dev")
    g("add", ".")
    g("commit", "-m", "code des applications")
    g("remote", "add", "origin", str(distant))
    g("push", "origin", "main")
    monkeypatch.setenv("ATELIER_PROJETS", str(tmp_path / "conf" / "projets.json"))
    monkeypatch.setattr(projet, "PROJECT_DIR", repo.resolve())
    monkeypatch.setattr(projet, "SNAP_DIR", repo / ".mcp_snapshots")
    for v in projets.VARIABLES + projets.SECRETS + ("ROBOT_PROJECT_DIR",):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(projets, "_ORIGINE", {**{v: None for v in projets.VARIABLES + projets.SECRETS}, "ROBOT_PROJECT_DIR": None})
    return repo, distant, g


def test_sous_dossier_cree_a_l_enregistrement(mono):
    from atelier.domain import projet, projets

    repo, _, _ = mono
    with pytest.raises(ValueError, match="sans « .. »"):
        projets.enregistrer({"nom": "Banque", "depot": str(repo), "sous_dossier": "../ailleurs"})
    with pytest.raises(ValueError, match="Repository introuvable"):
        projets.enregistrer({"nom": "Banque", "depot": str(repo / "absent"), "sous_dossier": "qa/robot"})
    l = projets.enregistrer({"nom": "Banque", "depot": str(repo), "sous_dossier": "qa\\robot\\"})  # saisie Windows acceptée
    p = l["projets"][0]
    assert p["dossier"] == str((repo / "qa" / "robot").resolve()) and p["sous_dossier"] == "qa/robot" and p["depot"] == str(repo.resolve())
    gi = (repo / "qa" / "robot" / ".gitignore").read_text("utf-8")
    assert "/studio/" in gi and "/.mcp_snapshots/" in gi  # l'état de travail de l'atelier ne part pas chez les développeurs
    projets.activer(p["id"])
    assert projet.PROJECT_DIR == (repo / "qa" / "robot").resolve() and projet.git_prefixe() == "qa/robot/"
    # deuxième application du même dépôt : un autre dossier de tests, même repository
    l = projets.enregistrer({"nom": "Banque web", "depot": str(repo), "sous_dossier": "qa/robot-web"})
    assert {x["sous_dossier"] for x in l["projets"]} == {"qa/robot", "qa/robot-web"}
    with pytest.raises(ValueError, match="déjà déclaré"):
        projets.enregistrer({"nom": "Doublon", "depot": str(repo), "sous_dossier": "qa/robot"})
    # projet historique (un dossier, sans repository) : inchangé
    assert projets.valider({"nom": "Ancien", "dossier": str(repo / "app-web")})["dossier"] == str((repo / "app-web").resolve())


def test_git_limite_au_dossier_des_tests(mono, monkeypatch):
    """Les modifications des développeurs ailleurs dans le dépôt ne bloquent ni « tirer » ni la merge request ; les
    chemins sont relatifs au projet de tests (ceux de l'inventaire et des revues) ; la MR signale ce qui sort du dossier."""
    from atelier.domain import projet, projets
    from atelier.generation import studio

    repo, distant, g = mono
    projets.activer(projets.enregistrer({"nom": "Banque", "depot": str(repo), "sous_dossier": "qa/robot"})["projets"][0]["id"])
    tests = repo / "qa" / "robot"
    (tests / "suites").mkdir()
    (tests / "suites" / "virement.robot").write_text("*** Test Cases ***\nVirement\n    [Tags]    BQM-22\n    Log    ok\n", "utf-8")
    g("add", ".")
    g("commit", "-m", "socle des tests")
    g("push", "origin", "main")
    g("switch", "-c", "auto/virement")
    g("branch", "--set-upstream-to=origin/main")
    (tests / "suites" / "virement.robot").write_text("*** Test Cases ***\nVirement\n    [Tags]    BQM-22\n    Log    ok v2\n", "utf-8")
    (repo / "app-mobile" / "main.kt").write_text("fun main() { println() }\n", "utf-8")  # travail en cours d'un développeur

    e = studio.git()
    assert e["sous_dossier"] == "qa/robot" and e["racine"].endswith("banque")
    assert e["modifications"] == ["M suites/virement.robot"]  # rien de app-mobile
    assert studio._modifs_bloquantes() == ["suites/virement.robot"]
    f = "suites/virement.robot"
    monkeypatch.setattr(studio, "revues_scripts", lambda: {f: {"statut": "Approved", "historique": [{"auteur": "relecteur", "date": "2026-11-23"}]}})
    monkeypatch.setattr(studio, "_stabilite_suites", lambda fs: {x: {"stable": True, "tests": {"Virement": ["PASS"] * 3}} for x in fs})
    studio._commit("Virement : assertion du solde", [f])
    assert studio._modifs_bloquantes() == []  # le code du développeur, non commité, ne bloque pas
    assert studio.git()["commits"][0]["message"] == "Virement : assertion du solde"
    assert g("show", "--name-only", "--format=", "HEAD").stdout.split() == ["qa/robot/suites/virement.robot"]  # seul le fichier des tests

    (repo / "app-web" / "main.kt").write_text("fun main() { 1 }\n", "utf-8")  # un commit hors du dossier sur la branche
    g("commit", "-qm", "app-web : correctif embarqué", "--", "app-web/main.kt")
    gl = FauxGitLab()
    r = studio.proposer_mr("Virement", gitlab_client=gl)
    assert r["fichiers"] == [f]  # relatif au projet : la revue et la stabilité retrouvent la suite
    d = gl.mrs[0]["description"]
    assert "### Fichiers (dossier `qa/robot`)" in d and "### Hors du dossier des tests" in d and "`app-web/main.kt`" in d
    assert "auto/virement" in subprocess.run(["git", "branch"], cwd=distant, capture_output=True, text=True).stdout
    assert studio._derniere_recuperation()  # FETCH_HEAD lu dans le .git du dépôt, pas dans le dossier des tests
    assert projet.depuis_racine_git("app-web/main.kt") is None and projet.depuis_racine_git("qa/robot/a.robot") == "a.robot"
