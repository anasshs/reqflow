# Dashboard de pilotage — état et écarts avec le cahier

État au 2026-11-18. Moteur : `atelier/intelligence/pilotage.py`. Écran : `ecran_pilotage.js` (#dashboard). Tests :
`tests/test_pilotage.py`. L'ancien Dashboard (runs, tendance, devices) reste accessible : « Suivi des runs » (#operations).

Légende : ✅ fait · 🟡 partiel (donnée limitée, dite à l'écran) · ⛔ non mesuré (donnée absente des copies locales)

| § | Sujet | État | Détail |
|---|---|---|---|
| 2 | Quatre zones + filtres | 🟡 | Filtres : sprint, module, version, plateforme, responsable, période. Pas de filtre niveau de test, type de test, statut. |
| 3 | Vue globale, 10 indicateurs cliquables | ✅ | Évolution : écart avec le dernier instantané d'un jour antérieur (un instantané par jour, `pilotage/historique.jsonl`). |
| 4.1 | Couverture des exigences | ✅ | Reliée, exécutée, validée, automatisée, manuelle seulement : mesures distinctes. Liens natifs Jira / Xray. |
| 4.1 | Exigences sans fonctionnalité découverte | 🟡 | « Exigences sans écran relié », avec la réserve : non explorée ≠ absente. |
| 4.2 | Discovery | ✅ | Comptes + répartition découvert / validé par un utilisateur / proposé par l'IA validé / en attente. |
| 4.3 | Qualité de la conception | 🟡 | « Sans jeu de données » mesuré sur les scénarios BDD seulement. |
| 4.4 | Couverture par sprint | 🟡 | Sur les US suivies dans Test Design. « Ajoutées en cours de sprint » si le périmètre du sprint a été figé. |
| 4.4 | Bugs par sprint, couverture par type de test | ⛔ | Le sprint des bugs n'est pas lu dans Jira. |
| 5.1 | Activité d'exécution | ✅ | Bloqué et non exécuté séparés de l'échec. Relances et « réussis après relance » : runs de l'atelier. |
| 5.2 | Quatre taux | 🟡 | Premier passage : runs de l'atelier seulement (Xray ne garde que le dernier résultat). |
| 5.3 | Anomalies | 🟡 | Bugs liés aux test runs des exécutions Xray. Priorité, responsable, dates lus dans Jira (réimporter les exécutions). |
| 5.3 | Réouverts, récurrents, par version, manuel / automatisé | ⛔ | Non lus dans Jira. |
| 5.4 | Charge par responsable | 🟡 | US, cas à valider, exécutions ouvertes, bugs, objectifs en retard. Pas de responsable par test dans la copie Xray. |
| 6.1 | Détection des évolutions | 🟡 | US modifiées, exigences ajoutées au périmètre, écrans à revoir, locators obsolètes ou manquants, fichiers `.robot` / `.resource` modifiés (git local), bugs corrigés. |
| 6.1 | Merge requests GitLab, API, règles métier | ⛔ | Appel réseau exclu du chargement ; pas de comparaison de versions d'API. |
| 6.2 | Analyse d'impact | ✅ | `connaissance.analyser_impact`, relations fiables seulement. Évolution hors graphe : dite, sélection « partielle ». |
| 6.3 | Trois catégories, motif par test | 🟡 | Complémentaire = autre test du même module que l'élément touché (pas encore par parcours partagé). |
| 6.4 | Indicateurs TNR | ✅ | Recommandés, sélectionnés, écartés, rejoués, réussis, en échec, impacts couverts. |
| 6.5 | Validation humaine, envoi à Execution Center | ✅ | Accepter, écarter (justification obligatoire), ajouter ; campagne de type TNR créée, rien n'est lancé. |
| 7.1 | Alertes avec action | ✅ | Chaque alerte mène à l'écran qui la traite. |
| 7.2 | Recommandations | 🟡 | Huit questions, par des règles sur des faits mesurés. Aucun texte généré par une IA ; « confiance » = mesure ou déduction. |
| 8 | État de préparation | ✅ | Quatre statuts, critères réglables par projet (`pilotage/criteres.yaml`), critère bloquant jamais compensé. |
| 8 | Exigences critiques | 🟡 | La criticité des exigences n'est pas lue : le critère porte sur la priorité des tests. |
| 10 | Définition, formule, source, date | ✅ | Sur chaque indicateur (infobulle) ; « — » avec la raison quand la mesure est impossible. |

Deux définitions de « couverte » coexistent et sont dites à l'écran : dans la vue globale, une exigence reliée à un test
(lien Jira / Xray) ; dans la matrice par sprint, une US au statut « Couverte » dans Test Design.

Non vérifié : aucune des zones n'a été essayée sur un vrai projet Jira / Xray ; vérifié par les tests et sur un projet
d'exemple dans un navigateur.
