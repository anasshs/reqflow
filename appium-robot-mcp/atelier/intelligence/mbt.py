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
    "critiques": ("Chemins critiques (orientée risque)", "Les chemins au plus fort risque métier : opérations sensibles, engagements, refus, priorités."),
}
LIMITES_DEFAUT = {"profondeur": 12, "chemins": 40, "transitions_par_scenario": 10, "passages_boucle": 1}
POIDS_PRIORITE = {"haute": 3, "normale": 1, "basse": 0}
NEGATIF = re.compile(r"(?i)\b(refus|rejet|interdit|invalide|erron|erreur|impossible|bloqu|insuffisant|dépass|depass|ne\s+\w+\s+pas|n'est pas|incorrect|échec|echec|manquant)")
MOTS_VIDES = {"le", "la", "les", "de", "des", "du", "un", "une", "et", "ou", "je", "il", "elle", "sur", "dans", "pour", "par", "avec", "que",
              "qui", "est", "sont", "son", "sa", "ses", "au", "aux", "en", "à", "l", "d", "on", "se", "si", "lorsque", "quand", "alors", "doit"}
_CACHE: dict = {}
_ACTUALISATION: dict = {}  # dernière actualisation des modèles (empreinte du projet, évolutions)


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
    transitions et conditions observées), les règles métier et les critères d'acceptation (exigences explicites : niveau
    « Confirmé »), puis propose comme HYPOTHÈSES les comportements non documentés (issue contraire d'une condition,
    session expirée, perte de connexion, double soumission, retour arrière, annulation, interruption et reprise, accès non
    autorisé, formulaire invalide). Les déclarations, corrections et décisions du QA sont conservées ; une hypothèse
    rejetée n'est jamais reproposée ; une nouvelle version n'est créée que si le comportement change."""
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
                    garde = cm.condition_commune(m, lib) or "C-" + cm.slug(lib, 50)
                    m["conditions"].setdefault(garde, cm.element("observé", "carte (condition observée pendant la Discovery)", libelle=lib, regle=""))
                tid = "T-" + _h(e, r2.vers, a.id)
                ok = r.statut == "validé" and r2.statut == "validé"
                m["transitions"][tid] = cm.element(
                    "observé", f"carte ({r2.source or 'Discovery'})", "validé" if ok else "à valider", de=_sid(e), vers=_sid(r2.vers), action=aid,
                    evenement=f"{GENRES.get(a.proprietes.get('genre', ''), 'action')} sur « {a.libelle} »", garde=garde, issue="vraie" if garde else "",
                    preconditions="", postconditions=f"l'écran {N[r2.vers].libelle} est affiché", priorite="normale",
                    alternative=bool(r2.proprietes.get("alternative")), fiabilite=r2.proprietes.get("fiabilite"))
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
    # ------------------------------------------------------------- règles métier : conditions explicites (à rattacher)
    us = _us_perimetre(g, type_, nid)
    textes = []
    for r in list(g.sortants(nid)) + [x for u in us for x in g.sortants(u)]:
        if r.type in ("contient", "possede") and N[r.vers].type == "regle":
            rg = N[r.vers]
            textes.append(f"{rg.libelle} {rg.proprietes.get('description', '')}")
            cid = cm.condition_commune(m, rg.libelle) or "C-R-" + cm.slug(rg.id.split(":", 1)[1], 50)
            m["conditions"].setdefault(cid, cm.element(rg.provenance if rg.provenance != "déduit" else "déduit", f"règle métier {rg.id}",
                                                       "validé" if rg.statut == "validé" else "à valider", justification=rg.proprietes.get("description", ""),
                                                       libelle=rg.libelle, regle=rg.id, exigence=rg.statut == "validé"))
    # ------------------------------------------------------------- critères d'acceptation (exigences explicites)
    initial = next((k for k, s in m["etats"].items() if s.get("initial")), "")
    champs = {}  # racines des champs SAISIS de chaque écran : un critère qui cite un champ s'applique à l'écran qui le saisit
    for k, e in m["etats"].items():
        if e.get("ecran") in N:
            champs[k] = set().union(*[_racines(N[r.vers].libelle) for r in g.sortants(e["ecran"]) if r.type == "contient"
                                      and N[r.vers].type == "composant" and N[r.vers].proprietes.get("type") in ("champ", "input", "")] or [set()])
    profondeur = _profondeurs(m)
    for u in us:
        cle = u.split(":", 1)[1]
        for n, c in enumerate(_criteres_us(g, u), 1):
            textes.append(c)
            s = structurer(c)
            source = f"US {cle}, critère {n}"
            cid = ""
            if s["condition"]:
                cid = cm.condition_commune(m, s["condition"]) or f"C-US-{cm.slug(cle, 30)}-{n}"
                cond = m["conditions"].setdefault(cid, cm.element("observé", source, "validé", justification=c, libelle=s["condition"][:200], regle="",
                                                                  exigence=True, us=u))
                cond.setdefault("exigences", [])
                if u not in cond["exigences"]:
                    cond["exigences"].append(u)
            tid_ref = _transition_proche(m, c, champs, s["condition"], profondeur)
            src = m["transitions"][tid_ref]["de"] if tid_ref else _etat_cite(m, c) or initial
            if not src:
                manquant.append(f"{source} : aucun état où l'appliquer (écrans à découvrir ou à relier).")
                continue
            if NEGATIF.search(c):
                eid = f"E-ERR-{cm.slug(cle, 30)}-{n}"
                res = _consequence(c, s)  # ce que le critère dit du refus (jamais inventé)
                m["etats"][eid] = cm.element("déduit", source, justification=c, nom=f"Refus : {res or 'résultat à confirmer'}"[:120], type="erreur",
                                             ecran=m["etats"][src].get("ecran", ""), description=c, contexte="", initial=False, final=True, us=u,
                                             calcul=True, a_confirmer=not res)
                m["transitions"]["T-" + _h(src, eid, cid or c)] = cm.element(
                    "déduit", source, justification=c, de=src, vers=eid, action=m["transitions"][tid_ref]["action"] if tid_ref else "",
                    evenement=m["transitions"][tid_ref].get("evenement", "") if tid_ref else "", garde=cid, issue="vraie" if cid else "",
                    preconditions="", postconditions=res, postconditions_a_confirmer=not res, priorite="haute", us=u, exigences=[u], calcul=True)
                if cid and tid_ref and not m["transitions"][tid_ref].get("garde"):  # le chemin nominal : la condition de refus n'est pas remplie
                    m["transitions"][tid_ref].update(garde=cid, issue="fausse", garde_deduite=True)
                elif cid and tid_ref and m["transitions"][tid_ref].get("issue") == "vraie":
                    # le nominal porte déjà la condition positive d'un autre critère : les deux conditions sont contraires
                    g1 = m["transitions"][tid_ref]["garde"]
                    m["conditions"][cid]["contraire"] = g1
                    m["conditions"][g1]["contraire"] = cid
                if not res:
                    manquant.append(f"{source} : résultat attendu du refus non précisé (message, état) : à confirmer.")
            elif tid_ref:
                t = m["transitions"][tid_ref]
                t.setdefault("exigences", [])
                if u not in t["exigences"]:
                    t["exigences"].append(u)
                attendu = _consequence(c, s)  # « le tableau de bord s'affiche » : la conséquence écrite dans le critère
                if attendu:
                    t["attendu_exigence"] = attendu
                if cid and not t.get("garde"):
                    t.update(garde=cid, issue="vraie", garde_deduite=True)
            else:
                manquant.append(f"{source} : aucune transition observée ne correspond à « {(s['action'] or c)[:80]} ».")
    m["us"] = us
    m["manquant"] = manquant
    m["hypotheses"] = _hypotheses(m, g, textes)
    m = _fusionner(cm.charger(m["id"]), m)
    _pre_post(m, _apres_authentification(m))  # préconditions et postconditions structurées, sourcées
    return cm.sauver(m, "reconstruction depuis le Knowledge Graph")


def _technique_action(g, a) -> tuple[list[str], list[str]]:
    """Locators de l'élément actionné et keywords qui les utilisent (préparation à l'automatisation)."""
    ecran, cle = a.proprietes.get("ecran", ""), a.proprietes.get("cle", "")
    if not cle:
        return [], []
    locs = sorted(i for i in g.noeuds if i.startswith(f"locator:{ecran}.{cle}@"))
    kws = sorted({r.de for l in locs for r in g.entrants(l) if r.type == "utilise" and g.noeuds[r.de].type == "keyword"})
    return locs, kws


def _racines(t: str) -> set:
    """Mots significatifs réduits à leur racine (5 lettres) : « confirme » et « confirmer », « ajout » et « ajouter »."""
    return {w[:5] for w in _mots(t)}


def _profondeurs(m: dict) -> dict:
    succ: dict = {}
    for t in m["transitions"].values():
        succ.setdefault(t["de"], []).append(t["vers"])
    prof = {k: 0 for k, e in m["etats"].items() if e.get("initial")}
    file = list(prof)
    while file:
        x = file.pop(0)
        for y in succ.get(x, []):
            if y not in prof:
                prof[y] = prof[x] + 1
                file.append(y)
    return prof


def _consequence(critere: str, s: dict) -> str:
    """Conséquence écrite dans le critère (« l'ajout du bénéficiaire est refusé »), sans la condition ; vide si le
    critère ne dit rien du résultat (il restera « à confirmer »)."""
    reste = re.sub(r"(?i)^\s*(si|quand|lorsque|lorsqu'|en cas d[e'])\s*[^,]+,\s*", "", critere).strip(" .")
    if reste and reste != critere.strip(" .") and len(reste) > 6:
        return reste[0].lower() + reste[1:]
    return s.get("resultat") or ""


def _transition_proche(m: dict, texte: str, champs: dict | None = None, condition: str = "", profondeur: dict | None = None) -> str:
    """Transition observée à laquelle s'applique un critère. D'abord la condition : si elle cite un champ SAISI sur un
    écran (« l'IBAN », « le montant »), le critère s'applique à la soumission de cet écran. Sinon, les mots du critère
    et de l'action (« confirme un virement » → « Confirmer le virement »). À égalité, la plus avancée dans le parcours
    (un refus survient au moment de l'engagement, pas en ouvrant l'écran)."""
    obs = {tid: t for tid, t in m["transitions"].items() if t.get("provenance") == "observé"}
    champs, prof = champs or {}, profondeur or {}
    # rareté de chaque racine (un mot présent partout, comme « bénéficiaire » dans une appli de virement, départage peu)
    docs = [_racines(m["actions"].get(t.get("action"), {}).get("libelle", "")) for t in obs.values()] + list(champs.values()) \
        + [_racines(e.get("nom", "")) for e in m["etats"].values()]
    df = lambda w: max(1, sum(1 for d in docs if w in d))  # noqa: E731
    rc, rt = _racines(condition or texte), _racines(texte)
    meilleur, cle_max = "", None
    for tid in sorted(obs):
        t = obs[tid]
        a = m["actions"].get(t.get("action"), {})
        score = sum(3 / df(w) for w in rc & champs.get(t["de"], set())) + sum(1 / df(w) for w in rt & _racines(a.get("libelle", "")))
        if score <= 0:
            continue
        cle = (round(score, 3), prof.get(t["de"], 0))
        if cle_max is None or cle > cle_max:
            meilleur, cle_max = tid, cle
    return meilleur


def _etat_cite(m: dict, texte: str) -> str:
    mt = _mots(texte)
    return next((k for k, s in m["etats"].items() if s.get("type") == "ecran" and _mots(s.get("nom", "")) & mt), "")


def _fusionner(ancien: dict | None, neuf: dict) -> dict:
    """Garde ce que le QA a déclaré, corrigé ou décidé (hypothèses comprises) ; rafraîchit ce qui vient des sources."""
    if not ancien:
        return neuf
    for k in ("statut", "cree", "chemins_generes", "historique_validations", "incoherences_signalees", "description", "revisions_proposees"):
        if k in ancien:
            neuf[k] = ancien[k]
    if ancien.get("nom_edite"):
        neuf["nom"], neuf["nom_edite"] = ancien["nom"], True
    for c in cm.COLLECTIONS:
        a, n = ancien.get(c) or {}, neuf[c]
        for k, el in a.items():
            if el.get("provenance") == "déclaré" or el.get("edite") or el.get("hypothese") or (k not in n and el.get("provenance") == "déduit"
                                                                                          and (el.get("valide_par") or el.get("auteur") == "ia")):
                # déclaré, corrigé, hypothèse acceptée, proposition d'IA en attente de décision ou validée par le QA :
                # une décision (ou une question posée au QA) ne se perd pas à la reconstruction
                n[k] = {**el, **({"source_disparue": True} if k not in n and el.get("provenance") == "observé" else {})}
                continue
            if k in n:
                if el.get("validation") == "rejeté" or el.get("valide_par"):
                    n[k].update({x: el[x] for x in ("validation", "valide_par", "motif_rejet") if x in el})
                n[k]["cree"] = el.get("cree", n[k]["cree"])
            elif el.get("validation") == "rejeté":
                n[k] = el  # gardé pour ne pas être reproposé ; jamais exploité
    for k, h in (ancien.get("hypotheses") or {}).items():
        if h.get("statut") in ("acceptée", "rejetée"):
            neuf["hypotheses"][k] = h  # une décision du QA ne se perd pas ; une hypothèse rejetée n'est jamais reproposée
    return neuf


# =========================================================================== moteur : structure et chemins
def _actifs(m: dict, mode: str) -> tuple[dict, dict]:
    """mode « verifie » : éléments ÉTABLIS seulement (Confirmé, Observé) ; « exploratoire » : tout sauf le rejeté."""
    ok = cm.etabli if mode == "verifie" else (lambda e: e.get("validation") != "rejeté")
    etats = {k: e for k, e in m["etats"].items() if ok(e)}
    trans = {}
    for k, t in m["transitions"].items():
        if not (ok(t) and t.get("de") in etats and t.get("vers") in etats):
            continue
        c = m["conditions"].get(t.get("garde") or "")
        if t.get("garde") and (not c or c.get("validation") == "rejeté" or not ok(c)):
            if not t.get("garde_deduite"):
                continue  # transition qui n'existe que par une condition écartée (ou non établie en mode vérifié)
            t = {**t, "garde": "", "issue": ""}  # transition observée : seule la garde rattachée par calcul est écartée
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


def _par_strategie(strategie: str, m: dict, etats: dict, trans: dict, st: dict, lim: dict, deja: dict | None = None) -> list:
    """Chemins candidats (transitions), leur justification et leur APPORT (ce qu'ils couvrent de nouveau), minimisés.
    `deja` : ce que les scénarios existants couvrent déjà (exclu des cibles : on ne regénère pas l'existant)."""
    deja = deja or {"transitions": set(), "etats": set(), "issues": set(), "paires": set(), "sequences": []}
    nom_e = lambda k: etats[k].get("nom", k)  # noqa: E731
    nom_t = lambda tid: f"{nom_e(trans[tid]['de'])} → {nom_e(trans[tid]['vers'])}"  # noqa: E731
    etab_t = {t for t, x in trans.items() if cm.etabli(x)}
    etab_e = {k for k, x in etats.items() if cm.etabli(x)}

    def vers_etat(e):
        return _plus_court(st, trans, st["initiaux"], lambda x: x == e)

    def via(seq: list[str]) -> list[str] | None:
        p = vers_etat(trans[seq[0]]["de"])
        if p is None:
            return None
        return _complet(st, trans, p + seq, trans[seq[-1]]["vers"], lim)

    cand: list = []
    if strategie == "etats":
        cibles = {e for e in etats if e in st["accessibles"] and e not in deja["etats"]} - set(st["initiaux"])
        etablis = etab_e
        for e in sorted(cibles, key=lambda k: (k not in etab_e, -len(vers_etat(k) or []), k)):
            p = _complet(st, trans, vers_etat(e) or [], e, lim)
            if p:
                cand.append((p, f"Atteint l'état « {nom_e(e)} »."))
    elif strategie in ("transitions", "conditions"):
        ts = [t for t in trans if trans[t]["de"] in st["accessibles"]]
        if strategie == "conditions":
            ts = [t for t in ts if trans[t].get("garde") and (trans[t]["garde"], trans[t].get("issue") or "vraie") not in deja["issues"]]
            cibles = {(trans[t]["garde"], trans[t].get("issue") or "vraie") for t in ts}
            etablis = {(trans[t]["garde"], trans[t].get("issue") or "vraie") for t in ts if t in etab_t}
        else:
            ts = [t for t in ts if t not in deja["transitions"]]
            cibles, etablis = set(ts), etab_t
        for tid in sorted(ts, key=lambda t: (t not in etab_t, -POIDS_PRIORITE.get(trans[t].get("priorite"), 1), t)):
            p = via([tid])
            if p is None:
                continue
            if strategie == "conditions":
                c = m["conditions"].get(trans[tid]["garde"], {})
                cand.append((p, f"Vérifie l'issue {trans[tid].get('issue') or 'vraie'} de la condition « {c.get('libelle', trans[tid]['garde'])} »."))
            else:
                cand.append((p, f"Parcourt la transition « {nom_t(tid)} »."))
    elif strategie == "paires":
        paires = [(t1, t2) for t1 in sorted(trans) for t2 in st["succ"][trans[t1]["vers"]]
                  if trans[t1]["de"] in st["accessibles"] and (t1, t2) not in deja["paires"]]
        cibles = set(paires)
        etablis = {x for x in paires if x[0] in etab_t and x[1] in etab_t}
        for t1, t2 in paires[: lim["chemins"] * 3]:
            p = via([t1, t2])
            if p is not None:
                cand.append((p, f"Enchaîne « {nom_t(t1)} » puis « {nom_t(t2)} »."))
    elif strategie in ("chemins", "critiques"):
        bruts: list = []

        def dfs(x, chemin, usages):
            if len(bruts) >= lim["chemins"] * 3:
                return
            if (x in st["finaux"] and chemin) or len(chemin) >= min(lim["profondeur"], lim["transitions_par_scenario"]):
                bruts.append((list(chemin), "Chemin d'un état initial à un état final." if x in st["finaux"] else "Chemin tronqué à la profondeur maximale."))
                return
            suite = [t for t in st["succ"][x] if usages.get(t, 0) < (1 + lim["passages_boucle"] if t in st["boucles"] else 1)]
            if not suite and chemin:
                bruts.append((list(chemin), "Chemin jusqu'à une impasse (état sans sortie)."))
                return
            for t in suite:
                usages[t] = usages.get(t, 0) + 1
                chemin.append(t)
                dfs(trans[t]["vers"], chemin, usages)
                chemin.pop()
                usages[t] -= 1
        for i in st["initiaux"]:
            dfs(i, [], {})
        bruts = [b for b in bruts if not any(_contient(s, b[0]) for s in deja["sequences"])]  # déjà couverts par un scénario
        if strategie == "critiques":
            bruts = sorted(bruts, key=lambda x: (-_score(x[0], trans, st, m), len(x[0])))[: max(1, min(lim["chemins"], 10))]
            bruts = [(p, f"Chemin prioritaire (score de risque {_score(p, trans, st, m)}) : " + j) for p, j in bruts]
        cand = bruts
        cibles = {tuple(p) for p, _ in cand}
        etablis = {tuple(p) for p, _ in cand if all(t in etab_t for t in p)}
    else:
        raise ValueError(f"Stratégie inconnue : {strategie} ({', '.join(STRATEGIES)})")
    return _minimiser(strategie, _reduire(cand), trans, cibles, etablis)[: lim["chemins"]]


def _score(p: list[str], trans: dict, st: dict, m: dict | None = None) -> int:
    """Score de risque d'un chemin (stratégie orientée risque) : priorité des transitions, risque métier des actions
    traversées (opération sensible, engagement), refus ou état d'erreur vérifié, état final atteint."""
    s = sum(POIDS_PRIORITE.get(trans[t].get("priorite"), 1) for t in p) + (2 if p and trans[p[-1]]["vers"] in st["finaux"] else 0)
    if m:
        for t in p:
            a = m["actions"].get(trans[t].get("action"), {}).get("libelle", "")
            s += RISQUES[_risque_action(a, m["etats"].get(trans[t]["de"], {}).get("nom", ""))] - 1
            if m["etats"].get(trans[t]["vers"], {}).get("type") == "erreur":
                s += 2
    return s


def _contient(grand: list[str], petit: list[str]) -> bool:
    n = len(petit)
    return any(grand[i:i + n] == petit for i in range(len(grand) - n + 1))


def _reduire(chemins: list[tuple[list[str], str]]) -> list[tuple[list[str], str]]:
    """Élimine les doublons et les chemins entièrement contenus dans un autre chemin retenu (redondants)."""
    uniques = list({tuple(p): (p, j) for p, j in chemins if p}.values())
    return [(p, j) for p, j in uniques if not any(q is not p and len(q) > len(p) and _contient(q, p) for q, _ in uniques)]


# =========================================================================== analyse complète
def analyser(mid: str, strategie: str = "transitions", limites: dict | None = None, mode: str = "exploratoire",
             inclure_couverts: bool = False) -> dict:
    """Analyse du modèle : structure (accessibles, inaccessibles, impasses, boucles, transitions non couvertes),
    informations manquantes, hypothèses, incohérences, et le MINIMUM de chemins qui atteint la couverture demandée,
    chacun avec sa valeur ajoutée. Par défaut, ce que les scénarios existants couvrent déjà n'est pas reciblé (ils sont
    listés comme réutilisés). mode « verifie » : éléments établis seulement. Mis en cache tant que rien n'a changé."""
    m = cm.exiger(mid)
    lim = {**LIMITES_DEFAUT, **{k: int(v) for k, v in (limites or {}).items() if k in LIMITES_DEFAUT and v}}
    if mode not in ("exploratoire", "verifie"):
        raise ValueError("Mode : exploratoire ou verifie.")
    cle = (mid, m.get("empreinte"), m.get("version"), strategie, json.dumps(lim, sort_keys=True), mode, bool(inclure_couverts), _empreinte_bdd(),
           json.dumps({k: h.get("statut") for k, h in (m.get("hypotheses") or {}).items()}, sort_keys=True))
    if cle in _CACHE:
        return json.loads(_CACHE[cle])
    etats, trans = _actifs(m, mode)
    st = _structure(m, etats, trans)
    conception = couverture_conception(m)
    deja = None if inclure_couverts else _deja(m, trans, conception)
    bruts = _par_strategie(strategie, m, etats, trans, st, lim, deja) if etats else []
    try:
        from atelier.discovery import connaissance

        gk = connaissance.construire() if bruts else None
    except Exception:  # noqa: BLE001
        gk = None
    chemins = [_decrire(m, etats, trans, st, p, j, strategie, conception, apport, gk) for p, j, apport in bruts]
    gardes = {t.get("garde") for t in trans.values() if t.get("garde")}
    issues = {(t["garde"], t.get("issue") or "vraie") for t in trans.values() if t.get("garde")}
    reutilises = [{"scenario": cle_s, "transitions": len(ts), "explicite": cle_s in conception["explicites"]}
                  for cle_s, ts in sorted(conception["par_scenario"].items())]
    hyp = [h for h in (m.get("hypotheses") or {}).values() if h.get("statut") == "proposée"]
    res = {
        "modele": resume(m), "strategie": strategie, "libelle_strategie": STRATEGIES[strategie][0], "mode": mode, "limites": lim,
        "inclure_couverts": bool(inclure_couverts),
        "structure": {"etats": len(etats), "transitions": len(trans), "conditions": len([c for c in m["conditions"].values() if c.get("validation") != "rejeté"]),
                      "initiaux": [_ref(etats, k) for k in st["initiaux"]], "finaux": [_ref(etats, k) for k in sorted(st["finaux"])],
                      "accessibles": len(st["accessibles"]),
                      "inaccessibles": [_ref(etats, k) for k in sorted(set(etats) - st["accessibles"])],
                      "impasses": [_ref(etats, k) for k in sorted(etats) if not st["succ"][k] and k not in st["finaux"]],
                      "boucles": st["boucles"],
                      "transitions_non_couvertes": sorted(set(trans) - set(conception["transitions"])),
                      "conditions_non_rattachees": sorted(k for k, c in m["conditions"].items() if c.get("validation") != "rejeté" and k not in gardes),
                      "issues_non_modelisees": sorted(f"{g} : issue {'fausse' if i == 'vraie' else 'vraie'}" for g, i in issues
                                                      if (g, "fausse" if i == "vraie" else "vraie") not in issues),
                      "niveaux": {n: sum(1 for c in cm.COLLECTIONS for e in m[c].values() if e.get("niveau") == n) for n in cm.NIVEAUX}},
        "chemins": chemins, "reutilises": reutilises, "hypotheses": hyp,
        "manquant": list(m.get("manquant") or []) + _a_confirmer(m), "incoherences": incoherences(m),
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


def _decrire(m, etats, trans, st, p: list[str], justification: str, strategie: str, conception: dict, apport: set | None = None, g=None) -> dict:
    sts = [trans[p[0]]["de"]] + [trans[t]["vers"] for t in p] if p else []
    conds = [{"id": trans[t]["garde"], "libelle": m["conditions"][trans[t]["garde"]].get("libelle", ""), "issue": trans[t].get("issue") or "vraie",
              "confiance": m["conditions"][trans[t]["garde"]].get("confiance"), "niveau": m["conditions"][trans[t]["garde"]].get("niveau")}
             for t in p if trans[t].get("garde")]
    elements = [etats[s] for s in sts] + [trans[t] for t in p] + [m["conditions"][c["id"]] for c in conds] \
        + [m["actions"][trans[t]["action"]] for t in p if trans[t].get("action") in m["actions"]]
    manquant = []
    for t in p:
        x = trans[t]
        if not cm.etabli(x):
            manquant.append(f"Transition {etats[x['de']]['nom']} → {etats[x['vers']]['nom']} : {x.get('niveau')} (hypothèse, pas une exigence).")
        if x.get("postconditions_a_confirmer"):
            manquant.append(f"Résultat attendu après « {etats[x['vers']]['nom']} » : à confirmer (exigence ou validation).")
    manquant += [f"Condition « {c['libelle']} » : {c['niveau']}." for c in conds if c["niveau"] not in cm.ETABLIS]
    fin = etats[sts[-1]] if sts else {}
    type_ = "negatif" if fin.get("type") in ("erreur", "systeme") and not cm.etabli(fin) or fin.get("type") == "erreur" else \
        "alternatif" if any(trans[t].get("alternative") for t in p) else "principal"
    prio = max((POIDS_PRIORITE.get(trans[t].get("priorite"), 1) for t in p), default=1)
    existants = sorted({s for s, ts in conception["par_scenario"].items() if set(p) <= set(ts)})
    apport = apport or set()

    def lib_unite(u):
        if isinstance(u, tuple) and len(u) == 2 and u[0] in trans and u[1] in trans:
            return f"« {etats[trans[u[0]]['de']]['nom']} → {etats[trans[u[0]]['vers']]['nom']} » puis « {etats[trans[u[1]]['vers']]['nom']} »"
        if isinstance(u, tuple) and len(u) == 2:
            return f"« {m['conditions'].get(u[0], {}).get('libelle', u[0])} » ({u[1]})"
        if isinstance(u, tuple):
            return "le parcours complet"
        if u in trans:
            return f"« {etats[trans[u]['de']]['nom']} → {etats[trans[u]['vers']]['nom']} »"
        return f"« {etats.get(u, {}).get('nom', u)} »"
    nature = {"transitions": "transition(s)", "etats": "état(s)", "paires": "enchaînement(s)", "conditions": "issue(s) de condition",
              "chemins": "parcours", "critiques": "parcours critique"}[strategie]
    valeur = f"Couvre {len(apport)} {nature} jamais vérifié(s) par un scénario : " + ", ".join(lib_unite(u) for u in sorted(apport, key=str)[:6]) \
        if apport else "Aucune couverture nouvelle (chemin redondant)."
    pid = "P-" + _h(*p)
    hypothese = any(not cm.etabli(e) for e in elements)
    noms = [etats[x]["nom"] for x in sts]
    court = noms if len(noms) <= 5 else noms[:2] + ["…"] + noms[-2:]  # titre lisible : le chemin complet est dans « etats »
    cond_finale = next((c for c in reversed(conds) if c["id"] == trans[p[-1]].get("garde")), None) if p else None
    titre = " → ".join(court) + (f" (si « {cond_finale['libelle'][:70]} » {'non remplie' if cond_finale['issue'] == 'fausse' else 'remplie'})"
                                 if cond_finale else "")
    return {"id": pid, "titre": titre, "chemin_complet": " → ".join(noms),
            "description": [_phrase(m, etats, trans[t]) for t in p], "etats": sts, "transitions": p,
            "actions": [trans[t]["action"] for t in p if trans[t].get("action")], "conditions": conds, "type": type_,
            "priorite": {3: "haute", 1: "normale", 0: "basse"}.get(prio, "normale"), "justification": justification, "strategie": strategie,
            "valeur_ajoutee": valeur, "apport": len(apport), "hypothese": hypothese,
            "confirme": not hypothese, "manquant": manquant, "scenarios_existants": existants, "atteint_final": bool(sts) and sts[-1] in st["finaux"],
            "exigences": sorted({u for t in p for u in trans[t].get("exigences") or []}), "automatisation": preparation(m, p, g)}


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
    """Transitions et états vérifiés par un scénario BDD : traçabilité MBT explicite (identifiants de transitions, ceux
    d'un autre modèle valent pour les mêmes transitions observées), sinon enchaînement des écrans des étapes (écran A
    puis écran B = transition A → B, action reconnue si possible). Les conditions et les états d'erreur ne sont couverts
    que par la traçabilité explicite."""
    scenarios = _scenarios() if scenarios is None else scenarios
    par_ecran: dict = {}
    for k, e in m["etats"].items():
        if e.get("ecran") and e.get("type") == "ecran":
            par_ecran.setdefault(e["ecran"].split(":", 1)[-1], k)
    par_paire: dict = {}
    for tid, t in m["transitions"].items():
        if t.get("validation") != "rejeté" and (not t.get("garde") or t.get("garde_deduite")):
            par_paire.setdefault((t["de"], t["vers"]), []).append(tid)
    par_scenario, etats_couverts, explicites = {}, set(), set()
    for s in scenarios:
        cle = s.get("cle", "")
        x = s.get("mbt") or {}
        ts = [t for t in x.get("transition_ids") or [] if t in m["transitions"]]
        if ts:
            par_scenario[cle] = ts
            explicites.add(cle)
            etats_couverts |= {e for e in x.get("state_ids") or [] if e in m["etats"]}
            continue
        etapes = [e for sc in s.get("scenarios", []) for e in sc.get("etapes", [])]
        seq = [par_ecran[e["ecran"]] for e in etapes if e.get("ecran") in par_ecran]
        seq = [v for i, v in enumerate(seq) if i == 0 or v != seq[i - 1]]
        etats_couverts |= set(seq)
        ts = []
        texte = " ".join(e.get("texte", "") for e in etapes)
        for a, b in zip(seq, seq[1:]):
            cands = par_paire.get((a, b), [])
            meilleur = [t for t in cands if _mots(m["actions"].get(m["transitions"][t].get("action"), {}).get("libelle", "")) & _mots(texte)]
            ts += meilleur or cands[:1]
        if ts:
            par_scenario[cle] = ts
    transitions = sorted({t for ts in par_scenario.values() for t in ts})
    return {"transitions": transitions, "etats": sorted(etats_couverts & set(m["etats"])), "par_scenario": par_scenario,
            "explicites": sorted(explicites)}


def couverture(mid: str) -> dict:
    """Couverture comportementale (cahier d'évolution § 9). Dénominateurs : éléments ÉTABLIS (Confirmé, Observé) ; les
    hypothèses (Déduit, À confirmer) n'entrent jamais dans les indicateurs officiels. Cinq niveaux, jamais confondus :
    conception (cas conçus ou scénarios), scénarios BDD, automatisation (test Robot relié), exécution (test exécuté),
    validée (dernière exécution réussie). « Vérifié » = validé : un scénario conçu n'est pas un comportement vérifié."""
    from atelier.discovery import connaissance

    m = cm.exiger(mid)
    g = connaissance.construire()
    etats = {k: e for k, e in m["etats"].items() if cm.etabli(e)}
    trans = {k: t for k, t in m["transitions"].items() if cm.etabli(t) and t.get("de") in etats and t.get("vers") in etats}
    issues = {(t["garde"], t.get("issue") or "vraie") for t in trans.values() if t.get("garde") and cm.etabli(m["conditions"].get(t["garde"], {}))}
    bdd = couverture_conception(m)
    cas = _cas_us(m)
    niv = {"conception": (set(bdd["transitions"]) | cas["transitions"], set(bdd["etats"]) | cas["etats"]),
           "bdd": (set(bdd["transitions"]), set(bdd["etats"]))}
    auto, execu, valide = (set(), set()), (set(), set()), (set(), set())
    for cle, ts in bdd["par_scenario"].items():
        sid = f"scenario:{cle}"
        robots = [r.vers for r in g.sortants(sid) if r.type == "implemente_par" and r.confirmee] if sid in g.noeuds else []
        if not robots:
            continue
        es = {m["transitions"][t]["de"] for t in ts if t in m["transitions"]} | {m["transitions"][t]["vers"] for t in ts if t in m["transitions"]}
        auto[0].update(ts), auto[1].update(es)
        statuts = [g.noeuds[r].proprietes.get("dernier_statut") for r in robots if r in g.noeuds]
        if any(statuts):
            execu[0].update(ts), execu[1].update(es)
        if any(s == "PASS" for s in statuts):
            valide[0].update(ts), valide[1].update(es)
    niv.update(automatisation=auto, execution=execu, validee=valide)
    try:
        retenus = [p for p in analyser(mid, "chemins", {"chemins": 30}, "verifie", True)["chemins"] if p["atteint_final"]]
    except Exception:  # noqa: BLE001
        retenus = []

    def bloc(ts: set, es: set) -> dict:
        ti = set(ts) & set(trans)
        iss = {(trans[t]["garde"], trans[t].get("issue") or "vraie") for t in ti if trans[t].get("garde")} & issues
        return {"etats": len(set(es) & set(etats)), "transitions": len(ti), "issues": len(iss),
                "chemins": sum(1 for p in retenus if set(p["transitions"]) <= ti),
                "taux": round(len(ti) / len(trans), 3) if trans else None}
    niveaux = {k: bloc(*v) for k, v in niv.items()}
    gen = m.get("chemins_generes") or {}
    inconnus = sum(1 for c in cm.COLLECTIONS for e in m[c].values() if e.get("niveau") in ("Déduit", "À confirmer")) \
        + sum(1 for h in (m.get("hypotheses") or {}).values() if h.get("statut") == "proposée")
    try:
        evo = evolutions(mid)
    except Exception:  # noqa: BLE001
        evo = {"chemins_impactes": []}
    bdd_t = set(bdd["transitions"])
    return {
        "modele": {"etats": len(etats), "transitions": len(trans), "issues": len(issues), "chemins": len(retenus),
                   "etats_confirmes": sum(e.get("niveau") == "Confirmé" for e in etats.values()),
                   "transitions_confirmees": sum(t.get("niveau") == "Confirmé" for t in trans.values()),
                   "conditions": sum(1 for c in m["conditions"].values() if c.get("validation") != "rejeté")},
        **niveaux,
        "indicateurs": {"etats": {"verifies": niveaux["validee"]["etats"], "etablis": len(etats)},
                        "transitions": {"verifiees": niveaux["validee"]["transitions"], "etablies": len(trans)},
                        "conditions": {"issues_verifiees": niveaux["validee"]["issues"], "issues_etablies": len(issues)},
                        "chemins": {"couverts": niveaux["bdd"]["chemins"], "retenus": len(retenus)},
                        "inconnus": inconnus, "scenarios_reutilises": len([s for s in bdd["par_scenario"] if s not in {v.get("scenario") for v in gen.values()}]),
                        "scenarios_generes": len(gen), "chemins_impactes": len(evo.get("chemins_impactes") or [])},
        "transitions_non_couvertes": [{"id": t, "libelle": f"{etats[trans[t]['de']]['nom']} → {etats[trans[t]['vers']]['nom']}"}
                                      for t in sorted(set(trans) - bdd_t)],
        "conditions_non_verifiees": sorted({g_ for g_, i in issues if (g_, i) not in {(trans[t]["garde"], trans[t].get("issue") or "vraie") for t in bdd_t & set(trans) if trans[t].get("garde")}}),
        "definitions": {"conception": "cas conçus (Test Design, traçabilité MBT) ou scénarios BDD", "bdd": "scénarios BDD du référentiel",
                        "automatisation": "scénario relié à un test Robot (identifiant en tag, lien confirmé)",
                        "execution": "test Robot exécuté (output.xml)", "validee": "dernière exécution réussie",
                        "etablis": "dénominateurs : éléments Confirmés ou Observés ; les hypothèses n'entrent pas dans les indicateurs officiels",
                        "remarque": "générer ou concevoir un scénario n'est jamais une preuve d'exécution"},
    }


def couverture_globale() -> dict:
    """Indicateurs comportementaux de tous les modèles (Dashboard, écran Couverture). Les modèles sont d'abord actualisés
    si le Knowledge Graph a changé (MBT incrémental)."""
    try:
        evol = actualiser_tous()
    except Exception:  # noqa: BLE001
        evol = []
    modeles = cm.lister()
    total = {"modeles": len(modeles), "parcours_identifies": 0, "parcours_couverts": 0, "transitions": 0, "transitions_couvertes": 0,
             "transitions_non_couvertes": 0, "conditions_non_verifiees": 0, "scenarios_manquants": 0,
             "etats_etablis": 0, "etats_verifies": 0, "transitions_verifiees": 0, "issues_etablies": 0, "issues_verifiees": 0,
             "inconnus": 0, "scenarios_reutilises": 0, "scenarios_generes": 0, "chemins_impactes": 0,
             "niveaux": {k: 0 for k in ("conception", "bdd", "automatisation", "execution", "validee")}}
    details = []
    for x in modeles:
        try:
            c = couverture(x["id"])
            manquants = analyser(x["id"], "transitions", mode="verifie")["chemins"]
        except Exception:  # noqa: BLE001 — un modèle illisible n'empêche pas les autres
            continue
        i = c["indicateurs"]
        total["parcours_identifies"] += i["chemins"]["retenus"]
        total["parcours_couverts"] += i["chemins"]["couverts"]
        total["transitions"] += c["modele"]["transitions"]
        total["transitions_couvertes"] += c["bdd"]["transitions"]
        total["transitions_non_couvertes"] += len(c["transitions_non_couvertes"])
        total["conditions_non_verifiees"] += len(c["conditions_non_verifiees"])
        total["scenarios_manquants"] += len(manquants)
        total["etats_etablis"] += i["etats"]["etablis"]
        total["etats_verifies"] += i["etats"]["verifies"]
        total["transitions_verifiees"] += i["transitions"]["verifiees"]
        total["issues_etablies"] += i["conditions"]["issues_etablies"]
        total["issues_verifiees"] += i["conditions"]["issues_verifiees"]
        for k in ("inconnus", "scenarios_reutilises", "scenarios_generes", "chemins_impactes"):
            total[k] += i[k]
        for k in total["niveaux"]:
            total["niveaux"][k] += c[k]["transitions"]
        details.append({"id": x["id"], "nom": x["nom"], "transitions": c["modele"]["transitions"], "conception": c["conception"]["transitions"],
                        "bdd": c["bdd"]["transitions"], "automatisation": c["automatisation"]["transitions"], "execution": c["execution"]["transitions"],
                        "validee": c["validee"]["transitions"], "inconnus": i["inconnus"], "chemins_impactes": i["chemins_impactes"]})
    return {**total, "modeles_detail": details, "evolutions": [e for e in evol if not e.get("erreur")]}


# =========================================================================== impact entre versions (lot 6)
def impact(mid: str, de: int | str, vers: int | str = "courante") -> dict:
    """Ce qu'une évolution du modèle touche : éléments changés, chemins et scénarios impactés (directement par leur
    traçabilité, potentiellement par leurs écrans), automatisations, couverture avant / après, actions proposées. La TNR
    ne retient que les scénarios touchés par des éléments ÉTABLIS. Rien n'est supprimé."""
    diff = cm.comparer(mid, de, vers)
    va, vb = cm.version(mid, de), cm.version(mid, vers)
    touches = {c: set(diff[c]["ajoutes"]) | set(diff[c]["retires"]) | {x["id"] for x in diff[c]["modifies"]} for c in cm.COLLECTIONS}
    for c in ("actions", "conditions"):
        cle = "action" if c == "actions" else "garde"
        for v in (va, vb):
            touches["transitions"] |= {k for k, t in (v.get("transitions") or {}).items() if t.get(cle) in touches[c]}
    etablis_t = {k for v in (va, vb) for k, t in (v.get("transitions") or {}).items() if k in touches["transitions"] and cm.etabli(t)}
    ecrans = {e.get("ecran", "").split(":", 1)[-1] for v in (va, vb) for k, e in (v.get("etats") or {}).items() if k in touches["etats"]}
    ecrans |= {(v.get("etats") or {}).get(t.get("de"), {}).get("ecran", "").split(":", 1)[-1]
               for v in (va, vb) for k, t in (v.get("transitions") or {}).items() if k in touches["transitions"]}
    ecrans.discard("")
    directs, potentiels = [], []
    for s in _scenarios():
        x = s.get("mbt") or {}
        ts = set(x.get("transition_ids") or [])
        if ts & touches["transitions"] or set(x.get("state_ids") or []) & touches["etats"]:
            directs.append({"cle": s["cle"], "titre": s.get("titre", ""), "officiel": bool(ts & etablis_t),
                            "raison": "généré depuis un chemin qui passe par un élément changé"})
        elif {e.get("ecran") for sc in s.get("scenarios", []) for e in sc.get("etapes", [])} & ecrans:
            potentiels.append({"cle": s["cle"], "titre": s.get("titre", ""), "raison": "passe par un écran concerné"})
    avant = couverture_conception({**va, **{k: va.get(k) or {} for k in cm.COLLECTIONS}})
    apres = couverture_conception({**vb, **{k: vb.get(k) or {} for k in cm.COLLECTIONS}})
    nouvelles = sorted(t for t in diff["transitions"]["ajoutes"] if t not in apres["transitions"])
    actions = [f"Relire {len(directs)} scénario(s) généré(s) depuis les éléments changés (aucun n'est supprimé)."] if directs else []
    if nouvelles:
        actions.append(f"Générer les scénarios des {len(nouvelles)} nouvelle(s) transition(s) (stratégie « transitions »).")
    if diff["transitions"]["retires"]:
        actions.append(f"{len(diff['transitions']['retires'])} transition(s) retirée(s) : vérifier que les scénarios qui les parcourent restent valides.")
    evo = evolutions(mid, de, vers)
    return {"difference": diff, "scenarios_impactes": directs, "scenarios_potentiels": potentiels,
            "chemins_impactes": evo["chemins_impactes"], "automatisations_impactees": evo["automatisations"], "revisions": evo["revisions"],
            "couverture_avant": {"transitions": len(avant["transitions"]), "total": len(va.get("transitions") or {})},
            "couverture_apres": {"transitions": len(apres["transitions"]), "total": len(vb.get("transitions") or {})},
            "transitions_nouvelles_non_couvertes": nouvelles, "actions_proposees": actions,
            "tags_tnr": sorted({d["cle"] for d in directs if d["officiel"]}),
            "a_examiner": sorted({d["cle"] for d in directs if not d["officiel"]})}


def impact_element(g, noeud: str) -> dict:
    """Pour l'analyse d'impact du graphe et la non-régression d'un build : modèles, transitions et scénarios générés
    concernés par un élément changé. Écran, action, locator ou keyword : ce qui le touche ; module : ses écrans ; User
    Story ou règle : les transitions qui portent ses critères ou ses conditions. Scénarios renvoyés avec leurs tests
    Robot et leur clé Xray quand elles existent (pour le périmètre de non-régression)."""
    N = g.noeuds
    vide = {"modeles": [], "transitions": 0, "scenarios": [], "tests_robot": [], "tests_xray": []}
    if noeud not in N:
        return vide
    n = N[noeud]
    ecrans = set()
    if n.type == "ecran":
        ecrans.add(noeud)
    elif n.type in ("locator", "action"):
        ecrans.add("ecran:" + (n.proprietes.get("ecran") or noeud.split(":", 1)[1].split(".", 1)[0].split("@", 1)[0]))
    elif n.type == "module":
        ecrans |= {r.vers for r in g.sortants(noeud) if r.type == "contient" and N[r.vers].type == "ecran"}
    out, scen = [], set()
    for x in cm.lister():
        m = cm.charger(x["id"]) or {}
        E, T, A, C = (m.get(k) or {} for k in ("etats", "transitions", "actions", "conditions"))
        etats = {k for k, e in E.items() if e.get("ecran") in ecrans or e.get("us") == noeud}
        conds = {k for k, c in C.items() if c.get("us") == noeud or noeud in (c.get("exigences") or []) or c.get("regle") == noeud}
        ts = {k for k, t in T.items() if t.get("de") in etats or t.get("vers") in etats or t.get("garde") in conds
              or noeud in (t.get("exigences") or []) or t.get("us") == noeud
              or noeud in A.get(t.get("action"), {}).get("locators", []) or noeud in A.get(t.get("action"), {}).get("keywords", [])}
        if not ts and not etats:
            continue
        scen |= {v.get("scenario") for v in (m.get("chemins_generes") or {}).values() if set(v.get("transitions") or []) & ts and v.get("scenario")}
        out.append({"id": x["id"], "nom": x["nom"], "etats": len(etats), "transitions": len(ts)})
    robots, xray = set(), set()
    for s in scen:
        sid = f"scenario:{s}"
        if sid in N:
            robots |= {r.vers for r in g.sortants(sid) if r.type == "implemente_par" and r.confirmee}
            if N[sid].proprietes.get("cle_xray"):
                xray.add(N[sid].proprietes["cle_xray"])
    return {"modeles": out, "transitions": sum(x["transitions"] for x in out), "scenarios": sorted(scen),
            "tests_robot": sorted(robots), "tests_xray": sorted(xray)}


# =========================================================================== automatisation (lot 7)
def preparation(m: dict, chemin: list[str], g=None) -> dict:
    """Préparation à l'automatisation d'un chemin : actions, locators, keywords (existants d'abord), Page Object,
    données de test, préconditions, environnement. Jamais « prêt » tant qu'un élément manque : ce qui manque est listé
    (à découvrir ou à créer)."""
    if g is None:
        try:
            from atelier.discovery import connaissance

            g = connaissance.construire()
        except Exception:  # noqa: BLE001
            g = None
    N = g.noeuds if g is not None else {}
    etapes, manque = [], []
    champs_requis, champs_ok = set(), set()
    for tid in chemin:
        t = m["transitions"].get(tid, {})
        a = m["actions"].get(t.get("action"), {})
        if not a:
            manque.append(f"Transition {tid} : action inconnue (à découvrir).")
            etapes.append({"transition": tid, "action": "", "locators": [], "keywords": [], "page_objects": [], "statut": "à découvrir"})
            continue
        locs = [x for x in a.get("locators") or [] if not N or x in N]
        kws = [x for x in a.get("keywords") or [] if not N or x in N]
        poms = sorted({r.de for k in kws for r in (g.entrants(k) if g is not None and k in N else []) if r.type == "contient"
                       and N[r.de].type == "resource" and any(x.type == "contient" and N[x.vers].type == "locator" for x in g.sortants(r.de))})
        statut = "prêt" if locs and kws else "locator seul" if locs else "à découvrir"
        if not locs:
            manque.append(f"« {a.get('libelle')} » : aucun locator connu (Discovery de l'écran à refaire, ou locator à déclarer).")
        elif not kws:
            manque.append(f"« {a.get('libelle')} » : aucun keyword Robot existant n'utilise ce locator (à créer dans Automation Studio).")
        elif not poms:
            manque.append(f"« {a.get('libelle')} » : keyword hors Page Object (resource qui définit les locators de l'écran) : à ranger.")
        ecran = (m["etats"].get(t.get("de"), {}).get("ecran") or "")
        if g is not None and ecran in N:
            for r in g.sortants(ecran):
                c = N[r.vers]
                if r.type == "contient" and c.type == "composant" and c.proprietes.get("genre") == "champ":
                    champs_requis.add(r.vers)
                    if any(x.type == "utilise" and N[x.vers].type == "variable" for x in g.sortants(r.vers)) or any(
                            c.proprietes.get("nom_technique") in (j.proprietes.get("champs") or []) for j in N.values() if j.type == "jdd"):
                        champs_ok.add(r.vers)
        etapes.append({"transition": tid, "action": a.get("libelle", ""), "locators": locs, "keywords": kws, "page_objects": poms, "statut": statut})
    donnees_manquantes = sorted(champs_requis - champs_ok)
    for c in donnees_manquantes:
        manque.append(f"Champ « {N[c].libelle} » : aucune donnée de test (variable du référentiel ou jeu de données) à associer.")
    preconditions = sorted({m["transitions"][t].get("preconditions") for t in chemin if m["transitions"].get(t, {}).get("preconditions")})
    debut = m["etats"].get(m["transitions"][chemin[0]]["de"], {}) if chemin and chemin[0] in m["transitions"] else {}
    if debut and not debut.get("initial"):
        preconditions.append(f"Atteindre « {debut.get('nom')} » avant le scénario.")
    environnements = []
    try:
        from atelier.execution import jdd

        environnements = jdd.environnements()
    except Exception:  # noqa: BLE001
        pass
    if not environnements and champs_requis:
        manque.append("Aucun environnement de données (data/jdd/<env>.yaml) : impossible de fournir les données au test.")
    pret = bool(etapes) and all(e["statut"] == "prêt" for e in etapes) and not donnees_manquantes and (environnements or not champs_requis)
    return {"statut": "prêt" if pret else "partiel" if any(e["locators"] for e in etapes) else "à découvrir", "etapes": etapes, "manquant": manque,
            "donnees": {"champs": len(champs_requis), "manquantes": [N[c].libelle for c in donnees_manquantes]},
            "preconditions": preconditions, "environnements": environnements,
            "cibles": {"robot": True, "playwright": False, "cypress": False}}


# =========================================================================== mode automatique : cas pour une US
def cas_pour_us(cle: str, g=None) -> dict:
    """Mode automatique (génération des cas d'une US) : modèle de l'US construit ou actualisé en arrière-plan, minimum de
    chemins des transitions et des conditions qui ne sont pas déjà couverts, convertis en cas proposés (même forme que les
    cas par catégorie). Les scénarios existants qui couvrent déjà le comportement sont renvoyés comme réutilisables."""
    g = _graphe(g)
    if f"user_story:{cle}" not in g.noeuds:
        return {"cas": [], "reutilisables": [], "manquant": [f"US {cle} absente du Knowledge Graph : pas d'analyse comportementale."], "modele": None}
    m = construire("user_story", cle, g)
    chemins, vus, reutilisables = [], set(), []
    for s in ("conditions", "transitions"):
        a = analyser(m["id"], s)
        for p in a["chemins"]:
            if p["id"] not in vus:
                vus.add(p["id"])
                chemins.append(p)
        reutilisables = a["reutilises"]
    from atelier.generation import bdd, mbt_bdd

    cas = []
    for p in chemins:
        etapes = [{"action": phrase, "donnees": "", "resultat": ""} for phrase in p["description"]]
        if etapes:
            dernier = m["etats"][p["etats"][-1]]
            etapes[-1]["resultat"] = (m["transitions"][p["transitions"][-1]].get("postconditions") or f"« {dernier['nom']} » est atteint") + \
                (" (à confirmer)" if m["transitions"][p["transitions"][-1]].get("postconditions_a_confirmer") else "")
        cat = {"negatif": "negatif", "alternatif": "alternatif"}.get(p["type"], "navigation")
        lignes, prec = [], ""
        for e in mbt_bdd.modele_bdd(p, m, "US_MBT")["scenarios"][0]["etapes"]:
            t = e["type"] if e["type"] in ("given", "when", "then") else prec or "given"
            lignes.append(("And" if t == prec else bdd.MOTS_EN[t]) + " " + e["texte"])
            prec = t
        cas.append({"categorie": cat, "titre": f"{p['titre']}"[:250], "etapes": etapes, "gherkin": "\n".join(lignes),
                    "source_detail": f"analyse comportementale : modèle {m['id']} v{m['version']}, chemin {p['id']}",
                    "justification": f"{p['justification']} {p['valeur_ajoutee']}", "confiance": 0.8 if p["confirme"] else 0.5,
                    "provenance": "observé" if p["confirme"] else "déduit", "manquant": p["manquant"],
                    "mbt": {"model_id": m["id"], "model_version": m["version"], "source_path_id": p["id"], "transition_ids": p["transitions"],
                            "state_ids": p["etats"], "coverage_strategy": p["strategie"], "generation_origin": "US_MBT"}})
    return {"cas": cas, "reutilisables": reutilisables, "manquant": list(m.get("manquant") or []), "modele": resume(m),
            "hypotheses": sum(1 for h in (m.get("hypotheses") or {}).values() if h.get("statut") == "proposée")}


# =========================================================================== IA : propositions à valider
SYSTEME_IA = """Tu enrichis un modèle comportemental de test (états, transitions, conditions) d'une application.
Règles : ne JAMAIS inventer un message d'erreur exact ni une règle métier absente des textes fournis ; distinguer un
écran d'un état métier (un écran peut porter plusieurs états : formulaire vide, renseigné, invalide, opération en
attente, acceptée, refusée) ; propose des états manquants, des transitions possibles, l'issue contraire des conditions,
les comportements exceptionnels pertinents (session expirée, perte de connexion, double soumission, retour arrière,
annulation, interruption, reprise, accès non autorisé) seulement comme hypothèses, des incohérences, et, si des
évolutions sont fournies, des révisions des scénarios concernés (jamais leur suppression). Chaque élément cite le texte
source dans sa justification. Ne repropose aucun élément de « rejetes ». Réponds uniquement en JSON :
{"etats": [{"nom": "", "type": "metier|erreur|systeme", "justification": ""}],
 "transitions": [{"de": "<nom ou id d'état>", "vers": "<nom ou id d'état>", "action": "", "garde": "<libellé de condition>", "issue": "vraie|fausse", "justification": ""}],
 "conditions": [{"libelle": "", "justification": ""}], "incoherences": [""], "revisions": [{"scenario": "", "proposition": ""}]}"""


def lecture_pour_ia(mid: str) -> dict:
    """Ce que l'IA (ou Cursor par le MCP) lit : le modèle résumé avec les niveaux de confiance, les critères des US, les
    informations manquantes, les hypothèses, les dernières évolutions et ce qui a été rejeté (à ne pas reproposer)."""
    m = cm.exiger(mid)
    from atelier.discovery import connaissance

    g = connaissance.construire()
    evo = evolutions(mid)
    return {"modele": mid, "version": m["version"], "perimetre": m["perimetre"],
            "etats": [{"id": k, "nom": e.get("nom"), "type": e.get("type"), "ecran": e.get("ecran", ""), "niveau": e.get("niveau")}
                      for k, e in m["etats"].items() if e.get("validation") != "rejeté"],
            "transitions": [{"id": k, "de": t["de"], "vers": t["vers"], "evenement": t.get("evenement", ""),
                             "action": m["actions"].get(t.get("action"), {}).get("libelle", ""),
                             "garde": m["conditions"].get(t.get("garde"), {}).get("libelle", ""), "issue": t.get("issue", ""),
                             "resultat": t.get("postconditions", ""), "niveau": t.get("niveau")}
                            for k, t in m["transitions"].items() if t.get("validation") != "rejeté"],
            "conditions": [{"id": k, "libelle": c.get("libelle"), "niveau": c.get("niveau")} for k, c in m["conditions"].items() if c.get("validation") != "rejeté"],
            "criteres": {u: _criteres_us(g, u) for u in m.get("us") or [] if u in g.noeuds},
            "hypotheses": [{"id": h["id"], "categorie": h["categorie_libelle"], "libelle": h["libelle"], "statut": h["statut"]}
                           for h in (m.get("hypotheses") or {}).values()],
            "evolutions": {k: evo[k] for k in ("de", "vers", "nouveaux_etats", "etats_supprimes", "nouvelles_transitions", "transitions_retirees",
                                               "conditions_ajoutees", "conditions_supprimees", "scenarios")},
            "manquant": m.get("manquant") or [],
            "rejetes": [e.get("nom") or e.get("libelle") for c in cm.COLLECTIONS for e in m[c].values() if e.get("validation") == "rejeté"]
            + [h["libelle"] for h in (m.get("hypotheses") or {}).values() if h.get("statut") == "rejetée"]}


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


GENRES = {"tap": "clic", "click": "clic", "type": "saisie", "swipe": "défilement", "press_back": "retour arrière", "open_url": "ouverture d'adresse"}


SOUMISSION = re.compile(r"(?i)valid|confirm|envoy|soumet|soumission|enregistr|pay|command|signer|souscri|transf|virement|connecter")


SENSIBLE = re.compile(r"(?i)virement|paiement|payer|transf|command|souscri|signer|supprim")


AUTH = re.compile(r"(?i)connexion|login|authentif|identifi|mot.de.passe")


DOCUMENTE = {"session_expiree": r"session|expir|déconnect|deconnect", "perte_connexion": r"réseau|reseau|connexion (perdue|interrompue)|hors.ligne",
             "double_soumission": r"double|deux fois|plusieurs fois", "retour_arriere": r"retour arri|bouton retour|précédent|precedent",
             "annulation": r"annul", "interruption": r"interrompu|interruption", "reprise": r"repris|reprendre",
             "acces_non_autorise": r"autoris|droit|habilit|interdit|rôle|role", "formulaire_invalide": r"obligatoire|invalide|format"}


MAX_HYPOTHESES = 30


def _hypotheses(m: dict, g, textes: list[str]) -> dict:
    """Comportements exceptionnels NON documentés, proposés comme hypothèses (jamais comme exigences, jamais avec un
    résultat attendu inventé). Un comportement que les critères ou les règles décrivent déjà n'est pas proposé."""
    tout = " ".join(textes)
    documente = {k for k, motif in DOCUMENTE.items() if re.search(motif, tout, re.I)}
    out: dict = {}
    E, T, A, C = m["etats"], m["transitions"], m["actions"], m["conditions"]

    def ajouter(cat, de, libelle, etat_nom, etat_type="erreur", action="", evenement="", condition="", issue="", description=""):
        if cat in documente or len(out) >= MAX_HYPOTHESES:
            return
        hid = f"H-{cat}-{_h(de, action, condition, issue, evenement)}"
        risque = "élevé" if cat in ("acces_non_autorise", "interruption", "double_soumission") and SENSIBLE.search(action or libelle) \
            else "élevé" if cat == "acces_non_autorise" else _risque_action(action, E.get(de, {}).get("nom", ""))
        out[hid] = {"id": hid, "categorie": cat, "categorie_libelle": cm.CATEGORIES_HYPOTHESE[cat], "libelle": libelle, "description": description,
                    "risque": risque,
                    "de": de, "action": action, "evenement": evenement, "condition": condition, "issue": issue, "etat_nom": etat_nom,
                    "etat_type": etat_type, "statut": "proposée", "source": "catalogue des comportements exceptionnels de l'atelier",
                    "justification": "Comportement non décrit par les exigences ni par les règles : à confirmer avec l'équipe (résultat attendu inconnu)."}

    # issue contraire d'une condition établie dont une seule issue est modélisée
    issues: dict = {}
    for t in T.values():
        if t.get("garde") and t.get("validation") != "rejeté":
            issues.setdefault(t["garde"], {})[t.get("issue") or "vraie"] = t
    for cid, par in issues.items():
        if len(par) == 1 and cid in C and not C[cid].get("contraire"):
            iss, t = next(iter(par.items()))
            contraire = "fausse" if iss == "vraie" else "vraie"
            lib = C[cid].get("libelle", cid)
            out_lib = f"« {lib} » {'non remplie' if contraire == 'fausse' else 'remplie'} : comportement à confirmer"
            if len(out) < MAX_HYPOTHESES:
                hid = f"H-condition_inverse-{_h(cid, contraire)}"
                out[hid] = {"id": hid, "categorie": "condition_inverse", "categorie_libelle": cm.CATEGORIES_HYPOTHESE["condition_inverse"],
                            "libelle": f"Issue {contraire} de « {lib} »", "description": f"Depuis « {E[t['de']]['nom']} », que se passe-t-il si la condition est "
                            f"{'non remplie' if contraire == 'fausse' else 'remplie'} ? Aucune règle connue ne le dit.", "de": t["de"],
                            "action": A.get(t.get("action"), {}).get("libelle", ""), "evenement": t.get("evenement", ""), "condition": lib, "issue": contraire,
                            "etat_nom": out_lib[:120], "etat_type": "erreur", "statut": "proposée", "source": f"condition {cid}",
                            "justification": "La condition inverse doit être étudiée ; son résultat n'est proposé que si une règle le décrit.",
                            "risque": _risque_action(A.get(t.get("action"), {}).get("libelle", ""), E[t["de"]].get("nom", ""))}
    # soumissions : double soumission, perte de connexion, retour arrière, interruption et reprise, session expirée
    authentifie = any(AUTH.search(e.get("nom", "")) for e in E.values())
    engage = re.compile(r"(?i)valid|confirm|envoy|soumet|payer|signer|souscri|command")
    soumissions = [(k, t) for k, t in sorted(T.items()) if t.get("validation") != "rejeté" and t.get("provenance") == "observé"
                   and engage.search(A.get(t.get("action"), {}).get("libelle", "") + " " + A.get(t.get("action"), {}).get("cle", ""))]
    sensibles = [(k, t) for k, t in soumissions if SENSIBLE.search(A.get(t.get("action"), {}).get("libelle", ""))]
    session_faite = False
    for k, t in sensibles + [x for x in soumissions if x not in sensibles]:
        a = A.get(t.get("action"), {}).get("libelle", "")
        de = t["de"]
        ajouter("double_soumission", de, f"Double soumission de « {a} »", f"Double soumission de « {a} » : comportement à confirmer",
                action=a, evenement=f"double clic sur « {a} »", description="L'opération ne doit-elle être traitée qu'une fois ?")
        ajouter("perte_connexion", de, f"Perte de connexion pendant « {a} »", f"Perte de connexion pendant « {a} » : comportement à confirmer",
                "systeme", action=a, evenement="perte de connexion pendant le traitement")
        ajouter("retour_arriere", de, f"Retour arrière pendant « {a} »", f"Retour arrière pendant « {a} » : comportement à confirmer",
                action=a, evenement="retour arrière pendant le traitement")
        if SENSIBLE.search(a):
            ajouter("interruption", de, f"Interruption pendant « {a} »", f"Transaction « {a} » interrompue : comportement à confirmer", "systeme",
                    action=a, evenement="interruption pendant la transaction")
            ajouter("reprise", de, f"Reprise après interruption de « {a} »", f"Reprise de « {a} » après interruption : comportement à confirmer",
                    "metier", action=a, evenement="reprise après interruption")
        if authentifie and not AUTH.search(E[de].get("nom", "")) and not session_faite:
            session_faite = True  # une fois par modèle, sur l'opération la plus engageante
            ajouter("session_expiree", de, f"Session expirée pendant « {a} »", f"Session expirée pendant « {a} » : comportement à confirmer",
                    "systeme", action=a, evenement="expiration de la session")
    # formulaires : invalide, annulation
    for k, e in sorted(E.items()):
        if e.get("type") != "ecran" or e.get("ecran") not in g.noeuds:
            continue
        champs = [r.vers for r in g.sortants(e["ecran"]) if r.type == "contient" and g.noeuds[r.vers].type == "composant"
                  and g.noeuds[r.vers].proprietes.get("genre") == "champ"]
        sorties = [t for t in T.values() if t.get("de") == k and t.get("validation") != "rejeté"]
        if not champs or not sorties:
            continue
        if not any(E.get(t["vers"], {}).get("type") == "erreur" for t in sorties):
            ajouter("formulaire_invalide", k, f"Formulaire « {e['nom']} » invalide", f"Formulaire « {e['nom']} » invalide : comportement à confirmer",
                    condition=f"les champs obligatoires de « {e['nom']} » sont valides", issue="fausse",
                    description=f"{len(champs)} champ(s) : obligatoire manquant ou format invalide.")
        if not any(re.search(r"(?i)annul|retour|fermer", A.get(t.get("action"), {}).get("libelle", "")) for t in sorties):
            ajouter("annulation", k, f"Annulation depuis « {e['nom']} »", f"Opération annulée depuis « {e['nom']} » : comportement à confirmer",
                    "metier", evenement="annulation de l'opération")
    # accès non autorisé : un écran atteint après l'authentification, demandé directement
    if authentifie:
        apres = [k for k, e in sorted(E.items()) if e.get("type") == "ecran" and not e.get("initial") and not AUTH.search(e.get("nom", ""))]
        init = next((k for k, e in E.items() if e.get("initial")), "")
        for k in apres[:2]:
            if init:
                ajouter("acces_non_autorise", init, f"Accès direct à « {E[k]['nom']} » sans être authentifié",
                        f"Accès à « {E[k]['nom']} » refusé : comportement à confirmer", evenement=f"accès direct à « {E[k]['nom']} »")
    return dict(sorted(out.items(), key=lambda kv: (-RISQUES.get(kv[1].get("risque"), 1), kv[0])))  # le plus risqué d'abord


def _issues(trans: dict, p: list[str]) -> set:
    return {(trans[t]["garde"], trans[t].get("issue") or "vraie") for t in p if trans[t].get("garde")}


def _unites(strategie: str, trans: dict, p: list[str]) -> set:
    """Ce qu'un chemin couvre, au sens de la stratégie (pour minimiser le nombre de chemins)."""
    if strategie == "etats":
        return {trans[p[0]]["de"]} | {trans[t]["vers"] for t in p} if p else set()
    if strategie == "paires":
        return set(zip(p, p[1:]))
    if strategie == "conditions":
        return _issues(trans, p)
    if strategie in ("chemins", "critiques"):
        return {tuple(p)}
    return set(p)


def _minimiser(strategie: str, candidats: list, trans: dict, cibles: set, etablis: set) -> list:
    """Le plus petit ensemble de chemins qui couvre les cibles (glouton : à chaque tour, le chemin qui apporte le plus
    d'éléments encore non couverts, établis d'abord, le plus court à égalité). Un chemin sans apport est écarté."""
    reste, choisis = set(cibles), []
    pool = list(candidats)
    while reste and pool:
        def gain(c):
            u = _unites(strategie, trans, c[0]) & reste
            return (len(u & etablis) if strategie not in ("chemins", "critiques") else 0, len(u), -len(c[0]))
        meilleur = max(pool, key=gain)
        apport = _unites(strategie, trans, meilleur[0]) & reste
        if not apport:
            break
        choisis.append((meilleur[0], meilleur[1], apport))
        reste -= apport
        pool.remove(meilleur)
    return choisis


def _deja(m: dict, trans: dict, conc: dict) -> dict:
    seqs = list(conc["par_scenario"].values())
    return {"transitions": set(conc["transitions"]), "etats": set(conc["etats"]),
            "issues": {(trans[t]["garde"], trans[t].get("issue") or "vraie") for t in conc["transitions"] if t in trans and trans[t].get("garde")},
            "paires": {p for s in seqs for p in zip(s, s[1:])}, "sequences": seqs}


def _cas_us(m: dict) -> dict:
    """Cas de test conçus dans Test Design (US) qui portent une traçabilité MBT : couverture de CONCEPTION."""
    try:
        from atelier.intelligence import testabilite_us

        d = testabilite_us._us()
    except Exception:  # noqa: BLE001
        return {"transitions": set(), "etats": set()}
    ts, es = set(), set()
    for u in d.values():
        for c in u.get("cas") or []:
            x = c.get("mbt") or {}
            if c.get("statut") in ("Rejeté", "Regroupé") or not x:
                continue
            ts |= {t for t in x.get("transition_ids") or [] if t in m["transitions"]}
            es |= {e for e in x.get("state_ids") or [] if e in m["etats"]}
    return {"transitions": ts, "etats": es}


def actualiser_tous(g=None, forcer: bool = False) -> list[dict]:
    """MBT incrémental : quand le Knowledge Graph change (nouvelle version d'une US, d'un écran, d'une règle), chaque
    modèle existant est reconstruit ; ceux dont le comportement a changé reçoivent une nouvelle version, et leurs
    évolutions (éléments, chemins, scénarios, automatisations impactés) sont renvoyées. Rien n'est supprimé."""
    from atelier.discovery import connaissance

    try:
        emp = connaissance._empreinte_projet()[0]
    except Exception:  # noqa: BLE001
        emp = ""
    if not forcer and emp and _ACTUALISATION.get("empreinte") == emp:
        return _ACTUALISATION.get("resultat", [])
    g = _graphe(g)
    out = []
    for x in cm.lister():
        per = x.get("perimetre") or {}
        try:
            avant = x.get("version")
            m = construire(per.get("type", ""), per.get("id", ""), g)
        except Exception as e:  # noqa: BLE001 — un périmètre disparu n'empêche pas les autres
            out.append({"id": x["id"], "nom": x["nom"], "erreur": str(e)[:200]})
            continue
        if m["version"] != avant:
            out.append({"id": m["id"], "nom": m["nom"], "de": avant, "vers": m["version"], "evolutions": evolutions(m["id"])})
    _ACTUALISATION.update(empreinte=emp, resultat=out)
    vider_cache()
    return out


def evolutions(mid: str, de: int | str | None = None, vers: int | str = "courante") -> dict:
    """Ce qui a changé entre deux versions (par défaut : la précédente et la courante) : nouveaux états, états supprimés
    ou modifiés, transitions nouvelles, modifiées ou retirées, conditions ajoutées ou supprimées, chemins générés
    impactés, scénarios BDD et automatisations concernés, et les révisions proposées (jamais appliquées)."""
    m = cm.exiger(mid)
    if de is None:
        de = (m.get("version") or 1) - 1
    if not de or int(de) < 1:
        return {"modele": mid, "de": None, "vers": m.get("version"), "nombre": 0, "chemins_impactes": [], "scenarios": [], "automatisations": [],
                "revisions": [], "nouveaux_etats": [], "etats_supprimes": [], "etats_modifies": [], "nouvelles_transitions": [],
                "transitions_modifiees": [], "transitions_retirees": [], "conditions_ajoutees": [], "conditions_supprimees": []}
    d = cm.comparer(mid, de, vers)
    va, vb = cm.version(mid, de), cm.version(mid, vers)
    touches_t = set(d["transitions"]["ajoutes"]) | set(d["transitions"]["retires"]) | {x["id"] for x in d["transitions"]["modifies"]}
    touches_e = set(d["etats"]["retires"]) | {x["id"] for x in d["etats"]["modifies"]}
    for v in (va, vb):
        touches_t |= {k for k, t in (v.get("transitions") or {}).items() if t.get("de") in touches_e or t.get("vers") in touches_e
                      or t.get("garde") in set(d["conditions"]["retires"]) | {x["id"] for x in d["conditions"]["modifies"]}
                      or t.get("action") in {x["id"] for x in d["actions"]["modifies"]} | set(d["actions"]["retires"])}
    chemins = []
    for pid, c in (m.get("chemins_generes") or {}).items():
        t = set(c.get("transitions") or []) & touches_t
        e = set(c.get("etats") or []) & touches_e
        if t or e:
            chemins.append({"chemin": pid, "scenario": c.get("scenario"), "transitions": sorted(t), "etats": sorted(e)})
    scen = {c["scenario"] for c in chemins if c.get("scenario")}
    for s in _scenarios():
        if set((s.get("mbt") or {}).get("transition_ids") or []) & touches_t:
            scen.add(s["cle"])
    automatisations = []
    try:
        from atelier.discovery import connaissance

        g = connaissance.construire()
        for s in sorted(scen):
            for r in g.sortants(f"scenario:{s}") if f"scenario:{s}" in g.noeuds else []:
                if r.type == "implemente_par":
                    automatisations.append({"scenario": s, "test_robot": r.vers, "libelle": g.noeuds[r.vers].libelle})
    except Exception:  # noqa: BLE001
        pass
    revisions = []
    for c in chemins:
        for t in c["transitions"]:
            if t in d["transitions"]["retires"]:
                revisions.append({"scenario": c["scenario"], "proposition": f"La transition {t} n'existe plus : relire les étapes correspondantes (ne rien supprimer sans décision)."})
            else:
                champs = next((x["champs"] for x in d["transitions"]["modifies"] if x["id"] == t), [])
                revisions.append({"scenario": c["scenario"], "proposition": f"Transition {t} modifiée ({', '.join(champs) or 'éléments liés'}) : vérifier l'étape et le résultat attendu."})
        for e in c["etats"]:
            revisions.append({"scenario": c["scenario"], "proposition": f"État {e} modifié ou retiré : vérifier l'étape « Alors » correspondante."})
    for t in d["transitions"]["ajoutes"]:
        tb = (vb.get("transitions") or {}).get(t, {})
        revisions.append({"scenario": "", "proposition": f"Nouvelle transition {t} ({(vb.get('etats') or {}).get(tb.get('de'), {}).get('nom', tb.get('de'))} → "
                                                         f"{(vb.get('etats') or {}).get(tb.get('vers'), {}).get('nom', tb.get('vers'))}) : générer ou compléter un scénario."})
    for r in (m.get("revisions_proposees") or [])[-20:]:
        revisions.append({**r, "source": r.get("source", "IA")})
    return {"modele": mid, "de": d["de"], "vers": d["vers"], "nombre": d["nombre"],
            "nouveaux_etats": d["etats"]["ajoutes"], "etats_supprimes": d["etats"]["retires"], "etats_modifies": d["etats"]["modifies"],
            "nouvelles_transitions": d["transitions"]["ajoutes"], "transitions_modifiees": d["transitions"]["modifies"],
            "transitions_retirees": d["transitions"]["retires"], "conditions_ajoutees": d["conditions"]["ajoutes"],
            "conditions_supprimees": d["conditions"]["retires"], "chemins_impactes": chemins, "scenarios": sorted(scen),
            "automatisations": automatisations, "revisions": revisions}


def tracabilite(cle: str) -> dict:
    """Chaîne de traçabilité d'un scénario BDD : exigence → Knowledge Graph → modèle → transitions → chemin → scénario →
    automatisation → exécution. Chaque maillon dit s'il est établi ; un maillon absent est signalé, jamais supposé."""
    from atelier.discovery import connaissance
    from atelier.generation import bdd

    s = bdd.charger(cle)
    if not s:
        raise KeyError(f"Scénario BDD inconnu : {cle}")
    x = s.get("mbt") or {}
    g = connaissance.construire()
    m = cm.charger(x.get("model_id", "")) if x.get("model_id") else None
    trans = [{"id": t, "libelle": (m["etats"].get(m["transitions"][t]["de"], {}).get("nom", "") + " → " + m["etats"].get(m["transitions"][t]["vers"], {}).get("nom", "")),
              "niveau": m["transitions"][t].get("niveau")} for t in x.get("transition_ids") or [] if m and t in m["transitions"]]
    exig = sorted(set(x.get("related_user_story_ids") or []) | {u for t in x.get("transition_ids") or [] if m and t in m["transitions"]
                                                                for u in m["transitions"][t].get("exigences") or []})
    sid = f"scenario:{cle}"
    robots = [r.vers for r in g.sortants(sid) if r.type == "implemente_par"] if sid in g.noeuds else []
    return {"scenario": cle, "titre": s.get("titre", ""),
            "chaine": [
                {"maillon": "Exigence", "elements": [{"id": u, "libelle": g.noeuds[u].libelle if u in g.noeuds else u} for u in exig]},
                {"maillon": "Knowledge Graph", "elements": [{"id": e, "libelle": g.noeuds[e].libelle} for e in
                                                            sorted({m["etats"][st].get("ecran") for st in x.get("state_ids") or [] if m and st in m["etats"]} - {"", None}) if e in g.noeuds]},
                {"maillon": "Modèle MBT", "elements": [{"id": x.get("model_id"), "libelle": f"{m['nom']} v{x.get('model_version')}"}] if m else []},
                {"maillon": "Transitions", "elements": trans},
                {"maillon": "Chemin", "elements": [{"id": x.get("source_path_id"), "libelle": x.get("coverage_strategy", "")}] if x.get("source_path_id") else []},
                {"maillon": "Scénario BDD", "elements": [{"id": cle, "libelle": s.get("titre", ""), "statut": s.get("statut")}]},
                {"maillon": "Automatisation", "elements": [{"id": r, "libelle": g.noeuds[r].libelle} for r in robots]},
                {"maillon": "Exécution", "elements": [{"id": r, "libelle": g.noeuds[r].proprietes.get("dernier_statut")} for r in robots
                                                      if g.noeuds[r].proprietes.get("dernier_statut")]},
            ],
            "a_confirmer": [e["texte"] for sc in s.get("scenarios", []) for e in sc.get("etapes", []) if "à confirmer" in e.get("texte", "")],
            "remarque": "Un scénario conçu ou généré n'est jamais une preuve de validation : seule une exécution réussie l'est."}


RISQUES = {"élevé": 3, "moyen": 2, "faible": 1}


def _risque_action(libelle: str, etat_nom: str = "") -> str:
    """Risque métier d'une action : élevé si elle engage de l'argent ou des données sensibles (virement, paiement,
    signature, suppression), moyen si elle engage l'utilisateur (valider, confirmer, envoyer), faible sinon."""
    if SENSIBLE.search(libelle or ""):
        return "élevé"
    if re.search(r"(?i)valid|confirm|envoy|soumet|enregistr|command|souscri", libelle or ""):
        return "élevé" if SENSIBLE.search(etat_nom or "") else "moyen"
    return "faible"


def _pre_post(m: dict, auth: set) -> None:
    """Préconditions et postconditions structurées de chaque transition, chacune avec sa source (jamais inventées) :
    - précondition « Utilisateur authentifié » quand l'état de départ n'est atteignable qu'après un écran
      d'authentification (observé) ; la condition gardant la transition (issue vraie ou fausse, niveau de la condition) ;
    - postcondition : l'état atteint (observé), le résultat écrit dans l'exigence (Confirmé), ou « à confirmer »."""
    for t in m["transitions"].values():
        pre, post = [], []
        if t["de"] in auth:
            pre.append({"texte": "Utilisateur authentifié", "source": "navigation observée (écran d'authentification en amont)", "niveau": "Observé"})
        c = m["conditions"].get(t.get("garde") or "")
        if c:
            pre.append({"texte": c.get("libelle", "") if t.get("issue") != "fausse" else f"non : {c.get('libelle', '')}",
                        "source": c.get("source", ""), "niveau": cm.niveau(c)})
        cible = m["etats"].get(t["vers"], {})
        if cible.get("type") == "ecran":
            post.append({"texte": f"L'écran « {cible.get('nom')} » est affiché", "source": "carte (Discovery)", "niveau": "Observé"})
        if t.get("attendu_exigence"):
            post.append({"texte": t["attendu_exigence"][0].upper() + t["attendu_exigence"][1:], "source": ", ".join(t.get("exigences") or []) or "exigence",
                         "niveau": "Confirmé"})
        if cible.get("type") in ("erreur", "systeme", "metier"):
            if t.get("postconditions") and not t.get("postconditions_a_confirmer"):
                post.append({"texte": t["postconditions"][0].upper() + t["postconditions"][1:], "source": t.get("source", ""), "niveau": "Confirmé" if t.get("exigences") else cm.niveau(t)})
            else:
                post.append({"texte": "Résultat attendu à confirmer", "source": "aucune exigence ne le précise", "niveau": "À confirmer"})
        t["preconditions_liste"], t["postconditions_liste"] = pre, post


def _apres_authentification(m: dict) -> set:
    """États atteints APRÈS un écran d'authentification (connexion, login) : ils supposent un utilisateur authentifié."""
    succ: dict = {}
    for t in m["transitions"].values():
        succ.setdefault(t["de"], set()).add(t["vers"])
    vus, file = set(), [k for k, e in m["etats"].items() if AUTH.search(e.get("nom", "")) and e.get("type") == "ecran"]
    file = [y for x in file for y in succ.get(x, ())]
    while file:
        x = file.pop()
        if x in vus or AUTH.search(m["etats"].get(x, {}).get("nom", "")):
            continue
        vus.add(x)
        file += list(succ.get(x, ()))
    return vus
