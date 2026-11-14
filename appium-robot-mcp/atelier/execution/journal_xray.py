"""Journal Xray d'un run (« outbox ») et synchroniseur avec reprise.

Le listener Robot n'appelle plus Xray directement : il écrit chaque événement dans
`<dossier du run>/xray_outbox.jsonl`, avec une clé d'idempotence. Le synchroniseur (thread du
listener pendant le run, ou `python -m atelier xray-sync <dossier>` plus tard) envoie le journal
dans l'ordre, avec backoff exponentiel, et note chaque clé envoyée dans `xray_outbox.envoyes`.
Les créations (plan, exécution) sont mémorisées étape par étape dans `xray_outbox.etat.json` :
un rejeu ne recrée jamais un plan ou une exécution déjà créés.

Le run Robot se termine normalement même si Xray est injoignable du début à la fin ; le journal
reste complet et peut être rejoué.

Réglages : XRAY_SYNC_ESSAIS (6), XRAY_SYNC_BACKOFF (1 s, doublé à chaque échec), XRAY_SYNC_PLAFOND (30 s).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime
from pathlib import Path

from atelier.integrations.xray import ErreurGraphQL

OUTBOX = "xray_outbox.jsonl"
ENVOYES = "xray_outbox.envoyes"
ETAT = "xray_outbox.etat.json"
VERROU = "xray_outbox.verrou"


STATUTS_DEFAUT = {"PASS": "PASSED", "FAIL": "FAILED", "SKIP": "TODO", "NOT RUN": "TODO", "EXECUTING": "EXECUTING"}


def statuts_xray() -> dict:
    """Statut Robot (et EXECUTING) -> statut de test run Xray. Les statuts de test run sont
    personnalisables par projet : XRAY_STATUTS='{"FAIL": "ECHEC", "EXECUTING": "EN COURS"}'
    remplace tout ou partie de la table (vérifier les noms avec `python -m atelier xray-verifier`)."""
    try:
        return {**STATUTS_DEFAUT, **json.loads(os.environ.get("XRAY_STATUTS") or "{}")}
    except json.JSONDecodeError:
        return dict(STATUTS_DEFAUT)


def statuts_non_finaux() -> set[str]:
    """Statuts Xray non finaux (Xray refuse alors l'heure de fin). Défaut : TODO, EXECUTING ;
    XRAY_STATUTS_NON_FINAUX='TODO,EXECUTING,EN ATTENTE' (contrôle : `python -m atelier xray-statuts`)."""
    v = os.environ.get("XRAY_STATUTS_NON_FINAUX") or "TODO,EXECUTING"
    return {x.strip().upper() for x in v.split(",") if x.strip()}


def controler_statuts(statuts: list[dict], table: dict | None = None) -> dict:
    """Compare la table Robot -> Xray (XRAY_STATUTS) aux statuts réels du projet (getStatuses).
    Signale les statuts inexistants et la finalité attendue : PASS / FAIL finaux, EXECUTING non final."""
    table = table or statuts_xray()
    reels = {str(s.get("name", "")).upper(): s for s in statuts}
    lignes, ok = [], True
    for robot, cible in table.items():
        s = reels.get(str(cible).upper())
        attendu_final = robot in ("PASS", "FAIL")
        if not s:
            etat, ok = "absent du projet Xray", False
        elif robot == "EXECUTING" and s.get("final"):
            etat, ok = "final : l'heure de fin serait figée dès le début du test", False
        elif attendu_final and not s.get("final"):
            etat, ok = "non final : Xray refusera l'heure de fin", False
        else:
            etat = "conforme"
        lignes.append({"robot": robot, "xray": cible, "final": (s or {}).get("final"), "etat": etat})
    non_finaux_reels = sorted(n for n, s in reels.items() if not s.get("final"))
    declares = statuts_non_finaux()
    return {"ok": ok and set(non_finaux_reels) <= declares, "lignes": lignes, "non_finaux_reels": non_finaux_reels,
            "non_finaux_declares": sorted(declares),
            "non_finaux_manquants": sorted(set(non_finaux_reels) - declares)}


class ErreurDefinitive(Exception):
    """Erreur que la répétition ne corrigera pas (ex. ticket cible qui est un Test)."""


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


# =========================================================================== journal
class Journal:
    def __init__(self, dossier: str | Path):
        self.dossier = Path(dossier)
        self._verrou = threading.Lock()

    @property
    def fichier(self) -> Path:
        return self.dossier / OUTBOX

    def ajouter(self, run_id: str, type_ev: str, test: str = "", **donnees) -> dict:
        horodatage = _maintenant()
        cle = hashlib.sha256(f"{run_id}|{test}|{type_ev}|{horodatage}".encode()).hexdigest()[:24]
        ev = {"cle": cle, "run_id": run_id, "test": test, "type": type_ev, "horodatage": horodatage,
              "donnees": donnees}
        with self._verrou:
            self.dossier.mkdir(parents=True, exist_ok=True)
            with self.fichier.open("a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
        return ev

    def evenements(self) -> list[dict]:
        if not self.fichier.exists():
            return []
        out = []
        for ligne in self.fichier.read_text("utf-8").splitlines():
            try:
                out.append(json.loads(ligne))
            except json.JSONDecodeError:
                pass  # ligne tronquée (arrêt brutal) : ignorée
        return out

    def envoyes(self) -> dict:
        f = self.dossier / ENVOYES
        out: dict = {}
        if f.exists():
            for ligne in f.read_text("utf-8").splitlines():
                try:
                    d = json.loads(ligne)
                    out[d["cle"]] = d
                except (json.JSONDecodeError, KeyError):
                    pass
        return out

    def marquer(self, cle: str, statut: str = "envoye", detail: str = ""):
        with (self.dossier / ENVOYES).open("a", encoding="utf-8") as f:
            f.write(json.dumps({"cle": cle, "statut": statut, "detail": detail, "heure": _maintenant()},
                               ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def etat(self) -> dict:
        f = self.dossier / ETAT
        return json.loads(f.read_text("utf-8")) if f.exists() else {}

    def sauver_etat(self, etat: dict):
        f = self.dossier / ETAT
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(etat, ensure_ascii=False, indent=2), "utf-8")
        os.replace(tmp, f)

    def restants(self) -> list[dict]:
        faits = self.envoyes()
        return [e for e in self.evenements() if e["cle"] not in faits]


# =========================================================================== synchroniseur
class Synchroniseur:
    def __init__(self, dossier: str | Path, xray=None, jira=None, sommeil=None, journaliser=None,
                 essais_max: int | None = None, backoff: float | None = None, plafond: float | None = None):
        self.journal = Journal(dossier)
        self._xray, self._jira = xray, jira
        self.arret = threading.Event()
        self.sommeil = sommeil or self.arret.wait  # attente interrompue par une demande d'arrêt
        self.journaliser = journaliser or (lambda niveau, msg, **k: None)
        self.essais_max = essais_max or int(os.environ.get("XRAY_SYNC_ESSAIS", 6))
        self.backoff = backoff if backoff is not None else float(os.environ.get("XRAY_SYNC_BACKOFF", 1))
        self.plafond = plafond if plafond is not None else float(os.environ.get("XRAY_SYNC_PLAFOND", 30))

    # ------------------------------------------------------------------ clients (créés à la demande)
    @property
    def xray(self):
        if self._xray is None:
            from atelier.integrations.xray import XrayClient

            self._xray = XrayClient()
        return self._xray

    @property
    def jira(self):
        if self._jira is None:
            from atelier.integrations.jira import JiraClient

            self._jira = JiraClient()
        return self._jira

    # ------------------------------------------------------------------ boucle
    def envoyer_tout(self) -> dict:
        """Envoie les événements restants dans l'ordre. S'arrête au premier événement qui échoue
        encore après tous les essais (les suivants en dépendent) : à rejouer plus tard."""
        bilan = {"envoyes": 0, "ignores": 0, "restants": 0, "erreur": ""}
        with _VerrouFichier(self.journal.dossier / VERROU):
            for ev in self.journal.restants():
                if self.arret.is_set():
                    break
                try:
                    self._avec_reprise(ev)
                except ErreurDefinitive as e:
                    self.journal.marquer(ev["cle"], "ignore", str(e))
                    self.journaliser("erreur", f"{ev['type']} {ev.get('test', '')} : {e}")
                    bilan["ignores"] += 1
                    continue
                except Exception as e:
                    bilan["erreur"] = f"{ev['type']} : {e}"
                    break
                self.journal.marquer(ev["cle"])
                bilan["envoyes"] += 1
        bilan["restants"] = len(self.journal.restants())
        return bilan

    def _avec_reprise(self, ev: dict):
        attente = self.backoff
        for essai in range(1, self.essais_max + 1):
            try:
                return self._traiter(ev)
            except ErreurDefinitive:
                raise
            except ErreurGraphQL as e:  # refus métier de Xray : réessayer ne change rien
                self.journaliser("erreur", f"Xray refuse ({ev['type']}) : {e} — non rejoué automatiquement, à corriger puis rejouer")
                raise
            except Exception as e:
                if essai == self.essais_max or self.arret.is_set():
                    self.journaliser("erreur", f"Xray injoignable ({ev['type']}) : {e} — à rejouer")
                    raise
                self.journaliser("avertissement", f"Xray : essai {essai} échoué ({e}), nouvel essai dans {attente:g} s")
                self.sommeil(attente)
                attente = min(attente * 2, self.plafond)

    # ------------------------------------------------------------------ traitements
    def _traiter(self, ev: dict):
        d, etat = ev["donnees"], self.journal.etat()
        if ev["type"] == "preparation":
            return self._preparer(d)
        if etat.get("abandon"):
            raise ErreurDefinitive(f"cible Xray non préparée : {etat['abandon']}")
        if ev["type"] == "transition":
            if self.jira.enabled and d.get("nom"):
                cible = self.jira.transition(etat["exec_key"], d["nom"])
                self.journaliser("info", f"{etat['exec_key']} -> {cible} ({d.get('moment', '')})")
            return
        run_id = (etat.get("runs") or {}).get(d.get("cle_xray"))
        if not run_id:
            raise ErreurDefinitive(f"{d.get('cle_xray')} : test introuvable dans l'exécution")
        if ev["type"] == "artefacts":  # output.xml, log.html, report.html (zip) joints aux test runs, après le run
            runs = etat.get("runs") or {}
            for cle in d.get("cles") or []:
                if cle in runs and Path(d["fichier"]).exists():
                    self.xray.add_evidence(runs[cle], [d["fichier"]])
            self.journaliser("info", f"résultats Robot joints à {len(d.get('cles') or [])} test run(s)")
            return
        if ev["type"] == "test_debut":
            self.xray.update_run(run_id, started=d["debut"])
            self.xray.set_status(run_id, statuts_xray()["EXECUTING"])
        elif ev["type"] == "test_fin":
            # Xray Cloud refuse finishedOn tant que le statut n'est pas final (constaté à l'essai réel) :
            # statut final d'abord, puis heures et commentaire, puis preuves.
            # SKIP / NOT RUN -> TODO (non final) : l'heure de fin n'est pas envoyée, sinon refus définitif.
            self.xray.set_status(run_id, d["statut"])
            final = str(d["statut"]).upper() not in statuts_non_finaux()
            self.xray.update_run(run_id, started=d.get("debut"), finished=d["fin"] if final else None,
                                 comment=d.get("commentaire"))
            captures = [c for c in d.get("captures") or [] if Path(c).exists()]
            if captures:
                self.xray.add_evidence(run_id, captures)
            self.journaliser("info", f"{d['cle_xray']} -> {d['statut']} ({ev.get('test', '')})")

    def _preparer(self, d: dict):
        """Cible Xray préparée étape par étape ; chaque création est mémorisée avant la suivante."""
        j = self.journal
        etat = j.etat()
        if etat.get("prepare"):
            return
        x = self.xray
        if "ticket" not in etat:
            etat["ticket"] = x.resolve(d["ticket"])
            j.sauver_etat(etat)
        info = etat["ticket"]
        if info["type"] == "test":
            etat["abandon"] = f"{info['key']} est un Test : donner un plan, une exécution, un ticket ou un projet."
            j.sauver_etat(etat)
            raise ErreurDefinitive(etat["abandon"])
        if "ids" not in etat:
            etat["ids"] = x.test_ids(d.get("cles_tests") or [])
            j.sauver_etat(etat)
        tids = list(etat["ids"].values())
        etat.setdefault("avertissements", [])
        if info["type"] == "execution":
            etat.update(exec_id=info["issueId"], exec_key=info["key"], plan_key=None, mode="mise à jour de l'exécution")
            if tids and not etat.get("tests_ajoutes"):
                x.add_tests_to_exec(etat["exec_id"], tids)
                etat["tests_ajoutes"] = True
            j.sauver_etat(etat)
        else:
            if info["type"] == "plan":
                etat.update(plan_id=info["issueId"], plan_key=info["key"], mode="nouvelle exécution ajoutée au plan")
                if tids and not etat.get("tests_ajoutes"):
                    x.add_tests_to_plan(etat["plan_id"], tids)
                    etat["tests_ajoutes"] = True
                j.sauver_etat(etat)
            elif "plan_id" not in etat:
                resume = d.get("plan_summary") or (f"Plan de test – {info['key']}" if info["type"] == "autre"
                                                    else f"Plan de test auto – {datetime.now():%d/%m/%Y}")
                etat["plan_id"], etat["plan_key"] = x.create_plan(info["projet"], resume, tids)
                etat["mode"] = "plan créé + exécution"
                j.sauver_etat(etat)
                if info["type"] == "autre" and self.jira.enabled:
                    try:
                        self.jira.link(etat["plan_key"], info["key"])
                    except Exception as e:
                        etat["avertissements"].append(f"Lien {etat['plan_key']} ↔ {info['key']} non créé : {e}")
                        j.sauver_etat(etat)
            if "exec_id" not in etat:
                etat["exec_id"], etat["exec_key"] = x.create_execution(info["projet"], d["exec_summary"], tids,
                                                                       d.get("envs") or [])
                j.sauver_etat(etat)
            if not etat.get("exec_dans_plan"):
                x.add_execs_to_plan(etat["plan_id"], [etat["exec_id"]])
                etat["exec_dans_plan"] = True
                j.sauver_etat(etat)
        par_issue = x.test_runs(etat["exec_id"], tids)
        etat["runs"] = {k: par_issue[i] for k, i in etat["ids"].items() if i in par_issue}
        etat["tests_inconnus_xray"] = [k for k in d.get("cles_tests") or [] if k not in etat["ids"]]
        etat["prepare"] = True
        j.sauver_etat(etat)
        self.journaliser("info", f"{etat['mode']} — exécution {etat['exec_key']}"
                         + (f", plan {etat['plan_key']}" if etat.get("plan_key") else ""), etat=etat)
        for k in etat["tests_inconnus_xray"]:
            self.journaliser("avertissement", f"Tag {k} : test introuvable dans Xray, non remonté.")
        for w in etat["avertissements"]:
            self.journaliser("avertissement", w)


class _VerrouFichier:
    """Un seul synchroniseur à la fois par dossier (listener et commande de rejeu)."""

    def __init__(self, chemin: Path):
        self.chemin = chemin
        self.fh = None

    def __enter__(self):
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(self.chemin, "w")
        try:
            import fcntl

            fcntl.flock(self.fh, fcntl.LOCK_EX)
        except ImportError:  # Windows : pas de verrou inter-processus
            pass
        return self

    def __exit__(self, *exc):
        try:
            import fcntl

            fcntl.flock(self.fh, fcntl.LOCK_UN)
        except ImportError:
            pass
        self.fh.close()


def envoyer_artefacts(outbox_dir: str | Path, sortie: str | Path, rapport: dict | None, mode: str = "") -> dict:
    """Après la fin de Robot (log.html et report.html n'existent qu'à ce moment) : zip des résultats joint aux
    test runs (mode « tous », « echecs » ou « aucun », variable XRAY_ARTEFACTS). Passe par le journal :
    idempotent, rejouable par xray-sync ; une erreur n'interrompt jamais le run."""
    import zipfile

    mode = (mode or os.environ.get("XRAY_ARTEFACTS", "tous")).strip().lower()
    if mode == "aucun" or not rapport:
        return {"mode": mode, "envoye": False}
    tests = rapport.get("tests") or []
    cles = sorted({t["cle_xray"] for t in tests if t.get("cle_xray") and (mode == "tous" or t.get("statut_robot") == "FAIL")})
    sortie = Path(sortie)
    fichiers = [sortie / n for n in ("output.xml", "log.html", "report.html") if (sortie / n).exists()]
    if not cles or not fichiers:
        return {"mode": mode, "envoye": False, "raison": "aucun test run concerné ou aucun fichier"}
    archive = sortie / "robot-resultats.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for f in fichiers:
            z.write(f, f.name)
    max_mo = float(os.environ.get("XRAY_ARTEFACTS_MAX_MO", 10))
    if archive.stat().st_size > max_mo * 1024 * 1024:
        return {"mode": mode, "envoye": False, "raison": f"archive de plus de {max_mo:g} Mo (XRAY_ARTEFACTS_MAX_MO)"}
    Journal(outbox_dir).ajouter("artefacts", "artefacts", "robot-resultats", fichier=str(archive), cles=cles)
    bilan = Synchroniseur(outbox_dir).envoyer_tout()
    return {"mode": mode, "envoye": not bilan["restants"], "test_runs": cles, "fichier": archive.name, **bilan}
