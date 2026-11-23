"""Runs Robot Framework : lancement (JDD vérifiés avant, listeners Xray et cartographie), bilan
d'un output.xml. Une indisponibilité Xray / Jira / carte n'interrompt jamais un run."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from atelier.discovery import carte, session
from atelier.domain import evenements, projet
from atelier.execution import jdd

LISTENERS = Path(__file__).resolve().parent / "listeners"
EN_COURS: dict = {"proc": None, "arret": False}


def env_robot(base: dict | None = None) -> dict:
    """Environnement du processus Robot. PYTHONIOENCODING « encodage:erreurs » (ex. utf-8:surrogateescape, que posent
    certains terminaux et agents) est valide pour Python, mais une partie de la chaîne Robot le prend pour un nom
    d'encodage : LookupError à chaque message, erreur en boucle, run bloqué sans output.xml. Seul l'encodage est gardé."""
    env = dict(os.environ if base is None else base)
    v = env.get("PYTHONIOENCODING", "")
    if ":" in v:
        env["PYTHONIOENCODING"] = v.split(":", 1)[0] or "utf-8"
    return env


def environnement_des_jeux(target: str, fichiers: list[str] | None = None) -> dict:
    """Run lancé sans environnement de données alors que la suite utilise &{JDD_<NOM>} : sans injection, Robot échoue
    sur « Variable '&{JDD_…}' not found » avant la première étape. Un seul environnement porte tous les jeux référencés :
    il est retenu ({"env"}). Aucun, ou plusieurs : le run n'est pas lancé ({"bloque": conseil}). Suite sans JDD : {}."""
    import re

    cibles = fichiers or [target]
    chemins = [p for c in cibles for p in ([projet.safe_path(c)] if projet.safe_path(c).is_file() else projet.safe_path(c).rglob("*.robot"))]
    noms = sorted({n for f in chemins for n in re.findall(r"JDD_([A-Z0-9_]+)", f.read_text("utf-8", errors="ignore"))})
    if not noms:
        return {}
    complets = [e for e in jdd.environnements() if not any(jdd.detecter(c, e)["inconnus"] for c in cibles)]
    if len(complets) == 1:
        return {"env": complets[0], "references": noms}
    jeux = ", ".join(f"JDD_{n}" for n in noms)
    return {"references": noms, "bloque": (
        f"La suite utilise {jeux} : choisir l'environnement des données ({', '.join(complets)}) avant de lancer le run."
        if complets else f"La suite utilise {jeux}, absent(s) de data/jdd : créer le jeu (Discovery › Données › Jeu de données "
                         "des tests) ou corriger la suite.")}


def selection_tests(ids: list[str]) -> dict:
    """Tests choisis un par un (« <fichier>::<nom du test> », identifiants de l'inventaire) : fichiers à passer à Robot,
    noms pour --test, et cible commune (fichier ou dossier) pour le bilan et l'historique. Un identifiant sans « :: »
    désigne toute la suite."""
    fichiers, noms, entiers = [], [], set()
    for i in ids or []:
        f, _, nom = str(i).partition("::")
        f = projet.safe_path(f).relative_to(projet.PROJECT_DIR).as_posix()
        if not projet.safe_path(f).is_file():
            raise FileNotFoundError(f"Suite introuvable : {f}")
        if f not in fichiers:
            fichiers.append(f)
        if nom:
            noms.append(nom)
        else:
            entiers.add(f)
    if not fichiers:
        raise ValueError("Aucun test choisi.")
    if entiers and noms:  # --test filtrerait aussi les suites choisies entières
        raise ValueError("Choisir des suites entières, ou des tests précis, pas les deux dans le même run.")
    cible = fichiers[0] if len(fichiers) == 1 else Path(os.path.commonpath(fichiers)).as_posix()
    return {"fichiers": fichiers, "noms": list(dict.fromkeys(noms)), "cible": cible}


def arreter_run() -> str:
    """Demande l'arrêt du run en cours. Linux / macOS : SIGINT, Robot termine proprement et écrit output.xml.
    Windows : un sous-processus ne peut pas recevoir SIGINT ; le run est interrompu (rapport Robot possiblement absent)."""
    import signal
    import sys

    proc = EN_COURS.get("proc")
    if not proc or proc.poll() is not None:
        return "Aucun run en cours."
    EN_COURS["arret"] = True
    if sys.platform == "win32":
        proc.terminate()
        return "Arrêt demandé : le run est interrompu (sous Windows, le rapport Robot du test en cours peut manquer)."
    proc.send_signal(signal.SIGINT)
    return "Arrêt demandé : le test en cours se termine, puis le rapport est écrit."


def deepest_fail(item, path: list[str]) -> list[str]:
    for child in getattr(item, "body", []) or []:
        if getattr(child, "status", None) == "FAIL":
            name = getattr(child, "name", None) or type(child).__name__
            return deepest_fail(child, path + [str(name)])
    return path


def parse_robot_output(output_xml: str = "results/mcp/output.xml") -> dict:
    """Résumé d'un output.xml : stats + tests en échec avec message et keyword fautif."""
    from robot.api import ExecutionResult

    result = ExecutionResult(str(projet.safe_path(output_xml)))
    total = result.statistics.total
    failures = []
    for test in result.suite.all_tests:
        if test.status == "FAIL":
            failures.append({"test": test.name, "tags": list(test.tags),
                             "message": test.message[:800],
                             "keyword_en_echec": " > ".join(deepest_fail(test, []))})
    return {"passes": total.passed, "echecs": total.failed,
            "skips": getattr(total, "skipped", 0), "tests_en_echec": failures}


def option_listener(listener, *args) -> str:
    """Valeur de --listener. Robot sépare les arguments par « : », ce qui coupe les chemins Windows
    (« C:\\… ») ; il accepte aussi « ; » comme séparateur : on l'emploie dès qu'un argument contient « : »."""
    args = [str(a) for a in args]
    sep = ";" if any(":" in a for a in args) else ":"
    return sep.join([str(listener), *args])


def run_robot(target: str, include_tags: list[str] | None = None,
              exclude_tags: list[str] | None = None, variables: dict | None = None,
              dry_run: bool = False, output_dir: str = "results/mcp",
              xray_ticket: str = "", xray_mode: str = "live",
              exec_summary: str = "", plan_summary: str = "",
              test_environments: list[str] | None = None,
              jira_transition_start: str = "", jira_transition_end: str = "",
              jira_transition_end_if_fail: str = "",
              attach_screenshots: bool = True, jdd_env: str = "",
              jdd_jeux: list[str] | None = None, events_url: str = "",
              relancer_echecs: bool = False, cartographie: bool = False, timeout_s: int = 3600,
              tests: list[str] | None = None, jira_champs_execution: dict | None = None) -> dict:
    """Lance une suite ou un dossier Robot Framework du projet puis renvoie le bilan.
    tests : tests précis (« <fichier>::<nom> », d'une ou plusieurs suites) au lieu de target : Robot --test.
    variables : ex. {'PLATFORM': 'android', 'DEVICE': 'emulator-5554'} (sélection du device).

    xray_ticket : une seule clé Jira, dont le type est détecté automatiquement :
      - Test Plan       -> crée une nouvelle exécution et l'ajoute au plan ;
      - Test Execution  -> met à jour cette exécution (tests manquants ajoutés) ;
      - autre ticket (US, epic…) ou clé projet seule (ex. DEMO) -> crée un plan + une exécution.
    xray_mode :
      - 'live' (défaut) : listener du MCP, test run en EXECUTING au démarrage de chaque test,
        PASSED / FAILED à la fin, heures de début et de fin, message d'échec et captures ;
      - 'listener_projet' : listener du projet (ROBOT_XRAY_LISTENER) avec la clé d'exécution ;
      - 'aucun'.
    test_environments : environnements Xray de l'exécution (défaut : valeur de PLATFORM).
    jira_transition_start / _end / _end_if_fail : transition Jira (nom de la transition ou du
      statut cible) appliquée au ticket d'exécution au début du run, à la fin, ou à la fin
      s'il y a au moins un échec.
    jdd_env / jdd_jeux : environnement et jeux de données à injecter (ex. 'recette',
      jdd_jeux vide = jeux référencés par la suite ;
      ['VIREMENT_STANDARD']). Les prérequis sont vérifiés AVANT le run : s'il manque des
      données, le run n'est pas lancé et le bilan indique « bloqué données ». Chaque jeu
      devient un dictionnaire &{JDD_<NOM>} utilisable dans « Initialiser Le Test ».
    events_url : URL qui reçoit les événements du run en direct (interface web).
    cartographie : enrichit la carte de l'application pendant le run (écrans et transitions des
      tests mobiles, test Xray qui passe par chaque écran). Ralentit un peu chaque action.
    relancer_echecs : rejoue uniquement les tests en échec du run précédent (même output_dir).
      Pour mettre à jour la même exécution Xray, passer sa clé dans xray_ticket.
    La session Appium du MCP est fermée avant le run pour libérer le device."""
    sel = selection_tests(tests) if tests else None
    if sel:
        target = sel["cible"]
    if not dry_run:
        from atelier.domain import prerequis

        rfb = prerequis.browser_robot()
        if not rfb["ok"] and prerequis.suites_web(target):
            raise RuntimeError(f"Run web impossible : {rfb['detail']}. {rfb['solution']}")
    if session.etat["platform"]:
        session.stop_session()
    evenements.publier({"type": "run_lance", "suite": target})
    jdd_file = None
    jdd_info: dict | None = None
    if not jdd_env and not jdd_jeux and not dry_run:  # aucun environnement choisi : celui des jeux de la suite, s'il est seul
        # (un dry run ne résout aucune variable : il n'injecte rien et n'est jamais bloqué faute de données)
        choix = environnement_des_jeux(target, sel["fichiers"] if sel else None)
        if choix.get("bloque"):
            return {"statut": "bloqué données", "jdd": {"env": "", "references": choix["references"]}, "conseil": choix["bloque"]}
        jdd_env = choix.get("env", "")
    if jdd_env and not jdd_jeux:  # environnement seul : jeux référencés (&{JDD_<NOM>}) par la suite
        jdd_jeux = sorted({j for c in (sel["fichiers"] if sel else [target]) for j in jdd.detecter(c, jdd_env)["detectes"]})
    if jdd_jeux:
        if not jdd_env:
            raise ValueError("jdd_env est obligatoire avec jdd_jeux.")
        res = jdd.resoudre(jdd_env, jdd_jeux)
        jdd_info = {"env": jdd_env, "controles": res["controles"], "bloques": res["bloques"]}
        if res["bloques"]:
            return {"statut": "bloqué données", "jdd": jdd_info,
                    "conseil": "Préparer les données manquantes ou choisir un autre jeu, puis relancer."}
        jdd_info["valeurs"] = jdd.masquer(jdd_env, res["jeux"])
    out_abs = projet.safe_path(output_dir)
    out_abs.mkdir(parents=True, exist_ok=True)
    report_path = out_abs / "xray_live_report.json"
    if report_path.exists():
        report_path.unlink()

    cmd = [sys.executable, "-m", "robot", "--outputdir", output_dir]
    if cartographie:
        app = carte.app_courante()
        if not app:
            raise RuntimeError("Aucune application dans la carte : crée-la d'abord.")
        cmd += ["--listener", option_listener(LISTENERS / "cartographie_listener.py", app)]
    if relancer_echecs:
        prev = out_abs / "output.xml"
        if not prev.exists():
            raise FileNotFoundError("Aucun run précédent à relancer dans ce dossier de résultats.")
        shutil.copy(prev, out_abs / "output_precedent.xml")
        cmd += ["--rerunfailed", str(out_abs / "output_precedent.xml")]
    if jdd_jeux:
        jdd_file = jdd.ecrire_fichier_variables(res["jeux"], out_abs / ".jdd_resolu.yaml")
        cmd += ["--variablefile", str(jdd_file)]
    live_xray = bool(xray_ticket) and not dry_run and xray_mode == "live"
    if live_xray or events_url:
        platform = str((variables or {}).get("PLATFORM", ""))
        cfg = {
            "ticket": xray_ticket if live_xray else "",
            "events_url": events_url,
            "exec_summary": exec_summary or (f"Exécution auto – {Path(target).stem}"
                                             + (f" – {platform}" if platform else "")
                                             + f" – {datetime.now():%d/%m/%Y %H:%M}"),
            "plan_summary": plan_summary,
            "test_environments": test_environments if test_environments is not None
            else ([platform] if platform else []),
            "transition_start": jira_transition_start,
            "transition_end": jira_transition_end,
            "transition_end_if_fail": jira_transition_end_if_fail,
            "champs_execution": jira_champs_execution or {},  # champs Jira de la Test Execution créée (environnement, build…)
            "attach_screenshots": attach_screenshots,
            "output_dir": str(out_abs),
            "outbox_dir": str(out_abs / "xray" / f"{datetime.now():%Y%m%d-%H%M%S-%f}"),
            "report": str(report_path),
        }
        cfg_path = out_abs / "xray_run_config.json"
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
        listener = LISTENERS / "xray_live_listener.py"
        cmd += ["--listener", option_listener(listener, cfg_path)]
    elif xray_ticket and not dry_run and xray_mode == "listener_projet":
        tpl = os.environ.get("ROBOT_XRAY_LISTENER", "")
        if not tpl:
            raise RuntimeError("ROBOT_XRAY_LISTENER non configuré.")
        cmd += ["--listener", tpl.replace("{exec_key}", xray_ticket),
                "--variable", f"XRAY_EXECUTION_KEY:{xray_ticket}"]

    for t in include_tags or []:
        cmd += ["--include", t]
    for t in exclude_tags or []:
        cmd += ["--exclude", t]
    for k, v in (variables or {}).items():
        cmd += ["--variable", f"{k}:{v}"]
    if dry_run:
        cmd.append("--dryrun")
    for nom in (sel["noms"] if sel else []):
        cmd += ["--test", nom.replace("[", "[[]")]  # motif Robot : « [ » ouvrirait une classe de caractères
    cmd += sel["fichiers"] if sel else [projet.safe_path(target).relative_to(projet.PROJECT_DIR).as_posix()]

    try:
        # stdin=DEVNULL : Robot ne lit jamais l'entrée ; hériter d'un tube que le parent lit (serveur MCP HTTP) le bloquait
        proc = subprocess.Popen(cmd, cwd=projet.PROJECT_DIR, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, errors="replace", env=env_robot())
        EN_COURS["proc"], EN_COURS["arret"] = proc, False
        try:
            sortie, erreurs = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            sortie, erreurs = proc.communicate()
            erreurs += f"\nDélai dépassé ({timeout_s} s) : run interrompu."
    finally:
        EN_COURS["proc"] = None
        if jdd_file and jdd_file.exists():
            jdd_file.unlink()  # contient des secrets résolus : jamais conservé
    bilan: dict = {"commande": " ".join(cmd), "code_retour": proc.returncode,
                   "console_fin": sortie[-3000:], "erreurs": erreurs[-2000:], "output_dir": output_dir}
    if EN_COURS.get("arret"):
        bilan["arrete"] = True
    output = out_abs / "output.xml"
    if output.exists():
        try:
            bilan["resultat"] = parse_robot_output(output.relative_to(projet.PROJECT_DIR).as_posix())
        except Exception as e:  # noqa: BLE001 - run arrêté ou tué : output.xml vide ou tronqué, le bilan (console, arrêt) reste utile
            bilan["rapport_illisible"] = f"output.xml incomplet (run interrompu) : {str(e)[:200]}"
    if report_path.exists():
        bilan["xray"] = json.loads(report_path.read_text("utf-8"))
        if live_xray and bilan["xray"].get("execution"):
            try:  # log.html / report.html n'existent qu'après la fin de Robot : envoi ici, via le journal
                from atelier.execution.journal_xray import envoyer_artefacts

                bilan["xray"]["artefacts"] = envoyer_artefacts(cfg["outbox_dir"], out_abs, bilan["xray"])
            except Exception as e:  # noqa: BLE001 - invariant : jamais d'échec du run à cause de Xray
                bilan["xray"]["artefacts"] = {"envoye": False, "erreur": str(e)[:300]}
    if jdd_info:
        bilan["jdd"] = jdd_info
    evenements.publier({"type": "run_bilan", "bilan": bilan})
    return bilan


def derniers_resultats(dossier: str = "results", reels: bool = False) -> dict:
    """Dernier statut connu de chaque test Robot, lu dans les output.xml du dossier de résultats
    (le plus récent l'emporte). Clé : « <fichier relatif>::<nom du test> ». reels : ignorer les dry runs."""
    base = projet.safe_path(dossier)
    out: dict = {}
    if not base.exists():
        return out
    for f in sorted(base.rglob("output.xml"), key=lambda p: p.stat().st_mtime):
        for cle, x in _tests_du_resultat(f):
            if reels and not x["reel"]:
                continue
            out[cle] = dict(x)
    return out


_MEMOIRE_RESULTATS: dict = {}  # output.xml -> (date, taille, projet, tests lus) : un résultat de run ne change plus


def _tests_du_resultat(f: Path) -> list:
    """Tests d'un output.xml (clé, statut…). Chaque écran relisait tous les output.xml du projet (3 s pour 47 runs) :
    un fichier déjà lu n'est relu que si sa date ou sa taille change."""
    from robot.api import ExecutionResult

    try:
        st = f.stat()
    except OSError:
        return []
    sig = (st.st_mtime_ns, st.st_size, str(projet.PROJECT_DIR))
    m = _MEMOIRE_RESULTATS.get(str(f))
    if m and m[0] == sig:
        return m[1]
    try:
        res = ExecutionResult(str(f))
    except Exception:
        return []  # run en cours d'écriture ou illisible : relu au prochain appel
    l = []
    for t in res.suite.all_tests:
        src = Path(str(t.source)) if t.source else None
        try:
            rel = src.resolve().relative_to(projet.PROJECT_DIR).as_posix() if src else ""
        except ValueError:
            rel = str(src)
        l.append((f"{rel}::{t.name}", {"statut": t.status, "message": t.message[:300], "reel": _execute(t),
                                        "fin": str(t.end_time or ""), "output": f.relative_to(projet.PROJECT_DIR).as_posix()}))
    _MEMOIRE_RESULTATS[str(f)] = (sig, l)
    return l


def _execute(element) -> bool:
    """Au moins un keyword réellement exécuté. Un dry run ne lance aucun keyword de bibliothèque (tous « NOT RUN ») :
    un test « PASS » en dry run n'a vérifié ni écran ni assertion."""
    structure = ("KEYWORD", "SETUP", "TEARDOWN", "IF/ELSE ROOT", "IF", "ELSE IF", "ELSE", "FOR", "ITERATION",
                 "TRY/EXCEPT ROOT", "TRY", "EXCEPT", "FINALLY", "WHILE", "GROUP")
    setup = getattr(element, "setup", None)
    for x in [*([setup] if setup and getattr(setup, "name", "") else []), *(getattr(element, "body", None) or [])]:
        if getattr(x, "type", "") not in structure:
            continue
        # un keyword de bibliothèque peut avoir un corps de messages de log : seuls les enfants structurels comptent
        if any(getattr(y, "type", "") in structure for y in (getattr(x, "body", None) or [])):
            if _execute(x):
                return True
        elif getattr(x, "type", "") in ("KEYWORD", "SETUP", "TEARDOWN") and getattr(x, "status", "NOT RUN") != "NOT RUN":
            return True
    return False
