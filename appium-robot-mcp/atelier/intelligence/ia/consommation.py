"""Tableau de consommation IA du poste (lu dans le journal) : totaux, évolution par jour et par mois, par fournisseur,
modèle, module QA, opération (coût d'une opération = somme de ses appels, regroupés par corrélation), projet et poste ;
comparaison des modèles ; activité MCP de Cursor à part, en estimation.

Mesures : tokens (pas de grille de prix, décision du 2026-11-21). Les appels directs et ceux de l'agent intégré sont la
consommation de l'atelier ; les lignes « mcp » estiment ce que les outils ont envoyé à Cursor : jamais additionnées.
"""
from __future__ import annotations

from collections import Counter, defaultdict

FILTRES = ("projet", "poste", "module", "fournisseur", "modele", "operation")


def _tok(a: dict) -> int:
    return int(a["tokens_entree"] or 0) + int(a["tokens_sortie"] or 0)


def _groupe(l: list, cle) -> list[dict]:
    g: dict = defaultdict(list)
    for a in l:
        g[cle(a) or "—"].append(a)
    out = []
    for k, xs in g.items():
        ok = [x for x in xs if x["statut"] == "ok" and not x["cache"]]
        ops = {x["correlation"] for x in ok}
        out.append({"cle": k, "appels": len(ok), "tokens": sum(_tok(x) for x in ok), "tokens_entree": sum(x["tokens_entree"] for x in ok),
                    "tokens_sortie": sum(x["tokens_sortie"] for x in ok), "tokens_cache": sum(x["tokens_cache_lus"] for x in ok),
                    "operations": len(ops), "par_operation": round(sum(_tok(x) for x in ok) / len(ops)) if ops else 0,
                    "erreurs": sum(x["statut"] == "erreur" for x in xs), "depuis_cache": sum(bool(x["cache"]) for x in xs),
                    "estimes": sum(bool(x["estime"]) for x in ok),
                    "modele_principal": (Counter(x["modele"] for x in ok).most_common(1) or [("", 0)])[0][0]})
    return sorted(out, key=lambda x: -x["tokens"])


def tableau(depuis: str = "", jusqu: str = "", **filtres) -> dict:
    from atelier.intelligence.ia import budget, journal

    tous = journal.appels(depuis, jusqu, **{k: v for k, v in filtres.items() if k in FILTRES})
    atelier = [a for a in tous if a["source"] in ("direct", "agent")]
    mcp = [a for a in tous if a["source"] == "mcp"]
    ok = [a for a in atelier if a["statut"] == "ok" and not a["cache"]]
    ops = {a["correlation"] for a in ok}
    totaux = {"appels": len(ok), "tokens": sum(_tok(a) for a in ok), "tokens_entree": sum(a["tokens_entree"] for a in ok),
              "tokens_sortie": sum(a["tokens_sortie"] for a in ok), "tokens_cache": sum(a["tokens_cache_lus"] for a in ok),
              "operations": len(ops), "par_operation": round(sum(_tok(a) for a in ok) / len(ops)) if ops else None,
              "erreurs": sum(a["statut"] == "erreur" for a in atelier), "replis": sum(bool(a["repli"]) for a in ok),
              "depuis_cache": sum(bool(a["cache"]) for a in atelier), "estimes": sum(bool(a["estime"]) for a in ok),
              "economie_compactage": sum(max(0, a["tokens_avant"] - a["tokens_apres"]) for a in ok),
              "tokens_evites_cache": sum(a["tokens_avant"] for a in atelier if a["cache"])}
    duree = defaultdict(list)
    for a in atelier:
        duree[a["modele"]].append(a)
    modeles = []
    for m, xs in duree.items():
        reels = [x for x in xs if not x["cache"]]  # le cache ne dit rien de la fiabilité du modèle
        bons = [x for x in reels if x["statut"] == "ok"]
        modeles.append({"modele": m or "—", "appels": len(reels), "reussite": round(100 * len(bons) / len(reels), 1) if reels else None,
                        "tokens_moyens": round(sum(_tok(x) for x in bons) / len(bons)) if bons else None,
                        "duree_moyenne_ms": round(sum(x["duree_ms"] for x in bons) / len(bons)) if bons else None,
                        "replis": sum(bool(x["repli"]) for x in bons)})
    valeurs = {k: sorted({a[k] for a in tous if a[k]}) for k in FILTRES}
    return {"filtres": {**filtres, "depuis": depuis, "jusqu": jusqu}, "valeurs": valeurs, "totaux": totaux,
            "par_jour": _groupe(ok, lambda a: a["date"][:10]), "par_mois": _groupe(ok, lambda a: a["date"][:7]),
            "par_fournisseur": _groupe(atelier, lambda a: a["fournisseur"]), "par_modele": _groupe(atelier, lambda a: a["modele"]),
            "par_module": _groupe(atelier, lambda a: a["module"]), "par_operation": _groupe(atelier, lambda a: a["operation"]),
            "par_projet": _groupe(atelier, lambda a: a["projet"]), "par_poste": _groupe(atelier, lambda a: a["poste"]),
            "modeles": sorted(modeles, key=lambda x: -x["appels"]),
            "cursor": {"appels_outils": len(mcp), "tokens_estimes": sum(a["tokens_entree"] for a in mcp),
                       "economie_allegement": sum(max(0, a["tokens_avant"] - a["tokens_apres"]) for a in mcp),
                       "demandes": len({a["correlation"] for a in mcp}), "par_outil": _groupe([{**a, "statut": "ok", "cache": 0} for a in mcp],
                                                                                         lambda a: a["operation"].removeprefix("mcp."))[:15],
                       "factures": None,
                       "note": "Estimation de ce que les outils de l'atelier ont envoyé à Cursor (caractères / 4). La consommation "
                               "réelle de Cursor (son modèle, ses tokens, sa facturation) n'est pas visible depuis l'atelier : indisponible."},
            "budget": budget.etat(filtres.get("module") or "")}
