# Projet de démonstration — module Connexion (application fictive « Banque Démo »)

Projet Robot Framework complet sur une application web **fictive** (`app/`), pour voir l'atelier
fonctionner de bout en bout avec de **vraies** exécutions (aucun chiffre simulé dans le dashboard).

| Élément | Où |
|---|---|
| Application fictive (connexion, accueil) | `app/connexion.html`, `app/accueil.html` |
| Tests Robot (7 cas, Gherkin + JDD) | `tests/connexion.robot` |
| Socle (keywords) / locators | `resources/socle/connexion.resource`, `resources/locators/connexion.resource` |
| Bibliothèque de démonstration (Playwright) | `resources/bibliotheques/NavigateurDemo.py` |
| Jeux de données (recette) | `data/jdd/recette.yaml` |
| Patrimoine Xray fictif (exigences, 9 tests, plan) | `patrimoine/xray.json` |
| Scénario BDD (brouillon, avec branche négative) | `bdd/DEMO-301.feature` |
| Carte de l'application (observée en session web réelle) | `app_map/banque_demo_web/` |
| Stratégie de test d'exemple | `strategie/strategie.yaml` |

## Comptes fictifs

| Identifiant | Mot de passe | Comportement |
|---|---|---|
| `client.demo` | `Demo#2026` | connexion réussie, accueil « Bienvenue, Client Démo » |
| `client.bloque` | `Bloque#2026` | refus : compte bloqué |
| autre / champs vides | — | message d'erreur |

**Anomalie volontaire** : l'exigence DEMO-311 demande le blocage au 3e échec ; l'application ne
bloque qu'au 4e. Le test DEMO-304 échoue donc réellement (capture d'écran, attendu / trouvé) :
c'est ce qui alimente l'analyse d'échec et le dashboard. DEMO-308 et DEMO-309 sont des tests
manuels non automatisés et DEMO-312 n'a aucun test automatisé : trous de couverture visibles.

## Lancer

```
ROBOT_PROJECT_DIR=$PWD/demo/banque_connexion WEB_BROWSER_EXECUTABLE=/chemin/chromium python web/app.py
```

Puis http://127.0.0.1:8765/plateforme : choisir Plateforme **Web** et Environnement **recette**,
Exécution › Lancer › `tests` (sans sélection de jeux : ceux référencés par la suite sont injectés).
Les résultats vont dans `results/runs/<id>/` (non versionné).
