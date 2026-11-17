"""Corrélation des écrans découverts avec Jira, Xray et le dépôt de tests (GitLab).

Pour chaque écran de la carte :
- **liens établis** (Knowledge Graph, relations fiables) : tests Robot qui utilisent ses locators, fichiers du
  dépôt, tests Xray qui les portent en tag, exigences Jira liées à ces tests (copie locale), tests passés par
  l'écran pendant les runs cartographiés ;
- **liens proposés** : jugés par une IA (Cursor via le MCP, ou LLM interne / Claude) qui comprend le texte de l'exigence
  et ce que montre l'écran ; à défaut (secours), exigences dont le résumé ou le module partage des mots avec le nom, le
  titre ou le module de l'écran. Une proposition n'entre dans le graphe que si l'automaticien la confirme (relation
  « impacte » déclarée) ;
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
    proposees = _avec_jugements(e["id"], proposees, exigences, pat)
    fichiers = sorted({t["fichier"] for t in imp["tests_robot"] if t.get("fichier")}
                      | {n.proprietes.get("fichier") for n in g.noeuds.values()
                         if n.type == "locator" and n.proprietes.get("ecran") == (e.get("nom") or "").lower() and n.proprietes.get("fichier")})
    return {"id": e["id"], "nom": e.get("nom") or e.get("titre") or e["id"], "module": e.get("module", ""), "noeud": nid,
            "tests_robot": imp["tests_robot"], "tests_xray": [{"cle": c, "resume": (tests_pat.get(c) or {}).get("resume", ""),
                                                                "connu": c in tests_pat} for c in cles],
            "exigences": sorted(exigences.values(), key=lambda x: x["cle"]), "exigences_proposees": proposees[:12],
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
    j = jugements().get(f"{e['id']}|{cle}")
    return declarations.ajouter_relation(f"{x['type']}:{cle}", f"ecran:{e.get('nom') or e['id']}", "impacte",
                                         source="Discovery (corrélation confirmée" + (f", proposée par {j['source']})" if j else ")"))


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


# --------------------------------------------------------------------------- corrélations jugées par une IA (Cursor / LLM)
VERDICTS = {"concerne": "concerne l'écran", "ne_concerne_pas": "ne concerne pas l'écran"}
CONSIGNE = (
    "Pour chaque écran, dire quelles exigences le concernent : « concerne » si l'exigence décrit un comportement visible ou "
    "déclenché sur cet écran (ses champs, boutons, messages, règles de saisie), « ne_concerne_pas » sinon. Un mot commun ne "
    "suffit pas : l'exigence peut porter sur un autre écran du même parcours. Les candidats sont une présélection par mots ; "
    "toute exigence de la liste peut être citée. Justification obligatoire. Le lien n'entre dans le Knowledge Graph qu'après "
    "confirmation de l'automaticien.")


def _fichier_jugements():
    from atelier.discovery import carte

    return carte._dir() / "correlations_jugees.json"


def jugements() -> dict:
    import json

    try:
        return json.loads(_fichier_jugements().read_text("utf-8"))
    except (OSError, ValueError, RuntimeError):
        return {}


def _avec_jugements(eid: str, proposees: list[dict], etablies: dict, pat: dict) -> list[dict]:
    """Propositions par les mots annotées du jugement d'une IA ; exigences jugées « concerne » ajoutées en tête. Une
    proposition jugée « ne concerne pas » reste visible avec ce jugement : l'automaticien tranche."""
    jug = {k.split("|", 1)[1]: v for k, v in jugements().items() if k.startswith(f"{eid}|")}
    if not jug:
        return proposees
    par_cle = {x["cle"]: x for x in pat.get("exigences", [])}
    out = [{**p, "jugement": jug[p["cle"]]} if p["cle"] in jug else p for p in proposees]
    vues = {p["cle"] for p in out}
    for cle, j in jug.items():
        if cle not in vues and cle not in etablies and cle in par_cle and j.get("verdict") == "concerne":
            x = par_cle[cle]
            out.append({"cle": cle, "resume": x.get("resume", ""), "type": x.get("type", ""), "mots": [], "score": 0, "jugement": j})
    rang = lambda p: 0 if (p.get("jugement") or {}).get("verdict") == "concerne" else 2 if p.get("jugement") else 1  # noqa: E731
    return sorted((p for p in out if p["cle"] not in etablies), key=lambda p: (rang(p), -p["score"], p["cle"]))


def _vue_ecran(e: dict) -> dict:
    from atelier.intelligence.jugement_ia import court

    els = [f"{k} ({el.get('type') or 'élément'})" + (f" : {court(el.get('libelle'), 80)}" if el.get("libelle") else "")
           for k, el in (e.get("elements") or {}).items()][:40]
    return {"ecran": e["id"], "nom": e.get("nom") or "", "titre": court(e.get("titre"), 120), "module": e.get("module") or "", "elements": els}


def correlations_a_juger(eid: str = "", limite: int = 15) -> dict:
    """Pour une IA : écrans (nom, titre, module, éléments ; libellés masqués), exigences déjà liées, candidats PRÉSÉLECTIONNÉS
    par les mots et liste des exigences de la copie locale Jira. Sans écran : d'abord ceux sans exigence liée."""
    from atelier.intelligence.jugement_ia import SECOURS, court

    ctx = _contexte()
    carte, pat = ctx[0], ctx[3]
    ecrans = [carte.ecran(eid)] if eid else carte.ecrans()
    lignes = []
    for e in ecrans:
        c = ecran(e["id"], ctx)
        lignes.append({**_vue_ecran(e), "exigences_liees": [x["cle"] for x in c["exigences"]],
                       "candidats": [{"cle": p["cle"], "resume": court(p["resume"], 160), "mots_communs": p["mots"],
                                     "jugement": p.get("jugement")} for p in c["exigences_proposees"]]})
    juges = {k.split("|", 1)[0] for k in jugements()}
    lignes.sort(key=lambda x: (bool(x["exigences_liees"]), x["ecran"] in juges, x["nom"]))  # écrans jamais jugés d'abord
    return {"consigne": CONSIGNE, "verdicts": list(VERDICTS), "candidats_par": SECOURS, "ecrans": lignes[:max(1, min(limite, 40))],
            "total_ecrans": len(lignes),
            "exigences": [{"cle": x["cle"], "type": x.get("type", ""), "resume": court(x.get("resume"), 160), "module": x.get("module") or ""}
                          for x in pat.get("exigences", [])][:400]}


def deposer_correlations(jugements_: list[dict], source: str = "Cursor (MCP)") -> dict:
    """Jugements d'une IA écran ↔ exigence, contrôlés (écran de la carte, exigence de la copie locale Jira, verdict connu,
    justification, lien pas déjà établi), conservés par application. Rien n'entre dans le graphe sans confirmation."""
    import json

    from atelier.intelligence.jugement_ia import justification as _j, maintenant
    from atelier.intelligence.strategie import _ecrire_atomique

    ctx = _contexte()
    carte, pat = ctx[0], ctx[3]
    connues = {x["cle"] for x in pat.get("exigences", [])}
    jug = jugements()
    compte, refuses, etablies = {v: 0 for v in VERDICTS}, [], {}
    for n, j in enumerate(jugements_ or [], 1):
        j = j if isinstance(j, dict) else {}
        ref, cle = str(j.get("ecran") or "").strip(), str(j.get("exigence") or "").strip()  # écran vide : refusé (carte.ecran)
        v, just = str(j.get("verdict") or "").strip().lower().replace(" ", "_"), _j(j.get("justification"))
        try:
            e = carte.ecran(ref)
        except KeyError:
            e = None
        if e and e["id"] not in etablies:
            etablies[e["id"]] = {x["cle"] for x in ecran(e["id"], ctx)["exigences"]}
        raison = ("écran inconnu dans la carte" if not e
                  else "exigence absente de la copie locale Jira" if cle not in connues
                  else "verdict inconnu (concerne ou ne_concerne_pas)" if v not in VERDICTS
                  else "justification manquante" if not just
                  else "lien déjà établi ou confirmé" if cle in etablies[e["id"]] else "")
        if raison:
            refuses.append({"index": n, "ecran": ref, "exigence": cle, "raison": raison})
            continue
        jug[f"{e['id']}|{cle}"] = {"verdict": v, "justification": just, "source": source, "date": maintenant()}
        compte[v] += 1
    _ecrire_atomique(_fichier_jugements(), json.dumps(jug, ensure_ascii=False, indent=1))
    return {"retenus": sum(compte.values()), **compte, "refuses": refuses}


SYSTEME = ("Tu es un ingénieur de test. On te donne des écrans d'une application (éléments observés) et des exigences Jira. "
           + CONSIGNE + ' Réponds uniquement en JSON : {"jugements": [{"ecran": "id", "exigence": "clé", "verdict": '
           '"concerne|ne_concerne_pas", "justification": "..."}]}. En français.')


def juger_ia(eid: str = "") -> dict:
    """Corrélations jugées par le LLM interne ou Claude (appel direct, texte masqué), mêmes contrôles que pour Cursor."""
    from atelier.intelligence import jugement_ia

    vue = correlations_a_juger(eid, limite=8)
    if not vue["ecrans"] or not vue["exigences"]:
        return {"disponible": False, "raison": "Aucun écran dans la carte ou aucune exigence dans la copie locale Jira."}
    return jugement_ia.appel_direct({k: vue[k] for k in ("ecrans", "exigences")}, SYSTEME, "jugements", deposer_correlations,
                                    "discovery_correlations_a_juger puis discovery_juger_correlations", 4000)
