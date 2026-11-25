"""Données des tests : quel jeu de données chaque test Robot utilise, et comment le changer.

Le lien test ↔ jeu est dans le code du test (« Initialiser Le Test    &{JDD_<NOM>} ») et dans le scénario BDD (champ
jdd) ; les valeurs sont dans data/jdd/<environnement>.yaml. Deux façons de changer :
  - pour un run seulement (le dépôt ne change pas) : substitution {jeu: autre jeu} au lancement (TNR, run d'un test,
    MCP run_tests jdd_variantes) ; les tests reçoivent les valeurs de l'autre jeu sous le même nom &{JDD_<jeu>} ;
  - pour toutes les exécutions suivantes (décision de l'utilisateur) : remplacer() change la ligne d'initialisation de
    chaque test concerné et le jeu de son scénario BDD."""
from __future__ import annotations

import re

from atelier.domain import projet

RE_INIT = re.compile(r"^(\s+Initialiser Le Test\s+)&\{JDD_([A-Za-z0-9_]+)\}")


def _jeux_par_test() -> list[dict]:
    """Tests du dépôt avec leur jeu de données (vide : test sans jeu), lus dans les fichiers .robot."""
    from atelier.execution import depot_robot

    inv = depot_robot.lire_depot()
    par_fichier: dict = {}
    for tid in inv["tests"]:
        fichier, _, nom = tid.partition("::")
        par_fichier.setdefault(fichier, []).append(nom)
    out = []
    for fichier, noms in sorted(par_fichier.items()):
        try:
            lignes = projet.safe_path(fichier).read_text("utf-8").splitlines()
        except (OSError, ValueError):
            continue
        jeux, courant, cas = {}, None, False
        for l in lignes:
            if l.startswith("***"):
                cas, courant = "test case" in l.lower(), None
                continue
            if not cas:
                continue
            if l.strip() and not l[:1].isspace():
                courant = l.strip()
                continue
            m = RE_INIT.match(l)
            if m and courant and courant not in jeux:
                jeux[courant] = m.group(2)
        for n in noms:
            tid = f"{fichier}::{n}"
            out.append({"id": tid, "nom": n, "suite": fichier, "jeu": jeux.get(n, ""),
                        "tags": list((inv["tests"].get(tid) or {}).get("tags") or [])})
    return out


def _env(env: str = "") -> str:
    if env:
        return env
    try:
        from atelier.generation import kanban

        return kanban._env() or "recette"
    except Exception:  # noqa: BLE001
        return "recette"


def vue(env: str = "") -> dict:
    """Pour l'environnement (celui de la campagne TNR par défaut) : chaque jeu de données avec ses champs, ses
    variantes et les tests qui l'utilisent ; les tests sans jeu ; les jeux utilisés mais absents du fichier."""
    from atelier.discovery import carte
    from atelier.execution import jdd

    env = _env(env)
    tests = _jeux_par_test()
    try:
        slug = carte.slug(carte.app_courante() or "")
    except Exception:  # noqa: BLE001
        slug = ""
    from atelier.discovery import application

    connus = application.slugs()
    tests = [t for t in tests if application.visible(application.du_chemin(t["suite"], connus), slug, connus)]  # application active
    try:
        jeux = jdd.lister(env)
        variantes = jdd.variantes(env)
    except Exception:  # noqa: BLE001 — fichier absent ou illisible : les liens restent visibles
        jeux, variantes = [], {}
    connus = {j["jeu"] for j in jeux}
    lignes = [{"jeu": j["jeu"], "description": j.get("description", ""), "champs": j.get("champs") or [],
               "variantes": [v["jeu"] for v in variantes.get(j["jeu"], [])],
               "tests": [t for t in tests if t["jeu"] == j["jeu"]]} for j in jeux]
    absents = sorted({t["jeu"] for t in tests if t["jeu"] and t["jeu"] not in connus})
    lignes += [{"jeu": j, "description": f"absent de {env}.yaml", "champs": [], "variantes": [], "absent": True,
                "tests": [t for t in tests if t["jeu"] == j]} for j in absents]
    lignes.sort(key=lambda x: (-len(x["tests"]), x["jeu"]))
    return {"environnement": env, "jeux": lignes, "sans_jeu": [t for t in tests if not t["jeu"]],
            "tests": len(tests), "fichier": f"data/jdd/{env}.yaml"}


def remplacer(ancien: str, nouveau: str, tests: list[str] | None = None) -> dict:
    """Remplacement permanent (décidé par l'utilisateur) : les tests qui utilisent « ancien » (ou seulement ceux
    donnés) passent à « nouveau » dans leur code, et leurs scénarios BDD aussi, pour toutes les exécutions suivantes."""
    from atelier.generation import bdd, lots

    if not ancien or not nouveau or ancien == nouveau:
        raise ValueError("Choisir un jeu de données différent de l'actuel.")
    if not re.fullmatch(r"[A-Za-z0-9_]+", nouveau):
        raise ValueError(f"Nom de jeu invalide : {nouveau}")
    cibles = [t for t in _jeux_par_test() if t["jeu"] == ancien and (not tests or t["id"] in tests)]
    if not cibles:
        raise ValueError(f"Aucun test n'utilise {ancien}.")
    par_fichier: dict = {}
    for t in cibles:
        par_fichier.setdefault(t["suite"], set()).add(t["nom"])
    modifies = []
    for fichier, noms in par_fichier.items():
        f = projet.safe_path(fichier)
        lignes, courant, cas = f.read_text("utf-8").splitlines(keepends=True), None, False
        for i, l in enumerate(lignes):
            if l.startswith("***"):
                cas, courant = "test case" in l.lower(), None
            elif cas and l.strip() and not l[:1].isspace():
                courant = l.strip()
            elif cas and courant in noms:
                m = RE_INIT.match(l)
                if m and m.group(2) == ancien:
                    lignes[i] = l.replace("&{JDD_" + ancien + "}", "&{JDD_" + nouveau + "}", 1)
                    modifies.append(f"{fichier}::{courant}")
        f.write_text("".join(lignes), "utf-8")
    par_bdd, _ = lots._index_tests()
    scenarios = []
    for cle, ts in par_bdd.items():  # le scénario d'un test modifié prend le nouveau jeu (s'il avait l'ancien ou aucun)
        if {t["id"] for t in ts} & set(modifies):
            m = bdd.charger(cle) or {}
            if m.get("jdd", "") in (ancien, ""):
                bdd.associer_jdd(cle, nouveau)
                scenarios.append(cle)
    return {"ancien": ancien, "nouveau": nouveau, "tests_modifies": modifies, "scenarios": sorted(scenarios)}
