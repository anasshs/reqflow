# Discovery Data Setup — référentiel universel de données

État au 2026-11-18. Moteur : `atelier/discovery/donnees.py`. Écran : Discovery › Données. Tests : `tests/test_donnees_discovery.py`.

## Principe
Le référentiel ne connaît aucun métier. Il n'y a pas de « compte », de « bénéficiaire » ni de « dossier » dans le code :
l'automaticien déclare les variables dont l'exploration a besoin, les regroupe, et Cursor y puise pendant le Discovery.

## Ce qui est séparé
| Quoi | Où | Contenu |
|---|---|---|
| Définition | `data/discovery/variables.yaml` | nom, clé, description, type, sensibilité, règles, source, alias, environnements, statut |
| Valeur | `data/discovery/valeurs.yaml` | par défaut, par environnement, par profil (jamais une valeur secrète) |
| Groupes et profils | `data/discovery/profils.yaml` | listes libres de variables (nature : groupe ou profil utilisateur) |
| Réglages | `data/discovery/reglages.yaml` | que faire d'un champ sans variable (signaler, ou générer pour certains types) |
| Contexte | `discovery/donnees/contextes/<session>.json` | valeurs utilisées par une session, origine, dépendances |
| Cycle de vie | `discovery/donnees/historique.jsonl` | demandes, saisies, données manquantes (aucune valeur) |

Ordre de résolution d'une valeur : déjà utilisée dans la session → valeur du profil → valeur de l'environnement → coffre
(variable secrète) → valeur par défaut → source de la variable.

## Types, sources, sensibilité
- Types : texte, nombre, entier, booleen, date, email, telephone, url, fichier, json, liste. Le type est toujours contrôlé ;
  les règles ajoutent format (expression régulière), longueur, bornes, valeurs autorisées.
- Sources : manuelle, environnement, coffre, generateur, calcul, api, requete, fichier (CSV / JSON du projet), session
  (valeur relevée pendant le parcours).
- Générateurs : date, nombre, email, prenom, nom, identifiant, alphanumerique, telephone, motif, choix. Une valeur générée
  respecte les règles de la variable et ne change plus pendant la session.
- Calculs : `texte` (assemblage), `nombre` (arithmétique seule : + - * / parenthèses, aucun appel), `date` (base + durée en
  jours, mois ou années). Les dépendances sont lues dans les `{{CLE}}` ; un cycle est refusé à l'enregistrement.
- Sensibilité : normale ; confidentielle (masquée à l'écran, dans l'historique et pour l'agent) ; secrète (en plus : jamais
  dans un fichier, coffre du poste ou variable d'environnement).

## Cursor (5 outils MCP)
| Outil | Rôle |
|---|---|
| `discovery_donnees_catalogue` | lire variables, profils, générateurs, réglages |
| `discovery_donnees_pour_champs` | besoins d'un écran : nature de chaque champ, variable retenue, valeur cohérente |
| `discovery_donnee` | valeur d'une variable pour la session |
| `discovery_donnee_definir` | garder une valeur relevée dans l'application |
| `discovery_donnees_contexte` | lire le contexte ; choisir le profil ou l'environnement |

Saisie : `type_text(locator, "{{var:CLE}}")`. La référence est résolue côté serveur ; la valeur réelle ne revient ni à
l'agent, ni dans les événements de l'atelier. L'agent ne modifie jamais le catalogue.

Champ sans variable : par défaut « manquante » (rien n'est inventé, la demande est tracée). Un générateur peut être
autorisé par type de champ ; jamais pour un mot de passe ou un code.

## Où les variables apparaissent ailleurs
- **Journal de la session Discovery** : une ligne « donnee » à chaque donnée obtenue, générée, calculée, relevée, saisie,
  manquante ou saisie hors référentiel (variable, champ, écran, origine ; jamais la valeur).
- **Knowledge Graph** : un nœud `variable:CLE` par définition (type cible `DataVariable`, sans valeur), ses dépendances
  (`depend_de`), et un lien observé `utilise` depuis l'écran et, quand il est identifié, depuis le champ où elle a servi.
  Un parcours `utilise` (lien déduit) les variables de ses écrans. L'analyse d'impact fonctionne sur une variable.
  Angles « Technique » et « Parcours utilisateur » du graphe.
- **Du parcours au scénario BDD** : l'étape de saisie cite la variable utilisée pour ce champ (« je renseigne montant
  avec la donnée Montant du virement ») et la garde (`variable`) ; le scénario issu d'une session garde son profil
  (`profil_donnees`). Le script Robot généré n'en tient pas compte : les tests lisent toujours `data/jdd`.
- Rattachement d'une utilisation à la carte (`donnees.liens_carte`) : une saisie par le locator du champ ; une demande
  par l'écran nommé par l'agent et le libellé du champ. Un locator présent sur plusieurs écrans n'est rattaché que si
  l'agent a nommé l'écran pour cette variable : aucun lien n'est deviné.

## Limites connues
- La nature d'un champ et le rapprochement champ ↔ variable reposent sur les mots du libellé et le type technique : un
  libellé inhabituel demande un alias sur la variable. Pas de jugement délégué à l'IA sur ce point.
- Une valeur sensible générée ou relevée pendant une session vit en mémoire : elle est perdue si l'atelier redémarre.
  De même une valeur secrète réglée sans coffre système disponible.
- Une saisie littérale faite par l'agent n'est pas bloquée : elle est tracée « hors référentiel » dans l'historique.
- Les valeurs confidentielles restent dans `valeurs.yaml` (donc dans le dépôt du projet de tests) : préférer « secrète »
  pour ce qui ne doit pas y figurer.
- Le profil d'une session se choisit dans Données › Préparation (ou `discovery_demarrer(profil_donnees=…)`), pas encore
  dans la fenêtre de création de session.
- API et requêtes : celles de `data/jdd` ; leur déclaration ne se fait pas depuis cet écran.
- Une demande faite sans nom d'écran (`discovery_donnee`, ou `discovery_donnees_pour_champs` sans `ecran`) n'est pas
  rattachée à la carte tant que la valeur n'est pas saisie par référence ; un nom d'écran inconnu de la carte non plus.
- Non essayé sur une vraie application ni avec un vrai Cursor : vérifié par les tests et sur le projet fictif.
