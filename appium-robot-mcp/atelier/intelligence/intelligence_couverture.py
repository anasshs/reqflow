"""Coverage Intelligence & Functional Reconstruction (cahier du 2026-11-15).

Analyse, reconstruit et aide à corriger la couverture fonctionnelle et la traçabilité, même quand Jira est mal
documenté, SANS second référentiel : les exigences viennent de l'import Jira (couverture_exigences), les tests et
exécutions de la copie Xray (patrimoine_xray), les observations de la carte / Discovery et du Knowledge Graph.

Ce module ne stocke que des PROPOSITIONS (jamais des données officielles) : User Stories et critères reconstruits,
liens exigence ↔ test, classements de tests orphelins. Chacune garde son origine, sa justification, son score, son
statut et son historique ; rien n'est écrit dans Jira / Xray sans validation humaine puis synchronisation explicite
(création de Story, lien natif « Test », commentaire), toujours journalisée.

  couverture/<app>_propositions.json   propositions et leur historique
  couverture/<app>_synchro_ci.jsonl     synchronisations vers Jira / Xray
"""
from __future__ import annotations

import json
import math
import os
import re
import secrets
import unicodedata
from collections import Counter
from datetime import datetime

from atelier.domain import projet

TYPES = ("user_story", "criteres", "lien_test", "classement_orphelin")
STATUTS = ("proposee", "validee", "rejetee", "synchronisee", "regroupee")
ORIGINES_CRITERE = {"observe": "observé directement", "deduit": "déduit d'un comportement", "ia": "proposé par l'IA", "a_confirmer": "à confirmer par le métier"}
SEUIL_LIEN = 35
GENERIQUE = re.compile(r"(?i)^(story|us|user story|tâche|task|amélioration|evolution|évolution|divers|todo|à définir|tbd|test|correction)\b")


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _auteur() -> str:
    from atelier.domain import roles

    return roles.utilisateur()


# =========================================================================== texte : normalisation et similarité
MOTS_VIDES = set("""le la les un une des de du d l et ou a à au aux en est sont pour par sur dans avec sans que qui quoi ce cet cette ces
son sa ses leur leurs mon ma mes ne pas plus il elle on nous vous ils elles être etre avoir doit doivent peut afin lors quand si
the a an of to and or in on for with is are be as by""".split())


def _sans_accents(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def jetons(texte: str) -> list[str]:
    """Mots significatifs, sans accents, racinés grossièrement (6 premières lettres) : « virements » ≈ « virement »."""
    mots = re.findall(r"[a-z0-9]{3,}", _sans_accents((texte or "").lower()))
    return [m[:6] for m in mots if m not in MOTS_VIDES]


def similarite(a: str, b: str) -> float:
    ja, jb = set(jetons(a)), set(jetons(b))
    return len(ja & jb) / len(ja | jb) if ja and jb else 0.0


class Corpus:
    """TF-IDF minimal (bibliothèque standard) pour comparer exigences et tests : les mots rares pèsent plus."""

    def __init__(self, textes: dict[str, str]):
        self.tf = {k: Counter(jetons(v)) for k, v in textes.items()}
        df = Counter(t for c in self.tf.values() for t in c)
        n = max(1, len(self.tf))
        self.idf = {t: math.log((1 + n) / (1 + d)) + 1 for t, d in df.items()}
        self.vec = {k: {t: f * self.idf[t] for t, f in c.items()} for k, c in self.tf.items()}
        self.norme = {k: math.sqrt(sum(x * x for x in v.values())) or 1.0 for k, v in self.vec.items()}

    def cosinus(self, a: str, b: str) -> tuple[float, list[str]]:
        va, vb = self.vec.get(a, {}), self.vec.get(b, {})
        communs = set(va) & set(vb)
        s = sum(va[t] * vb[t] for t in communs) / (self.norme.get(a, 1) * self.norme.get(b, 1))
        return s, sorted(communs, key=lambda t: -self.idf.get(t, 0))[:6]


# =========================================================================== stockage des propositions
def _fichier(nom: str):
    from atelier.intelligence import couverture_exigences

    return couverture_exigences._fichier(nom)


def _charger() -> list[dict]:
    f = _fichier("propositions.json")
    try:
        return json.loads(f.read_text("utf-8")) if f.exists() else []
    except (OSError, json.JSONDecodeError):
        return []


def _sauver(l: list[dict]):
    from atelier.intelligence.strategie import _ecrire_atomique

    _ecrire_atomique(_fichier("propositions.json"), json.dumps(l, ensure_ascii=False, indent=1))


def _journal_synchro(ligne: dict):
    with _fichier("synchro_ci.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": _maintenant(), "auteur": _auteur(), **ligne}, ensure_ascii=False) + "\n")


def synchronisations(limite: int = 100) -> list[dict]:
    f = _fichier("synchro_ci.jsonl")
    if not f.exists():
        return []
    return [json.loads(l) for l in f.read_text("utf-8").splitlines() if l.strip()][-limite:][::-1]


def _app() -> str:
    from atelier.discovery import carte

    return carte.app_courante() if carte.app_courante() else ""


def _ajouter(l: list[dict], type_: str, source: str, objet_source: str, objet_cible: str, score: int | None, justification: list[str],
             contenu: dict, cle_unique: str = "") -> dict:
    """Proposition nouvelle, ou existante mise à jour (même clé unique) ; une proposition rejetée n'est jamais reproposée."""
    from atelier.domain import projets

    if cle_unique:
        ex = next((p for p in l if p.get("cle_unique") == cle_unique), None)
        if ex:
            if ex["statut"] == "proposee":
                ex.update(score=score, justification=justification, contenu={**ex["contenu"], **contenu})
            return ex
    p = {"id": f"P{secrets.token_hex(4)}", "projet": projets.cle_xray() or "", "application": _app(), "type": type_, "source": source,
         "objet_source": objet_source, "objet_cible": objet_cible, "score": score, "justification": justification, "contenu": contenu,
         "statut": "proposee", "validateur": "", "cree": _maintenant(), "valide_le": "", "cle_unique": cle_unique,
         "historique": [{"date": _maintenant(), "auteur": _auteur() if source != "cursor" else "cursor", "action": "proposee", "detail": source}]}
    l.append(p)
    return p


def propositions(type_: str = "", statut: str = "") -> list[dict]:
    return [p for p in _charger() if (not type_ or p["type"] == type_) and (not statut or p["statut"] == statut)]


# =========================================================================== données sources (réutilisées)
def _donnees() -> dict:
    from atelier.discovery import intelligence_app
    from atelier.intelligence import couverture_exigences, patrimoine_xray

    src = couverture_exigences._lire_json(couverture_exigences._fichier("exigences.json"), {})
    pat = patrimoine_xray.charger_vue() or {"tests": []}
    app, ecrans, trans = intelligence_app._ecrans_carte()
    exig = {k: e for k, e in (src.get("exigences") or {}).items() if not e.get("hors_perimetre")}
    lies_test: dict = {}
    for k, e in exig.items():
        for t in e.get("tests_jira") or []:
            lies_test.setdefault(t, set()).add(k)
    for t in pat.get("tests") or []:
        for k in t.get("exigences") or []:
            lies_test.setdefault(t["cle"], set()).add(k)
    return {"src": src, "exigences": exig, "parents": src.get("parents") or {}, "epics": src.get("epics") or {},
            "tests": {t["cle"]: t for t in pat.get("tests") or []}, "liens": lies_test, "app": app, "ecrans": ecrans, "transitions": trans}


def _texte_exigence(e: dict) -> str:
    return " ".join([e.get("resume") or "", e.get("description") or "", " ".join(e.get("criteres") or [])])


def _texte_test(t: dict) -> str:
    etapes = " ".join(f"{s.get('action', '')} {s.get('donnees', '')} {s.get('resultat', '')}" for s in t.get("etapes") or [] if isinstance(s, dict))
    return " ".join([t.get("resume") or "", t.get("gherkin") or "", etapes, " ".join(t.get("preconditions") or []) if isinstance(t.get("preconditions"), list) else str(t.get("preconditions") or "")])


# =========================================================================== F1 : qualité documentaire Jira
def qualite_documentaire() -> list[dict]:
    """Problèmes de structuration Jira, avec criticité, explication, recommandation et action. Aucune modification de Jira."""
    d = _donnees()
    ex, parents, epics = d["exigences"], d["parents"], d["epics"]
    base = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
    lien = lambda k: f"{base}/browse/{k}" if base else ""  # noqa: E731
    out = []

    def anomalie(cle, resume, type_obj, code, criticite, explication, recommandation, action):
        out.append({"cle": cle, "resume": resume, "type_objet": type_obj, "code": code, "criticite": criticite, "explication": explication,
                    "recommandation": recommandation, "action": action, "lien": lien(cle)})

    enfants: dict = {}
    for k, e in ex.items():
        if e.get("parent"):
            enfants.setdefault(e["parent"], []).append(k)
    for k, e in epics.items():
        if k not in enfants and not any(p.get("parent") == k for p in parents.values()):
            anomalie(k, e.get("resume", ""), "Epic", "epic_sans_story", "haute", "Epic sans aucune Story dans le périmètre : la macro-fonctionnalité n'est pas détaillée.",
                     "Décomposer l'Epic en Stories (Functional Reconstruction peut en proposer depuis les écrans observés).", "reconstruire")
    for k, e in ex.items():
        r = e.get("resume") or ""
        if not (e.get("description") or "").strip():
            anomalie(k, r, e.get("type_jira") or "Story", "sans_description", "haute", "Story sans description : l'intention et le contexte manquent.",
                     "Ajouter le contexte, la valeur métier et les règles ; demander au PO.", "proposer_criteres")
        if not e.get("criteres"):
            anomalie(k, r, e.get("type_jira") or "Story", "sans_criteres", "haute" if (e.get("description") or "").strip() == "" else "moyenne",
                     "Aucun critère d'acceptation (champ dédié ou puces sous « Critères d'acceptation ») : la Story n'est pas testable telle quelle.",
                     "Proposer des critères d'acceptation (Given / When / Then) à faire valider par le métier.", "proposer_criteres")
        if len(jetons(r)) < 3 or GENERIQUE.match(r.strip()):
            anomalie(k, r, e.get("type_jira") or "Story", "trop_generique", "moyenne", "Titre trop court ou générique pour identifier la fonctionnalité.",
                     "Reformuler : « En tant que …, je souhaite … afin de … ».", "jira")
        if not e.get("parent"):
            anomalie(k, r, e.get("type_jira") or "Story", "sans_rattachement", "moyenne", "Story rattachée à aucune Epic / Feature : elle n'entre dans aucune macro-fonctionnalité.",
                     "Rattacher la Story à son Epic (ou Feature) dans Jira.", "jira")
        if not e.get("composants") and not e.get("versions") and not e.get("parent"):
            anomalie(k, r, e.get("type_jira") or "Story", "non_contextualisee", "basse", "Ni composant, ni version, ni parent : impossible de situer l'exigence.",
                     "Renseigner composant (module) et version cible.", "jira")
    for p, ks in enfants.items():
        if len(ks) >= 2 and all(not (ex[k].get("description") or "").strip() and not ex[k].get("criteres") for k in ks):
            info = parents.get(p) or {}
            anomalie(p, info.get("resume", ""), info.get("type_jira") or "Feature", "fonctionnalite_sans_detail", "moyenne",
                     f"Fonctionnalité dont les {len(ks)} Stories n'ont ni description ni critères.", "Détailler au moins les Stories prioritaires.", "proposer_criteres")
    cles = sorted(ex)
    for i, a in enumerate(cles):  # doublons : titres et descriptions très proches
        for b in cles[i + 1:]:
            s = similarite(_texte_exigence(ex[a]), _texte_exigence(ex[b]))
            if s >= 0.75:
                anomalie(a, ex[a].get("resume", ""), ex[a].get("type_jira") or "Story", "doublon", "moyenne",
                         f"Très proche de {b} « {ex[b].get('resume', '')} » (similarité {round(100 * s)} %).", "Fusionner ou différencier les deux Stories.", "jira")
    for k, e in (d["src"].get("exigences") or {}).items():
        if e.get("hors_perimetre"):
            anomalie(k, e.get("resume", ""), e.get("type_jira") or "Story", "obsolete", "basse", f"Sortie de la JQL du périmètre le {str(e['hors_perimetre'])[:10]}.",
                     "Confirmer qu'elle est obsolète, ou corriger la JQL des exigences.", "jira")
    ordre = {"haute": 0, "moyenne": 1, "basse": 2}
    return sorted(out, key=lambda x: (ordre[x["criticite"]], x["cle"]))


# =========================================================================== F2 : reconstruction fonctionnelle
def capacites() -> list[dict]:
    """Fonctionnalités reconstruites depuis la carte (écrans observés, composants, transitions) et les parcours du graphe,
    chacune avec ses observations, et documentée ou non par une exigence Jira (lien par test ou par texte)."""
    from atelier.discovery import connaissance

    d = _donnees()
    g = connaissance.construire()
    par_id = {e["id"]: e for e in d["ecrans"]}
    nom = lambda e: e.get("nom") or e.get("titre") or e["id"]  # noqa: E731
    caps = []
    dans_parcours = set()
    for n in g.noeuds.values():
        if n.type != "parcours":
            continue
        ids = [r.vers.split(":", 1)[1] for r in g.sortants(n.id) if r.type == "contient" and r.vers.startswith("ecran:")]
        dans_parcours |= set(ids)
        caps.append({"id": f"cap:{n.id}", "nom": n.libelle, "nature": "parcours", "source": n.source, "ecrans": ids})
    for e in d["ecrans"]:
        if e["id"] not in dans_parcours:
            caps.append({"id": f"cap:ecran:{e['id']}", "nom": nom(e), "nature": "écran", "source": "carte (observation)", "ecrans": [e["id"]]})
    exig_txt = {k: _texte_exigence(e) for k, e in d["exigences"].items()}
    out = []
    for c in caps:
        obs = []
        for eid in c["ecrans"]:
            e = par_id.get(eid) or {}
            obs.append({"nature": "écran", "texte": f"Écran « {nom(e) if e else eid} » observé", "ref": f"ecran:{eid}", "statut": "observé"})
            for k, el in (e.get("elements") or {}).items():
                if el.get("type") in ("champ", "saisie", "liste", "case", "bouton", "lien", "interrupteur"):
                    obs.append({"nature": el["type"], "texte": f"{el['type']} « {el.get('libelle') or k} »", "ref": f"element:{eid}.{k}", "statut": "observé"})
            for t in d["transitions"]:
                if t.get("de") == eid and t.get("vers") in par_id:
                    a = t.get("action") or {}
                    obs.append({"nature": "transition", "texte": f"« {a.get('cle') or a.get('locator') or a.get('type', '')} » mène à « {nom(par_id[t['vers']])} »",
                                "ref": f"transition:{t.get('id')}", "statut": "observé"})
        texte_cap = " ".join([c["nom"]] + [o["texte"] for o in obs])
        doc_par = sorted(k for k, t in exig_txt.items() if similarite(texte_cap, t) >= 0.12 or similarite(c["nom"], t) >= 0.3)
        tests_ecrans = set()
        for eid in c["ecrans"]:
            try:
                imp = connaissance.analyser_impact(g, f"ecran:{eid}")
                tests_ecrans |= {x["id"].split(":", 1)[1] for x in imp["tests_xray"]}
            except Exception:  # noqa: BLE001
                pass
        doc_par = sorted(set(doc_par) | {k for t in tests_ecrans for k in d["liens"].get(t, set())})
        module = next((par_id[i].get("module") for i in c["ecrans"] if par_id.get(i, {}).get("module")), "")
        out.append({**c, "module": module, "observations": obs[:60], "documentee_par": doc_par, "documentee": bool(doc_par),
                    "tests_lies": sorted(tests_ecrans)})
    return out


# =========================================================================== F3 : propositions de User Stories
def _epic_suggere(cap: dict, d: dict) -> str:
    candidats = {**{k: v for k, v in d["epics"].items()}, **{k: v for k, v in d["parents"].items()}}
    meilleur = max(candidats.items(), key=lambda kv: similarite(f"{cap['nom']} {cap.get('module', '')}", kv[1].get("resume", "")), default=None)
    return meilleur[0] if meilleur and similarite(f"{cap['nom']} {cap.get('module', '')}", meilleur[1].get("resume", "")) >= 0.15 else ""


def proposer_story(capacite_id: str, avec_ia: bool = False) -> dict:
    """Story reconstruite d'une fonctionnalité découverte : critères observés (composants, transitions), déduits
    (champs à saisir, enchaînements) et à confirmer par le métier (règles supposées). IA facultative, marquée."""
    caps = {c["id"]: c for c in capacites()}
    c = caps.get(capacite_id)
    if not c:
        raise KeyError(f"Fonctionnalité inconnue : {capacite_id}")
    d = _donnees()
    crit = []
    champs = [o for o in c["observations"] if o["nature"] in ("champ", "saisie", "liste", "case")]
    for o in champs[:8]:
        crit.append({"texte": f"Le {o['texte']} est présent et utilisable.", "origine": "observe", "ref": o["ref"]})
    for o in [o for o in c["observations"] if o["nature"] == "transition"][:6]:
        crit.append({"texte": f"Action {o['texte']}.", "origine": "observe", "ref": o["ref"]})
    for o in champs[:4]:
        crit.append({"texte": f"Une valeur invalide ou absente pour le {o['texte']} est refusée avec un message explicite.", "origine": "a_confirmer", "ref": o["ref"]})
    if any(o["nature"] == "bouton" for o in c["observations"]):
        b = next(o for o in c["observations"] if o["nature"] == "bouton")
        crit.append({"texte": f"Le {b['texte']} déclenche l'opération attendue.", "origine": "deduit", "ref": b["ref"]})
    contenu = {"titre": c["nom"], "en_tant_que": "utilisateur de l'application", "je_souhaite": f"utiliser « {c['nom']} »",
               "afin_de": "(objectif métier à confirmer)", "criteres": crit, "epic": _epic_suggere(c, d), "module": c.get("module", ""),
               "observations": c["observations"][:30], "capacite": capacite_id, "projet_jira": _projet_jira(d)}
    justification = [f"{len(c['observations'])} observation(s) de la carte / Discovery", "aucune exigence Jira ne documente cette fonctionnalité"
                     if not c["documentee"] else f"documentée en partie par {', '.join(c['documentee_par'])}"]
    if avec_ia:
        contenu = _enrichir_story_ia(contenu)
    l = _charger()
    p = _ajouter(l, "user_story", "ia" if contenu.get("par_ia") else "reconstruction", capacite_id, contenu.get("epic", ""), None, justification, contenu,
                 cle_unique=f"story:{capacite_id}")
    _sauver(l)
    return p


def _projet_jira(d: dict) -> str:
    c = Counter(k.split("-")[0] for k in d["exigences"])
    return c.most_common(1)[0][0] if c else ""


def _enrichir_story_ia(contenu: dict) -> dict:
    from atelier.intelligence import fournisseur_ia

    try:
        texte = fournisseur_ia.completer(
            "Tu reconstruis une User Story à partir d'observations d'une application. Réponds en JSON : "
            '{"en_tant_que": "...", "je_souhaite": "...", "afin_de": "...", "criteres": ["..."]}. N\'invente pas de règle métier : '
            "les critères qui ne découlent pas directement des observations seront marqués à confirmer.",
            json.dumps({"fonctionnalite": contenu["titre"], "observations": [o["texte"] for o in contenu["observations"]]}, ensure_ascii=False)[:6000], 900)
        r = fournisseur_ia.extraire_json(texte) or {}
    except Exception as e:  # noqa: BLE001
        return {**contenu, "ia_erreur": str(e)[:200]}
    observes = {c["texte"] for c in contenu["criteres"]}
    ajout = [{"texte": str(x)[:300], "origine": "ia", "ref": ""} for x in r.get("criteres") or [] if str(x) not in observes]
    return {**contenu, **{k: str(r[k])[:300] for k in ("en_tant_que", "je_souhaite", "afin_de") if r.get(k)}, "criteres": contenu["criteres"] + ajout, "par_ia": True}


def proposer_criteres(cle: str, avec_ia: bool = False) -> dict:
    """Critères d'acceptation proposés pour une Story existante mal documentée (depuis les observations qui lui
    correspondent, et l'IA si demandée). Validés, ils peuvent être ajoutés en commentaire Jira (jamais en champ)."""
    d = _donnees()
    e = d["exigences"].get(cle)
    if not e:
        raise KeyError(f"Exigence {cle} hors périmètre importé.")
    caps = [c for c in capacites() if cle in c["documentee_par"]]
    crit = []
    for c in caps[:3]:
        for o in [o for o in c["observations"] if o["nature"] in ("champ", "saisie", "transition", "bouton")][:6]:
            crit.append({"texte": f"{o['texte']} (observé)", "origine": "observe", "ref": o["ref"]})
    if not crit:
        crit.append({"texte": f"Le résultat attendu de « {e.get('resume', '')} » est visible pour l'utilisateur.", "origine": "a_confirmer", "ref": ""})
    contenu = {"titre": e.get("resume", ""), "criteres": crit, "capacites": [c["id"] for c in caps]}
    if avec_ia:
        from atelier.intelligence import fournisseur_ia

        try:
            r = fournisseur_ia.extraire_json(fournisseur_ia.completer(
                'Propose des critères d\'acceptation testables (Given/When/Then courts). Réponds en JSON {"criteres": ["..."]}.',
                json.dumps({"story": e.get("resume"), "description": e.get("description", ""), "observations": [c["texte"] for c in crit]}, ensure_ascii=False)[:6000], 700)) or {}
            contenu["criteres"] += [{"texte": str(x)[:300], "origine": "ia", "ref": ""} for x in r.get("criteres") or []]
        except Exception as ex:  # noqa: BLE001
            contenu["ia_erreur"] = str(ex)[:200]
    l = _charger()
    p = _ajouter(l, "criteres", "ia" if avec_ia else "reconstruction", cle, cle, None,
                 [f"{len(caps)} fonctionnalité(s) observée(s) liée(s) à {cle}" if caps else "aucune observation liée : critère générique à confirmer"], contenu,
                 cle_unique=f"criteres:{cle}")
    _sauver(l)
    return p


# =========================================================================== F4 : rapprochement exigences ↔ tests Xray
def analyser_liens(seuil: int = SEUIL_LIEN, max_par_exigence: int = 3) -> dict:
    """Correspondances exigence ↔ test absentes de Jira / Xray : score de confiance (0-100) expliqué par ses composantes.
    Ne crée jamais de lien : propositions « à valider » (ou « analyse nécessaire » sous 70)."""
    d = _donnees()
    ex, tests = d["exigences"], d["tests"]
    textes = {**{f"E:{k}": _texte_exigence(e) for k, e in ex.items()}, **{f"T:{k}": _texte_test(t) for k, t in tests.items()}}
    corpus = Corpus(textes)
    l = _charger()
    rejetes = {p["cle_unique"] for p in l if p["type"] == "lien_test" and p["statut"] == "rejetee"}
    nouvelles = 0
    for k, e in ex.items():
        cands = []
        for tk, t in tests.items():
            if k in d["liens"].get(tk, set()) or f"lien:{k}:{tk}" in rejetes:
                continue
            cos, communs = corpus.cosinus(f"E:{k}", f"T:{tk}")
            module = bool(t.get("module")) and (t.get("module") in (e.get("composants") or []) or similarite(t.get("module") or "", " ".join(e.get("composants") or [])) > 0.5)
            libelles = set(t.get("libelles") or []) & set((e.get("composants") or []) + (e.get("versions") or []))
            crit_ok = sum(1 for c in e.get("criteres") or [] if similarite(c, textes[f"T:{tk}"]) >= 0.2)
            score = round(min(100, 100 * (0.65 * min(1.0, cos * 1.6) + (0.15 if module else 0) + (0.05 if libelles else 0)
                                          + 0.15 * (crit_ok / max(1, len(e.get("criteres") or [])) if e.get("criteres") else 0))))
            if score >= seuil:
                raisons = [f"termes communs : {', '.join(communs)} (similarité {round(100 * cos)} %)"] if communs else []
                if module:
                    raisons.append(f"même module / composant ({t.get('module')})")
                if libelles:
                    raisons.append(f"libellés / versions communs : {', '.join(sorted(libelles))}")
                if crit_ok:
                    raisons.append(f"{crit_ok} critère(s) d'acceptation retrouvé(s) dans les étapes du test")
                cands.append((score, tk, raisons))
        for score, tk, raisons in sorted(cands, reverse=True)[:max_par_exigence]:
            avant = len(l)
            _ajouter(l, "lien_test", "analyse", k, tk, score, raisons,
                     {"exigence": k, "exigence_resume": e.get("resume", ""), "test": tk, "test_resume": tests[tk].get("resume", ""),
                      "fonctionnalite": (d["parents"].get(e.get("parent") or "") or {}).get("resume", ""),
                      "decision": "à valider" if score >= 70 else "analyse nécessaire"}, cle_unique=f"lien:{k}:{tk}")
            nouvelles += len(l) > avant
    _sauver(l)
    return {"nouvelles": nouvelles, "propositions": len([p for p in l if p["type"] == "lien_test" and p["statut"] == "proposee"])}


# =========================================================================== décisions et synchronisation
def decider(pid: str, decision: str, motif: str = "", modifications: dict | None = None) -> dict:
    """valider / rejeter (motif obligatoire) / modifier une proposition. Valider un lien ou créer dans Jira demande le
    rôle relecteur ; rien n'est encore écrit dans Jira / Xray (voir synchroniser)."""
    from atelier.domain import roles

    l = _charger()
    p = next((x for x in l if x["id"] == pid), None)
    if not p:
        raise KeyError(f"Proposition inconnue : {pid}")
    if decision == "modifier":
        roles.exiger("construire")
        if p["statut"] not in ("proposee", "validee"):
            raise ValueError("Seule une proposition en cours se modifie.")
        champs = {k: v for k, v in (modifications or {}).items() if k in ("titre", "en_tant_que", "je_souhaite", "afin_de", "criteres", "epic", "projet_jira", "classe", "justification_utilisateur")}
        p["contenu"].update(champs)
        p["historique"].append({"date": _maintenant(), "auteur": _auteur(), "action": "modifiee", "detail": ", ".join(champs)})
    elif decision in ("valider", "rejeter"):
        roles.exiger("decider_revue" if p["type"] == "lien_test" else "construire")
        if p["statut"] != "proposee":
            raise ValueError(f"Proposition déjà {p['statut']}.")
        if decision == "rejeter" and not motif.strip():
            raise ValueError("Un rejet doit être motivé.")
        if p["type"] == "classement_orphelin" and p["contenu"].get("classe") == "conserver" and not (motif.strip() or p["contenu"].get("justification_utilisateur")):
            raise ValueError("Conserver un test non rattaché demande une justification.")
        p["statut"] = "validee" if decision == "valider" else "rejetee"
        p["validateur"], p["valide_le"] = _auteur(), _maintenant()
        p["historique"].append({"date": _maintenant(), "auteur": _auteur(), "action": p["statut"], "detail": motif.strip()})
    else:
        raise ValueError("Décision : valider, rejeter ou modifier.")
    _sauver(l)
    return p


def regrouper(ids: list[str], titre: str = "") -> dict:
    """Fusionne plusieurs propositions de Story en une seule (critères et observations réunis) ; les autres sont « regroupées »."""
    l = _charger()
    ps = [x for x in l if x["id"] in ids and x["type"] == "user_story" and x["statut"] == "proposee"]
    if len(ps) < 2:
        raise ValueError("Choisir au moins deux propositions de Story en cours.")
    garde = ps[0]
    for x in ps[1:]:
        garde["contenu"]["criteres"] += [c for c in x["contenu"]["criteres"] if c not in garde["contenu"]["criteres"]]
        garde["contenu"]["observations"] = (garde["contenu"].get("observations") or []) + (x["contenu"].get("observations") or [])
        x["statut"] = "regroupee"
        x["historique"].append({"date": _maintenant(), "auteur": _auteur(), "action": "regroupee", "detail": f"dans {garde['id']}"})
    if titre.strip():
        garde["contenu"]["titre"] = titre.strip()
    garde["historique"].append({"date": _maintenant(), "auteur": _auteur(), "action": "regroupement", "detail": ", ".join(x["id"] for x in ps[1:])})
    _sauver(l)
    return garde


def synchroniser(pid: str, jira=None) -> dict:
    """Écrit dans Jira / Xray une proposition VALIDÉE, sur demande explicite : Story créée (rattachée à son Epic),
    lien natif « Test » exigence ↔ test (sans doublon), ou critères ajoutés en commentaire. Journalisé."""
    from atelier.domain import roles
    from atelier.integrations.jira import JiraClient

    roles.exiger("decider_revue")
    l = _charger()
    p = next((x for x in l if x["id"] == pid), None)
    if not p:
        raise KeyError(f"Proposition inconnue : {pid}")
    if p["statut"] != "validee":
        raise ValueError("Seule une proposition validée se synchronise.")
    jira = jira or JiraClient()
    if not getattr(jira, "enabled", True):
        raise RuntimeError("Jira non configuré (Paramètres › Connexions).")
    c = p["contenu"]
    if p["type"] == "user_story":
        if not c.get("projet_jira"):
            raise ValueError("Projet Jira de la Story à préciser (modifier la proposition).")
        desc = [f"En tant que {c['en_tant_que']}, je souhaite {c['je_souhaite']} afin de {c['afin_de']}.", "", "Critères d'acceptation :"]
        desc += [f"- {x['texte']} [{ORIGINES_CRITERE.get(x['origine'], x['origine'])}]" for x in c["criteres"]]
        desc += ["", f"Reconstruite par l'atelier depuis {len(c.get('observations') or [])} observation(s) de l'application (proposition {p['id']})."]
        cle = jira.creer_ticket(c["projet_jira"], c["titre"], "\n".join(desc), os.environ.get("JIRA_TYPE_STORY", "Story"), parent=c.get("epic") or "")
        resultat = {"cree": cle, "epic": c.get("epic") or ""}
    elif p["type"] == "lien_test":
        existants = {(x.get("outwardIssue") or x.get("inwardIssue") or {}).get("key") for x in
                     ((jira.get(f"/rest/api/3/issue/{c['exigence']}?fields=issuelinks") or {}).get("fields") or {}).get("issuelinks") or []}
        if c["test"] in existants:
            resultat = {"deja_lie": True}
        else:
            jira.link(c["test"], c["exigence"], os.environ.get("JIRA_LIEN_COUVERTURE", "Test"))  # même convention que Test Design
            resultat = {"lie": f"{c['test']} → {c['exigence']}"}
    elif p["type"] == "criteres":
        texte = "Critères d'acceptation proposés par l'atelier (validés par l'équipe QA) :\n" + "\n".join(
            f"- {x['texte']} [{ORIGINES_CRITERE.get(x['origine'], x['origine'])}]" for x in c["criteres"])
        jira.commenter(p["objet_source"], texte)
        resultat = {"commentaire": p["objet_source"]}
    else:
        raise ValueError("Ce type de proposition ne s'écrit pas dans Jira / Xray.")
    p["statut"] = "synchronisee"
    p["synchronisation"] = {"date": _maintenant(), **resultat}
    p["historique"].append({"date": _maintenant(), "auteur": _auteur(), "action": "synchronisee", "detail": json.dumps(resultat, ensure_ascii=False)})
    _sauver(l)
    _journal_synchro({"proposition": pid, "type": p["type"], **resultat})
    return p


# =========================================================================== F5 : tests manquants
def tests_manquants() -> dict:
    """Diagnostic par exigence (couvert, aucun test, couverture à vérifier) et tests sans exigence identifiée."""
    from atelier.intelligence import couverture_exigences

    from atelier.intelligence import testabilite_us

    c = couverture_exigences.calculer()
    try:  # suivi dans Test Design › US à couvrir : une seule liste de travail, ici on n'en montre que l'état
        suivis = testabilite_us._us()
    except Exception:  # noqa: BLE001 — Test Design absent ou illisible : le diagnostic reste utile
        suivis = {}
    lignes = []
    for x in c["exigences"]:
        n = len(x["tests"])
        diag = "aucun test associé" if not n else "couverture à vérifier" if (x["etat"] == "partielle" or (n == 1 and len(x["criteres"]) > 1)) else "couvert"
        lignes.append({"exigence": x["cle"], "resume": x["resume"], "fonctionnalite": x["fonctionnalite"], "tests": n, "diagnostic": diag,
                       "criteres": len(x["criteres"]), "suivi": ({"statut": suivis[x["cle"]].get("statut") or "Détectée",
                                                                   "cas": len(suivis[x["cle"]].get("cas") or [])} if x["cle"] in suivis else None)})
    ordre = {"aucun test associé": 0, "couverture à vérifier": 1, "couvert": 2}
    return {"exigences": sorted(lignes, key=lambda x: (ordre[x["diagnostic"]], x["exigence"])), "tests_sans_exigence": c["tests_sans_exigence"]}


def envoyer_vers_test_design(cle: str) -> dict:
    """Exigence sans test → Test Design (« US à couvrir ») : cas proposés depuis ses critères, à revoir, valider puis
    publier dans Xray selon le mapping de Test Design. Aucun test Xray n'est créé ici."""
    from atelier.intelligence import testabilite_us

    d = _donnees()
    e = d["exigences"].get(cle)
    if not e:
        raise KeyError(f"Exigence {cle} hors périmètre importé.")
    testabilite_us.importer_exigence({"cle": cle, "resume": e.get("resume", ""), "description": e.get("description", ""),
                                      "criteres": e.get("criteres") or [], "statut_jira": e.get("statut", ""), "tests_lies": sorted(e.get("tests_jira") or [])})
    return testabilite_us.proposer_cas(cle)


# =========================================================================== F6 : tests orphelins
def orphelins() -> list[dict]:
    """Tests sans exigence : meilleure correspondance (Story, Feature / Epic, fonctionnalité observée, règle) ou « orphelin »."""
    from atelier.discovery import connaissance

    d = _donnees()
    g = connaissance.construire()
    regles = [n for n in g.noeuds.values() if n.type == "regle"]
    caps = capacites()
    classes = {p["objet_source"]: p for p in _charger() if p["type"] == "classement_orphelin" and p["statut"] in ("proposee", "validee", "synchronisee")}
    out = []
    for tk, t in d["tests"].items():
        if d["liens"].get(tk):
            continue
        txt = _texte_test(t)
        best = lambda items, f: max(((similarite(txt, f(x)), x) for x in items), key=lambda z: z[0], default=(0, None))  # noqa: E731
        s_ex, e = best(d["exigences"].items(), lambda kv: _texte_exigence(kv[1]))
        s_par, par = best({**d["parents"], **d["epics"]}.items(), lambda kv: kv[1].get("resume", ""))
        s_cap, cap = best(caps, lambda c: c["nom"] + " " + " ".join(o["texte"] for o in c["observations"]))
        s_reg, reg = best(regles, lambda n: n.libelle)
        candidats = [x for x in [
            {"nature": "Story", "cle": e[0], "libelle": e[1].get("resume", ""), "score": round(100 * s_ex)} if e and s_ex >= 0.12 else None,
            {"nature": "Feature / Epic", "cle": par[0], "libelle": par[1].get("resume", ""), "score": round(100 * s_par)} if par and s_par >= 0.15 else None,
            {"nature": "fonctionnalité observée", "cle": cap["id"], "libelle": cap["nom"], "score": round(100 * s_cap)} if cap and s_cap >= 0.12 else None,
            {"nature": "règle métier", "cle": reg.id, "libelle": reg.libelle, "score": round(100 * s_reg)} if reg and s_reg >= 0.15 else None] if x]
        out.append({"test": tk, "resume": t.get("resume", ""), "module": t.get("module") or "", "candidats": sorted(candidats, key=lambda x: -x["score"]),
                    "statut": "candidat trouvé" if candidats else "orphelin", "classement": classes.get(tk)})
    return out


def classer_orphelin(test: str, classe: str, cible: str = "", justification: str = "") -> dict:
    """associer (à une exigence → proposition de lien) / nouvelle_exigence (→ proposition de Story) / technique /
    transversal / conserver (justification). Proposition à valider, jamais appliquée directement."""
    if classe not in ("associer", "nouvelle_exigence", "technique", "transversal", "conserver"):
        raise ValueError("Classement : associer, nouvelle_exigence, technique, transversal ou conserver.")
    d = _donnees()
    t = d["tests"].get(test)
    if not t:
        raise KeyError(f"Test inconnu : {test}")
    l = _charger()
    if classe == "associer":
        if cible not in d["exigences"]:
            raise ValueError("Exigence cible inconnue (périmètre importé).")
        p = _ajouter(l, "lien_test", "classement_orphelin", cible, test, None, [f"rattachement manuel du test orphelin {test}"] + ([justification] if justification else []),
                     {"exigence": cible, "exigence_resume": d["exigences"][cible].get("resume", ""), "test": test, "test_resume": t.get("resume", ""), "decision": "à valider"},
                     cle_unique=f"lien:{cible}:{test}")
    elif classe == "nouvelle_exigence":
        crit = [{"texte": s.get("resultat") or s.get("action", ""), "origine": "deduit", "ref": f"test:{test}"} for s in t.get("etapes") or [] if isinstance(s, dict) and (s.get("resultat") or s.get("action"))][:8]
        p = _ajouter(l, "user_story", "test_orphelin", test, "", None, [f"exigence implicite couverte par le test {test}"],
                     {"titre": t.get("resume", test), "en_tant_que": "utilisateur de l'application", "je_souhaite": t.get("resume", ""), "afin_de": "(à confirmer)",
                      "criteres": crit or [{"texte": "À préciser depuis le test", "origine": "a_confirmer", "ref": f"test:{test}"}], "epic": "", "observations": [],
                      "projet_jira": _projet_jira(d), "test_source": test}, cle_unique=f"story_test:{test}")
    else:
        if classe == "conserver" and not justification.strip():
            raise ValueError("Conserver un test non rattaché demande une justification.")
        p = _ajouter(l, "classement_orphelin", "utilisateur", test, "", None, [justification] if justification else [],
                     {"test": test, "classe": classe, "justification_utilisateur": justification}, cle_unique=f"orphelin:{test}")
    _sauver(l)
    return p


# =========================================================================== F7 : Coverage Intelligence (4 dimensions)
def vue() -> dict:
    from atelier.intelligence import couverture_exigences, patrimoine_xray

    c = couverture_exigences.calculer()
    d = _donnees()
    doc = qualite_documentaire()
    caps = capacites()
    ps = _charger()
    pat = patrimoine_xray.charger_vue() or {"tests": [], "executions": []}
    ex = c["exigences"]
    n = len(ex)
    pct = lambda a, b: round(100 * a / b, 1) if b else None  # noqa: E731
    stories = [e for e in d["exigences"].values()]
    sans_desc = sum(1 for e in stories if not (e.get("description") or "").strip())
    sans_ac = sum(1 for e in stories if not e.get("criteres"))
    bien_doc = sum(1 for e in stories if (e.get("description") or "").strip() and e.get("criteres"))
    tests_lies = {t["cle"] for x in ex for t in x["tests"]}
    statuts = Counter((((d["tests"].get(t) or {}).get("statut_xray") or {}).get("statut") or "NON EXÉCUTÉ").upper() for t in tests_lies)
    passes = sum(v for k, v in statuts.items() if "PASS" in k)
    echecs = sum(v for k, v in statuts.items() if "FAIL" in k)
    bloques = sum(v for k, v in statuts.items() if "BLOCK" in k or "ABORT" in k)
    non_exec = sum(v for k, v in statuts.items() if k in ("NON EXÉCUTÉ", "TO DO", "TODO", "EXECUTING"))
    dates = [x.get("cree") for x in pat.get("executions") or [] if x.get("cree")]
    auto = {"automatisees": sum(1 for x in ex if x["tests"] and all(t["automatise"] for t in x["tests"])),
            "partielles": sum(1 for x in ex if x["tests"] and any(t["automatise"] for t in x["tests"]) and not all(t["automatise"] for t in x["tests"])),
            "manuelles_seulement": sum(1 for x in ex if x["manuelle_seulement"]), "sans_test": sum(1 for x in ex if not x["tests"])}
    liens = [p for p in ps if p["type"] == "lien_test"]
    return {
        "import": c["import"],
        "overview": {"macro_fonctionnalites": len({x["macro"] for x in ex if x["macro"]}), "fonctionnalites": len({x["fonctionnalite"] for x in ex if x["fonctionnalite"]}),
                     "fonctionnalites_decouvertes": len(caps), "stories": n, "tests_xray": len(d["tests"]),
                     "ecarts": len(doc) + sum(1 for x in caps if not x["documentee"]) + auto["sans_test"] + len(c["tests_sans_exigence"])},
        "documentaire": {"taux": pct(bien_doc, n), "stories_documentees": bien_doc, "sans_description": sans_desc, "sans_criteres": sans_ac,
                         "fonctionnalites_decouvertes_sans_exigence": sum(1 for x in caps if not x["documentee"]), "anomalies": len(doc),
                         "definition": "Story documentée : description ET critères d'acceptation."},
        "tracabilite": {"taux": pct(n - auto["sans_test"], n), "exigences_avec_tests": n - auto["sans_test"], "exigences_sans_tests": auto["sans_test"],
                        "tests_orphelins": len(c["tests_sans_exigence"]), "liens_proposes": sum(1 for p in liens if p["statut"] == "proposee"),
                        "liens_valides": sum(1 for p in liens if p["statut"] == "validee"), "liens_synchronises": sum(1 for p in liens if p["statut"] == "synchronisee"),
                        "definition": "Exigence tracée : au moins un test Xray lié nativement (lien lu depuis l'exigence ou le test)."},
        "execution": {"taux": pct(len(tests_lies) - non_exec, len(tests_lies)), "tests_executes": len(tests_lies) - non_exec, "tests_non_executes": non_exec,
                      "passed": passes, "failed": echecs, "blocked": bloques, "derniere_execution": max(dates) if dates else None,
                      "definition": "Tests liés aux exigences dont le dernier statut Xray n'est pas TO DO / EXECUTING / vide."},
        "automatisation": {"taux": pct(auto["automatisees"] + auto["partielles"], n), **auto,
                           "definition": "Exigence automatisée : tous ses tests automatisés ; partielle : certains ; manuelle seulement : aucun."},
        "propositions": Counter(f"{p['type']}:{p['statut']}" for p in ps)}
