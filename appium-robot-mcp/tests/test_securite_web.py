"""Phase 1.2 : sécurité de l'interface locale (jetons, Host, Origin, WebSocket, taille des requêtes)."""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from web_app_loader import charger_app_web, module_web  # noqa: E402

BASE = "http://127.0.0.1:8765"


@pytest.fixture
def anonyme(projet, monkeypatch, tmp_path):
    monkeypatch.setattr(module_web(), "CONFIG_PATH", tmp_path / "atelier.json")
    return TestClient(charger_app_web(), base_url=BASE)


@pytest.fixture
def connecte(anonyme):
    anonyme.get("/")
    return anonyme


def _jeton_processus() -> dict:
    return {"X-Atelier-Jeton": module_web().JETON_PROCESSUS}


# --------------------------------------------------------------------------- jeton de session
def test_accueil_pose_un_cookie_httponly_samesite_strict(anonyme):
    r = anonyme.get("/")
    assert r.status_code == 200
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("atelier_jeton=") and "HttpOnly" in cookie and "SameSite=Strict" in cookie


def test_api_refusee_sans_jeton(anonyme):
    r = anonyme.get("/api/etat")
    assert r.status_code == 401
    assert "recharge" in r.json()["detail"]


def test_api_refusee_avec_mauvais_jeton(anonyme):
    anonyme.cookies.set("atelier_jeton", "faux")
    assert anonyme.get("/api/etat").status_code == 401


def test_api_acceptee_en_nominal(connecte):
    assert connecte.get("/api/etat").status_code == 200
    assert connecte.post("/api/config", json={"jql_candidats": "project = DEMO"},
                         headers={"Origin": BASE}).status_code == 200


def test_jeton_de_session_change_a_chaque_demarrage():
    import secrets

    mod = module_web()
    assert len(mod.JETON_SESSION) >= 40 and mod.JETON_SESSION != secrets.token_urlsafe(32)


# --------------------------------------------------------------------------- Host et Origin
@pytest.mark.parametrize("hote", ["evil.example:8765", "127.0.0.1:9999", "localhost", "0.0.0.0:8765"])
def test_hote_etranger_refuse(connecte, hote):
    assert connecte.get("/api/etat", headers={"Host": hote}).status_code == 403
    assert connecte.get("/", headers={"Host": hote}).status_code == 403


def test_localhost_accepte(connecte):
    assert connecte.get("/", headers={"Host": "localhost:8765"}).status_code == 200


@pytest.mark.parametrize("origine", ["http://evil.example", "http://localhost:8765", "null", "https://127.0.0.1:8765"])
def test_origine_etrangere_refusee(connecte, origine):
    assert connecte.post("/api/agent/stop", headers={"Origin": origine}).status_code == 403


def test_requete_cross_site_refusee(connecte):
    assert connecte.post("/api/agent/stop", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_pas_de_cors(connecte):
    r = connecte.options("/api/etat", headers={"Origin": "http://evil.example",
                                                "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers


def test_documentation_openapi_desactivee(connecte):
    assert connecte.get("/docs").status_code == 404 and connecte.get("/openapi.json").status_code == 404


# --------------------------------------------------------------------------- WebSocket
def _ws(client, headers: dict, hote: str = "127.0.0.1:8765"):
    """Le client de test n'applique ni base_url ni cookies au WebSocket : on les passe comme un navigateur."""
    jeton = client.cookies.get("atelier_jeton")
    if jeton:
        headers = {**headers, "Cookie": f"atelier_jeton={jeton}"}
    return client.websocket_connect(f"ws://{hote}/ws", headers=headers)


def test_websocket_nominal(connecte):
    with _ws(connecte, {"Origin": BASE}) as ws:
        ws.send_text("ping")


@pytest.mark.parametrize("cas", ["sans_jeton", "origine_etrangere", "sans_origine", "mauvais_hote"])
def test_websocket_refuse(connecte, cas):
    client, headers, hote = connecte, {"Origin": BASE}, "127.0.0.1:8765"
    if cas == "sans_jeton":
        client = TestClient(charger_app_web(), base_url=BASE)
    elif cas == "origine_etrangere":
        headers = {"Origin": "http://evil.example"}
    elif cas == "sans_origine":
        headers = {}
    else:
        headers, hote = {"Origin": "http://evil.example:8765"}, "evil.example:8765"
    with pytest.raises(WebSocketDisconnect):
        with _ws(client, headers, hote) as ws:
            ws.receive_text()


# --------------------------------------------------------------------------- processus locaux
def test_evenements_exigent_le_jeton_des_processus(connecte):
    assert connecte.post("/api/events", json={"type": "x"}).status_code == 401  # le cookie ne suffit pas
    assert connecte.post("/api/events", json={"type": "x"}, headers={"X-Atelier-Jeton": "faux"}).status_code == 401
    assert connecte.post("/api/events", json={"type": "x"}, headers=_jeton_processus()).status_code == 200


def test_steps_externes_exigent_le_jeton_des_processus(connecte):
    assert connecte.post("/api/externe/step", json={"gherkin": "x"}).status_code == 401
    assert connecte.get("/api/externe/reponse/x123").status_code == 401


def test_jeton_des_processus_publie_pour_le_seul_utilisateur():
    from atelier.integrations import interface_web

    f = Path(os.environ["ATELIER_JETON_FICHIER"])
    assert f.read_text() == module_web().JETON_PROCESSUS == interface_web.jeton()
    if sys.platform != "win32":  # Windows : pas de droits POSIX ; le fichier vit dans le profil de l'utilisateur (ACL du profil)
        assert stat.S_IMODE(f.stat().st_mode) == 0o600
    assert os.environ["ATELIER_JETON_EVENEMENTS"] == module_web().JETON_PROCESSUS  # hérité par les runs


# --------------------------------------------------------------------------- taille et liste blanche
def test_requete_trop_volumineuse(connecte):
    r = connecte.post("/api/config", content=b"{" + b" " * (3 * 1024 * 1024) + b"}",
                      headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_requete_volumineuse_sans_content_length(connecte):
    def morceaux():
        for _ in range(40):
            yield b" " * 100_000
    r = connecte.post("/api/config", content=morceaux(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413


@pytest.mark.parametrize("nom", ["write_project_file", "run_robot", "start_session", "explore", "__class__"])
def test_actions_manuelles_en_liste_blanche(connecte, nom):
    assert connecte.post("/api/action", json={"nom": nom, "args": {}}).status_code == 400


def test_vignette_nom_controle(connecte):
    assert connecte.get("/api/carte/vignette/..%2F..%2Fapp.yaml").status_code == 404
