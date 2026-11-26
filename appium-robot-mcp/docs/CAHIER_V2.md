# Cahier des charges V2 — AI-Powered Test Engineering Workbench

Version révisée le 2026-11-15 à partir du cahier V2 fourni par l'utilisateur. Les corrections issues de la revue
(confrontation au code) sont intégrées ; elles sont signalées par « Révision ». L'audit de l'existant est dans
`docs/V2_AUDIT_PHASE0.md`.

## 1. Contexte et vision

L'atelier est une application locale qui centralise les connaissances applicatives, aide à concevoir les tests
fonctionnels, génère les scripts Robot Framework, pilote les exécutions et analyse les résultats. Il expose un
serveur MCP de 76 outils. La V2 renforce ces capacités et permet une exploitation complète depuis Cursor.

### 1.1 Séparation des environnements

| | Développement | Production |
|---|---|---|
| Client IA | Claude Code | Cursor |
| Usage | faire évoluer l'atelier, le MCP, le Knowledge Graph, les workflows, les règles ; tests de non-régression | explorer, interroger le graphe, concevoir, générer, exécuter, analyser, mesurer la couverture |

Cursor est l'environnement conversationnel de l'automaticien ; l'atelier fournit les capacités métier et
techniques. L'interface web reste le poste de pilotage visuel.

## 2. Architecture cible

L'architecture existante est conservée et enrichie.

```
AUTOMATICIEN ──► CURSOR (+ règles .cursor/rules)          AUTOMATICIEN ──► INTERFACE WEB (127.0.0.1)
                    │                                                         │
                    ▼                                                         ▼
              SERVEUR MCP (unique, 76+ outils)                         API FastAPI (routes minces)
                    └──────────────────────┬──────────────────────────────────┘
                                           ▼
                         MOTEURS DE L'ATELIER (règles métier, validations côté serveur)
        Discovery · Test Design · Automation · Execution · Failure Analysis · Coverage · Parcours (workflow léger)
                                           │
                     ┌─────────────────────┼──────────────────────┐
                     ▼                     ▼                      ▼
              KNOWLEDGE GRAPH        PERSISTANCE (fichiers      INTÉGRATIONS
              (référentiel des       du projet, isolée par      Jira · Xray · GitLab · Robot Framework
              connaissances)         projet, journaux)          Appium · Playwright · Oracle (SELECT)
```

Révision : Jira, Xray et Git ne sont pas entre le MCP et l'atelier. Le MCP et le web sont deux façades minces ;
ce sont les moteurs qui appellent les intégrations. Cursor ne parle jamais directement à Jira ou Xray.

### 2.1 Principes fondamentaux

- Cursor reste le client IA de production ; Claude Code un outil de développement.
- Le serveur MCP existant est conservé et reste unique ; ses 76 outils restent compatibles (noms, signatures).
- Aucun runtime multi-agents autonome ; l'atelier reste local (127.0.0.1) ; les modules existants sont réutilisés.
- Les actions sensibles restent soumises à validation humaine, **imposée côté serveur** (voir §11).

## 3. Nouveau module : Parcours de fonctionnalité

### 3.1 Objectif

Workflow métier léger qui pilote le cycle de vie complet d'une fonctionnalité et coordonne les modules existants.
Exploitable depuis l'interface web et depuis Cursor (MCP). Ce n'est pas un agent autonome : chaque étape est
réalisée par un module existant (ou par Cursor via ses outils), le parcours en garde l'état, les références et
les validations.

### 3.2 Étapes

1. Discovery · 2. Reconstruction fonctionnelle · 3. Analyse de la couverture existante · 4. Test Design ·
5. Validation des scénarios · 6. Génération des scripts · 7. Qualification des scripts · 8. Exécution ·
9. Failure Analysis · 10. Synchronisation Xray et enrichissement du Knowledge Graph.

### 3.3 Le parcours

Identifiant unique, projet, application, **fonctionnalité** (Révision : identifiée par le nœud
`fonctionnalite:` ou `module:` du Knowledge Graph ; clés Jira associées facultatives), date de création, version,
statut, étapes, historique, validations, responsable.

### 3.4 Statuts (Révision : séparés)

- **Parcours** : Draft, In Progress, Waiting for Validation, Blocked, Suspended, Completed, Abandoned.
- **Étape** : À faire, En cours, En attente de validation, Validée, Échouée, Bloquée, Sautée (avec justification).

« Validated » et « Completed » se chevauchaient : une étape est validée, un parcours est terminé.
« Sautée » couvre les étapes sans objet (ex. reconstruction fonctionnelle quand l'US existe), toujours justifiée.

### 3.5 Étapes

Identifiant, statut, prérequis, entrées, sorties, **références aux objets existants** (session Discovery,
propositions, exigences, scénarios BDD, suites, revues, runs, échecs, exécutions Xray), résultat, date, validation,
historique. Révision : une étape **référence** les objets des modules, elle ne les recopie pas (aucun doublon de
données ; l'état d'une étape peut être recalculé à partir des objets référencés).

### 3.6 Reprise et rejouabilité

Suspendre, reprendre, relancer une étape, revenir à une étape précédente (les résultats suivants sont conservés
et marqués « à revoir »), comparer deux versions du parcours, voir les dépendances bloquantes. Idempotence : les
envois vers Xray réutilisent les clés d'idempotence existantes du journal Xray (aucun doublon).

## 4. Module Cursor Integration

### 4.1 Objectif

Exploiter l'atelier depuis Cursor avec des instructions standardisées et le contexte du projet sélectionné.

### 4.2 Règles Cursor

```
.cursor/rules/  global.mdc · project-context.mdc · security.mdc · mcp-usage.mdc · discovery.mdc ·
                test-design.mdc · automation.mdc · execution.mdc · failure-analysis.mdc · coverage.mdc ·
                knowledge-graph.mdc
```

Révisions :
- **Partir de l'existant** : deux règles existent (`cursor_rules_automatisation.mdc`, `cursor_rules_discovery.mdc`)
  et Paramètres › Cursor / Claude sait déjà les installer (état « à jour / à mettre à jour », sauvegarde `.bak`).
- **Portée de chaque fichier** : `global`, `security`, `mcp-usage` toujours appliqués ; les autres appliqués selon
  les fichiers concernés ou sur demande de l'agent (frontmatter Cursor), pour ne pas alourdir chaque conversation.
- Les règles **décrivent** ; elles ne sont jamais le seul garde-fou (§11).

### 4.3 Versionnement et génération

Consulter, modifier, créer une version, comparer, activer, restaurer, exporter au format Cursor, générer les
instructions propres au projet. Jamais d'écrasement silencieux des règles locales : comparaison avant
synchronisation, sauvegarde de l'existant.

### 4.4 Configuration MCP pour Cursor

Configuration exportable : commande, arguments, variables, chemins, projet, vérification de connexion. Aucun
secret dans les fichiers exportés (existant : la configuration ne contient ni secret ni chemin de projet).

### 4.5 Compatibilité

Les 76 noms d'outils sont conservés. Un changement de comportement (ex. validation imposée) est accompagné d'une
stratégie de migration explicite, documentée dans `docs/DECISIONS.md`.

## 5. Évolution du Test Design

### 5.1 Catégories de scénarios

Nominaux, alternatifs, négatifs, limites, validation des champs, gestion des erreurs, navigation, permissions,
règles métier.

### 5.2 Sources

Jira, Xray, Knowledge Graph, Discovery, dépôt Git, scripts existants, historique des anomalies, documentation.

### 5.3 Sans documentation fonctionnelle

Reconstruire la compréhension à partir des connaissances disponibles (existant : Coverage Intelligence ›
Functional Reconstruction). Chaque proposition : description, source, justification, confiance, informations
manquantes, statut de validation ; **faits observés distingués des hypothèses déduites** (provenances existantes
du graphe : observé / déclaré / déduit).

### 5.4 Doublons

Avant toute proposition : rechercher les tests Xray existants, comparer étapes, préconditions, résultats
attendus ; proposer création, évolution ou réutilisation. Révision : réutiliser et étendre le moteur de similarité
existant (Coverage Intelligence), pas un second moteur.

## 6. Évolution du Coverage

### 6.1 Axes

Exigences (US, critères d'acceptation) · fonctionnelle (modules, fonctionnalités, règles) · **parcours**
(découverts, étapes, associés à des tests, non couverts) · **UI** (écrans, composants, champs, boutons,
interactions) · tests (manuels, automatisés, qualifiés, exécutés).

### 6.2 Niveaux de couverture

Découvert → associé à un test → effectivement vérifié → couvert par un test automatisé → exécution réussie.

Révision : « effectivement vérifié » est **calculable pour les tests automatisés** (chaîne keyword → locator →
composant, et étapes réellement exécutées dans les runs). Pour les tests manuels, il ne peut venir que du texte des
étapes Xray : niveau de confiance faible, affiché comme tel. Tous les calculs sont explicables (définition,
formule, source, date), comme les indicateurs actuels.

### 6.3 Indicateurs

Couverture fonctionnelle, des parcours, des écrans, des composants ; taux d'automatisation ; taux de réussite ;
fonctionnalités sans test ; composants sans test associé. Révision : dans Application Intelligence › Couverture
(lieu unique de la couverture) et résumés dans Quality Governance.

## 7. Knowledge Graph

### 7.1 Champ — Révision : sous-type de composant

Les écrans ont déjà des composants typés et les règles de validation existent (règles de test). Le Champ est un
**composant de type champ** enrichi : nom technique, libellé, type, format, obligatoire, valeur par défaut,
messages d'erreur, écran, fonctionnalité, source, confiance, statut. Relations : écran contient champ ; champ
appartient à fonctionnalité ; champ possède règle (nœud `regle` existant) ; test vérifie champ.

### 7.2 Anomalie — Révision : à partir de l'existant

Le graphe a déjà le type `bug` (Jira) ; l'Execution Center compte les bugs, Failure Analysis relie échecs et
anomalies Jira. L'entité Anomalie étend `bug` : ID interne, ID Jira, titre, type, priorité, statut, fonctionnalité,
écran, test, exécution, date de détection, source, confiance, historique. Relations : concerne fonctionnalité /
écran, détectée par test, associée à exécution, référencée dans Jira.

### 7.3 Enrichissement automatique

Les échecs alimentent des **propositions** ; aucune anomalie créée dans Jira ni considérée comme confirmée sans
validation humaine.

## 8. Évolution du Failure Analysis

Associer les échecs aux écrans, composants et champs ; les relier aux anomalies Jira existantes ; historiser les
causes ; comparer les échecs similaires ; détecter les régressions récurrentes. Classification conservée.

## 9. Évolution du serveur MCP

Serveur unique. Évolutions : documentation, organisation logique par domaine (préfixes, sans renommer), réponses
normalisées, erreurs explicites, contrôle des autorisations côté serveur, journalisation (existante :
activité MCP visible dans le Studio). Nouveaux outils seulement si aucune capacité équivalente n'existe :
parcours (initialiser, consulter, valider une étape, reprendre), règles et profils, couverture avancée, Champ et
Anomalie.

## 10. Interface web — Révision

Garder les espaces actuels (Dashboard, Discovery, Application Intelligence avec la Couverture, Test Design,
Automation Studio, Execution Center, Failure Analysis, Quality Governance, Paramètres) et ajouter :
- **Parcours** (nouvel onglet principal) ;
- **Cursor** dans Paramètres › Cursor / Claude (existant : installation du MCP et des règles), enrichi du
  versionnement des règles.

Le cahier initial listait Coverage comme module séparé : la couverture vient d'être regroupée dans Application
Intelligence, on ne recrée pas un second lieu. Web et Cursor partagent les mêmes données et règles : une action
faite dans Cursor est visible dans le web et inversement (existant : événements temps réel, activité MCP).

## 11. Sécurité

Obligatoire : aucune action sensible pendant la découverte ; aucune saisie automatique non autorisée ; aucune
création Jira ni création / modification Xray sans validation ; aucun commit sans autorisation ; aucune fusion Git
automatique ; aucune modification silencieuse du Knowledge Graph ; traçabilité ; isolation par projet ; protection
des secrets ; historisation des validations.

**La validation est imposée côté serveur, jamais seulement dans les règles Cursor.**

Révision : l'audit a trouvé des outils MCP qui écrivent sans validation côté serveur (`jira_transition`,
`import_results_to_xray`, `qualify_failure`, transitions Jira de `run_robot`, `name_screen`, `tap` / `type_text`
hors session Discovery). Leur mise en conformité est une phase à part entière (phase 0 bis), avant le parcours.

## 12. Contraintes techniques

Conserver : FastAPI, interface JavaScript, serveur MCP existant, stockage fichiers par projet, Git, Robot
Framework, Appium, Browser Library, Cursor. Ne pas imposer : Next.js, PostgreSQL, Redis, pgvector, Docker, runtime
multi-agents, cloud, sept serveurs MCP. Toute évolution technique est justifiée par un besoin fonctionnel réel.

## 13. Plan de réalisation (Révision : ordre)

| Phase | Contenu |
|---|---|
| 0 | Audit de l'existant : matrice EXISTANT / À AMÉLIORER / À CRÉER (`docs/V2_AUDIT_PHASE0.md`) |
| 0 bis | Validation côté serveur des outils MCP d'écriture (noms conservés, migration documentée) |
| 1 | Parcours de fonctionnalité (web + MCP) |
| 2 | Cursor Integration (règles structurées, versionnement, export, configuration MCP) |
| 3 | Coverage avancé (parcours, UI, niveaux de couverture) |
| 4 | Test Design avancé (catégories, doublons) |
| 5 | Knowledge Graph (Champ, Anomalie) |
| 6 | Failure Analysis (liens échecs ↔ écrans, composants, champs, anomalies) |
| 7 | Consolidation (non-régression, intégration MCP, sécurité) |

## 14. Méthode de développement (Claude Code)

Analyser l'existant avant toute évolution ; ne pas recréer ; identifier les dépendances ; préserver noms et
contrats MCP et conventions ; éviter les migrations inutiles ; plan avant chaque phase ; incréments testés ;
non-régression ; documentation ; aucune suppression sans justification et validation.

Révision des livrables par phase (pour éviter plus de documentation que de code) : un document court par phase
dans `docs/` (existant, décisions, modèle de données, outils MCP et API concernés, écrans), les tests (unitaires,
intégration, non-régression) et l'entrée correspondante de `docs/DECISIONS.md`.

## 15. Critères de succès — Révision : mesurables

- Un parcours de fonctionnalité joué de bout en bout sur l'application de démonstration, depuis Cursor (MCP) puis
  depuis le web, interrompu et repris sans perte.
- 0 outil MCP renommé ou dont la signature casse ; la suite de tests existante passe.
- Pour chaque outil d'écriture, un test vérifie qu'il refuse d'agir sans validation côté serveur.
- Règles Cursor centralisées, versionnées, comparées avant synchronisation.
- Couverture des parcours et des composants UI calculée avec définition et source.
- Champ et Anomalie présents dans le graphe, reliés aux échecs.
- Tests d'intégration MCP par un client MCP de test (Cursor lui-même n'est pas pilotable par les tests).

## Conclusion

La V2 transforme les capacités existantes en un environnement de travail piloté par Cursor, cohérent, traçable
et industrialisable, sans plateforme d'agents supplémentaire. Claude Code développe ; Cursor opère ; le MCP relie ;
le Knowledge Graph conserve ; le parcours de fonctionnalité assure la continuité.
