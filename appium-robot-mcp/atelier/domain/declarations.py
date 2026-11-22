"""Connaissance déclarée par l'automaticien (ou proposée par l'IA), superposée aux graphes observés.

Stockage versionné dans le projet de tests (relu en MR) :
  connaissance/declarations.yaml   nœuds et relations ajoutés, modifications, masquages, fusions
  connaissance/historique.jsonl    une ligne par modification (qui, quand, quoi, avant / après)

Règles :
  - un élément observé n'est jamais effacé de sa source : il est masqué ou annoté ;
  - l'IA (auteur « ia ») ne peut qu'ajouter des propositions « déduit / à valider » ; elle ne
    modifie ni ne supprime un élément validé ;
  - valider une proposition est une action humaine, historisée.
"""
from __future__ import annotations

from atelier.domain.yaml_rapide import charger as charger_yaml

import json
import os
import threading
from datetime import datetime
from pathlib import Path

import yaml

from atelier.domain import projet
from atelier.domain.graphe import Graphe, verifier_type_noeud, verifier_type_relation

AUTEURS = ("automaticien", "ia")
_verrou = threading.Lock()


def _dossier() -> Path:
    return projet.PROJECT_DIR / os.environ.get("CONNAISSANCE_DIR", "connaissance")


def _fichier() -> Path:
    return _dossier() / "declarations.yaml"


def charger() -> dict:
    f = _fichier()
    data = charger_yaml(f.read_text("utf-8")) if f.exists() else None
    data = data or {}
    for k, d in (("noeuds", {}), ("relations", {}), ("modifications", {}), ("masques", []),
                 ("relations_masquees", []), ("fusions", {}), ("rejets", {})):
        data.setdefault(k, d)
    return data


def _sauver(data: dict):
    f = _fichier()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120), "utf-8")
    os.replace(tmp, f)


def _historiser(op: str, auteur: str, cible: str, avant=None, apres=None):
    d = _dossier()
    d.mkdir(parents=True, exist_ok=True)
    with (d / "historique.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": datetime.now().astimezone().isoformat(timespec="seconds"), "op": op,
                             "auteur": auteur, "cible": cible, "avant": avant, "apres": apres},
                            ensure_ascii=False, default=str) + "\n")


def historique(cible: str = "", limite: int = 200) -> list[dict]:
    f = _dossier() / "historique.jsonl"
    if not f.exists():
        return []
    lignes = [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()]
    if cible:
        lignes = [x for x in lignes if cible in (x["cible"] or "")]
    return lignes[-limite:][::-1]


def _auteur(auteur: str):
    if auteur not in AUTEURS:
        raise ValueError(f"Auteur inconnu : {auteur}")


def _proteger(auteur: str, statut: str, cible: str):
    if auteur == "ia" and statut == "validé":
        raise PermissionError(f"L'IA ne peut pas modifier un élément validé sans autorisation ({cible}).")


# =========================================================================== opérations
def ajouter_noeud(id: str, type: str, libelle: str, description: str = "", proprietes: dict | None = None,
                  plateformes: list | None = None, auteur: str = "automaticien") -> dict:
    _auteur(auteur)
    verifier_type_noeud(type)
    if not id.strip():
        raise ValueError("Identifiant obligatoire.")
    with _verrou:
        data = charger()
        if id in data["noeuds"]:
            raise FileExistsError(f"Le nœud {id} existe déjà.")
        if auteur == "ia" and id in data["rejets"]:
            raise PermissionError(f"Proposition {id} rejetée le {data['rejets'][id]['date'][:10]} : jamais reproposée.")
        n = {"type": type, "libelle": libelle, "description": description, "proprietes": proprietes or {},
             "plateformes": plateformes or [],
             "provenance": "déduit" if auteur == "ia" else "déclaré",
             "statut": "à valider" if auteur == "ia" else "validé"}
        data["noeuds"][id] = n
        if id in data["masques"]:
            data["masques"].remove(id)
        _sauver(data)
    _historiser("ajout_noeud", auteur, id, apres=n)
    return {"id": id, **n}


def modifier_noeud(id: str, statut_actuel: str, auteur: str = "automaticien", **champs) -> dict:
    """Modifie libellé, description, propriétés ou statut. Sur un nœud observé, la modification est
    une annotation (la source n'est pas touchée)."""
    _auteur(auteur)
    _proteger(auteur, statut_actuel, id)
    autorises = {"libelle", "description", "proprietes", "statut", "plateformes"}
    champs = {k: v for k, v in champs.items() if k in autorises and v is not None}
    if champs.get("statut") == "validé" and auteur == "ia":
        raise PermissionError("Seul l'automaticien valide une proposition.")
    with _verrou:
        data = charger()
        cible = data["noeuds"].get(id)
        avant = dict(cible) if cible else dict(data["modifications"].get(id, {}))
        if cible is not None:
            cible.update(champs)
        else:
            data["modifications"].setdefault(id, {}).update(champs)
        _sauver(data)
    _historiser("modification_noeud", auteur, id, avant=avant, apres=champs)
    return {"id": id, **champs}


def supprimer_noeud(id: str, statut_actuel: str, auteur: str = "automaticien"):
    _auteur(auteur)
    _proteger(auteur, statut_actuel, id)
    with _verrou:
        data = charger()
        avant = data["noeuds"].pop(id, None)
        if avant is None and id not in data["masques"]:
            data["masques"].append(id)  # nœud observé : masqué, jamais effacé de sa source
        data["relations"] = {k: r for k, r in data["relations"].items() if id not in (r["de"], r["vers"])}
        _sauver(data)
    _historiser("suppression_noeud", auteur, id, avant=avant)


def rejeter(id: str, motif: str = "") -> dict:
    """Décision humaine : la proposition est retirée ET mémorisée comme rejetée ; une analyse ultérieure
    (IA, extraction Jira) ne la repropose jamais. Annulable en la déclarant à nouveau à la main."""
    from datetime import datetime as _dt

    with _verrou:
        data = charger()
        avant = data["noeuds"].get(id) or data["relations"].get(id)
        if avant is None:
            raise KeyError(f"Proposition inconnue : {id}")
        if avant.get("statut") == "validé":
            raise PermissionError("Élément déjà validé : le supprimer explicitement, pas le rejeter.")
        data["noeuds"].pop(id, None)
        data["relations"].pop(id, None)
        if "|" not in id:
            data["relations"] = {k: x for k, x in data["relations"].items() if id not in (x["de"], x["vers"])}
        data["rejets"][id] = {"date": _dt.now().astimezone().isoformat(timespec="seconds"), "motif": motif.strip(),
                              "libelle": avant.get("libelle") or f"{avant.get('de')} → {avant.get('vers')}"}
        _sauver(data)
    _historiser("rejet", "automaticien", id, avant=avant, apres={"motif": motif.strip()})
    return {"id": id, **data["rejets"][id]}


def est_rejete(id: str) -> bool:
    return id in charger()["rejets"]


def ajouter_relation(de: str, vers: str, type: str, auteur: str = "automaticien", source: str = "") -> dict:
    _auteur(auteur)
    verifier_type_relation(type)
    if de == vers:
        raise ValueError("Une relation relie deux nœuds différents.")
    rid = f"{de}|{type}|{vers}"
    if auteur == "ia" and est_rejete(rid):
        raise PermissionError(f"Relation {rid} rejetée : jamais reproposée.")
    r = {"de": de, "vers": vers, "type": type, "source": source,
         "provenance": "déduit" if auteur == "ia" else "déclaré",
         "statut": "à valider" if auteur == "ia" else "validé"}
    with _verrou:
        data = charger()
        data["relations"][rid] = r
        if rid in data["relations_masquees"]:
            data["relations_masquees"].remove(rid)
        _sauver(data)
    _historiser("ajout_relation", auteur, rid, apres=r)
    return {"id": rid, **r}


def valider_relation(rid: str):
    with _verrou:
        data = charger()
        if rid not in data["relations"]:
            raise KeyError(f"Relation {rid} non déclarée.")
        data["relations"][rid]["statut"] = "validé"
        _sauver(data)
    _historiser("validation_relation", "automaticien", rid)


def supprimer_relation(rid: str, statut_actuel: str, auteur: str = "automaticien"):
    _auteur(auteur)
    _proteger(auteur, statut_actuel, rid)
    with _verrou:
        data = charger()
        avant = data["relations"].pop(rid, None)
        if avant is None and rid not in data["relations_masquees"]:
            data["relations_masquees"].append(rid)
        _sauver(data)
    _historiser("suppression_relation", auteur, rid, avant=avant)


def renommer_ecran(ancien: str, nouveau: str) -> int:
    """Un écran renommé (ou fusionné) dans la carte garde ses liens : les identifiants `ecran:<nom>`, `locator:<nom>.…`
    et `composant:<nom>.…` sont réécrits partout dans les déclarations. Renvoie le nombre de relations reportées (0 : rien à reporter)."""
    def m(i: str) -> str:
        if i == f"ecran:{ancien}":
            return f"ecran:{nouveau}"
        for p in ("locator", "composant"):
            if i.startswith(f"{p}:{ancien}."):
                return f"{p}:{nouveau}." + i[len(f"{p}:{ancien}."):]
        return i

    def mr(i: str) -> str:
        parts = i.split("|")
        return "|".join((m(parts[0]), parts[1], m(parts[2]))) if len(parts) == 3 else m(i)

    if not ancien or ancien == nouveau:
        return 0
    with _verrou:
        data = charger()
        avant = json.dumps(data, sort_keys=True, default=str)
        data["noeuds"] = {m(k): v for k, v in data["noeuds"].items()}
        data["relations"] = {mr(k): {**v, "de": m(v["de"]), "vers": m(v["vers"])} for k, v in data["relations"].items()}
        data["modifications"] = {mr(k): v for k, v in data["modifications"].items()}
        data["masques"] = [m(x) for x in data["masques"]]
        data["relations_masquees"] = [mr(x) for x in data["relations_masquees"]]
        data["fusions"] = {m(k): m(v) for k, v in data["fusions"].items()}
        data["rejets"] = {mr(k): v for k, v in data["rejets"].items()}
        apres = json.dumps(data, sort_keys=True, default=str)
        if avant == apres:
            return 0
        _sauver(data)
    n = sum(1 for k in json.loads(apres)["relations"] if k not in json.loads(avant)["relations"]) or 1
    _historiser("renommage_ecran", "automaticien", f"ecran:{ancien}", apres={"nouveau": f"ecran:{nouveau}", "relations": n})
    return n


def fusionner(source: str, cible: str, auteur: str = "automaticien"):
    _auteur(auteur)
    if auteur == "ia":
        raise PermissionError("Une fusion est une décision de l'automaticien.")
    with _verrou:
        data = charger()
        data["fusions"][source] = cible
        _sauver(data)
    _historiser("fusion", auteur, source, apres={"cible": cible})


# =========================================================================== application
def appliquer(g: Graphe, data: dict | None = None) -> Graphe:
    """Superpose les déclarations au graphe observé (ordre : ajouts, annotations, fusions, masques)."""
    data = data or charger()
    for id, n in data["noeuds"].items():
        g.noeud(id, n["type"], n["libelle"], proprietes={**(n.get("proprietes") or {}),
                                                         "description": n.get("description", "")},
                plateformes=n.get("plateformes") or [], provenance=n.get("provenance", "déclaré"),
                source=(n.get("proprietes") or {}).get("source_libelle") or "déclaration", statut=n.get("statut", "validé"),
                confiance=1.0 if n.get("provenance") != "déduit" else 0.5)
    for id, champs in data["modifications"].items():
        n = g.noeuds.get(id)
        if not n:
            continue
        if "libelle" in champs:
            n.libelle = champs["libelle"]
        if "statut" in champs:
            n.statut = champs["statut"]
        if "plateformes" in champs:
            n.plateformes = list(champs["plateformes"])
        n.proprietes.update({k: v for k, v in (champs.get("proprietes") or {}).items()})
        if "description" in champs:
            n.proprietes["description"] = champs["description"]
        n.proprietes["annote"] = True
    for r in data["relations"].values():
        g.relier(r["de"], r["vers"], r["type"], provenance=r.get("provenance", "déclaré"),
                 source=r.get("source") or "déclaration", statut=r.get("statut", "validé"))
    for source, cible in data["fusions"].items():
        if source in g.noeuds and cible in g.noeuds:
            g.fusionner(source, cible)
    for id in data["masques"]:
        g.retirer_noeud(id)
    for rid in data["relations_masquees"]:
        g.relations.pop(rid, None)
    return g
