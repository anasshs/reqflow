"""Test Design avancé (V2, phase 4) : propositions de cas par CATÉGORIE et détection des DOUBLONS.

Catégories : nominal, alternatif, négatif, limites, validation des champs, gestion des erreurs, navigation,
permissions, règles métier. Chaque proposition dit sa source (critère, règle, écran, champ, transition), sa
justification, sa confiance, ce qui manque, et si elle repose sur un fait OBSERVÉ ou une hypothèse DÉDUITE.
Les propositions sont des cas « Proposé » de Test Design › À concevoir : l'automaticien les complète, valide ou
rejette ; rien n'est publié dans Xray sans validation.

Doublons : avant de proposer, chaque cas est comparé aux tests Xray existants (instantané) et aux autres cas de l'US
sur quatre facettes — titre, étapes (actions), préconditions, résultats attendus — et sur le texte complet
(moyenne recouvrement / Jaccard des mots significatifs ; score = le plus fort des deux), puis reçoit une recommandation :
réutiliser (≥ 0,70), faire évoluer (≥ 0,40) ou créer. Similarité : mots significatifs communs (moteur de Coverage
Intelligence, aucun second moteur).
"""
from __future__ import annotations

import re

CATEGORIES = {
    "nominal": "Cas nominal", "alternatif": "Cas alternatif", "negatif": "Cas négatif", "limites": "Cas limites",
    "champs": "Validation des champs", "erreurs": "Gestion des erreurs", "navigation": "Navigation",
    "permissions": "Permissions", "regles": "Règles métier",
}
POIDS = {"titre": 0.30, "etapes": 0.35, "resultats": 0.25, "preconditions": 0.10}
SEUIL_REUTILISER, SEUIL_EVOLUER = 0.70, 0.40
NEGATION = re.compile(r"\b(refus|rejet|interdit|invalide|erron|erreur|impossible|bloqu|ne\s+\w+\s+pas|n'est pas|incorrect|échec|echec)", re.I)
ALTERNATIF = re.compile(r"\b(sinon|ou bien|si |lorsque|selon|au choix|à défaut|dans le cas)", re.I)
NOMBRE = re.compile(r"(\d+(?:[ .,]\d{3})*(?:,\d+)?)\s*(€|euros?|caract\w*|chiffres?|jours?|échecs?|echecs?|tentatives?|%|minutes?|secondes?|ans?|mois)", re.I)
PERMISSION = re.compile(r"\b(rôle|role|droit|profil|habilit|autoris|administrateur|conseiller|client)", re.I)


def _cas(cat: str, titre: str, etapes: list[dict], gherkin: str, source: str, justification: str, confiance: float,
         provenance: str, manquant: list[str] | None = None) -> dict:
    return {"categorie": cat, "titre": titre[:250], "etapes": etapes, "gherkin": gherkin, "source_detail": source,
            "justification": justification, "confiance": round(confiance, 2), "provenance": provenance, "manquant": manquant or []}


def _e(action: str, resultat: str = "", donnees: str = "") -> dict:
    return {"action": action, "donnees": donnees, "resultat": resultat}


# =========================================================================== contexte d'une US (graphe)
def contexte(cle: str, g=None) -> dict:
    """Règles, écrans, champs, messages, transitions et rôles liés à une US dans le Knowledge Graph."""
    if g is None:
        from atelier.discovery import connaissance

        g = connaissance.construire()
    N, us = g.noeuds, f"user_story:{cle}"
    out = {"regles": [], "ecrans": [], "champs": [], "messages": [], "transitions": [], "roles": []}
    if us not in N:
        return out

    def sortants(i, t=None):
        return [r.vers for r in g.sortants(i) if r.vers in N and (t is None or r.type == t)]

    out["regles"] = [{"id": r, "libelle": N[r].libelle, "description": N[r].proprietes.get("description", "")} for r in sortants(us, "contient") if N[r].type == "regle"]
    parents = [r.de for r in g.entrants(us) if r.type == "contient" and r.de in N and N[r.de].type in ("fonctionnalite", "module")]
    ecrans = sorted({e for p in parents for e in sortants(p, "contient") if N[e].type == "ecran"})
    for e in ecrans:
        out["ecrans"].append(N[e].libelle)
        for loc in sortants(e, "contient"):
            n = N[loc]
            if n.type != "locator":
                continue
            cle_ = n.libelle
            if cle_.startswith(("champ", "input", "saisie")) or n.proprietes.get("classe_action") == "controlled":
                out["champs"].append({"ecran": N[e].libelle, "cle": cle_})
            elif re.search(r"message|erreur|alerte", cle_, re.I):
                out["messages"].append({"ecran": N[e].libelle, "cle": cle_})
        out["transitions"] += [{"de": N[e].libelle, "vers": N[v].libelle} for v in sortants(e, "navigue_vers") if N[v].type == "ecran"]
    out["roles"] = sorted({N[r].libelle for p in parents for r in sortants(p, "contient") if N[r].type == "role"})
    out["champs"] = list({(c["ecran"], c["cle"]): c for c in out["champs"]}.values())
    out["messages"] = list({(c["ecran"], c["cle"]): c for c in out["messages"]}.values())
    return out


# =========================================================================== propositions par catégorie
def propositions(u: dict, ctx: dict, categories: list[str] | None = None) -> list[dict]:
    """Cas proposés pour une US (dict de Test Design) et son contexte de graphe ; aucune écriture."""
    from atelier.discovery.intelligence_app import structurer
    from atelier.intelligence import testabilite_us

    cats = [c for c in (categories or CATEGORIES) if c in CATEGORIES]
    crit = testabilite_us._criteres(u)
    texte = testabilite_us._texte(u)
    titre = u.get("resume") or u.get("cle", "")
    out: list[dict] = []

    def gh(cond, action, res):
        return f"Given {cond or 'le contexte de l’US est en place'}\nWhen {action}\nThen {res or 'le résultat attendu (à préciser)'}"

    for n, c in enumerate(crit, 1):
        s = structurer(c)
        neg = bool(NEGATION.search(c))
        cat = "negatif" if neg else "alternatif" if ALTERNATIF.search(c) and n > 1 else "nominal"
        if cat in cats:
            etapes = ([_e(f"Prérequis : {s['condition']}")] if s["condition"] else []) + [_e(s["action"] or c, s["resultat"] or "à préciser")]
            resume_c = " → ".join(x for x in (s["condition"], s["action"] if s["condition"] else c, s["resultat"]) if x)[:150]
            out.append(_cas(cat, f"{titre} — {CATEGORIES[cat].lower()} : {resume_c}", etapes, gh(s["condition"], s["action"] or c, s["resultat"]),
                            f"critère d'acceptation {n}", f"Critère : « {c[:160]} »", 0.8 if s["resultat"] else 0.6, "observé",
                            [] if s["resultat"] else ["résultat attendu à préciser"]))
        for valeur, unite in NOMBRE.findall(c):
            if "limites" in cats:
                v = valeur.replace(" ", "").replace(".", "").replace(",", ".")
                out.append(_cas("limites", f"{titre} — limite {valeur} {unite}", [
                    _e(f"Tester juste en dessous de {valeur} {unite}", "accepté (à confirmer)"),
                    _e(f"Tester exactement {valeur} {unite}", "comportement à la borne (à confirmer)"),
                    _e(f"Tester juste au-dessus de {valeur} {unite}", "refusé (à confirmer)")],
                    gh("le contexte de l’US est en place", f"la valeur vaut {v} {unite} (puis juste en dessous / au-dessus)", "le comportement à la borne est respecté"),
                    f"critère d'acceptation {n}", f"Valeur limite lue dans le critère : « {valeur} {unite} »", 0.7, "observé",
                    ["sens de la borne (incluse ou exclue)"]))
    if "nominal" in cats and not any(x["categorie"] == "nominal" for x in out):
        out.append(_cas("nominal", f"{titre} — cas nominal", [_e("Réaliser le parcours principal de l'US", "à préciser")], gh("", "le parcours principal est réalisé", ""),
                        "résumé de l'US", "Aucun critère positif exploitable : cas nominal à compléter.", 0.4, "déduit", ["étapes", "résultat attendu"]))
    if "negatif" in cats and not any(x["categorie"] == "negatif" for x in out):
        out.append(_cas("negatif", f"{titre} — donnée invalide", [_e("Reproduire le parcours avec une donnée invalide", "refus explicite (à confirmer)")],
                        gh("", "la donnée saisie est invalide", "l'opération est refusée"), "résumé de l'US",
                        "Aucun cas d'erreur décrit dans l'US : cas négatif déduit.", 0.4, "déduit", ["donnée invalide précise", "message attendu"]))
    for r in ctx.get("regles") or []:
        if "regles" in cats:
            out.append(_cas("regles", f"{titre} — règle « {r['libelle'][:120]} »", [_e(f"Vérifier la règle : {r['libelle']}", r.get("description") or "règle respectée")],
                            gh("", f"la règle « {r['libelle'][:80]} » s'applique", "la règle est respectée"), f"règle {r['id']}",
                            "Règle métier liée à l'US dans le Knowledge Graph.", 0.75, "observé"))
        for valeur, unite in NOMBRE.findall(f"{r['libelle']} {r.get('description', '')}"):
            if "limites" in cats and not any(valeur in x["titre"] for x in out if x["categorie"] == "limites"):
                out.append(_cas("limites", f"{titre} — limite {valeur} {unite}", [_e(f"Tester autour de {valeur} {unite} (en dessous, égal, au-dessus)", "à confirmer")],
                                gh("", f"la valeur est autour de {valeur} {unite}", "le comportement à la borne est respecté"), f"règle {r['id']}",
                                f"Valeur limite lue dans la règle « {r['libelle'][:80]} »", 0.65, "observé", ["sens de la borne"]))
    for ch in ctx.get("champs") or []:
        if "champs" in cats:
            out.append(_cas("champs", f"{titre} — validation du champ {ch['cle']}", [
                _e(f"Laisser {ch['cle']} vide ({ch['ecran']})", "champ obligatoire signalé (à confirmer)"),
                _e(f"Saisir un format invalide dans {ch['cle']}", "format refusé (à confirmer)")],
                gh(f"l'écran {ch['ecran']} est affiché", f"le champ {ch['cle']} est vide ou mal formé", "la saisie est refusée avec un message"),
                f"écran {ch['ecran']} · champ {ch['cle']}", "Champ observé sur un écran de la fonctionnalité (carte).", 0.55, "déduit",
                ["obligatoire ou non", "format attendu", "message d'erreur"]))
    for m in ctx.get("messages") or []:
        if "erreurs" in cats:
            out.append(_cas("erreurs", f"{titre} — message {m['cle']}", [_e(f"Provoquer l'erreur affichée par {m['cle']} ({m['ecran']})", "message d'erreur explicite affiché")],
                            gh(f"l'écran {m['ecran']} est affiché", "une erreur est provoquée", f"le message {m['cle']} est affiché"),
                            f"écran {m['ecran']} · élément {m['cle']}", "Zone de message d'erreur observée à l'écran.", 0.55, "déduit", ["cause de l'erreur", "texte attendu"]))
    for t in ctx.get("transitions") or []:
        if "navigation" in cats:
            out.append(_cas("navigation", f"{titre} — navigation {t['de']} → {t['vers']}", [_e(f"Depuis {t['de']}, aller vers {t['vers']}", f"l'écran {t['vers']} est affiché")],
                            gh(f"l'écran {t['de']} est affiché", f"l'utilisateur va vers {t['vers']}", f"l'écran {t['vers']} est affiché"),
                            f"transition {t['de']} → {t['vers']}", "Transition observée dans la carte de l'application.", 0.7, "observé"))
    if "permissions" in cats:
        roles = ctx.get("roles") or []
        if roles or PERMISSION.search(texte):
            for r in roles or ["profil non autorisé"]:
                out.append(_cas("permissions", f"{titre} — accès {r}", [_e(f"Se connecter avec le rôle « {r} » et tenter l'action", "accès conforme aux droits (à confirmer)")],
                                gh(f"l'utilisateur a le rôle {r}", "il tente l'action de l'US", "l'accès est conforme à ses droits"),
                                "rôles du graphe" if roles else "mention de droits dans l'US", "Droits mentionnés : un cas par rôle.",
                                0.6 if roles else 0.4, "observé" if roles else "déduit", [] if roles else ["liste des rôles et de leurs droits"]))
    return out


# =========================================================================== doublons
ETIQUETTES = re.compile(r"—\s*(cas \w+|validation du champ|validation des champs|gestion des erreurs|message|navigation|accès|permissions|"
                        r"règle|règles métier|limite)\b\s*:?", re.I)


def _recouvrement(a: str, b: str) -> float:
    """Moyenne du recouvrement (part des mots du texte le plus court présents dans l'autre) et de Jaccard : robuste
    quand un scénario court ressemble à un test Xray plus détaillé, sans s'emballer sur des mots génériques.
    Textes de moins de 4 mots significatifs : Jaccard seul."""
    from atelier.intelligence.intelligence_couverture import jetons, similarite

    ja, jb = set(jetons(a)), set(jetons(b))
    if min(len(ja), len(jb)) < 4:
        return similarite(a, b)
    return (len(ja & jb) / min(len(ja), len(jb)) + len(ja & jb) / len(ja | jb)) / 2


def _facettes(titre: str, etapes: list[dict], gherkin: str = "", preconditions: str = "") -> dict:
    titre = ETIQUETTES.sub(" ", titre or "")  # « — cas négatif : » n'est pas du contenu métier
    pre, act, res = [preconditions], [], []
    for e in etapes or []:
        a = str(e.get("action") or "")
        (pre if a.lower().startswith("prérequis") else act).append(a)
        res.append(str(e.get("resultat") or ""))
    for l in (gherkin or "").splitlines():
        m = re.match(r"\s*(Given|Étant donné|Etant donné|Soit|When|Quand|Lorsque|Then|Alors|And|Et)\b(.*)", l, re.I)
        if m:
            mot = m.group(1).lower()
            (pre if mot in ("given", "étant donné", "etant donné", "soit") else res if mot in ("then", "alors") else act).append(m.group(2))
    return {"titre": titre or "", "etapes": " ".join(act), "resultats": " ".join(res), "preconditions": " ".join(pre)}


def _score(a: dict, b: dict) -> tuple[float, dict]:
    """Score = le plus fort entre la moyenne pondérée des facettes présentes des deux côtés et la similarité du texte
    complet (une condition peut être une précondition d'un côté et une action de l'autre)."""
    from atelier.intelligence.intelligence_couverture import similarite

    f = {k: round(similarite(a[k], b[k]), 2) for k in POIDS if a[k].strip() and b[k].strip()}
    poids = sum(POIDS[k] for k in f) or 1
    f["texte complet"] = round(_recouvrement(" ".join(a.values()), " ".join(b.values())), 2)
    return round(max(sum(POIDS[k] * v for k, v in f.items() if k in POIDS) / poids, f["texte complet"]), 2), f


def recommandation(score: float) -> str:
    return "réutiliser" if score >= SEUIL_REUTILISER else "faire évoluer" if score >= SEUIL_EVOLUER else "créer"


def doublons(titre: str, etapes: list[dict] | None = None, gherkin: str = "", autres_cas: list[dict] | None = None, limite: int = 3) -> dict:
    """Tests Xray existants (et autres cas) les plus proches d'un scénario, avec les facettes comparées."""
    from atelier.intelligence import patrimoine_xray

    cible = _facettes(titre, etapes or [], gherkin)
    cands = []
    for t in (patrimoine_xray.charger_vue() or {}).get("tests") or []:
        pre = " ".join(str(p.get("resume") or p.get("definition") or p.get("cle") or "") if isinstance(p, dict) else str(p) for p in t.get("preconditions") or [])
        s, f = _score(cible, _facettes(t.get("resume", ""), t.get("etapes") or [], t.get("gherkin") or "", pre))
        cands.append({"type": "test Xray", "cle": t["cle"], "titre": t.get("resume", ""), "score": s, "facettes": f})
    for c in autres_cas or []:
        s, f = _score(cible, _facettes(c.get("titre", ""), c.get("etapes") or [], c.get("gherkin") or ""))
        cands.append({"type": "cas de l'US", "cle": c.get("cle_xray") or c.get("id", ""), "titre": c.get("titre", ""), "score": s, "facettes": f})
    cands = sorted(cands, key=lambda x: -x["score"])[:limite]
    meilleur = cands[0] if cands else None
    return {"recommandation": recommandation(meilleur["score"]) if meilleur else "créer", "meilleur": meilleur, "candidats": cands,
            "seuils": {"réutiliser": SEUIL_REUTILISER, "faire évoluer": SEUIL_EVOLUER}}


# =========================================================================== opérations sur une US de Test Design
def proposer(cle: str, categories: list[str] | None = None, g=None, origine: str = "atelier") -> dict:
    """Ajoute à l'US les cas proposés par catégorie, chacun annoté de sa recommandation de doublon. Un cas identique
    (même catégorie et même titre) déjà présent n'est pas ajouté deux fois."""
    from atelier.intelligence import testabilite_us as t

    d, u = t._exiger(cle)
    existants = {(c.get("categorie"), c["titre"]) for c in u.get("cas") or []}
    ajoutes = []
    for p in propositions(u, contexte(cle, g), categories):
        if (p["categorie"], p["titre"]) in existants:
            continue
        dbl = doublons(p["titre"], p["etapes"], p["gherkin"], [c for c in u.get("cas") or [] if c.get("statut") != "Rejeté"])
        c = t._ajouter_cas(u, p, f"catégorie : {CATEGORIES[p['categorie']]}")
        c.update({k: p[k] for k in ("categorie", "source_detail", "justification", "confiance", "provenance", "manquant")}, doublon=dbl)
        ajoutes.append(c)
    if ajoutes and u["statut"] in ("Détectée", "Analysée", "Réponses reçues", "Questions envoyées"):
        t._changer(u, "Cas proposés", f"{len(ajoutes)} cas par catégorie")
    t._sauver_us(d)
    t._journaliser("cas_proposes", cle=cle, nombre=len(ajoutes), source=f"catégories ({origine})")
    return {"ajoutes": len(ajoutes), "par_categorie": {k: sum(c["categorie"] == k for c in ajoutes) for k in CATEGORIES},
            "doublons": sum(c["doublon"]["recommandation"] != "créer" for c in ajoutes), "us": t.detail(cle)}


def verifier_doublons(cle: str) -> dict:
    """Recalcule la recommandation de doublon de chaque cas non publié de l'US (ex. après un import Xray)."""
    from atelier.intelligence import testabilite_us as t

    d, u = t._exiger(cle)
    n = 0
    for c in u.get("cas") or []:
        if c.get("statut") in ("Publié", "Rejeté"):
            continue
        autres = [x for x in u["cas"] if x["id"] != c["id"] and x.get("statut") != "Rejeté"]
        c["doublon"] = doublons(c["titre"], c.get("etapes") or [], c.get("gherkin") or "", autres)
        n += 1
    t._sauver_us(d)
    return {"verifies": n, "us": t.detail(cle)}
