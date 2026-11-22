"""Discovery Data Setup : référentiel universel de variables et de données, indépendant du métier de l'application.

Aucune catégorie n'est imposée (compte, bénéficiaire, dossier…) : l'automaticien déclare librement les variables dont
l'exploration a besoin. Cinq choses sont séparées :

  définition   data/discovery/variables.yaml   nom, clé, description, type, sensibilité, règles, source, alias, statut
  valeur       data/discovery/valeurs.yaml     par défaut, par environnement, par profil (une même variable, plusieurs valeurs)
  source       dans la définition              manuelle, environnement, coffre, générateur, calcul, API, requête, fichier, session
  contexte     discovery/donnees/contextes/    valeurs utilisées par UNE session Discovery (cohérentes d'un écran à l'autre)
  cycle de vie discovery/donnees/historique    qui a demandé quoi, quand, d'où vient la valeur (jamais la valeur sensible)

Profils et groupes (data/discovery/profils.yaml) : listes libres de variables, réutilisables d'une session à l'autre.

Sensibilité : « normale » (valeur lisible), « confidentielle » (masquée à l'écran, dans l'historique et pour l'agent),
« secrète » (en plus : jamais écrite dans un fichier, gardée dans le coffre du poste ou une variable d'environnement).
L'agent saisit une valeur masquée par sa référence {{var:CLE}}, résolue côté serveur au moment de la saisie.

Sources externes : les appels d'API et les requêtes sont ceux de data/jdd (liste blanche, lecture seule, jamais la
production) ; un fichier CSV / JSON est lu dans le projet de tests seulement.
"""
from __future__ import annotations

from atelier.domain.yaml_rapide import charger as charger_yaml

import ast
import csv
import io
import json
import os
import random
import re
import string
import uuid
from datetime import date, datetime, timedelta

import yaml

from atelier.domain import projet

CLE = re.compile(r"^[A-Z][A-Z0-9_]{0,59}$")
REF = re.compile(r"\{\{\s*(?:var\s*:\s*)?([A-Z][A-Z0-9_]*)\s*\}\}")
REF_SAISIE = re.compile(r"\{\{\s*var\s*:\s*([A-Z][A-Z0-9_]*)\s*\}\}")
TYPES = ("texte", "nombre", "entier", "booleen", "date", "email", "telephone", "url", "fichier", "json", "liste")
SENSIBILITES = ("normale", "confidentielle", "secrète")
SOURCES = ("manuelle", "environnement", "coffre", "generateur", "calcul", "api", "requete", "fichier", "session")
NATURES = ("groupe", "profil")
MASQUE = "••••"
FORMATS_DATE = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d")
HORS_SESSION = "hors-session"
ACTIONS_JOURNAL = ("obtenue", "générée", "calculée", "créée", "saisie", "manquante", "hors référentiel")
ACTIONS_USAGE = ("obtenue", "générée", "calculée", "créée", "saisie")
_MEMOIRE: dict = {}   # valeurs sensibles de la session en cours : jamais écrites sur le disque
_CHOIX: dict = {}     # profil et environnement choisis hors session Discovery


# =========================================================================== stockage
def _def_dir():
    return projet.PROJECT_DIR / os.environ.get("DISCOVERY_DONNEES_DIR", "data/discovery")


def _etat_dir():
    return projet.PROJECT_DIR / "discovery" / "donnees"


def _lire(nom: str) -> dict:
    f = _def_dir() / f"{nom}.yaml"
    return (charger_yaml(f.read_text("utf-8")) or {}) if f.exists() else {}


def _ecrire(nom: str, d: dict):
    f = _def_dir() / f"{nom}.yaml"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=True, width=120), "utf-8")


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _tracer(action: str, cle: str = "", **d):
    """Historique d'utilisation : jamais de valeur, seulement la variable, son origine et le champ servi."""
    f = _etat_dir() / "historique.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": _maintenant(), "action": action, "cle": cle, **{k: v for k, v in d.items() if v not in ("", None)}},
                            ensure_ascii=False) + "\n")
    if action in ACTIONS_JOURNAL and str(d.get("session") or "").startswith("DS-"):
        try:  # journal de la session Discovery : quelle donnée, pour quel champ, d'où elle vient — jamais la valeur
            from atelier.discovery import sessions_discovery

            quoi = " · ".join(str(x) for x in (cle, d.get("champ"), d.get("ecran"), d.get("origine") or d.get("raison")) if x)
            sessions_discovery._evenement(d["session"], {"type": "donnee", "action": action, "variable": cle, "detail": f"{action} · {quoi}"[:300]})
        except Exception:  # noqa: BLE001 — le journal n'empêche jamais d'obtenir une donnée
            pass


def historique(limite: int = 200, cle: str = "", session: str = "") -> list[dict]:
    f = _etat_dir() / "historique.jsonl"
    l = [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()] if f.exists() else []
    return [x for x in reversed(l) if (not cle or x.get("cle") == cle) and (not session or x.get("session") == session)][:limite]


# =========================================================================== définitions
def _normaliser(cle: str, d: dict) -> dict:
    src = d.get("source") or {}
    src = {"type": src} if isinstance(src, str) else dict(src)
    src.setdefault("type", "manuelle")
    return {"cle": cle, "nom": d.get("nom") or cle.replace("_", " ").capitalize(), "description": d.get("description", ""),
            "type": d.get("type") or "texte", "sensibilite": d.get("sensibilite") or "normale", "source": src,
            "regles": dict(d.get("regles") or {}), "alias": list(d.get("alias") or []),
            "environnements": list(d.get("environnements") or []), "reutilisable": d.get("reutilisable", True) is not False,
            "statut": d.get("statut") or "active"}


def variables(recherche: str = "", type_: str = "", profil: str = "", actives: bool = False) -> list[dict]:
    """Catalogue : définitions (jamais de valeur sensible), avec les variables dont chacune dépend."""
    membres = set(profils_dict().get(profil, {}).get("variables") or []) if profil else None
    vals, out = _lire("valeurs"), []
    for cle, d in sorted(_lire("variables").items()):
        v = _normaliser(cle, d or {})
        if (membres is not None and cle not in membres) or (type_ and v["type"] != type_) or (actives and v["statut"] != "active"):
            continue
        if recherche and recherche.casefold() not in " ".join([cle, v["nom"], v["description"], *v["alias"]]).casefold():
            continue
        x = vals.get(cle) or {}
        v["dependances"] = _dependances(v)
        v["valeurs"] = {"defaut": _affichable(v, x.get("defaut")),
                        "environnements": {e: _affichable(v, val) for e, val in (x.get("environnements") or {}).items()},
                        "profils": {p: _affichable(v, val) for p, val in (x.get("profils") or {}).items()}}
        out.append(v)
    return out


def variable(cle: str) -> dict:
    d = _lire("variables")
    if cle not in d:
        raise KeyError(f"Variable inconnue : {cle}")
    return _normaliser(cle, d[cle] or {})


def enregistrer_variable(cle: str, champs: dict) -> dict:
    """Crée ou modifie une définition. La valeur se règle à part (definir_valeur) : elle n'est pas dans la définition."""
    from atelier.domain import roles

    roles.exiger("preparer_donnees")
    cle = str(cle or "").strip().upper()
    if not CLE.match(cle):
        raise ValueError("Clé technique : majuscules, chiffres et _ (ex. CUSTOMER_EMAIL), 60 caractères au plus.")
    tout = _lire("variables")
    v = _normaliser(cle, {**(tout.get(cle) or {}), **{k: x for k, x in (champs or {}).items() if k != "cle"}})
    if v["type"] not in TYPES:
        raise ValueError(f"Type inconnu : {v['type']} ({', '.join(TYPES)}).")
    if v["sensibilite"] not in SENSIBILITES:
        raise ValueError(f"Sensibilité : {', '.join(SENSIBILITES)}.")
    if v["source"]["type"] not in SOURCES:
        raise ValueError(f"Source inconnue : {v['source']['type']} ({', '.join(SOURCES)}).")
    if v["statut"] not in ("active", "inactive"):
        raise ValueError("Statut : active ou inactive.")
    if v["source"]["type"] == "generateur" and v["source"].get("generateur") not in GENERATEURS:
        raise ValueError(f"Générateur inconnu ({', '.join(GENERATEURS)}).")
    if v["regles"].get("format"):
        try:
            re.compile(str(v["regles"]["format"]))
        except re.error as e:
            raise ValueError(f"Règle de format invalide : {e}") from None
    inconnues = [d for d in _dependances(v) if d != cle and d not in tout]
    if inconnues:
        raise ValueError("Dépend de variables inconnues : " + ", ".join(inconnues))
    tout[cle] = {k: x for k, x in v.items() if k != "cle"}
    cycle = _cycle(cle, tout)
    if cycle:
        raise ValueError("Dépendance circulaire : " + " → ".join(cycle))
    _ecrire("variables", tout)
    _tracer("définition enregistrée", cle)
    return v


def dupliquer_variable(cle: str, nouvelle: str) -> dict:
    v = variable(cle)
    if str(nouvelle).strip().upper() in _lire("variables"):
        raise FileExistsError(f"La variable {nouvelle} existe déjà.")
    return enregistrer_variable(nouvelle, {**{k: x for k, x in v.items() if k != "cle"}, "nom": v["nom"] + " (copie)"})


def supprimer_variable(cle: str) -> dict:
    from atelier.domain import roles

    roles.exiger("preparer_donnees")
    tout = _lire("variables")
    if cle not in tout:
        raise KeyError(f"Variable inconnue : {cle}")
    dependants = [k for k, d in tout.items() if k != cle and cle in _dependances(_normaliser(k, d or {}))]
    if dependants:
        raise ValueError(f"{cle} sert au calcul de : {', '.join(dependants)}. Modifier ces variables d'abord.")
    tout.pop(cle)
    _ecrire("variables", tout)
    vals = _lire("valeurs")
    if vals.pop(cle, None) is not None:
        _ecrire("valeurs", vals)
    pr = _lire("profils")
    for p in pr.values():
        p["variables"] = [x for x in p.get("variables") or [] if x != cle]
    _ecrire("profils", pr)
    _tracer("définition supprimée", cle)
    return {"supprimee": cle}


def _refs(x) -> list[str]:
    if isinstance(x, str):
        return REF.findall(x)
    if isinstance(x, dict):
        return [r for v in x.values() for r in _refs(v)]
    if isinstance(x, list):
        return [r for v in x for r in _refs(v)]
    return []


def _dependances(v: dict) -> list[str]:
    return list(dict.fromkeys(_refs({k: x for k, x in v["source"].items() if k != "type"})))


def _cycle(cle: str, tout: dict, chemin: tuple = ()) -> list[str]:
    if cle in chemin:
        return [*chemin[chemin.index(cle):], cle]
    if cle not in tout:
        return []
    for d in _dependances(_normaliser(cle, tout[cle] or {})):
        c = _cycle(d, tout, (*chemin, cle))
        if c:
            return c
    return []


def dependances() -> dict:
    """Règles et dépendances : pour chaque variable calculée ou paramétrée, ce dont elle dépend et ce qui en dépend."""
    tout = {v["cle"]: v for v in variables()}
    liens = [{"variable": c, "depend_de": d, "source": v["source"]["type"]} for c, v in tout.items() for d in v["dependances"]]
    problemes = [f"{l['variable']} dépend de {l['depend_de']}, inconnue" for l in liens if l["depend_de"] not in tout]
    problemes += [f"{l['variable']} dépend de {l['depend_de']}, inactive" for l in liens
                  if l["depend_de"] in tout and tout[l["depend_de"]]["statut"] != "active" and tout[l["variable"]]["statut"] == "active"]
    return {"liens": liens, "problemes": problemes,
            "regles": [{"variable": c, "type": v["type"], "regles": v["regles"]} for c, v in tout.items() if v["regles"]]}


# =========================================================================== profils et groupes
def profil_vers_jdd(profil: str, env: str, jeu: str = "") -> dict:
    """Jeu de données des tests (data/jdd/<env>.yaml) depuis un profil du référentiel : les tests automatisés rejouent
    avec les valeurs de la Discovery. Champ du jeu = clé de la variable en minuscules (KLINDOC_EMAIL → klindoc_email ;
    dans un keyword : ${JDD}[klindoc_email]).
    - date produite par le générateur « date » (decalage_jours) → {{date:+N:format}}, recalculée à chaque run ;
    - variable confidentielle ou secrète → {{env:CLE}} (jamais de valeur sensible écrite) ;
    - sinon la valeur réglée (profil, puis environnement, puis défaut), ou une valeur produite une fois par le générateur."""
    import random

    from atelier.execution import jdd

    p = profils_dict().get(str(profil or "").strip().upper())
    if not p:
        raise KeyError(f"Profil inconnu : {profil}")
    profil = str(profil).strip().upper()
    env = str(env or "").strip().lower()
    jeu = str(jeu or profil).strip().upper()
    vals, donnees, manquantes = _lire("valeurs"), {}, []
    for cle in p["variables"]:
        v = variable(cle)
        src, regle, champ = v["source"], vals.get(cle) or {}, cle.lower()
        if _sensible(v):
            donnees[champ] = "{{env:" + cle + "}}"
            continue
        valeur = next((regle.get(ou, {}).get(k) for ou, k in (("profils", profil), ("environnements", env))
                       if k and k in (regle.get(ou) or {})), None)
        if valeur is None and "defaut" in regle:
            valeur = regle["defaut"]
        if valeur is None and src.get("type") == "generateur" and src.get("generateur") == "date" and src.get("decalage_min") is None:
            valeur = "{{date:%+d:%s}}" % (int(src.get("decalage_jours", 0)), src.get("format", "%d/%m/%Y"))
        elif valeur is None and src.get("type") == "generateur":
            valeur = generer(src, v, None, random.Random())
        if valeur in (None, ""):
            manquantes.append(cle)
            continue
        donnees[champ] = valeur
    if manquantes:
        raise ValueError("Valeur à régler avant de créer le jeu de données : " + ", ".join(manquantes)
                         + " (Discovery › Données : valeur du profil ou par défaut).")
    import json

    r = jdd.importer(env, json.dumps({jeu: {"description": f"Depuis le profil {profil} (Discovery › Données)", "donnees": donnees}}),
                     "json", ecraser=True, ecrire=True)
    if r.get("erreurs"):
        raise ValueError(" ; ".join(r["erreurs"]))
    _tracer("jeu de données créé depuis le profil", profil, environnement=env, jeu=jeu)
    return {"jeu": jeu, "env": env, "fichier": r.get("fichier", ""), "champs": {c: c.lower() for c in p["variables"]},
            "dans_un_keyword": {c: "${JDD}[" + c.lower() + "]" for c in p["variables"]}}


def profils_dict() -> dict:
    return {k: {"description": (p or {}).get("description", ""), "nature": (p or {}).get("nature") or "groupe",
                "variables": list((p or {}).get("variables") or [])} for k, p in _lire("profils").items()}


def profils(nature: str = "") -> list[dict]:
    connues = set(_lire("variables"))
    return [{"nom": k, **p, "inconnues": [v for v in p["variables"] if v not in connues]}
            for k, p in sorted(profils_dict().items()) if not nature or p["nature"] == nature]


def enregistrer_profil(nom: str, variables_: list[str], description: str = "", nature: str = "groupe") -> dict:
    from atelier.domain import roles

    roles.exiger("preparer_donnees")
    nom = str(nom or "").strip().upper()
    if not CLE.match(nom):
        raise ValueError("Nom du profil : majuscules, chiffres et _ (ex. CLIENT_STANDARD).")
    if nature not in NATURES:
        raise ValueError("Nature : groupe (jeu de données) ou profil (profil utilisateur).")
    connues = set(_lire("variables"))
    inconnues = [v for v in variables_ or [] if v not in connues]
    if inconnues:
        raise ValueError("Variables inconnues : " + ", ".join(inconnues))
    pr = _lire("profils")
    pr[nom] = {"description": description, "nature": nature, "variables": list(dict.fromkeys(variables_ or []))}
    _ecrire("profils", pr)
    return {"nom": nom, **pr[nom]}


def dupliquer_profil(nom: str, nouveau: str) -> dict:
    p = profils_dict().get(nom)
    if not p:
        raise KeyError(f"Profil inconnu : {nom}")
    if str(nouveau).strip().upper() in profils_dict():
        raise FileExistsError(f"Le profil {nouveau} existe déjà.")
    r = enregistrer_profil(nouveau, p["variables"], p["description"], p["nature"])
    vals = _lire("valeurs")  # les valeurs propres au profil suivent la copie
    for x in vals.values():
        if nom in (x.get("profils") or {}):
            x["profils"][r["nom"]] = x["profils"][nom]
    _ecrire("valeurs", vals)
    return r


def supprimer_profil(nom: str) -> dict:
    from atelier.domain import roles

    roles.exiger("preparer_donnees")
    pr = _lire("profils")
    if pr.pop(nom, None) is None:
        raise KeyError(f"Profil inconnu : {nom}")
    _ecrire("profils", pr)
    return {"supprime": nom}


# =========================================================================== valeurs
def _sensible(v: dict) -> bool:
    return v["sensibilite"] != "normale"


def _affichable(v: dict, valeur):
    return valeur if valeur is None or not _sensible(v) else MASQUE


def _nom_coffre(cle: str, env: str = "", profil: str = "") -> str:
    return "donnee:" + cle + (f"@{env}" if env else "") + (f"#{profil}" if profil else "")


def definir_valeur(cle: str, valeur, env: str = "", profil: str = "") -> dict:
    """Règle la valeur d'une variable : par défaut, pour un environnement ou pour un profil. Une valeur secrète va dans
    le coffre du poste (à défaut : en mémoire, jusqu'à l'arrêt de l'atelier), jamais dans un fichier."""
    from atelier.domain import roles

    roles.exiger("preparer_donnees")
    v = variable(cle)
    if valeur not in (None, ""):
        erreurs = valider(v, valeur)
        if erreurs:
            raise ValueError(f"{cle} : " + " ; ".join(erreurs))
    ou = "profils" if profil else "environnements" if env else "defaut"
    if v["sensibilite"] == "secrète":
        from atelier.domain import coffre

        nom = _nom_coffre(cle, env, profil)
        if valeur in (None, ""):
            _MEMOIRE.pop(("coffre", nom), None)
            if coffre.disponible():
                coffre.effacer(nom)
            lieu = "effacée"
        elif coffre.disponible():
            coffre.ecrire(nom, str(valeur))
            lieu = "coffre du poste"
        else:
            _MEMOIRE[("coffre", nom)] = str(valeur)
            lieu = "mémoire (coffre indisponible : à ressaisir au prochain démarrage)"
        _tracer("valeur secrète réglée", cle, environnement=env, profil=profil, lieu=lieu)
        return {"cle": cle, "valeur": MASQUE, "lieu": lieu}
    vals = _lire("valeurs")
    x = vals.setdefault(cle, {})
    if ou == "defaut":
        x.pop("defaut", None) if valeur in (None, "") else x.__setitem__("defaut", valeur)
    else:
        d = x.setdefault(ou, {})
        d.pop(profil or env, None) if valeur in (None, "") else d.__setitem__(profil or env, valeur)
    _ecrire("valeurs", vals)
    _tracer("valeur réglée", cle, environnement=env, profil=profil)
    return {"cle": cle, "valeur": _affichable(v, valeur), "lieu": "data/discovery/valeurs.yaml"}


def _secret(cle: str, env: str, profil: str):
    from atelier.domain import coffre

    for nom in dict.fromkeys([_nom_coffre(cle, env, profil), _nom_coffre(cle, env), _nom_coffre(cle, "", profil), _nom_coffre(cle)]):
        val = _MEMOIRE.get(("coffre", nom)) or coffre.lire(nom)
        if val:
            return val
    return None


def secrets_etat(env: str = "") -> list[dict]:
    """Gestion des secrets : pour chaque variable secrète, où sa valeur est attendue et si elle est présente."""
    out = []
    for v in variables():
        if v["sensibilite"] != "secrète":
            continue
        src = v["source"]
        if src["type"] == "environnement":
            lieu, present = f"variable d'environnement {src.get('variable', v['cle'])}", bool(os.environ.get(src.get("variable", v["cle"])))
        elif src["type"] in ("manuelle", "coffre"):
            lieu, present = "coffre du poste", bool(_secret(v["cle"], env, ""))
        else:
            lieu, present = f"source {src['type']} (obtenue pendant la session)", None
        out.append({"cle": v["cle"], "nom": v["nom"], "lieu": lieu, "presente": present, "environnement": env})
    return out


# =========================================================================== validation
def _nombre(x) -> float:
    if isinstance(x, bool):
        raise ValueError
    if isinstance(x, (int, float)):
        return float(x)
    return float(str(x).replace(" ", "").replace("\xa0", "").replace(" ", "").replace(",", "."))


def _date(x, formats=FORMATS_DATE) -> date:
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    for f in formats:
        try:
            return datetime.strptime(str(x).strip(), f).date()
        except ValueError:
            continue
    raise ValueError(f"date illisible : {x}")


def valider(v: dict, valeur) -> list[str]:
    """Contrôle une valeur contre le type et les règles de la variable (format, longueur, bornes, valeurs autorisées)."""
    e, r, t, s = [], v.get("regles") or {}, v["type"], "" if valeur is None else str(valeur)
    try:
        if t in ("nombre", "entier"):
            n = _nombre(valeur)
            if t == "entier" and n != int(n):
                e.append("un entier est attendu")
            if r.get("min") is not None and n < float(r["min"]):
                e.append(f"inférieur au minimum {r['min']}")
            if r.get("max") is not None and n > float(r["max"]):
                e.append(f"supérieur au maximum {r['max']}")
        elif t == "booleen" and not isinstance(valeur, bool) and s.casefold() not in ("true", "false", "oui", "non", "0", "1", "vrai", "faux"):
            e.append("un booléen est attendu (oui / non)")
        elif t == "date":
            _date(valeur, (r["format_date"],) if r.get("format_date") else FORMATS_DATE)
        elif t == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", s):
            e.append("adresse e-mail invalide")
        elif t == "telephone" and not re.fullmatch(r"\+?[\d\s.\-()]{6,20}", s):
            e.append("numéro de téléphone invalide")
        elif t == "url" and not re.fullmatch(r"https?://\S+", s):
            e.append("URL invalide (http:// ou https://)")
        elif t == "json" and isinstance(valeur, str):
            json.loads(valeur)
        elif t == "liste" and not isinstance(valeur, (list, tuple)):
            e.append("une liste est attendue")
        elif t == "fichier":
            projet.safe_path(s)  # un fichier du projet de tests, jamais ailleurs
    except (ValueError, TypeError) as err:
        e.append(str(err) if "illisible" in str(err) or "interdit" in str(err) else f"valeur incompatible avec le type {t}")
    if r.get("format") and not re.fullmatch(str(r["format"]), s):
        e.append(f"ne respecte pas le format {r['format']}")
    if r.get("longueur_min") is not None and len(s) < int(r["longueur_min"]):
        e.append(f"moins de {r['longueur_min']} caractères")
    if r.get("longueur_max") is not None and len(s) > int(r["longueur_max"]):
        e.append(f"plus de {r['longueur_max']} caractères")
    if r.get("valeurs") and valeur not in r["valeurs"] and s not in [str(x) for x in r["valeurs"]]:
        e.append("hors des valeurs autorisées (" + ", ".join(str(x) for x in r["valeurs"][:8]) + ")")
    return e


# =========================================================================== générateurs
PRENOMS = ("Alex", "Camille", "Dominique", "Sacha", "Charlie", "Morgan", "Claude", "Noa", "Lou", "Eden")
NOMS = ("Martin", "Bernard", "Dubois", "Petit", "Durand", "Leroy", "Moreau", "Simon", "Laurent", "Michel")


def _g_date(p, rng):
    j = int(p.get("decalage_jours", 0))
    if p.get("decalage_min") is not None or p.get("decalage_max") is not None:
        j = rng.randint(int(p.get("decalage_min", 0)), int(p.get("decalage_max", 0)))
    return (date.today() + timedelta(days=j)).strftime(p.get("format", "%d/%m/%Y"))


def _g_nombre(p, rng):
    mini, maxi, dec = float(p.get("min", 0)), float(p.get("max", 1000)), int(p.get("decimales", 0))
    n = rng.uniform(mini, maxi)
    return int(round(n)) if dec == 0 else round(n, dec)


def _g_motif(p, rng):
    """# chiffre · A lettre majuscule · a lettre minuscule · * lettre ou chiffre ; le reste est recopié."""
    table = {"#": string.digits, "A": string.ascii_uppercase, "a": string.ascii_lowercase, "*": string.ascii_uppercase + string.digits}
    return "".join(rng.choice(table[c]) if c in table else c for c in str(p.get("motif", "########")))


GENERATEURS = {
    "date": ("Date du jour, décalée de N jours (decalage_jours) ou d'un nombre de jours tiré entre decalage_min et decalage_max ; format", _g_date),
    "nombre": ("Nombre entre min et max, avec decimales", _g_nombre),
    "email": ("Adresse e-mail unique : prefixe + aléa @ domaine (défaut : exemple.test, domaine réservé aux essais)",
              lambda p, rng: f"{p.get('prefixe', 'test')}.{''.join(rng.choice(string.ascii_lowercase + string.digits) for _ in range(8))}@{p.get('domaine', 'exemple.test')}"),
    "prenom": ("Prénom fictif", lambda p, rng: rng.choice(p.get("valeurs") or PRENOMS)),
    "nom": ("Nom de famille fictif", lambda p, rng: rng.choice(p.get("valeurs") or NOMS)),
    "identifiant": ("Identifiant unique (UUID), avec un prefixe facultatif", lambda p, rng: f"{p.get('prefixe', '')}{uuid.UUID(int=rng.getrandbits(128), version=4)}"),
    "alphanumerique": ("Chaîne de lettres et chiffres de longueur donnée",
                       lambda p, rng: "".join(rng.choice(p.get("alphabet") or string.ascii_uppercase + string.digits) for _ in range(int(p.get("longueur", 10))))),
    "telephone": ("Numéro respectant un motif (# = chiffre), ex. 06########", lambda p, rng: _g_motif({"motif": p.get("motif", "06########")}, rng)),
    "motif": ("Valeur respectant un motif : # chiffre, A majuscule, a minuscule, * lettre ou chiffre", _g_motif),
    "choix": ("Une valeur tirée dans la liste valeurs", lambda p, rng: rng.choice(list(p.get("valeurs") or [""]))),
}
# Sans variable dans le référentiel : générateur utilisé par type de champ, si les réglages l'autorisent.
GENERATEUR_PAR_TYPE = {"email": {"generateur": "email"}, "telephone": {"generateur": "telephone"}, "date": {"generateur": "date"},
                       "nombre": {"generateur": "nombre", "min": 1, "max": 100}, "entier": {"generateur": "nombre", "min": 1, "max": 100},
                       "texte": {"generateur": "alphanumerique", "longueur": 8}}


def generateurs() -> list[dict]:
    return [{"generateur": k, "description": d} for k, (d, _) in GENERATEURS.items()]


def generer(source: dict, v: dict | None = None, resoudre=None, rng=None) -> object:
    """Valeur produite par un générateur ; quand la variable a des règles, la valeur les respecte (20 essais)."""
    nom = source.get("generateur")
    if nom not in GENERATEURS:
        raise ValueError(f"Générateur inconnu : {nom}")
    rng = rng or random.SystemRandom()
    p = {k: (_substituer(x, resoudre) if resoudre and isinstance(x, str) else x) for k, x in source.items() if k not in ("type", "generateur")}
    for _ in range(20):
        val = GENERATEURS[nom][1](p, rng)
        if not v or not valider(v, val):
            return val
    raise ValueError(f"Le générateur « {nom} » ne produit pas de valeur conforme aux règles de {v['cle']} : {' ; '.join(valider(v, val))}")


# =========================================================================== calculs
def _substituer(texte: str, resoudre) -> str:
    return REF.sub(lambda m: str(resoudre(m.group(1))), texte)


def _evaluer(expr: str) -> float:
    """Arithmétique seule (+ - * / parenthèses) : aucune fonction, aucun nom, aucun appel."""
    ops = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b}

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return float(n.value)
        if isinstance(n, ast.BinOp) and type(n.op) in ops:
            return ops[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            return -ev(n.operand) if isinstance(n.op, ast.USub) else ev(n.operand)
        raise ValueError("formule refusée : seuls les nombres et + - * / ( ) sont permis")
    try:
        return ev(ast.parse(expr.strip(), mode="eval"))
    except SyntaxError:
        raise ValueError(f"formule illisible : {expr}") from None
    except ZeroDivisionError:
        raise ValueError("division par zéro dans la formule") from None


def _mois(d: date, n: int) -> date:
    a, m = divmod(d.month - 1 + n, 12)
    a, m = d.year + a, m + 1
    fin = (date(a + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).day
    return date(a, m, min(d.day, fin))


def calculer(source: dict, resoudre) -> object:
    """Valeur calculée depuis d'autres variables. operation : texte (assemblage), nombre (formule), date (base + durée)."""
    op = source.get("operation") or "texte"
    if op == "texte":
        return _substituer(str(source.get("formule", "")), resoudre)
    if op == "nombre":
        brut = REF.sub(lambda m: repr(_nombre(resoudre(m.group(1)))), str(source.get("formule", "")))
        n, dec = _evaluer(brut), int(source.get("decimales", 2))
        return int(round(n)) if dec == 0 else round(n, dec)
    if op == "date":
        base = str(source.get("base", "aujourd_hui"))
        d = date.today() if base == "aujourd_hui" else _date(_substituer(base, resoudre))
        n = int(_nombre(_substituer(str(source.get("ajouter", 0)), resoudre)))
        unite = source.get("unite", "jours")
        d = _mois(d, n) if unite == "mois" else _mois(d, 12 * n) if unite in ("annees", "années", "ans") else d + timedelta(days=n)
        return d.strftime(source.get("format", "%d/%m/%Y"))
    raise ValueError(f"Opération de calcul inconnue : {op} (texte, nombre, date)")


# =========================================================================== contexte de données d'une session
def session_courante() -> dict:
    """Session Discovery en cours (son environnement, son profil de données) ; sinon le contexte « hors session »."""
    try:
        from atelier.discovery import sessions_discovery

        s = sessions_discovery.active()
    except Exception:  # noqa: BLE001 — pas de session lisible : contexte hors session
        s = None
    if s:
        return {"session": s["id"], "environnement": s["config"].get("environnement", ""), "profil": s["config"].get("profil_donnees", "")}
    return {"session": HORS_SESSION, "environnement": _CHOIX.get("environnement", ""), "profil": _CHOIX.get("profil", "")}


def _fichier_contexte(sid: str):
    return _etat_dir() / "contextes" / f"{projet.slug(sid, 60, 'session')}.json"


def _charger_contexte(sid: str | None = None) -> dict:
    cour = session_courante()
    sid = sid or cour["session"]
    f = _fichier_contexte(sid)
    if f.exists():
        c = json.loads(f.read_text("utf-8"))
    else:
        c = {"session": sid, "environnement": cour["environnement"] if sid == cour["session"] else "",
             "profil": cour["profil"] if sid == cour["session"] else "", "ouvert": _maintenant(), "valeurs": {}}
    return c


def _sauver_contexte(c: dict):
    f = _fichier_contexte(c["session"])
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(c, ensure_ascii=False, indent=1, default=str), "utf-8")


def choisir(profil: str | None = None, environnement: str | None = None, sid: str | None = None) -> dict:
    """Profil de données et environnement du contexte (session en cours, ou hors session)."""
    if profil and profil not in profils_dict():
        raise KeyError(f"Profil inconnu : {profil} (profils : {', '.join(profils_dict()) or 'aucun'})")
    c = _charger_contexte(sid)
    if profil is not None:
        c["profil"] = profil
    if environnement is not None:
        c["environnement"] = environnement
    if c["session"] == HORS_SESSION:
        _CHOIX.update(profil=c["profil"], environnement=c["environnement"])
    _sauver_contexte(c)
    _tracer("contexte réglé", session=c["session"], profil=c["profil"], environnement=c["environnement"])
    return contexte(c["session"])


def contexte(sid: str | None = None) -> dict:
    """Data Context de la session : valeurs déjà utilisées (masquées si sensibles), leur origine et leurs dépendances."""
    c = _charger_contexte(sid)
    defs = _lire("variables")
    vals = [{"cle": k, **{a: b for a, b in x.items() if a != "valeur"}, "valeur": MASQUE if x.get("sensible") else x.get("valeur"),
             "au_catalogue": k in defs} for k, x in sorted(c["valeurs"].items())]
    return {**{k: c[k] for k in ("session", "environnement", "profil", "ouvert")}, "valeurs": vals,
            "variables_du_profil": profils_dict().get(c["profil"], {}).get("variables", [])}


def reinitialiser(sid: str | None = None, tout: bool = False) -> dict:
    """Réinitialisation : oublie les valeurs générées, calculées et créées pendant la session (tout=True : tout le contexte).
    Les prochaines demandes les produiront à nouveau."""
    c = _charger_contexte(sid)
    garde = {} if tout else {k: x for k, x in c["valeurs"].items() if x.get("origine") in ("référentiel", "source externe")}
    oubliees = sorted(set(c["valeurs"]) - set(garde))
    for k in oubliees:
        _MEMOIRE.pop((c["session"], k), None)
    c["valeurs"] = garde
    _sauver_contexte(c)
    _tracer("contexte réinitialisé", session=c["session"], oubliees=len(oubliees))
    return {"session": c["session"], "oubliees": oubliees, "gardees": sorted(garde)}


def _poser(c: dict, cle: str, valeur, sensible: bool, origine: str, source: str, dependances: list | None = None) -> None:
    if sensible:
        _MEMOIRE[(c["session"], cle)] = valeur
    c["valeurs"][cle] = {"valeur": None if sensible else valeur, "sensible": sensible, "origine": origine, "source": source,
                         "date": _maintenant(), "dependances": dependances or [], "utilisations": 0}


def _resoudre(cle: str, c: dict, pile: tuple = ()):
    """Valeur réelle d'une variable pour le contexte : déjà utilisée dans la session, sinon réglée (profil, environnement,
    défaut), sinon produite par sa source. La valeur est gardée dans le contexte : elle ne change plus pendant la session."""
    if cle in pile:
        raise ValueError("Dépendance circulaire : " + " → ".join([*pile, cle]))
    x = c["valeurs"].get(cle)
    if x:
        if not x.get("sensible"):
            return x["valeur"]
        if (c["session"], cle) in _MEMOIRE:
            return _MEMOIRE[(c["session"], cle)]
    defs = _lire("variables")
    if cle not in defs:
        raise KeyError(f"Variable inconnue : {cle} (ni au catalogue, ni dans le contexte de la session)")
    v = _normaliser(cle, defs[cle] or {})
    if v["statut"] != "active":
        raise ValueError(f"Variable {cle} inactive.")
    env, profil = c.get("environnement", ""), c.get("profil", "")
    if v["environnements"] and env and env not in v["environnements"]:
        raise ValueError(f"Variable {cle} non prévue pour l'environnement {env} ({', '.join(v['environnements'])}).")
    src, sens = v["source"], _sensible(v)
    suivant = lambda k: _resoudre(k, c, (*pile, cle))  # noqa: E731
    regle = (_lire("valeurs").get(cle) or {})
    valeur, origine, source = None, "référentiel", "valeur réglée"
    for ou, k in (("profils", profil), ("environnements", env)):
        if k and k in (regle.get(ou) or {}):
            valeur, source = regle[ou][k], f"valeur du {'profil' if ou == 'profils' else 'environnement'} {k}"
            break
    if valeur is None and v["sensibilite"] == "secrète" and src["type"] in ("manuelle", "coffre"):
        valeur, source = _secret(cle, env, profil), "coffre du poste"
    if valeur is None and "defaut" in regle:
        valeur, source = regle["defaut"], "valeur par défaut"
    if valeur is None:
        t = src["type"]
        if t == "environnement":
            valeur, source = os.environ.get(src.get("variable", cle)), f"variable d'environnement {src.get('variable', cle)}"
        elif t == "generateur":
            valeur, origine, source = generer(src, v, suivant), "générée", f"générateur {src.get('generateur')}"
        elif t == "calcul":
            valeur, origine, source = calculer(src, suivant), "calculée", f"calcul {src.get('operation', 'texte')}"
        elif t in ("api", "requete"):
            from atelier.execution import jdd

            params = {k: _substituer(str(p), suivant) for k, p in (src.get("params") or {}).items()}
            origine = "source externe"
            if t == "api":
                valeur, source = jdd.appeler_api(env, src.get("api", ""), params).get(src.get("champ", "")), f"API {src.get('api')}"
            else:
                lignes = jdd.executer_requete(env, src.get("requete", ""), params)
                valeur, source = (lignes[0].get(str(src.get("colonne", "")).lower()) if lignes else None), f"requête {src.get('requete')}"
        elif t == "fichier":
            valeur, origine, source = _depuis_fichier(src, suivant), "source externe", f"fichier {src.get('fichier')}"
        elif t == "session":
            raise LookupError(f"{cle} est produite pendant le parcours : elle n'a pas encore été relevée dans cette session "
                              "(discovery_donnee_definir dès que l'application l'affiche).")
    if valeur in (None, ""):
        raise LookupError(f"{cle} : aucune valeur ({'secret absent du coffre' if v['sensibilite'] == 'secrète' else 'valeur non réglée'}"
                          f"{', environnement ' + env if env else ''}{', profil ' + profil if profil else ''}).")
    erreurs = valider(v, valeur)
    if erreurs:
        raise ValueError(f"{cle} : valeur refusée par les règles ({' ; '.join(erreurs)}).")
    _poser(c, cle, valeur, sens, origine, source, _dependances(v))
    return valeur


def _depuis_fichier(src: dict, resoudre):
    """Valeur lue dans un fichier CSV ou JSON du projet de tests (colonne + ligne, ou chemin a.b.0)."""
    f = projet.safe_path(str(src.get("fichier", "")))
    if not f.exists():
        raise FileNotFoundError(f"Fichier de données introuvable : {src.get('fichier')}")
    texte = f.read_text("utf-8-sig")
    if f.suffix.lower() == ".json" or src.get("format") == "json":
        from atelier.execution.jdd import _extraire

        return _extraire(json.loads(texte), str(src.get("chemin", "")))
    lignes = list(csv.DictReader(io.StringIO(texte), delimiter=src.get("separateur") or (";" if texte.count(";") > texte.count(",") else ",")))
    if src.get("filtre"):  # {colonne: valeur} — la valeur peut citer une autre variable
        attendu = {k: _substituer(str(x), resoudre) for k, x in src["filtre"].items()}
        lignes = [l for l in lignes if all(str(l.get(k, "")) == x for k, x in attendu.items())]
    i = int(src.get("ligne", 0))
    if i >= len(lignes):
        raise LookupError(f"{src.get('fichier')} : aucune ligne ne convient.")
    return lignes[i].get(str(src.get("colonne", "")))


def _vue_agent(cle: str, c: dict, valeur) -> dict:
    x = c["valeurs"][cle]
    return {"cle": cle, "valeur": MASQUE if x["sensible"] else valeur, "sensible": x["sensible"], "saisie": "{{var:" + cle + "}}",
            "origine": x["origine"], "source": x["source"]}


def obtenir(cle: str, sid: str | None = None, champ: str = "", ecran: str = "") -> dict:
    """Data Provider : la valeur d'une variable pour la session. Une valeur sensible n'est jamais renvoyée : elle se
    saisit par sa référence {{var:CLE}}."""
    c = _charger_contexte(sid)
    nouvelle = cle not in c["valeurs"]
    try:
        valeur = _resoudre(cle, c)
    except Exception as e:
        _sauver_contexte(c)  # les dépendances déjà résolues restent cohérentes
        _tracer("manquante", cle, session=c["session"], champ=champ, ecran=ecran, raison=str(e)[:200])
        raise
    c["valeurs"][cle]["utilisations"] = c["valeurs"][cle].get("utilisations", 0) + 1
    _sauver_contexte(c)
    origine = c["valeurs"][cle]["origine"]
    _tracer(origine if nouvelle and origine in ("générée", "calculée") else "obtenue", cle, session=c["session"], champ=champ, ecran=ecran, origine=c["valeurs"][cle]["origine"], source=c["valeurs"][cle]["source"])
    return _vue_agent(cle, c, valeur)


def definir_contexte(cle: str, valeur, description: str = "", sensible: bool = False, sid: str | None = None) -> dict:
    """Enrichit le contexte : valeur relevée ou créée pendant le parcours (référence de dossier affichée, date choisie).
    Une variable du catalogue garde son type et ses règles ; une clé inconnue devient une variable de la session seulement."""
    cle = str(cle or "").strip().upper()
    if not CLE.match(cle):
        raise ValueError("Clé technique : majuscules, chiffres et _ (ex. DOSSIER_REFERENCE).")
    if valeur in (None, ""):
        raise ValueError("Valeur vide.")
    c = _charger_contexte(sid)
    defs = _lire("variables")
    if cle in defs:
        v = _normaliser(cle, defs[cle] or {})
        erreurs = valider(v, valeur)
        if erreurs:
            raise ValueError(f"{cle} : " + " ; ".join(erreurs))
        sensible = sensible or _sensible(v)
    _poser(c, cle, valeur, bool(sensible), "créée pendant la session", description or "relevée pendant le parcours")
    _sauver_contexte(c)
    _tracer("créée", cle, session=c["session"], origine="créée pendant la session", au_catalogue=cle in defs)
    return _vue_agent(cle, c, valeur)


def resoudre_saisie(texte: str, locator: str = "") -> str:
    """Texte à saisir : chaque {{var:CLE}} est remplacé par la valeur réelle, côté serveur (l'agent ne la voit pas).
    Une saisie littérale faite pendant une session, absente du contexte, est tracée « hors référentiel »."""
    c = _charger_contexte()
    refs = REF_SAISIE.findall(texte or "")
    if not refs:
        if c["session"] != HORS_SESSION and texte and not any(
                str(x.get("valeur")) == texte or str(_MEMOIRE.get((c["session"], k))) == texte for k, x in c["valeurs"].items()):
            _tracer("hors référentiel", session=c["session"], champ=locator[:120])
        return texte
    try:
        resolu = REF_SAISIE.sub(lambda m: str(_resoudre(m.group(1), c)), texte)
    finally:
        _sauver_contexte(c)
    for k in dict.fromkeys(refs):
        c["valeurs"][k]["utilisations"] = c["valeurs"][k].get("utilisations", 0) + 1
        _tracer("saisie", k, session=c["session"], champ=locator[:120], locator=locator, origine=c["valeurs"][k]["origine"])
    _sauver_contexte(c)
    return resolu


# =========================================================================== besoins d'un écran
def reglages() -> dict:
    r = _lire("reglages")
    return {"sans_variable": r.get("sans_variable") if r.get("sans_variable") in ("signaler", "generer") else "signaler",
            "generateurs_autorises": [t for t in r.get("generateurs_autorises") or [] if t in GENERATEUR_PAR_TYPE]}


def regler(sans_variable: str, generateurs_autorises: list[str] | None = None) -> dict:
    """Champ sans variable au référentiel : « signaler » (défaut, rien n'est inventé) ou « generer » pour les seuls types
    de champ listés (email, telephone, date, nombre, entier, texte)."""
    from atelier.domain import roles

    roles.exiger("preparer_donnees")
    if sans_variable not in ("signaler", "generer"):
        raise ValueError("sans_variable : signaler ou generer.")
    _ecrire("reglages", {"sans_variable": sans_variable, "generateurs_autorises": [t for t in generateurs_autorises or [] if t in GENERATEUR_PAR_TYPE]})
    return reglages()


def _sans_accent(t: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", str(t or "").casefold()) if not unicodedata.combining(c))


NATURES_CHAMP = [  # (type, secret, motif sur le libellé sans accent) — l'ordre compte : le plus précis d'abord
    ("texte", True, r"mot de passe|password|passwd|\bmdp\b|code secret|\bpin\b|code confidentiel"),
    ("texte", True, r"\botp\b|code de (verification|validation|securite)|code recu"),
    ("email", False, r"e-?mail|courriel|adresse electronique"),
    ("telephone", False, r"telephone|\btel\b|mobile|portable|\bgsm\b|phone"),
    ("date", False, r"\bdate\b|naissance|echeance|\bjour\b|debut|\bfin\b|expiration"),
    ("url", False, r"\burl\b|site web|lien"),
    ("fichier", False, r"fichier|document|piece jointe|justificatif|\bpdf\b|photo|image"),
    ("nombre", False, r"montant|prix|somme|quantite|nombre|duree|taux|\bage\b|solde|total|plafond"),
]
TYPES_HTML = {"email": "email", "tel": "telephone", "date": "date", "number": "nombre", "url": "url", "file": "fichier",
              "checkbox": "booleen", "password": "texte", "datetime-local": "date"}


def nature_champ(libelle: str, type_champ: str = "") -> dict:
    """Nature de la donnée attendue par un champ, d'après son libellé et son type technique (indication, sans IA)."""
    t = str(type_champ or "").casefold()
    lib = _sans_accent(libelle)
    for typ, secret, motif in NATURES_CHAMP:
        if re.search(motif, lib):
            return {"type": TYPES_HTML.get(t, typ) if not secret else "texte", "secret": secret or t == "password"}
    return {"type": TYPES_HTML.get(t, "texte"), "secret": t == "password"}


def rechercher(libelle: str = "", type_: str = "", contraintes: dict | None = None, sid: str | None = None, limite: int = 5) -> list[dict]:
    """Variables compatibles avec un besoin : nom, clé ou alias proches du libellé, type compatible, variable active et
    prévue pour l'environnement ; celles du profil de la session passent d'abord. contraintes : longueur_max, valeurs…"""
    from atelier.generation.reutilisation import mots

    c = _charger_contexte(sid)
    membres = set(profils_dict().get(c.get("profil", ""), {}).get("variables") or [])
    besoin, out = mots(libelle), []
    for v in variables(actives=True):
        if v["environnements"] and c.get("environnement") and c["environnement"] not in v["environnements"]:
            continue
        if type_ and v["type"] != type_ and "texte" not in (type_, v["type"]) and {type_, v["type"]} != {"nombre", "entier"}:
            continue
        noms = [v["nom"], v["cle"], *v["alias"]]
        if besoin:
            score = max((len(besoin & m) / len(besoin | m) for m in map(mots, noms) if m), default=0.0)
            if _sans_accent(libelle).strip() in [_sans_accent(n).strip() for n in noms]:
                score = 1.0
        else:
            score = 0.5 if type_ and v["type"] == type_ else 0.0
        if score < 0.5:
            continue
        lmax = (contraintes or {}).get("longueur_max")
        if lmax and v["regles"].get("longueur_max") and int(v["regles"]["longueur_max"]) > int(lmax):
            continue
        out.append({"cle": v["cle"], "nom": v["nom"], "type": v["type"], "sensibilite": v["sensibilite"], "source": v["source"]["type"],
                    "dans_le_profil": v["cle"] in membres, "deja_utilisee": v["cle"] in c["valeurs"], "score": round(score, 2),
                    "regles": v["regles"]})
    return sorted(out, key=lambda x: (-x["score"], not x["dans_le_profil"], not x["deja_utilisee"], x["cle"]))[:limite]


def pour_champs(champs: list[dict], ecran: str = "", sid: str | None = None) -> dict:
    """Besoins en données d'un écran. Pour chaque champ {libelle, type?, contraintes?} : nature de la donnée, variable
    retenue, valeur cohérente avec la session (ou référence de saisie si elle est sensible). Sans variable adaptée : un
    générateur autorisé par les réglages, sinon « manquante » — jamais une donnée inventée en silence."""
    regl, out = reglages(), []
    for ch in champs or []:
        ch = ch if isinstance(ch, dict) else {"libelle": str(ch)}
        lib = str(ch.get("libelle") or ch.get("label") or "").strip()
        nat = nature_champ(lib, ch.get("type", ""))
        r = {"champ": lib, "type_attendu": nat["type"], "secret": nat["secret"]}
        cands = rechercher(lib, nat["type"] if nat["type"] != "texte" else "", ch.get("contraintes"), sid)
        if cands:
            r["candidats"] = [{k: x[k] for k in ("cle", "nom", "type", "score", "dans_le_profil")} for x in cands]
            try:
                r.update(statut="trouvée", **obtenir(cands[0]["cle"], sid, lib, ecran))
            except Exception as e:  # noqa: BLE001 — variable connue mais sans valeur : dite telle quelle
                r.update(statut="manquante", cle=cands[0]["cle"], raison=str(e)[:300],
                         consigne="La variable existe mais n'a pas de valeur utilisable : le signaler à l'automaticien, ne rien inventer.")
        elif regl["sans_variable"] == "generer" and nat["type"] in regl["generateurs_autorises"] and not nat["secret"]:
            cle = ("AUTO_" + re.sub(r"[^A-Z0-9]+", "_", _sans_accent(lib).upper()).strip("_"))[:60] or "AUTO_CHAMP"
            c = _charger_contexte(sid)
            if cle not in c["valeurs"]:
                _poser(c, cle, generer(GENERATEUR_PAR_TYPE[nat["type"]]), False, "générée", f"générateur autorisé ({nat['type']}), sans variable au catalogue")
                _sauver_contexte(c)
                _tracer("générée", cle, session=c["session"], champ=lib, ecran=ecran, origine="générée", source="sans variable au catalogue")
            r.update(statut="générée", **_vue_agent(cle, c, c["valeurs"][cle]["valeur"]),
                     consigne="Valeur générée faute de variable : la proposer au catalogue si le champ revient.")
        else:
            _tracer("manquante", session=_charger_contexte(sid)["session"], champ=lib, ecran=ecran, raison="aucune variable compatible")
            r.update(statut="manquante", raison="aucune variable compatible au référentiel",
                     consigne="Ne rien inventer : signaler la donnée manquante à l'automaticien (nom du champ, type attendu) et "
                              "poursuivre ailleurs. Il crée la variable dans Discovery › Données.")
        out.append(r)
    bilan = {s: sum(x["statut"] == s for x in out) for s in ("trouvée", "générée", "manquante")}
    return {"champs": out, "trouvees": bilan["trouvée"], "generees": bilan["générée"], "manquantes": bilan["manquante"],
            "saisie": "type_text(locator, \"{{var:CLE}}\") : la valeur est posée côté serveur, même si elle est masquée ici."}


# =========================================================================== où chaque variable a servi
def usages(session: str = "") -> list[dict]:
    """Utilisations regroupées par (variable, écran, champ, locator), lues dans l'historique : nombre, sessions, dernière date."""
    f = _etat_dir() / "historique.jsonl"
    lignes = [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()] if f.exists() else []
    out: dict = {}
    for h in lignes:
        if h.get("action") not in ACTIONS_USAGE or not h.get("cle") or (session and h.get("session") != session):
            continue
        k = (h["cle"], h.get("ecran", ""), "" if h.get("locator") else h.get("champ", ""), h.get("locator", ""))
        u = out.setdefault(k, {"cle": k[0], "ecran": k[1], "champ": k[2], "locator": k[3], "utilisations": 0, "sessions": [], "derniere": ""})
        u["utilisations"] += 1
        u["derniere"] = h["date"]
        if h.get("session") and h["session"] not in u["sessions"]:
            u["sessions"].append(h["session"])
    return list(out.values())


def liens_carte(session: str = "") -> list[dict]:
    """Rattache chaque utilisation à la carte de l'application : écran, et élément quand il est identifié.
    - saisie : le locator désigne l'élément ; s'il existe sur plusieurs écrans, l'écran indiqué par l'agent pour la même
      variable départage, sinon aucun lien n'est fait (jamais un lien deviné) ;
    - demande pour un écran nommé : l'élément de même libellé, sinon l'écran seul."""
    from atelier.discovery import carte

    try:
        ecrans = carte.ecrans() if carte.app_courante() else []
    except Exception:  # noqa: BLE001 — pas de carte : aucune utilisation rattachée
        ecrans = []
    ref = lambda e: e.get("nom") or e["id"]  # noqa: E731
    par_locator: dict = {}
    for e in ecrans:
        for cle_el, el in (e.get("elements") or {}).items():
            for locs in (el.get("locators") or {}).values():
                for loc in locs or []:
                    par_locator.setdefault(loc, set()).add((ref(e), cle_el))
    us = usages(session)
    ecran_dit = {}
    for u in us:
        if u["ecran"]:
            ecran_dit.setdefault(u["cle"], set()).add(u["ecran"])
    out: dict = {}

    def lier(u, ecran_ref, element):
        x = out.setdefault((u["cle"], ecran_ref, element), {"cle": u["cle"], "ecran": ecran_ref, "element": element, "utilisations": 0,
                                                           "sessions": [], "saisie": False})
        x["utilisations"] += u["utilisations"]
        x["saisie"] = x["saisie"] or bool(u["locator"])
        x["sessions"] = sorted(set(x["sessions"]) | set(u["sessions"]))

    for u in us:
        if u["locator"]:
            cibles = par_locator.get(u["locator"], set())
            if len(cibles) > 1:
                cibles = {c for c in cibles if c[0] in ecran_dit.get(u["cle"], ())}
            if len(cibles) == 1:
                lier(u, *next(iter(cibles)))
        elif u["ecran"]:
            try:
                e = carte.ecran(u["ecran"])
            except Exception:  # noqa: BLE001 — écran nommé par l'agent, inconnu de la carte
                continue
            el = next((k for k, x in (e.get("elements") or {}).items()
                       if u["champ"] and _sans_accent(x.get("libelle", "")).strip() == _sans_accent(u["champ"]).strip()), "")
            lier(u, ref(e), el)
    return sorted(out.values(), key=lambda x: (x["ecran"], x["element"], x["cle"]))


# =========================================================================== préparation et vue d'ensemble
def preparer(profil: str = "", environnement: str = "") -> dict:
    """Préparation : essaie d'obtenir chaque variable du profil (ou du catalogue) dans un contexte d'essai, sans toucher
    au contexte d'une session. Dit ce qui est prêt et ce qui bloque, avant de lancer le Discovery."""
    cles = profils_dict().get(profil, {}).get("variables") if profil else [v["cle"] for v in variables(actives=True)]
    if profil and profil not in profils_dict():
        raise KeyError(f"Profil inconnu : {profil}")
    essai = {"session": "__preparation__", "environnement": environnement, "profil": profil, "valeurs": {}}
    pretes, bloquees = [], []
    for cle in cles or []:
        try:
            val = _resoudre(cle, essai)
            x = essai["valeurs"][cle]
            pretes.append({"cle": cle, "valeur": MASQUE if x["sensible"] else val, "origine": x["origine"], "source": x["source"]})
        except LookupError as e:
            (pretes if "pendant le parcours" in str(e) else bloquees).append(
                {"cle": cle, "valeur": None, "origine": "pendant la session", "source": "relevée pendant le parcours"}
                if "pendant le parcours" in str(e) else {"cle": cle, "raison": str(e)[:300]})
        except Exception as e:  # noqa: BLE001 — chaque blocage est rapporté avec sa raison
            bloquees.append({"cle": cle, "raison": str(e)[:300]})
    for k in [k for k in _MEMOIRE if k[0] == "__preparation__"]:
        _MEMOIRE.pop(k, None)
    return {"profil": profil, "environnement": environnement, "pretes": pretes, "bloquees": bloquees, "pret": not bloquees}


def _environnements_projet() -> list[str]:
    """Environnements du projet : ceux du projet Xray (secours : ceux qui ont des jeux de données)."""
    from atelier.integrations.xray import environnements

    return environnements.liste()


def sources_externes() -> dict:
    """Sources externes déclarées et variables qui s'en servent (API et requêtes : celles de data/jdd, déjà gardées)."""
    from atelier.execution import jdd

    par_source: dict = {}
    for v in variables():
        t = v["source"]["type"]
        if t in ("api", "requete", "fichier", "environnement", "coffre"):
            ref = v["source"].get({"api": "api", "requete": "requete", "fichier": "fichier", "environnement": "variable"}.get(t, ""), "") or v["cle"]
            par_source.setdefault(f"{t}:{ref}", {"type": t, "reference": ref, "variables": []})["variables"].append(v["cle"])
    try:
        req = sorted(jdd._load("requetes"))
    except FileNotFoundError:
        req = []
    return {"utilisees": sorted(par_source.values(), key=lambda x: (x["type"], x["reference"])), "apis_declarees": sorted(jdd.apis()),
            "requetes_declarees": req, "environnements": _environnements_projet()}


def vue() -> dict:
    vs = variables()
    return {"variables": len(vs), "actives": sum(v["statut"] == "active" for v in vs),
            "par_type": {t: sum(v["type"] == t for v in vs) for t in TYPES if any(v["type"] == t for v in vs)},
            "par_source": {s: sum(v["source"]["type"] == s for v in vs) for s in SOURCES if any(v["source"]["type"] == s for v in vs)},
            "sensibles": sum(v["sensibilite"] != "normale" for v in vs), "profils": len(profils_dict()),
            "types": list(TYPES), "sources": list(SOURCES), "sensibilites": list(SENSIBILITES), "generateurs": generateurs(),
            "reglages": reglages(), "contexte": {k: session_courante()[k] for k in ("session", "environnement", "profil")}}
