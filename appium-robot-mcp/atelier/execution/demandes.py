"""Mes demandes : tout ce que l'utilisateur a lancé et qui avance sans lui, en une seule liste.

Deux sources, jusque-là suivies à deux endroits :
  - les travaux de l'orchestrateur (BDD, dry-run, run sur un téléphone, étapes de l'agent, décisions humaines) ;
  - les demandes déposées à l'agent (Cursor / Claude Code), par exemple « Automatiser DEMO-12 » depuis un lot ou une
    sélection de scénarios issus du modèle comportemental.
Chaque entrée a un état simple : a_decider (attend l'utilisateur), en_attente (l'agent ne l'a pas encore prise),
en_cours, termine, echec, annule. Ce qui attend l'utilisateur vient en premier, puis ce qui avance, puis le reste.
Lecture seule : aucune décision n'est prise ici."""
from __future__ import annotations

ETATS = {"a_decider": "À décider", "en_attente": "En attente de l'agent", "en_cours": "En cours", "termine": "Terminé",
         "echec": "En échec", "annule": "Annulé"}
_ORDRE = {"a_decider": 0, "echec": 1, "en_cours": 2, "en_attente": 3, "termine": 4, "annule": 5}
_TRAVAIL = {"en_cours": "en_cours", "termine": "termine", "echec": "echec", "arrete": "echec", "annule": "annule"}
_BOITE = {"en attente": "en_attente", "prise": "en_cours", "terminée": "termine", "échouée": "echec", "annulée": "annule"}


def _de_travail(t: dict, boite: dict | None = None, agent: dict | None = None) -> dict:
    etapes = t.get("etapes") or []
    decision = next((e for e in etapes if e.get("statut") == "attente_decision"), None)
    courante = decision or next((e for e in etapes if e.get("statut") in ("en_cours", "attente_ressource", "echec")), None) \
        or next((e for e in etapes if e.get("statut") == "a_faire"), None)
    etat = "a_decider" if decision and t.get("statut") == "en_cours" else _TRAVAIL.get(t.get("statut"), "en_cours")
    demande = None
    if courante and courante.get("type") == "ia" and courante.get("demande") and courante.get("statut") == "en_cours":
        demande = (boite or {}).get(courante["demande"])
        if demande and demande.get("statut") == "en attente" and etat == "en_cours":
            etat = "en_attente"  # déposée, personne ne l'a prise : ne pas dire « en cours »
    detail = ""
    if courante:
        detail = courante.get("titre", "")
        if courante.get("statut") == "attente_ressource":
            detail += " · attend un téléphone libre"
        if courante.get("erreur"):
            detail += " · " + str(courante["erreur"])[:200]
        if demande and etat == "en_attente":
            detail += " · demande à l'agent en attente" + (f" : {agent['raison']}" if agent and not agent.get("pret") else "")
        elif demande and demande.get("statut") == "prise":
            detail += " · l'agent y travaille"
    return {"id": t["id"], "source": "travail", "titre": t.get("titre", ""), "etat": etat, "etat_libelle": ETATS[etat],
            "etape": detail, "avancement": [sum(e.get("statut") == "fait" for e in etapes), len(etapes)],
            "cree": t.get("cree", ""), "lien": f"#travaux/{t['id']}", "origine": (t.get("origine") or {}).get("ecran", ""),
            "demande": demande and {"id": demande["id"], "statut": demande["statut"], "pris": demande.get("pris", "")}}


def _de_boite(d: dict) -> dict:
    etat = _BOITE.get(d.get("statut"), "en_attente")
    detail = d.get("erreur") or (d.get("resultat") or "")[:240]
    if not detail:
        detail = {"en_attente": "Déposée : personne ne l'a encore prise.", "en_cours": "L'agent y travaille."}.get(etat, "")
    return {"id": d["id"], "source": "agent", "titre": d.get("titre", ""), "etat": etat, "etat_libelle": ETATS[etat],
            "etape": detail, "avancement": None, "cree": d.get("cree", ""), "lien": d.get("ecran") or "",
            "origine": d.get("ecran") or "", "mode": d.get("mode", ""),
            "demande": {"id": d["id"], "statut": d.get("statut"), "pris": d.get("pris", "")}}


def lister(limite: int = 40) -> dict:
    """Demandes récentes, ce qui attend l'utilisateur d'abord ; compteurs pour l'en-tête."""
    from atelier.execution import orchestrateur
    from atelier.integrations import boite_cursor

    try:
        demandes = boite_cursor.etat(limite=200)["demandes"]
        agent = boite_cursor.pret()
    except Exception:  # boîte illisible : les travaux restent visibles
        demandes, agent = [], {"pret": True, "raison": "", "a_faire": "", "comment": ""}
    par_id = {d["id"]: d for d in demandes}
    l = [_de_travail(t, par_id, agent) for t in orchestrateur.lister()]
    demandes = demandes[:limite]
    l += [_de_boite(d) for d in demandes if not d.get("travail")]  # une demande née d'un travail est suivie dans ce travail
    l.sort(key=lambda x: x["cree"] or "", reverse=True)
    l.sort(key=lambda x: _ORDRE[x["etat"]] if x["etat"] in ("a_decider", "echec", "en_cours", "en_attente") else 9)
    actives = [x for x in l if x["etat"] in ("a_decider", "en_cours", "en_attente")]
    recentes = [x for x in l if x not in actives][: max(0, limite - len(actives))]
    attente = [x for x in l if x["etat"] == "en_attente"]
    return {"demandes": actives + recentes, "agent": {**agent, "en_attente": len(attente)},
            "compteurs": {"a_decider": sum(x["etat"] == "a_decider" for x in l),
                          "en_cours": sum(x["etat"] in ("en_cours", "en_attente") for x in l),
                          "echec": sum(x["etat"] == "echec" for x in recentes[:10])}}
