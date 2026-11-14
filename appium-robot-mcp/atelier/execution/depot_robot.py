"""Lecture du dépôt de tests Robot Framework (parseur officiel robot.api.parsing).

Produit un inventaire statique : suites, tests (tags, clés Xray, keywords appelés, JDD, locators),
keywords définis dans le dépôt (fichier, documentation, appels), dictionnaires de locators
&{LOC_<ECRAN>_<PLATEFORME>} (et _SECOURS), bibliothèques importées. C'est la base de l'Automation
Flow Graph et de l'analyse d'impact.

Références de locators reconnues dans les arguments :
  ${LOC_ECRAN_ANDROID.cle}   ${LOC_ECRAN_${PLATFORM}.cle}   ${LOC_ECRAN_IOS}[cle]
Une référence au dictionnaire sans clé lisible (ex. via Set Variable) est rattachée à l'écran.
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


def lire_depot(racine: Path | None = None) -> dict:
    from robot.api.parsing import ModelVisitor, get_model, get_resource_model

    racine = (racine or projet.PROJECT_DIR).resolve()
    inv = {"suites": {}, "tests": {}, "keywords": {}, "locators": {}, "fichiers": {}, "erreurs": []}

    fichiers = sorted(p for ext in ("*.robot", "*.resource") for p in racine.rglob(ext)
                      if not (set(p.relative_to(racine).parts) & EXCLUS))
    for f in fichiers:
        rel = str(f.relative_to(racine))
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
                info["resources"].append(str(cible.relative_to(racine)) if racine in cible.parents else n.name)

            def visit_TestTags(self, n):
                info["tags_suite"] += list(n.values)

            visit_ForceTags = visit_TestTags

            def visit_Variable(self, n):
                m = DEF_LOC.match(n.name or "")
                if not m:
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

            def _bloc(self, n, genre: str):
                self.courant = {"nom": n.name, "fichier": rel, "ligne": n.lineno, "appels": [], "args": [],
                                "tags": [], "doc": ""}
                self.generic_visit(n)
                c, self.courant = self.courant, None
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
    """Appels -> keywords du dépôt ou bibliothèque ; plateformes de chaque test."""
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
