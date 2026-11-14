"""Sécurité de l'interface locale (middleware ASGI, HTTP et WebSocket).

- Hôte : seuls 127.0.0.1:PORT et localhost:PORT sont acceptés (protection DNS rebinding).
- Origine : si l'en-tête Origin est présent, il doit désigner ce même hôte ; requête marquée
  « cross-site » par le navigateur refusée. Pas de CORS.
- Jeton de session : généré au démarrage, posé par la page d'accueil dans un cookie HttpOnly
  SameSite=Strict, exigé sur /api/* et /ws.
- Jeton des processus locaux (listener Robot, MCP de Cursor / Claude Desktop) : en-tête
  X-Atelier-Jeton, seul accepté sur /api/events et /api/externe/*. Lu dans
  ATELIER_JETON_EVENEMENTS, sinon généré et écrit dans un fichier lisible par le seul
  utilisateur (ATELIER_JETON_FICHIER, défaut ~/.atelier-automatisation.jeton).
- Taille des requêtes plafonnée (WEB_TAILLE_MAX, 2 Mio par défaut).
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
from http.cookies import SimpleCookie
from pathlib import Path

from atelier.integrations.interface_web import ENTETE_JETON, FICHIER_JETON_DEFAUT

COOKIE = "atelier_jeton"
ROUTES_PROCESSUS = ("/api/events", "/api/externe/")
TAILLE_MAX_DEFAUT = 2 * 1024 * 1024
PAGES = ("/", "/plateforme")  # pages qui posent le cookie de session


class TropGros(Exception):
    pass


def _egal(a: str | None, b: str) -> bool:
    return bool(a) and hmac.compare_digest(a.encode(), b.encode())


def jeton_processus() -> str:
    """Jeton des listeners et du MCP : variable d'environnement, sinon généré et publié en fichier 0600."""
    jeton = os.environ.get("ATELIER_JETON_EVENEMENTS")
    if not jeton:
        jeton = secrets.token_urlsafe(32)
        f = Path(os.environ.get("ATELIER_JETON_FICHIER", FICHIER_JETON_DEFAUT)).expanduser()
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as fh:
                fh.write(jeton)
            os.chmod(f, 0o600)
        except OSError:
            pass  # sans fichier, seul ATELIER_JETON_EVENEMENTS permet aux processus externes de se connecter
        os.environ["ATELIER_JETON_EVENEMENTS"] = jeton  # hérité par les runs Robot lancés d'ici
    return jeton


class SecuriteLocale:
    def __init__(self, app, port: int, jeton_session: str, jeton_evenements: str,
                 taille_max: int | None = None):
        self.app = app
        self.hotes = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.jeton_session = jeton_session
        self.jeton_evenements = jeton_evenements
        self.taille_max = taille_max or int(os.environ.get("WEB_TAILLE_MAX", TAILLE_MAX_DEFAUT))

    # ------------------------------------------------------------------ contrôles
    @staticmethod
    def _entetes(scope) -> dict:
        return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}

    def _refus(self, scope, h: dict) -> tuple[int, str] | None:
        hote = h.get("host", "")
        if hote not in self.hotes:
            return 403, "Hôte refusé."
        origine = h.get("origin")
        if origine is not None and origine != f"http://{hote}":
            return 403, "Origine refusée."
        if h.get("sec-fetch-site") == "cross-site":
            return 403, "Requête d'un autre site refusée."
        chemin = scope.get("path", "")
        if scope["type"] == "websocket":
            if origine is None:
                return 403, "Origine absente."
            return None if self._cookie_ok(h) else (401, "Jeton de session absent ou invalide.")
        if chemin.startswith(ROUTES_PROCESSUS):
            ok = _egal(h.get(ENTETE_JETON.lower()), self.jeton_evenements)
            return None if ok else (401, "Jeton des processus locaux absent ou invalide.")
        if chemin.startswith("/api/") or chemin.startswith("/ws"):
            return None if self._cookie_ok(h) else (401, "Session expirée : recharge la page.")
        return None

    def _cookie_ok(self, h: dict) -> bool:
        c = SimpleCookie()
        try:
            c.load(h.get("cookie", ""))
        except Exception:
            return False
        return COOKIE in c and _egal(c[COOKIE].value, self.jeton_session)

    # ------------------------------------------------------------------ ASGI
    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        h = self._entetes(scope)
        refus = self._refus(scope, h)
        if refus:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            return await _repondre(send, *refus)
        if scope["type"] == "websocket":
            return await self.app(scope, receive, send)
        try:
            if int(h.get("content-length") or 0) > self.taille_max:
                return await _repondre(send, 413, "Requête trop volumineuse.")
        except ValueError:
            return await _repondre(send, 400, "Content-Length invalide.")

        recu = 0
        commence = False

        async def recevoir():
            nonlocal recu
            msg = await receive()
            if msg["type"] == "http.request":
                recu += len(msg.get("body", b""))
                if recu > self.taille_max:
                    raise TropGros()
            return msg

        async def envoyer(msg):
            nonlocal commence
            if msg["type"] == "http.response.start":
                commence = True
                if scope.get("path") in PAGES and scope.get("method") == "GET":
                    msg = {**msg, "headers": list(msg.get("headers", [])) + [
                        (b"set-cookie", f"{COOKIE}={self.jeton_session}; HttpOnly; SameSite=Strict; Path=/"
                         .encode())]}
            await send(msg)

        try:
            await self.app(scope, recevoir, envoyer)
        except TropGros:
            if not commence:
                await _repondre(send, 413, "Requête trop volumineuse.")


async def _repondre(send, code: int, message: str):
    corps = json.dumps({"detail": message}, ensure_ascii=False).encode()
    await send({"type": "http.response.start", "status": code,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(corps)).encode())]})
    await send({"type": "http.response.body", "body": corps})
