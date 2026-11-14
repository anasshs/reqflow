"""Application Intelligence : vues de compréhension de l'application sur le Knowledge Graph CENTRAL
(cahier des charges « Application Intelligence »). Aucun second graphe : tout est lu dans
connaissance.construire() (Jira / Xray via l'instantané, carte observée, dépôt, BDD, déclarations).
"""
from __future__ import annotations

from collections import Counter

import yaml

from atelier.domain import projet


def _g():
    from atelier.discovery import connaissance

    return connaissance.construire()


def _ecrans_carte() -> tuple[dict, list[dict], list[dict]]:
    from atelier.discovery import carte

    slug = carte.app_courante()
    app = next((a for a in carte.apps() if a.get("slug") == slug), {}) if slug else {}
    racine = carte._racine() / (slug or "")
    ecrans = [yaml.safe_load(f.read_text("utf-8")) or {} for f in sorted((racine / "ecrans").glob("*.yaml"))] if slug and (racine / "ecrans").exists() else []
    trans = (yaml.safe_load((racine / "transitions.yaml").read_text("utf-8")) or []) if slug and (racine / "transitions.yaml").exists() else []
    return app, ecrans, trans


def vue_ensemble() -> dict:
    from atelier.domain import declarations
    from atelier.intelligence import patrimoine_xray

    g = _g()
    types = Counter(n.type for n in g.noeuds.values())
    app, ecrans, trans = _ecrans_carte()
    pat = patrimoine_xray.charger() or {"tests": [], "exigences": []}
    tests_par_exig: dict = {}
    for t in pat["tests"]:
        for e in t.get("exigences") or []:
            tests_par_exig.setdefault(e, []).append(t["cle"])
    lies = {t for l in tests_par_exig.values() for t in l}
    vus = [p.get("vu_le", "") for e in ecrans for p in (e.get("plateformes") or {}).values() if isinstance(p, dict)]
    a_valider = [n for n in g.noeuds.values() if n.statut == "à valider"] + [r for r in g.relations.values() if r.statut == "à valider"]
    hist = declarations.historique() if hasattr(declarations, "historique") else []
    return {"application": {"nom": app.get("nom", ""), "plateformes": app.get("plateformes", []), "build": app.get("build", ""),
                            "derniere_exploration": max(vus) if vus else None, "derniere_synchro_xray": pat.get("date"),
                            "source_xray": pat.get("source", ""), "derniere_maj_graphe": (hist[0]["date"] if hist else None)},
            "fonctionnel": {"epics": types["epic"], "stories": types["user_story"], "fonctionnalites": types["fonctionnalite"], "regles": types["regle"],
                            "parcours": types["parcours"], "modules": types["module"]},
            "technique": {"ecrans": len(ecrans), "composants": sum(len(e.get("elements") or {}) for e in ecrans), "locators": types["locator"],
                          "keywords": types["keyword"], "api": types["endpoint"], "transitions": len(trans),
                          "ecrans_a_revoir": sum(bool(e.get("a_revoir")) for e in ecrans)},
            "tracabilite": {"stories_sans_test": [e["cle"] for e in pat["exigences"] if e.get("type") == "user_story" and not tests_par_exig.get(e["cle"])],
                            "tests_sans_exigence": [t["cle"] for t in pat["tests"] if t["cle"] not in lies],
                            "tests_automatises": sum(bool(n.proprietes.get("automatise")) for n in g.noeuds.values() if n.type == "test"),
                            "elements_a_valider": len(a_valider)},
            "limites": "Descriptions et critères d'acceptation Jira absents de l'instantané : l'extraction IA de fonctionnalités et de règles "
                       "nécessite l'import Jira complet (API à vérifier)."}


def jira() -> list[dict]:
    """Tickets Jira de l'instantané avec leur hiérarchie et leurs tests Xray (traçabilité bidirectionnelle)."""
    from atelier.intelligence import patrimoine_xray

    pat = patrimoine_xray.charger() or {"tests": [], "exigences": []}
    g = _g()
    enfants: dict = {}
    for e in pat["exigences"]:
        if e.get("parent"):
            enfants.setdefault(e["parent"], []).append(e["cle"])
    out = []
    for e in pat["exigences"]:
        tests = [t for t in pat["tests"] if e["cle"] in (t.get("exigences") or [])]
        out.append({**e, "enfants": enfants.get(e["cle"], []), "tests": [{"cle": t["cle"], "resume": t.get("resume", ""), "type": t.get("type", ""),
                    "automatise": bool((g.noeuds.get(f"test:{t['cle']}") or type("x", (), {"proprietes": {}})).proprietes.get("automatise"))} for t in tests]})
    return out


def ecrans() -> list[dict]:
    """Explorateur d'écrans : éléments, locators par plateforme, variantes, transitions, vignettes, tests associés."""
    from atelier.execution.depot_robot import lire_depot

    _, ec, trans = _ecrans_carte()
    inv = lire_depot()
    par_ecran: dict = {}
    for t in inv["tests"].values():
        for k in t["keywords"]:
            for e, _c in (inv["keywords"].get(k) or {}).get("locators") or []:
                par_ecran.setdefault(e, set()).add(t["nom"])
    noms = {e.get("id"): e.get("nom") or e.get("id") for e in ec}
    out = []
    for e in ec:
        plats = {p: {k: v for k, v in d.items() if k in ("contexte", "vu_le", "vu_build")} for p, d in (e.get("plateformes") or {}).items() if isinstance(d, dict)}
        out.append({"id": e.get("id"), "nom": e.get("nom") or "(sans nom)", "module": e.get("module", ""), "titre": e.get("titre", ""),
                    "plateformes": plats, "etats": e.get("etats") or [], "a_revoir": bool(e.get("a_revoir")),
                    "elements": [{"cle": k, "type": v.get("type"), "libelle": v.get("libelle"), "locators": v.get("locators") or {}} for k, v in (e.get("elements") or {}).items()],
                    "vignettes": [f"{e.get('id')}_{p}.png" for p in plats],
                    "depuis": sorted({noms.get(t.get("de"), t.get("de")) for t in trans if t.get("vers") == e.get("id")}),
                    "vers": sorted({noms.get(t.get("vers"), t.get("vers")) for t in trans if t.get("de") == e.get("id")}),
                    "tests": sorted(par_ecran.get(e.get("nom") or "", set()))})
    return out


def noeuds(types: list[str]) -> list[dict]:
    """Règles, parcours, API… déclarés ou observés dans le graphe, avec relations et provenance."""
    g = _g()
    out = []
    for n in g.noeuds.values():
        if n.type in types:
            rel = [{"sens": "→", "type": r.type, "cible": r.vers} for r in g.relations.values() if r.de == n.id] + \
                  [{"sens": "←", "type": r.type, "cible": r.de} for r in g.relations.values() if r.vers == n.id]
            out.append({"id": n.id, "type": n.type, "libelle": n.libelle, "provenance": n.provenance, "source": n.source, "statut": n.statut,
                        "description": n.proprietes.get("description", ""), "relations": rel})
    return sorted(out, key=lambda x: (x["type"], x["libelle"]))


def changements() -> list[dict]:
    """Changements détectés aujourd'hui sans historique de versions applicatives : écrans à revoir (carte),
    locators obsolètes (dépôt ≠ observation), clés Robot inconnues de Xray, tests Xray non implémentés."""
    from atelier.generation import studio
    from atelier.intelligence import couverture, patrimoine_xray

    out = []
    _, ec, _ = _ecrans_carte()
    for e in ec:
        if e.get("a_revoir"):
            out.append({"source": "Application (carte)", "nature": "Écran modifié à revoir", "element": e.get("nom") or e.get("id"), "impact": "écran"})
    for l in studio.locators():
        if l["etat"] in ("Obsolete", "Missing"):
            out.append({"source": "Application vs dépôt", "nature": f"Locator {l['etat']}", "element": f"{l['ecran']}.{l['cle']}", "impact": f"{l['utilisations']} keyword(s)"})
    pat = patrimoine_xray.charger()
    if pat:
        ind = couverture.indicateurs(_g(), pat)
        for c in ind.get("cles_robot_inconnues_de_xray", []):
            out.append({"source": "Dépôt vs Xray", "nature": "Clé Robot inconnue de Xray", "element": c, "impact": "traçabilité"})
    return out


def validation() -> list[dict]:
    """File de validation : éléments et relations proposés (déduits) en attente d'une décision humaine."""
    g = _g()
    out = [{"objet": "nœud", "id": n.id, "libelle": n.libelle, "type": n.type, "provenance": n.provenance, "source": n.source, "confiance": n.confiance}
           for n in g.noeuds.values() if n.statut == "à valider"]
    out += [{"objet": "relation", "id": r.id, "libelle": f"{r.de} — {r.type} → {r.vers}", "type": r.type, "provenance": r.provenance, "source": r.source, "confiance": None}
            for r in g.relations.values() if r.statut == "à valider"]
    return out


def api_endpoints() -> list[dict]:
    return noeuds(["endpoint", "entite"])
