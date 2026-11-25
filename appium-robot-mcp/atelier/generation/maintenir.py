"""Maintenance d'un test en échec, du Kanban à la merge request.

Un test dont le dernier run réel échoue arrive dans la colonne « À maintenir ». L'automaticien qualifie la cause
(suggestion de Failure Analysis à partir du message d'échec) :
- « test » : le test est à maintenir (script, locator, attente, scénario) → maintenance par le MCP : l'agent reproduit
  (run_tests), diagnostique à l'écran, corrige les pages et locators, et le scénario BDD s'il ne correspond plus à
  l'application (maintenance_modifier_bdd, jamais pour masquer une anomalie), vérifie en run réel, puis rend compte
  (maintenance_rapporter). L'atelier relance ensuite le dry-run et le run réel ;
- « application » : anomalie de l'application, le test est juste : il attend la correction (un run réussi le libère) ;
- « donnees » : donnée de test à changer (jeu de données du ticket), puis relancer ;
- « environnement » : service ou environnement indisponible : relancer plus tard.

Corrigé (run réel réussi après le début de la maintenance), le test attend la confirmation de l'automaticien. Confirmer
la résolution (décision humaine) : scénario validé, suites approuvées, Gherkin mis à jour dans Xray si le scénario a
changé (test déjà publié), code commité (generation/versionnement) ; puis la merge request (revue humaine et 3
exécutions stables, ou dérogation justifiée). Refuser relance la maintenance avec un commentaire.

Rien de cassé ailleurs : au début de la maintenance, l'atelier relève l'empreinte des fichiers dont dépend le test
(suite, pages de keywords, locators) et dit à l'agent quels autres tests les partagent. Si un fichier partagé change,
tous les tests qui en dépendent sont « impactés » : ils vont dans « À maintenir » jusqu'à un run réel réussi après le
changement, le run de vérification de l'atelier les inclut, et la confirmation est refusée tant qu'un seul échoue ou
n'a pas été rejoué.

L'état vit dans la fiche du scénario BDD (bdd/<cle>.yaml) : « maintenance » (en cours) et « maintenances » (historique,
drapeau « maintenu » du ticket) ; il est donc versionné avec le test."""
from __future__ import annotations

from datetime import datetime

CAUSES = {
    "test": "Le test est à maintenir (script, locator, attente, scénario)",
    "donnees": "Donnée de test à changer",
    "application": "Anomalie de l'application",
    "environnement": "Environnement ou service indisponible",
}
IMPACT = "impact"  # test touché par la maintenance d'un autre (fichier partagé modifié) : à rejouer
# catégories de Failure Analysis → cause du Kanban
_CATEGORIE_CAUSE = {"Locator Issue": "test", "Automation Defect": "test", "Timing Issue": "test", "Test Design Issue": "test",
                    "Assertion Issue": "test", "Framework Issue": "test", "Test Data Issue": "donnees",
                    "Application Defect": "application", "Environment Issue": "environnement", "Network Issue": "environnement",
                    "Blocked": "environnement"}
ETATS = {"a_qualifier": "à qualifier", "en_correction": "l'agent corrige", "echec_correction": "correction à reprendre",
         "a_confirmer": "corrigé : à confirmer", "application": "anomalie de l'application", "donnees": "donnée à changer",
         "environnement": "environnement indisponible", "impacte": "impacté par une maintenance : à rejouer"}

CONSIGNE = """Maintenance du test « {titre} » (scénario BDD {cle}), demandée depuis le Kanban de l'atelier.
Cause qualifiée par l'automaticien : {cause}.{commentaire}

Méthode :
1. Reproduire l'échec : run_tests(tests=[…]) sur les tests ci-dessous, en run réel.
2. Diagnostiquer à l'écran (screenshot, get_screen_elements, check_locator) et corriger dans les pages et les locators,
   jamais dans la suite ; réutiliser les keywords existants (studio_rapprocher_etapes).
3. Si le scénario BDD ne correspond plus à l'application (écran, libellé, enchaînement qui ont changé), le corriger avec
   maintenance_modifier_bdd(cle="{cle}", gherkin=…, raison=…), puis aligner le script (studio_scenario_bdd). Jamais pour
   faire passer un test sur une anomalie de l'application : dans ce cas, s'arrêter et le dire (cause « application »).
4. Vérifier en run réel (run_tests) jusqu'au succès : un dry run ne vérifie rien.
   RIEN NE DOIT CASSER AILLEURS : préférer une correction propre à ce test. Si un keyword, une page ou un locator
   partagé doit changer, relancer en run réel TOUS les tests qui en dépendent (liste ci-dessous) et les réparer aussi ;
   l'atelier détecte chaque fichier partagé modifié, met ses tests en maintenance et les rejoue avant toute confirmation.
5. studio_soumettre_revue pour chaque suite modifiée, puis maintenance_rapporter(cle="{cle}", cause=…, resume=…,
   fichiers=[…]) : ce qui était cassé, ce qui a changé et pourquoi, et les autres tests rejoués. L'automaticien confirme
   ensuite la résolution.
{partages}
"""


def _maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _date(x) -> float:
    try:
        return datetime.fromisoformat(str(x)[:19].replace(" ", "T")).timestamp()
    except ValueError:
        return 0.0


def suggestion(message: str) -> dict:
    """Cause probable d'un échec, d'après les règles de Failure Analysis (avec sa force et son explication)."""
    from atelier.execution import echecs

    for h in echecs.hypotheses(message or ""):
        cause = _CATEGORIE_CAUSE.get(h.get("categorie", ""))
        if cause:
            return {"cause": cause, "libelle": CAUSES[cause], "categorie": h["categorie"], "force": h.get("force", ""),
                    "explication": h.get("explication", "")}
    return {"cause": "", "libelle": "", "categorie": "Unknown", "force": "", "explication": "Aucune règle ne reconnaît ce message."}


def _travail(tid: str) -> dict | None:
    from atelier.execution import orchestrateur

    try:
        return orchestrateur.obtenir(tid) if tid else None
    except KeyError:
        return None


def etat(m: dict, dernier_run: dict | None) -> dict | None:
    """État de maintenance d'un test pour le Kanban (None : rien à maintenir). « colonne » : le ticket va dans « À maintenir »."""
    mt = m.get("maintenance") or {}
    echec = bool(dernier_run and dernier_run.get("statut") not in ("PASS", "SKIP"))
    fin = _date((dernier_run or {}).get("fin", ""))
    if not mt or mt.get("etat") == "resolu":
        if echec and fin > _date(mt.get("resolu_le", "")):
            return {"etat": "a_qualifier", "libelle": ETATS["a_qualifier"], "colonne": True, "suggestion": suggestion(dernier_run.get("message", ""))}
        return None
    base = {"cause": mt.get("cause", ""), "cause_libelle": CAUSES.get(mt.get("cause", ""), ""), "commentaire": mt.get("commentaire", ""),
            "depuis": mt.get("depuis", ""), "travail": mt.get("travail", ""), "rapport": mt.get("rapport"), "colonne": True,
            "bdd_modifie": bool(mt.get("gherkin_avant")) and _gherkin(m) != mt.get("gherkin_avant"), "bdd_raison": mt.get("bdd_raison", ""),
            "impacts": mt.get("impacts")}
    reussi_depuis = bool(dernier_run) and not echec and fin >= _date(mt.get("depuis", ""))
    if mt.get("cause") == IMPACT:
        if reussi_depuis:  # rejoué avec succès après le changement du fichier partagé
            return None
        return {**base, "etat": "impacte", "libelle": ETATS["impacte"], "source": mt.get("source", ""), "fichiers": mt.get("fichiers", [])}
    if mt.get("cause") != "test":
        if reussi_depuis:  # l'application, la donnée ou l'environnement est revenu : le test repasse, plus rien à faire
            return None
        return {**base, "etat": mt["cause"], "libelle": ETATS[mt["cause"]]}
    t = _travail(mt.get("travail", ""))
    if t and t["statut"] in ("a_faire", "en_cours"):
        e = next((x for x in t["etapes"] if x["statut"] not in ("fait", "annule")), None)
        return {**base, "etat": "en_correction", "libelle": f"{ETATS['en_correction']} · {(e or {}).get('titre', '')}".strip(" ·")}
    if reussi_depuis:
        return {**base, "etat": "a_confirmer", "libelle": ETATS["a_confirmer"]}
    erreur = next((x.get("erreur") for x in (t or {}).get("etapes", []) if x.get("erreur")), "") if t else ""
    return {**base, "etat": "echec_correction", "libelle": ETATS["echec_correction"], "erreur": (erreur or "le run réel échoue encore")[:300]}


# =========================================================================== impacts : rien de cassé ailleurs
def _empreinte(f: str) -> str:
    import hashlib

    from atelier.domain import projet

    try:
        return hashlib.sha256(projet.safe_path(f).read_bytes()).hexdigest()[:16]
    except (OSError, ValueError):
        return ""


def _dependances() -> tuple[dict, dict]:
    """{test: fichiers dont il dépend} pour tout le dépôt, et {test: scénario BDD qui le porte}."""
    from atelier.execution.depot_robot import lire_depot
    from atelier.generation import lots, maintenance

    inv = lire_depot()
    deps = {}
    for tid in inv["tests"]:
        try:
            deps[tid] = maintenance._fichiers_du_test(inv, tid)
        except Exception:  # noqa: BLE001 — test illisible : sans dépendances connues
            deps[tid] = set()
    par_bdd, _ = lots._index_tests()
    bdd_de = {t["id"]: c for c, ts in par_bdd.items() for t in ts}
    return deps, bdd_de


def partages(tests: list[str]) -> dict:
    """Fichiers dont dépendent ces tests et, pour chacun, les AUTRES tests qui en dépendent aussi."""
    deps, _ = _dependances()
    fichiers = set().union(*[deps.get(t, set()) for t in tests]) if tests else set()
    autres = {f: sorted(t for t, d in deps.items() if f in d and t not in tests) for f in sorted(fichiers)}
    return {"fichiers": {f: _empreinte(f) for f in sorted(fichiers)}, "autres": autres}


def detecter_impacts(cle: str) -> dict:
    """Fichiers partagés modifiés depuis le début de la maintenance et tests qui en dépendent (hors ceux du ticket) :
    chacun passe « impacté » (À maintenir) jusqu'à un run réel réussi ; la liste est gardée dans la maintenance."""
    from atelier.generation import bdd, lots

    m = _charger(cle)
    mt = m.get("maintenance") or {}
    avant = mt.get("empreintes") or {}
    if not avant:
        return {"fichiers": [], "tests": [], "bdd": []}
    par_bdd, _ = lots._index_tests()
    propres = {t["id"] for t in par_bdd.get(cle) or []}
    changes = sorted(f for f, h in avant.items() if _empreinte(f) != h)
    deps, bdd_de = _dependances()
    tests = sorted(t for t, d in deps.items() if t not in propres and d & set(changes))
    maintenant = _maintenant()
    scenarios = []
    for tid in tests:
        c = bdd_de.get(tid)
        if not c or c == cle or c in scenarios:
            continue
        autre = bdd.charger(c) or {}
        ouverte = autre.get("maintenance") or {}
        if ouverte.get("etat") not in (None, "resolu") and ouverte.get("cause") != IMPACT:
            continue  # déjà en maintenance pour sa propre cause : on ne l'écrase pas
        fichiers = sorted(set(changes) & deps.get(tid, set()))
        if ouverte.get("cause") == IMPACT and ouverte.get("source") == cle and ouverte.get("fichiers") == fichiers:
            scenarios.append(c)
            continue  # déjà marqué pour ces fichiers : sa date de référence ne bouge pas
        autre["maintenance"] = {"etat": "impacte", "cause": IMPACT, "source": cle, "fichiers": fichiers, "depuis": maintenant}
        bdd.sauver(autre)
        scenarios.append(c)
    mt = (_charger(cle).get("maintenance") or {})
    mt["impacts"] = {"fichiers": changes, "tests": tests, "bdd": scenarios, "detecte_le": maintenant if changes else ""}
    m = _charger(cle)
    m["maintenance"] = mt
    bdd.sauver(m)
    return mt["impacts"]


def impacts_a_rejouer(cle: str) -> list[dict]:
    """Tests impactés sans run réel réussi depuis le changement du fichier partagé (bloquent la confirmation)."""
    from atelier.execution import robot

    mt = (_charger(cle).get("maintenance") or {})
    imp = mt.get("impacts") or {}
    if not imp.get("tests"):
        return []
    reels = robot.derniers_resultats("results", reels=True)
    depuis = _date(imp.get("detecte_le") or mt.get("depuis", ""))
    out = []
    for tid in imp["tests"]:
        d = reels.get(tid)
        if not d or d.get("statut") != "PASS" or _date(d.get("fin", "")) < depuis:
            out.append({"test": tid, "statut": (d or {}).get("statut", "pas rejoué"), "fin": (d or {}).get("fin", "")})
    return out


def _gherkin(m: dict) -> str:
    from atelier.generation import bdd

    try:
        return bdd.serialiser(m)
    except Exception:  # noqa: BLE001
        return ""


def _charger(cle: str) -> dict:
    from atelier.generation import bdd

    return bdd._exiger(cle)


def qualifier(cle: str, cause: str, commentaire: str = "") -> dict:
    """Décision de l'automaticien sur la cause de l'échec. « test » lance la maintenance par le MCP."""
    from atelier.generation import bdd

    if cause not in CAUSES:
        raise ValueError("Cause : " + ", ".join(CAUSES))
    if cause == "test":
        return maintenir(cle, commentaire)
    m = _charger(cle)
    m["maintenance"] = {"etat": "qualifie", "cause": cause, "commentaire": commentaire.strip(), "depuis": _maintenant(), "par": "automaticien"}
    bdd.sauver(m)
    return {"cle": cle, "cause": cause}


def maintenir(cle: str, commentaire: str = "") -> dict:
    """Maintenance par le MCP : l'agent reproduit, corrige (scripts et, si besoin, scénario BDD) et vérifie ; puis
    dry-run et run réel par l'atelier. Le commentaire de l'automaticien (ce qu'il faut corriger) est transmis à l'agent."""
    from atelier.generation import bdd, kanban, maintenance

    c = kanban._ticket(cle)
    if c["type"] != "test" or not c["tests"]:
        raise ValueError("Pas encore automatisé : rien à maintenir.")
    kanban._deja_en_cours(c)
    m = _charger(cle)
    p = partages(c["tests"])
    lignes = [f"- {f} : aussi utilisé par {len(a)} autre(s) test(s)" + (" : " + ", ".join(a[:8]) + (" …" if len(a) > 8 else "") if a else "")
              for f, a in p["autres"].items() if a]
    texte = CONSIGNE.format(titre=c["titre"], cle=cle, cause=CAUSES["test"],
                            commentaire=f"\nCe qu'il faut corriger, selon l'automaticien : {commentaire.strip()}" if commentaire.strip() else "",
                            partages=("\nFichiers partagés avec d'autres tests (une modification les impacte tous) :\n" + "\n".join(lignes) + "\n")
                            if lignes else "\nAucun fichier de ce test n'est partagé avec un autre test.\n")
    d = maintenance.demande_maintenance(c["tests"], commentaire)
    r = kanban._travail(f"Maintenir « {c['titre']} »", [
        {"titre": "Maintenance par l'agent (MCP)", "type": "ia", "params": {"texte": texte + d["texte"],
                                                                           "attendus": ["run_tests", "maintenance_rapporter"]}},
        {"titre": "Dry-run", "type": "atelier", "action": "dry_run", "params": {"bdd": cle, "tests": c["tests"]}},
        {"titre": "Run réel (téléphone), tests impactés compris", "type": "atelier", "action": "run",
         "params": {"bdd": cle, "tests": c["tests"], "impacts_de": cle}}], cle, "maintenance")
    precedent = m.get("maintenance") or {}
    m["maintenance"] = {"etat": "en_correction", "cause": "test", "commentaire": commentaire.strip(), "depuis": _maintenant(), "par": "automaticien",
                        "travail": r["travail"], "gherkin_avant": precedent.get("gherkin_avant") if precedent.get("etat") in ("en_correction", "refuse") else _gherkin(m),
                        "tentatives": int(precedent.get("tentatives") or 0) + 1 if precedent.get("etat") in ("en_correction", "refuse") else 1,
                        # empreintes d'avant : gardées d'une tentative à l'autre (un changement reste un changement)
                        "empreintes": precedent.get("empreintes") if precedent.get("etat") in ("en_correction", "refuse") and precedent.get("empreintes")
                        else p["fichiers"], "impacts": precedent.get("impacts") if precedent.get("etat") in ("en_correction", "refuse") else None}
    bdd.sauver(m)
    return {"cle": cle, **r}


def _ouverte(cle: str) -> tuple[dict, dict]:
    m = _charger(cle)
    mt = m.get("maintenance") or {}
    if mt.get("cause") != "test" or mt.get("etat") == "resolu":
        raise PermissionError(f"Aucune maintenance en cours sur {cle} : elle se demande depuis le ticket du Kanban.")
    return m, mt


def modifier_bdd(cle: str, gherkin: str, raison: str, source: str = "agent") -> dict:
    """Pendant une maintenance seulement : le scénario BDD est réécrit (liens des étapes inchangées conservés) ; la
    version d'avant est gardée pour la confirmation, la raison est montrée à l'automaticien."""
    from atelier.generation import bdd

    if len((raison or "").strip()) < 10:
        raise ValueError("Raison obligatoire : ce qui a changé dans l'application et justifie de modifier le scénario.")
    _m, mt = _ouverte(cle)
    nouveau = bdd.depuis_texte(cle, gherkin)
    nouveau["maintenance"] = {**mt, "bdd_raison": raison.strip()[:500], "bdd_par": source, "bdd_le": _maintenant()}
    bdd.sauver(nouveau)
    return {"cle": cle, "modifie": _gherkin(nouveau) != mt.get("gherkin_avant"), "gherkin": _gherkin(nouveau), "statut": nouveau.get("statut"),
            "controles": [c for c in bdd.controles(nouveau) if c["gravite"] == "haute"]}


def rapporter(cle: str, cause: str, resume: str, fichiers: list[str] | None = None, source: str = "agent") -> dict:
    """Compte rendu de l'agent à la fin de la maintenance : cause constatée, ce qui a changé et pourquoi."""
    from atelier.generation import bdd

    if not (resume or "").strip():
        raise ValueError("Résumé obligatoire.")
    detecter_impacts(cle)
    m, mt = _ouverte(cle)
    mt["rapport"] = {"cause": cause if cause in CAUSES else "test", "resume": resume.strip()[:2000], "fichiers": [str(f) for f in fichiers or []][:50],
                     "par": source, "date": _maintenant()}
    m["maintenance"] = mt
    bdd.sauver(m)
    return {"cle": cle, "rapport": mt["rapport"], "impacts": mt.get("impacts"),
            "suite": "L'automaticien confirme la résolution dans le ticket du Kanban ; les tests impactés doivent repasser en run réel."}


def confirmer(cle: str, xray=None) -> dict:
    """Décision de l'automaticien : la correction est bonne. Scénario validé, suites approuvées, Gherkin mis à jour
    dans Xray si le scénario a changé et que le test y est publié, code commité ; drapeau « maintenu »."""
    from atelier.generation import bdd, flux, kanban, studio, versionnement

    c = kanban._ticket(cle)
    m = _charger(cle)
    e = etat(m, c.get("dernier_run"))
    if not e or e["etat"] != "a_confirmer":
        raise ValueError("Rien à confirmer : la confirmation suit un run réel réussi après la maintenance.")
    detecter_impacts(cle)
    restants = impacts_a_rejouer(cle)
    if restants:
        raise ValueError(f"{len(restants)} test(s) impacté(s) par la maintenance sans run réel réussi depuis le changement : "
                         + ", ".join(f"{x['test']} ({x['statut']})" for x in restants[:6]) + ". Les rejouer (ou les réparer) avant de confirmer.")
    m = _charger(cle)
    mt = m["maintenance"]
    bdd_modifie = e["bdd_modifie"]
    if m.get("statut") not in ("validé", "valide"):
        bdd.valider(cle)
    xray_maj, git, erreurs = "", None, []
    if c.get("xray"):  # déjà dans Xray : republier met à jour le Gherkin s'il a changé, et commite le code
        p = flux.publier([cle], xray=xray)
        erreurs = p.get("erreurs") or []
        xray_maj = next((x.get("resultat", "") for x in p.get("publies") or []), "")
        git = p.get("git")
    else:
        from atelier.generation import lots

        par_bdd, _ = lots._index_tests()
        for suite in sorted({t["suite"] for t in par_bdd.get(cle) or []}):
            studio.approuver_a_la_publication(suite)
        try:
            git = versionnement.committer([cle], message=f"Maintenance : {c['titre']}")
        except Exception as ex:  # noqa: BLE001 — Git indisponible : la résolution est gardée, le commit se reprend
            git = {"erreur": str(ex)[:300]}
    if erreurs:
        raise ValueError("Xray : " + "; ".join(f"{x['scenario']} : {x['erreur']}" for x in erreurs))
    m = _charger(cle)
    entree = {"date": _maintenant(), "cause": mt.get("cause", ""), "commentaire": mt.get("commentaire", ""), "rapport": mt.get("rapport"),
              "bdd_modifie": bdd_modifie, "bdd_raison": mt.get("bdd_raison", ""), "xray": xray_maj, "commit": (git or {}).get("commit", ""),
              "branche": (git or {}).get("branche", ""), "tentatives": mt.get("tentatives", 1), "confirme_par": "automaticien",
              "impacts": mt.get("impacts")}
    m["maintenances"] = [*(m.get("maintenances") or []), entree]
    m["maintenance"] = {"etat": "resolu", "resolu_le": entree["date"]}
    bdd.sauver(m)
    return {"cle": cle, "maintenance": entree, "git": git}


def refuser(cle: str, commentaire: str) -> dict:
    """La correction ne convient pas : la maintenance repart vers l'agent avec le commentaire de l'automaticien."""
    from atelier.generation import bdd

    if len((commentaire or "").strip()) < 5:
        raise ValueError("Dire ce qui ne va pas : l'agent repart de ce commentaire.")
    m, mt = _ouverte(cle)
    m["maintenance"] = {**mt, "etat": "refuse"}
    bdd.sauver(m)
    return maintenir(cle, commentaire)


def proposer_mr(cle: str, derogation: str = "", gitlab_client=None) -> dict:
    """Merge request du code maintenu : la branche de travail part sur GitLab (revue humaine, 3 exécutions stables ou
    dérogation justifiée). Description : la dernière maintenance confirmée."""
    from atelier.generation import kanban, studio

    c = kanban._ticket(cle)
    m = _charger(cle)
    h = (m.get("maintenances") or [None])[-1]
    if not h:
        raise ValueError("Aucune maintenance confirmée sur ce test.")
    lignes = [f"Maintenance du test « {c['titre']} »" + (f" ({c['xray']})" if c.get("xray") else ""), "",
              f"- Cause : {CAUSES.get(h['cause'], h['cause'])}"]
    if h.get("commentaire"):
        lignes.append(f"- Demande de l'automaticien : {h['commentaire']}")
    if (h.get("rapport") or {}).get("resume"):
        lignes.append(f"- Correction (agent) : {h['rapport']['resume']}")
    if h.get("bdd_modifie"):
        lignes.append(f"- Scénario BDD modifié : {h.get('bdd_raison') or 'oui'}" + (f" ; Xray : {h['xray']}" if h.get("xray") else ""))
    if (h.get("impacts") or {}).get("tests"):
        lignes.append(f"- Fichiers partagés modifiés : {', '.join(h['impacts']['fichiers'])} ; {len(h['impacts']['tests'])} autre(s) test(s) "
                      "impacté(s), tous rejoués avec succès avant la confirmation")
    return studio.proposer_mr(f"Maintenance : {c['titre']}", "\n".join(lignes), derogation=derogation, gitlab_client=gitlab_client)
