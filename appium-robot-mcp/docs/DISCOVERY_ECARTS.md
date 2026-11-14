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
| 3. Studio | livré | **fenêtre flottante Discovery** (bouton en bas à droite de toute la plateforme, déplaçable, redimensionnable, réductible ; reste ouverte en changeant d'écran) : choix de la cible (émulateur, appareil branché, simulateur iOS, navigateur), démarrage en un clic (connexion + session), écran en direct ; toucher l'image exécute directement une navigation sûre, sinon affiche la classe et demande confirmation ou refuse ; suggestions et derniers événements ; l'espace Studio garde le résumé et la timeline complète |
| 4. Screen Inventory | livré | écrans de la carte : module, plateformes, composants, sans locator stable, états, modifiés, couverts |
| 5. Component Inspector | livré (lecture) | locators par plateforme, secours, fiabilité Stable / Reliable / Fragile / Missing ; édition : écran en direct et Automation Studio › Locators |
| 6. Navigation Explorer | livré | transitions avec fiabilité, impasses, écrans isolés, transitions instables, chemin le plus fiable (Dijkstra) |
| 7. Behavioral Intelligence | livré | après chaque action du Studio : messages apparus, éléments apparus / disparus (même écran) ; chaque message devient une règle proposée (à valider) |
| 8. API Observation | livré (web) | appels XHR / fetch observés (méthode, chemin normalisé, noms des paramètres, statut ; jamais de valeurs, corps ni en-têtes), rapprochés des contrats OpenAPI ; non documentés proposés au KG. Mobile : proxy de test à brancher |
| 9. Results | livré | nouveaux écrans, écrans modifiés, composants ajoutés, transitions, actions, annotations, étapes sensibles |
| 10. Validation | livré | écrans à nommer (nom métier + module), propositions du KG (validation complète dans Application Intelligence) |
| 11. History | livré | historique des sessions, comparaison de deux sessions (écrans ajoutés / retirés, transitions ajoutées) |
| 12. Settings | livré | classement des actions (motifs sensibles, classes autorisées par environnement, classements manuels), liste rouge |
| Correlation Jira / Xray / GitLab | livré | par écran : exigences Jira, tests Xray, tests Robot, fichiers du dépôt (liens du KG) ; exigences proposées par mots communs, à confirmer ; derniers commits GitLab à la demande |

## Les 4 modes

| Mode | État |
|---|---|
| Guided Discovery | livré : la navigation (écran en direct, MCP, listener) alimente la carte et la timeline |
| Test-Based Discovery | livré : run Robot avec cartographie lancé depuis le Studio |
| Autonomous Discovery | livré : exploration existante (aucune saisie, liste rouge, liens externes ignorés) lancée depuis le Studio avec les limites de la session |
| AI Assisted Discovery | livré : suggestions explicables (actions sûres jamais essayées, pistes de la carte) ; avec IA_FOURNISSEUR interne / anthropic, le modèle ordonne et justifie les candidates (textes masqués, clés inventées ignorées, rien n'est exécuté sans clic) |

## Knowledge Graph : sources

Le panneau **Sources du graphe** (Knowledge Graph › connaissance) montre ce qui alimente le graphe :
carte (Discovery), copie locale Jira, copie locale Xray (tests, définitions), dépôt Robot, JDD,
contrats OpenAPI, déclarations. **Jira et Xray ne sont jamais interrogés en direct** : il faut
synchroniser Jira / importer les définitions Xray ; chaque ligne porte son action de mise à jour,
et le bouton **Lancer une Discovery** ouvre le Studio.

## Discovery piloté par Cursor / Claude (MCP)

L'atelier observe la mécanique (écrans, transitions, locators, réseau) ; l'agent apporte le sens, toujours en
propositions à valider. Règle Cursor : `cursor_rules_discovery.mdc`.

| Outil MCP | Rôle |
|---|---|
| `discovery_demarrer` | session Discovery sur la plateforme de la session ouverte |
| `discovery_ecran_courant` | écran, éléments avec classe et autorisation, textes affichés, actions à essayer, pistes |
| `discovery_proposer` | nom d'écran + module, fonctionnalité, parcours, règle, action, rôle, entité, lien vers une exigence |
| `discovery_terminer` | résultats de la session et propositions en attente |
| `discovery_parcours_vers_bdd` | brouillon de scénario BDD (Test Design) depuis une suite d'écrans ou un parcours du KG |

**Du parcours au test** (atelier/generation/parcours_bdd.py) : depuis un chemin (Navigation Explorer), un parcours du
Knowledge Graph ou une session (Discovery Results, fin de session dans la fenêtre), brouillon Gherkin français
relié aux écrans et locators de la carte, champs renseignés « avec le jeu de données » (aucune donnée littérale),
actions sensibles signalées (tag action_sensible). Étapes non validées : chaîne habituelle ensuite.

- Pendant une session en cours, `tap` et `type_text` du MCP passent par le classement : interdites et
  sensibles refusées à l'agent (la confirmation d'une action sensible est humaine), contrôlées selon
  l'environnement ; les comportements observés sont enregistrés. Hors session : comportement historique
  (construction de tests), signatures inchangées.
- Knowledge Graph : chaque proposition porte sa provenance (« Cursor (MCP) · session DS-… ») ; les règles
  observées sont reliées à leur écran ; chaque locator porte la classe de son action ; les noms d'écran
  proposés sont visibles sur l'écran. Validation / rejet dans la fenêtre Discovery ou Discovery › Validation ;
  un rejet est définitif (jamais reproposé).

## Classement des actions (atelier/discovery/classement.py)

| Classe | Exemple | Exploration autonome / suggestions | Depuis le Studio |
|---|---|---|---|
| Safe | lien, bouton de navigation | oui | oui |
| Controlled | champ, case à cocher | jamais | selon l'environnement (défaut : oui) |
| Sensitive | action sur un sujet sensible (« Nouveau virement », « Ajouter un bénéficiaire »), élément marqué sensible ; un menu « Virements » reste Safe | jamais | seulement si l'environnement l'autorise ET après confirmation |
| Forbidden | liste rouge, actions interdites de la session | jamais | jamais, sur aucun environnement |

## Reste à faire

1. Observation réseau mobile (proxy de test, certificat de l'entreprise, masquage).
2. Saisie assistée depuis le Studio (aujourd'hui : à la main sur le device), avec les JDD et le classement.
3. Corrélation avec les fichiers de l'application elle-même (dépôt applicatif GitLab), en plus du dépôt de tests.
