"""Application Discovery : sessions (configuration, timeline, résultats par différence, une seule session active)."""
import pytest


def _elements(*libelles):
    return [{"key": "bouton_" + l.lower().replace(" ", "_"), "type": "bouton", "libelle": l, "locators": [f"id={l.lower().replace(' ', '_')}"]}
            for l in libelles]


@pytest.fixture
def ds(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.discovery import sessions_discovery
    from atelier.domain import projet

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    carte.creer_app("Banque Web", ["web"], web={"url": "https://recette.exemple.fr"}, type_="web")
    return sessions_discovery


def test_cycle_session_et_resultats(ds):
    from atelier.discovery import carte
    from atelier.domain import evenements

    with pytest.raises(ValueError, match="Plateforme"):
        ds.creer({"plateforme": "android"})
    e0 = carte.observer(_elements("Comptes", "Virements"), "web", "https://recette.exemple.fr/accueil")
    s = ds.creer({"mode": "guidee", "environnement": "recette", "profondeur": 2})
    assert s["statut"] == "Préparée" and s["config"]["plateforme"] == "web" and s["config"]["app_nom"] == "Banque Web"
    ds.demarrer(s["id"])
    other = ds.creer({})
    with pytest.raises(PermissionError):
        ds.demarrer(other["id"])  # une seule session active
    # observation : un écran connu, un nouvel écran, une transition
    e1 = carte.observer(_elements("Virement interne", "Virement externe"), "web", "https://recette.exemple.fr/virements")
    evenements.publier({"type": "carte_change", "ecran": e1})
    evenements.publier({"type": "carte_change", "ecran": carte.observer(_elements("Comptes", "Virements"), "web", "https://recette.exemple.fr/accueil")})
    carte.enregistrer_transition(e0["id"], e1["id"], "web", {"type": "click", "cle": "virements", "libelle": "Virements"})
    evenements.publier({"type": "carte_change", "transition": [e0["id"], e1["id"]]})
    evenements.publier({"type": "ignore_moi"})
    ds.annoter(s["id"], "Étape de confirmation : ne jamais rejouer", sensible=True, ecran=e1["id"])
    ds.pause(s["id"])
    evenements.publier({"type": "carte_change", "ecran": e1})  # en pause : non enregistré
    ds.demarrer(s["id"])  # reprise
    fin = ds.arreter(s["id"])
    r = fin["resultats"]
    assert r["nouveaux_ecrans"] == 1 and r["nouveaux"][0]["id"] == e1["id"] and r["nouvelles_transitions"] == 1
    assert r["ecrans_visites"] == 2 and r["sensibles"] == 1
    types = [x["type"] for x in ds.timeline(s["id"])]
    assert types.count("ecran") == 2 and "transition" in types and "sensible" in types and types[-1] == "arret"
    assert ds.active() is None and ds.lister()[1]["statut"] == "Terminée"
    with pytest.raises(ValueError):
        ds.demarrer(s["id"])  # terminée : nouvelle session
    v = ds.vue_ensemble()
    assert v["kpi"]["ecrans"] == 2 and v["kpi"]["transitions"] == 1 and v["kpi"]["a_nommer"] == 2
    rapide = ds.vue_ensemble(avec_graphe=False)
    assert "fonctionnel" not in rapide and rapide["kpi"] == v["kpi"]
    assert set(v["durees"]) == {"depot_robot", "graphe"} and v["volume"]["noeuds"] >= 2
    n = ds.navigation()
    assert {x["id"] for x in n["impasses"]} == {e1["id"]} and ds.chemin(e1["id"], e0["id"])["trouve"]
