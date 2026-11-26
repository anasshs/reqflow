"""Client MCP de test (stdio) : lance `python server.py` exactement comme Cursor, initialise la session et appelle des
outils. Sert aux tests d'intégration de la V2 (Cursor lui-même n'est pas pilotable par les tests)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]


def _echanger(msgs: list[dict], attendus: set, env: dict | None, delai_s: int) -> tuple[dict, str]:
    """Envoie les messages et garde l'entrée ouverte jusqu'à toutes les réponses attendues (un serveur stdio s'arrête
    à la fermeture de son entrée, même si un appel est encore en cours)."""
    import queue
    import threading
    import time

    p = subprocess.Popen([sys.executable, str(RACINE / "server.py")], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8", "ATELIER_COFFRE": "non", **(env or {})})
    q: queue.Queue = queue.Queue()
    threading.Thread(target=lambda: [q.put(l) for l in p.stdout], daemon=True).start()
    erreurs: list = []
    threading.Thread(target=lambda: [erreurs.append(l) for l in p.stderr], daemon=True).start()
    p.stdin.write("".join(json.dumps(m) + "\n" for m in msgs))
    p.stdin.flush()
    rep, fin = {}, time.monotonic() + delai_s
    while not attendus <= set(rep) and time.monotonic() < fin:
        try:
            l = q.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            m = json.loads(l)
        except ValueError:
            continue
        if isinstance(m, dict) and "id" in m:
            rep[m["id"]] = m
    p.stdin.close()
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        p.kill()
    return rep, "".join(erreurs)


def session(appels: list[tuple[str, dict]], env: dict | None = None, delai_s: int = 60) -> list[dict]:
    """Une session MCP : initialize, puis chaque (outil, arguments) dans l'ordre. Renvoie, pour chaque appel,
    {"erreur": bool, "valeur": objet JSON décodé ou texte}."""
    msgs = [{"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                                                           "clientInfo": {"name": "tests-atelier", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"}]
    msgs += [{"jsonrpc": "2.0", "id": i + 1, "method": "tools/call", "params": {"name": n, "arguments": a}} for i, (n, a) in enumerate(appels)]
    rep, stderr = _echanger(msgs, set(range(1, len(appels) + 1)), env, delai_s)
    out = []
    for i in range(1, len(appels) + 1):
        m = rep.get(i)
        if m is None:
            raise RuntimeError(f"Pas de réponse MCP pour l'appel {i} ({appels[i - 1][0]}) : {stderr[-800:]}")
        r = m.get("result") or {}
        if "error" in m:
            out.append({"erreur": True, "valeur": m["error"].get("message", "")})
            continue
        if "structuredContent" in r and r["structuredContent"] is not None:
            v = r["structuredContent"]
            v = v.get("result", v) if isinstance(v, dict) and set(v) == {"result"} else v
        else:
            texte = "".join(c.get("text", "") for c in r.get("content") or [] if c.get("type") == "text")
            try:
                v = json.loads(texte)
            except ValueError:
                v = texte
        out.append({"erreur": bool(r.get("isError")), "valeur": v})
    return out


def lister_outils(env: dict | None = None) -> list[str]:
    msgs = [{"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                                                           "clientInfo": {"name": "tests-atelier", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"}, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}]
    rep, stderr = _echanger(msgs, {1}, env, 60)
    if 1 not in rep:
        raise RuntimeError(stderr[-800:])
    return [t["name"] for t in rep[1]["result"]["tools"]]
