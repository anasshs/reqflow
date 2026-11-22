"""Knowledge Graph, lot 6 : doublons de tests BDD par le contenu, indicateurs de qualité, sélection d'affichage."""


def _bdd(cle, titre, etapes):
    from atelier.generation import bdd

    m = bdd.creer(cle, titre)
    sc = m["scenarios"][0]["id"]
    for mot, texte, ecran in etapes:
        m = bdd.ajouter_etape(cle, sc, mot, texte)
        if ecran:
            m["scenarios"][0]["etapes"][-1]["ecran"] = ecran
            bdd.sauver(m)


CONNEXION = [("Étant donné", "que je suis sur l'écran connexion", "connexion"),
             ("Quand", "je saisis mon identifiant et mon mot de passe", "connexion")]


def test_doublons_bdd_compares_sur_le_contenu(projet):
    from atelier.intelligence import couverture

    _bdd("a", "Se connecter", CONNEXION + [("Alors", "le tableau de bord s'affiche", "tableau")])
    _bdd("b", "Titre sans rapport", CONNEXION + [("Alors", "le tableau de bord s'affiche", "tableau")])
    _bdd("c", "Connexion refusée", CONNEXION + [("Alors", "un message d'erreur rouge apparaît", "tableau")])
    _bdd("d", "Autre chose", [("Quand", "je consulte la liste des virements programmés", "virements")])
    d = {tuple(x["tests"]): x["classe"] for x in couverture.doublons_bdd()}
    assert d[("a", "b")] == "doublon probable"                    # titres différents, contenu identique
    assert d[("a", "c")] == "variante métier"                     # même chemin, résultat attendu différent
    assert not any("d" in k for k in d)


def test_qualite_parcours_declare_pas_orphelin(projet, monkeypatch):
    from atelier.discovery import connaissance, espaces, parcours_utilisateur as pu

    for v in ("XRAY_CLIENT_ID", "JIRA_BASE_URL"):
        monkeypatch.delenv(v, raising=False)
    from atelier.discovery import carte

    carte.creer_app("Site Démo", ["web"], web={"url": "https://demo.exemple.test"}, type_="web")
    vide = pu.enregistrer("", {"nom": "Demande de démo"})
    connaissance.vider_cache()
    q = espaces.qualite()
    assert vide["noeud"] not in [x["id"] for x in q["orphelins"]["elements"]]
    assert vide["noeud"] in [x["id"] for x in q["parcours_incomplets"]["elements"]]
    assert q["parcours_incomplets"]["par_completude"]["déclaré"] >= 1
    assert isinstance(q["doublons_bdd"], list)


def test_selection_affichage_au_dela_de_600(monkeypatch):
    """Test 7 du cahier : au-delà de 600 nœuds, l'élément sélectionné et ses voisins sont affichés, le masqué est compté."""
    from atelier.discovery import espaces
    from atelier.domain.graphe import Graphe

    g = Graphe("t")
    g.noeud("module:m", "module", "M")
    for i in range(700):
        g.noeud(f"locator:{i:03d}", "locator", f"E{i}")
    g.noeud("locator:cible", "locator", "Cible")
    g.noeud("locator:voisin", "locator", "Voisin")
    g.relier("locator:cible", "locator:voisin", "contient")
    v = espaces._limiter(g, {"locator:cible"})
    ids = {n["id"] for n in v["noeuds"]}
    assert v["tronque"] and v["total"] == 703 and len(ids) == espaces.MAX_NOEUDS
    assert {"locator:cible", "locator:voisin", "module:m"} <= ids
    assert v["masques_par_type"] == {"locator": 703 - espaces.MAX_NOEUDS}
