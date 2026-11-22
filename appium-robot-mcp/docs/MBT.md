# Model-Based Testing (MBT) : audit, architecture, plan

Cahier : « MODEL-BASED TESTING (MBT) – QAFlow ». Principe : l'utilisateur exprime le besoin, l'atelier comprend le
comportement, explore les possibilités et propose les tests. Le MBT est une intelligence intégrée, pas un outil de
modélisation de plus : mode automatique par défaut, interface avancée (« Analyser le comportement ») à la demande.

## 1. Audit de l'existant (lot 1)

| Composant | Existant | Réutilisé pour le MBT |
|---|---|---|
| Knowledge Graph (`atelier/discovery/connaissance.py`, `espaces.py`) | Écrans, actions en nœuds (écran → permet → action → aboutit à → écran), navigations observées, modules, parcours avec complétude, règles, US, tests BDD et ponts, provenance / confiance des liens, cache et relecture ciblée | Source principale du modèle comportemental ; reçoit les éléments du modèle (états, transitions, conditions, chemins) et leurs relations |
| Discovery (`atelier/discovery/carte`) | Transitions observées (`transitions.yaml` : de, vers, plateforme, action, essais, réussites, interdite) ; états visuels d'un écran (`etats`) | États « écran » et transitions observées |
| Exigences (`testabilite_us.py`, `intelligence_app.structurer`) | Critères d'acceptation structurés en condition / action / résultat, par motifs explicites (sans IA) | Conditions métier et états d'erreur proposés (déduits, à valider) |
| Générateur de cas d'US (`conception_avancee.proposer`) | Cas par catégorie (nominal, alternatif, négatif…), source, confiance, manquant, doublons | Mode automatique : les chemins du modèle y ajoutent des cas complémentaires (origine US + MBT) |
| Référentiel BDD (`generation/bdd.py`) | Modèle YAML + `.feature`, éditeur, contrôles, branches alternatif / négatif, génération Robot | Unique référentiel : un chemin devient un scénario BDD (même format, même éditeur) |
| Doublons (`couverture.doublons_bdd`, `conception_avancee.doublons`) | Comparaison par le contenu (étapes, actions, résultats, écrans, données) | Classement Doublon / Variante / Redondance partielle / Complémentaire / Nouveau, enrichi par les transitions parcourues |
| Couverture (`couverture.couverture_atelier`) | Couverture sans Xray, liens confirmés seulement | + couverture comportementale : modèle, conception, automatisation, exécution, validée |
| Impact (`connaissance.analyser_impact`) | Direct / indirect / potentiel, TNR sans Xray | + versions du modèle comparées, scénarios impactés |
| Robot Framework (`depot_robot`, tags) | Test Robot relié au test BDD par tag | Couverture d'automatisation ; correspondance action → locator → keyword (lot 7) |
| IA (`fournisseur_ia`, `ia/orchestrateur`, journal) | Point d'appel unique, coûts journalisés par opération, Cursor via MCP | Propositions d'états / transitions / conditions (opération « conception.mbt »), toujours à valider |

Ce qui manquait : un modèle de comportement distinct du graphe (états métier ≠ écrans), des conditions réutilisables,
un moteur d'exploration de chemins et des stratégies de couverture, la traçabilité modèle → chemin → scénario.

## 2. Architecture

Trois notions connectées, jamais confondues :

- **Knowledge Graph** : ce que l'atelier connaît de l'application (inchangé) ;
- **Behavior Model** (`atelier/domain/comportement.py`, fichiers `comportement/<id>.yaml`) : comment l'application doit
  se comporter, sur un périmètre (application, module, fonctionnalité, parcours, US, écran) ; versionné ;
- **Test Model** (`atelier/intelligence/mbt.py`) : comment le vérifier systématiquement : chemins, stratégies,
  couverture, génération BDD.

Pas de nouveau graphe indépendant ni de cinquième perspective : les éléments du modèle entrent dans le Knowledge
Graph (types `modele_comportement`, `etat`, `transition`, `condition`, `chemin`) et s'ouvrent depuis les perspectives
existantes (Utilisateur, Tests & Qualité, Tout ; action « Analyser le comportement » sur un élément).

### Structures (correspondance avec le cahier)

| Cahier | Atelier |
|---|---|
| Behavior Model : id, project_id, application_id, name, description, scope_type, scope_id, application_version, model_version, status, provenance, created_at, updated_at | `id`, `projet`, `application`, `nom`, `description`, `perimetre.type`, `perimetre.id`, `version_application`, `version`, `statut` (Draft, In Review, Validated, Deprecated), `provenance`, `cree`, `maj` |
| State : name, description, state_type, associated_screen_id, business_context, is_initial, is_final, provenance, confidence, validation_status | `etats[id]` : `nom`, `description`, `type` (metier, ecran, systeme, erreur), `ecran`, `contexte`, `initial`, `final`, `provenance`, `confiance`, `validation` |
| Transition : source, target, action, event, guard_condition, business_rule, preconditions, expected_postconditions, priority… | `transitions[id]` : `de`, `vers`, `action`, `evenement`, `garde` (id de condition) et `issue` (vraie / fausse), `regle`, `preconditions`, `postconditions`, `priorite` |
| Action : écran, composant, locator, keyword, endpoint | `actions[id]` : `libelle`, `ecran`, `cle`, `locator`, `keyword`, `endpoint` |
| Condition / règle métier réutilisable | `conditions[id]` : `libelle`, `regle`, utilisée par plusieurs transitions |

Provenance : observé / déclaré / déduit. Confiance (indépendante) : confirmée / probable / non vérifiée. Validation :
validé / à valider / rejeté. Chaque élément garde `source`, `justification`, `cree`, `maj`, `auteur`. Les éléments non
confirmés servent au mode exploratoire, jamais à la couverture, l'impact ou la non-régression officiels.

### Construction progressive (jamais de modélisation manuelle complète)

1. Discovery / Knowledge Graph : un état « écran » par écran du périmètre, une transition par navigation observée
   (action reprise du nœud action), états initiaux (aucune entrée dans le périmètre) et finaux (aucune sortie).
2. User Stories : chaque critère d'acceptation structuré donne une condition (déduite, à valider) ; un critère négatif
   donne un état d'erreur et une transition gardée (issue « fausse »), résultat attendu « à confirmer » tant qu'aucune
   exigence ne le précise. Aucune règle inventée : ce qui manque est listé (« informations manquantes »).
3. Règles métier du graphe : conditions candidates rattachées au périmètre.
4. Déclarations : états, transitions, conditions ajoutés ou corrigés par le QA (déclarés, confirmés).
5. IA : états manquants, transitions possibles, conditions alternatives, incohérences ; déposés « à valider ».

À chaque reconstruction : les éléments observés sont rafraîchis, les déclarations et validations conservées ; si le
contenu change, la version précédente est archivée (`comportement/versions/<id>/v<n>.yaml`) et la version augmente.

### Moteur (déterministe)

Accessibilité depuis les états initiaux, états inaccessibles, impasses, boucles, transitions inutilisées. Stratégies :
couverture des états, des transitions, des paires de transitions, des conditions (deux issues), des chemins (simples,
une boucle au plus), des chemins critiques (priorité, état final atteint). Limites internes (profondeur, nombre de
chemins, transitions par scénario, passages par boucle), réglables dans le mode avancé. Chaque chemin : identifiant
stable, description, états, transitions, conditions, priorité, justification, informations manquantes, scénario BDD
existant, préparation à l'automatisation.

### Génération BDD

Un chemin devient un scénario du référentiel BDD existant (même modèle, même éditeur, mêmes contrôles), avec la
traçabilité `mbt` : model_id, model_version, state_ids, transition_ids, action_ids, condition_ids, source_path_id,
coverage_strategy, related_user_story_ids, generation_origin (US_AI, MBT, US_MBT, Manual), generation_date. Doublons
vérifiés avant création ; aucune fusion automatique. Un résultat attendu non confirmé est écrit « (à confirmer) ».

## 3. Plan

| Lot | Contenu | État |
|---|---|---|
| 1 | Audit et architecture (ce document) | fait |
| 2 | Behavior Model : structures, stockage versionné, construction depuis le graphe et les US, provenance et validation, intégration au Knowledge Graph | fait |
| 3 | Moteur : exploration, boucles, stratégies, priorisation, chemins manquants, réduction des redondances | fait |
| 4 | Intégration BDD : génération depuis un chemin, traçabilité, doublons | fait |
| 5 | UX : mode automatique dans la génération des cas d'US, « Analyser le comportement », Model-Based Test Designer, outils MCP | fait |
| 6 | Couverture comportementale (modèle, conception, automatisation, exécution, validée) et impact entre versions | fait |
| 7 | Automatisation : action → locator → keyword → données, préparation par chemin | fait |

## 4. Références

- Skill « model-based-testing » (naodeng/awesome-qa-skills) : référence méthodologique seulement. Licence annoncée
  PolyForm Noncommercial 1.0.0 : aucun fichier ni code repris ; les instructions de l'atelier sont écrites de façon
  indépendante.
- GraphWalker : référence technique (états / transitions, générateurs de chemins, conditions d'arrêt). Non intégré :
  le moteur de l'atelier est en Python standard, sans dépendance, sur les fichiers du projet.

## 5. Où le trouver

- **Mode automatique** (défaut) : Test Design › une US › « Proposer par catégories » : l'option « Analyse comportementale :
  Automatique » ajoute les chemins non couverts (cas « navigation », « alternatif », « négatif », origine US + MBT) et
  signale les scénarios existants réutilisables. « Désactivée » : génération classique seule.
- **Mode avancé** : « Analyser le comportement » sur un élément du Knowledge Graph (application, module, fonctionnalité,
  parcours, US, écran, règle) ou sur une US de Test Design ; écran `#comportement` (périmètre, modèle, analyse,
  stratégie, chemins, génération BDD).
- **Couverture** : Knowledge Graph › Couverture, bloc « Comportement » (parcours identifiés et couverts, transitions et
  conditions non vérifiées, scénarios manquants) ; cinq niveaux par modèle dans l'analyse.
- **Impact** : l'analyse d'impact d'un écran, d'une action, d'un locator ou d'un keyword cite les modèles, transitions et
  scénarios générés concernés ; la comparaison de deux versions d'un modèle donne les scénarios impactés et les actions.
- **Cursor / Claude** (MCP) : `mbt_modele`, `mbt_chemins`, `mbt_deposer_propositions` (à valider), `mbt_generer_bdd`.
- **IA** : opération « conception.mbt » (Pilotage IA : réglable, coût journalisé).

## 6. Critères d'acceptation (cahier § 20)

| # | Critère | Où |
|---|---|---|
| 1 | Exploite le Knowledge Graph | `mbt.construire` (écrans, actions, transitions, règles, US du graphe) |
| 2 | Construction progressive | fusion : déclarations, corrections, décisions gardées ; versions |
| 3 | États et transitions depuis Discovery | nœuds action / aboutit_a de la carte |
| 4 | Règles enrichies depuis les US | critères structurés → conditions, refus (déduits) |
| 5 | IA sans validation automatique | `deposer_propositions` : déduit, à valider ; une IA ne valide jamais |
| 6 | Chemins nominaux et alternatifs | `analyser`, types nominal / alternatif / négatif |
| 7 | Stratégies | états, transitions, paires, conditions, chemins, critiques |
| 8 | Chemins justifiés | justification, manquant, priorité par chemin |
| 9 – 10 | BDD depuis MBT, référentiel existant | `mbt_bdd.generer` → `bdd.sauver`, éditeur Tests BDD |
| 11 | Traçabilité | champ `mbt` du scénario, chemins générés du modèle, relations du graphe |
| 12 | Doublons | `mbt_bdd.classer` (Doublon … Nouveau) |
| 13 | Couverture conception / automatisation / exécution | `mbt.couverture` (cinq niveaux) |
| 14 | Scénarios impactés par une évolution | `mbt.impact` (versions), `impact_element` |
| 15 | Génération US inchangée | `conception_avancee.proposer` (comportement « desactive » = comportement historique) |
| 16 | Sans Xray | aucune dépendance (graphe, BDD, Robot) |
| 17 – 18 | Mode standard transparent, mode avancé | option automatique ; écran `#comportement` |
| 19 | Cache et actualisation | analyses en cache (modèle, version, BDD, résultats) ; graphe relu au fichier près |
| 20 | Coût IA mesurable | opération `conception.mbt` dans le journal de l'orchestrateur |

Limites assumées : Playwright et Cypress ne sont pas encore générés par l'atelier (la préparation à l'automatisation
l'indique : cible Robot seule) ; l'édition du modèle se fait par formulaires (pas de glisser-déposer de transitions).

## 7. Évolution « moteur d'analyse comportementale »

| Cahier | Réalisation |
|---|---|
| § 2 Niveaux | `comportement.niveau` : Confirmé (exigence, règle explicite, décision du QA), Observé, Déduit, À confirmer, Rejeté. Établis = Confirmé + Observé (seuls dans les indicateurs officiels). Un rejet n'est jamais reproposé (éléments et hypothèses). États métier distincts des écrans (types métier, système, erreur rattachés à un écran). |
| § 3 Transition | état initial, événement (« clic sur … »), condition, action, état résultant, résultat attendu (et celui de l'exigence), source, niveau, exigences liées. Conditions mutualisées (`condition_commune`). Le critère « Si X, refus » donne la condition X (Confirmé), sa transition de refus (issue vraie) et, sur la transition nominale, l'issue contraire. Issue contraire non décrite : hypothèse « à confirmer ». |
| § 4 Exceptions | `mbt._hypotheses` : session expirée, perte de connexion, double soumission, retour arrière, annulation, interruption, reprise, accès non autorisé, formulaire invalide, issue contraire. Seulement si non documentées ; accepter = élément À confirmer sans résultat inventé ; rejeter = jamais reproposée. |
| § 5 Chemins | cibles établies d'abord ; ce que les scénarios existants couvrent n'est pas reciblé (« réutilisés ») ; minimisation gloutonne (le minimum de chemins) ; « valeur ajoutée » par chemin ; drapeau « hypothèse ». |
| § 6 Traçabilité | `mbt.tracabilite(cle)` : exigence → Knowledge Graph → modèle → transitions → chemin → scénario → automatisation → exécution ; tag `a_confirmer` sur le scénario. |
| § 7 Automatisation | `preparation` : locators, keywords existants, Page Object, données (champs sans variable ni jeu), préconditions, environnements ; « prêt » seulement si tout est là. |
| § 8 Incrémental | `actualiser_tous` (au changement du projet), `evolutions` (états, transitions, conditions, chemins, scénarios, automatisations, révisions proposées) ; TNR : scénarios touchés par des éléments établis ; les autres « à examiner ». |
| § 9 Dashboard | section « Couverture comportementale » (états, transitions, issues vérifiés / établis ; chemins couverts / retenus ; inconnus ; réutilisés ; générés ; impactés) et cinq niveaux : conception, scénarios BDD, automatisation, exécution, validée. |
| § 10 Modes | automatique (cas d'une US), assisté (Synthèse de l'écran Analyse comportementale), expert (Modèle, Analyse, Comportements manquants, Stratégie, Chemins, Génération, Évolutions et impact). |
