"""Bibliothèque Robot du projet de démonstration : pilote l'application web FICTIVE de `app/`
avec Playwright (déjà requis par l'atelier). Un vrai projet utiliserait la Browser library ;
celle-ci évite d'installer Node.js pour la démonstration.

Locators acceptés : `id=xxx`, `css=xxx` ou un sélecteur CSS brut.
Navigateur : WEB_BROWSER_EXECUTABLE si défini, sinon le Chromium installé par Playwright.
"""
import os
from pathlib import Path

from robot.api import logger
from robot.api.deco import keyword, library
from robot.libraries.BuiltIn import BuiltIn

RACINE_APP = Path(__file__).resolve().parents[2] / "app"


def _selecteur(locator: str) -> str:
    if locator.startswith("id="):
        return "#" + locator[3:]
    if locator.startswith("css="):
        return locator[4:]
    return locator


@library(scope="SUITE", auto_keywords=False)
class NavigateurDemo:
    def __init__(self, delai_s: float = 3):
        self.delai_ms = float(delai_s) * 1000
        self._pw = self._navigateur = self.page = None

    def _demarrer(self):
        if self._navigateur:
            return
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        exe = os.environ.get("WEB_BROWSER_EXECUTABLE") or None
        self._navigateur = self._pw.chromium.launch(executable_path=exe, headless=True)

    @keyword("Ouvrir L Application")
    def ouvrir(self, page: str = "connexion.html"):
        """Ouvre une page de l'application fictive dans un nouvel onglet."""
        self._demarrer()
        if self.page:
            self.page.close()
        self.page = self._navigateur.new_page(viewport={"width": 420, "height": 640})
        self.page.goto((RACINE_APP / page).as_uri())

    @keyword("Saisir Dans")
    def saisir(self, locator: str, texte: str):
        self.page.fill(_selecteur(locator), str(texte), timeout=self.delai_ms)

    @keyword("Cliquer Sur")
    def cliquer(self, locator: str):
        self.page.click(_selecteur(locator), timeout=self.delai_ms)

    @keyword("Le Texte Doit Contenir")
    def texte_contient(self, locator: str, attendu: str):
        """Attend (délai de la bibliothèque) que l'élément contienne le texte attendu."""
        sel = _selecteur(locator)
        try:
            self.page.wait_for_function(
                "([s, t]) => { const e = document.querySelector(s); return !!e && e.textContent.includes(t); }",
                arg=[sel, str(attendu)], timeout=self.delai_ms)
        except Exception:
            trouve = self.page.text_content(sel) if self.page.query_selector(sel) else "(élément absent)"
            raise AssertionError(f"Attendu : « {attendu} » dans {locator}. Trouvé : « {trouve} ».") from None

    @keyword("Capturer L Ecran")
    def capturer(self, nom: str = "capture"):
        """Capture d'écran dans ${OUTPUT DIR}/captures, insérée dans le log Robot."""
        if not self.page:
            return
        sortie = Path(BuiltIn().get_variable_value("${OUTPUT DIR}"))
        (sortie / "captures").mkdir(exist_ok=True)
        fichier = "".join(c if c.isalnum() or c in "-_" else "_" for c in nom) + ".png"
        self.page.screenshot(path=str(sortie / "captures" / fichier))
        logger.info(f'<img src="captures/{fichier}" width="320">', html=True)

    @keyword("Fermer L Application")
    def fermer(self):
        if self._navigateur:
            self._navigateur.close()
            self._pw.stop()
        self._pw = self._navigateur = self.page = None
