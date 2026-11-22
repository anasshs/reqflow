"""Génération BDD depuis le MBT (cahier MBT, § 10) : un chemin du modèle comportemental devient un scénario du
référentiel BDD EXISTANT (même modèle YAML / .feature, même éditeur, mêmes contrôles), jamais un second générateur ni
un second référentiel.

Traçabilité gardée dans le scénario (`mbt`) : model_id, model_version, state_ids, transition_ids, action_ids,
condition_ids, source_path_id, coverage_strategy, related_user_story_ids, generation_origin, generation_date.
Avant toute création, le chemin est comparé aux scénarios existants (doublon, variante, redondance partielle,
complémentaire, nouveau) : un doublon n'est pas recréé, aucune fusion n'est automatique. Un résultat attendu non
confirmé est écrit « (à confirmer) » : le message exact vient d'une exigence ou d'une validation, jamais d'une invention.
"""
from __future__ import annotations

from datetime import datetime

from atelier.domain import comportement as cm
from atelier.generation import bdd
from atelier.intelligence import mbt

ORIGINES = ("US_AI", "MBT", "US_MBT", "Manual")
# Trois décisions : Réutilisation (un scénario existant couvre déjà ce chemin : rien n'est créé), Complémentaire (un
# scénario existant en couvre une partie : le nouveau le prolonge ou en est une variante), Nouveau.
CLASSES = ("Réutilisation", "Complémentaire", "Nouveau")


def classer(chemin: dict, modele: dict, scenarios: list[dict] | None = None) -> dict:
    """Comparaison d'un chemin aux scénarios existants : transitions parcourues (traçabilité MBT ou écrans des étapes),
    états traversés, conditions et issues. Renvoie la classe la plus proche et le scénario concerné."""
    scenarios = mbt._scenarios() if scenarios is None else scenarios
    conc = mbt.couverture_conception(modele, scenarios)
    p, etats = list(chemin["transitions"]), set(chemin["etats"])
    issues = {(c["id"], c["issue"]) for c in chemin["conditions"]}
    meilleur = {"classe": "Nouveau", "nuance": "", "scenario": "", "raison": "aucun scénario ne parcourt ces transitions"}
    rang = {c: i for i, c in enumerate(CLASSES)}
    for s in scenarios:
        cle = s.get("cle", "")
        ts = conc["par_scenario"].get(cle)
        if not ts:
            continue
        x = s.get("mbt") or {}
        if ts == p or (set(ts) == set(p) and len(ts) == len(p)):
            c, nu, r = "Réutilisation", "identique", "mêmes transitions, mêmes conditions : réutiliser le scénario existant"
        elif mbt._contient(ts, p):
            c, nu, r = "Réutilisation", "contenu", "le scénario existant parcourt déjà tout ce chemin : le réutiliser"
        elif mbt._contient(p, ts):
            c, nu, r = "Complémentaire", "prolonge", f"prolonge le scénario existant {cle} (même début, comportement supplémentaire)"
        elif x.get("state_ids") and set(x["state_ids"]) == etats and {(i["id"], i["issue"]) for i in x.get("conditions") or []} != issues:
            c, nu, r = "Complémentaire", "variante", "mêmes états, conditions ou issues différentes (variante)"
        elif set(ts) & set(p):
            c, nu, r = "Complémentaire", "partiel", "transitions en partie communes"
        else:
            continue
        if rang[c] < rang[meilleur["classe"]]:
            meilleur = {"classe": c, "nuance": nu, "scenario": cle, "raison": r}
    return meilleur


def _texte_action(a: dict) -> str:
    lib = (a.get("libelle") or "l'élément").strip()
    if a.get("provenance") == "déclaré" and " " in lib and lib[:1].islower():
        return f"je {lib}" if not lib.lower().startswith(("je ", "j'")) else lib
    return f"je touche {lib.lower()}"


def modele_bdd(chemin: dict, m: dict, origine: str = "MBT", us: list[str] | None = None) -> dict:
    """Scénario BDD (modèle du référentiel) d'un chemin : Étant donné l'état initial, puis pour chaque transition la
    condition (Et), l'action (Quand) et le résultat (Alors). Locators repris de la Discovery quand ils sont connus."""
    E, T, A, C = m["etats"], m["transitions"], m["actions"], m["conditions"]

    def ecran(eid):
        return (E[eid].get("ecran") or "").split(":", 1)[-1]

    etapes = []
    e0 = E[chemin["etats"][0]]
    etapes.append(bdd._etape("Étant donné", f"que je suis sur l'écran {e0['nom']}" if e0.get("type") == "ecran" else e0["nom"], ecran=ecran(chemin["etats"][0])))
    t0 = T[chemin["transitions"][0]] if chemin["transitions"] else {}
    if any(x["texte"] == "Utilisateur authentifié" for x in t0.get("preconditions_liste") or []):  # précondition du point de départ
        etapes.append(bdd._etape("Et", "que je suis authentifié", ecran=ecran(chemin["etats"][0])))
    for tid in chemin["transitions"]:
        t = T[tid]
        if t.get("garde"):
            c = C[t["garde"]]
            suffixe = "" if c.get("confiance") == "confirmée" else " (condition à confirmer)"
            etapes.append(bdd._etape("Et", (f"la condition « {c.get('libelle')} » n'est pas remplie" if t.get("issue") == "fausse"
                                            else f"la condition « {c.get('libelle')} » est remplie") + suffixe, ecran=ecran(t["de"])))
        a = A.get(t.get("action"), {})
        loc = ""
        if a.get("locators"):
            loc = a["locators"][0].split(":", 1)[1].split("@", 1)[0]
        etapes.append(bdd._etape("Quand", _texte_action(a) if a else (t.get("evenement") or "l'événement attendu se produit"),
                                 ecran=ecran(t["de"]), locator=""))
        if loc:
            etapes[-1]["cle_locator"] = loc
        cible = E[t["vers"]]
        if cible.get("type") == "ecran":
            texte = f"l'écran {cible['nom']} est affiché"
        else:
            texte = (t.get("postconditions") or cible.get("nom") or "le résultat attendu est obtenu")
        if t.get("postconditions_a_confirmer"):
            texte = (t.get("postconditions") or ("l'opération est refusée" if cible.get("type") == "erreur" else texte)) + " (résultat attendu à confirmer)"
        etapes.append(bdd._etape("Alors", texte, ecran=ecran(t["vers"]) if cible.get("type") == "ecran" else ecran(t["de"]),
                                 resultat_attendu="" if t.get("postconditions_a_confirmer") else (t.get("postconditions") or "")))
        if cible.get("type") == "ecran" and t.get("attendu_exigence"):  # postcondition écrite dans l'exigence (Confirmé)
            etapes.append(bdd._etape("Et", t["attendu_exigence"], ecran=ecran(t["vers"]), resultat_attendu=t["attendu_exigence"]))
    titre = chemin["titre"][:200]
    us = us if us is not None else list(m.get("us") or [])
    trace = {"model_id": m["id"], "model_version": m["version"], "state_ids": chemin["etats"], "transition_ids": chemin["transitions"],
             "action_ids": chemin["actions"], "condition_ids": [c["id"] for c in chemin["conditions"]],
             "conditions": [{"id": c["id"], "issue": c["issue"]} for c in chemin["conditions"]],
             "source_path_id": chemin["id"], "coverage_strategy": chemin["strategie"],
             "related_user_story_ids": sorted(set(us) | set(chemin.get("exigences") or [])), "hypothese": bool(chemin.get("hypothese")),
             "generation_origin": origine, "generation_date": datetime.now().astimezone().isoformat(timespec="seconds")}
    per = m.get("perimetre") or {}
    description = [f"Généré par l'analyse comportementale (modèle {m['id']} v{m['version']}, chemin {chemin['id']}) : à relire et valider.",
                   f"Justification : {chemin['justification']}", f"Valeur ajoutée : {chemin.get('valeur_ajoutee', '')}"] + [f"À confirmer : {x}" for x in chemin["manquant"][:8]]
    return {"langue": "fr", "feature": titre, "titre": titre, "description": description, "contexte": [], "tags": [],
            "source": "mbt", "sources_generation": ["US", "MBT"] if origine == "US_MBT" else [origine], "statut": "brouillon",
            "module": per.get("id", "").split(":", 1)[1] if per.get("type") == "module" else "",
            "parcours": per.get("id", "") if per.get("type") == "parcours" else "", "mbt": trace,
            "scenarios": [{"id": bdd._id(), "nom": titre, "type": chemin["type"] if chemin["type"] in bdd.TYPES_SCENARIO else "principal",
                           "tags": ["mbt"] + (["a_confirmer"] if chemin["manquant"] else []), "depuis": "", "etapes": etapes}]}


def generer(mid: str, chemins: list[str] | None = None, strategie: str = "transitions", forcer: bool = False,
            origine: str = "MBT", limites: dict | None = None, auteur: str = "automaticien", inclure_couverts: bool = False) -> dict:
    """Crée les scénarios BDD (brouillons) des chemins choisis (tous ceux de la stratégie si aucun n'est choisi). Un
    doublon n'est créé qu'avec `forcer` ; chaque création est tracée dans le modèle (chemins générés)."""
    if origine not in ORIGINES:
        raise ValueError(f"Origine inconnue : {origine}")
    m = cm.exiger(mid)
    a = mbt.analyser(mid, strategie, limites, inclure_couverts=inclure_couverts)
    choisis = [p for p in a["chemins"] if not chemins or p["id"] in chemins]
    inconnus = sorted(set(chemins or []) - {p["id"] for p in choisis})
    scenarios = mbt._scenarios()
    crees, ignores = [], []
    for p in choisis:
        cl = classer(p, m, scenarios)
        if cl["classe"] == "Réutilisation" and not forcer:
            ignores.append({"chemin": p["id"], "titre": p["titre"], **cl})
            continue
        s = modele_bdd(p, m, origine)
        base = bdd._slug(f"mbt_{cm.slug(m['perimetre']['id'].split(':', 1)[-1], 30)}_{p['id'][2:]}")
        cle, n = base, 2
        while bdd.charger(cle):
            cle, n = f"{base}_{n}", n + 1
        s["cle"] = cle
        s["comparaison"] = cl
        bdd.sauver(s, auteur=auteur)
        scenarios.append(s)
        m["chemins_generes"][p["id"]] = {"scenario": cle, "version": m["version"], "strategie": strategie, "transitions": p["transitions"],
                                         "etats": p["etats"], "date": s["mbt"]["generation_date"], "classe": cl["classe"]}
        crees.append({"cle": cle, "chemin": p["id"], "titre": p["titre"], "type": p["type"], "comparaison": cl,
                      "a_confirmer": len(p["manquant"]), "automatisation": p["automatisation"]["statut"]})
    cm.sauver(m, "scénarios générés")
    mbt.vider_cache()
    return {"crees": crees, "ignores": ignores, "inconnus": inconnus, "modele": mbt.resume(cm.exiger(mid))}
