# Application Discovery — écarts avec le cahier des charges « Discovery Studio »

Principe retenu : **la carte de l'application (`app_map/<app>/`) reste la mémoire de la découverte** ;
le Knowledge Graph la lit, sans second graphe. Une session Discovery ne stocke que sa configuration,
sa timeline et une photo de la carte au début et à la fin : les résultats sont une **différence**,
jamais une valeur estimée.

Code : `atelier/discovery/sessions_discovery.py` (moteur), routes `/api/discovery/*`,
écran `atelier/adapters/web/static/ecran_discovery.js` (onglet **Discovery** de /plateforme).
Test : `tests/test_discovery_sessions.py`.

## Les 12 espaces

| Espace | État | Contenu |
|---|---|---|
| 1. Overview | livré | KPI fonctionnels, techniques, qualité de la connaissance (carte + KG), actions rapides |
| 2. Sessions | livré | création (application, build, plateforme, environnement, device, mode, profondeur, écrans max, périmètre, actions interdites), liste, statuts Préparée / En cours / En pause / Terminée |
| 3. Studio | partiel | Start / Pause / Resume / Stop, annotation, étape sensible, timeline en direct (bus d'événements : carte, navigation, exploration, runs) ; écran du device en direct : écran classique `/` (pas encore intégré dans le Studio) |
| 4. Screen Inventory | livré | écrans de la carte : module, plateformes, composants, sans locator stable, états, modifiés, couverts |
| 5. Component Inspector | livré (lecture) | locators par plateforme, secours, fiabilité Stable / Reliable / Fragile / Missing ; édition : écran en direct et Automation Studio › Locators |
| 6. Navigation Explorer | livré | transitions avec fiabilité, impasses, écrans isolés, transitions instables, chemin le plus fiable (Dijkstra) |
| 7. Behavioral Intelligence | à venir (phase 5) | messages d'erreur, validations, règles comportementales proposées |
| 8. API Observation | partiel | endpoints du KG (OpenAPI, déclarations) ; interception réseau en session à venir |
| 9. Results | livré | nouveaux écrans, écrans modifiés, composants ajoutés, transitions, actions, annotations, étapes sensibles |
| 10. Validation | livré | écrans à nommer (nom métier + module), propositions du KG (validation complète dans Application Intelligence) |
| 11. History | livré | historique des sessions, comparaison de deux sessions (écrans ajoutés / retirés, transitions ajoutées) |
| 12. Settings | partiel | liste rouge de l'application ; classement Safe / Controlled / Sensitive / Forbidden par environnement à venir |

## Les 4 modes

| Mode | État |
|---|---|
| Guided Discovery | livré : la navigation (écran en direct, MCP, listener) alimente la carte et la timeline |
| Test-Based Discovery | livré : run Robot avec cartographie lancé depuis le Studio |
| Autonomous Discovery | livré : exploration existante (aucune saisie, liste rouge, liens externes ignorés) lancée depuis le Studio avec les limites de la session |
| AI Assisted Discovery | à venir (phase 4) : suggestions de prochaines actions par le fournisseur IA configuré |

## Knowledge Graph : sources

Le panneau **Sources du graphe** (Knowledge Graph › connaissance) montre ce qui alimente le graphe :
carte (Discovery), copie locale Jira, copie locale Xray (tests, définitions), dépôt Robot, JDD,
contrats OpenAPI, déclarations. **Jira et Xray ne sont jamais interrogés en direct** : il faut
synchroniser Jira / importer les définitions Xray ; chaque ligne porte son action de mise à jour,
et le bouton **Lancer une Discovery** ouvre le Studio.

## Reste à faire (par ordre)

1. Écran du device / navigateur intégré dans le Studio (aujourd'hui : écran classique `/`).
2. Mode assisté par IA (suggestions, branches non explorées), propositions soumises à validation.
3. Classement des actions par environnement (Safe / Controlled / Sensitive / Forbidden).
4. Observation comportementale et réseau (proxy de test, masquage des tokens et données personnelles).
5. Corrélation automatique avec Jira, Xray et GitLab (écran ↔ exigence ↔ test ↔ fichier).
