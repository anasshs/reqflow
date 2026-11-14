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
            "limites": "Seules les exigences liées à au moins un test Xray sont importées depuis Jira ; l'extraction de fonctionnalités "
                       "par IA n'est pas disponible (règles candidates : extraction par motifs, à valider)."}


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


# =========================================================================== critères d'acceptation et règles métier (Jira)
import re  # noqa: E402

RE_CONDITION = re.compile(r"(?i)(?:^|,\s*)(si|lorsque|lorsqu'|quand|en cas d[e']|après)\s*(.+?)(?:,|\balors\b|$)")
RE_RESULTAT = re.compile(r"(?i)\b(doit|doivent|ne doit pas|ne peut pas|est refusée?|refuse|affiche|empêche|bloque|est bloquée?|reçoit|est redirigée?)\b(.*)")
RE_REGLE = re.compile(r"(?i)\b(doit|ne doit pas|ne peut pas|empêch|obligatoire|maximum|minimum|au plus|au moins|plafond|bloqu|refus|interdit)")


def criteres(e: dict) -> list[str]:
    """Critères d'acceptation d'un ticket : champ « criteres » (liste) ou puces de la description."""
    if isinstance(e.get("criteres"), list):
        return [str(c).strip() for c in e["criteres"] if str(c).strip()]
    lignes = (e.get("description") or "").splitlines()
    return [re.sub(r"^\s*[-*•]\s*", "", l).strip() for l in lignes if re.match(r"^\s*[-*•]\s+\S", l)]


def structurer(texte: str) -> dict:
    """Critère → condition / action / résultat attendu, par motifs explicites (pas d'IA)."""
    c = RE_CONDITION.search(texte)
    reste = texte.replace(c.group(0), " ", 1) if c else texte  # le résultat se cherche hors de la condition
    r = RE_RESULTAT.search(reste)
    action = reste.replace(r.group(0), " ") if r else reste
    return {"texte": texte, "condition": c.group(2).strip() if c else "", "resultat": (r.group(1) + r.group(2)).strip() if r else "",
            "action": re.sub(r"\s+", " ", action).strip(" ,."), "regle_candidate": bool(RE_REGLE.search(texte))}


def analyser_jira(proposer: bool = True) -> list[dict]:
    """Structure les critères de chaque ticket et propose les règles métier candidates dans la file de validation
    (provenance « déduit », statut « à valider », extrait et ticket source conservés). Idempotent."""
    from atelier.domain import declarations
    from atelier.intelligence import patrimoine_xray

    pat = patrimoine_xray.charger() or {"exigences": []}
    decl = declarations.charger()
    existants = set(decl["noeuds"]) | set(decl["rejets"])  # une proposition rejetée n'est jamais recréée
    out = []
    for e in pat["exigences"]:
        for n, texte in enumerate(criteres(e), 1):
            s = structurer(texte)
            item = {"ticket": e["cle"], "n": n, **s, "proposition": ""}
            if s["regle_candidate"] and proposer:
                rid = f"regle:{e['cle']}-{n}"
                item["proposition"] = rid
                if rid not in existants:
                    declarations.ajouter_noeud(rid, "regle", texte[:70] + ("…" if len(texte) > 70 else ""), description=texte,
                                               proprietes={"ticket_source": e["cle"], "extrait": texte, "condition": s["condition"],
                                                           "resultat_attendu": s["resultat"], "methode": "extraction par motifs (sans IA)"}, auteur="ia")
                    type_ex = "user_story" if e.get("type") == "user_story" else e.get("type", "epic")
                    try:
                        declarations.ajouter_relation(f"{type_ex}:{e['cle']}", rid, "contient", auteur="ia", source=f"jira:{e['cle']}")
                    except Exception:
                        pass
                    existants.add(rid)
            out.append(item)
    return out


# =========================================================================== versions du graphe
def _versions_dir():
    return projet.PROJECT_DIR / "connaissance" / "versions"


def _photo() -> dict:
    from atelier.domain import declarations

    g = _g()
    return {"noeuds": {i: [n.type, n.libelle, n.statut, n.provenance] for i, n in g.noeuds.items()},
            "relations": sorted(g.relations), "declarations": declarations.charger()}


def creer_version(nom: str, description: str = "") -> dict:
    import json

    from atelier.intelligence.strategie import _auteur, _maintenant

    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,60}", nom or ""):
        raise ValueError("Nom de version : lettres, chiffres, « _ », « - », « . ».")
    f = _versions_dir() / f"{nom}.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    v = {"nom": nom, "description": description.strip(), "date": _maintenant(), "auteur": _auteur(), **_photo()}
    with f.open("x", encoding="utf-8") as fh:  # une version n'est jamais réécrite
        fh.write(json.dumps(v, ensure_ascii=False))
    return {k: v[k] for k in ("nom", "description", "date", "auteur")} | {"noeuds": len(v["noeuds"]), "relations": len(v["relations"])}


def versions() -> list[dict]:
    import json

    d = _versions_dir()
    out = []
    for f in sorted(d.glob("*.json")) if d.exists() else []:
        v = json.loads(f.read_text("utf-8"))
        out.append({k: v[k] for k in ("nom", "description", "date", "auteur")} | {"noeuds": len(v["noeuds"]), "relations": len(v["relations"])})
    return sorted(out, key=lambda v: v["date"])


def _version(nom: str) -> dict:
    import json

    if nom == "courant":
        return _photo()
    f = _versions_dir() / f"{nom}.json"
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,60}", nom) or not f.exists():
        raise KeyError(f"Version inconnue : {nom}")
    return json.loads(f.read_text("utf-8"))


def comparer_versions(a: str, b: str = "courant") -> dict:
    x, y = _version(a), _version(b)
    return {"a": a, "b": b, "noeuds_ajoutes": sorted(set(y["noeuds"]) - set(x["noeuds"])), "noeuds_supprimes": sorted(set(x["noeuds"]) - set(y["noeuds"])),
            "noeuds_modifies": sorted(i for i in set(x["noeuds"]) & set(y["noeuds"]) if x["noeuds"][i] != y["noeuds"][i]),
            "relations_ajoutees": sorted(set(y["relations"]) - set(x["relations"])), "relations_supprimees": sorted(set(x["relations"]) - set(y["relations"]))}


def restaurer_version(nom: str) -> dict:
    """Restaure les déclarations d'une version ; l'état courant est d'abord sauvegardé comme version (rien n'est perdu)."""
    from datetime import datetime

    from atelier.domain import declarations

    v = _version(nom)
    sauvegarde = creer_version(f"avant-restauration-{datetime.now():%Y%m%d-%H%M%S}", f"automatique avant restauration de {nom}")
    declarations._sauver(v["declarations"])
    declarations._historiser("restauration_version", "automaticien", f"version:{nom}")
    return {"restauree": nom, "sauvegarde": sauvegarde["nom"]}
