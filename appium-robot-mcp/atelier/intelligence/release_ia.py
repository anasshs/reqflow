"""Interprétation d'une release ou d'un build par Cursor (par défaut) ou l'IA configurée.

Les règles de l'atelier découpent le texte ligne par ligne et rapprochent par les mots ; elles ne comprennent pas
qu'« optimisation du paiement » touche le virement, ni qu'un paragraphe contient trois évolutions. L'interprétation est
donc confiée par défaut à Cursor, qui lit (outil MCP `release_a_interpreter`) :
  - le texte de la Release Note ou du build, et ce que les règles en ont tiré ;
  - la connaissance de l'application : éléments du Knowledge Graph (US, epics, bugs, écrans, modules, parcours…) ;
  - le patrimoine de tests (Xray : module, criticité, exigences, dernier résultat, automatisé ou non) ;
  - les anomalies (Jira) et le périmètre proposé par les règles.
Puis il dépose (`release_deposer_interpretation`) :
  - les évolutions, chacune rattachée à des éléments du graphe, avec une justification ;
  - pour un build, les tests à ajouter au périmètre (retest, non-régression ciblée, qualification) ou à écarter.

Le serveur contrôle chaque proposition (élément du graphe connu, test connu, catégorie connue, justification présente,
décision humaine jamais écrasée) et renvoie les refus motivés. Ce qui est retenu devient la proposition PAR DÉFAUT :
rattachements utilisés par l'analyse d'impact, tests ajoutés ou écartés dans le périmètre. Le QA garde la main : il
délie, garde un test écarté, écarte un test ajouté, puis valide. Rien n'est écrit dans Jira ni Xray par l'IA.
Sans IA, les règles restent le secours, présentées comme telles.
"""
from __future__ import annotations

import json

from atelier.intelligence import releases as R

ACTIONS = ("ajouter", "ecarter")
SOURCE_CURSOR = "Cursor (MCP)"
OUTILS_CURSOR = "release_a_interpreter puis release_deposer_interpretation"
CONSIGNE = (
    "Interprète le texte comme un QA senior qui connaît l'application. 1) Évolutions : découpe le texte en évolutions "
    "(une par changement fonctionnel ou correction, même dans un paragraphe), donne leur type (nouvelle, modification, "
    "correction, technique, suppression) et rattache chacune aux éléments du Knowledge Graph qu'elle touche (US, epic, bug, "
    "écran, module, parcours, endpoint), par leur identifiant exact de la liste « elements ». Reprends l'identifiant de "
    "l'évolution des règles (« evolution ») quand c'est la même ; sinon donne son texte. 2) Pour un build : propose les tests "
    "à AJOUTER au périmètre proposé par les règles (catégorie retest pour une anomalie corrigée, ciblee pour un impact "
    "fonctionnel, qualification pour un test critique) et ceux à ÉCARTER (sans rapport réel avec le build), par la clé du "
    "test de la liste « tests ». Une justification courte et vérifiable pour chaque proposition. N'invente ni élément ni "
    "test : ce qui n'est pas dans les listes est refusé. Le QA valide dans l'atelier ; rien n'est écrit dans Jira ni Xray.")


def _cible(r: dict, bid: str = "") -> tuple[dict | None, list]:
    if not bid:
        return None, r.setdefault("evolutions", [])
    b = R._build(r, bid)
    return b, b["evolutions"]


# =========================================================================== lecture pour l'IA
def a_interpreter(rid: str, bid: str = "", limite_elements: int = 400, limite_tests: int = 400) -> dict:
    """Tout ce qu'il faut pour interpréter la Release Note (sans build) ou un build : texte masqué, extraction des règles,
    éléments du Knowledge Graph, tests, anomalies, périmètre des règles, consigne et format de dépôt.

    Contexte construit par pertinence, jamais le patrimoine entier par défaut : d'abord les tests du périmètre des
    règles et ceux des éléments déjà rattachés, puis ceux de leurs modules, puis le reste ; plafonds et niveau de détail
    réglables pour l'opération (Paramètres › IA : max_tests, max_elements, detail). En détail « minimal », seuls les
    tests pertinents et ceux de leurs modules sont transmis, sans résumé des éléments."""
    from atelier.intelligence import builds, jugement_ia, pilotage as p
    from atelier.intelligence.ia import config

    op = "non_regression.interpretation"
    ctx = config.contexte(op)
    limite_elements = config.plafond(op, "max_elements", limite_elements)
    limite_tests = config.plafond(op, "max_tests", limite_tests)
    minimal = ctx.get("detail") == "minimal"
    r = R._lire(rid)
    b, evolutions = _cible(r, bid)
    g = R._graphe()
    court = jugement_ia.court
    v = builds.analyser(r, b, g, delta=False) if b else None
    rattaches = {l["noeud"] for e in evolutions for l in e.get("liens") or [] if l["etat"] != "rejeté"}
    pertinents = {x["test"] for x in (v["perimetre"] if v else []) if x["impact"] != "ia"}
    for nid in rattaches:
        pertinents |= builds._tests_du_noeud(g, nid)[0]
    pat = p._pat()
    tous = pat.get("tests") or []
    modules = {t.get("module") for t in tous if t["cle"] in pertinents and t.get("module")}
    rang = lambda t: 0 if t["cle"] in pertinents else 1 if t.get("module") in modules else 2  # noqa: E731
    choisis = sorted((t for t in tous if not minimal or rang(t) < 2), key=lambda t: (rang(t), t["cle"]))[:limite_tests]
    publies = p._publies()[0]
    tests = [{"test": t["cle"], "resume": court(t.get("resume"), 200), "module": t.get("module", ""), "criticite": t.get("criticite", ""),
              "etiquettes": t.get("libelles") or [], "exigences": t.get("exigences") or [], "automatise": t["cle"] in publies,
              "dernier_statut": (t.get("statut_xray") or {}).get("statut", ""), **({"etapes": t.get("etapes")} if ctx.get("detail") == "complet" and t.get("etapes") else {})}
             for t in choisis]
    noeuds = sorted(((nid, n) for nid, n in g.noeuds.items() if n.type in R.TYPES_NOEUD), key=lambda x: (x[0] not in rattaches, x[0]))
    elements = [{"id": nid, "type": n.type, "libelle": court(n.libelle, 160), **({} if minimal else {"resume": court(n.proprietes.get("resume") or "", 200)})}
                for nid, n in noeuds][:limite_elements]
    bugs = [{"cle": x["cle"], "resume": court(x.get("resume"), 200), "statut": x.get("statut", ""), "priorite": x.get("priorite", ""),
             "tests": x.get("tests") or []} for x in p._sur(p._bugs, [])[0] or []]
    sortie = {
        "release": {k: r.get(k, "") for k in ("id", "nom", "version", "date_prevue", "perimetre")},
        "cible": "build" if b else "release_note",
        "texte": court(b["texte"] if b else r.get("texte", ""), 8000),
        "evolutions_des_regles": [{"evolution": e["id"], "texte": court(e["texte"], 400), "type": e["type"],
                                   "rattachements": [{"id": l["noeud"], "libelle": l["libelle"], "etat": l["etat"], "origine": l.get("origine", "")}
                                                     for l in e.get("liens") or []]} for e in evolutions],
        "elements": elements, "tests": tests, "anomalies": bugs, "types": list(R.TYPES), "consigne": CONSIGNE,
        "contexte": {"tests_transmis": len(tests), "tests_du_patrimoine": len(tous), "tests_pertinents": len(pertinents), "detail": ctx.get("detail"),
                     "note": "tests classés par pertinence (périmètre des règles et éléments rattachés, puis leurs modules) ; "
                             "un test absent de la liste peut être cité par sa clé s'il existe dans Xray"},
        "format_depot": {"evolutions": [{"evolution": "E1 (ou vide pour une nouvelle)", "texte": "si nouvelle", "type": "modification",
                                         "elements": ["user_story:ABC-1"], "justification": "…"}],
                         "tests": [{"test": "ABC-301", "action": "ajouter | ecarter", "categorie": "retest | ciblee | qualification",
                                    "justification": "…"}], "synthese": "deux ou trois phrases sur le risque du build"},
    }
    if b:
        sortie["build"] = {"id": b["id"], "numero": b["numero"], "description": court(b.get("description"), 1000), "changements": court(b.get("changements"), 1000),
                           "anomalies_declarees": b.get("anomalies_declarees") or [], "precedent": v["comparaison"]["precedent"]}
        sortie["perimetre_des_regles"] = [{"test": x["test"], "categorie": x["categorie"], "impact": x["impact"], "motifs": x["motifs"]}
                                         for x in v["perimetre"] if x["impact"] != "ia"]
    return sortie


# =========================================================================== dépôt contrôlé
def deposer(rid: str, bid: str = "", evolutions: list | None = None, tests: list | None = None, synthese: str = "",
            source: str = SOURCE_CURSOR) -> dict:
    """Interprétation déposée par l'IA, contrôlée puis appliquée comme proposition par défaut. Un nouveau dépôt remplace
    l'avis précédent sur les tests ; les décisions du QA (rattachement rejeté ou confirmé, test gardé ou écarté) priment."""
    from atelier.intelligence import jugement_ia as _jia

    _jia.exiger_ia()
    from atelier.intelligence import jugement_ia, pilotage as p

    r = R._lire(rid)
    b, evos = _cible(r, bid)
    if b and b.get("statut") != "Reçu":
        raise ValueError(f"Le périmètre du build {b['numero']} est déjà validé : le rouvrir avant une nouvelle interprétation.")
    g = R._graphe()
    retenus, refus = {"evolutions": [], "tests": []}, []
    date_ = R._maintenant()
    for j in evolutions or []:
        j = j if isinstance(j, dict) else {}
        just = jugement_ia.justification(j.get("justification"))
        eid = str(j.get("evolution") or "").strip()
        noeuds = [str(x) for x in j.get("elements") or j.get("noeuds") or []]
        if not just:
            refus.append({"objet": eid or j.get("texte", ""), "raison": "justification obligatoire"})
            continue
        e = next((x for x in evos if x["id"] == eid), None)
        if eid and e is None:
            refus.append({"objet": eid, "raison": "évolution inconnue (reprendre un identifiant de « evolutions_des_regles » ou donner un texte)"})
            continue
        typ = str(j.get("type") or "").strip()
        if typ and typ not in R.TYPES:
            refus.append({"objet": eid or j.get("texte", ""), "raison": f"type inconnu : {typ}"})
            continue
        if e is None:
            texte = " ".join(str(j.get("texte") or "").split())
            if len(texte) < 5:
                refus.append({"objet": "", "raison": "nouvelle évolution sans texte"})
                continue
            n = max([int(x["id"][1:]) for x in evos] or [0]) + 1
            e = {"id": f"E{n}", "texte": texte[:1000], "type": typ or R._type(texte) or "modification", "rubrique": "", "ligne": 0, "ligne_fin": 0,
                 "cles_jira": sorted(set(R._CLE_JIRA.findall(texte))), "origine": f"interprétée par {source}", "liens": []}
            evos.append(e)
        elif typ and not e.get("type_par_qa"):
            e["type"] = typ
        e["interpretation_ia"] = {"source": source, "date": date_, "justification": just}
        liens = {l["noeud"]: l for l in e.setdefault("liens", [])}
        for nid in noeuds:
            if nid not in g.noeuds:
                refus.append({"objet": f"{e['id']} → {nid}", "raison": "élément inconnu du Knowledge Graph"})
                continue
            l = liens.get(nid)
            if l and l["etat"] == "rejeté":
                refus.append({"objet": f"{e['id']} → {nid}", "raison": "rattachement rejeté par le QA"})
                continue
            if l and l["etat"] == "confirmé":
                l.setdefault("avis_ia", just)
                continue
            fiche = {**R._fiche(g, nid), "etat": "confirmé", "origine": f"{source} : {just}"[:400], "ia": True, "par": source, "date": date_}
            if l:
                l.update(fiche)
            else:
                e["liens"].append(fiche)
            retenus["evolutions"].append({"evolution": e["id"], "element": nid})
        # les propositions par mots que l'IA n'a pas retenues ne sont plus présentées : son interprétation fait foi par défaut
        e["liens"] = [l for l in e["liens"] if l["etat"] != "proposé"]
    avis_tests = []
    if b is not None:
        connus = {t["cle"] for t in p._pat().get("tests") or []}
        from atelier.intelligence import builds

        for j in tests or []:
            j = j if isinstance(j, dict) else {}
            cle = str(j.get("test") or "").strip().upper()
            action = str(j.get("action") or "").strip().lower().replace("é", "e")
            cat = str(j.get("categorie") or "ciblee").strip().lower().replace("é", "e")
            just = jugement_ia.justification(j.get("justification"))
            raison = ("test inconnu du patrimoine Xray" if cle not in connus else f"action : {', '.join(ACTIONS)}" if action not in ACTIONS
                      else f"catégorie : {', '.join(builds.CATEGORIES)}" if cat not in builds.CATEGORIES else "justification obligatoire" if not just else "")
            if raison:
                refus.append({"objet": cle or "?", "raison": raison})
                continue
            avis_tests = [x for x in avis_tests if x["test"] != cle] + [{"test": cle, "action": action, "categorie": cat, "justification": just}]
        b["avis_ia"] = {"source": source, "date": date_, "synthese": jugement_ia.justification(synthese)[:600], "tests": avis_tests, "refus": refus}
        retenus["tests"] = avis_tests
        R._journal(r, "build interprété par l'IA", build=b["numero"], source=source, rattachements=len(retenus["evolutions"]),
                   tests=len(avis_tests), refus=len(refus))
    else:
        r["interpretation_ia"] = {"source": source, "date": date_, "synthese": jugement_ia.justification(synthese)[:600], "refus": refus}
        if r.get("statut") == "Validée" and retenus["evolutions"]:
            r["statut"] = "Analysée"
            R._journal(r, "release repassée à « Analysée » (nouvelle interprétation)")
        R._journal(r, "Release Note interprétée par l'IA", source=source, rattachements=len(retenus["evolutions"]), refus=len(refus))
    R._ecrire(r)
    return {"retenus": retenus, "refus": refus, "source": source}


# =========================================================================== appel direct (LLM interne / Claude)
def interpreter_ia(rid: str, bid: str = "") -> dict:
    """Interprétation par l'IA à appel direct (texte masqué). Avec « cursor », l'atelier n'appelle rien : il le dit."""
    from atelier.intelligence import fournisseur_ia as ia

    if ia.fournisseur() == "cursor":
        return {"disponible": False, "raison": f"Fournisseur « cursor » : demander à Cursor (outils MCP {OUTILS_CURSOR})."}
    if not ia.configure():
        return {"disponible": False, "raison": f"IA « {ia.fournisseur()} » non disponible : interprétation par les règles uniquement (secours)."}
    lecture = a_interpreter(rid, bid, 250, 250)
    brut = ia.completer(CONSIGNE + " Réponds en JSON : {\"evolutions\": [...], \"tests\": [...], \"synthese\": \"...\"} selon « format_depot ».",
                        json.dumps({k: v for k, v in lecture.items() if k not in ("consigne",)}, ensure_ascii=False), 4000)
    try:
        j = ia.extraire_json(brut)
    except ValueError:
        j = {}
    j = j if isinstance(j, dict) else {}
    return {"disponible": True, **deposer(rid, bid, j.get("evolutions") or [], j.get("tests") or [], j.get("synthese") or "",
                                          f"IA {ia.fournisseur()} ({ia.modele()})")}


def etat_ia() -> dict:
    """Mode d'interprétation : cursor (par défaut quand Cursor est le fournisseur), appel direct, ou règles seules."""
    from atelier.intelligence import fournisseur_ia as ia

    f = ia.fournisseur()
    if ia.applicatif("non_regression.interpretation"):
        return {"fournisseur": f, "mode": "regles", "applicatif": True}
    return {"fournisseur": f, "mode": "cursor" if f == "cursor" else "direct" if ia.configure() else "regles"}
