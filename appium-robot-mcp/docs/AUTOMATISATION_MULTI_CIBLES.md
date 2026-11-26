# Automatiser la batterie de tests sur plusieurs cibles (proposition de conception)

Statut : **validée le 2026-11-25** (docs/DECISIONS.md) ; phases B, C, D, E et F livrées ; phase A (exécution sur
appareil) en attente de l'installation sur le téléphone ou d'une image d'émulateur. Suivi : docs/ROADMAP.md.
Vocabulaire : « cible » dans l'interface = **technologie** dans le code (`atelier/generation/technologies/`), pour ne pas
confondre avec le paramètre `cible` (chemin de la suite) de `bdd.generer_robot`.
Date : 2026-11-25. Point de départ : la TNR SIMPLE 4.4 (608) déroulée et rangée dans Xray
(`/Simple/TNR_SIMPLE_4.4`, plan TAM-5068, exécution TAM-5069), et le projet UI Automator déjà commencé
dans le dépôt de tests (`Simple-mobile-tests/uiautomator`).

## 1. Objectif

Donner, depuis l'atelier, un geste unique : **« Automatiser ce test (ou ce lot, ce parcours, toute la TNR) avec … »**
et choisir la cible :

| Cible | Pour | Technologie | Pilote |
|---|---|---|---|
| `robot-appium` | Android et iOS, application installée (boîte noire) | Robot Framework + AppiumLibrary | serveur Appium (existant) |
| `robot-web` | Web | Robot Framework + Browser (Playwright) ou SeleniumLibrary | navigateur |
| `uiautomator` | Android, application installée (boîte noire), exécution rapide dans le téléphone | Kotlin, `androidx.test.uiautomator`, JUnit4 | instrumentation Android |
| `espresso` | Android, **avec le code source de l'application** (boîte blanche) | Kotlin, Espresso / Compose Test | instrumentation Android, dans le dépôt de l'app |

Le résultat de chaque exécution remonte dans Xray de la même façon, quelle que soit la cible (statut, commentaire,
preuves, rattachement au plan et à l'exécution).

## 2. Ce qui existe déjà et qu'on garde

**Dans l'atelier** (rapport d'analyse du 2026-11-25) :

- **Entrée neutre déjà présente** : le scénario BDD (`atelier/generation/bdd.py`, `bdd/<clé>.feature` + `.yaml`), ses étapes
  typées (`given/when/then`, écran, locator, jeu de données, assertion), le jeu de données (`jdd`), le parcours, et la clé Xray.
- **Carte de l'application** : écrans, éléments par clé métier, locators par plateforme ; reliée au dépôt Robot et aux tests
  depuis le correctif du 2026-11-25 (55 écrans sur 88 reliés, 20 parcours sur 35).
- **Remontée Xray générique** : le journal « outbox » (`atelier/execution/journal_xray.py`) reçoit des événements
  `preparation`, `test_debut`, `test_fin`, `transition`, puis un synchroniseur les rejoue vers Xray. Il ne dépend pas de Robot.
- **Orchestration** : Kanban, flux simple / complet (`generation/flux.py`), file d'exécution (`execution/centre.py`), revue,
  versionnement, publication au TNR (`generation/tnr.py`).

**Ce qui est propre à Robot aujourd'hui** (à mettre derrière une cible) :

| Rôle | Endroit |
|---|---|
| Génération d'un test | `bdd.generer_robot` (unique générateur) |
| Corps d'une étape | `pom.corps_etape` (AppiumLibrary / Browser codés en dur) |
| Inventaire du socle | `depot_robot.lire_depot`, `reutilisation` (.robot / .resource) |
| Lancement | `robot.run_robot` |
| Lecture des résultats | `parse_robot_output`, `derniers_resultats` (output.xml) |
| Cartographie pendant le run | listener AppiumLibrary |

**Dans le dépôt de tests** : `Simple-mobile-tests/uiautomator` (Kotlin, UI Automator 2) :

- `outils/robot2kotlin.py` traduit **ligne à ligne** les 185 tests Robot (1 025 mots-clés, 93 % des instructions) ;
  un élément non traduit fait échouer le test en le nommant (`NonTraduit`), jamais de faux succès ; reste listé dans `A_TRADUIRE.md`.
- `outils/gen_ecrans.py` : 42 Page Objects par écran ; `socle/` (écrit à la main) : `Simple`, `Cible`, `Locators`, `R`.
- **Jamais compilé ni exécuté** (Gradle et paquets SDK absents du poste).

## 3. Point important sur Espresso

Espresso s'exécute **dans le processus de l'application** : il faut compiler les tests avec le code source de l'app
(module `androidTest` du dépôt de l'équipe de développement). Sur un APK livré par App Distribution, sans le code,
Espresso ne peut pas piloter l'app. C'est pour cela que le travail commencé utilise **UI Automator**, l'outil de Google
pour l'app installée.

Proposition : deux cibles Android natives qui partagent le même modèle et le même socle Kotlin.

- `uiautomator` tout de suite, sur l'APK de recette, sans dépendre de l'équipe de développement.
- `espresso` quand l'accès au dépôt de l'application est obtenu. Les tests sont alors générés dans son `androidTest`
  (`onView(withId(R.id.btnContinue))`, `onNodeWithTag` pour Compose), plus rapides et plus stables, et exécutables en CI
  par l'équipe de développement.

## 4. Conception : le modèle neutre et les cibles

```
                 Xray (scénarios Cucumber, plan TNR)          carte de l'application (écrans, éléments)
                                  │                                          │
                                  ▼                                          ▼
   scénario BDD ──► plan d'automatisation (modèle neutre) ◄── éléments + locators par plateforme + JDD
                                  │
            ┌──────────────┬──────┴───────┬───────────────┐
            ▼              ▼              ▼               ▼
      robot-appium     robot-web      uiautomator       espresso        (une « cible » = un module)
      .robot/.resource .robot         .kt (JUnit)       .kt (androidTest de l'app)
            │              │              │               │
            ▼              ▼              ▼               ▼
         Robot          Robot         Gradle + am instrument (JUnit XML / sortie instrumentation)
            └──────────────┴──────┬───────┴───────────────┘
                                  ▼
                  journal Xray (outbox) ─► Xray : statut, commentaire, preuves
                  historique, Kanban, couverture, knowledge graph
```

### 4.1 Le plan d'automatisation (nouveau, neutre)

Calculé une fois depuis le scénario BDD, indépendant de la technologie. Chaque étape devient une **intention** :

| Intention | Exemple d'étape | Données |
|---|---|---|
| `ouvrir` | Je suis connecté sur le tableau de bord | écran cible, prérequis (compte du JDD) |
| `toucher` | Je clique sur « Virement » | élément (clé métier de la carte) |
| `saisir` | Je renseigne le montant | élément, valeur = champ du JDD (`${JDD.montant}`), secret ou non |
| `choisir` | Je choisis le type d'ordre « Permanent » | élément de liste, valeur |
| `verifier` | Le récapitulatif affiche le montant | élément, assertion (`egal`, `contient`, `visible`, `absent`, `montant`) |
| `otp` | Je valide le code reçu par SMS | mode OTP (`arret` / `validation`), source (adb / API) |
| `attendre` / `revenir` / `defiler` | — | — |
| `appel` | réutiliser un keyword ou une fonction du socle existant | nom, arguments |

Ce modèle réutilise le classement existant (`pom.ACTION / SAISIE / RETOUR / SECRET`) et le rapprochement avec le socle
(`reutilisation.Rapprocheur`), sans le lier à Robot. Il rejoint la phase 2 de la roadmap (modèle d'assertion
`type / cible / attendu / source`).

### 4.2 L'interface d'une cible

Un module par technologie, sous `atelier/generation/technologies/` (livré en phase B : `Technologie`, registre, robot-*) :

```python
class Technologie:
    nom: str                      # "robot-appium", "robot-web", "uiautomator", "espresso"
    plateformes: list[str]        # ["android", "ios"] / ["web"] / ["android"]
    def prerequis(self) -> dict                       # outils du poste (Appium, Gradle, SDK, JDK, navigateur)
    def socle(self) -> dict                           # inventaire de ce qui existe déjà (keywords / fonctions / Page Objects)
    def generer(self, plan, app) -> list[Fichier]     # suite + pages + locators, dans la convention du dépôt
    def controler(self, fichiers) -> list[Probleme]   # robocop / compilation Kotlin (gradle compileDebugAndroidTestKotlin)
    def executer(self, selection, options) -> Run     # robot / gradle + am instrument
    def resultats(self, run) -> list[ResultatTest]    # output.xml / JUnit XML -> {cle_xray, statut, debut, fin, message, preuves}
```

- `robot-appium` et `robot-web` : extraction **sans changement de comportement** de `bdd.generer_robot`,
  `pom.corps_etape`, `robot.run_robot` (les tests actuels restent verts).
- `uiautomator` : reprend `socle/` et `gen_ecrans.py` du dépôt de tests. La génération **depuis le plan** produit des tests
  Kotlin lisibles (Page Object par écran de la carte, une méthode par intention). La traduction **ligne à ligne** de
  `robot2kotlin.py` reste disponible pour porter d'un coup le patrimoine Robot existant (voir § 5).
- `espresso` : même plan, même Page Objects ; seul le rendu des sélecteurs change (`withId(R.id.x)` depuis le resource-id
  de la carte, `withContentDescription`, `withText`, `onNodeWithTag` pour Compose).

### 4.3 Résultats et Xray (commun)

- Chaque test Kotlin porte sa clé : `@Xray("TAM-3243")` (annotation du socle) ; chaque test Robot garde son tag.
- `resultats()` convertit la sortie de la cible en événements de l'**outbox** existante (`test_debut`, `test_fin`) :
  Xray, l'historique, le Kanban, la couverture et la qualification des échecs fonctionnent sans changement.
- Exécution Kotlin : `gradlew connectedDebugAndroidTest` ou `adb shell am instrument -r` (sortie brute convertie),
  captures d'écran du socle en preuves, journal `logcat` filtré joint en cas d'échec.
- Comptes et OTP : jamais écrits dans le code. Ils sont passés en arguments d'instrumentation (`-e COMPTE.identifiant …`)
  depuis le coffre ou les variables du poste, comme le fait déjà `Simple-mobile-tests/uiautomator`.

### 4.4 Carte enrichie (pour les cibles natives)

La carte ne garde aujourd'hui que `type`, `libelle` et `locators` (chaînes au format Appium). Pour UI Automator et
Espresso, garder aussi les **attributs bruts** de chaque élément : `resource_id`, `content_desc`, `texte`, `classe`,
`compose` (oui / non), activité. Ces données sont déjà lues au parsing (`discovery/parsing.py`) et perdues à
l'enregistrement. À faire avec la phase 4 de la roadmap (carte robuste).

### 4.5 Dans l'atelier

- **Kanban / lots / tests automatisés** : un sélecteur « Automatiser avec » (cible) sur un test, une sélection, un parcours ou
  le plan TNR entier ; cible par défaut réglée par application (`app.yaml`, clé `automatisation.cible_defaut`).
- **Un test Xray peut avoir plusieurs implémentations** (une par cible), chacune avec son statut « vérifié » et son dernier run.
  Le graphe relie `test_xray ─implémenté par→ test_robot | test_kotlin`.
- **MCP** : outils existants inchangés (rétrocompatibilité) ; un argument `cible` (défaut `robot-appium`) sur
  `studio_generer_depuis_bdd`, `run_tests` ; nouveaux outils `cibles_disponibles`, `porter_vers_cible`
  (traduction d'une suite existante), classés dans `tests/test_securite_outils.py`.
- **Règles de génération** (CLAUDE.md, section « tests Robot GÉNÉRÉS ») : à étendre en « tests GÉNÉRÉS » avec les conventions
  Kotlin (une classe par parcours, Page Object par écran, aucune donnée littérale, clé Xray en annotation).

## 4.6 Points d'entrée et relais par le MCP

L'automaticien ne choisit pas des fichiers : il désigne **un parcours**, **une User Story** ou **un Test Plan Xray**.
L'atelier le résout en une liste de tests Xray, chacun avec son scénario BDD (ou « à concevoir »), ses implémentations
par technologie et son dernier statut :

| Entrée | Résolution |
|---|---|
| Parcours (`PU-…`) | scénarios BDD rattachés au parcours (`bdd.parcours`) -> clés Xray ; écrans du parcours connus (carte) |
| User Story (clé Jira) | tests Xray liés à l'US (couverture, Test Design) ; s'il en manque : `test_design_proposer` d'abord |
| Test Plan Xray | tests du plan et leur dernier statut ; tests manuels sans Gherkin signalés à compléter |

« Automatiser et vérifier » crée **une demande** dans la boîte de l'atelier (entrée, technologie, tests). Le MCP (Claude
Code ou Cursor) la prend (`atelier_demande_suivante`) et déroule pour chaque test : préparer (BDD, `check_jdd`,
`studio_socle`, `studio_plan_automatisation`) → générer (`studio_generer_depuis_bdd`, `technologie=`) → contrôler
(compilation / dry-run) → vérifier (`run_tests` sur le device, OTP selon l'environnement) → corriger ou qualifier
l'échec → publier dans Xray et commiter ; compte rendu par `atelier_demande_terminee`. L'automaticien intervient pour la
revue, une donnée manquante, ou un défaut applicatif à confirmer. Outil à ajouter : `automatiser_perimetre(entree,
reference, technologie)`.

## 5. Deux chemins pour la batterie existante

| | Porter (traduction) | Générer depuis le BDD |
|---|---|---|
| Entrée | code Robot du dépôt | scénario BDD + carte + JDD |
| Outil | `robot2kotlin.py` intégré comme `porter_vers_cible` | `Cible.generer(plan)` |
| Couverture immédiate | 185 tests, 93 % des instructions | les 148 tests Xray de la TNR, au fil des scénarios validés |
| Lisibilité | code fidèle au Robot, verbeux | Page Objects propres, maintenables |
| Usage | migration rapide, comparaison de vitesse Robot / Kotlin | cible de long terme, nouveaux tests |

Proposition : **porter** d'abord pour obtenir vite une batterie Kotlin exécutable et mesurer le gain, puis **régénérer depuis le
BDD** parcours par parcours, en remplaçant le code porté (le Kanban suit l'avancement par parcours).

## 6. Phases proposées (une à la fois)

| Phase | Contenu | Fini quand |
|---|---|---|
| A. Faire tourner l'existant | Installer Gradle 8.7, `platforms;android-34`, `build-tools;34.0.0` ; compiler `Simple-mobile-tests/uiautomator` ; corriger la compilation du code généré ; lancer la suite `login` ; comparer temps et stabilité avec Robot | 1 suite verte en Kotlin, mesure Robot vs Kotlin |
| B. Abstraction « cible » | `atelier/generation/cibles/` + plan neutre ; `robot-appium` / `robot-web` extraits sans changement de comportement | `pytest -q` vert, génération Robot identique octet pour octet |
| C. Cible `uiautomator` | socle Kotlin repris, génération depuis le plan, runner Gradle, résultats → outbox Xray, carte enrichie | un scénario BDD → test Kotlin → statut dans Xray |
| D. Porter le patrimoine | `porter_vers_cible` (robot2kotlin dans l'atelier), `A_TRADUIRE` visible par test, Kanban « porté / régénéré » | la TNR SIMPLE exécutable en Kotlin, avec la liste de ce qui reste |
| E. Cible `robot-web` complète | Browser ou SeleniumLibrary au choix par application | un parcours web de bout en bout |
| F. Cible `espresso` | si accès au dépôt de l'app : génération dans son `androidTest`, exécution en CI de l'équipe de développement | un parcours Espresso en CI |

## 7. Décisions à prendre

1. Espresso : obtient-on l'accès au code source de l'app SIMPLE (dépôt et build de l'équipe de développement) ?
   Sinon, la cible Android native reste `uiautomator`.
2. Cible par défaut de la TNR SIMPLE : `robot-appium` (existant, Android + iOS) ou `uiautomator` (Android, plus rapide) ?
3. Batterie existante : porter d'abord (rapide), ou régénérer directement depuis le BDD (propre, plus lent) ?
4. Web : Browser (Playwright, déjà en place) ou SeleniumLibrary (demande d'équipe) ?

## 8. Prérequis et risques

- **Poste** : le disque C: était plein le 2026-11-25. Gradle, le SDK et les builds Android demandent plusieurs Go.
- **Promon** (protection des builds) peut bloquer l'instrumentation sur certaines versions : à vérifier à la phase A.
- **Un seul pilote à la fois sur un téléphone** : un run UI Automator et un run Appium ne cohabitent pas (UiAutomation partagé).
- **OTP** : lecture par adb (`content://sms`) depuis l'atelier, ou API de recette. Jamais de code dans les logs.
