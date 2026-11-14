"""Connexion Oracle en lecture (JDD), par SID ou SERVICE_NAME.

DB_<ENV>_HOST, DB_<ENV>_PORT, DB_<ENV>_SID ou DB_<ENV>_SERVICE, DB_<ENV>_USER, DB_<ENV>_PASSWORD.
DB_TIMEOUT_MS (défaut 30000) plafonne la durée de chaque appel à la base.
"""
from __future__ import annotations

import os

DELAI_MS_DEFAUT = 30000


def delai_ms() -> int:
    return int(os.environ.get("DB_TIMEOUT_MS", DELAI_MS_DEFAUT))


def connect(env: str):
    import oracledb

    e = env.upper()
    g = lambda k, d=None: os.environ.get(f"DB_{e}_{k}", d)  # noqa: E731
    host, port = g("HOST"), int(g("PORT", "1521"))
    if not (host and g("USER")):
        raise RuntimeError(f"Connexion base non configurée pour {env} (DB_{e}_HOST, DB_{e}_USER…).")
    dsn = (oracledb.makedsn(host, port, sid=g("SID")) if g("SID")
           else oracledb.makedsn(host, port, service_name=g("SERVICE")))
    con = oracledb.connect(user=g("USER"), password=g("PASSWORD"), dsn=dsn)
    con.call_timeout = delai_ms()
    return con
