"""Qualification d'une release, build après build.

Release → Builds → analyse d'impact → périmètre de non-régression → exécutions → résultats de qualification.

Chaque build reçu est une livraison rattachée à la release : numéro, date de réception, description, contenu (évolutions et
corrections, collé), anomalies corrigées, changements par rapport au build précédent. Son contenu est lu et rattaché au
Knowledge Graph comme une Release Note (releases.py), puis COMPARÉ au build précédent et au périmètre initial de la release :
nouvelles évolutions, corrections, anomalies à retester, fonctionnalités nouvellement impactées, sorties du périmètre initial.

Périmètre d'un build, en trois catégories, chaque test avec sa raison :
- Retest : tests qui vérifient les anomalies déclarées corrigées (liens test ↔ bug de Xray et du Knowledge Graph) ;
- Non-régression ciblée : tests liés aux évolutions du build, impact direct (élément touché) ou indirect (même module) ;
- Qualification : tests critiques (criticité, étiquettes smoke / tnr / critique / sanity), qui sécurisent la release.
Le QA accepte, écarte (justifié) ou ajoute ; il valide le périmètre, l'envoie à Execution Center, puis déclare le build
Passed ou Failed. Rien n'est décidé seul.

Continuité : chaque build garde son analyse, son périmètre validé (instantané), sa campagne, son verdict et l'état des
anomalies à sa réception ; on ne repart jamais de zéro. Un build Passed ne qualifie pas la release : la qualification
dépend des résultats cumulés et de critères de sortie, évalués et affichés, et reste une décision du QA (dérogation
justifiée si un critère bloquant n'est pas satisfait).

Résultats : dernier statut Xray de chaque test (copie locale), compté pour le build s'il est postérieur à sa réception.
"""
from __future__ import annotations

import re
from datetime import date

from atelier.intelligence import releases as R

STATUTS = ("Reçu", "Périmètre validé", "En exécution", "Passed", "Failed")
CATEGORIES = {"retest": "Retest", "ciblee": "Non-régression ciblée", "qualification": "Qualification"}
ORDRE = {"retest": 0, "ciblee": 1, "qualification": 2}


def _pilotage():
    from atelier.intelligence import pilotage

    return pilotage


def _normal(t: str) -> str:
    return " ".join(sorted(R._mots(t)))


def _noeuds(evolutions: list) -> dict:
    """{nœud confirmé: libellé} d'une liste d'évolutions."""
    return {l["noeud"]: l["libelle"] for e in evolutions or [] for l in e.get("liens") or [] if l["etat"] == "confirmé"}


# =========================================================================== réception d'un build
def recevoir(rid: str, numero: str, date_reception: str = "", description: str = "", texte: str = "", anomalies: str = "",
             changements: str = "") -> dict:
    """Enregistre un build reçu pour la release. Le contenu collé est découpé en évolutions et rattaché au Knowledge Graph ;
    les anomalies corrigées sont les clés Jira listées (champ dédié) et celles citées dans les corrections du contenu."""
    r = R._lire(rid)
    numero = str(numero or "").strip()[:40]
    if not numero:
        raise ValueError("Numéro du build obligatoire.")
    if any(b["numero"].casefold() == numero.casefold() for b in r.get("builds") or []):
        raise FileExistsError(f"Le build {numero} est déjà enregistré pour cette release.")
    texte, a = R.lire_note(texte)
    declarees = sorted(set(R._CLE_JIRA.findall(anomalies or "")))
    citees = sorted({k for e in a["evolutions"] if e["type"] == "correction" for k in e["cles_jira"]})
    p = _pilotage()
    ouvertes = sorted(b["cle"] for b in p._sur(p._bugs, [])[0] or [] if p._etat_bug(b) not in ("resolu", "ferme"))
    n = max([int(b["id"][1:]) for b in r.get("builds") or []] or [0]) + 1
    b = {"id": f"B{n}", "numero": numero, "date_reception": R._date(date_reception) or date.today().isoformat(),
         "description": (description or "").strip()[:4000], "changements": (changements or "").strip()[:4000], "texte": texte,
         "evolutions": a["evolutions"], "anomalies_declarees": declarees, "anomalies_citees": [k for k in citees if k not in declarees],
         "anomalies_ouvertes_a_reception": ouvertes, "statut": "Reçu", "decisions": {}, "recu_par": R._auteur(), "recu_le": R._maintenant()}
    r.setdefault("builds", []).append(b)
    R._journal(r, "build reçu", build=numero, evolutions=len(a["evolutions"]), anomalies=len(declarees) + len(b["anomalies_citees"]))
    R._ecrire(r)
    return vue(rid, b["id"])


# =========================================================================== analyse : comparaison et périmètre
def _tests_du_noeud(g, nid: str) -> tuple[set, set]:
    """(tests directs, modules touchés) d'un élément du graphe, par l'analyse d'impact (relations fiables seulement)."""
    from atelier.discovery import connaissance

    directs, modules = set(), set()
    if nid not in g.noeuds:
        return directs, modules
    try:
        imp = connaissance.analyser_impact(g, nid)
        directs |= {t["id"].split(":", 1)[1] for t in imp.get("tests_xray") or []}
        modules |= set(imp.get("modules") or [])
    except Exception:  # noqa: BLE001 — un impact incalculable n'empêche pas d'afficher le build
        pass
    if g.noeuds[nid].type in ("user_story", "epic", "bug"):
        directs |= {x.vers.split(":", 1)[1] for x in g.sortants(nid, fiables=True) if x.type == "teste_par" and x.vers.startswith("test:")}
    return directs, modules


def _anomalies(b: dict) -> list[str]:
    return list(dict.fromkeys((b.get("anomalies_declarees") or []) + (b.get("anomalies_citees") or [])))


def analyser(r: dict, b: dict, g=None) -> dict:
    """Comparaison du build avec le build précédent et le périmètre initial, puis périmètre recommandé en trois catégories."""
    p = _pilotage()
    g = g or R._graphe()
    pat = p._pat()
    info = {t["cle"]: t for t in pat.get("tests") or []}
    builds = r.get("builds") or []
    i = builds.index(b)
    precedent = builds[i - 1] if i else None
    initial = _noeuds(r.get("evolutions"))
    avant = dict(initial)
    textes_avant = {_normal(e["texte"]) for e in r.get("evolutions") or []}
    for x in builds[:i]:
        avant.update(_noeuds(x["evolutions"]))
        textes_avant |= {_normal(e["texte"]) for e in x["evolutions"]}
    ici = _noeuds(b["evolutions"])

    # --- comparaison
    for e in b["evolutions"]:
        noeuds = [l["noeud"] for l in e.get("liens") or [] if l["etat"] == "confirmé"]
        e["etat"] = ("rattachée" if noeuds else "à trancher" if any(l["etat"] == "proposé" for l in e.get("liens") or []) else "non rattachée")
        e["nouveaute"] = ("déjà livrée" if _normal(e["texte"]) in textes_avant
                          else "touche le périmètre existant" if noeuds and all(n in avant for n in noeuds) else "nouvelle")
    bugs = {x["cle"]: x for x in p._sur(p._bugs, [])[0] or []}
    a_retester = []
    for cle in _anomalies(b):
        x = bugs.get(cle) or {}
        nid = R._noeud_de_la_cle(g, cle)
        tests = set(x.get("tests") or []) | (_tests_du_noeud(g, nid)[0] if nid else set())
        a_retester.append({"cle": cle, "resume": x.get("resume") or (g.noeuds[nid].libelle if nid else ""), "statut": x.get("statut", ""),
                           "etat": p._etat_bug(x) if x else "inconnue", "tests": sorted(tests), "connue": bool(x or nid)})
    comparaison = {
        "precedent": precedent["numero"] if precedent else "",
        "nouvelles": [e["id"] for e in b["evolutions"] if e["nouveaute"] == "nouvelle"],
        "deja_livrees": [e["id"] for e in b["evolutions"] if e["nouveaute"] == "déjà livrée"],
        "corrections": [e["id"] for e in b["evolutions"] if e["type"] == "correction"],
        "fonctionnalites_nouvelles": [{"noeud": n, "libelle": l} for n, l in ici.items() if n not in avant],
        "hors_perimetre_initial": [{"noeud": n, "libelle": l} for n, l in ici.items() if n not in initial] if r.get("evolutions") else [],
        "anomalies_a_retester": a_retester,
        "non_rattachees": [e["id"] for e in b["evolutions"] if e["etat"] != "rattachée"],
    }

    # --- périmètre recommandé
    reco: dict = {}

    def ajouter(cle, categorie, motif, impact=""):
        x = reco.setdefault(cle, {"test": cle, "categorie": categorie, "impact": impact, "motifs": []})
        if ORDRE[categorie] < ORDRE[x["categorie"]] or (categorie == x["categorie"] == "ciblee" and impact == "direct"):
            x["categorie"], x["impact"] = categorie, impact or x["impact"]
        if motif not in x["motifs"]:
            x["motifs"].append(motif)
    for a in a_retester:
        for t in a["tests"]:
            ajouter(t, "retest", f"vérifie l'anomalie corrigée {a['cle']}")
    for e in b["evolutions"]:
        for l in [l for l in e.get("liens") or [] if l["etat"] == "confirmé"]:
            directs, modules = _tests_du_noeud(g, l["noeud"])
            # impact indirect : les autres tests du module de l'élément, ou des modules de ses tests directs
            modules |= {info[t].get("module") for t in directs if t in info and info[t].get("module")}
            n = g.noeuds.get(l["noeud"])
            if n and n.type == "module":
                modules.add(n.libelle)
            for t in directs:
                ajouter(t, "ciblee", f"{R.TYPES.get(e['type'], 'évolution')} : {l['libelle']}", "direct")
            for t in pat.get("tests") or []:
                if t.get("module") in modules and t["cle"] not in directs:
                    ajouter(t["cle"], "ciblee", f"même module ({t['module']}) que {l['libelle']}", "indirect")
    for t in pat.get("tests") or []:
        crit = str(t.get("criticite") or "").casefold() in p.CRITIQUES
        etiq = next((x for x in t.get("libelles") or [] if str(x).casefold() in p.ETIQUETTES_SECURITE), "")
        if crit or etiq:
            ajouter(t["cle"], "qualification", f"criticité métier ({t['criticite']})" if crit else f"étiquette « {etiq} »")
    for cle, d in (b.get("decisions") or {}).items():
        if d.get("decision") == "ajoutée":
            ajouter(cle, "ciblee", f"ajouté par {d.get('par', '?')} : {d.get('motif', '')}".strip(" :"), "ajout")

    publies = p._publies()[0]
    lignes = []
    for cle, x in reco.items():
        t = info.get(cle) or {}
        sx = t.get("statut_xray") or {}
        classe = p._classe(sx.get("statut", ""))
        execute = classe in ("reussi", "echec", "bloque") and str(sx.get("fin") or "")[:10] >= b["date_reception"]
        d = (b.get("decisions") or {}).get(cle) or {}
        lignes.append({**x, "resume": t.get("resume", ""), "module": t.get("module", ""), "criticite": t.get("criticite", ""), "connu": cle in info,
                       "automatise": cle in publies, "dernier_statut": sx.get("statut", ""), "derniere_execution": str(sx.get("fin") or "")[:10],
                       "execute": execute, "resultat": classe if execute else "", "decision": d.get("decision", ""),
                       "decision_par": d.get("par", ""), "decision_motif": d.get("motif", "")})
    lignes.sort(key=lambda x: (ORDRE[x["categorie"]], x["impact"] != "direct", x["test"]))
    return {"comparaison": comparaison, "perimetre": lignes}


def _retenus(lignes: list) -> list:
    return [x for x in lignes if x["decision"] != "rejetée"]


def _resultats(lignes: list) -> dict:
    ret = _retenus(lignes)
    n = len(ret)
    return {"retenus": n, "executes": sum(x["execute"] for x in ret), "reussis": sum(x["resultat"] == "reussi" for x in ret),
            "echecs": sum(x["resultat"] == "echec" for x in ret), "bloques": sum(x["resultat"] == "bloque" for x in ret),
            "non_executes": sum(not x["execute"] for x in ret), "automatises": sum(x["automatise"] for x in ret),
            "par_categorie": {c: sum(x["categorie"] == c for x in ret) for c in CATEGORIES}}


def _anomalies_du_build(b: dict, lignes: list) -> dict:
    """Anomalies du build : déclarées corrigées (confirmées ou non par Jira), nouvelles et résiduelles sur son périmètre."""
    p = _pilotage()
    tests = {x["test"] for x in _retenus(lignes)}
    a_reception = set(b.get("anomalies_ouvertes_a_reception") or [])
    declarees = set(_anomalies(b))
    nouvelles, residuelles, corrigees, non_confirmees = [], [], [], []
    for x in p._sur(p._bugs, [])[0] or []:
        fiche = {"cle": x["cle"], "resume": x.get("resume", ""), "statut": x.get("statut", ""), "priorite": x.get("priorite", ""),
                 "tests": sorted(set(x.get("tests") or []) & tests)}
        ouvert = p._etat_bug(x) not in ("resolu", "ferme")
        if x["cle"] in declarees:
            (non_confirmees if ouvert else corrigees).append(fiche)
        elif ouvert and fiche["tests"]:
            (residuelles if x["cle"] in a_reception else nouvelles).append(fiche)
    connues = {x["cle"] for x in corrigees + non_confirmees}
    return {"corrigees": corrigees, "corrigees_non_confirmees": non_confirmees, "nouvelles": nouvelles, "residuelles": residuelles,
            "declarees_inconnues": sorted(declarees - connues)}


def vue(rid: str, bid: str) -> dict:
    """Vue d'un build : contenu, comparaison, périmètre (recommandé, ou validé), résultats et anomalies."""
    r = R._lire(rid)
    b = R._build(r, bid)
    a = analyser(r, b)
    lignes = a["perimetre"]
    if b.get("perimetre_valide"):  # le périmètre validé est figé : les tests retenus à la validation, recalculés pour leurs résultats
        figes = set(b["perimetre_valide"]["tests"])
        lignes = [x for x in lignes if x["test"] in figes] + [{"test": t, "categorie": "ciblee", "impact": "", "motifs": ["retenu à la validation"], "resume": "",
                                                               "module": "", "criticite": "", "connu": False, "automatise": False, "dernier_statut": "",
                                                               "derniere_execution": "", "execute": False, "resultat": "", "decision": "acceptée",
                                                               "decision_par": "", "decision_motif": ""}
                                                              for t in sorted(figes - {x["test"] for x in lignes})]
    return {"release": {k: r.get(k, "") for k in ("id", "nom", "version", "date_prevue")}, **b, **a, "perimetre": lignes,
            "resultats": _resultats(lignes), "anomalies": _anomalies_du_build(b, lignes), "types": R.TYPES, "categories": CATEGORIES}


# =========================================================================== décisions du QA sur un build
def operer(rid: str, bid: str, op: str, **p) -> dict:
    """Décisions sur un build, toutes tracées : décider d'un test (acceptée, rejetée justifiée, ajoutée, « » pour annuler),
    valider le périmètre, l'envoyer à Execution Center, déclarer le build Passed ou Failed, rouvrir, supprimer."""
    r = R._lire(rid)
    b = R._build(r, bid)
    par = R._auteur()
    if op == "decider":
        test, decision, motif = str(p.get("test") or "").strip().upper(), str(p.get("decision") or ""), str(p.get("motif") or "").strip()
        if decision not in ("acceptée", "rejetée", "ajoutée", ""):
            raise ValueError("Décision : acceptée, rejetée, ajoutée, ou vide pour l'annuler.")
        if not test:
            raise ValueError("Clé du test obligatoire.")
        if b["statut"] != "Reçu":
            raise PermissionError("Le périmètre de ce build est déjà validé : le rouvrir pour le modifier.")
        if decision == "rejetée" and len(motif) < 5:
            raise ValueError("Justifier l'exclusion (5 caractères au moins).")
        if decision == "ajoutée" and test not in {t["cle"] for t in _pilotage()._pat().get("tests") or []}:
            raise ValueError(f"{test} n'est pas un test connu de la copie Xray.")
        if decision:
            b.setdefault("decisions", {})[test] = {"decision": decision, "motif": motif[:400], "par": par, "date": R._maintenant()}
        else:
            b.get("decisions", {}).pop(test, None)
        R._journal(r, f"test {decision or 'remis en recommandation'}", build=b["numero"], test=test, motif=motif[:120])
    elif op == "valider":
        if b["statut"] != "Reçu":
            raise ValueError("Périmètre déjà validé.")
        retenus = [x["test"] for x in _retenus(analyser(r, b)["perimetre"])]
        if not retenus:
            raise ValueError("Aucun test dans le périmètre : ajouter des tests, ou rattacher les évolutions au Knowledge Graph.")
        b["perimetre_valide"] = {"tests": retenus, "par": par, "date": R._maintenant()}
        b["statut"] = "Périmètre validé"
        R._journal(r, "périmètre validé", build=b["numero"], tests=len(retenus))
    elif op == "campagne":
        if b["statut"] not in ("Périmètre validé", "En exécution"):
            raise ValueError("Valider d'abord le périmètre du build.")
        from atelier.execution import centre

        lignes = [x for x in analyser(r, b)["perimetre"] if x["test"] in set(b["perimetre_valide"]["tests"])]
        autos = [x["test"] for x in lignes if x["automatise"]]
        if not autos:
            raise ValueError("Aucun test automatisé dans le périmètre validé : les tests manuels s'exécutent dans Xray.")
        # plateformes : celles choisies, sinon celles des scripts des tests retenus
        plateformes = p.get("plateformes") or sorted({pl for x in _pilotage()._referentiel() for pl in x.get("plateformes") or []
                                                      if set([x["cle_xray"]] if isinstance(x.get("cle_xray"), str) else x.get("cle_xray") or []) & set(autos)})
        avant = {c["id"] for c in centre.campagnes()}
        apres = centre.enregistrer_campagne({"nom": str(p.get("nom") or "").strip() or f"{r['nom']} · build {b['numero']}", "type": "TNR",
                                             "plateformes": plateformes, "environnement": str(p.get("environnement") or ""), "tests": autos,
                                             "description": f"Qualification de {r['nom']}, build {b['numero']} (reçu le {b['date_reception']})."})
        c = next(c for c in apres if c["id"] not in avant)
        b.setdefault("campagnes", []).append({"id": c["id"], "nom": c["nom"], "tests": len(autos), "par": par, "date": R._maintenant()})
        b["statut"] = "En exécution"
        R._journal(r, "campagne créée", build=b["numero"], campagne=c["id"], tests=len(autos))
    elif op in ("passed", "failed"):
        if b["statut"] == "Reçu":
            raise ValueError("Valider d'abord le périmètre du build.")
        motif = str(p.get("motif") or "").strip()
        res = _resultats(vue(rid, bid)["perimetre"])
        if op == "passed" and (res["echecs"] or res["non_executes"]) and len(motif) < 10:
            raise ValueError(f"{res['echecs']} test(s) en échec et {res['non_executes']} non exécuté(s) : justifier le verdict Passed (10 caractères au moins).")
        b["statut"] = "Passed" if op == "passed" else "Failed"
        b["verdict"] = {"par": par, "date": R._maintenant(), "motif": motif[:400], "resultats": res}
        R._journal(r, f"build déclaré {b['statut']}", build=b["numero"], motif=motif[:120])
    elif op == "rouvrir":
        b["statut"] = "Reçu"
        b.pop("perimetre_valide", None)
        b.pop("verdict", None)
        R._journal(r, "build rouvert", build=b["numero"])
    elif op == "supprimer":
        r["builds"].remove(b)
        R._journal(r, "build supprimé", build=b["numero"])
        R._ecrire(r)
        return {"supprime": bid}
    else:
        raise ValueError(f"Opération inconnue : {op}")
    if op != "decider" and (r.get("qualification") or {}).get("etat", "").startswith("Qualifiée"):
        r["qualification"] = {"etat": "En cours", "rouverte_par": par, "date": R._maintenant()}  # un build a changé : la qualification est à refaire
        R._journal(r, "qualification à refaire (un build a changé)")
    R._ecrire(r)
    return vue(rid, bid)


# =========================================================================== vue release et qualification
def criteres_sortie(r: dict, vues: list[dict]) -> list[dict]:
    """Critères de sortie de la release, évalués sur les résultats cumulés (le dernier build fait foi pour les tests)."""
    p = _pilotage()
    dernier = vues[-1] if vues else None
    ouvertes = [a for v in vues for a in v["anomalies"]["nouvelles"] + v["anomalies"]["residuelles"] + v["anomalies"]["corrigees_non_confirmees"]]
    ouvertes = list({a["cle"]: a for a in ouvertes}.values())
    critiques = [a for a in ouvertes if str(a.get("priorite") or "").casefold() in p.CRITIQUES]

    def crit(id_, libelle, valeur, ok, bloquant, detail=""):
        return {"id": id_, "libelle": libelle, "valeur": valeur, "etat": "non mesurable" if ok is None else "satisfait" if ok else "non satisfait",
                "bloquant": bloquant, "detail": detail}
    res = dernier["resultats"] if dernier else None
    retest = [x for x in (dernier["perimetre"] if dernier else []) if x["categorie"] == "retest" and x["decision"] != "rejetée"]
    qualif = [x for x in (dernier["perimetre"] if dernier else []) if x["categorie"] == "qualification" and x["decision"] != "rejetée"]
    return [
        crit("dernier_build", "Dernier build déclaré Passed", dernier["statut"] if dernier else "aucun build", (dernier["statut"] == "Passed") if dernier else False, True,
             dernier["numero"] if dernier else ""),
        crit("anomalies_critiques", "Anomalies critiques ouvertes", len(critiques), len(critiques) == 0, True, ", ".join(a["cle"] for a in critiques)),
        crit("retests", "Retests du dernier build réussis", f"{sum(x['resultat'] == 'reussi' for x in retest)}/{len(retest)}",
             all(x["resultat"] == "reussi" for x in retest) if dernier else None, True),
        crit("qualification", "Tests de qualification du dernier build réussis", f"{sum(x['resultat'] == 'reussi' for x in qualif)}/{len(qualif)}",
             all(x["resultat"] == "reussi" for x in qualif) if dernier and qualif else None, True),
        crit("executes", "Périmètre du dernier build exécuté", f"{res['executes']}/{res['retenus']}" if res else "—",
             (res["non_executes"] == 0) if res and res["retenus"] else None, False),
        crit("anomalies_ouvertes", "Anomalies ouvertes sur la release", len(ouvertes), len(ouvertes) == 0, False, ", ".join(a["cle"] for a in ouvertes[:10])),
    ]


def tableau(rid: str) -> dict:
    """Vue release : builds, avancement, anomalies cumulées, couverture, critères de sortie, qualification."""
    r = R._lire(rid)
    g = R._graphe()
    vues = []
    for b in r.get("builds") or []:
        a = analyser(r, b, g)
        lignes = a["perimetre"] if not b.get("perimetre_valide") else [x for x in a["perimetre"] if x["test"] in set(b["perimetre_valide"]["tests"])]
        vues.append({"id": b["id"], "numero": b["numero"], "date_reception": b["date_reception"], "statut": b["statut"], "perimetre": lignes,
                     "resultats": _resultats(lignes), "anomalies": _anomalies_du_build(b, lignes), "comparaison": a["comparaison"],
                     "evolutions": len(b["evolutions"]), "verdict": b.get("verdict")})
    tests = {x["test"]: x for v in vues for x in _retenus(v["perimetre"])}
    executes = {x["test"] for v in vues for x in v["perimetre"] if x["execute"]}
    criteres = criteres_sortie(r, vues)
    ouvertes = {a["cle"] for v in vues for a in v["anomalies"]["nouvelles"] + v["anomalies"]["residuelles"] + v["anomalies"]["corrigees_non_confirmees"]}
    return {**{k: r.get(k, "") for k in ("id", "nom", "version", "date_prevue", "perimetre", "statut", "texte", "cree")},
            "qualification": r.get("qualification") or {"etat": "En cours"},
            "builds": [{k: v[k] for k in ("id", "numero", "date_reception", "statut", "resultats", "evolutions", "verdict")}
                       | {"anomalies_ouvertes": len(v["anomalies"]["nouvelles"]) + len(v["anomalies"]["residuelles"]) + len(v["anomalies"]["corrigees_non_confirmees"]),
                          "anomalies_corrigees": len(v["anomalies"]["corrigees"]), "nouvelles_evolutions": len(v["comparaison"]["nouvelles"]),
                          "a_retester": len(v["comparaison"]["anomalies_a_retester"])} for v in vues],
            "indicateurs": {"builds": len(vues), "builds_passed": sum(v["statut"] == "Passed" for v in vues), "builds_failed": sum(v["statut"] == "Failed" for v in vues),
                            "anomalies_ouvertes": len(ouvertes), "tests": len(tests), "tests_executes": len(executes & set(tests)),
                            "couverture": p_cent(len(executes & set(tests)), len(tests)),
                            "criteres_satisfaits": sum(c["etat"] == "satisfait" for c in criteres), "criteres": len(criteres),
                            "bloquants_non_satisfaits": sum(c["bloquant"] and c["etat"] != "satisfait" for c in criteres)},
            "criteres_sortie": criteres}


def p_cent(a: int, b: int):
    return round(100 * a / b, 1) if b else None


def qualifier(rid: str, motif: str = "", annuler: bool = False) -> dict:
    """Décision du QA : release qualifiée si tous les critères bloquants sont satisfaits ; sinon seulement avec une
    dérogation justifiée (20 caractères au moins), tracée comme telle. annuler : la qualification revient « En cours »."""
    r = R._lire(rid)
    if annuler:
        r["qualification"] = {"etat": "En cours", "rouverte_par": R._auteur(), "date": R._maintenant()}
        R._journal(r, "qualification annulée")
    else:
        t = tableau(rid)
        manquants = [c["libelle"] for c in t["criteres_sortie"] if c["bloquant"] and c["etat"] != "satisfait"]
        motif = (motif or "").strip()
        if manquants and len(motif) < 20:
            raise ValueError("Critères bloquants non satisfaits : " + " ; ".join(manquants) + ". Qualifier par dérogation demande une justification (20 caractères au moins).")
        r["qualification"] = {"etat": "Qualifiée par dérogation" if manquants else "Qualifiée", "par": R._auteur(), "date": R._maintenant(),
                              "motif": motif[:600], "criteres_non_satisfaits": manquants,
                              "build": (r.get("builds") or [{}])[-1].get("numero", "")}
        R._journal(r, r["qualification"]["etat"].lower(), motif=motif[:120])
    R._ecrire(r)
    return tableau(rid)


def numero_suivant(rid: str) -> str:
    """Proposition de numéro pour le prochain build : le dernier, incrémenté s'il finit par un nombre."""
    r = R._lire(rid)
    d = (r.get("builds") or [{}])[-1].get("numero", "")
    m = re.search(r"(\d+)$", d)
    return (d[: m.start()] + str(int(m.group(1)) + 1).zfill(len(m.group(1)))) if m else ""
