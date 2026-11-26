"""Base de l'atelier (documents, versions, déplacement), comptes (empreinte, rôles, projets, connexion exigée), projets
partagés entre postes (dossier propre à chaque poste), assistant du premier lancement."""
import json
import subprocess

import pytest


@pytest.fixture
def poste(tmp_path, monkeypatch):
    """Un poste neuf : sa base, sa configuration, la liste des projets dans la base (pas le fichier des tests)."""
    from atelier.domain import magasin, utilisateurs

    monkeypatch.setenv("ATELIER_DOSSIER", str(tmp_path / "poste"))
    monkeypatch.delenv("ATELIER_BASE", raising=False)
    monkeypatch.delenv("ATELIER_PROJETS", raising=False)
    monkeypatch.setattr(magasin, "_BASE", None)
    utilisateurs._SESSIONS.clear()
    return tmp_path


def test_documents_versions_conflit_et_deplacement(poste):
    from atelier.domain import magasin

    assert not magasin.configuree()
    v = magasin.ecrire("config", "x", {"a": 1}, version=0, par="moi")
    assert v == 1 and magasin.lire("config", "x")["a"] == 1
    with pytest.raises(magasin.Conflit):                     # deux postes : le second relit avant d'écrire
        magasin.ecrire("config", "x", {"a": 3}, version=0)
    assert magasin.ecrire("config", "x", {"a": 2}, version=1) == 2
    assert [h["operation"] for h in magasin.base().historique("config", "x")] == ["modification", "creation"]
    magasin.ecrire("config", "y_1", {"b": True})
    assert [d["_cle"] for d in magasin.lister("config", "y_")] == ["y_1"]       # « _ » n'est pas un joker
    exp = magasin.base().exporter(poste / "export.jsonl")
    assert exp["documents"] == 2
    autre = magasin.BaseLocale(poste / "ailleurs" / "atelier.db")              # la base déplacée sur un autre poste
    assert autre.importer(poste / "export.jsonl") == {"importes": 2, "ignores": 0}
    assert autre.lire("config", "x")["a"] == 2 and autre.importer(poste / "export.jsonl")["ignores"] == 2
    assert magasin.supprimer("config", "y_1") and magasin.lire("config", "y_1") is None


def test_comptes_empreinte_roles_et_dernier_responsable(poste):
    from atelier.domain import magasin, roles, utilisateurs

    assert not utilisateurs.actifs() and roles.role() == "responsable"          # mode ouvert, comme avant
    with pytest.raises(ValueError, match="premier compte"):
        utilisateurs.creer("b.durand", "un mot de passe long", "automaticien")
    with pytest.raises(ValueError, match="12 caractères"):
        utilisateurs.creer("a.martin", "court", "responsable")
    utilisateurs.creer("A.Martin", "un mot de passe long", "responsable", "Alice")
    brut = json.dumps(magasin.lire("utilisateurs", "a.martin"))
    assert "un mot de passe long" not in brut and "empreinte" in brut              # jamais le mot de passe
    assert "empreinte" not in utilisateurs.obtenir("a.martin") and "sel" not in utilisateurs.obtenir("a.martin")
    utilisateurs.creer("b.durand", "un autre mot de passe", "automaticien", projets=["demo"])
    with pytest.raises(PermissionError, match="incorrect"):
        utilisateurs.connecter("b.durand", "mauvais mot de passe")
    with pytest.raises(PermissionError, match="incorrect"):                      # même message : rien n'indique le compte
        utilisateurs.connecter("inconnu", "un autre mot de passe")
    jeton, u = utilisateurs.connecter("B.DURAND", "un autre mot de passe")
    assert utilisateurs.session(jeton)["identifiant"] == "b.durand"
    t = utilisateurs.COURANT.set(u)
    try:
        assert roles.utilisateur() == "b.durand" and roles.role() == "automaticien" and not roles.peut("merge_request")
        assert utilisateurs.projet_permis("demo") and not utilisateurs.projet_permis("autre")
    finally:
        utilisateurs.COURANT.reset(t)
    assert roles.role() == "automaticien"                                         # agent ou processus sans compte : jamais relecteur
    with pytest.raises(ValueError, match="responsable"):
        utilisateurs.modifier("a.martin", role="lecteur")
    utilisateurs.modifier("b.durand", actif=False)
    assert utilisateurs.session(jeton) is None                                    # désactivé : session fermée
    utilisateurs.changer_mot_de_passe("a.martin", "nouveau mot de passe long", ancien="un mot de passe long")
    with pytest.raises(PermissionError):
        utilisateurs.changer_mot_de_passe("a.martin", "encore un autre long", ancien="faux")


def test_projets_partages_dossier_propre_au_poste(poste, monkeypatch):
    from atelier.domain import magasin, projets

    ancien = poste / "ancien.json"                                                # liste d'avant la base : reprise
    d1 = poste / "depot_demo"
    d1.mkdir()
    ancien.write_text(json.dumps({"projets": [{"id": "demo", "nom": "DEMO", "dossier": str(d1), "xray_projet": "DEMO"}], "actif": "demo"}), "utf-8")
    monkeypatch.setattr(projets, "_fichier", lambda: ancien)
    l = projets.lister()
    assert [p["id"] for p in l["projets"]] == ["demo"] and l["fichier"] == "base de l'atelier"
    doc = magasin.lire("config", "projets")
    assert "dossier" not in doc["projets"][0]                                     # le dossier ne part pas dans la base partagée
    assert magasin._config_poste()["dossiers"] == {"demo": str(d1)}
    # autre poste : même base, pas de dossier → le projet est là, à rattacher
    base_partagee = magasin.chemin_base()
    monkeypatch.setenv("ATELIER_DOSSIER", str(poste / "poste2"))
    monkeypatch.setenv("ATELIER_BASE", str(base_partagee))
    monkeypatch.setattr(magasin, "_BASE", None)
    p = projets.lister()["projets"][0]
    assert p["id"] == "demo" and p["dossier"] == "" and not p["dossier_existe"]
    with pytest.raises(FileNotFoundError, match="pas de dossier sur ce poste"):
        projets.activer("demo")


def test_assistant_premier_compte_et_espace(poste, monkeypatch):
    from atelier.domain import assistant_poste, magasin, projet, utilisateurs

    e = assistant_poste.etat()
    assert not e["termine"] and not e["etapes"]["compte"] and not e["etapes"]["espace"]
    jeton, u = assistant_poste.creer_premier_compte("resp", "mot de passe du responsable", "Resp")
    assert u["role"] == "responsable" and magasin.configuree()
    with pytest.raises(PermissionError):
        assistant_poste.creer_premier_compte("autre", "mot de passe du responsable")
    with pytest.raises(PermissionError, match="connecter"):                     # comptes actifs, personne de connecté
        assistant_poste.espace({"nom": "DEMO", "dossier": str(poste)})
    # dépôt Git local en guise de GitLab : l'espace de travail est son clone
    source = poste / "gitlab_tests"
    source.mkdir()
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "x@exemple.invalid"], ["config", "user.name", "x"]):
        subprocess.run(["git", "-C", str(source), *args], check=True, capture_output=True)
    (source / "tests").mkdir()
    (source / "tests" / "a.robot").write_text("*** Test Cases ***\nA\n    No Operation\n", "utf-8")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(source), "commit", "-q", "-m", "init"], check=True, capture_output=True)
    monkeypatch.setattr(projet, "PROJECT_DIR", projet.PROJECT_DIR)
    t = utilisateurs.COURANT.set(u)
    try:
        with pytest.raises(ValueError, match="identifiant"):
            assistant_poste.cloner("https://moi:secret@gitlab.exemple/g/p.git", str(poste / "x"))
        r = assistant_poste.espace({"nom": "DEMO", "dossier": str(poste / "clone_demo"), "depot_git": source.as_uri(), "cloner": True, "xray_projet": "DEMO"})
    finally:
        utilisateurs.COURANT.reset(t)
    assert (poste / "clone_demo" / "tests" / "a.robot").exists() and r["projet"] == "demo"
    assert projet.PROJECT_DIR == (poste / "clone_demo").resolve()
    assert r["etat"]["etapes"]["espace"] and r["etat"]["termine"]


def test_connexion_exigee_par_l_interface(poste):
    from fastapi.testclient import TestClient

    from atelier.adapters.web import app as web
    from atelier.domain import utilisateurs

    c = TestClient(web.app, base_url="http://127.0.0.1:8765")
    c.get("/plateforme")                                                          # cookie de session de l'atelier
    assert c.get("/api/moi").status_code == 200                                   # mode ouvert : pas de compte, pas de connexion
    utilisateurs.creer("resp", "mot de passe du responsable", "responsable")
    r = c.get("/api/moi")
    assert r.status_code == 401 and r.json()["detail"] == "Connexion requise."
    assert c.get("/api/assistant/etat").status_code == 200                        # l'assistant reste lisible
    assert c.post("/api/connexion", json={"identifiant": "resp", "mot_de_passe": "faux"}).status_code == 401
    assert c.post("/api/connexion", json={"identifiant": "resp", "mot_de_passe": "mot de passe du responsable"}).status_code == 200
    m = c.get("/api/moi").json()
    assert m["compte"]["identifiant"] == "resp" and m["role"] == "responsable"
    r = c.post("/api/comptes", json={"identifiant": "lec", "mot_de_passe": "mot de passe du lecteur", "role": "lecteur"})
    assert r.status_code == 200 and "empreinte" not in r.text
    c2 = TestClient(web.app, base_url="http://127.0.0.1:8765")
    c2.get("/plateforme")
    c2.post("/api/connexion", json={"identifiant": "lec", "mot_de_passe": "mot de passe du lecteur"})
    assert c2.get("/api/comptes").status_code == 400                             # lecteur : pas de gestion des comptes
    c.post("/api/deconnexion")
    assert c.get("/api/moi").status_code == 401


def test_base_sur_un_partage_reseau_refusee(poste):
    from atelier.domain import assistant_poste

    partage = "\\\\serveur\\partage\\atelier.db"  # \\serveur\partage\atelier.db
    assert assistant_poste.chemin_reseau(partage) and assistant_poste.chemin_reseau("//serveur/partage/atelier.db")
    assert not assistant_poste.chemin_reseau(str(poste / "atelier.db"))
    with pytest.raises(ValueError, match="serveur de données"):
        assistant_poste.choisir_base(partage)
