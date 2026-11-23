"""Suivi en direct d'une exécution, tenu côté serveur.

Avant, l'état « en direct » n'existait que dans le navigateur, construit à partir des événements reçus pendant que l'écran
était ouvert : une page ouverte après le début du run, ou rechargée, ne montrait rien. Ici, l'atelier garde l'état du run
en cours à partir des mêmes événements (run_lance, run_debut, test_debut, kw_debut, kw_fin, test_fin, run_bilan, émis
par la file d'exécution et par le listener Robot), et l'écran le relit à tout moment.

Ce qui est suivi, pour le run en cours : chaque test (en attente, en cours, réussi, en échec, ignoré), sa durée, son
message d'échec et le keyword fautif ; l'étape BDD et le keyword en cours (trois niveaux au plus, comme le listener).
Les arguments des keywords sont ceux écrits dans le script (${JDD}[mot_de_passe]), jamais les valeurs résolues.
"""
from __future__ import annotations

import threading
import time

_VERROU = threading.Lock()
_RUN: dict | None = None
_DERNIER: dict | None = None

STATUTS = {"PASS": "réussi", "FAIL": "échec", "SKIP": "ignoré", "NOT RUN": "ignoré"}


def _maintenant() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _test(nom: str, fichier: str = "") -> dict:
    return {"nom": nom, "fichier": fichier, "statut": "en attente", "debut": "", "fin": "", "duree_s": None,
            "message": "", "keyword_en_echec": ""}


def _secondes(debut: str, fin: str) -> float | None:
    try:
        return round(time.mktime(time.strptime(fin[:19], "%Y-%m-%dT%H:%M:%S"))
                     - time.mktime(time.strptime(debut[:19], "%Y-%m-%dT%H:%M:%S")), 1)
    except (ValueError, TypeError):
        return None


def demarrer(run_id: str, suite: str = "", tests: list[str] | None = None, nom: str = "") -> None:
    """Un run démarre (file d'exécution). tests : identifiants « fichier::nom » quand ils sont connus d'avance
    (Tests automatisés › Vérifier) : ils s'affichent « en attente » avant même que Robot ne démarre."""
    global _RUN
    with _VERROU:
        _RUN = {"id": run_id or "", "suite": suite or "", "nom": nom or "", "debut": _maintenant(), "statut": "en cours",
                "tests": {}, "courant": "", "etape": "", "keyword": "", "keyword_debut": ""}
        for i in tests or []:
            fichier, _, n = str(i).partition("::")
            if n:
                _RUN["tests"][n] = _test(n, fichier)


def observer(ev: dict) -> None:
    """Met à jour l'état à partir d'un événement de l'atelier (les autres types sont ignorés)."""
    global _RUN, _DERNIER
    t = ev.get("type")
    if t == "run_lance":
        if not _RUN or (ev.get("run_id") and _RUN.get("id") != ev.get("run_id")):
            demarrer(ev.get("run_id") or "", ev.get("suite") or "")
        return
    with _VERROU:
        r = _RUN
        if t == "run_bilan":
            if r:
                b = ev.get("bilan") or {}
                r["statut"] = "erreur" if b.get("statut") in ("erreur", "bloqué données") or ("resultat" not in b and b) \
                    else "terminé"
                r["erreur"] = str(b.get("erreur") or b.get("conseil") or "")[:300]
                r["fin"], r["courant"], r["etape"], r["keyword"] = _maintenant(), "", "", ""
                for x in r["tests"].values():  # jamais exécutés (run interrompu, erreur de lancement)
                    if x["statut"] in ("en attente", "en cours"):
                        x["statut"] = "non exécuté"
                _DERNIER, _RUN = r, None
            return
        if not r:
            return
        if t == "run_debut":
            for x in ev.get("tests") or []:
                r["tests"].setdefault(x.get("nom", ""), _test(x.get("nom", "")))
        elif t == "test_debut":
            x = r["tests"].setdefault(ev.get("nom", ""), _test(ev.get("nom", "")))
            x.update(statut="en cours", debut=_maintenant())
            r.update(courant=x["nom"], etape="", keyword="", keyword_debut="")
        elif t == "kw_debut":
            nom, niveau = ev.get("nom", ""), int(ev.get("niveau") or 1)
            if niveau == 1:
                r["etape"] = nom
            r.update(keyword=nom, keyword_debut=_maintenant())
        elif t == "test_fin":
            x = r["tests"].setdefault(ev.get("nom", ""), _test(ev.get("nom", "")))
            fin = _maintenant()
            x.update(statut=STATUTS.get(ev.get("statut", ""), str(ev.get("statut", "")).lower()), fin=fin,
                     duree_s=_secondes(x["debut"], fin), message=str(ev.get("message") or "")[:500],
                     keyword_en_echec=str(ev.get("keyword_en_echec") or "")[:300])
            if r["courant"] == x["nom"]:
                r.update(courant="", etape="", keyword="")


def _copie(r: dict | None) -> dict | None:
    if not r:
        return None
    tests = list(r["tests"].values())
    compte = {k: sum(1 for x in tests if x["statut"] == k) for k in ("en attente", "en cours", "réussi", "échec", "ignoré")}
    return {**{k: v for k, v in r.items() if k != "tests"}, "tests": tests, "compte": compte, "total": len(tests),
            "termines": compte["réussi"] + compte["échec"] + compte["ignoré"]}


def etat() -> dict:
    """Run en cours (ou None) et dernier run suivi (jusqu'au prochain)."""
    with _VERROU:
        return {"en_cours": _copie(_RUN), "dernier": _copie(_DERNIER)}


def reinitialiser() -> None:
    """Tests uniquement."""
    global _RUN, _DERNIER
    with _VERROU:
        _RUN = _DERNIER = None


def vue(run_id: str = "") -> dict:
    """Tout ce que l'écran Exécution affiche : le run en cours (tests, étape et keyword courants), la file d'attente,
    les dernières exécutions, et le run demandé s'il est terminé (tests lus dans son output.xml)."""
    from atelier.execution import centre, historique

    e = etat()
    choisi = None
    if run_id and not (e["en_cours"] and e["en_cours"]["id"] == run_id):
        try:
            d = historique.detail(run_id)
        except (KeyError, ValueError):
            d = None
        if d:
            b = d.get("bilan") or {}
            tests = [{"nom": t["nom"], "fichier": t.get("suite", ""), "statut": STATUTS.get(t["statut"], t["statut"].lower()),
                      "duree_s": t.get("duree_s"), "message": t.get("message", ""), "keyword_en_echec": ""} for t in d["tests"]]
            resume = next((x for x in historique.lister(200) if x["id"] == run_id), {})
            choisi = {"id": run_id, "suite": (d.get("params") or {}).get("target", ""), "debut": d.get("debut"), "fin": d.get("fin"),
                      "statut": resume.get("statut", ""), "erreur": str(b.get("erreur") or b.get("conseil") or "")[:300],
                      "tests": tests, "total": len(tests),
                      "compte": {k: sum(1 for x in tests if x["statut"] == k) for k in ("réussi", "échec", "ignoré")}}
    return {"en_cours": e["en_cours"], "file": centre.FILE.attente(), "run": choisi,
            "recents": [{k: r.get(k) for k in ("id", "suite", "debut", "fin", "statut", "passes", "echecs", "erreur")}
                        for r in historique.lister(10)]}
