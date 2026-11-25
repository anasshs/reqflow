"""Notification d'activité : /api/activite dit ce qui tourne (run : progression, test et étape courants ; Discovery
active), et le dernier run terminé pour le message de fin."""


def test_activite_run_en_cours_puis_termine(projet):
    from fastapi.testclient import TestClient

    from atelier.adapters.web import app as web
    from atelier.execution import direct

    c = TestClient(web.app, base_url="http://127.0.0.1:8765")
    c.get("/plateforme")
    assert c.get("/api/activite").json()["run"] is None
    direct.observer({"type": "run_lance", "run_id": "RUN-X", "suite": "tests/carte.robot"})
    direct.observer({"type": "run_debut", "tests": [{"nom": "A"}, {"nom": "B"}]})
    direct.observer({"type": "test_debut", "nom": "A"})
    direct.observer({"type": "kw_debut", "nom": "Ouvrir La Carte", "niveau": 1})
    r = c.get("/api/activite").json()["run"]
    assert r["id"] == "RUN-X" and r["total"] == 2 and r["termines"] == 0 and r["courant"] == "A" and r["etape"] == "Ouvrir La Carte"
    direct.observer({"type": "test_fin", "nom": "A", "statut": "PASS"})
    direct.observer({"type": "test_fin", "nom": "B", "statut": "FAIL"})
    direct.observer({"type": "run_bilan", "run_id": "RUN-X", "bilan": {"resultat": {}}})
    a = c.get("/api/activite").json()
    assert a["run"] is None and a["dernier_run"]["id"] == "RUN-X"
    assert a["dernier_run"]["compte"]["réussi"] == 1 and a["dernier_run"]["compte"]["échec"] == 1
