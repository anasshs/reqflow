"""Cerveau de l'application : sources et fraîcheur, modules, lacunes, apprentissages, questions."""
import shutil
from pathlib import Path

import pytest

from tests.conftest import pointer_projet

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"


@pytest.fixture
def demo(tmp_path, monkeypatch):
    d = tmp_path / "demo"
    shutil.copytree(DEMO, d, ignore=shutil.ignore_patterns("results", "studio", "executions"))
    pointer_projet(d, monkeypatch)
    monkeypatch.setenv("IA_FOURNISSEUR", "aucun")
    return d


def test_vue_du_cerveau(demo):
    from atelier.intelligence import cerveau

    v = cerveau.vue()
    ids = {s["id"]: s for s in v["sources"]}
    assert set(ids) == {"carte", "exigences", "tests", "executions", "depot", "runs", "cursor"}
    assert ids["depot"]["fraicheur"] == "à jour" and ids["exigences"]["fraicheur"] == "jamais"  # exigences jamais importées
    assert any(l["sujet"].startswith("Exigences Jira") and l["priorite"] == 1 for l in v["lacunes"])
    assert v["maturite"]["sources"] == 7 and v["maturite"]["modules"] == len(v["modules"])
    for m in v["modules"]:
        assert {"couverture", "automatisation", "echecs", "connu"} <= set(m)


def test_modules_et_lacunes_calculees():
    from atelier.intelligence import cerveau

    srcs = [{"id": "carte", "nom": "Carte", "fraicheur": "à jour", "age_jours": 1, "action": "#discovery", "action_lib": "Explorer"}]
    mods = [{"module": "Virements", "connu": False, "exigences": 4, "exigences_couvertes": 1, "couverture": 25, "tests": 2, "tests_automatises": 0,
             "automatisation": 0, "echecs": ["DEMO-9"], "ecrans_fragiles": 0}]
    l = cerveau.lacunes(srcs, mods, 3)
    textes = [x["texte"] for x in l]
    assert l[0]["priorite"] == 1 and any("non" in t or "aucun écran" in t for t in textes)
    assert any("25 %" in t for t in textes) and any("DEMO-9" in t for t in textes) and any("3 proposition" in t for t in textes)


def test_question_sans_ia_repond_avec_les_faits(demo):
    from atelier.intelligence import cerveau

    r = cerveau.demander("Que sait-on de la connexion ?")
    assert r["mode"] == "recherche" and r["elements"] and r["reponse"]
    assert any("onnexion" in e["libelle"] for e in r["elements"])
    vide = cerveau.demander("hippopotame zébré")
    assert not vide["elements"] and "ne sait rien" in vide["reponse"]
    with pytest.raises(ValueError):
        cerveau.demander("?")


def test_question_avec_ia_fondee_sur_les_faits(demo, monkeypatch):
    from atelier.intelligence import cerveau, fournisseur_ia

    recu = {}
    monkeypatch.setattr(cerveau, "_ia_etat", lambda: {"appel_direct": True})

    def completer(systeme, demande, max_tokens=1500):
        recu["systeme"], recu["demande"] = systeme, demande
        return "Le module Connexion a 3 tests automatisés."

    monkeypatch.setattr(fournisseur_ia, "completer", completer)
    r = cerveau.demander("connexion tests")
    assert r["mode"] == "ia" and r["reponse"].startswith("Le module") and "UNIQUEMENT avec les faits" in recu["systeme"]
    assert "Faits (JSON)" in recu["demande"]


def test_outils_mcp_du_cerveau(demo):
    from atelier.adapters import facade

    v = facade.cerveau_application()
    assert set(v) == {"application", "maturite", "sources", "modules", "lacunes"}
    assert facade.cerveau_question("connexion")["mode"] == "recherche"
