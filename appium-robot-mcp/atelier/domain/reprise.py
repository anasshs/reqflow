"""Changer le dépôt d'un projet sans perdre sa connaissance.

La connaissance et le travail de l'atelier (carte, Discovery, parcours, modèle comportemental, conception, exécutions,
gouvernance… : synchro.PARTAGES) vivent dans le dossier du projet. Quand un projet existant reçoit un autre dossier
(autre dépôt, nouveau clone), ils sont repris dans le nouveau dossier :
- un fichier absent du nouveau dossier y est copié ;
- un fichier identique est laissé tel quel ;
- un fichier différent : la connaissance de l'atelier l'emporte, la version du dépôt est gardée à côté
  (« <nom>.conflit-depot-<date> », jamais synchronisée) ;
- l'ancien dossier n'est jamais modifié (copie, pas déplacement).
Les scripts Robot (tests/, resources/…) appartiennent au dépôt : ils ne sont pas touchés.
"""
from __future__ import annotations

import filecmp
import shutil
from datetime import datetime
from pathlib import Path


def _fichiers(dossier: Path):
    from atelier.domain import synchro

    for p in synchro.PARTAGES:
        racine = dossier / p.rstrip("/")
        if p.endswith("/"):
            if racine.is_dir():
                for f in racine.rglob("*"):
                    if f.is_file():
                        rel = f.relative_to(dossier).as_posix()
                        if synchro.partage(rel):
                            yield rel
        elif racine.is_file():
            yield p


def reprendre(ancien: str | Path, nouveau: str | Path) -> dict:
    """Reprend dans `nouveau` la connaissance et le travail de l'atelier présents dans `ancien`."""
    a, n = Path(ancien).expanduser(), Path(nouveau).expanduser()
    bilan = {"de": str(a), "vers": str(n), "copies": 0, "identiques": 0, "conflits": [], "erreurs": []}
    if not a.is_dir() or not n.is_dir() or a.resolve() == n.resolve():
        return bilan
    date = datetime.now().strftime("%Y%m%d-%H%M%S")
    for rel in _fichiers(a):
        src, dst = a / rel, n / rel
        try:
            if dst.exists():
                if filecmp.cmp(src, dst, shallow=False):
                    bilan["identiques"] += 1
                    continue
                garde = dst.with_name(f"{dst.name}.conflit-depot-{date}")
                shutil.copy2(dst, garde)
                bilan["conflits"].append(rel)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            bilan["copies"] += 1
        except OSError as e:
            bilan["erreurs"].append(f"{rel} : {e}"[:200])
    return bilan
