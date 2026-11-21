"""Consultation et enrichissement des entités Champ et Anomalie du Knowledge Graph (V2, phase 5).

- Champ = composant de genre « champ » (observé dans la carte) : attributs, règles de validation, messages d'erreur,
  fonctionnalité, tests qui le vérifient.
- Anomalie = nœud « bug » : bug Jira et/ou échec analysé (Failure Analysis) avec écran, composant, test, exécution.
- Enrichir = PROPOSER une règle de validation liée à un champ : nœud et relation « à valider » (boîte À valider) ;
  rien n'est modifié dans le graphe validé sans décision humaine.
"""
from __future__ import annotations

import re


def _graphe(g=None):
    if g is not None:
        return g
    from atelier.discovery import connaissance

    return connaissance.construire()


def champs(ecran: str = "", g=None) -> list[dict]:
    g = _graphe(g)
    out = []
    for n in sorted(g.noeuds.values(), key=lambda x: x.id):
        if n.type != "composant" or n.proprietes.get("genre") != "champ":
            continue
        p = n.proprietes
        if ecran and p.get("ecran") != ecran:
            continue
        regles = [{"id": r.vers, "libelle": g.noeuds[r.vers].libelle, "lien": r.provenance, "statut": r.statut}
                  for r in g.sortants(n.id) if r.type == "possede" and r.vers in g.noeuds]
        out.append({"id": n.id, "ecran": p.get("ecran"), "nom_technique": p.get("nom_technique"), "libelle": p.get("libelle") or n.libelle,
                    "type": p.get("type"), "format": p.get("format"), "obligatoire": p.get("obligatoire"), "valeur_defaut": p.get("valeur_defaut"),
                    "regles_validation": regles, "messages_erreur": p.get("messages_erreur") or [], "fonctionnalite": p.get("fonctionnalite", ""),
                    "plateformes": n.plateformes, "tests": sorted(g.noeuds[r.de].libelle for r in g.entrants(n.id) if r.type == "verifie" and r.de in g.noeuds),
                    "anomalies": sorted(r.de for r in g.entrants(n.id) if r.type == "concerne"),
                    "source": n.source, "confiance": n.confiance, "statut": n.statut})
    return out


def anomalies(g=None) -> list[dict]:
    g = _graphe(g)
    out = []
    for n in sorted(g.noeuds.values(), key=lambda x: x.id):
        if n.type != "bug":
            continue
        p = n.proprietes

        def vers(t, types):
            return sorted(g.noeuds[r.vers].libelle for r in g.sortants(n.id) if r.type == t and r.vers in g.noeuds and g.noeuds[r.vers].type in types)
        out.append({"id": n.id, "id_jira": p.get("id_jira") or p.get("cle") or (n.id.split(":", 1)[1] if not n.id.startswith("bug:FA-") else ""),
                    "id_interne": p.get("id_interne", ""), "titre": n.libelle, "type": p.get("type_anomalie") or "bug Jira",
                    "priorite": p.get("priorite", ""), "statut": p.get("statut_analyse") or p.get("statut") or "",
                    "fonctionnalites": vers("concerne", ("fonctionnalite", "module")), "ecrans": vers("concerne", ("ecran",)),
                    "composants": vers("concerne", ("composant",)), "tests": vers("detecte_par", ("test_robot", "test")),
                    "execution": p.get("execution", ""), "date_detection": p.get("date_detection", ""), "message": p.get("message", ""),
                    "source": n.source, "confiance": n.confiance, "statut_validation": n.statut, "historique": p.get("historique") or []})
    return out


def proposer_regle_champ(ecran: str, champ: str, regle: str, description: str = "", g=None) -> dict:
    """Propose une règle de validation (obligatoire, format, valeur par défaut, message…) pour un champ : nœud « regle »
    et relation « possède », tous deux à valider. Le texte de la règle alimente ensuite les attributs du champ."""
    from atelier.domain import declarations

    g = _graphe(g)
    cid = f"composant:{ecran}.{champ}"
    if cid not in g.noeuds:
        connus = ", ".join(c["id"].split(":", 1)[1] for c in champs(g=g)[:20])
        raise KeyError(f"Champ inconnu : {ecran}.{champ} (champs connus : {connus or 'aucun'}).")
    if len((regle or "").strip()) < 5:
        raise ValueError("Règle trop courte : décrire la contrainte (ex. « montant obligatoire, 2 décimales maximum »).")
    rid = "regle:" + re.sub(r"[^a-z0-9]+", "_", f"{champ} {regle}".lower()).strip("_")[:80]
    try:
        declarations.ajouter_noeud(rid, "regle", regle.strip()[:150], description=description[:1000],
                                   proprietes={"origine": "cursor", "champ": cid}, auteur="ia")
    except FileExistsError:
        pass
    try:
        declarations.ajouter_relation(cid, rid, "possede", auteur="ia", source="proposition Cursor")
    except PermissionError:
        pass
    return {"champ": cid, "regle": rid, "statut": "à valider",
            "message": "Règle proposée (à valider dans Application Intelligence › À valider) : les attributs du champ seront mis à jour après validation."}
