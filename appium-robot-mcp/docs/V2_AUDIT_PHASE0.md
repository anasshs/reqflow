# V2 — Phase 0 : audit de l'existant

Date : 2026-11-15. Base : branche `claude/zip-review-dev-o5q90v` (commit de l'audit). Cahier de référence :
`docs/CAHIER_V2.md`. Méthode : lecture du code (AST de `atelier/adapters/facade.py` pour les outils MCP, routes de
`atelier/adapters/web/app.py`, modèles du graphe), vérification des gardes côté serveur outil par outil.

## 1. Synthèse

| Indicateur | Valeur |
|---|---|
| Outils MCP | **76** à l'audit (88 après la V2, voir V2_BILAN.md) (37 lecture, 7 propositions validées dans l'atelier, 10 actions device, 18 écritures locales, 4 écritures externes Jira / Xray) |
| Routes API web | **329** (studio 32, conception 29, centre 27, discovery 23, graphes 22, strategie 20, carte 19, echecs 16, testabilite 14, …) |
| Tests automatisés | **461** tests dans 55 fichiers, tous verts |
| Types du Knowledge Graph | 33 types de nœuds en 7 catégories, 11 types de relations, 3 provenances (observé / déclaré / déduit) |
| Règles Cursor | 2 fichiers (`cursor_rules_automatisation.mdc`, `cursor_rules_discovery.mdc`), installables depuis Paramètres |
| Écarts de sécurité | **6 outils MCP** écrivent sans validation côté serveur (§8) — à traiter en phase 0 bis |

## 2. Matrice EXISTANT / À AMÉLIORER / À CRÉER

| Exigence V2 | Existant | À améliorer | À créer |
|---|---|---|---|
| §3 Parcours de fonctionnalité | Les 10 étapes existent comme modules séparés (Discovery, reconstruction, couverture, Test Design, revue BDD, génération, qualification 3 runs, exécution, Failure Analysis, synchro Xray + À valider) ; événements temps réel ; journaux par module | — | **Le parcours** : modèle (parcours, étapes, références, statuts, historique), moteur léger, écran web, outils MCP (initialiser, consulter, valider, reprendre) |
| §4.2 Règles Cursor | 2 règles ; installation, état « à jour », sauvegarde `.bak` (Paramètres › Cursor / Claude, `atelier/integrations/agents_ia.py`) | Découper en 11 fichiers avec portée (frontmatter) ; contexte projet | Versionnement (versions, comparaison, activation, restauration), comparaison avant synchronisation |
| §4.4 Configuration MCP | Configuration exportée sans secret ni chemin de projet ; installation dans Cursor ; dernière activité MCP affichée | Vérification de connexion explicite (appel de test) | — |
| §5 Test Design | US à couvrir (analyse, questions, cas proposés, publication Xray), règles de test et cas limites, BDD, revue interne, reconstruction fonctionnelle (Coverage Intelligence) avec source et confiance | Catégories de scénarios (alternatifs, permissions, navigation, validation de champs) ; faits / hypothèses explicites dans chaque proposition | Détection de doublons sur étapes / préconditions / résultats attendus (en étendant le moteur de similarité de Coverage Intelligence) |
| §6 Coverage | Couverture des exigences (4 indicateurs, critères d'acceptation, instantanés), Coverage Intelligence (documentaire, traçabilité, exécution, automatisation), couverture des écrans par les tests (`list_screens`) | Niveaux « associé / vérifié / automatisé / exécuté avec succès » | Couverture des **parcours** et des **composants UI** avec définitions ; indicateurs au tableau de bord |
| §7 Knowledge Graph | Types `composant`, `regle`, `bug` ; provenance, confiance, statut de validation, historique et versions du graphe | `composant` de type champ (attributs de champ) ; `bug` enrichi en Anomalie | Relations champ ↔ règle, test vérifie champ, anomalie ↔ écran / exécution |
| §8 Failure Analysis | Classification (12 catégories), étape fautive, preuves, comparaison au run précédent, regroupement par signature, anomalies Jira (doublons, création confirmée), retests | Lier l'échec à l'écran et au composant du graphe ; historiser les causes par composant | Détection de régressions récurrentes par composant / fonctionnalité |
| §9 MCP | Serveur unique, 76 outils, préfixes partiels (`studio_`, `discovery_`, `coverage_`, `map_`, `xray_`, `jira_`), activité journalisée (masquage des secrets), pause / arrêt | Documentation par domaine ; réponses et erreurs normalisées | Outils du parcours, des règles, de la couverture avancée, de Champ / Anomalie |
| §10 Interface web | 8 onglets (Dashboard, Discovery, Application Intelligence, Test Design, Automation Studio, Execution Center, Failure Analysis, Quality Governance) + Paramètres ; projet global dans le header | — | Onglet **Parcours** ; versionnement des règles dans Paramètres › Cursor / Claude |
| §11 Sécurité | Invariants testés (exploration, SELECT, safe_path, Xray non bloquant, 3 runs + revue, actions sensibles en Discovery) ; rôles (lecteur < automaticien < relecteur < responsable) ; revues ; propositions ; MR sans fusion | **6 outils MCP sans garde côté serveur** (§8) | Mécanisme commun « demande d'action en attente de validation » |
| §12 Contraintes | FastAPI, JS, fichiers par projet, local 127.0.0.1 | — | — |

## 3. Modules et moteurs

`atelier/discovery` (carte, sessions, exploration, apprentissage, classement, comportements, corrélation, connaissance,
intelligence_app) · `atelier/intelligence` (cerveau, couverture, couverture_exigences, intelligence_couverture,
patrimoine_xray, testabilite_us, gouvernance, plan_test, strategie = référentiel de pilotage, fournisseur_ia) ·
`atelier/generation` (bdd, conception, regles_test, parcours_bdd, studio, studio_avance, sessions_agent, editeur,
locators, rangement, cycle_vie) · `atelier/execution` (centre, robot, historique, echecs, journal_xray, jdd, flux,
suivi, listeners) · `atelier/domain` (graphe, projet, projets, roles, coffre, evenements, activite_agent,
declarations) · `atelier/integrations` (jira, xray, gitlab, appium, playwright, oracle, http, agents_ia).

## 4. Modèle de données (stockage par projet, dans le projet de tests)

| Dossier | Contenu | Versionné dans Git ? |
|---|---|---|
| `tests/`, `resources/`, `data/jdd/`, `bdd/`, `api/` | patrimoine de tests (suites, socle, JDD, scénarios BDD, contrats) | oui |
| `app_map/` | carte de l'application (écrans, éléments, transitions, vignettes) | à décider (partagée) |
| `patrimoine/` | instantané Xray importé | non conseillé |
| `strategie/` | référentiel de pilotage (périmètre, environnements, objectifs, critères, plan) + journal | à décider |
| `conception/`, `testabilite/` | revues de conception, US à couvrir, règles, baselines | à décider |
| `studio/`, `executions/`, `results/`, `discovery/`, `connaissance/`, `analyses/`, `couverture/`, `gouvernance/` | état de travail de l'atelier (revues, runs, sessions, graphe calculé, instantanés) | non (.gitignore conseillé, signalé par Git du Studio) |

Isolation : un projet = un dossier ; le sélecteur du header change de projet pour tous les modules (`projets.py`).

## 5. Knowledge Graph

Nœuds (`atelier/domain/graphe.py`) : APPLICATION (application, plateforme, environnement, version) ; FONCTIONNEL
(module, fonctionnalite, parcours, ecran, action, regle, role) ; TECHNIQUE (composant, locator, keyword, endpoint,
entite, resource, bibliotheque) ; JIRA (epic, user_story, bug) ; XRAY (test, test_plan, test_set, test_execution) ;
BDD (feature, scenario, step) ; AUTOMATION (suite, test_robot, jdd, requete, resultat).
Relations : contient, navigue_vers, depend_de, appelle, verifie, couvre, implemente_par, teste_par, execute_par,
impacte, utilise. Chaque nœud : provenance, source, confiance, statut (validé / à valider / rejeté), historique ;
versions du graphe. Sources : carte, dépôt Robot, JDD, patrimoine Xray, couverture des exigences, déclarations,
apprentissages Discovery / Cursor.

## 6. Règles Cursor et intégration

- `cursor_rules_automatisation.mdc` : lire le cerveau d'abord, outils du Studio, pause / arrêt, dry run avant revue.
- `cursor_rules_discovery.mdc` : exploration, propositions `discovery_proposer`, règles de nommage.
- Installation et mise à jour : Paramètres › Cursor / Claude (MCP Cursor et Claude Desktop, règles du projet,
  sauvegarde `.bak`, aucun secret ni chemin de projet).
- Le contexte projet vient de l'atelier : le MCP utilise le projet et l'application actifs.

## 7. Mécanismes de validation existants (côté serveur)

Rôles et quatre yeux (`roles.exiger`) · revue technique des scripts (Generated → Technical Review → Approved →
Published, run réussi ou dérogation) · propositions Discovery / Cursor / graphe / Coverage Intelligence (boîte
À valider) · revue interne de conception · workflow des corrections de locators (Proposed → … → Validated, retest) ·
qualification 3 runs · Git : commit sur branche non protégée, suites approuvées ; MR seulement, jamais de fusion ·
Coverage Intelligence : synchronisation Jira après validation · outbox Xray idempotente · actions device classées
pendant une session Discovery.

## 8. Écarts de sécurité (§11 du cahier) — phase 0 bis (corrigés le 2026-11-15, voir DECISIONS)

| Outil | Constat | Correction proposée (nom et signature conservés) |
|---|---|---|
| `jira_transition` | change le statut d'un ticket Jira, aucune validation | crée une **demande d'action** en attente ; exécutée après validation dans l'atelier (ou exécution directe seulement si une validation préalable existe pour ce ticket et cette transition) |
| `import_results_to_xray` | importe un output.xml dans Xray, aucune validation | idem : demande d'action, aperçu (tests, statuts, exécution cible), exécution après validation ; idempotence conservée |
| `qualify_failure` | écrit un commentaire de test run Xray | qualification enregistrée dans Failure Analysis (proposition) ; envoi Xray après validation |
| `run_robot` (`jira_transition_start/_end/_end_if_fail`) | transitions Jira pendant le run, sans validation | transitions préparées comme demandes, ou autorisées seulement si la campagne les a validées ; envoi des résultats Xray inchangé (but du run, idempotent) |
| `name_screen`, `add_screen_locator` | renommage / fusion d'écrans et remplacement de locator directement dans la carte | renommage d'un écran sans nom : direct (observé) ; **fusion** et remplacement : proposition à valider |
| `tap`, `type_text` hors session Discovery | aucune liste rouge ni contrôle d'action sensible | appliquer la liste rouge et le classement des actions en permanence (invariant 6) ; actions sensibles seulement sur environnement autorisé |

Migration : comportement documenté dans `docs/DECISIONS.md` et dans la description des outils (sans changer leur
nom) ; règle `security.mdc` mise à jour ; un test par outil vérifie le refus sans validation.

## 9. Tests de non-régression

461 tests (`pytest -q`, ~1 min 45) ; aucun appel réel (Jira, Xray, GitLab, Oracle, Appium, IA simulés) ; tests
web Playwright sur pages locales ; tests MCP : nombre d'outils (76), noms. À ajouter en V2 : tests de refus des
outils d'écriture, tests d'intégration MCP par client stdio, tests du parcours.

## 10. Liste des 76 outils MCP

Nature : **L** lecture · **P** proposition validée dans l'atelier · **A** action sur le device / navigateur ·
**É** écriture locale (projet, carte) · **X** écriture externe (Jira / Xray).

### Session (Appium / navigateur) (14)

| Outil | Nature | Garde côté serveur | Rôle |
|---|---|---|---|
| `list_devices` | L | lecture | Liste les devices Android (adb) et iOS (simulateurs démarrés + devices physiques) connectés. |
| `start_session` | A | — | Ouvre une session : 'android' / 'ios' (Appium) ou 'web' (navigateur Playwright, mêmes |
| `stop_session` | A | — | Ferme la session courante (mobile ou web). |
| `screenshot` | L | lecture | Capture d'écran du device ou de la page web (pour vérifier visuellement l'écran courant). |
| `get_screen_elements` | L | lecture | Liste les éléments significatifs de l'écran avec des locators AppiumLibrary |
| `element_at` | L | lecture | Élément situé à un point de l'écran (coordonnées en proportion 0-1 de la largeur et de la |
| `open_url` | A | aucune garde de domaine | Web uniquement : ouvre une URL dans la session navigateur. |
| `get_page_source` | L | lecture | Arbre brut de l'écran (XML mobile ou HTML web, tronqué), si get_screen_elements ne suffit pas. |
| `check_locator` | L | lecture | Vérifie un locator : nombre d'éléments trouvés + texte/visibilité du premier. |
| `tap` | A | ⚠ classée et autorisée pendant une session Discovery ; **aucun contrôle hors session** (liste rouge, actions sensibles) | Touche / clique un élément. Mobile : locator AppiumLibrary (id=..., accessibility_id=..., |
| `type_text` | A | ⚠ idem `tap` : saisie libre hors session Discovery | Saisit du texte dans un champ (mobile ou web). |
| `swipe` | A | — | Swipe plein écran (mobile) ou défilement (web). direction : up (vers le bas du contenu), |
| `press_back` | A | — | Retour : bouton retour Android, page précédente en web. Sur iOS, toucher le bouton de navigation. |
| `wait_for` | L | lecture | Attend qu'un élément soit présent à l'écran. |

### Carte et locators (17)

| Outil | Nature | Garde côté serveur | Rôle |
|---|---|---|---|
| `capture_screen_locators` | É | écrit les captures de l'écran | Enregistre les locators de l'écran courant pour la plateforme de la session |
| `generate_locators_resource` | É | ✅ pas d'écrasement sans overwrite | Fusionne les captures d'un écran en un fichier .resource Robot. |
| `add_screen_locator` | É | ⚠ remplace une clé de locator capturée sans validation | Ajoute ou remplace une clé dans les locators capturés d'un écran (plateforme de la session |
| `map_apps` | L | lecture | Applications cartographiées et application active. |
| `map_create_app` | É | change l'application active | Déclare une nouvelle application à cartographier (devient l'application active). |
| `map_select_app` | É | change l'application active (contexte partagé avec le web) | Change d'application active (slug, voir map_apps). |
| `map_set_build` | É | met à jour le build de la carte | Indique le build testé : les écrans revisités sont comparés à leur version précédente. |
| `where_am_i` | É | crée l'écran s'il est inconnu (observé) | Écran courant d'après la carte (créé s'il est inconnu), avec ses éléments et locators connus. |
| `list_screens` | L | lecture | Écrans de la carte (nom, titre, module, plateformes, couverture par les tests). |
| `screen_info` | L | lecture | Détail d'un écran (par nom, alias ou id) : éléments, locators par plateforme, transitions. |
| `name_screen` | É | ⚠ modifie la carte directement (renommage, **fusion d'écrans**) sans validation | Donne un nom métier à un écran (ex. virement_saisie). Un nom déjà utilisé fusionne les deux |
| `goto_screen` | A | rejoue un chemin connu de la carte | Va sur un écran connu en rejouant le chemin le plus fiable de la carte (avec rattrapage). |
| `explore` | A | ✅ liste rouge, aucune saisie, liens externes ignorés (invariant 1) | Explore automatiquement l'application depuis l'écran courant (hors liste rouge, sans saisie). |
| `stop_exploration` | A | — | Demande l'arrêt de l'exploration en cours. |
| `map_import_existing` | É | amorce la carte | Amorce la carte avec les locators des fichiers .resource existants du projet. |
| `map_tags_report` | L | lecture | Éléments sans identifiant de test (Compose sans testTag, SwiftUI sans identifier, web sans |
| `export_screen_resource` | É | écrit un .resource dans le projet | Génère le .resource d'un écran depuis la carte (locator principal + secours par plateforme). |

### Discovery (6)

| Outil | Nature | Garde côté serveur | Rôle |
|---|---|---|---|
| `propose_step` | P | ✅ proposition, validée dans l'atelier (À valider / revue) | Propose un step Gherkin construit à partir de l'action faite sur le device. |
| `discovery_demarrer` | É | session avec environnement et périmètre | Démarre une session Discovery sur l'application de la carte et la plateforme de la session ouverte |
| `discovery_ecran_courant` | L | lecture | Écran courant pour explorer : écran de la carte (nouveau ou non, noms déjà proposés), éléments avec leur classe |
| `discovery_proposer` | P | ✅ proposition, validée dans l'atelier (À valider / revue) | Dépose ce que tu as compris dans le Knowledge Graph, comme proposition à valider par l'automaticien. |
| `discovery_parcours_vers_bdd` | P | ✅ proposition, validée dans l'atelier (À valider / revue) | Crée dans Test Design un brouillon de scénario BDD depuis la carte : soit une suite ordonnée d'écrans |
| `discovery_terminer` | É | clôt la session | Termine la session Discovery en cours : résultats (nouveaux écrans, transitions, comportements, endpoints, |

### Knowledge Graph et cerveau (7)

| Outil | Nature | Garde côté serveur | Rôle |
|---|---|---|---|
| `knowledge_graph` | L | lecture | Graphe de connaissance de l'application (carte, dépôt Robot, JDD, patrimoine Xray, déclarations). |
| `impact_analysis` | L | lecture | Analyse d'impact d'une modification (locator, keyword, resource, écran, JDD…) : tests Robot et Xray, |
| `coverage_report` | L | lecture | Couverture du patrimoine Xray (instantané patrimoine/xray.json) : tests automatisés / manuels par module, |
| `automation_flow` | L | lecture | Construction technique d'un test automatisé : scénario Xray -> test Robot -> keywords -> locators, |
| `plan_de_test` | L | lecture | Résumé d'un module pour dresser son plan de test (au lieu du graphe brut) : écrans (et locators fragiles), |
| `cerveau_application` | L | lecture | Ce que l'atelier sait de l'application active, à lire AVANT de construire ou d'explorer : sans module, vue |
| `cerveau_question` | L | lecture | Pose une question au cerveau de l'application (ex. « quels écrans du module Virements n'ont pas de test ? »). |

### Coverage Intelligence (3)

| Outil | Nature | Garde côté serveur | Rôle |
|---|---|---|---|
| `coverage_intelligence` | L | lecture | Coverage Intelligence de l'application active. vue : « overview » (4 dimensions : documentaire, traçabilité, |
| `coverage_proposer_story` | P | ✅ proposition, validée dans l'atelier (À valider / revue) | Dépose une proposition de User Story reconstruite (id de fonctionnalité donné par coverage_intelligence("reconstruction" |
| `coverage_proposer_lien` | P | ✅ proposition, validée dans l'atelier (À valider / revue) | Dépose une proposition de lien exigence ↔ test Xray (score 0-100, raisons). Jamais créé dans Jira / Xray sans |

### Test Design (testabilité des US) (2)

| Outil | Nature | Garde côté serveur | Rôle |
|---|---|---|---|
| `testabilite_us_a_traiter` | L | lecture | Testabilité des US : User Stories à analyser (texte masqué, réponses de l'équipe). Lire chaque US, repérer les |
| `testabilite_deposer_proposition` | P | ✅ proposition, validée dans l'atelier (À valider / revue) | Dépose l'analyse de l'agent pour une US. constats : [{"gravite": "haute/moyenne/basse", "message", "extrait", |

### Automation Studio (11)

| Outil | Nature | Garde côté serveur | Rôle |
|---|---|---|---|
| `studio_socle` | L | lecture | Ce qu'il faut réutiliser avant d'écrire un test : keywords du socle (nom, documentation, fichier, utilisations, |
| `studio_scenario_bdd` | L | lecture | Scénario BDD d'un test Xray (Test Design) et son mapping vers le socle : pour chaque étape, keyword existant ou |
| `studio_generer_depuis_bdd` | É | ✅ aperçu par défaut ; écriture sans écrasement, entrée en revue | Génère la suite Robot d'un scénario BDD (keywords du socle, stubs pour les étapes à créer). ecrire=False : |
| `studio_construire_test` | É | ✅ idem | Assemble un test Robot depuis les keywords EXISTANTS du socle (INITIALISATION + JDD ajoutés). etapes : |
| `studio_executer_etape` | É | suite temporaire via la file ; pas d'écriture du dépôt | Exécute un seul keyword du socle (INITIALISATION + jeu de données, puis ce keyword) dans une suite temporaire |
| `studio_revue` | L | lecture | État de la revue technique des scripts. Sans fichier : liste (statut, dernière décision et commentaire). |
| `studio_soumettre_revue` | P | ✅ proposition, validée dans l'atelier (À valider / revue) | Soumet un script à la revue technique de l'automaticien (Généré / Modifications demandées / Refusé → Revue |
| `studio_corrections_locators` | L | lecture | Locators à fiabiliser (fragiles, obsolètes, ou dont un secours a servi dans les derniers runs) avec la valeur |
| `studio_corriger_locator` | É | ✅ historique de l'éditeur ; suites impactées renvoyées en revue | Applique une correction de locator (ex. valeur proposée par studio_corrections_locators) dans son fichier |
| `studio_factorisation_keywords` | L | lecture | Groupes de keywords en double (corps identique, ou même nom dans plusieurs fichiers) avec le keyword à garder |
| `studio_factoriser_keywords` | É | ✅ idem ; seuls les groupes « applicable » | Factorise un groupe de keywords au corps identique (id renvoyé par studio_factorisation_keywords) : appels |

### Dépôt de tests (Git local) (3)

| Outil | Nature | Garde côté serveur | Rôle |
|---|---|---|---|
| `list_project_files` | L | lecture | Liste les fichiers du projet de tests (ex. '**/*.resource', 'tests/**/*.robot'). |
| `read_project_file` | L | lecture | Lit un fichier du projet (keywords existants, steps, suites) pour réutiliser le socle. |
| `write_project_file` | É | ✅ safe_path, pas d'écrasement implicite ; une suite écrite repasse en revue technique | Écrit un fichier dans le projet (nouvelle suite, steps…). Refuse d'écraser sans overwrite=True. |

### Exécution et données (6)

| Outil | Nature | Garde côté serveur | Rôle |
|---|---|---|---|
| `parse_robot_output` | L | lecture | Résumé d'un output.xml : stats + tests en échec avec message et keyword fautif. |
| `run_robot` | X | ⚠ écrit les résultats dans Xray (but du run, idempotent) ; paramètres `jira_transition_*` : **transitions Jira sans validation** | Lance une suite ou un dossier Robot Framework du projet puis renvoie le bilan. |
| `list_jdd` | L | lecture | Liste les jeux de données d'un environnement (sans env : liste des environnements). |
| `get_jdd` | L | lecture | Détail d'un jeu de données (secrets affichés sous forme {{env:VARIABLE}}, jamais en clair). |
| `find_test_data` | L | lecture | Cherche des données éligibles via une requête de la liste blanche (requetes.yaml), |
| `check_jdd` | L | lecture | Vérifie les prérequis de données AVANT un run. Un jeu bloqué = test « bloqué données », |

### Jira / Xray (7)

| Outil | Nature | Garde côté serveur | Rôle |
|---|---|---|---|
| `xray_get_test` | L | lecture | Lit un test Xray : type, scénario Gherkin (Cucumber) ou étapes manuelles, libellés. |
| `xray_search_tests` | L | lecture | Cherche des tests Xray par JQL, ex. les candidats à l'automatisation d'un projet. |
| `jira_subtasks` | L | lecture | Sous-tâches d'un ticket (ex. ST1 Locators Android… ST5 Branchement) avec leur statut. |
| `qualify_failure` | X | ❌ **écrit un commentaire de test run Xray sans validation** | Qualifie un échec dans le test run Xray : bug, données, locator ou environnement. |
| `xray_inspect_ticket` | L | lecture | Indique ce que deviendra un run sur ce ticket : Test Plan (nouvelle exécution ajoutée), |
| `jira_transition` | X | ❌ **change le statut d'un ticket Jira sans validation** | Fait passer un ticket Jira dans un statut (nom de transition ou de statut cible). |
| `import_results_to_xray` | X | ❌ **écrit dans Xray sans validation côté serveur** | Envoie un output.xml Robot dans Xray Cloud (import/execution/robot), en secours |