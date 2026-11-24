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

from atelier.domain.yaml_rapide import charger as charger_yaml

import json
import os
import re
import shlex
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from atelier.domain import projet

STATUTS = ("en attente", "prise", "terminée", "échouée", "annulée")
MODES = ("boite", "cli")
ENVOIS = {"lien": "Ouvrir le chat de Cursor avec la demande (à relire et envoyer)",
          "boite": "Boîte de demandes : l'agent vient la chercher (lui dire une fois « traite les demandes de l'atelier »)",
          "cli": "Ligne de commande : l'atelier lance l'agent sans fenêtre, dès l'envoi (recommandé)"}
AGENTS = {"cursor": "Cursor", "claude_code": "Claude Code"}  # agent qui traite les demandes de l'atelier (par le MCP)
ENVOIS_CURSOR_SEUL = ("lien",)  # lien profond : propre à Cursor ; la ligne de commande vaut pour Cursor (agent) et Claude Code (claude -p)
# Claude Code sans fenêtre : le MCP de l'atelier déclaré dans .mcp.json du projet de tests, et ses seuls outils autorisés
# (pas de commande du poste, pas d'écriture hors des outils de l'atelier).
ARGS_CLAUDE = "-p {demande} --output-format text --mcp-config .mcp.json --allowedTools mcp__appium-robot"
PHRASE_ECOUTE = "Traite les demandes de l'atelier"
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

    v = _reglages().get("envoi")
    return v if v in ENVOIS else "lien"


def agent() -> str:
    """Agent de l'atelier pour le projet : « cursor » (défaut, historique) ou « claude_code »."""
    v = _reglages().get("agent")
    return v if v in AGENTS else "cursor"


def nom_agent() -> str:
    return AGENTS[agent()]


def regler_agent(a: str) -> dict:
    """Change l'agent qui traite les demandes de l'atelier (rôle automaticien). Claude Code n'a pas de lien profond : ses
    demandes partent en ligne de commande (claude -p) si elle est installée sur le poste, sinon par la boîte."""
    from atelier.domain import roles

    roles.exiger("construire")
    if a not in AGENTS:
        raise ValueError(f"Agent : {', '.join(AGENTS)}.")
    _ecrire_reglages(agent=a)
    if a != "cursor" and envoi() in ENVOIS_CURSOR_SEUL:
        c = cli()
        _ecrire_reglages(envoi="cli" if c["trouvee"] and c.get("connecte", True) else "boite")
    return etat()


def _reglages() -> dict:
    """Réglages Cursor du projet (atelier_cursor.yaml) : mode d'envoi et fournisseur d'IA ; {} si absent ou illisible."""
    import yaml

    f = _fichier_reglage()
    try:
        d = (charger_yaml(f.read_text("utf-8")) or {}) if f.exists() else {}
    except (OSError, yaml.YAMLError):
        d = {}
    return d if isinstance(d, dict) else {}


def _ecrire_reglages(**champs) -> None:
    import yaml

    _fichier_reglage().write_text(yaml.safe_dump({**_reglages(), **champs}, allow_unicode=True, sort_keys=True), "utf-8")


def regler_ia(cursor: bool) -> dict:
    """Cursor est (ou n'est plus) l'IA de l'atelier pour ce projet : c'est ce qui affiche les boutons « Demander à
    Cursor ». Refusé quand l'entreprise impose un fournisseur par la variable IA_FOURNISSEUR."""
    from atelier.domain import roles
    from atelier.intelligence import fournisseur_ia

    roles.exiger("construire")
    if fournisseur_ia.impose():
        raise ValueError(f"Le fournisseur d'IA est imposé par la variable IA_FOURNISSEUR (« {fournisseur_ia.impose()} ») : il ne se change pas ici.")
    _ecrire_reglages(ia="cursor" if cursor else "aucun")
    return etat()


def regler_force(force: bool) -> dict:
    """Ajoute (ou retire) l'option --force de la ligne de commande de Cursor pour ce projet. Constat du 2026-11-19 : sans
    fenêtre, l'agent refuse les outils de l'atelier malgré l'autorisation ciblée de .cursor/cli.json ; seul --force les
    laisse passer. Il autorise AUSSI les commandes du poste et l'écriture de fichiers par l'agent : choix explicite de
    l'automaticien, jamais activé par défaut."""
    from atelier.domain import roles

    roles.exiger("construire")
    _ecrire_reglages(cli_force=bool(force))
    return etat()


def regler_envoi(mode: str) -> dict:
    """Règle une fois le mode d'envoi des demandes à Cursor pour tout le projet (rôle automaticien)."""
    import yaml

    from atelier.domain import roles

    roles.exiger("construire")
    if mode not in ENVOIS:
        raise ValueError(f"Mode d'envoi : {', '.join(ENVOIS)}.")
    if mode in ENVOIS_CURSOR_SEUL and agent() != "cursor":
        raise ValueError(f"Ce mode d'envoi est propre à Cursor : avec {nom_agent()}, choisir la ligne de commande ou la boîte de demandes.")
    if mode == "cli":
        _ligne("essai")  # commande absente ou mal réglée sur ce poste : dit avant d'enregistrer
    _ecrire_reglages(envoi=mode)
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
def _candidats_claude() -> list[str]:
    """Où trouver Claude Code en ligne de commande : ATELIER_CLAUDE_CLI, sinon « claude » dans le PATH, sinon les dossiers
    d'installation habituels (installateur officiel, npm) : l'atelier lancé hors d'un terminal n'a pas toujours le PATH."""
    commande = os.environ.get("ATELIER_CLAUDE_CLI", "").strip()
    if commande:
        return [commande]
    exe = "claude.exe" if os.name == "nt" else "claude"
    return ["claude", str(Path.home() / ".local" / "bin" / exe), str(Path(os.environ.get("APPDATA") or Path.home()) / "npm" / "claude.cmd"),
            str(Path.home() / ".claude" / "local" / exe)]


def _claude_connecte() -> bool:
    """Claude Code est-il connecté à un compte sur ce poste (connexion faite une fois avec « claude ») ou à une clé d'API ?
    Sans connexion, claude -p répond « Not logged in » : la demande reste alors dans la boîte."""
    return bool(os.environ.get("ANTHROPIC_API_KEY")) or (Path.home() / ".claude" / ".credentials.json").exists()


def _cli_claude() -> dict:
    candidats = _candidats_claude()
    trouvee = next((c for c in candidats if shutil.which(c)), "")
    args = os.environ.get("ATELIER_CLAUDE_CLI_ARGS", "").strip() or ARGS_CLAUDE
    accordee = "mcp__appium-robot" in args or "mcp__" + SERVEUR_MCP in args
    return {"agent": "claude_code", "commande": trouvee or candidats[0], "trouvee": bool(trouvee), "arguments": args, "force": False,
            "valide": "{demande}" in args, "delai_s": int(os.environ.get("ATELIER_CURSOR_CLI_DELAI", "900") or 900),
            "mcp_du_projet": (projet.PROJECT_DIR / ".mcp.json").exists(),
            "permissions": {"fichier": "arguments (--allowedTools)", "jeton": "mcp__" + SERVEUR_MCP, "accordee": accordee, "erreur": ""},
            "connecte": _claude_connecte(),
            "installer": "npm install -g @anthropic-ai/claude-code, puis « claude » une fois dans un terminal pour se connecter"}


def cli() -> dict:
    """Commande de l'agent en ligne de commande (Cursor : agent ; Claude Code : claude -p), telle que réglée sur ce poste,
    et si elle est installée."""
    if agent() == "claude_code":
        return _cli_claude()
    commande = os.environ.get("ATELIER_CURSOR_CLI", "").strip()
    candidats = [commande] if commande else ["agent", "cursor-agent"]
    trouvee = next((c for c in candidats if shutil.which(c)), "")
    args = os.environ.get("ATELIER_CURSOR_CLI_ARGS", "").strip() or ARGS_DEFAUT
    force = _reglages().get("cli_force") is True
    if force and "--force" not in shlex.split(args):
        args += " --force"
    return {"agent": "cursor", "commande": trouvee or candidats[0], "trouvee": bool(trouvee), "arguments": args, "force": force,
            "valide": "{demande}" in args, "delai_s": int(os.environ.get("ATELIER_CURSOR_CLI_DELAI", "900") or 900),
            "mcp_du_projet": (projet.PROJECT_DIR / ".cursor" / "mcp.json").exists(), "permissions": permissions_cli(),
            "installer": "Cursor › Paramètres › installer l'agent en ligne de commande (agent), ou ATELIER_CURSOR_CLI"}


# --------------------------------------------------------------------------- ce que l'agent a le droit d'appeler
# Sans fenêtre, personne ne peut approuver un appel d'outil : l'agent en ligne de commande refuse alors chaque outil de
# l'atelier (« refusé »), même serveur MCP chargé. Deux conditions, toutes deux vérifiables ici :
#   1. le serveur MCP est approuvé pour la ligne de commande (« agent mcp enable appium-robot », une fois par poste) ;
#   2. les outils de l'atelier sont autorisés dans .cursor/cli.json du projet de tests (jeton Mcp(appium-robot:*)).
# Seuls les outils de l'atelier sont autorisés : ni commande du poste, ni écriture de fichier (pas de --force).
SERVEUR_MCP = "appium-robot"
JETON_MCP = f"Mcp({SERVEUR_MCP}:*)"


def _fichier_permissions():
    return projet.PROJECT_DIR / ".cursor" / "cli.json"


def permissions_cli() -> dict:
    """Les outils de l'atelier sont-ils autorisés pour l'agent en ligne de commande, dans ce projet de tests ?"""
    f, erreur, permises = _fichier_permissions(), "", []
    if f.exists():
        try:
            permises = list(((json.loads(f.read_text("utf-8")) or {}).get("permissions") or {}).get("allow") or [])
        except (ValueError, OSError, AttributeError) as e:
            erreur = f"fichier illisible : {e}"[:200]
    accordee = any(p in (JETON_MCP, f"Mcp({SERVEUR_MCP}:*)", "Mcp(*:*)") for p in permises)
    return {"fichier": ".cursor/cli.json", "jeton": JETON_MCP, "accordee": accordee, "erreur": erreur}


def autoriser_outils_cli() -> dict:
    """Ajoute le jeton des outils de l'atelier à .cursor/cli.json du projet ; les autres permissions sont conservées."""
    f = _fichier_permissions()
    conf = {}
    if f.exists():
        try:
            conf = json.loads(f.read_text("utf-8")) or {}
        except ValueError as e:
            raise ValueError(f".cursor/cli.json illisible ({e}) : le corriger à la main, rien n'a été modifié.") from e
        if not isinstance(conf, dict):
            raise ValueError(".cursor/cli.json n'est pas un objet JSON : le corriger à la main, rien n'a été modifié.")
    perms = conf.setdefault("permissions", {})
    perms.setdefault("allow", [])
    perms.setdefault("deny", [])
    if JETON_MCP not in perms["allow"]:
        perms["allow"].append(JETON_MCP)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(conf, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return permissions_cli()


def verifier_cli(lanceur=None) -> dict:
    """Demande à l'agent en ligne de commande l'état de ses serveurs MCP (« agent mcp list », dans le projet de tests) :
    dit si celui de l'atelier est chargé, à approuver, ou inconnu, avec la commande à taper le cas échéant."""
    c = cli()
    r = {"commande": c["commande"], "trouvee": c["trouvee"], "serveur": "inconnu", "detail": "", "a_faire": "",
         "permissions": c["permissions"]}
    if not c["trouvee"]:
        r["a_faire"] = f"Installer {nom_agent()} en ligne de commande : {c['installer']}."
        return r
    exe = shutil.which(c["commande"])
    nom = Path(exe).name
    try:
        p = (lanceur or subprocess.run)([exe, "mcp", "list"], cwd=str(projet.PROJECT_DIR), capture_output=True, text=True,
                                        encoding="utf-8", errors="replace", timeout=60, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        r["detail"] = "aucune réponse après 60 s"
        r["a_faire"] = f"Dans un terminal : {nom} login, puis {nom} mcp list."
        return r
    except OSError as e:
        r["detail"] = str(e)[:300]
        return r
    sortie = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", f"{p.stdout or ''}\n{p.stderr or ''}")
    ligne = next((l.strip() for l in sortie.splitlines() if l.strip().lower().startswith(SERVEUR_MCP + ":")), "")
    r["detail"] = (ligne or sortie.strip())[-300:]
    etat_ = ligne.split(":", 1)[1].strip().lower() if ligne else ""
    if not ligne:
        r["serveur"] = "absent"
        r["a_faire"] = "Étape 1 : installer le MCP dans Cursor, puis vérifier à nouveau."
    elif "approval" in etat_:
        r["serveur"] = "a_approuver"
        r["a_faire"] = f"Dans un terminal, une fois : {nom} mcp enable {SERVEUR_MCP}"
    elif etat_.startswith(("ready", "loaded", "connected")) or "connected" in etat_ or "✓" in etat_:
        r["serveur"] = "charge"
    else:
        r["serveur"] = "en_erreur"
        r["a_faire"] = "Vérifier que l'atelier est lancé (serveur MCP démarré, étape 1), puis vérifier à nouveau."
    if r["serveur"] == "charge" and not c["permissions"]["accordee"] and not c["force"]:
        r["a_faire"] = "Serveur chargé, mais ses outils ne sont pas autorisés sans fenêtre : « Autoriser les outils de l'atelier »."
    return r


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
        raise FileNotFoundError(f"{nom_agent()} en ligne de commande introuvable sur ce poste (« {c['commande']} ») : {c['installer']}.")
    if not c["valide"]:
        raise ValueError("Les arguments de la ligne de commande doivent contenir {demande} (l'endroit où la demande est passée).")
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
            attendre: bool = False, prioritaire: bool = False, agent: str = "", travail: str = "") -> dict:
    """Dépose une demande selon le mode réglé pour le projet (ou le mode donné). « boite » : Cursor viendra la chercher
    par le MCP. « cli » : l'atelier lance l'agent en ligne de commande tout de suite (en arrière-plan ; attendre=True
    pour les essais). Mode « lien » : rien à déposer, la demande s'ouvre dans le chat de Cursor."""
    texte = str(texte or "").strip()
    if not texte:
        raise ValueError("Demande vide.")
    regle = not mode
    mode = mode or envoi()
    if regle and mode == "boite" and not _derniere_ecoute()["active"]:
        c = cli()
        if c["trouvee"] and c["valide"] and c.get("connecte", True):  # sinon la demande attendrait un agent qui ne vient pas
            mode = "cli"
    if mode == "lien":
        raise ValueError("Mode d'envoi « lien » : la demande s'ouvre dans le chat de Cursor, rien n'est déposé.")
    if mode not in MODES:
        raise ValueError("Mode : boite ou cli.")
    if mode == "cli" and not cli().get("connecte", True):  # Claude Code pas encore connecté : la demande attend dans la boîte
        mode = "boite"
    if mode == "cli":
        _ligne(texte)  # commande absente ou mal réglée : dit tout de suite, rien n'est déposé
    did = uuid.uuid4().hex[:8]
    while did.isdigit():  # un identifiant tout en chiffres serait masqué comme un numéro dans le compte rendu de l'agent
        did = uuid.uuid4().hex[:8]
    d = {"id": "DC-" + did, "titre": " ".join(str(titre or "Demande").split())[:160], "texte": texte[:12000],
         "attendus": [str(a) for a in (attendus or [])][:8], "ecran": str(ecran or "")[:200], "mode": mode,
         "statut": "en attente", "cree": _maintenant(), **({"prioritaire": True} if prioritaire else {}),
         **({"agent": agent} if agent in ("claude_code", "cursor") else {}), **({"travail": travail} if travail else {})}
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


def _ligne_prete() -> bool:
    c = cli()
    return c["trouvee"] and c["valide"] and c.get("connecte", True)


def relancer(did: str, lanceur=None) -> bool:
    """Une demande restée dans la boîte part en ligne de commande dès que l'agent y est prêt (installé, connecté) et que
    personne n'écoute la boîte. Rend True si elle est partie."""
    d = next((x for x in _lire() if x["id"] == did), None)
    if not d or d["statut"] != "en attente" or d.get("mode") != "boite" or _derniere_ecoute()["active"] or not _ligne_prete():
        return False
    _modifier(did, mode="cli")
    threading.Thread(target=_executer_cli, args=(did, d["texte"], lanceur), daemon=True).start()
    return True


def relancer_en_attente(lanceur=None) -> list[str]:
    """Au démarrage de l'atelier (ou quand l'agent devient prêt) : toutes les demandes en attente partent à l'agent."""
    return [d["id"] for d in _lire() if d["statut"] == "en attente" and relancer(d["id"], lanceur)]


def annuler(did: str) -> dict:
    d = next((x for x in _lire() if x["id"] == did), None)
    if not d:
        raise KeyError(f"Demande inconnue : {did}")
    if d["statut"] != "en attente":
        raise ValueError(f"Demande déjà {d['statut']} : seule une demande en attente s'annule.")
    return _modifier(did, statut="annulée", fini=_maintenant())


def pret() -> dict:
    """Une demande déposée maintenant sera-t-elle traitée ? Oui si l'agent est lancé en ligne de commande (installé et
    connecté) ou s'il écoute la boîte ; sinon la raison et ce qu'il faut faire, pour ne jamais laisser croire qu'il travaille."""
    nom, ecoute = nom_agent(), _derniere_ecoute()
    if ecoute["active"]:
        return {"pret": True, "comment": f"{nom} écoute la boîte de demandes", "raison": "", "a_faire": ""}
    c = cli()
    if c["trouvee"] and c["valide"] and c.get("connecte", True) and envoi() != "lien":
        return {"pret": True, "comment": f"{nom} est lancé en ligne de commande à chaque demande", "raison": "", "a_faire": ""}
    phrase = f"ou dire une fois à {nom} dans son chat : « {PHRASE_ECOUTE} »"
    if agent() == "claude_code" and c["trouvee"] and not c.get("connecte", True):
        return {"pret": False, "comment": "", "raison": "Claude Code n'est pas connecté sur ce poste",
                "a_faire": f"dans un terminal : claude, puis /login ; {phrase}"}
    if not c["trouvee"]:
        return {"pret": False, "comment": "", "raison": f"{nom} n'est pas installé en ligne de commande et n'écoute pas la boîte",
                "a_faire": f"{c['installer']} ; {phrase}"}
    return {"pret": False, "comment": "", "raison": f"{nom} n'écoute pas la boîte de demandes", "a_faire": phrase[3:]}


def etat(limite: int = 20) -> dict:
    """Pour l'interface : demandes récentes (les plus récentes d'abord), nombre en attente, dernier passage de l'agent
    à la boîte, et réglage de la ligne de commande."""
    l = _lire()
    return {"demandes": list(reversed(l))[:limite], "en_attente": sum(d["statut"] == "en attente" and d["mode"] == "boite" for d in l),
            "ecoute": _derniere_ecoute(), "cli": cli(), "envoi": envoi(), "envois": ENVOIS, "ia": _fournisseur_ia(),
            "agent": agent(), "agent_nom": nom_agent(), "agents": AGENTS, "envois_cursor_seul": list(ENVOIS_CURSOR_SEUL)}


def _fournisseur_ia() -> dict:
    """Les boutons « Demander à Cursor » ne s'affichent que si l'atelier est lancé avec IA_FOURNISSEUR=cursor : le dire
    dans les paramètres évite de chercher des boutons absents."""
    from atelier.intelligence import fournisseur_ia

    f, impose, nom = fournisseur_ia.fournisseur(), fournisseur_ia.impose(), nom_agent()
    return {"fournisseur": f, "boutons_cursor": f == "cursor", "impose": impose,
            "aide": "" if f == "cursor" else (f"Les boutons « Demander à {nom} » sont masqués : la variable IA_FOURNISSEUR impose « {impose} »." if impose
                                              else f"Les boutons « Demander à {nom} » sont masqués : cocher « {nom} est l'IA de l'atelier », puis Valider.")}


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
    """Prochaine demande en attente de la boîte, marquée « prise » : une demande prioritaire (lancée d'un clic par
    l'automaticien, ex. « Que faire ici ? » du graphe) d'abord, sinon la plus ancienne. Sans demande, attend jusqu'à
    attente_s secondes (40 au plus) puis rend la main : l'agent rappelle l'outil."""
    limite = time.time() + max(0, min(int(attente_s or 0), ATTENTE_MAX_S))
    from atelier.domain import agent_mcp

    appelant = agent_mcp.cle() if agent_mcp._courant.get() else ""  # agent MCP qui appelle (vide : hors MCP, tout est servi)
    while True:
        f = _fichier_ecoute()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"t": time.time()}), "utf-8")
        with _verrou:
            l = _lire()
            # une demande destinée à un agent (étape d'un travail : Claude Code ou Cursor) n'est servie qu'à lui
            attente = [x for x in l if x["statut"] == "en attente" and x["mode"] == "boite"
                       and (not x.get("agent") or not appelant or x["agent"] == appelant)]
            d = next((x for x in attente if x.get("prioritaire")), attente[0] if attente else None)
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
