"""Vue fonctionnelle reliée : relations déduites de la Discovery (module → module, parcours → module, parcours → parcours)
et liens « via » dans une vue filtrée (aucun nœud isolé alors que la connaissance les relie)."""


def _el(cle, libelle, type_="lien"):
    return {"key": cle, "type": type_, "libelle": libelle, "locators": [f"id={cle}"]}


def _carte(projet):
    from atelier.discovery import carte

    carte.creer_app("Site Démo", ["web"], web={"url": "https://demo.exemple.test"}, type_="web")
    u = "https://demo.exemple.test"
    acc = carte.observer([_el("lien_tarifs", "Tarifs"), _el("lien_connexion", "Connexion")], "web", u + "/")
    tar = carte.observer([_el("bouton_essai", "Essai gratuit", "bouton")], "web", u + "/tarifs")
    con = carte.observer([_el("champ_email", "E-mail", "champ")], "web", u + "/connexion")
    carte.renommer(acc["id"], "accueil", "Vitrine")
    carte.renommer(tar["id"], "tarifs", "Offres")
    carte.renommer(con["id"], "connexion", "Compte")
    carte.enregistrer_transition(acc["id"], tar["id"], "web", {"type": "tap", "cle": "lien_tarifs", "libelle": "Tarifs"})
    carte.enregistrer_transition(acc["id"], con["id"], "web", {"type": "tap", "cle": "lien_connexion", "libelle": "Connexion"})
    return acc, tar, con


def test_modules_relies_par_la_navigation(projet):
    from atelier.discovery import connaissance

    _carte(projet)
    connaissance.vider_cache()
    g = connaissance.construire()
    r = {(x.de, x.vers): x for x in g.relations.values() if x.type == "mene_a"}
    assert ("module:Vitrine", "module:Offres") in r and ("module:Vitrine", "module:Compte") in r
    x = r[("module:Vitrine", "module:Offres")]
    assert x.provenance == "déduit" and x.statut == "validé" and x.proprietes["actions"] == ["Tarifs"] and x.proprietes["transitions"] == 1


def test_vue_fonctionnelle_sans_noeud_isole(projet):
    from atelier.discovery import connaissance, espaces

    _carte(projet)
    connaissance.vider_cache()
    v = espaces.vue_connaissance(types=["application", "module", "parcours"])
    ids = {n["id"] for n in v["noeuds"]}
    assert {"module:Vitrine", "module:Offres", "module:Compte"} <= ids
    relies = {r["de"] for r in v["relations"]} | {r["vers"] for r in v["relations"]}
    assert all(i in relies for i in ids), "aucun nœud isolé dans la vue fonctionnelle"
    assert any(r["type"] == "mene_a" for r in v["relations"])


def test_liens_via_dans_une_vue_filtree(projet):
    from atelier.discovery import connaissance, espaces

    _carte(projet)
    connaissance.vider_cache()
    v = espaces.vue_connaissance(types=["module", "locator"])  # écrans masqués : modules et locators reliés « via »
    via = [r for r in v["relations"] if r["type"] == "lie_via"]
    assert via and all(r["proprietes"]["via"] for r in via) and "ecran" in via[0]["proprietes"]["types"]


def test_parcours_traverse_et_enchaine(projet):
    from atelier.discovery import connaissance
    from atelier.domain.graphe import Graphe

    g = Graphe("t")
    for i, t in [("module:A", "module"), ("module:B", "module"), ("ecran:x", "ecran"), ("ecran:y", "ecran"), ("ecran:z", "ecran"),
                 ("parcours:p1", "parcours"), ("parcours:p2", "parcours")]:
        g.noeud(i, t, i)
    for m, e in [("module:A", "ecran:x"), ("module:B", "ecran:y"), ("module:B", "ecran:z")]:
        g.relier(m, e, "contient")
    g.relier("parcours:p1", "ecran:x", "contient", proprietes={"ordre": 0})
    g.relier("parcours:p1", "ecran:y", "contient", proprietes={"ordre": 1})
    g.relier("parcours:p2", "ecran:y", "contient", proprietes={"ordre": 0}, provenance="déduit", statut="à valider")
    g.relier("parcours:p2", "ecran:z", "contient", proprietes={"ordre": 1})
    connaissance._relations_fonctionnelles(g)
    t = {(r.de, r.vers): r for r in g.relations.values() if r.type == "traverse"}
    assert set(t) == {("parcours:p1", "module:A"), ("parcours:p1", "module:B"), ("parcours:p2", "module:B")}
    assert t[("parcours:p2", "module:B")].statut == "à valider"  # un écran encore proposé : lien à valider
    assert any(r.type == "enchaine_avec" and (r.de, r.vers) == ("parcours:p1", "parcours:p2") for r in g.relations.values())
