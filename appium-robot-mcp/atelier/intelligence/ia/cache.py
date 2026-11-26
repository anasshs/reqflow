"""Cache des réponses des modèles : une même demande (même opération, même consigne, même modèle, mêmes données) n'est
pas reposée tant que ses sources n'ont pas changé et que sa durée de validité court.

Clé : empreinte de l'opération, de la consigne (version du prompt), du modèle et de la demande. Validité : la réponse
garde les versions des sources au moment de l'appel (copie Xray des tests, exigences Jira, Knowledge Graph, règles
Cursor) ; si l'une a changé, la réponse est écartée. Invalidation sélective par opération, module QA ou source.
Le cache ne concerne que les appels directs : avec Cursor, ses jugements déposés sont déjà conservés par l'atelier.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

SOURCES = ("tests", "exigences", "graphe", "regles")


def cle(operation: str, systeme: str, modele: str, demande: str) -> str:
    h = hashlib.sha256()
    for p in (operation, hashlib.sha256(systeme.encode()).hexdigest(), modele, demande):
        h.update(p.encode("utf-8", "ignore") + b"\x00")
    return h.hexdigest()


def _signature(f) -> str:
    try:
        st = f.stat()
        return f"{st.st_size}:{st.st_mtime_ns}"
    except OSError:
        return ""


def versions() -> dict:
    """Version courante de chaque source (signature de fichier ou empreinte) ; « » quand elle est introuvable."""
    out = {}
    try:
        from atelier.intelligence import patrimoine_xray

        out["tests"] = _signature(patrimoine_xray.fichier())
    except Exception:  # noqa: BLE001
        out["tests"] = ""
    try:
        from atelier.intelligence import couverture_exigences

        out["exigences"] = _signature(couverture_exigences._fichier("exigences.json"))
    except Exception:  # noqa: BLE001
        out["exigences"] = ""
    try:
        from atelier.discovery import connaissance

        out["graphe"] = connaissance._empreinte_projet()[0]
    except Exception:  # noqa: BLE001
        out["graphe"] = ""
    try:
        from atelier.integrations import regles_cursor

        out["regles"] = str(regles_cursor.etat().get("active") or "")
    except Exception:  # noqa: BLE001
        out["regles"] = ""
    return out


def lire(k: str, courantes: dict | None = None) -> dict | None:
    from atelier.intelligence.ia import journal

    l = journal.lire("SELECT * FROM cache WHERE cle = ?", (k,))
    if not l:
        return None
    e = l[0]
    if e["expire"] and e["expire"] < journal.maintenant():
        journal.executer("DELETE FROM cache WHERE cle = ?", (k,))
        return None
    courantes = courantes if courantes is not None else versions()
    gardees = json.loads(e["versions"] or "{}")
    if any(gardees.get(s, "") != courantes.get(s, "") for s in SOURCES):
        journal.executer("DELETE FROM cache WHERE cle = ?", (k,))
        return None
    return e


def ecrire(k: str, operation: str, module: str, modele: str, valeur: str, tokens: int, duree_heures: float, courantes: dict | None = None):
    from atelier.intelligence.ia import journal

    expire = (datetime.now().astimezone() + timedelta(hours=float(duree_heures))).isoformat(timespec="seconds") if duree_heures else ""
    journal.executer("INSERT OR REPLACE INTO cache VALUES (?,?,?,?,?,?,?,?,?)",
                     (k, operation, module, modele, journal.maintenant(), expire, json.dumps(courantes if courantes is not None else versions()),
                      valeur, int(tokens)))


def invalider(operation: str = "", module: str = "", source: str = "") -> int:
    """Supprime les réponses d'une opération, d'un module QA, ou dépendant d'une source (toutes en dépendent) ; tout sinon."""
    from atelier.intelligence.ia import journal

    if operation:
        return journal.executer("DELETE FROM cache WHERE operation = ?", (operation,))
    if module:
        return journal.executer("DELETE FROM cache WHERE module = ?", (module,))
    if source and source not in SOURCES:
        raise ValueError(f"Source : {', '.join(SOURCES)}.")
    return journal.executer("DELETE FROM cache", ())


def etat() -> dict:
    from atelier.intelligence.ia import journal

    l = journal.lire("SELECT operation, module, COUNT(*) n, SUM(tokens_evites) t FROM cache GROUP BY operation, module ORDER BY n DESC")
    return {"entrees": sum(x["n"] for x in l), "par_operation": l, "versions": versions(), "sources": SOURCES}
