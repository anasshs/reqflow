"""
Jeux de données (JDD) des tests auto.

Fichiers dans le projet de tests (ROBOT_PROJECT_DIR) :
  data/jdd/<env>.yaml       jeux nommés (ex. VIREMENT_STANDARD) : données + prérequis
  data/jdd/requetes.yaml    requêtes SQL autorisées (liste blanche, lecture seule)

Dans les valeurs d'un jeu :
  {{env:NOM_VARIABLE}}             secret lu dans l'environnement (jamais écrit dans le dépôt)
  {{requete:NOM.colonne}}          1re ligne d'une requête déclarée dans les prérequis du jeu

Connexion Oracle par environnement (SID ou SERVICE_NAME) : voir atelier/integrations/oracle.
Garde-fous : liste blanche, SELECT uniquement, paramètres liés, lignes et durée plafonnées,
rollback systématique (le compte doit en plus être en lecture seule côté base).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from atelier.domain import projet
from atelier.integrations import oracle

TOKEN_RE = re.compile(r"\{\{\s*(env|requete)\s*:\s*([^}]+?)\s*\}\}")
SECRET_RE = re.compile(r"\{\{\s*env\s*:")
READ_ONLY_RE = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)


# --------------------------------------------------------------------------- fichiers
def _jdd_dir() -> Path:
    return projet.PROJECT_DIR / os.environ.get("JDD_DIR", "data/jdd")


def _load(name: str) -> dict:
    path = _jdd_dir() / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"{path} introuvable.")
    return yaml.safe_load(path.read_text("utf-8")) or {}


def environnements() -> list[str]:
    return sorted(p.stem for p in _jdd_dir().glob("*.yaml") if p.stem != "requetes")


def lister(env: str) -> list[dict]:
    return [{"jeu": k, "description": (v or {}).get("description", ""),
             "champs": list(((v or {}).get("donnees") or {}).keys()),
             "prerequis": [p.get("requete") for p in (v or {}).get("prerequis", [])]}
            for k, v in _load(env).items()]


def lire(env: str, jeu: str) -> dict:
    """Jeu brut, secrets masqués (seul le nom de la variable d'environnement apparaît)."""
    data = _load(env)
    if jeu not in data:
        raise KeyError(f"Jeu « {jeu} » absent de {env}.yaml (jeux : {', '.join(data)})")
    return data[jeu]


# --------------------------------------------------------------------------- base
def _connect(env: str):
    return oracle.connect(env)


def executer_requete(env: str, nom: str, params: dict | None = None, max_lignes: int = 20) -> list[dict]:
    """Exécute une requête de la liste blanche (lecture seule), avec paramètres liés."""
    requetes = _load("requetes")
    if nom not in requetes:
        raise KeyError(f"Requête « {nom} » non déclarée dans requetes.yaml.")
    sql = requetes[nom]["sql"].strip().rstrip(";")
    if not READ_ONLY_RE.match(sql) or ";" in sql:
        raise PermissionError(f"Requête « {nom} » refusée : seules les lectures (SELECT) sont permises.")
    con = _connect(env)
    try:
        cur = con.cursor()
        cur.execute(sql, params or {})
        cols = [c[0].lower() for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchmany(max_lignes)]
        con.rollback()
        return [{k: (str(v) if v is not None else None) for k, v in r.items()} for r in rows]
    finally:
        con.close()


# --------------------------------------------------------------------------- résolution
def resoudre(env: str, jeux: list[str]) -> dict:
    """Vérifie les prérequis puis résout les valeurs.
    Retour : {'jeux': {nom: données résolues}, 'bloques': [...], 'controles': [...]}"""
    resolus, bloques, controles = {}, [], []
    for jeu in jeux:
        brut = lire(env, jeu)
        cache: dict = {}
        ok = True
        for p in brut.get("prerequis", []) or []:
            nom = p["requete"]
            try:
                lignes = executer_requete(env, nom, p.get("params"))
            except Exception as e:
                lignes, err = [], str(e)
            else:
                err = ""
            cache[nom] = lignes
            mini = int(p.get("min_lignes", 1))
            passe = len(lignes) >= mini and not err
            controles.append({"jeu": jeu, "requete": nom, "lignes": len(lignes),
                              "attendu_min": mini, "ok": passe, "erreur": err})
            if not passe:
                ok = False
                bloques.append({"jeu": jeu, "requete": nom,
                                "message": err or p.get("message", f"{nom} : données insuffisantes")})
        if not ok:
            continue

        def sub(m):
            kind, ref = m.group(1), m.group(2)
            if kind == "env":
                val = os.environ.get(ref)
                if val is None:
                    raise KeyError(f"Variable d'environnement {ref} absente (jeu {jeu}).")
                return val
            req, _, col = ref.partition(".")
            lignes = cache.get(req)
            if not lignes:
                raise KeyError(f"{{{{requete:{ref}}}}} : requête non déclarée en prérequis de {jeu}.")
            return str(lignes[0].get(col.lower(), ""))

        try:
            resolus[jeu] = {k: TOKEN_RE.sub(sub, str(v)) if isinstance(v, str) else v
                            for k, v in (brut.get("donnees") or {}).items()}
        except KeyError as e:
            bloques.append({"jeu": jeu, "requete": None, "message": str(e)})
    return {"jeux": resolus, "bloques": bloques, "controles": controles}


def masquer(env: str, resolus: dict) -> dict:
    """Version affichable : les valeurs issues de {{env:…}} sont masquées."""
    out = {}
    for jeu, donnees in resolus.items():
        brut = (lire(env, jeu).get("donnees") or {})
        out[jeu] = {k: ("••••" if isinstance(brut.get(k), str) and SECRET_RE.search(brut[k]) else v)
                    for k, v in donnees.items()}
    return out


def ecrire_fichier_variables(resolus: dict, chemin: Path) -> Path:
    """Fichier de variables Robot (YAML) : JDD_<NOM> devient un dictionnaire &{JDD_<NOM>}."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(yaml.safe_dump({f"JDD_{k.upper()}": v for k, v in resolus.items()},
                                     allow_unicode=True, sort_keys=False), "utf-8")
    return chemin


# --------------------------------------------------------------------------- vues
def liste(env: str = "") -> dict:
    """Environnements disponibles (sans env) ou jeux d'un environnement."""
    if not env:
        return {"environnements": environnements()}
    return {"env": env, "jeux": lister(env)}


def verifier(env: str, jeux: list[str]) -> dict:
    """Prérequis vérifiés avant un run ; valeurs secrètes masquées."""
    res = resoudre(env, jeux)
    return {"pret": not res["bloques"], "bloques": res["bloques"], "controles": res["controles"],
            "valeurs": masquer(env, res["jeux"])}


def detecter(target: str, env: str) -> dict:
    """Jeux de données référencés (JDD_<NOM>) dans les fichiers d'une suite du projet."""
    base = projet.safe_path(target)
    files = [base] if base.is_file() else list(base.rglob("*.robot")) + list(base.rglob("*.resource"))
    noms: set = set()
    for f in files:
        noms |= set(re.findall(r"JDD_([A-Z0-9_]+)", f.read_text("utf-8", errors="ignore")))
    dispo = {j["jeu"].upper(): j["jeu"] for j in lister(env)}
    return {"detectes": [dispo[n] for n in sorted(noms) if n in dispo],
            "inconnus": sorted(n for n in noms if n not in dispo)}
