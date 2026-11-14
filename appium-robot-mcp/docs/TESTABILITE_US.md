# Testabilité des User Stories — stratégie actionnable

Une politique de la stratégie de test du projet : chaque US des espaces Jira activés (projets des squads) doit être
comprise, clarifiée puis couverte par au moins un test du projet Xray cible.

## Où
- Politique (espaces Jira) et file de travail : **Test Design › US à couvrir** ; résumé dans **Test Strategy › Vue d'ensemble**.
- Moteur : `atelier/intelligence/testabilite_us.py` ; IA : `atelier/intelligence/fournisseur_ia.py`.
- Données (dans le repository du projet) : `testabilite/espaces.yaml`, `testabilite/us.json`, `testabilite/journal.jsonl`.

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
