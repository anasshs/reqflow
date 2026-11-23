"""Parcours utilisateur : cadrer une exploration avant de la dérouler (initiation de Discovery).

Avant de lancer l'application sur un device ou un navigateur, l'automaticien prépare le parcours : un nom, un objectif,
un point de départ et un résultat attendu, les exigences Jira (epic, US) que ce parcours réalise, le profil de données
à utiliser, la cible et qui navigue (lui, ou Cursor). Le parcours est enregistré : il se rouvre, se modifie et se
relance ; chaque déroulé est une session Discovery rattachée au parcours.

Ce que le cadrage apporte au Knowledge Graph :
- un nœud « parcours » déclaré (donc validé) dès l'enregistrement ;
- le lien exigence → parcours (« associe_a », lu « a le parcours »), validé d'office : c'est l'automaticien qui le
  déclare. Il n'entre dans aucun calcul de couverture ni de périmètre ;
- après un déroulé, les écrans traversés sont PROPOSÉS comme écrans du parcours (« contient », à valider) : ils ne
  deviennent officiels qu'à la validation du parcours, écran par écran ;
- les exigences du parcours sont proposées en priorité pour ces écrans dans Corrélation. Le lien écran ↔ exigence
  (« réalisé par ») reste une décision humaine, prise dans Corrélation, jamais ici.

Stockage : <projet>/discovery/parcours/<id>.json (un fichier par parcours, journal des modifications compris).
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime

from atelier.domain import projet

PILOTES = {"moi": "Je navigue", "cursor": "Cursor navigue"}
STATUTS = ("Brouillon", "Prêt", "En cours", "Exploré", "Validé", "Archivé")
TYPES_EXIGENCE = ("epic", "user_story", "bug")
LIMITES = {"nom": 120, "objectif": 1000, "point_depart": 150, "resultat_attendu": 1000, "environnement": 60}
LIBELLES = {"nom": "nom", "objectif": "objectif", "point_depart": "point de départ", "resultat_attendu": "résultat attendu",
            "exigences": "exigences", "profil_donnees": "profil de données", "plateforme": "plateforme",
            "environnement": "environnement", "pilote": "qui navigue"}
JOURNAL_MAX = 300
_ID = re.compile(r"^PU-[a-z0-9_]{1,60}$")
_verrou = threading.RLock()
_index: dict = {"cle": None, "valeur": {}}


PRODUCTION = re.compile(r"\bprod(uction)?\b|\bprd\b", re.I)


def _d():
    return projet.PROJECT_DIR / "discovery" / "parcours"


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _utilisateur() -> str:
    from atelier.domain import roles

    return roles.utilisateur()


def _lire(pid: str) -> dict:
    f = _d() / f"{pid}.json"
    if not _ID.match(str(pid or "")) or not f.exists():
        raise KeyError(f"Parcours inconnu : {pid}")
    return json.loads(f.read_text("utf-8"))


def _ecrire(p: dict):
    from atelier.intelligence.strategie import _ecrire_atomique

    p["historique"] = p.get("historique", [])[-JOURNAL_MAX:]
    _ecrire_atomique(_d() / f"{p['id']}.json", json.dumps(p, ensure_ascii=False, indent=1))


def _tous(app: str | None = None) -> list[dict]:
    d = _d()
    out = []
    for f in sorted(d.glob("PU-*.json")) if d.exists() else []:
        try:
            p = json.loads(f.read_text("utf-8"))
        except ValueError:
            continue  # fichier illisible : ignoré, jamais écrasé
        if app is None or p.get("app") == app:
            out.append(p)
    return out


def _journal(p: dict, action: str, **details):
    p.setdefault("historique", []).append({"date": _maintenant(), "par": _utilisateur(), "action": action, **details})


def _app() -> str:
    from atelier.discovery import carte

    app = carte.app_courante()
    if not app:
        raise ValueError("Aucune application : la déclarer d'abord (Paramètres › Applications).")
    return app


# --------------------------------------------------------------------------- contrôle des champs
def _exigences_locales() -> dict:
    from atelier.intelligence import patrimoine_xray

    pat = patrimoine_xray.charger() or {"exigences": []}
    return {x["cle"]: x for x in pat.get("exigences", [])}


def _texte(champ: str, valeur) -> str:
    t = str(valeur or "").strip()
    if len(t) > LIMITES[champ]:
        raise ValueError(f"Le champ « {LIBELLES[champ]} » dépasse {LIMITES[champ]} caractères.")
    return t


def _controler(champs: dict, p: dict, app: str) -> dict:
    """Valeurs contrôlées des seuls champs fournis ; une valeur refusée dit pourquoi, rien n'est corrigé en silence."""
    from atelier.discovery import carte, donnees

    out = {}
    for c in ("nom", "objectif", "point_depart", "resultat_attendu", "environnement"):
        if c in champs:
            out[c] = _texte(c, champs[c])
    if "nom" in out:
        if not out["nom"]:
            raise ValueError("Le nom du parcours est obligatoire.")
        homonyme = next((x for x in _tous(app) if x["id"] != p.get("id") and not x.get("archive")
                         and x["nom"].strip().lower() == out["nom"].lower()), None)
        if homonyme:
            raise ValueError(f"Un parcours « {homonyme['nom']} » existe déjà ({homonyme['id']}) : le rouvrir, ou choisir un autre nom.")
    if "exigences" in champs:
        connues = _exigences_locales()
        cles = list(dict.fromkeys(str(k).strip().upper() for k in champs["exigences"] or [] if str(k).strip()))
        absentes = [k for k in cles if k not in connues]
        if absentes:
            raise ValueError(f"Exigence(s) absente(s) de la copie locale Jira : {', '.join(absentes)} (synchroniser d'abord).")
        autres = [k for k in cles if connues[k].get("type") not in TYPES_EXIGENCE]
        if autres:
            raise ValueError(f"Seuls une epic, une US ou un bug se rattachent à un parcours : {', '.join(autres)}.")
        out["exigences"] = cles
    if "profil_donnees" in champs:
        profil = str(champs["profil_donnees"] or "").strip()
        if profil and profil not in donnees.profils_dict():
            raise ValueError(f"Profil de données inconnu : {profil} (Discovery › Données).")
        out["profil_donnees"] = profil
    if "plateforme" in champs:
        plateforme = str(champs["plateforme"] or "").strip()
        declarees = carte.config_app(app).get("plateformes") or []
        if plateforme and plateforme not in declarees:
            raise ValueError(f"Plateforme {plateforme} non déclarée pour l'application ({', '.join(declarees) or 'aucune'}).")
        out["plateforme"] = plateforme
    if "pilote" in champs:
        pilote = str(champs["pilote"] or "moi").strip()
        if pilote not in PILOTES:
            raise ValueError(f"Qui navigue : {', '.join(PILOTES)}.")
        out["pilote"] = pilote
    return out


# --------------------------------------------------------------------------- Knowledge Graph
def _noeud_ecran(eid: str) -> str:
    from atelier.discovery import carte

    e = carte.ecran(eid)
    return f"ecran:{e.get('nom') or e['id']}"


def _synchroniser_graphe(p: dict):
    """Nœud « parcours » déclaré et liens exigence → parcours, alignés sur le cadrage. Les liens vers les écrans ne sont
    jamais créés ici : ils viennent d'un déroulé, puis de la validation."""
    from atelier.discovery import carte, connaissance
    from atelier.domain import declarations

    nid = p.get("noeud") or f"parcours:{carte.slug(p['nom'], 50)}"
    p["noeud"] = nid
    data = declarations.charger()
    props = {"origine": "cadrage", "parcours_utilisateur": p["id"], "source_libelle": f"cadrage du parcours {p['id']}"}
    existant = data["noeuds"].get(nid)
    if existant is None:
        declarations.ajouter_noeud(nid, "parcours", p["nom"], description=p.get("objectif", ""), proprietes=props)
    elif (existant.get("libelle"), existant.get("description"), existant.get("statut"),
          (existant.get("proprietes") or {}).get("parcours_utilisateur")) != (p["nom"], p.get("objectif", ""), "validé", p["id"]):
        # nom ou objectif modifié, ou parcours déjà proposé par un agent sous ce nom : le cadrage le reprend et le valide
        declarations.modifier_noeud(nid, existant.get("statut", "validé"), libelle=p["nom"], description=p.get("objectif", ""),
                                    proprietes={**(existant.get("proprietes") or {}), **props}, statut="validé")
    connues = _exigences_locales()
    voulues = {f"{connues[k]['type']}:{k}" for k in p.get("exigences", []) if k in connues}
    actuelles = {rid: r for rid, r in declarations.charger()["relations"].items() if r["vers"] == nid and r["type"] == "associe_a"}
    source = f"cadrage du parcours {p['id']} par {_utilisateur()}"
    for de in sorted(voulues):
        if f"{de}|associe_a|{nid}" not in actuelles:
            declarations.ajouter_relation(de, nid, "associe_a", source=source)
    for rid, r in actuelles.items():
        if r["de"] not in voulues:
            declarations.supprimer_relation(rid, r.get("statut", "validé"))
    connaissance.vider_cache()


def _relation_ecran(p: dict, eid: str) -> str:
    return f"{p['noeud']}|contient|{_noeud_ecran(eid)}"


# --------------------------------------------------------------------------- vues
def statut(p: dict, sessions: list[dict] | None = None) -> str:
    if p.get("archive"):
        return "Archivé"
    etats = [s.get("statut") for s in (sessions if sessions is not None else _sessions(p))]
    if any(e in ("En cours", "En pause") for e in etats):
        return "En cours"
    if p.get("valide"):
        return "Validé"
    if "Terminée" in etats:
        return "Exploré"
    return "Prêt" if p.get("nom") and p.get("plateforme") else "Brouillon"


def _sessions(p: dict) -> list[dict]:
    from atelier.discovery import sessions_discovery

    out = []
    for sid in p.get("sessions", []):
        try:
            s = sessions_discovery._lire(sid)
        except KeyError:
            out.append({"id": sid, "statut": "introuvable"})
            continue
        r = s.get("resultats") or {}
        out.append({"id": sid, "statut": s["statut"], "debut": s.get("debut") or s.get("cree"), "fin": s.get("fin"),
                    "auteur": s.get("auteur", ""), "plateforme": s["config"].get("plateforme", ""),
                    "environnement": s["config"].get("environnement", ""), "device": s["config"].get("device", ""),
                    "ecrans_visites": r.get("ecrans_visites"), "nouveaux_ecrans": r.get("nouveaux_ecrans"),
                    "nouvelles_transitions": r.get("nouvelles_transitions")})
    return out


def _ecrans(p: dict) -> list[dict]:
    """Écrans du parcours dans l'ordre du déroulé, avec l'état de leur lien au parcours dans le Knowledge Graph."""
    from atelier.discovery import carte
    from atelier.domain import declarations

    relations = declarations.charger()["relations"] if p.get("ecrans") else {}
    dernier = set((p.get("deroules") or [{}])[-1].get("chemin") or [])
    out = []
    for eid in p.get("ecrans", []):
        try:
            e = carte.ecran(eid)
        except KeyError:
            out.append({"id": eid, "nom": eid, "connu": False, "lien": "écran absent de la carte"})
            continue
        r = relations.get(f"{p['noeud']}|contient|ecran:{e.get('nom') or e['id']}") or {}
        out.append({"id": eid, "nom": e.get("nom") or e.get("titre") or eid, "titre": e.get("titre", ""), "module": e.get("module", ""),
                    "nomme": bool(e.get("nom")), "connu": True, "lien": r.get("statut") or "sans lien",
                    "au_dernier_deroule": eid in dernier})
    return out


def _donnees(p: dict) -> dict | None:
    """Ce que le profil de données peut fournir avant de partir (aucune valeur n'est renvoyée ici)."""
    from atelier.discovery import donnees

    if not p.get("profil_donnees"):
        return None
    try:
        prep = donnees.preparer(p["profil_donnees"], p.get("environnement", ""))
    except Exception as e:  # noqa: BLE001 — profil supprimé depuis, référentiel illisible : dit, jamais bloquant ici
        return {"profil": p["profil_donnees"], "pret": False, "pretes": [], "bloquees": [], "erreur": str(e)[:300]}
    return {"profil": p["profil_donnees"], "pret": prep["pret"],
            "pretes": [{"cle": x["cle"], "origine": x.get("origine", "")} for x in prep["pretes"]],
            "bloquees": [{"cle": x["cle"], "raison": x.get("raison", "")} for x in prep["bloquees"]]}


def _exigences(p: dict) -> list[dict]:
    connues = _exigences_locales()
    out = []
    for k in p.get("exigences", []):
        x = connues.get(k)
        out.append({"cle": k, "type": x.get("type", ""), "resume": x.get("resume", ""), "statut": x.get("statut", ""),
                    "description": str(x.get("description") or "")[:1500], "criteres": list(x.get("criteres") or [])[:20],
                    "absente": False} if x else {"cle": k, "type": "", "resume": "", "criteres": [], "absente": True})
    return out


def _controles(p: dict, exigences: list[dict], donnees_: dict | None) -> dict:
    """Ce qui empêche de lancer (bloquants) et ce qui affaiblit le déroulé sans l'empêcher (avertissements)."""
    bloquants, avertissements = [], []
    if not p.get("plateforme"):
        bloquants.append("Choisir la plateforme (étape Cible).")
    if p.get("archive"):
        bloquants.append("Parcours archivé : le restaurer avant de le dérouler.")
    if not p.get("exigences"):
        avertissements.append("Aucune exigence rattachée : la corrélation des écrans ne sera pas ciblée.")
    absentes = [x["cle"] for x in exigences if x["absente"]]
    if absentes:
        avertissements.append(f"Exigence(s) absente(s) de la copie locale Jira : {', '.join(absentes)}.")
    if not p.get("profil_donnees"):
        avertissements.append("Aucun profil de données : les champs à saisir seront signalés comme manquants.")
    elif donnees_ and donnees_.get("erreur"):
        avertissements.append(f"Profil de données illisible : {donnees_['erreur']}")
    elif donnees_ and donnees_["bloquees"]:
        avertissements.append(f"{len(donnees_['bloquees'])} variable(s) du profil sans valeur : "
                              f"{', '.join(x['cle'] for x in donnees_['bloquees'][:6])}.")
    if PRODUCTION.search(str(p.get("environnement") or "")):
        avertissements.append("Environnement de production : explorer de préférence en recette. Les actions sensibles restent bloquées ; "
                              + ("Cursor navigue seul, sans revue avant chaque clic." if p.get("pilote") == "cursor"
                                 else "aucune donnée réelle à saisir."))
    if not p.get("objectif") or not p.get("resultat_attendu"):
        avertissements.append("Objectif ou résultat attendu vide : Cursor ne saura pas où s'arrêter.")
    return {"pret": not bloquants, "bloquants": bloquants, "avertissements": avertissements}


def _resume(p: dict) -> dict:
    return {**{k: p.get(k, "") for k in ("id", "nom", "objectif", "profil_donnees", "plateforme", "environnement", "pilote",
                                           "auteur", "cree", "modifie", "noeud")},
            "exigences": list(p.get("exigences", [])), "statut": statut(p), "sessions": len(p.get("sessions", [])),
            "ecrans": len(p.get("ecrans", [])), "archive": bool(p.get("archive")), "valide": p.get("valide")}


def lister(archives: bool = False) -> list[dict]:
    """Parcours utilisateur de l'application active, du plus récemment modifié au plus ancien."""
    from atelier.discovery import carte

    app = carte.app_courante()
    if not app:
        return []
    return sorted((_resume(p) for p in _tous(app) if archives or not p.get("archive")), key=lambda x: x["modifie"], reverse=True)


def explorations_libres() -> list[dict]:
    """Sessions Discovery terminées de l'application active, sans parcours préparé, qui ont traversé au moins deux
    écrans : chacune peut devenir un test (brouillon BDD depuis la session), comme un parcours déroulé."""
    from atelier.discovery import carte, sessions_discovery

    app = carte.app_courante()
    out = []
    for s in sessions_discovery.lister() if app else []:
        c, r = s.get("config") or {}, s.get("resultats") or {}
        if c.get("app") != app or c.get("parcours") or s.get("statut") != "Terminée" or (r.get("ecrans_visites") or 0) < 2:
            continue
        out.append({"id": s["id"], "debut": s.get("debut") or s.get("cree"), "fin": s.get("fin"), "auteur": s.get("auteur", ""),
                    "plateforme": c.get("plateforme", ""), "perimetre": c.get("perimetre", ""), "mode": c.get("mode", ""),
                    "ecrans_visites": r.get("ecrans_visites"), "nouveaux_ecrans": r.get("nouveaux_ecrans")})
    return out


def options() -> dict:
    """Ce que l'écran de cadrage propose : plateformes de l'application, profils de données, environnements, écrans connus."""
    from atelier.discovery import carte, donnees

    app = carte.app_courante()
    if not app:
        return {"application": None, "plateformes": [], "profils": [], "environnements": [], "ecrans": [], "pilotes": PILOTES}
    cfg = carte.config_app(app)
    try:
        envs = donnees._environnements_projet()
    except Exception:  # noqa: BLE001 — projet Xray non configuré : la saisie reste libre
        envs = []
    return {"application": {"slug": app, "nom": cfg.get("nom", app)}, "plateformes": cfg.get("plateformes") or [],
            "profils": [{"nom": x["nom"], "nature": x["nature"], "description": x["description"], "variables": len(x["variables"])}
                        for x in donnees.profils()],
            "environnements": envs, "pilotes": PILOTES,
            "ecrans": sorted({e.get("nom") or e.get("titre") or e["id"] for e in carte.ecrans()})}


def obtenir(pid: str) -> dict:
    p = _lire(pid)
    sessions = _sessions(p)
    exigences, donnees_ = _exigences(p), _donnees(p)
    ecrans = _ecrans(p)
    return {**_resume(p), "statut": statut(p, sessions), "point_depart": p.get("point_depart", ""),
            "resultat_attendu": p.get("resultat_attendu", ""), "app": p.get("app", ""), "exigences": exigences,
            "donnees": donnees_, "controles": _controles(p, exigences, donnees_), "sessions": sessions, "ecrans": ecrans,
            "ecrans_a_valider": sum(e.get("lien") == "à valider" for e in ecrans),
            "session_active": next((s["id"] for s in sessions if s["statut"] in ("En cours", "En pause")), ""),
            "historique": list(reversed(p.get("historique", [])))[:60], "demande_cursor": demande_cursor(p)}


# --------------------------------------------------------------------------- enregistrement
def enregistrer(pid: str = "", champs: dict | None = None) -> dict:
    """Crée (sans identifiant) ou modifie un parcours. Seuls les champs fournis changent ; chaque changement est journalisé."""
    from atelier.discovery import carte
    from atelier.domain import roles

    roles.exiger("construire")
    champs = champs or {}
    creation = not pid
    with _verrou:
        app = _app()
        if pid:
            p = _lire(pid)
            if p.get("app") != app:
                raise ValueError(f"Ce parcours appartient à l'application « {p.get('app')} », pas à l'application active.")
        else:
            p = {"app": app, "nom": "", "objectif": "", "point_depart": "", "resultat_attendu": "", "exigences": [], "profil_donnees": "",
                 "plateforme": "", "environnement": "", "pilote": "moi", "sessions": [], "deroules": [], "ecrans": [], "historique": []}
            if "nom" not in champs:
                raise ValueError("Le nom du parcours est obligatoire.")
            plats = (carte.config_app() or {}).get("plateformes") or []
            if not champs.get("plateforme") and len(plats) == 1:
                champs = {**champs, "plateforme": plats[0]}
        valeurs = _controler(champs, p, app)
        if creation:
            base = f"PU-{carte.slug(valeurs['nom'], 40)}"
            pid, n = base, 1
            while (_d() / f"{pid}.json").exists():
                n += 1
                pid = f"{base}_{n}"
            p.update(id=pid, cree=_maintenant(), auteur=_utilisateur())
            _journal(p, "création", detail=valeurs["nom"])
        for c, v in valeurs.items():
            if p.get(c) != v:
                if not creation:
                    _journal(p, "modification", champ=LIBELLES[c], avant=p.get(c), apres=v)
                p[c] = v
        p["modifie"] = _maintenant()
        _synchroniser_graphe(p)
        _ecrire(p)
    return obtenir(pid)


def dupliquer(pid: str, nom: str) -> dict:
    """Nouveau parcours avec le même cadrage (variante d'un parcours) ; les déroulés et les écrans ne sont pas repris."""
    p = _lire(pid)
    return enregistrer("", {"nom": nom, **{c: p.get(c) for c in ("objectif", "point_depart", "resultat_attendu", "exigences",
                                                                   "profil_donnees", "plateforme", "environnement", "pilote")}})


def archiver(pid: str, archive: bool = True, motif: str = "") -> dict:
    """Range ou restaure un parcours. Rien n'est supprimé : cadrage, déroulés et liens du Knowledge Graph sont gardés."""
    from atelier.domain import roles

    roles.exiger("construire")
    with _verrou:
        p = _lire(pid)
        if archive and statut(p) == "En cours":
            raise ValueError("Une session de ce parcours est en cours : la terminer avant d'archiver.")
        p["archive"] = bool(archive)
        _journal(p, "archivage" if archive else "restauration", detail=motif.strip()[:300])
        p["modifie"] = _maintenant()
        _ecrire(p)
    return obtenir(pid)


# --------------------------------------------------------------------------- déroulé (sessions Discovery)
def cadre_session(pid: str, app: str = "") -> dict:
    """Ce que le parcours apporte à la configuration d'une session Discovery (périmètre, point de départ, données)."""
    p = _lire(pid)
    if p.get("archive"):
        raise ValueError(f"Parcours {pid} archivé : le restaurer avant de le dérouler.")
    if app and p.get("app") != app:
        raise ValueError(f"Le parcours {pid} appartient à l'application « {p.get('app')} ».")
    return {"parcours": pid, "parcours_nom": p["nom"], "perimetre": p["nom"], "point_depart": p.get("point_depart", ""),
            "profil_donnees": p.get("profil_donnees", ""), "environnement": p.get("environnement", ""),
            "plateforme": p.get("plateforme", "")}


def rattacher_session(pid: str, sid: str):
    with _verrou:
        p = _lire(pid)
        if sid not in p["sessions"]:
            p["sessions"].append(sid)
            _journal(p, "déroulé lancé", detail=sid)
            p["modifie"] = _maintenant()
            _ecrire(p)


def session_terminee(s: dict) -> dict | None:
    """À la fin d'une session rattachée : les écrans traversés, dans l'ordre, sont proposés comme écrans du parcours
    (« contient », à valider). Un écran déjà validé ou rejeté pour ce parcours n'est pas reproposé."""
    from atelier.discovery import connaissance, sessions_discovery
    from atelier.domain import declarations

    pid = (s.get("config") or {}).get("parcours")
    if not pid:
        return None
    chemin = []
    for e in sessions_discovery.timeline(s["id"], 5000):
        if e.get("type") == "ecran" and e.get("ecran") and (not chemin or chemin[-1] != e["ecran"]):
            chemin.append(e["ecran"])
    with _verrou:
        p = _lire(pid)
        p["deroules"] = [d for d in p.get("deroules", []) if d.get("session") != s["id"]]
        p["deroules"].append({"session": s["id"], "date": s.get("fin") or _maintenant(), "chemin": chemin[:300]})
        source = f"déroulé du parcours « {p['nom']} » · session {s['id']}"
        relations = declarations.charger()["relations"]
        proposes = 0
        for eid in dict.fromkeys(chemin):
            if eid in p.get("ecrans_retires", []):
                continue
            try:
                nid_ecran = _noeud_ecran(eid)
            except KeyError:
                continue  # écran retiré de la carte entre-temps
            if eid not in p["ecrans"]:
                p["ecrans"].append(eid)
            if f"{p['noeud']}|contient|{nid_ecran}" not in relations:
                try:
                    declarations.ajouter_relation(p["noeud"], nid_ecran, "contient", auteur="ia", source=source)
                    proposes += 1
                except PermissionError:
                    p["ecrans"].remove(eid)  # lien rejeté auparavant : jamais reproposé
        _journal(p, "déroulé terminé", detail=f"{s['id']} · {len(set(chemin))} écran(s) traversé(s), {proposes} proposé(s) au parcours")
        p["modifie"] = _maintenant()
        _ecrire(p)
    connaissance.vider_cache()
    try:
        sessions_discovery._evenement(s["id"], {"type": "parcours", "detail": f"{p['nom']} : {proposes} écran(s) proposé(s) au parcours"})
    except OSError:
        pass
    return {"parcours": pid, "ecrans": len(p["ecrans"]), "proposes": proposes}


def valider(pid: str, ecrans: list[str] | None = None) -> dict:
    """Décision humaine : les écrans gardés deviennent les écrans officiels du parcours ; les autres sont retirés et ne
    seront plus reproposés. Sans liste, tous les écrans du déroulé sont gardés."""
    from atelier.discovery import connaissance
    from atelier.domain import declarations, roles

    roles.exiger("construire")
    with _verrou:
        p = _lire(pid)
        if not p.get("ecrans"):
            raise ValueError("Aucun écran à valider : dérouler d'abord le parcours sur un device ou un navigateur.")
        gardes = set(p["ecrans"]) if ecrans is None else {e for e in ecrans if e in p["ecrans"]}
        if not gardes:
            raise ValueError("Garder au moins un écran, ou archiver le parcours.")
        relations = declarations.charger()["relations"]
        retires = []
        for eid in list(p["ecrans"]):
            try:
                rid = _relation_ecran(p, eid)
            except KeyError:
                p["ecrans"].remove(eid)
                continue
            r = relations.get(rid)
            if eid in gardes:
                if r is None:
                    de, _, vers = rid.split("|")
                    declarations.ajouter_relation(de, vers, "contient", source=f"validation du parcours {pid} par {_utilisateur()}")
                elif r.get("statut") != "validé":
                    declarations.valider_relation(rid)
            else:
                if r is not None and r.get("statut") != "validé":
                    declarations.rejeter(rid, f"retiré du parcours {pid} à la validation")
                elif r is not None:
                    declarations.supprimer_relation(rid, "validé")
                p["ecrans"].remove(eid)
                p.setdefault("ecrans_retires", []).append(eid)
                retires.append(eid)
        p["valide"] = {"par": _utilisateur(), "date": _maintenant(), "ecrans": len(p["ecrans"])}
        _journal(p, "validation", detail=f"{len(p['ecrans'])} écran(s) gardé(s), {len(retires)} retiré(s)")
        p["modifie"] = _maintenant()
        _ecrire(p)
    connaissance.vider_cache()
    try:  # le comportement du parcours est compris dès sa validation (MBT, en arrière-plan, sans IA)
        from atelier.intelligence import mbt

        mbt.construire("parcours", p["noeud"])
    except Exception:  # noqa: BLE001 — l'analyse comportementale n'empêche jamais la validation du parcours
        pass
    return obtenir(pid)


# --------------------------------------------------------------------------- pour la corrélation et pour l'agent
def exigences_des_ecrans() -> dict:
    """{écran de la carte: {clé d'exigence: [noms des parcours]}} pour l'application active : les exigences d'un
    parcours sont des candidates prioritaires pour ses écrans (jamais un lien)."""
    from atelier.discovery import carte

    d = _d()
    fichiers = sorted(d.glob("PU-*.json")) if d.exists() else []
    app = carte.app_courante()
    cle = (str(d), app, tuple((f.name, f.stat().st_mtime_ns) for f in fichiers))
    if _index["cle"] != cle:
        index: dict = {}
        for p in _tous(app):
            if p.get("archive") or not p.get("exigences"):
                continue
            for eid in p.get("ecrans", []):
                for k in p["exigences"]:
                    index.setdefault(eid, {}).setdefault(k, []).append(p["nom"])
        _index.update(cle=cle, valeur=index)
    return _index["valeur"]


def demande_cursor(p: dict) -> str:
    """Demande précise à Cursor pour dérouler ce parcours (au lieu d'une demande générique d'exploration)."""
    pid = p["id"]
    return (f"Déroule avec moi le parcours utilisateur « {p['nom']} » ({pid}). Commence par discovery_parcours_cadre(\"{pid}\") : "
            "objectif, point de départ, résultat attendu, exigences avec leurs critères d'acceptation, profil de données et "
            f"variables prêtes. Ouvre la session (start_session{', plateforme ' + p['plateforme'] if p.get('plateforme') else ''}) "
            f"puis discovery_demarrer(parcours=\"{pid}\"). Avance écran par écran du point de départ au résultat attendu, sans "
            "t'écarter du parcours ; saisis par référence {{var:CLE}} ; propose ce que tu comprends (discovery_proposer) ; dis pour "
            "chaque écran traversé si les exigences du parcours le concernent (discovery_correlations_a_juger puis "
            "discovery_juger_correlations). Laisse-moi les actions sensibles, puis discovery_terminer.")


def cadre_agent(pid: str = "") -> dict:
    """Lecture seule, pour l'agent : sans identifiant, les parcours préparés ; sinon le cadrage complet du parcours.
    Aucune valeur de donnée n'est renvoyée (les saisies passent par les références {{var:CLE}})."""
    if not pid:
        return {"parcours": [{k: x[k] for k in ("id", "nom", "statut", "exigences", "profil_donnees", "plateforme", "environnement")}
                             for x in lister()]}
    v = obtenir(pid)
    return {"id": v["id"], "nom": v["nom"], "statut": v["statut"], "objectif": v["objectif"], "point_depart": v["point_depart"],
            "resultat_attendu": v["resultat_attendu"], "plateforme": v["plateforme"], "environnement": v["environnement"],
            "exigences": [{k: x.get(k) for k in ("cle", "type", "resume", "description", "criteres")} for x in v["exigences"] if not x["absente"]],
            "donnees": v["donnees"], "ecrans_deja_traverses": [e["nom"] for e in v["ecrans"]],
            "consigne": "Reste dans ce parcours : du point de départ au résultat attendu. Les exigences listées sont celles que le "
                        "parcours réalise ; le lien écran ↔ exigence reste une proposition que l'automaticien confirme."}
