"""Environnements de test du projet : lus dans le projet Xray, jamais saisis dans les paramètres du projet.

Source (décision de l'utilisateur du 2026-11-18) : les « Test Environments » du projet Xray. Deux lectures, toutes deux
choisies par introspection du schéma (rien n'est supposé, un champ absent est signalé) :
  1. les paramètres du projet Xray (getProjectSettings › testEnvironments) ;
  2. à défaut, les environnements portés par les Test Executions récentes du projet.

La liste est gardée dans le projet de tests (studio/environnements_xray.json) avec sa date et sa source : l'atelier
reste utilisable sans réseau (une indisponibilité de Xray n'interrompt jamais le travail). Sans aucune lecture réussie,
les environnements qui ont un fichier de jeux de données (data/jdd/<env>.yaml) servent de secours, présentés comme tels.

Un environnement Xray et un fichier de jeux de données se correspondent sans tenir compte de la casse (« RECETTE » /
recette.yaml).
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime

from atelier.domain import projet

AGE_MAX_S = 12 * 3600
SECOURS = "jeux de données du projet (secours : Xray pas encore lu)"
_en_cours = threading.Lock()


def _fichier():
    return projet.PROJECT_DIR / "studio" / "environnements_xray.json"


def lire() -> dict:
    f = _fichier()
    try:
        return json.loads(f.read_text("utf-8")) if f.exists() else {}
    except ValueError:
        return {}


def _jdd() -> list[str]:
    from atelier.execution import jdd

    try:
        return jdd.environnements()
    except Exception:  # noqa: BLE001 — pas de dossier de données
        return []


def synchroniser(xray=None, cle: str = "") -> dict:
    """Lit les environnements du projet Xray et les garde dans le projet de tests. Erreur explicite si le projet Xray
    n'est pas déclaré ou si Xray n'est pas configuré ; la dernière liste lue reste alors en place."""
    from atelier.domain import projets
    from atelier.integrations.xray import XrayClient

    cle = cle or projets.cle_xray()
    if not cle:
        raise ValueError("Aucun projet Xray déclaré pour ce projet (Paramètres › Projets, clé du projet Xray).")
    r = (xray or XrayClient()).environnements(cle)
    d = {"projet": cle, "date": datetime.now().astimezone().isoformat(timespec="seconds"), "source": r["source"],
         "environnements": r["environnements"], "absents": r["absents"]}
    f = _fichier()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d, ensure_ascii=False, indent=1), "utf-8")
    return etat()


def liste() -> list[str]:
    """Environnements du projet : ceux lus dans Xray ; sinon, en secours, ceux des fichiers de jeux de données."""
    return list(lire().get("environnements") or []) or _jdd()


def etat() -> dict:
    """Pour l'interface : environnements, d'où ils viennent, quand ils ont été lus, et lesquels ont des jeux de données."""
    from atelier.domain import projets

    d, jdd = lire(), {e.casefold() for e in _jdd()}
    noms = list(d.get("environnements") or [])
    return {"environnements": [{"nom": n, "jeux_de_donnees": n.casefold() in jdd} for n in (noms or _jdd())],
            "source": d.get("source") if noms else (SECOURS if jdd else ""), "date": d.get("date", ""), "projet": d.get("projet") or projets.cle_xray(),
            "depuis_xray": bool(noms), "absents": d.get("absents") or [],
            "sans_environnement": [e for e in _jdd() if noms and e.casefold() not in {n.casefold() for n in noms}]}


def assurer() -> None:
    """Relit Xray en arrière-plan quand la liste manque, date de plus de 12 h ou vient d'un autre projet Xray. Ne lève
    jamais et ne bloque jamais l'interface ; sans identifiants Xray, ne fait rien."""
    import os

    from atelier.domain import projets

    d, cle = lire(), projets.cle_xray()
    if not cle or not os.environ.get("XRAY_CLIENT_ID"):
        return
    try:
        age = time.time() - datetime.fromisoformat(d["date"]).timestamp() if d.get("date") else AGE_MAX_S + 1
    except ValueError:
        age = AGE_MAX_S + 1
    if d.get("projet") == cle and age < AGE_MAX_S:
        return

    def tache():
        if not _en_cours.acquire(blocking=False):
            return
        try:
            synchroniser()
        except Exception:  # noqa: BLE001 — Xray indisponible : la dernière liste reste en place
            pass
        finally:
            _en_cours.release()

    threading.Thread(target=tache, daemon=True).start()
