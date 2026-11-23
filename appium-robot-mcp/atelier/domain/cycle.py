"""Le cycle de référence : du parcours au TNR. Une seule définition, les autres en sont des vues.

Étapes d'un lot (écran Lots TNR, #lots) et statut unique d'un scénario. Les autres découpages de l'atelier restent
pour leurs écrans, mais se rattachent à celui-ci (DECOUPAGES) : un nouvel écran ou un nouveau statut se range ici
d'abord.

Glossaire — « parcours » désigne, selon le contexte :
  parcours utilisateur   PU-… : cadrage d'une Discovery (nom, point de départ, résultat attendu, profil de données)
  parcours (graphe)      nœud « parcours:… » du Knowledge Graph, proposé par un agent ou déclaré
  parcours métier        regroupement des tests d'un même parcours dans une suite Robot (suites_parcours.py)
  suivi de fonctionnalité  ancien « parcours de fonctionnalité » (intelligence/parcours_fonctionnalite.py), piloté par les US
Et « lot » : ce qu'on fait passer ensemble du parcours au TNR (generation/lots.py).
"""
from __future__ import annotations

ETAPES = (
    ("cadrer", "Cadrer", "Nom, application, point de départ, résultat attendu, profil de données", "#discovery/cadrage"),
    ("explorer", "Explorer", "Discovery : écrans, actions, données ; écrans validés", "#discovery"),
    ("scenariser", "Scénariser", "Un scénario par chemin, variantes en tableau d'exemples lié au jeu de données", "#bdd"),
    ("automatiser", "Automatiser et vérifier", "Génération exécutable, dry-run, run réel", "#lots"),
    ("publier", "Publier au TNR", "Tests Xray, plan TNR, campagne ; chaque run remonte dans Xray", "#lots"),
)

STATUTS_SCENARIO = ("Brouillon", "Validé", "Automatisé", "Vérifié", "Au TNR")

# rattachement des autres découpages à ce cycle (étape d'origine → étape de référence)
DECOUPAGES = {
    "chemin": {"decouvrir": "explorer", "concevoir": "scenariser", "automatiser": "automatiser", "executer": "publier"},
    "qualification": {"comprendre": "explorer", "comportement": "scenariser", "concevoir": "scenariser",
                      "automatiser": "automatiser", "executer": "publier", "evoluer": "publier"},
    "fonctionnalite": {"discovery": "explorer", "reconstruction": "cadrer", "couverture": "cadrer", "conception": "scenariser",
                       "validation": "scenariser", "generation": "automatiser", "qualification": "automatiser",
                       "execution": "publier", "analyse": "publier", "synchronisation": "publier"},
    "cycle_vie_test": {"brouillon": "scenariser", "redige": "scenariser", "a_automatiser": "automatiser",
                       "en_automatisation": "automatiser", "automatise": "publier"},
}


def etape(id_: str) -> dict:
    e = next((x for x in ETAPES if x[0] == id_), None)
    if not e:
        raise KeyError(f"Étape inconnue : {id_}")
    return dict(zip(("id", "titre", "role", "ecran"), e))


def reference(decoupage: str, etape_origine: str) -> dict:
    """Étape de référence d'une étape d'un autre découpage (ex. reference("chemin", "concevoir") → Scénariser)."""
    return etape(DECOUPAGES[decoupage][etape_origine])
