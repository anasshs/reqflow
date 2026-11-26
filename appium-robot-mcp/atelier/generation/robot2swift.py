"""Conversion du patrimoine Robot (AppiumLibrary) en XCUITest (Swift) : iOS natif, sans Appium.

Lu dans le dépôt Robot de l'application (robot.api.parsing), écrit dans son dépôt iOS (technologie « xcuitest ») :
  <dossier>/Genere/Keywords.swift          un keyword utilisateur → func k_<slug>(…) (mêmes noms que le portage Kotlin)
  <dossier>/Genere/<Suite>RobotTests.swift une suite → une classe XCTestCase, un test → func test_<CLE_XRAY>_<nom>()
Traductions : keywords AppiumLibrary et BuiltIn courants → assistant Atelier (Socle/Atelier.swift) ; appel d'un keyword
utilisateur → k_<slug>(…) ; ${LOCATOR} → sa valeur iOS (${X}  ${X_${PLATFORM}} résolu avec PLATFORM=IOS) ; ${JDD}[champ]
→ Atelier.donnee("champ") ; Initialiser Le Test &{JDD_X} → Atelier.initialiser(jeu: "X") ; ${x}=  Get Text → let.
Tout ce qui n'est pas traduit (structure IF / FOR, keyword de bibliothèque inconnu, locator Android seul) devient
Atelier.aImplementer("…") : le test échoue en le nommant, jamais de faux succès. Le bilan dit ce qui reste par test.
Fichiers réécrits à chaque conversion (propriété de l'atelier) ; Socle/ et Bdd/ ne sont jamais touchés.
"""
from __future__ import annotations

import re
from pathlib import Path

from atelier.generation.technologies.kotlin import MARQUE, camel, slug
from atelier.generation.technologies.xcuitest import methode, sw

VAR = re.compile(r"[$@&%]\{([^{}]+)\}")
CLE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")
COMMENTAIRES = {"log", "logtoconsole", "comment", "settestdocumentation", "settestmessage", "journaliserletape",
                "journaliserletatdelecran", "nooperation"}


def norme(nom: str) -> str:
    return re.sub(r"[\s_]+", "", str(nom or "").lower())


class Convertisseur:
    def __init__(self, racine: Path):
        self.racine = racine
        self.scalaires: dict[str, str] = {"PLATFORM": "IOS", "EMPTY": "", "SPACE": " ", "TRUE": "true", "FALSE": "false"}
        self.keywords: dict[str, dict] = {}
        self.suites: list[dict] = []

    # ------------------------------------------------------------------ lecture du dépôt Robot
    def lire(self):
        from robot.api.parsing import get_model, get_resource_model

        fichiers = [f for f in sorted(self.racine.rglob("*")) if f.suffix in (".robot", ".resource")
                    and not any(p in f.parts for p in ("results", ".venv", "node_modules"))]
        for f in fichiers:
            try:
                model = (get_resource_model if f.suffix == ".resource" else get_model)(str(f))
            except Exception:  # noqa: BLE001 — fichier illisible : ignoré (le dépôt Robot le signale déjà)
                continue
            suite = {"fichier": f.relative_to(self.racine).as_posix(), "tests": []}
            for section in model.sections:
                genre = type(section).__name__
                if genre == "VariableSection":
                    for v in section.body:
                        if type(v).__name__ != "Variable" or not v.name:
                            continue
                        if v.name.startswith("${") and len(v.value or ()) == 1:
                            self.scalaires.setdefault(v.name[2:-1], str(v.value[0]))
                        elif v.name.startswith("&{"):  # dictionnaire de locators « clé=valeur » : ${NOM.clé} / ${NOM}[clé]
                            for item in v.value or ():
                                if "=" in str(item):
                                    k, val = str(item).split("=", 1)
                                    self.scalaires.setdefault(f"{v.name[2:-1]}.{k}", val)
                elif genre == "KeywordSection":
                    for k in section.body:
                        if type(k).__name__ == "Keyword":
                            self.keywords.setdefault(norme(k.name), {"nom": k.name, "noeud": k, "fichier": suite["fichier"]})
                elif genre == "TestCaseSection":
                    for t in section.body:
                        if type(t).__name__ == "TestCase":
                            suite["tests"].append(t)
            if suite["tests"]:
                self.suites.append(suite)

    # ------------------------------------------------------------------ valeurs
    def resoudre(self, nom: str, profondeur: int = 0) -> str | None:
        """Valeur d'une variable scalaire du dépôt, variables imbriquées résolues (PLATFORM=IOS) ; None si inconnue."""
        if profondeur > 8:
            return None

        def sous(m):
            r = self.resoudre(m.group(1), profondeur + 1)
            return r if r is not None else m.group(0)

        nom = VAR.sub(sous, nom)
        v = self.scalaires.get(nom)
        if v is None:
            return None
        for _ in range(8):  # ${X} → ${X_${PLATFORM}} → ${X_IOS} → valeur : jusqu'à stabilité
            if "${" not in v:
                break
            nv = VAR.sub(sous, v)
            if nv == v:
                break
            v = nv
        return v

    def expr(self, texte: str, locales: dict) -> tuple[str, bool]:
        """Expression Swift d'un argument Robot (« ok » faux si une variable reste inconnue)."""
        t = re.sub(r"\$\{(\w+)\}\[['\"]?(\w+)['\"]?\]", r"${\1.\2}", str(texte))  # ${X}[clé] → ${X.clé}
        m = re.fullmatch(r"\$\{(JDD\w*|DONNEES|jdd|donnees)\.(\w+)\}", t)
        if m and f"{m.group(1)}.{m.group(2)}" not in self.scalaires:  # donnée du jeu de données du test
            return f"Atelier.donnee({sw(m.group(2))})", True
        m = re.fullmatch(r"\$\{([^{}]+)\}", t)
        if m and m.group(1) in locales:
            return locales[m.group(1)], True
        ok, morceaux, pos = True, [], 0
        for v in VAR.finditer(t):
            morceaux.append(t[pos:v.start()].replace("\\", "\\\\").replace('"', '\\"'))
            nom = v.group(1)
            d = re.fullmatch(r"(JDD\w*|DONNEES|jdd|donnees)\.(\w+)", nom)
            if d and nom not in self.scalaires:
                morceaux.append(f"\\(Atelier.donnee({sw(d.group(2))}))")
            elif nom in locales:
                morceaux.append(f"\\({locales[nom]})")
            else:
                val = self.resoudre(nom)
                if val is None or "${" in val:
                    ok = False
                    morceaux.append(v.group(0))
                else:
                    morceaux.append(val.replace("\\", "\\\\").replace('"', '\\"'))
            pos = v.end()
        morceaux.append(t[pos:].replace("\\", "\\\\").replace('"', '\\"'))
        return '"' + "".join(morceaux) + '"', ok

    @staticmethod
    def secondes(t: str) -> str:
        m = re.fullmatch(r"\s*(?:timeout=)?([\d.]+)\s*(s|sec|seconds?)?\s*", str(t or ""))
        return m.group(1) if m else ""

    # ------------------------------------------------------------------ appels
    def _integres(self, nom: str):
        """Keyword utilisateur à arguments intégrés (« Le Compte Est ${compte} ») qui correspond à l'appel : (clé, valeurs)."""
        for cle, k in self.keywords.items():
            if "${" not in k["nom"]:
                continue
            motif = re.escape(re.sub(r"\s+", " ", k["nom"].strip()))
            motif = re.sub(r"\\\$\\\{[^}]*\\\}", "(.+?)", motif)
            m = re.fullmatch(motif, re.sub(r"\s+", " ", nom.strip()), re.I)
            if m:
                return cle, list(m.groups())
        return None, []

    def appel(self, nom: str, args: list[str], assign: list[str], locales: dict, manques: list) -> list[str]:
        nom = re.sub(r"(?i)^(given|when|then|and|but|étant donné|etant donne|quand|alors|et|mais)\s+", "", str(nom).strip())
        n = norme(nom)
        if n == "initialiserletest":  # avant toute résolution : &{JDD_X} désigne le jeu, pas une variable à évaluer
            m = re.fullmatch(r"&\{JDD_([A-Za-z0-9_]+)\}", args[0]) if args else None
            return [f"        Atelier.initialiser(jeu: {sw(m.group(1))})"] if m else ["        // Initialiser Le Test (sans jeu de données)"]
        if n not in self.keywords:
            cle_i, valeurs = self._integres(nom)
            if cle_i:  # arguments intégrés : valeurs lues dans le nom de l'appel, puis les arguments explicites
                ex = [self.expr(v, locales) for v in valeurs + list(args)]
                if all(o for _, o in ex):
                    appel = f"k_{slug(self.keywords[cle_i]['nom'])}({', '.join(s for s, _ in ex)})"
                    if assign:
                        cible = assign[0].strip("${}= ")
                        locales[cible] = "v_" + slug(cible)
                        return [f"        let v_{slug(cible)} = {appel}"]
                    return [f"        {appel}"]
        pos = [a for a in args if not re.match(r"^\w+=", a) or a.startswith("${")]
        nommes = dict(a.split("=", 1) for a in args if re.match(r"^\w+=", a) and not a.startswith("${"))
        e = [self.expr(a, locales) for a in pos]
        ok = all(o for _, o in e)
        x = [s for s, _ in e]
        cible = assign[0].strip("${}= ") if assign else ""

        def var(expression: str) -> list[str]:
            if not cible:
                return [f"        _ = {expression}"]
            nv = "v_" + slug(cible)
            decl = "" if cible in locales else "var "
            locales[cible] = nv
            return [f"        {decl}{nv} = {expression}"]

        def manque(raison: str) -> list[str]:
            manques.append(raison)
            return [f"        Atelier.aImplementer({sw(raison)})"]

        if n in COMMENTAIRES:
            return [f"        // {nom} {' '.join(args)}".rstrip()]
        if not ok:
            return manque(f"{nom} : variable non résolue pour iOS ({' '.join(args)[:80]})")
        un = x[0] if x else '""'
        delai = self.secondes(nommes.get("timeout") or (pos[1] if len(pos) > 1 else ""))
        sur_element = n in ("clickelement", "tap", "clickbutton", "inputtext", "inputpassword", "inputvalue", "typetext", "cleartext",
                            "waituntilelementisvisible", "waituntilpagecontainselement", "pageshouldcontainelement",
                            "elementshouldbevisible", "expectelement", "elementshouldbeenabled", "waitforelement", "gettext",
                            "getelementtext", "elementshouldcontaintext", "elementtextshouldbe", "elementshouldcontain")
        if sur_element and un == '""':  # ${X_IOS} vide : l'élément n'a pas de locator iOS (Discovery iOS à faire)
            return manque(f"{nom} : locator iOS absent ({pos[0] if pos else ''}) — à capturer par une Discovery iOS")
        if n in ("clickelement", "tap", "clickbutton", "clicktext", "clickelementatcoordinates") and x:
            return [f"        Atelier.toucher({un})"]
        if n in ("inputtext", "inputpassword", "inputvalue", "typetext", "saisirmotdepasse") and len(x) >= 2:
            return [f"        Atelier.saisir({x[0]}, {x[1]})"]
        if n in ("cleartext",) and x:
            return [f'        Atelier.saisir({un}, "")']
        if n in ("waituntilelementisvisible", "waituntilpagecontainselement", "pageshouldcontainelement", "elementshouldbevisible",
                 "expectelement", "elementshouldbeenabled", "waitforelement") and x:
            return [f"        Atelier.attendre({un}{', ' + delai if delai else ''})"]
        if n in ("waituntilpagecontains", "pageshouldcontaintext", "pageshouldcontain") and x:
            return [f"        Atelier.texteVisible({un}{', ' + delai if delai else ''})"]
        if n in ("pageshouldnotcontainelement", "elementshouldnotbevisible", "waituntilpagedoesnotcontainelement",
                 "waituntilelementisnotvisible") and x:
            return [f"        Atelier.absent({un})"]
        if n in ("elementshouldcontaintext", "elementtextshouldbe", "elementshouldcontain") and len(x) >= 2:
            return [f"        Atelier.verifier({x[0]}, attendu: {x[1]})"]
        if n in ("gettext", "getelementtext") and x:
            return var(f"Atelier.texte({un})")
        if n in ("goback", "pressback"):
            return ["        Atelier.retour()"]
        if n == "presskeycode" and pos[:1] == ["4"]:
            return ["        Atelier.retour()"]
        if n in ("hidekeyboard", "masquerleclavierandroid"):
            return ["        Atelier.masquerClavier()"]
        if n in ("swipe", "swipebypercent", "scrolldown", "scrollup", "scroll"):
            sens = "bas" if n == "scrollup" else "haut"
            return [f"        Atelier.balayer({sw(sens)})"]
        if n == "sleep":
            return [f"        Atelier.pause({self.secondes(pos[0] if pos else '1') or '1'})"]
        if n in ("capturepagescreenshot", "capturelecran"):
            return ["        Atelier.capture()"]
        if n in ("openapplication", "launchapplication", "activateapplication"):
            return ["        Atelier.lancer()"]
        if n in ("closeapplication", "quitapplication", "terminateapplication", "closeallapplications"):
            return ["        Atelier.app.terminate()"]
        if n == "setvariable":
            return var(un)
        if n in ("settestvariable", "setsuitevariable", "setglobalvariable") and len(pos) >= 2:
            nom_v = pos[0].strip("${}\\")
            locales[nom_v] = "v_" + slug(nom_v)
            return [f"        let v_{slug(nom_v)} = {x[1]}"]
        if n == "shouldbeequal" and len(x) >= 2:
            return [f"        XCTAssertEqual({x[0]}, {x[1]})"]
        if n == "shouldcontain" and len(x) >= 2:
            return [f"        XCTAssertTrue(({x[0]}).contains({x[1]}))"]
        if n == "shouldnotbeempty" and x:
            return [f"        XCTAssertFalse(({un}).isEmpty)"]
        if n == "fail":
            return [f"        XCTFail({un})"]
        if n in self.keywords:
            k = self.keywords[n]
            fn = "k_" + slug(k["nom"])
            appel = f"{fn}({', '.join(x)})"
            return var(appel) if cible else [f"        {appel}"]
        if "${" in nom:  # keyword à arguments intégrés : non converti automatiquement
            return manque(f"keyword à arguments intégrés : {nom}")
        return manque(f"keyword non converti : {nom}")

    def corps(self, noeuds, locales: dict, manques: list) -> tuple[list[str], bool]:
        lignes, retour = [], False
        for st in noeuds:
            g = type(st).__name__
            if g == "KeywordCall":
                lignes += self.appel(st.keyword, [str(a) for a in st.args], [str(a) for a in st.assign], locales, manques)
            elif g in ("ReturnStatement", "Return", "ReturnSetting"):
                vals = [str(v) for v in getattr(st, "values", ()) or ()]
                if vals:
                    s, ok = self.expr(vals[0], locales)
                    lignes.append(f"        return {s}" if ok else f"        Atelier.aImplementer({sw('retour non résolu')}); return \"\"")
                    retour = True
            elif g in ("If", "For", "While", "Try", "Group"):
                manques.append(f"structure {g.upper()} non convertie")
                lignes.append(f"        Atelier.aImplementer({sw(f'structure {g.upper()} non convertie (ligne {st.lineno})')})")
            elif g in ("Setup", "Teardown") and getattr(st, "name", None):
                lignes += self.appel(st.name, [str(a) for a in st.args], [], locales, manques)
        return lignes, retour

    # ------------------------------------------------------------------ génération
    def keyword_swift(self, k: dict) -> tuple[str, list]:
        noeud, manques, locales, params = k["noeud"], [], {}, []
        for nom in re.findall(r"\$\{([^}:]+)(?::[^}]*)?\}", k["nom"]):  # arguments intégrés au nom, dans l'ordre
            p = "a_" + slug(nom)
            locales[nom] = p
            params.append(f"_ {p}: String")
        for st in noeud.body:
            if type(st).__name__ == "KeywordArguments" or (type(st).__name__ == "Arguments"):
                for a in st.values:
                    nom, _, defaut = str(a).partition("=")
                    nom = nom.strip("${}@& ")
                    p = "a_" + slug(nom)
                    locales[nom] = p
                    params.append(f"_ {p}: String" + (f" = {self.expr(defaut, {})[0]}" if defaut else ""))
        lignes, retour = self.corps([s for s in noeud.body if type(s).__name__ not in ("KeywordArguments", "Arguments")], locales, manques)
        if retour and not any(l.strip().startswith("return") for l in lignes[-1:]):
            lignes.append('        return ""')
        sig = f"func k_{slug(k['nom'])}({', '.join(params)})" + (" -> String" if retour else "")
        attr = "@discardableResult\n" if retour else ""
        return f"/// {k['nom']} ({k['fichier']})\n{attr}{sig} {{\n" + "\n".join(lignes or ["        // (vide)"]) + "\n}", manques

    def convertir(self, dossier: str) -> dict:
        self.lire()
        blocs, bilan_kw = [], {}
        for n, k in sorted(self.keywords.items()):
            code, manques = self.keyword_swift(k)
            blocs.append(code)
            bilan_kw[n] = {"nom": k["nom"], "complet": not manques, "manques": manques[:5]}
        fichiers = [{"chemin": f"{dossier}/Genere/Keywords.swift",
                     "contenu": f"import XCTest\n\n// {MARQUE} (conversion Robot → XCUITest) : réécrit à chaque conversion.\n\n" + "\n\n".join(blocs) + "\n"}]
        bilan_tests = []

        def appels_kw(noeud) -> set:
            out = set()
            for st in getattr(noeud, "body", []) or []:
                nom = getattr(st, "keyword", None) or getattr(st, "name", None)
                if not nom:
                    continue
                nom = re.sub(r"(?i)^(given|when|then|and|but|étant donné|etant donne|quand|alors|et|mais)\s+", "", str(nom).strip())
                cle = norme(nom) if norme(nom) in self.keywords else self._integres(nom)[0]
                if cle:
                    out.add(cle)
            return out

        def fermeture(depart: set) -> set:
            vus, pile = set(), list(depart)
            while pile:
                k = pile.pop()
                if k not in vus:
                    vus.add(k)
                    pile += list(appels_kw(self.keywords[k]["noeud"]))
            return vus

        for s in self.suites:
            classe = camel(Path(s["fichier"]).stem, majuscule=True) + "RobotTests"
            methodes = []
            for t in s["tests"]:
                tags = [str(v) for st in t.body if type(st).__name__ == "Tags" for v in st.values]
                cle = next((x for x in tags if CLE.match(x)), "")
                manques, locales = [], {}
                lignes, _ = self.corps(t.body, locales, manques)
                kws = fermeture(appels_kw(t))
                incomplets = sorted(bilan_kw[k]["nom"] for k in kws if not bilan_kw[k]["complet"])
                nom_m = methode(cle, t.name) if cle else "test_" + slug(t.name)[:70]
                methodes.append(f"    /// {t.name}" + (f" — Xray : {cle}" if cle else "") + f"\n    func {nom_m}() throws {{\n"
                                + "\n".join(lignes or ["        // (vide)"]) + "\n    }")
                bilan_tests.append({"suite": s["fichier"], "test": t.name, "cle_xray": cle, "methode": f"{classe}/{nom_m}",
                                    "complet": not manques and not incomplets, "manques": manques[:5], "keywords_incomplets": incomplets[:10]})
            fichiers.append({"chemin": f"{dossier}/Genere/{classe}.swift", "contenu":
                             f"import XCTest\n\n/// {s['fichier']} — {MARQUE} (conversion Robot → XCUITest) : réécrit à chaque conversion.\n"
                             f"final class {classe}: XCTestCase {{\n\n    override func setUpWithError() throws {{\n"
                             "        continueAfterFailure = false\n        Atelier.lancer()\n    }\n\n" + "\n\n".join(methodes) + "\n}\n"})
        return {"fichiers": fichiers, "keywords": len(bilan_kw), "keywords_complets": sum(v["complet"] for v in bilan_kw.values()),
                "tests": len(bilan_tests), "tests_complets": sum(t["complet"] for t in bilan_tests), "detail_tests": bilan_tests,
                "keywords_incomplets": [v for v in bilan_kw.values() if not v["complet"]][:50]}


def porter(ecrire: bool = True) -> dict:
    """Convertit le dépôt Robot de l'application active en XCUITest dans son dépôt iOS ; rend le bilan par test."""
    from atelier.domain import projet
    from atelier.generation.technologies.xcuitest import SOCLE, Xcuitest

    c = Xcuitest.config()
    racine_robot = projet.racine_code("robot-appium")
    r = Convertisseur(racine_robot).convertir(c["dossier"])
    if ecrire:
        with projet.pour_technologie("xcuitest"):
            socle = f"{c['dossier']}/Socle/Atelier.swift"
            if not projet.safe_path(socle).exists():
                projet.ecrire_fichier(socle, SOCLE.replace("MARQUE", MARQUE).replace('"BUNDLE"', sw(c["bundle"])))
            for f in r["fichiers"]:
                projet.ecrire_fichier(f["chemin"], f["contenu"], True)
            r["depot"] = str(projet.racine_code())
    r["fichiers"] = [f["chemin"] for f in r["fichiers"]]
    r["depot_robot"] = str(racine_robot)
    return r
