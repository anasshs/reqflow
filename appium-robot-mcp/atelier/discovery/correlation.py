"""Corrélation des écrans découverts avec les exigences Jira, les tests Xray et le dépôt de tests (GitLab).

Deux relations, jamais confondues (décision du 2026-11-18, docs/CORRELATION_EXIGENCES_ECRANS.md) :
- **« vérifiée sur »** (exigence → écran) : PREUVE issue des tests, créée automatiquement par le Knowledge Graph. Un test
  automatisé lié à l'exigence dans Xray utilise les locators de l'écran, ou est passé par l'écran pendant un run
  cartographié. Elle porte ses preuves (test Xray, scripts, locators) et ne dit pas que l'écran réalise l'exigence :
  un test de bout en bout traverse aussi la connexion et l'accueil ;
- **« réalisé par »** (exigence → écran) : association FONCTIONNELLE, active seulement après une décision humaine
  (proposition d'une IA confirmée, preuve de test promue, ou lien manuel). Relation déclarée « impacte ».

Les propositions (jugées par une IA : Cursor via le MCP, ou LLM interne / Claude ; à défaut, simple ressemblance des mots)
restent dans cet espace : elles n'entrent dans le graphe qu'une fois confirmées, et un rejet est mémorisé (jamais
reproposé). Prérequis : l'écran existe dans la carte (session Discovery) ; sinon, aucun lien n'est créé.
Aucun appel Jira / Xray en direct : la copie locale (synchronisation) fait foi.
"""
from __future__ import annotations

import json
import re
import unicodedata

MOTS_VIDES = {"ecran", "page", "de", "du", "des", "la", "le", "les", "et", "en", "un", "une", "pour", "mon", "mes",
              "vos", "votre", "accueil", "home", "screen", "liste", "detail", "details", "saisie", "the", "and"}
TYPES_EXIGENCE = ("epic", "user_story", "bug")
ORIGINES = {"ia": "proposition d'une IA confirmée", "tests": "preuve de test promue", "manuel": "lien manuel",
            "mots": "ressemblance des mots"}


def _mots(*textes: str) -> set[str]:
    t = unicodedata.normalize("NFKD", " ".join(x or "" for x in textes)).encode("ascii", "ignore").decode().lower()
    return {m.rstrip("s") for m in re.split(r"[^a-z0-9]+", t) if len(m) >= 4 and m not in MOTS_VIDES}


def _contexte():
    from atelier.discovery import carte, connaissance
    from atelier.intelligence import patrimoine_xray

    g = connaissance.construire()
    pat = patrimoine_xray.charger_vue() or {"tests": [], "exigences": []}
    return carte, connaissance, g, pat


# --------------------------------------------------------------------------- décisions humaines et journal (par application)
def _lire(nom: str, defaut):
    from atelier.discovery import carte

    try:
        return json.loads((carte._dir() / nom).read_text("utf-8"))
    except (OSError, ValueError, RuntimeError):
        return defaut


def _ecrire(nom: str, data):
    from atelier.discovery import carte
    from atelier.intelligence.strategie import _ecrire_atomique

    _ecrire_atomique(carte._dir() / nom, json.dumps(data, ensure_ascii=False, indent=1))


def utilisateur() -> str:
    """Qui décide : la session du poste (l'atelier est local, sans comptes)."""
    import getpass

    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return "automaticien"


def decisions() -> dict:
    """État courant des décisions humaines, par couple « id d'écran|clé d'exigence » (id de la carte : stable)."""
    return _lire("correlations_decisions.json", {})


def _journal(evenement: str, eid: str, cle: str, **details):
    from atelier.intelligence.jugement_ia import maintenant

    j = _lire("correlations_historique.json", [])
    j.append({"date": maintenant(), "evenement": evenement, "ecran": eid, "exigence": cle,
              **{k: v for k, v in details.items() if v not in ("", None, [])}})
    _ecrire("correlations_historique.json", j[-2000:])


def _decider(eid: str, cle: str, etat: str, origine: str, motif: str = "", jugement: dict | None = None) -> dict:
    from atelier.intelligence.jugement_ia import maintenant

    d = decisions()
    d[f"{eid}|{cle}"] = {"etat": etat, "par": utilisateur(), "date": maintenant(), "origine": origine,
                         **({"motif": motif.strip()[:400]} if motif.strip() else {}), **({"jugement": jugement} if jugement else {})}
    _ecrire("correlations_decisions.json", d)
    _journal(etat, eid, cle, par=d[f"{eid}|{cle}"]["par"], origine=origine, motif=motif.strip()[:400],
             verdict=(jugement or {}).get("verdict"), source=(jugement or {}).get("source"))
    return d[f"{eid}|{cle}"]


def migrer_ecran(ancien: str, nouveau: str):
    """Deux écrans fusionnés dans la carte : jugements et décisions de l'écran disparu suivent l'écran gardé."""
    for nom in ("correlations_jugees.json", "correlations_decisions.json"):
        data = _lire(nom, {})
        touche = False
        for k in [k for k in data if k.startswith(f"{ancien}|")]:
            data.setdefault(f"{nouveau}|{k.split('|', 1)[1]}", data[k])
            del data[k]
            touche = True
        if touche:
            _ecrire(nom, data)


# --------------------------------------------------------------------------- un écran
def ecran(eid: str, ctx=None) -> dict:
    carte, connaissance, g, pat = ctx or _contexte()
    e = carte.ecran(eid)
    nid = f"ecran:{e.get('nom') or e['id']}"
    present = nid in g.noeuds
    imp = connaissance.analyser_impact(g, nid) if present else {"tests_robot": [], "tests_xray": [], "modules": []}
    cles = sorted({t["libelle"].split()[0] for t in imp["tests_xray"]} | {c for t in imp["tests_robot"] for c in t["cles_xray"]}
                  | {k for k in e.get("utilise_par") or [] if re.match(r"^[A-Z][A-Z0-9]+-\d+$", k)})
    tests_pat = {t["cle"]: t for t in pat.get("tests", [])}
    ex_par_cle = {x["cle"]: x for x in pat.get("exigences", [])}
    jug = {k.split("|", 1)[1]: v for k, v in jugements().items() if k.startswith(f"{e['id']}|")}
    dec = {k.split("|", 1)[1]: v for k, v in decisions().items() if k.startswith(f"{e['id']}|")}

    def fiche(n) -> dict:
        k = n.proprietes.get("cle") or n.id.split(":", 1)[1]
        return {"cle": k, "resume": (ex_par_cle.get(k) or {}).get("resume") or n.proprietes.get("resume") or "", "type": n.type}

    verifiees, realisees = {}, {}
    for r in g.entrants(nid, fiables=True) if present else []:
        n = g.noeuds.get(r.de)
        if not n or n.type not in TYPES_EXIGENCE:
            continue
        f = fiche(n)
        if r.type == "verifiee_sur":  # preuve issue des tests (Knowledge Graph)
            preuves = r.proprietes.get("preuves") or []
            verifiees[f["cle"]] = {**f, "preuves": preuves, "via": ", ".join(p["test_xray"] for p in preuves),
                                   "jugement": jug.get(f["cle"])}
        elif r.type == "impacte":  # association fonctionnelle validée
            d = dec.get(f["cle"]) or {}
            origine = d.get("origine") if d.get("etat") == "confirmée" else "manuel"
            realisees[f["cle"]] = {**f, "origine": origine, "origine_libelle": ORIGINES.get(origine, origine),
                                   "valide_par": d.get("par", ""), "valide_le": d.get("date", ""), "jugement": d.get("jugement"),
                                   "relation": r.id, "source": r.source}
    for k in realisees:  # une exigence validée garde ses preuves de test, sans figurer deux fois
        if k in verifiees:
            realisees[k]["preuves"] = verifiees[k]["preuves"]
    # compatibilité : toutes les exigences reliées, avec ce qui les relie
    exigences = {k: {**{c: v[c] for c in ("cle", "resume", "type")}, "via": v["via"].split(", ")[0], "lien": "vérifiée sur"}
                 for k, v in verifiees.items()}
    exigences.update({k: {**{c: v[c] for c in ("cle", "resume", "type")}, "via": "déclaré", "lien": "réalisé par"}
                      for k, v in realisees.items()})
    rejetees = sorted(({"cle": k, "resume": (ex_par_cle.get(k) or {}).get("resume", ""), "motif": d.get("motif", ""),
                        "par": d.get("par", ""), "date": d.get("date", "")}
                       for k, d in dec.items() if d.get("etat") == "rejetée" and k not in realisees), key=lambda x: x["cle"])
    # propositions par les mots (secours), puis jugements d'une IA
    mots = _mots(e.get("nom", ""), e.get("titre", ""), e.get("module", ""))
    proposees = []
    ecartees = set(exigences) | {x["cle"] for x in rejetees}
    from atelier.discovery import parcours_utilisateur

    du_parcours = parcours_utilisateur.exigences_des_ecrans().get(e["id"], {})  # exigences des parcours qui traversent l'écran
    if mots:
        for x in pat.get("exigences", []):
            if x["cle"] in ecartees:
                continue
            communs = mots & _mots(x.get("resume", ""), x.get("module") or "")
            if communs:
                proposees.append({"cle": x["cle"], "resume": x.get("resume", ""), "type": x["type"], "mots": sorted(communs),
                                  "score": len(communs)})
    for p in proposees:
        if p["cle"] in du_parcours:
            p["parcours"] = du_parcours[p["cle"]]
    vues = {p["cle"] for p in proposees}
    proposees += [{"cle": k, "resume": ex_par_cle[k].get("resume", ""), "type": ex_par_cle[k]["type"], "mots": [], "score": 0, "parcours": noms}
                  for k, noms in du_parcours.items() if k not in vues and k not in ecartees and k in ex_par_cle]
    proposees.sort(key=lambda p: (not p.get("parcours"), -p["score"], p["cle"]))
    proposees = _avec_jugements(jug, proposees, ecartees, pat)
    fichiers = sorted({t["fichier"] for t in imp["tests_robot"] if t.get("fichier")}
                      | {n.proprietes.get("fichier") for n in g.noeuds.values()
                         if n.type == "locator" and n.proprietes.get("ecran") == (e.get("nom") or "").lower() and n.proprietes.get("fichier")})
    return {"id": e["id"], "nom": e.get("nom") or e.get("titre") or e["id"], "module": e.get("module", ""), "noeud": nid,
            "titre": e.get("titre", ""), "plateformes": sorted((e.get("plateformes") or {}).keys()),
            "tests_robot": imp["tests_robot"], "tests_xray": [{"cle": c, "resume": (tests_pat.get(c) or {}).get("resume", ""),
                                                                "connu": c in tests_pat} for c in cles],
            "exigences": sorted(exigences.values(), key=lambda x: x["cle"]),
            "realisees": sorted(realisees.values(), key=lambda x: x["cle"]),
            "verifiees": sorted((v for k, v in verifiees.items() if k not in realisees), key=lambda x: x["cle"]),
            "exigences_proposees": proposees[:12], "rejetees": rejetees,
            "fichiers": sorted(f for f in fichiers if f), "tests_cartographies": sorted(e.get("utilise_par") or [])}


def detail(eid: str) -> dict:
    """Écran complet pour l'espace Corrélation : composants et locators, parcours (écrans voisins), liens et propositions."""
    ctx = _contexte()
    carte = ctx[0]
    c = ecran(eid, ctx)
    e = carte.ecran(eid)
    noms = {x["id"]: x.get("nom") or x.get("titre") or x["id"] for x in carte.ecrans()}
    action = lambda t: t["action"].get("libelle") or t["action"].get("cle") or t["action"].get("type") or ""  # noqa: E731
    ts = carte.transitions()
    return {**c,
            "composants": [{"cle": k, "type": el.get("type") or "", "libelle": el.get("libelle") or "",
                            "locators": {p: (locs or [""])[0] for p, locs in (el.get("locators") or {}).items() if locs}}
                           for k, el in (e.get("elements") or {}).items()],
            "parcours": {"depuis": [{"ecran": noms.get(t["de"], t["de"]), "action": action(t)} for t in ts if t["vers"] == e["id"]],
                         "vers": [{"ecran": noms.get(t["vers"], t["vers"]), "action": action(t)} for t in ts if t["de"] == e["id"]]}}


def synthese() -> dict:
    """Tous les écrans de l'application active : liens par écran, état de corrélation. « carte_vide » : aucune
    Discovery n'a encore été faite, rien ne peut être relié."""
    ctx = _contexte()
    carte = ctx[0]
    if not carte.app_courante():
        return {"ecrans": [], "sans_test": 0, "sans_exigence": 0, "copie_jira": False, "carte_vide": True, "application": ""}
    out = []
    for e in carte.ecrans():
        c = ecran(e["id"], ctx)
        etat = ("réalisé" if c["realisees"] else "vérifié par les tests" if c["verifiees"]
                else "propositions à trancher" if c["exigences_proposees"] else "à corréler")
        out.append({"id": c["id"], "nom": c["nom"], "module": c["module"], "noeud": c["noeud"], "plateformes": c["plateformes"],
                    "tests_robot": len(c["tests_robot"]), "tests_xray": len(c["tests_xray"]), "exigences": len(c["exigences"]),
                    "realisees": len(c["realisees"]), "verifiees": len(c["verifiees"]),
                    "proposees": len(c["exigences_proposees"]), "fichiers": len(c["fichiers"]), "etat": etat})
    try:
        suivre_preuves(ctx)
    except Exception:  # noqa: BLE001 — le suivi des preuves ne bloque jamais l'affichage
        pass
    return {"ecrans": out, "sans_test": sum(1 for x in out if not x["tests_robot"] and not x["tests_xray"]),
            "sans_exigence": sum(1 for x in out if not x["exigences"]), "copie_jira": bool(ctx[3].get("exigences")),
            "carte_vide": not out, "application": carte.app_courante() or ""}


# --------------------------------------------------------------------------- décisions : confirmer, rejeter, retirer
def _exigence(cle: str) -> dict:
    from atelier.intelligence import patrimoine_xray

    pat = patrimoine_xray.charger() or {"exigences": []}
    x = next((x for x in pat.get("exigences", []) if x["cle"] == cle), None)
    if not x:
        raise KeyError(f"Exigence {cle} absente de la copie locale Jira : synchroniser d'abord.")
    return x


def confirmer(eid: str, cle: str, origine: str = "") -> dict:
    """Décision humaine : l'exigence est « réalisée par » l'écran. Relation déclarée « impacte » (exigence → écran),
    validée. L'écran doit exister dans la carte. origine : « manuel » pour un lien créé à la main ; sinon déduite
    (proposition d'une IA, preuve de test promue, ressemblance des mots)."""
    from atelier.discovery import carte, connaissance
    from atelier.domain import declarations

    e = carte.ecran(eid)  # KeyError : pas d'écran dans la carte, pas de lien
    x = _exigence(cle)
    c = ecran(e["id"])
    if any(r["cle"] == cle for r in c["realisees"]):
        raise ValueError(f"{cle} est déjà reliée à l'écran {c['nom']}.")
    j = jugements().get(f"{e['id']}|{cle}")
    if origine not in ORIGINES:
        origine = ("ia" if j and j.get("verdict") != "ne_concerne_pas" else "tests" if any(v["cle"] == cle for v in c["verifiees"])
                   else "mots" if any(p["cle"] == cle for p in c["exigences_proposees"]) else "manuel")
    source = "Discovery (" + ("lien manuel)" if origine == "manuel" else "corrélation confirmée"
                              + (f", proposée par {j['source']})" if origine == "ia" else ", preuve de test)" if origine == "tests" else ")"))
    r = declarations.ajouter_relation(f"{x['type']}:{cle}", f"ecran:{e.get('nom') or e['id']}", "impacte", source=source)
    _decider(e["id"], cle, "confirmée", origine, jugement=j if origine == "ia" else None)
    connaissance.vider_cache()
    return r


def rejeter(eid: str, cle: str, motif: str = "") -> dict:
    """Décision humaine : la proposition est écartée et mémorisée (historique) ; elle n'est plus proposée, et une IA ne
    peut plus la redéposer. Un lien déjà validé se retire, il ne se rejette pas."""
    from atelier.discovery import carte

    e = carte.ecran(eid)
    c = ecran(e["id"])
    if any(r["cle"] == cle for r in c["realisees"]):
        raise PermissionError(f"{cle} est déjà reliée à l'écran {c['nom']} : retirer le lien, pas le rejeter.")
    j = jugements().get(f"{e['id']}|{cle}")
    return {"ecran": e["id"], "cle": cle, **_decider(e["id"], cle, "rejetée", "ia" if j else "mots", motif, j)}


def retirer(eid: str, cle: str, motif: str = "") -> dict:
    """Retire un lien « réalisé par » validé (erreur, écran qui a changé). Historisé ; la preuve de test éventuelle reste."""
    from atelier.discovery import carte, connaissance
    from atelier.domain import declarations

    e = carte.ecran(eid)
    c = ecran(e["id"])
    lien = next((r for r in c["realisees"] if r["cle"] == cle), None)
    if not lien:
        raise KeyError(f"{cle} n'est pas reliée à l'écran {c['nom']}.")
    declarations.supprimer_relation(lien["relation"], "validé")
    d = _decider(e["id"], cle, "retirée", lien["origine"], motif)
    connaissance.vider_cache()
    return {"ecran": e["id"], "cle": cle, **d}


def chercher_exigences(q: str = "", eid: str = "", limite: int = 20) -> list[dict]:
    """Exigences de la copie locale Jira pour un lien manuel (clé ou mots du résumé) ; celles déjà reliées à l'écran
    sont signalées."""
    ctx = _contexte()
    pat = ctx[3]
    liees = {x["cle"]: x["lien"] for x in ecran(eid, ctx)["exigences"]} if eid else {}
    mots = [m for m in unicodedata.normalize("NFKD", q or "").encode("ascii", "ignore").decode().lower().split() if m]
    out = []
    for x in pat.get("exigences", []):
        texte = unicodedata.normalize("NFKD", f"{x['cle']} {x.get('resume') or ''} {x.get('module') or ''}").encode("ascii", "ignore").decode().lower()
        if all(m in texte for m in mots):
            out.append({"cle": x["cle"], "resume": x.get("resume", ""), "type": x.get("type", ""), "module": x.get("module") or "",
                        "lien": liees.get(x["cle"], "")})
            if len(out) >= max(1, min(limite, 50)):
                break
    return out


def historique(eid: str = "", limite: int = 200) -> list[dict]:
    """Journal de la corrélation : confirmations, rejets, retraits, preuves de test apparues ou perdues."""
    from atelier.discovery import carte

    noms = {x["id"]: x.get("nom") or x.get("titre") or x["id"] for x in carte.ecrans()} if carte.app_courante() else {}
    j = [x for x in _lire("correlations_historique.json", []) if not eid or x.get("ecran") == eid]
    return [{**x, "nom": noms.get(x.get("ecran"), x.get("ecran"))} for x in j[-limite:][::-1]]


def suivre_preuves(ctx=None) -> dict:
    """Compare les preuves de test du graphe au dernier relevé : une preuve qui disparaît (script modifié, tag retiré)
    est consignée dans l'historique, jamais effacée en silence. Un lien « vérifiée sur » qui garde d'autres preuves reste."""
    g = (ctx or _contexte())[2]
    courant = {}
    for r in g.relations.values():
        if r.type == "verifiee_sur" and g.noeuds[r.vers].proprietes.get("id_carte"):
            n = g.noeuds[r.de]
            cle = n.proprietes.get("cle") or n.id.split(":", 1)[1]
            courant[f"{g.noeuds[r.vers].proprietes['id_carte']}|{cle}"] = sorted(p["test_xray"] for p in r.proprietes.get("preuves") or [])
    avant = _lire("correlations_preuves.json", None)
    bilan = {"apparus": 0, "perdus": 0, "preuves_perdues": 0}
    if avant is not None:
        for k, tests in courant.items():
            eid, cle = k.split("|", 1)
            if k not in avant:
                _journal("lien vérifié apparu", eid, cle, tests=tests)
                bilan["apparus"] += 1
            elif set(avant[k]) - set(tests):
                _journal("preuve perdue", eid, cle, tests=sorted(set(avant[k]) - set(tests)), restent=tests)
                bilan["preuves_perdues"] += 1
        for k in set(avant) - set(courant):
            eid, cle = k.split("|", 1)
            _journal("lien vérifié perdu : plus aucune preuve", eid, cle, tests=avant[k])
            bilan["perdus"] += 1
    if avant != courant:
        _ecrire("correlations_preuves.json", courant)
    return bilan


def actualiser() -> dict:
    """Relit les sources (carte, dépôt, copie Jira / Xray) et refait la corrélation ; renvoie ce qui a changé."""
    from atelier.discovery import connaissance

    connaissance.vider_cache()
    ctx = _contexte()
    bilan = suivre_preuves(ctx)
    return {**bilan, "ecrans": len(ctx[0].ecrans()) if ctx[0].app_courante() else 0}


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
VERDICTS = {"concerne": "concerne l'écran", "ne_concerne_pas": "ne concerne pas l'écran", "incertain": "incertain"}
ESTIMATIONS = ("faible", "moyenne", "forte")
CONSIGNE = (
    "Pour chaque écran, dire quelles exigences le concernent : « concerne » si l'exigence décrit un comportement visible ou "
    "déclenché sur cet écran (ses champs, boutons, messages, règles de saisie), « ne_concerne_pas » sinon, « incertain » si "
    "les éléments observés ne permettent pas de trancher. Un mot commun ne suffit pas : l'exigence peut porter sur un autre "
    "écran du même parcours ; un test qui traverse l'écran (« verifiees_par_tests ») ne prouve pas non plus que l'écran "
    "réalise l'exigence. Les candidats sont une présélection par mots ; toute exigence de la liste peut être citée. "
    "Justification obligatoire ; « preuves » : les éléments de l'écran ou les phrases de l'exigence sur lesquels tu t'appuies ; "
    "« confiance » : ton estimation (faible, moyenne, forte), jamais utilisée dans un calcul. Le lien n'entre dans le "
    "Knowledge Graph qu'après confirmation de l'automaticien ; une proposition qu'il a rejetée n'est plus à reproposer.")


def _fichier_jugements():
    from atelier.discovery import carte

    return carte._dir() / "correlations_jugees.json"


def jugements() -> dict:
    try:
        return json.loads(_fichier_jugements().read_text("utf-8"))
    except (OSError, ValueError, RuntimeError):
        return {}


def _avec_jugements(jug: dict, proposees: list[dict], ecartees: set, pat: dict) -> list[dict]:
    """Propositions par les mots annotées du jugement d'une IA ; exigences jugées « concerne » ou « incertain » ajoutées.
    Une proposition jugée « ne concerne pas » reste visible avec ce jugement : l'automaticien tranche."""
    if not jug:
        return proposees
    par_cle = {x["cle"]: x for x in pat.get("exigences", [])}
    out = [{**p, "jugement": jug[p["cle"]]} if p["cle"] in jug else p for p in proposees]
    vues = {p["cle"] for p in out}
    for cle, j in jug.items():
        if cle not in vues and cle not in ecartees and cle in par_cle and j.get("verdict") in ("concerne", "incertain"):
            x = par_cle[cle]
            out.append({"cle": cle, "resume": x.get("resume", ""), "type": x.get("type", ""), "mots": [], "score": 0, "jugement": j})
    ordre = {"concerne": 0, "incertain": 1, None: 2, "ne_concerne_pas": 3}
    rang = lambda p: ordre.get((p.get("jugement") or {}).get("verdict"), 2)  # noqa: E731
    return sorted((p for p in out if p["cle"] not in ecartees), key=lambda p: (rang(p), not p.get("parcours"), -p["score"], p["cle"]))


def _vue_ecran(e: dict) -> dict:
    from atelier.intelligence.jugement_ia import court

    els = [f"{k} ({el.get('type') or 'élément'})" + (f" : {court(el.get('libelle'), 80)}" if el.get("libelle") else "")
           for k, el in (e.get("elements") or {}).items()][:40]
    return {"ecran": e["id"], "nom": e.get("nom") or "", "titre": court(e.get("titre"), 120), "module": e.get("module") or "", "elements": els}


def correlations_a_juger(eid: str = "", limite: int = 15) -> dict:
    """Pour une IA : écrans (nom, titre, module, plateformes, éléments, écrans voisins du parcours ; libellés masqués),
    exigences déjà liées ou seulement vérifiées par les tests, candidats PRÉSÉLECTIONNÉS par les mots (avec description et
    critères d'acceptation) et liste des exigences de la copie locale Jira. Sans écran : d'abord ceux sans exigence liée.
    Aucune capture d'écran n'est transmise."""
    from atelier.intelligence.jugement_ia import SECOURS, court

    ctx = _contexte()
    carte, pat = ctx[0], ctx[3]
    ecrans = [carte.ecran(eid)] if eid else carte.ecrans()
    par_cle = {x["cle"]: x for x in pat.get("exigences", [])}
    noms = {x["id"]: x.get("nom") or x.get("titre") or x["id"] for x in carte.ecrans()}
    ts = carte.transitions()
    lignes = []
    for e in ecrans:
        c = ecran(e["id"], ctx)
        lignes.append({**_vue_ecran(e), "plateformes": c["plateformes"],
                       "parcours": {"depuis": sorted({noms.get(t["de"], t["de"]) for t in ts if t["vers"] == e["id"]}),
                                    "vers": sorted({noms.get(t["vers"], t["vers"]) for t in ts if t["de"] == e["id"]})},
                       "exigences_liees": [x["cle"] for x in c["realisees"]],
                       "verifiees_par_tests": [{"cle": v["cle"], "resume": court(v["resume"], 160), "tests": v["via"],
                                                "jugement": v.get("jugement")} for v in c["verifiees"]],
                       "candidats": [{"cle": p["cle"], "resume": court(p["resume"], 160), "mots_communs": p["mots"],
                                      "parcours": p.get("parcours", []),
                                      "description": court((par_cle.get(p["cle"]) or {}).get("description"), 300),
                                      "criteres": [court(x, 160) for x in ((par_cle.get(p["cle"]) or {}).get("criteres") or [])[:6]],
                                      "jugement": p.get("jugement")} for p in c["exigences_proposees"]]})
    juges = {k.split("|", 1)[0] for k in jugements()}
    lignes.sort(key=lambda x: (bool(x["exigences_liees"]), x["ecran"] in juges, x["nom"]))  # écrans jamais jugés d'abord
    return {"consigne": CONSIGNE, "verdicts": list(VERDICTS), "confiance": list(ESTIMATIONS), "candidats_par": SECOURS,
            "ecrans": lignes[:max(1, min(limite, 40))], "total_ecrans": len(lignes),
            "exigences": [{"cle": x["cle"], "type": x.get("type", ""), "resume": court(x.get("resume"), 160), "module": x.get("module") or ""}
                          for x in pat.get("exigences", [])][:400]}


def deposer_correlations(jugements_: list[dict], source: str = "Cursor (MCP)") -> dict:
    """Jugements d'une IA écran ↔ exigence, contrôlés (écran de la carte, exigence de la copie locale Jira, verdict connu,
    justification, lien pas déjà confirmé, proposition pas déjà rejetée), conservés par application. Facultatifs :
    « confiance » (faible, moyenne, forte : estimation de l'IA) et « preuves » (éléments sur lesquels elle s'appuie).
    Rien n'entre dans le graphe sans confirmation."""
    from atelier.intelligence.jugement_ia import court, justification as _j, maintenant
    from atelier.intelligence.strategie import _ecrire_atomique

    ctx = _contexte()
    carte, pat = ctx[0], ctx[3]
    connues = {x["cle"] for x in pat.get("exigences", [])}
    jug, dec = jugements(), decisions()
    compte, refuses, confirmees = {v: 0 for v in VERDICTS}, [], {}
    for n, j in enumerate(jugements_ or [], 1):
        j = j if isinstance(j, dict) else {}
        ref, cle = str(j.get("ecran") or "").strip(), str(j.get("exigence") or "").strip()  # écran vide : refusé (carte.ecran)
        v, just = str(j.get("verdict") or "").strip().lower().replace(" ", "_"), _j(j.get("justification"))
        try:
            e = carte.ecran(ref)
        except KeyError:
            e = None
        if e and e["id"] not in confirmees:
            confirmees[e["id"]] = {x["cle"] for x in ecran(e["id"], ctx)["realisees"]}
        raison = ("écran inconnu dans la carte" if not e
                  else "exigence absente de la copie locale Jira" if cle not in connues
                  else "verdict inconnu (concerne, ne_concerne_pas ou incertain)" if v not in VERDICTS
                  else "justification manquante" if not just
                  else "lien déjà établi ou confirmé" if cle in confirmees[e["id"]]
                  else "proposition rejetée par l'automaticien : elle n'est plus à reproposer"
                  if (dec.get(f"{e['id']}|{cle}") or {}).get("etat") == "rejetée" else "")
        if raison:
            refuses.append({"index": n, "ecran": ref, "exigence": cle, "raison": raison})
            continue
        estimation = str(j.get("confiance") or "").strip().lower()
        preuves = [court(p, 160) for p in (j.get("preuves") if isinstance(j.get("preuves"), list) else []) if str(p).strip()][:6]
        jug[f"{e['id']}|{cle}"] = {"verdict": v, "justification": just, "source": source, "date": maintenant(),
                                   **({"estimation": estimation} if estimation in ESTIMATIONS else {}),
                                   **({"preuves": preuves} if preuves else {})}
        compte[v] += 1
    _ecrire_atomique(_fichier_jugements(), json.dumps(jug, ensure_ascii=False, indent=1))
    return {"retenus": sum(compte.values()), **compte, "refuses": refuses}


SYSTEME = ("Tu es un ingénieur de test. On te donne des écrans d'une application (éléments observés) et des exigences Jira. "
           + CONSIGNE + ' Réponds uniquement en JSON : {"jugements": [{"ecran": "id", "exigence": "clé", "verdict": '
           '"concerne|ne_concerne_pas|incertain", "justification": "...", "confiance": "faible|moyenne|forte", '
           '"preuves": ["..."]}]}. En français.')


def juger_ia(eid: str = "") -> dict:
    """Corrélations jugées par le LLM interne ou Claude (appel direct, texte masqué), mêmes contrôles que pour Cursor."""
    from atelier.intelligence import jugement_ia

    vue = correlations_a_juger(eid, limite=8)
    if not vue["ecrans"] or not vue["exigences"]:
        return {"disponible": False, "raison": "Aucun écran dans la carte ou aucune exigence dans la copie locale Jira."}
    return jugement_ia.appel_direct({k: vue[k] for k in ("ecrans", "exigences")}, SYSTEME, "jugements", deposer_correlations,
                                    "discovery_correlations_a_juger puis discovery_juger_correlations", 4000)
