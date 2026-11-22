"""Services des espaces de travail : vues de graphes prêtes à afficher, détail d'un nœud,
modifications déclarées (avec contrôle du statut actuel), analyse d'impact, export.

Le graphe est reconstruit à chaque demande à partir des sources (carte, dépôt, instantané Xray,
déclarations) : pas de cache qui pourrait diverger des fichiers.
"""
from __future__ import annotations

from atelier.discovery import connaissance
from atelier.domain import declarations, ontologie
from atelier.domain.graphe import CATEGORIES, TYPES_NOEUDS, TYPES_RELATIONS, Graphe

MAX_NOEUDS = 600  # au-delà, l'interface demande de filtrer (lisibilité)


def _graphe() -> Graphe:
    return connaissance.construire()


def _typer(g: Graphe, d: dict) -> dict:
    """Lecture métier ajoutée à chaque nœud et relation affichés (ontologie cible : type typé, relation métier, sens,
    système d'origine, statut de validation). Les champs historiques restent : les écrans actuels les lisent encore."""
    types = {i: ontologie.type_cible(n, g) for i, n in g.noeuds.items()}
    for n in d["noeuds"]:
        t = types.get(n["id"])
        if t:
            n["metier"] = {"type": t, "libelle": ontologie.TYPES_CIBLES[t][1], "univers": ontologie.TYPES_CIBLES[t][0]}
    for x in d["relations"]:
        rel = g.relations.get(x["id"])
        if rel and rel.de in g.noeuds and rel.vers in g.noeuds:
            x["metier"] = ontologie.metier(rel, g, types)
    return d


TYPES_CLES = ("application", "module", "fonctionnalite", "parcours", "ecran", "scenario", "user_story", "epic", "test")


def _limiter(g: Graphe, prioritaires: set | None = None) -> dict:
    """Au-delà de MAX_NOEUDS, l'AFFICHAGE est une sélection (le référentiel n'est jamais tronqué) : d'abord l'élément
    sélectionné et le périmètre demandé, puis leurs voisins directs, puis les éléments clés (modules, parcours, écrans,
    tests…) les plus reliés, puis le reste. Ce qui n'est pas affiché est compté par type (« masques_par_type »)."""
    total = len(g.noeuds)
    if total > MAX_NOEUDS:
        prio = set(prioritaires or ()) & set(g.noeuds)
        voisins = {r.vers for r in g.relations.values() if r.de in prio} | {r.de for r in g.relations.values() if r.vers in prio}
        degre: dict = {}
        for r in g.relations.values():
            degre[r.de] = degre.get(r.de, 0) + 1
            degre[r.vers] = degre.get(r.vers, 0) + 1
        rang = lambda i: (0 if i in prio else 1 if i in voisins else 2 if g.noeuds[i].type in TYPES_CLES else 3,  # noqa: E731
                          -degre.get(i, 0), CATEGORIES.index(g.noeuds[i].categorie), i)
        garde = sorted(g.noeuds, key=rang)[:MAX_NOEUDS]
        masques: dict = {}
        for i in set(g.noeuds) - set(garde):
            masques[g.noeuds[i].type] = masques.get(g.noeuds[i].type, 0) + 1
        g = g.sous_graphe(garde)
        return {**_typer(g, g.vers_dict()), "tronque": True, "total": total, "masques_par_type": masques}
    return {**_typer(g, g.vers_dict()), "tronque": False}


def referentiel() -> dict:
    return {"types": TYPES_NOEUDS, "categories": CATEGORIES, "relations": TYPES_RELATIONS}


def _projet_id() -> str:
    from atelier.domain import projet

    return projet.PROJECT_DIR.name


def ontologie_cible() -> dict:
    """Vocabulaire contrôlé du Knowledge Graph : univers, types de nœuds, relations typées, systèmes d'origine,
    statuts de validation (les éléments « extension » sont hors de la spécification)."""
    return {"univers": list(ontologie.UNIVERS),
            "types": [{"type": t, "univers": u, "libelle": l, "extension": x} for t, (u, l, x) in ontologie.TYPES_CIBLES.items()],
            "relations": [{"type": t, "famille": f, "libelle": l, "extension": x} for t, (f, l, x) in ontologie.RELATIONS.items()],
            "source_system": list(ontologie.SYSTEMES), "validation_status": list(ontologie.STATUTS)}


def property_graph() -> dict:
    """Le graphe du projet au format cible (nœuds et arêtes typés), indépendant du stockage."""
    return ontologie.property_graph(_graphe(), _projet_id())


def rapport_migration() -> dict:
    """Cohérence de la migration vers les relations typées, sur le graphe du projet."""
    return ontologie.rapport_migration(_graphe(), _projet_id())


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


TYPES_PERIMETRE = ("module", "parcours", "fonctionnalite", "epic", "user_story")


def perimetres() -> dict:
    """Périmètres proposés pour réduire les graphes : modules, parcours, fonctionnalités, epics, US (avec le nombre
    d'éléments qu'ils contiennent)."""
    g = _graphe()
    out = {t: [] for t in TYPES_PERIMETRE}
    for n in g.noeuds.values():
        if n.type in out:
            out[n.type].append({"id": n.id, "libelle": n.libelle, "statut": n.statut,
                                "elements": len([r for r in g.sortants(n.id) if r.type == "contient"])})
    for t in out:
        out[t].sort(key=lambda x: x["libelle"].lower())
    return out


def ids_perimetre(g, nid: str) -> set[str]:
    """Le périmètre et tout ce qu'il contient (relations « contient », propositions comprises), puis un pas de
    voisinage depuis chacun (locators, tests, exigences, règles…) pour garder le contexte ; la navigation n'est
    gardée qu'entre écrans du périmètre."""
    if nid not in g.noeuds:
        raise KeyError(f"Périmètre inconnu : {nid}")
    coeur = g.atteignables(nid, "aval", {"contient"}, fiables=False)
    if g.noeuds[nid].type in ("epic", "user_story", "fonctionnalite", "parcours"):  # tests et écrans liés à l'exigence
        for i in list(coeur):
            coeur |= {r.vers for r in g.sortants(i) if r.type in ("teste_par", "impacte", "utilise")}
    garde = set(coeur)
    for r in g.relations.values():
        if r.type == "navigue_vers":  # navigation : seulement à l'intérieur du périmètre
            continue
        if r.de in coeur:
            garde.add(r.vers)
        elif r.vers in coeur and r.type != "contient":  # pas de remontée vers les autres modules / l'application
            garde.add(r.de)
    return garde


def filtres_disponibles(g: Graphe) -> dict:
    """Valeurs proposées par les filtres de l'écran, lues dans le référentiel complet."""
    types: dict = {}
    for n in g.noeuds.values():
        types[n.type] = types.get(n.type, 0) + 1
    return {"applications": sorted(({"id": i, "libelle": n.libelle} for i, n in g.noeuds.items() if n.type == "application"), key=lambda x: x["id"]),
            "plateformes": sorted({p for n in g.noeuds.values() for p in n.plateformes}),
            "versions": sorted((n.id.split(":", 1)[1] for n in g.noeuds.values() if n.type == "version"), reverse=True),
            "types": dict(sorted(types.items()))}


def vue_connaissance(types: list[str] | None = None, categories: list[str] | None = None, plateforme: str = "",
                     recherche: str = "", centre: str = "", profondeur: int = 1, patrimoine: str = "lie",
                     perimetre: str = "", version: str = "") -> dict:
    """patrimoine « lie » (défaut) : la connaissance de l'application et les seuls tickets Jira / Xray qui s'y
    rattachent ; « tout » : toute la copie locale Jira / Xray. Un centre ou une recherche montrent toujours tout."""
    g = _graphe()
    filtres = filtres_disponibles(g)
    masques = 0
    if perimetre:
        g = g.sous_graphe(ids_perimetre(g, perimetre))
    if centre:
        if centre not in g.noeuds:
            raise KeyError(f"Élément inconnu : {centre}")
        g = g.voisinage([centre], max(1, min(profondeur, 4)))
    elif patrimoine != "tout" and not recherche.strip():
        garde = patrimoine_lie(g)
        masques = sum(1 for i, n in g.noeuds.items() if i not in garde and n.type in PATRIMOINE + ("module",))
        g = g.sous_graphe(garde)
    vue = g.filtrer(types, categories, plateforme, recherche, version)
    if (types or plateforme or version) and not centre:
        projeter_liens(g, vue)
    prio = {centre} if centre else (ids_perimetre(g, perimetre) if perimetre and perimetre in g.noeuds else set())
    d = connaissance.DERNIERE_CONSTRUCTION.get("delta") or {}
    return {**_limiter(vue, prio), "patrimoine_masque": masques, "filtres": filtres,
            "construction": {"date": connaissance.DERNIERE_CONSTRUCTION.get("date"), "modifies": d.get("modifies", []),
                             "retires": len(d.get("retires", []))}}


def projeter_liens(complet, vue, max_par_noeud: int = 12):
    """Vue filtrée (ex. « Fonctionnel ») : deux éléments affichés reliés par un élément masqué (écran, composant…)
    reçoivent un lien « lié via » (pointillé, jamais stocké), avec ce qui les relie : aucune vue ne laisse des nœuds isolés
    alors que la connaissance les relie. Seuls les liens fiables (observés, déclarés, déduits validés) sont projetés."""
    from collections import defaultdict

    gardes = set(vue.noeuds)
    voisins = defaultdict(set)
    for r in complet.relations.values():
        if not r.fiable:
            continue
        voisins[r.de].add(r.vers)
        voisins[r.vers].add(r.de)
    existants = {frozenset((r.de, r.vers)) for r in vue.relations.values()}
    via: dict = defaultdict(set)
    for x, autour in voisins.items():
        if x in gardes or complet.noeuds[x].type in ("application", "plateforme", "version", "environnement"):
            continue  # un nœud qui relie tout (l'application…) ne dit rien d'un lien entre deux éléments
        affiches = sorted(a for a in autour if a in gardes)
        if len(affiches) < 2 or len(affiches) > 40:  # nœud masqué trop central : il relierait tout à tout
            continue
        for i, a in enumerate(affiches):
            for b in affiches[i + 1:]:
                if frozenset((a, b)) not in existants:
                    via[(a, b)].add(x)
    par_noeud: dict = defaultdict(int)
    for (a, b), xs in sorted(via.items(), key=lambda kv: -len(kv[1])):
        if par_noeud[a] >= max_par_noeud or par_noeud[b] >= max_par_noeud:
            continue
        types = sorted({complet.noeuds[x].type for x in xs})
        r = vue.relier(a, b, "lie_via", provenance="déduit", statut="validé", source="projection de la vue",
                       proprietes={"via": sorted(xs)[:10], "nombre": len(xs), "types": types})
        if r:
            par_noeud[a] += 1
            par_noeud[b] += 1


def vue_couverture(module: str = "", afficher: str = "tous", recherche: str = "", test: str = "") -> dict:
    """test (clé Xray) : ouvre la vue sur le module du test, ou sur sa seule traçabilité s'il n'a pas de module ;
    le test est renvoyé dans « focus » pour être sélectionné et centré."""
    from atelier.intelligence import couverture, patrimoine_xray

    g = _graphe()
    pat = patrimoine_xray.charger_vue()
    focus = ""
    if test:
        focus = test if test.startswith("test:") else f"test:{test}"
        module = module or couverture.module_du_test(g, focus)
    v = couverture.vue(g, module, afficher) if module or not focus else couverture.vue_test(g, focus)
    if focus and focus not in v.noeuds:  # filtre manuels / automatisés qui l'excluait : on garde le test demandé
        v = couverture.vue_test(g, focus)
    v = v.filtrer(recherche=recherche)
    return {**_limiter(v), "indicateurs": couverture.indicateurs(g, pat), "instantane": patrimoine_xray.etat(),
            "modules": sorted({n.libelle for n in g.noeuds.values() if n.type == "module"}), "module": module, "focus": focus}


def qualite() -> dict:
    """Indicateurs de qualité du référentiel (pas des erreurs de construction) : nœuds orphelins (hors parcours
    simplement déclaré : information de complétude), relations non validées, parcours incomplets, fonctionnalités sans
    test, tests sans parcours ni fonctionnalité, écrans sans parcours, tests sans résultat, relations dont le sens métier
    n'est pas reconnu pour cette paire de types (incohérentes)."""
    g = _graphe()
    n, rels = g.noeuds, list(g.relations.values())
    lies = {r.de for r in rels} | {r.vers for r in rels}
    entrants: dict = {}
    for r in rels:
        entrants.setdefault(r.vers, []).append(r)
    sortants: dict = {}
    for r in rels:
        sortants.setdefault(r.de, []).append(r)
    lib = lambda ids: sorted(({"id": i, "libelle": n[i].libelle, "type": n[i].type} for i in ids), key=lambda x: x["id"])[:40]  # noqa: E731
    orphelins = [i for i, x in n.items() if i not in lies and not (x.type == "parcours" and x.proprietes.get("completude") == "déclaré")]
    incomplets = [i for i, x in n.items() if x.type == "parcours" and x.proprietes.get("completude") not in ("exploré", "confirmé")]
    verifiees = {r.vers for r in rels if r.type in ("verifie", "teste_par", "verifiee_sur") and r.confirmee}
    verifiees |= {r.de for r in rels if r.type == "teste_par" and r.confirmee}
    f_sans_test = [i for i, x in n.items() if x.type == "fonctionnalite" and i not in verifiees]
    t_sans_cible = [i for i, x in n.items() if x.type == "scenario"
                    and not any(r.type in ("verifie", "couvre") for r in sortants.get(i, []))]
    e_sans_parcours = [i for i, x in n.items() if x.type == "ecran"
                       and not any(r.type == "contient" and n[r.de].type == "parcours" for r in entrants.get(i, []))]
    sans_resultat = [i for i, x in n.items() if x.type == "test_robot" and not x.proprietes.get("dernier_statut")]
    non_validees = [r for r in rels if r.statut != "validé"]
    incoherentes = [r for r in rels if ontologie.metier(r, g)["generique"]]
    bloc = lambda ids, aide: {"nombre": len(ids), "elements": lib(ids), "aide": aide}  # noqa: E731
    return {
        "orphelins": bloc(orphelins, "Éléments sans aucune relation."),
        "parcours_incomplets": {**bloc(incomplets, "Parcours déclarés, découverts ou partiellement explorés."),
                                "par_completude": {c: sum(1 for i in incomplets if n[i].proprietes.get("completude") == c)
                                                   for c in ("déclaré", "découvert", "partiellement exploré")}},
        "fonctionnalites_sans_test": bloc(f_sans_test, "Aucun test ne les vérifie (lien confirmé)."),
        "tests_sans_parcours": bloc(t_sans_cible, "Tests BDD qui ne vérifient aucun parcours et ne couvrent aucun écran."),
        "ecrans_sans_parcours": bloc(e_sans_parcours, "Écrans qu'aucun parcours ne traverse."),
        "tests_sans_resultat": bloc(sans_resultat, "Tests Robot jamais exécutés (aucun output.xml)."),
        "relations_non_validees": {"nombre": len(non_validees), "aide": "Propositions à valider : hors couverture, impact et TNR officiels."},
        "relations_incoherentes": {"nombre": len(incoherentes), "aide": "Relations dont le sens métier n'est pas reconnu pour cette paire de types.",
                                   "exemples": [{"de": r.de, "type": r.type, "vers": r.vers} for r in incoherentes[:20]]},
        "doublons_bdd": couverture_doublons(),
    }


def couverture_doublons() -> list[dict]:
    from atelier.intelligence import couverture

    try:
        return couverture.doublons_bdd()
    except Exception:  # noqa: BLE001 — un test BDD illisible ne bloque pas les indicateurs
        return []


def candidats(module: str = "") -> list[dict]:
    from atelier.intelligence import couverture, patrimoine_xray

    return couverture.candidats(_graphe(), patrimoine_xray.charger_vue(), module)


def vue_flux(cible: str = "", mode: str = "verifie", module: str = "") -> dict:
    from atelier.execution import flux

    g = _graphe()
    tests = sorted(({"id": i, "libelle": n.libelle} for i, n in g.noeuds.items()
                    if n.type == "test_robot" or n.type == "scenario" or (n.type == "test" and n.proprietes.get("automatise"))),
                   key=lambda x: x["id"])
    return {**_limiter(flux.vue(g, cible, mode, module)), "cibles": tests, "mode": mode,
            "modules": sorted({n.libelle for n in g.noeuds.values() if n.type == "module"})}


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
        return {"relation": {**r.vers_dict(), "metier": ontologie.metier(r, g)},
                "noeud": {"id": o.id, "type": o.type, "libelle": o.libelle, "categorie": o.categorie,
                          "metier": ontologie.TYPES_CIBLES[ontologie.type_cible(o, g)][1]}}
    sortants = [lien(r, r.vers) for r in g.sortants(noeud)]
    entrants = [lien(r, r.de) for r in g.entrants(noeud)]
    voisins = {x["noeud"]["id"] for x in sortants + entrants}
    proches = g.voisinage([noeud], 2).noeuds
    histo = declarations.historique(noeud, 50)
    t = ontologie.type_cible(n, g)
    return {"noeud": {**n.vers_dict(), "metier": {"type": t, "libelle": ontologie.TYPES_CIBLES[t][1], "univers": ontologie.TYPES_CIBLES[t][0],
                                                   "id": ontologie.id_cible(n, t),
                                                   "validation_status": ontologie.statut_validation(n.provenance, n.statut)}},
            "sortants": sortants, "entrants": entrants,
            "tests_xray": sorted(i for i in proches if g.noeuds[i].type == "test"),
            "tests_robot": sorted(i for i in proches if g.noeuds[i].type == "test_robot"),
            "scenarios_bdd": sorted(i for i in proches if g.noeuds[i].type in ("scenario", "feature")),
            "nb_voisins": len(voisins), "historique": histo,
            "provenance": _provenance(n, histo), "tracabilite": _tracabilite(g, noeud, set(proches))}


TRACABILITE = (("exigences", ("fonctionnalite", "user_story", "epic", "regle")), ("parcours", ("parcours",)),
               ("tests", ("scenario", "test", "test_robot")), ("plans", ("test_plan", "test_set")),
               ("executions", ("test_execution", "resultat")), ("anomalies", ("bug",)))


def _tracabilite(g: Graphe, noeud: str, proches: set) -> dict:
    """Ce qui est relié à l'élément à deux pas au plus : exigences, parcours, tests (BDD, Xray, Robot), plans, exécutions,
    anomalies ; chaque entrée dit si le chemin est confirmé (lien direct confirmé, ou deux liens confirmés)."""
    conf = g.confirme().voisinage([noeud], 2).noeuds
    out = {}
    for cle, types in TRACABILITE:
        ids = sorted(i for i in proches if i != noeud and g.noeuds[i].type in types)
        out[cle] = [{"id": i, "libelle": g.noeuds[i].libelle, "type": g.noeuds[i].type, "confirme": i in conf} for i in ids[:40]]
    return out


def _provenance(n, histo: list) -> dict:
    p = n.proprietes or {}
    dates = [h.get("date") for h in histo if h.get("date")]
    return {"provenance": n.provenance, "source": n.source, "fichier": p.get("fichier") or (n.source if "/" in (n.source or "") else ""),
            "statut": n.statut, "confiance": n.confiance,
            "validation": ontologie.statut_validation(n.provenance, n.statut),
            "premiere_trace": min(dates) if dates else (p.get("cree") or ""), "derniere_trace": max(dates) if dates else ""}


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
    if type == "verifiee_sur":
        raise PermissionError("« Vérifiée sur » est une preuve issue des tests : elle ne se déclare pas à la main.")
    from atelier.discovery import correlation

    a, b = g.noeuds[de], g.noeuds[vers]
    if type == "impacte" and {a.type, b.type} & set(correlation.TYPES_EXIGENCE) and "ecran" in (a.type, b.type):
        # exigence ↔ écran : même modèle que Discovery › Corrélation (« réalisé par », exigence → écran)
        ex, ec = (a, b) if b.type == "ecran" else (b, a)
        if not ec.proprietes.get("id_carte"):
            raise ValueError(f"L'écran {ec.libelle} n'est pas dans la carte de l'application : il faut l'avoir vu pendant "
                             "une Discovery avant de le relier à une exigence.")
        if auteur == "automaticien":
            return correlation.confirmer(ec.proprietes["id_carte"], ex.proprietes.get("cle") or ex.id.split(":", 1)[1], "manuel")
        de, vers = ex.id, ec.id
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
        return flux.vue(g, cible if cible in g.noeuds else "", "exploratoire", ensemble=True)
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
