"""Automation Studio : comment automatiser (cahier des charges « Module Automation Studio »).

S'appuie sur l'existant sans le dupliquer : dépôt Robot (keywords, locators &{LOC_<ECRAN>_<PLAT>}),
carte de l'application (écrans observés), scénarios BDD, JDD, Knowledge Graph central.
Métadonnées propres au studio, dans le projet de tests :
  studio/revues_scripts.json   revue technique de chaque suite (empreinte du contenu approuvé)
  studio/espaces.yaml          espaces d'automatisation (périmètres techniques du projet)
  studio/journal.jsonl         historique des opérations
Principe : l'IA propose, l'automaticien valide ; aucune modification silencieuse d'un fichier.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import shutil
from datetime import datetime

import yaml

from atelier.domain import projet
from atelier.intelligence.strategie import _auteur, _ecrire_atomique, _maintenant

STATUTS_REVUE = ["Generated", "Technical Review", "Changes Requested", "Approved", "Published", "Rejected"]
LIBELLES_REVUE = {"Generated": "Généré / non revu", "Technical Review": "Revue technique", "Changes Requested": "Modifications demandées",
                  "Approved": "Approuvé", "Published": "Publié (Execution Center)", "Rejected": "Refusé"}
TRANSITIONS = {"soumettre": (("Generated", "Changes Requested", "Rejected"), "Technical Review"),
               "demander_modifications": (("Technical Review",), "Changes Requested"),
               "refuser": (("Generated", "Technical Review", "Changes Requested"), "Rejected"),  # script écarté, justifié
               "approuver": (("Technical Review",), "Approved"), "publier": (("Approved",), "Published")}
SECRET = re.compile(r"(?i)\b(password|passwd|mot_de_passe|mdp|token|secret|api[_-]?key)\b\s*[=:]\s*(?!\$\{|\{\{env:)[^\s$]{4,}")
ASSERTION = re.compile(r"(?i)^(then|alors|et|and)\b|should|doit|vérifier|verifier|le texte doit")


def _dossier():
    return projet.PROJECT_DIR / "studio"


def _journaliser(op: str, **d):
    f = _dossier() / "journal.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": _maintenant(), "auteur": _auteur(), "op": op, **d}, ensure_ascii=False) + "\n")


def journal(limite: int = 200) -> list[dict]:
    f = _dossier() / "journal.jsonl"
    l = [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()] if f.exists() else []
    return list(reversed(l))[:limite]


def _inv():
    from atelier.execution.depot_robot import lire_depot

    return lire_depot()


# =========================================================================== Locators Repository
def fiabilite(valeur: str) -> tuple[str, str]:
    """(stratégie, niveau) : stable (identifiant technique), fiable (css / rôle / prédicat), fragile (texte, xpath)."""
    v = valeur.strip()
    strat = "xpath" if v.startswith("//") else v.split("=", 1)[0] if "=" in v else "css"
    if strat in ("id", "accessibility_id", "data-testid", "resource-id"):
        return strat, "Stable"
    if strat == "xpath" or strat == "text" or re.search(r":nth|\[\d+\]", v):
        return strat, "Fragile"
    return strat, "Reliable"


def locators() -> list[dict]:
    """Locators du dépôt + fiabilité + état (obsolète si l'écran est cartographié mais l'élément absent,
    manquant si référencé sans être défini) + utilisations + secours."""
    from atelier.discovery import carte

    inv = _inv()
    usages: dict = {}
    for k in inv["keywords"].values():
        for ec, cle in k.get("locators") or []:
            usages[(ec, cle)] = usages.get((ec, cle), 0) + 1
    observes: dict = {}  # (écran, plateforme) -> valeurs observées dans la carte
    try:
        racine = carte._racine() / (carte.app_courante() or "") / "ecrans"
        for f in racine.glob("*.yaml") if racine.exists() else []:
            d = yaml.safe_load(f.read_text("utf-8")) or {}
            for el in (d.get("elements") or {}).values():
                for plat, vals in (el.get("locators") or {}).items():
                    observes.setdefault((d.get("nom") or d.get("id"), plat), set()).update(vals or [])
    except Exception:
        pass
    verifs = {j["locator"]: j for j in reversed(journal(1000)) if j["op"] == "verification_locator"}
    out = []
    for lid, l in inv["locators"].items():
        strat, niveau = fiabilite(l["valeur"])
        cle_obs = (l["ecran"], l["plateforme"])
        etat = niveau
        if cle_obs in observes and l["valeur"] not in observes[cle_obs]:
            etat = "Obsolete"
        out.append({**l, "strategie": strat, "fiabilite": niveau, "etat": etat, "utilisations": usages.get((l["ecran"], l["cle"]), 0),
                    "ecran_cartographie": cle_obs in observes, "derniere_verification": verifs.get(lid)})
    definis = {(l["ecran"], l["cle"]) for l in inv["locators"].values()}
    for (ec, cle), n in usages.items():
        if (ec, cle) not in definis:
            out.append({"id": f"{ec}.{cle}@?", "ecran": ec, "cle": cle, "plateforme": "", "valeur": "", "secours": [], "fichier": "",
                        "strategie": "", "fiabilite": "", "etat": "Missing", "utilisations": n, "ecran_cartographie": False, "derniere_verification": None})
    return sorted(out, key=lambda x: (x["ecran"], x["cle"], x["plateforme"]))


def noter_verification(locator_id: str, resultat: dict) -> dict:
    """Résultat d'un test de locator sur le device / navigateur (check_locator), journalisé."""
    e = {"locator": locator_id, "trouve": bool(resultat.get("nb_trouves")), "nb": resultat.get("nb_trouves", 0)}
    _journaliser("verification_locator", **e)
    return e


# =========================================================================== Keywords Repository
def keywords() -> list[dict]:
    from atelier.execution.depot_robot import BIBLIOTHEQUES_UI, nom_bibliotheque, normaliser

    inv = _inv()
    appelants: dict = {}
    for src in list(inv["keywords"].values()) + list(inv["tests"].values()):
        for k in src.get("keywords") or []:
            appelants[k] = appelants.get(k, 0) + 1
    noms: dict = {}
    for k in inv["keywords"].values():
        noms.setdefault(normaliser(k["nom"]), []).append(k["fichier"])
    libs_fichier = {f: i.get("bibliotheques", []) for f, i in inv["fichiers"].items()}
    out = []
    for kid, k in inv["keywords"].items():
        libs = libs_fichier.get(k["fichier"], [])
        out.append({"id": kid, "nom": k["nom"], "fichier": k["fichier"], "ligne": k["ligne"], "documentation": k.get("doc", ""),
                    "categorie": k["fichier"].rsplit("/", 1)[-1].rsplit(".", 1)[0], "utilisations": appelants.get(kid, 0),
                    "dependances": k.get("keywords", []) + k.get("externes", []), "locators": [f"{e}.{c}" for e, c in k.get("locators") or []],
                    "jdd": k.get("jdd", []), "plateformes": sorted({p for lib in libs for p in BIBLIOTHEQUES_UI.get(nom_bibliotheque(lib), [])}),
                    "doublon": len(noms[normaliser(k["nom"])]) > 1, "inutilise": appelants.get(kid, 0) == 0,
                    "wrapper_1_1": len(k.get("externes", [])) == 1 and not k.get("keywords") and len(k.get("locators") or []) == 1})
    return sorted(out, key=lambda x: (x["categorie"], x["nom"]))


# =========================================================================== Page Objects
def page_objects() -> list[dict]:
    """Par écran : clés métier et valeurs par plateforme ; clés absentes sur une plateforme déclarée."""
    ecrans: dict = {}
    for l in locators():
        if l["etat"] == "Missing":
            continue
        e = ecrans.setdefault(l["ecran"], {"ecran": l["ecran"], "plateformes": {}, "fichiers": set()})
        e["plateformes"].setdefault(l["plateforme"], {})[l["cle"]] = {"valeur": l["valeur"], "etat": l["etat"]}
        e["fichiers"].add(l["fichier"])
    out = []
    for e in ecrans.values():
        toutes = set().union(*[set(v) for v in e["plateformes"].values()])
        e["incoherences"] = {p: sorted(toutes - set(v)) for p, v in e["plateformes"].items() if toutes - set(v)}
        e["cles"] = sorted(toutes)
        e["fichiers"] = sorted(e["fichiers"])
        out.append(e)
    return sorted(out, key=lambda x: x["ecran"])


# =========================================================================== frameworks et Git
def frameworks() -> dict:
    from atelier.execution.centre import runner_local

    r = runner_local()
    outils = {o: bool(shutil.which(o)) for o in ("node", "adb", "xcrun", "appium", "robocop", "git")}
    lignes = [("Web", "Robot Framework + Browser Library", "Browser", ["node"]), ("Web (démo)", "Robot Framework + Playwright (NavigateurDemo)", "Playwright", []),
              ("Android", "Robot Framework + AppiumLibrary", "AppiumLibrary", ["adb", "appium"]),
              ("iOS", "Robot Framework + AppiumLibrary (macOS)", "AppiumLibrary", ["xcrun", "appium"]),
              ("API", "Robot Framework + RequestsLibrary", "RequestsLibrary", [])]
    return {"runner": r, "outils": outils, "frameworks": [
        {"type": t, "technologie": tech, "version": r["bibliotheques"].get(lib, ""), "robot": r["bibliotheques"]["Robot Framework"],
         "prerequis": {o: outils.get(o, False) for o in req},
         "disponible": bool(r["bibliotheques"].get(lib)) and all(outils.get(o, False) for o in req)} for t, tech, lib, req in lignes]}


def git() -> dict:
    from atelier.execution.centre import _git

    if not _git("rev-parse", "--is-inside-work-tree"):
        return {"depot": False, "message": "Le projet de tests n'est pas un dépôt Git (lecture seule ici ; commit et merge request : phase 7)."}
    log = _git("log", "-15", "--date=iso-strict", "--format=%h%x1f%an%x1f%ad%x1f%s")
    return {"depot": True, "branche": _git("rev-parse", "--abbrev-ref", "HEAD"), "commit": _git("rev-parse", "--short", "HEAD"),
            "distant": _git("remote", "get-url", "origin").split("@")[-1],  # jamais d'identifiant dans l'URL affichée
            "branches": [b.strip("* ").strip() for b in _git("branch", "--list").splitlines()],
            "modifications": [x for x in _git("status", "--porcelain").splitlines() if x],
            "commits": [dict(zip(("hash", "auteur", "date", "message"), x.split("\x1f"))) for x in log.splitlines() if x]}


# =========================================================================== revue technique des scripts
def _empreinte(fichier: str) -> str:
    return hashlib.sha256(projet.safe_path(fichier).read_bytes()).hexdigest()[:16]


def _stock() -> dict:
    f = _dossier() / "revues_scripts.json"
    return json.loads(f.read_text("utf-8")) if f.exists() else {}


def revues_scripts() -> dict:
    """Statut de revue de chaque suite ; un fichier modifié après approbation revient en revue technique."""
    st = _stock()
    out = {}
    for f in _inv()["suites"]:
        r = dict(st.get(f) or {"statut": "Generated", "historique": []})
        r["en_workflow"] = f in st  # entré en revue (généré par l'atelier ou soumis) ; sinon patrimoine existant
        r["modifie_depuis_validation"] = False
        if r["statut"] in ("Approved", "Published") and r.get("empreinte") != _empreinte(f):
            r["statut"], r["modifie_depuis_validation"] = "Technical Review", True
        out[f] = r
    return out


def entrer_en_revue(fichier: str, origine: str) -> dict:
    """Un script généré par l'atelier (Builder, BDD) entre en revue technique à l'état « Generated » :
    il ne pourra être exécuté (hors dry-run) qu'une fois approuvé, ou par dérogation justifiée."""
    projet.safe_path(fichier)
    st = _stock()
    r = st.setdefault(fichier, {"statut": "Generated", "historique": []})
    r["statut"] = "Generated"
    r.pop("empreinte", None)
    r["historique"].append({"date": _maintenant(), "auteur": _auteur(), "de": "", "vers": "Generated",
                            "commentaire": f"généré ({origine})"})
    _ecrire_atomique(_dossier() / "revues_scripts.json", json.dumps(st, ensure_ascii=False, indent=1))
    _journaliser(f"generation_{origine}", fichier=fichier)
    return r


def renvoyer_en_revue(fichiers: list[str], motif: str) -> list[str]:
    """Suites touchées par une modification du socle (locator corrigé, keywords factorisés) : de nouveau en revue
    technique, même si leur propre fichier n'a pas changé. Renvoie les suites renvoyées."""
    st = _stock()
    renvoyees = []
    for f in sorted(set(fichiers)):
        r = st.setdefault(f, {"statut": "Generated", "historique": []})
        if r["statut"] == "Technical Review":
            continue
        r["historique"].append({"date": _maintenant(), "auteur": _auteur(), "de": r["statut"], "vers": "Technical Review", "commentaire": motif})
        r["statut"] = "Technical Review"
        r.pop("empreinte", None)
        renvoyees.append(f)
    if renvoyees:
        _ecrire_atomique(_dossier() / "revues_scripts.json", json.dumps(st, ensure_ascii=False, indent=1))
        _journaliser("renvoi_en_revue", fichiers=renvoyees, commentaire=motif)
    return renvoyees


def controles_script(fichier: str) -> list[dict]:
    from atelier.execution.depot_robot import fermeture_keywords
    from atelier.generation import editeur

    inv = _inv()
    contenu = projet.safe_path(fichier).read_text("utf-8")
    out = []
    add = lambda code, g, m: out.append({"code": code, "gravite": g, "message": m})  # noqa: E731
    tests = [t for t in inv["tests"].values() if t["fichier"] == fichier]
    sans_cle = [t["nom"] for t in tests if not t.get("cles_xray")]
    add("xray", "haute" if sans_cle else "ok", f"Clé Xray absente : {', '.join(sans_cle)}" if sans_cle else "Clé Xray conservée sur chaque test.")
    lint = editeur.lint(contenu, fichier)
    add("conventions", "haute" if any(p.get("gravite") == "erreur" for p in lint["problemes"]) else "moyenne" if lint["problemes"] else "ok",
        "; ".join(p["message"] for p in lint["problemes"][:4]) or "Syntaxe et conventions respectées.")
    sec = SECRET.findall(contenu)
    add("secrets", "haute" if sec else "ok", "Valeur sensible en clair dans le script." if sec else "Aucun secret en clair.")
    sans_ass = [t["nom"] for t in tests if not any(ASSERTION.search(a) for a in t["appels"])]
    add("assertions", "moyenne" if sans_ass else "ok", f"Sans assertion visible : {', '.join(sans_ass)}" if sans_ass else "Chaque test vérifie un résultat.")
    directs = sorted({a for t in tests for a in t["appels"] if a not in [inv["keywords"][k]["nom"] for k in t["keywords"] if k in inv["keywords"]]
                      and not re.match(r"(?i)^(given|when|then|and|but|log|set test variable)\b", a)})
    add("reutilisation", "moyenne" if directs else "ok", f"Appels hors socle dans les tests : {', '.join(directs[:5])}" if directs else "Les tests n'appellent que des keywords du socle.")
    fiab = {f"{l['ecran']}.{l['cle']}": l for l in locators()}
    kws = fermeture_keywords(inv, [k for t in tests for k in t["keywords"]])
    utilises = {f"{e}.{c}" for k in kws if k in inv["keywords"] for e, c in inv["keywords"][k].get("locators") or []}
    fragiles = sorted(u for u in utilises if (fiab.get(u) or {}).get("etat") in ("Fragile", "Obsolete", "Missing"))
    add("locators", "moyenne" if fragiles else "ok", f"Locators fragiles / obsolètes : {', '.join(fragiles)}" if fragiles else "Locators stables ou fiables.")
    sans_jdd = [t["nom"] for t in tests if not t.get("jdd")]
    add("donnees", "basse" if sans_jdd else "ok", f"Sans jeu de données : {', '.join(sans_jdd)}" if sans_jdd else "Données via JDD.")
    return out


def _version_approuvee(fichier: str):
    return _dossier() / "versions" / (fichier.replace("/", "__") + ".approuve")


def dernier_run(fichier: str) -> dict | None:
    """Dernier run (réel ou dry run) qui couvrait cette suite, et s'il est postérieur à la dernière modification."""
    from atelier.execution import historique

    cible = projet.safe_path(fichier)
    for r in historique.lister(200):
        t = (r.get("suite") or "").rstrip("/")
        if t and (t == fichier or fichier.startswith(t + "/")):
            apres = bool(r.get("debut")) and datetime.fromisoformat(r["debut"][:19]).timestamp() >= cible.stat().st_mtime
            return {**{k: r.get(k) for k in ("id", "debut", "statut", "passes", "echecs", "dry_run")}, "apres_modification": apres}
    return None


def revue_script(fichier: str) -> dict:
    import difflib

    from atelier.generation import sessions_agent

    projet.safe_path(fichier)
    r = revues_scripts().get(fichier)
    if r is None:
        raise KeyError(f"Suite inconnue : {fichier}")
    v = _version_approuvee(fichier)
    diff = ""
    if v.exists():
        avant, apres = v.read_text("utf-8").splitlines(), projet.safe_path(fichier).read_text("utf-8").splitlines()
        diff = "\n".join(list(difflib.unified_diff(avant, apres, "version approuvée", "version actuelle", lineterm="", n=2))[:400])
    run = dernier_run(fichier)
    return {**r, "fichier": fichier, "controles": controles_script(fichier), "version_approuvee": v.exists(), "diff_version_approuvee": diff,
            "dernier_run": run, "run_valide": bool(run and run["apres_modification"] and run["statut"] == "réussi"),
            "session_agent": sessions_agent.session_du_script(r.get("historique"))}


def transition_script(fichier: str, action: str, commentaire: str = "", derogation: str = "") -> dict:
    if action not in TRANSITIONS:
        raise ValueError(f"Action inconnue : {action}")
    from atelier.domain import roles

    roles.exiger({"soumettre": "soumettre_revue", "publier": "publier"}.get(action, "decider_revue"))
    actuel = revue_script(fichier)
    depuis, vers = TRANSITIONS[action]
    if action == "approuver" and roles.quatre_yeux():
        soumis = next((h for h in reversed(actuel.get("historique") or []) if h.get("vers") == "Technical Review"), None)
        if soumis and soumis.get("auteur") == roles.utilisateur():
            raise PermissionError("Quatre yeux : un script ne s'approuve pas par la personne qui l'a soumis.")
    if actuel["statut"] not in depuis:
        raise ValueError(f"« {action} » impossible depuis {LIBELLES_REVUE[actuel['statut']]}.")
    if action == "demander_modifications" and not commentaire.strip():
        raise ValueError("Préciser les modifications demandées.")
    if action == "refuser" and not commentaire.strip():
        raise ValueError("Un refus doit être justifié.")
    if action in ("approuver", "publier"):
        bloquants = [c["message"] for c in actuel["controles"] if c["gravite"] == "haute"]
        if bloquants:
            raise ValueError("Contrôles bloquants : " + " ; ".join(bloquants))
    if action == "approuver" and not actuel["run_valide"]:
        if len(derogation.strip()) < 10:
            raise ValueError("Approbation : lancer d'abord un dry run (ou un run) réussi de la suite depuis sa dernière modification, "
                             "ou justifier une dérogation (10 caractères au moins).")
        commentaire = (commentaire + " · " if commentaire.strip() else "") + f"dérogation (sans run réussi) : {derogation.strip()}"
    st = _stock()
    r = st.setdefault(fichier, {"statut": "Generated", "historique": []})
    r["historique"].append({"date": _maintenant(), "auteur": _auteur(), "de": actuel["statut"], "vers": vers, "commentaire": commentaire.strip()})
    r["statut"] = vers
    if vers in ("Approved", "Published"):
        r["empreinte"] = _empreinte(fichier)  # toute modification ultérieure renvoie en revue
        v = _version_approuvee(fichier)  # base de l'écart affiché à la prochaine revue
        v.parent.mkdir(parents=True, exist_ok=True)
        v.write_text(projet.safe_path(fichier).read_text("utf-8"), "utf-8")
    _ecrire_atomique(_dossier() / "revues_scripts.json", json.dumps(st, ensure_ascii=False, indent=1))
    _journaliser("revue_script", fichier=fichier, action=action, de=actuel["statut"], vers=vers, commentaire=commentaire.strip())
    return revue_script(fichier)


# =========================================================================== BDD to Automation
def _corps(k: dict) -> str:
    """Lignes d'un keyword (de sa définition jusqu'à la prochaine ligne non indentée)."""
    lignes = projet.safe_path(k["fichier"]).read_text("utf-8").splitlines()[k["ligne"]:]
    corps = []
    for l in lignes:
        if l and not l[0].isspace():
            break
        corps.append(l)
    return "\n".join(corps)


def mapping_bdd(cle: str) -> dict:
    """Correspondance de chaque étape BDD avec le socle : keyword existant ou à créer, locators, données, assertion."""
    from atelier.execution.depot_robot import cle_appel, fermeture_keywords
    from atelier.generation import bdd

    m = bdd.charger(cle)
    if not m:
        raise KeyError(f"Scénario BDD inconnu : {cle}")
    inv = _inv()
    par_cle = {cle_appel(k["nom"]): kid for kid, k in inv["keywords"].items()}
    fiab = {f"{l['ecran']}.{l['cle']}": l["etat"] for l in locators()}
    scenarios = []
    for s in m["scenarios"]:
        etapes = []
        for e in s["etapes"]:
            kid = par_cle.get(cle_appel(e["texte"])) or par_cle.get(cle_appel(re.sub(r"^(que|qu')\s*", "", e["texte"])))
            k = inv["keywords"].get(kid) if kid else None
            locs = sorted({f"{ec}.{c}" for x in fermeture_keywords(inv, [kid]) if x in inv["keywords"] for ec, c in inv["keywords"][x].get("locators") or []}) if kid else []
            etapes.append({"id": e["id"], "mot": e.get("mot") or e["type"], "texte": e["texte"], "keyword": k["nom"] if k else "",
                           "fichier": f"{k['fichier']}:{k['ligne']}" if k else "", "statut": "existant" if k else "à créer",
                           "locators": [{"id": x, "etat": fiab.get(x, "Missing")} for x in locs],
                           "donnees": sorted({d for x in fermeture_keywords(inv, [kid]) if x in inv["keywords"]
                                              for d in re.findall(r"\$\{DONNEES\.(\w+)\}", _corps(inv["keywords"][x]))}) if kid else [],
                           "assertion": e["type"] == "then", "valide": e.get("valide", False),
                           "proprietes": {x: e.get(x) for x in ("ecran", "locator", "jdd", "assertion") if e.get(x)}})
        scenarios.append({"id": s["id"], "nom": s["nom"], "type": s["type"], "etapes": etapes})
    tot = [e for s in scenarios for e in s["etapes"]]
    return {"cle": cle, "titre": m.get("titre", ""), "jdd": m.get("jdd", ""), "statut_bdd": m.get("statut", ""), "scenarios": scenarios,
            "existants": sum(e["statut"] == "existant" for e in tot), "a_creer": sum(e["statut"] == "à créer" for e in tot)}


# =========================================================================== espaces d'automatisation
def espaces() -> list[dict]:
    f = _dossier() / "espaces.yaml"
    return (yaml.safe_load(f.read_text("utf-8")) or []) if f.exists() else []


def enregistrer_espace(e: dict) -> list[dict]:
    if not (e.get("nom") or "").strip():
        raise ValueError("Nom de l'espace obligatoire.")
    plats = e.get("plateformes") or []
    if not plats:
        raise ValueError("Au moins une plateforme.")
    projet.safe_path(e.get("repertoire") or "tests")
    propre = {"id": e.get("id") or f"ESP-{secrets.token_hex(3).upper()}", "nom": e["nom"].strip(), "application": e.get("application", ""),
              "plateformes": plats, "framework": e.get("framework", ""), "depot_git": e.get("depot_git", ""),
              "repertoire": e.get("repertoire") or "tests", "convention": e.get("convention", ""), "statut": e.get("statut", "Actif")}
    l = espaces()
    i = next((k for k, x in enumerate(l) if x["id"] == propre["id"]), None)
    l.append(propre) if i is None else l.__setitem__(i, propre)
    _ecrire_atomique(_dossier() / "espaces.yaml", yaml.safe_dump(l, allow_unicode=True, sort_keys=False))
    _journaliser("espace", id=propre["id"], nom=propre["nom"])
    return espaces()


# =========================================================================== vue d'ensemble
def vue_ensemble() -> dict:
    from atelier.execution import historique
    from atelier.generation import bdd

    inv = _inv()
    locs, kws, rev = locators(), keywords(), revues_scripts()
    try:
        from atelier.intelligence import strategie

        plan = strategie.plan_automatisation()
    except Exception:
        plan = []
    auto = [c for c in plan if c["automatise"]]
    runs = historique.lister(5)
    gen = [j for j in journal(500) if j["op"].startswith("generation")]
    out = {"kpi": {"scenarios_bdd": len(bdd.lister()), "candidats": sum(not c["automatise"] for c in plan),
                    "tests_automatises": len(inv["tests"]), "en_revue": sum(r["statut"] == "Technical Review" for r in rev.values()),
                    "approuves": sum(r["statut"] in ("Approved", "Published") for r in rev.values()),
                    "locators_a_corriger": sum(l["etat"] in ("Obsolete", "Missing") for l in locs),
                    "keywords": len(kws), "couverture_automatisee": round(100 * len(auto) / len(plan), 1) if plan else None,
                    "derniere_generation": gen[0]["date"] if gen else None, "derniere_execution": runs[0]["debut"] if runs else None},
            "locators_par_etat": {e: sum(l["etat"] == e for l in locs) for e in ("Stable", "Reliable", "Fragile", "Obsolete", "Missing")},
            "scripts_par_statut": {s: sum(r["statut"] == s for r in rev.values()) for s in STATUTS_REVUE},
            "tests_par_plateforme": {p: sum(p in t.get("plateformes", []) for t in inv["tests"].values()) for p in ("web", "android", "ios")},
            "keywords_reutilisation": {"réutilisés (2+)": sum(k["utilisations"] >= 2 for k in kws), "utilisés une fois": sum(k["utilisations"] == 1 for k in kws),
                                       "inutilisés": sum(k["inutilise"] for k in kws)},
            "activite": journal(10)}
    from atelier.generation import studio_avance

    try:
        studio_avance.relever_tendance(out)  # un relevé réel par jour : les courbes ne sont jamais reconstituées
    except OSError:
        pass
    out["tendance"] = studio_avance.tendance()
    from atelier.domain import roles

    out["roles"] = roles.etat()
    return out


# =========================================================================== Git en écriture (local, encadré)
BRANCHES_PROTEGEES = ("main", "master", "develop", "production")


def creer_branche(nom: str) -> dict:
    from atelier.execution.centre import _git

    if not re.fullmatch(r"[A-Za-z0-9._/-]{3,80}", nom or "") or nom in BRANCHES_PROTEGEES or ".." in nom:
        raise ValueError("Nom de branche invalide ou protégé.")
    if not _git("rev-parse", "--is-inside-work-tree"):
        raise RuntimeError("Le projet de tests n'est pas un dépôt Git.")
    import subprocess

    r = subprocess.run(["git", "-C", str(projet.PROJECT_DIR), "switch", "-c", nom], capture_output=True, text=True, timeout=15)
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[:300])
    _journaliser("git_branche", nom=nom)
    return git()


def commit(message: str, fichiers: list[str]) -> dict:
    from atelier.domain import roles

    roles.exiger("commit_local")
    return _commit(message, fichiers)


def _commit(message: str, fichiers: list[str]) -> dict:
    """Commit local des seuls fichiers donnés, jamais sur une branche protégée ; chaque suite .robot doit être
    approuvée ou publiée en revue technique. Aucun push : la publication passe par une merge request (phase 7)."""
    import subprocess

    from atelier.execution.centre import _git

    branche = _git("rev-parse", "--abbrev-ref", "HEAD")
    if not branche:
        raise RuntimeError("Le projet de tests n'est pas un dépôt Git.")
    if branche in BRANCHES_PROTEGEES:
        raise PermissionError(f"Commit refusé sur la branche protégée « {branche} » : créer une branche de travail.")
    if not message.strip() or not fichiers:
        raise ValueError("Message et fichiers obligatoires.")
    rev = revues_scripts()
    non_valides = [f for f in fichiers if f.endswith(".robot") and (rev.get(f) or {}).get("statut") not in ("Approved", "Published")]
    if non_valides:
        raise PermissionError("Revue technique non approuvée : " + ", ".join(non_valides))
    for f in fichiers:
        projet.safe_path(f)
    base = ["git", "-C", str(projet.PROJECT_DIR)]
    r = subprocess.run(base + ["add", "--", *fichiers], capture_output=True, text=True, timeout=30)
    if r.returncode == 0:
        r = subprocess.run(base + ["commit", "-m", message.strip(), "--", *fichiers], capture_output=True, text=True, timeout=30)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300])
    _journaliser("git_commit", branche=branche, fichiers=", ".join(fichiers))
    return git()


# =========================================================================== GitLab : merge request encadrée
EXECUTIONS_STABLES = 3  # invariant 5 : 3 exécutions stables ET revue humaine


def gitlab_etat() -> dict:
    """Connexion GitLab du projet actif (utilisateur, projet, branche par défaut) et MR ouvertes pour la branche courante."""
    from atelier.execution.centre import _git
    from atelier.integrations import gitlab

    if not gitlab.configure():
        return {"configure": False, "message": "GitLab non configuré : URL et projet dans Paramètres › Projets, jeton d'accès personnel "
                                               "dans la variable désignée (GITLAB_TOKEN par défaut)."}
    try:
        c = gitlab.GitLabClient()
        branche = _git("rev-parse", "--abbrev-ref", "HEAD")
        return {"configure": True, "utilisateur": c.utilisateur(), "projet": c.projet_info(), "branche": branche,
                "mr_ouvertes": c.mr_ouvertes(branche) if branche and branche not in BRANCHES_PROTEGEES else []}
    except Exception as e:  # noqa: BLE001 - GitLab indisponible : affiché, jamais bloquant pour le reste
        return {"configure": True, "erreur": str(e)[:400]}


def gitlab_commits(jours: int = 14, chemin: str = "") -> list[dict]:
    from datetime import datetime, timedelta

    from atelier.integrations.gitlab import GitLabClient

    depuis = (datetime.now().astimezone() - timedelta(days=max(1, int(jours)))).isoformat(timespec="seconds")
    return GitLabClient().commits(depuis=depuis, chemin=chemin)


def _stabilite_suites(fichiers: list[str]) -> dict:
    """Pour chaque suite : ses tests et leurs dernières exécutions réelles (au moins 3, toutes PASS = stable)."""
    from atelier.intelligence import gouvernance

    inv = _inv()
    seq = {t["test"]: t["sequence"] for t in gouvernance.stabilite()["tests"]}
    out = {}
    for f in fichiers:
        tests = [t["nom"] for t in inv["tests"].values() if t["fichier"] == f]
        detail = {n: (seq.get(n) or [])[-EXECUTIONS_STABLES:] for n in tests}
        out[f] = {"tests": detail, "stable": bool(tests) and all(len(s) == EXECUTIONS_STABLES and set(s) == {"PASS"} for s in detail.values())}
    return out


def _git_env_push(url_distant: str) -> dict:
    """Environnement du « git push » : le jeton GitLab passe par la configuration Git en variables d'environnement
    (GIT_CONFIG_*), jamais dans la ligne de commande, l'URL, un fichier ou un log. Distant SSH : clés de l'utilisateur."""
    import base64
    import os

    from atelier.integrations.http import variable_secrete

    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    ca = os.environ.get("GITLAB_CA_BUNDLE") or os.environ.get("XRAY_CA_BUNDLE")
    if ca:
        env["GIT_SSL_CAINFO"] = ca
    jeton = variable_secrete("GITLAB_TOKEN")
    if url_distant.startswith("https://") and jeton:
        entete = "Authorization: Basic " + base64.b64encode(f"oauth2:{jeton}".encode()).decode()
        n = int(env.get("GIT_CONFIG_COUNT") or 0)  # s'ajoute à une configuration Git déjà passée par l'environnement
        env.update({"GIT_CONFIG_COUNT": str(n + 1), f"GIT_CONFIG_KEY_{n}": "http.extraHeader", f"GIT_CONFIG_VALUE_{n}": entete})
    return env


def proposer_mr(titre: str, description: str = "", cible: str = "", derogation: str = "", gitlab_client=None) -> dict:
    from atelier.domain import roles

    roles.exiger("merge_request")
    return _proposer_mr(titre, description, cible, derogation, gitlab_client)


def _proposer_mr(titre: str, description: str = "", cible: str = "", derogation: str = "", gitlab_client=None) -> dict:
    """Pousse la branche de travail et crée une merge request GitLab, jamais une fusion.
    Conditions : branche non protégée ; chaque suite .robot modifiée approuvée / publiée en revue technique (humaine)
    ET stable sur ses 3 dernières exécutions réelles, sauf dérogation justifiée (journalisée et écrite dans la MR).
    La description reprend fichiers, revues, stabilité et tests Xray concernés."""
    import os
    import subprocess

    from atelier.execution.centre import _git
    from atelier.integrations.gitlab import GitLabClient

    branche = _git("rev-parse", "--abbrev-ref", "HEAD")
    if not branche:
        raise RuntimeError("Le projet de tests n'est pas un dépôt Git.")
    if branche in BRANCHES_PROTEGEES or branche == "HEAD":
        raise PermissionError(f"Merge request impossible depuis « {branche} » : créer une branche de travail.")
    if not titre.strip():
        raise ValueError("Titre de la merge request obligatoire.")
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Modifications locales non validées : faire le commit (suites approuvées) avant la merge request.")
    c = gitlab_client or GitLabClient()
    info = c.projet_info()
    cible = cible or info.get("branche_defaut") or "main"
    deja = c.mr_ouvertes(branche)
    if deja:
        return {"deja_ouverte": True, "mr": deja[0]}
    _git("fetch", "--quiet", "origin", cible)
    base = _git("merge-base", "HEAD", f"origin/{cible}") or _git("merge-base", "HEAD", cible)
    fichiers = [f for f in _git("diff", "--name-only", f"{base}..HEAD" if base else "HEAD~1..HEAD").splitlines() if f]
    if not fichiers:
        raise ValueError(f"Aucun changement entre « {branche} » et « {cible} ».")
    suites = [f for f in fichiers if f.endswith(".robot")]
    rev = revues_scripts()
    non_revues = [f for f in suites if (rev.get(f) or {}).get("statut") not in ("Approved", "Published")]
    if non_revues:
        raise PermissionError("Revue technique non approuvée : " + ", ".join(non_revues))
    stab = _stabilite_suites(suites)
    instables = [f for f, x in stab.items() if not x["stable"]]
    if instables and len(derogation.strip()) < 10:
        raise PermissionError(f"Moins de {EXECUTIONS_STABLES} exécutions réelles stables pour : {', '.join(instables)}. "
                              "Lancer les exécutions, ou proposer la merge request avec une dérogation justifiée.")
    url = _git("remote", "get-url", "origin")
    r = subprocess.run(["git", "-C", str(projet.PROJECT_DIR), "push", "--set-upstream", "origin", f"{branche}:{branche}"],
                       capture_output=True, text=True, timeout=120, env=_git_env_push(url))
    if r.returncode:
        jeton = os.environ.get("GITLAB_TOKEN") or "\x00"
        raise RuntimeError("git push refusé : " + (r.stderr or r.stdout).replace(jeton, "***").strip()[:400])
    inv = _inv()
    cles = sorted({k for t in inv["tests"].values() if t["fichier"] in suites for k in t.get("cles_xray") or []})
    jira = (os.environ.get("JIRA_BASE_URL") or "").rstrip("/")
    lignes = [description.strip(), "", "### Fichiers", *[f"- `{f}`" for f in fichiers], "", "### Revue technique (Automation Studio)"]
    for f in suites:
        h = ((rev.get(f) or {}).get("historique") or [{}])[-1]
        lignes.append(f"- `{f}` : {rev[f]['statut']} par {h.get('auteur', '?')} le {str(h.get('date', ''))[:10]}")
    lignes += ["", f"### Stabilité ({EXECUTIONS_STABLES} dernières exécutions réelles)"]
    for f, x in stab.items():
        lignes.append(f"- `{f}` : {'stable' if x['stable'] else '**non stable**'} — "
                      + "; ".join(f"{n} : {' → '.join(s) or 'aucune exécution'}" for n, s in x["tests"].items()))
    if instables:
        lignes += ["", f"> Dérogation : {derogation.strip()}"]
    if cles:
        lignes += ["", "### Tests Xray", *[f"- [{k}]({jira}/browse/{k})" if jira else f"- {k}" for k in cles]]
    lignes += ["", "_Merge request proposée par l'Atelier d'automatisation : la fusion reste une décision humaine._"]
    mr = c.creer_mr(branche, cible, titre.strip(), "\n".join(lignes).strip(), ["automatisation"])
    _journaliser("gitlab_mr", branche=branche, cible=cible, mr=mr.get("url", ""), derogation=derogation.strip() if instables else "")
    return {"deja_ouverte": False, "mr": mr, "fichiers": fichiers, "stabilite": stab}


# =========================================================================== Builder : test assemblé depuis le socle
def construire_test(nom: str, cle_xray: str, jdd: str, etapes: list[dict], tags: list[str] | None = None, fichier: str = "") -> dict:
    """Assemble un test Robot conforme (INITIALISATION + JDD, Gherkin, tags) à partir de keywords EXISTANTS du socle.
    etapes : [{"mot": "Given|When|Then|And", "keyword": "<nom exact du keyword>"}]. Prévisualisation : aucun fichier écrit."""
    from atelier.execution.depot_robot import KEY_RE, lire_depot, normaliser

    inv = lire_depot()
    par_nom = {normaliser(k["nom"]): k for k in inv["keywords"].values()}
    if not nom.strip() or not etapes:
        raise ValueError("Nom du test et au moins une étape obligatoires.")
    if cle_xray and not KEY_RE.match(cle_xray):
        raise ValueError("Clé Xray invalide.")
    if not re.fullmatch(r"[A-Z0-9_]+", jdd or ""):
        raise ValueError("Jeu de données obligatoire (convention INITIALISATION + &{JDD_<NOM>}).")
    inconnus = [e["keyword"] for e in etapes if e.get("type", "keyword") == "keyword" and normaliser(e.get("keyword", "")) not in par_nom]
    if inconnus:
        raise ValueError("Keywords absents du socle (à créer d'abord) : " + ", ".join(inconnus))
    controle = _lignes_controle(etapes)  # blocs SI / POUR / ESSAYER validés (équilibre, champs sur une ligne)
    mots = {"given": "Given", "when": "When", "then": "Then", "and": "And", "but": "But"}
    kw_etapes = [e for e in etapes if e.get("type", "keyword") == "keyword"]
    if not kw_etapes:
        raise ValueError("Au moins une étape keyword (les blocs seuls ne testent rien).")
    ressources = sorted({par_nom[normaliser(e["keyword"])]["fichier"] for e in kw_etapes} | {par_nom[normaliser("Initialiser Le Test")]["fichier"]}
                        if normaliser("Initialiser Le Test") in par_nom else {par_nom[normaliser(e["keyword"])]["fichier"] for e in kw_etapes})
    fichier = fichier or f"tests/{re.sub(r'[^a-z0-9]+', '_', nom.lower()).strip('_')}.robot"
    profondeur = fichier.count("/")
    lignes = ["*** Settings ***", f"Documentation    {nom} (assemblé dans Automation Studio depuis le socle).",
              *[f"Resource    {'../' * profondeur}{r}" for r in ressources], "", "*** Test Cases ***", nom,
              *([f"    [Tags]    {'    '.join(etiquettes)}"] if (etiquettes := [t for t in [cle_xray, *(tags or [])] if t]) else []), "    # INITIALISATION",
              f"    Initialiser Le Test    &{{JDD_{jdd}}}", "    # SCÉNARIO"]
    for e, (niveau, ligne) in zip(etapes, controle):
        if ligne is None:  # étape keyword, indentée selon les blocs ouverts
            mot = mots.get(str(e.get("mot", "")).lower(), "And")
            args = "".join(f"    {x}" for x in e.get("arguments") or [] if str(x).strip())
            ligne = f"{mot} {par_nom[normaliser(e['keyword'])]['nom']}{args}"
        lignes.append("    " * (niveau + 1) + ligne)
    contenu = "\n".join(lignes) + "\n"
    from atelier.generation import editeur

    return {"fichier": fichier, "contenu": contenu, "lint": editeur.lint(contenu, fichier), "existe": projet.safe_path(fichier).exists()}


TYPES_CONTROLE = {"si": "IF", "sinon_si": "ELSE IF", "sinon": "ELSE", "pour": "FOR", "essayer": "TRY", "echec": "EXCEPT", "finalement": "FINALLY", "fin": "END"}


def _lignes_controle(etapes: list[dict]) -> list[tuple[int, str | None]]:
    """(niveau d'indentation, ligne Robot ou None pour un keyword) pour chaque étape ; blocs Robot 5+ :
    IF / ELSE IF / ELSE / END, FOR … IN / IN RANGE / END, TRY / EXCEPT / FINALLY / END. Vérifie l'équilibre."""
    pile, out = [], []

    def propre(v, nom: str) -> str:
        if re.search(r"[\r\n\t]", str(v)):
            raise ValueError(f"{nom} : une seule ligne, sans tabulation.")
        return str(v).strip()

    for n, e in enumerate(etapes, 1):
        t = e.get("type", "keyword")
        if t == "keyword":
            out.append((len(pile), None))
            continue
        if t not in TYPES_CONTROLE:
            raise ValueError(f"Étape {n} : type inconnu « {t} ».")
        if t == "si":
            cond = propre(e.get("condition", ""), "Condition")
            if not cond:
                raise ValueError(f"Étape {n} : condition du SI obligatoire (ex. ${{DONNEES.type}} == 'externe').")
            out.append((len(pile), f"IF    {cond}"))
            pile.append("si")
        elif t in ("sinon_si", "sinon"):
            if not pile or pile[-1] != "si":
                raise ValueError(f"Étape {n} : {TYPES_CONTROLE[t]} sans SI ouvert.")
            cond = propre(e.get("condition", ""), "Condition") if t == "sinon_si" else ""
            if t == "sinon_si" and not cond:
                raise ValueError(f"Étape {n} : condition du SINON SI obligatoire.")
            out.append((len(pile) - 1, f"ELSE IF    {cond}" if cond else "ELSE"))
        elif t == "pour":
            var, liste = propre(e.get("variable", ""), "Variable"), propre(e.get("liste", ""), "Liste")
            if not re.fullmatch(r"\$\{[A-Za-z_]\w*\}", var) or not liste:
                raise ValueError(f"Étape {n} : POUR attend une variable ${{nom}} et une liste (ex. @{{DONNEES.montants}} ou RANGE 3).")
            m = re.fullmatch(r"(?i)range\s+(.+)", liste)
            out.append((len(pile), f"FOR    {var}    IN RANGE    {m.group(1)}" if m else f"FOR    {var}    IN    {liste}"))
            pile.append("pour")
        elif t == "essayer":
            out.append((len(pile), "TRY"))
            pile.append("essayer")
        elif t in ("echec", "finalement"):
            if not pile or pile[-1] != "essayer":
                raise ValueError(f"Étape {n} : {TYPES_CONTROLE[t]} sans ESSAYER ouvert.")
            motif = propre(e.get("motif", ""), "Motif") if t == "echec" else ""
            out.append((len(pile) - 1, f"EXCEPT    {motif}" if motif else TYPES_CONTROLE[t]))
        else:  # fin
            if not pile:
                raise ValueError(f"Étape {n} : FIN sans bloc ouvert.")
            pile.pop()
            out.append((len(pile), "END"))
    if pile:
        raise ValueError(f"Bloc(s) non fermé(s) : {', '.join(x.upper() for x in pile)} (ajouter FIN).")
    return out


def ecrire_test(construit: dict, origine: str = "builder") -> dict:
    """Écrit le test assemblé (jamais d'écrasement) ; il entre en revue technique à l'état « Generated »."""
    from atelier.domain import roles

    roles.exiger("construire")
    projet.ecrire_fichier(construit["fichier"], construit["contenu"], False)
    entrer_en_revue(construit["fichier"], origine)
    return {"fichier": construit["fichier"], "revue": "Generated"}
