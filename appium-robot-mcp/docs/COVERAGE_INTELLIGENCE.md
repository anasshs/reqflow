# Coverage Intelligence & Functional Reconstruction — réalisation (2026-11-15)

Légende : ✅ fait · ◐ fait avec une limite · ⏳ restant

Aucun second référentiel : exigences = import Jira de la couverture (`couverture_exigences`), tests et exécutions = copie
Xray (`patrimoine_xray`), observations = carte / Discovery et Knowledge Graph (un seul graphe). Le module
`atelier/intelligence/intelligence_couverture.py` ne stocke que des **propositions** (`couverture/<app>_propositions.json`)
et le journal des synchronisations (`couverture/<app>_synchro_ci.jsonl`).

| # | Fonctionnalité | État | Détail |
|---|---|---|---|
| 1 | Qualité documentaire Jira | ✅ | Epic sans Story (Epics des projets lus à l'import), Story sans description / sans critères, trop générique, sans rattachement, non contextualisée, fonctionnalité sans détail, doublons (similarité ≥ 75 %), sorties du périmètre. Criticité, explication, recommandation, action ; Jira jamais modifié. |
| 2 | Reconstruction fonctionnelle | ✅ | Fonctionnalités = parcours du graphe et écrans observés hors parcours ; observations (écrans, champs, boutons, transitions) ; documentée si une exigence la décrit (texte) ou couvre ses écrans (tests liés). |
| 3 | Reconstruction des User Stories | ✅ | Story + critères marqués observé / déduit / proposé par l'IA / à confirmer ; modifier, valider, rejeter (motivé), regrouper ; création Jira après validation et confirmation, rattachée à l'Epic choisi ; observations conservées dans la proposition. |
| 4 | Liens Jira / Xray | ◐ | Score 0-100 expliqué : similarité TF-IDF (Story, description, critères ↔ test, étapes, préconditions), module / composant, libellés / versions, critères retrouvés dans les étapes. Jamais de lien sans validation (relecteur) ; lien natif « Test » (JIRA_LIEN_COUVERTURE) sans doublon ; rejets jamais reproposés ; historique. Limite : pas de re-classement par LLM dans l'atelier (Cursor peut déposer ses propres propositions : `coverage_proposer_lien`). |
| 5 | Tests manquants | ✅ | Couvert / aucun test / à vérifier / tests sans exigence ; « Proposer des scénarios » envoie l'exigence dans Test Design (US à couvrir : cas depuis les critères, revue, validation, publication Xray selon le mapping). Aucun test Xray créé directement. |
| 6 | Tests orphelins | ✅ | Candidats : Story, Feature / Epic, fonctionnalité observée, règle métier ; classement proposé : associer, nouvelle exigence, technique, transversal, conserver (justification obligatoire). |
| 7 | Coverage Intelligence (4 dimensions) | ✅ | Documentaire, traçabilité, exécution (Passed / Failed / Blocked, dernière exécution), automatisation (automatisée, partielle, manuelle seulement, sans test) : distinctes, avec leur définition. |
| 11 | Interface | ✅ / ◐ | Test Strategy › Coverage Intelligence (Overview, Documentation Gaps, Functional Reconstruction, Test Mapping, Missing Tests, Orphan Tests) ; aussi dans Application Intelligence › Apprendre › Reconstruction fonctionnelle. Coverage Graph : vue « couverture » du Knowledge Graph, qui montre désormais aussi les Stories sans test et leurs parents ; les Test Runs ne sont pas des nœuds (statut porté par le test et ses exécutions). |
| 13 | Sécurité | ✅ / ◐ | Création de Story, lien et commentaire : validation puis synchronisation explicite (rôle relecteur), journalisées ; permissions Jira = celles du jeton de l'utilisateur ; propositions distinctes des données officielles ; observations = libellés et locators (Discovery ne saisit rien). Limite : annulation d'une synchronisation à faire dans Jira (pas de suppression automatique). |

Outils MCP (Cursor) : `coverage_intelligence(vue)`, `coverage_proposer_story(...)`, `coverage_proposer_lien(...)` —
propositions uniquement, validées dans l'atelier.

À confirmer sur le vrai Jira / Xray : JQL `issuetype = Epic` (nom du type), sens du lien « Test » (même convention que
Test Design), champ `parent` à la création d'une Story (projets « team-managed » et « company-managed »).
