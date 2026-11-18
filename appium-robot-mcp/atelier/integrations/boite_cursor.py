"""Boîte de demandes à Cursor : envoyer une demande à l'agent sans quitter l'atelier.

L'atelier ne peut pas écrire dans le chat de Cursor : jusqu'ici chaque demande passait par « Ouvrir dans Cursor »
(lien profond), que l'automaticien relisait puis envoyait. Deux voies évitent ce va-et-vient ; le lien reste en secours.

  boîte   la demande est déposée dans une file ; Cursor vient la chercher par le MCP. L'automaticien dit UNE fois dans
          le chat « traite les demandes de l'atelier » : l'agent appelle atelier_demande_suivante (qui attend une
          demande), l'exécute, appelle atelier_demande_terminee, puis recommence ;
  cli     l'atelier lance lui-même l'agent Cursor en ligne de commande, sans fenêtre, avec la demande pour consigne.

Le mode se règle UNE fois, pour toute l'équipe (Paramètres › Cursor / Claude) : « lien » (défaut), « boite » ou « cli ».
Il est gardé dans le projet de tests (atelier_cursor.yaml, versionné). Une demande d'exploration passe toujours par le
chat : l'automaticien doit voir l'agent, lui répondre et faire lui-même les actions sensibles.

Dans les deux cas la demande est le texte que l'automaticien a choisi d'envoyer en cliquant dans l'atelier : elle a la
même valeur qu'une demande tapée dans le chat, et l'agent reste soumis aux mêmes gardes côté serveur (actions classées,
écritures en revue, aucune décision humaine par MCP).

Ligne de commande : rien n'est supposé de l'installation. La commande et ses arguments se règlent par
ATELIER_CURSOR_CLI (défaut « agent », l'installeur de Cursor pose aussi « cursor-agent ») et ATELIER_CURSOR_CLI_ARGS
(défaut : -p {demande} --output-format text --approve-mcps --trust). Sans « --force », l'agent ne modifie pas de
fichier par lui-même : il passe par les outils MCP de l'atelier, qui gardent leurs contrôles. Options relevées dans la
documentation publique de Cursor le 2026-11-18 sans avoir pu les essayer : à vérifier sur le poste (état « trouvée »).
Sous Windows la commande est un lanceur de script : la demande est alors écrite dans studio/demandes_cursor/<id>.md et
l'argument se réduit à une consigne courte sans caractère spécial (voir _lanceur_script).

Stockage : <projet>/studio/demandes_cursor.json (état de l'atelier, jamais de secret : le texte d'une demande ne
contient que des noms d'outils et des clés).
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime

from atelier.domain import projet

STATUTS = ("en attente", "prise", "terminée", "échouée", "annulée")
MODES = ("boite", "cli")
ENVOIS = {"lien": "Ouvrir le chat de Cursor avec la demande (à relire et envoyer)",
          "boite": "Boîte de demandes : Cursor vient la chercher (lui dire une fois « traite les demandes de l'atelier »)",
          "cli": "Ligne de commande : l'atelier lance Cursor sans fenêtre"}
ATTENTE_MAX_S = 40          # un outil MCP qui ne répond pas est coupé par le client : on rend la main avant
ARGS_DEFAUT = "-p {demande} --output-format text --approve-mcps --trust"
GARDEES = 60                # demandes conservées (les plus récentes)
_verrou = threading.Lock()
CONSIGNE_SUITE = ("Exécute cette demande comme si l'automaticien venait de la taper dans le chat, avec les règles de l'atelier. "
                  "Quand elle est finie (ou impossible), appelle atelier_demande_terminee(id, resume), puis rappelle "
                  "atelier_demande_suivante() pour attendre la suivante.")
CONSIGNE_VIDE = ("Aucune demande pour l'instant. Rappelle atelier_demande_suivante() pour continuer d'attendre : ne t'arrête "
                 "que si l'automaticien te le dit dans le chat.")


def _fichier():
    return projet.PROJECT_DIR / "studio" / "demandes_cursor.json"


def _fichier_reglage():
    return projet.PROJECT_DIR / "atelier_cursor.yaml"


def envoi() -> str:
    """Mode d'envoi des demandes réglé pour le projet ; « lien » tant que rien n'est réglé ou si le fichier est illisible."""
    import yaml

    f = _fichier_reglage()
    try:
        v = ((yaml.safe_load(f.read_text("utf-8")) or {}) if f.exists() else {}).get("envoi")
    except (OSError, yaml.YAMLError, AttributeError):
        v = None
    return v if v in ENVOIS else "lien"


def regler_envoi(mode: str) -> dict:
    """Règle une fois le mode d'envoi des demandes à Cursor pour tout le projet (rôle automaticien)."""
    import yaml

    from atelier.domain import roles

    roles.exiger("construire")
    if mode not in ENVOIS:
        raise ValueError(f"Mode d'envoi : {', '.join(ENVOIS)}.")
    if mode == "cli":
        _ligne("essai")  # commande absente ou mal réglée sur ce poste : dit avant d'enregistrer
    _fichier_reglage().write_text(yaml.safe_dump({"envoi": mode}, allow_unicode=True), "utf-8")
    return etat()


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _lire() -> list[dict]:
    f = _fichier()
    try:
        return json.loads(f.read_text("utf-8")) if f.exists() else []
    except ValueError:
        return []


def _ecrire(l: list[dict]):
    from atelier.intelligence.strategie import _ecrire_atomique

    _ecrire_atomique(_fichier(), json.dumps(l[-GARDEES:], ensure_ascii=False, indent=1))


def _modifier(did: str, **champs) -> dict:
    with _verrou:
        l = _lire()
        d = next((x for x in l if x["id"] == did), None)
        if not d:
            raise KeyError(f"Demande inconnue : {did}")
        d.update(champs)
        _ecrire(l)
        return d


# =========================================================================== ligne de commande de Cursor
def cli() -> dict:
    """Commande de l'agent Cursor en ligne de commande, telle que réglée sur ce poste, et si elle est installée."""
    commande = os.environ.get("ATELIER_CURSOR_CLI", "").strip()
    candidats = [commande] if commande else ["agent", "cursor-agent"]
    trouvee = next((c for c in candidats if shutil.which(c)), "")
    args = os.environ.get("ATELIER_CURSOR_CLI_ARGS", "").strip() or ARGS_DEFAUT
    return {"commande": trouvee or candidats[0], "trouvee": bool(trouvee), "arguments": args,
            "valide": "{demande}" in args, "delai_s": int(os.environ.get("ATELIER_CURSOR_CLI_DELAI", "900") or 900),
            "mcp_du_projet": (projet.PROJECT_DIR / ".cursor" / "mcp.json").exists()}


def _lanceur_script(executable: str) -> bool:
    """Sous Windows, « agent » est un lanceur .cmd / .ps1 : l'argument passe alors par l'interpréteur de commandes, qui
    réinterprète guillemets, %, & et | (défaut connu du lanceur Windows de Cursor : guillemets retirés, arguments
    recollés). La demande ne doit pas voyager dans un tel argument."""
    return os.name == "nt" and str(executable).lower().endswith((".cmd", ".bat", ".ps1"))


def _par_fichier(did: str, texte: str) -> str:
    """Écrit la demande dans le projet et renvoie une consigne courte, sans caractère spécial, qui dit de la lire."""
    rel = f"studio/demandes_cursor/{did}.md"
    f = projet.safe_path(rel)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(texte, "utf-8")
    return f"Lis le fichier {rel} du projet et execute la demande qu il contient, avec les regles de l atelier."


def _ligne(texte: str, did: str = "") -> list[str]:
    c = cli()
    if not c["trouvee"]:
        raise FileNotFoundError(f"Commande « {c['commande']} » introuvable : installer l'agent Cursor en ligne de commande, ou régler "
                                "ATELIER_CURSOR_CLI sur son chemin.")
    if not c["valide"]:
        raise ValueError("ATELIER_CURSOR_CLI_ARGS doit contenir {demande} (l'endroit où la demande est passée).")
    exe = shutil.which(c["commande"])
    if did and _lanceur_script(exe):  # lanceur Windows : la demande voyage dans un fichier du projet, pas dans l'argument
        texte = _par_fichier(did, texte)
    # liste d'arguments, jamais de shell : sur un exécutable, le texte de la demande ne peut pas devenir une commande
    return [exe, *[a.replace("{demande}", texte) for a in shlex.split(c["arguments"])]]


def _executer_cli(did: str, texte: str, lanceur=None):
    """Lance l'agent sans fenêtre dans le projet de tests (ses règles et son mcp.json) ; garde la fin de sa réponse."""
    from atelier.execution.echecs import masquer_texte

    try:
        ligne = _ligne(texte, did)
        _modifier(did, statut="prise", pris=_maintenant())
        r = (lanceur or subprocess.run)(ligne, cwd=str(projet.PROJECT_DIR), capture_output=True, text=True, encoding="utf-8",
                                        errors="replace", timeout=cli()["delai_s"], stdin=subprocess.DEVNULL)
        sortie = masquer_texte((r.stdout or "").strip()[-4000:], [])
        if r.returncode == 0:
            _modifier(did, statut="terminée", fini=_maintenant(), resultat=sortie)
        else:
            _modifier(did, statut="échouée", fini=_maintenant(), resultat=sortie,
                      erreur=masquer_texte(((r.stderr or "").strip() or f"code de retour {r.returncode}")[-1200:], []))
    except subprocess.TimeoutExpired:
        _modifier(did, statut="échouée", fini=_maintenant(), erreur=f"Aucune fin après {cli()['delai_s']} s : agent arrêté.")
    except Exception as e:  # noqa: BLE001 — l'échec est rapporté sur la demande, jamais perdu dans un fil d'exécution
        _modifier(did, statut="échouée", fini=_maintenant(), erreur=str(e)[:600])


# =========================================================================== dépôt et suivi (atelier)
def deposer(titre: str, texte: str, attendus: list[str] | None = None, ecran: str = "", mode: str = "", lanceur=None,
            attendre: bool = False) -> dict:
    """Dépose une demande selon le mode réglé pour le projet (ou le mode donné). « boite » : Cursor viendra la chercher
    par le MCP. « cli » : l'atelier lance l'agent en ligne de commande tout de suite (en arrière-plan ; attendre=True
    pour les essais). Mode « lien » : rien à déposer, la demande s'ouvre dans le chat de Cursor."""
    texte = str(texte or "").strip()
    if not texte:
        raise ValueError("Demande vide.")
    mode = mode or envoi()
    if mode == "lien":
        raise ValueError("Mode d'envoi « lien » : la demande s'ouvre dans le chat de Cursor, rien n'est déposé.")
    if mode not in MODES:
        raise ValueError("Mode : boite ou cli.")
    if mode == "cli":
        _ligne(texte)  # commande absente ou mal réglée : dit tout de suite, rien n'est déposé
    d = {"id": "DC-" + uuid.uuid4().hex[:8], "titre": " ".join(str(titre or "Demande").split())[:160], "texte": texte[:12000],
         "attendus": [str(a) for a in (attendus or [])][:8], "ecran": str(ecran or "")[:200], "mode": mode,
         "statut": "en attente", "cree": _maintenant()}
    with _verrou:
        l = _lire()
        l.append(d)
        _ecrire(l)
    if mode == "cli":
        fil = threading.Thread(target=_executer_cli, args=(d["id"], texte, lanceur), daemon=True)
        fil.start()
        if attendre:
            fil.join()
            return next(x for x in _lire() if x["id"] == d["id"])
    return d


def annuler(did: str) -> dict:
    d = next((x for x in _lire() if x["id"] == did), None)
    if not d:
        raise KeyError(f"Demande inconnue : {did}")
    if d["statut"] != "en attente":
        raise ValueError(f"Demande déjà {d['statut']} : seule une demande en attente s'annule.")
    return _modifier(did, statut="annulée", fini=_maintenant())


def etat(limite: int = 20) -> dict:
    """Pour l'interface : demandes récentes (les plus récentes d'abord), nombre en attente, dernier passage de l'agent
    à la boîte, et réglage de la ligne de commande."""
    l = _lire()
    return {"demandes": list(reversed(l))[:limite], "en_attente": sum(d["statut"] == "en attente" and d["mode"] == "boite" for d in l),
            "ecoute": _derniere_ecoute(), "cli": cli(), "envoi": envoi(), "envois": ENVOIS}


def _fichier_ecoute():
    return projet.PROJECT_DIR / "studio" / "cursor_ecoute.json"


def _derniere_ecoute() -> dict:
    """L'agent écoute-t-il la boîte ? Vrai s'il est venu la consulter il y a moins de deux minutes."""
    f = _fichier_ecoute()
    try:
        t = json.loads(f.read_text("utf-8"))["t"] if f.exists() else 0
    except (ValueError, KeyError):
        t = 0
    return {"active": bool(t) and time.time() - t < 120, "il_y_a_s": int(time.time() - t) if t else None}


# =========================================================================== côté agent (MCP)
def suivante(attente_s: int = ATTENTE_MAX_S, pause: float = 1.0) -> dict:
    """Prochaine demande en attente de la boîte (la plus ancienne), marquée « prise ». Sans demande, attend jusqu'à
    attente_s secondes (40 au plus) puis rend la main : l'agent rappelle l'outil."""
    limite = time.time() + max(0, min(int(attente_s or 0), ATTENTE_MAX_S))
    while True:
        f = _fichier_ecoute()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"t": time.time()}), "utf-8")
        with _verrou:
            l = _lire()
            d = next((x for x in l if x["statut"] == "en attente" and x["mode"] == "boite"), None)
            if d:
                d.update(statut="prise", pris=_maintenant())
                _ecrire(l)
        if d:
            return {"demande": {k: d[k] for k in ("id", "titre", "texte", "attendus")}, "consigne": CONSIGNE_SUITE,
                    "restantes": sum(x["statut"] == "en attente" and x["mode"] == "boite" for x in l)}
        if time.time() >= limite:
            return {"demande": None, "consigne": CONSIGNE_VIDE}
        time.sleep(pause)


def terminer(did: str, resume: str = "", echec: bool = False) -> dict:
    """L'agent rend compte : demande terminée (ou impossible), avec une phrase de résultat pour l'automaticien."""
    from atelier.execution.echecs import masquer_texte

    d = next((x for x in _lire() if x["id"] == did), None)
    if not d:
        raise KeyError(f"Demande inconnue : {did}")
    if d["statut"] != "prise":
        raise ValueError(f"Demande {d['statut']} : seule une demande prise se termine.")
    d = _modifier(did, statut="échouée" if echec else "terminée", fini=_maintenant(),
                  **{"erreur" if echec else "resultat": masquer_texte(" ".join(str(resume or "").split())[:1200], [])})
    return {"id": did, "statut": d["statut"], "consigne": "Rappelle atelier_demande_suivante() pour attendre la demande suivante."}
