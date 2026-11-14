# Appium Robot MCP

Mobile (AppiumLibrary, Android + iOS) et web (Browser library), avec Xray, Jira et une interface
web de contrôle.

Serveur MCP qui branche Claude Desktop sur un device Android / iOS via Appium, pour relever
les locators, générer la couche locators Robot Framework (POM) et lancer / analyser les suites.

## Installation (macOS)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
npm i -g appium
appium driver install uiautomator2
appium driver install xcuitest
appium            # laisser tourner (port 4723)
```

Copier le contenu de `claude_desktop_config.example.json` dans
`~/Library/Application Support/Claude/claude_desktop_config.json` (adapter les chemins),
puis redémarrer Claude Desktop.

### Sous Cursor

Même serveur, même transport (stdio). Copier `cursor_mcp.example.json` dans
`.cursor/mcp.json` à la racine du projet de tests (ou `~/.cursor/mcp.json` pour tous les
projets), adapter les chemins, puis activer le serveur dans *Settings → MCP*.
Avantage sous Cursor : l'agent voit directement les fichiers du projet, il peut donc
écrire locators, steps et suites dans l'éditeur et lancer `run_robot` dans la foulée.

## Organisation du code

Le code vit dans le paquet `atelier/` : moteurs (`discovery`, `generation`, `execution`,
`intelligence`), services partagés (`domain`), clients bas niveau (`integrations`) et façades
(`adapters/mcp`, `adapters/web`). Les fichiers racine (`server.py`, `web/app.py`, listeners…)
restent les points d'entrée : les configurations existantes n'ont pas à changer.
Tests : `pytest -q` (aucun service réel appelé).

## Espaces de travail (graphes) — http://127.0.0.1:8765/plateforme

Spécification : `docs/ESPACES_DE_TRAVAIL.md`. MVP livré :

- **Application Knowledge Graph** (Application Map, Functional / Technical Graph) : carte, dépôt Robot, JDD,
  instantané Xray, derniers résultats, et ce que l'automaticien déclare (ajout, modification, masquage,
  relation, fusion, validation — tout est historisé dans `connaissance/` du projet de tests).
- **Xray Coverage Graph** : Epic → User Story → Test Xray → Test Robot, indicateurs par module calculés sur
  des définitions affichées (un test est « automatisé » si sa clé est portée en tag par un test Robot).
  Le patrimoine vient d'un instantané daté `patrimoine/xray.json` (Xray Portfolio : import JSON ou
  synchronisation Jira).
- **Automation Flow Graph** : scénario → test Robot → keywords → locators (et secours) → écrans ; JDD →
  requêtes Oracle ; bibliothèques et plateformes.
- **Impact Analysis** : depuis un locator, keyword, resource, écran ou JDD : tests, scénarios, modules,
  plateformes concernés, et TNR ciblée (dry run ou run réel).
- Assistant IA contextuel : anomalies calculées sans IA ; avec `ANTHROPIC_API_KEY`, questions sur le seul
  graphe sélectionné. Rien n'est appliqué sans validation.

Outils MCP correspondants : `knowledge_graph`, `impact_analysis`, `coverage_report`, `automation_flow`.

## Outils exposés

| Domaine | Outils |
|---|---|
| Device | `list_devices`, `start_session`, `stop_session` |
| Lecture écran | `screenshot`, `get_screen_elements`, `get_page_source`, `check_locator` |
| Actions | `tap`, `type_text`, `swipe`, `press_back`, `wait_for` |
| POM | `capture_screen_locators`, `generate_locators_resource` |
| Projet Robot | `list_project_files`, `read_project_file`, `write_project_file`, `run_robot`, `parse_robot_output` |
| JDD | `list_jdd`, `get_jdd`, `find_test_data`, `check_jdd` |
| Parcours | `xray_get_test`, `xray_search_tests`, `propose_step` (validation dans l'interface web) |
| Web | `start_session(platform="web")`, `open_url`, `element_at`, `add_screen_locator` |
| Suivi | `jira_subtasks`, `qualify_failure`, `run_robot(relancer_echecs=True)` |
| Xray / Jira | `run_robot(xray_ticket=...)` en live, `xray_inspect_ticket`, `jira_transition`, `import_results_to_xray` |

Les locators sont au format AppiumLibrary : `id=`, `accessibility_id=`, `xpath=`,
`nsp=` (prédicat iOS), `chain=` (class chain iOS).

## Workflow type (trame TAM : ST1 → ST5)

1. **ST1 Locators Android** — « Ouvre une session Android sur emulator-5554, va sur l'écran
   Virement, relève les éléments et capture les locators sous le nom *virement_saisie* avec
   les clés champ_montant, champ_motif, bouton_valider. »
2. **ST2 Locators iOS** — même demande avec une session iOS : mêmes clés métier.
3. `generate_locators_resource("virement_saisie")` produit
   `resources/locators/virement_saisie.resource` :

   ```robot
   *** Variables ***
   &{LOC_VIREMENT_SAISIE_ANDROID}    champ_montant=id=ma.attijari:id/amount
   ...    bouton_valider=accessibility_id=Valider
   &{LOC_VIREMENT_SAISIE_IOS}        champ_montant=accessibility_id=amountField
   ...    bouton_valider=accessibility_id=Valider
   ```

   Sélection de plateforme côté projet : `${LOC}=    Set Variable    ${LOC_VIREMENT_SAISIE_${PLATFORM}}`.
4. **ST3 / Steps BDD** — Claude lit les keywords génériques existants (`read_project_file`)
   et écrit les steps / la suite en s'appuyant dessus (pas de wrapper 1:1 par élément).
5. **ST5 Branchement** — `run_robot` avec `dry_run=True`, puis run réel et `parse_robot_output`.

## Remontée des résultats dans Xray (temps réel)

Un seul paramètre, `xray_ticket`, dont le type est détecté automatiquement :

| Ticket donné | Effet du run |
|---|---|
| Test Plan (ex. TAM-50) | nouvelle exécution créée, ajoutée au plan ; tests ajoutés au plan |
| Test Execution (ex. TAM-77) | exécution mise à jour, tests manquants ajoutés |
| Autre ticket (US, epic) | plan créé et lié au ticket + exécution |
| Clé projet seule (ex. TAM) | plan + exécution créés dans le projet |

`xray_inspect_ticket` dit à l'avance ce que fera le run.

Pendant le run (listener `xray_live_listener.py`, mode `live` par défaut) :
- début de chaque test : test run en **EXECUTING** + heure de début ;
- fin de chaque test : **PASSED / FAILED** + heure de fin, message d'échec en commentaire,
  captures d'écran en preuves ;
- plusieurs tests Robot sur la même clé Xray (Android + iOS) : un seul échec suffit à
  mettre FAILED, début = premier test, fin = dernier ;
- ticket d'exécution : transition Jira au début (`jira_transition_start`, ex. « En cours »)
  et à la fin (`jira_transition_end`, ou `jira_transition_end_if_fail` s'il y a un échec).
  Le nom de la transition ou du statut cible est accepté.

Exemple : « Lance la suite virement en Android sur emulator-5554, tags smoke, sur le plan
TAM-50, passe l'exécution en cours au début puis Terminé à la fin. »

Le rattachement se fait par les tags de clé Xray des tests (ex. ATTIJARI-100). Rapport du run
dans `results/mcp/xray_live_report.json`. Une erreur Xray ou Jira n'interrompt jamais le run.

**Journal et reprise** : chaque événement est d'abord écrit dans un journal local
(`results/mcp/xray/<horodatage>/xray_outbox.jsonl`) puis envoyé à Xray avec reprise (backoff
exponentiel). Si Xray est injoignable, le run va au bout normalement et le journal reste complet ;
le rejouer plus tard, sans doublon :

```bash
python -m atelier xray-sync results/mcp        # tous les runs en attente sous ce dossier
```

Réglages : `XRAY_SYNC_ESSAIS` (6), `XRAY_SYNC_BACKOFF` (1 s), `XRAY_SYNC_PLAFOND` (30 s),
`XRAY_SYNC_DELAI_FIN` (attente maximale en fin de run, 30 s).
Le listener s'utilise aussi seul en CI :
`robot --listener xray_live_listener.py:xray_run_config.json tests/`.

Autres modes : `xray_mode="listener_projet"` (ton listener via `ROBOT_XRAY_LISTENER`) ou
`import_results_to_xray` (import API de output.xml, en secours — pas sur un run déjà
remonté en live). `jira_transition` change le statut d'un ticket à la demande.

Identifiants : `XRAY_CLIENT_ID`, `XRAY_CLIENT_SECRET`, et pour Jira `JIRA_BASE_URL`,
`JIRA_EMAIL`, `JIRA_API_TOKEN` — uniquement en variables d'environnement. Derrière le proxy
TLS de l'entreprise, `XRAY_CA_BUNDLE` pointe vers le certificat racine de la société.

## Carte de l'application (première étape avec une nouvelle app)

L'outil construit un graphe des écrans (nœuds) et des actions qui mènent de l'un à l'autre
(transitions), stocké en YAML dans `app_map/<application>/` du projet de tests (versionné,
relu en MR). Ce n'est pas un entraînement du modèle : c'est une base de connaissance que
l'agent consulte à chaque session.

- **Assistant « Nouvelle application »** (menu des applications) : identité, prérequis (build
  sans Promon, langue fixée, comptes, liste rouge), import des `.resource` existants, rejeu de
  la TNR avec cartographie, exploration, nommage.
- **Enregistrement passif** : chaque action faite via le MCP (Cursor, agent intégré, écran en
  direct) enregistre l'écran et la transition. `MAP_PASSIVE=0` pour désactiver.
- **Exploration** (`explore`, ou panneau de la carte) : parcours en largeur, jamais de saisie,
  jamais d'action de la liste rouge, liens externes ignorés.
- **TNR** : `run_robot(cartographie=True)` ou `--listener cartographie_listener.py:<app>` ; les
  tests Xray qui passent par chaque écran sont mémorisés (couverture, impact).
- **Onglet Carte** : graphe avec vignettes, couleurs (testé, changé au build, à nommer, action
  interdite), renommer, fusionner, supprimer, interdire une action, choisir le locator
  principal, « Y aller » (rejoue le chemin sur le device), exporter le `.resource`.
- **Build** : `map_set_build` ; les écrans revisités sont comparés (orange s'ils changent) et un
  tag apparu devient automatiquement le locator principal.
- **App sans tags (Compose / SwiftUI)** : reconnaissance par textes fixes (fixer la langue),
  UiSelector texte pour les boutons, locator relatif au libellé pour les champs, locators de
  secours + keyword `Localiser` (`socle/localisation_robuste.resource`), rapport priorisé des
  identifiants à demander aux devs (`map_tags_report`, ticket Jira depuis l'interface).

Outils MCP : `map_apps`, `map_create_app`, `map_select_app`, `map_set_build`, `where_am_i`,
`list_screens`, `screen_info`, `name_screen`, `goto_screen`, `explore`, `stop_exploration`,
`map_import_existing`, `map_tags_report`, `export_screen_resource`.

Le guide d'utilisation complet est dans l'interface (bouton **Guide**, et **?** sur les panneaux).

## Web avec Browser library

Mêmes outils, plateforme `web` : le MCP pilote un navigateur Playwright, le moteur de Browser
library, donc les sélecteurs relevés fonctionnent tels quels dans les tests Robot.

```bash
pip install playwright robotframework-browser
playwright install chromium        # et rfbrowser init pour Browser library
```

- `start_session(platform="web", url="https://recette…", headless=False)` ; `open_url` pour naviguer.
- Locators par ordre de robustesse : `data-testid=`, `id=` (ids stables uniquement), `css=input[name=…]`,
  `css=[placeholder=…]`, `role=button[name="…"]`, `text="…"`, chemin CSS en dernier recours.
- `generate_locators_resource` produit `&{LOC_<ECRAN>_WEB}`.
- Runs, Xray live, JDD et qualification : identiques au mobile (variable `PLATFORM=web`).
- Proxy d'entreprise avec certificat interne : `WEB_IGNORE_HTTPS=1` pour la session du MCP.

## Automatiser un parcours

Le plus fiable : partir de la clé du test Xray. `xray_get_test` lit son scénario Gherkin
(ou ses étapes manuelles), et Claude le déroule étape par étape sur le device.

> « Automatise ATTIJARI-200 sur Android avec le jeu VIREMENT_STANDARD (recette) : lis le
> scénario dans Xray, déroule-le sur le device, relève les locators écran par écran,
> réutilise les keywords génériques du projet, puis lance un dry run. »

Sans test Xray, décris le parcours en Gherkin directement dans la consigne.

## Jeux de données (JDD)

Deux fichiers dans le projet de tests (exemples dans `exemple_projet/data/jdd/`) :

- `data/jdd/<env>.yaml` : jeux nommés (`VIREMENT_STANDARD`…), avec leurs données et leurs
  prérequis. `{{env:VAR}}` = secret lu dans l'environnement ; `{{requete:NOM.colonne}}` =
  valeur trouvée en base au moment du run (ex. un compte avec un solde suffisant).
- `data/jdd/requetes.yaml` : requêtes SQL autorisées (liste blanche, SELECT uniquement,
  paramètres liés). Connexion par `DB_<ENV>_HOST`, `_PORT`, `_SID` (ou `_SERVICE`), `_USER`,
  `_PASSWORD`.

Outils : `list_jdd`, `get_jdd`, `find_test_data`, `check_jdd`. Dans `run_robot`, `jdd_env` +
`jdd_jeux` vérifient les prérequis **avant** le run : s'il manque des données, rien n'est
lancé et le bilan dit « bloqué données » (fini le faux échec du compte sans solde). Sinon
chaque jeu arrive dans Robot en dictionnaire `&{JDD_<NOM>}`, à passer à « Initialiser Le
Test ». Le fichier de valeurs résolues est supprimé à la fin du run.

## Cursor qui pilote, interface web qui affiche

Mode recommandé : Cursor est l'agent (via le MCP), l'interface web sert d'écran de contrôle.
Pas besoin de clé API Claude dans ce mode.

1. Lancer l'interface : `python web/app.py` (http://127.0.0.1:8765).
2. Dans la config MCP de Cursor : `WEB_EVENTS_URL=http://127.0.0.1:8765/api/events`
   (déjà dans `cursor_mcp.example.json`).
3. Copier `cursor_rules_automatisation.mdc` dans `.cursor/rules/` du projet de tests : Cursor
   y trouve les conventions et la méthode.
4. Dans Cursor : « Automatise ATTIJARI-200 sur Android avec le jeu VIREMENT_STANDARD (recette). »

Ce que tu vois dans la page pendant que Cursor travaille :
- l'écran du device en direct, la session ouverte par Cursor étant suivie automatiquement ;
- l'élément visé encadré avant chaque tap, saisie ou vérification ;
- chaque action de Cursor dans l'activité (préfixée « Cursor ») ;
- chaque step proposé par Cursor (`propose_step`) dans « Scénario en construction » :
  Cursor attend ton Valider / Corriger, et reçoit ta correction ;
- les locators au fur et à mesure des captures ;
- les runs lancés par Cursor, en direct dans l'onglet Exécuter.

Interface fermée ou injoignable : Cursor continue normalement, les steps passent « sans
validation ». Le même branchement marche avec Claude Desktop.

## Interface web : prise en main

- **État de l'atelier** (pastille en haut à droite) : Appium, devices, navigateur, Xray, Jira,
  base, Cursor — chaque point à régler vient avec sa solution.
- **Connecter** : un clic. Android / iOS / Web, device détecté, app ou URL mémorisée
  (`~/.atelier-automatisation.json`).
- **Construire en 3 étapes** :
  1. *Choisir le test* dans la liste des candidats Xray (filtre JQL modifiable), voir son
     scénario, choisir le jeu de données, puis « Copier la consigne pour Cursor » ou démarrer
     l'agent intégré ;
  2. *Construire* : chaque step se valide avec Entrée, se corrige avec C ou des corrections en
     un clic ; l'activité s'affiche en phrases (détail technique sur demande) ;
  3. *Relire et enregistrer* : fichiers produits, dry run, sous-tâches Jira passées au statut
     choisi (préselection selon la plateforme).
- **Toucher l'écran** pour désigner un élément : locators proposés avec leur robustesse, puis
  Toucher, Saisir, Ajouter aux locators, ou Utiliser dans la correction du step en cours.
- **Locators** : badge robuste / correct / fragile, progression « iOS 7/9 », bouton
  « Compléter sur iOS » (consigne pour Cursor ou agent intégré) qui rejoue les steps validés
  pour relever les clés manquantes.
- **Exécuter** : préréglages enregistrés, options avancées repliées, statuts Jira proposés
  depuis le workflow du projet, jeux de données détectés dans la suite et vérifiés avant le
  lancement.
- **Échecs** : clic sur un test en échec → message, keyword fautif, captures, lien Jira,
  qualification (bug, données, locator, environnement) écrite dans le test run Xray ;
  « Relancer les échecs » met à jour la même exécution.

## Interface web avec agent intégré (optionnel)

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # + variables Xray / Jira / base comme pour le MCP
export ROBOT_PROJECT_DIR=/CHEMIN/attijari-mobile-tests
python web/app.py                   # http://127.0.0.1:8765
```

- **Construire un test** : écran du device en direct (adb / simctl, environ 3 images/s),
  élément visé surligné avant chaque action, scénario Gherkin qui se construit step par
  step avec Valider / Corriger, locators Android et iOS côte à côte, activité de l'agent.
  Toute écriture de fichier dans le projet demande ton accord.
- **Exécuter** : suite, tags, ticket Xray (avec « Vérifier le ticket »), statuts Jira, JDD
  (avec « Vérifier les données »), puis suivi en direct : tests EXECUTING / PASSED / FAILED
  avec heures de début et de fin, keyword en cours, journal Xray et bilan.

`CLAUDE_MODEL` choisit le modèle (défaut `claude-sonnet-5-5`). L'interface n'écoute qu'en
local (127.0.0.1) : ne pas l'exposer sur le réseau.

### Sécurité de l'interface locale

- La page d'accueil pose un jeton de session (cookie HttpOnly, SameSite=Strict), nouveau à chaque
  démarrage : après un redémarrage de l'interface, recharger la page.
- Seuls les hôtes `127.0.0.1:PORT` et `localhost:PORT` sont acceptés ; une requête venant d'un
  autre site (en-tête `Origin` différent) est refusée, WebSocket compris. Pas de CORS.
- Le listener Robot et le MCP (Cursor, Claude Desktop) s'authentifient avec un jeton à part, lu
  dans `ATELIER_JETON_EVENEMENTS` ou, à défaut, dans le fichier `~/.atelier-automatisation.jeton`
  (droits 600) que l'interface écrit au démarrage : rien à configurer sur un même poste.
- Requêtes limitées à 2 Mio (`WEB_TAILLE_MAX`).

## Points d'attention

- **Jetpack Compose** : les `testTag` n'apparaissent comme `resource-id` que si l'app active
  `testTagsAsResourceId = true`. Sinon le MCP se rabat sur `content-desc` / texte / XPath,
  ce qui est plus fragile — demander l'activation aux devs.
- **Promon SHIELD** : une build protégée peut bloquer l'instrumentation ou les captures
  d'écran. Utiliser une build de recette non shieldée pour le relevé des locators.
- **Device partagé** : `run_robot` ferme la session du MCP avant le run pour libérer le device.
- **Sécurité** : lecture / écriture limitées au dossier `ROBOT_PROJECT_DIR`, pas d'écrasement
  sans `overwrite=True`. Ne pas utiliser de vraies données client dans les sessions.
- À ajouter au `.gitignore` du projet : `.mcp_snapshots/` et `results/`.
- JDD : uniquement des données de recette, jamais de vraies données client ; les secrets
  restent dans l'environnement.
