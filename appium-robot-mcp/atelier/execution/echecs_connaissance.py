"""Failure Analysis × Knowledge Graph (V2, phase 6) : relier chaque échec à l'écran, au composant (et au champ) qu'il
touche, aux anomalies Jira déjà connues, comparer les échecs d'un même composant, historiser les causes et détecter
les régressions récurrentes.

- Localisation d'un échec : étape fautive → locator → référentiel (écran, clé). Calculée une fois et gardée dans le
  suivi de l'échec (pas de relecture des runs à chaque affichage).
- Régression : le test était réussi au run précédent et échoue maintenant. Régression RÉCURRENTE : au moins deux
  régressions sur le même composant (ou, sans localisation, le même test), sur des runs différents.
- Causes historisées : catégorie confirmée par l'automaticien (sinon proposée par les règles), avec la date.
Lecture seule : aucune décision n'est prise ici, aucune anomalie n'est créée.
"""
from __future__ import annotations

from collections import defaultdict

from atelier.execution import echecs


def localiser(eid: str, forcer: bool = False) -> dict:
    """Écran / composant / locator / étape d'un échec ; mémorisé dans le suivi de l'échec."""
    s = echecs._stock().get(eid, {})
    if s.get("localisation") and not forcer:
        return s["localisation"]
    ctx = echecs._contexte_sur(eid)
    loc = {k: ctx.get(k, "") for k in ("ecran", "composant", "locator", "etape", "plateforme")}
    st = echecs._stock()
    st.setdefault(eid, {"historique": []})["localisation"] = loc
    echecs._sauver(st)
    return loc


def localiser_tous(limite: int = 60) -> dict:
    """Localise les échecs récents qui ne le sont pas encore (borné : chaque localisation relit un run)."""
    faits = 0
    st = echecs._stock()
    for e in echecs.collecter(limite):
        if not (st.get(e["id"]) or {}).get("localisation"):
            localiser(e["id"])
            faits += 1
    return {"localises": faits}


def _cause(e: dict) -> str:
    return e.get("categorie_confirmee") or e.get("categorie_probable") or "Unknown"


def _anomalies_connues(g=None) -> dict:
    """Anomalies du graphe par écran et par composant (bugs Jira et échecs déjà qualifiés)."""
    try:
        from atelier.discovery import entites

        l = entites.anomalies(g)
    except Exception:  # noqa: BLE001
        return {}
    par: dict = defaultdict(list)
    for a in l:
        for x in a["ecrans"] + a["composants"]:
            par[x].append({"id": a["id"], "id_jira": a["id_jira"], "titre": a["titre"], "statut": a["statut"]})
    return par


def par_composant(limite: int = 60, g=None) -> dict:
    """Échecs regroupés par composant (écran.clé), causes historisées, régressions et régressions récurrentes."""
    st = echecs._stock()
    evts = echecs.collecter(limite)
    groupes: dict = defaultdict(list)
    for e in evts:
        loc = (st.get(e["id"]) or {}).get("localisation") or {}
        cle = f"{loc['ecran']}.{loc['composant']}" if loc.get("ecran") and loc.get("composant") else (loc.get("ecran") or f"test : {e['nom']}")
        groupes[cle].append({**e, "localisation": loc})
    champs = set()
    try:
        from atelier.discovery import entites

        champs = {f"{c['ecran']}.{c['nom_technique']}" for c in entites.champs(g=g)}
    except Exception:  # noqa: BLE001
        pass
    connues = _anomalies_connues(g)
    out = []
    for cle, l in groupes.items():
        l = sorted(l, key=lambda x: x["date"])
        regressions = [x for x in l if x.get("precedent") == "PASS"]
        ecran = (l[0]["localisation"] or {}).get("ecran", "")
        comp = (l[0]["localisation"] or {}).get("composant", "")
        out.append({
            "cle": cle, "ecran": ecran, "composant": comp, "est_champ": cle in champs, "localise": bool(ecran),
            "echecs": len(l), "runs": sorted({x["run"] for x in l}), "tests": sorted({x["nom"] for x in l}),
            "premier": l[0]["date"], "dernier": l[-1]["date"],
            "causes": [{"date": x["date"], "run": x["run"], "test": x["nom"], "cause": _cause(x), "confirmee": bool(x.get("categorie_confirmee")),
                        "jira": x.get("jira", "")} for x in l],
            "cause_dominante": max({_cause(x) for x in l}, key=lambda c: sum(_cause(x) == c for x in l)),
            "regressions": len(regressions), "regression_recurrente": len({x["run"] for x in regressions}) >= 2,
            "anomalies_jira": sorted({x["jira"] for x in l if x.get("jira")}),
            "anomalies_connues": list({a["id"]: a for a in connues.get(ecran, [])}.values()) if ecran else [],  # au niveau de l'écran
            "echecs_ids": [x["id"] for x in l]})
    out.sort(key=lambda x: (not x["regression_recurrente"], -x["regressions"], -x["echecs"]))
    return {"composants": out, "non_localises": sum(1 for x in out if not x["localise"]),
            "regressions_recurrentes": [x["cle"] for x in out if x["regression_recurrente"]],
            "definitions": {"régression": "le test était réussi au run précédent et échoue maintenant",
                            "régression récurrente": "au moins deux régressions sur le même composant (ou le même test), sur des runs différents",
                            "cause": "catégorie confirmée par l'automaticien, sinon proposée par les règles"}}


def connaissance_echec(eid: str, g=None) -> dict:
    """Pour un échec : localisation, autres échecs du même composant (toutes signatures), anomalies déjà connues sur
    l'écran / le composant, causes historisées du composant, régression ou non."""
    loc = localiser(eid)
    localiser_tous()  # comparer avec les autres échecs suppose qu'ils soient localisés (une fois chacun, mémorisé)
    pc = par_composant(g=g)
    cle = f"{loc['ecran']}.{loc['composant']}" if loc.get("ecran") and loc.get("composant") else loc.get("ecran", "")
    groupe = next((x for x in pc["composants"] if eid in x["echecs_ids"]), None) or next((x for x in pc["composants"] if x["cle"] == cle), None)
    e = next((x for x in echecs.collecter(60) if x["id"] == eid), {})
    return {"echec": eid, "localisation": loc, "composant": cle or None, "est_champ": bool(groupe and groupe["est_champ"]),
            "regression": e.get("precedent") == "PASS", "regression_recurrente": bool(groupe and groupe["regression_recurrente"]),
            "meme_composant": [c for c in (groupe or {}).get("causes", []) if c["run"] != e.get("run") or c["test"] != e.get("nom")],
            "anomalies_connues": (groupe or {}).get("anomalies_connues", []), "anomalies_jira": (groupe or {}).get("anomalies_jira", []),
            "cause_dominante": (groupe or {}).get("cause_dominante")}
