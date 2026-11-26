"""Lecture du dépôt de tests Robot Framework (parseur officiel robot.api.parsing).

Produit un inventaire statique : suites, tests (tags, clés Xray, keywords appelés, JDD, locators),
keywords définis dans le dépôt (fichier, documentation, appels), dictionnaires de locators
&{LOC_<ECRAN>_<PLATEFORME>} (et _SECOURS), bibliothèques importées. C'est la base de l'Automation
Flow Graph et de l'analyse d'impact.

Références de locators reconnues dans les arguments :
  ${LOC_ECRAN_ANDROID.cle}   ${LOC_ECRAN_${PLATFORM}.cle}   ${LOC_ECRAN_IOS}[cle]
Une référence au dictionnaire sans clé lisible (ex. via Set Variable) est rattachée à l'écran.
Locators « scalaires » aussi (format des pages générées par l'atelier) : ${NOM}    android=… dans un fichier de locators
(resources/locators/<page>.resource) ; l'écran est le nom du fichier, la clé le nom de la variable, et ${NOM} dans un
keyword en est une référence.
"""
from __future__ import annotations

import re
from pathlib import Path

from atelier.domain import projet
from atelier.integrations.xray import KEY_RE

EXCLUS = {"results", ".mcp_snapshots", "app_map", ".venv", "node_modules", ".git", "connaissance", "patrimoine"}
PLATEFORMES = {"ANDROID": "android", "IOS": "ios", "WEB": "web"}
REF_CLE = re.compile(r"LOC_([A-Z0-9_]+?)_(ANDROID|IOS|WEB|\$\{PLATFORM\})(?:_SECOURS)?\}?(?:\.|\[)\s*([A-Za-z_]\w*)")
REF_ECRAN = re.compile(r"LOC_([A-Z0-9_]+?)_(ANDROID|IOS|WEB|\$\{PLATFORM\})")
DEF_LOC = re.compile(r"^&\{LOC_([A-Z0-9_]+?)_(ANDROID|IOS|WEB)(_SECOURS)?\}$")
REF_JDD = re.compile(r"JDD_([A-Z0-9_]+)")
DEF_SCALAIRE = re.compile(r"^\$\{([A-Za-z_]\w*)\}$")
# locator scalaire décliné par plateforme : ${NOM_ANDROID} / ${NOM_IOS} / ${NOM_WEB}, choisi par ${NOM}    ${NOM_${PLATFORM}}
SUFFIXE_PLATEFORME = re.compile(r"^(\w+?)_(ANDROID|IOS|WEB)$", re.IGNORECASE)
REF_VAR = re.compile(r"\$\{([A-Za-z_]\w*)\}")
# valeur qui est sans ambiguïté un locator (hors d'un fichier de locators) / qui peut l'être (dans un fichier de locators)
LOC_SUR = re.compile(r"^(android|accessibility_id|xpath|nsp|chain|-android uiautomator|-ios \w+)=|^//")
LOC_POSSIBLE = re.compile(r"^(id|name|class|css|text|identifier|predicate|link|partial link)=")


def plateforme_locator(valeur: str) -> str:
    """Plateforme d'un locator scalaire, lue dans sa syntaxe (android par défaut pour un locator mobile)."""
    v = valeur.strip()
    if re.match(r"^(nsp|chain|-ios \w+|predicate|identifier)=", v) or "XCUIElement" in v:
        return "ios"
    if re.match(r"^(css|text|link|partial link)=", v) or "data-testid" in v:
        return "web"
    return "android"
PREFIXES_BDD = re.compile(r"^(given|when|then|and|but|étant donné|etant donne|soit|quand|lorsque|alors|et|mais)\s+",
                          re.IGNORECASE)
BIBLIOTHEQUES_UI = {"AppiumLibrary": ["android", "ios"], "Browser": ["web"], "SeleniumLibrary": ["web"],
                    "NavigateurDemo": ["web"]}  # bibliothèque Playwright du projet de démonstration (demo/)


def nom_bibliotheque(lib: str) -> str:
    """« ../bibliotheques/NavigateurDemo.py » -> « NavigateurDemo » ; un nom de module est gardé tel quel."""
    return Path(lib.replace("\\", "/")).stem if lib.endswith(".py") else lib


def normaliser(nom: str) -> str:
    """Nom de keyword comparable (règles de Robot : casse, espaces et _ ignorés)."""
    return re.sub(r"[\s_]+", "", nom).casefold()


def cle_appel(nom: str) -> str:
    """Nom appelé -> clé de keyword : préfixes BDD et préfixe de bibliothèque retirés."""
    nom = PREFIXES_BDD.sub("", nom.strip())
    if "." in nom and not nom.startswith("$"):
        nom = nom.split(".")[-1]
    return normaliser(nom)


def _refs(textes: list[str]) -> tuple[list, list, list]:
    blob = "  ".join(textes)
    locs = sorted({(e.lower(), c) for e, _, c in REF_CLE.findall(blob)})
    ecrans = sorted({e.lower() for e, _ in REF_ECRAN.findall(blob)})
    jdd = sorted(set(REF_JDD.findall(blob)))
    return locs, ecrans, jdd


_MEMOIRE_DEPOT: dict = {}  # racine -> (signature des fichiers, inventaire) : relu seulement si un fichier a changé


def lire_depot(racine: Path | None = None) -> dict:
    """Inventaire du dépôt Robot (une fois par calcul dans une portée domain/memo, sinon à chaque appel)."""
    from atelier.domain import memo

    return memo.memoiser(("lire_depot", str((racine or projet.racine_code()).resolve())), lambda: _lire_depot_memoire(racine))


def _lire_depot_memoire(racine: Path | None = None) -> dict:
    """Inventaire du dépôt Robot. Lu à chaque affichage (chemin, Studio, revues) : gardé en mémoire tant qu'aucun fichier
    .robot / .resource n'est ajouté, retiré ou modifié (texte comparé : lire est rapide, analyser est lent), et rendu en copie."""
    import copy

    racine = (racine or projet.racine_code()).resolve()  # dépôt de code de l'application active, sinon le projet
    fichiers = sorted(p for ext in ("*.robot", "*.resource") for p in racine.rglob(ext)
                      if not (set(p.relative_to(racine).parts) & EXCLUS))
    sig = []
    for f in fichiers:
        try:
            sig.append((str(f), f.read_bytes()))
        except OSError:
            sig.append((str(f), b""))
    m = _MEMOIRE_DEPOT.get(str(racine))
    if not m or m[0] != sig:
        m = _MEMOIRE_DEPOT[str(racine)] = (sig, _lire_depot(racine, fichiers))
    return copy.deepcopy(m[1])


def _lire_depot(racine: Path, fichiers: list[Path]) -> dict:
    from robot.api.parsing import ModelVisitor, get_model, get_resource_model

    inv = {"suites": {}, "tests": {}, "keywords": {}, "locators": {}, "fichiers": {}, "erreurs": []}
    for f in fichiers:
        rel = f.relative_to(racine).as_posix()
        try:
            model = (get_resource_model if f.suffix == ".resource" else get_model)(str(f))
        except Exception as e:  # fichier illisible : signalé, le reste du dépôt est lu
            inv["erreurs"].append({"fichier": rel, "erreur": str(e)})
            continue
        info = {"fichier": rel, "type": f.suffix[1:], "bibliotheques": [], "resources": [], "tags_suite": [],
                "tests": [], "keywords": [], "locators": []}
        inv["fichiers"][rel] = info

        class Visiteur(ModelVisitor):
            courant: dict | None = None

            def visit_LibraryImport(self, n):
                info["bibliotheques"].append(n.name)

            def visit_ResourceImport(self, n):
                cible = (f.parent / n.name).resolve()
                info["resources"].append(cible.relative_to(racine).as_posix() if racine in cible.parents else n.name)

            def visit_TestTags(self, n):
                info["tags_suite"] += list(n.values)

            visit_ForceTags = visit_TestTags

            def visit_Variable(self, n):
                m = DEF_LOC.match(n.name or "")
                if not m:
                    self._scalaire(n)
                    return
                ecran, plat, secours = m.group(1).lower(), PLATEFORMES[m.group(2)], bool(m.group(3))
                for v in n.value or ():
                    if "=" not in v:
                        continue
                    cle, val = v.split("=", 1)
                    lid = f"{ecran}.{cle}@{plat}"
                    loc = inv["locators"].setdefault(lid, {"id": lid, "ecran": ecran, "cle": cle, "plateforme": plat,
                                                           "valeur": "", "secours": [], "fichier": rel})
                    if secours:
                        loc["secours"] = [s.strip() for s in val.split("||") if s.strip()]
                    else:
                        loc["valeur"], loc["fichier"] = val, rel
                    if lid not in info["locators"]:
                        info["locators"].append(lid)

            def _scalaire(self, n):
                s = DEF_SCALAIRE.match(n.name or "")
                vals = [str(v) for v in (n.value or ())]
                if not s or len(vals) != 1:
                    return
                val = vals[0].strip()
                dans_locators = "locator" in rel.lower()
                if not (LOC_SUR.match(val) or (dans_locators and LOC_POSSIBLE.match(val))):
                    return
                ecran, cle, plat = f.stem.lower(), s.group(1).lower(), plateforme_locator(val)
                variante = SUFFIXE_PLATEFORME.match(s.group(1))
                if variante:  # ${NOM_ANDROID} : clé métier « nom », commune aux plateformes ; ${NOM} en est la référence
                    cle, plat = variante.group(1).lower(), PLATEFORMES[variante.group(2).upper()]
                lid = f"{ecran}.{cle}@{plat}"
                inv["locators"].setdefault(lid, {"id": lid, "ecran": ecran, "cle": cle, "plateforme": plat, "valeur": val,
                                                 "secours": [], "fichier": rel, "scalaire": True, "variable": s.group(1),
                                                 **({"variable_base": variante.group(1)} if variante else {})})
                if lid not in info["locators"]:
                    info["locators"].append(lid)

            def _bloc(self, n, genre: str):
                self.courant = {"nom": n.name, "fichier": rel, "ligne": n.lineno, "appels": [], "args": [],
                                "tags": [], "doc": ""}
                self.generic_visit(n)
                c, self.courant = self.courant, None
                c["variables"] = sorted({v for a in c["args"] for v in REF_VAR.findall(a)})
                c["locators"], c["ecrans"], c["jdd"] = _refs(c.pop("args"))
                return c

            def visit_TestCase(self, n):
                c = self._bloc(n, "test")
                tags = list(dict.fromkeys(info["tags_suite"] + c["tags"]))
                c.update(tags=tags, cles_xray=[t for t in tags if KEY_RE.match(t)], id=f"{rel}::{c['nom']}")
                inv["tests"][c["id"]] = c
                info["tests"].append(c["id"])

            def visit_Keyword(self, n):
                c = self._bloc(n, "keyword")
                c["id"] = normaliser(c["nom"])
                if c["id"] in inv["keywords"]:  # doublon : signalé, la première définition reste
                    inv["keywords"][c["id"]].setdefault("doublons", []).append(f"{rel}:{c['ligne']}")
                else:
                    inv["keywords"][c["id"]] = c
                info["keywords"].append(c["id"])

            def visit_Tags(self, n):
                if self.courant is not None:
                    self.courant["tags"] += list(n.values)

            def visit_Documentation(self, n):
                if self.courant is not None:
                    self.courant["doc"] = n.value

            def visit_KeywordCall(self, n):
                if self.courant is not None:
                    if n.keyword:
                        self.courant["appels"].append(n.keyword)
                    self.courant["args"] += [str(a) for a in n.args] + [str(a) for a in n.assign]

            def visit_Setup(self, n):
                if self.courant is not None and n.name:
                    self.courant["appels"].append(n.name)
                    self.courant["args"] += [str(a) for a in n.args]

            visit_Teardown = visit_Setup

        Visiteur().visit(model)
        if f.suffix == ".robot" and info["tests"]:
            inv["suites"][rel] = {"fichier": rel, "nom": f.stem.replace("_", " ").title(), "tests": info["tests"],
                                  "bibliotheques": info["bibliotheques"], "resources": info["resources"]}
    _resoudre(inv)
    return inv


def _resoudre(inv: dict):
    """Appels -> keywords du dépôt ou bibliothèque ; plateformes de chaque test ; ${NOM} -> locators scalaires."""
    scalaires: dict = {}
    for loc in inv["locators"].values():
        if loc.get("scalaire"):
            scalaires.setdefault(loc["variable"].upper(), (loc["ecran"], loc["cle"]))
            if loc.get("variable_base"):  # ${NOM} (choisi par ${NOM_${PLATFORM}}) désigne la même clé métier
                scalaires.setdefault(loc["variable_base"].upper(), (loc["ecran"], loc["cle"]))
    for c in list(inv["tests"].values()) + list(inv["keywords"].values()):
        refs = {scalaires[v.upper()] for v in c.pop("variables", []) if v.upper() in scalaires}
        c["locators"] = sorted({tuple(x) for x in c["locators"]} | refs)
    for c in list(inv["tests"].values()) + list(inv["keywords"].values()):
        c["keywords"] = list(dict.fromkeys(k for k in (cle_appel(a) for a in c["appels"]) if k in inv["keywords"]))
        c["externes"] = list(dict.fromkeys(a for a in c["appels"] if cle_appel(a) not in inv["keywords"]))
    for t in inv["tests"].values():
        libs = _bibliotheques_visibles(inv, t["fichier"])
        t["bibliotheques"] = libs
        t["plateformes"] = sorted({p for lib in libs for p in BIBLIOTHEQUES_UI.get(nom_bibliotheque(lib), [])})


def _bibliotheques_visibles(inv: dict, fichier: str, vus: set | None = None) -> list[str]:
    vus = vus or set()
    if fichier in vus or fichier not in inv["fichiers"]:
        return []
    vus.add(fichier)
    info = inv["fichiers"][fichier]
    out = list(info["bibliotheques"])
    for r in info["resources"]:
        out += _bibliotheques_visibles(inv, r, vus)
    return list(dict.fromkeys(out))


def fermeture_keywords(inv: dict, depart: list[str]) -> list[str]:
    """Keywords du dépôt atteints (transitivement) depuis une liste de keywords."""
    vus, pile = [], list(depart)
    while pile:
        k = pile.pop(0)
        if k in vus or k not in inv["keywords"]:
            continue
        vus.append(k)
        pile += inv["keywords"][k]["keywords"]
    return vus


def dependances_test(inv: dict, test_id: str) -> dict:
    """Tout ce dont dépend un test : keywords (transitifs), locators, écrans, JDD."""
    t = inv["tests"][test_id]
    kws = fermeture_keywords(inv, t["keywords"])
    blocs = [t] + [inv["keywords"][k] for k in kws]
    locs = sorted({tuple(x) for b in blocs for x in b["locators"]})
    return {"keywords": kws, "locators": [list(x) for x in locs],
            "ecrans": sorted({e for b in blocs for e in b["ecrans"]}),
            "jdd": sorted({j for b in blocs for j in b["jdd"]})}
