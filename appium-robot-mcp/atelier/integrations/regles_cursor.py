"""Règles Cursor de l'atelier (V2, phase 2) : 11 fichiers structurés, versionnés par projet, synchronisés vers
`.cursor/rules/` sans jamais écraser silencieusement une règle modifiée localement.

- Base livrée avec l'atelier : `regles_cursor/*.mdc` (le contexte du projet y est un gabarit).
- Versions du projet : `<projet>/atelier_regles/versions/v<N>/` + `index.json` (version active, auteur, date,
  commentaire). Toute modification crée une nouvelle version ; restaurer = réactiver une version précédente.
  Ce dossier peut être versionné dans Git avec le projet (aucun chemin local, aucun secret).
- Synchronisation : aperçu fichier par fichier (nouveau, identique, à mettre à jour, modifié localement) ; un fichier
  modifié localement n'est remplacé que s'il est explicitement choisi, avec une sauvegarde `.bak`.
"""
from __future__ import annotations

import difflib
import hashlib
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

from atelier.domain import projet

RUBRIQUES = [  # id, fichier livré, fichier installé, rôle
    ("global", "global.mdc", "atelier-global.mdc", "Principes généraux de l'atelier"),
    ("project-context", "project-context.mdc", "atelier-project-context.mdc", "Contexte du projet sélectionné dans l'atelier"),
    ("security", "security.mdc", "atelier-security.mdc", "Restrictions et validations obligatoires"),
    ("mcp-usage", "mcp-usage.mdc", "atelier-mcp-usage.mdc", "Utilisation des outils MCP"),
    ("discovery", "discovery.mdc", "atelier-discovery.mdc", "Exploration et découverte"),
    ("test-design", "test-design.mdc", "atelier-test-design.mdc", "Conception des scénarios"),
    ("automation", "automatisation.mdc", "atelier-automatisation.mdc", "Conventions de génération Robot Framework"),
    ("execution", "execution.mdc", "atelier-execution.mdc", "Préparation et lancement des tests"),
    ("failure-analysis", "failure-analysis.mdc", "atelier-failure-analysis.mdc", "Diagnostic des échecs"),
    ("coverage", "coverage.mdc", "atelier-coverage.mdc", "Mesure de la couverture"),
    ("knowledge-graph", "knowledge-graph.mdc", "atelier-knowledge-graph.mdc", "Consultation et enrichissement du graphe"),
]
PAR_ID = {r[0]: r for r in RUBRIQUES}


def _base() -> Path:
    return projet.RACINE_OUTIL / "regles_cursor"


def _dossier() -> Path:
    return projet.PROJECT_DIR / "atelier_regles"


def _cursor() -> Path:
    return projet.PROJECT_DIR / ".cursor" / "rules"


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _auteur() -> str:
    from atelier.domain import roles

    return roles.utilisateur()


def _index() -> dict:
    f = _dossier() / "index.json"
    return json.loads(f.read_text("utf-8")) if f.exists() else {"active": 0, "versions": []}


def _ecrire_index(ix: dict):
    from atelier.intelligence.strategie import _ecrire_atomique

    _dossier().mkdir(parents=True, exist_ok=True)
    _ecrire_atomique(_dossier() / "index.json", json.dumps(ix, ensure_ascii=False, indent=1))


def portee(texte: str) -> str:
    """« toujours », « fichiers : … » ou « à la demande », d'après le frontmatter Cursor."""
    tete = texte.split("---", 2)[1] if texte.startswith("---") and texte.count("---") >= 2 else ""
    if "alwaysApply: true" in tete:
        return "toujours"
    g = next((l.split(":", 1)[1].strip().strip('"') for l in tete.splitlines() if l.startswith("globs:")), "")
    return f"fichiers : {g}" if g else "à la demande"


# =========================================================================== contexte du projet
def contexte_projet() -> str:
    """Instructions propres au projet, calculées depuis l'atelier (aucun chemin local, aucun secret)."""
    l = []
    try:
        from atelier.domain import projets

        p = projets.actif() or {}
        if p:
            l.append(f"- Projet de tests : {p.get('nom', '')}" + (f" ; projet Xray / Jira : {p['xray_projet']}" if p.get("xray_projet") else ""))
    except Exception:  # noqa: BLE001 — sans registre de projets
        pass
    try:
        from atelier.discovery import carte

        a = carte.config_app()
        if a.get("nom"):
            l.append(f"- Application active : {a['nom']} ; plateformes : {', '.join(a.get('plateformes') or []) or 'non précisées'}")
        mods = sorted({e.get("module") for e in carte.ecrans() if e.get("module")})
        if mods:
            l.append(f"- Modules connus dans la carte : {', '.join(mods)}")
    except Exception:  # noqa: BLE001 — aucune carte
        pass
    try:
        from atelier.execution import jdd

        envs = jdd.environnements()
        if envs:
            l.append(f"- Environnements de données (JDD) : {', '.join(envs)} ; jamais la production.")
    except Exception:  # noqa: BLE001
        pass
    try:
        from atelier.generation import rangement

        r = rangement.regles()
        l.append(f"- Rangement des tests générés : dépôt Robot « {r.get('robot', '')} », dossier Xray « {r.get('xray', '')} ».")
    except Exception:  # noqa: BLE001
        pass
    l.append(f"- Instructions générées par l'atelier le {_maintenant()[:10]} ; régénérer depuis Paramètres › Cursor / Claude.")
    return "\n".join(l)


def _texte_base(rid: str) -> str:
    t = (_base() / PAR_ID[rid][1]).read_text("utf-8")
    return t.replace("{{CONTEXTE_PROJET}}", contexte_projet()) if rid == "project-context" else t


# =========================================================================== versions
def _creer_version(contenus: dict, commentaire: str, origine: str) -> dict:
    ix = _index()
    n = max([v["n"] for v in ix["versions"]] or [0]) + 1
    d = _dossier() / "versions" / f"v{n}"
    d.mkdir(parents=True, exist_ok=True)
    for rid, t in contenus.items():
        (d / PAR_ID[rid][1]).write_text(t, "utf-8")
    ix["versions"].append({"n": n, "date": _maintenant(), "auteur": _auteur(), "commentaire": commentaire.strip(), "origine": origine})
    ix["active"] = n
    _ecrire_index(ix)
    return ix


def _assurer() -> dict:
    ix = _index()
    if not ix["versions"]:
        ix = _creer_version({r[0]: _texte_base(r[0]) for r in RUBRIQUES}, "Règles de base de l'atelier", "base")
    return ix


def contenu(rid: str, n: int | None = None) -> str:
    if rid not in PAR_ID:
        raise KeyError(f"Règle inconnue : {rid} ({', '.join(PAR_ID)})")
    ix = _assurer()
    n = int(n or ix["active"])
    f = _dossier() / "versions" / f"v{n}" / PAR_ID[rid][1]
    if not f.exists():
        raise KeyError(f"Version {n} inconnue.")
    return f.read_text("utf-8")


def _contenus(n: int) -> dict:
    return {r[0]: contenu(r[0], n) for r in RUBRIQUES}


def enregistrer(rid: str, texte: str, commentaire: str) -> dict:
    """Modifie une règle : nouvelle version (copie de l'active + ce changement), activée ; frontmatter obligatoire."""
    from atelier.domain import roles

    roles.exiger("construire")
    if rid not in PAR_ID:
        raise KeyError(f"Règle inconnue : {rid}")
    if not texte.startswith("---") or texte.count("---") < 2 or "description:" not in texte.split("---", 2)[1]:
        raise ValueError("Frontmatter Cursor obligatoire en tête (--- description: … alwaysApply: … ---).")
    if len(commentaire.strip()) < 5:
        raise ValueError("Commentaire de version obligatoire (5 caractères minimum).")
    ix = _assurer()
    c = _contenus(ix["active"])
    if c[rid] == texte:
        raise ValueError("Aucun changement par rapport à la version active.")
    c[rid] = texte
    _creer_version(c, commentaire, f"modification de {rid}")
    return etat()


def regenerer_contexte(commentaire: str = "") -> dict:
    """Nouvelle version avec le contexte du projet recalculé (projet, application, modules, environnements)."""
    ix = _assurer()
    c = _contenus(ix["active"])
    nouveau = _texte_base("project-context")
    if c["project-context"].split("- Instructions générées")[0] == nouveau.split("- Instructions générées")[0]:
        return {**etat(), "inchange": True}
    c["project-context"] = nouveau
    _creer_version(c, commentaire or "Contexte du projet régénéré", "contexte")
    return etat()


def activer(n: int, commentaire: str = "") -> dict:
    """Active (restaure) une version existante ; journalisé dans l'index."""
    from atelier.domain import roles

    roles.exiger("construire")
    ix = _assurer()
    if not any(v["n"] == int(n) for v in ix["versions"]):
        raise KeyError(f"Version {n} inconnue.")
    ix["active"] = int(n)
    ix.setdefault("journal", []).append({"date": _maintenant(), "auteur": _auteur(), "action": f"activation de v{n}", "commentaire": commentaire.strip()})
    _ecrire_index(ix)
    return etat()


def comparer(a: int, b: int) -> list[dict]:
    ca, cb = _contenus(int(a)), _contenus(int(b))
    out = []
    for rid, _, cible, _ in RUBRIQUES:
        if ca[rid] != cb[rid]:
            out.append({"id": rid, "fichier": cible, "diff": "".join(difflib.unified_diff(
                ca[rid].splitlines(True), cb[rid].splitlines(True), f"v{a}/{cible}", f"v{b}/{cible}"))})
    return out


# =========================================================================== synchronisation vers .cursor/rules
def apercu() -> list[dict]:
    """Pour chaque règle active : état du fichier installé dans le projet et différence."""
    ix = _assurer()
    connus = {r[0]: {contenu(r[0], v["n"]) for v in ix["versions"]} | {_texte_base(r[0])} for r in RUBRIQUES}
    try:  # règles livrées par les versions précédentes de l'atelier (migration V1 → V2)
        anciennes = json.loads((_base() / "anciennes_versions.json").read_text("utf-8"))["empreintes"]
    except (OSError, ValueError, KeyError):
        anciennes = {}
    out = []
    for rid, _, cible, role in RUBRIQUES:
        voulu, f = contenu(rid), _cursor() / cible
        local = f.read_text("utf-8") if f.exists() else None
        if local is None:
            statut = "nouveau"
        elif local == voulu:
            statut = "identique"
        elif local in connus[rid] or hashlib.sha256(local.encode("utf-8")).hexdigest() in anciennes.get(rid, []):
            statut = "à mettre à jour"  # ancienne version de l'atelier, non modifiée localement
        else:
            statut = "modifié localement"
        out.append({"id": rid, "fichier": cible, "role": role, "portee": portee(voulu), "statut": statut,
                    "diff": "" if statut in ("identique", "nouveau") else "".join(difflib.unified_diff(
                        (local or "").splitlines(True), voulu.splitlines(True), f"local/{cible}", f"v{ix['active']}/{cible}"))})
    return out


def synchroniser(remplacer: list[str] | None = None) -> dict:
    """Écrit la version active dans .cursor/rules/ : nouveaux et à mettre à jour automatiquement ; un fichier
    « modifié localement » seulement s'il figure dans remplacer (sauvegarde .bak). Jamais d'écrasement silencieux."""
    remplacer = set(remplacer or [])
    dossier = projet.safe_path(".cursor/rules")
    dossier.mkdir(parents=True, exist_ok=True)
    out = {"copiees": [], "identiques": [], "ignorees": [], "sauvegardes": []}
    for x in apercu():
        f = dossier / x["fichier"]
        if x["statut"] == "identique":
            out["identiques"].append(x["fichier"])
            continue
        if x["statut"] == "modifié localement":
            if x["id"] not in remplacer and x["fichier"] not in remplacer:
                out["ignorees"].append(x["fichier"])
                continue
            bak = f.with_suffix(f.suffix + ".bak")
            bak.write_bytes(f.read_bytes())
            out["sauvegardes"].append(bak.name)
        f.write_text(contenu(x["id"]), "utf-8")
        out["copiees"].append(x["fichier"])
    ix = _index()
    ix.setdefault("journal", []).append({"date": _maintenant(), "auteur": _auteur(), "action": f"synchronisation de v{ix['active']}",
                                         "commentaire": f"{len(out['copiees'])} copiée(s), {len(out['ignorees'])} ignorée(s)"})
    _ecrire_index(ix)
    return out


def exporter_zip(config_mcp: dict | None = None) -> bytes:
    """Archive prête pour Cursor : .cursor/rules/*.mdc de la version active (+ exemple de configuration MCP, sans secret)."""
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for rid, _, cible, _ in RUBRIQUES:
            z.writestr(f".cursor/rules/{cible}", contenu(rid))
        if config_mcp:
            z.writestr("mcp.json.exemple", json.dumps(config_mcp, ensure_ascii=False, indent=2))
        z.writestr("LISEZMOI.txt", "Règles Cursor de l'atelier d'automatisation : copier .cursor/rules/ à la racine du projet de tests.\n"
                                   "mcp.json.exemple : entrée « appium-robot » à fusionner dans ~/.cursor/mcp.json (aucun secret).\n")
    return b.getvalue()


def etat() -> dict:
    ix = _assurer()
    ap = {x["id"]: x for x in apercu()}
    return {"active": ix["active"], "versions": list(reversed(ix["versions"])), "journal": list(reversed(ix.get("journal", [])))[:20],
            "regles": [{"id": rid, "fichier": cible, "role": role, "portee": ap[rid]["portee"], "statut": ap[rid]["statut"]}
                       for rid, _, cible, role in RUBRIQUES]}


def actives() -> list[dict]:
    """Instructions actives du projet (outil MCP cursor_regles)."""
    ix = _assurer()
    return [{"id": rid, "fichier": cible, "role": role, "portee": portee(contenu(rid)), "version": ix["active"], "contenu": contenu(rid)}
            for rid, _, cible, role in RUBRIQUES]
