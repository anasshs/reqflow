"""Testabilité des User Stories : politique actionnable de la stratégie de test.

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
              "type_test": type_test, "min_tests": max(1, int(e.get("min_tests") or 1))}
    if not propre["projet_xray"]:
        raise ValueError("Projet Xray cible requis (ou un projet actif avec une clé Xray).")
    l = [x for x in espaces() if x["projet_jira"] != cle] + [propre]
    _ecrire("espaces.yaml", yaml.safe_dump({"espaces": l}, allow_unicode=True, sort_keys=False))
    _journaliser("politique_espace", espace=cle, actif=propre["actif"])
    return l


def supprimer_espace(cle: str) -> list[dict]:
    l = [x for x in espaces() if x["projet_jira"] != cle]
    _ecrire("espaces.yaml", yaml.safe_dump({"espaces": l}, allow_unicode=True, sort_keys=False))
    _journaliser("politique_espace_retire", espace=cle)
    return l


def jql_espace(e: dict) -> str:
    parts = [f'project = "{e["projet_jira"]}"']
    if e.get("types_issue"):
        parts.append("issuetype in (" + ", ".join(f'"{t}"' for t in e["types_issue"]) + ")")
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


def detecter(jira=None, limite: int = 500) -> dict:
    """Lecture seule dans Jira : US des espaces actifs, description, critères, tests déjà liés (liens de type « test »)."""
    from atelier.integrations.jira import JiraClient, adf_vers_texte

    jira = jira or JiraClient()
    if not getattr(jira, "enabled", True):
        raise RuntimeError("Jira non configuré (Paramètres › Connexions).")
    champ_crit = os.environ.get("JIRA_CHAMP_CRITERES", "").strip()
    champs = ["summary", "description", "status", "issuelinks", "issuetype", "assignee", "updated"] + ([champ_crit] if champ_crit else [])
    d = _us()
    bilan = {"espaces": 0, "us": 0, "nouvelles": 0, "deja_couvertes": 0}
    for e in [x for x in espaces() if x.get("actif")]:
        bilan["espaces"] += 1
        for i in jira.rechercher(jql_espace(e), champs, limite):
            f = i.get("fields") or {}
            liens = [l.get("outwardIssue") or l.get("inwardIssue") or {} for l in f.get("issuelinks") or []
                     if "test" in ((l.get("type") or {}).get("name") or "").lower()]
            tests_lies = sorted({x.get("key") for x in liens if x.get("key")})
            crit = f.get(champ_crit) if champ_crit else None
            u = d.get(i["key"])
            base = {"cle": i["key"], "espace": e["projet_jira"], "resume": f.get("summary") or "",
                    "description": adf_vers_texte(f.get("description")), "criteres_jira": adf_vers_texte(crit) if crit else "",
                    "statut_jira": (f.get("status") or {}).get("name", ""), "assigne": ((f.get("assignee") or {}).get("displayName") or ""),
                    "maj_jira": f.get("updated", ""), "tests_lies": tests_lies}
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
            bilan["deja_couvertes"] += u["statut"].startswith("Couverte")
            bilan["us"] += 1
            d[i["key"]] = u
    _sauver_us(d)
    _journaliser("detection", **{k: v for k, v in bilan.items()})
    return {**bilan, "file": file()}


def file(espace: str = "", statut: str = "") -> list[dict]:
    return [{k: u.get(k) for k in ("cle", "espace", "resume", "statut", "statut_jira", "assigne", "tests_lies")}
            | {"constats": len(u.get("constats") or []), "cas": len(u.get("cas") or []), "alertes": len(u.get("alertes") or [])}
            for u in _us().values() if (not espace or u["espace"] == espace) and (not statut or u["statut"] == statut)]


def detail(cle: str) -> dict:
    _, u = _exiger(cle)
    e = next((x for x in espaces() if x["projet_jira"] == u["espace"]), {})
    return {**u, "politique": e, "journal": journal(cle, 50)}


def indicateurs() -> dict:
    from collections import Counter

    d = _us().values()
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
    if decision == "valider":
        vide = [e for e in c["etapes"] if not e["action"].strip() or e["resultat"].strip() in ("", "à préciser")]
        if c["etapes"] and vide:
            raise ValueError("Chaque étape doit avoir une action et un résultat attendu précis avant validation.")
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
    e = next((x for x in espaces() if x["projet_jira"] == u["espace"]), None)
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
