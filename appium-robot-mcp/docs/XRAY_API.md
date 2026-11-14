# API Xray Cloud — état de la vérification

**Statut au 2026-11-14 : AUCUN appel n'est vérifié.** La documentation officielle
(`docs.getxray.app`, `xray.cloud.getxray.app/doc/graphql`) n'était pas accessible depuis
l'environnement de développement (hôtes bloqués par le réseau). Rien ci-dessous n'est déduit
de mémoire : chaque ligne reste « à vérifier » tant que la colonne Résultat n'est pas remplie
à partir d'une source officielle ou de l'introspection du schéma réel.

## Comment vérifier (poste qui accède à Xray)

```bash
export XRAY_CLIENT_ID=... XRAY_CLIENT_SECRET=...      # + XRAY_CA_BUNDLE derrière le proxy
python -m atelier xray-verifier --sortie docs/XRAY_API_resultat.md
```

La commande interroge le schéma GraphQL réel (introspection) et, pour chaque appel du client,
indique : présent ou non, arguments passés que le schéma ne connaît pas, arguments obligatoires
du schéma que le client ne passe pas, et les champs de `AttachmentDataInput`. Elle liste aussi
les requêtes du schéma qui concernent les statuts. Code retour 0 = conforme, 1 = écarts.
Reporter ensuite le résultat dans le tableau ci-dessous (date + source) et corriger le client
(`atelier/integrations/xray/__init__.py`) si besoin ; la table des appels vérifiés est dans
`atelier/integrations/xray/verification.py`.

Limite : l'introspection ne vérifie que les noms et les arguments, pas les champs sélectionnés
dans les réponses (ex. `testExecution { issueId jira(fields: ["key"]) }`) ni la sémantique. Un
premier run réel sur un projet de recette Xray reste nécessaire (voir « Essai réel »).

## GraphQL — requêtes

| Appel (tel qu'utilisé) | Où | Points précis à vérifier | Résultat |
|---|---|---|---|
| `getTests(jql: String, limit: Int)` → `results { issueId gherkin unstructured testType { name kind } steps { action data result } jira(fields: [...]) }` | `xray_get_test`, `search_tests`, `test_ids`, `resolve` | limite max par appel (le client plafonne à 100) ; noms `gherkin`, `unstructured`, `steps.action/data/result` ; forme de `jira(fields:)` | à vérifier |
| `getTestPlans(jql, limit)` → `results { issueId jira(fields: ["key","summary"]) }` | `resolve` | existence, arguments | à vérifier |
| `getTestExecutions(jql, limit)` → idem | `resolve` | existence, arguments | à vérifier |
| `getTestRuns(testIssueIds: [String], testExecIssueIds: [String], limit: Int)` → `results { id test { issueId } }` | `test_runs` | noms des arguments, type de `id` (le client le traite comme `String`) | à vérifier |
| requête listant les statuts de test run (nom inconnu) | — | existe-t-elle ? par projet ? (sert à remplacer `XRAY_STATUTS` par une lecture) | à vérifier |

## GraphQL — mutations

| Appel (tel qu'utilisé) | Où | Points précis à vérifier | Résultat |
|---|---|---|---|
| `createTestPlan(testIssueIds: [String], jira: JSON!)` → `testPlan { issueId jira(fields: ["key"]) } warnings` | préparation | forme de `jira` (`{"fields": {"summary", "project": {"key"}}}`) | à vérifier |
| `createTestExecution(testIssueIds, testEnvironments: [String], jira: JSON!)` → `testExecution { issueId jira(fields: ["key"]) } warnings` | préparation | `testEnvironments` accepté à la création ; les test runs sont-ils créés immédiatement (le client les relit juste après) ? | à vérifier |
| `addTestExecutionsToTestPlan(issueId: String!, testExecIssueIds: [String])` → `addedTestExecutions warning` | préparation | nom du champ `warning` (singulier ?) | à vérifier |
| `addTestsToTestPlan(issueId: String!, testIssueIds: [String])` → `addedTests warning` | préparation | idem | à vérifier |
| `addTestsToTestExecution(issueId: String!, testIssueIds: [String])` → `addedTests warning` | préparation | idem | à vérifier |
| `updateTestRunStatus(id: String!, status: String!)` (sans sélection) | début / fin de test | renvoie-t-il un scalaire (sinon il faut une sélection) ; valeurs de statut acceptées (statuts personnalisés) | à vérifier |
| `updateTestRun(id: String!, startedOn: String, finishedOn: String, comment: String)` → `warnings` | début / fin de test, qualification | `startedOn` / `finishedOn` / `comment` acceptés par CETTE mutation (ou mutations dédiées) ; format de date attendu (le client envoie ISO 8601 avec fuseau) | à vérifier |
| `addEvidenceToTestRun(id: String!, evidence: [AttachmentDataInput]!)` → `addedEvidence warnings` ; `AttachmentDataInput { filename mimeType data }` (base64) | fin de test en échec | noms des champs, taille maximale d'une preuve | à vérifier |

## REST

| Appel | Points précis à vérifier | Résultat |
|---|---|---|
| `POST {base}/authenticate` corps `{"client_id", "client_secret"}` → jeton (chaîne JSON) | durée de vie du jeton (le client le garde pour toute la durée d'un synchroniseur) | à vérifier |
| `POST {base}/import/execution/robot?projectKey=&testExecKey=&testPlanKey=` corps output.xml, `Content-Type: application/xml` | paramètres acceptés (`testEnvironments`, `revision`, `fixVersion`…), Content-Type exact, forme de la réponse (`key`) | à vérifier |
| Base `https://xray.cloud.getxray.app/api/v2` (réglable par `XRAY_BASE_URL`) | URL régionales (US / EU / AU) à proposer si le tenant n'est pas sur l'instance globale | à vérifier |

## Statuts de test run personnalisés

Les noms envoyés à Xray ne sont plus figés dans le code : table par défaut
`PASS→PASSED, FAIL→FAILED, SKIP/NOT RUN→TODO, EXECUTING→EXECUTING`, remplaçable par
`XRAY_STATUTS` (JSON, ex. `{"FAIL": "ECHEC"}`). L'agrégation de plusieurs tests Robot sur une
même clé Xray se fait sur les statuts Robot (FAIL > PASS > SKIP), donc reste juste quels que
soient les noms Xray. Reste à faire après vérification : lire la liste des statuts du projet
dans Xray (si la requête existe) et refuser un run dont un statut configuré n'existe pas.

## Essai réel (après la vérification par introspection)

Sur un projet de recette Xray, avec une suite de 2 tests tagués : `run_robot(..., xray_ticket="<PROJET>")`
puis contrôler dans Xray : plan et exécution créés, test runs EXECUTING puis statut final,
heures de début / fin, commentaire et capture sur l'échec ; recommencer avec un Test Plan,
puis une Test Execution existants.
