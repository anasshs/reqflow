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
