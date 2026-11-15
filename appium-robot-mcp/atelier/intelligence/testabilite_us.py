"""Testabilité des User Stories : politique actionnable de la stratégie de test, rejouée à chaque sprint.

Le backlog du sprint (construit par le PO) est le périmètre de test de l'itération : par défaut, chaque espace suit
son sprint actif (option : aussi le sprint suivant, pour préparer pendant le planning). Au démarrage, le périmètre
du sprint peut être figé (photo immuable) ; le bilan compare ensuite le sprint à cette photo (US ajoutées / retirées
en cours de sprint) et mesure la couverture obtenue.

Pour chaque espace Jira activé (projet d'une squad rattaché au projet Xray du projet actif), chaque US qui entre dans
le périmètre suit un cycle tracé :
    Détectée -> Analysée -> Questions envoyées -> Réponses reçues -> Cas proposés -> Couverte
    (ou Couverte (existant) si des tests Xray la couvrent déjà ; ou Non testable, avec justification).

Garde-fous :
- rien n'est écrit dans Jira ni dans Xray sans action explicite de l'automaticien (questions relues avant envoi,
  cas validés avant publication) ;
- l'IA (fournisseur choisi par l'entreprise, voir fournisseur_ia) ne fait que proposer ; les règles explicables
  fonctionnent seules ; tout texte est masqué avant envoi à un modèle ;
- chaque décision est historisée (testabilite/journal.jsonl) ; état par US dans testabilite/us.json.
"""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime

import yaml

from atelier.domain import projet

STATUTS = ["Détectée", "Analysée", "Questions envoyées", "Réponses reçues", "Cas proposés", "Couverte",
           "Couverte (existant)", "Non testable"]
TYPES_TEST = ("Manual", "Cucumber")
PORTEES = {"sprint": "sprint actif", "sprint_suivant": "prochain sprint uniquement", "sprint_et_suivant": "sprint actif + prochain sprint",
           "backlog": "backlog entier (US non terminées, avec ou sans sprint)", "hors_sprint": "backlog hors sprint (non planifié)",
           "statuts": "statuts (sans sprint)"}
MARQUEUR = "[Atelier QA] Questions de testabilité"

# --------------------------------------------------------------------------- règles d'analyse (explicables)
TERMES_VAGUES = ["rapide", "rapidement", "performant", "facile", "facilement", "intuitif", "convivial", "optimal",
                 "correctement", "adapté", "approprié", "etc", "si possible", "éventuellement", "et/ou", "...", "…",
                 "plusieurs", "certains", "quelques", "normalement", "sécurisé"]
A_DEFINIR = re.compile(r"(?i)\b(tbd|à définir|a definir|à préciser|a preciser|à confirmer|todo)\b|\?\?")
CAS_ERREUR = re.compile(r"(?i)\b(erreur|refus|refusé|invalide|échec|echec|impossible|interdit|bloqu|rejet|exception|si .{0,40}sinon|message d'erreur)")
DONNEES = re.compile(r"(?i)\b(montant|plafond|date|format|nombre|longueur|caract[eè]res?|champ|valeur|limite|seuil|\d+)")
ROLES = re.compile(r"(?i)\b(en tant que|utilisateur|client|conseiller|administrateur|agent|gestionnaire|profil|rôle|role)\b")


def _d():
    return projet.PROJECT_DIR / "testabilite"


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _auteur() -> str:
    return os.environ.get("USERNAME") or os.environ.get("USER") or "automaticien"


def _ecrire(nom: str, texte: str):
    f = _d() / nom
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(f.suffix + ".tmp")
    tmp.write_text(texte, "utf-8")
    os.replace(tmp, f)


def _journaliser(op: str, **d):
    _d().mkdir(parents=True, exist_ok=True)
    with (_d() / "journal.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": _maintenant(), "auteur": _auteur(), "op": op, **d}, ensure_ascii=False) + "\n")


def journal(cle: str = "", limite: int = 200) -> list[dict]:
    f = _d() / "journal.jsonl"
    l = [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()] if f.exists() else []
    return [x for x in l if not cle or x.get("cle") == cle][::-1][:limite]


# =========================================================================== politique : espaces Jira activés
def espaces() -> list[dict]:
    """Espaces Jira (politique des US) de l'application active ; un espace non rattaché (ancienne politique) vaut
    pour toutes les applications jusqu'à son rattachement (Paramètres › Configuration)."""
    from atelier.discovery import carte

    app = carte.app_courante()
    return [e for e in tous_espaces() if not app or not e.get("application") or e["application"] == app]


def tous_espaces() -> list[dict]:
    f = _d() / "espaces.yaml"
    return (yaml.safe_load(f.read_text("utf-8")) or {}).get("espaces", []) if f.exists() else []


def enregistrer_espace(e: dict) -> list[dict]:
    """Espace = projet Jira d'une squad. projet_xray : projet où les tests sont créés (défaut : projet actif)."""
    from atelier.domain import projets

    cle = str(e.get("projet_jira") or "").strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,19}", cle):
        raise ValueError("Clé du projet Jira de la squad attendue (ex. SQUAD1).")
    type_test = e.get("type_test") or "Manual"
    if type_test not in TYPES_TEST:
        raise ValueError(f"Type de test : {', '.join(TYPES_TEST)}.")
    propre = {"projet_jira": cle, "nom": str(e.get("nom") or cle).strip(), "actif": bool(e.get("actif", True)),
              "types_issue": [t.strip() for t in (e.get("types_issue") or ["Story"]) if str(t).strip()],
              "statuts": [s.strip() for s in (e.get("statuts") or []) if str(s).strip()],
              "jql_complement": str(e.get("jql_complement") or "").strip(),
              "projet_xray": (str(e.get("projet_xray") or "").strip().upper() or projets.cle_xray()),
              "type_test": type_test, "min_tests": max(1, int(e.get("min_tests") or 1)),
              "portee": e.get("portee") if e.get("portee") in PORTEES else "sprint",
              "application": str(e.get("application") or "").strip() or _app_active()}
    autre = next((x for x in tous_espaces() if x["projet_jira"] == cle and x.get("application") and x["application"] != propre["application"]), None)
    if autre:
        raise ValueError(f"L'espace {cle} est déjà rattaché à l'application « {autre['application']} ».")
    if not propre["projet_xray"]:
        raise ValueError("Projet Xray cible requis (ou un projet actif avec une clé Xray).")
    l = [x for x in tous_espaces() if x["projet_jira"] != cle] + [propre]
    _ecrire("espaces.yaml", yaml.safe_dump({"espaces": l}, allow_unicode=True, sort_keys=False))
    _journaliser("politique_espace", espace=cle, actif=propre["actif"])
    return l


def supprimer_espace(cle: str) -> list[dict]:
    l = [x for x in tous_espaces() if x["projet_jira"] != cle]
    _ecrire("espaces.yaml", yaml.safe_dump({"espaces": l}, allow_unicode=True, sort_keys=False))
    _journaliser("politique_espace_retire", espace=cle)
    return l


def _app_active() -> str:
    from atelier.discovery import carte

    try:
        return carte.app_courante() or ""
    except Exception:  # noqa: BLE001
        return ""


def rattacher_espace(cle: str, application: str) -> list[dict]:
    """Rattache un espace existant (ancienne politique) à une application."""
    l = tous_espaces()
    e = next((x for x in l if x["projet_jira"] == cle), None)
    if not e:
        raise KeyError(f"Espace inconnu : {cle}")
    e["application"] = application
    _ecrire("espaces.yaml", yaml.safe_dump({"espaces": l}, allow_unicode=True, sort_keys=False))
    _journaliser("politique_espace_rattache", espace=cle, application=application)
    return l


def jql_espace(e: dict, sprint: str | int | None = None) -> str:
    """Sprint donné : tout le backlog du sprint (quel que soit le statut) ; sinon filtre par statuts."""
    parts = [f'project = "{e["projet_jira"]}"']
    if e.get("types_issue"):
        parts.append("issuetype in (" + ", ".join(f'"{t}"' for t in e["types_issue"]) + ")")
    if sprint is not None:
        parts.append(f"sprint = {int(sprint)}" if str(sprint).isdigit() else f"sprint in {sprint}")
    else:
        parts.append("status in (" + ", ".join(f'"{s}"' for s in e["statuts"]) + ")" if e.get("statuts") else "statusCategory != Done")
    if e.get("jql_complement"):
        parts.append(f"({e['jql_complement']})")
    return " AND ".join(parts) + " ORDER BY created DESC"


# =========================================================================== état des US
def _us() -> dict:
    f = _d() / "us.json"
    return json.loads(f.read_text("utf-8")) if f.exists() else {}


def _sauver_us(d: dict):
    _ecrire("us.json", json.dumps(d, ensure_ascii=False, indent=1))


def _exiger(cle: str) -> tuple[dict, dict]:
    d = _us()
    if cle not in d:
        raise KeyError(f"US inconnue : {cle} (lancer la détection).")
    return d, d[cle]


def _changer(u: dict, statut: str, detail: str = ""):
    u.setdefault("historique", []).append({"date": _maintenant(), "auteur": _auteur(), "de": u.get("statut", ""), "vers": statut, "detail": detail})
    u["statut"] = statut


def sprints(espace: str = "", jira=None) -> dict:
    """Sprints (actifs, futurs, fermés récents) des tableaux Scrum de chaque espace ; {projet: [sprints]}."""
    from atelier.integrations.jira import JiraClient

    jira = jira or JiraClient()
    out = {}
    for e in [x for x in espaces() if x.get("actif") and (not espace or x["projet_jira"] == espace)]:
        vus, l = set(), []
        try:
            for t in [b for b in jira.tableaux(e["projet_jira"]) if (b.get("type") or "scrum") == "scrum"]:
                for s in jira.sprints(t["id"]):
                    if s["id"] not in vus:
                        vus.add(s["id"])
                        l.append(s)
        except Exception as ex:  # noqa: BLE001 - API agile indisponible : portée par JQL openSprints()
            out[e["projet_jira"]] = {"erreur": str(ex)[:200], "sprints": []}
            continue
        ordre = {"active": 0, "future": 1, "closed": 2}
        l.sort(key=lambda s: (ordre.get(s["etat"], 3), s["debut"] or "9999") if s["etat"] != "closed" else (2, "".join(chr(255 - ord(c)) for c in (s["fin"] or ""))))
        out[e["projet_jira"]] = {"sprints": [s for s in l if s["etat"] != "closed"] + [s for s in l if s["etat"] == "closed"][:3]}
    return out


def chercher_projets_jira(recherche: str = "", jira=None) -> list[dict]:
    """Aide à la saisie de la politique : projets Jira visibles (nom ou clé), déjà suivis signalés."""
    from atelier.integrations.jira import JiraClient

    jira = jira or JiraClient()
    if not getattr(jira, "enabled", True):
        raise RuntimeError("Jira non configuré (Paramètres › Connexions).")
    suivis = {e["projet_jira"] for e in espaces()}
    return [{**p, "suivi": p["cle"] in suivis} for p in jira.projets(recherche.strip())]


def details_projet_jira(cle: str, jira=None) -> dict:
    """Types de ticket, statuts et tableaux Scrum / sprints du projet choisi (préremplissage, lecture seule)."""
    from atelier.integrations.jira import JiraClient

    jira = jira or JiraClient()
    out = {"cle": cle, "types": [], "statuts": [], "tableaux": [], "sprint_actif": None, "erreurs": []}
    for nom, appel in (("types", lambda: jira.types_issue_projet(cle)), ("statuts", lambda: jira.statuts_projet(cle, "Story")),
                       ("tableaux", lambda: jira.tableaux(cle))):
        try:
            out[nom] = appel()
        except Exception as ex:  # noqa: BLE001 - une information indisponible n'empêche pas la saisie
            out["erreurs"].append(f"{nom} : {str(ex)[:150]}")
    for t in [x for x in out["tableaux"] if (x.get("type") or "scrum") == "scrum"]:
        try:
            out["sprint_actif"] = next((s for s in jira.sprints(t["id"], "active") if s.get("etat") == "active"), None) or out["sprint_actif"]
        except Exception as ex:  # noqa: BLE001
            out["erreurs"].append(f"sprints : {str(ex)[:150]}")
    return out


def _prochain(l: list[dict]) -> dict | None:
    """Prochain sprint : sprint futur qui commence le plus tôt (sinon le plus ancien créé)."""
    futurs = [s for s in l if s["etat"] == "future"]
    return min(futurs, key=lambda s: (s.get("debut") or "9999", s["id"])) if futurs else None


def _jql_backlog(e: dict, hors_sprint: bool) -> str:
    """Backlog : US non terminées de l'espace (types de la politique) ; hors sprint = non planifiées."""
    base = jql_espace({**e, "statuts": [], "jql_complement": e.get("jql_complement", "")}).replace(" ORDER BY created DESC", "")
    return base + (" AND sprint is EMPTY" if hors_sprint else "") + " ORDER BY created DESC"


def _cibles(e: dict, jira, sprint: str = "", portee: str = "", messages: list | None = None) -> list[tuple[str, dict | None]]:
    """Requêtes de détection d'un espace. portee (filtre de détection) prime sur la portée de la politique :
    sprint (actif), sprint_suivant (prochain uniquement), sprint_et_suivant, backlog (entier), hors_sprint, statuts."""
    messages = messages if messages is not None else []
    portee = portee if portee in PORTEES else e.get("portee", "sprint")
    if not sprint:
        if portee == "statuts":
            return [(jql_espace(e), None)]
        if portee in ("backlog", "hors_sprint"):
            return [(_jql_backlog(e, portee == "hors_sprint"), None)]
    sp = sprints(e["projet_jira"], jira).get(e["projet_jira"], {})
    l = sp.get("sprints") or []
    if sprint:
        choisis = [s for s in l if str(s["id"]) == str(sprint)] or [{"id": int(sprint), "nom": f"sprint {sprint}", "etat": ""}]
    else:
        actifs = [s for s in l if s["etat"] == "active"] if portee in ("sprint", "sprint_et_suivant") else []
        prochain = _prochain(l) if portee in ("sprint_suivant", "sprint_et_suivant") else None
        choisis = actifs + ([prochain] if prochain else [])
        if portee in ("sprint_suivant", "sprint_et_suivant") and not prochain and not sp.get("erreur"):
            messages.append(f"{e['projet_jira']} : aucun prochain sprint créé dans Jira.")
        if portee in ("sprint", "sprint_et_suivant") and not actifs and not sp.get("erreur"):
            messages.append(f"{e['projet_jira']} : aucun sprint actif.")
    if not choisis:
        if sp.get("erreur"):
            messages.append(f"{e['projet_jira']} : sprints non lus (API agile), repli JQL.")
            return [(jql_espace(e, "futureSprints()" if portee == "sprint_suivant" else "openSprints()"), None)]
        return []
    return [(jql_espace(e, s["id"]), s) for s in choisis]


def detecter(jira=None, limite: int = 500, sprint: str = "", portee: str = "") -> dict:
    """Lecture seule dans Jira : backlog du (des) sprint(s) visé(s) de chaque espace actif (ou US par statuts), avec
    description, critères et tests déjà liés. Une US sortie d'un sprint perd l'étiquette de ce sprint (tracé)."""
    from atelier.integrations.jira import JiraClient, adf_vers_texte

    jira = jira or JiraClient()
    if not getattr(jira, "enabled", True):
        raise RuntimeError("Jira non configuré (Paramètres › Connexions).")
    champ_crit = os.environ.get("JIRA_CHAMP_CRITERES", "").strip()
    champs = ["summary", "description", "status", "issuelinks", "issuetype", "assignee", "updated"] + ([champ_crit] if champ_crit else [])
    d = _us()
    bilan = {"espaces": 0, "us": 0, "nouvelles": 0, "deja_couvertes": 0, "sprints": [], "retirees": 0, "messages": [],
             "portee": PORTEES.get(portee, "selon la politique de chaque espace")}
    for e in [x for x in espaces() if x.get("actif")]:
        bilan["espaces"] += 1
        for jql, sp in _cibles(e, jira, sprint, portee, bilan["messages"]):
            if sp:
                bilan["sprints"].append(f"{e['projet_jira']} · {sp['nom']}")
            trouvees = set()
            for i in jira.rechercher(jql, champs, limite):
                trouvees.add(i["key"])
                _integrer(d, i, e, sp, champ_crit, adf_vers_texte, bilan)
            if sp:  # US qui ne sont plus dans le backlog de ce sprint
                for u in d.values():
                    if u["espace"] == e["projet_jira"] and str(sp["id"]) in (u.get("sprints") or {}) and u["cle"] not in trouvees:
                        u["sprints"].pop(str(sp["id"]))
                        u.setdefault("historique", []).append({"date": _maintenant(), "auteur": _auteur(), "de": u["statut"], "vers": u["statut"],
                                                               "detail": f"retirée du sprint {sp['nom']}"})
                        bilan["retirees"] += 1
    _sauver_us(d)
    _journaliser("detection", **{k: (", ".join(v) if isinstance(v, list) else v) for k, v in bilan.items()})
    if not bilan["us"] and not bilan["messages"]:
        bilan["messages"].append("Aucune US trouvée pour cette portée.")
    return {**bilan, "file": file(sprint=sprint)}


def _integrer(d: dict, i: dict, e: dict, sp: dict | None, champ_crit: str, adf_vers_texte, bilan: dict):
    """Fusionne une US lue dans Jira dans l'état local (création, mise à jour, couverture existante, sprint)."""
    f = i.get("fields") or {}
    tests_lies, ignores = liens_de_test(f.get("issuelinks") or [])
    crit = f.get(champ_crit) if champ_crit else None
    u = d.get(i["key"])
    base = {"cle": i["key"], "espace": e["projet_jira"], "resume": f.get("summary") or "",
            "description": adf_vers_texte(f.get("description")), "criteres_jira": adf_vers_texte(crit) if crit else "",
            "statut_jira": (f.get("status") or {}).get("name", ""), "assigne": ((f.get("assignee") or {}).get("displayName") or ""),
            "maj_jira": f.get("updated", ""), "tests_lies": tests_lies, "liens_ignores": ignores}
    if u is None:
        u = {**base, "statut": "", "historique": [], "constats": [], "questions": {}, "cas": []}
        _changer(u, "Couverte (existant)" if len(tests_lies) >= e["min_tests"] else "Détectée",
                 f"{len(tests_lies)} test(s) déjà lié(s)" if tests_lies else "")
        bilan["nouvelles"] += 1
    else:
        modifiee = u.get("maj_jira") and base["maj_jira"] != u.get("maj_jira")
        u.update(base)
        if modifiee and u["statut"] not in ("Détectée", "Non testable"):
            u.setdefault("alertes", []).append({"date": _maintenant(), "message": "US modifiée dans Jira depuis l'analyse : à revoir."})
        if len(tests_lies) >= e["min_tests"] and u["statut"] in ("Détectée", "Analysée"):
            _changer(u, "Couverte (existant)", f"{len(tests_lies)} test(s) lié(s) dans Jira")
    if sp:
        u.setdefault("sprints", {})[str(sp["id"])] = {"nom": sp["nom"], "etat": sp.get("etat", "")}
    bilan["deja_couvertes"] += u["statut"].startswith("Couverte")
    bilan["us"] += 1
    d[i["key"]] = u


def importer_exigence(e: dict) -> dict:
    """Exigence sans test venue de Coverage Intelligence → file « US à couvrir » de Test Design (même workflow :
    cas proposés, revus, validés, puis publiés dans Xray selon le mapping). Ne touche pas une US déjà suivie."""
    d = _us()
    cle = e["cle"]
    if cle not in d:
        u = {"cle": cle, "espace": cle.split("-")[0], "resume": e.get("resume", ""), "description": e.get("description", ""),
             "criteres_jira": "\n".join(f"- {c}" for c in e.get("criteres") or []), "statut_jira": e.get("statut_jira", ""), "assigne": "",
             "maj_jira": "", "tests_lies": e.get("tests_lies") or [], "liens_ignores": [], "statut": "", "historique": [], "constats": [],
             "questions": {}, "cas": [], "origine": "Coverage Intelligence"}
        _changer(u, "Détectée", "exigence sans test (Coverage Intelligence)")
        d[cle] = u
        _sauver_us(d)
        _journaliser("import_exigence", cle=cle, source="Coverage Intelligence")
    return d[cle]


def types_test() -> set[str]:
    """Nom(s) du type de ticket Test de Xray (XRAY_TEST_ISSUE_TYPE, virgules ; défaut « Test »), en minuscules."""
    return {t.strip().lower() for t in (os.environ.get("XRAY_TEST_ISSUE_TYPE") or "Test").split(",") if t.strip()}


def liens_de_test(issuelinks: list[dict]) -> tuple[list[str], list[dict]]:
    """Couverture réelle d'une US : seuls comptent les tickets liés dont le TYPE est Test (Xray), quel que soit le nom
    du lien. Un « is tested by » vers une Task, un Bug, une Test Execution… n'est pas une couverture : il est ignoré
    et signalé. Un ticket lié dont le type n'est pas renvoyé par Jira n'est jamais compté."""
    tests, ignores, types = set(), [], types_test()
    for l in issuelinks or []:
        cible = l.get("outwardIssue") or l.get("inwardIssue") or {}
        if not cible.get("key"):
            continue
        type_cible = (((cible.get("fields") or {}).get("issuetype") or {}).get("name") or "")
        lien = (l.get("type") or {}).get("name") or ""
        if type_cible.lower() in types:
            tests.add(cible["key"])
        elif "test" in lien.lower() or "test" in type_cible.lower():  # piège : lien « test » vers autre chose qu'un Test
            ignores.append({"cle": cible["key"], "type": type_cible or "inconnu", "lien": lien,
                            "raison": "ticket lié qui n'est pas un Test Xray : ne couvre pas l'US"})
    return sorted(tests), ignores


def _dans(u: dict, sprint: str) -> bool:
    return not sprint or str(sprint) in (u.get("sprints") or {})


def file(espace: str = "", statut: str = "", sprint: str = "") -> list[dict]:
    mes_espaces = {e["projet_jira"] for e in espaces()}  # US des espaces de l'application active
    return [{k: u.get(k) for k in ("cle", "espace", "resume", "statut", "statut_jira", "assigne", "tests_lies")}
            | {"constats": len(u.get("constats") or []), "cas": len(u.get("cas") or []), "alertes": len(u.get("alertes") or []),
               "sprints": [s["nom"] for s in (u.get("sprints") or {}).values()]}
            for u in _us().values() if u["espace"] in mes_espaces and (not espace or u["espace"] == espace)
            and (not statut or u["statut"] == statut) and _dans(u, sprint)]


# =========================================================================== périmètre figé et bilan de sprint
def _fichier_sprint(espace: str, sprint: str):
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,19}", espace or "") or not str(sprint).isdigit():
        raise ValueError("Espace et identifiant de sprint attendus.")
    return _d() / "sprints" / f"{espace}-{int(sprint)}.json"


def figer_sprint(espace: str, sprint: str) -> dict:
    """Photo immuable du backlog du sprint au démarrage (création exclusive : jamais réécrite)."""
    us_ = [u for u in _us().values() if u["espace"] == espace and _dans(u, sprint)]
    if not us_:
        raise ValueError("Aucune US connue pour ce sprint : lancer d'abord la détection du sprint.")
    f = _fichier_sprint(espace, sprint)
    f.parent.mkdir(parents=True, exist_ok=True)
    nom = next(iter(u["sprints"][str(sprint)]["nom"] for u in us_))
    photo = {"espace": espace, "sprint": str(sprint), "nom": nom, "date": _maintenant(), "auteur": _auteur(),
             "us": {u["cle"]: {"resume": u["resume"], "statut": u["statut"], "tests": len(u.get("tests_lies") or [])} for u in us_}}
    try:
        with f.open("x", encoding="utf-8") as fh:
            fh.write(json.dumps(photo, ensure_ascii=False, indent=1))
    except FileExistsError:
        raise FileExistsError(f"Périmètre du sprint {nom} déjà figé (photo immuable).") from None
    _journaliser("sprint_fige", espace=espace, sprint=str(sprint), us=len(us_))
    return bilan_sprint(espace, sprint)


def bilan_sprint(espace: str, sprint: str) -> dict:
    """Couverture du backlog du sprint et écart avec le périmètre figé (US ajoutées / retirées en cours de sprint)."""
    from collections import Counter

    f = _fichier_sprint(espace, sprint)
    photo = json.loads(f.read_text("utf-8")) if f.exists() else None
    us_ = {u["cle"]: u for u in _us().values() if u["espace"] == espace and _dans(u, sprint)}
    st = Counter(u["statut"] for u in us_.values())
    tot = len(us_)
    couvertes = sum(u["statut"].startswith("Couverte") for u in us_.values())
    nom = photo["nom"] if photo else next((u["sprints"][str(sprint)]["nom"] for u in us_.values()), f"sprint {sprint}")
    return {"espace": espace, "sprint": str(sprint), "nom": nom, "us": tot, "par_statut": dict(st),
            "couvertes": couvertes, "taux_couverture": round(100 * couvertes / tot, 1) if tot else None,
            "analysees": sum(u["statut"] not in ("Détectée",) for u in us_.values()),
            "en_attente_reponse": st.get("Questions envoyées", 0), "non_testables": st.get("Non testable", 0),
            "tests_crees": sum(1 for u in us_.values() for c in u.get("cas") or [] if c["statut"] == "Publié"),
            "non_couvertes": sorted(k for k, u in us_.items() if not u["statut"].startswith("Couverte") and u["statut"] != "Non testable"),
            "fige": {"date": photo["date"], "auteur": photo["auteur"], "us": len(photo["us"])} if photo else None,
            "ajoutees": sorted(set(us_) - set(photo["us"])) if photo else [],
            "retirees": sorted(set(photo["us"]) - set(us_)) if photo else []}


def detail(cle: str) -> dict:
    _, u = _exiger(cle)
    e = next((x for x in tous_espaces() if x["projet_jira"] == u["espace"]), {})
    cas = [{**c, "verification": {"manuel": verifier_cas(c, "Manual"), "bdd": verifier_cas(c, "Cucumber")},
            "format_publication": e.get("type_test") or "Manual"} for c in u.get("cas") or []]
    return {**u, "cas": cas, "politique": e, "journal": journal(cle, 50)}


# =========================================================================== deux formats d'un cas : BDD et étapes manuelles
_MOTS = {"given": "given", "étant donné": "given", "etant donne": "given", "soit": "given", "when": "when", "quand": "when",
         "lorsque": "when", "then": "then", "alors": "then", "and": "and", "et": "and", "but": "and", "mais": "and"}
_RE_LIGNE = re.compile(r"^\s*(" + "|".join(sorted(map(re.escape, _MOTS), key=len, reverse=True)) + r")\b\s*(.*)$", re.I)
_A_PRECISER = re.compile(r"\.\.\.|à préciser|a preciser|\(à compléter|à compléter", re.I)


def lignes_gherkin(g: str) -> list[tuple[str, str]]:
    """[(type effectif given|when|then, texte)] ; « Et / Mais » prennent le type de la ligne précédente."""
    out, courant = [], "given"
    for brut in (g or "").splitlines():
        m = _RE_LIGNE.match(brut)
        if not m:
            continue
        t = _MOTS[m.group(1).lower()]
        courant = courant if t == "and" else t
        out.append((courant, m.group(2).strip()))
    return out


def gherkin_vers_etapes(g: str) -> list[dict]:
    """Given → prérequis ; When → action ; Then → résultat attendu de l'action précédente."""
    etapes = []
    for t, texte in lignes_gherkin(g):
        if t == "given":
            etapes.append({"action": f"Prérequis : {texte}", "donnees": "", "resultat": ""})
        elif t == "when":
            etapes.append({"action": texte, "donnees": "", "resultat": ""})
        else:
            if etapes and not etapes[-1]["action"].startswith("Prérequis"):
                etapes[-1]["resultat"] = (etapes[-1]["resultat"] + " ; " if etapes[-1]["resultat"] else "") + texte
            else:
                etapes.append({"action": "Vérifier", "donnees": "", "resultat": texte})
    return etapes


def etapes_vers_gherkin(etapes: list[dict]) -> str:
    lignes, precedent = [], ""
    for e in etapes or []:
        action, res = (e.get("action") or "").strip(), (e.get("resultat") or "").strip()
        if action.lower().startswith("prérequis"):
            lignes.append(("And" if precedent == "given" else "Given") + " " + action.split(":", 1)[-1].strip())
            precedent = "given"
            continue
        if action:
            if e.get("donnees"):
                action += " avec les données du jeu"
            lignes.append(("And" if precedent == "when" else "When") + " " + action)
            precedent = "when"
        if res:
            lignes.append(("And" if precedent == "then" else "Then") + " " + res)
            precedent = "then"
    if lignes and not lignes[0].startswith("Given"):
        lignes.insert(0, "Given le contexte de l'US est en place")
    return "\n".join(lignes)


def verifier_cas(c: dict, type_test: str) -> list[str]:
    """Problèmes qui empêchent de publier le cas dans ce format (vide = prêt)."""
    if type_test == "Cucumber":
        g = (c.get("gherkin") or "").strip()
        if not g:
            return ["Gherkin vide."]
        types = [t for t, _ in lignes_gherkin(g)]
        pb = [f"Aucune étape « {lib} »." for t, lib in (("given", "Étant donné / Given"), ("when", "Quand / When"), ("then", "Alors / Then")) if t not in types]
        if _A_PRECISER.search(g):
            pb.append("Gherkin encore générique (« ... » ou « à préciser »).")
        return pb
    etapes = c.get("etapes") or []
    if not etapes:
        return ["Aucune étape."]
    pb = []
    for i, e in enumerate(etapes, 1):
        if not (e.get("action") or "").strip():
            pb.append(f"Étape {i} : action vide.")
        prerequis = (e.get("action") or "").lower().startswith("prérequis")
        if not prerequis and (not (e.get("resultat") or "").strip() or _A_PRECISER.search(e.get("resultat") or "")):
            pb.append(f"Étape {i} : résultat attendu à préciser.")
        if _A_PRECISER.search(e.get("action") or ""):
            pb.append(f"Étape {i} : action à compléter.")
    return pb


def convertir_cas(cle: str, cid: str, vers: str) -> dict:
    """Génère un format depuis l'autre : vers « etapes » (depuis le Gherkin) ou « gherkin » (depuis les étapes)."""
    _, u = _exiger(cle)
    c = next((x for x in u.get("cas") or [] if x["id"] == cid), None)
    if not c:
        raise KeyError(f"Cas inconnu : {cid}")
    if vers == "etapes":
        if not lignes_gherkin(c.get("gherkin")):
            raise ValueError("Gherkin vide : rien à convertir.")
        return modifier_cas(cle, cid, {"etapes": gherkin_vers_etapes(c["gherkin"])})
    if vers == "gherkin":
        if not c.get("etapes"):
            raise ValueError("Aucune étape : rien à convertir.")
        return modifier_cas(cle, cid, {"gherkin": etapes_vers_gherkin(c["etapes"])})
    raise ValueError("Conversion : etapes ou gherkin.")


def indicateurs(sprint: str = "") -> dict:
    from collections import Counter

    d = [u for u in _us().values() if _dans(u, sprint)]
    par_espace: dict = {}
    for u in d:
        par_espace.setdefault(u["espace"], Counter())[u["statut"]] += 1
    tot = len(d)
    couvertes = sum(u["statut"].startswith("Couverte") for u in d)
    return {"us": tot, "couvertes": couvertes, "taux_couverture": round(100 * couvertes / tot, 1) if tot else None,
            "en_attente_reponse": sum(u["statut"] == "Questions envoyées" for u in d),
            "non_testables": sum(u["statut"] == "Non testable" for u in d),
            "par_espace": {k: dict(v) for k, v in par_espace.items()}}


# =========================================================================== analyse
def _texte(u: dict) -> str:
    return "\n".join(x for x in (u.get("resume"), u.get("description"), u.get("criteres_jira")) if x)


def _criteres(u: dict) -> list[str]:
    from atelier.discovery.intelligence_app import criteres

    l = criteres({"description": "\n".join(x for x in (u.get("description"), u.get("criteres_jira")) if x)})
    return l


def regles(u: dict) -> list[dict]:
    """Constats explicables : chaque constat cite la règle et, si possible, l'extrait concerné."""
    t = _texte(u)
    bas = t.lower()
    out = []
    add = lambda code, gravite, message, extrait="", question="": out.append(  # noqa: E731
        {"code": code, "gravite": gravite, "message": message, "extrait": extrait, "question": question, "source": "règles"})
    crit = _criteres(u)
    if len((u.get("description") or "").split()) < 15:
        add("description_courte", "haute", "Description trop courte pour en déduire le comportement attendu.",
            question="Pouvez-vous décrire le comportement attendu (point de départ, action, résultat) ?")
    if not crit:
        add("sans_criteres", "haute", "Aucun critère d'acceptation identifiable (liste à puces ou champ dédié).",
            question="Quels sont les critères d'acceptation de cette US ?")
    vagues = sorted({m for m in TERMES_VAGUES if re.search(r"(?<!\w)" + re.escape(m) + r"(?!\w)", bas)})
    if vagues:
        ext = next((l for l in t.splitlines() if any(v in l.lower() for v in vagues)), "")
        add("termes_vagues", "moyenne", f"Termes non mesurables : {', '.join(vagues)}.", ext.strip()[:200],
            f"Pouvez-vous préciser de façon mesurable : {', '.join(vagues)} ?")
    m = A_DEFINIR.search(t)
    if m:
        add("a_definir", "haute", "Éléments encore à définir dans l'US.", t[max(0, m.start() - 60): m.end() + 60].strip(),
            "Les points marqués « à définir » ont-ils été tranchés ?")
    if not CAS_ERREUR.search(t):
        add("sans_cas_erreur", "moyenne", "Aucun cas d'erreur ou de refus décrit.",
            question="Quel est le comportement attendu en cas d'erreur, de donnée invalide ou de refus ?")
    if not DONNEES.search(t):
        add("sans_donnees", "basse", "Aucune donnée, règle de format ou limite mentionnée.",
            question="Y a-t-il des règles sur les données (formats, limites, plafonds, valeurs par défaut) ?")
    if not ROLES.search(t):
        add("sans_role", "basse", "Profil ou rôle de l'utilisateur non précisé.",
            question="Quels profils ou rôles sont concernés par cette US ?")
    return out


def analyser(cle: str) -> dict:
    """Analyse par règles (toujours) ; propositions de questions à relire avant envoi."""
    d, u = _exiger(cle)
    u["constats"] = [c for c in (u.get("constats") or []) if c.get("source") != "règles"] + regles(u)
    from atelier.discovery.intelligence_app import structurer

    u["criteres_structures"] = [structurer(c) for c in _criteres(u)]
    u.setdefault("questions", {})["brouillon"] = _brouillon(u)
    if u["statut"] in ("Détectée", "Analysée"):
        _changer(u, "Analysée", f"{len(u['constats'])} constat(s)")
    _sauver_us(d)
    _journaliser("analyse", cle=cle, constats=len(u["constats"]), source="règles")
    return detail(cle)


def _brouillon(u: dict) -> str:
    qs = [c["question"] for c in u.get("constats") or [] if c.get("question")]
    qs = list(dict.fromkeys(qs))
    if not qs:
        return ""
    return "Bonjour,\nPour préparer les tests de cette US, pouvez-vous préciser :\n" + "\n".join(f"- {q}" for q in qs) + "\nMerci."


SYSTEME_ANALYSE = ("Tu es testeur QA. Tu analyses une User Story pour la rendre testable. Réponds UNIQUEMENT en JSON : "
                   '{"constats": [{"gravite": "haute|moyenne|basse", "message": "...", "extrait": "...", "question": "..."}], '
                   '"cas": [{"titre": "...", "etapes": [{"action": "...", "donnees": "...", "resultat": "..."}], "gherkin": "..."}]}. '
                   "N'invente aucune règle métier : une information absente devient une question. En français.")


def _masque(t: str) -> str:
    from atelier.execution.echecs import masquer_texte

    return masquer_texte(t, [])


def analyser_ia(cle: str) -> dict:
    """Analyse et cas proposés par le LLM interne ou Claude (selon IA_FOURNISSEUR) ; texte masqué avant envoi.
    Avec « cursor », l'atelier n'appelle rien : l'agent Cursor dépose ses propositions (deposer_proposition)."""
    from atelier.intelligence import fournisseur_ia as ia

    d, u = _exiger(cle)
    if ia.fournisseur() == "cursor":
        return {"disponible": False, "raison": "Fournisseur « cursor » : demander à l'agent Cursor d'analyser l'US via les outils MCP "
                                               "testabilite_us_a_traiter puis testabilite_deposer_proposition."}
    if not ia.configure():
        return {"disponible": False, "raison": f"IA « {ia.fournisseur()} » non disponible : analyse par règles uniquement."}
    envoye = _masque(f"US {u['cle']} : {u['resume']}\n\nDescription :\n{u.get('description', '')}\n\nCritères :\n{u.get('criteres_jira', '')}"
                     + ("\n\nRéponses de l'équipe :\n" + "\n".join(r["texte"] for r in (u.get("questions") or {}).get("reponses", []))
                        if (u.get("questions") or {}).get("reponses") else ""))
    brut = ia.completer(SYSTEME_ANALYSE, envoye, 2500)
    try:
        prop = ia.extraire_json(brut)
    except ValueError:
        prop = {"constats": [], "cas": []}
    return deposer_proposition(cle, prop.get("constats") or [], prop.get("cas") or [], f"IA {ia.fournisseur()} ({ia.modele()})",
                               contexte_envoye=envoye, _d=d)


def deposer_proposition(cle: str, constats: list[dict], cas: list[dict], source: str = "Cursor", contexte_envoye: str = "", _d=None) -> dict:
    """Propositions d'une IA (Cursor via le MCP, LLM interne) : constats et cas « Proposé », jamais appliqués sans validation."""
    d = _d if _d is not None else _us()
    if cle not in d:
        raise KeyError(f"US inconnue : {cle}")
    u = d[cle]
    for c in constats:
        if c.get("message"):
            u.setdefault("constats", []).append({"code": "ia", "gravite": c.get("gravite") or "moyenne", "message": str(c["message"])[:500],
                                                 "extrait": str(c.get("extrait") or "")[:300], "question": str(c.get("question") or "")[:400], "source": source})
    for c in cas:
        _ajouter_cas(u, c, source)
    u.setdefault("questions", {})["brouillon"] = _brouillon(u)
    if u["statut"] == "Détectée":
        _changer(u, "Analysée", f"propositions {source}")
    if cas and u["statut"] in ("Analysée", "Réponses reçues"):
        _changer(u, "Cas proposés", f"{len(cas)} cas proposé(s) par {source}")
    _sauver_us(d)
    _journaliser("proposition_ia", cle=cle, source=source, constats=len(constats), cas=len(cas), contexte_envoye=contexte_envoye[:4000])
    return detail(cle)


# =========================================================================== questions dans Jira
def modifier_questions(cle: str, texte: str) -> dict:
    d, u = _exiger(cle)
    u.setdefault("questions", {})["brouillon"] = texte.strip()
    _sauver_us(d)
    return detail(cle)


def envoyer_questions(cle: str, jira=None) -> dict:
    """Commentaire Jira sur l'US, uniquement sur action explicite après relecture du brouillon."""
    from atelier.integrations.jira import JiraClient

    d, u = _exiger(cle)
    texte = ((u.get("questions") or {}).get("brouillon") or "").strip()
    if not texte:
        raise ValueError("Aucune question à envoyer (analyser l'US ou rédiger les questions).")
    jira = jira or JiraClient()
    r = jira.commenter(cle, f"{MARQUEUR}\n{texte}")
    u["questions"].setdefault("envois", []).append({"date": _maintenant(), "date_jira": r.get("date") or "", "auteur": _auteur(), "commentaire_id": r.get("id"),
                                                    "auteur_jira": r.get("auteur_id"), "texte": texte})
    _changer(u, "Questions envoyées", f"commentaire {r.get('id')}")
    _sauver_us(d)
    _journaliser("questions_envoyees", cle=cle, commentaire=r.get("id"))
    return detail(cle)


def _instant(s: str) -> datetime:
    """Date Jira (« 2026-11-14T16:58:07.123+0000 ») ou de l'atelier (ISO avec « +00:00 »), comparable."""
    s = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", str(s).strip()).replace("Z", "+00:00")
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.astimezone()


def relever_reponses(cle: str = "", jira=None) -> dict:
    """Lecture seule : commentaires publiés après le dernier envoi de questions, hors ceux de l'atelier."""
    from atelier.integrations.jira import JiraClient

    jira = jira or JiraClient()
    d = _us()
    nouvelles = 0
    for k, u in d.items():
        envois = (u.get("questions") or {}).get("envois") or []
        if (cle and k != cle) or not envois:
            continue
        dernier = envois[-1]
        nos_ids = {e.get("commentaire_id") for e in envois}
        connues = {r["id"] for r in u["questions"].get("reponses", [])}
        for c in jira.commentaires(k):
            if c["id"] in nos_ids or c["id"] in connues or MARQUEUR in c["texte"] or _instant(c["date"]) <= _instant(dernier.get("date_jira") or dernier["date"]):  # horloge de Jira
                continue
            u["questions"].setdefault("reponses", []).append(c)
            nouvelles += 1
            if u["statut"] == "Questions envoyées":
                _changer(u, "Réponses reçues", f"réponse de {c['auteur']}")
    _sauver_us(d)
    _journaliser("releve_reponses", cle=cle, nouvelles=nouvelles)
    return {"nouvelles": nouvelles, "file": file()}


# =========================================================================== cas de test
def _ajouter_cas(u: dict, c: dict, source: str) -> dict:
    etapes = [{"action": str(e.get("action") or ""), "donnees": str(e.get("donnees") or e.get("data") or ""),
               "resultat": str(e.get("resultat") or e.get("result") or "")} for e in c.get("etapes") or []]
    cas = {"id": "C" + secrets.token_hex(3), "titre": str(c.get("titre") or u["resume"])[:250], "etapes": etapes,
           "gherkin": str(c.get("gherkin") or ""), "statut": "Proposé", "source": source, "date": _maintenant(), "cle_xray": ""}
    u.setdefault("cas", []).append(cas)
    return cas


def proposer_cas(cle: str) -> dict:
    """Cas squelettes par règles : un cas par critère d'acceptation (condition / action / résultat), plus un cas d'erreur
    si l'US n'en décrit pas. Les réponses de l'équipe sont jointes en note du premier cas. À compléter et valider."""
    d, u = _exiger(cle)
    from atelier.discovery.intelligence_app import structurer

    crit = _criteres(u)
    nouveaux = []
    for n, c in enumerate(crit, 1):
        s = structurer(c)
        etapes = ([{"action": f"Prérequis : {s['condition']}", "donnees": "", "resultat": ""}] if s["condition"] else []) + \
                 [{"action": s["action"] or c, "donnees": "", "resultat": s["resultat"] or "à préciser"}]
        g = "\n".join(x for x in (f"Given {s['condition']}" if s["condition"] else "Given le contexte de l'US est en place",
                                  f"When {s['action'] or c}", f"Then {s['resultat'] or 'le résultat attendu (à préciser)'}") if x)
        nouveaux.append(_ajouter_cas(u, {"titre": f"{u['resume'][:180]} — critère {n}", "etapes": etapes, "gherkin": g}, "règles"))
    if not crit:
        nouveaux.append(_ajouter_cas(u, {"titre": f"{u['resume'][:200]} — cas nominal", "etapes": [
            {"action": "À compléter depuis l'US et les réponses de l'équipe", "donnees": "", "resultat": "à préciser"}],
            "gherkin": "Given ...\nWhen ...\nThen ..."}, "règles"))
    if not CAS_ERREUR.search(_texte(u)):
        nouveaux.append(_ajouter_cas(u, {"titre": f"{u['resume'][:180]} — cas d'erreur", "etapes": [
            {"action": "Reproduire le parcours avec une donnée invalide", "donnees": "", "resultat": "Refus explicite (comportement à confirmer)"}],
            "gherkin": "Given le contexte de l'US est en place\nWhen la donnée saisie est invalide\nThen l'opération est refusée"}, "règles"))
    reps = (u.get("questions") or {}).get("reponses") or []
    if reps and nouveaux:
        nouveaux[0]["notes"] = "Réponses de l'équipe : " + " | ".join(f"{r['auteur']} : {r['texte'][:300]}" for r in reps)
    if u["statut"] in ("Détectée", "Analysée", "Réponses reçues", "Questions envoyées"):
        _changer(u, "Cas proposés", f"{len(nouveaux)} cas squelette(s) par règles")
    _sauver_us(d)
    _journaliser("cas_proposes", cle=cle, nombre=len(nouveaux), source="règles")
    return detail(cle)


def modifier_cas(cle: str, cid: str, champs: dict) -> dict:
    d, u = _exiger(cle)
    c = next((x for x in u["cas"] if x["id"] == cid), None)
    if not c:
        raise KeyError(f"Cas inconnu : {cid}")
    if c["statut"] == "Publié":
        raise PermissionError("Cas déjà publié dans Xray : le modifier dans Xray (Test Design).")
    for k in ("titre", "gherkin"):
        if k in champs:
            c[k] = str(champs[k])
    if "etapes" in champs:
        c["etapes"] = [{"action": str(e.get("action") or ""), "donnees": str(e.get("donnees") or ""), "resultat": str(e.get("resultat") or "")}
                       for e in champs["etapes"]]
    if c["statut"] == "Validé":
        c["statut"] = "Proposé"  # toute modification d'un cas validé demande une nouvelle validation
    _sauver_us(d)
    return detail(cle)


def decider_cas(cle: str, cid: str, decision: str, motif: str = "") -> dict:
    d, u = _exiger(cle)
    c = next((x for x in u["cas"] if x["id"] == cid), None)
    if not c:
        raise KeyError(f"Cas inconnu : {cid}")
    if decision not in ("valider", "rejeter"):
        raise ValueError("Décision : valider ou rejeter.")
    if c["statut"] == "Publié":
        raise PermissionError("Cas déjà publié.")
    if decision == "rejeter" and not motif.strip():
        raise ValueError("Un rejet doit être motivé.")
    if decision == "valider":  # vérifié dans le format qui sera publié (type de test de l'espace)
        e = next((x for x in tous_espaces() if x["projet_jira"] == u["espace"]), {})
        pb = verifier_cas(c, e.get("type_test") or "Manual")
        if pb:
            raise ValueError(f"Cas non prêt ({'BDD' if e.get('type_test') == 'Cucumber' else 'étapes manuelles'}) : " + " ".join(pb))
    c["statut"], c["decision"] = ("Validé" if decision == "valider" else "Rejeté"), {"par": _auteur(), "date": _maintenant(), "motif": motif.strip()}
    _sauver_us(d)
    _journaliser("cas_" + decision, cle=cle, cas=cid, motif=motif.strip())
    return detail(cle)


def publier_cas(cle: str, xray=None, jira=None) -> dict:
    """Crée dans Xray les cas validés (type de l'espace : Manual avec étapes, ou Cucumber) et les lie à l'US (lien de
    couverture JIRA_LIEN_COUVERTURE, défaut « Test »). Une erreur sur un cas n'empêche pas les autres ; tout est historisé."""
    from atelier.integrations.jira import JiraClient
    from atelier.integrations.xray import XrayClient

    d, u = _exiger(cle)
    e = next((x for x in tous_espaces() if x["projet_jira"] == u["espace"]), None)
    if not e:
        raise ValueError(f"Espace {u['espace']} retiré de la politique.")
    a_publier = [c for c in u["cas"] if c["statut"] == "Validé"]
    if not a_publier:
        raise ValueError("Aucun cas validé à publier.")
    xray, jira = xray or XrayClient(), jira or JiraClient()
    lien = os.environ.get("JIRA_LIEN_COUVERTURE", "Test")
    publies, erreurs = [], []
    for c in a_publier:
        try:
            if e["type_test"] == "Cucumber":
                if not c["gherkin"].strip():
                    raise ValueError("Gherkin vide.")
                r = xray.creer_test_cucumber(e["projet_xray"], c["titre"], c["gherkin"])
            else:
                if not c["etapes"]:
                    raise ValueError("Aucune étape.")
                r = xray.creer_test_manuel(e["projet_xray"], c["titre"], c["etapes"])
            c["cle_xray"], c["statut"] = r["cle"], "Publié"
            try:
                jira.link(r["cle"], cle, lien)  # « <test> tests <US> » : sens à confirmer à l'essai réel
            except Exception as le:  # noqa: BLE001 - test créé : l'absence de lien est signalée, pas annulée
                c["avertissement"] = f"lien de couverture non créé : {str(le)[:200]}"
            publies.append(r["cle"])
        except Exception as ex:  # noqa: BLE001
            erreurs.append({"cas": c["id"], "erreur": str(ex)[:300]})
    u["tests_lies"] = sorted(set(u.get("tests_lies") or []) | set(publies))
    if len(u["tests_lies"]) >= e["min_tests"]:
        _changer(u, "Couverte", f"{len(publies)} test(s) créé(s) : {', '.join(publies)}")
    _sauver_us(d)
    _journaliser("publication_xray", cle=cle, tests=", ".join(publies), erreurs=len(erreurs))
    return {**detail(cle), "publies": publies, "erreurs": erreurs}


def non_testable(cle: str, justification: str) -> dict:
    if len(justification.strip()) < 10:
        raise ValueError("Justification obligatoire (10 caractères au moins).")
    d, u = _exiger(cle)
    _changer(u, "Non testable", justification.strip())
    _sauver_us(d)
    _journaliser("non_testable", cle=cle, justification=justification.strip())
    return detail(cle)


def a_traiter(limite: int = 20) -> list[dict]:
    """Pour l'agent Cursor (MCP) : US à analyser, avec leur texte masqué."""
    out = []
    for u in _us().values():
        if u["statut"] in ("Détectée", "Analysée", "Réponses reçues"):
            out.append({"cle": u["cle"], "statut": u["statut"], "resume": u["resume"],
                        "texte": _masque(_texte(u)), "reponses": [_masque(r["texte"]) for r in (u.get("questions") or {}).get("reponses", [])]})
    return out[:limite]
