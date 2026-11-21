"""Assistant d'installation et de lancement (lanceur.py) : ne fait que ce qui manque, poste prêt = lancement direct.
Aucune installation réelle : pip, venv et l'atelier du .venv sont simulés."""
import subprocess
import types

import pytest


@pytest.fixture
def l(tmp_path, monkeypatch):
    import lanceur

    racine = tmp_path / "atelier"
    (racine / ".venv" / "bin").mkdir(parents=True)
    (racine / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    monkeypatch.setattr(lanceur, "ICI", racine)
    monkeypatch.setattr(lanceur, "POSTE", tmp_path / "poste.json")
    monkeypatch.setattr(lanceur, "python_venv", lambda racine=racine: racine / ".venv" / "bin" / "python")
    monkeypatch.setattr(lanceur, "marqueur", lambda racine=racine: racine / ".venv" / ".atelier-dependances")
    monkeypatch.setattr(lanceur, "empreinte_dependances", lambda racine=racine: "e-" + (racine / "requirements.txt").read_text())
    lanceur.A_REGLER.clear()
    cmds = []

    def faux(cmd, **kw):
        cmds.append([str(c) for c in cmd])
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(lanceur, "executer", faux)
    return types.SimpleNamespace(m=lanceur, cmds=cmds, racine=racine)


def test_dependances_installees_une_fois_puis_a_jour(l):
    assert l.m.etape_dependances() and any("requirements.txt" in c for c in l.cmds[-1])
    n = len(l.cmds)
    assert l.m.etape_dependances() and len(l.cmds) == n                        # poste prêt : rien n'est relancé
    (l.racine / "requirements.txt").write_text("fastapi\nuvicorn\n", encoding="utf-8")
    assert l.m.etape_dependances() and len(l.cmds) > n                         # requirements.txt a changé : réinstallation


def test_navigateur_installe_puis_secours_du_poste(l, monkeypatch, tmp_path):
    etats = iter([{"ok": False}, {"ok": True, "detail": "Chromium installé"}])
    monkeypatch.setattr(l.m, "interroger_atelier", lambda code, env=None: next(etats))
    assert l.m.etape_navigateur({}) and ["playwright", "install", "chromium"] == l.cmds[-1][-3:]
    chrome = tmp_path / "chrome.exe"
    chrome.write_text("")
    monkeypatch.setattr(l.m, "interroger_atelier", lambda code, env=None: {"ok": False})
    monkeypatch.setattr(l.m, "NAVIGATEURS_POSTE", [str(chrome)])
    env = {}
    assert l.m.etape_navigateur(env) and env["WEB_BROWSER_EXECUTABLE"] == str(chrome)
    assert l.m.lire_poste()["WEB_BROWSER_EXECUTABLE"] == str(chrome)            # gardé pour les prochains lancements


def test_projet_demande_puis_enregistre(l, monkeypatch, tmp_path):
    monkeypatch.setattr(l.m, "interroger_atelier", lambda code, env=None: {"ok": True, "dossier": "/x/tests", "nom": "tests"})
    assert l.m.etape_projet({}, interactif=True, saisie=lambda _: pytest.fail("rien à demander : projet déjà choisi"))
    monkeypatch.setattr(l.m, "interroger_atelier", lambda code, env=None: {"ok": False, "dossier": str(l.racine)})
    assert l.m.etape_projet({}, interactif=False) and l.m.A_REGLER                # non interactif : signalé, pas bloquant
    cible = tmp_path / "mes-tests"
    assert l.m.etape_projet({}, interactif=True, saisie=lambda _: str(cible))
    assert cible.is_dir() and "projets.enregistrer" in l.cmds[-1][2] and l.cmds[-1][-2:] == [str(cible), "mes-tests"]
    n = len(l.cmds)
    assert l.m.etape_projet({}, interactif=True, saisie=lambda _: str(l.racine)) and len(l.cmds) == n   # jamais le dossier de l'atelier


def test_lanceur_windows_trouve_python_et_propose_de_l_installer():
    from pathlib import Path

    cmd = (Path(__file__).resolve().parents[1] / "lancer-atelier.cmd").read_text(encoding="utf-8")
    assert "py -3 -c" in cmd and "python -c" in cmd and "winget install -e --id Python.Python.3.13" in cmd and "lanceur.py %*" in cmd
    attr = (Path(__file__).resolve().parents[1] / ".gitattributes").read_text(encoding="utf-8")
    assert "*.cmd text eol=crlf" in attr
