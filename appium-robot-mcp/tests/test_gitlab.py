"""GitLab : client (jeton en en-tête, jamais dans l'URL), merge request encadrée (jamais de fusion)."""
import json
import subprocess

import pytest


def test_client_jeton_en_entete_et_chemin_encode(monkeypatch):
    from atelier.integrations import gitlab

    monkeypatch.setenv("GITLAB_URL", "https://gitlab.exemple.interne/")
    monkeypatch.setenv("GITLAB_PROJET", "qa/automatisation/tests-banque")
    monkeypatch.setenv("GITLAB_TOKEN", '"jeton-secret-123"')
    appels = []

    def faux_http(methode, url, data=None, headers=None, timeout=60, cafile=None):
        appels.append((methode, url, json.loads(data) if data else None, headers))
        if url.endswith("/merge_requests") and methode == "POST":
            return json.dumps({"iid": 7, "title": "T", "state": "opened", "source_branch": "auto/x", "target_branch": "main", "web_url": "https://g/mr/7"})
        return json.dumps({"username": "jdupont", "name": "J. Dupont"})

    monkeypatch.setattr(gitlab, "http", faux_http)
    c = gitlab.GitLabClient()
    assert c.utilisateur()["login"] == "jdupont"
    mr = c.creer_mr("auto/x", "main", "T", "desc", ["automatisation"])
    assert mr["iid"] == 7
    for _, url, _, h in appels:
        assert "jeton-secret-123" not in url and h["PRIVATE-TOKEN"] == "jeton-secret-123"  # guillemets retirés
    assert "/projects/qa%2Fautomatisation%2Ftests-banque/merge_requests" in appels[1][1]
    assert appels[1][2]["remove_source_branch"] is False and "merge_when_pipeline_succeeds" not in appels[1][2]
    monkeypatch.setenv("GITLAB_URL", "http://gitlab.exemple.interne")
    with pytest.raises(ValueError, match="https"):
        gitlab.GitLabClient()


class FauxGitLab:
    def __init__(self, ouvertes=None):
        self.mrs, self.ouvertes = [], ouvertes or []

    def projet_info(self):
        return {"branche_defaut": "main", "chemin": "qa/tests", "url": "https://g/qa/tests"}

    def mr_ouvertes(self, source=""):
        return self.ouvertes

    def creer_mr(self, source, cible, titre, description, libelles=None):
        self.mrs.append({"source": source, "cible": cible, "titre": titre, "description": description})
        return {"iid": 12, "url": "https://g/qa/tests/-/merge_requests/12"}


@pytest.fixture
def depot(tmp_path, monkeypatch):
    """Repository de tests Git réel avec un « origin » nu local ; branche de travail avec une suite modifiée."""
    from atelier.domain import projet

    distant, repo = tmp_path / "distant.git", tmp_path / "repo"
    g = lambda *a, cwd=repo: subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True)  # noqa: E731
    subprocess.run(["git", "init", "--bare", "-b", "main", str(distant)], check=True, capture_output=True)
    repo.mkdir()
    g("init", "-b", "main")
    g("config", "user.email", "qa@exemple.fr")
    g("config", "user.name", "QA")
    (repo / "tests").mkdir()
    (repo / "tests" / "connexion.robot").write_text("*** Test Cases ***\nConnexion valide\n    [Tags]    DEMO-301\n    Log    ok\n", "utf-8")
    g("add", ".")
    g("commit", "-m", "socle")
    g("remote", "add", "origin", str(distant))
    g("push", "origin", "main")
    g("switch", "-c", "auto/connexion")
    (repo / "tests" / "connexion.robot").write_text("*** Test Cases ***\nConnexion valide\n    [Tags]    DEMO-301\n    Log    ok v2\n", "utf-8")
    g("commit", "-am", "connexion v2")
    monkeypatch.setattr(projet, "PROJECT_DIR", repo.resolve())
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    return repo, distant, g


def test_merge_request_encadree(depot, monkeypatch):
    from atelier.generation import studio

    repo, distant, g = depot
    f = "tests/connexion.robot"
    monkeypatch.setattr(studio, "revues_scripts", lambda: {f: {"statut": "Generated", "historique": []}})
    with pytest.raises(PermissionError, match="Revue technique"):
        studio.proposer_mr("Connexion", gitlab_client=FauxGitLab())
    monkeypatch.setattr(studio, "revues_scripts", lambda: {f: {"statut": "Approved", "historique": [{"auteur": "relecteur", "date": "2026-11-14"}]}})
    monkeypatch.setattr(studio, "_stabilite_suites", lambda fs: {x: {"stable": False, "tests": {"Connexion valide": ["PASS", "FAIL"]}} for x in fs})
    with pytest.raises(PermissionError, match="3 exécutions"):
        studio.proposer_mr("Connexion", gitlab_client=FauxGitLab())
    assert "auto/connexion" not in subprocess.run(["git", "branch"], cwd=distant, capture_output=True, text=True).stdout  # rien poussé
    gl = FauxGitLab()
    r = studio.proposer_mr("Connexion", "Automatisation du parcours.", derogation="démo client vendredi, runs à suivre", gitlab_client=gl)
    assert r["mr"]["iid"] == 12 and r["fichiers"] == [f]
    assert "auto/connexion" in subprocess.run(["git", "branch"], cwd=distant, capture_output=True, text=True).stdout  # branche poussée
    d = gl.mrs[0]["description"]
    assert gl.mrs[0]["cible"] == "main" and "Dérogation : démo client vendredi" in d and "Approved par relecteur" in d and "DEMO-301" not in ""
    assert studio.proposer_mr("Connexion", gitlab_client=FauxGitLab(ouvertes=[{"iid": 12}]))["deja_ouverte"]
    g("switch", "main")
    with pytest.raises(PermissionError, match="branche de travail"):
        studio.proposer_mr("X", gitlab_client=FauxGitLab())


def test_push_https_jeton_jamais_dans_la_commande(monkeypatch):
    from atelier.generation import studio

    monkeypatch.setenv("GITLAB_TOKEN", "jeton-xyz")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")  # configuration Git déjà passée par l'environnement : conservée
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "http.proxy")
    env = studio._git_env_push("https://gitlab.exemple.interne/qa/tests.git")
    assert env["GIT_CONFIG_COUNT"] == "2" and env["GIT_CONFIG_KEY_0"] == "http.proxy"
    assert env["GIT_CONFIG_KEY_1"] == "http.extraHeader" and "jeton-xyz" not in env["GIT_CONFIG_VALUE_1"]  # encodé en Basic
    assert studio._git_env_push("git@gitlab.exemple.interne:qa/tests.git")["GIT_CONFIG_COUNT"] == "1"  # SSH : clés de l'utilisateur
