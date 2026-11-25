"""Serveur de données partagé : le vrai serveur (processus à part, sa base), deux postes qui s'y connectent.
Amorçage (la base d'un poste part sur le serveur avec ses comptes), connexion vérifiée par le serveur, droits
(lecteur en lecture seule, projets ouverts au compte, empreintes jamais rendues), synchronisation entre postes par le
serveur, HTTPS obligatoire hors de la machine."""
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent


def _port_libre() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture
def serveur(tmp_path):
    port = _port_libre()
    env = {k: v for k, v in __import__("os").environ.items() if k not in ("ATELIER_BASE", "ATELIER_DOSSIER")}
    p = subprocess.Popen([sys.executable, str(RACINE / "serveur_donnees.py"), "--base", str(tmp_path / "serveur" / "atelier.db"), "--port", str(port)],
                         cwd=str(RACINE), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            with urllib.request.urlopen(url + "/v1/sante", timeout=1) as r:
                if json.loads(r.read())["ok"]:
                    break
        except OSError:
            time.sleep(0.1)
    else:
        p.kill()
        raise RuntimeError("serveur non démarré : " + p.stdout.read().decode(errors="replace"))
    yield url
    p.terminate()
    p.wait(10)


@pytest.fixture
def poste(tmp_path, monkeypatch):
    from atelier.domain import magasin, utilisateurs

    def sur(nom: str):
        monkeypatch.setenv("ATELIER_DOSSIER", str(tmp_path / f"poste_{nom}"))
        monkeypatch.setenv("ATELIER_POSTE_NOM", f"PC-{nom.upper()}")
        monkeypatch.delenv("ATELIER_BASE", raising=False)
        monkeypatch.delenv("ATELIER_PROJETS", raising=False)
        monkeypatch.setattr(magasin, "_BASE", None)
        utilisateurs._SESSIONS.clear()
        utilisateurs._JETONS_SERVEUR.clear()
        utilisateurs._CACHE.clear()

    return sur


def test_https_obligatoire_hors_de_la_machine():
    from atelier import serveur_donnees

    with pytest.raises(SystemExit, match="HTTPS obligatoire"):
        serveur_donnees.creer_serveur("0.0.0.0", _port_libre())


def test_deplacer_la_base_sur_le_serveur_puis_travailler_a_deux(serveur, poste, tmp_path):
    from atelier.domain import assistant_poste, magasin, synchro, utilisateurs

    # poste A : base locale, deux comptes, un projet
    poste("a")
    _, resp = assistant_poste.creer_premier_compte("resp", "mot de passe du responsable", "Resp")
    utilisateurs.creer("lec", "mot de passe du lecteur", "lecteur", projets=["autre"])
    magasin.ecrire("config", "reglage", {"x": 1})
    t = utilisateurs.COURANT.set(resp)
    try:
        r = assistant_poste.choisir_base(serveur, deplacer=True)                     # la base part sur le serveur
    finally:
        utilisateurs.COURANT.reset(t)
    assert r["copie"]["importes"] >= 3 and magasin.distante()
    assert utilisateurs.actifs()                                                   # les comptes sont venus avec
    with pytest.raises(PermissionError):
        magasin.lire("config", "reglage")                                         # pas connecté au serveur : rien
    with pytest.raises(PermissionError):
        utilisateurs.connecter("resp", "faux mot de passe")
    jeton, u = utilisateurs.connecter("resp", "mot de passe du responsable")      # vérifié par le serveur
    t = utilisateurs.COURANT.set(u)
    try:
        assert magasin.lire("config", "reglage")["x"] == 1
        assert all("empreinte" not in c and "sel" not in c for c in utilisateurs.lister())
        with pytest.raises(PermissionError):                                       # accès générique aux comptes : refusé
            magasin.lire("utilisateurs", "resp")
        with pytest.raises(ValueError, match="déjà"):                              # serveur déjà amorcé
            assistant_poste.choisir_serveur(serveur, deplacer=True)
        dossier_a = tmp_path / "a" / "DEMO"
        (dossier_a / "conception").mkdir(parents=True)
        (dossier_a / "conception" / "kanban.yaml").write_text("us: {}\n", "utf-8")
        assert synchro.synchroniser("demo", dossier_a)["envoyes"] == ["conception/kanban.yaml"]
    finally:
        utilisateurs.COURANT.reset(t)

    # poste B : rejoint le serveur, se connecte, reçoit le travail de A
    poste("b")
    assistant_poste.choisir_serveur(serveur)
    jeton_b, ub = utilisateurs.connecter("resp", "mot de passe du responsable")
    t = utilisateurs.COURANT.set(ub)
    try:
        dossier_b = tmp_path / "b" / "DEMO"
        dossier_b.mkdir(parents=True)
        assert synchro.synchroniser("demo", dossier_b)["recus"] == ["conception/kanban.yaml"]
    finally:
        utilisateurs.COURANT.reset(t)
    # un lecteur : lecture seule, et seulement ses projets
    _, ul = utilisateurs.connecter("lec", "mot de passe du lecteur")
    t = utilisateurs.COURANT.set(ul)
    try:
        assert magasin.lire("config", "reglage")["x"] == 1
        with pytest.raises(PermissionError, match="automaticien"):
            magasin.ecrire("config", "reglage", {"x": 2})
        with pytest.raises(PermissionError, match="non ouvert"):
            magasin.versions("fichiers:demo")
        with pytest.raises(PermissionError):
            utilisateurs.lister()
    finally:
        utilisateurs.COURANT.reset(t)
    # synchronisation de fond (sans requête de page) : le jeton du dernier compte connecté sur ce poste, avec ses droits
    with pytest.raises(PermissionError, match="non ouvert"):                       # dernier connecté : le lecteur
        synchro.synchroniser("demo", tmp_path / "b" / "DEMO")
    utilisateurs.connecter("resp", "mot de passe du responsable")
    assert synchro.synchroniser("demo", tmp_path / "b" / "DEMO")["recus"] == []
