# Décisions

Une ligne datée par décision d'architecture ou de conception.

- 2026-11-14 : MCP et interface web deviennent des façades ; logique dans quatre moteurs (découverte, intelligence, génération, exécution).
- 2026-11-14 : YAML versionné reste la source de vérité de la connaissance ; base relationnelle seulement si multi-utilisateurs.
- 2026-11-14 : `mcp` épinglé en `<2` : mcp 2.x supprime `mcp.server.fastmcp` et le serveur ne démarrait plus sur une installation neuve ; migration vers `MCPServer` à planifier séparément (risque sur la rétrocompatibilité des outils).
- 2026-11-14 : outils partagés dans `atelier/adapters/facade.py` (mêmes noms, signatures et docstrings que les outils MCP) ; le MCP les enregistre, l'interface web et l'agent intégré les appellent. Aucune des deux façades n'importe plus `server.py`.
- 2026-11-14 : chemin du projet de tests lu au moment de l'appel dans `atelier.domain.projet` (un seul point de réglage) ; plus de constantes `PROJECT_DIR` recopiées dans chaque module.
- 2026-11-14 : les anciens modules racine (`server.py`, `app_map.py`, `jdd.py`, `xray_client.py`, `web_backend.py`, listeners, `web/app.py`) restent des points d'entrée qui désignent les nouveaux modules (`sys.modules`) : configurations Cursor / Claude Desktop et commandes CI inchangées.
- 2026-11-14 : bus d'événements `atelier/domain/evenements.py` ; le surlignage n'est calculé que si un abonné l'écoute (même comportement qu'avec `WEB_EVENTS_URL` / `EVENT_HOOK`). `WEB_EVENTS_URL` reste le réglage du relais MCP → interface.
- 2026-11-14 : délai des appels Oracle plafonné (`DB_TIMEOUT_MS`, 30 s par défaut) : l'invariant 2 l'exigeait, le prototype ne l'appliquait pas.
- 2026-11-14 : interface web protégée par un middleware ASGI unique (`atelier/adapters/web/securite.py`) qui couvre HTTP et WebSocket : Host, Origin, Sec-Fetch-Site, jeton de session en cookie HttpOnly SameSite=Strict, taille plafonnée. Documentation OpenAPI (/docs) désactivée.
- 2026-11-14 : jeton des processus locaux (listener Robot, MCP de Cursor) distinct du jeton de session, seul accepté sur `/api/events` et `/api/externe/*`. Source : `ATELIER_JETON_EVENEMENTS`, sinon généré au démarrage et écrit dans `~/.atelier-automatisation.jeton` (droits 600) pour que le MCP lancé par Cursor le trouve sans configuration. Ce n'est pas un secret métier (valable pour une seule exécution de l'interface, local), d'où l'exception à la règle « jamais sur disque ».
- 2026-11-14 : journal Xray par run dans `results/<dossier>/xray/<horodatage>/` (un nouveau run n'écrase jamais les événements non envoyés du précédent) ; `python -m atelier xray-sync <dossier>` rejoue un run ou tous les runs sous un dossier.
- 2026-11-14 : la préparation de la cible Xray (plan, exécution, ajout au plan) est mémorisée étape par étape dans `xray_outbox.etat.json` : une reprise ne recrée jamais un plan ou une exécution. Limite connue : si Xray crée l'objet mais que la réponse se perd, la reprise le recrée (pas de clé d'idempotence côté Xray).
- 2026-11-14 : synchronisation strictement dans l'ordre du journal ; arrêt au premier événement en échec après tous les essais (les suivants dépendent de la préparation). Erreurs définitives (ticket cible qui est un Test, test absent de l'exécution) marquées « ignoré » pour ne pas bloquer le rejeu.
- 2026-11-14 : le client Xray distingue les erreurs GraphQL (clé inconnue) des erreurs de transport (`ErreurGraphQL`) : une coupure n'est plus jamais prise pour « ticket autre » ou « test inconnu » (défaut du prototype : résultats perdus en silence).
- 2026-11-14 : en fin de run, le listener attend au plus `XRAY_SYNC_DELAI_FIN` (30 s) puis rend la main ; le reste part au rejeu.
- 2026-11-14 : vérification de l'API Xray non faite (documentation officielle inaccessible depuis l'environnement de développement) ; remplacée par un outil d'introspection du schéma réel (`python -m atelier xray-verifier`) et une liste précise des points à vérifier (docs/XRAY_API.md). Aucun appel n'est déclaré vérifié.
- 2026-11-14 : statuts Xray configurables (`XRAY_STATUTS`) et agrégation faite sur les statuts Robot (FAIL > PASS > SKIP) : juste quels que soient les noms personnalisés du projet.
- 2026-11-14 : espaces de travail livrés sur demande (spécification docs/ESPACES_DE_TRAVAIL.md) en parallèle de la roadmap par phases ; seul le MVP (3 graphes + impact) est réalisé, la deuxième phase n'est pas anticipée.
- 2026-11-14 : un seul graphe de connaissance reconstruit à chaque demande depuis les sources (carte, dépôt, JDD, instantané Xray, résultats, déclarations) ; Coverage et Flow en sont des vues. Pas de base de données : les déclarations sont un YAML versionné (connaissance/) + un historique JSONL.
- 2026-11-14 : un élément observé n'est jamais supprimé de sa source depuis le graphe : il est masqué (historisé). L'IA ne crée que des éléments « déduit / à valider » et ne modifie rien de validé ; l'analyse d'impact ignore un lien déduit non validé.
- 2026-11-14 : couverture calculée sur un instantané daté du patrimoine (patrimoine/xray.json), remplacé seulement par une synchronisation ou un import explicites ; « automatisé » = clé Xray portée en tag par un test Robot du dépôt.
- 2026-11-14 : Automation Candidates n'affiche pas de score tant que les critères (phase 3) ne sont pas collectés : « déjà automatisé » est la seule recommandation affirmée, les données manquantes sont listées.
- 2026-11-14 : composant graphe SVG écrit sans bibliothèque (réseau d'entreprise sans CDN, pas de dépendance JavaScript à maintenir) ; au-delà de 600 nœuds l'affichage est tronqué et l'interface demande de filtrer.
- 2026-11-14 : interface refaite d'après les maquettes fournies ; seules les données réelles sont affichées. Les éléments des maquettes sans source (confiance IA par étape, « couverture estimée », agents / file Redis, utilisateur connecté) ne sont pas simulés : remplacés par des données calculées (statistiques du scénario, contrôles) ou annoncés comme non disponibles.
- 2026-11-14 : thème sombre par défaut si le système le demande, bascule mémorisée dans le navigateur (préférence locale uniquement) ; couleurs du graphe lues dans les variables CSS du thème.
- 2026-11-14 : scénario BDD stocké en `.feature` + `.yaml` (liens et validations) dans `bdd/` du projet ; un `.feature` modifié à la main est relu et les liens sont conservés pour les étapes au texte inchangé ; un texte modifié est à revalider ; validation refusée si un contrôle de gravité haute subsiste.
- 2026-11-14 : les apostrophes du français ne délimitent pas une donnée littérale (« d'erreur ») ; seuls les nombres et les textes entre guillemets doubles ou « » le sont.
- 2026-11-14 : chaque run lancé par l'interface écrit dans `results/runs/<id>/` (fin de l'écrasement de `results/mcp`) ; arrêt par SIGINT pour que Robot termine le test en cours et écrive son rapport.
- 2026-11-14 : l'éditeur refuse d'écraser un fichier modifié sur le disque depuis son ouverture (contrôle par le contenu lu) ; chaque enregistrement est historisé avec le nombre de lignes ajoutées / retirées.
- 2026-11-14 : design aligné au plus près des maquettes (grappes colorées autour d'un nœud central, cartes à icône, liens courbes ; numéros d'étapes hors carte, menu d'actions vertical, Gherkin numéroté ; éditeur à 4 colonnes ; exécution à rangées décalées). Écarts assumés : aucune « confiance IA » par étape ni « couverture estimée » (pas de source), utilisateur = compte du poste (pas d'authentification), écran de référence affiché seulement si le locator appartient à un écran de la carte.
- 2026-11-14 : Knowledge Graph en régions comme la maquette (exigences en haut à gauche, parcours en haut, actions à gauche, données / locators / résultats à droite, tests en bas à gauche, exécution en bas) ; couleur et légende par famille de types (variables `--f-*`) ; un seul libellé de relation par couple de régions ; au-delà de 6 cartes une région se replie derrière « + N autres » (les éléments liés directement au centre passent d'abord). Les familles Exécution et Résultat restent vides tant que le graphe n'a pas de nœud correspondant : rien n'est inventé.
- 2026-11-14 : projet de démonstration `demo/banque_connexion/` (application web fictive, module Connexion) : 7 tests Robot réellement exécutés via une petite bibliothèque Playwright de démonstration (`NavigateurDemo`, pour ne pas imposer Node.js / Browser library), patrimoine Xray fictif, carte observée en session web réelle, scénario BDD créé par le moteur. Une anomalie volontaire (blocage au 4e échec au lieu du 3e) fait échouer DEMO-304 : le dashboard et l'analyse d'échec montrent de vrais résultats, rien n'est simulé.
- 2026-11-14 : `run_robot` avec un environnement JDD mais sans jeux injecte les jeux référencés par la suite (`&{JDD_<NOM>}`) ; le détail d'un test n'affiche que le(s) jeu(x) qu'il utilise, résout les `${LOC_…}` depuis le dépôt (sous-étape en échec d'abord) et inclut setup / teardown (capture d'échec).
- 2026-11-14 : Test Strategy stockée dans le projet de tests (`strategie/strategie.yaml`, versions publiées `strategie/versions/v<N>.yaml` créées en mode exclusif, `index.json`, `journal.jsonl`) : versionnable avec le dépôt, sans base de données. Les indicateurs (objectifs, critères automatiques, vue d'ensemble) sont recalculés à chaque lecture depuis l'instantané Xray, le graphe et l'historique des runs ; aucun champ ne permet de saisir une valeur actuelle (RG10). Modifier une version publiée ouvre la version suivante (RG12). Les rôles ne sont pas gérés (pas d'authentification locale) : l'auteur journalisé est le compte du poste.
- 2026-11-14 : Test Design ne crée pas de référentiel concurrent : il lit l'instantané Xray, les scénarios BDD et le dépôt, et ne stocke que des métadonnées de conception dans le projet (`conception/revues.json`, `conception/baselines/` en création exclusive, `conception/mapping_xray.yaml`, `conception/journal.jsonl`). Le statut de revue interne est distinct du statut Xray ; les statuts externes ne sont jamais supposés (à configurer). Les modes de synchronisation B / C restent désactivés tant que les mutations Xray ne sont pas vérifiées.
- 2026-11-14 : `/api/run` ne refuse plus un run concurrent (409) : il le met dans la file à priorités de l'Execution Center, servie par le runner local (capacité 1, déclarée telle quelle). Le contexte (projet, application, version, environnement, plateforme, commit, revue des scripts) est figé à l'entrée dans la file. Le retry est une seconde tentative des seuls échecs, preuves conservées par tentative et résultats fusionnés par `rebot --merge` ; « Recommandé par IA » et le score d'automatisabilité ne sont jamais renseignés sans calcul réel.
- 2026-11-14 : Failure Analysis classe les échecs par règles déterministes ; la « force » d'une hypothèse est un libellé tiré de la règle, jamais un pourcentage de confiance (les pourcentages du cahier des charges supposeraient un modèle calibré). L'IA n'est appelée qu'à la demande, sans valeurs de JDD. Quality Governance : chaque KPI porte définition, formule, source et date ; un facteur sans donnée est exclu et les pondérations renormalisées ; la release readiness ne vaut jamais autorisation et exige un avis QA tracé.


## 2026-11-14 — Plusieurs projets dans une même instance (repository + projet Xray / Jira)
- Un projet = un repository de tests Robot + une clé de projet Xray / Jira + URL Jira / Xray + environnements.
  Toutes les données du produit (stratégie, conception, instantané Xray, exécutions, échecs, gouvernance,
  Knowledge Graph) restent dans le repository : basculer de projet change tout le contexte, rien n'est partagé.
- La liste est une configuration du poste (`ATELIER_PROJETS`, défaut `~/.atelier-projets.json`), jamais du dépôt.
  Elle ne contient aucun secret : seulement le NOM de la variable d'environnement qui porte chaque identifiant
  (ex. `XRAY_CLIENT_ID_TAM`) ; une valeur collée par erreur est refusée.
- Bascule (`atelier/domain/projets.py`) : refusée si un run est en cours ou en file ; journalisée
  (`~/.atelier-projets.journal.jsonl`) ; met à jour PROJECT_DIR, ROBOT_PROJECT_DIR (sous-processus Robot) et les
  variables de connexion du projet (ou les valeurs globales de démarrage). Au démarrage, le dernier projet actif est
  repris, sauf si ROBOT_PROJECT_DIR est imposé. Le serveur MCP (processus séparé) reste sur ROBOT_PROJECT_DIR.
- La clé du projet actif préremplit imports, synchronisation Jira, publication BDD et anomalies ; pour les runs elle
  n'est qu'une indication (un ticket Xray reste un choix explicite : pas de plan / exécution créés par défaut).


## 2026-11-14 — GitLab d'entreprise (LDAP) : merge requests encadrées
- Connexion par jeton d'accès personnel (portées api, write_repository), jamais le mot de passe LDAP ; jeton lu dans
  GITLAB_TOKEN ou la variable désignée par le projet ; envoyé en en-tête (API) ou via GIT_CONFIG_* en environnement
  (git push https) : jamais dans une URL, une ligne de commande, un fichier ou un log. Certificat : GITLAB_CA_BUNDLE.
- Merge request depuis Automation Studio › Git : branche non protégée, pas de modification suivie non validée,
  suites .robot modifiées approuvées en revue technique ET stables sur leurs 3 dernières exécutions réelles
  (invariant 5), sinon dérogation justifiée écrite dans la MR et journalisée. Description générée : fichiers,
  revues, stabilité, liens Xray. L'atelier ne fusionne jamais ; une MR déjà ouverte pour la branche est réutilisée.
- Lecture : utilisateur, projet, branche par défaut, MR ouvertes, commits récents ; état dans Paramètres › Connexions.


## 2026-11-14 — Connexions générales et secrets saisis dans l'application
- URL Jira, e-mail Jira, URL Xray : connexions générales (tous les projets), enregistrées dans la liste du poste
  (non secrètes) ; une variable d'environnement posée au démarrage reste prioritaire ; un projet peut les redéfinir.
- Secrets (identifiants Xray, jetons Jira / GitLab) : saisissables dans Paramètres › Connexions, gardés en mémoire
  par le serveur local jusqu'à son arrêt — jamais écrits sur disque, jamais journalisés (le nom seulement), jamais
  renvoyés par l'API. Seuls les noms attendus (secrets généraux ou variables déclarées par un projet) sont acceptés.
  Usage durable : variables d'environnement du poste. Un coffre du système (Windows Credential Manager) serait une
  évolution de la règle « secrets uniquement en variables d'environnement » : à décider explicitement.


## 2026-11-14 — Coffre des secrets du système (keyring) — décision de l'utilisateur
- Les secrets saisis dans Paramètres › Connexions sont mémorisés dans le coffre du système via `keyring`
  (Gestionnaire d'identifiants Windows ; trousseau macOS ; Secret Service Linux), service « atelier-automatisation ».
  Nouvelle dépendance justifiée : seule façon portable d'utiliser le coffre chiffré de l'OS sans écrire de fichier.
- Rechargés au démarrage par l'interface web ET par les commandes `python -m atelier …` ; une variable
  d'environnement du poste reste prioritaire ; « Effacer » retire le secret de la session et du coffre.
- Coffre indisponible (aucun backend système) ou ATELIER_COFFRE=non : saisie en mémoire de session uniquement.
- Règle du CLAUDE.md amendée en conséquence (secrets : environnement ou coffre du système, jamais un fichier de l'atelier).


## 2026-11-14 — Stratégie actionnable : testabilité des US ; IA interchangeable
- À la demande de l'utilisateur, la stratégie agit sur les US des squads (espaces Jira activés) plutôt que sur des
  critères d'entrée bloquants : détection, analyse, questions en commentaire Jira, cas de test, publication Xray.
- IA choisie par l'entreprise (`IA_FOURNISSEUR`) : aucune, Cursor via le MCP (autorisé), LLM interne compatible
  OpenAI (prévu par l'entreprise), Claude sur autorisation. Les règles explicables fonctionnent seules.
- Toute écriture externe (commentaire Jira, test Xray, lien) est explicite et historisée ; les propositions d'IA ne
  sont jamais appliquées sans validation ; détails et points à vérifier : docs/TESTABILITE_US.md.


## 2026-11-14 — La stratégie se rejoue à chaque sprint
- Décision de l'utilisateur : le backlog du sprint (construit par le PO) est le cœur de la stratégie de test.
  Portée par défaut d'un espace : le sprint actif ; périmètre figé au démarrage (photo immuable, création exclusive)
  et bilan de fin de sprint (couverture, US ajoutées / retirées en cours de sprint). Détails : docs/TESTABILITE_US.md.
