"""Classement des actions de l'application (cahier Discovery : Safe / Controlled / Sensitive / Forbidden).

- **forbidden** (interdite)  : liste rouge de l'application ; jamais exécutée par l'atelier, en aucun mode ;
- **sensitive** (sensible)   : action métier à conséquence, c.-à-d. un sujet sensible (virement, paiement,
  bénéficiaire, plafond…) ET un verbe d'action (effectuer, confirmer, ajouter, supprimer, modifier, nouveau…), ou
  élément marqué sensible pendant une session. Un menu, un onglet ou un lien qui ne fait que naviguer vers le sujet
  (« Virements », « Mes bénéficiaires ») reste de la navigation ; exécutée seulement sur un environnement qui l'autorise ET après confirmation
  explicite ; jamais par l'exploration autonome ni sur suggestion de l'IA ;
- **controlled** (contrôlée) : saisie ou sélection (champ, case à cocher) : faite à la main, jamais par l'exploration ;
- **safe** (sûre)            : navigation (bouton, lien, onglet, élément de liste) : seule classe que l'exploration
  autonome et les suggestions touchent.

Règles par application (app.yaml, clé « classement ») : motifs sensibles, classement manuel par clé d'élément,
classes autorisées par environnement, et par environnement (décision humaine journalisée dans
discovery/autorisations.jsonl) :
- motifs de la liste rouge levés sur cet environnement (actions guidées : automaticien ou agent ; l'exploration
  autonome garde toujours la liste rouge complète) ;
- agent autorisé : Cursor / Claude peuvent exécuter les actions sensibles pendant une session Discovery sur cet
  environnement (sinon la confirmation d'une action sensible reste humaine) ;
- exploration sans restriction : l'exploration autonome (et ses suggestions) touche aussi les actions sensibles et les
  motifs de liste rouge levés pour cet environnement (décision de l'automaticien, ex. une recette jetable). L'invariant de sécurité 6 s'applique : une action sensible n'est exécutée que
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
# verbes (et marques) d'action : sans l'un d'eux, un sujet sensible n'est qu'une destination de navigation
VERBES_ACTION = re.compile(
    r"effectu|confirm|valid|envoy|\bpa(y|i)(e|er|ez)\b|r[eè]gl(er|ez)\b|ajout|supprim|modifi|enregistr|souscri|sign|transf[eé]r|[eé]met|"
    r"oppos|bloqu|d[ée]bloqu|r[ée]sili|accept|command|recharg|initi|programm|nouveau|nouvelle|cr[ée]er|activer|d[ée]sactiver|"
    r"changer|r[ée]initialis|annuler|retirer|verser|ordonn", re.I)
# classes autorisées en guidé (action déclenchée depuis le Studio) quand l'environnement n'est pas déclaré
POLITIQUE_DEFAUT = ["safe", "controlled"]
CONTEXTES = ("exploration", "suggestion", "guidee")


def regles(app: str | None = None) -> dict:
    from atelier.discovery import carte

    c = carte.config_app(app).get("classement") or {}
    return {"sensibles": c.get("sensibles") or list(SENSIBLES_DEFAUT), "cles": dict(c.get("cles") or {}),
            "environnements": {k: list(v) for k, v in (c.get("environnements") or {}).items()},
            "liste_rouge_levee": {k: list(v) for k, v in (c.get("liste_rouge_levee") or {}).items() if v},
            "agent_sensible": {k: dict(v) for k, v in (c.get("agent_sensible") or {}).items() if (v or {}).get("actif")},
            "exploration_libre": {k: dict(v) for k, v in (c.get("exploration_libre") or {}).items() if (v or {}).get("actif")}}


def exploration_libre(environnement: str, r: dict | None = None) -> bool:
    """L'exploration autonome est-elle sans restriction sur cet environnement (réglage journalisé) ?"""
    r = r or regles()
    return bool(environnement) and bool(r.get("exploration_libre", {}).get(environnement.strip().lower()))


def environnement_session() -> str:
    """Environnement de la session Discovery en cours (vide sans session)."""
    try:
        from atelier.discovery import sessions_discovery

        s = sessions_discovery.active()
        return ((s or {}).get("config") or {}).get("environnement", "") if s else ""
    except Exception:  # noqa: BLE001
        return ""


def _journaliser(app: str | None, quoi: str, environnement: str, avant, apres):
    import json
    import os
    from datetime import datetime

    from atelier.domain import projet

    f = projet.PROJECT_DIR / "discovery" / "autorisations.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": datetime.now().astimezone().isoformat(timespec="seconds"),
                             "auteur": os.environ.get("USERNAME") or os.environ.get("USER") or "automaticien",
                             "application": app or "", "environnement": environnement, "quoi": quoi, "avant": avant, "apres": apres},
                            ensure_ascii=False) + "\n")


def journal_autorisations(limite: int = 100) -> list[dict]:
    import json

    from atelier.domain import projet

    f = projet.PROJECT_DIR / "discovery" / "autorisations.jsonl"
    return [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()][-limite:][::-1] if f.exists() else []


def maj_regles(sensibles: list[str] | None = None, environnements: dict | None = None, app: str | None = None,
               liste_rouge_levee: dict | None = None, agent_sensible: dict | None = None,
               exploration_libre: dict | None = None) -> dict:
    from atelier.discovery import carte

    r = regles(app)
    if liste_rouge_levee is not None:
        rouge = set((carte.config_app(app).get("liste_rouge") or {}).get("textes") or [])
        nouveau = {}
        for env, motifs in liste_rouge_levee.items():
            env, m = str(env).strip(), [x.strip() for x in motifs or [] if str(x).strip()]
            inconnus = [x for x in m if x not in rouge]
            if inconnus:
                raise ValueError(f"Pas dans la liste rouge de l'application : {', '.join(inconnus)}.")
            if env and m:
                nouveau[env] = sorted(set(m))
        for env in set(nouveau) | set(r["liste_rouge_levee"]):
            if nouveau.get(env) != r["liste_rouge_levee"].get(env):
                _journaliser(app, "liste rouge levée", env, r["liste_rouge_levee"].get(env, []), nouveau.get(env, []))
        r["liste_rouge_levee"] = nouveau
    if agent_sensible is not None:
        from datetime import datetime
        import os

        nouveau = {}
        for env, actif in agent_sensible.items():
            env = str(env).strip()
            if env and actif:
                nouveau[env] = r["agent_sensible"].get(env) or {
                    "actif": True, "par": os.environ.get("USERNAME") or os.environ.get("USER") or "automaticien",
                    "date": datetime.now().astimezone().isoformat(timespec="seconds")}
        for env in set(nouveau) | set(r["agent_sensible"]):
            if bool(nouveau.get(env)) != bool(r["agent_sensible"].get(env)):
                _journaliser(app, "agent autorisé sur les actions sensibles", env, bool(r["agent_sensible"].get(env)), bool(nouveau.get(env)))
        r["agent_sensible"] = nouveau
    if exploration_libre is not None:
        from datetime import datetime
        import os

        nouveau = {}
        for env, actif in exploration_libre.items():
            env = str(env).strip().lower()
            if env and actif:
                nouveau[env] = r["exploration_libre"].get(env) or {
                    "actif": True, "par": os.environ.get("USERNAME") or os.environ.get("USER") or "automaticien",
                    "date": datetime.now().astimezone().isoformat(timespec="seconds")}
        for env in set(nouveau) | set(r["exploration_libre"]):
            if bool(nouveau.get(env)) != bool(r["exploration_libre"].get(env)):
                _journaliser(app, "exploration autonome sans restriction", env, bool(r["exploration_libre"].get(env)), bool(nouveau.get(env)))
        r["exploration_libre"] = nouveau
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


def interdit(element: dict, app: str | None = None, r: dict | None = None, environnement: str = "") -> str:
    """Motif de la liste rouge qui interdit l'élément (vide sinon) ; les motifs levés pour l'environnement ne
    comptent pas (sans environnement : liste rouge complète)."""
    from atelier.discovery import carte

    r = r or regles(app)
    lr = carte.config_app(app).get("liste_rouge") or {}
    if element.get("key") in (lr.get("cles") or []):
        return element.get("key")
    if environnement and exploration_libre(environnement, r):  # sans restriction : seules les clés interdites une à une restent
        return ""
    leves = set(r["liste_rouge_levee"].get(environnement, [])) if environnement else set()
    txt = f"{element.get('key', '')} {element.get('libelle', '')}"
    return next((m for m in (lr.get("textes") or carte.LISTE_ROUGE_DEFAUT) if m not in leves and re.search(m, txt, re.I)), "")


def classer(element: dict, app: str | None = None, r: dict | None = None, environnement: str = "") -> dict:
    """Classe d'un élément observé ({key, type, libelle}) et raison, du plus strict au moins strict. environnement :
    les motifs de liste rouge levés pour cet environnement ne s'appliquent pas (actions guidées seulement)."""
    r = r or regles(app)
    cle = element.get("key") or ""
    txt = f"{cle} {element.get('libelle') or ''}"
    rouge = interdit(element, app, r, environnement)
    if rouge:
        return {"classe": "forbidden", "raison": f"liste rouge de l'application (« {rouge} »)"}
    manuel = r["cles"].get(cle)
    if manuel:
        return {"classe": manuel, "raison": "classement manuel"}
    motif = next((m for m in r["sensibles"] if re.search(m, txt, re.I)), None)
    verbe = VERBES_ACTION.search(txt)
    if motif and verbe:
        return {"classe": "sensitive", "raison": f"action « {verbe.group(0)} » sur un sujet sensible (« {motif} »)"}
    if element.get("type") in CONTROLES:
        return {"classe": "controlled", "raison": "saisie ou sélection"}
    if motif:
        return {"classe": "safe", "raison": f"navigation vers un sujet sensible (« {motif} »), sans action"}
    return {"classe": "safe", "raison": "navigation"}


def autorise(element: dict, contexte: str = "guidee", environnement: str = "", confirme: bool = False,
             app: str | None = None, agent: bool = False) -> dict:
    """L'atelier peut-il exécuter cette action ? exploration et suggestion : « safe » seulement ; guidé : classes
    autorisées pour l'environnement ; une action sensible exige en plus une confirmation explicite."""
    if contexte not in CONTEXTES:
        raise ValueError(f"Contexte : {', '.join(CONTEXTES)}.")
    r = regles(app)
    libre = contexte in ("exploration", "suggestion") and exploration_libre(environnement, r)
    # exploration : liste rouge complète, sauf exploration sans restriction sur cet environnement
    c = classer(element, app, r, environnement if contexte == "guidee" or libre else "")
    classe = c["classe"]
    if classe == "forbidden":
        return {**c, "autorise": False, "motif": "Action interdite (liste rouge) : jamais exécutée par l'atelier."}
    if libre:
        return {**c, "autorise": True, "motif": "", "exploration_libre": True}
    if contexte in ("exploration", "suggestion"):
        ok = classe == "safe"
        return {**c, "autorise": ok, "motif": "" if ok else f"Action {LIBELLES[classe]} : jamais en {contexte}, à faire à la main."}
    permises = r["environnements"].get(environnement, POLITIQUE_DEFAUT)
    if classe not in permises:
        return {**c, "autorise": False,
                "motif": f"Action {LIBELLES[classe]} non autorisée sur l'environnement « {environnement or 'non précisé'} » "
                         f"(autorisées : {', '.join(LIBELLES[x] for x in permises)})."}
    if classe == "sensitive" and agent:
        a = r["agent_sensible"].get(environnement)
        if not a:
            return {**c, "autorise": False, "confirmation": True,
                    "motif": f"Action sensible : réservée à l'automaticien sur « {environnement or 'environnement non précisé'} » "
                             "(Discovery › Settings : autoriser l'agent sur cet environnement)."}
        return {**c, "autorise": True, "motif": "", "par_agent": True, "autorisation": a}
    if classe == "sensitive" and not confirme:
        return {**c, "autorise": False, "confirmation": True, "motif": "Action sensible : confirmation explicite requise."}
    return {**c, "autorise": True, "motif": ""}
