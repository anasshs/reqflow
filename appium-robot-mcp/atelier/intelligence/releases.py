"""Release Notes : d'un texte collé au périmètre de non-régression.

L'automaticien colle le texte d'une Release Note. L'atelier le découpe en évolutions (par des règles : aucune IA n'est
appelée), rattache chaque évolution au Knowledge Graph, puis les évolutions d'une release VALIDÉE deviennent des
évolutions du TNR existant (pilotage.tnr) : même analyse d'impact, mêmes catégories de tests, même validation humaine.
Aucun second moteur d'impact.

Rattachement d'une évolution :
- une clé Jira citée dans le texte (US, bug, epic) et connue du graphe : rattachement CERTAIN, fait d'office ;
- une clé citée mais inconnue du graphe : signalée, jamais inventée (synchroniser Jira, ou relier à la main) ;
- sans clé : des éléments du graphe sont PROPOSÉS par les mots communs (modules, fonctionnalités, parcours, écrans,
  exigences). Une proposition n'est jamais un rattachement : le QA confirme, rejette, ou relie lui-même ;
- rien : l'évolution reste « non rattachée », visible, et le TNR dit que sa sélection est partielle.

Le texte d'origine est conservé tel quel ; chaque évolution garde la ligne dont elle vient. Données par projet, dans le
projet de tests (`releases/`), jamais dans le dépôt de l'atelier.
"""
from __future__ import annotations

import json
import re
import secrets
import unicodedata
from datetime import datetime

from atelier.domain import projet

TYPES = {"nouvelle": "Nouvelle fonctionnalité", "modification": "Modification", "correction": "Correction",
         "technique": "Évolution technique", "suppression": "Suppression"}
STATUTS = ("Analysée", "Validée")
TYPES_NOEUD = ("module", "fonctionnalite", "parcours", "ecran", "epic", "user_story", "bug", "regle", "endpoint")
_CLE_JIRA = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b")
_VERSION = re.compile(r"(?i)\b(?:version|release|v)\s*[:#]?\s*(\d+(?:\.\d+){1,3}(?:[-.][A-Za-z0-9]+)?)\b|\b(\d+\.\d+\.\d+(?:\.\d+)?)\b")
_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})\b")
_PUCE = re.compile(r"^\s*(?:[-*•–·▪◦]|\d+[.)]|[a-z][.)])\s+")
# titre de rubrique ou mot en tête de ligne -> type d'évolution (dans cet ordre : le plus précis d'abord)
_MOTS_TYPE = [
    ("suppression", r"suppression|supprim|retrait|retir|removed?|deprecat|décommission|decommission"),
    ("correction", r"correction|correctif|corrig|bug|anomalie|fix(?:e[sd])?|hotfix|résolu|resolu"),
    ("technique", r"technique|technical|migration|montée de version|montee de version|upgrade|refactor|performance|infrastructure|sécurité|securite|dépendance|dependance"),
    ("nouvelle", r"nouveaut|nouvelle|nouveau|ajout|new feature|feature|added|création|creation"),
    ("modification", r"modification|modifi|évolution|evolution|amélioration|amelioration|changement|changed|improvement|mise à jour|mise a jour"),
]
MOTS_VIDES = {"dans", "avec", "pour", "sans", "sous", "entre", "depuis", "lors", "plus", "tout", "tous", "toute", "toutes", "cette", "leur", "leurs",
              "être", "etre", "avoir", "fait", "faire", "peut", "sont", "elle", "elles", "nous", "vous", "donc", "ainsi", "aussi", "alors", "that", "with",
              "from", "this", "have", "been", "when", "will", "apres", "avant", "toujours", "encore", "meme", "tres", "quand", "comme", "nouvelle", "nouveau", "ajout", "correction", "modification", "evolution", "version",
              "release", "possibilite", "utilisateur", "utilisateurs", "application", "ecran", "page", "fonctionnalite", "permet", "permettre"}


def _dossier():
    return projet.PROJECT_DIR / "releases"


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _auteur() -> str:
    from atelier.intelligence.strategie import _auteur as a

    return a()


def _mots(texte: str) -> set[str]:
    """Mots comparables d'un texte. Les clés Jira sont retirées : leur préfixe (le nom du projet) est partout."""
    t = unicodedata.normalize("NFKD", _CLE_JIRA.sub(" ", texte or "")).encode("ascii", "ignore").decode().lower()
    return {(m[:-1] if len(m) >= 6 and m.endswith("s") else m) for m in re.split(r"[^a-z0-9]+", t) if len(m) >= 4 and m not in MOTS_VIDES}


def _type(texte: str) -> str:
    return next((t for t, motif in _MOTS_TYPE if re.search(rf"(?i)\b(?:{motif})", texte)), "")


# =========================================================================== lecture du texte collé (règles)
def analyser_texte(texte: str) -> dict:
    """Découpe une Release Note collée : version, date, clés Jira citées, et une évolution par puce ou par ligne.
    Le type vient du titre de rubrique au-dessus (« Corrections », « Nouveautés »…), sinon des mots de la ligne, sinon
    « modification ». Rien n'est interprété au-delà : le QA corrige ensuite."""
    lignes = (texte or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    v = _VERSION.search(texte or "")
    d = _DATE.search(texte or "")
    evolutions, rubrique, type_rubrique = [], "", ""
    for n, brut in enumerate(lignes, 1):
        ligne = brut.strip()
        if not ligne or re.fullmatch(r"[-=_*#~ ]{3,}", ligne):
            continue
        puce = bool(_PUCE.match(brut))
        contenu = _PUCE.sub("", brut).strip().lstrip("#").strip()
        titre = not puce and (ligne.startswith("#") or ligne.endswith(":") or (len(contenu) <= 60 and not re.search(r"[.;]$", contenu) and len(contenu.split()) <= 6))
        if titre:
            rubrique, type_rubrique = contenu.rstrip(":").strip(), _type(contenu)
            if not _CLE_JIRA.search(contenu):  # un titre qui cite une clé Jira est aussi une évolution
                continue
        if len(contenu) < 8 and not _CLE_JIRA.search(contenu):
            continue
        if not puce and not titre and evolutions and evolutions[-1]["ligne"] == n - 1 and brut[:1].isspace():
            evolutions[-1]["texte"] += " " + contenu  # suite indentée de la puce précédente
            evolutions[-1]["cles_jira"] = sorted(set(evolutions[-1]["cles_jira"]) | set(_CLE_JIRA.findall(contenu)))
            evolutions[-1]["ligne_fin"] = n
            continue
        evolutions.append({"id": f"E{len(evolutions) + 1}", "texte": contenu, "type": type_rubrique or _type(contenu) or "modification",
                           "rubrique": rubrique, "ligne": n, "ligne_fin": n, "cles_jira": sorted(set(_CLE_JIRA.findall(contenu))), "origine": "règles"})
    return {"version": (v.group(1) or v.group(2)) if v else "", "date": d.group(1) if d else "",
            "cles_jira": sorted(set(_CLE_JIRA.findall(texte or ""))), "evolutions": evolutions}


# =========================================================================== rattachement au Knowledge Graph
def _graphe():
    from atelier.discovery import connaissance

    return connaissance.construire()


def _noeud_de_la_cle(g, cle: str) -> str:
    return next((i for i in (f"user_story:{cle}", f"epic:{cle}", f"bug:{cle}") if i in g.noeuds), "") or next(
        (i for i, n in g.noeuds.items() if n.proprietes.get("cle") == cle and n.type in ("user_story", "epic", "bug")), "")


def _fiche(g, nid: str) -> dict:
    n = g.noeuds.get(nid)
    return {"noeud": nid, "type": n.type if n else "", "libelle": (n.libelle if n else nid.split(":", 1)[-1]), "connu": bool(n)}


def _proposer(g, texte: str, exclus: set) -> list[dict]:
    """Éléments du graphe qui partagent des mots avec l'évolution : une présélection, jamais un rattachement."""
    mots = _mots(texte)
    if not mots:
        return []
    trouves = []
    for nid, n in g.noeuds.items():
        if n.type not in TYPES_NOEUD or nid in exclus:
            continue
        communs = mots & _mots(f"{n.libelle} {n.proprietes.get('resume') or ''}")
        if communs:
            trouves.append((len(communs), nid, sorted(communs)))
    # un mot présent dans trop d'éléments ne distingue rien (le nom du produit, du module…)
    compte: dict = {}
    for _, _, communs in trouves:
        for m in communs:
            compte[m] = compte.get(m, 0) + 1
    seuil = max(8, len(trouves) // 2)
    out = []
    for _, nid, communs in trouves:
        utiles = [m for m in communs if compte[m] <= seuil]
        if utiles:
            out.append({**_fiche(g, nid), "etat": "proposé", "origine": "mots communs", "mots": utiles})
    return sorted(out, key=lambda x: (-len(x["mots"]), x["libelle"]))[:5]


def _rattacher(g, evo: dict):
    """Liens d'une évolution : clés Jira citées (certaines), propositions par les mots, en gardant les décisions du QA."""
    liens = {l["noeud"]: l for l in evo.get("liens") or [] if l.get("etat") in ("confirmé", "rejeté")}  # décisions humaines gardées
    inconnues = []
    for cle in evo.get("cles_jira") or []:
        nid = _noeud_de_la_cle(g, cle)
        if not nid:
            inconnues.append(cle)
        elif nid not in liens:
            liens[nid] = {**_fiche(g, nid), "etat": "confirmé", "origine": "clé Jira citée dans la Release Note"}
    for p in _proposer(g, evo["texte"], set(liens)):
        liens[p["noeud"]] = p
    evo["liens"] = list(liens.values())
    evo["cles_inconnues"] = inconnues


# =========================================================================== releases enregistrées
def _lire(rid: str) -> dict:
    if not re.fullmatch(r"REL-\d{8}-[a-z0-9]{6}", rid or ""):
        raise KeyError(f"Release inconnue : {rid}")
    f = _dossier() / f"{rid}.json"
    if not f.exists():
        raise KeyError(f"Release inconnue : {rid}")
    return json.loads(f.read_text("utf-8"))


def _ecrire(r: dict):
    from atelier.intelligence.strategie import _ecrire_atomique

    r["modifie"] = _maintenant()
    _dossier().mkdir(parents=True, exist_ok=True)
    _ecrire_atomique(_dossier() / f"{r['id']}.json", json.dumps(r, ensure_ascii=False, indent=1))
    try:  # le TNR lit les releases validées : son calcul mémorisé n'est plus à jour
        from atelier.intelligence import pilotage

        pilotage._MEMO.clear()
    except Exception:  # noqa: BLE001
        pass


def _journal(r: dict, action: str, **details):
    r.setdefault("historique", []).append({"date": _maintenant(), "par": _auteur(), "action": action,
                                           **{k: v for k, v in details.items() if v not in ("", None, [])}})


def _resume(r: dict) -> dict:
    ev = r.get("evolutions") or []
    rattachees = sum(any(l["etat"] == "confirmé" for l in e.get("liens") or []) for e in ev)
    a_trancher = sum(any(l["etat"] == "proposé" for l in e.get("liens") or []) and not any(l["etat"] == "confirmé" for l in e.get("liens") or []) for e in ev)
    return {**{k: r.get(k, "") for k in ("id", "nom", "version", "date", "statut", "source", "cree", "modifie", "auteur")},
            "evolutions": len(ev), "rattachees": rattachees, "a_trancher": a_trancher, "non_rattachees": len(ev) - rattachees - a_trancher,
            "cles_jira": len(r.get("cles_jira") or [])}


def lister() -> list[dict]:
    d = _dossier()
    out = []
    for f in sorted(d.glob("REL-*.json")) if d.exists() else []:
        try:
            out.append(_resume(json.loads(f.read_text("utf-8"))))
        except (OSError, ValueError):
            continue
    return sorted(out, key=lambda x: x["cree"], reverse=True)


def creer(texte: str, nom: str = "") -> dict:
    """Enregistre une Release Note collée : texte d'origine conservé, évolutions extraites et rattachées. Un texte
    identique à une release déjà enregistrée est refusé (doublon)."""
    import hashlib

    texte = (texte or "").strip()
    if len(texte) < 20:
        raise ValueError("Coller le texte de la Release Note (20 caractères au moins).")
    if len(texte) > 200_000:
        raise ValueError("Texte trop long (200 000 caractères au plus) : coller la Release Note, pas tout un document.")
    empreinte = hashlib.sha256(re.sub(r"\s+", " ", texte).encode("utf-8")).hexdigest()
    d = _dossier()
    for f in d.glob("REL-*.json") if d.exists() else []:
        try:
            autre = json.loads(f.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if autre.get("empreinte") == empreinte:
            raise FileExistsError(f"Cette Release Note est déjà enregistrée ({autre['id']} · {autre.get('nom', '')}).")
    a = analyser_texte(texte)
    if not a["evolutions"]:
        raise ValueError("Aucune évolution reconnue dans ce texte : une évolution par ligne ou par puce est attendue.")
    g = _graphe()
    for e in a["evolutions"]:
        _rattacher(g, e)
    rid = f"REL-{datetime.now():%Y%m%d}-{secrets.token_hex(3)}"
    r = {"id": rid, "nom": (nom or "").strip()[:120] or (f"Release {a['version']}" if a["version"] else f"Release du {datetime.now():%d/%m/%Y}"),
         "version": a["version"], "date": a["date"], "statut": "Analysée", "source": "texte collé", "auteur": _auteur(), "cree": _maintenant(),
         "texte": texte, "empreinte": empreinte, "cles_jira": a["cles_jira"], "evolutions": a["evolutions"], "historique": []}
    _journal(r, "création", evolutions=len(a["evolutions"]))
    _ecrire(r)
    return obtenir(rid)


def obtenir(rid: str) -> dict:
    """La release, ses évolutions et, pour chaque rattachement confirmé, les tests que l'analyse d'impact trouve."""
    from atelier.discovery import connaissance

    r = _lire(rid)
    g = _graphe()
    for e in r["evolutions"]:
        tests = set()
        for l in e.get("liens") or []:
            l["connu"] = l["noeud"] in g.noeuds
            if l["etat"] == "confirmé" and l["connu"]:
                try:
                    imp = connaissance.analyser_impact(g, l["noeud"])
                    tests |= {t["id"].split(":", 1)[1] for t in imp.get("tests_xray") or []}
                except Exception:  # noqa: BLE001 — un impact incalculable n'empêche pas d'afficher la release
                    pass
                if g.noeuds[l["noeud"]].type in ("user_story", "epic", "bug"):
                    tests |= {x.vers.split(":", 1)[1] for x in g.sortants(l["noeud"], fiables=True) if x.type == "teste_par" and x.vers.startswith("test:")}
        e["tests"] = sorted(tests)
        e["etat"] = ("rattachée" if any(l["etat"] == "confirmé" for l in e.get("liens") or [])
                     else "à trancher" if any(l["etat"] == "proposé" for l in e.get("liens") or []) else "non rattachée")
        e["sans_test"] = e["etat"] == "rattachée" and not tests  # rattachée au graphe, mais aucun test : couverture à créer
    return {**r, **{k: v for k, v in _resume(r).items() if k in ("rattachees", "a_trancher", "non_rattachees")}, "types": TYPES,
            "tests": sorted({t for e in r["evolutions"] for t in e["tests"]}), "sans_test": sum(e["sans_test"] for e in r["evolutions"])}


def chercher_noeuds(q: str, limite: int = 12) -> list[dict]:
    """Éléments du Knowledge Graph pour relier une évolution à la main (libellé, clé Jira ou identifiant)."""
    g = _graphe()
    mots = [m for m in unicodedata.normalize("NFKD", q or "").encode("ascii", "ignore").decode().lower().split() if m]
    if not mots:
        return []
    out = []
    for nid, n in g.noeuds.items():
        if n.type not in TYPES_NOEUD:
            continue
        texte = unicodedata.normalize("NFKD", f"{nid} {n.libelle} {n.proprietes.get('cle') or ''} {n.proprietes.get('resume') or ''}").encode("ascii", "ignore").decode().lower()
        if all(m in texte for m in mots):
            out.append(_fiche(g, nid))
            if len(out) >= max(1, min(limite, 40)):
                break
    return out


def _evolution(r: dict, eid: str) -> dict:
    e = next((e for e in r["evolutions"] if e["id"] == eid), None)
    if e is None:
        raise KeyError(f"Évolution inconnue : {eid}")
    return e


def operer(rid: str, op: str, **p) -> dict:
    """Corrections du QA, toutes tracées : modifier / ajouter / supprimer une évolution, confirmer / rejeter / relier /
    délier un élément du graphe, renommer, valider (la release alimente alors le TNR) ou rouvrir, supprimer la release."""
    r = _lire(rid)
    g = _graphe()
    if op == "supprimer_release":
        (_dossier() / f"{rid}.json").unlink()
        try:
            from atelier.intelligence import pilotage

            pilotage._MEMO.clear()
        except Exception:  # noqa: BLE001
            pass
        return {"supprimee": rid}
    if op in ("valider", "rouvrir"):
        r["statut"] = "Validée" if op == "valider" else "Analysée"
        if op == "valider":
            r["validation"] = {"par": _auteur(), "date": _maintenant()}
        _journal(r, "validation" if op == "valider" else "réouverture")
    elif op == "renommer":
        r["nom"] = str(p.get("nom") or "").strip()[:120] or r["nom"]
        r["version"] = str(p.get("version") or r.get("version") or "").strip()[:40]
        _journal(r, "renommage", nom=r["nom"])
    elif op == "ajouter_evolution":
        texte = str(p.get("texte") or "").strip()
        if len(texte) < 5:
            raise ValueError("Décrire l'évolution.")
        n = max([int(e["id"][1:]) for e in r["evolutions"]] or [0]) + 1
        e = {"id": f"E{n}", "texte": texte[:1000], "type": p.get("type") if p.get("type") in TYPES else (_type(texte) or "modification"), "rubrique": "",
             "ligne": 0, "ligne_fin": 0, "cles_jira": sorted(set(_CLE_JIRA.findall(texte))), "origine": "ajoutée par le QA"}
        _rattacher(g, e)
        r["evolutions"].append(e)
        _journal(r, "évolution ajoutée", evolution=e["id"])
    else:
        e = _evolution(r, str(p.get("evolution") or ""))
        if op == "supprimer_evolution":
            r["evolutions"].remove(e)
            _journal(r, "évolution supprimée", evolution=e["id"], texte=e["texte"][:120])
        elif op == "modifier_evolution":
            if p.get("type"):
                if p["type"] not in TYPES:
                    raise ValueError(f"Type inconnu : {p['type']}")
                e["type"] = p["type"]
            if p.get("texte") is not None and str(p["texte"]).strip() and str(p["texte"]).strip() != e["texte"]:
                e["texte"] = str(p["texte"]).strip()[:1000]
                e["cles_jira"] = sorted(set(_CLE_JIRA.findall(e["texte"])))
                e["corrigee"] = True
                _rattacher(g, e)
            _journal(r, "évolution corrigée", evolution=e["id"])
        elif op in ("confirmer", "rejeter", "relier", "delier"):
            nid = str(p.get("noeud") or "")
            lien = next((l for l in e.get("liens") or [] if l["noeud"] == nid), None)
            if op == "relier":
                if nid not in g.noeuds:
                    raise KeyError(f"Élément inconnu du Knowledge Graph : {nid}")
                if lien is None:
                    lien = {**_fiche(g, nid), "origine": "relié par le QA"}
                    e.setdefault("liens", []).append(lien)
                lien.update(etat="confirmé", par=_auteur(), date=_maintenant())
            elif lien is None:
                raise KeyError(f"{nid} n'est pas proposé pour cette évolution.")
            elif op == "delier":
                e["liens"].remove(lien)
            else:
                lien.update(etat="confirmé" if op == "confirmer" else "rejeté", par=_auteur(), date=_maintenant())
            _journal(r, {"confirmer": "rattachement confirmé", "rejeter": "proposition rejetée", "relier": "relié à la main", "delier": "rattachement retiré"}[op],
                     evolution=e["id"], noeud=nid)
        else:
            raise ValueError(f"Opération inconnue : {op}")
    if op not in ("valider", "rouvrir", "renommer") and r["statut"] == "Validée":
        r["statut"] = "Analysée"  # une release modifiée après validation est à revalider : le TNR ne lit que du validé
        _journal(r, "à revalider (modifiée après validation)")
    _ecrire(r)
    return obtenir(rid)


# =========================================================================== alimentation du TNR
def evolutions_tnr(depuis: str = "") -> list[dict]:
    """Évolutions des releases VALIDÉES, au format du TNR (pilotage.evolutions) : une par élément du graphe confirmé ;
    une évolution sans rattachement confirmé est transmise « hors graphe » (le TNR dit alors que sa sélection est partielle)."""
    out = []
    d = _dossier()
    for f in sorted(d.glob("REL-*.json")) if d.exists() else []:
        try:
            r = json.loads(f.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        jour = str((r.get("validation") or {}).get("date") or r.get("cree") or "")[:10]
        if r.get("statut") != "Validée" or (depuis and jour < depuis):
            continue
        for e in r.get("evolutions") or []:
            base = {"nature": f"{TYPES.get(e['type'], 'Évolution')} (Release Note)", "detail": e["texte"][:160], "date": jour,
                    "source": f"Release Note · {r['nom']}", "tests_directs": []}
            confirmes = [l for l in e.get("liens") or [] if l["etat"] == "confirmé"]
            for l in confirmes:
                out.append({**base, "id": f"release:{r['id']}:{e['id']}:{l['noeud']}", "element": l["libelle"], "noeud": l["noeud"]})
            if not confirmes:
                out.append({**base, "id": f"release:{r['id']}:{e['id']}", "element": e["texte"][:60], "noeud": ""})
    return out
