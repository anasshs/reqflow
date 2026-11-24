#!/usr/bin/env python3
"""Agent Mac de l'atelier : rend les iPhone (et téléphones Android) branchés sur ce Mac utilisables par l'atelier d'un
autre poste du même réseau Wi-Fi. Bibliothèque standard uniquement : Python 3.10+, Xcode et Appium suffisent.

    ./lancer-agent-mac.sh            (ou : python3 agent_mac.py)

Ce que fait l'agent :
- répond au scan réseau de l'atelier (UDP 47611) : nom du Mac, port, empreinte de son certificat ;
- liste les appareils du Mac : iPhone branchés (xcrun devicectl, idevice_id), simulateurs démarrés, Android (adb) ;
- relaie Appium : l'atelier pilote les iPhone comme un Appium local. Appium écoute ici sur 127.0.0.1 uniquement :
  seul l'agent est joignable sur le réseau.

Sécurité :
- HTTPS (certificat propre à ce Mac, créé au premier lancement avec openssl) ; l'atelier épingle son empreinte ;
- appairage par un code affiché ici (valable 15 min, 5 essais) : le code ne circule jamais, l'atelier prouve qu'il le
  connaît par un HMAC de l'empreinte du certificat (un intermédiaire sur le Wi-Fi ne peut ni le lire ni le rejouer) ;
- ensuite chaque requête porte un jeton (gardé ici sous forme d'empreinte SHA-256) ; réseau local uniquement ;
- l'agent ne reçoit ni test, ni donnée de test, ni secret : Robot, Xray et les jeux de données restent sur l'atelier.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION = 1
PORT = 47610            # HTTPS : appareils, appairage, relais Appium
PORT_SCAN = 47611       # UDP : réponse au scan de l'atelier
QUESTION_SCAN = b"ATELIER-AGENT?"
DOSSIER = Path(os.environ.get("ATELIER_AGENT_DOSSIER") or Path.home() / ".atelier-agent").expanduser()
APPIUM_LOCAL = os.environ.get("ATELIER_AGENT_APPIUM", "http://127.0.0.1:4723").rstrip("/")
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # sans 0/O ni 1/I : code lisible à l'écran
DUREE_CODE_S, ESSAIS_MAX = 15 * 60, 5


def normaliser_code(code: str) -> str:
    return "".join(c for c in (code or "").upper() if c.isalnum())


def preuve(code: str, empreinte: str) -> str:
    """Ce que l'atelier envoie à l'appairage : HMAC-SHA256 de l'empreinte du certificat, clé = le code affiché."""
    return hmac.new(normaliser_code(code).encode(), empreinte.encode(), hashlib.sha256).hexdigest()


def empreinte_der(der: bytes) -> str:
    return hashlib.sha256(der).hexdigest()


# =========================================================================== état de l'agent
class Agent:
    def __init__(self, dossier: Path = DOSSIER, nom: str = "", appium: str = APPIUM_LOCAL):
        self.dossier, self.appium = dossier, appium
        self.nom = nom or socket.gethostname().removesuffix(".local")
        self.dossier.mkdir(parents=True, exist_ok=True)
        self.verrou = threading.Lock()
        self.code, self.code_fin, self.essais = "", 0.0, 0
        self.nouveau_code()

    # ------------------------------------------------------------- certificat
    @property
    def cert(self) -> Path:
        return self.dossier / "cert.pem"

    @property
    def cle(self) -> Path:
        return self.dossier / "cle.pem"

    def preparer_certificat(self):
        if self.cert.exists() and self.cle.exists():
            return
        openssl = shutil.which("openssl")
        if not openssl:
            raise SystemExit("openssl introuvable (présent par défaut sur macOS) : impossible de créer le certificat de l'agent.")
        subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(self.cle), "-out", str(self.cert),
                        "-days", "3650", "-subj", f"/CN=atelier-agent-{self.nom}"], check=True, capture_output=True)
        os.chmod(self.cle, 0o600)

    @property
    def empreinte(self) -> str:
        return empreinte_der(ssl.PEM_cert_to_DER_cert(self.cert.read_text()))

    # ------------------------------------------------------------- appairage
    def nouveau_code(self) -> str:
        brut = "".join(secrets.choice(ALPHABET) for _ in range(8))
        self.code, self.code_fin, self.essais = brut, time.time() + DUREE_CODE_S, 0
        return f"{brut[:4]}-{brut[4:]}"

    def _jetons(self) -> list[dict]:
        f = self.dossier / "jetons.json"
        try:
            return json.loads(f.read_text("utf-8"))
        except (OSError, ValueError):
            return []

    def _ecrire_jetons(self, l: list[dict]):
        f = self.dossier / "jetons.json"
        f.write_text(json.dumps(l, ensure_ascii=False, indent=2), "utf-8")
        os.chmod(f, 0o600)

    def appairer(self, preuve_recue: str, poste: str) -> str:
        """Rend un jeton si la preuve correspond au code en cours ; lève PermissionError sinon."""
        with self.verrou:
            if not self.code or time.time() > self.code_fin or self.essais >= ESSAIS_MAX:
                raise PermissionError("Code d'appairage expiré ou trop d'essais : relancer l'agent pour en afficher un nouveau.")
            if not hmac.compare_digest(preuve(self.code, self.empreinte), str(preuve_recue or "")):
                self.essais += 1
                raise PermissionError("Code d'appairage incorrect.")
            jeton = secrets.token_urlsafe(32)
            l = self._jetons() + [{"poste": str(poste)[:80], "empreinte": hashlib.sha256(jeton.encode()).hexdigest(),
                                   "le": time.strftime("%Y-%m-%d %H:%M")}]
            self._ecrire_jetons(l)
            self.code = ""  # un code ne sert qu'une fois
            return jeton

    def autorise(self, jeton: str) -> bool:
        h = hashlib.sha256((jeton or "").encode()).hexdigest()
        return any(hmac.compare_digest(h, j["empreinte"]) for j in self._jetons())

    def appaire(self) -> bool:
        return bool(self._jetons())

    # ------------------------------------------------------------- appareils
    def identite(self) -> dict:
        return {"agent": "atelier-mac", "version": VERSION, "nom": self.nom, "empreinte": self.empreinte, "appaire": self.appaire()}

    def appium_pret(self) -> bool:
        try:
            with urllib.request.urlopen(self.appium + "/status", timeout=2):
                return True
        except OSError:
            return False

    def appareils(self) -> dict:
        out = {"ios_physiques": [], "ios_simulateurs": [], "android": [], "appium": self.appium_pret()}
        if shutil.which("xcrun"):
            try:
                r = subprocess.run(["xcrun", "simctl", "list", "devices", "booted", "-j"], capture_output=True, text=True, timeout=30)
                for runtime, devs in json.loads(r.stdout or "{}").get("devices", {}).items():
                    out["ios_simulateurs"] += [{"udid": d["udid"], "nom": d["name"], "runtime": runtime.split(".")[-1]}
                                               for d in devs if d.get("state") == "Booted"]
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
            out["ios_physiques"] = iphones_devicectl()
        if shutil.which("idevice_id"):
            try:
                r = subprocess.run(["idevice_id", "-l"], capture_output=True, text=True, timeout=20)
                out["ios_physiques"] += [{"udid": u, "nom": "iPhone"} for u in r.stdout.split()
                                         if u and u not in {x["udid"] for x in out["ios_physiques"]}]
            except (OSError, subprocess.SubprocessError):
                pass
        adb = shutil.which("adb") or next((p for p in (Path.home() / "Library/Android/sdk/platform-tools/adb",) if p.exists()), None)
        if adb:
            try:
                r = subprocess.run([str(adb), "devices", "-l"], capture_output=True, text=True, timeout=20)
                for ligne in r.stdout.splitlines()[1:]:
                    p = ligne.split()
                    if len(p) > 1 and p[1] == "device":
                        out["android"].append({"udid": p[0], "details": " ".join(p[2:])})
            except (OSError, subprocess.SubprocessError):
                pass
        return out

    # ------------------------------------------------------------- relais Appium
    def relayer(self, methode: str, chemin: str, corps: bytes, type_contenu: str) -> tuple[int, str, bytes]:
        u = urllib.parse.urlsplit(self.appium)
        c = http.client.HTTPConnection(u.hostname, u.port or 4723, timeout=600)  # création de session iOS : jusqu'à plusieurs minutes
        try:
            base = u.path.rstrip("/")
            c.request(methode, base + chemin, body=corps or None, headers={"Content-Type": type_contenu or "application/json"})
            r = c.getresponse()
            return r.status, r.getheader("Content-Type", "application/json"), r.read()
        finally:
            c.close()


def iphones_devicectl() -> list[dict]:
    try:
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "devices.json")
            subprocess.run(["xcrun", "devicectl", "list", "devices", "--json-output", f], capture_output=True, timeout=30)
            if not os.path.isfile(f):
                return []
            with open(f, encoding="utf-8") as fh:
                devices = (json.load(fh).get("result") or {}).get("devices") or []
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    out = []
    for x in devices:
        hp, cp, dp = x.get("hardwareProperties") or {}, x.get("connectionProperties") or {}, x.get("deviceProperties") or {}
        if hp.get("reality") == "physical" and hp.get("platform") in ("iOS", "iPadOS") and hp.get("udid") \
                and cp.get("pairingState", "paired") == "paired":
            out.append({"udid": hp["udid"], "nom": dp.get("name") or hp.get("marketingName") or "iPhone",
                        "ios": dp.get("osVersionNumber", "")})
    return out



# =========================================================================== serveur
def fabriquer_gestionnaire(agent: Agent):
    class Gestionnaire(BaseHTTPRequestHandler):
        server_version = "atelier-agent"

        def log_message(self, fmt, *args):  # journal court, sans en-têtes (le jeton n'y passe jamais)
            sys.stderr.write(f"  {self.address_string()} {self.command} {self.path.split('?')[0][:80]}\n")

        def _reseau_local(self) -> bool:
            try:
                ip = ipaddress.ip_address(self.client_address[0])
                return ip.is_private or ip.is_loopback or ip.is_link_local
            except ValueError:
                return False

        def _json(self, code: int, data):
            b = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def _corps(self) -> bytes:
            n = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(n) if n else b""

        def _traiter(self):
            if not self._reseau_local():
                return self._json(403, {"erreur": "réseau local uniquement"})
            chemin = self.path
            if chemin == "/atelier/identite" and self.command == "GET":
                return self._json(200, agent.identite())
            if chemin == "/atelier/appairer" and self.command == "POST":
                try:
                    d = json.loads(self._corps() or b"{}")
                    return self._json(200, {"jeton": agent.appairer(d.get("preuve", ""), d.get("poste", ""))})
                except PermissionError as e:
                    return self._json(403, {"erreur": str(e)})
                except ValueError:
                    return self._json(400, {"erreur": "requête invalide"})
            if not agent.autorise(self.headers.get("X-Atelier-Jeton", "")):
                return self._json(401, {"erreur": "poste non appairé : appairer l'atelier avec le code affiché sur le Mac"})
            if chemin == "/atelier/appareils" and self.command == "GET":
                return self._json(200, agent.appareils())
            try:
                code, type_contenu, corps = agent.relayer(self.command, chemin, self._corps(), self.headers.get("Content-Type", ""))
            except OSError as e:
                return self._json(502, {"erreur": f"Appium injoignable sur le Mac ({agent.appium}) : {e}"})
            self.send_response(code)
            self.send_header("Content-Type", type_contenu)
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

        do_GET = do_POST = do_DELETE = do_PUT = _traiter

    return Gestionnaire


def repondre_au_scan(agent: Agent, port_https: int, port_scan: int = PORT_SCAN, arret: threading.Event | None = None):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", port_scan))
    s.settimeout(1)
    while not (arret and arret.is_set()):
        try:
            data, adresse = s.recvfrom(256)
        except socket.timeout:
            continue
        except OSError:
            break
        if data.strip() == QUESTION_SCAN:
            s.sendto(json.dumps({**agent.identite(), "port": port_https}).encode(), adresse)
    s.close()


def demarrer_appium(agent: Agent):
    """Appium sur 127.0.0.1 uniquement (jamais exposé : l'agent est le seul point d'entrée réseau)."""
    if agent.appium_pret():
        print("  [ok] Appium répond :", agent.appium)
        return
    appium = shutil.which("appium")
    if not appium:
        print("  [!!] Appium absent : « npm install -g appium » puis « appium driver install xcuitest ».")
        return
    port = urllib.parse.urlsplit(agent.appium).port or 4723
    journal = open(agent.dossier / "appium.log", "ab")
    subprocess.Popen([appium, "--address", "127.0.0.1", "--port", str(port)], stdout=journal, stderr=journal,
                     stdin=subprocess.DEVNULL, start_new_session=True)
    for _ in range(40):
        if agent.appium_pret():
            print("  [ok] Appium démarré (127.0.0.1:%d, journal : %s)" % (port, agent.dossier / "appium.log"))
            return
        time.sleep(0.75)
    print("  [!!] Appium ne répond pas : voir", agent.dossier / "appium.log")


def adresses_locales() -> list[str]:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # aucune donnée envoyée : sert à connaître l'adresse de la carte réseau
        ip = s.getsockname()[0]
        s.close()
        return [ip]
    except OSError:
        return []


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description="Agent Mac de l'atelier (iPhone branchés sur ce Mac).")
    a.add_argument("--port", type=int, default=PORT)
    a.add_argument("--nom", default="")
    a.add_argument("--sans-appium", action="store_true", help="ne pas démarrer Appium")
    o = a.parse_args(argv)
    agent = Agent(nom=o.nom)
    agent.preparer_certificat()
    if not o.sans_appium:
        demarrer_appium(agent)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(agent.cert, agent.cle)
    serveur = ThreadingHTTPServer(("0.0.0.0", o.port), fabriquer_gestionnaire(agent))
    serveur.socket = ctx.wrap_socket(serveur.socket, server_side=True)
    threading.Thread(target=repondre_au_scan, args=(agent, o.port), daemon=True).start()
    app = agent.appareils()
    code = f"{agent.code[:4]}-{agent.code[4:]}"
    print(f"""
  Agent Mac de l'atelier — {agent.nom}  ({', '.join(adresses_locales()) or 'adresse inconnue'} : port {o.port})
  Appareils : {len(app['ios_physiques'])} iPhone, {len(app['ios_simulateurs'])} simulateur(s), {len(app['android'])} Android
  Empreinte : {agent.empreinte[:16]}…

  Code d'appairage (15 min) :  {code}
  Dans l'atelier : Execution Center › Appareils › « Chercher les Mac du réseau », puis saisir ce code.
  (Ctrl+C pour arrêter l'agent)
""", flush=True)
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
