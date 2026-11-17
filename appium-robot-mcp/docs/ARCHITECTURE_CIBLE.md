# Architecture cible — Atelier d'automatisation intelligent

Statut : document de cible, révisé le 2026-11-16 à partir de la proposition d'architecture « 7 couches et
agents IA spécialisés », confrontée au code et au cahier V2 (`docs/CAHIER_V2.md`, livré : `docs/V2_BILAN.md`).
Il fixe le cap au-delà de la V2 ; le travail reste découpé phase par phase (`docs/ROADMAP.md`, cahiers) et chaque
choix appliqué est consigné dans `docs/DECISIONS.md`.

Corrections apportées à la proposition initiale :

1. **Le MCP est une façade, pas un bus interne.** Les moteurs de l'atelier appellent directement les
   intégrations (Jira, Xray, Git…). Le MCP expose les capacités de l'atelier au client IA (Cursor) ; il n'y a
   ni sept serveurs MCP ni connecteur MCP entre l'atelier et Jira / Xray.
2. **Les agents sont des rôles, portés aujourd'hui par Cursor.** Chaque agent de la proposition (Discovery,
   Test Design, Automation, Execution, Failure Analysis, Coverage, Knowledge) correspond à une règle Cursor
   versionnée et à un jeu d'outils MCP ; l'atelier fournit les capacités et **impose les validations côté
   serveur**. Un runtime d'agents interne à l'atelier reste une option, avec des conditions (§ 5.8).
3. **L'orchestrateur est un workflow fixe : le Parcours de fonctionnalité.** Dix étapes connues, l'état et
   les validations gardés par l'atelier ; pas de planification libre par un LLM.
4. **Tout n'est pas de l'IA.** Exécution, synchronisation Xray, calcul de couverture et contrôles statiques
   sont des services déterministes.
5. **Pas de réécriture.** La pile reste locale (FastAPI, interface JavaScript, fichiers du projet) ; la pile
   « plateforme d'équipe » (PostgreSQL, Redis, Docker…) n'est adoptée que si l'atelier devient multi-utilisateur.
6. **Sections ajoutées** : confidentialité et IA, évaluation des agents, données de test et environnements,
   prérequis de qualité des données.

---

## 1. Vision générale

Construire une plateforme intelligente qui industrialise le cycle de vie des tests fonctionnels : découverte de
l'application, conception, automatisation, exécution, analyse des résultats et pilotage de la couverture.

La plateforme assiste l'automaticien et automatise progressivement les tâches répétitives grâce à des agents IA
spécialisés, **qui proposent ; l'automaticien valide**.

L'architecture est indépendante du fournisseur de LLM (Cursor et ses modèles, LLM interne, Claude, GPT…) et des
outils externes. Elle est construite **à partir de l'atelier existant** (annexe A).

## 2. Architecture globale

```
                                   AUTOMATICIEN
                    ┌────────────────────┴─────────────────────┐
                    ▼                                          ▼
   ┌──────────────────────────────────┐      ┌──────────────────────────────────┐
   │ CURSOR — client IA de production │      │ INTERFACE WEB — poste de pilotage │
   │ agents = rôles (.cursor/rules)   │      │ (127.0.0.1) : espaces, Parcours, │
   │ Discovery · Test Design ·        │      │ validations « À valider »         │
   │ Automation · Execution ·         │      └─────────────────┬────────────────┘
   │ Failure Analysis · Coverage ·    │                        │
   │ Knowledge                        │                        │
   └────────────────┬─────────────────┘                        │
                    ▼                                          ▼
   ┌──────────────────────────────────┐      ┌──────────────────────────────────┐
   │ FAÇADE MCP (serveur unique,      │      │ FAÇADE WEB (API FastAPI,          │
   │ outils regroupés par domaine)    │      │ routes minces)                    │
   └────────────────┬─────────────────┘      └─────────────────┬────────────────┘
                    └──────────────────────┬───────────────────┘
                                           ▼
   ┌───────────────────────────────────────────────────────────────────────────────┐
   │ ORCHESTRATION : Parcours de fonctionnalité (workflow fixe en 10 étapes) ·      │
   │ file d'exécution · demandes d'action et validations imposées côté serveur      │
   ├───────────────────────────────────────────────────────────────────────────────┤
   │ MOTEURS MÉTIER (atelier/) : discovery · intelligence · generation · execution  │
   │ services déterministes + règles explicables ; appels IA par la passerelle IA   │
   │                  ┌─────────────────────────────────────────────┐              │
   │                  │ KNOWLEDGE GRAPH + MÉMOIRE DU PROJET (cœur)   │              │
   │                  └─────────────────────────────────────────────┘              │
   └───────────────────────────────────────┬───────────────────────────────────────┘
                                           ▼
   ┌───────────────────────────────────────────────────────────────────────────────┐
   │ INTÉGRATIONS (clients Python) : Jira · Xray · GitLab · Robot Framework ·       │
   │ Appium · Playwright · Oracle (SELECT uniquement)                               │
   └───────────────────────────────────────────────────────────────────────────────┘
```

Règles de dépendance (appliquées dans le code, à conserver) :

- un moteur n'importe jamais une façade ; les façades (web, MCP) ne contiennent aucune logique métier ;
- Cursor ne parle jamais directement à Jira, Xray ou Git : il passe par les outils de l'atelier ;
- le Knowledge Graph est au cœur, accessible directement par tous les moteurs ;
- tout appel à un LLM fait par l'atelier lui-même passe par la passerelle IA
  (`atelier/intelligence/fournisseur_ia.py`) ;
- **une validation humaine est imposée côté serveur** ; les règles Cursor décrivent, elles ne sont jamais le
  seul garde-fou.

## 3. Couche application — interface utilisateur

Deux postes, mêmes données : une action faite dans Cursor est visible dans l'interface web et inversement
(événements temps réel, activité MCP).

| Espace | Existant |
|---|---|
| Dashboard global | oui |
| Parcours (cycle de vie d'une fonctionnalité) | oui (V2 phase 1) |
| Discovery et exploration applicative | oui |
| Application Intelligence : cerveau, connaissance, Knowledge Graph, couverture, validation | oui |
| Test Design (catégories, doublons) | oui (V2 phase 4) |
| Automation Studio | oui |
| Execution Center | oui |
| Failure Analysis (relié à la connaissance) | oui (V2 phase 6) |
| Quality Governance | oui |
| Paramètres : projets, connecteurs, environnements, Cursor / Claude (règles versionnées, MCP) | oui |
| Configuration des modèles IA de l'atelier | partiel : fournisseur IA par variable d'environnement |
| Évaluation des agents | à créer (§ 12) |

La couverture a un lieu unique (Application Intelligence) ; elle est résumée dans Quality Governance.

Le choix du projet est global (sélecteur du header) : tous les modules, Cursor compris, travaillent sur le
projet actif ; changer de projet change tout le contexte.

## 4. Orchestration — Parcours de fonctionnalité

L'orchestrateur est le **Parcours de fonctionnalité** (`atelier/intelligence/parcours_fonctionnalite.py`) :
un workflow fixe, exploitable depuis le web et depuis Cursor, qui coordonne les modules existants sans recopier
leurs données.

Responsabilités (réalisées) :

- un parcours par fonctionnalité (nœud `fonctionnalite:` ou `module:` du graphe) ;
- dix étapes connues, chacune réalisée par un module existant ou par Cursor via ses outils ;
- une étape ne démarre que si les précédentes sont validées ou sautées (avec justification) ;
- références aux objets des modules (sessions, scénarios, suites, runs, échecs, exécutions Xray) ;
- suspension, reprise, retour à une étape (les suivantes passent « à revoir »), comparaison de versions ;
- validations humaines imposées côté serveur (validation des scénarios, qualification, synchronisation Xray) ;
- historique de toutes les opérations.

Ce que l'orchestrateur ne fait pas :

- il ne contient aucune règle métier d'un agent ;
- il ne choisit pas librement les agents à partir d'un objectif en langage naturel. Une planification libre
  pourra être étudiée plus tard, toujours avec un plan affiché et validé avant exécution.

Les tâches longues (runs) passent par la file d'exécution de l'Execution Center.

## 5. Agents IA

Un agent est un **rôle** : un objectif, des instructions (règle Cursor versionnée), un jeu d'outils MCP et des
garde-fous imposés par l'atelier. En production, c'est Cursor qui joue les rôles ; l'atelier fournit les
capacités, les données et les validations.

Chaque agent ne fait que **proposer** : ses sorties sont des éléments « à valider », avec leur source et un
niveau de confiance exprimé par un libellé (élevé / moyen / faible), jamais un pourcentage inventé. Les faits
observés sont distingués des hypothèses déduites.

| Agent | Règle Cursor | Capacités de l'atelier | Part déterministe |
|---|---|---|---|
| Discovery | `discovery.mdc` | `discovery/` | exploration, reconnaissance des écrans |
| Test Design | `test-design.mdc` | `generation/conception.py`, `regles_test.py` | catégories, similarité (doublons) |
| Automation | `automatisation.mdc` | `generation/studio*.py`, `locators.py` | contrôles statiques, revue |
| Execution | `execution.mdc` | `execution/centre.py`, `robot.py`, `journal_xray.py` | **tout** (service) |
| Failure Analysis | `failure-analysis.mdc` | `execution/echecs.py` | règles explicables avec preuves |
| Coverage | `coverage.mdc` | `intelligence/intelligence_couverture.py` | **calculs** (service) |
| Knowledge | `knowledge-graph.mdc` | `discovery/connaissance.py`, `domain/declarations.py` | reconstruction du graphe |

Règles transverses : `global.mdc`, `project-context.mdc`, `security.mdc`, `mcp-usage.mdc`. Les 11 règles sont
versionnées dans `regles_cursor/` et synchronisées vers `.cursor/rules/` du projet de tests sans écrasement.

### 5.1 Discovery Agent

Objectif : découvrir et comprendre l'application testée.

- Explorer les interfaces web et mobile ; identifier écrans, composants, champs, boutons, interactions,
  parcours et dépendances entre écrans ; détecter les changements d'interface.
- Rôle de l'IA : nommer les écrans, proposer les rapprochements (écran ↔ exigence), les parcours et les champs.
- Sources : application réelle, Jira, dépôt Robot, documentation disponible, Xray.
- Garde-fous : aucune saisie, aucune case cochée, aucune action de la liste rouge, liens externes ignorés ;
  aucune action sensible pendant la découverte.

### 5.2 Test Design Agent

Objectif : concevoir les scénarios de tests fonctionnels.

- Analyser user stories, critères d'acceptation, tests Xray existants et Knowledge Graph.
- Catégories : nominaux, alternatifs, négatifs, limites, validation des champs, gestion des erreurs,
  navigation, permissions, règles métier.
- Avant toute proposition : rechercher les tests existants et proposer création, évolution ou réutilisation.
- Sans documentation fonctionnelle : reconstruction à partir de l'exploration, des écrans, du dépôt, des tests
  existants et de l'historique ; confiance faible et informations manquantes affichées.
- Conventions : Gherkin français, aucune donnée littérale dans le scénario (JDD).

### 5.3 Automation Agent

Objectif : transformer les scénarios validés en scripts Robot Framework.

- Réutiliser keywords et composants du framework ; jamais de keyword réinventé ni de wrapper 1:1 par élément.
- Page Object Model, séparation locators / keywords / scénarios, initialisation JDD, tags clé Xray +
  fonctionnels ; mêmes clés métier de locators sur Android et iOS.
- Contrôles déterministes : syntaxe, robocop, doublons.
- Une correction n'est déclarée fiable qu'après **3 exécutions stables et une revue humaine**.
- Technologies : Robot Framework, Browser library, AppiumLibrary, RequestsLibrary, Python ; Selenium si
  nécessaire.
- Aucun commit sans autorisation, aucune fusion Git automatique.

### 5.4 Execution (service)

- Préparer les campagnes, sélectionner suites, environnements, navigateurs et appareils (Android, iOS).
- Lancer via la file à priorités, superviser, collecter résultats, logs et captures.
- Transmettre les résultats à Xray par le journal rejouable ; une indisponibilité Xray / Jira n'interrompt
  jamais un run.
- Vérifier la disponibilité des environnements, appareils et données avant chaque run.

### 5.5 Failure Analysis Agent

- Lire rapports, logs et captures ; identifier l'étape en échec ; comparer avec les exécutions précédentes ;
  relier l'échec aux écrans, composants, champs et anomalies.
- Diagnostic de base déterministe ; IA consultée à la demande, sur un contexte masqué.
- Classification : anomalie applicative, défaut du script, locator obsolète, données de test, environnement,
  réseau, synchronisation, framework, assertion, conception du test, bloqué, non déterminé.
- À étendre : historique des Test Executions Xray lancées hors de l'atelier (tests instables, échecs
  permanents).
- Une anomalie n'est créée dans Jira qu'après validation humaine.

### 5.6 Coverage (service + agent)

- Calculs explicables (définition, formule, source, date) sur l'instantané Xray, le graphe et l'historique.
- Axes : exigences, fonctionnelle, parcours, UI (écrans, composants, champs), tests manuels / automatisés.
- Niveaux : découvert → associé à un test → effectivement vérifié → automatisé → exécution réussie.
- Identifier fonctionnalités sans test, tests sans rattachement, incohérences de traçabilité.
- **Hygiène du référentiel** (à créer) : statuts Jira / Xray périmés, composants en doublon ou qui sont des
  plateformes, plans vides, plusieurs applications dans une même JQL. Rapport proposé ; correction humaine.

### 5.7 Knowledge Agent

- Rechercher dans le graphe, proposer de nouvelles connaissances (fonctionnalités, parcours, champs, règles),
  détecter les incohérences.
- N'enregistre que des propositions « déduit / à valider ».

### 5.8 Runtime d'agents interne (option, non retenu aujourd'hui)

Faire exécuter les rôles par l'atelier lui-même (sans Cursor), via la passerelle IA, n'est envisagé que si :

- un besoin réel l'exige (traitement planifié sans automaticien, par exemple l'analyse nocturne des échecs) ;
- le fournisseur d'IA est autorisé par l'entreprise ;
- l'agent a passé son évaluation (§ 12).

Dans ce cas, les agents internes appellent les moteurs directement (pas au travers du MCP) et restent soumis aux
mêmes validations côté serveur.

## 6. Intégrations et façade MCP

### 6.1 Intégrations internes (`atelier/integrations/`)

- **Jira** : projets, epics, user stories, critères d'acceptation, tâches, liens, recherche, transitions.
- **Xray** : tests, Test Sets, Test Plans, Test Executions ; création et mise à jour (schéma vérifié par
  introspection, `docs/XRAY_API_resultat.md`), campagnes, synchronisation des résultats, traçabilité.
- **GitLab** : dépôts, fichiers, branches, merge request après autorisation.
- **Robot Framework** : validation syntaxique, analyse des suites et keywords, exécution, rapports, output.xml.
- **Appium** : appareils, capacités, sessions, exploration, éléments UI, captures.
- **Playwright** (web) : navigation, exploration, DOM, captures, appels réseau observés.
- **Oracle** : SELECT uniquement, requêtes en liste blanche, paramètres liés, délai et lignes plafonnés.

### 6.2 Façade MCP

Serveur unique (88 outils, dont les 76 historiques inchangés), organisé par domaine : Jira, Xray, Git, Robot,
Appium, Browser, Knowledge, Parcours, Coverage, Test Design.

- Aucune logique de raisonnement.
- Noms et signatures des outils existants conservés (rétrocompatibilité).
- Chaque outil d'écriture passe par une **demande d'action** validée dans l'atelier ; chaque outil est classé
  dans le registre de sécurité (`tests/test_securite_outils.py`).

## 7. Knowledge Graph — référentiel central de connaissances

Le Knowledge Graph est le patrimoine fonctionnel et technique de la plateforme. Il n'est pas limité à Jira.

Sources : Discovery, Jira, Xray, dépôt Git / Robot, historique des exécutions, documentation (OpenAPI…), jeux
de données, validations des automaticiens, propositions des agents.

Entités : application, version, module, fonctionnalité, parcours, écran, composant UI, champ (composant de type
champ), bouton, règle métier, epic, user story, test case, test step, test plan, keyword, script, locator, jeu
de données, environnement, appareil, test execution, résultat, anomalie (extension de `bug`).

Relations principales :

- Application → contient → Modules → contient → Fonctionnalités.
- Fonctionnalité → utilise → Écrans → contient → Composants UI / Champs.
- Champ → possède → Règle ; Test → vérifie → Champ.
- Fonctionnalité → est décrite par → User Stories ; est vérifiée par → Test Cases.
- Test Case → est automatisé par → Scripts → utilise → Keywords, Locators, Jeux de données.
- Test Case → est exécuté dans → Test Execution (Test Plan, environnement, appareil, version).
- Test Execution → produit → Résultats → peut révéler → Anomalie (concerne fonctionnalité / écran).

Chaque connaissance conserve : source, date de découverte, version de l'application, niveau de confiance
(libellé), statut (observé / déclaré / déduit à valider / validé / masqué) et historique.

Règles :

- le graphe est reconstruit depuis les sources ; les déclarations humaines sont un YAML versionné avec un
  historique JSONL (`connaissance/`) ;
- un élément observé n'est jamais supprimé depuis le graphe : il est masqué (historisé) ;
- l'IA ne crée que des éléments « déduit / à valider » et ne modifie rien de validé ; l'analyse d'impact ignore
  un lien déduit non validé ; aucune modification silencieuse.

## 8. Mémoire et contexte

- Mémoire du projet et conventions d'automatisation (dont les règles Cursor versionnées).
- Historique des analyses, des générations, des décisions humaines, des parcours et des exécutions.
- Historique des appels IA (fournisseur, modèle, entrée masquée, sortie, décision).

Persistante, versionnée et isolée par projet : stockée dans le projet de tests (YAML / JSON / JSONL). Une base
de données n'est introduite qu'à l'étape « plateforme d'équipe » (§ 9).

## 9. Couche technique et infrastructure

La pile dépend d'une décision à prendre le moment venu : **outil local de l'automaticien** ou **plateforme
d'équipe**.

### Étape 1 — poste local (actuelle, à conserver)

- Backend : Python, FastAPI, moteurs métier indépendants ; écoute sur 127.0.0.1 uniquement.
- Frontend : interface web existante (JavaScript sans dépendance externe, réseau sans CDN).
- Client IA : Cursor (production), Claude Code (développement de l'atelier).
- Données : fichiers du projet, instantanés Xray datés.
- Orchestration : Parcours de fonctionnalité, file d'exécution à priorités, journal Xray rejouable.
- Secrets : variables d'environnement ou coffre du système (`keyring`) ; jamais dans un fichier ni un log.

### Étape 2 — plateforme d'équipe (seulement si multi-utilisateur)

Conditions de passage : plusieurs automaticiens sur le même projet en simultané, partage en temps réel ou
exécutions centralisées. Chaque brique est justifiée par un besoin fonctionnel réel.

- Données : PostgreSQL (modèle de graphe relationnel), pgvector pour la recherche sémantique, stockage des
  artefacts et captures.
- Orchestration : file de messages (Redis ou équivalent), tâches asynchrones, retries.
- Infrastructure : Docker, GitLab CI/CD, secrets centralisés, logs centralisés, monitoring.
- Sécurité à refaire : authentification (SSO), rôles, hébergement interne, proxy TLS, cloisonnement des projets.
- Frontend : React / Next.js seulement si l'interface est refondue, pas pour l'architecture.

## 10. Principes de gouvernance

1. Aucun agent ne modifie des données de production sans autorisation.
2. Toute génération de script est traçable.
3. Toute modification du dépôt est contrôlée : aucun commit sans autorisation, aucune fusion automatique.
4. Toute création ou modification Jira / Xray passe par une validation et est historisée.
5. Les connaissances découvertes sont distinguées des connaissances validées.
6. Les agents fonctionnent indépendamment les uns des autres.
7. Changer de LLM ne demande pas de refonte.
8. Les intégrations sont indépendantes des agents ; le MCP est une façade, pas un bus interne.
9. Les agents partagent un contexte projet commun (projet actif).
10. Les actions sensibles (paiement, virement, suppression, validation métier) demandent une validation humaine
    et ne s'exécutent que si le scénario les autorise, sur un environnement autorisé.
11. La validation est imposée côté serveur, jamais seulement dans les instructions d'un agent.
12. Une proposition d'IA n'est jamais appliquée sans validation humaine.
13. Aucune valeur estimée n'est affichée comme un fait (pas de score ni de pourcentage sans calcul réel).
14. Une indisponibilité de Xray, Jira ou de la carte n'interrompt jamais un run.

## 11. Confidentialité et IA

- Le client IA et le fournisseur des appels faits par l'atelier sont choisis par l'entreprise
  (`IA_FOURNISSEUR` : aucun / cursor / interne / anthropic ; défaut « aucun »).
- Les textes envoyés par l'atelier sont masqués : e-mails, IBAN, numéros de carte, secrets, longs nombres,
  données client.
- Les outils MCP ne renvoient jamais de secret.
- Aucune donnée client ni capture d'application bancaire réelle dans le dépôt de l'atelier.
- Chaque appel IA fait par l'atelier est historisé ; aucun code ne dépend du SDK d'un fournisseur particulier.

## 12. Évaluation des agents

Un rôle d'agent (règle Cursor ou agent interne) n'est généralisé que s'il est mesuré :

- jeux de référence par rôle : échecs déjà diagnostiqués, scénarios déjà validés, écrans déjà nommés, doublons
  connus ;
- indicateurs : précision de la classification des échecs, taux d'acceptation des propositions, taux de
  correction après revue, doublons évités ;
- mesure à chaque nouvelle version d'une règle Cursor, d'un modèle ou d'un prompt ; retour à la version
  précédente si un indicateur se dégrade (les règles sont déjà versionnées et restaurables).

## 13. Données de test et environnements

- Jeux de données (JDD), environnements et appareils sont des entités du Knowledge Graph.
- Avant chaque run : disponibilité de l'environnement, des appareils et des données (prérequis Oracle en
  lecture seule).
- Les tests qui consomment une donnée sont tagués (`consomme_donnee`).
- Chaque Test Execution renseigne l'environnement, l'appareil et la version de l'application.

## 14. Prérequis de qualité des données

Les agents ne valent que ce que valent leurs sources. Avant de les exploiter sur un projet réel :

- périmètre de chaque application isolé dans Jira et Xray (composant ou label ; une JQL par application) ;
- composants Jira = modules fonctionnels (pas de plateformes, pas de doublons) ;
- statuts des Test Executions et Test Plans à jour ; environnements renseignés ;
- bugs liés aux exécutions en échec ;
- tests automatisés reliés au dépôt Robot par leur clé Xray en tag.

## 15. Workflow métier principal — les dix étapes du parcours

Exemple : automatiser une fonctionnalité mobile.

| # | Étape | Agent / service | Validation humaine |
|---|---|---|---|
| 1 | Discovery | Discovery Agent + exploration | les noms et rapprochements proposés |
| 2 | Reconstruction fonctionnelle | Knowledge Agent | les connaissances déduites |
| 3 | Analyse de la couverture existante | Coverage (service) | — |
| 4 | Test Design | Test Design Agent | — |
| 5 | Validation des scénarios | — | **imposée côté serveur** |
| 6 | Génération des scripts | Automation Agent | revue des scripts |
| 7 | Qualification des scripts | Execution (3 runs stables) | **imposée côté serveur** |
| 8 | Exécution | Execution (service) | — |
| 9 | Failure Analysis | règles + Failure Analysis Agent | diagnostic confirmé, anomalie Jira |
| 10 | Synchronisation Xray et enrichissement du graphe | service | **imposée côté serveur** |

## 16. Objectif final

La plateforme devient un atelier d'automatisation intelligent dans lequel :

- l'application se découvre elle-même ;
- les connaissances fonctionnelles sont centralisées et validées ;
- les tests sont conçus avec l'assistance de l'IA ;
- les scripts sont générés en réutilisant le framework existant ;
- les tests s'exécutent sur le web et le mobile ;
- les échecs sont analysés et classés avec leurs preuves ;
- la couverture est mesurée en continu ;
- Xray reste le référentiel de gestion des tests, Git le référentiel des scripts, et le Knowledge Graph le
  référentiel des connaissances applicatives ;
- l'automaticien garde le contrôle des décisions importantes.

La plateforme ne remplace pas l'automaticien : elle transforme son rôle en supervision, validation,
enrichissement du patrimoine de tests et traitement des situations complexes.

---

## Annexe A — Écarts entre la cible et l'existant (après la V2)

| Sujet | Existant | À faire |
|---|---|---|
| Rôles d'agents | 11 règles Cursor versionnées, 88 outils MCP | jouer un premier parcours réel sur TAM |
| Orchestration | Parcours de fonctionnalité (10 étapes) | planification libre : non prévue |
| Évaluation des agents | aucune | jeux de référence et indicateurs par rôle (§ 12) |
| Failure Analysis sur l'historique Xray | runs de l'atelier | instables et échecs permanents des Test Executions Xray |
| Hygiène du référentiel | indicateurs partiels | rapport dédié (§ 5.6) |
| Passerelle IA | `fournisseur_ia.py` | faire passer `adapters/web/agent.py` par la passerelle (dépend aujourd'hui du SDK Anthropic) |
| Configuration des modèles | variables d'environnement | écran de configuration, sans secret affiché |
| Runtime d'agents interne | agent intégré (Studio, API Claude) | seulement aux conditions du § 5.8 |
| Git | GitLab non configuré sur le poste | configuration, merge request après autorisation |
| Recherche sémantique | aucune | étape 2 seulement |

## Annexe B — Ordre de mise en œuvre proposé

1. Nettoyage Jira / Xray du projet (§ 14), réalisé par l'équipe.
2. Mise en service de la V2 sur le poste : synchroniser les règles Cursor, tester le serveur MCP, jouer un
   premier parcours réel.
3. Failure Analysis sur l'historique Xray, en lecture seule, avec son jeu de référence.
4. Évaluation des rôles d'agents (§ 12).
5. Passerelle IA unique (correction de `agent.py`).
6. Décision poste local / plateforme d'équipe, puis étape 2 si nécessaire.
