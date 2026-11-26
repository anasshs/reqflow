"""Publier au TNR : un geste pour passer des scénarios vérifiés au plan de non-régression de l'application dans Xray.

Conventions réglées une fois par application (fiche de l'application, clé « tnr ») :
  etiquette   étiquette Jira de chaque test publié (défaut : nom de l'application en minuscules, tirets : « banque-demo »)
  dossier     dossier du Test Repository Xray (défaut : « /<nom de l'application> ») ; les modules en sont des sous-dossiers
  plan        clé du Test Plan TNR de l'application (créé à la première publication s'il est vide)
  campagne    identifiant de la campagne TNR de l'Execution Center (créée à la première publication)

Publier au TNR, pour des scénarios BDD : découpage en un scénario par test (un test Xray Cucumber = un scénario),
publication (création ou mise à jour du Gherkin) avec l'étiquette et dans le dossier, ajout des tests au plan TNR,
campagne mise à jour (tests du plan). Chaque exécution de la campagne crée une Test Execution dans ce plan.
Les liens avec les exigences Jira ne sont pas gérés ici (étape ultérieure, jamais bloquante).
"""
from __future__ import annotations

import re

from atelier.domain import projet


def _app() -> dict:
    from atelier.discovery import carte

    return carte.config_app()


def _etiquette_defaut(nom: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", projet.slug(nom or "application", 40, "application").lower()).strip("-")


def conventions() -> dict:
    """Conventions TNR de l'application active (valeurs par défaut si rien n'est réglé)."""
    app = _app()
    t = app.get("tnr") or {}
    dossiers = (app.get("tests_xray") or {}).get("dossiers") or []
    return {"application": app.get("nom", ""), "slug": app.get("slug", ""),
            "etiquette": t.get("etiquette") or _etiquette_defaut(app.get("nom", "")),
            "dossier": t.get("dossier") or (dossiers[0] if dossiers else "/" + (app.get("nom") or "").strip()),
            "plan": t.get("plan", ""), "campagne": t.get("campagne", ""),
            "champs_plan": t.get("champs_plan") or {}, "champs_execution": t.get("champs_execution") or {},
            "transition_debut": t.get("transition_debut", ""), "transition_fin": t.get("transition_fin", ""),
            "plateformes": [p for p in app.get("plateformes") or [] if p in ("web", "android", "ios", "api")]}


def regler(etiquette: str | None = None, dossier: str | None = None, plan: str | None = None, campagne: str | None = None,
           champs_plan: dict | None = None, champs_execution: dict | None = None,
           transition_debut: str | None = None, transition_fin: str | None = None) -> dict:
    """Règle les conventions TNR de l'application active (seuls les champs donnés changent).
    champs_plan / champs_execution : champs Jira posés sur le Test Plan créé / chaque Test Execution du TNR,
    {id: {"valeur", "type", "items", "nom"}} ; une valeur vide retire le champ. transition_debut / _fin : transition Jira
    de la Test Execution au début du run (ex. « En cours d'exécution ») et à la fin (ex. « Terminé »)."""
    from atelier.discovery import carte

    app = _app()
    t = dict(app.get("tnr") or {})
    if etiquette is not None:
        if " " in etiquette.strip():
            raise ValueError("Une étiquette Jira ne peut pas contenir d'espace.")
        t["etiquette"] = etiquette.strip()
    if dossier is not None:
        t["dossier"] = "/" + dossier.strip().strip("/") if dossier.strip() else ""
    if plan is not None:
        if plan.strip() and not re.fullmatch(r"[A-Z][A-Z0-9_]+-\d+", plan.strip().upper()):
            raise ValueError(f"Clé de Test Plan invalide : {plan}")
        t["plan"] = plan.strip().upper()
    if campagne is not None:
        t["campagne"] = campagne.strip()
    for cle, val in (("champs_plan", champs_plan), ("champs_execution", champs_execution)):
        if val is not None:
            t[cle] = {k: v for k, v in val.items() if isinstance(v, dict) and str(v.get("valeur") or "").strip()}
    for cle, val in (("transition_debut", transition_debut), ("transition_fin", transition_fin)):
        if val is not None:
            t[cle] = val.strip()
    champs = {"tnr": t}
    if t.get("dossier"):  # le rangement Xray (generation/rangement.py) lit le dossier de l'application ici
        champs["tests_xray"] = {**(app.get("tests_xray") or {}), "dossiers": [t["dossier"]]}
    carte.maj_app(**champs)
    return conventions()


def valeur_jira(c: dict):
    """Valeur au format de l'API Jira selon le type du champ : option, version(s), utilisateur, texte, nombre."""
    v, typ, items = str(c.get("valeur") or "").strip(), c.get("type", ""), c.get("items", "")
    if typ == "option":
        return {"value": v}
    if typ == "array" and items == "option":
        return [{"value": x.strip()} for x in v.split(",") if x.strip()]
    if typ == "array" and items == "version" or typ == "version":
        return [{"name": x.strip()} for x in v.split(",") if x.strip()] if typ == "array" else {"name": v}
    if typ == "array" and items == "string":
        return [x.strip() for x in v.split(",") if x.strip()]
    if typ == "number":
        return float(v)
    return v


def payload_champs(champs: dict) -> dict:
    return {k: valeur_jira(c) for k, c in (champs or {}).items() if str(c.get("valeur") or "").strip()}


def champs_jira() -> dict:
    """Champs Jira proposables pour le Test Plan et la Test Execution du TNR, avec leurs valeurs autorisées, et les
    transitions de la Test Execution (lues sur la dernière exécution du plan TNR si elle existe). Lecture seule."""
    from atelier.domain import projets
    from atelier.integrations.jira import JiraClient

    projet_xray = projets.cle_xray()
    j = JiraClient()
    if not j.enabled:
        raise ValueError("Jira non configuré (Paramètres › Connexions).")
    exclus = {"summary", "project", "issuetype", "reporter", "description", "attachment", "issuelinks", "labels", "assignee"}
    garder = lambda l: [c for c in l if c["id"] not in exclus]  # noqa: E731
    out = {"plan": garder(j.champs_type(projet_xray, "Test Plan")), "execution": garder(j.champs_type(projet_xray, "Test Execution")),
           "transitions": [], "conventions": conventions()}
    # statuts du workflow de la Test Execution : une transition peut viser un statut par son nom (JiraClient.transition)
    try:
        out["statuts"] = j.statuts_projet(projet_xray, "Test Execution")
    except Exception:  # noqa: BLE001
        out["statuts"] = []
    derniere = _derniere_execution()
    if derniere:
        out["transitions"] = [{"nom": x.get("transition"), "vers": x.get("statut_cible")} for x in j.transitions(derniere)]
        out["execution_exemple"] = derniere
    return out


def _derniere_execution() -> str:
    """Clé de la dernière Test Execution créée par un run de la campagne TNR (bilans des runs de l'atelier)."""
    from atelier.execution import historique

    conv = conventions()
    for r in historique.lister(50):
        if (r.get("campagne") or "") == conv["campagne"] and r.get("xray"):
            return r["xray"]
    return ""


def _appliquer_champs_plan(cle: str) -> list[str]:
    """Pose les champs Jira réglés sur le Test Plan (jamais bloquant : un refus est rendu en avertissement)."""
    from atelier.integrations.jira import JiraClient

    champs = payload_champs(conventions()["champs_plan"])
    if not champs:
        return []
    try:
        JiraClient().maj_champs(cle, champs)
        return []
    except Exception as e:  # noqa: BLE001
        return [f"Champs du plan {cle} non posés : {str(e)[:200]}"]


def _assurer_plan(conv: dict, cles_tests: list[str], xray) -> dict:
    """Plan TNR de l'application : créé s'il n'existe pas, sinon complété avec les tests publiés."""
    from atelier.domain import projets

    ids = xray.test_ids(cles_tests) if cles_tests else {}
    if not conv["plan"]:
        projet_xray = projets.cle_xray()
        if not projet_xray:
            raise ValueError("Projet Xray inconnu (Paramètres › Projets).")
        _, cle = xray.create_plan(projet_xray, f"TNR {conv['application']}".strip(), list(ids.values()))
        regler(plan=cle)
        return {"plan": cle, "cree": True, "ajoutes": sorted(ids), "avertissements": _appliquer_champs_plan(cle)}
    info = xray.resolve(conv["plan"])
    if info.get("type") != "plan":
        raise ValueError(f"{conv['plan']} n'est pas un Test Plan (type {info.get('type')}).")
    if ids:
        xray.add_tests_to_plan(info["issueId"], list(ids.values()))
    return {"plan": conv["plan"], "cree": False, "ajoutes": sorted(ids)}


def _assurer_campagne(conv: dict, cles_tests: list[str]) -> dict:
    """Campagne TNR de l'Execution Center liée au plan : créée au premier passage, puis ses tests sont complétés."""
    from atelier.execution import centre, jdd

    existante = next((c for c in centre.campagnes() if c["id"] == conv["campagne"]), None) if conv["campagne"] else None
    envs = jdd.environnements()
    base = existante or {"nom": f"TNR {conv['application']}".strip(), "type": "TNR",
                         "description": f"Non-régression {conv['application']} : tests publiés au TNR depuis l'atelier.",
                         "plateformes": conv["plateformes"][:1] or ["android"], "environnement": envs[0] if len(envs) == 1 else "",
                         "cible": f"tests/{conv['slug']}" if conv["slug"] else "tests", "priorite": "High", "mode_execution": "nouvelle"}
    tests = sorted(set(base.get("tests") or []) | set(cles_tests))
    l = centre.enregistrer_campagne({**base, "tests": tests, "plan_xray": conv["plan"]})
    c = next(x for x in l if x["nom"] == base["nom"]) if not existante else next(x for x in l if x["id"] == existante["id"])
    if not conv["campagne"]:
        regler(campagne=c["id"])
    return {"campagne": c["id"], "nom": c["nom"], "tests": len(c["tests"]), "creee": existante is None}


def publier(cles_bdd: list[str], xray=None, campagne: bool = True) -> dict:
    """Publier au TNR des scénarios BDD. Écriture externe (Jira / Xray) : à n'appeler que sur décision de
    l'automaticien (bouton de l'atelier, ou demande validée quand l'agent la propose)."""
    from atelier.generation import bdd, conception
    from atelier.integrations.xray import XrayClient

    if not cles_bdd:
        raise ValueError("Choisir au moins un scénario.")
    conv = conventions()
    if conv["dossier"]:
        regler(dossier=conv["dossier"])  # rangement Xray aligné sur la convention
    xray = xray or XrayClient()
    publies, erreurs, cles_xray = [], [], []
    for cle in cles_bdd:
        try:
            for c in bdd.separer_scenarios(cle):
                r = conception.publier_bdd(c, xray=xray, libelles=[conv["etiquette"]] if conv["etiquette"] else None)
                if r.get("conflit"):
                    erreurs.append({"scenario": c, "erreur": r.get("message", "conflit avec Xray")})
                    continue
                k = conception.cle_xray_du_scenario(c)
                cles_xray.append(k)
                publies.append({"scenario": c, "xray": k, "resultat": r.get("resultat", "")})
        except Exception as e:  # noqa: BLE001 - un scénario en erreur n'empêche pas les autres
            erreurs.append({"scenario": cle, "erreur": str(e)[:300]})
    plan = _assurer_plan(conventions(), cles_xray, xray) if cles_xray else None
    camp = _assurer_campagne(conventions(), cles_xray) if (cles_xray and campagne) else None
    return {"publies": publies, "erreurs": erreurs, "plan": plan, "campagne": camp, "conventions": conventions()}


# =========================================================================== choix du plan TNR
def _tests_tnr() -> list[str]:
    """Clés Xray des tests au TNR de l'application : ceux de sa campagne TNR."""
    from atelier.execution import centre

    conv = conventions()
    c = next((x for x in centre.campagnes() if x["id"] == conv["campagne"]), None) if conv["campagne"] else None
    return list((c or {}).get("tests") or [])


def plans_disponibles(recherche: str = "", xray=None, limite: int = 200) -> dict:
    """Test Plans du projet Xray (ouverts d'abord, les plus récents en tête), filtrés par texte ; le plan TNR actuel
    est signalé. Lecture seule."""
    from atelier.domain import projets
    from atelier.integrations.xray import XrayClient

    projet_xray = projets.cle_xray()
    if not projet_xray:
        raise ValueError("Projet Xray inconnu (Paramètres › Projets).")
    xray = xray or XrayClient()
    plans = xray.conteneurs(projet_xray, limite=limite, seulement=("plans",)).get("plans") or []
    r = (recherche or "").strip().lower()
    actuel = conventions()["plan"]
    out = [{"cle": p["cle"], "resume": p.get("resume", ""), "statut": p.get("statut", ""), "ferme": bool(p.get("ferme")),
            "tests": p.get("tests_total") if p.get("tests_total") is not None else len(p.get("tests") or []),
            "cree": p.get("cree", ""), "actuel": p["cle"] == actuel}
           for p in plans if p.get("cle") and (not r or r in p["cle"].lower() or r in (p.get("resume") or "").lower())]
    out = sorted(out, key=lambda p: p["cree"], reverse=True)
    out.sort(key=lambda p: (not p["actuel"], p["ferme"]))  # stable : plan actuel, puis ouverts, chacun du plus récent au plus ancien
    return {"projet": projet_xray, "actuel": actuel, "plans": out}


def choisir_plan(cle: str, xray=None) -> dict:
    """Fait d'un Test Plan existant le plan TNR de l'application : les tests au TNR y sont ajoutés, la campagne le suit
    (chaque run y crée sa Test Execution). Écriture Xray : décision de l'automaticien."""
    from atelier.integrations.xray import XrayClient

    cle = (cle or "").strip().upper()
    xray = xray or XrayClient()
    info = xray.resolve(cle)
    if info.get("type") != "plan":
        raise ValueError(f"{cle} n'est pas un Test Plan (type {info.get('type')}).")
    regler(plan=cle)
    tests = _tests_tnr()
    ids = xray.test_ids(tests) if tests else {}
    if ids:
        xray.add_tests_to_plan(info["issueId"], list(ids.values()))
    camp = _assurer_campagne(conventions(), []) if conventions()["campagne"] or tests else None
    return {"plan": cle, "cree": False, "ajoutes": sorted(ids), "campagne": camp, "conventions": conventions(),
            "avertissements": _appliquer_champs_plan(cle)}


def creer_plan(nom: str = "", xray=None) -> dict:
    """Crée un nouveau Test Plan TNR (résumé donné, sinon « TNR <application> ») avec les tests au TNR, et en fait le
    plan de l'application ; la campagne le suit. Écriture Xray : décision de l'automaticien."""
    from atelier.domain import projets
    from atelier.integrations.xray import XrayClient

    projet_xray = projets.cle_xray()
    if not projet_xray:
        raise ValueError("Projet Xray inconnu (Paramètres › Projets).")
    xray = xray or XrayClient()
    conv = conventions()
    tests = _tests_tnr()
    ids = xray.test_ids(tests) if tests else {}
    _, cle = xray.create_plan(projet_xray, (nom or "").strip() or f"TNR {conv['application']}".strip(), list(ids.values()))
    regler(plan=cle)
    camp = _assurer_campagne(conventions(), []) if conventions()["campagne"] or tests else None
    return {"plan": cle, "cree": True, "ajoutes": sorted(ids), "campagne": camp, "conventions": conventions(),
            "avertissements": _appliquer_champs_plan(cle)}


def finaliser_execution(cle: str, transitions: list[str] | None = None, joindre: str = "") -> dict:
    """Applique à une Test Execution existante les champs Jira réglés (environnement, build…) puis les transitions
    données (ex. [« En cours d'exécution », « Terminé »]) : pour une exécution créée avant le réglage des conventions,
    ou rejouée. Jamais bloquant : chaque refus de Jira est rendu."""
    from atelier.integrations.jira import JiraClient

    cle = (cle or "").strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]+-\d+", cle):
        raise ValueError(f"Clé invalide : {cle}")
    j = JiraClient()
    if not j.enabled:
        raise ValueError("Jira non configuré (Paramètres › Connexions).")
    faits, erreurs = [], []
    champs = payload_champs(conventions()["champs_execution"])
    if champs:
        try:
            j.maj_champs(cle, champs)
            faits.append(f"champs : {', '.join(conventions()['champs_execution'][k].get('nom') or k for k in champs)}")
        except Exception as e:  # noqa: BLE001
            erreurs.append(f"champs : {str(e)[:200]}")
    for t in transitions if transitions is not None else [conventions()["transition_debut"], conventions()["transition_fin"]]:
        if not t:
            continue
        try:
            faits.append(f"statut : {j.transition(cle, t)}")
        except Exception as e:  # noqa: BLE001
            erreurs.append(f"transition « {t} » : {str(e)[:200]}")
    if joindre:  # log total d'un run (archive des résultats) joint au ticket, chemin dans le projet de tests
        try:
            j.joindre(cle, str(projet.safe_path(joindre)))
            faits.append(f"pièce jointe : {joindre.rsplit('/', 1)[-1]}")
        except Exception as e:  # noqa: BLE001
            erreurs.append(f"pièce jointe : {str(e)[:200]}")
    return {"execution": cle, "faits": faits, "erreurs": erreurs}
