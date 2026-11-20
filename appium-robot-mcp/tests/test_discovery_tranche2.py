"""Discovery, deuxième tranche : classement des actions, suggestions (IA bornée aux candidates), comportements,
réseau (sans valeurs ni en-têtes), actions depuis le Studio, corrélation écrans ↔ Jira / Xray / dépôt."""
import pytest


def _el(cle, libelle, type_="bouton"):
    return {"key": cle, "type": type_, "libelle": libelle, "locators": [f"id={cle}"]}


@pytest.fixture
def app(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.domain import projet

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    carte.creer_app("Banque Web", ["web"], web={"url": "https://recette.exemple.fr"}, type_="web")
    return carte


# --------------------------------------------------------------------------- classement
def test_classement_et_politique(app):
    from atelier.discovery import classement as c

    assert c.classer(_el("bouton_deconnexion", "Se déconnecter"))["classe"] == "forbidden"
    assert c.classer(_el("bouton_virement", "Nouveau virement"))["classe"] == "sensitive"
    assert c.classer(_el("champ_montant", "Montant", "champ"))["classe"] == "controlled"
    assert c.classer(_el("lien_comptes", "Mes comptes", "lien"))["classe"] == "safe"
    # un menu ou un lien vers un sujet sensible reste de la navigation ; l'action sur ce sujet est sensible
    assert c.classer(_el("lien_virements", "Virements", "lien"))["classe"] == "safe"
    assert c.classer(_el("lien_beneficiaires", "Mes bénéficiaires", "lien"))["classe"] == "safe"
    assert c.classer(_el("bouton_ajout", "Ajouter un bénéficiaire"))["classe"] == "sensitive"
    assert c.classer(_el("champ_montant_virement", "Montant du virement", "champ"))["classe"] == "controlled"
    # exploration / suggestion : safe uniquement
    assert not c.autorise(_el("champ_montant", "Montant", "champ"), "exploration")["autorise"]
    # guidé, environnement non déclaré : safe + controlled ; sensible refusée
    assert c.autorise(_el("champ_montant", "Montant", "champ"), "guidee", "recette")["autorise"]
    assert not c.autorise(_el("bouton_virement", "Nouveau virement"), "guidee", "recette")["autorise"]
    # environnement qui autorise le sensible : confirmation explicite exigée
    c.maj_regles(environnements={"recette": ["safe", "controlled", "sensitive"], "production": ["safe"]})
    v = c.autorise(_el("bouton_virement", "Nouveau virement"), "guidee", "recette")
    assert not v["autorise"] and v["confirmation"]
    assert c.autorise(_el("bouton_virement", "Nouveau virement"), "guidee", "recette", confirme=True)["autorise"]
    assert not c.autorise(_el("champ_montant", "Montant", "champ"), "guidee", "production")["autorise"]
    # interdite : jamais, même confirmée ; aucun environnement ne peut l'autoriser
    assert not c.autorise(_el("bouton_deconnexion", "Se déconnecter"), "guidee", "recette", confirme=True)["autorise"]
    with pytest.raises(ValueError):
        c.maj_regles(environnements={"recette": ["forbidden"]})
    # classement manuel par clé
    c.marquer("lien_comptes", "sensitive")
    assert c.classer(_el("lien_comptes", "Mes comptes", "lien"))["raison"] == "classement manuel"
    c.marquer("lien_comptes", "auto")
    assert c.classer(_el("lien_comptes", "Mes comptes", "lien"))["classe"] == "safe"


# --------------------------------------------------------------------------- comportements et réseau
def test_comportements_et_regles_proposees(app):
    from atelier.discovery import comportements
    from atelier.domain import declarations

    avant = [_el("bouton_valider", "Continuer"), {"key": "texte_titre", "type": "texte", "libelle": "Saisie"}]
    apres = avant[:1] + [{"key": "texte_err", "type": "texte", "libelle": "Le montant est obligatoire"},
                         _el("bouton_annuler", "Annuler")]
    comps = comportements.comparer(avant, apres, "Continuer")
    assert {c["type"] for c in comps} == {"message", "element_apparu"}
    ids = comportements.proposer_regles(comps, "virement_saisie")
    n = declarations.charger()["noeuds"][ids[0]]
    assert n["type"] == "regle" and n["statut"] == "à valider" and n["provenance"] == "déduit"
    assert comportements.proposer_regles(comps, "virement_saisie") == []  # pas de doublon


def test_reseau_normalise_sans_valeurs(app):
    from atelier.discovery import comportements
    from atelier.integrations.playwright import WebBackend

    class Req:
        def __init__(self, url, t="fetch", m="GET"):
            self.url, self.resource_type, self.method = url, t, m

    class Rep:
        def __init__(self, req, statut=200):
            self.request, self.status = req, statut

    w = WebBackend()
    w._noter_reponse(Rep(Req("https://api.exemple.fr/comptes/12345678/operations?token=SECRET&page=2")))
    w._noter_reponse(Rep(Req("https://api.exemple.fr/comptes/87654321/operations?page=3"), 500))
    w._noter_reponse(Rep(Req("https://cdn.exemple.fr/logo.png", "image")))
    j = w.journal_reseau()
    assert len(j) == 2 and "SECRET" not in str(j) and j[0]["parametres"] == ["page", "token"]
    eps = comportements.endpoints(j)
    assert len(eps) == 1 and eps[0]["chemin"] == "/comptes/{id}/operations" and eps[0]["appels"] == 2 and eps[0]["erreurs"] == 1
    assert comportements.rapprocher(eps)[0]["connu"] is None
    assert comportements.proposer_endpoints(eps) == ["endpoint:GET /comptes/{id}/operations"]


def test_endpoint_documente_reconnu(app, tmp_path):
    from atelier.discovery import comportements

    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "comptes.yaml").write_text(
        "openapi: 3.0.0\ninfo: {title: t, version: '1'}\npaths:\n  /comptes/{compteId}/operations:\n    get: {summary: ops}\n", "utf-8")
    eps = comportements.rapprocher([{"methode": "GET", "hote": "h", "chemin": "/comptes/{id}/operations", "statuts": [200], "parametres": []}])
    assert eps[0]["connu"] == "openapi"
    assert comportements.proposer_endpoints(eps) == []


# --------------------------------------------------------------------------- suggestions
def test_suggestions_safe_et_ia_bornee(app, monkeypatch):
    from atelier.discovery import assistance
    from atelier.intelligence import fournisseur_ia

    e0 = app.observer([_el("lien_comptes", "Mes comptes", "lien"), _el("lien_aide", "Aide", "lien")], "web", "https://recette.exemple.fr/")
    els = [_el("lien_comptes", "Mes comptes", "lien"), _el("lien_aide", "Aide", "lien"), _el("bouton_virement", "Nouveau virement"),
           _el("bouton_deconnexion", "Se déconnecter"), _el("champ_iban", "IBAN FR7612345678901234567890123", "champ")]
    monkeypatch.setattr(fournisseur_ia, "configure", lambda: False)
    r = assistance.suggerer(els, e0, "web")
    assert [x["cle"] for x in r["suggestions"]] == ["lien_comptes", "lien_aide"]
    assert r["ecartees"] == {"controlled": 1, "sensitive": 1, "forbidden": 1}
    envoye = {}

    def completer(systeme, demande, n):
        envoye["d"] = demande
        return '[{"cle": "lien_aide", "raison": "aide jamais vue"}, {"cle": "bouton_inventé", "raison": "x"}]'

    monkeypatch.setattr(fournisseur_ia, "configure", lambda: True)
    monkeypatch.setattr(fournisseur_ia, "completer", completer)
    r = assistance.suggerer(els, e0, "web")
    assert [x["cle"] for x in r["suggestions"]] == ["lien_aide", "lien_comptes"] and r["suggestions"][0]["par_ia"]
    assert "bouton_virement" not in envoye["d"] and "IBAN" not in envoye["d"]  # seules les candidates sûres partent


# --------------------------------------------------------------------------- actions depuis le Studio
def test_agir_classe_refuse_et_observe(app, monkeypatch):
    from atelier.discovery import actions, observation, session, sessions_discovery as ds

    ecrans = {"courant": [_el("bouton_virement", "Nouveau virement"), _el("lien_aide", "Aide", "lien")]}
    faits = []
    monkeypatch.setattr(session, "plateforme", lambda: "web")
    monkeypatch.setattr(session, "current_elements", lambda n=150: ecrans["courant"])
    monkeypatch.setattr(session, "is_web", lambda: False)
    monkeypatch.setattr(observation, "observer", lambda els=None, test_key=None: {"id": "e_x", "nom": "aide"})

    def tap(loc):
        faits.append(loc)
        ecrans["courant"] = [{"key": "texte_msg", "type": "texte", "libelle": "Service indisponible, erreur 503"}]

    monkeypatch.setattr(actions, "tap", tap)
    with pytest.raises(PermissionError):
        ds.agir("tap", "id=lien_aide")
    s = ds.creer({"environnement": "recette", "actions_interdites": ["Aide"]})
    ds.demarrer(s["id"])
    r = ds.agir("tap", "id=bouton_virement")
    assert not r["execute"] and r["classe"] == "sensitive" and faits == []
    r = ds.agir("tap", "id=lien_aide")
    assert not r["execute"] and "session" in r["raison"]  # interdite par la configuration de la session
    s2 = ds.arreter(s["id"])
    s3 = ds.creer({"environnement": "recette"})
    ds.demarrer(s3["id"])
    r = ds.agir("tap", "id=lien_aide")
    assert r["execute"] and faits == ["id=lien_aide"] and r["regles_proposees"]
    types = [e["type"] for e in ds.timeline(s3["id"])]
    assert "comportement" in types
    assert ds.arreter(s3["id"])["resultats"]["comportements"] >= 1
    assert s2["resultats"]["refus"] == 2


# --------------------------------------------------------------------------- corrélation
def test_correlation_ecran_jira_xray_depot(app, tmp_path):
    from atelier.discovery import correlation
    from atelier.intelligence import patrimoine_xray

    e = app.observer([_el("bouton_valider", "Valider le virement")], "web", "https://recette.exemple.fr/virement")
    app.renommer(e["id"], "virement_saisie", "Virements")
    (tmp_path / "resources").mkdir()
    (tmp_path / "resources" / "virement.resource").write_text(
        "*** Variables ***\n&{LOC_VIREMENT_SAISIE_WEB}    bouton_valider=id=bouton_valider\n", "utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "virement.robot").write_text(
        "*** Settings ***\nResource    ../resources/virement.resource\n\n*** Test Cases ***\nVirement simple\n"
        "    [Tags]    DEMO-11\n    Click    ${LOC_VIREMENT_SAISIE_WEB}[bouton_valider]\n", "utf-8")
    patrimoine_xray.enregistrer({"projet": "DEMO", "tests": [{"cle": "DEMO-11", "resume": "Virement simple", "exigences": ["DEMO-2"]}],
                                 "exigences": [{"cle": "DEMO-2", "type": "user_story", "resume": "Saisir un virement"},
                                               {"cle": "DEMO-3", "type": "user_story", "resume": "Plafond des virements"},
                                               {"cle": "DEMO-4", "type": "user_story", "resume": "Consulter les comptes"}]}, "test")
    c = correlation.ecran(e["id"])
    assert [t["cle"] for t in c["tests_xray"]] == ["DEMO-11"] and c["tests_robot"]
    assert [x["cle"] for x in c["exigences"]] == ["DEMO-2"] and "tests/virement.robot" in c["fichiers"]
    assert [x["cle"] for x in c["candidats"]] == ["DEMO-3"]  # « virement » en commun ; DEMO-4 non : présélection pour l'IA
    assert c["exigences_proposees"] == []                    # jamais une proposition sans jugement d'une IA
    correlation.confirmer(e["id"], "DEMO-3")
    c = correlation.ecran(e["id"])
    assert {x["cle"] for x in c["exigences"]} == {"DEMO-2", "DEMO-3"} and not c["candidats"]
    syn = correlation.synthese()
    assert syn["ecrans"][0]["exigences"] == 2 and syn["sans_test"] == 0
    assert correlation.commits_gitlab(c["fichiers"]) == {"configure": False, "fichiers": {}}
