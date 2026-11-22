"""Knowledge Graph, lot 1 : confiance des relations, actions utilisateur en nœuds, tests BDD et ponts, complétude des parcours."""


def _el(cle, libelle, type_="lien"):
    return {"key": cle, "type": type_, "libelle": libelle, "locators": [f"id={cle}"]}


def _projet(projet, monkeypatch):
    for v in ("XRAY_CLIENT_ID", "JIRA_BASE_URL"):
        monkeypatch.delenv(v, raising=False)
    from atelier.discovery import carte, parcours_utilisateur as pu

    carte.creer_app("Site Démo", ["web"], web={"url": "https://demo.exemple.test"}, type_="web")
    u = "https://demo.exemple.test"
    acc = carte.observer([_el("lien_connexion", "Connexion")], "web", u + "/")
    con = carte.observer([_el("champ_email", "E-mail", "champ")], "web", u + "/connexion")
    carte.renommer(acc["id"], "accueil", "Vitrine")
    carte.renommer(con["id"], "connexion", "Compte")
    carte.enregistrer_transition(acc["id"], con["id"], "web", {"type": "tap", "cle": "lien_connexion", "libelle": "Connexion"})
    vide = pu.enregistrer("", {"nom": "Demande de démo"})          # préparé, jamais déroulé
    return acc, con, vide


def test_action_utilisateur_est_un_noeud(projet, monkeypatch):
    from atelier.discovery import connaissance

    _projet(projet, monkeypatch)
    connaissance.vider_cache()
    g = connaissance.construire()
    a = g.noeuds["action:accueil.lien_connexion"]
    assert a.type == "action" and a.libelle == "Connexion" and a.plateformes == ["web"]
    types = {(r.de, r.type, r.vers) for r in g.relations.values()}
    assert ("ecran:accueil", "permet", a.id) in types and (a.id, "aboutit_a", "ecran:connexion") in types
    assert ("ecran:accueil", "navigue_vers", "ecran:connexion") in types        # compatibilité : la transition reste


def test_parcours_declare_sans_ecran_existe(projet, monkeypatch):
    from atelier.discovery import connaissance

    _, _, vide = _projet(projet, monkeypatch)
    connaissance.vider_cache()
    g = connaissance.construire()
    p = g.noeuds[vide["noeud"]]
    assert p.type == "parcours" and p.proprietes["completude"] == "déclaré"


def test_test_bdd_dans_le_graphe_et_ponts(projet, monkeypatch):
    from atelier.discovery import connaissance
    from atelier.generation import bdd, parcours_bdd

    acc, con, vide = _projet(projet, monkeypatch)
    r = parcours_bdd.brouillon([acc["id"], con["id"]], titre="Aller à la connexion")
    m = bdd.charger(r["cle"])
    m["parcours"] = vide["noeud"]
    bdd.sauver(m)
    (projet / "tests").mkdir()
    (projet / "tests" / "c.robot").write_text(f"*** Test Cases ***\nAller à la connexion\n    [Tags]    {r['cle']}\n    Log    x\n", "utf-8")
    connaissance.vider_cache()
    g = connaissance.construire()
    sid = f"scenario:{r['cle']}"
    assert g.noeuds[sid].type == "scenario" and g.noeuds[sid].proprietes["automatise"]
    rel = {(x.de, x.type, x.vers) for x in g.relations.values()}
    assert (sid, "couvre", "ecran:accueil") in rel and (sid, "couvre", "ecran:connexion") in rel
    assert (sid, "verifie", vide["noeud"]) in rel
    assert any(t == "implemente_par" and d == sid and v.startswith("test_robot:") for d, t, v in rel)


def test_confiance_des_relations():
    from atelier.domain.graphe import Relation

    assert Relation("a", "b", "contient").confiance_niveau == "confirmée"
    assert Relation("a", "b", "mene_a", provenance="déduit", proprietes={"calcul": True}).confiance_niveau == "probable"
    assert Relation("a", "b", "verifie", provenance="déduit", statut="à valider").confiance_niveau == "non vérifiée"
    assert Relation("a", "b", "verifie", provenance="déduit").confiance_niveau == "confirmée"   # déduite puis validée par un humain
    assert Relation("a", "b", "contient").vers_dict()["confiance_niveau"] == "confirmée"


def test_completude():
    from atelier.discovery import connaissance
    from atelier.domain.graphe import Graphe

    g = Graphe("t")
    for i, t in [("parcours:p", "parcours"), ("ecran:x", "ecran"), ("ecran:y", "ecran"), ("scenario:s", "scenario")]:
        g.noeud(i, t, i)
    assert connaissance.completude_parcours(g, "parcours:p") == "déclaré"
    g.relier("parcours:p", "ecran:x", "contient", provenance="déduit", statut="à valider")
    assert connaissance.completude_parcours(g, "parcours:p") == "découvert"
    g.relier("parcours:p", "ecran:y", "contient")
    assert connaissance.completude_parcours(g, "parcours:p") == "partiellement exploré"
    g.relations["parcours:p|contient|ecran:x"].statut = "validé"
    assert connaissance.completude_parcours(g, "parcours:p") == "exploré"
    g.relier("scenario:s", "parcours:p", "verifie")
    assert connaissance.completude_parcours(g, "parcours:p") == "confirmé"
