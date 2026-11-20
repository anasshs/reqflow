"""Éditeur de test : explorateur du projet, enregistrement historisé, contrôles (lint, robocop),
propriétés d'une suite (Xray, JDD, requêtes, dernière exécution), réutilisation et impact."""
from __future__ import annotations

import difflib
import re
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
                enfants.append({"nom": p.name, "chemin": p.relative_to(racine).as_posix(), "type": "fichier"})
        return {"nom": d.name, "chemin": d.relative_to(racine).as_posix() if d != racine else "", "type": "dossier",
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
    structure = None
    if cible.suffix in (".robot", ".resource"):
        try:  # rangé comme le reste du dépôt ? Constat rendu à l'éditeur, jamais bloquant
            from atelier.generation import structure_depot

            structure = structure_depot.controler(chemin, contenu)
        except Exception:  # noqa: BLE001 — un dépôt illisible n'empêche pas d'enregistrer
            structure = None
    return {"chemin": chemin, "lignes_ajoutees": ajout, "lignes_retirees": retrait, "cree": not avant, "structure": structure}


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

    def locale(tous: list[str]) -> tuple[str, str]:
        """(clé locale d'un scénario BDD portée en tag, clé Xray de ce scénario s'il est publié)."""
        try:
            from atelier.generation import bdd, conception

            scenarios = {b["cle"] for b in bdd.lister()}
            t = next((x for x in tous if x in scenarios and not KEY_RE.match(x)), "")
            return t, (conception.cle_xray_du_scenario(t) if t else "")
        except Exception:  # noqa: BLE001 — aucun scénario lisible : contrôle simple
            return "", ""

    def fin_test():
        if test is None:
            return
        if not any(KEY_RE.match(t) for t in tags + tags_suite):
            cle, xray = locale(tags + tags_suite)
            if cle and xray:
                message = f"Test « {test} » : le tag « {cle} » est la clé locale du scénario, publié dans Xray sous {xray} : remplacer le tag par {xray}."
            elif cle:
                message = (f"Test « {test} » : le tag « {cle} » est la clé locale d'un scénario pas encore publié dans Xray. "
                           "Publier le scénario (Scénarios BDD) : la clé Xray remplacera ce tag.")
            else:
                message = f"Test « {test} » sans tag de clé Xray."
            out.append({"ligne": debut, "message": message, "gravite": "avertissement"})
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
        r = subprocess.run(cmd, cwd=projet.PROJECT_DIR, capture_output=True, text=True, errors="replace", timeout=120)
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
    suite = {"revue": "", "parcours": [], "structure": None}
    try:  # où en est la suite : revue technique, parcours métier de ses tests, rangement dans le dépôt
        from atelier.generation import structure_depot, studio, suites_parcours

        suite["revue"] = (studio.revues_scripts().get(chemin) or {}).get("statut", "")
        noms = []
        for t in tests:
            p = next((suites_parcours.parcours_du_test(x["cle"]) for x in t["xray"]), None)
            t["parcours"] = (p or {}).get("nom", "")
            if t["parcours"] and t["parcours"] not in noms:
                noms.append(t["parcours"])
        suite["parcours"] = noms
        suite["structure"] = structure_depot.controler(chemin, "", inv)
    except Exception:  # noqa: BLE001 — information d'appoint : jamais une raison de ne pas afficher la suite
        pass
    return {"chemin": chemin, "tests": tests, "suite": suite, "bibliotheques": info.get("bibliotheques", []),
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


# =========================================================================== aller à la définition (Ctrl + clic)
_VARIABLE = re.compile(r"[$@&%]\{([^{}]+)\}")
_SECTION_ED = re.compile(r"^\*+\s*([A-Za-zé ]+?)\s*\**\s*$")
_IMPORT = re.compile(r"^(Resource|Library|Variables)(\s{2,}|\t)(\S.*?)(\s{2,}|\t|$)", re.I)


def _nom_variable(nom: str) -> str:
    """Nom de variable comparable (règles de Robot : casse, espaces et _ ignorés ; accès « .attribut » retiré)."""
    return re.sub(r"[\s_]+", "", nom.split(".")[0]).casefold()


def _variables_declarees(texte: str) -> list[tuple[str, int]]:
    """Variables de la section *** Variables *** d'un fichier : [(nom comparable, ligne)]."""
    out, section = [], ""
    for n, ligne in enumerate(texte.splitlines(), 1):
        s = _SECTION_ED.match(ligne.strip())
        if s:
            section = s.group(1).lower()
        elif section.startswith("variable"):
            m = _VARIABLE.match(ligne)
            if m:
                out.append((_nom_variable(m.group(1)), n))
    return out


def _keywords_declares(texte: str) -> list[tuple[str, int]]:
    """Keywords de la section *** Keywords *** d'un fichier : [(nom tel qu'écrit, ligne)]."""
    out, section = [], ""
    for n, ligne in enumerate(texte.splitlines(), 1):
        s = _SECTION_ED.match(ligne.strip())
        if s:
            section = s.group(1).lower()
        elif section.startswith("keyword") and ligne.strip() and not ligne[0].isspace() and not ligne.startswith("#"):
            out.append((ligne.strip(), n))
    return out


def _correspond(appel: str, nom: str) -> bool:
    """L'appel désigne-t-il ce keyword ? Même nom (casse, espaces et _ ignorés), ou keyword à arguments intégrés."""
    from atelier.execution.depot_robot import cle_appel, normaliser

    if cle_appel(appel) == normaliser(nom):
        return True
    if "${" not in nom:
        return False
    motif = "".join(".+?" if p.startswith("${") else re.escape(normaliser(p)) for p in re.split(r"(\$\{[^}]*\})", nom) if p)
    return re.fullmatch(motif, cle_appel(appel)) is not None


def definition(chemin: str, contenu: str, ligne: int, colonne: int) -> dict:
    """Où est défini ce qui se trouve sous le curseur (ligne et colonne à partir de 1, dans le contenu affiché, même non
    enregistré) : une variable (${…}, &{…}, @{…}), un keyword appelé, ou un fichier importé (Resource, Library,
    Variables). Cherche d'abord dans le fichier ouvert, puis dans le dépôt. Lecture seule.
    Rend {"trouve", "genre", "nom", "fichier", "ligne", "autres", "message"}."""
    from atelier.execution import depot_robot

    lignes = contenu.splitlines()
    if not 1 <= ligne <= len(lignes):
        return {"trouve": False, "message": "Rien sous le curseur."}
    texte, col = lignes[ligne - 1], max(0, colonne - 1)
    rien = lambda genre, nom, message: {"trouve": False, "genre": genre, "nom": nom, "message": message}  # noqa: E731
    ok = lambda genre, nom, lieux: {"trouve": True, "genre": genre, "nom": nom, "fichier": lieux[0][0], "ligne": lieux[0][1],  # noqa: E731
                                    "autres": [{"fichier": f, "ligne": n} for f, n in lieux[1:6]], "message": ""}

    # 1. fichier importé
    imp = _IMPORT.match(texte.strip())
    if imp and not texte[:1].isspace():
        cible = imp.group(3).strip()
        try:
            rel = (projet.safe_path(chemin).parent / cible).resolve().relative_to(projet.PROJECT_DIR).as_posix()
        except ValueError:
            return rien("fichier", cible, f"{cible} est hors du projet.")
        if projet.safe_path(rel).is_file():
            return ok("fichier", cible, [(rel, 1)])
        return rien("fichier", cible, f"{cible} : bibliothèque ou fichier absent du projet (aucune définition à ouvrir).")

    # 2. variable sous le curseur
    for m in _VARIABLE.finditer(texte):
        fin = m.end()
        while fin < len(texte) and texte[fin] == "[":  # accès ${dico}[cle] : fait partie de la même référence
            f2 = texte.find("]", fin)
            if f2 < 0:
                break
            fin = f2 + 1
        if m.start() <= col < fin:
            nom, cle = m.group(0), _nom_variable(m.group(1))
            lieux = [(chemin, n) for v, n in _variables_declarees(contenu) if v == cle]
            # variable locale : argument ou affectation plus haut dans le même test / keyword
            debut = next((i for i in range(ligne - 1, -1, -1) if lignes[i].strip() and not lignes[i][0].isspace()), 0)
            for i in range(debut, ligne - 1):
                l = lignes[i].strip()
                if l.startswith("[Arguments]") or re.match(r"^(FOR\s|[$@&]\{[^}]+\}\s*=?(\s{2,}|\t))", l):
                    if any(_nom_variable(v.group(1).split("=")[0]) == cle for v in _VARIABLE.finditer(l.split("    IN")[0] if l.startswith("FOR") else
                                                                                                    (l if l.startswith("[Arguments]") else re.split(r"\s{2,}|\t", l)[0]))):
                        lieux.append((chemin, i + 1))
            if not lieux:
                inv = depot_robot.lire_depot()
                for rel in sorted(inv["fichiers"]):
                    if rel != chemin:
                        try:
                            lieux += [(rel, n) for v, n in _variables_declarees(projet.lire_fichier(rel)) if v == cle]
                        except OSError:
                            continue
            if lieux:
                return ok("variable", nom, lieux)
            if cle.startswith("jdd"):
                return rien("variable", nom, f"{nom} est un jeu de données : il se consulte dans Jeux de données, pas dans un fichier Robot.")
            return rien("variable", nom, f"{nom} : aucune déclaration trouvée dans le dépôt (variable de bibliothèque, de ligne de commande ou créée à l'exécution).")

    # 3. keyword appelé : la cellule sous le curseur
    pos, cellule = 0, ""
    for part in re.split(r"(\s{2,}|\t)", texte):
        if pos <= col < pos + len(part) and part.strip():
            cellule = part.strip()
        pos += len(part)
    if not cellule or cellule.startswith(("[", "#", "...", "*")) or not re.search(r"[A-Za-zÀ-ÿ]", cellule):
        return {"trouve": False, "message": "Rien à ouvrir sous le curseur : placer le curseur sur un keyword, une variable ou un fichier importé."}
    lieux = [(chemin, n) for nom, n in _keywords_declares(contenu) if _correspond(cellule, nom) and n != ligne]
    if not lieux:
        inv = depot_robot.lire_depot()
        for k in inv["keywords"].values():
            if k["fichier"] != chemin and _correspond(cellule, k["nom"]):
                lieux.append((k["fichier"], k["ligne"]))
                lieux += [(d.rsplit(":", 1)[0], int(d.rsplit(":", 1)[1])) for d in k.get("doublons", [])]
    if lieux:
        return ok("keyword", cellule, lieux)
    return rien("keyword", cellule, f"« {cellule} » : aucun keyword de ce nom dans le dépôt (keyword d'une bibliothèque, ou texte qui n'est pas un appel).")
