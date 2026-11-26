# V2 — Phase 2 : intégration Cursor

## Existant réutilisé
Installation du MCP dans Cursor / Claude Desktop (fusion, sauvegarde `.bak`, ni secret ni chemin de projet) et copie
des règles sans écrasement implicite (`atelier/integrations/agents_ia.py`, Paramètres › Cursor / Claude).

## Règles structurées (`regles_cursor/`, installées sous `.cursor/rules/atelier-<id>.mdc`)
| Règle | Portée (frontmatter Cursor) | Rôle |
|---|---|---|
| global | toujours | principes : cerveau d'abord, réutiliser, ne rien inventer, propositions, parcours |
| project-context | toujours | contexte du projet généré depuis l'atelier (projet, application, modules, environnements, rangement) |
| security | toujours | secrets, actions sensibles, demandes à valider, Git, fichiers, base de données |
| mcp-usage | toujours | outils par domaine, bonnes pratiques (aperçu avant écriture, refus = résultat normal) |
| discovery | à la demande | exploration (ex-`cursor_rules_discovery.mdc`) |
| test-design | à la demande | conception, catégories de cas, doublons, sources et confiance |
| automation | fichiers `*.robot`, `*.resource` | conventions Robot (ex-`cursor_rules_automatisation.mdc`) |
| execution | à la demande | préparation et lancement des runs |
| failure-analysis | à la demande | diagnostic et classification des échecs |
| coverage | à la demande | indicateurs et niveaux de couverture |
| knowledge-graph | à la demande | consultation, provenance, enrichissement par propositions |

Les sections communes (sécurité, parcours) ne sont plus recopiées dans chaque règle.

## Versionnement (`atelier/integrations/regles_cursor.py`, `<projet>/atelier_regles/`)
- v1 = base de l'atelier + contexte du projet, créée au premier usage.
- Modifier une règle (frontmatter obligatoire, commentaire obligatoire) crée une nouvelle version, activée.
- Régénérer le contexte projet crée une version si le contexte a changé.
- Comparer deux versions (diff unifié par fichier) ; activer (restaurer) une version précédente ; journal.
- Le dossier `atelier_regles/` peut être versionné avec le projet (aucun chemin local, aucun secret).

## Synchronisation vers `.cursor/rules/` — jamais d'écrasement silencieux
Aperçu par fichier : nouveau, identique, à mettre à jour (ancienne version de l'atelier, y compris les règles
livrées avant la V2 : empreintes dans `regles_cursor/anciennes_versions.json`), modifié localement (diff affiché).
Un fichier modifié localement n'est remplacé que s'il est coché, avec sauvegarde `.bak`.

## Export et configuration MCP
- Export zip : `.cursor/rules/*.mdc` de la version active + `mcp.json.exemple` (aucun secret) + mode d'emploi.
- « Tester le serveur MCP » : lance réellement le serveur comme Cursor (même commande, stdio), l'initialise et liste
  ses outils (nom du serveur, nombre d'outils, durée) ; en cas d'échec, l'erreur du serveur est affichée.

## MCP
Outil ajouté : `cursor_regles(regle="")` (instructions actives du projet). 82 outils, aucun existant modifié.

## Tests
`tests/test_regles_cursor.py` (11 règles et portées, versions / comparaison / restauration, synchronisation sans
écrasement et `.bak`, contexte régénéré, export sans secret, outil MCP, migration des anciennes règles, **vrai client
MCP stdio** : 82 outils) ; `tests/test_agents_ia.py` mis à jour.
