"""Reste à explorer : ce que la carte de l'application ne couvre pas encore, pour mesurer l'utilité d'une exploration.

Une exploration ne rejoue pas les parcours : elle travaille sur la carte et n'essaie que ce qui n'a jamais été essayé.
Ce module répond à « que reste-t-il ? », à partir de données déjà présentes, sans rien estimer :
- les écrans qui ne sont dans aucun parcours validé (liens « parcours contient écran » du Knowledge Graph) ;
- les actions sûres jamais essayées, écran par écran (mémoire des actions de la carte, classement des actions) ;
- les actions non sûres jamais essayées (saisie, sensibles, interdites) : l'exploration autonome ne les fera jamais,
  elles demandent un parcours préparé ou une navigation à la main ;
- les impasses et les écrans sans entrée connue (navigation de la carte).

Périmètre : un module de la carte (« module:eSim ») ou un parcours validé (« parcours:… ») borne la question, et borne
l'exploration elle-même (exploration.py, assistance.py). Les écrans découverts pendant la session en font partie : c'est
le delta recherché. Un écran déjà connu hors du périmètre est une frontière : on y arrive, on ne repart pas de là.
"""
from __future__ import annotations

TYPES_PERIMETRE = {"module": "Module", "parcours": "Parcours validé"}


def perimetres() -> list[dict]:
    """Périmètres possibles : les modules de la carte, puis les parcours validés, avec leur nombre d'écrans."""
    from atelier.discovery import carte
    from atelier.domain import declarations

    if not carte.app_courante():
        return []
    ecrans = carte.ecrans()
    modules: dict = {}
    for e in ecrans:
        if e.get("module"):
            modules.setdefault(e["module"], set()).add(e["id"])
    out = [{"noeud": f"module:{m}", "type": "module", "libelle": m, "ecrans": sorted(ids)} for m, ids in sorted(modules.items(), key=lambda x: x[0].lower())]
    par_noeud = {f"ecran:{e.get('nom') or e['id']}": e["id"] for e in ecrans}
    data = declarations.charger()
    parcours: dict = {}
    for r in data["relations"].values():
        n = data["noeuds"].get(r["de"]) or {}
        if (r["type"] == "contient" and r["de"].startswith("parcours:") and r["vers"] in par_noeud and r.get("statut") == "validé"
                and n.get("statut", "validé") == "validé"):
            parcours.setdefault(r["de"], {"libelle": n.get("libelle") or r["de"].split(":", 1)[1], "ecrans": set()})["ecrans"].add(par_noeud[r["vers"]])
    out += [{"noeud": k, "type": "parcours", "libelle": v["libelle"], "ecrans": sorted(v["ecrans"])}
            for k, v in sorted(parcours.items(), key=lambda x: x[1]["libelle"].lower())]
    return out


def perimetre(noeud: str) -> dict | None:
    """Le périmètre désigné (identifiant « module:… » / « parcours:… », ou libellé sans ambiguïté) ; None s'il est vide.
    Un périmètre inconnu est une erreur : jamais d'exploration silencieusement non bornée."""
    texte = str(noeud or "").strip()
    if not texte:
        return None
    tous = perimetres()
    trouve = [p for p in tous if p["noeud"] == texte] or [p for p in tous if p["libelle"].lower() == texte.lower()]
    if len(trouve) != 1:
        raise KeyError(f"Périmètre inconnu ou ambigu : {texte} (modules de la carte ou parcours validés : "
                       f"{', '.join(p['noeud'] for p in tous) or 'aucun'}).")
    return trouve[0]


def _parcours_par_ecran() -> dict:
    """{nœud d'écran: {"valides": [libellés des parcours], "proposes": [...]}} depuis les liens déclarés du graphe."""
    from atelier.domain import declarations

    data = declarations.charger()
    out: dict = {}
    for r in data["relations"].values():
        if r["type"] == "contient" and r["de"].startswith("parcours:") and r["vers"].startswith("ecran:"):
            n = data["noeuds"].get(r["de"]) or {}
            libelle = n.get("libelle") or r["de"].split(":", 1)[1]
            # officiel seulement si le lien ET le parcours sont validés ; sinon ce n'est qu'une proposition
            officiel = r.get("statut") == "validé" and n.get("statut", "validé") == "validé"
            out.setdefault(r["vers"], {"valides": [], "proposes": []})["valides" if officiel else "proposes"].append(libelle)
    return out


def a_explorer(noeud: str = "") -> dict:
    """Synthèse et détail par écran de ce qui reste à explorer dans l'application active, ou dans un périmètre."""
    from atelier.discovery import assistance, carte, sessions_discovery

    if not carte.app_courante():
        return {"application": "", "carte_vide": True, "ecrans": [], "synthese": {}, "perimetres": [], "perimetre": None}
    choix = perimetre(noeud)
    tous = carte.ecrans()
    ecrans = [e for e in tous if e["id"] in set(choix["ecrans"])] if choix else tous
    par_ecran = _parcours_par_ecran()
    nav = sessions_discovery.navigation() if ecrans else {"impasses": [], "isoles": []}
    impasses, isoles = {x["id"] for x in nav["impasses"]}, {x["id"] for x in nav["isoles"]}
    lignes = []
    for e in ecrans:
        p = par_ecran.get(f"ecran:{e.get('nom') or e['id']}") or {"valides": [], "proposes": []}
        a_essayer, non_sures = [], 0
        for plat in sorted((e.get("plateformes") or {}).keys()):
            els = [{"key": k, "type": el.get("type"), "libelle": el.get("libelle") or "", "locators": (el.get("locators") or {}).get(plat) or []}
                   for k, el in (e.get("elements") or {}).items() if (el.get("locators") or {}).get(plat)]
            c = assistance.candidates(els, e["id"], plat)
            a_essayer += [{"cle": x["cle"], "libelle": x["libelle"], "plateforme": plat} for x in c["candidates"]]
            non_sures += sum(c["ecartees"].values())
        lignes.append({"id": e["id"], "nom": e.get("nom") or e.get("titre") or e["id"], "module": e.get("module") or "", "nomme": bool(e.get("nom")),
                       "parcours": sorted(set(p["valides"])), "parcours_proposes": sorted(set(p["proposes"]) - set(p["valides"])),
                       "hors_parcours": not p["valides"], "a_essayer": len(a_essayer), "a_essayer_exemples": a_essayer[:6], "non_sures": non_sures,
                       "impasse": e["id"] in impasses, "isole": e["id"] in isoles})
    lignes.sort(key=lambda x: (not x["hors_parcours"], -x["a_essayer"], x["nom"]))
    s = {"ecrans": len(lignes), "hors_parcours": sum(x["hors_parcours"] for x in lignes), "dans_un_parcours": sum(not x["hors_parcours"] for x in lignes),
         "a_essayer": sum(x["a_essayer"] for x in lignes), "non_sures": sum(x["non_sures"] for x in lignes),
         "impasses": sum(x["impasse"] for x in lignes), "isoles": sum(x["isole"] for x in lignes),
         "parcours_valides": len({p for x in lignes for p in x["parcours"]})}
    s["rien"] = bool(lignes) and not (s["hors_parcours"] or s["a_essayer"] or s["impasses"] or s["isoles"])
    s["sans_module"] = sum(1 for e in tous if not e.get("module"))  # écrans à ranger : ils n'entrent dans aucun périmètre « module »
    return {"application": carte.app_courante(), "carte_vide": not tous, "ecrans": lignes, "synthese": s,
            "perimetre": {k: choix[k] for k in ("noeud", "type", "libelle")} | {"ecrans": len(choix["ecrans"])} if choix else None,
            "perimetres": [{k: p[k] for k in ("noeud", "type", "libelle")} | {"ecrans": len(p["ecrans"])} for p in perimetres()]}
