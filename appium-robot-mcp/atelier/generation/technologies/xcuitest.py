"""Technologie XCUITest (iOS natif, Swift) : l'équivalent iOS d'UI Automator / Espresso, bien plus rapide qu'Appium.

Les tests sont des classes XCTestCase d'une cible « UI Testing Bundle » du projet Xcode de l'application (son dépôt iOS :
fiche application, dépôt de la technologie « xcuitest »). L'atelier écrit dans ce dépôt, sous automatisation.dossier_xcuitest
(défaut AtelierUITests/) :
  Socle/Atelier.swift      assistant (lancement, éléments depuis les locators de la carte, données, OTP, à implémenter)
  Bdd/<Classe>Tests.swift  tests générés depuis les scénarios BDD (même plan d'automatisation que les autres technologies)
  Genere/…                 keywords et tests Robot convertis (generation/robot2swift.py)
Il suffit d'ajouter ce dossier à la cible UI Tests dans Xcode (une fois). Exécution : xcodebuild test sur un Mac
(execution/xcuitest.py). Données : variables d'environnement du test JDD_<JEU>_<CHAMP> (xcodebuild : TEST_RUNNER_…),
jamais écrites dans le code. Clé Xray : dans le nom de la méthode (test_TAM_301_…) et en commentaire.
"""
from __future__ import annotations

import re

from atelier.generation.technologies import Technologie
from atelier.generation.technologies.kotlin import MARQUE, camel, doc, slug

DOSSIER_DEFAUT = "AtelierUITests"


def sw(s: str) -> str:
    """Littéral Swift (\\( n'est jamais une interpolation)."""
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def methode(cle_xray: str, nom: str) -> str:
    """test_TAM_301_connexion_valide : la clé Xray se relit dans le nom (résultats → Xray)."""
    return f"test_{re.sub(r'[^A-Za-z0-9]', '_', cle_xray)}_{slug(nom)[:60]}"


def cle_de_methode(m: str) -> str:
    x = re.match(r"test_([A-Z][A-Z0-9]*)_(\d+)(?:_|$)", m or "")
    return f"{x.group(1)}-{x.group(2)}" if x else ""


SOCLE = r'''import XCTest

/// MARQUE (XCUITest) : ne pas modifier, réécrit à chaque génération.
/// Données : variables d'environnement JDD_<JEU>_<CHAMP> (xcodebuild : TEST_RUNNER_JDD_…) ; OTP_MODE (arret par défaut) ;
/// APP_BUNDLE_ID (sinon l'application cible du schéma).
enum Atelier {
    static var app: XCUIApplication!
    static var jeu = ""
    static var delai: TimeInterval = 15
    static var env: [String: String] { ProcessInfo.processInfo.environment }

    static func lancer(bundle: String = "BUNDLE") {
        let id = env["APP_BUNDLE_ID"] ?? bundle
        app = id.isEmpty ? XCUIApplication() : XCUIApplication(bundleIdentifier: id)
        app.launch()
    }

    static var otpMode: String { env["OTP_MODE"] ?? "arret" }

    static func initialiser(jeu: String) { self.jeu = jeu }

    /// Valeur d'un champ du jeu de données ; échec nommé si l'atelier ne l'a pas fournie (jamais une valeur inventée).
    static func donnee(_ champ: String, jeu: String? = nil) -> String {
        let cle = "JDD_\((jeu ?? self.jeu).uppercased())_\(champ.uppercased())"
        guard let v = env[cle], !v.isEmpty else { XCTFail("Donnée \(cle) non fournie (variable d'environnement du test)"); return "" }
        return v
    }

    /// Élément depuis un locator de la carte ou du dépôt Robot : id= / accessibility_id= / name=, -ios predicate string:,
    /// XPath simple (//*[@name|@label|@value="…"]), sinon libellé ou identifiant égal au texte.
    static func el(_ locator: String) -> XCUIElement {
        let l = locator.trimmingCharacters(in: .whitespaces)
        let tous = app.descendants(matching: .any)
        for p in ["id=", "accessibility_id=", "accessibility id=", "name="] where l.hasPrefix(p) {
            return tous[String(l.dropFirst(p.count))].firstMatch
        }
        for p in ["-ios predicate string:", "predicate="] where l.hasPrefix(p) {
            return tous.matching(NSPredicate(format: String(l.dropFirst(p.count)))).firstMatch
        }
        if let r = try? NSRegularExpression(pattern: "@(name|label|value)\\s*=\\s*[\"']([^\"']+)[\"']"),
           let m = r.firstMatch(in: l, range: NSRange(l.startIndex..., in: l)),
           let a = Range(m.range(at: 1), in: l), let v = Range(m.range(at: 2), in: l) {
            let attribut = String(l[a]) == "name" ? "identifier" : String(l[a])
            return tous.matching(NSPredicate(format: "%K == %@", attribut, String(l[v]))).firstMatch
        }
        if l.hasPrefix("//") || l.hasPrefix("xpath=") || l.hasPrefix("-ios class chain:") {
            aImplementer("locator non traduit en XCUITest : \(l)")
        }
        return tous.matching(NSPredicate(format: "label == %@ OR identifier == %@", l, l)).firstMatch
    }

    @discardableResult
    static func attendre(_ l: String, _ t: TimeInterval? = nil) -> XCUIElement {
        let e = el(l)
        XCTAssertTrue(e.waitForExistence(timeout: t ?? delai), "Élément absent : \(l)")
        return e
    }

    static func toucher(_ l: String) { attendre(l).tap() }

    static func saisir(_ l: String, _ valeur: String) {
        let e = attendre(l)
        e.tap()
        if let actuel = e.value as? String, !actuel.isEmpty, actuel != (e.placeholderValue ?? "") {
            e.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: actuel.count))
        }
        e.typeText(valeur)
    }

    static func texte(_ l: String) -> String {
        let e = attendre(l)
        return e.label.isEmpty ? ((e.value as? String) ?? "") : e.label
    }

    static func verifier(_ l: String, attendu: String = "") {
        if attendu.isEmpty { attendre(l) } else { XCTAssertTrue(texte(l).contains(attendu), "\(l) : « \(texte(l)) », attendu « \(attendu) »") }
    }

    static func absent(_ l: String) { XCTAssertFalse(el(l).waitForExistence(timeout: 2), "Élément présent à tort : \(l)") }

    static func texteVisible(_ t: String, _ delaiMax: TimeInterval? = nil) {
        let e = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", t)).firstMatch
        XCTAssertTrue(e.waitForExistence(timeout: delaiMax ?? delai), "Texte absent : \(t)")
    }

    static func retour() {
        let b = app.navigationBars.buttons.element(boundBy: 0)
        if b.exists { b.tap() } else { app.coordinate(withNormalizedOffset: CGVector(dx: 0.01, dy: 0.5)).press(forDuration: 0.1, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.8, dy: 0.5))) }
    }

    static func balayer(_ sens: String) {
        switch sens { case "bas": app.swipeDown(); case "gauche": app.swipeLeft(); case "droite": app.swipeRight(); default: app.swipeUp() }
    }

    static func masquerClavier() { if app.keyboards.element.exists { app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.08)).tap() } }

    static func pause(_ secondes: Double) { Thread.sleep(forTimeInterval: secondes) }

    static func capture(_ nom: String = "capture") {
        let a = XCTAttachment(screenshot: app.screenshot()); a.lifetime = .keepAlways; a.name = nom
        XCTContext.runActivity(named: nom) { $0.add(a) }
    }

    /// OTP : vrai si le test doit s'arrêter là (mode arret). En validation (recette), le code est fourni par OTP_CODE :
    /// iOS ne laisse pas un test lire les SMS.
    static func otpDansChamp(_ l: String) -> Bool {
        if otpMode != "validation" { return true }
        guard let code = env["OTP_CODE"], !code.isEmpty else { XCTFail("OTP_MODE=validation : OTP_CODE à fournir (iOS ne lit pas les SMS)"); return true }
        saisir(l, code)
        return false
    }

    /// Étape que l'atelier n'a pas su automatiser : le test échoue en la nommant (jamais de faux succès).
    static func aImplementer(_ etape: String) { XCTFail("Étape à implémenter : \(etape)") }
}
'''


class Xcuitest(Technologie):
    def __init__(self):
        super().__init__("xcuitest", "XCUITest (Swift, iOS natif)", ["ios"], "Swift",
                         "XCTest UI (XCUIApplication), Xcode sur Mac",
                         prerequis=["Mac avec Xcode", "projet Xcode de l'application avec une cible UI Tests (dépôt iOS)",
                                    "simulateur iOS ou iPhone de développement"])

    @staticmethod
    def config() -> dict:
        from atelier.discovery import carte

        try:
            cfg = carte.config_app() if carte.app_courante() else {}
        except Exception:  # noqa: BLE001
            cfg = {}
        a = (cfg or {}).get("automatisation") or {}
        return {"dossier": (a.get("dossier_xcuitest") or DOSSIER_DEFAUT).strip("/"),
                "bundle": ((cfg or {}).get("ios") or {}).get("bundle_id") or "",
                "projet": a.get("xcode_projet", ""), "schema": a.get("xcode_schema", ""), "cible": a.get("xcode_cible", ""),
                "destination": a.get("xcode_destination") or "platform=iOS Simulator,name=iPhone 15"}

    @staticmethod
    def fonctions_portees(dossier: str) -> set[str]:
        """Fonctions k_<nom> des keywords Robot déjà convertis en Swift (Genere/)."""
        from atelier.domain import projet

        out = set()
        with projet.pour_technologie("xcuitest"):
            d = projet.safe_path(f"{dossier}/Genere")
            for f in d.glob("*.swift") if d.exists() else []:
                out |= set(re.findall(r"\bfunc\s+(k_\w+)\(", f.read_text("utf-8", errors="replace")))
        return out

    def _etape(self, e: dict, x: dict, fonctions: set, jeu: str, a_impl: list) -> list[str]:
        lignes = [f"        // {e['mot'].capitalize()} {e['texte']}"]
        fn = "k_" + slug(x["keyword"]) if x.get("statut") == "existant" and x.get("keyword") else ""
        if fn and fn in fonctions:  # keyword Robot déjà converti : appelé tel quel
            return lignes + [f"        {fn}({', '.join(sw(a) for a in x.get('arguments') or [])})"]
        i, loc = e["intention"], e.get("locator") or ""
        if i == "revenir":
            return lignes + ["        Atelier.retour()"]
        if i == "otp":
            if loc:
                return lignes + [f"        if Atelier.otpDansChamp({sw(loc)}) {{ return }}  // mode arret : rien n'est validé"]
            return lignes + ['        if Atelier.otpMode != "validation" { return }  // arrêt sur l\'écran OTP, rien n\'est validé']
        if i == "sms" and e.get("sms") == "preparer_sms":
            return lignes + ["        // repère SMS : sans objet sur iOS (le code OTP est fourni par OTP_CODE)"]
        if i == "sms" or not loc:
            a_impl.append(e["texte"])
            return lignes + [f"        Atelier.aImplementer({sw(e['texte'])})"]
        if i == "toucher":
            return lignes + [f"        Atelier.toucher({sw(loc)})"]
        if i == "saisir":
            valeur = f"Atelier.donnee({sw(e['donnee'])})" if e.get("donnee") else sw("")
            return lignes + [f"        Atelier.saisir({sw(loc)}, {valeur})"]
        attendu = f", attendu: {sw(e['attendu'])}" if e.get("attendu") else ""
        return lignes + [f"        Atelier.verifier({sw(loc)}{attendu})"]

    def generer(self, m: dict, inventaire: dict | None = None, chemin: str = "") -> dict:
        from atelier.domain import projet
        from atelier.generation import bdd

        c = self.config()
        plan = self.plan(m)
        rap = bdd.reutilisation(m, inventaire)
        fonctions = self.fonctions_portees(c["dossier"])
        nom_classe = camel(m.get("parcours", "").replace("PU-", "") or m.get("module") or m["cle"], majuscule=True) + "Tests"
        test_rel = chemin.replace("\\", "/") if chemin else f"{c['dossier']}/Bdd/{nom_classe}.swift"
        cle_xray = plan["cle_xray"] or m["cle"]
        a_impl, methodes = [], []
        for s in plan["scenarios"]:
            for jeu in s["jeux"] or [""]:
                nom = methode(cle_xray, s["nom"] + (f" {jeu}" if len(s["jeux"]) > 1 else ""))
                corps = ([f"        Atelier.initialiser(jeu: {sw(jeu)})"] if jeu else []) \
                    + [l for e in s["etapes"] for l in self._etape(e, rap.get(e["id"], {}), fonctions, jeu, a_impl)]
                methodes.append((nom, f"    /// {doc(s['nom'])} — Xray : {cle_xray} (scénario BDD {m['cle']}" + (f", jeu {jeu}" if jeu else "")
                                 + f")\n    func {nom}() throws {{\n" + "\n".join(corps) + "\n    }"))
        with projet.pour_technologie(self.nom):
            existant = projet.lire_fichier(test_rel) if projet.safe_path(test_rel).exists() else ""
            depot = str(projet.racine_code())
        deja = set(re.findall(r"\bfunc\s+(\w+)\(", existant))
        nouvelles = [b for n, b in methodes if n not in deja]
        if existant:
            i = existant.rstrip().rfind("}")
            contenu = (existant[:i].rstrip() + "\n\n" + "\n\n".join(nouvelles) + "\n}\n") if nouvelles else existant
        else:
            contenu = (f"import XCTest\n\n/// {doc(plan['titre'])} — {MARQUE} depuis les scénarios BDD (XCUITest).\n"
                       f"final class {nom_classe}: XCTestCase {{\n\n    override func setUpWithError() throws {{\n"
                       "        continueAfterFailure = false\n        Atelier.lancer()\n    }\n\n"
                       + "\n\n".join(nouvelles) + "\n}\n")
        return {"chemin": test_rel, "contenu": contenu, "pages": [], "technologie": self.nom, "langage": "Swift",
                "socle": [{"chemin": f"{c['dossier']}/Socle/Atelier.swift", "contenu": SOCLE.replace("MARQUE", MARQUE).replace('"BUNDLE"', sw(c["bundle"]))}],
                "classe": nom_classe, "methodes": [n for n, _ in methodes], "ajout": bool(existant),
                "methodes_ajoutees": [n for n, b in methodes if b in nouvelles], "fonctions_reutilisees": sorted(fonctions & {l.strip().split("(")[0] for _, b in methodes for l in b.splitlines()}),
                "a_implementer": list(dict.fromkeys(a_impl)), "cle_xray": plan["cle_xray"], "tag": cle_xray, "depot": depot,
                "a_integrer": f"ajouter le dossier {c['dossier']}/ à la cible UI Tests du projet Xcode (une fois)"}

    def ecrire(self, m: dict, g: dict, remplacer: bool = False, origine: str = "cursor") -> dict:
        from atelier.domain import projet
        from atelier.generation import studio

        with projet.pour_technologie(self.nom):
            for f in g["socle"]:
                if not projet.safe_path(f["chemin"]).exists() or projet.lire_fichier(f["chemin"]) != f["contenu"]:
                    projet.ecrire_fichier(f["chemin"], f["contenu"], True)
            projet.ecrire_fichier(g["chemin"], g["contenu"], g["ajout"])
            revue = studio.entrer_en_revue(g["chemin"], origine)
        return {**g, "ecrit": True, "revue": revue}

    def controler(self, g: dict | None = None) -> dict:
        """Contrôle avant revue : compilation des tests (xcodebuild build-for-testing), sur un Mac seulement."""
        from atelier.execution import xcuitest

        return xcuitest.compiler()
