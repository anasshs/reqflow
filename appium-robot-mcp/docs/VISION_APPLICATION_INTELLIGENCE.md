# Vision simple — Application Intelligence et Knowledge Graph

Proposition du 17 novembre 2026, à valider avant réalisation.

## Le constat

Aujourd'hui, Application Intelligence et le Knowledge Graph exposent beaucoup d'éléments.
- **Application Intelligence** a 5 rubriques et 5 sous-onglets dans « Connaissance ».
- **La couverture** a son propre jeu d'onglets (Coverage Intelligence).
- **Le graphe** a 8 vues : connaissances, fonctionnel, technique, parcours, construction BDD, couverture, flux et impact.
- **Sous le graphe** :
  - 10 boutons d'action ;
  - un bandeau « Scénario BDD » ;
  - un assistant IA ;
  - une légende de 9 familles.

Plusieurs écrans répondent à la même question. Plusieurs boutons dupliquent Test Design ou Automation Studio (générer une étape, générer Robot, valider le scénario). Le graphe complet (2 339 éléments sur TAM) n'est lisible qu'une fois filtré.

Le principe qui change tout : **Cursor construit la connaissance, l'atelier la contrôle, l'humain la valide.**
- **Cursor** lit Jira, Xray, l'application et le dépôt par le MCP. Il comprend le texte et range chaque chose à sa place : module, epic, fonctionnalité, US, règle, écran, test.
- **L'atelier** vérifie chaque proposition et la garde « à valider » tant qu'un humain ne l'a pas confirmée.

Le graphe devient le résultat de ce travail, plus un espace où l'on construit à la main.

## La cible : trois questions, trois entrées

| Question de l'équipe | Entrée | Ce qu'on y voit |
|---|---|---|
| Que fait l'application, et où en est-on ? | **Carte fonctionnelle** (Application Intelligence) | L'arbre Module › Epic › Fonctionnalité › US, avec un état sur chaque nœud |
| Qu'est-ce qui vérifie quoi, et que relancer si ça change ? | **Knowledge Graph** (menu séparé) | Traçabilité, Impact, Explorer |
| Que dois-je décider ? | **À valider** | Toutes les propositions de Cursor, de Discovery et des règles, avec leur justification |

### 1. Application Intelligence = la carte fonctionnelle

- **Page d'accueil** : l'arbre **Module › Epic › Fonctionnalité › US**. Chaque nœud porte quatre pastilles :
  - exigences couvertes ;
  - tests manuels / automatisés ;
  - écrans connus ;
  - éléments à valider.
- **Un clic ouvre la fiche du nœud**, toujours avec les mêmes quatre blocs :
  1. **Demandé** : critères, règles métier, questions ouvertes (Jira) ;
  2. **Existe** : écrans, parcours, champs (Discovery) ;
  3. **Vérifié par** : tests Xray, scripts Robot, dernière exécution ;
  4. **Manques** : US sans test, tests orphelins ou redondants, écrans sans test.
- **Les actions de la fiche** :
  - « Demander à Cursor » pour compléter les cas, relier les tests ou générer le test ;
  - « Plan de test » ;
  - « Voir dans le graphe » (Traçabilité centrée sur ce nœud).
- **Ce qui disparaît comme rubrique propre** : « Exigences et règles », « Écrans et parcours », « Champs et anomalies », « API » et les onglets de Coverage Intelligence. Leur contenu passe dans la fiche, filtré sur le nœud choisi. « Historique » devient un onglet de la fiche.
- **Construction par Cursor** : un bouton « Demander à Cursor de structurer » sur un module ou un epic.
  - Cursor regroupe les US en fonctionnalités et rattache chaque fonctionnalité à son module, en justifiant chaque rattachement.
  - Il relie aussi les écrans et les tests.
  - Tout arrive dans « À valider », selon le même modèle que les jugements déjà délégués (règles = présélection, IA = sens, humain = décision).

### 2. Knowledge Graph = un menu séparé, trois vues

| Vue | Garde | Valeur ajoutée |
|---|---|---|
| **Traçabilité** (ex-Couverture) | Epic → US → Test Xray → Test Robot, par module ou centrée sur un test | Voir ce qui vérifie quoi, ouvrir un test depuis Test Design |
| **Impact** | Choisir un écran, un locator, un keyword ou un JDD → tests touchés et TNR ciblée à lancer | Le meilleur retour sur investissement : on relance 12 tests au lieu de 1 346 |
| **Explorer** (ex-Graphe de connaissances) | Voisinage d'un élément, filtre Fonctionnel / Technique, périmètre | Comprendre une dépendance précise |

**Retiré du graphe :**

| Élément | Devient |
|---|---|
| Vues « Fonctionnel » et « Technique » | Un simple filtre de la vue Explorer |
| Vue « Parcours utilisateur » | Le module Parcours (déjà présent) |
| Vue « Construction BDD » | Test Design (redirection déjà en place) |
| Vue « Flux » | Le détail d'un test dans Automation Studio |
| Boutons « Générer étape », « Générer Robot », « Valider le scénario », bandeau BDD | Test Design et Automation Studio |
| Assistant IA du graphe | Cursor, qui répond mieux avec tout le contexte |
| « Ajouter nœud », « Fusionner », filtre de statut, mini-carte | Menu « ⋮ » : rarement utiles, Cursor propose à la place |

Il reste trois boutons sous le graphe : **Impact**, **Explorer les dépendances** et **Demander à Cursor**.

### 3. À valider, avec le suivi Cursor

- **Une seule boîte de validation**, comme aujourd'hui. Chaque proposition y dit qui l'a faite (Cursor, Discovery ou règles), pourquoi, et ce qu'elle change.
- **Le suivi** : le panneau « Demandes à Cursor » (livré le 17/11) montre pour chaque demande le temps écoulé, le moment où Cursor l'a prise en compte, ce qu'il fait et quand son résultat est déposé.

## Ce que Cursor apporte, et ce qui reste aux règles

| Cursor (compréhension du texte, justifiée) | Règles de l'atelier (vérifiables) |
|---|---|
| Regrouper les US en fonctionnalités, rattacher au module | Comptages, couverture, pastilles |
| Relier exigence ↔ test, écran ↔ exigence (déjà livré) | Analyse d'impact (relations du graphe) |
| Classer les orphelins, juger les redondances (déjà livré) | Contrôles : rien d'appliqué sans validation |
| Proposer les cas manquants d'une US (déjà livré) | Sécurité des actions, droits des rôles |

## Étapes proposées

| Étape | Contenu | Effort | Valeur |
|---|---|---|---|
| **A. Simplifier le graphe** | Menu « Knowledge Graph » séparé, 3 vues, 3 boutons, anciennes adresses redirigées | Faible | Lisibilité immédiate |
| **B. Carte fonctionnelle** | Arbre Module › Epic › Fonctionnalité › US et fiche à 4 blocs, construits sur l'existant (plan de test, couverture, corrélation) | Moyen | Une seule page par sujet |
| **C. Structuration par Cursor** | 2 outils MCP : `intelligence_structure_a_proposer` (lecture) et `intelligence_proposer_structure` (dépôt justifié, à valider), plus une règle Cursor | Moyen | La carte se construit sans saisie |

**Prérequis pour B et C** : à toi de fixer les niveaux de l'arbre.
- Le module vient-il des composants Jira, des dossiers Xray ou d'une liste déclarée ?
- Le niveau « fonctionnalité » est-il souhaité entre Epic et US ?
