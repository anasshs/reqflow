"""Structure du dépôt de tests : où l'équipe range déjà ses tests, ses locators, ses keywords et page objects.

Un dépôt existant a sa logique (un dossier pour les locators, un autre pour les keywords et les pages, un autre pour
les tests…). Ce qui est généré, par l'atelier ou par Cursor, doit la suivre. Ce module la LIT dans le dépôt (aucun
réglage à saisir) et contrôle qu'un fichier est rangé à l'endroit attendu pour son genre :
- la structure est transmise à Cursor avant qu'il écrive (`studio_socle`, clé « structure ») ;
- un fichier écrit hors de la structure est signalé à l'écriture et dans la revue technique (contrôle « structure »).

Genre d'un fichier, d'après son contenu : « tests » (suite .robot), « keywords » (.resource avec des keywords : socle,
page objects), « locators » (.resource qui ne porte que des dictionnaires &{LOC_…}). La racine d'un genre est le plus
long dossier commun à ses fichiers. Un fichier est à sa place sous cette racine, ou dans un dossier voisin de même niveau
(tests/virement à côté de tests/connexion) ; il ne l'est pas dans un nouveau dossier à la racine du dépôt, ni dans le
dossier réservé à un autre genre. Sans fichier d'un genre dans le dépôt, rien n'est imposé pour ce genre.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import PurePosixPath

GENRES = {"tests": "Tests (suites .robot)", "keywords": "Keywords et page objects (.resource)", "locators": "Locators (.resource)"}
CONSIGNE = ("Ranger chaque fichier dans le dossier de son genre, comme le dépôt le fait déjà : ne pas créer de nouveau dossier "
            "racine, ne pas mélanger locators, keywords et tests dans un même fichier s'ils sont séparés ailleurs.")
_TESTS = re.compile(r"(?mi)^\*+\s*test cases?\s*\*+")
_KEYWORDS = re.compile(r"(?mi)^\*+\s*keywords?\s*\*+")
_LOCATORS = re.compile(r"(?m)^&\{LOC_[A-Z0-9_]+\}")


def _genre_fichier(info: dict) -> str:
    if info.get("type") == "robot" or info.get("tests"):
        return "tests"
    if info.get("keywords"):
        return "keywords"
    return "locators" if info.get("locators") else ""


def genre_du_contenu(chemin: str, contenu: str) -> str:
    """Genre d'un fichier à écrire, d'après son extension et son contenu ; vide s'il n'est pas classable."""
    if chemin.endswith(".robot") or _TESTS.search(contenu or ""):
        return "tests"
    if _KEYWORDS.search(contenu or ""):
        return "keywords"
    return "locators" if _LOCATORS.search(contenu or "") else ""


def _dossier(chemin: str) -> str:
    d = PurePosixPath(chemin.replace("\\", "/")).parent.as_posix()
    return "" if d == "." else d


def _racine(dossiers: list[str]) -> str:
    """Plus long dossier commun ; vide si les fichiers sont à la racine du dépôt ou sous des racines différentes."""
    if not dossiers or "" in dossiers:
        return ""
    parts = [d.split("/") for d in dossiers]
    commun = []
    for niveau in zip(*parts):
        if len(set(niveau)) != 1:
            break
        commun.append(niveau[0])
    return "/".join(commun)


def _sous(dossier: str, racine: str) -> bool:
    return dossier == racine or dossier.startswith(racine + "/")


def structure(inv: dict | None = None, sauf: set[str] | None = None) -> dict:
    """Structure lue dans le dépôt : par genre, sa racine et ses dossiers (du plus fourni au moins fourni).
    sauf : fichiers à ignorer (celui qu'on contrôle ne doit pas justifier sa propre place)."""
    from atelier.generation import rangement

    if inv is None:
        from atelier.execution.depot_robot import lire_depot

        inv = lire_depot()
    par: dict = {g: Counter() for g in GENRES}
    for rel, info in inv["fichiers"].items():
        g = _genre_fichier(info)
        if g and rel not in (sauf or ()):
            par[g][_dossier(rel)] += 1
    genres = {g: {"libelle": GENRES[g], "fichiers": sum(c.values()), "racine": _racine(list(c)),
                  "dossiers": [{"dossier": d or "(racine du dépôt)", "fichiers": n} for d, n in sorted(c.items(), key=lambda x: (-x[1], x[0]))][:12]}
              for g, c in par.items()}
    motif = rangement.regles()["robot"]
    racine_tests = genres["tests"]["racine"]
    return {"genres": genres, "vide": not any(x["fichiers"] for x in genres.values()), "consigne": CONSIGNE,
            "regle_tests": motif,
            # le motif de rangement des tests générés (Test Design › Réglages) doit rester sous le dossier des tests existants
            "regle_tests_conforme": not racine_tests or _sous(_dossier(motif.replace("{", "").replace("}", "")), racine_tests)}


def controler(chemin: str, contenu: str = "", inv: dict | None = None) -> dict:
    """Le fichier est-il rangé comme le dépôt range déjà les fichiers de son genre ? Jamais bloquant : c'est un constat,
    rendu à l'écriture et affiché dans la revue technique. Le fichier contrôlé est ignoré dans le calcul de la structure."""
    chemin = chemin.replace("\\", "/")
    if inv is None:
        from atelier.execution.depot_robot import lire_depot

        inv = lire_depot()
    genre = genre_du_contenu(chemin, contenu) or _genre_fichier(inv["fichiers"].get(chemin) or {})
    s = structure(inv, {chemin})
    info = s["genres"].get(genre)
    if not genre:
        return {"fichier": chemin, "genre": "", "conforme": True, "attendu": "", "message": "Fichier non classé (ni test, ni keywords, ni locators) : aucune structure à suivre."}
    if not info["fichiers"]:
        return {"fichier": chemin, "genre": genre, "conforme": True, "attendu": "",
                "message": f"Premier fichier de ce genre ({GENRES[genre]}) dans le dépôt : aucune structure à suivre."}
    d, racine = _dossier(chemin), info["racine"]
    connus = [x["dossier"] for x in info["dossiers"]]
    if racine:
        # sous la racine du genre, ou dans un dossier voisin de même niveau (tests/virement à côté de tests/connexion,
        # resources/pages à côté de resources/keywords) ; jamais un nouveau dossier à la racine du dépôt
        parent = _dossier(racine)
        ok, attendu = _sous(d, racine) or bool(parent and _dossier(d) == parent), racine + "/"
    else:  # fichiers à la racine du dépôt ou sous plusieurs racines : même premier dossier qu'un fichier existant
        tetes = {"" if x == "(racine du dépôt)" else x.split("/")[0] for x in connus}
        ok, attendu = d.split("/")[0] in tetes, " ou ".join(sorted((t + "/") if t else "(racine du dépôt)" for t in tetes))
    # sous la bonne racine, mais dans le dossier réservé à un autre genre (ex. des keywords dans resources/locators)
    autre = next((GENRES[g] for g, o in s["genres"].items() if g != genre and o["racine"] and _sous(d, o["racine"])
                  and not (racine and _sous(racine, o["racine"]))), "")  # un ancêtre commun n'est pas un dossier réservé
    if ok and autre:
        return {"fichier": chemin, "genre": genre, "conforme": False, "attendu": attendu,
                "message": f"{chemin} : rangé dans le dossier des « {autre} », alors que le dépôt range ses « {GENRES[genre]} » sous {attendu} (ex. {connus[0]}/)."}
    if not ok:
        return {"fichier": chemin, "genre": genre, "conforme": False, "attendu": attendu,
                "message": f"{chemin} : hors de la structure du dépôt, qui range ses « {GENRES[genre]} » sous {attendu} (ex. {connus[0]}/)."}
    return {"fichier": chemin, "genre": genre, "conforme": True, "attendu": attendu, "message": f"Rangé comme le reste du dépôt (sous {attendu})."}


def resume() -> dict:
    """Pour une IA, avant d'écrire : où ranger chaque genre de fichier (racine et dossiers existants)."""
    s = structure()
    return {"consigne": s["consigne"], "regle_tests": s["regle_tests"],
            "genres": {g: {"racine": x["racine"], "dossiers": [d["dossier"] for d in x["dossiers"][:6]], "fichiers": x["fichiers"]}
                       for g, x in s["genres"].items()}}
