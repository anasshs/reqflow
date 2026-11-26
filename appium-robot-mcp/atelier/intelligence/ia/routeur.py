"""Choix du modèle : indépendant des modules QA, il ne lit que l'opération, la taille du contexte, le budget et la santé
observée des modèles.

- niveau « economique » ou « avance » réglé pour l'opération, ou « auto » : avancé au-delà du seuil de tokens du routage ;
- budget en « restriction » : modèle économique imposé ;
- modèle désactivé, ou en échec sur la majorité de ses derniers appels (dernière heure) : le secours passe devant ;
- le secours suit toujours le modèle principal (repli après erreur ou délai dépassé).
Une opération déterministe (couverture, impact, TNR, critères…) n'arrive jamais ici : le backend la calcule.
"""
from __future__ import annotations

from datetime import datetime, timedelta


def niveau(reglage: dict, tokens: int, etat_budget: str = "") -> tuple[str, str]:
    """(niveau retenu, raison)."""
    n = reglage.get("niveau") or "auto"
    if etat_budget == "restriction":
        return "economique", "budget en restriction : modèle économique imposé"
    if n == "auto":
        seuil = int((reglage.get("routage") or {}).get("seuil_avance_tokens") or 12000)
        return ("avance", f"contexte de {tokens} tokens ≥ seuil {seuil}") if tokens >= seuil else ("economique", f"contexte de {tokens} tokens < seuil {seuil}")
    return n, "réglé pour l'opération"


def _en_echec(modele: str, routage: dict) -> bool:
    from atelier.intelligence.ia import journal

    depuis = (datetime.now().astimezone() - timedelta(hours=1)).isoformat(timespec="seconds")
    l = journal.lire("SELECT statut FROM appels WHERE modele = ? AND date >= ? AND source != 'mcp' AND cache = 0 ORDER BY date DESC LIMIT 10",
                     (modele, depuis))
    mini = int(routage.get("sante_min_appels") or 4)
    return len(l) >= mini and sum(x["statut"] == "erreur" for x in l) / len(l) >= float(routage.get("sante_taux_echec") or 0.5)


def candidats(reglage: dict, tokens: int, etat_budget: str = "") -> list[dict]:
    """Modèles à essayer, dans l'ordre : [{niveau, modele, …, raison}] ; le secours en dernier (ou en premier si le principal
    est en échec). Un modèle sans nom ou désactivé est écarté."""
    n, raison = niveau(reglage, tokens, etat_budget)
    m = reglage["modeles"]
    ordre = [n, "secours"] if n != "secours" else ["secours"]
    out, vus = [], set()
    for x in ordre:
        e = m.get(x) or {}
        if not e.get("modele") or e.get("actif") is False or e["modele"] in vus:
            continue
        vus.add(e["modele"])
        out.append({**e, "niveau": x, "raison": raison if x == n else "repli"})
    if len(out) > 1 and _en_echec(out[0]["modele"], reglage.get("routage") or {}):
        out = [{**out[1], "raison": f"{out[0]['modele']} en échec sur ses derniers appels"}, out[0]]
    if not out:  # tout désactivé : le modèle par défaut du fournisseur, pour ne pas casser l'atelier
        from atelier.intelligence.ia import config

        out = [{"modele": config.modele_par_defaut(), "niveau": "defaut", "raison": "aucun modèle actif réglé"}]
    return out
