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
def check_locator(locator: str) -> dict:
    """Vérifie un locator : nombre d'éléments trouvés + texte/visibilité du premier."""
    return session.check_locator(locator)


@outil
def tap(locator: str, timeout: float = 10) -> str:
    """Touche / clique un élément. Mobile : locator AppiumLibrary (id=..., accessibility_id=...,
    xpath=...). Web : sélecteur Browser library (data-testid=..., id=..., css=..., text="...")."""
    from atelier.discovery import apprentissage

    return apprentissage.action_mcp("tap", locator, lambda: actions.tap(locator, timeout))


@outil
def type_text(locator: str, text: str, clear: bool = True, hide_keyboard: bool = True) -> str:
    """Saisit du texte dans un champ (mobile ou web)."""
    from atelier.discovery import apprentissage

    return apprentissage.action_mcp("type_text", locator, lambda: actions.type_text(locator, text, clear, hide_keyboard))


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

    r = testabilite_us.deposer_proposition(cle, constats or [], cas or [], "Cursor (MCP)")
    return {"cle": cle, "statut": r["statut"], "constats": len(r["constats"]), "cas": len(r["cas"])}


@outil
def discovery_demarrer(environnement: str = "", mode: str = "assistee", perimetre: str = "") -> dict:
    """Démarre une session Discovery sur l'application de la carte et la plateforme de la session ouverte
    (start_session d'abord). Pendant la session, tap et type_text sont classés (Safe / Controlled / Sensitive /
    Forbidden) : les actions interdites et sensibles sont refusées, la saisie dépend de l'environnement."""
    from atelier.discovery import session, sessions_discovery

    s = sessions_discovery.creer({"plateforme": session.plateforme() or "", "environnement": environnement, "mode": mode,
                                  "perimetre": perimetre, "device": "agent MCP"})
    return {k: v for k, v in sessions_discovery.demarrer(s["id"]).items() if k in ("id", "statut", "config")}


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

    return apprentissage.proposer(nature, libelle, ecran, description, module, exigence, "cursor")


@outil
def discovery_parcours_vers_bdd(ecrans: list | None = None, parcours: str = "", titre: str = "") -> dict:
    """Crée dans Test Design un brouillon de scénario BDD depuis la carte : soit une suite ordonnée d'écrans
    (identifiants ou noms), soit un parcours du Knowledge Graph (ex. « parcours:virement_interne »). Étapes reliées
    aux écrans et locators connus, données par le jeu de données, actions sensibles signalées. À relire et valider
    dans l'atelier avant l'automatisation."""
    from atelier.generation import parcours_bdd

    r = parcours_bdd.brouillon(ecrans=ecrans or None, parcours=parcours, titre=titre)
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
    jeux de données de l'environnement et conventions du projet. module : filtre sur l'écran ou la catégorie."""
    from atelier.generation import studio

    f = (module or "").lower()
    kws = [{k: x[k] for k in ("nom", "documentation", "fichier", "categorie", "utilisations", "doublon", "wrapper_1_1", "plateformes")}
           for x in studio.keywords() if not f or f in x["categorie"].lower() or f in x["nom"].lower()]
    locs = [{k: x[k] for k in ("ecran", "cle", "plateforme", "valeur", "etat", "fichier")} for x in studio.locators() if not f or f in x["ecran"]]
    envs = jdd.environnements()
    e = env or (envs[0] if envs else "")
    return {"keywords": kws, "locators": locs, "environnement": e, "jeux": jdd.lister(e) if e else [],
            "conventions": ["Gherkin français + Page Object Model : locators / keywords / scénarios séparés",
                            "INITIALISATION : Initialiser Le Test    &{JDD_<NOM>} ; aucune donnée littérale dans le scénario",
                            "réutiliser les keywords du socle ; jamais de wrapper 1:1 par élément",
                            "tags : clé Xray + tags fonctionnels (smoke, e2e, negatif, consomme_donnee)",
                            "tout script écrit entre en revue technique : l'automaticien l'approuve dans l'atelier"]}


@outil
def studio_scenario_bdd(cle: str) -> dict:
    """Scénario BDD d'un test Xray (Test Design) et son mapping vers le socle : pour chaque étape, keyword existant ou
    à créer, locators et leur état, données ${DONNEES.x}, assertion. Point de départ pour écrire le test Robot."""
    from atelier.generation import bdd, studio

    m = bdd._exiger(cle)
    return {"cle": cle, "titre": m.get("titre", ""), "gherkin": bdd.serialiser(m), "controles": bdd.controles(m),
            "mapping": studio.mapping_bdd(cle)}


@outil
def studio_generer_depuis_bdd(cle: str, ecrire: bool = False, chemin: str = "") -> dict:
    """Génère la suite Robot d'un scénario BDD (keywords du socle, stubs pour les étapes à créer). ecrire=False :
    aperçu seulement. ecrire=True : écrit le fichier (jamais d'écrasement) ; il entre en revue technique « Généré »
    et ne s'exécute qu'après approbation de l'automaticien dans l'atelier."""
    from atelier.generation import bdd, studio

    g = bdd.generer_robot(bdd._exiger(cle))
    if ecrire:
        cible = chemin or g["chemin"]
        projet.ecrire_fichier(cible, g["contenu"], False)
        studio.entrer_en_revue(cible, "cursor")
        g["ecrit"] = cible
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

    c = studio.construire_test(nom, cle_xray, jdd_nom, etapes, tags or [])
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

    r = studio.transition_script(fichier, "soumettre", commentaire or "soumis par Cursor")
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
