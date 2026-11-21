"""Plan de test d'une release dans Xray, et ses Test Executions.

Une release a UN Test Plan Xray. Ses Test Executions viennent des périmètres proposés pour ses builds, découpés par type
(retest, non-régression ciblée, qualification) ou par module fonctionnel, et peuvent être créées AVANT la validation du
périmètre. Chaque exécution porte un environnement de test choisi parmi ceux du projet Xray ; une exécution peut être
dupliquée pour un autre environnement quand le projet en gère plusieurs. Dans Xray, on retrouve donc le plan, ses
exécutions et leurs tests.

Les statuts de test run se mettent à jour depuis l'atelier (updateTestRunStatus) ; ils sont gardés localement avec
l'auteur et la date, et comptent dans les résultats du build (builds.py), avant même la prochaine synchronisation Xray.

Toutes les écritures vers Xray sont des actions explicites du QA. Une erreur Xray est remontée telle quelle, rien n'est
enregistré localement pour une création échouée. Les tests absents de Xray sont signalés et ne sont pas envoyés.
"""
from __future__ import annotations

import re

from atelier.intelligence import releases as R

DECOUPAGES = {"type": "par type de test", "module": "par module fonctionnel", "unique": "une seule exécution"}
STATUTS = ("TO DO", "EXECUTING", "PASSED", "FAILED", "BLOCKED")
_CLE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")


def _xray(xray=None):
    if xray is not None:
        return xray
    from atelier.integrations.xray import XrayClient

    return XrayClient()


def _projet() -> str:
    from atelier.domain import projets

    cle = projets.cle_xray()
    if not cle:
        raise ValueError("Projet Xray inconnu : le déclarer dans Paramètres › Projets (clé du projet Xray).")
    return cle


def environnements() -> list[str]:
    from atelier.integrations.xray import environnements as envs

    return envs.liste()


def _statut_xray(statut: str) -> str:
    """Statut choisi dans l'atelier -> nom du statut de test run dans le projet Xray (table XRAY_STATUTS)."""
    from atelier.execution.journal_xray import statuts_xray

    t = statuts_xray()
    return {"PASSED": t.get("PASS", "PASSED"), "FAILED": t.get("FAIL", "FAILED"), "TO DO": t.get("NOT RUN", "TO DO"),
            "EXECUTING": t.get("EXECUTING", "EXECUTING")}.get(statut, statut)


def _plan(r: dict) -> dict:
    return r.setdefault("plan", {"xray": None, "executions": []})


# =========================================================================== propositions de découpage
def proposer(rid: str, bid: str, decoupage: str = "type") -> list[dict]:
    """Exécutions proposées pour le périmètre d'un build (validé ou seulement proposé) : un groupe par type de test, par
    module, ou un seul groupe. Les tests écartés n'y sont pas ; les tests déjà dans une exécution du build sont signalés."""
    from atelier.intelligence import builds

    if decoupage not in DECOUPAGES:
        raise ValueError(f"Découpage : {', '.join(DECOUPAGES)}.")
    r = R._lire(rid)
    b = R._build(r, bid)
    v = builds.vue(rid, bid)
    tests = [x for x in v["perimetre"] if x["decision"] != "rejetée"]
    deja = {t for x in _plan(r)["executions"] if x["build"] == bid for t in x["tests"]}
    groupes: dict = {}
    for x in tests:
        cle = (x["categorie"] if decoupage == "type" else (x.get("module") or "Sans module") if decoupage == "module" else "tout")
        groupes.setdefault(cle, []).append(x["test"])
    nom = lambda g: (f"{r['nom']} · build {b['numero']} · " + (builds.CATEGORIES.get(g, g) if decoupage == "type" else g if decoupage == "module" else "périmètre"))  # noqa: E731
    ordre = list(builds.CATEGORIES) if decoupage == "type" else sorted(groupes, key=str.lower)
    return [{"groupe": g, "nom": nom(g), "tests": groupes[g], "deja": sorted(set(groupes[g]) & deja)} for g in ordre if g in groupes]


# =========================================================================== écritures Xray
def creer_plan(rid: str, xray=None) -> dict:
    """Crée le Test Plan Xray de la release (une seule fois)."""
    r = R._lire(rid)
    p = _plan(r)
    if p["xray"]:
        raise FileExistsError(f"La release a déjà son Test Plan : {p['xray']['cle']}.")
    x = _xray(xray)
    issue, cle = x.create_plan(_projet(), f"Release {r['nom']}" + (f" ({r['version']})" if r.get("version") and r["version"] not in r["nom"] else ""), [])
    p["xray"] = {"cle": cle, "issueId": issue, "par": R._auteur(), "date": R._maintenant()}
    R._journal(r, "Test Plan créé dans Xray", plan=cle)
    R._ecrire(r)
    return etat(rid)


def creer_executions(rid: str, bid: str, groupes: list[dict], xray=None) -> dict:
    """Crée dans Xray une Test Execution par groupe ({nom, tests, environnement}), avec ses tests et son environnement,
    rattachée au Test Plan de la release (créé au besoin) ; les tests sont aussi ajoutés au plan."""
    r = R._lire(rid)
    b = R._build(r, bid)
    p = _plan(r)
    if not groupes:
        raise ValueError("Aucune exécution à créer.")
    envs = environnements()
    x = _xray(xray)
    projet = _projet()
    if not p["xray"]:
        issue, cle = x.create_plan(projet, f"Release {r['nom']}" + (f" ({r['version']})" if r.get("version") and r["version"] not in r["nom"] else ""), [])
        p["xray"] = {"cle": cle, "issueId": issue, "par": R._auteur(), "date": R._maintenant()}
        R._journal(r, "Test Plan créé dans Xray", plan=cle)
    crees = []
    for g in groupes:
        tests = [t.strip().upper() for t in g.get("tests") or [] if _CLE.match(str(t).strip().upper())]
        env = str(g.get("environnement") or "").strip()
        if not tests:
            continue
        if env and envs and env not in envs:
            raise ValueError(f"Environnement inconnu du projet : {env} (connus : {', '.join(envs)}).")
        ids = x.test_ids(tests)
        if not ids:
            raise ValueError(f"Aucun des tests de « {g.get('nom', '')} » n'existe dans Xray : rien n'est créé pour ce groupe.")
        nom = (str(g.get("nom") or "").strip() or f"{r['nom']} · build {b['numero']}")[:200] + (f" · {env}" if env else "")
        issue, cle = x.create_execution(projet, nom, list(ids.values()), [env] if env else [])
        x.add_execs_to_plan(p["xray"]["issueId"], [issue])
        x.add_tests_to_plan(p["xray"]["issueId"], list(ids.values()))
        n = max([int(e["id"][1:]) for e in p["executions"]] or [0]) + 1
        e = {"id": f"X{n}", "build": bid, "nom": nom, "groupe": str(g.get("groupe") or ""), "environnement": env, "tests": sorted(ids),
             "absents": sorted(set(tests) - set(ids)), "xray": {"cle": cle, "issueId": issue}, "ids_tests": ids, "statuts": {},
             "par": R._auteur(), "date": R._maintenant(), "copie_de": g.get("copie_de", "")}
        p["executions"].append(e)
        crees.append(e)
        R._journal(r, "Test Execution créée dans Xray", build=b["numero"], execution=cle, environnement=env, tests=len(ids))
    if not crees:
        raise ValueError("Aucune exécution créée : groupes sans test.")
    R._ecrire(r)
    return {**etat(rid), "creees": [e["xray"]["cle"] for e in crees]}


def dupliquer(rid: str, xid: str, environnement: str, xray=None) -> dict:
    """Même exécution (mêmes tests) pour un autre environnement du projet : nouvelle Test Execution dans le même plan."""
    r = R._lire(rid)
    e = _execution(r, xid)
    envs = environnements()
    environnement = str(environnement or "").strip()
    if len(envs) < 2:
        raise ValueError("Le projet ne gère pas plusieurs environnements de test : rien à dupliquer.")
    if environnement not in envs:
        raise ValueError(f"Environnement inconnu du projet : {environnement} (connus : {', '.join(envs)}).")
    if any(x["build"] == e["build"] and x["environnement"] == environnement and sorted(x["tests"]) == sorted(e["tests"]) for x in _plan(r)["executions"]):
        raise FileExistsError(f"Ces tests ont déjà une exécution sur {environnement} pour ce build.")
    base = re.sub(r" · [^·]+$", "", e["nom"]) if e["environnement"] else e["nom"]
    return creer_executions(rid, e["build"], [{"nom": base, "tests": e["tests"], "environnement": environnement, "groupe": e["groupe"], "copie_de": e["id"]}], xray)


def _execution(r: dict, xid: str) -> dict:
    e = next((x for x in _plan(r)["executions"] if x["id"] == xid), None)
    if e is None:
        raise KeyError(f"Exécution inconnue : {xid}")
    return e


def maj_statut(rid: str, xid: str, test: str, statut: str, commentaire: str = "", xray=None) -> dict:
    """Met à jour le statut du test run dans Xray depuis l'atelier, puis le garde localement (auteur, date)."""
    r = R._lire(rid)
    e = _execution(r, xid)
    test = str(test or "").strip().upper()
    if statut not in STATUTS:
        raise ValueError(f"Statut : {', '.join(STATUTS)}.")
    if test not in e["tests"]:
        raise KeyError(f"{test} n'est pas dans l'exécution {e['xray']['cle']}.")
    x = _xray(xray)
    issue_test = (e.get("ids_tests") or {}).get(test) or x.test_ids([test]).get(test)
    run = x.test_runs(e["xray"]["issueId"], [issue_test]).get(issue_test) if issue_test else None
    if not run:
        raise RuntimeError(f"Test run introuvable dans Xray pour {test} dans {e['xray']['cle']}.")
    x.set_status(run, _statut_xray(statut))
    if commentaire.strip():
        x.update_run(run, comment=commentaire.strip()[:2000])
    e["statuts"][test] = {"statut": statut, "par": R._auteur(), "date": R._maintenant(), **({"commentaire": commentaire.strip()[:400]} if commentaire.strip() else {})}
    R._journal(r, "statut mis à jour dans Xray", execution=e["xray"]["cle"], test=test, statut=statut)
    R._ecrire(r)
    return etat(rid)


# =========================================================================== lecture
CLASSE = {"PASSED": "reussi", "FAILED": "echec", "BLOCKED": "bloque"}


def statuts_locaux(r: dict, bid: str) -> dict:
    """{test: {"statut", "date", "execution"}} : dernier statut posé depuis l'atelier dans une exécution du build."""
    out: dict = {}
    for e in _plan(r)["executions"]:
        if e["build"] != bid:
            continue
        for t, s in (e.get("statuts") or {}).items():
            if t not in out or s["date"] > out[t]["date"]:
                out[t] = {**s, "execution": e["xray"]["cle"], "environnement": e["environnement"]}
    return out


def etat(rid: str) -> dict:
    """Plan de la release, ses exécutions par build, avec l'avancement des statuts posés depuis l'atelier."""
    r = R._lire(rid)
    p = _plan(r)
    nums = {b["id"]: b["numero"] for b in r.get("builds") or []}
    envs = environnements()
    execs = []
    for e in p["executions"]:
        st = e.get("statuts") or {}
        compte = {s: sum(v["statut"] == s for v in st.values()) for s in STATUTS}
        compte["TO DO"] += len(e["tests"]) - len(st)
        execs.append({**{k: v for k, v in e.items() if k != "ids_tests"}, "build_numero": nums.get(e["build"], e["build"]), "compte": compte,
                      "envs_libres": [x for x in envs if len(envs) > 1 and x != e["environnement"] and not any(
                          y["build"] == e["build"] and y["environnement"] == x and sorted(y["tests"]) == sorted(e["tests"]) for y in p["executions"])]})
    return {"plan": p["xray"], "executions": execs, "environnements": envs, "multi_environnements": len(envs) > 1, "statuts": list(STATUTS),
            "decoupages": DECOUPAGES}
