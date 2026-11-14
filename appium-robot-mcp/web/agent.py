"""
Agent de construction de tests (API Claude) pour l'interface web.

Il réutilise les outils du serveur MCP (server.py) et ajoute :
  - proposer_step : chaque step Gherkin est proposé puis validé ou corrigé dans l'interface ;
  - approbation obligatoire avant toute écriture de fichier dans le projet ;
  - surlignage de l'élément visé sur l'écran du device avant chaque action.
"""
from __future__ import annotations

import base64
import inspect
import json
import os
import threading
import time
import typing
import uuid

import server as core

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")

SYSTEM = """Tu es l'automaticien d'une équipe QA bancaire (Robot Framework, Xray Cloud).
Mobile : AppiumLibrary sur Android et iOS. Web : Browser library (Playwright).
Tu construis des tests automatisés en pilotant un vrai device ou un vrai navigateur.

Conventions du projet, à respecter strictement :
- BDD en Gherkin français + Page Object Model : séparation locators / keywords / scénarios.
- La session est déjà ouverte (device ou navigateur). Ne lance pas de nouvelle session.
  En web, open_url sert à naviguer ; les locators suivent la syntaxe Browser library, par
  ordre de préférence : data-testid=, id=, css=…[name=…], role=…[name="…"], text="…".
  Le .resource web contient &{LOC_<ECRAN>_WEB} ; keywords Browser : Click, Fill Text, Get Text…
- Tu produis la couche locators avec capture_screen_locators puis generate_locators_resource :
  mêmes clés métier sur Android et iOS (ex. champ_montant, bouton_valider).
- Keywords : réutilise d'abord le socle générique du projet (lis-le avec list_project_files /
  read_project_file). Jamais de keyword wrapper 1:1 par élément.
- Données : passées en dictionnaire. Chaque test se lit en 2 blocs : INITIALISATION
  (« Initialiser Le Test » avec un jeu de données &{JDD_<NOM>}) puis SCÉNARIO en Gherkin sans
  donnée littérale. N'invente jamais de données : utilise list_jdd / get_jdd / check_jdd, et si
  aucun jeu ne convient, propose la structure du jeu à créer.
- Tags : la clé Xray du test + tags fonctionnels (smoke, e2e, negatif, consomme_donnee).
- Un seul scénario end-to-end par suite.

Carte de l'application : commence par where_am_i et list_screens. Pour aller sur un écran connu,
utilise goto_screen au lieu de naviguer à la main ; pour ses locators, screen_info (inutile de
réanalyser l'écran). N'explore que ce que la carte ne connaît pas, et nomme les nouveaux écrans
(name_screen). Les .resource se génèrent depuis la carte (export_screen_resource).

Méthode :
1. Si une clé de test Xray est donnée, lis-la avec xray_get_test : ses étapes sont le parcours.
2. Lis les keywords et steps existants du projet.
3. Pour chaque étape : get_screen_elements (ou screenshot si besoin), agis sur le device
   (tap, type_text, swipe…), vérifie le résultat, puis appelle proposer_step avec le step
   Gherkin, le keyword utilisé ou à créer et les clés de locators. Attends la validation ;
   si l'utilisateur corrige, applique sa correction.
4. À chaque nouvel écran stabilisé, capture_screen_locators avec les seules clés utiles.
5. En fin de parcours : generate_locators_resource, écriture des steps / de la suite
   (write_project_file, soumis à approbation), puis run_robot en dry_run.
Réponds en français, de façon concise. Préfère les locators id / accessibility_id ; signale
les locators fragiles (XPath, texte)."""

EXPOSED = ["where_am_i", "goto_screen", "screen_info", "list_screens", "name_screen", "export_screen_resource",
           "get_screen_elements", "screenshot", "check_locator", "tap", "type_text", "swipe",
           "press_back", "wait_for", "element_at", "open_url", "capture_screen_locators",
           "add_screen_locator", "generate_locators_resource",
           "list_project_files", "read_project_file", "write_project_file", "xray_get_test",
           "list_jdd", "get_jdd", "check_jdd", "find_test_data", "run_robot"]
ACTIONS = {"tap", "type_text", "wait_for", "check_locator"}


def _json_type(t) -> dict:
    origin = typing.get_origin(t)
    args = [a for a in typing.get_args(t) if a is not type(None)]
    if origin in (typing.Union, getattr(__import__("types"), "UnionType", None)) and args:
        return _json_type(args[0])
    if t is str:
        return {"type": "string"}
    if t is bool:
        return {"type": "boolean"}
    if t is int:
        return {"type": "integer"}
    if t is float:
        return {"type": "number"}
    if t is dict or origin is dict:
        return {"type": "object"}
    if t is list or origin is list:
        return {"type": "array", "items": _json_type(args[0]) if args else {}}
    return {}


def _schema(fn) -> dict:
    hints = typing.get_type_hints(fn)
    props, required = {}, []
    for name, p in inspect.signature(fn).parameters.items():
        props[name] = _json_type(hints.get(name, str))
        if p.default is inspect.Parameter.empty:
            required.append(name)
    return {"type": "object", "properties": props, "required": required}


def build_tools() -> list[dict]:
    tools = [{"name": n, "description": (inspect.getdoc(getattr(core, n)) or n)[:1000],
              "input_schema": _schema(getattr(core, n))} for n in EXPOSED]
    tools += [
        {"name": "proposer_step",
         "description": "Propose un step Gherkin construit à partir de l'action réalisée sur le device. "
                        "Bloque jusqu'à validation ou correction par l'utilisateur.",
         "input_schema": {"type": "object", "required": ["gherkin"], "properties": {
             "gherkin": {"type": "string", "description": "Ex. « Quand je saisis le montant du virement »"},
             "keyword": {"type": "string", "description": "Keyword réutilisé ou à créer"},
             "locators": {"type": "array", "items": {"type": "string"}},
             "commentaire": {"type": "string"}}}},
        {"name": "terminer",
         "description": "Termine la construction avec un résumé de ce qui a été produit.",
         "input_schema": {"type": "object", "required": ["resume"],
                          "properties": {"resume": {"type": "string"}}}},
    ]
    return tools


class Agent:
    def __init__(self, emit):
        self.emit = emit                      # emit(dict) -> diffusion WebSocket
        self.messages: list = []
        self.steps: list = []
        self.pending: dict | None = None
        self.stop_flag = threading.Event()
        self.thread: threading.Thread | None = None
        self.tools = build_tools()

    # ------------------------------------------------------------------ cycle
    @property
    def busy(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def start(self, instruction: str):
        if self.busy:
            raise RuntimeError("L'agent travaille déjà.")
        self.stop_flag.clear()
        last = self.messages[-1] if self.messages else None
        if last and last["role"] == "user" and isinstance(last["content"], list):
            last["content"].append({"type": "text", "text": instruction})  # après des tool_result
        else:
            self.messages.append({"role": "user", "content": instruction})
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_flag.set()
        if self.pending:
            self.answer(self.pending["id"], "refuser", "Arrêt demandé par l'utilisateur.")

    def reset(self):
        self.stop()
        self.messages, self.steps = [], []

    def answer(self, pending_id: str, decision: str, texte: str = ""):
        p = self.pending
        if not p or p["id"] != pending_id:
            raise KeyError("Aucune validation en attente avec cet identifiant.")
        p["reponse"] = (decision, texte)
        p["event"].set()

    def _wait_user(self, kind: str, payload: dict):
        pid = uuid.uuid4().hex[:8]
        self.pending = {"id": pid, "event": threading.Event(), "reponse": None,
                        "payload": {"nature": kind, **payload}}
        self.emit({"type": "attente", "id": pid, "nature": kind, **payload})
        while not self.pending["event"].wait(0.5):
            if self.stop_flag.is_set():
                break
        decision, texte = self.pending["reponse"] or ("refuser", "Arrêt demandé.")
        self.pending = None
        self.emit({"type": "attente_fin", "id": pid, "decision": decision})
        return decision, texte

    # ------------------------------------------------------------------ outils
    def _highlight(self, locator: str, label: str):
        try:
            box = core._rect_ratio(locator)
            if box:
                self.emit({"type": "surlignage", "label": label, **box})
                time.sleep(0.7)  # laisse le temps de voir l'élément visé
        except Exception:
            pass

    def _run_tool(self, name: str, args: dict):
        if name == "proposer_step":
            step = {"n": len(self.steps) + 1, **args, "statut": "proposé"}
            self.steps.append(step)
            decision, texte = self._wait_user("step", {"step": step})
            step["statut"] = {"valider": "validé", "corriger": "corrigé"}.get(decision, "refusé")
            if texte:
                step["correction"] = texte
            self.emit({"type": "step", "step": step})
            return {"decision": step["statut"], "correction": texte}
        if name == "terminer":
            self.emit({"type": "termine", "resume": args.get("resume", "")})
            return "ok"
        if name == "write_project_file":
            decision, texte = self._wait_user("fichier", {"chemin": args.get("path"),
                                                         "contenu": args.get("content", "")[:20000]})
            if decision != "valider":
                return {"ecrit": False, "retour_utilisateur": texte or "refusé"}
        if name == "run_robot":  # le run de l'agent s'affiche aussi en direct dans l'onglet Exécuter
            args.setdefault("events_url", f"http://127.0.0.1:{os.environ.get('WEB_PORT', '8765')}/api/events")
        if name in ACTIONS and args.get("locator"):
            self._highlight(args["locator"], name)

        result = getattr(core, name)(**args)

        if name == "screenshot" or name in ACTIONS | {"swipe", "press_back", "open_url"}:
            self.emit({"type": "ecran_change"})
        if name in ("capture_screen_locators", "generate_locators_resource", "add_screen_locator"):
            self.emit({"type": "locators_change"})
        return result

    def _tool_content(self, name: str, result):
        if name == "screenshot":
            png = core.screenshot_png()
            return [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                 "data": base64.b64encode(png).decode()}}]
        text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
        return text[:15000]

    # ------------------------------------------------------------------ boucle Claude
    def _client(self):
        import anthropic

        ca = os.environ.get("XRAY_CA_BUNDLE")
        if ca:
            import httpx

            return anthropic.Anthropic(http_client=httpx.Client(verify=ca, timeout=120))
        return anthropic.Anthropic()

    def _loop(self):
        client = self._client()
        self.emit({"type": "agent_etat", "etat": "travaille"})
        try:
            for _ in range(80):
                if self.stop_flag.is_set():
                    break
                resp = client.messages.create(model=MODEL, max_tokens=4000, system=SYSTEM,
                                              tools=self.tools, messages=self.messages)
                self.messages.append({"role": "assistant", "content": resp.content})
                for b in resp.content:
                    if b.type == "text" and b.text.strip():
                        self.emit({"type": "agent_texte", "texte": b.text})
                if resp.stop_reason != "tool_use":
                    break
                results = []
                for b in resp.content:
                    if b.type != "tool_use":
                        continue
                    self.emit({"type": "outil", "nom": b.name, "args": b.input})
                    try:
                        out = self._run_tool(b.name, b.input)
                        content, err = self._tool_content(b.name, out), False
                    except Exception as e:
                        content, err = f"Erreur : {e}", True
                        self.emit({"type": "outil_erreur", "nom": b.name, "erreur": str(e)})
                    results.append({"type": "tool_result", "tool_use_id": b.id,
                                    "content": content, "is_error": err})
                self.messages.append({"role": "user", "content": results})
                if any(b.type == "tool_use" and b.name == "terminer" for b in resp.content):
                    break
        except Exception as e:
            self.emit({"type": "agent_erreur", "erreur": str(e)})
        finally:
            self.emit({"type": "agent_etat", "etat": "pret"})
