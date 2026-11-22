"""Knowledge Graph, finitions : relecture ciblée des fichiers, écart entre deux constructions, filtre par version,
détail d'un élément (provenance, traçabilité), filtres proposés."""


def _el(cle, libelle, type_="lien"):
    return {"key": cle, "type": type_, "libelle": libelle, "locators": [f"id={cle}"]}


def _carte(monkeypatch):
    for v in ("XRAY_CLIENT_ID", "JIRA_BASE_URL"):
        monkeypatch.delenv(v, raising=False)
    from atelier.discovery import carte

    carte.creer_app("Site Démo", ["web"], web={"url": "https://demo.exemple.test"}, type_="web", build="1.0")
    u = "https://demo.exemple.test"
    acc = carte.observer([_el("lien_connexion", "Connexion")], "web", u + "/", build="1.0")
    con = carte.observer([_el("champ_email", "E-mail", "champ")], "web", u + "/connexion", build="1.0")
    tar = carte.observer([_el("bouton_essai", "Essai", "bouton")], "web", u + "/tarifs", build="2.0")
    carte.renommer(acc["id"], "accueil", "Vitrine")
    carte.renommer(con["id"], "connexion", "Compte")
    carte.renommer(tar["id"], "tarifs", "Offres")
    carte.enregistrer_transition(acc["id"], con["id"], "web", {"type": "tap", "cle": "lien_connexion", "libelle": "Connexion"})
    return carte, acc, con, tar


def test_releture_ciblee_et_delta(projet, monkeypatch):
    """Cahier 5.1 / 5.2 : un écran modifié est le seul fichier relu ; l'écart le désigne ; un écran retiré disparaît
    avec ses relations (aucune relation orpheline)."""
    from atelier.discovery import connaissance

    carte, acc, con, tar = _carte(monkeypatch)
    connaissance.vider_cache()
    connaissance._construire()
    carte.renommer(con["id"], "connexion", "Espace client")            # seul ce fichier d'écran change
    g = connaissance._construire()
    f = connaissance.DERNIERE_CONSTRUCTION["fichiers"]["écrans (carte)"]
    assert f == {"relus": 1, "reutilises": 2}
    d = connaissance.DERNIERE_CONSTRUCTION["delta"]
    assert "ecran:connexion" in d["modifies"] and "module:Espace client" in d["ajoutes"] and "module:Compte" in d["retires"]
    assert g.noeuds["ecran:connexion"].libelle == "connexion"
    (carte._dir() / "ecrans" / f"{tar['id']}.yaml").unlink()
    g = connaissance._construire()
    assert "ecran:tarifs" not in g.noeuds and "ecran:tarifs" in connaissance.DERNIERE_CONSTRUCTION["delta"]["retires"]
    assert all(r.de in g.noeuds and r.vers in g.noeuds for r in g.relations.values())


def test_filtre_version_et_filtres_proposes(projet, monkeypatch):
    from atelier.discovery import connaissance, espaces

    _carte(monkeypatch)
    connaissance.vider_cache()
    g = connaissance.construire()
    assert g.noeuds["ecran:tarifs"].proprietes["versions"] == ["2.0"]
    assert {"version:1.0", "version:2.0"} <= set(g.noeuds)
    v1 = set(g.filtrer(version="1.0").noeuds)
    assert "ecran:accueil" in v1 and "ecran:tarifs" not in v1 and "version:2.0" not in v1 and "module:Vitrine" in v1
    v = espaces.vue_connaissance(["application", "module", "ecran"], version="2.0")
    ids = {n["id"] for n in v["noeuds"]}
    assert "ecran:tarifs" in ids and "ecran:accueil" not in ids
    f = v["filtres"]
    assert f["plateformes"] == ["web"] and f["versions"] == ["2.0", "1.0"] and f["types"]["ecran"] == 3
    assert [a["id"] for a in f["applications"]] == ["application:site_demo"]


def test_detail_provenance_et_tracabilite(projet, monkeypatch):
    from atelier.discovery import connaissance, espaces, parcours_utilisateur as pu
    from atelier.generation import bdd, parcours_bdd

    carte, acc, con, _ = _carte(monkeypatch)
    vide = pu.enregistrer("", {"nom": "Se connecter"})
    r = parcours_bdd.brouillon([acc["id"], con["id"]], titre="Aller à la connexion")
    m = bdd.charger(r["cle"])
    m["parcours"] = vide["noeud"]
    bdd.sauver(m)
    connaissance.vider_cache()
    d = espaces.detail("ecran:connexion")
    assert d["provenance"]["provenance"] == "observé" and d["provenance"]["source"] == "carte"
    tests = {x["id"]: x for x in d["tracabilite"]["tests"]}
    assert tests[f"scenario:{r['cle']}"]["confirme"] is True
    assert vide["noeud"] in [x["id"] for x in d["tracabilite"]["parcours"]]
    assert set(d["tracabilite"]) == {"exigences", "parcours", "tests", "plans", "executions", "anomalies"}
