"""Technologies Android natives en Kotlin (docs/AUTOMATISATION_MULTI_CIBLES.md, phases C et F).

UI Automator (phase C) : tests d'instrumentation qui pilotent l'application INSTALLÉE (boîte noire, comme Appium, mais
dans le téléphone). Ils vivent dans le projet Kotlin du dépôt de tests (fiche de l'application :
automatisation.projet_kotlin, défaut « uiautomator ») et s'appuient sur son socle (socle/Simple.kt, socle/Cible.kt,
socle/Locators.kt, socle/R.kt). Depuis le plan d'automatisation neutre :
  - un Page Object par écran de la carte : pages/Page<Écran>.kt (objet Kotlin, une Cible par élément) ;
  - une classe de test par parcours (sinon par module) : bdd/<Nom>Test.kt, une méthode par scénario (et par jeu de
    données d'un tableau d'exemples), annotée @Xray("CLE") ;
  - chaque étape selon son intention ; une étape qui correspond à un keyword Robot déjà porté en Kotlin (fonction
    k_<nom> du dossier genere/, produite par outils/robot2kotlin.py) l'appelle : rien n'est réécrit deux fois ;
  - ce qui ne se traduit pas échoue en se nommant (Bdd.aImplementer), jamais de faux succès.
Rien d'existant n'est réécrit : un Page Object ou une classe de test existants sont complétés (éléments et méthodes
absents ajoutés en fin d'objet / de classe).

Espresso (phase F) : voir technologies/espresso.py.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from atelier.generation.technologies import Technologie

MARQUE = "Généré par l'atelier"


# =========================================================================== utilitaires Kotlin
def slug(nom: str) -> str:
    """Même règle que outils/robot2kotlin.py : ASCII, minuscules, _ (les fonctions portées s'appellent k_<slug>)."""
    s = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower() or "x"


def camel(nom: str, majuscule: bool = False) -> str:
    mots = [m for m in slug(nom).split("_") if m]
    s = "".join(m.capitalize() for m in mots) if mots else "X"
    s = s if majuscule else s[0].lower() + s[1:]
    return ("_" + s) if s[0].isdigit() else s


def ks(s: str) -> str:
    """Littéral Kotlin (les $ ne sont pas des gabarits)."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'


def doc(s: str) -> str:
    return s.replace("*/", "* /").replace("/*", "/ *")


# =========================================================================== projet Kotlin
class ProjetKotlin:
    """Le projet Kotlin du dépôt de tests : racine des sources de test, paquet, socle, fonctions déjà portées."""

    def __init__(self, dossier: str = ""):
        from atelier.domain import projet
        from atelier.generation import perimetre

        self.dossier = (dossier or perimetre.dossier_kotlin()).strip("/")
        self.racine = projet.PROJECT_DIR / self.dossier
        self.paquet = self._paquet()
        self.src_rel = f"{self.dossier}/app/src/androidTest/java/{self.paquet.replace('.', '/')}"
        self.src = projet.PROJECT_DIR / self.src_rel

    def _paquet(self) -> str:
        from atelier.discovery import carte

        try:
            cfg = (carte.config_app() if carte.app_courante() else {}).get("automatisation") or {}
        except Exception:  # noqa: BLE001
            cfg = {}
        if cfg.get("paquet_kotlin"):
            return cfg["paquet_kotlin"]
        g = self.racine / "app" / "build.gradle.kts"
        m = re.search(r'namespace\s*=\s*"([\w.]+)"', g.read_text("utf-8")) if g.exists() else None
        return m.group(1) if m else "tests.tnr"

    def exiger_socle(self):
        manquants = [f for f in ("socle/Simple.kt", "socle/Cible.kt", "socle/Locators.kt", "socle/R.kt") if not (self.src / f).exists()]
        if manquants:
            raise ValueError(f"Socle Kotlin absent de {self.src_rel} ({', '.join(manquants)}) : le projet UI Automator du dépôt "
                             "de tests doit exister (docs/AUTOMATISATION_MULTI_CIBLES.md, phase A).")

    def fonctions_portees(self) -> set[str]:
        """Fonctions k_<nom> des keywords Robot déjà portés en Kotlin (dossier genere/)."""
        out = set()
        for f in (self.src / "genere").glob("*.kt") if (self.src / "genere").exists() else []:
            out |= set(re.findall(r"\bfun\s+(k_\w+)\(", f.read_text("utf-8", errors="replace")))
        return out


# =========================================================================== éléments (Cible du socle)
def cible(locator: str) -> str:
    """Expression Kotlin d'une Cible du socle depuis un locator de la carte ou du dépôt (toutes syntaxes Appium)."""
    from atelier.generation import plan_automatisation

    e = plan_automatisation.element(locator)
    m = re.search(r"([\w.]+):id/", locator or "")
    if e["resource_id"]:
        if m and not m.group(1).startswith("$"):
            return f"Cible(By.res({ks(m.group(1) + ':id/' + e['resource_id'])}))"
        return f"Cible(By.res(Simple.paquet, {ks(e['resource_id'])}))"
    if e["accessibility_id"]:
        return f"Cible(By.desc({ks(e['accessibility_id'])}))"
    if e["texte"] and re.fullmatch(r'(xpath=)?//\*\[@text\s*=\s*["\'][^"\']+["\']\]', (locator or "").strip()):
        return f"Cible(By.text({ks(e['texte'])}))"
    brut = ks((locator or "").strip()).replace("\\${APP_ID}", "${Simple.paquet}")
    return f"Locators.depuisTexte({brut})"  # traduit à l'exécution ; intraduisible : échec explicite (NonTraduit)


def nom_element(etape: dict) -> str:
    e = etape.get("element") or {}
    return camel(e.get("resource_id") or e.get("accessibility_id") or e.get("texte") or etape.get("texte") or "element")


def nom_page(ecran: str) -> str:
    return "Page" + camel((ecran or "general").split(":", 1)[-1], majuscule=True)


# =========================================================================== fichiers
def contenu_bdd(paquet: str) -> str:
    """Assistant des tests générés depuis un scénario BDD : annotation @Xray, données du jeu, OTP, étape à implémenter."""
    return f'''package {paquet}.bdd

import androidx.test.uiautomator.By
import {paquet}.socle.Cible
import {paquet}.socle.NonTraduit
import {paquet}.socle.R
import {paquet}.socle.Simple
import org.junit.Assume
import java.util.regex.Pattern

/** Clé du test Xray que ce test automatise (remontée des résultats dans Xray). */
@Retention(AnnotationRetention.RUNTIME)
@Target(AnnotationTarget.FUNCTION)
annotation class Xray(val cle: String)

/**
 * {MARQUE} (tests issus des scénarios BDD) : ne pas modifier, il est réécrit à chaque génération.
 * Données : arguments d'instrumentation « -e jdd.<JEU>.<champ> valeur » fournis par l'atelier, jamais écrits dans le code.
 * OTP : -e otp_mode arret (défaut : le test s'arrête sur l'écran OTP, rien n'est validé) ou validation (recette : code lu
 * dans les SMS du téléphone, saisi et confirmé).
 */
object Bdd {{
    private var debutOtp = System.currentTimeMillis()

    /** Étape que l'atelier n'a pas su automatiser : le test échoue en la nommant (jamais de faux succès). */
    fun aImplementer(etape: String): Nothing = throw NonTraduit("Étape à implémenter : $etape")

    /** Valeur d'un champ du jeu de données ; test ignoré (pas en échec) si l'atelier ne l'a pas fournie. */
    fun donnee(jeu: String, champ: String): String {{
        val v = Simple.arg("jdd.$jeu.$champ")
        Assume.assumeTrue("Donnée jdd.$jeu.$champ non fournie (argument d'instrumentation)", v.isNotEmpty())
        return v
    }}

    /** Jeu de données complet, rendu aux keywords portés du dépôt Robot (variables du test, et ${{JDD}}). */
    fun initialiserJeu(jeu: String, champs: List<String>) {{
        val m = champs.associateWith {{ Simple.arg("jdd.$jeu.$it") }}
        R.initialiser(m)
        R.portee["JDD"] = m
    }}

    /** Élément présent (constat d'une étape « Alors »). */
    fun verifier(cible: Cible, quoi: String, attendu: String = "") {{
        val el = cible.exiger(quoi = quoi)
        if (attendu.isNotEmpty() && !(el.text ?: "").contains(attendu)) throw AssertionError("$quoi : « ${{el.text}} », attendu « $attendu »")
    }}

    /** Repère avant l'action qui envoie le SMS : seul un SMS reçu ensuite est lu. */
    fun avantOtp() {{ debutOtp = System.currentTimeMillis() - 2_000 }}

    /** Écran OTP : vrai si le test doit s'arrêter là (mode arret) ; en mode validation, code lu, saisi et confirmé. */
    fun otp(): Boolean {{
        val ecran = Cible(By.text(Pattern.compile("(?i)^code de confirmation$")))
        ecran.exiger(30_000, "écran OTP")
        if (Simple.otpMode != "validation") return true
        val fin = System.currentTimeMillis() + 90_000
        var code: String? = null
        while (code == null && System.currentTimeMillis() < fin) {{
            val sms = Simple.device.executeShellCommand("content query --uri content://sms/inbox --projection date:body --sort \\"date DESC\\"")
            code = Regex("date=(\\\\d+), body=(.*)").findAll(sms).firstOrNull {{ (it.groupValues[1].toLongOrNull() ?: 0) >= debutOtp }}
                ?.let {{ Regex("(?<!\\\\d)(\\\\d{{6}})(?!\\\\d)").find(it.groupValues[2])?.groupValues?.get(1) }}
            if (code == null) Thread.sleep(3_000)
        }}
        if (code == null) throw AssertionError("Aucun SMS OTP reçu en 90 s")
        Cible(By.res(Pattern.compile(".*:id/inputOTP"))).cliquer()
        Simple.device.executeShellCommand("input text $code")
        Cible(By.res(Pattern.compile(".*:id/btnValidate"))).cliquer()
        return false
    }}
}}
'''


def _ajouter_dans(existant: str, blocs: list[str]) -> str:
    """Ajoute des blocs avant la dernière accolade fermante (fin de l'objet ou de la classe), sans rien réécrire."""
    i = existant.rstrip().rfind("}")
    return existant[:i].rstrip() + "\n\n" + "\n\n".join(b.rstrip() for b in blocs) + "\n}\n"


def contenu_page(paquet: str, nom: str, ecran: str, elements: dict[str, tuple[str, str]], existant: str = "") -> tuple[str, list[str]]:
    """Page Object d'un écran : {nom_element: (expression Cible, locator d'origine)}. Existant : seuls les absents sont ajoutés."""
    deja = set(re.findall(r"\bval\s+(\w+)\s*=", existant))
    nouveaux = {k: v for k, v in elements.items() if k not in deja}
    lignes = [f"    /** {doc(loc)} */\n    val {k} = {expr}" for k, (expr, loc) in nouveaux.items()]
    if existant:
        return (_ajouter_dans(existant, lignes) if lignes else existant), list(nouveaux)
    entete = (f"package {paquet}.pages\n\nimport androidx.test.uiautomator.By\nimport {paquet}.socle.Cible\n"
              f"import {paquet}.socle.Locators\nimport {paquet}.socle.Simple\n\n"
              f"/** Écran « {doc(ecran or 'général')} » (carte de l'application) — {MARQUE} : éléments ajoutés à la génération, "
              "jamais réécrits. */\n@Suppress(\"unused\")\n")
    return entete + f"object {nom} {{\n" + "\n".join(lignes) + "\n}\n", list(nouveaux)


# =========================================================================== génération
class UiAutomator(Technologie):
    def __init__(self):
        super().__init__("uiautomator", "UI Automator 2 (Kotlin)", ["android"], "Kotlin",
                         "instrumentation Android, application installée",
                         prerequis=["JDK 17", "SDK Android 34", "Gradle 8.7", "projet Kotlin du dépôt de tests (socle)"])

    def _etape(self, e: dict, x: dict, fonctions: set, jeu: str, pages_util: dict, reutilisees: list, a_impl: list,
               page_defaut: str) -> list[str]:
        lignes = [f"        // {e['mot'].capitalize()} {e['texte']}"]
        fn = "k_" + slug(x["keyword"]) if x.get("statut") == "existant" and x.get("keyword") else ""
        if fn and fn in fonctions:  # keyword Robot déjà porté en Kotlin : appelé tel quel
            valeurs = list(x.get("arguments") or [])
            if x.get("correspondance") == "arguments intégrés":  # « Le Compte Est ${compte} » : valeurs lues dans le texte
                from atelier.generation.reutilisation import _motif

                mm = (_motif(x["keyword"]) or re.compile("$^")).fullmatch(" ".join(e["texte"].split()))
                valeurs = list(mm.groups()) if mm else valeurs
            args = ", ".join(f"R.fmt(v, {ks(a)})" for a in valeurs)
            lignes.append(f"        {fn}({args})")
            reutilisees.append(fn)
            return lignes
        # « Le Compte De Connexion Est ${COMPTE_VALIDE} » : keyword porté « Le Compte De Connexion Est » + arguments explicites
        mm = re.fullmatch(r"(.+?)((?:\s+[$&@]\{[^}]+\}(?:\[[^\]]+\])?)+)\s*", e["texte"])
        if mm and "k_" + slug(mm.group(1)) in fonctions:
            fn = "k_" + slug(mm.group(1))
            vals = re.findall(r"[$&@]\{[^}]+\}(?:\[[^\]]+\])?", mm.group(2))
            lignes.append(f"        {fn}({', '.join(f'R.fmt(v, {ks(a)})' for a in vals)})")
            reutilisees.append(fn)
            return lignes
        i = e["intention"]
        if i == "revenir":
            return lignes + ["        Simple.device.pressBack()"]
        if i == "otp":
            return lignes + ["        if (Bdd.otp()) return  // mode arret : le test s'arrête sur l'écran OTP, rien n'est validé"]
        if i == "ouvrir" and not e["locator"]:
            if re.search(r"(?i)connect", e["texte"]):
                return lignes + ["        Simple.seConnecter()"]
            a_impl.append(e["texte"])
            return lignes + [f"        Bdd.aImplementer({ks(e['texte'])})"]
        if not e["locator"]:
            a_impl.append(e["texte"])
            return lignes + [f"        Bdd.aImplementer({ks(e['texte'])})"]
        page = nom_page(e["ecran"] or page_defaut)
        el = nom_element(e)
        pages_util.setdefault(page, {"ecran": e["ecran"] or page_defaut, "elements": {}})["elements"][el] = (cible(e["locator"]), e["locator"])
        ref = f"{page}.{el}"
        if i == "toucher":
            return lignes + [f"        {ref}.cliquer()"]
        if i == "saisir":
            valeur = f"Bdd.donnee({ks(jeu)}, {ks(e['donnee'])})" if jeu else f"Simple.arg({ks('jdd.' + e['donnee'])})"
            return lignes + [f"        {ref}.saisir({valeur})"]
        attendu = f", {ks(e['attendu'])}" if e.get("attendu") else ""
        return lignes + [f"        Bdd.verifier({ref}, {ks(e['texte'])}{attendu})"]

    def generer(self, m: dict, inventaire: dict | None = None, chemin: str = "") -> dict:
        from atelier.domain import projet
        from atelier.generation import bdd

        pk = ProjetKotlin()
        pk.exiger_socle()
        fonctions = pk.fonctions_portees()
        plan = self.plan(m)
        rap = bdd.reutilisation(m, inventaire)
        page_defaut = m.get("module") or plan["titre"]
        nom_classe = camel(m.get("parcours", "").replace("PU-", "") or m.get("module") or m["cle"], majuscule=True) + "BddTest"
        test_rel = chemin.replace("\\", "/") if chemin else f"{pk.src_rel}/bdd/{nom_classe}.kt"
        pages_util: dict = {}
        reutilisees, a_impl, methodes = [], [], []
        cle_xray = plan["cle_xray"] or m["cle"]
        for s in plan["scenarios"]:
            for jeu in s["jeux"] or [""]:
                nom = camel(f"{cle_xray} {s['nom']}" + (f" {jeu}" if len(s["jeux"]) > 1 else ""))
                corps = ["        R.portee.clear()", "        val v = mutableMapOf<String, Any?>()"]
                champs = sorted({e["donnee"] for e in s["etapes"] if e["donnee"]})
                if jeu:
                    corps.append(f"        Bdd.initialiserJeu({ks(jeu)}, listOf({', '.join(ks(c) for c in champs)}))")
                if any(e["intention"] == "otp" for e in s["etapes"]):
                    corps.append("        Bdd.avantOtp()")
                for e in s["etapes"]:
                    corps += self._etape(e, rap.get(e["id"], {}), fonctions, jeu, pages_util, reutilisees, a_impl, page_defaut)
                methodes.append((nom, f"    /** {doc(s['nom'])} — {cle_xray} (scénario BDD {m['cle']}" + (f", jeu {jeu}" if jeu else "")
                                 + ") */\n    @Test\n    @Xray(" + ks(cle_xray) + f")\n    fun {nom}() {{\n" + "\n".join(corps) + "\n    }"))
        p = pk.paquet
        imports = ["androidx.test.ext.junit.runners.AndroidJUnit4", f"{p}.socle.R", f"{p}.socle.Simple", "org.junit.Before", "org.junit.Test",
                   "org.junit.runner.RunWith"] + [f"{p}.pages.{x}" for x in sorted(pages_util)] + ([f"{p}.genere.*"] if reutilisees else [])
        existant = projet.lire_fichier(test_rel) if projet.safe_path(test_rel).exists() else ""
        deja = set(re.findall(r"\bfun\s+(\w+)\(", existant))
        nouvelles = [b for n, b in methodes if n not in deja]
        if existant:
            manque = [i for i in imports if f"import {i}" not in existant]
            base = existant
            if manque:  # imports ajoutés après le dernier import existant
                pos = base.rfind("\nimport ")
                fin = base.find("\n", pos + 1)
                base = base[:fin + 1] + "".join(f"import {i}\n" for i in manque) + base[fin + 1:]
            contenu = _ajouter_dans(base, nouvelles) if nouvelles else base
        else:
            contenu = (f"package {p}.bdd\n\n" + "".join(f"import {i}\n" for i in imports)
                       + f"\n/** {doc(plan['titre'])} — {MARQUE} depuis les scénarios BDD (UI Automator) : méthodes ajoutées, "
                         "jamais réécrites. */\n@RunWith(AndroidJUnit4::class)\n"
                       + f"class {nom_classe} {{\n\n    @Before\n    fun ouvrir() = Simple.ouvrirApplication()\n\n" + "\n\n".join(nouvelles) + "\n}\n")
        pages = []
        for nom, info in sorted(pages_util.items()):
            rel = f"{pk.src_rel}/pages/{nom}.kt"
            ex = projet.lire_fichier(rel) if projet.safe_path(rel).exists() else ""
            c, ajoutes = contenu_page(p, nom, info["ecran"], info["elements"], ex)
            pages.append({"chemin": rel, "page": nom, "contenu": c, "nouveau": not ex, "elements": ajoutes})
        return {"chemin": test_rel, "contenu": contenu, "pages": pages, "technologie": self.nom, "langage": "Kotlin",
                "socle": [{"chemin": f"{pk.src_rel}/bdd/Bdd.kt", "contenu": contenu_bdd(p)}],
                "classe": f"{p}.bdd.{nom_classe}", "methodes": [n for n, _ in methodes], "ajout": bool(existant),
                "methodes_ajoutees": [n for n, b in methodes if b in nouvelles],
                "fonctions_reutilisees": sorted(set(reutilisees)), "a_implementer": list(dict.fromkeys(a_impl)),
                "cle_xray": plan["cle_xray"], "tag": cle_xray, "projet_kotlin": pk.dossier}

    def ecrire(self, m: dict, g: dict, remplacer: bool = False, origine: str = "cursor") -> dict:
        """Écrit la classe de test (complétée si elle existe), les Page Objects et l'assistant Bdd.kt ; la classe entre
        en revue technique « Généré ». Une méthode existante n'est jamais réécrite."""
        from atelier.domain import projet
        from atelier.generation import studio

        for f in g["socle"]:  # assistant des tests BDD : propriété de l'atelier, réécrit
            if not projet.safe_path(f["chemin"]).exists() or projet.lire_fichier(f["chemin"]) != f["contenu"]:
                projet.ecrire_fichier(f["chemin"], f["contenu"], True)
        for pg in g["pages"]:
            if pg["nouveau"] or pg["elements"]:
                projet.ecrire_fichier(pg["chemin"], pg["contenu"], not pg["nouveau"])
        projet.ecrire_fichier(g["chemin"], g["contenu"], g["ajout"])
        revue = studio.entrer_en_revue(g["chemin"], origine)
        return {**g, "ecrit": True, "revue": revue}

    def controler(self, g: dict | None = None) -> dict:
        """Contrôle avant revue : compilation des tests Kotlin (gradle compileDebugAndroidTestKotlin)."""
        from atelier.execution import instrumentation

        return instrumentation.compiler(ProjetKotlin().dossier)
