"""Jugements délégués à une IA : le modèle commun aux analyses qui demandent de COMPRENDRE un texte.

Les règles de l'atelier comparent des mots ; elles ne savent pas que « pack éligible » et « pack non éligible » ont des
résultats opposés, ni qu'un test reformulé vérifie la même chose. Pour ces analyses (granularité des tests, doublons,
liens exigence ↔ test, tests orphelins, corrélation écran ↔ exigence), le partage est toujours le même :

  1. les règles fournissent les faits et PRÉSÉLECTIONNENT des candidats (rappel large, explicable) ;
  2. l'IA juge le sens, avec une justification obligatoire :
       - Cursor via le MCP (outil « …_a_juger » en lecture, puis outil de dépôt), l'atelier n'appelle rien ;
       - ou un appel direct (LLM interne / Claude, selon IA_FOURNISSEUR), texte masqué avant envoi ;
  3. le serveur contrôle chaque jugement (objets connus, verdict connu, justification) et renvoie les refus motivés ;
  4. l'automaticien décide : rien n'est appliqué, lié, créé ou écrit dans Jira / Xray par l'IA.

Sans IA, les règles restent disponibles comme secours, présentées comme telles (« sans compréhension du texte »).
"""
from __future__ import annotations

import json
from typing import Callable

SECOURS = "présélection par ressemblance des mots (secours, sans compréhension du texte)"


def court(texte, n: int = 400) -> str:
    """Texte masqué (valeurs de JDD, numéros, courriels…) et tronqué, prêt à être lu par une IA."""
    from atelier.intelligence.testabilite_us import _masque

    t = " ".join(str(texte or "").split())
    return _masque(t[:n] + ("…" if len(t) > n else ""))


def etapes_courtes(etapes, n: int = 10, l: int = 200) -> list[dict]:
    return [{k: court(e.get(k), l) for k in ("action", "donnees", "resultat") if e.get(k)}
            for e in (etapes or [])[:n] if isinstance(e, dict)]


def justification(j) -> str:
    return " ".join(str(j or "").split())[:800]


def exiger_ia(operation: str = "") -> None:
    """Refuse un jugement d'IA (dépôt de Cursor ou appel direct) pour un type de traitement réglé sur le modèle applicatif."""
    from atelier.intelligence import fournisseur_ia

    if fournisseur_ia.applicatif(operation):
        from atelier.intelligence.ia import operations

        op = fournisseur_ia._operation(operation)
        raise PermissionError(f"« {operations.TRAITEMENTS.get(op, (op,))[0]} » est réglé sur le modèle applicatif (Paramètres › Pilotage IA) : "
                              "jugement de l'IA refusé, l'atelier garde ses règles.")


def maintenant() -> str:
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")


def appel_direct(lecture: dict, systeme: str, champ: str, deposer: Callable[[list, str], dict], outils_cursor: str,
                 jetons: int = 3000) -> dict:
    """Jugement par le LLM interne ou Claude (appel direct). Avec « cursor », l'atelier n'appelle rien : l'agent passe par
    les outils MCP indiqués. Le dépôt passe par les mêmes contrôles que celui de Cursor."""
    from atelier.intelligence import fournisseur_ia as ia

    if ia.fournisseur() == "cursor":
        return {"disponible": False, "raison": f"Fournisseur « cursor » : demander à Cursor (outils MCP {outils_cursor})."}
    if not ia.configure():
        return {"disponible": False, "raison": f"IA « {ia.fournisseur()} » non disponible : présélection par règles uniquement (secours)."}
    brut = ia.completer(systeme, json.dumps(lecture, ensure_ascii=False), jetons)
    try:
        r = ia.extraire_json(brut)
    except ValueError:
        r = {}
    items = r.get(champ) if isinstance(r, dict) else r
    return {"disponible": True, **deposer(items if isinstance(items, list) else [], f"IA {ia.fournisseur()} ({ia.modele()})")}
