# De l'US au test automatisé

Un seul fil relie la couverture des US (ou des parcours) par des tests fonctionnels et l'automatisation de ces tests.
Il se suit sur un écran : **Automation Studio › 1 · À automatiser**. Le même contenu est disponible dans l'outil :
**Automation Studio › 1 · À automatiser › Guide** (à tenir à jour avec ce document).

## Périmètre

On ne travaille jamais sur tout le projet à la fois. Le menu « Périmètre » borne le fil :

| Périmètre | Identifiant | Ce qu'il contient |
|---|---|---|
| Sprint | `sprint:<espace>\|<id>` | Les US du backlog du sprint (Test Design › À concevoir) ; la photo figée fait foi si le sprint est figé |
| Parcours utilisateur | `parcours:<id>` | Les exigences rattachées au parcours quand on l'a préparé dans Discovery |
| User Story | `us:<clé>` | Une US et ses tests |
| Module | `module:<nom>` | Les tests du module et leurs US |

Un périmètre inconnu est refusé : jamais de liste silencieusement non bornée. Depuis Test Design, le bouton
« À automatiser » d'une US et « Tests du sprint à automatiser » ouvrent le fil déjà borné
(`#studio/candidats/us:<clé>`, `#studio/candidats/sprint:<espace>|<id>`).

## Les cinq étapes d'une US

L'étape se déduit des tests de l'US (`strategie.etape_us`) : rien n'est saisi pour la faire avancer.

| Étape | Condition | Ce qu'il reste à faire | Où |
|---|---|---|---|
| À concevoir | Aucun test ne couvre l'US | Concevoir les cas, les valider, les publier dans Xray | Test Design › À concevoir |
| À décider | Des tests, aucun retenu | Relire les cas, décider lesquels automatiser | Test Design › Cas de test, puis À automatiser |
| À construire | Un test approuvé ou « Prêt pour l'automatisation » | Créer le scénario BDD, lancer la construction | À automatiser |
| En construction | Un test « En construction » | Suivre Cursor, relire le script | 2 · Construire, puis 3 · Revue et publication |
| Automatisée | Tous les tests ont un script Robot | Rien | Execution Center |

Tant qu'un test de l'US reste à faire, l'US n'est pas « Automatisée ».

## Les actions sur un test

Dans l'ordre du travail : **Décider** (enregistre la décision, ne lance rien) → **Créer le BDD** → **Construire**
(apparaît quand le test est approuvé et a son BDD ; ouvre « Construire en direct » avec la demande à Cursor prête et
fait passer le test à « En construction ») ; puis **Mapping** (ce qui existe dans le socle, génération sans Cursor) et
le **Knowledge Graph** du test.

## Ce qui est produit suit la structure du dépôt

Cursor part du dépôt existant : il lit le socle (keywords, locators, données), puis ouvre l'application pour vérifier
chaque étape et ne capturer que ce qui manque. Ce qu'il écrit doit être rangé comme l'équipe range déjà ses fichiers.

- **Structure lue, jamais saisie** : `atelier/generation/structure_depot.py` lit dans le dépôt où sont les tests
  (suites .robot), les keywords et page objects (.resource avec des keywords) et les locators (.resource qui ne porte
  que des dictionnaires `&{LOC_…}`). Elle est affichée dans Automation Studio › Environnement › Réglages.
- **Donnée à Cursor avant d'écrire** : `studio_socle` renvoie « structure » (racine et dossiers par genre) ; la
  consigne est aussi dans la demande envoyée et dans la règle `automatisation.mdc`.
- **Contrôlée** : `studio_generer_depuis_bdd` et `studio_construire_test` rendent le constat « structure » dès l'aperçu ;
  la revue technique a un contrôle « structure » sur le script et les ressources qu'il importe. Le constat n'est pas
  bloquant : l'automaticien le voit avant d'approuver.
- **Règle** : un fichier est à sa place sous le dossier commun de son genre, ou dans un dossier voisin de même niveau
  (un nouveau module à côté des tests existants). Il ne l'est pas dans un nouveau dossier à la racine du dépôt, ni dans
  le dossier réservé à un autre genre. Sans fichier d'un genre, rien n'est imposé.

Limites : un fichier écrit par `write_project_file` n'est contrôlé qu'en revue, s'il est importé par un script ; les
jeux de données ne sont pas un genre contrôlé ; un projet qui a déjà ses règles Cursor versionnées garde sa règle
`automatisation` active tant qu'elle n'est pas mise à jour (Paramètres › Cursor / Claude).

## Une suite par parcours métier

Règle de l'équipe : les tests d'un même parcours métier sont dans la même suite Robot (`atelier/generation/suites_parcours.py`).

- **Parcours métier d'un test** : le parcours utilisateur (Discovery › Préparer un parcours) dont une exigence rattachée
  est couverte par le test. Plusieurs parcours possibles : celui qui partage le plus d'exigences avec le test.
- **Suite du parcours** : la suite du dépôt qui porte déjà des tests du parcours (reconnue à leurs clés Xray en tag,
  quel que soit son nom) ; sinon une nouvelle suite au nom du parcours, rangée selon le motif de Test Design › Réglages.
- **Ajout, jamais réécriture** : le test est ajouté en fin de section de tests, avec les imports manquants et les
  keywords à implémenter. Chaque ligne de la suite d'origine est conservée, dans l'ordre (contrôlé avant d'écrire).
  Un test déjà présent (même nom ou même clé Xray) est refusé. La suite complétée repasse en revue technique.
- **Sans parcours** : le test garde sa propre suite, comme avant. Un chemin imposé par l'appelant n'est jamais un ajout.
- **Sans relation test ↔ exigence** : le parcours ne peut pas être déduit. L'automaticien rattache le test à la main,
  dans l'aperçu du script (BDD → Robot › Générer le script Robot) : il choisit son **parcours métier** (même un
  parcours sans exigence rattachée), ou directement une **suite existante** du dépôt. Le choix est enregistré sur le
  scénario BDD (`parcours`, `suite`) et l'aperçu est recalculé. Priorité : suite choisie, parcours choisi, parcours
  déduit des US, suite propre. Effacer le choix revient à la déduction.
- L'aperçu du script dit ce qui va se passer : « Ajout à une suite existante », « Nouvelle suite du parcours » ou
  « Suite propre », avec la raison.

Limites : l'ajout se fait par `studio_generer_depuis_bdd` et par l'aperçu de l'atelier ; `studio_construire_test`
(assemblage par palette) écrit toujours une suite à part. Un test rattaché à un parcours après coup n'est pas déplacé.

## La clé du test Xray dans le code Robot

Chaque test Robot porte en tag la clé de son test Xray : c'est ce qui le relie à Xray (statut « Automatisé », suite
d'un parcours, résultats d'exécution).

- **Scénario créé depuis un test Xray** : sa clé est déjà celle du test ; elle est écrite en tag.
- **Scénario créé dans l'atelier** (Discovery, saisie) : il est publié en BDD dans Xray (Scénarios BDD › Publier), ce
  qui crée le test Gherkin. `conception.cle_xray_du_scenario` rend la clé créée ; la génération l'écrit en tag.
- **Script écrit avant la publication** : il porte la clé locale du scénario. À la publication,
  `conception.reporter_cle_xray` remplace ce mot dans la ligne `[Tags]` du test, rien d'autre, et renvoie la suite en
  revue technique. Un échec de ce report n'annule pas la publication : il est signalé dans son résultat.
- L'aperçu du script indique le tag qui sera écrit, et signale un scénario pas encore dans Xray.
- **Type du test dans Xray** : le test créé est un test dont la définition est du Gherkin. Xray Cloud nomme ce type
  « Cucumber » par défaut ; un projet peut le nommer autrement (« Gherkin »). Le nom utilisé à la création se règle dans
  Test Design › Réglages › Mapping et synchronisation Xray (`conception.type_gherkin`) ; les deux noms sont reconnus à
  la lecture. Les écrans parlent de « test Gherkin ».

## Trois statuts distincts

| Statut | Porte sur | Valeurs | Qui le change |
|---|---|---|---|
| Revue | Le cas de test | Brouillon, En revue, Modifications demandées, Approuvé, Prêt pour l'automatisation | L'automaticien, Test Design › Cas de test |
| Décision | L'automatisation du test | À analyser, À valider, Approuvé, En construction, Rejeté ; « Automatisé » dès qu'un script Robot porte la clé du test | L'automaticien (« Décider ») ; « En construction » posé au lancement de la construction |
| Revue technique | Le script Robot | Généré, Revue technique, Modifications demandées, Approuvé, Publié, Refusé | L'automaticien, 3 · Revue et publication |

## Où c'est

| Élément | Emplacement |
|---|---|
| Moteur | `candidats_perimetre`, `etape_us`, `ETAPES_FIL`, `marquer_en_construction` dans `atelier/intelligence/strategie.py` |
| Routes | `GET /api/studio/candidats?perimetre=`, `POST /api/studio/candidats/construction` |
| Écran et guide | `candidats` et `guide` dans `atelier/adapters/web/static/ecran_studio.js` |
| Structure du dépôt | `atelier/generation/structure_depot.py` ; route `GET /api/studio/structure` |
| Suite par parcours métier | `atelier/generation/suites_parcours.py` (`cible`, `ajouter`, `rattacher`, `options`), appelé par `bdd.generer_robot` ; `GET /api/bdd/{cle}/rangement`, opération `rangement` de `POST /api/bdd/{cle}/operation` |
| Tests | `tests/test_strategie.py`, `tests/test_routes_strategie.py`, `tests/test_structure_depot.py` |

## Limites connues

- Le lien US ↔ test vient de la copie locale Xray et des tests liés suivis par Test Design : un test publié depuis une
  US apparaît dans le fil après la synchronisation Xray suivante.
- Le périmètre « parcours » est celui des parcours utilisateur de Discovery (exigences rattachées au cadrage). Les
  parcours de fonctionnalité (module Parcours) ne sont pas encore un périmètre.
- « En construction » est posé quand l'automaticien lance la demande, pas quand Cursor commence réellement.
- Le score d'automatisabilité reste « non calculé » ; la publication des cas dans Xray attend son essai réel.
- Aucun verrou : construire un test non approuvé reste possible depuis Mapping.
