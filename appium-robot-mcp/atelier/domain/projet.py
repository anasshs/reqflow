"""Projet de tests Robot Framework : emplacement et accès fichiers sûrs.

Les moteurs lisent PROJECT_DIR / SNAP_DIR au moment de l'appel (jamais copiés à l'import) :
un seul endroit à régler, y compris dans les tests.
"""
from __future__ import annotations

import contextvars
import os
import re
import unicodedata
from contextlib import contextmanager
from pathlib import Path

# Dossier de l'outil (contient atelier/, les points d'entrée historiques et le socle Robot).
RACINE_OUTIL = Path(__file__).resolve().parent.parent.parent

PROJECT_DIR = Path(os.environ.get("ROBOT_PROJECT_DIR", Path.cwd())).expanduser().resolve()
SNAP_DIR = Path(os.environ.get("MCP_SNAPSHOT_DIR", PROJECT_DIR / ".mcp_snapshots")).expanduser()


def dossier() -> Path:
    return PROJECT_DIR


def snapshots() -> Path:
    return SNAP_DIR


# --------------------------------------------------------------------------- code des tests : dépôt de l'application
# Le code généré vit au niveau de l'APPLICATION : chaque application peut avoir son dépôt (fiche : depot.dossier), commité
# et fusionné vers le GitLab de l'application. La connaissance de l'atelier (carte, BDD, graphe, Discovery, releases,
# résultats des runs) reste dans le projet. Sans dépôt déclaré, le code reste dans le projet (comportement historique).
CODE = ("tests", "resources", "libraries", "data/jdd", "args", "uiautomator", "espresso", "xcuitest")
# Une application peut avoir PLUSIEURS dépôts, chacun pour une ou des technologies (fiche : depots [{technologies, dossier,
# gitlab_url, gitlab_projet, branche}] ; l'ancien « depot » unique vaut pour les technologies Robot). Pendant la génération
# ou l'exécution d'une technologie (pour_technologie), les chemins relatifs du code se résolvent dans SON dépôt.
_cache_depot: dict = {}
_techno = contextvars.ContextVar("technologie_code", default="")


@contextmanager
def pour_technologie(technologie: str):
    """Les chemins du code se résolvent dans le dépôt de cette technologie le temps du bloc (génération, exécution)."""
    jeton = _techno.set(str(technologie or ""))
    try:
        yield
    finally:
        _techno.reset(jeton)


def technologie_courante() -> str:
    return _techno.get()


def depots_application() -> list[dict]:
    """Dépôts de l'application active, normalisés : [{technologies, dossier, gitlab_url, gitlab_projet, branche}]."""
    try:
        from atelier.discovery import carte

        app = carte.app_courante()
        cfg = (carte.config_app(app) or {}) if app else {}
    except Exception:  # noqa: BLE001 — aucune application, carte illisible : pas de dépôt propre
        return []
    out = [dict(d, technologies=list(d.get("technologies") or [])) for d in cfg.get("depots") or [] if isinstance(d, dict)]
    if cfg.get("depot"):  # forme historique : un seul dépôt, celui des tests Robot
        out.append(dict(cfg["depot"], technologies=list(cfg["depot"].get("technologies") or ["robot"])))
    return out


def _famille(t: str) -> str:
    return "robot" if not t or t.startswith("robot") else t


def depot_application(technologie: str | None = None) -> dict:
    """Dépôt de la technologie (celle en cours si non précisée) : celui qui la déclare, ou sa famille (robot-appium →
    « robot »), sinon un dépôt sans technologie déclarée ; {} si aucun."""
    t = _techno.get() if technologie is None else technologie
    depots = depots_application()
    for d in depots:
        if t and t in d["technologies"]:
            return d
    for d in depots:
        if _famille(t) in [_famille(x) for x in d["technologies"]]:
            return d
    return next((d for d in depots if not d["technologies"]), {})


def racine_code(technologie: str | None = None) -> Path:
    """Racine du code de la technologie : son dépôt s'il est déclaré pour l'application active, sinon le projet."""
    t = _techno.get() if technologie is None else technologie
    try:
        f = PROJECT_DIR / os.environ.get("APP_MAP_DIR", "app_map") / ".app_courante"
        cle = (str(PROJECT_DIR), f.stat().st_mtime_ns if f.exists() else 0, _mtime_fiche(), _famille(t), t)
    except OSError:
        cle = (str(PROJECT_DIR), 0, 0, _famille(t), t)
    if cle not in _cache_depot:
        d = str(depot_application(t).get("dossier") or "").strip()
        p = Path(d).expanduser() if d else None
        _cache_depot.clear() if len(_cache_depot) > 64 else None
        _cache_depot[cle] = (p if p.is_absolute() else PROJECT_DIR / p).resolve() if p else PROJECT_DIR
    return _cache_depot[cle]


def racines_code() -> list[Path]:
    """Toutes les racines de code de l'application active (pour autoriser un chemin absolu dans l'une d'elles)."""
    out = [racine_code()]
    for d in depots_application():
        if d.get("dossier"):
            p = Path(d["dossier"]).expanduser()
            out.append((p if p.is_absolute() else PROJECT_DIR / p).resolve())
    return list(dict.fromkeys(out))


def _mtime_fiche() -> int:
    try:
        racine = PROJECT_DIR / os.environ.get("APP_MAP_DIR", "app_map")
        app = (racine / ".app_courante").read_text("utf-8").strip()
        return (racine / app / "app.yaml").stat().st_mtime_ns
    except OSError:
        return 0


def est_code(rel: str) -> bool:
    r = str(rel).replace("\\", "/").lstrip("./")
    return any(r == c or r.startswith(c + "/") for c in CODE)


def safe_path(rel: str) -> Path:
    """Empêche toute lecture/écriture hors du projet de tests (et des dépôts de code de l'application active).
    Dans le bloc d'une technologie qui a son propre dépôt, tout chemin relatif se résout dans ce dépôt."""
    code = racine_code()
    dedie = bool(_techno.get()) and code != PROJECT_DIR and bool(depot_application().get("dossier"))
    base = code if (dedie or est_code(rel)) else PROJECT_DIR
    p = (base / rel).resolve()
    for racine in dict.fromkeys([base, PROJECT_DIR, *racines_code()]):
        if p == racine or racine in p.parents:
            return p
    raise ValueError(f"Chemin hors du projet interdit : {rel}")


def relatif(p) -> str:
    """Chemin affiché et passé aux outils : relatif au dépôt de code s'il le contient, sinon au projet."""
    p = Path(p).resolve()
    for racine in dict.fromkeys([racine_code(), PROJECT_DIR, *racines_code()]):
        if p == racine or racine in p.parents:
            return p.relative_to(racine).as_posix()
    raise ValueError(f"Chemin hors du projet : {p}")


def slug(text: str, max_len: int = 40, defaut: str = "element") -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text[:max_len] or defaut


def lister_fichiers(pattern: str = "**/*.robot") -> list[str]:
    base = racine_code()
    return sorted(p.relative_to(base).as_posix() for p in base.glob(pattern)
                  if ".mcp_snapshots" not in p.parts)[:500]


def lire_fichier(path: str) -> str:
    return safe_path(path).read_text("utf-8")


def ecrire_fichier(path: str, content: str, overwrite: bool = False) -> str:
    """Écrit dans le projet ; refuse d'écraser sans overwrite=True."""
    from atelier.domain import evenements

    target = safe_path(path)
    if target.exists() and not overwrite:
        raise FileExistsError(f"{path} existe déjà (overwrite=True pour remplacer).")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, "utf-8")
    evenements.publier({"type": "outil", "nom": "write_project_file", "args": {"path": path}})
    return f"Écrit : {target}"
