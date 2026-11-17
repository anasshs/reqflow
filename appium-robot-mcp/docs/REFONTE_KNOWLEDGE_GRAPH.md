# Refonte du Knowledge Graph — analyse préalable et plan de migration

Analyse du 17 novembre 2026, faite avant toute modification du modèle (section 10 de la spécification).
Les chiffres viennent du projet TAM (application SIMPLE), lus en lecture seule.

## 1. Ce qui existe aujourd'hui

- **Modèle** (`atelier/domain/graphe.py`) : 33 types de nœuds rangés en 7 catégories, 15 types de relations.
- **Identifiants** : `type:clé` (ex. `test:TAM-2173`, `user_story:DG-709`).
- **Stockage** : le graphe n'est pas stocké. Il est reconstruit à chaque affichage (avec un cache) depuis les sources locales :
  - la carte de l'application (Discovery) ;
  - le dépôt Robot ;
  - la copie locale Jira / Xray ;
  - les JDD et les contrats OpenAPI ;
  - les anomalies.
- **Ajouts manuels** : `connaissance/declarations.yaml`, historisés dans `connaissance/historique.jsonl`.
- **Provenance** : chaque nœud et chaque relation porte une provenance (`observé`, `déclaré`, `déduit`), une source en texte libre et un statut (`validé`, `à valider`). Une relation déduite non validée n'est jamais utilisée pour une décision. Ce principe est conservé.
- **Métadonnées d'une relation** : pas d'identifiant propre, pas de confiance, pas de dates, pas de système d'origine normalisé.

### Le graphe de TAM aujourd'hui

2 363 nœuds et 5 528 relations.

| Nœuds | Nombre |
|---|---|
| test | 1 346 |
| user_story | 560 |
| test_execution | 324 |
| epic | 55 |
| test_plan | 27 |
| module | 22 |
| regle (déduites, à valider) | 21 |
| bug | 5 |
| plateforme, application | 3 |

**Deux constats.**
- **L'univers applicatif est vide.** Aucun écran n'est cartographié sur TAM : il se remplira dès que tu brancheras le téléphone et que tu navigueras avec Discovery.
- **43 % des relations sont des « contient » génériques** (2 370 sur 5 528), avec six sens différents.

## 2. Correspondance des relations existantes

### Relations présentes sur TAM

| Relation actuelle | De → vers | Nombre | Sens réel | Relation cible | Sens cible |
|---|---|---|---|---|---|
| contient | test_plan → test | 1 132 | Le test est planifié dans le plan | `INCLUDED_IN_PLAN` | Test → Test Plan |
| contient | module → test | 714 | Le test porte le composant Jira | `BELONGS_TO` | Test → Module |
| contient | epic → user_story | 404 | Hiérarchie Jira | `PARENT_OF` | Epic → Story |
| contient | module → user_story | 92 | La story porte le composant Jira | `BELONGS_TO` | Story → Module |
| contient | user_story → regle | 21 | Règle extraite du texte (déduite) | `HAS_BUSINESS_RULE` | Story → Règle, `PROPOSED` |
| contient | module → bug | 3 | Le bug porte le composant | `BELONGS_TO` | Bug → Module |
| contient | application → plateforme | 2 | Plateformes de l'application | `RUNS_ON` (à ajouter) | Application → Plateforme |
| contient | user_story → user_story | 2 | Sous-tâche d'une story | `PARENT_OF` | Story → Sous-tâche |
| execute_par | test → test_execution | 2 844 | Le test est dans l'exécution | `EXECUTED_IN` | Test → Test Execution |
| teste_par | user_story → test | 199 | Lien de couverture Xray | `VERIFIES` | Test → Story (sens inversé) |
| teste_par | epic → test | 109 | Lien de couverture Xray | `VERIFIES` | Test → Epic ou Feature |
| teste_par | bug → test | 6 | Test lié à un bug | `VERIFIES` | Test → Bug |

Toutes ces relations viennent de Jira ou de Xray : elles deviennent `OFFICIAL`, sauf les 21 règles déduites, qui restent `PROPOSED`.

### Relations produites par le code, absentes de TAM faute de carte et de dépôt

| Relation actuelle | De → vers | Relation cible |
|---|---|---|
| contient | application → module, module → écran, application → écran | `HAS_MODULE` (à ajouter), `REALIZED_BY` proposé ou `BELONGS_TO` |
| contient | écran → locator, écran → composant | `CONTAINS_COMPONENT`, puis composant → locator en `USES_LOCATOR` |
| contient | resource → locator, resource → keyword, suite → test_robot | `DEFINES` (à ajouter) : organisation de fichiers, pas de sens métier |
| contient | fonctionnalité → champ (déduit) | `REALIZED_BY`, `PROPOSED` |
| navigue_vers | écran → écran | `NAVIGATES_TO` |
| utilise | composant → locator | `USES_LOCATOR` |
| utilise | keyword / test_robot → locator, bibliothèque | `USES_LOCATOR`, `USES_LIBRARY` (à ajouter) |
| utilise | exigence → endpoint (annotation `x-jira` du contrat OpenAPI) | `REALIZED_BY` : déclaré dans le contrat, donc repris tel quel |
| appelle | test_robot / keyword → keyword | `USES_KEYWORD` |
| depend_de | test_robot → jdd, jdd → requête | `USES_TEST_DATA` |
| depend_de | resource → resource, keyword → écran | `IMPORTS` (à ajouter), `USES_PAGE_OBJECT` |
| implemente_par | test → test_robot | `AUTOMATED_BY` |
| teste_par | écran → test (carte TNR) | `COVERS` (Test → Écran), source `EXECUTION_CENTER` |
| verifie | test_robot → champ | `COVERS` |
| possede | champ → règle (déduit) | `IMPLEMENTS_RULE`, `PROPOSED` |
| concerne, detecte_par, associe_a | anomalie → écran, test, règle | Conservées : hors du vocabulaire de la spécification, à nommer `AFFECTS`, `DETECTED_BY`, `RELATED_TO` |

### Relations ambiguës, à valider avant migration

1. **module → test et module → story (806 relations).** Le « module » actuel est le composant Jira. Deux lectures sont possibles :
   - le composant Jira devient directement le `BusinessModule` ;
   - le composant reste une donnée Jira, et le module métier est proposé à part puis relié.

   La spécification demande de ne pas créer de nœuds métier artificiels. Je recommande donc la première lecture, avec la source `JIRA`.
2. **epic → test (109 relations).** Sur TAM, 20 exigences sont de type Jira « Feature » et sont aujourd'hui rangées comme epic ou story. Il faut un type `JiraFeature` distinct avant de migrer ces liens.
3. **application → écran sans module.** Un écran sans module n'appartient à rien : ces relations sont à conserver comme simple inventaire (`HAS_SCREEN`), sans leur donner de sens métier.
4. **module → endpoint.** Ce rattachement suit l'étiquette (`tags`) du contrat OpenAPI quand elle porte le nom d'un module : à confirmer que l'étiquette désigne bien le module métier.

## 3. Correspondance des types de nœuds

| Type actuel | Type cible | Remarque |
|---|---|---|
| module | BusinessModule | Source : composant Jira ou module nommé dans Discovery |
| fonctionnalite, parcours, regle | BusinessFeature, UserJourney, BusinessRule | Déjà proposés par Discovery et Cursor |
| — | BusinessDomain, BusinessSubFeature, BusinessProcess | N'existent nulle part : à déclarer, ou à faire proposer par Cursor |
| epic, user_story, bug | JiraEpic, JiraStory, JiraBug | |
| — | JiraFeature | Donnée disponible (20 sur TAM), type à créer |
| — | AcceptanceCriterion | Aujourd'hui un bloc de texte dans la story : à découper |
| test, test_plan, test_execution | XrayTest, XrayTestPlan, XrayTestExecution | |
| test_set | XrayTestSet | Type prévu mais jamais alimenté (voir le tableau ci-dessous) |
| — | XrayTestRun, XrayPrecondition | Données déjà dans la copie locale, absentes du graphe (voir ci-dessous) |
| feature, scenario | BDDScenario | |
| test_robot, suite, keyword, jdd | AutomationScript, RobotSuite, Keyword, TestDataSet | |
| resource | PageObject | Seulement les resources de locators |
| application, ecran, composant, locator, endpoint, action | Application, Screen, UIComponent, Locator, APIEndpoint, UIAction | |
| — | ScreenState, ObservedBehavior, DiscoveredJourney, APIRequest, APIResponse | À produire par Discovery |

**Données Xray déjà dans la copie locale et non exploitées par le graphe :**

| Donnée | Volume sur TAM | Devient |
|---|---|---|
| Test Sets | 47, portés par 324 tests | Nœuds XrayTestSet et relations `MEMBER_OF` |
| Préconditions | 20 tests concernés | Nœuds XrayPrecondition et relations `HAS_PRECONDITION` |
| Test Runs (statut et date de fin) | Dans 316 exécutions sur 324 | Nœuds XrayTestRun et relations `HAS_TEST_RUN` |

Les objets Xray sont donc bien distincts à la source. C'est le graphe qui les aplatit.

## 4. Provenance : passage au modèle cible

| Aujourd'hui | source_system | validation_status | confidence |
|---|---|---|---|
| observé, source « instantané Xray » | XRAY | OFFICIAL | 1,0 |
| observé, source « exigences Jira » | JIRA | OFFICIAL | 1,0 |
| observé, source « carte » | APPLICATION_DISCOVERY | OFFICIAL | 1,0 |
| observé, source « dépôt », « tag Robot », JDD | AUTOMATION_STUDIO | OFFICIAL | 1,0 |
| observé, source « carte (TNR) », résultats | EXECUTION_CENTER | OFFICIAL | 1,0 |
| déclaré | saisie humaine | VALIDATED | 1,0 |
| déduit, à valider | AI_INFERENCE | PROPOSED | celle du calcul ou de Cursor |
| déduit, validé | AI_INFERENCE | VALIDATED | conservée |
| masqué ou écarté | inchangé | REJECTED | — |

**À ajouter sur chaque relation :** `id` stable, `source_reference` (clé Jira, fichier, session Discovery), `created_at`, `updated_at`, `last_observed_at` et `project_id`.

Une relation qui n'est plus observée à la reconstruction passe `OBSOLETE` au lieu de disparaître.

## 5. Points à trancher avant de coder

1. **Stockage.** La spécification propose PostgreSQL / Supabase. Aujourd'hui l'atelier est local (127.0.0.1) et ses données restent dans le dépôt du projet.
   - **Supabase** est un service en ligne : les exigences et les tests de la banque sortiraient du poste. C'est à valider par la sécurité avant tout.
   - **Ma recommandation** : les deux tables `graph_nodes` et `graph_edges`, avec les index demandés, dans un fichier **SQLite** par projet. SQLite est dans la bibliothèque standard, n'ajoute aucune dépendance, et le même schéma se porte tel quel sur PostgreSQL plus tard.
2. **Module métier.** Composant Jira = BusinessModule (ma recommandation), ou module métier séparé ?
3. **Domaine métier.** Ce niveau n'existe dans aucune source. Soit tu le déclares (une liste courte), soit Cursor le propose.
4. **Critères d'acceptation.** Découpage par règles (listes, « Étant donné… ») ou par Cursor, avec validation ?
5. **Identifiants.** `jira:CLE` et `xray:CLE` comme dans la spécification. Dans Xray Cloud, un test est aussi un ticket Jira : je propose `xray:` pour Test, Test Set, Test Plan, Test Execution et Précondition, et `jira:` pour le reste.

## 6. Ce que la refonte touche dans le code

- **Les relations sont utilisées partout** : « contient » apparaît dans 59 lignes Python, 6 lignes d'interface et 7 fichiers de test. Au total, les 15 types sont cités dans environ 160 lignes Python.
- **Modules concernés** :
  - couverture ;
  - analyse d'impact ;
  - plan de test ;
  - flux ;
  - Coverage Intelligence ;
  - Failure Analysis ;
  - outils MCP `knowledge_graph` et `plan_de_test` ;
  - écran du graphe.
- **Conséquence** : la migration doit passer par une couche de compatibilité. Les anciens noms restent lisibles pendant la transition, puis chaque module est basculé avec ses tests.

## 7. Plan par phases

Une phase à la fois, chacune livrable et testée.

| Phase | Contenu | Critères d'acceptation couverts |
|---|---|---|
| **0. Analyse** (faite) | Ce document : inventaire, correspondances, ambiguïtés | Préalable de la section 10 |
| **1. Ontologie et relations typées** (livrée le 17/11, voir section 9) | Vocabulaire contrôlé, métadonnées des relations, table de migration par paire de types, rapport de cohérence avant / après, couche de compatibilité | 2, 3, 9, 10 |
| **2. Testing Graph complet** | Test Set, Précondition, Test Run, Feature Jira, critères d'acceptation ; relations officielles Xray conservées telles quelles | 1, 4, 6 |
| **3. Application Graph** | Discovery produit états d'écran, composants, actions, comportements, parcours découverts ; fonctionne sans Jira | 1, 7 |
| **4. Business Graph et corrélation** | Domaines, fonctionnalités, sous-fonctionnalités ; Cursor propose les liens transverses avec justification et confiance, à valider | 3, 7 |
| **5. Stockage et synchronisation** | `graph_nodes` / `graph_edges`, isolement par projet, synchronisation incrémentale, relations obsolètes, historique | 10, 11 |
| **6. Navigation et services** | Cinq vues (fonctionnelle, applicative, couverture, technique, impact), filtres, API et outils MCP communs | 5, 8, 12 |

**Lien avec la vision du même jour** (`docs/VISION_APPLICATION_INTELLIGENCE.md`) : la « carte fonctionnelle » est la vue fonctionnelle du Business Graph, et le menu Knowledge Graph passe de trois à cinq vues. Les deux documents sont compatibles.

## 8. Rôle de Discovery (téléphone branché)

- **Aujourd'hui sur TAM** : l'univers applicatif est vide. Le graphe ne contient que Jira et Xray.
- **Pendant ta navigation** : chaque écran visité crée un écran, ses composants, ses locators et la transition empruntée. Ces éléments sont observés, donc officiels côté application.
- **Après la navigation** : Cursor propose les liens transverses (story ↔ écran, critère ↔ comportement, test ↔ parcours), chacun avec sa justification et sa confiance. Rien n'entre dans la traçabilité avant ta validation.
- **Sans documentation Jira** : Discovery suffit à construire l'Application Graph. Les fonctionnalités découvertes sans story apparaissent comme « découvertes sans documentation ».

## 9. Phase 1 livrée (17 novembre 2026)

**Décisions appliquées** (recommandations de la section 5, modifiables) : composant Jira = module métier ; identifiants `jira:` / `xray:` ; le stockage en tables reste pour la phase 5.

**Ce qui est en place**
- **Ontologie** (`atelier/domain/ontologie.py`) : 48 types de nœuds dans les trois univers et 44 relations typées. Les 29 relations de la spécification y sont ; 15 sont des extensions marquées comme telles, nécessaires pour ne perdre aucune relation existante (`RUNS_ON`, `DEFINES`, `HAS_LOCATOR`…).
- **Migration par paire de types** : chaque relation historique est traduite selon les types qu'elle relie. Le sens est inversé quand le métier l'exige (un test vérifie une exigence).
- **Provenance** : chaque nœud et chaque relation porte son système d'origine, son statut de validation et sa confiance. Une proposition sans confiance calculée a une confiance vide : aucune valeur n'est inventée.
- **Feature Jira** : le type Jira d'origine est maintenant gardé. Une « fonctionnalité » qui porte une clé Jira est une Feature Jira, pas un nœud métier.
- **Services communs** :
  - `GET /api/graphes/ontologie` : le vocabulaire ;
  - `GET /api/graphes/property-graph` : le graphe au format cible (nœuds et arêtes) ;
  - `GET /api/graphes/migration` : le rapport de cohérence.
- **Affichage** : le détail d'un nœud et d'une relation montre le type typé, la relation métier dans son sens, le système d'origine et le statut (officiel, validé, proposé).

**Résultat sur TAM**

| Relation historique | Devient | Nombre |
|---|---|---|
| execute_par | `EXECUTED_IN` | 2 844 |
| contient | `INCLUDED_IN_PLAN` | 1 132 |
| contient | `BELONGS_TO` (composant Jira) | 809 |
| contient | `PARENT_OF` | 406 |
| teste_par | `VERIFIES` (sens inversé) | 314 |
| contient | `HAS_BUSINESS_RULE` (proposé) | 21 |
| contient | `RUNS_ON` (extension) | 2 |

- 5 528 relations avant, 5 528 après ; 2 363 nœuds avant et après.
- 5 507 relations officielles, 21 proposées ; aucune relation générique restante.
- Les 109 liens « epic → test » étaient en réalité des liens Feature → test : ils sont maintenant typés `VERIFIES` vers une Feature Jira.

**Ce qui n'est pas encore fait**
- Les modules (couverture, impact, plan de test…) lisent encore les relations historiques : la traduction se fait à la lecture. Ils seront basculés un par un dans les phases suivantes.
- Les dates d'une relation (`created_at`, `updated_at`, `last_observed_at`) ne sont remplies que si la source est datée. Elles seront réelles avec le stockage (phase 5), comme les statuts `OBSOLETE` et `REJECTED`.
- Test Set, Précondition, Test Run et critères d'acceptation : phase 2.
