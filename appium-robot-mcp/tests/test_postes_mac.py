"""Mac du Wi-Fi qui prêtent leurs iPhone : agent réel (HTTPS, certificat généré par openssl) devant un faux Appium,
client de l'atelier (appairage par code, relais local, épinglage du certificat). Aucun vrai Mac ni iPhone."""
import json
import shutil
import socket
import ssl
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytestmark = pytest.mark.skipif(not shutil.which("openssl"), reason="openssl absent : certificat de l'agent impossible à créer")

UDID = "00008110-001A2B3C4D5E6F70"


class FauxAppium(BaseHTTPRequestHandler):
    recus: list = []

    def log_message(self, *a):
        pass

    def _rep(self, data):
        b = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        FauxAppium.recus.append(("GET", self.path, None))
        self._rep({"value": {"ready": True}})

    def do_POST(self):
        corps = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        FauxAppium.recus.append(("POST", self.path, json.loads(corps or b"{}")))
        self._rep({"value": {"sessionId": "s-1", "capabilities": {}}})


@pytest.fixture
def mac(tmp_path, monkeypatch):
    import agent_mac
    from atelier.integrations import postes_mac

    appium = ThreadingHTTPServer(("127.0.0.1", 0), FauxAppium)
    threading.Thread(target=appium.serve_forever, daemon=True).start()
    agent = agent_mac.Agent(dossier=tmp_path / "agent", nom="mac-test", appium=f"http://127.0.0.1:{appium.server_address[1]}")
    agent.preparer_certificat()
    monkeypatch.setattr(agent, "appareils", lambda: {"ios_physiques": [{"udid": UDID, "nom": "iPhone de test", "ios": "17.5"}],
                                                     "ios_simulateurs": [], "android": [], "appium": True})
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(agent.cert, agent.cle)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), agent_mac.fabriquer_gestionnaire(agent))
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("ATELIER_POSTES_MAC", str(tmp_path / "postes.json"))
    monkeypatch.setenv("ATELIER_COFFRE", "non")
    postes_mac._cache.update(t=0.0, appareils=[])
    postes_mac._relais.clear()
    FauxAppium.recus = []
    yield agent, srv.server_address[1], postes_mac
    srv.shutdown()
    appium.shutdown()
    for s, _ in list(postes_mac._relais.values()):
        s.shutdown()
    postes_mac._relais.clear()


def test_appairage_puis_run_sur_l_iphone_du_mac(mac):
    agent, port, pm = mac
    code = f"{agent.code[:4]}-{agent.code[4:]}"
    with pytest.raises(PermissionError):
        pm.appairer("127.0.0.1", port, "AAAA-AAAA")                       # mauvais code : refusé, compté
    poste = pm.appairer("127.0.0.1", port, code.lower())                  # le code se saisit sans tenir compte de la casse
    assert poste["nom"] == "mac-test" and poste["empreinte"] == agent.empreinte
    with pytest.raises(PermissionError):
        pm.appairer("127.0.0.1", port, code)                              # un code ne sert qu'une fois
    a = pm.appareils(forcer=True)
    assert a[0]["udid"] == UDID and a[0]["plateforme"] == "ios" and a[0]["poste_nom"] == "mac-test"
    url = pm.url_appium(UDID)
    assert url.startswith("http://127.0.0.1:")                             # relais local, jamais exposé
    assert pm.url_appium("emulator-5554") is None                          # appareil du poste : Appium local
    v = pm.variables_run({"PLATFORM": "ios", "UDID": UDID})
    assert v["REMOTE_URL"] == url
    req = urllib.request.Request(url + "/session", data=json.dumps({"capabilities": {"alwaysMatch": {"appium:udid": UDID}}}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        assert json.loads(r.read())["value"]["sessionId"] == "s-1"
    assert FauxAppium.recus[-1][1] == "/session" and FauxAppium.recus[-1][2]["capabilities"]["alwaysMatch"]["appium:udid"] == UDID


def test_sans_jeton_l_agent_refuse(mac):
    agent, port, pm = mac
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(f"https://127.0.0.1:{port}/atelier/appareils", context=ctx, timeout=5)
    assert e.value.code == 401
    with pytest.raises(urllib.error.HTTPError) as e:                       # le relais Appium non plus
        urllib.request.urlopen(f"https://127.0.0.1:{port}/status", context=ctx, timeout=5)
    assert e.value.code == 401


def test_certificat_different_refuse(mac):
    agent, port, pm = mac
    pm.appairer("127.0.0.1", port, agent.code)
    l = pm.postes()
    l[0]["empreinte"] = "0" * 64                                           # un autre appareil se fait passer pour le Mac
    pm._ecrire(l)
    a = pm.appareils(forcer=True)
    assert a[0].get("erreur") and "certificat" in a[0]["erreur"]
    assert pm.url_appium(UDID) is None


def test_trop_d_essais_bloque_le_code(mac):
    agent, port, pm = mac
    for _ in range(5):
        with pytest.raises(PermissionError):
            pm.appairer("127.0.0.1", port, "ZZZZ-ZZZZ")
    with pytest.raises(PermissionError, match="trop d'essais"):
        pm.appairer("127.0.0.1", port, agent.code)


def test_reponse_au_scan(mac):
    import agent_mac

    agent, port, pm = mac
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.bind(("127.0.0.1", 0))
    port_scan = u.getsockname()[1]
    u.close()
    arret = threading.Event()
    threading.Thread(target=agent_mac.repondre_au_scan, args=(agent, port, port_scan, arret), daemon=True).start()
    c = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    c.settimeout(3)
    try:
        for _ in range(10):
            c.sendto(agent_mac.QUESTION_SCAN, ("127.0.0.1", port_scan))
            try:
                d = json.loads(c.recvfrom(4096)[0])
                break
            except socket.timeout:
                continue
        assert d["agent"] == "atelier-mac" and d["port"] == port and d["empreinte"] == agent.empreinte
    finally:
        arret.set()
        c.close()


def test_preuve_identique_des_deux_cotes():
    import agent_mac
    from atelier.integrations import postes_mac

    assert agent_mac.preuve("ab12-CD34", "f" * 64) == postes_mac.preuve("AB12CD34", "f" * 64)
