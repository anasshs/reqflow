"""Discovery piloté par un agent (MCP) : actions classées pendant une session, propositions à valider, provenance
et apprentissages visibles dans le Knowledge Graph."""
import pytest


def _el(cle, libelle, type_="bouton"):
    return {"key": cle, "type": type_, "libelle": libelle, "locators": [f"id={cle}"]}


@pytest.fixture
def app(tmp_path, monkeypatch):
    from atelier.discovery import carte, observation, session
    from atelier.domain import projet

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    carte.creer_app("Banque Web", ["web"], web={"url": "https://recette.exemple.fr"}, type_="web")
    ecran = {"els": [_el("bouton_virement", "Nouveau virement"), _el("lien_aide", "Aide", "lien"), _el("champ_montant", "Montant", "champ")]}
    monkeypatch.setattr(session, "plateforme", lambda: "web")
    monkeypatch.setattr(session, "is_web", lambda: False)
    monkeypatch.setattr(session, "current_elements", lambda n=150: ecran["els"])
    monkeypatch.setattr(session, "etat", {**session.etat, "platform": "web"})
    monkeypatch.setattr(observation, "carte_active", lambda: True)
    monkeypatch.setattr(observation, "observer", lambda els=None, test_key=None: carte.observer(
        [e for e in (els if els is not None else ecran["els"]) if e.get("key")], "web", "https://recette.exemple.fr/"))
    return carte, ecran


def test_actions_mcp_classees_seulement_en_session(app):
    from atelier.discovery import apprentissage, sessions_discovery as ds

    faits = []
    with pytest.raises(PermissionError, match="hors session"):  # V2 : action sensible refusée aussi hors session
        apprentissage.action_mcp("tap", "id=bouton_virement", lambda: faits.append("v"))
    assert apprentissage.action_mcp("tap", "id=lien_aide", lambda: faits.append("v")) is None  # navigation hors session : permise
    s = ds.creer({"environnement": "recette"})
    ds.demarrer(s["id"])
    with pytest.raises(PermissionError, match="non autorisée"):
        apprentissage.action_mcp("tap", "id=bouton_virement", lambda: faits.append("v2"))
    apprentissage.action_mcp("type_text", "id=champ_montant", lambda: faits.append("saisie"))  # contrôlée : autorisée par défaut
    from atelier.discovery import classement

    classement.maj_regles(environnements={"recette": ["safe", "controlled", "sensitive"]})
    with pytest.raises(PermissionError, match="réservée à l'automaticien"):  # agent non autorisé sur cet environnement
        apprentissage.action_mcp("tap", "id=bouton_virement", lambda: faits.append("v3"))
    classement.maj_regles(environnements={"recette": ["safe"]})
    with pytest.raises(PermissionError, match="non autorisée"):
        apprentissage.action_mcp("type_text", "id=champ_montant", lambda: faits.append("saisie2"))
    apprentissage.action_mcp("tap", "id=lien_aide", lambda: faits.append("aide"))
    assert faits == ["v", "saisie", "aide"]
    assert sum(e["type"] == "refus" for e in ds.timeline(s["id"])) == 3


def test_ecran_courant_et_propositions_vers_le_graphe(app):
    from atelier.discovery import apprentissage, connaissance, sessions_discovery as ds
    from atelier.intelligence import patrimoine_xray

    carte, _ = app
    s = ds.creer({"environnement": "recette"})
    ds.demarrer(s["id"])
    v = apprentissage.ecran_courant()
    cl = {e["cle"]: (e["classe"], e["autorise"]) for e in v["elements"]}
    assert cl["bouton_virement"] == ("sensitive", False) and cl["lien_aide"] == ("safe", True)
    assert [x["cle"] for x in v["a_essayer"]] == ["lien_aide"] and v["session"]["id"] == s["id"]
    eid = v["ecran"]["id"]

    apprentissage.proposer("nom_ecran", "Accueil client", eid, module="Accueil")
    apprentissage.proposer("fonctionnalite", "Initier un virement", eid, description="bouton Nouveau virement")
    apprentissage.proposer("regle", "Montant obligatoire", eid, agent="claude")
    patrimoine_xray.enregistrer({"projet": "DEMO", "tests": [], "exigences": [{"cle": "DEMO-7", "type": "user_story", "resume": "Accueil"}]}, "test")
    apprentissage.proposer("lien_exigence", "", eid, exigence="DEMO-7")
    with pytest.raises(KeyError):
        apprentissage.proposer("lien_exigence", "", eid, exigence="DEMO-404")
    props = apprentissage.propositions(s["id"])
    assert {p["type"] for p in props} == {"nom_ecran", "fonctionnalite", "regle", "contient", "impacte"}
    assert all("session " + s["id"] in (p["source"] or "") for p in props)
    assert "proposition" in [e["type"] for e in ds.timeline(s["id"])]

    g = connaissance.construire()
    f = g.noeuds["fonctionnalite:initier_un_virement"]
    assert f.statut == "à valider" and "Cursor (MCP) · session" in f.source
    assert g.noeuds["regle:montant_obligatoire"].source.startswith("Claude (MCP)")
    loc = next(n for n in g.noeuds.values() if n.type == "locator" and n.libelle == "bouton_virement")
    assert loc.proprietes["classe_action"] == "sensitive"
    assert g.noeuds[f"ecran:{eid}"].proprietes["noms_proposes"]

    # décisions humaines : nom appliqué, fonctionnalité validée, règle rejetée (jamais reproposée)
    nom = next(p for p in props if p["type"] == "nom_ecran")
    apprentissage.decider(nom["id"], True)
    assert carte.ecran(eid)["nom"] == "accueil_client" and carte.ecran(eid)["module"] == "Accueil"
    apprentissage.decider("fonctionnalite:initier_un_virement", True)
    apprentissage.decider("regle:montant_obligatoire", False)
    g = connaissance.construire()
    assert g.noeuds["fonctionnalite:initier_un_virement"].statut == "validé" and "regle:montant_obligatoire" not in g.noeuds
    with pytest.raises(PermissionError):
        from atelier.domain import declarations

        declarations.ajouter_noeud("regle:montant_obligatoire", "regle", "Montant obligatoire", auteur="ia")


def test_agent_autorise_par_environnement_et_liste_rouge_levee(app):
    from atelier.discovery import apprentissage, classement, sessions_discovery as ds

    carte, ecran = app
    ecran["els"] = ecran["els"] + [_el("bouton_valider", "Valider")]
    faits = []
    classement.maj_regles(environnements={"recette": ["safe", "controlled", "sensitive"], "preprod": ["safe"]},
                          agent_sensible={"recette": True}, liste_rouge_levee={"recette": [r"\bvalid"]})
    with pytest.raises(ValueError, match="liste rouge"):
        classement.maj_regles(liste_rouge_levee={"recette": ["inexistant"]})
    s = ds.creer({"environnement": "recette"})
    ds.demarrer(s["id"])
    apprentissage.action_mcp("tap", "id=bouton_virement", lambda: faits.append("virement"))  # sensible : agent autorisé en recette
    apprentissage.action_mcp("tap", "id=bouton_valider", lambda: faits.append("valider"))    # liste rouge levée en recette
    assert faits == ["virement", "valider"]
    assert any(e["type"] == "sensible_agent" for e in ds.timeline(s["id"]))
    # exploration autonome : liste rouge complète, quel que soit l'environnement
    assert not classement.autorise({"key": "bouton_valider", "libelle": "Valider", "type": "bouton"}, "exploration", "recette")["autorise"]
    ds.arreter(s["id"])
    s2 = ds.creer({"environnement": "preprod"})
    ds.demarrer(s2["id"])
    with pytest.raises(PermissionError):
        apprentissage.action_mcp("tap", "id=bouton_valider", lambda: faits.append("valider-preprod"))  # préprod : toujours interdit
    with pytest.raises(PermissionError):
        apprentissage.action_mcp("tap", "id=bouton_virement", lambda: faits.append("virement-preprod"))
    # décisions journalisées ; retrait de l'autorisation
    classement.maj_regles(agent_sensible={})
    j = classement.journal_autorisations()
    assert [x["quoi"] for x in j][:1] == ["agent autorisé sur les actions sensibles"] and j[0]["apres"] is False
    assert {x["quoi"] for x in j} == {"agent autorisé sur les actions sensibles", "liste rouge levée"}
