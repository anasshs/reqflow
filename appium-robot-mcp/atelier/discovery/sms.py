"""SMS reçus par l'appareil Android de la session, lus par adb : code OTP et lien (URL).

    adb -s <appareil> shell content query --uri content://sms/inbox --projection date:address:body --sort "date DESC"

Sert aux étapes prédéfinies de la Discovery (sessions_discovery.etape_predefinie) : l'automaticien, ou l'agent par le
MCP, demande « saisir l'OTP reçu par SMS » ou « ouvrir le lien reçu par SMS » au lieu de lire le téléphone à la main.
Seul un SMS reçu APRÈS le repère (heure de l'appareil, posé par « préparer la réception d'un SMS ») est lu : jamais celui
d'une opération précédente. Le corps des SMS n'est jamais journalisé ; le code OTP n'est jamais renvoyé ni écrit.

Mêmes motifs que la bibliothèque Robot des tests générés (modele_sms_robot.py) : ce que la Discovery lit, le test
automatisé le relit de la même façon.
"""
from __future__ import annotations

import re
import subprocess
import time

MOTIF_CODE_ANCRE = r"(?i)\bcode\b\s*:?\s*(\d{4,8})"   # « …saisir le code :111111. » : ancré sur le mot « code »
MOTIF_CODE = r"(?<!\d)(\d{6})(?!\d)"                    # sinon 6 chiffres isolés (format habituel)
MOTIF_CODE_LARGE = r"(?<!\d)(\d{4,8})(?!\d)"            # en dernier recours 4 à 8 chiffres isolés
MOTIF_LIEN = r"https?://[^\s\"'<>]+"
_LIGNE = re.compile(r"Row: \d+ date=(\d+), address=(.*?), body=(.*)")


def _adb(serial: str, *args: str, lanceur=None, delai: int = 20) -> str:
    from atelier.discovery import session

    adb = session.chemin_adb() or "adb"
    cmd = [adb, *(["-s", serial] if serial and serial != "navigateur" else []), *args]
    if lanceur:
        return lanceur(cmd)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=delai)
    if r.returncode != 0:
        raise RuntimeError(f"adb : {(r.stderr or r.stdout).strip()[:300] or 'échec'}")
    return r.stdout


def heure_appareil(serial: str = "", lanceur=None) -> int:
    """Heure de l'appareil en millisecondes (les dates des SMS sont dans cette horloge, pas celle du poste)."""
    sortie = _adb(serial, "shell", "date", "+%s", lanceur=lanceur).strip()
    try:
        return int(sortie.splitlines()[-1].strip()) * 1000
    except (ValueError, IndexError):
        return int(time.time() * 1000)


def lire(serial: str = "", depuis_ms: int = 0, expediteur: str = "", lanceur=None) -> list[dict]:
    """SMS reçus après depuis_ms (du plus récent au plus ancien), éventuellement d'un expéditeur donné."""
    sortie = _adb(serial, "shell", "content", "query", "--uri", "content://sms/inbox", "--projection", "date:address:body",
                  "--sort", "\"date DESC\"", lanceur=lanceur)
    out = []
    for l in sortie.splitlines():
        m = _LIGNE.match(l.strip())
        if not m:
            continue
        d, adresse, corps = int(m.group(1)), m.group(2).strip(), m.group(3)
        if d < depuis_ms:
            break  # trié du plus récent au plus ancien : le reste est plus vieux
        if expediteur and expediteur.casefold() not in adresse.casefold():
            continue
        out.append({"date": d, "expediteur": adresse, "corps": corps})
    return out


def code(corps: str) -> str:
    for motif in (MOTIF_CODE_ANCRE, MOTIF_CODE, MOTIF_CODE_LARGE):
        m = re.search(motif, corps or "")
        if m:
            return m.group(1)
    return ""


def lien(corps: str) -> str:
    m = re.search(MOTIF_LIEN, corps or "")
    return m.group(0).rstrip(".,;)") if m else ""


def attendre(quoi: str, serial: str = "", depuis_ms: int = 0, delai_s: int = 90, intervalle_s: float = 3, expediteur: str = "",
             lanceur=None, dormir=time.sleep) -> dict:
    """Attend un SMS qui contient un code (quoi="code") ou un lien (quoi="lien") : {valeur, date, expediteur}.
    TimeoutError si rien n'arrive dans le délai (le corps des SMS lus n'est jamais renvoyé)."""
    if quoi not in ("code", "lien"):
        raise ValueError("quoi : code ou lien.")
    extraire = code if quoi == "code" else lien
    fin = time.monotonic() + max(1, int(delai_s))
    while True:
        for s in lire(serial, depuis_ms, expediteur, lanceur):
            v = extraire(s["corps"])
            if v:
                return {"valeur": v, "date": s["date"], "expediteur": s["expediteur"]}
        if time.monotonic() >= fin:
            raise TimeoutError(f"Aucun SMS avec {'un code' if quoi == 'code' else 'un lien'} reçu en {delai_s} s"
                               + (f" de « {expediteur} »" if expediteur else "") + " après le repère.")
        dormir(intervalle_s)


def ouvrir_lien(url: str, serial: str = "", lanceur=None) -> str:
    """Ouvre le lien sur l'appareil (intent VIEW : l'application qui gère le lien, sinon le navigateur)."""
    if not re.fullmatch(MOTIF_LIEN, url or ""):
        raise ValueError("Lien invalide.")
    _adb(serial, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", f"'{url}'", lanceur=lanceur)
    return url
