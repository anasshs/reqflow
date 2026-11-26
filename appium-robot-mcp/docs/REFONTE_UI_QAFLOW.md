# Refonte de l'interface : QAFlow

Statut : **cadrage**, 2026-11-25 (demande de l'utilisateur, maquettes « QAFlow » en 13 écrans et spécification en 11 points).
Principe retenu par l'utilisateur : **garder l'interface actuelle, ajouter la nouvelle à côté** (raccourci dans l'en-tête),
puis basculer quand elle est rodée.

## 1. Ce que la nouvelle interface doit faire comprendre immédiatement

1. **Sur quoi je travaille ?** L'application, sa version, son environnement, et les parcours concernés.
2. **Que puis-je faire ?** Concevoir un parcours, ou automatiser un test.
3. **Quels résultats sont disponibles ?** Parcours, BDD, JDD, Knowledge Graph, scripts, campagnes, exécutions.

Aucun ordre imposé, aucun pourcentage global : les statuts sont portés par les objets (parcours, scénario, test,
exécution, tâche IA) et chacun a une signification précise (§ 5).

## 2. Coexistence avec l'interface actuelle

| | Interface actuelle | QAFlow (nouvelle) |
|---|---|---|
| Adresse | `/plateforme` (et `/` classique) | **`/qaflow`** |
| Fichiers | `static/plateforme.*`, `ecran_*.js` | **`static/qaflow/`** (html, css, js), aucun fichier de l'ancienne modifié hormis le raccourci |
| Serveur, session, comptes | — | **les mêmes** : même FastAPI, même cookie de session (`/qaflow` ajouté aux pages de `securite.PAGES`), mêmes rôles |
| API | `/api/*` | **les mêmes `/api/*`** ; les seuls ajouts sont des **agrégats de lecture** `/api/qaflow/*` (une vue = un appel) |
| Moteurs | `atelier/*` | **inchangés** : aucune logique métier dans la nouvelle interface (règle d'architecture du projet) |
| Passage de l'une à l'autre | bouton « Nouvelle interface (QAFlow) » dans l'en-tête | bouton « Interface actuelle » ; chaque écran QAFlow pas encore refait renvoie vers l'écran existant (`/plateforme#…`) |

**Bascule** (fin du chantier, décision de l'utilisateur) : `/` et la connexion mènent à `/qaflow` ; `/plateforme` reste
joignable tant qu'un écran n'a pas d'équivalent. Critères : tous les écrans des maquettes livrés, aucun renvoi vers
l'ancienne interface pour le travail courant (concevoir, automatiser, exécuter, release notes), une campagne TNR réelle
menée de bout en bout dans QAFlow, tests Playwright des parcours principaux verts.

## 3. Écrans des maquettes et ce qui existe déjà

| # | Écran | Ce que l'atelier sait déjà faire | À ajouter |
|---|---|---|---|
| 1 | **Accueil – bulle application** (nom, version, environnement ; centre d'exécution, dernières exécutions, release notes) | `/api/contexte` (application, version = build, environnements, projet), `/api/centre/vue`, `/api/executions`, `/api/releases` | agrégat `/api/qaflow/accueil` (une seule lecture) ; bulle et animation |
| 2 | **Choix des voies** Concevoir / Automatiser | — (navigation) | écran |
| 3A | **Concevoir – Ajouter un parcours** | cadrage d'un parcours (`/api/discovery/cadrage`), session Discovery assistée (`/api/discovery/sessions`), MCP qui explore et propose | assistant en 5 étapes de la maquette (module → démarrer → tester → capturer → générer) branché sur cadrage + session |
| 3A.1 | **Session manuelle assistée par l'IA** (écrans, actions, composants, transitions capturés en direct, minuteur) | session Discovery : événements, écrans visités, transitions (`/api/discovery/sessions/{sid}`), flux d'événements (WebSocket) | compteurs en direct ; miroir de l'écran du téléphone (capture existante `/api/mcp/image`) |
| 3A.2 | **Parcours créé et enrichi** (scénarios, JDD, écrans, nœuds du graphe ; prochaines étapes) | fin de session : écrans du parcours, propositions à valider (`discovery_terminer`), BDD depuis le parcours (`/api/discovery/parcours-bdd`), JDD proposés | agrégat du parcours (`/api/qaflow/parcours/{id}`) ; « prochaines étapes » = ce qui manque réellement (pas une liste figée) |
| 3B | **Consulter les parcours** (statut, BDD, JDD, écrans, graphe, tests associés) | parcours (`parcours_utilisateur.lister`), scénarios par parcours (`bdd.lister`), écrans du parcours, implémentations par technologie (`perimetre._implementations`) | agrégat `/api/qaflow/parcours` (une ligne par parcours, chiffres réels) |
| 3B+ | **Espace de travail d'un parcours** (description, étapes, écrans et actions, MBT, BDD, JDD, automatisations, historique) | tout existe en écrans séparés : cadrage, carte, MBT (`/api/mbt/modele`, intégré à l'analyse), BDD, JDD, tests automatisés, exécutions | un écran à onglets qui réunit ces vues **sans** en faire des modules à part ; le MBT y est un onglet d'analyse, pas un outil à manipuler |
| 4 | **Automatiser – saisir la référence** (User Story, test existant, parcours, expression libre ; options) | points d'entrée parcours / US / Test Plan (`/api/automatisation/perimetre`), technologies, dépôt de la demande pour le MCP (`/api/automatisation/lancer`) | entrées « test existant » (une clé Xray) et **« expression libre »** (texte → demande au MCP qui cherche l'existant puis conçoit le scénario) ; options « rechercher l'existant » / « générer et valider automatiquement » |
| 5 | **Automatisation en cours** (étapes réelles : analyse, Knowledge Graph, composants, POM et locators, script, exécution et correction, validation, rangement TNR) | travaux de l'orchestrateur avec étapes et statuts (`/api/travaux/{id}`), demande à l'agent suivie (`/api/demandes`) | consigne de la demande découpée en étapes nommées comme la maquette ; vue de suivi |
| 5A.1 | **Automatisation terminée** (script, emplacement dans le référentiel TNR, exécuter, voir le script) | génération écrite et mise en revue, chemin du fichier, `run_tests`, éditeur de code | écran de résultat ; **les trois notions séparées** (§ 5.2) |
| 7 | **Centre d'exécution** (en cours, réussis, échecs, total ; exécutions récentes : nom, type, environnement, statut, date) | Execution Center (`/api/centre/vue`, `/api/centre/file`, `/api/executions`), Xray (`/api/centre/executions-xray`) | vue QAFlow ; statut « Bloqué » et « Annulé » ajoutés à l'affichage s'ils manquent |
| 8 | **Centre de release notes** (importer, analyse IA, impacts, adaptation TNR, tests complémentaires, préparation d'exécution ; releases récentes) | Releases complet : création, Release Note, interprétation par l'IA, impacts, périmètre retest / ciblé / qualification, plan (`/api/releases/*`) | dépôt de fichier (PDF, DOCX, TXT, MD) → texte ; présentation « proposé / retiré / ajouté » avec la raison de chaque test |
| 9 | **Nouvelle demande** (retour à l'accueil, compteurs à jour) | — | navigation |
| — | **Menu latéral permanent** : tests manuels, tests automatisés, planification (plans), exécutions, résultats et anomalies, rapports | écrans existants : patrimoine Xray, `#tests`, campagnes / plans, `#centre`, Failure Analysis, rapports | au début : liens vers les écrans existants (`/plateforme#…`) ; refaits un par un |
| — | **Centre d'activité IA** (icône permanente de l'en-tête) | Mes demandes : travaux + boîte de l'agent, états, étape courante, avancement, à décider (`/api/demandes`) | panneau QAFlow avec étapes, livrables intermédiaires, erreurs et actions attendues (§ 6) |
| — | **Knowledge Graph** (accès permanent, connaissance vivante) | Knowledge Graph et espaces (`/api/graphes/*`), suivi en direct | lien permanent ; jamais présenté comme une étape à terminer |

## 4. Agrégats de lecture à ajouter (`/api/qaflow/*`)

Routes minces (adapter web), qui n'appellent que des moteurs existants ; aucune écriture.

| Route | Contenu |
|---|---|
| `GET /api/qaflow/accueil` | application (nom, slug, version, environnement, plateformes), compteurs du centre d'exécution (en cours, réussis, échecs, total), 5 dernières exécutions, dernière release, tâches IA actives |
| `GET /api/qaflow/parcours` | par parcours : statut métier (§ 5), scénarios BDD (total / validés), JDD (associés / manquants), écrans, enrichissement du graphe (liens validés / à valider), tests automatisés par technologie, dernière exécution |
| `GET /api/qaflow/parcours/{id}` | espace de travail : cadrage, étapes ordonnées, écrans et actions (carte), modèle MBT résumé, scénarios, JDD, automatisations, historique d'exécution |
| `GET /api/qaflow/activite` | tâches IA et MCP (travaux + demandes) avec étapes, dépendances, livrables, erreurs, action attendue |

## 5. Statuts : un vocabulaire, une signification

### 5.1 Statuts métier (objets : parcours, scénario, test, campagne)

Quatre statuts, pas plus (décision de l'utilisateur du 2026-11-25 : « pas trop de statuts »).

| Statut QAFlow | Signification | Correspondance existante |
|---|---|---|
| À faire | rien n'est engagé | parcours « Brouillon » sans session ; scénario sans étape |
| En cours | travail engagé ou éléments manquants (la liste des manques s'affiche sous le statut, pas comme un statut) | parcours « En cours », « Prêt », « Exploré » incomplet ; contrôles BDD de gravité haute ; `a_implementer` |
| À valider | livrables disponibles, attendent une validation humaine | revue « Généré » ; propositions « à valider » ; parcours « Exploré » complet |
| Validé | validation explicite réalisée | parcours « Validé » ; scénario `validé` ; revue « Approuvé » / publication Xray |

Pendant une session assistée, le miroir de l'écran a trois modes : **Naviguer** (toucher, classé côté serveur),
**Saisir** (la valeur tapée devient une donnée du jeu du parcours, saisie par sa référence, secret au coffre) et
**Vérifier** (texte affiché ou présence d'un élément : assertion du scénario, valeur attendue rangée au jeu). Données,
saisies et vérifications se corrigent ensuite dans l'onglet « Jeux de données » du parcours.

Jeux de données : **Validé** (le jeu existe dans `data/jdd/<env>.yaml`), **À faire** (référencé mais absent, ou étape
qui consomme une donnée sans jeu), **À valider** (donnée proposée par l'IA pendant une session, à confirmer).

Un blocage (donnée bloquée, appareil absent, installation refusée, décision attendue) n'est pas un statut : c'est une
**alerte** affichée sur l'objet, avec sa raison et l'action qui le lève.

### 5.2 Trois notions distinctes pour un test automatisé

| Notion | Preuve dans l'atelier |
|---|---|
| **Généré par l'IA** | fichier écrit et entré en revue (« Généré ») |
| **Exécuté techniquement** | « Vérifié » : run réel postérieur à la dernière modification (dry-run et compilation n'en sont pas) |
| **Validé par la QA** | approbation de la revue / publication au TNR par l'automaticien |

Une génération réussie n'est jamais affichée comme « validé ».

### 5.3 Statuts techniques des tâches IA et MCP

En cours · Action requise · Terminé · Échoué — correspondance avec les travaux : `a_faire` / `en_attente` / `en_cours` /
`attente_ressource` → En cours (l'étape courante dit ce qui est attendu) ; `attente_decision` / `a_decider` → Action requise ;
`termine` → Terminé ; `echec` → Échoué ; `annule` → retiré de la liste. Une tâche échouée garde les livrables des étapes réussies (déjà vrai pour les
travaux : chaque étape a son résultat).

## 6. Centre d'activité IA

Icône permanente dans l'en-tête (compteurs : en cours, à décider). Le panneau liste chaque tâche : application,
type d'opération, statut technique, début / fin, **étapes réelles** (pas de pourcentage), dépendances, livrables
intermédiaires (scénarios, fichiers, écrans), erreurs, action attendue (bouton qui mène à la décision). Les tâches
indépendantes s'affichent en parallèle ; une tâche dépendante dit ce qu'elle attend. Source : `/api/demandes`
(travaux de l'orchestrateur et demandes de la boîte), étendu par `/api/qaflow/activite`.

## 7. Phases (une à la fois)

| Phase | Contenu | Fini quand |
|---|---|---|
| **Q0. Coquille et raccourci** | `/qaflow` (session et cookie), en-tête (contexte application / version / environnement, Centre d'activité, retour à l'interface actuelle), menu latéral (liens vers les écrans existants), accueil à bulle, choix Concevoir / Automatiser ; raccourci dans l'interface actuelle | la nouvelle interface s'ouvre, montre le contexte réel et mène partout ; l'ancienne est intacte |
| **Q1. Concevoir** | consulter les parcours (agrégat), espace de travail d'un parcours, ajouter un parcours (assistant + session assistée en direct), parcours créé et enrichi | un parcours conçu de bout en bout depuis QAFlow |
| **Q2. Automatiser** | référence (US, test existant, parcours, expression libre), automatisation en cours (étapes), automatisation terminée (trois notions) | un test automatisé depuis chaque type de référence |
| **Q3. Centre d'activité et centre d'exécution** | panneau d'activité complet, centre d'exécution QAFlow | toutes les opérations longues suivies sans quitter l'écran courant |
| **Q4. Release notes** | import de fichier, analyse, périmètre argumenté modifiable, préparation de la campagne | une campagne de non-régression préparée depuis une Release Note |
| **Q5. Menu latéral refait** | tests manuels, tests automatisés, plans, exécutions, résultats et anomalies, Knowledge Graph dans QAFlow | plus aucun renvoi vers l'ancienne interface pour le travail courant |
| **Q6. Bascule** | `/` mène à QAFlow, critères du § 2 | décision de l'utilisateur |

## 8. Règles de réalisation

- Aucune logique métier dans `static/qaflow/` ni dans les routes `/api/qaflow/*` : lecture et assemblage seulement.
- Le contexte (application, version, environnement, module choisi) est gardé pendant toute la navigation (état de la
  page + `localStorage` pour le confort, jamais pour la donnée).
- Toute opération longue passe par une tâche (travail de l'orchestrateur ou demande de la boîte) : jamais d'appel
  bloquant depuis l'interface.
- Thème sombre des maquettes par défaut, thème clair disponible ; accessibilité (contrastes, clavier, libellés).
- Tests : un test Playwright par écran livré (page locale, API simulées comme pour l'interface actuelle).
