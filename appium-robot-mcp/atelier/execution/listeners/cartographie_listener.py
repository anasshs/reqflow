"""
Listener Robot Framework (API v3) — cartographie pendant les runs (tests mobiles AppiumLibrary).

    robot --listener /chemin/cartographie_listener.py:<slug_application> tests/

Après chaque action AppiumLibrary (Click Element, Input Text, Tap…), l'écran est identifié dans la
carte de l'application et la transition est enregistrée. Chaque écran retient aussi les tests Xray
qui passent par lui (« utilise_par »), ce qui sert à la couverture et à l'analyse d'impact.

Le run n'est jamais interrompu par la cartographie (erreurs ignorées).
Web (Browser library) : la carte web se construit pendant les sessions du MCP.
"""
from __future__ import annotations

import os
import re
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

ACTIONS = {"click element", "click button", "click text", "tap", "click a point", "input text",
           "input password", "go back", "press keycode", "swipe", "swipe by percent", "scroll",
           "scroll down", "scroll up", "click element at coordinates"}
KEY_RE = re.compile(os.environ.get("XRAY_TEST_KEY_REGEX", r"^[A-Z][A-Z0-9_]+-\d+$"))


class cartographie_listener:
    ROBOT_LISTENER_API_VERSION = 3

    def __init__(self, app: str = ""):
        self.app = app or None
        self.test_key = None
        self.avant = None

    def _driver(self):
        from robot.libraries.BuiltIn import BuiltIn

        return BuiltIn().get_library_instance("AppiumLibrary")._current_application()

    def _observer(self):
        from atelier.discovery import carte as app_map
        from atelier.discovery.parsing import parse_elements as _parse_elements

        drv = self._driver()
        plat = str(drv.capabilities.get("platformName", "")).lower()
        plat = "ios" if "ios" in plat else "android"
        ctx = ""
        if plat == "android":
            try:
                ctx = drv.current_activity or ""
            except Exception:
                pass
        els = _parse_elements(drv.page_source, plat)
        build = app_map.config_app(self.app).get("build", "")
        obs = app_map.observer(els, plat, ctx, build=build, vignette_cb=drv.get_screenshot_as_png,
                               test_key=self.test_key, s=self.app)
        return obs, plat, els

    @staticmethod
    def _est_action(result) -> bool:
        lib = getattr(result, "owner", None) or getattr(result, "libname", "") or ""
        nom = (getattr(result, "name", "") or getattr(result, "kwname", "") or "").lower()
        return str(lib) == "AppiumLibrary" and nom in ACTIONS

    def start_test(self, data, result):
        self.test_key = next((t for t in data.tags if KEY_RE.match(t)), None)

    def start_keyword(self, data, result):
        if self._est_action(result):
            try:
                self.avant = self._observer()
            except Exception:
                self.avant = None

    def end_keyword(self, data, result):
        if not self._est_action(result) or not self.avant:
            return
        try:
            from atelier.discovery import carte as app_map

            time.sleep(0.8)  # laisse l'écran se stabiliser
            apres, plat, _ = self._observer()
            avant = self.avant[0]
            if apres["id"] != avant["id"] and result.status == "PASS":
                args = [str(a) for a in getattr(data, "args", ())]
                nom = (getattr(result, "name", "") or "").lower()
                typ = "press_back" if nom == "go back" else "type_text" if "input" in nom else \
                    "swipe" if ("swipe" in nom or "scroll" in nom) else "tap"
                loc = args[0] if args and typ in ("tap", "type_text") else ""
                action = {"type": typ, "locator": loc,
                          "cle": app_map.cle_pour_locator(avant["id"], loc, plat, self.app) if loc else ""}
                app_map.enregistrer_transition(avant["id"], apres["id"], plat, action, source="tnr", s=self.app)
        except Exception:
            pass
        finally:
            self.avant = None
