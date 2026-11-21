"""Optimisation sans perte de ce qui est envoyé aux modèles et à Cursor.

- Compacter : JSON réécrit sans espaces inutiles, valeurs vides (null, "", [], {}) retirées, éléments identiques
  consécutifs d'une liste dédoublonnés ; texte libre : espaces répétés réduits. Aucune valeur non vide n'est retirée.
- Plafond : si le contexte dépasse la limite d'entrée du modèle, l'appel est REFUSÉ avec un message qui dit quoi réduire ;
  jamais tronqué en silence (une information nécessaire à une décision QA ne disparaît pas sans le dire).
- Tokens : comptés par le fournisseur quand il les rend ; sinon estimés (4 caractères par token), et signalés comme tels.
"""
from __future__ import annotations

import json
import re


def estimer(texte) -> int:
    t = texte if isinstance(texte, str) else json.dumps(texte, ensure_ascii=False, default=str)
    return (len(t) + 3) // 4


def _vide(v) -> bool:
    return v is None or v == "" or v == [] or v == {}


def alleger(obj):
    """Copie sans valeurs vides ni doublons consécutifs dans les listes ; le reste est inchangé."""
    if isinstance(obj, dict):
        out = {k: alleger(v) for k, v in obj.items()}
        return {k: v for k, v in out.items() if not _vide(v)}
    if isinstance(obj, list):
        out = []
        for v in (alleger(x) for x in obj):
            if not out or v != out[-1]:
                out.append(v)
        return out
    return obj


def _compacter_json(t: str) -> str | None:
    t = t.strip()
    if not t or t[0] not in "[{":
        return None
    try:
        return json.dumps(alleger(json.loads(t)), ensure_ascii=False, separators=(",", ":"))
    except ValueError:
        return None


def compacter(texte: str) -> str:
    """Demande compactée : un JSON (seul, ou après une consigne « … Contexte :\\n{json} ») est réécrit sans perte."""
    j = _compacter_json(texte)
    if j is not None:
        return j
    m = re.search(r"\n\s*([\[{])", texte)
    if m:
        debut = m.start(1)
        j = _compacter_json(texte[debut:])
        if j is not None:
            return re.sub(r"[ \t]{2,}", " ", texte[:debut]).rstrip() + "\n" + j
    return re.sub(r"[ \t]{2,}", " ", texte)


class ContexteTropGros(ValueError):
    pass


def preparer(systeme: str, demande: str, reglage: dict, max_entree: int | None) -> tuple[str, int, int]:
    """(demande à envoyer, tokens estimés avant, après). Refuse un contexte au-delà de la limite d'entrée du modèle."""
    avant = estimer(systeme) + estimer(demande)
    if (reglage.get("optimisation") or {}).get("compacter", True):
        demande = compacter(demande)
    apres = estimer(systeme) + estimer(demande)
    if max_entree and apres > max_entree:
        raise ContexteTropGros(f"Contexte trop volumineux pour « {reglage.get('operation')} » : {apres} tokens estimés, limite {max_entree}. "
                               "Réduire le périmètre (moins de tests ou d'exigences) ou les plafonds de contexte dans Paramètres › IA ; "
                               "rien n'est tronqué sans le dire.")
    return demande, avant, apres
