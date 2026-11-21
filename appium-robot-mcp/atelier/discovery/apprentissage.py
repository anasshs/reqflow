"""Discovery piloté par un agent (Cursor ou Claude via le MCP) : ce que l'agent comprend de l'application est déposé
dans le Knowledge Graph sous forme de **propositions** (déduites, à valider), avec leur provenance (agent, session).

- nom_ecran        : nom métier et module proposés pour un écran (appliqués seulement à la validation) ;
- fonctionnalite, parcours : nœud relié à l'écran (le nœud « contient » l'écran) ;
- regle, action, role, entite : nœud relié à l'écran (l'écran « contient » le nœud) ;
- lien_exigence    : l'exigence Jira « impacte » l'écran (clé présente dans la copie locale).

Les actions de l'agent sur le device pendant une session Discovery passent par le classement des actions
(classement.py) : interdites et sensibles refusées (la confirmation d'une action sensible est humaine, dans la
fenêtre Discovery), contrôlées selon l'environnement de la session ; les comportements observés sont enregistrés.
Hors session Discovery, les outils MCP gardent leur comportement historique (construction de tests).
"""
from __future__ import annotations

import re
from datetime import datetime

NATURES = ("nom_ecran", "fonctionnalite", "parcours", "regle", "action", "role", "entite", "lien_exigence")
CONTIENT_ECRAN = ("fonctionnalite", "parcours")
AGENTS = ("cursor", "claude_code", "claude", "ia", "automaticien")


def _slug(t: str) -> str:
    from atelier.discovery import carte

    return carte.slug(t, 50)


def _contexte(agent: str) -> tuple[str, str]:
    from atelier.discovery import sessions_discovery

    s = sessions_discovery.active()
    sid = s["id"] if s else ""
    nom = {"cursor": "Cursor", "claude_code": "Claude Code", "claude": "Claude Desktop", "ia": "IA", "automaticien": "Automaticien"}.get(agent, agent)
    return sid, f"{nom} (MCP)" + (f" · session {sid}" if sid else "")


def proposer(nature: str, libelle: str, ecran: str = "", description: str = "", module: str = "", exigence: str = "",
             agent: str = "cursor") -> dict:
    """Dépose une proposition de l'agent ; rien n'est validé ni appliqué sans décision humaine."""
    from atelier.discovery import carte, sessions_discovery
    from atelier.domain import declarations

    if nature not in NATURES:
        raise ValueError(f"Nature : {', '.join(NATURES)}.")
    agent = agent if agent in AGENTS else "cursor"
    libelle = (libelle or "").strip()
    if not libelle and nature != "lien_exigence":
        raise ValueError("Libellé obligatoire.")
    sid, source = _contexte(agent)
    e = carte.ecran(ecran) if ecran else None
    if nature in ("nom_ecran", "lien_exigence") and not e:
        raise ValueError("Écran obligatoire (identifiant ou nom de la carte).")
    nid_ecran = f"ecran:{e.get('nom') or e['id']}" if e else ""
    out = {"nature": nature, "statut": "à valider", "source": source}

    if nature == "nom_ecran":
        props = e.setdefault("propositions_nom", [])
        if not any(p["nom"] == carte.slug(libelle) and p.get("module", "") == module for p in props):
            props.append({"nom": carte.slug(libelle), "module": module, "description": description[:300], "source": source,
                          "date": datetime.now().isoformat(timespec="seconds")})
            carte._save_ecran(e)
        out.update(ecran=e["id"], nom=carte.slug(libelle), module=module)
    elif nature == "lien_exigence":
        from atelier.intelligence import patrimoine_xray

        cle = (exigence or libelle).strip().upper()
        pat = patrimoine_xray.charger() or {"exigences": []}
        x = next((x for x in pat.get("exigences", []) if x["cle"] == cle), None)
        if not x:
            raise KeyError(f"Exigence {cle} absente de la copie locale Jira : synchroniser d'abord.")
        r = declarations.ajouter_relation(f"{x['type']}:{cle}", nid_ecran, "impacte", auteur="ia", source=source)
        out.update(id=r["id"])
    else:
        nid = f"{nature}:{_slug(libelle)}"
        try:
            declarations.ajouter_noeud(nid, nature, libelle[:150], description=description[:1000],
                                       proprietes={"origine": agent, "session": sid, "source_libelle": source, "ecran": e["id"] if e else ""},
                                       auteur="ia")
        except FileExistsError:
            pass  # déjà proposé : on ajoute seulement le lien à l'écran
        if e:
            de, vers = (nid, nid_ecran) if nature in CONTIENT_ECRAN else (nid_ecran, nid)
            try:
                declarations.ajouter_relation(de, vers, "contient", auteur="ia", source=source)
            except PermissionError:
                pass
        out.update(id=nid)
    if sid:
        sessions_discovery._evenement(sid, {"type": "proposition", "detail": f"{source} · {nature} : {libelle or exigence}"[:300],
                                            "ecran": e["id"] if e else ""})
    return out


def propositions(session: str = "") -> list[dict]:
    """Propositions à valider (déposées par un agent ou déduites des observations), filtrables par session."""
    from atelier.discovery import carte
    from atelier.domain import declarations

    d = declarations.charger()
    out = []
    for nid, n in d["noeuds"].items():
        p = n.get("proprietes") or {}
        if n.get("statut") == "à valider" and (not session or p.get("session") == session):
            out.append({"id": nid, "objet": "noeud", "type": n["type"], "libelle": n["libelle"], "source": p.get("source_libelle") or n.get("provenance"),
                        "ecran": p.get("ecran", "")})
    for rid, r in d["relations"].items():
        if r.get("statut") == "à valider" and (not session or session in (r.get("source") or "")):
            out.append({"id": rid, "objet": "relation", "type": r["type"], "libelle": f"{r['de']} — {r['type']} → {r['vers']}", "source": r.get("source", "")})
    try:
        for e in carte.ecrans() if carte.app_courante() else []:
            for p in e.get("propositions_nom") or []:
                if not session or session in p.get("source", ""):
                    out.append({"id": f"nom:{e['id']}:{p['nom']}", "objet": "nom_ecran", "type": "nom_ecran", "ecran": e["id"],
                                "libelle": f"{e.get('nom') or e.get('titre') or e['id']} → {p['nom']}" + (f" (module {p['module']})" if p.get("module") else ""),
                                "source": p.get("source", "")})
    except Exception:  # noqa: BLE001
        pass
    return out


def decider(pid: str, valider: bool, motif: str = "") -> dict:
    """Décision humaine sur une proposition : nœud / relation (validation ou rejet définitif), nom d'écran (appliqué)."""
    from atelier.discovery import carte

    if pid.startswith("nom:"):
        _, eid, nom = pid.split(":", 2)
        e = carte.ecran(eid)
        p = next((p for p in e.get("propositions_nom") or [] if p["nom"] == nom), None)
        if not p:
            raise KeyError("Proposition de nom inconnue.")
        e["propositions_nom"] = [x for x in e["propositions_nom"] if x is not p]
        carte._save_ecran(e)
        if valider:
            carte.renommer(eid, p["nom"], p.get("module") or None)
        return {"id": pid, "valide": valider}
    from atelier.discovery import espaces

    if valider:
        espaces.valider(pid)
    else:
        espaces.rejeter(pid, motif or "rejeté pendant la Discovery")
    return {"id": pid, "valide": valider}


def ecran_courant(ia_suggestions: bool = False) -> dict:
    """Pour l'agent : écran courant (carte), ses éléments avec leur classe et l'autorisation dans la session, les
    actions sûres jamais essayées et les pistes de la carte, les propositions de nom déjà faites."""
    from atelier.discovery import assistance, classement, comportements, session, sessions_discovery
    from atelier.discovery.observation import carte_active, observer

    if not session.plateforme() or not carte_active():
        raise RuntimeError("Aucun device ni navigateur, ou aucune application : start_session puis map_select_app.")
    s = sessions_discovery.active()
    env = (s or {}).get("config", {}).get("environnement", "")
    els = session.current_elements(150)
    obs = observer(els)
    r = classement.regles()
    elements = []
    for el in els:
        c = classement.classer(el, r=r)
        a = classement.autorise(el, "guidee", env) if s else {"autorise": True, "motif": "hors session Discovery"}
        elements.append({"cle": el["key"], "type": el.get("type"), "libelle": el.get("libelle", ""), "locator": (el.get("locators") or [""])[0],
                         "classe": c["classe"], "autorise": bool(a.get("autorise")), "motif": a.get("motif", "")})
    sug = assistance.suggerer(els, obs, session.etat["platform"], ia=ia_suggestions)
    from atelier.discovery import carte

    e = carte.ecran(obs["id"]) if obs else {}
    return {"session": {"id": s["id"], "statut": s["statut"], "environnement": env, "mode": s["config"]["mode"],
                        "perimetre": sug.get("perimetre")} if s else None,
            "ecran": {"id": obs.get("id"), "nom": obs.get("nom") or "", "titre": obs.get("titre") or "", "nouveau": obs.get("nouveau", False),
                      "module": e.get("module", ""), "propositions_nom": e.get("propositions_nom", [])} if obs else None,
            "elements": elements, "textes": [t for t in comportements.messages(comportements.etat_ecran())][:20],
            "a_essayer": [{"cle": x["cle"], "libelle": x["libelle"], "locator": x["locator"]} for x in sug["suggestions"]],
            "pistes": sug["pistes"]}


def action_mcp(nom: str, locator: str, fn):
    """Action de l'agent (tap, type_text), toujours classée côté serveur (V2, phase 0 bis) :
    - hors session Discovery : liste rouge et actions sensibles refusées ; navigation et saisie (contrôlée) permises ;
    - pendant une session : autorisée selon l'environnement de la session, puis comportements observés."""
    from atelier.discovery import classement, comportements, session, sessions_discovery
    from atelier.discovery.observation import observer

    s = sessions_discovery.active()
    if not s or s["statut"] != "En cours":
        try:
            ecran_ = comportements.etat_ecran()
        except Exception:  # noqa: BLE001 — écran illisible : classement sur le seul locator
            ecran_ = []
        el = next((e for e in ecran_ if locator in (e.get("locators") or [])), None) or {"key": re.sub(r"\W+", "_", locator)[:60], "libelle": "", "type": "element"}
        if nom == "type_text":
            el = {**el, "type": "champ"}
        v = classement.autorise(el, "guidee", "", False, None, agent=True)
        if not v["autorise"]:
            raise PermissionError(f"Action refusée (hors session Discovery) : {v.get('motif') or 'non autorisée'} "
                                  "Pour une action sensible, démarrer une session Discovery sur un environnement autorisé.")
        return fn()
    avant = comportements.etat_ecran()
    el = next((e for e in avant if locator in (e.get("locators") or [])), None) or {"key": re.sub(r"\W+", "_", locator)[:60], "libelle": "", "type": "element"}
    if nom == "type_text":
        el = {**el, "type": "champ"}
    interdite = sessions_discovery._interdite_session(s, el)
    v = {"autorise": False, "classe": "forbidden", "motif": f"action interdite pour la session (« {interdite} »)"} if interdite else \
        classement.autorise(el, "guidee", s["config"].get("environnement", ""), False, s["config"]["app"], agent=True)
    if not v["autorise"]:
        motif = v.get("motif") or "action refusée"
        sessions_discovery._evenement(s["id"], {"type": "refus", "detail": f"agent · {el.get('libelle') or el.get('key')} : {motif}"[:300]})
        raise PermissionError(f"Discovery {s['id']} : {motif}")
    ecran_avant = (observer([e for e in avant if e.get("key")]) or {}).get("id")
    if v.get("par_agent"):  # trace de chaque action sensible faite par l'agent
        a = v.get("autorisation") or {}
        sessions_discovery._evenement(s["id"], {"type": "sensible_agent", "detail": f"agent · {el.get('libelle') or el.get('key')} "
                                                f"(autorisé sur {s['config'].get('environnement')} par {a.get('par', '?')} le {str(a.get('date', ''))[:10]})"[:300]})
    res = fn()
    try:
        apres = comportements.etat_ecran()
        obs = observer([e for e in apres if e.get("key")]) or {}
        comps = comportements.comparer(avant, apres, el.get("libelle") or el.get("key"))
        if obs.get("id") != ecran_avant:
            comps = [c for c in comps if c["type"] == "message"]
        for c in comps[:20]:
            sessions_discovery._evenement(s["id"], {"type": "comportement", "detail": f"{c['type'].replace('_', ' ')} : {c['detail']}", "ecran": obs.get("id")})
        comportements.proposer_regles(comps, obs.get("nom") or obs.get("id", ""))
    except Exception:  # noqa: BLE001 - l'observation ne fait jamais échouer l'action
        pass
    return res

