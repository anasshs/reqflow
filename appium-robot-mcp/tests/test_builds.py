"""Qualification d'une release build après build : création, réception des builds, comparaison avec le précédent et le
périmètre initial, périmètre en trois catégories (retest, non-régression ciblée, qualification), décisions du QA,
verdict de build, critères de sortie et qualification de la release. Projet de démonstration, données fictives."""
from datetime import date, datetime, timedelta

import pytest

from tests.test_releases import rel  # noqa: F401 — projet de démonstration isolé

AUJ = date.today().isoformat()
HIER = (date.today() - timedelta(days=1)).isoformat()
NOTE = """Release 3.0.0

Nouveautés
- DEMO-312 : réinitialisation du mot de passe par e-mail
"""
BUILD1 = """Évolutions
- DEMO-312 : lien de réinitialisation valable 24 h
Corrections
- DEMO-777 : le compte n'était plus bloqué après trois échecs
"""
BUILD2 = """Évolutions
- DEMO-312 : lien de réinitialisation valable 24 h
- DEMO-313 : déconnexion depuis toutes les pages
"""


@pytest.fixture
def b(rel):  # noqa: F811
    """Copie Xray de démonstration complétée : un bug DEMO-777 (lié au test DEMO-304), des résultats d'exécution."""
    from atelier.intelligence import builds, patrimoine_xray, pilotage

    pat = patrimoine_xray.charger()
    next(t for t in pat["tests"] if t["cle"] == "DEMO-301")["module"] = "Accueil"   # un test critique hors du module touché
    pat["executions"] = [{"cle": "DEMO-900", "resume": "Recette 3.0", "statut": "En cours", "assigne": "", "resolu": "",
                          "runs": {"DEMO-304": {"statut": "FAILED", "defauts": ["7"]}},
                          "bugs": [{"id": "7", "cle": "DEMO-777", "resume": "Blocage du compte inopérant", "statut": "Ouvert", "ferme": False,
                                    "priorite": "Highest", "assigne": "", "cree": HIER + "T09:00:00", "resolu": ""}]}]
    patrimoine_xray.enregistrer(pat, "test")
    pilotage.vider_memo()
    return builds


def _resultat(cles, statut, jour=AUJ):
    from atelier.intelligence import patrimoine_xray, pilotage

    pat = patrimoine_xray.charger()
    for t in pat["tests"]:
        if t["cle"] in cles:
            # un résultat posé « aujourd'hui » l'est maintenant, donc après la réception des builds du test
            t["statut_xray"] = {"statut": statut, "fin": datetime.now().isoformat(timespec="seconds") if jour == AUJ else jour + "T10:00:00"}
    patrimoine_xray.enregistrer(pat, "test")
    pilotage.vider_memo()


def _bug(cle, ferme):
    from atelier.intelligence import patrimoine_xray, pilotage

    pat = patrimoine_xray.charger()
    for e in pat["executions"]:
        for x in e["bugs"]:
            if x["cle"] == cle:
                x.update(ferme=ferme, statut="Terminé" if ferme else "Ouvert")
    patrimoine_xray.enregistrer(pat, "test")
    pilotage.vider_memo()


def test_creation_d_une_release_sans_puis_avec_release_note(rel, b):  # noqa: F811
    r = rel.creer("", nom="Release 3.0", version="3.0.0", date_prevue="15/12/2026", perimetre="Mot de passe et déconnexion")
    assert (r["version"], r["date_prevue"], r["perimetre"], r["evolutions"], r["source"]) == ("3.0.0", "2026-12-15", "Mot de passe et déconnexion", [], "saisie")
    with pytest.raises(ValueError, match="Nommer la release"):
        rel.creer("")
    with pytest.raises(ValueError, match="Date illisible"):
        rel.creer("", nom="X", date_prevue="demain")
    r = rel.operer(r["id"], "note", texte=NOTE)
    assert len(r["evolutions"]) == 1 and r["evolutions"][0]["etat"] == "rattachée"
    with pytest.raises(ValueError, match="déjà sa Release Note"):
        rel.operer(r["id"], "note", texte=NOTE)
    r = rel.operer(r["id"], "renommer", nom="Release 3.0 bis", date_prevue="2026-12-20", perimetre="Accès")
    assert (r["nom"], r["date_prevue"], r["perimetre"]) == ("Release 3.0 bis", "2026-12-20", "Accès")


def test_build_compare_retest_ciblee_qualification(rel, b):  # noqa: F811
    r = rel.creer(NOTE, nom="Release 3.0", version="3.0.0")
    v = b.recevoir(r["id"], "3.0.0-b1", AUJ, "Première livraison", BUILD1, anomalies="")
    c = v["comparaison"]
    # comparaison : premier build, comparé au périmètre initial
    assert c["precedent"] == "" and v["anomalies_citees"] == ["DEMO-777"] and v["anomalies_declarees"] == []
    assert c["anomalies_a_retester"][0]["cle"] == "DEMO-777" and c["anomalies_a_retester"][0]["tests"] == ["DEMO-304"]
    e = {x["id"]: x for x in v["evolutions"]}
    assert e["E1"]["nouveaute"] == "touche le périmètre existant" and e["E2"]["type"] == "correction"
    assert c["corrections"] == ["E2"] and c["fonctionnalites_nouvelles"] == [] and c["hors_perimetre_initial"] == []
    # périmètre : trois catégories, chaque test avec sa raison
    p = {x["test"]: x for x in v["perimetre"]}
    assert p["DEMO-304"]["categorie"] == "retest" and "DEMO-777" in p["DEMO-304"]["motifs"][0]
    assert p["DEMO-308"]["categorie"] == "ciblee" and p["DEMO-308"]["impact"] == "direct"
    assert any(x["categorie"] == "ciblee" and x["impact"] == "indirect" for x in v["perimetre"])
    assert p["DEMO-301"]["categorie"] == "qualification" and p["DEMO-301"]["motifs"] == ["criticité métier (Haute)"]
    assert "criticité métier (Haute)" in p["DEMO-302"]["motifs"] and p["DEMO-302"]["categorie"] == "ciblee"   # critique ET touché : ciblé, les deux raisons gardées
    assert v["anomalies"]["corrigees_non_confirmees"][0]["cle"] == "DEMO-777"          # déclarée corrigée, encore ouverte dans Jira
    with pytest.raises(FileExistsError):
        b.recevoir(r["id"], "3.0.0-B1")

    # décisions du QA, validation, verdict
    with pytest.raises(ValueError, match="Justifier"):
        b.operer(r["id"], v["id"], "decider", test="DEMO-302", decision="rejetée")
    v = b.operer(r["id"], v["id"], "decider", test="DEMO-302", decision="rejetée", motif="hors périmètre fonctionnel")
    v = b.operer(r["id"], v["id"], "decider", test="DEMO-309", decision="ajoutée", motif="session expirée sur reset")
    assert {x["test"]: x["decision"] for x in v["perimetre"]}["DEMO-309"] == "ajoutée"
    with pytest.raises(ValueError, match="Valider d'abord"):
        b.operer(r["id"], v["id"], "passed")
    v = b.operer(r["id"], v["id"], "valider")
    assert v["statut"] == "Périmètre validé" and "DEMO-302" not in v["perimetre_valide"]["tests"] and "DEMO-309" in v["perimetre_valide"]["tests"]
    with pytest.raises(PermissionError):
        b.operer(r["id"], v["id"], "decider", test="DEMO-303", decision="rejetée", motif="trop tard pour ce build")
    v = b.operer(r["id"], v["id"], "campagne")
    assert v["statut"] == "En exécution" and v["campagnes"][0]["tests"] >= 1
    with pytest.raises(ValueError, match="justifier le verdict"):
        b.operer(r["id"], v["id"], "passed")                                          # rien n'est encore exécuté
    _resultat(set(v["perimetre_valide"]["tests"]), "PASSED")
    _bug("DEMO-777", True)
    v = b.vue(r["id"], v["id"])
    assert v["resultats"]["non_executes"] == 0 and v["resultats"]["reussis"] == v["resultats"]["retenus"]
    assert [x["cle"] for x in v["anomalies"]["corrigees"]] == ["DEMO-777"]
    v = b.operer(r["id"], v["id"], "passed")
    assert v["statut"] == "Passed" and v["verdict"]["resultats"]["reussis"] == v["resultats"]["retenus"]

    # deuxième build : comparé au premier, continuité gardée
    v2 = b.recevoir(r["id"], "3.0.0-b2", AUJ, "Ajout de la déconnexion", BUILD2, changements="Ajout DEMO-313")
    e = {x["id"]: x for x in v2["evolutions"]}
    assert v2["comparaison"]["precedent"] == "3.0.0-b1" and e["E1"]["nouveaute"] == "déjà livrée" and e["E2"]["nouveaute"] == "nouvelle"
    assert [x["noeud"] for x in v2["comparaison"]["fonctionnalites_nouvelles"]] == ["user_story:DEMO-313"]
    assert [x["noeud"] for x in v2["comparaison"]["hors_perimetre_initial"]] == ["user_story:DEMO-313"]
    assert v2["comparaison"]["anomalies_a_retester"] == []
    assert b.vue(r["id"], v["id"])["statut"] == "Passed"                                 # le build 1 garde son historique

    # vue release : un build Passed ne qualifie pas la release
    t = b.tableau(r["id"])
    assert t["indicateurs"]["builds"] == 2 and t["indicateurs"]["builds_passed"] == 1 and t["qualification"]["etat"] == "En cours"
    crit = {c["id"]: c for c in t["criteres_sortie"]}
    assert crit["dernier_build"]["etat"] == "non satisfait" and crit["anomalies_critiques"]["etat"] == "satisfait"
    with pytest.raises(ValueError, match="dérogation"):
        b.qualifier(r["id"])
    t = b.qualifier(r["id"], motif="Build 2 en cours, mise en production validée par le comité")
    assert t["qualification"]["etat"] == "Qualifiée par dérogation" and t["qualification"]["criteres_non_satisfaits"]
    v2 = b.operer(r["id"], v2["id"], "valider")
    assert b.tableau(r["id"])["qualification"]["etat"] == "En cours"                      # un build a changé : la qualification est à refaire
    _resultat(set(v2["perimetre_valide"]["tests"]), "PASSED")
    b.operer(r["id"], v2["id"], "passed")
    t = b.qualifier(r["id"])
    assert t["qualification"]["etat"] == "Qualifiée" and t["indicateurs"]["bloquants_non_satisfaits"] == 0


def test_corrections_des_evolutions_d_un_build_et_routes(rel, b, monkeypatch, tmp_path):  # noqa: F811
    from fastapi.testclient import TestClient

    from web_app_loader import charger_app_web, module_web

    r = rel.creer("", nom="Release 3.1")
    v = b.recevoir(r["id"], "b1", AUJ, "", "- Possibilité de se déconnecter depuis toutes les pages")
    assert v["evolutions"][0]["etat"] == "à trancher"
    v = b.operer(r["id"], v["id"], "valider") if v["perimetre"] else v
    v = rel.operer(r["id"], "relier", build=v["id"], evolution="E1", noeud="user_story:DEMO-313")
    assert v["evolutions"][0]["etat"] == "rattachée" and v["statut"] == "Reçu"           # périmètre à revalider après correction
    assert "DEMO-307" in {x["test"] for x in v["perimetre"]}

    monkeypatch.setattr(module_web(), "CONFIG_PATH", tmp_path / "atelier.json")
    c = TestClient(charger_app_web(), base_url="http://127.0.0.1:8765")
    assert c.get("/plateforme").status_code == 200
    n = c.post("/api/releases", json={"nom": "Release 4", "version": "4.0", "date_prevue": "2026-12-01", "perimetre": "Tout"}).json()
    assert n["date_prevue"] == "2026-12-01"
    x = c.post(f"/api/releases/{n['id']}/builds", json={"numero": "4.0-b1", "texte": BUILD1, "anomalies": "DEMO-777"}).json()
    assert x["anomalies_declarees"] == ["DEMO-777"] and x["perimetre"]
    assert c.get(f"/api/releases/{n['id']}/builds/{x['id']}").json()["numero"] == "4.0-b1"
    assert c.post(f"/api/releases/{n['id']}/builds/{x['id']}/operation", json={"op": "decider", "test": "DEMO-301", "decision": "rejetée", "motif": "non concerné"}).status_code == 200
    assert c.post(f"/api/releases/{n['id']}/builds/{x['id']}/operation", json={"op": "rejeter", "evolution": "E1", "noeud": "inexistant"}).status_code == 400
    assert c.get(f"/api/releases/{n['id']}/tableau").json()["indicateurs"]["builds"] == 1
    assert c.post(f"/api/releases/{n['id']}/qualifier", json={}).status_code == 400
    assert c.post(f"/api/releases/{n['id']}/builds/{x['id']}/operation", json={"op": "supprimer"}).json() == {"supprime": x["id"]}


class XrayPlan:
    """Faux Xray : Test Plan, Test Executions avec environnement, test runs et statuts. Trace chaque écriture."""
    def __init__(self, absents=()):
        self.plans, self.execs, self.statuts, self.absents, self.n = {}, {}, {}, set(absents), 100

    def _id(self):
        self.n += 1
        return str(self.n)

    def test_ids(self, cles):
        return {c: "t" + c.split("-")[1] for c in cles if c not in self.absents}

    def create_plan(self, projet, resume, tests):
        i = self._id()
        self.plans[i] = {"cle": f"{projet}-{i}", "resume": resume, "tests": set(tests), "execs": []}
        return i, f"{projet}-{i}"

    def create_execution(self, projet, resume, tests, envs):
        i = self._id()
        self.execs[i] = {"cle": f"{projet}-{i}", "resume": resume, "tests": list(tests), "envs": list(envs)}
        return i, f"{projet}-{i}"

    def add_execs_to_plan(self, plan, execs):
        self.plans[plan]["execs"] += execs

    def add_tests_to_plan(self, plan, tests):
        self.plans[plan]["tests"] |= set(tests)

    def test_runs(self, exec_id, tests):
        return {t: f"run-{exec_id}-{t}" for t in tests if t in self.execs[exec_id]["tests"]}

    def set_status(self, run, statut):
        self.statuts[run] = statut

    def update_run(self, run, comment=None, **_):
        self.statuts[run + ":commentaire"] = comment


@pytest.fixture
def plan(b, monkeypatch):
    from atelier.domain import projets
    from atelier.integrations.xray import environnements
    from atelier.intelligence import plan_release

    monkeypatch.setattr(projets, "cle_xray", lambda: "DEMO")
    monkeypatch.setattr(environnements, "liste", lambda: ["RECETTE", "PREPROD"])
    return plan_release


def test_plan_xray_de_la_release_et_executions_par_type(rel, b, plan):  # noqa: F811
    r = rel.creer(NOTE, nom="Release 3.0", version="3.0.0")
    v = b.recevoir(r["id"], "b1", AUJ, "", BUILD1)
    x = XrayPlan(absents={"DEMO-309"})
    # avant validation du périmètre : exécutions proposées par type, ou par module
    g = plan.proposer(r["id"], v["id"], "type")
    assert [y["groupe"] for y in g] == ["retest", "ciblee", "qualification"] and g[0]["tests"] == ["DEMO-304"]
    assert {y["groupe"] for y in plan.proposer(r["id"], v["id"], "module")} == {"Connexion", "Accueil"}
    assert len(plan.proposer(r["id"], v["id"], "unique")) == 1
    e = plan.creer_executions(r["id"], v["id"], [{**g[0], "environnement": "RECETTE"}, {**g[1], "environnement": "RECETTE"}], xray=x)
    assert e["plan"]["cle"].startswith("DEMO-") and len(e["executions"]) == 2 and len(e["creees"]) == 2
    xp = next(iter(x.plans.values()))
    assert xp["resume"] == "Release Release 3.0 (3.0.0)" and len(xp["execs"]) == 2                 # dans Xray : le plan, ses exécutions…
    assert set(xp["tests"]) == {t for i in xp["execs"] for t in x.execs[i]["tests"]}                # … et leurs tests
    assert all(x.execs[i]["envs"] == ["RECETTE"] for i in xp["execs"])
    ciblee = next(y for y in e["executions"] if y["groupe"] == "ciblee")
    assert ciblee["absents"] == ["DEMO-309"] and "DEMO-309" not in ciblee["tests"]                  # absent de Xray : signalé, pas envoyé
    assert next(y for y in plan.proposer(r["id"], v["id"], "type") if y["groupe"] == "retest")["deja"] == ["DEMO-304"]
    with pytest.raises(FileExistsError, match="déjà son Test Plan"):
        plan.creer_plan(r["id"], xray=x)
    with pytest.raises(ValueError, match="Environnement inconnu"):
        plan.creer_executions(r["id"], v["id"], [{**g[2], "environnement": "PROD"}], xray=x)

    # dupliquer pour un autre environnement du projet ; pas deux fois
    retest = next(y for y in e["executions"] if y["groupe"] == "retest")
    assert retest["envs_libres"] == ["PREPROD"]
    e = plan.dupliquer(r["id"], retest["id"], "PREPROD", xray=x)
    copie = next(y for y in e["executions"] if y["copie_de"] == retest["id"])
    assert copie["environnement"] == "PREPROD" and copie["tests"] == retest["tests"] and copie["nom"].endswith("· PREPROD") and "RECETTE" not in copie["nom"]
    with pytest.raises(FileExistsError):
        plan.dupliquer(r["id"], retest["id"], "PREPROD", xray=x)

    # statut mis à jour depuis l'atelier : envoyé à Xray, compté dans les résultats du build
    e = plan.maj_statut(r["id"], retest["id"], "DEMO-304", "PASSED", "rejoué après correction", xray=x)
    assert x.statuts[f"run-{retest['xray']['issueId']}-t304"] == "PASSED" and x.statuts[f"run-{retest['xray']['issueId']}-t304:commentaire"]
    assert next(y for y in e["executions"] if y["id"] == retest["id"])["compte"]["PASSED"] == 1
    l = {y["test"]: y for y in b.vue(r["id"], v["id"])["perimetre"]}
    assert (l["DEMO-304"]["execute"], l["DEMO-304"]["resultat"]) == (True, "reussi")
    with pytest.raises(ValueError, match="Statut"):
        plan.maj_statut(r["id"], retest["id"], "DEMO-304", "OK", xray=x)
    with pytest.raises(KeyError):
        plan.maj_statut(r["id"], retest["id"], "DEMO-301", "PASSED", xray=x)


def test_un_seul_environnement_pas_de_duplication(rel, b, plan, monkeypatch):  # noqa: F811
    from atelier.integrations.xray import environnements

    monkeypatch.setattr(environnements, "liste", lambda: ["RECETTE"])
    r = rel.creer(NOTE, nom="Release 3.1")
    v = b.recevoir(r["id"], "b1", AUJ, "", BUILD1)
    x = XrayPlan()
    e = plan.creer_executions(r["id"], v["id"], plan.proposer(r["id"], v["id"], "unique"), xray=x)
    assert not e["multi_environnements"] and e["executions"][0]["envs_libres"] == []
    with pytest.raises(ValueError, match="plusieurs environnements"):
        plan.dupliquer(r["id"], e["executions"][0]["id"], "RECETTE", xray=x)


def test_actualiser_depuis_xray_dans_la_vue_du_build(rel, b, monkeypatch):  # noqa: F811
    """Les PASSED / FAILED posés dans Xray sont relus depuis la vue du build : lecture des exécutions depuis la réception
    du build, puis vue recalculée. Une erreur Xray ne modifie rien."""
    from atelier.intelligence import patrimoine_xray

    r = rel.creer(NOTE, nom="Release 3.2")
    v = b.recevoir(r["id"], "b1", AUJ, "", BUILD1)
    appels = []

    def lecture(projet, xray, depuis, jusqu):  # Xray simulé : DEMO-304 passé dans Xray
        appels.append((depuis, jusqu))
        _resultat({"DEMO-304"}, "PASSED")
        return {"lues": 3, "nombre": 12}
    monkeypatch.setattr(patrimoine_xray, "importer_executions", lecture)
    vu = b.actualiser_xray(r["id"], v["id"])
    assert appels == [(AUJ, "")]
    assert vu["lecture_xray"]["executions"] == 3
    assert next(x for x in vu["perimetre"] if x["test"] == "DEMO-304")["resultat"] == "reussi"

    def panne(*a):
        raise RuntimeError("Xray injoignable")
    monkeypatch.setattr(patrimoine_xray, "importer_executions", panne)
    with pytest.raises(RuntimeError):
        b.actualiser_xray(r["id"], v["id"])
    assert b.vue(r["id"], v["id"])["lecture_xray"]["executions"] == 3


def test_build_remplace_et_qualification_a_refaire(rel, b):  # noqa: F811
    """Un nouveau build remplace le build encore en cours (lecture seule) et remet une release qualifiée « En cours » ;
    sa suppression rend la main au build remplacé. Plusieurs tests s'écartent d'un coup, avec un seul motif."""
    r = rel.creer(NOTE, nom="Release 3.3")
    v1 = b.recevoir(r["id"], "b1", AUJ, "", BUILD1)
    v1 = b.operer(r["id"], v1["id"], "decider", tests=["DEMO-302", "DEMO-303"], decision="rejetée", motif="hors périmètre du build")
    assert {x["test"]: x["decision"] for x in v1["perimetre"]}["DEMO-303"] == "rejetée"
    b.operer(r["id"], v1["id"], "valider")
    b.qualifier(r["id"], motif="mise en production décidée par le comité de release")
    assert b.tableau(r["id"])["qualification"]["etat"] == "Qualifiée par dérogation"

    v2 = b.recevoir(r["id"], "b2", AUJ, "", BUILD2)
    t = b.tableau(r["id"])
    assert t["qualification"]["etat"] == "En cours" and t["courant"] == v2["id"]
    assert [(x["numero"], x["statut"], x["remplace_par"]) for x in t["builds"]] == [("b1", "Remplacé", "b2"), ("b2", "Reçu", "")]
    with pytest.raises(PermissionError, match="remplacé par le build b2"):
        b.operer(r["id"], v1["id"], "passed")
    b.operer(r["id"], v2["id"], "supprimer")
    assert b.tableau(r["id"])["builds"][0]["statut"] == "Périmètre validé"                 # le build remplacé reprend son statut


def test_delta_avec_le_build_precedent(rel, b):  # noqa: F811
    """Chaque test du build est situé par rapport au build précédent : nouveau, à rejouer (échec), déjà réussi et non
    touché de nouveau (candidat à écarter), reconduit."""
    r = rel.creer(NOTE, nom="Release 3.4")
    v1 = b.recevoir(r["id"], "b1", HIER, "", BUILD1)
    v1 = b.operer(r["id"], v1["id"], "valider")
    _resultat({"DEMO-303"}, "PASSED", HIER)
    _resultat({"DEMO-304"}, "FAILED", HIER)
    v2 = b.recevoir(r["id"], "b2", AUJ, "", BUILD2)
    d = {x["test"]: x for x in v2["perimetre"]}
    assert d["DEMO-304"]["delta"] == "a_rejouer" and d["DEMO-304"]["resultat_precedent"] == "echec"
    assert d["DEMO-303"]["delta"] == "deja_reussi"                                       # réussi sur b1, touché seulement par son module
    assert all(x["delta"] == "nouveau" for x in v2["perimetre"] if x["test"] not in v1["perimetre_valide"]["tests"])
    delta = v2["comparaison"]["delta"]
    assert delta["precedent"] == "b1" and delta["a_rejouer"] >= 1 and delta["deja_reussi"] >= 1
    assert "delta" not in b.vue(r["id"], v1["id"])["comparaison"]                         # premier build : rien à comparer


def test_campagnes_par_execution_xray(rel, b, plan, monkeypatch):  # noqa: F811
    """Exécution unifiée : une campagne par Test Execution Xray du build, qui réutilise cette exécution pour ses résultats."""
    from atelier.execution import centre
    from atelier.intelligence import pilotage

    r = rel.creer(NOTE, nom="Release 3.5")
    v = b.recevoir(r["id"], "b1", AUJ, "", BUILD1)
    v = b.operer(r["id"], v["id"], "valider")
    autos = [x["test"] for x in v["perimetre"] if x["automatise"] and x["test"] in v["perimetre_valide"]["tests"]]
    assert autos, "le projet de démonstration doit avoir des tests automatisés"
    x = XrayPlan()
    e = plan.creer_executions(r["id"], v["id"], plan.proposer(r["id"], v["id"], "type"), xray=x)
    v = b.operer(r["id"], v["id"], "campagne", par_execution=True)
    camps = {c["id"]: c for c in centre.campagnes()}
    liees = [c for c in v["campagnes"] if c.get("execution")]
    assert liees and v["statut"] == "En exécution"
    for c in liees:
        assert camps[c["id"]]["mode_execution"] == "reutiliser" and camps[c["id"]]["execution_xray"] == c["execution"]
        assert set(camps[c["id"]]["tests"]) <= set(autos)
    assert {c["execution"] for c in liees} <= {ex["xray"]["cle"] for ex in e["executions"]}
    with pytest.raises(ValueError, match="déjà créées"):
        b.operer(r["id"], v["id"], "campagne", par_execution=True)
    pilotage.vider_memo()


def test_resultat_compte_apres_la_reception_a_l_heure_pres(b):  # noqa: F811
    """Deux builds reçus le même jour ne partagent pas leurs résultats : le jour de la réception, l'heure fait foi."""
    b1 = {"date_reception": "2026-11-21", "recu_le": "2026-11-21T09:00:00"}
    assert b.apres_reception(b1, "2026-11-21T09:30:00") and not b.apres_reception(b1, "2026-11-21T08:59:00")
    assert b.apres_reception(b1, "2026-11-22T01:00:00") and not b.apres_reception(b1, "2026-11-20T23:00:00")
    saisi = {"date_reception": "2026-11-18", "recu_le": "2026-11-21T09:00:00"}                # date de réception saisie dans le passé
    assert b.apres_reception(saisi, "2026-11-18T07:00:00")
