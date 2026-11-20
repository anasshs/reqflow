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

## 2026-11-16 — V2 phase 7 : consolidation
- Client MCP de test (`tests/client_mcp.py`) : lance le serveur comme Cursor ; scénario de bout en bout (parcours,
  suspension, reprise, décisions humaines dans le web) et contrat des 88 outils vérifiés par ce client.
- Registre de sécurité (`tests/test_securite_outils.py`) : tout outil MCP doit être classé (lecture, proposition,
  action, écriture locale, écriture externe) ; aucun outil git / fusion, aucune décision humaine par MCP.
- Bilan des critères de succès et limites connues : `docs/V2_BILAN.md`.

## 2026-11-16 — Squads : une seule source, la Politique des US

- Les squads (projets Jira des équipes) se déclaraient à deux endroits : Paramètres › Configuration › Politique des US
  (par application) et Paramètres › Périmètre (par projet, niveau « squad »). La synchronisation n'allait que dans un
  sens et les deux listes avaient divergé ; les squads du périmètre n'entraient dans aucun calcul.
- La Politique des US est désormais la seule source des squads. Le niveau « squad » et le champ « projet Jira de la
  squad » sont retirés du périmètre ; « Ajouter des squads » est remplacé par un rappel des squads de la politique.
  Les squads déjà déclarées dans le périmètre sont reprises dans la politique par une action explicite (« Reprendre dans
  la politique et retirer d'ici », `POST /api/strategie/squads/reprendre`), journalisée ; la route
  `POST /api/strategie/squads` est supprimée.
- Paramètres › Périmètre devient « Exclusions et criticité » : il ne garde que ce qu'il est seul à faire (exigences et
  modules exclus de la couverture, criticité des modules pour le risque). L'adresse `#parametres/perimetre` est conservée.
- La JQL des exigences enregistrée est signalée « figée » : elle ne suit plus la politique des US ; un bouton permet de
  revenir à la JQL déduite (`jql_deduite` exposée par `/api/couverture/reglages`).
- Reste ouvert : le référentiel (exclusions, criticité) est par projet, la politique par application.

## 2026-11-16 — Performances : trois caches, résultats inchangés

Mesures sur le projet TAM (465 exigences, 3 429 tests, instantané Xray de 2,3 Mo), avant → après, résultats
comparés à une référence capturée avant modification (identiques) :
Cerveau 28 s → 2,2 s ; qualité documentaire 22 s → 0,3 s ; stratégie 1,2 s → 0,2 s ; anomalies 0,8 s → 0,1 s.
- Découpage des textes (`intelligence_couverture.jetons`) mémorisé par texte, et détection des doublons qui
  découpe chaque exigence une seule fois : la boucle n² redécoupait les mêmes textes 216 000 fois.
- Instantané Xray (`patrimoine_xray.charger`, `charger_vue`) en cache, clé = chemin + taille + CRC32 du contenu
  (la date de modification avance par pas de ~15 ms sous Windows). Chaque appel reçoit une copie (pickle) : un
  appelant qui modifie ce qu'il lit n'altère jamais le cache. Vue filtrée gardée par filtre d'application.
- Graphe de connaissance (`connaissance.construire`) en cache tant que l'empreinte du projet (chemin, taille, date
  de chaque fichier, variables de réglage) ne change pas ; pas de cache si un fichier a été modifié depuis moins de
  2 s ; un seul calcul à la fois (les requêtes parallèles attendent au lieu de recalculer) ; copie par appel.
  Un inventaire fourni par l'appelant contourne le cache.
- Pas de base de données ni de dépendance ajoutée (bibliothèque standard : functools, pickle, zlib, hashlib).

## 2026-11-16 — Console Cursor et granularité des tests

- Console Cursor (`static/console_agent.js`, flottante sur tous les écrans) : chaque appel MCP décrit en français
  (`activite_agent.decrire`, phrase dédiée ou première phrase de la documentation de l'outil), règles `.mdc` du projet
  qui citent l'outil (`regles_cursor.regles_par_outil`, lecture seule), client MCP (poignée de main), identifiant
  d'appel (début / fin reliés). Le protocole MCP ne transmet pas le modèle : nouvel outil `agent_annoncer` (89 outils,
  classé lecture, n'écrit rien) que la règle `mcp-usage.mdc` demande d'appeler à chaque tâche (intention, modèle, étape).
- US à couvrir : panneau en trois tailles (normal, large, plein écran, mémorisé dans le navigateur), onglets, cas
  filtrables, US précédente / suivante.
- Granularité (`intelligence/granularite_tests.py`) : un test = un objectif ; indicateur « comportements couverts par
  test » (champ `couvre` des cas, sinon leur titre) au lieu du nombre de tests. Regroupement « données » (un test, une
  variante par cas, plan du scénario) ou « contrôle » (points de contrôle) : toujours décidé par l'automaticien, cas
  d'origine « Regroupé » (jamais supprimés), réversible avant publication. Suggestions par règles explicables,
  volontairement prudentes ; deux cas au résultat opposé (forme négative d'un seul côté) ne sont jamais regroupés.
  Les regroupements de sens reviennent à Cursor (règle `test-design.mdc` : minimum de tests couvrant tous les
  comportements, `couvre` par cas) ou à l'automaticien. Contrat des 76 outils historiques inchangé.
- Révision le même jour : décider que deux cas ont le même objectif est un jugement sur le sens, que les règles (mots
  communs) ne savent pas faire (sur une US réelle : un regroupement trouvé sur trois ou quatre, et un premier essai qui
  rapprochait « éligible » et « non éligible »). Les suggestions passent donc à l'IA : deux outils MCP (91 outils)
  `test_design_cas_us` (lecture : US masquée, cas regroupables avec identifiants, consigne) et
  `test_design_proposer_regroupements` (proposition : cas, mode, titre, justification obligatoire, couvre ; contrôlée
  côté serveur, refus motivés renvoyés à l'agent) ; avec un LLM interne ou Claude, `consolider_ia` (appel direct, texte
  masqué). Les règles restent en secours quand l'IA est désactivée, affichées « sans compréhension du texte ». Dans
  tous les cas l'atelier ne fait que proposer : l'automaticien applique ou écarte ; la mécanique (test regroupé, cas
  « Regroupé », retour arrière, indicateur) reste dans l'atelier.

## 2026-11-17 — Jugements sur le sens délégués à Cursor (même modèle que la granularité)
- Constat : cinq analyses décidaient du SENS d'un texte en ne comparant que des mots — doublons de Test Design
  (Jaccard / recouvrement → réutiliser, faire évoluer, créer), tests Xray redondants (Jaccard des titres), liens
  exigence ↔ test (TF-IDF, module, libellés), classement des tests orphelins, corrélation écran ↔ exigence (mots
  communs). Elles confondent un résultat opposé avec un doublon et ratent une reformulation.
- Décision : partage unique, décrit dans `atelier/intelligence/jugement_ia.py` — les règles présélectionnent (rappel
  large, explicable) ; l'IA juge, justification obligatoire ; le serveur contrôle chaque jugement (objets connus,
  verdict connu, lien ni existant ni déjà rejeté…) et renvoie des refus motivés ; l'automaticien décide. Rien n'est
  appliqué, lié, supprimé ni écrit dans Jira / Xray par l'IA.
- Dix outils MCP (101 au total, contrat des 76 historiques inchangé), une lecture et un dépôt par analyse :
  `test_design_doublons_a_juger` / `test_design_juger_doublons`, `xray_redondances_a_juger` / `xray_juger_redondances`,
  `coverage_liens_a_juger` / `coverage_juger_liens`, `coverage_orphelins_a_classer` / `coverage_classer_orphelins`,
  `discovery_correlations_a_juger` / `discovery_juger_correlations`. Lectures « L », dépôts « P » (registre de sécurité).
- Avec un LLM interne ou Claude : même lecture, appel direct (texte masqué), même dépôt contrôlé. Avec « cursor »,
  l'atelier n'appelle rien : bouton « Demander à Cursor » (demande à copier) et rafraîchissement dès le dépôt.
- Les jugements se superposent aux règles sans les effacer : verdict et justification affichés à côté de la
  présélection (« règles, sans compréhension du texte ») ; une paire jugée « distincts » reste visible.
- Restent aux règles : diagnostic de base des échecs (motifs techniques fiables), indicateurs et comptages, classement
  de sécurité des actions et droits des rôles (invariants, jamais confiés à un LLM).

## 2026-11-17 — Correctifs : poste Windows et relecture des jugements délégués
- Chemins du projet : toujours avec « / » (`relative_to(...).as_posix()`), sous Windows comme sous Linux. Ce sont des
  clés (suite en revue, nœuds du graphe, historique) : avec « \ », une suite nommée `tests/x.robot` par Cursor ou par
  l'interface était « inconnue ». Les imports `Resource` générés suivent la même règle (dans Robot Framework, « \ »
  est le caractère d'échappement).
- Arrêt d'un run sous Windows : un sous-processus ne peut pas recevoir SIGINT ; le run est interrompu
  (`terminate`), le bilan dit « arrêté », le rapport du test en cours peut manquer. Linux / macOS : inchangé.
- Rapport Robot vide ou tronqué (arrêt, délai dépassé, plantage) : l'historique reste consultable (aucun test listé),
  le bilan garde la console et signale `rapport_illisible`.
- Journal Xray : une ligne coupée au milieu d'un caractère accentué est ignorée comme toute ligne tronquée.
- Descriptions des outils MCP : indentation du code retirée (`inspect.cleandoc`), identique à Python 3.13.
- Sorties de sous-processus (git, adb, Robot) : décodage sans erreur fatale ; git lu en UTF-8.
- Relecture indépendante du commit des jugements délégués, constats corrigés : le panneau d'une US n'est plus
  réaffiché pendant une saisie, pour une autre US, sur un événement rejoué ou hors écran ; les lots à juger avancent
  (ce qui est déjà jugé passe en dernier, les paires écartées sont mémorisées dans `liens_ecartes.json`) ; le
  recalcul des doublons par règles garde le verdict de l'IA ; une référence d'écran vide est refusée ; les règles de
  granularité ne remplacent plus les propositions d'une IA ni l'historique ; un classement déjà décidé n'est pas
  compté comme déposé ; écriture atomique avec un fichier temporaire par écriture.
- Tests propres à Linux (droits 0600 du fichier de jeton, lien symbolique) : adaptés, pas le code.

## 2026-11-17 — Serveur MCP en HTTP pour une équipe Cursor qui n'autorise que des URL
- Contexte : l'administrateur de l'équipe Cursor bloque les serveurs MCP absents de sa liste blanche (« blocked by
  team admin ») ; la liste contient déjà l'URL `http://localhost:8000/mcp`, pas la commande `python server.py`.
- `MCP_HTTP_PORT` (ex. 8000) : l'interface démarre elle-même `server.py --http` (HTTP « streamable » du SDK MCP,
  chemin `/mcp`), écoute 127.0.0.1 uniquement, protection DNS rebinding du SDK (hôte étranger refusé : 421). Le
  serveur est arrêté avec l'interface, y compris si elle est tuée (fin du flux stdin surveillée).
- « Installer dans Cursor » écrit alors `{"url": "http://localhost:<port>/mcp"}` ; « Tester le serveur MCP » interroge
  cette URL. Claude Desktop reste en stdio. Sans `MCP_HTTP_PORT`, rien ne change (Cursor lance server.py).
- Limite : l'interface doit rester ouverte pendant que Cursor travaille ; un autre programme sur le port l'empêche
  de démarrer (signalé par le test de connexion). Aucune dépendance ajoutée (SDK `mcp` déjà présent).

## 2026-11-17 — Suivi des demandes à Cursor, graphe de couverture, « Je prends »
- Suivi des demandes à Cursor (suivi_cursor.js) : chaque « Demander à Cursor » (Copier / Ouvrir dans Cursor) ouvre une
  carte flottante : temps écoulé, prise en compte (premier appel MCP après l'envoi), appels et dernière action, résultat
  déposé (fin d'un outil de dépôt attendu, passé par l'écran appelant). Aides : aucun signe après 2 min, silence de
  3 min (Cursor attend une réponse ou une confirmation dans son chat). Appels rattachés à la demande ouverte la plus
  récente (un agent par poste). Rien n'est envoyé à Cursor par l'atelier : suivi en lecture des événements MCP.
- Graphe › Couverture : adresse #graphe/couverture/test/<clé> (Test Design › Traçabilité) ou /module/<nom> ; le test
  est sélectionné et centré, la liste des modules reflète le module affiché ; une couche de plus de 12 éléments est
  repliée sur plusieurs lignes ; vue sans module tronquée signalée ; le bandeau BDD ne montre plus le scénario d'un
  autre test.
- Test Design › À concevoir : BDD (Cucumber) en priorité pour la création dans Xray — Gherkin du cas s'il est prêt,
  sinon tiré de ses étapes ; étapes manuelles seulement en secours. Le type de test de l'espace n'impose plus le
  format. « Je prends » (un cas ou une multi-sélection) = enregistrer, valider, créer dans Xray et lier à l'US en une
  confirmation ; un cas non prêt est refusé avec sa raison, les autres partent. « Je ne prends pas » = rejet motivé
  (un motif pour la sélection).

## 2026-11-17 — Refonte du Knowledge Graph, phase 1 : ontologie et relations typées
- Spécification de l'utilisateur : trois univers (Business, Testing, Application), relations métier typées à la place des
  « contient » génériques, provenance sur chaque relation. Analyse préalable et plan : docs/REFONTE_KNOWLEDGE_GRAPH.md.
- Phase 1 = traduction sans perte, pas de réécriture : les moteurs construisent toujours le graphe historique (lu par
  couverture, impact, plan de test, outils MCP) ; `atelier/domain/ontologie.py` le traduit vers le modèle cible par
  PAIRE de types (un « contient » devient INCLUDED_IN_PLAN, BELONGS_TO, PARENT_OF… selon ce qu'il relie), en inversant
  le sens quand le métier l'exige (Test VERIFIES Story). Bascule des modules : phases suivantes, un par un.
- Décisions prises par défaut (recommandations acceptées) : composant Jira = BusinessModule ; identifiants `jira:<clé>` /
  `xray:<clé>` ; stockage `graph_nodes` / `graph_edges` reporté à la phase 5 (SQLite local recommandé, Supabase écarté
  tant que la sécurité ne l'a pas validé : données de la banque hors du poste).
- Provenance : observé = OFFICIAL ; déclaré ou proposition validée = VALIDATED ; déduit non validé = PROPOSED. Confiance
  d'une proposition = valeur calculée, sinon vide (aucune confiance inventée). Systèmes ajoutés à la liste de la
  spécification : USER_DECLARATION (saisie humaine) et API_CONTRACT (contrat OpenAPI).
- Extensions du vocabulaire (15 relations, 11 types) marquées « extension » et comptées dans le rapport de migration.

## 2026-11-18 — Graphe : Fonctionnel, Technique et Parcours utilisateur deviennent un filtre
- Les trois onglets n'affichaient qu'une partie du graphe principal (même route, autres types) : ils sont fusionnés en
  un filtre « Afficher » de l'onglet « Graphe de connaissances » (Tout le graphe, Fonctionnel, Technique, Parcours
  utilisateur). Il reste cinq onglets : Graphe de connaissances, Construction BDD, Couverture, Flux, Impact.
- Adresse : `#graphe/connaissance/<angle>` ; les anciennes adresses `#graphe/fonctionnel`, `/technique`, `/parcours`
  y mènent toujours. Le filtre est retrouvé en revenant d'un autre onglet du graphe, pas depuis un autre écran.
- Sur le graphe complet, le filtre est appliqué par le serveur (avant le plafond d'affichage) ; autour d'un élément
  exploré, il masque les voisins des autres types, l'élément exploré restant affiché. Aucune route ni outil MCP modifié.

## 2026-11-18 — Corrélation exigences ↔ écrans : « vérifiée sur » et « réalisé par »
- Décision de l'utilisateur : deux relations distinctes. « Vérifiée sur » = preuve issue des tests, créée seule par le
  graphe (écran → locators → scripts Robot → clé Xray → exigence), avec ses preuves. « Réalisé par » = association
  fonctionnelle, active seulement après une décision humaine (preuve promue, proposition d'une IA confirmée, lien manuel).
  Détail : docs/CORRELATION_EXIGENCES_ECRANS.md.
- Pourquoi : un test de bout en bout traverse la connexion et l'accueil ; relier ces écrans à toutes les exigences
  fabriquerait de la couverture fonctionnelle. La preuve de test reste un fait, exclu de la couverture et du périmètre.
- Prérequis imposé par le serveur : l'écran doit être dans la carte (vu pendant une Discovery) ; un écran connu du seul
  dépôt n'est pas reliable. « Vérifiée sur » ne se déclare pas à la main.
- Verdict « incertain », preuves et estimation (faible, moyenne, forte) ajoutés au jugement d'une IA ; l'estimation est
  indicative, jamais calculée. Rejet humain mémorisé : la proposition n'est plus proposée ni redéposable.
- Écarts assumés avec la spécification : sens Exigence → Écran (lecture « réalisé par ») ; aucune capture transmise à
  une IA (aucune n'est conservée) ; auteur = session du poste, rôles d'Automation Studio pas encore appliqués à ces décisions ; stockage durable des relations
  reporté à la phase 5 de la refonte (un journal consigne les preuves perdues).
- Aucun outil MCP ajouté ; `discovery_juger_correlations` garde sa signature (champs facultatifs en plus).

## 2026-11-18 — Transition des applications mobiles vers les testTag (Jetpack Compose)
- Contexte : les applications mobiles passent aux testTag. Un testTag (avec `testTagsAsResourceId = true`) est lu comme
  un resource-id SANS « package:id/ ». Le locator `id=` d'Appium complète le nom avec le package de l'application et ne
  le trouve pas, sauf réglage `disableIdLocatorAutocompletion`. L'atelier génère donc pour ces identifiants
  `android=new UiSelector().resourceId("<tag>")`, qui marche sans réglage ; un resource-id complet garde `id=`.
- La clé métier d'un élément ne change pas quand son identifiant arrive ou change de nom : l'élément observé est rattaché
  à l'élément déjà cartographié de même type qui partage un locator (texte, position relative au libellé). Un tag nommé
  comme la clé (« champ_montant ») redonne directement cette clé : c'est le tag que propose `map_tags_report`.
- L'écran est reconnu par ses libellés quand ses identifiants arrivent (son empreinte passait de 100 % à moins de 30 %
  de ressemblance, donc un doublon) ; son empreinte passe aux identifiants, changement « identifiants » consigné.
- Le Studio classe ces locators « Stable ». Fixture : tests/fixtures/hierarchies/android_compose_testtag.xml.
- Identifiant RENOMMÉ (« id=…:id/valider » ou un testTag devient « Sp_valider_btn ») : rejoué, l'écran était pris pour un
  nouvel écran. Il est maintenant reconnu par ses libellés et son titre (seuil plus exigeant, 0,85), l'élément par un
  locator commun ou, à défaut, par son libellé s'il est unique ; l'ancien identifiant, disparu de l'application, est
  retiré (changement « identifiant_remplace »). Un champ identifié garde en secours l'ancre « libellé qui précède ».
  Limite assumée : un champ sans libellé propre n'est pas rapproché (rien n'est deviné). Le Studio propose aussi le
  testTag pour un locator repéré par son texte. Fixtures : android_compose_testtag_renomme, android_classique_vers_compose.
- Non vérifié sur un vrai build Compose ni avec un vrai Appium : le comportement d'Appium vient de la documentation et
  des retours de la communauté, à confirmer à la première livraison avec testTag.

## 2026-11-18 — Réutilisation des keywords dès la rédaction des étapes BDD
- Constat : la réutilisation n'était garantie qu'à l'assemblage (`studio_construire_test`). À la génération depuis un
  scénario BDD, une étape reformulée (« je valide le virement » pour le keyword « Valider Le Virement ») était classée
  « à créer » et un keyword en double était déclaré dans la suite.
- Moteur `atelier/generation/reutilisation.py` (sans IA, bibliothèque standard) : chaque étape est « existant » (même
  nom, ou keyword à arguments intégrés, reconnu comme le fait Robot), « proche » (mêmes mots significatifs, radicaux de
  5 lettres, au moins 60 % en commun ; les négations comptent) ou « à créer ». Inventaire du dépôt gardé en mémoire tant
  qu'aucun .robot / .resource ne change.
- Test Design : contrôle « keyword_proche » (gravité moyenne), pastille par étape (socle / doublon ? / à créer), bouton
  « Reprendre » le keyword proposé, saisie assistée par la liste des keywords du socle. La décision reste humaine :
  reprendre le keyword, ou confirmer un nouveau keyword (`keyword_nouveau` dans le modèle, remis en jeu si le texte change).
- Garde : l'écriture de la suite générée (atelier et `studio_generer_depuis_bdd`) est refusée tant qu'une étape proche
  d'un keyword existant n'est pas tranchée. L'aperçu reste possible et nomme les doublons probables.
- Revue technique : contrôle « doublons_keywords » (keyword défini dans le script, proche ou homonyme d'un keyword d'un
  autre fichier).
- Cursor : outil de lecture `studio_rapprocher_etapes` (102 outils, contrat des 76 historiques inchangé) ; règles
  test-design, automatisation et mcp-usage complétées ; `studio_scenario_bdd` renvoie les keywords proches par étape.
- Limites assumées : la comparaison ne lit que des mots (un synonyme, « confirmer » pour « valider », n'est pas vu ;
  un faux rapprochement se lève en confirmant le nouveau keyword) ; les keywords des bibliothèques Python ne sont pas
  inventoriés ; `write_project_file` reste libre, c'est la revue technique qui signale le doublon.

## 2026-11-18 — Keywords en double : jugement délégué à Cursor (ou à l'IA en appel direct)
- Les synonymes échappent à la comparaison de mots. Même partage que les autres jugements (jugement_ia.py) : lecture
  `studio_keywords_a_juger(cle)` (étapes sans keyword, candidats présélectionnés avec leur corps, nom de tous les keywords
  du dépôt), dépôt `studio_juger_keywords(cle, jugements)` : verdict reutiliser | creer, keyword cité, justification.
  104 outils MCP. Appel direct (LLM interne / Claude) : `reutilisation.juger_keywords_ia`, mêmes contrôles.
- Contrôles du serveur : étape jugeable (sans keyword existant, sans décision humaine), verdict connu, keyword cité
  présent dans le dépôt, justification ; refus motivés renvoyés à l'agent.
- Effet : un verdict « réutiliser » rend l'étape « doublon ? » comme un rapprochement par les mots (contrôle, pastille,
  écriture de la suite refusée) ; l'automaticien reprend le keyword ou confirme un nouveau keyword. Un verdict « créer »
  est affiché mais ne lève jamais un doublon vu par les mots. L'IA ne réécrit aucune étape et ne crée aucun keyword.
- Jugements et décisions valent pour toutes les étapes de même texte (une branche copie les étapes communes) ; un texte
  modifié les remet en jeu. Contrôle d'information « keywords_a_juger » tant que des étapes « à créer » n'ont pas été jugées.
- Limite assumée : le jugement n'est pas exigé avant l'écriture (un scénario sans IA disponible resterait bloqué) ; c'est
  le contrôle d'information et les règles Cursor qui le demandent.

## 2026-11-18 — Discovery Data Setup : référentiel universel de données
- Demande : un référentiel de variables indépendant du métier, que Cursor consulte pendant le Discovery. Détail :
  docs/DISCOVERY_DATA_SETUP.md. Moteur `atelier/discovery/donnees.py`, bibliothèque standard seulement.
- Définition, valeur, source, contexte et historique sont cinq fichiers distincts ; une même variable a une valeur par
  défaut, par environnement et par profil.
- L'agent lit, demande et enrichit le contexte de sa session ; il n'écrit jamais le catalogue (rôle automaticien). Une
  valeur confidentielle ou secrète ne lui est jamais renvoyée : saisie par référence `{{var:CLE}}` dans `type_text`
  (signature inchangée), résolue côté serveur, jamais publiée dans les événements.
- Champ sans variable : « manquante » par défaut ; générateur possible par type de champ si l'automaticien l'autorise.
- Formules : arithmétique seule, évaluée sur l'arbre syntaxique (aucun nom, aucun appel). Fichiers : projet de tests
  seulement (`safe_path`). API et requêtes : mécanismes gardés des jeux de données, réutilisés tels quels.
- 5 outils MCP (109 au total, contrat des 76 historiques inchangé) ; règles discovery et mcp-usage complétées.
- Les jeux de données existants (`data/jdd`) ne sont pas migrés : ils restent la source des tests Robot.

## 2026-11-18 — Variables du Discovery dans le graphe, les parcours et le journal de session
- Accord de l'utilisateur : brancher les trois, en gardant le référentiel (exploration) séparé des jeux de données des
  tests Robot (`data/jdd`), qui restent la source des scripts.
- Graphe : type de nœud `variable` (cible `DataVariable`, extension), jamais de valeur ; liens observés écran / champ →
  variable, dépendances, lien déduit parcours → variable. Journal de session : événements « donnee ».
- Parcours → BDD : l'étape de saisie cite et garde la variable utilisée ; le script généré ne change pas.
- Aucun lien deviné : un locator présent sur plusieurs écrans n'est rattaché que si l'agent a nommé l'écran.

## 2026-11-18 — Envoyer une demande à Cursor sans quitter l'atelier
- Constat de l'utilisateur : cliquer « Ouvrir dans Cursor » à chaque demande n'est pas pratique. L'atelier ne peut pas
  écrire dans le chat de Cursor ; deux voies ajoutées, le lien restant en secours (`atelier/integrations/boite_cursor.py`).
- Boîte de demandes : la demande est déposée, Cursor vient la chercher par le MCP (`atelier_demande_suivante`, qui attend
  40 s au plus puis rend la main, et `atelier_demande_terminee`). L'automaticien dit une fois « traite les demandes de
  l'atelier » ; la règle mcp-usage décrit la boucle. 111 outils MCP.
- Ligne de commande : l'atelier lance l'agent Cursor sans fenêtre dans le projet de tests. Commande et arguments
  réglables (`ATELIER_CURSOR_CLI`, `ATELIER_CURSOR_CLI_ARGS`, `ATELIER_CURSOR_CLI_DELAI`), liste d'arguments sans shell.
  Par défaut sans `--force` : l'agent passe par les outils MCP, qui gardent leurs contrôles.
- Le choix se mémorise sur le poste (panneau « Demandes à Cursor » › Envoi) : les demandes suivantes partent d'un clic.
- Une demande de la boîte vaut une demande tapée dans le chat et ne donne aucun droit de plus.
- Non vérifié : les options de la ligne de commande de Cursor viennent d'une recherche web du 2026-11-18 (la
  documentation officielle n'était pas joignable d'ici) et n'ont pas été essayées avec un vrai Cursor ; ni la tenue de
  la boucle d'écoute dans un vrai chat (durée maximale d'un outil, nombre d'appels par tour). Un administrateur
  d'équipe Cursor peut interdire le mode sans fenêtre.

## 2026-11-18 — Envoi des demandes à Cursor : un seul réglage, une fenêtre allégée
- Demande de l'utilisateur : pas de boutons en plus ; le mode se choisit une fois dans les paramètres ; pour
  l'exploration le chat convient, à condition d'alléger la fenêtre.
- Le mode d'envoi (lien, boîte, ligne de commande) se règle dans Paramètres › Cursor / Claude et vaut pour tout le projet
  (`atelier_cursor.yaml`, versionné ; rôle automaticien). Le choix par clic, la préférence par navigateur et le bouton
  « Envoi » du panneau de suivi sont retirés.
- « Demander à Cursor » : en mode boîte ou ligne de commande, la demande part d'un clic, sans fenêtre ; si l'envoi
  échoue (commande absente sur ce poste), la fenêtre du chat s'ouvre.
- Fenêtre du chat : la demande, une ligne, « Copier » et « Ouvrir dans Cursor ». L'explication et la note de suivi ne
  sont plus affichées.
- Exploration : un bouton « Explorer avec Cursor » dans Discovery › Explorer, toujours par le chat quel que soit le
  réglage (l'automaticien doit voir l'agent, lui répondre et faire les actions sensibles).
- Le mode « ligne de commande » est refusé à l'enregistrement tant que la commande manque sur le poste qui règle ; un
  autre poste sans la commande retombe sur le chat.

## 2026-11-18 — Environnements lus dans le projet Xray
- Décision de l'utilisateur : les environnements viennent du projet Xray ; le champ « Environnements » est retiré des
  paramètres du projet (une valeur encore présente dans un projet enregistré est ignorée).
- Lecture (`XrayClient.environnements`, `atelier/integrations/xray/environnements.py`), par introspection comme le reste
  du client : paramètres du projet Xray (`getProjectSettings › testEnvironments`), à défaut les environnements des
  100 dernières Test Executions. Lecture seule. Liste gardée dans `studio/environnements_xray.json` avec date et source.
- Le sélecteur d'environnement du haut, Discovery › Données et Paramètres › Projets lisent cette liste. Relecture en
  arrière-plan quand elle manque ou date de plus de 12 h ; bouton « Actualiser depuis Xray » dans Paramètres › Projets.
- Xray indisponible ou non configuré : la dernière liste lue reste ; sans aucune lecture, les environnements des
  fichiers de jeux de données servent de secours, présentés comme tels.
- Un environnement Xray retrouve son fichier de jeux de données sans tenir compte de la casse ; un environnement sans
  fichier est affiché « sans données », un fichier sans environnement Xray est signalé.
- Non vérifié sur un vrai Xray : `getProjectSettings` et `ProjectSettings.testEnvironments` n'ont pas été introspectés
  d'ici (un forum Atlassian cite le type et le champ). S'ils manquent, c'est dit dans « absents » et la seconde lecture
  sert. À confirmer et consigner dans docs/XRAY_API.md au premier essai réel.

## 2026-11-18 — Dashboard de pilotage (aide à la décision)
- Cahier de l'utilisateur : passer du reporting à « que faire maintenant ? ». Détail et écarts : docs/DASHBOARD_PILOTAGE.md.
- Le Dashboard n'a aucune donnée propre : `atelier/intelligence/pilotage.py` agrège les copies locales (aucun appel
  Jira, Xray ou GitLab au chargement), zone par zone pour un affichage progressif. Seuls sont à lui : l'instantané
  quotidien des indicateurs, les décisions TNR et les critères de livraison (`pilotage/`).
- Jamais d'estimation : une mesure impossible est « indisponible » avec sa raison. Bloqué et non exécuté ne sont pas
  des échecs. Une proposition non validée n'alimente aucun indicateur.
- TNR : évolutions → analyse d'impact (relations fiables) → obligatoires / complémentaires / sécurité fonctionnelle, avec
  le motif ; le responsable accepte, écarte en justifiant, ajoute ; campagne TNR créée dans Execution Center.
- Recommandations : règles sur des faits, sans génération par une IA.
- L'import des bugs des exécutions lit en plus priorité, responsable, création et résolution (lecture seule Jira).
- L'ancien Dashboard devient « Suivi des runs » (#operations).

## 2026-11-18 — Mapping des statuts des tickets, par projet
- Demande de l'utilisateur : un mapping des statuts des tickets Test, Test Execution, Test Plan et Bug, dans les
  paramètres, par projet et non par application.
- `atelier/domain/statuts.py`, fichier `atelier_statuts.yaml` du repository de tests (versionné, commun à toutes les
  applications du projet). Écran : Paramètres › Statuts des tickets. Le nom Jira de chaque type de ticket est réglable.
- Chaque statut du workflow est relié à une catégorie de l'atelier (test : étapes du cycle de vie + obsolète ; exécution :
  à faire, en cours, terminée, annulée ; plan : à faire, en cours, clôturé, annulé ; bug : ouvert, en cours, résolu,
  fermé, réouvert, rejeté). Statuts proposés : ceux des copies locales, et ceux lus dans Jira à la demande (lecture seule).
- Effets : plan clôturé (Execution Center), bug ouvert / réouvert / rejeté et exécution ouverte (Dashboard), statut Jira
  appliqué par le cycle de vie d'un test quand il n'est pas réglé dans Xray Mapping. Un bug rejeté sort des comptes.
- Un statut non relié garde l'ancien repli (catégorie « terminé » de Jira, puis nom du statut) et reste signalé : aucun
  projet existant ne change de comportement tant qu'il n'a rien réglé.
- Non modifié : les statuts de la revue de conception restent dans Test Design › Xray Mapping ; les statuts des test runs
  Xray (PASSED, FAILED…) ne font pas partie de ce mapping.

## 2026-11-18 — Cursor en ligne de commande sous Windows : la demande passe par un fichier
- Sous Windows, la commande « agent » de Cursor est un lanceur de script (.cmd / .ps1). Un défaut connu de ce lanceur
  retire les guillemets et recolle des arguments ; plus largement, un argument passé à un script traverse
  l'interpréteur de commandes, qui réinterprète « " », « % », « & », « | ».
- Quand la commande trouvée est un tel lanceur, l'atelier écrit la demande dans `studio/demandes_cursor/<id>.md` et ne
  passe en argument qu'une consigne courte, sans caractère spécial, qui dit de lire ce fichier. Sur un exécutable
  (macOS, Linux, .exe), rien ne change : la demande reste un argument, sans shell.
- Non essayé avec un vrai Cursor sous Windows : installation `irm 'https://cursor.com/install?win32=true' | iex` relevée
  dans la documentation publique ; à confirmer sur le poste.

## 2026-11-18 — « Cursor est l'IA de l'atelier » réglable dans les paramètres
- Constat de l'utilisateur : après avoir connecté Cursor, les boutons « Demander à Cursor » restaient absents. Ils
  dépendent du fournisseur d'IA, jusqu'ici fixé par la seule variable IA_FOURNISSEUR à définir avant le lancement.
- Sans variable, le projet peut maintenant choisir Cursor dans Paramètres › Cursor / Claude (`ia: cursor` dans
  `atelier_cursor.yaml`, à côté du mode d'envoi). La variable, quand elle est définie, s'impose et le réglage du projet
  ne peut pas la contourner.
- Seul « cursor » se règle ainsi : avec lui l'atelier n'appelle aucun modèle. « interne » et « anthropic » demandent
  une URL ou une clé et restent réglés par variables d'environnement.

## 2026-11-19 — Suivi des demandes : l'état réel d'une demande déposée
- Constat de l'utilisateur : demande envoyée, panneau bloqué sur « En attente de Cursor », rien dans le chat de Cursor.
  Le panneau ne lisait que l'activité MCP : une demande restée dans la boîte (Cursor n'écoute pas) ou un lancement en
  ligne de commande en échec étaient muets.
- Le panneau lit maintenant l'état de la demande déposée (toutes les 4 s tant qu'elle n'est pas finie) : dans la boîte
  et Cursor n'écoute pas (avec la phrase à lui dire), prise, terminée avec son compte rendu, échec avec la raison
  rendue par la ligne de commande. En ligne de commande, il dit que rien n'apparaîtra dans le chat de Cursor.

## 2026-11-19 — Ligne de commande de Cursor : serveur approuvé et outils autorisés, vérifiés par l'atelier
- Constats de l'utilisateur, sur son poste : `agent mcp list` rendait « appium-robot: not loaded (needs approval) »
  malgré l'option `--approve-mcps` ; une fois le serveur approuvé à la main (`agent mcp enable appium-robot`), la
  demande aboutissait mais chaque appel d'outil de l'atelier était refusé, donc rien n'était déposé.
- Cause : sans fenêtre, personne ne peut approuver un appel d'outil. Deux conditions distinctes : serveur MCP approuvé
  pour la ligne de commande (par poste) ; outils autorisés dans `.cursor/cli.json` du projet de tests.
- Paramètres › Cursor / Claude, étape 4, en mode ligne de commande : « Vérifier la ligne de commande » lance
  `agent mcp list` dans le projet (sans shell) et dit si le serveur est chargé, à approuver (avec la commande à taper)
  ou inconnu ; « Autoriser les outils de l'atelier » ajoute le jeton `Mcp(appium-robot:*)` à `.cursor/cli.json`, les
  autres permissions étant conservées, un fichier illisible n'étant jamais écrasé.
- `--force` reste écarté : il autoriserait aussi les commandes du poste et l'écriture de fichiers. Seuls les outils de
  l'atelier, eux-mêmes bornés par les invariants de sécurité, sont autorisés.
- Non vérifié sur la documentation officielle (cursor.com inaccessible depuis la session) : la syntaxe du jeton vient
  d'une recherche web, et un retour du forum Cursor signale qu'une liste d'autorisation n'a pas toujours suffi en mode
  sans fenêtre. À confirmer par l'essai réel de l'utilisateur.

## 2026-11-19 — Ligne de commande de Cursor : option --force, choix explicite de l'automaticien
- Essai réel de l'utilisateur sur son poste : la même demande (appel de `cursor_regles`) est refusée avec
  `--approve-mcps --trust`, et aboutit avec `--force` en plus. L'essai a été fait depuis le dossier de l'atelier : il ne
  prouve pas que l'autorisation ciblée de `.cursor/cli.json` est ignorée, seulement que `--force` suffit.
- Décision : `--force` reste absent par défaut. Une case de Paramètres › Cursor / Claude (étape 4) l'ajoute pour le
  projet (`cli_force` dans `atelier_cursor.yaml`), avec l'avertissement : l'agent peut alors aussi lancer des commandes
  du poste et écrire des fichiers sans demander. Rôle automaticien exigé.

## 2026-11-19 — « Générer le script Robot » de Test Design mène à Automation Studio
- Constat de l'utilisateur : dans Construction BDD, le bouton générait le script sur place (calcul local, sans Cursor),
  avec des keywords vides pour les étapes sans keyword, puis ouvrait l'éditeur de code. Rien ne menait à Automation
  Studio, où Cursor construit le test.
- Décision : le bouton ouvre Automation Studio › BDD → Robot (mapping) sur le scénario en cours. Test Design conçoit,
  Automation Studio automatise.
- Sur cet écran : « Faire construire par Cursor » (keywords manquants créés dans le socle, dry run, soumission en revue)
  et « Générer le script Robot » (aperçu puis écriture, jamais d'écrasement implicite). L'ancienne prévisualisation
  seule est remplacée par cette fenêtre, qui porte les mêmes contrôles qu'avant : écriture bloquée tant qu'une étape
  proche d'un keyword existant n'est pas tranchée, keywords à implémenter listés.
- Après écriture, le script entre en revue « Généré » comme avant, et l'atelier ouvre Revue et publication sur ce
  script (et non plus l'éditeur de code).
- Aucune route ni aucun outil MCP modifié : seuls deux écrans changent.

## 2026-11-19 — Initiation de Discovery : préparer un parcours utilisateur avant de le dérouler
- Demande de l'utilisateur : présenter la Discovery avec Cursor comme un assistant qui fait choisir le jeu de données,
  nommer le parcours et rattacher une epic ou une US avant le déroulé sur device ou web ; les parcours sont sauvegardés,
  rouvrables et modifiables.
- Décision : un écran en cinq étapes dans Discovery (« Préparer un parcours »), pas un nouveau module. Détail :
  docs/PARCOURS_UTILISATEUR.md.
- Nom : « parcours utilisateur », pour ne pas le confondre avec le « parcours de fonctionnalité » du menu Parcours.
- Lien parcours ↔ exigence validé d'office (déclaré par l'automaticien) ; lien écran ↔ exigence inchangé : proposition
  à confirmer dans Corrélation. Les exigences du parcours y sont seulement proposées en premier pour ses écrans.
- Relation choisie pour exigence → parcours : `associe_a` (règle d'ontologie `HAS_JOURNEY`), et non `contient`, pour
  qu'elle n'entre ni dans les périmètres ni dans la couverture.
- Jeu de données : le profil de Discovery › Données (celui dont Cursor tire ses saisies), pas `data/jdd`.
- MCP : un outil ajouté (`discovery_parcours_cadre`, lecture) et un paramètre facultatif (`discovery_demarrer(parcours=…)`).
  112 outils ; les noms et signatures existants sont conservés.

## 2026-11-19 — Refonte du design : barre latérale, barre de contexte, palette indigo
- Demande de l'utilisateur, sur une maquette fournie : une interface qui ne ressemble plus à un prototype.
- Ossature : barre latérale sombre (modules, ressources, paramètres) à la place des onglets du haut ; barre de contexte
  claire au-dessus de la zone de travail. La barre latérale se réduit aux icônes (choix mémorisé), et d'office sur les
  écrans de travail denses (Scénario BDD, Éditeur, Exécution, Knowledge Graph) sous 1700 px de large.
- Les rubriques d'un module ne sont plus une seconde colonne : elles tiennent sur une barre au-dessus du contenu, qui
  prend toute la largeur. Le bouton « Console Cursor » est logé dans la barre latérale (il recouvrait le contenu).
- Palette : une seule couleur d'accent (indigo) ; vert, orange et rouge réservés aux états. Thème clair par défaut,
  thème sombre conservé. Titres de carte en casse normale, tableaux et pastilles allégés, champs et boutons sur fond blanc.
- Repris de la maquette : la structure et le langage visuel. Non repris : ses chiffres, son assistant illustré et ses
  entrées de menu sans écran derrière (Bibliothèque, Composants, Utilisateurs) — rien n'est affiché sans source réelle.
  La barre latérale ne propose que des destinations existantes ; « Accueil » ouvre le Dashboard de pilotage.
- Mise en œuvre : `plateforme.css` (règles modifiées à leur place), `plateforme.html`, socle `plateforme.js` (navigation
  latérale `NAV`, entrée active, réduction). Aucun écran de module n'a été réécrit ; aucune route ni outil MCP modifié.
- Corrigé au passage : le Dashboard échouait (« can only concatenate list ») dès qu'un écran était relié à une exigence.
  La synthèse de corrélation rend maintenant aussi les clés (`cles_realisees`, `cles_verifiees`), lues par le pilotage.
- Dashboard (demande du même jour) : une icône par indicateur et par bloc, au trait, sur quatre teintes (indigo pour les
  volumes, vert pour l'acquis, orange et rouge pour les défauts). Un indicateur de défaut reste gris tant que sa valeur
  est nulle : la couleur signale quelque chose à traiter, jamais une alerte à vide.

## 2026-11-20 — « Explorer » devient « Explorer le reste » et dit ce qui reste hors des parcours
- Question de l'utilisateur : à quoi sert « Explorer » quand des parcours existent, et rejoue-t-il les parcours ?
- Constat dans le code : l'exploration ne connaît pas les parcours ; elle travaille sur la carte et n'essaie que les
  actions jamais essayées. Mais rien n'affichait ce qui restait hors des parcours : son utilité ne se mesurait pas.
- Décision : l'entrée est renommée « Explorer le reste » et s'ouvre sur un bloc « Reste à explorer » (écrans hors de
  tout parcours validé, actions sûres jamais essayées, actions à faire à la main, impasses), calculé sur des données
  déjà présentes. Aucun mécanisme d'exploration n'est modifié. Détail : docs/PARCOURS_UTILISATEUR.md.
- Périmètre d'exploration (demande du même jour : « j'ai ajouté les parcours eSIM, j'explore le delta dans eSIM
  uniquement ») : un module ou un parcours validé borne le reste à explorer et l'exploration. Un écran déjà connu hors
  du périmètre est une frontière (transition enregistrée, rien d'essayé depuis lui) ; un écran découvert pendant la
  session fait partie du périmètre. Les invariants de l'exploration (aucune saisie, aucune action sensible) sont inchangés.

## 2026-11-20 — Corrélation : seule l'IA configurée propose, périmètre
- Mesure sur une simulation (8 écrans, 5 exigences) : 37 propositions, dont 31 dues au seul mot « esim », présent partout.
- Décision de l'utilisateur (« pour la corrélation, je veux confier uniquement à Cursor, Claude ou l'IA configurée ») :
  seule l'IA propose un lien (« concerne » ou « incertain », justifié). Les exigences des parcours et la ressemblance
  des mots ne sont plus des propositions mais la présélection transmise à l'IA ; un mot présent dans plus de la moitié
  des exigences ne présélectionne rien (à partir de 4 exigences). Sans IA configurée : aucune proposition. Le périmètre de « Explorer le reste » (module ou parcours validé) borne
  aussi la Corrélation, et un parcours validé l'ouvre sur ses écrans. Confirmer reste une décision humaine.
  Aucun outil MCP ajouté ni modifié. Détail : docs/CORRELATION_EXIGENCES_ECRANS.md.

## 2026-11-20 — Automation Studio : rien ne recouvre la zone de travail
- Constat de l'utilisateur : les fenêtres modales rendent l'écran compliqué.
- Décision : une modale ne sert plus qu'à une saisie courte (motif d'un refus). Dans Automation Studio :
  « Construire avec Cursor » tient en trois zones fixes (écran piloté, actions de Cursor, « À vous ») ; la demande à
  envoyer à Cursor et ses questions s'affichent dans « À vous » ; les tests en attente et les sessions passées ont leur
  vue (« À revoir et sessions ») ; une session rejouée s'ouvre en pleine page (`#studio/direct/session/<id>`), l'image
  s'agrandit sur place ; l'aperçu du script Robot s'ouvre à droite du tableau de mapping. Le lanceur flottant de
  Discovery est masqué dans « Construire en direct ». `DemanderCursor` accepte `options.zone` pour s'afficher dans la
  page ; ailleurs, son comportement est inchangé. Aucune route ni outil MCP modifié.

## 2026-11-20 — Un périmètre borné de l'US au test à automatiser
- Question de l'utilisateur : peut-on passer d'une US à sa couverture par des tests fonctionnels, puis choisir les
  tests à automatiser, dans un périmètre bien limité ?
- Constat : chaque étape existait, mais le périmètre (sprint, dans Test Design › À concevoir) se perdait dans
  Automation Studio › À automatiser, qui listait toute la copie locale Xray sans dire quelle US chaque test couvre.
- Décision : « À automatiser » se borne à une US, à un sprint (la photo figée fait foi si le sprint est figé) ou à un
  module ; chaque candidat affiche les US qu'il couvre (copie locale Xray et tests liés de la testabilité) et son statut
  de revue de Test Design, « Prêt pour l'automatisation » en tête ; les US du sprint sans test sont signalées. Une US
  et un sprint de « À concevoir » ouvrent « À automatiser » borné (`#studio/candidats/us:<clé>`, `sprint:<espace>|<id>`).
  Moteur : `strategie.candidats_perimetre` ; route `GET /api/studio/candidats`. Périmètre inconnu : refusé.
  `plan_automatisation` et sa route sont inchangés. Aucun outil MCP ajouté.

## 2026-11-20 — La construction se lance depuis « À automatiser »
- Question de l'utilisateur : quand lance-t-on le développement des scripts ?
- Constat : le développement ne se lançait que depuis Mapping ou Construire ; la décision ne suivait pas.
- Décision : un test approuvé qui a son scénario BDD porte un bouton « Construire », qui ouvre « Construire en direct »
  avec la demande à Cursor prête. Lancer la construction fait passer « Approuvé » à « En construction » (journalisé) ;
  aucune autre décision n'est modifiée, et construire un test non approuvé reste possible depuis Mapping (la décision
  reste humaine, elle n'est pas un verrou). Moteur : `strategie.marquer_en_construction`.

## 2026-11-20 — Un seul fil, de la couverture des US à l'automatisation, et un guide dans l'outil
- Demande de l'utilisateur : brancher le workflow d'automatisation sur celui de la couverture des US ou des parcours
  par les tests, clair et simple ; ajouter une documentation dans l'outil.
- Décision : « À automatiser » devient « De l'US au test automatisé ». L'écran liste les US du périmètre, chacune avec
  son étape (À concevoir, À décider, À construire, En construction, Automatisée) déduite de ses tests, et ses tests
  avec leurs actions. Une US sans test y figure avec le lien vers Test Design. Le parcours utilisateur de Discovery
  devient un périmètre (ses exigences rattachées). Un guide est intégré (Automation Studio › À automatiser › Guide),
  doublé par docs/DE_L_US_AU_TEST_AUTOMATISE.md. Aucune étape n'est saisie ; aucun outil MCP ajouté.

## 2026-11-20 — Ce qui est généré suit la structure existante du dépôt
- Demande de l'utilisateur : on part d'un code source qui a déjà sa structure (un dossier pour les locators, un autre
  pour les pages et les keywords, puis les tests, les ressources…) ; Cursor doit produire dans la même logique.
- Constat : rien ne lisait cette structure ; les dossiers par défaut étaient fixés dans le code.
- Décision : la structure est lue dans le dépôt (aucun réglage), donnée à Cursor avant d'écrire (`studio_socle`,
  demande, règle `automatisation`), et contrôlée à l'aperçu, à l'écriture et dans la revue technique (contrôle
  « structure », non bloquant). Détail : docs/DE_L_US_AU_TEST_AUTOMATISE.md. Signatures des outils MCP inchangées
  (deux outils rendent une clé de plus) ; aucun outil ajouté.

## 2026-11-20 — Une suite Robot par parcours métier
- Décision de l'utilisateur : « des tests du même parcours métier en une seule suite ». Elle remplace, pour les tests
  rattachés à un parcours, la convention « un scénario end-to-end par suite ».
- Mise en œuvre : le parcours métier d'un test est le parcours utilisateur dont une exigence est couverte par le test.
  Le premier test crée la suite du parcours ; les suivants y sont ajoutés en fin de suite. La suite existante d'un
  dépôt est reconnue aux clés Xray qu'elle porte.
- Invariant « pas d'écrasement implicite » : conservé. Un ajout n'est pas une réécriture : chaque ligne d'origine est
  conservée dans l'ordre (contrôle avant écriture, sinon abandon), un test déjà présent est refusé, la suite repasse en
  revue technique. `write_project_file` refuse toujours d'écraser sans `overwrite=True`.
- Détail : docs/DE_L_US_AU_TEST_AUTOMATISE.md. Signatures des outils MCP inchangées.

## 2026-11-20 — Rattacher un test à la main, sans relation test ↔ exigence
- Question de l'utilisateur : sans relation test ↔ exigence, que se passe-t-il si on veut ajouter des tests ?
- Constat : le parcours métier ne se déduisait que par la chaîne test → US → parcours ; sans elle, le test restait
  dans sa propre suite et aucun écran ne permettait de le regrouper.
- Décision : dans l'aperçu du script, l'automaticien choisit le parcours métier du test, ou directement une suite
  existante du dépôt. Le choix passe avant la déduction ; l'ajout suit les mêmes garanties (rien n'est réécrit, test
  déjà présent refusé, retour en revue technique). Aucun outil MCP ajouté.

## 2026-11-20 — La clé du test Xray créé à la publication arrive dans le code Robot
- Précision de l'utilisateur : le test est ajouté en BDD dans le référentiel Xray, puis sa clé va dans le code Robot.
- Constat : la clé créée était enregistrée (sync_xray.json) mais le script gardait la clé locale du scénario en tag,
  avant comme après la publication ; le test n'était alors pas reconnu comme lié à Xray.
- Décision : la génération écrit en tag la clé du test Xray dès qu'elle existe ; la publication remplace le tag local
  dans les scripts déjà écrits (un seul mot de la ligne [Tags]) et renvoie la suite en revue technique.

## 2026-11-20 — « Gherkin », pas « Cucumber »
- Remarque de l'utilisateur : le test publié est un test Gherkin, pas « Cucumber ». Il ne sait pas comment le type de
  test est nommé dans son Xray.
- Constat : le nom « Cucumber » (nom par défaut du type Gherkin dans Xray Cloud) était fixé dans le code à la création
  du test, et affiché dans les écrans.
- Décision : les écrans et les messages disent « test Gherkin ». Le nom du type dans Xray devient réglable (Test
  Design › Réglages › Mapping, défaut « Cucumber ») et sert à créer le test ; « Cucumber » et « Gherkin » sont tous deux
  reconnus à la lecture. À vérifier dans Xray par l'utilisateur : Réglages du projet › Test Types.

## 2026-11-20 — L'Éditeur de code suit les règles du fil
- Question de l'utilisateur : l'Éditeur de code est-il à jour ? Il ne connaissait aucune des règles ajoutées ce jour.
- Décision : les propriétés d'une suite affichent sa revue technique, le parcours métier de ses tests et son rangement
  dans la structure du dépôt ; l'enregistrement signale un fichier hors structure, sans bloquer ; le contrôle distingue
  une clé locale de scénario (pas encore publié, ou publié sous une clé Xray à reporter) d'une clé absente ; les deux
  fenêtres modales (« Plus d'actions », « Créer un keyword ») deviennent un menu déroulant et un formulaire dans la page.
- Limite connue : sous environ 850 px de hauteur, le bas de la colonne de gauche de l'éditeur passe en partie sous le
  panneau du bas (défaut antérieur de la grille, non corrigé ici).

## 2026-11-20 — Éditeur de code : panneaux repliables et « aller à la définition »
- Demandes de l'utilisateur : pouvoir réduire les panneaux pour alléger l'espace de l'éditeur ; pouvoir faire
  Ctrl + clic pour ouvrir un keyword, une variable, etc.
- Décision : les quatre panneaux autour du code se replient (un par un, ou « Code seul »), choix gardé sur le poste.
  Ctrl + clic, Cmd + clic ou F12 ouvre la définition d'un keyword appelé, d'une variable ou d'un fichier importé,
  cherchée dans le fichier affiché puis dans le dépôt (`editeur.definition`, lecture seule). Un keyword de
  bibliothèque ou un jeu de données n'a pas de définition à ouvrir : l'éditeur le dit.
- Auto-complétion (même jour, « c'est un plus ») : en tapant ou sur Ctrl + Espace, l'éditeur propose les keywords du
  dépôt et du fichier ouvert, les variables, les clés d'un dictionnaire de locators, les fichiers resource et les
  réglages ([Tags], [Arguments]…). Rien n'est inventé ni demandé à une IA : tout vient du dépôt ou du contenu affiché.
- Mémoire des modifications (même jour) : l'éditeur tient sa propre mémoire annuler / rétablir par fichier ouvert
  (Ctrl + Z, Ctrl + Y), pour que les insertions faites par l'atelier s'annulent comme la frappe ; Alt + ← revient à
  l'emplacement d'avant un « aller à la définition ». La mémoire vit dans la page : elle est perdue si l'on recharge.
- Brouillon automatique (même jour, choix de l'utilisateur entre brouillon et enregistrement automatique du fichier) :
  chaque frappe est gardée aussitôt sur le poste (stockage du navigateur, par projet et par fichier) et reprise à la
  réouverture ; le fichier du projet ne change que sur Ctrl + S, pour qu'un script approuvé ne reparte pas en revue à
  chaque lettre. Si le fichier a changé sur le disque depuis le brouillon, l'éditeur affiche le fichier et propose de
  reprendre ou d'abandonner le brouillon. Le brouillon reste sur le poste : il ne suit pas l'utilisateur ailleurs.

## 2026-11-20 — Robocop dans l'Éditeur de code
- Question de l'utilisateur : Robocop et le Linter fonctionnent-ils ? Essai réel : le Linter oui ; Robocop n'était pas
  installé avec l'atelier, sa sortie était tronquée, et il reprochait aux tests générés leurs propres conventions.
- Décision : `robotframework-robocop` entre dans requirements.txt. Robocop analyse le contenu affiché dans un fichier
  temporaire (le fichier du projet n'est pas enregistré), rend un problème par ligne, et ignore NAME18 et DOC02 tant
  que le projet n'a pas sa configuration Robocop ; avec une configuration du projet, celle-ci fait foi.
- Conséquence assumée : sans configuration du projet, un vrai keyword mal casé n'est plus signalé par Robocop.

## 2026-11-20 — Release Notes : première étape de « Release Intelligence & Impact Analysis »
- Cahier de l'utilisateur : un module qui passe d'une Release Note (Teams, fichiers, Jira) à un périmètre de
  non-régression. Avis rendu : la moitié existe déjà (analyse d'impact, sélection TNR, validation, campagne) ; étendre
  le TNR plutôt que construire un second moteur ; les notifications de changement de Microsoft Graph sont incompatibles
  avec l'écoute sur 127.0.0.1 ; sept « agents » ne correspondent pas à l'architecture (moteurs + jugements délégués).
- Décision de l'utilisateur : commencer par le texte collé ; il peut contenir les US, mais pas toujours.
- Mise en œuvre : `atelier/intelligence/releases.py`. Lecture par des règles, sans IA. Clé Jira citée et connue :
  rattachement certain ; sinon proposition par les mots, à trancher. Une release validée alimente `pilotage.evolutions`.
  Détail et suite : docs/RELEASE_NOTES.md. Aucun outil MCP ajouté.

## 2026-11-20 — Qualification d'une release par builds successifs
- Demande de l'utilisateur : une release reçoit plusieurs builds ; chacun est analysé par rapport au précédent et au
  périmètre initial ; périmètre en trois catégories (retest, non-régression ciblée, qualification) ; historique par build ;
  un build Passed ne qualifie pas la release ; deux niveaux de pilotage (release, build).
- Décision : écran Releases dédié (barre latérale), moteur `atelier/intelligence/builds.py` ; la Release Note de la
  release reste le périmètre initial (`releases.py`). Le verdict de build et la qualification de la release sont des
  décisions du QA ; les critères de sortie sont évalués et affichés, un critère bloquant non satisfait impose une
  dérogation justifiée. Le résumé du Dashboard mène à l'écran. Aucun outil MCP ajouté, aucune dépendance.
