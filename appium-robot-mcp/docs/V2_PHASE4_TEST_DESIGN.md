# V2 — Phase 4 : Test Design avancé (catégories et doublons)

## Existant réutilisé
Test Design › À concevoir (US, critères, cas squelettes par critère, validation, publication Xray), règles de test,
Knowledge Graph (règles, écrans, champs, messages, transitions, rôles), moteur de similarité de Coverage Intelligence.

## Cas par catégorie (`atelier/intelligence/conception_avancee.py`)
| Catégorie | Source | Provenance |
|---|---|---|
| nominal / alternatif / négatif | chaque critère d'acceptation (condition → action → résultat) ; négatif si négation, alternatif si condition | observé |
| négatif, nominal par défaut | à défaut de critère exploitable | déduit, confiance faible |
| limites | valeurs chiffrées des critères et des règles (€, caractères, jours, échecs, %…) : en dessous, à la borne, au-dessus | observé |
| validation des champs | champs des écrans de la fonctionnalité (carte) : vide, format invalide | déduit |
| gestion des erreurs | zones de message d'erreur observées | déduit |
| navigation | transitions de la carte entre écrans de la fonctionnalité | observé |
| permissions | rôles du graphe (un cas par rôle), ou mention de droits dans l'US | observé / déduit |
| règles métier | règles liées à l'US | observé |

Chaque cas : catégorie, source, justification, confiance, informations manquantes, provenance, statut « Proposé ».
Une proposition identique (même catégorie et titre) n'est jamais ajoutée deux fois.

## Doublons
Comparaison avec les tests Xray de l'instantané et les autres cas de l'US sur quatre facettes (titre sans
étiquette de catégorie, étapes, préconditions, résultats attendus ; Gherkin découpé Given / When / Then) et sur le
texte complet (moyenne recouvrement / Jaccard des mots significatifs). Score = le plus fort ; recommandation :
**réutiliser** ≥ 0,70, **faire évoluer** ≥ 0,40, sinon **créer**. Rien n'est supprimé : l'automaticien décide.

## Où
- Test Design › À concevoir › panneau d'une US : « Proposer par catégories » (choix des catégories) et « Vérifier les
  doublons » ; chaque cas affiche catégorie, observé / déduit, confiance, source, justification, manques, test le
  plus proche et facettes comparées.
- MCP : `test_design_proposer(cle, categories)`, `test_design_doublons(titre, etapes, gherkin)` (85 outils, aucun
  existant modifié) ; règle Cursor `test-design` mise à jour.

## Tests
`tests/test_conception_avancee.py` : contexte depuis le graphe, toutes les catégories avec source / confiance /
manques, limites lues dans critères et règles, idempotence, doublon « réutiliser » vs « créer », vérification,
outils MCP.
