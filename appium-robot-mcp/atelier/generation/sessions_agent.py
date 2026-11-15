"""Trace des sessions de l'agent (Cursor, Claude) : chaque appel d'outil MCP et l'écran après chaque action visible,
conservés dans le projet de tests pour que le relecteur voie comment un script a été construit.

  studio/sessions_agent/<id>/journal.jsonl   appels (heure, outil, état, arguments masqués, durée, résultat)
  studio/sessions_agent/<id>/img_<n>.png     écran après une action (navigateur : image du MCP ; mobile : adb / simctl)

Une session = une suite d'appels sans pause de plus de 30 minutes. Un script écrit par l'agent est relié à la session
active au moment de sa génération (historique de revue « généré (cursor) »). Aucun secret : les arguments arrivent
déjà masqués (atelier/domain/activite_agent.py).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from atelier.domain import projet

PAUSE_MAX = timedelta(minutes=30)
IMAGES_MAX = 400


def _racine():
    d = projet.PROJECT_DIR / "studio" / "sessions_agent"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ids() -> list[str]:
    return sorted(p.name for p in _racine().iterdir() if p.is_dir() and re.fullmatch(r"\d{8}-\d{6}", p.name))


def _derniere_ligne(sid: str) -> dict | None:
    f = _racine() / sid / "journal.jsonl"
    if not f.exists():
        return None
    lignes = [l for l in f.read_text("utf-8").splitlines() if l.strip()]
    return json.loads(lignes[-1]) if lignes else None


def session_courante(maintenant: datetime | None = None) -> str:
    """Session en cours, ou nouvelle si le dernier appel date de plus de 30 minutes."""
    maintenant = maintenant or datetime.now()
    ids = _ids()
    if ids:
        d = _derniere_ligne(ids[-1])
        if d and maintenant - datetime.fromisoformat(d["date"]) <= PAUSE_MAX:
            return ids[-1]
    sid = maintenant.strftime("%Y%m%d-%H%M%S")
    (_racine() / sid).mkdir(parents=True, exist_ok=True)
    return sid


def enregistrer_appel(ev: dict, maintenant: datetime | None = None) -> str:
    maintenant = maintenant or datetime.now()
    sid = session_courante(maintenant)
    ligne = {"date": maintenant.isoformat(timespec="seconds"), **{k: ev.get(k) for k in ("nom", "etat", "famille", "args", "duree", "resultat", "message") if ev.get(k) is not None}}
    with (_racine() / sid / "journal.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    return sid


def enregistrer_image(png: bytes, outil: str = "", maintenant: datetime | None = None) -> str | None:
    """Écran après une action : rattaché au dernier appel de la session (au plus IMAGES_MAX images par session)."""
    maintenant = maintenant or datetime.now()
    sid = session_courante(maintenant)
    d = _racine() / sid
    n = len(list(d.glob("img_*.png")))
    if n >= IMAGES_MAX or not png:
        return None
    nom = f"img_{n + 1:04d}.png"
    (d / nom).write_bytes(png)
    with (d / "journal.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": maintenant.isoformat(timespec="seconds"), "image": nom, "nom": outil, "etat": "image"}, ensure_ascii=False) + "\n")
    return nom


def lister(limite: int = 30) -> list[dict]:
    out = []
    for sid in reversed(_ids()[-limite:]):
        f = _racine() / sid / "journal.jsonl"
        lignes = [json.loads(l) for l in f.read_text("utf-8").splitlines() if l.strip()] if f.exists() else []
        appels = [l for l in lignes if l.get("etat") in ("fin", "erreur")]
        out.append({"id": sid, "debut": lignes[0]["date"] if lignes else "", "fin": lignes[-1]["date"] if lignes else "",
                    "appels": len(appels), "erreurs": sum(l["etat"] == "erreur" for l in appels), "images": sum(1 for l in lignes if l.get("image")),
                    "ecrits": sorted({str(l.get("resultat", "")).split(" : ", 1)[1] for l in appels
                                      if l.get("famille") == "ecriture" and str(l.get("resultat", "")).startswith(("fichier : ", "ecrit : "))})})
    return out


def detail(sid: str) -> dict:
    if not re.fullmatch(r"\d{8}-\d{6}", sid or ""):
        raise ValueError("Identifiant de session invalide.")
    f = _racine() / sid / "journal.jsonl"
    if not f.exists():
        raise KeyError(f"Session {sid} inconnue.")
    lignes = [json.loads(l) for l in f.read_text("utf-8").splitlines() if l.strip()]
    # une étape par appel (le début porte les arguments, la fin le résultat) ; l'image suit l'appel qui l'a produite
    etapes = []
    for l in lignes:
        if l.get("image"):
            if etapes:
                etapes[-1]["image"] = l["image"]
            continue
        if l.get("etat") in ("fin", "erreur") and etapes and etapes[-1]["nom"] == l.get("nom") and etapes[-1]["etat"] == "debut":
            etapes[-1].update({k: v for k, v in l.items() if k != "args"})
            continue
        etapes.append(dict(l))
    return {"id": sid, "etapes": etapes}


def image(sid: str, nom: str) -> bytes:
    if not re.fullmatch(r"\d{8}-\d{6}", sid or "") or not re.fullmatch(r"img_\d{4}\.png", nom or ""):
        raise ValueError("Image invalide.")
    return (_racine() / sid / nom).read_bytes()


def session_du_script(historique: list[dict]) -> str | None:
    """Session de l'agent active quand le script a été généré par Cursor (dernière génération « (cursor) »)."""
    gen = next((h for h in reversed(historique or []) if re.search(r"\(cursor\)", h.get("commentaire") or "")), None)
    if not gen:
        return None
    t = datetime.fromisoformat(gen["date"][:19])
    for sid in reversed(_ids()):
        debut = datetime.strptime(sid, "%Y%m%d-%H%M%S")
        d = _derniere_ligne(sid)
        fin = datetime.fromisoformat(d["date"]) if d else debut
        if debut - timedelta(minutes=1) <= t <= fin + PAUSE_MAX:
            return sid
    return None
