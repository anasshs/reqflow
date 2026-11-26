"""Couverture avancée (V2, phase 3) : parcours et composants UI, avec des NIVEAUX de couverture explicables.

Tout est calculé sur le Knowledge Graph existant (aucun second référentiel) :
  écran ─contient→ locator (un composant = une clé métier de l'écran, toutes plateformes)
  keyword ─utilise→ locator ; test Robot ─appelle→ keyword (et keyword ─appelle→ keyword) ; un locator du dépôt de même
  valeur (ou de même resource-id) qu'un locator de la carte est relié à celui-ci (connaissance._depuis_depot)
  scénario BDD ─couvre→ écran (écrans de ses étapes) et ─implémenté par→ test Robot : l'écran est couvert par ce test
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
    "associé": "Utilisé par au moins un test Robot (keyword → locator) ; pour un écran, aussi parcouru par un scénario BDD automatisé, ou via une fonctionnalité dont une US a un test Xray (déduit).",
    "automatisé": "Utilisé par un test Robot rattaché à un test Xray (clé Xray en tag).",
    "exécuté": "Un de ces tests a au moins une exécution réelle connue (effectivement vérifié).",
    "réussi": "La dernière exécution d'un de ces tests est réussie (PASS).",
}


SOCLE_PART, SOCLE_MIN_TESTS = 0.6, 5  # keyword appelé par 60 % des tests (5 tests au moins) : socle commun


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
    fermetures: dict[str, set] = {}
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
        fermetures[tid] = vus
    # socle commun : keyword appelé (directement ou non) par la plupart des tests (initialisation, popups au démarrage,
    # teardown). Les écrans qu'il touche « au cas où » ne sont pas couverts par chacun de ces tests.
    appels: dict[str, int] = {}
    for vus in fermetures.values():
        for k in vus:
            appels[k] = appels.get(k, 0) + 1
    socle = {k for k, nb in appels.items() if len(fermetures) >= SOCLE_MIN_TESTS and nb / len(fermetures) >= SOCLE_PART}
    tests_par_locator: dict[str, set] = {}
    for tid, vus in fermetures.items():
        for k in vus - socle:
            for loc in sortants(k, "utilise"):
                tests_par_locator.setdefault(loc, set()).add(tid)

    def info_test(tid):
        p = N[tid].proprietes
        return {"id": tid, "nom": N[tid].libelle, "xray": list(p.get("cles_xray") or []), "statut": p.get("dernier_statut") or ""}

    # écrans des étapes d'un scénario BDD automatisé -> tests Robot qui l'implémentent
    tests_par_ecran_bdd: dict[str, set] = {}
    for sid, n in N.items():
        if n.type != "scenario":
            continue
        robots = [t for t in sortants(sid, "implemente_par") if N[t].type == "test_robot"]
        for e in sortants(sid, "couvre"):
            if N[e].type == "ecran" and robots:
                tests_par_ecran_bdd.setdefault(e, set()).update(robots)

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
        par_bdd = [info_test(t) for t in sorted(tests_par_ecran_bdd.get(eid, set()))]
        tous = sorted({t for c in comps for t in c["tests"]} | {t["nom"] for t in par_bdd})
        niv_comp = max([_rang(c["niveau"]) for c in comps] + [_rang(_niveau_tests(par_bdd))], default=0)
        deduits = sorted(N[t].libelle for t in xray_par_ecran.get(eid, set()))
        niveau = NIVEAUX[niv_comp] if niv_comp else ("associé" if deduits else "découvert")
        ecrans.append({"id": eid, "nom": n.libelle, "module": mod, "composants": len(comps),
                       "composants_par_niveau": {lv: sum(_rang(c["niveau"]) >= _rang(lv) for c in comps) for lv in NIVEAUX},
                       "niveau": niveau, "association_deduite": niveau == "associé" and not niv_comp,
                       "tests_robot": tous, "tests_xray_deduits": deduits,
                       "tests_xray": sorted({k for c in comps for k in c["tests_xray"]} | {k for t in par_bdd for k in t["xray"]})})

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


def _ordre_navigation(g, etapes: list[dict]) -> list[dict]:
    """Étapes d'un parcours dans l'ordre de navigation observé (écran → navigue vers → écran) : d'abord les écrans où
    l'on n'arrive depuis aucune autre étape, puis ceux qu'ils ouvrent. Ordre d'origine si rien n'est connu."""
    ids = [e["id"] for e in etapes]
    suiv = {i: [r.vers for r in g.sortants(i) if r.type == "navigue_vers" and r.vers in ids and r.vers != i] for i in ids}
    entrees = {i: sum(i in v for k, v in suiv.items() if k != i) for i in ids}
    ordre, vus = [], set()
    file = [i for i in ids if entrees[i] == 0] or ids[:1]
    while file:
        i = file.pop(0)
        if i in vus:
            continue
        vus.add(i)
        ordre.append(i)
        file += [x for x in suiv[i] if x not in vus]
    ordre += [i for i in ids if i not in vus]
    par = {e["id"]: e for e in etapes}
    return [par[i] for i in ordre]


def carte(g=None) -> dict:
    """Carte de couverture par les tests (écran « Couverture des tests ») : parcours en chaînes d'écrans, écrans par
    module, et matrice tests × écrans. État d'un écran : couvert (un test y va), echec (son dernier run a échoué),
    partiel (association déduite seulement), non_couvert. Un écran au nom technique (e_…) est nommé par son titre."""
    if g is None:
        from atelier.discovery import connaissance

        g = connaissance.construire()
    N = g.noeuds
    c = calculer(g)
    ordre_deroule: dict = {}  # nœud parcours -> identifiants de carte des écrans, dans l'ordre du déroulé
    try:
        from atelier.discovery import parcours_utilisateur

        for pu in parcours_utilisateur.lister():
            if pu.get("noeud"):
                ordre_deroule[pu["noeud"]] = [e["id"] for e in parcours_utilisateur.obtenir(pu["id"]).get("ecrans", [])]
    except Exception:  # noqa: BLE001 — sans cadrage, l'ordre de navigation du graphe suffit
        pass
    robots = {n.libelle: (i, n) for i, n in N.items() if n.type == "test_robot"}

    def etat(i):
        return (N[i].proprietes.get("couverture_tests") or {}).get("etat") or "non_couvert" if i in N else "non_couvert"

    def lisible(i, nom):
        titre = (N[i].proprietes.get("titre") or "").strip() if i in N else ""
        return (titre if (nom.startswith("e_") and titre) else nom).replace("_", " ")

    ecrans, tests = [], {}
    for e in c["ecrans"]:
        ts = []
        for nom in e["tests_robot"]:
            tid, n = robots.get(nom, (None, None))
            if not n:
                continue
            p = n.proprietes
            cle = (p.get("cles_xray") or [""])[0]
            tests.setdefault(tid, {"id": tid, "nom": nom, "cle_xray": cle, "statut": p.get("dernier_statut") or "", "fichier": p.get("fichier", "")})
            ts.append(tid)
        module = (e["module"] or "").strip()
        ecrans.append({"id": e["id"], "nom": lisible(e["id"], e["nom"]), "module": module[:1].upper() + module[1:] if module else "",
                       "etat": etat(e["id"]), "niveau": e["niveau"], "tests": ts,
                       "tests_xray": sorted({tests[t]["cle_xray"] for t in ts if tests[t]["cle_xray"]})})
    par_id = {e["id"]: e for e in ecrans}
    parcours = []
    for p in c["parcours"]:
        if not p["etapes"]:
            continue  # parcours sans écran (préparé, jamais déroulé, ou archivé)
        etapes = _ordre_navigation(g, [par_id[x["id"]] for x in p["etapes"] if x["id"] in par_id])
        rang = {i: k for k, i in enumerate(ordre_deroule.get(p["id"]) or [])}
        if rang:
            def cle(e):
                r = rang.get(N[e["id"]].proprietes.get("id_carte"))
                if r is not None:
                    return r
                # écran hors du déroulé (lien ajouté à part) : juste avant le premier écran du déroulé qu'il ouvre, sinon en tête
                suivants = [rang[N[x.vers].proprietes.get("id_carte")] for x in g.sortants(e["id"]) if x.type == "navigue_vers"
                            and x.vers in N and N[x.vers].proprietes.get("id_carte") in rang]
                return min(suivants) - 0.5 if suivants else -1  # souvent l'écran de départ (ajouté à part)
            etapes.sort(key=cle)
        parcours.append({"id": p["id"], "libelle": p["libelle"], "etat": etat(p["id"]),
                         "etapes": [{k: x[k] for k in ("id", "nom", "etat", "tests_xray")} for x in etapes]})
    nb = {k: sum(e["etat"] == k for e in ecrans) for k in ("couvert", "echec", "partiel", "non_couvert")}
    return {"date": c["date"], "parcours": parcours, "ecrans": ecrans, "tests": sorted(tests.values(), key=lambda t: (t["cle_xray"] or "~", t["nom"])),
            "indicateurs": {"parcours": len(parcours), "parcours_couverts": sum(p["etat"] == "couvert" for p in parcours),
                            "ecrans": len(ecrans), **nb}}
