"""Base de l'atelier : un magasin de documents (style NoSQL) pour les projets, la configuration, les comptes et, phase
par phase, la connaissance et le travail en cours (docs/BASE_ATELIER.md).

Chaque document est un objet JSON rangé par (collection, clé), avec un numéro de version : une écriture qui donne la
version qu'elle a lue est refusée si quelqu'un a écrit entre-temps (Conflit), pour que deux postes ne s'écrasent jamais.
Chaque écriture est journalisée (qui, quand, quelle version).

Base locale (défaut) : SQLite, fourni avec Python, un seul fichier (~/.atelier/atelier.db), aucun service qui tourne :
rien ne ralentit le poste. Mode WAL : lectures pendant les écritures. Pour la déplacer (autre poste, serveur partagé) :
exporter() puis importer() ; le serveur partagé est un autre « moteur » derrière la même interface (phase 4).

Emplacement : ATELIER_BASE (chemin du fichier), sinon la configuration du poste (~/.atelier/poste.json), sinon le
défaut. Aucun secret n'y est jamais écrit : mots de passe des comptes en empreinte PBKDF2 seulement, jetons des
outils dans le coffre du système.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  collection TEXT NOT NULL, cle TEXT NOT NULL, doc TEXT NOT NULL, version INTEGER NOT NULL,
  modifie TEXT NOT NULL, par TEXT NOT NULL DEFAULT '', PRIMARY KEY (collection, cle));
CREATE TABLE IF NOT EXISTS journal (
  id INTEGER PRIMARY KEY AUTOINCREMENT, collection TEXT NOT NULL, cle TEXT NOT NULL, version INTEGER NOT NULL,
  operation TEXT NOT NULL, par TEXT NOT NULL DEFAULT '', date TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS journal_doc ON journal (collection, cle);
CREATE TABLE IF NOT EXISTS meta (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL);
"""
FORMAT = 1


class Conflit(Exception):
    """Le document a changé depuis sa lecture (autre poste, autre onglet) : relire, puis réappliquer."""


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def dossier_poste() -> Path:
    return Path(os.environ.get("ATELIER_DOSSIER") or Path.home() / ".atelier").expanduser()


def _config_poste() -> dict:
    f = dossier_poste() / "poste.json"
    try:
        return json.loads(f.read_text("utf-8")) if f.exists() else {}
    except (OSError, ValueError):
        return {}


def regler_poste(**valeurs) -> dict:
    """Configuration du poste (où est la base) : ~/.atelier/poste.json, jamais de secret."""
    d = dossier_poste()
    d.mkdir(parents=True, exist_ok=True)
    c = {**_config_poste(), **valeurs}
    tmp = d / "poste.json.tmp"
    tmp.write_text(json.dumps(c, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(d / "poste.json")
    return c


def chemin_base() -> Path:
    if os.environ.get("ATELIER_BASE"):
        return Path(os.environ["ATELIER_BASE"]).expanduser()
    b = (_config_poste().get("base") or {})
    if b.get("type", "locale") == "locale" and b.get("chemin"):
        return Path(b["chemin"]).expanduser()
    return dossier_poste() / "atelier.db"


def config_base() -> dict:
    """Base choisie pour ce poste : {"type": "locale", "chemin"} ou {"type": "serveur", "url", "ca"}."""
    if os.environ.get("ATELIER_BASE"):
        return {"type": "locale", "chemin": os.environ["ATELIER_BASE"]}
    return _config_poste().get("base") or {"type": "locale"}


def configuree() -> bool:
    """La base a été choisie (assistant du premier lancement) ou existe déjà."""
    return bool(os.environ.get("ATELIER_BASE")) or bool(_config_poste().get("base")) or chemin_base().exists()


class BaseLocale:
    """Moteur SQLite : documents JSON, versions, journal."""

    def __init__(self, chemin: Path):
        self.chemin = Path(chemin)
        self._local = threading.local()
        self._verrou = threading.Lock()
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        with self._cx() as cx:
            cx.executescript(SCHEMA)
            cx.execute("INSERT OR IGNORE INTO meta VALUES ('format', ?)", (str(FORMAT),))
            cx.execute("INSERT OR IGNORE INTO meta VALUES ('cree', ?)", (_maintenant(),))

    def _cx(self) -> sqlite3.Connection:
        cx = getattr(self._local, "cx", None)
        if cx is None:
            cx = sqlite3.connect(str(self.chemin), timeout=10, isolation_level=None, check_same_thread=False)
            cx.execute("PRAGMA journal_mode=WAL")
            cx.execute("PRAGMA synchronous=NORMAL")
            cx.execute("PRAGMA foreign_keys=ON")
            self._local.cx = cx
        return cx

    def fermer(self):
        cx = getattr(self._local, "cx", None)
        if cx is not None:
            cx.close()
            self._local.cx = None

    # ------------------------------------------------------------------ documents
    def lire(self, collection: str, cle: str) -> dict | None:
        r = self._cx().execute("SELECT doc, version, modifie, par FROM documents WHERE collection=? AND cle=?", (collection, cle)).fetchone()
        if not r:
            return None
        d = json.loads(r[0])
        return {**d, "_version": r[1], "_modifie": r[2], "_par": r[3]} if isinstance(d, dict) else {"valeur": d, "_version": r[1]}

    def ecrire(self, collection: str, cle: str, doc: dict, version: int | None = None, par: str = "") -> int:
        """Écrit le document ; version = celle lue (None : écriture sans contrôle). Rend la nouvelle version."""
        if not collection or not cle:
            raise ValueError("Collection et clé obligatoires.")
        propre = {k: v for k, v in (doc or {}).items() if not str(k).startswith("_")}
        texte = json.dumps(propre, ensure_ascii=False, default=str)
        with self._verrou:
            cx = self._cx()
            cx.execute("BEGIN IMMEDIATE")
            try:
                r = cx.execute("SELECT version FROM documents WHERE collection=? AND cle=?", (collection, cle)).fetchone()
                actuelle = r[0] if r else 0
                if version is not None and version != actuelle:
                    raise Conflit(f"{collection}/{cle} a changé (version {actuelle}, lue {version}) : relire avant d'écrire.")
                nouvelle, date = actuelle + 1, _maintenant()
                cx.execute("INSERT INTO documents VALUES (?,?,?,?,?,?) ON CONFLICT(collection, cle) DO UPDATE SET doc=excluded.doc, "
                           "version=excluded.version, modifie=excluded.modifie, par=excluded.par", (collection, cle, texte, nouvelle, date, par))
                cx.execute("INSERT INTO journal (collection, cle, version, operation, par, date) VALUES (?,?,?,?,?,?)",
                           (collection, cle, nouvelle, "creation" if not r else "modification", par, date))
                cx.execute("COMMIT")
            except BaseException:
                cx.execute("ROLLBACK")
                raise
        return nouvelle

    def supprimer(self, collection: str, cle: str, version: int | None = None, par: str = "") -> bool:
        with self._verrou:
            cx = self._cx()
            cx.execute("BEGIN IMMEDIATE")
            try:
                r = cx.execute("SELECT version FROM documents WHERE collection=? AND cle=?", (collection, cle)).fetchone()
                if not r:
                    cx.execute("ROLLBACK")
                    return False
                if version is not None and version != r[0]:
                    raise Conflit(f"{collection}/{cle} a changé (version {r[0]}, lue {version}).")
                cx.execute("DELETE FROM documents WHERE collection=? AND cle=?", (collection, cle))
                cx.execute("INSERT INTO journal (collection, cle, version, operation, par, date) VALUES (?,?,?,?,?,?)",
                           (collection, cle, r[0] + 1, "suppression", par, _maintenant()))
                cx.execute("COMMIT")
            except BaseException:
                cx.execute("ROLLBACK")
                raise
        return True

    def lister(self, collection: str, prefixe: str = "") -> list[dict]:
        rows = self._cx().execute("SELECT cle, doc, version, modifie, par FROM documents WHERE collection=? AND cle LIKE ? ESCAPE '\\' ORDER BY cle",
                                  (collection, prefixe.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")).fetchall()
        out = []
        for cle, doc, v, mod, par in rows:
            d = json.loads(doc)
            out.append({**(d if isinstance(d, dict) else {"valeur": d}), "_cle": cle, "_version": v, "_modifie": mod, "_par": par})
        return out

    def versions(self, collection: str) -> dict:
        """{clé: version} d'une collection, sans lire les documents (synchronisation)."""
        return dict(self._cx().execute("SELECT cle, version FROM documents WHERE collection=?", (collection,)).fetchall())

    def historique(self, collection: str, cle: str, limite: int = 50) -> list[dict]:
        rows = self._cx().execute("SELECT version, operation, par, date FROM journal WHERE collection=? AND cle=? ORDER BY id DESC LIMIT ?",
                                  (collection, cle, limite)).fetchall()
        return [dict(zip(("version", "operation", "par", "date"), r)) for r in rows]

    # ------------------------------------------------------------------ déplacer la base
    def exporter(self, fichier: Path) -> dict:
        """Tous les documents, une ligne JSON chacun (avec version) : pour déplacer la base ou la sauvegarder."""
        n = 0
        fichier = Path(fichier)
        fichier.parent.mkdir(parents=True, exist_ok=True)
        with fichier.open("w", encoding="utf-8") as f:
            for c, k, doc, v, mod, par in self._cx().execute("SELECT collection, cle, doc, version, modifie, par FROM documents ORDER BY collection, cle"):
                f.write(json.dumps({"collection": c, "cle": k, "doc": json.loads(doc), "version": v, "modifie": mod, "par": par}, ensure_ascii=False) + "\n")
                n += 1
        return {"fichier": str(fichier), "documents": n}

    def importer(self, fichier: Path, par: str = "import") -> dict:
        """Charge un export : un document déjà présent n'est remplacé que si l'export en a une version plus récente."""
        ajoutes = ignores = 0
        for ligne in Path(fichier).read_text("utf-8").splitlines():
            if not ligne.strip():
                continue
            x = json.loads(ligne)
            actuel = self.lire(x["collection"], x["cle"])
            if actuel and actuel["_version"] >= int(x.get("version") or 0):
                ignores += 1
                continue
            with self._verrou:  # même version que dans la base d'origine : un nouvel import ne recopie rien
                cx = self._cx()
                cx.execute("INSERT INTO documents VALUES (?,?,?,?,?,?) ON CONFLICT(collection, cle) DO UPDATE SET doc=excluded.doc, "
                           "version=excluded.version, modifie=excluded.modifie, par=excluded.par",
                           (x["collection"], x["cle"], json.dumps(x["doc"], ensure_ascii=False), int(x.get("version") or 1),
                            x.get("modifie") or _maintenant(), x.get("par") or par))
                cx.execute("INSERT INTO journal (collection, cle, version, operation, par, date) VALUES (?,?,?,?,?,?)",
                           (x["collection"], x["cle"], int(x.get("version") or 1), "import", par, _maintenant()))
            ajoutes += 1
        return {"importes": ajoutes, "ignores": ignores}

    def info(self) -> dict:
        cx = self._cx()
        par_collection = dict(cx.execute("SELECT collection, COUNT(*) FROM documents GROUP BY collection").fetchall())
        meta = dict(cx.execute("SELECT cle, valeur FROM meta").fetchall())
        return {"type": "locale", "moteur": "SQLite (documents JSON)", "chemin": str(self.chemin),
                "taille_ko": round(self.chemin.stat().st_size / 1024) if self.chemin.exists() else 0,
                "documents": sum(par_collection.values()), "collections": par_collection, "cree": meta.get("cree", ""), "format": meta.get("format", "")}


class BaseDistante:
    """Moteur serveur : la même interface, servie par le serveur de données de l'atelier (atelier/serveur_donnees.py)
    en HTTPS. Chaque appel porte le jeton du compte connecté sur le serveur (domain/utilisateurs) ; le serveur vérifie
    les droits (rôle, projets). Bibliothèque standard seulement (urllib, ssl)."""

    def __init__(self, url: str, ca: str = ""):
        self.url = url.rstrip("/")
        self.ca = ca
        self.chemin = Path(self.url)  # identifiant de la base (comparé pour savoir si elle a changé)
        self.jeton_fond = ""  # jeton du dernier compte connecté : sert à la synchronisation de fond

    def _contexte(self):
        import ssl

        if not self.url.startswith("https://"):
            return None
        return ssl.create_default_context(cafile=self.ca or os.environ.get("ATELIER_SERVEUR_CA") or None)

    def appel(self, route: str, corps: dict | None = None, jeton: str | None = None, delai: float = 30) -> dict:
        import urllib.error
        import urllib.request

        if jeton is None:
            from atelier.domain import utilisateurs

            jeton = utilisateurs.jeton_serveur() or self.jeton_fond
        req = urllib.request.Request(f"{self.url}/v1/{route}", data=json.dumps(corps or {}).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {jeton}"} if jeton else {})})
        try:
            with urllib.request.urlopen(req, timeout=delai, context=self._contexte()) as r:
                return json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read().decode("utf-8")).get("detail", "")
            except Exception:  # noqa: BLE001
                detail = ""
            detail = detail or f"erreur {e.code}"
            if e.code == 409:
                raise Conflit(detail) from None
            if e.code in (401, 403):
                raise PermissionError(detail) from None
            if e.code == 404:
                raise KeyError(detail) from None
            raise ValueError(detail) from None
        except urllib.error.URLError as e:
            raise ConnectionError(f"Serveur de données injoignable ({self.url}) : {e.reason}") from None

    def lire(self, collection, cle):
        return self.appel("lire", {"collection": collection, "cle": cle}).get("doc")

    def ecrire(self, collection, cle, doc, version=None, par=""):
        propre = {k: v for k, v in (doc or {}).items() if not str(k).startswith("_")}
        return self.appel("ecrire", {"collection": collection, "cle": cle, "doc": propre, "version": version, "par": par})["version"]

    def supprimer(self, collection, cle, version=None, par=""):
        return self.appel("supprimer", {"collection": collection, "cle": cle, "version": version, "par": par})["supprime"]

    def lister(self, collection, prefixe=""):
        return self.appel("lister", {"collection": collection, "prefixe": prefixe})["docs"]

    def versions(self, collection):
        return self.appel("versions", {"collection": collection})["versions"]

    def historique(self, collection, cle, limite=50):
        return self.appel("historique", {"collection": collection, "cle": cle, "limite": limite})["historique"]

    def info(self):
        return {**self.appel("info"), "type": "serveur", "url": self.url}

    def exporter(self, fichier):
        lignes = self.appel("exporter", delai=300)["lignes"]
        fichier = Path(fichier)
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lignes), "utf-8")
        return {"fichier": str(fichier), "documents": len(lignes)}

    def importer(self, fichier, par="import"):
        lignes = [json.loads(x) for x in Path(fichier).read_text("utf-8").splitlines() if x.strip()]
        total = {"importes": 0, "ignores": 0}
        for i in range(0, len(lignes), 200):
            r = self.appel("importer", {"lignes": lignes[i:i + 200], "par": par}, delai=300)
            total = {k: total[k] + r.get(k, 0) for k in total}
        return total

    def fermer(self):
        pass


_BASE = None
_VERROU = threading.Lock()


def base():
    """La base du poste : locale (fichier SQLite) ou serveur (serveur de données de l'atelier), selon la configuration."""
    global _BASE
    c = config_base()
    with _VERROU:
        if c.get("type") == "serveur" and c.get("url"):
            if not isinstance(_BASE, BaseDistante) or _BASE.url != c["url"].rstrip("/"):
                _BASE = BaseDistante(c["url"], c.get("ca", ""))
            return _BASE
        chemin = chemin_base()
        if not isinstance(_BASE, BaseLocale) or _BASE.chemin != chemin:
            _BASE = BaseLocale(chemin)
        return _BASE


def distante() -> bool:
    return isinstance(base(), BaseDistante)


def lire(collection: str, cle: str) -> dict | None:
    return base().lire(collection, cle)


def ecrire(collection: str, cle: str, doc: dict, version: int | None = None, par: str = "") -> int:
    return base().ecrire(collection, cle, doc, version, par)


def supprimer(collection: str, cle: str, version: int | None = None, par: str = "") -> bool:
    return base().supprimer(collection, cle, version, par)


def lister(collection: str, prefixe: str = "") -> list[dict]:
    return base().lister(collection, prefixe)


def versions(collection: str) -> dict:
    return base().versions(collection)
