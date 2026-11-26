"""Détection des devices : adb hors PATH (SDK Android), appareils vus par adb mais pas prêts."""
import os
import stat

import pytest


@pytest.mark.skipif(os.name == "nt", reason="faux adb en script shell")
def test_adb_du_sdk_et_appareils_pas_prets(tmp_path, monkeypatch):
    from atelier.discovery import session

    outils = tmp_path / "sdk" / "platform-tools"
    outils.mkdir(parents=True)
    adb = outils / "adb"
    adb.write_text("#!/bin/sh\necho 'List of devices attached'\necho 'emulator-5554 device product:sdk model:Pixel'\n"
                   "echo 'R58M12ABC unauthorized usb:1-1'\n", "utf-8")
    adb.chmod(adb.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(tmp_path / "vide"))  # adb absent du PATH
    monkeypatch.setenv("ANDROID_HOME", str(tmp_path / "sdk"))
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    assert session.chemin_adb() == str(adb)
    assert [d["udid"] for d in session.list_devices()["android"]] == ["emulator-5554"]
    d = session.diagnostic_devices()
    assert {"udid": "R58M12ABC", "etat": "unauthorized"} in d["android_tous"] and d["adb"] == str(adb)


def test_sans_adb(tmp_path, monkeypatch):
    from atelier.discovery import session

    monkeypatch.setenv("PATH", str(tmp_path))
    for v in ("ANDROID_HOME", "ANDROID_SDK_ROOT", "LOCALAPPDATA"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert session.chemin_adb() is None and session.diagnostic_devices()["adb"] is None
