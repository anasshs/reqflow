"""Tests automatisés, vue simple : où en est chaque test, le vérifier, le valider, en lancer la maintenance.

Le parcours de l'automaticien tient en quatre gestes :
  1. il demande l'automatisation (Test Design, Automation Studio) ; l'agent écrit le code ;
  2. le test apparaît ici « À valider » ;
  3. « Vérifier » l'exécute pour de vrai (Robot --test, un ou plusieurs tests, une ou plusieurs suites) ;
     « Valider » le rend exécutable partout ; « Écarter » le met de côté, avec un motif ;
  4. « Lancer la maintenance » envoie à l'agent une seule demande pour toute la sélection.

Trois états au lieu des six de la revue technique (qui reste disponible dans Automation Studio pour le détail) :
  À valider (généré, en revue, modifications demandées, ou modifié depuis la validation), Validé (approuvé ou publié),
  Écarté (refusé). Un script jamais entré en revue (patrimoine existant) est « Existant ».

Vérifié : le test a passé dans un run RÉEL postérieur à la dernière modification de sa suite et de tout ce qu'il
utilise (pages, locators, socle). Un dry run ne compte pas : il ne lance aucun keyword, donc aucune assertion.
Un test tagué consomme_donnee crée une donnée réelle à chaque run : il ne se vérifie pas avant validation (dry run et
dérogation justifiée) ; tous les autres doivent être vérifiés avant « Valider ».
"""
from __future__ import annotations

from datetime import datetime

from atelier.domain import projet

ETATS = {"Generated": "À valider", "Technical Review": "À valider", "Changes Requested": "À valider",
         "Approved": "Validé", "Published": "Validé", "Rejected": "Écarté"}
CONSOMME = "consomme_donnee"


def _date(iso: str) -> float:
    try:
        return datetime.fromisoformat(str(iso)[:19]).timestamp()
    except ValueError:
        return 0.0


def _fichiers_du_test(inv: dict, tid: str) -> set[str]:
    """La suite et tout ce dont le test dépend (pages de keywords, fichiers de locators) : une modification de l'un
    d'eux rend la vérification caduque."""
    from atelier.execution.depot_robot import dependances_test

    t = inv["tests"][tid]
    d = dependances_test(inv, tid)
    fichiers = {t["fichier"]} | {inv["keywords"][k]["fichier"] for k in d.get("keywords", []) if k in inv["keywords"]}
    locs = {(e, c) for e, c in d.get("locators", [])}
    fichiers |= {l["fichier"] for l in inv["locators"].values() if (l["ecran"], l["cle"]) in locs and l.get("fichier")}
    return fichiers


HORS_DEPOT = ("studio/", "results/")  # copies de l'atelier (versions remplacées) et sorties de runs : pas des suites


def _valide_le(revue: dict) -> float:
    """Date de la dernière validation (passage à Approved ou Published) d'une suite ; 0 si jamais validée."""
    return max((_date(h.get("date", "")) for h in revue.get("historique") or [] if h.get("vers") in ("Approved", "Published")), default=0.0)


def _modifie_le(fichiers: set[str]) -> float:
    return max((projet.safe_path(f).stat().st_mtime for f in fichiers if projet.safe_path(f).exists()), default=0.0)


def vue() -> dict:
    """Suites et tests du dépôt : état simple, dernier résultat réel, vérifié ou non, consomme une donnée ou non."""
    from atelier.execution import robot
    from atelier.execution.depot_robot import lire_depot
    from atelier.generation import studio

    inv = lire_depot()
    revues = studio.revues_scripts()
    reels = robot.derniers_resultats("results", reels=True)
    try:  # identifiant du test BDD porté en tag : il identifie le test, il ne le décrit pas (affiché à part)
        from atelier.generation import bdd

        cles_bdd = {b["cle"] for b in bdd.lister()}
    except Exception:  # noqa: BLE001 — sans scénarios BDD lisibles
        cles_bdd = set()
    suites = []
    for f in sorted({t["fichier"] for t in inv["tests"].values() if not t["fichier"].startswith(HORS_DEPOT)}):
        r = revues.get(f) or {}
        etat = ETATS.get(r.get("statut", ""), "À valider") if r.get("en_workflow") else "Existant"
        dependances = set().union(*[_fichiers_du_test(inv, k) for k, v in inv["tests"].items() if v["fichier"] == f])
        pages_modifiees = etat == "Validé" and _modifie_le(dependances - {f}) > _valide_le(r) + 1
        if pages_modifiees:  # la revue ne suit que le fichier de la suite : une page ou un locator modifié depuis compte aussi
            etat = "À valider"
        tests = []
        for tid, t in sorted(((k, v) for k, v in inv["tests"].items() if v["fichier"] == f), key=lambda x: x[1].get("ligne", 0)):
            dernier = reels.get(tid)
            modifie = _modifie_le(_fichiers_du_test(inv, tid))
            verifie = bool(dernier and dernier["statut"] == "PASS" and _date(dernier["fin"]) >= modifie - 1)
            tests.append({"id": tid, "nom": t["nom"], "tags": [x for x in t.get("tags", []) if x not in t.get("cles_xray", []) and x not in cles_bdd],
                          "cles": t.get("cles_xray", []), "consomme": CONSOMME in (t.get("tags") or []), "verifie": verifie,
                          "bdd": [x for x in t.get("tags", []) if x in cles_bdd],
                          "dernier": {k: dernier[k] for k in ("statut", "fin", "message")} if dernier else None,
                          "perime": bool(dernier) and _date(dernier["fin"]) < modifie - 1})
        suites.append({"fichier": f, "etat": etat, "statut": r.get("statut", ""), "en_workflow": bool(r.get("en_workflow")),
                       "modifie_depuis_validation": bool(r.get("modifie_depuis_validation")) or pages_modifiees, "tests": tests})
    compte = {e: sum(1 for s in suites for _ in s["tests"] if s["etat"] == e) for e in ("À valider", "Validé", "Écarté", "Existant")}
    return {"suites": suites, "compte": compte}


def cycle_bdd(v: dict | None = None) -> dict:
    """Où en est chaque test BDD après sa conception : script écrit (un test du dépôt porte sa clé en tag), suite, état de la
    suite (À valider / Validé / Écarté), tests vérifiés par un run réel. Sert aux écrans à n'offrir que l'action suivante
    (créer le BDD, générer le script, vérifier, valider) au lieu de toutes, toujours."""
    v = v or vue()
    out: dict = {}
    for s in v["suites"]:
        for t in s["tests"]:
            for cle in t.get("bdd") or []:
                c = out.setdefault(cle, {"script": True, "suites": [], "etat": s["etat"], "tests": 0, "verifies": 0})
                if s["fichier"] not in c["suites"]:
                    c["suites"].append(s["fichier"])
                c["tests"] += 1
                c["verifies"] += bool(t["verifie"])
                if s["etat"] != "Validé":  # une suite encore à valider l'emporte sur une suite validée
                    c["etat"] = s["etat"] if c["etat"] == "Validé" else c["etat"]
    for c in out.values():
        c["verifie"] = c["tests"] > 0 and c["verifies"] == c["tests"]
    return out


def etape_bdd(b: dict, c: dict | None) -> dict:
    """Étape suivante d'un test BDD (b : statut du scénario ; c : cycle_bdd) : une seule action proposée. Dès qu'un script
    existe, c'est lui qui compte (un scénario resté « brouillon » mais déjà automatisé n'est pas à refaire)."""
    if not c:
        if (b.get("statut") or "brouillon") != "validé":
            return {"etape": "valider_bdd", "libelle": "Relire et valider le scénario BDD"}
        return {"etape": "generer", "libelle": "Générer le script Robot"}
    if c["etat"] == "Validé" and c["verifie"]:
        return {"etape": "fait", "libelle": "Automatisé, vérifié et validé"}
    if not c["verifie"]:
        return {"etape": "verifier", "libelle": "Vérifier le test (run réel)"}
    return {"etape": "valider_test", "libelle": "Valider le test automatisé"}


def du_parcours(b: dict, parcours: dict) -> bool:
    """Le test BDD b vient-il de ce parcours ? Relié par l'identifiant (PU-…), le nœud (parcours:…), une de ses sessions de
    Discovery, ou à défaut par la clé que l'atelier lui a donnée à la création (parcours_<nom>, parcours_<nom>_2…)."""
    import re

    from atelier.generation import bdd

    lien = b.get("parcours") or ""
    if lien and lien in (parcours.get("id"), parcours.get("noeud")):
        return True
    if b.get("session") and b["session"] in (parcours.get("sessions_ids") or []):
        return True
    if lien or b.get("session"):
        return False
    base = bdd._slug(f"parcours_{parcours.get('nom') or ''}")
    return bool(parcours.get("nom")) and re.fullmatch(re.escape(base) + r"(_\d+)?", b.get("cle", "")) is not None


def _suites(ids: list[str]) -> list[str]:
    return list(dict.fromkeys(str(i).partition("::")[0] for i in ids or []))


def a_verifier(fichier: str, v: dict | None = None) -> list[str]:
    """Tests de la suite qui doivent passer en run réel avant « Valider » (non vérifiés, hors consomme_donnee)."""
    s = next((x for x in (v or vue())["suites"] if x["fichier"] == fichier), None)
    if s is None:
        raise KeyError(f"Suite inconnue : {fichier}")
    return [t["nom"] for t in s["tests"] if not t["consomme"] and not t["verifie"]]


def valider(ids: list[str], commentaire: str = "", derogation: str = "") -> list[dict]:
    """« Valider » : un clic pour la suite de chaque test choisi (soumettre, approuver et publier de la revue technique).
    Exige que ses tests soient vérifiés en run réel (sauf consomme_donnee) ; sinon une dérogation justifiée."""
    from atelier.generation import studio

    v = vue()
    out = []
    for f in _suites(ids):
        try:
            manquants = a_verifier(f, v)
            if manquants and len(derogation.strip()) < 10:
                raise ValueError(f"Vérifier d'abord en run réel : {', '.join(manquants)} (bouton « Vérifier »), ou justifier une dérogation.")
            s = next((x for x in v["suites"] if x["fichier"] == f), {})
            statut = (studio.revues_scripts().get(f) or {}).get("statut", "Generated")
            if s.get("etat") == "Validé":
                out.append({"fichier": f, "ok": True, "etat": "Validé", "message": "Déjà validé."})
                continue
            if statut in ("Approved", "Published"):  # pages ou locators modifiés depuis la validation : de nouveau en revue
                studio.renvoyer_en_revue([f], "pages ou locators modifiés depuis la validation")
                statut = "Technical Review"
            if statut in ("Generated", "Changes Requested", "Rejected"):  # modifiée après validation : déjà « Technical Review »
                studio.transition_script(f, "soumettre", commentaire or "à valider")
            nb = sum(1 for s in v["suites"] if s["fichier"] == f for t in s["tests"] if t["verifie"])
            preuve = derogation.strip() or f"vérifié en run réel ({nb} test(s) passé(s) après la dernière modification)"
            studio.transition_script(f, "approuver", commentaire, derogation=preuve)
            studio.transition_script(f, "publier", commentaire)
            out.append({"fichier": f, "ok": True, "etat": "Validé", "message": "Validé." + (" Dérogation : " + derogation.strip() if manquants else "")})
        except (ValueError, PermissionError, KeyError) as e:
            out.append({"fichier": f, "ok": False, "etat": "À valider", "message": str(e)})
    return out


def ecarter(ids: list[str], motif: str) -> list[dict]:
    from atelier.generation import studio

    if len(str(motif or "").strip()) < 5:
        raise ValueError("Motif obligatoire pour écarter un test.")
    out = []
    for f in _suites(ids):
        try:
            studio.transition_script(f, "refuser", motif.strip())
            out.append({"fichier": f, "ok": True, "etat": "Écarté", "message": "Écarté."})
        except (ValueError, PermissionError, KeyError) as e:
            out.append({"fichier": f, "ok": False, "etat": "", "message": str(e)})
    return out


def controle_verification(ids: list[str]) -> dict:
    """Run réel de tests précis : permis sans validation (c'est la vérification) tant qu'aucun ne crée de donnée réelle.
    Un test consomme_donnee dans une suite non validée : il faut valider d'abord (dry run + dérogation)."""
    v = vue()
    par_id = {t["id"]: (s, t) for s in v["suites"] for t in s["tests"]}
    choisis = [t for i in ids for t in ([par_id[i][1]] if i in par_id else [x for s in v["suites"] if s["fichier"] == i for x in s["tests"]])]
    bloquants = [t["nom"] for t in choisis if t["consomme"] and next(s for s in v["suites"] if t["id"] in [x["id"] for x in s["tests"]])["etat"]
                 not in ("Validé", "Existant")]
    return {"tests": [t["id"] for t in choisis], "bloquants": bloquants}


NOM_JOB_VERIFICATION = "Vérification"  # nom du job mis en file par Tests automatisés › Vérifier


def executions_verification(limite: int = 3) -> dict:
    """Suivi des vérifications depuis l'écran Tests automatisés : celle en cours (avec ses tests, pour les marquer « en
    cours »), celles en file d'attente, et les dernières terminées avec leur statut et, si le run n'a pas pu se lancer
    (données, erreur de lecture d'un fichier…), le message d'erreur. Chaque entrée porte l'identifiant du run, que
    l'écran Exécution (#execution/<id>) sait afficher."""
    from atelier.execution import centre, historique

    job = centre.FILE.en_cours or {}
    en_cours = None
    if job.get("nom") == NOM_JOB_VERIFICATION:
        en_cours = {"id": job.get("id", ""), "etat": job.get("etat", ""), "entre_le": job.get("entre_le", ""),
                    "tests": list((job.get("params") or {}).get("tests") or [])}
    attente = [{"id": j.get("id", ""), "entre_le": j.get("entre_le", "")} for j in centre.FILE.attente()
               if j.get("nom") == NOM_JOB_VERIFICATION]
    actifs = {x["id"] for x in attente} | ({en_cours["id"]} if en_cours else set())
    recents = [{k: r.get(k) for k in ("id", "debut", "fin", "statut", "passes", "echecs", "erreur")} | {"nb_tests": len(r["tests"])}
               for r in historique.lister(30) if r.get("tests") and r.get("fin") and r["id"] not in actifs][:limite]
    return {"en_cours": en_cours, "attente": attente, "recents": recents}


def demande_maintenance(ids: list[str], consigne: str = "") -> dict:
    """Une seule demande à l'agent (Cursor, Claude Code) pour toute la sélection : derniers résultats réels, corrections de
    locators proposées par l'atelier, contrôles de la revue en écart, et la méthode imposée."""
    from atelier.generation import studio, studio_avance

    v = vue()
    par_id = {t["id"]: t for s in v["suites"] for t in s["tests"]}
    tests = [par_id[i] for i in ids if i in par_id] + [t for s in v["suites"] if s["fichier"] in ids for t in s["tests"]]
    tests = list({t["id"]: t for t in tests}.values())
    if not tests:
        raise ValueError("Aucun test choisi.")
    suites = _suites([t["id"] for t in tests])
    lignes = [f"Maintenance de {len(tests)} test(s), choisis dans l'atelier (Tests automatisés)."]
    if consigne.strip():
        lignes += ["", "Consigne de l'automaticien : " + consigne.strip()]
    lignes += ["", "Tests (identifiant · dernier résultat réel) :"]
    for t in tests:
        d = t["dernier"]
        etat = (f"{d['statut']} le {d['fin'][:16].replace('T', ' ')}" + (" (antérieur à la dernière modification)" if t["perime"] else "")
                + (f" — {d['message']}" if d.get("message") else "")) if d else "jamais exécuté en run réel"
        lignes.append(f"- {t['id']} · {etat}" + (" · consomme_donnee : ne pas l'exécuter sans mon accord" if t["consomme"] else ""))
    try:
        from atelier.execution.depot_robot import dependances_test, lire_depot

        inv = lire_depot()
        utilises = {tuple(x) for t in tests if t["id"] in inv["tests"] for x in dependances_test(inv, t["id"]).get("locators", [])}
        corr = [c for c in studio_avance.propositions_correction() if (c["ecran"], c["cle"]) in utilises][:10]
    except Exception:  # noqa: BLE001 — sans historique de runs : pas de proposition
        corr = []
    if corr:
        lignes += ["", "Corrections de locators proposées par l'atelier (studio_corrections_locators) :"]
        lignes += [f"- {c['id']} : {c['valeur']} → {c.get('proposition') or '?'} ({c.get('source', '')})" for c in corr]
    for f in suites:
        ecarts = [c for c in studio.controles_script(f) if c["gravite"] not in ("ok", "info")]
        if ecarts:
            lignes += ["", f"Revue de {f}, écarts à corriger :"] + [f"- {c['code']} : {c['message']}" for c in ecarts]
    lignes += ["", "Méthode (règles atelier-automatisation et atelier-robot-expert) :",
               "1. Reproduire : run_tests(tests=[…]) sur ces identifiants (jamais un test consomme_donnee sans mon accord).",
               "2. Diagnostiquer chaque échec à l'écran (session web, check_locator, screenshot) ; corriger dans les pages et les "
               "locators, jamais dans la suite ; réutiliser les keywords existants (studio_rapprocher_etapes).",
               "3. Vérifier en run réel chaque test corrigé (run_tests) : un dry run ne lance aucun keyword, il ne vérifie aucune "
               "assertion.",
               "4. studio_soumettre_revue pour chaque suite modifiée, puis résumer ce qui a changé et pourquoi. Je valide dans "
               "l'atelier (Tests automatisés)."]
    return {"titre": f"Maintenance : {len(tests)} test(s)", "texte": "\n".join(lignes), "tests": [t["id"] for t in tests],
            "attendus": ["run_tests", "studio_soumettre_revue"]}
