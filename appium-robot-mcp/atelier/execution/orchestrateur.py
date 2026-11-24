"""Orchestrateur des travaux IA / MCP : l'atelier tient le plan, l'agent n'exécute que des étapes courtes.

Un travail (lancé d'un clic : suggestion du graphe…) est une suite d'étapes typées :
  - atelier  : déterministe, sans IA (brouillon BDD, dry-run, run réel) ; un run passe par la file d'exécution de
               l'atelier (historique, revue, suivi en direct), sur un téléphone libre ;
  - ia       : une demande courte à un agent (Claude Code ou Cursor, selon l'étape), terminée quand il en rend compte ;
  - humain   : une décision (valider le BDD, approuver la revue) ; elle n'arrête que son travail.
L'utilisateur n'attend jamais : tout avance en arrière-plan, l'état est écrit sur disque (reprise après redémarrage),
et chaque étape est visible (panneau « Mes travaux », fiche du graphe, popups).

Ressources : un téléphone par run (réservé le temps du run) ; les étapes IA et les décisions n'en prennent pas, elles
avancent pendant qu'un autre travail occupe un téléphone. Charge : une boucle légère (un fichier relu toutes les
3 s, rien d'autre tant qu'aucun travail n'est actif) ; aucun calcul dans les requêtes de l'interface.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime

ETATS = ("a_faire", "en_cours", "attente_ressource", "attente_decision", "fait", "echec", "annule")
PERIODE_S = 3.0
MAX_TENTATIVES_RUN = 1

_verrou = threading.RLock()
_fil: dict = {"thread": None, "stop": threading.Event()}
# branchements fournis par l'adapter web (comme FileExecution.executer) : jamais d'import d'adapter ici
HOOKS: dict = {"mettre_en_file": None, "emit": None}
_reservations: dict = {}  # udid -> id du travail qui l'occupe


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _fichier():
    from atelier.domain import projet

    return projet.PROJECT_DIR / "orchestration" / "travaux.json"


def _lire() -> list[dict]:
    f = _fichier()
    try:
        return json.loads(f.read_text("utf-8")) if f.exists() else []
    except (OSError, json.JSONDecodeError):
        return []


def _ecrire(l: list[dict]):
    f = _fichier()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(l[-200:], ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, f)


def _emettre(t: dict, etape: dict | None = None):
    if HOOKS.get("emit"):
        try:
            HOOKS["emit"]({"type": "travail", "id": t["id"], "titre": t["titre"], "statut": t["statut"],
                           "etape": etape and {k: etape.get(k) for k in ("id", "titre", "type", "statut", "agent")}})
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- création et décisions
def creer(titre: str, etapes: list[dict], origine: dict | None = None, env: str = "", plateforme: str = "android") -> dict:
    """Crée un travail. etapes : [{titre, type (atelier|ia|humain), action, params, agent}] dans l'ordre."""
    if not etapes:
        raise ValueError("Un travail a au moins une étape.")
    t = {"id": "TR-" + uuid.uuid4().hex[:8], "titre": " ".join(str(titre).split())[:160], "cree": _maintenant(),
         "statut": "en_cours", "env": env, "plateforme": plateforme, "origine": origine or {}, "contexte": {},
         "etapes": [{"id": f"E{i + 1}", "titre": e["titre"], "type": e["type"], "action": e.get("action", ""),
                     "params": e.get("params") or {}, "agent": e.get("agent", ""), "statut": "a_faire", "debut": "",
                     "fin": "", "resultat": "", "erreur": "", "tentatives": 0} for i, e in enumerate(etapes)]}
    t["contexte"]["travail"] = t["id"]
    for e in t["etapes"]:  # une clé BDD connue d'avance (scénario existant) est dans le contexte dès le départ
        if e["params"].get("bdd"):
            t["contexte"]["bdd"] = e["params"]["bdd"]
    if any(e["type"] not in ("atelier", "ia", "humain") for e in t["etapes"]):
        raise ValueError("Type d'étape : atelier, ia ou humain.")
    with _verrou:
        l = _lire()
        l.append(t)
        _ecrire(l)
    demarrer()
    _emettre(t)
    return t


def lister(actifs_seulement: bool = False) -> list[dict]:
    l = list(reversed(_lire()))
    return [t for t in l if t["statut"] == "en_cours"] if actifs_seulement else l


def obtenir(tid: str) -> dict:
    t = next((x for x in _lire() if x["id"] == tid), None)
    if not t:
        raise KeyError(f"Travail inconnu : {tid}")
    return t


def _modifier(tid: str, fn) -> dict:
    with _verrou:
        l = _lire()
        t = next((x for x in l if x["id"] == tid), None)
        if not t:
            raise KeyError(f"Travail inconnu : {tid}")
        fn(t)
        _ecrire(l)
    return t


def decider(tid: str, etape: str, accepter: bool, commentaire: str = "") -> dict:
    """Décision humaine sur une étape « humain » en attente : la suite reprend (ou le travail s'arrête si refus)."""
    def f(t):
        e = next((x for x in t["etapes"] if x["id"] == etape), None)
        if not e or e["type"] != "humain" or e["statut"] != "attente_decision":
            raise ValueError("Aucune décision attendue sur cette étape.")
        e.update(statut="fait" if accepter else "echec", fin=_maintenant(),
                 resultat=("accepté" if accepter else "refusé") + (f" : {commentaire}" if commentaire else ""))
        if not accepter:
            t["statut"] = "arrete"
    t = _modifier(tid, f)
    e = next(x for x in t["etapes"] if x["id"] == etape)
    if accepter and e.get("action") == "publier_xray":  # flux simple : la décision est la publication (hors verrou : Xray)
        t = _publier_xray(tid, e)
    _emettre(t)
    return t


def _publier_xray(tid: str, e: dict) -> dict:
    """Publie le scénario BDD du travail dans Xray (generation/flux.publier) ; un échec laisse l'étape en échec, à reprendre."""
    from atelier.generation import flux

    t = obtenir(tid)
    cle = (e.get("params") or {}).get("bdd") or (t.get("contexte") or {}).get("bdd")
    try:
        if not cle:
            raise ValueError("aucun scénario BDD dans ce travail")
        r = flux.publier([cle])
        if r["erreurs"]:
            raise ValueError("; ".join(f"{x['scenario']} : {x['erreur']}" for x in r["erreurs"]))
        texte, erreur = "publié dans Xray : " + ", ".join(x["xray"] or x["scenario"] for x in r["publies"]), ""
    except Exception as ex:  # noqa: BLE001 - Xray indisponible, contrôle bloquant… : dit sur l'étape
        texte, erreur = "", f"Publication impossible : {str(ex)[:300]}"

    def maj(t):
        x = next(y for y in t["etapes"] if y["id"] == e["id"])
        x.update(statut="echec" if erreur else "fait", resultat=texte, erreur=erreur)
        if erreur:
            t["statut"] = "echec"
    return _modifier(tid, maj)


def reprendre(tid: str) -> dict:
    """Relance un travail en échec (ou arrêté) depuis l'étape en échec : les étapes faites ne sont pas refaites."""
    def f(t):
        if t["statut"] not in ("echec", "arrete"):
            raise ValueError("Seul un travail en échec ou arrêté se reprend.")
        e = next((x for x in t["etapes"] if x["statut"] == "echec"), None)
        if e:
            e.update(statut="a_faire", erreur="", resultat="repris", fin="", erreurs_internes=0)
            for k in ("run_id", "demande", "trace", "telephone"):
                e.pop(k, None)
        t["statut"] = "en_cours"
        t.pop("fin", None)
    t = _modifier(tid, f)
    demarrer()
    _emettre(t)
    return t


def annuler(tid: str) -> dict:
    def f(t):
        t["statut"] = "annule"
        for e in t["etapes"]:
            if e["statut"] in ("a_faire", "attente_ressource", "attente_decision"):
                e["statut"] = "annule"
    t = _modifier(tid, f)
    _liberer(tid)
    _retirer_demandes(t)
    _emettre(t)
    return t


def _retirer_demandes(t: dict):
    """Demandes à l'agent de ce travail encore dans la boîte : retirées (sinon l'agent ferait un travail annulé)."""
    from atelier.integrations import boite_cursor

    for d in boite_cursor.etat(200)["demandes"]:
        if d.get("travail") == t["id"] and d.get("statut") == "en attente":
            try:
                boite_cursor.annuler(d["id"])
            except (KeyError, ValueError):
                pass


# --------------------------------------------------------------------------- ressources : téléphones
def telephones(plateforme: str = "android") -> list[str]:
    """Téléphones de la plateforme, dans l'ordre : Android branchés (adb) ; iOS (macOS) : iPhone branchés puis simulateurs
    démarrés. Vide si l'outil du système est indisponible."""
    try:
        from atelier.discovery import session

        d = session.list_devices()
        if plateforme == "ios":
            return list(d.get("ios_physiques", [])) + [s["udid"] for s in d.get("ios_simulateurs", [])]
        return [x["udid"] for x in d.get("android", [])]
    except Exception:  # noqa: BLE001
        return []


def _reserver(tid: str, plateforme: str = "android") -> str:
    with _verrou:
        libres = [u for u in telephones(plateforme) if u not in _reservations]
        if not libres:
            return ""
        _reservations[libres[0]] = tid
        return libres[0]


def _liberer(tid: str):
    with _verrou:
        for u in [u for u, x in _reservations.items() if x == tid]:
            del _reservations[u]


# --------------------------------------------------------------------------- moteur
def demarrer():
    """Lance la boucle de l'orchestrateur (une seule, légère) si elle ne tourne pas."""
    with _verrou:
        th = _fil["thread"]
        if th and th.is_alive():
            return
        _fil["stop"].clear()
        _fil["thread"] = threading.Thread(target=_boucle, name="orchestrateur", daemon=True)
        _fil["thread"].start()


def arreter():
    _fil["stop"].set()


def _boucle():
    while not _fil["stop"].is_set():
        try:
            if not avancer():
                with _verrou:  # relu sous verrou : un travail créé pendant ce tour relance la boucle au lieu d'attendre
                    if not any(x["statut"] == "en_cours" for x in _lire()):
                        _fil["thread"] = None
                        return  # plus aucun travail actif : la boucle s'arrête, elle repart au prochain travail
        except Exception:  # noqa: BLE001 — une erreur d'un tour n'arrête jamais l'orchestrateur
            pass
        _fil["stop"].wait(PERIODE_S)


def avancer() -> bool:
    """Un tour : fait progresser chaque travail actif d'une étape au plus. Rend True s'il reste des travaux actifs."""
    actifs = [t["id"] for t in _lire() if t["statut"] == "en_cours"]
    for tid in actifs:
        try:
            _avancer_travail(tid)
        except Exception as ex:  # noqa: BLE001 — l'erreur est écrite sur l'étape (jamais avalée), les autres travaux continuent
            import traceback

            detail = f"{type(ex).__name__} : {ex}"[:400]
            def noter(x, detail=detail, pile=traceback.format_exc()[-1200:]):
                e = next((s for s in x["etapes"] if s["statut"] not in ("fait", "annule")), None)
                if e:
                    e["erreurs_internes"] = e.get("erreurs_internes", 0) + 1
                    e["resultat"] = f"erreur interne ({e['erreurs_internes']}) : {detail}"
                    e["trace"] = pile
                    if e["erreurs_internes"] >= 3:  # pas de boucle infinie : l'étape échoue avec la cause
                        e.update(statut="echec", erreur=detail, fin=_maintenant())
            _modifier(tid, noter)
    return any(t["statut"] == "en_cours" for t in _lire())


def _avancer_travail(tid: str):
    t = obtenir(tid)
    e = next((x for x in t["etapes"] if x["statut"] not in ("fait", "annule")), None)
    if e is None:
        _modifier(tid, lambda x: x.update(statut="termine", fin=_maintenant()))
        _liberer(tid)
        _emettre(obtenir(tid))
        return
    if e["statut"] == "echec":
        _modifier(tid, lambda x: x.update(statut="echec", fin=_maintenant()))
        _liberer(tid)
        _emettre(obtenir(tid))
        return
    avant = (e["statut"], e["resultat"])
    {"atelier": _etape_atelier, "ia": _etape_ia, "humain": _etape_humaine}[e["type"]](t, e)
    if (e["statut"], e["resultat"]) != avant:
        def maj(x):
            y = next(s for s in x["etapes"] if s["id"] == e["id"])
            y.update(e)
            x["contexte"] = t["contexte"]
        _modifier(tid, maj)
        _emettre(obtenir(tid), e)


def _etape_humaine(t: dict, e: dict):
    if e["statut"] == "a_faire":
        e.update(statut="attente_decision", debut=_maintenant())


def _etape_ia(t: dict, e: dict):
    from atelier.integrations import boite_cursor

    if e["statut"] == "a_faire":
        texte = e["params"].get("texte", "")
        for k, v in t["contexte"].items():  # ce que les étapes précédentes ont produit (clé BDD, fichier…)
            texte = texte.replace("{" + k + "}", str(v))
        # mode réglé pour le projet (ligne de commande : l'agent est lancé tout de suite) ; la boîte si le lien est réglé
        # (un lien profond ne sert pas un travail en arrière-plan), ou si l'agent n'est pas prêt en ligne de commande
        mode = "boite" if boite_cursor.envoi() == "lien" else ""
        d = boite_cursor.deposer(e["titre"], texte, attendus=e["params"].get("attendus") or [], ecran=t["origine"].get("ecran", ""),
                                 mode=mode, prioritaire=True, agent=e.get("agent", ""), travail=t["id"])
        e.update(statut="en_cours", debut=_maintenant(), resultat=f"demande {d['id']} déposée pour {e.get('agent') or 'l’agent'}",
                 demande=d["id"])
        return
    d = next((x for x in boite_cursor.etat(200)["demandes"] if x["id"] == e.get("demande")), None)
    if not d:
        e.update(statut="echec", erreur="demande introuvable dans la boîte", fin=_maintenant())
    elif d["statut"] == "terminée":
        e.update(statut="fait", fin=_maintenant(), resultat=str(d.get("resultat") or "terminée")[:600])
    elif d["statut"] in ("échouée", "annulée"):
        e.update(statut="echec", fin=_maintenant(), erreur=str(d.get("erreur") or d["statut"])[:600])
    elif d["statut"] == "prise" and "prise" not in e["resultat"]:
        e["resultat"] = f"demande {d['id']} prise par l’agent"
    elif d["statut"] == "en attente" and boite_cursor.relancer(d["id"]):  # l'agent est devenu prêt (connexion faite) : elle part
        e["resultat"] = f"demande {d['id']} lancée en ligne de commande"


def _tests_du_bdd(*tags: str) -> list[str]:
    """Tests Robot qui portent en tag la clé du scénario BDD, sa clé Xray (après publication, le tag local est remplacé
    par la clé du test Xray) ou l'identifiant du travail (consigne donnée à l'agent)."""
    from atelier.execution import depot_robot

    inv = depot_robot.lire_depot()
    voulus = {x for x in tags if x}
    try:
        from atelier.generation import conception

        voulus |= {conception.cle_xray_du_scenario(x) for x in list(voulus)} - {""}
    except Exception:  # noqa: BLE001 — publications illisibles : les tags locaux suffisent
        pass
    return [i for i, x in inv["tests"].items() if voulus & set(x.get("tags") or [])]


def _etape_atelier(t: dict, e: dict):
    a = e["action"]
    if a == "brouillon_bdd":
        from atelier.generation import parcours_bdd

        p = e["params"]
        try:
            r = parcours_bdd.brouillon(ecrans=p["ecrans"], titre=p["titre"]) if p.get("ecrans") \
                else parcours_bdd.brouillon(parcours=p["parcours"], titre=p["titre"])
            cle = r["cle"]
        except parcours_bdd.DejaCouvert as x:
            cle = x.existant["cle"]
        t["contexte"]["bdd"] = cle
        e.update(statut="fait", debut=e["debut"] or _maintenant(), fin=_maintenant(), resultat=f"scénario {cle}")
        return
    if a in ("dry_run", "run"):
        _etape_run(t, e, dry_run=a == "dry_run")
        return
    e.update(statut="echec", erreur=f"action inconnue : {a}", fin=_maintenant())


def _etape_run(t: dict, e: dict, dry_run: bool):
    from atelier.execution import historique

    if e["statut"] in ("a_faire", "attente_ressource"):
        if not HOOKS.get("mettre_en_file"):
            e.update(statut="attente_ressource", resultat="file d'exécution indisponible (atelier non démarré)")
            return
        cle = t["contexte"].get("bdd") or e["params"].get("bdd", "")
        tests = list(e["params"].get("tests") or []) or _tests_du_bdd(cle, t["id"])  # tests donnés (rejeu d'un sujet), sinon ceux du scénario
        if not tests:
            e.update(statut="echec", fin=_maintenant(), erreur=f"aucun test Robot ne porte le tag {cle or t['id']} : l'automatisation n'a pas abouti")
            return
        udid = "" if dry_run else _reserver(t["id"], t.get("plateforme") or "android")
        if not dry_run and not udid:
            e.update(statut="attente_ressource", resultat="en attente d'un téléphone libre")
            return
        from atelier.execution import robot

        sel = robot.selection_tests(tests)
        variables = {"PLATFORM": t.get("plateforme") or "android", **({"UDID": udid} if udid else {})}
        params = {"target": sel["cible"], "tests": tests, "dry_run": dry_run, "variables": variables,
                  "jdd_env": t.get("env") or "", "xray_mode": "aucun"}
        extra = dict(e["params"].get("run_params") or {})  # exécution TNR : Test Execution du plan TNR, transitions Jira
        if extra.get("xray_ticket") and not dry_run:
            params.pop("xray_mode")
        params.update({k: v for k, v in extra.items() if v})
        r = HOOKS["mettre_en_file"](params, "High", "", f"{t['titre']} · {'dry-run' if dry_run else 'run'}")
        e.update(statut="en_cours", debut=_maintenant(), run_id=r["run_id"], telephone=udid,
                 resultat=f"{'dry-run' if dry_run else 'run'} {r['run_id']} en file" + (f" sur {udid}" if udid else ""))
        t["contexte"]["tests"] = tests
        if not t["contexte"].get("bdd"):  # scénario créé par l'agent : retrouvé par les tags du test (lien dans « Mes travaux »)
            try:
                from atelier.execution import depot_robot
                from atelier.generation import bdd

                tags = {g for x in tests for g in depot_robot.lire_depot()["tests"].get(x, {}).get("tags", [])}
                cle = next((b["cle"] for b in bdd.lister() if b["cle"] in tags), "")
                if cle:
                    t["contexte"]["bdd"] = cle
            except Exception:  # noqa: BLE001
                pass
        return
    run = next((x for x in historique.lister(30) if x["id"] == e.get("run_id")), None)
    if not run or run["statut"] == "en cours":
        return
    if not dry_run:
        _liberer(t["id"])
    if run["statut"] == "réussi":
        e.update(statut="fait", fin=_maintenant(), resultat=f"{run['id']} : {run.get('passes') or 0} réussi(s)")
    else:
        e.update(statut="echec", fin=_maintenant(), erreur=f"{run['id']} : {run['statut']}"
                 + (f" ({run.get('echecs')} échec(s))" if run.get("echecs") else "") + (f" — {run['erreur']}" if run.get("erreur") else ""))


def reprendre_au_demarrage():
    """Après un redémarrage : les réservations en mémoire sont perdues, les runs en cours sont relus dans l'historique ;
    la boucle repart s'il reste des travaux actifs. Un run réel encore en cours garde son téléphone (pas de second run dessus)."""
    with _verrou:
        for t in _lire():
            for e in t["etapes"] if t["statut"] == "en_cours" else []:
                if e["statut"] == "en_cours" and e.get("telephone"):
                    _reservations[e["telephone"]] = t["id"]
    if any(t["statut"] == "en_cours" for t in _lire()):
        demarrer()
