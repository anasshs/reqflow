"""Le Knowledge Graph autour d'un nœud, en texte (lecture seule) : pour relire ce qu'une Discovery a créé.

    python -m atelier.discovery.graphe_texte parcours:authentification      # le parcours et son voisinage (2 sauts)
    python -m atelier.discovery.graphe_texte parcours:authentification 1    # voisinage direct seulement
    python -m atelier.discovery.graphe_texte                                 # résumé : nœuds et relations par type

Le projet est celui de ROBOT_PROJECT_DIR (comme l'atelier). Pour chaque nœud : type, libellé, statut et provenance ;
pour chaque relation : type, sens, statut et provenance. Aucune valeur de donnée de test n'est affichée.
"""
from __future__ import annotations

import sys
from collections import Counter

PROPRIETES_VUES = ("module", "url", "chemin", "plateformes", "nom", "titre", "fichier")


def voisinage(nid: str, sauts: int = 2) -> dict:
    from atelier.discovery import connaissance

    g = connaissance.construire()
    if nid not in g.noeuds:
        proches = [n for n in g.noeuds if nid.split(":")[-1].lower() in n.lower()][:10]
        raise KeyError(f"Nœud inconnu : {nid}" + (f" (proches : {', '.join(proches)})" if proches else ""))
    vus, front = {nid}, {nid}
    rels = {}
    for _ in range(max(1, sauts)):
        suivant = set()
        for r in g.relations.values():
            if r.de in front or r.vers in front:
                rels[r.id] = r
                for x in (r.de, r.vers):
                    if x not in vus:
                        vus.add(x)
                        suivant.add(x)
        front = suivant
    return {"noeuds": [g.noeuds[n] for n in sorted(vus) if n in g.noeuds], "relations": list(rels.values())}


def _noeud(n) -> str:
    props = {k: v for k, v in (n.proprietes or {}).items() if k in PROPRIETES_VUES and v not in ("", None, [], {})}
    return (f"  {n.id}  [{n.type}] « {n.libelle} » · {n.statut} · {n.provenance}"
            + (f" · {props}" if props else ""))


def _relation(r) -> str:
    return f"  {r.de}  --{r.type}-->  {r.vers}  · {r.statut} · {r.provenance}"


def principal(argv: list[str]) -> int:
    from atelier.discovery import connaissance

    if not argv:
        g = connaissance.construire()
        print(f"{len(g.noeuds)} nœud(s), {len(g.relations)} relation(s)")
        print("Nœuds par type :", dict(Counter(n.type for n in g.noeuds.values()).most_common()))
        print("Relations par type :", dict(Counter(r.type for r in g.relations.values()).most_common()))
        a_valider = [n for n in g.noeuds.values() if n.statut != "validé"] + [r for r in g.relations.values() if r.statut != "validé"]
        print(f"À valider : {len(a_valider)}")
        print("Parcours :", ", ".join(n for n, x in g.noeuds.items() if x.type == "parcours") or "aucun")
        return 0
    try:
        v = voisinage(argv[0], int(argv[1]) if len(argv) > 1 else 2)
    except (KeyError, ValueError) as e:
        print(str(e).strip("'\""))
        return 1
    print(f"NŒUDS ({len(v['noeuds'])})")
    for n in v["noeuds"]:
        print(_noeud(n))
    print(f"\nRELATIONS ({len(v['relations'])})")
    for r in sorted(v["relations"], key=lambda r: (r.type, r.de, r.vers)):
        print(_relation(r))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # console Windows : accents lisibles
    except (AttributeError, ValueError):
        pass
    sys.exit(principal(sys.argv[1:]))
