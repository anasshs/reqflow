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

from atelier.domain.yaml_rapide import charger as charger_yaml

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
SANS_EFFET = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm", ".html", ".log", ".zip", ".svg", ".bak", ".tmp")
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
            if nom.lower().endswith(SANS_EFFET):
                continue
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
        _MEMO_SOURCES.clear()
        _MEMO_FICHIERS.clear()
        _SIGNATURES.clear()


# =========================================================================== sources relues seulement si elles changent
# Une Discovery modifie la carte, pas le dépôt Robot ni les résultats : leur lecture (la plus coûteuse sur un vrai dépôt)
# est réutilisée tant que leurs propres fichiers n'ont pas changé. L'assemblage du graphe, lui, est refait : il est rapide,
# déterministe et ne laisse jamais une relation d'une ancienne version d'un fichier (un fichier retiré disparaît).
_MEMO_SOURCES: dict = {}
DERNIERE_CONSTRUCTION: dict = {}


def _fichiers(motifs: tuple[str, ...], sous: str = "") -> list:
    base = projet.PROJECT_DIR / sous if sous else projet.PROJECT_DIR
    if not base.exists():
        return []
    out = []
    for r, ds, fs in os.walk(base):
        ds[:] = sorted(d for d in ds if d not in DOSSIERS_IGNORES)
        out += [os.path.join(r, f) for f in sorted(fs) if any(Path(f).match(m) for m in motifs)]
    return out


def _memo(nom: str, fichiers: list, calcul):
    """Résultat de calcul() réutilisé tant que les fichiers de la source (chemin, taille, date) sont identiques."""
    h = hashlib.blake2b(digest_size=16)
    h.update(str(projet.PROJECT_DIR).encode())
    for f in fichiers:
        try:
            st = os.stat(f)
        except OSError:
            continue
        h.update(f"\n{f}|{st.st_size}|{st.st_mtime_ns}".encode())
    cle = h.hexdigest()
    m = _MEMO_SOURCES.get(nom)
    if m and m[0] == cle:
        DERNIERE_CONSTRUCTION.setdefault("reutilisees", []).append(nom)
        return pickle.loads(m[1])
    val = calcul()
    _MEMO_SOURCES[nom] = (cle, pickle.dumps(val, protocol=pickle.HIGHEST_PROTOCOL))
    DERNIERE_CONSTRUCTION.setdefault("relues", []).append(nom)
    return val


# Grain plus fin pour ce qui change pendant une Discovery : chaque fichier d'écran (et chaque test BDD) est relu seulement
# s'il a changé ; les autres sont repris en mémoire. Un fichier disparu n'est plus lu : ses nœuds et relations disparaissent.
_MEMO_FICHIERS: dict = {}


def _lu(source: str, chemins: list, lecture):
    """lecture() réutilisée tant que les fichiers `chemins` (taille, date) n'ont pas changé ; compteurs par source."""
    cle = []
    for c in chemins:
        try:
            st = os.stat(c)
            cle.append((str(c), st.st_size, st.st_mtime_ns))
        except OSError:
            cle.append((str(c), None, None))
    k = (source, str(chemins[0]) if chemins else "")
    m = _MEMO_FICHIERS.get(k)
    stats = DERNIERE_CONSTRUCTION.setdefault("fichiers", {}).setdefault(source, {"relus": 0, "reutilises": 0})
    if m and m[0] == cle:
        stats["reutilises"] += 1
        return pickle.loads(m[1])
    val = lecture()
    _MEMO_FICHIERS[k] = (cle, pickle.dumps(val, protocol=pickle.HIGHEST_PROTOCOL))
    stats["relus"] += 1
    return val


# Delta entre deux constructions : ce qui a été ajouté, modifié ou retiré (mis en avant à l'écran pendant le suivi en direct).
_SIGNATURES: dict = {}


def _signature(n) -> str:
    import json as _json

    return hashlib.blake2b(_json.dumps([n.type, n.libelle, n.statut, n.provenance, n.plateformes, n.proprietes], sort_keys=True,
                                       default=str, ensure_ascii=False).encode(), digest_size=8).hexdigest()


def _delta(g: Graphe) -> dict:
    liens: dict = {}
    for r in g.relations.values():  # une relation ajoutée, retirée ou changée modifie ses deux extrémités
        t = f"{r.de}|{r.type}|{r.vers}|{r.statut}"
        liens.setdefault(r.de, []).append(t)
        liens.setdefault(r.vers, []).append(t)
    sig = {i: _signature(n) + hashlib.blake2b("\n".join(sorted(liens.get(i, []))).encode(), digest_size=6).hexdigest()
           for i, n in g.noeuds.items()}
    avant = _SIGNATURES.get("noeuds")
    _SIGNATURES["noeuds"] = sig
    if avant is None:
        return {"premiere": True, "ajoutes": [], "modifies": [], "retires": []}
    return {"premiere": False, "ajoutes": sorted(set(sig) - set(avant))[:300],
            "modifies": sorted(i for i in sig if i in avant and sig[i] != avant[i])[:300],
            "retires": sorted(set(avant) - set(sig))[:300]}


# =========================================================================== construction
def construire(avec_declarations: bool = True, inventaire: dict | None = None) -> Graphe:
    """Graphe de connaissance de l'application active ; mis en cache tant que le projet ne change pas (voir plus haut).
    Un inventaire fourni par l'appelant (dépôt simulé, sous-ensemble) contourne le cache."""
    if inventaire is not None:
        return _construire(avec_declarations, inventaire)
    empreinte, recent = _empreinte_projet()
    from atelier.discovery import carte

    cle = (empreinte, avec_declarations, carte.app_courante() or "")  # un graphe par application active
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


ETATS_COUVERTURE = {"couvert": "Couvert par un test", "echec": "Couvert, dernier run en échec", "partiel": "Partiellement couvert",
                    "non_couvert": "Non couvert"}


def _annoter_couverture_tests(g: Graphe):
    """Couverture par les tests, posée sur chaque écran et chaque parcours (vue « Couverture des tests » du graphe) :
    écran couvert (un test l'utilise, ou un scénario BDD automatisé le parcourt), couvert mais en échec (dernier run KO),
    partiel (association déduite via une fonctionnalité), non couvert ; parcours couvert (toutes ses étapes),
    partiel (une partie), non couvert. Calcul de couverture_avancee : jamais bloquant."""
    try:
        from atelier.intelligence import couverture_avancee

        c = couverture_avancee.calculer(g)
    except Exception:  # noqa: BLE001
        return
    for e in c["ecrans"]:
        n = g.noeuds.get(e["id"])
        if not n:
            continue
        if e["tests_robot"]:
            echec = e["niveau"] == "exécuté"  # exécuté sans être réussi : dernier run en échec
            etat = "echec" if echec else "couvert"
        else:
            etat = "partiel" if e["tests_xray_deduits"] else "non_couvert"
        n.proprietes["couverture_tests"] = {"etat": etat, "libelle": ETATS_COUVERTURE[etat], "niveau": e["niveau"],
                                            "tests": e["tests_robot"][:20], "tests_xray": e.get("tests_xray", [])[:20]}
    for p in c["parcours"]:
        n = g.noeuds.get(p["id"])
        if not n:
            continue
        total, faites = len(p["etapes"]), p["etapes_associees"]
        etat = "non_couvert" if not faites else "couvert" if faites == total else "partiel"
        n.proprietes["couverture_tests"] = {"etat": etat, "libelle": ETATS_COUVERTURE[etat], "niveau": p["niveau"],
                                            "etapes": total, "etapes_couvertes": faites,
                                            "non_couvertes": [x["ecran"] for x in p["etapes"] if x["niveau"] == "découvert"]}


COMPLETUDES = ("déclaré", "découvert", "partiellement exploré", "exploré", "confirmé")


def completude_parcours(g: Graphe, pid: str) -> str:
    """déclaré (aucun écran : préparé, pas encore déroulé) ; découvert (écrans proposés, aucun validé) ; partiellement
    exploré (une partie validée) ; exploré (tous validés) ; confirmé (exploré et vérifié par au moins un test BDD)."""
    ecrans = [r for r in g.sortants(pid) if r.type == "contient" and r.vers.startswith("ecran:")]
    if not ecrans:
        return "déclaré"
    valides = sum(1 for r in ecrans if r.statut == "validé")
    if not valides:
        return "découvert"
    if valides < len(ecrans):
        return "partiellement exploré"
    verifie = any(r.type == "verifie" and r.confirmee for r in g.entrants(pid))
    return "confirmé" if verifie else "exploré"


def _relations_fonctionnelles(g: Graphe):
    """Vue fonctionnelle reliée, déduite de ce que la Discovery a observé (agrégats, jamais inventés) :
    - module → mène à → module : au moins une navigation d'un écran de l'un vers un écran de l'autre
      (transitions, actions et écrans gardés en propriétés) ;
    - parcours → traverse → module : un écran du parcours appartient au module (ordre de passage gardé) ;
    - parcours → s'enchaîne avec → parcours : le dernier écran de l'un est le premier de l'autre.
    Statut : celui des faits sources (un parcours dont les écrans sont encore à valider donne des liens à valider)."""
    for sid, n in list(g.noeuds.items()):  # pont Tests ↔ Utilisateur : le test BDD vérifie le parcours dont il vient
        if n.type == "scenario" and n.proprietes.get("parcours") in g.noeuds:
            g.relier(sid, n.proprietes["parcours"], "verifie", source="bdd (parcours d'origine)")
    module_de: dict = {}
    for r in g.relations.values():
        if r.type == "contient" and r.de.startswith("module:") and r.vers.startswith("ecran:"):
            module_de.setdefault(r.vers, r.de)
    agg: dict = {}
    for r in list(g.relations.values()):
        if r.type != "navigue_vers" or r.proprietes.get("interdite"):
            continue
        a, b = module_de.get(r.de), module_de.get(r.vers)
        if a and b and a != b:
            x = agg.setdefault((a, b), {"transitions": 0, "ecrans": set(), "actions": set()})
            x["transitions"] += 1
            x["ecrans"].update((r.de, r.vers))
            if r.proprietes.get("action"):
                x["actions"].add(str(r.proprietes["action"]))
    for (a, b), x in agg.items():
        g.relier(a, b, "mene_a", provenance="déduit", statut="validé", source="navigations observées entre leurs écrans (Discovery)",
                 proprietes={"calcul": True, "transitions": x["transitions"], "actions": sorted(x["actions"])[:12],
                             "preuves": sorted(x["ecrans"])[:20], "via_ecrans": sorted(x["ecrans"])[:20]})
    extremites: dict = {}
    for pid, n in g.noeuds.items():
        if n.type != "parcours":
            continue
        rels = sorted((r for r in g.sortants(pid, False) if r.type == "contient" and r.vers.startswith("ecran:")),
                      key=lambda r: (r.proprietes.get("ordre", 0), r.vers))
        if not rels:
            continue
        extremites[pid] = (rels[0].vers, rels[-1].vers)
        modules: dict = {}
        for i, r in enumerate(rels):
            m = module_de.get(r.vers)
            if m:
                st = modules.get(m, (i, "validé", []))
                modules[m] = (st[0], "validé" if st[1] == "validé" and r.statut == "validé" else "à valider", st[2] + [r.vers])
        for m, (ordre, statut, ecrans) in modules.items():
            g.relier(pid, m, "traverse", provenance="déduit", statut=statut, source="écrans du parcours (Discovery)",
                     proprietes={"calcul": True, "ordre": ordre, "preuves": ecrans[:20], "via_ecrans": ecrans[:20]})
    for pid, n in g.noeuds.items():
        if n.type == "parcours":
            n.proprietes["completude"] = completude_parcours(g, pid)
    for a, (_, fin) in extremites.items():
        for b, (debut, _) in extremites.items():
            if a != b and fin == debut:
                g.relier(a, b, "enchaine_avec", provenance="déduit", statut="validé", source="fin de l'un = début de l'autre",
                         proprietes={"calcul": True, "preuves": [fin], "via_ecrans": [fin]})


def _construire(avec_declarations: bool = True, inventaire: dict | None = None) -> Graphe:
    from atelier.execution import depot_robot
    from atelier.execution.robot import derniers_resultats
    from atelier.intelligence import patrimoine_xray

    debut = time.perf_counter()
    DERNIERE_CONSTRUCTION.clear()
    g = Graphe("connaissance")
    _depuis_carte(g)
    inv = inventaire if inventaire is not None else _memo("dépôt Robot", _fichiers(("*.robot", "*.resource")), depot_robot.lire_depot)
    _depuis_depot(g, inv)
    _depuis_jdd(g)
    _depuis_patrimoine(g, patrimoine_xray.charger_vue())
    _depuis_couverture(g)
    _depuis_bdd(g, inv)
    _depuis_openapi(g)
    _resultats(g, _memo("résultats des runs", _fichiers(("output.xml",), "results"), derniers_resultats))
    if avec_declarations:
        declarations.appliquer(g)
    _depuis_donnees(g)  # après les déclarations : les parcours déclarés reçoivent les variables de leurs écrans
    _relations_fonctionnelles(g)  # le « quoi » relié entre lui : modules, parcours (depuis la Discovery)
    _depuis_comportement(g)  # modèles comportementaux (MBT) : états, transitions, conditions, chemins générés
    _verifiees_sur(g, set(declarations.charger()["relations_masquees"]) if avec_declarations else set())
    _enrichir_champs(g)
    _depuis_anomalies(g)
    _marquer_automatisation(g)
    _annoter_couverture_tests(g)
    try:  # isolation des applications du projet : rien d'une autre application dans ce graphe
        from atelier.discovery import application, carte

        DERNIERE_CONSTRUCTION["autres_applications_retires"] = application.filtrer_graphe(g, carte.app_courante() or "")
    except Exception:  # noqa: BLE001 — filtrage impossible : le graphe reste complet plutôt que vide
        pass
    if inventaire is None and avec_declarations:
        DERNIERE_CONSTRUCTION["delta"] = _delta(g)
    DERNIERE_CONSTRUCTION.update(duree_s=round(time.perf_counter() - debut, 3), noeuds=len(g.noeuds), relations=len(g.relations),
                                 date=time.strftime("%Y-%m-%dT%H:%M:%S"))
    return g


def _depuis_comportement(g: Graphe):
    """Modèles comportementaux (comportement/*.yaml, MBT) : un nœud par modèle, état, transition, condition, et par
    chemin qui a donné un scénario BDD. Relations du cahier (CONTAINS_STATE, STARTS_FROM, LEADS_TO, TRIGGERED_BY,
    GUARDED_BY, ASSOCIATED_WITH, TRAVERSES, DERIVED_FROM, VERIFIES) avec la provenance et la validation de l'élément :
    un élément déduit non validé reste une proposition (jamais dans la couverture ni l'impact officiels)."""
    try:
        from atelier.domain import comportement as cm

        d = cm.dossier()
        fichiers = sorted(d.glob("*.yaml")) if d.exists() else []
    except Exception:  # noqa: BLE001
        return
    import yaml as _yaml

    for f in fichiers:
        try:
            m = _lu("modèles comportementaux", [f], lambda f=f: charger_yaml(f.read_text("utf-8")) or {})
        except Exception:  # noqa: BLE001 — un modèle illisible ne bloque pas le graphe
            continue
        if not m.get("id"):
            continue
        mid = f"modele_comportement:{m['id']}"
        g.noeud(mid, "modele_comportement", m.get("nom") or m["id"], provenance="déclaré" if m.get("statut") == "Validated" else "observé",
                source=f"comportement/{f.name}", proprietes={"version": m.get("version"), "statut": m.get("statut"), "perimetre": m.get("perimetre")})
        per = (m.get("perimetre") or {}).get("id")
        if per in g.noeuds:
            g.relier(per, mid, "associe_a", source="modèle comportemental (périmètre)")

        def st(el):
            v = el.get("validation", "à valider")
            return ("déduit" if el.get("provenance") == "déduit" else "observé" if el.get("provenance") == "observé" else "déclaré",
                    "validé" if v == "validé" else "à valider")
        for k, e in (m.get("etats") or {}).items():
            if e.get("validation") == "rejeté":
                continue
            prov, statut = st(e)
            eid = f"etat:{m['id']}/{k}"
            g.noeud(eid, "etat", e.get("nom") or k, provenance=prov, source=e.get("source", ""), statut=statut,
                    proprietes={"genre": e.get("type"), "initial": e.get("initial"), "final": e.get("final"), "confiance_mbt": e.get("confiance")})
            g.relier(mid, eid, "contient_etat", provenance=prov, statut=statut, source="modèle comportemental")
            if e.get("ecran") in g.noeuds:
                g.relier(eid, e["ecran"], "associe_a", provenance=prov, statut=statut, source="modèle comportemental")
        for k, c in (m.get("conditions") or {}).items():
            if c.get("validation") == "rejeté":
                continue
            prov, statut = st(c)
            g.noeud(f"condition:{m['id']}/{k}", "condition", c.get("libelle") or k, provenance=prov, source=c.get("source", ""), statut=statut,
                    proprietes={"regle": c.get("regle", ""), "confiance_mbt": c.get("confiance")})
            if c.get("regle") in g.noeuds:
                g.relier(f"condition:{m['id']}/{k}", c["regle"], "associe_a", provenance=prov, statut=statut, source="modèle comportemental")
        for k, t in (m.get("transitions") or {}).items():
            de, vers = f"etat:{m['id']}/{t.get('de')}", f"etat:{m['id']}/{t.get('vers')}"
            if t.get("validation") == "rejeté" or de not in g.noeuds or vers not in g.noeuds:
                continue
            prov, statut = st(t)
            a = (m.get("actions") or {}).get(t.get("action")) or {}
            tid = f"transition:{m['id']}/{k}"
            g.noeud(tid, "transition", f"{g.noeuds[de].libelle} → {g.noeuds[vers].libelle}" + (f" ({a.get('libelle')})" if a.get("libelle") else ""),
                    provenance=prov, source=t.get("source", ""), statut=statut,
                    proprietes={"priorite": t.get("priorite"), "issue": t.get("issue", ""), "confiance_mbt": t.get("confiance")})
            for typ, x, y in (("contient_transition", mid, tid), ("part_de", tid, de), ("conduit_a", tid, vers)):
                g.relier(x, y, typ, provenance=prov, statut=statut, source="modèle comportemental")
            if a.get("noeud") in g.noeuds:
                g.relier(tid, a["noeud"], "declenchee_par", provenance=prov, statut=statut, source="modèle comportemental")
            cond = f"condition:{m['id']}/{t.get('garde')}"
            if t.get("garde") and cond in g.noeuds:
                g.relier(tid, cond, "gardee_par", provenance=prov, statut=statut, source="modèle comportemental")
        for pid, c in (m.get("chemins_generes") or {}).items():
            sc = f"scenario:{c.get('scenario')}"
            if sc not in g.noeuds:
                continue
            ch = f"chemin:{m['id']}/{pid}"
            g.noeud(ch, "chemin", f"Chemin {pid}", provenance="déduit", statut="validé", source=f"comportement/{f.name}",
                    proprietes={"calcul": True, "strategie": c.get("strategie"), "version_modele": c.get("version")})
            g.relier(sc, ch, "derive_de", provenance="déduit", statut="validé", source="génération MBT", proprietes={"calcul": True})
            for t in c.get("transitions") or []:
                if f"transition:{m['id']}/{t}" in g.noeuds:
                    g.relier(ch, f"transition:{m['id']}/{t}", "parcourt", provenance="déduit", statut="validé", source="génération MBT",
                             proprietes={"calcul": True})
                    g.relier(sc, f"transition:{m['id']}/{t}", "verifie", source="génération MBT (traçabilité du scénario)")
            for e in c.get("etats") or []:
                if f"etat:{m['id']}/{e}" in g.noeuds:
                    g.relier(sc, f"etat:{m['id']}/{e}", "verifie", source="génération MBT (traçabilité du scénario)")


def _id_ecran(e: dict) -> str:
    return f"ecran:{e.get('nom') or e['id']}"


def _depuis_carte(g: Graphe):
    from atelier.discovery import carte

    try:
        slug = carte.app_courante()
        if not slug:
            return
        cfg = carte.config_app()
        dossier = carte._dir() / "ecrans"
        ecrans = [e for e in (_lu("écrans (carte)", [f], lambda f=f: carte._load(f, {}))
                              for f in sorted(dossier.glob("*.yaml"))) if e and e.get("id")]
        transitions = carte.transitions()
    except Exception:
        return
    app = g.noeud(f"application:{slug}", "application", cfg.get("nom") or slug, source="carte",
                  proprietes={"langue": cfg.get("langue", ""), "build": cfg.get("build", "")},
                  plateformes=list(cfg.get("plateformes") or []))
    for p in cfg.get("plateformes") or []:
        g.noeud(f"plateforme:{p}", "plateforme", p.capitalize(), source="carte", plateformes=[p])
        g.relier(app.id, f"plateforme:{p}", "contient", source="carte")
    builds = {cfg.get("build") or ""}
    for e in ecrans:
        builds |= {p.get("vu_build") or "" for p in (e.get("plateformes") or {}).values()}
        builds |= {c.get("build") or "" for c in e.get("changements") or []}
    for b in sorted(builds - {""}):
        g.noeud(f"version:{b}", "version", f"Build {b}", source="carte", proprietes={"courante": b == cfg.get("build")})
        g.relier(app.id, f"version:{b}", "contient", source="carte")
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
                    proprietes={"id_carte": e["id"], "ids_fusionnes": e.get("ids_fusionnes", []), "titre": e.get("titre", ""), "a_revoir": e.get("a_revoir", False),
                                "versions": sorted(({p.get("vu_build") or "" for p in (e.get("plateformes") or {}).values()}
                                                   | {c.get("build") or "" for c in e.get("changements") or []}) - {""}),
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
            libelle = t["action"].get("libelle") or t["action"].get("cle") or t["action"].get("type")
            fiab = round(t["reussites"] / max(t["essais"], 1), 2)
            g.relier(par_id[t["de"]], par_id[t["vers"]], "navigue_vers", source=f"carte ({t.get('source', '')})",
                     proprietes={"action": libelle, "plateforme": t["plateforme"], "interdite": t.get("interdite", False),
                                 "fiabilite": fiab})
            # perspective utilisateur : écran → permet → action → aboutit à → écran (condition éventuelle sur le lien)
            de = par_id[t["de"]]
            cle_action = t["action"].get("cle") or t["action"].get("type") or "action"
            aid = f"action:{de.split(':', 1)[1]}.{cle_action}"
            a = g.noeuds.get(aid) or g.noeud(aid, "action", libelle or cle_action, source="carte",
                                              proprietes={"genre": t["action"].get("type", ""), "cle": t["action"].get("cle", ""),
                                                          "ecran": de.split(":", 1)[1]})
            if t["plateforme"] not in a.plateformes:
                a.plateformes.append(t["plateforme"])
            g.relier(de, aid, "permet", source="carte")
            g.relier(aid, par_id[t["vers"]], "aboutit_a", source="carte",
                     proprietes={"plateforme": t["plateforme"], "fiabilite": fiab, "interdite": t.get("interdite", False),
                                 **({"condition": t["condition"]} if t.get("condition") else {}),
                                 **({"alternative": True} if t.get("alternative") else {})})


def _verifiees_sur(g: Graphe, masquees: set | None = None):
    """Exigence « vérifiée sur » écran : PREUVE issue des tests, créée automatiquement. Un test automatisé utilise les
    locators de l'écran (dépôt), ou est passé par l'écran pendant un run cartographié ; il porte une clé Xray ; ce test
    Xray est lié à l'exigence. Une seule relation par couple, qui garde toutes ses preuves (test Xray, scripts, locators).
    Seuls les écrans de la carte (vus pendant une Discovery) sont reliés. Cette relation ne dit pas que l'écran réalise
    l'exigence (un test de bout en bout traverse aussi la connexion) : elle n'entre dans aucun calcul de couverture ni
    d'impact ; « réalisé par » reste une décision humaine (Discovery › Corrélation)."""
    import re as _re

    cle_xray = _re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
    for n in [x for x in g.noeuds.values() if x.type == "ecran" and x.proprietes.get("id_carte")]:
        par_test: dict[str, set] = {}
        for s in {n.id} | g.atteignables(n.id, "aval", {"contient"}):
            for i in g.atteignables(s, "amont", RELATIONS_DEPENDANCE):
                if g.noeuds[i].type == "test_robot":
                    par_test.setdefault(i, set())
                    if g.noeuds[s].type == "locator":
                        par_test[i].add(g.noeuds[s].libelle)
        preuves: dict[str, dict] = {}

        def preuve(cle: str) -> dict:
            return preuves.setdefault(cle, {"test_xray": cle, "scripts": [], "locators": set(), "origines": set()})

        for t, locs in par_test.items():
            tn = g.noeuds[t]
            cles = set(tn.proprietes.get("cles_xray") or []) | {
                x.de.split(":", 1)[1] for x in g.entrants(t, fiables=True) if x.type == "implemente_par" and g.noeuds[x.de].type == "test"}
            for c in cles:
                p = preuve(c)
                p["scripts"].append({"nom": tn.libelle, "fichier": tn.proprietes.get("fichier") or ""})
                p["locators"] |= locs
                p["origines"].add("locators utilisés par le script")
        for x in g.sortants(n.id):
            if x.type == "teste_par" and x.source == "carte (TNR)" and cle_xray.match(x.vers.split(":", 1)[1]):
                preuve(x.vers.split(":", 1)[1])["origines"].add("écran traversé pendant un run cartographié")
        for c in sorted(preuves):
            p = preuves[c]
            for x in g.entrants(f"test:{c}", fiables=True):
                if x.type != "teste_par" or g.noeuds[x.de].type not in ("epic", "user_story", "bug"):
                    continue
                if f"{x.de}|verifiee_sur|{n.id}" in (masquees or ()):
                    continue
                rel = g.relier(x.de, n.id, "verifiee_sur", source="tests automatisés", proprietes={"preuves": []})
                rel.proprietes["preuves"].append({"test_xray": c, "scripts": sorted(p["scripts"], key=lambda s: (s["fichier"], s["nom"])),
                                                  "locators": sorted(p["locators"]), "origines": sorted(p["origines"])})


_IDENTIFIANTS = (
    ("rid", re.compile(r"""resourceId(?:Matches)?\("(?:[\w.]+:id/)?([^"]+)"\)|@resource-id\s*=\s*["'](?:[\w.]+:id/)?([^"']+)["']|^id=(?:[\w.]+:id/)?(\S+)$""")),
    ("acc", re.compile(r"""^accessibility_id=(.+)$|description\("([^"]+)"\)|@content-desc\s*=\s*["']([^"']+)["']""")),
    ("txt", re.compile(r"""\.text\("([^"]+)"\)|@text\s*=\s*["']([^"']+)["']""")),
)


def identifiant_locator(valeur: str) -> str:
    """Identité d'un locator indépendante de sa syntaxe : premier resource-id, sinon accessibility id, sinon texte exact.
    « android=new UiSelector().resourceId("x") », « id=app:id/x » et « //*[@resource-id="x"] » ont la même : rid:x."""
    for genre, rx in _IDENTIFIANTS:
        m = rx.search(valeur or "")
        if m:
            return f"{genre}:{next(x for x in m.groups() if x)}"
    return ""


# un élément présent sur plus d'écrans que cela (barre de navigation, bouton retour de l'en-tête, bouton de popup) est un
# composant commun : un test qui le touche ne couvre pas pour autant chacun de ces écrans
COMPOSANT_COMMUN_MAX = 3


def _correspondances_carte(g: Graphe) -> tuple[dict, dict]:
    """Locators de la carte indexés par valeur exacte et par identité (pour relier le dépôt à la carte)."""
    par_valeur, par_ident = {}, {}
    for lid, n in g.noeuds.items():
        if n.type != "locator" or n.source != "carte":
            continue
        p = n.proprietes
        for v in [p.get("valeur") or ""] + list(p.get("secours") or []):
            if v:
                par_valeur.setdefault((v.strip(), p.get("plateforme")), set()).add(lid)
        i = identifiant_locator(p.get("valeur") or "")
        if i:
            par_ident.setdefault((i, p.get("plateforme")), set()).add(lid)
    return par_valeur, par_ident


def _depuis_depot(g: Graphe, inv: dict):
    from atelier.discovery import carte
    from atelier.execution.depot_robot import BIBLIOTHEQUES_UI, nom_bibliotheque

    par_valeur, par_ident = _correspondances_carte(g)
    carte_de: dict = {}  # locator du dépôt -> locators de la carte de même valeur (ou de même identité)
    communs: dict = {}   # locator du dépôt -> nombre d'écrans où l'élément existe (barre de navigation, retour…)
    for lid, loc in inv["locators"].items():
        v, plat = (loc.get("valeur") or "").strip(), loc["plateforme"]
        cibles = par_valeur.get((v, plat)) or par_ident.get((identifiant_locator(v), plat)) if v else None
        if not cibles:
            continue
        ecrans_cibles = {c.split(":", 1)[1].rsplit("@", 1)[0].rsplit(".", 1)[0] for c in cibles}
        if len(ecrans_cibles) > COMPOSANT_COMMUN_MAX:  # composant commun : le toucher ne dit pas sur quel écran on est
            communs[f"locator:{lid}"] = len(ecrans_cibles)
            continue
        carte_de[f"locator:{lid}"] = sorted(cibles - {f"locator:{lid}"})
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
        if carte_de.get(nid):
            n.proprietes["correspond_a"] = carte_de[nid]
        if communs.get(nid):
            n.proprietes["composant_commun"] = communs[nid]
        if loc.get("scalaire"):  # le nom du fichier de locators n'est pas un écran : rattaché à la carte par sa valeur
            continue
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
                for m in carte_de.get(c, []):  # même élément dans la carte : le test couvre l'écran découvert
                    g.relier(src, m, "utilise", source="dépôt (même locator que la carte)")
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


def _depuis_bdd(g: Graphe, inv: dict):
    """Tests BDD de l'atelier (bdd/*.yaml) : un nœud « scénario » par test BDD, présent avec ou sans Xray, et ses ponts :
    - scénario → vérifie → parcours (le parcours dont il vient) ;
    - scénario → couvre → écran (écrans cités par ses étapes) ;
    - scénario → est implémenté par → test Robot (le test porte l'identifiant du scénario, ou sa clé Xray, en tag) ;
    - test Xray → est formalisé par → scénario (scénario créé depuis le test, ou publié dans Xray) ;
    - scénario → utilise → jeu de données."""
    try:
        from atelier.generation import bdd, conception
    except Exception:  # noqa: BLE001
        return
    try:
        dossier = bdd._dossier()
        fichiers = sorted(dossier.glob("*.yaml")) if dossier.exists() else []
    except Exception:  # noqa: BLE001
        return
    try:
        publiees = conception._publications_xray()
    except Exception:  # noqa: BLE001
        publiees = {}

    def lire(f):
        import yaml as _yaml

        cle = (charger_yaml(f.read_text("utf-8")) or {}).get("cle") or f.stem
        m = bdd.charger(cle) or {}
        return {"cle": cle, "titre": m.get("titre", ""), "statut": m.get("statut", "brouillon")}, m

    lus = []
    for f in fichiers:
        try:
            lus.append(_lu("tests BDD", [f, f.with_suffix(".feature")], lambda f=f: lire(f)))
        except Exception:  # noqa: BLE001 — fichier illisible : ignoré, jamais bloquant
            continue
    par_tag: dict = {}
    for tid, t in (inv.get("tests") or {}).items():
        for tag in t.get("tags") or []:
            par_tag.setdefault(tag, []).append(f"test_robot:{tid}")
    from atelier.integrations.xray import KEY_RE

    par_id_carte = {}
    for n in g.noeuds.values():
        if n.type == "ecran" and n.proprietes.get("id_carte"):
            for i in [n.proprietes["id_carte"], *(n.proprietes.get("ids_fusionnes") or [])]:
                par_id_carte.setdefault(i, n.id)
    for b, m in lus:
        cle = b["cle"]
        cle_xray = (publiees.get(cle) or {}).get("xray") or (cle if KEY_RE.match(cle or "") else "") or m.get("cle_xray") or ""
        sid = f"scenario:{cle}"
        etapes = [e for s in m.get("scenarios", []) for e in s.get("etapes", [])]
        g.noeud(sid, "scenario", b.get("titre") or cle, source=f"bdd/{cle}.yaml",
                proprietes={"statut_bdd": b.get("statut", ""), "origine": m.get("source", ""), "module": m.get("module", ""),
                            "jdd": m.get("jdd", ""), "etapes": len(etapes), "cle_xray": cle_xray,
                            "scenarios": len(m.get("scenarios", []))})
        if m.get("module"):
            g.noeud(f"module:{m['module']}", "module", m["module"], source="bdd")
            g.relier(f"module:{m['module']}", sid, "contient", source="bdd")
        if m.get("parcours"):  # le parcours vient des déclarations (appliquées plus loin) : relié dans _relations_fonctionnelles
            g.noeuds[sid].proprietes["parcours"] = m["parcours"]
        for ref in sorted({e.get("ecran") for e in etapes if e.get("ecran")}):
            cible = f"ecran:{ref}" if f"ecran:{ref}" in g.noeuds else par_id_carte.get(ref, "")  # id technique d'un écran renommé depuis
            if cible:
                g.relier(sid, cible, "couvre", source="bdd (étapes)")
        for tag in {cle, cle_xray} - {""}:
            for tr in par_tag.get(tag, []):
                if tr in g.noeuds:
                    g.relier(sid, tr, "implemente_par", source="dépôt (tag du test)")
        if cle_xray and f"test:{cle_xray}" in g.noeuds:
            g.relier(f"test:{cle_xray}", sid, "formalise_par", source="bdd (clé Xray)")
        if m.get("jdd") and f"jdd:{m['jdd'].upper()}" in g.noeuds:
            g.relier(sid, f"jdd:{m['jdd'].upper()}", "utilise", source="bdd")
        g.noeuds[sid].proprietes["automatise"] = any(r.type == "implemente_par" for r in g.sortants(sid))


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


def _depuis_donnees(g: Graphe):
    """Référentiel de données Discovery : une variable par définition active (jamais sa valeur), ses dépendances, et les
    champs / écrans où elle a réellement servi pendant les sessions (lien observé). Un parcours utilise les variables
    de ses écrans (lien déduit)."""
    from atelier.discovery import donnees

    try:
        vs = donnees.variables()
        liens = donnees.liens_carte()
        profils = donnees.profils_dict()
    except Exception:  # noqa: BLE001 — référentiel illisible : le reste du graphe est construit
        return
    src = "data/discovery/variables.yaml"
    for v in vs:
        g.noeud(f"variable:{v['cle']}", "variable", v["nom"], source=src, provenance="déclaré",
                proprietes={"cle": v["cle"], "description": v["description"], "type": v["type"], "sensibilite": v["sensibilite"],
                            "source_valeur": v["source"]["type"], "regles": v["regles"], "statut": v["statut"],
                            "profils": sorted(p for p, x in profils.items() if v["cle"] in x["variables"]),
                            "utilisations": 0, "sessions": [], "ecrans": []})
    for v in vs:
        for d in v["dependances"]:
            g.relier(f"variable:{v['cle']}", f"variable:{d}", "depend_de", source=src, provenance="déclaré")
    par_nom = {n.libelle: n.id for n in g.noeuds.values() if n.type == "ecran"} | {
        n.proprietes.get("id_carte"): n.id for n in g.noeuds.values() if n.type == "ecran"}
    for l in liens:
        vid, eid = f"variable:{l['cle']}", par_nom.get(l["ecran"])
        if vid not in g.noeuds or not eid:
            continue
        p = g.noeuds[vid].proprietes
        p["utilisations"] += l["utilisations"]
        p["sessions"] = sorted(set(p["sessions"]) | set(l["sessions"]))
        if l["ecran"] not in p["ecrans"]:
            p["ecrans"].append(l["ecran"])
        cid = f"composant:{l['ecran']}.{l['element']}"
        for de in [eid] + ([cid] if l["element"] and cid in g.noeuds else []):  # l'écran toujours, le champ quand il est identifié
            r = g.relier(de, vid, "utilise", provenance="observé", source=f"Discovery ({', '.join(l['sessions']) or 'hors session'})",
                         proprietes={"utilisations": 0, "saisie": False})
            r.proprietes["utilisations"] += l["utilisations"]
            r.proprietes["saisie"] = r.proprietes["saisie"] or l["saisie"]
    for n in [n for n in g.noeuds.values() if n.type == "parcours"]:
        for r in g.sortants(n.id):
            if r.type == "contient" and r.vers.startswith("ecran:"):
                nom = g.noeuds[r.vers].libelle
                for vid, v in [(k, x) for k, x in g.noeuds.items() if x.type == "variable" and nom in x.proprietes.get("ecrans", [])]:
                    g.relier(n.id, vid, "utilise", provenance="déduit", statut="validé", source="variables utilisées sur les écrans du parcours")


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
            d = _json.loads(f.read_text("utf-8")) if f.suffix == ".json" else charger_yaml(f.read_text("utf-8"))
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
    ext = _impact_etendu(g, noeud_id, sources | dependants)
    tous_robot = sorted(set(tests_robot) | set(ext["indirect"]["tests_robot"]))  # direct + indirect, liens confirmés
    sans_cle = [t for t in tests_robot if not g.noeuds[t].proprietes.get("cles_xray")]
    cles = sorted({c for t in tests_robot for c in g.noeuds[t].proprietes.get("cles_xray") or []})
    tags_tnr = _tags_tnr(g, tous_robot)
    fichiers = sorted({g.noeuds[t].proprietes.get("fichier", "") for t in tous_robot})
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
        # TNR, même sans Xray : 1. test Robot relié à un test BDD (son identifiant en tag), 2. relié à un test Xray (clé),
        # 3. tests BDD concernés sans script (à exécuter à la main), 4. tests Xray manuels. Liens confirmés seulement.
        "tnr": {"possible": bool(tags_tnr), "target": cible or ".", "include_tags": tags_tnr,
                "tests_sans_cle_xray": [g.noeuds[t].libelle for t in sans_cle],
                "tests_bdd_manuels": ext["tests_bdd_manuels"], "tests_xray_manuels": ext["tests_xray_manuels"],
                "explication": (f"TNR ciblée : {len(tous_robot)} test(s) Robot concernés, par l'identifiant de leur test BDD ou leur clé Xray."
                                if tags_tnr else "Aucun test automatisé concerné ; voir les tests à exécuter à la main.")},
        "dimensions": ext["dimensions"], "direct": {"tests_robot": tests_robot}, "indirect": ext["indirect"],
        "potentiel": ext["potentiel"],
    }


def _tags_tnr(g: Graphe, tests_robot: list[str]) -> list[str]:
    """Tags qui sélectionnent ces tests Robot : identifiants des tests BDD qu'ils implémentent (lien confirmé), sinon
    leurs clés Xray."""
    tags = set()
    for t in tests_robot:
        bdd = [r.de.split(":", 1)[1] for r in g.entrants(t) if r.type == "implemente_par" and r.de.startswith("scenario:") and r.confirmee]
        tags |= set(bdd) or set(g.noeuds[t].proprietes.get("cles_xray") or [])
    return sorted(tags)


def _impact_etendu(g: Graphe, noeud_id: str, touches: set) -> dict:
    """Impact fonctionnel et utilisateur d'une modification. Direct : ce qui dépend techniquement de l'élément (calculé
    par analyser_impact). Indirect (liens confirmés) : les tests BDD qui couvrent un écran touché ou qui vérifient un
    parcours passant par lui, et leurs tests Robot. Potentiel (suggestions, jamais dans la TNR) : écrans qui mènent à
    un écran touché ou en partent, et les tests BDD qui les couvrent ; liens probables ou non vérifiés."""
    c = g.confirme()
    ecrans = {i for i in touches | {noeud_id} if g.noeuds.get(i) and g.noeuds[i].type == "ecran"}
    for i in list(touches):  # un locator ou un composant touché : son écran
        if g.noeuds.get(i) and g.noeuds[i].type in ("locator", "composant", "action"):
            ecrans |= {r.de for r in c.entrants(i) if r.type in ("contient", "permet") and g.noeuds[r.de].type == "ecran"}
    parcours = {r.de for e in ecrans for r in c.entrants(e) if r.type == "contient" and g.noeuds[r.de].type == "parcours"}
    actions = {r.vers for e in ecrans for r in c.sortants(e) if r.type == "permet"}
    actions |= {r.de for e in ecrans for r in c.entrants(e) if r.type == "aboutit_a"}
    transitions = [{"de": r.de, "vers": r.vers, "action": r.proprietes.get("action", "")}
                   for r in c.relations.values() if r.type == "navigue_vers" and (r.de in ecrans or r.vers in ecrans)]
    fonct = {r.de for e in ecrans for r in c.entrants(e) if g.noeuds[r.de].type in ("fonctionnalite", "user_story", "epic", "regle")}
    fonct |= {r.vers for e in ecrans for r in c.sortants(e) if g.noeuds[r.vers].type in ("fonctionnalite", "user_story", "epic", "regle")}
    fonct |= {r.de for p in parcours for r in c.entrants(p) if g.noeuds[r.de].type in ("fonctionnalite", "user_story", "epic")}
    scen = {r.de for e in ecrans for r in c.entrants(e) if r.type == "couvre" and r.de.startswith("scenario:")}
    scen |= {r.de for p in parcours for r in c.entrants(p) if r.type == "verifie" and r.de.startswith("scenario:")}
    scen |= {r.de for f in fonct for r in c.entrants(f) if r.type == "verifie" and r.de.startswith("scenario:")}
    robots = {r.vers for s in scen for r in c.sortants(s) if r.type == "implemente_par"}
    voisins = {r.de for e in ecrans for r in g.entrants(e) if r.type == "navigue_vers"} | \
              {r.vers for e in ecrans for r in g.sortants(e) if r.type == "navigue_vers"}
    voisins -= ecrans
    scen_pot = {r.de for v in voisins for r in g.entrants(v) if r.type == "couvre" and r.de.startswith("scenario:")} - scen
    scen_pot |= {r.de for e in ecrans for r in g.entrants(e) if r.type == "couvre" and r.de.startswith("scenario:") and not r.confirmee}
    xray_manuels = sorted({r.de for s in scen for r in c.entrants(s) if r.type == "formalise_par"
                           and not g.noeuds[r.de].proprietes.get("automatise")})
    lib = lambda ids: [{"id": i, "libelle": g.noeuds[i].libelle} for i in sorted(ids) if i in g.noeuds]  # noqa: E731
    return {
        "dimensions": {
            "technique": {"elements": lib(i for i in touches if g.noeuds[i].type in ("locator", "keyword", "resource", "composant",
                                                                                     "endpoint", "jdd", "variable", "module"))},
            "fonctionnel": {"elements": lib(fonct), "parcours": lib(parcours)},
            "utilisateur": {"ecrans": lib(ecrans), "actions": lib(actions), "transitions": transitions[:50], "parcours_traverses": lib(parcours)},
        },
        "indirect": {"tests_bdd": lib(scen), "tests_robot": sorted(robots)},
        "potentiel": {"ecrans_voisins": lib(voisins), "tests_bdd": lib(scen_pot),
                      "explication": "Suggestions à examiner : écrans qui mènent à l'élément ou en partent, liens non confirmés. Jamais dans la TNR."},
        "tests_bdd_manuels": [x["libelle"] for x in lib(s for s in scen if not any(r.type == "implemente_par" for r in c.sortants(s)))],
        "tests_xray_manuels": [g.noeuds[i].libelle for i in xray_manuels],
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
    out["construction"] = dict(DERNIERE_CONSTRUCTION)  # durée, sources relues ou réutilisées, volume
    return out
