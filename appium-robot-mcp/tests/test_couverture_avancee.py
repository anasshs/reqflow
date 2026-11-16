"""V2, phase 3 : couverture des parcours et composants UI par niveau (découvert → associé → automatisé → exécuté →
réussi), calculée sur le Knowledge Graph et explicable."""
import pytest

from atelier.domain.graphe import Graphe


@pytest.fixture
def g():
    g = Graphe("essai")
    g.noeud("module:Virements", "module", "Virements")
    for e in ("saisie", "confirmation", "aide"):
        g.noeud(f"ecran:{e}", "ecran", e)
        g.relier("module:Virements", f"ecran:{e}", "contient")
    loc = {"saisie": ["champ_montant", "bouton_valider", "lien_aide"], "confirmation": ["message_ok"], "aide": ["texte_aide"]}
    for e, cles in loc.items():
        for c in cles:
            for p in ("android", "ios"):
                g.noeud(f"locator:{e}.{c}@{p}", "locator", c, proprietes={"plateforme": p})
                g.relier(f"ecran:{e}", f"locator:{e}.{c}@{p}", "contient")
    # keywords : Saisir utilise champ_montant (via un keyword appelé), Valider utilise bouton_valider, Vérifier utilise message_ok
    for k, l in (("saisir_montant", "saisie.champ_montant@android"), ("valider", "saisie.bouton_valider@ios"), ("verifier", "confirmation.message_ok@android")):
        g.noeud(f"keyword:{k}", "keyword", k)
        g.relier(f"keyword:{k}", f"locator:{l}", "utilise")
    g.noeud("keyword:faire_virement", "keyword", "faire virement")
    g.relier("keyword:faire_virement", "keyword:saisir_montant", "appelle")
    # T1 : test Robot sans clé Xray (associé) → saisir ; T2 : tracé VIR-1, exécuté FAIL → valider ;
    # T3 : tracé VIR-2, PASS → vérifier
    tests = {"t1": ([], "", "keyword:faire_virement"), "t2": (["VIR-1"], "FAIL", "keyword:valider"), "t3": (["VIR-2"], "PASS", "keyword:verifier")}
    for t, (cles, st, kw) in tests.items():
        g.noeud(f"test_robot:{t}", "test_robot", t, proprietes={"cles_xray": cles, "dernier_statut": st})
        g.relier(f"test_robot:{t}", kw, "appelle")
    # parcours saisie → confirmation ; parcours avec l'écran d'aide (non couvert)
    g.noeud("parcours:virement", "parcours", "Faire un virement")
    g.relier("parcours:virement", "ecran:saisie", "contient")
    g.relier("parcours:virement", "ecran:confirmation", "contient")
    g.noeud("parcours:aide", "parcours", "Consulter l'aide")
    g.relier("parcours:aide", "ecran:saisie", "contient")
    g.relier("parcours:aide", "ecran:aide", "contient")
    return g


def test_niveaux_des_composants(g):
    from atelier.intelligence import couverture_avancee as ca

    r = ca.calculer(g)
    niv = {c["id"].split("#")[1] if "#" in c["id"] else c["id"]: c["niveau"] for c in r["composants"]}
    assert niv == {"champ_montant": "associé", "bouton_valider": "exécuté", "lien_aide": "découvert",
                   "message_ok": "réussi", "texte_aide": "découvert"}
    c = next(x for x in r["composants"] if x["cle"] == "champ_montant")
    assert c["plateformes"] == ["android", "ios"] and c["tests"] == ["t1"]  # un composant = une clé, toutes plateformes
    assert r["repartition"]["composants"] == {"découvert": 5, "associé": 3, "automatisé": 2, "exécuté": 2, "réussi": 1}
    assert r["indicateurs"]["couverture_composants"]["valeur"] == 60.0 and r["indicateurs"]["reussite_composants"]["valeur"] == 20.0
    assert set(r["definitions"]) == set(ca.NIVEAUX)


def test_ecrans_et_parcours(g):
    from atelier.intelligence import couverture_avancee as ca

    r = ca.calculer(g)
    e = {x["nom"]: x for x in r["ecrans"]}
    assert e["saisie"]["niveau"] == "exécuté" and e["confirmation"]["niveau"] == "réussi" and e["aide"]["niveau"] == "découvert"
    assert e["saisie"]["composants_par_niveau"]["associé"] == 2 and e["saisie"]["module"] == "Virements"
    p = {x["libelle"]: x for x in r["parcours"]}
    assert p["Faire un virement"]["niveau"] == "exécuté" and p["Faire un virement"]["couverture_etapes"] == 100.0
    assert p["Consulter l'aide"]["niveau"] == "découvert" and p["Consulter l'aide"]["etapes_associees"] == 1
    assert r["indicateurs"]["couverture_parcours"]["valeur"] == 50.0
    assert r["sans_test"]["ecrans"] == ["aide"] and r["sans_test"]["parcours"] == ["Consulter l'aide"]
    assert "saisie.lien_aide" in r["sans_test"]["composants"]


def test_association_deduite_par_fonctionnalite(g):
    from atelier.intelligence import couverture_avancee as ca

    g.noeud("fonctionnalite:aide", "fonctionnalite", "Aide")
    g.noeud("user_story:VIR-9", "user_story", "VIR-9")
    g.noeud("test:VIR-90", "test", "VIR-90 Afficher l'aide")
    g.relier("fonctionnalite:aide", "ecran:aide", "contient")
    g.relier("fonctionnalite:aide", "user_story:VIR-9", "contient")
    g.relier("user_story:VIR-9", "test:VIR-90", "teste_par")
    e = {x["nom"]: x for x in ca.calculer(g)["ecrans"]}["aide"]
    assert e["niveau"] == "associé" and e["association_deduite"] and e["tests_xray_deduits"] == ["VIR-90 Afficher l'aide"]


def test_filtre_module_et_outil_mcp(g, monkeypatch):
    from atelier.adapters import facade
    from atelier.discovery import connaissance
    from atelier.intelligence import couverture_avancee as ca

    assert ca.calculer(g, "Comptes")["ecrans"] == []
    monkeypatch.setattr(connaissance, "construire", lambda *a, **k: g)
    r = facade.coverage_ui()
    assert r["indicateurs"]["couverture_ecrans"]["valeur"] == pytest.approx(66.7) and all(c["niveau"] == "découvert" for c in r["composants"])
    assert len(facade.coverage_ui(detail=True)["composants"]) == 5
