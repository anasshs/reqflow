"""Page Object Model imposé à la génération : suite = tests seulement ; une page par écran ; ajout sans réécriture."""


def test_page_creee_puis_completee_sans_reecriture(projet):
    from atelier.domain import projet as pj
    from atelier.generation import pom

    inv = {"fichiers": {}}
    k = [{"nom": "je touche connexion", "doc": "À implémenter.", "ecran": "", "args": []}]
    p = pom.preparer(k, inv, "tests/app/auth/connexion.robot", page_defaut="authentification")["pages"][0]
    assert p["chemin"] == "resources/pages/application/authentification.resource" and p["nouveau"]
    assert "*** Keywords ***" in p["contenu"] and "Page Object Model" in p["contenu"]
    assert pom.ecrire([p]) == [p["chemin"]]
    avant = pj.lire_fichier(p["chemin"]) + "\nMon Keyword Écrit À La Main\n    Log    gardé\n"
    pj.ecrire_fichier(p["chemin"], avant, True)
    k2 = k + [{"nom": "l'écran accueil est affiché", "doc": "À implémenter.", "ecran": "", "args": []}]
    p2 = pom.preparer(k2, inv, "tests/app/auth/connexion.robot", page_defaut="authentification")["pages"][0]
    assert p2["keywords"] == ["l'écran accueil est affiché"] and not p2["nouveau"]
    assert p2["contenu"].startswith(avant.rstrip())          # rien de l'existant n'est réécrit
    pom.ecrire([p2])
    assert "Mon Keyword Écrit À La Main" in pj.lire_fichier(p["chemin"])


def test_racine_des_pages_du_depot():
    from atelier.generation import pom

    inv = {"fichiers": {"socle/page_objects/accueil.resource": {"keywords": ["x"]}, "tests/a.robot": {"tests": ["t"]}}}
    assert pom.racine_pages(inv) == "socle/page_objects"
    assert pom.racine_pages({"fichiers": {}}) == "resources/pages"


def test_revue_signale_une_suite_hors_pom(projet):
    from atelier.generation import studio

    (projet / "tests").mkdir()
    (projet / "tests" / "suite.robot").write_text(
        "*** Test Cases ***\nT\n    Click    id=valider\n    Mon Etape\n\n*** Keywords ***\nMon Etape\n    Log    x\n", "utf-8")
    c = {x["code"]: x for x in studio.controles_script("tests/suite.robot")}
    assert c["pom"]["gravite"] == "moyenne" and "Mon Etape" in c["pom"]["message"] and "id=valider" in c["pom"]["message"]
    (projet / "tests" / "propre.robot").write_text("*** Test Cases ***\nT\n    Mon Etape Ailleurs\n", "utf-8")
    assert {x["code"]: x for x in studio.controles_script("tests/propre.robot")}["pom"]["gravite"] == "ok"


def test_style_professionnel():
    from atelier.generation import studio

    brut = "*** Test Cases ***\nT\n    Sleep    2s\n    Valider\n\n*** Keywords ***\nValider\n    Log    x\n"
    s = studio.style_robot("tests/t.robot", brut)
    assert [x["gravite"] for x in s] == ["moyenne", "basse", "basse"] and "Sleep" in s[0]["message"] and "Valider" in s[1]["message"]
    propre = ("*** Settings ***\nTest Teardown    Terminer Le Test\n\n*** Test Cases ***\nT\n    Valider\n\n"
              "*** Keywords ***\nValider\n    [Documentation]    Valide.\n    Log    x\n")
    assert studio.style_robot("tests/t.robot", propre) == []


def test_regenerer_un_test_deja_ecrit(projet, monkeypatch):
    """Suite qui ne porte que ce test : remplacement explicite seulement, ancienne version sauvegardée ; jamais si
    d'autres tests y vivent."""
    import pytest

    from atelier.domain import projet as pj
    from atelier.generation import bdd

    for v in ("XRAY_CLIENT_ID", "JIRA_BASE_URL"):
        monkeypatch.delenv(v, raising=False)
    m = bdd.creer("authentification", "Authentification")
    m = bdd.ajouter_etape("authentification", m["scenarios"][0]["id"], "Alors", "le formulaire de connexion est affiché")
    g = bdd.generer_robot(bdd.charger("authentification"))
    pj.ecrire_fichier(g["chemin"], "*** Test Cases ***\nAuthentification\n    [Tags]    authentification\n    Log    ancien\n")
    with pytest.raises(FileExistsError, match="remplacer=True"):
        bdd.ecrire_generation(bdd.charger("authentification"), g)
    r = bdd.ecrire_generation(bdd.charger("authentification"), g, remplacer=True)
    assert r["ecrit"] == g["chemin"] and r["sauvegarde"].startswith("studio/remplaces/")
    assert "Log    ancien" in pj.lire_fichier(r["sauvegarde"]) and "*** Keywords ***" not in pj.lire_fichier(g["chemin"])
    pj.ecrire_fichier(g["chemin"], "*** Test Cases ***\nAutre Test\n    [Tags]    autre\n    Log    x\n", True)
    with pytest.raises(FileExistsError, match="contient d'autres tests"):
        bdd.ecrire_generation(bdd.charger("authentification"), g, remplacer=True)


def test_donnees_sans_jeu_de_donnees_bloque(projet, monkeypatch):
    """Étape qui consomme une donnée sans jeu de données associé : contrôle bloquant, écriture refusée, prochaine action."""
    import pytest

    from atelier.generation import bdd
    from atelier.intelligence import chemin

    for v in ("XRAY_CLIENT_ID", "JIRA_BASE_URL"):
        monkeypatch.delenv(v, raising=False)
    m = bdd.creer("login_failed", "Login Failed")
    bdd.ajouter_etape("login_failed", m["scenarios"][0]["id"], "Quand", "je me connecte avec le jeu de données")
    m = bdd.charger("login_failed")
    assert any(c["code"] == "jdd_requis" and c["gravite"] == "haute" for c in bdd.controles(m))
    with pytest.raises(ValueError, match="Variable '\\$\\{JDD\\}' not found"):
        bdd.ecrire_generation(m, bdd.generer_robot(m))
    assert chemin.etat()["suivante"]["bouton"] == "Associer un jeu de données"
    m = bdd.associer_jdd("login_failed", "CLIENT_INVALIDE")
    assert not any(c["code"] == "jdd_requis" for c in bdd.controles(m))
    assert "Initialiser Le Test    &{JDD_CLIENT_INVALIDE}" in bdd.generer_robot(m)["contenu"]


def test_pages_suivent_le_dossier_du_depot(monkeypatch):
    """Pages déjà rangées par écran (resources/keywords/formulaire_connexion.resource) : les nouvelles vont à côté."""
    from atelier.generation import pom

    monkeypatch.setattr(pom, "_noms_ecrans", lambda: {"accueil", "formulaire_connexion"})
    inv = {"fichiers": {"resources/keywords/formulaire_connexion.resource": {"keywords": ["x"]},
                        "resources/keywords/accueil.resource": {"keywords": ["y"]},
                        "resources/common.resource": {"keywords": ["Initialiser Le Test"]}}}
    assert pom.chemin_page("tableau_de_bord", inv) == "resources/keywords/tableau_de_bord.resource"
    assert pom.chemin_page("accueil", {"fichiers": {}}).startswith("resources/pages/")


def test_initialiser_en_suite_setup_bloquant():
    from atelier.generation import studio

    s = studio.style_robot("tests/t.robot", "*** Settings ***\nSuite Setup       Initialiser Le Test    &{JDD_X}\n\n*** Test Cases ***\nT\n    Log    x\n")
    assert s[0]["gravite"] == "haute" and "Test Setup" in s[0]["message"]


def test_style_expert_antipatterns():
    from atelier.generation import studio

    brut = ("*** Settings ***\nLibrary    Browser\nLibrary    SeleniumLibrary\n\n*** Test Cases ***\nT\n    Go To    https://exemple.fr\n"
            "    Run Keyword And Ignore Error    Valider\n    Tap    100    200\n\n*** Keywords ***\nValider\n    [Documentation]    x\n"
            + "".join(f"    Log    {i}\n" for i in range(16)))
    m = " | ".join(x["message"] for x in studio.style_robot("tests/t.robot", brut))
    for attendu in ("masqué", "SeleniumLibrary", "coordonnées", "URL écrite", "15 lignes"):
        assert attendu in m, attendu
