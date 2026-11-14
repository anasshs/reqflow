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
