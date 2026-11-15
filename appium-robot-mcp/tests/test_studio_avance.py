"""Automation Studio, compléments du cahier : rôles, blocs SI / POUR / ESSAYER, étape isolée, secours utilisés et
correction assistée, factorisation des keywords, import CSV / JSON et API de préparation, tendance."""
import json
import shutil
from pathlib import Path

import pytest

from tests.conftest import pointer_projet

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"


@pytest.fixture
def demo(tmp_path, monkeypatch):
    d = tmp_path / "demo"
    shutil.copytree(DEMO, d, ignore=shutil.ignore_patterns("results", "connaissance", "studio", "executions"))
    pointer_projet(d, monkeypatch)
    return d


# --------------------------------------------------------------------------- rôles
def test_roles_mode_ouvert_puis_droits_et_quatre_yeux(demo, monkeypatch):
    from atelier.domain import roles
    from atelier.generation import studio

    moi = roles.utilisateur()
    assert not roles.actifs() and roles.peut("decider_revue")
    with pytest.raises(ValueError, match="responsable"):
        roles.definir({moi: "automaticien"})  # on ne s'enferme pas dehors
    roles.definir({moi: "responsable", "b.relecteur": "relecteur"})
    f = "tests/connexion.robot"
    studio.transition_script(f, "soumettre")
    with pytest.raises(PermissionError, match="Quatre yeux"):
        studio.transition_script(f, "approuver")  # soumis et approuvé par la même personne
    monkeypatch.setattr(roles, "utilisateur", lambda: "b.relecteur")
    assert studio.transition_script(f, "approuver")["statut"] == "Approved"
    monkeypatch.setattr(roles, "utilisateur", lambda: "c.inconnu")  # absent de la liste : lecteur
    with pytest.raises(PermissionError, match="lecteur"):
        studio.transition_script(f, "publier")
    with pytest.raises(PermissionError):
        roles.definir({"c.inconnu": "responsable"})


# --------------------------------------------------------------------------- builder
def test_builder_blocs_si_pour_essayer(demo):
    from atelier.generation import studio

    etapes = [{"mot": "Given", "keyword": "je suis sur la page de connexion"},
              {"type": "si", "condition": "'${DONNEES.identifiant}' != ''"},
              {"mot": "When", "keyword": "je me connecte avec le jeu de données"},
              {"type": "sinon"}, {"mot": "When", "keyword": "je valide sans remplir les champs"}, {"type": "fin"},
              {"type": "pour", "variable": "${i}", "liste": "RANGE 2"},
              {"type": "essayer"}, {"mot": "Then", "keyword": "le message d'erreur attendu s'affiche"}, {"type": "echec", "motif": "*introuvable*"},
              {"mot": "And", "keyword": "je suis sur la page de connexion"}, {"type": "fin"}, {"type": "fin"}]
    c = studio.construire_test("Connexion conditionnelle", "DEMO-301", "CLIENT_ACTIF", etapes)
    corps = c["contenu"].split("# SCÉNARIO")[1]
    assert "    IF    '${DONNEES.identifiant}' != ''\n        When je me connecte avec le jeu de données\n    ELSE\n        When je valide" in corps
    assert "    FOR    ${i}    IN RANGE    2\n        TRY\n            Then le message d'erreur attendu s'affiche\n        EXCEPT    *introuvable*" in corps
    assert corps.rstrip().endswith("    END\n    END") and c["lint"]["ok"], c["lint"]
    with pytest.raises(ValueError, match="non fermé"):
        studio.construire_test("X", "", "CLIENT_ACTIF", [{"type": "si", "condition": "1"}, {"keyword": "je suis sur la page de connexion"}])
    with pytest.raises(ValueError, match="sans SI"):
        studio.construire_test("X", "", "CLIENT_ACTIF", [{"keyword": "je suis sur la page de connexion"}, {"type": "sinon"}])
    with pytest.raises(ValueError, match="une seule ligne"):
        studio.construire_test("X", "", "CLIENT_ACTIF", [{"type": "si", "condition": "1\n    Log    injection"}, {"keyword": "je suis sur la page de connexion"}, {"type": "fin"}])


def test_etape_isolee_suite_temporaire_hors_depot(demo):
    from atelier.generation import studio_avance

    e = studio_avance.preparer_etape("je me connecte avec le jeu de données", "CLIENT_ACTIF")
    assert e["cible"].startswith("results/builder/")
    txt = (demo / e["cible"]).read_text("utf-8")
    assert "Resource    ../../../resources/socle/connexion.resource" in txt and "Test Teardown    Terminer Le Test" in txt
    assert "    Initialiser Le Test    &{JDD_CLIENT_ACTIF}\n    je me connecte avec le jeu de données" in txt
    with pytest.raises(ValueError, match="absent"):
        studio_avance.preparer_etape("Keyword Inexistant", "CLIENT_ACTIF")


# --------------------------------------------------------------------------- locators
def test_secours_utilise_et_correction_appliquee(demo):
    from atelier.generation import studio, studio_avance

    run = demo / "results" / "runs" / "RUN-20261115-100000"
    run.mkdir(parents=True)
    (run / "output.xml").write_text('<robot><msg level="WARN">Sélecteur de secours utilisé : css=[data-testid=&quot;login&quot;] '
                                    '(principal introuvable : id=bouton_connexion)</msg></robot>', "utf-8")
    assert studio_avance.secours_utilises()["id=bouton_connexion"][0]["secours"] == 'css=[data-testid="login"]'
    p = next(x for x in studio_avance.propositions_correction() if x["id"] == "connexion.bouton_connexion@web")
    assert p["proposition"] == 'css=[data-testid="login"]' and "secours utilisé" in p["source"]
    r = studio_avance.appliquer_correction(p["id"], "data-testid=login")
    assert r["avant"] == "id=bouton_connexion" and r["apres"] == "data-testid=login"
    txt = (demo / "resources/locators/connexion.resource").read_text("utf-8")
    assert "bouton_connexion=data-testid=login" in txt and "champ_identifiant=id=identifiant" in txt
    assert next(l for l in studio.locators() if l["id"] == "connexion.bouton_connexion@web")["valeur"] == "data-testid=login"
    with pytest.raises(ValueError, match="double espace"):
        studio_avance.appliquer_correction(p["id"], "a    b")


# --------------------------------------------------------------------------- keywords
def test_factorisation_corps_identique(demo):
    from atelier.generation import studio, studio_avance

    socle = demo / "resources/socle/connexion.resource"
    socle.write_text(socle.read_text("utf-8") + "\nje clique sur se connecter\n    Cliquer Sur    ${LOC_CONNEXION_WEB.bouton_connexion}\n", "utf-8")
    suite = demo / "tests/connexion.robot"
    suite.write_text(suite.read_text("utf-8").replace("When je valide sans remplir les champs", "When je clique sur se connecter"), "utf-8")
    g = next(x for x in studio_avance.propositions_factorisation() if x["raison"] == "corps identique")
    noms = {g["garder"]["nom"], *[r["nom"] for r in g["remplacer"]]}
    assert noms == {"je valide sans remplir les champs", "je clique sur se connecter"} and g["applicable"]
    r = studio_avance.appliquer_factorisation(g["id"])
    restant = g["garder"]["nom"]
    retire = next(n for n in noms if n != restant)
    assert retire not in socle.read_text("utf-8").split("*** Keywords ***")[1].splitlines()
    assert f"When {restant}" in suite.read_text("utf-8") and f"When {retire}" not in suite.read_text("utf-8")
    assert r["fichiers"] and not [k for k in studio.keywords() if k["nom"] == retire]


# --------------------------------------------------------------------------- données
def test_import_csv_json_controle(demo):
    from atelier.execution import jdd

    csv = "jeu;description;identifiant;mot_de_passe\nCLIENT_PRO;Client pro;pro.demo;{{env:MDP_PRO}}\nCLIENT_ACTIF;doublon;x;{{env:MDP}}\n"
    a = jdd.importer("recette", csv, "csv")
    assert a["nouveaux"] == ["CLIENT_PRO"] and any("CLIENT_ACTIF" in e and "remplacer" in e for e in a["erreurs"]) and not a["ecrit"]
    r = jdd.importer("recette", csv.replace("CLIENT_ACTIF;doublon", "CLIENT_PME;pme"), "csv", ecrire=True)
    assert r["ecrit"] and jdd.lire("recette", "CLIENT_PRO")["donnees"] == {"identifiant": "pro.demo", "mot_de_passe": "{{env:MDP_PRO}}"}
    assert jdd.lire("recette", "CLIENT_ACTIF")["donnees"]["identifiant"] == "client.demo"  # jeux existants conservés
    mauvais = jdd.importer("recette", json.dumps({"client_x": {"donnees": {"Token": "abc123"}}}), "json")
    assert len(mauvais["erreurs"]) == 3  # nom de jeu, nom de champ, secret en clair
    with pytest.raises(ValueError, match="jeu"):
        jdd.importer("recette", "a;b\n1;2\n", "csv")


def test_api_de_preparation_declaree(demo, monkeypatch):
    from atelier.execution import jdd

    monkeypatch.setenv("API_RECETTE_URL", "https://api.recette.exemple")
    monkeypatch.setenv("API_RECETTE_JETON", "jeton-secret")
    (demo / "data/jdd/api.yaml").write_text("""CREER_CLIENT:
  description: Crée un client de test
  methode: POST
  url: "{{env:API_RECETTE_URL}}/clients/{segment}"
  entetes: {Authorization: "Bearer {{env:API_RECETTE_JETON}}"}
  corps: {type: particulier}
  environnements: [recette]
  extraire: {identifiant: data.login, mot_de_passe: data.secret}
""", "utf-8")
    (demo / "data/jdd/recette.yaml").write_text((demo / "data/jdd/recette.yaml").read_text("utf-8") + """
CLIENT_CREE:
  prerequis:
    - api: CREER_CLIENT
      params: {segment: pro}
  donnees:
    identifiant: "{{api:CREER_CLIENT.identifiant}}"
""", "utf-8")
    appels = []

    def faux_http(m, url, data, entetes, delai):
        appels.append((m, url, json.loads(data), entetes["Authorization"]))
        return json.dumps({"data": {"login": "auto.123", "secret": "s3cr3t"}})

    monkeypatch.setattr("atelier.integrations.http.http", faux_http)
    r = jdd.resoudre("recette", ["CLIENT_CREE"])
    assert r["jeux"]["CLIENT_CREE"] == {"identifiant": "auto.123"} and not r["bloques"]
    assert appels == [("POST", "https://api.recette.exemple/clients/pro", {"type": "particulier"}, "Bearer jeton-secret")]
    t = jdd.tester_api("recette", "CREER_CLIENT", http_fn=faux_http)
    assert t["valeurs"]["mot_de_passe"] == "•••" and t["valeurs"]["identifiant"] == "auto.123"
    with pytest.raises(PermissionError, match="production"):
        jdd.appeler_api("production", "CREER_CLIENT", http_fn=faux_http)
    with pytest.raises(PermissionError, match="non autorisé"):
        jdd.appeler_api("integration", "CREER_CLIENT", http_fn=faux_http)
    monkeypatch.setenv("API_RECETTE_URL", "http://api.recette.exemple")
    with pytest.raises(PermissionError, match="HTTPS"):
        jdd.appeler_api("recette", "CREER_CLIENT", http_fn=faux_http)


# --------------------------------------------------------------------------- tendance
def test_tendance_un_releve_par_jour(demo):
    from atelier.generation import studio, studio_avance

    v = studio.vue_ensemble()
    studio.vue_ensemble()
    t = studio_avance.tendance()
    assert len(t) == 1 and t[0]["tests_automatises"] == v["kpi"]["tests_automatises"] and v["roles"]["actifs"] is False
    f = demo / "studio" / "tendance.jsonl"
    f.write_text(json.dumps({"jour": "2026-11-01", "tests_automatises": 3}) + "\n" + f.read_text("utf-8"), "utf-8")
    assert [x["jour"] for x in studio.vue_ensemble()["tendance"]][0] == "2026-11-01"


# --------------------------------------------------------------------------- Cursor construit, l'automaticien valide
def test_cursor_construit_et_soumet_sans_pouvoir_approuver(demo):
    from atelier.adapters import facade
    from atelier.generation import studio

    socle = facade.studio_socle()
    assert any(k["nom"] == "je me connecte avec le jeu de données" for k in socle["keywords"]) and socle["environnement"] == "recette"
    apercu = facade.studio_construire_test("Connexion par Cursor", "CLIENT_ACTIF", [{"mot": "Given", "keyword": "je suis sur la page de connexion"},
                                                                                    {"mot": "When", "keyword": "je me connecte avec le jeu de données"}], "DEMO-301")
    assert apercu["lint"]["ok"] and "ecrit" not in apercu and not (demo / apercu["fichier"]).exists()
    c = facade.studio_construire_test("Connexion par Cursor", "CLIENT_ACTIF", [{"mot": "Given", "keyword": "je suis sur la page de connexion"}], "DEMO-301", ecrire=True)
    f = c["fichier"]
    r = studio.revue_script(f)
    assert r["statut"] == "Generated" and "généré (cursor)" in r["historique"][-1]["commentaire"]
    assert facade.studio_soumettre_revue(f)["statut"] == "Technical Review"
    assert facade.studio_revue(f)["statut"] == "Technical Review"
    noms = {o.__name__ for o in facade.OUTILS}
    assert not {n for n in noms if any(m in n for m in ("approuver", "publier", "refuser"))}  # décisions humaines uniquement


def test_suite_ecrite_par_l_agent_entre_en_revue(demo):
    from atelier.adapters import facade
    from atelier.generation import studio

    facade.write_project_file("tests/ecrite_par_cursor.robot", "*** Test Cases ***\nT\n    Log    x\n")
    facade.write_project_file("resources/socle/notes.resource", "*** Keywords ***\nK\n    Log    x\n")
    rev = studio.revues_scripts()
    assert rev["tests/ecrite_par_cursor.robot"]["statut"] == "Generated" and "resources/socle/notes.resource" not in rev


# --------------------------------------------------------------------------- Cursor en direct
def test_activite_agent_masque_les_secrets():
    from atelier.domain import activite_agent as a

    r = a.resumer_arguments("type_text", {"key": "champ_mot_de_passe", "text": "Demo#2026"})
    assert r == {"key": "champ_mot_de_passe", "text": "•••"}
    assert a.resumer_arguments("write_project_file", {"path": "tests/x.robot", "content": "x" * 900}) == {"path": "tests/x.robot", "content": "900 caractères"}
    assert a.resumer_arguments("studio_socle", {"jeton_api": "abc"})["jeton_api"] == "•••"
    assert a.famille("tap") == "ecran" and a.famille("studio_construire_test") == "ecriture" and a.famille("studio_socle") == "lecture"


def test_chaque_appel_mcp_est_publie_debut_et_fin():
    pytest.importorskip("mcp")
    from atelier.adapters.mcp import server
    from atelier.domain import evenements

    recus = []
    evenements.abonner(recus.append, {"mcp_outil"})

    def type_text(key: str, text: str) -> dict:
        return {"statut": "saisi"}

    def tap(key: str) -> dict:
        raise RuntimeError("élément introuvable")

    server._suivre_projet(type_text)("champ_mdp", "secret!")
    with pytest.raises(RuntimeError):
        server._suivre_projet(tap)("bouton")
    assert [(e["nom"], e["etat"]) for e in recus] == [("type_text", "debut"), ("type_text", "fin"), ("tap", "debut"), ("tap", "erreur")]
    assert recus[0]["args"] == {"key": "champ_mdp", "text": "•••"} and "secret!" not in json.dumps(recus)
    assert recus[1]["resultat"] == "statut : saisi" and "introuvable" in recus[3]["message"]


def test_image_du_navigateur_de_l_agent_et_activite(projet, monkeypatch, tmp_path):
    pytest.importorskip("fastapi")
    import base64

    from fastapi.testclient import TestClient
    from web_app_loader import charger_app_web, module_web

    web = module_web()
    monkeypatch.setattr(web, "CONFIG_PATH", tmp_path / "atelier.json")
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    c.get("/")
    png = base64.b64encode(b"\x89PNG-image-de-test").decode()
    assert c.post("/api/mcp/image", json={"png": png, "outil": "open_url"}).status_code == 401  # jeton des processus exigé
    h = {"X-Atelier-Jeton": web.JETON_PROCESSUS}
    assert c.post("/api/events", json={"source": "mcp", "type": "session", "etat": "ouverte", "platform": "web"}, headers=h).status_code == 200
    assert c.post("/api/events", json={"source": "mcp", "type": "mcp_outil", "nom": "open_url", "etat": "fin", "famille": "ecran"}, headers=h).status_code == 200
    assert c.post("/api/mcp/image", json={"png": png, "outil": "open_url"}, headers=h).status_code == 200
    a = c.get("/api/mcp/activite").json()
    assert a["actif"] and a["evenements"][-1]["nom"] == "open_url" and a["image_agent"]["outil"] == "open_url"
    assert c.get("/api/frame.png").content == b"\x89PNG-image-de-test"  # navigateur piloté dans le processus MCP


def test_cursor_corrige_un_locator_et_les_suites_repassent_en_revue(demo):
    from atelier.adapters import facade
    from atelier.generation import studio

    f = "tests/connexion.robot"
    studio.transition_script(f, "soumettre")
    studio.transition_script(f, "approuver")
    assert studio.revue_script(f)["statut"] == "Approved"
    r = facade.studio_corriger_locator("connexion.bouton_connexion@web", "data-testid=login")
    assert r["suites_en_revue"] == [f] and studio.revue_script(f)["statut"] == "Technical Review"  # le fichier de la suite n'a pas changé
    j = next(x for x in studio.journal() if x["op"] == "correction_locator")
    assert j["origine"] == "cursor"
