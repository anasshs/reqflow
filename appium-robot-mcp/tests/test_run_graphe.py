"""Graphe du run en direct : les actions d'un run projetées sur les écrans (en cours, réussi, échec, à venir), action
lisible (saisie, assertion…), chemin parcouru ; l'initialisation du test ne situe aucun écran."""
import pytest


@pytest.fixture
def run(monkeypatch):
    from atelier.execution import direct, run_graphe

    direct.reinitialiser()
    statique = {"ecrans": {"ecran:login": {"id": "ecran:login", "nom": "login", "module": "Login", "etat": "couvert", "tests_xray": ["DEMO-1"]},
                           "ecran:oubli": {"id": "ecran:oubli", "nom": "identifiant oublié", "module": "Login", "etat": "couvert", "tests_xray": ["DEMO-1"]},
                           "ecran:profil": {"id": "ecran:profil", "nom": "profil", "module": "Menu", "etat": "couvert", "tests_xray": ["DEMO-2"]},
                           "ecran:accueil": {"id": "ecran:accueil", "nom": "accueil", "module": "", "etat": "couvert", "tests_xray": []}},
                "prevus": {"Oubli": ["ecran:login", "ecran:oubli"], "Profil": ["ecran:profil"]}, "cles": {"Oubli": "DEMO-1", "Profil": "DEMO-2"},
                "par_variable": {"lien_oubli": {"ecran:login"}, "oubli_telephone": {"ecran:oubli"}},
                "par_keyword": {"attendrelepremierecran": {"ecran:accueil"}}, "transitions": set()}
    monkeypatch.setattr(run_graphe, "_statique", lambda run_id: statique)
    direct.demarrer("RUN-1", "tests")
    yield direct, run_graphe
    direct.reinitialiser()


def _ev(direct, *evs):
    for t, e in evs:
        direct.observer({"type": t, **e})


def test_run_projete_sur_les_ecrans(run):
    direct, rg = run
    _ev(direct, ("run_debut", {"tests": [{"nom": "Oubli"}, {"nom": "Profil"}]}), ("test_debut", {"nom": "Oubli"}),
        ("kw_debut", {"nom": "common.Initialiser Le Test", "niveau": 1}),
        ("kw_debut", {"nom": "common.Attendre Le Premier Ecran", "niveau": 2}),          # socle : ne situe aucun écran
        ("kw_debut", {"nom": "pages.je touche Identifiant oublié", "niveau": 1}),
        ("kw_debut", {"nom": "common.Toucher", "niveau": 2, "args": ["${LIEN_OUBLI}"]}),
        ("kw_debut", {"nom": "pages.je saisis le numéro de téléphone", "niveau": 1}),
        ("kw_debut", {"nom": "AppiumLibrary.Input Text", "niveau": 2, "args": ["${OUBLI_TELEPHONE}", "${JDD}[telephone]"]}),
        ("kw_debut", {"nom": "pages.le bouton Valider est actif", "niveau": 1}),
        ("kw_debut", {"nom": "AppiumLibrary.Expect Element", "niveau": 2, "args": ["${BOUTON_VALIDER}", "enabled"]}))
    v = rg.vue()
    etats = {e["id"]: e["etat"] for e in v["ecrans"]}
    assert etats == {"ecran:login": "visite", "ecran:oubli": "en_cours", "ecran:profil": "a_venir"}   # accueil jamais situé
    assert v["liens"] == [{"de": "ecran:login", "vers": "ecran:oubli", "test": "Oubli"}]
    assert v["courant"]["ecran"] == "ecran:oubli" and v["courant"]["action_courante"]["action"] == "assertion"
    assert [x["action"] for x in v["pas"]] == ["ouverture", "toucher", "saisie", "assertion"]
    assert v["pas"][2]["libelle"] == "Saisie · je saisis le numéro de téléphone"
    assert next(t for t in v["tests"] if t["nom"] == "Oubli")["cle_xray"] == "DEMO-1"

    _ev(direct, ("test_fin", {"nom": "Oubli", "statut": "PASS"}), ("test_debut", {"nom": "Profil"}))
    etats = {e["id"]: e["etat"] for e in rg.vue()["ecrans"]}
    assert etats["ecran:oubli"] == "reussi" and etats["ecran:login"] == "reussi" and etats["ecran:profil"] == "a_venir"


def test_echec_et_run_termine(run):
    direct, rg = run
    _ev(direct, ("run_debut", {"tests": [{"nom": "Oubli"}]}), ("test_debut", {"nom": "Oubli"}),
        ("kw_debut", {"nom": "common.Toucher", "niveau": 2, "args": ["${LIEN_OUBLI}"]}),
        ("kw_fin", {"nom": "Toucher", "statut": "FAIL", "niveau": 2}),
        ("test_fin", {"nom": "Oubli", "statut": "FAIL", "message": "élément absent"}), ("run_bilan", {"bilan": {"resultat": {}}}))
    v = rg.vue()  # le dernier run suivi reste affiché
    assert v["run"]["statut"] == "terminé" and v["courant"] is None
    assert {e["id"]: e["etat"] for e in v["ecrans"]}["ecran:login"] == "echec" and v["pas"][-1]["statut"] == "FAIL"


def test_actions_lisibles():
    from atelier.execution.run_graphe import action

    assert [action(n)[0] for n in ("AppiumLibrary.Input Password", "AppiumLibrary.Click Element", "BuiltIn.Should Be Equal",
                                   "common.Vérifier Que L'Élément Est Affiché", "AppiumLibrary.Swipe", "AppiumLibrary.Go Back",
                                   "AppiumLibrary.Open Application", "BuiltIn.Log")] == \
        ["saisie", "toucher", "assertion", "verification", "defilement", "retour", "ouverture", "etape"]


def test_sonde_qui_echoue_ne_visite_pas_l_ecran(run):
    """« Suis-je déjà connecté ? » : une vérification qui échoue alors que le test continue n'est pas une visite."""
    direct, rg = run
    _ev(direct, ("run_debut", {"tests": [{"nom": "Oubli"}]}), ("test_debut", {"nom": "Oubli"}),
        ("kw_debut", {"nom": "pages.je suis connecté", "niveau": 1}),
        ("kw_debut", {"nom": "AppiumLibrary.Expect Element", "niveau": 2, "args": ["${OUBLI_TELEPHONE}", "visible"]}),
        ("kw_fin", {"nom": "Expect Element", "statut": "FAIL", "niveau": 2}),
        ("kw_debut", {"nom": "common.Toucher", "niveau": 2, "args": ["${LIEN_OUBLI}"]}))
    v = rg.vue()
    assert [c["ecran"] for c in v["chemin"]] == ["ecran:login"]
    assert v["pas"][0]["action"] == "sonde" and v["pas"][0]["statut"] == ""


def test_run_de_l_agent_hors_file_suivi_en_direct(run):
    """Un run lancé par l'agent (MCP run_tests) n'a ni run_lance ni run_bilan : son run_debut démarre le suivi, son run_fin
    le termine."""
    direct, rg = run
    direct.reinitialiser()
    _ev(direct, ("run_debut", {"suite": "Login", "tests": [{"nom": "Oubli"}]}), ("test_debut", {"nom": "Oubli"}),
        ("kw_debut", {"nom": "common.Toucher", "niveau": 2, "args": ["${LIEN_OUBLI}"]}))
    v = rg.vue()
    assert v["run"]["id"].startswith("AGENT-") and v["run"]["statut"] == "en cours" and v["courant"]["ecran"] == "ecran:login"
    _ev(direct, ("test_fin", {"nom": "Oubli", "statut": "PASS"}), ("run_fin", {"statut": "PASS", "stats": {"passes": 1, "echecs": 0}}))
    v = rg.vue()
    assert v["run"]["statut"] == "terminé" and {e["id"]: e["etat"] for e in v["ecrans"]}["ecran:login"] == "reussi"
