"""Synchronisation du travail et de la connaissance par la base : deux postes, une base, chacun son dossier.
Envoi, réception, conflit (rien ne se perd), suppression propagée, garde-fou des suppressions en masse, exclusions
(code des tests, résultats, traces de l'agent), fichiers binaires (captures)."""
import pytest


@pytest.fixture
def deux_postes(tmp_path, monkeypatch):
    from atelier.domain import magasin, synchro

    monkeypatch.setenv("ATELIER_BASE", str(tmp_path / "base_partagee.db"))
    monkeypatch.setattr(magasin, "_BASE", None)
    monkeypatch.setattr(synchro, "_DERNIER", {})
    a, b = tmp_path / "poste_a" / "DEMO", tmp_path / "poste_b" / "DEMO"
    a.mkdir(parents=True)
    b.mkdir(parents=True)

    def sur(nom):
        """Passe sur le poste nom (sa config et son état de synchronisation propres, même base)."""
        monkeypatch.setenv("ATELIER_DOSSIER", str(tmp_path / f"poste_{nom}" / ".atelier"))
        monkeypatch.setenv("ATELIER_POSTE_NOM", f"PC-{nom.upper()}")
        return synchro.synchroniser("demo", a if nom == "a" else b)

    return a, b, sur


def test_envoi_reception_et_exclusions(deux_postes):
    a, b, sur = deux_postes
    (a / "conception").mkdir()
    (a / "conception" / "kanban.yaml").write_text("us: {}\n", "utf-8")
    (a / "app_map" / "vignettes").mkdir(parents=True)
    (a / "app_map" / "vignettes" / "e_1_android.png").write_bytes(b"\x89PNG\x00\xff")      # capture (binaire)
    (a / "tests").mkdir()
    (a / "tests" / "x.robot").write_text("*** Test Cases ***\n", "utf-8")                    # code : Git, pas la base
    (a / "results").mkdir()
    (a / "results" / "output.xml").write_text("<robot/>", "utf-8")
    (a / "studio" / "sessions_agent").mkdir(parents=True)
    (a / "studio" / "sessions_agent" / "trace.json").write_text("{}", "utf-8")
    (a / "atelier_statuts.yaml").write_text("statuts: []\n", "utf-8")
    r = sur("a")
    assert sorted(r["envoyes"]) == ["app_map/vignettes/e_1_android.png", "atelier_statuts.yaml", "conception/kanban.yaml"]
    r = sur("b")
    assert sorted(r["recus"]) == ["app_map/vignettes/e_1_android.png", "atelier_statuts.yaml", "conception/kanban.yaml"]
    assert (b / "app_map" / "vignettes" / "e_1_android.png").read_bytes() == b"\x89PNG\x00\xff"
    assert not (b / "tests").exists() and not (b / "results").exists() and not (b / "studio").exists()
    assert sur("b")["recus"] == [] and sur("a")["envoyes"] == []                               # rien de neuf : rien ne bouge


def test_modification_suppression_et_conflit(deux_postes):
    a, b, sur = deux_postes
    (a / "conception").mkdir()
    k = a / "conception" / "kanban.yaml"
    k.write_text("v: 1\n", "utf-8")
    (a / "discovery").mkdir()
    (a / "discovery" / "p.json").write_text("{}", "utf-8")
    sur("a")
    sur("b")
    (b / "conception" / "kanban.yaml").write_text("v: 2\n", "utf-8")                          # B modifie
    assert sur("b")["envoyes"] == ["conception/kanban.yaml"]
    assert sur("a")["recus"] == ["conception/kanban.yaml"] and k.read_text("utf-8") == "v: 2\n"
    k.write_text("v: 3 (A)\n", "utf-8")                                                        # les deux modifient
    (b / "conception" / "kanban.yaml").write_text("v: 3 (B)\n", "utf-8")
    sur("b")
    r = sur("a")
    assert r["conflits"][0]["fichier"] == "conception/kanban.yaml"
    assert k.read_text("utf-8") == "v: 3 (B)\n"                                                # la base s'applique…
    copie = a / r["conflits"][0]["copie_locale"]
    assert copie.read_text("utf-8") == "v: 3 (A)\n" and "PC-A" in copie.name                  # … la version locale est gardée
    assert sur("a")["envoyes"] == []                                                           # la copie n'est pas synchronisée
    (a / "discovery" / "p.json").unlink()                                                      # suppression propagée
    assert sur("a")["supprimes_base"] == ["discovery/p.json"]
    assert sur("b")["supprimes_local"] == ["discovery/p.json"] and not (b / "discovery" / "p.json").exists()


def test_garde_fou_des_suppressions_en_masse(deux_postes):
    from atelier.domain import synchro

    a, b, sur = deux_postes
    (a / "app_map").mkdir()
    for i in range(synchro.SEUIL_SUPPRESSIONS + 5):
        (a / "app_map" / f"e_{i}.json").write_text("{}", "utf-8")
    sur("a")
    sur("b")
    for f in (a / "app_map").iterdir():                                                       # dossier vidé par erreur
        f.unlink()
    r = sur("a")
    assert len(r["suppressions_en_attente"]) == synchro.SEUIL_SUPPRESSIONS + 5 and r["supprimes_base"] == []
    assert len(list((b / "app_map").iterdir())) == synchro.SEUIL_SUPPRESSIONS + 5             # rien n'a disparu ailleurs
    r = synchro.synchroniser("demo", a, confirmer_suppressions=True)
    assert len(r["supprimes_base"]) == synchro.SEUIL_SUPPRESSIONS + 5
