"""Technologies Robot Framework : le générateur historique (bdd.generer_robot + Page Object Model de pom), choisi
pour une bibliothèque donnée. La sortie est celle de generer_robot, à l'identique ; seule la bibliothèque des keywords
générés (AppiumLibrary, Browser, SeleniumLibrary, API) est imposée par la technologie au lieu d'être déduite du type de
l'application. Web : Browser (Playwright, défaut) ou SeleniumLibrary, au choix par application (automatisation.technologie_defaut)."""
from __future__ import annotations

from atelier.generation.technologies import Technologie


class _Robot(Technologie):
    type_app = ""

    def generer(self, m: dict, inventaire: dict | None = None, chemin: str = "") -> dict:
        from atelier.generation import bdd

        g = bdd.generer_robot(m, inventaire, chemin, type_app=self.type_app)
        g["technologie"] = self.nom
        return g


class RobotAppium(_Robot):
    type_app = "mobile"

    def __init__(self):
        super().__init__("robot-appium", "Robot Framework + Appium", ["android", "ios"], "Robot Framework",
                         "serveur Appium (UiAutomator2 / XCUITest)", prerequis=["robotframework", "robotframework-appiumlibrary", "Appium"])


class RobotWeb(_Robot):
    type_app = "web"

    def __init__(self):
        super().__init__("robot-web", "Robot Framework + Browser", ["web"], "Robot Framework", "navigateur (Playwright)",
                         prerequis=["robotframework", "robotframework-browser"])


class RobotSelenium(_Robot):
    type_app = "web-selenium"

    def __init__(self):
        super().__init__("robot-selenium", "Robot Framework + SeleniumLibrary", ["web"], "Robot Framework", "navigateur (WebDriver)",
                         prerequis=["robotframework", "robotframework-seleniumlibrary", "pilote du navigateur (chromedriver…)"])


class RobotApi(_Robot):
    type_app = "api"

    def __init__(self):
        super().__init__("robot-api", "Robot Framework + RequestsLibrary", ["api"], "Robot Framework", "HTTP",
                         prerequis=["robotframework", "robotframework-requests"])
