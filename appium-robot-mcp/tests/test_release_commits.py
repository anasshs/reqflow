"""Release Note au format commit conventionnel (feat / fix / refactor) : le préfixe donne le type de l'évolution et
sa portée, même sous une rubrique « NOUVEAUTÉS » qui dirait « nouvelle » pour tout."""
from atelier.intelligence import releases


def test_type_et_portee_des_commits():
    assert releases.type_conventionnel("feat(flight): ask a loyalty number") == ("nouvelle", "flight")
    assert releases.type_conventionnel("fix: keep the runner off") == ("correction", "")
    assert releases.type_conventionnel("refactor(e_sim): move logic") == ("technique", "e_sim")
    assert releases.type_conventionnel("feature(assistant): init") == ("nouvelle", "assistant")
    assert releases.type_conventionnel("revert(transfer): drop renaming") == ("suppression", "transfer")
    assert releases.type_conventionnel("Corriger l'affichage du solde") == ("", "")


def test_la_rubrique_ne_l_emporte_pas_sur_le_prefixe():
    a = releases.analyser_texte("NOUVEAUTÉS :\n* feat(vol): show amenities on fare cards\n* fix(cartes): keep the card name visible\n"
                                "* refactor(cartes): migrate the screens to Compose\n* Nouvel écran de bienvenue pour tous")
    assert [(e["type"], e.get("portee", "")) for e in a["evolutions"]] == [
        ("nouvelle", "vol"), ("correction", "cartes"), ("technique", "cartes"), ("nouvelle", "")]
