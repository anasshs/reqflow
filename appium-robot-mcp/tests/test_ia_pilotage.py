"""Pilotage de l'IA (atelier/intelligence/ia) : point d'appel unique, journal des tokens, cache versionné, routage
économique / avancé / secours, plafonds sans troncature silencieuse, budgets en tokens, réglages hiérarchiques, mesure
des réponses MCP. Le modèle est un faux client : aucun appel réel."""
import importlib.util
import types

import pytest


class FauxClaude:
    """Faux client Anthropic : rend un texte et un usage ; échoue pour les modèles listés dans `en_panne`."""
    def __init__(self, usage=True, en_panne=()):
        self.appels, self.usage, self.en_panne = [], usage, set(en_panne)
        self.messages = self

    def create(self, **kw):
        self.appels.append(kw)
        if kw["model"] in self.en_panne:
            raise TimeoutError("délai dépassé")
        u = types.SimpleNamespace(input_tokens=120, output_tokens=30, cache_read_input_tokens=0, cache_creation_input_tokens=0) if self.usage else None
        return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=f"réponse de {kw['model']}")], usage=u)


@pytest.fixture
def ia(projet, tmp_path, monkeypatch):
    from atelier.intelligence import assistant
    from atelier.intelligence.ia import cache, journal

    monkeypatch.setenv("IA_FOURNISSEUR", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "factice")
    monkeypatch.setenv("ATELIER_IA_JOURNAL", str(tmp_path / "ia.sqlite"))
    monkeypatch.setattr(cache, "versions", lambda: {"tests": "v1", "exigences": "v1", "graphe": "g1", "regles": "1"})
    client = FauxClaude()
    monkeypatch.setattr(assistant, "_client", lambda: client)
    from atelier.intelligence.ia import orchestrateur

    return types.SimpleNamespace(client=client, journal=journal, orch=orchestrateur, projet=projet)


def _regler(projet, texte):
    (projet / "atelier_ia.yaml").write_text(texte, encoding="utf-8")


def test_completer_passe_par_le_point_unique_et_mesure(ia):
    from atelier.intelligence import fournisseur_ia

    assert fournisseur_ia.completer("Consigne", '{"a": 1, "vide": [], "b": "x"}', 500) == "réponse de claude-sonnet-5-5"
    envoye = ia.client.appels[0]["messages"][0]["content"]
    assert envoye == '{"a":1,"b":"x"}'                                                   # compacté sans perte
    (a,) = ia.journal.appels()
    assert (a["source"], a["fournisseur"], a["statut"], a["tokens_entree"], a["tokens_sortie"], a["estime"]) == ("direct", "anthropic", "ok", 120, 30, 0)
    assert a["operation"] == "autre" and a["tokens_avant"] > a["tokens_apres"] and a["correlation"]


def test_operation_deduite_de_l_appelant(ia, tmp_path):
    """L'opération QA vient du module qui appelle : les points d'appel existants n'ont pas changé."""
    f = tmp_path / "correlation.py"
    f.write_text("from atelier.intelligence import fournisseur_ia\ndef juger():\n    return fournisseur_ia.completer('S', 'D')\n", encoding="utf-8")
    spec = importlib.util.spec_from_file_location("correlation_essai", f)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.juger()
    (a,) = ia.journal.appels()
    assert (a["operation"], a["module"]) == ("discovery.correlation", "Discovery")


def test_correlation_regroupe_les_appels_d_une_operation(ia):
    with ia.journal.operation() as cid:
        ia.orch.appeler("S", "première", operation="non_regression.interpretation")
        ia.orch.appeler("S", "seconde", operation="non_regression.interpretation")
    l = ia.journal.appels(correlation=cid)
    assert len(l) == 2 and {x["module"] for x in l} == {"Non-Regression"}


def test_cache_tant_que_les_sources_ne_changent_pas(ia, monkeypatch):
    from atelier.intelligence.ia import cache

    ia.orch.appeler("S", "même demande", operation="conception.doublons")
    r = ia.orch.executer("S", "même demande", operation="conception.doublons")
    assert r["cache"] and len(ia.client.appels) == 1 and r["tokens_evites"] == 150
    monkeypatch.setattr(cache, "versions", lambda: {"tests": "v2", "exigences": "v1", "graphe": "g1", "regles": "1"})  # copie Xray réimportée
    assert not ia.orch.executer("S", "même demande", operation="conception.doublons")["cache"] and len(ia.client.appels) == 2
    assert cache.invalider(operation="conception.doublons") == 1


def test_routage_economique_avance_et_repli(ia):
    _regler(ia.projet, """modeles:
  economique: {modele: modele-eco, max_sortie: 800}
  avance: {modele: modele-avance}
  secours: {modele: modele-secours}
routage: {seuil_avance_tokens: 50}
operations:
  conception.doublons: {niveau: economique}
""")
    assert ia.orch.executer("S", "court", operation="exigences.testabilite")["modele"] == "modele-avance"      # niveau réglé par défaut : avancé
    assert ia.orch.executer("S", "court", operation="impact.assistant")["modele"] == "modele-eco"              # auto, petit contexte
    assert ia.orch.executer("S", "x" * 400, operation="impact.assistant")["modele"] == "modele-avance"         # auto, au-delà du seuil
    r = ia.orch.executer("S", "court bis", 2000, operation="conception.doublons")
    assert r["modele"] == "modele-eco" and ia.client.appels[-1]["max_tokens"] == 800                          # limite de sortie du modèle
    ia.client.en_panne.add("modele-eco")
    r = ia.orch.executer("S", "autre", operation="conception.doublons")
    assert r["modele"] == "modele-secours" and r["repli"]
    statuts = [(a["modele"], a["statut"], a["repli"]) for a in ia.journal.appels()][-2:]
    assert statuts == [("modele-eco", "erreur", 0), ("modele-secours", "ok", 1)]


def test_contexte_trop_gros_refuse_jamais_tronque(ia):
    from atelier.intelligence.ia import optimiseur

    _regler(ia.projet, "modeles:\n  economique: {modele: m, max_entree: 20}\n  avance: {modele: m, max_entree: 20}\n")
    with pytest.raises(optimiseur.ContexteTropGros, match="rien n'est tronqué"):
        ia.orch.appeler("S", "y" * 400, operation="conception.doublons")
    assert ia.client.appels == []


def test_budget_en_tokens_restriction_puis_blocage(ia):
    from atelier.intelligence import fournisseur_ia
    from atelier.intelligence.ia import budget

    _regler(ia.projet, """modeles:
  economique: {modele: modele-eco}
  avance: {modele: modele-avance}
budgets:
  global: 500
  seuils: {information: 10, avertissement: 20, restriction: 25, blocage: 60}
""")
    ia.orch.appeler("S", "un", operation="exigences.testabilite")                                    # 150 tokens : 30 %
    assert budget.etat()["niveau"] == "restriction"
    assert ia.orch.executer("S", "deux", operation="exigences.testabilite")["modele"] == "modele-eco"  # restriction : économique imposé
    assert budget.etat()["niveau"] == "blocage" and not fournisseur_ia.configure()                    # 300 / 500 = 60 %
    with pytest.raises(budget.BudgetAtteint, match="règles"):
        ia.orch.appeler("S", "trois", operation="exigences.testabilite")


def test_reglages_hierarchiques_plafonnes_et_historises(ia, tmp_path, monkeypatch):
    from atelier.intelligence.ia import config

    ent = tmp_path / "entreprise.yaml"
    ent.write_text("modeles:\n  '*': {max_sortie: 1000}\nbudgets: {global: 100000}\n", encoding="utf-8")
    monkeypatch.setenv("ATELIER_IA_CONFIG", str(ent))
    with pytest.raises(ValueError, match="Niveau de modèle inconnu"):
        config.enregistrer({"modeles": {"turbo": {"modele": "x"}}})
    config.enregistrer({"modeles": {"economique": {"modele": "eco", "max_sortie": 4000}}, "budgets": {"global": 900000},
                        "operations": {"conception.doublons": {"niveau": "economique", "contexte": {"max_tests": 20}}}})
    e = config.effective()
    assert e["modeles"]["economique"]["max_sortie"] == 1000 and e["budgets"]["global"] == 100000          # plafonds de l'entreprise
    assert config.plafond("conception.doublons", "max_tests", 400) == 20 and config.plafond("autre", "max_tests", 10) == 10
    h = config.historique()
    assert h and '"eco"' in h[0]["apres"]


def test_reponse_mcp_mesuree_et_allegee_sans_perte(ia):
    r = ia.orch.mesurer_mcp("release_a_interpreter", {"texte": "abc", "absents": [], "tests": [{"test": "T-1", "resume": ""}]}, 0.2, "D42")
    assert r == {"texte": "abc", "tests": [{"test": "T-1"}]}
    (a,) = ia.journal.appels(source="mcp")
    assert (a["operation"], a["module"], a["correlation"], a["estime"]) == ("mcp.release_a_interpreter", "Non-Regression", "D42", 1)
    assert a["tokens_avant"] > a["tokens_apres"] > 0
    assert ia.orch.mesurer_mcp("screenshot", b"png", 0.1) == b"png"                                     # non JSON : rendu tel quel


def test_sans_usage_les_tokens_sont_estimes(ia):
    ia.client.usage = False
    ia.orch.appeler("S", "demande", operation="conception.doublons")
    (a,) = ia.journal.appels()
    assert a["estime"] == 1 and a["tokens_entree"] > 0


def test_assistant_respecte_le_fournisseur(ia, monkeypatch):
    from atelier.discovery.connaissance import Graphe
    from atelier.intelligence import assistant

    monkeypatch.setenv("IA_FOURNISSEUR", "aucun")
    r = assistant.demander(Graphe(), "connaissance", "anomalies")
    assert r["disponible"] is False and ia.client.appels == []
