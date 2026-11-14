# Test Design — écart entre le cahier des charges et l'existant (2026-11-14)

Principe retenu : **Xray reste le référentiel officiel**. Test Design est une couche de conception
autour de Xray ; la plateforme conserve des métadonnées (revues, baselines, mapping), jamais un
référentiel concurrent. Les appels Xray d'écriture ne sont pas encore vérifiés (docs/XRAY_API.md) :
aucune synchronisation d'écriture n'est donc présentée comme fonctionnelle.

Légende : ✅ existant · 🆕 ajouté par cette livraison · ⏳ restant · ⛔ bloqué (API Xray à vérifier)

| # | Écran | État | Détail |
|---|---|---|---|
| 01 | Vue d'ensemble | 🆕 | KPI réels (exigences, cas Xray, BDD, revues, prêts / automatisés, couverture, état de l'instantané Xray), répartitions par statut / type / priorité / module. |
| 02 | Exigences & import | ✅ + 🆕 | Import d'instantané JSON et synchronisation Jira existants (`/api/patrimoine*`). Ajout : liste des exigences avec tests associés et exigences sans test. ⏳ import Excel / CSV, génération IA de cas depuis une exigence. |
| 03 | Cas de test (Xray) | 🆕 | Liste avec clé, type, module, priorité, exigences, statut Xray, mode manuel / automatisé, statut de revue interne, état de synchronisation (« importé, instantané du … »). Le type Xray choisit l'éditeur (Cucumber → BDD ; Manual → étapes ; Generic → définition technique). ⛔ création / modification dans Xray. ⏳ éditeur d'étapes manuelles. |
| 04 | Scénarios BDD | ✅ | Construction BDD (graphe ↔ `.feature`, branches, contrôles, IA, génération Robot). Lien depuis Test Design. ⏳ Scenario Outline / Examples dans l'éditeur graphique. |
| 05 | Jeux de données | ✅ | `data/jdd/<env>.yaml`, prérequis vérifiés, secrets masqués, association JDD ↔ scénario BDD. Vue en lecture dans Test Design. ⏳ import CSV / JSON, éditeur. |
| 06 | Règles de test | ⏳ | Non commencé (objet métier à créer, lié aux exigences et tests). |
| 07 | Suites de test | ✅ (lecture) | Suites Robot du dépôt et plans Xray de l'instantané. ⏳ organisation par glisser-déposer, Test Sets. |
| 08 | Traçabilité | ✅ | Knowledge Graph (vue Couverture, analyse d'impact, anomalies) avec clés Jira / Xray dans les propriétés. |
| 09 | Réutilisables | ✅ (lecture) | Keywords du socle et nombre d'utilisations (`/api/editeur/reutilisation`). ⏳ préconditions, fragments, templates versionnés. |
| 10 | Revue & validation | 🆕 | Workflow interne Draft → In Review → Changes Requested → Approved → Ready for Automation, séparé du statut Xray ; contrôles (exigence associée, scénario BDD valide, doublons, JDD) ; historique des décisions, réviseur, commentaires. |
| 11 | Baseline & versioning | 🆕 | Baseline immuable (exigences, cas de test, scénarios BDD, suites) ; comparaison entre baselines ou avec l'état courant ; tests impactés par une exigence modifiée. ⏳ restauration locale d'un cas de test. |
| 12 | Xray Mapping & synchronisation | 🆕 + ⛔ | Mapping des objets, des champs (sens, actif, obligatoire, transformation, champs personnalisés) et des statuts (vides par défaut : aucun équivalent supposé). « Tester le mapping » sur l'instantané. Mode A (import) : instantané / Jira. ⛔ modes B (bidirectionnel) et C (publication), gestion des conflits, arborescence du Test Repository. |
| 13 | Paramètres | 🆕 (lecture) | Conventions appliquées (Gherkin français, tags, INITIALISATION, JDD), modèle IA, mapping par défaut. |

Hors périmètre de cette livraison : rôles et droits (pas d'authentification dans l'interface
locale), multi-projets dans une même interface.
