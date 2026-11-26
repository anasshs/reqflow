"""Simulateur : comparer plusieurs réglages sur UNE demande réelle déjà passée (gardée masquée dans le journal), avant de
les activer.

Deux modes :
- estimation (défaut, gratuit) : tokens d'entrée selon le compactage, plafonds d'entrée et de sortie, sortie attendue
  (celle de la référence, plafonnée), durée moyenne observée du modèle, réponse disponible en cache ;
- exécution (sur demande explicite, consomme des tokens) : la demande est réellement rejouée sous chaque réglage, sans
  cache ; le résultat est comparé à la référence (verdicts identiques pour une réponse JSON, sinon ressemblance du texte).
La qualité finale reste notée par une personne : une note peut être posée sur chaque résultat.
"""
from __future__ import annotations

import difflib
import json

from atelier.intelligence.ia import cache, journal, optimiseur


def entrees(limite: int = 50, operation: str = "") -> list[dict]:
    w, p = ("WHERE operation = ?", (operation,)) if operation else ("", ())
    return journal.lire(f"SELECT id, date, operation, module, modele, max_sortie, LENGTH(demande) taille FROM entrees {w} ORDER BY date DESC LIMIT ?",
                        p + (limite,))


def _entree(eid: str) -> dict:
    l = journal.lire("SELECT * FROM entrees WHERE id = ?", (eid,))
    if not l:
        raise KeyError(f"Demande inconnue du journal : {eid}")
    return l[0]


def _verdicts(texte: str):
    try:
        from atelier.intelligence import fournisseur_ia

        j = fournisseur_ia.extraire_json(texte)
    except Exception:  # noqa: BLE001
        return None
    items = j if isinstance(j, list) else next((v for v in j.values() if isinstance(v, list)), None) if isinstance(j, dict) else None
    if items is None:
        return None
    return {json.dumps({k: v for k, v in x.items() if k not in ("justification", "preuves", "confiance")}, sort_keys=True, ensure_ascii=False)
            for x in items if isinstance(x, dict)}


def comparer(reference: str, texte: str) -> dict:
    """Proximité avec la référence : part des verdicts identiques (réponse JSON), sinon ressemblance du texte (0 à 100)."""
    a, b = _verdicts(reference), _verdicts(texte)
    if a is not None and b is not None:
        commun = len(a & b)
        return {"methode": "verdicts", "score": round(100 * commun / max(len(a | b), 1), 1), "identiques": commun, "reference": len(a), "obtenus": len(b)}
    return {"methode": "texte", "score": round(100 * difflib.SequenceMatcher(None, reference, texte).ratio(), 1)}


def _duree_moyenne(modele: str) -> int | None:
    l = journal.lire("SELECT AVG(duree_ms) d FROM appels WHERE modele = ? AND statut = 'ok' AND cache = 0 AND source != 'mcp'", (modele,))
    return round(l[0]["d"]) if l and l[0]["d"] is not None else None


def simuler(eid: str, variantes: list[dict], executer: bool = False) -> dict:
    """variantes : [{nom, modele?, niveau?, compacter?, max_entree?, max_sortie?}] ; la référence est l'appel d'origine."""
    from atelier.intelligence.ia import config

    e = _entree(eid)
    if not variantes:
        raise ValueError("Au moins une variante à comparer.")
    if len(variantes) > 6:
        raise ValueError("Six variantes au plus.")
    sortie_ref = optimiseur.estimer(e["reponse"])
    resultats = [{"nom": "référence", "modele": e["modele"], "tokens_entree": optimiseur.estimer(e["systeme"]) + optimiseur.estimer(e["demande"]),
                  "tokens_sortie": sortie_ref, "duree_ms": _duree_moyenne(e["modele"]), "proximite": {"methode": "référence", "score": 100.0}}]
    for v in variantes:
        nom = str(v.get("nom") or v.get("modele") or v.get("niveau") or "variante")[:60]
        modele = v.get("modele") or (config.modeles().get(v.get("niveau") or "") or {}).get("modele") or e["modele"]
        demande = optimiseur.compacter(e["demande"]) if v.get("compacter", True) else e["demande"]
        entree = optimiseur.estimer(e["systeme"]) + optimiseur.estimer(demande)
        r = {"nom": nom, "modele": modele, "tokens_entree": entree, "compacter": v.get("compacter", True)}
        if v.get("max_entree") and entree > int(v["max_entree"]):
            resultats.append({**r, "refus": f"contexte de {entree} tokens > limite {v['max_entree']} : la demande serait refusée"})
            continue
        if executer:
            from atelier.intelligence.ia import orchestrateur

            try:
                x = orchestrateur.executer(e["systeme"], demande, int(v.get("max_sortie") or e["max_sortie"] or 1500), e["operation"],
                                           forcer={"modele": modele, "max_sortie": v.get("max_sortie"), "compacter": v.get("compacter", True)},
                                           sans_cache=True, garder_entree=False, source="direct")
            except Exception as ex:  # noqa: BLE001
                resultats.append({**r, "erreur": str(ex)[:300]})
                continue
            resultats.append({**r, "tokens_entree": x["usage"]["tokens_entree"], "tokens_sortie": x["usage"]["tokens_sortie"], "estime": x["estime"],
                              "duree_ms": x["duree_ms"], "proximite": comparer(e["reponse"], x["texte"]), "texte": x["texte"][:4000]})
        else:
            sortie = min(sortie_ref, int(v["max_sortie"])) if v.get("max_sortie") else sortie_ref
            en_cache = cache.lire(cache.cle(e["operation"], e["systeme"], modele, demande)) is not None
            resultats.append({**r, "tokens_sortie": sortie, "duree_ms": _duree_moyenne(modele), "en_cache": en_cache,
                              "tronque": bool(v.get("max_sortie") and sortie_ref > int(v["max_sortie"])), "estime": True})
    for x in resultats:
        x["tokens"] = (x.get("tokens_entree") or 0) + (x.get("tokens_sortie") or 0) if not x.get("refus") and not x.get("erreur") else None
    ref = resultats[0]["tokens"] or 1
    for x in resultats[1:]:
        if x["tokens"] is not None:
            x["ecart_tokens_pct"] = round(100 * (x["tokens"] - ref) / ref, 1)
    sid = journal.nouvel_id()
    journal.executer("INSERT INTO simulations VALUES (?,?,?,?,?,?)", (sid, journal.maintenant(), journal.poste(), eid, e["operation"],
                                                                      json.dumps({"executer": executer, "resultats": resultats}, ensure_ascii=False)))
    return {"id": sid, "entree": {k: e[k] for k in ("id", "date", "operation", "module", "modele")}, "mode": "exécution" if executer else "estimation",
            "resultats": resultats}


def noter(sid: str, nom: str, note: int, commentaire: str = "") -> dict:
    """Note humaine de la qualité d'un résultat (1 à 5) : la qualité n'est jamais déduite seule."""
    if not 1 <= int(note) <= 5:
        raise ValueError("Note de 1 à 5.")
    l = journal.lire("SELECT * FROM simulations WHERE id = ?", (sid,))
    if not l:
        raise KeyError(f"Simulation inconnue : {sid}")
    d = json.loads(l[0]["resultats"])
    x = next((r for r in d["resultats"] if r["nom"] == nom), None)
    if x is None:
        raise KeyError(f"Résultat inconnu : {nom}")
    x["note"] = {"valeur": int(note), "commentaire": commentaire[:300], "par": journal.poste(), "date": journal.maintenant()}
    journal.executer("UPDATE simulations SET resultats = ? WHERE id = ?", (json.dumps(d, ensure_ascii=False), sid))
    return {"id": sid, **d}


def historique(limite: int = 20) -> list[dict]:
    return [{**{k: s[k] for k in ("id", "date", "poste", "entree", "operation")}, **json.loads(s["resultats"])}
            for s in journal.lire("SELECT * FROM simulations ORDER BY date DESC LIMIT ?", (limite,))]
