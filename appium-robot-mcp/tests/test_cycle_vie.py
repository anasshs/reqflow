"""Cycle de vie d'un test aligné sur le workflow Jira : Brouillon → Rédigé → À automatiser (candidat auto = vrai)
→ En cours d'automatisation → Automatisé (3 exécutions stables + revue du script)."""
import pytest


class FauxJira:
    enabled = True

    def __init__(self, panne=False):
        self.appels, self.panne = [], panne

    def maj_champs(self, cle, champs):
        self.appels.append(("champs", cle, champs))

    def transition(self, cle, nom):
        if self.panne:
            raise RuntimeError("Transition « À automatiser » indisponible")
        self.appels.append(("transition", cle, nom))
        return nom


@pytest.fixture
def cv(tmp_path, monkeypatch):
    from atelier.domain import projet
    from atelier.generation import conception, cycle_vie

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(conception, "controles_revue", lambda cle: [{"gravite": "ok", "message": "ok"}])
    cycle_vie.maj_config(statuts={"redige": "Rédigé", "a_automatiser": "A automatiser", "en_automatisation": "En cours d'automatisation",
                                  "automatise": "Automatisé"}, champ_candidat="customfield_10070", valeur_candidat="option:Oui")
    return cycle_vie


def test_workflow_complet_et_ordre_jira(cv, monkeypatch):
    from atelier.generation import studio

    j = FauxJira()
    assert cv.etat("DEMO-1")["etape"] == "brouillon"
    with pytest.raises(ValueError, match="impossible"):
        cv.avancer("DEMO-1", "a_automatiser", jira=j)  # pas de saut d'étape
    cv.avancer("DEMO-1", "redige", jira=j)
    cv.avancer("DEMO-1", "a_automatiser", jira=j)
    assert j.appels[-2:] == [("champs", "DEMO-1", {"customfield_10070": {"value": "Oui"}}), ("transition", "DEMO-1", "A automatiser")]
    cv.avancer("DEMO-1", "en_automatisation", jira=j)
    # Automatisé : script portant la clé + 3 exécutions stables + revue du script
    monkeypatch.setattr(cv, "_scripts", lambda cle: ["tests/app/virements/v.robot"])
    monkeypatch.setattr(studio, "_stabilite_suites", lambda f: {x: {"stable": False} for x in f})
    monkeypatch.setattr(studio, "revues_scripts", lambda: {"tests/app/virements/v.robot": {"statut": "Approved"}})
    with pytest.raises(PermissionError, match="stables"):
        cv.avancer("DEMO-1", "automatise", jira=j)
    monkeypatch.setattr(studio, "_stabilite_suites", lambda f: {x: {"stable": True} for x in f})
    r = cv.avancer("DEMO-1", "automatise", jira=j)
    assert r["etape"] == "automatise" and [h["vers"] for h in r["historique"]] == ["redige", "a_automatiser", "en_automatisation", "automatise"]
    assert cv.avancer("DEMO-1", "en_automatisation", jira=j)["etape"] == "en_automatisation"  # régression : retour possible


def test_jira_en_echec_rien_ne_change(cv):
    cv.avancer("DEMO-2", "redige", jira=FauxJira())
    with pytest.raises(RuntimeError, match="indisponible"):
        cv.avancer("DEMO-2", "a_automatiser", jira=FauxJira(panne=True))
    assert cv.etat("DEMO-2")["etape"] == "redige"


def test_sans_champ_candidat_et_sans_jira(cv):
    class SansJira:
        enabled = False

    cv.maj_config(champ_candidat="")
    cv.avancer("DEMO-3", "redige", jira=SansJira())
    with pytest.raises(PermissionError, match="candidat auto"):
        cv.avancer("DEMO-3", "a_automatiser", jira=SansJira())
    r = cv.avancer("DEMO-3", "brouillon", jira=SansJira())
    assert r["etape"] == "brouillon" and "Jira non configuré" in r["avertissement"]
    with pytest.raises(ValueError, match="customfield"):
        cv.maj_config(champ_candidat="candidat")
    assert cv._valeur_jira("true") is True and cv._valeur_jira("options:Oui") == [{"value": "Oui"}]
