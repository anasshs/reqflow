# V2 — Phase 5 : Knowledge Graph — Champ et Anomalie

## Existant réutilisé
Types `composant`, `regle`, `bug` ; locators de la carte ; dépôt Robot (test → keyword → locator) ; Failure Analysis
(échecs, décisions, associations Jira) ; déclarations et boîte À valider pour tout enrichissement.

## Champ = composant de genre « champ » (`atelier/discovery/connaissance.py`)
- Créé à partir de la carte pour chaque zone de saisie (type champ / case / liste, classe « contrôlée », clé `champ_…`).
- Attributs : nom technique, libellé, type, format, obligatoire, valeur par défaut, règles de validation, messages
  d'erreur, écran, fonctionnalité, plateformes, source, confiance, statut.
- Relations : écran **contient** champ ; fonctionnalité **contient** champ (déduit de l'écran) ; champ **possède** règle
  (déclarée, ou **déduite** du texte de la règle → à valider) ; test Robot **vérifie** champ (keyword → locator) ;
  champ **utilise** ses locators.
- Obligatoire / format / valeur par défaut sont lus dans le texte des règles liées ; « non renseigné » sinon.

## Anomalie = nœud « bug » enrichi
- Source : bugs Jira du patrimoine + échecs de Failure Analysis confirmés « défaut applicatif » ou associés à une
  anomalie Jira. Au moment de la décision, Failure Analysis enregistre le contexte (test, exécution, date, message,
  étape fautive, locator, écran, composant) : le graphe le lit sans relire les runs.
- Attributs : id interne, id Jira, titre, type, statut, test, exécution, date de détection, message, source,
  confiance, statut de validation, historique.
- Relations : anomalie **concerne** écran / composant / fonctionnalité ; **est détectée par** test Robot et test
  Xray ; **est associée à** l'exécution (nœud résultat).
- Sans clé Jira : identifiant stable `bug:FA-…`, confiance 0,8 si confirmée ; rien n'est créé dans Jira ici.

## Vocabulaire ajouté (aucun type existant modifié)
Relations `possede`, `concerne`, `detecte_par`, `associe_a`.

## Où
- Application Intelligence › Connaissance › **Champs et anomalies**.
- MCP : `knowledge_entites(type, ecran)` (consulter) et `knowledge_proposer_champ(ecran, champ, regle)` (proposer une
  règle de validation, à valider) — 87 outils, aucun existant modifié ; règle Cursor `knowledge-graph` mise à jour.
- API : `GET /api/connaissance/entites?type=champ|anomalie`.

## Tests
`tests/test_champs_anomalies.py` : champ enrichi (règle déduite à valider, obligatoire / format / défaut, messages,
fonctionnalité, tests), anomalies depuis Failure Analysis (relations, confiance, identifiants stables, pas de
doublon), contexte enregistré à la décision, proposition de règle par Cursor.
