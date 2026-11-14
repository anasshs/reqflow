"""Assistant IA contextuel des graphes.

Deux niveaux :
  1. anomalies() — contrôles déterministes, sans IA (toujours disponibles, vérifiables) :
     locators ou JDD référencés mais non définis, keywords en double, tests Robot sans clé Xray,
     clés Robot inconnues de l'instantané Xray, écrans à revoir (changés au build), exigences non
     couvertes, propositions IA en attente de validation ;
  2. demander() — question à Claude sur le SEUL contexte du graphe sélectionné (nœuds, relations,
     anomalies). La réponse doit citer les identifiants de nœuds ; elle n'est jamais appliquée :
     toute proposition passe par une action de l'automaticien (« déduit / à valider »).
"""
from __future__ import annotations

import json
import os

from atelier.domain.graphe import Graphe

MODELE = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
INTENTIONS = {
    "expliquer": "Explique ce graphe à un automaticien : ce qu'il montre, les éléments centraux, les chemins importants.",
    "resumer": "Résume les dépendances de l'élément sélectionné (ou du graphe) : qui dépend de quoi.",
    "anomalies": "Identifie les anomalies et incohérences visibles dans ce contexte, par ordre de gravité.",
    "ameliorations": "Propose des améliorations concrètes (robustesse des locators, factorisation de keywords, traçabilité).",
    "lacunes": "Détecte les lacunes : exigences ou écrans non couverts, tests sans automatisation, liens manquants.",
    "impacts": "Analyse les impacts d'une modification de l'élément sélectionné.",
    "manquants": "Liste les éléments ou relations manquants probables, chacun comme proposition à valider.",
    "recommandation": "Explique la recommandation ou le statut de l'élément sélectionné à partir des faits observés.",
}
SYSTEME = """Tu assistes un automaticien QA (Robot Framework, Xray) dans la plateforme « Atelier d'automatisation ».
Règles strictes :
- Réponds UNIQUEMENT à partir du contexte JSON fourni (graphe sélectionné, nœuds, relations, anomalies calculées).
  Si une information n'y est pas, dis-le : n'invente ni écran, ni test, ni donnée, ni pourcentage.
- Cite les identifiants exacts des nœuds entre crochets, ex. [locator:virement_saisie.bouton_valider@android].
- Distingue les faits (observés, déclarés) des hypothèses. Un lien « déduit » non validé n'est pas un fait.
- Tes propositions ne sont pas appliquées : termine par une section « Propositions à valider » (liste
  numérotée) quand tu proposes des modifications.
- Réponds en français, de façon concise et structurée."""


def anomalies(g: Graphe, pat: dict | None = None) -> list[dict]:
    out = []

    def ajout(gravite, code, noeud, message):
        out.append({"gravite": gravite, "code": code, "noeud": noeud, "message": message})
    for n in g.noeuds.values():
        p = n.proprietes
        if n.type == "locator" and p.get("non_defini"):
            ajout("haute", "locator_non_defini", n.id, f"Locator {n.libelle} référencé mais défini dans aucun fichier.")
        if n.type == "jdd" and p.get("non_defini"):
            ajout("haute", "jdd_non_defini", n.id, f"Jeu de données {n.libelle} référencé mais absent de data/jdd.")
        if n.type == "keyword" and p.get("doublons"):
            ajout("moyenne", "keyword_double", n.id, f"Keyword {n.libelle} défini plusieurs fois : {', '.join(p['doublons'])}.")
        if n.type == "test_robot" and not p.get("cles_xray"):
            ajout("moyenne", "test_sans_cle", n.id, f"Test Robot {n.libelle} sans tag de clé Xray (non traçable).")
        if n.type == "test" and p.get("automatise") and pat and not p.get("connu_xray"):
            ajout("moyenne", "cle_inconnue", n.id, f"Clé {n.libelle} portée par le dépôt mais absente de l'instantané Xray.")
        if n.type == "ecran" and p.get("a_revoir"):
            ajout("moyenne", "ecran_a_revoir", n.id, f"Écran {n.libelle} changé au dernier build : à revoir.")
        if n.type == "locator" and p.get("fiabilite") == "fragile":
            ajout("basse", "locator_fragile", n.id, f"Locator {n.libelle} fragile ({p.get('valeur')}).")
        if n.statut == "à valider":
            ajout("info", "proposition_en_attente", n.id, f"Proposition IA en attente de validation : {n.libelle}.")
        if n.type == "test_robot" and p.get("dernier_statut") == "FAIL":
            ajout("haute", "test_en_echec", n.id, f"Dernière exécution en échec : {p.get('dernier_message', '')[:120]}")
    for r in g.relations.values():
        if r.statut == "à valider":
            ajout("info", "proposition_en_attente", r.id, f"Relation proposée à valider : {r.id}.")
    for e in (pat or {}).get("exigences", []):
        nid = f"{e['type']}:{e['cle']}"
        if nid in g.noeuds and e["type"] == "user_story" and not any(r.type == "teste_par" for r in g.sortants(nid)):
            ajout("moyenne", "exigence_non_couverte", nid, f"{e['cle']} n'est liée à aucun test Xray.")
    ordre = {"haute": 0, "moyenne": 1, "basse": 2, "info": 3}
    return sorted(out, key=lambda a: (ordre[a["gravite"]], a["noeud"]))


def contexte(g: Graphe, selection: str = "", max_noeuds: int = 150) -> dict:
    """Contexte envoyé à l'IA : le voisinage de la sélection (ou le graphe), borné."""
    sous = g.voisinage([selection], 2) if selection and selection in g.noeuds else g
    ids = list(sous.noeuds)[:max_noeuds]
    sous = sous.sous_graphe(ids)
    return {"selection": selection or None,
            "noeuds": [{"id": n.id, "type": n.type, "libelle": n.libelle, "provenance": n.provenance,
                        "statut": n.statut, "plateformes": n.plateformes,
                        "proprietes": {k: v for k, v in n.proprietes.items() if k not in ("sql",)}}
                       for n in sous.noeuds.values()],
            "relations": [{"de": r.de, "type": r.type, "vers": r.vers, "provenance": r.provenance, "statut": r.statut}
                          for r in sous.relations.values()],
            "tronque": len(g.noeuds) > len(ids) and not selection}


def demander(g: Graphe, graphe_nom: str, intention: str, selection: str = "", question: str = "",
             pat: dict | None = None, client=None) -> dict:
    if intention not in INTENTIONS and not question:
        raise ValueError(f"Intention inconnue : {intention} ({', '.join(INTENTIONS)})")
    ctx = contexte(g, selection)
    ctx["anomalies_calculees"] = [a for a in anomalies(g, pat) if not selection or a["noeud"] in {n["id"] for n in ctx["noeuds"]}]
    consigne = INTENTIONS.get(intention, "") + (f"\nQuestion de l'automaticien : {question}" if question else "")
    if client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return {"disponible": False, "raison": "ANTHROPIC_API_KEY non configurée : seules les anomalies "
                                                   "calculées (sans IA) sont affichées.",
                    "anomalies": ctx["anomalies_calculees"]}
        client = _client()
    message = client.messages.create(
        model=MODELE, max_tokens=2000, system=SYSTEME,
        messages=[{"role": "user", "content": f"Graphe : {graphe_nom}\n{consigne}\n\nContexte :\n"
                                              + json.dumps(ctx, ensure_ascii=False, default=str)}])
    texte = "".join(b.text for b in message.content if getattr(b, "type", "") == "text")
    cites = sorted({n["id"] for n in ctx["noeuds"] if f"[{n['id']}]" in texte})
    return {"disponible": True, "reponse": texte, "noeuds_cites": cites, "anomalies": ctx["anomalies_calculees"],
            "avertissement": "Réponse de l'IA : à vérifier. Rien n'est modifié sans votre validation."}


def _client():
    import anthropic

    ca = os.environ.get("XRAY_CA_BUNDLE")
    if ca:
        import httpx

        return anthropic.Anthropic(http_client=httpx.Client(verify=ca, timeout=120))
    return anthropic.Anthropic()


SYSTEME_SCENARIO = SYSTEME + """
Tu relis un scénario BDD (Gherkin) avant sa génération en Robot Framework. Conventions : Gherkin français,
aucune donnée littérale dans les steps (elles viennent du jeu de données &{JDD_<NOM>}), une assertion métier
par résultat attendu, branches négatives pour les cas d'erreur, étapes reliées aux écrans de la carte.
Cite les étapes par leur identifiant entre crochets, ex. [s1a2b3c4]."""


def demander_scenario(m: dict, controles_calcules: list[dict], question: str = "", client=None) -> dict:
    """Relecture du scénario par l'IA, sur le seul contenu du scénario et des contrôles calculés."""
    if client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return {"disponible": False, "raison": "ANTHROPIC_API_KEY non configurée : seuls les contrôles "
                                                   "calculés (sans IA) sont affichés.", "controles": controles_calcules}
        client = _client()
    ctx = {"scenario": {k: m.get(k) for k in ("cle", "titre", "jdd", "statut", "scenarios", "contexte")},
           "controles_calcules": controles_calcules}
    consigne = question or "Relis ce scénario : assertions manquantes, branches à ajouter, données littérales, ambiguïtés."
    message = client.messages.create(model=MODELE, max_tokens=1500, system=SYSTEME_SCENARIO,
                                     messages=[{"role": "user", "content": consigne + "\n\nContexte :\n"
                                                + json.dumps(ctx, ensure_ascii=False, default=str)}])
    texte = "".join(b.text for b in message.content if getattr(b, "type", "") == "text")
    ids = {e["id"] for s in m.get("scenarios", []) for e in s["etapes"]}
    return {"disponible": True, "reponse": texte, "etapes_citees": sorted(i for i in ids if f"[{i}]" in texte),
            "controles": controles_calcules,
            "avertissement": "Réponse de l'IA : à vérifier. Rien n'est modifié sans votre validation."}
