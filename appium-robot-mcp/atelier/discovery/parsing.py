"""Lecture des hiérarchies mobiles (XML Appium) : éléments significatifs et locators AppiumLibrary
classés du plus robuste au plus fragile (Android classique, Jetpack Compose avec ou sans testTag, iOS)."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from atelier.domain.projet import slug


# Identifiant de test Jetpack Compose (Modifier.testTag + testTagsAsResourceId) : le resource-id est le tag tel quel,
# sans « package:id/ ». Le locator id= d'Appium complète le nom avec le package de l'application et ne le trouverait
# pas (sauf réglage disableIdLocatorAutocompletion) : on passe par un sélecteur UiAutomator, qui marche sans réglage.
UIA_ID = 'android=new UiSelector().resourceId("'


def locator_id_android(rid: str) -> str:
    if ":id/" in rid:
        return f"id={rid}"
    return UIA_ID + rid.replace("\\", "\\\\").replace('"', '\\"') + '")'


def _xq(value: str) -> str:
    """Quote XPath sûre (gère les apostrophes, fréquentes en français)."""
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    return "concat(" + ", \"'\", ".join(f"'{p}'" for p in parts) + ")"


def _abs_xpath(node, parents) -> str:
    steps = []
    while node in parents:
        parent = parents[node]
        same = [c for c in parent if c.tag == node.tag]
        steps.append(f"{node.tag}[{same.index(node) + 1}]")
        node = parent
    return "//" + "/".join(reversed(steps)) if steps else "//*"


def _kind(cls: str) -> str:
    c = cls.lower()
    if "edittext" in c or "textfield" in c or "securetextfield" in c:
        return "champ"
    if "switch" in c or "checkbox" in c or "radio" in c:
        return "case"
    if "statictext" in c or c.endswith("textview"):
        return "texte"
    if "image" in c:
        return "image"
    return "bouton"


def parse_elements(source: str, platform: str) -> list[dict]:
    root = ET.fromstring(source.encode("utf-8"))
    parents = {c: p for p in root.iter() for c in p}
    elements: list[dict] = []

    for node in root.iter():
        a = node.attrib
        locs: list[str] = []
        ancre, attr_lib = "", ("", "")
        if platform == "android":
            if a.get("displayed", "true") == "false":
                continue
            rid, text, desc = a.get("resource-id", ""), a.get("text", ""), a.get("content-desc", "")
            clickable = a.get("clickable") == "true"
            cls = a.get("class", node.tag)
            if "EditText" in cls or "TextField" in cls:
                # champ de saisie : son texte est la VALEUR saisie (identifiant, n° de contrat…), jamais un locator ni un
                # libellé — aucune donnée client dans la carte ; le champ reste repéré par son id ou son libellé voisin
                text = ""
            if not (rid or text or desc or clickable):
                continue
            if rid:
                locs.append(locator_id_android(rid))
            tag = bool(rid) and ":id/" not in rid  # testTag Compose
            if desc:
                locs.append(f"accessibility_id={desc}")
            if text:
                locs.append(f"xpath=//*[@text={_xq(text)}]")
            enfant = ""
            if clickable and not (text or desc) and (tag or not rid):  # bouton Compose (avec ou sans testTag) : libellé porté par un enfant
                enfant = next((n.attrib.get("text") or n.attrib.get("content-desc") for n in node.iter()
                               if n is not node and (n.attrib.get("text") or n.attrib.get("content-desc"))), "")
                if enfant:
                    locs.append(f"xpath=//*[@text={_xq(enfant)}]/ancestor-or-self::*[@clickable='true'][1]")
            label = text or desc or enfant or rid.split("/")[-1]
            base = rid.split("/")[-1] if rid else (desc or text or enfant)
            attr_lib = ("text", text) if text else ("content-desc", desc) if desc else ("", "")
            p = parents.get(node)  # conteneur identifié le plus proche : borne un libellé qui se répète
            while p is not None and not ancre:
                ancre = p.attrib.get("resource-id", "")
                p = parents.get(p)
            bounds = a.get("bounds", "")
            nums = [int(n) for n in re.findall(r"-?\d+", bounds)]
            rect = [nums[0], nums[1], nums[2] - nums[0], nums[3] - nums[1]] if len(nums) == 4 else None
        else:
            if a.get("visible") == "false":
                continue
            name, label_attr = a.get("name", ""), a.get("label", "")
            cls = a.get("type", node.tag)
            interactive = any(t in cls for t in ("Button", "TextField", "Switch", "Cell", "Link"))
            if cls in ("XCUIElementTypeApplication", "XCUIElementTypeWindow"):
                continue
            if not (name or label_attr or interactive):
                continue
            if name:
                locs.append(f"accessibility_id={name}")
            if label_attr and label_attr != name:
                locs.append(f'nsp=label == "{label_attr}"')
            if label_attr:
                locs.append(f'chain=**/{cls}[`label == "{label_attr}"`]')
            label = label_attr or name
            base = name or label_attr
            bounds = f"[{a.get('x')},{a.get('y')}][{a.get('width')}x{a.get('height')}]"
            try:
                rect = [float(a.get(k)) for k in ("x", "y", "width", "height")]
            except (TypeError, ValueError):
                rect = None

        if not locs:
            locs.append(f"xpath={_abs_xpath(node, parents)}")
        kind = _kind(cls)
        nom = slug(base or cls.split('.')[-1])
        if platform == "android" and locs[0].startswith(UIA_ID) and nom.startswith(f"{kind}_"):
            cle = nom  # un testTag déjà nommé comme la clé métier (« champ_montant ») redonne exactement cette clé
        else:
            cle = f"{kind}_{nom}"
        elements.append({
            "key": cle,
            "type": kind,
            "classe": cls.split(".")[-1],
            "libelle": label,
            "locators": locs,
            "bounds": bounds,
            "rect": rect,
            "_ancre": ancre, "_lib": attr_lib,
        })

    if platform == "android":
        _android_sans_ids(elements)
    # Unicité des clés + signalement des locators principaux ambigus
    seen: dict[str, int] = {}
    primary_count: dict[str, int] = {}
    for e in elements:
        primary_count[e["locators"][0]] = primary_count.get(e["locators"][0], 0) + 1
    for e in elements:
        n = seen.get(e["key"], 0)
        seen[e["key"]] = n + 1
        if n:
            e["key"] = f"{e['key']}_{n + 1}"
        e["locator_unique"] = primary_count[e["locators"][0]] == 1
    _borner_ambigus(elements)
    for e in elements:
        e.pop("_ancre", None)
        e.pop("_lib", None)
    return elements


def _borner_ambigus(elements: list[dict]):
    """Android : un libellé qui se répète (même texte dans deux cartes, Compose ou non) donne un locator principal
    ambigu. S'il a un conteneur identifié (resource-id ou testTag) où il est seul, le locator borné à ce conteneur passe
    en tête ; l'ancien reste en secours."""
    groupes: dict[tuple, int] = {}
    for e in elements:
        if e.get("_ancre") and e.get("_lib", ("", ""))[0]:
            groupes[(e["_ancre"], *e["_lib"])] = groupes.get((e["_ancre"], *e["_lib"]), 0) + 1
    for e in elements:
        attr, val = e.get("_lib") or ("", "")
        if e.get("locator_unique", True) or not e.get("_ancre") or not attr or groupes.get((e["_ancre"], attr, val)) != 1:
            continue
        borne = f"xpath=//*[@resource-id={_xq(e['_ancre'])}]//*[@{attr}={_xq(val)}]"
        if borne not in e["locators"]:
            e["locators"].insert(0, borne)
            e["locator_unique"] = True


def _uia(text: str) -> str:
    return 'android=new UiSelector().text("' + text.replace("\\", "\\\\").replace('"', '\\"') + '")'


def _android_sans_ids(elements: list[dict]):
    """Jetpack Compose sans testTag : pas de resource-id. On privilégie
    - pour un bouton / texte : UiSelector().text(...) (plus rapide et lisible qu'un XPath) ;
    - pour un champ : locator RELATIF au libellé qui le précède (sa valeur change à la saisie).
    Avec un testTag, le champ garde ce locator relatif en SECOURS : c'est lui qui permet de reconnaître l'élément déjà
    cartographié quand son identifiant arrive."""
    dernier_libelle = ""
    libre = False  # le dernier libellé n'a pas encore servi d'ancre à un champ (deux champs de suite : pas d'ancre sûre)
    for e in elements:
        locs = e["locators"]
        a_id = any(l.startswith(("id=", "accessibility_id=", UIA_ID)) for l in locs)
        libelle = e.get("libelle") or ""
        statique = libelle and not re.search(r"\d[\d\s.,]*\d|•|@", libelle) and len(libelle) <= 40
        if e["type"] == "champ" and not a_id:
            texte = [l for l in locs if l.startswith("xpath=//*[@text")]
            autres = [l for l in locs if l not in texte]
            rel = [f"xpath=//*[@text={_xq(dernier_libelle)}]/following::android.widget.EditText[1]"] if dernier_libelle else []
            e["locators"] = rel + autres + texte or locs
            if dernier_libelle:
                e["key"] = f"champ_{slug(dernier_libelle)}"
        elif e["type"] == "champ" and dernier_libelle and libre:
            # champ identifié (resource-id ou testTag) : l'ancre reste en secours ; c'est elle qui relie le champ déjà
            # cartographié à celui dont l'identifiant vient d'arriver ou d'être renommé
            rel = f"xpath=//*[@text={_xq(dernier_libelle)}]/following::android.widget.EditText[1]"
            e["locators"] = locs + ([rel] if rel not in locs else [])
        elif not a_id and libelle and statique and e["type"] != "champ":
            e["locators"] = [_uia(libelle)] + locs
        if e["type"] == "champ":
            libre = False
        if e["type"] == "texte" and statique:
            dernier_libelle, libre = libelle, True
