# V2 — Phase 1 : Parcours de fonctionnalité

## Existant réutilisé
Les 10 étapes existaient déjà comme modules séparés (Discovery, Coverage Intelligence, couverture des exigences,
Test Design « À concevoir », revue de conception, Automation Studio, qualification 3 runs, Execution Center, Failure
Analysis, boîte À valider). Le parcours ne les remplace pas : il les relie, sans dupliquer leurs données.

## Modèle (`<projet>/parcours/PF-AAAAMMJJ-xxxxxx.json`)
- Parcours : id, projet, application, fonctionnalité (nœud du graphe `module:…` / `fonctionnalite:…`), libellé,
  clés Jira, version, responsable, dates, suspendu / abandonné, étapes, historique, versions (instantané à chaque
  validation, pour comparer).
- Étape : id, numéro, titre, rôle, écran de l'atelier, outils MCP utiles, validation humaine (oui / non),
  prérequis, statut, références (type, id, libellé), résultat, validation (qui, quand, commentaire), à revoir,
  historique.
- Statuts du parcours (calculés) : Draft, In Progress, Waiting for Validation, Blocked, Suspended, Completed,
  Abandoned. Statuts d'étape : À faire, En cours, En attente de validation, Validée, Échouée, Bloquée, Sautée.

## Règles (moteur `atelier/intelligence/parcours_fonctionnalite.py`)
- Un parcours ouvert par fonctionnalité (création idempotente) ; une référence n'est ajoutée qu'une fois.
- Une étape ne démarre, ne se soumet et ne se valide que si les étapes précédentes sont validées ou sautées.
- Sauter ou abandonner exige une justification (10 caractères) ; échouer / bloquer exige un motif.
- Revenir à une étape : elle repart « En cours », les suivantes déjà faites sont conservées et marquées « à revoir ».
- Validation humaine imposée côté serveur pour « Validation des scénarios », « Qualification des scripts » et
  « Synchronisation Xray » : depuis Cursor, « valider » les met en attente de validation ; dans l'atelier, le rôle
  relecteur est exigé (les autres étapes : rôle automaticien).
- Indices constatés dans les modules (lecture seule, jamais une validation automatique) : écrans du module dans la
  carte, état des US dans À concevoir, suites portant les clés Jira et leur statut de revue.

## Outils MCP ajoutés (81 au total, aucun existant modifié)
`parcours_lister`, `parcours_initialiser`, `parcours_etat`, `parcours_etape` (demarrer, referencer, soumettre,
valider, sauter, echouer, bloquer, revenir), `parcours_reprendre` (suspendre, reprendre, abandonner).

## API web
`GET/POST /api/parcours`, `GET /api/parcours/{id}`, `POST /api/parcours/{id}/etape`, `POST /api/parcours/{id}/etat`,
`GET /api/parcours/{id}/comparer?a=&b=`. Événement temps réel `parcours_change` : une action faite dans Cursor
s'affiche aussitôt dans l'écran.

## Écran
Onglet principal **Parcours** : liste des parcours (statut, étape courante, avancement), détail des 10 étapes
(statut, à revoir, dépendances bloquantes, références, constats, lien « Ouvrir » vers le module), panneau d'actions,
historique (origine Cursor ou utilisateur), comparaison avec une version précédente.

## Tests
`tests/test_parcours_fonctionnalite.py` : création idempotente, dépendances, saut justifié, reprise et « à revoir »,
comparaison de versions, validation humaine imposée (MCP et rôle), suspension / reprise / abandon, parcours complet
par les outils MCP, routes web.
