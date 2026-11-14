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
Test Strategy : phases 1, 2, 5 et une partie de la 4 livrées (voir ROADMAP) ; projet de démonstration
`demo/banque_connexion/` (application web fictive, exécutions réelles).
Test Design : couche de conception autour de Xray (voir docs/TEST_DESIGN_ECARTS.md) ; publication du Gherkin (modes B / C) branchée, schéma `createTest` conforme (essai réel à faire).
Automation Studio et Execution Center : voir docs/AUTOMATION_EXECUTION_ECARTS.md (file d'exécution : atelier/execution/centre.py).
Application Intelligence, Failure Analysis, Quality Governance : docs/INTELLIGENCE_ECHECS_GOUVERNANCE_ECARTS.md.
Projets multiples : Paramètres › Projets et sélecteur du header (atelier/domain/projets.py, docs/DECISIONS.md).
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
- Un scénario end-to-end par suite ; mêmes clés métier de locators sur Android et iOS.

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
python server.py                 # serveur MCP (stdio) -> atelier/adapters/mcp/server.py
python web/app.py                # interface web http://127.0.0.1:8765 -> atelier/adapters/web/app.py
pytest -q
```
