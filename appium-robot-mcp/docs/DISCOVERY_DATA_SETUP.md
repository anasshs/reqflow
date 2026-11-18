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
- Non essayé sur une vraie application ni avec un vrai Cursor : vérifié par les tests et sur le projet fictif.
