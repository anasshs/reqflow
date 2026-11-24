"""Fonctions-outils partagées par les façades (MCP, interface web, agent intégré).

Chaque fonction garde EXACTEMENT le nom, la signature et la docstring de l'outil MCP historique
(Cursor et les règles .cursor/rules en dépendent ; test de rétrocompatibilité) et se contente
d'appeler un moteur. Aucune logique métier ici.
"""
from __future__ import annotations

import os

from mcp.server.fastmcp import Image

from atelier.discovery import actions, carte, carte_outils, exploration, session
from atelier.domain import projet
from atelier.execution import jdd, robot, suivi
from atelier.generation import locators, steps
from atelier.integrations import interface_web
from atelier.intelligence import patrimoine

# Interface web en écran de contrôle (Cursor ou Claude Desktop pilotent, la page affiche) :
# WEB_EVENTS_URL=http://127.0.0.1:8765/api/events. Vide quand l'interface embarque les outils.
WEB_EVENTS_URL = os.environ.get("WEB_EVENTS_URL", "")

OUTILS: list = []


def outil(fn):
    """Marque une fonction comme outil exposé par les façades."""
    OUTILS.append(fn)
    return fn


def _agent():
    """Agent MCP de l'appel en cours (Cursor, Claude Code…) : attribution des dépôts, revues et propositions."""
    from atelier.domain import agent_mcp

    return agent_mcp


@outil
def list_devices() -> dict:
    """Liste les devices Android (adb) et iOS (simulateurs démarrés + devices physiques) connectés."""
    return session.list_devices()


@outil
def start_session(platform: str, udid: str = "", app: str = "", app_package: str = "",
                  app_activity: str = "", bundle_id: str = "", no_reset: bool = True,
                  extra_caps: dict | None = None, url: str = "", browser: str = "chromium",
                  headless: bool = True) -> dict:
    """Ouvre une session : 'android' / 'ios' (Appium) ou 'web' (navigateur Playwright, mêmes
    sélecteurs que Robot Framework Browser library).
    Web : url de départ, browser 'chromium' | 'firefox' | 'webkit', headless (False = fenêtre visible).
    Mobile : udid : device ciblé (voir list_devices).
    app : chemin .apk/.ipa (optionnel si l'app est déjà installée).
    Android : app_package / app_activity. iOS : bundle_id.
    extra_caps : capabilities supplémentaires (ex. {'appium:automationName': 'UiAutomator2'})."""
    return session.start_session(platform, udid, app, app_package, app_activity, bundle_id, no_reset,
                                 extra_caps, url, browser, headless)


@outil
def stop_session() -> str:
    """Ferme la session courante (mobile ou web)."""
    return session.stop_session()


@outil
def screenshot() -> Image:
    """Capture d'écran du device ou de la page web (pour vérifier visuellement l'écran courant)."""
    return Image(data=session.screenshot_png(), format="png")


@outil
def get_screen_elements(max_elements: int = 120) -> dict:
    """Liste les éléments significatifs de l'écran avec des locators AppiumLibrary
    classés du plus robuste au plus fragile. 'locator_unique' = False signale un
    locator principal ambigu à renforcer."""
    return session.get_screen_elements(max_elements)


@outil
def element_at(x_ratio: float, y_ratio: float) -> dict:
    """Élément situé à un point de l'écran (coordonnées en proportion 0-1 de la largeur et de la
    hauteur), avec ses locators. Sert à « montrer » un élément en touchant l'image de l'écran."""
    return session.element_at(x_ratio, y_ratio)


@outil
def open_url(url: str) -> dict:
    """Web uniquement : ouvre une URL dans la session navigateur."""
    return actions.open_url(url)


@outil
def get_page_source(max_chars: int = 60000) -> str:
    """Arbre brut de l'écran (XML mobile ou HTML web, tronqué), si get_screen_elements ne suffit pas."""
    return session.get_page_source(max_chars)


@outil
def locator_robustesse(locators: list[str], platform: str = "") -> dict:
    """Robustesse de locators selon la politique de l'atelier (web, Android natif ou Compose, iOS) : pour chacun
    niveau (Stable / Reliable / Fragile), score 1 à 5, raisons et conseil ; « classes » du plus robuste au plus
    fragile ; « regles » : ordre de préférence et interdits de la plateforme. Lecture seule. Vérifier ensuite le
    principal sur l'écran avec check_locator (un seul élément trouvé)."""
    from atelier.generation import robustesse_locators as r

    evals = [r.evaluer(l, platform) for l in locators]
    return {"evaluations": evals, "classes": r.classer(locators, platform), "regles": r.regles(platform)}


@outil
def check_locator(locator: str) -> dict:
    """Vérifie un locator : nombre d'éléments trouvés + texte/visibilité du premier."""
    # valeur d'un locator du dépôt : vérification journalisée pour lui (« verifie » : ses identifiants), la revue en tient
    # compte (description de l'outil inchangée : rétrocompatibilité MCP)
    r = session.check_locator(locator)
    try:
        from atelier.generation import studio

        ids = studio.noter_verification_valeur(locator, r, session.plateforme() or "")
        if ids:
            r = {**r, "verifie": ids}
    except Exception:  # noqa: BLE001 — dépôt illisible : la vérification elle-même reste rendue
        pass
    return r


@outil
def tap(locator: str, timeout: float = 10) -> str:
    """Touche / clique un élément. Mobile : locator AppiumLibrary (id=..., accessibility_id=...,
    xpath=...). Web : sélecteur Browser library (data-testid=..., id=..., css=..., text="...")."""
    from atelier.discovery import apprentissage

    return apprentissage.action_mcp("tap", locator, lambda: actions.tap(locator, timeout))


@outil
def type_text(locator: str, text: str, clear: bool = True, hide_keyboard: bool = True) -> str:
    """Saisit du texte dans un champ (mobile ou web)."""
    # Description figée (contrat des outils historiques). text peut citer une variable du référentiel de données
    # Discovery : {{var:CLE}} est remplacé par sa valeur côté serveur (seul moyen de saisir une valeur masquée).
    from atelier.discovery import apprentissage, donnees

    def saisir():
        reel = donnees.resoudre_saisie(text, locator)  # la valeur réelle ne revient ni à l'agent ni dans les événements
        return actions.type_text(locator, reel, clear, hide_keyboard, affiche=text)

    return apprentissage.action_mcp("type_text", locator, saisir)


@outil
def swipe(direction: str = "up", ratio: float = 0.6, duration_ms: int = 600) -> str:
    """Swipe plein écran (mobile) ou défilement (web). direction : up (vers le bas du contenu),
    down, left, right."""
    return actions.swipe(direction, ratio, duration_ms)


@outil
def press_back() -> str:
    """Retour : bouton retour Android, page précédente en web. Sur iOS, toucher le bouton de navigation."""
    return actions.press_back()


@outil
def wait_for(locator: str, timeout: float = 15) -> str:
    """Attend qu'un élément soit présent à l'écran."""
    return actions.wait_for(locator, timeout)


@outil
def capture_screen_locators(screen_name: str, selection: dict | None = None) -> dict:
    """Enregistre les locators de l'écran courant pour la plateforme de la session
    (correspond aux sous-tâches 'Locators Android' / 'Locators iOS').
    selection : {cle_metier: locator} pour ne garder et nommer que les éléments utiles.
    Sans selection, tous les éléments relevés sont gardés avec leur locator principal."""
    return locators.capture_screen_locators(screen_name, selection)


@outil
def generate_locators_resource(screen_name: str, output_dir: str = "resources/locators",
                               overwrite: bool = False) -> dict:
    """Fusionne les captures d'un écran en un fichier .resource Robot.
    Mobile : &{LOC_<ECRAN>_ANDROID} et &{LOC_<ECRAN>_IOS}, mêmes clés métier sur les deux
    plateformes (clés manquantes signalées). Web : &{LOC_<ECRAN>_WEB} (sélecteurs Browser library)."""
    return locators.generate_locators_resource(screen_name, output_dir, overwrite)


@outil
def propose_step(gherkin: str, keyword: str = "", locators: list[str] | None = None,
                 commentaire: str = "", attendre_validation: bool = True,
                 delai_max_s: int = 600) -> dict:
    """Propose un step Gherkin construit à partir de l'action faite sur le device.
    Avec l'interface web ouverte (WEB_EVENTS_URL), le step s'affiche dans « Scénario en
    construction » et l'outil attend que l'utilisateur clique Valider ou Corriger.
    Retour : decision ('validé', 'corrigé', 'refusé' ou 'sans validation') + correction éventuelle.
    En cas de correction, l'appliquer avant de passer au step suivant."""
    step = {"gherkin": gherkin, "keyword": keyword, "locators": locators or [], "commentaire": commentaire}
    return steps.proposer(step, interface_web.base(WEB_EVENTS_URL), attendre_validation, delai_max_s)


@outil
def list_project_files(pattern: str = "**/*.robot") -> list[str]:
    """Liste les fichiers du projet de tests (ex. '**/*.resource', 'tests/**/*.robot')."""
    return projet.lister_fichiers(pattern)


@outil
def read_project_file(path: str) -> str:
    """Lit un fichier du projet (keywords existants, steps, suites) pour réutiliser le socle."""
    return projet.lire_fichier(path)


@outil
def write_project_file(path: str, content: str, overwrite: bool = False) -> str:
    """Écrit un fichier dans le projet (nouvelle suite, steps…). Refuse d'écraser sans overwrite=True."""
    r = projet.ecrire_fichier(path, content, overwrite)
    if path.endswith(".robot") and "*** Test Cases ***" in content:  # suite écrite par l'agent : revue humaine avant exécution
        from atelier.generation import studio

        studio.entrer_en_revue(path, "cursor")
    return r


@outil
def parse_robot_output(output_xml: str = "results/mcp/output.xml") -> dict:
    """Résumé d'un output.xml : stats + tests en échec avec message et keyword fautif."""
    return robot.parse_robot_output(output_xml)


@outil
def run_robot(target: str, include_tags: list[str] | None = None,
              exclude_tags: list[str] | None = None, variables: dict | None = None,
              dry_run: bool = False, output_dir: str = "results/mcp",
              xray_ticket: str = "", xray_mode: str = "live",
              exec_summary: str = "", plan_summary: str = "",
              test_environments: list[str] | None = None,
              jira_transition_start: str = "", jira_transition_end: str = "",
              jira_transition_end_if_fail: str = "",
              attach_screenshots: bool = True, jdd_env: str = "",
              jdd_jeux: list[str] | None = None, events_url: str = "",
              relancer_echecs: bool = False, cartographie: bool = False, timeout_s: int = 3600) -> dict:
    """Lance une suite ou un dossier Robot Framework du projet puis renvoie le bilan.
    variables : ex. {'PLATFORM': 'android', 'DEVICE': 'emulator-5554'} (sélection du device).

    xray_ticket : une seule clé Jira, dont le type est détecté automatiquement :
      - Test Plan       -> crée une nouvelle exécution et l'ajoute au plan ;
      - Test Execution  -> met à jour cette exécution (tests manquants ajoutés) ;
      - autre ticket (US, epic…) ou clé projet seule (ex. TAM) -> crée un plan + une exécution.
    xray_mode :
      - 'live' (défaut) : listener du MCP, test run en EXECUTING au démarrage de chaque test,
        PASSED / FAILED à la fin, heures de début et de fin, message d'échec et captures ;
      - 'listener_projet' : listener du projet (ROBOT_XRAY_LISTENER) avec la clé d'exécution ;
      - 'aucun'.
    test_environments : environnements Xray de l'exécution (défaut : valeur de PLATFORM).
    jira_transition_start / _end / _end_if_fail : transition Jira (nom de la transition ou du
      statut cible) appliquée au ticket d'exécution au début du run, à la fin, ou à la fin
      s'il y a au moins un échec.
    jdd_env / jdd_jeux : environnement et jeux de données à injecter (ex. 'recette',
      ['VIREMENT_STANDARD']). Les prérequis sont vérifiés AVANT le run : s'il manque des
      données, le run n'est pas lancé et le bilan indique « bloqué données ». Chaque jeu
      devient un dictionnaire &{JDD_<NOM>} utilisable dans « Initialiser Le Test ».
    events_url : URL qui reçoit les événements du run en direct (interface web).
    cartographie : enrichit la carte de l'application pendant le run (écrans et transitions des
      tests mobiles, test Xray qui passe par chaque écran). Ralentit un peu chaque action.
    relancer_echecs : rejoue uniquement les tests en échec du run précédent (même output_dir).
      Pour mettre à jour la même exécution Xray, passer sa clé dans xray_ticket.
    La session Appium du MCP est fermée avant le run pour libérer le device."""
    # Transitions Jira : jamais appliquées directement depuis Cursor ; demandes à valider après le run (V2, phase 0 bis)
    transitions = {"début": jira_transition_start, "fin": jira_transition_end, "fin si échec": jira_transition_end_if_fail}
    bilan = robot.run_robot(target, include_tags, exclude_tags, variables, dry_run, output_dir, xray_ticket, xray_mode,
                           exec_summary, plan_summary, test_environments, "",
                           "", "", attach_screenshots, jdd_env, jdd_jeux,
                           events_url or WEB_EVENTS_URL, relancer_echecs, cartographie, timeout_s)
    demandees = {k: v for k, v in transitions.items() if v}
    if demandees and not dry_run:
        from atelier.domain import demandes

        ticket = ((bilan.get("xray") or {}).get("execution")) or xray_ticket
        echec = bool((bilan.get("resultat") or {}).get("echecs") or bilan.get("code_retour"))
        a_faire = [(m, t) for m, t in demandees.items() if m != "fin si échec" or echec]
        bilan["transitions_jira"] = [demandes.creer("jira_transition", {"issue_key": ticket, "transition": t},
                                                    f"{ticket} → {t} (transition « {m} » du run)")["id"] for m, t in a_faire if ticket]
        bilan["transitions_jira_note"] = "Transitions Jira déposées en demandes : à valider dans l'atelier (À valider)."
    return bilan


@outil
def xray_get_test(test_key: str) -> dict:
    """Lit un test Xray : type, scénario Gherkin (Cucumber) ou étapes manuelles, libellés.
    Point de départ pour automatiser un parcours : Claude déroule ces étapes sur le device."""
    return patrimoine.xray_get_test(test_key)


@outil
def list_jdd(env: str = "") -> dict:
    """Liste les jeux de données d'un environnement (sans env : liste des environnements)."""
    return jdd.liste(env)


@outil
def get_jdd(env: str, jeu: str) -> dict:
    """Détail d'un jeu de données (secrets affichés sous forme {{env:VARIABLE}}, jamais en clair)."""
    return jdd.lire(env, jeu)


@outil
def find_test_data(env: str, requete: str, params: dict | None = None) -> list[dict]:
    """Cherche des données éligibles via une requête de la liste blanche (requetes.yaml),
    en lecture seule. Ex. requete='compte_avec_solde', params={'client': 'U123456', 'montant_min': 150}."""
    return jdd.executer_requete(env, requete, params)


@outil
def check_jdd(env: str, jeux: list[str]) -> dict:
    """Vérifie les prérequis de données AVANT un run. Un jeu bloqué = test « bloqué données »,
    à ne pas lancer (évite les faux échecs, ex. compte sans solde pour un virement)."""
    return jdd.verifier(env, jeux)


@outil
def xray_search_tests(jql: str, limit: int = 50) -> list[dict]:
    """Cherche des tests Xray par JQL, ex. les candidats à l'automatisation d'un projet."""
    return patrimoine.xray_search_tests(jql, limit)


@outil
def add_screen_locator(screen_name: str, key: str, locator: str, platform: str = "") -> dict:
    """Ajoute ou remplace une clé dans les locators capturés d'un écran (plateforme de la session
    par défaut). Sert à corriger un locator sans tout recapturer."""
    # V2 (phase 0 bis) : une clé nouvelle est ajoutée directement ; remplacer une valeur existante devient une demande
    from atelier.domain import demandes

    ancien = locators.locator_capture(screen_name, key, platform)
    if ancien is None or ancien == locator:
        return locators.add_screen_locator(screen_name, key, locator, platform)
    p = locators.plateforme(platform)
    d = demandes.creer("remplacer_locator", {"screen_name": screen_name, "key": key, "locator": locator, "platform": p},
                       f"{screen_name}.{key}@{p} : {ancien} → {locator}", apercu={"avant": ancien, "apres": locator})
    return {"ecran": screen_name, "platform": p, "cle": key, "statut": "en attente de validation", "demande": d["id"],
            "message": demandes.message(d)}


@outil
def jira_subtasks(issue_key: str) -> list[dict]:
    """Sous-tâches d'un ticket (ex. ST1 Locators Android… ST5 Branchement) avec leur statut."""
    return suivi.jira_subtasks(issue_key)


@outil
def qualify_failure(run_id: str, qualification: str, commentaire: str = "", message_echec: str = "") -> str:
    """Qualifie un échec dans le test run Xray : bug, données, locator ou environnement."""
    # V2 (phase 0 bis) : écriture Xray déposée en demande, envoyée après validation dans l'atelier
    from atelier.domain import demandes

    d = demandes.creer("qualify_failure", {"run_id": run_id, "qualification": qualification, "commentaire": commentaire,
                                           "message_echec": message_echec[:2000]}, f"test run {run_id} : {qualification}")
    return demandes.message(d)


@outil
def map_apps() -> dict:
    """Applications cartographiées et application active."""
    return carte_outils.map_apps()


@outil
def map_create_app(nom: str, plateformes: list[str], app_package: str = "", app_activity: str = "",
                   bundle_id: str = "", url: str = "", build: str = "", langue: str = "fr") -> dict:
    """Déclare une nouvelle application à cartographier (devient l'application active)."""
    return carte_outils.map_create_app(nom, plateformes, app_package, app_activity, bundle_id, url, build, langue)


@outil
def map_select_app(app: str) -> dict:
    """Change d'application active (slug, voir map_apps)."""
    return carte.choisir_app(app)


@outil
def map_set_build(build: str) -> dict:
    """Indique le build testé : les écrans revisités sont comparés à leur version précédente."""
    return carte.maj_app(build=build)


@outil
def where_am_i() -> dict:
    """Écran courant d'après la carte (créé s'il est inconnu), avec ses éléments et locators connus."""
    return exploration.where_am_i()


@outil
def list_screens(module: str = "") -> list[dict]:
    """Écrans de la carte (nom, titre, module, plateformes, couverture par les tests)."""
    return carte_outils.list_screens(module)


@outil
def screen_info(ecran: str) -> dict:
    """Détail d'un écran (par nom, alias ou id) : éléments, locators par plateforme, transitions."""
    return carte_outils.screen_info(ecran)


@outil
def name_screen(ecran: str, nom: str, module: str = "") -> dict:
    """Donne un nom métier à un écran (ex. virement_saisie). Un nom déjà utilisé fusionne les deux
    écrans (cas du même écran vu sur Android puis sur iOS)."""
    # V2 (phase 0 bis) : le simple nommage est immédiat ; la fusion devient une demande à valider
    from atelier.discovery import carte
    from atelier.domain import demandes

    autre = carte.ecran_nomme(nom, sauf=ecran)
    if not autre:
        return carte_outils.name_screen(ecran, nom, module)
    d = demandes.creer("fusion_ecrans", {"ecran": ecran, "nom": nom, "module": module},
                       f"écran {ecran} → fusion avec « {autre.get('nom')} » ({autre['id']})")
    return {"ecran": ecran, "statut": "en attente de validation", "demande": d["id"], "message": demandes.message(d)}


@outil
def goto_screen(ecran: str) -> dict:
    """Va sur un écran connu en rejouant le chemin le plus fiable de la carte (avec rattrapage)."""
    return exploration.goto_screen(ecran)


@outil
def explore(max_ecrans: int = 25, profondeur: int = 3, duree_max_s: int = 900) -> dict:
    """Explore automatiquement l'application depuis l'écran courant (hors liste rouge, sans saisie).
    Long : préférer le lancement depuis l'interface web, qui montre la progression."""
    # description figée (outil historique, tests/test_retrocompatibilite.py). Pendant une session Discovery bornée à un
    # périmètre, l'exploration ne repart jamais d'un écran déjà connu hors de ce périmètre (exploration.py).
    return exploration.explorer(max_ecrans, profondeur, duree_max_s)


@outil
def stop_exploration() -> str:
    """Demande l'arrêt de l'exploration en cours."""
    return exploration.stop_exploration()


@outil
def map_import_existing(pattern: str = "**/*.resource") -> dict:
    """Amorce la carte avec les locators des fichiers .resource existants du projet."""
    return carte_outils.map_import_existing(pattern)


@outil
def map_tags_report(limite: int = 200) -> dict:
    """Éléments sans identifiant de test (Compose sans testTag, SwiftUI sans identifier, web sans
    data-testid), classés par nombre de tests concernés, avec le tag proposé."""
    return carte_outils.map_tags_report(limite)


@outil
def export_screen_resource(ecran: str, output_dir: str = "resources/locators") -> str:
    """Génère le .resource d'un écran depuis la carte (locator principal + secours par plateforme)."""
    return locators.export_screen_resource(ecran, output_dir)


@outil
def xray_inspect_ticket(ticket: str) -> dict:
    """Indique ce que deviendra un run sur ce ticket : Test Plan (nouvelle exécution ajoutée),
    Test Execution (mise à jour), autre ticket / projet (création plan + exécution)."""
    return suivi.xray_inspect_ticket(ticket)


@outil
def jira_transition(issue_key: str, transition: str) -> str:
    """Fait passer un ticket Jira dans un statut (nom de transition ou de statut cible)."""
    # V2 (phase 0 bis) : écriture Jira déposée en demande, exécutée après validation dans l'atelier
    from atelier.domain import demandes

    d = demandes.creer("jira_transition", {"issue_key": issue_key, "transition": transition}, f"{issue_key} → {transition}")
    return demandes.message(d)


@outil
def import_results_to_xray(output_xml: str = "results/mcp/output.xml",
                           test_execution_key: str = "", project_key: str = "",
                           test_plan_key: str = "") -> dict:
    """Envoie un output.xml Robot dans Xray Cloud (import/execution/robot), en secours
    quand le run s'est fait sans listener. N'utiliser pas sur un run déjà remonté en live."""
    # V2 (phase 0 bis) : écriture Xray déposée en demande (aperçu des statistiques), envoyée après validation
    from atelier.domain import demandes

    if not (test_execution_key or project_key):
        raise ValueError("Renseigner test_execution_key ou project_key.")
    projet.safe_path(output_xml)
    try:
        resume = parse_robot_output(output_xml)
        apercu = {k: resume.get(k) for k in ("passes", "echecs") if k in resume}
    except Exception as e:  # noqa: BLE001 — aperçu facultatif
        apercu = {"erreur": str(e)[:200]}
    d = demandes.creer("import_results_to_xray", {"output_xml": output_xml, "test_execution_key": test_execution_key,
                                                  "project_key": project_key, "test_plan_key": test_plan_key},
                       f"{output_xml} → {test_execution_key or 'nouvelle exécution ' + project_key}", apercu=apercu)
    return {"statut": "en attente de validation", "demande": d["id"], "apercu": apercu, "message": demandes.message(d)}



# --------------------------------------------------------------------------- espaces de travail (ajouts)
@outil
def knowledge_graph(categorie: str = "", recherche: str = "", centre: str = "", profondeur: int = 1) -> dict:
    """Graphe de connaissance de l'application (carte, dépôt Robot, JDD, patrimoine Xray, déclarations).
    categorie : APPLICATION, FONCTIONNEL, TECHNIQUE, JIRA, XRAY, BDD ou AUTOMATION (vide = tout).
    centre : identifiant d'un nœud (ex. 'ecran:virement_saisie') pour n'avoir que son voisinage."""
    from atelier.discovery import espaces

    return espaces.vue_connaissance(None, [categorie] if categorie else None, "", recherche, centre, profondeur)


@outil
def mbt_modele(perimetre: str) -> dict:
    """Model-Based Testing : construit ou actualise le modèle comportemental d'un périmètre et le renvoie pour lecture
    (états, transitions, conditions, critères des US, informations manquantes, éléments rejetés à ne pas reproposer).
    perimetre : 'module:Comptes', 'user_story:DEMO-12', 'parcours:<id>', 'fonctionnalite:<id>', 'ecran:<nom>' ou 'application'.
    Seul le fichier comportement/<id>.yaml du projet est écrit (nouvelle version si le comportement change)."""
    from atelier.intelligence import mbt

    type_, _, id_ = perimetre.partition(":")
    m = mbt.construire(type_, perimetre if id_ else "")
    return {"resume": mbt.resume(m), "lecture": mbt.lecture_pour_ia(m["id"])}


@outil
def mbt_chemins(modele: str, strategie: str = "transitions", mode: str = "exploratoire", inclure_couverts: bool = False) -> dict:
    """Le minimum de chemins d'un modèle comportemental pour la stratégie, chacun avec sa valeur ajoutée (ce qu'il couvre
    de nouveau), sa justification, ses informations manquantes, son niveau (hypothèse ou établi), les scénarios existants
    et la préparation à l'automatisation ; plus la structure, les hypothèses et les scénarios réutilisés.
    strategie : etats, transitions, paires, conditions, chemins, critiques. mode : exploratoire ou verifie (éléments
    établis seulement). Par défaut, ce que les scénarios existants couvrent déjà n'est pas reciblé."""
    from atelier.intelligence import mbt

    return mbt.analyser(modele, strategie, None, mode, inclure_couverts)


@outil
def mbt_deposer_propositions(modele: str, propositions: dict) -> dict:
    """Dépose des propositions d'enrichissement du modèle (Cursor ou autre IA) : {"etats": [{nom, type, justification}],
    "transitions": [{de, vers, action, garde, issue, justification}], "conditions": [{libelle, justification}],
    "incoherences": [texte], "revisions": [{scenario, proposition}]} (révisions de scénarios : proposées, jamais appliquées). Toujours « déduit » et « à valider » : rien n'est confirmé sans le QA. Ne jamais inventer un
    message d'erreur ni une règle absente des textes fournis par mbt_modele."""
    from atelier.domain import comportement
    from atelier.intelligence import mbt

    r = comportement.deposer_propositions(modele, propositions or {}, source="Cursor (MCP)")
    mbt.vider_cache()
    return {"ajoutes": r["ajoutes"], "ignores": r["ignores"], "modele": mbt.resume(r["modele"])}


@outil
def mbt_generer_bdd(modele: str, chemins: list[str] | None = None, strategie: str = "transitions") -> dict:
    """Crée les scénarios BDD (brouillons, référentiel BDD existant) des chemins choisis d'un modèle comportemental
    (tous ceux de la stratégie si aucun). Doublons détectés et non recréés ; traçabilité modèle → chemin → scénario gardée."""
    from atelier.generation import mbt_bdd

    return mbt_bdd.generer(modele, chemins or None, strategie, False, "MBT")


@outil
def impact_analysis(element: str) -> dict:
    """Analyse d'impact d'une modification (locator, keyword, resource, écran, JDD…) : tests Robot et Xray,
    modules, plateformes concernés et TNR ciblée (include_tags pour run_robot).
    element : identifiant de nœud, ex. 'locator:virement_saisie.bouton_valider@android', 'keyword:seconnecter'."""
    from atelier.discovery import espaces

    return espaces.impact(element)


@outil
def coverage_report(module: str = "") -> dict:
    """Couverture du patrimoine Xray (instantané patrimoine/xray.json) : tests automatisés / manuels par module,
    exigences non couvertes, redondances candidates, avec les définitions utilisées."""
    from atelier.discovery import espaces

    v = espaces.vue_couverture(module)
    return {"indicateurs": v["indicateurs"], "instantane": v["instantane"]}


@outil
def automation_flow(cible: str = "") -> dict:
    """Construction technique d'un test automatisé : scénario Xray -> test Robot -> keywords -> locators,
    JDD -> requêtes, bibliothèques et plateformes. cible : 'test:DEMO-1' ou 'test_robot:<fichier>::<nom>'."""
    from atelier.discovery import espaces

    return espaces.vue_flux(cible)


@outil
def testabilite_us_a_traiter(limite: int = 20) -> list:
    """Testabilité des US : User Stories à analyser (texte masqué, réponses de l'équipe). Lire chaque US, repérer les
    ambiguïtés, formuler des questions et proposer des cas de test, puis les déposer avec testabilite_deposer_proposition.
    Aucune proposition n'est appliquée sans validation humaine dans l'atelier."""
    from atelier.intelligence import testabilite_us

    return testabilite_us.a_traiter(limite)


@outil
def testabilite_deposer_proposition(cle: str, constats: list, cas: list) -> dict:
    """Dépose l'analyse de l'agent pour une US. constats : [{"gravite": "haute|moyenne|basse", "message", "extrait",
    "question"}] ; cas : [{"titre", "etapes": [{"action", "donnees", "resultat"}], "gherkin"}]. N'invente aucune règle
    métier : une information absente devient une question. Rien n'est envoyé à Jira ni créé dans Xray."""
    from atelier.intelligence import testabilite_us

    r = testabilite_us.deposer_proposition(cle, constats or [], cas or [], _agent().source())
    return {"cle": cle, "statut": r["statut"], "constats": len(r["constats"]), "cas": len(r["cas"])}


@outil
def discovery_demarrer(environnement: str = "", mode: str = "assistee", perimetre: str = "", profil_donnees: str = "",
                       parcours: str = "") -> dict:
    """Démarre une session Discovery sur l'application de la carte et la plateforme de la session ouverte
    (start_session d'abord). Pendant la session, tap et type_text sont classés (Safe / Controlled / Sensitive /
    Forbidden) : les actions interdites et sensibles sont refusées, la saisie dépend de l'environnement.
    profil_donnees : profil du référentiel de données (Discovery › Données) dont la session tire ses valeurs.
    perimetre : texte libre, ou un périmètre d'exploration reconnu — module de la carte (« module:eSim ») ou parcours
    validé (« parcours:… »). La session est alors bornée : discovery_ecran_courant dit dans « session.perimetre » si
    l'écran courant en est sorti (ne rien y essayer, revenir) ; un écran découvert pendant la session en fait partie.
    parcours : identifiant d'un parcours utilisateur préparé dans l'atelier (« PU-… », voir discovery_parcours_cadre) ;
    la session le déroule : environnement, périmètre et profil viennent du cadrage s'ils ne sont pas précisés, et les
    écrans traversés sont proposés au parcours à la fin."""
    from atelier.discovery import session, sessions_discovery

    s = sessions_discovery.creer({"plateforme": session.plateforme() or "", "environnement": environnement, "mode": mode,
                                  "perimetre": perimetre, "device": "agent MCP", "profil_donnees": profil_donnees, "parcours": parcours})
    return {k: v for k, v in sessions_discovery.demarrer(s["id"]).items() if k in ("id", "statut", "config")}


@outil
def discovery_parcours_cadre(parcours: str = "") -> dict:
    """Cadrage d'un parcours utilisateur préparé par l'automaticien avant l'exploration (Discovery › Préparer un parcours).
    Sans argument : les parcours préparés (identifiant, nom, statut, exigences, profil de données, cible). Avec un
    identifiant « PU-… » : objectif, point de départ, résultat attendu, exigences Jira avec description et critères
    d'acceptation, variables du profil prêtes ou bloquées (jamais leur valeur), écrans déjà traversés. Lecture seule :
    le cadrage ne se modifie que dans l'atelier."""
    from atelier.discovery import parcours_utilisateur

    return parcours_utilisateur.cadre_agent(parcours)


# Référentiel universel de données (Discovery Data Setup) : l'automaticien prépare variables, profils et générateurs dans
# l'atelier ; l'agent lit, demande des valeurs cohérentes et enrichit le contexte de SA session. Il ne crée ni ne modifie
# aucune définition, et ne reçoit jamais une valeur confidentielle ou secrète (saisie par référence {{var:CLE}}).
@outil
def discovery_donnees_catalogue(recherche: str = "", type: str = "", profil: str = "") -> dict:
    """Référentiel de données Discovery : variables déclarées (clé, nom, type, sensibilité, source, règles, alias,
    dépendances), profils / groupes, générateurs et réglages. Filtres : recherche (texte), type (texte, nombre, date,
    email, telephone…), profil. Aucune valeur sensible. Lecture seule."""
    from atelier.discovery import donnees

    return {"variables": [{k: v[k] for k in ("cle", "nom", "description", "type", "sensibilite", "regles", "alias", "dependances", "statut")}
                          | {"source": v["source"]["type"]} for v in donnees.variables(recherche, type, profil)],
            "profils": donnees.profils(), "generateurs": donnees.generateurs(), "reglages": donnees.reglages(),
            "contexte": donnees.session_courante()}


@outil
def discovery_donnees_pour_champs(champs: list[dict], ecran: str = "") -> dict:
    """Besoins en données d'un écran, à appeler AVANT de remplir un formulaire. champs : [{"libelle": "Adresse e-mail",
    "type": "email" (type technique du champ, facultatif), "contraintes": {"longueur_max": 50}}]. Pour chaque champ :
    nature de la donnée attendue, variable du référentiel retenue, valeur cohérente avec le reste de la session (masquée
    si sensible) et la référence de saisie {{var:CLE}} à passer à type_text. statut « manquante » : aucune variable ne
    convient → ne rien inventer, le signaler à l'automaticien. Les valeurs obtenues sont gardées pour la session."""
    from atelier.discovery import donnees

    return donnees.pour_champs(champs or [], ecran)


@outil
def discovery_donnee(cle: str, champ: str = "") -> dict:
    """Valeur d'une variable du référentiel pour la session en cours : déjà utilisée (inchangée), sinon réglée pour le
    profil ou l'environnement, sinon générée ou calculée depuis ses dépendances. Une valeur sensible revient masquée :
    la saisir avec type_text(locator, "{{var:CLE}}"). Erreur explicite si aucune valeur n'est disponible."""
    from atelier.discovery import donnees

    return donnees.obtenir(str(cle or "").strip().upper(), champ=champ)


@outil
def discovery_donnee_definir(cle: str, valeur: str, description: str = "", sensible: bool = False) -> dict:
    """Enrichit le contexte de données de la session avec une valeur RELEVÉE dans l'application ou choisie pendant le
    parcours (référence de dossier affichée, date sélectionnée), pour la réutiliser sur les écrans suivants. Jamais une
    donnée métier inventée. N'ajoute rien au catalogue : l'automaticien décide d'en faire une variable."""
    from atelier.discovery import donnees

    return donnees.definir_contexte(cle, valeur, description, sensible)


@outil
def discovery_donnee_proposer(cle: str, valeur: str, nom: str = "", type: str = "texte", description: str = "",
                              regles: dict | None = None) -> dict:
    """Donnée absente du référentiel (discovery_donnees_pour_champs : statut « manquante ») : propose-la avec une valeur
    de TEST plausible, au format du champ (ex. RIB de 24 chiffres, nom fictif). Elle entre au catalogue « à valider »,
    rejoint le profil de données du parcours en cours et se saisit tout de suite avec type_text(locator, "{{var:CLE}}").
    L'automaticien la confirme ou la change dans l'atelier. À la fin du parcours, discovery_profil_vers_jdd(profil,
    environnement) en fait le jeu de données du test. Une variable déjà confirmée ne se propose pas : l'utiliser."""
    from atelier.discovery import donnees, sessions_discovery

    s = sessions_discovery.active() or {}
    return donnees.proposer_variable(cle, valeur, nom, type, description, regles, (s.get("config") or {}).get("parcours", ""),
                                     _agent().source())


@outil
def discovery_profil_vers_jdd(profil: str, environnement: str, jeu: str = "") -> dict:
    """Crée (ou met à jour) le jeu de données des tests automatisés (data/jdd/<environnement>.yaml) depuis un profil du
    référentiel Discovery : le test rejoue avec les valeurs de la Discovery. Champ = clé de la variable en minuscules,
    lu dans un keyword par ${JDD}[champ] (« dans_un_keyword »). Date générée (J+N) : recalculée à chaque run ;
    variable sensible : {{env:CLE}}, jamais écrite. Associer ensuite le jeu au test BDD."""
    from atelier.discovery import donnees

    return donnees.profil_vers_jdd(profil, environnement, jeu)


@outil
def discovery_donnees_contexte(profil: str = "", environnement: str = "") -> dict:
    """Data Context de la session Discovery en cours : valeurs déjà utilisées (masquées si sensibles), leur origine
    (référentiel, source externe, générée, calculée, créée pendant la session) et leurs dépendances. profil /
    environnement : choisit le profil de données ou l'environnement du contexte avant de le lire."""
    from atelier.discovery import donnees

    return donnees.choisir(profil or None, environnement or None) if profil or environnement else donnees.contexte()


@outil
def discovery_ecran_courant() -> dict:
    """Écran courant pour explorer : écran de la carte (nouveau ou non, noms déjà proposés), éléments avec leur classe
    et l'autorisation dans la session, textes affichés (messages), actions sûres jamais essayées, pistes de la carte
    (impasses, écrans isolés, transitions instables). À appeler après chaque action."""
    from atelier.discovery import apprentissage

    return apprentissage.ecran_courant()


@outil
def discovery_proposer(nature: str, libelle: str, ecran: str = "", description: str = "", module: str = "",
                       exigence: str = "") -> dict:
    """Dépose ce que tu as compris dans le Knowledge Graph, comme proposition à valider par l'automaticien.
    nature : nom_ecran (libelle = nom métier, module), fonctionnalite, parcours, regle, action, role, entite
    (reliés à l'écran), lien_exigence (exigence = clé Jira de la copie locale, l'exigence impacte l'écran).
    N'invente rien : uniquement ce qui est observé à l'écran ou écrit dans une exigence."""
    from atelier.discovery import apprentissage

    return apprentissage.proposer(nature, libelle, ecran, description, module, exigence, _agent().cle())


@outil
def discovery_parcours_vers_bdd(ecrans: list | None = None, parcours: str = "", titre: str = "", forcer: bool = False) -> dict:
    """Crée dans Test Design un brouillon de scénario BDD depuis la carte : soit une suite ordonnée d'écrans
    (identifiants ou noms), soit un parcours du Knowledge Graph (ex. « parcours:virement_interne »). Étapes reliées
    aux écrans et locators connus, données par le jeu de données, actions sensibles signalées. À relire et valider
    dans l'atelier avant l'automatisation. Un déroulé qu'un test BDD existant fait déjà n'est pas recréé : la réponse
    donne ce test (deja_couvert) ; forcer=True crée quand même une variante."""
    from atelier.generation import parcours_bdd

    try:
        r = parcours_bdd.brouillon(ecrans=ecrans or None, parcours=parcours, titre=titre, forcer=forcer)
    except parcours_bdd.DejaCouvert as e:
        return {"cle": "", "deja_couvert": e.existant, "message": str(e)}
    return {k: r[k] for k in ("cle", "titre", "gherkin", "locators", "donnees", "avertissements")}


@outil
def plan_de_test(module: str) -> dict:
    """Résumé d'un module pour dresser son plan de test (au lieu du graphe brut) : écrans (et locators fragiles),
    parcours, fonctionnalités, règles, exigences Jira avec leurs tests Xray (automatisés ou non, dernier statut),
    ce qui n'est pas couvert, actions sensibles, endpoints, et des pistes. module : nom (« Virements ») ou
    identifiant (« module:Virements »)."""
    from atelier.intelligence import plan_test

    return plan_test.plan(module)


@outil
def discovery_terminer() -> dict:
    """Termine la session Discovery en cours : résultats (nouveaux écrans, transitions, comportements, endpoints,
    actions refusées) et propositions en attente de validation."""
    from atelier.discovery import apprentissage, sessions_discovery

    s = sessions_discovery.active()
    if not s:
        raise RuntimeError("Aucune session Discovery en cours.")
    fin = sessions_discovery.arreter(s["id"])
    r = {k: v for k, v in (fin.get("resultats") or {}).items() if k not in ("nouveaux", "modifies")}
    return {"id": fin["id"], "resultats": r, "propositions_a_valider": len(apprentissage.propositions(fin["id"]))}


# =========================================================================== Construire / Automation Studio (Cursor construit,
# l'automaticien valide dans l'atelier : revue technique, aucune approbation possible depuis l'agent)
@outil
def studio_socle(module: str = "", env: str = "") -> dict:
    """Ce qu'il faut réutiliser avant d'écrire un test : keywords du socle (nom, documentation, fichier, utilisations,
    signaux doublon / wrapper 1:1), locators par écran avec leur état (Stable, Reliable, Fragile, Obsolete, Missing),
    jeux de données de l'environnement, conventions du projet et « structure » : où le dépôt range déjà ses tests, ses
    keywords / page objects et ses locators (racine et dossiers par genre) ; tout nouveau fichier suit cette structure.
    module : filtre sur l'écran ou la catégorie."""
    from atelier.generation import structure_depot, studio

    f = (module or "").lower()
    kws = [{k: x[k] for k in ("nom", "documentation", "fichier", "categorie", "utilisations", "doublon", "wrapper_1_1", "plateformes")}
           for x in studio.keywords() if not f or f in x["categorie"].lower() or f in x["nom"].lower()]
    locs = [{k: x[k] for k in ("ecran", "cle", "plateforme", "valeur", "etat", "fichier")} for x in studio.locators() if not f or f in x["ecran"]]
    envs = jdd.environnements()
    e = env or (envs[0] if envs else "")
    return {"keywords": kws, "locators": locs, "environnement": e, "jeux": jdd.lister(e) if e else [],
            "structure": structure_depot.resume(),
            "conventions": ["ranger chaque fichier dans le dossier de son genre, comme le dépôt le fait déjà (« structure ») : aucun nouveau dossier racine",
                            "Gherkin français + Page Object Model : locators / keywords / scénarios séparés",
                            "INITIALISATION : Initialiser Le Test    &{JDD_<NOM>} ; aucune donnée littérale dans le scénario",
                            "réutiliser les keywords du socle ; jamais de wrapper 1:1 par élément",
                            "une suite par parcours métier : studio_generer_depuis_bdd choisit la suite du parcours et y ajoute le test (« ajout ») ; ne pas imposer un autre chemin",
                            "tags : clé Xray + tags fonctionnels (smoke, e2e, negatif, consomme_donnee)",
                            "tout script écrit entre en revue technique : l'automaticien l'approuve dans l'atelier"]}


@outil
def studio_rapprocher_etapes(etapes: list[str]) -> dict:
    """À appeler AVANT de rédiger ou de proposer des étapes BDD : rapproche chaque texte d'étape des keywords du dépôt.
    Pour chaque étape : statut « existant » (keyword réutilisé tel quel : même nom ou arguments intégrés), « proche »
    (un keyword existant emploie les mêmes mots : reprendre son libellé exact, ne pas créer de doublon) ou « à créer »,
    avec le keyword, son fichier et sa documentation. Lecture seule ; comparaison de mots, sans IA."""
    from atelier.generation import reutilisation

    return reutilisation.rapprocher_etapes(etapes or [])


@outil
def studio_scenario_bdd(cle: str) -> dict:
    """Scénario BDD d'un test Xray (Test Design) et son mapping vers le socle : pour chaque étape, keyword existant ou
    à créer, keywords proches à reprendre (doublons possibles), locators et leur état, données ${DONNEES.x}, assertion.
    Point de départ pour écrire le test Robot."""
    from atelier.generation import bdd, studio

    m = bdd._exiger(cle)
    return {"cle": cle, "titre": m.get("titre", ""), "gherkin": bdd.serialiser(m), "controles": bdd.controles(m),
            "mapping": studio.mapping_bdd(cle)}


@outil
def tnr_conventions() -> dict:
    """Conventions TNR de l'application active : étiquette Jira des tests publiés, dossier Xray, Test Plan TNR et
    campagne de l'Execution Center (vides tant que rien n'a été publié). Lecture seule."""
    from atelier.generation import tnr

    return tnr.conventions()


@outil
def tnr_demander_publication(scenarios: list[str]) -> str:
    """Publier au TNR des scénarios BDD vérifiés (clés de Test Design) : un test Xray Cucumber par scénario (découpage
    automatique), étiquette et dossier de l'application, ajout au Test Plan TNR (créé s'il manque), campagne à jour.
    Écriture Xray : déposée en demande, exécutée après validation de l'automaticien dans l'atelier."""
    from atelier.domain import demandes

    if not scenarios:
        raise ValueError("Donner au moins un scénario.")
    d = demandes.creer("tnr_publier", {"scenarios": [str(s) for s in scenarios]}, f"Publier au TNR : {', '.join(map(str, scenarios[:6]))}"
                       + (f" (+{len(scenarios) - 6})" if len(scenarios) > 6 else ""))
    return demandes.message(d)


@outil
def studio_generer_depuis_bdd(cle: str, ecrire: bool = False, chemin: str = "", remplacer: bool = False) -> dict:
    """Génère la suite Robot d'un scénario BDD en Page Object Model : la suite (tests seulement) et, dans « pages », la
    ressource de chaque écran où ajouter les keywords à implémenter (stubs). ecrire=False :
    aperçu seulement ; « keywords_proches » liste les étapes qui ressemblent à un keyword existant. ecrire=True : écrit
    le fichier (jamais d'écrasement) ; il entre en revue technique « Généré » et ne s'exécute qu'après approbation de
    l'automaticien dans l'atelier. L'écriture est refusée tant qu'une étape proche d'un keyword existant n'est pas
    tranchée dans Test Design (reprendre le keyword, ou confirmer un nouveau keyword) : aucun doublon silencieux.
    remplacer=True : régénère un test déjà écrit (ex. passage en Page Object Model) quand sa suite ne contient que lui ;
    l'ancienne version est sauvegardée (studio/remplaces/). Une suite qui porte d'autres tests n'est jamais remplacée."""
    from atelier.generation import bdd, structure_depot, studio

    m = bdd._exiger(cle)
    g = bdd.generer_robot(m)
    if chemin and chemin.replace("\\", "/") != g["chemin"]:  # chemin imposé : suite à part, jamais un ajout
        g = bdd.generer_robot(m, cible=chemin)
    g["structure"] = structure_depot.controler(g["chemin"], g["contenu"])  # rangé comme le reste du dépôt ?
    if ecrire:  # suite (création, ajout au parcours, ou remplacement explicite si elle ne porte que ce test) + pages
        g = bdd.ecrire_generation(m, g, remplacer, "cursor")
    return g


@outil
def studio_construire_test(nom: str, jdd_nom: str, etapes: list[dict], cle_xray: str = "", tags: list[str] | None = None,
                           ecrire: bool = False) -> dict:
    """Assemble un test Robot depuis les keywords EXISTANTS du socle (INITIALISATION + JDD ajoutés). etapes :
    [{"mot": "Given|When|Then|And", "keyword": "<nom exact>", "arguments": [...]}] et blocs
    {"type": "si", "condition": "..."}, {"type": "sinon"}, {"type": "pour", "variable": "${i}", "liste": "RANGE 3"},
    {"type": "essayer"}, {"type": "echec"}, {"type": "fin"}. ecrire=False : aperçu + lint ; ecrire=True : fichier écrit,
    en revue technique « Généré » (approbation humaine dans l'atelier)."""
    from atelier.generation import studio

    from atelier.generation import structure_depot

    c = studio.construire_test(nom, cle_xray, jdd_nom, etapes, tags or [])
    c["structure"] = structure_depot.controler(c["fichier"], c["contenu"])  # rangé comme le reste du dépôt ?
    if ecrire:
        c["ecrit"] = studio.ecrire_test(c, "cursor")
    return c


@outil
def studio_executer_etape(keyword: str, jdd_nom: str, plateforme: str = "web", env: str = "", arguments: list[str] | None = None) -> dict:
    """Exécute un seul keyword du socle (INITIALISATION + jeu de données, puis ce keyword) dans une suite temporaire
    hors dépôt (results/builder/). Pour mettre au point une étape avant d'écrire le test complet."""
    from atelier.generation import studio_avance

    e = studio_avance.preparer_etape(keyword, jdd_nom, arguments or [])
    out = e["cible"].rsplit("/", 1)[0]
    r = robot.run_robot(e["cible"], variables={"PLATFORM": plateforme}, output_dir=out, xray_mode="aucun", jdd_env=env)
    return {"cible": e["cible"], "resultat": r}


@outil
def run_tests(tests: list[str], dry_run: bool = False, jdd_env: str = "", output_dir: str = "",
              derogation: str = "", jdd_variantes: dict | None = None) -> dict:
    """Exécute des tests PRÉCIS (pas toute la suite) : tests = identifiants « <fichier>::<nom du test> » (une ou plusieurs
    suites ; un fichier seul = toute la suite). Sert à reproduire puis vérifier une maintenance : un run réel est la
    vérification qui précède la validation ; un dry run ne lance aucun keyword, il ne vérifie aucune assertion.
    Un test tagué consomme_donnee (donnée réelle créée à chaque run) n'est exécuté que si sa suite est validée, ou avec
    une dérogation justifiée de l'automaticien. jdd_env vide : l'environnement des jeux de données est déduit.
    output_dir vide : un dossier par run (results/tests/<date>) : la preuve d'un run n'est pas écrasée par le suivant.
    jdd_variantes : profil de données choisi pour un jeu, ex. {"LOGIN_DEMO": "LOGIN_DEMO_PLUS18"} (jeux
    déclarés « variante_de » dans le JDD) : les tests reçoivent les valeurs du profil sans modifier leur code."""
    from atelier.execution import centre

    from datetime import datetime

    sel = robot.selection_tests(tests)
    output_dir = output_dir or f"results/tests/{datetime.now():%Y%m%d-%H%M%S-%f}"
    revue = centre.controle_revue(sel["cible"], dry_run, derogation, tests)
    r = robot.run_robot(sel["cible"], dry_run=dry_run, output_dir=output_dir, xray_mode="aucun", jdd_env=jdd_env, tests=tests,
                        events_url=WEB_EVENTS_URL, jdd_variantes=jdd_variantes)  # suivi en direct dans l'atelier (graphe du run, exécution)
    return {**r, "tests": tests, "revue": revue}


@outil
def studio_revue(fichier: str = "") -> dict:
    """État de la revue technique des scripts. Sans fichier : liste (statut, dernière décision et commentaire).
    Avec fichier : statut, contrôles automatiques (clé Xray, conventions, secrets, assertions, réutilisation, locators,
    données) et historique — à lire pour corriger un script en « Modifications demandées »."""
    from atelier.generation import studio

    if fichier:
        return studio.revue_script(fichier)
    return {f: {"statut": r["statut"], "derniere_decision": (r.get("historique") or [{}])[-1]} for f, r in studio.revues_scripts().items()}


@outil
def studio_soumettre_revue(fichier: str, commentaire: str = "") -> dict:
    """Soumet un script à la revue technique de l'automaticien (Généré / Modifications demandées / Refusé → Revue
    technique). L'agent ne peut ni approuver, ni refuser, ni publier : ces décisions restent humaines, dans l'atelier."""
    from atelier.generation import studio

    r = studio.transition_script(fichier, "soumettre", commentaire or f"soumis par {_agent().libelle()}")
    return {"fichier": fichier, "statut": r["statut"], "controles": r["controles"]}


@outil
def studio_corrections_locators() -> list[dict]:
    """Locators à fiabiliser (fragiles, obsolètes, ou dont un secours a servi dans les derniers runs) avec la valeur
    proposée et sa source. Appliquer avec studio_corriger_locator (les suites concernées repassent en revue)."""
    from atelier.generation import studio_avance

    return studio_avance.propositions_correction()


@outil
def studio_corriger_locator(locator_id: str, valeur: str) -> dict:
    """Applique une correction de locator (ex. valeur proposée par studio_corrections_locators) dans son fichier
    .resource, avec historique de l'éditeur. Toutes les suites qui utilisent ce locator repassent en revue
    technique : l'automaticien valide dans l'atelier. locator_id : « écran.clé@plateforme »."""
    from atelier.generation import studio_avance

    return studio_avance.appliquer_correction(locator_id, valeur, origine="cursor")


@outil
def studio_factorisation_keywords() -> list[dict]:
    """Groupes de keywords en double (corps identique, ou même nom dans plusieurs fichiers) avec le keyword à garder
    et ceux à remplacer. Seuls les groupes « applicable » peuvent être factorisés automatiquement."""
    from atelier.generation import studio_avance

    return studio_avance.propositions_factorisation()


@outil
def studio_factoriser_keywords(groupe_id: str) -> dict:
    """Factorise un groupe de keywords au corps identique (id renvoyé par studio_factorisation_keywords) : appels
    renommés vers le keyword gardé, définitions en double retirées, imports vérifiés, historique de l'éditeur. Les
    suites concernées repassent en revue technique : l'automaticien valide dans l'atelier."""
    from atelier.generation import studio_avance

    return studio_avance.appliquer_factorisation(groupe_id, origine="cursor")


# =========================================================================== cerveau de l'application
@outil
def cerveau_application(module: str = "") -> dict:
    """Ce que l'atelier sait de l'application active, à lire AVANT de construire ou d'explorer : sans module, vue
    d'ensemble (sources et leur fraîcheur, modules avec écrans / exigences / couverture / automatisation / échecs,
    lacunes et prochaines actions) ; avec module, le détail du module (écrans, parcours, règles, exigences et tests,
    non couvert, à automatiser, pistes)."""
    from atelier.intelligence import cerveau, plan_test

    if module:
        return plan_test.plan(module)
    v = cerveau.vue()
    return {k: v[k] for k in ("application", "maturite", "sources", "modules", "lacunes")}


@outil
def cerveau_question(question: str) -> dict:
    """Pose une question au cerveau de l'application (ex. « quels écrans du module Virements n'ont pas de test ? »).
    Réponse fondée uniquement sur ses connaissances (graphe, carte, Jira / Xray, dépôt, exécutions), éléments cités."""
    from atelier.intelligence import cerveau

    return cerveau.demander(question)


# =========================================================================== Coverage Intelligence
@outil
def coverage_intelligence(vue: str = "overview") -> dict | list:
    """Coverage Intelligence de l'application active. vue : « overview » (4 dimensions : documentaire, traçabilité,
    exécution, automatisation), « documentation » (anomalies Jira), « reconstruction » (fonctionnalités observées et si
    une exigence les documente), « liens » (rapprochements exigence ↔ test proposés), « manquants » (exigences sans test),
    « orphelins » (tests sans exigence et candidats). Lecture seule."""
    from atelier.intelligence import intelligence_couverture as ci

    fn = {"overview": ci.vue, "documentation": ci.qualite_documentaire, "reconstruction": ci.capacites,
          "liens": lambda: ci.propositions("lien_test"), "manquants": ci.tests_manquants, "orphelins": ci.orphelins}.get(vue)
    if not fn:
        raise ValueError("vue : overview, documentation, reconstruction, liens, manquants ou orphelins.")
    return fn()


@outil
def coverage_proposer_story(capacite: str, je_souhaite: str, afin_de: str, criteres: list[dict], titre: str = "",
                            en_tant_que: str = "utilisateur de l'application", epic: str = "") -> dict:
    """Dépose une proposition de User Story reconstruite (id de fonctionnalité donné par coverage_intelligence("reconstruction")).
    criteres : [{"texte": "...", "origine": "observe|deduit|ia|a_confirmer"}] ; n'invente pas de règle métier : ce qui
    n'est pas observé est « a_confirmer ». L'automaticien valide ; la création Jira reste humaine."""
    from atelier.intelligence import intelligence_couverture as ci

    p = ci.proposer_story(capacite)
    crit = [{"texte": str(c.get("texte", ""))[:300], "origine": c.get("origine") if c.get("origine") in ci.ORIGINES_CRITERE else "a_confirmer",
             "ref": str(c.get("ref", ""))} for c in criteres or [] if c.get("texte")]
    l = ci._charger()
    x = next(y for y in l if y["id"] == p["id"])
    x["contenu"].update({k: v for k, v in (("titre", titre), ("en_tant_que", en_tant_que), ("je_souhaite", je_souhaite), ("afin_de", afin_de), ("epic", epic)) if v})
    x["contenu"]["criteres"] = crit or x["contenu"]["criteres"]
    x["source"] = "cursor"
    x["historique"].append({"date": ci._maintenant(), "auteur": "cursor", "action": "modifiee", "detail": "proposition de Cursor"})
    ci._sauver(l)
    return x


@outil
def coverage_proposer_lien(exigence: str, test: str, score: int, justification: list[str]) -> dict:
    """Dépose une proposition de lien exigence ↔ test Xray (score 0-100, raisons). Jamais créé dans Jira / Xray sans
    validation humaine puis synchronisation explicite dans l'atelier."""
    from atelier.intelligence import intelligence_couverture as ci

    d = ci._donnees()
    if exigence not in d["exigences"] or test not in d["tests"]:
        raise ValueError("Exigence (périmètre importé) ou test (tests de l'application) inconnu.")
    l = ci._charger()
    p = ci._ajouter(l, "lien_test", "cursor", exigence, test, max(0, min(100, int(score))), [str(j)[:300] for j in justification or []][:8],
                    {"exigence": exigence, "exigence_resume": d["exigences"][exigence].get("resume", ""), "test": test,
                     "test_resume": d["tests"][test].get("resume", ""), "decision": "à valider" if score >= 70 else "analyse nécessaire"},
                    cle_unique=f"lien:{exigence}:{test}")
    ci._sauver(l)
    return p



# =========================================================================== jugements délégués à Cursor (comprendre le texte)
# Les règles présélectionnent par ressemblance des mots ; Cursor juge le sens, avec justification ; le serveur contrôle et
# renvoie les refus motivés ; l'automaticien décide dans l'atelier (voir atelier/intelligence/jugement_ia.py).
@outil
def test_design_doublons_a_juger(cle: str) -> dict:
    """Doublons : chaque cas non publié d'une US de Test Design (texte masqué) avec les tests Xray et autres cas de l'US
    présélectionnés par les mots, la consigne et les verdicts possibles. Lire avant test_design_juger_doublons. Lecture seule."""
    from atelier.intelligence import conception_avancee

    return conception_avancee.doublons_pour_agent(cle)


@outil
def test_design_juger_doublons(cle: str, jugements: list[dict]) -> dict:
    """Doublons : dépose ton jugement pour des cas d'une US. jugements : [{"cas": id, "verdict": "reutiliser" (un test
    existant vérifie déjà le même objectif et le même résultat) | "faire_evoluer" (même objectif, test à compléter) |
    "creer", "test": clé Xray ou id d'un autre cas de l'US (obligatoire sauf pour creer), "justification": ce qui est
    identique, ce qui diffère}]. Un résultat opposé n'est jamais un doublon ; en cas de doute, faire_evoluer. Rien n'est
    rejeté ni publié : l'automaticien décide. Renvoie les jugements retenus et refusés (avec la raison)."""
    from atelier.intelligence import conception_avancee

    return conception_avancee.deposer_jugements_doublons(cle, jugements or [], _agent().source())


@outil
def studio_keywords_a_juger(cle: str) -> dict:
    """Keywords en double : chaque étape d'un scénario BDD sans keyword existant (texte masqué), les keywords du dépôt
    présélectionnés par les mots (documentation, corps), le nom de tous les keywords du dépôt (« socle »), la consigne et
    les verdicts possibles. Lire avant studio_juger_keywords. Lecture seule."""
    from atelier.generation import reutilisation

    return reutilisation.keywords_pour_agent(cle)


@outil
def studio_juger_keywords(cle: str, jugements: list[dict]) -> dict:
    """Keywords en double : dépose ton jugement pour des étapes d'un scénario BDD. jugements : [{"etape": id, "verdict":
    "reutiliser" (un keyword existant fait déjà la même action ou la même vérification : synonyme, reformulation) |
    "creer", "keyword": nom exact du keyword existant (obligatoire pour reutiliser), "justification": ce qui est identique,
    ce qui diffère}]. Une action opposée ou un autre résultat n'est jamais le même keyword ; en cas de doute, creer.
    Aucun texte d'étape n'est modifié et aucun keyword n'est créé : l'automaticien reprend le keyword ou confirme le
    nouveau dans Test Design. Renvoie les jugements retenus et refusés (avec la raison)."""
    from atelier.generation import reutilisation

    return reutilisation.deposer_jugements_keywords(cle, jugements or [], _agent().source())


@outil
def xray_redondances_a_juger(module: str = "", limite: int = 30) -> dict:
    """Tests Xray redondants : paires de tests d'un même module présélectionnées par les mots (titres et étapes
    masqués), avec la consigne. Lire avant xray_juger_redondances. Lecture seule."""
    from atelier.intelligence import couverture, patrimoine_xray

    return couverture.redondances_pour_agent((patrimoine_xray.charger_vue() or {}).get("tests") or [], module, limite)


@outil
def xray_juger_redondances(jugements: list[dict]) -> dict:
    """Tests Xray redondants : dépose ton jugement. jugements : [{"tests": [clé, clé], "verdict": "redondants" (même
    objectif, même résultat attendu) | "distincts", "justification"}]. Aucun test n'est modifié ni supprimé :
    l'automaticien décide. Renvoie les jugements retenus et refusés (avec la raison)."""
    from atelier.intelligence import couverture, patrimoine_xray

    return couverture.deposer_jugements_redondances((patrimoine_xray.charger_vue() or {}).get("tests") or [], jugements or [], _agent().source())


@outil
def coverage_liens_a_juger(exigence: str = "", limite: int = 10) -> dict:
    """Traçabilité : exigences (texte et critères masqués) avec les tests Xray candidats présélectionnés par les mots,
    les tests déjà liés et la consigne. Sans exigence : d'abord celles sans test. Lire avant coverage_juger_liens.
    Lecture seule."""
    from atelier.intelligence import intelligence_couverture as ci

    return ci.liens_a_juger(exigence, limite)


@outil
def coverage_juger_liens(jugements: list[dict]) -> dict:
    """Traçabilité : dépose ton jugement exigence ↔ test. jugements : [{"exigence": clé, "test": clé, "verdict": "couvre"
    | "partiel" | "ne_couvre_pas", "criteres_couverts": [...], "justification"}]. couvre / partiel : lien proposé (ou
    avis sur la proposition des règles) ; ne_couvre_pas : avis sur la proposition des règles. Aucun lien n'est créé dans
    Jira / Xray : l'automaticien valide. Renvoie les jugements retenus et refusés (avec la raison)."""
    from atelier.intelligence import intelligence_couverture as ci

    return ci.deposer_jugements_liens(jugements or [], _agent().source())


@outil
def coverage_orphelins_a_classer(limite: int = 20) -> dict:
    """Tests orphelins : tests Xray sans exigence et sans classement en cours (texte masqué), candidats présélectionnés
    par les mots, exigences du périmètre et classes possibles. Lire avant coverage_classer_orphelins. Lecture seule."""
    from atelier.intelligence import intelligence_couverture as ci

    return ci.orphelins_a_classer(limite)


@outil
def coverage_classer_orphelins(classements: list[dict]) -> dict:
    """Tests orphelins : propose un classement. classements : [{"test": clé, "classe": "associer" | "nouvelle_exigence" |
    "technique" | "transversal" | "conserver", "cible": clé de l'exigence (pour associer), "justification"}]. Propositions
    à valider dans l'atelier, jamais appliquées. Renvoie les classements retenus et refusés (avec la raison)."""
    from atelier.intelligence import intelligence_couverture as ci

    return ci.deposer_classements_orphelins(classements or [], _agent().source())


@outil
def discovery_correlations_a_juger(ecran: str = "", limite: int = 15) -> dict:
    """Corrélation écran ↔ exigence : écrans de la carte (éléments observés, libellés masqués), exigences déjà liées,
    candidates présélectionnées par les mots et exigences de la copie locale Jira. Sans écran : d'abord ceux sans
    exigence. Lire avant discovery_juger_correlations. Lecture seule."""
    from atelier.discovery import correlation

    return correlation.correlations_a_juger(ecran, limite)


@outil
def discovery_juger_correlations(jugements: list[dict]) -> dict:
    """Corrélation écran ↔ exigence : dépose ton jugement. jugements : [{"ecran": id ou nom, "exigence": clé, "verdict":
    "concerne" | "ne_concerne_pas" | "incertain", "justification", "preuves": [éléments de l'écran ou phrases de l'exigence
    sur lesquels tu t'appuies] (facultatif), "confiance": "faible" | "moyenne" | "forte" (facultatif, ton estimation)}].
    Le lien « réalisé par » n'entre dans le Knowledge Graph qu'après confirmation de l'automaticien ; une proposition qu'il
    a rejetée est refusée. Renvoie les jugements retenus et refusés (avec la raison)."""
    from atelier.discovery import correlation

    return correlation.deposer_correlations(jugements or [], _agent().source())


@outil
def release_a_interpreter(release: str, build: str = "") -> dict:
    """Releases : tout pour interpréter la Release Note (sans build) ou un build reçu — texte masqué, évolutions tirées
    par les règles, éléments du Knowledge Graph (US, epics, bugs, écrans, modules, parcours), patrimoine de tests Xray
    (module, criticité, exigences, automatisé, dernier statut), anomalies Jira, périmètre des règles, consigne et format
    de dépôt. Lire avant release_deposer_interpretation. Lecture seule."""
    from atelier.intelligence import release_ia

    return release_ia.a_interpreter(release, build)


@outil
def release_deposer_interpretation(release: str, build: str = "", evolutions: list[dict] | None = None,
                                   tests: list[dict] | None = None, synthese: str = "") -> dict:
    """Releases : dépose ton interprétation. evolutions : [{"evolution": id des règles ou vide, "texte": si nouvelle,
    "type", "elements": [ids du Knowledge Graph], "justification"}] ; tests (build seulement) : [{"test": clé, "action":
    "ajouter" | "ecarter", "categorie": "retest" | "ciblee" | "qualification", "justification"}] ; synthese : le risque du
    build en deux ou trois phrases. Contrôlé par le serveur (éléments et tests connus, justification), appliqué comme
    proposition par défaut que le QA valide ; rien n'est écrit dans Jira / Xray. Renvoie les retenus et les refus."""
    from atelier.intelligence import release_ia

    return release_ia.deposer(release, build, evolutions or [], tests or [], synthese or "", _agent().source())


__all__ = [f.__name__ for f in OUTILS]


# =========================================================================== parcours de fonctionnalité (V2, phase 1)
@outil
def parcours_lister() -> list[dict]:
    """Parcours de fonctionnalité du projet (statut, avancement, étape courante). Un parcours suit le cycle de vie
    d'une fonctionnalité : Discovery → reconstruction → couverture → Test Design → validation → génération →
    qualification → exécution → Failure Analysis → synchronisation Xray / Knowledge Graph."""
    from atelier.intelligence import parcours_fonctionnalite as pf

    return pf.lister()


@outil
def parcours_initialiser(fonctionnalite: str, libelle: str = "", jira: list[str] | None = None) -> dict:
    """Crée (ou retrouve, s'il est déjà ouvert) le parcours d'une fonctionnalité. fonctionnalite : nœud du Knowledge
    Graph (« module:Connexion », « fonctionnalite:… ») ou nom du module ; jira : clés des US / exigences liées."""
    from atelier.intelligence import parcours_fonctionnalite as pf

    return pf.creer(fonctionnalite, libelle, jira or [], origine="mcp")


@outil
def parcours_etat(parcours_id: str) -> dict:
    """État complet d'un parcours : étapes (statut, références, validation, à revoir), dépendances bloquantes,
    indices constatés dans les modules, écran de l'atelier et outils MCP utiles pour chaque étape, historique."""
    from atelier.intelligence import parcours_fonctionnalite as pf

    return pf.obtenir(parcours_id)


@outil
def parcours_etape(parcours_id: str, etape: str, action: str, commentaire: str = "",
                   reference_type: str = "", reference_id: str = "", reference_libelle: str = "") -> dict:
    """Agit sur une étape (etape : discovery, reconstruction, couverture, conception, validation, generation,
    qualification, execution, analyse, synchronisation). action : demarrer · referencer (relier un objet produit :
    reference_type ex. session_discovery, exigence, scenario_bdd, suite, run, echec, execution_xray + reference_id) ·
    soumettre · valider · sauter (justification obligatoire) · echouer / bloquer (motif) · revenir (relancer l'étape ;
    les suivantes restent, marquées à revoir). Les étapes « validation », « qualification » et « synchronisation » ne
    se valident que dans l'atelier : depuis ici elles passent en attente de validation."""
    from atelier.intelligence import parcours_fonctionnalite as pf

    ref = {"type": reference_type, "id": reference_id, "libelle": reference_libelle} if reference_id else None
    return pf.agir(parcours_id, etape, action, commentaire, ref, origine="mcp")


@outil
def parcours_reprendre(parcours_id: str, action: str = "reprendre", motif: str = "") -> dict:
    """Suspend, reprend ou abandonne un parcours (action : suspendre · reprendre · abandonner, avec motif). Rien
    n'est perdu : les étapes, références et validations sont conservées."""
    from atelier.intelligence import parcours_fonctionnalite as pf

    return pf.changer_etat(parcours_id, action, motif, origine="mcp")


# =========================================================================== boîte de demandes de l'atelier
# L'automaticien clique dans l'atelier ; l'agent vient chercher la demande ici au lieu d'attendre qu'on la colle dans
# son chat (atelier/integrations/boite_cursor.py). Une demande vaut une demande de l'automaticien dans le chat.
@outil
def atelier_demande_suivante(attente_s: int = 40) -> dict:
    """Boîte de demandes de l'atelier : renvoie la prochaine demande déposée par l'automaticien (id, titre, texte), ou
    attend jusqu'à attente_s secondes (40 au plus) qu'il en dépose une. À appeler en boucle quand il te dit « traite les
    demandes de l'atelier » : exécuter le texte reçu comme une demande tapée dans le chat, puis atelier_demande_terminee,
    puis rappeler cet outil. Sans demande (« demande » vide) : rappeler l'outil, ne pas s'arrêter."""
    from atelier.integrations import boite_cursor

    return boite_cursor.suivante(attente_s)


@outil
def atelier_demande_terminee(id: str, resume: str = "", echec: bool = False) -> dict:
    """Rend compte d'une demande prise dans la boîte de l'atelier : resume = une ou deux phrases pour l'automaticien (ce
    qui a été fait, ce qui reste à décider) ; echec=True si la demande n'a pas pu être menée, avec la raison. Aucun
    secret ni donnée personnelle dans le résumé. Ensuite : atelier_demande_suivante()."""
    from atelier.integrations import boite_cursor

    return boite_cursor.terminer(id, resume, echec)


# =========================================================================== règles Cursor (V2, phase 2)
@outil
def cursor_regles(regle: str = "") -> list[dict]:
    """Instructions actives de ce projet (règles Cursor versionnées dans l'atelier) : sans argument, la liste
    (id, fichier, rôle, portée, version) ; avec regle (global, project-context, security, mcp-usage, discovery,
    test-design, automation, execution, failure-analysis, coverage, knowledge-graph), son contenu complet."""
    from atelier.integrations import regles_cursor

    l = regles_cursor.actives()
    if regle:
        return [x for x in l if x["id"] == regle] or [{"erreur": f"Règle inconnue : {regle}"}]
    return [{k: v for k, v in x.items() if k != "contenu"} for x in l]


@outil
def agent_annoncer(intention: str, modele: str = "", etape: str = "", regles: list[str] | None = None) -> dict:
    """Annonce à l'automaticien, en une phrase, ce que tu vas faire (console Cursor de l'atelier). À appeler au début
    de chaque tâche et à chaque changement d'étape. intention : phrase en français (« J'analyse les US de la squad DRE
    pour proposer les cas de test ») ; modele : le modèle qui te fait fonctionner, si tu le connais ; etape : étape du
    parcours ou du travail ; regles : règles .mdc du projet que tu appliques. N'écrit rien : simple annonce."""
    from atelier.domain import evenements

    propre = lambda t, n: " ".join(str(t or "").split())[:n]  # noqa: E731
    ev = {"type": "mcp_annonce", "intention": propre(intention, 400), "modele": propre(modele, 80), "etape": propre(etape, 120),
          "regles": [propre(r, 60) for r in (regles or [])][:6]}
    if not ev["intention"]:
        return {"ok": False, "erreur": "intention vide : une phrase en français est attendue."}
    evenements.publier(ev)
    return {"ok": True, "affiche": "Annonce visible dans la console Cursor de l'atelier."}


# =========================================================================== couverture avancée (V2, phase 3)
@outil
def coverage_ui(module: str = "", detail: bool = False) -> dict:
    """Couverture des parcours et des composants UI, par niveau : découvert → associé (utilisé par un test) →
    automatisé (test tracé dans Xray) → exécuté → réussi. Indicateurs (écrans, composants, parcours, automatisation,
    réussite) avec définition et détail, écrans / composants / parcours sans test. detail=True : liste complète des
    composants et de leurs tests."""
    from atelier.intelligence import couverture_avancee

    r = couverture_avancee.calculer(module=module)
    if not detail:
        r["composants"] = [c for c in r["composants"] if c["niveau"] == "découvert"][:50]
    return r


# =========================================================================== Test Design avancé (V2, phase 4)
@outil
def test_design_proposer(cle: str, categories: list[str] | None = None) -> dict:
    """Propose des cas pour une US de Test Design (À concevoir) par catégorie : nominal, alternatif, negatif,
    limites, champs, erreurs, navigation, permissions, regles (toutes par défaut). Chaque cas porte sa source, sa
    justification, sa confiance, ce qui manque, observé / déduit, et une recommandation de doublon (réutiliser,
    faire évoluer, créer) face aux tests Xray existants. Cas « Proposé » : l'automaticien valide dans l'atelier."""
    from atelier.intelligence import conception_avancee

    r = conception_avancee.proposer(cle, categories, origine="cursor")
    u = r.pop("us")
    r["cas"] = [{k: c.get(k) for k in ("id", "categorie", "titre", "confiance", "provenance", "source_detail", "manquant", "statut")}
                | {"doublon": (c.get("doublon") or {}).get("recommandation"), "proche": ((c.get("doublon") or {}).get("meilleur") or {}).get("cle")}
                for c in u.get("cas") or [] if c.get("categorie")]
    return r


@outil
def test_design_doublons(titre: str, etapes: list[dict] | None = None, gherkin: str = "") -> dict:
    """Avant de proposer un scénario : tests Xray existants les plus proches par RESSEMBLANCE DES MOTS (titre, étapes,
    préconditions, résultats attendus) et recommandation des règles : réutiliser (≥ 0,70), faire évoluer (≥ 0,40) ou
    créer. Présélection seulement, sans compréhension du texte : juger le sens toi-même (résultat opposé = pas un
    doublon) ; pour les cas d'une US, utiliser test_design_doublons_a_juger puis test_design_juger_doublons. etapes :
    [{"action", "donnees", "resultat"}] ; gherkin : texte Given / When / Then."""
    from atelier.intelligence import conception_avancee

    return conception_avancee.doublons(titre, etapes or [], gherkin)


@outil
def test_design_cas_us(cle: str) -> dict:
    """Une US de Test Design (texte et réponses de l'équipe masqués) et ses cas regroupables (id, titre, statut, source,
    étapes, Gherkin, couvre), avec la consigne de regroupement. À lire avant test_design_proposer_regroupements, et
    avant testabilite_deposer_proposition pour une US précise. Lecture seule."""
    from atelier.intelligence import granularite_tests

    return granularite_tests.cas_pour_agent(cle)


@outil
def test_design_proposer_regroupements(cle: str, propositions: list[dict]) -> dict:
    """Granularité : propose de regrouper des cas d'une US (un test = un objectif). propositions : [{"cas": [id, id, ...],
    "mode": "donnees" (même chemin, données différentes : un test à variantes) | "controle" (un détail devient un point
    de contrôle d'un autre cas), "titre", "justification" (obligatoire : pourquoi c'est le même objectif), "couvre":
    [comportements de l'US vérifiés]}]. Ne jamais regrouper des résultats métier différents. Chaque appel REMPLACE tes
    propositions encore en attente pour cette US : envoyer la liste complète. Rien n'est regroupé :
    l'automaticien applique ou écarte chaque proposition dans l'atelier. Renvoie les propositions retenues et refusées."""
    from atelier.intelligence import granularite_tests

    return granularite_tests.deposer_regroupements(cle, propositions or [], _agent().source())


# =========================================================================== Champ et Anomalie (V2, phase 5)
@outil
def knowledge_entites(type: str = "champ", ecran: str = "") -> list[dict]:
    """Entités Champ et Anomalie du Knowledge Graph. type « champ » : champs observés (nom technique, libellé, type,
    format, obligatoire, valeur par défaut, règles de validation, messages d'erreur, fonctionnalité, tests qui le
    vérifient, anomalies) ; ecran pour filtrer. type « anomalie » : bugs Jira et échecs analysés (écran, composant,
    test, exécution, date, statut, source, confiance, statut de validation)."""
    from atelier.discovery import entites

    if type not in ("champ", "anomalie"):
        raise ValueError("type : champ ou anomalie.")
    return entites.champs(ecran) if type == "champ" else entites.anomalies()


@outil
def knowledge_proposer_champ(ecran: str, champ: str, regle: str, description: str = "") -> dict:
    """Propose une règle de validation pour un champ (ex. « montant obligatoire, 2 décimales maximum ») : règle et
    lien « possède » à valider dans l'atelier ; après validation, obligatoire / format / valeur par défaut du champ
    en sont déduits. N'invente rien : uniquement ce qui est observé à l'écran ou lu dans une exigence."""
    from atelier.discovery import entites

    return entites.proposer_regle_champ(ecran, champ, regle, description)


# =========================================================================== Failure Analysis × connaissance (V2, phase 6)
@outil
def failure_connaissance(echec_id: str = "") -> dict:
    """Échecs reliés à la connaissance. Sans echec_id : échecs regroupés par composant (écran.clé), causes historisées,
    régressions (réussi au run précédent, échec maintenant) et régressions récurrentes (≥ 2 sur le même composant).
    Avec echec_id (« RUN-…::id du test ») : écran / composant / champ touchés, autres échecs du même composant,
    anomalies déjà connues sur l'écran, cause dominante, régression ou non. Lecture seule."""
    from atelier.execution import echecs_connaissance as ec

    return ec.connaissance_echec(echec_id) if echec_id else ec.par_composant()
