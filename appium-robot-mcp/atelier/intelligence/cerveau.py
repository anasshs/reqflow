"""Cerveau de l'application : ce que l'atelier sait de l'application sélectionnée, d'où il le sait, depuis quand,
ce qu'il ignore encore, et quoi faire ensuite. Point d'entrée unique pour l'automaticien (Application Intelligence)
et pour l'agent (outils MCP cerveau_application / cerveau_question).

Tout vient des sources réelles déjà présentes (Knowledge Graph, carte, Jira / Xray, dépôt Robot, exécutions,
sessions de l'agent) : rien n'est estimé ; chaque indicateur affiche son mode de calcul. Le cerveau est propre à
chaque application : il suit l'application active (header), sa JQL et sa carte.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from atelier.domain import projet

FRAIS_JOURS = 7


def _date(d) -> datetime | None:
    if not d:
        return None
    try:
        x = datetime.fromisoformat(str(d)[:19])
        return x
    except ValueError:
        return None


def _age_jours(d) -> int | None:
    x = _date(d)
    return None if x is None else max(0, (datetime.now() - x).days)


def _fraicheur(d) -> str:
    a = _age_jours(d)
    return "jamais" if a is None else "à jour" if a <= FRAIS_JOURS else "ancienne"


# =========================================================================== sources de connaissance
def sources() -> list[dict]:
    """Chaque source qui alimente le cerveau : date de la dernière mise à jour, volume, fraîcheur, où la mettre à jour."""
    from atelier.discovery import intelligence_app
    from atelier.execution import historique
    from atelier.generation import sessions_agent
    from atelier.intelligence import couverture_exigences, patrimoine_xray

    app, ecrans, _ = intelligence_app._ecrans_carte()
    vus = [p.get("vu_le", "") for e in ecrans for p in (e.get("plateformes") or {}).values() if isinstance(p, dict) and p.get("vu_le")]
    pat = patrimoine_xray.charger() or {}
    ex = couverture_exigences._lire_json(couverture_exigences._fichier("exigences.json"), {})
    fichiers = [f for motif in ("**/*.robot", "**/*.resource") for f in projet.PROJECT_DIR.glob(motif)
                if "results" not in f.parts and ".git" not in f.parts] if projet.PROJECT_DIR.exists() else []
    depot = max((f.stat().st_mtime for f in fichiers), default=None)
    runs = historique.lister(1)
    sess = sessions_agent.lister(1)
    l = [
        {"id": "carte", "nom": "Carte de l'application (écrans observés)", "date": max(vus) if vus else None, "volume": f"{len(ecrans)} écran(s)",
         "role": "ce qui existe vraiment à l'écran", "action": "#discovery", "action_lib": "Explorer (Discovery)"},
        {"id": "exigences", "nom": "Exigences Jira (périmètre de couverture)", "date": ex.get("date"),
         "volume": f"{sum(1 for e in (ex.get('exigences') or {}).values() if not e.get('hors_perimetre'))} exigence(s)",
         "role": "ce qui est demandé", "action": "#strategie/couverture", "action_lib": "Importer les exigences"},
        {"id": "tests", "nom": "Tests Xray de l'application", "date": pat.get("date"), "volume": f"{len(pat.get('tests') or [])} test(s)",
         "role": "comment on vérifie", "action": "#parametres/configuration", "action_lib": "Synchroniser les tests"},
        {"id": "executions", "nom": "Exécutions Xray (Test Executions)", "date": (pat.get("executions_xray") or {}).get("date"),
         "volume": f"{len(pat.get('executions') or [])} exécution(s)", "role": "ce qui marche aujourd'hui", "action": "#centre/vue", "action_lib": "Actualiser depuis Xray"},
        {"id": "depot", "nom": "Dépôt Robot (scripts, socle, locators)", "date": datetime.fromtimestamp(depot).isoformat(timespec="seconds") if depot else None,
         "volume": f"{len(fichiers)} fichier(s)", "role": "ce qui est automatisé", "action": "#studio", "action_lib": "Automation Studio"},
        {"id": "runs", "nom": "Runs de l'atelier", "date": runs[0]["debut"] if runs else None, "volume": "", "role": "derniers résultats Robot",
         "action": "#centre/historique", "action_lib": "Historique"},
        {"id": "cursor", "nom": "Sessions de Cursor", "date": sess[0]["fin"] if sess else None, "volume": f"{sess[0]['appels']} appel(s) (dernière)" if sess else "",
         "role": "ce que l'agent a fait", "action": "#studio/direct", "action_lib": "Avec Cursor"},
    ]
    for x in l:
        x["fraicheur"], x["age_jours"] = _fraicheur(x["date"]), _age_jours(x["date"])
    return l


# =========================================================================== modules
def _pct(n, d):
    return round(100 * n / d) if d else None


def modules(g=None) -> list[dict]:
    """Par module du Knowledge Graph : connaissance (écrans, parcours, règles), couverture (exigences avec test),
    automatisation (tests Xray automatisés), stabilité (tests en échec), points d'attention."""
    from atelier.discovery import connaissance
    from atelier.intelligence import plan_test

    g = g or connaissance.construire()
    out = []
    for nid in sorted(i for i, n in g.noeuds.items() if n.type == "module"):
        try:
            p = plan_test.plan(nid, g)
        except Exception:  # noqa: BLE001 — un module illisible n'empêche pas les autres
            continue
        r = p["resume"]
        ex = [e for e in p["exigences"] if e["type"] != "epic"]
        tests = {t["cle"]: t for e in p["exigences"] for t in e["tests"]}
        auto = sum(1 for t in tests.values() if t["automatise"])
        fragiles = sum(1 for e in p["ecrans"] if e["locators_fragiles"])
        out.append({"id": nid, "module": p["module"], "ecrans": r["ecrans"], "parcours": r["parcours"], "regles": r["regles"],
                    "exigences": len(ex), "exigences_couvertes": sum(1 for e in ex if e["tests"]), "couverture": _pct(sum(1 for e in ex if e["tests"]), len(ex)),
                    "tests": len(tests), "tests_automatises": auto, "automatisation": _pct(auto, len(tests)),
                    "echecs": p["echecs"], "ecrans_fragiles": fragiles, "actions_sensibles": r["actions_sensibles"],
                    "connu": bool(r["ecrans"]) or bool(r["parcours"]), "pistes": p["pistes"]})
    return out


# =========================================================================== lacunes et prochaines actions
def lacunes(srcs: list[dict], mods: list[dict], a_valider: int) -> list[dict]:
    """Ce que le cerveau ne sait pas (ou plus) et l'action qui le comble, du plus important au moins important."""
    out = []
    for s in srcs:
        if s["id"] in ("carte", "exigences", "tests") and s["fraicheur"] != "à jour":
            out.append({"priorite": 1 if s["fraicheur"] == "jamais" else 2, "sujet": s["nom"],
                        "texte": "jamais alimentée" if s["fraicheur"] == "jamais" else f"dernière mise à jour il y a {s['age_jours']} jours",
                        "action": s["action"], "action_lib": s["action_lib"]})
    for m in mods:
        if not m["connu"] and (m["exigences"] or m["tests"]):
            out.append({"priorite": 1, "sujet": f"Module {m['module']}", "texte": "exigences ou tests connus, mais aucun écran ni parcours : l'application n'a pas été explorée ici",
                        "action": "#discovery", "action_lib": "Explorer ce module"})
        if m["exigences"] and (m["couverture"] or 0) < 50:
            out.append({"priorite": 2, "sujet": f"Module {m['module']}", "texte": f"couverture des exigences {m['couverture'] or 0} % ({m['exigences_couvertes']}/{m['exigences']})",
                        "action": "#strategie/couverture", "action_lib": "Voir la couverture"})
        if m["echecs"]:
            out.append({"priorite": 1, "sujet": f"Module {m['module']}", "texte": f"{len(m['echecs'])} test(s) en échec : {', '.join(m['echecs'][:5])}",
                        "action": "#echecs", "action_lib": "Analyser les échecs"})
        if m["tests"] and (m["automatisation"] or 0) < 50:
            out.append({"priorite": 3, "sujet": f"Module {m['module']}", "texte": f"automatisation {m['automatisation'] or 0} % ({m['tests_automatises']}/{m['tests']})",
                        "action": "#studio/candidats", "action_lib": "Candidats à automatiser"})
        if m["ecrans_fragiles"]:
            out.append({"priorite": 3, "sujet": f"Module {m['module']}", "texte": f"locators fragiles sur {m['ecrans_fragiles']} écran(s)",
                        "action": "#studio/locators", "action_lib": "Corriger les locators"})
    if a_valider:
        out.append({"priorite": 2, "sujet": "Connaissances à valider", "texte": f"{a_valider} proposition(s) (Discovery, Cursor, graphe, Coverage Intelligence) attendent une décision",
                    "action": "#intelligence/a_valider", "action_lib": "Valider"})
    return sorted(out, key=lambda x: x["priorite"])


# =========================================================================== journal d'apprentissage
def apprentissages(limite: int = 40) -> list[dict]:
    """Ce que le cerveau a appris récemment, toutes sources confondues, du plus récent au plus ancien."""
    from atelier.domain import declarations
    from atelier.generation import sessions_agent, studio
    from atelier.intelligence import couverture_exigences

    l = []
    for h in declarations.historique(limite=limite):
        l.append({"date": h["date"], "source": "Knowledge Graph", "texte": f"{h['op'].replace('_', ' ')} · {h.get('cible') or ''}", "auteur": h.get("auteur", "")})
    for j in studio.journal(limite):
        if j["op"] in ("correction_locator", "factorisation_keywords", "revue_script", "generation_cursor", "generation_bdd", "generation_builder"):
            l.append({"date": j["date"], "source": "Automation Studio", "texte": f"{j['op'].replace('_', ' ')} · {j.get('fichier') or j.get('locator') or j.get('nom') or ''}"
                      + (f" ({j['de']} → {j['vers']})" if j.get("de") and j.get("vers") else ""), "auteur": j.get("auteur", "")})
    for s in couverture_exigences.evolution()["synchros"][:10]:
        l.append({"date": s["date"], "source": "Jira (exigences)", "texte": f"{s['exigences']} exigence(s) · +{len(s['ajoutees'])} · sorties {len(s['sorties_du_perimetre'])}", "auteur": ""})
    for s in sessions_agent.lister(10):
        l.append({"date": s["fin"], "source": "Cursor", "texte": f"session de {s['appels']} appel(s)" + (f", a écrit {', '.join(s['ecrits'])}" if s["ecrits"] else ""), "auteur": "cursor"})

    def cle(x):
        d = _date(x["date"])
        return d.replace(tzinfo=None) if d else datetime.min
    return sorted(l, key=cle, reverse=True)[:limite]


# =========================================================================== vue d'ensemble
def vue() -> dict:
    from atelier.discovery import carte, connaissance, intelligence_app

    g = connaissance.construire()
    srcs = sources()
    mods = modules(g)
    try:
        a_valider_n = len(a_valider())
    except Exception:  # noqa: BLE001 — une source illisible ne bloque pas le cerveau
        a_valider_n = sum(1 for n in g.noeuds.values() if n.statut == "à valider")
    app, _, _ = intelligence_app._ecrans_carte()
    slug = carte.app_courante() if carte.app_courante() else ""
    connues = sum(1 for s in srcs if s["fraicheur"] != "jamais")
    lac = lacunes(srcs, mods, a_valider_n)
    try:  # documentation Jira (Coverage Intelligence) : anomalies hautes signalées au cerveau
        from atelier.intelligence import intelligence_couverture

        doc = intelligence_couverture.qualite_documentaire()
        hautes = sum(1 for x in doc if x["criticite"] == "haute")
        if hautes:
            lac.insert(0, {"priorite": 1, "sujet": "Documentation Jira", "texte": f"{len(doc)} anomalie(s), dont {hautes} haute(s) (Stories sans description ou critères, Epics vides…)",
                           "action": "#strategie/coverage", "action_lib": "Coverage Intelligence"})
    except Exception:  # noqa: BLE001
        pass
    return {"application": {"slug": slug, "nom": app.get("nom") or slug, "plateformes": app.get("plateformes", []), "build": app.get("build", "")},
            "maturite": {"sources_alimentees": connues, "sources": len(srcs), "modules": len(mods), "modules_connus": sum(m["connu"] for m in mods),
                         "a_valider": a_valider_n,
                         "definition": "Sources alimentées : sources avec au moins une mise à jour ; module connu : au moins un écran ou un parcours dans la carte."},
            "sources": srcs, "modules": mods, "lacunes": lac, "apprentissages": apprentissages(),
            "ia": _ia_etat()}


def _ia_etat() -> dict:
    from atelier.intelligence import fournisseur_ia

    try:
        return fournisseur_ia.etat()
    except Exception:  # noqa: BLE001
        return {"fournisseur": "aucun", "appel_direct": False}


# =========================================================================== questions au cerveau
MOTS_VIDES = {"le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "à", "a", "au", "aux", "en", "est", "sont", "que", "qui", "quoi",
              "quel", "quelle", "quels", "quelles", "pour", "sur", "dans", "avec", "il", "y", "ce", "cette", "ces", "mon", "ma", "mes", "on", "pas", "ne"}


def _mots(texte: str) -> set:
    return {m for m in re.findall(r"[a-zà-ÿ0-9_]{3,}", (texte or "").lower()) if m not in MOTS_VIDES}


def demander(question: str) -> dict:
    """Réponse fondée uniquement sur ce que le cerveau sait : faits pertinents (graphe, modules, lacunes) ; avec une IA
    configurée, réponse rédigée à partir de ces seuls faits, avec les éléments cités. Sans IA : les faits trouvés."""
    from atelier.discovery import connaissance
    from atelier.intelligence import plan_test

    q = (question or "").strip()
    if len(q) < 3:
        raise ValueError("Poser une question (ex. « Qu'est-ce qui n'est pas testé dans les virements ? »).")
    g = connaissance.construire()
    mots = _mots(q)
    mods = modules(g)
    cibles = [m for m in mods if _mots(m["module"]) & mots] or []
    faits = []
    for n in g.noeuds.values():
        score = len(_mots(f"{n.libelle} {n.proprietes.get('resume', '')} {n.proprietes.get('description', '')}") & mots)
        if score:
            faits.append((score, {"id": n.id, "type": n.type, "libelle": n.libelle, "statut": n.statut, "source": n.source}))
    faits = [f for _, f in sorted(faits, key=lambda x: -x[0])[:25]]
    contexte = {"modules": [{k: m[k] for k in ("module", "ecrans", "parcours", "exigences", "couverture", "tests", "automatisation", "echecs")} for m in mods],
                "lacunes": lacunes(sources(), mods, 0)[:10], "elements": faits,
                "detail_modules": [plan_test.plan(m["id"], g) for m in cibles[:2]]}
    ia = _ia_etat()
    if ia.get("appel_direct"):
        from atelier.intelligence import fournisseur_ia

        try:
            texte = fournisseur_ia.completer(
                "Tu es le cerveau d'une application testée (QA). Réponds en français, brièvement, UNIQUEMENT avec les faits fournis ; "
                "cite les éléments (identifiants, clés Jira / Xray, écrans) ; si les faits ne suffisent pas, dis ce qu'il faut explorer ou importer.",
                f"Question : {q}\n\nFaits (JSON) :\n{json.dumps(contexte, ensure_ascii=False, default=str)[:12000]}", 900)
            return {"mode": "ia", "reponse": texte, "elements": faits, "modules": [m["module"] for m in cibles]}
        except Exception as e:  # noqa: BLE001 — IA indisponible : les faits restent utiles
            return {"mode": "recherche", "reponse": f"IA indisponible ({e}) : voici les faits trouvés.", "elements": faits, "modules": [m["module"] for m in cibles],
                    "detail": contexte["detail_modules"]}
    if not faits and not cibles:
        return {"mode": "recherche", "reponse": "Le cerveau ne sait rien sur ce sujet : explorer l'application (Discovery) ou importer les exigences et tests.",
                "elements": [], "modules": []}
    resume = []
    for d in contexte["detail_modules"]:
        resume.append(f"Module {d['module']} : {d['resume']['ecrans']} écran(s), {d['resume']['exigences']} exigence(s), "
                      f"{d['resume']['us_sans_test']} US sans test, {d['resume']['tests_a_automatiser']} test(s) à automatiser, {len(d['echecs'])} en échec.")
        resume += d["pistes"][:3]
    return {"mode": "recherche", "reponse": " ".join(resume) or f"{len(faits)} élément(s) liés à la question.", "elements": faits,
            "modules": [m["module"] for m in cibles], "detail": contexte["detail_modules"]}


# =========================================================================== une seule boîte « À valider »
def a_valider() -> list[dict]:
    """Toutes les propositions en attente d'une décision humaine, d'où qu'elles viennent, sans doublon :
    Discovery / agent (déclarations et noms d'écrans), relations déduites du graphe, Coverage Intelligence
    (Stories, critères, liens exigence ↔ test, classements de tests orphelins). Chaque élément dit comment décider."""
    from atelier.discovery import apprentissage, intelligence_app
    from atelier.domain import demandes
    from atelier.intelligence import intelligence_couverture

    out, vus = [], set()
    for d in demandes.lister("en attente"):  # actions demandées par Cursor : rien n'est fait avant acceptation
        out.append({"source": "Cursor (action)", "decision": "action", "id": d["id"], "type": d["libelle_type"], "libelle": d["resume"],
                    "detail": ", ".join(f"{k} {v}" for k, v in (d.get("apercu") or {}).items())[:240] or f"demandé le {d['cree_le'][:16].replace('T', ' ')}",
                    "confiance": None})
    for p in apprentissage.propositions():
        vus.add(p["id"])
        src = str(p.get("source") or "")
        origine = src.split(" (MCP)")[0] if " (MCP)" in src else "Cursor" if "cursor" in src.lower() else "Jira (règles extraites)" if src.startswith("jira:") or src == "déduit" else "Discovery"
        out.append({"source": origine, "decision": "discovery", "id": p["id"], "type": p.get("type", ""), "libelle": p.get("libelle", ""),
                    "detail": p.get("source") or "", "confiance": None})
    for v in intelligence_app.validation():
        if v["id"] not in vus:
            out.append({"source": "Knowledge Graph (déduit)", "decision": "graphe", "id": v["id"], "type": v["type"], "libelle": v["libelle"],
                        "detail": v.get("source") or "", "confiance": v.get("confiance")})
    L = {"user_story": "Story reconstruite", "criteres": "critères d'acceptation", "lien_test": "lien exigence ↔ test", "classement_orphelin": "classement de test orphelin"}
    for p in intelligence_couverture.propositions(statut="proposee"):
        c = p["contenu"]
        out.append({"source": "Coverage Intelligence", "decision": "ci", "id": p["id"], "type": L.get(p["type"], p["type"]),
                    "libelle": c.get("titre") or f"{c.get('exigence', '')} ↔ {c.get('test', '')}" if p["type"] == "lien_test" else c.get("titre") or c.get("test", ""),
                    "detail": " · ".join(p.get("justification") or [])[:240], "confiance": p.get("score")})
    return out
