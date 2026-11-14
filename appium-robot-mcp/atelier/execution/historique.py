"""Historique des exécutions lancées depuis l'atelier et détail d'un test (étapes, logs, preuves).

Chaque run lancé par l'interface écrit ses résultats dans un dossier propre (results/runs/<id>/) et
son bilan dans results/runs/<id>/bilan.json : les runs ne s'écrasent plus.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from atelier.domain import projet

RACINE = "results/runs"


def nouvel_id() -> str:
    return f"RUN-{datetime.now():%Y%m%d-%H%M%S}"


def dossier(run_id: str) -> Path:
    if not re.fullmatch(r"RUN-\d{8}-\d{6}(-\d+)?", run_id):
        raise ValueError("Identifiant de run invalide.")
    return projet.safe_path(f"{RACINE}/{run_id}")


def enregistrer(run_id: str, params: dict, bilan: dict | None, debut: str, fin: str | None = None):
    d = dossier(run_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "bilan.json").write_text(json.dumps({"id": run_id, "params": params, "bilan": bilan, "debut": debut, "fin": fin},
                                             ensure_ascii=False, indent=1, default=str), "utf-8")


def lister(limite: int = 50) -> list[dict]:
    base = projet.PROJECT_DIR / RACINE
    out = []
    for f in sorted(base.glob("RUN-*/bilan.json"), reverse=True)[:limite] if base.exists() else []:
        try:
            d = json.loads(f.read_text("utf-8"))
        except json.JSONDecodeError:
            continue
        b = d.get("bilan") or {}
        r = b.get("resultat") or {}
        statut = "en cours" if not d.get("fin") else "arrêté" if b.get("arrete") else "bloqué données" \
            if b.get("statut") == "bloqué données" else "erreur" if b.get("statut") == "erreur" or "resultat" not in b \
            else "échec" if r.get("echecs") else "réussi"
        out.append({"id": d["id"], "suite": (d.get("params") or {}).get("target"), "debut": d.get("debut"),
                    "fin": d.get("fin"), "statut": statut, "passes": r.get("passes"), "echecs": r.get("echecs"),
                    "plateforme": ((d.get("params") or {}).get("variables") or {}).get("PLATFORM", ""),
                    "xray": (b.get("xray") or {}).get("execution"), "dry_run": bool((d.get("params") or {}).get("dry_run"))})
    return out


def detail(run_id: str) -> dict:
    d = dossier(run_id)
    f = d / "bilan.json"
    if not f.exists():
        raise KeyError(f"Run {run_id} inconnu.")
    data = json.loads(f.read_text("utf-8"))
    data["tests"] = _tests(_sortie(data))
    return data


def _sortie(data: dict) -> Path:
    """Dossier de résultats du run (une relance des échecs réutilise celui du run d'origine)."""
    return projet.safe_path((data.get("params") or {}).get("output_dir") or f"{RACINE}/{data['id']}") / "output.xml"


def _tests(output: Path) -> list[dict]:
    if not output.exists():
        return []
    from robot.api import ExecutionResult

    from atelier.integrations.xray import KEY_RE

    res = ExecutionResult(str(output))
    return [{"id": t.id, "nom": t.name, "suite": t.parent.name, "statut": t.status, "message": t.message[:500],
             "cles_xray": [x for x in t.tags if KEY_RE.match(x)], "tags": list(t.tags),
             "debut": str(t.start_time or ""), "duree_s": round(t.elapsed_time.total_seconds(), 2)}
            for t in res.suite.all_tests]


def detail_test(run_id: str, test_id: str) -> dict:
    """Étapes (keywords de premier niveau et leurs sous-keywords), messages de log, captures du test."""
    from robot.api import ExecutionResult

    data = json.loads((dossier(run_id) / "bilan.json").read_text("utf-8"))
    sortie = _sortie(data)
    d = sortie.parent
    res = ExecutionResult(str(sortie))
    test = next((t for t in res.suite.all_tests if t.id == test_id), None)
    if test is None:
        raise KeyError(f"Test {test_id} absent du run {run_id}.")
    captures, logs = [], []

    def etape(kw, niveau=0) -> dict:
        enfants = [x for x in getattr(kw, "body", []) if getattr(x, "type", "") in ("KEYWORD", "SETUP", "TEARDOWN")]
        for m in [x for x in getattr(kw, "body", []) if getattr(x, "type", "") == "MESSAGE"]:
            txt = m.message
            for src in re.findall(r'src="([^"]+\.png)"', txt):
                captures.append(src)
            logs.append({"heure": str(m.timestamp or ""), "niveau": m.level, "keyword": kw.name,
                         "message": re.sub(r"<[^>]+>", "", txt)[:800]})
        return {"nom": kw.name, "args": [str(a) for a in getattr(kw, "args", ())][:6], "statut": kw.status,
                "debut": str(kw.start_time or ""), "duree_s": round(kw.elapsed_time.total_seconds(), 2),
                "message": getattr(kw, "message", "")[:500],
                "sous_etapes": [etape(x, niveau + 1) for x in enfants] if niveau < 2 else []}
    etapes = [etape(k) for k in test.body if getattr(k, "type", "") in ("KEYWORD", "SETUP", "TEARDOWN")]
    fautive = next((i for i, e in enumerate(etapes) if e["statut"] == "FAIL"), None)
    captures = [c for c in dict.fromkeys(captures) if (d / c).exists()]
    return {"id": test.id, "nom": test.name, "statut": test.status, "message": test.message, "tags": list(test.tags),
            "etapes": etapes, "etape_en_echec": fautive, "logs": logs[-300:], "captures": captures,
            "dossier": str(d.relative_to(projet.PROJECT_DIR))}
