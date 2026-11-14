"""Knowledge Graph : par défaut, seuls les tickets Jira / Xray rattachés à l'application sont affichés."""
from atelier.discovery import espaces
from atelier.domain.graphe import Graphe


def _g():
    g = Graphe("connaissance")
    g.noeud("ecran:virement", "ecran", "virement", source="carte")
    g.noeud("test_robot:t1", "test_robot", "Virement simple", source="dépôt")
    g.relier("test_robot:t1", "ecran:virement", "depend_de", source="dépôt")
    for cle, typ in (("DEMO-1", "epic"), ("DEMO-2", "user_story"), ("DEMO-3", "user_story"), ("DEMO-9", "epic")):
        g.noeud(f"{typ}:{cle}", typ, cle, source="instantané")
    g.relier("epic:DEMO-1", "user_story:DEMO-2", "contient", source="instantané")
    g.relier("epic:DEMO-1", "user_story:DEMO-3", "contient", source="instantané")  # US sœur, sans lien avec l'app
    for cle in ("DEMO-11", "DEMO-12"):
        g.noeud(f"test:{cle}", "test", cle, source="instantané")
    g.relier("test:DEMO-11", "test_robot:t1", "implemente_par", source="tag Robot")
    g.relier("user_story:DEMO-2", "test:DEMO-11", "teste_par", source="instantané")
    g.relier("user_story:DEMO-3", "test:DEMO-12", "teste_par", source="instantané")
    g.noeud("test_plan:DEMO-50", "test_plan", "DEMO-50", source="instantané")
    g.relier("test_plan:DEMO-50", "test:DEMO-11", "contient", source="instantané")
    g.noeud("module:Virements", "module", "Virements", source="instantané")
    g.relier("module:Virements", "user_story:DEMO-2", "contient", source="instantané")
    g.noeud("module:Cartes", "module", "Cartes", source="instantané")
    g.relier("module:Cartes", "epic:DEMO-9", "contient", source="instantané")
    return g


def test_patrimoine_lie():
    garde = espaces.patrimoine_lie(_g())
    assert {"test:DEMO-11", "user_story:DEMO-2", "epic:DEMO-1", "module:Virements", "ecran:virement"} <= garde
    assert not {"user_story:DEMO-3", "test:DEMO-12", "epic:DEMO-9", "test_plan:DEMO-50", "module:Cartes"} & garde


def test_vue_connaissance_masque_puis_tout(monkeypatch):
    monkeypatch.setattr(espaces, "_graphe", _g)
    v = espaces.vue_connaissance()
    ids = {n["id"] for n in v["noeuds"]}
    assert "user_story:DEMO-3" not in ids and v["patrimoine_masque"] == 5
    assert "user_story:DEMO-3" in {n["id"] for n in espaces.vue_connaissance(patrimoine="tout")["noeuds"]}
    assert "user_story:DEMO-3" in {n["id"] for n in espaces.vue_connaissance(recherche="DEMO-3")["noeuds"]}  # recherche : tout
