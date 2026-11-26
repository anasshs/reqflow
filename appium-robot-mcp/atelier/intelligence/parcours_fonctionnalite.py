"""Parcours de fonctionnalité (V2, phase 1) : workflow métier LÉGER qui suit le cycle de vie d'une fonctionnalité,
de la Discovery à la synchronisation Xray. Ce n'est pas un agent : chaque étape est réalisée par un module existant
(depuis le web ou par Cursor via ses outils MCP) ; le parcours en garde l'état, les références, les validations et
l'historique, et indique ce qui bloque.

Règles :
- une étape RÉFÉRENCE les objets des modules (session Discovery, exigences, scénarios BDD, suites, runs, échecs,
  exécutions Xray…), elle ne les recopie pas ;
- une étape ne démarre que si ses prérequis sont validés ou sautés (dépendances bloquantes affichées) ;
- sauter une étape exige une justification ; revenir à une étape conserve les résultats suivants, marqués « à revoir » ;
- les étapes de décision humaine (validation des scénarios, qualification, synchronisation Xray) ne se valident que
  dans l'atelier : depuis Cursor (MCP) elles passent « en attente de validation » (contrôle côté serveur) ;
- chaque changement est historisé ; une version (instantané des étapes) est gardée à chaque validation, pour comparer.

Stockage : <projet>/parcours/<id>.json (état de travail de l'atelier, isolé par projet).
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime

from atelier.domain import evenements, projet

ETAPES = [  # id, titre, rôle, écran de l'atelier, outils MCP utiles, validation humaine obligatoire (web)
    ("discovery", "Discovery", "Explorer les écrans et parcours de la fonctionnalité", "discovery/studio",
     ["discovery_demarrer", "discovery_ecran_courant", "discovery_proposer", "discovery_terminer"], False),
    ("reconstruction", "Reconstruction fonctionnelle", "Comprendre la fonctionnalité (Stories et critères reconstruits si absents)",
     "intelligence/couverture", ["coverage_intelligence", "coverage_proposer_story"], False),
    ("couverture", "Couverture existante", "Ce qui est déjà couvert : exigences, tests Xray, tests manquants et orphelins",
     "intelligence/couverture", ["coverage_intelligence", "coverage_report", "cerveau_application"], False),
    ("conception", "Test Design", "Concevoir les cas de test manquants", "conception/us",
     ["testabilite_us_a_traiter", "testabilite_deposer_proposition", "plan_de_test", "studio_rapprocher_etapes", "studio_keywords_a_juger", "studio_juger_keywords"], False),
    ("validation", "Validation des scénarios", "Revue et validation humaine des scénarios (BDD, cas)", "conception/cas", [], True),
    ("generation", "Génération des scripts", "Construire les tests Robot depuis le socle existant", "studio/direct",
     ["studio_socle", "studio_scenario_bdd", "studio_generer_depuis_bdd", "studio_construire_test"], False),
    ("qualification", "Qualification des scripts", "Revue technique et 3 exécutions stables", "studio/revue",
     ["studio_revue", "studio_soumettre_revue"], True),
    ("execution", "Exécution", "Lancer les tests sur les environnements et appareils choisis", "centre/selection",
     ["run_robot", "check_jdd"], False),
    ("analyse", "Failure Analysis", "Analyser et classer les échecs", "echecs/inbox", ["parse_robot_output"], False),
    ("synchronisation", "Synchronisation Xray et Knowledge Graph", "Résultats dans Xray, connaissances validées dans le graphe",
     "intelligence/a_valider", ["import_results_to_xray", "knowledge_graph"], True),
]
IDS = [e[0] for e in ETAPES]
STATUTS_ETAPE = ("À faire", "En cours", "En attente de validation", "Validée", "Échouée", "Bloquée", "Sautée")
STATUTS_PARCOURS = ("Draft", "In Progress", "Waiting for Validation", "Blocked", "Suspended", "Completed", "Abandoned")
FAITES = ("Validée", "Sautée")


# =========================================================================== stockage
def _dossier():
    return projet.PROJECT_DIR / "parcours"


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _auteur(origine: str = "") -> str:
    from atelier.domain import roles

    return "cursor" if origine == "mcp" else roles.utilisateur()


def _sauver(p: dict, evenement: str = ""):
    from atelier.intelligence.strategie import _ecrire_atomique

    p["statut"] = statut_global(p)
    p["maj_le"] = _maintenant()
    _dossier().mkdir(parents=True, exist_ok=True)
    _ecrire_atomique(_dossier() / f"{p['id']}.json", json.dumps(p, ensure_ascii=False, indent=1, default=str))
    evenements.publier({"type": "parcours_change", "id": p["id"], "evenement": evenement})


def _lire(pid: str) -> dict:
    if not re.fullmatch(r"PF-[0-9]{8}-[0-9a-f]{6}", pid or ""):
        raise KeyError(f"Parcours inconnu : {pid}")
    f = _dossier() / f"{pid}.json"
    if not f.exists():
        raise KeyError(f"Parcours inconnu : {pid}")
    return json.loads(f.read_text("utf-8"))


def _histo(p: dict, action: str, etape: str = "", origine: str = "", **details):
    p["historique"].append({"date": _maintenant(), "par": _auteur(origine), "origine": origine or "web", "action": action,
                            "etape": etape, **{k: v for k, v in details.items() if v not in ("", None)}})


def _etape(p: dict, eid: str) -> dict:
    e = next((x for x in p["etapes"] if x["id"] == eid), None)
    if not e:
        raise KeyError(f"Étape inconnue : {eid} ({', '.join(IDS)})")
    return e


# =========================================================================== statut et dépendances
def statut_global(p: dict) -> str:
    if p.get("abandonne"):
        return "Abandoned"
    if p.get("suspendu"):
        return "Suspended"
    st = [e["statut"] for e in p["etapes"]]
    if all(s in FAITES for s in st):
        return "Completed"
    if "Bloquée" in st or "Échouée" in st:
        return "Blocked"
    if "En attente de validation" in st:
        return "Waiting for Validation"
    if any(s != "À faire" for s in st):
        return "In Progress"
    return "Draft"


def dependances_bloquantes(p: dict, eid: str) -> list[str]:
    """Prérequis (étapes précédentes) ni validés ni sautés."""
    e = _etape(p, eid)
    return [x for x in e["prerequis"] if _etape(p, x)["statut"] not in FAITES]


def _modifiable(p: dict):
    if p.get("abandonne"):
        raise ValueError("Parcours abandonné : lecture seule.")
    if p.get("suspendu"):
        raise ValueError("Parcours suspendu : le reprendre d'abord.")


# =========================================================================== création, lecture
def creer(fonctionnalite: str, libelle: str = "", jira: list[str] | None = None, responsable: str = "", origine: str = "") -> dict:
    """Nouveau parcours pour une fonctionnalité (nœud du Knowledge Graph « module:… » / « fonctionnalite:… », ou nom).
    Idempotent : un parcours ouvert existe déjà pour cette fonctionnalité → il est renvoyé."""
    f = (fonctionnalite or "").strip()
    if not f:
        raise ValueError("Fonctionnalité obligatoire (nœud du Knowledge Graph ou nom du module).")
    if ":" not in f:
        f = f"module:{f}"
    cles = sorted({k.strip().upper() for k in jira or [] if k.strip()})
    if any(not re.fullmatch(r"[A-Z][A-Z0-9_]*-\d+", k) for k in cles):
        raise ValueError("Références Jira attendues sous la forme CLE-123.")
    deja = next((x for x in lister() if x["fonctionnalite"] == f and x["statut"] not in ("Completed", "Abandoned")), None)
    if deja:
        return obtenir(deja["id"])
    try:
        from atelier.discovery import carte

        app = carte.config_app().get("nom", "")
    except Exception:  # noqa: BLE001 — aucune application cartographiée
        app = ""
    p = {"id": f"PF-{datetime.now():%Y%m%d}-{secrets.token_hex(3)}", "projet": projet.PROJECT_DIR.name, "application": app,
         "fonctionnalite": f, "libelle": (libelle or f.split(":", 1)[1]).strip(), "jira": cles, "version": 1,
         "responsable": responsable.strip() or _auteur(origine), "cree_le": _maintenant(), "suspendu": False, "abandonne": False,
         "etapes": [{"id": eid, "numero": i + 1, "titre": t, "role": r, "ecran": ec, "outils_mcp": o, "validation_humaine": h,
                     "prerequis": [IDS[i - 1]] if i else [], "statut": "À faire", "references": [], "resultat": "",
                     "validation": None, "a_revoir": False, "date": "", "historique": []}
                    for i, (eid, t, r, ec, o, h) in enumerate(ETAPES)],
         "historique": [], "versions": []}
    _histo(p, "création", origine=origine, fonctionnalite=f)
    _sauver(p, "création")
    return obtenir(p["id"])


def lister() -> list[dict]:
    if not _dossier().exists():
        return []
    out = []
    for f in sorted(_dossier().glob("PF-*.json"), reverse=True):
        try:
            p = json.loads(f.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        faites = sum(e["statut"] in FAITES for e in p["etapes"])
        courante = next((e for e in p["etapes"] if e["statut"] not in FAITES), None)
        out.append({"id": p["id"], "fonctionnalite": p["fonctionnalite"], "libelle": p["libelle"], "jira": p["jira"],
                    "statut": statut_global(p), "avancement": f"{faites}/{len(p['etapes'])}", "etape_courante": courante and courante["titre"],
                    "responsable": p["responsable"], "maj_le": p.get("maj_le", ""), "version": p["version"]})
    return out


def obtenir(pid: str) -> dict:
    """Parcours complet + dépendances bloquantes et indices constatés dans les modules (lecture seule)."""
    p = _lire(pid)
    p["statut"] = statut_global(p)
    for e in p["etapes"]:
        e["bloquee_par"] = dependances_bloquantes(p, e["id"])
    p["indices"] = indices(p)
    return p


# =========================================================================== actions sur une étape
ACTIONS = ("demarrer", "referencer", "soumettre", "valider", "sauter", "echouer", "bloquer", "revenir")


def agir(pid: str, eid: str, action: str, commentaire: str = "", reference: dict | None = None, origine: str = "") -> dict:
    """Une action sur une étape. origine « mcp » : appel depuis Cursor (les étapes de décision humaine n'y sont pas
    validables : elles passent en attente de validation)."""
    if action not in ACTIONS:
        raise ValueError(f"Action inconnue : {action} ({', '.join(ACTIONS)}).")
    p = _lire(pid)
    _modifiable(p)
    e = _etape(p, eid)
    bloquantes = dependances_bloquantes(p, eid)
    commentaire = (commentaire or "").strip()

    def changer(statut: str, detail: str = ""):
        avant = e["statut"]
        e["statut"], e["date"] = statut, _maintenant()
        e["historique"].append({"date": e["date"], "par": _auteur(origine), "origine": origine or "web", "de": avant, "vers": statut,
                                "commentaire": detail})

    if action in ("demarrer", "soumettre", "valider") and bloquantes:
        raise PermissionError(f"Étape « {e['titre']} » bloquée par : {', '.join(_etape(p, b)['titre'] for b in bloquantes)}.")
    if action == "demarrer":
        changer("En cours", commentaire)
    elif action == "referencer":
        r = reference or {}
        if not (r.get("type") and r.get("id")):
            raise ValueError("Référence : type et id obligatoires (ex. {type: 'run', id: 'RUN-…'}).")
        ref = {"type": str(r["type"])[:40], "id": str(r["id"])[:120], "libelle": str(r.get("libelle") or "")[:200]}
        if not any(x["type"] == ref["type"] and x["id"] == ref["id"] for x in e["references"]):  # idempotent
            e["references"].append({**ref, "ajoute_le": _maintenant(), "par": _auteur(origine)})
        if e["statut"] == "À faire" and not bloquantes:
            changer("En cours", "référence ajoutée")
    elif action == "soumettre":
        e["resultat"] = commentaire or e["resultat"]
        changer("En attente de validation", commentaire)
    elif action == "valider":
        if e["validation_humaine"] and origine == "mcp":  # contrôle côté serveur : décision humaine dans l'atelier
            e["resultat"] = commentaire or e["resultat"]
            changer("En attente de validation", "validation humaine requise dans l'atelier")
            _histo(p, "validation demandée", eid, origine, commentaire=commentaire)
            _sauver(p, "validation demandée")
            return obtenir(pid)
        from atelier.domain import roles

        roles.exiger("decider_revue" if e["validation_humaine"] else "construire")
        changer("Validée", commentaire)
        e["validation"] = {"par": _auteur(origine), "date": e["date"], "commentaire": commentaire}
        e["a_revoir"] = False
        p["version"] += 1
        p["versions"].append({"version": p["version"], "date": e["date"], "par": _auteur(origine), "raison": f"étape « {e['titre']} » validée",
                              "etapes": {x["id"]: {"statut": x["statut"], "references": [f"{r['type']}:{r['id']}" for r in x["references"]]}
                                         for x in p["etapes"]}})
    elif action == "sauter":
        if len(commentaire) < 10:
            raise ValueError("Sauter une étape exige une justification (10 caractères minimum).")
        changer("Sautée", commentaire)
    elif action in ("echouer", "bloquer"):
        if not commentaire:
            raise ValueError("Motif obligatoire.")
        changer("Échouée" if action == "echouer" else "Bloquée", commentaire)
    elif action == "revenir":  # relancer cette étape ; les suivantes déjà faites sont gardées et marquées à revoir
        changer("En cours", commentaire or "reprise de l'étape")
        for x in p["etapes"][IDS.index(eid) + 1:]:
            if x["statut"] in FAITES or x["statut"] == "En attente de validation":
                x["a_revoir"] = True
    _histo(p, action, eid, origine, commentaire=commentaire, reference=(reference or {}).get("id"))
    _sauver(p, action)
    return obtenir(pid)


def changer_etat(pid: str, action: str, motif: str = "", origine: str = "") -> dict:
    """suspendre / reprendre / abandonner le parcours (rien n'est perdu)."""
    p = _lire(pid)
    if p.get("abandonne"):
        raise ValueError("Parcours abandonné : lecture seule.")
    if action == "suspendre":
        p["suspendu"] = True
    elif action == "reprendre":
        p["suspendu"] = False
    elif action == "abandonner":
        if len((motif or "").strip()) < 10:
            raise ValueError("Abandonner exige une justification (10 caractères minimum).")
        p["abandonne"] = True
    else:
        raise ValueError("Action : suspendre, reprendre ou abandonner.")
    _histo(p, action, origine=origine, commentaire=(motif or "").strip())
    _sauver(p, action)
    return obtenir(pid)


def comparer(pid: str, a: int, b: int | None = None) -> dict:
    """Différences d'état des étapes entre deux versions (b absent : état courant)."""
    p = _lire(pid)
    va = next((v for v in p["versions"] if v["version"] == int(a)), None)
    if not va:
        raise KeyError(f"Version {a} inconnue (versions : {', '.join(str(v['version']) for v in p['versions']) or 'aucune'}).")
    courant = {x["id"]: {"statut": x["statut"], "references": [f"{r['type']}:{r['id']}" for r in x["references"]]} for x in p["etapes"]}
    vb = courant if b in (None, "") else next((v["etapes"] for v in p["versions"] if v["version"] == int(b)), None)
    if vb is None:
        raise KeyError(f"Version {b} inconnue.")
    diff = []
    for eid in IDS:
        x, y = va["etapes"].get(eid, {}), vb.get(eid, {})
        if x != y:
            diff.append({"etape": eid, "titre": _etape(p, eid)["titre"], "avant": x.get("statut"), "apres": y.get("statut"),
                         "references_ajoutees": sorted(set(y.get("references", [])) - set(x.get("references", []))),
                         "references_retirees": sorted(set(x.get("references", [])) - set(y.get("references", [])))})
    return {"parcours": pid, "a": int(a), "b": b or "courant", "differences": diff}


# =========================================================================== indices constatés dans les modules
def indices(p: dict) -> dict:
    """Ce que les modules montrent déjà pour cette fonctionnalité (aide à décider, jamais une validation automatique)."""
    out: dict = {}
    nom = p["libelle"].lower()
    try:
        from atelier.discovery import carte

        ecr = [e for e in carte.ecrans() if (e.get("module") or "").lower() == nom]
        out["discovery"] = f"{len(ecr)} écran(s) du module dans la carte" + (f" : {', '.join((e.get('nom') or e['id']) for e in ecr[:6])}" if ecr else "")
    except Exception:  # noqa: BLE001 — module sans carte : pas d'indice
        pass
    if p["jira"]:
        try:
            from atelier.intelligence import testabilite_us

            us = testabilite_us._us()
            vus = {k: us[k].get("statut") or "Détectée" for k in p["jira"] if k in us}
            out["conception"] = "; ".join(f"{k} : {s}" for k, s in vus.items()) or "aucune des références Jira n'est dans « À concevoir »"
        except Exception:  # noqa: BLE001
            pass
        try:
            from atelier.generation import studio

            inv, rev = studio._inv(), studio.revues_scripts()
            suites = sorted({t["fichier"] for t in inv["tests"].values() if set(t.get("cles_xray") or []) & set(p["jira"])})
            if suites:
                out["generation"] = f"{len(suites)} suite(s) portant ces clés : " + ", ".join(suites[:5])
                out["qualification"] = "; ".join(f"{s} : {(rev.get(s) or {}).get('statut', 'Generated')}" for s in suites[:5])
        except Exception:  # noqa: BLE001
            pass
    return out
