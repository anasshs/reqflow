"""Test Design › Règles de test (cahier Test Design, écran 06).

Une règle de test est un nœud « regle » du Knowledge Graph (une seule source : les règles candidates extraites des
critères Jira par Application Intelligence sont les mêmes objets). Elle porte une catégorie, une logique, des
conditions, des résultats attendus et des paramètres ; elle est reliée aux exigences (exigence -contient-> règle) et
aux tests Xray (règle -teste_par-> test). Les cas limites sont générés à partir des paramètres, comme propositions ;
leur création dans Xray est une action explicite (test Manual), liée aux exigences de la règle.
Une proposition (IA, extraction) reste « à valider » : jamais utilisée pour une décision avant validation humaine.
"""
from __future__ import annotations

import os
import re
from decimal import Decimal, InvalidOperation

from atelier.domain import declarations

CATEGORIES = ["Métier", "Validation", "Calcul", "Sécurité fonctionnelle", "Gestion des données", "Workflow"]
TYPES_PARAMETRE = {"nombre": "Nombre (bornes min / max)", "liste": "Liste de valeurs autorisées", "obligatoire": "Condition obligatoire",
                   "texte": "Valeur fixe"}


def _id(nom: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", nom.lower().encode("ascii", "ignore").decode()).strip("_")[:50] or "regle"
    return f"regle:{s}"


def _graphe():
    from atelier.discovery import connaissance

    return connaissance.construire()


def _exigence_id(cle: str, g) -> str:
    return next((f"{t}:{cle}" for t in ("user_story", "epic", "bug") if f"{t}:{cle}" in g.noeuds), f"user_story:{cle}")


def _parametres(l: list[dict]) -> list[dict]:
    out = []
    for p in l or []:
        nom = str(p.get("nom") or "").strip()
        if not nom:
            continue
        t = p.get("type") if p.get("type") in TYPES_PARAMETRE else "texte"
        x = {"nom": nom, "type": t, "unite": str(p.get("unite") or "").strip()}
        if t == "nombre":
            for k in ("min", "max"):
                v = str(p.get(k) if p.get(k) is not None else "").strip().replace(",", ".")
                if v:
                    try:
                        Decimal(v)
                    except InvalidOperation:
                        raise ValueError(f"Paramètre « {nom} » : {k} doit être un nombre.") from None
                x[k] = v
            if "min" in x and "max" in x and Decimal(x["min"]) > Decimal(x["max"]):
                raise ValueError(f"Paramètre « {nom} » : min supérieur à max.")
        elif t == "liste":
            vals = p.get("valeurs")
            x["valeurs"] = [v.strip() for v in (vals.split(",") if isinstance(vals, str) else vals or []) if str(v).strip()]
        elif t == "texte":
            x["valeur"] = str(p.get("valeur") or "").strip()
        out.append(x)
    return out


# =========================================================================== lecture
def lister() -> list[dict]:
    g = _graphe()
    rels = list(declarations.charger()["relations"].values())
    out = []
    for n in g.noeuds.values():
        if n.type != "regle":
            continue
        pr = n.proprietes or {}
        # liens lus dans les déclarations : un test tout juste créé dans Xray (absent de l'instantané) compte déjà
        exig = sorted({r["de"].split(":", 1)[1] for r in rels if r["vers"] == n.id and r["type"] == "contient"
                       and r["de"].split(":", 1)[0] in ("user_story", "epic", "bug")})
        tests = sorted({r["vers"].split(":", 1)[1] for r in rels if r["de"] == n.id and r["type"] == "teste_par"})
        out.append({"id": n.id, "nom": n.libelle, "statut": n.statut, "provenance": n.provenance,
                    "categorie": pr.get("categorie", ""), "logique": pr.get("logique") or pr.get("description", ""),
                    "conditions": pr.get("conditions") or ([pr["condition"]] if pr.get("condition") else []),
                    "resultats": pr.get("resultats") or ([pr["resultat_attendu"]] if pr.get("resultat_attendu") else []),
                    "parametres": pr.get("parametres") or [], "exigences": exig, "tests": tests,
                    "source": pr.get("ticket_source", ""), "extrait": pr.get("extrait", ""),
                    "couverte": bool(tests)})
    return sorted(out, key=lambda r: (r["statut"] != "validé", r["nom"].lower()))


def detail(rid: str) -> dict:
    r = next((x for x in lister() if x["id"] == rid), None)
    if not r:
        raise KeyError(f"Règle inconnue : {rid}")
    return {**r, "cas_limites": cas_limites(r)}


def indicateurs() -> dict:
    l = lister()
    valides = [r for r in l if r["statut"] == "validé"]
    return {"regles": len(l), "validees": len(valides), "a_valider": len(l) - len(valides),
            "couvertes": sum(r["couverte"] for r in valides), "non_couvertes": [r["id"] for r in valides if not r["couverte"]],
            "par_categorie": {c: sum(r["categorie"] == c for r in l) for c in CATEGORIES}}


# =========================================================================== écriture (automaticien)
def enregistrer(r: dict) -> dict:
    """Crée (sans id) ou met à jour une règle ; liens exigences / tests synchronisés en relations du graphe."""
    nom = str(r.get("nom") or "").strip()
    if not nom:
        raise ValueError("Nom de la règle obligatoire.")
    if r.get("categorie") and r["categorie"] not in CATEGORIES:
        raise ValueError(f"Catégorie : {', '.join(CATEGORIES)}.")
    proprietes = {"categorie": r.get("categorie", ""), "logique": str(r.get("logique") or "").strip(),
                  "conditions": [c.strip() for c in r.get("conditions") or [] if str(c).strip()],
                  "resultats": [c.strip() for c in r.get("resultats") or [] if str(c).strip()],
                  "parametres": _parametres(r.get("parametres") or [])}
    data = declarations.charger()
    rid = r.get("id") or _id(nom)
    if rid in data["noeuds"]:
        n = data["noeuds"][rid]
        declarations.modifier_noeud(rid, n.get("statut", "validé"), libelle=nom, description=proprietes["logique"],
                                    proprietes={**(n.get("proprietes") or {}), **proprietes})
    elif r.get("id"):
        raise KeyError(f"Règle inconnue : {rid}")
    else:
        while rid in data["noeuds"]:
            rid += "_2"
        declarations.ajouter_noeud(rid, "regle", nom, description=proprietes["logique"], proprietes=proprietes)
    lier(rid, r.get("exigences"), r.get("tests"))
    return detail(rid)


def lier(rid: str, exigences: list[str] | None = None, tests: list[str] | None = None):
    """Aligne les relations déclarées de la règle sur les listes données (None = inchangé)."""
    g = _graphe()
    data = declarations.charger()
    for cles, type_rel, sens in ((exigences, "contient", "entrant"), (tests, "teste_par", "sortant")):
        if cles is None:
            continue
        voulues = {str(k).strip().upper() for k in cles if str(k).strip()}
        actuelles = {rel_id: rel for rel_id, rel in data["relations"].items() if rel["type"] == type_rel
                     and ((sens == "entrant" and rel["vers"] == rid) or (sens == "sortant" and rel["de"] == rid))}
        for rel_id, rel in actuelles.items():
            autre = (rel["de"] if sens == "entrant" else rel["vers"]).split(":", 1)[1]
            if autre not in voulues:
                declarations.supprimer_relation(rel_id, rel.get("statut", "validé"))
        presentes = {(rel["de"] if sens == "entrant" else rel["vers"]).split(":", 1)[1] for rel in actuelles.values()}
        for k in voulues - presentes:
            if sens == "entrant":
                declarations.ajouter_relation(_exigence_id(k, g), rid, "contient", source="Règles de test")
            else:
                declarations.ajouter_relation(rid, f"test:{k}", "teste_par", source="Règles de test")


def supprimer(rid: str):
    data = declarations.charger()
    n = data["noeuds"].get(rid)
    if not n:
        raise KeyError(f"Règle déclarée inconnue : {rid}")
    declarations.supprimer_noeud(rid, n.get("statut", "validé"))
    return {"supprimee": rid}


# =========================================================================== cas limites (propositions)
def _pas(*valeurs: str) -> Decimal:
    dec = max((len(v.split(".")[1]) if "." in v else 0) for v in valeurs if v)
    return Decimal(1).scaleb(-dec) if dec else Decimal(1)


def cas_limites(r: dict) -> list[dict]:
    """Valeurs aux bornes et cas de refus, par paramètre, les autres paramètres restant nominaux.
    nombre : min − pas (refusé), min, nominal, max (acceptés), max + pas (refusé) ; liste : une valeur autorisée
    (acceptée), une valeur hors liste (refusée) ; obligatoire : condition non remplie (refusée)."""
    params = r.get("parametres") or []
    nominal = {}
    for p in params:
        if p["type"] == "nombre":
            lo, hi = p.get("min"), p.get("max")
            nominal[p["nom"]] = str(((Decimal(lo) + Decimal(hi)) / 2).quantize(_pas(lo, hi))) if lo and hi else (lo or hi or "valeur valide")
        elif p["type"] == "liste":
            nominal[p["nom"]] = (p.get("valeurs") or ["valeur autorisée"])[0]
        elif p["type"] == "obligatoire":
            nominal[p["nom"]] = "oui"
        else:
            nominal[p["nom"]] = p.get("valeur") or ""
    resultat_ok = "; ".join(r.get("resultats") or []) or "opération acceptée"
    out = []

    def cas(param, valeur, accepte, libelle):
        u = f" {param.get('unite')}" if param.get("unite") and param["type"] == "nombre" else ""
        out.append({"id": f"{param['nom']}|{valeur}", "titre": f"{r['nom']} — {param['nom']} = {valeur}{u} ({libelle})",
                    "donnees": {**nominal, param["nom"]: valeur}, "attendu": "accepté" if accepte else "refusé",
                    "resultat": resultat_ok if accepte else f"refus explicite : {param['nom']} {libelle}"})

    for p in params:
        if p["type"] == "nombre":
            lo, hi = p.get("min"), p.get("max")
            pas = _pas(lo or "", hi or "")
            if lo:
                cas(p, str(Decimal(lo) - pas), False, "sous le minimum")
                cas(p, lo, True, "minimum")
            if lo and hi:
                cas(p, nominal[p["nom"]], True, "valeur nominale")
            if hi:
                cas(p, hi, True, "maximum")
                cas(p, str(Decimal(hi) + pas), False, "au-dessus du maximum")
        elif p["type"] == "liste" and p.get("valeurs"):
            cas(p, p["valeurs"][0], True, "valeur autorisée")
            cas(p, "VALEUR_HORS_LISTE", False, "hors des valeurs autorisées")
        elif p["type"] == "obligatoire":
            cas(p, "non", False, "condition non remplie")
    return out


def creer_cas_xray(rid: str, ids_cas: list[str], projet: str = "", xray=None, jira=None) -> dict:
    """Crée dans Xray (test Manual) les cas limites choisis, liés à la règle et à ses exigences. Action explicite."""
    from atelier.domain import projets
    from atelier.integrations.jira import JiraClient
    from atelier.integrations.xray import XrayClient

    r = detail(rid)
    if r["statut"] != "validé":
        raise PermissionError("Règle à valider : la valider avant de créer des tests à partir d'elle.")
    choisis = [c for c in r["cas_limites"] if c["id"] in set(ids_cas)]
    if not choisis:
        raise ValueError("Aucun cas limite choisi.")
    projet = projet or projets.cle_xray()
    if not projet:
        raise ValueError("Projet Xray requis.")
    xray, jira = xray or XrayClient(), jira or JiraClient()
    lien = os.environ.get("JIRA_LIEN_COUVERTURE", "Test")
    crees, erreurs = [], []
    for c in choisis:
        etapes = [{"action": "Préparer les données : " + ", ".join(f"{k} = {v}" for k, v in c["donnees"].items()), "donnees": "",
                   "resultat": "Données prêtes"},
                  {"action": f"Appliquer la règle « {r['nom']} »" + (f" ({r['logique'][:150]})" if r.get("logique") else ""), "donnees": "",
                   "resultat": c["resultat"]}]
        try:
            t = xray.creer_test_manuel(projet, c["titre"][:250], etapes)
            crees.append(t["cle"])
            for e in r["exigences"]:
                try:
                    jira.link(t["cle"], e, lien)
                except Exception as le:  # noqa: BLE001 - test créé : lien manquant signalé
                    erreurs.append({"cas": c["id"], "erreur": f"lien {e} : {str(le)[:150]}"})
        except Exception as ex:  # noqa: BLE001
            erreurs.append({"cas": c["id"], "erreur": str(ex)[:300]})
    if crees:
        lier(rid, None, sorted(set(r["tests"]) | set(crees)))
    return {"crees": crees, "erreurs": erreurs, "regle": detail(rid)}


# =========================================================================== propositions
def proposer_depuis_exigences() -> dict:
    """Règles candidates extraites des critères d'acceptation Jira (motifs explicites, sans IA), « à valider »."""
    from atelier.discovery import intelligence_app

    avant = {r["id"] for r in lister()}
    intelligence_app.analyser_jira(proposer=True)
    nouvelles = [r for r in lister() if r["id"] not in avant]
    return {"proposees": len(nouvelles), "regles": [r["id"] for r in nouvelles]}
