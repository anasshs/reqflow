"""Maintenance d'un test en échec depuis le Kanban : colonne « À maintenir », cause qualifiée (suggestion de Failure
Analysis), maintenance par le MCP (consigne, scénario BDD modifiable seulement pendant une maintenance, compte rendu),
rien de cassé ailleurs (fichier partagé modifié : tests impactés en maintenance, rejoués avant toute confirmation),
confirmation humaine (Xray mis à jour si le scénario a changé, commit), refus qui relance l'agent, merge request,
drapeau « maintenu »."""
import pytest

TID = "tests/carte.robot::CARTE"
TID_SOLDE = "tests/solde.robot::SOLDE"
ROBOT = """*** Settings ***
Resource    ../resources/commun.resource

*** Test Cases ***
{cle}
    [Tags]    {cle}
    Ouvrir Le Menu
"""


@pytest.fixture
def atelier(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.domain import projet
    from atelier.execution import orchestrateur, robot
    from atelier.generation import bdd

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    monkeypatch.setenv("ATELIER_FLUX", "simple")
    monkeypatch.setattr(orchestrateur, "demarrer", lambda: None)
    carte.creer_app("Banque Démo", ["android"])
    (tmp_path / "tests").mkdir()
    (tmp_path / "resources").mkdir()
    (tmp_path / "resources" / "commun.resource").write_text("*** Keywords ***\nOuvrir Le Menu\n    No Operation\n", "utf-8")
    for cle, titre in (("CARTE", "Carte"), ("SOLDE", "Solde")):
        bdd.creer(cle, titre)
        bdd.depuis_texte(cle, f"# language: fr\nFonctionnalité: {titre}\n  Scénario: {titre}\n    Quand j'ouvre la carte\n    Alors la carte est affichée\n")
        m = bdd.charger(cle)
        m["application"] = carte.app_courante()
        bdd.sauver(m)
        (tmp_path / "tests" / f"{cle.lower()}.robot").write_text(ROBOT.format(cle=cle), "utf-8")
    runs = {}
    monkeypatch.setattr(robot, "derniers_resultats", lambda dossier="results", reels=False: dict(runs))
    return runs


def _run(runs, statut, message="", fin="2099-01-01T10:00:00", tid=TID):
    runs[tid] = {"statut": statut, "message": message, "fin": fin, "reel": True, "output": ""}


def _carte(cle="CARTE"):
    from atelier.generation import kanban

    return next(x for x in kanban.tableau()["tickets"] if x["id"] == cle)


def test_un_echec_arrive_dans_a_maintenir_avec_une_cause_suggeree(atelier):
    _run(atelier, "PASS", fin="2000-01-01T10:00:00")
    assert _carte()["colonne"] == "automatise" and _carte()["maintenance"] is None
    _run(atelier, "FAIL", "Element 'id=carte' did not match any elements after 10 seconds.", fin="2000-01-02T10:00:00")
    c = _carte()
    assert c["colonne"] == "maintenance" and c["colonne_flux"] == "automatise"
    assert c["maintenance"]["etat"] == "a_qualifier" and c["maintenance"]["suggestion"]["cause"] == "test"


def test_anomalie_de_l_application_puis_run_reussi(atelier):
    from atelier.generation import maintenir

    _run(atelier, "FAIL", "Attendu : 120 trouvé : 0", fin="2000-01-02T10:00:00")
    assert _carte()["maintenance"]["suggestion"]["cause"] == "application"
    maintenir.qualifier("CARTE", "application", "Le solde n'est plus calculé : anomalie remontée")
    assert _carte()["maintenance"]["etat"] == "application" and _carte()["colonne"] == "maintenance"
    _run(atelier, "PASS")                                                        # l'application est corrigée
    assert _carte()["maintenance"] is None and _carte()["colonne"] == "automatise"
    with pytest.raises(ValueError):
        maintenir.qualifier("CARTE", "n_importe_quoi")


def test_maintenance_par_le_mcp_confirmee(atelier, monkeypatch):
    from atelier.adapters import facade
    from atelier.execution import orchestrateur
    from atelier.generation import bdd, flux, kanban, maintenir

    _run(atelier, "FAIL", "Element 'id=carte' did not match any elements", fin="2000-01-02T10:00:00")
    with pytest.raises(PermissionError):                                         # pas de maintenance ouverte : scénario intouchable
        maintenir.modifier_bdd("CARTE", "# language: fr\nFonctionnalité: X\n  Scénario: X\n    Quand x\n    Alors y\n", "l'écran a changé de nom")
    r = kanban.deplacer("CARTE", "maintenance")                                  # glisser vers « À maintenir »
    orchestrateur.annuler(r["travail"])
    r = maintenir.qualifier("CARTE", "test", "La carte est sous le pli : défiler avant de la toucher")
    t = orchestrateur.obtenir(r["travail"])
    texte = t["etapes"][0]["params"]["texte"]
    assert [e["titre"] for e in t["etapes"]] == ["Maintenance par l'agent (MCP)", "Dry-run", "Run réel (téléphone), tests impactés compris"]
    assert "sous le pli" in texte and "maintenance_modifier_bdd" in texte and "maintenance_rapporter" in texte and TID in texte
    assert "resources/commun.resource : aussi utilisé par 1 autre(s) test(s) : " + TID_SOLDE in texte   # ce qu'il ne faut pas casser
    assert t["etapes"][2]["params"]["impacts_de"] == "CARTE"
    assert _carte()["maintenance"]["etat"] == "en_correction"
    # l'agent, par le MCP : le libellé a changé dans l'application, il corrige le scénario puis rend compte
    nouveau = "# language: fr\nFonctionnalité: Carte\n  Scénario: Carte\n    Quand j'ouvre mes cartes\n    Alors la carte est affichée\n"
    with pytest.raises(ValueError):
        facade.maintenance_modifier_bdd("CARTE", nouveau, "court")
    assert facade.maintenance_modifier_bdd("CARTE", nouveau, "Le menu « Carte » s'appelle désormais « Mes cartes »")["modifie"]
    rap = facade.maintenance_rapporter("CARTE", "test", "Défilement ajouté dans la page de la carte", ["tests/carte.robot"])
    assert rap["impacts"]["tests"] == []                                         # aucun fichier partagé touché
    orchestrateur.annuler(r["travail"])
    assert _carte()["maintenance"]["etat"] == "echec_correction"                 # pas encore de run réussi depuis
    with pytest.raises(ValueError):
        maintenir.confirmer("CARTE")
    _run(atelier, "PASS")
    c = kanban.ticket("CARTE")
    assert c["maintenance"]["etat"] == "a_confirmer" and c["maintenance"]["bdd_modifie"] and "j'ouvre la carte" in c["gherkin_avant"]
    assert c["maintenance"]["rapport"]["resume"].startswith("Défilement")
    publie = []
    monkeypatch.setattr(kanban, "_ticket", lambda cle: {**_carte(), "xray": "DEMO-7"})
    monkeypatch.setattr(flux, "publier", lambda cles, xray=None: publie.append(cles) or {"publies": [{"scenario": "CARTE", "resultat": "Gherkin mis à jour"}],
                                                                                         "erreurs": [], "git": {"commit": "abc1234", "branche": "atelier/xray-1"}})
    r = maintenir.confirmer("CARTE")
    assert publie == [["CARTE"]] and r["maintenance"]["xray"] == "Gherkin mis à jour" and r["maintenance"]["commit"] == "abc1234"
    m = bdd.charger("CARTE")
    assert m["statut"] == "validé" and m["maintenance"]["etat"] == "resolu" and m["maintenances"][0]["bdd_modifie"]


def test_un_keyword_partage_modifie_met_les_autres_tests_en_maintenance(atelier):
    """Rien de cassé ailleurs : le keyword commun change, le test SOLDE qui l'utilise passe « impacté » jusqu'à un run
    réel réussi, et la maintenance de CARTE ne se confirme pas avant."""
    from atelier.domain import projet
    from atelier.execution import orchestrateur
    from atelier.generation import maintenir

    _run(atelier, "FAIL", "Element 'id=menu' did not match any elements", fin="2000-01-02T10:00:00")
    _run(atelier, "PASS", fin="2000-01-01T10:00:00", tid=TID_SOLDE)
    r = maintenir.maintenir("CARTE", "")
    # l'agent modifie le keyword partagé
    (projet.PROJECT_DIR / "resources" / "commun.resource").write_text("*** Keywords ***\nOuvrir Le Menu\n    Log    menu\n", "utf-8")
    imp = maintenir.rapporter("CARTE", "test", "Keyword Ouvrir Le Menu : attente du menu ajoutée")["impacts"]
    assert imp["fichiers"] == ["resources/commun.resource"] and imp["tests"] == [TID_SOLDE] and imp["bdd"] == ["SOLDE"]
    s = _carte("SOLDE")
    assert s["colonne"] == "maintenance" and s["maintenance"]["etat"] == "impacte" and s["maintenance"]["source"] == "CARTE"
    orchestrateur.annuler(r["travail"])
    _run(atelier, "PASS")                                                        # CARTE corrigé…
    assert _carte()["maintenance"]["etat"] == "a_confirmer"
    with pytest.raises(ValueError, match="impacté"):                             # … mais SOLDE n'a pas été rejoué
        maintenir.confirmer("CARTE")
    _run(atelier, "FAIL", "Element 'id=solde' not found", tid=TID_SOLDE)
    with pytest.raises(ValueError, match="FAIL"):                                # SOLDE cassé par le changement : pas de confirmation
        maintenir.confirmer("CARTE")
    assert _carte("SOLDE")["colonne"] == "maintenance"
    _run(atelier, "PASS", fin="2099-01-02T10:00:00", tid=TID_SOLDE)              # SOLDE réparé et rejoué
    assert _carte("SOLDE")["maintenance"] is None
    r = maintenir.confirmer("CARTE")
    assert r["maintenance"]["impacts"]["tests"] == [TID_SOLDE]


def test_le_run_de_verification_inclut_les_tests_impactes(atelier, monkeypatch):
    from atelier.domain import projet
    from atelier.execution import orchestrateur
    from atelier.generation import maintenir

    _run(atelier, "FAIL", "Element 'id=menu' did not match any elements", fin="2000-01-02T10:00:00")
    r = maintenir.maintenir("CARTE", "")
    (projet.PROJECT_DIR / "resources" / "commun.resource").write_text("*** Keywords ***\nOuvrir Le Menu\n    Log    menu\n", "utf-8")
    vu = {}
    monkeypatch.setitem(orchestrateur.HOOKS, "mettre_en_file", lambda params, *a, **k: vu.update(params) or {"run_id": "RUN-X"})
    monkeypatch.setattr(orchestrateur, "_reserver", lambda *a, **k: "SERIE1")
    t = orchestrateur.obtenir(r["travail"])
    try:
        orchestrateur._etape_run(t, t["etapes"][2], False)
    except Exception:  # noqa: BLE001 — la suite de l'étape (suivi du run) n'est pas l'objet du test
        pass
    assert vu.get("tests") == [TID, TID_SOLDE]


def test_refus_relance_l_agent_et_merge_request(atelier, monkeypatch):
    from atelier.execution import orchestrateur
    from atelier.generation import bdd, maintenir, studio

    _run(atelier, "FAIL", "Element 'id=carte' did not match any elements", fin="2000-01-02T10:00:00")
    r1 = maintenir.maintenir("CARTE", "")
    orchestrateur.annuler(r1["travail"])
    with pytest.raises(ValueError):
        maintenir.refuser("CARTE", "")
    r2 = maintenir.refuser("CARTE", "Le défilement masque le bouton Valider")
    assert r2["travail"] != r1["travail"] and bdd.charger("CARTE")["maintenance"]["tentatives"] == 2
    assert "masque le bouton" in orchestrateur.obtenir(r2["travail"])["etapes"][0]["params"]["texte"]
    orchestrateur.annuler(r2["travail"])
    _run(atelier, "PASS")
    maintenir.confirmer("CARTE")                                                 # pas dans Xray, pas de dépôt Git : confirmé quand même
    c = _carte()
    assert c["maintenu"]["n"] == 1 and c["maintenance"] is None and c["colonne"] == "automatise"
    vu = {}
    monkeypatch.setattr(studio, "proposer_mr", lambda titre, description="", cible="", derogation="", gitlab_client=None:
                        vu.update(titre=titre, description=description, derogation=derogation) or {"mr": {"url": "x"}})
    maintenir.proposer_mr("CARTE", "Correction urgente, 1 run stable")
    assert vu["titre"] == "Maintenance : Carte" and "masque le bouton" in vu["description"] and vu["derogation"]
