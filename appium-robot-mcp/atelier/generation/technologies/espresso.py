"""Technologie Espresso (phase F, docs/AUTOMATISATION_MULTI_CIBLES.md § 3).

Espresso s'exécute DANS le processus de l'application : les tests se compilent avec son code source. L'atelier n'écrit que
dans le projet de tests (invariant : fichiers limités au projet) : les tests sont générés dans
<projet de tests>/espresso/src/androidTest/java/<paquet>/, prêts à intégrer au module androidTest du dépôt de
l'application (ou exécutés si automatisation.projet_espresso désigne un projet Gradle du dépôt de tests qui l'inclut).

Même plan d'automatisation que les autres technologies. Sélecteurs : identifiant résolu à l'exécution
(resources.getIdentifier : aucune dépendance à la classe R de l'application), description d'accessibilité, texte.
Un élément Compose sans identifiant de vue (testTag) demande la règle Compose : étape « à implémenter », nommée.
"""
from __future__ import annotations

import re

from atelier.generation.technologies import Technologie
from atelier.generation.technologies.kotlin import MARQUE, UiAutomator, _ajouter_dans, camel, doc, ks

IMPORTS = ["android.app.Activity", "androidx.test.core.app.ActivityScenario", "androidx.test.ext.junit.runners.AndroidJUnit4",
           "androidx.test.platform.app.InstrumentationRegistry", "androidx.test.espresso.Espresso.onView",
           "androidx.test.espresso.Espresso.pressBack", "androidx.test.espresso.action.ViewActions.click",
           "androidx.test.espresso.action.ViewActions.closeSoftKeyboard", "androidx.test.espresso.action.ViewActions.replaceText",
           "androidx.test.espresso.assertion.ViewAssertions.matches", "androidx.test.espresso.matcher.ViewMatchers.isDisplayed",
           "androidx.test.espresso.matcher.ViewMatchers.withContentDescription", "androidx.test.espresso.matcher.ViewMatchers.withText",
           "org.hamcrest.Matchers.containsString", "org.junit.Before", "org.junit.Test", "org.junit.runner.RunWith"]


def vue(etape: dict) -> str:
    """Matcher Espresso d'un élément ; vide si l'élément n'a pas de quoi être visé par onView (testTag Compose, aucun)."""
    e, loc = etape.get("element") or {}, etape.get("locator") or ""
    if e.get("resource_id"):
        if ":id/" not in loc and not loc.startswith("id="):
            return ""  # testTag Compose : onNodeWithTag (règle Compose), pas onView
        return f"Vue.id({ks(e['resource_id'])})"
    if e.get("accessibility_id"):
        return f"withContentDescription({ks(e['accessibility_id'])})"
    if e.get("texte"):
        return f"withText({ks(e['texte'])})"
    return ""


def contenu_vue(paquet: str) -> str:
    lignes = [
        f"package {paquet}", "",
        "import android.view.View",
        "import androidx.test.espresso.matcher.ViewMatchers.withId",
        "import androidx.test.platform.app.InstrumentationRegistry",
        "import org.hamcrest.Matcher",
        "import org.junit.Assume", "",
        "/** Clé du test Xray que ce test automatise. */",
        "@Retention(AnnotationRetention.RUNTIME)",
        "@Target(AnnotationTarget.FUNCTION)",
        "annotation class Xray(val cle: String)", "",
        f"/** {MARQUE} (Espresso) : ne pas modifier, réécrit à chaque génération. Données : « -e jdd.<JEU>.<champ> valeur ». */",
        "object Vue {",
        "    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext",
        "    private val args get() = InstrumentationRegistry.getArguments()", "",
        "    /** Vue par son identifiant (« btnContinue »), résolu dans l'application testée, sans dépendre de sa classe R. */",
        "    fun id(nom: String): Matcher<View> {",
        "        val i = ctx.resources.getIdentifier(nom, \"id\", ctx.packageName)",
        "        if (i == 0) throw AssertionError(\"Identifiant inconnu dans l'application : $nom\")",
        "        return withId(i)",
        "    }", "",
        "    fun donnee(jeu: String, champ: String): String {",
        "        val v = args.getString(\"jdd.$jeu.$champ\") ?: \"\"",
        "        Assume.assumeTrue(\"Donnée jdd.$jeu.$champ non fournie\", v.isNotEmpty())",
        "        return v",
        "    }", "",
        "    fun otpMode(): String = args.getString(\"otp_mode\") ?: \"arret\"", "",
        "    fun aImplementer(etape: String): Nothing = throw AssertionError(\"Étape à implémenter : $etape\")",
        "}", ""]
    return "\n".join(lignes)


class Espresso(Technologie):
    def __init__(self):
        super().__init__("espresso", "Espresso (Kotlin)", ["android"], "Kotlin",
                         "instrumentation Android, dans le processus de l'application",
                         raison="exécution avec le code source de l'application (module androidTest de son dépôt)",
                         prerequis=["code source de l'application (exécution)", "JDK 17", "SDK Android", "Gradle"])

    @staticmethod
    def config() -> dict:
        from atelier.discovery import carte

        try:
            cfg = carte.config_app() if carte.app_courante() else {}
        except Exception:  # noqa: BLE001
            cfg = {}
        a = (cfg or {}).get("automatisation") or {}
        pkg_app = re.sub(r"\.dev$", "", ((cfg or {}).get("android") or {}).get("app_package") or "app")
        return {"paquet": a.get("paquet_espresso") or pkg_app + ".tnr", "dossier": (a.get("projet_espresso") or "espresso").strip("/")}

    def _etape(self, e: dict, jeu: str, a_impl: list) -> list[str]:
        lignes = [f"        // {e['mot'].capitalize()} {e['texte']}"]
        v, i = vue(e), e["intention"]
        if i == "revenir":
            return lignes + ["        pressBack()"]
        if i == "otp":
            return lignes + ['        if (Vue.otpMode() != "validation") return  // arrêt sur l\'écran OTP, rien n\'est validé']
        if i == "sms" and e.get("sms") == "preparer_sms":
            return lignes + ["        // repère SMS : sans objet tant que la lecture des SMS n'est pas portée en Espresso"]
        if i == "sms":  # lecture des SMS (adb) : pas encore portée en Espresso, jamais un faux succès
            a_impl.append(e["texte"])
            return lignes + [f"        Vue.aImplementer({ks(e['texte'])})"]
        if not v:
            a_impl.append(e["texte"])
            return lignes + [f"        Vue.aImplementer({ks(e['texte'])})"]
        if i == "toucher":
            return lignes + [f"        onView({v}).perform(click())"]
        if i == "saisir":
            valeur = f"Vue.donnee({ks(jeu)}, {ks(e['donnee'])})" if jeu else ks("")
            return lignes + [f"        onView({v}).perform(replaceText({valeur}), closeSoftKeyboard())"]
        if e.get("attendu"):
            return lignes + [f"        onView({v}).check(matches(withText(containsString({ks(e['attendu'])}))))"]
        return lignes + [f"        onView({v}).check(matches(isDisplayed()))"]

    def generer(self, m: dict, inventaire: dict | None = None, chemin: str = "") -> dict:
        from atelier.domain import projet

        c = self.config()
        plan = self.plan(m)
        paquet, src = c["paquet"], f"{c['dossier']}/src/androidTest/java/{c['paquet'].replace('.', '/')}"
        nom_classe = camel(m.get("parcours", "").replace("PU-", "") or m.get("module") or m["cle"], majuscule=True) + "EspressoTest"
        test_rel = chemin.replace("\\", "/") if chemin else f"{src}/{nom_classe}.kt"
        cle_xray = plan["cle_xray"] or m["cle"]
        a_impl, methodes = [], []
        for s in plan["scenarios"]:
            for jeu in s["jeux"] or [""]:
                nom = camel(f"{cle_xray} {s['nom']}" + (f" {jeu}" if len(s["jeux"]) > 1 else ""))
                corps = [l for e in s["etapes"] for l in self._etape(e, jeu, a_impl)]
                methodes.append((nom, f"    /** {doc(s['nom'])} — {cle_xray} (scénario BDD {m['cle']}) */\n    @Test\n    @Xray({ks(cle_xray)})\n"
                                      f"    fun {nom}() {{\n" + "\n".join(corps) + "\n    }"))
        existant = projet.lire_fichier(test_rel) if projet.safe_path(test_rel).exists() else ""
        deja = set(re.findall(r"\bfun\s+(\w+)\(", existant))
        nouvelles = [b for n, b in methodes if n not in deja]
        if existant:
            contenu = _ajouter_dans(existant, nouvelles) if nouvelles else existant
        else:
            contenu = (f"package {paquet}\n\n" + "".join(f"import {i}\n" for i in IMPORTS)
                       + f"\n/** {doc(plan['titre'])} — {MARQUE} depuis les scénarios BDD (Espresso, dans le processus de l'application). */\n"
                       + f"@RunWith(AndroidJUnit4::class)\nclass {nom_classe} {{\n\n    @Before\n    fun ouvrir() {{\n"
                       + "        val ctx = InstrumentationRegistry.getInstrumentation().targetContext\n"
                       + "        ActivityScenario.launch<Activity>(ctx.packageManager.getLaunchIntentForPackage(ctx.packageName)!!)\n    }\n\n"
                       + "\n\n".join(nouvelles) + "\n}\n")
        return {"chemin": test_rel, "contenu": contenu, "pages": [], "technologie": self.nom, "langage": "Kotlin",
                "socle": [{"chemin": f"{src}/Vue.kt", "contenu": contenu_vue(paquet)}],
                "classe": f"{paquet}.{nom_classe}", "methodes": [n for n, _ in methodes], "ajout": bool(existant),
                "methodes_ajoutees": [n for n, b in methodes if b in nouvelles], "fonctions_reutilisees": [],
                "a_implementer": list(dict.fromkeys(a_impl)), "cle_xray": plan["cle_xray"], "tag": cle_xray,
                "projet_kotlin": c["dossier"], "a_integrer": "module androidTest du dépôt de l'application"}

    def ecrire(self, m: dict, g: dict, remplacer: bool = False, origine: str = "cursor") -> dict:
        return UiAutomator.ecrire(self, m, g, remplacer, origine)
