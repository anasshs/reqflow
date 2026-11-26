"""Plan d'automatisation : ce qu'un scénario BDD demande de faire, indépendamment de la technologie qui l'automatisera
(Robot + Appium, Robot web, UI Automator, Espresso : generation/technologies).

Chaque étape du scénario devient une INTENTION, rattachée à l'écran et à l'élément de la carte, et au champ du jeu de
données qu'elle utilise :
  ouvrir     l'étape d'entrée (Given) qui amène sur un écran ou dans un état (connexion, écran de départ)
  toucher    toucher / cliquer / choisir / valider un élément
  saisir     renseigner un champ avec une valeur du jeu de données (« secret » : jamais journalisée)
  revenir    retour arrière
  otp        code de confirmation reçu par SMS (mode arret / validation selon l'environnement)
  verifier   constat (Then, ou étape marquée assertion) : présence, valeur
  appel      étape sans élément de la carte ni intention reconnue : un élément du socle de la technologie à réutiliser
             ou à écrire (jamais un faux succès)
Le classement reprend les motifs de la génération Robot (pom.ACTION / SAISIE / RETOUR / SECRET) : une même étape a la
même intention, quelle que soit la technologie. Le plan ne contient ni code, ni nom de keyword, ni syntaxe de locator
d'une bibliothèque : la technologie traduit l'élément (resource-id, accessibility id, texte) dans sa propre syntaxe.
"""
from __future__ import annotations

import re

from atelier.generation import pom

OTP = re.compile(r"(?i)\botp\b|code (de confirmation|re[çc]u|sms)|code par sms")
INTENTIONS = ("ouvrir", "toucher", "saisir", "revenir", "otp", "sms", "verifier", "appel")
# sms : étape prédéfinie SMS par adb autre que l'OTP (repère avant l'envoi, lien reçu ouvert ou gardé : etapes_sms.py)


def element(locator: str) -> dict:
    """Identité d'un élément, lue dans son locator (toutes syntaxes Appium / UiSelector / XPath / web) :
    {resource_id, accessibility_id, texte}. Vide si le locator n'en porte aucune."""
    from atelier.discovery.connaissance import identifiant_locator

    ident = identifiant_locator(locator or "")
    genre, _, valeur = ident.partition(":")
    out = {"resource_id": valeur if genre == "rid" else "", "accessibility_id": valeur if genre == "acc" else "",
           "texte": valeur if genre == "txt" else ""}
    if not ident:
        m = re.search(r"data-testid=[\"']?([\w-]+)", locator or "")
        if m:
            out["resource_id"] = m.group(1)
    return out


def intention(etape: dict) -> str:
    from atelier.generation import etapes_sms

    texte, champ = etape.get("texte", ""), etape.get("jdd", "")
    predef = etapes_sms.reconnaitre(etape)
    if predef:
        return "otp" if predef == "otp" else "sms"
    if pom.RETOUR.match(texte):
        return "revenir"
    if OTP.search(texte):
        return "otp"
    if pom.SAISIE.match(texte) and champ:
        return "saisir"
    if pom.ACTION.match(texte):
        return "toucher"
    if etape.get("assertion") or etape.get("type") == "then":
        return "verifier"
    if etape.get("type") == "given":
        return "ouvrir"
    return "verifier" if etape.get("locator") else "appel"


def etape(e: dict) -> dict:
    """Étape du plan : intention, écran, élément de la carte, donnée du jeu (secret ou non), texte d'origine."""
    from atelier.generation import etapes_sms

    champ = e.get("jdd") or ""
    loc = e.get("locator") or ""
    return {"id": e.get("id", ""), "mot": e.get("type", ""), "texte": e.get("texte", ""), "intention": intention(e),
            "ecran": e.get("ecran") or "", "locator": loc, "element": element(loc) if loc else {},
            "donnee": champ, "secret": bool(champ and pom.SECRET.search(champ)),
            "attendu": e.get("resultat_attendu") or "",
            "sms": etapes_sms.reconnaitre(e),  # étape prédéfinie SMS (etapes_sms.py), « » sinon
            # décision « réutiliser sans réécrire » : élément du socle à appeler, le texte de l'étape (Xray) reste tel quel
            "reutilise": (e.get("keyword_lie") or {}).get("keyword", "")}


def construire(m: dict) -> dict:
    """Plan d'automatisation d'un scénario BDD (modèle de generation/bdd.py) : un plan par scénario, une variante par
    jeu de données du tableau d'exemples (sinon le jeu du test)."""
    from atelier.generation import bdd, conception

    cle_xray = conception.cle_xray_du_scenario(m["cle"]) or ""
    scenarios = []
    for s in m.get("scenarios") or []:
        etapes = [etape(e) for e in s.get("etapes") or []]
        scenarios.append({"nom": s.get("nom", ""), "type": s.get("type", "principal"),
                          "tags": list(dict.fromkeys([*(m.get("tags") or []), *(s.get("tags") or [])])),
                          "jeux": bdd.jeux_des_exemples(s) or ([m["jdd"].upper()] if m.get("jdd") else []),
                          "etapes": etapes})
    toutes = [e for s in scenarios for e in s["etapes"]]
    return {"cle": m["cle"], "cle_xray": cle_xray, "titre": m.get("titre") or m.get("feature") or m["cle"],
            "module": m.get("module") or "", "parcours": m.get("parcours") or "", "jdd": m.get("jdd") or "",
            "scenarios": scenarios,
            "bilan": {"etapes": len(toutes), **{i: sum(e["intention"] == i for e in toutes) for i in INTENTIONS},
                      "sans_element": sum(1 for e in toutes if e["intention"] in ("toucher", "saisir") and not e["locator"])}}
