# Évolution du Knowledge Graph — audit de l'existant et plan d'intégration

Cahier : « QAFlow — Évolution du Knowledge Graph » (4 perspectives, ponts sémantiques, confiance, construction live,
couverture / flux / impact sans Xray). Règle : un seul graphe, un seul moteur ; on étend, on ne remplace pas.

## 1. Existant (audit du 2026-11-22)

| Sujet | Où | Constat |
|---|---|---|
| Nœud | `atelier/domain/graphe.py` `Noeud` | id `type:clé`, type, libellé, propriétés, provenance (observé / déclaré / déduit), source, statut (validé / à valider), confiance (nombre), plateformes |
| Relation | `graphe.py` `Relation` | id `de|type|vers`, type, provenance, source, statut, propriétés ; **ni niveau de confiance, ni dates, ni preuves structurées** |
| Types | `TYPES_NOEUDS`, `TYPES_RELATIONS` | historiques ; **ontologie cible** déjà présente (`atelier/domain/ontologie.py` : BusinessDomain, BusinessProcess, BusinessRule, UserJourney, UIAction, ScreenState, ObservedBehavior…, relations métier typées et migration des relations historiques) |
| Construction | `atelier/discovery/connaissance.py` `_construire` | 11 étapes : carte, dépôt Robot, JDD, Jira / Xray local, périmètre de couverture, OpenAPI, résultats, déclarations, données Discovery, relations fonctionnelles déduites, preuves |
| Cache | `connaissance.construire` | graphe gardé tant que l'empreinte du projet (taille + date de chaque fichier) ne change pas ; sinon reconstruction totale (1 à 3 s) ; chaque appelant reçoit une copie |
| Événements | `domain/evenements`, WebSocket | `carte_change`, `discovery`, `mcp_outil` (fin d'outil MCP), `outil`, `locators_change` ; l'écran graphe se recharge en direct (regroupé + filet 8 s) |
| Validation | `atelier/domain/declarations.py` | ajouter / modifier / valider / rejeter / fusionner / masquer, historique ; statut métier `OFFICIAL / VALIDATED / PROPOSED` (`ontologie.statut_validation`) |
| Consommateurs | `espaces.vue_connaissance`, `couverture.vue/indicateurs/candidats`, `flux.vue`, `connaissance.analyser_impact`, `espaces.ids_perimetre/patrimoine_lie/anomalies`, `ontologie.property_graph` | |

Écarts au cahier :
1. **Tests BDD absents du graphe** (`bdd/*.yaml` n'est pas lu) : couverture sans Xray impossible.
2. **Action = propriété d'une transition** (lien écran → écran), pas un nœud.
3. **Parcours déclaré sans écran** : présent mais isolé, sans statut de complétude.
4. **Confiance des relations** : seulement provenance + statut ; pas de dates ni de preuves.
5. **Construction totale** à chaque changement ; pas de mise à jour ciblée.
6. **Impact** : pas de navigation ; TNR uniquement par clés Xray. **Flux** : suit les liens non validés.
7. **Affichage** tronqué à 600 nœuds par ordre alphabétique.

## 2. Décisions d'intégration

- **Pas de nouveau modèle.** `Noeud` et `Relation` gardent leurs champs et leurs identifiants ; les ajouts sont des
  champs à valeur par défaut ou des propriétés. Les relations historiques restent (consommées par Couverture, Flux,
  Impact) ; les relations métier précises sont **ajoutées** à côté quand la source le permet.
- **Confiance d'une relation** (`Relation.confiance_niveau`) : `confirmée` (observée, déclarée, ou validée), `probable`
  (déduite par un calcul déterministe à partir de faits observés, avec preuves), `non vérifiée` (proposition à valider,
  IA comprise). Seules les relations `confirmée` alimentent couverture, impact et TNR officiels. Dates (`cree`, `maj`)
  et preuves (`preuves`) en propriétés.
- **Perspectives = vues filtrées** du même graphe : Fonctionnelle, Utilisateur / Parcours, Technique, Tests & Qualité,
  Tout. « Construction BDD » quitte les vues du graphe (éditeur dédié).
- **Ne rien inventer** : un type métier (domaine, processus, étape, condition, événement, donnée métier) n'apparaît que
  si une source ou une déclaration le fournit.

## 3. Plan (lots du cahier)

| Lot | Contenu | État |
|---|---|---|
| 1 | Confiance des relations ; actions utilisateur en nœuds (écran → permet → action → aboutit à → écran) ; tests BDD dans le graphe et ponts (scénario → vérifie → parcours, couvre → écran, implémenté par → test Robot, test Xray → formalisé par → scénario) ; complétude des parcours | fait |
| 2 | Mise à jour ciblée (sources relues seulement si elles changent, empreinte sans captures), cohérence (assemblage refait, aucune relation orpheline), remplacement atomique, parcours incomplets (lot 1) | fait |
| 3 | Perspectives graphiques (Fonctionnelle, Utilisateur, Technique, Tests & Qualité, Tout ; filtres provenance / confiance / statut ; « Voir dans » une autre perspective) | fait |
| 4 | Couverture indépendante de Xray (couverture_atelier : parcours, écrans, fonctionnalités, tests BDD automatisés, liens confirmés seulement) | fait |
| 5 | Flux vérifié / exploratoire, vue d'ensemble limitée ; Impact technique / fonctionnel / utilisateur, direct / indirect / potentiel ; TNR sans Xray (identifiant BDD, puis clé Xray) | fait |
| 6 | Doublons sémantiques, qualité du graphe, sélection d'affichage | fait |

## 4. Finitions (sections 5.1, 5.4, 6 et 12 du cahier)

- **Mise à jour ciblée au fichier près** : chaque fichier d'écran de la carte et chaque test BDD n'est relu que s'il a
  changé (taille, date) ; les autres sont repris en mémoire. L'assemblage reste complet et atomique (aucune relation
  d'une ancienne version d'un fichier). Chaque construction calcule l'écart avec la précédente (ajoutés, modifiés,
  retirés, relations comprises) : pendant le suivi en direct, les éléments nouveaux sont surlignés en vert, les éléments
  modifiés en bleu (compteurs « +n · ~m » dans le bouton « En direct »). Volumes : Sources du graphe.
- **Filtres** (bouton « Filtres » de la barre) : application (si plusieurs), plateforme, version (builds où chaque
  écran a été vu, lus dans la carte), type d'élément (dans la perspective), provenance, confiance des liens, statut,
  patrimoine Jira / Xray. Module, fonctionnalité, parcours : liste « périmètre ».
- **Liens « via »** : leur panneau donne le chemin réel (éléments intermédiaires, cliquables, et « Afficher » ouvre
  l'élément intermédiaire avec ses deux relations réelles). Jamais enregistrés, jamais dans la couverture ni l'impact.
- **Panneau de détail en onglets** : actions toujours visibles (Explorer, Impact, Couverture, Relier, Modifier, Valider,
  Fusionner, Masquer, IA) ; onglets Propriétés (identifiant, nom, type, module, plateforme, version, statut),
  Provenance (origine, source, fichier, dates, validation, confiance), Relations (entrantes, sortantes, par type, niveau
  de confiance), Traçabilité (exigences, parcours, tests, plans, exécutions, anomalies à deux pas, « non confirmé » si le
  chemin ne passe pas par des liens confirmés), Historique (création, modification, validation, fusion, déclaration).
