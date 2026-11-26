"""Nommer les écrans en une fois (rôle dans le parcours, doublons probables) ; règles Jira : le récit n'est pas une règle,
et elles ne retiennent pas la Discovery."""
import pytest


def _el(cle, libelle, type_="bouton"):
    return {"key": cle, "type": type_, "libelle": libelle, "locators": [f"id={cle}"]}


@pytest.fixture
def carte_agences(tmp_path, monkeypatch):
    from atelier.discovery import carte
    from atelier.domain import projet

    monkeypatch.setattr(projet, "PROJECT_DIR", tmp_path)
    carte.creer_app("Banque Web", ["web"], web={"url": "https://recette.exemple.fr"}, type_="web")
    u = "https://recette.exemple.fr"
    acc = carte.observer([_el("lien_agences", "Agences", "lien")], "web", u + "/")
    carte.renommer(acc["id"], "accueil", "Accueil")
    villes = [carte.observer([_el(f"ville_{i}", f"Ville {i}")], "web", f"{u}/villes?p={i}") for i in range(3)]
    for v in villes:
        e = carte.ecran(v["id"])
        e["titre"] = "Sélectionner une ville"
        carte._save_ecran(e)
    carte.enregistrer_transition(acc["id"], villes[1]["id"], "web", {"type": "tap", "cle": "lien_agences", "libelle": "Agences"})
    annuler = carte.observer([_el("bouton_annuler", "Annuler")], "web", u + "/recherche")
    e = carte.ecran(annuler["id"])
    e["titre"] = "Annuler"
    carte._save_ecran(e)
    return carte, acc["id"], [v["id"] for v in villes], annuler["id"]


def test_noms_proposes_selon_le_role_et_doublons(carte_agences):
    from atelier.discovery import apprentissage

    carte, acc, villes, annuler = carte_agences
    apprentissage.proposer("nom_ecran", "agences_choix_ville", ecran=villes[0], module="Agences", agent="claude_code")
    noms = {x["ecran"]: x for x in apprentissage.noms_ecrans()}
    assert acc not in noms                                                           # déjà nommé : pas touché
    assert (noms[villes[0]]["nom"], noms[villes[0]]["module"], noms[villes[0]]["fusion_avec"]) == ("agences_choix_ville", "Agences", "")
    assert noms[villes[1]]["fusion_avec"] == noms[villes[2]]["fusion_avec"] == "agences_choix_ville"   # même titre : même écran probable
    assert noms[villes[1]]["module"] == "Accueil"                                    # module de l'écran d'où l'on vient
    assert noms[annuler]["nom"] == ""                                                # « Annuler » n'est pas un nom

    r = apprentissage.appliquer_noms([{"ecran": villes[0], "nom": "agences_choix_ville", "module": "Agences"},
                                      {"ecran": villes[1], "nom": "agences_choix_ville", "module": "Agences"}])
    assert (r["nommes"], r["fusionnes"], r["erreurs"]) == (2, 1, [])
    assert carte.ecran(villes[0])["nom"] == "agences_choix_ville" and not carte.ecran(villes[0]).get("propositions_nom")
    assert len([e for e in carte.ecrans() if e.get("nom") == "agences_choix_ville"]) == 1   # fusionnés en un seul écran
    assert carte.ecran(villes[1])["id"] == villes[0]                                 # l'ancien identifiant retrouve l'écran fusionné
    assert not [p for p in apprentissage.propositions() if p["objet"] == "nom_ecran"]


def test_regles_jira_le_recit_n_est_pas_une_regle():
    from atelier.discovery import intelligence_app as ia

    e = {"description": "- En tant que client, je souhaite que le virement doit être rapide\n"
                        "- Afin de sécuriser mes fonds. Critères d'acceptation : le virement ne peut pas dépasser le plafond\n"
                        "- Le montant doit être positif"}
    c = ia.criteres(e)
    assert c[1] == "le virement ne peut pas dépasser le plafond"
    assert [ia.structurer(x)["regle_candidate"] for x in c] == [False, True, True]


def test_seules_les_propositions_de_carte_retiennent_la_discovery():
    from atelier.intelligence import cerveau

    assert cerveau.bloque_discovery({"objet": "nom_ecran", "type": "nom_ecran"})
    assert cerveau.bloque_discovery({"objet": "noeud", "type": "parcours"})
    assert cerveau.bloque_discovery({"objet": "relation", "id": "parcours:p|contient|ecran:e", "relation": {"de": {"id": "parcours:p"}}})
    assert not cerveau.bloque_discovery({"objet": "noeud", "type": "regle"})
    assert not cerveau.bloque_discovery({"objet": "relation", "id": "user_story:DEMO-1|contient|regle:DEMO-1-2"})
