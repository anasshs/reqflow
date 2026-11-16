"""V2, phase 6 : échecs reliés à l'écran / au composant, causes historisées, régressions récurrentes, anomalies
connues ; localisation calculée une fois puis mémorisée."""
import pytest


@pytest.fixture
def ec(tmp_path, monkeypatch):
    from atelier.discovery import entites
    from atelier.domain import projet
    from atelier.execution import echecs, echecs_connaissance

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path.resolve())

    def evt(run, test, precedent, date, msg="Element not found"):
        return {"id": f"{run}::{test}", "run": run, "test_id": test, "nom": f"Test {test}", "cle_xray": "", "message": msg, "date": date,
                "plateforme": "web", "precedent": precedent, "categorie_confirmee": "", "categorie_probable": "Locator Issue", "jira": "", "statut": "Diagnosis Proposed"}
    evts = [evt("RUN-1", "t1", None, "2026-11-10T10:00"), evt("RUN-2", "t1", "PASS", "2026-11-12T10:00"),
            evt("RUN-3", "t2", "PASS", "2026-11-14T10:00"), evt("RUN-3", "t9", "FAIL", "2026-11-14T10:00", "Timeout")]
    monkeypatch.setattr(echecs, "collecter", lambda limite=30: list(reversed(evts)))
    appels = []

    def contexte(eid):
        appels.append(eid)
        return {"ecran": "", "composant": ""} if eid.endswith("t9") else {"ecran": "saisie", "composant": "champ_montant", "locator": "id=montant",
                                                                           "etape": "Saisir Le Montant", "plateforme": "web"}
    monkeypatch.setattr(echecs, "_contexte_sur", contexte)
    monkeypatch.setattr(entites, "champs", lambda ecran="", g=None: [{"ecran": "saisie", "nom_technique": "champ_montant"}])
    monkeypatch.setattr(entites, "anomalies", lambda g=None: [{"id": "bug:VIR-99", "id_jira": "VIR-99", "titre": "Montant refusé", "statut": "Ouvert",
                                                               "ecrans": ["saisie"], "composants": [], "fonctionnalites": []}])
    return echecs_connaissance, appels


def test_localisation_memorisee(ec):
    m, appels = ec
    assert m.localiser_tous()["localises"] == 4 and len(appels) == 4
    assert m.localiser_tous()["localises"] == 0 and len(appels) == 4  # déjà localisés : aucun run relu
    assert m.localiser("RUN-1::t1")["composant"] == "champ_montant"


def test_regroupement_regressions_et_causes(ec):
    m, _ = ec
    m.localiser_tous()
    r = m.par_composant()
    c = r["composants"][0]
    assert c["cle"] == "saisie.champ_montant" and c["est_champ"] and c["echecs"] == 3 and c["runs"] == ["RUN-1", "RUN-2", "RUN-3"]
    assert c["regressions"] == 2 and c["regression_recurrente"] and r["regressions_recurrentes"] == ["saisie.champ_montant"]
    assert [x["cause"] for x in c["causes"]] == ["Locator Issue"] * 3 and c["anomalies_connues"][0]["id_jira"] == "VIR-99"
    autre = next(x for x in r["composants"] if not x["localise"])
    assert autre["cle"] == "test : Test t9" and not autre["regression_recurrente"] and r["non_localises"] == 1


def test_connaissance_d_un_echec(ec):
    m, _ = ec
    k = m.connaissance_echec("RUN-3::t2")
    assert k["composant"] == "saisie.champ_montant" and k["est_champ"] and k["regression"] and k["regression_recurrente"]
    assert {x["run"] for x in k["meme_composant"]} == {"RUN-1", "RUN-2"} and k["anomalies_connues"][0]["id"] == "bug:VIR-99"
    assert not m.connaissance_echec("RUN-1::t1")["regression"]


def test_outil_mcp(ec):
    from atelier.adapters import facade

    m, _ = ec
    m.localiser_tous()
    assert facade.failure_connaissance()["regressions_recurrentes"] == ["saisie.champ_montant"]
    assert facade.failure_connaissance("RUN-2::t1")["regression"] is True
