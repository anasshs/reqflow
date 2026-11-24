"""L'atelier fonctionne sous Windows, macOS et Linux : les consignes affichées citent les commandes du poste."""
import sys

import pytest


@pytest.mark.parametrize("plateforme,lancement,python,node", [
    ("win32", "lancer-atelier.cmd", ".venv\Scripts\python", "winget"),
    ("darwin", "./lancer-atelier.sh", ".venv/bin/python", "brew install node"),
    ("linux", "./lancer-atelier.sh", ".venv/bin/python", "gestionnaire de paquets"),
])
def test_consignes_selon_le_systeme(monkeypatch, plateforme, lancement, python, node):
    from atelier.domain import prerequis

    monkeypatch.setattr(sys, "platform", plateforme)
    assert prerequis.commande_lancement() == lancement and prerequis.python_venv() == python and node in prerequis.installer_node()


def test_adb_du_sdk_macos_trouve_hors_path(monkeypatch, tmp_path):
    import os

    from atelier.discovery import session

    adb = tmp_path / "Library" / "Android" / "sdk" / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
    adb.parent.mkdir(parents=True)
    adb.write_text("")
    monkeypatch.setattr(session.shutil, "which", lambda c: None)
    for v in ("ANDROID_HOME", "ANDROID_SDK_ROOT", "LOCALAPPDATA"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    assert os.path.normpath(session.chemin_adb()) == os.path.normpath(str(adb))


def test_lanceur_shell_en_fins_de_ligne_unix():
    from pathlib import Path

    sh = (Path(__file__).resolve().parents[1] / "lancer-atelier.sh").read_bytes()
    assert sh.startswith(b"#!/usr/bin/env sh") and b"\r\n" not in sh     # un « \r » casse le script sous macOS / Linux
