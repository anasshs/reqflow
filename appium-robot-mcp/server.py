"""
Appium Robot MCP
================
Serveur MCP qui permet à Claude Desktop ou Cursor de :
  1. piloter un device Android / iOS via Appium, ou un navigateur web via Playwright
     (sélecteurs compatibles Robot Framework Browser library) ;
  2. relever les éléments de l'écran avec des locators prêts pour AppiumLibrary ;
  3. générer les fichiers de locators Robot Framework (Android + iOS dans un même .resource) ;
  4. lancer des suites Robot Framework et analyser output.xml ;
  5. lire / écrire des fichiers du projet de tests (limité au dossier ROBOT_PROJECT_DIR) ;
  6. remonter les résultats dans Xray Cloud en temps réel (listener xray_live_listener.py :
     plan / exécution à partir d'un ticket, EXECUTING puis PASSED/FAILED, heures de début et
     de fin, transitions Jira), ou par import API de output.xml en secours.

Compatible Claude Desktop et Cursor (transport stdio).

Principe POM respecté : le MCP produit uniquement la couche LOCATORS.
Les keywords restent génériques (pas de wrapper 1:1 par élément) et les
scénarios BDD sont écrits par-dessus le socle existant du projet.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.parse
from urllib.parse import urlparse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP, Image

APPIUM_URL = os.environ.get("APPIUM_URL", "http://127.0.0.1:4723")
PROJECT_DIR = Path(os.environ.get("ROBOT_PROJECT_DIR", Path.cwd())).expanduser().resolve()
SNAP_DIR = Path(os.environ.get("MCP_SNAPSHOT_DIR", PROJECT_DIR / ".mcp_snapshots")).expanduser()

# Interface web en écran de contrôle (Cursor ou Claude Desktop pilotent, la page affiche) :
# WEB_EVENTS_URL=http://127.0.0.1:8765/api/events
WEB_EVENTS_URL = os.environ.get("WEB_EVENTS_URL", "")

mcp = FastMCP("appium-robot")
_state: dict = {"driver": None, "platform": None}


# --------------------------------------------------------------------------- backend web
_webb_inst = None


def _webb():
    """Backend Playwright (créé à la demande)."""
    global _webb_inst
    if _webb_inst is None:
        from web_backend import WebBackend

        _webb_inst = WebBackend()
    return _webb_inst


def _is_web() -> bool:
    return _state["platform"] == "web"


def window_size() -> dict:
    """Taille de l'écran (mobile) ou du viewport (web)."""
    return _webb().window() if _is_web() else _driver().get_window_size()


def _rect_ratio(locator: str) -> dict | None:
    if _is_web():
        return _webb().rect(locator)
    r, w = _find(locator, 3).rect, _driver().get_window_size()
    return {"x": r["x"] / w["width"], "y": r["y"] / w["height"],
            "w": r["width"] / w["width"], "h": r["height"] / w["height"]}


# --------------------------------------------------------------------------- interface web
def _web_base() -> str:
    return WEB_EVENTS_URL.rsplit("/api/", 1)[0] if WEB_EVENTS_URL else ""


def _web_call(method: str, path: str, body: dict | None = None, timeout: float = 2):
    req = urllib.request.Request(_web_base() + path, method=method,
                                 data=json.dumps(body, default=str).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


EVENT_HOOK = None  # défini par l'interface web quand elle embarque le MCP dans son processus
HOOK_TYPES = {"carte_change", "exploration", "locators_change", "navigation"}


def _notify(ev: dict):
    """Envoie un événement à l'interface web, sans jamais bloquer ni faire échouer l'outil."""
    if not WEB_EVENTS_URL:
        if EVENT_HOOK and ev.get("type") in HOOK_TYPES:
            try:
                EVENT_HOOK(dict(ev))
            except Exception:
                pass
        return
    ev = {"source": "mcp", **ev}

    def send():
        try:
            _web_call("POST", "/api/events", ev)
        except Exception:
            pass
    threading.Thread(target=send, daemon=True).start()


def _show_target(locator: str, label: str):
    """Surligne l'élément visé dans l'interface web avant l'action."""
    if not WEB_EVENTS_URL:
        return
    try:
        box = _rect_ratio(locator)
        if box:
            _notify({"type": "surlignage", "label": label, **box})
            time.sleep(0.7)
    except Exception:
        pass


def _action_done(nom: str, args: dict):
    _notify({"type": "outil", "nom": nom, "args": args})
    _notify({"type": "ecran_change"})


# --------------------------------------------------------------------------- carte de l'app
MAP_PASSIF = os.environ.get("MAP_PASSIVE", "1") != "0"


def _carte():
    import app_map

    return app_map


def _carte_active() -> bool:
    try:
        return MAP_PASSIF and bool(_state["platform"]) and bool(_carte().app_courante())
    except Exception:
        return False


def _contexte() -> str:
    try:
        if _is_web():
            return _carte().motif_url(_webb().info()["url"])
        if _state["platform"] == "android":
            return _driver().current_activity or ""
    except Exception:
        pass
    return ""


def _attendre_stable(timeout: float = 4.0) -> list[dict]:
    """Attend que l'écran ne bouge plus (fin d'animation / de chargement) avant de l'identifier."""
    m = _carte()
    els = _current_elements(150)
    prev, t0 = None, time.time()
    while time.time() - t0 < timeout:
        sig = m.signature(els)
        if sig == prev:
            return els
        prev = sig
        time.sleep(0.6)
        els = _current_elements(150)
    return els


def _observer(els: list[dict] | None = None, test_key: str | None = None) -> dict | None:
    if not _carte_active():
        return None
    m = _carte()
    obs = m.observer(els if els is not None else _current_elements(150), _state["platform"], _contexte(),
                     build=m.config_app().get("build", ""), vignette_cb=screenshot_png, test_key=test_key)
    if obs.get("nouveau"):
        _notify({"type": "carte_change", "ecran": obs})
    return obs


def _avec_carte(action: dict, fn):
    """Exécute une action et enregistre la transition observée (si l'écran change)."""
    if not _carte_active():
        return fn()
    try:
        avant = _observer()
    except Exception:
        avant = None
    t0 = time.time()
    res = fn()
    try:
        apres = _observer(_attendre_stable())
        if avant and apres and avant["id"] != apres["id"]:
            plat = _state["platform"]
            action["cle"] = _carte().cle_pour_locator(avant["id"], action.get("locator", ""), plat)
            _carte().enregistrer_transition(avant["id"], apres["id"], plat, action,
                                            duree_ms=int((time.time() - t0) * 1000))
            _notify({"type": "carte_change", "transition": [avant["id"], apres["id"]]})
    except Exception:
        pass
    return res


def _click_raw(locator: str, timeout: float = 5):
    if _is_web():
        _webb().click(locator, timeout)
    else:
        _find(locator, timeout).click()


def _back_raw():
    _webb().back() if _is_web() else _driver().back()


def _present(locator: str) -> bool:
    try:
        if _is_web():
            return _webb().check(locator)["nb_trouves"] > 0
        by, value = _by(locator)
        return len(_driver().find_elements(by, value)) > 0
    except Exception:
        return False


def _rejouer(t: dict) -> bool:
    a, plat, m = t["action"], _state["platform"], _carte()
    try:
        if a["type"] == "press_back":
            _back_raw()
        elif a["type"] == "open_url":
            _webb().goto(a["url"])
        elif a["type"] == "swipe":
            swipe(a.get("direction", "up"))
        else:
            candidats = []
            if a.get("cle"):
                try:
                    candidats = (m.ecran(t["de"]).get("elements", {}).get(a["cle"], {}).get("locators", {})
                                 .get(plat) or [])
                except KeyError:
                    pass
            candidats = list(dict.fromkeys(candidats + ([a["locator"]] if a.get("locator") else [])))
            loc = next((c for c in candidats if _present(c)), None)
            if not loc:
                return False
            _show_target(loc, "navigation")
            _click_raw(loc)
        return True
    except Exception:
        return False


def _relancer_app():
    cfg = _carte().config_app()
    plat = _state["platform"]
    if plat == "web":
        if cfg.get("web", {}).get("url"):
            _webb().goto(cfg["web"]["url"])
        return
    ident = cfg.get(plat, {}).get("app_package" if plat == "android" else "bundle_id")
    if ident:
        try:
            _driver().terminate_app(ident)
        except Exception:
            pass
        _driver().activate_app(ident)
        time.sleep(2)


def _aller(cible_id: str, max_essais: int = 3) -> dict:
    m, plat = _carte(), _state["platform"]
    cur = None
    for essai in range(max_essais):
        cur = _observer(_attendre_stable(3))
        if not cur:
            return {"arrive": False, "raison": "Carte inactive (aucune application ou session)."}
        if cur["id"] == cible_id:
            return {"arrive": True, "ecran": cur, "essais": essai + 1}
        trajet = m.chemin(cur["id"], cible_id, plat)
        if trajet is None:
            for _ in range(2):  # rattrapage : retour puis nouvel essai de calcul
                _back_raw()
                cur = _observer(_attendre_stable(3))
                if cur and m.chemin(cur["id"], cible_id, plat) is not None:
                    break
            else:
                _relancer_app()
            continue
        for t in trajet:
            _notify({"type": "navigation", "transition": t["id"], "de": t["de"], "vers": t["vers"]})
            ok = _rejouer(t)
            arrive = _observer(_attendre_stable(4))
            bon = ok and arrive and arrive["id"] == t["vers"]
            m.noter(t["id"], bool(bon))
            if not bon:
                break
        else:
            return {"arrive": True, "ecran": _observer(), "essais": essai + 1}
    return {"arrive": False, "raison": "Chemin non rejouable pour l'instant", "ecran_courant": cur}


_EXPLO = {"stop": threading.Event(), "en_cours": False}


def _explorer(max_ecrans: int = 25, profondeur: int = 3, duree_max_s: int = 900) -> dict:
    """Parcours en largeur : touche les éléments cliquables (hors liste rouge), enregistre chaque écran
    et chaque transition, puis revient. Ne saisit jamais de texte, n'active jamais de case."""
    m, plat = _carte(), _state["platform"]
    if not _carte_active():
        raise RuntimeError("Ouvre une session et choisis une application avant d'explorer.")
    _EXPLO["stop"].clear()
    _EXPLO["en_cours"] = True
    t0 = time.time()
    depart = _observer(_attendre_stable())
    hote = urlparse(_webb().info()["url"]).netloc if _is_web() else ""
    file, vus = [(depart["id"], 0)], {depart["id"]}
    bilan = {"ecrans_visites": 1, "nouveaux": 0, "transitions": 0, "ignores_liste_rouge": 0, "journal": []}
    try:
        while file and not _EXPLO["stop"].is_set() and time.time() - t0 < duree_max_s and len(vus) <= max_ecrans:
            eid, prof = file.pop(0)
            if prof >= profondeur or not _aller(eid)["arrive"]:
                continue
            for t in m.transitions():  # poursuit aussi vers les écrans déjà connus depuis celui-ci
                if t["de"] == eid and t["plateforme"] == plat and not t.get("interdite") and t["vers"] not in vus:
                    vus.add(t["vers"])
                    file.append((t["vers"], prof + 1))
            deja = m.actions_depuis(eid, plat)
            candidats = []
            for el in _current_elements(150):
                if el.get("type") not in ("bouton", "lien", "element", "liste"):
                    continue
                if m.interdit(el):
                    bilan["ignores_liste_rouge"] += 1
                    continue
                if el["key"] not in deja and el["locators"][0] not in deja:
                    candidats.append(el)
            for el in candidats[:15]:
                if _EXPLO["stop"].is_set() or time.time() - t0 > duree_max_s or len(vus) > max_ecrans:
                    break
                if not _aller(eid)["arrive"]:
                    break
                loc = el["locators"][0]
                try:
                    _show_target(loc, "exploration")
                    _click_raw(loc, 3)
                except Exception:
                    m.marquer_essaye(eid, plat, el["key"])
                    continue
                if _is_web() and urlparse(_webb().info()["url"]).netloc != hote:  # lien externe
                    _back_raw()
                    m.marquer_essaye(eid, plat, el["key"])
                    continue
                obs = _observer(_attendre_stable())
                if obs["id"] == eid:
                    m.marquer_essaye(eid, plat, el["key"])
                    continue
                m.enregistrer_transition(eid, obs["id"], plat, {"type": "tap", "cle": el["key"], "locator": loc,
                                                                "libelle": el.get("libelle", "")}, source="exploration")
                bilan["transitions"] += 1
                bilan["nouveaux"] += 1 if obs["nouveau"] else 0
                if obs["id"] not in vus:
                    vus.add(obs["id"])
                    file.append((obs["id"], prof + 1))
                msg = f"{el.get('libelle') or el['key']} → {obs.get('nom') or obs.get('titre') or obs['id']}"
                bilan["journal"].append(msg)
                _notify({"type": "exploration", "message": msg, "nb_ecrans": len(vus), "nouveau": obs["nouveau"]})
    finally:
        _EXPLO["en_cours"] = False
        bilan["ecrans_visites"] = len(vus)
        bilan["duree_s"] = int(time.time() - t0)
        bilan["arret"] = "demandé" if _EXPLO["stop"].is_set() else "terminé"
        _notify({"type": "exploration", "fin": True, "bilan": {k: v for k, v in bilan.items() if k != "journal"}})
    return bilan


# --------------------------------------------------------------------------- utilitaires
def _driver():
    if _state["driver"] is None:
        raise RuntimeError("Aucune session Appium active. Appelle d'abord start_session.")
    return _state["driver"]


def _safe_path(rel: str) -> Path:
    """Empêche toute lecture/écriture hors du projet de tests."""
    p = (PROJECT_DIR / rel).resolve()
    if p != PROJECT_DIR and PROJECT_DIR not in p.parents:
        raise ValueError(f"Chemin hors du projet interdit : {rel}")
    return p


def _slug(text: str, max_len: int = 40) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text[:max_len] or "element"


def _xq(value: str) -> str:
    """Quote XPath sûre (gère les apostrophes, fréquentes en français)."""
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    return "concat(" + ", \"'\", ".join(f"'{p}'" for p in parts) + ")"


def _by(locator: str):
    """Convertit un locator au format AppiumLibrary (id=..., xpath=...) en (By, valeur)."""
    from appium.webdriver.common.appiumby import AppiumBy

    strategies = {
        "id": AppiumBy.ID,
        "accessibility_id": AppiumBy.ACCESSIBILITY_ID,
        "xpath": AppiumBy.XPATH,
        "class": AppiumBy.CLASS_NAME,
        "name": AppiumBy.NAME,
        "android": AppiumBy.ANDROID_UIAUTOMATOR,
        "nsp": AppiumBy.IOS_PREDICATE,
        "chain": AppiumBy.IOS_CLASS_CHAIN,
    }
    if locator.startswith(("//", "(")):
        return AppiumBy.XPATH, locator
    strat, sep, value = locator.partition("=")
    if sep and strat.strip() in strategies:
        return strategies[strat.strip()], value
    return AppiumBy.ID, locator


def _find(locator: str, timeout: float = 10):
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    by, value = _by(locator)
    return WebDriverWait(_driver(), timeout).until(EC.presence_of_element_located((by, value)))


def _abs_xpath(node, parents) -> str:
    steps = []
    while node in parents:
        parent = parents[node]
        same = [c for c in parent if c.tag == node.tag]
        steps.append(f"{node.tag}[{same.index(node) + 1}]")
        node = parent
    return "//" + "/".join(reversed(steps)) if steps else "//*"


def _kind(cls: str) -> str:
    c = cls.lower()
    if "edittext" in c or "textfield" in c or "securetextfield" in c:
        return "champ"
    if "switch" in c or "checkbox" in c or "radio" in c:
        return "case"
    if "statictext" in c or c.endswith("textview"):
        return "texte"
    if "image" in c:
        return "image"
    return "bouton"


def _parse_elements(source: str, platform: str) -> list[dict]:
    root = ET.fromstring(source.encode("utf-8"))
    parents = {c: p for p in root.iter() for c in p}
    elements: list[dict] = []

    for node in root.iter():
        a = node.attrib
        locs: list[str] = []
        if platform == "android":
            if a.get("displayed", "true") == "false":
                continue
            rid, text, desc = a.get("resource-id", ""), a.get("text", ""), a.get("content-desc", "")
            clickable = a.get("clickable") == "true"
            cls = a.get("class", node.tag)
            if not (rid or text or desc or clickable):
                continue
            if rid:
                locs.append(f"id={rid}")
            if desc:
                locs.append(f"accessibility_id={desc}")
            if text:
                locs.append(f"xpath=//*[@text={_xq(text)}]")
            enfant = ""
            if clickable and not (rid or text or desc):  # bouton Compose : le libellé est porté par un enfant
                enfant = next((n.attrib.get("text") or n.attrib.get("content-desc") for n in node.iter()
                               if n is not node and (n.attrib.get("text") or n.attrib.get("content-desc"))), "")
                if enfant:
                    locs.append(f"xpath=//*[@text={_xq(enfant)}]/ancestor-or-self::*[@clickable='true'][1]")
            label = text or desc or enfant or rid.split("/")[-1]
            base = rid.split("/")[-1] if rid else (desc or text or enfant)
            bounds = a.get("bounds", "")
            nums = [int(n) for n in re.findall(r"-?\d+", bounds)]
            rect = [nums[0], nums[1], nums[2] - nums[0], nums[3] - nums[1]] if len(nums) == 4 else None
        else:
            if a.get("visible") == "false":
                continue
            name, label_attr = a.get("name", ""), a.get("label", "")
            cls = a.get("type", node.tag)
            interactive = any(t in cls for t in ("Button", "TextField", "Switch", "Cell", "Link"))
            if cls in ("XCUIElementTypeApplication", "XCUIElementTypeWindow"):
                continue
            if not (name or label_attr or interactive):
                continue
            if name:
                locs.append(f"accessibility_id={name}")
            if label_attr and label_attr != name:
                locs.append(f'nsp=label == "{label_attr}"')
            if label_attr:
                locs.append(f'chain=**/{cls}[`label == "{label_attr}"`]')
            label = label_attr or name
            base = name or label_attr
            bounds = f"[{a.get('x')},{a.get('y')}][{a.get('width')}x{a.get('height')}]"
            try:
                rect = [float(a.get(k)) for k in ("x", "y", "width", "height")]
            except (TypeError, ValueError):
                rect = None

        if not locs:
            locs.append(f"xpath={_abs_xpath(node, parents)}")
        kind = _kind(cls)
        elements.append({
            "key": f"{kind}_{_slug(base or cls.split('.')[-1])}",
            "type": kind,
            "classe": cls.split(".")[-1],
            "libelle": label,
            "locators": locs,
            "bounds": bounds,
            "rect": rect,
        })

    if platform == "android":
        _android_sans_ids(elements)
    # Unicité des clés + signalement des locators principaux ambigus
    seen: dict[str, int] = {}
    primary_count: dict[str, int] = {}
    for e in elements:
        primary_count[e["locators"][0]] = primary_count.get(e["locators"][0], 0) + 1
    for e in elements:
        n = seen.get(e["key"], 0)
        seen[e["key"]] = n + 1
        if n:
            e["key"] = f"{e['key']}_{n + 1}"
        e["locator_unique"] = primary_count[e["locators"][0]] == 1
    return elements


def _uia(text: str) -> str:
    return 'android=new UiSelector().text("' + text.replace("\\", "\\\\").replace('"', '\\"') + '")'


def _android_sans_ids(elements: list[dict]):
    """Jetpack Compose sans testTag : pas de resource-id. On privilégie
    - pour un bouton / texte : UiSelector().text(...) (plus rapide et lisible qu'un XPath) ;
    - pour un champ : locator RELATIF au libellé qui le précède (sa valeur change à la saisie)."""
    dernier_libelle = ""
    for e in elements:
        locs = e["locators"]
        a_id = any(l.startswith(("id=", "accessibility_id=")) for l in locs)
        libelle = e.get("libelle") or ""
        statique = libelle and not re.search(r"\d[\d\s.,]*\d|•|@", libelle) and len(libelle) <= 40
        if e["type"] == "champ" and not a_id:
            texte = [l for l in locs if l.startswith("xpath=//*[@text")]
            autres = [l for l in locs if l not in texte]
            rel = [f"xpath=//*[@text={_xq(dernier_libelle)}]/following::android.widget.EditText[1]"] if dernier_libelle else []
            e["locators"] = rel + autres + texte or locs
            if dernier_libelle:
                e["key"] = f"champ_{_slug(dernier_libelle)}"
        elif not a_id and libelle and statique and e["type"] != "champ":
            e["locators"] = [_uia(libelle)] + locs
        if e["type"] == "texte" and statique:
            dernier_libelle = libelle


def _robot_escape(value: str) -> str:
    value = value.replace("\\", "\\\\")
    return re.sub(r" {2,}", lambda m: " " + "\\ " * (len(m.group()) - 1), value)


# --------------------------------------------------------------------------- devices & session
@mcp.tool()
def list_devices() -> dict:
    """Liste les devices Android (adb) et iOS (simulateurs démarrés + devices physiques) connectés."""
    out: dict = {"android": [], "ios_simulateurs": [], "ios_physiques": []}
    if shutil.which("adb"):
        r = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True, timeout=20)
        for line in r.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) > 1 and parts[1] == "device":
                out["android"].append({"udid": parts[0], "details": " ".join(parts[2:])})
    if shutil.which("xcrun"):
        r = subprocess.run(["xcrun", "simctl", "list", "devices", "booted", "-j"],
                           capture_output=True, text=True, timeout=30)
        for runtime, devs in json.loads(r.stdout or "{}").get("devices", {}).items():
            for d in devs:
                if d.get("state") == "Booted":
                    out["ios_simulateurs"].append(
                        {"nom": d["name"], "udid": d["udid"], "runtime": runtime.split(".")[-1]})
    if shutil.which("idevice_id"):
        r = subprocess.run(["idevice_id", "-l"], capture_output=True, text=True, timeout=20)
        out["ios_physiques"] = [u for u in r.stdout.split() if u]
    return out


@mcp.tool()
def start_session(platform: str, udid: str = "", app: str = "", app_package: str = "",
                  app_activity: str = "", bundle_id: str = "", no_reset: bool = True,
                  extra_caps: dict | None = None, url: str = "", browser: str = "chromium",
                  headless: bool = True) -> dict:
    """Ouvre une session : 'android' / 'ios' (Appium) ou 'web' (navigateur Playwright, mêmes
    sélecteurs que Robot Framework Browser library).
    Web : url de départ, browser 'chromium' | 'firefox' | 'webkit', headless (False = fenêtre visible).
    Mobile : udid : device ciblé (voir list_devices).
    app : chemin .apk/.ipa (optionnel si l'app est déjà installée).
    Android : app_package / app_activity. iOS : bundle_id.
    extra_caps : capabilities supplémentaires (ex. {'appium:automationName': 'UiAutomator2'})."""
    if _state["platform"]:
        stop_session()
    p = platform.lower().strip()
    if p == "web":
        info = _webb().start(url, browser, headless)
        _state["platform"] = "web"
        _notify({"type": "session", "etat": "ouverte", "platform": "web"})
        return {"statut": "session ouverte", "platform": "web", **info}

    from appium import webdriver
    from appium.options.android import UiAutomator2Options
    from appium.options.ios import XCUITestOptions

    if p == "android":
        opts = UiAutomator2Options()
        if app_package:
            opts.app_package = app_package
        if app_activity:
            opts.app_activity = app_activity
    elif p == "ios":
        opts = XCUITestOptions()
        if bundle_id:
            opts.bundle_id = bundle_id
    else:
        raise ValueError("platform doit valoir 'android', 'ios' ou 'web'")
    if udid:
        opts.udid = udid
    if app:
        opts.app = app
    opts.no_reset = no_reset
    opts.new_command_timeout = 900
    for k, v in (extra_caps or {}).items():
        opts.set_capability(k, v)

    _state["driver"] = webdriver.Remote(APPIUM_URL, options=opts)
    _state["platform"] = p
    _notify({"type": "session", "etat": "ouverte", "platform": p, "udid": udid})
    return {"statut": "session ouverte", "platform": p, "session_id": _state["driver"].session_id}


@mcp.tool()
def stop_session() -> str:
    """Ferme la session courante (mobile ou web)."""
    if _is_web():
        _webb().stop()
        _state["platform"] = None
        _notify({"type": "session", "etat": "fermee"})
        return "Session fermée."
    if _state["driver"] is None:
        return "Aucune session active."
    try:
        _state["driver"].quit()
    finally:
        _state["driver"], _state["platform"] = None, None
    _notify({"type": "session", "etat": "fermee"})
    return "Session fermée."


# --------------------------------------------------------------------------- lecture de l'écran
@mcp.tool()
def screenshot() -> Image:
    """Capture d'écran du device ou de la page web (pour vérifier visuellement l'écran courant)."""
    return Image(data=screenshot_png(), format="png")


def screenshot_png() -> bytes:
    return _webb().screenshot() if _is_web() else _driver().get_screenshot_as_png()


@mcp.tool()
def get_screen_elements(max_elements: int = 120) -> dict:
    """Liste les éléments significatifs de l'écran avec des locators AppiumLibrary
    classés du plus robuste au plus fragile. 'locator_unique' = False signale un
    locator principal ambigu à renforcer."""
    elements = _current_elements(max_elements)
    out = {"platform": _state["platform"], "nb_elements": len(elements), "elements": elements}
    if _is_web():
        out.update(_webb().info())
    return out


def _current_elements(max_elements: int = 120) -> list[dict]:
    if _is_web():
        els = _webb().elements(max_elements)
        seen: dict = {}
        for e in els:  # clés uniques
            n = seen.get(e["key"], 0)
            seen[e["key"]] = n + 1
            if n:
                e["key"] = f"{e['key']}_{n + 1}"
        return els
    return _parse_elements(_driver().page_source, _state["platform"])[:max_elements]


@mcp.tool()
def element_at(x_ratio: float, y_ratio: float) -> dict:
    """Élément situé à un point de l'écran (coordonnées en proportion 0-1 de la largeur et de la
    hauteur), avec ses locators. Sert à « montrer » un élément en touchant l'image de l'écran."""
    if _is_web():
        el = _webb().element_at(x_ratio, y_ratio)
        if not el:
            raise LookupError("Aucun élément à cet endroit.")
        return el
    w = _driver().get_window_size()
    x, y = x_ratio * w["width"], y_ratio * w["height"]
    hits = [e for e in _parse_elements(_driver().page_source, _state["platform"])
            if e.get("rect") and e["rect"][0] <= x <= e["rect"][0] + e["rect"][2]
            and e["rect"][1] <= y <= e["rect"][1] + e["rect"][3] and e["rect"][2] * e["rect"][3] > 0]
    if not hits:
        raise LookupError("Aucun élément à cet endroit.")
    # le plus petit élément qui contient le point, en privilégiant ceux qui ont un id
    hits.sort(key=lambda e: (not e["locators"][0].startswith(("id=", "accessibility_id=")),
                             e["rect"][2] * e["rect"][3]))
    return hits[0]


@mcp.tool()
def open_url(url: str) -> dict:
    """Web uniquement : ouvre une URL dans la session navigateur."""
    if not _is_web():
        raise RuntimeError("open_url est réservé aux sessions web.")
    info = _avec_carte({"type": "open_url", "url": url}, lambda: _webb().goto(url))
    _action_done("open_url", {"url": url})
    return info


@mcp.tool()
def get_page_source(max_chars: int = 60000) -> str:
    """Arbre brut de l'écran (XML mobile ou HTML web, tronqué), si get_screen_elements ne suffit pas."""
    return _webb().source(max_chars) if _is_web() else _driver().page_source[:max_chars]


@mcp.tool()
def check_locator(locator: str) -> dict:
    """Vérifie un locator : nombre d'éléments trouvés + texte/visibilité du premier."""
    _show_target(locator, "vérification")
    if _is_web():
        return _webb().check(locator)
    by, value = _by(locator)
    found = _driver().find_elements(by, value)
    info: dict = {"locator": locator, "nb_trouves": len(found)}
    if found:
        info.update({"texte": found[0].text, "affiche": found[0].is_displayed()})
    return info


# --------------------------------------------------------------------------- actions
@mcp.tool()
def tap(locator: str, timeout: float = 10) -> str:
    """Touche / clique un élément. Mobile : locator AppiumLibrary (id=..., accessibility_id=...,
    xpath=...). Web : sélecteur Browser library (data-testid=..., id=..., css=..., text="...")."""
    _show_target(locator, "tap")
    _avec_carte({"type": "tap", "locator": locator}, lambda: _click_raw(locator, timeout))
    _action_done("tap", {"locator": locator})
    return f"Tap effectué sur {locator}"


@mcp.tool()
def type_text(locator: str, text: str, clear: bool = True, hide_keyboard: bool = True) -> str:
    """Saisit du texte dans un champ (mobile ou web)."""
    _show_target(locator, "saisie")

    def saisir():
        if _is_web():
            _webb().fill(locator, text, clear)
            return
        el = _find(locator)
        if clear:
            el.clear()
        el.send_keys(text)
        if hide_keyboard:
            try:
                _driver().hide_keyboard()
            except Exception:
                pass
    _avec_carte({"type": "type_text", "locator": locator}, saisir)  # la valeur saisie n'est jamais stockée
    _action_done("type_text", {"locator": locator, "text": text})
    return f"Saisie effectuée dans {locator}"


@mcp.tool()
def swipe(direction: str = "up", ratio: float = 0.6, duration_ms: int = 600) -> str:
    """Swipe plein écran (mobile) ou défilement (web). direction : up (vers le bas du contenu),
    down, left, right."""
    if _is_web():
        _avec_carte({"type": "swipe", "direction": direction}, lambda: _webb().scroll(direction, ratio))
        _action_done("swipe", {"direction": direction})
        return f"Défilement {direction} effectué"
    size = _driver().get_window_size()
    w, h = size["width"], size["height"]
    cx, cy, dx, dy = w // 2, h // 2, int(w * ratio / 2), int(h * ratio / 2)
    moves = {"up": (cx, cy + dy, cx, cy - dy), "down": (cx, cy - dy, cx, cy + dy),
             "left": (cx + dx, cy, cx - dx, cy), "right": (cx - dx, cy, cx + dx, cy)}
    if direction not in moves:
        raise ValueError("direction : up, down, left ou right")
    _avec_carte({"type": "swipe", "direction": direction}, lambda: _driver().swipe(*moves[direction], duration_ms))
    _action_done("swipe", {"direction": direction})
    return f"Swipe {direction} effectué"


@mcp.tool()
def press_back() -> str:
    """Retour : bouton retour Android, page précédente en web. Sur iOS, toucher le bouton de navigation."""
    _avec_carte({"type": "press_back"}, _back_raw)
    _action_done("press_back", {})
    return "Retour effectué"


@mcp.tool()
def wait_for(locator: str, timeout: float = 15) -> str:
    """Attend qu'un élément soit présent à l'écran."""
    _show_target(locator, "attente")
    if _is_web():
        _webb().wait(locator, timeout)
    else:
        _find(locator, timeout)
    return f"{locator} présent"


# --------------------------------------------------------------------------- génération POM
@mcp.tool()
def capture_screen_locators(screen_name: str, selection: dict | None = None) -> dict:
    """Enregistre les locators de l'écran courant pour la plateforme de la session
    (correspond aux sous-tâches 'Locators Android' / 'Locators iOS').
    selection : {cle_metier: locator} pour ne garder et nommer que les éléments utiles.
    Sans selection, tous les éléments relevés sont gardés avec leur locator principal."""
    platform = _state["platform"]
    if selection:
        locators = dict(selection)
    else:
        locators = {e["key"]: e["locators"][0] for e in _current_elements(200)}
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAP_DIR / f"{_slug(screen_name)}_{platform}.json"
    path.write_text(json.dumps({"ecran": screen_name, "platform": platform,
                                "date": datetime.now().isoformat(timespec="seconds"),
                                "locators": locators}, ensure_ascii=False, indent=2), "utf-8")
    _notify({"type": "locators_change"})
    _notify({"type": "outil", "nom": "capture_screen_locators", "args": {"ecran": screen_name}})
    return {"fichier": str(path), "nb_locators": len(locators)}


@mcp.tool()
def generate_locators_resource(screen_name: str, output_dir: str = "resources/locators",
                               overwrite: bool = False) -> dict:
    """Fusionne les captures d'un écran en un fichier .resource Robot.
    Mobile : &{LOC_<ECRAN>_ANDROID} et &{LOC_<ECRAN>_IOS}, mêmes clés métier sur les deux
    plateformes (clés manquantes signalées). Web : &{LOC_<ECRAN>_WEB} (sélecteurs Browser library)."""
    slug = _slug(screen_name)
    var = slug.upper()
    data = {}
    for p in ("android", "ios", "web"):
        f = SNAP_DIR / f"{slug}_{p}.json"
        data[p] = json.loads(f.read_text("utf-8"))["locators"] if f.exists() else {}
    if not any(data.values()):
        raise RuntimeError("Aucune capture trouvée : lance capture_screen_locators d'abord.")
    mobile = bool(data["android"] or data["ios"])
    platforms = (["android", "ios"] if mobile else []) + (["web"] if data["web"] else [])
    all_keys = list(dict.fromkeys([*data["android"], *data["ios"]]))
    lines = ["*** Settings ***",
             f"Documentation    Locators de l'écran « {screen_name} » ({' + '.join(p.capitalize() for p in platforms)}).",
             f"...              Générés par appium-robot MCP le {datetime.now():%d/%m/%Y} — à relire avant commit.",
             "", "*** Variables ***"]
    for p in platforms:
        missing = [k for k in all_keys if k not in data[p]] if p != "web" else []
        if missing:
            lines.append(f"# TODO {p} : clés à relever -> {', '.join(missing)}")
        entries = [f"{k}={_robot_escape(v)}" for k, v in data[p].items()]
        if not entries:
            lines.append(f"&{{LOC_{var}_{p.upper()}}}")
        else:
            lines.append(f"&{{LOC_{var}_{p.upper()}}}    {entries[0]}")
            lines += [f"...    {e}" for e in entries[1:]]
        lines.append("")

    target = _safe_path(f"{output_dir}/{slug}.resource")
    if target.exists() and not overwrite:
        raise FileExistsError(f"{target} existe déjà (overwrite=True pour remplacer).")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), "utf-8")
    _notify({"type": "locators_change"})
    _notify({"type": "outil", "nom": "generate_locators_resource", "args": {"fichier": str(target)}})
    return {"fichier": str(target), "cles": all_keys or list(data["web"]),
            "manquants_android": [k for k in all_keys if k not in data["android"]] if mobile else [],
            "manquants_ios": [k for k in all_keys if k not in data["ios"]] if mobile else []}


# --------------------------------------------------------------------------- validation des steps
@mcp.tool()
def propose_step(gherkin: str, keyword: str = "", locators: list[str] | None = None,
                 commentaire: str = "", attendre_validation: bool = True,
                 delai_max_s: int = 600) -> dict:
    """Propose un step Gherkin construit à partir de l'action faite sur le device.
    Avec l'interface web ouverte (WEB_EVENTS_URL), le step s'affiche dans « Scénario en
    construction » et l'outil attend que l'utilisateur clique Valider ou Corriger.
    Retour : decision ('validé', 'corrigé', 'refusé' ou 'sans validation') + correction éventuelle.
    En cas de correction, l'appliquer avant de passer au step suivant."""
    step = {"gherkin": gherkin, "keyword": keyword, "locators": locators or [],
            "commentaire": commentaire}
    if not WEB_EVENTS_URL:
        return {"decision": "sans validation", "raison": "interface web non configurée"}
    try:
        pid = _web_call("POST", "/api/externe/step", step)["id"]
    except Exception as e:
        return {"decision": "sans validation", "raison": f"interface web injoignable : {e}"}
    if not attendre_validation:
        return {"decision": "proposé", "id": pid}
    fin = time.time() + delai_max_s
    while time.time() < fin:
        try:
            r = _web_call("GET", f"/api/externe/reponse/{pid}")
        except Exception:
            r = {}
        if r.get("decision"):
            return {"decision": r["decision"], "correction": r.get("texte", "")}
        time.sleep(1)
    return {"decision": "sans réponse", "raison": f"pas de validation en {delai_max_s} s"}


# --------------------------------------------------------------------------- projet Robot
@mcp.tool()
def list_project_files(pattern: str = "**/*.robot") -> list[str]:
    """Liste les fichiers du projet de tests (ex. '**/*.resource', 'tests/**/*.robot')."""
    return sorted(str(p.relative_to(PROJECT_DIR)) for p in PROJECT_DIR.glob(pattern)
                  if ".mcp_snapshots" not in p.parts)[:500]


@mcp.tool()
def read_project_file(path: str) -> str:
    """Lit un fichier du projet (keywords existants, steps, suites) pour réutiliser le socle."""
    return _safe_path(path).read_text("utf-8")


@mcp.tool()
def write_project_file(path: str, content: str, overwrite: bool = False) -> str:
    """Écrit un fichier dans le projet (nouvelle suite, steps…). Refuse d'écraser sans overwrite=True."""
    target = _safe_path(path)
    if target.exists() and not overwrite:
        raise FileExistsError(f"{path} existe déjà (overwrite=True pour remplacer).")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, "utf-8")
    _notify({"type": "outil", "nom": "write_project_file", "args": {"path": path}})
    return f"Écrit : {target}"


def _deepest_fail(item, path: list[str]) -> list[str]:
    for child in getattr(item, "body", []) or []:
        if getattr(child, "status", None) == "FAIL":
            name = getattr(child, "name", None) or type(child).__name__
            return _deepest_fail(child, path + [str(name)])
    return path


@mcp.tool()
def parse_robot_output(output_xml: str = "results/mcp/output.xml") -> dict:
    """Résumé d'un output.xml : stats + tests en échec avec message et keyword fautif."""
    from robot.api import ExecutionResult

    result = ExecutionResult(str(_safe_path(output_xml)))
    total = result.statistics.total
    failures = []
    for test in result.suite.all_tests:
        if test.status == "FAIL":
            failures.append({"test": test.name, "tags": list(test.tags),
                             "message": test.message[:800],
                             "keyword_en_echec": " > ".join(_deepest_fail(test, []))})
    return {"passes": total.passed, "echecs": total.failed,
            "skips": getattr(total, "skipped", 0), "tests_en_echec": failures}


@mcp.tool()
def run_robot(target: str, include_tags: list[str] | None = None,
              exclude_tags: list[str] | None = None, variables: dict | None = None,
              dry_run: bool = False, output_dir: str = "results/mcp",
              xray_ticket: str = "", xray_mode: str = "live",
              exec_summary: str = "", plan_summary: str = "",
              test_environments: list[str] | None = None,
              jira_transition_start: str = "", jira_transition_end: str = "",
              jira_transition_end_if_fail: str = "",
              attach_screenshots: bool = True, jdd_env: str = "",
              jdd_jeux: list[str] | None = None, events_url: str = "",
              relancer_echecs: bool = False, cartographie: bool = False, timeout_s: int = 3600) -> dict:
    """Lance une suite ou un dossier Robot Framework du projet puis renvoie le bilan.
    variables : ex. {'PLATFORM': 'android', 'DEVICE': 'emulator-5554'} (sélection du device).

    xray_ticket : une seule clé Jira, dont le type est détecté automatiquement :
      - Test Plan       -> crée une nouvelle exécution et l'ajoute au plan ;
      - Test Execution  -> met à jour cette exécution (tests manquants ajoutés) ;
      - autre ticket (US, epic…) ou clé projet seule (ex. TAM) -> crée un plan + une exécution.
    xray_mode :
      - 'live' (défaut) : listener du MCP, test run en EXECUTING au démarrage de chaque test,
        PASSED / FAILED à la fin, heures de début et de fin, message d'échec et captures ;
      - 'listener_projet' : listener du projet (ROBOT_XRAY_LISTENER) avec la clé d'exécution ;
      - 'aucun'.
    test_environments : environnements Xray de l'exécution (défaut : valeur de PLATFORM).
    jira_transition_start / _end / _end_if_fail : transition Jira (nom de la transition ou du
      statut cible) appliquée au ticket d'exécution au début du run, à la fin, ou à la fin
      s'il y a au moins un échec.
    jdd_env / jdd_jeux : environnement et jeux de données à injecter (ex. 'recette',
      ['VIREMENT_STANDARD']). Les prérequis sont vérifiés AVANT le run : s'il manque des
      données, le run n'est pas lancé et le bilan indique « bloqué données ». Chaque jeu
      devient un dictionnaire &{JDD_<NOM>} utilisable dans « Initialiser Le Test ».
    events_url : URL qui reçoit les événements du run en direct (interface web).
    cartographie : enrichit la carte de l'application pendant le run (écrans et transitions des
      tests mobiles, test Xray qui passe par chaque écran). Ralentit un peu chaque action.
    relancer_echecs : rejoue uniquement les tests en échec du run précédent (même output_dir).
      Pour mettre à jour la même exécution Xray, passer sa clé dans xray_ticket.
    La session Appium du MCP est fermée avant le run pour libérer le device."""
    if _state["platform"]:
        stop_session()
    events_url = events_url or WEB_EVENTS_URL
    if events_url and WEB_EVENTS_URL:
        _notify({"type": "run_lance", "suite": target})
    jdd_file = None
    jdd_info: dict | None = None
    if jdd_jeux:
        import jdd

        if not jdd_env:
            raise ValueError("jdd_env est obligatoire avec jdd_jeux.")
        res = jdd.resoudre(jdd_env, jdd_jeux)
        jdd_info = {"env": jdd_env, "controles": res["controles"], "bloques": res["bloques"]}
        if res["bloques"]:
            return {"statut": "bloqué données", "jdd": jdd_info,
                    "conseil": "Préparer les données manquantes ou choisir un autre jeu, puis relancer."}
        jdd_info["valeurs"] = jdd.masquer(jdd_env, res["jeux"])
    out_abs = _safe_path(output_dir)
    out_abs.mkdir(parents=True, exist_ok=True)
    report_path = out_abs / "xray_live_report.json"
    if report_path.exists():
        report_path.unlink()

    cmd = [sys.executable, "-m", "robot", "--outputdir", output_dir]
    if cartographie:
        app = _carte().app_courante()
        if not app:
            raise RuntimeError("Aucune application dans la carte : crée-la d'abord.")
        cmd += ["--listener", f"{Path(__file__).resolve().parent / 'cartographie_listener.py'}:{app}"]
    if relancer_echecs:
        prev = out_abs / "output.xml"
        if not prev.exists():
            raise FileNotFoundError("Aucun run précédent à relancer dans ce dossier de résultats.")
        shutil.copy(prev, out_abs / "output_precedent.xml")
        cmd += ["--rerunfailed", str(out_abs / "output_precedent.xml")]
    if jdd_jeux:
        jdd_file = jdd.ecrire_fichier_variables(res["jeux"], out_abs / ".jdd_resolu.yaml")
        cmd += ["--variablefile", str(jdd_file)]
    live_xray = bool(xray_ticket) and not dry_run and xray_mode == "live"
    if live_xray or events_url:
        platform = str((variables or {}).get("PLATFORM", ""))
        cfg = {
            "ticket": xray_ticket if live_xray else "",
            "events_url": events_url,
            "exec_summary": exec_summary or (f"Exécution auto – {Path(target).stem}"
                                             + (f" – {platform}" if platform else "")
                                             + f" – {datetime.now():%d/%m/%Y %H:%M}"),
            "plan_summary": plan_summary,
            "test_environments": test_environments if test_environments is not None
            else ([platform] if platform else []),
            "transition_start": jira_transition_start,
            "transition_end": jira_transition_end,
            "transition_end_if_fail": jira_transition_end_if_fail,
            "attach_screenshots": attach_screenshots,
            "output_dir": str(out_abs),
            "report": str(report_path),
        }
        cfg_path = out_abs / "xray_run_config.json"
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
        listener = Path(__file__).resolve().parent / "xray_live_listener.py"
        cmd += ["--listener", f"{listener}:{cfg_path}"]
    elif xray_ticket and not dry_run and xray_mode == "listener_projet":
        tpl = os.environ.get("ROBOT_XRAY_LISTENER", "")
        if not tpl:
            raise RuntimeError("ROBOT_XRAY_LISTENER non configuré.")
        cmd += ["--listener", tpl.replace("{exec_key}", xray_ticket),
                "--variable", f"XRAY_EXECUTION_KEY:{xray_ticket}"]

    for t in include_tags or []:
        cmd += ["--include", t]
    for t in exclude_tags or []:
        cmd += ["--exclude", t]
    for k, v in (variables or {}).items():
        cmd += ["--variable", f"{k}:{v}"]
    if dry_run:
        cmd.append("--dryrun")
    cmd.append(str(_safe_path(target).relative_to(PROJECT_DIR)))

    try:
        proc = subprocess.run(cmd, cwd=PROJECT_DIR, capture_output=True, text=True, timeout=timeout_s)
    finally:
        if jdd_file and jdd_file.exists():
            jdd_file.unlink()  # contient des secrets résolus : jamais conservé
    bilan: dict = {"commande": " ".join(cmd), "code_retour": proc.returncode,
                   "console_fin": proc.stdout[-3000:], "erreurs": proc.stderr[-2000:]}
    output = out_abs / "output.xml"
    if output.exists():
        bilan["resultat"] = parse_robot_output(str(output.relative_to(PROJECT_DIR)))
    if report_path.exists():
        bilan["xray"] = json.loads(report_path.read_text("utf-8"))
    if jdd_info:
        bilan["jdd"] = jdd_info
    _notify({"type": "run_bilan", "bilan": bilan})
    return bilan


# --------------------------------------------------------------------------- Xray / Jira
@mcp.tool()
def xray_get_test(test_key: str) -> dict:
    """Lit un test Xray : type, scénario Gherkin (Cucumber) ou étapes manuelles, libellés.
    Point de départ pour automatiser un parcours : Claude déroule ces étapes sur le device."""
    from xray_client import XrayClient

    q = ('query($jql: String) { getTests(jql: $jql, limit: 1) { results { issueId gherkin unstructured '
         'testType { name kind } steps { action data result } '
         'jira(fields: ["key", "summary", "labels", "description"]) } } }')
    res = XrayClient().gql(q, {"jql": f'key = "{test_key.upper()}"'})["getTests"]["results"]
    if not res:
        raise KeyError(f"Test {test_key} introuvable dans Xray.")
    t = res[0]
    jira = t.get("jira") or {}
    return {"cle": jira.get("key"), "resume": jira.get("summary"), "libelles": jira.get("labels"),
            "type": (t.get("testType") or {}).get("name"), "gherkin": t.get("gherkin"),
            "etapes": t.get("steps") or [], "generique": t.get("unstructured"),
            "description": jira.get("description")}


@mcp.tool()
def list_jdd(env: str = "") -> dict:
    """Liste les jeux de données d'un environnement (sans env : liste des environnements)."""
    import jdd

    if not env:
        return {"environnements": jdd.environnements()}
    return {"env": env, "jeux": jdd.lister(env)}


@mcp.tool()
def get_jdd(env: str, jeu: str) -> dict:
    """Détail d'un jeu de données (secrets affichés sous forme {{env:VARIABLE}}, jamais en clair)."""
    import jdd

    return jdd.lire(env, jeu)


@mcp.tool()
def find_test_data(env: str, requete: str, params: dict | None = None) -> list[dict]:
    """Cherche des données éligibles via une requête de la liste blanche (requetes.yaml),
    en lecture seule. Ex. requete='compte_avec_solde', params={'client': 'U123456', 'montant_min': 150}."""
    import jdd

    return jdd.executer_requete(env, requete, params)


@mcp.tool()
def check_jdd(env: str, jeux: list[str]) -> dict:
    """Vérifie les prérequis de données AVANT un run. Un jeu bloqué = test « bloqué données »,
    à ne pas lancer (évite les faux échecs, ex. compte sans solde pour un virement)."""
    import jdd

    res = jdd.resoudre(env, jeux)
    return {"pret": not res["bloques"], "bloques": res["bloques"], "controles": res["controles"],
            "valeurs": jdd.masquer(env, res["jeux"])}


@mcp.tool()
def xray_search_tests(jql: str, limit: int = 50) -> list[dict]:
    """Cherche des tests Xray par JQL, ex. les candidats à l'automatisation d'un projet."""
    from xray_client import XrayClient

    return XrayClient().search_tests(jql, limit)


@mcp.tool()
def add_screen_locator(screen_name: str, key: str, locator: str, platform: str = "") -> dict:
    """Ajoute ou remplace une clé dans les locators capturés d'un écran (plateforme de la session
    par défaut). Sert à corriger un locator sans tout recapturer."""
    p = (platform or _state["platform"] or "").lower()
    if p not in ("android", "ios", "web"):
        raise ValueError("Plateforme inconnue : ouvre une session ou précise platform.")
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAP_DIR / f"{_slug(screen_name)}_{p}.json"
    data = json.loads(path.read_text("utf-8")) if path.exists() else {"ecran": screen_name, "platform": p,
                                                                      "locators": {}}
    data["locators"][key] = locator
    data["date"] = datetime.now().isoformat(timespec="seconds")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    _notify({"type": "locators_change"})
    return {"ecran": screen_name, "platform": p, "cle": key, "locator": locator}


@mcp.tool()
def jira_subtasks(issue_key: str) -> list[dict]:
    """Sous-tâches d'un ticket (ex. ST1 Locators Android… ST5 Branchement) avec leur statut."""
    from xray_client import JiraClient

    return JiraClient().sous_taches(issue_key)


@mcp.tool()
def qualify_failure(run_id: str, qualification: str, commentaire: str = "", message_echec: str = "") -> str:
    """Qualifie un échec dans le test run Xray : bug, données, locator ou environnement."""
    from xray_client import XrayClient

    texte = f"[Qualification : {qualification}]" + (f" {commentaire}" if commentaire else "")
    if message_echec:
        texte += f"\n---\n{message_echec[:2000]}"
    XrayClient().update_run(run_id, comment=texte)
    return "Qualification enregistrée dans Xray."


# --------------------------------------------------------------------------- outils carte
def _ecran_resume(e: dict) -> dict:
    return {"id": e["id"], "nom": e.get("nom", ""), "titre": e.get("titre", ""), "module": e.get("module", ""),
            "plateformes": sorted((e.get("plateformes") or {}).keys()), "etats": [s["nom"] for s in e.get("etats", [])],
            "elements": {k: {"type": v.get("type"), "libelle": v.get("libelle"), "locators": v.get("locators")}
                         for k, v in (e.get("elements") or {}).items()},
            "utilise_par": e.get("utilise_par", []), "a_revoir": e.get("a_revoir", False)}


@mcp.tool()
def map_apps() -> dict:
    """Applications cartographiées et application active."""
    m = _carte()
    return {"active": m.app_courante(), "applications": m.apps()}


@mcp.tool()
def map_create_app(nom: str, plateformes: list[str], app_package: str = "", app_activity: str = "",
                   bundle_id: str = "", url: str = "", build: str = "", langue: str = "fr") -> dict:
    """Déclare une nouvelle application à cartographier (devient l'application active)."""
    return _carte().creer_app(nom, plateformes, {"app_package": app_package, "app_activity": app_activity},
                              {"bundle_id": bundle_id}, {"url": url}, build, langue)


@mcp.tool()
def map_select_app(app: str) -> dict:
    """Change d'application active (slug, voir map_apps)."""
    return _carte().choisir_app(app)


@mcp.tool()
def map_set_build(build: str) -> dict:
    """Indique le build testé : les écrans revisités sont comparés à leur version précédente."""
    return _carte().maj_app(build=build)


@mcp.tool()
def where_am_i() -> dict:
    """Écran courant d'après la carte (créé s'il est inconnu), avec ses éléments et locators connus."""
    obs = _observer(_attendre_stable(3))
    if not obs:
        raise RuntimeError("Carte inactive : ouvre une session et choisis une application.")
    return {**obs, **_ecran_resume(_carte().ecran(obs["id"]))}


@mcp.tool()
def list_screens(module: str = "") -> list[dict]:
    """Écrans de la carte (nom, titre, module, plateformes, couverture par les tests)."""
    return [{"id": e["id"], "nom": e.get("nom", ""), "titre": e.get("titre", ""), "module": e.get("module", ""),
             "plateformes": sorted((e.get("plateformes") or {}).keys()), "tests": len(e.get("utilise_par", []))}
            for e in _carte().ecrans() if not module or e.get("module") == module]


@mcp.tool()
def screen_info(ecran: str) -> dict:
    """Détail d'un écran (par nom, alias ou id) : éléments, locators par plateforme, transitions."""
    m = _carte()
    e = m.ecran(ecran)
    ts = m.transitions()
    return {**_ecran_resume(e),
            "sorties": [{"vers": t["vers"], "action": t["action"], "fiabilite": round(t["reussites"] / max(t["essais"], 1), 2)}
                        for t in ts if t["de"] == e["id"] and not t.get("interdite")],
            "entrees": [{"depuis": t["de"], "action": t["action"]} for t in ts if t["vers"] == e["id"]]}


@mcp.tool()
def name_screen(ecran: str, nom: str, module: str = "") -> dict:
    """Donne un nom métier à un écran (ex. virement_saisie). Un nom déjà utilisé fusionne les deux
    écrans (cas du même écran vu sur Android puis sur iOS)."""
    e = _carte().renommer(ecran, nom, module or None)
    _notify({"type": "carte_change"})
    return _ecran_resume(e)


@mcp.tool()
def goto_screen(ecran: str) -> dict:
    """Va sur un écran connu en rejouant le chemin le plus fiable de la carte (avec rattrapage)."""
    cible = _carte().ecran(ecran)
    return _aller(cible["id"])


@mcp.tool()
def explore(max_ecrans: int = 25, profondeur: int = 3, duree_max_s: int = 900) -> dict:
    """Explore automatiquement l'application depuis l'écran courant (hors liste rouge, sans saisie).
    Long : préférer le lancement depuis l'interface web, qui montre la progression."""
    return _explorer(max_ecrans, profondeur, duree_max_s)


@mcp.tool()
def stop_exploration() -> str:
    """Demande l'arrêt de l'exploration en cours."""
    _EXPLO["stop"].set()
    return "Arrêt demandé."


@mcp.tool()
def map_import_existing(pattern: str = "**/*.resource") -> dict:
    """Amorce la carte avec les locators des fichiers .resource existants du projet."""
    res = _carte().importer_resources(pattern)
    _notify({"type": "carte_change"})
    return res


@mcp.tool()
def map_tags_report(limite: int = 200) -> dict:
    """Éléments sans identifiant de test (Compose sans testTag, SwiftUI sans identifier, web sans
    data-testid), classés par nombre de tests concernés, avec le tag proposé."""
    m = _carte()
    lignes = m.rapport_tags()[:limite]
    return {"nb": len(lignes), "lignes": lignes, "texte": m.texte_rapport_tags(lignes, m.config_app().get("nom", ""))}


@mcp.tool()
def export_screen_resource(ecran: str, output_dir: str = "resources/locators") -> str:
    """Génère le .resource d'un écran depuis la carte (locator principal + secours par plateforme)."""
    m = _carte()
    e = m.ecran(ecran)
    p = m.exporter_resource(e["id"], _safe_path(f"{output_dir}/{e.get('nom') or e['id']}.resource"))
    _notify({"type": "outil", "nom": "generate_locators_resource", "args": {"fichier": str(p)}})
    return str(p)


@mcp.tool()
def xray_inspect_ticket(ticket: str) -> dict:
    """Indique ce que deviendra un run sur ce ticket : Test Plan (nouvelle exécution ajoutée),
    Test Execution (mise à jour), autre ticket / projet (création plan + exécution)."""
    from xray_client import XrayClient

    info = XrayClient().resolve(ticket)
    effet = {"plan": "nouvelle exécution créée et ajoutée à ce plan",
             "execution": "cette exécution sera mise à jour",
             "test": "c'est un Test : non utilisable comme cible",
             "autre": "un plan (lié au ticket) + une exécution seront créés",
             "projet": "un plan + une exécution seront créés dans ce projet"}[info["type"]]
    return {**info, "effet_du_run": effet}


@mcp.tool()
def jira_transition(issue_key: str, transition: str) -> str:
    """Fait passer un ticket Jira dans un statut (nom de transition ou de statut cible)."""
    from xray_client import JiraClient

    cible = JiraClient().transition(issue_key, transition)
    return f"{issue_key} -> {cible}"


@mcp.tool()
def import_results_to_xray(output_xml: str = "results/mcp/output.xml",
                           test_execution_key: str = "", project_key: str = "",
                           test_plan_key: str = "") -> dict:
    """Envoie un output.xml Robot dans Xray Cloud (import/execution/robot), en secours
    quand le run s'est fait sans listener. N'utiliser pas sur un run déjà remonté en live."""
    from xray_client import XRAY_BASE, XrayClient, http

    if not (test_execution_key or project_key):
        raise ValueError("Renseigner test_execution_key ou project_key.")
    params = {k: v for k, v in {"testExecKey": test_execution_key, "projectKey": project_key,
                                "testPlanKey": test_plan_key}.items() if v}
    url = f"{XRAY_BASE}/import/execution/robot?{urllib.parse.urlencode(params)}"
    answer = json.loads(http("POST", url, _safe_path(output_xml).read_bytes(),
                             {"Content-Type": "application/xml",
                              "Authorization": f"Bearer {XrayClient().token()}"}))
    return {"statut": "importé", "execution": answer.get("key"), "reponse_xray": answer}


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    mcp.run()
