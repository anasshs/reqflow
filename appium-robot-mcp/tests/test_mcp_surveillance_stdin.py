"""Serveur MCP HTTP démarré par l'atelier : la surveillance de son entrée (arrêt avec l'atelier) ne doit pas bloquer les
processus qu'il lance (run Robot, git…). Sous Windows, un fils qui héritait du tube lu par la surveillance restait bloqué
dès son démarrage."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

SCRIPT = textwrap.dedent("""
    import os, subprocess, sys, threading
    sys.path.insert(0, sys.argv[1])
    from atelier.adapters.mcp.server import _detacher_stdin
    canal = _detacher_stdin()
    fin = threading.Event()
    def surveiller():
        while os.read(canal, 4096):
            pass
        fin.set()
    threading.Thread(target=surveiller, daemon=True).start()
    # le fils hérite de l'entrée standard du processus : il doit démarrer et finir malgré la lecture en cours
    r = subprocess.run([sys.executable, "-c", "print('fils ok')"], stdout=subprocess.PIPE, text=True, timeout=30)
    print(r.stdout.strip(), flush=True)
    print("surveillance terminée" if fin.wait(30) else "surveillance bloquée", flush=True)
""")


def test_un_fils_demarre_pendant_la_surveillance_et_la_surveillance_voit_la_fin_du_tube():
    p = subprocess.Popen([sys.executable, "-c", SCRIPT, str(RACINE)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, encoding="utf-8", cwd=RACINE,
                         env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    premiere = p.stdout.readline().strip()  # le fils a démarré et fini alors que le tube est encore ouvert
    p.stdin.close()  # l'atelier s'arrête : fin du flux
    reste, erreurs = p.communicate(timeout=60)
    assert premiere == "fils ok", erreurs
    assert reste.strip() == "surveillance terminée", erreurs
