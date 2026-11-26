"""Publier au TNR : conventions de l'application, découpage un scénario = un test, publication avec étiquette et
dossier, plan TNR créé puis complété, campagne liée, clé reportée sans renvoi en revue."""
import pytest

GHERKIN_DEUX = """# language: fr
Fonctionnalité: Connexion
  Scénario: Se connecter
    Étant donné que je suis sur l'écran de connexion
    Quand je saisis mes identifiants du jeu de données
    Alors le tableau de bord est affiché

  @negatif
  Scénario: Bouton inactif sans identifiants
    Étant donné que je suis sur l'écran de connexion
    Alors le bouton Me connecter est inactif
"""


class FauxXray:
    def __init__(self):
        self.crees, self.plans, self.ajouts, self.n = [], {}, [], 600

    def lire_gherkin(self, cle):
        return None

    def creer_test_cucumber(self, projet, resume, gherkin, libelles=None):
        self.n += 1
        self.crees.append({"cle": f"{projet}-{self.n}", "resume": resume, "libelles": libelles})
        return {"cle": f"{projet}-{self.n}", "issueId": str(self.n)}

    def ranger_test(self, projet, issue_id, dossier):
        self.crees[-1]["dossier"] = dossier

    def test_ids(self, cles):
        return {k: k.split("-")[1] for k in cles}

    def create_plan(self, projet, resume, ids):
        self.plans[f"{projet}-900"] = {"resume": resume, "ids": list(ids)}
        return "900", f"{projet}-900"

    def resolve(self, cle):
        return {"type": "plan", "issueId": "900", "key": cle} if cle in self.plans else {"type": "autre", "key": cle}

    def add_tests_to_plan(self, plan_id, ids):
        self.ajouts.append(list(ids))


@pytest.fixture
def appli(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.domain import projet, projets

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(projets, "cle_xray", lambda: "DEMO")
    carte.creer_app("Banque Démo", ["android"])
    (tmp_path / "data" / "jdd").mkdir(parents=True)
    (tmp_path / "data" / "jdd" / "recette.yaml").write_text("LOGIN:\n  donnees:\n    identifiant: x\n", "utf-8")
    return tmp_path


def test_conventions_par_defaut_et_reglage(appli):
    from atelier.generation import tnr

    c = tnr.conventions()
    assert (c["etiquette"], c["dossier"], c["plan"], c["plateformes"]) == ("banque-demo", "/Banque Démo", "", ["android"])
    c = tnr.regler(etiquette="tnr-s1", dossier="Mobile/Banque Démo")
    assert (c["etiquette"], c["dossier"]) == ("tnr-s1", "/Mobile/Banque Démo")
    from atelier.discovery import carte
    assert carte.config_app()["tests_xray"]["dossiers"] == ["/Mobile/Banque Démo"]   # le rangement Xray suit
    with pytest.raises(ValueError, match="espace"):
        tnr.regler(etiquette="tnr s1")
    with pytest.raises(ValueError, match="Test Plan"):
        tnr.regler(plan="pas une clé")


def test_publier_au_tnr_decoupe_publie_et_inscrit_au_plan(appli):
    from atelier.execution import centre
    from atelier.generation import bdd, conception, tnr

    bdd.creer("CONNEXION", "Connexion")
    bdd.depuis_texte("CONNEXION", GHERKIN_DEUX)
    bdd.associer_module("CONNEXION", "Login")
    x = FauxXray()
    r = tnr.publier(["CONNEXION"], xray=x)
    assert not r["erreurs"], r["erreurs"]
    # un scénario = un test Xray : le négatif est devenu un BDD à part
    assert [p["scenario"] for p in r["publies"]] == ["CONNEXION", "CONNEXION_BOUTON_INACTIF_SANS_IDENTIFIANTS"]
    assert len(bdd.charger("CONNEXION")["scenarios"]) == 1
    assert all(c["libelles"] == ["banque-demo"] and c["dossier"] == "/Banque Démo/Login" for c in x.crees)
    # plan TNR créé une fois, avec les deux tests ; conventions et campagne retenues
    assert r["plan"] == {"plan": "DEMO-900", "cree": True, "ajoutes": ["DEMO-601", "DEMO-602"], "avertissements": []}
    assert x.plans["DEMO-900"]["resume"] == "TNR Banque Démo"
    camp = next(c for c in centre.campagnes() if c["id"] == r["campagne"]["campagne"])
    assert camp["plan_xray"] == "DEMO-900" and camp["tests"] == ["DEMO-601", "DEMO-602"] and camp["environnement"] == "recette"
    assert tnr.conventions()["plan"] == "DEMO-900" and tnr.conventions()["campagne"] == camp["id"]
    assert conception.cle_xray_du_scenario("CONNEXION") == "DEMO-601"

    # lot suivant : le plan existant est complété, la campagne aussi (pas de second plan)
    bdd.creer("SOLDE", "Solde")
    bdd.depuis_texte("SOLDE", "# language: fr\nFonctionnalité: Solde\n  Scénario: Masquer le solde\n    Quand je masque le solde\n")
    r2 = tnr.publier(["SOLDE"], xray=x)
    assert r2["plan"] == {"plan": "DEMO-900", "cree": False, "ajoutes": ["DEMO-603"]} and x.ajouts == [["603"]]
    camp = next(c for c in centre.campagnes() if c["id"] == r["campagne"]["campagne"])
    assert camp["tests"] == ["DEMO-601", "DEMO-602", "DEMO-603"] and len(centre.campagnes()) == 1


def test_un_scenario_en_erreur_n_arrete_pas_les_autres(appli):
    from atelier.generation import bdd, tnr

    bdd.creer("SOLDE", "Solde")
    bdd.depuis_texte("SOLDE", "# language: fr\nFonctionnalité: Solde\n  Scénario: Masquer le solde\n    Quand je masque le solde\n")
    r = tnr.publier(["INCONNU", "SOLDE"], xray=FauxXray())
    assert [e["scenario"] for e in r["erreurs"]] == ["INCONNU"] and [p["scenario"] for p in r["publies"]] == ["SOLDE"]


def test_variantes_un_test_robot_par_jeu_du_tableau_d_exemples(appli):
    """Plan du Scénario avec une colonne « jeu » : un test Robot par ligne, chacun avec son jeu de données."""
    from atelier.generation import bdd

    bdd.creer("RECHARGE", "Recharge")
    bdd.depuis_texte("RECHARGE", """# language: fr
Fonctionnalité: Recharge
  Plan du Scénario: Préparer une recharge
    Quand je choisis le facturier du jeu de données
    Alors la liste des éléments à payer est affichée

    Exemples:
      | jeu                 | facturier          |
      | RECHARGE_A        | Opérateur A      |
      | RECHARGE_B     | Opérateur B        |
""")
    m = bdd.charger("RECHARGE")
    assert bdd.jeux_des_exemples(m["scenarios"][0]) == ["RECHARGE_A", "RECHARGE_B"]
    g = bdd.generer_robot(m)
    c = g["contenu"]
    assert "Préparer une recharge — RECHARGE_A" in c and "Préparer une recharge — RECHARGE_B" in c
    assert c.count("Initialiser Le Test    &{JDD_RECHARGE_A}") == 1 and c.count("&{JDD_RECHARGE_B}") == 1
    assert c.count("When je choisis le facturier du jeu de données") == 2


def test_generation_executable_corps_et_locators(appli):
    """Étapes avec locator : keywords générés avec leur corps (toucher, saisie du jeu, mot de passe sans log,
    vérification), locators dans resources/locators/<page>.resource importé par la page ; sans locator : stub."""
    import yaml

    from atelier.domain import projet as pj
    from atelier.generation import bdd

    bdd.creer("LOGIN", "Connexion")
    bdd.depuis_texte("LOGIN", """# language: fr
Fonctionnalité: Connexion
  Scénario: Se connecter
    Quand je saisis le mot de passe du jeu de données
    Et je touche Me connecter
    Alors le tableau de bord est affiché
    Et une étape sans locator
""")
    f = appli / "bdd" / "login.yaml"
    m = yaml.safe_load(f.read_text("utf-8"))
    locs = ['android=new UiSelector().resourceId("champ_mdp")', 'android=new UiSelector().resourceId("bouton_connect")',
            'android=new UiSelector().resourceId("dashboard_home")', ""]
    for e, loc in zip(m["scenarios"][0]["etapes"], locs):
        e.update(ecran="login", locator=loc)
    m["scenarios"][0]["etapes"][0]["jdd"] = "mot_de_passe"
    m["jdd"] = "LOGIN_TEST"
    f.write_text(yaml.safe_dump(m, allow_unicode=True), "utf-8")
    import os, time
    os.utime(f, (time.time() + 5, time.time() + 5))
    g = bdd.generer_robot(bdd.charger("LOGIN"))
    page = next(p for p in g["pages"] if p["page"] == "login")
    c = page["contenu"]
    assert "Input Password    ${LOGIN_CHAMP_MDP}    ${JDD}[mot_de_passe]" in c
    assert "Click Element    ${LOGIN_BOUTON_CONNECT}" in c and "Wait Until Element Is Visible    ${LOGIN_DASHBOARD_HOME}    15s" in c
    assert "Fail    Keyword à implémenter : une étape sans locator" in c
    assert "Resource    ../../locators/login.resource" in c
    assert page["locators"]["variables"]["LOGIN_BOUTON_CONNECT"] == locs[1]
    bdd.ecrire_generation(bdd.charger("LOGIN"), g)
    assert "${LOGIN_CHAMP_MDP}" in pj.lire_fichier("resources/locators/login.resource")


def test_choisir_ou_creer_le_plan_tnr(appli):
    """Plan TNR : liste des plans (actuel en tête, puis ouverts, du plus récent), choix d'un plan existant (tests du TNR
    ajoutés, campagne mise à jour), ou création d'un nouveau plan."""
    from atelier.execution import centre
    from atelier.generation import bdd, tnr

    class Xray(FauxXray):
        def conteneurs(self, projet, limite=500, seulement=()):
            return {"plans": [{"cle": "DEMO-10", "resume": "Ancien plan", "statut": "Done", "ferme": True, "cree": "2026-01-01", "tests": []},
                              {"cle": "DEMO-20", "resume": "TNR sprint 12", "statut": "Open", "ferme": False, "cree": "2026-11-01", "tests": ["DEMO-1"]},
                              {"cle": "DEMO-30", "resume": "Recette", "statut": "Open", "ferme": False, "cree": "2026-11-20", "tests": []}]}

        def resolve(self, cle):
            return {"type": "plan", "issueId": cle.split("-")[1], "key": cle} if cle.startswith("DEMO-") and int(cle.split("-")[1]) % 10 == 0 \
                else super().resolve(cle)

    x = Xray()
    bdd.creer("SOLDE", "Solde")
    bdd.depuis_texte("SOLDE", "# language: fr\nFonctionnalité: Solde\n  Scénario: Masquer le solde\n    Quand je masque le solde\n")
    tnr.publier(["SOLDE"], xray=x)                                  # plan DEMO-900 créé, campagne créée
    p = tnr.plans_disponibles(xray=x)
    assert [q["cle"] for q in p["plans"]] == ["DEMO-30", "DEMO-20", "DEMO-10"]   # DEMO-900 absent de la liste factice
    assert [q["cle"] for q in tnr.plans_disponibles("sprint", xray=x)["plans"]] == ["DEMO-20"]

    r = tnr.choisir_plan("demo-20", xray=x)
    assert r["plan"] == "DEMO-20" and r["ajoutes"] == ["DEMO-601"] and x.ajouts[-1] == ["601"]
    camp = next(c for c in centre.campagnes() if c["id"] == tnr.conventions()["campagne"])
    assert camp["plan_xray"] == "DEMO-20" and len(centre.campagnes()) == 1
    assert tnr.plans_disponibles(xray=x)["plans"][0] == {**tnr.plans_disponibles(xray=x)["plans"][0], "cle": "DEMO-20", "actuel": True}

    r = tnr.creer_plan("TNR release 3", xray=x)
    assert r["cree"] and r["plan"] == "DEMO-900" and x.plans["DEMO-900"]["resume"] == "TNR release 3"
    assert next(c for c in centre.campagnes() if c["id"] == tnr.conventions()["campagne"])["plan_xray"] == "DEMO-900"


def test_champs_jira_au_format_de_l_api_et_campagne_avec_transitions(appli):
    """Valeurs des champs Jira selon leur type ; conventions réglées (champs plan / exécution, transitions) ; la
    campagne transmet transitions et champs au run quand elle les porte."""
    from atelier.execution import centre
    from atelier.generation import tnr

    c = {"cf_type": {"valeur": "TNR", "type": "option"}, "cf_env": {"valeur": "Recette", "type": "array", "items": "option"},
         "cf_build": {"valeur": "2.1", "type": "string"}, "fixVersions": {"valeur": "2.1", "type": "array", "items": "version"},
         "cf_vide": {"valeur": "", "type": "option"}}
    assert tnr.payload_champs(c) == {"cf_type": {"value": "TNR"}, "cf_env": [{"value": "Recette"}], "cf_build": "2.1",
                                     "fixVersions": [{"name": "2.1"}]}
    conv = tnr.regler(champs_plan={"cf_type": c["cf_type"], "cf_vide": c["cf_vide"]}, champs_execution={"cf_build": c["cf_build"]},
                      transition_debut="En cours d'exécution", transition_fin="Terminé")
    assert list(conv["champs_plan"]) == ["cf_type"] and conv["transition_fin"] == "Terminé"
    p = centre.params_campagne({"cible": "tests", "tests": ["DEMO-1"], "tags": [], "retry": False, "jira_transition_start": "Démarrer",
                                "jira_champs_execution": {"cf_build": "2.1"}}, "android")
    assert p["jira_transition_start"] == "Démarrer" and p["jira_champs_execution"] == {"cf_build": "2.1"}
