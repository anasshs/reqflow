# V2 — Phase 3 : couverture avancée (parcours et composants UI)

## Existant réutilisé
Couverture des exigences et Coverage Intelligence (documentaire, traçabilité, exécution, automatisation) ; Knowledge
Graph (écran → locator, keyword → locator, test Robot → keyword, test Xray → test Robot, résultats des runs,
fonctionnalités, parcours). Aucun second référentiel : tout est calculé sur le graphe.

## Niveaux (`atelier/intelligence/couverture_avancee.py`) — chaque niveau inclut le précédent
| Niveau | Définition |
|---|---|
| découvert | présent dans la carte (Discovery, cartographie des runs, import des .resource) |
| associé | utilisé par au moins un test Robot (keyword → locator, appels de keywords suivis) ; pour un écran, aussi via une fonctionnalité dont une US a un test Xray (association **déduite**, signalée) |
| automatisé | utilisé par un test Robot rattaché à un test Xray (clé en tag) |
| exécuté | un de ces tests a au moins une exécution réelle connue (« effectivement vérifié ») |
| réussi | dernière exécution réussie (PASS) |

- Composant = une clé métier d'un écran, toutes plateformes confondues (Android, iOS, web).
- Écran = niveau du meilleur de ses composants ; parcours = niveau de sa moins bonne étape, avec le % d'étapes associées.
- Limite assumée : pour les tests manuels, l'étape Xray est du texte libre ; aucune couverture au niveau composant
  n'est inventée.

## Indicateurs
Couverture des écrans, des composants, des parcours ; composants automatisés ; composants en succès ; écrans,
composants (hors liste rouge) et parcours sans test. Chaque indicateur porte son détail (n / total).

## Où
- Application Intelligence › Couverture › onglet **Parcours et UI** (niveaux, écrans, parcours, sans test).
- Tableau de bord : carte « Couverture fonctionnelle et UI ».
- MCP : `coverage_ui(module="", detail=False)` (83 outils, aucun existant modifié). API : `GET /api/couverture-avancee`.

## Tests
`tests/test_couverture_avancee.py` : graphe construit avec un composant par niveau (associé sans clé Xray, exécuté
en échec, réussi), écrans et parcours, association déduite par fonctionnalité, filtre de module, outil MCP.
