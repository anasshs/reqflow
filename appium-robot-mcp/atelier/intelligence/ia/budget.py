"""Budgets IA mensuels, en tokens (pas de grille de prix : décision du 2026-11-21) : global, par projet, par module QA,
par poste. Seuils en pourcentage : information, avertissement, restriction (modèle économique imposé), blocage (plus
aucun appel IA direct). Bloqué, l'atelier continue avec ses règles, comme sans IA : les traitements déterministes ne
dépendent jamais du budget.

Compté : les appels directs et ceux de l'agent intégré (tokens réellement consommés par l'atelier), hors réponses tirées
du cache. Les estimations MCP (ce que reçoit Cursor) sont affichées à part, jamais imputées au budget de l'atelier.
"""
from __future__ import annotations

from datetime import datetime


def debut_du_mois() -> str:
    d = datetime.now().astimezone()
    return d.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")


def _consomme(**filtre) -> int:
    from atelier.intelligence.ia import journal

    where, params = ["date >= ?", "source IN ('direct', 'agent')", "cache = 0"], [debut_du_mois()]
    for k, v in filtre.items():
        where.append(f"{k} = ?")
        params.append(v)
    l = journal.lire(f"SELECT COALESCE(SUM(tokens_entree + tokens_sortie), 0) t FROM appels WHERE {' AND '.join(where)}", tuple(params))
    return int(l[0]["t"]) if l else 0


def etat(module: str = "", projet: str = "", poste: str = "", cfg: dict | None = None) -> dict:
    """{niveau, portees: [{portee, nom, limite, consomme, pct, niveau}]} ; niveau = le plus sévère des portées."""
    from atelier.intelligence.ia import config, journal

    cfg = cfg or config.effective()
    b = cfg.get("budgets") or {}
    seuils = b.get("seuils") or config.DEFAUT["budgets"]["seuils"]
    projet = projet or journal.projet_courant()
    poste = poste or journal.poste()
    portees = [("global", "", b.get("global"), {}), ("projet", projet, (b.get("projets") or {}).get(projet), {"projet": projet}),
               ("module", module, (b.get("modules") or {}).get(module), {"module": module}),
               ("poste", poste, (b.get("postes") or {}).get(poste), {"poste": poste})]
    out = []
    for portee, nom, limite, filtre in portees:
        if not limite or (portee != "global" and not nom):
            continue
        c = _consomme(**filtre)
        pct = round(100 * c / limite, 1)
        niv = next((s for s in reversed(config.SEUILS) if seuils.get(s) is not None and pct >= seuils[s]), "")
        out.append({"portee": portee, "nom": nom, "limite": int(limite), "consomme": c, "pct": pct, "niveau": niv})
    ordre = {"": 0, **{s: i + 1 for i, s in enumerate(config.SEUILS)}}
    return {"niveau": max((x["niveau"] for x in out), key=lambda s: ordre[s], default=""), "portees": out, "depuis": debut_du_mois()}


class BudgetAtteint(RuntimeError):
    pass


def verifier(module: str) -> str:
    """Niveau du budget pour un appel du module ; lève BudgetAtteint au blocage."""
    e = etat(module)
    if e["niveau"] == "blocage":
        p = next(x for x in e["portees"] if x["niveau"] == "blocage")
        raise BudgetAtteint(f"Budget IA atteint ({p['portee']}{' ' + p['nom'] if p['nom'] else ''} : {p['consomme']} tokens sur {p['limite']} ce mois-ci) : "
                            "l'atelier continue avec ses règles, sans IA.")
    return e["niveau"]


def bloque_global() -> bool:
    try:
        return etat()["niveau"] == "blocage"
    except Exception:  # noqa: BLE001
        return False
