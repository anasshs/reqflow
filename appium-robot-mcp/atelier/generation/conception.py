"""Test Design : couche de conception autour de Xray (cahier des charges « Module Test Design »).

Xray reste le référentiel officiel des tests : ce module lit l'instantané Xray (patrimoine), les
scénarios BDD et le dépôt Robot, et ne conserve que des MÉTADONNÉES de conception :
  conception/revues.json            revue interne par objet (séparée du statut Xray)
  conception/baselines/<nom>.json   baselines immuables (création exclusive)
  conception/mapping_xray.yaml      correspondances objets / champs / statuts plateforme ↔ Jira / Xray
  conception/journal.jsonl          journal d'audit
Seule écriture vers Xray : publier_bdd (test Gherkin créé ou Gherkin mis à jour), sur action explicite, avec détection
de conflit et historique (conception/sync_xray.jsonl). createTest / updateGherkinTestDefinition : voir docs/XRAY_API.md.
"""
from __future__ import annotations

from atelier.domain.yaml_rapide import charger as charger_yaml

import json
import os
import re
from collections import Counter

import yaml

from atelier.domain import projet
from atelier.intelligence.strategie import _auteur, _ecrire_atomique, _maintenant

STATUTS_REVUE = ["Draft", "In Review", "Changes Requested", "Approved", "Ready for Automation"]
LIBELLES_REVUE = {"Draft": "Brouillon", "In Review": "En revue", "Changes Requested": "Modifications demandées",
                  "Approved": "Approuvé", "Ready for Automation": "Prêt pour l'automatisation"}
TRANSITIONS_REVUE = {"soumettre": (("Draft", "Changes Requested"), "In Review"),
                     "demander_modifications": (("In Review",), "Changes Requested"),
                     "approuver": (("In Review",), "Approved"),
                     "pret_automatisation": (("Approved",), "Ready for Automation"),
                     "rouvrir": (("Approved", "Ready for Automation"), "Draft")}
EDITEURS = {"manual": "etapes", "cucumber": "bdd", "generic": "technique", "exploratory": "exploratoire"}

OBJETS_DEFAUT = [
    ("Requirement", "Jira Epic / Story (issue configurée)"), ("Test Case", "Xray Test"), ("Manual Test", "Xray Manual Test"),
    ("BDD Scenario", "Xray Cucumber Test"), ("Generic Automated Test", "Xray Generic Test"),
    ("Test Precondition", "Xray Precondition"), ("Test Suite", "Xray Test Set ou objet interne"),
    ("Test Repository Folder", "Xray Test Repository Folder"), ("Test Plan", "Xray Test Plan"),
    ("Test Execution", "Xray Test Execution"), ("Test Run", "Xray Test Run")]
CHAMPS_DEFAUT = [  # (interne, externe, sens, clé dans l'instantané Xray pour « tester le mapping »)
    ("test_key", "Issue Key", "lecture", "cle"), ("summary", "Summary", "bidirectionnel", "resume"),
    ("description", "Description", "bidirectionnel", "description"), ("priority", "Priority", "bidirectionnel", "criticite"),
    ("test_type", "Test Type", "bidirectionnel", "type"), ("preconditions", "Preconditions", "bidirectionnel", "preconditions"),
    ("steps.action", "Action", "bidirectionnel", "etapes"), ("steps.data", "Data", "bidirectionnel", "etapes"),
    ("steps.expected", "Expected Result", "bidirectionnel", "etapes"), ("gherkin", "Scenario", "bidirectionnel", "gherkin"),
    ("labels", "Labels", "bidirectionnel", "libelles"), ("assignee", "Assignee", "bidirectionnel", "assignee"),
    ("dataset", "Champ personnalisé / référence externe", "selon configuration", ""),
    ("repository_path", "Test Repository Folder", "bidirectionnel", "dossier")]
SENS = ["lecture", "écriture", "bidirectionnel", "selon configuration"]


def _dossier():
    return projet.PROJECT_DIR / "conception"


def _journaliser(op: str, **details):
    f = _dossier() / "journal.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": _maintenant(), "auteur": _auteur(), "op": op, **details}, ensure_ascii=False) + "\n")


def journal(limite: int = 200) -> list[dict]:
    f = _dossier() / "journal.jsonl"
    lignes = [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()] if f.exists() else []
    return list(reversed(lignes))[:limite]


# =========================================================================== sources
def _sources() -> dict:
    from atelier.discovery import connaissance
    from atelier.generation import bdd
    from atelier.intelligence import patrimoine_xray

    pat = patrimoine_xray.charger_vue() or {"tests": [], "exigences": [], "plans": []}
    g = connaissance.construire()
    return {"pat": pat, "etat_xray": patrimoine_xray.etat(), "bdd": {b["cle"]: b for b in bdd.lister()}, "g": g}


def _revues() -> dict:
    f = _dossier() / "revues.json"
    return json.loads(f.read_text("utf-8")) if f.exists() else {}


def _etat_sync(etat_xray: dict) -> str:
    if not etat_xray.get("present"):
        return "non synchronisé"
    d = etat_xray.get("definitions_xray") or {}
    return (f"définitions Xray importées le {d['date'][:10]}" if d.get("date")
            else f"importé de Jira (instantané du {str(etat_xray.get('date'))[:10]}) ; définitions Xray non importées")


# =========================================================================== écrans de consultation
def cas_de_test() -> list[dict]:
    """Écran 03 : cas de test Xray + éditeur selon le type + statut de revue interne + état de synchronisation."""
    s = _sources()
    rev = _revues()
    out = []
    gherkin = noms_gherkin()
    for t in s["pat"]["tests"]:
        n = s["g"].noeuds.get(f"test:{t['cle']}")
        p = n.proprietes if n else {}
        typ = str(t.get("type") or "").lower()
        typ = "cucumber" if typ in gherkin else typ  # le type Gherkin du projet, quel que soit son nom dans Xray
        out.append({"cle": t["cle"], "resume": t.get("resume", ""), "type": t.get("type", ""), "module": t.get("module", ""),
                    "priorite": t.get("criticite", ""), "exigences": t.get("exigences", []), "plans": t.get("plans", []),
                    "statut_xray": t.get("statut", ""), "automatise": bool(p.get("automatise")),
                    "dernier_resultat": p.get("dernier_resultat"), "editeur": EDITEURS.get(typ, "inconnu"),
                    "bdd": t["cle"] if t["cle"] in s["bdd"] else "", "statut_bdd": (s["bdd"].get(t["cle"]) or {}).get("statut", ""),
                    "revue": (rev.get(f"test:{t['cle']}") or {}).get("statut", "Draft"),
                    "synchronisation": _etat_sync(s["etat_xray"]), "issueId": t.get("issueId", ""), "dossier": t.get("dossier", ""),
                    "etapes": t.get("etapes"), "gherkin": t.get("gherkin", ""), "definition": t.get("definition", ""),
                    "preconditions": t.get("preconditions") or [], "type_jira": t.get("type_jira", "")})
    return out


def exigences() -> list[dict]:
    """Écran 02 : exigences de l'instantané avec leurs tests ; sans test = trou de couverture."""
    s = _sources()
    par_exig: dict = {}
    for t in s["pat"]["tests"]:
        for e in t.get("exigences") or []:
            par_exig.setdefault(e, []).append(t["cle"])
    return [{**e, "tests": par_exig.get(e["cle"], []), "sans_test": not par_exig.get(e["cle"])} for e in s["pat"]["exigences"]]


def vue_ensemble() -> dict:
    """Écran 01 : indicateurs calculés depuis les données réelles (aucune saisie)."""
    cas = cas_de_test()
    ex = exigences()
    s = _sources()
    rev = Counter(c["revue"] for c in cas)
    modules: dict = {}
    for e in ex:
        m = modules.setdefault(e.get("module") or "—", {"exigences": 0, "couvertes": 0})
        m["exigences"] += 1
        m["couvertes"] += 0 if e["sans_test"] else 1
    at = tests_atelier({c["cle"] for c in cas})
    return {
        "kpi": {"exigences": len(ex), "cas_xray": len(cas), "scenarios_bdd": len(s["bdd"]),
                "a_revoir": rev["In Review"] + rev["Changes Requested"] + at["a_revoir"], "approuves": rev["Approved"] + at["approuves"],
                "prets_automatisation": rev["Ready for Automation"] + at["prets_automatisation"],
                "automatises": sum(c["automatise"] for c in cas) + at["automatises"],
                "couverture_exigences": round(100 * sum(not e["sans_test"] for e in ex) / len(ex), 1) if ex else None},
        "detail": {"xray": {"a_revoir": rev["In Review"] + rev["Changes Requested"], "approuves": rev["Approved"],
                            "prets_automatisation": rev["Ready for Automation"], "automatises": sum(c["automatise"] for c in cas)},
                   "atelier": {k: at[k] for k in ("a_revoir", "approuves", "prets_automatisation", "automatises")}},
        "tests_atelier": at["par_etape"], "nb_tests_atelier": at["total"],
        "xray": s["etat_xray"],
        "par_statut_xray": dict(Counter(c["statut_xray"] or "—" for c in cas)),
        "par_type": dict(Counter(c["type"] or "—" for c in cas)),
        "par_priorite": dict(Counter(c["priorite"] or "—" for c in cas)),
        "par_revue": {k: rev[k] for k in STATUTS_REVUE},
        "couverture_modules": modules,
        "exigences_sans_test": [e["cle"] for e in ex if e["sans_test"]],
        "activite": journal(10),
        "bdd_recents": sorted(({"cle": b["cle"], "titre": b.get("titre", ""), "statut": b.get("statut", ""), "maj": str(b.get("maj") or "")}
                               for b in s["bdd"].values() if b.get("maj")), key=lambda b: b["maj"], reverse=True)[:8],
    }


def tests_atelier(cles_xray: set | None = None) -> dict:
    """Tests conçus dans l'atelier (scénarios BDD sans cas Xray : Discovery, saisie, MBT) et leur avancement. Sans eux, un
    projet sans Xray affichait 0 approuvé, 0 prêt, 0 automatisé alors que ses tests l'étaient (constat du 2026-11-22).
    « À revoir » = scénario brouillon ; « approuvé » = scénario validé ; « prêt » = validé, script pas encore écrit ;
    « automatisé » = script écrit (un test du dépôt porte la clé du scénario)."""
    from atelier.generation import bdd, maintenance

    cles_xray = cles_xray or set()
    l = [b for b in bdd.lister() if b["cle"] not in cles_xray]
    try:
        cyc = maintenance.cycle_bdd() if l else {}
    except Exception:  # noqa: BLE001 — dépôt illisible : avancement inconnu, les scénarios restent comptés
        cyc = {}
    etapes = Counter(maintenance.etape_bdd(b, cyc.get(b["cle"]))["etape"] for b in l)
    valides = [b for b in l if b.get("statut") == "validé"]
    return {"total": len(l), "a_revoir": sum(1 for b in l if b.get("statut") != "validé" and b["cle"] not in cyc),
            "approuves": len(valides), "prets_automatisation": sum(1 for b in valides if b["cle"] not in cyc),
            "automatises": sum(1 for b in l if b["cle"] in cyc),
            "par_etape": {lib: etapes.get(e, 0) for e, lib in (("valider_bdd", "Scénario à valider"), ("generer", "Script à générer"),
                                                               ("verifier", "À vérifier (run réel)"), ("valider_test", "Test à valider"),
                                                               ("fait", "Automatisé, vérifié, validé"))}}


# =========================================================================== revue et validation (écran 10)
def controles_revue(cle: str) -> list[dict]:
    """Contrôles avant approbation d'un cas de test (gravité haute = bloque l'approbation)."""
    from atelier.generation import bdd
    from atelier.intelligence import couverture, patrimoine_xray

    pat = patrimoine_xray.charger_vue() or {"tests": []}
    t = next((x for x in pat["tests"] if x["cle"] == cle), None)
    if not t:
        raise KeyError(f"Cas de test {cle} absent de l'instantané Xray.")
    out = []
    ok = lambda code, msg: out.append({"code": code, "gravite": "ok", "message": msg})  # noqa: E731
    ko = lambda code, g, msg: out.append({"code": code, "gravite": g, "message": msg})  # noqa: E731
    (ok if t.get("exigences") else lambda c, m: ko(c, "haute", m))("exigence", "Exigence associée." if t.get("exigences") else "Aucune exigence associée.")
    m = bdd.charger(cle)
    if str(t.get("type", "")).lower() in noms_gherkin() or m:
        if not m:
            ko("bdd", "haute", "Test Gherkin sans scénario BDD.")
        else:
            hautes = [c["message"] for c in bdd.controles(m) if c["gravite"] == "haute"]
            if hautes:
                ko("bdd", "haute", "Scénario BDD : " + " ; ".join(hautes))
            else:
                ok("bdd", "Scénario BDD sans défaut bloquant.")
            if m.get("jdd"):
                ok("jdd", f"Jeu de données associé : {m['jdd']}.")
            else:
                ko("jdd", "moyenne", "Aucun jeu de données associé au scénario.")
    if str(t.get("type", "")).lower() == "manual":
        if t.get("etapes"):
            ok("etapes", f"{len(t['etapes'])} étape(s) avec résultat attendu.")
        else:
            ko("etapes", "info", "Étapes non présentes dans l'instantané : à vérifier dans Xray.")
    from atelier.discovery import connaissance

    doublons = [r for r in couverture.indicateurs(connaissance.construire(), pat).get("redondances", []) if cle in r["tests"]]
    if doublons:
        ko("doublon", "moyenne", "Doublon possible avec " + ", ".join(x for r in doublons for x in r["tests"] if x != cle) + ".")
    else:
        ok("doublon", "Aucun doublon détecté.")
    return out


def revue(cle: str) -> dict:
    r = _revues().get(f"test:{cle}") or {"statut": "Draft", "reviseur": "", "historique": []}
    return {**r, "cle": cle, "controles": controles_revue(cle)}


def transition_revue(cle: str, action: str, commentaire: str = "", reviseur: str = "") -> dict:
    if action not in TRANSITIONS_REVUE:
        raise ValueError(f"Action inconnue : {action}")
    depuis, vers = TRANSITIONS_REVUE[action]
    revs = _revues()
    r = revs.setdefault(f"test:{cle}", {"statut": "Draft", "reviseur": "", "historique": []})
    if r["statut"] not in depuis:
        raise ValueError(f"« {action} » impossible depuis {LIBELLES_REVUE[r['statut']]}.")
    if action == "demander_modifications" and not commentaire.strip():
        raise ValueError("Préciser les modifications demandées.")
    if action in ("approuver", "pret_automatisation"):
        bloquants = [c["message"] for c in controles_revue(cle) if c["gravite"] == "haute"]
        if bloquants:
            raise ValueError("Contrôles bloquants : " + " ; ".join(bloquants))
    if reviseur:
        r["reviseur"] = reviseur.strip()
    r["historique"].append({"date": _maintenant(), "auteur": _auteur(), "action": action, "de": r["statut"], "vers": vers,
                            "commentaire": commentaire.strip()})
    r["statut"] = vers
    _ecrire_atomique(_dossier() / "revues.json", json.dumps(revs, ensure_ascii=False, indent=1))
    _journaliser("revue", cle=cle, action=action, vers=vers)
    return revue(cle)


# =========================================================================== baselines (écran 11)
def _nom_baseline(nom: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,60}", nom or ""):
        raise ValueError("Nom de baseline : lettres, chiffres, « _ », « - » et « . » (60 caractères au plus).")
    return nom


def _etat_courant() -> dict:
    from atelier.execution.depot_robot import lire_depot
    from atelier.generation import bdd

    s = _sources()
    scen = {}
    for cle in s["bdd"]:
        m = bdd.charger(cle)
        scen[cle] = {"statut": m.get("statut", ""), "gherkin": bdd.serialiser(m)}
    return {"exigences": {e["cle"]: {k: e.get(k) for k in ("resume", "statut", "module", "parent")} for e in s["pat"]["exigences"]},
            "tests": {t["cle"]: {k: t.get(k) for k in ("resume", "type", "statut", "criticite", "module", "exigences", "gherkin")}
                      for t in s["pat"]["tests"]},
            "scenarios_bdd": scen, "suites": sorted(lire_depot()["suites"])}


def creer_baseline(nom: str, description: str = "") -> dict:
    nom = _nom_baseline(nom)
    f = _dossier() / "baselines" / f"{nom}.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    contenu = {"nom": nom, "description": description.strip(), "date": _maintenant(), "auteur": _auteur(), **_etat_courant()}
    with f.open("x", encoding="utf-8") as fh:  # immuable : jamais réécrite
        fh.write(json.dumps(contenu, ensure_ascii=False, indent=1))
    _journaliser("baseline", nom=nom)
    return resume_baseline(contenu)


def resume_baseline(b: dict) -> dict:
    return {"nom": b["nom"], "description": b.get("description", ""), "date": b["date"], "auteur": b["auteur"],
            "exigences": len(b["exigences"]), "tests": len(b["tests"]), "scenarios_bdd": len(b["scenarios_bdd"]), "suites": len(b["suites"])}


def baselines() -> list[dict]:
    d = _dossier() / "baselines"
    return [resume_baseline(json.loads(f.read_text("utf-8"))) for f in sorted(d.glob("*.json"))] if d.exists() else []


def _baseline(nom: str) -> dict:
    if nom == "courant":
        return _etat_courant()
    f = _dossier() / "baselines" / f"{_nom_baseline(nom)}.json"
    if not f.exists():
        raise KeyError(f"Baseline inconnue : {nom}")
    return json.loads(f.read_text("utf-8"))


def comparer_baselines(a: str, b: str = "courant") -> dict:
    """Ajouts, suppressions, modifications ; tests impactés par une exigence modifiée."""
    x, y = _baseline(a), _baseline(b)
    out = {}
    for k in ("exigences", "tests", "scenarios_bdd"):
        ax, by = x.get(k, {}), y.get(k, {})
        out[k] = {"ajoutes": sorted(set(by) - set(ax)), "supprimes": sorted(set(ax) - set(by)),
                  "modifies": {c: [f for f in set(ax[c]) | set(by[c]) if ax[c].get(f) != by[c].get(f)]
                               for c in sorted(set(ax) & set(by)) if ax[c] != by[c]}}
    exig_mod = set(out["exigences"]["modifies"])
    out["tests_impactes"] = sorted(c for c, t in y.get("tests", {}).items() if exig_mod & set(t.get("exigences") or []))
    out["suites"] = {"ajoutees": sorted(set(y.get("suites", [])) - set(x.get("suites", []))),
                     "supprimees": sorted(set(x.get("suites", [])) - set(y.get("suites", [])))}
    return out


# =========================================================================== mapping Xray (écran 12)
CHAMPS_APPLICATION = {"composant": "Composant Jira", "libelle": "Libellé Jira", "personnalise": "Champ personnalisé Jira"}


def type_gherkin() -> str:
    """Nom, dans le Xray du projet, du type de test dont la définition est du Gherkin : celui que le mapping associe à
    l'éditeur BDD (Test Design › Réglages). « Cucumber » par défaut, comme dans Xray Cloud."""
    return next((str(t.get("xray") or "").strip() for t in mapping().get("types", [])
                 if t.get("editeur") == "bdd" and str(t.get("xray") or "").strip()), "Cucumber")


def noms_gherkin() -> set[str]:
    """Noms de type (en minuscules) reconnus comme « test Gherkin » : le nom réglé, et les deux noms usuels."""
    return {type_gherkin().lower(), "cucumber", "gherkin"}


def _defaut_mapping() -> dict:
    return {"objets": [{"interne": i, "externe": e, "confirme": False} for i, e in OBJETS_DEFAUT],
            "champs": [{"interne": i, "externe": e, "sens": s, "actif": True, "obligatoire": i in ("test_key", "summary", "test_type"),
                        "transformation": "", "cle_instantane": c} for i, e, s, c in CHAMPS_DEFAUT],
            "statuts": [{"interne": s, "externe": ""} for s in STATUTS_REVUE],  # jamais supposé : à configurer
            "types": [{"xray": "Manual", "editeur": "etapes"}, {"xray": "Cucumber", "editeur": "bdd"},
                      {"xray": "Generic", "editeur": "technique"}, {"xray": "Exploratory", "editeur": "exploratoire"}],
            "projet_jira": "", "dossier_repository": "", "mode": "A (import)",
            "application": {"champ": "composant", "champ_jira": ""}}


def mapping() -> dict:
    f = _dossier() / "mapping_xray.yaml"
    m = charger_yaml(f.read_text("utf-8")) if f.exists() else _defaut_mapping()
    m.setdefault("application", {"champ": "composant", "champ_jira": ""})
    return {**m, "champs_application": CHAMPS_APPLICATION, "modes": {"A (import)": "disponible : instantané JSON ou synchronisation Jira (description et critères inclus)",
                           "B (bidirectionnel)": "disponible pour les tests Gherkin : mise à jour du Gherkin, conflits détectés (jamais d'écrasement silencieux)",
                           "C (publication)": "disponible : scénario BDD publié comme test Gherkin, clé Xray conservée"},
            "sens_possibles": SENS, "statuts_internes": STATUTS_REVUE, "libelles_revue": LIBELLES_REVUE}


def enregistrer_mapping(m: dict) -> dict:
    propre = {k: m[k] for k in ("objets", "champs", "statuts", "types", "projet_jira", "dossier_repository", "mode", "application", "cycle_vie") if k in m}
    for t in propre.get("types") or []:
        t["xray"] = str(t.get("xray") or "").strip()
        if not re.fullmatch(r"[\w .\-/()]{1,60}", t["xray"]):
            raise ValueError("Nom d'un type de test Xray : 1 à 60 caractères (lettres, chiffres, espaces, . - / ( )).")
    cc = ((propre.get("cycle_vie") or {}).get("champ_candidat") or "").strip()
    if cc and not re.fullmatch(r"customfield_\d+", cc):
        raise ValueError("Champ « candidat auto » : identifiant customfield_<numéro> attendu (ex. customfield_10070).")
    if "application" in propre:
        a = propre["application"] or {}
        if a.get("champ") not in CHAMPS_APPLICATION:
            raise ValueError("Champ de l'application : composant, libelle ou personnalise.")
        cj = str(a.get("champ_jira") or "").strip()
        if a["champ"] == "personnalise" and not re.fullmatch(r"customfield_\d+", cj):
            raise ValueError("Champ personnalisé : identifiant customfield_<numéro> attendu (ex. customfield_10050).")
        propre["application"] = {"champ": a["champ"], "champ_jira": cj if a["champ"] == "personnalise" else ""}
    for c in propre.get("champs", []):
        if not c.get("interne") or not c.get("externe"):
            raise ValueError("Chaque correspondance de champ a un champ interne et un champ externe.")
        if c.get("sens") not in SENS:
            raise ValueError(f"Sens inconnu : {c.get('sens')}")
        if re.match(r"^customfield_\d+$", c["externe"]) is None and c["externe"].startswith("customfield"):
            raise ValueError(f"Champ personnalisé Jira mal formé : {c['externe']} (customfield_<numéro>).")
    if propre.get("mode", "A (import)") not in ("A (import)", "B (bidirectionnel)", "C (publication)"):
        raise ValueError("Mode : A (import), B (bidirectionnel) ou C (publication).")
    base = mapping()
    base.update(propre)
    for k in ("modes", "sens_possibles", "statuts_internes", "libelles_revue", "champs_application"):
        base.pop(k, None)
    _ecrire_atomique(_dossier() / "mapping_xray.yaml", yaml.safe_dump(base, allow_unicode=True, sort_keys=False))
    _journaliser("mapping")
    return mapping()


def tester_mapping() -> dict:
    """Champs mappés présents / absents dans l'instantané Xray ; statuts internes sans équivalent."""
    from atelier.intelligence import patrimoine_xray

    pat = patrimoine_xray.charger_vue() or {"tests": []}
    presents = {k for t in pat["tests"] for k, v in t.items() if v not in (None, "", [])}
    m = mapping()
    champs = [{**c, "dans_instantane": bool(c.get("cle_instantane")) and c["cle_instantane"] in presents} for c in m["champs"] if c.get("actif")]
    return {"champs": champs, "non_mappes": sorted(presents - {c.get("cle_instantane") for c in m["champs"]}),
            "statuts_sans_equivalent": [s["interne"] for s in m["statuts"] if not s.get("externe")],
            "tests_analyses": len(pat["tests"])}


# =========================================================================== publication BDD -> Xray (modes C et B)
def _empreinte(texte: str) -> str:
    import hashlib

    return hashlib.sha256(re.sub(r"\s+", " ", texte or "").strip().encode()).hexdigest()[:16]


def gherkin_xray(m: dict) -> str:
    """Définition d'un test Cucumber Xray (1 test = 1 scénario) : étapes du Contexte (Background) puis du scénario
    principal, et tableau Examples d'un Scenario Outline. Aucun élément du scénario principal n'est perdu."""
    from atelier.generation.bdd import MOTS_EN

    p = next((s for s in m["scenarios"] if s["type"] == "principal"), m["scenarios"][0])
    lignes = [f"{MOTS_EN[e['type']]} {e['texte']}" for e in (m.get("contexte") or []) + p["etapes"]]
    if p.get("exemples"):
        lignes += ["", "Examples:"] + [f"  {l}" for l in p["exemples"]]
    return "\n".join(lignes)


def non_publies(m: dict) -> list[str]:
    """Scénarios du fichier qui ne font pas partie du test publié (un test Xray Cucumber = un scénario)."""
    p = next((s for s in m["scenarios"] if s["type"] == "principal"), m["scenarios"][0])
    return [s["nom"] for s in m["scenarios"] if s is not p]


def _publications_xray() -> dict:
    f = _dossier() / "sync_xray.json"
    return json.loads(f.read_text("utf-8")) if f.exists() else {}


def _historiser_sync(objet: str, direction: str, statut: str, resultat: str):
    f = _dossier() / "sync_xray.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": _maintenant(), "auteur": _auteur(), "objet": objet, "direction": direction,
                             "statut": statut, "resultat": resultat}, ensure_ascii=False) + "\n")


def historique_sync(limite: int = 200) -> list[dict]:
    f = _dossier() / "sync_xray.jsonl"
    l = [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()] if f.exists() else []
    return list(reversed(l))[:limite]


def cle_xray_du_scenario(cle: str) -> str:
    """Clé du test Xray d'un scénario BDD : celle créée ou reliée à la publication (sync_xray.json), sinon la clé du
    scénario si elle a la forme d'une clé Xray (scénario créé depuis un test Xray). Vide : pas encore dans Xray."""
    from atelier.integrations.xray import KEY_RE

    publiee = (_publications_xray().get(cle) or {}).get("xray") or ""
    return publiee or (cle if KEY_RE.match(cle or "") else "")


def reporter_cle_xray(cle: str, cle_xray: str) -> list[str]:
    """Après la publication d'un scénario dans Xray : la clé du test Xray remplace la clé locale du scénario dans les
    tags des scripts Robot déjà écrits (seul ce mot de la ligne [Tags] change). Le comportement du test ne change pas :
    une suite approuvée le reste (empreinte reprise) et un test « Vérifié » le reste (date de modification du fichier
    conservée). Renvoie les fichiers modifiés."""
    from atelier.execution.depot_robot import lire_depot
    from atelier.generation import studio

    if not cle_xray or cle_xray == cle:
        return []
    modifies = []
    for rel in sorted({t["fichier"] for t in lire_depot()["tests"].values() if cle in (t.get("tags") or [])}):
        texte = projet.lire_fichier(rel)
        lignes = texte.split("\n")
        for n, ligne in enumerate(lignes):
            if ligne.strip().startswith("[Tags]"):
                mots = re.split(r"(\s{2,}|\t)", ligne)  # séparateurs conservés tels quels
                if cle in mots:
                    lignes[n] = "".join(cle_xray if x == cle else x for x in mots)
        nouveau = "\n".join(lignes)
        if nouveau != texte:
            chemin = projet.safe_path(rel)
            avant = chemin.stat()
            projet.ecrire_fichier(rel, nouveau, True)
            os.utime(chemin, (avant.st_atime, avant.st_mtime))  # tag seul : « Vérifié » reste acquis
            modifies.append(rel)
    if modifies:
        studio.reprendre_empreinte(modifies, f"clé Xray {cle_xray} reportée dans le tag du test (scénario {cle} publié dans Xray)")
        _journaliser("cle_xray_reportee", cle=cle, xray=cle_xray, fichiers=modifies)
    return modifies


def publier_bdd(cle: str, projet_xray: str = "", decision: str = "", xray=None, libelles: list[str] | None = None) -> dict:
    """Mode C : test absent de Xray -> création d'un test Cucumber (clé récupérée et conservée).
    Mode B : test Cucumber existant -> mise à jour du Gherkin, seulement si Xray n'a pas changé depuis la dernière
    synchronisation ; sinon conflit présenté (decision = « local » pour imposer la version locale, « xray » pour
    garder celle de Xray). Un test d'un autre type n'est jamais converti. Chaque échange est historisé.
    libelles : étiquettes Jira posées à la création (mode C), ex. [« banque-demo »]."""
    from atelier.generation import bdd
    from atelier.integrations.xray import KEY_RE, XrayClient

    from atelier.domain import projets

    m = bdd.charger(cle)
    if not m:
        raise KeyError(f"Scénario BDD inconnu : {cle}")
    projet_xray = projet_xray or projets.cle_xray()
    local = gherkin_xray(m)
    sync = _publications_xray()
    st = sync.get(cle)
    xray = xray or XrayClient()
    cible = (st or {}).get("xray") or (cle if KEY_RE.match(cle) else "")
    try:
        return _publier(cle, m, local, sync, st, xray, cible, projet_xray, decision, libelles)
    except ValueError:
        raise  # refus métier ou saisie locale incomplète : déjà historisé ou sans échange avec Xray
    except Exception as e:  # RG-X07 : toute erreur d'échange avec Xray est historisée, puis remontée
        _historiser_sync(cible or cle, "Local → Xray", "Erreur", str(e)[:300])
        raise


def _publier(cle, m, local, sync, st, xray, cible, projet_xray, decision, libelles=None) -> dict:
    existant = xray.lire_gherkin(cible) if cible else None
    if existant:
        if (existant.get("type") or "").lower() not in {"", *noms_gherkin()}:
            _historiser_sync(cible, "Local → Xray", "Refusé", f"test de type {existant['type']} : aucune conversion automatique")
            raise ValueError(f"{cible} est un test {existant['type']} : pas de conversion automatique en test Gherkin.")
        e_xray, e_local = _empreinte(existant["gherkin"]), _empreinte(local)
        modifie_xray = existant["gherkin"].strip() and e_xray != (st or {}).get("empreinte") and e_xray != e_local
        if modifie_xray and decision not in ("local", "xray"):
            _historiser_sync(cible, "Bidirectionnel", "Conflit", "modification externe détectée dans Xray")
            return {"conflit": True, "cle_xray": cible, "local": local, "xray": existant["gherkin"],
                    "message": "Le Gherkin a été modifié dans Xray depuis la dernière synchronisation : choisir la version à conserver."}
        if decision == "xray":
            sync[cle] = {"xray": cible, "issueId": existant["issueId"], "empreinte": e_xray, "date": _maintenant()}
            resultat = "version Xray conservée (le scénario local est à aligner dans Construction BDD)"
            statut = "Conflit résolu"
        elif e_xray == e_local:
            sync[cle] = {"xray": cible, "issueId": existant["issueId"], "empreinte": e_local, "date": _maintenant()}
            resultat, statut = "déjà identique", "Synchronisé"
        else:
            xray.maj_gherkin(existant["issueId"], local)
            sync[cle] = {"xray": cible, "issueId": existant["issueId"], "empreinte": e_local, "date": _maintenant()}
            resultat, statut = "Gherkin mis à jour", "Succès"
        mode = "B (mise à jour)"
    else:
        if not projet_xray:
            raise ValueError("Projet Xray requis pour créer le test (mode C).")
        tg = type_gherkin()  # nom du type Gherkin dans le Xray du projet ; passé seulement s'il diffère du défaut
        r = xray.creer_test_cucumber(projet_xray, m.get("titre") or cle, local, **({"type_test": tg} if tg != "Cucumber" else {}),
                                     **({"libelles": libelles} if libelles else {}))
        cible = r["cle"]
        sync[cle] = {"xray": cible, "issueId": r["issueId"], "empreinte": _empreinte(local), "date": _maintenant()}
        resultat, statut, mode = f"test Gherkin créé ({cible}, type Xray « {tg} »)", "Succès", "C (publication)"
        from atelier.generation import rangement

        dossier = rangement.dossier_xray(m)
        if dossier:  # rangement application / module : un échec laisse le test à la racine, signalé
            try:
                xray.ranger_test(projet_xray, r["issueId"], dossier)
                resultat += f" dans {dossier}"
                sync[cle]["dossier"] = dossier
            except Exception as e:  # noqa: BLE001
                resultat += f" ; rangement dans {dossier} impossible ({str(e)[:160]}) : à ranger dans Xray"
    from atelier.intelligence.strategie import _ecrire_atomique as _ea

    _ea(_dossier() / "sync_xray.json", json.dumps(sync, ensure_ascii=False, indent=1))
    autres = non_publies(m)
    if autres:
        resultat += f" ; {len(autres)} autre(s) scénario(s) non publié(s) dans ce test : {', '.join(autres)}"
    scripts = []
    try:  # la clé Xray arrive dans le code Robot déjà écrit ; un échec ici n'annule pas la publication
        scripts = reporter_cle_xray(cle, cible)
        if scripts:
            resultat += f" ; clé {cible} reportée dans le tag de {', '.join(scripts)} (suite renvoyée en revue technique)"
    except Exception as e:  # noqa: BLE001
        resultat += f" ; report de la clé {cible} dans les scripts Robot impossible ({str(e)[:160]}) : à faire à la main"
    _historiser_sync(cible, "Local → Xray" if decision != "xray" else "Xray → Local", statut, resultat)
    _journaliser("publication_xray", cle=cle, xray=cible, statut=statut)
    return {"conflit": False, "mode": mode, "cle_xray": cible, "statut": statut, "resultat": resultat, "non_publies": autres,
            "scripts_mis_a_jour": scripts}


def statuts_workflow_test(projet: str = "", jira=None) -> dict:
    """Statuts du workflow du type Test (Xray) dans le projet Jira, pour choisir les statuts externes du mapping sans
    les saisir. Lecture seule (GET /rest/api/3/project/{clé}/statuses). Type absent : statuts de tous les types, signalé."""
    import os

    from atelier.domain import projets
    from atelier.integrations.jira import JiraClient

    projet = (projet or mapping().get("projet_jira") or projets.cle_jira()).strip().upper()
    if not projet:
        raise ValueError("Projet Jira requis (champ « Projet Jira » du mapping ou projet actif).")
    jira = jira or JiraClient()
    if not getattr(jira, "enabled", True):
        raise RuntimeError("Jira non configuré (Paramètres › Connexions).")
    types = [t.strip() for t in (os.environ.get("XRAY_TEST_ISSUE_TYPE") or "Test").split(",") if t.strip()]
    data = jira.get(f"/rest/api/3/project/{projet}/statuses") or []
    for it in data:
        if (it.get("name") or "").lower() in {t.lower() for t in types}:
            return {"projet": projet, "type": it["name"], "statuts": [s["name"] for s in it.get("statuses") or []], "type_trouve": True}
    tous = sorted({s["name"] for it in data for s in it.get("statuses") or []})
    return {"projet": projet, "type": types[0], "statuts": tous, "type_trouve": False,
            "types_disponibles": [it.get("name") for it in data]}
