"""Assistant d'installation et de lancement de l'atelier (bibliothèque standard seulement).

    lancer-atelier.cmd             (Windows : double-clic, ou dans un terminal)
    ./lancer-atelier.sh            (Linux / macOS)
    python lanceur.py [options]    (directement, avec Python 3.10 ou plus)

À chaque lancement, l'assistant vérifie le poste et ne fait QUE ce qui manque :
  1. Python 3.10 ou plus récent (le lanceur .cmd / .sh propose de l'installer s'il est absent) ;
  2. l'environnement .venv de l'atelier (créé s'il n'existe pas) ;
  3. les dépendances de requirements.txt (installées si le fichier a changé depuis la dernière installation) ;
  4. le navigateur Chromium de Playwright (installé s'il manque ; sinon Chrome ou Edge du poste en secours) ;
  5. le projet de tests (demandé et enregistré s'il n'y en a pas : l'atelier n'écrit jamais dans son propre dossier) ;
  6. Cursor, s'il est sur le poste : l'atelier branché dans Cursor (MCP : stdio, ou par URL http://localhost:8000/mcp si
     Cursor est configuré par URL — jamais l'adresse de l'interface 8765) et ses règles copiées dans le projet, et un mode
     d'envoi des demandes qui marche (la ligne de commande sans l'agent Cursor installé bascule sur la boîte de demandes).
     Ces changements de configuration sont demandés avant d'être faits.
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
import shutil
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
                     "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                     "/Applications/Chromium.app/Contents/MacOS/Chromium", "/usr/bin/google-chrome", "/usr/bin/chromium"]


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
    try:
        rep = (saisie("  Dossier du projet de tests : ") or "").strip().strip('"')
    except (EOFError, KeyboardInterrupt):  # pas de saisie possible : rien n'est créé à la place de l'utilisateur
        alerte("Aucun projet de tests choisi : l'atelier le signalera (Paramètres › Projets).")
        return True
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


CODE_CURSOR = ("import json, sys; from atelier.domain import projets; projets.au_demarrage(); "
               "from atelier.integrations import agents_ia, boite_cursor; from atelier.intelligence import fournisseur_ia; "
               "port = int(sys.argv[1]); c = agents_ia.etat(port)['agents']['cursor']; "
               "e = {} if c['erreur'] else (agents_ia._lire(agents_ia.fichier_config('cursor')).get('mcpServers') or {}).get(agents_ia.NOM) or {}; "
               "print(json.dumps({'cursor_present': c['dossier_agent'], 'mcp_installe': c['installe'], 'mcp_a_jour': c['a_jour'], "
               "'url_actuelle': e.get('url', ''), 'mcp_http_port': agents_ia.port_http(), "
               "'erreur': c['erreur'], 'envoi': boite_cursor.envoi(), 'cli': boite_cursor.cli()['trouvee'], "
               "'fournisseur': fournisseur_ia.fournisseur()}))")
PORT_MCP_HTTP = 8000
CODE_BRANCHER = ("import json, sys; from atelier.domain import projets; projets.au_demarrage(); from atelier.integrations import agents_ia; "
                 "r = agents_ia.installer('cursor', int(sys.argv[1])); g = agents_ia.installer_regles(False); "
                 "print(json.dumps({'ok': True, 'fichier': r['fichier'], 'sauvegarde': r['sauvegarde'], 'regles': len(g['copiees'])}))")
CODE_ENVOI = ("import json, sys; from atelier.domain import projets; projets.au_demarrage(); from atelier.integrations import boite_cursor; "
              "boite_cursor.regler_envoi(sys.argv[1]); print(json.dumps({'ok': True}))")


def _oui(question: str, saisie) -> bool:
    try:
        return (saisie(f"  {question} [O/n] ") or "o").strip().lower() in ("o", "oui", "y", "yes")
    except (EOFError, KeyboardInterrupt):  # pas de saisie possible (lancé sans terminal) : on ne fait rien de plus
        print()
        return False


def _venv_json(code: str, *args, env=None) -> dict:
    r = executer([python_venv(), "-c", code, *args], capture_output=True, text=True, env=env)
    try:
        return json.loads((r.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"erreur": (r.stderr or r.stdout or "").strip()[-300:]}


def etape_cursor(env: dict, port: int, interactif: bool, saisie=input) -> bool:
    """Cursor (facultatif) : MCP de l'atelier branché, règles copiées, mode d'envoi des demandes utilisable."""
    c = _venv_json(CODE_CURSOR, port, env=env)
    if c.get("erreur") and "cursor_present" not in c:
        alerte(f"Cursor : vérification impossible ({c['erreur'][:160]}).")
        return True
    if not c["cursor_present"] and c.get("fournisseur") != "cursor":
        ok("Cursor : absent du poste (facultatif, l'atelier fonctionne sans)")
        return True
    # Cursor configuré par URL (liste blanche d'URL côté Cursor) : le MCP HTTP de l'atelier est sur MCP_HTTP_PORT, à
    # l'adresse http://localhost:<port>/mcp — jamais sur le port de l'interface web (8765)
    if c.get("url_actuelle") and not c.get("mcp_http_port"):
        if f":{port}" in c["url_actuelle"]:
            alerte(f"Cursor pointe sur {c['url_actuelle']} : c'est l'interface web de l'atelier, pas son serveur MCP.")
        if interactif and _oui(f"Cursor est configuré par URL : servir le MCP de l'atelier en HTTP sur http://localhost:{PORT_MCP_HTTP}/mcp "
                               "(port retenu pour les prochains lancements) ?", saisie):
            d = lire_poste()
            d["MCP_HTTP_PORT"] = str(PORT_MCP_HTTP)
            ecrire_poste(d)
            env["MCP_HTTP_PORT"] = str(PORT_MCP_HTTP)
            c = _venv_json(CODE_CURSOR, port, env=env)
    if c.get("erreur"):
        alerte(f"Cursor : {c['erreur']}")
    elif not c["mcp_a_jour"]:
        quoi = "mettre à jour le branchement de l'atelier dans Cursor" if c["mcp_installe"] else "brancher l'atelier dans Cursor (MCP)"
        if interactif and _oui(f"Cursor : {quoi} et copier ses règles dans le projet ?", saisie):
            r = _venv_json(CODE_BRANCHER, port, env=env)
            if r.get("ok"):
                if env.get("MCP_HTTP_PORT"):
                    ok(f"Cursor : MCP par URL http://localhost:{env['MCP_HTTP_PORT']}/mcp (servi par l'atelier à chaque lancement)")
                ok(f"Cursor : atelier branché ({r['fichier']}{', sauvegarde .bak' if r.get('sauvegarde') else ''}), "
                   f"{r['regles']} règle(s) copiée(s) ; redémarrer Cursor pour le prendre en compte")
            else:
                alerte(f"Cursor : branchement impossible ({r.get('erreur', '')[:160]}) ; le faire dans Paramètres › Cursor / Claude.")
        else:
            alerte(f"Cursor : {quoi} (Paramètres › Cursor / Claude, en un clic).")
    else:
        ok("Cursor : atelier branché (MCP à jour)")
    if c.get("envoi") == "cli" and not c.get("cli"):
        if interactif and _oui("Demandes à Cursor en « ligne de commande », mais l'agent Cursor en ligne de commande n'est pas installé : "
                               "passer à la « boîte de demandes » (rien à installer) ?", saisie):
            if _venv_json(CODE_ENVOI, "boite", env=env).get("ok"):
                ok("Cursor : demandes envoyées par la boîte de demandes (dire une fois dans Cursor « Traite les demandes de l'atelier »)")
        else:
            alerte("Cursor : mode « ligne de commande » sans l'agent Cursor installé (commande « agent ») : installer Cursor CLI, "
                   "régler ATELIER_CURSOR_CLI, ou choisir la boîte de demandes (Paramètres › Cursor / Claude).")
    elif c.get("envoi"):
        mode = {"lien": "le chat (lien)", "boite": "la boîte de demandes", "cli": "la ligne de commande"}.get(c["envoi"], c["envoi"])
        ok(f"Cursor : demandes envoyées par {mode}")
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


def etape_browser_robot(env: dict, interactif: bool, saisie=input) -> bool:
    """Bibliothèque Robot Browser (tests web) : « rfbrowser init » après pip ; Node.js est requis. Non bloquant."""
    code = "import json; from atelier.domain import prerequis; print(json.dumps(prerequis.browser_robot()))"
    r = interroger_atelier(code, env)
    if r.get("ok"):
        ok("Tests web : bibliothèque Robot Browser prête")
        return True
    if not shutil.which("node"):
        if sys.platform.startswith("win") and shutil.which("winget") and interactif and _oui(
                "  Node.js est requis pour les tests web (bibliothèque Robot Browser). L'installer avec winget ? [O/n] ", saisie):
            executer(["winget", "install", "-e", "--id", "OpenJS.NodeJS.LTS", "--accept-package-agreements", "--accept-source-agreements"])
        elif sys.platform == "darwin" and shutil.which("brew") and interactif and _oui(
                "  Node.js est requis pour les tests web (bibliothèque Robot Browser). L'installer avec Homebrew (brew install node) ? [O/n] ", saisie):
            executer(["brew", "install", "node"])
        if not shutil.which("node"):
            alerte("Tests web : Node.js absent (https://nodejs.org, version LTS). Après installation, fermer et rouvrir la fenêtre, "
                   "puis relancer : l'atelier initialisera la bibliothèque Browser. La Discovery et le mobile fonctionnent sans.")
            return True
    action("Initialisation de la bibliothèque Robot Browser (rfbrowser init), quelques minutes la première fois…")
    if executer([python_venv(), "-m", "Browser.entry", "init"]).returncode == 0 and interroger_atelier(code, env).get("ok"):
        ok("Tests web : bibliothèque Robot Browser initialisée")
        return True
    alerte("Initialisation de la bibliothèque Browser impossible. Derrière un proxy : régler HTTPS_PROXY (et NODE_EXTRA_CA_CERTS "
           "pour le certificat), puis « " + (".venv\\Scripts\\python" if os.name == "nt" else ".venv/bin/python") + " -m Browser.entry init ».")
    return True


def etape_appium(env: dict, interactif: bool, saisie=input) -> bool:
    """Téléphones (Android, et iPhone / simulateurs sur Mac) : Appium et ses pilotes installés, puis Appium démarré s'il ne
    répond pas. Non bloquant : le web et l'API fonctionnent sans."""
    code = "import json; from atelier.domain import prerequis; print(json.dumps(prerequis.mobile()))"
    m = interroger_atelier(code, env)
    if "erreur" in m:
        return True
    if not m.get("ok") and m.get("commandes") and interactif and _oui(
            "Outils mobiles : " + m.get("detail", "") + ". Les installer (" + " ; ".join(" ".join(c) for c in m["commandes"]) + ") ?", saisie):
        for c in m["commandes"]:
            exe = shutil.which(c[0])
            if exe:
                action(" ".join(c) + "…")
                executer([exe, *c[1:]])
        m = interroger_atelier(code, env)
    if not m.get("ok"):
        alerte("Outils mobiles : " + m.get("detail", "") + (" — " + m["solution"] if m.get("solution") else ""))
    else:
        ok("Outils mobiles : " + m.get("detail", ""))
    appium = shutil.which("appium")
    url = (env.get("APPIUM_URL") or "http://127.0.0.1:4723").rstrip("/")
    if not appium or "aucun outil mobile" in m.get("detail", "") or not url.startswith(("http://127.0.0.1", "http://localhost")):
        return True
    try:
        with urllib.request.urlopen(url + "/status", timeout=2):
            ok("Appium répond (" + url + ")")
            return True
    except OSError:
        pass
    journal = Path.home() / ".atelier-appium.log"
    port = url.rsplit(":", 1)[-1].split("/")[0]
    with open(journal, "ab") as j:  # détaché : Appium reste disponible pour les runs, journal dans le dossier personnel
        subprocess.Popen([appium, "--port", port], stdout=j, stderr=j, stdin=subprocess.DEVNULL,
                         **({"creationflags": 0x00000008 | 0x00000200} if os.name == "nt" else {"start_new_session": True}))
    if attendre(url + "/status", 30):
        ok(f"Appium démarré ({url}, journal : {journal})")
    else:
        alerte(f"Appium ne répond pas après 30 s : voir {journal}")
    return True


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description="Assistant d'installation et de lancement de l'atelier.")
    a.add_argument("--verifier", action="store_true", help="vérifier et installer ce qui manque, sans lancer")
    a.add_argument("--sans-ouvrir", action="store_true", help="ne pas ouvrir le navigateur")
    a.add_argument("--reinstaller", action="store_true", help="réinstaller les dépendances")
    a.add_argument("--port", type=int, default=int(os.environ.get("WEB_PORT") or 8765))
    o = a.parse_args(argv)
    print("\nAtelier : préparation du poste")
    env = {**os.environ, **{k: v for k, v in lire_poste().items() if k in ("WEB_BROWSER_EXECUTABLE", "MCP_HTTP_PORT") and not os.environ.get(k)}}
    etapes_faites = [etape_python() and etape_venv() and etape_dependances(o.reinstaller)]
    if not etapes_faites[0]:
        alerte("Poste non prêt : corriger ci-dessus, puis relancer.")
        return 1
    etape_navigateur(env)
    etape_browser_robot(env, interactif=sys.stdin.isatty())
    etape_appium(env, interactif=sys.stdin.isatty())
    etape_projet(env, interactif=sys.stdin.isatty())
    etape_cursor(env, o.port, interactif=sys.stdin.isatty())
    print(f"\n  Atelier prêt{f' ({len(A_REGLER)} point(s) à régler ci-dessus, non bloquant)' if A_REGLER else ''}.")
    if o.verifier:
        return 0
    print(f"  Démarrage sur http://127.0.0.1:{o.port}  (Ctrl+C pour arrêter)\n")
    return lancer(env, o.port, not o.sans_ouvrir)


if __name__ == "__main__":
    sys.exit(main())
