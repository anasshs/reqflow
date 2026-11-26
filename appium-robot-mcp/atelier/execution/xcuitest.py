"""Exécution des tests XCUITest (iOS natif) : xcodebuild sur un Mac, dans le dépôt iOS de l'application.

  xcodebuild test -project|-workspace <xcode_projet> -scheme <xcode_schema> -destination '<xcode_destination>'
             -resultBundlePath <résultats> [-only-testing:<cible>/<Classe>/<methode> …]

Données : TEST_RUNNER_JDD_<JEU>_<CHAMP>, TEST_RUNNER_OTP_MODE, TEST_RUNNER_OTP_CODE, TEST_RUNNER_APP_BUNDLE_ID (xcodebuild
retire le préfixe TEST_RUNNER_ et les passe au test) ; valeurs jamais journalisées. Résultats lus dans la sortie
(« Test Case '-[Cible.Classe methode]' passed/failed (x seconds) ») et envoyés à Xray par l'outbox (même journal que les
runs Robot et Kotlin) quand un ticket est donné. Hors Mac : refus clair, rien n'est lancé.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

LIGNE_CAS = re.compile(r"Test Case '-\[(?:([\w.]+)\.)?(\w+) (\w+)\]' (passed|failed|skipped) \(([\d.]+) seconds\)")
LIGNE_ERREUR = re.compile(r":\s*error:\s*-\[(?:[\w.]+\.)?(\w+) (\w+)\]\s*:\s*(.*)")
SECRET = re.compile(r"(?i)(password|passwd|mot_?de_?passe|mdp|secret|token|pin|otp)")


def disponible() -> dict:
    ok = sys.platform == "darwin" and bool(shutil.which("xcodebuild"))
    return {"disponible": ok, "raison": "" if ok else "XCUITest s'exécute sur un Mac avec Xcode (xcodebuild introuvable sur ce poste)."}


def _config() -> dict:
    from atelier.generation.technologies.xcuitest import Xcuitest

    return Xcuitest.config()


def commande(action: str, tests: list[str] | None = None, cfg: dict | None = None, resultats: str = "") -> list[str]:
    """Commande xcodebuild (test, build-for-testing) ; tests : « Classe/methode » ou « Classe » (-only-testing)."""
    from atelier.domain import projet

    c = cfg or _config()
    if not c.get("projet") or not c.get("schema"):
        raise ValueError("Fiche application › automatisation : xcode_projet (.xcodeproj ou .xcworkspace du dépôt iOS) et xcode_schema "
                         "sont à renseigner.")
    with projet.pour_technologie("xcuitest"):
        chemin = projet.safe_path(c["projet"])
    cmd = ["xcodebuild", action, "-workspace" if chemin.suffix == ".xcworkspace" else "-project", str(chemin), "-scheme", c["schema"],
           "-destination", c["destination"]]
    if resultats:
        cmd += ["-resultBundlePath", resultats]
    cible = c.get("cible") or ""
    for t in tests or []:
        t = str(t).replace("#", "/").replace(".swift", "")
        cmd.append(f"-only-testing:{cible}/{t}" if cible and not t.startswith(cible + "/") else f"-only-testing:{t}")
    return cmd


def env_test(jdd: dict | None = None, extra: dict | None = None) -> dict:
    """Environnement du test : JDD_<JEU>_<CHAMP>, OTP_MODE… préfixés TEST_RUNNER_ (transmis par xcodebuild)."""
    e = dict(os.environ)
    for jeu, champs in (jdd or {}).items():
        for champ, v in (champs or {}).items():
            e[f"TEST_RUNNER_JDD_{str(jeu).upper()}_{str(champ).upper()}"] = str(v)
    for k, v in (extra or {}).items():
        e[f"TEST_RUNNER_{k.upper()}"] = str(v)
    return e


def jeux_des_tests(tests: list[str] | None = None) -> list[str]:
    """Jeux de données utilisés (Atelier.initialiser(jeu: « X »)) par les classes de test choisies (toutes si aucune)."""
    from atelier.domain import projet

    classes = {str(t).replace("#", "/").split("/")[-2 if "/" in str(t) else -1] for t in tests or []}
    jeux = set()
    with projet.pour_technologie("xcuitest"):
        d = projet.safe_path(_config()["dossier"])
        for f in d.rglob("*.swift") if d.exists() else []:
            texte = f.read_text("utf-8", errors="replace")
            if classes and not any(re.search(rf"\bclass\s+{re.escape(c)}\b", texte) for c in classes):
                continue
            jeux |= set(re.findall(r'initialiser\(jeu:\s*"([A-Za-z0-9_]+)"\)', texte))
    return sorted(jeux)


def analyser_sortie(texte: str) -> list[dict]:
    """Sortie de xcodebuild test → [{cible, classe, methode, statut PASS|FAIL|SKIP, duree_s, message, cle_xray}]."""
    from atelier.generation.technologies.xcuitest import cle_de_methode

    messages = {}
    for l in texte.splitlines():
        m = LIGNE_ERREUR.search(l)
        if m:
            messages.setdefault((m.group(1), m.group(2)), m.group(3).strip()[:500])
    out = []
    for l in texte.splitlines():
        m = LIGNE_CAS.search(l)
        if m:
            cible, classe, meth, st, d = m.groups()
            out.append({"cible": cible or "", "classe": classe, "methode": meth, "statut": {"passed": "PASS", "failed": "FAIL"}.get(st, "SKIP"),
                        "duree_s": float(d), "message": messages.get((classe, meth), ""), "cle_xray": cle_de_methode(meth)})
    return out


def _executer(cmd: list[str], env: dict | None, delai: int, cwd: Path) -> tuple[int, str]:
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, errors="replace", timeout=delai)
    return r.returncode, (r.stdout or "") + "\n" + (r.stderr or "")


def compiler(lanceur=None) -> dict:
    """xcodebuild build-for-testing : les tests générés compilent-ils dans le projet de l'application ?"""
    from atelier.domain import projet

    d = disponible()
    if not d["disponible"] and not lanceur:
        return {"ok": False, "message": d["raison"], "mac_requis": True}
    with projet.pour_technologie("xcuitest"):
        cmd = commande("build-for-testing")
        code, sortie = (lanceur or _executer)(cmd, None, 1800, projet.racine_code())
    erreurs = [l.strip() for l in sortie.splitlines() if ": error:" in l][:20]
    return {"ok": code == 0, "commande": " ".join(cmd), "erreurs": erreurs, "message": "Compilation réussie." if code == 0 else
            (erreurs[0] if erreurs else sortie.strip().splitlines()[-1] if sortie.strip() else "échec de xcodebuild")}


def executer(tests: list[str] | None = None, jdd: dict | None = None, extra: dict | None = None, xray: dict | None = None,
             lanceur=None) -> dict:
    """Run XCUITest : xcodebuild test, résultats par test (clé Xray lue dans le nom de méthode), Xray par l'outbox si demandé."""
    from atelier.domain import projet
    from atelier.execution import instrumentation

    d = disponible()
    if not d["disponible"] and not lanceur:
        return {"ok": False, "message": d["raison"], "mac_requis": True}
    dossier = projet.PROJECT_DIR / "results" / "xcuitest" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dossier.mkdir(parents=True, exist_ok=True)
    with projet.pour_technologie("xcuitest"):
        cmd = commande("test", tests, resultats=str(dossier / "Resultats.xcresult"))
        t0 = time.time()
        code, sortie = (lanceur or _executer)(cmd, env_test(jdd, extra), 7200, projet.racine_code())
    (dossier / "xcodebuild.log").write_text(sortie[-2_000_000:], "utf-8")
    res = analyser_sortie(sortie)
    bilan = {"ok": code == 0, "resultats": res, "commande": " ".join(cmd), "duree_s": round(time.time() - t0, 1),
             "passes": sum(t["statut"] == "PASS" for t in res), "echecs": sum(t["statut"] == "FAIL" for t in res),
             "ignores": sum(t["statut"] == "SKIP" for t in res), "dossier": projet.relatif(dossier),
             "erreur": "" if res or code == 0 else (sortie.strip().splitlines() or ["échec de xcodebuild"])[-1][:300]}
    if xray and res:
        cles = {f"{t['classe']}#{t['methode']}": t["cle_xray"] for t in res if t["cle_xray"]}
        bilan["xray_traces"] = instrumentation.journaliser_xray(res, cles, dossier / "xray", {**xray, "test_environments": xray.get("test_environments") or ["iOS"]})
    return bilan
