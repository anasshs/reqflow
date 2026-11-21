"""Robustesse des locators : la politique unique de l'atelier (web, Android natif ou Jetpack Compose, iOS).

Un test livré doit être rejouable sans retouche : son locator principal désigne UN seul élément, ne dépend ni de la
position dans la page, ni d'un identifiant généré, ni (si possible) d'un libellé qui change avec la langue. Ce module
note un locator, classe une liste du plus robuste au plus fragile et rend les règles en clair : la Discovery,
la revue des scripts (contrôle « locators ») et Cursor (outil MCP locator_robustesse, règle locators.mdc) appliquent
la même politique.

Niveaux : Stable (identifiant posé pour les tests), Reliable (attribut sémantique, rôle, zone bornée), Fragile (texte
seul, XPath, position). Score de 1 à 5 pour trier.
"""
from __future__ import annotations

import re

# identifiants générés par les frameworks (React useId, MUI, Ember, Angular, hachages) : changent d'un rendu à l'autre
_ID_GENERE = re.compile(r"(^|[-_:])(mui|ember|ng|radix|headlessui|react)[-_:]?\w*\d|\d{3,}|^:r\w*:$|^[0-9a-f]{8,}$", re.I)
_POSITION = re.compile(r":nth|nth=|\[\d+\]|:eq\(|nth-of-type|nth-child")

REGLES = {
    "web": {
        "ordre": ["data-testid=… (identifiant de test posé par les développeurs)", "id=… stable (sans chiffres générés)",
                  "css=input[name=\"…\"] ou [placeholder=\"…\"] pour un champ", "role=button[name=\"…\"] (rôle + nom accessible)",
                  "css=<zone> a[href=\"…\"] ou css=<zone> >> text=\"…\" quand un libellé se répète (en-tête, pied de page…)",
                  "text=\"…\" seulement s'il est unique et court"],
        "interdits": ["XPath et chemins CSS (body > div:nth-of-type…)", "index ou position (nth=, :nth-child, [2])",
                      "identifiants générés (mui-123, :r1:, ember45, hachages)", "texte long ou qui change (montants, dates)"],
    },
    "android": {
        "ordre": ["id=<package>:id/… (resource-id natif)",
                  "Jetpack Compose : testTag exposé en resource-id (Modifier.testTag + semantics { testTagsAsResourceId = true }) ; "
                  "le demander aux développeurs, c'est le seul identifiant stable en Compose",
                  "accessibility_id=… (content-desc ; attention aux traductions)",
                  "android=new UiSelector().text(\"…\") pour un bouton Compose sans testTag",
                  "locator relatif à un libellé voisin (champ Compose sans testTag), en secours"],
        "interdits": ["XPath absolu ou indexé (//…/android.view.View[3])", "bounds / coordonnées",
                      "texte seul s'il apparaît plusieurs fois à l'écran (le borner à un conteneur identifié)"],
    },
    "ios": {
        "ordre": ["accessibility_id=… (accessibilityIdentifier posé par les développeurs)", "nsp=label == \"…\" (prédicat)",
                  "chain=**/XCUIElementType…[`label == \"…\"`] (class chain)"],
        "interdits": ["XPath", "index ou position"],
    },
    "commun": ["Vérifier chaque locator principal sur l'écran : un seul élément trouvé (check_locator → nb_trouves == 1).",
               "Mêmes clés métier sur Android, iOS et web ; un locator de secours par clé quand le principal est fragile "
               "(keyword « Localiser » du socle).",
               "Aucun locator dans les tests : ils vivent dans les fichiers de locators de la page (Page Object Model)."],
}


def _plateforme(v: str, plateforme: str) -> str:
    if plateforme:
        return plateforme
    if v.startswith(("android=", "-android")) or ":id/" in v:
        return "android"
    if v.startswith(("nsp=", "chain=", "-ios")):
        return "ios"
    if v.startswith(("data-testid=", "css=", "role=", "text=")):
        return "web"
    return ""


def evaluer(locator: str, plateforme: str = "", unique: bool | None = None) -> dict:
    """{locator, strategie, niveau, score, raisons, conseil} ; unique : résultat d'un check_locator s'il est connu."""
    v = (locator or "").strip()
    p = _plateforme(v, plateforme)
    strat = "xpath" if v.startswith(("//", "(//")) else v.split("=", 1)[0] if "=" in v.split("[", 1)[0] else "css"
    valeur = v.split("=", 1)[1] if "=" in v and strat != "css" else v
    raisons, score = [], 3
    if strat in ("data-testid", "accessibility_id"):
        score = 4 if strat == "accessibility_id" and p == "android" else 5
        raisons.append("identifiant posé pour les tests" if score == 5 else "content-desc : stable, mais peut suivre la langue")
    elif strat == "id":
        if _ID_GENERE.search(valeur.split(":id/")[-1]):
            score = 1
            raisons.append("identifiant qui semble généré (chiffres, préfixe de framework) : change d'un rendu à l'autre")
        else:
            score = 5
            raisons.append("testTag Compose exposé en resource-id" if p == "android" and ":id/" not in valeur
                           else "identifiant technique stable")
    elif strat == "android":
        if ".resourceId(" in v:
            score, _ = 5, raisons.append("testTag Compose lu par UiSelector")
        elif ".text(" in v or ".description(" in v:
            score, _ = 3, raisons.append("UiSelector par libellé : lisible, dépend du texte affiché")
        else:
            score, _ = 2, raisons.append("UiSelector sans identifiant")
    elif strat in ("nsp", "chain"):
        score, _ = 3, raisons.append("prédicat iOS sur le libellé")
    elif strat == "role":
        score, _ = 4, raisons.append("rôle et nom accessible")
    elif strat == "css":
        if re.search(r"\[name=|\[placeholder=", v) and not _POSITION.search(v):
            score, _ = 4, raisons.append("attribut sémantique du champ")
        elif re.search(r"a\[href=", v) or ">> text=" in v:
            score, _ = 3, raisons.append("borné à une zone de la page ou à un lien")
        elif v.startswith(("css=body", "css=html")):
            score, _ = 1, raisons.append("chemin dans l'arbre de la page : casse au moindre changement de mise en page")
        else:
            score, _ = 3, raisons.append("sélecteur CSS")
    elif strat == "text":
        score = 2
        raisons.append("texte seul : dépend du libellé (traduction, reformulation)")
        if len(valeur) > 30:
            score, _ = 1, raisons.append("texte long")
    elif strat == "xpath":
        score = 2 if ("@text" in v or "@label" in v or "@content-desc" in v) and not re.search(r"/\w+\[\d+\]", v) else 1
        raisons.append("XPath sur un libellé" if score == 2 else "XPath positionnel : le plus fragile")
    if _POSITION.search(v) and score > 1:
        score = 1
        raisons.append("dépend de la position (index)")
    if unique is False:
        score = min(score, 1)
        raisons.append("désigne plusieurs éléments : le borner à un conteneur identifié")
    niveau = "Stable" if score >= 5 else "Reliable" if score >= 3 else "Fragile"
    conseil = "" if niveau != "Fragile" else (
        "Demander un testTag exposé en resource-id (Compose) ou un resource-id ; sinon UiSelector par texte avec un secours."
        if p == "android" else "Demander un accessibilityIdentifier ; sinon un prédicat sur le libellé." if p == "ios"
        else "Préférer data-testid, id stable, name/placeholder ou rôle ; si le texte se répète, le borner à sa zone (en-tête, pied…).")
    return {"locator": v, "plateforme": p, "strategie": strat, "niveau": niveau, "score": score, "raisons": raisons, "conseil": conseil}


def classer(locators: list[str], plateforme: str = "") -> list[str]:
    """Du plus robuste au plus fragile ; ordre d'origine conservé à robustesse égale."""
    return [x for _, _, x in sorted((-evaluer(l, plateforme)["score"], i, l) for i, l in enumerate(locators))]


def regles(plateforme: str = "") -> dict:
    """Règles en clair, pour une plateforme (web, android, ios) ou toutes."""
    if plateforme in REGLES and plateforme != "commun":
        return {plateforme: REGLES[plateforme], "commun": REGLES["commun"]}
    return REGLES
