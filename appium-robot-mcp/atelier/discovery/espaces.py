"""Services des espaces de travail : vues de graphes prêtes à afficher, détail d'un nœud,
modifications déclarées (avec contrôle du statut actuel), analyse d'impact, export.

Le graphe est reconstruit à chaque demande à partir des sources (carte, dépôt, instantané Xray,
déclarations) : pas de cache qui pourrait diverger des fichiers.
"""
from __future__ import annotations

from atelier.discovery import connaissance
from atelier.domain import declarations
from atelier.domain.graphe import CATEGORIES, TYPES_NOEUDS, TYPES_RELATIONS, Graphe

MAX_NOEUDS = 600  # au-delà, l'interface demande de filtrer (lisibilité)


def _graphe() -> Graphe:
    return connaissance.construire()


def _limiter(g: Graphe) -> dict:
    d = g.vers_dict()
    d["tronque"] = len(g.noeuds) > MAX_NOEUDS
    if d["tronque"]:
        garde = sorted(g.noeuds, key=lambda i: (CATEGORIES.index(g.noeuds[i].categorie), i))[:MAX_NOEUDS]
        d = {**g.sous_graphe(garde).vers_dict(), "tronque": True, "total": len(g.noeuds)}
    return d


def referentiel() -> dict:
    return {"types": TYPES_NOEUDS, "categories": CATEGORIES, "relations": TYPES_RELATIONS}


# =========================================================================== vues
PATRIMOINE = ("epic", "user_story", "bug", "test", "test_plan", "test_execution")
EXIGENCES = ("epic", "user_story", "bug")


def patrimoine_lie(g) -> set[str]:
    """Nœuds à montrer quand on ne veut que la connaissance de l'application : tout ce qui n'est pas du patrimoine
    Jira / Xray, plus les tickets rattachés à l'application — tests Xray reliés à un élément de l'application (test
    Robot qui porte la clé, écran, endpoint…), exigences testées par ces tests ou reliées directement à l'application
    (lien confirmé, x-jira OpenAPI), et leurs epics parents. Plans, exécutions et le reste du backlog sont masqués."""
    voisins: dict[str, set[str]] = {}
    for r in g.relations.values():
        voisins.setdefault(r.de, set()).add(r.vers)
        voisins.setdefault(r.vers, set()).add(r.de)
    app = {i for i, n in g.noeuds.items() if n.type not in PATRIMOINE and n.type != "module"}
    tests = {i for i, n in g.noeuds.items() if n.type == "test" and voisins.get(i, set()) & app}
    exig = {i for i, n in g.noeuds.items() if n.type in EXIGENCES and voisins.get(i, set()) & (app | tests)}

    def parents(ids):
        return {r.de for r in g.relations.values() if r.type == "contient" and r.vers in ids and g.noeuds[r.de].type in EXIGENCES}

    nouveaux = parents(exig) - exig
    while nouveaux:  # remontée des epics parents, sans redescendre vers leurs autres US
        exig |= nouveaux
        nouveaux = parents(nouveaux) - exig
    garde = app | tests | exig
    modules = {i for i, n in g.noeuds.items() if n.type == "module" and voisins.get(i, set()) & garde}
    return garde | modules


def vue_connaissance(types: list[str] | None = None, categories: list[str] | None = None, plateforme: str = "",
                     recherche: str = "", centre: str = "", profondeur: int = 1, patrimoine: str = "lie") -> dict:
    """patrimoine « lie » (défaut) : la connaissance de l'application et les seuls tickets Jira / Xray qui s'y
    rattachent ; « tout » : toute la copie locale Jira / Xray. Un centre ou une recherche montrent toujours tout."""
    g = _graphe()
    masques = 0
    if centre:
        if centre not in g.noeuds:
            raise KeyError(f"Élément inconnu : {centre}")
        g = g.voisinage([centre], max(1, min(profondeur, 4)))
    elif patrimoine != "tout" and not recherche.strip():
        garde = patrimoine_lie(g)
        masques = sum(1 for i, n in g.noeuds.items() if i not in garde and n.type in PATRIMOINE + ("module",))
        g = g.sous_graphe(garde)
    return {**_limiter(g.filtrer(types, categories, plateforme, recherche)), "patrimoine_masque": masques}


def vue_couverture(module: str = "", afficher: str = "tous", recherche: str = "") -> dict:
    from atelier.intelligence import couverture, patrimoine_xray

    g = _graphe()
    pat = patrimoine_xray.charger_vue()
    v = couverture.vue(g, module, afficher).filtrer(recherche=recherche)
    return {**_limiter(v), "indicateurs": couverture.indicateurs(g, pat), "instantane": patrimoine_xray.etat(),
            "modules": sorted({n.libelle for n in g.noeuds.values() if n.type == "module"})}


def candidats(module: str = "") -> list[dict]:
    from atelier.intelligence import couverture, patrimoine_xray

    return couverture.candidats(_graphe(), patrimoine_xray.charger_vue(), module)


def vue_flux(cible: str = "") -> dict:
    from atelier.execution import flux

    g = _graphe()
    tests = sorted(({"id": i, "libelle": n.libelle} for i, n in g.noeuds.items()
                    if n.type == "test_robot" or (n.type == "test" and n.proprietes.get("automatise"))),
                   key=lambda x: x["id"])
    return {**_limiter(flux.vue(g, cible)), "cibles": tests}


def impact(noeud: str) -> dict:
    return connaissance.analyser_impact(_graphe(), noeud)


# =========================================================================== détail
def detail(noeud: str) -> dict:
    g = _graphe()
    n = g.noeuds.get(noeud)
    if not n:
        raise KeyError(f"Élément inconnu : {noeud}")

    def lien(r, autre):
        o = g.noeuds[autre]
        return {"relation": r.vers_dict(), "noeud": {"id": o.id, "type": o.type, "libelle": o.libelle,
                                                     "categorie": o.categorie}}
    sortants = [lien(r, r.vers) for r in g.sortants(noeud)]
    entrants = [lien(r, r.de) for r in g.entrants(noeud)]
    voisins = {x["noeud"]["id"] for x in sortants + entrants}
    proches = g.voisinage([noeud], 2).noeuds
    return {"noeud": n.vers_dict(), "sortants": sortants, "entrants": entrants,
            "tests_xray": sorted(i for i in proches if g.noeuds[i].type == "test"),
            "tests_robot": sorted(i for i in proches if g.noeuds[i].type == "test_robot"),
            "scenarios_bdd": sorted(i for i in proches if g.noeuds[i].type in ("scenario", "feature")),
            "nb_voisins": len(voisins), "historique": declarations.historique(noeud, 50)}


# =========================================================================== modifications
def _statut(g: Graphe, noeud: str) -> str:
    return g.noeuds[noeud].statut if noeud in g.noeuds else "validé"


def ajouter_noeud(id: str, type: str, libelle: str, description: str = "", plateformes: list | None = None,
                  auteur: str = "automaticien") -> dict:
    if id in _graphe().noeuds:
        raise FileExistsError(f"Le nœud {id} existe déjà.")
    return declarations.ajouter_noeud(id, type, libelle, description, plateformes=plateformes, auteur=auteur)


def modifier_noeud(id: str, auteur: str = "automaticien", **champs) -> dict:
    g = _graphe()
    if id not in g.noeuds:
        raise KeyError(f"Élément inconnu : {id}")
    return declarations.modifier_noeud(id, _statut(g, id), auteur, **champs)


def supprimer_noeud(id: str, auteur: str = "automaticien"):
    g = _graphe()
    if id not in g.noeuds:
        raise KeyError(f"Élément inconnu : {id}")
    declarations.supprimer_noeud(id, _statut(g, id), auteur)


def ajouter_relation(de: str, vers: str, type: str, auteur: str = "automaticien") -> dict:
    g = _graphe()
    for x in (de, vers):
        if x not in g.noeuds:
            raise KeyError(f"Élément inconnu : {x}")
    return declarations.ajouter_relation(de, vers, type, auteur)


def supprimer_relation(rid: str, auteur: str = "automaticien"):
    g = _graphe()
    r = g.relations.get(rid)
    if not r:
        raise KeyError(f"Relation inconnue : {rid}")
    declarations.supprimer_relation(rid, r.statut, auteur)


def valider(id: str):
    """Validation humaine d'une proposition (nœud ou relation)."""
    if "|" in id:
        declarations.valider_relation(id)
    else:
        modifier_noeud(id, statut="validé")


def rejeter(id: str, motif: str = ""):
    """Rejet humain durable d'une proposition (nœud ou relation)."""
    return declarations.rejeter(id, motif)


def fusionner(source: str, cible: str):
    g = _graphe()
    for x in (source, cible):
        if x not in g.noeuds:
            raise KeyError(f"Élément inconnu : {x}")
    if g.noeuds[source].type != g.noeuds[cible].type:
        raise ValueError("On ne fusionne que deux éléments du même type.")
    declarations.fusionner(source, cible)


def exporter(nom: str, **params) -> dict:
    vues = {"connaissance": vue_connaissance, "couverture": vue_couverture, "flux": vue_flux}
    if nom not in vues:
        raise KeyError(f"Graphe inconnu : {nom}")
    return vues[nom](**params)


# =========================================================================== assistant
def _vue_graphe(nom: str, cible: str = "", module: str = "") -> Graphe:
    from atelier.execution import flux
    from atelier.intelligence import couverture

    g = _graphe()
    if nom == "couverture":
        return couverture.vue(g, module)
    if nom == "flux":
        return flux.vue(g, cible if cible in g.noeuds else "")
    if nom == "connaissance":
        return g
    raise KeyError(f"Graphe inconnu : {nom}")


def anomalies(nom: str = "connaissance", module: str = "") -> list[dict]:
    from atelier.intelligence import assistant, patrimoine_xray

    return assistant.anomalies(_vue_graphe(nom, module=module), patrimoine_xray.charger_vue())


def demander_ia(nom: str, intention: str, selection: str = "", question: str = "", cible: str = "",
                module: str = "") -> dict:
    from atelier.intelligence import assistant, patrimoine_xray

    return assistant.demander(_vue_graphe(nom, cible, module), nom, intention, selection, question,
                              patrimoine_xray.charger_vue())
