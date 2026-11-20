# Corrélation entre exigences Jira et écrans de l'application

Décision d'architecture du 2026-11-18 : **deux relations distinctes**, pour ne jamais confondre une preuve issue des
tests avec une association fonctionnelle validée.

## Prérequis

L'écran doit exister dans la carte de l'application, donc avoir été vu pendant une session Discovery (téléphone,
émulateur ou navigateur). Sans écran dans la carte, aucun lien n'est créé : ni automatique, ni proposé, ni manuel. Un
écran connu seulement par les locators du dépôt de tests ne suffit pas.

## Les deux relations

| | « Vérifiée sur » | « Réalisé par » |
|---|---|---|
| Sens | Exigence → Écran | Exigence → Écran |
| Type (ontologie) | `VERIFIED_ON` (extension) | `REALIZED_BY` |
| Relation historique | `verifiee_sur` | `impacte` (déclarée) |
| Ce qu'elle dit | Un test automatisé de l'exigence passe par l'écran | L'écran réalise l'exigence |
| Création | Automatique, à chaque construction du graphe | Décision humaine uniquement |
| Système d'origine | `AUTOMATED_TEST` | `CURSOR_VALIDATED` ou `USER_DECLARATION` |
| Statut | `OFFICIAL` (fait observé) | `VALIDATED` |
| Couverture fonctionnelle, périmètre d'une exigence | Non | Oui |
| Traçabilité et preuve de test | Oui | Oui (elle garde ses preuves de test) |

Un test de bout en bout traverse la connexion et l'accueil avant l'écran qu'il vérifie : la preuve de test est un fait,
pas une affirmation fonctionnelle. Elle se promeut en « réalisé par » d'un clic, par décision humaine.

## Trois chemins vers « réalisé par »

1. **Preuve de test promue** : l'exigence est déjà « vérifiée sur » l'écran ; l'automaticien confirme qu'il la réalise.
2. **Proposition d'une IA confirmée** : Cursor (via le MCP) ou le LLM interne juge chaque couple écran / exigence —
   `concerne`, `ne_concerne_pas` ou `incertain` — avec une justification, ses preuves et une estimation (faible, moyenne,
   forte). L'automaticien confirme, rejette ou laisse en attente. Sans IA configurée, aucune proposition n'est faite.
3. **Lien manuel** : depuis Discovery › Corrélation (« Relier manuellement ») ou depuis le graphe (« Relier » sur un écran
   ou sur une exigence).

Dans les trois cas, la même relation est écrite, avec l'origine, l'auteur (session du poste) et la date de la décision.

## Preuves de la relation automatique

Chaîne suivie : écran → locators → scripts Robot Framework → clé Xray en tag → test Xray → exigence Jira liée au test
dans Xray. S'y ajoutent les tests passés par l'écran pendant un run cartographié.

- Une seule relation par couple exigence / écran ; chaque test Xray y ajoute une preuve (scripts, locators, origine).
- Les preuves sont relevées à chaque affichage de la Corrélation. Une preuve qui disparaît (script modifié, tag retiré)
  est consignée dans l'historique ; la relation reste tant qu'il lui reste une preuve.

## Propositions : seule l'IA propose, dans un périmètre

Mesure du 2026-11-20 sur une simulation (8 écrans, 5 exigences) : 37 propositions, dont 31 dues à un seul mot présent
dans le nom de chaque écran et dans le titre de chaque exigence. Décision de l'utilisateur le même jour : la
corrélation est confiée uniquement à l'IA configurée (Cursor, Claude ou le LLM interne).

- **Seule l'IA propose** : une proposition est un jugement « concerne » ou « incertain » de l'IA, avec sa
  justification. Un jugement « ne concerne pas » est rangé à part (« Écartées par l'IA »), où l'automaticien peut
  encore confirmer ou rejeter. Sans IA configurée, l'écran le dit et ne propose rien ; le lien manuel reste possible.
- **Présélection, pas proposition** : les exigences d'un parcours qui traverse l'écran et la ressemblance des mots ne
  sont plus affichées comme des propositions. Elles forment les « candidats » transmis à l'IA, et l'écran indique
  combien attendent son jugement. L'IA peut toujours citer n'importe quelle exigence de la liste.
- **Mots communs ignorés** : un mot présent dans plus de la moitié des exigences de la copie locale (à partir de 4
  exigences) ne présélectionne rien.
- **Origine d'un lien** : « proposition d'une IA confirmée », « preuve de test promue » ou « lien manuel ». L'origine
  « ressemblance des mots » n'est plus attribuée ; les décisions passées qui la portent la gardent.
- **Périmètre** : le menu « Périmètre » (module de la carte ou parcours validé, le même que dans « Explorer le reste »,
  `atelier/discovery/reste.py`) borne la liste des écrans, les compteurs et la demande faite à Cursor. Le choix est
  partagé entre les deux écrans. Le bouton « Corrélation des écrans » d'un parcours validé ouvre la Corrélation sur ses
  écrans. Un périmètre inconnu est refusé ; l'écran revient alors à toute l'application et le signale.

Limite : au plus 12 candidats par écran sont transmis à l'IA, ceux des parcours d'abord.

## Ce qui n'entre dans aucun calcul

- Une proposition non confirmée : elle reste dans Discovery › Corrélation, jamais dans le graphe.
- Une proposition rejetée : gardée dans l'historique, plus jamais proposée ; une IA ne peut pas la redéposer.
- L'estimation donnée par une IA : indicative, affichée comme telle, jamais utilisée dans un calcul.

## Où c'est

| Élément | Emplacement |
|---|---|
| Moteur | `atelier/discovery/correlation.py` |
| Relation automatique | `_verifiees_sur` dans `atelier/discovery/connaissance.py` |
| Ontologie | `VERIFIED_ON`, `AUTOMATED_TEST`, `CURSOR_VALIDATED` dans `atelier/domain/ontologie.py` |
| Lien manuel depuis le graphe | `ajouter_relation` dans `atelier/discovery/espaces.py` |
| Écran renommé ou fusionné | `renommer_ecran` dans `atelier/domain/declarations.py` |
| Interface | Discovery › Corrélation (`ecran_discovery.js`), panneau de relation du graphe |
| Outils MCP (signatures inchangées) | `discovery_correlations_a_juger`, `discovery_juger_correlations` |
| Tests | `tests/test_correlation.py` |

Données par application, dans le dossier de la carte : `correlations_jugees.json` (jugements des IA),
`correlations_decisions.json` (décisions humaines), `correlations_preuves.json` (dernier relevé des preuves),
`correlations_historique.json` (journal).

## Limites connues

- **Stockage** : les relations automatiques sont recalculées à chaque construction du graphe ; seul le journal garde la
  trace d'une preuve perdue. Le stockage durable des relations est la phase 5 de la refonte du graphe.
- **Identifiant d'écran** : dans le graphe, un écran porte son nom (`ecran:<nom>`). Un renommage ou une fusion reporte
  les liens déclarés ; l'identifiant stable reste celui de la carte.
- **Captures d'écran** : l'atelier n'en conserve pas et n'en transmet aucune à une IA. L'écran est décrit par ses
  composants, ses locators et ses écrans voisins.
- **Rôles et droits** : l'auteur d'une décision est la session du poste, comme dans Automation Studio ; les rôles
  d'Automation Studio (`atelier_roles.yaml`) ne sont pas encore appliqués aux décisions de corrélation.
- **Exécution** : la preuve référence le test Xray, les scripts et les locators, pas un numéro d'exécution précis.
