"""Une suite Robot par parcours métier : les tests d'un même parcours sont rangés dans la même suite.

Règle de l'équipe (décision de l'utilisateur du 2026-11-20). Le parcours métier d'un test est le parcours utilisateur
(Discovery › Préparer un parcours) dont une exigence rattachée est couverte par le test. La suite du parcours est :
1. la suite du dépôt qui porte déjà des tests du même parcours (clés Xray en tag) — le test y est AJOUTÉ ;
2. sinon, une nouvelle suite nommée d'après le parcours, rangée selon le motif de Test Design › Réglages.
Un test sans parcours métier garde sa propre suite, comme avant.

Sans relation test ↔ exigence, l'automaticien rattache le test à la main (scénario BDD, `rattacher`) : il choisit le
parcours métier, ou directement une suite existante du dépôt. Ordre de priorité : suite choisie, parcours choisi,
parcours déduit des US, suite propre.

Ajouter n'est jamais réécrire : le contenu existant de la suite est conservé ligne pour ligne (contrôlé), seuls
s'ajoutent les imports manquants, le ou les cas de test en fin de section et les keywords à implémenter. Un test déjà
présent (même nom ou même clé Xray) est refusé. La suite complétée repasse en revue technique.
"""
from __future__ import annotations

import re

_SECTION = re.compile(r"^\*+\s*(settings?|variables?|test cases?|tasks?|keywords?|comments?)\s*\**\s*$", re.I)


def _us_du_test(cle: str) -> set[str]:
    """US couvertes par le test : copie locale Xray, et tests liés suivis par Test Design."""
    from atelier.intelligence import patrimoine_xray, testabilite_us

    us: set = set()
    pat = patrimoine_xray.charger_vue() or {"tests": []}
    for t in pat.get("tests", []):
        if t["cle"] == cle:
            us |= set(t.get("exigences") or [])
    try:
        us |= {u["cle"] for u in testabilite_us._us().values() if cle in (u.get("tests_lies") or [])}
    except Exception:  # noqa: BLE001 — testabilité non configurée
        pass
    return us


def _tests_des_us(us: set[str]) -> set[str]:
    from atelier.intelligence import patrimoine_xray, testabilite_us

    pat = patrimoine_xray.charger_vue() or {"tests": []}
    cles = {t["cle"] for t in pat.get("tests", []) if us & set(t.get("exigences") or [])}
    try:
        cles |= {t for u in testabilite_us._us().values() if u["cle"] in us for t in u.get("tests_lies") or []}
    except Exception:  # noqa: BLE001
        pass
    return cles


def parcours_du_test(cle: str, m: dict | None = None) -> dict | None:
    """Le parcours métier du test : celui désigné par le scénario (« parcours »), sinon le parcours utilisateur qui
    partage le plus d'exigences avec le test (à égalité : le plus récemment modifié). None : aucun."""
    from atelier.discovery import parcours_utilisateur

    try:
        connus = parcours_utilisateur.lister()
    except Exception:  # noqa: BLE001 — aucune application active
        return None
    voulu = (m or {}).get("parcours")
    if voulu:  # choisi à la main : vaut même pour un parcours sans exigence rattachée
        p = next((p for p in connus if voulu in (p["id"], p["nom"])), None)
        if p:
            return {"id": p["id"], "nom": p["nom"], "exigences": list(p.get("exigences") or []), "autres": [], "choisi": True}
    tous = [p for p in connus if p.get("exigences")]
    us = _us_du_test(cle)
    candidats = sorted(((len(us & set(p["exigences"])), n, p) for n, p in enumerate(tous) if us & set(p["exigences"])), key=lambda x: (-x[0], x[1]))
    if not candidats:
        return None
    p = candidats[0][2]
    return {"id": p["id"], "nom": p["nom"], "exigences": list(p["exigences"]), "autres": [c[2]["nom"] for c in candidats[1:]]}


def suite_du_parcours(p: dict, inv: dict, sauf_cle: str = "") -> str:
    """Suite existante du parcours : le fichier .robot qui porte le plus de tests du parcours (hors le test lui-même)."""
    from atelier.generation import bdd, conception

    cles = _tests_des_us(set(p["exigences"]))
    for b in bdd.lister():  # scénarios rattachés à la main au même parcours
        if (bdd.charger(b["cle"]) or {}).get("parcours") in (p["id"], p["nom"]):
            cles |= {b["cle"], conception.cle_xray_du_scenario(b["cle"])} - {""}
    cles -= {sauf_cle, conception.cle_xray_du_scenario(sauf_cle)}
    compte: dict = {}
    for t in inv["tests"].values():
        if cles & set(t.get("cles_xray") or []):
            compte[t["fichier"]] = compte.get(t["fichier"], 0) + 1
    return min(compte, key=lambda f: (-compte[f], f)) if compte else ""


def cible(m: dict, inv: dict) -> dict:
    """Où écrire le test du scénario : {"chemin", "ajout" (la suite existe : on y ajoute), "parcours", "raison"}."""
    from atelier.domain import projet
    from atelier.generation import rangement

    suite = str(m.get("suite") or "").strip().replace("\\", "/")
    if suite and (inv["fichiers"].get(suite) or {}).get("type") == "robot":
        return {"chemin": suite, "ajout": True, "parcours": "", "raison": f"Suite choisie à la main : le test est ajouté à {suite}."}
    perdue = f"La suite choisie ({suite}) n'existe plus dans le dépôt. " if suite else ""
    from atelier.generation import conception

    p = parcours_du_test(conception.cle_xray_du_scenario(m["cle"]) or m["cle"], m)  # les US sont liées au test Xray
    if not p:
        return {"chemin": rangement.chemin_robot(m), "ajout": False, "parcours": "",
                "raison": perdue + "Aucun parcours métier pour ce test (ni choisi, ni déduit de ses US) : il garde sa propre suite. "
                                   "Pour le regrouper, choisir son parcours métier ou une suite existante."}
    origine = "choisi à la main" if p.get("choisi") else "déduit des US du test"
    existante = suite_du_parcours(p, inv, m["cle"])
    if existante:
        return {"chemin": existante, "ajout": True, "parcours": p["nom"],
                "raison": perdue + f"Parcours métier « {p['nom']} » ({origine}) : ajouté à sa suite existante, qui porte déjà des tests du parcours."}
    chemin = rangement.chemin_robot({**m, "titre": p["nom"]})  # la suite porte le nom du parcours
    if projet.safe_path(chemin).exists():
        return {"chemin": chemin, "ajout": True, "parcours": p["nom"], "raison": perdue + f"Parcours métier « {p['nom']} » ({origine}) : ajouté à la suite du parcours."}
    return {"chemin": chemin, "ajout": False, "parcours": p["nom"],
            "raison": perdue + f"Parcours métier « {p['nom']} » ({origine}) : première suite du parcours ; les prochains tests du parcours y seront ajoutés."}


def options(cle: str) -> dict:
    """Pour l'écran : parcours métier et suites existantes où ranger le test, choix enregistré et parcours déduit des US."""
    from atelier.discovery import parcours_utilisateur
    from atelier.execution.depot_robot import lire_depot
    from atelier.generation import bdd

    m = bdd._exiger(cle)
    try:
        parcours = [{"id": p["id"], "nom": p["nom"], "exigences": len(p.get("exigences") or [])} for p in parcours_utilisateur.lister()]
    except Exception:  # noqa: BLE001 — aucune application active
        parcours = []
    inv = lire_depot()
    suites = [{"fichier": f, "tests": len(i["tests"])} for f, i in sorted(inv["fichiers"].items()) if i["type"] == "robot"]
    deduit = parcours_du_test(cle, {})
    return {"parcours": parcours, "suites": suites, "choix": {"parcours": m.get("parcours", ""), "suite": m.get("suite", "")},
            "deduit": (deduit or {}).get("nom", "")}


def rattacher(cle: str, parcours: str = "", suite: str = "") -> dict:
    """Choix de l'automaticien sur le scénario BDD : son parcours métier, ou une suite existante du dépôt (l'un ou l'autre ;
    les deux vides : retour à la déduction par les US). Contrôlé : parcours connu, suite .robot présente dans le dépôt."""
    from atelier.discovery import parcours_utilisateur
    from atelier.execution.depot_robot import lire_depot
    from atelier.generation import bdd

    m = bdd._exiger(cle)
    parcours, suite = str(parcours or "").strip(), str(suite or "").strip().replace("\\", "/")
    if parcours and suite:
        raise ValueError("Choisir un parcours métier OU une suite existante, pas les deux.")
    if parcours:
        p = next((p for p in parcours_utilisateur.lister() if parcours in (p["id"], p["nom"])), None)
        if not p:
            raise KeyError(f"Parcours inconnu : {parcours}.")
        parcours = p["id"]
    if suite and (lire_depot()["fichiers"].get(suite) or {}).get("type") != "robot":
        raise KeyError(f"Suite inconnue dans le dépôt : {suite}.")
    for champ, valeur in (("parcours", parcours), ("suite", suite)):
        if valeur:
            m[champ] = valeur
        else:
            m.pop(champ, None)
    return bdd.sauver(m)


def _sections(texte: str) -> list[tuple[str, list[str]]]:
    """[(nom de section normalisé ou "" pour l'en-tête, lignes — titre compris)] dans l'ordre du fichier."""
    out: list = [("", [])]
    for ligne in texte.splitlines():
        s = _SECTION.match(ligne.strip())
        if s:
            nom = s.group(1).lower().rstrip("s")
            out.append(({"setting": "settings", "variable": "variables", "test case": "tests", "task": "tests", "keyword": "keywords",
                         "comment": "comments"}[nom], [ligne]))
        else:
            out[-1][1].append(ligne)
    return out


def _blocs(lignes: list[str]) -> list[tuple[str, list[str]]]:
    """Cas de test ou keywords d'une section : [(nom, lignes)] ; un nom commence en colonne 0."""
    out: list = []
    for ligne in lignes:
        if ligne.strip() and not ligne[0].isspace() and not ligne.startswith("#"):
            out.append((ligne.strip(), [ligne]))
        elif out:
            out[-1][1].append(ligne)
    return [(n, [x for x in b]) for n, b in out]


def _fin(lignes: list[str]) -> list[str]:
    while lignes and not lignes[-1].strip():
        lignes = lignes[:-1]
    return lignes


def ajouter(suite: str, genere: str) -> dict:
    """Ajoute à une suite existante les cas de test d'une suite générée, sans rien réécrire. Rend {"contenu", "tests",
    "imports", "keywords"}. Refuse un test déjà présent (nom ou clé Xray) et une suite sans section de tests."""
    from atelier.execution.depot_robot import normaliser

    cible_, source = _sections(suite), _sections(genere)
    sec = lambda sections, nom: next((l for n, l in sections if n == nom), None)  # noqa: E731
    tests_c, tests_s = sec(cible_, "tests"), sec(source, "tests")
    if tests_c is None:
        raise ValueError("La suite existante n'a pas de section « *** Test Cases *** » : ajout impossible.")
    nouveaux = _blocs((tests_s or [])[1:])
    if not nouveaux:
        raise ValueError("Aucun cas de test à ajouter.")
    presents = {normaliser(n) for n, _ in _blocs(tests_c[1:])}
    tags_presents = {t for ligne in tests_c for t in re.split(r"\s{2,}|\t", ligne.strip())[1:] if ligne.strip().startswith("[Tags]")}
    for nom, bloc in nouveaux:
        tags = {t for ligne in bloc for t in re.split(r"\s{2,}|\t", ligne.strip())[1:] if ligne.strip().startswith("[Tags]")}
        cles = {t for t in tags & tags_presents if re.fullmatch(r"[A-Z][A-Z0-9]+-\d+", t)}
        if normaliser(nom) in presents or cles:
            raise FileExistsError(f"Le test « {nom} » est déjà dans la suite" + (f" (clé {', '.join(sorted(cles))})" if cles else "") + " : rien n'est ajouté.")
    # imports manquants, dans l'ordre de la suite générée
    reglages_c = sec(cible_, "settings")
    deja = {re.sub(r"\s+", " ", x.strip()) for x in (reglages_c or [])}
    imports = [x for x in (sec(source, "settings") or [])[1:] if re.match(r"(?i)\s*(resource|library|variables)\s{2,}", x) and re.sub(r"\s+", " ", x.strip()) not in deja]
    # keywords à implémenter que la suite ne définit pas déjà
    kw_c = sec(cible_, "keywords")
    connus = {normaliser(n) for n, _ in _blocs((kw_c or [])[1:])}
    keywords = [(n, b) for n, b in _blocs((sec(source, "keywords") or [])[1:]) if normaliser(n) not in connus]

    sortie: list[str] = []
    reglages_faits = False
    for nom, lignes in cible_:
        lignes = list(lignes)
        if nom == "settings" and imports and not reglages_faits:
            corps = _fin(lignes)
            lignes = corps + imports + [""]
            reglages_faits = True
        elif nom == "tests":
            lignes = _fin(lignes) + [x for _, bloc in nouveaux for x in ["", *_fin(list(bloc))]] + [""]
        elif nom == "keywords" and keywords:
            lignes = _fin(lignes) + [x for _, bloc in keywords for x in ["", *_fin(list(bloc))]] + [""]
        sortie += lignes
    if imports and not reglages_faits:  # suite sans section Settings : créée en tête
        sortie = ["*** Settings ***", *imports, "", *sortie]
    if keywords and kw_c is None:
        sortie = _fin(sortie) + ["", "*** Keywords ***"] + [x for n, (_, bloc) in enumerate(keywords) for x in ([""] if n else []) + _fin(list(bloc))]
    contenu = "\n".join(_fin(sortie)) + "\n"
    # garde-fou : chaque ligne non vide de la suite d'origine est conservée, dans l'ordre (ajouter n'est pas réécrire)
    it = iter(x.rstrip() for x in contenu.splitlines())
    perdues = [x for x in (y.rstrip() for y in suite.splitlines() if y.strip()) if not any(x == z for z in it)]
    if perdues:
        raise RuntimeError(f"Ajout abandonné : {len(perdues)} ligne(s) de la suite d'origine ne seraient pas conservées.")
    return {"contenu": contenu, "tests": [n for n, _ in nouveaux], "imports": [x.strip() for x in imports], "keywords": [n for n, _ in keywords]}
