"""Projet de tests Robot Framework : emplacement et accès fichiers sûrs.

Les moteurs lisent PROJECT_DIR / SNAP_DIR au moment de l'appel (jamais copiés à l'import) :
un seul endroit à régler, y compris dans les tests.
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

# Dossier de l'outil (contient atelier/, les points d'entrée historiques et le socle Robot).
RACINE_OUTIL = Path(__file__).resolve().parent.parent.parent

PROJECT_DIR = Path(os.environ.get("ROBOT_PROJECT_DIR", Path.cwd())).expanduser().resolve()
SNAP_DIR = Path(os.environ.get("MCP_SNAPSHOT_DIR", PROJECT_DIR / ".mcp_snapshots")).expanduser()


def dossier() -> Path:
    return PROJECT_DIR


def snapshots() -> Path:
    return SNAP_DIR


def git_prefixe() -> str:
    """Position du projet de tests dans son dépôt Git (« qa/robot/ » ; vide à la racine du dépôt ou hors dépôt).
    Un projet peut vivre dans un sous-dossier d'un dépôt multi-applications : les commandes Git de l'atelier se
    limitent alors à ce sous-dossier et leurs chemins sont rendus relatifs au projet."""
    import subprocess

    try:
        r = subprocess.run(["git", "-C", str(PROJECT_DIR), "rev-parse", "--show-prefix"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def depuis_racine_git(chemin: str, prefixe: str | None = None) -> str | None:
    """Chemin donné par Git (relatif à la racine du dépôt) → relatif au projet ; None s'il est hors du projet."""
    prefixe = git_prefixe() if prefixe is None else prefixe
    chemin = chemin.strip().strip('"')
    if not prefixe:
        return chemin
    return chemin[len(prefixe):] if chemin.startswith(prefixe) else None


def safe_path(rel: str) -> Path:
    """Empêche toute lecture/écriture hors du projet de tests."""
    base = PROJECT_DIR
    p = (base / rel).resolve()
    if p != base and base not in p.parents:
        raise ValueError(f"Chemin hors du projet interdit : {rel}")
    return p


def slug(text: str, max_len: int = 40, defaut: str = "element") -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text[:max_len] or defaut


def lister_fichiers(pattern: str = "**/*.robot") -> list[str]:
    base = PROJECT_DIR
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
