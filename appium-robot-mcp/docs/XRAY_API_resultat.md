# Vérification de l'API Xray — 2026-11-14 14:54

Source : introspection GraphQL de `https://xray.cloud.getxray.app/api/v2` (lancée sur le poste de l'utilisateur).

Résultat global : **conforme**

| Appel | Présent | Arguments inconnus du schéma | Obligatoires non passés |
|---|---|---|---|
| requete `getTests` | oui | — | — |
| requete `getTestPlans` | oui | — | — |
| requete `getTestExecutions` | oui | — | — |
| requete `getTestRuns` | oui | — | — |
| mutation `createTestPlan` | oui | — | — |
| mutation `createTestExecution` | oui | — | — |
| mutation `addTestExecutionsToTestPlan` | oui | — | — |
| mutation `addTestsToTestPlan` | oui | — | — |
| mutation `addTestsToTestExecution` | oui | — | — |
| mutation `updateTestRunStatus` | oui | — | — |
| mutation `updateTestRun` | oui | — | — |
| mutation `addEvidenceToTestRun` | oui | — | — |
| type `AttachmentDataInput` | oui | — | — |

Requêtes du schéma liées aux statuts : `getStatus`, `getStatuses`, `getStepStatus`, `getStepStatuses`
