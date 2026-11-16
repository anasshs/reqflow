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


## 2026-11-14 — Applications d'un projet : déclaration dans la plateforme, rattachement Xray
- L'assistant « Nouvelle application » de l'interface classique est repris dans Paramètres › Applications
  (identité, prérequis, liste rouge, import des locators, cartographie par la TNR ; exploration en direct : interface classique).
- Les applications vivent dans le repository du projet (`app_map/`) : un projet Xray peut en contenir plusieurs.
  Chaque application porte `projet_xray` (défaut : projet actif) et `tests_xray` (composant ou libellé Jira qui
  identifie ses tests dans ce projet ; vide = tout le projet).

## 2026-11-15 — Le coffre est la source unique des secrets — décision de l'utilisateur
- Tous les processus lisent les secrets dans le coffre du système au moment de l'appel : interface web, MCP (Cursor /
  Claude, relu avant les outils sans redémarrage), ligne de commande, listener des runs Robot (sous-processus).
- Le coffre prime sur une variable d'environnement du poste, qui ne sert que de repli ; « Verser dans le coffre »
  (Paramètres › Connexions) y copie une variable du poste sans jamais afficher sa valeur.
- Un secret saisi dans l'atelier va toujours au coffre quand il est disponible (plus de « session seulement ») ;
  coffre indisponible : mémoire de session, signalé.
- Variables propres d'un projet (ex. XRAY_CLIENT_ID_TAM) : lues dans le coffre elles aussi, sans repli silencieux sur
  le compte général. Clés IA (ANTHROPIC_API_KEY, IA_INTERNE_JETON) gérées de la même façon.


## 2026-11-15 — Campagne, Test Plan et Test Execution — décision de l'utilisateur
- Une campagne est une définition locale de l'atelier (quoi lancer, plateformes, environnement, planification) ;
  ce n'est ni un Test Plan ni une Test Execution Xray.
- Elle se rattache à un Test Plan Xray existant (liste filtrée par la JQL des Test Plans de l'application) ou à un
  Test Plan créé depuis le formulaire (action explicite). Chaque lancement crée une Test Execution rattachée à ce
  plan, ou réutilise une Test Execution donnée.
- Configuration de l'application : JQL des Test Plans et JQL des Test Executions (vide = tout le projet Xray) ; le
  tableau de bord ne lit dans Xray que les Test Executions de cette JQL.
- Vocabulaire de l'atelier : Campagne ↔ Test Plan ; Exécution ↔ Test Execution ; Run = un lancement Robot qui
  écrit dans une Exécution. Plusieurs runs peuvent alimenter la même Exécution (relance des échecs, relance
  complète, retry) ; une campagne lancée sur deux plateformes crée une Exécution par plateforme (environnement
  Xray distinct). Le lien Exécution ↔ runs ↔ campagne est calculé à partir des runs, jamais stocké à part.

## 2026-11-15 — Couverture : liaison directe Test Xray ↔ Story / Requirement — décision de l'utilisateur
- La liaison native Test Xray ↔ Story / Requirement Jira (liens « Test », lus depuis l'exigence et depuis le test) est
  le mécanisme principal de couverture ; l'atelier n'en crée aucune. Epics / Features (parents Jira, jusqu'à 3
  niveaux) servent seulement à agréger : macro-fonctionnalité = ancêtre le plus haut, fonctionnalité = parent direct.
- Périmètre : JQL des exigences de l'application (Paramètres › Configuration ; défaut : espaces de la politique des
  US), moins les exigences exclues de la Test Strategy.
- Quatre indicateurs distincts : existence, exécution, résultat, automatisée (filtrable par plateforme) ; filtres
  par version (fixVersions). L'automatisation n'entre plus dans l'état « couverte ».
- Critères d'acceptation : activables par application ; un test couvre un critère par association enregistrée dans
  l'atelier (historisée) ou par libellé Xray AC<n> / CA<n>.
- Synchronisations journalisées (ajouts, sorties, liens modifiés) ; une exigence sortie de la JQL est gardée et
  marquée « hors périmètre », jamais supprimée en silence ; une JQL vide n'écrase rien. Instantanés par version.

## 2026-11-15 — Construire avec Cursor : l'agent construit, l'automaticien voit et valide — décision de l'utilisateur
- Cursor construit les tests par le MCP (socle, scénario BDD, génération, étape isolée, corrections de locators,
  factorisation) ; il ne peut ni approuver, ni refuser, ni publier. Tout ce qu'il écrit ou corrige renvoie les
  suites concernées en revue technique.
- Chaque appel d'outil MCP est publié à l'atelier (début, fin, durée, résultat ; texte saisi et secrets masqués).
  L'écran piloté est visible : mobile par adb / simctl, navigateur par une image envoyée par le MCP après chaque
  action (route protégée par le jeton des processus locaux). Vue : Automation Studio › Construire › Avec Cursor.

## 2026-11-15 — Application Intelligence = cerveau de chaque application — décision de l'utilisateur
- Le cerveau (atelier/intelligence/cerveau.py) est la porte d'entrée de la connaissance d'une application : sources et
  fraîcheur (carte, exigences Jira, tests et exécutions Xray, dépôt Robot, runs, sessions Cursor), modules (connaissance,
  couverture, automatisation, échecs), lacunes avec l'action qui les comble, journal d'apprentissage, questions.
- Les réponses ne s'appuient que sur ce que le cerveau sait (IA facultative, rédige à partir des faits fournis).
- Cursor lit le cerveau avant de construire ou d'explorer (outils cerveau_application, cerveau_question).

## 2026-11-15 — Un seul endroit par sujet entre les modules
- **Couverture** : une seule rubrique, Test Strategy › Couverture (onglet « Couverture des exigences » + onglets Coverage
  Intelligence). Quality Governance › Functional Coverage n'affiche plus qu'un résumé (4 dimensions) et un lien.
  L'ancienne adresse `#strategie/coverage` mène à la même page (onglet Overview).
- **Écrans** : Discovery explore, Application Intelligence consulte. Screen Inventory, Component Inspector et Discovery
  Validation sortent du menu Discovery ; leurs adresses mènent à Application Intelligence › Écrans (fiabilité des
  locators, « à nommer », défilement sur l'écran demandé) et › À valider.
- **Corrections de locators** : un seul circuit, Automation Studio › Socle › Locators : corrections calculées + propositions
  nées d'un échec (workflow Proposed → … → Validated inchangé). Failure Analysis › Fix Recommendations les compte et y renvoie.
- **Exigences sans test** : Missing Tests est l'entrée (diagnostic + colonne « Suivi Test Design ») ; US à couvrir reste le
  lieu de travail (conception, validation, publication). Plus de « Proposer » en double pour une exigence déjà suivie.

## 2026-11-15 — Git et GitLab depuis l'atelier : synchroniser oui, fusionner non
- Le code source des tests vit dans le clone local du dépôt GitLab (`ROBOT_PROJECT_DIR`). Studio › Revue et publication ›
  Git et merge request couvre le circuit : Récupérer (fetch), Tirer (`pull --ff-only`), Basculer, créer la branche,
  commit local (suites approuvées), pousser + merge request, pousser les corrections sur la MR ouverte.
- La fusion reste une décision humaine dans GitLab ; l'atelier ne fusionne pas, ne rebase pas et ne résout aucun conflit :
  en cas de divergence, « Tirer » refuse et renvoie vers l'IDE / le terminal. Après fusion : « Revenir sur la cible et tirer ».
- Les nouveaux commits poussés sur une MR ouverte passent les mêmes garde-fous que la création (revue approuvée,
  3 exécutions stables ou dérogation écrite).
- L'état de travail de l'atelier rangé dans le projet (studio/, executions/, results/, discovery/, connaissance/, analyses/,
  couverture/, gouvernance/, testabilite/) est propre à chaque poste : signalé s'il est versionné (.gitignore conseillé),
  il ne bloque ni Tirer, ni Basculer, ni la merge request.

## 2026-11-15 — Test Design simplifié : 6 entrées, doublons renvoyés à leur module
- Menu : Vue d'ensemble · À concevoir (ex-US à couvrir) · Cas de test (Cas Xray et revue, Scénarios BDD) · Règles de test ·
  Organisation Xray (suites / plans / dossiers, baselines) · Réglages (mapping et synchronisation Xray, rangement).
- La revue interne de conception est intégrée à Cas de test (compteurs du circuit = filtre, panneau de revue) ;
  `#conception/revue` ouvre Cas de test filtré sur « En revue ».
- Écrans en double retirés, adresses conservées : Exigences & import → Test Strategy › Couverture ; Traçabilité →
  Knowledge Graph (couverture) ; Réutilisables → Studio › Keywords ; Jeux de données → Studio › Données de test
  (la liste des jeux y est désormais affichée).

## 2026-11-15 — Failure Analysis et Execution Center simplifiés (5 entrées chacun)
- Failure Analysis : Vue d'ensemble (avec les tendances) · Échecs à traiter · Investigation (Diagnostic et preuves,
  Anomalie Jira, Retests et clôture) · Causes et corrections (Causes racines, Corrections recommandées, Locators en cause) ·
  Réglages. AI Diagnosis et Evidence Viewer étaient déjà l'investigation ; Failure Trends rejoint la vue d'ensemble.
- Execution Center : Vue d'ensemble · Campagnes · Lancer (Choisir des tests, Paramétrer un run, File d'attente, En direct) ·
  Résultats (Résultats, Historique, Preuves, Synchronisation Xray) · Infrastructure (Appareils, Runners, Réglages).
- Les preuves d'un run restent à un seul endroit (Execution Center › Résultats › Preuves) ; Failure Analysis les montre
  dans le contexte de l'échec. Le retest d'un échec (clôture) reste distinct de « Qualifier » du Studio (3 runs d'une suite).
- Anciennes adresses conservées ; titres d'écrans en français.

## 2026-11-15 — Quality Governance simplifié (4 entrées)
- Vue qualité (Vue qualité, Couverture fonctionnelle, Couverture d'automatisation, Efficacité des tests) · Release Readiness
  (Release Readiness, Recommandations) · Tendances et risques (Tendances, Risques applicatifs, Stabilité, Santé de
  l'automatisation) · Rapports (Rapports, Réglages). Module en lecture seule : les indicateurs reprennent les données
  des autres modules (Couverture, Studio, Failure Analysis), sans les recalculer ailleurs. Adresses et titres en français.

## 2026-11-15 — Discovery simplifié (5 entrées) ; nommer un écran dans Application Intelligence
- Discovery : Vue d'ensemble · Explorer (Explorer, Sessions) · Résultats (Synthèse, Navigation, Comportements, API observées) ·
  Corrélation · Historique et réglages. Écrans, composants et validation restent consultés dans Application Intelligence
  (anciennes adresses redirigées) ; leurs anciens écrans Discovery, devenus inaccessibles, sont supprimés du code.
- Le nommage des écrans (« à nommer »), qui n'existait que dans l'ancienne Discovery Validation, est désormais dans
  Application Intelligence › Écrans (nom métier + module, journalisé).

## 2026-11-15 — Suppression du module Test Strategy (éléments déplacés, export conservé)
- Constat : sur 14 rubriques, seules quelques-unes servaient à un calcul ; le reste était documentaire et les objectifs /
  critères doublaient les seuils de Quality Governance. Décision de l'utilisateur : supprimer le module, déplacer l'utile.
- Déplacements (même stockage `strategie/`, données existantes conservées, référentiel créé au premier usage) :
  couverture → Application Intelligence › Couverture ; périmètre (exclusions, criticité) → Paramètres › Périmètre ;
  environnements (vérification utilisée avant run) → Execution Center › Infrastructure › Environnements ;
  objectifs et critères d'entrée / sortie → Quality Governance › Release Readiness (les critères de sortie y sont affichés
  et un critère obligatoire non satisfait déconseille la livraison) ; décisions du plan d'automatisation → Automation Studio ›
  À automatiser (« Décider »).
- Export du document de stratégie (PDF, données réelles du jour) : Quality Governance › Rapports.
- Abandonnés comme écrans : types et niveaux de tests, risques, données, outils, workflow versions / publication
  (les données restent dans le fichier et apparaissent dans l'export). Anciennes adresses #strategie/… redirigées.
- Le score de Release Readiness n'est pas modifié : l'état des critères de sortie est affiché à côté, comme alerte.

## 2026-11-15 — V2 phase 0 bis : validation imposée côté serveur pour les outils MCP d'écriture
- Nouveau mécanisme commun `atelier/domain/demandes.py` : un outil qui écrirait dans Jira / Xray ou modifierait la
  carte sans retour dépose une **demande** (stockée dans `<projet>/validations/`, idempotente, historisée) ; elle
  n'est exécutée qu'une fois, à l'acceptation dans Application Intelligence › À valider (droit `valider_action`,
  rôle relecteur ; rejet justifié). Un échec d'exécution est conservé, jamais rejoué automatiquement.
- Outils concernés (noms, signatures et descriptions inchangés — contrat de rétrocompatibilité) :
  `jira_transition`, `qualify_failure`, `import_results_to_xray` (aperçu des statistiques) → demandes ;
  `run_robot` : les `jira_transition_*` ne sont plus transmises au run, elles deviennent des demandes sur
  l'exécution Xray du run (la transition « fin si échec » seulement s'il y a eu un échec) ; l'envoi des résultats
  du run dans Xray est inchangé (but du run, idempotent) ;
  `name_screen` : nommage direct, **fusion** d'écrans → demande ; `add_screen_locator` : ajout direct,
  **remplacement** d'une valeur → demande ;
  `tap` / `type_text` : classés côté serveur même hors session Discovery (liste rouge et actions sensibles refusées,
  navigation et saisie contrôlée permises).
- Migration : le comportement est expliqué dans la réponse de chaque outil et dans les règles Cursor
  (`cursor_rules_*.mdc`, section « Actions soumises à validation ») ; à réinstaller depuis Paramètres › Cursor / Claude.
- Interface web : les écrans de l'atelier (Execution Center, Failure Analysis…) gardent leurs propres circuits de
  confirmation ; seule l'entrée MCP est concernée.

## 2026-11-15 — V2 phase 1 : parcours de fonctionnalité
- Workflow léger (pas d'agent) : le parcours relie les modules existants, référence leurs objets et garde états,
  validations, historique et versions (`docs/V2_PHASE1_PARCOURS.md`). Onglet principal « Parcours ».
- 5 outils MCP ajoutés (`parcours_*`), 81 au total ; aucun outil existant modifié.
- Décision humaine imposée côté serveur pour la validation des scénarios, la qualification et la synchronisation
  Xray (depuis Cursor : mise en attente de validation ; dans l'atelier : rôle relecteur).
- Stockage dans `<projet>/parcours/` (état de travail de l'atelier, ignoré par les contrôles Git du Studio).

## 2026-11-16 — V2 phase 2 : règles Cursor structurées et versionnées
- 11 règles (`regles_cursor/`), installées sous `.cursor/rules/atelier-<id>.mdc` ; les deux règles historiques gardent
  leur nom installé (`atelier-automatisation.mdc`, `atelier-discovery.mdc`) : pas de fichier orphelin chez les équipes.
- Versions par projet dans `<projet>/atelier_regles/` ; synchronisation avec aperçu, un fichier modifié localement
  n'est remplacé que s'il est choisi (sauvegarde `.bak`) ; les règles livrées avant la V2 sont reconnues par empreinte.
- « Tester le serveur MCP » démarre réellement le serveur comme Cursor (preuve de connexion, pas une supposition).
- Outil MCP `cursor_regles` ajouté (82 outils).

## 2026-11-16 — V2 phase 3 : couverture des parcours et composants UI
- Cinq niveaux explicables (découvert, associé, automatisé, exécuté, réussi) calculés sur le Knowledge Graph ;
  « vérifié » = exécuté (au moins une exécution réelle), seul sens mesurable sans inventer.
- Tests manuels : pas de couverture au niveau composant (texte libre Xray) ; association écran ↔ test Xray déduite
  par la fonctionnalité, affichée comme telle.
- Lieu unique : Application Intelligence › Couverture (onglet Parcours et UI) ; résumé au tableau de bord ;
  outil MCP `coverage_ui` (83 outils).

## 2026-11-16 — V2 phase 4 : Test Design par catégories, doublons
- Cas proposés pour 9 catégories à partir des critères, règles, champs, messages, transitions et rôles du graphe ;
  observé / déduit, confiance et manques explicites ; règles déterministes (pas d'IA requise).
- Doublons sur titre, étapes, préconditions, résultats attendus et texte complet ; seuils réutiliser 0,70 / faire
  évoluer 0,40 ; similarité du moteur de Coverage Intelligence (aucun second moteur).
- 2 outils MCP ajoutés (85).

## 2026-11-16 — V2 phase 5 : Champ et Anomalie dans le Knowledge Graph
- Champ = composant de genre « champ » (pas de nouveau type de nœud) ; Anomalie = nœud « bug » enrichi par Failure
  Analysis. Relations ajoutées : possede, concerne, detecte_par, associe_a.
- Un lien champ ↔ règle déduit du texte reste « à valider » ; une anomalie sans clé Jira n'est jamais créée dans Jira.
- Failure Analysis enregistre le contexte de l'anomalie à la décision (jamais bloquant).
- 2 outils MCP ajoutés (87).

## 2026-11-16 — V2 phase 6 : échecs reliés à la connaissance
- Localisation d'un échec (écran, composant) calculée une fois et mémorisée ; étape sans locator = « sans écran »,
  jamais deviné.
- Régression = réussi au run précédent puis échec ; récurrente = ≥ 2 sur le même composant (ou test), runs différents.
- Lecture seule : aucune décision ni anomalie créée ; outil MCP `failure_connaissance` (88).
