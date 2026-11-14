"""Navigation et exploration guidées par la carte : aller sur un écran connu en rejouant le chemin
le plus fiable, explorer automatiquement l'application.

Invariants (testés) : l'exploration ne saisit jamais de texte, ne coche jamais de case, ne touche
aucune action de la liste rouge et ignore les liens externes.
"""
from __future__ import annotations

import threading
import time
from urllib.parse import urlparse

from atelier.discovery import actions, carte, session
from atelier.discovery.observation import attendre_stable, carte_active, observer
from atelier.domain import evenements


def rejouer(t: dict) -> bool:
    a, plat, m = t["action"], session.etat["platform"], carte
    try:
        if a["type"] == "press_back":
            session.back_raw()
        elif a["type"] == "open_url":
            session.webb().goto(a["url"])
        elif a["type"] == "swipe":
            actions.swipe(a.get("direction", "up"))
        else:
            candidats = []
            if a.get("cle"):
                try:
                    candidats = (m.ecran(t["de"]).get("elements", {}).get(a["cle"], {}).get("locators", {})
                                 .get(plat) or [])
                except KeyError:
                    pass
            candidats = list(dict.fromkeys(candidats + ([a["locator"]] if a.get("locator") else [])))
            loc = next((c for c in candidats if session.present(c)), None)
            if not loc:
                return False
            session.montrer_cible(loc, "navigation")
            session.click_raw(loc)
        return True
    except Exception:
        return False


def relancer_app():
    cfg = carte.config_app()
    plat = session.etat["platform"]
    if plat == "web":
        if cfg.get("web", {}).get("url"):
            session.webb().goto(cfg["web"]["url"])
        return
    ident = cfg.get(plat, {}).get("app_package" if plat == "android" else "bundle_id")
    if ident:
        try:
            session.driver().terminate_app(ident)
        except Exception:
            pass
        session.driver().activate_app(ident)
        time.sleep(2)


def aller(cible_id: str, max_essais: int = 3) -> dict:
    m, plat = carte, session.etat["platform"]
    cur = None
    for essai in range(max_essais):
        cur = observer(attendre_stable(3))
        if not cur:
            return {"arrive": False, "raison": "Carte inactive (aucune application ou session)."}
        if cur["id"] == cible_id:
            return {"arrive": True, "ecran": cur, "essais": essai + 1}
        trajet = m.chemin(cur["id"], cible_id, plat)
        if trajet is None:
            for _ in range(2):  # rattrapage : retour puis nouvel essai de calcul
                session.back_raw()
                cur = observer(attendre_stable(3))
                if cur and m.chemin(cur["id"], cible_id, plat) is not None:
                    break
            else:
                relancer_app()
            continue
        for t in trajet:
            evenements.publier({"type": "navigation", "transition": t["id"], "de": t["de"], "vers": t["vers"]})
            ok = rejouer(t)
            arrive = observer(attendre_stable(4))
            bon = ok and arrive and arrive["id"] == t["vers"]
            m.noter(t["id"], bool(bon))
            if not bon:
                break
        else:
            return {"arrive": True, "ecran": observer(), "essais": essai + 1}
    return {"arrive": False, "raison": "Chemin non rejouable pour l'instant", "ecran_courant": cur}


EXPLO = {"stop": threading.Event(), "en_cours": False}


def explorer(max_ecrans: int = 25, profondeur: int = 3, duree_max_s: int = 900) -> dict:
    """Parcours en largeur : touche les éléments cliquables (hors liste rouge), enregistre chaque écran
    et chaque transition, puis revient. Ne saisit jamais de texte, n'active jamais de case."""
    m, plat = carte, session.etat["platform"]
    if not carte_active():
        raise RuntimeError("Ouvre une session et choisis une application avant d'explorer.")
    EXPLO["stop"].clear()
    EXPLO["en_cours"] = True
    t0 = time.time()
    depart = observer(attendre_stable())
    hote = urlparse(session.webb().info()["url"]).netloc if session.is_web() else ""
    file, vus = [(depart["id"], 0)], {depart["id"]}
    bilan = {"ecrans_visites": 1, "nouveaux": 0, "transitions": 0, "ignores_liste_rouge": 0, "journal": []}
    try:
        while file and not EXPLO["stop"].is_set() and time.time() - t0 < duree_max_s and len(vus) <= max_ecrans:
            eid, prof = file.pop(0)
            if prof >= profondeur or not aller(eid)["arrive"]:
                continue
            for t in m.transitions():  # poursuit aussi vers les écrans déjà connus depuis celui-ci
                if t["de"] == eid and t["plateforme"] == plat and not t.get("interdite") and t["vers"] not in vus:
                    vus.add(t["vers"])
                    file.append((t["vers"], prof + 1))
            deja = m.actions_depuis(eid, plat)
            candidats = []
            for el in session.current_elements(150):
                if el.get("type") not in ("bouton", "lien", "element", "liste"):
                    continue
                if m.interdit(el):
                    bilan["ignores_liste_rouge"] += 1
                    continue
                if el["key"] not in deja and el["locators"][0] not in deja:
                    candidats.append(el)
            for el in candidats[:15]:
                if EXPLO["stop"].is_set() or time.time() - t0 > duree_max_s or len(vus) > max_ecrans:
                    break
                if not aller(eid)["arrive"]:
                    break
                loc = el["locators"][0]
                try:
                    session.montrer_cible(loc, "exploration")
                    session.click_raw(loc, 3)
                except Exception:
                    m.marquer_essaye(eid, plat, el["key"])
                    continue
                if session.is_web() and urlparse(session.webb().info()["url"]).netloc != hote:  # lien externe
                    session.back_raw()
                    m.marquer_essaye(eid, plat, el["key"])
                    continue
                obs = observer(attendre_stable())
                if obs["id"] == eid:
                    m.marquer_essaye(eid, plat, el["key"])
                    continue
                m.enregistrer_transition(eid, obs["id"], plat, {"type": "tap", "cle": el["key"], "locator": loc,
                                                                "libelle": el.get("libelle", "")}, source="exploration")
                bilan["transitions"] += 1
                bilan["nouveaux"] += 1 if obs["nouveau"] else 0
                if obs["id"] not in vus:
                    vus.add(obs["id"])
                    file.append((obs["id"], prof + 1))
                msg = f"{el.get('libelle') or el['key']} → {obs.get('nom') or obs.get('titre') or obs['id']}"
                bilan["journal"].append(msg)
                evenements.publier({"type": "exploration", "message": msg, "nb_ecrans": len(vus), "nouveau": obs["nouveau"]})
    finally:
        EXPLO["en_cours"] = False
        bilan["ecrans_visites"] = len(vus)
        bilan["duree_s"] = int(time.time() - t0)
        bilan["arret"] = "demandé" if EXPLO["stop"].is_set() else "terminé"
        evenements.publier({"type": "exploration", "fin": True, "bilan": {k: v for k, v in bilan.items() if k != "journal"}})
    return bilan


def stop_exploration() -> str:
    EXPLO["stop"].set()
    return "Arrêt demandé."


def where_am_i() -> dict:
    obs = observer(attendre_stable(3))
    if not obs:
        raise RuntimeError("Carte inactive : ouvre une session et choisis une application.")
    return {**obs, **carte.resume_ecran(carte.ecran(obs["id"]))}


def goto_screen(ecran: str) -> dict:
    cible = carte.ecran(ecran)
    return aller(cible["id"])
