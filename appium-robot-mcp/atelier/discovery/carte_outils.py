"""Vues de la carte pour les façades : listes, détail d'un écran, renommage."""
from __future__ import annotations

from atelier.discovery import carte
from atelier.domain import evenements


def list_screens(module: str = "") -> list[dict]:
    return [{"id": e["id"], "nom": e.get("nom", ""), "titre": e.get("titre", ""), "module": e.get("module", ""),
             "plateformes": sorted((e.get("plateformes") or {}).keys()), "tests": len(e.get("utilise_par", []))}
            for e in carte.ecrans() if not module or e.get("module") == module]


def screen_info(ecran: str) -> dict:
    e = carte.ecran(ecran)
    ts = carte.transitions()
    return {**carte.resume_ecran(e),
            "sorties": [{"vers": t["vers"], "action": t["action"],
                         "fiabilite": round(t["reussites"] / max(t["essais"], 1), 2)}
                        for t in ts if t["de"] == e["id"] and not t.get("interdite")],
            "entrees": [{"depuis": t["de"], "action": t["action"]} for t in ts if t["vers"] == e["id"]]}


def name_screen(ecran: str, nom: str, module: str = "") -> dict:
    e = carte.renommer(ecran, nom, module or None)
    evenements.publier({"type": "carte_change"})
    return carte.resume_ecran(e)


def map_import_existing(pattern: str = "**/*.resource") -> dict:
    res = carte.importer_resources(pattern)
    evenements.publier({"type": "carte_change"})
    return res


def map_tags_report(limite: int = 200) -> dict:
    lignes = carte.rapport_tags()[:limite]
    return {"nb": len(lignes), "lignes": lignes,
            "texte": carte.texte_rapport_tags(lignes, carte.config_app().get("nom", ""))}


def ecran_detail(eid: str) -> dict:
    """Détail complet d'un écran pour l'onglet Carte de l'interface."""
    e = carte.ecran(eid)
    ts = carte.transitions()
    return {**carte.resume_ecran(e), "changements": e.get("changements", [])[-10:],
            "vignettes": {p: v.get("vignette") for p, v in (e.get("plateformes") or {}).items() if v.get("vignette")},
            "contexte": {p: v.get("contexte") for p, v in (e.get("plateformes") or {}).items()},
            "importe_de": e.get("importe_de"), "alias": e.get("alias", []),
            "sorties": [t for t in ts if t["de"] == e["id"]], "entrees": [t for t in ts if t["vers"] == e["id"]]}


def map_apps() -> dict:
    return {"active": carte.app_courante(), "applications": carte.apps()}


def map_create_app(nom: str, plateformes: list[str], app_package: str = "", app_activity: str = "",
                   bundle_id: str = "", url: str = "", build: str = "", langue: str = "fr") -> dict:
    return carte.creer_app(nom, plateformes, {"app_package": app_package, "app_activity": app_activity},
                           {"bundle_id": bundle_id}, {"url": url}, build, langue)
