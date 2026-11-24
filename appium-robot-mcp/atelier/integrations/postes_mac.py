"""Mac du réseau Wi-Fi qui prêtent leurs iPhone à l'atelier (agent_mac.py lancé sur le Mac).

Principe : Robot reste sur ce poste. Seul Appium tourne sur le Mac, derrière l'agent. L'atelier ouvre pour chaque Mac
appairé un relais local (http://127.0.0.1:<port>, jamais exposé) qui transmet les commandes Appium au Mac en HTTPS,
certificat épinglé et jeton. Un run sur un iPhone du Mac reçoit REMOTE_URL = ce relais : Xray, le graphe en direct, les
jeux de données et les secrets restent sur ce poste, comme pour un téléphone branché ici.

- scanner() : question UDP en diffusion sur le Wi-Fi, les agents répondent (nom, port, empreinte) ;
- appairer(hote, port, code) : le code affiché sur le Mac ne circule pas (preuve HMAC de l'empreinte du certificat) ;
  le jeton reçu va dans le coffre du système, l'empreinte dans ~/.atelier-postes-mac.json ;
- appareils() : iPhone, simulateurs et Android de chaque Mac (cache de quelques secondes) ;
- url_appium(udid) : URL Appium (relais) d'un appareil d'un Mac, None s'il est branché ici.
"""
from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import os
import socket
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT_SCAN = 47611
QUESTION_SCAN = b"ATELIER-AGENT?"
CACHE_S = 5.0
_verrou = threading.RLock()
_cache: dict = {"t": 0.0, "appareils": []}
_relais: dict = {}           # id du Mac -> (serveur, url)
_jetons_memoire: dict = {}   # coffre indisponible : jetons gardés en mémoire jusqu'à l'arrêt


def _fichier() -> Path:
    return Path(os.environ.get("ATELIER_POSTES_MAC") or Path.home() / ".atelier-postes-mac.json").expanduser()


def _lire() -> list[dict]:
    try:
        return json.loads(_fichier().read_text("utf-8"))
    except (OSError, ValueError):
        return []


def _ecrire(l: list[dict]):
    _fichier().write_text(json.dumps(l, ensure_ascii=False, indent=2), "utf-8")


def _nom_secret(pid: str) -> str:
    return f"poste_mac:{pid}"


def _jeton(pid: str) -> str:
    from atelier.domain import coffre

    try:
        return coffre.lire(_nom_secret(pid)) or _jetons_memoire.get(pid, "")
    except Exception:  # noqa: BLE001
        return _jetons_memoire.get(pid, "")


def _garder_jeton(pid: str, jeton: str):
    from atelier.domain import coffre

    try:
        if coffre.disponible():
            coffre.ecrire(_nom_secret(pid), jeton)
            return
    except Exception:  # noqa: BLE001
        pass
    _jetons_memoire[pid] = jeton


def preuve(code: str, empreinte: str) -> str:
    """Même calcul que l'agent : HMAC-SHA256 de l'empreinte du certificat, clé = le code affiché sur le Mac."""
    code = "".join(c for c in (code or "").upper() if c.isalnum())
    return hmac.new(code.encode(), empreinte.encode(), hashlib.sha256).hexdigest()


# =========================================================================== transport (HTTPS épinglé)
class _Connexion(http.client.HTTPSConnection):
    """HTTPS vers l'agent : le certificat est propre au Mac (auto-signé), on vérifie son empreinte, pas une autorité."""

    def __init__(self, hote, port, empreinte="", timeout=10):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        super().__init__(hote, port, timeout=timeout, context=ctx)
        self.attendue, self.empreinte = empreinte, ""

    def connect(self):
        super().connect()
        self.empreinte = hashlib.sha256(self.sock.getpeercert(binary_form=True)).hexdigest()
        if self.attendue and not hmac.compare_digest(self.empreinte, self.attendue):
            self.close()
            raise ssl.SSLError("certificat du Mac différent de celui appairé : appairer de nouveau (ou appareil usurpé)")


def _requete(poste: dict, methode: str, chemin: str, corps: bytes | None = None, entetes: dict | None = None,
             timeout: float = 10) -> tuple[int, str, bytes]:
    c = _Connexion(poste["hote"], poste["port"], poste.get("empreinte", ""), timeout)
    try:
        c.request(methode, chemin, body=corps, headers={"X-Atelier-Jeton": _jeton(poste["id"]), **(entetes or {})})
        r = c.getresponse()
        return r.status, r.getheader("Content-Type", "application/json"), r.read()
    finally:
        c.close()


def identite(hote: str, port: int = 47610) -> dict:
    """Identité d'un agent (sans appairage) : nom, empreinte. Sert à ajouter un Mac à la main par son adresse."""
    c = _Connexion(hote, port, timeout=5)
    try:
        c.request("GET", "/atelier/identite")
        d = json.loads(c.getresponse().read() or b"{}")
    finally:
        c.close()
    if d.get("agent") != "atelier-mac":
        raise ValueError(f"{hote}:{port} n'est pas un agent Mac de l'atelier.")
    if d.get("empreinte") != c.empreinte:
        raise ssl.SSLError("empreinte annoncée différente du certificat présenté")
    return {**d, "hote": hote, "port": port}


# =========================================================================== scan, appairage, liste
def scanner(delai: float = 1.5) -> list[dict]:
    """Agents qui répondent sur le Wi-Fi (diffusion UDP). Un réseau qui isole les appareils ne répond pas : ajouter
    alors le Mac par son adresse IP (affichée au lancement de l'agent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.settimeout(0.3)
    trouves: dict = {}
    try:
        s.sendto(QUESTION_SCAN, ("255.255.255.255", PORT_SCAN))
        fin = time.time() + delai
        while time.time() < fin:
            try:
                data, (ip, _) = s.recvfrom(4096)
            except socket.timeout:
                continue
            try:
                d = json.loads(data)
            except ValueError:
                continue
            if d.get("agent") == "atelier-mac":
                trouves[f"{ip}:{d.get('port')}"] = {"hote": ip, "port": int(d.get("port") or 47610), "nom": d.get("nom", ""),
                                                    "empreinte": d.get("empreinte", "")}
    except OSError:
        pass
    finally:
        s.close()
    connus = {p["empreinte"]: p for p in _lire()}
    return [{**t, "appaire": t["empreinte"] in connus, "id": (connus.get(t["empreinte"]) or {}).get("id", "")} for t in trouves.values()]


def appairer(hote: str, port: int, code: str, nom_poste: str = "") -> dict:
    """Appaire ce poste à l'agent du Mac avec le code affiché sur le Mac."""
    c = _Connexion(hote, int(port), timeout=10)
    try:
        c.connect()
        empreinte = c.empreinte
        corps = json.dumps({"preuve": preuve(code, empreinte), "poste": nom_poste or socket.gethostname()}).encode()
        c.request("POST", "/atelier/appairer", body=corps, headers={"Content-Type": "application/json"})
        r = c.getresponse()
        d = json.loads(r.read() or b"{}")
    finally:
        c.close()
    if r.status != 200 or not d.get("jeton"):
        raise PermissionError(d.get("erreur") or f"appairage refusé ({r.status})")
    ident = identite(hote, int(port))
    with _verrou:
        l = [p for p in _lire() if p.get("empreinte") != empreinte]
        pid = "mac-" + empreinte[:10]
        poste = {"id": pid, "nom": ident.get("nom") or hote, "hote": hote, "port": int(port), "empreinte": empreinte,
                 "appaire_le": time.strftime("%Y-%m-%d %H:%M")}
        _ecrire(l + [poste])
        _garder_jeton(pid, d["jeton"])
        _cache["t"] = 0.0
    return poste


def oublier(pid: str) -> dict:
    from atelier.domain import coffre

    with _verrou:
        _ecrire([p for p in _lire() if p["id"] != pid])
        _jetons_memoire.pop(pid, None)
        try:
            coffre.effacer(_nom_secret(pid))
        except Exception:  # noqa: BLE001
            pass
        r = _relais.pop(pid, None)
        if r:
            r[0].shutdown()
        _cache["t"] = 0.0
    return {"oublie": pid}


def postes() -> list[dict]:
    return _lire()


def appareils(forcer: bool = False) -> list[dict]:
    """Appareils de tous les Mac appairés : [{poste, poste_nom, udid, nom, plateforme, type, details}] ; un Mac
    injoignable est signalé par une entrée {poste, erreur}. Cache de CACHE_S secondes (l'inventaire est lu souvent)."""
    with _verrou:
        if not forcer and time.time() - _cache["t"] < CACHE_S:
            return list(_cache["appareils"])
    out = []
    for p in _lire():
        try:
            code, _, corps = _requete(p, "GET", "/atelier/appareils", timeout=4)
            if code != 200:
                raise PermissionError(json.loads(corps or b"{}").get("erreur") or f"HTTP {code}")
            d = json.loads(corps)
        except Exception as e:  # noqa: BLE001 — un Mac éteint ou hors réseau n'empêche jamais le reste
            out.append({"poste": p["id"], "poste_nom": p["nom"], "erreur": str(e)[:200]})
            continue
        base = {"poste": p["id"], "poste_nom": p["nom"], "appium": d.get("appium", False)}
        out += [{**base, "udid": x["udid"], "nom": x.get("nom", "iPhone"), "plateforme": "ios", "type": "physique",
                 "details": f"{x.get('nom', 'iPhone')} {x.get('ios', '')}".strip()} for x in d.get("ios_physiques", [])]
        out += [{**base, "udid": x["udid"], "nom": x.get("nom", ""), "plateforme": "ios", "type": "simulateur",
                 "details": f"{x.get('nom', '')} {x.get('runtime', '')}".strip()} for x in d.get("ios_simulateurs", [])]
        out += [{**base, "udid": x["udid"], "nom": x.get("details", ""), "plateforme": "android", "type": "physique / émulateur",
                 "details": x.get("details", "")} for x in d.get("android", [])]
    with _verrou:
        _cache.update(t=time.time(), appareils=out)
    return list(out)


def appareil(udid: str) -> dict | None:
    if not udid or not _lire():
        return None
    return next((a for a in appareils() if a.get("udid") == udid), None)


# =========================================================================== relais Appium local
def _gestionnaire(poste: dict):
    class Relais(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _relayer(self):
            n = int(self.headers.get("Content-Length") or 0)
            corps = self.rfile.read(n) if n else None
            try:
                code, type_contenu, rep = _requete(poste, self.command, self.path, corps,
                                                   {"Content-Type": self.headers.get("Content-Type", "application/json")}, timeout=600)
            except Exception as e:  # noqa: BLE001
                code, type_contenu = 502, "application/json"
                rep = json.dumps({"value": {"error": "unknown error", "message": f"Mac {poste['nom']} injoignable : {e}"}}).encode()
            self.send_response(code)
            self.send_header("Content-Type", type_contenu)
            self.send_header("Content-Length", str(len(rep)))
            self.end_headers()
            self.wfile.write(rep)

        do_GET = do_POST = do_DELETE = do_PUT = _relayer

    return Relais


def relais(pid: str) -> str:
    """URL Appium locale (127.0.0.1, port libre) qui mène au Mac ; démarrée à la première demande."""
    with _verrou:
        if pid in _relais:
            return _relais[pid][1]
        poste = next((p for p in _lire() if p["id"] == pid), None)
        if not poste:
            raise KeyError(f"Mac {pid} non appairé")
        srv = ThreadingHTTPServer(("127.0.0.1", 0), _gestionnaire(poste))
        threading.Thread(target=srv.serve_forever, name=f"relais-{pid}", daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        _relais[pid] = (srv, url)
        return url


def url_appium(udid: str) -> str | None:
    """URL Appium à utiliser pour cet appareil s'il est branché sur un Mac appairé (relais local), sinon None."""
    a = appareil(udid)
    return relais(a["poste"]) if a and not a.get("erreur") else None


def variables_run(variables: dict | None) -> dict:
    """Variables d'un run : un UDID d'un Mac appairé reçoit REMOTE_URL = le relais (sauf REMOTE_URL déjà imposé)."""
    v = dict(variables or {})
    udid = str(v.get("UDID") or v.get("DEVICE") or "")
    if udid and "REMOTE_URL" not in v:
        url = url_appium(udid)
        if url:
            v["REMOTE_URL"] = url
    return v
