# AI Test Engineering Platform — Espaces de travail de l'automaticien (conception fonctionnelle)

Document de référence fourni par l'équipe (2026-11-14). L'état de réalisation est suivi dans
docs/ROADMAP.md (section « Espaces de travail »).

## 1. Vision générale

Faire évoluer le rôle de l'automaticien d'un producteur de scripts vers un responsable de la
conception, de la supervision et de la qualité des automatisations pilotées par l'IA : comprendre
l'application, analyser le patrimoine Xray, sélectionner les tests à automatiser, valider les
scénarios BDD, contrôler les scripts générés, analyser les échecs, piloter la qualité globale.
L'automaticien n'est pas obligé de rédiger chaque script Robot Framework. Son rôle : définir et
valider la stratégie ; contrôler la compréhension fonctionnelle ; valider les scénarios BDD ;
superviser la génération technique ; corriger et approuver les propositions de l'IA ; analyser et
qualifier les échecs ; garantir la fiabilité du patrimoine ; piloter indicateurs et couverture.

**Principe fondamental : l'IA propose, construit et exécute. L'automaticien contrôle, arbitre,
valide et améliore.**

## 2. Espaces

Dashboard, Application Intelligence, Test Strategy, Test Design, Automation Studio, Execution
Center, Quality Governance. Chaque espace propose des vues graphiques interactives et
opérationnelles (explorer, modifier, relier, analyser, piloter), pas de simples illustrations.

## 3. Application Intelligence — Application Knowledge Graph

Point central de connaissance de l'application.

- Nœuds — APPLICATION : application, plateforme, environnement, version. FONCTIONNEL : module,
  fonctionnalité, parcours métier, écran, action utilisateur, règle métier, rôle utilisateur.
  TECHNIQUE : composant, locator, keyword, endpoint API, entité de données. JIRA : epic, user
  story, bug. XRAY : test, test plan, test set, test execution. BDD : feature, scenario, step.
  AUTOMATION : robot suite, script, JDD, keyword, résultat d'exécution.
- Relations : contient, navigue vers, dépend de, appelle, vérifie, couvre, est implémenté par, est
  testé par, est exécuté par, impacte.
- Actions : ajouter / modifier / supprimer un nœud ou une relation, renommer, fusionner,
  développer les dépendances, filtrer par catégorie, rechercher, afficher les propriétés, comparer
  deux versions, identifier les dépendances, analyser l'impact d'une modification, demander une
  analyse à l'IA, exporter.
- Panneau de propriétés : nom, type, description, identifiant, source de découverte, version,
  plateforme, éléments liés, tests Xray, scénarios BDD, scripts automatisés, historique, niveau de
  confiance.

## 4. Test Strategy

### 4.1 Xray Coverage Graph
Traçabilité Epic → User Story → Fonctionnalité → Test Xray → Scénario BDD → Script automatisé →
Résultat. Éléments : epics, user stories, modules, fonctionnalités, tests manuels / automatisés /
BDD, test plans, test executions, scores d'automatisation, criticité, niveau de couverture.
Actions : explorer, filtrer (module, criticité, statut, plateforme), afficher tests manuels /
automatisés, identifier les tests redondants et les fonctionnalités non couvertes, comparer la
couverture, analyser une fonctionnalité, sélectionner des tests, créer un lot d'automatisation,
générer un plan d'automatisation, exporter.

### 4.2 Automation Candidates
Clé, nom, module, type, criticité, fréquence d'exécution, stabilité, faisabilité, données,
complexité de maintenance, score, recommandation IA (à automatiser / à investiguer / à reporter /
à ne pas automatiser / déjà automatisé), chaque recommandation expliquée par des éléments
observables et vérifiables. Actions : consulter, analyser, dépendances, tests similaires, modifier
la priorité, accepter / refuser, ajouter au backlog, lancer la construction.

## 5. Test Design

### 5.1 Journey Graph
Parcours utilisateur (ex. connexion → accueil → virements → bénéficiaire → montant → récapitulatif
→ confirmation → vérification). Par étape : écran, action, condition de passage, données, résultat
attendu, éléments techniques, endpoint, règle métier. Actions : ajouter / modifier / supprimer une
étape, condition, branche alternative, cas négatif, cas limite, relier à un écran ou une API,
assertion, JDD, compléter par l'IA, valider.

### 5.2 BDD Scenario Graph
Un nœud par étape Gherkin (Given, When, Then, And, But, assertion, précondition, donnée).
Actions : ajouter / modifier / supprimer / déplacer, assertion, contrôle négatif, résultat
attendu, donnée, relier à un écran / endpoint, générer et prévisualiser le .feature, valider,
envoyer vers Xray. Synchronisation dans les deux sens entre graphe et fichier Gherkin.

## 6. Automation Studio — Automation Flow Graph

BDD Scenario → Robot Test Suite → Keywords → Page Objects → Locators → Appium / Browser Library ;
JDD et requêtes Oracle en dépendances. Nœuds : scénario BDD, suite, test case, keyword, fichier
resource, page object, locator, JDD, requête Oracle, bibliothèque, driver, plateforme.
Informations — BDD : clé Xray, nom, nombre d'étapes, statut de validation. Robot : nom, fichier,
version, dernière exécution, statut. Keyword : nom, description, source, utilisations,
dépendances. Locator : nom métier, valeur, type, plateforme, fiabilité, tests concernés, secours.
JDD : nom, environnement, source, prérequis, disponibilité.
Actions : ouvrir / modifier le code, modifier / tester / remplacer un locator, ajouter un secours,
tester / modifier un keyword, doublons, keywords similaires, dépendances, comparer deux versions,
analyse d'impact, correction par l'IA, valider, dry run, Merge Request GitLab.

**Impact Analysis** : à la modification d'un locator, keyword ou composant, identifier les tests,
scénarios, modules et plateformes concernés, et les tests à rejouer ; générer une TNR ciblée.

## 7. Execution Center — Live Execution Graph
Suite, test, step, keyword, action, résultat, capture, durée ; statuts QUEUED, EXECUTING, PASSED,
FAILED, BLOCKED, SKIPPED, RETRY. Actions : démarrer, pause si possible, arrêter, rejouer un test,
rejouer les échecs, logs, captures, preuves, ticket Xray, rapport. Timeline avec heures de début
et de fin, keyword en cours, preuves.

## 8. Failure Analysis — Failure Diagnosis Graph
Test FAILED → étape → keyword → preuves → classification → proposition → validation → nouvelle
exécution. Catégories : bug applicatif, locator invalide, données, environnement, synchronisation,
assertion incorrecte, scénario incomplet, erreur du framework. Informations : test Xray, étape,
keyword, message, logs, capture, locator, écran réel / de référence, JDD, historique, diagnostic
IA et sa confiance. Actions : rejouer l'étape, tester / corriger le locator, comparer les écrans,
logs, corriger le JDD, modifier l'assertion, analyse approfondie, bug Jira, relancer, valider,
mettre à jour la cartographie. Une correction IA n'est jamais validée sans vérification.

## 9. Quality Governance — Automation Health Graph
Par application, module, fonctionnalité. Pourcentages calculés à partir d'une définition
explicite de la couverture, jamais de données fictives. Indicateurs : tests existants /
automatisés / manuels, couverture, réussite, stabilité, obsolètes, redondants, en maintenance,
temps moyen d'exécution et de construction, coût de génération, autonomie IA, correction humaine,
ROI. Actions : analyser un module, lacunes, plan d'automatisation, obsolètes, instables, comparer
deux versions, impact d'une livraison, TNR, rapport, export.

## 10. Composants UX communs
Barre supérieure : recherche, filtres (type, plateforme, statut, version), zoom, ajuster, plein
écran, historique, export. Zone centrale : graphe interactif, nœuds sélectionnables, relations
orientées, déplacement, zoom, navigation, développement des dépendances, mini-map, légende.
Panneau droit : informations, propriétés, relations, dépendances, historique, statut, actions,
suggestions IA. Barre d'actions IA contextuelle (expliquer, résumer, anomalies, améliorations,
lacunes, impacts, éléments manquants, recommandation) qui agit sur le graphe sélectionné.

## 11. Principes de conception
1. Graphes interactifs et opérationnels. 2. Chaque nœud = objet identifiable. 3. Chaque relation
a une signification précise. 4. Chaque modification est historisée. 5. Synchronisation Xray /
Jira / GitLab selon des règles explicites. 6. L'IA ne modifie pas un élément validé sans
autorisation. 7. Propositions IA explicables. 8. L'automaticien peut reprendre la main à tout
moment. 9. Vues filtrables par application, module, plateforme, environnement. 10. Les graphes
évoluent avec les versions de l'application.

## 12. Navigation
Dashboard · Application Intelligence (Application Map, Functional Graph, Technical Graph, Impact
Analysis) · Test Strategy (Xray Portfolio, Automation Candidates, Coverage Graph, Automation
Roadmap) · Test Design (Journey Graph, BDD Scenarios, Test Review, Assertions) · Automation Studio
(Robot Suites, Automation Flow Graph, Locators, Keywords, Test Data / JDD, Code Review) · Execution
Center (Live Executions, Execution Graph, Failure Analysis, Execution History) · Quality Governance
(Automation Health, Coverage Dashboard, Stability, Performance, ROI, Reports).

## 13. Priorités
MVP : 1. Application Knowledge Graph ; 2. Xray Coverage Graph ; 3. Automation Flow Graph.
Deuxième phase : Journey Graph, BDD Scenario Graph, Failure Diagnosis Graph, Automation Health Graph.

## 14. Objectif final
L'IA devient le moteur d'exécution et de production ; l'automaticien devient le pilote et le
garant de la qualité.
