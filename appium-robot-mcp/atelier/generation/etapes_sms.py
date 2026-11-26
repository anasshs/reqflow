"""Étapes prédéfinies « SMS par adb » : leur texte BDD et leur automatisation.

Pendant une Discovery, l'automaticien (ou l'agent par le MCP) joue « préparer la réception d'un SMS », « saisir l'OTP
reçu par SMS », « ouvrir le lien reçu par SMS » (sessions_discovery.etape_predefinie). Le scénario BDD généré reprend
ces étapes avec un texte fixe (TEXTES), et le test automatisé les rejoue :
- Robot : keywords de la bibliothèque SMS du dépôt (« Marquer Le Début De L'Attente SMS », « Récupérer Le Code OTP »,
  « Récupérer Le Lien Reçu Par SMS ») — celle de l'équipe si elle existe déjà (réutiliser avant de créer), sinon la
  bibliothèque livrée par l'atelier (MODELE, écrite une fois dans libraries/SmsAdb.py) ;
- Kotlin (UI Automator / Espresso) : intention « otp » du plan d'automatisation (Bdd.avantOtp / Bdd.otp).
L'OTP suit ${OTP_MODE} comme le reste du dépôt : « arret » par défaut (le test s'arrête sur l'écran OTP, rien n'est
validé), « validation » en recette seulement.
"""
from __future__ import annotations

import re

TEXTES = {"preparer_sms": "je prépare la réception d'un SMS",
          "otp": "je saisis le code OTP reçu par SMS",
          "lien": "j'ouvre le lien reçu par SMS",
          "lien_recuperer": "je récupère le lien reçu par SMS"}
KW_MARQUER, KW_CODE, KW_LIEN = "Marquer Le Début De L'Attente SMS", "Récupérer Le Code OTP", "Récupérer Le Lien Reçu Par SMS"
BIBLIOTHEQUE = "libraries/SmsAdb.py"
_EXCLUS = re.compile(r"(^|/)(\.venv|venv|node_modules|results|\.git|build|__pycache__)(/|$)")


def _norme(t: str) -> str:
    return re.sub(r"\s+", " ", str(t or "").replace("’", "'").strip().casefold())


def reconnaitre(etape: dict | str | None) -> str:
    """Identifiant de l'étape prédéfinie (preparer_sms, otp, lien, lien_recuperer), ou « » si ce n'en est pas une.
    Le champ « predefinie » fait foi ; à défaut le texte (scénario édité dans le .feature)."""
    if isinstance(etape, dict):
        if etape.get("predefinie") in TEXTES:
            return etape["predefinie"]
        etape = etape.get("texte", "")
    t = _norme(etape)
    return next((k for k, v in TEXTES.items() if _norme(v) == t), "")


def bibliotheque_existante() -> str:
    """Bibliothèque Python du dépôt qui définit déjà « Récupérer Le Code OTP » (chemin relatif au projet), ou « »."""
    from atelier.domain import projet

    racine = projet.PROJECT_DIR
    for f in sorted(racine.rglob("*.py")):
        rel = f.relative_to(racine).as_posix()
        if _EXCLUS.search(rel):
            continue
        try:
            texte = f.read_text("utf-8", errors="replace")
        except OSError:
            continue
        if re.search(r"""@keyword\(\s*["']Récupérer Le Code OTP["']""", texte):
            return rel
    return ""


def corps(nom: str, loc: str, type_app: str) -> list[str]:
    """Corps Robot de l'étape prédéfinie (loc : variable du locator du champ, pour l'OTP)."""
    mobile = type_app in ("mobile", "web-selenium")
    if nom == "preparer_sms":
        return [f"    {KW_MARQUER}"]
    if nom == "otp":
        saisir = ([f"    Wait Until Element Is Visible    {loc}    15s", f"    Input Password    {loc}    ${{code}}"] if mobile
                  else [f"    Fill Secret    {loc}    $code"]) if loc else ["    Fail    Champ du code OTP à désigner (locator absent)."]
        return ["    ${mode}=    Get Variable Value    ${OTP_MODE}    arret",
                "    IF    \"${mode}\".strip().lower() != \"validation\"",
                "        Pass Execution    OTP_MODE=${mode} : arrêt sur l'écran OTP, rien n'est validé (validation : recette seulement).",
                "    END",
                f"    ${{code}}=    {KW_CODE}    timeout=90", *saisir]
    if nom in ("lien", "lien_recuperer"):
        lignes = [f"    ${{lien}}=    {KW_LIEN}    timeout=90", "    Set Test Variable    ${LIEN_SMS}    ${lien}"]
        if nom == "lien":
            lignes += (["    ${adb}=    Get Variable Value    ${ADB}    adb",
                        "    ${udid}=    Get Variable Value    ${UDID}    ${EMPTY}",
                        "    @{cible}=    Run Keyword If    \"${udid}\"    Create List    -s    ${udid}    ELSE    Create List",
                        "    ${r}=    Run Process    ${adb}    @{cible}    shell    am    start    -a    android.intent.action.VIEW    -d    '${lien}'",
                        "    Should Be Equal As Integers    ${r.rc}    0    Ouverture du lien reçu par SMS impossible : ${r.stderr}"]
                       if type_app == "mobile" else ["    Go To    ${lien}"])
        return lignes
    return []


def imports(nom: str, type_app: str) -> list[str]:
    """Bibliothèques à importer dans la page pour cette étape (chemins relatifs au projet, ou noms de bibliothèque)."""
    out = [bibliotheque_existante() or BIBLIOTHEQUE]
    if nom == "lien" and type_app == "mobile":
        out.append("Process")
    return out


MODELE = '''# -*- coding: utf-8 -*-
"""SMS reçus par l'appareil Android, lus par adb (livré par l'atelier : étapes prédéfinies de la Discovery).

    adb [-s <serial>] shell content query --uri content://sms/inbox --projection date:address:body --sort "date DESC"

Ordre : « Marquer Le Début De L'Attente SMS » AVANT l'action qui envoie le SMS, puis « Récupérer Le Code OTP » ou
« Récupérer Le Lien Reçu Par SMS » : seul un SMS reçu après le repère est lu, jamais celui d'une exécution précédente.
Appareil : argument serial, sinon ${UDID}, sinon ANDROID_SERIAL, sinon l'unique appareil connecté. adb : ${ADB},
ADB_PATH, sinon « adb » du PATH. Le corps des SMS et le code ne sont jamais journalisés.
"""
import os
import re
import subprocess
import time

from robot.api.deco import keyword, library
from robot.libraries.BuiltIn import BuiltIn

MOTIFS_CODE = (r"(?i)\\bcode\\b\\s*:?\\s*(\\d{4,8})", r"(?<!\\d)(\\d{6})(?!\\d)", r"(?<!\\d)(\\d{4,8})(?!\\d)")
MOTIF_LIEN = r"https?://[^\\s\\"'<>]+"
LIGNE = re.compile(r"Row: \\d+ date=(\\d+), address=(.*?), body=(.*)")


@library(scope="GLOBAL")
class SmsAdb:
    def __init__(self):
        self._repere = 0

    def _variable(self, nom, defaut=""):
        try:
            return BuiltIn().get_variable_value("${%s}" % nom, defaut) or defaut
        except Exception:
            return defaut

    def _adb(self, serial, *args):
        adb = self._variable("ADB") or os.environ.get("ADB_PATH") or "adb"
        serial = serial or self._variable("UDID") or os.environ.get("ANDROID_SERIAL", "")
        cmd = [adb] + (["-s", serial] if serial else []) + list(args)
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        if r.returncode != 0:
            raise AssertionError("adb : " + (r.stderr or r.stdout).strip()[:300])
        return r.stdout

    def _heure(self, serial):
        try:
            return int(self._adb(serial, "shell", "date", "+%s").strip().splitlines()[-1]) * 1000
        except (ValueError, IndexError):
            return int(time.time() * 1000)

    def _attendre(self, extraire, quoi, serial, expediteur, timeout, intervalle):
        depuis = self._repere or self._heure(serial) - 120000
        fin = time.monotonic() + float(timeout)
        while True:
            sortie = self._adb(serial, "shell", "content", "query", "--uri", "content://sms/inbox",
                               "--projection", "date:address:body", "--sort", '"date DESC"')
            for l in sortie.splitlines():
                m = LIGNE.match(l.strip())
                if not m or int(m.group(1)) < depuis:
                    continue
                if expediteur and expediteur.lower() not in m.group(2).lower():
                    continue
                v = extraire(m.group(3))
                if v:
                    self._repere = int(m.group(1)) + 1  # consommé : le suivant devra être plus récent
                    return v
            if time.monotonic() >= fin:
                raise AssertionError("Aucun SMS avec %s reçu en %s s après le repère." % (quoi, timeout))
            time.sleep(float(intervalle))

    @keyword("Marquer Le Début De L'Attente SMS")
    def marquer_debut(self, serial=None):
        """Repère (heure de l'appareil) : seuls les SMS reçus ensuite seront lus. À appeler AVANT l'action qui envoie le SMS."""
        self._repere = self._heure(serial)

    @keyword("Récupérer Le Code OTP")
    def recuperer_code(self, serial=None, expediteur="", timeout=90, intervalle=3):
        """Attend le SMS et retourne son code (jamais journalisé).

        | ${code}= | Récupérer Le Code OTP | timeout=90 |
        """
        def extraire(corps):
            for motif in MOTIFS_CODE:
                m = re.search(motif, corps)
                if m:
                    return m.group(1)
            return ""
        return self._attendre(extraire, "un code", serial, expediteur, timeout, intervalle)

    @keyword("Récupérer Le Lien Reçu Par SMS")
    def recuperer_lien(self, serial=None, expediteur="", timeout=90, intervalle=3):
        """Attend un SMS qui contient un lien et le retourne.

        | ${lien}= | Récupérer Le Lien Reçu Par SMS | timeout=90 |
        """
        def extraire(corps):
            m = re.search(MOTIF_LIEN, corps)
            return m.group(0).rstrip(".,;)") if m else ""
        return self._attendre(extraire, "un lien", serial, expediteur, timeout, intervalle)
'''
