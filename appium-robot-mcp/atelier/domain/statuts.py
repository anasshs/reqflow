"""Mapping des statuts des tickets, réglé par PROJET (jamais par application).

Chaque équipe a son workflow Jira : « Ready », « Prêt », « Validé métier »… L'atelier ne devine plus le sens d'un statut
par son nom : pour les quatre types de ticket qu'il lit, chaque statut du workflow est relié à une catégorie de l'atelier.

  test        brouillon · rédigé · à automatiser · en cours d'automatisation · automatisé · obsolète
  execution   à faire · en cours · terminée · annulée                     (Test Execution)
  plan        à faire · en cours · clôturé · annulé                       (Test Plan)
  bug         ouvert · en cours · résolu · fermé · réouvert · rejeté

Stockage : <projet>/atelier_statuts.yaml (versionné : toute l'équipe a le même mapping). Le nom du type de ticket Jira
de chaque famille est réglable (« Bug » peut s'appeler « Bogue » ou « Anomalie »).

Rien n'est supposé : un statut sans correspondance est signalé. Pour ne pas casser un projet qui n'a encore rien réglé,
les lecteurs gardent leur ancien repli (catégorie « terminé » de Jira lue à l'import) quand un statut n'est pas relié,
et le disent.
"""
from __future__ import annotations

from atelier.domain.yaml_rapide import charger as charger_yaml

import yaml

from atelier.domain import projet

TYPES = {"test": "Test", "execution": "Test Execution", "plan": "Test Plan", "bug": "Bug"}
LIBELLES_TYPES = {"test": "Test", "execution": "Test Execution", "plan": "Test Plan", "bug": "Bug"}
CATEGORIES = {
    "test": [("brouillon", "Brouillon"), ("redige", "Rédigé"), ("a_automatiser", "À automatiser"), ("en_automatisation", "En cours d'automatisation"),
             ("automatise", "Automatisé"), ("obsolete", "Obsolète")],
    "execution": [("a_faire", "À faire"), ("en_cours", "En cours"), ("terminee", "Terminée"), ("annulee", "Annulée")],
    "plan": [("a_faire", "À faire"), ("en_cours", "En cours"), ("cloture", "Clôturé"), ("annule", "Annulé")],
    "bug": [("ouvert", "Ouvert"), ("en_cours", "En cours"), ("resolu", "Résolu"), ("ferme", "Fermé"), ("reouvert", "Réouvert"), ("rejete", "Rejeté")],
}
# catégories qui ne demandent plus de travail (plan ou exécution fermés, bug clos)
FERMEES = {"execution": {"terminee", "annulee"}, "plan": {"cloture", "annule"}, "bug": {"resolu", "ferme", "rejete"}, "test": {"obsolete"}}


def _fichier():
    return projet.PROJECT_DIR / "atelier_statuts.yaml"


def _lire() -> dict:
    f = _fichier()
    try:
        d = (charger_yaml(f.read_text("utf-8")) or {}) if f.exists() else {}
    except (OSError, yaml.YAMLError):
        d = {}
    return d if isinstance(d, dict) else {}


def mapping() -> dict:
    """Mapping du projet : nom Jira de chaque type de ticket, et pour chaque type {statut Jira: catégorie}."""
    d = _lire()
    connues = {t: {c for c, _ in l} for t, l in CATEGORIES.items()}
    return {"types": {t: str((d.get("types") or {}).get(t) or defaut).strip() or defaut for t, defaut in TYPES.items()},
            "correspondances": {t: {str(s): c for s, c in ((d.get("correspondances") or {}).get(t) or {}).items() if c in connues[t]} for t in TYPES},
            "regle": _fichier().exists()}


def enregistrer(types: dict | None = None, correspondances: dict | None = None) -> dict:
    """Enregistre le mapping du projet (rôle automaticien). Une catégorie vide retire la correspondance du statut."""
    from atelier.domain import roles

    roles.exiger("construire")
    m = mapping()
    for t, nom in (types or {}).items():
        if t not in TYPES:
            raise ValueError(f"Type de ticket inconnu : {t} ({', '.join(TYPES)}).")
        if not str(nom or "").strip():
            raise ValueError(f"Nom du type de ticket Jira obligatoire pour « {LIBELLES_TYPES[t]} ».")
        m["types"][t] = str(nom).strip()
    for t, corr in (correspondances or {}).items():
        if t not in TYPES:
            raise ValueError(f"Type de ticket inconnu : {t} ({', '.join(TYPES)}).")
        connues, propres = {c for c, _ in CATEGORIES[t]}, {}
        for statut, cat in (corr or {}).items():
            statut = " ".join(str(statut or "").split())
            if not statut or not cat:
                continue
            if cat not in connues:
                raise ValueError(f"Catégorie inconnue pour {LIBELLES_TYPES[t]} : {cat} ({', '.join(sorted(connues))}).")
            propres[statut] = cat
        m["correspondances"][t] = propres
    _fichier().write_text(yaml.safe_dump({"types": m["types"], "correspondances": m["correspondances"]}, allow_unicode=True, sort_keys=True), "utf-8")
    return etat()


def categorie(type_: str, statut: str) -> str:
    """Catégorie de l'atelier pour un statut Jira (casse et espaces ignorés) ; « » si le statut n'est pas relié."""
    s = " ".join(str(statut or "").split()).casefold()
    if not s:
        return ""
    return next((c for k, c in mapping()["correspondances"].get(type_, {}).items() if k.casefold() == s), "")


def ferme(type_: str, statut: str) -> bool | None:
    """Le ticket ne demande plus de travail ? None quand le statut n'est pas relié : l'appelant garde alors son repli."""
    c = categorie(type_, statut)
    return None if not c else c in FERMEES[type_]


def statut_pour(type_: str, categorie_: str) -> str:
    """Premier statut Jira relié à une catégorie (ex. le statut à appliquer pour passer un test « à automatiser »)."""
    return next((s for s, c in mapping()["correspondances"].get(type_, {}).items() if c == categorie_), "")


def observes() -> dict:
    """Statuts rencontrés dans les copies locales (sans réseau), par type, avec leur nombre d'occurrences."""
    from atelier.intelligence import patrimoine_xray

    out: dict = {t: {} for t in TYPES}

    def compter(t, statut):
        s = " ".join(str(statut or "").split())
        if s:
            out[t][s] = out[t].get(s, 0) + 1
    try:
        pat = patrimoine_xray.charger() or {}
    except Exception:  # noqa: BLE001 — copie illisible : seuls les statuts déjà reliés sont proposés
        pat = {}
    for x in pat.get("tests") or []:
        compter("test", x.get("statut"))
    vus = set()
    for e in pat.get("executions") or []:
        compter("execution", e.get("statut"))
        for b in e.get("bugs") or []:
            if b.get("cle") not in vus:
                vus.add(b.get("cle"))
                compter("bug", b.get("statut"))
        for p in e.get("plans") or []:
            compter("plan", p.get("statut"))
    for p in (pat.get("plans_xray") or {}).get("plans") or []:
        compter("plan", p.get("statut"))
    for x in pat.get("exigences") or []:
        if x.get("type") == "bug":
            compter("bug", x.get("statut"))
    return out


def lire_jira(jira=None, projet_cle: str = "") -> dict:
    """Statuts du workflow de chaque type de ticket, lus dans Jira (lecture seule, GET project/{clé}/statuses).
    {type: {"type_jira", "trouve", "statuts": [...]}, "types_disponibles": [...]}"""
    from atelier.domain import projets
    from atelier.integrations.jira import JiraClient

    cle = (projet_cle or projets.cle_jira()).strip().upper()
    if not cle:
        raise ValueError("Aucun projet Jira déclaré pour ce projet (Paramètres › Projets).")
    jira = jira or JiraClient()
    if not getattr(jira, "enabled", True):
        raise RuntimeError("Jira non configuré (Paramètres › Connexions).")
    data = jira.get(f"/rest/api/3/project/{cle}/statuses") or []
    par_type = {str(it.get("name") or "").casefold(): [s["name"] for s in it.get("statuses") or []] for it in data}
    m, out = mapping(), {}
    for t, nom in m["types"].items():
        out[t] = {"type_jira": nom, "trouve": nom.casefold() in par_type, "statuts": par_type.get(nom.casefold(), [])}
    return {**out, "types_disponibles": sorted(str(it.get("name") or "") for it in data), "projet": cle}


def etat(statuts_jira: dict | None = None) -> dict:
    """Pour l'écran : par type, chaque statut connu (relié, vu dans les copies locales, ou lu dans Jira) avec sa
    catégorie, d'où il est connu et combien de tickets le portent ; et les statuts sans correspondance."""
    m, obs = mapping(), observes()
    types = []
    for t in TYPES:
        jira = (statuts_jira or {}).get(t, {}).get("statuts") or []
        noms = list(dict.fromkeys([*jira, *m["correspondances"][t], *obs[t]]))
        par_cf = {k.casefold(): c for k, c in m["correspondances"][t].items()}
        lignes = [{"statut": s, "categorie": par_cf.get(s.casefold(), ""), "tickets": next((n for k, n in obs[t].items() if k.casefold() == s.casefold()), 0),
                   "sources": [x for x, ok in (("Jira", s in jira), ("copies locales", any(k.casefold() == s.casefold() for k in obs[t]))) if ok]} for s in noms]
        types.append({"id": t, "libelle": LIBELLES_TYPES[t], "type_jira": m["types"][t], "categories": [{"id": c, "libelle": l} for c, l in CATEGORIES[t]],
                      "statuts": lignes, "sans_correspondance": [x["statut"] for x in lignes if not x["categorie"]],
                      "type_trouve": (statuts_jira or {}).get(t, {}).get("trouve")})
    return {"types": types, "regle": m["regle"], "fichier": "atelier_statuts.yaml",
            "types_disponibles": (statuts_jira or {}).get("types_disponibles") or [],
            "sans_correspondance": sum(len(x["sans_correspondance"]) for x in types)}
