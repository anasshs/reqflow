# Release Notes : du texte collé au périmètre de non-régression

Première étape du module « Release Intelligence & Impact Analysis » (cahier de l'utilisateur du 2026-11-20). Le QA colle
le texte d'une Release Note ; l'atelier en tire des évolutions, les rattache au Knowledge Graph, et une release validée
alimente le TNR existant. Aucun second moteur d'impact : la release est une source d'évolutions de plus.

Où : **Dashboard › Release Notes**, au-dessus de « Intelligence de non-régression (TNR) » (`#dashboard/releases`).

## Le parcours

1. **Coller** le texte (et, si l'on veut, un nom). Un texte identique à une release déjà enregistrée est refusé.
2. **Lecture par des règles, sans IA** (`releases.analyser_texte`) : version, date, clés Jira citées, et une évolution par
   puce ou par ligne. Le type (nouvelle fonctionnalité, modification, correction, évolution technique, suppression)
   vient du titre de rubrique au-dessus, sinon des mots de la ligne, sinon « modification ». Chaque évolution garde la
   ligne dont elle vient ; le texte d'origine est conservé tel quel.
3. **Rattachement au Knowledge Graph**, évolution par évolution :

| Cas | Ce que fait l'atelier |
|---|---|
| Une clé d'US, de bug ou d'epic est citée et connue du graphe | Rattachement certain, fait d'office |
| Une clé est citée mais inconnue du graphe | Signalée « clé inconnue », jamais inventée |
| Aucune clé | Jusqu'à cinq éléments du graphe proposés par les mots communs : à confirmer ou rejeter |
| Rien ne correspond | « non rattachée », visible ; le QA peut la relier à la main |

   Une proposition n'est jamais un rattachement. Le préfixe des clés Jira et les mots présents dans trop d'éléments ne
   rapprochent rien.
4. **Corrections du QA**, toutes tracées dans le journal de la release : changer le type, corriger le texte (une clé
   d'US ajoutée rattache l'évolution), ajouter ou supprimer une évolution, confirmer, rejeter, relier, délier.
5. **Valider et envoyer au TNR** : les évolutions rattachées entrent dans l'analyse d'impact du TNR (tests obligatoires
   et complémentaires, avec « Release Note » dans le motif) ; celles qui ne le sont pas y figurent « hors graphe », et le
   TNR dit que sa sélection est partielle. Une release modifiée après validation repasse à « Analysée » : le TNR ne lit
   que du validé.

Pour chaque évolution rattachée, l'écran affiche les tests que l'analyse d'impact trouve ; « aucun test : à créer »
signale une évolution rattachée au graphe mais sans couverture.

## Qualification d'une release, build après build

Écran **Releases** (barre latérale, `#releases`). Structure : Release → Builds → analyse d'impact → périmètre de
non-régression → Test Executions → résultats de qualification. Moteur : `atelier/intelligence/builds.py`.

1. **Créer la release** : nom, version, date de livraison prévue, périmètre fonctionnel ; la Release Note se colle à la
   création ou plus tard (onglet « Périmètre initial »). Ses évolutions forment le périmètre initial.
2. **Recevoir un build** à chaque livraison : numéro (le suivant est proposé), date, description, contenu collé ou
   importé d'un fichier texte, anomalies corrigées (clés Jira), changements par rapport au précédent.
3. **Analyse du build**, comparée au build précédent et au périmètre initial : nouvelles évolutions, évolutions déjà
   livrées, corrections, anomalies à retester (déclarées, ou citées dans une correction) et leurs tests, fonctionnalités
   nouvellement impactées, éléments hors du périmètre initial, évolutions non rattachées.
4. **Périmètre en trois catégories**, chaque test avec sa raison : **Retest** (tests liés aux anomalies corrigées),
   **Non-régression ciblée** (impact direct sur l'élément touché, ou indirect par son module), **Qualification** (tests
   critiques par criticité ou étiquette). Le QA accepte, écarte (justifié) ou ajoute, puis **valide** : le périmètre est
   figé pour ce build.
5. **Exécution** : « Envoyer à Execution Center » crée une campagne avec les tests automatisés retenus (rien n'est
   lancé) ; les tests manuels s'exécutent dans Xray. Un test compte comme exécuté pour le build si son dernier résultat
   Xray est postérieur à la réception du build. « Actualiser depuis Xray », dans la vue du build, relit les Test Executions créées
   depuis la réception du build (statuts posés dans Xray) et recalcule les résultats ; la date de la dernière lecture
   est affichée.
6. **Verdict du build** : Passed ou Failed, déclaré par le QA ; Passed avec des échecs ou des tests non exécutés demande
   une justification.
7. **Anomalies du build** : corrigées (confirmé dans Jira), déclarées corrigées mais encore ouvertes, nouvelles,
   résiduelles (déjà ouvertes à la réception).
8. **Qualification de la release** : un build Passed ne qualifie pas la release. Critères de sortie évalués sur les
   résultats cumulés (dernier build Passed, aucune anomalie critique ouverte, retests et tests de qualification du
   dernier build réussis — bloquants ; périmètre exécuté, anomalies ouvertes — indicatifs). Le QA qualifie ; un critère
   bloquant non satisfait impose une dérogation justifiée, tracée comme telle. Un build modifié remet la qualification
   « En cours ».

Un nouveau build **remplace** le build encore en cours (Reçu, Périmètre validé, En exécution) : celui-ci passe à
« Remplacé », en consultation seulement (sa suppression rend la main au build remplacé). Un nouveau build remet aussi une
release qualifiée « En cours ». À l'ouverture d'une release, le build en cours s'ouvre directement.

Dans le périmètre, un test proposé est **retenu par défaut** : seul « Écarter » existe (avec un motif), y compris pour
plusieurs tests cochés à la fois. La raison s'affiche en court (« module Connexion », « retest DEMO-777 », « test
critique »…), le détail au survol. La colonne de résultat n'apparaît qu'une fois le périmètre validé, et les résultats
Xray sont relus automatiquement à l'ouverture d'un build en exécution (si la dernière lecture date de plus de 10 min).

Chaque build garde son analyse, son périmètre validé, sa campagne, son verdict et les anomalies ouvertes à sa
réception : on ne repart jamais de zéro. Le Dashboard affiche un résumé des releases.

## Interprétation par Cursor (par défaut)

Les règles découpent ligne par ligne et rapprochent par les mots ; elles ne comprennent pas le sens. L'interprétation de
la Release Note et de chaque build est donc confiée **par défaut à Cursor** (ou à l'IA à appel direct configurée) ; les
règles restent le secours, présentées comme telles.

- **Demandée d'office** : à la création d'une release avec sa Release Note, et à la réception d'un build, la demande part
  vers Cursor (mode d'envoi réglé dans Paramètres › Cursor / Claude). « Réinterpréter avec Cursor » la relance.
- **Ce que Cursor lit** (`release_a_interpreter`, lecture seule) : le texte masqué, les évolutions tirées par les
  règles, les éléments du Knowledge Graph (US, epics, bugs, écrans, modules, parcours, endpoints), le patrimoine de tests
  Xray (module, criticité, étiquettes, exigences, automatisé, dernier statut), les anomalies Jira et, pour un build, le
  périmètre des règles.
- **Ce qu'il dépose** (`release_deposer_interpretation`) : les évolutions (découpage, type) rattachées aux éléments du
  graphe ; pour un build, les tests à ajouter (retest, ciblée, qualification) ou à écarter ; une synthèse du risque.
  Chaque proposition a une justification.
- **Contrôlé par le serveur** : élément du graphe connu, test du patrimoine connu, action et catégorie connues,
  justification présente ; un rattachement rejeté par le QA n'est jamais réécrit ; un build au périmètre validé est
  refusé (le rouvrir). Les refus sont renvoyés et affichés.
- **Appliqué par défaut** : les rattachements comptent dans l'analyse d'impact (comparaison, périmètre, TNR) ; les tests
  ajoutés apparaissent avec l'impact « IA » et leur raison ; les tests écartés sont « écartés par l'IA », que le QA peut
  **Garder**. Le QA délie, garde, écarte, puis valide. Rien n'est écrit dans Jira ni Xray par l'IA.

Moteur `atelier/intelligence/release_ia.py` ; routes `GET /api/releases-ia/etat`, `POST /api/releases/{id}/interpreter`
(appel direct) ; outils MCP `release_a_interpreter` (L) et `release_deposer_interpretation` (P).

## Plan Xray de la release et Test Executions

- **Un Test Plan Xray par release**, créé à la demande (onglet « Plan Xray et exécutions ») ou à la première exécution.
- **Exécutions depuis un build**, bloc « Exécutions Xray » : découpage proposé **par type de test** (retest,
  non-régression ciblée, qualification), **par module fonctionnel** ou en une seule exécution. Possible **avant la
  validation du périmètre** ; les tests écartés n'y sont pas, ceux déjà dans une exécution du build sont signalés.
  Chaque exécution a un nom modifiable et **un environnement choisi** parmi ceux du projet Xray.
- Dans Xray : la Test Execution est créée avec ses tests et son environnement, rattachée au Test Plan ; les tests sont
  aussi ajoutés au plan. Les tests absents de Xray sont signalés et non envoyés ; une erreur Xray n'enregistre rien.
- **Dupliquer** une exécution pour un autre environnement : proposé seulement si le projet gère plusieurs
  environnements, et pas deux fois pour le même build, les mêmes tests et le même environnement.
- **Statuts depuis l'atelier** : TO DO, EXECUTING, PASSED, FAILED, BLOCKED par test, envoyés au test run Xray
  (noms de statuts du projet via `XRAY_STATUTS`) et gardés avec l'auteur et la date ; ils comptent dans les résultats du
  build (« Résultat pour ce build ») sans attendre la synchronisation Xray, sauf résultat Xray plus récent.

Moteur `atelier/intelligence/plan_release.py` ; routes `GET/POST /api/releases/{id}/plan`,
`GET /api/releases/{id}/builds/{b}/executions?decoupage=`.

## Où c'est

| Élément | Emplacement |
|---|---|
| Moteur | `atelier/intelligence/releases.py` |
| Alimentation du TNR | `releases.evolutions_tnr`, lu par `pilotage.evolutions` |
| Routes | `GET/POST /api/releases`, `GET /api/releases/{id}`, `POST /api/releases/{id}/operation`, `GET /api/releases/noeuds` |
| Écran | `releases()` dans `atelier/adapters/web/static/ecran_pilotage.js` |
| Données | `<projet>/releases/REL-AAAAMMJJ-xxxxxx.json` (dans le projet de tests, jamais dans le dépôt de l'atelier) |
| Builds et qualification | `atelier/intelligence/builds.py` ; écran `ecran_releases.js` ; routes `/api/releases/{id}/tableau`, `/qualifier`, `/builds`, `/builds/{b}/operation` |
| Tests | `tests/test_releases.py`, `tests/test_builds.py` |

## Ce qui n'est pas fait (suite du cahier)

- **Interprétation par Cursor** : faite (voir plus haut), mais pas encore essayée sur un vrai projet ; le découpage de
  l'exécution Xray (par type, par module) reste proposé par les règles.
- **Teams** : ni lecture du canal, ni notifications. Les notifications de changement de Microsoft Graph demandent une
  adresse publique, incompatible avec l'écoute sur 127.0.0.1 : la lecture se fera par interrogation périodique, une
  fois l'accès accordé par l'administrateur Microsoft 365.
- **Import de fichiers** : texte seulement (.txt, .md, .csv, lu dans le navigateur) ; PDF, Word et Excel ne sont pas lus.
- **Sources Jira** (release, sprint) comme point de départ.
- **Critères de sortie configurables** par release : ils sont fixes pour l'instant.
- **Score de risque**, catégorie « tests à créer » transmise à Test Design, indicateurs dédiés.
- **Essai réel** du plan et des exécutions sur un projet Xray (les tests simulent Xray).
