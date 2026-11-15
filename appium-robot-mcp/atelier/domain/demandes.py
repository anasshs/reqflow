"""Demandes d'action en attente de validation humaine (V2, phase 0 bis).

Un outil MCP qui écrirait dans Jira / Xray ou modifierait la carte sans retour possible n'agit plus directement :
il dépose une DEMANDE, que l'automaticien accepte ou rejette dans l'atelier (Application Intelligence › À valider).
La validation est imposée côté serveur : les règles Cursor la décrivent, elles ne sont jamais le seul garde-fou.

Stockage : <projet>/validations/demandes.json (état de travail de l'atelier, isolé par projet). Chaque demande
garde son historique (création, décision, exécution, erreur). Une demande identique déjà en attente n'est pas
dupliquée (idempotence). L'exécution n'a lieu qu'une fois, à l'acceptation.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime

from atelier.domain import evenements, projet

STATUTS = ("en attente", "exécutée", "échec", "rejetée")
TYPES = {
    "jira_transition": "Transition d'un ticket Jira",
    "import_results_to_xray": "Import de résultats Robot dans Xray",
    "qualify_failure": "Qualification d'un test run Xray (commentaire)",
    "fusion_ecrans": "Fusion de deux écrans de la carte",
    "remplacer_locator": "Remplacement d'un locator capturé",
}


def _fichier():
    return projet.PROJECT_DIR / "validations" / "demandes.json"


def _lire() -> list[dict]:
    f = _fichier()
    try:
        return json.loads(f.read_text("utf-8")) if f.exists() else []
    except (OSError, ValueError):
        return []


def _ecrire(l: list[dict]):
    from atelier.intelligence.strategie import _ecrire_atomique

    _fichier().parent.mkdir(parents=True, exist_ok=True)
    _ecrire_atomique(_fichier(), json.dumps(l, ensure_ascii=False, indent=1, default=str))


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _auteur() -> str:
    from atelier.domain import roles

    return roles.utilisateur()


def creer(type_: str, params: dict, resume: str, origine: str = "cursor", apercu: dict | None = None) -> dict:
    """Dépose une demande (aucune action exécutée). Une demande identique en attente est renvoyée telle quelle."""
    if type_ not in TYPES:
        raise ValueError(f"Type de demande inconnu : {type_} ({', '.join(TYPES)}).")
    l = _lire()
    deja = next((d for d in l if d["statut"] == "en attente" and d["type"] == type_ and d["params"] == params), None)
    if deja:
        return deja
    d = {"id": f"DEM-{datetime.now():%Y%m%d}-{secrets.token_hex(3)}", "type": type_, "libelle_type": TYPES[type_],
         "resume": resume[:300], "params": params, "apercu": apercu or {}, "origine": origine, "statut": "en attente",
         "cree_le": _maintenant(), "historique": [{"date": _maintenant(), "par": origine, "action": "demande"}]}
    l.append(d)
    _ecrire(l)
    evenements.publier({"type": "demandes_change"})
    return d


def lister(statut: str = "") -> list[dict]:
    return [d for d in reversed(_lire()) if not statut or d["statut"] == statut]


def message(d: dict) -> str:
    """Texte renvoyé à Cursor : rien n'a été fait, où valider."""
    return (f"Demande {d['id']} enregistrée ({d['libelle_type']} : {d['resume']}) — EN ATTENTE DE VALIDATION. "
            "Rien n'a encore été modifié : l'automaticien l'accepte ou la rejette dans l'atelier "
            "(Application Intelligence › À valider).")


def _executer(d: dict):
    p = d["params"]
    if d["type"] == "jira_transition":
        from atelier.execution import suivi
        return suivi.jira_transition(p["issue_key"], p["transition"])
    if d["type"] == "import_results_to_xray":
        from atelier.execution import suivi
        return suivi.import_results_to_xray(p["output_xml"], p.get("test_execution_key", ""), p.get("project_key", ""), p.get("test_plan_key", ""))
    if d["type"] == "qualify_failure":
        from atelier.execution import suivi
        return suivi.qualify_failure(p["run_id"], p["qualification"], p.get("commentaire", ""), p.get("message_echec", ""))
    if d["type"] == "fusion_ecrans":
        from atelier.discovery import carte
        e = carte.renommer(p["ecran"], p["nom"], p.get("module") or None)
        evenements.publier({"type": "carte_change"})
        return {"ecran": e.get("id"), "nom": e.get("nom")}
    if d["type"] == "remplacer_locator":
        from atelier.generation import locators
        return locators.add_screen_locator(p["screen_name"], p["key"], p["locator"], p["platform"])
    raise ValueError(f"Type non exécutable : {d['type']}")


def decider(did: str, accepter: bool, commentaire: str = "") -> dict:
    """Acceptation (exécution, une seule fois) ou rejet (définitif). Droit « valider_action » (relecteur)."""
    from atelier.domain import roles

    roles.exiger("valider_action")
    l = _lire()
    d = next((x for x in l if x["id"] == did), None)
    if not d:
        raise KeyError(f"Demande inconnue : {did}")
    if d["statut"] != "en attente":
        raise ValueError(f"Demande {did} déjà traitée ({d['statut']}).")
    if not accepter and not commentaire.strip():
        raise ValueError("Un rejet doit être justifié.")
    qui = _auteur()
    if accepter:
        try:
            r = _executer(d)
            d["statut"], d["resultat"] = "exécutée", json.loads(json.dumps(r, ensure_ascii=False, default=str))
        except Exception as e:  # noqa: BLE001 — l'échec est conservé, la demande ne repart pas toute seule
            d["statut"], d["erreur"] = "échec", str(e)[:500]
    else:
        d["statut"] = "rejetée"
    d["decide_par"], d["decide_le"], d["commentaire"] = qui, _maintenant(), commentaire.strip()
    d["historique"].append({"date": d["decide_le"], "par": qui, "action": "acceptée" if accepter else "rejetée",
                            "commentaire": commentaire.strip(), "statut": d["statut"]})
    _ecrire(l)
    evenements.publier({"type": "demandes_change"})
    return d
