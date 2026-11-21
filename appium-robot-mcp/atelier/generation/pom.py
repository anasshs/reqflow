"""Page Object Model des tests générés : toujours, même dans un dépôt vide.

- La suite de tests ne contient que *** Settings *** (les ressources des pages) et *** Test Cases *** : aucun keyword,
  aucun locator.
- Une ressource par page / écran : ses keywords (les étapes Gherkin implémentées), qui importent les locators de
  l'écran (resources/locators/<écran>.resource, écrit par generate_locators_resource) et le socle commun.
- Le socle commun (Initialiser Le Test, Localiser…) : le fichier qui le porte déjà, sinon resources/common.resource.

Les pages suivent le dépôt : si l'équipe a déjà un dossier de pages (« pages », « page_objects »…), il est repris ;
sinon resources/pages/<application>/<écran>.resource. Une page existante n'est jamais réécrite : les keywords manquants
sont ajoutés à la fin (même règle que l'ajout d'un test à la suite de son parcours).
"""
from __future__ import annotations

import os
import re
from pathlib import PurePosixPath

RACINE_DEFAUT = "resources/pages"
COMMUN_DEFAUT = "resources/common.resource"
DOSSIER_LOCATORS = "resources/locators"
_PAGES = re.compile(r"(?i)(^|/)(pages?|page_?objects?|po)(/|$)")
_SECTION_KW = re.compile(r"(?mi)^\*+\s*keywords?\s*\*+\s*$")


def _noms_ecrans() -> set[str]:
    from atelier.discovery import carte
    from atelier.domain import projet

    try:
        return {projet.slug(e.get("nom") or "", 50, "") for e in carte.ecrans() if e.get("nom")} - {""}
    except Exception:  # noqa: BLE001 — pas de carte : seule la convention de nommage des dossiers compte
        return set()


def dossier_pages_existant(inv: dict) -> str:
    """Dossier où le dépôt range déjà ses pages : celui des .resource à keywords qui portent le nom d'un écran
    (resources/keywords/formulaire_connexion.resource), ou d'un dossier « pages / page_objects ». Vide sinon."""
    from collections import Counter

    ecrans, dossiers = _noms_ecrans(), Counter()
    for rel, info in inv.get("fichiers", {}).items():
        if rel.endswith(".resource") and info.get("keywords"):
            pp = PurePosixPath(rel)
            if pp.stem in ecrans or _PAGES.search(str(pp.parent) + "/"):
                dossiers[str(pp.parent)] += 1
    return dossiers.most_common(1)[0][0] if dossiers else ""


def racine_pages(inv: dict) -> str:
    """Dossier des pages : celui du dépôt s'il existe, sinon le défaut (resources/pages)."""
    return dossier_pages_existant(inv) or RACINE_DEFAUT


def nom_page(ref: str) -> str:
    """Nom de fichier de la page d'un écran (son nom métier dans la carte), « commun » si inconnu."""
    from atelier.discovery import carte
    from atelier.domain import projet

    if not ref:
        return "commun"
    try:
        e = carte.ecran(ref)
        return projet.slug(e.get("nom") or e.get("titre") or ref, 50, "commun")
    except (KeyError, ValueError, RuntimeError):
        return projet.slug(ref, 50, "commun")


def application() -> str:
    from atelier.discovery import carte
    from atelier.domain import projet

    try:
        app = carte.config_app() if carte.app_courante() else {}
    except Exception:  # noqa: BLE001
        app = {}
    return projet.slug(app.get("nom") or "", 40, "application")


def chemin_page(page: str, inv: dict) -> str:
    """Page d'un écran : à côté des pages existantes du dépôt, sinon resources/pages/<application>/<écran>.resource."""
    existant = dossier_pages_existant(inv)
    return f"{existant}/{page}.resource" if existant else f"{RACINE_DEFAUT}/{application()}/{page}.resource"


def _rel(de: str, vers: str) -> str:
    """Chemin relatif d'import Robot, toujours avec des « / » : sous Windows, os.path.relpath rend des « \\ » que Robot
    lit comme des échappements (« ..\\socle\\commun.resource » devenait « ....soclecommun.resource », introuvable)."""
    return os.path.relpath(vers, str(PurePosixPath(de).parent)).replace("\\", "/")


def _definis(texte: str) -> set[str]:
    """Noms des keywords déjà définis dans un fichier (insensible à la casse et aux espaces)."""
    m = _SECTION_KW.search(texte or "")
    if not m:
        return set()
    noms = set()
    for ligne in texte[m.end():].splitlines():
        if ligne.startswith("***"):
            break
        if ligne and not ligne[0].isspace() and not ligne.startswith("#"):
            noms.add(re.sub(r"\s+", " ", ligne.strip()).lower())
    return noms


def _bloc(nom: str, doc: str, args: list[str]) -> list[str]:
    return [nom, f"    [Documentation]    {doc}", *args, f"    Fail    Keyword à implémenter : {nom}", ""]


def contenu_page(chemin: str, page: str, keywords: list[tuple[str, str, list[str]]], existant: str = "",
                 commun: str = "") -> tuple[str, list[str]]:
    """(contenu, keywords ajoutés). Existant : on n'ajoute que les keywords absents, en fin de fichier."""
    from atelier.domain import projet

    deja = _definis(existant)
    nouveaux = [k for k in keywords if re.sub(r"\s+", " ", k[0].strip()).lower() not in deja]
    blocs = [l for k in nouveaux for l in _bloc(*k)]
    if existant:
        if not nouveaux:
            return existant, []
        base = existant.rstrip() + "\n"
        return (base + ("\n" if _SECTION_KW.search(existant) else "\n*** Keywords ***\n") + "\n".join(blocs)).rstrip() + "\n", [k[0] for k in nouveaux]
    imports = []
    loc = f"{DOSSIER_LOCATORS}/{page}.resource"
    if page != "commun" and projet.safe_path(loc).exists():
        imports.append(f"Resource    {_rel(chemin, loc)}")
    if commun and commun != chemin:
        imports.append(f"Resource    {_rel(chemin, commun)}")
    texte = ["*** Settings ***",
             f"Documentation    Page « {page} » (Page Object Model) : les keywords de l'écran. Ses locators : {loc}.",
             *imports, "", "*** Keywords ***", *blocs]
    return "\n".join(texte).rstrip() + "\n", [k[0] for k in nouveaux]


def preparer(a_creer: list[dict], inv: dict, suite: str, commun_existant: str = "", page_defaut: str = "") -> dict:
    """Pages à écrire pour les keywords à créer ({nom, doc, args, ecran}) et lignes Resource de la suite.
    Rend {pages: [{chemin, page, contenu, nouveau, keywords}], imports: [chemins relatifs à la suite]}."""
    from atelier.domain import projet

    commun = commun_existant or COMMUN_DEFAUT
    par_page: dict[str, list] = {}
    for k in a_creer:
        # étape sans écran connu : page du module (ou du scénario), jamais le socle commun
        page = "commun" if k["nom"] == "Initialiser Le Test" else nom_page(k["ecran"]) if k.get("ecran") else (page_defaut or "general")
        par_page.setdefault(page, []).append((k["nom"], k["doc"], k.get("args") or []))
    pages = []
    for page, kws in par_page.items():
        chemin = commun if page == "commun" else chemin_page(page, inv)
        try:
            existant = projet.lire_fichier(chemin)
        except (FileNotFoundError, OSError, ValueError):
            existant = ""
        contenu, ajoutes = contenu_page(chemin, page, kws, existant, commun if page != "commun" else "")
        pages.append({"chemin": chemin, "page": page, "contenu": contenu, "nouveau": not existant, "keywords": ajoutes})
    return {"pages": pages, "imports": [p["chemin"] for p in pages]}


def ecrire(pages: list[dict]) -> list[str]:
    """Écrit les pages : création, ou ajout en fin de page existante (son contenu d'origine est conservé tel quel)."""
    from atelier.domain import projet

    ecrites = []
    for p in pages:
        if not p["keywords"]:
            continue
        projet.ecrire_fichier(p["chemin"], p["contenu"], not p["nouveau"])
        ecrites.append(p["chemin"])
    return ecrites


def chemin_relatif(de: str, vers: str) -> str:
    return _rel(de, vers)
