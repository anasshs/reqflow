"""Commandes en ligne de l'atelier.

    python -m atelier xray-sync <dossier>    rejoue les journaux Xray non envoyés d'un run
                                             (ou de tous les runs sous ce dossier)
    python -m atelier xray-verifier          compare les appels du client au schéma GraphQL réel
    python -m atelier xray-statuts --projet TAM   contrôle XRAY_STATUTS avec les statuts réels du projet
    python -m atelier xray-import --projet TAM    importe les définitions Xray des tests (lecture seule dans Xray)
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


def xray_verifier(sortie: str = "") -> int:
    from atelier.integrations.xray import base_url
    from atelier.integrations.xray.verification import rapport_markdown, verifier

    res = verifier()
    texte = rapport_markdown(res, base_url())
    if sortie:
        Path(sortie).write_text(texte, "utf-8")
    print(texte)
    return 0 if res["ok"] else 1


def xray_statuts(projet: str) -> int:
    """Lecture seule : aucune écriture dans Xray."""
    from atelier.execution.journal_xray import controler_statuts
    from atelier.integrations.xray import XrayClient

    x = XrayClient()
    statuts = x.statuts(x.id_projet(projet))
    c = controler_statuts(statuts)
    print(f"Statuts de test run du projet {projet} : " + ", ".join(
        f"{s['name']}{' (final)' if s.get('final') else ''}" for s in statuts))
    for ligne in c["lignes"]:
        print(f"  {ligne['robot']:<10} -> {ligne['xray']:<12} {ligne['etat']}")
    if c["non_finaux_manquants"]:
        print("Statuts non finaux à déclarer dans XRAY_STATUTS_NON_FINAUX : " + ", ".join(c["non_finaux_manquants"]))
    print("Résultat : " + ("conforme" if c["ok"] else "à corriger (XRAY_STATUTS / XRAY_STATUTS_NON_FINAUX)"))
    return 0 if c["ok"] else 1


def xray_import(projet: str, jql: str = "") -> int:
    from atelier.intelligence.patrimoine_xray import completer_depuis_xray

    r = completer_depuis_xray(projet, jql)
    print(json.dumps({k: r.get(k) for k in ("fichier", "source", "nb_tests", "importes", "introuvables", "champs_absents")},
                     ensure_ascii=False, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m atelier", description="Atelier d'automatisation")
    sous = p.add_subparsers(dest="commande", required=True)
    s = sous.add_parser("xray-sync", help="Rejoue les journaux Xray non envoyés")
    s.add_argument("dossier", help="Dossier d'un run (xray_outbox.jsonl) ou dossier parent")
    v = sous.add_parser("xray-verifier", help="Vérifie les appels Xray par introspection du schéma")
    v.add_argument("--sortie", default="", help="Fichier Markdown du résultat (ex. docs/XRAY_API_resultat.md)")
    st = sous.add_parser("xray-statuts", help="Contrôle la table des statuts avec les statuts réels du projet Xray")
    st.add_argument("--projet", required=True, help="Clé du projet Jira (ex. TAM) ou son identifiant numérique")
    im = sous.add_parser("xray-import", help="Importe les définitions de tests Xray dans l'instantané du projet")
    im.add_argument("--projet", default="", help="Clé du projet (utilisée sans instantané existant)")
    im.add_argument("--jql", default="", help="JQL des tests à importer (remplace l'instantané)")
    args = p.parse_args(argv)
    if args.commande == "xray-sync":
        return xray_sync(args.dossier)
    if args.commande == "xray-verifier":
        return xray_verifier(args.sortie)
    if args.commande == "xray-import":
        return xray_import(args.projet, args.jql)
    if args.commande == "xray-statuts":
        return xray_statuts(args.projet)
    return 2


if __name__ == "__main__":
    sys.exit(main())
