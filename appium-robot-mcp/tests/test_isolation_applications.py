"""Isolation des applications d'un même projet : le Kanban, les Données des tests et le Knowledge Graph ne montrent que
l'application active (scénarios, tests, ressources, modèles MBT, jeux de données). « simple » n'est pas « simple_one »."""
import pytest


@pytest.fixture
def projet(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.domain import projet as pj

    monkeypatch.setattr(pj, "PROJECT_DIR", tmp_path)
    monkeypatch.setenv("ATELIER_FLUX", "simple")
    carte.creer_app("Banque Une", ["android"])          # slug banque_une
    carte.creer_app("Banque", ["android"])              # slug banque : préfixe de l'autre
    for app, cle in (("banque_une", "UNE_SOLDE"), ("banque", "BANQUE_SOLDE")):
        d = tmp_path / "tests" / app
        d.mkdir(parents=True)
        (d / "solde.robot").write_text(f"*** Test Cases ***\nSolde\n    [Tags]    {cle}\n    Initialiser Le Test    &{{JDD_{cle}}}\n    No Operation\n", "utf-8")
    (tmp_path / "data" / "jdd").mkdir(parents=True)
    (tmp_path / "data" / "jdd" / "recette.yaml").write_text("UNE_SOLDE:\n  donnees: {a: 1}\nBANQUE_SOLDE:\n  donnees: {a: 2}\n", "utf-8")
    from atelier.generation import bdd

    for cle in ("UNE_SOLDE", "BANQUE_SOLDE"):  # scénarios sans application déclarée : rattachés par le dossier de leur test
        bdd.creer(cle, cle)
        bdd.depuis_texte(cle, f"# language: fr\nFonctionnalité: {cle}\n  Scénario: {cle}\n    Quand je fais x\n    Alors c'est fait\n")
    return carte


def test_regle_d_appartenance(projet):
    from atelier.discovery import application

    connus = {"banque_une", "banque"}
    assert application.du_chemin("tests/banque_une/solde.robot", connus) == "banque_une"
    assert application.du_chemin("resources/locators/banque/x.resource", connus) == "banque"
    assert application.du_chemin("resources/common.resource", connus) == ""
    assert application.du_scenario({"application": "Banque Une"}, (), connus) == "banque_une"
    assert application.du_scenario({}, ["tests/banque/solde.robot"], connus) == "banque"
    assert not application.visible("", "banque", connus)                        # plusieurs applications : sans propriétaire, caché
    assert application.visible("", "banque", {"banque"})                         # une seule application : partagé


def test_kanban_et_donnees_par_application(projet, monkeypatch):
    from atelier.execution import donnees_tests
    from atelier.generation import kanban

    for app, attendu in (("banque_une", "UNE_SOLDE"), ("banque", "BANQUE_SOLDE")):
        monkeypatch.setattr(projet, "app_courante", lambda a=app: a)
        tests = [x["id"] for x in kanban.tableau()["tickets"] if x["type"] == "test"]
        assert tests == [attendu]
        assert [t["jeu"] for t in donnees_tests.vue("recette")["jeux"] if t["tests"]] == [attendu]


def test_graphe_par_application(projet, monkeypatch):
    from atelier.discovery import connaissance

    monkeypatch.setattr(projet, "app_courante", lambda: "banque")
    g = connaissance._construire(True, None)
    ids = set(g.noeuds)
    assert not any("banque_une" in i or "UNE_SOLDE" in i for i in ids)             # rien de l'autre application
    assert any("tests/banque/solde.robot" in i for i in ids) and "scenario:BANQUE_SOLDE" in ids
