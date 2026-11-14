# Audit de conformité aux cahiers des charges — 2026-11-14

Méthode : chaque exigence des 8 cahiers (Espaces de travail, Test Strategy, Test Design, Automation Studio,
Execution Center, Failure Analysis, Quality Governance, Application Intelligence) confrontée au code réel
(moteur + route + écran), sans se fier aux documents d'écart.
Légende : ✅ conforme · 🟡 partiel · ❌ absent · ⛔ dépend d'un service externe (Jira / Xray réel, IA, Appium).

## Bilan par module
| Module | ✅ | 🟡 | ❌ / ⛔ | Commentaire |
|---|---|---|---|---|
| Espaces de travail | navigation, flux + impact, couverture | graphe, panneau, UX | filtres version / environnement, graphes phase 2 | un seul Knowledge Graph respecté |
| Test Strategy | 01, 07, 08, 14 | 02-06, 09-13 | rôles | export PDF tronqué ; stratégie archivée sans issue |
| Test Design | 08 | 01-05, 07, 09-13 | 06 règles de test, rôles | mode A importe depuis Jira, pas depuis Xray (type, étapes, Gherkin) |
| Automation Studio | 2, 9, 12 | 4-8, 10, 11, 13-19 | rôles | revue sans « Refuser » ; historique sans avant / après |
| Execution Center | 9, 14, 17 | 2, 4-8, 12, 13, 15, 16 | runners distants, device farm, parallélisme | |
| Failure Analysis | contexte, classification | 4-16 | rôles, paramétrage | IA ni masquée ni historisée |
| Quality Governance | — | 4-15 | rôles, synthèse IA | constantes non paramétrées |
| Application Intelligence | 2.1, 17 | 4-16, 19 | extraction / mapping IA, Journey Builder, paramétrage | |

Transverse : aucune authentification ni rôle (tous les cahiers) ; aucun multi-projets dans une même instance.

## Violations des règles transverses — toutes corrigées le 2026-11-14
| # | Constat | Règle | Effort |
|---|---|---|---|
| 1 | Un script non approuvé s'exécute (revue non bloquante dans `centre.verifier`, `/api/run` et campagnes sans contrôle) | validation humaine | S |
| 2 | « Rejouer les échecs » réutilise `output_dir` du run d'origine et écrase ses résultats | pas d'écrasement silencieux | S |
| 3 | État Xray « Synced » alors que des événements ont été ignorés (erreur définitive) | pas de valeur trompeuse | S |
| 4 | Rejet d'une proposition de connaissance non durable : `analyser_jira` la recrée | validation humaine | S/M |
| 5 | « Confiance » affichée en % = constantes codées (1.0 / 0.8 / 0.3) | pas de valeur simulée | S |
| 6 | Analyse IA des échecs : données non masquées, réponse non historisée | masquage, historisation | S |
| 7 | Facteur « anomalies » de la release (`1 - n/5`) sans méthode affichée ; seuils de risque / flaky codés | méthode affichée, paramétrable | S |
| 8 | Stratégie archivée : plus aucune nouvelle version ni restauration possible | versions | S |
| 9 | `valider_critere` / `verifier_environnement` modifient une version publiée | versions immuables | S |
| 10 | `publier_bdd` : erreurs Xray non historisées ; Background, Outline / Examples non publiés | historisation, perte de données | M |
| 11 | Paramètres de gouvernance modifiés sans historique ; un GET de la vue écrit un instantané | historisation | S |
| 12 | Textes d'écran obsolètes (« à venir », « Git lecture seule », « mode A uniquement ») | information exacte | S |

## Écarts fonctionnels majeurs
- Test Design : import réel depuis Xray (`getTests` : type, étapes, préconditions, Gherkin, dossier) — L.
- Application Intelligence : impact depuis une Story / règle / API, scénarios BDD dans le graphe — M ;
  import Jira complet (tickets sans test, historique des instantanés, changements) — M/L ⛔.
- Test Design : règles de test (06), éditeur d'étapes Manual, création de cas, Test Sets — L.
- Test Strategy : score du plan d'automatisation (critères, ROI, complexité) et transmission à Test Design — M/L.
- Quality Governance : couverture fonctionnelle par fonctionnalité / règle / parcours du Knowledge Graph — L.
- Failure Analysis : filtres de l'Inbox, temps de diagnostic / résolution, machine à états New → Closed — M.
- Execution Center : parallélisme, runners distants, réservation de devices, états Blocked / Aborted / Cancelled — L ⛔.
- Rôles et permissions (tous modules) — L.

## Corrections apportées (2026-11-14)
| # | Correction |
|---|---|
| 1 | `centre.controle_revue` : un script entré en revue (Builder, génération BDD) ne s'exécute qu'Approved / Published ; dry-run libre ; dérogation justifiée journalisée (`executions/derogations_revue.jsonl`) ; `ATELIER_REVUE_EXECUTION=avertissement` ; patrimoine jamais entré en revue non bloqué. |
| 2 | Rejeu : nouveau dossier de run, `output.xml` d'origine copié ; retry rattaché à la Test Execution créée par la 1re tentative. |
| 3 | `etat_xray` : Failed / Partial dès qu'un événement est abandonné, erreurs définitives affichées. |
| 4 | `declarations.rejeter` : rejet motivé, mémorisé, jamais reproposé (IA, extraction Jira). |
| 5 | Plus de pourcentage de confiance : base factuelle (observé, déclaré, déduit à valider, référencé non défini). |
| 6 | IA des échecs : JDD et motifs sensibles masqués avant envoi ; contexte envoyé, modèle et réponse historisés (`analyses/ia/`). |
| 7 | Seuils de risque, transitions flaky, poids de santé, plafond d'anomalies de release : paramètres affichés dans les définitions. |
| 8 | Stratégie archivée : toute modification ouvre une nouvelle version. |
| 9 | Validations de critères et vérifications d'environnement : suivi hors du document (`strategie/suivi.json`), version publiée intacte. |
| 10 | Scenario Outline / Examples conservés ; Background inclus dans le test publié ; scénarios non publiés signalés ; erreurs Xray historisées. |
| 11 | Paramètres de gouvernance historisés (avant / après) ; la vue ne s'écrit plus, l'instantané quotidien est pris par le planificateur. |
| 12 | Textes d'écran et docstrings alignés sur le code. |
