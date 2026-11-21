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


def test_cursor_branche_et_mode_d_envoi(l, monkeypatch):
    """Cursor sur le poste : l'atelier y est branché (MCP + règles) et la ligne de commande sans agent installé bascule sur
    la boîte de demandes — chaque changement demandé avant d'être fait ; sans Cursor, rien n'est touché."""
    etat = {"cursor_present": True, "mcp_installe": False, "mcp_a_jour": False, "erreur": "", "envoi": "cli", "cli": False, "fournisseur": "cursor"}
    appels = []

    def venv(code, *args, env=None):
        appels.append((code, args))
        return etat if code == l.m.CODE_CURSOR else {"ok": True, "fichier": "~/.cursor/mcp.json", "sauvegarde": "", "regles": 11}
    monkeypatch.setattr(l.m, "_venv_json", venv)
    reponses = iter(["", "o"])                                                          # Entrée = oui
    assert l.m.etape_cursor({}, 8765, interactif=True, saisie=lambda _: next(reponses))
    faits = [c for c, _ in appels]
    assert l.m.CODE_BRANCHER in faits and (l.m.CODE_ENVOI, ("boite",)) in appels
    appels.clear()
    assert l.m.etape_cursor({}, 8765, interactif=True, saisie=lambda _: "n")             # refusé : rien n'est modifié
    assert [c for c, _ in appels] == [l.m.CODE_CURSOR] and l.m.A_REGLER
    appels.clear()
    assert l.m.etape_cursor({}, 8765, interactif=False)                                   # non interactif : signalé seulement
    assert [c for c, _ in appels] == [l.m.CODE_CURSOR]
    etat.update(cursor_present=False, fournisseur="aucun")
    appels.clear()
    assert l.m.etape_cursor({}, 8765, interactif=True, saisie=lambda _: pytest.fail("Cursor absent : rien à demander"))
    assert [c for c, _ in appels] == [l.m.CODE_CURSOR]


def test_cursor_par_url_sur_le_port_de_l_interface(l, monkeypatch):
    """Cursor configuré par URL vers l'interface (8765) : signalé ; le mode HTTP du MCP (localhost:8000/mcp) est proposé,
    retenu sur le poste et passé à l'atelier à chaque lancement."""
    etats = [{"cursor_present": True, "mcp_installe": True, "mcp_a_jour": False, "erreur": "", "envoi": "boite", "cli": False,
              "fournisseur": "cursor", "url_actuelle": "http://127.0.0.1:8765", "mcp_http_port": None},
             {"cursor_present": True, "mcp_installe": True, "mcp_a_jour": False, "erreur": "", "envoi": "boite", "cli": False,
              "fournisseur": "cursor", "url_actuelle": "http://127.0.0.1:8765", "mcp_http_port": 8000}]
    appels = []

    def venv(code, *args, env=None):
        appels.append((code, dict(env or {})))
        return etats.pop(0) if code == l.m.CODE_CURSOR else {"ok": True, "fichier": "mcp.json", "sauvegarde": "mcp.json.bak", "regles": 0}
    monkeypatch.setattr(l.m, "_venv_json", venv)
    env = {}
    assert l.m.etape_cursor(env, 8765, interactif=True, saisie=lambda _: "o")
    assert any("interface web" in a for a in l.m.A_REGLER)
    assert env["MCP_HTTP_PORT"] == "8000" and l.m.lire_poste()["MCP_HTTP_PORT"] == "8000"
    branchement = next(e for c, e in appels if c == l.m.CODE_BRANCHER)
    assert branchement["MCP_HTTP_PORT"] == "8000"                                        # l'entrée écrite est l'URL http://localhost:8000/mcp


def test_etape_browser_robot(monkeypatch):
    import lanceur

    monkeypatch.setattr(lanceur, "interroger_atelier", lambda code, env=None: {"ok": True})
    assert lanceur.etape_browser_robot({}, interactif=False)
    appels = []
    monkeypatch.setattr(lanceur, "interroger_atelier", lambda code, env=None: {"ok": False})
    monkeypatch.setattr(lanceur.shutil, "which", lambda nom: None)
    monkeypatch.setattr(lanceur, "executer", lambda cmd, **kw: appels.append(cmd))
    assert lanceur.etape_browser_robot({}, interactif=False) and appels == []  # sans Node.js : rien lancé, message
