"""Comptes de l'atelier : qui se connecte, avec quel rôle, à quels projets (docs/BASE_ATELIER.md).

Les comptes vivent dans la base (collection « utilisateurs »). Tant qu'aucun compte n'existe, l'atelier reste en mode
ouvert, comme avant (l'utilisateur est le compte du poste) ; l'assistant du premier lancement crée le premier compte,
responsable. Dès qu'un compte existe, il faut se connecter.

Mot de passe : jamais gardé, seulement son empreinte PBKDF2-SHA256 (sel aléatoire, 310 000 itérations), comparée en
temps constant ; 12 caractères au moins. Rôles : ceux de domain/roles.py (lecteur, automaticien, relecteur,
responsable). Projets : la liste des projets ouverts au compte (« * » : tous). Il reste toujours au moins un
responsable actif. Les sessions vivent en mémoire de l'atelier (un redémarrage demande de se reconnecter).

Base sur le serveur de données (magasin.BaseDistante) : les comptes vivent sur le serveur, qui vérifie le mot de passe
et les droits ; l'atelier du poste garde, par session, le jeton du serveur de ce compte (jamais montré à la page).
"""
from __future__ import annotations

import contextvars
import hashlib
import hmac
import re
import secrets
import threading
import time
from datetime import datetime

from atelier.domain import magasin
from atelier.domain.roles import ORDRE, ROLES

COLLECTION = "utilisateurs"
ITERATIONS = 310_000
LONGUEUR_MIN = 12
DUREE_SESSION = 12 * 3600
IDENTIFIANT = re.compile(r"^[a-zA-Z0-9._-]{2,40}$")

COURANT: contextvars.ContextVar[dict | None] = contextvars.ContextVar("utilisateur_atelier", default=None)
_SESSIONS: dict[str, tuple[str, float]] = {}
_VERROU = threading.Lock()
_JETONS_SERVEUR: dict[str, str] = {}  # compte -> jeton du serveur de données (base distante)
_CACHE: dict[str, tuple[float, object]] = {}


def _d() -> bool:
    try:
        return magasin.distante()
    except Exception:  # noqa: BLE001
        return False


def _cache(cle: str, fn, duree: float = 20):
    x = _CACHE.get(cle)
    if x and x[0] > time.time():
        return x[1]
    v = fn()
    _CACHE[cle] = (time.time() + duree, v)
    return v


def _distant(route: str, corps: dict | None = None, jeton: str | None = None):
    _CACHE.clear()
    return magasin.base().appel(route, corps or {}, jeton=jeton)


def jeton_serveur() -> str:
    """Jeton du serveur de données pour le compte courant (base distante)."""
    u = COURANT.get()
    return _JETONS_SERVEUR.get(u["identifiant"], "") if u else ""


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _empreinte(mot_de_passe: str, sel: bytes, iterations: int = ITERATIONS) -> str:
    return hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode("utf-8"), sel, iterations).hex()


def _vue(u: dict) -> dict:
    """Compte sans son empreinte : ce que l'API peut rendre."""
    return {k: u.get(k) for k in ("identifiant", "nom", "role", "projets", "actif", "cree", "derniere_connexion")} | {"version": u.get("_version")}


def _verifier_mot_de_passe(m: str):
    if len(m or "") < LONGUEUR_MIN:
        raise ValueError(f"Mot de passe : {LONGUEUR_MIN} caractères au moins.")


def actifs() -> bool:
    """Des comptes existent : la connexion est exigée."""
    try:
        if _d():
            return bool(_cache("actifs", lambda: magasin.base().appel("comptes/actifs", jeton="")["actifs"]))
        return any(u.get("actif", True) for u in magasin.lister(COLLECTION))
    except Exception:  # noqa: BLE001 — base illisible : on ne bloque pas l'atelier, on le signale ailleurs
        return False


def lister() -> list[dict]:
    if _d():
        return magasin.base().appel("comptes/lister")["comptes"]
    return [_vue(u) for u in magasin.lister(COLLECTION)]


def obtenir(identifiant: str) -> dict | None:
    ident = (identifiant or "").lower()
    if _d():
        jeton = _JETONS_SERVEUR.get(ident) or None
        return _cache(f"compte:{ident}", lambda: magasin.base().appel("comptes/obtenir", {"identifiant": ident}, jeton=jeton).get("compte"))
    u = magasin.lire(COLLECTION, ident)
    return _vue(u) if u else None


def _responsables_actifs(sauf: str = "") -> int:
    return sum(1 for u in magasin.lister(COLLECTION) if u.get("role") == "responsable" and u.get("actif", True) and u["_cle"] != sauf)


def creer(identifiant: str, mot_de_passe: str, role: str = "automaticien", nom: str = "", projets: list[str] | None = None, par: str = "") -> dict:
    """Nouveau compte. Le premier compte est forcément responsable (sinon personne ne pourrait gérer les autres)."""
    ident = (identifiant or "").strip().lower()
    if _d():
        return _distant("comptes/creer", {"identifiant": ident, "mot_de_passe": mot_de_passe, "role": role, "nom": nom, "projets": projets or ["*"]})["compte"]
    if not IDENTIFIANT.match(ident):
        raise ValueError("Identifiant : 2 à 40 caractères, lettres, chiffres, point, tiret ou souligné.")
    if role not in ROLES:
        raise ValueError(f"Rôle : {', '.join(ORDRE)}.")
    if magasin.lire(COLLECTION, ident):
        raise ValueError(f"Le compte {ident} existe déjà.")
    if not actifs() and role != "responsable":
        raise ValueError("Le premier compte est responsable : il gère ensuite les autres.")
    _verifier_mot_de_passe(mot_de_passe)
    sel = secrets.token_bytes(16)
    doc = {"identifiant": ident, "nom": (nom or ident).strip()[:80], "role": role, "projets": list(projets or ["*"]), "actif": True,
           "sel": sel.hex(), "iterations": ITERATIONS, "empreinte": _empreinte(mot_de_passe, sel), "cree": _maintenant(), "derniere_connexion": ""}
    magasin.ecrire(COLLECTION, ident, doc, version=0, par=par or ident)
    return obtenir(ident)


def modifier(identifiant: str, role: str | None = None, projets: list[str] | None = None, actif: bool | None = None, nom: str | None = None,
             version: int | None = None, par: str = "") -> dict:
    ident = (identifiant or "").lower()
    if _d():
        return _distant("comptes/modifier", {"identifiant": ident, "role": role, "projets": projets, "actif": actif, "nom": nom})["compte"]
    u = magasin.lire(COLLECTION, ident)
    if not u:
        raise KeyError(f"Compte inconnu : {ident}")
    if role is not None and role not in ROLES:
        raise ValueError(f"Rôle : {', '.join(ORDRE)}.")
    perd_responsable = u.get("role") == "responsable" and ((role is not None and role != "responsable") or actif is False)
    if perd_responsable and _responsables_actifs(sauf=ident) == 0:
        raise ValueError("Il faut toujours au moins un responsable actif.")
    for k, v in (("role", role), ("projets", projets), ("actif", actif), ("nom", nom)):
        if v is not None:
            u[k] = v
    magasin.ecrire(COLLECTION, ident, u, version=u["_version"] if version is None else version, par=par)
    if actif is False:
        fermer_sessions(ident)
    return obtenir(ident)


def changer_mot_de_passe(identifiant: str, nouveau: str, ancien: str | None = None, par: str = "") -> dict:
    """Par le titulaire (ancien mot de passe exigé) ou par un responsable (réinitialisation, ancien = None)."""
    ident = (identifiant or "").lower()
    if _d():
        r = _distant("comptes/mot-de-passe", {"identifiant": ident, "nouveau": nouveau, "ancien": ancien})["compte"]
        fermer_sessions(ident)
        return r
    u = magasin.lire(COLLECTION, ident)
    if not u:
        raise KeyError(f"Compte inconnu : {ident}")
    if ancien is not None and not _correct(u, ancien):
        raise PermissionError("Mot de passe actuel incorrect.")
    _verifier_mot_de_passe(nouveau)
    sel = secrets.token_bytes(16)
    u.update(sel=sel.hex(), iterations=ITERATIONS, empreinte=_empreinte(nouveau, sel))
    magasin.ecrire(COLLECTION, ident, u, version=u["_version"], par=par or ident)
    fermer_sessions(ident)
    return obtenir(ident)


def _correct(u: dict, mot_de_passe: str) -> bool:
    try:
        calc = _empreinte(mot_de_passe or "", bytes.fromhex(u["sel"]), int(u.get("iterations") or ITERATIONS))
    except (KeyError, ValueError):
        return False
    return hmac.compare_digest(calc, u.get("empreinte", ""))


def connecter(identifiant: str, mot_de_passe: str) -> tuple[str, dict]:
    """Rend (jeton de session, compte). Même refus que le compte existe ou non (rien n'indique lequel est faux)."""
    ident = (identifiant or "").strip().lower()
    if _d():  # le serveur vérifie ; l'atelier garde son jeton pour les appels de ce compte
        r = magasin.base().appel("connexion", {"identifiant": ident, "mot_de_passe": mot_de_passe}, jeton="")
        _JETONS_SERVEUR[ident] = r["jeton"]
        magasin.base().jeton_fond = r["jeton"]
        _CACHE.clear()
        jeton = secrets.token_urlsafe(32)
        with _VERROU:
            _SESSIONS[jeton] = (ident, time.time() + DUREE_SESSION)
        return jeton, r["compte"]
    u = magasin.lire(COLLECTION, ident)
    ok = _correct(u, mot_de_passe) if u else (_empreinte(mot_de_passe or "", b"\0" * 16) and False)  # même coût de calcul
    if not ok or not u.get("actif", True):
        raise PermissionError("Identifiant ou mot de passe incorrect.")
    u["derniere_connexion"] = _maintenant()
    magasin.ecrire(COLLECTION, ident, u, par=ident)
    jeton = secrets.token_urlsafe(32)
    with _VERROU:
        _SESSIONS[jeton] = (ident, time.time() + DUREE_SESSION)
    return jeton, obtenir(ident)


def session(jeton: str) -> dict | None:
    """Compte de la session (None : absente, expirée, ou compte désactivé)."""
    if not jeton:
        return None
    with _VERROU:
        s = _SESSIONS.get(jeton)
        if not s or s[1] < time.time():
            _SESSIONS.pop(jeton, None)
            return None
    u = obtenir(s[0])
    return u if u and u.get("actif", True) else None


def deconnecter(jeton: str):
    with _VERROU:
        _SESSIONS.pop(jeton, None)


def fermer_sessions(identifiant: str):
    with _VERROU:
        for j in [j for j, (i, _) in _SESSIONS.items() if i == identifiant]:
            _SESSIONS.pop(j, None)
        _JETONS_SERVEUR.pop(identifiant, None)


def courant() -> dict | None:
    return COURANT.get()


def projet_permis(pid: str, u: dict | None = None) -> bool:
    """Le compte (courant par défaut) peut-il ouvrir ce projet ? Mode ouvert ou sans compte connecté : oui."""
    u = u or courant()
    if not u:
        return True
    p = u.get("projets") or ["*"]
    return "*" in p or pid in p
