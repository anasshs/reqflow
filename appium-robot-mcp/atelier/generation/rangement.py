"""Rangement des tests générés, par application et module (convention de l'équipe : tests/{application}/{module}/).

- Dépôt Robot : chemin du fichier .robot (défaut « tests/{application}/{module}/{scenario}.robot ») ;
- Xray : dossier du Test Repository où le test est rangé à sa création (défaut « {dossier_application}/{module} »,
  {dossier_application} = premier dossier de l'application déclaré dans Xray Mapping, sinon le dossier de publication).

Variables : {application}, {module}, {scenario} (noms normalisés : minuscules, _), {dossier_application}. Réglable
dans Test Design › Paramètres (conception/rangement.yaml, versionné avec le projet). Aucun chemin hors du projet.
"""
from __future__ import annotations

from atelier.domain.yaml_rapide import charger as charger_yaml

import collections

import yaml

from atelier.domain import projet

DEFAUT = {"robot": "tests/{application}/{module}/{scenario}.robot", "xray": "{dossier_application}/{module}"}
VARIABLES = ("application", "module", "scenario", "dossier_application")


def _fichier():
    return projet.PROJECT_DIR / "conception" / "rangement.yaml"


def regles() -> dict:
    f = _fichier()
    d = charger_yaml(f.read_text("utf-8")) if f.exists() else {}
    return {**DEFAUT, **{k: v for k, v in (d or {}).items() if k in DEFAUT and v}}


def maj(robot: str = "", xray: str = "") -> dict:
    r = regles()
    for cle, val in (("robot", robot), ("xray", xray)):
        if val is None:
            continue
        val = val.strip() or DEFAUT[cle]
        try:
            val.format(**{v: "x" for v in VARIABLES})
        except (KeyError, IndexError, ValueError) as e:
            raise ValueError(f"Règle « {val} » : variable inconnue ou accolade invalide ({e}). Variables : {', '.join(VARIABLES)}.")
        r[cle] = val
    if not r["robot"].endswith(".robot"):
        raise ValueError("Le chemin Robot doit finir par .robot.")
    projet.safe_path(_chemin(r["robot"], {v: "x" for v in VARIABLES}))  # reste dans le projet
    f = _fichier()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(yaml.safe_dump(r, allow_unicode=True, sort_keys=False), "utf-8")
    return r


def module_des_ecrans(refs: list[str]) -> str:
    """Module le plus fréquent parmi les écrans (carte) ; vide si aucun n'en a."""
    from atelier.discovery import carte

    mods = []
    for r in refs:
        try:
            m = carte.ecran(r).get("module")
        except KeyError:
            continue
        if m:
            mods.append(m)
    return collections.Counter(mods).most_common(1)[0][0] if mods else ""


def _valeurs(m: dict) -> dict:
    from atelier.discovery import carte

    try:
        app = carte.config_app() if carte.app_courante() else {}
    except Exception:  # noqa: BLE001
        app = {}
    try:
        from atelier.generation import conception

        publication = conception.mapping().get("dossier_repository") or ""
    except Exception:  # noqa: BLE001
        publication = ""
    dossiers = (app.get("tests_xray") or {}).get("dossiers") or []
    return {"application": projet.slug(app.get("nom") or "", 40, "application"),
            "module": projet.slug(m.get("module") or "", 40, "sans_module"),
            "scenario": projet.slug(m.get("titre") or m.get("cle") or "", 60, "scenario"),
            "dossier_application": dossiers[0] if dossiers else publication,
            "module_xray": (m.get("module") or "").strip()}


def _chemin(motif: str, v: dict) -> str:
    return "/".join(p for p in motif.format(**v).replace("\\", "/").split("/") if p and p != ".")


def chemin_robot(m: dict) -> str:
    return _chemin(regles()["robot"], _valeurs(m))


def dossier_xray(m: dict) -> str:
    """Dossier Xray du test ; vide = racine (ni dossier d'application ni module)."""
    from atelier.discovery import carte

    v = _valeurs(m)
    v = {**v, "module": v["module_xray"]}  # dans Xray : nom lisible du module (« Virements »)
    d = carte.normaliser_dossier(regles()["xray"].format(**{k: v.get(k, "") for k in VARIABLES}))
    return "" if d == "/" else d
