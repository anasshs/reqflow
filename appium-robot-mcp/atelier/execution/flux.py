"""Automation Flow Graph : construction technique d'un test automatisé.

Scénario (test Xray) → test Robot → keywords (transitifs) → locators → écrans ; fichiers resource
et suite qui les contiennent ; JDD → requêtes Oracle ; bibliothèques (AppiumLibrary, Browser) et
plateformes. Sans cible : tout le patrimoine automatisé.
"""
from __future__ import annotations

from atelier.domain.graphe import Graphe

TYPES_FLUX = {"test", "suite", "test_robot", "keyword", "resource", "locator", "ecran", "jdd", "requete",
              "bibliotheque", "plateforme"}


def vue(g: Graphe, cible: str = "") -> Graphe:
    if not cible:
        ids = {i for i, n in g.noeuds.items() if n.type in TYPES_FLUX - {"ecran", "plateforme"}}
        ids = {i for i in ids if g.noeuds[i].type != "test" or g.noeuds[i].proprietes.get("automatise")}
        return g.sous_graphe(ids)
    if cible not in g.noeuds:
        raise KeyError(f"Élément inconnu : {cible}")
    depart = {cible}
    if g.noeuds[cible].type == "test":
        depart |= {r.vers for r in g.sortants(cible) if r.type == "implemente_par"}
    elif g.noeuds[cible].type == "test_robot":
        depart |= {r.de for r in g.entrants(cible) if r.type == "implemente_par"}
    ids = set(depart)
    for d in depart:
        ids |= g.atteignables(d, "aval", {"appelle", "utilise", "depend_de"}, fiables=False)
    for i in list(ids):  # contenants : fichiers resource / suite, écrans des locators
        for r in g.entrants(i):
            if r.type == "contient" and g.noeuds[r.de].type in ("resource", "suite", "ecran"):
                ids.add(r.de)
    ids |= {f"plateforme:{p}" for i in ids for p in g.noeuds[i].plateformes if g.noeuds[i].type == "test_robot"}
    for p in [i for i in ids if i.startswith("plateforme:")]:
        if p not in g.noeuds:
            g.noeud(p, "plateforme", p.split(":", 1)[1].capitalize(), source="dépôt")
        for t in [i for i in ids if g.noeuds.get(i) and g.noeuds[i].type == "test_robot"]:
            if p.split(":", 1)[1] in g.noeuds[t].plateformes:
                g.relier(t, p, "execute_par", source="bibliothèques importées")
    return g.sous_graphe({i for i in ids if i in g.noeuds and g.noeuds[i].type in TYPES_FLUX})
