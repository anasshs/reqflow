"""Classement des actions de l'application (cahier Discovery : Safe / Controlled / Sensitive / Forbidden).

- **forbidden** (interdite)  : liste rouge de l'application ; jamais exécutée par l'atelier, en aucun mode ;
- **sensitive** (sensible)   : action métier à conséquence (virement, paiement, bénéficiaire, plafond…) ou marquée
  sensible pendant une session ; exécutée seulement sur un environnement qui l'autorise ET après confirmation
  explicite ; jamais par l'exploration autonome ni sur suggestion de l'IA ;
- **controlled** (contrôlée) : saisie ou sélection (champ, case à cocher) : faite à la main, jamais par l'exploration ;
- **safe** (sûre)            : navigation (bouton, lien, onglet, élément de liste) : seule classe que l'exploration
  autonome et les suggestions touchent.

Règles par application (app.yaml, clé « classement ») : motifs sensibles, classement manuel par clé d'élément,
classes autorisées par environnement. L'invariant de sécurité 6 s'applique : une action sensible n'est exécutée que
si elle est explicitement autorisée, sur un environnement autorisé.
"""
from __future__ import annotations

import re

CLASSES = ("safe", "controlled", "sensitive", "forbidden")
LIBELLES = {"safe": "Safe", "controlled": "Controlled", "sensitive": "Sensitive", "forbidden": "Forbidden"}
SENSIBLES_DEFAUT = [
    r"virement", r"paiement", r"\bpay", r"b[ée]n[ée]ficiaire", r"plafond", r"supprim", r"opposition", r"r[ée]sili",
    r"mot de passe", r"code secret", r"\botp\b", r"cl[ée] de s[ée]curit", r"ajouter un", r"modifier",
]
CONTROLES = ("champ", "case")
# classes autorisées en guidé (action déclenchée depuis le Studio) quand l'environnement n'est pas déclaré
POLITIQUE_DEFAUT = ["safe", "controlled"]
CONTEXTES = ("exploration", "suggestion", "guidee")


def regles(app: str | None = None) -> dict:
    from atelier.discovery import carte

    c = carte.config_app(app).get("classement") or {}
    return {"sensibles": c.get("sensibles") or list(SENSIBLES_DEFAUT), "cles": dict(c.get("cles") or {}),
            "environnements": {k: list(v) for k, v in (c.get("environnements") or {}).items()}}


def maj_regles(sensibles: list[str] | None = None, environnements: dict | None = None, app: str | None = None) -> dict:
    from atelier.discovery import carte

    r = regles(app)
    if sensibles is not None:
        motifs = [s.strip() for s in sensibles if str(s).strip()]
        for m in motifs:
            re.compile(m)  # motif invalide : erreur explicite plutôt qu'un classement faux
        r["sensibles"] = motifs
    if environnements is not None:
        envs = {}
        for env, cl in environnements.items():
            env = str(env).strip()
            if not env:
                continue
            inconnues = set(cl) - set(CLASSES)
            if inconnues:
                raise ValueError(f"Classe inconnue : {', '.join(sorted(inconnues))} ({', '.join(CLASSES)}).")
            if "forbidden" in cl:
                raise ValueError("Une action interdite (liste rouge) n'est autorisée sur aucun environnement.")
            envs[env] = [c for c in CLASSES if c in cl]
        r["environnements"] = envs
    carte.maj_app(app, classement=r)
    return r


def marquer(cle: str, classe: str, app: str | None = None) -> dict:
    """Classement manuel d'un élément (par sa clé) ; « auto » retire le classement manuel."""
    from atelier.discovery import carte

    if not cle.strip():
        raise ValueError("Clé d'élément obligatoire.")
    if classe not in CLASSES + ("auto",):
        raise ValueError(f"Classe : {', '.join(CLASSES)} ou auto.")
    r = regles(app)
    if classe == "auto":
        r["cles"].pop(cle, None)
    else:
        r["cles"][cle] = classe
    carte.maj_app(app, classement=r)
    return r


def classer(element: dict, app: str | None = None, r: dict | None = None) -> dict:
    """Classe d'un élément observé ({key, type, libelle}) et raison, du plus strict au moins strict."""
    from atelier.discovery import carte

    r = r or regles(app)
    cle = element.get("key") or ""
    txt = f"{cle} {element.get('libelle') or ''}"
    if carte.interdit(element, app):
        return {"classe": "forbidden", "raison": "liste rouge de l'application"}
    manuel = r["cles"].get(cle)
    if manuel:
        return {"classe": manuel, "raison": "classement manuel"}
    motif = next((m for m in r["sensibles"] if re.search(m, txt, re.I)), None)
    if motif:
        return {"classe": "sensitive", "raison": f"motif sensible « {motif} »"}
    if element.get("type") in CONTROLES:
        return {"classe": "controlled", "raison": "saisie ou sélection"}
    return {"classe": "safe", "raison": "navigation"}


def autorise(element: dict, contexte: str = "guidee", environnement: str = "", confirme: bool = False,
             app: str | None = None) -> dict:
    """L'atelier peut-il exécuter cette action ? exploration et suggestion : « safe » seulement ; guidé : classes
    autorisées pour l'environnement ; une action sensible exige en plus une confirmation explicite."""
    if contexte not in CONTEXTES:
        raise ValueError(f"Contexte : {', '.join(CONTEXTES)}.")
    r = regles(app)
    c = classer(element, app, r)
    classe = c["classe"]
    if classe == "forbidden":
        return {**c, "autorise": False, "motif": "Action interdite (liste rouge) : jamais exécutée par l'atelier."}
    if contexte in ("exploration", "suggestion"):
        ok = classe == "safe"
        return {**c, "autorise": ok, "motif": "" if ok else f"Action {LIBELLES[classe]} : jamais en {contexte}, à faire à la main."}
    permises = r["environnements"].get(environnement, POLITIQUE_DEFAUT)
    if classe not in permises:
        return {**c, "autorise": False,
                "motif": f"Action {LIBELLES[classe]} non autorisée sur l'environnement « {environnement or 'non précisé'} » "
                         f"(autorisées : {', '.join(LIBELLES[x] for x in permises)})."}
    if classe == "sensitive" and not confirme:
        return {**c, "autorise": False, "confirmation": True, "motif": "Action sensible : confirmation explicite requise."}
    return {**c, "autorise": True, "motif": ""}
