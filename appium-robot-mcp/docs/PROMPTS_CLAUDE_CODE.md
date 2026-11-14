# Consignes à donner à Claude Code, phase par phase

Une phase = une session. Ouvrir Claude Code à la racine du dépôt, coller la consigne, relire le
plan qu'il propose AVANT de le laisser coder, puis relire le diff et lancer `pytest -q` soi-même.

## Démarrage (une seule fois)
```
Lis CLAUDE.md, README.md et docs/ROADMAP.md, puis parcours le code. Ne modifie rien.
Rends-moi : (1) ta compréhension de l'architecture actuelle en 10 lignes, (2) les risques que tu
vois pour la phase 1, (3) les questions bloquantes. Crée ensuite tests/ avec des tests de
caractérisation du comportement actuel (outils MCP listés, parsing Android / Compose / iOS,
carte sur un site web local Playwright, résolution JDD avec base simulée) pour sécuriser le
refactoring. Montre-moi le plan avant d'écrire.
```

## Phase 1 — Fondations
```
Réalise la phase 1 de docs/ROADMAP.md, dans l'ordre 1.1 → 1.4, une sous-phase à la fois.
Avant 1.1, ajoute un test qui fige la liste des outils MCP (noms + paramètres) pour prouver la
rétrocompatibilité. Pour 1.4, vérifie chaque appel Xray sur la documentation officielle ; si tu
ne peux pas y accéder, liste précisément ce qui reste à vérifier dans docs/XRAY_API.md au lieu
de supposer. Coche la roadmap, consigne tes décisions dans docs/DECISIONS.md, commits en français.
```

## Phase 2 — Assertions
```
Réalise la phase 2 de docs/ROADMAP.md. Commence par le modèle d'assertion et ses tests, puis la
classification des steps « Alors », puis les keywords du socle, puis l'outil MCP et la validation
dans l'interface. Aucun test généré ne doit pouvoir être produit sans assertion métier.
```

## Phase 3 — Test Intelligence Engine
```
Réalise la phase 3. Crée d'abord un jeu de données Xray fictif de 50 tests (tests/fixtures/xray/).
Chaque critère doit avoir une valeur, une source et un statut de disponibilité ; une donnée
absente reste absente, elle n'est jamais estimée sans le dire. Le score est configurable et chaque
recommandation est expliquée. Ajoute l'onglet « Patrimoine » à l'interface.
```

## Phase 4 — Carte robuste
```
Réalise la phase 4. Écris d'abord les jeux de hiérarchies fictives (variantes du même écran,
écrans proches mais différents), puis la reconnaissance pondérée avec score de confiance, puis le
modèle écran fonctionnel → implémentations, puis le script de migration de app_map/.
Zéro faux positif sur les cas « différents ».
```

## Phase 5 — Knowledge Graph niveau 1
```
Réalise la phase 5. Toute relation porte sa provenance (observé, déclaré, déduit), sa source, sa
date et son statut. Un lien déduit non validé n'est jamais utilisé pour une décision. Alimentation
automatique depuis Xray (simulé), le dépôt Robot et la cartographie TNR. Vue arborescente et outils
MCP feature_info, coverage_report, screen_info enrichi.
```

## Phase 6 — API
```
Réalise la phase 6 avec une spec OpenAPI fictive « bénéficiaires » et un faux serveur local.
Mêmes conventions que les tests mobiles (INITIALISATION + JDD, tags Xray, assertions). Exécution
et remontée Xray par le moteur d'exécution existant (journal + reprise).
```

## Phase 7 — Maintenance et autonomie
```
Réalise la phase 7. Six catégories d'échec avec preuves conservées, actions par catégorie,
3 exécutions stables avant toute proposition de MR, contrôles robocop et conventions, trois modes
d'autonomie conditionnés par des indicateurs et activés par un humain. Jamais de modification
silencieuse ni de commit direct sur la branche principale.
```

## À chaque fin de phase (vous, pas Claude Code)
- Relire le diff complet et `docs/DECISIONS.md`.
- Lancer `pytest -q`, puis un essai manuel : Cursor + interface web sur une app de recette.
- Ne passer à la phase suivante qu'une fois la phase validée.
