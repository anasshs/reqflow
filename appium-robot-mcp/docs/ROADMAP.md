# Roadmap — Atelier d'automatisation → AI Test Engineering Platform

Principe : la qualité avant le volume. Chaque phase est livrable seule, testée, et ne casse pas
les outils MCP existants. Cocher les cases au fil de l'eau ; noter les décisions dans
`docs/DECISIONS.md` (une ligne datée par décision).

---

## Phase 1 — Fondations (aucune nouvelle fonctionnalité visible)

### 1.1 Découpage en moteurs
- [ ] Créer le paquet `atelier/` selon l'architecture de CLAUDE.md.
- [ ] Déplacer la logique de `server.py` vers les moteurs : sessions et observation → `discovery`,
      génération de .resource → `generation`, runs / listeners / qualification → `execution`,
      clients Xray / Jira / Oracle / Appium / Playwright → `integrations`.
- [ ] `app_map.py` → `atelier/discovery/carte/` ; `web_backend.py` → `atelier/integrations/playwright/`.
- [ ] `adapters/mcp/server.py` : enregistre les mêmes outils, chacun en quelques lignes.
- [ ] `adapters/web/app.py` : mêmes routes, appelant les moteurs (plus d'import de `server.py`).
- [ ] Gardes de compatibilité : `server.py` et `web/app.py` à la racine deviennent de simples
      points d'entrée qui importent les adapters (les configs Cursor existantes continuent de marcher).
- [ ] Événements : un bus interne (`atelier/domain/evenements.py`) remplace `EVENT_HOOK` et
      `WEB_EVENTS_URL` ; les adapters s'y abonnent.

**Acceptation** : la liste des outils MCP (noms + paramètres) est identique avant / après
(test automatique qui compare les deux) ; toutes les routes web répondent ; `pytest -q` vert.

### 1.2 Sécurité de l'interface locale
- [ ] Jeton de session généré au démarrage, transmis à la page (cookie HttpOnly SameSite=Strict) ;
      exigé sur toutes les routes `/api/*` et le WebSocket, sauf `/api/events` (jeton propre aux listeners).
- [ ] Vérification `Host` ∈ {127.0.0.1:PORT, localhost:PORT} (protection DNS rebinding) et
      `Origin` identique pour les requêtes navigateur et le WebSocket. Pas de CORS.
- [ ] Taille maximale des requêtes, chemins limités au projet (déjà `_safe_path`), liste blanche
      des actions manuelles (déjà en place, à tester).
**Acceptation** : tests qui prouvent le refus sans jeton, avec un mauvais `Host`, avec une `Origin`
étrangère, et l'acceptation dans le cas nominal.

### 1.3 Synchronisation Xray découplée de l'exécution
- [ ] Le listener écrit chaque événement dans un journal local (`results/<run>/xray_outbox.jsonl`)
      avec une clé d'idempotence (run_id + test + type d'événement + horodatage).
- [ ] Un synchroniseur (thread du listener + commande `python -m atelier xray-sync <dossier>`)
      envoie le journal à Xray avec reprise (backoff exponentiel), marque les événements envoyés,
      et peut rejouer un run complet plus tard.
- [ ] Le run Robot se termine normalement même si Xray est injoignable du début à la fin.
**Acceptation** : test avec un faux Xray qui échoue 3 fois puis répond → aucun événement perdu,
aucun doublon ; test avec Xray totalement indisponible → run terminé, journal complet, rejeu OK.

### 1.4 Vérification de l'API Xray
- [ ] Vérifier chaque appel listé dans CLAUDE.md (documentation officielle ou introspection
      GraphQL) ; corriger les noms et arguments ; documenter dans `docs/XRAY_API.md`.
- [ ] Préciser la gestion des statuts personnalisés (statuts de test run configurables par
      projet) : lire la liste des statuts disponibles plutôt que la supposer.

---

## Phase 2 — Assertions (fiabilité des tests générés)

- [ ] Modèle d'assertion : `type` ∈ {ui, api, base, historique}, `cible`, `attendu`, `source`
      (step « Alors », résultat attendu Xray, règle de gestion).
- [ ] Analyse des steps « Alors / Et » et des résultats attendus Xray → assertions candidates.
- [ ] Stratégie de vérification par type de résultat :
      message ou état à l'écran → UI ; statut ou montant → API si disponible, sinon base ;
      opération enregistrée → historique UI ou requête base. Ne pas tout vérifier par l'interface.
- [ ] Outil MCP `propose_assertion` (validé dans l'interface comme les steps).
- [ ] Keywords génériques du socle : `Vérifier Écran`, `Vérifier Valeur API`,
      `Vérifier En Base` (requête de la liste blanche), avec messages d'échec explicites.
- [ ] Contrôle : un test généré sans aucune assertion sur le résultat métier est refusé.
**Acceptation** : sur 3 scénarios fictifs (virement, ajout bénéficiaire, paiement facture), les
assertions générées couvrent chaque « Alors » ; tests unitaires de la classification.

---

## Phase 3 — Test Intelligence Engine (que faut-il automatiser ?)

- [ ] Collecte par projet Xray : tests manuels, type, priorité, libellés, composants, module
      (dossier du Test Repository), historique des exécutions (fréquence, statuts), défauts liés.
- [ ] Critères, chacun avec sa valeur, sa source et sa disponibilité :
      criticité métier, fréquence d'exécution, répétitivité, stabilité du parcours (carte),
      faisabilité (écrans et locators connus, robustesse), données (JDD disponibles),
      coût de maintenance estimé, recouvrement avec des tests existants (similarité de texte
      simple, sans dépendance lourde).
- [ ] Score pondéré configurable et **explicable** : chaque recommandation liste les critères qui
      l'ont fait monter ou descendre, et les données manquantes.
- [ ] Décision : à automatiser / à investiguer / à reporter / à ne pas automatiser.
- [ ] Onglet « Patrimoine » dans l'interface : tableau trié, filtres, export, envoi des tests
      retenus vers l'étape « Choisir le test ».
**Acceptation** : jeu de données Xray fictif (50 tests) → classement stable, chaque ligne justifiée,
critères manquants affichés comme tels (jamais inventés).

---

## Phase 4 — Carte robuste

- [ ] Reconnaissance pondérée : resource-id / accessibility id / data-testid (très élevé),
      texte fixe (élevé), structure (moyen), activité ou URL (moyen), position (faible) ;
      score de confiance renvoyé avec chaque reconnaissance.
- [ ] Contexte d'observation enregistré : plateforme, version de l'app, langue, état, rôle /
      compte, origine (observation, exploration, TNR), confiance.
- [ ] Modèle à deux niveaux : **écran fonctionnel** (nom métier, fonctionnalité) → une
      **implémentation** par plateforme (empreinte, éléments, transitions, comportements).
      Plus jamais de fusion technique automatique Android / iOS : on relie deux implémentations
      au même écran fonctionnel.
- [ ] Script de migration des fichiers `app_map/` existants vers le nouveau modèle.
**Acceptation** : jeux de hiérarchies fictives (variantes d'un même écran, écrans proches mais
différents) → zéro faux positif sur les cas « différents », reconnaissance des variantes.

---

## Phase 5 — Application Knowledge Graph (niveau 1)

- [ ] Entités : application, module, fonctionnalité, écran fonctionnel, test Xray, scénario BDD,
      test Robot. Relations typées avec `provenance` ∈ {observé, déclaré, déduit}, `source`,
      `date`, `statut` ∈ {validé, à valider}.
- [ ] Alimentation automatique : arborescence du Test Repository Xray (modules / fonctionnalités),
      liens tests ↔ BDD (Xray), tests Robot (tags de clé Xray), écrans ↔ tests (cartographie TNR).
- [ ] Vue arborescente module → fonctionnalité → écrans / tests / automatisations ; couverture.
- [ ] Outils MCP : `feature_info`, `coverage_report`, `screen_info` enrichi (fonctionnalité, tests).
- [ ] Règle : un lien « déduit » non validé n'est jamais utilisé pour une décision (TNR, score).
**Acceptation** : sur le dépôt fictif, la vue reconstitue la hiérarchie et la couverture sans saisie.
Niveaux suivants (hors phase) : règles de gestion (extraction des US Jira + validation),
rôles, API, dépendances et analyse d'impact branchée sur le calcul de profondeur.

---

## Phase 6 — API Discovery & Automation

- [ ] Import OpenAPI / Swagger : endpoints, méthodes, paramètres, schémas de réponse, sécurité.
- [ ] Dépendances entre endpoints (ressource créée par l'un, utilisée par l'autre).
- [ ] Liens endpoints ↔ fonctionnalités (knowledge graph) et ↔ tests Xray.
- [ ] Génération BDD puis Robot Framework avec RequestsLibrary, mêmes conventions
      (INITIALISATION + JDD, pas de donnée littérale, tags Xray), authentification configurable.
- [ ] Exécution et remontée Xray par le même moteur d'exécution (journal, reprise).
- [ ] Assertions API réutilisables par les tests mobiles et web (phase 2).
**Acceptation** : une spec OpenAPI fictive « bénéficiaires » → endpoints identifiés, tests générés
et exécutés contre un faux serveur local, résultats dans le journal Xray.

---

## Phase 7 — Boucle de maintenance encadrée et niveaux d'autonomie

- [ ] Qualification en 6 catégories : bug applicatif, données, locator invalide, environnement,
      synchronisation / timing, scénario ou assertion. Chaque qualification conserve ses preuves :
      logs, capture, step, locator utilisé, historique de l'écran dans la carte, score de confiance.
- [ ] Actions par catégorie : bug → brouillon d'anomalie Jira ; locator → proposition depuis la
      carte (locators de secours, tags apparus) ; timing → ajustement d'attente explicite ;
      données → vérification JDD ; scénario → signalement au QA.
- [ ] Validation humaine → réexécution → **3 exécutions stables** (Android et iOS si concernés)
      → proposition de MR GitLab (branche, diff, description, lien Xray). Jamais de commit direct.
- [ ] Contrôles avant MR : robocop, vérification des conventions (pas de donnée littérale,
      tags présents, pas de wrapper 1:1, assertions présentes), relecture critique par l'agent.
- [ ] Trois modes : **assisté** (validation de chaque step), **semi-autonome** (steps connus
      exécutés seuls, nouveaux steps validés), **autonome contrôlé** (scénario déjà approuvé,
      environnement autorisé). Passage d'un mode à l'autre conditionné par des indicateurs
      (taux de steps validés sans correction, taux de stabilité) et autorisé par un humain.
- [ ] Trois niveaux de sécurité : exploration / construction / exécution (voir CLAUDE.md).
- [ ] Indicateurs exportables (Grafana) : taux d'autonomie, coût et temps par test, instabilité.
**Acceptation** : scénarios d'échec simulés pour chaque catégorie → bonne qualification avec preuves,
aucune MR proposée avant 3 passages stables, aucune modification silencieuse.
