"""Behavior Model : comment l'application doit se comporter, sur un périmètre (cahier MBT, § 6).

Distinct du Knowledge Graph (ce que l'atelier connaît) et du modèle de test (comment le vérifier : atelier/intelligence/mbt.py).
Un modèle par périmètre, dans le projet de tests :
  comportement/<id>.yaml                    version courante
  comportement/versions/<id>/v<n>.yaml      versions précédentes (jamais réécrites)

Éléments : états, transitions, actions, conditions. Chacun garde sa provenance (observé / déclaré / déduit), sa
validation (validé / à valider / rejeté), sa confiance (confirmée / probable / non vérifiée : calculée, indépendante de
la provenance), sa source, sa justification, ses dates et son auteur. Une proposition (calcul ou IA) n'est jamais
validée automatiquement ; un élément rejeté reste connu (pour ne pas être reproposé) mais n'est plus exploité.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime

import yaml

from atelier.domain import projet

STATUTS = ("Draft", "In Review", "Validated", "Deprecated")
LIBELLES_STATUT = {"Draft": "Brouillon", "In Review": "En revue", "Validated": "Validé", "Deprecated": "Obsolète"}
TYPES_ETAT = {"metier": "État métier", "ecran": "État d'écran", "systeme": "État système", "erreur": "État d'erreur"}
TYPES_PERIMETRE = ("application", "module", "fonctionnalite", "parcours", "user_story", "ecran", "regle")
COLLECTIONS = ("etats", "transitions", "actions", "conditions")
PROVENANCES = ("observé", "déclaré", "déduit")
VALIDATIONS = ("validé", "à valider", "rejeté")
PRIORITES = ("haute", "normale", "basse")
# niveau de confiance d'un élément (cahier d'évolution § 2) : seuls « Confirmé » et « Observé » sont ÉTABLIS (couverture,
# impact et TNR officiels) ; « Déduit » et « À confirmer » restent des hypothèses ; « Rejeté » n'est jamais reproposé.
NIVEAUX = ("Confirmé", "Observé", "Déduit", "À confirmer", "Rejeté")
ETABLIS = ("Confirmé", "Observé")
CATEGORIES_HYPOTHESE = {
    "session_expiree": "Session expirée pendant une opération", "perte_connexion": "Perte de connexion",
    "double_soumission": "Double soumission", "retour_arriere": "Retour arrière pendant un traitement",
    "annulation": "Annulation d'une opération", "interruption": "Interruption pendant une transaction",
    "reprise": "Reprise après interruption", "acces_non_autorise": "Accès à une fonctionnalité non autorisée",
    "condition_inverse": "Issue contraire d'une condition", "formulaire_invalide": "Formulaire invalide",
}
_HORODATAGE = ("cree", "maj", "auteur")


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def dossier():
    return projet.PROJECT_DIR / "comportement"


def slug(texte: str, n: int = 60) -> str:
    return projet.slug(str(texte), n, "x")


def identifiant(type_: str, id_: str) -> str:
    """Identifiant d'un modèle à partir de son périmètre (stable : le même périmètre retrouve le même modèle)."""
    if type_ not in TYPES_PERIMETRE:
        raise ValueError(f"Périmètre inconnu : {type_} ({', '.join(TYPES_PERIMETRE)})")
    return f"{type_}-{slug(id_.split(':', 1)[-1], 70)}"


def confiance(el: dict) -> str:
    """confirmée : lue dans une source et non contestée, déclarée, ou validée par un humain ; probable : calculée de
    façon déterministe à partir de faits observés ; non vérifiée : proposition à valider (IA comprise) ; rejetée."""
    v = el.get("validation", "à valider")
    if v == "rejeté":
        return "rejetée"
    if v == "validé":
        return "confirmée" if el.get("provenance") != "déduit" or el.get("valide_par") else "probable"
    return "non vérifiée"


def niveau(el: dict) -> str:
    """Confirmé : exigence ou règle métier explicite, déclaration ou validation du QA ; Observé : découvert dans
    l'application ; Déduit : proposé (calcul ou IA) ; À confirmer : information insuffisante (résultat inconnu,
    hypothèse) ; Rejeté : refusé par le QA."""
    if el.get("validation") == "rejeté":
        return "Rejeté"
    if el.get("valide_par") or el.get("provenance") == "déclaré" or (el.get("exigence") and el.get("validation") == "validé"):
        return "Confirmé"
    if el.get("a_confirmer") or el.get("postconditions_a_confirmer") or el.get("hypothese"):
        return "À confirmer"
    if el.get("provenance") == "observé":
        return "Observé"
    return "Déduit"


def etabli(el: dict) -> bool:
    return niveau(el) in ETABLIS


def element(provenance: str, source: str, validation: str = "", justification: str = "", auteur: str = "atelier", **champs) -> dict:
    if provenance not in PROVENANCES:
        raise ValueError(f"Provenance inconnue : {provenance}")
    validation = validation or ("à valider" if provenance == "déduit" else "validé")
    if validation not in VALIDATIONS:
        raise ValueError(f"Validation inconnue : {validation}")
    t = _maintenant()
    el = {**champs, "provenance": provenance, "validation": validation, "source": source, "justification": justification,
          "cree": t, "maj": t, "auteur": auteur}
    el["confiance"] = confiance(el)
    el["niveau"] = niveau(el)
    return el


def nouveau(type_: str, id_: str, nom: str = "", description: str = "", application: str = "", version_application: str = "") -> dict:
    t = _maintenant()
    return {"id": identifiant(type_, id_), "projet": projet.PROJECT_DIR.name, "application": application, "nom": nom or id_,
            "description": description, "perimetre": {"type": type_, "id": id_}, "version_application": version_application,
            "version": 0, "statut": "Draft", "provenance": "observé", "cree": t, "maj": t,
            "etats": {}, "transitions": {}, "actions": {}, "conditions": {}, "chemins_generes": {}, "historique_validations": [],
            "hypotheses": {}}


# =========================================================================== lecture / écriture versionnée
def _fichier(mid: str):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", mid or ""):
        raise ValueError(f"Identifiant de modèle invalide : {mid}")
    return dossier() / f"{mid}.yaml"


def lister() -> list[dict]:
    d = dossier()
    out = []
    for f in sorted(d.glob("*.yaml")) if d.exists() else []:
        try:
            m = yaml.safe_load(f.read_text("utf-8")) or {}
        except yaml.YAMLError:
            continue
        out.append({"id": m.get("id", f.stem), "nom": m.get("nom", ""), "perimetre": m.get("perimetre", {}), "version": m.get("version", 0),
                    "statut": m.get("statut", "Draft"), "maj": m.get("maj", ""),
                    **{f"nb_{c}": sum(1 for e in (m.get(c) or {}).values() if e.get("validation") != "rejeté") for c in COLLECTIONS}})
    return out


def charger(mid: str) -> dict | None:
    f = _fichier(mid)
    if not f.exists():
        return None
    m = yaml.safe_load(f.read_text("utf-8")) or {}
    for c in COLLECTIONS + ("chemins_generes", "hypotheses"):
        m.setdefault(c, {})
    m.setdefault("historique_validations", [])
    return m


def exiger(mid: str) -> dict:
    m = charger(mid)
    if m is None:
        raise KeyError(f"Modèle inconnu : {mid}")
    return m


def contenu(m: dict) -> str:
    """Empreinte du contenu (sans les dates) : une nouvelle version n'est créée que si le comportement change."""
    propre = {c: {k: {x: y for x, y in v.items() if x not in _HORODATAGE} for k, v in (m.get(c) or {}).items()} for c in COLLECTIONS}
    return hashlib.blake2b(json.dumps(propre, sort_keys=True, ensure_ascii=False, default=str).encode(), digest_size=12).hexdigest()


def sauver(m: dict, motif: str = "") -> dict:
    """Écrit le modèle ; si son contenu a changé, la version précédente est archivée et la version augmente."""
    f = _fichier(m["id"])
    f.parent.mkdir(parents=True, exist_ok=True)
    for c in COLLECTIONS:  # niveau et confiance toujours recalculés : jamais un état incohérent sur disque
        for el in (m.get(c) or {}).values():
            el["confiance"], el["niveau"] = confiance(el), niveau(el)
    ancien = charger(m["id"])
    emp = contenu(m)
    if ancien is not None and contenu(ancien) == emp and ancien.get("version"):
        m["version"] = ancien["version"]
    else:
        if ancien is not None and ancien.get("version"):
            arch = dossier() / "versions" / m["id"] / f"v{ancien['version']}.yaml"
            arch.parent.mkdir(parents=True, exist_ok=True)
            if not arch.exists():
                arch.write_text(yaml.safe_dump(ancien, allow_unicode=True, sort_keys=False, width=120), "utf-8")
        m["version"] = int((ancien or {}).get("version") or 0) + 1
        m["motif_version"] = motif
        m["maj"] = _maintenant()
    m["empreinte"] = emp
    tmp = f.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump(m, allow_unicode=True, sort_keys=False, width=120), "utf-8")
    tmp.replace(f)
    return m


def versions(mid: str) -> list[dict]:
    d = dossier() / "versions" / mid
    out = []
    for f in sorted(d.glob("v*.yaml"), key=lambda p: int(p.stem[1:])) if d.exists() else []:
        v = yaml.safe_load(f.read_text("utf-8")) or {}
        out.append({"version": v.get("version"), "maj": v.get("maj", ""), "motif": v.get("motif_version", "")})
    m = charger(mid)
    if m:
        out.append({"version": m.get("version"), "maj": m.get("maj", ""), "motif": m.get("motif_version", ""), "courante": True})
    return out


def version(mid: str, n: int | str) -> dict:
    m = exiger(mid)
    if str(n) in ("", "courante") or int(n) == m.get("version"):
        return m
    f = dossier() / "versions" / mid / f"v{int(n)}.yaml"
    if not f.exists():
        raise KeyError(f"Version inconnue : {mid} v{n}")
    return yaml.safe_load(f.read_text("utf-8")) or {}


def comparer(mid: str, a: int | str, b: int | str = "courante") -> dict:
    """Différences entre deux versions : éléments ajoutés, retirés, modifiés (champs changés), par collection."""
    va, vb = version(mid, a), version(mid, b)
    out = {"modele": mid, "de": va.get("version"), "vers": vb.get("version")}
    for c in COLLECTIONS:
        x, y = va.get(c) or {}, vb.get(c) or {}
        modifies = []
        for k in sorted(set(x) & set(y)):
            champs = sorted(f for f in set(x[k]) | set(y[k]) if f not in _HORODATAGE + ("confiance", "niveau") and x[k].get(f) != y[k].get(f))
            if champs:
                modifies.append({"id": k, "champs": champs})
        out[c] = {"ajoutes": sorted(set(y) - set(x)), "retires": sorted(set(x) - set(y)), "modifies": modifies}
    out["nombre"] = sum(len(out[c]["ajoutes"]) + len(out[c]["retires"]) + len(out[c]["modifies"]) for c in COLLECTIONS)
    return out


# =========================================================================== modifications par le QA (déclarées, confirmées)
def _id_libre(m: dict, coll: str, prefixe: str, texte: str) -> str:
    base = f"{prefixe}-{slug(texte, 40)}"
    i, eid = 1, base
    while eid in m[coll]:
        i += 1
        eid = f"{base}-{i}"
    return eid


def ajouter_etat(mid: str, nom: str, type_: str = "metier", ecran: str = "", description: str = "", contexte: str = "",
                 initial: bool = False, final: bool = False, auteur: str = "automaticien") -> dict:
    if type_ not in TYPES_ETAT:
        raise ValueError(f"Type d'état inconnu : {type_}")
    if not nom.strip():
        raise ValueError("Nom de l'état obligatoire.")
    m = exiger(mid)
    eid = _id_libre(m, "etats", "E", nom)
    m["etats"][eid] = element("déclaré", "déclaration", auteur=auteur, nom=nom.strip(), type=type_, ecran=ecran, description=description,
                              contexte=contexte, initial=bool(initial), final=bool(final))
    return sauver(m, f"état « {nom} » ajouté")


def ajouter_condition(mid: str, libelle: str, regle: str = "", auteur: str = "automaticien") -> dict:
    if not libelle.strip():
        raise ValueError("Libellé de la condition obligatoire.")
    m = exiger(mid)
    cid = _id_libre(m, "conditions", "C", libelle)
    m["conditions"][cid] = element("déclaré", "déclaration", auteur=auteur, libelle=libelle.strip(), regle=regle)
    return sauver(m, f"condition « {libelle} » ajoutée")


def ajouter_transition(mid: str, de: str, vers: str, action: str = "", garde: str = "", issue: str = "vraie", evenement: str = "",
                       postconditions: str = "", preconditions: str = "", priorite: str = "normale", auteur: str = "automaticien") -> dict:
    m = exiger(mid)
    for e in (de, vers):
        if e not in m["etats"]:
            raise KeyError(f"État inconnu : {e}")
    if garde and garde not in m["conditions"]:
        raise KeyError(f"Condition inconnue : {garde}")
    if priorite not in PRIORITES or issue not in ("vraie", "fausse"):
        raise ValueError("Priorité : haute, normale ou basse ; issue : vraie ou fausse.")
    aid = ""
    if action.strip():
        aid = next((k for k, a in m["actions"].items() if a.get("libelle", "").casefold() == action.strip().casefold()), "")
        if not aid:
            aid = _id_libre(m, "actions", "A", action)
            m["actions"][aid] = element("déclaré", "déclaration", auteur=auteur, libelle=action.strip(), ecran=m["etats"][de].get("ecran", ""))
    tid = _id_libre(m, "transitions", "T", f"{de}-{vers}-{action}")
    m["transitions"][tid] = element("déclaré", "déclaration", auteur=auteur, de=de, vers=vers, action=aid, evenement=evenement, garde=garde,
                                    issue=issue if garde else "", preconditions=preconditions, postconditions=postconditions, priorite=priorite)
    return sauver(m, "transition ajoutée")


def modifier(mid: str, collection: str, eid: str, champs: dict, auteur: str = "automaticien") -> dict:
    """Correction par le QA : l'élément est marqué « édité » (une reconstruction ne l'écrase plus)."""
    m = exiger(mid)
    if collection not in COLLECTIONS or eid not in m[collection]:
        raise KeyError(f"Élément inconnu : {collection}/{eid}")
    el = m[collection][eid]
    interdits = {"provenance", "validation", "confiance", "cree", "auteur", "source"}
    for k, v in champs.items():
        if k not in interdits:
            el[k] = v
    if collection == "transitions" and el.get("garde") and el["garde"] not in m["conditions"]:
        raise KeyError(f"Condition inconnue : {el['garde']}")
    el.update(edite=True, maj=_maintenant(), modifie_par=auteur)
    return sauver(m, f"{collection[:-1]} {eid} modifié")


def valider(mid: str, collection: str, eid: str, auteur: str = "automaticien") -> dict:
    return _decider(mid, collection, eid, "validé", "", auteur)


def rejeter(mid: str, collection: str, eid: str, motif: str, auteur: str = "automaticien") -> dict:
    if not motif.strip():
        raise ValueError("Le motif du rejet est obligatoire.")
    return _decider(mid, collection, eid, "rejeté", motif, auteur)


def _decider(mid: str, collection: str, eid: str, decision: str, motif: str, auteur: str) -> dict:
    m = exiger(mid)
    if collection not in COLLECTIONS or eid not in m[collection]:
        raise KeyError(f"Élément inconnu : {collection}/{eid}")
    el = m[collection][eid]
    if auteur == "ia":
        raise PermissionError("Une IA ne valide ni ne rejette un élément du modèle.")
    el["validation"] = decision
    if decision == "validé":
        el["valide_par"] = auteur
    if motif:
        el["motif_rejet"] = motif
    el["maj"] = _maintenant()
    el["confiance"], el["niveau"] = confiance(el), niveau(el)
    m["historique_validations"].append({"date": el["maj"], "element": f"{collection}/{eid}", "decision": decision, "auteur": auteur, "motif": motif})
    return sauver(m, f"{collection[:-1]} {eid} {decision}")


def supprimer(mid: str, collection: str, eid: str, auteur: str = "automaticien") -> dict:
    """Un élément déclaré est supprimé ; un élément observé ou déduit se rejette (sinon la reconstruction le recréerait)."""
    m = exiger(mid)
    if collection not in COLLECTIONS or eid not in m[collection]:
        raise KeyError(f"Élément inconnu : {collection}/{eid}")
    if m[collection][eid].get("provenance") != "déclaré":
        raise PermissionError("Élément observé ou déduit : le rejeter (avec un motif) plutôt que le supprimer.")
    del m[collection][eid]
    if collection == "etats":
        for tid in [k for k, t in m["transitions"].items() if eid in (t.get("de"), t.get("vers"))]:
            del m["transitions"][tid]
    if collection == "conditions":
        for t in m["transitions"].values():
            if t.get("garde") == eid:
                t["garde"], t["issue"] = "", ""
    return sauver(m, f"{collection[:-1]} {eid} supprimé")


def changer_statut(mid: str, statut: str, auteur: str = "automaticien") -> dict:
    if statut not in STATUTS:
        raise ValueError(f"Statut inconnu : {statut} ({', '.join(STATUTS)})")
    m = exiger(mid)
    m["statut"] = statut
    m["historique_validations"].append({"date": _maintenant(), "element": "modèle", "decision": statut, "auteur": auteur, "motif": ""})
    return sauver(m, f"statut {statut}")


def deposer_propositions(mid: str, propositions: dict, source: str = "IA") -> dict:
    """Propositions d'une IA (Cursor, LLM) : états, transitions, conditions, toujours « déduit » et « à valider ». Une
    proposition déjà rejetée n'est pas recréée ; une transition vers un état inconnu est ignorée (signalée)."""
    m = exiger(mid)
    ajoutes, ignores = [], []
    rejetes = {(c, (e.get("nom") or e.get("libelle") or "").casefold()) for c in COLLECTIONS for e in m[c].values() if e.get("validation") == "rejeté"}
    for p in propositions.get("conditions") or []:
        lib = str(p.get("libelle") or "").strip()
        if not lib or ("conditions", lib.casefold()) in rejetes or any(c.get("libelle", "").casefold() == lib.casefold() for c in m["conditions"].values()):
            continue
        cid = _id_libre(m, "conditions", "C", lib)
        m["conditions"][cid] = element("déduit", source, justification=str(p.get("justification") or ""), auteur="ia", libelle=lib)
        ajoutes.append(f"conditions/{cid}")
    for p in propositions.get("etats") or []:
        nom = str(p.get("nom") or "").strip()
        if not nom or ("etats", nom.casefold()) in rejetes or any(e.get("nom", "").casefold() == nom.casefold() for e in m["etats"].values()):
            continue
        eid = _id_libre(m, "etats", "E", nom)
        m["etats"][eid] = element("déduit", source, justification=str(p.get("justification") or ""), auteur="ia", nom=nom,
                                  type=p.get("type") if p.get("type") in TYPES_ETAT else "metier", ecran=str(p.get("ecran") or ""),
                                  description=str(p.get("description") or ""), initial=False, final=bool(p.get("final")))
        ajoutes.append(f"etats/{eid}")
    noms = {e.get("nom", "").casefold(): k for k, e in m["etats"].items()}
    conds = {c.get("libelle", "").casefold(): k for k, c in m["conditions"].items()}
    for p in propositions.get("transitions") or []:
        de = p.get("de") if p.get("de") in m["etats"] else noms.get(str(p.get("de") or "").casefold())
        vers = p.get("vers") if p.get("vers") in m["etats"] else noms.get(str(p.get("vers") or "").casefold())
        if not de or not vers:
            ignores.append(f"transition {p.get('de')} → {p.get('vers')} : état inconnu")
            continue
        garde = p.get("garde") if p.get("garde") in m["conditions"] else conds.get(str(p.get("garde") or "").casefold(), "")
        tid = _id_libre(m, "transitions", "T", f"{de}-{vers}-{p.get('action', '')}")
        aid = ""
        if str(p.get("action") or "").strip():
            aid = _id_libre(m, "actions", "A", p["action"])
            m["actions"][aid] = element("déduit", source, auteur="ia", libelle=str(p["action"]).strip(), ecran=m["etats"][de].get("ecran", ""))
        m["transitions"][tid] = element("déduit", source, justification=str(p.get("justification") or ""), auteur="ia", de=de, vers=vers,
                                        action=aid, evenement="", garde=garde, issue=("fausse" if p.get("issue") == "fausse" else "vraie") if garde else "",
                                        preconditions="", postconditions=str(p.get("postconditions") or ""), priorite="normale",
                                        postconditions_a_confirmer=True)
        ajoutes.append(f"transitions/{tid}")
    m.setdefault("revisions_proposees", [])
    for r in propositions.get("revisions") or []:  # révisions de scénarios : proposées, jamais appliquées
        if isinstance(r, dict) and str(r.get("proposition") or "").strip():
            m["revisions_proposees"].append({"scenario": str(r.get("scenario") or ""), "proposition": str(r["proposition"])[:400], "source": source,
                                             "date": _maintenant()})
    m.setdefault("incoherences_signalees", [])
    for x in propositions.get("incoherences") or []:
        m["incoherences_signalees"].append({"texte": str(x)[:400], "source": source, "date": _maintenant()})
    sauver(m, f"{len(ajoutes)} proposition(s) {source}")
    return {"ajoutes": ajoutes, "ignores": ignores, "modele": charger(mid)}


def copie(m: dict) -> dict:
    return copy.deepcopy(m)


# =========================================================================== conditions mutualisées
def mots(texte: str) -> set:
    import unicodedata

    t = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode().lower()
    vides = {"le", "la", "les", "de", "des", "du", "un", "une", "et", "est", "sont", "pas", "ne", "n", "l", "d", "si", "que", "qui"}
    return {x for x in re.findall(r"[a-z0-9]+", t) if x not in vides and len(x) > 1}


def condition_commune(m: dict, libelle: str) -> str:
    """Identifiant d'une condition existante de même sens (mêmes mots significatifs, ou presque) : une condition métier
    se réutilise dans plusieurs transitions au lieu d'être recréée sous une autre forme."""
    a = mots(libelle)
    if not a:
        return ""
    for k, c in (m.get("conditions") or {}).items():
        b = mots(c.get("libelle", ""))
        if b and (a == b or len(a & b) / len(a | b) >= 0.75):
            return k
    return ""


# =========================================================================== hypothèses (comportements non documentés)
def decider_hypothese(mid: str, hid: str, decision: str, motif: str = "", auteur: str = "automaticien") -> dict:
    """Accepter une hypothèse la fait entrer dans le modèle comme comportement À CONFIRMER (état et transition déduits,
    résultat attendu inconnu tant qu'une exigence ou le QA ne le précise pas). Rejeter la garde pour qu'elle ne soit
    jamais reproposée. Une IA ne décide pas."""
    if auteur == "ia":
        raise PermissionError("Une IA ne décide pas d'une hypothèse.")
    m = exiger(mid)
    h = (m.get("hypotheses") or {}).get(hid)
    if not h:
        raise KeyError(f"Hypothèse inconnue : {hid}")
    if decision == "rejeter":
        if not motif.strip():
            raise ValueError("Le motif du rejet est obligatoire.")
        h.update(statut="rejetée", motif_rejet=motif, decide_par=auteur, maj=_maintenant())
    elif decision == "accepter":
        de = h.get("de")
        if de not in m["etats"]:
            raise KeyError(f"État de départ inconnu : {de}")
        eid = h.get("etat_id") or f"E-H-{slug(hid, 40)}"
        m["etats"][eid] = element("déduit", f"hypothèse {CATEGORIES_HYPOTHESE.get(h['categorie'], h['categorie'])}", auteur=auteur,
                                  justification=h.get("justification", ""), nom=h.get("etat_nom") or h["libelle"][:120],
                                  type=h.get("etat_type") or "erreur", ecran=m["etats"][de].get("ecran", ""), description=h.get("description", ""),
                                  contexte="", initial=False, final=True, hypothese=True)
        garde = ""
        if h.get("condition"):
            garde = condition_commune(m, h["condition"]) or _id_libre(m, "conditions", "C", h["condition"])
            m["conditions"].setdefault(garde, element("déduit", f"hypothèse {h['categorie']}", auteur=auteur, libelle=h["condition"], regle="",
                                                      hypothese=True))
        aid = ""
        if h.get("action"):
            aid = next((k for k, a in m["actions"].items() if a.get("libelle", "").casefold() == h["action"].casefold()), "") \
                or _id_libre(m, "actions", "A", h["action"])
            m["actions"].setdefault(aid, element("déduit", f"hypothèse {h['categorie']}", auteur=auteur, libelle=h["action"], ecran=m["etats"][de].get("ecran", "")))
        tid = f"T-H-{slug(hid, 40)}"
        m["transitions"][tid] = element("déduit", f"hypothèse {CATEGORIES_HYPOTHESE.get(h['categorie'], h['categorie'])}", auteur=auteur,
                                        justification=h.get("justification", ""), de=de, vers=eid, action=aid, evenement=h.get("evenement", ""),
                                        garde=garde, issue=h.get("issue", "vraie") if garde else "", preconditions="", postconditions="",
                                        postconditions_a_confirmer=True, priorite="haute", hypothese=True)
        h.update(statut="acceptée", decide_par=auteur, maj=_maintenant(), etat_id=eid, transition_id=tid)
    else:
        raise ValueError("Décision : accepter ou rejeter.")
    m["historique_validations"].append({"date": _maintenant(), "element": f"hypotheses/{hid}", "decision": decision, "auteur": auteur, "motif": motif})
    return sauver(m, f"hypothèse {hid} : {decision}")
