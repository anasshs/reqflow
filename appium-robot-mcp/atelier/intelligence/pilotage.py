"""Dashboard de pilotage : « que devons-nous faire maintenant ? » plutôt que « où en sommes-nous ? ».

Ce module ne détient aucune donnée : il agrège et corrèle les référentiels existants (copie Jira / Xray, couverture
des exigences, Test Design, carte et Knowledge Graph, runs de l'atelier, Failure Analysis). Cinq zones :

  synthese    indicateurs du haut, avec leur évolution depuis l'instantané précédent ;
  conception  couverture des exigences, Discovery, qualité de la conception, couverture par sprint ;
  execution   activité, taux de réussite, anomalies, charge par responsable ;
  tnr         évolutions détectées → analyse d'impact → tests à rejouer, validés par un humain, envoyés en campagne ;
  decision    alertes avec leur action, recommandations, état de préparation de la livraison.

Règles tenues ici (cahier, § 10) :
  - couverte ≠ exécutée ≠ validée : trois mesures distinctes, jamais additionnées ;
  - seules les relations natives Jira / Xray et les relations fiables du graphe comptent : une proposition de l'IA non
    validée n'alimente aucun indicateur ;
  - bloqué et non exécuté ne sont jamais comptés comme échoués ; premier passage et résultat après relance sont séparés ;
  - chaque indicateur porte sa définition, sa formule, sa source et sa date ; une mesure impossible est dite
    « indisponible » avec la raison, jamais remplacée par une estimation ;
  - les recommandations sont des règles sur des faits mesurés, sans génération de texte par une IA ; chacune cite ses
    preuves et dit si elle repose sur une mesure ou sur une déduction.

Rien n'appelle Jira, Xray ni GitLab : tout vient des copies locales (leur date est affichée).
"""
from __future__ import annotations

import json
import sys
import subprocess
import time
from datetime import date, datetime, timedelta

import yaml

from atelier.domain import projet

CRITIQUES = ("highest", "high", "critical", "blocker", "critique", "bloquant", "bloquante", "haute", "très haute", "majeure", "p0", "p1")
ETIQUETTES_SECURITE = ("smoke", "tnr", "critique", "sanity")
PERIODE_JOURS = 14
_MEMO: dict = {}


# =========================================================================== outils
def _memo(nom: str, fn, duree: float = 45.0):
    """Une source lourde est calculée une fois pour les cinq zones d'un même affichage."""
    cle = (str(projet.PROJECT_DIR), nom)
    v = _MEMO.get(cle)
    if v and time.time() - v[0] < duree:
        return v[1]
    r = fn()
    _MEMO[cle] = (time.time(), r)
    return r


def vider_memo():
    _MEMO.clear()


def _sur(fn, defaut=None):
    """(valeur, raison) : une source absente ou en erreur donne un indicateur « indisponible », jamais une exception."""
    try:
        return fn(), ""
    except Exception as e:  # noqa: BLE001 — chaque zone reste affichable sans l'une de ses sources
        return defaut, str(e)[:200] or type(e).__name__


def _pct(a, b):
    return round(100 * a / b, 1) if b else None


def _ind(id_: str, libelle: str, valeur, definition: str, formule: str, source: str, lien: str = "", unite: str = "",
         date_: str = "", raison: str = "", detail: str = "") -> dict:
    return {"id": id_, "libelle": libelle, "valeur": valeur, "unite": unite, "disponible": valeur is not None,
            "raison": "" if valeur is not None else (raison or "donnée non disponible"), "definition": definition, "formule": formule,
            "source": source, "date": date_, "lien": lien, "detail": detail}


def _nombre(x) -> int:
    return len(x) if isinstance(x, (list, tuple, set, dict)) else int(x or 0)


def _jour(texte) -> str:
    return str(texte or "")[:10]


def _depuis(f: dict) -> str:
    return _jour(f.get("depuis")) or (date.today() - timedelta(days=PERIODE_JOURS)).isoformat()


def _dossier():
    return projet.PROJECT_DIR / "pilotage"


# =========================================================================== sources (copies locales)
def _pat() -> dict:
    from atelier.intelligence import patrimoine_xray

    return _memo("pat", lambda: patrimoine_xray.charger_vue() or {})


def _us() -> dict:
    from atelier.intelligence import testabilite_us

    return _memo("us", lambda: _sur(testabilite_us._us, {})[0] or {})


def _couverture(f: dict) -> tuple[dict | None, str]:
    from atelier.intelligence import couverture_exigences

    def calcul():
        c = couverture_exigences.calculer(f.get("version", ""), f.get("plateforme", ""))
        if not c["import"].get("date"):
            raise LookupError("périmètre des exigences jamais importé (Coverage › importer le périmètre Jira)")
        return c
    return _memo(f"couv:{f.get('version', '')}:{f.get('plateforme', '')}", lambda: _sur(calcul))


def _graphe():
    from atelier.discovery import connaissance

    return _memo("graphe", connaissance.construire, 60)


def _referentiel() -> list[dict]:
    from atelier.execution import centre

    return _memo("referentiel", lambda: _sur(centre.referentiel, [])[0] or [])


def _runs() -> list[dict]:
    from atelier.execution import historique

    return _memo("runs", lambda: _sur(lambda: historique.lister(200), [])[0] or [])


def _stabilite() -> tuple[dict | None, str]:
    from atelier.intelligence import gouvernance

    return _memo("stabilite", lambda: _sur(gouvernance.stabilite), 120)


def _module_exigence() -> dict:
    return {e["cle"]: e.get("module") or "" for e in _pat().get("exigences") or []}


def _cles_sprint(f: dict) -> set | None:
    """Clés des US du sprint filtré (None = pas de filtre)."""
    s = str(f.get("sprint") or "")
    return {k for k, u in _us().items() if s in (u.get("sprints") or {})} if s else None


def _exigences(f: dict) -> tuple[list[dict], str, str]:
    """Exigences du périmètre après filtres (module, sprint) : (lignes, date de la copie, raison si indisponible)."""
    c, raison = _couverture(f)
    if not c:
        return [], "", raison
    mod, sprint = _module_exigence(), _cles_sprint(f)
    l = [x for x in c["exigences"] if (not f.get("module") or mod.get(x["cle"]) == f["module"]) and (sprint is None or x["cle"] in sprint)]
    return l, _jour(c["import"].get("date")), ""


def _tests(f: dict) -> list[dict]:
    return [t for t in _pat().get("tests") or [] if not f.get("module") or t.get("module") == f["module"]]


def _publies() -> tuple[set, set]:
    """(clés Xray dont le script est publié, clés portées par un script non publié). Publié = revue « Published », ou
    script hors du circuit de revue (antérieur au circuit : il s'exécute déjà)."""
    pub, non = set(), set()
    for t in _referentiel():
        for c in ([t["cle_xray"]] if isinstance(t.get("cle_xray"), str) else t.get("cle_xray") or []):
            if c:
                (pub if t.get("revue") == "Published" or not t.get("en_workflow") else non).add(c)
    return pub, non - pub


def _classe(statut: str) -> str:
    """Statut de test run Xray → réussi | échec | bloqué | non exécuté | autre (bloqué n'est jamais un échec)."""
    s = (statut or "").upper().replace(" ", "")
    if "PASS" in s:
        return "reussi"
    if "BLOCK" in s or "ABORT" in s:
        return "bloque"
    if "FAIL" in s:
        return "echec"
    if not s or s in ("TODO", "EXECUTING"):
        return "en_cours" if s == "EXECUTING" else "non_execute"
    return "autre"


def _bugs() -> list[dict]:
    """Bugs liés aux test runs des exécutions Xray (copie locale), dédoublonnés, avec les exécutions qui les portent."""
    vus: dict = {}
    for e in _pat().get("executions") or []:
        for b in e.get("bugs") or []:
            x = vus.setdefault(b.get("cle"), {**b, "executions": [], "tests": set()})
            x["executions"].append(e.get("cle"))
            runs = e.get("runs") or {}
            # tests dont le test run porte ce bug ; copie plus ancienne (bug sans identifiant) : tests en échec de l'exécution
            x["tests"] |= ({t for t, r in runs.items() if str(b["id"]) in [str(d) for d in r.get("defauts") or []]} if b.get("id")
                           else {t for t, r in runs.items() if _classe(r.get("statut")) == "echec"})
    return [{**b, "tests": sorted(b["tests"])} for b in vus.values() if b.get("cle")]


def _etat_bug(b: dict) -> str:
    """Catégorie du bug d'après le mapping des statuts du projet ; statut non relié : « fermé » ou « ouvert » selon la
    catégorie « terminé » de Jira lue à l'import."""
    from atelier.domain import statuts

    return statuts.categorie("bug", b.get("statut", "")) or ("ferme" if b.get("ferme") else "ouvert")


def _bug_ouvert(b: dict) -> bool:
    return _etat_bug(b) in ("ouvert", "en_cours", "reouvert")


def _critique(b: dict) -> bool | None:
    p = str(b.get("priorite") or "").strip().casefold()
    return None if not p else p in CRITIQUES


def contexte() -> dict:
    """Valeurs proposées par les filtres du Dashboard, toutes tirées des copies locales."""
    us, pat = _us(), _pat()
    sprints: dict = {}
    for u in us.values():
        for sid, s in (u.get("sprints") or {}).items():
            sprints[sid] = {"id": sid, "nom": s.get("nom") or f"sprint {sid}", "etat": s.get("etat", ""), "espace": u.get("espace", "")}
    c, _ = _couverture({})
    personnes = {u.get("assigne") for u in us.values()} | {e.get("assigne") for e in pat.get("executions") or []} | {b.get("assigne") for b in _bugs()}
    return {"sprints": sorted(sprints.values(), key=lambda s: (s["etat"] != "active", -int(s["id"]) if str(s["id"]).isdigit() else 0)),
            "modules": sorted({t.get("module") for t in pat.get("tests") or [] if t.get("module")} | {m for m in _module_exigence().values() if m}),
            "versions": (c or {}).get("versions") or [], "plateformes": ["android", "ios", "web"],
            "responsables": sorted(p for p in personnes if p), "periode_jours": PERIODE_JOURS,
            "sources": {"xray": _jour((pat.get("date") or "")), "exigences": _jour(((c or {}).get("import") or {}).get("date")),
                        "us": len(us), "executions": len(pat.get("executions") or [])}}


# =========================================================================== zone 1 : synthèse
def _mesures(f: dict) -> dict:
    """Mesures de base, partagées par la synthèse, les alertes et l'état de préparation."""
    ex, date_ex, raison_ex = _exigences(f)
    tests = _tests(f)
    cles = {t["cle"] for t in tests}
    pub, non_pub = _publies()
    derniers = {t["cle"]: _classe((t.get("statut_xray") or {}).get("statut", "")) for t in tests}
    executes = [c for c, k in derniers.items() if k in ("reussi", "echec", "bloque")]
    bugs = [b for b in _bugs() if _etat_bug(b) != "rejete"]  # un bug rejeté n'est pas une anomalie de l'application
    ouverts = [b for b in bugs if _bug_ouvert(b)]
    crit = [b for b in ouverts if _critique(b)]
    stab, raison_stab = _stabilite()
    return {"exigences": ex, "date_exigences": date_ex, "raison_exigences": raison_ex, "tests": tests, "cles": cles,
            "publies": pub & cles, "non_publies": non_pub & cles, "derniers": derniers, "executes": executes,
            "reussis": [c for c in executes if derniers[c] == "reussi"], "echoues": [c for c in executes if derniers[c] == "echec"],
            "bloques": [c for c in executes if derniers[c] == "bloque"], "bugs": bugs, "bugs_ouverts": ouverts, "bugs_critiques": crit,
            "priorite_bugs_connue": any(_critique(b) is not None for b in ouverts) or not ouverts,
            "flaky": (stab or {}).get("flaky") if stab else None, "raison_flaky": raison_stab, "date_xray": _jour(_pat().get("date"))}


def synthese(f: dict | None = None) -> dict:
    f = f or {}
    m = _mesures(f)
    ex, n = m["exigences"], len(m["exigences"])
    couvertes = sum(x["existence"] for x in ex)
    t = tnr(f)
    src_x, src_e = "copie locale Xray", "périmètre Jira importé (Coverage)"
    indicateurs = [
        _ind("exigences", "Exigences du périmètre", n if not m["raison_exigences"] else None, "Exigences Jira du périmètre importé, hors exigences exclues de la stratégie.",
             "nombre d'exigences du périmètre", src_e, "#graphe/couverture", date_=m["date_exigences"], raison=m["raison_exigences"]),
        _ind("couvertes", "Exigences couvertes", couvertes if not m["raison_exigences"] else None, "Exigences reliées à au moins un test Xray (lien natif Jira / Xray). Couverte ne veut pas dire exécutée.",
             "exigences avec ≥ 1 test lié", src_e, "#graphe/couverture", date_=m["date_exigences"], raison=m["raison_exigences"]),
        _ind("taux_couverture", "Taux de couverture", _pct(couvertes, n) if not m["raison_exigences"] else None, "Part des exigences du périmètre reliées à au moins un test.",
             "exigences couvertes / exigences du périmètre", src_e, "#graphe/couverture", "%", m["date_exigences"], m["raison_exigences"] or "aucune exigence dans le périmètre"),
        _ind("tests", "Tests conçus", len(m["tests"]) if _pat() else None, "Tests présents dans Xray pour l'application.", "nombre de tests Xray", src_x, "#conception/cas",
             date_=m["date_xray"], raison="copie Xray absente (Paramètres › synchroniser le patrimoine)"),
        _ind("automatises", "Tests automatisés", len(m["publies"]) if _pat() else None,
             "Tests Xray portés par un script Robot publié (revue « Published », ou script antérieur au circuit de revue).",
             "tests Xray dont la clé est portée par un script publié", "dépôt Robot + revue des scripts", "#studio/revue", date_=m["date_xray"],
             raison="copie Xray absente", detail=f"{len(m['non_publies'])} autre(s) avec un script non publié" if m["non_publies"] else ""),
        _ind("taux_reussite", "Taux de réussite", _pct(len(m["reussis"]), len(m["executes"])),
             "Dernier résultat connu de chaque test exécuté. Les tests non exécutés ne sont pas comptés ; les bloqués comptent dans le dénominateur, pas comme échecs.",
             "tests réussis / tests ayant un dernier résultat (réussi, échoué, bloqué)", src_x, "#centre/vue", "%", m["date_xray"], "aucun test exécuté dans la copie Xray"),
        _ind("bugs_ouverts", "Bugs ouverts", len(m["bugs_ouverts"]) if _pat().get("executions") is not None and _pat() else None,
             "Bugs liés à un test run d'une exécution Xray et non terminés dans Jira. Un bug sans lien avec un test run n'est pas vu.",
             "bugs liés aux test runs, statut Jira non terminé", "exécutions Xray + Jira", "#centre/vue", date_=m["date_xray"], raison="exécutions Xray non importées"),
        _ind("bugs_critiques", "Bugs critiques", len(m["bugs_critiques"]) if m["priorite_bugs_connue"] and _pat() else None,
             "Bugs ouverts dont la priorité Jira est élevée (" + ", ".join(CRITIQUES[:6]) + "…).", "bugs ouverts de priorité élevée", "exécutions Xray + Jira",
             "#centre/vue", date_=m["date_xray"], raison="priorité des bugs non lue : réimporter les exécutions Xray" if _pat() else "copie Xray absente"),
        _ind("instables", "Tests instables", len(m["flaky"]) if m["flaky"] is not None else None,
             "Tests dont le résultat alterne d'un run à l'autre (critères de stabilité de Quality Governance).", "tests classés « Potentially flaky »",
             "runs de l'atelier", "#gouvernance", raison=m["raison_flaky"] or "aucun run de l'atelier"),
        _ind("tnr", "TNR à exécuter", t["indicateurs"]["impactes_non_executes"],
             "Tests recommandés après les évolutions détectées, pas encore exécutés depuis ces évolutions.", "tests recommandés non rejetés et non exécutés depuis l'évolution",
             "analyse d'impact (Knowledge Graph)", "#dashboard/tnr", detail=f"{t['indicateurs']['recommandes']} recommandé(s)"),
    ]
    precedent = _precedent()
    for i in indicateurs:
        v0 = (precedent or {}).get("valeurs", {}).get(i["id"])
        i["precedent"] = v0
        i["evolution"] = round(i["valeur"] - v0, 1) if isinstance(i["valeur"], (int, float)) and isinstance(v0, (int, float)) else None
    if not any(f.get(k) for k in ("sprint", "module", "version", "plateforme")):
        _instantane({i["id"]: i["valeur"] for i in indicateurs})
    return {"indicateurs": indicateurs, "compare_a": (precedent or {}).get("date", ""), "filtres": f}


def _historique() -> list[dict]:
    f = _dossier() / "historique.jsonl"
    return [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()] if f.exists() else []


def _precedent() -> dict | None:
    """Dernier instantané d'un jour antérieur : la base de comparaison des indicateurs."""
    return next((h for h in reversed(_historique()) if h["date"] < date.today().isoformat()), None)


def _instantane(valeurs: dict):
    """Un instantané par jour (le dernier calcul du jour remplace le précédent) : sert à dire « +3 depuis le … »."""
    h = [x for x in _historique() if x["date"] != date.today().isoformat()] + [{"date": date.today().isoformat(), "valeurs": valeurs}]
    f = _dossier() / "historique.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in h[-400:]), "utf-8")


# =========================================================================== zone 2 : conception et Discovery
def conception(f: dict | None = None) -> dict:
    f = f or {}
    ex, date_ex, raison = _exigences(f)
    n, src = len(ex), "périmètre Jira importé (Coverage)"
    k = lambda id_, lib, v, d, form, lien="#graphe/couverture", **kw: _ind(id_, lib, None if raison else v, d, form, src, lien, date_=date_ex, raison=raison, **kw)  # noqa: E731
    cles = lambda cond: [x["cle"] for x in ex if cond(x)]  # noqa: E731
    couverture = {"indicateurs": [
        k("total", "Exigences Jira", n, "Exigences du périmètre.", "nombre"),
        k("reliees", "Reliées à au moins un test", sum(x["existence"] for x in ex), "Lien natif Jira / Xray vers un test.", "exigences avec ≥ 1 test"),
        k("sans_test", "Sans test associé", sum(not x["existence"] for x in ex), "Aucun test lié : à concevoir.", "exigences sans test", "#conception/us"),
        k("partielles", "Partiellement couvertes", sum(x["etat"] == "partielle" for x in ex), "Au moins un critère d'acceptation sans test.", "exigences dont un critère n'a pas de test"),
        k("executees", "Exécutées", sum(x["execution"] for x in ex), "Tous les tests liés ont un résultat. Exécutée ne veut pas dire validée.", "exigences dont tous les tests ont été exécutés"),
        k("validees", "Résultat positif", sum(x["resultat"] for x in ex), "Tous les tests liés sont réussis à leur dernière exécution.", "exigences dont tous les tests sont réussis"),
        k("automatisees", "Couvertes par un test automatisé", sum(x["automatisee"] for x in ex), "Au moins un test lié est porté par un script Robot.", "exigences avec ≥ 1 test automatisé"),
        k("manuelles", "Couvertes par des tests manuels seulement", sum(x["manuelle_seulement"] for x in ex), "Des tests existent, aucun n'est automatisé.", "exigences couvertes sans test automatisé", "#studio"),
    ], "sans_test": cles(lambda x: not x["existence"])[:60], "en_echec": cles(lambda x: x["echec"])[:60]}

    # Discovery : ce qui est observé, proposé, validé — et le rapprochement avec Jira
    from atelier.discovery import correlation, intelligence_app

    vue, r1 = _memo("ia_vue", lambda: _sur(intelligence_app.vue_ensemble))
    noeuds, _ = _memo("ia_noeuds", lambda: _sur(lambda: intelligence_app.noeuds(["module", "fonctionnalite", "ecran", "parcours", "regle"]), []))
    corr, r2 = _memo("correlation", lambda: _sur(correlation.synthese), 90)
    fo, te = (vue or {}).get("fonctionnel") or {}, (vue or {}).get("technique") or {}
    d = lambda id_, lib, v, defi, lien="#discovery/resultats", raison_="": _ind(id_, lib, v, defi, "nombre", "carte de l'application + Knowledge Graph", lien, raison=raison_ or r1)  # noqa: E731
    ecrans = (corr or {}).get("ecrans") or []
    # « realisees » et « verifiees » sont des nombres dans la synthèse : les clés sont dans « cles_… »
    avec_ecran = {c for e in ecrans for c in (e.get("cles_realisees") or []) + (e.get("cles_verifiees") or [])}
    par_etat: dict = {}
    for nd in noeuds or []:
        etat = ("validé par un utilisateur" if nd["provenance"] == "déclaré" and nd["statut"] == "validé" else "en attente de validation" if nd["statut"] != "validé"
                else "proposé par l'IA, validé" if nd["provenance"] == "déduit" else "découvert (observé)")
        par_etat.setdefault(nd["type"], {}).setdefault(etat, 0)
        par_etat[nd["type"]][etat] += 1
    discovery = {"indicateurs": [
        d("modules", "Modules fonctionnels", fo.get("modules") if vue else None, "Modules connus de la carte et de Jira."),
        d("fonctionnalites", "Fonctionnalités", fo.get("fonctionnalites") if vue else None, "Fonctionnalités du Knowledge Graph."),
        d("ecrans", "Écrans cartographiés", te.get("ecrans") if vue else None, "Écrans observés par Discovery.", "#intelligence/ecrans"),
        d("parcours", "Parcours identifiés", fo.get("parcours") if vue else None, "Parcours proposés ou déclarés."),
        d("regles", "Règles métier détectées", fo.get("regles") if vue else None, "Règles déduites des messages observés ou déclarées."),
        d("ecrans_sans_exigence", "Écrans sans exigence Jira", _nombre((corr or {}).get("sans_exigence")) if corr else None,
          "Écran observé qu'aucune exigence ne réalise ni ne vérifie : opportunité de documentation, ou périmètre à confirmer.", "#discovery/correlation", r2),
        d("ecrans_non_valides", "Écrans sans association fonctionnelle validée", sum(e.get("etat") != "réalisé" for e in ecrans) if corr else None,
          "Écran sans lien « réalisé par » confirmé par un humain (une preuve de test ne suffit pas).", "#discovery/correlation", r2),
        _ind("exigences_sans_ecran", "Exigences sans écran relié", None if raison or not corr else sum(x["cle"] not in avec_ecran for x in ex),
             "Exigence du périmètre reliée à aucun écran de la carte. Elle peut ne pas avoir été explorée : ce n'est pas la preuve qu'elle manque dans l'application.",
             "exigences du périmètre absentes des liens écran ↔ exigence", "corrélation exigences ↔ écrans", "#discovery/correlation", raison=raison or r2),
        d("a_valider", "Éléments en attente de validation", (vue or {}).get("tracabilite", {}).get("elements_a_valider") if vue else None,
          "Propositions de l'IA ou déductions non encore tranchées : elles ne comptent dans aucun indicateur officiel.", "#intelligence/a_valider"),
    ], "par_etat": par_etat}

    # qualité de la conception
    from atelier.generation import bdd, conception as conception_mod

    cv, r3 = _memo("conception_vue", lambda: _sur(conception_mod.vue_ensemble))
    kc = (cv or {}).get("kpi") or {}
    tests = _tests(f)
    scen = _sur(bdd.lister, [])[0] or []
    sans_jdd = 0
    for s in scen:
        m = _sur(lambda s=s: bdd.charger(s["cle"]))[0]
        sans_jdd += bool(m) and not m.get("jdd")
    manuels = [t for t in tests if t.get("etapes")]
    from atelier.intelligence import couverture as couverture_mod

    red = _memo("redondances", lambda: _sur(lambda: couverture_mod.redondances(_pat().get("tests") or []), [])[0] or [])
    q = lambda id_, lib, v, defi, form, source, lien="#conception/cas", raison_="": _ind(id_, lib, v, defi, form, source, lien, raison=raison_)  # noqa: E731
    qualite = {"indicateurs": [
        q("tests_xray", "Tests Xray", len(tests) if _pat() else None, "Tests de l'application dans Xray.", "nombre", "copie locale Xray", raison_="copie Xray absente"),
        q("bdd", "Scénarios BDD conçus", len(scen), "Scénarios du projet de tests.", "nombre", "bdd/ du projet", "#bdd"),
        q("en_revue", "Tests en revue", kc.get("a_revoir") if cv else None, "Cas de test en cours de relecture.", "cas « In Review » ou « Changes Requested »", "revue de conception", raison_=r3),
        q("approuves", "Tests approuvés", kc.get("approuves") if cv else None, "Cas de test approuvés.", "cas « Approved » ou « Ready for Automation »", "revue de conception", raison_=r3),
        q("sans_precondition", "Tests sans précondition", sum(not t.get("preconditions") for t in tests) if _pat() else None,
          "Tests Xray sans précondition liée. Tous n'en ont pas besoin : à lire comme une liste à vérifier.", "tests sans précondition Xray", "copie locale Xray", raison_="copie Xray absente"),
        q("sans_jdd", "Scénarios sans jeu de données", sans_jdd, "Scénarios BDD sans jeu de données associé. Non mesuré pour les tests Xray manuels.", "scénarios BDD sans JDD", "bdd/ du projet", "#bdd"),
        q("sans_resultat", "Tests sans résultat attendu", sum(any(not (e.get("resultat") or "").strip() for e in t["etapes"]) for t in manuels) if _pat() else None,
          "Tests manuels dont au moins une étape n'a pas de résultat attendu.", "tests manuels avec une étape sans résultat attendu", "copie locale Xray", raison_="copie Xray absente"),
        q("redondants", "Tests potentiellement redondants", len(red), "Paires de tests d'un même module au texte très proche : à juger, pas à supprimer d'office.",
          "paires de similarité ≥ 80 %", "copie locale Xray", "#gouvernance"),
    ]}
    return {"couverture": couverture, "discovery": discovery, "qualite": qualite, "sprints": sprints(f), "filtres": f}


def sprints(f: dict | None = None, combien: int = 4) -> dict:
    """Matrice de couverture par sprint, sur les US suivies dans Test Design. Le périmètre figé au début du sprint sert
    à dire ce qui a été ajouté en cours de route."""
    from atelier.intelligence import testabilite_us

    us, pub = _us(), _publies()[0]
    liste = contexte()["sprints"]
    if (f or {}).get("sprint"):
        liste = [s for s in liste if s["id"] == str(f["sprint"])]
    liste = sorted(liste, key=lambda s: int(s["id"]) if str(s["id"]).isdigit() else 0)[-combien:]
    derniers = {t["cle"]: _classe((t.get("statut_xray") or {}).get("statut", "")) for t in _pat().get("tests") or []}
    colonnes = []
    for s in liste:
        b, raison = _sur(lambda s=s: testabilite_us.bilan_sprint(s["espace"], s["id"]))
        if not b:
            colonnes.append({**s, "erreur": raison})
            continue
        tests = {t for k, u in us.items() if s["id"] in (u.get("sprints") or {}) for t in u.get("tests_lies") or []}
        colonnes.append({**s, "exigences": b["us"], "couvertes": b["couvertes"], "non_couvertes": len(b["non_couvertes"]), "taux_couverture": b["taux_couverture"],
                         "tests_concus": len(tests), "tests_automatises": len(tests & pub),
                         "tests_executes": sum(derniers.get(t) in ("reussi", "echec", "bloque") for t in tests),
                         "ajoutees_en_cours": len(b["ajoutees"]) if b["fige"] else None, "perimetre_fige": bool(b["fige"]), "liste_non_couvertes": b["non_couvertes"][:40]})
    return {"sprints": colonnes, "lignes": [["exigences", "Exigences du périmètre"], ["couvertes", "Exigences couvertes"], ["non_couvertes", "Exigences non couvertes"],
                                            ["tests_concus", "Tests conçus"], ["tests_automatises", "Tests automatisés"], ["tests_executes", "Tests exécutés"],
                                            ["ajoutees_en_cours", "Ajoutées en cours de sprint"]],
            "non_mesure": ["Bugs identifiés par sprint : le sprint des bugs n'est pas lu dans Jira.",
                           "« Ajoutées en cours de sprint » demande d'avoir figé le périmètre du sprint (Test Design › US)."],
            "definition": "US suivies dans Test Design, par sprint Jira. Couverte = US au statut « Couverte ». Tests = tests Xray liés à ces US."}


# =========================================================================== zone 3 : exécution et qualité
def execution(f: dict | None = None) -> dict:
    f = f or {}
    m, depuis = _mesures(f), _depuis(f)
    d = m["derniers"]
    non_exec = [c for c, k in d.items() if k == "non_execute"]
    en_cours = [c for c, k in d.items() if k == "en_cours"]
    runs = [r for r in _runs() if not r.get("dry_run") and r.get("passes") is not None and _jour(r.get("debut")) >= depuis]
    passes, echecs = sum(r.get("passes") or 0 for r in runs), sum(r.get("echecs") or 0 for r in runs)
    apres_retry = sum(len(r.get("instables") or []) for r in runs)
    relances = sum((r.get("tentatives") or 1) > 1 for r in runs)
    durees = []
    for r in runs:
        try:
            durees.append((datetime.fromisoformat(r["fin"]) - datetime.fromisoformat(r["debut"])).total_seconds())
        except (KeyError, TypeError, ValueError):
            continue
    sx, sa = "copie locale Xray (dernier résultat de chaque test)", f"runs de l'atelier depuis le {depuis}"
    x = lambda id_, lib, v, defi, form, src=sx, lien="#centre/vue", unite="", raison="": _ind(id_, lib, v, defi, form, src, lien, unite, m["date_xray"] if src == sx else "", raison)  # noqa: E731
    vide_x = None if not _pat() else 0
    activite = {"indicateurs": [
        x("executes", "Tests exécutés", len(m["executes"]) if _pat() else vide_x, "Tests ayant un dernier résultat exploitable.", "réussis + échoués + bloqués", raison="copie Xray absente"),
        x("reussis", "Réussis", len(m["reussis"]) if _pat() else vide_x, "Dernier résultat réussi.", "tests au statut PASSED", raison="copie Xray absente"),
        x("echoues", "Échoués", len(m["echoues"]) if _pat() else vide_x, "Dernier résultat en échec. Les bloqués n'y sont pas.", "tests au statut FAILED", raison="copie Xray absente"),
        x("bloques", "Bloqués", len(m["bloques"]) if _pat() else vide_x, "Test qui n'a pas pu aller au bout (BLOCKED, ABORTED). Ni réussi, ni échoué.", "tests bloqués ou interrompus", raison="copie Xray absente"),
        x("non_executes", "Non exécutés", len(non_exec) if _pat() else vide_x, "Tests jamais exécutés ou remis à faire. Jamais comptés comme échecs.", "tests sans résultat (TO DO)", raison="copie Xray absente"),
        x("en_cours", "En cours", len(en_cours) if _pat() else vide_x, "Tests en cours d'exécution.", "tests au statut EXECUTING", raison="copie Xray absente"),
        x("relances", "Runs relancés", relances, "Runs de l'atelier ayant eu une seconde tentative.", "runs avec plus d'une tentative", sa, "#execution"),
        x("apres_retry", "Réussis après relance", apres_retry, "Tests passés seulement à la seconde tentative : comptés à part du premier passage.", "tests réussis à la tentative 2", sa, "#execution"),
        x("duree", "Durée moyenne d'un run", round(sum(durees) / len(durees) / 60, 1) if durees else None, "Durée moyenne des runs de l'atelier.", "moyenne (fin − début)", sa, "#execution", "min",
          "aucun run de l'atelier sur la période"),
    ], "repartition": {"réussis": len(m["reussis"]), "échoués": len(m["echoues"]), "bloqués": len(m["bloques"]), "non exécutés": len(non_exec), "en cours": len(en_cours)}}
    nex = len(m["executes"])
    taux = {"indicateurs": [
        x("premier_passage", "Réussite au premier passage", _pct(passes - apres_retry, passes + echecs), "Tests réussis sans relance, sur les runs de l'atelier.",
          "(réussis − réussis après relance) / tests exécutés", sa, "#execution", "%", "aucun run de l'atelier sur la période"),
        x("final", "Réussite finale", _pct(len(m["reussis"]), nex), "Dernier résultat de chaque test exécuté.", "tests réussis / tests ayant un résultat final", unite="%", raison="aucun test exécuté"),
        x("echec", "Taux d'échec", _pct(len(m["echoues"]), nex), "Tests dont le dernier résultat est un échec.", "tests échoués / tests exécutés", unite="%", raison="aucun test exécuté"),
        x("blocage", "Taux de blocage", _pct(len(m["bloques"]), nex), "Tests bloqués ou interrompus.", "tests bloqués / tests exécutés", unite="%", raison="aucun test exécuté"),
    ]}

    bugs, ouverts = m["bugs"], m["bugs_ouverts"]
    mod_test = {t["cle"]: t.get("module") or "sans module" for t in _pat().get("tests") or []}
    par_module: dict = {}
    for b in ouverts:
        for mo in {mod_test.get(t, "sans module") for t in b["tests"]} or {"sans module"}:
            par_module[mo] = par_module.get(mo, 0) + 1
    delais = []
    for b in bugs:
        try:
            delais.append((datetime.fromisoformat(str(b["resolu"])[:19]) - datetime.fromisoformat(str(b["cree"])[:19])).total_seconds() / 86400)
        except (KeyError, TypeError, ValueError):
            continue
    sb = "bugs liés aux test runs des exécutions Xray (copie locale) + Jira"
    b_ = lambda id_, lib, v, defi, form, raison="": _ind(id_, lib, v, defi, form, sb, "#centre/vue", date_=m["date_xray"], raison=raison)  # noqa: E731
    lu = _pat().get("executions") is not None and bool(_pat())
    from atelier.domain import statuts as statuts_projet

    mapping_bugs = bool(statuts_projet.mapping()["correspondances"]["bug"])
    anomalies = {"indicateurs": [
        b_("total", "Bugs identifiés", len(bugs) if lu else None, "Bugs liés à un test run. Un bug saisi dans Jira sans lien avec un test run n'est pas vu.", "bugs distincts liés aux test runs", "exécutions Xray non importées"),
        b_("ouverts", "Ouverts", len(ouverts) if lu else None, "Statut Jira non terminé.", "bugs non terminés", "exécutions Xray non importées"),
        b_("resolus", "Résolus", len(bugs) - len(ouverts) if lu else None, "Statut Jira terminé.", "bugs terminés", "exécutions Xray non importées"),
        b_("reouverts", "Réouverts", sum(_etat_bug(b) == "reouvert" for b in bugs) if lu and mapping_bugs else None,
           "Bugs dont le statut actuel est relié à « Réouvert » dans le mapping du projet.", "bugs au statut réouvert",
           "relier les statuts des bugs (Paramètres › Statuts des tickets)" if lu else "exécutions Xray non importées"),
        b_("rejetes", "Rejetés (non comptés)", len(_bugs()) - len(bugs) if lu and mapping_bugs else None,
           "Bugs au statut relié à « Rejeté » : écartés de tous les comptes d'anomalies.", "bugs au statut rejeté",
           "relier les statuts des bugs (Paramètres › Statuts des tickets)" if lu else "exécutions Xray non importées"),
        b_("critiques", "Critiques ouverts", len(m["bugs_critiques"]) if m["priorite_bugs_connue"] and lu else None, "Priorité Jira élevée.", "bugs ouverts de priorité élevée",
           "priorité non lue : réimporter les exécutions Xray"),
        b_("non_affectes", "Ouverts sans responsable", sum(not b.get("assigne") for b in ouverts) if any("assigne" in b for b in bugs) or not bugs else None,
           "Bugs ouverts sans personne assignée dans Jira.", "bugs ouverts sans responsable", "responsable non lu : réimporter les exécutions Xray"),
        b_("resolution", "Temps moyen de résolution (jours)", round(sum(delais) / len(delais), 1) if delais else None, "Du jour de création à la résolution dans Jira.",
           "moyenne (résolution − création)", "dates non lues, ou aucun bug résolu"),
        b_("tests_associes", "Tests associés aux bugs ouverts", len({t for b in ouverts for t in b["tests"]}) if lu else None, "Tests en échec dans les exécutions qui portent ces bugs.",
           "tests en échec des exécutions portant un bug ouvert", "exécutions Xray non importées"),
    ], "par_module": sorted(par_module.items(), key=lambda kv: -kv[1]),
        "ouverts": [{k: b.get(k) for k in ("cle", "resume", "statut", "priorite", "assigne", "executions", "tests")} for b in ouverts[:40]],
        "non_mesure": [("Bugs récurrents et bugs par sprint ou par version : non lus dans Jira." if mapping_bugs else
                        "Bugs réouverts : relier les statuts des bugs dans Paramètres › Statuts des tickets. Bugs récurrents, par sprint ou par version : non lus dans Jira."),
                       "Bugs détectés par des tests manuels ou automatisés : l'origine du test run n'est pas rapprochée du bug."]}
    return {"activite": activite, "taux": taux, "anomalies": anomalies, "responsables": responsables(f), "filtres": f, "depuis": depuis}


def responsables(f: dict | None = None) -> dict:
    """Charge par personne assignée (noms lus dans Jira / Xray). Personne ne reçoit une tâche ici : la vue montre où
    le travail s'accumule et ce qui n'a pas de responsable."""
    from atelier.intelligence import strategie

    sprint, lignes = _cles_sprint(f or {}), {}

    def l(nom):
        return lignes.setdefault(nom or "Sans responsable", {"responsable": nom or "Sans responsable", "us_a_couvrir": 0, "cas_a_valider": 0,
                                                             "executions_ouvertes": 0, "bugs_ouverts": 0, "en_retard": 0, "elements": []})
    for k, u in _us().items():
        if sprint is not None and k not in sprint:
            continue
        if not str(u.get("statut", "")).startswith("Couverte") and u.get("statut") != "Non testable":
            l(u.get("assigne"))["us_a_couvrir"] += 1
            l(u.get("assigne"))["elements"].append(k)
        l(u.get("assigne"))["cas_a_valider"] += sum(c.get("statut") == "Proposé" for c in u.get("cas") or [])
    from atelier.domain import statuts as statuts_projet

    for e in _pat().get("executions") or []:
        fermee = statuts_projet.ferme("execution", e.get("statut", ""))  # mapping du projet ; statut non relié : date de résolution Jira
        if not (bool(e.get("resolu")) if fermee is None else fermee) and any(_classe(r.get("statut")) in ("non_execute", "en_cours") for r in (e.get("runs") or {}).values()):
            l(e.get("assigne"))["executions_ouvertes"] += 1
            l(e.get("assigne"))["elements"].append(e.get("cle"))
    for b in _bugs():
        if _bug_ouvert(b):
            l(b.get("assigne"))["bugs_ouverts"] += 1
            l(b.get("assigne"))["elements"].append(b.get("cle"))
    etat, _ = _memo("strategie", lambda: _sur(strategie.etat), 120)
    for o in (((etat or {}).get("synthese") or {}).get("objectifs") or {}).get("liste") or []:
        if o.get("echeance") and str(o["echeance"])[:10] < date.today().isoformat() and o.get("etat") != "atteint":
            l(o.get("responsable"))["en_retard"] += 1
    out = list(lignes.values())
    for x in out:
        x["charge"] = x["us_a_couvrir"] + x["cas_a_valider"] + x["executions_ouvertes"] + x["bugs_ouverts"]
        x["elements"] = x["elements"][:30]
    nommes = [x["charge"] for x in out if x["responsable"] != "Sans responsable"]
    moyenne = sum(nommes) / len(nommes) if nommes else 0
    for x in out:
        x["surcharge"] = x["responsable"] != "Sans responsable" and x["charge"] >= 5 and x["charge"] > 1.5 * moyenne
    if (f or {}).get("responsable"):
        out = [x for x in out if x["responsable"] == f["responsable"]]
    return {"lignes": sorted(out, key=lambda x: (x["responsable"] == "Sans responsable", -x["charge"])),
            "colonnes": [["us_a_couvrir", "US à couvrir"], ["cas_a_valider", "Cas à valider"], ["executions_ouvertes", "Exécutions ouvertes"],
                         ["bugs_ouverts", "Bugs ouverts"], ["en_retard", "Actions en retard"]],
            "definition": "US à couvrir : US assignées, ni couvertes ni non testables. Cas à valider : cas proposés sur ses US. Exécutions ouvertes : Test Executions "
                          "Xray assignées avec des tests restant à exécuter. Actions en retard : objectifs de la stratégie dont l'échéance est passée.",
            "non_mesure": ["Tests à automatiser et tests en revue par personne : Xray ne porte pas de responsable par test dans la copie locale."]}


# =========================================================================== zone 4 : intelligence de non-régression
def _fichiers_modifies(depuis: str) -> list[dict]:
    """Fichiers d'automatisation (.robot, .resource) modifiés dans le dépôt local depuis la date (git log, sans réseau)."""
    try:
        r = subprocess.run(["git", "log", f"--since={depuis}", "--name-only", "--pretty=format:@%ad|%an", "--date=short", "--", "*.robot", "*.resource"],
                           cwd=str(projet.PROJECT_DIR), capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return []
    out, entete = {}, ("", "")
    for ligne in r.stdout.splitlines() if r.returncode == 0 else []:
        if ligne.startswith("@"):
            entete = tuple(ligne[1:].split("|", 1))
        elif ligne.strip():
            out.setdefault(ligne.strip(), {"fichier": ligne.strip(), "date": entete[0], "auteur": entete[1] if len(entete) > 1 else ""})
    return list(out.values())


def evolutions(f: dict | None = None) -> list[dict]:
    """Évolutions détectées depuis la date, chacune rattachée à un élément du Knowledge Graph quand c'est possible."""
    from atelier.discovery import intelligence_app

    depuis, out = _depuis(f or {}), []
    g = _graphe()

    def noeud(*candidats):
        return next((c for c in candidats if c in g.noeuds), "")

    def trouver_us(cle):
        return noeud(f"user_story:{cle}", f"epic:{cle}", f"bug:{cle}") or next((i for i, nd in g.noeuds.items() if nd.proprietes.get("cle") == cle), "")
    for k, u in _us().items():
        for a in u.get("alertes") or []:
            if "modifiée" in str(a.get("message", "")) and _jour(a.get("date")) >= depuis:
                out.append({"id": f"us:{k}", "nature": "Exigence modifiée dans Jira", "element": k, "detail": u.get("resume", ""), "date": _jour(a.get("date")),
                            "source": "Jira (Test Design)", "noeud": trouver_us(k), "tests_directs": list(u.get("tests_lies") or [])})
    c, _ = _couverture({})
    if c:
        from atelier.intelligence import couverture_exigences

        synchros = (_sur(couverture_exigences.evolution, {})[0] or {}).get("synchros") or []
        for s in [s for s in synchros[1:] if _jour(s.get("date")) >= depuis][-3:]:  # la première synchronisation est l'import initial, pas une évolution
            for k in (s.get("ajoutees") or [])[:30] if isinstance(s.get("ajoutees"), list) else []:
                out.append({"id": f"ajout:{k}", "nature": "Exigence ajoutée au périmètre", "element": k, "detail": "", "date": _jour(s.get("date")),
                            "source": "Jira (périmètre)", "noeud": trouver_us(k), "tests_directs": []})
    for ch in _sur(intelligence_app.changements, [])[0] or []:
        if ch["nature"].startswith("Écran"):
            out.append({"id": f"ecran:{ch['element']}", "nature": "Écran modifié (Discovery)", "element": ch["element"], "detail": "écran à revoir dans la carte",
                        "date": "", "source": "Application Discovery", "noeud": noeud(f"ecran:{ch['element']}"), "tests_directs": []})
        elif ch["nature"].startswith("Locator"):
            loc = next((i for i in g.noeuds if i.startswith(f"locator:{ch['element']}@")), "")
            out.append({"id": f"locator:{ch['element']}", "nature": ch["nature"].replace("Obsolete", "obsolète").replace("Missing", "manquant"), "element": ch["element"],
                        "detail": ch["impact"], "date": "", "source": "Automation Studio", "noeud": loc, "tests_directs": []})
    for fm in _fichiers_modifies(depuis):
        nid = noeud(f"resource:{fm['fichier']}", f"suite:{fm['fichier']}")
        out.append({"id": f"fichier:{fm['fichier']}", "nature": "Fichier d'automatisation modifié", "element": fm["fichier"], "detail": fm["auteur"], "date": fm["date"],
                    "source": "dépôt Git local", "noeud": nid, "tests_directs": [t for r in _referentiel() if r.get("fichier") == fm["fichier"]
                                                                              for t in ([r["cle_xray"]] if isinstance(r.get("cle_xray"), str) else r.get("cle_xray") or []) if t]})
    for b in _bugs():
        if _etat_bug(b) in ("resolu", "ferme") and _jour(b.get("resolu")) >= depuis:
            out.append({"id": f"bug:{b['cle']}", "nature": "Bug corrigé", "element": b["cle"], "detail": b.get("resume", ""), "date": _jour(b.get("resolu")),
                        "source": "Jira (bugs des exécutions)", "noeud": trouver_us(b["cle"]), "tests_directs": list(b["tests"])})
    from atelier.intelligence import releases

    # Release Notes validées par le QA : leurs évolutions entrent dans la même analyse d'impact (un élément disparu du
    # graphe depuis le rattachement redevient « hors graphe », jamais un impact inventé)
    for e in _sur(lambda: releases.evolutions_tnr(depuis), [])[0] or []:
        out.append({**e, "noeud": e["noeud"] if e["noeud"] in g.noeuds else ""})
    vus, propres = set(), []
    for e in out:
        if e["id"] not in vus:
            vus.add(e["id"])
            propres.append(e)
    return propres


def _decisions() -> dict:
    f = _dossier() / "tnr_decisions.json"
    return json.loads(f.read_text("utf-8")) if f.exists() else {}


def tnr(f: dict | None = None) -> dict:
    """Tests à rejouer après les évolutions : obligatoires (directement touchés), complémentaires (même module que
    l'élément touché), sécurité fonctionnelle (criticité métier). Chaque test dit pourquoi il est là."""
    from atelier.discovery import connaissance

    f = f or {}
    evo, g, pat = evolutions(f), _graphe(), _pat()
    info = {t["cle"]: t for t in pat.get("tests") or []}
    pub = _publies()[0]
    reco: dict = {}

    def ajouter(cle, categorie, motif, date_evo=""):
        if cle not in info and not cle:
            return
        r = reco.setdefault(cle, {"test": cle, "categorie": categorie, "motifs": [], "depuis": ""})
        ordre = {"obligatoire": 0, "complementaire": 1, "securite": 2}
        if ordre[categorie] < ordre[r["categorie"]]:
            r["categorie"] = categorie
        if motif not in r["motifs"]:
            r["motifs"].append(motif)
        r["depuis"] = max(r["depuis"], date_evo or "")
    non_rattachees, cand_comp, cand_secu = [], {}, {}
    for e in evo:
        directs, modules = set(e["tests_directs"]), set()
        if e["noeud"]:
            imp = _sur(lambda e=e: connaissance.analyser_impact(g, e["noeud"]))[0] or {}
            directs |= set((imp.get("tnr") or {}).get("include_tags") or []) | {t["id"].split(":", 1)[1] for t in imp.get("tests_xray") or []}
            modules = set(imp.get("modules") or [])
            if g.noeuds[e["noeud"]].type in ("user_story", "epic", "bug"):  # tests qui vérifient l'exigence
                directs |= {r.vers.split(":", 1)[1] for r in g.sortants(e["noeud"], fiables=True) if r.type == "teste_par" and r.vers.startswith("test:")}
        e["tests"] = sorted(directs)
        if not directs and not e["noeud"]:
            non_rattachees.append(e["id"])
        for t in directs:
            ajouter(t, "obligatoire", f"{e['nature']} : {e['element']}", e["date"])
        for t in pat.get("tests") or []:
            if t.get("module") in modules and t["cle"] not in directs:
                cand_comp.setdefault(t["cle"], (f"même module ({t['module']}) que {e['element']}", e["date"]))
    if evo:  # sans évolution, rien n'est à rejouer : la sécurité fonctionnelle accompagne une campagne, elle ne la déclenche pas
        for t in pat.get("tests") or []:
            if f.get("module") and t.get("module") != f["module"]:
                continue
            crit = str(t.get("criticite") or "").casefold() in CRITIQUES
            etiq = next((x for x in t.get("libelles") or [] if str(x).casefold() in ETIQUETTES_SECURITE), "")
            if (crit or etiq) and t["cle"] not in reco:
                cand_secu.setdefault(t["cle"], (f"criticité métier ({t['criticite']})" if crit else f"étiquette « {etiq} »", ""))
    dec = _decisions()
    # mêmes bornes que le périmètre d'un build : complémentaires et sécurité classés par risque, plafonnés, le reste dit
    from atelier.intelligence import builds as _bld

    bornes, non_retenus = _bld._bornes(), {}
    for cands, cat, cle_borne in ((cand_comp, "complementaire", "max_indirects"), (cand_secu, "securite", "max_qualification")):
        restants = {k: v for k, v in cands.items() if k not in reco and (dec.get(k) or {}).get("decision") != "ajoutée"}
        classes = sorted(restants, key=lambda k: (-_bld._risque(info.get(k) or {}, sys.modules[__name__]), k))
        garder = classes[:bornes[cle_borne]] if bornes[cle_borne] > 0 else classes
        for k in garder:
            ajouter(k, cat, *restants[k])
        if len(classes) > len(garder):
            non_retenus[cat] = classes[len(garder):]
    for cle, d in dec.items():
        if d.get("decision") == "ajoutée" and cle not in reco:
            ajouter(cle, "obligatoire", f"ajouté par {d.get('par', '?')} : {d.get('motif', '')}".strip(" :"))
    priorites = {"obligatoire": "Très élevée", "complementaire": "Élevée", "securite": "Moyenne"}
    lignes = []
    for cle, r in reco.items():
        t = info.get(cle) or {}
        if f.get("module") and t.get("module") != f["module"]:
            continue
        sx = t.get("statut_xray") or {}
        classe = _classe(sx.get("statut", ""))
        rejoue = classe in ("reussi", "echec", "bloque") and bool(r["depuis"]) and _jour(sx.get("fin")) >= r["depuis"]
        if not r["depuis"]:  # évolution sans date (écran, locator) ou sécurité : rejoué s'il a un résultat sur la période
            rejoue = classe in ("reussi", "echec", "bloque") and _jour(sx.get("fin")) >= _depuis(f)
        d = dec.get(cle) or {}
        lignes.append({**r, "resume": t.get("resume", ""), "module": t.get("module", ""), "connu": cle in info, "automatise": cle in pub,
                       "priorite": d.get("priorite") or priorites[r["categorie"]], "dernier_statut": sx.get("statut", ""), "rejoue": rejoue,
                       "resultat": classe if rejoue else "", "decision": d.get("decision", ""), "decision_par": d.get("par", ""), "decision_motif": d.get("motif", "")})
    ordre = {"obligatoire": 0, "complementaire": 1, "securite": 2}
    lignes.sort(key=lambda x: (ordre[x["categorie"]], x["rejoue"], x["test"]))
    retenus = [x for x in lignes if x["decision"] != "rejetée"]
    impactes = [x for x in retenus if x["categorie"] != "securite"]
    ind = {"recommandes": len(lignes), "obligatoires": sum(x["categorie"] == "obligatoire" for x in lignes),
           "complementaires": sum(x["categorie"] == "complementaire" for x in lignes), "securite": sum(x["categorie"] == "securite" for x in lignes),
           "selectionnes": sum(x["decision"] in ("acceptée", "ajoutée") for x in lignes), "acceptes": sum(x["decision"] == "acceptée" for x in lignes),
           "rejetes": sum(x["decision"] == "rejetée" for x in lignes), "executes": sum(x["rejoue"] for x in retenus),
           "reussis": sum(x["resultat"] == "reussi" for x in retenus), "echoues": sum(x["resultat"] == "echec" for x in retenus),
           "impactes_non_executes": sum(not x["rejoue"] for x in impactes),
           "obligatoires_non_executes": sum(not x["rejoue"] for x in retenus if x["categorie"] == "obligatoire"),
           "couverture_impacts": _pct(sum(x["rejoue"] for x in impactes), len(impactes))}
    return {"evolutions": evo, "recommandations": lignes, "indicateurs": ind, "depuis": _depuis(f), "non_rattachees": non_rattachees,
            "non_retenus": {c: {"nombre": len(l), "tests": l[:200]} for c, l in non_retenus.items()}, "bornes": bornes,
            "avertissement": (f"{len(non_rattachees)} évolution(s) sans élément correspondant dans le Knowledge Graph : leur impact n'a pas pu être analysé. "
                              "Cette sélection est donc partielle." if non_rattachees else ""),
            "non_detecte": ["Merge requests et commits distants GitLab (appel réseau : hors du chargement du Dashboard).",
                            "Changements d'API et de règles métier : pas de comparaison de versions disponible."],
            "definition": "Obligatoire : test directement lié à l'élément modifié (relations fiables du graphe). Complémentaire : autre test du même module. "
                          "Sécurité fonctionnelle : test de criticité élevée ou étiqueté smoke / tnr, sans lien avec une évolution. "
                          "Complémentaires et sécurité : les plus à risque d'abord (criticité, dernier échec, étiquette), dans la limite des plafonds "
                          "réglés (Paramètres › Pilotage IA) ; les autres sont comptés comme non retenus."}


def decider_tnr(test: str, decision: str, motif: str = "", priorite: str = "") -> dict:
    """Décision du responsable QA sur une recommandation : acceptée, rejetée (justification obligatoire), ajoutée (test
    hors recommandation), ou « » pour revenir à l'état recommandé."""
    from atelier.domain import roles

    roles.exiger("construire")
    test = str(test or "").strip().upper()
    if decision not in ("acceptée", "rejetée", "ajoutée", ""):
        raise ValueError("Décision : acceptée, rejetée, ajoutée, ou vide pour l'annuler.")
    if not test:
        raise ValueError("Clé du test obligatoire.")
    if decision == "rejetée" and len(motif.strip()) < 5:
        raise ValueError("Justifier l'exclusion (5 caractères au moins) : elle est gardée avec la sélection.")
    if decision == "ajoutée" and test not in {t["cle"] for t in _pat().get("tests") or []}:
        raise ValueError(f"{test} n'est pas un test connu de la copie Xray.")
    if priorite and priorite not in ("Très élevée", "Élevée", "Moyenne", "Basse"):
        raise ValueError("Priorité : Très élevée, Élevée, Moyenne ou Basse.")
    d = _decisions()
    if decision:
        d[test] = {"decision": decision, "motif": motif.strip()[:400], "priorite": priorite, "par": roles.utilisateur(), "date": datetime.now().isoformat(timespec="seconds")}
    else:
        d.pop(test, None)
    f = _dossier() / "tnr_decisions.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d, ensure_ascii=False, indent=1), "utf-8")
    vider_memo()
    return tnr()["indicateurs"]


def creer_campagne_tnr(nom: str, plateformes: list[str], environnement: str = "", inclure_obligatoires: bool = True) -> dict:
    """Envoie la sélection validée à Execution Center : campagne de type TNR avec les tests acceptés ou ajoutés (et les
    obligatoires non rejetés). Rien n'est lancé : la campagne s'exécute depuis Execution Center."""
    from atelier.execution import centre

    t = tnr()
    retenus = [x for x in t["recommandations"] if x["decision"] in ("acceptée", "ajoutée")
               or (inclure_obligatoires and x["categorie"] == "obligatoire" and x["decision"] != "rejetée")]
    autos = [x["test"] for x in retenus if x["automatise"]]
    if not autos:
        raise ValueError("Aucun test automatisé dans la sélection : accepter des tests, ou les automatiser d'abord.")
    avant = {c["id"] for c in centre.campagnes()}
    apres = centre.enregistrer_campagne({"nom": nom or f"TNR du {date.today().isoformat()}", "type": "TNR", "plateformes": plateformes, "environnement": environnement,
                                         "tests": autos, "description": f"Sélection issue de l'analyse d'impact ({len(t['evolutions'])} évolution(s) depuis le {t['depuis']})."
                                         + (f" {t['avertissement']}" if t["avertissement"] else "")})
    c = next(c for c in apres if c["id"] not in avant)
    return {"campagne": c["id"], "nom": c["nom"], "tests": len(autos), "non_automatises": sorted(x["test"] for x in retenus if not x["automatise"]),
            "partielle": bool(t["avertissement"]), "avertissement": t["avertissement"]}


# =========================================================================== zone 5 : aide à la décision
CRITERES_DEFAUT = [
    {"id": "couverture", "libelle": "Couverture des exigences", "comparateur": ">=", "seuil": 80, "unite": "%", "bloquant": False},
    {"id": "critiques_non_valides", "libelle": "Tests critiques sans résultat positif", "comparateur": "<=", "seuil": 0, "bloquant": True},
    {"id": "reussite", "libelle": "Taux de réussite final", "comparateur": ">=", "seuil": 95, "unite": "%", "bloquant": False},
    {"id": "bugs_critiques", "libelle": "Bugs critiques ouverts", "comparateur": "<=", "seuil": 0, "bloquant": True},
    {"id": "bugs_ouverts", "libelle": "Bugs ouverts", "comparateur": "<=", "seuil": 5, "bloquant": False},
    {"id": "tnr_obligatoires", "libelle": "TNR obligatoires non exécutés", "comparateur": "<=", "seuil": 0, "bloquant": True},
    {"id": "tnr_echecs", "libelle": "TNR en échec", "comparateur": "<=", "seuil": 0, "bloquant": True},
    {"id": "instables", "libelle": "Tests instables", "comparateur": "<=", "seuil": 3, "bloquant": False},
    {"id": "bloques", "libelle": "Tests bloqués", "comparateur": "<=", "seuil": 0, "bloquant": False},
]


def criteres() -> list[dict]:
    """Critères de l'état de préparation : ceux du projet (pilotage/criteres.yaml), sinon les valeurs par défaut."""
    f = _dossier() / "criteres.yaml"
    regles = {}
    try:
        regles = {c["id"]: c for c in (yaml.safe_load(f.read_text("utf-8")) or {}).get("criteres") or []} if f.exists() else {}
    except (OSError, yaml.YAMLError, KeyError, TypeError):
        regles = {}
    return [{**c, **{k: regles[c["id"]][k] for k in ("seuil", "bloquant") if k in regles.get(c["id"], {})}} for c in CRITERES_DEFAUT]


def regler_criteres(reglages: list[dict]) -> list[dict]:
    """Seuil et caractère bloquant de chaque critère, pour le projet (rôle relecteur : c'est une règle de livraison)."""
    from atelier.domain import roles

    roles.exiger("decider_revue")
    connus, propres = {c["id"] for c in CRITERES_DEFAUT}, []
    for r in reglages or []:
        if r.get("id") not in connus:
            raise ValueError(f"Critère inconnu : {r.get('id')}")
        try:
            seuil = float(r["seuil"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"Seuil numérique attendu pour {r.get('id')}.") from None
        propres.append({"id": r["id"], "seuil": seuil, "bloquant": bool(r.get("bloquant"))})
    f = _dossier() / "criteres.yaml"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(yaml.safe_dump({"criteres": propres}, allow_unicode=True, sort_keys=False), "utf-8")
    return criteres()


def preparation(f: dict | None = None) -> dict:
    """État de préparation de la livraison : PRÊT, PRÊT AVEC RÉSERVES, NON PRÊT ou DONNÉES INSUFFISANTES. Une bonne
    couverture ne compense jamais un critère bloquant. C'est une aide à la décision, pas une autorisation."""
    f = f or {}
    m, t = _mesures(f), tnr(f)["indicateurs"]
    ex = m["exigences"]
    critiques = [x for x in m["tests"] if str(x.get("criticite") or "").casefold() in CRITIQUES]
    valeurs = {"couverture": _pct(sum(x["existence"] for x in ex), len(ex)) if not m["raison_exigences"] else None,
               "critiques_non_valides": sum(m["derniers"].get(x["cle"]) != "reussi" for x in critiques) if m["tests"] else None,
               "reussite": _pct(len(m["reussis"]), len(m["executes"])), "bugs_critiques": len(m["bugs_critiques"]) if m["priorite_bugs_connue"] and _pat() else None,
               "bugs_ouverts": len(m["bugs_ouverts"]) if _pat() else None, "tnr_obligatoires": t["obligatoires_non_executes"], "tnr_echecs": t["echoues"],
               "instables": len(m["flaky"]) if m["flaky"] is not None else None, "bloques": len(m["bloques"]) if _pat() else None}
    lignes = []
    for c in criteres():
        v = valeurs.get(c["id"])
        ok = None if v is None else (v >= c["seuil"] if c["comparateur"] == ">=" else v <= c["seuil"])
        lignes.append({**c, "valeur": v, "respecte": ok})
    essentiels = [x for x in lignes if x["id"] in ("couverture", "reussite")]
    bloquants_ko = [x for x in lignes if x["bloquant"] and x["respecte"] is False]
    if any(x["valeur"] is None for x in essentiels):
        statut, raison = "DONNÉES INSUFFISANTES", "La couverture ou les résultats d'exécution ne sont pas mesurables : importer le périmètre et les exécutions."
    elif bloquants_ko:
        statut, raison = "NON PRÊT", "Critère(s) bloquant(s) non respecté(s) : " + ", ".join(x["libelle"] for x in bloquants_ko) + "."
    elif any(x["respecte"] is not True for x in lignes):
        ko = [x["libelle"] for x in lignes if x["respecte"] is False]
        inconnus = [x["libelle"] for x in lignes if x["respecte"] is None]
        statut = "PRÊT AVEC RÉSERVES"
        raison = " ".join(filter(None, [("Sous le seuil : " + ", ".join(ko) + ".") if ko else "", ("Non mesuré : " + ", ".join(inconnus) + ".") if inconnus else ""]))
    else:
        statut, raison = "PRÊT", "Tous les critères du projet sont respectés."
    return {"statut": statut, "raison": raison, "criteres": lignes,
            "avertissement": "Aide à la décision : ce statut ne vaut pas autorisation de mise en production. La criticité des exigences n'est pas lue dans Jira ; "
                             "« tests critiques » s'appuie sur la priorité des tests."}


def decision(f: dict | None = None) -> dict:
    """Alertes (chacune avec son action), recommandations (constat, preuves, priorité, action, nature de la preuve) et
    état de préparation."""
    f = f or {}
    m, t, c = _mesures(f), tnr(f), conception(f)
    ex = m["exigences"]
    sans_test = [x["cle"] for x in ex if not x["existence"]]
    alertes, recos = [], []

    def alerte(priorite, texte, action, lien, elements=()):
        alertes.append({"priorite": priorite, "texte": texte, "action": action, "lien": lien, "elements": list(elements)[:20]})

    def reco(question, constat, elements, preuves, priorite, impact, action, lien, confiance):
        recos.append({"question": question, "constat": constat, "elements": list(elements)[:15], "preuves": preuves, "priorite": priorite, "impact": impact,
                      "action": action, "lien": lien, "confiance": confiance})
    if m["bugs_critiques"]:
        alerte("haute", f"{len(m['bugs_critiques'])} bug(s) critique(s) ouvert(s).", "Consulter les bugs", "#centre/vue", [b["cle"] for b in m["bugs_critiques"]])
    if t["indicateurs"]["obligatoires_non_executes"]:
        alerte("haute", f"{t['indicateurs']['obligatoires_non_executes']} test(s) directement touché(s) par une évolution n'ont pas été rejoués.",
               "Préparer la campagne TNR", "#dashboard/tnr", [x["test"] for x in t["recommandations"] if x["categorie"] == "obligatoire" and not x["rejoue"]])
    if sans_test:
        alerte("haute" if f.get("sprint") else "moyenne", f"{len(sans_test)} exigence(s) {'du sprint ' if f.get('sprint') else ''}sans aucun test associé.",
               "Ouvrir Test Design", "#conception/us", sans_test)
    if m["echoues"]:
        alerte("moyenne", f"{len(m['echoues'])} test(s) en échec à leur dernière exécution.", "Consulter Failure Analysis", "#echecs", m["echoues"])
    if m["flaky"]:
        alerte("moyenne", f"{len(m['flaky'])} test(s) automatisé(s) instable(s).", "Voir la stabilité", "#gouvernance", m["flaky"])
    if m["bloques"]:
        alerte("moyenne", f"{len(m['bloques'])} test(s) bloqué(s) : ni réussis, ni échoués.", "Voir les exécutions", "#centre/vue", m["bloques"])
    disc = {i["id"]: i for i in c["discovery"]["indicateurs"]}
    if (disc["ecrans_non_valides"]["valeur"] or 0) > 0:
        alerte("basse", f"{disc['ecrans_non_valides']['valeur']} écran(s) découvert(s) sans association fonctionnelle validée.", "Relier écrans et exigences", "#discovery/correlation")
    if (disc["a_valider"]["valeur"] or 0) > 0:
        alerte("basse", f"{disc['a_valider']['valeur']} élément(s) proposé(s) en attente de validation : ils ne comptent dans aucun indicateur.", "Valider ou rejeter", "#intelligence/a_valider")
    modifiees = [e["element"] for e in t["evolutions"] if e["nature"].startswith("Exigence")]
    if modifiees:
        alerte("moyenne", f"{len(modifiees)} exigence(s) ont évolué depuis le {t['depuis']}.", "Revoir leurs tests", "#conception/us", modifiees)
    resp = responsables(f)["lignes"]
    sans = next((x for x in resp if x["responsable"] == "Sans responsable"), None)
    if sans and sans["charge"]:
        alerte("moyenne", f"{sans['charge']} élément(s) en attente sans responsable.", "Affecter dans Jira", "#dashboard/execution", sans["elements"])
    for x in [x for x in resp if x["surcharge"]]:
        alerte("basse", f"{x['responsable']} porte {x['charge']} éléments en attente, nettement plus que la moyenne.", "Répartir la charge", "#dashboard/execution")
    for src, d_ in (("Xray", m["date_xray"]), ("le périmètre des exigences", m["date_exigences"])):
        if d_ and d_ < (date.today() - timedelta(days=7)).isoformat():
            alerte("basse", f"La copie de {src} date du {d_} : les indicateurs peuvent être en retard.", "Resynchroniser", "#parametres")

    # recommandations : des règles sur des faits mesurés (aucun texte généré)
    mod_ex, mod_test = _module_exigence(), {x["cle"]: x.get("module") or "sans module" for x in m["tests"]}
    risque: dict = {}
    for k in sans_test:
        risque.setdefault(mod_ex.get(k) or "sans module", {"sans_test": 0, "echecs": 0, "bugs": 0})["sans_test"] += 1
    for k in m["echoues"]:
        risque.setdefault(mod_test.get(k, "sans module"), {"sans_test": 0, "echecs": 0, "bugs": 0})["echecs"] += 1
    for b in m["bugs_ouverts"]:
        for mo in {mod_test.get(x, "sans module") for x in b["tests"]} or {"sans module"}:
            risque.setdefault(mo, {"sans_test": 0, "echecs": 0, "bugs": 0})["bugs"] += 1
    classe = sorted(risque.items(), key=lambda kv: -(kv[1]["sans_test"] + 2 * kv[1]["echecs"] + 3 * kv[1]["bugs"]))[:5]
    if classe:
        reco("Quels sont les modules les plus risqués ?", f"{classe[0][0]} cumule le plus de signaux.", [k for k, _ in classe],
             [f"{k} : {v['sans_test']} exigence(s) sans test, {v['echecs']} test(s) en échec, {v['bugs']} bug(s) ouvert(s)" for k, v in classe],
             "haute" if classe[0][1]["bugs"] or classe[0][1]["echecs"] else "moyenne", "Risque de régression non détectée sur ces modules.",
             "Concevoir les tests manquants et traiter les échecs de ces modules en premier.", "#graphe/couverture", "mesure (classement par somme pondérée : indicatif)")
    if sans_test:
        reco("Quels tests faut-il concevoir en priorité ?", f"{len(sans_test)} exigence(s) n'ont aucun test.", sans_test, [f"périmètre importé le {m['date_exigences']}"],
             "haute", "Exigences livrables sans aucune vérification.", "Proposer les cas dans Test Design, en commençant par le sprint en cours.", "#conception/us", "mesure")
    a_auto = [x["cle"] for x in ex if x["manuelle_seulement"]]
    if a_auto:
        reco("Quels tests doivent être automatisés ?", f"{len(a_auto)} exigence(s) ne sont couvertes que par des tests manuels.", a_auto,
             ["aucun test lié n'est porté par un script Robot"], "moyenne", "Chaque campagne de non-régression reste manuelle sur ces exigences.",
             "Automatiser d'abord celles qui reviennent dans les TNR recommandés.", "#studio", "mesure")
    a_rejouer = [x["test"] for x in t["recommandations"] if x["categorie"] != "securite" and not x["rejoue"] and x["decision"] != "rejetée"]
    if a_rejouer:
        reco("Quels tests faut-il rejouer après les dernières évolutions ?", f"{len(a_rejouer)} test(s) touchés par {len(t['evolutions'])} évolution(s) n'ont pas été rejoués.",
             a_rejouer, [f"{e['nature']} : {e['element']}" for e in t["evolutions"][:6]], "haute", "Une régression sur ces parcours passerait inaperçue.",
             "Valider la sélection puis créer la campagne TNR.", "#dashboard/tnr", "déduction (relations fiables du Knowledge Graph)" + (" — sélection partielle" if t["avertissement"] else ""))
    if m["bugs_critiques"] or m["bugs_ouverts"]:
        cibles = m["bugs_critiques"] or m["bugs_ouverts"]
        reco("Quels bugs bloquent potentiellement la livraison ?", f"{len(cibles)} bug(s) {'critique(s) ' if m['bugs_critiques'] else ''}ouvert(s).", [b["cle"] for b in cibles],
             [f"{b['cle']} ({b.get('statut', '')}) : {len(b['tests'])} test(s) en échec associé(s)" for b in cibles[:6]], "haute" if m["bugs_critiques"] else "moyenne",
             "Tests associés en échec tant que le bug n'est pas corrigé.", "Suivre la correction, puis rejouer les tests associés.", "#centre/vue",
             "mesure" if m["priorite_bugs_connue"] else "mesure (priorité des bugs non lue : tous les bugs ouverts sont listés)")
    retard = [x for x in resp if x["en_retard"] or x["surcharge"]]
    if retard:
        reco("Qui doit traiter les éléments en retard ?", f"{len(retard)} personne(s) ont des actions en retard ou une charge élevée.", [x["responsable"] for x in retard],
             [f"{x['responsable']} : {x['charge']} en attente, {x['en_retard']} en retard" for x in retard], "moyenne", "Blocage d'organisation plutôt que de test.",
             "Répartir ou réaffecter dans Jira.", "#dashboard/execution", "mesure")
    prep = preparation(f)
    reco("Le sprint est-il suffisamment couvert pour envisager une livraison ?", f"État de préparation : {prep['statut']}.", [x["libelle"] for x in prep["criteres"] if x["respecte"] is not True],
         [f"{x['libelle']} : {x['valeur'] if x['valeur'] is not None else 'non mesuré'} (seuil {x['comparateur']} {x['seuil']})" for x in prep["criteres"]],
         "haute" if prep["statut"] == "NON PRÊT" else "moyenne", prep["raison"], "Lever les critères non respectés, ou ajuster les seuils du projet.", "#dashboard/decision",
         "mesure sur les critères du projet")
    ordre = {"haute": 0, "moyenne": 1, "basse": 2}
    return {"alertes": sorted(alertes, key=lambda a: ordre[a["priorite"]]), "recommandations": sorted(recos, key=lambda r: ordre[r["priorite"]]), "preparation": prep,
            "methode": "Alertes et recommandations sont calculées par des règles sur les données de l'atelier. Aucun texte n'est généré par une IA.", "filtres": f}
