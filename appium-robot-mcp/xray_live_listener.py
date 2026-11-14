"""
Listener Robot Framework (API v3) — remontée Xray Cloud en temps réel.

Usage (le MCP le branche tout seul ; utilisable aussi en CI) :
    robot --listener /chemin/xray_live_listener.py:/chemin/xray_run_config.json tests/

Déroulé :
  début du run   -> résout le ticket (plan / exécution / autre / projet), crée ou complète
                    l'exécution, transition Jira de début sur l'exécution ;
  début de test  -> test run en EXECUTING + heure de début (startedOn) ;
  fin de test    -> PASSED / FAILED (+ message d'échec en commentaire, captures en preuve)
                    + heure de fin (finishedOn) ;
  fin du run     -> transition Jira de fin (ou de fin en échec), rapport JSON.

Sans ticket Xray, le listener sert uniquement au suivi en direct (events_url).
Avec events_url, chaque événement (test, keyword, statut Xray) est envoyé à l'interface web.

Le rattachement se fait par les tags de clé Xray portés par les tests (ex. ATTIJARI-100).
Aucune erreur Xray/Jira n'interrompt le run : elles sont journalisées dans le rapport.
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from xray_client import KEY_RE, JiraClient, XrayClient, now_iso  # noqa: E402

STATUS = {"PASS": "PASSED", "FAIL": "FAILED", "SKIP": "TODO", "NOT RUN": "TODO"}
GRAVITE = {"TODO": 0, "PASSED": 1, "FAILED": 2}


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
        self.ctx: dict | None = None
        self.run_start: dict = {}     # run_id -> startedOn (premier test Robot rattaché)
        self.run_status: dict = {}    # run_id -> statut agrégé
        self.test_t0: dict = {}       # id test Robot -> timestamp epoch (pour les captures)
        self.journal: list = []
        self.tests: list = []
        self._written = False
        self.kw_depth = 0
        self._events: queue.Queue = queue.Queue()
        if self.cfg.get("events_url"):
            threading.Thread(target=self._sender, daemon=True).start()
        self.xray = None
        if self.cfg.get("ticket"):
            try:
                self.xray = XrayClient()
            except Exception as e:
                self._log("erreur", f"Xray désactivé : {e}")
        self.jira = JiraClient()

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
                                             headers={"Content-Type": "application/json"},
                                             method="POST")
                urllib.request.urlopen(req, timeout=2).read()
            except Exception:
                pass  # l'interface peut être fermée : le run continue
            finally:
                self._events.task_done()

    # ------------------------------------------------------------------ utilitaires
    def _log(self, niveau: str, msg: str):
        self.journal.append({"heure": now_iso(), "niveau": niveau, "message": msg})
        self._emit("journal", niveau=niveau, message=msg)
        sys.__stdout__.write(f"[Xray] {msg}\n")
        sys.__stdout__.flush()

    def _safe(self, what: str, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            self._log("erreur", f"{what} : {e}")
            return None

    def _run_id(self, data):
        if not self.ctx:
            return None, None
        for tag in data.tags:
            if KEY_RE.match(tag) and tag in self.ctx["runs"]:
                return tag, self.ctx["runs"][tag]
        return None, None

    def _transition(self, name: str, moment: str):
        if name and self.ctx and self.jira.enabled:
            cible = self._safe(f"transition Jira ({moment})", self.jira.transition,
                               self.ctx["exec_key"], name)
            if cible:
                self._log("info", f"{self.ctx['exec_key']} -> {cible} ({moment})")

    # ------------------------------------------------------------------ suite
    def start_suite(self, data, result):
        self.depth += 1
        if self.depth != 1:
            return
        self._emit("run_debut", suite=data.name,
                   tests=[{"id": t.id, "nom": t.name, "tags": list(t.tags)} for t in data.all_tests])
        if not self.xray:
            return
        keys = sorted({t for test in data.all_tests for t in test.tags if KEY_RE.match(t)})
        if not keys:
            self._log("avertissement", "Aucun tag de clé Xray sur les tests sélectionnés.")
        self.ctx = self._safe("préparation Xray", self.xray.prepare,
                              self.cfg["ticket"], keys, self.cfg["exec_summary"],
                              self.cfg.get("plan_summary", ""), self.cfg.get("test_environments"),
                              self.jira)
        if not self.ctx:
            return
        self._emit("xray", mode=self.ctx["mode"], execution=self.ctx["exec_key"],
                   plan=self.ctx["plan_key"])
        self._log("info", f"{self.ctx['mode']} — exécution {self.ctx['exec_key']}"
                          + (f", plan {self.ctx['plan_key']}" if self.ctx["plan_key"] else ""))
        for k in self.ctx["tests_inconnus_xray"]:
            self._log("avertissement", f"Tag {k} : test introuvable dans Xray, non remonté.")
        for w in self.ctx["avertissements"]:
            self._log("avertissement", w)
        self._transition(self.cfg.get("transition_start", ""), "début")

    def end_suite(self, data, result):
        self.depth -= 1
        if self.depth == 0:
            if self.ctx:
                failed = "FAILED" in self.run_status.values()
                end = (self.cfg.get("transition_end_if_fail") if failed else "") \
                    or self.cfg.get("transition_end", "")
                self._transition(end, "fin")
            self._emit("run_fin", statut=result.status,
                       stats={"passes": result.statistics.passed, "echecs": result.statistics.failed})
            self._write_report()

    # ------------------------------------------------------------------ test
    def start_test(self, data, result):
        self.test_t0[data.id] = time.time()
        key, run_id = self._run_id(data)
        self._emit("test_debut", id=data.id, nom=data.name, cle_xray=key,
                   statut_xray="EXECUTING" if run_id else None)
        if not run_id or run_id in self.run_start:
            return  # déjà EXECUTING (plusieurs tests Robot pour une même clé Xray)
        started = now_iso()
        self.run_start[run_id] = started
        self._safe(f"{key} début", self.xray.update_run, run_id, started=started)
        self._safe(f"{key} EXECUTING", self.xray.set_status, run_id, "EXECUTING")

    def end_test(self, data, result):
        key, run_id = self._run_id(data)
        finished = now_iso()
        status = STATUS.get(result.status, "TODO")
        echec = result.status == "FAIL"
        captures: list[str] = []
        if echec:  # captures produites pendant ce test (AppiumLibrary ou Browser library)
            t0 = self.test_t0.get(data.id, 0)
            captures = sorted((p for p in glob.glob(os.path.join(self.cfg["output_dir"], "**", "*.png"),
                                                    recursive=True) if os.path.getmtime(p) >= t0),
                              key=os.path.getmtime)[-5:]
        kw_fautif = " > ".join(_deepest_fail(result, [])) if echec else ""
        self.tests.append({"test": data.name, "cle_xray": key, "statut_robot": result.status,
                           "statut_xray": status if run_id else None,
                           "debut": self.run_start.get(run_id) if run_id else None,
                           "fin": finished, "run_id": run_id})
        self._emit("test_fin", id=data.id, nom=data.name, cle_xray=key, statut=result.status,
                   statut_xray=status if run_id else None, message=result.message[:1500],
                   keyword_en_echec=kw_fautif, run_id=run_id,
                   captures=[os.path.relpath(p, self.cfg["output_dir"]) for p in captures],
                   execution=self.ctx and self.ctx["exec_key"],
                   debut=self.run_start.get(run_id) if run_id else None, fin=finished)
        if not run_id:
            return
        previous = self.run_status.get(run_id, "TODO")
        agg = status if GRAVITE.get(status, 0) >= GRAVITE.get(previous, 0) else previous
        self.run_status[run_id] = agg

        comment = None
        if echec:
            platform = ", ".join(self.cfg.get("test_environments") or [])
            comment = (f"Test Robot : {data.name}" + (f"\nPlateforme : {platform}" if platform else "")
                       + (f"\nKeyword en échec : {kw_fautif}" if kw_fautif else "")
                       + f"\nÉchec : {result.message[:2000]}")
        self._safe(f"{key} fin", self.xray.update_run, run_id,
                   started=self.run_start.get(run_id), finished=finished, comment=comment)
        self._safe(f"{key} {agg}", self.xray.set_status, run_id, agg)
        if captures and self.cfg.get("attach_screenshots", True):
            self._safe(f"{key} preuves", self.xray.add_evidence, run_id, captures)
        self._log("info", f"{key} -> {agg} ({data.name})")

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

    # ------------------------------------------------------------------ rapport
    def close(self):
        self._write_report()
        if self.cfg.get("events_url"):
            self._events.put(None)
            time.sleep(0.5)

    def _write_report(self):
        if self._written or not self.cfg.get("report"):
            return
        self._written = True
        rapport = {"ticket": self.cfg.get("ticket"),
                   "mode": self.ctx and self.ctx["mode"],
                   "plan": self.ctx and self.ctx["plan_key"],
                   "execution": self.ctx and self.ctx["exec_key"],
                   "tests_inconnus_xray": self.ctx["tests_inconnus_xray"] if self.ctx else [],
                   "tests": self.tests, "journal": self.journal}
        with open(self.cfg["report"], "w", encoding="utf-8") as f:
            json.dump(rapport, f, ensure_ascii=False, indent=2)
