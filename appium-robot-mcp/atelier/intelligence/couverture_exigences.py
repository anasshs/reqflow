"""Couverture fonctionnelle : liaison directe Test Xray ↔ Story / Requirement Jira (décision du 2026-11-15).

Modèle : Macro-fonctionnalité → Fonctionnalité → Exigence Jira → Critères d'acceptation → Tests Xray → Exécutions →
Résultats. Jira reste le référentiel des exigences, Xray celui des tests et des exécutions ; l'atelier lit leurs
relations natives (liens d'issue « Test » / « tests », lus des deux côtés) et n'en crée aucune. Les Epics / Features
(parents Jira) servent seulement à agréger.

- Périmètre : JQL des exigences de l'application (Paramètres › Configuration ; défaut : espaces Jira de la politique
  des US), moins les exigences exclues du périmètre de la Test Strategy.
- Quatre indicateurs distincts, jamais confondus : existence (≥ 1 test), exécution (tous ses tests exécutés),
  résultat (tous ses tests au dernier statut PASS), automatisée (≥ 1 test automatisé, sur la plateforme filtrée).
- Critères d'acceptation (activable par application) : un test couvre un critère par association enregistrée dans
  l'atelier (enrichissement local, historisé) ou par libellé Xray « AC1 » / « CA1 » sur le test.
- Synchronisations journalisées ; une exigence sortie de la JQL n'est jamais supprimée en silence : elle est gardée,
  marquée « hors périmètre », et le journal le dit. Instantanés datés, par version, pour suivre l'évolution.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

from atelier.domain import projet

CHAMPS = ["summary", "issuetype", "status", "parent", "issuelinks", "fixVersions", "components", "labels", "description"]
NIVEAUX_PARENTS = 3
RE_AC = re.compile(r"^(?:AC|CA)[-_ ]?(\d{1,2})$", re.I)


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _dossier():
    d = projet.PROJECT_DIR / "couverture"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _app() -> str:
    from atelier.discovery import carte

    return carte.app_courante() if carte.app_courante() else ""


def _fichier(nom: str):
    app = _app()
    return _dossier() / (f"{app}_{nom}" if app else nom)


def _lire_json(f, defaut):
    try:
        return json.loads(f.read_text("utf-8")) if f.exists() else defaut
    except (OSError, json.JSONDecodeError):
        return defaut


def _ecrire_json(f, data):
    from atelier.intelligence.strategie import _ecrire_atomique

    _ecrire_atomique(f, json.dumps(data, ensure_ascii=False, indent=1))


def _journal(nom: str, ligne: dict):
    with _fichier(nom).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(ligne, ensure_ascii=False) + "\n")


def _lire_journal(nom: str, n: int = 50) -> list[dict]:
    f = _fichier(nom)
    if not f.exists():
        return []
    out = []
    for l in f.read_text("utf-8").splitlines()[-n:]:
        try:
            out.append(json.loads(l))
        except json.JSONDecodeError:
            continue
    return list(reversed(out))


# =========================================================================== périmètre (JQL) et réglages
def jql_deduite() -> str:
    """JQL par défaut : US des espaces Jira de la politique de l'application (Paramètres › Configuration)."""
    from atelier.intelligence import testabilite_us

    esp = [e for e in testabilite_us.espaces() if e.get("actif", True)]
    if not esp:
        return ""
    projets_ = sorted({e["projet_jira"] for e in esp})
    types = sorted({t for e in esp for t in e.get("types_issue") or []}) or ["Story"]
    liste = lambda v: ", ".join('"' + x.replace('"', '\\"') + '"' for x in v)  # noqa: E731
    return f"project in ({liste(projets_)}) AND issuetype in ({liste(types)}) ORDER BY key"


def reglages() -> dict:
    """{"jql", "deduite", "criteres_actifs"} de l'application active."""
    from atelier.discovery import carte

    cfg = carte.config_app() if _app() else {}
    c = cfg.get("couverture") or {}
    deduite = jql_deduite()
    # jql_deduite : celle que donnerait la politique des US ; une JQL enregistrée la remplace et ne suit plus la politique
    return {"jql": c.get("jql_exigences") or deduite, "deduite": not c.get("jql_exigences"), "jql_deduite": deduite,
            "criteres_actifs": bool(c.get("criteres_actifs")), "champ_criteres": os.environ.get("JIRA_CHAMP_CRITERES", "").strip()}


def enregistrer_reglages(jql_exigences: str = "", criteres_actifs: bool | None = None) -> dict:
    from atelier.discovery import carte

    if not _app():
        raise ValueError("Aucune application sélectionnée.")
    c = dict(carte.config_app().get("couverture") or {})
    c["jql_exigences"] = (jql_exigences or "").strip()
    if criteres_actifs is not None:
        c["criteres_actifs"] = bool(criteres_actifs)
    carte.maj_app(_app(), couverture=c)
    return reglages()


# =========================================================================== import Jira (lecture seule)
def _type_lien_test(lien: dict) -> bool:
    t = lien.get("type") or {}
    return any("test" in (t.get(k) or "").lower() for k in ("name", "inward", "outward"))


def importer(jira=None) -> dict:
    """Lit dans Jira les exigences du périmètre (JQL), leurs tests liés (liens natifs), leurs parents (jusqu'à 3
    niveaux) ; compare à l'import précédent et journalise. Rien n'est écrit dans Jira / Xray."""
    from atelier.integrations.jira import JiraClient
    from atelier.intelligence import patrimoine_xray

    r = reglages()
    if not r["jql"]:
        raise ValueError("Aucune JQL d'exigences : la renseigner (Paramètres › Configuration) ou rattacher un espace Jira à l'application.")
    jira = jira or JiraClient()
    if not getattr(jira, "enabled", True):
        raise RuntimeError("Jira non configuré (Paramètres › Connexions).")
    champs = CHAMPS + ([r["champ_criteres"]] if r["champ_criteres"] else [])
    issues = jira.rechercher(r["jql"], champs, patrimoine_xray.limite_import())
    tronque = bool(getattr(jira, "tronque", False))
    exigences = {}
    for i in issues:
        f = i.get("fields") or {}
        lies = [l.get("outwardIssue") or l.get("inwardIssue") for l in f.get("issuelinks") or [] if _type_lien_test(l)]
        tests = sorted({x["key"] for x in lies if x and _est_test(x)})  # lien « Test » vers un ticket de type Test Xray
        exigences[i["key"]] = {"cle": i["key"], "resume": f.get("summary") or "", "type_jira": (f.get("issuetype") or {}).get("name", ""),
                               "statut": (f.get("status") or {}).get("name", ""), "parent": (f.get("parent") or {}).get("key"),
                               "versions": [v.get("name") for v in f.get("fixVersions") or [] if v.get("name")],
                               "composants": [c.get("name") for c in f.get("components") or [] if c.get("name")],
                               "tests_jira": tests, **patrimoine_xray._description_et_criteres(f, r["champ_criteres"])}
    # parents (fonctionnalités, macro-fonctionnalités) : remontée jusqu'à NIVEAUX_PARENTS
    parents: dict = {}
    a_lire = {e["parent"] for e in exigences.values() if e["parent"] and e["parent"] not in exigences}
    for _ in range(NIVEAUX_PARENTS):
        a_lire -= set(parents) | set(exigences)
        if not a_lire:
            break
        lus = patrimoine_xray._par_lots(jira, sorted(a_lire), ["summary", "issuetype", "status", "parent"])
        a_lire = set()
        for i in lus:
            f = i.get("fields") or {}
            parents[i["key"]] = {"cle": i["key"], "resume": f.get("summary") or "", "type_jira": (f.get("issuetype") or {}).get("name", ""),
                                 "statut": (f.get("status") or {}).get("name", ""), "parent": (f.get("parent") or {}).get("key")}
            if parents[i["key"]]["parent"]:
                a_lire.add(parents[i["key"]]["parent"])
    epics = {}
    projets_ = sorted({k.split("-")[0] for k in exigences})
    if projets_:  # Epics des projets du périmètre, même sans Story : détection « Epic sans Story » (Coverage Intelligence)
        try:
            for i in jira.rechercher(f"project in ({', '.join(projets_)}) AND issuetype = Epic", ["summary", "status", "description"], 500):
                f = i.get("fields") or {}
                epics[i["key"]] = {"cle": i["key"], "resume": f.get("summary") or "", "statut": (f.get("status") or {}).get("name", "")}
        except Exception:  # noqa: BLE001 — type Epic absent ou JQL refusée : la détection est simplement indisponible
            epics = {}
    return _fusionner_import(exigences, parents, r["jql"], tronque, epics)


def _est_test(issue: dict | None) -> bool:
    nom = ((((issue or {}).get("fields") or {}).get("issuetype") or {}).get("name") or "").strip().lower()
    types = {"test"} | {t.strip().lower() for t in (os.environ.get("XRAY_TEST_ISSUE_TYPE") or "").split(",") if t.strip()}
    return nom in types


def _fusionner_import(exigences: dict, parents: dict, jql: str, tronque: bool, epics: dict | None = None) -> dict:
    """Comparaison avec l'import précédent : ajouts, sorties du périmètre (gardées, marquées), liens changés."""
    avant = _lire_json(_fichier("exigences.json"), {"exigences": {}})
    anciennes = avant.get("exigences") or {}
    if not exigences and anciennes:
        raise ValueError("La JQL ne renvoie aucune exigence : import refusé, les données précédentes sont conservées.")
    ajoutees = sorted(set(exigences) - set(anciennes))
    sorties = sorted(k for k in set(anciennes) - set(exigences) if not anciennes[k].get("hors_perimetre"))
    liens_changes = sorted(k for k in set(exigences) & set(anciennes) if set(exigences[k]["tests_jira"]) != set(anciennes[k].get("tests_jira") or []))
    date = _maintenant()
    for k in set(anciennes) - set(exigences):  # jamais de perte silencieuse
        exigences[k] = {**anciennes[k], "hors_perimetre": anciennes[k].get("hors_perimetre") or date}
    data = {"date": date, "jql": jql, "tronque": tronque, "exigences": exigences, "parents": {**(avant.get("parents") or {}), **parents},
            "epics": epics if epics is not None else avant.get("epics") or {}}
    _ecrire_json(_fichier("exigences.json"), data)
    bilan = {"date": date, "jql": jql, "exigences": sum(1 for e in exigences.values() if not e.get("hors_perimetre")),
             "ajoutees": ajoutees, "sorties_du_perimetre": sorties, "liens_modifies": liens_changes, "tronque": tronque}
    _journal("synchro.jsonl", bilan)
    return bilan


# =========================================================================== critères d'acceptation (enrichissement local)
def associer_critere(exigence: str, index: int, tests: list[str]) -> dict:
    """Tests qui couvrent le critère n° index (1…) de l'exigence. Enrichissement de l'atelier, historisé."""
    data = _lire_json(_fichier("exigences.json"), {}).get("exigences") or {}
    e = data.get(exigence)
    if not e:
        raise KeyError(f"Exigence {exigence} inconnue : importer les exigences d'abord.")
    if not 1 <= int(index) <= len(e.get("criteres") or []):
        raise ValueError(f"Critère {index} absent de {exigence}.")
    m = _lire_json(_fichier("criteres.json"), {})
    m.setdefault(exigence, {})[str(int(index))] = sorted(set(tests))
    _ecrire_json(_fichier("criteres.json"), m)
    _journal("criteres.jsonl", {"date": _maintenant(), "exigence": exigence, "critere": int(index), "tests": sorted(set(tests))})
    return m[exigence]


# =========================================================================== calcul
def _classe(st: str) -> str:
    s = (st or "").upper()
    return "reussi" if "PASS" in s else "echec" if any(x in s for x in ("FAIL", "ABORT", "BLOCK")) else "non_execute" if not s or s in ("TODO", "TO DO", "EXECUTING") else "autre"


def _pct(n: int, d: int):
    return round(100 * n / d, 1) if d else None


def calculer(version: str = "", plateforme: str = "") -> dict:
    """Couverture du périmètre : par exigence, par fonctionnalité, par macro-fonctionnalité et globale."""
    from atelier.execution.depot_robot import lire_depot
    from atelier.intelligence import patrimoine_xray, strategie

    r = reglages()
    src = _lire_json(_fichier("exigences.json"), {})
    pat = patrimoine_xray.charger_vue() or {"tests": []}
    tests_info = {t["cle"]: t for t in pat.get("tests") or []}
    inv = lire_depot()
    plats: dict = {}
    for t in inv["tests"].values():
        for c in t.get("cles_xray") or []:
            plats.setdefault(c, set()).update(t.get("plateformes") or [])
    auto = {c for c, p in plats.items() if not plateforme or plateforme in p}
    # liens côté tests (champ « exigences » de la copie Xray) : même relation native, lue depuis le test
    par_exig: dict = {}
    for t in pat.get("tests") or []:
        for e in t.get("exigences") or []:
            par_exig.setdefault(e, set()).add(t["cle"])
    exclues = set()
    try:
        s = strategie.charger() or {}
        exclues = {k for x in (s.get("rubriques") or {}).get("perimetre") or [] if x.get("inclus") is False for k in x.get("jira") or []}
    except Exception:  # noqa: BLE001 — stratégie absente : tout le périmètre Jira
        pass
    assoc = _lire_json(_fichier("criteres.json"), {})
    parents = src.get("parents") or {}
    toutes = src.get("exigences") or {}
    versions = sorted({v for e in toutes.values() for v in e.get("versions") or []})

    def chaine(cle):
        out, p, vus = [], toutes.get(cle, {}).get("parent"), set()
        while p and p not in vus and len(out) < NIVEAUX_PARENTS:
            vus.add(p)
            info = parents.get(p) or toutes.get(p) or {"cle": p, "resume": "", "type_jira": ""}
            out.append(info)
            p = info.get("parent")
        return out

    lignes, hors = [], []
    for k, e in sorted(toutes.items()):
        if e.get("hors_perimetre") or k in exclues:
            hors.append({"cle": k, "resume": e.get("resume"), "raison": "exclue de la Test Strategy" if k in exclues else f"sortie de la JQL le {e['hors_perimetre'][:10]}"})
            continue
        if version and version not in (e.get("versions") or []):
            continue
        tests = sorted(set(e.get("tests_jira") or []) | par_exig.get(k, set()))
        st = {t: ((tests_info.get(t) or {}).get("statut_xray") or {}).get("statut", "") for t in tests}
        cl = {t: _classe(s_) for t, s_ in st.items()}
        executes = [t for t in tests if cl[t] in ("reussi", "echec", "autre")]
        ac = e.get("criteres") or []
        ac_tests = []
        if r["criteres_actifs"] and ac:
            for n in range(1, len(ac) + 1):
                via_lib = {t for t in tests if any((m := RE_AC.match(lb)) and int(m.group(1)) == n for lb in (tests_info.get(t) or {}).get("libelles") or [])}
                ac_tests.append(sorted(via_lib | set((assoc.get(k) or {}).get(str(n)) or [])))
        ch = chaine(k)
        fonc, macro = (ch[0] if ch else None), (ch[-1] if ch else None)
        etat = "non_couverte" if not tests else "partielle" if ac_tests and any(not x for x in ac_tests) else "couverte"
        lignes.append({"cle": k, "resume": e.get("resume", ""), "type_jira": e.get("type_jira", ""), "statut": e.get("statut", ""),
                       "versions": e.get("versions") or [], "fonctionnalite": fonc["cle"] if fonc else "", "macro": macro["cle"] if macro else "",
                       "tests": [{"cle": t, "statut": st[t], "classe": cl[t], "automatise": t in auto, "resume": (tests_info.get(t) or {}).get("resume", ""),
                                  "connu": t in tests_info} for t in tests],
                       "existence": bool(tests), "execution": bool(tests) and len(executes) == len(tests),
                       "execution_partielle": 0 < len(executes) < len(tests),
                       "resultat": bool(tests) and all(cl[t] == "reussi" for t in tests), "echec": any(cl[t] == "echec" for t in tests),
                       "automatisee": any(t in auto for t in tests), "manuelle_seulement": bool(tests) and not any(t in auto for t in tests),
                       "criteres": [{"index": n + 1, "texte": ac[n], "tests": ac_tests[n] if ac_tests else []} for n in range(len(ac))] if r["criteres_actifs"] else [],
                       "criteres_non_testes": sum(1 for x in ac_tests if not x), "etat": etat})

    def agreger(sel):
        n = len(sel)
        tests = {t["cle"] for x in sel for t in x["tests"]}
        return {"exigences": n, "tests": len(tests), "tests_automatises": sum(1 for t in tests if t in auto),
                "couvertes": sum(x["existence"] for x in sel), "partielles": sum(x["etat"] == "partielle" for x in sel),
                "existence": _pct(sum(x["existence"] for x in sel), n), "execution": _pct(sum(x["execution"] for x in sel), n),
                "resultat": _pct(sum(x["resultat"] for x in sel), n), "automatisee": _pct(sum(x["automatisee"] for x in sel), n),
                "en_echec": sum(x["echec"] for x in sel), "sans_test": sum(not x["existence"] for x in sel),
                "part_tests_automatises": _pct(sum(1 for t in tests if t in auto), len(tests))}

    def libelle(cle):
        i = parents.get(cle) or toutes.get(cle) or {}
        return {"cle": cle, "resume": i.get("resume", ""), "type_jira": i.get("type_jira", "")}

    fonctions = []
    for f in sorted({x["fonctionnalite"] for x in lignes}):
        sel = [x for x in lignes if x["fonctionnalite"] == f]
        fonctions.append({**(libelle(f) if f else {"cle": "", "resume": "Sans fonctionnalité", "type_jira": ""}), "macro": sel[0]["macro"], **agreger(sel)})
    macros = []
    for m in sorted({x["macro"] for x in lignes}):
        sel = [x for x in lignes if x["macro"] == m]
        macros.append({**(libelle(m) if m else {"cle": "", "resume": "Sans macro-fonctionnalité", "type_jira": ""}),
                       "fonctionnalites": len({x["fonctionnalite"] for x in sel}), **agreger(sel)})
    lies = {t for x in lignes for t in (y["cle"] for y in x["tests"])} | {t for ts in par_exig.values() for t in ts}
    return {"reglages": r, "import": {k: src.get(k) for k in ("date", "jql", "tronque")}, "filtres": {"version": version, "plateforme": plateforme},
            "versions": versions, "global": agreger(lignes), "macros": macros, "fonctionnalites": fonctions, "exigences": lignes,
            "sans_test": [x["cle"] for x in lignes if not x["existence"]],
            "tests_sans_exigence": sorted(t["cle"] for t in pat.get("tests") or [] if t["cle"] not in lies),
            "en_echec": [x["cle"] for x in lignes if x["echec"]], "manuelles_seulement": [x["cle"] for x in lignes if x["manuelle_seulement"]],
            "criteres_non_testes": [{"exigence": x["cle"], "index": c["index"], "texte": c["texte"]} for x in lignes for c in x["criteres"] if not c["tests"]],
            "hors_perimetre": hors,
            "definitions": {
                "existence": "Exigence avec au moins un Test Xray lié (lien natif Jira/Xray, lu depuis l'exigence ou depuis le test).",
                "execution": "Tous les tests liés ont été exécutés (dernier statut Xray différent de TO DO / EXECUTING / vide).",
                "resultat": "Tous les tests liés ont PASS comme dernier statut Xray.",
                "automatisee": "Au moins un test lié est automatisé (clé portée par un test Robot du dépôt" + (f", plateforme {plateforme}" if plateforme else "") + ").",
                "partielle": "Exigence avec des tests, mais au moins un critère d'acceptation sans test (si les critères sont activés)."}}


# =========================================================================== instantanés et historique
def enregistrer_instantane(version: str = "", commentaire: str = "") -> dict:
    c = calculer(version)
    ligne = {"date": _maintenant(), "version": version or "toutes", "commentaire": commentaire.strip(), "global": c["global"],
             "macros": [{k: m[k] for k in ("cle", "resume", "exigences", "existence", "execution", "resultat", "automatisee")} for m in c["macros"]]}
    _journal("instantanes.jsonl", ligne)
    return ligne


def evolution() -> dict:
    return {"instantanes": _lire_journal("instantanes.jsonl", 100), "synchros": _lire_journal("synchro.jsonl", 30)}
