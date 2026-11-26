# Audit — du parcours au TNR dans Xray : l'existant et sa simplification

État au 2026-11-23, à partir d'un cas réel : application mobile bancaire (Android, recette), 12 scénarios automatisés,
publiés dans Xray et inscrits à un plan TNR dédié.
Objectif : le même résultat, mais un chemin court et évident, parce que ce cas d'usage va se répéter chaque jour et
grossir par lots successifs (12 scénarios aujourd'hui, de nouveaux demain).

Hors priorité (mais à ne pas fermer) : le lien avec les exigences Jira (US, critères, couverture des exigences).
Il sera injecté ensuite ; voir la section 6.

---

## 1. Le chemin réellement suivi (12 scénarios)

| # | Étape | Ce qu'on a fait | Où (écran / outil) | Qui |
|---|---|---|---|---|
| 1 | Cadrer | Parcours « PU-parcours_de_bout_en_bout » : nom, point de départ, profil de données | Discovery › Préparer un parcours | automaticien |
| 2 | Explorer | Session Discovery, écran par écran, propositions (noms d'écrans, règles, parcours) | Agent (MCP) + device | agent ; connexion par l'automaticien |
| 3 | Valider la connaissance | 25 + 24 propositions « à valider » | Application Intelligence › À valider | automaticien (non fait à ce jour) |
| 4 | Écrire les scénarios | Brouillon depuis la carte, puis réécrit à la main ; liens écran / locator / donnée posés un par un | Tests BDD / Construction BDD (fichiers `bdd/*.feature`) | agent |
| 5 | Données | Variables + valeurs (Discovery › Données), jeux `data/jdd/recette.yaml`, et un 3e endroit (`comptes` de la fiche application) | 3 endroits | automaticien + agent |
| 6 | Juger les keywords | Une décision « créer / réutiliser » par étape, même quand le socle est vide | `studio_keywords_a_juger` / `studio_juger_keywords` | agent |
| 7 | Générer | Suite + pages « À implémenter » (stubs) | `studio_generer_depuis_bdd` | agent |
| 8 | Implémenter | Corps des keywords, fichiers de locators, socle (ouverture de l'app, teardown) | Éditeur / fichiers | agent |
| 9 | Vérifier en local | Dry-run, puis run réel de la sélection | Tests automatisés › Vérifier ; Exécution | automaticien (login) / agent (sans login) |
| 10 | Valider | Revue technique des suites (bloquante pour une campagne) | Tests automatisés › Valider / Automation Studio › Revue | automaticien |
| 11 | Publier dans Xray | Un test Cucumber par scénario, étiquette, dossier ; clé reportée dans le tag Robot | Test Design › Publier (pas d'outil MCP) | agent (script) |
| 12 | Inscrire au TNR | Test Plan créé, campagne créée, tests ajoutés | Execution Center › Campagnes | agent (script) |
| 13 | Exécuter | Campagne → nouvelle Test Execution par run, statuts, heures, environnement, log | Execution Center | automaticien |

**Volume :** environ dix endroits différents de la plateforme, cinq systèmes de statut, trois endroits pour les
données, et quatre étapes (4, 6, 11, 12) qui n'ont été possibles qu'en contournant l'interface (fichiers, scripts).

---

## 2. Constats

### 2.1 Trop de façons de nommer le même chemin
Le même cycle est décrit cinq fois dans le code, avec des découpages différents :

| Définition | Fichier | Étapes |
|---|---|---|
| Parcours de qualification (barre latérale) | `intelligence/qualification.py` | 6 : comprendre, comportement, concevoir, automatiser, exécuter, évoluer |
| « Ton chemin » (Accueil) | `intelligence/chemin.py` | 4 : découvrir, concevoir, automatiser, exécuter |
| Parcours de fonctionnalité | `intelligence/parcours_fonctionnalite.py` | 10 : discovery … synchronisation |
| Étapes d'une US | `docs/DE_L_US_AU_TEST_AUTOMATISE.md` | 5 : à concevoir … automatisée |
| Cycle de vie d'un test | `generation/cycle_vie.py` | 5 : brouillon … automatisé |

Et le mot « parcours » désigne quatre objets différents : parcours utilisateur (PU-…, cadrage Discovery), parcours de
fonctionnalité (suivi par US), parcours proposé au Knowledge Graph, parcours métier (regroupement des suites Robot).

### 2.2 Trop de statuts pour un scénario
Pour savoir « où en est ce scénario », il faut croiser : statut du BDD (brouillon / validé), revue technique du script
(Generated → Published), état de Tests automatisés (À valider / Validé / Écarté) et « Vérifié », publication Xray
(clé ou non), présence dans le plan TNR. Aucun écran ne montre les cinq ensemble.

### 2.3 Données en trois endroits
- Discovery › Données : variables, profils, valeurs (y compris un mot de passe en clair si la variable est « normale »).
- `data/jdd/<env>.yaml` : jeux des tests, avec `{{env:…}}`.
- Fiche application, champ `comptes` : identifiants en clair, renvoyés par `map_apps`.
Le lien entre les deux premiers manquait au run (corrigé aujourd'hui : `{{env:X}}` lit aussi le référentiel), et la
valeur d'un profil n'est toujours pas utilisée au run.

### 2.4 Des étapes obligatoires qui n'apportent rien dans ce cas
- Jugement des keywords étape par étape, même avec un socle vide.
- Refus « doublon probable » sur une ressemblance de mots (« je saisis la référence… » contre « je saisis mes
  identifiants… ») : on reformule pour passer, sans que le contrôle ait évité un vrai doublon.
- Publication dans Xray qui renvoie les suites en revue alors que seul le tag a changé.
- 1 test Xray = 1 scénario : un fichier BDD à deux scénarios perd le second à la publication ; il a fallu découper.

### 2.5 Ce qui n'existe qu'à moitié
- Le brouillon BDD tiré de la carte ne reprend pas les actions faites (il propose « je renseigne mot de passe » sur un
  parcours sans connexion, « je reviens en arrière » au lieu du choix de la ville) : il est réécrit à chaque fois.
- La génération produit des stubs ; l'implémentation (keywords, locators) reste entièrement à faire.
- Les pages générées prennent le titre de l'écran pour nom (`ios.resource` = nom du client, `des_avantages_….resource`).
- Publication Xray, création du plan TNR et ajout à une campagne : pas d'outil MCP, donc pas faisable par l'agent sans
  passer par des scripts.
- Variantes (plusieurs facturiers, plusieurs services) : pas d'outil pour relever un catalogue ni pour lier un tableau
  d'exemples à un jeu de données.

### 2.6 Robustesse rencontrée en route
Session Appium qui expire pendant une attente, journal Discovery corrompu par deux processus (MCP et interface),
`where_am_i` hors session qui crée des écrans fantômes (le bureau Android nommé « Paramètres »), données personnelles
du client capturées dans les locators de « Mon profil », vue Exécution figée si on l'ouvre en cours de run (corrigé),
erreur de lancement d'un run invisible dans Tests automatisés (corrigé).

---

## 3. La cible : un « lot TNR » en 5 étapes, sur un seul écran

Un **lot** = un parcours cadré + ses scénarios. Il vit dans le temps : on y ajoute des scénarios demain, ils suivent
le même chemin et rejoignent le même plan TNR.

| Étape | L'automaticien fait | La plateforme / l'agent font | Fini quand |
|---|---|---|---|
| 1. Cadrer | Nom, application, point de départ, résultat attendu, profil de données | Crée le lot ; rattache le plan TNR de l'application (créé au premier lot) | Le cadrage est complet |
| 2. Explorer | Se connecte si besoin ; valide les écrans en un clic (lot) | Discovery, noms d'écrans, règles, captures sans données client | Écrans du lot validés |
| 3. Scénariser | Relit et coche les scénarios | Un scénario par chemin (actions et données réelles du déroulé), variantes en tableau d'exemples lié au jeu | Scénarios validés |
| 4. Automatiser et vérifier | Lance le run réel (s'il faut se connecter) | Génère et implémente (keywords, locators, pages bien nommées), dry-run, puis run réel | Chaque scénario « Vérifié » |
| 5. Publier au TNR | Un bouton « Publier le lot » | Tests Xray (étiquette et dossier de l'application), ajout au plan TNR, campagne à jour ; clés dans les tags sans repasser en revue | Lot dans le plan ; chaque run va dans Xray |

**Un seul statut par scénario**, lu sur une ligne : `Brouillon → Validé → Automatisé → Vérifié → Au TNR`
(+ `En échec` à côté, issu du dernier run). Les statuts internes (revue technique, décision) restent, mais ne sont
plus ce qu'on regarde.

**Un seul écran, « Lot »** : une ligne par scénario, une colonne par étape (✓ / à faire / en échec), la prochaine
action en bouton, et en tête : appareil, environnement, plan TNR, dernier run.

```
Lot « Parcours de bout en bout » · Banque Démo · Android · recette · Plan TNR DEMO-900 · dernier run 18:16 (8/9)
Scénario                                  Validé  Automatisé  Vérifié   Au TNR     Dernier run
Se connecter et afficher le tableau...      ✓        ✓         ✓       DEMO-601    réussi
Consulter l'onglet Carte                    ✓        ✓       en échec  DEMO-607    Service indisponible
Recharge mobile (3 variantes)               ✓        ✓         à faire     —          —
[ + Ajouter des scénarios ]                     [ Vérifier la sélection ]      [ Publier le lot au TNR ]
```

---

## 4. Comparaison étape par étape

| Étape | Aujourd'hui | Cible | Gain |
|---|---|---|---|
| Cadrage | Formulaire PU sans résultat attendu obligatoire ; plan TNR et étiquette Xray réglés ailleurs | Cadrage du lot avec résultat attendu ; conventions Xray de l'application (étiquette, dossier, plan TNR) posées une fois | Pas de réglage caché découvert à la publication |
| Exploration | Propositions une par une, validation dans un autre écran | Validation en lot dans l'écran Lot ; aucune donnée client dans les locators | 1 écran au lieu de 2 |
| Scénarios | Brouillon réécrit à la main ; liens posés un à un ; multi-scénarios perdus à la publication | Brouillon fidèle au déroulé, liens déjà posés ; 1 scénario = 1 fichier = 1 test Xray | Plus de découpage ni de réécriture |
| Données | 3 endroits, mot de passe possible en clair | Un seul référentiel (Discovery › Données) ; les jeux `data/jdd` en sont générés ; secret obligatoire pour un mot de passe | 1 endroit, aucun secret en clair |
| Keywords | Jugement par étape obligatoire ; refus sur ressemblance de mots | Jugement seulement s'il existe un candidat crédible ; sinon création directe, signalée | Moins d'allers-retours |
| Génération | Stubs « À implémenter », pages nommées par le titre | Keywords implémentés depuis les actions enregistrées ; pages nommées par le nom d'écran validé | Scripts exécutables dès la génération |
| Vérification | Vérifier, Exécution, Tests automatisés : trois écrans | Bouton dans l'écran Lot, suivi en direct sur place | 1 écran |
| Validation | Revue technique bloquante, relancée par la publication | « Vérifié » suffit pour publier ; la revue garde la main sur les changements de code, pas sur un tag | Plus de revue inutile |
| Publication + TNR | Par scénario (Test Design), plan et campagne à part ; pas d'outil MCP | « Publier le lot » : tests, étiquette, dossier, ajout au plan TNR, campagne ; outil MCP équivalent | 1 action au lieu de ~4 par scénario |
| Exécution | Campagne : Test Execution, heures, environnement, log sur le ticket | Inchangé (déjà en place) | — |

---

## 5. Plan incrémental

Chaque palier est utilisable seul. Les deux premiers suppriment l'essentiel des frictions sans nouvel écran.

| Palier | Contenu | Effort |
|---|---|---|
| **P1 — conventions et un bouton** | Réglage par application : étiquette Xray, dossier, plan TNR (créé s'il manque) ; « Publier au TNR » (sélection) = publication + ajout au plan + campagne ; publication sans renvoi en revue quand seul le tag change ; outils MCP `tnr_publier` et `tnr_plan` | S |
| **P2 — données à un seul endroit** | Jeux `data/jdd` générés depuis les profils Discovery ; variable de type mot de passe forcée « secrète » ; champ `comptes` retiré de la fiche application (et masqué dans `map_apps`) ; valeur de profil utilisée au run | S |
| **P3 — écran Lot** | Vue par lot (ligne = scénario, colonnes = étapes, statut unique, prochaine action), en réutilisant `bdd`, `maintenance.vue`, `sync_xray.json`, campagnes ; « Ajouter des scénarios » ouvre le cadrage ou la Discovery | M |
| **P4 — scénarios fidèles et variantes** | Brouillon BDD depuis les actions réelles de la session ; 1 scénario par fichier ; tableau d'exemples lié à un jeu ; relevé de catalogue (facturiers × services) en démo | M |
| **P5 — génération exécutable** | Keywords générés avec leur corps depuis les actions enregistrées (tap, saisie par `${JDD}[…]`, vérification de présence) ; pages nommées par l'écran validé ; jugement des keywords seulement s'il y a un candidat | M–L |
| **P6 — unifier les définitions** | Une seule définition du cycle (celle du lot), les autres en deviennent des vues ; un seul sens pour « parcours » | M |

Robustesse à traiter au fil de l'eau : écriture concurrente du journal Discovery (session déjà proposée), session
Appium maintenue pendant une Discovery, `where_am_i` sans effet hors session, masquage des données client dans la carte,
fichier `.jdd_resolu.yaml` (secrets résolus) supprimé en fin de run.

---

## 6. Exigences Jira : dépriorisées, mais prévues

Rien de ce qui précède ne dépend des exigences. Pour pouvoir les injecter ensuite sans reprise :
- garder dans le lot et dans chaque scénario un champ « exigences » facultatif (clés Jira), vide aujourd'hui ;
- au cadrage, un emplacement « US liées » optionnel, jamais bloquant ;
- à la publication, si des exigences sont renseignées, le lien test ↔ exigence part en proposition
  (`coverage_proposer_lien`), validée ensuite par l'automaticien ;
- les écrans de couverture d'exigences (Test Design › À concevoir, Coverage Intelligence) restent en place, mais hors du
  chemin du lot.

---

## 7. Déjà corrigé pendant ce cas d'usage (2026-11-23, non commité)

| Correctif | Fichiers |
|---|---|
| `{{env:X}}` d'un jeu lit aussi le coffre et Discovery › Données | `execution/jdd.py`, `discovery/donnees.py` |
| Tests automatisés : panneau « Exécutions » (en cours, en file, terminées, erreur de lancement) | `generation/maintenance.py`, `ecran_tests.js` |
| Vue Exécution simple et temps réel tenue côté serveur ; vue détaillée qui reprend le direct | `execution/direct.py`, `ecran_suivi.js`, `ecran_execution.js` |
| Étiquettes Jira à la création d'un test Xray | `integrations/xray/__init__.py`, `generation/conception.py` |
| Log total joint au ticket Test Execution | `execution/journal_xray.py` |

---

## 8. Réalisé (2026-11-23, non commité)

| Palier | Ce qui est livré | Où |
|---|---|---|
| P1 | Conventions TNR par application (étiquette, dossier, plan, campagne) ; « Publier au TNR » : découpage 1 scénario = 1 test, publication avec étiquette et dossier, plan TNR créé s'il manque puis complété, campagne liée à jour ; clé Xray reportée sans renvoi en revue ni perte de « Vérifié » ; outils MCP `tnr_conventions` et `tnr_demander_publication` (demande validée) ; bouton dans Tests automatisés et dans Lots TNR | `generation/tnr.py`, `generation/conception.py`, `generation/studio.py`, `domain/demandes.py`, routes `/api/tnr/*` |
| P2 | Variable « mot de passe / jeton / PIN / OTP » toujours secrète ; `secrets_en_clair` et `securiser_secrets` (valeurs en clair déplacées au coffre) ; valeur de profil utilisée au run ; champ `comptes` masqué dans `map_apps` ; jeux tirés d'un profil gardent ce profil | `discovery/donnees.py`, `execution/jdd.py`, `discovery/carte_outils.py`, routes `/api/donnees/*` |
| P3 | Écran Lots TNR (#lots) : une ligne par scénario, statut unique, étapes, prochaine action, sélection → Vérifier / Publier au TNR / rattacher ; conventions en tête ; alerte des secrets en clair ; lots dans `conception/lots.yaml`, appartenance dans le BDD (champ `lot`), filtrés sur l'application active | `generation/lots.py`, `static/ecran_lots.js`, routes `/api/lots*` |
| P4 | Brouillon BDD fidèle aux actions réelles d'une session (toucher, saisir par variable, revenir, défiler ; seuls les champs saisis) ; Plan du Scénario avec colonne « jeu » → un test Robot par variante ; découpage automatique avant publication | `generation/parcours_bdd.py`, `generation/bdd.py` |
| P5 | Keywords générés avec leur corps depuis l'étape (mobile : Click Element, Input Text / Input Password, Wait Until Element Is Visible ; web : Click, Fill Text / Fill Secret, Wait For Elements State) et locators dans `resources/locators/<page>.resource` ; pages nommées par l'écran validé (jamais son titre) (le refus sur ressemblance reste levé par une décision humaine seulement : règle du projet, un jugement d'IA ne la remplace jamais) | `generation/pom.py`, `generation/bdd.py` |
| P6 | Cycle de référence unique (`domain/cycle.py`) : étapes, statuts, rattachement des autres découpages, glossaire de « parcours » ; « Automatiser » mène à Lots TNR | `domain/cycle.py`, `intelligence/chemin.py`, `intelligence/qualification.py` |
| Robustesse | Timeline Discovery : verrou inter-processus, une écriture par ligne, doublons écartés, lecture tolérante ; `where_am_i` hors de l'application n'enregistre rien ; la valeur d'un champ de saisie n'entre plus dans la carte ; session Appium tenue 1 h | `discovery/sessions_discovery.py`, `discovery/observation.py`, `discovery/exploration.py`, `discovery/parsing.py`, `integrations/appium` |

Appliqué au projet de tests du cas réel : conventions de l'application (étiquette, dossier, plan TNR, campagne),
trois lots (Avant connexion, Parcours de bout en bout, Paiement en démo), mot de passe déplacé au coffre, champ `comptes`
vidé.

Reste ouvert : relevé automatique d'un catalogue de variantes (facturiers × services), exigences Jira (section 6).
