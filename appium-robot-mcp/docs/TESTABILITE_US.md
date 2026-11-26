# Testabilité des User Stories — stratégie actionnable

Une politique de la stratégie de test du projet : chaque US des espaces Jira activés (projets des squads) doit être
comprise, clarifiée puis couverte par au moins un test du projet Xray cible.

## Où
- Politique (espaces Jira) et file de travail : **Test Design › US à couvrir** ; résumé dans **Test Strategy › Vue d'ensemble**.
- Moteur : `atelier/intelligence/testabilite_us.py` ; IA : `atelier/intelligence/fournisseur_ia.py`.
- Données (dans le repository du projet) : `testabilite/espaces.yaml`, `testabilite/us.json`, `testabilite/journal.jsonl`.

## Par sprint : le backlog du sprint est le périmètre de test
Les équipes sont agiles : au démarrage de chaque sprint, le backlog construit par le PO dit ce qui va être développé,
donc ce qui doit être testé. Portée par espace :
- **sprint actif** (défaut) : tout le backlog du sprint en cours, quel que soit le statut des US ;
- **sprint actif + sprint suivant** : préparer les questions et les cas pendant le planning ;
- **statuts** : ancien mode, sans sprint.

Rituels proposés :
1. **Planning / démarrage** : « Détecter le backlog du sprint », puis « Figer le périmètre du sprint » (photo immuable).
2. **Pendant le sprint** : analyse, questions aux squads, réponses, cas de test, publication dans Xray ; une nouvelle
   détection signale les US ajoutées et retire l'étiquette du sprint aux US sorties du backlog (historisé).
3. **Revue / fin de sprint** : « Bilan du sprint » : couverture du backlog, US non couvertes, en attente de réponse,
   tests créés, US ajoutées ou retirées depuis le gel.

Sprints lus par l'API Jira Software (`/rest/agile/1.0/board?projectKeyOrId=`, `/board/{id}/sprint`), tableaux Scrum ;
si cette API est inaccessible, repli sur le JQL `sprint in openSprints()` (sans nom de sprint) et avertissement à l'écran.

## Cycle d'une US
`Détectée → Analysée → Questions envoyées → Réponses reçues → Cas proposés → Couverte`
(`Couverte (existant)` si des tests sont déjà liés ; `Non testable` avec justification ; alerte si l'US change dans Jira).

| Étape | Action | Écriture externe |
|---|---|---|
| Détection | JQL par espace (types, statuts, complément) ; tests déjà liés lus | aucune (lecture Jira) |
| Analyse par règles | description courte, critères absents, termes vagues, « à définir », cas d'erreur, données, rôle — chaque constat cite la règle et l'extrait | aucune |
| Analyse IA | selon `IA_FOURNISSEUR` ; texte masqué avant envoi ; propositions à valider | aucune |
| Questions | brouillon relu et modifiable, envoi explicite en commentaire Jira (marqueur « [Atelier QA] ») | commentaire Jira |
| Réponses | commentaires postérieurs à l'envoi (horloge de Jira), hors ceux de l'atelier | aucune |
| Cas de test | squelettes par règles (un par critère + cas d'erreur) ou IA ; édition ; validation exigeant action et résultat attendu | aucune |
| Publication | cas validés créés dans Xray (Manual avec étapes, ou Cucumber) + lien de couverture vers l'US | Xray + lien Jira |

## Fournisseur d'IA (`IA_FOURNISSEUR`)
- `aucun` (défaut) : règles seulement.
- `cursor` : l'agent Cursor utilise les outils MCP `testabilite_us_a_traiter` puis `testabilite_deposer_proposition` ;
  l'atelier n'appelle aucun modèle.
- `interne` : LLM de l'entreprise, API compatible OpenAI : `IA_INTERNE_URL` (ex. `https://llm.interne/v1`),
  `IA_INTERNE_MODELE`, jeton `IA_INTERNE_JETON` (environnement ou coffre), certificat `IA_INTERNE_CA_BUNDLE`.
- `anthropic` : seulement si l'entreprise l'autorise (`ANTHROPIC_API_KEY`).

## À vérifier à l'essai réel (sur une US de test dédiée)
- `createTest(steps: [CreateStepInput])` pour un test Manual : contrôlé par `python -m atelier xray-verifier`.
- Commentaires Jira : `POST /rest/api/3/issue/{key}/comment` (ADF), `GET …/comment`.
- Lien de couverture : type `JIRA_LIEN_COUVERTURE` (défaut « Test »), sens « <test> tests <US> » ; les projets des
  squads doivent être déclarés comme projets d'exigences dans les réglages Xray pour que la couverture y soit comptée.
- Droits du compte API : lire et commenter dans les projets des squads.
