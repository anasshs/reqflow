# Automation Studio et Execution Center — écart avec les cahiers des charges (2026-11-14)

Légende : ✅ existant réutilisé · 🆕 ajouté · ⏳ restant · ⛔ bloqué (API Xray non vérifiée, docs/XRAY_API.md)

## Contexte projet global (commun aux deux cahiers)
- ✅ Projet actif unique dans le header (ROBOT_PROJECT_DIR) ; 🆕 aucun module n'a de second sélecteur ; navigation
  réordonnée : Dashboard · Application Intelligence · Test Strategy · Test Design · Automation Studio · Execution Center.
- 🆕 Contexte d'exécution figé à l'entrée dans la file (projet, application, version, environnement, plateforme, commit
  Git du projet, statut de revue des scripts) et conservé dans l'historique.
- ⏳ Plusieurs projets dans une même instance, droits et rôles (pas d'authentification dans l'interface locale).

## Automation Studio
| # | Écran | État | Détail |
|---|---|---|---|
| 1 | Overview | 🆕 | KPI réels (BDD, candidats, tests automatisés, scripts en revue / approuvés, locators à corriger, keywords, couverture, dernière génération / exécution), répartitions. ⏳ courbes dans le temps. |
| 2 | Automation Candidates | 🆕 + ✅ | Candidats de Test Strategy avec plateforme, criticité, plans, critères et manques. Score : « non calculé » (aucune valeur inventée) tant que répétitivité / stabilité / complexité ne sont pas mesurées. |
| 3 | Automation Projects | 🆕 | Espaces techniques du projet (application, plateformes, framework, répertoire, dépôt, convention). |
| 4 | BDD to Automation | 🆕 | Mapping étape → keyword du socle (existant / à créer), locators et leur état, données `${DONNEES.x}`, assertion ; prévisualisation Robot. Édition du mapping et propositions IA : Construction BDD (✅). |
| 5 | Automation Builder | ✅ / ⏳ | Construction BDD tient lieu de constructeur visuel ; ⏳ palette d'actions techniques, contrôle If / For / Try, exécution d'une étape isolée. |
| 6 | Application Knowledge | ✅ | Knowledge Graph central (pas de second graphe), impact, anomalies. |
| 7 | Locators Repository | 🆕 | Fiabilité (Stable / Reliable / Fragile), Obsolete (écran cartographié sans la valeur), Missing (référencé non défini), secours, utilisations, test sur session journalisé. ⏳ enregistrement du secours réellement utilisé à l'exécution, correction assistée (phase 7). |
| 8 | Keywords Repository | 🆕 | Catégorie, plateformes, locators, données, utilisations, doublons, inutilisés, wrappers 1:1. ⏳ factorisation IA. |
| 9 | Page Objects | 🆕 | Clés métier par écran et par plateforme, incohérences Android / iOS / Web. |
| 10 | Test Data & Configuration | ✅ | JDD YAML, Oracle en SELECT liste blanche, secrets {{env:}}, fichier résolu supprimé après le run. ⏳ CSV / JSON / API. |
| 11 | Framework Management | 🆕 | Versions réellement installées et prérequis (node, adb, xcrun, appium). |
| 12 | Code Editor | ✅ | Éditeur existant (historique, diff, lint, robocop) ; l'IA ne modifie jamais un fichier sans validation. |
| 13 | Git Repository | 🆕 (lecture) | Branche, commits, modifications locales. ⏳ branche, commit, push, MR (phase 7, jamais vers la branche principale). |
| 14 | Automation Review | 🆕 | Generated → Technical Review → Changes Requested → Approved → Published ; contrôles (clé Xray, conventions, secrets, assertions, réutilisation, locators, données) ; un script modifié après validation revient en revue (empreinte). |
| 15 | Automation History | 🆕 | Journal des revues, vérifications de locators, espaces. |
| 16 | Settings | 🆕 (lecture) | Conventions, IA, Git, Xray ; connexions communes dans les Paramètres globaux. |

## Execution Center
| # | Écran | État | Détail |
|---|---|---|---|
| 1 | Overview | 🆕 | Exécutions, en cours, en file, réussis, échoués, taux, durée moyenne, instables, runner ; par plateforme / statut ; activité. Bloqués / ignorés non distingués aujourd'hui. |
| 2 | Test Campaigns | 🆕 | Création, modification, duplication, exécution (un job par plateforme), dry run, archivage, comparaison des deux derniers runs, dernière exécution et taux de réussite réels. ⏳ planification. |
| 3 | Test Selection | 🆕 | Filtres (module, plateforme, criticité, dernier résultat, revue, plan), sélection des échecs, contrôle préalable par test (script, revue, plateforme, framework, données, environnement), lancement des seuls tests exécutables. ⏳ sélection par JQL / Test Set. |
| 4 | Run Configuration | 🆕 | Cible, tags, plateforme, environnement, device, priorité, ticket Xray, variables (sensibles refusées), retry, dry run. |
| 5 | Execution Queue | 🆕 | File à priorités (Critical > High > Normal > Low), annulation d'un job en attente, mise à jour temps réel. Capacité 1 (runner local). |
| 6 | Live Monitoring | ✅ | Écran Exécution (WebSocket, étapes, logs, captures, arrêt contrôlé, rejouer les échecs). |
| 7 | Device Farm | ✅ (inventaire) | adb / simctl réels. ⏳ réservation, historique, endpoints Appium distants. |
| 8 | Runners Management | 🆕 | Runner local réel (OS, bibliothèques, plateformes possibles, charge). ⏳ runners distants (serveur, GitLab, Kubernetes, macOS). |
| 9 | Execution Results | ✅ + 🆕 | Résultats détaillés (écran Exécution) ; comparaison de deux runs. ⏳ qualification (Failure Analysis). |
| 10 | Evidence Repository | 🆕 | Fichiers du run (captures prévisualisées, output.xml, log, rapport, journal Xray, tentatives). ⏳ vidéos, traces réseau, politique de conservation. |
| 11 | Execution History | 🆕 | Contexte figé, campagne, tentatives et tests instables, export CSV. |
| 12 | Xray Synchronization | ✅ + 🆕 | Journal local (outbox) idempotent, jamais bloquant ; état Synced / Pending / Partial par run. ⛔ création / association réelles tant que l'API n'est pas vérifiée. |
| 13 | Settings | 🆕 (lecture) | Parallélisme, priorités, retry, preuves, Xray. ⏳ notifications, planification. |

Retry : seconde tentative des seuls échecs, preuves de chaque tentative conservées (`tentative-1/`, `tentative-2/`),
résultats fusionnés par `rebot --merge`, tests passés au second essai déclarés instables ; un premier échec n'est
jamais transformé silencieusement en réussite.

## Écarts développés (seconde passe, 2026-11-14)
- 🆕 Execution Center : planification interne (quotidienne, hebdomadaire, intervalle ≥ 15 min ; un seul déclenchement par
  échéance), webhook CI/CD `POST /api/externe/campagnes/<id>/executer` (jeton de processus), exclusion temporaire de tests
  par tag (le test reste au référentiel).
- 🆕 Automation Studio : Builder (palette des keywords du socle, étapes Gherkin ordonnées, INITIALISATION + JDD
  automatiques, lint, écriture sans écrasement, entrée en revue « Generated ») ; Git local encadré (branche de travail,
  commit des seules suites approuvées / publiées, refus sur main / master / develop / production, aucun push).
- Restent : runners distants, réservation de devices, notifications, merge request (API GitLab), blocs If / For / Try.
