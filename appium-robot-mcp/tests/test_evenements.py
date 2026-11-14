"""Bus d'événements interne et relais vers l'interface web."""
from __future__ import annotations

import http.server
import json
import threading
import time

import pytest

from atelier.domain import evenements


@pytest.fixture(autouse=True)
def bus_propre():
    sauvegarde = list(evenements._abonnes)
    yield
    evenements._abonnes[:] = sauvegarde


def test_abonnement_filtre_par_type():
    recus = []
    stop = evenements.abonner(recus.append, {"carte_change"})
    evenements.publier({"type": "outil"})
    evenements.publier({"type": "carte_change", "x": 1})
    stop()
    evenements.publier({"type": "carte_change"})
    assert recus == [{"type": "carte_change", "x": 1}]


def test_abonne_en_erreur_ne_bloque_pas_les_autres():
    recus = []
    evenements.abonner(lambda ev: 1 / 0)
    evenements.abonner(recus.append)
    evenements.publier({"type": "outil"})
    assert recus == [{"type": "outil"}]


def test_chaque_abonne_recoit_une_copie():
    evenements.abonner(lambda ev: ev.update(type="modifie"))
    recus = []
    evenements.abonner(recus.append)
    evenements.publier({"type": "outil"})
    assert recus[0]["type"] == "outil"


def test_surlignage_seulement_si_quelqu_un_ecoute():
    evenements.reinitialiser()
    assert not evenements.a_des_abonnes("surlignage")
    evenements.abonner(lambda ev: None, {"carte_change"})
    assert not evenements.a_des_abonnes("surlignage")
    evenements.abonner(lambda ev: None)
    assert evenements.a_des_abonnes("surlignage")


def test_relais_mcp_vers_l_interface(monkeypatch, projet):
    recus = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            recus.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    from atelier.adapters import facade
    from atelier.adapters.mcp import server as serveur

    monkeypatch.setattr(facade, "WEB_EVENTS_URL", f"http://127.0.0.1:{srv.server_address[1]}/api/events")
    stop = evenements.abonner(serveur._relayer)
    try:
        serveur.write_project_file("tests/x.robot", "contenu")
        for _ in range(50):
            if recus:
                break
            time.sleep(0.05)
    finally:
        stop()
        srv.shutdown()
    assert recus == [("/api/events", {"source": "mcp", "type": "outil", "nom": "write_project_file",
                                      "args": {"path": "tests/x.robot"}})]


def test_propose_step_sans_interface():
    from atelier.adapters.mcp import server as serveur

    assert serveur.propose_step("Quand je valide")["decision"] == "sans validation"
