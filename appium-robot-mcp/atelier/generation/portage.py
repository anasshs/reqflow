"""Porter le patrimoine Robot vers Kotlin (phase D, docs/AUTOMATISATION_MULTI_CIBLES.md § 5).

Le traducteur ligne à ligne vit dans le projet Kotlin du dépôt de tests (outils/robot2kotlin.py : chaque keyword devient une
fonction k_<nom>, chaque suite une classe JUnit, ce qui ne se traduit pas sûrement devient R.nonTraduit(...) et échoue en
se nommant). L'atelier le lance, puis dit TEST PAR TEST ce qui reste à traduire (directement dans le test, ou dans un
keyword qu'il appelle) : de quoi décider entre compléter le code porté et régénérer le test depuis son scénario BDD.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ENTETE = re.compile(r"Instructions traduites\s*:\s*(\d+)\s*·\s*non traduites\s*:\s*(\d+)")
FONCTION = re.compile(r"^\s*fun\s+(\w+)\(", re.M)


def _executer(cmd: list[str], cwd: Path) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _corps(texte: str) -> dict[str, str]:
    """Fonction Kotlin -> son corps (jusqu'à la fonction suivante)."""
    pos = [(m.group(1), m.start()) for m in FONCTION.finditer(texte)]
    return {nom: texte[d:(pos[i + 1][1] if i + 1 < len(pos) else len(texte))] for i, (nom, d) in enumerate(pos)}


def reste_a_traduire(dossier_genere: Path) -> list[dict]:
    """Par test porté (méthode d'une classe *Test.kt) : instructions R.nonTraduit atteintes, directement ou par les
    keywords k_ appelés (fermeture). [{classe, methode, cle, non_traduits, exemples}]."""
    fichiers = {f: f.read_text("utf-8", errors="replace") for f in sorted(dossier_genere.glob("*.kt"))}
    kws: dict[str, str] = {}
    for f, t in fichiers.items():
        if not f.stem.endswith("Test"):
            kws.update({n: c for n, c in _corps(t).items() if n.startswith("k_")})
    directs = {n: re.findall(r'R\.nonTraduit\("((?:[^"\\]|\\.)*)"\)', c) for n, c in kws.items()}
    appels = {n: set(re.findall(r"\b(k_\w+)\(", c)) - {n} for n, c in kws.items()}

    def fermeture(depart: set) -> set:
        vus, pile = set(), list(depart)
        while pile:
            k = pile.pop()
            if k in vus or k not in kws:
                continue
            vus.add(k)
            pile += list(appels.get(k, ()))
        return vus

    out = []
    for f, t in fichiers.items():
        if not f.stem.endswith("Test"):
            continue
        for nom, c in _corps(t).items():
            if nom in ("preparerSuite", "terminerSuite") or nom.startswith("k_"):
                continue
            ici = re.findall(r'R\.nonTraduit\("((?:[^"\\]|\\.)*)"\)', c)
            via = [x for k in sorted(fermeture(set(re.findall(r"\b(k_\w+)\(", c)))) for x in directs.get(k, [])]
            m = re.match(r"([a-z][a-z0-9]*)_(\d+)_", nom)
            out.append({"classe": f.stem, "methode": nom, "cle": f"{m.group(1).upper()}-{m.group(2)}" if m else "",
                        "non_traduits": len(ici) + len(via), "exemples": list(dict.fromkeys(ici + via))[:3]})
    return out


def porter(lanceur=None) -> dict:
    """Lance outils/robot2kotlin.py du projet Kotlin sur le dépôt Robot, puis fait le bilan par test."""
    from atelier.domain import projet
    from atelier.generation.technologies.kotlin import ProjetKotlin

    pk = ProjetKotlin()
    script = pk.racine / "outils" / "robot2kotlin.py"
    if not script.exists():
        raise ValueError(f"Traducteur absent : {script.relative_to(projet.PROJECT_DIR).as_posix()} (projet Kotlin du dépôt de tests).")
    code, sortie = (lanceur or _executer)([sys.executable, "-I", str(script), str(projet.PROJECT_DIR)], pk.racine)
    if code != 0:
        return {"ok": False, "message": (sortie.strip().splitlines() or ["Échec du traducteur."])[-1][:500]}
    a = pk.racine / "A_TRADUIRE.md"
    m = ENTETE.search(a.read_text("utf-8")) if a.exists() else None
    traduites, non = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    tests = reste_a_traduire(pk.src / "genere")
    return {"ok": True, "instructions_traduites": traduites, "non_traduites": non,
            "taux": round(100 * traduites / (traduites + non), 1) if traduites + non else None,
            "tests": len(tests), "tests_complets": sum(1 for t in tests if not t["non_traduits"]),
            "a_traduire": sorted([t for t in tests if t["non_traduits"]], key=lambda t: -t["non_traduits"]),
            "rapport": a.relative_to(projet.PROJECT_DIR).as_posix() if a.exists() else ""}
