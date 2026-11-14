"""Testabilité des US : détection (lecture seule), analyse par règles, questions relues puis commentées, réponses,
cas proposés / validés, publication Xray + lien de couverture ; IA interchangeable (Cursor, LLM interne)."""
import json

import pytest


class FauxJira:
    enabled = True

    def __init__(self):
        self.commentaires_postes, self.liens = [], []
        self.reponses = []
        self.us = [
            {"key": "SQ1-10", "fields": {"summary": "Création d'une carte multi-usage", "status": {"name": "Ready"}, "issuetype": {"name": "Story"},
                                         "updated": "2026-11-14T10:00:00.000+0000",
                                         "description": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text":
                                             "En tant que conseiller je crée une carte rapidement pour le client, etc."}]}]}}},
            {"key": "SQ1-11", "fields": {"summary": "Consultation du plafond", "status": {"name": "Ready"}, "issuetype": {"name": "Story"},
                                         "updated": "2026-11-14T10:00:00.000+0000", "description": None,
                                         "issuelinks": [{"type": {"name": "Test"}, "inwardIssue": {"key": "TAM-900"}}]}},
        ]

    def rechercher(self, jql, champs, limite):
        self.jql = jql
        return self.us

    def commenter(self, key, texte):
        self.commentaires_postes.append((key, texte))
        return {"id": "500", "auteur_id": "qa", "date": "2026-11-14T11:00:00.000+0000"}

    def commentaires(self, key):
        return [{"id": "500", "auteur": "QA", "auteur_id": "qa", "date": "2026-11-14T11:00:00.000+0000", "texte": "[Atelier QA] Questions de testabilité ..."},
                {"id": "400", "auteur": "PO", "auteur_id": "po", "date": "2026-11-13T09:00:00.000+0000", "texte": "ancien commentaire"}] + self.reponses

    def link(self, a, b, type_name="Relates"):
        self.liens.append((a, b, type_name))


class FauxXray:
    def __init__(self):
        self.manuels = []

    def creer_test_manuel(self, projet, resume, etapes):
        self.manuels.append((projet, resume, etapes))
        return {"cle": f"{projet}-{1000 + len(self.manuels)}", "issueId": "1"}


@pytest.fixture
def t(tmp_path, monkeypatch):
    from atelier.domain import projet
    from atelier.intelligence import testabilite_us

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    monkeypatch.setenv("IA_FOURNISSEUR", "aucun")
    testabilite_us.enregistrer_espace({"projet_jira": "sq1", "nom": "Squad Cartes", "statuts": ["Ready"], "projet_xray": "TAM", "portee": "statuts"})
    return testabilite_us


def test_cycle_complet(t):
    j, x = FauxJira(), FauxXray()
    with pytest.raises(ValueError):
        t.enregistrer_espace({"projet_jira": "sq 1"})
    r = t.detecter(jira=j)
    assert 'project = "SQ1"' in j.jql and 'status in ("Ready")' in j.jql
    assert r["nouvelles"] == 2 and r["deja_couvertes"] == 1
    st = {u["cle"]: u["statut"] for u in t.file()}
    assert st == {"SQ1-10": "Détectée", "SQ1-11": "Couverte (existant)"}
    # analyse par règles : constats explicables + brouillon de questions, rien n'est envoyé
    d = t.analyser("SQ1-10")
    codes = {c["code"] for c in d["constats"]}
    assert {"description_courte", "sans_criteres", "termes_vagues", "sans_cas_erreur"} <= codes and "sans_role" not in codes
    assert "rapidement" in next(c for c in d["constats"] if c["code"] == "termes_vagues")["message"]
    assert d["statut"] == "Analysée" and "critères d'acceptation" in d["questions"]["brouillon"] and not j.commentaires_postes
    # envoi explicite (après relecture) puis relevé des réponses postérieures, hors commentaires de l'atelier
    t.modifier_questions("SQ1-10", d["questions"]["brouillon"] + "\nQuel plafond par défaut ?")
    d = t.envoyer_questions("SQ1-10", jira=j)
    assert d["statut"] == "Questions envoyées" and j.commentaires_postes[0][1].startswith(t.MARQUEUR)
    assert t.relever_reponses(jira=j)["nouvelles"] == 0  # seul l'ancien commentaire existe
    j.reponses = [{"id": "501", "auteur": "PO", "auteur_id": "po", "date": "2026-11-14T12:00:00.000+0000",
                   "texte": "- Si le client a déjà 3 cartes, la création doit être refusée\n- Plafond par défaut 1000"}]
    assert t.relever_reponses(jira=j)["nouvelles"] == 1 and t.detail("SQ1-10")["statut"] == "Réponses reçues"
    # cas squelettes par règles, validation exigée (étapes complètes), publication + lien de couverture
    d = t.proposer_cas("SQ1-10")
    assert d["statut"] == "Cas proposés" and any("cas d'erreur" in c["titre"] for c in d["cas"]) and "Plafond par défaut" in d["cas"][0]["notes"]
    c = d["cas"][0]
    with pytest.raises(ValueError, match="résultat attendu"):
        t.decider_cas("SQ1-10", c["id"], "valider")
    t.modifier_cas("SQ1-10", c["id"], {"etapes": [{"action": "Créer une carte pour un client sans carte", "donnees": "client C1", "resultat": "Carte créée"}]})
    t.decider_cas("SQ1-10", c["id"], "valider")
    with pytest.raises(ValueError, match="motivé"):
        t.decider_cas("SQ1-10", d["cas"][1]["id"], "rejeter")
    r = t.publier_cas("SQ1-10", xray=x, jira=j)
    assert r["publies"] == ["TAM-1001"] and x.manuels[0][0] == "TAM" and x.manuels[0][2][0]["resultat"] == "Carte créée"
    assert j.liens == [("TAM-1001", "SQ1-10", "Test")] and r["statut"] == "Couverte"
    with pytest.raises(PermissionError):
        t.modifier_cas("SQ1-10", c["id"], {"titre": "x"})
    ind = t.indicateurs()
    assert ind["us"] == 2 and ind["couvertes"] == 2 and ind["taux_couverture"] == 100.0
    assert [e["op"] for e in t.journal("SQ1-10")][:2] == ["publication_xray", "cas_valider"]


def test_proposition_cursor_et_llm_interne(t, monkeypatch):
    from atelier.intelligence import fournisseur_ia

    t.detecter(jira=FauxJira())
    monkeypatch.setenv("IA_FOURNISSEUR", "cursor")
    assert t.analyser_ia("SQ1-10")["disponible"] is False  # l'atelier n'appelle rien : l'agent Cursor dépose
    a = t.a_traiter()
    assert a[0]["cle"] == "SQ1-10" and "conseiller" in a[0]["texte"]
    d = t.deposer_proposition("SQ1-10", [{"gravite": "haute", "message": "Nombre maximal de cartes non précisé", "question": "Combien de cartes au maximum ?"}],
                              [{"titre": "Refus au-delà du maximum", "etapes": [{"action": "Créer une 4e carte", "resultat": "Refus"}]}], "Cursor (MCP)")
    assert d["statut"] == "Cas proposés" and d["cas"][0]["statut"] == "Proposé" and "Combien de cartes" in d["questions"]["brouillon"]
    # LLM interne compatible OpenAI : texte masqué avant envoi, réponse JSON
    monkeypatch.setenv("IA_FOURNISSEUR", "interne")
    monkeypatch.setenv("IA_INTERNE_URL", "https://llm.interne.exemple/v1")
    monkeypatch.setenv("IA_INTERNE_MODELE", "modele-maison")
    envoyes = []

    def faux_http(m, url, data=None, headers=None, timeout=60, cafile=None):
        envoyes.append((url, json.loads(data)))
        return json.dumps({"choices": [{"message": {"content": '```json\n{"constats": [{"gravite": "moyenne", "message": "Délai non défini"}], "cas": []}\n``` fin'}}]})

    monkeypatch.setattr("atelier.integrations.http.http", faux_http)
    u = t._us()
    u["SQ1-10"]["description"] += " Contact : jean.dupont@exemple.fr"
    t._sauver_us(u)
    d = t.analyser_ia("SQ1-10")
    assert envoyes[0][0] == "https://llm.interne.exemple/v1/chat/completions" and envoyes[0][1]["model"] == "modele-maison"
    assert "jean.dupont" not in json.dumps(envoyes[0][1])  # masqué avant envoi
    assert any(c["message"] == "Délai non défini" and c["source"].startswith("IA interne") for c in d["constats"])
    assert fournisseur_ia.etat()["appel_direct"]


def test_non_testable_justifie(t):
    t.detecter(jira=FauxJira())
    with pytest.raises(ValueError):
        t.non_testable("SQ1-10", "non")
    assert t.non_testable("SQ1-10", "US purement technique, couverte par les tests unitaires")["statut"] == "Non testable"


class FauxJiraAgile(FauxJira):
    """Tableau Scrum avec un sprint actif (12) et un sprint futur (13) ; le backlog du sprint 12 évolue."""

    def __init__(self):
        super().__init__()
        self.backlog = {12: ["SQ1-10", "SQ1-11"], 13: ["SQ1-11"]}

    def tableaux(self, projet):
        return [{"id": 7, "nom": "Tableau SQ1", "type": "scrum"}]

    def sprints(self, tableau, etats="active,future,closed"):
        return [{"id": 13, "nom": "Sprint 13", "etat": "future", "debut": "", "fin": "", "objectif": "", "tableau": 7},
                {"id": 12, "nom": "Sprint 12", "etat": "active", "debut": "2026-11-10", "fin": "2026-11-24", "objectif": "Cartes", "tableau": 7}]

    def rechercher(self, jql, champs, limite):
        self.jql = jql
        num = int(jql.split("sprint = ")[1].split()[0])
        return [u for u in self.us if u["key"] in self.backlog[num]]


def test_sprint_backlog_fige_et_bilan(t):
    j = FauxJiraAgile()
    t.enregistrer_espace({"projet_jira": "SQ1", "projet_xray": "TAM"})  # portée par défaut : sprint actif
    r = t.detecter(jira=j)
    assert "sprint = 12" in j.jql and "status" not in j.jql and r["sprints"] == ["SQ1 · Sprint 12"] and r["us"] == 2
    assert {u["cle"] for u in t.file(sprint="12")} == {"SQ1-10", "SQ1-11"} and t.file(sprint="13") == []
    b = t.figer_sprint("SQ1", "12")
    assert b["fige"]["us"] == 2 and b["taux_couverture"] == 50.0 and b["non_couvertes"] == ["SQ1-10"]
    with pytest.raises(FileExistsError):
        t.figer_sprint("SQ1", "12")  # photo immuable
    # en cours de sprint, le PO retire SQ1-10 et ajoute SQ1-12
    j.us.append({"key": "SQ1-12", "fields": {"summary": "Opposition sur carte", "status": {"name": "To Do"}, "issuetype": {"name": "Story"},
                                             "updated": "2026-11-15T10:00:00.000+0000", "description": None}})
    j.backlog[12] = ["SQ1-11", "SQ1-12"]
    r = t.detecter(jira=j, sprint="12")
    assert r["retirees"] == 1 and "retirée du sprint Sprint 12" in t.detail("SQ1-10")["historique"][-1]["detail"]
    b = t.bilan_sprint("SQ1", "12")
    assert b["ajoutees"] == ["SQ1-12"] and b["retirees"] == ["SQ1-10"] and b["us"] == 2
    # portée « sprint actif + suivant » : préparation pendant le planning
    t.enregistrer_espace({"projet_jira": "SQ1", "projet_xray": "TAM", "portee": "sprint_et_suivant"})
    assert t.detecter(jira=j)["sprints"] == ["SQ1 · Sprint 12", "SQ1 · Sprint 13"]
    assert t.indicateurs("12")["us"] == 2



def test_recherche_projets_jira_pour_la_politique(t):
    class J(FauxJiraAgile):
        def projets(self, recherche="", limite=30):
            self.q = recherche
            return [{"cle": "SQ1", "nom": "Squad Cartes", "type": "software", "geree_par_equipe": False},
                    {"cle": "SQ2", "nom": "Squad Paiement", "type": "software", "geree_par_equipe": True}]

        def types_issue_projet(self, projet):
            return ["Epic", "Story", "Bug", "Task"]

        def statuts_projet(self, projet, issue_type=""):
            return ["To Do", "Ready", "In Progress", "Done"]

    j = J()
    l = t.chercher_projets_jira(" squad ", jira=j)
    assert j.q == "squad" and [p["suivi"] for p in l] == [True, False]  # SQ1 déjà suivi par la politique
    d = t.details_projet_jira("SQ1", jira=j)
    assert d["types"][1] == "Story" and d["sprint_actif"]["nom"] == "Sprint 12" and "Ready" in d["statuts"]
