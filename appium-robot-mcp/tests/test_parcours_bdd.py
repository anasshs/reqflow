"""Du parcours découvert au test : brouillon BDD depuis un chemin, un parcours du Knowledge Graph ou une session."""
import pytest


def _el(cle, libelle, type_="bouton"):
    return {"key": cle, "type": type_, "libelle": libelle, "locators": [f"id={cle}"]}


@pytest.fixture
def carte_virements(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.domain import projet

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    carte.creer_app("Banque Web", ["web"], web={"url": "https://recette.exemple.fr"}, type_="web")
    u = "https://recette.exemple.fr"
    acc = carte.observer([_el("lien_virements", "Virements", "lien"), _el("lien_comptes", "Mes comptes", "lien")], "web", u + "/")
    vir = carte.observer([_el("bouton_nouveau", "Nouveau virement"), _el("lien_historique", "Historique", "lien")], "web", u + "/virements")
    sai = carte.observer([_el("champ_montant", "Montant", "champ"), _el("champ_motif", "Motif", "champ"), _el("bouton_continuer", "Continuer")],
                         "web", u + "/virements/saisie")
    carte.renommer(acc["id"], "accueil")
    carte.renommer(vir["id"], "virements")
    carte.renommer(sai["id"], "virement_saisie", "Virements")
    carte.enregistrer_transition(acc["id"], vir["id"], "web", {"type": "tap", "cle": "lien_virements", "libelle": "Virements"})
    carte.enregistrer_transition(vir["id"], sai["id"], "web", {"type": "tap", "cle": "bouton_nouveau", "libelle": "Nouveau virement"})
    return carte, (acc["id"], vir["id"], sai["id"])


def test_brouillon_depuis_un_chemin(carte_virements):
    from atelier.generation import bdd, parcours_bdd

    _, (acc, _vir, sai) = carte_virements
    r = parcours_bdd.brouillon(ecrans=["accueil", "virement_saisie"], titre="Initier un virement")
    g = r["gherkin"]
    assert "Étant donné que je suis sur l'écran accueil" in g and "Quand je touche virements" in g and "Alors l'écran virement saisie est affiché" in g
    assert r["locators"] == {"connus": 2, "manquants": 0} and r["donnees"] == []
    assert any("Nouveau virement" in a for a in r["avertissements"])  # action sensible signalée
    m = bdd.charger(r["cle"])
    sc = m["scenarios"][0]
    assert "action_sensible" in sc["tags"] and m["statut"] == "brouillon" and not any(e["valide"] for e in sc["etapes"])
    quand = [e for e in sc["etapes"] if e["type"] == "when"]
    assert quand[0]["locator"] == "id=lien_virements" and quand[0]["ecran"] == "accueil"
    assert not [c for c in r["controles"] if c["code"] == "donnee_litterale"]
    # même déroulé : pas de doublon (le test existant est désigné), sauf variante voulue
    with pytest.raises(parcours_bdd.DejaCouvert) as e:
        parcours_bdd.brouillon(ecrans=["accueil", "virements"], titre="Aller aux virements")  # contenu dans le premier
    assert e.value.existant["cle"] == r["cle"] and e.value.existant["inclus"]
    v = parcours_bdd.brouillon(ecrans=["accueil", "virement_saisie"], titre="Initier un virement", forcer=True)
    assert v["cle"] == r["cle"] + "_2" and any("Variante" in a for a in v["avertissements"])


def test_brouillon_depuis_un_parcours_propose(carte_virements, monkeypatch):
    from atelier.discovery import apprentissage, sessions_discovery
    from atelier.generation import parcours_bdd

    monkeypatch.setattr(sessions_discovery, "active", lambda: None)
    for e in ("virement_saisie", "accueil", "virements"):  # proposés dans le désordre
        apprentissage.proposer("parcours", "Virement interne", e)
    assert parcours_bdd.ecrans_du_parcours("parcours:virement_interne") == [carte_virements[1][i] for i in (0, 1, 2)]
    r = parcours_bdd.brouillon(parcours="parcours:virement_interne")
    assert r["ecrans"] == ["accueil", "virements", "virement_saisie"] and "parcours" in r["cle"]


def test_brouillon_depuis_une_session_et_champs(carte_virements):
    from atelier.discovery import carte, sessions_discovery as ds
    from atelier.generation import parcours_bdd

    _, (acc, vir, sai) = carte_virements
    conf = carte.observer([_el("texte_ok", "Virement enregistré", "texte")], "web", "https://recette.exemple.fr/virements/ok")
    carte.enregistrer_transition(sai, conf["id"], "web", {"type": "tap", "cle": "bouton_continuer", "libelle": "Continuer"})
    s = ds.creer({})
    ds.demarrer(s["id"])
    for de, vers in ((acc, vir), (vir, sai), (sai, conf["id"])):
        ds._evenement(s["id"], {"type": "transition", "de": de, "vers": vers})
    r = parcours_bdd.brouillon(session=s["id"])
    assert "je renseigne montant avec le jeu de données" in r["gherkin"] and r["donnees"] == ["champ_montant", "champ_motif"]
    with pytest.raises(ValueError):
        parcours_bdd.brouillon(ecrans=["accueil"], session=s["id"])


def test_brouillon_fidele_aux_actions_de_la_session(carte_virements):
    """Session avec actions enregistrées : le brouillon rejoue ce qui a été fait (et seulement les champs saisis),
    sans doublon quand deux façades ont écrit le même événement."""
    import json as _json

    from atelier.discovery import carte, sessions_discovery as ds
    from atelier.generation import parcours_bdd

    _, (acc, vir, sai) = carte_virements
    loc = lambda ecran, cle: ((carte.ecran(ecran)["elements"][cle].get("locators") or {}).get("web") or [""])[0]  # noqa: E731
    s = ds.creer({})
    ds.demarrer(s["id"])
    cle_lien = next(k for k in carte.ecran(acc)["elements"] if k.startswith(("lien", "bouton")))
    cle_montant = "champ_montant"
    evts = [{"type": "action", "detail": "tap " + _json.dumps({"locator": loc(acc, cle_lien)})},
            {"type": "transition", "de": acc, "vers": vir}]
    for e in evts + evts:  # écrit deux fois, comme avec deux façades
        ds._evenement(s["id"], {**e, "date": "2026-11-23T10:00:00+00:00"})
    ds._evenement(s["id"], {"type": "transition", "de": vir, "vers": sai, "date": "2026-11-23T10:00:05+00:00"})
    ds._evenement(s["id"], {"type": "action", "date": "2026-11-23T10:00:06+00:00",
                             "detail": "type_text " + _json.dumps({"locator": loc(sai, cle_montant), "text": "{{var:MONTANT}}"})})
    r = parcours_bdd.brouillon(session=s["id"])
    g = r["gherkin"]
    assert g.count("Quand je touche") == 1 and "je renseigne montant avec la donnée MONTANT" in g
    assert "motif" not in g.lower().split("scénario")[-1]          # champ non saisi : pas d'étape
    assert r["variables"] == {"montant": "MONTANT"}


def test_du_parcours_au_script_robot_sans_xray(carte_virements, monkeypatch):
    """Fil complet par l'interface, sans Jira ni Xray : écrans découverts → test BDD → suite Robot écrite."""
    from fastapi.testclient import TestClient

    for v in ("XRAY_CLIENT_ID", "XRAY_CLIENT_SECRET", "JIRA_URL", "JIRA_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    from web_app_loader import charger_app_web

    _, (acc, vir, sai) = carte_virements
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/").status_code == 200  # cookie de session, comme en ouvrant la page
    r = c.post("/api/discovery/parcours-bdd", json={"ecrans": [acc, vir, sai], "titre": "Saisir un virement"})
    assert r.status_code == 200, r.text
    cle = r.json()["cle"]
    assert c.get(f"/api/bdd/{cle}").status_code == 200
    apercu = c.post(f"/api/bdd/{cle}/generer", json={}).json()
    assert "*** Test Cases ***" in apercu["contenu"] and "ecrit" not in apercu
    ecrit = c.post(f"/api/bdd/{cle}/generer", json={"ecrire": True})
    assert ecrit.status_code == 200, ecrit.text
    from atelier.domain import projet
    assert (projet.PROJECT_DIR / ecrit.json()["ecrit"]).exists()
