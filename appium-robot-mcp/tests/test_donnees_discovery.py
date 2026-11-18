"""Discovery Data Setup : référentiel universel de variables (définition, valeur, source, contexte, cycle de vie),
profils, générateurs, calculs dépendants, contexte de session cohérent, besoins d'un écran, secrets jamais exposés."""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

import pytest


@pytest.fixture
def ref(projet):
    from atelier.discovery import donnees

    donnees._MEMOIRE.clear()
    donnees._CHOIX.clear()
    v = donnees.enregistrer_variable
    v("FIRST_NAME", {"nom": "Prénom", "alias": ["first name"], "source": {"type": "generateur", "generateur": "prenom"}})
    v("LAST_NAME", {"nom": "Nom", "alias": ["nom de famille"]})
    v("FULL_NAME", {"nom": "Nom complet", "source": {"type": "calcul", "operation": "texte", "formule": "{{FIRST_NAME}} {{LAST_NAME}}"}})
    v("EMAIL", {"nom": "Adresse e-mail", "type": "email", "source": {"type": "generateur", "generateur": "email", "prefixe": "client"}})
    v("PHONE", {"nom": "Téléphone", "type": "telephone", "regles": {"format": r"06\d{8}"},
                "source": {"type": "generateur", "generateur": "telephone", "motif": "06########"}})
    v("PASSWORD", {"nom": "Mot de passe", "sensibilite": "secrète"})
    v("START_DATE", {"nom": "Date de début", "type": "date", "source": {"type": "generateur", "generateur": "date", "decalage_jours": 10}})
    v("CREDIT_DURATION", {"nom": "Durée du crédit", "type": "entier", "regles": {"min": 1, "max": 360}})
    v("END_DATE", {"nom": "Date de fin", "type": "date",
                   "source": {"type": "calcul", "operation": "date", "base": "{{START_DATE}}", "ajouter": "{{CREDIT_DURATION}}", "unite": "mois"}})
    v("AMOUNT_HT", {"nom": "Montant HT", "type": "nombre", "source": {"type": "generateur", "generateur": "nombre", "min": 100, "max": 500, "decimales": 2}})
    v("VAT_RATE", {"nom": "Taux de TVA", "type": "nombre"})
    v("AMOUNT_TTC", {"nom": "Montant TTC", "type": "nombre",
                     "source": {"type": "calcul", "operation": "nombre", "formule": "{{AMOUNT_HT}} * (1 + {{VAT_RATE}} / 100)", "decimales": 2}})
    v("API_BASE_URL", {"nom": "URL de l'API", "type": "url"})
    v("DOSSIER_REFERENCE", {"nom": "Référence du dossier", "source": {"type": "session"}, "regles": {"format": r"D-\d{4}"}})
    for cle, val in (("LAST_NAME", "Durand"), ("CREDIT_DURATION", 12), ("VAT_RATE", 20)):
        donnees.definir_valeur(cle, val)
    donnees.definir_valeur("API_BASE_URL", "https://int.exemple.test/api", env="INT")
    donnees.definir_valeur("API_BASE_URL", "https://recette.exemple.test/api", env="RECETTE")
    donnees.enregistrer_profil("CLIENT_STANDARD", ["FIRST_NAME", "LAST_NAME", "FULL_NAME", "EMAIL", "PHONE", "PASSWORD"], "Client courant", "profil")
    donnees.enregistrer_profil("DOSSIER_CREDIT", ["START_DATE", "CREDIT_DURATION", "END_DATE", "AMOUNT_HT", "VAT_RATE", "AMOUNT_TTC", "DOSSIER_REFERENCE"])
    return donnees


def test_definition_valeur_et_source_separees(ref, projet):
    d = (projet / "data" / "discovery")
    assert "Durand" not in (d / "variables.yaml").read_text("utf-8") and "Durand" in (d / "valeurs.yaml").read_text("utf-8")
    v = {x["cle"]: x for x in ref.variables()}
    assert set(v["END_DATE"]["dependances"]) == {"START_DATE", "CREDIT_DURATION"} and v["EMAIL"]["source"]["generateur"] == "email"
    assert v["API_BASE_URL"]["valeurs"]["environnements"] == {"INT": "https://int.exemple.test/api", "RECETTE": "https://recette.exemple.test/api"}
    # même définition, valeur selon l'environnement
    ref.choisir(environnement="INT")
    assert ref.obtenir("API_BASE_URL")["valeur"] == "https://int.exemple.test/api"
    ref.reinitialiser(tout=True)
    ref.choisir(environnement="RECETTE")
    assert ref.obtenir("API_BASE_URL")["valeur"] == "https://recette.exemple.test/api"
    assert [x["cle"] for x in ref.variables(type_="date")] == ["END_DATE", "START_DATE"]
    assert [x["cle"] for x in ref.variables(recherche="famille")] == ["LAST_NAME"]


def test_definitions_controlees(ref):
    with pytest.raises(ValueError, match="Clé technique"):
        ref.enregistrer_variable("prénom du client", {})
    with pytest.raises(ValueError, match="Type inconnu"):
        ref.enregistrer_variable("X", {"type": "iban"})
    with pytest.raises(ValueError, match="variables inconnues"):
        ref.enregistrer_variable("X", {"source": {"type": "calcul", "formule": "{{INCONNUE}}"}})
    with pytest.raises(ValueError, match="circulaire"):
        ref.enregistrer_variable("FIRST_NAME", {"source": {"type": "calcul", "formule": "{{FULL_NAME}}"}})
    with pytest.raises(ValueError, match="sert au calcul de : FULL_NAME"):
        ref.supprimer_variable("LAST_NAME")
    with pytest.raises(ValueError, match="supérieur au maximum"):
        ref.definir_valeur("CREDIT_DURATION", 999)
    c = ref.dupliquer_variable("EMAIL", "EMAIL_PRO")
    assert c["source"]["generateur"] == "email" and c["nom"].endswith("(copie)")
    ref.supprimer_variable("EMAIL_PRO")
    ref.dupliquer_profil("CLIENT_STANDARD", "CLIENT_PREMIUM")
    assert {p["nom"]: p["nature"] for p in ref.profils()} == {"CLIENT_PREMIUM": "profil", "CLIENT_STANDARD": "profil", "DOSSIER_CREDIT": "groupe"}
    assert [p["nom"] for p in ref.profils("groupe")] == ["DOSSIER_CREDIT"]
    ref.supprimer_variable("PHONE")
    assert "PHONE" not in ref.profils_dict()["CLIENT_STANDARD"]["variables"]  # retirée des profils


def test_generees_calculees_et_coherentes_dans_la_session(ref):
    debut = ref.obtenir("START_DATE")["valeur"]
    assert debut == (date.today() + timedelta(days=10)).strftime("%d/%m/%Y")
    fin = ref.obtenir("END_DATE")
    attendu = ref._mois(date.today() + timedelta(days=10), 12).strftime("%d/%m/%Y")
    assert (fin["valeur"], fin["origine"], fin["source"]) == (attendu, "calculée", "calcul date")
    ttc, ht = ref.obtenir("AMOUNT_TTC")["valeur"], ref.obtenir("AMOUNT_HT")["valeur"]
    assert 100 <= ht <= 500 and ttc == round(ht * 1.2, 2)
    nom = ref.obtenir("FULL_NAME")["valeur"]
    assert nom == f"{ref.obtenir('FIRST_NAME')['valeur']} Durand"
    mail, tel = ref.obtenir("EMAIL")["valeur"], ref.obtenir("PHONE")["valeur"]
    assert re.fullmatch(r"client\.[a-z0-9]{8}@exemple\.test", mail) and re.fullmatch(r"06\d{8}", tel)
    # mêmes valeurs à chaque demande : la session reste cohérente d'un écran à l'autre
    assert (ref.obtenir("EMAIL")["valeur"], ref.obtenir("AMOUNT_HT")["valeur"], ref.obtenir("FULL_NAME")["valeur"]) == (mail, ht, nom)
    c = {x["cle"]: x for x in ref.contexte()["valeurs"]}
    assert set(c["AMOUNT_TTC"]["dependances"]) == {"AMOUNT_HT", "VAT_RATE"} and c["VAT_RATE"]["origine"] == "référentiel"
    assert c["EMAIL"]["origine"] == "générée" and c["EMAIL"]["utilisations"] == 2
    # réinitialisation : les valeurs générées et calculées sont refaites, les valeurs réglées restent
    r = ref.reinitialiser()
    assert "EMAIL" in r["oubliees"] and "VAT_RATE" in r["gardees"] and ref.obtenir("EMAIL")["valeur"] != mail


def test_formule_arithmetique_seulement(ref):
    assert ref._evaluer("(100 + 20) * 2 / 3") == 80
    for refusee in ("__import__('os').system('x')", "open('f')", "a + 1", "2 ** 8"):
        with pytest.raises(ValueError):
            ref._evaluer(refusee)


def test_secret_jamais_ecrit_ni_renvoye(ref, projet):
    r = ref.definir_valeur("PASSWORD", "S3cret-de-test")
    assert r["valeur"] == "••••" and "mémoire" in r["lieu"]            # coffre désactivé dans les tests
    v = ref.obtenir("PASSWORD")
    assert v == {"cle": "PASSWORD", "valeur": "••••", "sensible": True, "saisie": "{{var:PASSWORD}}", "origine": "référentiel", "source": "coffre du poste"}
    assert ref.resoudre_saisie("{{var:PASSWORD}}", "id=mdp") == "S3cret-de-test"   # seul le serveur voit la valeur
    partout = "".join(f.read_text("utf-8") for f in projet.rglob("*") if f.is_file())
    assert "S3cret-de-test" not in partout and "••••" not in json.dumps(ref.historique())
    assert {x["cle"]: x["presente"] for x in ref.secrets_etat()} == {"PASSWORD": True}
    ref.definir_valeur("PASSWORD", "")
    ref.reinitialiser(tout=True)
    with pytest.raises(LookupError, match="secret absent du coffre"):
        ref.obtenir("PASSWORD")


def test_variable_de_session_relevee_pendant_le_parcours(ref):
    with pytest.raises(LookupError, match="pas encore été relevée"):
        ref.obtenir("DOSSIER_REFERENCE")
    with pytest.raises(ValueError, match="format"):
        ref.definir_contexte("DOSSIER_REFERENCE", "ABC")             # règles du catalogue appliquées
    ref.definir_contexte("DOSSIER_REFERENCE", "D-2026", "affichée sur l'écran de confirmation")
    assert ref.obtenir("DOSSIER_REFERENCE")["valeur"] == "D-2026"
    ref.definir_contexte("NUMERO_TICKET", "T-77")                     # hors catalogue : variable de la session seulement
    c = {x["cle"]: x for x in ref.contexte()["valeurs"]}
    assert c["NUMERO_TICKET"]["au_catalogue"] is False and c["NUMERO_TICKET"]["origine"] == "créée pendant la session"
    assert "NUMERO_TICKET" not in {x["cle"] for x in ref.variables()}


def test_besoins_d_un_ecran(ref):
    ref.choisir(profil="CLIENT_STANDARD")
    ref.definir_valeur("PASSWORD", "S3cret-de-test")
    r = ref.pour_champs([{"libelle": "Prénom"}, {"libelle": "Nom de famille"}, {"libelle": "Adresse e-mail", "type": "email"},
                         {"libelle": "Téléphone mobile"}, {"libelle": "Mot de passe", "type": "password"},
                         {"libelle": "Date de début"}, {"libelle": "Type de contrat"}], ecran="souscription")
    par = {x["champ"]: x for x in r["champs"]}
    assert (r["trouvees"], r["generees"], r["manquantes"]) == (6, 0, 1)
    assert par["Prénom"]["cle"] == "FIRST_NAME" and par["Nom de famille"]["valeur"] == "Durand"
    assert par["Adresse e-mail"]["type_attendu"] == "email" and par["Adresse e-mail"]["cle"] == "EMAIL"
    assert par["Téléphone mobile"]["cle"] == "PHONE" and par["Date de début"]["cle"] == "START_DATE"
    assert par["Mot de passe"]["valeur"] == "••••" and par["Mot de passe"]["saisie"] == "{{var:PASSWORD}}"
    manquant = par["Type de contrat"]
    assert manquant["statut"] == "manquante" and "Ne rien inventer" in manquant["consigne"] and "valeur" not in manquant
    actions = [(h["action"], h.get("champ")) for h in ref.historique()]
    assert ("manquante", "Type de contrat") in actions and ("générée", "Adresse e-mail") in actions
    # générateur autorisé par les réglages, pour les seuls types listés ; jamais pour un secret
    ref.regler("generer", ["texte", "iban"])
    assert ref.reglages() == {"sans_variable": "generer", "generateurs_autorises": ["texte"]}
    r = ref.pour_champs([{"libelle": "Type de contrat"}, {"libelle": "Code OTP"}, {"libelle": "Quantité"}])
    assert [x["statut"] for x in r["champs"]] == ["générée", "manquante", "manquante"]
    auto = r["champs"][0]
    assert auto["cle"] == "AUTO_TYPE_DE_CONTRAT" and ref.pour_champs([{"libelle": "Type de contrat"}])["champs"][0]["valeur"] == auto["valeur"]


def test_preparation_et_sources(ref, projet):
    p = ref.preparer("DOSSIER_CREDIT")
    assert p["pret"] and {x["cle"] for x in p["pretes"]} == set(ref.profils_dict()["DOSSIER_CREDIT"]["variables"])
    assert ref.contexte()["valeurs"] == []                             # l'essai ne touche pas au contexte
    p = ref.preparer("CLIENT_STANDARD")
    assert not p["pret"] and [x["cle"] for x in p["bloquees"]] == ["PASSWORD"]
    (projet / "data" / "clients.csv").write_text("code;ville\nA1;Lyon\nB2;Nantes\n", "utf-8")
    ref.enregistrer_variable("CUSTOMER_CODE", {"nom": "Code client"})
    ref.definir_valeur("CUSTOMER_CODE", "B2")
    ref.enregistrer_variable("CITY", {"nom": "Ville", "source": {"type": "fichier", "fichier": "data/clients.csv", "colonne": "ville",
                                                                 "filtre": {"code": "{{CUSTOMER_CODE}}"}}})
    assert ref.obtenir("CITY") | {"saisie": ""} == {"cle": "CITY", "valeur": "Nantes", "sensible": False, "saisie": "", "origine": "source externe",
                                                    "source": "fichier data/clients.csv"}
    ref.enregistrer_variable("HORS_PROJET", {"source": {"type": "fichier", "fichier": "../../etc/passwd", "colonne": "x"}})
    with pytest.raises(ValueError, match="hors du projet"):
        ref.obtenir("HORS_PROJET")
    assert {"type": "fichier", "reference": "data/clients.csv", "variables": ["CITY"]} in ref.sources_externes()["utilisees"]
    assert ref.dependances()["liens"][0].keys() == {"variable", "depend_de", "source"} and ref.vue()["variables"] == 17


def test_outils_mcp_et_saisie_par_reference(ref, monkeypatch):
    from atelier.adapters import facade
    from atelier.discovery import actions, apprentissage

    cat = facade.discovery_donnees_catalogue(profil="CLIENT_STANDARD")
    assert {v["cle"] for v in cat["variables"]} == set(ref.profils_dict()["CLIENT_STANDARD"]["variables"])
    assert "valeurs" not in cat["variables"][0] and cat["reglages"]["sans_variable"] == "signaler"
    assert facade.discovery_donnees_contexte(profil="CLIENT_STANDARD")["profil"] == "CLIENT_STANDARD"
    ref.definir_valeur("PASSWORD", "S3cret-de-test")
    assert facade.discovery_donnee("password")["valeur"] == "••••"
    assert facade.discovery_donnee_definir("dossier_reference", "D-0042")["valeur"] == "D-0042"
    r = facade.discovery_donnees_pour_champs([{"libelle": "Référence du dossier"}])
    assert r["champs"][0]["valeur"] == "D-0042"
    saisies, publies = [], []
    monkeypatch.setattr(apprentissage, "action_mcp", lambda nom, locator, fn: fn())
    monkeypatch.setattr(actions.session, "montrer_cible", lambda *a: None)
    monkeypatch.setattr(actions.session, "is_web", lambda: True)
    monkeypatch.setattr(actions.session, "webb", lambda: type("W", (), {"fill": lambda self, l, t, c: saisies.append(t)})())
    monkeypatch.setattr(actions, "avec_carte", lambda ev, fn: fn())
    monkeypatch.setattr(actions.session, "action_faite", lambda nom, args: publies.append(args["text"]))
    retour = facade.type_text("id=mdp", "{{var:PASSWORD}}")
    assert saisies == ["S3cret-de-test"] and publies == ["{{var:PASSWORD}}"] and "S3cret" not in retour
    assert ref.historique()[0] | {"date": ""} == {"date": "", "action": "saisie", "cle": "PASSWORD", "session": "hors-session", "champ": "id=mdp",
                                                 "origine": "référentiel"}


def test_profil_de_la_session_discovery(ref, monkeypatch):
    from atelier.discovery import sessions_discovery

    monkeypatch.setattr(sessions_discovery, "active", lambda: {"id": "DS-1", "config": {"environnement": "RECETTE", "profil_donnees": "CLIENT_STANDARD"}})
    assert ref.contexte() | {"ouvert": "", "valeurs": []} == {"session": "DS-1", "environnement": "RECETTE", "profil": "CLIENT_STANDARD", "ouvert": "",
                                                            "valeurs": [], "variables_du_profil": ref.profils_dict()["CLIENT_STANDARD"]["variables"]}
    assert ref.obtenir("API_BASE_URL")["valeur"] == "https://recette.exemple.test/api"
    assert ref.resoudre_saisie("valeur inventée", "id=champ") == "valeur inventée"      # saisie littérale : laissée, mais tracée
    assert ref.historique()[0]["action"] == "hors référentiel" and ref.historique(session="DS-1")
    monkeypatch.setattr(sessions_discovery, "active", lambda: {"id": "DS-2", "config": {"environnement": "INT"}})
    assert ref.obtenir("API_BASE_URL")["valeur"] == "https://int.exemple.test/api"          # contexte indépendant par session
    with pytest.raises(ValueError, match="Profil de données inconnu"):
        sessions_discovery._profil_donnees("INEXISTANT")


def test_routes_web(ref):
    from fastapi.testclient import TestClient

    from web_app_loader import charger_app_web

    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/").status_code == 200
    post = lambda a, b: c.post(f"/api/discovery/donnees/{a}", json=b)  # noqa: E731
    assert post("variable", {"cle": "PROMO_CODE", "champs": {"nom": "Code promo", "regles": {"longueur_max": 8}}}).json()["cle"] == "PROMO_CODE"
    assert post("valeur", {"cle": "PROMO_CODE", "valeur": "BIENVENUE-2026"}).status_code == 400          # règle de longueur
    assert post("valeur", {"cle": "PROMO_CODE", "valeur": "ETE26"}).status_code == 200
    assert post("valeur", {"cle": "PASSWORD", "valeur": "S3cret-de-test"}).json()["valeur"] == "••••"
    assert post("profil", {"nom": "TEST_ECOMMERCE", "variables": ["EMAIL", "PROMO_CODE"], "nature": "groupe"}).status_code == 200
    assert post("contexte", {"profil": "TEST_ECOMMERCE", "env": "RECETTE"}).json()["profil"] == "TEST_ECOMMERCE"
    assert post("preparer", {"profil": "TEST_ECOMMERCE"}).json()["pret"] is True
    assert post("obtenir", {"cle": "PROMO_CODE"}).json()["valeur"] == "ETE26"
    assert len(post("generer", {"source": {"generateur": "motif", "motif": "AA-####"}}).json()["exemples"]) == 3
    assert post("inconnue", {}).status_code == 404
    d = c.get("/api/discovery/donnees").json()
    assert d["vue"]["variables"] == 15 and d["contexte"]["profil"] == "TEST_ECOMMERCE" and "S3cret-de-test" not in json.dumps(d)
    assert {x["cle"] for x in d["contexte"]["valeurs"]} == {"PROMO_CODE"} and d["historique"][0]["action"] == "obtenue"
    assert post("reinitialiser", {"tout": True}).json()["oubliees"] == ["PROMO_CODE"]
    assert post("supprimer-variable", {"cle": "PROMO_CODE"}).status_code == 200
