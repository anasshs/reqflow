"""Application Discovery : sessions de découverte (cahier « Application Discovery — Discovery Studio »).

Une session encadre une période d'observation de l'application (guidée, assistée, autonome ou par les tests) :
configuration figée (application, build, plateforme, environnement, device, langue, mode, limites, actions
interdites), timeline des événements observés (écrans, transitions, actions, exploration, annotations, étapes
sensibles) et résultats calculés par différence entre la carte au démarrage et à l'arrêt : une session n'enrichit
que ce qu'elle découvre, sans dupliquer ce qui était déjà connu.

La carte de l'application (atelier/discovery/carte) reste la mémoire des écrans et transitions ; le Knowledge Graph
la lit : aucun second graphe. Stockage : <projet>/discovery/sessions/<id>.json et <id>.jsonl (timeline).
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime

from atelier.domain import evenements, projet

MODES = {"guidee": "Guided Discovery", "assistee": "AI Assisted Discovery", "autonome": "Autonomous Discovery",
         "tests": "Test-Based Discovery"}
STATUTS = ("Préparée", "En cours", "En pause", "Terminée")
TYPES_SUIVIS = {"carte_change", "navigation", "exploration", "session", "outil", "run_lance", "run_bilan"}
_verrou = threading.Lock()


def _d():
    return projet.PROJECT_DIR / "discovery" / "sessions"


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _auteur() -> str:
    return os.environ.get("USERNAME") or os.environ.get("USER") or "automaticien"


def _lire(sid: str) -> dict:
    f = _d() / f"{sid}.json"
    if not f.exists() or "/" in sid or ".." in sid:
        raise KeyError(f"Session inconnue : {sid}")
    return json.loads(f.read_text("utf-8"))


def _ecrire(s: dict):
    _d().mkdir(parents=True, exist_ok=True)
    f = _d() / f"{s['id']}.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, f)


def _evenement(sid: str, ev: dict):
    _d().mkdir(parents=True, exist_ok=True)
    with (_d() / f"{sid}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": _maintenant(), **ev}, ensure_ascii=False, default=str) + "\n")


# =========================================================================== photo de la carte
def photo() -> dict:
    """État de la carte de l'application active : écrans (empreinte, éléments, états), transitions."""
    from atelier.discovery import carte

    if not carte.app_courante():
        return {"app": None, "ecrans": {}, "transitions": []}
    ecr = {}
    for e in carte.ecrans():
        ecr[e["id"]] = {"nom": e.get("nom") or e.get("titre") or e["id"], "elements": len(e.get("elements") or {}),
                        "etats": len(e.get("etats") or []), "changements": len(e.get("changements") or []),
                        "plateformes": sorted((e.get("plateformes") or {}).keys())}
    return {"app": carte.app_courante(), "ecrans": ecr, "transitions": sorted(t["id"] for t in carte.transitions())}


# =========================================================================== cycle de vie
def _profil_donnees(nom: str) -> str:
    """Profil du référentiel de données Discovery choisi pour la session (facultatif)."""
    from atelier.discovery import donnees

    nom = str(nom or "").strip()
    if nom and nom not in donnees.profils_dict():
        raise ValueError(f"Profil de données inconnu : {nom} (Discovery › Données).")
    return nom


def creer(config: dict) -> dict:
    from atelier.discovery import carte

    app = config.get("app") or carte.app_courante()
    if not app:
        raise ValueError("Aucune application : la déclarer d'abord (Paramètres › Applications).")
    cfg_app = carte.config_app(app)
    cadre = {}
    if config.get("parcours"):  # session qui déroule un parcours utilisateur préparé : le cadrage complète la configuration
        from atelier.discovery import parcours_utilisateur

        cadre = parcours_utilisateur.cadre_session(str(config["parcours"]), app)
    plateforme = config.get("plateforme") or cadre.get("plateforme") or (cfg_app.get("plateformes") or ["web"])[0]
    # périmètre d'exploration : désigné explicitement (inconnu = refus), ou reconnu dans le texte libre « périmètre »
    from atelier.discovery import reste

    borne = reste.perimetre(config.get("perimetre_noeud", ""))
    if not borne and config.get("perimetre") and not cadre:
        try:
            borne = reste.perimetre(config["perimetre"])
        except KeyError:
            borne = None  # texte libre qui ne désigne ni module ni parcours : simple libellé, exploration non bornée
    if plateforme not in (cfg_app.get("plateformes") or []):
        raise ValueError(f"Plateforme {plateforme} non déclarée pour {cfg_app.get('nom')}.")
    mode = config.get("mode") or "guidee"
    if mode not in MODES:
        raise ValueError(f"Mode : {', '.join(MODES)}.")
    entier = lambda k, d: max(1, int(config.get(k) or d))  # noqa: E731
    sid = f"DS-{datetime.now():%Y%m%d-%H%M%S}"
    while (_d() / f"{sid}.json").exists():
        sid += "b"
    s = {"id": sid, "statut": "Préparée", "cree": _maintenant(), "auteur": _auteur(),
         "config": {"app": app, "app_nom": cfg_app.get("nom", app), "build": config.get("build") or cfg_app.get("build", ""),
                    "plateforme": plateforme, "environnement": config.get("environnement") or cadre.get("environnement", ""),
                    "device": config.get("device", ""), "langue": config.get("langue") or cfg_app.get("langue", "fr"),
                    "mode": mode, "point_depart": config.get("point_depart") or cadre.get("point_depart", ""),
                    "profondeur": entier("profondeur", 3),
                    "max_ecrans": entier("max_ecrans", 30),
                    "perimetre": (borne["libelle"] if borne else config.get("perimetre")) or cadre.get("perimetre", ""),
                    "perimetre_noeud": borne["noeud"] if borne else "",
                    "profil_donnees": _profil_donnees(config.get("profil_donnees") or cadre.get("profil_donnees", "")),
                    "parcours": cadre.get("parcours", ""), "parcours_nom": cadre.get("parcours_nom", ""),
                    "actions_interdites": [a.strip() for a in config.get("actions_interdites") or [] if str(a).strip()]},
         "periodes": [], "annotations": 0, "sensibles": 0}
    _ecrire(s)
    _evenement(sid, {"type": "session_creee", "detail": MODES[mode] + (f" · parcours « {cadre['parcours_nom']} »" if cadre else "")})
    if cadre:
        parcours_utilisateur.rattacher_session(cadre["parcours"], sid)
    return s


def perimetre_actif() -> dict | None:
    """Périmètre de la session en cours : ses écrans, et ceux qui étaient déjà connus au démarrage. Un écran découvert
    pendant la session n'est jamais « hors périmètre » : c'est le delta recherché."""
    from atelier.discovery import reste

    s = active()
    noeud = ((s or {}).get("config") or {}).get("perimetre_noeud") or ""
    if not noeud:
        return None
    try:
        p = reste.perimetre(noeud)
    except KeyError:
        return None  # module ou parcours disparu depuis : la session n'est plus bornée, plutôt que bloquée
    return {"noeud": p["noeud"], "libelle": p["libelle"], "ecrans": set(p["ecrans"]),
            "connus_au_debut": set(((s.get("photo_debut") or {}).get("ecrans") or {}).keys())}


def hors_perimetre(eid: str, p: dict | None) -> bool:
    return bool(p and eid and eid in p["connus_au_debut"] and eid not in p["ecrans"])


def active() -> dict | None:
    d = _d()
    for f in sorted(d.glob("DS-*.json"), reverse=True) if d.exists() else []:
        s = json.loads(f.read_text("utf-8"))
        if s["statut"] in ("En cours", "En pause"):
            return s
    return None


def demarrer(sid: str) -> dict:
    with _verrou:
        s = _lire(sid)
        a = active()
        if a and a["id"] != sid:
            raise PermissionError(f"Session {a['id']} déjà en cours : la terminer d'abord.")
        if s["statut"] == "Terminée":
            raise ValueError("Session terminée : en créer une nouvelle (les sessions s'enrichissent les unes les autres).")
        if s["statut"] == "Préparée":
            s["photo_debut"] = photo()
            s["debut"] = _maintenant()
        s["statut"] = "En cours"
        s["periodes"].append({"debut": _maintenant(), "t0": time.time()})
        _ecrire(s)
    _evenement(sid, {"type": "demarrage" if len(s["periodes"]) == 1 else "reprise"})
    return s


def pause(sid: str) -> dict:
    s = _lire(sid)
    if s["statut"] != "En cours":
        raise ValueError("Seule une session en cours peut être mise en pause.")
    s["statut"] = "En pause"
    s["periodes"][-1].update(fin=_maintenant(), t1=time.time())
    _ecrire(s)
    _evenement(sid, {"type": "pause"})
    return s


def arreter(sid: str) -> dict:
    s = _lire(sid)
    if s["statut"] == "Terminée":
        return s
    if s["periodes"] and "fin" not in s["periodes"][-1]:
        s["periodes"][-1].update(fin=_maintenant(), t1=time.time())
    s["statut"] = "Terminée"
    s["fin"] = _maintenant()
    s["photo_fin"] = photo()
    s["reseau"] = _reseau_session(s)
    s["resultats"] = _resultats(s)
    _ecrire(s)
    _evenement(sid, {"type": "arret", "detail": f"{s['resultats']['nouveaux_ecrans']} nouvel(aux) écran(s)"})
    if s["config"].get("parcours"):  # les écrans traversés sont proposés au parcours ; jamais d'échec de l'arrêt pour autant
        try:
            from atelier.discovery import parcours_utilisateur

            parcours_utilisateur.session_terminee(s)
        except Exception as e:  # noqa: BLE001
            _evenement(sid, {"type": "parcours", "detail": f"écrans non rattachés au parcours : {e}"[:300]})
    return s


def annoter(sid: str, texte: str, sensible: bool = False, ecran: str = "", cle: str = "") -> dict:
    """Annotation de l'étape courante ; « sensible » : étape à ne jamais rejouer ni explorer automatiquement
    (avec la clé d'un élément : l'élément est classé « sensitive » pour l'application)."""
    if not texte.strip():
        raise ValueError("Texte de l'annotation obligatoire.")
    s = _lire(sid)
    if sensible and cle.strip():
        from atelier.discovery import classement

        classement.marquer(cle.strip(), "sensitive", s["config"]["app"])
    s["sensibles" if sensible else "annotations"] = s.get("sensibles" if sensible else "annotations", 0) + 1
    _ecrire(s)
    _evenement(sid, {"type": "sensible" if sensible else "annotation", "detail": texte.strip()[:500], "ecran": ecran})
    return s


def timeline(sid: str, limite: int = 500) -> list[dict]:
    _lire(sid)
    f = _d() / f"{sid}.jsonl"
    return [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()][-limite:] if f.exists() else []


def lister() -> list[dict]:
    d = _d()
    out = []
    for f in sorted(d.glob("DS-*.json"), reverse=True) if d.exists() else []:
        s = json.loads(f.read_text("utf-8"))
        out.append({k: s.get(k) for k in ("id", "statut", "cree", "debut", "fin", "auteur", "config", "resultats", "annotations", "sensibles")})
    return out


# =========================================================================== observation (bus d'événements)
def observer_evenement(ev: dict):
    """Ajoute à la timeline de la session en cours les événements d'observation (sans effet hors session)."""
    if ev.get("type") not in TYPES_SUIVIS:
        return
    try:
        s = active()
    except Exception:  # noqa: BLE001 - jamais d'erreur côté observation
        return
    if not s or s["statut"] != "En cours":
        return
    t = ev.get("type")
    ecran = ev.get("ecran") or {}
    entree = {"type": t}
    if t == "carte_change" and isinstance(ecran, dict) and ecran:
        entree.update({"type": "ecran", "ecran": ecran.get("id"), "detail": ("nouvel écran : " if ecran.get("nouveau") else "écran reconnu : ")
                       + (ecran.get("nom") or ecran.get("titre") or ecran.get("id", "")), "nouveau": bool(ecran.get("nouveau"))})
    elif t == "carte_change" and ev.get("transition"):
        de, vers = ev["transition"][:2]
        entree.update({"type": "transition", "de": de, "vers": vers, "detail": f"{de} → {vers}"})
    elif t == "navigation":
        entree.update({"type": "transition", "de": ev.get("de"), "vers": ev.get("vers"), "detail": f"{ev.get('de')} → {ev.get('vers')}"})
    elif t == "exploration":
        entree["detail"] = ev.get("message") or ("fin de l'exploration" if ev.get("fin") else "")
    elif t == "outil":
        entree.update({"type": "action", "detail": f"{ev.get('nom')} {json.dumps(ev.get('args') or {}, ensure_ascii=False)[:200]}"})
    elif t == "session":
        entree["detail"] = f"device {ev.get('etat')} {ev.get('platform') or ''}".strip()
    elif t in ("run_lance", "run_bilan"):
        entree.update({"type": "test", "detail": "exécution de tests " + ("lancée" if t == "run_lance" else "terminée")})
    else:
        entree["detail"] = t
    _evenement(s["id"], entree)


evenements.abonner(observer_evenement, TYPES_SUIVIS)


# =========================================================================== résultats et vues
def _resultats(s: dict) -> dict:
    a, b = s.get("photo_debut") or {"ecrans": {}, "transitions": []}, s.get("photo_fin") or photo()
    nouveaux = sorted(set(b["ecrans"]) - set(a["ecrans"]))
    modifies = sorted(k for k in set(a["ecrans"]) & set(b["ecrans"])
                      if (b["ecrans"][k]["elements"], b["ecrans"][k]["etats"], b["ecrans"][k]["changements"])
                      != (a["ecrans"][k]["elements"], a["ecrans"][k]["etats"], a["ecrans"][k]["changements"]))
    tl = timeline(s["id"])
    reseau = s.get("reseau") or {}
    return {"comportements": sum(e["type"] == "comportement" for e in tl), "refus": sum(e["type"] == "refus" for e in tl),
            "endpoints": reseau.get("endpoints", []), "endpoints_proposes": reseau.get("proposes", []),
            "nouveaux_ecrans": len(nouveaux), "ecrans_modifies": len(modifies), "ecrans_visites": len({e.get("ecran") for e in tl if e.get("ecran")}),
            "nouvelles_transitions": len(set(b["transitions"]) - set(a["transitions"])), "actions": sum(e["type"] == "action" for e in tl),
            "composants_ajoutes": sum(b["ecrans"][k]["elements"] - a["ecrans"].get(k, {"elements": 0})["elements"] for k in b["ecrans"]),
            "nouveaux": [{"id": k, "nom": b["ecrans"][k]["nom"]} for k in nouveaux], "modifies": [{"id": k, "nom": b["ecrans"][k]["nom"]} for k in modifies],
            "annotations": s.get("annotations", 0), "sensibles": s.get("sensibles", 0)}


def resultats(sid: str) -> dict:
    s = _lire(sid)
    return {**s, "resultats": s.get("resultats") or (_resultats({**s, "photo_fin": photo()}) if s.get("photo_debut") else None),
            "timeline": timeline(sid, 300)}


def comparer(a: str, b: str) -> dict:
    """Deux sessions : écrans et transitions connus à la fin de chacune, différences."""
    sa, sb = _lire(a), _lire(b)
    pa, pb = sa.get("photo_fin") or sa.get("photo_debut") or {"ecrans": {}, "transitions": []}, sb.get("photo_fin") or photo()
    return {"a": a, "b": b, "ecrans_a": len(pa["ecrans"]), "ecrans_b": len(pb["ecrans"]),
            "ajoutes": [pb["ecrans"][k]["nom"] for k in sorted(set(pb["ecrans"]) - set(pa["ecrans"]))],
            "retires": [pa["ecrans"][k]["nom"] for k in sorted(set(pa["ecrans"]) - set(pb["ecrans"]))],
            "transitions_ajoutees": len(set(pb["transitions"]) - set(pa["transitions"]))}


def vue_ensemble(avec_graphe: bool = True) -> dict:
    """Indicateurs de découverte calculés sur la carte et le Knowledge Graph (aucune valeur estimée).
    avec_graphe=False : carte et sessions seulement (immédiat) ; le graphe se calcule à part (graphe_ensemble)."""
    from atelier.discovery import carte

    k = {"ecrans": 0, "transitions": 0, "actions": 0, "composants": 0, "locators": 0, "sans_locator_stable": 0,
         "ecrans_avec_variantes": 0, "ecrans_modifies": 0, "a_nommer": 0}
    if carte.app_courante():
        ecr, tr = carte.ecrans(), carte.transitions()
        k["ecrans"], k["transitions"] = len(ecr), len(tr)
        k["actions"] = len({(t["de"], json.dumps(t.get("action") or {}, sort_keys=True)) for t in tr})
        for e in ecr:
            els = (e.get("elements") or {}).values()
            k["composants"] += len(els)
            for el in els:
                locs = [l for ls in (el.get("locators") or {}).values() for l in ls]
                k["locators"] += len(locs)
                if el.get("type") in carte.INTERACTIFS and not any(carte.robustesse(l) == "robuste" for l in locs):
                    k["sans_locator_stable"] += 1
            k["ecrans_avec_variantes"] += bool(e.get("etats"))
            k["ecrans_modifies"] += bool(e.get("a_revoir"))
            k["a_nommer"] += not e.get("nom")
    out = {"kpi": k, "sessions": len(lister()), "active": active(), "app": carte.app_courante()}
    return {**out, **graphe_ensemble()} if avec_graphe else out


def graphe_ensemble() -> dict:
    """Indicateurs du Knowledge Graph (une seule construction), avec la durée de chaque étape pour le diagnostic."""
    from atelier.discovery import connaissance
    from atelier.execution import depot_robot

    durees = {}
    t = time.time()
    inv = depot_robot.lire_depot()
    durees["depot_robot"] = round(time.time() - t, 2)
    t = time.time()
    g = connaissance.construire(inventaire=inv)
    durees["graphe"] = round(time.time() - t, 2)
    par_type = {}
    for n in g.noeuds.values():
        par_type[n.type] = par_type.get(n.type, 0) + 1
    a_valider = sum(n.statut == "à valider" for n in g.noeuds.values()) + sum(r.statut == "à valider" for r in g.relations.values())
    return {"fonctionnel": {"fonctionnalites": par_type.get("fonctionnalite", 0), "parcours": par_type.get("parcours", 0),
                            "regles": par_type.get("regle", 0), "endpoints": par_type.get("endpoint", 0)},
            "qualite": {"a_valider": a_valider, "valides": sum(n.statut == "validé" for n in g.noeuds.values())},
            "durees": durees, "volume": {"noeuds": len(g.noeuds), "relations": len(g.relations), "fichiers_robot": len(inv.get("fichiers") or {})}}


def navigation() -> dict:
    """Transitions, impasses (aucune sortie), écrans isolés (aucune entrée hors départ), transitions instables."""
    from atelier.discovery import carte

    if not carte.app_courante():
        return {"transitions": [], "impasses": [], "isoles": [], "instables": []}
    g = carte.graphe()
    noms = {n["id"]: n["nom"] or n["titre"] or n["id"] for n in g["nodes"]}
    sorties = {e["de"] for e in g["edges"] if e["type"] != "press_back"}
    entrees = {e["vers"] for e in g["edges"] if e["type"] != "press_back"}
    return {"depart": g["depart"], "noms": noms,
            "transitions": [{**e, "de_nom": noms.get(e["de"], e["de"]), "vers_nom": noms.get(e["vers"], e["vers"])} for e in g["edges"]],
            "impasses": [{"id": i, "nom": noms[i]} for i in noms if i not in sorties],
            "isoles": [{"id": i, "nom": noms[i]} for i in noms if i not in entrees and i != g["depart"]],
            "instables": [e["id"] for e in g["edges"] if e["essais"] and e["fiabilite"] < 0.8]}


def chemin(vers: str, depuis: str = "", plateforme: str = "") -> dict:
    """Chemin le plus fiable vers un écran (carte.chemin : transitions réussies privilégiées)."""
    from atelier.discovery import carte

    g = carte.graphe()
    depuis = depuis or g["depart"]
    plateforme = plateforme or ((carte.config_app().get("plateformes") or ["web"])[0])
    c = carte.chemin(depuis, vers, plateforme)
    return {"depuis": depuis, "vers": vers, "plateforme": plateforme, "etapes": c or [], "trouve": c is not None}


# =========================================================================== actions depuis le Studio
def _reseau_session(s: dict) -> dict:
    """Appels réseau (web) observés pendant les périodes actives de la session, rapprochés du Knowledge Graph ;
    les endpoints non documentés sont proposés (à valider)."""
    from atelier.discovery import comportements

    if s["config"]["plateforme"] != "web":
        return {"endpoints": [], "proposes": [], "note": "mobile : observation réseau par proxy de test, non branchée"}
    journal = [x for x in comportements.journal_reseau(min((p.get("t0", 0) for p in s["periodes"]), default=0))
               if any(p.get("t0", 0) <= x["t"] <= p.get("t1", time.time()) for p in s["periodes"])]
    eps = comportements.rapprocher(comportements.endpoints(journal))
    try:
        proposes = comportements.proposer_endpoints([e for e in eps if not e["connu"]])
    except Exception:  # noqa: BLE001 - la proposition au graphe ne bloque pas l'arrêt de la session
        proposes = []
    return {"endpoints": eps, "proposes": proposes}


def _interdite_session(s: dict, element: dict) -> str:
    txt = f"{element.get('key') or ''} {element.get('libelle') or ''}".lower()
    return next((a for a in s["config"].get("actions_interdites") or [] if a.lower() in txt), "")


def agir(action: str, locator: str = "", element: dict | None = None, confirme: bool = False) -> dict:
    """Action déclenchée depuis le Studio sur le device / navigateur : classée puis autorisée (ou refusée) selon
    l'environnement de la session ; la transition est enregistrée dans la carte, les comportements observés
    (messages, éléments apparus / disparus) vont dans la timeline et deviennent des règles proposées."""
    from atelier.discovery import actions, classement, comportements, session
    from atelier.discovery.observation import observer

    s = active()
    if not s or s["statut"] != "En cours":
        raise PermissionError("Démarrer (ou reprendre) une session Discovery avant d'agir depuis le Studio.")
    if action not in ("tap", "press_back"):
        raise ValueError("Actions du Studio : tap, press_back (la saisie se fait à la main sur le device).")
    if not session.plateforme():
        raise RuntimeError("Aucun device ni navigateur connecté : « Connecter » dans le Studio.")
    avant = comportements.etat_ecran()
    ecran_avant = (observer([e for e in avant if e.get("key")]) or {}).get("id")
    el = dict(element or {})
    if action == "tap":
        if not locator:
            raise ValueError("Locator obligatoire.")
        el = next((e for e in avant if locator in (e.get("locators") or [])), None) or el
        interdite = _interdite_session(s, el)
        verdict = {"classe": "forbidden", "raison": f"action interdite pour la session (« {interdite} »)", "autorise": False,
                   "motif": "Action interdite par la configuration de la session."} if interdite else \
            classement.autorise(el, "guidee", s["config"].get("environnement", ""), confirme, s["config"]["app"])
    else:
        verdict = {"classe": "safe", "raison": "retour", "autorise": True, "motif": ""}
    libelle = el.get("libelle") or el.get("key") or locator or "retour"
    if not verdict["autorise"]:
        if not verdict.get("confirmation"):
            _evenement(s["id"], {"type": "refus", "detail": f"{libelle} : {verdict['motif']}"})
        return {**verdict, "execute": False}
    actions.tap(locator) if action == "tap" else actions.press_back()
    apres = comportements.etat_ecran()
    obs = observer([e for e in apres if e.get("key")])
    comps = comportements.comparer(avant, apres, libelle)
    if (obs or {}).get("id") != ecran_avant:  # changement d'écran : c'est une transition, seuls les messages comptent
        comps = [c for c in comps if c["type"] == "message"]
    for c in comps[:20]:
        _evenement(s["id"], {"type": "comportement", "detail": f"{c['type'].replace('_', ' ')} : {c['detail']}",
                             "ecran": (obs or {}).get("id")})
    regles = comportements.proposer_regles(comps, (obs or {}).get("nom") or (obs or {}).get("id", ""))
    return {**verdict, "execute": True, "ecran": obs, "comportements": comps, "regles_proposees": regles}
