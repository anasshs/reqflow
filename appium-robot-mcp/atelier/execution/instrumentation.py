"""Exécution des tests Kotlin d'instrumentation Android (UI Automator, Espresso) : compilation Gradle, installation des
APK, lancement par « am instrument », lecture des résultats, remontée dans Xray par le journal (outbox) existant —
les mêmes événements que le listener Robot (preparation, test_debut, test_fin), donc Xray, historique, Kanban et
qualification des échecs fonctionnent sans changement (docs/AUTOMATISATION_MULTI_CIBLES.md, phase C).

Garde-fous : un seul pilote à la fois sur un téléphone (pas de session Appium pendant un run d'instrumentation) ;
comptes, mots de passe et données passés en arguments d'instrumentation (-e), jamais écrits ni journalisés en clair.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

CODES = {"1": "DEBUT", "0": "PASS", "-2": "FAIL", "-1": "FAIL", "-3": "SKIP", "-4": "SKIP"}
SECRET = re.compile(r"(?i)(password|passwd|mot_?de_?passe|mdp|secret|token|pin|cvv|otp|identifiant)")


def _racine(dossier: str) -> Path:
    from atelier.domain import projet

    return projet.safe_path(dossier)


def gradle(dossier: str) -> list[str]:
    """Commande Gradle : wrapper du projet, sinon GRADLE (variable), sinon gradle du SDK Android (C:\\Android\\gradle-*),
    sinon gradle du PATH."""
    r = _racine(dossier)
    for w in ("gradlew.bat", "gradlew") if os.name == "nt" else ("gradlew",):
        if (r / w).exists():
            return [str(r / w)]
    if os.environ.get("GRADLE"):
        return [os.environ["GRADLE"]]
    sdk = Path(os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or "C:/Android")
    for g in sorted(sdk.glob("gradle-*/bin/gradle" + (".bat" if os.name == "nt" else "")), reverse=True):
        return [str(g)]
    g = shutil.which("gradle")
    if not g:
        raise RuntimeError("Gradle introuvable : installer Gradle 8.7 (ou un wrapper gradlew dans le projet Kotlin), ou régler GRADLE.")
    return [g]


def _executer(cmd: list[str], cwd: Path | None = None, delai: int = 1800) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=delai)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def appareil(lanceur=None) -> str:
    """Premier appareil Android connecté (adb devices) ; refus clair sinon."""
    code, sortie = (lanceur or _executer)(["adb", "devices"], None, 60)
    for l in sortie.splitlines()[1:]:
        p = l.split()
        if len(p) >= 2 and p[1] == "device":
            return p[0]
    raise RuntimeError("Aucun appareil Android connecté (adb devices) : brancher le téléphone ou démarrer un émulateur.")


def compiler(dossier: str, lanceur=None) -> dict:
    """Compile les tests (contrôle avant revue) : {ok, erreurs: [« e: fichier:ligne:col message »], duree_s}."""
    t0 = time.time()
    code, sortie = (lanceur or _executer)(gradle(dossier) + [":app:compileDebugAndroidTestKotlin", "--console=plain"], _racine(dossier))
    erreurs = [l.strip() for l in sortie.splitlines() if l.startswith("e: ")]
    return {"ok": code == 0, "erreurs": erreurs[:50], "duree_s": round(time.time() - t0, 1),
            "message": "Compilation réussie." if code == 0 else (erreurs[0] if erreurs else sortie.strip().splitlines()[-1:] or ["Échec de la compilation."])[0]}


def construire(dossier: str, lanceur=None) -> dict:
    code, sortie = (lanceur or _executer)(gradle(dossier) + [":app:assembleDebug", ":app:assembleDebugAndroidTest", "--console=plain"], _racine(dossier))
    r = _racine(dossier) / "app" / "build" / "outputs" / "apk"
    return {"ok": code == 0, "hote": str(r / "debug" / "app-debug.apk"), "tests": str(r / "androidTest" / "debug" / "app-debug-androidTest.apk"),
            "message": "" if code == 0 else sortie.strip().splitlines()[-1:][0] if sortie.strip() else "Échec du build."}


def installer(udid: str, apks: list[str], lanceur=None) -> dict:
    """Installe les APK ; un refus du téléphone est dit clairement (MIUI : « Installer via USB » à confirmer sur l'écran)."""
    for a in apks:
        code, sortie = (lanceur or _executer)(["adb", "-s", udid, "install", "-r", "-t", a], None, 600)
        if code != 0 or "Failure" in sortie:
            motif = re.search(r"Failure \[([^\]]+)\]", sortie)
            m = motif.group(1) if motif else sortie.strip()[-200:]
            conseil = (" Le téléphone demande de confirmer l'installation sur son écran (MIUI : Options pour les développeurs › "
                       "Installer via USB)." if "USER_RESTRICTED" in m else "")
            return {"ok": False, "apk": Path(a).name, "message": f"Installation refusée : {m}.{conseil}"}
    return {"ok": True}


def analyser_sortie(texte: str) -> list[dict]:
    """Sortie brute de « am instrument -r » -> [{classe, methode, statut PASS|FAIL|SKIP, message, debut, fin}]."""
    out, courant, bloc = {}, {}, {}
    for ligne in texte.splitlines():
        m = re.match(r"INSTRUMENTATION_STATUS: (\w+)=(.*)", ligne)
        if m:
            cle, val = m.groups()
            bloc[cle] = val if cle != "stack" else val
            courant = bloc
            continue
        m = re.match(r"INSTRUMENTATION_STATUS_CODE: (-?\d+)", ligne)
        if m:
            statut = CODES.get(m.group(1), "FAIL")
            ident = f"{bloc.get('class', '')}#{bloc.get('test', '')}"
            if bloc.get("test"):
                t = out.setdefault(ident, {"classe": bloc.get("class", ""), "methode": bloc["test"], "statut": "FAIL", "message": "",
                                           "debut": datetime.now().isoformat(timespec="seconds"), "fin": ""})
                if statut != "DEBUT":
                    t["statut"] = statut
                    t["fin"] = datetime.now().isoformat(timespec="seconds")
                    t["message"] = (bloc.get("stack") or "").split("\n")[0][:1500]
            bloc = {}
            continue
        if courant.get("stack") is not None and ligne and not ligne.startswith("INSTRUMENTATION"):
            courant["stack"] = courant["stack"] + "\n" + ligne
    return list(out.values())


def cles_xray(dossier: str) -> dict[str, str]:
    """« classe#methode » -> clé Xray : annotation @Xray("CLE") au-dessus de la méthode, sinon nom tam_<n>_… (tests portés)."""
    from atelier.domain import projet

    out = {}
    for f in _racine(dossier).rglob("*.kt"):
        if "build" in f.relative_to(projet.PROJECT_DIR).parts:
            continue
        texte = f.read_text("utf-8", errors="replace")
        paquet = (re.search(r"^package\s+([\w.]+)", texte, re.M) or [None, ""])[1]
        classe = (re.search(r"\bclass\s+(\w+)", texte) or [None, ""])[1]
        for m in re.finditer(r'(?:@Xray\("([A-Z][A-Z0-9_]+-\d+)"\)\s*)?fun\s+(\w+)\(', texte):
            cle = m.group(1) or ("-".join(re.match(r"([a-z][a-z0-9]*)_(\d+)_", m.group(2)).groups()).upper()
                                 if re.match(r"([a-z][a-z0-9]*)_(\d+)_", m.group(2)) else "")
            if cle:
                out[f"{paquet}.{classe}#{m.group(2)}"] = cle
    return out


def arguments(jdd: dict | None = None, extra: dict | None = None) -> list[str]:
    """Arguments d'instrumentation : -e jdd.<JEU>.<champ> valeur (jeux de données), -e otp_mode, etc."""
    out = []
    for jeu, champs in (jdd or {}).items():
        for c, v in (champs or {}).items():
            out += ["-e", f"jdd.{jeu}.{c}", str(v)]
    for k, v in (extra or {}).items():
        out += ["-e", k, str(v)]
    return out


def masquer(cmd: list[str]) -> str:
    """Commande lisible pour le journal : valeurs des arguments sensibles masquées."""
    out, i = [], 0
    while i < len(cmd):
        out.append(cmd[i])
        if cmd[i] == "-e" and i + 2 < len(cmd):
            out += [cmd[i + 1], "***" if SECRET.search(cmd[i + 1]) else cmd[i + 2]]
            i += 3
            continue
        i += 1
    return " ".join(out)


def executer(udid: str, selection: list[str], paquet_tests: str, args: list[str] | None = None, lanceur=None) -> dict:
    """am instrument -w -r -e class <a#b,c> ... ; selection : classes ou « classe#methode »."""
    cmd = ["adb", "-s", udid, "shell", "am", "instrument", "-w", "-r"] + (["-e", "class", ",".join(selection)] if selection else []) \
        + (args or []) + [f"{paquet_tests}/androidx.test.runner.AndroidJUnitRunner"]
    t0 = time.time()
    code, sortie = (lanceur or _executer)(cmd, None, 3600)
    res = analyser_sortie(sortie)
    erreur = "" if res or "INSTRUMENTATION_FAILED" not in sortie else sortie.strip().splitlines()[-1]
    return {"resultats": res, "commande": masquer(cmd), "duree_s": round(time.time() - t0, 1), "erreur": erreur,
            "passes": sum(t["statut"] == "PASS" for t in res), "echecs": sum(t["statut"] == "FAIL" for t in res),
            "ignores": sum(t["statut"] == "SKIP" for t in res)}


def journaliser_xray(resultats: list[dict], cles: dict[str, str], dossier_outbox: str | Path, cfg: dict) -> int:
    """Écrit dans l'outbox Xray les mêmes événements que le listener Robot : preparation, test_debut, test_fin. Le
    synchroniseur existant les envoie (journal_xray.Synchroniseur). Rend le nombre de tests tracés dans Xray."""
    from atelier.execution.journal_xray import Journal, statuts_xray

    j, st = Journal(dossier_outbox), statuts_xray()
    run_id = cfg.get("run_id") or f"KT-{datetime.now():%Y%m%d-%H%M%S}"
    traces = [(t, cles.get(f"{t['classe']}#{t['methode']}")) for t in resultats]
    traces = [(t, k) for t, k in traces if k]
    j.ajouter(run_id, "preparation", ticket=cfg.get("ticket", ""), cles_tests=sorted({k for _, k in traces}),
              exec_summary=cfg.get("exec_summary", ""), plan_summary=cfg.get("plan_summary", ""),
              envs=cfg.get("test_environments") or ["Android"], champs=cfg.get("champs_execution") or {})
    for t, k in traces:
        ident = f"{t['classe']}#{t['methode']}"
        j.ajouter(run_id, "test_debut", ident, cle_xray=k, debut=t["debut"])
        commentaire = None if t["statut"] == "PASS" else (f"Test Kotlin : {ident}\nTechnologie : {cfg.get('technologie', 'uiautomator')}"
                                                           + (f"\nÉchec : {t['message']}" if t["message"] else ""))
        j.ajouter(run_id, "test_fin", ident, cle_xray=k, statut=st.get(t["statut"], "TO DO"), debut=t["debut"],
                  fin=t["fin"] or t["debut"], commentaire=commentaire, captures=[])
    return len(traces)


def lancer(dossier: str, udid: str, selection: list[str], jdd: dict | None = None, extra: dict | None = None,
           xray: dict | None = None, construire_avant: bool = True, lanceur=None) -> dict:
    """Run complet : build, installation, exécution, bilan ; Xray si xray={ticket, exec_summary, ...} (outbox du run)."""
    from atelier.generation.technologies.kotlin import ProjetKotlin

    if construire_avant:
        b = construire(dossier, lanceur)
        if not b["ok"]:
            return {"ok": False, "etape": "build", "message": b["message"]}
        i = installer(udid, [b["hote"], b["tests"]], lanceur)
        if not i["ok"]:
            return {"ok": False, "etape": "installation", "message": i["message"]}
    pk = ProjetKotlin(dossier)
    r = executer(udid, selection, pk.paquet + ".test", arguments(jdd, extra), lanceur)
    r["ok"] = not r["erreur"] and r["echecs"] == 0
    if xray:
        from atelier.domain import projet

        dossier_run = projet.PROJECT_DIR / "results" / "kotlin" / datetime.now().strftime("%Y%m%d-%H%M%S")
        r["xray_traces"] = journaliser_xray(r["resultats"], cles_xray(dossier), dossier_run, {**xray, "technologie": "uiautomator"})
        r["outbox"] = str(dossier_run)
    return r
