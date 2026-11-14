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


def arreter_run() -> str:
    """Demande l'arrêt du run en cours (SIGINT : Robot termine proprement et écrit output.xml)."""
    import signal

    proc = EN_COURS.get("proc")
    if not proc or proc.poll() is not None:
        return "Aucun run en cours."
    EN_COURS["arret"] = True
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
              relancer_echecs: bool = False, cartographie: bool = False, timeout_s: int = 3600) -> dict:
    """Lance une suite ou un dossier Robot Framework du projet puis renvoie le bilan.
    variables : ex. {'PLATFORM': 'android', 'DEVICE': 'emulator-5554'} (sélection du device).

    xray_ticket : une seule clé Jira, dont le type est détecté automatiquement :
      - Test Plan       -> crée une nouvelle exécution et l'ajoute au plan ;
      - Test Execution  -> met à jour cette exécution (tests manquants ajoutés) ;
      - autre ticket (US, epic…) ou clé projet seule (ex. TAM) -> crée un plan + une exécution.
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
      ['VIREMENT_STANDARD']). Les prérequis sont vérifiés AVANT le run : s'il manque des
      données, le run n'est pas lancé et le bilan indique « bloqué données ». Chaque jeu
      devient un dictionnaire &{JDD_<NOM>} utilisable dans « Initialiser Le Test ».
    events_url : URL qui reçoit les événements du run en direct (interface web).
    cartographie : enrichit la carte de l'application pendant le run (écrans et transitions des
      tests mobiles, test Xray qui passe par chaque écran). Ralentit un peu chaque action.
    relancer_echecs : rejoue uniquement les tests en échec du run précédent (même output_dir).
      Pour mettre à jour la même exécution Xray, passer sa clé dans xray_ticket.
    La session Appium du MCP est fermée avant le run pour libérer le device."""
    if session.etat["platform"]:
        session.stop_session()
    evenements.publier({"type": "run_lance", "suite": target})
    jdd_file = None
    jdd_info: dict | None = None
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
        cmd += ["--listener", f"{LISTENERS / 'cartographie_listener.py'}:{app}"]
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
            "attach_screenshots": attach_screenshots,
            "output_dir": str(out_abs),
            "outbox_dir": str(out_abs / "xray" / f"{datetime.now():%Y%m%d-%H%M%S-%f}"),
            "report": str(report_path),
        }
        cfg_path = out_abs / "xray_run_config.json"
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
        listener = LISTENERS / "xray_live_listener.py"
        cmd += ["--listener", f"{listener}:{cfg_path}"]
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
    cmd.append(str(projet.safe_path(target).relative_to(projet.PROJECT_DIR)))

    try:
        proc = subprocess.Popen(cmd, cwd=projet.PROJECT_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
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
        bilan["resultat"] = parse_robot_output(str(output.relative_to(projet.PROJECT_DIR)))
    if report_path.exists():
        bilan["xray"] = json.loads(report_path.read_text("utf-8"))
    if jdd_info:
        bilan["jdd"] = jdd_info
    evenements.publier({"type": "run_bilan", "bilan": bilan})
    return bilan


def derniers_resultats(dossier: str = "results") -> dict:
    """Dernier statut connu de chaque test Robot, lu dans les output.xml du dossier de résultats
    (le plus récent l'emporte). Clé : « <fichier relatif>::<nom du test> »."""
    from robot.api import ExecutionResult

    base = projet.safe_path(dossier)
    out: dict = {}
    if not base.exists():
        return out
    for f in sorted(base.rglob("output.xml"), key=lambda p: p.stat().st_mtime):
        try:
            res = ExecutionResult(str(f))
        except Exception:
            continue
        for t in res.suite.all_tests:
            src = Path(str(t.source)) if t.source else None
            try:
                rel = str(src.resolve().relative_to(projet.PROJECT_DIR)) if src else ""
            except ValueError:
                rel = str(src)
            out[f"{rel}::{t.name}"] = {"statut": t.status, "message": t.message[:300],
                                       "fin": str(t.end_time or ""), "output": str(f.relative_to(projet.PROJECT_DIR))}
    return out
