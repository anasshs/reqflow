"""Corrélation des écrans découverts avec Jira, Xray et le dépôt de tests (GitLab).

Pour chaque écran de la carte :
- **liens établis** (Knowledge Graph, relations fiables) : tests Robot qui utilisent ses locators, fichiers du
  dépôt, tests Xray qui les portent en tag, exigences Jira liées à ces tests (copie locale), tests passés par
  l'écran pendant les runs cartographiés ;
- **liens proposés** : exigences dont le résumé ou le module partage des mots avec le nom, le titre ou le module de
  l'écran ; une proposition n'entre dans le graphe que si l'automaticien la confirme (relation « impacte »
  déclarée) ;
- **GitLab** (à la demande) : derniers commits des fichiers concernés, si GitLab est configuré.
Aucun appel Jira / Xray en direct : la copie locale (synchronisation) fait foi.
"""
from __future__ import annotations

import re
import unicodedata

MOTS_VIDES = {"ecran", "page", "de", "du", "des", "la", "le", "les", "et", "en", "un", "une", "pour", "mon", "mes",
              "vos", "votre", "accueil", "home", "screen", "liste", "detail", "details", "saisie", "the", "and"}


def _mots(*textes: str) -> set[str]:
    t = unicodedata.normalize("NFKD", " ".join(x or "" for x in textes)).encode("ascii", "ignore").decode().lower()
    return {m.rstrip("s") for m in re.split(r"[^a-z0-9]+", t) if len(m) >= 4 and m not in MOTS_VIDES}


def _contexte():
    from atelier.discovery import carte, connaissance
    from atelier.intelligence import patrimoine_xray

    g = connaissance.construire()
    pat = patrimoine_xray.charger_vue() or {"tests": [], "exigences": []}
    return carte, connaissance, g, pat


def ecran(eid: str, ctx=None) -> dict:
    carte, connaissance, g, pat = ctx or _contexte()
    e = carte.ecran(eid)
    nid = f"ecran:{e.get('nom') or e['id']}"
    imp = connaissance.analyser_impact(g, nid) if nid in g.noeuds else {"tests_robot": [], "tests_xray": [], "modules": []}
    cles = sorted({t["libelle"].split()[0] for t in imp["tests_xray"]} | {c for t in imp["tests_robot"] for c in t["cles_xray"]}
                  | {k for k in e.get("utilise_par") or [] if re.match(r"^[A-Z][A-Z0-9]+-\d+$", k)})
    tests_pat = {t["cle"]: t for t in pat.get("tests", [])}
    ex_par_cle = {x["cle"]: x for x in pat.get("exigences", [])}
    exigences = {}
    for c in cles:
        for x in (tests_pat.get(c) or {}).get("exigences") or []:
            k = x if isinstance(x, str) else x.get("cle")
            if k:
                exigences[k] = {"cle": k, "resume": (ex_par_cle.get(k) or {}).get("resume", ""), "type": (ex_par_cle.get(k) or {}).get("type", ""),
                                "via": c}
    # liens déclarés (confirmés) dans le graphe
    for r in g.entrants(nid, fiables=True) if nid in g.noeuds else []:
        n = g.noeuds.get(r.de)
        if n and n.type in ("epic", "user_story", "bug") and r.type == "impacte":
            k = n.proprietes.get("cle") or r.de.split(":", 1)[1]
            exigences.setdefault(k, {"cle": k, "resume": n.proprietes.get("resume", ""), "type": n.type, "via": "déclaré"})
    # propositions par les mots
    mots = _mots(e.get("nom", ""), e.get("titre", ""), e.get("module", ""))
    proposees = []
    if mots:
        for x in pat.get("exigences", []):
            if x["cle"] in exigences:
                continue
            communs = mots & _mots(x.get("resume", ""), x.get("module") or "")
            if communs:
                proposees.append({"cle": x["cle"], "resume": x.get("resume", ""), "type": x["type"], "mots": sorted(communs),
                                  "score": len(communs)})
        proposees.sort(key=lambda p: (-p["score"], p["cle"]))
    fichiers = sorted({t["fichier"] for t in imp["tests_robot"] if t.get("fichier")}
                      | {n.proprietes.get("fichier") for n in g.noeuds.values()
                         if n.type == "locator" and n.proprietes.get("ecran") == (e.get("nom") or "").lower() and n.proprietes.get("fichier")})
    return {"id": e["id"], "nom": e.get("nom") or e.get("titre") or e["id"], "module": e.get("module", ""), "noeud": nid,
            "tests_robot": imp["tests_robot"], "tests_xray": [{"cle": c, "resume": (tests_pat.get(c) or {}).get("resume", ""),
                                                                "connu": c in tests_pat} for c in cles],
            "exigences": sorted(exigences.values(), key=lambda x: x["cle"]), "exigences_proposees": proposees[:8],
            "fichiers": sorted(f for f in fichiers if f), "tests_cartographies": sorted(e.get("utilise_par") or [])}


def synthese() -> dict:
    """Tous les écrans de l'application active : nombre de liens par écran, écrans sans exigence ni test."""
    ctx = _contexte()
    carte = ctx[0]
    if not carte.app_courante():
        return {"ecrans": [], "sans_test": 0, "sans_exigence": 0, "copie_jira": False}
    out = []
    for e in carte.ecrans():
        c = ecran(e["id"], ctx)
        out.append({"id": c["id"], "nom": c["nom"], "module": c["module"], "tests_robot": len(c["tests_robot"]),
                    "tests_xray": len(c["tests_xray"]), "exigences": len(c["exigences"]),
                    "proposees": len(c["exigences_proposees"]), "fichiers": len(c["fichiers"])})
    return {"ecrans": out, "sans_test": sum(1 for x in out if not x["tests_robot"] and not x["tests_xray"]),
            "sans_exigence": sum(1 for x in out if not x["exigences"]), "copie_jira": bool(ctx[3].get("exigences"))}


def confirmer(eid: str, cle: str) -> dict:
    """L'automaticien confirme qu'une exigence concerne l'écran : relation déclarée « impacte » (exigence → écran)."""
    from atelier.discovery import carte
    from atelier.domain import declarations
    from atelier.intelligence import patrimoine_xray

    e = carte.ecran(eid)
    pat = patrimoine_xray.charger() or {"exigences": []}
    x = next((x for x in pat.get("exigences", []) if x["cle"] == cle), None)
    if not x:
        raise KeyError(f"Exigence {cle} absente de la copie locale Jira : synchroniser d'abord.")
    return declarations.ajouter_relation(f"{x['type']}:{cle}", f"ecran:{e.get('nom') or e['id']}", "impacte",
                                         source="Discovery (corrélation confirmée)")


def commits_gitlab(fichiers: list[str], limite: int = 3) -> dict:
    """Derniers commits GitLab des fichiers (à la demande ; GitLab non configuré : rien, sans erreur)."""
    from atelier.integrations import gitlab

    if not gitlab.configure():
        return {"configure": False, "fichiers": {}}
    c = gitlab.GitLabClient()
    out = {}
    for f in fichiers[:10]:
        try:
            out[f] = c.commits(chemin=f, limite=limite)
        except Exception as e:  # noqa: BLE001
            out[f] = {"erreur": str(e)[:200]}
    return {"configure": True, "fichiers": out}
