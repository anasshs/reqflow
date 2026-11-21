"""Liaison avec les agents IA (Cursor, Claude Desktop) : configuration MCP du poste et règles du projet.

- La configuration MCP ne contient que le Python de l'atelier, server.py et l'adresse de l'interface locale :
  ni chemin de projet (le serveur MCP suit le projet actif de l'atelier), ni secret (variables d'environnement ou
  coffre du système, lus par le serveur lui-même).
- Installer = fusionner l'entrée « appium-robot » dans le fichier de configuration de l'agent sur ce poste, en gardant
  les autres serveurs et une copie de sauvegarde (.bak) du fichier précédent.
- Les règles Cursor (11 fichiers .mdc, versionnés par projet : atelier/integrations/regles_cursor.py) sont copiées
  dans <projet de tests>/.cursor/rules/ : aucun chemin local ; un fichier modifié localement n'est remplacé qu'avec accord.
- verifier() lance réellement le serveur MCP (stdio) et liste ses outils : la connexion est prouvée, pas supposée.
- Mode HTTP (MCP_HTTP_PORT, ex. 8000) : quand l'équipe Cursor n'autorise que des URL (liste blanche d'administration,
  ex. http://localhost:8000/mcp), l'atelier démarre lui-même le serveur MCP en HTTP sur 127.0.0.1 (jamais exposé) et
  l'entrée Cursor devient {"url": …}. Claude Desktop garde le mode stdio.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from atelier.domain import projet

NOM = "appium-robot"


def fichier_config(agent: str) -> Path:
    if agent == "cursor":
        return Path.home() / ".cursor" / "mcp.json"
    if agent == "claude":
        if os.name == "nt":
            return Path(os.environ.get("APPDATA", str(Path.home()))) / "Claude" / "claude_desktop_config.json"
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"
    raise ValueError("Agent : cursor ou claude.")


def port_http() -> int | None:
    """Port du serveur MCP en HTTP (variable MCP_HTTP_PORT) ; None = mode stdio (Cursor lance le serveur lui-même)."""
    v = os.environ.get("MCP_HTTP_PORT", "").strip()
    if not v:
        return None
    if not v.isdigit() or not 0 < int(v) < 65536:
        raise ValueError(f"MCP_HTTP_PORT invalide : {v!r} (attendu : un numéro de port, ex. 8000).")
    return int(v)


def url_http() -> str:
    return f"http://localhost:{port_http()}/mcp"


def _env_serveur(port: int) -> dict:
    env = {"WEB_EVENTS_URL": f"http://127.0.0.1:{port}/api/events"}
    for v in ("APPIUM_URL", "ATELIER_JETON_FICHIER", "ATELIER_PROJETS"):  # réglages non secrets du poste, s'ils sont imposés
        if os.environ.get(v):
            env[v] = os.environ[v]
    return env


def entree(port: int, agent: str = "cursor") -> dict:
    """Entrée « appium-robot » : Python de l'atelier (son environnement virtuel), server.py, interface locale ;
    en mode HTTP (Cursor seulement), l'URL du serveur MCP que l'atelier a démarré."""
    if agent == "cursor" and port_http():
        return {"url": url_http()}
    return {"command": sys.executable, "args": [str(projet.RACINE_OUTIL / "server.py")], "env": _env_serveur(port)}


def config(port: int) -> dict:
    return {"mcpServers": {NOM: entree(port)}}


_serveur_http: dict = {}


def demarrer_serveur_http(port: int):
    """Mode HTTP : démarre le serveur MCP (python server.py --http) à côté de l'interface ; None en mode stdio."""
    import subprocess

    if not port_http():
        return None
    env = {**os.environ, **_env_serveur(port), "PYTHONIOENCODING": "utf-8", "FASTMCP_LOG_LEVEL": "WARNING",
           "ATELIER_SURVEILLER_PARENT": "1"}
    # stdin relié à l'atelier : s'il s'arrête, même brutalement, le serveur MCP voit la fin du flux et s'arrête (port libéré)
    journal = journal_http()
    sortie = open(journal, "w", encoding="utf-8")  # noqa: SIM115 — gardé ouvert pour le processus fils
    p = subprocess.Popen([sys.executable, str(projet.RACINE_OUTIL / "server.py"), "--http"], env=env, stdin=subprocess.PIPE,
                         stdout=sortie, stderr=subprocess.STDOUT)
    _serveur_http["p"] = p
    return p


def journal_http() -> Path:
    """Sortie du serveur MCP HTTP (démarrage, erreurs) : dite à l'utilisateur quand il ne répond pas."""
    return Path(os.environ.get("ATELIER_MCP_JOURNAL") or Path.home() / ".atelier-mcp-http.log").expanduser()


def _joignable(hote: str, port: int, delai: float = 0.5) -> bool:
    import socket

    try:
        with socket.create_connection((hote, port), timeout=delai):
            return True
    except OSError:
        return False


def cursor_par_url() -> str:
    """URL configurée pour l'atelier dans Cursor (« » en mode stdio, sans configuration ou fichier illisible)."""
    try:
        return ((_lire(fichier_config("cursor")).get("mcpServers") or {}).get(NOM) or {}).get("url", "")
    except ValueError:
        return ""


def etat_serveur_http(attendre_s: float = 0) -> dict:
    """État du serveur MCP HTTP, pour la console, la pastille et l'assistant : attendu (MCP_HTTP_PORT), lancé, joignable
    sur 127.0.0.1 et ::1, fin du journal en cas d'échec ; et Cursor configuré par URL sans serveur attendu."""
    import time

    port = port_http()
    url_cursor = cursor_par_url()
    if not port:
        return {"attendu": False, "url_cursor": url_cursor, "ok": not url_cursor,
                "message": (f"Cursor attend {url_cursor}, mais l'atelier n'a pas été lancé avec MCP_HTTP_PORT : le serveur MCP n'est pas démarré. "
                            "Lancer l'atelier avec lancer-atelier.cmd (il retient le port), ou définir MCP_HTTP_PORT=8000 avant de le lancer.")
                if url_cursor else "mode stdio : Cursor lance lui-même le serveur MCP"}
    def a_pris_le_port() -> bool:  # notre serveur écrit cette ligne une fois le port pris (journal réécrit à chaque démarrage)
        try:
            return "Serveur MCP de l'atelier :" in journal_http().read_text("utf-8", errors="replace")
        except OSError:
            return False
    fin = time.time() + attendre_s
    while True:
        v4, v6 = _joignable("127.0.0.1", port), _joignable("::1", port)
        p = _serveur_http.get("p")
        mort = p is not None and p.poll() is not None
        # lancé par cet atelier : prêt seulement quand c'est NOTRE serveur qui a pris le port (un port qui répond peut être
        # tenu par un autre programme, ou un autre atelier) ; sinon (état lu d'ailleurs) : le port répond
        pret = v4 and (p is None or (not mort and a_pris_le_port()))
        if pret or mort or time.time() >= fin:
            break
        time.sleep(0.5)
    v4 = pret
    queue = ""
    if not v4:
        try:
            lignes = journal_http().read_text("utf-8", errors="replace").strip().splitlines()
            echec = [x for x in lignes if x.startswith("ÉCHEC :")]
            queue = echec[-1].removeprefix("ÉCHEC : ") if echec else "\n".join(lignes[-6:])
        except OSError:
            queue = ""
    url = url_http()
    return {"attendu": True, "url": url, "url_cursor": url_cursor, "ok": v4, "ipv4": v4, "ipv6": v6,
            "processus": None if p is None else ("arrêté (code %s)" % p.returncode if mort else "lancé"),
            "message": (f"prêt sur {url}" + ("" if v6 or not v4 else " (IPv4 seulement)")) if v4
            else (f"le serveur MCP n'a pas démarré sur {url}" if mort else f"le serveur MCP ne répond pas sur {url}")
            + (f" — {queue}" if queue else f" (journal : {journal_http()})"),
            "journal": str(journal_http())}


def arreter_serveur_http() -> None:
    p = _serveur_http.pop("p", None)
    if p and p.poll() is None:
        try:
            p.stdin.close()
        except OSError:
            pass
        p.terminate()
        try:
            p.wait(5)
        except Exception:  # noqa: BLE001
            p.kill()


def _lire(f: Path) -> dict:
    if not f.exists() or not f.read_text("utf-8").strip():
        return {}
    try:
        return json.loads(f.read_text("utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{f} n'est pas un JSON valide ({e.msg}, ligne {e.lineno}) : le corriger ou le renommer, puis recommencer.")


def etat(port: int) -> dict:
    """Pour chaque agent : fichier, installé ou non, à jour ou non (chemins / port différents) ; règles du projet."""
    agents = {}
    for a in ("cursor", "claude"):
        attendu = entree(port, a)
        f = fichier_config(a)
        try:
            actuel = (_lire(f).get("mcpServers") or {}).get(NOM)
            erreur = ""
        except ValueError as e:
            actuel, erreur = None, str(e)
        agents[a] = {"fichier": str(f), "installe": bool(actuel), "a_jour": actuel == attendu, "erreur": erreur,
                     "dossier_agent": f.parent.exists()}
    from atelier.integrations import regles_cursor

    regles = {x["fichier"]: {"present": x["statut"] != "nouveau", "a_jour": x["statut"] == "identique", "statut": x["statut"]}
              for x in regles_cursor.apercu()}
    p = _serveur_http.get("p")
    http = {"url": url_http(), "actif": bool(p and p.poll() is None)} if port_http() else None
    return {"agents": agents, "regles": regles, "projet": str(projet.PROJECT_DIR), "config": config(port), "http": http}


def installer(agent: str, port: int) -> dict:
    """Ajoute / met à jour l'entrée « appium-robot » dans la configuration de l'agent (autres serveurs conservés)."""
    f = fichier_config(agent)
    d = _lire(f)
    sauvegarde = ""
    if f.exists():
        sauvegarde = str(f) + ".bak"
        shutil.copyfile(f, sauvegarde)
    d.setdefault("mcpServers", {})[NOM] = entree(port, agent)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), "utf-8")
    os.replace(tmp, f)
    return {"agent": agent, "fichier": str(f), "sauvegarde": sauvegarde}


def installer_regles(ecraser: bool = False) -> dict:
    """Copie les règles Cursor (version active du projet) dans le projet de tests ; un fichier modifié localement
    n'est remplacé qu'avec ecraser=True (sauvegarde .bak ; pas d'écrasement implicite)."""
    from atelier.integrations import regles_cursor

    tous = [r[0] for r in regles_cursor.RUBRIQUES] if ecraser else []
    r = regles_cursor.synchroniser(tous)
    return {"copiees": r["copiees"], "differentes": r["ignorees"], "identiques": r["identiques"], "sauvegardes": r["sauvegardes"]}


def verifier(port: int, delai_s: int = 40) -> dict:
    """Démarre le serveur MCP comme le fera Cursor (même commande, stdio), fait l'initialisation et liste les outils ;
    en mode HTTP, interroge le serveur que l'atelier a démarré, à l'URL configurée dans Cursor."""
    import subprocess
    import time

    if port_http():
        return verifier_http(url_http(), delai_s)
    e = entree(port, "claude")
    debut = time.monotonic()
    env = {**os.environ, **e["env"], "PYTHONIOENCODING": "utf-8"}
    p = subprocess.Popen([e["command"], *e["args"]], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", env=env)
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                                                           "clientInfo": {"name": "atelier-verification", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    # L'entrée reste ouverte jusqu'à la réponse à tools/list : la fermer aussitôt arrête parfois le serveur avant qu'il réponde.
    import threading

    reponses, fini = {}, threading.Event()

    def lire():
        for l in p.stdout:
            try:
                m = json.loads(l)
            except ValueError:
                continue
            if isinstance(m, dict) and "id" in m:
                reponses[m["id"]] = m
                if m["id"] == 2:
                    break
        fini.set()

    threading.Thread(target=lire, daemon=True).start()
    try:
        p.stdin.write("".join(json.dumps(m) + "\n" for m in msgs))
        p.stdin.flush()
    except OSError:
        pass
    fini.wait(delai_s)
    try:
        p.stdin.close()
    except OSError:
        pass
    try:
        p.wait(timeout=3)
    except subprocess.TimeoutExpired:
        p.kill()
    err = p.stderr.read() if p.stderr else ""
    outils = [t["name"] for t in ((reponses.get(2) or {}).get("result") or {}).get("tools", [])]
    ok = bool(outils) and "result" in (reponses.get(1) or {})
    return {"ok": ok, "outils": len(outils), "serveur": ((reponses.get(1) or {}).get("result") or {}).get("serverInfo", {}),
            "duree_s": round(time.monotonic() - debut, 1), "commande": " ".join([e["command"], *e["args"]]),
            "erreur": "" if ok else (err or "")[-600:] or "aucune réponse du serveur MCP"}


def _post_http(url: str, corps: dict, session: str, delai_s: float):
    """Un message JSON-RPC en HTTP « streamable » : réponse JSON ou flux SSE (lignes « data: »)."""
    import urllib.request

    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session:
        h["Mcp-Session-Id"] = session
    req = urllib.request.Request(url, json.dumps(corps).encode("utf-8"), h, method="POST")
    with urllib.request.urlopen(req, timeout=delai_s) as rep:  # noqa: S310 (URL locale construite par l'atelier)
        texte = rep.read().decode("utf-8", "replace")
        sid = rep.headers.get("Mcp-Session-Id") or session
    for ligne in texte.splitlines() if "data:" in texte else [texte]:
        ligne = ligne[5:].strip() if ligne.startswith("data:") else ligne.strip()
        try:
            m = json.loads(ligne)
        except ValueError:
            continue
        if isinstance(m, dict) and m.get("id") == corps.get("id"):
            return m, sid
    return None, sid


def verifier_http(url: str, delai_s: int = 40) -> dict:
    """Initialise une session MCP sur l'URL (le serveur peut encore démarrer : nouvel essai pendant delai_s) et liste les outils."""
    import time

    debut = time.monotonic()
    erreur = ""
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                                                                         "clientInfo": {"name": "atelier-verification", "version": "1"}}}
    while time.monotonic() - debut < delai_s:
        try:
            r1, sid = _post_http(url, init, "", 15)
            _post_http(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, sid, 15)
            r2, _ = _post_http(url, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, sid, 30)
            outils = [t["name"] for t in ((r2 or {}).get("result") or {}).get("tools", [])]
            ok = bool(outils) and "result" in (r1 or {})
            return {"ok": ok, "outils": len(outils), "serveur": ((r1 or {}).get("result") or {}).get("serverInfo", {}),
                    "duree_s": round(time.monotonic() - debut, 1), "commande": url,
                    "erreur": "" if ok else "réponse MCP inattendue"}
        except OSError as e:  # serveur pas encore prêt, ou port occupé par un autre programme
            erreur = str(getattr(e, "reason", "") or e)
            time.sleep(1)
    return {"ok": False, "outils": 0, "serveur": {}, "duree_s": round(time.monotonic() - debut, 1), "commande": url,
            "erreur": f"serveur MCP injoignable sur {url} ({erreur}). Lancer l'atelier avec MCP_HTTP_PORT défini ; "
                      "si le port est pris par un autre programme, en choisir un autre autorisé par l'équipe Cursor."}
