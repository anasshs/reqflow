"""Commandes en ligne de l'atelier.

    python -m atelier xray-sync <dossier>    rejoue les journaux Xray non envoyés d'un run
                                             (ou de tous les runs sous ce dossier)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from atelier.execution.journal_xray import OUTBOX, Synchroniseur


def dossiers_a_synchroniser(racine: Path) -> list[Path]:
    if (racine / OUTBOX).exists():
        return [racine]
    return sorted(p.parent for p in racine.rglob(OUTBOX))


def xray_sync(dossier: str) -> int:
    racine = Path(dossier).expanduser().resolve()
    dossiers = dossiers_a_synchroniser(racine)
    if not dossiers:
        print(f"Aucun journal Xray ({OUTBOX}) sous {racine}.", file=sys.stderr)
        return 2
    code = 0
    for d in dossiers:
        def journaliser(niveau, msg, **_):
            print(f"[{niveau}] {msg}", file=sys.stderr)
        bilan = Synchroniseur(d, journaliser=journaliser).envoyer_tout()
        print(json.dumps({"dossier": str(d), **bilan}, ensure_ascii=False))
        code = code or (1 if bilan["restants"] else 0)
    return code


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m atelier", description="Atelier d'automatisation")
    sous = p.add_subparsers(dest="commande", required=True)
    s = sous.add_parser("xray-sync", help="Rejoue les journaux Xray non envoyés")
    s.add_argument("dossier", help="Dossier d'un run (xray_outbox.jsonl) ou dossier parent")
    args = p.parse_args(argv)
    if args.commande == "xray-sync":
        return xray_sync(args.dossier)
    return 2


if __name__ == "__main__":
    sys.exit(main())
