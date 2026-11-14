"""Failure Analysis : comprendre pourquoi un test a échoué (cahier des charges « Module Failure Analysis »).

Les échecs viennent des runs réels (results/runs). Le diagnostic de base est DÉTERMINISTE : des règles
explicables produisent des hypothèses classées avec leurs preuves ; la « force » d'une hypothèse est un
libellé (élevée / moyenne / faible) tiré de la règle, jamais un pourcentage inventé. L'IA (Claude) n'est
consultée qu'à la demande, sur un contexte sans données sensibles, et ne modifie rien.
Métadonnées dans le projet : analyses/echecs.json (statut, diagnostic confirmé, regroupement, Jira,
retests, corrections) et analyses/journal.jsonl. Un résultat d'exécution n'est jamais modifié.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

from atelier.domain import projet
from atelier.intelligence.strategie import _auteur, _ecrire_atomique, _maintenant

CATEGORIES = ["Application Defect", "Locator Issue", "Automation Defect", "Test Data Issue", "Environment Issue", "Timing Issue",
              "Framework Issue", "Network Issue", "Assertion Issue", "Test Design Issue", "Blocked", "Unknown"]
STATUTS = ["New", "Diagnosis Proposed", "Human Review", "Confirmed", "Fix In Progress", "Fixed", "Retest", "Closed",
           "Reopened", "False Positive", "Inconclusive", "Blocked"]
STATUTS_CORRECTION = ["Proposed", "Under Review", "Approved", "Applied", "Validated", "Rejected"]
# (catégorie, motif, force, explication) — évaluées dans l'ordre, plusieurs peuvent correspondre
REGLES = [
    ("Locator Issue", r"(?i)(no element|element .*not found|did not match any element|unable to locate|nosuchelement|waiting for (selector|locator)|"
     r"element .*not (visible|attached)|locator .*not found)", "élevée", "Le locator ne trouve pas l'élément à l'écran."),
    ("Timing Issue", r"(?i)(timeout|timed out|délai dépassé|wait until|did not become)", "moyenne", "Attente expirée : élément ou écran trop lent, ou absent."),
    ("Application Defect", r"(?i)(attendu ?:.*trouvé ?:|expected .* but (was|got)|should be equal|!=|does not contain|ne contient pas)",
     "moyenne", "L'écran répond, mais le résultat observé diffère du résultat attendu."),
    ("Assertion Issue", r"(?i)(attendu ?:.*trouvé ?:|should be equal|!=)", "faible", "La vérification attendue peut être mal définie (à confirmer avec le métier)."),
    ("Automation Defect", r"(?i)(no keyword with name|variable '?\$\{[^}]+\}'? not found|resolving variable|non-existing|keyword .* expected \d+ argument|syntax)",
     "élevée", "Erreur du script (keyword, variable ou argument)."),
    ("Test Data Issue", r"(?i)(bloqué données|jdd|dictionary .* has no key|has no key|aucun compte|données? (absentes?|manquantes?))",
     "élevée", "Donnée de test absente ou invalide."),
    ("Network Issue", r"(?i)(connection refused|econnrefused|name or service not known|net::err|getaddrinfo|ssl|certificate|503|502|504)",
     "moyenne", "Service distant ou réseau indisponible."),
    ("Environment Issue", r"(?i)(environment|environnement|server error|500 internal|maintenance)", "faible", "L'environnement de test semble en cause."),
    ("Framework Issue", r"(?i)(appium|webdriver|session not created|browser (has been )?closed|playwright|chromedriver|xcuitest|uiautomator)",
     "moyenne", "Problème du moteur d'automatisation (driver, Appium, navigateur)."),
]
FORCE = {"élevée": 3, "moyenne": 2, "faible": 1}


def _dossier():
    return projet.PROJECT_DIR / "analyses"


def _stock() -> dict:
    f = _dossier() / "echecs.json"
    return json.loads(f.read_text("utf-8")) if f.exists() else {}


def _sauver(st: dict):
    _ecrire_atomique(_dossier() / "echecs.json", json.dumps(st, ensure_ascii=False, indent=1))


def _journaliser(op: str, **d):
    f = _dossier() / "journal.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": _maintenant(), "auteur": _auteur(), "op": op, **d}, ensure_ascii=False) + "\n")


def journal(limite: int = 300) -> list[dict]:
    f = _dossier() / "journal.jsonl"
    l = [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()] if f.exists() else []
    return list(reversed(l))[:limite]


def nettoyer(message: str) -> str:
    """Message lisible : sans HTML ni l'annexe ajoutée par « rebot --merge » (ancien statut d'une tentative)."""
    message = message or ""
    nouveau = re.search(r'class="new-message">[^<]*</span>(.*?)(<br>|<hr>|$)', message)
    m = nouveau.group(1) if nouveau else re.split(r"<hr>", message)[0]
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m)).strip()


def signature(message: str, etape: str = "", locator: str = "") -> str:
    """Empreinte d'un échec : message normalisé (nombres, guillemets, identifiants retirés) + étape + locator."""
    m = re.sub(r"\d+", "#", message or "")
    m = re.sub(r"«[^»]*»|\"[^\"]*\"|'[^']*'", "«…»", m)
    return re.sub(r"\s+", " ", f"{m[:160]}|{etape}|{locator}").strip().lower()


def hypotheses(message: str, etape: dict | None = None, contexte: dict | None = None) -> list[dict]:
    """Hypothèses classées, chacune avec sa règle et ses preuves (déterministe, explicable)."""
    contexte = contexte or {}
    out = []
    for cat, motif, force, expl in REGLES:
        m = re.search(motif, message or "")
        if m:
            preuves = [f"Message : « {m.group(0)[:120]} »"]
            if etape and etape.get("locator"):
                preuves.append(f"Locator utilisé : {etape['locator']} ({etape.get('strategie') or '?'})")
            out.append({"categorie": cat, "force": force, "explication": expl, "preuves": preuves, "regle": motif[:60]})
    loc = (contexte.get("locator_etat") or "")
    if loc in ("Obsolete", "Missing"):
        out.append({"categorie": "Locator Issue", "force": "élevée", "explication": f"Le locator est {loc} dans le référentiel (carte de l'application).",
                    "preuves": [f"État du locator : {loc}"], "regle": "référentiel des locators"})
    if contexte.get("precedent") == "PASS" and out:
        out[0]["preuves"].append("Le même test réussissait au run précédent : régression probable (application, données ou environnement).")
    if not out:
        out.append({"categorie": "Unknown", "force": "faible", "explication": "Aucune règle ne reconnaît ce message.", "preuves": [f"Message : « {(message or '')[:120]} »"], "regle": ""})
    # une même catégorie peut venir de deux règles : on garde la plus forte, puis tri par force
    meilleures: dict = {}
    for h in out:
        if h["categorie"] not in meilleures or FORCE[h["force"]] > FORCE[meilleures[h["categorie"]]["force"]]:
            meilleures[h["categorie"]] = h
    return sorted(meilleures.values(), key=lambda h: -FORCE[h["force"]])


# =========================================================================== collecte
def collecter(limite_runs: int = 30) -> list[dict]:
    """Échecs des runs réels récents (un événement par test en échec), enrichis de leur suivi."""
    from atelier.execution import historique

    st = _stock()
    runs = [r for r in historique.lister(limite_runs) if not r["dry_run"] and r.get("echecs")]
    vus: dict = {}  # nom du test -> statuts des runs plus anciens (pour récurrence / régression)
    tous = []
    for r in reversed(runs):  # du plus ancien au plus récent
        try:
            d = historique.detail(r["id"])
        except Exception:
            continue
        for t in d.get("tests", []):
            precedent = (vus.get(t["nom"]) or [None])[-1]
            vus.setdefault(t["nom"], []).append(t["statut"])
            if t["statut"] != "FAIL":
                continue
            eid = f"{r['id']}::{t['id']}"
            s = st.get(eid, {})
            tous.append({"id": eid, "run": r["id"], "test_id": t["id"], "nom": t["nom"], "cle_xray": (t.get("cles_xray") or [""])[0],
                         "message": nettoyer(t["message"]), "date": r["debut"], "plateforme": r["plateforme"], "campagne": r.get("campagne", ""),
                         "environnement": (r.get("contexte") or {}).get("environnement", ""), "commit": (r.get("contexte") or {}).get("commit", ""),
                         "version": (r.get("contexte") or {}).get("version_application", ""), "precedent": precedent,
                         "recurrent": vus[t["nom"]][:-1].count("FAIL") > 0, "signature": signature(nettoyer(t["message"])),
                         "statut": s.get("statut", "Diagnosis Proposed"), "categorie_confirmee": s.get("categorie", ""),
                         "groupe": s.get("groupe", ""), "jira": s.get("jira", ""), "retests": s.get("retests", [])})
    for e in tous:
        e["categorie_probable"] = hypotheses(e["message"], None, {"precedent": e["precedent"]})[0]["categorie"]
        e["groupe"] = e["groupe"] or "G-" + hashlib.sha1(e["signature"].encode()).hexdigest()[:6].upper()
    return list(reversed(tous))


def _evenement(eid: str) -> dict:
    e = next((x for x in collecter(60) if x["id"] == eid), None)
    if not e:
        raise KeyError(f"Échec inconnu : {eid}")
    return e


def investigation(eid: str) -> dict:
    """Écran central : étapes, étape fautive (locator, écran de référence), preuves, hypothèses, tests impactés."""
    from atelier.execution import historique

    e = _evenement(eid)
    d = historique.detail_test(e["run"], e["test_id"])
    fautive = d["etapes"][d["etape_en_echec"]] if d["etape_en_echec"] is not None else None
    loc_etat, proposition = "", None
    if fautive and fautive.get("locator"):
        loc_etat, proposition = _diagnostic_locator(fautive["locator"], d.get("plateforme", ""))
    hyp = hypotheses(e["message"], fautive, {"locator_etat": loc_etat, "precedent": e["precedent"]})
    similaires = [x for x in collecter(60) if x["groupe"] == e["groupe"] and x["id"] != eid]
    return {**e, "detail": d, "etape_fautive": fautive, "hypotheses": hyp, "locator_etat": loc_etat, "proposition_locator": proposition,
            "impactes": tests_impactes(fautive), "similaires": similaires[:20], "suivi": _stock().get(eid, {}),
            "brouillon_jira": brouillon_jira(e, d, fautive)}


def _diagnostic_locator(valeur: str, plateforme: str) -> tuple[str, dict | None]:
    """État du locator (référentiel) et, si l'élément de même clé est observé ailleurs dans la carte, proposition."""
    from atelier.generation import studio

    for l in studio.locators():
        if l["valeur"] == valeur:
            prop = None
            if l["etat"] == "Obsolete":
                prop = {"actuel": valeur, "cle": f"{l['ecran']}.{l['cle']}", "propositions": _observes(l["ecran"], l["cle"], plateforme or l["plateforme"]),
                        "justification": "La valeur n'est plus observée sur l'écran cartographié ; valeurs observées pour la même clé ci-dessous."}
            return l["etat"], prop
    return "", None


def _observes(ecran: str, cle: str, plateforme: str) -> list[str]:
    import yaml

    from atelier.discovery import carte

    try:
        racine = carte._racine() / (carte.app_courante() or "") / "ecrans"
        for f in racine.glob("*.yaml"):
            d = yaml.safe_load(f.read_text("utf-8")) or {}
            if d.get("nom") != ecran:
                continue
            for k, el in (d.get("elements") or {}).items():
                if k.endswith(cle) or cle.endswith(k.split("_", 1)[-1]):
                    return (el.get("locators") or {}).get(plateforme, [])
    except Exception:
        pass
    return []


def tests_impactes(etape: dict | None) -> list[dict]:
    """Tests du dépôt qui utilisent le même locator (ou, à défaut, le même keyword)."""
    if not etape:
        return []
    from atelier.execution.depot_robot import fermeture_keywords, lire_depot, normaliser

    inv = lire_depot()
    cible_loc = etape.get("locator") or ""
    ids_loc = {f"{l['ecran']}.{l['cle']}" for l in inv["locators"].values() if l["valeur"] == cible_loc} if cible_loc else set()
    kw = normaliser(re.sub(r"^(given|when|then|and|but)\s+", "", etape.get("nom", ""), flags=re.I))
    out = []
    for t in inv["tests"].values():
        kws = fermeture_keywords(inv, t["keywords"])
        locs = {f"{e}.{c}" for k in kws if k in inv["keywords"] for e, c in inv["keywords"][k].get("locators") or []}
        raison = "même locator" if ids_loc & locs else "même keyword" if kw in kws else ""
        if raison:
            out.append({"test": t["nom"], "fichier": t["fichier"], "cle_xray": (t.get("cles_xray") or [""])[0], "raison": raison})
    return out


def brouillon_jira(e: dict, d: dict, fautive: dict | None) -> dict:
    """Anomalie préparée (jamais créée automatiquement) ; données du JDD exclues."""
    etapes = [x["nom"] for x in d["etapes"] if x["nom"] not in ("Initialiser Le Test", "Terminer Le Test")]
    attendu, trouve = "", ""
    m = re.search(r"Attendu ?: ?(.+?)\. ?Trouvé ?: ?(.+)", e["message"])
    if m:
        attendu, trouve = m.group(1).strip(), m.group(2).strip()
    return {"summary": f"[{e['cle_xray'] or e['nom']}] {e['nom']} : échec à l'étape « {(fautive or {}).get('nom', '?')} »",
            "steps": etapes, "expected": attendu or "(voir le test Xray)", "actual": trouve or e["message"][:300],
            "environment": f"{e['plateforme']} · {e['environnement'] or '—'}", "version": e["version"] or "—",
            "evidence": [f"{d['dossier']}/{c}" for c in d.get("captures", [])], "xray": e["cle_xray"], "execution": e["run"],
            "severity_suggeree": "Majeure" if e["categorie_probable"] == "Application Defect" else "À qualifier"}


# =========================================================================== décisions humaines
def _maj(eid: str, op: str, **champs) -> dict:
    st = _stock()
    s = st.setdefault(eid, {"historique": []})
    s.update(champs)
    s.setdefault("historique", []).append({"date": _maintenant(), "auteur": _auteur(), "op": op, **{k: v for k, v in champs.items() if k != "retests"}})
    _sauver(st)
    _journaliser(op, echec=eid, **{k: v for k, v in champs.items() if isinstance(v, str)})
    return s


def decider(eid: str, decision: str, categorie: str = "", commentaire: str = "") -> dict:
    """confirmer (avec catégorie) / rejeter / inconclusif / faux_positif (justifié) / correction_en_cours / corrige / clore / rouvrir."""
    _evenement(eid)
    cibles = {"confirmer": "Confirmed", "rejeter": "Human Review", "inconclusif": "Inconclusive", "faux_positif": "False Positive",
              "correction_en_cours": "Fix In Progress", "corrige": "Fixed", "clore": "Closed", "rouvrir": "Reopened", "bloque": "Blocked"}
    if decision not in cibles:
        raise ValueError(f"Décision : {', '.join(cibles)}.")
    if decision == "confirmer" and categorie not in CATEGORIES:
        raise ValueError("Confirmer un diagnostic exige une catégorie.")
    if decision in ("faux_positif", "rejeter", "rouvrir") and not commentaire.strip():
        raise ValueError("Justification obligatoire.")
    if decision == "clore" and not any(r.get("resultat") == "PASS" for r in _stock().get(eid, {}).get("retests", [])):
        raise ValueError("Clôture impossible sans retest réussi (la fermeture Jira ne suffit pas).")
    champs = {"statut": cibles[decision], "commentaire": commentaire.strip()}
    if categorie:
        champs["categorie"] = categorie
    return _maj(eid, f"decision_{decision}", **champs)


def regrouper(eid: str, groupe: str) -> dict:
    """Regroupement réversible : groupe vide = retour au groupe calculé par la signature."""
    return _maj(eid, "regroupement", groupe=groupe.strip())


def associer_jira(eid: str, cle: str) -> dict:
    if cle and not re.fullmatch(r"[A-Z][A-Z0-9]+-\d+", cle):
        raise ValueError("Clé Jira attendue (ex. DEMO-42).")
    return _maj(eid, "jira", jira=cle)


def noter_retest(eid: str, run_id: str) -> dict:
    s = _stock().get(eid, {})
    retests = s.get("retests", []) + [{"run": run_id, "date": _maintenant(), "resultat": None}]
    return _maj(eid, "retest", statut="Retest", retests=retests)


def resultats_retests(eid: str) -> list[dict]:
    """Résultat de chaque retest lu dans son run (avant / après conservés, rien n'est écrasé)."""
    from atelier.execution import historique

    e = _evenement(eid)
    st = _stock()
    s = st.get(eid, {})
    for r in s.get("retests", []):
        try:
            t = next((x for x in historique.detail(r["run"]).get("tests", []) if x["nom"] == e["nom"]), None)
            r["resultat"], r["message"], r["duree_s"] = (t["statut"], t["message"], t["duree_s"]) if t else (None, "", None)
        except Exception:
            pass
    if s:
        _sauver(st)
    return s.get("retests", [])


# =========================================================================== IA (à la demande)
MOTIFS_SENSIBLES = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "‹email›"),
    (re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,4})?\b"), "‹iban›"),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "‹carte›"),
    (re.compile(r"(?i)\b(bearer|token|password|mot de passe|mdp|secret|pin)\b\s*[:=]?\s*\S+"), r"\1 ‹masqué›"),
    (re.compile(r"\b\d{6,}\b"), "‹nombre›"),
]


def _valeurs_jdd() -> list[str]:
    """Toutes les valeurs textuelles des jeux de données du projet (tous environnements)."""
    import yaml

    vals: set[str] = set()

    def parcourir(x):
        if isinstance(x, dict):
            for v in x.values():
                parcourir(v)
        elif isinstance(x, list):
            for v in x:
                parcourir(v)
        elif isinstance(x, (str, int, float)) and not isinstance(x, bool) and len(str(x)) >= 3:
            vals.add(str(x))

    for f in (projet.PROJECT_DIR / "data" / "jdd").glob("*.y*ml") if (projet.PROJECT_DIR / "data" / "jdd").exists() else []:
        try:
            parcourir(yaml.safe_load(f.read_text("utf-8")))
        except Exception:  # noqa: BLE001 - un JDD illisible n'empêche pas l'analyse ; il est simplement ignoré
            pass
    return sorted(vals, key=len, reverse=True)


def masquer_texte(texte: str, valeurs: list[str] | None = None) -> str:
    """Masque les valeurs de JDD connues puis les motifs sensibles (email, IBAN, carte, secret, longs nombres)."""
    t = str(texte or "")
    for v in valeurs if valeurs is not None else _valeurs_jdd():
        t = t.replace(v, "‹jdd›")
    for motif, rempl in MOTIFS_SENSIBLES:
        t = motif.sub(rempl, t)
    return t


def historique_ia(eid: str) -> list[dict]:
    f = _dossier() / "ia" / f"{re.sub(r'[^\w.-]', '_', eid)}.jsonl"
    return [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()][::-1] if f.exists() else []


def demander_ia(eid: str, client=None) -> dict:
    """Analyse IA d'un échec : message, étapes, locator, hypothèses calculées. Les valeurs de JDD et les motifs
    sensibles sont masqués AVANT l'envoi ; le contexte envoyé, le modèle et la réponse sont historisés."""
    from atelier.intelligence import assistant

    i = investigation(eid)
    if client is None:
        import os

        if not os.environ.get("ANTHROPIC_API_KEY"):
            return {"disponible": False, "raison": "ANTHROPIC_API_KEY non configurée : diagnostic par règles uniquement."}
        client = assistant._client()
    vals = _valeurs_jdd()
    ctx = {"test": i["nom"], "cle_xray": i["cle_xray"], "plateforme": i["plateforme"], "message": masquer_texte(i["message"][:800], vals),
           "etapes": [{"nom": masquer_texte(x["nom"], vals), "statut": x["statut"], "locator": x.get("locator", ""),
                       "message": masquer_texte(x.get("message", "")[:300], vals)} for x in i["detail"]["etapes"]],
           "locator_etat": i["locator_etat"], "hypotheses_calculees": [{k: h[k] for k in ("categorie", "force", "explication")} for h in i["hypotheses"]],
           "precedent": i["precedent"], "recurrent": i["recurrent"]}
    msg = client.messages.create(model=assistant.MODELE, max_tokens=900, messages=[{"role": "user", "content":
        "Tu analyses l'échec d'un test automatisé Robot Framework. Propose 1 à 3 causes probables parmi : " + ", ".join(CATEGORIES)
        + ". Pour chacune : preuves tirées du contexte uniquement, et ce qu'il faut vérifier. Ne modifie rien, n'invente aucune donnée. Réponds en français.\n\n"
        + json.dumps(ctx, ensure_ascii=False)}])
    texte = "".join(getattr(b, "text", "") for b in msg.content)
    entree = {"date": _maintenant(), "auteur": _auteur(), "modele": assistant.MODELE, "contexte_envoye": ctx, "reponse": texte,
              "statut": "Proposée (à valider)"}
    f = _dossier() / "ia" / f"{re.sub(r'[^\w.-]', '_', eid)}.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entree, ensure_ascii=False) + "\n")
    _journaliser("analyse_ia", echec=eid, modele=assistant.MODELE)
    return {"disponible": True, "reponse": texte, "modele": assistant.MODELE, "date": entree["date"],
            "avertissement": "Proposition IA à valider : aucune modification n'est appliquée. Données masquées avant envoi ; analyse historisée."}


# =========================================================================== vue d'ensemble et tendances
def vue_ensemble() -> dict:
    from collections import Counter

    from atelier.execution import centre, historique

    ev = collecter(60)
    cat = Counter(e["categorie_confirmee"] or e["categorie_probable"] for e in ev)
    confirmes = [e for e in ev if e["categorie_confirmee"]]
    xray = [x for x in (centre.etat_xray(r["id"]) for r in historique.lister(30)) if x["statut"] in ("Pending", "Partial")]
    recur = Counter(e["nom"] for e in ev)
    return {"kpi": {"total": len(ev), "nouveaux": sum(not e["recurrent"] for e in ev), "recurrents": sum(e["recurrent"] for e in ev),
                    "a_analyser": sum(e["statut"] in ("New", "Diagnosis Proposed", "Human Review") for e in ev),
                    "defauts_applicatifs": sum(e["categorie_confirmee"] == "Application Defect" for e in ev),
                    "automatisation": sum((e["categorie_confirmee"] or e["categorie_probable"]) in ("Automation Defect", "Locator Issue", "Timing Issue") for e in ev),
                    "environnement": sum((e["categorie_confirmee"] or e["categorie_probable"]) in ("Environment Issue", "Network Issue", "Framework Issue") for e in ev),
                    "donnees": sum((e["categorie_confirmee"] or e["categorie_probable"]) == "Test Data Issue" for e in ev),
                    "inconnus": cat.get("Unknown", 0), "resolus": sum(e["statut"] in ("Fixed", "Closed") for e in ev),
                    "taux_confirmation": round(100 * len(confirmes) / len(ev), 1) if ev else None,
                    "synchro_xray_en_attente": len(xray)},
            "par_categorie": dict(cat), "par_plateforme": dict(Counter(e["plateforme"] for e in ev)),
            "par_jour": dict(sorted(Counter(e["date"][:10] for e in ev).items())), "top_recurrents": recur.most_common(8),
            "derniers": ev[:10], "xray_hors_echecs": xray,
            "note": "Les erreurs de synchronisation Xray sont listées à part : elles ne sont jamais comptées comme échecs de test."}


# =========================================================================== corrections proposées (avant / après)
def _corrections() -> dict:
    f = _dossier() / "corrections.json"
    return json.loads(f.read_text("utf-8")) if f.exists() else {}


def _sauver_corrections(c: dict):
    _ecrire_atomique(_dossier() / "corrections.json", json.dumps(c, ensure_ascii=False, indent=1))


def proposer_correction_locator(eid: str, nouvelle_valeur: str, justification: str = "") -> dict:
    """Proposition (jamais appliquée ici) : remplace la valeur du locator fautif dans sa ressource, diff à l'appui."""
    import difflib

    from atelier.execution.depot_robot import lire_depot

    i = investigation(eid)
    actuel = (i.get("etape_fautive") or {}).get("locator", "")
    if not actuel:
        raise ValueError("Aucun locator identifié sur l'étape en échec.")
    nouvelle_valeur = nouvelle_valeur.strip()
    if not nouvelle_valeur or nouvelle_valeur == actuel or "\n" in nouvelle_valeur:
        raise ValueError("Nouvelle valeur de locator invalide.")
    loc = next((l for l in lire_depot()["locators"].values() if l["valeur"] == actuel), None)
    if not loc:
        raise KeyError(f"Locator {actuel} introuvable dans les ressources du dépôt.")
    avant = projet.safe_path(loc["fichier"]).read_text("utf-8")
    motif = re.compile(rf"(\b{re.escape(loc['cle'])}=){re.escape(actuel)}(?=\s{{2,}}|\t|$)", re.M)
    if len(motif.findall(avant)) != 1:
        raise ValueError("Définition du locator ambiguë ou introuvable : correction manuelle dans le Code Editor.")
    apres = motif.sub(lambda m: m.group(1) + nouvelle_valeur, avant)
    cid = f"COR-{hashlib.sha1((eid + nouvelle_valeur).encode()).hexdigest()[:8].upper()}"
    c = {"id": cid, "echec": eid, "type": "locator", "fichier": loc["fichier"], "cle": f"{loc['ecran']}.{loc['cle']}@{loc['plateforme']}",
         "avant_valeur": actuel, "apres_valeur": nouvelle_valeur, "justification": justification.strip(), "statut": "Proposed",
         "diff": "\n".join(difflib.unified_diff(avant.splitlines(), apres.splitlines(), loc["fichier"], loc["fichier"] + " (proposé)", lineterm="")),
         "contenu_base": avant, "contenu_propose": apres, "impactes": i["impactes"], "historique": [{"date": _maintenant(), "par": _auteur(), "statut": "Proposed"}]}
    cs = _corrections()
    cs[cid] = c
    _sauver_corrections(cs)
    _journaliser("correction_proposee", echec=eid, correction=cid)
    return c


def corrections() -> list[dict]:
    return sorted(_corrections().values(), key=lambda c: c["historique"][0]["date"], reverse=True)


def faire_avancer_correction(cid: str, action: str, commentaire: str = "") -> dict:
    """soumettre → Under Review, approuver → Approved, appliquer → Applied (écrit via l'éditeur, historisé),
    valider → Validated (retest réussi exigé), rejeter → Rejected (justifié)."""
    from atelier.generation import editeur

    cs = _corrections()
    c = cs.get(cid)
    if not c:
        raise KeyError(f"Correction inconnue : {cid}")
    regles = {"soumettre": ("Proposed", "Under Review"), "approuver": ("Under Review", "Approved"), "appliquer": ("Approved", "Applied"),
              "valider": ("Applied", "Validated")}
    if action == "rejeter":
        if not commentaire.strip():
            raise ValueError("Un rejet doit être justifié.")
        if c["statut"] in ("Applied", "Validated"):
            raise ValueError("Correction déjà appliquée : revenir en arrière par le Code Editor (historique).")
        vers = "Rejected"
    elif action in regles:
        depuis, vers = regles[action]
        if c["statut"] != depuis:
            raise ValueError(f"« {action} » impossible depuis {c['statut']}.")
    else:
        raise ValueError("Action : soumettre, approuver, appliquer, valider ou rejeter.")
    if action == "appliquer":  # contrôle de concurrence : le fichier ne doit pas avoir changé depuis la proposition
        editeur.enregistrer(c["fichier"], c["contenu_propose"], version_lue=c["contenu_base"])
        _maj(c["echec"], "correction_appliquee", statut="Fix In Progress")
    if action == "valider" and not any(r.get("resultat") == "PASS" for r in resultats_retests(c["echec"])):
        raise ValueError("Validation impossible sans retest réussi après application.")
    c["statut"] = vers
    c["historique"].append({"date": _maintenant(), "par": _auteur(), "statut": vers, "commentaire": commentaire.strip()})
    _sauver_corrections(cs)
    _journaliser(f"correction_{action}", correction=cid)
    return c



# =========================================================================== anomalies Jira (création encadrée)
def doublons_jira(eid: str, projet: str, jira=None) -> list[dict]:
    """Anomalies ouvertes probablement identiques, à examiner AVANT toute création (même test ou même message)."""
    from atelier.integrations.jira import JiraClient

    from atelier.domain import projets

    projet = projet or projets.cle_jira()
    if not projet:
        raise ValueError("Projet Jira requis (aucun projet actif avec une clé Jira).")
    jira = jira or JiraClient()
    e = _evenement(eid)
    mots = " ".join(re.findall(r"[A-Za-zÀ-ÿ]{5,}", nettoyer(e["message"]))[:6]).replace('"', "")
    clauses = [f'text ~ "{mots}"'] if mots else []
    if e["cle_xray"]:
        clauses.append(f'issue in linkedIssues("{e["cle_xray"]}")')
    if not clauses:
        return []
    type_bug = os.environ.get("JIRA_TYPE_ANOMALIE", "Bug")
    jql = f'project = "{projet}" AND issuetype = "{type_bug}" AND statusCategory != Done AND ({" OR ".join(clauses)})'
    return [{"cle": i["key"], "resume": (i.get("fields") or {}).get("summary", ""), "statut": ((i.get("fields") or {}).get("status") or {}).get("name", "")}
            for i in jira.rechercher(jql, ["summary", "status"], 20)]


def creer_anomalie_jira(eid: str, projet: str, resume: str = "", description: str = "", lier_test: bool = True, jira=None) -> dict:
    """Crée l'anomalie à partir du brouillon (modifiable), joint les captures, lie le test Xray, associe l'échec.
    Appelée uniquement sur action explicite de l'utilisateur, après consultation des doublons."""
    from atelier.integrations.jira import JiraClient

    from atelier.domain import projets

    projet = projet or projets.cle_jira()
    if not projet:
        raise ValueError("Projet Jira requis (aucun projet actif avec une clé Jira).")
    jira = jira or JiraClient()
    i = investigation(eid)
    b = i["brouillon_jira"]
    texte = description.strip() or "\n".join([f"Étapes : " + " ; ".join(b["steps"]), f"Résultat attendu : {b['expected']}",
                                                f"Résultat obtenu : {b['actual']}", f"Environnement : {b['environment']}",
                                                f"Version : {b['version']}", f"Test Xray : {b['xray']} · exécution {b['execution']}"])
    cle = jira.creer_ticket(projet, (resume or b["summary"])[:250], texte, os.environ.get("JIRA_TYPE_ANOMALIE", "Bug"))
    jointes, erreurs = [], []
    for c in b["evidence"]:
        try:
            jira.joindre(cle, str(projet_dir() / c))
            jointes.append(c.rsplit("/", 1)[-1])
        except Exception as ex:  # noqa: BLE001 - l'anomalie existe : on signale sans l'annuler
            erreurs.append(str(ex)[:200])
    if lier_test and b["xray"]:
        try:
            jira.link(cle, b["xray"], os.environ.get("JIRA_LIEN_ANOMALIE", "Relates"))
        except Exception as ex:  # noqa: BLE001
            erreurs.append(f"lien : {str(ex)[:200]}")
    associer_jira(eid, cle)
    _journaliser("anomalie_jira_creee", echec=eid, cle=cle)
    return {"cle": cle, "pieces_jointes": jointes, "erreurs": erreurs}


def projet_dir():
    return projet.PROJECT_DIR
