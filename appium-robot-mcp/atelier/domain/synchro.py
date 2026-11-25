"""Synchronisation du travail et de la connaissance d'un projet avec la base de l'atelier (docs/BASE_ATELIER.md).

La base est la référence partagée entre postes ; le dossier du projet en est la copie de travail locale, celle que les
moteurs de l'atelier lisent et écrivent (aucun moteur n'a donc à changer). À chaque passage (tâche de fond de
l'atelier, quelques secondes) :
- un fichier modifié ici part dans la base ; un fichier modifié par un autre poste arrive ici ;
- modifié des deux côtés depuis le dernier passage : la version de la base s'applique, la version locale est gardée à
  côté (« <fichier>.conflit-<poste>-<date> ») et le conflit est signalé — rien ne se perd ;
- une suppression se propage, mais au-delà de SEUIL_SUPPRESSIONS fichiers d'un coup, rien n'est supprimé sans
  confirmation (garde-fou contre un dossier vidé par erreur).

Ce qui se synchronise : le travail (Kanban, US, maintenances, demandes, travaux de l'orchestrateur, revues, campagnes,
gouvernance, stratégie…) et la connaissance (carte de l'application et captures, Discovery, parcours, modèles MBT,
instantané Xray, couverture, déclarations). Ce qui ne se synchronise pas : le code des tests (Git / GitLab), les
résultats de runs (lourds, locaux), les traces des sessions de l'agent, les fichiers temporaires.

Collection de la base : « fichiers:<projet> », clé = chemin relatif, document = {hash, taille, texte | b64, poste}.
État du dernier passage : ~/.atelier/synchro/<projet>.json (hash et version de chaque fichier).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import threading
from datetime import datetime
from pathlib import Path

from atelier.domain import magasin

# dossiers et fichiers du projet partagés par la base
TRAVAIL = ("conception/", "orchestration/", "studio/", "executions/", "gouvernance/", "pilotage/", "strategie/", "testabilite/",
           "validations/", "analyses/", "atelier_regles/", "atelier_statuts.yaml", "atelier_cursor.yaml", "atelier_roles.yaml")
# atelier_regles/ : versions des règles de l'agent (source partagée) ; .cursor/rules, CLAUDE.md, .claude/skills et .mcp.json
# en sont l'installation sur chaque poste (là où Cursor / Claude Code lisent) : jamais synchronisés, régénérés localement.
CONNAISSANCE = ("app_map/", "discovery/", "parcours/", "comportement/", "patrimoine/", "couverture/", "connaissance/")
PARTAGES = TRAVAIL + CONNAISSANCE
EXCLUS = ("studio/sessions_agent/", "results/", ".git/")
SUFFIXES_EXCLUS = (".tmp", ".lock", ".pyc", ".bak", ".swp")
TAILLE_MAX = 20 * 1024 * 1024
SEUIL_SUPPRESSIONS = 25
_VERROUS: dict[str, threading.Lock] = {}


def poste() -> str:
    return os.environ.get("ATELIER_POSTE_NOM") or socket.gethostname()


def _collection(pid: str) -> str:
    return f"fichiers:{pid}"


def _index_fichier(pid: str) -> Path:
    return magasin.dossier_poste() / "synchro" / f"{pid}.json"


def _lire_index(pid: str) -> dict:
    f = _index_fichier(pid)
    try:
        return json.loads(f.read_text("utf-8")) if f.exists() else {}
    except (OSError, ValueError):
        return {}


def _ecrire_index(pid: str, idx: dict):
    f = _index_fichier(pid)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(idx, ensure_ascii=False), "utf-8")
    os.replace(tmp, f)


def partage(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    if rel.startswith(EXCLUS) or rel.endswith(SUFFIXES_EXCLUS) or ".conflit-" in rel:
        return False
    return any(rel == p or (p.endswith("/") and rel.startswith(p)) for p in PARTAGES)


def _locaux(dossier: Path) -> dict:
    """{chemin relatif: (mtime, taille)} des fichiers partagés du dossier."""
    out = {}
    for p in PARTAGES:
        cible = dossier / p
        if p.endswith("/"):
            if not cible.is_dir():
                continue
            for f in cible.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(dossier).as_posix()
                    if partage(rel):
                        st = f.stat()
                        out[rel] = (st.st_mtime_ns, st.st_size)
        elif cible.is_file():
            st = cible.stat()
            out[p] = (st.st_mtime_ns, st.st_size)
    return out


def _hash(contenu: bytes) -> str:
    return hashlib.sha256(contenu).hexdigest()


def _doc(contenu: bytes) -> dict:
    try:
        return {"hash": _hash(contenu), "taille": len(contenu), "texte": contenu.decode("utf-8"), "poste": poste()}
    except UnicodeDecodeError:
        return {"hash": _hash(contenu), "taille": len(contenu), "b64": base64.b64encode(contenu).decode("ascii"), "poste": poste()}


def _contenu(doc: dict) -> bytes:
    return doc["texte"].encode("utf-8") if "texte" in doc else base64.b64decode(doc.get("b64") or "")


def _ecrire_local(dossier: Path, rel: str, contenu: bytes):
    f = dossier / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f.name + ".synchro.tmp")
    tmp.write_bytes(contenu)
    os.replace(tmp, f)


def _horodatage() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def synchroniser(pid: str, dossier: str | Path, confirmer_suppressions: bool = False) -> dict:
    """Un passage de synchronisation du projet pid (dossier : sa copie locale). Rend le bilan du passage."""
    dossier = Path(dossier)
    verrou = _VERROUS.setdefault(pid, threading.Lock())
    if not verrou.acquire(blocking=False):
        return {"projet": pid, "en_cours": True}
    try:
        return _passage(pid, dossier, confirmer_suppressions)
    finally:
        verrou.release()


def _passage(pid: str, dossier: Path, confirmer: bool) -> dict:
    coll = _collection(pid)
    idx = _lire_index(pid)
    locaux = _locaux(dossier)
    distants = magasin.versions(coll)
    bilan = {"projet": pid, "envoyes": [], "recus": [], "supprimes_base": [], "supprimes_local": [], "conflits": [], "ignores": [],
             "suppressions_en_attente": [], "date": datetime.now().astimezone().isoformat(timespec="seconds")}

    def change_local(rel) -> tuple[bool, bytes | None]:
        """(modifié depuis le dernier passage ?, contenu si lu)."""
        e = idx.get(rel)
        mt, taille = locaux[rel]
        if e and e.get("mtime") == mt and e.get("taille") == taille:
            return False, None
        contenu = (dossier / rel).read_bytes()
        return (not e or _hash(contenu) != e.get("hash")), contenu

    a_supprimer_base, a_supprimer_local = [], []
    for rel in sorted(set(locaux) | set(distants) | set(idx)):
        e = idx.get(rel)
        v_dist = distants.get(rel)
        try:
            if rel in locaux:
                if locaux[rel][1] > TAILLE_MAX:
                    bilan["ignores"].append(rel)
                    continue
                modifie, contenu = change_local(rel)
                if not modifie and contenu is None and e and v_dist == e.get("version"):
                    continue  # rien n'a bougé
                if contenu is None:
                    contenu = (dossier / rel).read_bytes()
                h = _hash(contenu)
                if v_dist is None:
                    if e and not modifie:  # supprimé par un autre poste, intact ici
                        a_supprimer_local.append(rel)
                        continue
                    v = magasin.ecrire(coll, rel, _doc(contenu), version=0, par=poste())
                    bilan["envoyes"].append(rel)
                elif e and v_dist == e.get("version"):
                    if not modifie:
                        idx[rel] = {**e, "mtime": locaux[rel][0], "taille": locaux[rel][1]}
                        continue
                    v = magasin.ecrire(coll, rel, _doc(contenu), version=v_dist, par=poste())
                    bilan["envoyes"].append(rel)
                else:  # la base a bougé (ou première rencontre)
                    d = magasin.lire(coll, rel)
                    distant = _contenu(d)
                    if _hash(distant) == h:
                        v = d["_version"]
                    elif e and not modifie:
                        _ecrire_local(dossier, rel, distant)
                        h, v = _hash(distant), d["_version"]
                        bilan["recus"].append(rel)
                    else:  # modifié des deux côtés : la base s'applique, la version locale est gardée à côté
                        copie = f"{rel}.conflit-{poste()}-{_horodatage()}"
                        _ecrire_local(dossier, copie, contenu)
                        _ecrire_local(dossier, rel, distant)
                        h, v = _hash(distant), d["_version"]
                        bilan["conflits"].append({"fichier": rel, "copie_locale": copie, "par": d.get("_par", "")})
                st = (dossier / rel).stat()
                idx[rel] = {"hash": h, "version": v, "mtime": st.st_mtime_ns, "taille": st.st_size}
            elif v_dist is not None:
                if e and v_dist == e.get("version"):  # supprimé ici, intact dans la base
                    a_supprimer_base.append(rel)
                    continue
                d = magasin.lire(coll, rel)
                contenu = _contenu(d)
                _ecrire_local(dossier, rel, contenu)
                st = (dossier / rel).stat()
                idx[rel] = {"hash": _hash(contenu), "version": d["_version"], "mtime": st.st_mtime_ns, "taille": st.st_size}
                bilan["recus"].append(rel)
            else:
                idx.pop(rel, None)  # supprimé des deux côtés
        except magasin.Conflit:
            bilan["conflits"].append({"fichier": rel, "copie_locale": "", "par": "écriture concurrente : repris au prochain passage"})

    if len(a_supprimer_base) + len(a_supprimer_local) > SEUIL_SUPPRESSIONS and not confirmer:
        bilan["suppressions_en_attente"] = sorted(a_supprimer_base + a_supprimer_local)
    else:
        for rel in a_supprimer_base:
            try:
                magasin.supprimer(coll, rel, version=idx[rel]["version"], par=poste())
                bilan["supprimes_base"].append(rel)
                idx.pop(rel, None)
            except magasin.Conflit:
                pass
        for rel in a_supprimer_local:
            try:
                (dossier / rel).unlink()
            except FileNotFoundError:
                pass
            bilan["supprimes_local"].append(rel)
            idx.pop(rel, None)
    _ecrire_index(pid, idx)
    _DERNIER[pid] = bilan
    return bilan


_DERNIER: dict[str, dict] = {}


def etat(pid: str) -> dict:
    idx = _lire_index(pid)
    return {"projet": pid, "fichiers": len(idx), "dernier": _DERNIER.get(pid), "poste": poste()}


def projet_actif() -> tuple[str, Path] | None:
    """(id, dossier) du projet actif de ce poste, s'il est déclaré."""
    from atelier.domain import projets

    p = projets.actif()
    return (p["id"], Path(p["dossier"])) if p and p.get("dossier") else None
