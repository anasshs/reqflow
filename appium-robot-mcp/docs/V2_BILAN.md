# V2 — Bilan (phase 7 : consolidation)

Date : 2026-11-16. Cahier : `docs/CAHIER_V2.md`. Audit initial : `docs/V2_AUDIT_PHASE0.md`.

## Critères de succès (§15 du cahier) — vérifiés par des tests automatiques

| Critère | Statut | Preuve |
|---|---|---|
| Un parcours de fonctionnalité joué de bout en bout sur la démo, depuis Cursor (MCP) puis depuis le web, interrompu et repris sans perte | ✅ | `tests/test_v2_bout_en_bout.py::test_parcours_complet_depuis_cursor_puis_l_atelier` : **vrai client MCP stdio** (`tests/client_mcp.py`, même commande que Cursor) + API web ; suspension depuis Cursor, refus pendant la suspension, reprise depuis l'atelier, 10 étapes validées, toutes les références conservées, 10 versions |
| 0 outil MCP renommé ou dont la signature / la description casse | ✅ | `tests/test_retrocompatibilite.py` (76 outils historiques figés : noms, paramètres, descriptions) ; `test_outils_et_contrat_mcp` : les 76 sont exposés par le vrai serveur, 88 au total |
| Pour chaque outil d'écriture, un test vérifie qu'il refuse d'agir sans validation côté serveur | ✅ | `tests/test_demandes_mcp.py` (chaque écriture Jira / Xray, fusion d'écrans, remplacement de locator) ; `tests/test_securite_outils.py` (registre : chacun des 88 outils classé, écritures externes par demande, actions device classées, aucun outil git / fusion, aucune décision humaine par MCP) ; `test_cursor_ne_peut_ni_ecrire_dans_jira_ni_valider_une_decision_humaine` par le vrai client |
| Règles Cursor centralisées, versionnées, comparées avant synchronisation | ✅ | `tests/test_regles_cursor.py` (11 règles, versions, comparaison, restauration, synchronisation sans écrasement + `.bak`, migration des anciennes règles) |
| Couverture des parcours et des composants UI calculée avec définition et source | ✅ | `tests/test_couverture_avancee.py` (5 niveaux, définitions, indicateurs avec détail) |
| Champ et Anomalie présents dans le graphe, reliés aux échecs | ✅ | `tests/test_champs_anomalies.py`, `tests/test_echecs_connaissance.py` |
| Tests d'intégration MCP par un client MCP de test | ✅ | `tests/client_mcp.py` ; `tests/test_v2_bout_en_bout.py` ; « Tester le serveur MCP » dans Paramètres |
| L'atelier continue à fonctionner localement ; validations humaines maintenues | ✅ | aucune nouvelle dépendance, aucun service externe ; décisions humaines imposées côté serveur (demandes, étapes « validation / qualification / synchronisation », rôles) |

## Ce que la V2 a livré

| Phase | Livré | Document |
|---|---|---|
| 0 | Audit, matrice EXISTANT / À AMÉLIORER / À CRÉER, 76 outils classés | `V2_AUDIT_PHASE0.md` |
| 0 bis | Validation côté serveur des outils MCP d'écriture (demandes d'action) | `DECISIONS.md` |
| 1 | Parcours de fonctionnalité (web + MCP) | `V2_PHASE1_PARCOURS.md` |
| 2 | 11 règles Cursor versionnées, synchronisation sans écrasement, export, test réel du serveur MCP | `V2_PHASE2_CURSOR.md` |
| 3 | Couverture des parcours et composants UI par niveau | `V2_PHASE3_COUVERTURE.md` |
| 4 | Test Design par catégories, détection des doublons | `V2_PHASE4_TEST_DESIGN.md` |
| 5 | Champ et Anomalie dans le Knowledge Graph | `V2_PHASE5_KNOWLEDGE_GRAPH.md` |
| 6 | Échecs reliés aux écrans, composants, champs, anomalies ; régressions récurrentes | `V2_PHASE6_FAILURE_ANALYSIS.md` |
| 7 | Client MCP de test, scénario de bout en bout, registre de sécurité, bilan | ce document |

Outils MCP : 76 → **88** (12 ajoutés : `parcours_lister`, `parcours_initialiser`, `parcours_etat`, `parcours_etape`,
`parcours_reprendre`, `cursor_regles`, `coverage_ui`, `test_design_proposer`, `test_design_doublons`,
`knowledge_entites`, `knowledge_proposer_champ`, `failure_connaissance`) ; aucun outil existant renommé ni modifié
dans son contrat. Changement de comportement documenté : 6 outils d'écriture passent par une demande à valider.

## Limites connues (assumées, documentées)
- Couverture « vérifiée » mesurable seulement pour les tests automatisés ; tests manuels : association déduite au
  niveau écran.
- Test Design par catégories : règles déterministes ; une US sans critère ni lien dans le graphe ne produit que des
  cas déduits, à confiance faible.
- Localisation d'un échec impossible quand l'étape fautive n'utilise pas de locator du référentiel (initialisation,
  données) : affichée « sans écran », jamais devinée.
- Cursor lui-même n'est pas pilotable par les tests : l'intégration est vérifiée avec un client MCP qui lance le
  serveur exactement comme Cursor.
- Accès réel Jira / Xray non rejoué ici (aucun service réel dans les tests) : à valider sur le poste de l'équipe
  (TAM), en particulier l'exécution des demandes acceptées.
- Un échec intermittent isolé de la suite a été observé une fois en phase 4, non reproduit depuis.

## À faire sur le poste de l'équipe
1. Paramètres › Cursor / Claude : « Synchroniser vers le projet… » (11 règles), puis « Tester le serveur MCP ».
2. Ajouter au `.gitignore` du dépôt de tests l'état de travail de l'atelier (`studio/ executions/ results/ discovery/
   connaissance/ analyses/ couverture/ gouvernance/ testabilite/ validations/ parcours/`) ; versionner
   `atelier_regles/` si l'équipe partage ses règles.
3. Jouer un premier parcours réel sur TAM et accepter une demande Jira de test dans À valider.
