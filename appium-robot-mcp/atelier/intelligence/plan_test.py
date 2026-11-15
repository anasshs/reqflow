"""Plan de test d'un module : résumé structuré du Knowledge Graph pour l'agent (Cursor / Claude) ou l'automaticien,
au lieu du graphe brut (qui peut compter des milliers de nœuds quand les modules s'accumulent).

Contenu, uniquement depuis les sources du graphe (carte, déclarations validées ou proposées, dépôt Robot, copie
locale Jira / Xray) : écrans et leurs locators fragiles, parcours, fonctionnalités, règles, exigences Jira avec leurs
tests Xray (automatisés ou non, dernier statut), ce qui n'est pas couvert, actions sensibles, endpoints, pistes.
Rien n'est estimé : un élément absent du graphe n'apparaît pas.
"""
from __future__ import annotations

EXIGENCES = ("epic", "user_story", "bug")


def _module(g, module: str) -> str:
    nid = module if module.startswith("module:") else f"module:{module}"
    if nid in g.noeuds:
        return nid
    m = next((i for i, n in g.noeuds.items() if n.type == "module" and n.libelle.lower() == module.lower().replace("module:", "")), None)
    if not m:
        modules = sorted(n.libelle for n in g.noeuds.values() if n.type == "module")
        raise KeyError(f"Module inconnu : {module} (modules : {', '.join(modules) or 'aucun'}).")
    return m


def plan(module: str, g=None) -> dict:
    """g : graphe déjà construit (le cerveau calcule tous les modules sur un seul graphe)."""
    from atelier.discovery import connaissance, espaces
    from atelier.intelligence import patrimoine_xray

    g = g or connaissance.construire()
    nid = _module(g, module)
    coeur = g.atteignables(nid, "aval", {"contient"}, fiables=False)
    zone = espaces.ids_perimetre(g, nid)
    pat = {t["cle"]: t for t in (patrimoine_xray.charger_vue() or {"tests": []})["tests"]}

    def statut_xray(cle):
        return ((pat.get(cle) or {}).get("statut_xray") or {}).get("statut", "")

    def tests_xray_de(i):
        out = []
        for r in g.sortants(i):
            if r.type == "teste_par" and r.vers in g.noeuds and g.noeuds[r.vers].type == "test":
                t = g.noeuds[r.vers]
                cle = t.proprietes.get("cle") or t.libelle.split()[0]
                out.append({"cle": cle, "resume": t.proprietes.get("resume") or "", "automatise": bool(t.proprietes.get("automatise")),
                            "dernier_resultat_robot": t.proprietes.get("dernier_resultat", ""), "statut_xray": statut_xray(cle)})
        return out

    ecrans = []
    for i in sorted(x for x in coeur if g.noeuds[x].type == "ecran"):
        n = g.noeuds[i]
        locs = [g.noeuds[r.vers] for r in g.sortants(i) if r.type == "contient" and g.noeuds.get(r.vers) and g.noeuds[r.vers].type == "locator"]
        imp = connaissance.analyser_impact(g, i)
        ecrans.append({"id": i, "nom": n.libelle, "elements": len({x.libelle for x in locs}),
                       "locators_fragiles": sorted({x.libelle for x in locs if x.proprietes.get("fiabilite") not in ("robuste", None)}),
                       "actions_sensibles": sorted({x.libelle for x in locs if x.proprietes.get("classe_action") in ("sensitive", "forbidden")}),
                       "tests_robot": len(imp["tests_robot"]), "tests_xray": [t["id"].split(":", 1)[1] for t in imp["tests_xray"]],
                       "vers": sorted({g.noeuds[r.vers].libelle for r in g.sortants(i) if r.type == "navigue_vers" and r.vers in g.noeuds})})

    def noeuds(types):
        return [{"id": i, "libelle": g.noeuds[i].libelle, "statut": g.noeuds[i].statut, "source": g.noeuds[i].source,
                 "description": g.noeuds[i].proprietes.get("description", "")} for i in sorted(zone) if g.noeuds[i].type in types]

    parcours = noeuds(("parcours",))
    for p in parcours:
        p["ecrans"] = [r.vers.split(":", 1)[1] for r in g.sortants(p["id"]) if r.type == "contient" and r.vers.startswith("ecran:")]
    exigences = []
    for i in sorted(x for x in zone if g.noeuds[x].type in EXIGENCES):
        n = g.noeuds[i]
        tests = tests_xray_de(i)
        exigences.append({"cle": n.proprietes.get("cle") or i.split(":", 1)[1], "type": n.type, "resume": n.proprietes.get("resume") or n.libelle,
                          "statut": n.proprietes.get("statut", ""), "tests": tests,
                          "couverture": "aucun test" if not tests else "automatisée" if all(t["automatise"] for t in tests) else "manuelle (à automatiser)"})
    par_cle = {e["cle"]: e for e in exigences}
    for e in exigences:  # un epic est couvert à travers ses US
        if e["type"] == "epic" and not e["tests"]:
            enfants = [g.noeuds[r.vers].proprietes.get("cle") for r in g.sortants(f"epic:{e['cle']}") if r.type == "contient" and r.vers in g.noeuds]
            couverts = [k for k in enfants if k in par_cle and par_cle[k]["tests"]]
            if couverts:
                e["couverture"] = f"via ses US ({len(couverts)}/{len(enfants)})"
    ecrans_sans_test = [e["nom"] for e in ecrans if not e["tests_robot"] and not e["tests_xray"]]
    us_sans_test = [e["cle"] for e in exigences if e["type"] == "user_story" and not e["tests"]]
    a_automatiser = sorted({t["cle"] for e in exigences for t in e["tests"] if not t["automatise"]})
    echecs = sorted({t["cle"] for e in exigences for t in e["tests"] if "FAIL" in (t["statut_xray"] or t["dernier_resultat_robot"] or "").upper()})
    pistes = []
    if us_sans_test:
        pistes.append(f"{len(us_sans_test)} US sans test : écrire les cas (Test Design › US à couvrir, ou testabilité).")
    for p in parcours:
        sans = [e for e in p["ecrans"] if e in ecrans_sans_test]
        if sans:
            pistes.append(f"Parcours « {p['libelle']} » : écrans sans test ({', '.join(sans)}) : discovery_parcours_vers_bdd.")
    if a_automatiser:
        pistes.append(f"{len(a_automatiser)} test(s) Xray manuels à automatiser : {', '.join(a_automatiser[:10])}.")
    fragiles = [e["nom"] for e in ecrans if e["locators_fragiles"]]
    if fragiles:
        pistes.append(f"Locators fragiles sur {len(fragiles)} écran(s) ({', '.join(fragiles[:5])}) : demander des identifiants stables aux développeurs.")
    sensibles = sorted({a for e in ecrans for a in e["actions_sensibles"]})
    if sensibles:
        pistes.append(f"Actions sensibles ({', '.join(sensibles[:8])}) : scénarios à autoriser explicitement, environnement dédié.")
    if echecs:
        pistes.append(f"Tests en échec : {', '.join(echecs[:10])} : analyser (Failure Analysis) avant d'étendre la couverture.")
    return {"module": g.noeuds[nid].libelle, "id": nid,
            "resume": {"ecrans": len(ecrans), "parcours": len(parcours), "regles": len(noeuds(("regle",))), "exigences": len(exigences),
                       "us_sans_test": len(us_sans_test), "ecrans_sans_test": len(ecrans_sans_test), "tests_a_automatiser": len(a_automatiser),
                       "actions_sensibles": len(sensibles)},
            "ecrans": ecrans, "parcours": parcours, "fonctionnalites": noeuds(("fonctionnalite",)), "regles": noeuds(("regle",)),
            "exigences": exigences, "endpoints": [n["libelle"] for n in noeuds(("endpoint",))],
            "non_couvert": {"us": us_sans_test, "ecrans": ecrans_sans_test}, "a_automatiser": a_automatiser, "echecs": echecs,
            "pistes": pistes}
