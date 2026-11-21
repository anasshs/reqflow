"""Journal de consommation IA du poste (SQLite, bibliothèque standard) : appels, cache de réponses, entrées rejouables,
historique des réglages, simulations.

Fichier : ATELIER_IA_JOURNAL (défaut ~/.atelier-ia.sqlite), hors du dépôt de tests : il contient des métriques par poste,
et pour le simulateur des demandes déjà masquées. L'écriture d'un appel passe par une file traitée en arrière-plan :
elle ne ralentit jamais l'appel mesuré, et une erreur d'écriture ne le fait jamais échouer.

Fiabilité : chaque appel a un identifiant unique (clé primaire, INSERT OR IGNORE : un événement rejoué n'est pas compté
deux fois) ; « estime » distingue les tokens comptés par le fournisseur des tokens estimés (caractères / 4) ; les sources
(« direct », « agent », « mcp ») ne s'additionnent pas : un appel MCP est une estimation de ce que reçoit Cursor.
"""
from __future__ import annotations

import json
import os
import queue
import sqlite3
import threading
import uuid
from contextlib import closing
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path

CORRELATION: ContextVar[str] = ContextVar("correlation_ia", default="")
CHAMPS = ("id", "correlation", "date", "source", "fournisseur", "modele", "niveau", "operation", "module", "projet", "poste",
          "tokens_entree", "tokens_sortie", "tokens_cache_lus", "tokens_cache_crees", "estime", "duree_ms", "statut", "erreur",
          "cache", "repli", "tokens_avant", "tokens_apres")
SCHEMA = """
CREATE TABLE IF NOT EXISTS appels (id TEXT PRIMARY KEY, correlation TEXT, date TEXT, source TEXT, fournisseur TEXT, modele TEXT,
  niveau TEXT, operation TEXT, module TEXT, projet TEXT, poste TEXT, tokens_entree INTEGER, tokens_sortie INTEGER,
  tokens_cache_lus INTEGER, tokens_cache_crees INTEGER, estime INTEGER, duree_ms INTEGER, statut TEXT, erreur TEXT,
  cache INTEGER, repli INTEGER, tokens_avant INTEGER, tokens_apres INTEGER);
CREATE INDEX IF NOT EXISTS appels_date ON appels(date);
CREATE TABLE IF NOT EXISTS cache (cle TEXT PRIMARY KEY, operation TEXT, module TEXT, modele TEXT, date TEXT, expire TEXT,
  versions TEXT, valeur TEXT, tokens_evites INTEGER);
CREATE TABLE IF NOT EXISTS entrees (id TEXT PRIMARY KEY, date TEXT, operation TEXT, module TEXT, modele TEXT, systeme TEXT,
  demande TEXT, reponse TEXT, max_sortie INTEGER);
CREATE TABLE IF NOT EXISTS reglages (date TEXT, poste TEXT, portee TEXT, avant TEXT, apres TEXT);
CREATE TABLE IF NOT EXISTS simulations (id TEXT PRIMARY KEY, date TEXT, poste TEXT, entree TEXT, operation TEXT, resultats TEXT);
"""
_FILE: "queue.Queue[tuple]" = queue.Queue()
_VERROU = threading.Lock()
_FIL: dict = {"t": None}
_PRET: set = set()


def chemin() -> Path:
    return Path(os.environ.get("ATELIER_IA_JOURNAL") or Path.home() / ".atelier-ia.sqlite").expanduser()


def connexion() -> sqlite3.Connection:
    f = chemin()
    f.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(f, timeout=10)
    c.row_factory = sqlite3.Row
    if str(f) not in _PRET:
        c.executescript(SCHEMA)
        _PRET.add(str(f))
    return c


def maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def poste() -> str:
    try:
        from atelier.intelligence import releases

        return releases._auteur()
    except Exception:  # noqa: BLE001
        return os.environ.get("USERNAME") or os.environ.get("USER") or "poste"


def projet_courant() -> str:
    try:
        from atelier.domain import projets

        p = projets.actif() or {}
        return p.get("nom") or p.get("id") or ""
    except Exception:  # noqa: BLE001
        from atelier.domain import projet

        return projet.PROJECT_DIR.name


def nouvel_id() -> str:
    return uuid.uuid4().hex


def correlation() -> str:
    """Identifiant de corrélation de l'opération en cours (tous ses appels le partagent) ; un nouveau sinon."""
    return CORRELATION.get() or nouvel_id()


class operation:
    """Contexte : `with journal.operation():` regroupe tous les appels IA d'une même opération QA sous un identifiant."""
    def __init__(self, cid: str = ""):
        self.cid, self.jeton = cid or nouvel_id(), None

    def __enter__(self):
        self.jeton = CORRELATION.set(self.cid)
        return self.cid

    def __exit__(self, *_):
        CORRELATION.reset(self.jeton)


# =========================================================================== écriture asynchrone
def _travail():
    while True:
        sql, params, fait = _FILE.get()
        try:
            with _VERROU, closing(connexion()) as c, c:
                c.execute(sql, params)
        except Exception:  # noqa: BLE001 — la mesure ne fait jamais échouer l'atelier
            pass
        finally:
            if fait:
                fait.set()
            _FILE.task_done()


def _ecrire(sql: str, params: tuple, attendre: bool = False):
    if _FIL["t"] is None or not _FIL["t"].is_alive():
        _FIL["t"] = threading.Thread(target=_travail, daemon=True, name="journal-ia")
        _FIL["t"].start()
    fait = threading.Event() if attendre else None
    _FILE.put((sql, params, fait))
    if fait:
        fait.wait(10)


def vider():
    """Attend que toutes les écritures en file soient faites (tests, lecture juste après un appel)."""
    if _FIL["t"] is not None:
        _FILE.join()


def enregistrer_appel(**e) -> str:
    e = {**e, "id": e.get("id") or nouvel_id(), "date": e.get("date") or maintenant(), "correlation": e.get("correlation") or correlation(),
         "projet": e["projet"] if "projet" in e else projet_courant(), "poste": e.get("poste") or poste()}
    valeurs = tuple(int(e.get(k) or 0) if k in ("tokens_entree", "tokens_sortie", "tokens_cache_lus", "tokens_cache_crees", "duree_ms",
                                                 "tokens_avant", "tokens_apres") else int(bool(e.get(k))) if k in ("estime", "cache", "repli")
                    else str(e.get(k) or "")[:2000] for k in CHAMPS)
    _ecrire(f"INSERT OR IGNORE INTO appels ({', '.join(CHAMPS)}) VALUES ({', '.join('?' * len(CHAMPS))})", valeurs)
    return e["id"]


def enregistrer_entree(eid: str, operation: str, module: str, modele: str, systeme: str, demande: str, reponse: str, max_sortie: int,
                       garder: int = 200):
    """Demande déjà masquée, gardée pour le simulateur (les `garder` plus récentes seulement)."""
    _ecrire("INSERT OR REPLACE INTO entrees VALUES (?,?,?,?,?,?,?,?,?)", (eid, maintenant(), operation, module, modele, systeme[:20000],
                                                                          demande[:200000], reponse[:50000], int(max_sortie)))
    _ecrire("DELETE FROM entrees WHERE id NOT IN (SELECT id FROM entrees ORDER BY date DESC LIMIT ?)", (int(garder),))


def historiser_reglage(portee: str, avant: dict, apres: dict):
    _ecrire("INSERT INTO reglages VALUES (?,?,?,?,?)", (maintenant(), poste(), portee, json.dumps(avant, ensure_ascii=False),
                                                         json.dumps(apres, ensure_ascii=False)), attendre=True)


# =========================================================================== lecture
def lire(sql: str, params: tuple = ()) -> list[dict]:
    vider()
    try:
        with closing(connexion()) as c:
            return [dict(r) for r in c.execute(sql, params)]
    except sqlite3.Error:
        return []


def executer(sql: str, params: tuple = ()) -> int:
    """Écriture synchrone (cache, simulations, invalidations) ; rend le nombre de lignes touchées."""
    vider()
    with _VERROU, closing(connexion()) as c, c:
        return c.execute(sql, params).rowcount


def appels(depuis: str = "", jusqu: str = "", **filtres) -> list[dict]:
    """Appels du journal, filtrés (projet, poste, module, operation, fournisseur, modele, source, statut, correlation)."""
    where, params = ["1=1"], []
    if depuis:
        where.append("date >= ?")
        params.append(depuis)
    if jusqu:
        where.append("date < ?")
        params.append(jusqu)
    for k, v in filtres.items():
        if v and k in CHAMPS:
            where.append(f"{k} = ?")
            params.append(v)
    return lire(f"SELECT * FROM appels WHERE {' AND '.join(where)} ORDER BY date", tuple(params))
