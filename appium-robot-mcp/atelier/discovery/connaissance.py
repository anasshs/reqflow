"""Application Knowledge Graph : toute la connaissance de l'application dans un seul graphe.

Sources (provenance « observé ») :
  - la carte (app_map/) : application, plateformes, build, modules, écrans, locators, navigation,
    tests Xray passés par chaque écran ;
  - le dépôt Robot : suites, tests, keywords, fichiers resource, locators, JDD, bibliothèques ;
  - les JDD (data/jdd) : requêtes Oracle en prérequis ;
  - l'instantané du patrimoine Xray / Jira : modules, epics, user stories, tests, plans, exécutions ;
  - les derniers output.xml : statut des tests Robot.
Puis la connaissance déclarée par l'automaticien (atelier/domain/declarations.py).

Identifiants : « <type>:<clé> », ex. ecran:virement_saisie, locator:virement_saisie.champ_montant@android,
test:DEMO-1, test_robot:tests/virement.robot::Virement Nominal, keyword:saisirlemontant.
"""
from __future__ import annotations

import hashlib
import os
import posixpath
import pickle
import re
import threading
import time
from pathlib import Path

from atelier.domain import declarations, projet
from atelier.domain.graphe import Graphe

# Relations suivies vers l'amont pour trouver qui dépend d'un élément modifié.
RELATIONS_DEPENDANCE = {"appelle", "utilise", "depend_de"}


# =========================================================================== cache du graphe
# Le graphe se reconstruit depuis les fichiers du projet (carte, dépôt Robot, JDD, instantané Xray, résultats,
# déclarations…) : 1 à 3 s, et un écran l'appelait plusieurs fois. Il est gardé tant que l'empreinte du projet
# (chemin, taille et date de modification de chaque fichier) ne change pas. Prudence liée au pas de la date de
# modification (~15 ms sous Windows) : si un fichier a été modifié il y a moins de STABILITE_S secondes, le cache
# n'est pas utilisé (une seconde écriture rapprochée pourrait ne pas changer la date). Chaque appel reçoit sa propre
# copie du graphe (pickle) : les appelants peuvent la modifier librement.
DOSSIERS_IGNORES = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mcp_snapshots", ".idea", ".vscode"}
VARIABLES = ("APP_MAP_DIR", "CONNAISSANCE_DIR", "PATRIMOINE_FICHIER", "MAP_SEUIL_SIMILARITE", "ATELIER_PROJETS")
STABILITE_S = 2.0
_CACHE_GRAPHE: dict = {}
_VERROU_GRAPHE = threading.Lock()


def _empreinte_projet() -> tuple[str, float]:
    """(empreinte des fichiers du projet et des réglages qui influencent le graphe, date de modification la plus récente)."""
    racine = projet.PROJECT_DIR
    h = hashlib.blake2b(digest_size=16)
    h.update(str(racine).encode())
    for v in VARIABLES:
        h.update(f"|{v}={os.environ.get(v, '')}".encode())
    recent = 0.0
    projets_f = Path(os.environ.get("ATELIER_PROJETS", Path.home() / ".atelier-projets.json")).expanduser()
    for r, ds, fs in os.walk(racine):
        ds[:] = sorted(d for d in ds if d not in DOSSIERS_IGNORES)
        for nom in sorted(fs):
            p = os.path.join(r, nom)
            try:
                st = os.stat(p)
            except OSError:
                continue
            h.update(f"\n{p}|{st.st_size}|{st.st_mtime_ns}".encode())
            recent = max(recent, st.st_mtime)
    try:
        st = projets_f.stat()
        h.update(f"\n{projets_f}|{st.st_size}|{st.st_mtime_ns}".encode())
    except OSError:
        pass
    return h.hexdigest(), recent


def vider_cache():
    with _VERROU_GRAPHE:
        _CACHE_GRAPHE.clear()


# =========================================================================== construction
def construire(avec_declarations: bool = True, inventaire: dict | None = None) -> Graphe:
    """Graphe de connaissance de l'application active ; mis en cache tant que le projet ne change pas (voir plus haut).
    Un inventaire fourni par l'appelant (dépôt simulé, sous-ensemble) contourne le cache."""
    if inventaire is not None:
        return _construire(avec_declarations, inventaire)
    empreinte, recent = _empreinte_projet()
    cle = (empreinte, avec_declarations)
    if time.time() - recent < STABILITE_S:  # projet en cours de modification : pas de cache
        return _construire(avec_declarations, None)
    with _VERROU_GRAPHE:  # un seul calcul à la fois : les requêtes parallèles attendent le résultat au lieu de le refaire
        octets = _CACHE_GRAPHE.get(cle)
        if octets is None:
            octets = pickle.dumps(_construire(avec_declarations, None), protocol=pickle.HIGHEST_PROTOCOL)
            if len(_CACHE_GRAPHE) >= 4:
                _CACHE_GRAPHE.clear()
            _CACHE_GRAPHE[cle] = octets
    return pickle.loads(octets)


def _construire(avec_declarations: bool = True, inventaire: dict | None = None) -> Graphe:
    from atelier.execution import depot_robot
    from atelier.execution.robot import derniers_resultats
    from atelier.intelligence import patrimoine_xray

    g = Graphe("connaissance")
    _depuis_carte(g)
    inv = inventaire if inventaire is not None else depot_robot.lire_depot()
    _depuis_depot(g, inv)
    _depuis_jdd(g)
    _depuis_patrimoine(g, patrimoine_xray.charger_vue())
    _depuis_couverture(g)
    _depuis_openapi(g)
    _resultats(g, derniers_resultats())
    if avec_declarations:
        declarations.appliquer(g)
    _enrichir_champs(g)
    _depuis_anomalies(g)
    _marquer_automatisation(g)
    return g


def _id_ecran(e: dict) -> str:
    return f"ecran:{e.get('nom') or e['id']}"


def _depuis_carte(g: Graphe):
    from atelier.discovery import carte

    try:
        slug = carte.app_courante()
        if not slug:
            return
        cfg = carte.config_app()
        ecrans = carte.ecrans()
        transitions = carte.transitions()
    except Exception:
        return
    app = g.noeud(f"application:{slug}", "application", cfg.get("nom") or slug, source="carte",
                  proprietes={"langue": cfg.get("langue", ""), "build": cfg.get("build", "")},
                  plateformes=list(cfg.get("plateformes") or []))
    for p in cfg.get("plateformes") or []:
        g.noeud(f"plateforme:{p}", "plateforme", p.capitalize(), source="carte", plateformes=[p])
        g.relier(app.id, f"plateforme:{p}", "contient", source="carte")
    if cfg.get("build"):
        g.noeud(f"version:{cfg['build']}", "version", f"Build {cfg['build']}", source="carte")
        g.relier(app.id, f"version:{cfg['build']}", "contient", source="carte")
    try:
        from atelier.discovery import classement

        regles_cl = classement.regles()
    except Exception:  # noqa: BLE001
        classement, regles_cl = None, None
    par_id = {}
    for e in ecrans:
        eid = _id_ecran(e)
        par_id[e["id"]] = eid
        plats = sorted((e.get("plateformes") or {}).keys())
        n = g.noeud(eid, "ecran", e.get("nom") or e.get("titre") or e["id"], source="carte", plateformes=plats,
                    proprietes={"id_carte": e["id"], "titre": e.get("titre", ""), "a_revoir": e.get("a_revoir", False),
                                "etats": len(e.get("etats", [])),
                                "noms_proposes": [f"{p['nom']} ({p.get('source', '')})" for p in e.get("propositions_nom") or []]},
                    confiance=1.0 if e.get("nom") else 0.8)
        if e.get("module"):
            g.noeud(f"module:{e['module']}", "module", e["module"], source="carte")
            g.relier(app.id, f"module:{e['module']}", "contient", source="carte")
            g.relier(f"module:{e['module']}", n.id, "contient", source="carte")
        else:
            g.relier(app.id, n.id, "contient", source="carte")
        for cle, el in (e.get("elements") or {}).items():
            classe = classement.classer({"key": cle, "type": el.get("type"), "libelle": el.get("libelle", "")}, r=regles_cl)["classe"] \
                if classement else ""
            for plat, locs in (el.get("locators") or {}).items():
                if not locs:
                    continue
                lid = f"locator:{e.get('nom') or e['id']}.{cle}@{plat}"
                g.noeud(lid, "locator", cle, source="carte", plateformes=[plat],
                        proprietes={"valeur": locs[0], "secours": locs[1:], "plateforme": plat,
                                    "fiabilite": carte.robustesse(locs[0]), "libelle_ecran": el.get("libelle", ""),
                                    "classe_action": classe})
                g.relier(n.id, lid, "contient", source="carte")
            if el.get("type") in ("champ", "case", "liste", "select", "input") or classe == "controlled" or cle.startswith(("champ", "input", "saisie")):
                cid = f"composant:{e.get('nom') or e['id']}.{cle}"  # V2 : le Champ est un composant de genre « champ »
                g.noeud(cid, "composant", el.get("libelle") or cle, source="carte", plateformes=sorted(el.get("locators") or {}),
                        proprietes={"genre": "champ", "nom_technique": cle, "libelle": el.get("libelle", ""), "type": el.get("type", ""),
                                    "ecran": e.get("nom") or e["id"], "format": None, "obligatoire": None, "valeur_defaut": None,
                                    "regles_validation": [], "messages_erreur": []})
                g.relier(n.id, cid, "contient", source="carte")
                for plat in el.get("locators") or {}:
                    g.relier(cid, f"locator:{e.get('nom') or e['id']}.{cle}@{plat}", "utilise", source="carte")
        for cle_test in e.get("utilise_par", []):
            g.noeud(f"test:{cle_test}", "test", cle_test, source="carte (TNR)")
            g.relier(n.id, f"test:{cle_test}", "teste_par", source="carte (TNR)")
    for t in transitions:
        if t["de"] in par_id and t["vers"] in par_id:
            g.relier(par_id[t["de"]], par_id[t["vers"]], "navigue_vers", source=f"carte ({t.get('source', '')})",
                     proprietes={"action": t["action"].get("libelle") or t["action"].get("cle") or t["action"].get("type"),
                                 "plateforme": t["plateforme"], "interdite": t.get("interdite", False),
                                 "fiabilite": round(t["reussites"] / max(t["essais"], 1), 2)})


def _depuis_depot(g: Graphe, inv: dict):
    from atelier.discovery import carte
    from atelier.execution.depot_robot import BIBLIOTHEQUES_UI, nom_bibliotheque

    for lid, loc in inv["locators"].items():
        nid = f"locator:{lid}"
        g.noeud(nid, "locator", loc["cle"], source=f"dépôt ({loc['fichier']})", plateformes=[loc["plateforme"]],
                proprietes={"valeur": loc["valeur"], "secours": loc["secours"], "plateforme": loc["plateforme"],
                            "fiabilite": carte.robustesse(loc["valeur"]) if loc["valeur"] else "inconnue",
                            "fichier": loc["fichier"], "ecran": loc["ecran"]})
        n = g.noeuds[nid]
        n.proprietes.setdefault("fichier", loc["fichier"])
        if loc["valeur"]:
            n.proprietes["valeur_depot"] = loc["valeur"]
        eid = f"ecran:{loc['ecran']}"
        g.noeud(eid, "ecran", loc["ecran"], source="dépôt", plateformes=[loc["plateforme"]])
        g.relier(eid, nid, "contient", source="dépôt")
    for rel, info in inv["fichiers"].items():
        typ = "suite" if rel in inv["suites"] else "resource"
        fid = f"{typ}:{rel}"
        g.noeud(fid, typ, rel.rsplit("/", 1)[-1], source="dépôt", proprietes={"fichier": rel})
        for lid in info["locators"]:
            g.relier(fid, f"locator:{lid}", "contient", source="dépôt")
        for k in info["keywords"]:
            if inv["keywords"].get(k, {}).get("fichier") == rel:
                g.noeud(f"keyword:{k}", "keyword", inv["keywords"][k]["nom"], source="dépôt")
                g.relier(fid, f"keyword:{k}", "contient", source="dépôt")
        for r in info["resources"]:
            if r in inv["fichiers"]:
                g.noeud(f"resource:{r}", "resource", r.rsplit("/", 1)[-1], source="dépôt", proprietes={"fichier": r})
                g.relier(fid, f"resource:{r}", "depend_de", source="dépôt")
        for lib in info["bibliotheques"]:
            nom = nom_bibliotheque(lib)
            g.noeud(f"bibliotheque:{nom}", "bibliotheque", nom, source="dépôt",
                    plateformes=BIBLIOTHEQUES_UI.get(nom, []))
            g.relier(fid, f"bibliotheque:{nom}", "utilise", source="dépôt")

    def lier_refs(src: str, bloc: dict, plats: list[str]):
        for k in bloc["keywords"]:
            g.relier(src, f"keyword:{k}", "appelle", source="dépôt")
        for ecran, cle in bloc["locators"]:
            cibles = [i for i in (f"locator:{ecran}.{cle}@{p}" for p in ("android", "ios", "web")) if i in g.noeuds]
            if not cibles:  # référence à un locator qu'aucun fichier ne définit : anomalie visible
                nid = f"locator:{ecran}.{cle}@?"
                g.noeud(nid, "locator", cle, source="dépôt (référence seule)", confiance=0.3,
                        proprietes={"non_defini": True, "ecran": ecran})
                cibles = [nid]
            for c in cibles:
                g.relier(src, c, "utilise", source="dépôt")
        for ecran in bloc["ecrans"]:
            if not any(e == ecran for e, _ in bloc["locators"]):
                g.noeud(f"ecran:{ecran}", "ecran", ecran, source="dépôt")
                g.relier(src, f"ecran:{ecran}", "depend_de", source="dépôt")
        for j in bloc["jdd"]:
            g.noeud(f"jdd:{j}", "jdd", j, source="dépôt (référence)")
            g.relier(src, f"jdd:{j}", "depend_de", source="dépôt")

    for k, kw in inv["keywords"].items():
        n = g.noeud(f"keyword:{k}", "keyword", kw["nom"], source=f"dépôt ({kw['fichier']})",
                    proprietes={"fichier": kw["fichier"], "ligne": kw["ligne"], "documentation": kw["doc"],
                                "appels_externes": kw["externes"][:20], "doublons": kw.get("doublons", [])})
        lier_refs(n.id, kw, [])
    utilisations: dict = {}
    for tid, t in inv["tests"].items():
        n = g.noeud(f"test_robot:{tid}", "test_robot", t["nom"], source=f"dépôt ({t['fichier']})",
                    plateformes=t["plateformes"],
                    proprietes={"fichier": t["fichier"], "ligne": t["ligne"], "tags": t["tags"],
                                "cles_xray": t["cles_xray"], "documentation": t["doc"]})
        g.relier(f"suite:{t['fichier']}", n.id, "contient", source="dépôt")
        lier_refs(n.id, t, t["plateformes"])
        for lib in t["bibliotheques"]:
            g.relier(n.id, f"bibliotheque:{lib}", "utilise", source="dépôt")
        for cle in t["cles_xray"]:
            g.noeud(f"test:{cle}", "test", cle, source="tags du dépôt")
            g.relier(f"test:{cle}", n.id, "implemente_par", source="tag Robot")
        for k in t["keywords"]:
            utilisations[k] = utilisations.get(k, 0) + 1
    for k, nb in utilisations.items():
        g.noeuds[f"keyword:{k}"].proprietes["appels_directs_par_tests"] = nb


def _depuis_jdd(g: Graphe):
    from atelier.execution import jdd

    try:
        envs = jdd.environnements()
        requetes = jdd._load("requetes") if (jdd._jdd_dir() / "requetes.yaml").exists() else {}
    except Exception:
        return
    for nom, r in (requetes or {}).items():
        g.noeud(f"requete:{nom}", "requete", nom, source="data/jdd/requetes.yaml",
                proprietes={"description": (r or {}).get("description", ""), "sql": (r or {}).get("sql", "")})
    for env in envs:
        try:
            jeux = jdd.lister(env)
        except Exception:
            continue
        for j in jeux:
            nid = f"jdd:{j['jeu'].upper()}"
            n = g.noeud(nid, "jdd", j["jeu"], source=f"data/jdd/{env}.yaml")
            n.provenance, n.source = "observé", f"data/jdd/{env}.yaml"
            n.proprietes.setdefault("environnements", [])
            if env not in n.proprietes["environnements"]:
                n.proprietes["environnements"].append(env)
            n.proprietes.update(description=j["description"], champs=j["champs"], prerequis=j["prerequis"])
            for req in j["prerequis"]:
                if f"requete:{req}" in g.noeuds:
                    g.relier(nid, f"requete:{req}", "depend_de", source=f"data/jdd/{env}.yaml")
    for n in g.noeuds.values():  # JDD référencés mais définis nulle part : anomalie visible
        if n.type == "jdd" and not n.proprietes.get("environnements"):
            n.proprietes["non_defini"] = True
            n.confiance = 0.3


def _depuis_couverture(g: Graphe):
    """Exigences du périmètre importées pour la couverture (y compris celles SANS test), leurs parents et leurs liens
    natifs vers les tests : la vue Coverage Graph montre aussi ce qui n'est pas couvert."""
    try:
        from atelier.intelligence import couverture_exigences

        src = couverture_exigences._lire_json(couverture_exigences._fichier("exigences.json"), {})
    except Exception:  # noqa: BLE001 — import jamais fait : rien à ajouter
        return
    if not src.get("exigences"):
        return
    s = f"exigences Jira ({str(src.get('date', '?'))[:16]})"
    for k, p in (src.get("parents") or {}).items():
        typ = "epic" if (p.get("type_jira") or "").lower() in ("epic", "épopée") or not p.get("parent") else "fonctionnalite"
        if f"epic:{k}" not in g.noeuds and f"fonctionnalite:{k}" not in g.noeuds:
            g.noeud(f"{typ}:{k}", typ, f"{k} {p.get('resume') or ''}".strip(), source=s, proprietes={"cle": k, "resume": p.get("resume"), "statut": p.get("statut")})
    trouver = lambda k: next((f"{t}:{k}" for t in ("epic", "fonctionnalite", "user_story") if f"{t}:{k}" in g.noeuds), None)  # noqa: E731
    for k, e in (src.get("exigences") or {}).items():
        if e.get("hors_perimetre"):
            continue
        nid = trouver(k) or g.noeud(f"user_story:{k}", "user_story", f"{k} {e.get('resume') or ''}".strip(), source=s,
                                    proprietes={"cle": k, "resume": e.get("resume"), "statut": e.get("statut"), "description": (e.get("description") or "")[:500]}).id
        if e.get("parent") and trouver(e["parent"]):
            g.relier(trouver(e["parent"]), nid, "contient", source=s)
        for t in e.get("tests_jira") or []:
            if f"test:{t}" in g.noeuds:
                g.relier(nid, f"test:{t}", "teste_par", source=s)
    for k, p in (src.get("parents") or {}).items():
        if p.get("parent") and trouver(p["parent"]) and trouver(k):
            g.relier(trouver(p["parent"]), trouver(k), "contient", source=s)


def _depuis_patrimoine(g: Graphe, pat: dict | None):
    if not pat:
        return
    src = f"instantané Xray ({pat.get('date', '?')})"
    for e in pat.get("exigences", []):
        n = g.noeud(f"{e['type']}:{e['cle']}", e["type"], f"{e['cle']} {e.get('resume') or ''}".strip(), source=src,
                    proprietes={"cle": e["cle"], "resume": e.get("resume"), "statut": e.get("statut"),
                                "module": e.get("module"), "type_jira": e.get("type_jira")})
        if e.get("module"):
            g.noeud(f"module:{e['module']}", "module", e["module"], source=src)
            g.relier(f"module:{e['module']}", n.id, "contient", source=src)
    for e in pat.get("exigences", []):
        if e.get("parent"):
            parent = next((f"{t}:{e['parent']}" for t in ("epic", "user_story") if f"{t}:{e['parent']}" in g.noeuds), None)
            if parent:
                g.relier(parent, f"{e['type']}:{e['cle']}", "contient", source=src)
    for p in pat.get("plans", []):
        g.noeud(f"test_plan:{p['cle']}", "test_plan", f"{p['cle']} {p.get('resume') or ''}".strip(), source=src)
    for x in pat.get("executions", []):
        g.noeud(f"test_execution:{x['cle']}", "test_execution", f"{x['cle']} {x.get('resume') or ''}".strip(), source=src)
    for t in pat["tests"]:
        n = g.noeud(f"test:{t['cle']}", "test", t["cle"], source=src)
        n.source = src
        n.libelle = f"{t['cle']} {t.get('resume') or ''}".strip()
        n.proprietes.update({k: t.get(k) for k in ("resume", "type", "module", "libelles", "statut", "criticite")},
                            connu_xray=True)
        if t.get("module"):
            g.noeud(f"module:{t['module']}", "module", t["module"], source=src)
            g.relier(f"module:{t['module']}", n.id, "contient", source=src)
        for ex in t["exigences"]:
            for typ in ("user_story", "epic", "bug"):
                if f"{typ}:{ex}" in g.noeuds:
                    g.relier(f"{typ}:{ex}", n.id, "teste_par", source=src)
        for p in t["plans"]:
            g.noeud(f"test_plan:{p}", "test_plan", p, source=src)
            g.relier(f"test_plan:{p}", n.id, "contient", source=src)
        for x in t["executions"]:
            g.noeud(f"test_execution:{x}", "test_execution", x, source=src)
            g.relier(n.id, f"test_execution:{x}", "execute_par", source=src)


def _depuis_openapi(g: Graphe):
    """Spécifications OpenAPI / Swagger du projet (api/*.yaml|yml|json) : un nœud par opération, relié au module
    (tag de même nom) et aux tickets Jira cités dans l'extension « x-jira »."""
    import json as _json

    import yaml as _yaml

    from atelier.domain import projet

    base = projet.PROJECT_DIR / "api"
    for f in sorted(base.glob("*")) if base.exists() else []:
        if f.suffix not in (".yaml", ".yml", ".json"):
            continue
        try:
            d = _json.loads(f.read_text("utf-8")) if f.suffix == ".json" else _yaml.safe_load(f.read_text("utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict) or not ("openapi" in d or "swagger" in d):
            continue
        rel = f.relative_to(projet.PROJECT_DIR).as_posix()
        for chemin, ops in (d.get("paths") or {}).items():
            for meth, op in (ops or {}).items():
                if meth.lower() not in ("get", "post", "put", "patch", "delete") or not isinstance(op, dict):
                    continue
                nid = f"endpoint:{meth.upper()} {chemin}"
                g.noeud(nid, "endpoint", f"{meth.upper()} {chemin}", source="openapi", plateformes=["api"],
                        proprietes={"resume": op.get("summary", ""), "operation": op.get("operationId", ""), "fichier": rel,
                                    "version_api": (d.get("info") or {}).get("version", ""),
                                    "parametres": [p.get("name") for p in op.get("parameters") or [] if isinstance(p, dict)],
                                    "reponses": sorted(str(c) for c in (op.get("responses") or {})),
                                    "authentification": bool(op.get("security", d.get("security")))})
                for tag in op.get("tags") or []:
                    if f"module:{tag}" in g.noeuds:
                        g.relier(f"module:{tag}", nid, "contient", source="openapi")
                for cle in op.get("x-jira") or []:
                    for t in ("user_story", "epic"):
                        if f"{t}:{cle}" in g.noeuds:
                            g.relier(f"{t}:{cle}", nid, "utilise", source="openapi")


def _resultats(g: Graphe, res: dict):
    for tid, r in res.items():
        n = g.noeuds.get(f"test_robot:{tid}")
        if n:
            n.proprietes.update(dernier_statut=r["statut"], dernier_message=r["message"], derniere_fin=r["fin"])


OBLIGATOIRE = re.compile(r"\b(obligatoire|requis|ne peut pas être vide|doit être renseign)", re.I)
FORMAT = re.compile(r"(format[^.;,]{0,60}|\d+\s*(?:chiffres|caractères)[^.;,]{0,30}|(?:adresse )?e-?mail|iban|date[^.;,]{0,20})", re.I)
DEFAUT = re.compile(r"par défaut[^.;,]{0,60}", re.I)


def _enrichir_champs(g: Graphe):
    """Champs (composants de genre « champ ») : règles de validation (liées par une déclaration ou dont le texte cite
    le champ — lien déduit), obligatoire / format / valeur par défaut lus dans ces règles, messages d'erreur de l'écran,
    fonctionnalités de l'écran, tests qui vérifient le champ (test Robot → keyword → locator du champ)."""
    import re as _re

    champs = [n for n in g.noeuds.values() if n.type == "composant" and n.proprietes.get("genre") == "champ"]
    if not champs:
        return
    regles = [n for n in g.noeuds.values() if n.type == "regle"]
    tests_par_locator: dict = {}
    for tid, t in g.noeuds.items():
        if t.type != "test_robot":
            continue
        vus, pile = set(), [r.vers for r in g.sortants(tid) if r.type == "appelle"]
        while pile:
            k = pile.pop()
            if k in vus or k not in g.noeuds or g.noeuds[k].type != "keyword":
                continue
            vus.add(k)
            pile += [r.vers for r in g.sortants(k) if r.type == "appelle"]
        for k in vus:
            for r in g.sortants(k):
                if r.type == "utilise":
                    tests_par_locator.setdefault(r.vers, set()).add(tid)
    for c in champs:
        p = c.proprietes
        ecran_id = next((r.de for r in g.entrants(c.id) if r.type == "contient" and g.noeuds.get(r.de) and g.noeuds[r.de].type == "ecran"), None)
        mots = {m for m in _re.findall(r"[a-zà-ÿ]{4,}", f"{p.get('libelle', '')} {p['nom_technique'].replace('_', ' ')}".lower()) if m not in ("champ", "saisie", "input")}
        for rg in regles:
            texte = f"{rg.libelle} {rg.proprietes.get('description', '')}".lower()
            declare = any(r.type == "possede" and r.vers == rg.id for r in g.sortants(c.id))
            if not declare and mots and any(m in texte for m in mots):
                g.relier(c.id, rg.id, "possede", provenance="déduit", source="texte de la règle", statut="à valider")
        liees = [g.noeuds[r.vers] for r in g.sortants(c.id) if r.type == "possede" and r.vers in g.noeuds]
        textes = " ".join(f"{x.libelle}. {x.proprietes.get('description', '')}" for x in liees)
        p["regles_validation"] = [x.libelle for x in liees]
        p["obligatoire"] = True if OBLIGATOIRE.search(textes) else p.get("obligatoire")
        m = FORMAT.search(textes)
        p["format"] = m.group(0).strip() if m else p.get("format")
        m = DEFAUT.search(textes)
        p["valeur_defaut"] = m.group(0).strip() if m else p.get("valeur_defaut")
        if ecran_id:
            p["messages_erreur"] = sorted({g.noeuds[r.vers].libelle for r in g.sortants(ecran_id) if r.vers in g.noeuds
                                           and g.noeuds[r.vers].type == "locator" and _re.search(r"message|erreur|alerte", g.noeuds[r.vers].libelle, _re.I)})
            for r in g.entrants(ecran_id):
                if r.type == "contient" and g.noeuds.get(r.de) and g.noeuds[r.de].type == "fonctionnalite":
                    g.relier(r.de, c.id, "contient", source="carte (écran de la fonctionnalité)", provenance="déduit")
                    p["fonctionnalite"] = g.noeuds[r.de].libelle
        locs = [r.vers for r in g.sortants(c.id) if r.type == "utilise"]
        for t in sorted({t for l in locs for t in tests_par_locator.get(l, set())}):
            g.relier(t, c.id, "verifie", source="dépôt Robot (keyword → locator)")


def _depuis_anomalies(g: Graphe):
    """Anomalies : bugs Jira (patrimoine) enrichis par Failure Analysis — échecs associés à une anomalie Jira ou
    confirmés « défaut applicatif ». Sans clé Jira, l'anomalie reste « à valider » (jamais créée dans Jira ici)."""
    try:
        from atelier.execution import echecs

        st = echecs._stock()
    except Exception:  # noqa: BLE001
        return
    for eid, s in st.items():
        a = s.get("anomalie")
        if not a or not (s.get("jira") or s.get("categorie") == "Application Defect"):
            continue
        cle = s.get("jira") or ""
        bid = f"bug:{cle}" if cle else f"bug:FA-{hashlib.sha1(eid.encode()).hexdigest()[:8].upper()}"  # identifiant stable
        confirme = s.get("categorie") == "Application Defect"
        existant = g.noeuds.get(bid)
        n = g.noeud(bid, "bug", existant.libelle if existant else (f"{cle} " if cle else "") + f"Échec : {a.get('nom', '')}"[:150],
                    source="Failure Analysis", provenance="observé" if cle else "déduit",
                    statut="validé" if (cle or confirme) else "à valider", confiance=1.0 if cle and confirme else 0.8 if cle or confirme else 0.5,
                    proprietes={"id_interne": eid, "id_jira": cle, "type_anomalie": "défaut applicatif" if confirme else "à qualifier",
                                "statut_analyse": s.get("statut", ""), "test": a.get("nom", ""), "execution": a.get("run", ""),
                                "date_detection": a.get("date", ""), "message": a.get("message", ""), "ecran": a.get("ecran", ""),
                                "composant": a.get("composant", ""), "historique": [f"{h.get('date', '')[:16]} {h.get('op', '')} {h.get('auteur', '')}" for h in s.get("historique", [])][-10:]})
        if a.get("ecran"):
            eid_ = f"ecran:{a['ecran']}"
            if eid_ in g.noeuds:
                g.relier(n.id, eid_, "concerne", source="Failure Analysis")
                for r in g.entrants(eid_):
                    if r.type == "contient" and g.noeuds.get(r.de) and g.noeuds[r.de].type in ("fonctionnalite", "module"):
                        g.relier(n.id, r.de, "concerne", source="Failure Analysis (écran de la fonctionnalité)", provenance="déduit")
            cid = f"composant:{a['ecran']}.{a.get('composant', '')}"
            if a.get("composant") and cid in g.noeuds:
                g.relier(n.id, cid, "concerne", source="Failure Analysis (étape fautive)")
        tr = next((i for i, x in g.noeuds.items() if x.type == "test_robot" and x.libelle == a.get("nom")), None)
        if tr:
            g.relier(n.id, tr, "detecte_par", source="Failure Analysis")
        if a.get("cle_xray") and f"test:{a['cle_xray']}" in g.noeuds:
            g.relier(n.id, f"test:{a['cle_xray']}", "detecte_par", source="Failure Analysis")
        if a.get("run"):
            rid = f"resultat:{a['run']}"
            g.noeud(rid, "resultat", f"Exécution {a['run']}", source="Execution Center", proprietes={"run": a["run"], "date": a.get("date", "")})
            g.relier(n.id, rid, "associe_a", source="Failure Analysis")


def _marquer_automatisation(g: Graphe):
    """Définition explicite : un test Xray est automatisé si au moins un test Robot du dépôt porte sa
    clé en tag (relation « est implémenté par » observée)."""
    for n in g.noeuds.values():
        if n.type != "test":
            continue
        impl = [r.vers for r in g.sortants(n.id, fiables=True) if r.type == "implemente_par"]
        n.proprietes["automatise"] = bool(impl)
        n.proprietes.setdefault("connu_xray", False)
        statuts = [g.noeuds[i].proprietes.get("dernier_statut") for i in impl]
        statuts = [s for s in statuts if s]
        if statuts:
            n.proprietes["dernier_resultat"] = "FAIL" if "FAIL" in statuts else "PASS" if "PASS" in statuts else statuts[0]


# =========================================================================== analyse d'impact
def analyser_impact(g: Graphe, noeud_id: str) -> dict:
    """Ce qui est concerné par la modification d'un locator, keyword, resource, écran, JDD, composant…
    Seules les relations fiables (observées, déclarées, ou déduites ET validées) sont suivies."""
    if noeud_id not in g.noeuds:
        raise KeyError(f"Élément inconnu : {noeud_id}")
    depart = g.noeuds[noeud_id]
    sources = {noeud_id}
    if depart.type in ("ecran", "resource", "suite", "composant", "module"):
        sources |= {x for x in g.atteignables(noeud_id, "aval", {"contient"})}
    dependants = set()
    for s in sources:
        dependants |= g.atteignables(s, "amont", RELATIONS_DEPENDANCE)
    dependants |= sources
    tests_robot = sorted(i for i in dependants if g.noeuds[i].type == "test_robot")
    tests_xray = sorted({r.de for t in tests_robot for r in g.entrants(t, fiables=True) if r.type == "implemente_par"})
    keywords = sorted(i for i in dependants if g.noeuds[i].type == "keyword")
    modules = set()
    for t in tests_xray:
        modules |= {r.de for r in g.entrants(t, fiables=True) if r.type == "contient" and g.noeuds[r.de].type == "module"}
    for e in [i for i in sources | dependants if g.noeuds[i].type in ("ecran", "locator")]:
        for r in g.entrants(e, fiables=True):
            if r.type == "contient" and g.noeuds[r.de].type == "module":
                modules.add(r.de)
            if r.type == "contient" and g.noeuds[r.de].type == "ecran":
                modules |= {x.de for x in g.entrants(r.de, fiables=True)
                            if x.type == "contient" and g.noeuds[x.de].type == "module"}
    if depart.type == "locator" and depart.plateformes:
        plateformes = sorted(depart.plateformes)
    else:
        plateformes = sorted({p for t in tests_robot for p in g.noeuds[t].plateformes})
    sans_cle = [t for t in tests_robot if not g.noeuds[t].proprietes.get("cles_xray")]
    cles = sorted({c for t in tests_robot for c in g.noeuds[t].proprietes.get("cles_xray") or []})
    fichiers = sorted({g.noeuds[t].proprietes.get("fichier", "") for t in tests_robot})
    cible = posixpath.commonpath(fichiers) if fichiers else ""  # chemins du projet : toujours « / »
    if cible in fichiers and len(fichiers) > 1:
        cible = posixpath.dirname(cible)
    return {
        "element": depart.vers_dict(),
        "tests_robot": [{"id": t, "nom": g.noeuds[t].libelle, "fichier": g.noeuds[t].proprietes.get("fichier"),
                         "cles_xray": g.noeuds[t].proprietes.get("cles_xray") or []} for t in tests_robot],
        "tests_xray": [{"id": t, "libelle": g.noeuds[t].libelle} for t in tests_xray],
        "scenarios": [g.noeuds[t].libelle for t in tests_xray],
        "keywords": [{"id": k, "nom": g.noeuds[k].libelle} for k in keywords],
        "modules": sorted(g.noeuds[m].libelle for m in modules),
        "plateformes": plateformes,
        "tnr": {"possible": bool(cles), "target": cible or ".", "include_tags": cles,
                "tests_sans_cle_xray": [g.noeuds[t].libelle for t in sans_cle],
                "explication": ("TNR ciblée : tests Robot qui portent les clés Xray concernées."
                                if cles else "Aucun test concerné ne porte de clé Xray : TNR par tag impossible.")},
    }


def sources() -> dict:
    """Ce qui alimente le graphe, avec état et volume : carte (Discovery), dépôt Robot, JDD, Jira / Xray
    (copie locale), contrats OpenAPI, déclarations. Aucune source n'est interrogée en direct."""
    from atelier.discovery import carte, sessions_discovery
    from atelier.domain import projet
    from atelier.execution import depot_robot
    from atelier.intelligence import patrimoine_xray

    out = {}
    try:
        app = carte.app_courante()
        sess = sessions_discovery.lister()
        out["carte"] = {"app": app, "ecrans": len(carte.ecrans()) if app else 0, "transitions": len(carte.transitions()) if app else 0,
                        "derniere_session": (sess[0].get("fin") or sess[0].get("debut") or sess[0]["cree"]) if sess else None, "sessions": len(sess)}
    except Exception as e:  # noqa: BLE001
        out["carte"] = {"erreur": str(e)[:200]}
    try:
        inv = depot_robot.lire_depot()
        out["depot"] = {"suites": len(inv.get("suites") or []), "tests": len(inv.get("tests") or {}), "keywords": len(inv.get("keywords") or {})}
    except Exception as e:  # noqa: BLE001
        out["depot"] = {"erreur": str(e)[:200]}
    e = patrimoine_xray.etat()
    out["jira_xray"] = {"present": e.get("present", False), "date": e.get("date"), "source": e.get("source"), "tests": e.get("nb_tests", 0),
                        "exigences": e.get("nb_exigences", 0), "definitions": (e.get("definitions_xray") or {}).get("date")}
    api_dir = projet.PROJECT_DIR / "api"
    out["openapi"] = {"fichiers": sorted(f.name for f in api_dir.glob("*.*") if f.suffix in (".yaml", ".yml", ".json"))} if api_dir.exists() else {"fichiers": []}
    jdd_dir = projet.PROJECT_DIR / "data" / "jdd"
    out["jdd"] = {"environnements": sorted(f.stem for f in jdd_dir.glob("*.y*ml") if f.stem != "requetes")} if jdd_dir.exists() else {"environnements": []}
    d = declarations.charger()
    out["declarations"] = {"noeuds": len(d["noeuds"]), "relations": len(d["relations"]),
                           "a_valider": sum(n.get("statut") == "à valider" for n in d["noeuds"].values())}
    return out
