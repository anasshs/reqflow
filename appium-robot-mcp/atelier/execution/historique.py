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
                    "xray": (b.get("xray") or {}).get("execution"), "dry_run": bool((d.get("params") or {}).get("dry_run")),
                    "campagne": (d.get("params") or {}).get("campagne", ""), "priorite": (d.get("params") or {}).get("priorite", ""),
                    "contexte": (d.get("params") or {}).get("contexte") or {},
                    "tentatives": len(b.get("tentatives") or []) or (1 if "resultat" in b else 0), "instables": b.get("instables") or []})
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
        return {"nom": kw.name, "bibliotheque": str(getattr(kw, "owner", "") or ""), "args": [str(a) for a in getattr(kw, "args", ())][:6], "statut": kw.status,
                "debut": str(kw.start_time or ""), "duree_s": round(kw.elapsed_time.total_seconds(), 2),
                "message": getattr(kw, "message", "")[:500],
                "sous_etapes": [etape(x, niveau + 1) for x in enfants] if niveau < 2 else []}
    # setup et teardown du test (RF 7 : hors de test.body) : la capture d'échec est souvent prise au teardown
    corps = ([test.setup] if test.setup else []) + [k for k in test.body if getattr(k, "type", "") in ("KEYWORD", "SETUP", "TEARDOWN")] \
        + ([test.teardown] if test.teardown else [])
    etapes = [etape(k) for k in corps]
    fautive = next((i for i, e in enumerate(etapes) if e["statut"] == "FAIL"), None)
    captures = [c for c in dict.fromkeys(captures) if (d / c).exists()]
    try:
        fichier = str(Path(str(test.source)).resolve().relative_to(projet.PROJECT_DIR))
    except (ValueError, TypeError):
        fichier = str(test.source or "")
    plateforme = ((data.get("params") or {}).get("variables") or {}).get("PLATFORM", "")
    references = _references_carte(plateforme)
    definitions, valeurs = _definitions_keywords(), _valeurs_locators(plateforme)
    for e in etapes:
        _enrichir(e, references, definitions, valeurs, plateforme)
    toutes = ((data.get("bilan") or {}).get("jdd") or {}).get("valeurs") or {}
    jeux = {j.upper() for e in etapes for j in _jdd_cites(e)}  # seulement le(s) jeu(x) passé(s) par ce test
    donnees = {k: v for k, v in toutes.items() if k.upper() in jeux} if jeux else toutes
    return {"id": test.id, "nom": test.name, "statut": test.status, "message": test.message, "tags": list(test.tags),
            "fichier": fichier, "ligne": test.lineno, "plateforme": plateforme,
            "donnees": donnees,
            "etapes": etapes, "etape_en_echec": fautive, "logs": logs[-300:], "captures": captures,
            "dossier": str(d.relative_to(projet.PROJECT_DIR))}


LOCATOR = re.compile(r"^(id|accessibility_id|xpath|android|nsp|chain|class|name|css|data-testid|text|role)=|^//")
STRATEGIES = {"id": "id (resource-id)", "accessibility_id": "accessibility id", "xpath": "xpath", "//": "xpath",
              "android": "android uiautomator", "nsp": "iOS predicate", "chain": "iOS class chain", "class": "class name",
              "name": "name", "css": "css (Playwright)", "data-testid": "data-testid (Playwright)", "text": "texte (Playwright)",
              "role": "rôle ARIA (Playwright)"}


def _references_carte(plateforme: str) -> dict:
    """{valeur de locator: écran de la carte qui le contient (nom, vignette de la plateforme)}."""
    from atelier.discovery import carte

    out: dict = {}
    try:
        if not carte.app_courante():
            return out
        for ec in carte.ecrans():
            for el in (ec.get("elements") or {}).values():
                for plat, locs in (el.get("locators") or {}).items():
                    if plateforme and plat != plateforme:
                        continue
                    vignette = ((ec.get("plateformes") or {}).get(plat) or {}).get("vignette")
                    for loc in locs or []:
                        out.setdefault(loc, {"ecran": ec.get("nom") or ec["id"], "id": ec["id"], "plateforme": plat,
                                             "vignette": vignette})
    except Exception:
        pass
    return out


def _definitions_keywords() -> dict:
    try:
        from atelier.execution import depot_robot

        inv = depot_robot.lire_depot()
        return {k: {"fichier": v["fichier"], "ligne": v["ligne"]} for k, v in inv["keywords"].items()}
    except Exception:
        return {}


def _jdd_cites(e: dict):
    for a in e["args"]:
        yield from re.findall(r"JDD_([A-Za-z0-9_]+)", a)
    for x in e["sous_etapes"]:
        yield from _jdd_cites(x)


def _valeurs_locators(plateforme: str) -> dict:
    """« ecran.cle@plateforme » -> valeur, depuis les &{LOC_<ECRAN>_<PLATEFORME>} du dépôt."""
    try:
        from atelier.execution import depot_robot

        return {k: v["valeur"] for k, v in depot_robot.lire_depot()["locators"].items() if v.get("valeur")}
    except Exception:
        return {}


def _resoudre(arg: str, valeurs: dict, plateforme: str) -> str:
    """${LOC_ECRAN_WEB.cle} ou ${LOC_ECRAN_${PLATFORM}.cle} -> valeur du locator déclarée dans le dépôt."""
    from atelier.execution.depot_robot import PLATEFORMES, REF_CLE

    m = REF_CLE.search(arg)
    if not m:
        return arg
    plat = PLATEFORMES.get(m.group(2), plateforme)
    return valeurs.get(f"{m.group(1).lower()}.{m.group(3)}@{plat}", arg)


def _enrichir(e: dict, references: dict, definitions: dict, valeurs: dict | None = None, plateforme: str = ""):
    """Locator utilisé (dans l'étape ou ses sous-étapes, la sous-étape en échec d'abord), stratégie,
    écran de référence, définition du keyword."""
    from atelier.execution.depot_robot import normaliser

    valeurs = valeurs or {}

    def locators(x):
        yield from (a for a in (_resoudre(a, valeurs, plateforme) for a in x["args"]) if LOCATOR.match(a))
        for s in sorted(x["sous_etapes"], key=lambda s: s["statut"] != "FAIL"):
            yield from locators(s)
    loc = next(locators(e), "")
    e["locator"] = loc
    prefixe = "//" if loc.startswith("//") else loc.split("=", 1)[0] if loc else ""
    e["type_locator"] = prefixe.replace("//", "xpath") if loc else ""
    e["strategie"] = ("id (attribut HTML)" if prefixe == "id" and plateforme == "web" else STRATEGIES.get(prefixe, "")) if loc else ""
    e["ecran_reference"] = references.get(loc)
    e["definition"] = definitions.get(normaliser(e["nom"]))
