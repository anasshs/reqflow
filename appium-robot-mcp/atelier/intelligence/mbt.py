"""Model-Based Testing : construction du modèle comportemental et moteur d'exploration (cahier MBT, § 5 à 9, 13 à 15).

Tout ce module est DÉTERMINISTE (aucun appel d'IA) : construction depuis le Knowledge Graph, la Discovery, les critères
d'acceptation et les règles ; exploration des chemins ; stratégies de couverture ; couverture comportementale ; impact
entre versions ; préparation à l'automatisation. L'IA n'intervient que par `proposer_ia` (propositions à valider).

Le modèle est stocké par atelier/domain/comportement.py ; un chemin devient un scénario BDD par
atelier/generation/mbt_bdd.py (référentiel et éditeur BDD existants).
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import deque

from atelier.domain import comportement as cm

STRATEGIES = {
    "etats": ("Couverture des états", "Chaque état est visité au moins une fois."),
    "transitions": ("Couverture des transitions", "Chaque transition est parcourue au moins une fois."),
    "paires": ("Couverture des paires de transitions", "Chaque enchaînement de deux transitions consécutives est vérifié."),
    "conditions": ("Couverture des conditions", "Chaque issue (vraie, fausse) de chaque condition métier est vérifiée."),
    "chemins": ("Couverture des chemins", "Les chemins possibles d'un état initial à un état final (boucles limitées)."),
    "critiques": ("Chemins critiques", "Les chemins métier prioritaires (priorité des transitions, état final atteint)."),
}
LIMITES_DEFAUT = {"profondeur": 12, "chemins": 40, "transitions_par_scenario": 10, "passages_boucle": 1}
POIDS_PRIORITE = {"haute": 3, "normale": 1, "basse": 0}
NEGATIF = re.compile(r"(?i)\b(refus|rejet|interdit|invalide|erron|erreur|impossible|bloqu|insuffisant|dépass|depass|ne\s+\w+\s+pas|n'est pas|incorrect|échec|echec|manquant)")
MOTS_VIDES = {"le", "la", "les", "de", "des", "du", "un", "une", "et", "ou", "je", "il", "elle", "sur", "dans", "pour", "par", "avec", "que",
              "qui", "est", "sont", "son", "sa", "ses", "au", "aux", "en", "à", "l", "d", "on", "se", "si", "lorsque", "quand", "alors", "doit"}
_CACHE: dict = {}


def _mots(t: str) -> set:
    import unicodedata

    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return {m for m in re.findall(r"[a-z0-9]+", t) if m not in MOTS_VIDES and len(m) > 2}


def _h(*parts) -> str:
    return hashlib.blake2b("|".join(map(str, parts)).encode(), digest_size=5).hexdigest()


def _graphe(g=None):
    if g is not None:
        return g
    from atelier.discovery import connaissance

    return connaissance.construire()


# =========================================================================== périmètres
NOMS_PERIMETRE = {"application": "Application", "module": "Module", "fonctionnalite": "Fonctionnalité", "parcours": "Parcours",
                  "user_story": "User Story", "ecran": "Écran", "regle": "Règle métier"}


def perimetres(g=None) -> dict:
    g = _graphe(g)
    out = {t: [] for t in cm.TYPES_PERIMETRE}
    for i, n in sorted(g.noeuds.items()):
        if n.type in out:
            out[n.type].append({"id": i, "libelle": n.libelle, "statut": n.statut})
    return out


def _noeud_perimetre(g, type_: str, id_: str) -> str:
    if type_ == "application":
        apps = sorted(i for i, n in g.noeuds.items() if n.type == "application")
        if id_ and id_ in apps:
            return id_
        if not apps:
            raise KeyError("Aucune application cartographiée : lancer une Discovery.")
        return apps[0]
    nid = id_ if id_.startswith(f"{type_}:") else f"{type_}:{id_}"
    if nid not in g.noeuds:
        raise KeyError(f"Élément inconnu : {nid}")
    return nid


def _ecrans_perimetre(g, type_: str, nid: str) -> tuple[list[str], list[str]]:
    """Écrans du périmètre (ordonnés pour un parcours) et ce qui manque pour le modéliser."""
    N, manquant = g.noeuds, []
    if type_ == "application":
        return sorted(i for i, n in N.items() if n.type == "ecran"), manquant
    if type_ == "module":
        return sorted(r.vers for r in g.sortants(nid) if r.type == "contient" and N[r.vers].type == "ecran"), manquant
    if type_ == "parcours":
        rels = sorted((r for r in g.sortants(nid, False) if r.type == "contient" and r.vers.startswith("ecran:")),
                      key=lambda r: (r.proprietes.get("ordre", 0), r.vers))
        if not rels:
            manquant.append("Parcours déclaré sans écran : le dérouler dans Discovery pour observer ses écrans et transitions.")
        return list(dict.fromkeys(r.vers for r in rels)), manquant
    if type_ == "ecran":
        voisins = {r.vers for r in g.sortants(nid) if r.type == "navigue_vers"} | {r.de for r in g.entrants(nid) if r.type == "navigue_vers"}
        return [nid] + sorted(voisins), manquant
    conf = g.confirme()
    proches = conf.voisinage([nid], 2).noeuds
    ecrans = sorted(i for i in proches if N[i].type == "ecran")
    if not ecrans:
        modules = [r.de for r in g.entrants(nid) if r.type == "contient" and N[r.de].type == "module"]
        ecrans = sorted({r.vers for m in modules for r in g.sortants(m) if r.type == "contient" and N[r.vers].type == "ecran"})
    if not ecrans:
        manquant.append(f"Aucun écran relié à {N[nid].libelle} : relier l'exigence à ses écrans (Discovery › Corrélation) ou "
                        "déclarer les états du comportement.")
    return ecrans, manquant


def _us_perimetre(g, type_: str, nid: str) -> list[str]:
    N = g.noeuds
    if type_ == "user_story":
        return [nid]
    if type_ in ("module", "fonctionnalite", "epic"):
        return sorted(r.vers for r in g.sortants(nid) if r.type == "contient" and N[r.vers].type == "user_story")
    if type_ == "parcours":
        return sorted(r.de for r in g.entrants(nid) if r.type == "associe_a" and N[r.de].type == "user_story")
    return []


def _criteres_us(g, us_id: str) -> list[str]:
    from atelier.discovery.intelligence_app import criteres

    cle = us_id.split(":", 1)[1]
    try:
        from atelier.intelligence import testabilite_us

        u = testabilite_us._us().get(cle)
    except Exception:  # noqa: BLE001
        u = None
    if u:
        return criteres({"description": "\n".join(x for x in (u.get("description"), u.get("criteres_jira")) if x)})
    p = g.noeuds[us_id].proprietes
    if isinstance(p.get("criteres"), list):
        return [str(c) for c in p["criteres"] if str(c).strip()]
    return criteres({"description": p.get("description") or ""})


def _sid(ecran: str) -> str:
    return "E-" + cm.slug(ecran.split(":", 1)[1], 60)


# =========================================================================== construction progressive
def construire(type_: str, id_: str = "", g=None, auteur: str = "atelier") -> dict:
    """Construit (ou actualise) le modèle comportemental d'un périmètre depuis le Knowledge Graph (écrans, actions,
    transitions observées, conditions observées), les critères d'acceptation des US (conditions et états d'erreur
    DÉDUITS, à valider) et les règles métier. Les déclarations, corrections et décisions du QA sont conservées ; une
    nouvelle version n'est créée que si le comportement change."""
    from atelier.discovery.intelligence_app import structurer

    g = _graphe(g)
    N = g.noeuds
    nid = _noeud_perimetre(g, type_, id_)
    app = next((n for n in N.values() if n.type == "application"), None)
    courante = next((i.split(":", 1)[1] for i, n in N.items() if n.type == "version" and n.proprietes.get("courante")), "")
    m = cm.nouveau(type_, nid, nom=f"{NOMS_PERIMETRE[type_]} {N[nid].libelle}", application=app.libelle if app else "",
                   version_application=courante)
    ecrans, manquant = _ecrans_perimetre(g, type_, nid)
    dans = set(ecrans)
    # ------------------------------------------------------------- états d'écran et transitions observées
    for e in ecrans:
        m["etats"][_sid(e)] = cm.element("observé", "carte (Discovery)", nom=N[e].libelle, type="ecran", ecran=e, description="",
                                         contexte="", initial=False, final=False)
    for e in ecrans:
        for r in g.sortants(e):
            if r.type != "permet" or N[r.vers].type != "action":
                continue
            a = N[r.vers]
            for r2 in g.sortants(a.id):
                if r2.type != "aboutit_a" or r2.vers not in dans or r2.vers == e or r2.proprietes.get("interdite"):
                    continue
                aid = "A-" + cm.slug(a.id.split(":", 1)[1], 70)
                if aid not in m["actions"]:
                    locs, kws = _technique_action(g, a)
                    m["actions"][aid] = cm.element("observé", "carte (Discovery)", libelle=a.libelle, ecran=e, cle=a.proprietes.get("cle", ""),
                                                   genre=a.proprietes.get("genre", ""), noeud=a.id, locators=locs, keywords=kws)
                garde = ""
                if r2.proprietes.get("condition"):
                    lib = str(r2.proprietes["condition"])
                    garde = "C-" + cm.slug(lib, 50)
                    m["conditions"].setdefault(garde, cm.element("observé", "carte (condition observée pendant la Discovery)", libelle=lib, regle=""))
                tid = "T-" + _h(e, r2.vers, a.id)
                ok = r.statut == "validé" and r2.statut == "validé"
                m["transitions"][tid] = cm.element(
                    "observé", f"carte ({r2.source or 'Discovery'})", "validé" if ok else "à valider", de=_sid(e), vers=_sid(r2.vers), action=aid,
                    evenement="", garde=garde, issue="vraie" if garde else "", preconditions="", postconditions=f"l'écran {N[r2.vers].libelle} est affiché",
                    priorite="normale", alternative=bool(r2.proprietes.get("alternative")), fiabilite=r2.proprietes.get("fiabilite"))
    # ------------------------------------------------------------- états initiaux et finaux
    entrees = {t["vers"] for t in m["transitions"].values()}
    sorties = {t["de"] for t in m["transitions"].values()}
    if type_ == "parcours" and ecrans:
        m["etats"][_sid(ecrans[0])]["initial"] = True
        m["etats"][_sid(ecrans[-1])]["final"] = True
    else:
        for sid, s in m["etats"].items():
            s["initial"] = sid not in entrees
            s["final"] = sid not in sorties
        if m["etats"] and not any(s["initial"] for s in m["etats"].values()):
            m["etats"][_sid(ecrans[0])]["initial"] = True
    # ------------------------------------------------------------- règles métier : conditions à rattacher
    for r in list(g.sortants(nid)) + [x for u in _us_perimetre(g, type_, nid) for x in g.sortants(u)]:
        if r.type in ("contient", "possede") and N[r.vers].type == "regle":
            rg = N[r.vers]
            cid = "C-R-" + cm.slug(rg.id.split(":", 1)[1], 50)
            m["conditions"].setdefault(cid, cm.element(rg.provenance, f"règle métier {rg.id}", "validé" if rg.statut == "validé" else "à valider",
                                                       justification=rg.proprietes.get("description", ""), libelle=rg.libelle, regle=rg.id))
    # ------------------------------------------------------------- critères d'acceptation : conditions, refus (déduits)
    us = _us_perimetre(g, type_, nid)
    initial = next((k for k, s in m["etats"].items() if s.get("initial")), "")
    for u in us:
        cle = u.split(":", 1)[1]
        for n, c in enumerate(_criteres_us(g, u), 1):
            s = structurer(c)
            cid = f"C-US-{cm.slug(cle, 30)}-{n}"
            m["conditions"][cid] = cm.element("déduit", f"US {cle}, critère {n}", justification=c, libelle=(s["condition"] or s["texte"])[:200],
                                              regle="", us=u, calcul=True)
            tid_ref = _transition_proche(m, s["action"] or c)
            src = m["transitions"][tid_ref]["de"] if tid_ref else _etat_cite(m, c) or initial
            if not src:
                manquant.append(f"US {cle}, critère {n} : aucun état où l'appliquer (écrans à découvrir ou à relier).")
                continue
            if NEGATIF.search(c):
                eid = f"E-ERR-{cm.slug(cle, 30)}-{n}"
                res = s["resultat"]
                m["etats"][eid] = cm.element("déduit", f"US {cle}, critère {n}", justification=c, nom=f"Refus : {res or 'résultat à confirmer'}"[:120],
                                             type="erreur", ecran=m["etats"][src].get("ecran", ""), description=c, contexte="", initial=False,
                                             final=True, us=u, calcul=True)
                m["transitions"]["T-" + _h(src, eid, cid)] = cm.element(
                    "déduit", f"US {cle}, critère {n}", justification=c, de=src, vers=eid,
                    action=m["transitions"][tid_ref]["action"] if tid_ref else "", evenement="", garde=cid, issue="fausse", preconditions="",
                    postconditions=res, postconditions_a_confirmer=not res, priorite="haute", us=u, calcul=True)
                if not res:
                    manquant.append(f"US {cle}, critère {n} : résultat attendu du refus non précisé (message, état) : à confirmer.")
            elif tid_ref and not m["transitions"][tid_ref].get("garde"):
                m["transitions"][tid_ref].update(garde=cid, issue="vraie", garde_deduite=True)
            elif not tid_ref:
                manquant.append(f"US {cle}, critère {n} : aucune transition observée ne correspond à « {(s['action'] or c)[:80]} ».")
    m["us"] = us
    m["manquant"] = manquant
    m = _fusionner(cm.charger(m["id"]), m)
    return cm.sauver(m, "reconstruction depuis le Knowledge Graph")


def _technique_action(g, a) -> tuple[list[str], list[str]]:
    """Locators de l'élément actionné et keywords qui les utilisent (préparation à l'automatisation)."""
    ecran, cle = a.proprietes.get("ecran", ""), a.proprietes.get("cle", "")
    if not cle:
        return [], []
    locs = sorted(i for i in g.noeuds if i.startswith(f"locator:{ecran}.{cle}@"))
    kws = sorted({r.de for l in locs for r in g.entrants(l) if r.type == "utilise" and g.noeuds[r.de].type == "keyword"})
    return locs, kws


def _transition_proche(m: dict, texte: str) -> str:
    """Transition dont l'action partage le plus de mots significatifs avec le texte (au moins un)."""
    mt, meilleur, score = _mots(texte), "", 0
    for tid, t in m["transitions"].items():
        a = m["actions"].get(t.get("action"), {})
        s = len(mt & _mots(a.get("libelle", "") + " " + m["etats"].get(t["vers"], {}).get("nom", "")))
        if s > score:
            meilleur, score = tid, s
    return meilleur


def _etat_cite(m: dict, texte: str) -> str:
    mt = _mots(texte)
    return next((k for k, s in m["etats"].items() if s.get("type") == "ecran" and _mots(s.get("nom", "")) & mt), "")


def _fusionner(ancien: dict | None, neuf: dict) -> dict:
    """Garde ce que le QA a déclaré, corrigé ou décidé ; rafraîchit ce qui vient des sources."""
    if not ancien:
        return neuf
    for k in ("statut", "cree", "chemins_generes", "historique_validations", "incoherences_signalees", "description"):
        if k in ancien:
            neuf[k] = ancien[k]
    if ancien.get("nom_edite"):
        neuf["nom"], neuf["nom_edite"] = ancien["nom"], True
    for c in cm.COLLECTIONS:
        a, n = ancien.get(c) or {}, neuf[c]
        for k, el in a.items():
            if el.get("provenance") == "déclaré" or el.get("edite"):
                n[k] = {**el, **({"source_disparue": True} if k not in n and el.get("provenance") != "déclaré" else {})}
                continue
            if k in n:
                if el.get("validation") == "rejeté" or el.get("valide_par"):
                    n[k].update({x: el[x] for x in ("validation", "valide_par", "motif_rejet") if x in el})
                n[k]["cree"] = el.get("cree", n[k]["cree"])
                n[k]["confiance"] = cm.confiance(n[k])
            elif el.get("validation") == "rejeté":
                n[k] = el  # gardé pour ne pas être reproposé ; jamais exploité
    return neuf


# =========================================================================== moteur : structure et chemins
def _actifs(m: dict, mode: str) -> tuple[dict, dict]:
    ok = (lambda e: e.get("confiance") == "confirmée") if mode == "verifie" else (lambda e: e.get("validation") != "rejeté")
    etats = {k: e for k, e in m["etats"].items() if ok(e)}
    trans = {}
    for k, t in m["transitions"].items():
        if not (ok(t) and t.get("de") in etats and t.get("vers") in etats):
            continue
        c = m["conditions"].get(t.get("garde") or "")
        if t.get("garde") and (not c or c.get("validation") == "rejeté" or not ok(c)):
            if t.get("issue") == "fausse" or not t.get("garde_deduite"):
                continue  # issue fausse d'une condition écartée (ou non confirmée en mode vérifié) : transition non exploitable
            t = {**t, "garde": "", "issue": ""}  # transition observée : seule la garde proposée est écartée
        trans[k] = t
    return etats, trans


def _structure(m: dict, etats: dict, trans: dict) -> dict:
    succ: dict = {k: [] for k in etats}
    pred: dict = {k: [] for k in etats}
    for tid, t in sorted(trans.items()):
        succ[t["de"]].append(tid)
        pred[t["vers"]].append(tid)
    initiaux = [k for k, e in etats.items() if e.get("initial")] or [k for k in etats if not pred[k]] or sorted(etats)[:1]
    finaux = {k for k, e in etats.items() if e.get("final")} or {k for k in etats if not succ[k]}
    vus, file = set(initiaux), deque(initiaux)
    while file:
        x = file.popleft()
        for tid in succ[x]:
            v = trans[tid]["vers"]
            if v not in vus:
                vus.add(v)
                file.append(v)
    atteint: dict = {}  # pour chaque état, les états qu'il atteint (détection des boucles)
    for s in etats:
        a, f = set(), deque([s])
        while f:
            x = f.popleft()
            for tid in succ[x]:
                v = trans[tid]["vers"]
                if v not in a:
                    a.add(v)
                    f.append(v)
        atteint[s] = a
    boucles = sorted(tid for tid, t in trans.items() if t["de"] in atteint[t["vers"]] or t["de"] == t["vers"])
    return {"succ": succ, "pred": pred, "initiaux": initiaux, "finaux": finaux, "accessibles": vus, "boucles": boucles}


def _plus_court(st: dict, trans: dict, depart: list[str], cible) -> list[str] | None:
    """Plus court chemin (transitions) d'un des états de départ vers un état qui satisfait `cible`."""
    prec, file = {d: None for d in depart}, deque(depart)
    while file:
        x = file.popleft()
        if cible(x):
            chemin = []
            while prec[x] is not None:
                tid = prec[x]
                chemin.append(tid)
                x = trans[tid]["de"]
            return chemin[::-1]
        for tid in st["succ"][x]:
            v = trans[tid]["vers"]
            if v not in prec:
                prec[v] = tid
                file.append(v)
    return None


def _complet(st, trans, prefixe: list[str], depart_etat: str, lim: dict) -> list[str]:
    """Préfixe prolongé jusqu'au plus proche état final, sans dépasser le nombre de transitions par scénario."""
    if depart_etat in st["finaux"]:
        return prefixe
    fin = _plus_court(st, trans, [depart_etat], lambda x: x in st["finaux"]) or []
    return prefixe + fin if len(prefixe) + len(fin) <= lim["transitions_par_scenario"] else prefixe


def _par_strategie(strategie: str, m: dict, etats: dict, trans: dict, st: dict, lim: dict) -> list[tuple[list[str], str]]:
    """Chemins candidats (liste de transitions) et leur justification."""
    out: list[tuple[list[str], str]] = []
    nom_e = lambda k: etats[k].get("nom", k)  # noqa: E731
    nom_t = lambda tid: f"{nom_e(trans[tid]['de'])} → {nom_e(trans[tid]['vers'])}"  # noqa: E731

    def vers_etat(e):
        return _plus_court(st, trans, st["initiaux"], lambda x: x == e)

    def via(seq: list[str]) -> list[str] | None:
        p = vers_etat(trans[seq[0]]["de"])
        if p is None:
            return None
        return _complet(st, trans, p + seq, trans[seq[-1]]["vers"], lim)

    if strategie == "etats":
        couverts = set(st["initiaux"])
        for e in sorted(etats, key=lambda k: -len(vers_etat(k) or [])):
            if e in couverts or e not in st["accessibles"] or len(out) >= lim["chemins"]:
                continue
            p = _complet(st, trans, vers_etat(e) or [], e, lim)
            couverts |= {trans[t]["vers"] for t in p}
            out.append((p, f"Atteint l'état « {nom_e(e)} »."))
    elif strategie in ("transitions", "critiques") or strategie == "conditions":
        cibles = sorted(trans, key=lambda t: (-POIDS_PRIORITE.get(trans[t].get("priorite"), 1), t))
        if strategie == "conditions":
            cibles = [t for t in cibles if trans[t].get("garde")]
        couverts: set = set()
        for tid in cibles:
            if tid in couverts or len(out) >= lim["chemins"] or trans[tid]["de"] not in st["accessibles"]:
                continue
            p = via([tid])
            if p is None:
                continue
            couverts |= set(p)
            if strategie == "conditions":
                c = m["conditions"].get(trans[tid]["garde"], {})
                out.append((p, f"Vérifie l'issue {trans[tid].get('issue') or 'vraie'} de la condition « {c.get('libelle', trans[tid]['garde'])} »."))
            else:
                out.append((p, f"Parcourt la transition « {nom_t(tid)} »."))
        if strategie == "critiques":
            out = sorted(out, key=lambda x: -_score(x[0], trans, st))[: max(1, min(lim["chemins"], 10))]
            out = [(p, f"Chemin prioritaire (score {_score(p, trans, st)}) : " + j) for p, j in out]
    elif strategie == "paires":
        for t1 in sorted(trans):
            for t2 in st["succ"][trans[t1]["vers"]]:
                if len(out) >= lim["chemins"] or trans[t1]["de"] not in st["accessibles"]:
                    break
                if any(_contient(p, [t1, t2]) for p, _ in out):
                    continue
                p = via([t1, t2])
                if p is not None:
                    out.append((p, f"Enchaîne « {nom_t(t1)} » puis « {nom_t(t2)} »."))
    elif strategie == "chemins":
        def dfs(x, chemin, usages):
            if len(out) >= lim["chemins"]:
                return
            if (x in st["finaux"] and chemin) or len(chemin) >= min(lim["profondeur"], lim["transitions_par_scenario"]):
                out.append((list(chemin), "Chemin d'un état initial à un état final." if x in st["finaux"] else "Chemin tronqué à la profondeur maximale."))
                return
            suite = [t for t in st["succ"][x] if usages.get(t, 0) <= lim["passages_boucle"] - (1 if t in st["boucles"] else 0)
                     or (t not in st["boucles"] and usages.get(t, 0) == 0)]
            if not suite and chemin:
                out.append((list(chemin), "Chemin jusqu'à une impasse (état sans sortie)."))
                return
            for t in suite:
                usages[t] = usages.get(t, 0) + 1
                chemin.append(t)
                dfs(trans[t]["vers"], chemin, usages)
                chemin.pop()
                usages[t] -= 1
        for i in st["initiaux"]:
            dfs(i, [], {})
    else:
        raise ValueError(f"Stratégie inconnue : {strategie} ({', '.join(STRATEGIES)})")
    return _reduire(out)


def _score(p: list[str], trans: dict, st: dict) -> int:
    return sum(POIDS_PRIORITE.get(trans[t].get("priorite"), 1) for t in p) + (2 if p and trans[p[-1]]["vers"] in st["finaux"] else 0)


def _contient(grand: list[str], petit: list[str]) -> bool:
    n = len(petit)
    return any(grand[i:i + n] == petit for i in range(len(grand) - n + 1))


def _reduire(chemins: list[tuple[list[str], str]]) -> list[tuple[list[str], str]]:
    """Élimine les doublons et les chemins entièrement contenus dans un autre chemin retenu (redondants)."""
    uniques = list({tuple(p): (p, j) for p, j in chemins if p}.values())
    return [(p, j) for p, j in uniques if not any(q is not p and len(q) > len(p) and _contient(q, p) for q, _ in uniques)]


# =========================================================================== analyse complète
def analyser(mid: str, strategie: str = "transitions", limites: dict | None = None, mode: str = "exploratoire") -> dict:
    """Analyse du modèle : structure (accessibles, inaccessibles, impasses, boucles, transitions jamais couvertes),
    informations manquantes, incohérences, et chemins candidats de la stratégie, chacun justifié. Mis en cache tant que
    le modèle, les scénarios BDD et le graphe n'ont pas changé. mode « verifie » : éléments confirmés seulement."""
    m = cm.exiger(mid)
    lim = {**LIMITES_DEFAUT, **{k: int(v) for k, v in (limites or {}).items() if k in LIMITES_DEFAUT and v}}
    if mode not in ("exploratoire", "verifie"):
        raise ValueError("Mode : exploratoire ou verifie.")
    cle = (mid, m.get("empreinte"), m.get("version"), strategie, json.dumps(lim, sort_keys=True), mode, _empreinte_bdd())
    if cle in _CACHE:
        return json.loads(_CACHE[cle])
    etats, trans = _actifs(m, mode)
    st = _structure(m, etats, trans)
    bruts = _par_strategie(strategie, m, etats, trans, st, lim) if etats else []
    conception = couverture_conception(m)
    chemins = [_decrire(m, etats, trans, st, p, j, strategie, conception) for p, j in bruts]
    gardes = {t.get("garde") for t in trans.values() if t.get("garde")}
    issues = {(t["garde"], t.get("issue") or "vraie") for t in trans.values() if t.get("garde")}
    res = {
        "modele": resume(m), "strategie": strategie, "libelle_strategie": STRATEGIES[strategie][0], "mode": mode, "limites": lim,
        "structure": {"etats": len(etats), "transitions": len(trans), "conditions": len([c for c in m["conditions"].values() if c.get("validation") != "rejeté"]),
                      "initiaux": [_ref(etats, k) for k in st["initiaux"]], "finaux": [_ref(etats, k) for k in sorted(st["finaux"])],
                      "accessibles": len(st["accessibles"]),
                      "inaccessibles": [_ref(etats, k) for k in sorted(set(etats) - st["accessibles"])],
                      "impasses": [_ref(etats, k) for k in sorted(etats) if not st["succ"][k] and k not in st["finaux"]],
                      "boucles": st["boucles"],
                      "transitions_non_couvertes": sorted(set(trans) - set(conception["transitions"])),
                      "conditions_non_rattachees": sorted(k for k, c in m["conditions"].items() if c.get("validation") != "rejeté" and k not in gardes),
                      "issues_non_modelisees": sorted(f"{g} : issue {'fausse' if i == 'vraie' else 'vraie'}" for g, i in issues
                                                      if (g, "fausse" if i == "vraie" else "vraie") not in issues)},
        "chemins": chemins, "manquant": list(m.get("manquant") or []) + _a_confirmer(m), "incoherences": incoherences(m),
    }
    _CACHE[cle] = json.dumps(res, ensure_ascii=False, default=str)
    if len(_CACHE) > 64:
        _CACHE.pop(next(iter(_CACHE)))
    return res


def _ref(etats: dict, k: str) -> dict:
    return {"id": k, "nom": etats[k].get("nom", k), "type": etats[k].get("type", "")}


def _a_confirmer(m: dict) -> list[str]:
    out = []
    for tid, t in m["transitions"].items():
        if t.get("validation") == "rejeté":
            continue
        if t.get("postconditions_a_confirmer"):
            out.append(f"Résultat attendu de la transition {tid} ({m['etats'].get(t['vers'], {}).get('nom', t['vers'])}) : à confirmer.")
    return out


def incoherences(m: dict) -> list[str]:
    out = []
    for tid, t in m["transitions"].items():
        if t.get("validation") == "rejeté":
            continue
        for x in (t.get("de"), t.get("vers")):
            if x not in m["etats"]:
                out.append(f"Transition {tid} : état {x} inconnu.")
            elif m["etats"][x].get("validation") == "rejeté":
                out.append(f"Transition {tid} : relie l'état rejeté {x}.")
        if t.get("garde") and t["garde"] not in m["conditions"]:
            out.append(f"Transition {tid} : condition {t['garde']} inconnue.")
    vus: dict = {}
    for tid, t in m["transitions"].items():
        k = (t.get("de"), t.get("vers"), t.get("action"), t.get("garde"), t.get("issue"))
        if k in vus and t.get("validation") != "rejeté":
            out.append(f"Transitions {vus[k]} et {tid} identiques.")
        vus[k] = tid
    for k, e in m["etats"].items():
        if e.get("source_disparue"):
            out.append(f"État {k} corrigé par le QA mais disparu de sa source (écran retiré ?) : à revoir.")
    out += [x["texte"] for x in m.get("incoherences_signalees") or []]
    return out


def _decrire(m, etats, trans, st, p: list[str], justification: str, strategie: str, conception: dict) -> dict:
    sts = [trans[p[0]]["de"]] + [trans[t]["vers"] for t in p] if p else []
    conds = [{"id": trans[t]["garde"], "libelle": m["conditions"][trans[t]["garde"]].get("libelle", ""), "issue": trans[t].get("issue") or "vraie",
              "confiance": m["conditions"][trans[t]["garde"]].get("confiance")} for t in p if trans[t].get("garde")]
    elements = [etats[s] for s in sts] + [trans[t] for t in p] + [m["conditions"][c["id"]] for c in conds] \
        + [m["actions"][trans[t]["action"]] for t in p if trans[t].get("action") in m["actions"]]
    manquant = []
    for t in p:
        x = trans[t]
        if x.get("confiance") != "confirmée":
            manquant.append(f"Transition {etats[x['de']]['nom']} → {etats[x['vers']]['nom']} : {x.get('confiance')}.")
        if x.get("postconditions_a_confirmer"):
            manquant.append(f"Résultat attendu après « {etats[x['vers']]['nom']} » : à confirmer (exigence ou validation).")
    manquant += [f"Condition « {c['libelle']} » : {c['confiance']}." for c in conds if c["confiance"] != "confirmée"]
    erreur = bool(sts) and etats[sts[-1]].get("type") == "erreur"
    type_ = "negatif" if erreur or any(c["issue"] == "fausse" for c in conds) else "alternatif" if any(trans[t].get("alternative") for t in p) else "principal"
    prio = max((POIDS_PRIORITE.get(trans[t].get("priorite"), 1) for t in p), default=1)
    existants = sorted({s for s, ts in conception["par_scenario"].items() if set(p) <= set(ts)})
    pid = "P-" + _h(*p)
    return {"id": pid, "titre": " → ".join(etats[s]["nom"] for s in sts) + (f" (si « {conds[-1]['libelle'][:60]} » {'non remplie' if conds[-1]['issue'] == 'fausse' else 'remplie'})" if conds else ""),
            "description": [_phrase(m, etats, trans[t]) for t in p], "etats": sts, "transitions": p,
            "actions": [trans[t]["action"] for t in p if trans[t].get("action")], "conditions": conds, "type": type_,
            "priorite": {3: "haute", 1: "normale", 0: "basse"}.get(prio, "normale"), "justification": justification, "strategie": strategie,
            "confirme": all(e.get("confiance") == "confirmée" for e in elements), "manquant": manquant,
            "scenarios_existants": existants, "atteint_final": bool(sts) and sts[-1] in st["finaux"],
            "automatisation": preparation(m, p)}


def _phrase(m, etats, t) -> str:
    a = m["actions"].get(t.get("action"), {}).get("libelle", "")
    g = m["conditions"].get(t.get("garde"), {}).get("libelle", "")
    cond = f" si « {g} » {'n’est pas remplie' if t.get('issue') == 'fausse' else 'est remplie'}" if g else ""
    return f"Depuis « {etats[t['de']]['nom']} »{f', « {a} »' if a else ''}{cond} mène à « {etats[t['vers']]['nom']} »."


def resume(m: dict) -> dict:
    return {"id": m["id"], "nom": m.get("nom"), "perimetre": m.get("perimetre"), "version": m.get("version"), "statut": m.get("statut"),
            "statut_libelle": cm.LIBELLES_STATUT.get(m.get("statut"), m.get("statut")), "maj": m.get("maj"),
            "version_application": m.get("version_application", ""),
            **{f"nb_{c}": sum(1 for e in m[c].values() if e.get("validation") != "rejeté") for c in cm.COLLECTIONS},
            "a_valider": sum(1 for c in cm.COLLECTIONS for e in m[c].values() if e.get("validation") == "à valider")}


# =========================================================================== couverture comportementale (lot 6)
def _empreinte_bdd() -> str:
    import os

    try:
        from atelier.generation import bdd

        d = bdd._dossier()
        st = [(f.name, f.stat().st_size, f.stat().st_mtime_ns) for f in sorted(d.glob("*.yaml"))] if d.exists() else []
    except Exception:  # noqa: BLE001
        st = []
    try:
        from atelier.domain import projet

        r = projet.PROJECT_DIR / "results"
        st.append(max((os.stat(os.path.join(a, f)).st_mtime_ns for a, _, fs in os.walk(r) for f in fs if f == "output.xml"), default=0) if r.exists() else 0)
    except OSError:
        pass
    return _h(*st)


def _scenarios() -> list[dict]:
    from atelier.generation import bdd

    out = []
    for b in bdd.lister():
        try:
            m = bdd.charger(b["cle"]) or {}
        except Exception:  # noqa: BLE001
            continue
        out.append(m)
    return out


def couverture_conception(m: dict, scenarios: list[dict] | None = None) -> dict:
    """Transitions et états vérifiés par un scénario BDD : traçabilité MBT explicite (scénario généré depuis ce
    modèle), sinon enchaînement des écrans des étapes (écran A puis écran B = transition A → B, action reconnue si
    possible). Les conditions et les états d'erreur ne sont couverts que par la traçabilité explicite."""
    scenarios = _scenarios() if scenarios is None else scenarios
    par_ecran: dict = {}
    for k, e in m["etats"].items():
        if e.get("ecran") and e.get("type") == "ecran":
            par_ecran.setdefault(e["ecran"].split(":", 1)[-1], k)
    par_paire: dict = {}
    for tid, t in m["transitions"].items():
        if t.get("validation") != "rejeté" and not t.get("garde"):
            par_paire.setdefault((t["de"], t["vers"]), []).append(tid)
    par_scenario, etats_couverts = {}, set()
    for s in scenarios:
        cle = s.get("cle", "")
        x = s.get("mbt") or {}
        if x.get("model_id") == m["id"]:
            ts = [t for t in x.get("transition_ids") or [] if t in m["transitions"]]
            par_scenario[cle] = ts
            etats_couverts |= set(x.get("state_ids") or [])
            continue
        etapes = [e for sc in s.get("scenarios", []) for e in sc.get("etapes", [])]
        seq = [par_ecran[e["ecran"]] for e in etapes if e.get("ecran") in par_ecran]
        seq = [v for i, v in enumerate(seq) if i == 0 or v != seq[i - 1]]
        etats_couverts |= set(seq)
        ts = []
        for a, b in zip(seq, seq[1:]):
            cands = par_paire.get((a, b), [])
            texte = " ".join(e.get("texte", "") for e in etapes)
            meilleur = [t for t in cands if _mots(m["actions"].get(m["transitions"][t].get("action"), {}).get("libelle", "")) & _mots(texte)]
            ts += meilleur or cands[:1]
        if ts:
            par_scenario[cle] = ts
    transitions = sorted({t for ts in par_scenario.values() for t in ts})
    return {"transitions": transitions, "etats": sorted(etats_couverts & set(m["etats"])), "par_scenario": par_scenario}


def couverture(mid: str) -> dict:
    """Cinq niveaux, jamais confondus (cahier § 14) : modèle (éléments modélisés, confirmés), conception (vérifiés par un
    scénario BDD), automatisation (scénario relié à un test Robot), exécution (test Robot exécuté), validée (dernière
    exécution réussie, éléments confirmés). Générer un scénario n'est jamais une preuve d'exécution."""
    from atelier.discovery import connaissance

    m = cm.exiger(mid)
    g = connaissance.construire()
    etats = {k: e for k, e in m["etats"].items() if e.get("validation") != "rejeté"}
    trans = {k: t for k, t in m["transitions"].items() if t.get("validation") != "rejeté" and t.get("de") in etats and t.get("vers") in etats}
    conc = couverture_conception(m)
    auto, execu, valide = set(), set(), set()
    for cle, ts in conc["par_scenario"].items():
        sid = f"scenario:{cle}"
        robots = [r.vers for r in g.sortants(sid) if r.type == "implemente_par" and r.confirmee] if sid in g.noeuds else []
        if not robots:
            continue
        auto |= set(ts)
        statuts = [g.noeuds[r].proprietes.get("dernier_statut") for r in robots if r in g.noeuds]
        if any(statuts):
            execu |= set(ts)
        if any(s == "PASS" for s in statuts):
            valide |= {t for t in ts if trans.get(t, {}).get("confiance") == "confirmée"}
    gardes = {}
    for tid, t in trans.items():
        if t.get("garde"):
            gardes.setdefault(t["garde"], set()).add((t.get("issue") or "vraie", tid))
    cond_verif = {c for c, iss in gardes.items() if {i for i, tid in iss if tid in conc["transitions"]} >= {"vraie", "fausse"}}

    def bloc(ensemble: set) -> dict:
        n = len(set(trans) & ensemble)
        return {"transitions": n, "taux": round(n / len(trans), 3) if trans else None}
    return {
        "modele": {"etats": len(etats), "transitions": len(trans), "etats_confirmes": sum(e.get("confiance") == "confirmée" for e in etats.values()),
                   "transitions_confirmees": sum(t.get("confiance") == "confirmée" for t in trans.values()),
                   "conditions": sum(1 for c in m["conditions"].values() if c.get("validation") != "rejeté")},
        "conception": {**bloc(set(conc["transitions"])), "etats": len(set(conc["etats"]) & set(etats)), "scenarios": len(conc["par_scenario"])},
        "automatisation": bloc(auto), "execution": bloc(execu), "validee": bloc(valide),
        "transitions_non_couvertes": [{"id": t, "libelle": f"{etats[trans[t]['de']]['nom']} → {etats[trans[t]['vers']]['nom']}"}
                                      for t in sorted(set(trans) - set(conc["transitions"]))],
        "conditions_non_verifiees": sorted(set(gardes) - cond_verif),
        "definitions": {"conception": "vérifié par un scénario BDD (traçabilité MBT, ou enchaînement des écrans de ses étapes)",
                        "automatisation": "scénario relié à un test Robot (identifiant en tag, lien confirmé)",
                        "execution": "test Robot exécuté (output.xml)", "validee": "dernière exécution réussie, élément confirmé",
                        "remarque": "générer un scénario n'est jamais une preuve d'exécution"},
    }


def couverture_globale() -> dict:
    """Indicateurs comportementaux de tous les modèles (écran Couverture)."""
    modeles = cm.lister()
    total = {"modeles": len(modeles), "parcours_identifies": 0, "parcours_couverts": 0, "transitions": 0, "transitions_couvertes": 0,
             "transitions_non_couvertes": 0, "conditions_non_verifiees": 0, "scenarios_manquants": 0}
    details = []
    for x in modeles:
        try:
            c = couverture(x["id"])
            a = analyser(x["id"], "chemins", {"chemins": 30})
        except Exception:  # noqa: BLE001 — un modèle illisible n'empêche pas les autres
            continue
        identifies = [p for p in a["chemins"] if p["atteint_final"]]
        couverts = sum(1 for p in identifies if p["scenarios_existants"])
        manquants = len(analyser(x["id"], "transitions")["chemins"]) if c["transitions_non_couvertes"] else 0
        total["parcours_identifies"] += len(identifies)
        total["parcours_couverts"] += couverts
        total["transitions"] += c["modele"]["transitions"]
        total["transitions_couvertes"] += c["conception"]["transitions"]
        total["transitions_non_couvertes"] += len(c["transitions_non_couvertes"])
        total["conditions_non_verifiees"] += len(c["conditions_non_verifiees"])
        total["scenarios_manquants"] += sum(1 for p in analyser(x["id"], "transitions")["chemins"] if not p["scenarios_existants"]) if manquants else 0
        details.append({"id": x["id"], "nom": x["nom"], "transitions": c["modele"]["transitions"], "conception": c["conception"]["transitions"],
                        "automatisation": c["automatisation"]["transitions"], "execution": c["execution"]["transitions"],
                        "validee": c["validee"]["transitions"]})
    return {**total, "modeles_detail": details}


# =========================================================================== impact entre versions (lot 6)
def impact(mid: str, de: int | str, vers: int | str = "courante") -> dict:
    """Ce qu'une évolution du modèle touche : éléments changés, scénarios BDD impactés (directement par leur
    traçabilité, potentiellement par leurs écrans), couverture avant / après, actions proposées. Rien n'est supprimé."""
    diff = cm.comparer(mid, de, vers)
    va, vb = cm.version(mid, de), cm.version(mid, vers)
    touches = {c: set(diff[c]["ajoutes"]) | set(diff[c]["retires"]) | {x["id"] for x in diff[c]["modifies"]} for c in cm.COLLECTIONS}
    for c in ("actions", "conditions"):  # une action ou une condition changée touche les transitions qui l'utilisent
        cle = "action" if c == "actions" else "garde"
        for v in (va, vb):
            touches["transitions"] |= {k for k, t in (v.get("transitions") or {}).items() if t.get(cle) in touches[c]}
    ecrans = {e.get("ecran", "").split(":", 1)[-1] for v in (va, vb) for k, e in (v.get("etats") or {}).items() if k in touches["etats"]}
    ecrans |= {(v.get("etats") or {}).get(t.get("de"), {}).get("ecran", "").split(":", 1)[-1]
               for v in (va, vb) for k, t in (v.get("transitions") or {}).items() if k in touches["transitions"]}
    ecrans.discard("")
    directs, potentiels = [], []
    for s in _scenarios():
        x = s.get("mbt") or {}
        if x.get("model_id") == mid and (set(x.get("transition_ids") or []) & touches["transitions"] or set(x.get("state_ids") or []) & touches["etats"]):
            directs.append({"cle": s["cle"], "titre": s.get("titre", ""), "raison": "généré depuis un chemin qui passe par un élément changé"})
        elif {e.get("ecran") for sc in s.get("scenarios", []) for e in sc.get("etapes", [])} & ecrans:
            potentiels.append({"cle": s["cle"], "titre": s.get("titre", ""), "raison": "passe par un écran concerné"})
    avant, apres = couverture_conception({**va, **{k: va.get(k) or {} for k in cm.COLLECTIONS}}), couverture_conception({**vb, **{k: vb.get(k) or {} for k in cm.COLLECTIONS}})
    nouvelles = sorted(t for t in diff["transitions"]["ajoutes"] if t not in apres["transitions"])
    actions = [f"Relire {len(directs)} scénario(s) généré(s) depuis les éléments changés (aucun n'est supprimé)."] if directs else []
    if nouvelles:
        actions.append(f"Générer les scénarios des {len(nouvelles)} nouvelle(s) transition(s) (stratégie « transitions »).")
    if diff["transitions"]["retires"]:
        actions.append(f"{len(diff['transitions']['retires'])} transition(s) retirée(s) : vérifier que les scénarios qui les parcourent restent valides.")
    return {"difference": diff, "scenarios_impactes": directs, "scenarios_potentiels": potentiels,
            "couverture_avant": {"transitions": len(avant["transitions"]), "total": len(va.get("transitions") or {})},
            "couverture_apres": {"transitions": len(apres["transitions"]), "total": len(vb.get("transitions") or {})},
            "transitions_nouvelles_non_couvertes": nouvelles, "actions_proposees": actions,
            "tags_tnr": sorted({d["cle"] for d in directs})}


def impact_element(g, noeud: str) -> dict:
    """Pour l'analyse d'impact du graphe : modèles, transitions et scénarios générés concernés par un élément changé
    (écran, action, locator, keyword)."""
    N = g.noeuds
    if noeud not in N:
        return {"modeles": [], "transitions": 0, "scenarios": []}
    n = N[noeud]
    ecran = noeud if n.type == "ecran" else ""
    if n.type in ("locator", "action"):
        ecran = "ecran:" + (n.proprietes.get("ecran") or noeud.split(":", 1)[1].split(".", 1)[0].split("@", 1)[0])
    out, scen = [], set()
    for x in cm.lister():
        m = cm.charger(x["id"]) or {}
        etats = {k for k, e in (m.get("etats") or {}).items() if e.get("ecran") == ecran or e.get("ecran") == noeud}
        ts = {k for k, t in (m.get("transitions") or {}).items() if t.get("de") in etats or t.get("vers") in etats
              or noeud in (m.get("actions") or {}).get(t.get("action"), {}).get("locators", [])
              or noeud in (m.get("actions") or {}).get(t.get("action"), {}).get("keywords", [])}
        if not ts and not etats:
            continue
        derives = [v.get("scenario") for v in (m.get("chemins_generes") or {}).values() if set(v.get("transitions") or []) & ts]
        scen |= {s for s in derives if s}
        out.append({"id": x["id"], "nom": x["nom"], "etats": len(etats), "transitions": len(ts)})
    return {"modeles": out, "transitions": sum(x["transitions"] for x in out), "scenarios": sorted(scen)}


# =========================================================================== automatisation (lot 7)
def preparation(m: dict, chemin: list[str]) -> dict:
    """Préparation à l'automatisation d'un chemin : pour chaque action, locator, keyword et données connus. Jamais
    « prêt » tant qu'un élément manque : ce qui manque est listé (à découvrir ou à compléter)."""
    etapes, manque = [], []
    for tid in chemin:
        t = m["transitions"].get(tid, {})
        a = m["actions"].get(t.get("action"), {})
        if not a:
            manque.append(f"Transition {tid} : action inconnue (à découvrir).")
            etapes.append({"transition": tid, "action": "", "locators": [], "keywords": [], "statut": "à découvrir"})
            continue
        locs, kws = a.get("locators") or [], a.get("keywords") or []
        statut = "prêt" if locs and kws else "locator seul" if locs else "à découvrir"
        if not locs:
            manque.append(f"« {a.get('libelle')} » : aucun locator connu (Discovery de l'écran à refaire, ou locator à déclarer).")
        elif not kws:
            manque.append(f"« {a.get('libelle')} » : aucun keyword Robot n'utilise ce locator (à créer dans Automation Studio).")
        etapes.append({"transition": tid, "action": a.get("libelle", ""), "locators": locs, "keywords": kws, "statut": statut})
    pret = bool(etapes) and all(e["statut"] == "prêt" for e in etapes)
    return {"statut": "prêt" if pret else "partiel" if any(e["locators"] for e in etapes) else "à découvrir", "etapes": etapes, "manquant": manque,
            "cibles": {"robot": True, "playwright": False, "cypress": False}}


# =========================================================================== mode automatique : cas pour une US
def cas_pour_us(cle: str, g=None) -> dict:
    """Mode automatique (génération des cas d'une US) : modèle de l'US construit ou actualisé en arrière-plan, chemins
    des transitions et des conditions, convertis en cas proposés (même forme que les cas par catégorie). Les
    scénarios BDD qui couvrent déjà un chemin sont renvoyés comme réutilisables, pas reproposés."""
    g = _graphe(g)
    if f"user_story:{cle}" not in g.noeuds:
        return {"cas": [], "reutilisables": [], "manquant": [f"US {cle} absente du Knowledge Graph : pas d'analyse comportementale."], "modele": None}
    m = construire("user_story", cle, g)
    chemins, vus = [], set()
    for s in ("conditions", "transitions"):
        for p in analyser(m["id"], s)["chemins"]:
            if p["id"] not in vus:
                vus.add(p["id"])
                chemins.append(p)
    cas, reutilisables = [], []
    for p in chemins:
        if p["scenarios_existants"]:
            reutilisables.append({"chemin": p["id"], "titre": p["titre"], "scenarios": p["scenarios_existants"]})
            continue
        etapes = [{"action": phrase, "donnees": "", "resultat": ""} for phrase in p["description"]]
        if etapes:
            dernier = m["etats"][p["etats"][-1]]
            etapes[-1]["resultat"] = (m["transitions"][p["transitions"][-1]].get("postconditions") or f"« {dernier['nom']} » est atteint") + \
                (" (à confirmer)" if m["transitions"][p["transitions"][-1]].get("postconditions_a_confirmer") else "")
        cat = {"negatif": "negatif", "alternatif": "alternatif"}.get(p["type"], "navigation")
        from atelier.generation import bdd, mbt_bdd

        lignes, prec = [], ""
        for e in mbt_bdd.modele_bdd(p, m, "US_MBT")["scenarios"][0]["etapes"]:
            t = e["type"] if e["type"] in ("given", "when", "then") else prec or "given"
            lignes.append(("And" if t == prec else bdd.MOTS_EN[t]) + " " + e["texte"])
            prec = t
        cas.append({"categorie": cat, "titre": f"{p['titre']}"[:250], "etapes": etapes, "gherkin": "\n".join(lignes),
                    "source_detail": f"analyse comportementale : modèle {m['id']} v{m['version']}, chemin {p['id']}",
                    "justification": p["justification"], "confiance": 0.8 if p["confirme"] else 0.5,
                    "provenance": "observé" if p["confirme"] else "déduit", "manquant": p["manquant"],
                    "mbt": {"model_id": m["id"], "model_version": m["version"], "source_path_id": p["id"], "transition_ids": p["transitions"],
                            "state_ids": p["etats"], "coverage_strategy": p["strategie"], "generation_origin": "US_MBT"}})
    return {"cas": cas, "reutilisables": reutilisables, "manquant": list(m.get("manquant") or []), "modele": resume(m)}


# =========================================================================== IA : propositions à valider
SYSTEME_IA = """Tu enrichis un modèle comportemental de test (états, transitions, conditions) d'une application.
Règles : ne JAMAIS inventer un message d'erreur exact ni une règle métier absente des textes fournis ; propose seulement
des états manquants, des transitions possibles, des conditions alternatives (issue vraie / fausse) et des incohérences,
chacun avec une justification qui cite le texte source. Réponds uniquement en JSON :
{"etats": [{"nom": "", "type": "metier|erreur|systeme", "justification": ""}],
 "transitions": [{"de": "<nom ou id d'état>", "vers": "<nom ou id d'état>", "action": "", "garde": "<libellé de condition>", "issue": "vraie|fausse", "justification": ""}],
 "conditions": [{"libelle": "", "justification": ""}], "incoherences": [""]}"""


def lecture_pour_ia(mid: str) -> dict:
    """Ce que l'IA (ou Cursor par le MCP) lit : le modèle résumé, les critères des US, les informations manquantes."""
    m = cm.exiger(mid)
    from atelier.discovery import connaissance

    g = connaissance.construire()
    return {"modele": mid, "version": m["version"], "perimetre": m["perimetre"],
            "etats": [{"id": k, "nom": e.get("nom"), "type": e.get("type"), "confiance": e.get("confiance")} for k, e in m["etats"].items()
                      if e.get("validation") != "rejeté"],
            "transitions": [{"id": k, "de": t["de"], "vers": t["vers"], "action": m["actions"].get(t.get("action"), {}).get("libelle", ""),
                             "garde": m["conditions"].get(t.get("garde"), {}).get("libelle", ""), "issue": t.get("issue", "")}
                            for k, t in m["transitions"].items() if t.get("validation") != "rejeté"],
            "conditions": [{"id": k, "libelle": c.get("libelle")} for k, c in m["conditions"].items() if c.get("validation") != "rejeté"],
            "criteres": {u: _criteres_us(g, u) for u in m.get("us") or [] if u in g.noeuds},
            "manquant": m.get("manquant") or [], "rejetes": [e.get("nom") or e.get("libelle") for c in cm.COLLECTIONS for e in m[c].values()
                                                           if e.get("validation") == "rejeté"]}


def proposer_ia(mid: str) -> dict:
    """Propositions d'IA déposées « déduit / à valider » (jamais validées automatiquement). Avec Cursor : l'agent lit
    par mbt_modele et dépose par mbt_deposer_propositions. Coût journalisé par l'orchestrateur (opération conception.mbt)."""
    from atelier.intelligence import fournisseur_ia

    f = fournisseur_ia.fournisseur()
    if f == "cursor":
        return {"disponible": False, "cursor": True,
                "raison": "IA réglée sur Cursor : demander à Cursor « enrichis le modèle " + mid + " » (outils mbt_modele puis mbt_deposer_propositions)."}
    if not fournisseur_ia.configure() or fournisseur_ia.applicatif("conception.mbt"):
        return {"disponible": False, "raison": "Aucune IA configurée pour l'analyse comportementale : le modèle reste construit par règles."}
    texte = fournisseur_ia.completer(SYSTEME_IA, json.dumps(lecture_pour_ia(mid), ensure_ascii=False)[:12000], 1500)
    props = fournisseur_ia.extraire_json(texte) or {}
    if not isinstance(props, dict):
        return {"disponible": True, "ajoutes": [], "raison": "Réponse de l'IA illisible : rien n'a été ajouté."}
    r = cm.deposer_propositions(mid, props, source=f"IA ({f})")
    return {"disponible": True, "ajoutes": r["ajoutes"], "ignores": r["ignores"], "modele": resume(r["modele"])}


def vider_cache():
    _CACHE.clear()
