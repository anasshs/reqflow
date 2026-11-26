"""Moteur d'exécution : vrais runs Robot Framework (suites locales) et listener de suivi en direct."""
from __future__ import annotations

import http.server
import json
import threading

import pytest

pytest.importorskip("robot")

SUITE = """*** Test Cases ***
Virement Nominal
    [Tags]    DEMO-1    smoke
    Log    ok

Virement En Echec
    [Tags]    DEMO-2
    Fail    Solde insuffisant
"""


@pytest.fixture
def suite(projet):
    f = projet / "tests" / "virement.robot"
    f.parent.mkdir()
    f.write_text(SUITE, "utf-8")
    return "tests/virement.robot"


def test_dry_run(suite):
    import server

    bilan = server.run_robot(suite, dry_run=True)
    assert bilan["code_retour"] == 0
    assert bilan["resultat"]["passes"] == 2 and bilan["resultat"]["echecs"] == 0


def test_run_reel_bilan_et_keyword_fautif(suite):
    import server

    bilan = server.run_robot(suite, variables={"PLATFORM": "android"})
    assert bilan["resultat"]["passes"] == 1 and bilan["resultat"]["echecs"] == 1
    echec = bilan["resultat"]["tests_en_echec"][0]
    assert echec["test"] == "Virement En Echec" and echec["message"] == "Solde insuffisant"
    assert echec["keyword_en_echec"] == "Fail"


def test_cible_hors_projet_refusee(projet):
    import server

    with pytest.raises(ValueError):
        server.run_robot("../ailleurs.robot")


def test_listener_suivi_en_direct(suite):
    """Le listener déplacé dans atelier/ est chargé par chemin par le sous-processus Robot."""
    import server

    recus = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            recus.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        bilan = server.run_robot(suite, events_url=f"http://127.0.0.1:{srv.server_address[1]}/api/events")
    finally:
        srv.shutdown()
    assert bilan["resultat"]["echecs"] == 1, bilan["erreurs"]
    types = [e["type"] for e in recus]
    assert types[0] == "run_debut" and "run_fin" in types
    fins = {e["nom"]: e for e in recus if e["type"] == "test_fin"}
    assert fins["Virement En Echec"]["statut"] == "FAIL"
    assert fins["Virement En Echec"]["message"] == "Solde insuffisant"


def test_option_listener_chemins_windows():
    """Robot coupe les arguments de listener sur « : » : un chemin C:\\… doit passer avec « ; »."""
    from atelier.execution.robot import option_listener

    assert option_listener("l.py", "/tmp/config.json") == "l.py:/tmp/config.json"
    assert option_listener(r"C:\a\l.py", r"C:\r\xray_run_config.json") == r"C:\a\l.py;C:\r\xray_run_config.json"


def test_env_robot_garde_seulement_l_encodage():
    """PYTHONIOENCODING « utf-8:surrogateescape » bloquait Robot (LookupError en boucle) : seul l'encodage est transmis."""
    from atelier.execution.robot import env_robot

    assert env_robot({"PYTHONIOENCODING": "utf-8:surrogateescape", "X": "1"}) == {"PYTHONIOENCODING": "utf-8", "X": "1"}
    assert env_robot({"PYTHONIOENCODING": "utf-8"})["PYTHONIOENCODING"] == "utf-8"
    assert "PYTHONIOENCODING" not in env_robot({})


def test_environnement_des_donnees_deduit_ou_run_bloque(projet):
    """Run lancé de l'atelier sans environnement de données : un seul environnement porte les jeux de la suite → il est
    retenu ; plusieurs ou aucun → le run n'est pas lancé (au lieu de « Variable '&{JDD_…}' not found » dans Robot)."""
    from atelier.execution.robot import environnement_des_jeux, run_robot

    (projet / "tests").mkdir(exist_ok=True)
    (projet / "tests" / "t.robot").write_text("*** Test Cases ***\nT\n    Initialiser Le Test    &{JDD_DEMO}\n", "utf-8")
    (projet / "tests" / "sans.robot").write_text("*** Test Cases ***\nT\n    Log    x\n", "utf-8")
    d = projet / "data" / "jdd"
    d.mkdir(parents=True, exist_ok=True)
    assert environnement_des_jeux("tests/sans.robot") == {}
    assert "absent" in environnement_des_jeux("tests/t.robot")["bloque"]
    (d / "prod.yaml").write_text("DEMO:\n  donnees:\n    nom: a\n", "utf-8")
    (d / "recette.yaml").write_text("AUTRE:\n  donnees:\n    nom: b\n", "utf-8")
    assert environnement_des_jeux("tests/t.robot") == {"env": "prod", "references": ["DEMO"]}
    (d / "recette.yaml").write_text("DEMO:\n  donnees:\n    nom: b\n", "utf-8")
    choix = environnement_des_jeux("tests/t.robot")
    assert "choisir l'environnement" in choix["bloque"] and "prod, recette" in choix["bloque"]
    assert run_robot("tests/t.robot")["statut"] == "bloqué données"  # rien n'est lancé
    assert run_robot("tests/t.robot", dry_run=True).get("code_retour") is not None  # dry run : jamais bloqué faute de données


def test_profil_de_donnees_choisi_au_lancement(projet, monkeypatch):
    """Variante d'un jeu (« variante_de ») choisie au lancement : les tests qui utilisent &{JDD_LOGIN} reçoivent les
    valeurs du profil (+18 / -18) sans modifier leur code ; une variante inconnue est refusée ; le secret reste masqué."""
    import pytest

    from atelier.execution import jdd
    from atelier.execution.robot import run_robot

    (projet / "tests").mkdir(exist_ok=True)
    (projet / "tests" / "p.robot").write_text(
        "*** Test Cases ***\nProfil\n    Should Be Equal    ${JDD_LOGIN}[identifiant]    ${ATTENDU}\n", "utf-8")
    d = projet / "data" / "jdd"
    d.mkdir(parents=True, exist_ok=True)
    (d / "recette.yaml").write_text(
        "LOGIN:\n  donnees:\n    identifiant: STANDARD\n    mot_de_passe: \"{{env:MDP_STD}}\"\n"
        "LOGIN_PLUS18:\n  variante_de: LOGIN\n  libelle: Client +18\n  donnees:\n    identifiant: MAJEUR\n    mot_de_passe: \"{{env:MDP_18}}\"\n", "utf-8")
    monkeypatch.setenv("MDP_STD", "x")
    monkeypatch.setenv("MDP_18", "y")
    assert jdd.variantes("recette") == {"LOGIN": [{"jeu": "LOGIN_PLUS18", "libelle": "Client +18", "description": ""}]}
    b = run_robot("tests/p.robot", variables={"ATTENDU": "MAJEUR"}, jdd_env="recette", jdd_variantes={"LOGIN": "LOGIN_PLUS18"},
                  output_dir="results/p1")
    assert b["code_retour"] == 0, b["console_fin"]
    assert b["jdd"]["variantes"] == {"LOGIN": "LOGIN_PLUS18"} and b["jdd"]["valeurs"]["LOGIN"]["mot_de_passe"] == "••••"
    assert run_robot("tests/p.robot", variables={"ATTENDU": "STANDARD"}, jdd_env="recette", output_dir="results/p2")["code_retour"] == 0
    with pytest.raises(ValueError):
        run_robot("tests/p.robot", jdd_env="recette", jdd_variantes={"LOGIN": "INCONNU"}, output_dir="results/p3")


def test_dry_run_avec_profil_sans_secret_ni_device(projet, monkeypatch):
    """Dry run d'un profil dont le mot de passe n'est pas encore dans le coffre : jamais bloqué, aucun secret lu."""
    from atelier.execution import jdd
    from atelier.execution.robot import run_robot

    (projet / "tests").mkdir(exist_ok=True)
    (projet / "tests" / "d.robot").write_text("*** Test Cases ***\nD\n    Log    ${JDD_LOGIN}[identifiant]\n", "utf-8")
    d = projet / "data" / "jdd"
    d.mkdir(parents=True, exist_ok=True)
    (d / "recette.yaml").write_text("LOGIN:\n  donnees:\n    identifiant: A\n    mot_de_passe: \"{{env:ABSENT_1}}\"\n"
                                    "LOGIN_B:\n  variante_de: LOGIN\n  donnees:\n    identifiant: B\n    mot_de_passe: \"{{env:ABSENT_2}}\"\n", "utf-8")
    monkeypatch.setattr(jdd, "valeur_env", lambda *a, **k: (_ for _ in ()).throw(AssertionError("secret lu en dry run")))
    b = run_robot("tests/d.robot", dry_run=True, jdd_env="recette", jdd_variantes={"LOGIN": "LOGIN_B"}, output_dir="results/dr")
    assert b["code_retour"] == 0 and not b["jdd"]["bloques"], b


def test_la_file_transmet_le_profil_de_donnees():
    """Profil choisi à l'écran : la file passe par le moteur (l'outil MCP historique run_robot garde sa signature) ;
    run_tests (outil récent) l'accepte."""
    import inspect
    from pathlib import Path

    from atelier.adapters import facade

    assert "jdd_variantes" not in inspect.signature(facade.run_robot).parameters
    assert "jdd_variantes" in inspect.signature(facade.run_tests).parameters
    app = (Path(__file__).resolve().parents[1] / "atelier" / "adapters" / "web" / "app.py").read_text("utf-8")
    assert '"jdd_variantes", "fichiers_arguments"))' in app  # profil de données et fichiers d'arguments du projet : le moteur
