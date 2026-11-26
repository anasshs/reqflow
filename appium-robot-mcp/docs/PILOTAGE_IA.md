# Pilotage de l'IA : mesure, réglages, routage, contexte, cache, budgets, simulateur

Cahier « AI Management, Optimization & Cost Control » ; audit et plan du 2026-11-21. Réalisé : phases 2 à 9.
Décidé par l'utilisateur : pas de grille de prix (mesure et budgets en **tokens**) ; pas de connecteurs d'usage des
fournisseurs ni de Cursor (phase 10 non faite).

Écran : **Paramètres › Pilotage IA** (`#ia`) — Consommation, Réglages, Budgets, Cache, Simulateur.
Moteur : `atelier/intelligence/ia/`. Tests : `tests/test_ia_pilotage.py` (faux client, aucun appel réel).

## Principe

Backend d'abord : couverture, impact, TNR, critères de sortie restent calculés sans IA. Tout appel direct à un modèle
passe par **un seul point** (`orchestrateur.executer`) : `fournisseur_ia.completer` (signature inchangée, 13 points
d'appel inchangés), l'assistant des espaces de travail et l'agent intégré. L'opération QA est déduite du module appelant
(`operations.py`).

En production, **Cursor raisonne avec son propre modèle** : l'atelier ne peut ni le router ni le plafonner. Il mesure et
allège ce que ses outils MCP lui envoient (estimation, source « mcp »), corrélé à la demande de la boîte en cours. La
consommation facturée de Cursor est affichée « indisponible », jamais à zéro, jamais additionnée.

## Parcours d'un appel

1. Opération et module QA (déduits de l'appelant) ; identifiant de corrélation partagé par les appels d'une opération.
2. Budget : au blocage, refus — l'atelier continue avec ses règles, comme sans IA.
3. Réglages de l'opération (entreprise → projet → opération, plafonnés par l'entreprise).
4. Demande compactée **sans perte** (JSON réécrit, valeurs vides retirées) ; au-delà de la limite d'entrée du modèle,
   l'appel est **refusé avec un message** : rien n'est tronqué en silence.
5. Routage : économique, avancé ou « auto » (seuil de tokens) ; restriction budgétaire → économique ; modèle en échec sur
   ses derniers appels → le secours passe devant ; repli sur le secours après erreur ou délai.
6. Cache : même opération, consigne, modèle et demande, et sources inchangées (copie Xray, exigences, graphe, règles).
7. Appel, tentatives, repli ; tokens comptés par le fournisseur (`usage`), sinon estimés (4 caractères / token) et
   signalés « estimés ».
8. Journal en arrière-plan ; réponse mise en cache ; demande (masquée) gardée pour le simulateur.

## Réglages

| Niveau | Où | Contenu |
|---|---|---|
| Entreprise | fichier désigné par `ATELIER_IA_CONFIG` (poste) | plafonds : tokens d'entrée et de sortie par modèle (`'*'` pour tous), budget global |
| Projet | `<projet>/atelier_ia.yaml`, versionné, édité dans Paramètres › Pilotage IA › Réglages | modèles économique / avancé / secours (modèle, limites, température, délai, tentatives, actif), routage, optimisation, contexte, cache, budgets |
| Opération | section `operations.<opération>` du projet | niveau, sortie max, durée du cache, contexte (tests max, détail) |

Le fournisseur reste celui de l'entreprise (`IA_FOURNISSEUR`) : un modèle déclaré pour un autre fournisseur est ignoré.
Chaque modification depuis l'atelier est historisée (journal du poste) en plus de l'historique git du fichier.

## IA ou modèle applicatif, par type de traitement

Paramètres › Pilotage IA › Réglages, tableau « Traitement : IA ou modèle applicatif » (section `traitements` de
`atelier_ia.yaml`). Pour chacun des 15 types de traitement où l'IA peut intervenir : **IA** (défaut) ou **modèle
applicatif** (règles seules). Les 8 traitements où l'applicatif est **fragile** (il ne fait que rapprocher des mots :
lecture des Release Notes, liens exigence ↔ test, redondances, testabilité, doublons, granularité, keywords,
corrélation écran ↔ exigence) sont marqués et recommandés en IA.

Réglé sur le modèle applicatif : aucun appel direct (l'orchestrateur refuse), l'état vu par l'écran est « aucun » (les
boutons « Demander à Cursor » / « Avis de l'IA » disparaissent), et un jugement déposé par Cursor via le MCP est refusé
avec un message. Le traitement est déduit du module appelant : les écrans et les points d'appel existants n'ont pas
changé. Le fournisseur global de l'entreprise prime : avec « aucun », tout passe par le modèle applicatif.

Toujours applicatifs (calculs, jamais confiés à l'IA) : couverture et taux, analyse d'impact, périmètre de
non-régression et ses plafonds, comparaison entre builds, critères de sortie, statuts et résultats.

## Modèle applicatif : plafonds du périmètre

Impact indirect limité au module de l'élément touché ; indirects et qualification classés par risque (criticité,
dernier échec, étiquette, jamais exécuté) et plafonnés (40 et 30 par défaut, section `perimetre`, 0 = sans plafond).
Les non retenus sont comptés par catégorie et module, et s'ajoutent en un clic. Mesuré sur 3 000 tests : 3 009 tests
proposés avant, 821 après (dont 751 directs, liés par les données de l'essai).

## Contexte transmis

Plafonds réglables (tests, exigences, éléments du graphe, écrans) et niveau de détail (minimal, standard, complet),
appliqués aux lectures destinées à l'IA et à Cursor (interprétation des releases, liens exigence ↔ test, orphelins,
corrélation écran ↔ exigence). L'interprétation d'une release est construite **par pertinence** : tests du périmètre
des règles et des éléments rattachés, puis de leurs modules ; en détail « minimal », rien d'autre.

## Journal, consommation, budgets

- Journal : SQLite du poste (`ATELIER_IA_JOURNAL`, défaut `~/.atelier-ia.sqlite`), hors git ; identifiant unique par
  appel (un événement rejoué n'est pas compté deux fois).
- Consommation : totaux, évolution quotidienne et mensuelle, par module QA, opération, fournisseur, modèle, projet, poste ;
  tokens par opération QA (somme des appels corrélés) ; comparaison des modèles (réussite, tokens moyens, durée, replis) ;
  économies du compactage et du cache ; Cursor à part.
- Budgets mensuels en tokens (global, projet, module QA, poste) ; seuils information, avertissement, restriction
  (économique imposé), blocage (règles seules). Comptés : appels directs et agent intégré, hors cache.

## Simulateur

Sur une demande réelle passée : estimation gratuite de plusieurs réglages (modèle, compactage, limites) ou exécution
réelle sur demande explicite, comparée à la référence (verdicts identiques pour une réponse JSON, sinon ressemblance du
texte) ; note humaine de 1 à 5 par résultat.

## Changement de comportement

L'assistant des espaces de travail et l'agent intégré respectent désormais `IA_FOURNISSEUR` (avant : dès qu'une clé
Claude existait). L'agent intégré demande le fournisseur « anthropic » (boucle avec outils de l'API Claude).

## Non fait

- Coûts en euros (pas de grille de prix, décision du 2026-11-21).
- Connecteurs d'usage des fournisseurs et de Cursor (phase 10).
- Droits d'accès aux données de consommation : l'atelier n'a pas de comptes ; le journal est celui du poste.
- Regroupement d'appels (batching) : les opérations existantes font déjà un appel par lot de jugements.
