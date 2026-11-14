# API Xray Cloud — état de la vérification

**Statut au 2026-11-14 : schéma VÉRIFIÉ par introspection, conforme** (rapport : `docs/XRAY_API_resultat.md`,
lancé sur un poste connecté à Xray Cloud global). Les 4 requêtes, les 8 mutations et `AttachmentDataInput`
existent avec exactement les arguments passés par le client, sans argument obligatoire oublié ; l'authentification
REST (`/authenticate`) répond. Reste à confirmer par un essai réel (section « Essai réel ») : champs sélectionnés
dans les réponses, sémantique (création immédiate des test runs, statuts acceptés, format des dates, taille des
preuves) et l'import REST Robot, que l'introspection GraphQL ne couvre pas.

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
| `getTests(jql: String, limit: Int)` → `results { issueId gherkin unstructured testType { name kind } steps { action data result } jira(fields: [...]) }` | `xray_get_test`, `search_tests`, `test_ids`, `resolve` | limite max par appel (le client plafonne à 100) ; noms `gherkin`, `unstructured`, `steps.action/data/result` ; forme de `jira(fields:)` | noms et arguments conformes (introspection 2026-11-14) ; reste : sémantique à l'essai réel |
| `getTestPlans(jql, limit)` → `results { issueId jira(fields: ["key","summary"]) }` | `resolve` | existence, arguments | noms et arguments conformes (introspection 2026-11-14) ; reste : sémantique à l'essai réel |
| `getTestExecutions(jql, limit)` → idem | `resolve` | existence, arguments | noms et arguments conformes (introspection 2026-11-14) ; reste : sémantique à l'essai réel |
| `getTestRuns(testIssueIds: [String], testExecIssueIds: [String], limit: Int)` → `results { id test { issueId } }` | `test_runs` | noms des arguments, type de `id` (le client le traite comme `String`) | noms et arguments conformes (introspection 2026-11-14) ; reste : sémantique à l'essai réel |
| requête listant les statuts de test run | — | sert à remplacer `XRAY_STATUTS` par une lecture | existe : `getStatuses` (et `getStatus`, `getStepStatus(es)`) ; signature à relever avec la prochaine vérification (l'outil l'affiche désormais) |

## GraphQL — mutations

| Appel (tel qu'utilisé) | Où | Points précis à vérifier | Résultat |
|---|---|---|---|
| `createTestPlan(testIssueIds: [String], jira: JSON!)` → `testPlan { issueId jira(fields: ["key"]) } warnings` | préparation | forme de `jira` (`{"fields": {"summary", "project": {"key"}}}`) | noms et arguments conformes (introspection 2026-11-14) ; reste : sémantique à l'essai réel |
| `createTestExecution(testIssueIds, testEnvironments: [String], jira: JSON!)` → `testExecution { issueId jira(fields: ["key"]) } warnings` | préparation | `testEnvironments` accepté à la création ; les test runs sont-ils créés immédiatement (le client les relit juste après) ? | noms et arguments conformes (introspection 2026-11-14) ; reste : sémantique à l'essai réel |
| `addTestExecutionsToTestPlan(issueId: String!, testExecIssueIds: [String])` → `addedTestExecutions warning` | préparation | nom du champ `warning` (singulier ?) | noms et arguments conformes (introspection 2026-11-14) ; reste : sémantique à l'essai réel |
| `addTestsToTestPlan(issueId: String!, testIssueIds: [String])` → `addedTests warning` | préparation | idem | noms et arguments conformes (introspection 2026-11-14) ; reste : sémantique à l'essai réel |
| `addTestsToTestExecution(issueId: String!, testIssueIds: [String])` → `addedTests warning` | préparation | idem | noms et arguments conformes (introspection 2026-11-14) ; reste : sémantique à l'essai réel |
| `updateTestRunStatus(id: String!, status: String!)` (sans sélection) | début / fin de test | renvoie-t-il un scalaire (sinon il faut une sélection) ; valeurs de statut acceptées (statuts personnalisés) | noms et arguments conformes (introspection 2026-11-14) ; reste : sémantique à l'essai réel |
| `updateTestRun(id: String!, startedOn: String, finishedOn: String, comment: String)` → `warnings` | début / fin de test, qualification | `startedOn` / `finishedOn` / `comment` acceptés par CETTE mutation (ou mutations dédiées) ; format de date attendu (le client envoie ISO 8601 avec fuseau) | noms et arguments conformes ; **essai réel 2026-11-14 : `finishedOn` refusé tant que le statut n'est pas final** (« Cannot set finishedOn because test run status is not final ») → le client envoie désormais le statut final avant les heures et le commentaire |
| `addEvidenceToTestRun(id: String!, evidence: [AttachmentDataInput]!)` → `addedEvidence warnings` ; `AttachmentDataInput { filename mimeType data }` (base64) | fin de test en échec | noms des champs, taille maximale d'une preuve | noms et arguments conformes (introspection 2026-11-14) ; reste : sémantique à l'essai réel |

## REST

| Appel | Points précis à vérifier | Résultat |
|---|---|---|
| `POST {base}/authenticate` corps `{"client_id", "client_secret"}` → jeton (chaîne JSON) | durée de vie du jeton (le client le garde pour toute la durée d'un synchroniseur) | fonctionne (2026-11-14) ; durée de vie à confirmer |
| `POST {base}/import/execution/robot?projectKey=&testExecKey=&testPlanKey=` corps output.xml, `Content-Type: application/xml` | paramètres acceptés (`testEnvironments`, `revision`, `fixVersion`…), Content-Type exact, forme de la réponse (`key`) | à vérifier |
| Base `https://xray.cloud.getxray.app/api/v2` (réglable par `XRAY_BASE_URL`) | URL régionales (US / EU / AU) à proposer si le tenant n'est pas sur l'instance globale | instance globale fonctionnelle pour ce tenant (2026-11-14) |

## Jira (instantané du patrimoine, espaces de travail)

| Appel | Points précis à vérifier | Résultat |
|---|---|---|
| `POST {JIRA_BASE_URL}/rest/api/3/search/jql` corps `{jql, fields, maxResults, nextPageToken}` → `issues`, `nextPageToken` | endpoint actuel de recherche Jira Cloud (remplace `/search`), pagination | à vérifier |
| champs `summary, issuetype, labels, status, components, priority, issuelinks, parent` | `parent` pour l'epic d'une user story ; composants comme module | à vérifier |
| lien Xray test ↔ exigence dans `issuelinks` (type dont le nom contient « test ») | nom exact du type de lien créé par Xray sur le site | à vérifier |

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


## Essai réel du 2026-11-14 (projet de recette, 1 test, 1 exécution existante)
- Résolution du ticket (Test / Test Execution), ajout du test à l'exécution, lecture du test run : **OK**.
- Erreur de transport (HTTP 502) absorbée par le nouvel essai automatique : **OK**.
- `updateTestRun(finishedOn…)` avant `updateTestRunStatus(final)` : **refusé par Xray** → ordre corrigé
  (statut final, puis heures et commentaire, puis preuves) ; le faux serveur des tests reproduit cette règle.
- Un refus métier GraphQL n'est plus réessayé (inutile) : erreur journalisée, événement conservé pour `xray-sync`.
- Sous Windows, l'argument du listener (chemin `C:\…`) était coupé par Robot : séparateur « ; » utilisé.
- Après correction et `xray-sync` : test run **FAILED**, heures, commentaire et capture jointe **confirmés** dans Xray.
- `output.xml`, `log.html`, `report.html` n'existent qu'après la fin de Robot (donc après le listener) : ils sont
  désormais zippés (`robot-resultats.zip`) et joints aux test runs en fin de run, via le journal (rejouable).
  `XRAY_ARTEFACTS` = `tous` (défaut) | `echecs` | `aucun` ; `XRAY_ARTEFACTS_MAX_MO` (défaut 10) plafonne l'archive.
- Restent à confirmer : taille maximale acceptée par `addEvidenceToTestRun`, statuts personnalisés (`getStatuses`).

## Publication BDD (Test Design, modes B / C) — schéma vérifié le 2026-11-14
| Appel | Usage | Statut |
|---|---|---|
| `createTest(testType: {name: "Cucumber"}, gherkin: String, jira: JSON!)` → `test { issueId jira(fields: ["key"]) } warnings` | création d'un test Cucumber (mode C) | nom et arguments conformes (introspection 2026-11-14) ; reste : essai réel |
| `updateGherkinTestDefinition(issueId: String!, gherkin: String!)` | mise à jour du Gherkin (mode B) | nom et arguments conformes (introspection 2026-11-14) ; reste : essai réel |
| `getTests(jql) { results { issueId gherkin testType { name } } }` | lecture du Gherkin pour détecter les conflits | même requête que l'instantané, champ `gherkin` à confirmer |

Variables Jira associées : `JIRA_CHAMP_CRITERES` (champ des critères d'acceptation, ex. `customfield_<n>`),
`JIRA_TYPE_ANOMALIE` (défaut `Bug`), `JIRA_LIEN_ANOMALIE` (défaut `Relates`).

## Statuts de test run (lecture vérifiée le 2026-11-14)
`getStatuses(projectId: String)` → `[Status { name description final color coverageStatus }]` ; `projectId` est
l'identifiant numérique Jira du projet (lu sur un test : `jira(fields: ["project"])`).
Contrôle en lecture seule : `python -m atelier xray-statuts --projet <CLÉ>` compare `XRAY_STATUTS` aux statuts réels
(PASS / FAIL doivent viser un statut final, EXECUTING un statut non final). Les statuts non finaux
(`XRAY_STATUTS_NON_FINAUX`, défaut `TODO,EXECUTING`) ne reçoivent jamais d'heure de fin : un test SKIP (→ TODO)
n'est donc plus refusé par Xray.
