"""Couverture avancée (V2, phase 3) : parcours et composants UI, avec des NIVEAUX de couverture explicables.

Tout est calculé sur le Knowledge Graph existant (aucun second référentiel) :
  écran ─contient→ locator (un composant = une clé métier de l'écran, toutes plateformes)
  keyword ─utilise→ locator ; test Robot ─appelle→ keyword (et keyword ─appelle→ keyword)
  test Xray ─implémenté par→ test Robot (clé en tag) ; dernier statut du test Robot (runs réels)
  fonctionnalité ─contient→ écran et user story ─testée par→ test Xray (association déduite, écran seulement)
  parcours ─contient→ écrans (étapes).

Niveaux, du plus faible au plus fort (chaque niveau inclut le précédent) :
  découvert   présent dans la carte de l'application ;
  associé     utilisé par au moins un test Robot (keyword → locator) ; pour un écran, aussi via une fonctionnalité
              dont une US a un test Xray (association déduite, confiance moyenne) ;
  automatisé  utilisé par un test Robot rattaché à un test Xray (clé en tag) ;
  exécuté     ce test a au moins une exécution réelle connue (effectivement vérifié) ;
  réussi      dernière exécution réussie (PASS).
Limite assumée : pour les tests manuels, l'étape Xray est du texte libre : aucune couverture au niveau composant
n'est inventée ; seule l'association déduite au niveau écran est indiquée.
"""
from __future__ import annotations

from datetime import datetime

NIVEAUX = ["découvert", "associé", "automatisé", "exécuté", "réussi"]
DEFINITIONS = {
    "découvert": "Présent dans la carte de l'application (Discovery, cartographie des runs, import des .resource).",
    "associé": "Utilisé par au moins un test Robot (keyword → locator) ; pour un écran, aussi via une fonctionnalité dont une US a un test Xray (déduit).",
    "automatisé": "Utilisé par un test Robot rattaché à un test Xray (clé Xray en tag).",
    "exécuté": "Un de ces tests a au moins une exécution réelle connue (effectivement vérifié).",
    "réussi": "La dernière exécution d'un de ces tests est réussie (PASS).",
}


def _rang(niveau: str) -> int:
    return NIVEAUX.index(niveau)


def _niveau_tests(tests: list[dict]) -> str:
    if not tests:
        return "découvert"
    if any(t["statut"] == "PASS" and t["xray"] for t in tests):
        return "réussi"
    if any(t["statut"] and t["xray"] for t in tests):
        return "exécuté"
    if any(t["xray"] for t in tests):
        return "automatisé"
    return "associé"


def _pct(n: int, d: int):
    return round(100 * n / d, 1) if d else None


def calculer(g=None, module: str = "") -> dict:
    if g is None:
        from atelier.discovery import connaissance

        g = connaissance.construire()
    N = g.noeuds

    def sortants(i, t):
        return [r.vers for r in g.sortants(i) if r.type == t and r.vers in N]

    # tests Robot → keywords (fermeture) → locators
    tests_par_locator: dict[str, set] = {}
    for tid, n in N.items():
        if n.type != "test_robot":
            continue
        vus, pile = set(), sortants(tid, "appelle")
        while pile:
            k = pile.pop()
            if k in vus or N[k].type != "keyword":
                continue
            vus.add(k)
            pile += sortants(k, "appelle")
        for k in vus:
            for loc in sortants(k, "utilise"):
                tests_par_locator.setdefault(loc, set()).add(tid)

    def info_test(tid):
        p = N[tid].proprietes
        return {"id": tid, "nom": N[tid].libelle, "xray": list(p.get("cles_xray") or []), "statut": p.get("dernier_statut") or ""}

    # tests Xray associés à un écran par sa fonctionnalité (déduit)
    xray_par_ecran: dict[str, set] = {}
    for fid, n in N.items():
        if n.type not in ("fonctionnalite", "module"):
            continue
        ecr = sortants(fid, "contient")
        tests = {t for us in ecr if N[us].type == "user_story" for t in sortants(us, "teste_par")}
        for e in ecr:
            if N[e].type == "ecran" and tests:
                xray_par_ecran.setdefault(e, set()).update(tests)
    modules = {e: N[m].libelle for m, n in N.items() if n.type == "module" for e in sortants(m, "contient") if N[e].type == "ecran"}

    ecrans, composants = [], []
    for eid, n in sorted(N.items()):
        if n.type != "ecran":
            continue
        mod = modules.get(eid, "")
        if module and mod.lower() != module.lower():
            continue
        par_cle: dict[str, list] = {}
        for loc in sortants(eid, "contient"):
            if N[loc].type == "locator":
                par_cle.setdefault(N[loc].libelle, []).append(loc)
        comps = []
        for cle, locs in sorted(par_cle.items()):
            tests = {t for l in locs for t in tests_par_locator.get(l, set())}
            infos = [info_test(t) for t in sorted(tests)]
            c = {"id": f"{eid}#{cle}", "ecran": n.libelle, "cle": cle, "plateformes": sorted({N[l].proprietes.get("plateforme", "") for l in locs}),
                 "classe": next((N[l].proprietes.get("classe_action") for l in locs if N[l].proprietes.get("classe_action")), ""),
                 "niveau": _niveau_tests(infos), "tests": [t["nom"] for t in infos], "tests_xray": sorted({k for t in infos for k in t["xray"]})}
            comps.append(c)
        composants += comps
        tous = sorted({t for c in comps for t in c["tests"]})
        niv_comp = max((_rang(c["niveau"]) for c in comps), default=0)
        deduits = sorted(N[t].libelle for t in xray_par_ecran.get(eid, set()))
        niveau = NIVEAUX[niv_comp] if niv_comp else ("associé" if deduits else "découvert")
        ecrans.append({"id": eid, "nom": n.libelle, "module": mod, "composants": len(comps),
                       "composants_par_niveau": {lv: sum(_rang(c["niveau"]) >= _rang(lv) for c in comps) for lv in NIVEAUX},
                       "niveau": niveau, "association_deduite": niveau == "associé" and not niv_comp,
                       "tests_robot": tous, "tests_xray_deduits": deduits})

    rang_ecran = {e["id"]: _rang(e["niveau"]) for e in ecrans}
    parcours = []
    for pid, n in sorted(N.items()):
        if n.type != "parcours":
            continue
        etapes = [{"ecran": N[e].libelle, "id": e, "niveau": NIVEAUX[rang_ecran.get(e, 0)]} for e in sortants(pid, "contient") if N[e].type == "ecran"]
        if module and not any(rang_ecran.get(x["id"]) is not None for x in etapes):
            continue
        rangs = [_rang(x["niveau"]) for x in etapes]
        parcours.append({"id": pid, "libelle": n.libelle, "statut": n.statut, "etapes": etapes,
                         "etapes_associees": sum(r >= 1 for r in rangs), "couverture_etapes": _pct(sum(r >= 1 for r in rangs), len(rangs)),
                         "niveau": NIVEAUX[min(rangs)] if rangs else "découvert"})

    def repartition(l):
        return {lv: sum(_rang(x["niveau"]) >= _rang(lv) for x in l) for lv in NIVEAUX}

    rc, re_, rp = repartition(composants), repartition(ecrans), repartition(parcours)
    indicateurs = {
        "couverture_ecrans": {"valeur": _pct(re_["associé"], len(ecrans)), "detail": f"{re_['associé']}/{len(ecrans)} écran(s) au moins associé(s)"},
        "couverture_composants": {"valeur": _pct(rc["associé"], len(composants)), "detail": f"{rc['associé']}/{len(composants)} composant(s) utilisés par un test"},
        "couverture_parcours": {"valeur": _pct(rp["associé"], len(parcours)), "detail": f"{rp['associé']}/{len(parcours)} parcours dont toutes les étapes sont associées"},
        "automatisation_composants": {"valeur": _pct(rc["automatisé"], len(composants)), "detail": f"{rc['automatisé']}/{len(composants)} composant(s) couverts par un test automatisé tracé dans Xray"},
        "reussite_composants": {"valeur": _pct(rc["réussi"], len(composants)), "detail": f"{rc['réussi']}/{len(composants)} composant(s) dont un test a réussi à sa dernière exécution"},
    }
    return {"date": datetime.now().astimezone().isoformat(timespec="seconds"), "module": module, "niveaux": NIVEAUX, "definitions": DEFINITIONS,
            "indicateurs": indicateurs, "repartition": {"composants": rc, "ecrans": re_, "parcours": rp},
            "ecrans": ecrans, "composants": composants, "parcours": parcours,
            "sans_test": {"ecrans": [e["nom"] for e in ecrans if e["niveau"] == "découvert"],
                          "composants": [f"{c['ecran']}.{c['cle']}" for c in composants if c["niveau"] == "découvert" and c["classe"] != "forbidden"],
                          "parcours": [p["libelle"] for p in parcours if p["etapes_associees"] < len(p["etapes"])]},
            "source": "Knowledge Graph (carte, dépôt Robot, patrimoine Xray, résultats des runs)",
            "limites": "Tests manuels : aucune couverture au niveau composant (étapes Xray en texte libre) ; association écran ↔ test Xray déduite via les fonctionnalités."}
