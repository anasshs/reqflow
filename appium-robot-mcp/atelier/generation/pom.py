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
        # nom métier validé, sinon module ; jamais le titre de l'écran (il peut contenir le nom du client connecté)
        return projet.slug(e.get("nom") or e.get("module") or f"ecran_{e.get('id') or ref}", 50, "commun")
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


ACTION = re.compile(r"(?i)^(que )?je (touche|clique|ouvre|choisis|sélectionne|selectionne|valide|appuie|coche|ferme|"
                    r"réinitialise|reinitialise|masque|réaffiche|reaffiche|filtre|active|désactive|lance|continue)\b")
SAISIE = re.compile(r"(?i)^je (renseigne|saisis|remplis|tape|entre)\b")
RETOUR = re.compile(r"(?i)^je reviens en arrière")
SECRET = re.compile(r"(?i)(password|passwd|mot_?de_?passe|mdp|secret|token|pin|cvv|otp)")


def _type_app() -> str:
    from atelier.discovery import carte

    try:
        return carte.type_app(carte.config_app()) if carte.app_courante() else "web"
    except Exception:  # noqa: BLE001
        return "web"


def nom_locator(page: str, etape: dict) -> str:
    """Nom de variable du locator d'une étape : PAGE_ELEMENT (identifiant technique de l'élément si le locator en a un)."""
    from atelier.domain import projet

    loc = etape.get("locator") or ""
    base = ""
    for motif in (r'resourceId\("([^"]+)"\)', r'^id=([\w:/.-]+)', r'data-testid=["\']?([\w-]+)', r'^accessibility_id=([\w -]+)'):
        m = re.search(motif, loc)
        if m:
            base = m.group(1)
            break
    base = base or etape.get("texte", "element")
    base = base.split(":id/")[-1]
    return f"{projet.slug(page, 30, 'page')}_{projet.slug(base, 40, 'element')}".upper()


def corps_etape(etape: dict | None, var: str, type_app: str) -> list[str]:
    """Corps d'un keyword généré depuis son étape : toucher, saisir la donnée du jeu (secret sans journalisation),
    revenir en arrière, ou vérifier la présence. Vide si l'étape n'a pas de quoi agir (pas de locator) : stub."""
    if not etape:
        return []
    texte, champ = etape.get("texte", ""), etape.get("jdd", "")
    loc = "${" + var + "}" if var else ""
    mobile = type_app == "mobile"
    if RETOUR.match(texte):
        return ["    Go Back"]
    if not loc or type_app == "api":
        return []
    if SAISIE.match(texte) and champ:
        if mobile:
            saisie = "Input Password" if SECRET.search(champ) else "Input Text"
            return [f"    Wait Until Element Is Visible    {loc}    15s", f"    {saisie}    {loc}    ${{JDD}}[{champ}]"]
        if SECRET.search(champ):
            return [f"    ${{secret}}=    Set Variable    ${{JDD}}[{champ}]", f"    Fill Secret    {loc}    $secret"]
        return [f"    Fill Text    {loc}    ${{JDD}}[{champ}]"]
    if ACTION.match(texte):
        return ([f"    Wait Until Element Is Visible    {loc}    15s", f"    Click Element    {loc}"] if mobile else [f"    Click    {loc}"])
    return ([f"    Wait Until Element Is Visible    {loc}    15s"] if mobile
            else [f"    Wait For Elements State    {loc}    visible    timeout=15s"])


def _bloc(nom: str, doc: str, args: list[str], corps: list[str] | None = None) -> list[str]:
    if corps:
        return [nom, f"    [Documentation]    {doc}", *args, *corps, ""]
    return [nom, f"    [Documentation]    {doc}", *args, f"    Fail    Keyword à implémenter : {nom}", ""]


def contenu_page(chemin: str, page: str, keywords: list[tuple], existant: str = "",
                 commun: str = "", avec_locators: bool = False) -> tuple[str, list[str]]:
    """(contenu, keywords ajoutés). Existant : on n'ajoute que les keywords absents, en fin de fichier. Un keyword est
    (nom, doc, args) ou (nom, doc, args, corps) ; sans corps, c'est un stub « À implémenter »."""
    from atelier.domain import projet

    deja = _definis(existant)
    nouveaux = [k for k in keywords if re.sub(r"\s+", " ", k[0].strip()).lower() not in deja]
    blocs = [l for k in nouveaux for l in _bloc(*k)]
    loc = f"{DOSSIER_LOCATORS}/{page}.resource"
    import_loc = f"Resource    {_rel(chemin, loc)}"
    if existant:
        if not nouveaux:
            return existant, []
        if avec_locators and import_loc not in existant:  # la page reçoit ses premiers locators : import ajouté
            existant = _ajouter_import(existant, import_loc)
        base = existant.rstrip() + "\n"
        return (base + ("\n" if _SECTION_KW.search(existant) else "\n*** Keywords ***\n") + "\n".join(blocs)).rstrip() + "\n", [k[0] for k in nouveaux]
    imports = []
    if page != "commun" and (avec_locators or projet.safe_path(loc).exists()):
        imports.append(import_loc)
    if commun and commun != chemin:
        imports.append(f"Resource    {_rel(chemin, commun)}")
    texte = ["*** Settings ***",
             f"Documentation    Page « {page} » (Page Object Model) : les keywords de l'écran. Ses locators : {loc}.",
             *imports, "", "*** Keywords ***", *blocs]
    return "\n".join(texte).rstrip() + "\n", [k[0] for k in nouveaux]


def _ajouter_import(texte: str, ligne: str) -> str:
    """Ajoute une ligne Resource à la fin de la section Settings (avant la section suivante)."""
    lignes = texte.split("\n")
    debut = next((i for i, l in enumerate(lignes) if re.match(r"(?i)^\*+\s*settings", l)), None)
    if debut is None:
        return "*** Settings ***\n" + ligne + "\n\n" + texte
    fin = next((i for i in range(debut + 1, len(lignes)) if lignes[i].startswith("*")), len(lignes))
    while fin > debut + 1 and not lignes[fin - 1].strip():
        fin -= 1
    return "\n".join(lignes[:fin] + [ligne] + lignes[fin:])


def preparer(a_creer: list[dict], inv: dict, suite: str, commun_existant: str = "", page_defaut: str = "") -> dict:
    """Pages à écrire pour les keywords à créer ({nom, doc, args, ecran}) et lignes Resource de la suite.
    Rend {pages: [{chemin, page, contenu, nouveau, keywords}], imports: [chemins relatifs à la suite]}."""
    from atelier.domain import projet

    commun = commun_existant or COMMUN_DEFAUT
    type_app = _type_app()
    par_page: dict[str, list] = {}
    locators: dict[str, dict] = {}
    for k in a_creer:
        # étape sans écran connu : page du module (ou du scénario), jamais le socle commun
        page = "commun" if k["nom"] == "Initialiser Le Test" else nom_page(k["ecran"]) if k.get("ecran") else (page_defaut or "general")
        etape = k.get("etape") or None
        var = nom_locator(page, etape) if etape and etape.get("locator") else ""
        corps = corps_etape(etape, var, type_app) if page != "commun" else []
        doc = k["doc"]
        if corps:
            if var:
                locators.setdefault(page, {})[var] = etape["locator"]
            doc = (doc.replace("À implémenter : aucun keyword du dépôt ne correspond.", "").strip()
                   + f" Généré depuis l'étape « {etape['texte']} »" + (f" (écran {k['ecran']})" if k.get("ecran") else "") + " : à relire.").strip()
        par_page.setdefault(page, []).append((k["nom"], doc, k.get("args") or [], corps))
    pages = []
    for page, kws in par_page.items():
        chemin = commun if page == "commun" else chemin_page(page, inv)
        try:
            existant = projet.lire_fichier(chemin)
        except (FileNotFoundError, OSError, ValueError):
            existant = ""
        contenu, ajoutes = contenu_page(chemin, page, kws, existant, commun if page != "commun" else "", bool(locators.get(page)))
        pages.append({"chemin": chemin, "page": page, "contenu": contenu, "nouveau": not existant, "keywords": ajoutes,
                      "locators": {"chemin": f"{DOSSIER_LOCATORS}/{page}.resource", "variables": locators.get(page, {})}})
    return {"pages": pages, "imports": [p["chemin"] for p in pages]}


def contenu_locators(chemin: str, variables: dict, existant: str = "") -> str:
    """Fichier de locators d'une page : variables ajoutées en fin de fichier, celles déjà définies sont gardées."""
    deja = set(re.findall(r"(?m)^\$\{(\w+)\}", existant or ""))
    nouvelles = [f"${{{k}}}".ljust(46) + v for k, v in variables.items() if k not in deja]
    if not nouvelles:
        return existant
    if existant:
        return existant.rstrip() + "\n" + "\n".join(nouvelles) + "\n"
    return "\n".join(["*** Settings ***", f"Documentation    Locators de la page « {PurePosixPath(chemin).stem} » (générés depuis les étapes BDD).",
                       "", "", "*** Variables ***", *nouvelles]) + "\n"


def ecrire(pages: list[dict]) -> list[str]:
    """Écrit les pages : création, ou ajout en fin de page existante (son contenu d'origine est conservé tel quel)."""
    from atelier.domain import projet

    ecrites = []
    for p in pages:
        if not p["keywords"]:
            continue
        loc = p.get("locators") or {}
        if loc.get("variables"):  # les locators d'abord : la page les importe
            try:
                existant = projet.lire_fichier(loc["chemin"])
            except (FileNotFoundError, OSError, ValueError):
                existant = ""
            contenu = contenu_locators(loc["chemin"], loc["variables"], existant)
            if contenu != existant:
                projet.ecrire_fichier(loc["chemin"], contenu, bool(existant))
                ecrites.append(loc["chemin"])
        projet.ecrire_fichier(p["chemin"], p["contenu"], not p["nouveau"])
        ecrites.append(p["chemin"])
    return ecrites


def chemin_relatif(de: str, vers: str) -> str:
    return _rel(de, vers)
