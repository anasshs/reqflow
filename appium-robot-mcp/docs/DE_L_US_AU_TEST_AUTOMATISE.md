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
| Tests | `tests/test_strategie.py`, `tests/test_routes_strategie.py` |

## Limites connues

- Le lien US ↔ test vient de la copie locale Xray et des tests liés suivis par Test Design : un test publié depuis une
  US apparaît dans le fil après la synchronisation Xray suivante.
- Le périmètre « parcours » est celui des parcours utilisateur de Discovery (exigences rattachées au cadrage). Les
  parcours de fonctionnalité (module Parcours) ne sont pas encore un périmètre.
- « En construction » est posé quand l'automaticien lance la demande, pas quand Cursor commence réellement.
- Le score d'automatisabilité reste « non calculé » ; la publication des cas dans Xray attend son essai réel.
- Aucun verrou : construire un test non approuvé reste possible depuis Mapping.
