"""Xray Coverage Graph et indicateurs de couverture, calculés sur des définitions explicites.

Définitions (affichées telles quelles dans l'interface) :
  - Test automatisé : test Xray dont la clé est portée en tag par au moins un test Robot du dépôt.
  - Couverture automatisée (module ou global) : tests automatisés / tests Xray de l'instantané.
  - Exigence couverte : epic / user story liée à au moins un test Xray (directement ou, pour une
    epic, via ses user stories) ; couverte en automatique si l'un de ces tests est automatisé.
  - Tests redondants (candidats) : deux tests d'un même module dont les résumés partagent au moins
    SEUIL_REDONDANCE des mots significatifs (Jaccard). À confirmer par l'automaticien.
Une donnée absente de l'instantané (criticité, module…) reste absente : jamais estimée.
"""
from __future__ import annotations

import re
import unicodedata

from atelier.domain.graphe import Graphe

TYPES_COUVERTURE = {"module", "epic", "user_story", "bug", "test", "test_plan", "test_execution", "test_robot"}
SEUIL_REDONDANCE = 0.8
MOTS_VIDES = {"le", "la", "les", "de", "des", "du", "un", "une", "et", "a", "au", "aux", "en", "sur", "pour",
              "par", "avec", "sans", "d", "l", "test", "verifier", "verification"}
DEFINITIONS = {
    "test_automatise": "Test Xray dont la clé est portée en tag par au moins un test Robot du dépôt.",
    "couverture_automatisee": "Tests automatisés / tests Xray de l'instantané (par module et global).",
    "exigence_couverte": "Epic ou user story liée à au moins un test Xray (une epic via ses user stories).",
    "exigence_couverte_auto": "Exigence couverte dont au moins un test lié est automatisé.",
    "redondance": f"Même module et résumés semblables à {int(SEUIL_REDONDANCE * 100)} % ou plus (mots significatifs).",
}


def vue(g: Graphe, module: str = "", afficher: str = "tous") -> Graphe:
    """Sous-graphe de traçabilité Epic → US → Test Xray → Test Robot, filtrable."""
    ids = {i for i, n in g.noeuds.items() if n.type in TYPES_COUVERTURE}
    if module:
        dans = g.atteignables(f"module:{module}", "aval", {"contient", "teste_par", "implemente_par"}) | {f"module:{module}"}
        tests = {i for i in dans if g.noeuds[i].type == "test"}
        amont = set()
        for t in tests:
            amont |= {i for i in g.atteignables(t, "amont", {"contient", "teste_par"})
                      if g.noeuds[i].type in ("epic", "user_story", "bug", "test_plan")}
        ids &= dans | amont
    if afficher in ("manuels", "automatises"):
        voulu = afficher == "automatises"
        exclus = {i for i in ids if g.noeuds[i].type == "test" and bool(g.noeuds[i].proprietes.get("automatise")) != voulu}
        ids -= exclus
        ids -= {i for i in ids if g.noeuds[i].type == "test_robot" and not voulu}
    return g.sous_graphe(ids)


def _mots(texte: str) -> set:
    t = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode().lower()
    return {m for m in re.findall(r"[a-z0-9]+", t) if m not in MOTS_VIDES and len(m) > 1}


def redondances(tests: list[dict]) -> list[dict]:
    out = []
    for i, a in enumerate(tests):
        for b in tests[i + 1:]:
            if (a.get("module") or "") != (b.get("module") or ""):
                continue
            ma, mb = _mots(a.get("resume")), _mots(b.get("resume"))
            if not ma or not mb:
                continue
            sim = len(ma & mb) / len(ma | mb)
            if sim >= SEUIL_REDONDANCE:
                out.append({"tests": [a["cle"], b["cle"]], "similarite": round(sim, 2), "module": a.get("module")})
    return out


def indicateurs(g: Graphe, pat: dict | None) -> dict:
    if not pat:
        return {"disponible": False, "raison": "Aucun instantané du patrimoine Xray : synchroniser ou importer.",
                "definitions": DEFINITIONS}
    tests = pat["tests"]
    auto = {t["cle"]: bool((g.noeuds.get(f"test:{t['cle']}") or _Vide()).proprietes.get("automatise")) for t in tests}
    modules: dict = {}
    for t in tests:
        m = t.get("module") or "(sans module)"
        d = modules.setdefault(m, {"module": m, "tests": 0, "automatises": 0, "manuels": 0})
        d["tests"] += 1
        d["automatises" if auto[t["cle"]] else "manuels"] += 1
    for d in modules.values():
        d["couverture_automatisee"] = round(d["automatises"] / d["tests"], 3) if d["tests"] else None
    tests_par_exigence: dict = {}
    for t in tests:
        for e in t["exigences"]:
            tests_par_exigence.setdefault(e, []).append(t["cle"])
    enfants: dict = {}
    for e in pat.get("exigences", []):
        if e.get("parent"):
            enfants.setdefault(e["parent"], []).append(e["cle"])
    exig = []
    for e in pat.get("exigences", []):
        lies = list(tests_par_exigence.get(e["cle"], []))
        for us in enfants.get(e["cle"], []):
            lies += tests_par_exigence.get(us, [])
        lies = sorted(set(lies))
        exig.append({"cle": e["cle"], "type": e["type"], "resume": e.get("resume"), "tests": lies,
                     "couverte": bool(lies), "couverte_auto": any(auto.get(t) for t in lies)})
    nb_auto = sum(auto.values())
    cles_xray = set(auto)
    orphelins = sorted(n.libelle for n in g.noeuds.values()
                       if n.type == "test" and n.proprietes.get("automatise") and n.id[5:] not in cles_xray)
    return {
        "disponible": True, "instantane": {"date": pat.get("date"), "source": pat.get("source")},
        "definitions": DEFINITIONS,
        "global": {"tests": len(tests), "automatises": nb_auto, "manuels": len(tests) - nb_auto,
                   "couverture_automatisee": round(nb_auto / len(tests), 3) if tests else None,
                   "exigences": len(exig), "exigences_couvertes": sum(e["couverte"] for e in exig),
                   "exigences_couvertes_auto": sum(e["couverte_auto"] for e in exig)},
        "modules": sorted(modules.values(), key=lambda d: d["module"]),
        "exigences_non_couvertes": [e for e in exig if not e["couverte"]],
        "exigences_sans_automatisation": [e for e in exig if e["couverte"] and not e["couverte_auto"]],
        "redondances": redondances(tests),
        "cles_robot_inconnues_de_xray": orphelins,
    }


def candidats(g: Graphe, pat: dict | None, module: str = "") -> list[dict]:
    """Tests candidats (4.2) avec les seules informations observables. Le score pondéré et les
    recommandations argumentées relèvent du Test Intelligence Engine (phase 3) : en attendant,
    seule « déjà automatisé » est affirmée, le reste est « à analyser » avec ce qui manque."""
    out = []
    for t in (pat or {}).get("tests", []):
        if module and (t.get("module") or "") != module:
            continue
        n = g.noeuds.get(f"test:{t['cle']}")
        automatise = bool(n and n.proprietes.get("automatise"))
        manque = [c for c in ("criticite", "module") if not t.get(c)]
        manque += ["fréquence d'exécution", "stabilité", "faisabilité", "données", "maintenance"]
        out.append({"cle": t["cle"], "resume": t.get("resume"), "module": t.get("module"), "type": t.get("type"),
                    "criticite": t.get("criticite"), "statut": t.get("statut"), "automatise": automatise,
                    "dernier_resultat": n and n.proprietes.get("dernier_resultat"),
                    "score": None,
                    "recommandation": "Déjà automatisé" if automatise else "À analyser",
                    "justification": ([f"Implémenté par {len([r for r in g.sortants(n.id) if r.type == 'implemente_par'])} test(s) Robot (tag {t['cle']})."]
                                      if automatise else ["Score non calculé : critères pas encore collectés."]),
                    "donnees_manquantes": [] if automatise else manque})
    return out


class _Vide:
    proprietes: dict = {}
