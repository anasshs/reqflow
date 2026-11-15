"""
Jeux de données (JDD) des tests auto.

Fichiers dans le projet de tests (ROBOT_PROJECT_DIR) :
  data/jdd/<env>.yaml       jeux nommés (ex. VIREMENT_STANDARD) : données + prérequis
  data/jdd/requetes.yaml    requêtes SQL autorisées (liste blanche, lecture seule)
  data/jdd/api.yaml         appels d'API de préparation déclarés (environnements autorisés, jamais la production)

Dans les valeurs d'un jeu :
  {{env:NOM_VARIABLE}}             secret lu dans l'environnement (jamais écrit dans le dépôt)
  {{requete:NOM.colonne}}          1re ligne d'une requête déclarée dans les prérequis du jeu
  {{api:NOM.champ}}                champ extrait de la réponse d'un appel d'API déclaré dans les prérequis du jeu

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

TOKEN_RE = re.compile(r"\{\{\s*(env|requete|api)\s*:\s*([^}]+?)\s*\}\}")
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
    return sorted(p.stem for p in _jdd_dir().glob("*.yaml") if p.stem not in ("requetes", "api"))


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
        cache_api: dict = {}
        ok = True
        for p in brut.get("prerequis", []) or []:
            if p.get("api"):
                nom = p["api"]
                try:
                    cache_api[nom] = appeler_api(env, nom, p.get("params"))
                    controles.append({"jeu": jeu, "api": nom, "ok": True, "erreur": ""})
                except Exception as e:  # noqa: BLE001 — appel en échec : jeu bloqué, raison affichée
                    ok = False
                    controles.append({"jeu": jeu, "api": nom, "ok": False, "erreur": str(e)[:300]})
                    bloques.append({"jeu": jeu, "requete": None, "api": nom, "message": f"API {nom} : {str(e)[:300]}"})
                continue
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
            if kind == "api":
                nom_api, _, champ = ref.partition(".")
                if nom_api not in cache_api:
                    raise KeyError(f"{{{{api:{ref}}}}} : appel non déclaré en prérequis de {jeu}.")
                if champ not in cache_api[nom_api]:
                    raise KeyError(f"{{{{api:{ref}}}}} : champ absent de l'extraction de {nom_api}.")
                return str(cache_api[nom_api][champ])
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


# --------------------------------------------------------------------------- import CSV / JSON
CLE_SENSIBLE = re.compile(r"(?i)(password|passwd|mot_?de_?passe|mdp|secret|token|jeton|api_?key|pin|iban|carte|cvv)")


def _jeux_importes(contenu: str, format_: str) -> dict:
    import csv
    import io
    import json

    jeux: dict = {}
    if format_ == "csv":
        lecteur = csv.DictReader(io.StringIO(contenu.lstrip("\ufeff")), dialect=csv.Sniffer().sniff(contenu[:2000], delimiters=";,\t"))
        if not lecteur.fieldnames or "jeu" not in [c.strip().lower() for c in lecteur.fieldnames]:
            raise ValueError("CSV : une colonne « jeu » (nom du jeu, ex. CLIENT_ACTIF) est obligatoire.")
        for n, ligne in enumerate(lecteur, 2):
            ligne = {(k or "").strip(): (v or "").strip() for k, v in ligne.items()}
            nom = ligne.pop(next(k for k in ligne if k.lower() == "jeu"))
            desc = ligne.pop(next((k for k in list(ligne) if k.lower() == "description"), "__aucune__"), "")
            jeux.setdefault(nom, {"description": desc, "donnees": {}})["donnees"].update({k: v for k, v in ligne.items() if k and v != ""})
            if not nom:
                raise ValueError(f"CSV ligne {n} : nom du jeu vide.")
    elif format_ == "json":
        d = json.loads(contenu)
        items = d.items() if isinstance(d, dict) else [(x.get("jeu"), x) for x in d]
        for nom, v in items:
            v = v or {}
            donnees = v.get("donnees") if isinstance(v.get("donnees"), dict) else {k: x for k, x in v.items() if k not in ("jeu", "description")}
            jeux[str(nom or "")] = {"description": str(v.get("description") or ""), "donnees": {k: x for k, x in donnees.items()}}
    else:
        raise ValueError("Format : csv ou json.")
    return jeux


def importer(env: str, contenu: str, format_: str, ecraser: bool = False, ecrire: bool = False) -> dict:
    """Jeux de données importés d'un CSV (colonnes : jeu, description, puis un champ par colonne) ou d'un JSON
    ({jeu: {description, donnees}} ou liste d'objets avec « jeu »). Contrôles : noms de jeu en MAJUSCULES, aucune
    valeur sensible en clair ({{env:VAR}} obligatoire), pas d'écrasement d'un jeu existant sans ecraser=True.
    ecrire=False : aperçu ; ecrire=True : écriture par l'éditeur (historique)."""
    from atelier.domain import roles
    from atelier.generation import editeur

    if not re.fullmatch(r"[a-z0-9_-]{1,40}", env or ""):
        raise ValueError("Environnement : lettres minuscules, chiffres, - ou _ (ex. recette).")
    jeux = _jeux_importes(contenu, format_)
    if not jeux:
        raise ValueError("Aucun jeu dans le fichier.")
    erreurs = []
    for nom, j in jeux.items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", nom):
            erreurs.append(f"{nom or '(vide)'} : nom de jeu en MAJUSCULES (ex. CLIENT_ACTIF)")
        for k, v in j["donnees"].items():
            if not re.fullmatch(r"[a-z][a-z0-9_]*", k):
                erreurs.append(f"{nom}.{k} : nom de champ en minuscules (ex. mot_de_passe)")
            if CLE_SENSIBLE.search(k) and not SECRET_RE.search(str(v)):
                erreurs.append(f"{nom}.{k} : valeur sensible en clair, mettre {{{{env:NOM_VARIABLE}}}}")
    chemin = _jdd_dir() / f"{env}.yaml"
    existants = (yaml.safe_load(chemin.read_text("utf-8")) or {}) if chemin.exists() else {}
    conflits = sorted(set(jeux) & set(existants))
    if conflits and not ecraser:
        erreurs.append(f"Jeux déjà présents dans {env}.yaml : {', '.join(conflits)} (cocher « remplacer » pour les écraser)")
    apercu = {"env": env, "jeux": {n: {"description": j["description"], "champs": list(j["donnees"])} for n, j in jeux.items()},
              "nouveaux": sorted(set(jeux) - set(existants)), "remplaces": conflits if ecraser else [], "erreurs": erreurs}
    if not ecrire or erreurs:
        return {**apercu, "ecrit": False}
    roles.exiger("importer_donnees")
    fusion = {**existants, **{n: {k: v for k, v in (("description", j["description"]), ("donnees", j["donnees"])) if v} for n, j in jeux.items()}}
    rel = str(chemin.relative_to(projet.PROJECT_DIR))
    entete = chemin.read_text("utf-8").split("\n\n")[0] + "\n\n" if chemin.exists() and chemin.read_text("utf-8").startswith("#") else ""
    editeur.enregistrer(rel, entete + yaml.safe_dump(fusion, allow_unicode=True, sort_keys=False))
    return {**apercu, "ecrit": True, "fichier": rel}


# --------------------------------------------------------------------------- API de préparation des données
ENV_INTERDITS = re.compile(r"(?i)^(prod|production|prd|live)$")


def apis() -> dict:
    f = _jdd_dir() / "api.yaml"
    return (yaml.safe_load(f.read_text("utf-8")) or {}) if f.exists() else {}


def _substituer_secrets(v):
    from atelier.integrations.http import variable_secrete

    if isinstance(v, str):
        def sub(m):
            if m.group(1) != "env":
                raise ValueError("Seuls {{env:VAR}} sont permis dans la déclaration d'un appel d'API.")
            val = variable_secrete(m.group(2))
            if not val:
                raise KeyError(f"Variable {m.group(2)} absente (coffre ou environnement).")
            return val
        return TOKEN_RE.sub(sub, v)
    if isinstance(v, dict):
        return {k: _substituer_secrets(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_substituer_secrets(x) for x in v]
    return v


def _extraire(reponse, chemin: str):
    v = reponse
    for part in [p for p in chemin.split(".") if p]:
        if isinstance(v, list) and part.isdigit():
            v = v[int(part)]
        elif isinstance(v, dict) and part in v:
            v = v[part]
        else:
            raise KeyError(f"« {chemin} » absent de la réponse.")
    return v


def appeler_api(env: str, nom: str, params: dict | None = None, http_fn=None) -> dict:
    """Appel déclaré dans data/jdd/api.yaml (méthode, url, en-têtes, corps, environnements autorisés, champs à
    extraire). Refus : appel non déclaré, environnement non listé ou de production, méthode autre que GET / POST /
    PUT, URL non HTTPS (sauf localhost). Les secrets viennent du coffre ({{env:VAR}}) et n'apparaissent jamais en retour."""
    import json
    from urllib.parse import urlparse

    from atelier.integrations.http import http

    d = apis().get(nom)
    if not d:
        raise KeyError(f"Appel « {nom} » non déclaré dans api.yaml.")
    if ENV_INTERDITS.match(env or "") or env not in (d.get("environnements") or []):
        raise PermissionError(f"Appel « {nom} » non autorisé sur l'environnement « {env} » (autorisés : {', '.join(d.get('environnements') or []) or 'aucun'} ; jamais la production).")
    methode = str(d.get("methode") or "GET").upper()
    if methode not in ("GET", "POST", "PUT"):
        raise PermissionError(f"Méthode {methode} refusée (GET, POST, PUT).")
    url = _substituer_secrets(str(d.get("url") or ""))
    for k, v in (params or {}).items():
        url = url.replace("{" + k + "}", str(v))
    u = urlparse(url)
    if u.scheme != "https" and u.hostname not in ("localhost", "127.0.0.1"):
        raise PermissionError("URL HTTPS obligatoire (sauf localhost).")
    entetes = {"Content-Type": "application/json", "Accept": "application/json", **_substituer_secrets(d.get("entetes") or {})}
    corps = _substituer_secrets(d.get("corps")) if d.get("corps") is not None else None
    texte = (http_fn or http)(methode, url, json.dumps(corps).encode() if corps is not None else None, entetes, int(d.get("delai", 15)))
    try:
        reponse = json.loads(texte) if texte.strip() else {}
    except json.JSONDecodeError:
        raise ValueError(f"Réponse de {nom} non JSON.") from None
    return {champ: _extraire(reponse, chemin) for champ, chemin in (d.get("extraire") or {}).items()}


def tester_api(env: str, nom: str, params: dict | None = None, http_fn=None) -> dict:
    """Essai explicite depuis l'interface : l'appel est réel (il peut créer des données sur l'environnement)."""
    from atelier.domain import roles

    roles.exiger("preparer_donnees")
    valeurs = appeler_api(env, nom, params, http_fn)
    return {"api": nom, "env": env, "champs": sorted(valeurs), "valeurs": {k: (str(v)[:80] if not CLE_SENSIBLE.search(k) else "•••") for k, v in valeurs.items()}}


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
