"""Paquet installable : le code et ses lanceurs, jamais les tests, les environnements, les bases ni les secrets ;
raccourcis proposés une seule fois par le lanceur."""
import zipfile


def test_paquet_sans_tests_ni_secrets(tmp_path):
    import importlib.util
    from pathlib import Path

    racine = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("paquet", racine / "outils" / "paquet.py")
    paquet = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(paquet)
    r = paquet.construire(tmp_path / "atelier.zip")
    noms = zipfile.ZipFile(r["paquet"]).namelist()
    assert "atelier/lancer-atelier.cmd" in noms and "atelier/serveur_donnees.py" in noms and "atelier/LISEZMOI-INSTALLATION.txt" in noms
    assert "atelier/atelier/domain/magasin.py" in noms and "atelier/VERSION" in noms
    assert not any(n.startswith("atelier/tests/") or n.endswith((".env", ".db", ".pyc")) or "/.venv/" in n for n in noms)
    assert (tmp_path / "atelier.zip.sha256").read_text("utf-8").split()[0] == r["sha256"]


def test_raccourcis_proposes_une_fois(tmp_path, monkeypatch):
    import lanceur

    monkeypatch.setattr(lanceur.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(lanceur.os, "name", "nt")
    appels = []
    monkeypatch.setattr(lanceur, "executer", lambda cmd, **k: appels.append(cmd) or type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})())
    assert lanceur.etape_raccourcis(interactif=True, saisie=lambda q: "n")       # refusé : plus demandé ensuite
    assert (tmp_path / ".atelier" / "raccourcis.json").exists() and appels == []
    assert lanceur.etape_raccourcis(interactif=True, saisie=lambda q: "o") and appels == []
    assert lanceur.etape_raccourcis(interactif=False, forcer=True) and "WScript.Shell" in appels[0][-1]
