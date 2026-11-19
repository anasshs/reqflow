# Parcours utilisateur — initiation de Discovery

État au 2026-11-19. Moteur : `atelier/discovery/parcours_utilisateur.py`. Écran : Discovery › Préparer un parcours
(`ecran_discovery_parcours.js`). Tests : `tests/test_parcours_utilisateur.py`.

## Pourquoi
Avant, une exploration démarrait sans cadre : ni nom de parcours, ni exigence, ni jeu de données choisi dans l'atelier.
Avec Cursor, ces questions étaient posées dans son chat et rien n'était gardé. Le parcours n'apparaissait qu'après coup,
comme une proposition. Demande de l'utilisateur (2026-11-19) : assister l'automaticien avant le déroulé, et pouvoir
rouvrir et modifier un parcours.

## Ce que l'automaticien prépare
| Étape | Contenu | Obligatoire |
|---|---|---|
| 1 · Parcours | nom, objectif, point de départ, résultat attendu | le nom |
| 2 · Exigences | epics, US ou bugs de la copie locale Jira, avec leurs critères d'acceptation | non (averti) |
| 3 · Données | profil du référentiel Discovery › Données, environnement ; variables prêtes ou sans valeur | non (averti) |
| 4 · Cible et lancement | plateforme déclarée pour l'application, qui navigue (l'automaticien ou Cursor), récapitulatif | la plateforme |
| 5 · Déroulés et validation | sessions rattachées, écrans traversés à garder ou retirer, journal | — |

Le parcours est enregistré dès l'étape 1 (`<projet>/discovery/parcours/PU-<nom>.json`). Il se rouvre, se modifie, se
duplique (variante) et s'archive ; rien n'est supprimé. Chaque modification est journalisée (champ, avant, après, par qui).
Statuts calculés : Brouillon → Prêt → En cours → Exploré → Validé ; Archivé.

Une exploration libre, sans parcours, reste possible et inchangée (Discovery › Explorer).

## Le déroulé
- « Je navigue » : la fenêtre Discovery s'ouvre sur la plateforme du cadrage ; la session créée porte le parcours.
- « Cursor navigue » : la demande cite l'identifiant du parcours. Cursor lit `discovery_parcours_cadre("PU-…")` puis
  appelle `discovery_demarrer(parcours="PU-…")`. Le cadrage complète la configuration de la session (périmètre, point
  de départ, profil de données, environnement) quand ces valeurs ne sont pas précisées.
- À la fin de la session, les écrans traversés sont proposés au parcours, dans l'ordre et sans répétition.

## Ce qui entre dans le Knowledge Graph
| Quoi | Relation | Statut | Qui décide |
|---|---|---|---|
| Le parcours | nœud `parcours:<nom>` déclaré | validé | l'automaticien, en l'enregistrant |
| Exigence → parcours | `associe_a`, lu « a le parcours » (`HAS_JOURNEY`) | validé | l'automaticien, en la rattachant |
| Parcours → écran | `contient` (`PART_OF_JOURNEY`) | à valider, puis validé | l'automaticien, à l'étape 5 |
| Exigence → écran | aucune relation créée ici | — | Corrélation (« réalisé par », décision humaine) |

Règles :
- Le lien exigence → parcours n'entre dans aucun calcul de couverture ni de périmètre (`associe_a` n'est pas suivi).
- Un écran retiré à la validation est mémorisé comme rejeté : un nouveau déroulé ne le repropose pas.
- Les exigences d'un parcours sont proposées EN PREMIER pour ses écrans dans Corrélation, avec la mention du parcours ;
  elles y restent des propositions tant que l'automaticien ne les confirme pas (décision du 2026-11-18).
- Un parcours déjà proposé par un agent sous le même nom est repris et validé par le cadrage (même nœud).

## Pour Cursor
| Outil | Rôle |
|---|---|
| `discovery_parcours_cadre` (lecture) | sans argument : parcours préparés ; avec « PU-… » : cadrage complet, sans aucune valeur de donnée |
| `discovery_demarrer(parcours=…)` | la session déroule le parcours (paramètre ajouté, facultatif) |

L'agent ne crée ni ne modifie un cadrage.

## Limites connues
- Le parcours utilisateur (ce document) et le « parcours de fonctionnalité » du menu Parcours (cycle de vie en dix
  étapes) sont deux objets distincts ; ils ne sont pas encore reliés l'un à l'autre.
- Le jeu de données est le profil Discovery, pas les jeux `data/jdd` des tests Robot.
- Rôles : enregistrer, valider et archiver demandent le droit « construire » quand les rôles sont activés.
- Vérifié sur une application fictive et sur un projet de simulation, avec un déroulé simulé (aucun device réel, aucune
  demande réelle à Cursor).
