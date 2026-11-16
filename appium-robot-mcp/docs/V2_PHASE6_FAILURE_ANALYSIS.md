# V2 — Phase 6 : Failure Analysis relié à la connaissance

## Existant réutilisé
Collecte des échecs des runs réels, regroupement par signature, étape fautive et diagnostic du locator, décisions
humaines, association Jira, retests ; Knowledge Graph (champs, anomalies — phase 5).

## Ajouts (`atelier/execution/echecs_connaissance.py`, lecture seule)
- **Localisation** : étape fautive → locator → référentiel → écran et composant ; calculée une fois et mémorisée dans
  le suivi de l'échec (aucune relecture des runs à l'affichage). Une étape sans locator (initialisation, données)
  reste « sans écran » : rien n'est inventé.
- **Échecs par composant** : nombre, runs, tests, première / dernière date, champ ou non.
- **Causes historisées** : catégorie confirmée par l'automaticien (sinon proposée), datée, avec l'anomalie Jira associée.
- **Régression** : test réussi au run précédent, en échec maintenant ; **régression récurrente** : au moins deux
  régressions sur le même composant (ou le même test) dans des runs différents.
- **Anomalies déjà connues** sur l'écran (bugs Jira et anomalies du graphe) : à vérifier avant d'en créer une.
- **Échecs similaires** : en plus du groupe par signature, les autres échecs du même composant (toutes signatures).

## Où
- Failure Analysis › Causes et corrections › **Par composant** (bouton « Localiser les échecs »).
- Failure Analysis › Investigation : bloc **Dans la connaissance** (composant, champ, régression, autres échecs du
  composant, anomalies connues).
- MCP : `failure_connaissance(echec_id="")` (88 outils, aucun existant modifié) ; règle Cursor `failure-analysis`.
- API : `GET /api/echecs/composants`, `POST /api/echecs/localiser`, `GET /api/echecs/connaissance?id=`.

## Tests
`tests/test_echecs_connaissance.py` : localisation mémorisée, regroupement, régressions récurrentes, causes,
anomalies connues, échec non localisable, outil MCP.
