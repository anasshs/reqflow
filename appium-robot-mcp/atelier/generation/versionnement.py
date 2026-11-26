"""Versionnement des tests publiés : un test envoyé dans Xray comme test automatisé a son code dans le dépôt Git du
projet de tests, prêt pour la merge request.

Les fichiers d'un scénario : la suite Robot de ses tests et tout ce dont ils dépendent (pages de keywords, fichiers de
locators), le scénario BDD (.feature et sa fiche), et les fichiers de jeux de données qui déclarent ses jeux. L'état de
travail de l'atelier (résultats, sessions, revues…) n'en fait jamais partie.

À la publication dans Xray (generation/flux.publier), ces fichiers sont commités : sur la branche de travail courante,
ou sur une nouvelle branche « atelier/xray-<date> » si la branche courante est protégée (main, master…). Jamais de
push ici : la branche part sur GitLab avec la merge request (studio.proposer_mr, revue humaine et 3 exécutions stables).
Une indisponibilité Git n'empêche jamais la publication : l'état est rendu, à reprendre depuis le ticket."""
from __future__ import annotations

import re
import subprocess
import time

from atelier.domain import projet


def _git(*args: str) -> str:
    from atelier.execution.centre import _git as g

    return g(*args)


def depot() -> bool:
    return _git("rev-parse", "--is-inside-work-tree") == "true"


def fichiers(cle: str) -> list[str]:
    """Fichiers du dépôt qui portent le scénario et son automatisation (chemins relatifs au projet de tests)."""
    from atelier.execution.depot_robot import lire_depot
    from atelier.generation import bdd, lots, maintenance, studio

    out: set[str] = set()
    par_bdd, _ = lots._index_tests()
    tests = [t["id"] for t in par_bdd.get(cle) or []]
    if tests:
        inv = lire_depot()
        for tid in tests:
            if tid in inv["tests"]:
                out |= maintenance._fichiers_du_test(inv, tid)
    for f in bdd._fichiers(cle):
        if f.exists():
            out.add(projet.relatif(f))
    jeux = set()
    for tid in tests:
        fichier, _, _nom = tid.partition("::")
        try:
            jeux |= set(re.findall(r"&\{JDD_([A-Za-z0-9_]+)\}", projet.safe_path(fichier).read_text("utf-8")))
        except (OSError, ValueError):
            pass
    d = projet.racine_code() / "data" / "jdd"
    for y in sorted(d.glob("*.yaml")) if d.exists() and jeux else []:
        texte = y.read_text("utf-8", errors="replace")
        if any(re.search(rf"(?m)^{re.escape(j)}:", texte) for j in jeux):
            out.add(projet.relatif(y))
    return sorted(f for f in out if not f.startswith(studio.ETAT_ATELIER))


def etat(cle: str) -> dict:
    """Lien du test avec Git : branche, dernier commit de ses fichiers, fichiers à commiter, poussé ou non."""
    if not depot():
        return {"depot": False}
    fs = fichiers(cle)
    statut = {}
    for ligne in _git("-c", "core.quotepath=false", "status", "--porcelain", "--untracked-files=all", "--", *fs).splitlines() if fs else []:
        code, _, chemin = ligne.strip().partition(" ")  # la sortie est nettoyée : « M x », « ?? x », « A  x »
        if chemin.strip():
            statut[chemin.strip().strip('"')] = "nouveau" if code == "??" else "modifié"
    dernier = _git("log", "-1", "--date=iso-strict", "--format=%h%x1f%s%x1f%ad%x1f%an", "--", *fs) if fs else ""
    commit = dict(zip(("hash", "message", "date", "auteur"), dernier.split("\x1f"))) if dernier else None
    pousse = bool(commit and _git("branch", "-r", "--contains", commit["hash"]).strip())
    return {"depot": True, "branche": _git("rev-parse", "--abbrev-ref", "HEAD"), "fichiers": [{"fichier": f, "etat": statut.get(f, "commité")} for f in fs],
            "a_commiter": [f for f in fs if f in statut], "commit": commit, "pousse": pousse,
            "distant": _git("remote", "get-url", "origin").split("@")[-1]}  # jamais d'identifiant dans l'URL affichée


def _branche_de_travail() -> tuple[str, bool]:
    """Branche où commiter : la courante si elle n'est pas protégée, sinon une nouvelle « atelier/xray-<date> »."""
    from atelier.generation import studio

    b = _git("rev-parse", "--abbrev-ref", "HEAD")
    if b and b not in studio.BRANCHES_PROTEGEES and b != "HEAD":
        return b, False
    nom = "atelier/xray-" + time.strftime("%Y%m%d-%H%M")
    n = 1
    while _git("rev-parse", "--verify", "--quiet", f"refs/heads/{nom}"):
        n += 1
        nom = "atelier/xray-" + time.strftime("%Y%m%d-%H%M") + f"-{n}"
    r = subprocess.run(["git", "-C", str(projet.racine_code()), "switch", "-c", nom], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=15)
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[:300])
    return nom, True


def committer(cles: list[str], message: str = "", xray: dict | None = None) -> dict:
    """Commit des fichiers des scénarios donnés qui ont des changements (suites approuvées à la publication).
    xray : {scénario: clé Xray} pour le message. Rien à commiter : rien n'est fait (pas de commit vide)."""
    from atelier.generation import bdd, studio

    if not depot():
        return {"depot": False, "commit": "", "fichiers": []}
    a_commiter = sorted({f for c in cles for f in etat(c)["a_commiter"]})
    if not a_commiter:
        return {"depot": True, "commit": "", "fichiers": [], "branche": _git("rev-parse", "--abbrev-ref", "HEAD"), "message": "Déjà commité."}
    rev = studio.revues_scripts()  # contrôlé avant de créer une branche : un refus ne laisse rien derrière lui
    non_valides = [f for f in a_commiter if f.endswith(".robot") and (rev.get(f) or {}).get("statut") not in ("Approved", "Published")]
    if non_valides:
        raise PermissionError("Revue technique non approuvée : " + ", ".join(non_valides))
    branche, nouvelle = _branche_de_travail()
    if not message:
        noms = [f"{(bdd.charger(c) or {}).get('titre') or c}" + (f" ({xray[c]})" if xray and xray.get(c) else "") for c in cles]
        message = "Tests automatisés publiés dans Xray : " + ", ".join(noms)
    studio._commit(message[:300], a_commiter)
    return {"depot": True, "commit": _git("rev-parse", "--short", "HEAD"), "branche": branche, "nouvelle_branche": nouvelle,
            "fichiers": a_commiter, "message": message[:300]}
