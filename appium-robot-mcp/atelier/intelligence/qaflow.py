"""Vues de lecture de QAFlow (docs/REFONTE_UI_QAFLOW.md) : parcours avec leur statut métier et ce qui leur manque.

Rien n'est écrit ici : ce module assemble des lectures existantes (parcours utilisateur, scénarios BDD, cycle des tests
automatisés, implémentations par technologie) et les traduit dans le vocabulaire de QAFlow.

Statuts métier, quatre et pas plus (décision de l'utilisateur du 2026-11-25) : À faire, En cours, À valider, Validé.
Un blocage n'est pas un statut : c'est une alerte portée par l'objet, avec sa raison.
Un test automatisé porte trois notions distinctes : généré (script écrit), exécuté (run réel postérieur à la dernière
modification), validé par la QA (suite validée). Une génération n'est jamais présentée comme validée.
"""
from __future__ import annotations

A_FAIRE, EN_COURS, A_VALIDER, VALIDE = "À faire", "En cours", "À valider", "Validé"
STATUTS = (A_FAIRE, EN_COURS, A_VALIDER, VALIDE)


def _reperes(p: dict, sessions: list | None = None) -> dict:
    """Ce qui relie un parcours à ses scénarios BDD (identifiant, nœud, nom, sessions de Discovery)."""
    from atelier.discovery import parcours_utilisateur

    if sessions is None:
        try:
            sessions = parcours_utilisateur._lire(p["id"]).get("sessions", [])
        except (KeyError, ValueError):
            sessions = []
    return {"id": p.get("id"), "noeud": p.get("noeud"), "nom": p.get("nom"),
            "sessions_ids": [x if isinstance(x, str) else x.get("id") for x in sessions]}


def notions(cycle: dict | None) -> dict:
    """Les trois notions d'un test automatisé, chacune prouvée séparément."""
    c = cycle or {}
    return {"genere": bool(c.get("script")), "execute": bool(c.get("verifie")), "valide_qa": c.get("etat") == "Validé"}


def _scenarios(reperes: dict, tous: list[dict], cycles: dict) -> list[dict]:
    from atelier.generation import maintenance

    out = []
    for b in tous:
        if not maintenance.du_parcours(b, reperes):
            continue
        c = cycles.get(b["cle"])
        out.append({"cle": b["cle"], "titre": b.get("titre", ""), "scenarios": b.get("scenarios", 0),
                    "statut": VALIDE if b.get("statut") == "validé" else A_VALIDER,
                    "notions": notions(c), "suites": (c or {}).get("suites", []),
                    "suivante": maintenance.etape_bdd(b, c)["libelle"]})
    return out


def statut_parcours(statut_atelier: str, sessions: int, scenarios: list[dict]) -> str:
    """Statut atelier du parcours (Brouillon, Prêt, En cours, Exploré, Validé) traduit en statut QAFlow."""
    if statut_atelier == "Validé":
        return VALIDE
    if statut_atelier == "Exploré":
        return A_VALIDER
    if statut_atelier == "En cours" or sessions or scenarios:
        return EN_COURS
    return A_FAIRE


def _alertes(d: dict, scenarios: list[dict]) -> list[str]:
    """Ce qui manque réellement au parcours (pas une liste figée) : chaque alerte dit quoi faire."""
    c = d.get("controles") or {}
    out = list(c.get("bloquants") or [])
    if not d.get("sessions"):
        out.append("Aucune session déroulée : démarrer une session assistée pour capturer écrans et actions.")
    elif not scenarios:
        out.append("Aucun scénario BDD : les générer depuis la dernière session.")
    out += list(c.get("avertissements") or [])
    n = d.get("ecrans_a_valider") or 0
    if n:
        out.append(f"{n} écran(s) proposé(s) à valider.")
    a_valider = sum(1 for s in scenarios if s["statut"] == A_VALIDER)
    if a_valider:
        out.append(f"{a_valider} scénario(s) BDD à relire et valider.")
    non_executes = sum(1 for s in scenarios if s["notions"]["genere"] and not s["notions"]["execute"])
    if non_executes:
        out.append(f"{non_executes} test(s) généré(s) jamais exécutés en run réel.")
    don = d.get("donnees") or {}
    if don.get("bloquees"):
        out.append(f"{len(don['bloquees'])} donnée(s) du profil sans valeur.")
    return out


def _contexte():
    from atelier.generation import bdd, maintenance

    tous = bdd.lister()
    try:
        cycles = maintenance.cycle_bdd() if tous else {}
    except Exception:  # noqa: BLE001 — dépôt illisible : parcours servis sans l'avancement des tests
        cycles = {}
    return tous, cycles


def parcours() -> list[dict]:
    """Une ligne par parcours de l'application active : statut QAFlow, chiffres réels, alertes."""
    from atelier.discovery import parcours_utilisateur

    tous, cycles = _contexte()
    out = []
    for p in parcours_utilisateur.lister():
        sc = _scenarios(_reperes(p), tous, cycles)
        out.append({"id": p["id"], "nom": p["nom"], "objectif": p.get("objectif", ""), "plateforme": p.get("plateforme", ""),
                    "environnement": p.get("environnement", ""), "modifie": p.get("modifie", ""),
                    "statut": statut_parcours(p["statut"], p.get("sessions", 0), sc), "statut_atelier": p["statut"],
                    "ecrans": p.get("ecrans", 0), "sessions": p.get("sessions", 0), "exigences": p.get("exigences", []),
                    "bdd": {"total": len(sc), "valides": sum(1 for s in sc if s["statut"] == VALIDE)},
                    "tests": {"generes": sum(1 for s in sc if s["notions"]["genere"]),
                              "executes": sum(1 for s in sc if s["notions"]["execute"]),
                              "valides_qa": sum(1 for s in sc if s["notions"]["valide_qa"])}})
    return out


def parcours_detail(pid: str) -> dict:
    """Espace de travail d'un parcours : cadrage, écrans, scénarios et leurs tests, données, sessions, historique."""
    from atelier.discovery import parcours_utilisateur
    from atelier.generation import perimetre

    d = parcours_utilisateur.obtenir(pid)
    tous, cycles = _contexte()
    sc = _scenarios(_reperes(d, [s["id"] for s in d.get("sessions", [])]), tous, cycles)
    try:
        par_bdd = {v: k for k, v in perimetre._bdd_par_cle_xray().items()}
        impl = perimetre._implementations()
    except Exception:  # noqa: BLE001 — dépôt ou projet Kotlin illisible : pas d'implémentation connue
        par_bdd, impl = {}, {}
    for s in sc:
        s["cle_xray"] = par_bdd.get(s["cle"], "")
        s["technologies"] = sorted(impl.get(s["cle_xray"] or s["cle"], {}))
    sc_jdd = jeux_de_donnees(pid, d, sc)
    return {**{k: d.get(k) for k in ("id", "nom", "objectif", "point_depart", "resultat_attendu", "plateforme", "environnement",
                                     "pilote", "profil_donnees", "auteur", "cree", "modifie", "noeud", "session_active")},
            "statut": statut_parcours(d["statut"], len(d.get("sessions", [])), sc), "statut_atelier": d["statut"],
            "exigences": d.get("exigences", []), "ecrans": d.get("ecrans", []), "sessions": d.get("sessions", []),
            "donnees": d.get("donnees"), "scenarios": sc, "alertes": _alertes(d, sc) + sc_jdd["alertes"],
            "jdd": sc_jdd, "historique": d.get("historique", [])[:30]}


# --------------------------------------------------------------------------- jeux de données d'un parcours
def jeux_de_donnees(pid: str, d: dict | None = None, scenarios: list[dict] | None = None) -> dict:
    """Données du parcours, sous trois angles, chacun avec un statut QAFlow :
    - jeux des scénarios (&{JDD_<NOM>}, data/jdd/<env>.yaml) : Validé s'il existe dans l'environnement, À faire sinon,
      ou si une étape consomme une donnée sans jeu ;
    - données proposées par l'agent pendant les sessions : À valider (confirmées par l'automaticien) ;
    - profil de données de la Discovery : variables prêtes et sans valeur.
    Aucune valeur secrète n'est renvoyée."""
    from atelier.discovery import donnees, parcours_utilisateur
    from atelier.execution import donnees_tests, jdd

    d = d or parcours_utilisateur.obtenir(pid)
    env = d.get("environnement") or donnees_tests._env()
    try:
        connus = {j["jeu"]: j for j in jdd.lister(env)}
        variantes = jdd.variantes(env)
    except Exception:  # noqa: BLE001 — fichier absent ou illisible : chaque jeu apparaît « à faire »
        connus, variantes = {}, {}
    if scenarios is None:
        scenarios = _scenarios(_reperes(d, [x["id"] for x in d.get("sessions", [])]), *_contexte())
    jeux, sans_jeu = {}, []
    from atelier.generation import bdd

    for s in scenarios:
        m = bdd.charger(s["cle"]) or {}
        noms = [m["jdd"]] if m.get("jdd") else []
        noms += [j for sc in m.get("scenarios") or [] for j in bdd.jeux_des_exemples(sc)]
        if not noms and bdd.etapes_avec_donnees(m):
            sans_jeu.append({"cle": s["cle"], "titre": s["titre"]})
        for n in dict.fromkeys(noms):
            j = jeux.setdefault(n, {"jeu": n, "statut": VALIDE if n in connus else A_FAIRE,
                                    "description": (connus.get(n) or {}).get("description", ""),
                                    "champs": (connus.get(n) or {}).get("champs", []),
                                    "variantes": [v["jeu"] for v in variantes.get(n, [])], "scenarios": []})
            j["scenarios"].append(s["cle"])
    try:
        proposees = donnees.propositions(pid)
    except Exception:  # noqa: BLE001 — référentiel illisible : rien de proposé plutôt qu'une erreur
        proposees = []
    proposees = [{"cle": p["cle"], "nom": p["nom"], "type": p["type"], "description": p["description"], "statut": A_VALIDER,
                  "valeur": "••••" if p["type"] in ("secret", "mot_de_passe") else p.get("valeur"), "par": p.get("par", "")}
                 for p in proposees]
    alertes = []
    absents = [j["jeu"] for j in jeux.values() if j["statut"] == A_FAIRE]
    if absents:
        alertes.append(f"Jeu(x) de données absent(s) de {env} : {', '.join(absents)}.")
    if sans_jeu:
        alertes.append(f"{len(sans_jeu)} scénario(s) consomment une donnée sans jeu de données.")
    if proposees:
        alertes.append(f"{len(proposees)} donnée(s) proposée(s) par l'agent à confirmer.")
    return {"environnement": env, "fichier": f"data/jdd/{env}.yaml", "jeux": list(jeux.values()), "sans_jeu": sans_jeu,
            "proposees": proposees, "profil": d.get("donnees"), "alertes": alertes,
            "variables": _variables_du_parcours(d.get("profil_donnees") or "", {p["cle"] for p in proposees}),
            # jeu de données des tests du parcours : nommé comme son profil, tenu à jour à chaque saisie ou modification
            "jeu_du_parcours": {"jeu": (d.get("profil_donnees") or "").upper(), "env": env,
                                "present": bool(d.get("profil_donnees")) and (d.get("profil_donnees") or "").upper() in connus,
                                "champs": (connus.get((d.get("profil_donnees") or "").upper()) or {}).get("champs", [])},
            "consignes": _consignes(d)}


def _variables_du_parcours(profil: str, proposees: set) -> list[dict]:
    """Données du profil du parcours (saisies et valeurs attendues des sessions comprises), valeur du profil : modifiables
    à tout moment. Une valeur secrète reste masquée."""
    from atelier.discovery import donnees

    if not profil:
        return []
    try:
        vs = donnees.variables(profil=profil)
    except Exception:  # noqa: BLE001 — référentiel illisible
        return []
    out = []
    for v in vs:
        val = v["valeurs"]["profils"].get(profil, v["valeurs"]["defaut"])
        out.append({"cle": v["cle"], "nom": v["nom"], "type": v["type"], "secret": v["sensibilite"] == "secrète",
                    "valeur": val, "attendu": v["cle"].startswith("ATTENDU_"), "profil": profil,
                    "statut": A_VALIDER if v["cle"] in proposees else VALIDE if val not in (None, "") else A_FAIRE})
    return out


def _consignes(d: dict) -> dict:
    """Saisies et vérifications faites depuis le miroir pendant les sessions du parcours (corrigeables, retirables)."""
    from atelier.discovery import sessions_discovery

    saisies, assertions = [], []
    for s in d.get("sessions", []):
        try:
            x = sessions_discovery._lire(s["id"])
        except (KeyError, ValueError, OSError):
            continue
        saisies += [{**a, "session": s["id"], "index": i} for i, a in enumerate(x.get("saisies") or [])]
        assertions += [{**a, "session": s["id"], "index": i} for i, a in enumerate(x.get("assertions") or [])]
    return {"saisies": saisies, "assertions": assertions}


# --------------------------------------------------------------------------- Centre d'activité IA
_ETAT_TRAVAIL = {"en_cours": "en_cours", "termine": "termine", "echec": "echec", "arrete": "echec", "annule": "annule"}
_ETAT_BOITE = {"en attente": "en_attente", "prise": "en_cours", "terminée": "termine", "échouée": "echec", "annulée": "annule"}
_LIVRABLES = ("bdd", "fichier", "suite", "run", "chemin", "cle_xray")


def _de_travail(t: dict) -> dict:
    etapes = t.get("etapes") or []
    decision = next((e for e in etapes if e.get("statut") == "attente_decision"), None)
    etat = "a_decider" if decision and t.get("statut") == "en_cours" else _ETAT_TRAVAIL.get(t.get("statut"), "en_cours")
    attend = next((e for e in etapes if e.get("statut") == "attente_ressource"), None)
    erreur = next((e.get("erreur") for e in etapes if e.get("erreur")), "")
    return {"id": t["id"], "source": "travail", "titre": t.get("titre", ""), "etat": etat, "debut": t.get("cree", ""),
            "fin": next((e.get("fin") for e in reversed(etapes) if e.get("fin")), "") if etat in ("termine", "echec") else "",
            "etapes": [{"id": e["id"], "titre": e.get("titre", ""), "type": e.get("type", ""), "statut": e.get("statut", ""),
                        "resultat": str(e.get("resultat") or "")[:200], "erreur": str(e.get("erreur") or "")[:200]} for e in etapes],
            "dependance": "attend un téléphone libre" if attend else "",
            "livrables": {k: v for k, v in (t.get("contexte") or {}).items() if k in _LIVRABLES and v},
            "erreur": str(erreur or "")[:300],
            "action": {"type": "decider", "etape": decision["id"], "libelle": decision.get("titre", "Décision attendue")} if decision else None,
            "lien": f"/plateforme#travaux/{t['id']}"}


def activite(limite: int = 30) -> dict:
    """Toutes les tâches IA et MCP en une liste : travaux de l'orchestrateur (étapes réelles, dépendance, livrables,
    erreur, décision attendue), demandes à l'agent (compte rendu ; suivi QAFlow si c'est une automatisation) et session
    Discovery en cours. Ce qui attend l'utilisateur d'abord, puis ce qui avance, puis le reste. Lecture seule."""
    from atelier.discovery import sessions_discovery
    from atelier.execution import orchestrateur
    from atelier.integrations import boite_cursor

    taches = []
    try:
        taches += [_de_travail(t) for t in orchestrateur.lister()[:limite]]
    except Exception:  # noqa: BLE001 — orchestrateur illisible : le reste reste visible
        pass
    try:
        boite = boite_cursor.etat(limite=limite)["demandes"]
    except Exception:  # noqa: BLE001
        boite = []
    from atelier.generation import suivi_automatisation

    suivis = {f.stem for f in suivi_automatisation._d().glob("DC-*.json")} if suivi_automatisation._d().exists() else set()
    for d in boite:
        if d.get("travail"):
            continue  # suivie dans son travail
        etat = _ETAT_BOITE.get(d.get("statut"), "en_attente")
        taches.append({"id": d["id"], "source": "agent", "titre": d.get("titre", ""), "etat": etat, "debut": d.get("cree", ""),
                       "fin": d.get("fini", ""), "etapes": [], "dependance": "l'agent ne l'a pas encore prise" if etat == "en_attente" else "",
                       "livrables": {}, "erreur": str(d.get("erreur") or "")[:300], "compte_rendu": str(d.get("resultat") or "")[:400],
                       "action": None, "lien": f"#automatisation/{d['id']}" if d["id"] in suivis else (d.get("ecran") or "")})
    try:
        s = sessions_discovery.active()
    except Exception:  # noqa: BLE001
        s = None
    if s:
        cfg = s.get("config") or {}
        taches.append({"id": s["id"], "source": "session", "titre": f"Session assistée · {cfg.get('parcours_nom') or cfg.get('app_nom', '')}",
                       "etat": "en_cours", "debut": s.get("debut") or s.get("cree", ""), "fin": "", "etapes": [], "dependance": "",
                       "livrables": {}, "erreur": "", "action": None,
                       "lien": f"#session/{cfg['parcours']}/{s['id']}" if cfg.get("parcours") else "/plateforme#discovery"})
    ordre = {"a_decider": 0, "en_cours": 1, "en_attente": 2}  # puis le reste (terminé, échoué), du plus récent au plus ancien
    taches = [t for t in taches if t["etat"] != "annule"]
    taches.sort(key=lambda t: t["debut"] or "", reverse=True)
    taches.sort(key=lambda t: ordre.get(t["etat"], 9))
    return {"taches": taches[:limite], "compteurs": {"a_decider": sum(t["etat"] == "a_decider" for t in taches),
                                                     "en_cours": sum(t["etat"] in ("en_cours", "en_attente") for t in taches)}}


# --------------------------------------------------------------------------- Centre d'exécution
def execution(limite: int = 20) -> dict:
    """Centre d'exécution QAFlow : exécutions en cours et en file, compteurs (exécutions réussies / en échec, tests
    passés / échoués : des nombres, jamais un pourcentage global), exécutions récentes. Lecture seule."""
    from atelier.execution import centre, direct, historique

    v = centre.vue_ensemble()
    k = v.get("kpi") or {}
    try:  # le run qui tourne vraiment (suivi en direct par le listener), pas seulement la file
        en_direct = bool((direct.vue() or {}).get("en_cours"))
    except Exception:  # noqa: BLE001
        en_direct = False
    recents = []
    for r in historique.lister()[:limite]:
        ctx = r.get("contexte") or {}
        recents.append({"id": r["id"], "nom": r.get("campagne") or r.get("suite") or r["id"], "type": "Contrôle (dry-run)" if r.get("dry_run") else "Exécution",
                        "plateforme": r.get("plateforme") or ctx.get("plateforme", ""), "environnement": ctx.get("environnement", ""),
                        "version": ctx.get("version_application", ""), "statut": r.get("statut", ""), "passes": r.get("passes", 0),
                        "echecs": r.get("echecs", 0), "debut": r.get("debut", ""), "fin": r.get("fin", ""), "xray": r.get("xray")})
    return {"compteurs": {"en_cours": int(bool(k.get("en_cours") or v.get("en_cours") or en_direct)), "en_file": len(v.get("file") or []),
                          "executions": len(recents), "reussies": sum(r["statut"] not in ("échec", "erreur", "arrêté") and not r["echecs"] for r in recents),
                          "en_echec": sum(r["statut"] in ("échec", "erreur") or bool(r["echecs"]) for r in recents),
                          "tests_passes": sum(r["passes"] or 0 for r in recents), "tests_echoues": sum(r["echecs"] or 0 for r in recents)},
            "en_cours": v.get("en_cours"), "file": v.get("file") or [], "recents": recents}


# --------------------------------------------------------------------------- processus d'une release
ETAPES_RELEASE = (("note", "Release Note analysée"), ("build", "Build reçu"), ("perimetre", "Périmètre validé"),
                  ("plan", "Test Plan Xray"), ("execution", "Test Execution Xray"), ("lancement", "Exécution lancée"),
                  ("resultats", "Résultats dans Xray"), ("verdict", "Verdict du build"))


def processus_release(rid: str, bid: str = "") -> dict:
    """La release comme un processus : de la Release Note à la Test Execution Xray, rangée dans le Test Plan de la
    release, exécutée, résultats écrits dans Xray, verdict du build. Chaque étape est faite ou non d'après les données
    (jamais déclarée) ; la première non faite est l'étape courante, avec l'action qui la fait avancer. Lecture seule."""
    from atelier.intelligence import builds, plan_release, releases

    r = releases._lire(rid)
    bs = r.get("builds") or []
    b = next((x for x in bs if x["id"] == bid), None) if bid else (bs[-1] if bs else None)
    try:
        etat = plan_release.etat(rid)
    except Exception as e:  # noqa: BLE001 — Xray non configuré : le processus reste lisible, l'étape le dira
        etat = {"plan": (r.get("plan") or {}).get("xray"), "executions": [dict(x, compte={}) for x in (r.get("plan") or {}).get("executions") or []],
                "environnements": [], "erreur": str(e)[:300]}
    execs = [e for e in etat["executions"] if b and e["build"] == b["id"]]
    campagnes = [c for c in (b or {}).get("campagnes") or [] if c.get("execution")]
    a_faire = sum((e.get("compte") or {}).get("TO DO", len(e["tests"])) for e in execs)
    faits = {"note": bool(r.get("evolutions")), "build": bool(b), "perimetre": bool(b and b.get("perimetre_valide")),
             "plan": bool(etat.get("plan")), "execution": bool(execs), "lancement": bool(campagnes),
             "resultats": bool(execs) and a_faire == 0, "verdict": bool(b and b.get("statut") in ("Passed", "Failed"))}
    details = {"note": f"{len(r.get('evolutions') or [])} évolution(s)",
               "build": f"build {b['numero']}" if b else "",
               "perimetre": f"{len((b or {}).get('perimetre_valide', {}).get('tests') or [])} test(s) retenu(s)" if faits["perimetre"] else "",
               "plan": (etat.get("plan") or {}).get("cle", ""),
               "execution": ", ".join(f"{e['xray']['cle']}" + (f" ({e['environnement']})" if e.get("environnement") else "") for e in execs),
               "lancement": f"{len(campagnes)} campagne(s)" if campagnes else "",
               "resultats": f"{a_faire} test(s) encore à exécuter" if execs and a_faire else "tous les tests ont un statut" if execs else "",
               "verdict": (b or {}).get("statut", "") if faits["verdict"] else ""}
    courante = next((k for k, _ in ETAPES_RELEASE if not faits[k]), "")
    return {"release": {k: r.get(k, "") for k in ("id", "nom", "version", "statut")},
            "build": {k: b.get(k) for k in ("id", "numero", "statut")} if b else None, "builds": [{"id": x["id"], "numero": x["numero"], "statut": x["statut"]} for x in bs],
            "etapes": [{"id": k, "libelle": lib, "fait": faits[k], "courante": k == courante, "detail": details[k]} for k, lib in ETAPES_RELEASE],
            "courante": courante, "plan": etat.get("plan"), "executions": execs, "environnements": etat.get("environnements") or [],
            "campagnes": campagnes, "xray_erreur": etat.get("erreur", ""),
            "decoupages": plan_release.DECOUPAGES, "categories": builds.CATEGORIES}


# --------------------------------------------------------------------------- session assistée en direct
def session_en_direct(sid: str) -> dict:
    """Ce que la session a capturé jusqu'ici : durée effective, compteurs, derniers événements (lecture seule)."""
    import time
    from datetime import datetime

    from atelier.discovery import sessions_discovery

    s = sessions_discovery.resultats(sid)
    tl = s.get("timeline") or []
    duree = 0.0
    for p in s.get("periodes") or []:
        fin = p.get("t1") or (time.time() if s["statut"] == "En cours" else p.get("t0", 0))
        duree += max(0.0, fin - p.get("t0", fin))
    r = s.get("resultats") or {}
    return {"id": s["id"], "statut": s["statut"], "parcours": s["config"].get("parcours", ""),
            "plateforme": s["config"].get("plateforme", ""), "device": s["config"].get("device", ""),
            "environnement": s["config"].get("environnement", ""), "duree_s": int(duree),
            "compteurs": {"ecrans": len({e.get("ecran") for e in tl if e.get("ecran")}),
                          "nouveaux_ecrans": sum(1 for e in tl if e.get("type") == "ecran" and e.get("nouveau")),
                          "actions": sum(1 for e in tl if e.get("type") == "action"),
                          "transitions": sum(1 for e in tl if e.get("type") == "transition"),
                          "annotations": s.get("annotations", 0), "sensibles": s.get("sensibles", 0)},
            "resultats": r if s["statut"] == "Terminée" else None,
            "evenements": [{"type": e.get("type"), "detail": e.get("detail", ""), "t": e.get("t") or e.get("date", "")}
                           for e in tl[-20:]][::-1],
            "lu": datetime.now().astimezone().isoformat(timespec="seconds")}
