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

## Où c'est

| Élément | Emplacement |
|---|---|
| Moteur | `atelier/intelligence/releases.py` |
| Alimentation du TNR | `releases.evolutions_tnr`, lu par `pilotage.evolutions` |
| Routes | `GET/POST /api/releases`, `GET /api/releases/{id}`, `POST /api/releases/{id}/operation`, `GET /api/releases/noeuds` |
| Écran | `releases()` dans `atelier/adapters/web/static/ecran_pilotage.js` |
| Données | `<projet>/releases/REL-AAAAMMJJ-xxxxxx.json` (dans le projet de tests, jamais dans le dépôt de l'atelier) |
| Tests | `tests/test_releases.py` |

## Ce qui n'est pas fait (suite du cahier)

- **Compréhension par une IA** : la lecture est faite par des règles. Elle découpe bien une note en liste, mal un texte
  rédigé en paragraphes ; elle ne comprend pas qu'« optimisation du paiement » concerne le virement. Étape suivante :
  déléguer l'extraction et le rapprochement à l'IA configurée (Cursor, Claude, LLM interne), avec validation humaine.
- **Teams** : ni lecture du canal, ni notifications. Les notifications de changement de Microsoft Graph demandent une
  adresse publique, incompatible avec l'écoute sur 127.0.0.1 : la lecture se fera par interrogation périodique, une
  fois l'accès accordé par l'administrateur Microsoft 365.
- **Import de fichiers** (PDF, Word, Excel), **sources Jira** (release, sprint) comme point de départ.
- **Score de risque**, catégorie « tests à créer » transmise à Test Design, Test Plan Xray depuis la release,
  indicateurs dédiés.
