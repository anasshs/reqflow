"""Éditeur de test : explorateur du projet, enregistrement historisé, contrôles (lint, robocop),
propriétés d'une suite (Xray, JDD, requêtes, dernière exécution), réutilisation et impact."""
from __future__ import annotations

import difflib
import shutil
import subprocess
import sys

from atelier.domain import projet

EXTENSIONS = {".robot", ".resource", ".py", ".yaml", ".yml", ".feature", ".json", ".md", ".txt", ".xml", ".cfg", ".toml"}
EXCLUS = {"results", ".mcp_snapshots", ".git", ".venv", "node_modules", "__pycache__", "vignettes"}
TAILLE_MAX = 1_000_000


# =========================================================================== explorateur
def arbre() -> dict:
    """Arborescence des fichiers éditables du projet de tests."""
    racine = projet.PROJECT_DIR

    def noeud(d):
        enfants = []
        for p in sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
            if p.name in EXCLUS or p.name.startswith(".") and p.name not in (".gitlab-ci.yml",):
                continue
            if p.is_symlink():
                continue
            if p.is_dir():
                sous = noeud(p)
                if sous["enfants"]:
                    enfants.append(sous)
            elif p.suffix in EXTENSIONS or p.name in (".gitlab-ci.yml",):
                enfants.append({"nom": p.name, "chemin": str(p.relative_to(racine)), "type": "fichier"})
        return {"nom": d.name, "chemin": str(d.relative_to(racine)) if d != racine else "", "type": "dossier",
                "enfants": enfants}
    return noeud(racine) if racine.exists() else {"nom": "", "chemin": "", "type": "dossier", "enfants": []}


# =========================================================================== enregistrement
def enregistrer(chemin: str, contenu: str, version_lue: str | None = None) -> dict:
    """Écrit un fichier du projet. `version_lue` (contenu chargé dans l'éditeur) protège contre l'écrasement
    d'une modification faite entre-temps sur le disque. Chaque enregistrement est historisé (diff résumé)."""
    from atelier.domain import declarations

    cible = projet.safe_path(chemin)
    if cible.suffix not in EXTENSIONS and cible.name != ".gitlab-ci.yml":
        raise ValueError(f"Type de fichier non éditable : {cible.suffix}")
    if len(contenu.encode()) > TAILLE_MAX:
        raise ValueError("Fichier trop volumineux pour l'éditeur.")
    avant = cible.read_text("utf-8") if cible.exists() else ""
    if version_lue is not None and cible.exists() and avant != version_lue:
        raise FileExistsError(f"{chemin} a été modifié sur le disque depuis son ouverture : recharger avant d'enregistrer.")
    diff = list(difflib.unified_diff(avant.splitlines(), contenu.splitlines(), lineterm="", n=0))
    ajout = sum(1 for x in diff if x.startswith("+") and not x.startswith("+++"))
    retrait = sum(1 for x in diff if x.startswith("-") and not x.startswith("---"))
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(contenu, "utf-8")
    declarations._historiser("edition_fichier", "automaticien", f"fichier:{chemin}",
                             apres={"lignes_ajoutees": ajout, "lignes_retirees": retrait})
    return {"chemin": chemin, "lignes_ajoutees": ajout, "lignes_retirees": retrait, "cree": not avant}


def historique(chemin: str) -> list[dict]:
    from atelier.domain import declarations

    return declarations.historique(f"fichier:{chemin}", 100)


# =========================================================================== contrôles
def lint(contenu: str, chemin: str = "suite.robot") -> dict:
    """Erreurs de syntaxe Robot Framework (parseur officiel), sans exécuter le fichier."""
    import ast
    import io

    from robot.api.parsing import get_model, get_resource_model

    erreurs = []
    est_resource = chemin.endswith(".resource")
    model = (get_resource_model if est_resource else get_model)(io.StringIO(contenu), data_only=False)

    for n in ast.walk(model):  # les nœuds du modèle Robot sont des nœuds ast
        for e in getattr(n, "errors", ()) or ():
            erreurs.append({"ligne": getattr(n, "lineno", 0), "message": str(e), "gravite": "erreur"})
    erreurs += _lint_conventions(contenu)
    return {"ok": not any(e.get("gravite", "erreur") == "erreur" for e in erreurs), "problemes": erreurs}


def _lint_conventions(contenu: str) -> list[dict]:
    """Conventions du produit (CLAUDE.md) vérifiables à la lecture : tags Xray, INITIALISATION."""
    import re

    from atelier.integrations.xray import KEY_RE

    out = []
    lignes = contenu.splitlines()
    section, test, tags, init, debut = "", None, [], False, 0
    tags_suite = []

    def fin_test():
        if test is None:
            return
        if not any(KEY_RE.match(t) for t in tags + tags_suite):
            out.append({"ligne": debut, "message": f"Test « {test} » sans tag de clé Xray.", "gravite": "avertissement"})
        if not init:
            out.append({"ligne": debut, "message": f"Test « {test} » sans bloc INITIALISATION (Initialiser Le Test).",
                        "gravite": "avertissement"})
    for i, brut in enumerate(lignes, 1):
        if brut.startswith("***"):
            fin_test()
            test = None
            section = brut.strip("* ").lower()
            continue
        if section.startswith("setting") and re.match(r"^(Test|Force) Tags\s", brut):
            tags_suite += [t for t in re.split(r"\s{2,}|\t", brut)[1:] if t]
        if not section.startswith("test case"):
            continue
        if brut and not brut[0].isspace() and not brut.startswith("#"):
            fin_test()
            test, tags, init, debut = brut.strip(), [], False, i
        elif test and brut.strip().startswith("[Tags]"):
            tags = [t for t in re.split(r"\s{2,}|\t", brut.strip())[1:] if t]
        elif test and re.match(r"^\s+Initialiser Le Test\b", brut, re.I):
            init = True
    fin_test()
    return out


def robocop(chemin: str) -> dict:
    """robocop (si installé) sur un fichier du projet."""
    cible = projet.safe_path(chemin)
    if not shutil.which("robocop"):
        try:
            import robocop  # noqa: F401
        except ImportError:
            return {"disponible": False, "message": "robocop non installé (pip install robotframework-robocop)."}
    for cmd in ([sys.executable, "-m", "robocop", "check", str(cible)], [sys.executable, "-m", "robocop", str(cible)]):
        r = subprocess.run(cmd, cwd=projet.PROJECT_DIR, capture_output=True, text=True, timeout=120)
        if "No such command" not in r.stderr and "unrecognized" not in r.stderr.lower():
            return {"disponible": True, "code_retour": r.returncode, "sortie": (r.stdout + r.stderr)[-8000:]}
    return {"disponible": True, "code_retour": r.returncode, "sortie": (r.stdout + r.stderr)[-8000:]}


# =========================================================================== propriétés et réutilisation
def proprietes(chemin: str) -> dict:
    """Ce que l'éditeur affiche à côté d'une suite : tests, clés Xray et leur fiche dans l'instantané,
    JDD et requêtes utilisées, derniers statuts, dépendances et autres tests impactés."""
    from atelier.execution import depot_robot, jdd
    from atelier.execution.robot import derniers_resultats
    from atelier.intelligence import patrimoine_xray

    projet.safe_path(chemin)
    inv = depot_robot.lire_depot()
    pat = {t["cle"]: t for t in (patrimoine_xray.charger() or {}).get("tests", [])}
    res = derniers_resultats()
    tests = []
    for tid, t in inv["tests"].items():
        if t["fichier"] != chemin:
            continue
        dep = depot_robot.dependances_test(inv, tid)
        prerequis = []
        for j in dep["jdd"]:
            try:
                for env in jdd.environnements():
                    jeu = next((x for x in jdd.lister(env) if x["jeu"].upper() == j), None)
                    if jeu:
                        prerequis += jeu["prerequis"]
            except Exception:
                pass
        locs = {tuple(x) for x in dep["locators"]}
        autres = sorted({o for o, ot in inv["tests"].items() if o != tid and (
            set(depot_robot.dependances_test(inv, o)["keywords"]) & set(dep["keywords"])
            or {tuple(x) for x in depot_robot.dependances_test(inv, o)["locators"]} & locs)})
        tests.append({"id": tid, "nom": t["nom"], "ligne": t["ligne"], "tags": t["tags"], "plateformes": t["plateformes"],
                      "xray": [{"cle": k, **{c: pat[k].get(c) for c in ("resume", "type", "statut", "criticite", "plans",
                                                                       "executions", "module")}} if k in pat
                               else {"cle": k, "absent_instantane": True} for k in t["cles_xray"]],
                      "jdd": dep["jdd"], "requetes": sorted(set(prerequis)),
                      "keywords": [inv["keywords"][k]["nom"] for k in dep["keywords"]],
                      "locators": [f"{e}.{c}" for e, c in dep["locators"]],
                      "dernier_resultat": res.get(tid),
                      "autres_tests_impactes": [{"id": o, "nom": inv["tests"][o]["nom"],
                                                 "cles_xray": inv["tests"][o]["cles_xray"]} for o in autres]})
    info = inv["fichiers"].get(chemin, {})
    return {"chemin": chemin, "tests": tests, "bibliotheques": info.get("bibliotheques", []),
            "resources": info.get("resources", []), "keywords_definis": [inv["keywords"][k]["nom"] for k in info.get("keywords", [])
                                                                          if k in inv["keywords"]]}


def reutilisation() -> dict:
    """Keywords (avec nombre d'appels dans le dépôt), locators et fichiers resource réutilisables."""
    from atelier.execution import depot_robot

    inv = depot_robot.lire_depot()
    appels: dict = {}
    for b in list(inv["tests"].values()) + list(inv["keywords"].values()):
        for a in b["appels"]:
            k = depot_robot.cle_appel(a)
            if k in inv["keywords"]:
                appels[k] = appels.get(k, 0) + 1
    return {"keywords": sorted(({"nom": k["nom"], "fichier": k["fichier"], "ligne": k["ligne"], "documentation": k["doc"],
                                 "appels": appels.get(kid, 0)} for kid, k in inv["keywords"].items()),
                               key=lambda x: (-x["appels"], x["nom"])),
            "locators": sorted(({"id": lid, "ecran": l["ecran"], "cle": l["cle"], "plateforme": l["plateforme"],
                                 "valeur": l["valeur"], "fichier": l["fichier"]} for lid, l in inv["locators"].items()),
                               key=lambda x: x["id"]),
            "resources": sorted(f for f in inv["fichiers"] if f.endswith(".resource"))}
