"""Granularité des tests d'une US : regrouper sans perdre de comportement couvert, jamais automatiquement,
toujours réversible avant publication ; « comportements couverts par test » plutôt que le nombre de tests."""
import json

import pytest


@pytest.fixture
def g(tmp_path, monkeypatch):
    from atelier.domain import projet
    from atelier.intelligence import granularite_tests, testabilite_us

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    (tmp_path / "testabilite").mkdir()
    (tmp_path / "testabilite" / "us.json").write_text(json.dumps({"DEMO-1": {
        "cle": "DEMO-1", "espace": "SQ", "resume": "Livraison à domicile", "statut": "Analysée", "description": "", "cas": []}}), "utf-8")
    e = lambda a, r: {"action": a, "donnees": "", "resultat": r}  # noqa: E731
    testabilite_us.deposer_proposition("DEMO-1", [], [
        {"titre": "Adresse étrangère : modification obligatoire", "etapes": [e("Choisir la livraison à domicile avec une adresse étrangère",
                                                                                   "« Continuer » grisé, modification obligatoire")]},
        {"titre": "Numéro étranger : modification obligatoire", "etapes": [e("Choisir la livraison à domicile avec un numéro étranger",
                                                                               "« Continuer » grisé, modification obligatoire")]},
        {"titre": "Pack non éligible : pas de choix du mode", "etapes": [e("Choisir un pack éligible ou non", "Passage direct à l'agence"),
                                                                          e("Continuer", "Choix de l'agence")]},
        {"titre": "Pack éligible : tarif affiché", "etapes": [e("Choisir un pack éligible", "Tarif de livraison affiché")]},
        {"titre": "Envoi EERD", "etapes": [e("Terminer la souscription", "Quatre champs transmis")], "couvre": ["4 champs", "mode transmis"]},
    ], "Cursor (MCP)")
    return granularite_tests, testabilite_us


def _ids(u, *debuts):
    return [next(c["id"] for c in u["cas"] if c["titre"].startswith(d)) for d in debuts]


def test_regroupement_par_donnees_reversible(g):
    gr, t = g
    u = t.detail("DEMO-1")
    assert u["granularite"] == {"tests": 5, "comportements": 6, "par_test": 1.2, "regroupes": 0}  # « couvre » déclaré : 2 comportements
    a, b = _ids(u, "Adresse", "Numéro")
    u = gr.regrouper("DEMO-1", [a, b], "donnees")
    nouveau = next(c for c in u["cas"] if c.get("regroupe"))
    assert nouveau["statut"] == "Proposé" and nouveau["regroupe"] == [a, b]
    assert [s["action"] for s in nouveau["etapes"]][0].startswith("Variante 1 (Adresse étrangère")
    assert "Plan du scénario" in nouveau["gherkin"] and "| variante | action | resultat |" in nouveau["gherkin"]
    assert set(nouveau["couvre"]) == {"Adresse étrangère : modification obligatoire", "Numéro étranger : modification obligatoire"}
    assert {c["statut"] for c in u["cas"] if c["id"] in (a, b)} == {"Regroupé"}
    assert u["granularite"] == {"tests": 4, "comportements": 6, "par_test": 1.5, "regroupes": 2}  # aucun comportement perdu
    with pytest.raises(PermissionError):
        t.decider_cas("DEMO-1", a, "valider")  # un cas regroupé ne se décide plus seul
    with pytest.raises(ValueError):
        gr.regrouper("DEMO-1", [a, nouveau["id"]], "donnees")  # déjà regroupé
    u = gr.degrouper("DEMO-1", nouveau["id"])
    assert not any(c.get("regroupe") for c in u["cas"]) and {c["statut"] for c in u["cas"]} == {"Proposé"}
    assert u["granularite"]["tests"] == 5


def test_point_de_controle_et_garde_fous(g):
    gr, t = g
    u = t.detail("DEMO-1")
    hote, detail_ = _ids(u, "Pack non", "Envoi")
    u = gr.regrouper("DEMO-1", [hote, detail_], "controle", "Souscription complète")
    nouveau = next(c for c in u["cas"] if c.get("regroupe"))
    assert nouveau["titre"] == "Souscription complète" and nouveau["etapes"][-1]["action"] == "Vérifier : Terminer la souscription"
    with pytest.raises(ValueError):
        gr.regrouper("DEMO-1", [hote], "donnees")  # au moins deux cas
    with pytest.raises(ValueError):
        gr.regrouper("DEMO-1", ["x", "y"], "inconnu")


def test_suggestions_jamais_appliquees_et_resultats_opposes_separes(g):
    gr, t = g
    u = gr.proposer("DEMO-1")
    props = u["consolidation"]["propositions"]
    titres = {c["id"]: c["titre"] for c in u["cas"]}
    donnees = [p for p in props if p["mode"] == "donnees"]
    assert len(donnees) == 1 and sorted(titres[i][:7] for i in donnees[0]["cas"]) == ["Adresse", "Numéro "]
    # « Pack non éligible » et « Pack éligible » : résultat métier opposé, jamais regroupés
    assert not any({titres[i][:8] for i in p["cas"]} >= {"Pack non", "Pack éli"} for p in props)
    assert all(c["statut"] == "Proposé" for c in u["cas"])  # rien n'est appliqué sans décision
    u = gr.decider_proposition("DEMO-1", donnees[0]["id"], "appliquer")
    assert u["granularite"]["regroupes"] == 2
    with pytest.raises(ValueError):
        gr.decider_proposition("DEMO-1", donnees[0]["id"], "appliquer")  # déjà traitée
    assert "cas_regroupes" in (t._d() / "journal.jsonl").read_text("utf-8")


def test_regroupements_proposes_par_cursor_controles_puis_decides(g):
    gr, t = g
    u = t.detail("DEMO-1")
    a, b, hote, detail_ = _ids(u, "Adresse", "Numéro", "Pack non", "Pack éligible")
    vue = gr.cas_pour_agent("DEMO-1")
    assert {c["id"] for c in vue["cas"]} == {c["id"] for c in u["cas"]} and "un objectif" in vue["consigne"]
    r = gr.deposer_regroupements("DEMO-1", [
        {"cas": [a, b], "mode": "données", "titre": "Coordonnées étrangères", "justification": "Même chemin, seule la donnée change",
         "couvre": ["adresse étrangère bloquante", "numéro étranger bloquant"]},
        {"cas": [a, hote], "mode": "controle", "justification": "x"},           # cas déjà pris
        {"cas": [hote, detail_], "mode": "fusion", "justification": "x"},      # mode inconnu
        {"cas": [hote, "inconnu"], "mode": "donnees", "justification": "x"},   # cas inconnu
        {"cas": [hote, detail_], "mode": "controle"},                          # justification manquante
    ])
    assert r["retenues"] == 1 and [x["index"] for x in r["refusees"]] == [2, 3, 4, 5] and (r["avant"], r["apres"]) == (5, 4)
    u = t.detail("DEMO-1")
    p = next(x for x in u["consolidation"]["propositions"] if x["statut"] == "Proposé")
    assert p["source"] == "Cursor (MCP)" and all(c["statut"] == "Proposé" for c in u["cas"])  # rien appliqué par l'agent
    u = gr.decider_proposition("DEMO-1", p["id"], "appliquer")
    nouveau = next(c for c in u["cas"] if c.get("regroupe"))
    assert nouveau["titre"] == "Coordonnées étrangères" and nouveau["couvre"] == ["adresse étrangère bloquante", "numéro étranger bloquant"]
    assert nouveau["source"] == "regroupement proposé · Cursor (MCP)"


def test_regles_marquees_secours_et_ia_directe(g, monkeypatch):
    gr, t = g
    from atelier.intelligence import fournisseur_ia

    assert all(p["source"].startswith("règles") for p in gr.proposer("DEMO-1")["consolidation"]["propositions"])
    monkeypatch.setenv("IA_FOURNISSEUR", "cursor")
    assert gr.consolider_ia("DEMO-1")["disponible"] is False  # Cursor passe par le MCP, l'atelier n'appelle rien
    monkeypatch.setenv("IA_FOURNISSEUR", "interne")
    monkeypatch.setattr(fournisseur_ia, "configure", lambda: True)
    u = t.detail("DEMO-1")
    a, b = _ids(u, "Adresse", "Numéro")
    envoye = {}
    monkeypatch.setattr(fournisseur_ia, "completer", lambda s, d, m=0: envoye.setdefault("d", d) and json.dumps(
        {"regroupements": [{"cas": [a, b], "mode": "donnees", "justification": "même chemin"}]}))
    u = gr.consolider_ia("DEMO-1")
    props = [x for x in u["consolidation"]["propositions"] if x["statut"] == "Proposé"]
    assert len(props) == 1 and props[0]["source"].startswith("IA interne") and a in envoye["d"]
    assert u["ia"]["fournisseur"] == "interne"


def test_outils_mcp_granularite(g):
    from atelier.adapters import facade

    gr, t = g
    a, b = _ids(t.detail("DEMO-1"), "Adresse", "Numéro")
    assert len(facade.test_design_cas_us("DEMO-1")["cas"]) == 5
    r = facade.test_design_proposer_regroupements("DEMO-1", [{"cas": [a, b], "mode": "donnees", "justification": "même chemin"}])
    assert r["retenues"] == 1 and not r["refusees"]


def test_regles_gardent_les_propositions_de_l_ia_et_l_historique(g):
    gr, t = g
    u = t.detail("DEMO-1")
    a, b, hote, detail_ = _ids(u, "Adresse", "Numéro", "Pack non", "Envoi")
    gr.deposer_regroupements("DEMO-1", [{"cas": [hote, detail_], "mode": "controle", "justification": "détail vérifié en fin de parcours"}])
    u = gr.proposer("DEMO-1")  # secours par règles : ne remplace pas la proposition de Cursor encore en attente
    props = u["consolidation"]["propositions"]
    assert [p["source"] for p in props if set(p["cas"]) == {hote, detail_}] == ["Cursor (MCP)"]
    regle = next(p for p in props if set(p["cas"]) == {a, b})
    gr.decider_proposition("DEMO-1", regle["id"], "ecarter")
    props = gr.proposer("DEMO-1")["consolidation"]["propositions"]  # un regroupement écarté n'est pas reproposé
    assert [p["statut"] for p in props if set(p["cas"]) == {a, b}] == ["Écartée"]


def test_defaire_un_regroupement_contenu_dans_un_autre_est_refuse(g):
    gr, t = g
    u = t.detail("DEMO-1")
    a, b, hote = _ids(u, "Adresse", "Numéro", "Pack non")
    r1 = next(c for c in gr.regrouper("DEMO-1", [a, b], "donnees")["cas"] if c.get("regroupe"))["id"]
    gr.regrouper("DEMO-1", [hote, r1], "controle", "Parcours complet")
    with pytest.raises(ValueError, match="autre regroupement"):
        gr.degrouper("DEMO-1", r1)
