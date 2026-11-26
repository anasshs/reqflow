"""Le chemin de l'utilisateur (Découvrir → Concevoir le test → Automatiser → Exécuter) : la prochaine action suit
l'état réel des objets, sans Jira ni Xray."""
import pytest


def _el(cle, libelle, type_="bouton"):
    return {"key": cle, "type": type_, "libelle": libelle, "locators": [f"id={cle}"]}


@pytest.fixture
def sans_integrations(monkeypatch):
    for v in ("XRAY_CLIENT_ID", "XRAY_CLIENT_SECRET", "JIRA_BASE_URL"):
        monkeypatch.delenv(v, raising=False)


def test_projet_vide_sans_application(projet, sans_integrations):
    from atelier.intelligence import chemin

    e = chemin.etat()
    assert [x["id"] for x in e["etapes"]] == ["decouvrir", "concevoir", "automatiser", "executer"]
    assert e["suivante"]["bouton"] == "Déclarer l'application" and e["etapes"][0]["courante"]
    assert e["integrations"] == {"xray": False, "jira": False, "xray_configure": False, "jira_configure": False}


def test_du_parcours_au_script_la_prochaine_action_avance(projet, sans_integrations):
    from atelier.discovery import carte, parcours_utilisateur as pu
    from atelier.generation import bdd, parcours_bdd
    from atelier.intelligence import chemin

    carte.creer_app("Boutique", ["web"], web={"url": "https://recette.exemple.fr"}, type_="web")
    assert chemin.etat()["suivante"]["bouton"] == "Découvrir un parcours"

    p = pu.enregistrer("", {"nom": "Accueil vers connexion"})
    assert p["plateforme"] == "web"  # seule plateforme de l'application : rien à choisir avant de dérouler
    s = chemin.etat()["suivante"]
    assert s["bouton"] == "Dérouler le parcours" and s["lien"] == f"#discovery/cadrage/{p['id']}"

    u = "https://recette.exemple.fr"
    acc = carte.observer([_el("lien_connexion", "Connexion", "lien")], "web", u + "/")
    con = carte.observer([_el("champ_login", "Identifiant", "champ"), _el("bouton_valider", "Se connecter")], "web", u + "/connexion")
    carte.enregistrer_transition(acc["id"], con["id"], "web", {"type": "tap", "cle": "lien_connexion", "libelle": "Connexion"})
    r = parcours_bdd.brouillon([acc["id"], con["id"]], titre="Aller à la connexion")
    s = chemin.etat()["suivante"]
    assert (s["etape"], s["bouton"], s["lien"]) == ("concevoir", "Relire le test BDD", f"#bdd/{r['cle']}")

    m = bdd.charger(r["cle"])
    for sc in m["scenarios"]:
        for e in sc["etapes"]:
            e["valide"] = True
    m["statut"] = "validé"
    bdd.sauver(m)
    assert chemin.etat()["suivante"]["bouton"] == "Générer le script Robot"

    g = bdd.generer_robot(bdd.charger(r["cle"]))
    from atelier.domain import projet as pj

    f = pj.safe_path(g["chemin"])
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(g["contenu"], "utf-8")
    from atelier.generation import pom

    pom.ecrire(g["pages"])  # Page Object Model : les keywords à implémenter sont dans les pages
    e = chemin.etat()
    assert (e["suivante"]["etape"], e["suivante"]["bouton"]) == ("automatiser", "Construire avec Cursor")
    assert e["suivante"]["lien"] == f"#studio/direct/{r['cle']}" and e["etapes"][2]["courante"]
    assert "1 à construire" in e["etapes"][2]["detail"]


def test_integrations_suivent_la_configuration(projet, monkeypatch):
    from atelier.intelligence import chemin

    monkeypatch.setenv("XRAY_CLIENT_ID", "id-factice")
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    i = chemin.integrations()
    assert i["xray"] and i["xray_configure"] and not i["jira"]


def test_cadrage_dans_le_brouillon_et_alerte_production(projet, sans_integrations):
    """Objectif, point de départ et résultat attendu saisis au cadrage passent dans le test BDD ; la production est signalée."""
    from atelier.discovery import carte, graphe_texte, parcours_utilisateur as pu
    from atelier.generation import parcours_bdd

    carte.creer_app("Boutique", ["web"], web={"url": "https://recette.exemple.fr"}, type_="web")
    p = pu.enregistrer("", {"nom": "Authentification", "objectif": "Ouvrir la connexion", "point_depart": "Accueil",
                            "resultat_attendu": "Formulaire de connexion affiché", "environnement": "Prod", "pilote": "cursor"})
    assert any("production" in a and "Cursor navigue seul" in a for a in p["controles"]["avertissements"])
    assert not any("production" in a for a in pu.enregistrer(p["id"], {"environnement": "recette"})["controles"]["avertissements"])

    u = "https://recette.exemple.fr"
    acc = carte.observer([_el("lien_connexion", "Connexion", "lien")], "web", u + "/")
    con = carte.observer([_el("champ_login", "Identifiant", "champ")], "web", u + "/connexion")
    carte.enregistrer_transition(acc["id"], con["id"], "web", {"type": "tap", "cle": "lien_connexion", "libelle": "Connexion"})
    assert parcours_bdd.cadrage_source(p["noeud"])["id"] == p["id"]
    r = parcours_bdd.brouillon([acc["id"], con["id"]], titre="sans cadrage")
    assert "résultat attendu" not in r["gherkin"]  # chemin de la carte : aucun cadrage
    import pytest as _pytest

    with _pytest.MonkeyPatch.context() as mp:  # écrans du parcours (validés dans le Knowledge Graph en vrai)
        mp.setattr(parcours_bdd, "ecrans_du_parcours", lambda nid: [acc["id"], con["id"]])
        r = parcours_bdd.brouillon(parcours=p["noeud"], titre="Authentification")
    assert "Alors le résultat attendu est obtenu : Formulaire de connexion affiché" in r["gherkin"]
    assert "Objectif : Ouvrir la connexion" in r["gherkin"] and "Point de départ : Accueil" in r["gherkin"]

    assert graphe_texte.principal([]) == 0
    assert graphe_texte.principal([p["noeud"], "1"]) == 0
    assert graphe_texte.principal(["parcours:inconnu"]) == 1


def test_revue_sans_xray_n_exige_pas_de_cle(projet, sans_integrations):
    """Sans Xray, l'approbation n'est pas bloquée par l'absence de clé : l'identifiant du test BDD en tag suffit."""
    from atelier.generation import bdd, studio

    bdd.creer("authentification", "Authentification")
    (projet / "tests").mkdir()
    (projet / "tests" / "auth.robot").write_text("*** Test Cases ***\nAuthentification\n    [Tags]    authentification\n    Log    ok\n", "utf-8")
    c = {x["code"]: x for x in studio.controles_script("tests/auth.robot")}
    assert "xray" not in c and c["identifiant"]["gravite"] == "ok"
    assert not [x for x in c.values() if x["gravite"] == "haute"]
