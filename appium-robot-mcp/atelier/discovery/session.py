"""Session de découverte : le driver Appium (Android / iOS) ou la page Playwright (web) vit ici,
pas dans les façades. Lecture de l'écran et actions brutes (sans carte)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time

from atelier.discovery.parsing import UIA_ID, parse_elements
from atelier.domain import evenements
from atelier.integrations import appium as appium_int

APPIUM_URL = os.environ.get("APPIUM_URL", "http://127.0.0.1:4723")

etat: dict = {"driver": None, "platform": None}
_webb_inst = None


# --------------------------------------------------------------------------- accès
def webb():
    """Backend Playwright (créé à la demande)."""
    global _webb_inst
    if _webb_inst is None:
        from atelier.integrations.playwright import WebBackend

        _webb_inst = WebBackend()
    return _webb_inst


def plateforme() -> str | None:
    return etat["platform"]


def is_web() -> bool:
    return etat["platform"] == "web"


def driver():
    if etat["driver"] is None:
        raise RuntimeError("Aucune session Appium active. Appelle d'abord start_session.")
    return etat["driver"]


def find(locator: str, timeout: float = 10):
    return appium_int.find(driver(), locator, timeout)


# --------------------------------------------------------------------------- devices & session
def chemin_adb() -> str | None:
    """adb du PATH, sinon celui du SDK Android (ANDROID_HOME, ANDROID_SDK_ROOT, emplacements par défaut de Windows,
    macOS et Linux) : sous Windows, le SDK installé par Android Studio n'est souvent pas dans le PATH."""
    trouve = shutil.which("adb")
    if trouve:
        return trouve
    exe = "adb.exe" if os.name == "nt" else "adb"
    racines = [os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"),
               os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk") if os.environ.get("LOCALAPPDATA") else None,
               os.path.expanduser("~/Library/Android/sdk"), os.path.expanduser("~/Android/Sdk")]
    for r in racines:
        if r and os.path.isfile(os.path.join(r, "platform-tools", exe)):
            return os.path.join(r, "platform-tools", exe)
    return None


def diagnostic_devices() -> dict:
    """Pourquoi un device n'apparaît pas : adb trouvé ou non, appareils vus par adb mais pas prêts (unauthorized,
    offline), outils iOS présents."""
    adb = chemin_adb()
    out = {"adb": adb, "android_tous": [], "xcrun": bool(shutil.which("xcrun")), "idevice_id": bool(shutil.which("idevice_id")),
           "android_home": os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or "", "erreur": ""}
    if adb:
        try:
            r = subprocess.run([adb, "devices", "-l"], capture_output=True, text=True, errors="replace", timeout=20)
            for line in r.stdout.splitlines()[1:]:
                parts = line.split()
                if len(parts) > 1:
                    out["android_tous"].append({"udid": parts[0], "etat": parts[1]})
        except Exception as e:  # noqa: BLE001
            out["erreur"] = str(e)[:200]
    return out


def list_devices() -> dict:
    out: dict = {"android": [], "ios_simulateurs": [], "ios_physiques": []}
    adb = chemin_adb()
    if adb:
        r = subprocess.run([adb, "devices", "-l"], capture_output=True, text=True, errors="replace", timeout=20)
        for line in r.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) > 1 and parts[1] == "device":
                out["android"].append({"udid": parts[0], "details": " ".join(parts[2:])})
    if shutil.which("xcrun"):
        r = subprocess.run(["xcrun", "simctl", "list", "devices", "booted", "-j"],
                           capture_output=True, text=True, errors="replace", timeout=30)
        for runtime, devs in json.loads(r.stdout or "{}").get("devices", {}).items():
            for d in devs:
                if d.get("state") == "Booted":
                    out["ios_simulateurs"].append(
                        {"nom": d["name"], "udid": d["udid"], "runtime": runtime.split(".")[-1]})
    if shutil.which("idevice_id"):
        r = subprocess.run(["idevice_id", "-l"], capture_output=True, text=True, errors="replace", timeout=20)
        out["ios_physiques"] = [u for u in r.stdout.split() if u]
    return out


def start_session(platform: str, udid: str = "", app: str = "", app_package: str = "",
                  app_activity: str = "", bundle_id: str = "", no_reset: bool = True,
                  extra_caps: dict | None = None, url: str = "", browser: str = "chromium",
                  headless: bool = True) -> dict:
    if etat["platform"]:
        stop_session()
    p = platform.lower().strip()
    if p == "web":
        info = webb().start(url, browser, headless)
        etat["platform"] = "web"
        evenements.publier({"type": "session", "etat": "ouverte", "platform": "web"})
        return {"statut": "session ouverte", "platform": "web", **info}
    if p not in ("android", "ios"):
        raise ValueError("platform doit valoir 'android', 'ios' ou 'web'")
    etat["driver"] = appium_int.creer_driver(APPIUM_URL, p, udid, app, app_package, app_activity, bundle_id,
                                             no_reset, extra_caps)
    etat["platform"] = p
    evenements.publier({"type": "session", "etat": "ouverte", "platform": p, "udid": udid})
    return {"statut": "session ouverte", "platform": p, "session_id": etat["driver"].session_id}


def stop_session() -> str:
    if is_web():
        webb().stop()
        etat["platform"] = None
        evenements.publier({"type": "session", "etat": "fermee"})
        return "Session fermée."
    if etat["driver"] is None:
        return "Aucune session active."
    try:
        etat["driver"].quit()
    finally:
        etat["driver"], etat["platform"] = None, None
    evenements.publier({"type": "session", "etat": "fermee"})
    return "Session fermée."


# --------------------------------------------------------------------------- lecture
def screenshot_png() -> bytes:
    return webb().screenshot() if is_web() else driver().get_screenshot_as_png()


def window_size() -> dict:
    """Taille de l'écran (mobile) ou du viewport (web)."""
    return webb().window() if is_web() else driver().get_window_size()


def rect_ratio(locator: str) -> dict | None:
    if is_web():
        return webb().rect(locator)
    r, w = find(locator, 3).rect, driver().get_window_size()
    return {"x": r["x"] / w["width"], "y": r["y"] / w["height"],
            "w": r["width"] / w["width"], "h": r["height"] / w["height"]}


def current_elements(max_elements: int = 120) -> list[dict]:
    if is_web():
        els = webb().elements(max_elements)
        seen: dict = {}
        for e in els:  # clés uniques
            n = seen.get(e["key"], 0)
            seen[e["key"]] = n + 1
            if n:
                e["key"] = f"{e['key']}_{n + 1}"
        return els
    return parse_elements(driver().page_source, etat["platform"])[:max_elements]


def get_screen_elements(max_elements: int = 120) -> dict:
    elements = current_elements(max_elements)
    out = {"platform": etat["platform"], "nb_elements": len(elements), "elements": elements}
    if is_web():
        out.update(webb().info())
    return out


def element_at(x_ratio: float, y_ratio: float) -> dict:
    if is_web():
        el = webb().element_at(x_ratio, y_ratio)
        if not el:
            raise LookupError("Aucun élément à cet endroit.")
        return el
    w = driver().get_window_size()
    x, y = x_ratio * w["width"], y_ratio * w["height"]
    hits = [e for e in parse_elements(driver().page_source, etat["platform"])
            if e.get("rect") and e["rect"][0] <= x <= e["rect"][0] + e["rect"][2]
            and e["rect"][1] <= y <= e["rect"][1] + e["rect"][3] and e["rect"][2] * e["rect"][3] > 0]
    if not hits:
        raise LookupError("Aucun élément à cet endroit.")
    # le plus petit élément qui contient le point, en privilégiant ceux qui ont un id
    hits.sort(key=lambda e: (not e["locators"][0].startswith(("id=", "accessibility_id=", UIA_ID)),
                             e["rect"][2] * e["rect"][3]))
    return hits[0]


def get_page_source(max_chars: int = 60000) -> str:
    return webb().source(max_chars) if is_web() else driver().page_source[:max_chars]


def present(locator: str) -> bool:
    try:
        if is_web():
            return webb().check(locator)["nb_trouves"] > 0
        b, value = appium_int.by(locator)
        return len(driver().find_elements(b, value)) > 0
    except Exception:
        return False


def check_locator(locator: str) -> dict:
    montrer_cible(locator, "vérification")
    if is_web():
        return webb().check(locator)
    b, value = appium_int.by(locator)
    found = driver().find_elements(b, value)
    info: dict = {"locator": locator, "nb_trouves": len(found)}
    if found:
        info.update({"texte": found[0].text, "affiche": found[0].is_displayed()})
    return info


# --------------------------------------------------------------------------- actions brutes
def montrer_cible(locator: str, label: str):
    """Surligne l'élément visé (si une façade affiche l'écran) avant l'action."""
    if not evenements.a_des_abonnes("surlignage"):
        return
    try:
        box = rect_ratio(locator)
        if box:
            evenements.publier({"type": "surlignage", "label": label, **box})
            time.sleep(0.7)
    except Exception:
        pass


def action_faite(nom: str, args: dict):
    evenements.publier({"type": "outil", "nom": nom, "args": args})
    evenements.publier({"type": "ecran_change"})


def click_raw(locator: str, timeout: float = 5):
    if is_web():
        webb().click(locator, timeout)
    else:
        find(locator, timeout).click()


def back_raw():
    webb().back() if is_web() else driver().back()
