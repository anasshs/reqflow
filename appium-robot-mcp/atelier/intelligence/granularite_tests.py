"""Granularité des tests d'une US (Test Design › À concevoir) : couvrir tous les comportements avec le minimum de tests.

Principe : un test = un objectif ; le nombre de tests n'est pas un indicateur de qualité. Deux façons de regrouper des
cas proposés, toujours sur décision de l'automaticien (aucun regroupement n'est appliqué automatiquement) :
- « données » : même chemin, seules les données et les résultats changent -> un seul test, une variante par cas
  (étapes manuelles : variantes à la suite ; Gherkin : plan du scénario avec un tableau d'exemples) ;
- « contrôle » : un cas qui ne vérifie qu'un détail d'un écran déjà traversé -> point de contrôle dans un autre test.
Garder séparés les cas dont le résultat métier, la criticité ou le niveau (API, mobile) diffèrent.

Les cas d'origine ne sont jamais supprimés : ils passent « Regroupé » (référence vers le test qui les remplace) et le
regroupement se défait tant que le test n'est pas publié. Chaque test garde la liste des comportements qu'il couvre
(« couvre ») : l'indicateur est « comportements couverts par test », pas le nombre de tests.
Décider que deux cas ont le même objectif est un jugement sur le sens : il revient à une IA qui comprend le texte.
- Cursor (MCP) : test_design_cas_us lit les cas, test_design_proposer_regroupements dépose les regroupements ;
- LLM interne ou Claude (appel direct, texte masqué) : consolider_ia ;
- sans IA (IA_FOURNISSEUR=aucun) : règles de secours (similarité des mots des actions, résultats et titres), sans
  compréhension du texte, affichées comme telles.
Dans tous les cas l'atelier ne fait que proposer : l'automaticien applique ou écarte chaque regroupement."""
from __future__ import annotations

import re
import secrets

from atelier.intelligence import testabilite_us as t
from atelier.intelligence.intelligence_couverture import _jaccard, _jetons

INACTIFS = ("Rejeté", "Regroupé")
MODES = {"donnees": "même chemin, données différentes", "controle": "points de contrôle"}
SEUIL = 0.5
CONTROLE = re.compile(r"(?i)\b(affich|visible|libell|gris|tarif|message|texte|ic[oô]ne|couleur|format)")
_CITATION = re.compile(r"«[^»]*»|\"[^\"]*\"|\d+")
# résultat métier opposé (« éligible » / « non éligible ») : jamais regroupés, même si les mots se ressemblent
NEGATION = re.compile(r"(?i)(?<![\w])(non|pas|sans|aucune?|refus\w*|interdit\w*|impossible|invalide|échec|erreur|rejet\w*)(?![\w])")


def _negatif(c: dict) -> bool:
    return bool(NEGATION.search(c.get("titre") or ""))


def _compatibles(a: dict, b: dict) -> bool:
    return _negatif(a) == _negatif(b)


def actifs(u: dict) -> list[dict]:
    return [c for c in u.get("cas") or [] if c.get("statut") not in INACTIFS]


def couvre(c: dict) -> list[str]:
    """Comportements couverts par un cas : déclarés (« couvre »), sinon son titre."""
    return [str(x) for x in c.get("couvre") or [] if str(x).strip()] or [c.get("titre") or c["id"]]


def indicateur(u: dict) -> dict:
    """Comportements couverts / tests (cas actifs : proposés, validés, publiés)."""
    a = actifs(u)
    comp = sorted({x for c in a for x in couvre(c)})
    return {"tests": len(a), "comportements": len(comp), "par_test": round(len(comp) / len(a), 2) if a else None,
            "regroupes": sum(c.get("statut") == "Regroupé" for c in u.get("cas") or [])}


# --------------------------------------------------------------------------- regroupement
def _cas(u: dict, cid: str) -> dict:
    c = next((x for x in u.get("cas") or [] if x["id"] == cid), None)
    if not c:
        raise KeyError(f"Cas inconnu : {cid}")
    return c


def _sans_prefixe(e: dict) -> bool:
    return not (e.get("action") or "").lower().startswith("prérequis")


def _gherkin_variantes(titre: str, cas: list[dict]) -> str:
    """Plan du scénario avec un tableau d'exemples, si chaque cas se résume à une action et un résultat."""
    lignes = []
    for c in cas:
        e = [x for x in c.get("etapes") or [] if _sans_prefixe(x)]
        if len(e) != 1:
            return ""
        lignes.append((c.get("titre") or "", e[0].get("action") or "", e[0].get("resultat") or ""))
    cell = lambda v: (v or "").replace("|", "/").replace("\n", " ").strip()  # noqa: E731
    return "\n".join([f"Plan du scénario: {titre}", "  Étant donné le contexte de l'US en place", "  Quand <action>", "  Alors <resultat>",
                      "", "  Exemples:", "    | variante | action | resultat |"]
                     + [f"    | {cell(v)} | {cell(a)} | {cell(r)} |" for v, a, r in lignes])


def regrouper(cle: str, ids: list[str], mode: str, titre: str = "", source: str = "regroupement", justification: str = "",
              couvre_declare: list[str] | None = None) -> dict:
    """Remplace plusieurs cas par un seul test (cas « Proposé », à valider) ; les cas d'origine passent « Regroupé »."""
    if mode not in MODES:
        raise ValueError(f"Mode : {', '.join(MODES)}.")
    ids = list(dict.fromkeys(ids or []))
    if len(ids) < 2:
        raise ValueError("Choisir au moins deux cas à regrouper.")
    d, u = t._exiger(cle)
    cas = [_cas(u, i) for i in ids]
    bloques = [c["titre"] for c in cas if c.get("statut") in ("Publié",) + INACTIFS]
    if bloques:
        raise ValueError("Cas publiés, rejetés ou déjà regroupés : " + " ; ".join(bloques[:3]))
    if mode == "donnees":
        base = cas[0]
        etapes = []
        for n, c in enumerate(cas, 1):
            for e in c.get("etapes") or []:
                pref = "" if not _sans_prefixe(e) else f"Variante {n} ({c.get('titre', '')[:70]}) : "
                etapes.append({"action": pref + (e.get("action") or ""), "donnees": e.get("donnees") or "", "resultat": e.get("resultat") or ""})
        titre = titre.strip() or f"{base['titre'][:160]} — {len(cas)} variantes"
        gherkin = _gherkin_variantes(titre, cas)
    else:
        cible = max(cas, key=lambda c: len(c.get("etapes") or []))
        etapes = [dict(e) for e in cible.get("etapes") or []]
        ajouts = []
        for c in cas:
            if c is cible:
                continue
            for e in c.get("etapes") or []:
                if _sans_prefixe(e):
                    etapes.append({"action": f"Vérifier : {e.get('action') or ''}", "donnees": e.get("donnees") or "", "resultat": e.get("resultat") or ""})
                    if e.get("resultat"):
                        ajouts.append(e["resultat"])
        titre = titre.strip() or cible["titre"]
        g = (cible.get("gherkin") or "").rstrip()
        gherkin = g + "".join(f"\n  Et {r}" for r in ajouts) if g else ""
    nouveau = t._ajouter_cas(u, {"titre": titre, "etapes": etapes, "gherkin": gherkin}, source)
    declare = [str(x).strip() for x in couvre_declare or [] if str(x).strip()]
    nouveau.update({"regroupe": ids, "mode_regroupement": mode, "couvre": declare or sorted({x for c in cas for x in couvre(c)}),
                    "justification": justification or f"Regroupement ({MODES[mode]}) de {len(cas)} cas."})
    for c in cas:
        c["statut_avant"], c["statut"], c["regroupe_dans"] = c["statut"], "Regroupé", nouveau["id"]
    t._sauver_us(d)
    t._journaliser("cas_regroupes", cle=cle, cas=", ".join(ids), vers=nouveau["id"], mode=mode, source=source)
    return t.detail(cle)


def degrouper(cle: str, cid: str) -> dict:
    """Défait un regroupement non publié : le test regroupé est retiré, les cas d'origine reviennent à leur statut."""
    d, u = t._exiger(cle)
    c = _cas(u, cid)
    if not c.get("regroupe"):
        raise ValueError("Ce cas n'est pas un regroupement.")
    if c.get("statut") == "Publié":
        raise PermissionError("Test déjà publié dans Xray : le regroupement ne peut plus être défait ici.")
    if c.get("statut") == "Regroupé":
        raise ValueError("Ce regroupement fait lui-même partie d'un autre regroupement : défaire d'abord celui qui le contient.")
    for o in u["cas"]:
        if o.get("regroupe_dans") == cid:
            o["statut"] = o.pop("statut_avant", "Proposé")
            o.pop("regroupe_dans", None)
    u["cas"] = [x for x in u["cas"] if x["id"] != cid]
    t._sauver_us(d)
    t._journaliser("regroupement_defait", cle=cle, cas=cid)
    return t.detail(cle)


# --------------------------------------------------------------------------- propositions par une IA (Cursor, LLM)
SOURCE_REGLES = "règles (secours, sans compréhension du texte)"
CONSIGNE = ("Un test = un objectif. Regrouper en mode « donnees » les cas qui suivent le même chemin et ne diffèrent que par "
            "les données et les résultats (un test, une variante par cas) ; en mode « controle » un cas qui ne vérifie qu'un "
            "détail d'un écran déjà traversé par un autre cas (il devient un point de contrôle de ce cas). Garder séparés les "
            "cas dont le résultat métier diffère (ex. éligible / non éligible, succès / refus), la criticité ou le niveau (API, "
            "mobile). Ne rien regrouper plutôt que regrouper à tort. Pour chaque regroupement : cas (au moins deux "
            "identifiants), mode, titre du test obtenu, justification (pourquoi c'est le même objectif), couvre (comportements "
            "de l'US vérifiés par le test).")


def cas_pour_agent(cle: str) -> dict:
    """Pour une IA (Cursor via le MCP, LLM interne) : l'US (texte masqué) et ses cas regroupables, avec leurs identifiants."""
    _, u = t._exiger(cle)
    regroupables = [c for c in actifs(u) if c.get("statut") != "Publié"]
    m = t._masque
    return {"cle": u["cle"], "resume": u.get("resume", ""), "texte": m(t._texte(u)), "consigne": CONSIGNE, "modes": MODES,
            "reponses_equipe": [m(r.get("texte") or "") for r in (u.get("questions") or {}).get("reponses") or []],
            "cas": [{"id": c["id"], "titre": m(c.get("titre") or ""), "statut": c.get("statut"), "source": c.get("source"),
                     "couvre": c.get("couvre") or [], "gherkin": m(c.get("gherkin") or ""),
                     "etapes": [{k: m(e.get(k) or "") for k in ("action", "donnees", "resultat")} for e in c.get("etapes") or []]}
                    for c in regroupables],
            "non_regroupables": [{"id": c["id"], "titre": m(c.get("titre") or ""), "statut": c.get("statut")}
                                 for c in u.get("cas") or [] if c not in regroupables]}


def _refus(p: dict, ids: list[str], mode: str, regroupables: set, pris: set) -> str:
    if mode not in MODES:
        return "mode inconnu (donnees ou controle)"
    if len(ids) < 2:
        return "au moins deux cas"
    hors = [i for i in ids if i not in regroupables]
    if hors:
        return "cas inconnus ou non regroupables (publiés, rejetés, déjà regroupés) : " + ", ".join(hors)
    deja = [i for i in ids if i in pris]
    if deja:
        return "cas déjà dans un autre regroupement : " + ", ".join(deja)
    if not str(p.get("justification") or "").strip():
        return "justification manquante"
    return ""


def deposer_regroupements(cle: str, propositions: list[dict], source: str = "Cursor (MCP)") -> dict:
    """Regroupements proposés par une IA : contrôlés (cas connus et regroupables, au moins deux, chacun dans un seul
    regroupement, mode connu, justification), puis présentés à l'automaticien qui applique ou écarte. Remplacent les
    suggestions encore en attente ; rien n'est regroupé ici."""
    from atelier.intelligence import jugement_ia as _jia

    _jia.exiger_ia()
    d, u = t._exiger(cle)
    regroupables = {c["id"] for c in actifs(u) if c.get("statut") != "Publié"}
    retenues, refusees, pris = [], [], set()
    for n, p in enumerate(propositions or [], 1):
        p = p if isinstance(p, dict) else {}
        ids = list(dict.fromkeys(str(i) for i in p.get("cas") or []))
        mode = str(p.get("mode") or "").strip().lower().replace("é", "e").replace("ô", "o")
        raison = _refus(p, ids, mode, regroupables, pris)
        if raison:
            refusees.append({"index": n, "raison": raison})
            continue
        pris |= set(ids)
        retenues.append({"id": "G" + secrets.token_hex(3), "mode": mode, "cas": ids, "statut": "Proposé", "source": source,
                         "titre": str(p.get("titre") or "").strip()[:200], "justification": str(p["justification"]).strip()[:600],
                         "couvre": [str(x).strip()[:200] for x in p.get("couvre") or [] if str(x).strip()][:30]})
    anciennes = [x for x in (u.get("consolidation") or {}).get("propositions") or [] if x.get("statut") != "Proposé"]
    u["consolidation"] = {"date": t._maintenant(), "source": source, "propositions": anciennes + retenues, "avant": len(regroupables),
                          "apres": len(regroupables) - sum(len(p["cas"]) - 1 for p in retenues)}
    t._sauver_us(d)
    t._journaliser("consolidation_proposee", cle=cle, propositions=len(retenues), refusees=len(refusees), source=source)
    return {"cle": cle, "retenues": len(retenues), "refusees": refusees, "avant": u["consolidation"]["avant"],
            "apres": u["consolidation"]["apres"]}


SYSTEME_CONSOLIDATION = ("Tu es un ingénieur de test. On te donne une User Story et ses cas de test proposés. " + CONSIGNE
                         + ' Réponds uniquement en JSON : {"regroupements": [{"cas": ["id", "id"], "mode": "donnees|controle", '
                         '"titre": "...", "justification": "...", "couvre": ["..."]}]}. Liste vide si rien ne doit être regroupé. En français.')


def consolider_ia(cle: str) -> dict:
    """Regroupements proposés par le LLM interne ou Claude (appel direct, texte masqué). Avec « cursor », l'atelier
    n'appelle rien : l'agent passe par test_design_cas_us puis test_design_proposer_regroupements."""
    import json

    from atelier.intelligence import fournisseur_ia as ia

    if ia.fournisseur() == "cursor":
        return {"disponible": False, "raison": "Fournisseur « cursor » : demander à Cursor de consolider (outils MCP test_design_cas_us "
                                               "puis test_design_proposer_regroupements)."}
    if not ia.configure():
        return {"disponible": False, "raison": f"IA « {ia.fournisseur()} » non disponible : suggestions par règles uniquement (secours)."}
    vue = cas_pour_agent(cle)
    if len(vue["cas"]) < 2:
        return {"disponible": False, "raison": "Moins de deux cas regroupables."}
    brut = ia.completer(SYSTEME_CONSOLIDATION, json.dumps({k: vue[k] for k in ("cle", "resume", "texte", "cas")}, ensure_ascii=False), 2500)
    try:
        r = ia.extraire_json(brut)
    except ValueError:
        r = {}
    props = r.get("regroupements") if isinstance(r, dict) else r
    deposer_regroupements(cle, props if isinstance(props, list) else [], f"IA {ia.fournisseur()} ({ia.modele()})")
    return t.detail(cle)


# --------------------------------------------------------------------------- suggestions de secours (règles)
def _mots(texte: str) -> set:
    return set(_jetons(_CITATION.sub(" ", texte or "")))


def _profil(c: dict) -> dict:
    e = [x for x in c.get("etapes") or [] if _sans_prefixe(x)]
    return {"actions": _mots(" ".join(x.get("action") or "" for x in e)), "resultats": _mots(" ".join(x.get("resultat") or "" for x in e)),
            "titre": _mots(c.get("titre") or ""), "n": len(e)}


def _score(a: dict, b: dict) -> float:
    return round(0.5 * _jaccard(a["actions"], b["actions"]) + 0.3 * _jaccard(a["resultats"], b["resultats"])
                 + 0.2 * _jaccard(a["titre"], b["titre"]), 2)


def proposer(cle: str) -> dict:
    """Secours sans IA : regroupements suggérés par des règles (jamais appliqués), sans compréhension du texte : groupes
    de cas aux mots proches (score ≥ SEUIL) -> « données » ; cas d'une seule étape qui ne vérifie qu'un affichage, au
    début d'un autre cas -> « contrôle ». Garde-fou : jamais une forme négative avec une forme positive."""
    d, u = t._exiger(cle)
    cas = [c for c in actifs(u) if c.get("statut") != "Publié"]
    prof = {c["id"]: _profil(c) for c in cas}
    parent = {c["id"]: c["id"] for c in cas}

    def racine(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    paires = {}
    for i, a in enumerate(cas):
        for b in cas[i + 1:]:
            s = _score(prof[a["id"]], prof[b["id"]])
            if s >= SEUIL and abs(prof[a["id"]]["n"] - prof[b["id"]]["n"]) <= 1 and _compatibles(a, b):
                parent[racine(b["id"])] = racine(a["id"])
                paires[(a["id"], b["id"])] = s
    groupes: dict = {}
    for c in cas:
        groupes.setdefault(racine(c["id"]), []).append(c["id"])
    props = []
    pris = set()
    for ids in groupes.values():
        if len(ids) < 2:
            continue
        scores = [s for (x, y), s in paires.items() if x in ids and y in ids]
        props.append({"id": "G" + secrets.token_hex(3), "mode": "donnees", "cas": ids, "statut": "Proposé", "source": SOURCE_REGLES,
                      "justification": f"{len(ids)} cas au même chemin (actions, résultats et titres proches : score {max(scores):.2f}) : "
                                       "un seul test avec une variante par cas."})
        pris |= set(ids)
    for c in cas:  # détail d'affichage déjà vérifiable dans un autre test
        p = prof[c["id"]]
        e = [x for x in c.get("etapes") or [] if _sans_prefixe(x)]
        if c["id"] in pris or p["n"] != 1 or not CONTROLE.search(e[0].get("resultat") or ""):
            continue
        hote = max((o for o in cas if o["id"] != c["id"] and prof[o["id"]]["n"] > 1 and o["id"] not in pris and _compatibles(o, c)),
                   key=lambda o: _jaccard(p["actions"], _mots((o["etapes"] or [{}])[0].get("action") or "")), default=None)
        if hote and _jaccard(p["actions"], _mots((hote["etapes"] or [{}])[0].get("action") or "")) >= 0.4:
            props.append({"id": "G" + secrets.token_hex(3), "mode": "controle", "cas": [hote["id"], c["id"]], "statut": "Proposé",
                          "source": SOURCE_REGLES,
                          "justification": f"« {c['titre'][:80]} » ne vérifie qu'un affichage déjà traversé par « {hote['titre'][:80]} » : "
                                           "point de contrôle dans ce test."})
            pris |= {c["id"], hote["id"]}
    # les règles ne remplacent que leurs propres suggestions en attente : l'historique (appliquées, écartées) et les
    # propositions d'une IA encore en attente sont gardés ; un regroupement déjà écarté n'est pas reproposé
    existantes = (u.get("consolidation") or {}).get("propositions") or []
    gardees = [x for x in existantes if x.get("statut") != "Proposé" or not str(x.get("source") or "règles").startswith("règles")]
    pris_ia = {i for x in gardees if x.get("statut") == "Proposé" for i in x["cas"]}
    ecartees = {(x.get("mode"), frozenset(x["cas"])) for x in gardees if x.get("statut") == "Écartée"}
    props = [p for p in props if not (set(p["cas"]) & pris_ia) and (p["mode"], frozenset(p["cas"])) not in ecartees]
    attente = [x for x in gardees if x.get("statut") == "Proposé"] + props
    u["consolidation"] = {"date": t._maintenant(), "source": SOURCE_REGLES, "propositions": gardees + props, "avant": len(cas),
                          "apres": len(cas) - sum(len(p["cas"]) - 1 for p in attente)}
    t._sauver_us(d)
    t._journaliser("consolidation_proposee", cle=cle, propositions=len(props))
    return t.detail(cle)


def decider_proposition(cle: str, pid: str, decision: str, titre: str = "") -> dict:
    d, u = t._exiger(cle)
    p = next((x for x in (u.get("consolidation") or {}).get("propositions") or [] if x["id"] == pid), None)
    if not p:
        raise KeyError(f"Proposition inconnue : {pid}")
    if p["statut"] != "Proposé":
        raise ValueError("Proposition déjà traitée.")
    if decision not in ("appliquer", "ecarter"):
        raise ValueError("Décision : appliquer ou ecarter.")
    p["statut"] = "Appliquée" if decision == "appliquer" else "Écartée"
    t._sauver_us(d)
    if decision == "ecarter":
        t._journaliser("consolidation_ecartee", cle=cle, proposition=pid)
        return t.detail(cle)
    try:
        return regrouper(cle, p["cas"], p["mode"], titre or p.get("titre") or "", f"regroupement proposé · {p.get('source') or 'règles'}",
                         p["justification"], p.get("couvre"))
    except Exception:
        d, u = t._exiger(cle)
        next(x for x in u["consolidation"]["propositions"] if x["id"] == pid)["statut"] = "Proposé"
        t._sauver_us(d)
        raise
