"""Module Test Strategy : édition, contrôles, indicateurs réels, workflow, versions immuables."""
import shutil
from pathlib import Path

import pytest

from tests.conftest import pointer_projet

DEMO = Path(__file__).resolve().parents[1] / "demo" / "banque_connexion"


@pytest.fixture
def st(tmp_path, monkeypatch):
    d = tmp_path / "demo"
    shutil.copytree(DEMO, d, ignore=shutil.ignore_patterns("results", "connaissance", "strategie"))
    pointer_projet(d, monkeypatch)
    from atelier.intelligence import strategie

    return strategie


def _remplir(st):
    """Stratégie minimale publiable."""
    st.creer("Stratégie Connexion", "Banque Démo Web", "1.0.0", "qa")
    e = st.etat()
    st.enregistrer_element("objectifs", {"nom": "Automatiser la régression", "indicateur": "couverture_automatisee",
                                         "comparateur": ">=", "cible": 80})
    st.enregistrer_element("criteres", {"description": "Couverture fonctionnelle", "type": "entrée", "obligatoire": True,
                                        "verification": "automatique", "indicateur": "couverture_fonctionnelle", "seuil": 70})
    st.enregistrer_element("criteres", {"description": "Rapport validé", "type": "sortie", "obligatoire": True,
                                        "verification": "manuelle"})
    return e


def test_creation_obligatoire_et_unique(st):
    with pytest.raises(FileNotFoundError):
        st.enregistrer_element("objectifs", {"nom": "x"})
    with pytest.raises(ValueError):
        st.creer("", "app")
    st.creer("S", "App")
    with pytest.raises(FileExistsError):
        st.creer("S", "App")
    assert st.etat()["strategie"]["statut"] == "Draft"


def test_objectif_mesure_depuis_les_sources_reelles(st):
    _remplir(st)
    e = st.etat()
    o = e["synthese"]["objectifs"]["liste"][0]
    # 7 tests sur 9 du patrimoine sont automatisés (tags du dépôt) : 77,8 %, cible 80 % non atteinte
    assert o["valeur"] == pytest.approx(77.8) and o["etat"] == "en cours"
    # 4 exigences sur 5 ont un test (l'épopée DEMO-300 n'en a pas directement)
    assert e["mesures"]["couverture_fonctionnelle"]["valeur"] == 80.0
    assert e["mesures"]["taux_reussite"]["valeur"] is None  # aucun run : rien n'est inventé


def test_controles_et_niveau_de_risque(st):
    _remplir(st)
    st.enregistrer_element("risques", {"nom": "Service tiers indisponible", "probabilite": "4", "impact": "3"})
    e = st.etat()
    r = e["strategie"]["rubriques"]["risques"][0]
    assert (r["score"], r["niveau"]) == (12, "critique")
    assert any("sans plan de mitigation" in c["message"] for c in e["controles"] if c["gravite"] == "erreur")
    assert e["publiable"] is False
    with pytest.raises(ValueError):
        st.enregistrer_element("objectifs", {"nom": "sans cible", "indicateur": "taux_reussite"})
    with pytest.raises(ValueError, match="référence"):
        st.enregistrer_element("environnements", {"nom": "TEST", "type": "TEST", "acces": "MotDePasse123"})


def test_lien_casse_apres_suppression(st):
    _remplir(st)
    e = st.enregistrer_element("perimetre", {"nom": "Connexion", "niveau": "module"})
    mid = e["strategie"]["rubriques"]["perimetre"][0]["id"]
    st.enregistrer_element("risques", {"nom": "Données", "probabilite": "1", "impact": "1", "elements": [mid]})
    e = st.supprimer_element("perimetre", mid)
    assert any("Lien cassé" in c["message"] for c in e["controles"])


def test_workflow_publication_et_versions_immuables(st):
    _remplir(st)
    with pytest.raises(ValueError):
        st.transition("publier")
    st.transition("soumettre")
    with pytest.raises(ValueError):
        st.transition("demander_modifications")  # commentaire obligatoire
    st.transition("approuver", "ok")
    e = st.transition("publier", "première")
    assert e["strategie"]["statut"] == "Published" and e["versions"][0]["statut"] == "Published"
    v1 = st.version(1)
    # RG12 : modifier une version publiée ouvre la version 2 (brouillon), la v1 reste intacte
    e = st.enregistrer_element("objectifs", {"nom": "Stabilité", "indicateur": "taux_instables", "comparateur": "<=", "cible": 5})
    assert e["strategie"]["version"] == 2 and e["strategie"]["statut"] == "Draft"
    assert st.version(1) == v1 and len(v1["rubriques"]["objectifs"]) == 1
    d = st.comparer(1, "courante")
    assert d["rubriques"]["objectifs"]["ajoutes"] == ["Stabilité"]
    st.transition("soumettre"); st.transition("approuver"); e = st.transition("publier")
    statuts = {v["version"]: v["statut"] for v in e["versions"]}
    assert statuts == {1: "Archived", 2: "Published"}  # RG03 : une seule version publiée
    e = st.restaurer(1)
    assert e["strategie"]["version"] == 3 and len(e["strategie"]["rubriques"]["objectifs"]) == 1
    ops = [j["op"] for j in st.journal()]
    assert {"publier", "nouvelle_version", "restauration"} <= set(ops)


def test_critere_manuel_et_automatique(st):
    _remplir(st)
    e = st.etat()
    auto, manuel = sorted(e["criteres"], key=lambda c: c["verification"])
    assert auto["etat"] == "satisfait"  # couverture fonctionnelle 80 % >= 70
    assert manuel["etat"] == "à valider"
    with pytest.raises(ValueError):
        st.valider_critere(auto["id"], "preuve")  # RG10 : un critère mesuré ne se valide pas à la main
    e = st.valider_critere(manuel["id"], "Rapport relu en comité")
    assert [c for c in e["criteres"] if c["id"] == manuel["id"]][0]["etat"] == "satisfait"
    assert st.criteres_entree_non_satisfaits() == []


def test_import_perimetre_sans_doublon(st):
    _remplir(st)
    e = st.importer_perimetre()
    e = st.importer_perimetre()
    p = e["strategie"]["rubriques"]["perimetre"]
    assert sum(1 for x in p if x["niveau"] == "module") == 1
    ex = [x for x in p if x["niveau"] == "exigence"]
    assert len(ex) == 5 and all(x["parent"] for x in ex)
    assert next(x for x in ex if x["jira"] == ["DEMO-311"])["xray"] == ["DEMO-304", "DEMO-306"]


def test_plan_automatisation_decision_humaine(st):
    _remplir(st)
    plan = {c["cle"]: c for c in st.plan_automatisation()}
    assert plan["DEMO-301"]["statut_plan"] == "Automatisé"
    assert plan["DEMO-308"]["statut_plan"] == "À analyser" and plan["DEMO-308"]["score"] is None
    with pytest.raises(ValueError):
        st.decider_candidat("DEMO-308", "Recommandé par IA")
    with pytest.raises(ValueError):
        st.decider_candidat("DEMO-308", "Rejeté")
    st.decider_candidat("DEMO-308", "Approuvé", "Robot + Playwright", "2 j")
    assert {c["cle"]: c for c in st.plan_automatisation()}["DEMO-308"]["statut_plan"] == "Approuvé"



def test_archivee_reprise_et_suivi_hors_version(tmp_path, monkeypatch):
    """Une stratégie archivée se reprend en nouvelle version ; valider un critère ne modifie pas la version publiée."""
    from atelier.domain import projet
    from atelier.intelligence import strategie as st

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    st.creer("Stratégie", "Banque démo")
    st.enregistrer_element("criteres", {"description": "Démo validée par le métier", "type": "sortie", "verification": "manuelle"})
    s = st.charger()
    s["statut"] = "Published"
    st._sauver(s)
    cid = st.charger()["rubriques"]["criteres"][0]["id"]
    avant = (tmp_path / "strategie").joinpath("strategie.yaml").read_text("utf-8") if (tmp_path / "strategie" / "strategie.yaml").exists() else None
    st.valider_critere(cid, "PV de recette du 14/11")
    s = st.charger()
    assert s["statut"] == "Published" and s["version"] == 1  # aucune nouvelle version, aucun retour en brouillon
    assert s["rubriques"]["criteres"][0]["validation"]["preuve"] == "PV de recette du 14/11"
    if avant is not None:
        assert "PV de recette" not in (tmp_path / "strategie" / "strategie.yaml").read_text("utf-8")
    s["statut"] = "Archived"
    st._sauver(s)
    st.enregistrer_element("criteres", {"description": "Nouveau critère", "type": "sortie", "verification": "manuelle"})
    s = st.charger()
    assert s["statut"] == "Draft" and s["version"] == 2



def test_ajout_en_lot_et_squads(tmp_path, monkeypatch):
    from atelier.domain import projet
    from atelier.intelligence import strategie as st

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    st.creer("Stratégie TAM", "TAM")
    st.enregistrer_element("types_tests", {"nom": "API", "methode": "Automatisée"})
    o = st.options_lot("types_tests")
    assert next(x for x in o["options"] if x["valeur"] == "API")["present"]
    e = st.ajouter_en_lot("types_tests", ["Fonctionnel", "Régression", "API", "Inconnu"], {"methode": "Automatisée"})
    assert e["ajoutes"] == ["Fonctionnel", "Régression"]  # API déjà présent, valeur inconnue ignorée
    types = {x["nom"]: x for x in st.charger()["rubriques"]["types_tests"]}
    assert types["Régression"]["methode"] == "Automatisée" and types["Fonctionnel"]["actif"] is True
    st.ajouter_en_lot("niveaux", ["API", "End-to-End"], parts={"API": 40, "End-to-End": 10})
    assert {x["nom"]: x["part_cible"] for x in st.charger()["rubriques"]["niveaux"]} == {"API": 40, "End-to-End": 10}
    st.ajouter_en_lot("outils", ["Jira", "Xray Cloud"])
    assert {x["nom"]: x["usage"] for x in st.charger()["rubriques"]["outils"]}["Jira"].startswith("Exigences")
    with pytest.raises(ValueError):
        st.ajouter_en_lot("outils", ["Jira"])


def test_squads_du_perimetre_reprises_dans_la_politique_des_us(tmp_path, monkeypatch):
    """Les squads ne se déclarent plus que dans la politique des US : celles de l'ancien périmètre y sont reprises
    (sans doublon), puis retirées du périmètre ; le niveau « squad » n'est plus accepté."""
    from atelier.domain import projet, projets
    from atelier.intelligence import strategie as st
    from atelier.intelligence import testabilite_us

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(projets, "cle_xray", lambda: "TAM")
    st.creer("Stratégie TAM", "TAM")
    testabilite_us.enregistrer_espace({"projet_jira": "SQA", "nom": "Squad A"})  # déjà suivie par la politique
    s = st.charger()  # périmètre écrit avant la correction : deux squads et un module rattaché à l'une d'elles
    s["rubriques"]["perimetre"] += [{"id": "per_a", "nom": "Squad A", "niveau": "squad", "projet_jira": "SQA", "inclus": True},
                                    {"id": "per_b", "nom": "Squad B", "niveau": "squad", "projet_jira": "sqb", "inclus": True},
                                    {"id": "per_m", "nom": "Cartes", "niveau": "module", "parent": "per_b", "inclus": True}]
    st._sauver(s)
    assert [(q["projet_jira"], q["dans_politique"]) for q in st.etat()["squads_a_reprendre"]] == [("SQA", True), ("SQB", False)]
    r = st.reprendre_squads()
    assert r["ajoutees_politique"] == ["SQB"] and r["deja_dans_politique"] == ["SQA"] and r["refusees"] == []
    assert sorted(e["projet_jira"] for e in testabilite_us.tous_espaces()) == ["SQA", "SQB"]
    per = st.charger()["rubriques"]["perimetre"]
    assert [x["id"] for x in per] == ["per_m"] and per[0]["parent"] == ""  # le module remonte à la racine
    assert st.etat()["squads_a_reprendre"] == []
    with pytest.raises(ValueError):
        st.reprendre_squads()  # plus rien à reprendre
    with pytest.raises(ValueError):
        st.enregistrer_element("perimetre", {"nom": "Squad C", "niveau": "squad"})
    assert "squads_reprises_dans_politique" in (tmp_path / "strategie" / "journal.jsonl").read_text("utf-8")


def test_candidats_dans_un_perimetre(st):
    """De l'US au test à automatiser, dans un périmètre borné : US, sprint (photo figée) ou module. Chaque candidat porte
    les US qu'il couvre et son statut de revue ; « Prêt pour l'automatisation » passe en tête."""
    import json

    from atelier.generation import conception
    from atelier.intelligence import testabilite_us as t

    d = st.candidats_perimetre()
    assert d["total"] == 9 and d["perimetre"] is None and len(d["candidats"]) == 9
    par_cle = {c["cle"]: c for c in d["candidats"]}
    assert [x["cle"] for x in par_cle["DEMO-304"]["exigences"]] == ["DEMO-311"] and par_cle["DEMO-304"]["revue"] == "Draft"
    assert ("us:DEMO-311", 2) in [(p["noeud"], p["tests"]) for p in d["perimetres"]]
    assert ("module:Connexion", 9) in [(p["noeud"], p["tests"]) for p in d["perimetres"]]
    assert [c["cle"] for c in d["candidats"]][:2] == ["DEMO-308", "DEMO-309"]            # non automatisés d'abord

    # périmètre « US » : seulement les tests qui la couvrent
    d = st.candidats_perimetre("us:DEMO-311")
    assert sorted(c["cle"] for c in d["candidats"]) == ["DEMO-304", "DEMO-306"] and d["perimetre"]["type"] == "us" and d["automatises"] == 2
    assert [c["cle"] for c in st.candidats_perimetre("module:Connexion")["candidats"]] == [c["cle"] for c in st.candidats_perimetre()["candidats"]]
    for inconnu in ("us:DEMO-999", "module:Inconnu", "sprint:SQ1|12", "n'importe quoi"):
        with pytest.raises(KeyError, match="Périmètre inconnu"):
            st.candidats_perimetre(inconnu)                                               # jamais une liste silencieusement non bornée

    # la revue de Test Design ordonne : « Prêt pour l'automatisation » en tête
    conception._dossier().mkdir(parents=True, exist_ok=True)
    (conception._dossier() / "revues.json").write_text(json.dumps({"test:DEMO-309": {"statut": "Ready for Automation", "historique": []}}), "utf-8")
    d = st.candidats_perimetre()
    assert d["candidats"][0]["cle"] == "DEMO-309" and d["candidats"][0]["pret"] and d["prets"] == 1
    assert d["candidats"][0]["revue_libelle"] == "Prêt pour l'automatisation"

    # périmètre « sprint » : les US du sprint suivies par la testabilité, avec leurs tests liés ; US sans test signalées
    t.enregistrer_espace({"projet_jira": "SQ1", "projet_xray": "DEMO"})
    us = {k: {"cle": k, "espace": "SQ1", "resume": r, "statut": "Détectée", "tests_lies": tl, "sprints": {"12": {"nom": "Sprint 12", "etat": "active"}}}
          for k, r, tl in (("SQ1-1", "Verrouillage du compte", ["DEMO-308"]), ("SQ1-2", "Mot de passe oublié", []))}
    t._sauver_us(us)
    d = st.candidats_perimetre("sprint:SQ1|12")
    assert [c["cle"] for c in d["candidats"]] == ["DEMO-308"] and d["perimetre"]["us"] == 2 and d["perimetre"]["fige"] is False
    assert [x["cle"] for x in d["candidats"][0]["exigences"]] == ["DEMO-312", "SQ1-1"]     # copie Xray et tests liés de la testabilité
    assert [x["cle"] for x in d["us_sans_test"]] == ["SQ1-2"]
    assert st.candidats_perimetre("us:SQ1-2")["candidats"] == []                          # US connue, pas encore de test : liste vide, pas une erreur
    t.figer_sprint("SQ1", "12")
    us["SQ1-3"] = {"cle": "SQ1-3", "espace": "SQ1", "resume": "Ajoutée en cours de sprint", "statut": "Détectée", "tests_lies": ["DEMO-309"],
                   "sprints": {"12": {"nom": "Sprint 12", "etat": "active"}}}
    t._sauver_us(us)
    d = st.candidats_perimetre("sprint:SQ1|12")
    assert d["perimetre"]["fige"] and d["perimetre"]["us"] == 2 and [c["cle"] for c in d["candidats"]] == ["DEMO-308"]   # la photo figée fait foi


def test_construction_lancee_fait_avancer_une_decision_approuvee(st):
    """Lancer la construction ne change que « Approuvé » → « En construction » : toute autre décision reste humaine."""
    _remplir(st)
    assert st.marquer_en_construction("DEMO-308") == {"cle": "DEMO-308", "change": False, "statut": ""}          # aucune décision
    st.decider_candidat("DEMO-308", "Approuvé", "Robot + Playwright", "2 j", "prioritaire")
    st.decider_candidat("DEMO-309", "Rejeté", commentaire="hors périmètre")
    assert st.marquer_en_construction("DEMO-308", "Automation Studio")["change"] is True
    plan = {c["cle"]: c for c in st.plan_automatisation()}
    assert plan["DEMO-308"]["statut_plan"] == "En construction"
    assert (plan["DEMO-308"]["decision"]["framework"], plan["DEMO-308"]["decision"]["effort"], plan["DEMO-308"]["decision"]["commentaire"]) == ("Robot + Playwright", "2 j", "prioritaire")
    assert st.marquer_en_construction("DEMO-308")["change"] is False                                              # déjà en construction
    assert st.marquer_en_construction("DEMO-309") == {"cle": "DEMO-309", "change": False, "statut": "Rejeté"}     # un rejet ne bouge pas
    assert {c["cle"]: c for c in st.plan_automatisation()}["DEMO-309"]["statut_plan"] == "Rejeté"


def test_fil_de_l_us_au_test_automatise(st):
    """L'étape d'une US se déduit de ses tests : à concevoir (aucun test), à décider, à construire (test approuvé ou
    prêt), en construction, automatisée (tous ses tests ont un script). Un parcours utilisateur est aussi un périmètre."""
    from atelier.discovery import parcours_utilisateur as pu
    from atelier.intelligence import testabilite_us as t

    T = lambda **k: {"automatise": False, "statut_plan": "À analyser", "pret": False, **k}  # noqa: E731
    assert st.etape_us([]) == "a_concevoir"
    assert st.etape_us([T()]) == "a_decider"
    assert st.etape_us([T(pret=True)]) == "a_construire" and st.etape_us([T(statut_plan="Approuvé")]) == "a_construire"
    assert st.etape_us([T(statut_plan="En construction"), T(statut_plan="Approuvé")]) == "en_construction"
    assert st.etape_us([T(automatise=True), T()]) == "a_decider"                           # tant qu'un test reste à faire, l'US n'est pas automatisée
    assert st.etape_us([T(automatise=True), T(automatise=True, statut_plan="Rejeté")]) == "automatisee"

    _remplir(st)
    d = st.candidats_perimetre()
    us = {u["cle"]: u for u in d["us"]}
    assert us["DEMO-311"]["etape"] == "automatisee" and (us["DEMO-311"]["tests"], us["DEMO-311"]["automatises"]) == (["DEMO-304", "DEMO-306"], 2)
    assert us["DEMO-312"]["etape"] == "a_decider"                                          # DEMO-308, pas encore décidé
    assert [e["id"] for e in d["etapes"]] == ["a_concevoir", "a_decider", "a_construire", "en_construction", "automatisee"]
    assert sum(e["us"] for e in d["etapes"]) == len(d["us"]) and all(e["a_faire"] and e["ecran"] for e in d["etapes"])
    st.decider_candidat("DEMO-308", "Approuvé")
    assert {u["cle"]: u["etape"] for u in st.candidats_perimetre("us:DEMO-312")["us"]} == {"DEMO-312": "a_construire"}
    st.marquer_en_construction("DEMO-308")
    assert st.candidats_perimetre("us:DEMO-312")["us"][0]["etape"] == "en_construction"

    # une US suivie sans test ouvre le fil : à concevoir
    t.enregistrer_espace({"projet_jira": "SQ1", "projet_xray": "DEMO"})
    t._sauver_us({"SQ1-2": {"cle": "SQ1-2", "espace": "SQ1", "resume": "Mot de passe oublié", "statut": "Détectée", "tests_lies": [],
                            "sprints": {"12": {"nom": "Sprint 12", "etat": "active"}}}})
    d = st.candidats_perimetre("sprint:SQ1|12")
    assert [(u["cle"], u["etape"], u["suivie"]) for u in d["us"]] == [("SQ1-2", "a_concevoir", True)] and d["candidats"] == []

    # un parcours utilisateur borne le fil à ses exigences rattachées
    p = pu.enregistrer("", {"nom": "Récupérer son accès", "plateforme": "web", "exigences": ["DEMO-311", "DEMO-312"]})
    d = st.candidats_perimetre(f"parcours:{p['id']}")
    assert d["perimetre"]["type"] == "parcours" and d["perimetre"]["us"] == 2
    assert sorted(c["cle"] for c in d["candidats"]) == ["DEMO-304", "DEMO-306", "DEMO-308"]
    assert [(u["cle"], u["etape"]) for u in d["us"]] == [("DEMO-312", "en_construction"), ("DEMO-311", "automatisee")]
    assert (f"parcours:{p['id']}", 3) in [(x["noeud"], x["tests"]) for x in d["perimetres"]]
    with pytest.raises(KeyError, match="Périmètre inconnu"):
        st.candidats_perimetre("parcours:PU-inconnu")
