"""Couche LOCATORS du Page Object Model : captures par écran et par plateforme, génération des
fichiers .resource Robot (mêmes clés métier sur Android et iOS, clés manquantes signalées)."""
from __future__ import annotations

import json
import re
from datetime import datetime

from atelier.discovery import carte, session
from atelier.domain import evenements, projet



def robot_escape(value: str) -> str:
    value = value.replace("\\", "\\\\")
    return re.sub(r" {2,}", lambda m: " " + "\\ " * (len(m.group()) - 1), value)


def capture_screen_locators(screen_name: str, selection: dict | None = None) -> dict:
    """Enregistre les locators de l'écran courant pour la plateforme de la session
    (correspond aux sous-tâches 'Locators Android' / 'Locators iOS').
    selection : {cle_metier: locator} pour ne garder et nommer que les éléments utiles.
    Sans selection, tous les éléments relevés sont gardés avec leur locator principal."""
    platform = session.etat["platform"]
    if selection:
        locators = dict(selection)
    else:
        locators = {e["key"]: e["locators"][0] for e in session.current_elements(200)}
    projet.SNAP_DIR.mkdir(parents=True, exist_ok=True)
    path = projet.SNAP_DIR / f"{projet.slug(screen_name)}_{platform}.json"
    path.write_text(json.dumps({"ecran": screen_name, "platform": platform,
                                "date": datetime.now().isoformat(timespec="seconds"),
                                "locators": locators}, ensure_ascii=False, indent=2), "utf-8")
    evenements.publier({"type": "locators_change"})
    evenements.publier({"type": "outil", "nom": "capture_screen_locators", "args": {"ecran": screen_name}})
    return {"fichier": str(path), "nb_locators": len(locators)}


def generate_locators_resource(screen_name: str, output_dir: str = "resources/locators",
                               overwrite: bool = False) -> dict:
    """Fusionne les captures d'un écran en un fichier .resource Robot.
    Mobile : &{LOC_<ECRAN>_ANDROID} et &{LOC_<ECRAN>_IOS}, mêmes clés métier sur les deux
    plateformes (clés manquantes signalées). Web : &{LOC_<ECRAN>_WEB} (sélecteurs Browser library)."""
    slug = projet.slug(screen_name)
    var = slug.upper()
    data = {}
    for p in ("android", "ios", "web"):
        f = projet.SNAP_DIR / f"{slug}_{p}.json"
        data[p] = json.loads(f.read_text("utf-8"))["locators"] if f.exists() else {}
    if not any(data.values()):
        raise RuntimeError("Aucune capture trouvée : lance capture_screen_locators d'abord.")
    mobile = bool(data["android"] or data["ios"])
    platforms = (["android", "ios"] if mobile else []) + (["web"] if data["web"] else [])
    all_keys = list(dict.fromkeys([*data["android"], *data["ios"]]))
    lines = ["*** Settings ***",
             f"Documentation    Locators de l'écran « {screen_name} » ({' + '.join(p.capitalize() for p in platforms)}).",
             f"...              Générés par appium-robot MCP le {datetime.now():%d/%m/%Y} — à relire avant commit.",
             "", "*** Variables ***"]
    for p in platforms:
        missing = [k for k in all_keys if k not in data[p]] if p != "web" else []
        if missing:
            lines.append(f"# TODO {p} : clés à relever -> {', '.join(missing)}")
        entries = [f"{k}={robot_escape(v)}" for k, v in data[p].items()]
        if not entries:
            lines.append(f"&{{LOC_{var}_{p.upper()}}}")
        else:
            lines.append(f"&{{LOC_{var}_{p.upper()}}}    {entries[0]}")
            lines += [f"...    {e}" for e in entries[1:]]
        lines.append("")

    target = projet.safe_path(f"{output_dir}/{slug}.resource")
    if target.exists() and not overwrite:
        raise FileExistsError(f"{target} existe déjà (overwrite=True pour remplacer).")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), "utf-8")
    evenements.publier({"type": "locators_change"})
    evenements.publier({"type": "outil", "nom": "generate_locators_resource", "args": {"fichier": str(target)}})
    return {"fichier": str(target), "cles": all_keys or list(data["web"]),
            "manquants_android": [k for k in all_keys if k not in data["android"]] if mobile else [],
            "manquants_ios": [k for k in all_keys if k not in data["ios"]] if mobile else []}


def add_screen_locator(screen_name: str, key: str, locator: str, platform: str = "") -> dict:
    """Ajoute ou remplace une clé dans les locators capturés d'un écran (plateforme de la session
    par défaut). Sert à corriger un locator sans tout recapturer."""
    p = (platform or session.etat["platform"] or "").lower()
    if p not in ("android", "ios", "web"):
        raise ValueError("Plateforme inconnue : ouvre une session ou précise platform.")
    projet.SNAP_DIR.mkdir(parents=True, exist_ok=True)
    path = projet.SNAP_DIR / f"{projet.slug(screen_name)}_{p}.json"
    data = json.loads(path.read_text("utf-8")) if path.exists() else {"ecran": screen_name, "platform": p,
                                                                      "locators": {}}
    data["locators"][key] = locator
    data["date"] = datetime.now().isoformat(timespec="seconds")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    evenements.publier({"type": "locators_change"})
    return {"ecran": screen_name, "platform": p, "cle": key, "locator": locator}


def export_screen_resource(ecran: str, output_dir: str = "resources/locators") -> str:
    """.resource d'un écran depuis la carte (locator principal + secours par plateforme)."""
    e = carte.ecran(ecran)
    p = carte.exporter_resource(e["id"], projet.safe_path(f"{output_dir}/{e.get('nom') or e['id']}.resource"))
    evenements.publier({"type": "outil", "nom": "generate_locators_resource", "args": {"fichier": str(p)}})
    return str(p)


def captures() -> dict:
    """Locators capturés par écran et par plateforme (onglet Locators de l'interface)."""
    ecrans: dict = {}
    d = projet.SNAP_DIR
    for f in sorted(d.glob("*.json")) if d.exists() else []:
        data = json.loads(f.read_text("utf-8"))
        ecrans.setdefault(data["ecran"], {"android": {}, "ios": {}, "web": {}})[data["platform"]] = data["locators"]
    return ecrans
