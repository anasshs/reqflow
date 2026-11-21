"""Assistant d'installation et de lancement de l'atelier (bibliothèque standard seulement).

    lancer-atelier.cmd             (Windows : double-clic, ou dans un terminal)
    ./lancer-atelier.sh            (Linux / macOS)
    python lanceur.py [options]    (directement, avec Python 3.10 ou plus)

À chaque lancement, l'assistant vérifie le poste et ne fait QUE ce qui manque :
  1. Python 3.10 ou plus récent (le lanceur .cmd / .sh propose de l'installer s'il est absent) ;
  2. l'environnement .venv de l'atelier (créé s'il n'existe pas) ;
  3. les dépendances de requirements.txt (installées si le fichier a changé depuis la dernière installation) ;
  4. le navigateur Chromium de Playwright (installé s'il manque ; sinon Chrome ou Edge du poste en secours) ;
  5. le projet de tests (demandé et enregistré s'il n'y en a pas : l'atelier n'écrit jamais dans son propre dossier).
Si tout est en place : « Atelier prêt », et il démarre directement, puis s'ouvre dans le navigateur.

Options : --verifier (vérifier et installer, sans lancer), --sans-ouvrir (ne pas ouvrir le navigateur),
--reinstaller (réinstaller les dépendances), --port N (défaut 8765, ou WEB_PORT).
Réglages du poste gardés dans ~/.atelier-poste.json (navigateur de secours) ; le projet, dans la liste des projets
de l'atelier (Paramètres › Projets). Aucun secret n'est demandé ni écrit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ICI = Path(__file__).resolve().parent
VERSION_MIN = (3, 10)
POSTE = Path(os.environ.get("ATELIER_POSTE") or Path.home() / ".atelier-poste.json").expanduser()


# =========================================================================== affichage
def dire(symbole: str, texte: str):
    ligne = f"  {symbole} {texte}"
    try:
        print(ligne, flush=True)
    except UnicodeEncodeError:  # console Windows sans UTF-8
        print(ligne.encode("ascii", "replace").decode("ascii"), flush=True)


def ok(t):
    dire("[ok]", t)


def action(t):
    dire("[..]", t)


A_REGLER: list = []


def alerte(t):
    A_REGLER.append(t)
    dire("[!!]", t)


# =========================================================================== poste
def lire_poste() -> dict:
    try:
        return json.loads(POSTE.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def ecrire_poste(d: dict):
    POSTE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def python_venv(racine: Path = ICI) -> Path:
    return racine / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def empreinte_dependances(racine: Path = ICI) -> str:
    """Empreinte de requirements.txt et de la version de Python : les dépendances sont à réinstaller si elle change."""
    h = hashlib.sha256((racine / "requirements.txt").read_bytes())
    h.update(f"|{sys.version_info.major}.{sys.version_info.minor}".encode())
    return h.hexdigest()


def marqueur(racine: Path = ICI) -> Path:
    return racine / ".venv" / ".atelier-dependances"


def executer(cmd: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], cwd=ICI, **kw)


def interroger_atelier(code: str, env: dict | None = None) -> dict:
    """Exécute un court contrôle dans le Python du .venv (l'atelier y est importable) ; rend son JSON."""
    r = executer([python_venv(), "-c", code], capture_output=True, text=True, env=env)
    try:
        return json.loads((r.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"erreur": (r.stderr or r.stdout or "").strip()[-400:]}


# =========================================================================== étapes
def etape_python() -> bool:
    if sys.version_info < VERSION_MIN:
        alerte(f"Python {sys.version.split()[0]} : l'atelier demande Python {VERSION_MIN[0]}.{VERSION_MIN[1]} ou plus récent "
               "(https://www.python.org/downloads/).")
        return False
    ok(f"Python {sys.version.split()[0]}")
    return True


def etape_venv() -> bool:
    if python_venv().exists():
        ok("Environnement .venv")
        return True
    action("Création de l'environnement .venv…")
    if executer([sys.executable, "-m", "venv", ICI / ".venv"]).returncode != 0 or not python_venv().exists():
        alerte("Création du .venv impossible (sous Linux : installer le paquet python3-venv).")
        return False
    ok("Environnement .venv créé")
    return True


def etape_dependances(forcer: bool = False) -> bool:
    attendu = empreinte_dependances().strip()
    if not forcer and marqueur().exists() and marqueur().read_text("utf-8").strip() == attendu:
        ok("Dépendances à jour")
        return True
    action("Installation des dépendances (requirements.txt), quelques minutes la première fois…")
    executer([python_venv(), "-m", "pip", "install", "--upgrade", "pip"], capture_output=True)
    if executer([python_venv(), "-m", "pip", "install", "-r", "requirements.txt"]).returncode != 0:
        alerte("Échec de pip. Derrière un proxy d'entreprise : régler HTTPS_PROXY (et PIP_CERT pour le certificat), puis relancer.")
        return False
    marqueur().write_text(attendu, encoding="utf-8")
    ok("Dépendances installées")
    return True


NAVIGATEURS_POSTE = [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                     r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                     "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/google-chrome", "/usr/bin/chromium"]


def etape_navigateur(env: dict) -> bool:
    code = "import json; from atelier.domain import prerequis; print(json.dumps(prerequis.navigateur()))"
    n = interroger_atelier(code, env)
    if n.get("ok"):
        ok(f"Navigateur web : {n.get('detail', '')}")
        return True
    action("Installation du navigateur Chromium de Playwright…")
    if executer([python_venv(), "-m", "playwright", "install", "chromium"]).returncode == 0 and interroger_atelier(code, env).get("ok"):
        ok("Navigateur Chromium installé")
        return True
    secours = next((p for p in NAVIGATEURS_POSTE if Path(p).is_file()), "")
    if secours:  # proxy qui bloque le téléchargement : le Chrome ou l'Edge du poste
        d = lire_poste()
        d["WEB_BROWSER_EXECUTABLE"] = secours
        ecrire_poste(d)
        env["WEB_BROWSER_EXECUTABLE"] = secours
        ok(f"Navigateur du poste utilisé : {secours}")
        return True
    alerte("Aucun navigateur pour Discovery web : définir WEB_BROWSER_EXECUTABLE vers Chrome ou Edge. L'atelier démarre quand même.")
    return True  # non bloquant : le mobile et le reste de l'atelier fonctionnent


def _documents() -> Path:
    d = Path.home() / "Documents"
    return d if d.is_dir() else Path.home()


def etape_projet(env: dict, interactif: bool, saisie=input) -> bool:
    """Projet de tests : ROBOT_PROJECT_DIR, sinon le projet actif de l'atelier ; à défaut, demandé et enregistré."""
    code = ("import json; from atelier.domain import prerequis, projets; projets.au_demarrage(); p = prerequis.projet(); "
            "a = projets.actif() or {}; print(json.dumps({**p, 'nom': a.get('nom', '')}))")
    p = interroger_atelier(code, env)
    if p.get("ok"):
        ok(f"Projet de tests : {p.get('nom') or ''} {p['dossier']}".replace("  ", " "))
        return True
    if not interactif:
        alerte("Aucun projet de tests choisi : l'atelier le signalera (Paramètres › Projets).")
        return True
    defaut = _documents() / "GitHub" / "tests-atelier"
    print("\n  Aucun projet de tests choisi. L'atelier y écrira la carte de l'application, les locators, les scénarios et les releases.")
    print("  Donner le dossier d'un dépôt de tests Robot existant, ou Entrée pour créer :", defaut)
    rep = (saisie("  Dossier du projet de tests : ") or "").strip().strip('"')
    dossier = Path(rep).expanduser() if rep else defaut
    if dossier.resolve() == ICI:
        alerte("Ce dossier est celui de l'atelier : choisir un autre dossier (relancer l'assistant).")
        return True
    dossier.mkdir(parents=True, exist_ok=True)
    nom = dossier.name
    code_enr = ("import json, sys; from atelier.domain import projets; d = sys.argv[1]; n = sys.argv[2]; "
                "l = projets.lister()['projets']; p = next((x for x in l if x['dossier'] == str(__import__('pathlib').Path(d).resolve())), None); "
                "pid = p['id'] if p else next(x for x in projets.enregistrer({'nom': n, 'dossier': d})['projets'] if x['nom'] == n)['id']; "
                "projets.activer(pid); print(json.dumps({'ok': True, 'id': pid}))")
    r = executer([python_venv(), "-c", code_enr, dossier, nom], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        alerte(f"Enregistrement du projet impossible : {(r.stderr or '').strip()[-300:]}")
        return True
    ok(f"Projet de tests créé et choisi : {nom} ({dossier})")
    return True


# =========================================================================== lancement
def attendre(url: str, delai: float = 60) -> bool:
    fin = time.time() + delai
    while time.time() < fin:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except OSError:
            time.sleep(0.7)
    return False


def lancer(env: dict, port: int, ouvrir: bool) -> int:
    url = f"http://127.0.0.1:{port}/plateforme"
    env = {**env, "WEB_PORT": str(port)}
    proc = subprocess.Popen([str(python_venv()), str(ICI / "web" / "app.py")], cwd=ICI, env=env)
    if attendre(url) and ouvrir:
        webbrowser.open(url)
    try:
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        return 0


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description="Assistant d'installation et de lancement de l'atelier.")
    a.add_argument("--verifier", action="store_true", help="vérifier et installer ce qui manque, sans lancer")
    a.add_argument("--sans-ouvrir", action="store_true", help="ne pas ouvrir le navigateur")
    a.add_argument("--reinstaller", action="store_true", help="réinstaller les dépendances")
    a.add_argument("--port", type=int, default=int(os.environ.get("WEB_PORT") or 8765))
    o = a.parse_args(argv)
    print("\nAtelier : préparation du poste")
    env = {**os.environ, **{k: v for k, v in lire_poste().items() if k == "WEB_BROWSER_EXECUTABLE" and not os.environ.get(k)}}
    etapes_faites = [etape_python() and etape_venv() and etape_dependances(o.reinstaller)]
    if not etapes_faites[0]:
        alerte("Poste non prêt : corriger ci-dessus, puis relancer.")
        return 1
    etape_navigateur(env)
    etape_projet(env, interactif=sys.stdin.isatty())
    print(f"\n  Atelier prêt{f' ({len(A_REGLER)} point(s) à régler ci-dessus, non bloquant)' if A_REGLER else ''}.")
    if o.verifier:
        return 0
    print(f"  Démarrage sur http://127.0.0.1:{o.port}  (Ctrl+C pour arrêter)\n")
    return lancer(env, o.port, not o.sans_ouvrir)


if __name__ == "__main__":
    sys.exit(main())
