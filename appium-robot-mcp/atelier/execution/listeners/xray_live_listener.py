"""
Listener Robot Framework (API v3) — remontée Xray Cloud en temps réel, découplée du run.

Usage (le MCP le branche tout seul ; utilisable aussi en CI) :
    robot --listener /chemin/xray_live_listener.py:/chemin/xray_run_config.json tests/

Déroulé : chaque événement est d'abord écrit dans le journal du run
(`<output_dir>/xray_outbox.jsonl`, voir atelier/execution/journal_xray.py), puis envoyé à Xray par
un thread de synchronisation avec reprise :
  début du run   -> préparation de la cible (plan / exécution / autre / projet), transition Jira ;
  début de test  -> test run en EXECUTING + heure de début (startedOn) ;
  fin de test    -> PASSED / FAILED (+ message d'échec en commentaire, captures en preuve)
                    + heure de fin (finishedOn) ;
  fin du run     -> transition Jira de fin (ou de fin en échec), rapport JSON.
En fin de run, le listener attend au plus XRAY_SYNC_DELAI_FIN secondes (30 par défaut) ; ce qui
n'a pas pu partir reste dans le journal : `python -m atelier xray-sync <output_dir>`.

Sans ticket Xray, le listener sert uniquement au suivi en direct (events_url).
Le rattachement se fait par les tags de clé Xray portés par les tests (ex. ATTIJARI-100).
Aucune erreur Xray/Jira n'interrompt le run.
"""
from __future__ import annotations

import glob
import json
import os
import queue
import sys
import threading
import time
import urllib.request
import uuid

# Racine de l'outil (le listener est chargé par chemin depuis un sous-processus Robot).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from atelier.execution.journal_xray import Journal, Synchroniseur, statuts_xray  # noqa: E402
from atelier.integrations import interface_web  # noqa: E402
from atelier.integrations.xray import KEY_RE, now_iso  # noqa: E402

GRAVITE = {"SKIP": 0, "NOT RUN": 0, "PASS": 1, "FAIL": 2}  # agrégation sur les statuts Robot


def _deepest_fail(item, path: list) -> list:
    for child in getattr(item, "body", []) or []:
        if getattr(child, "status", None) == "FAIL":
            name = getattr(child, "name", None) or type(child).__name__
            return _deepest_fail(child, path + [str(name)])
    return path


class xray_live_listener:  # même nom que le module : Robot instancie cette classe
    ROBOT_LISTENER_API_VERSION = 3

    def __init__(self, config_path: str):
        with open(config_path, encoding="utf-8") as f:
            self.cfg = json.load(f)
        self.depth = 0
        self.run_id = uuid.uuid4().hex[:12]
        self.debut_xray: dict = {}    # clé Xray -> startedOn (premier test Robot rattaché)
        self.statut_robot: dict = {}  # clé Xray -> statut Robot agrégé (FAIL > PASS > SKIP)
        self.statuts = statuts_xray()
        self.test_t0: dict = {}       # id test Robot -> timestamp epoch (pour les captures)
        self.journal: list = []
        self.tests: list = []
        self._written = False
        self.kw_depth = 0
        self._events: queue.Queue = queue.Queue()
        if self.cfg.get("events_url"):
            threading.Thread(target=self._sender, daemon=True).start()
        dossier_journal = self.cfg.get("outbox_dir") or self.cfg["output_dir"]
        self.outbox = Journal(dossier_journal) if self.cfg.get("ticket") else None
        self.synchro: Synchroniseur | None = None
        self._reveil = threading.Event()
        self._fin = threading.Event()
        self._fil: threading.Thread | None = None
        self.bilan_synchro: dict = {}
        if self.outbox:
            self.synchro = Synchroniseur(dossier_journal, journaliser=self._journal_synchro)
            self._fil = threading.Thread(target=self._boucle_synchro, daemon=True)
            self._fil.start()

    # ------------------------------------------------------------------ événements web
    def _emit(self, kind: str, **data):
        if self.cfg.get("events_url"):
            self._events.put({"type": kind, "heure": now_iso(), **data})

    def _sender(self):
        while True:
            ev = self._events.get()
            if ev is None:
                return
            try:
                req = urllib.request.Request(self.cfg["events_url"], data=json.dumps(ev).encode(),
                                             headers=interface_web.entetes(), method="POST")
                urllib.request.urlopen(req, timeout=2).read()
            except Exception:
                pass  # l'interface peut être fermée : le run continue
            finally:
                self._events.task_done()

    # ------------------------------------------------------------------ journal et synchronisation
    def _log(self, niveau: str, msg: str):
        self.journal.append({"heure": now_iso(), "niveau": niveau, "message": msg})
        self._emit("journal", niveau=niveau, message=msg)
        sys.__stdout__.write(f"[Xray] {msg}\n")
        sys.__stdout__.flush()

    def _journal_synchro(self, niveau: str, msg: str, etat: dict | None = None):
        self._log(niveau, msg)
        if etat:
            self._emit("xray", mode=etat.get("mode"), execution=etat.get("exec_key"), plan=etat.get("plan_key"))

    def _ecrire(self, type_ev: str, test: str = "", **donnees):
        try:
            self.outbox.ajouter(self.run_id, type_ev, test, **donnees)
        except Exception as e:  # disque plein… : jamais d'interruption du run
            self._log("erreur", f"Journal Xray non écrit ({type_ev}) : {e}")
        self._reveil.set()

    def _boucle_synchro(self):
        while not self._fin.is_set():
            self._reveil.wait(1.0)
            self._reveil.clear()
            try:
                self.bilan_synchro = self.synchro.envoyer_tout()
            except Exception as e:
                self._log("erreur", f"Synchronisation Xray : {e}")
        try:  # dernier passage après la fin du run
            self.bilan_synchro = self.synchro.envoyer_tout()
        except Exception as e:
            self._log("erreur", f"Synchronisation Xray : {e}")

    def _etat(self) -> dict:
        try:
            return self.outbox.etat() if self.outbox else {}
        except Exception:
            return {}

    # ------------------------------------------------------------------ suite
    def start_suite(self, data, result):
        self.depth += 1
        if self.depth != 1:
            return
        self._emit("run_debut", suite=data.name,
                   tests=[{"id": t.id, "nom": t.name, "tags": list(t.tags)} for t in data.all_tests])
        if not self.outbox:
            return
        keys = sorted({t for test in data.all_tests for t in test.tags if KEY_RE.match(t)})
        if not keys:
            self._log("avertissement", "Aucun tag de clé Xray sur les tests sélectionnés.")
        self._ecrire("preparation", ticket=self.cfg["ticket"], cles_tests=keys,
                     exec_summary=self.cfg["exec_summary"], plan_summary=self.cfg.get("plan_summary", ""),
                     envs=self.cfg.get("test_environments") or [])
        if self.cfg.get("transition_start"):
            self._ecrire("transition", moment="début", nom=self.cfg["transition_start"])

    def end_suite(self, data, result):
        self.depth -= 1
        if self.depth == 0:
            if self.outbox:
                failed = "FAIL" in self.statut_robot.values()
                end = (self.cfg.get("transition_end_if_fail") if failed else "") \
                    or self.cfg.get("transition_end", "")
                if end:
                    self._ecrire("transition", moment="fin", nom=end)
            self._emit("run_fin", statut=result.status,
                       stats={"passes": result.statistics.passed, "echecs": result.statistics.failed})

    # ------------------------------------------------------------------ test
    @staticmethod
    def _cle(data) -> str | None:
        return next((t for t in data.tags if KEY_RE.match(t)), None)

    def start_test(self, data, result):
        self.test_t0[data.id] = time.time()
        key = self._cle(data) if self.outbox else None
        self._emit("test_debut", id=data.id, nom=data.name, cle_xray=key,
                   statut_xray="EXECUTING" if key else None)
        if not key or key in self.debut_xray:
            return  # déjà EXECUTING (plusieurs tests Robot pour une même clé Xray)
        self.debut_xray[key] = now_iso()
        self._ecrire("test_debut", data.id, cle_xray=key, debut=self.debut_xray[key])

    def end_test(self, data, result):
        key = self._cle(data) if self.outbox else None
        finished = now_iso()
        echec = result.status == "FAIL"
        captures: list[str] = []
        if echec:  # captures produites pendant ce test (AppiumLibrary ou Browser library)
            t0 = self.test_t0.get(data.id, 0)
            captures = sorted((p for p in glob.glob(os.path.join(self.cfg["output_dir"], "**", "*.png"),
                                                    recursive=True) if os.path.getmtime(p) >= t0),
                              key=os.path.getmtime)[-5:]
        kw_fautif = " > ".join(_deepest_fail(result, [])) if echec else ""
        agg = None
        if key:
            previous = self.statut_robot.get(key, "NOT RUN")
            pire = result.status if GRAVITE.get(result.status, 0) >= GRAVITE.get(previous, 0) else previous
            self.statut_robot[key] = pire
            agg = self.statuts.get(pire, "TO DO")
        etat = self._etat()
        run_id = (etat.get("runs") or {}).get(key)
        self.tests.append({"test": data.name, "cle_xray": key, "statut_robot": result.status,
                           "statut_xray": agg, "debut": self.debut_xray.get(key) if key else None,
                           "fin": finished, "run_id": run_id})
        self._emit("test_fin", id=data.id, nom=data.name, cle_xray=key, statut=result.status,
                   statut_xray=agg, message=result.message[:1500],
                   keyword_en_echec=kw_fautif, run_id=run_id,
                   captures=[os.path.relpath(p, self.cfg["output_dir"]) for p in captures],
                   execution=etat.get("exec_key"),
                   debut=self.debut_xray.get(key) if key else None, fin=finished)
        if not key:
            return
        comment = None
        if echec:
            platform = ", ".join(self.cfg.get("test_environments") or [])
            comment = (f"Test Robot : {data.name}" + (f"\nPlateforme : {platform}" if platform else "")
                       + (f"\nKeyword en échec : {kw_fautif}" if kw_fautif else "")
                       + f"\nÉchec : {result.message[:2000]}")
        self._ecrire("test_fin", data.id, cle_xray=key, statut=agg, debut=self.debut_xray.get(key),
                     fin=finished, commentaire=comment,
                     captures=captures if self.cfg.get("attach_screenshots", True) else [])

    # ------------------------------------------------------------------ keywords (RF 7+)
    def start_keyword(self, data, result):
        self.kw_depth += 1
        if self.kw_depth <= 3:  # étapes BDD + 2 niveaux de keywords : lisible en direct
            self._emit("kw_debut", nom=getattr(result, "full_name", None) or result.name,
                       args=[str(a) for a in getattr(data, "args", ())][:6], niveau=self.kw_depth)

    def end_keyword(self, data, result):
        if self.kw_depth <= 3:
            self._emit("kw_fin", nom=result.name, statut=result.status, niveau=self.kw_depth)
        self.kw_depth -= 1

    # ------------------------------------------------------------------ fin
    def close(self):
        if self._fil:
            self._fin.set()
            self._reveil.set()
            self._fil.join(float(os.environ.get("XRAY_SYNC_DELAI_FIN", 30)))
            if self._fil.is_alive():  # Xray toujours injoignable : on rend la main, le journal reste
                self.synchro.arret.set()
                self._fil.join(5)
            restants = len(self.outbox.restants())
            if restants:
                self._log("avertissement", f"{restants} événement(s) Xray non envoyé(s) : "
                                           f"python -m atelier xray-sync {self.outbox.dossier}")
        self._write_report()
        if self.cfg.get("events_url"):
            self._events.put(None)
            time.sleep(0.5)

    def _write_report(self):
        if self._written or not self.cfg.get("report"):
            return
        self._written = True
        etat = self._etat()
        runs = etat.get("runs") or {}
        for t in self.tests:  # run_id connus seulement une fois la cible préparée
            t["run_id"] = t["run_id"] or runs.get(t["cle_xray"])
        rapport = {"ticket": self.cfg.get("ticket"),
                   "mode": etat.get("mode"),
                   "plan": etat.get("plan_key"),
                   "execution": etat.get("exec_key"),
                   "tests_inconnus_xray": etat.get("tests_inconnus_xray", []),
                   "tests": self.tests, "journal": self.journal,
                   "synchro": {"journal": self.outbox and str(self.outbox.fichier),
                               "restants": len(self.outbox.restants()) if self.outbox else 0}}
        with open(self.cfg["report"], "w", encoding="utf-8") as f:
            json.dump(rapport, f, ensure_ascii=False, indent=2)
