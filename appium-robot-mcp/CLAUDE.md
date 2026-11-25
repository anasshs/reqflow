# CLAUDE.md — Atelier d'automatisation (AI Test Engineering Platform)

## Le produit en une phrase
Comprendre l'application, analyser le patrimoine de tests Xray, identifier ce qu'il faut
automatiser, puis générer, exécuter et maintenir des tests Robot Framework (mobile AppiumLibrary,
web Browser library, API RequestsLibrary) avec une traçabilité complète dans Xray et Jira.

## Où on en est
Phase 1 : 1.1, 1.2, 1.3 faites ; 1.4 : schéma Xray vérifié conforme par introspection le 2026-11-14
(docs/XRAY_API_resultat.md) ; essai réel d'écriture réussi (statut, heures, commentaire, captures, artefacts).
Espaces de travail (docs/ESPACES_DE_TRAVAIL.md) : MVP livré (3 graphes + impact, page /plateforme) ;
la deuxième phase des espaces n'est pas commencée.
Test Strategy : module supprimé comme écran le 2026-11-15 (référentiel de pilotage, voir DECISIONS) ; projet de démonstration
`demo/banque_connexion/` (application web fictive, exécutions réelles).
Test Design : couche de conception autour de Xray (voir docs/TEST_DESIGN_ECARTS.md) ; publication du Gherkin (modes B / C) branchée, schéma `createTest` conforme (essai réel à faire).
Automation Studio et Execution Center : voir docs/AUTOMATION_EXECUTION_ECARTS.md (file d'exécution : atelier/execution/centre.py).
Application Intelligence, Failure Analysis, Quality Governance : docs/INTELLIGENCE_ECHECS_GOUVERNANCE_ECARTS.md.
Testabilité des US (stratégie actionnable) : docs/TESTABILITE_US.md.
Corrélation exigences ↔ écrans (« vérifiée sur » automatique, « réalisé par » validé) : docs/CORRELATION_EXIGENCES_ECRANS.md.
Discovery Data Setup (référentiel universel de variables, profils, générateurs, contexte de session) : docs/DISCOVERY_DATA_SETUP.md.
Parcours utilisateur (initiation de Discovery : cadrer un parcours avant de le dérouler, le rouvrir, le valider) : docs/PARCOURS_UTILISATEUR.md.
Dashboard de pilotage (couverture, exécution, TNR par analyse d'impact, état de préparation) : docs/DASHBOARD_PILOTAGE.md.
Releases (interprétation par Cursor par défaut, création, Release Note, builds successifs comparés, périmètre retest / ciblée / qualification, verdict par build, critères de sortie et qualification ; écran Releases) : docs/RELEASE_NOTES.md.
Pilotage de l'IA (point d'appel unique, journal des tokens, réglages, routage, contexte, cache, budgets, simulateur ; écran Paramètres › Pilotage IA) : docs/PILOTAGE_IA.md.
Chemin de l'utilisateur (Découvrir → Concevoir le test → Automatiser → Exécuter : bandeau « Ton chemin » de l'Accueil, repère
d'étape en haut des écrans du chemin, prochaine action ; options Jira / Xray affichées seulement s'ils sont utilisés) : atelier/intelligence/chemin.py.
Navigation (2026-11-24) : barre latérale courte (Accueil, Mes demandes, « Mon chemin » en 4 étapes, Pilotage, Paramètres) ; deux chemins
basculables, « Application » (Discovery → test) et « User Stories » (US → test, fil de strategie.ETAPES_FIL), affichés tous deux à l'Accueil ;
« Mes demandes » réunit travaux de l'orchestrateur et demandes à l'agent (atelier/execution/demandes.py, compteur dans l'en-tête).
Flux de passage d'un test (2026-11-24) : « simple » par défaut, générer le BDD → automatiser → publier dans Xray, la publication
valant validation et approbation (atelier/generation/flux.py) ; « complet » = cycle avec approbations. Tests : conftest fixe « complet ».
Atelier en Kanban (2026-11-24, écran d'arrivée #atelier) : couloirs par parcours métier, cartes tests par état, transitions qui lancent
des travaux de l'orchestrateur (atelier/generation/kanban.py, ecran_atelier.js) ; Claude Code en ligne de commande (claude -p) : boite_cursor.py.
De l'US au test automatisé (un seul fil dans un périmètre : couverture des US ou parcours, puis automatisation ; guide dans l'outil) : docs/DE_L_US_AU_TEST_AUTOMATISE.md.
Lots TNR (écran #lots, chemin simplifié parcours → scénarios → automatisation vérifiée → Publier au TNR, statut unique par
scénario, conventions TNR par application, cycle de référence unique domain/cycle.py) : docs/AUDIT_PARCOURS_TNR.md, generation/lots.py et tnr.py.
Tests automatisés (vue simple, écran #tests : À valider / Validé / Écarté, « Vérifié » = run réel après la dernière modification de
la suite et de ses pages ; Vérifier = run Robot --test de la sélection, permis avant validation sauf consomme_donnee ; Valider en un
clic ; maintenance d'une sélection = une demande à l'agent ; outil MCP run_tests) : atelier/generation/maintenance.py.
Knowledge Graph : vue fonctionnelle reliée (module → mène à → module, parcours → traverse → module, parcours → s'enchaîne
avec, déduits de la Discovery ; liens « via » dans une vue filtrée), suivi en direct pendant une Discovery et fenêtre à part
(#graphe/connaissance/<angle>/direct) : atelier/discovery/connaissance.py, espaces.py, ecran_graphe.js.
Model-Based Testing (modèle comportemental versionné comportement/, moteur de chemins et stratégies, BDD depuis un chemin,
couverture comportementale, mode automatique dans la génération des cas d'US, écran #comportement) : docs/MBT.md.
Agents : Cursor, Claude Code (.mcp.json du projet + règles en CLAUDE.md / skills : atelier/integrations/claude_code.py),
Claude Desktop ; règles du projet mises à niveau automatiquement quand l'atelier en livre de nouvelles (personnalisées gardées).
Projets multiples : Paramètres › Projets et sélecteur du header (atelier/domain/projets.py, docs/DECISIONS.md).
V2 (workbench piloté par Cursor, docs/CAHIER_V2.md) : phases 0 à 7 livrées (docs/V2_BILAN.md) — parcours de
fonctionnalité, demandes d'action validées côté serveur, 13 règles Cursor versionnées (dont « robot-expert » : qualité du code, « model-based-testing » : analyse comportementale), couverture parcours / UI, Test
Design par catégories et doublons, Champ / Anomalie, échecs reliés à la connaissance, jugements délégués à Cursor (granularité, doublons, redondances, liens
exigence ↔ test, orphelins, corrélation écran ↔ exigence : atelier/intelligence/jugement_ia.py). 131 outils MCP (76 historiques
inchangés) ; classement de sécurité de chaque outil : tests/test_securite_outils.py (à compléter pour tout nouvel outil) ;
client MCP de test : tests/client_mcp.py.
Maintenance depuis le Kanban (2026-11-25, atelier/generation/maintenir.py) : colonne « À maintenir » (run réel en échec,
ou test impacté), cause qualifiée (suggestion de Failure Analysis), maintenance par le MCP (scripts et scénario BDD :
maintenance_modifier_bdd, compte rendu : maintenance_rapporter), rien de cassé ailleurs (fichier partagé modifié : tests
impactés en maintenance, rejoués), confirmation humaine (Xray mis à jour, commit), merge request, drapeau « maintenu ».
Un test publié dans Xray a son code commité (atelier/generation/versionnement.py).
Base de l'atelier (2026-11-25, 5 phases livrées) : docs/BASE_ATELIER.md — base de documents locale ou serveur de
données HTTPS (atelier/domain/magasin.py, atelier/serveur_donnees.py), comptes et connexion (utilisateurs.py),
assistant du premier lancement (assistant_poste.py, /assistant), travail et connaissance synchronisés par la base
(synchro.py), paquet installable (outils/paquet.py, raccourcis du lanceur).
Adopter un dépôt existant (2026-11-25, écran #adoption, atelier/generation/adoption.py ; proposé à l'ajout / modification d'un projet, changement de dépôt sans perte de connaissance : domain/reprise.py) : tests Gherkin du dépôt → scénarios BDD
(clé Xray, jeu de données), suites → parcours proposés (techniques écartées), run cartographié → écrans des parcours.
Automatisation multi-technologies (2026-11-25 ; docs/AUTOMATISATION_MULTI_CIBLES.md) : plan neutre (generation/plan_automatisation.py) et
technologies (generation/technologies/ : robot-appium, robot-web, robot-selenium, robot-api, uiautomator, espresso),
points d'entrée (generation/perimetre.py, écran #automatiser), exécution Kotlin (execution/instrumentation.py), portage (generation/portage.py).
Le code vit dans le paquet `atelier/` (moteurs + intégrations + façades).
Les fichiers racine `server.py`, `app_map.py`, `jdd.py`, `xray_client.py`, `web_backend.py`,
`xray_live_listener.py`, `cartographie_listener.py` et `web/app.py` ne sont plus que des points
d'entrée de rétrocompatibilité. Outils MCP : `atelier/adapters/facade.py` (enregistrés par
`atelier/adapters/mcp/server.py`). Tests : `tests/` (`pytest -q`).
Le travail à faire est décrit phase par phase dans **docs/ROADMAP.md**. Toujours travailler sur
UNE phase à la fois, cocher les tâches terminées dans la roadmap, et ne pas anticiper la suivante.

## Architecture cible (phase 1, puis à respecter partout)
Le MCP n'est PAS le produit : c'est une façade. L'interface web en est une autre.
```
atelier/
  domain/          modèles et services métier partagés (aucune dépendance MCP / FastAPI)
  discovery/       Application Discovery Engine : sessions, observation, carte, exploration, knowledge graph
  intelligence/    Test Intelligence Engine : analyse Xray, score d'automatisation
  generation/      Test Generation Engine : BDD, locators, keywords, suites, assertions
  execution/       Test Execution Engine : runs Robot, listeners, journal Xray, qualification, maintenance
  integrations/    xray/, jira/, gitlab/, oracle/, appium/, playwright/ (clients bas niveau)
  adapters/mcp/    serveur MCP : uniquement des fonctions minces qui appellent les moteurs
  adapters/web/    FastAPI + static : uniquement des routes minces qui appellent les moteurs
```
Règles : un moteur n'importe jamais un adapter ; les adapters ne contiennent aucune logique
métier ; l'état de session (driver Appium, page Playwright) vit dans `discovery`, pas dans le MCP.

## Contraintes non négociables
- **Langue** : interface, docstrings, messages, documentation et commits en français.
  Identifiants Python : garder le style existant (mélange français/anglais toléré, cohérent par module).
- **Aucune donnée client dans le dépôt** : pas de vraie clé Xray, compte, URL interne, locator
  d'une app réelle, capture d'écran d'app bancaire. Fixtures = apps fictives (`tests/fixtures/`).
- **Secrets** en variables d'environnement, ou dans le coffre du système (Gestionnaire d'identifiants Windows via
  `keyring`, décision de l'utilisateur du 2026-11-14). Jamais dans un fichier de l'atelier ni dans les logs ;
  jamais renvoyés par l'API.
- **Réseau d'entreprise** : proxy TLS (certificat via `XRAY_CA_BUNDLE`), Promon sur les builds,
  Oracle par SID. Ne rien supposer d'accessible sur Internet hormis les API Xray/Jira configurées.
- **Interface locale** : écoute 127.0.0.1 uniquement, jamais exposée.
  Seule exception, par décision de l'utilisateur (2026-11-25) : le serveur de données de l'atelier
  (serveur_donnees.py), HTTPS obligatoire hors de la machine et chaque appel authentifié par un compte.
- **Rétrocompatibilité MCP** : garder les noms et signatures des outils MCP existants
  (Cursor et les règles `.cursor/rules` les utilisent). Ajouter, ne pas casser.
- **Dépendances** : préférer la bibliothèque standard ; toute nouvelle dépendance doit être
  justifiée dans le message de commit et ajoutée à `requirements.txt`.

## Invariants de sécurité (à tester, jamais à affaiblir)
1. Exploration : aucune saisie, aucune case cochée, aucune action de la liste rouge, liens externes ignorés.
2. Base de données : SELECT uniquement, requêtes en liste blanche, paramètres liés, délai et nombre
   de lignes plafonnés, compte en lecture seule.
3. Fichiers : lecture/écriture limitées au projet de tests (`_safe_path`), pas d'écrasement implicite.
4. Une indisponibilité Xray / Jira / carte n'interrompt jamais un run Robot.
5. Aucune correction de test n'est déclarée fiable sans 3 exécutions stables ET revue humaine.
6. Les actions sensibles (paiement, virement, suppression, validation métier) ne sont exécutées
   que si le scénario les autorise explicitement, sur un environnement autorisé.

## Conventions des tests Robot GÉNÉRÉS (le produit les impose)
- BDD en Gherkin français + Page Object Model ; séparation locators / keywords / scénarios.
- Réutiliser le socle existant avant de créer ; jamais de wrapper 1:1 par élément.
- Chaque test : bloc INITIALISATION (« Initialiser Le Test » avec un dictionnaire &{JDD_<NOM>})
  puis SCÉNARIO Gherkin sans donnée littérale.
- Tags : clé Xray + tags fonctionnels (smoke, e2e, negatif, consomme_donnee).
- Une suite par parcours métier : les tests d'un même parcours vont dans la même suite (décision de l'utilisateur du
  2026-11-20, `atelier/generation/suites_parcours.py`) ; un test sans parcours garde sa suite. Mêmes clés métier de
  locators sur Android et iOS.

## Points d'API à vérifier sur la documentation officielle (ne pas supposer)
Les appels GraphQL Xray Cloud ont été écrits de mémoire. Avant de les industrialiser, vérifier
leur existence et leurs arguments (documentation Xray Cloud GraphQL ou introspection du schéma) :
`updateTestRunStatus`, `updateTestRun(startedOn, finishedOn, comment)`, `addEvidenceToTestRun`,
`createTestExecution`, `createTestPlan`, `addTestExecutionsToTestPlan`, `addTestsToTestPlan`,
`addTestsToTestExecution`, `getTestRuns`, `getTests`, `getTestPlans`, `getTestExecutions`,
l'import REST `/api/v2/import/execution/robot`. Consigner le résultat dans `docs/XRAY_API.md`.

## Tests et qualité
- `pytest -q` doit passer avant chaque commit. Aucun test ne doit appeler un vrai service :
  Xray, Jira, GitLab, Oracle, Appium et l'API Claude sont simulés (fixtures, faux serveurs).
- Le web se teste en réel avec Playwright sur des pages HTML locales (`tests/fixtures/sites/`).
- Le parsing mobile se teste sur des XML de hiérarchie fictifs (Android classique, Compose sans
  testTag, iOS).
- Linter : `ruff` (si ajouté) ; les `.robot` générés passent `robocop` (phase 7).
- Commits petits et thématiques, un ou plusieurs par tâche de la roadmap.

## Commandes
```
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
playwright install chromium      # ou WEB_BROWSER_EXECUTABLE=/chemin/chromium
lancer-atelier.cmd / ./lancer-atelier.sh  # assistant : Python, .venv, dépendances, Chromium, projet de tests, puis lancement
python installer.py              # le même assistant, sans lancer (lanceur.py --verifier)
python server.py                 # serveur MCP (stdio) -> atelier/adapters/mcp/server.py
MCP_HTTP_PORT=8000 python web/app.py  # l'interface démarre aussi le MCP en HTTP : http://localhost:8000/mcp
python web/app.py                # interface web http://127.0.0.1:8765 -> atelier/adapters/web/app.py
pytest -q
```
