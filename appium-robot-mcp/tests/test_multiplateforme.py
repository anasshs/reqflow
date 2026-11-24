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


# --------------------------------------------------------------------------- Mac avec iPhone branchés
def test_iphone_detecte_par_devicectl_sans_libimobiledevice(monkeypatch):
    import json
    import subprocess

    from atelier.discovery import session

    devices = {"result": {"devices": [
        {"hardwareProperties": {"udid": "00008110-001A2B3C4D5E6F70", "platform": "iOS", "reality": "physical"},
         "connectionProperties": {"pairingState": "paired"}},
        {"hardwareProperties": {"udid": "00008030-0000000000000001", "platform": "iOS", "reality": "physical"},
         "connectionProperties": {"pairingState": "unpaired"}},                      # pas encore « Faire confiance »
        {"hardwareProperties": {"udid": "AAAA", "platform": "watchOS", "reality": "physical"}}]}}

    def run(cmd, *a, **k):
        if cmd[:2] == ["xcrun", "devicectl"]:
            open(cmd[-1], "w", encoding="utf-8").write(json.dumps(devices))
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[:2] == ["xcrun", "simctl"]:
            return subprocess.CompletedProcess(cmd, 0, json.dumps({"devices": {"com.apple.CoreSimulator.SimRuntime.iOS-17-5": [
                {"name": "iPhone 15", "udid": "6F1A2B3C-1111-2222-3333-444455556666", "state": "Booted"}]}}), "")
        raise AssertionError(cmd)
    monkeypatch.setattr(session, "chemin_adb", lambda: None)
    monkeypatch.setattr(session.shutil, "which", lambda c: "/usr/bin/xcrun" if c == "xcrun" else None)
    monkeypatch.setattr(session.subprocess, "run", run)
    d = session.list_devices()
    assert d["ios_physiques"] == ["00008110-001A2B3C4D5E6F70"]
    assert d["ios_simulateurs"][0]["udid"] == "6F1A2B3C-1111-2222-3333-444455556666"
    assert session.est_simulateur(d["ios_simulateurs"][0]["udid"]) and not session.est_simulateur(d["ios_physiques"][0])


def test_iphone_reel_signe_par_l_equipe_du_poste(monkeypatch):
    from atelier.integrations import appium

    monkeypatch.delenv("IOS_TEAM_ID", raising=False)
    assert appium.caps_iphone_reel("00008110-001A2B3C4D5E6F70") == {}                     # Xcode décide
    monkeypatch.setenv("IOS_TEAM_ID", "ABCDE12345")
    monkeypatch.setenv("IOS_WDA_BUNDLE_ID", "fr.exemple.wda")
    caps = appium.caps_iphone_reel("00008110-001A2B3C4D5E6F70")
    assert caps == {"appium:xcodeOrgId": "ABCDE12345", "appium:xcodeSigningId": "Apple Development",
                    "appium:updatedWDABundleId": "fr.exemple.wda"}
    assert appium.caps_iphone_reel("6F1A2B3C-1111-2222-3333-444455556666") == {}         # simulateur : pas de signature


def test_prerequis_mobiles_sur_mac(monkeypatch, tmp_path):
    from atelier.discovery import session
    from atelier.domain import prerequis

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("APPIUM_HOME", str(tmp_path))
    monkeypatch.delenv("IOS_TEAM_ID", raising=False)
    monkeypatch.setattr(session, "chemin_adb", lambda: None)
    outils = {"node", "appium", "xcrun", "xcodebuild"}
    monkeypatch.setattr(prerequis.shutil, "which", lambda c: f"/usr/local/bin/{c}" if c in outils else None)
    m = prerequis.mobile()
    assert not m["ok"] and "xcuitest" in m["detail"] and m["commandes"] == [["appium", "driver", "install", "xcuitest"]]
    (tmp_path / "node_modules" / "appium-xcuitest-driver").mkdir(parents=True)
    m = prerequis.mobile()
    assert m["ok"] and "iOS" in m["detail"] and "IOS_TEAM_ID" in m["detail"]
    outils.discard("appium")
    m = prerequis.mobile()
    assert not m["ok"] and ["npm", "install", "-g", "appium"] in m["commandes"]


def test_sans_outil_mobile_rien_a_installer(monkeypatch):
    from atelier.discovery import session
    from atelier.domain import prerequis

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(session, "chemin_adb", lambda: None)
    assert prerequis.mobile()["ok"] and prerequis.mobile()["commandes"] == []


def test_lanceur_sans_saisie_possible_ne_plante_pas():
    import lanceur

    def eof(_):
        raise EOFError
    assert lanceur._oui("Installer ?", eof) is False
