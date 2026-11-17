"""Caches de performance : instantané Xray, graphe de connaissance, découpage des textes.
Un cache ne doit jamais changer un résultat : copies indépendantes, invalidation dès qu'une source change."""
import os
import re
import time

import pytest


@pytest.fixture
def projet(tmp_path, monkeypatch):
    from atelier.domain import projet as p
    from atelier.discovery import connaissance
    from atelier.intelligence import patrimoine_xray

    monkeypatch.setattr(p, "PROJECT_DIR", tmp_path)
    patrimoine_xray.vider_cache()
    connaissance.vider_cache()
    yield tmp_path
    patrimoine_xray.vider_cache()
    connaissance.vider_cache()


def _vieillir(racine, secondes=60):
    """Date de modification ancienne pour tous les fichiers : le projet est « stable » (cache utilisable)."""
    t = time.time() - secondes
    for r, _, fs in os.walk(racine):
        for f in fs:
            os.utime(os.path.join(r, f), (t, t))


def test_instantane_xray_copies_independantes_et_relu_des_qu_il_change(projet):
    from atelier.intelligence import patrimoine_xray as px

    px.enregistrer({"projet": "DEMO", "tests": [{"cle": "DEMO-1", "resume": "A"}], "exigences": []}, "test")
    a = px.charger()
    a["tests"][0]["resume"] = "modifié par l'appelant"
    assert px.charger()["tests"][0]["resume"] == "A"  # le cache n'est jamais exposé
    # écriture directe (sans enregistrer), même taille, immédiatement après : détectée par l'empreinte du contenu
    f = px.fichier()
    f.write_text(f.read_text("utf-8").replace('"A"', '"B"'), "utf-8")
    assert px.charger()["tests"][0]["resume"] == "B"
    v = px.charger_vue()
    v["tests"].clear()
    assert px.charger_vue()["tests"]  # vue filtrée : copie elle aussi
    f.unlink()
    assert px.charger() is None and px.charger_vue() is None


def test_graphe_en_cache_tant_que_le_projet_ne_change_pas(projet, monkeypatch):
    from atelier.discovery import connaissance
    from atelier.domain.graphe import Graphe

    appels = []

    def faux(avec_declarations=True, inventaire=None):
        appels.append(inventaire)
        g = Graphe("connaissance")
        g.noeud("test:DEMO-1", "test", f"version {len(appels)}")
        return g

    monkeypatch.setattr(connaissance, "_construire", faux)
    (projet / "connaissance").mkdir()
    (projet / "connaissance" / "declarations.yaml").write_text("noeuds: []\n", "utf-8")
    _vieillir(projet)
    g1 = connaissance.construire()
    g1.noeuds.clear()  # l'appelant modifie sa copie
    g2 = connaissance.construire()
    assert len(appels) == 1 and g2.noeuds["test:DEMO-1"].libelle == "version 1"
    # une source change (taille différente) : reconstruction
    (projet / "connaissance" / "declarations.yaml").write_text("noeuds: [x]\n", "utf-8")
    _vieillir(projet)
    assert connaissance.construire().noeuds["test:DEMO-1"].libelle == "version 2"
    # un fichier ajouté : reconstruction
    (projet / "nouveau.robot").write_text("*** Test Cases ***\n", "utf-8")
    _vieillir(projet)
    connaissance.construire()
    assert len(appels) == 3
    # inventaire fourni par l'appelant : jamais de cache
    connaissance.construire(inventaire={"tests": {}})
    assert len(appels) == 4 and appels[-1] == {"tests": {}}


def test_graphe_sans_cache_pendant_une_modification(projet, monkeypatch):
    """Un fichier modifié il y a moins de STABILITE_S secondes : le pas de la date de modification pourrait masquer
    une seconde écriture, le graphe est donc reconstruit à chaque appel."""
    from atelier.discovery import connaissance
    from atelier.domain.graphe import Graphe

    appels = []
    monkeypatch.setattr(connaissance, "_construire", lambda avec_declarations=True, inventaire=None: appels.append(1) or Graphe("connaissance"))
    (projet / "carte.yaml").write_text("x: 1\n", "utf-8")  # date de modification : maintenant
    connaissance.construire()
    connaissance.construire()
    assert len(appels) == 2


def test_decoupage_des_textes_memorise_sans_changer_le_resultat():
    from atelier.intelligence import intelligence_couverture as ic

    t = "Les virements instantanés doivent être confirmés par l'utilisateur"
    attendu = [m[:6] for m in re.findall(r"[a-z0-9]{3,}", ic._sans_accents(t.lower())) if m not in ic.MOTS_VIDES]
    assert ic.jetons(t) == attendu
    j = ic.jetons(t)
    j.append("pollution")  # la liste renvoyée est une copie
    assert ic.jetons(t) == attendu
    assert ic.similarite(t, t) == 1.0 and ic.similarite("", t) == 0.0 and ic.similarite(None, t) == 0.0
    assert ic.similarite("virement instantané", "virements instantanés") == 1.0
