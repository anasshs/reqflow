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


def test_recuperer_tirer_basculer(depot, tmp_path):
    """Récupérer (fetch), tirer (pull --ff-only) et basculer, sans jamais fusionner à la place de l'automaticien."""
    from atelier.generation import studio

    repo, distant, g = depot
    assert studio.git()["amont"] == ""  # branche de travail jamais poussée
    with pytest.raises(ValueError, match="distante suivie"):
        studio.synchroniser("tirer")
    (repo / "brouillon.robot").write_text("x", "utf-8")  # fichier non suivi : n'empêche pas de basculer
    (repo / "tests" / "connexion.robot").write_text("modifié", "utf-8")
    with pytest.raises(ValueError, match="non validées"):
        studio.synchroniser("basculer", "main")
    g("checkout", "--", "tests/connexion.robot")
    with pytest.raises(ValueError, match="inconnue"):
        studio.synchroniser("basculer", "nexiste-pas")
    g("branch", "--set-upstream-to=origin/main", "main")
    assert studio.synchroniser("basculer", "main")["branche"] == "main"
    autre = tmp_path / "collegue"  # un collègue pousse sur main
    subprocess.run(["git", "clone", "-q", str(distant), str(autre)], check=True, capture_output=True)
    (autre / "tests" / "nouveau.robot").write_text("*** Test Cases ***\nNouveau\n    Log    ok\n", "utf-8")
    for a in (["config", "user.email", "c@exemple.fr"], ["config", "user.name", "C"], ["add", "."], ["commit", "-qm", "nouveau"], ["push", "-q", "origin", "main"]):
        g(*a, cwd=autre)
    assert studio.git()["en_retard"] == 0  # rien de su avant de récupérer
    e = studio.synchroniser("recuperer")
    assert e["en_retard"] == 1 and e["amont"] == "origin/main" and "auto/connexion" not in e["branches_distantes"] and e["derniere_recuperation"]
    e = studio.synchroniser("tirer")
    assert e["en_retard"] == 0 and (repo / "tests" / "nouveau.robot").exists()
    (repo / "local.txt").write_text("l", "utf-8")  # divergence : commit local + commit distant
    g("add", "local.txt")
    g("commit", "-qm", "local")
    (autre / "b.txt").write_text("b", "utf-8")
    for a in (["add", "."], ["commit", "-qm", "distant"], ["push", "-q", "origin", "main"]):
        g(*a, cwd=autre)
    studio.synchroniser("recuperer")
    with pytest.raises(RuntimeError, match="divergé"):
        studio.synchroniser("tirer")
    with pytest.raises(ValueError, match="Action inconnue"):
        studio.synchroniser("pousser")


def test_mr_ouverte_pousse_les_nouveaux_commits(depot, monkeypatch):
    from atelier.generation import studio

    repo, distant, g = depot
    f = "tests/connexion.robot"
    monkeypatch.setattr(studio, "revues_scripts", lambda: {f: {"statut": "Approved", "historique": [{"auteur": "r", "date": "2026-11-15"}]}})
    monkeypatch.setattr(studio, "_stabilite_suites", lambda fs: {x: {"stable": True, "tests": {}} for x in fs})
    studio.proposer_mr("Connexion", gitlab_client=FauxGitLab())
    ouverte = FauxGitLab(ouvertes=[{"iid": 12, "cible": "main", "url": "https://g/mr/12"}])
    assert studio.proposer_mr("", gitlab_client=ouverte) == {"deja_ouverte": True, "mr": ouverte.ouvertes[0], "pousse": False}
    (repo / f).write_text("*** Test Cases ***\nConnexion valide\n    Log    ok v3\n", "utf-8")  # correction demandée en revue
    g("commit", "-qam", "connexion v3")
    monkeypatch.setattr(studio, "revues_scripts", lambda: {f: {"statut": "Technical Review", "historique": []}})
    with pytest.raises(PermissionError, match="Revue technique"):  # mêmes garde-fous que la création
        studio.proposer_mr("", gitlab_client=ouverte)
    monkeypatch.setattr(studio, "revues_scripts", lambda: {f: {"statut": "Approved", "historique": [{"auteur": "r", "date": "2026-11-15"}]}})
    r = studio.proposer_mr("", gitlab_client=ouverte)
    assert r["pousse"] and not ouverte.mrs  # aucune nouvelle MR
    assert "connexion v3" in subprocess.run(["git", "log", "--format=%s", "auto/connexion"], cwd=distant, capture_output=True, text=True).stdout
    assert studio.git()["en_avance"] == 0


def test_etat_de_travail_atelier_ne_bloque_pas(depot):
    """Revues, runs, sessions de l'atelier rangés dans le projet : signalés, jamais bloquants pour tirer / basculer."""
    from atelier.generation import studio

    repo, distant, g = depot
    (repo / "studio").mkdir()
    (repo / "studio" / "journal.jsonl").write_text("{}\n", "utf-8")
    g("add", "studio/journal.jsonl")
    g("commit", "-qm", "journal versionné par erreur")
    (repo / "studio" / "journal.jsonl").write_text("{}\n{}\n", "utf-8")
    e = studio.git()
    assert e["etat_atelier_versionne"] == 1 and e["etat_atelier_modifie"] == ["studio/journal.jsonl"] and not e["modifications"]
    assert not studio._modifs_bloquantes()
    with pytest.raises(RuntimeError, match="gitignore"):  # absent de main : Git protège le fichier, message clair
        studio.synchroniser("basculer", "main")
    g("rm", "-q", "--cached", "studio/journal.jsonl")
    g("commit", "-qm", "journal hors suivi")
    assert studio.synchroniser("basculer", "main")["branche"] == "main" and (repo / "studio" / "journal.jsonl").exists()
