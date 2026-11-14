# Application Intelligence, Failure Analysis, Quality Governance — écart avec les cahiers des charges (2026-11-14)

Légende : ✅ existant réutilisé · 🆕 ajouté · ⏳ restant · ⛔ bloqué (import Jira complet / API Xray non vérifiés)

Principes tenus partout : projet unique hérité du header ; un seul Knowledge Graph ; aucun indicateur, score,
confiance ou recommandation sans données et méthode affichées ; l'IA propose, l'humain valide ; rien n'est
modifié silencieusement (résultats d'exécution, scripts, référentiels).

## Application Intelligence (15 rubriques)
| Écran | État | Détail |
|---|---|---|
| Application Overview | 🆕 | Application, plateformes, build, dates (exploration, instantané Xray / Jira, graphe), compteurs fonctionnels, techniques et de traçabilité. |
| Jira Intelligence | 🆕 / ⛔ | Hiérarchie Epic → Story et tests Xray (traçabilité dans les deux sens) depuis l'instantané. ⛔ descriptions / critères d'acceptation, donc extraction IA des fonctionnalités et règles : import Jira complet requis. |
| Application Map, Functional / Technical Graph, Impact | ✅ + 🆕 | Knowledge Graph central ; nouvelles vues Fonctionnel et Technique (distinctes, connectées). |
| User Journeys | ✅ / ⏳ | Parcours déclarés + vue graphe ; éditeur de parcours dédié à venir (Construction BDD en tient lieu). |
| Screen Explorer | 🆕 | Écrans de la carte : vignettes, composants et locators par plateforme, contexte, transitions, états, tests qui les utilisent. |
| API Intelligence, Business Rules | 🆕 (lecture) / ⏳ | Nœuds déclarés avec provenance ; import OpenAPI / Postman et extraction de règles à venir. |
| Application Exploration | ✅ | Exploration guidée / automatique (liste rouge, aucune saisie) et cartographie par les tests. ⏳ exploration assistée par IA. |
| Change Detection | 🆕 / ⏳ | Écarts entre sources (écrans à revoir, locators obsolètes ou manquants, clés Robot inconnues de Xray). ⏳ versions Jira, Git, API. |
| Knowledge Validation, History | ✅ + 🆕 | File des propositions « à valider » (valider / rejeter, historisé), journal des déclarations. ⏳ versions nommées du graphe, restauration. |

## Failure Analysis (12 rubriques) — `atelier/execution/echecs.py`
| Écran | État | Détail |
|---|---|---|
| Overview, Inbox, Trends | 🆕 | Échecs collectés automatiquement depuis les runs réels ; nouveaux / récurrents / régressions ; répartitions ; synchronisation Xray comptée à part (jamais un échec de test). |
| Investigation, Evidence | 🆕 | Timeline des étapes, étape fautive, locator, écran attendu (carte) / capture réelle, logs, code ; décisions (confirmer avec catégorie, rejeter, inconclusif, faux positif justifié, correction, clore, rouvrir). |
| AI Diagnosis | 🆕 | Hypothèses par règles explicables (preuves, force élevée / moyenne / faible : ce n'est pas une probabilité) ; analyse IA à la demande si ANTHROPIC_API_KEY, sans valeur de JDD. |
| Locator Diagnosis | 🆕 | État du locator (référentiel), valeurs observées pour la même clé dans la carte ; ⏳ test de remplacement et application (Automation Studio, validation). |
| Root Cause | 🆕 | Regroupement par signature (message normalisé), réversible ; tests impactés (même locator / keyword). ⏳ croisement Git / versions. |
| Fix Recommendations | 🆕 / ⏳ | Correction recommandée par catégorie et module cible ; ⏳ propositions de code avant / après générées par IA. |
| Retest & Validation | 🆕 | Relance via la file de l'Execution Center ; avant / après conservés ; clôture impossible sans retest réussi. |
| Jira Defects | 🆕 / ⛔ | Brouillon d'anomalie (étapes, attendu / obtenu, environnement, version, preuves), association à une clé existante ; ⛔ création et recherche de doublons dans Jira. |

## Quality Governance (12 rubriques) — `atelier/intelligence/gouvernance.py`
| Écran | État | Détail |
|---|---|---|
| Overview | 🆕 | 10 KPI (définition, formule, source, date) ; ROI « indisponible » tant que les minutes manuelles ne sont pas paramétrées ; insights par règles. |
| Functional / Automation Coverage | 🆕 | Par exigence (satisfaisante / partielle / insuffisante / indisponible, libellés + couleurs), par module, par plateforme, tests sans exigence. |
| Test Effectiveness | 🆕 / ⛔ | Taux d'échec par test, échecs par module, défauts confirmés, redondances ; ⛔ défauts après livraison (Jira). |
| Automation Health | 🆕 | Score pondéré documenté (locators, conformité de revue, réutilisation), doublons, inutilisés, jamais exécutés, backlog de maintenance. |
| Test Stability | 🆕 | Séquences par test, « potentially flaky » (définition paramétrable), constamment en échec, instables au retry, durées. |
| Application Risk | 🆕 | Score par module avec facteurs et pondérations configurables ; facteur sans donnée exclu. ⏳ par fonctionnalité. |
| Release Readiness | 🆕 | Évaluation historisée (critères pondérés, données disponibles, Ready / Ready with Risks / Not Ready / Insufficient Data), avis QA Manager obligatoire et tracé ; jamais une autorisation automatique. |
| Trends | 🆕 | Instantanés quotidiens des KPI (conservés même si les sources évoluent) et série par run. ⏳ filtres et comparaisons de périodes. |
| Recommendations | 🆕 | Règles explicables, priorité, module cible, responsable, statut Proposed → Completed historisé. |
| Reports | 🆕 | QA Manager, Testing Factory, Automation, Release : PDF (impression) et CSV. ⏳ Excel natif, partage. |
| Settings | 🆕 | Seuils, pondérations risque / release, ROI. |

Restant commun : rôles et permissions (pas d'authentification locale), multi-projets dans une même instance.

## Écarts développés (seconde passe, 2026-11-14)
- 🆕 Failure Analysis : proposition de correction de locator (valeur observée dans la carte), diff avant / après,
  workflow Proposed → Under Review → Approved → Applied (écriture via l'éditeur, contrôle de concurrence, historisée,
  revue technique du script à refaire) → Validated (retest réussi exigé) ; rejet justifié.
- 🆕 Application Intelligence : critères d'acceptation structurés (condition / action / résultat) depuis le champ
  `criteres` ou les puces de la description, règles métier candidates proposées « à valider » avec ticket et extrait ;
  import OpenAPI / Swagger (`api/*.yaml|json` : endpoints, module par tag, stories par `x-jira`) ; versions nommées du
  graphe (immuables), comparaison, restauration avec sauvegarde automatique de l'état courant.
- Restent bloqués par Jira / Xray : import Jira complet (descriptions réelles), création d'anomalies et doublons,
  écriture des tests et résultats dans Xray (voir docs/XRAY_API.md).
