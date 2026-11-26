# Roadmap — Atelier d'automatisation → AI Test Engineering Platform

Principe : la qualité avant le volume. Chaque phase est livrable seule, testée, et ne casse pas
les outils MCP existants. Cocher les cases au fil de l'eau ; noter les décisions dans
`docs/DECISIONS.md` (une ligne datée par décision).

---

## Phase 1 — Fondations (aucune nouvelle fonctionnalité visible)

### 1.1 Découpage en moteurs
- [x] Créer le paquet `atelier/` selon l'architecture de CLAUDE.md.
- [x] Déplacer la logique de `server.py` vers les moteurs : sessions et observation → `discovery`,
      génération de .resource → `generation`, runs / listeners / qualification → `execution`,
      clients Xray / Jira / Oracle / Appium / Playwright → `integrations`.
- [x] `app_map.py` → `atelier/discovery/carte/` ; `web_backend.py` → `atelier/integrations/playwright/`.
- [x] `adapters/mcp/server.py` : enregistre les mêmes outils, chacun en quelques lignes.
- [x] `adapters/web/app.py` : mêmes routes, appelant les moteurs (plus d'import de `server.py`).
- [x] Gardes de compatibilité : `server.py` et `web/app.py` à la racine deviennent de simples
      points d'entrée qui importent les adapters (les configs Cursor existantes continuent de marcher).
- [x] Événements : un bus interne (`atelier/domain/evenements.py`) remplace `EVENT_HOOK` et
      `WEB_EVENTS_URL` ; les adapters s'y abonnent.

**Acceptation** : la liste des outils MCP (noms + paramètres) est identique avant / après
(test automatique qui compare les deux) ; toutes les routes web répondent ; `pytest -q` vert.

### 1.2 Sécurité de l'interface locale
- [x] Jeton de session généré au démarrage, transmis à la page (cookie HttpOnly SameSite=Strict) ;
      exigé sur toutes les routes `/api/*` et le WebSocket, sauf `/api/events` (jeton propre aux listeners).
- [x] Vérification `Host` ∈ {127.0.0.1:PORT, localhost:PORT} (protection DNS rebinding) et
      `Origin` identique pour les requêtes navigateur et le WebSocket. Pas de CORS.
- [x] Taille maximale des requêtes, chemins limités au projet (déjà `_safe_path`), liste blanche
      des actions manuelles (déjà en place, à tester).
**Acceptation** : tests qui prouvent le refus sans jeton, avec un mauvais `Host`, avec une `Origin`
étrangère, et l'acceptation dans le cas nominal.

### 1.3 Synchronisation Xray découplée de l'exécution
- [x] Le listener écrit chaque événement dans un journal local (`results/<run>/xray_outbox.jsonl`)
      avec une clé d'idempotence (run_id + test + type d'événement + horodatage).
- [x] Un synchroniseur (thread du listener + commande `python -m atelier xray-sync <dossier>`)
      envoie le journal à Xray avec reprise (backoff exponentiel), marque les événements envoyés,
      et peut rejouer un run complet plus tard.
- [x] Le run Robot se termine normalement même si Xray est injoignable du début à la fin.
**Acceptation** : test avec un faux Xray qui échoue 3 fois puis répond → aucun événement perdu,
aucun doublon ; test avec Xray totalement indisponible → run terminé, journal complet, rejeu OK.

### 1.4 Vérification de l'API Xray
- [x] *(2026-11-14 : schéma conforme par introspection, docs/XRAY_API_resultat.md ; essai réel d'écriture restant)* Vérifier chaque appel listé dans CLAUDE.md (documentation officielle ou introspection
      GraphQL) ; corriger les noms et arguments ; documenter dans `docs/XRAY_API.md`.
- [ ] *(en partie : noms configurables `XRAY_STATUTS`, agrégation sur les statuts Robot ; lecture depuis Xray après vérification)* Préciser la gestion des statuts personnalisés (statuts de test run configurables par
      projet) : lire la liste des statuts disponibles plutôt que la supposer.

---

## Espaces de travail de l'automaticien (docs/ESPACES_DE_TRAVAIL.md)

Demandé le 2026-11-14, en parallèle de la roadmap par phases. Page `/plateforme` de l'interface.

### MVP (§13 de la spécification)
- [x] Navigation des 7 espaces (§12) ; entrées non livrées signalées « phase 2 » / « à venir », jamais simulées.
- [x] Composant graphe commun (§10) : recherche, filtres type / plateforme / statut, zoom, ajuster, plein écran,
      déplacement, sélection avec voisins, développement des dépendances, mini-carte, légende, historique,
      export JSON / SVG, panneau de propriétés et d'actions, barre IA contextuelle. Sans bibliothèque externe.
- [x] Application Knowledge Graph : carte + dépôt Robot + JDD + instantané Xray + résultats + déclarations ;
      ajouter / modifier / masquer / relier / fusionner / valider, tout historisé (connaissance/).
- [x] Xray Coverage Graph : Epic → US → Test Xray → Test Robot, filtres module et manuel / automatisé,
      indicateurs sur définitions explicites, exigences non couvertes, redondances candidates.
- [x] Automation Flow Graph : scénario → test Robot → keywords → locators (+ secours) → écrans, resource,
      JDD → requêtes Oracle, bibliothèques, plateformes.
- [x] Impact Analysis : tests, scénarios, modules, plateformes, TNR ciblée (dry run ou run).
- [x] Pages : Dashboard, Xray Portfolio (import / synchronisation Jira), Automation Candidates (faits observables
      seulement), Coverage Dashboard, Robot Suites, Locators, Keywords, Test Data / JDD.
- [x] Outils MCP ajoutés : `knowledge_graph`, `impact_analysis`, `coverage_report`, `automation_flow`.
- [ ] Synchronisation Jira à vérifier sur un vrai site (`POST /rest/api/3/search/jql`, champs, lien « Test » ; docs/XRAY_API.md).
- [ ] Comparer deux versions (graphe par build) ; tests similaires ; lot / plan d'automatisation (avec la phase 3).
- [ ] Modifier le code / un locator depuis le Studio avec validation et dry run ; MR GitLab (phase 7).

### Interface aux maquettes (demande du 2026-11-14)
- [x] Nouvelle interface `/plateforme` : thèmes sombre et clair, en-tête de contexte réel (projet, application, version,
      plateforme, environnement, Xray, session), onglets Dashboard, Knowledge Graph, Construction BDD, Éditeur de test,
      Exécution, Rapports, et Paramètres en section à part.
- [x] Construction BDD : graphe d'étapes et branches synchronisé avec `bdd/<clé>.feature`, propriétés d'étape (écran,
      locator, JDD, API, assertion, validation), contrôles sans IA, relecture IA, génération Robot réutilisant le socle.
- [x] Éditeur de test : explorateur, onglets, coloration Robot, enregistrement historisé, lint (syntaxe + conventions),
      robocop si installé, dry run / exécution, propriétés Xray / JDD / requêtes, dépendances et impact, réutilisation,
      aperçu mobile, captures. Commit / MR : phase 7.
- [x] Exécution : un dossier par run, historique, suivi en direct, KPI, étapes et logs d'un test, arrêt, relance des échecs.
- [ ] Paramètres › Connexions : détail des flux (sens, fréquence, proxy, certificats) — prochaine étape demandée.
- [x] Écran de référence (carte) à côté de l'écran réel pour une étape en échec (locator résolu depuis le dépôt).
- [ ] Agents / planification / file d'attente.
- [x] Projet de démonstration `demo/banque_connexion/` : module Connexion d'une application web fictive, 7 tests réellement
      exécutés (dont un échec réel dû à une anomalie volontaire), carte observée, patrimoine Xray fictif, stratégie d'exemple.

### Test Strategy (cahier des charges du 2026-11-14)
Moteur `atelier/intelligence/strategie.py`, écran « Test Strategy » (14 rubriques, menu latéral, complétude).
- [x] Phase 1 Socle : stratégie par projet (RG01), versions, vue d'ensemble (A à G), objectifs mesurés, périmètre
      hiérarchique avec import Xray / Jira (identifiants externes conservés, sans doublon).
- [x] Phase 2 Configuration : types, niveaux (pyramide), environnements (vérification de disponibilité, accès = référence
      au secret), critères d'entrée / sortie (automatiques mesurés ou manuels avec preuve), risques (criticité calculée,
      matrice), données de test (présence du JDD), outils (état des connexions des Paramètres).
- [x] Phase 4 Intelligence (partie) : couverture et traçabilité depuis le Knowledge Graph ; plan d'automatisation depuis
      les candidats calculés, décisions humaines journalisées (« Recommandé par IA » réservé à une analyse IA réelle).
- [x] Phase 5 Gouvernance : workflow Draft → In Review → Approved → Published → Archived, contrôles bloquants, version publiée
      immuable (RG03, RG12), comparaison, restauration, journal d'audit, export PDF (impression du navigateur), carte
      Dashboard, avertissement des critères d'entrée au lancement d'un run.
- [ ] Phase 3 Intégrations : connecter / synchroniser Jira, Xray, GitLab depuis la stratégie (dépend de la vérification 1.4).
- [ ] Rôles et droits (QA Manager, Test Lead…) : nécessite une authentification, absente de l'interface locale.
- [ ] Recommandations IA du plan d'automatisation (explicables, à valider) ; multi-projets dans une même interface.
- [ ] Le périmètre n'alimente pas encore le Knowledge Graph (nœuds déclarés) ni les recommandations IA.

### Test Design (cahier des charges du 2026-11-14) — écart détaillé : docs/TEST_DESIGN_ECARTS.md
Moteur `atelier/generation/conception.py`, écran « Test Design » (13 rubriques). Xray reste le référentiel officiel.
- [x] Vue d'ensemble (KPI réels), exigences avec tests associés, cas de test Xray (type → éditeur, mode, revue, synchronisation).
- [x] Revue & validation interne (Draft → In Review → Changes Requested → Approved → Ready for Automation), séparée du statut
      Xray, contrôles (exigence, BDD, JDD, doublons), historique des décisions, réviseur.
- [x] Baselines immuables et comparaison (dont tests impactés par une exigence modifiée).
- [x] Xray Mapping : objets, champs (sens, actif, obligatoire, transformation, champs personnalisés), statuts sans
      équivalent supposé, test du mapping sur l'instantané ; modes A (import), B / C (publication du Gherkin Cucumber, conflits).
- [x] Scénarios BDD, JDD, suites, traçabilité, réutilisables : écrans existants réutilisés ou vues en lecture.
- [ ] Règles de test ; éditeur d'étapes manuelles ; génération IA de cas depuis une exigence ; import Excel / CSV.
- [x] Modes B / C pour le Gherkin, conflits détectés, historique (createTest / updateGherkinTestDefinition conformes au schéma, essai réel à faire).
- [ ] Arborescence du Test Repository, Test Sets, publication des tests Manual / Generic.

### Automation Studio et Execution Center (cahiers des charges du 2026-11-14) — docs/AUTOMATION_EXECUTION_ECARTS.md
- [x] Navigation globale par module, projet unique dans le header, contexte d'exécution figé et historisé.
- [x] Automation Studio : référentiels locators (fiabilité, obsolètes, manquants), keywords (doublons, inutilisés,
      wrappers 1:1), page objects (cohérence entre plateformes), mapping BDD → socle, frameworks, Git en lecture,
      revue technique des scripts avec retour en revue après modification, espaces d'automatisation, historique.
- [x] Execution Center : campagnes, sélection avec contrôle préalable, configuration, file à priorités, runner local,
      devices, preuves, historique, comparaison, état de synchronisation Xray, retry historisé (instables détectés).
- [ ] Runners distants et parallélisme, réservation de devices, planification (cron, webhook, CI), notifications.
- [ ] Builder à palette d'actions, Git en écriture (branche, MR), Failure Analysis (qualification des échecs).

### Application Intelligence, Failure Analysis, Quality Governance (2026-11-14) — docs/INTELLIGENCE_ECHECS_GOUVERNANCE_ECARTS.md
- [x] Navigation des 8 modules ; vues Fonctionnel / Technique du graphe central ; explorateur d'écrans ; Jira (instantané) ;
      changements entre sources ; file de validation.
- [x] Failure Analysis : collecte automatique, hypothèses par règles explicables, investigation (attendu / obtenu),
      regroupement réversible, tests impactés, décisions, retest via la file, brouillon Jira, IA à la demande.
- [x] Quality Governance : KPI documentés et historisés, couvertures, efficacité, santé, stabilité, risques,
      release readiness avec avis QA, recommandations suivies, rapports PDF / CSV, paramètres.
- [x] Descriptions et critères Jira, création d'anomalies et doublons, versions du graphe.
- [ ] Import Jira complet (tickets sans test, historique des instantanés), extraction IA, propositions de code.

### Deuxième phase (§13)
- [ ] Journey Graph. - [x] BDD Scenario Graph (synchronisé avec le .feature). - [ ] Failure Diagnosis Graph.
- [ ] Automation Health Graph (nécessite l'historique des exécutions).

---

## Phase 2 — Assertions (fiabilité des tests générés)

- [ ] Modèle d'assertion : `type` ∈ {ui, api, base, historique}, `cible`, `attendu`, `source`
      (step « Alors », résultat attendu Xray, règle de gestion).
- [ ] Analyse des steps « Alors / Et » et des résultats attendus Xray → assertions candidates.
- [ ] Stratégie de vérification par type de résultat :
      message ou état à l'écran → UI ; statut ou montant → API si disponible, sinon base ;
      opération enregistrée → historique UI ou requête base. Ne pas tout vérifier par l'interface.
- [ ] Outil MCP `propose_assertion` (validé dans l'interface comme les steps).
- [ ] Keywords génériques du socle : `Vérifier Écran`, `Vérifier Valeur API`,
      `Vérifier En Base` (requête de la liste blanche), avec messages d'échec explicites.
- [ ] Contrôle : un test généré sans aucune assertion sur le résultat métier est refusé.
**Acceptation** : sur 3 scénarios fictifs (virement, ajout bénéficiaire, paiement facture), les
assertions générées couvrent chaque « Alors » ; tests unitaires de la classification.

---

## Phase 3 — Test Intelligence Engine (que faut-il automatiser ?)

- [ ] Collecte par projet Xray : tests manuels, type, priorité, libellés, composants, module
      (dossier du Test Repository), historique des exécutions (fréquence, statuts), défauts liés.
- [ ] Critères, chacun avec sa valeur, sa source et sa disponibilité :
      criticité métier, fréquence d'exécution, répétitivité, stabilité du parcours (carte),
      faisabilité (écrans et locators connus, robustesse), données (JDD disponibles),
      coût de maintenance estimé, recouvrement avec des tests existants (similarité de texte
      simple, sans dépendance lourde).
- [ ] Score pondéré configurable et **explicable** : chaque recommandation liste les critères qui
      l'ont fait monter ou descendre, et les données manquantes.
- [ ] Décision : à automatiser / à investiguer / à reporter / à ne pas automatiser.
- [ ] Onglet « Patrimoine » dans l'interface : tableau trié, filtres, export, envoi des tests
      retenus vers l'étape « Choisir le test ».
**Acceptation** : jeu de données Xray fictif (50 tests) → classement stable, chaque ligne justifiée,
critères manquants affichés comme tels (jamais inventés).

---

## Phase 4 — Carte robuste

- [ ] Reconnaissance pondérée : resource-id / accessibility id / data-testid (très élevé),
      texte fixe (élevé), structure (moyen), activité ou URL (moyen), position (faible) ;
      score de confiance renvoyé avec chaque reconnaissance.
- [ ] Contexte d'observation enregistré : plateforme, version de l'app, langue, état, rôle /
      compte, origine (observation, exploration, TNR), confiance.
- [ ] Modèle à deux niveaux : **écran fonctionnel** (nom métier, fonctionnalité) → une
      **implémentation** par plateforme (empreinte, éléments, transitions, comportements).
      Plus jamais de fusion technique automatique Android / iOS : on relie deux implémentations
      au même écran fonctionnel.
- [ ] Script de migration des fichiers `app_map/` existants vers le nouveau modèle.
**Acceptation** : jeux de hiérarchies fictives (variantes d'un même écran, écrans proches mais
différents) → zéro faux positif sur les cas « différents », reconnaissance des variantes.

---

## Phase 5 — Application Knowledge Graph (niveau 1)

- [ ] Entités : application, module, fonctionnalité, écran fonctionnel, test Xray, scénario BDD,
      test Robot. Relations typées avec `provenance` ∈ {observé, déclaré, déduit}, `source`,
      `date`, `statut` ∈ {validé, à valider}.
- [ ] Alimentation automatique : arborescence du Test Repository Xray (modules / fonctionnalités),
      liens tests ↔ BDD (Xray), tests Robot (tags de clé Xray), écrans ↔ tests (cartographie TNR).
- [ ] Vue arborescente module → fonctionnalité → écrans / tests / automatisations ; couverture.
- [ ] Outils MCP : `feature_info`, `coverage_report`, `screen_info` enrichi (fonctionnalité, tests).
- [ ] Règle : un lien « déduit » non validé n'est jamais utilisé pour une décision (TNR, score).
**Acceptation** : sur le dépôt fictif, la vue reconstitue la hiérarchie et la couverture sans saisie.
Niveaux suivants (hors phase) : règles de gestion (extraction des US Jira + validation),
rôles, API, dépendances et analyse d'impact branchée sur le calcul de profondeur.

---

## Phase 6 — API Discovery & Automation

- [ ] Import OpenAPI / Swagger : endpoints, méthodes, paramètres, schémas de réponse, sécurité.
- [ ] Dépendances entre endpoints (ressource créée par l'un, utilisée par l'autre).
- [ ] Liens endpoints ↔ fonctionnalités (knowledge graph) et ↔ tests Xray.
- [ ] Génération BDD puis Robot Framework avec RequestsLibrary, mêmes conventions
      (INITIALISATION + JDD, pas de donnée littérale, tags Xray), authentification configurable.
- [ ] Exécution et remontée Xray par le même moteur d'exécution (journal, reprise).
- [ ] Assertions API réutilisables par les tests mobiles et web (phase 2).
**Acceptation** : une spec OpenAPI fictive « bénéficiaires » → endpoints identifiés, tests générés
et exécutés contre un faux serveur local, résultats dans le journal Xray.

---

## Phase 7 — Boucle de maintenance encadrée et niveaux d'autonomie

- [ ] Qualification en 6 catégories : bug applicatif, données, locator invalide, environnement,
      synchronisation / timing, scénario ou assertion. Chaque qualification conserve ses preuves :
      logs, capture, step, locator utilisé, historique de l'écran dans la carte, score de confiance.
- [ ] Actions par catégorie : bug → brouillon d'anomalie Jira ; locator → proposition depuis la
      carte (locators de secours, tags apparus) ; timing → ajustement d'attente explicite ;
      données → vérification JDD ; scénario → signalement au QA.
- [ ] Validation humaine → réexécution → **3 exécutions stables** (Android et iOS si concernés)
      → proposition de MR GitLab (branche, diff, description, lien Xray). Jamais de commit direct.
- [ ] Contrôles avant MR : robocop, vérification des conventions (pas de donnée littérale,
      tags présents, pas de wrapper 1:1, assertions présentes), relecture critique par l'agent.
- [ ] Trois modes : **assisté** (validation de chaque step), **semi-autonome** (steps connus
      exécutés seuls, nouveaux steps validés), **autonome contrôlé** (scénario déjà approuvé,
      environnement autorisé). Passage d'un mode à l'autre conditionné par des indicateurs
      (taux de steps validés sans correction, taux de stabilité) et autorisé par un humain.
- [ ] Trois niveaux de sécurité : exploration / construction / exécution (voir CLAUDE.md).
- [ ] Indicateurs exportables (Grafana) : taux d'autonomie, coût et temps par test, instabilité.
**Acceptation** : scénarios d'échec simulés pour chaque catégorie → bonne qualification avec preuves,
aucune MR proposée avant 3 passages stables, aucune modification silencieuse.

## V2 — Workbench piloté par Cursor (cahier : docs/CAHIER_V2.md)
- [x] Phase 0 — Audit de l'existant : matrice EXISTANT / À AMÉLIORER / À CRÉER, 76 outils MCP classés (docs/V2_AUDIT_PHASE0.md)
- [x] Phase 0 bis — Validation côté serveur des outils MCP d'écriture (jira_transition, import_results_to_xray, qualify_failure, transitions de run_robot, fusion d'écrans / remplacement de locator, tap / type_text hors Discovery)
- [x] Phase 1 — Parcours de fonctionnalité (web + MCP) — docs/V2_PHASE1_PARCOURS.md
- [x] Phase 2 — Cursor Integration (règles structurées, versionnement, export, configuration MCP) — docs/V2_PHASE2_CURSOR.md
- [x] Phase 3 — Coverage avancé (parcours, composants UI, niveaux de couverture) — docs/V2_PHASE3_COUVERTURE.md
- [x] Phase 4 — Test Design avancé (catégories de scénarios, doublons) — docs/V2_PHASE4_TEST_DESIGN.md
- [x] Phase 5 — Knowledge Graph (Champ, Anomalie) — docs/V2_PHASE5_KNOWLEDGE_GRAPH.md
- [x] Phase 6 — Failure Analysis (liens échecs ↔ écrans, composants, champs, anomalies) — docs/V2_PHASE6_FAILURE_ANALYSIS.md
- [x] Phase 7 — Consolidation (non-régression, intégration MCP, sécurité) — docs/V2_BILAN.md

## Automatisation multi-technologies (docs/AUTOMATISATION_MULTI_CIBLES.md, 2026-11-25)

Une phase à la fois. Points d'entrée : parcours, User Story, Test Plan Xray ; le MCP déroule la chaîne.

### A. Faire tourner le projet UI Automator du dépôt de tests
- [x] Compilation (Gradle 8.7, SDK 34) : BUILD SUCCESSFUL, APK hôte et APK de test produits
- [ ] Installation sur le téléphone (confirmation MIUI « Installer via USB » à accepter sur l'appareil) ou émulateur
- [ ] Suite `login` exécutée ; temps et stabilité comparés à Robot ; comportement de Promon constaté

### B. Abstraction « technologie » (sans changement de comportement)
- [x] Plan d'automatisation neutre : generation/plan_automatisation.py (intentions, élément, donnée, secret)
- [x] Registre generation/technologies/ : robot-appium, robot-web, robot-api branchés sur bdd.generer_robot
      (bibliothèque imposée par la technologie, sortie identique) ; uiautomator et espresso déclarés, indisponibles
- [x] MCP : technologies_disponibles, studio_plan_automatisation ; argument `technologie` de studio_generer_depuis_bdd
      (vide = comportement historique)
- [x] Tests : tests/test_technologies.py (sortie identique, bibliothèque imposée, registre, plan, outils)
- [x] « Réutiliser sans réécrire » : une étape BDD est liée à un keyword existant sans changer son texte (Gherkin Xray
      inchangé) ; le Robot généré appelle le keyword (libellé Xray en commentaire) ; lien cassé signalé (bdd.keyword_lie)
- [ ] Interface : choix de la technologie (« cible ») dans la console TNR auto et le Kanban

- [x] Interface : écran « Automatiser » (#automatiser) — point d'entrée, technologie, sélection des tests, lancement ;
      consigne du Kanban avec la technologie par défaut de l'application
- [x] Points d'entrée : parcours, User Story, Test Plan Xray (generation/perimetre.py ; outils perimetre_automatisation,
      automatiser_perimetre ; demande déposée dans la boîte de l'atelier)

### C. Technologie UI Automator
- [x] Génération depuis le plan : Page Objects par écran (pages/), classe par parcours (bdd/), @Xray, keywords portés
      réutilisés (k_…, arguments intégrés et explicites), Bdd.kt (données, OTP arret / validation, étape à implémenter)
- [x] Essai réel (copie du dépôt SIMPLE) : 146 scénarios BDD générés, 1 187 étapes dont 5 « à implémenter » ;
      compilation Gradle réussie avec le socle et les 1 025 keywords portés
- [x] Exécution : execution/instrumentation.py (build, installation avec refus MIUI expliqué, am instrument, résultats,
      outbox Xray test_debut / test_fin) ; run_tests(technologie="uiautomator")
- [x] Carte enrichie : classe native de chaque élément par plateforme (resource-id, description, texte déjà gardés)

### D. Porter le patrimoine Robot
- [x] generation/portage.py + outil porter_vers_kotlin + bouton de l'écran Automatiser : robot2kotlin du projet Kotlin,
      bilan par test en suivant les keywords appelés (SIMPLE : 93 % des instructions, mais 32 tests complets sur 185)

### E. Robot web complet
- [x] robot-web (Browser) et robot-selenium (SeleniumLibrary : mêmes keywords qu'AppiumLibrary), au choix par application

### F. Espresso
- [x] technologies/espresso.py : même plan, onView par identifiant résolu à l'exécution (sans la classe R), description,
      texte ; tests écrits dans <projet de tests>/espresso/ (invariant fichiers) ; exécution refusée sans projet Gradle
      qui inclut l'application
- [ ] Compilation réelle des tests Espresso (bibliothèque espresso-core absente du cache Gradle : téléchargement à autoriser)

### A (suite). Exécution réelle sur appareil
- [ ] Installation des APK sur le Redmi (confirmation MIUI à l'écran) ou image d'émulateur Android 33 (téléchargement en cours)
- [ ] Suite login exécutée en Kotlin ; temps et stabilité comparés à Robot ; comportement de Promon constaté

## Refonte de l'interface : QAFlow (docs/REFONTE_UI_QAFLOW.md, 2026-11-25)

Nouvelle interface à côté de l'actuelle (/qaflow, même session, même API) ; bascule quand elle est rodée.

- [x] Q0. Coquille et raccourci : /qaflow, en-tête (application, version, plateformes, Centre d'activité IA, thème,
      retour à l'interface actuelle), menu latéral et menu exécution (renvois ↗), accueil à bulle sans pourcentage global,
      choix Concevoir / Automatiser, agrégat /api/qaflow/accueil, lien « Nouvelle interface » dans /plateforme (tests/test_qaflow.py)
- [ ] Q1. Concevoir
  - [x] Consulter les parcours (#parcours) : statut métier, filtre par statut, écrans, BDD validés, tests généré / exécuté /
        validé QA ; agrégat /api/qaflow/parcours (atelier/intelligence/qaflow.py)
  - [x] Espace de travail d'un parcours (#parcours/<id>) : onglets Aperçu (cadrage, ce qui manque, exigences), Écrans,
        Scénarios et tests (trois notions, technologies), Sessions, Historique ; /api/qaflow/parcours/{id}
  - [x] Ajouter un parcours (#ajouter) : étape 1 « cadrer » (même API que le cadrage actuel), puis espace du parcours
  - [x] Session assistée en direct (#session/<parcours>[/<session>]) : étapes 2 à 5 — cible (appareil ou adresse web),
        miroir de l'écran cliquable (classement côté serveur : navigation sûre exécutée, action sensible confirmée,
        interdite refusée), chrono, compteurs et événements en direct, pause, annotation, fin, résultats, génération
        du scénario BDD (≥ 2 écrans) ; lecture /api/qaflow/session/{sid}, écritures par les routes Discovery existantes
  - [x] Saisir et vérifier depuis le miroir (modes Naviguer / Saisir / Vérifier) : une valeur saisie devient une donnée
        du profil du parcours (catalogue Discovery, secret au coffre) et se saisit par {{var:CLE}} ; une vérification
        (« affiche le texte » ou « est affiché ») est consignée dans la session, sa valeur attendue devient une donnée
        ATTENDU_… ; le BDD généré reprend saisies (« je renseigne … avec la donnée … ») et vérifications (« Alors … »),
        corrigées ou retirées entre-temps (sessions_discovery.saisir / verifier / corriger_consigne,
        donnees.enregistrer_saisie, parcours_bdd.etapes_de_session ; tests/test_saisie_verification_session.py)
  - [x] Saisir : taper une valeur, ou choisir une donnée existante (donnée du parcours, variable du catalogue proche du
        champ, champ d'un jeu de données des tests ; secrets masqués) ; le jeu de données du test du parcours
        (data/jdd/<env>.yaml, jeu = profil du parcours, secret → {{env:CLE}}) est réécrit à chaque saisie ou
        modification (donnees.donnees_pour_saisie, jdd_du_parcours, ajouter_au_parcours, retirer_du_parcours)
  - [x] Étapes prédéfinies « SMS par adb » (Android) pendant la session et par le MCP (discovery_etape_predefinie) :
        préparer la réception d'un SMS (repère), saisir l'OTP reçu dans le champ désigné (code jamais affiché ni écrit),
        ouvrir / récupérer le lien reçu (LIEN_SMS) ; BDD : textes fixes, repère inséré avant l'action qui envoie le SMS ;
        Robot : bibliothèque SMS du dépôt réutilisée, sinon libraries/SmsAdb.py livrée une fois, OTP selon ${OTP_MODE} ;
        Kotlin : Bdd.otpDansChamp / lienSms ; Espresso : lien « à implémenter » (discovery/sms.py, generation/etapes_sms.py,
        règle discovery.mdc ; tests/test_etapes_sms.py)
  - [x] Onglet « Jeux de données » : ajouter une donnée (nouvelle, ou existante du catalogue), la modifier, la retirer du
        parcours ; jeu des tests affiché avec ses champs
  - [x] Jeux de données du parcours (onglet « Jeux de données ») : données du parcours modifiables à tout moment (valeur
        du profil, secret remplacé sans être affiché), saisies et vérifications des sessions (retirer, changer le type) ; jeux des scénarios (Validé s'il existe dans
        data/jdd/<env>.yaml, À faire sinon), scénarios qui consomment une donnée sans jeu, données proposées par l'IA
        (À valider, bouton Confirmer), profil de données ; aucune valeur secrète ; /api/qaflow/parcours/{id}/jdd
- [x] Q2. Automatiser (#automatiser/<référence>, #automatisation/<demande>) : référence US, test existant, parcours, plan
      de test ou expression libre (tests existants proches proposés, sinon le MCP conçoit le scénario depuis la demande) ;
      technologie ; options « rechercher l'existant d'abord » et « exécuter après génération » ; demande déposée au MCP ;
      suivi test par test lu dans l'atelier (demande prise, scénario BDD, script généré, exécuté, validé QA — jamais
      d'après le compte rendu de l'agent), relu toutes les 5 s ; automatisations récentes
      (generation/perimetre.py : entrées test et libre ; generation/suivi_automatisation.py ; tests/test_automatisation_qaflow.py)
- [x] Q3. Centre d'activité IA complet (travaux : étapes réelles, dépendance, livrables, erreur, décision acceptée ou
      refusée depuis le panneau ; demandes à l'agent avec compte rendu et lien vers le suivi QAFlow ; session en cours ;
      ce qui attend l'utilisateur d'abord) et centre d'exécution QAFlow (#execution : en cours, en file, exécutions
      réussies / en échec, tests passés / échoués — des nombres, aucun pourcentage —, exécutions récentes avec type,
      environnement, version) ; /api/qaflow/activite, /api/qaflow/execution (tests/test_activite_execution_qaflow.py)
- [x] Q4. Release notes (#releases, #releases/<id>) : Release Note déposée en fichier (PDF, DOCX, TXT, MD → texte à relire,
      bibliothèque standard seulement : atelier/intelligence/documents.py) ou collée ; évolutions et tests impactés ;
      tests complémentaires à concevoir (évolution sans test ou non rattachée) ; analyse IA ; build reçu ; périmètre en trois
      catégories, chaque test avec sa raison, proposé / retenu / retiré (justifié) / ajouté ; validation ; campagne préparée
      vers le centre d'exécution (tests/test_documents_releases_qaflow.py)
  - [x] Processus de release en 8 étapes lues dans les données (Release Note analysée → build reçu → périmètre validé →
        Test Plan Xray → Test Execution Xray → exécution lancée → résultats dans Xray → verdict du build), étape courante
        mise en avant ; SORTIE de la release = Test Execution Xray (découpage unique / par type / par module, environnement)
        rangée dans le Test Plan de la release, puis une campagne par Test Execution qui écrit ses résultats dans cette
        exécution, relecture des résultats Xray, verdict Passed / Failed (qaflow.processus_release,
        /api/qaflow/releases/{id}/processus ; tests/test_processus_release_qaflow.py, Xray simulé)
- [x] Contrôle avant bascule, comme le MCP (vrai serveur MCP, tests/test_qaflow_mcp_bout_en_bout.py) : conception (écrans,
      données, graphe, plan de test, BDD depuis la carte) puis automatisation (périmètre test / libre, dépôt, prise par
      atelier_demande_suivante, plan, génération Robot, dry-run) ; corrigé : envoi jamais réglé (« lien ») → la demande
      d'automatisation attend le MCP dans la boîte au lieu d'être refusée ; test déjà automatisé sans BDD affiché « Sans BDD »
- [x] Gardés dans le nouveau processus : Knowledge Graph (#graphe : vues fonctionnel / parcours et écrans / tests, moteur
      graphe.js réutilisé, détail d'un nœud, valider / rejeter, en direct), couverture du graphe par les tests (calque
      couvert / partiel / échec / sans test, liste à couvrir), MBT dans l'espace du parcours (onglet Modèle : construire,
      couverture comportementale par niveau en nombres, chemins proposés, BDD générés), exécution en direct dans le centre
      d'exécution (test courant, keyword, chemin d'écrans, statuts, arrêt ; écran de l'appareil seulement pour un run mobile)
- [x] MBT terminé → au choix : « Concevoir » (scénarios BDD à relire, onglet Scénarios du parcours) ou « Automatiser ces
      chemins » (scénarios créés ou déjà existants envoyés au MCP : point d'entrée « tests », liste de clés)
- [x] Menu de droite : Exécution en direct (#direct : graphe du run, écrans en couches dans l'ordre parcouru, état de
      chaque écran, tests, dernières actions) et Couverture des parcours (#couverture : parcours × étapes, écrans, matrice
      tests × écrans ; même calcul que le tableau du dashboard, /api/couverture/carte)
- [x] Code au niveau de l'APPLICATION : fiche application = projet Xray, projets Jira associés, cibles (URL web, package
      Android, bundle iOS), dépôt des tests (dossier local, GitLab https, projet GitLab, branche cible) ; le code généré
      (tests, resources, libraries, data/jdd, args, projets Kotlin / Espresso) est écrit, lu, exécuté et commité dans le
      dépôt de l'application active, merge request sur son GitLab ; la connaissance (carte, BDD, graphe, Discovery,
      releases, résultats) reste au projet ; sans dépôt déclaré, comportement historique (projet.racine_code / safe_path /
      relatif, gitlab._cible ; tests/test_depot_application.py). Projet = accès Jira (URL, e-mail, jeton) et Xray (client
      id / secret) au coffre, écran QAFlow #parametres
- [x] Technologie iOS native XCUITest (Swift) : generation/technologies/xcuitest.py (même plan d'automatisation ; Socle/Atelier.swift :
      éléments depuis les locators de la carte, données JDD_<JEU>_<CHAMP> en variables d'environnement, OTP par OTP_CODE ;
      tests Bdd/<Classe>Tests.swift, clé Xray dans le nom test_TAM_301_…) ; conversion Robot → XCUITest
      (generation/robot2swift.py, outil porter_vers_xcuitest, bouton dans QAFlow Automatiser : AppiumLibrary et BuiltIn
      courants, keywords utilisateur → k_<slug>, arguments intégrés, ${X_${PLATFORM}} résolu en iOS, ${JDD}[champ] ;
      sinon échec nommé : « locator iOS absent », structure IF / FOR) ; exécution xcodebuild sur Mac
      (execution/xcuitest.py, run_tests(technologie="xcuitest"), résultats → outbox Xray) ; projet Xcode dans la fiche
      (xcode_projet, xcode_schema, xcode_cible, xcode_destination, dossier_xcuitest). SIMPLE : 1 017 keywords, 218 complets,
      185 tests, 20 complets — le reste attend surtout les locators iOS (Discovery iOS)
- [x] Plusieurs dépôts par application, un par technologie (fiche : depots [{technologies, dossier, gitlab_url, gitlab_projet,
      branche}]) : projet.pour_technologie / racine_code(technologie) ; commit et merge request vers le GitLab du dépôt
- [ ] Essai sur Mac : compilation (build-for-testing) et run XCUITest réels, merge request vers le dépôt iOS
- [ ] Q5. Menu latéral refait dans QAFlow
- [ ] Q6. Bascule (décision de l'utilisateur)
