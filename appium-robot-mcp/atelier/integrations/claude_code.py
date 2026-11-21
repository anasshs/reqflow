"""Claude Code dans le projet de tests : les mêmes règles que Cursor, au format de Claude Code.

Claude Code ne lit pas .cursor/rules. Il lit CLAUDE.md (instructions toujours chargées, qui peuvent importer d'autres
fichiers par « @chemin ») et des skills (.claude/skills/<nom>/SKILL.md, chargés quand leur description correspond à la
tâche). La version active des règles du projet (regles_cursor) est donc écrite ainsi :
- règles « toujours » (sécurité, principes, usage du MCP, contexte du projet) : .claude/atelier/<règle>.md, importées
  par un bloc de CLAUDE.md délimité par des marques (le reste de CLAUDE.md, s'il existe, n'est jamais touché) ;
- règles à la demande (automatisation, robot-expert, discovery, test design…) : un skill chacune.
Un fichier modifié à la main depuis la dernière installation n'est remplacé qu'avec accord (sauvegarde .bak).
La configuration MCP de Claude Code pour ce projet est .mcp.json, à la racine du projet (agents_ia).
"""
from __future__ import annotations

import hashlib
import json
import re

from atelier.domain import projet

DEBUT = "<!-- atelier : début (bloc généré par l'atelier, ne pas modifier entre ces marques) -->"
FIN = "<!-- atelier : fin -->"
_EMPREINTES = ".claude/atelier/.empreintes.json"


def _frontmatter(texte: str) -> tuple[dict, str]:
    if texte.startswith("---") and texte.count("---") >= 2:
        _, tete, corps = texte.split("---", 2)
        meta = {}
        for l in tete.splitlines():
            if ":" in l:
                k, v = l.split(":", 1)
                meta[k.strip()] = v.strip().strip('"')
        return meta, corps.lstrip("\n")
    return {}, texte


def fichiers() -> dict[str, str]:
    """{chemin relatif au projet : contenu} pour la version active des règles."""
    from atelier.integrations import regles_cursor as rc

    out, imports = {}, []
    for rid, _, _, role in rc.RUBRIQUES:
        meta, corps = _frontmatter(rc.contenu(rid))
        if meta.get("alwaysApply") == "true":
            chemin = f".claude/atelier/{rid}.md"
            out[chemin] = f"# {role}\n\n{corps}"
            imports.append(chemin)
        else:
            desc = re.sub(r"\s+", " ", f"{meta.get('description') or role}. {role}.").replace(":", " —")
            out[f".claude/skills/atelier-{rid}/SKILL.md"] = f"---\nname: atelier-{rid}\ndescription: {desc}\n---\n\n{corps}"
    out["CLAUDE.md"] = "\n".join([DEBUT, "# Atelier d'automatisation : règles du projet de tests",
                                  "Règles toujours appliquées (les autres sont des skills .claude/skills/atelier-*) :",
                                  *[f"@{c}" for c in imports], FIN]) + "\n"
    return out


def _empreinte(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def _bloc_claude_md(existant: str, bloc: str) -> str:
    if DEBUT in existant and FIN in existant:
        avant, reste = existant.split(DEBUT, 1)
        return avant + bloc.rstrip("\n") + reste.split(FIN, 1)[1]
    return (existant.rstrip() + "\n\n" if existant.strip() else "") + bloc


def apercu() -> list[dict]:
    """État de chaque fichier : nouveau, identique, à mettre à jour (non modifié depuis l'installation), modifié localement."""
    try:
        emp = json.loads(projet.safe_path(_EMPREINTES).read_text("utf-8"))
    except (OSError, ValueError):
        emp = {}
    out = []
    for rel, voulu in fichiers().items():
        f = projet.safe_path(rel)
        local = f.read_text("utf-8") if f.exists() else None
        if rel == "CLAUDE.md":
            voulu = _bloc_claude_md(local or "", voulu)
        statut = ("nouveau" if local is None else "identique" if local == voulu
                  else "à mettre à jour" if rel == "CLAUDE.md" or emp.get(rel) == _empreinte(local) else "modifié localement")
        out.append({"fichier": rel, "statut": statut, "contenu": voulu})
    return out


def installer(ecraser: bool = False) -> dict:
    """Écrit les règles pour Claude Code dans le projet de tests ; jamais d'écrasement silencieux d'un fichier modifié."""
    r = {"copiees": [], "identiques": [], "ignorees": [], "sauvegardes": []}
    try:
        emp = json.loads(projet.safe_path(_EMPREINTES).read_text("utf-8"))
    except (OSError, ValueError):
        emp = {}
    for x in apercu():
        f = projet.safe_path(x["fichier"])
        if x["statut"] == "identique":
            r["identiques"].append(x["fichier"])
            continue
        if x["statut"] == "modifié localement":
            if not ecraser:
                r["ignorees"].append(x["fichier"])
                continue
            bak = f.with_name(f.name + ".bak")
            bak.write_bytes(f.read_bytes())
            r["sauvegardes"].append(str(bak.relative_to(projet.PROJECT_DIR)))
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(x["contenu"], "utf-8")
        emp[x["fichier"]] = _empreinte(x["contenu"])
        r["copiees"].append(x["fichier"])
    e = projet.safe_path(_EMPREINTES)
    e.parent.mkdir(parents=True, exist_ok=True)
    e.write_text(json.dumps(emp, indent=1), "utf-8")
    return r
