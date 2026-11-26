"""Quality Governance : mesurer, comprendre, anticiper (cahier des charges « Module Quality Governance »).

Tout indicateur porte sa définition, sa formule, sa source et sa date de calcul ; un indicateur sans
données est « indisponible » (valeur None), jamais estimé. Les recommandations sont produites par des
règles explicables, chacune avec les données qui la justifient ; une synthèse IA reste optionnelle.
Stockage projet : gouvernance/parametres.yaml, historique.jsonl (instantanés), releases.jsonl,
recommandations.json.
"""
from __future__ import annotations

from atelier.domain.yaml_rapide import charger as charger_yaml

import json
from collections import Counter
from datetime import datetime, timedelta

import yaml

from atelier.domain import projet
from atelier.intelligence.strategie import _auteur, _ecrire_atomique, _maintenant

DEFAUTS = {
    "seuils": {"couverture_ok": 80, "couverture_partielle": 50, "flaky_executions_min": 3, "flaky_transitions_min": 2,
               "fenetre_runs": 30, "jours_sans_execution": 30, "risque_high": 60, "risque_medium": 35},
    "poids_risque": {"criticite": 30, "couverture": 25, "automatisation": 15, "echecs": 20, "instabilite": 10},
    "poids_sante": {"locators": 40, "revue": 30, "reutilisation": 30},
    "poids_release": {"couverture_critique": 25, "resultats": 25, "anomalies": 20, "stabilite": 15, "couverture_auto": 10, "tracabilite": 5},
    "release": {"seuil_ready": 80, "seuil_avec_risques": 60, "donnees_min_pct": 60, "anomalies_plafond": 5},
    "minutes_manuelles_par_test": None,  # ROI indisponible tant que non renseigné
}
STATUTS_RECO = ["Proposed", "Accepted", "Rejected", "In Progress", "Completed"]
CRITICITE = {"Critique": 1.0, "Haute": 0.75, "Moyenne": 0.5, "Basse": 0.25}


def _d():
    return projet.PROJECT_DIR / "gouvernance"


def parametres() -> dict:
    f = _d() / "parametres.yaml"
    p = charger_yaml(f.read_text("utf-8")) if f.exists() else {}
    out = json.loads(json.dumps(DEFAUTS))
    for k, v in (p or {}).items():
        out[k] = {**out[k], **v} if isinstance(out.get(k), dict) and isinstance(v, dict) else v
    return out


def enregistrer_parametres(p: dict) -> dict:
    for groupe in ("poids_risque", "poids_release"):
        if groupe in p and (any(float(v) < 0 for v in p[groupe].values()) or not sum(float(v) for v in p[groupe].values())):
            raise ValueError(f"{groupe} : pondérations positives, de somme non nulle.")
    m = p.get("minutes_manuelles_par_test")
    if m not in (None, "") and float(m) <= 0:
        raise ValueError("Minutes manuelles par test : nombre positif.")
    s = (p.get("seuils") or {})
    if s and float(s.get("risque_medium", 0)) > float(s.get("risque_high", 100)):
        raise ValueError("Seuil de risque MEDIUM supérieur au seuil HIGH.")
    if "release" in p and float(p["release"].get("anomalies_plafond", 1)) <= 0:
        raise ValueError("Plafond d'anomalies : nombre positif.")
    avant = parametres()
    base = json.loads(json.dumps(avant))
    base.update({k: v for k, v in p.items() if k in DEFAUTS})
    _ecrire_atomique(_d() / "parametres.yaml", yaml.safe_dump(base, allow_unicode=True, sort_keys=False))
    apres = parametres()
    diff = {f"{g}.{k}" if isinstance(apres[g], dict) else g: {"avant": (avant[g].get(k) if isinstance(avant[g], dict) else avant[g]),
                                                               "apres": (v if isinstance(apres[g], dict) else apres[g])}
            for g in apres for k, v in (apres[g].items() if isinstance(apres[g], dict) else [(None, apres[g])])
            if (avant[g].get(k) if isinstance(avant[g], dict) else avant[g]) != v}
    if diff:  # toute modification de paramètre est tracée (qui, quand, avant / après)
        with (_d() / "parametres_historique.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"date": _maintenant(), "auteur": _auteur(), "changements": diff}, ensure_ascii=False) + "\n")
    return apres


def historique_parametres() -> list[dict]:
    f = _d() / "parametres_historique.jsonl"
    return [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()][::-1] if f.exists() else []


# =========================================================================== données de base
def _sources() -> dict:
    from atelier.discovery import connaissance
    from atelier.execution import historique
    from atelier.intelligence import patrimoine_xray

    p = parametres()
    pat = patrimoine_xray.charger_vue() or {"tests": [], "exigences": [], "plans": []}
    g = connaissance.construire()
    auto = {t["cle"] for t in pat["tests"] if (n := g.noeuds.get(f"test:{t['cle']}")) and n.proprietes.get("automatise")}
    runs = [r for r in historique.lister(p["seuils"]["fenetre_runs"]) if not r["dry_run"] and r.get("passes") is not None]
    seq: dict = {}
    for r in reversed(runs):
        try:
            for t in historique.detail(r["id"]).get("tests", []):
                seq.setdefault(t["nom"], []).append({"run": r["id"], "statut": t["statut"], "plateforme": r["plateforme"],
                                                     "env": (r.get("contexte") or {}).get("environnement", ""), "duree": t["duree_s"],
                                                     "cle": (t.get("cles_xray") or [""])[0]})
        except Exception:
            continue
    return {"p": p, "pat": pat, "auto": auto, "runs": runs, "seq": seq, "g": g, "date": _maintenant(),
            "date_xray": (pat.get("date") or "")}


def _par_exigence(pat) -> dict:
    d: dict = {}
    for t in pat["tests"]:
        for e in t.get("exigences") or []:
            d.setdefault(e, []).append(t["cle"])
    return d


# =========================================================================== stabilité
def stabilite(s: dict | None = None) -> dict:
    s = s or _sources()
    mini = s["p"]["seuils"]["flaky_executions_min"]
    trans_min = s["p"]["seuils"].get("flaky_transitions_min", 2)
    out = []
    for nom, l in s["seq"].items():
        st = [x["statut"] for x in l]
        transitions = sum(a != b for a, b in zip(st, st[1:]))
        flaky = len(st) >= mini and "PASS" in st and "FAIL" in st and transitions >= trans_min
        out.append({"test": nom, "cle_xray": l[-1]["cle"], "executions": len(st), "sequence": st[-10:], "transitions": transitions,
                    "taux_reussite": round(100 * st.count("PASS") / len(st), 1), "classification": "Potentially flaky" if flaky else
                    "Constamment en échec" if set(st) == {"FAIL"} else "Stable" if set(st) == {"PASS"} else "À surveiller",
                    "durees": [x["duree"] for x in l[-10:]], "plateformes": sorted({x["plateforme"] for x in l})})
    instables_retry = sorted({n for r in s["runs"] for n in (r.get("instables") or [])})
    premiers = [r for r in s["runs"]]
    p1 = sum((r["passes"] + r["echecs"]) for r in premiers)
    return {"tests": sorted(out, key=lambda x: (x["classification"] != "Potentially flaky", x["taux_reussite"])),
            "flaky": [x["test"] for x in out if x["classification"] == "Potentially flaky"], "instables_retry": instables_retry,
            "definition": f"Potentially flaky : au moins {mini} exécutions réelles, résultats PASS et FAIL, et au moins {trans_min} changements de statut. "
                          "Un test toujours en échec n'est pas instable.", "tests_executes": len(out), "executions_total": p1}


# =========================================================================== couvertures
def couverture_fonctionnelle(s: dict | None = None) -> dict:
    s = s or _sources()
    pex = _par_exigence(s["pat"])
    ok, part = s["p"]["seuils"]["couverture_ok"], s["p"]["seuils"]["couverture_partielle"]
    exig = []
    for e in s["pat"]["exigences"]:
        ts = pex.get(e["cle"], [])
        na = sum(t in s["auto"] for t in ts)
        etat = "indisponible" if e["type"] == "epic" and not ts else "insuffisante" if not ts else "satisfaisante"  # existence ; automatisation à part
        exig.append({**{k: e.get(k) for k in ("cle", "type", "resume", "module", "parent", "statut")}, "tests": ts, "automatises": na, "etat": etat})
    modules: dict = {}
    for e in exig:
        if e["etat"] == "indisponible":
            continue
        m = modules.setdefault(e["module"] or "—", {"module": e["module"] or "—", "exigences": 0, "couvertes": 0, "auto": 0})
        m["exigences"] += 1
        m["couvertes"] += bool(e["tests"])
        m["auto"] += e["automatises"] > 0
    for m in modules.values():
        m["pct"] = round(100 * m["couvertes"] / m["exigences"], 1)
        m["etat"] = "satisfaisante" if m["pct"] >= ok else "partielle" if m["pct"] >= part else "insuffisante"
    lies = {t for ts in pex.values() for t in ts}
    return {"exigences": exig, "modules": list(modules.values()),
            "sans_exigence": [t["cle"] for t in s["pat"]["tests"] if t["cle"] not in lies],
            "definition": "Exigence couverte (satisfaisante) : au moins un test Xray lié ; insuffisante : aucun test ; l'automatisation est comptée à part "
                          "(colonne automatisés) ; une epic sans test direct est « indisponible » (agrégée par ses stories). Vue complète : Test Strategy › Couverture et traçabilité.",
            "source": f"Instantané Xray du {s['date_xray'][:16]} + dépôt Robot", "date": s["date"]}


def couverture_automatisation(s: dict | None = None) -> dict:
    from atelier.execution.depot_robot import lire_depot

    s = s or _sources()
    inv = lire_depot()
    plats_par_cle: dict = {}
    for t in inv["tests"].values():
        for c in t.get("cles_xray") or []:
            plats_par_cle.setdefault(c, set()).update(t.get("plateformes") or [])
    modules: dict = {}
    for t in s["pat"]["tests"]:
        m = modules.setdefault(t.get("module") or "—", {"module": t.get("module") or "—", "total": 0, "manuels": 0, "automatises": 0,
                                                         "plateformes": Counter()})
        m["total"] += 1
        if t["cle"] in s["auto"]:
            m["automatises"] += 1
            m["plateformes"].update(plats_par_cle.get(t["cle"], []))
        else:
            m["manuels"] += 1
    for m in modules.values():
        m["couverture"] = round(100 * m["automatises"] / m["total"], 1) if m["total"] else None
        m["plateformes"] = dict(m["plateformes"])
    try:
        from atelier.intelligence import strategie

        plan = Counter(c["statut_plan"] for c in strategie.plan_automatisation())
    except Exception:
        plan = Counter()
    return {"modules": list(modules.values()), "plan": dict(plan),
            "par_plateforme": {p: sum(p in v for v in plats_par_cle.values()) for p in ("web", "android", "ios", "api")},
            "definition": "Test automatisé : test Xray dont la clé est portée en tag par au moins un test Robot du dépôt ; "
                          "par plateforme : plateformes des bibliothèques du test Robot.", "date": s["date"]}


# =========================================================================== efficacité et santé
def efficacite(s: dict | None = None) -> dict:
    from atelier.intelligence import couverture

    s = s or _sources()
    tests = [{"test": n, "cle_xray": l[-1]["cle"], "executions": len(l), "echecs": sum(x["statut"] == "FAIL" for x in l)} for n, l in s["seq"].items()]
    for t in tests:
        t["taux_echec"] = round(100 * t["echecs"] / t["executions"], 1)
    try:
        from atelier.execution import echecs

        ev = echecs.collecter(s["p"]["seuils"]["fenetre_runs"])
    except Exception:
        ev = []
    module_de = {t["cle"]: t.get("module") for t in s["pat"]["tests"]}
    return {"tests": sorted(tests, key=lambda x: -x["taux_echec"]),
            "echecs_par_module": dict(Counter(module_de.get(e["cle_xray"]) or "—" for e in ev)),
            "defauts_confirmes": sum(e["categorie_confirmee"] == "Application Defect" for e in ev),
            "echecs_sans_defaut": sum(e["categorie_confirmee"] not in ("", "Application Defect") for e in ev),
            "jamais_en_echec": [t["test"] for t in tests if t["executions"] >= 3 and not t["echecs"]],
            "redondances": couverture.redondances(s["pat"]["tests"]) if s["pat"]["tests"] else [],
            "note": "« Jamais en échec » n'est pas « sans valeur » : un test de non-régression peut légitimement toujours passer.",
            "date": s["date"]}


def sante_automatisation(s: dict | None = None) -> dict:
    from atelier.execution.robot import derniers_resultats
    from atelier.generation import studio

    s = s or _sources()
    locs, kws, rev = studio.locators(), studio.keywords(), studio.revues_scripts()
    res = derniers_resultats()
    limite = datetime.now() - timedelta(days=s["p"]["seuils"]["jours_sans_execution"])
    from atelier.execution.depot_robot import lire_depot

    inv = lire_depot()
    jamais = [t for t in inv["tests"] if t not in res]
    anciens = [t for t, r in res.items() if r.get("fin") and datetime.fromisoformat(str(r["fin"])[:19]) < limite]
    try:
        from atelier.execution import echecs

        backlog = [e for e in echecs.collecter(60) if (e["categorie_confirmee"] or "") in ("Locator Issue", "Automation Defect", "Timing Issue")
                   and e["statut"] not in ("Closed", "Fixed")]
    except Exception:
        backlog = []
    n = lambda c: sum(1 for l in locs if l["etat"] == c)  # noqa: E731
    sante_loc = round(100 * (n("Stable") + n("Reliable")) / len(locs), 1) if locs else None
    conformite = round(100 * sum(r["statut"] in ("Approved", "Published") for r in rev.values()) / len(rev), 1) if rev else None
    reutil = round(100 * sum(k["utilisations"] >= 2 for k in kws) / len(kws), 1) if kws else None
    ps = s["p"]["poids_sante"]
    parts = [(sante_loc, ps["locators"]), (conformite, ps["revue"]), (reutil, ps["reutilisation"])]
    dispo = [(v, w) for v, w in parts if v is not None]
    return {"indicateurs": {"locators_sains": sante_loc, "conformite_revue": conformite, "reutilisation_keywords": reutil,
                            "keywords_doublons": sum(k["doublon"] for k in kws), "keywords_inutilises": sum(k["inutilise"] for k in kws),
                            "scripts_jamais_executes": len(jamais), "scripts_non_executes_recemment": len(anciens),
                            "backlog_maintenance": len(backlog),
                            "score": round(sum(v * w for v, w in dispo) / sum(w for _, w in dispo), 1) if dispo else None},
            "locators": Counter(l["etat"] for l in locs), "jamais_executes": jamais[:30], "backlog": backlog[:30],
            "definition": f"Santé = moyenne pondérée : locators stables ou fiables (poids {ps['locators']}), scripts approuvés / publiés "
                          f"(poids {ps['revue']}), keywords réutilisés, 2 appels et plus (poids {ps['reutilisation']}) ; "
                          "composantes sans donnée exclues et pondérations renormalisées.", "date": s["date"]}


# =========================================================================== risques
def risques(s: dict | None = None) -> dict:
    s = s or _sources()
    w = s["p"]["poids_risque"]
    hi, med = s["p"]["seuils"].get("risque_high", 60), s["p"]["seuils"].get("risque_medium", 35)
    cf = {m["module"]: m for m in couverture_fonctionnelle(s)["modules"]}
    ca = {m["module"]: m for m in couverture_automatisation(s)["modules"]}
    crit_strat = {}
    try:
        from atelier.intelligence import strategie

        for x in (strategie.charger() or {"rubriques": {"perimetre": []}})["rubriques"]["perimetre"]:
            if x.get("niveau") == "module" and x.get("criticite"):
                crit_strat[x["nom"]] = x["criticite"]
    except Exception:
        pass
    flaky = set(stabilite(s)["flaky"])
    out = []
    for mod in sorted(set(cf) | set(ca)):
        tests = [t for t in s["pat"]["tests"] if (t.get("module") or "—") == mod]
        crit = crit_strat.get(mod) or max((t.get("criticite") or "Basse" for t in tests), key=lambda c: CRITICITE.get(c, 0), default="")
        execs = [x for n, l in s["seq"].items() for x in l if x["cle"] in {t["cle"] for t in tests}]
        facteurs = {"criticite": CRITICITE.get(crit), "couverture": 1 - cf[mod]["pct"] / 100 if mod in cf else None,
                    "automatisation": 1 - (ca[mod]["couverture"] or 0) / 100 if mod in ca and ca[mod]["couverture"] is not None else None,
                    "echecs": sum(x["statut"] == "FAIL" for x in execs) / len(execs) if execs else None,
                    "instabilite": sum(1 for n in flaky if any(x["cle"] in {t["cle"] for t in tests} for x in s["seq"].get(n, []))) / len(tests) if tests else None}
        dispo = {k: v for k, v in facteurs.items() if v is not None}
        score = round(100 * sum(w[k] * v for k, v in dispo.items()) / sum(w[k] for k in dispo), 1) if dispo else None
        out.append({"module": mod, "score": score, "niveau": None if score is None else "HIGH" if score >= hi else "MEDIUM" if score >= med else "LOW",
                    "criticite": crit, "facteurs": {k: (round(v, 2) if v is not None else None) for k, v in facteurs.items()},
                    "tests": len(tests), "lacunes": [e["cle"] for e in couverture_fonctionnelle(s)["exigences"] if (e["module"] or "—") == mod and e["etat"] == "insuffisante"]})
    return {"modules": sorted(out, key=lambda x: -(x["score"] or 0)), "poids": w,
            "definition": "Score = moyenne pondérée des facteurs disponibles (0 à 1) × 100 : criticité, manque de couverture, manque d'automatisation, "
                          f"taux d'échec, part de tests instables. HIGH ≥ {hi}, MEDIUM ≥ {med} (paramétrables). Facteur sans donnée exclu (pondérations renormalisées).",
            "date": s["date"]}


# =========================================================================== KPI, instantanés, tendances
def kpis(s: dict | None = None) -> list[dict]:
    s = s or _sources()
    cf, st, sa = couverture_fonctionnelle(s), stabilite(s), sante_automatisation(s)
    pat, runs = s["pat"], s["runs"][:10]
    ex = [e for e in cf["exigences"] if e["etat"] != "indisponible"]
    mods = cf["modules"]
    p, e = sum(r["passes"] for r in runs), sum(r["echecs"] for r in runs)
    sans_retry = [r for r in runs if (r.get("tentatives") or 1) <= 1]
    hautes_manuelles = {t["cle"] for t in pat["tests"] if t.get("criticite") == "Haute" and t["cle"] not in s["auto"]}
    inconnues = []
    try:
        from atelier.intelligence import couverture

        inconnues = couverture.indicateurs(s["g"], pat).get("cles_robot_inconnues_de_xray", []) if pat["tests"] else []
    except Exception:
        pass
    minutes = s["p"].get("minutes_manuelles_par_test")
    roi = round(sum((r["passes"] or 0) + (r["echecs"] or 0) for r in s["runs"]) * float(minutes) / 60, 1) if minutes else None
    src_x, src_r = f"Xray ({s['date_xray'][:10] or 'aucun instantané'})", f"{len(s['runs'])} run(s) réels"
    K = lambda i, l, v, u, d, f, src: {"id": i, "libelle": l, "valeur": v, "unite": u, "definition": d, "formule": f, "source": src, "date": s["date"]}  # noqa: E731
    return [
        K("functional_coverage", "Functional Coverage", round(100 * sum(m["couvertes"] > 0 for m in mods) / len(mods), 1) if mods else None, "%",
          "Modules fonctionnels ayant au moins une exigence testée (les fonctionnalités = modules tant qu'aucune n'est déclarée).", "modules couverts / modules", src_x),
        K("test_coverage", "Test Coverage", round(100 * sum(bool(x["tests"]) for x in ex) / len(ex), 1) if ex else None, "%",
          "Exigences couvertes par au moins un test.", "exigences avec test / exigences (hors epics sans test direct)", src_x),
        K("automation_coverage", "Automation Coverage", round(100 * len(s["auto"]) / len(pat["tests"]), 1) if pat["tests"] else None, "%",
          "Part des tests Xray automatisés.", "tests portés en tag Robot / tests Xray", f"{src_x} + dépôt"),
        K("pass_rate", "Pass Rate", round(100 * p / (p + e), 1) if p + e else None, "%", "Taux de réussite des 10 derniers runs réels.", "tests PASS / tests exécutés", src_r),
        K("test_stability", "Test Stability", round(100 * sum(r["echecs"] == 0 for r in sans_retry) / len(sans_retry), 1) if sans_retry else None, "%",
          "Runs réussis au premier passage (sans retry).", "runs sans échec ni retry / runs sans retry", src_r),
        K("flaky_rate", "Flaky Rate", round(100 * len(st["flaky"]) / st["tests_executes"], 1) if st["tests_executes"] else None, "%", st["definition"],
          "tests potentiellement flaky / tests exécutés", src_r),
        K("automation_health", "Automation Health", sa["indicateurs"]["score"], "/100", sa["definition"], "pondération des composantes disponibles", "Automation Studio"),
        K("critical_gaps", "Critical Gaps", sum(not x["tests"] or bool(hautes_manuelles & set(x["tests"])) for x in ex) if ex else None, "",
          "Exigences sans test, ou liées à un test de criticité Haute non automatisé.", "comptage", src_x),
        K("obsolete_tests", "Obsolete Tests", len(inconnues) + sa["indicateurs"]["scripts_non_executes_recemment"], "",
          "Tests Robot portant une clé inconnue de Xray + scripts non exécutés depuis le délai configuré.", "comptage", f"{src_x} + résultats"),
        K("automation_roi", "Automation ROI", roi, "h", "Heures d'exécution manuelle évitées par les runs automatisés.",
          "tests exécutés × minutes manuelles par test / 60 (paramètre requis)", f"{src_r} + paramètre"),
    ]


def instantane(force: bool = False) -> dict:
    """Enregistre l'état des KPI (au plus un instantané automatique par jour) pour garder l'historique."""
    f = _d() / "historique.jsonl"
    l = [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()] if f.exists() else []
    if l and not force and l[-1]["date"][:10] == _maintenant()[:10]:
        return l[-1]
    k = kpis()
    snap = {"date": _maintenant(), "auteur": _auteur(), "kpis": {x["id"]: x["valeur"] for x in k}}
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(snap, ensure_ascii=False) + "\n")
    return snap


def tendances() -> dict:
    f = _d() / "historique.jsonl"
    snaps = [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()] if f.exists() else []
    s = _sources()
    return {"instantanes": snaps, "runs": [{"id": r["id"], "debut": r["debut"], "passes": r["passes"], "echecs": r["echecs"],
                                             "plateforme": r["plateforme"], "campagne": r.get("campagne", "")} for r in reversed(s["runs"])]}


# =========================================================================== release readiness
def evaluer_release(version: str = "", campagne: str = "", environnement: str = "", commit: str = "") -> dict:
    s = _sources()
    p = s["p"]
    cf = couverture_fonctionnelle(s)
    runs = [r for r in s["runs"] if (not campagne or r.get("campagne") == campagne) and (not environnement or (r.get("contexte") or {}).get("environnement") == environnement)]
    crit = [e for e in cf["exigences"] if e["etat"] != "indisponible" and any(t.get("criticite") == "Haute" for t in s["pat"]["tests"] if t["cle"] in e["tests"])]
    try:
        from atelier.execution import echecs

        ouverts = [e for e in echecs.collecter(60) if e["categorie_confirmee"] == "Application Defect" and e["statut"] not in ("Closed", "Fixed")]
        plafond = float(p["release"].get("anomalies_plafond", 5))
        anomalies = 1.0 if not ouverts else max(0.0, 1 - len(ouverts) / plafond)
    except Exception:
        anomalies, ouverts = None, []
    st = stabilite(s)
    criteres = {
        "couverture_critique": (sum(bool(e["tests"]) for e in crit) / len(crit)) if crit else None,
        "resultats": (runs[0]["passes"] / (runs[0]["passes"] + runs[0]["echecs"])) if runs and runs[0]["passes"] + runs[0]["echecs"] else None,
        "anomalies": anomalies,
        "stabilite": (1 - len(st["flaky"]) / st["tests_executes"]) if st["tests_executes"] else None,
        "couverture_auto": (len(s["auto"]) / len(s["pat"]["tests"])) if s["pat"]["tests"] else None,
        "tracabilite": (1 - len(cf["sans_exigence"]) / len(s["pat"]["tests"])) if s["pat"]["tests"] else None}
    w = p["poids_release"]
    dispo = {k: v for k, v in criteres.items() if v is not None}
    pct_dispo = 100 * sum(w[k] for k in dispo) / sum(w.values())
    score = round(100 * sum(w[k] * v for k, v in dispo.items()) / sum(w[k] for k in dispo), 1) if dispo else None
    echecs_dernier = runs[0]["echecs"] if runs else None
    etat = ("Insufficient Data" if pct_dispo < p["release"]["donnees_min_pct"] or score is None else
            "Ready" if score >= p["release"]["seuil_ready"] and not echecs_dernier and not ouverts else
            "Ready with Risks" if score >= p["release"]["seuil_avec_risques"] else "Not Ready")
    ev = {"id": f"REL-{_maintenant().replace(':', '').replace('-', '')}", "date": _maintenant(), "auteur": _auteur(), "version": version,
          "campagne": campagne, "environnement": environnement, "commit": commit, "run_reference": runs[0]["id"] if runs else "",
          "criteres": {k: (round(100 * v, 1) if v is not None else None) for k, v in criteres.items()}, "poids": w, "donnees_disponibles_pct": round(pct_dispo, 1),
          "score": score, "etat": etat, "anomalies_ouvertes": [x["id"] for x in ouverts], "flaky": st["flaky"],
          "avertissement": "Le score n'autorise pas une mise en production : la décision reste au QA Manager.", "validation": None}
    f = _d() / "releases.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return ev


def releases() -> list[dict]:
    f = _d() / "releases.jsonl"
    l = [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()] if f.exists() else []
    return list(reversed(l))


def valider_release(rid: str, decision: str, commentaire: str = "") -> dict:
    """Avis QA Manager historisé (l'évaluation elle-même n'est jamais réécrite)."""
    if decision not in ("approuvée", "refusée"):
        raise ValueError("Décision : approuvée ou refusée.")
    if not commentaire.strip():
        raise ValueError("Commentaire obligatoire.")
    if not any(r["id"] == rid for r in releases()):
        raise KeyError(f"Évaluation inconnue : {rid}")
    f = _d() / "validations_release.jsonl"
    v = {"release": rid, "decision": decision, "commentaire": commentaire.strip(), "par": _auteur(), "date": _maintenant()}
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(v, ensure_ascii=False) + "\n")
    return v


def validations_release() -> list[dict]:
    f = _d() / "validations_release.jsonl"
    return [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()] if f.exists() else []


# =========================================================================== recommandations
def recommandations() -> list[dict]:
    """Règles explicables -> recommandations avec leurs données ; statut et responsable conservés."""
    s = _sources()
    cf, ca, st, sa = couverture_fonctionnelle(s), couverture_automatisation(s), stabilite(s), sante_automatisation(s)
    out = []
    add = lambda i, cat, prio, titre, just, module_cible: out.append({"id": i, "categorie": cat, "priorite": prio, "titre": titre,  # noqa: E731
                                                                     "justification": just, "module_cible": module_cible})
    for e in cf["exigences"]:
        if e["etat"] == "insuffisante":
            add(f"cov:{e['cle']}", "Functional Coverage", "HIGH", f"Concevoir un test pour {e['cle']} ({e['resume']})",
                f"Exigence {e['cle']} sans aucun test Xray associé (instantané du {s['date_xray'][:10]}).", "Test Design")
    for m in ca["modules"]:
        if m["couverture"] is not None and m["couverture"] < s["p"]["seuils"]["couverture_ok"]:
            add(f"auto:{m['module']}", "Automation Coverage", "MEDIUM", f"Augmenter l'automatisation du module {m['module']}",
                f"{m['automatises']}/{m['total']} tests automatisés ({m['couverture']} %), seuil {s['p']['seuils']['couverture_ok']} %.", "Test Strategy")
    for t in st["tests"]:
        if t["classification"] == "Constamment en échec":
            add(f"echec:{t['test']}", "Risk Reduction", "HIGH", f"Diagnostiquer « {t['test']} » (échec à chaque exécution)",
                f"{t['executions']} exécution(s), toutes en échec : défaut applicatif probable ou script à corriger.", "Failure Analysis")
        if t["classification"] == "Potentially flaky":
            add(f"flaky:{t['test']}", "Test Stability", "HIGH", f"Stabiliser « {t['test']} »",
                f"Séquence {' → '.join(t['sequence'])} ({t['transitions']} changements de statut).", "Automation Studio")
    if sa["locators"].get("Fragile") or sa["locators"].get("Obsolete"):
        add("loc:fragiles", "Locator Maintenance", "MEDIUM", "Corriger les locators fragiles ou obsolètes",
            f"{sa['locators'].get('Fragile', 0)} fragile(s), {sa['locators'].get('Obsolete', 0)} obsolète(s) dans le référentiel.", "Automation Studio")
    if sa["indicateurs"]["conformite_revue"] is not None and sa["indicateurs"]["conformite_revue"] < 100:
        add("revue:scripts", "Script Maintenance", "LOW", "Faire passer les scripts en revue technique",
            f"{sa['indicateurs']['conformite_revue']} % des suites approuvées ou publiées.", "Automation Studio")
    for t in cf["sans_exigence"]:
        add(f"trace:{t}", "Test Design", "LOW", f"Rattacher le test {t} à une exigence", f"Le test Xray {t} n'est lié à aucune exigence.", "Test Design")
    f = _d() / "recommandations.json"
    suivi = json.loads(f.read_text("utf-8")) if f.exists() else {}
    for r in out:
        r.update(suivi.get(r["id"], {"statut": "Proposed", "responsable": ""}))
    ordre = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    return sorted(out, key=lambda r: (r["statut"] in ("Completed", "Rejected"), ordre[r["priorite"]]))


def suivre_recommandation(rid: str, statut: str, responsable: str = "", commentaire: str = "") -> dict:
    if statut not in STATUTS_RECO:
        raise ValueError(f"Statut : {', '.join(STATUTS_RECO)}.")
    if statut == "Rejected" and not commentaire.strip():
        raise ValueError("Un rejet doit être justifié.")
    f = _d() / "recommandations.json"
    suivi = json.loads(f.read_text("utf-8")) if f.exists() else {}
    h = suivi.get(rid, {}).get("historique", [])
    h.append({"date": _maintenant(), "par": _auteur(), "statut": statut, "commentaire": commentaire.strip()})
    suivi[rid] = {"statut": statut, "responsable": responsable.strip(), "historique": h}
    _ecrire_atomique(f, json.dumps(suivi, ensure_ascii=False, indent=1))
    return suivi[rid]


def vue_ensemble() -> dict:
    """Lecture seule : l'instantané quotidien est pris par le planificateur de l'interface, pas par un affichage."""
    s = _sources()
    return {"kpis": kpis(s), "modules": couverture_fonctionnelle(s)["modules"], "automatisation": couverture_automatisation(s)["modules"],
            "risques": risques(s)["modules"], "locators": dict(sante_automatisation(s)["locators"]), "date": s["date"],
            "recommandations": [r for r in recommandations() if r["statut"] in ("Proposed", "Accepted", "In Progress")][:6]}
