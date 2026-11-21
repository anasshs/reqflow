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
