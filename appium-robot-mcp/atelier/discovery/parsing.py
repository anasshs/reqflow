"""Lecture des hiérarchies mobiles (XML Appium) : éléments significatifs et locators AppiumLibrary
classés du plus robuste au plus fragile (Android classique, Jetpack Compose sans testTag, iOS)."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from atelier.domain.projet import slug


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
        if platform == "android":
            if a.get("displayed", "true") == "false":
                continue
            rid, text, desc = a.get("resource-id", ""), a.get("text", ""), a.get("content-desc", "")
            clickable = a.get("clickable") == "true"
            cls = a.get("class", node.tag)
            if not (rid or text or desc or clickable):
                continue
            if rid:
                locs.append(f"id={rid}")
            if desc:
                locs.append(f"accessibility_id={desc}")
            if text:
                locs.append(f"xpath=//*[@text={_xq(text)}]")
            enfant = ""
            if clickable and not (rid or text or desc):  # bouton Compose : le libellé est porté par un enfant
                enfant = next((n.attrib.get("text") or n.attrib.get("content-desc") for n in node.iter()
                               if n is not node and (n.attrib.get("text") or n.attrib.get("content-desc"))), "")
                if enfant:
                    locs.append(f"xpath=//*[@text={_xq(enfant)}]/ancestor-or-self::*[@clickable='true'][1]")
            label = text or desc or enfant or rid.split("/")[-1]
            base = rid.split("/")[-1] if rid else (desc or text or enfant)
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
        elements.append({
            "key": f"{kind}_{slug(base or cls.split('.')[-1])}",
            "type": kind,
            "classe": cls.split(".")[-1],
            "libelle": label,
            "locators": locs,
            "bounds": bounds,
            "rect": rect,
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
    return elements


def _uia(text: str) -> str:
    return 'android=new UiSelector().text("' + text.replace("\\", "\\\\").replace('"', '\\"') + '")'


def _android_sans_ids(elements: list[dict]):
    """Jetpack Compose sans testTag : pas de resource-id. On privilégie
    - pour un bouton / texte : UiSelector().text(...) (plus rapide et lisible qu'un XPath) ;
    - pour un champ : locator RELATIF au libellé qui le précède (sa valeur change à la saisie)."""
    dernier_libelle = ""
    for e in elements:
        locs = e["locators"]
        a_id = any(l.startswith(("id=", "accessibility_id=")) for l in locs)
        libelle = e.get("libelle") or ""
        statique = libelle and not re.search(r"\d[\d\s.,]*\d|•|@", libelle) and len(libelle) <= 40
        if e["type"] == "champ" and not a_id:
            texte = [l for l in locs if l.startswith("xpath=//*[@text")]
            autres = [l for l in locs if l not in texte]
            rel = [f"xpath=//*[@text={_xq(dernier_libelle)}]/following::android.widget.EditText[1]"] if dernier_libelle else []
            e["locators"] = rel + autres + texte or locs
            if dernier_libelle:
                e["key"] = f"champ_{slug(dernier_libelle)}"
        elif not a_id and libelle and statique and e["type"] != "champ":
            e["locators"] = [_uia(libelle)] + locs
        if e["type"] == "texte" and statique:
            dernier_libelle = libelle
