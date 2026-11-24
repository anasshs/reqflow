"""Atelier en Kanban : un backlog de sujets (parcours métier, User Stories) et les tickets tests qu'ils produisent, une
colonne par état, des filtres (sujet, type, texte).

Tickets
  parcours  sujet à couvrir : À faire → En conception (exploration par l'agent) ; ensuite couvert, il sert de filtre.
  us        User Story à couvrir : À faire → En conception (l'agent conçoit les tests qui manquent à l'existant).
  test      un scénario BDD : À faire (sans étapes) → En conception → BDD prêt → En automatisation → Automatisé → En run
            → Dans Xray.
Un test appartient à un parcours (maintenance.du_parcours) et/ou à une US : tag Gherkin @<US>, exigence du scénario, ou
créé pendant le travail de l'US. Filtrer sur un sujet montre ses tickets ; un nouveau test rejoint sa colonne.

L'état d'un ticket se déduit de ce qui existe (étapes, tests Robot portant sa clé, clé Xray publiée). Déplacer un ticket
déclenche l'action de la colonne visée, comme une transition Jira ; « Lancer » sur un sujet fait tout d'un clic :
couvrir (explorer le parcours / concevoir les tests de l'US) puis automatiser les tests produits. Chaque action longue est
un travail de l'orchestrateur : le ticket reste dans la colonne visée avec un indicateur tant qu'il avance ; un échec
reste affiché ; une transition impossible est refusée avec la raison. La publication dans Xray reste la décision de
l'utilisateur (flux simple, generation/flux.py)."""
from __future__ import annotations

from datetime import datetime

COLONNES = [("a_faire", "À faire"), ("conception", "En conception"), ("bdd_pret", "BDD prêt"), ("automatisation", "En automatisation"),
            ("automatise", "Automatisé"), ("en_run", "En run"), ("dans_xray", "Dans Xray")]
ORDRE = {c: i for i, (c, _) in enumerate(COLONNES)}
TYPES = {"parcours": "Parcours", "us": "User Story", "test": "Test"}

CONSIGNE_CONCEVOIR = ("Conçois le scénario BDD {cle} (« {titre} ») avec le MCP de l'atelier : lis le parcours et les écrans connus "
                      "(studio_scenario_bdd, discovery_parcours_cadre si le scénario vient d'un parcours), écris des étapes Gherkin en "
                      "français, sans donnée littérale (jeu de données), avec au moins un résultat vérifié (Alors). Ne publie rien.")
CONSIGNE_AUTOMATISER = ("Automatise le scénario BDD {cle} (« {titre} ») avec le MCP de l'atelier : studio_socle, "
                        "studio_scenario_bdd(\"{cle}\"), studio_generer_depuis_bdd(\"{cle}\", ecrire=True) ; complète les keywords "
                        "restés « À implémenter » dans le socle sans wrapper 1:1, range chaque fichier dans la structure du dépôt, "
                        "garde le tag {cle} sur le test, puis vérifie en dry_run. Ne publie rien dans Xray.")
CONSIGNE_US = ("Couvre la User Story {cle} « {titre} »{criteres} avec le MCP de l'atelier. Regarde d'abord ce qui la couvre déjà "
               "(test_design_cas_us(\"{cle}\") si Jira est relié, scénarios BDD et tests existants) : ne crée que les scénarios BDD "
               "qui manquent, un par comportement à vérifier, avec le tag @{cle} sur la fonctionnalité, des étapes en français "
               "sans donnée littérale et au moins un résultat vérifié (Alors). Ne publie rien.")
CONSIGNE_AUTOMATISER_SUJET = ("Automatise chaque scénario BDD {quoi} qui n'a pas encore de test Robot, avec le MCP de l'atelier : "
                              "studio_socle, puis pour chacun studio_generer_depuis_bdd(cle, ecrire=True) ; complète les keywords restés "
                              "« À implémenter » sans wrapper 1:1, range les fichiers dans la structure du dépôt, garde la clé du scénario "
                              "en tag, vérifie en dry_run. Ne publie rien dans Xray.")


# =========================================================================== backlog (User Stories ajoutées)
def _fichier():
    from atelier.domain import projet

    return projet.PROJECT_DIR / "conception" / "kanban.yaml"


def _lire() -> dict:
    import yaml

    f = _fichier()
    try:
        d = (yaml.safe_load(f.read_text("utf-8")) or {}) if f.exists() else {}
    except (OSError, yaml.YAMLError):
        d = {}
    d.setdefault("us", {})
    return d


def _ecrire(d: dict):
    import yaml

    f = _fichier()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), "utf-8")


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _infos_us(cle: str) -> dict:
    """Titre et critères connus de l'US (Jira suivi par la testabilité, sinon copie locale Xray)."""
    try:
        from atelier.intelligence import testabilite_us

        u = testabilite_us._us().get(cle) or {}
        if u:
            return {"titre": u.get("resume") or "", "criteres": u.get("criteres") or u.get("description") or ""}
    except Exception:  # noqa: BLE001 — testabilité non configurée
        pass
    try:
        from atelier.intelligence import patrimoine_xray

        e = next((x for x in (patrimoine_xray.charger_vue() or {}).get("exigences", []) if x.get("cle") == cle), None)
        if e:
            return {"titre": e.get("resume") or "", "criteres": ""}
    except Exception:  # noqa: BLE001
        pass
    return {}


def ajouter_us(cle: str, titre: str = "", criteres: str = "", lancer: bool = False, automatiser: bool = True) -> dict:
    """Ajoute une User Story au backlog (À faire) ; lancer=True la couvre tout de suite (et automatise ses tests)."""
    import re

    cle = str(cle or "").strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*-\d+", cle):
        raise ValueError("Clé de User Story attendue, ex. DEMO-123.")
    d = _lire()
    avant, connu = d["us"].get(cle, {}), _infos_us(cle)
    d["us"][cle] = {**avant, "titre": (titre or connu.get("titre") or avant.get("titre") or cle).strip(),
                    "criteres": (criteres or connu.get("criteres") or avant.get("criteres") or "").strip(),
                    "ajoute": avant.get("ajoute") or _maintenant()}
    _ecrire(d)
    return {"sujet": cle, **(lancer_sujet(cle, automatiser) if lancer else {})}


def retirer_us(cle: str) -> dict:
    d = _lire()
    if cle not in d["us"]:
        raise KeyError(f"User Story absente du backlog : {cle}")
    del d["us"][cle]
    _ecrire(d)
    return {"retire": cle}


# =========================================================================== tableau
_BOITE: dict = {}  # statut des demandes à l'agent, relu à chaque tableau


def _travaux_par_ticket() -> dict:
    from atelier.execution import orchestrateur
    from atelier.integrations import boite_cursor

    try:
        _BOITE.clear()
        _BOITE.update({d["id"]: d.get("statut") for d in boite_cursor.etat(200)["demandes"]})
    except Exception:  # noqa: BLE001 — boîte illisible : l'indicateur dit seulement « en cours »
        pass

    out: dict = {}
    for t in orchestrateur.lister():  # du plus récent au plus ancien
        k = (t.get("origine") or {}).get("kanban")
        if k and k not in out:
            out[k] = t
    return out


def _indicateur(t: dict | None) -> dict | None:
    if not t or t["statut"] in ("termine", "annule"):
        return None
    e = next((x for x in t["etapes"] if x["statut"] not in ("fait", "annule")), None)
    etape = (e or {}).get("titre", "")
    if t["statut"] == "en_cours":
        attente = (e or {}).get("statut")
        texte = {"attente_ressource": "attend le téléphone", "attente_decision": "à décider"}.get(attente, "en cours")
        if e and e.get("type") == "ia" and e.get("demande") and _BOITE.get(e["demande"]) == "en attente":
            texte = "en attente de l'agent"
        return {"etat": "decision" if attente == "attente_decision" else "en_cours", "travail": t["id"],
                "texte": f"{etape} · {texte}", "colonne": (t.get("origine") or {}).get("colonne", "")}
    return {"etat": "echec", "travail": t["id"], "texte": f"{etape} : {(e or {}).get('erreur') or 'échec'}"[:300], "colonne": ""}


def _tags(m: dict) -> set:
    tags = set(m.get("tags") or []) | {g for s in m.get("scenarios") or [] for g in s.get("tags") or []}
    return {str(g).lstrip("@").upper() for g in tags} | {str(x).upper() for x in m.get("exigences") or []}


def _ticket_test(m: dict, tests: list[dict], cle_xray: str, travail: dict | None, sujets: list[str]) -> dict:
    etapes = sum(len(s.get("etapes") or []) for s in m.get("scenarios") or [])
    reelle = "dans_xray" if cle_xray and tests else "automatise" if tests else "bdd_pret" if etapes else "a_faire"
    ind = _indicateur(travail)
    col = ind["colonne"] if ind and ind["etat"] != "echec" and ind["colonne"] in ORDRE else reelle
    dernier = next((t.get("dernier") for t in tests if t.get("dernier")), None)
    return {"type": "test", "id": m["cle"], "cle": m["cle"], "titre": m.get("titre") or m["cle"], "colonne": col, "colonne_reelle": reelle,
            "xray": cle_xray, "etapes": etapes, "tests": [t["id"] for t in tests], "sujets": sujets,
            "dernier_run": dernier and {"statut": dernier.get("statut"), "fin": dernier.get("fin"), "message": (dernier.get("message") or "")[:200]},
            "indicateur": ind}


def _ticket_sujet(type_: str, id_: str, nom: str, detail: str, tests: list[dict], travail: dict | None, explore: bool = False) -> dict:
    ind = _indicateur(travail)
    en_cours = bool(ind and ind["etat"] in ("en_cours", "decision")) or explore
    etat = "conception" if en_cours else "couvert" if tests else "a_faire"
    par_col = {c: sum(t["colonne"] == c for t in tests) for c, _ in COLONNES}
    return {"type": type_, "id": id_, "cle": id_, "titre": nom, "detail": detail, "etat": etat,
            "colonne": None if etat == "couvert" else etat, "indicateur": ind, "tests": len(tests), "par_colonne": par_col,
            "dans_xray": par_col["dans_xray"]}


def tableau() -> dict:
    """Colonnes, tickets (sujets du backlog et tests) et sujets (pour le filtre) de l'application active."""
    from atelier.discovery import carte, parcours_utilisateur as pu
    from atelier.generation import bdd, conception, flux, lots, maintenance

    colonnes = [dict(zip(("id", "titre"), c)) for c in COLONNES]
    app = carte.app_courante()
    if not app:
        return {"colonnes": colonnes, "tickets": [], "sujets": [], "application": "", "flux": flux.etat(), "types": TYPES}
    par_bdd, _ = lots._index_tests()
    travaux = _travaux_par_ticket()
    slug = carte.slug(app)
    parcours = [p for p in pu._tous(app) if not p.get("archive")]
    backlog = _lire()["us"]
    modeles = []
    for b in bdd.lister():
        m = bdd.charger(b["cle"]) or {}
        tests = par_bdd.get(b["cle"], [])
        if not (m.get("parcours") or m.get("session") or (m.get("application") or "") in (app, slug) or m.get("lot")
                or any(t["suite"].startswith(f"tests/{slug}/") for t in tests) or _tags(m) & set(backlog)):
            continue  # scénario d'une autre application
        modeles.append(({**m, "cle": b["cle"], "cree_le": m.get("cree") or b.get("maj") or ""}, tests))

    # à quels sujets appartient chaque test
    sujets_de: dict = {m["cle"]: [] for m, _ in modeles}
    for p in parcours:
        ref = {"id": p["id"], "nom": p.get("nom") or p["id"], "noeud": p.get("noeud", ""),
               "sessions_ids": [x if isinstance(x, str) else x.get("id") for x in p.get("sessions", [])]}
        for m, _ in modeles:
            if maintenance.du_parcours(m, ref):
                sujets_de[m["cle"]].append(p["id"])
    for cle_us, u in backlog.items():
        tr = travaux.get(cle_us)
        for m, _ in modeles:
            liee = cle_us in _tags(m)
            if not liee and tr and not sujets_de[m["cle"]]:  # créé pendant le travail de l'US, sans autre sujet
                liee = bool(m.get("cree_le")) and m["cree_le"] >= tr.get("cree", "9")
            if liee and cle_us not in sujets_de[m["cle"]]:
                sujets_de[m["cle"]].append(cle_us)

    tests = [_ticket_test(m, t, conception.cle_xray_du_scenario(m["cle"]), travaux.get(m["cle"]), sujets_de[m["cle"]]) for m, t in modeles]
    sujets = []
    propositions = _lire().get("propositions") or {}
    for p in sorted(parcours, key=lambda x: x.get("modifie") or "", reverse=True):
        les_tests = [t for t in tests if p["id"] in t["sujets"]]
        detail = " → ".join(x for x in (p.get("point_depart"), p.get("resultat_attendu")) if x) or f"{len(p.get('ecrans', []))} écran(s)"
        sujets.append({**_ticket_sujet("parcours", p["id"], p.get("nom") or p["id"], detail, les_tests, travaux.get(p["id"]),
                                       pu.statut(p) == "En cours"),
                       "a_qualifier": len((propositions.get(p["id"]) or {}).get("chemins") or [])})
    for cle_us, u in sorted(backlog.items(), key=lambda x: x[1].get("ajoute") or "", reverse=True):
        les_tests = [t for t in tests if cle_us in t["sujets"]]
        sujets.append(_ticket_sujet("us", cle_us, u.get("titre") or cle_us, (u.get("criteres") or "")[:160], les_tests, travaux.get(cle_us)))
    tickets = [s for s in sujets if s["colonne"]] + tests
    return {"colonnes": colonnes, "tickets": tickets, "sujets": sujets, "application": app, "flux": flux.etat(), "types": TYPES}


def _ticket(id_: str) -> dict:
    t = tableau()
    for x in t["tickets"] + t["sujets"]:
        if x["id"] == id_:
            return x
    raise KeyError(f"Ticket inconnu : {id_}")


# =========================================================================== actions
def _travail(titre: str, etapes: list[dict], kanban: str, colonne: str) -> dict:
    from atelier.execution import orchestrateur
    from atelier.integrations import boite_cursor

    agent = boite_cursor.agent()
    for e in etapes:
        if e["type"] == "ia":
            e.setdefault("agent", agent)
    t = orchestrateur.creer(titre, etapes, origine={"type": "kanban", "kanban": kanban, "colonne": colonne, "ecran": f"#atelier/{kanban}"})
    return {"travail": t["id"], "etapes": [e["titre"] for e in t["etapes"]]}


def _deja_en_cours(x: dict):
    if x.get("indicateur") and x["indicateur"]["etat"] in ("en_cours", "decision"):
        raise ValueError(f"Une action est déjà en cours sur ce ticket ({x['indicateur']['texte']}) : la suivre dans Mes demandes.")


def lancer_sujet(id_: str, automatiser: bool = True) -> dict:
    """Un clic sur un sujet : le couvrir (explorer le parcours et extraire son test / concevoir les tests qui manquent à
    l'US), puis, si automatiser, automatiser les tests produits."""
    from atelier.discovery import parcours_utilisateur as pu

    x = _ticket(id_)
    if x["type"] == "test":
        raise ValueError("Un test se fait avancer en le déplaçant de colonne.")
    _deja_en_cours(x)
    if x["type"] == "parcours":
        p = pu._lire(id_)
        etapes = [{"titre": "Dérouler le parcours", "type": "ia",
                   "params": {"texte": pu.demande_cursor(p) + " Termine par atelier_demande_terminee avec les écrans traversés.",
                              "attendus": ["discovery_terminer"]}},
                  {"titre": "Extraire le test", "type": "atelier", "action": "brouillon_bdd", "params": {"parcours": id_, "titre": p.get("nom") or ""}}]
        if automatiser:
            etapes += [{"titre": "Automatiser le test", "type": "ia",
                        "params": {"texte": CONSIGNE_AUTOMATISER.format(cle="{bdd}", titre=p.get("nom") or id_), "attendus": ["studio_generer_depuis_bdd"]}},
                       {"titre": "Dry-run", "type": "atelier", "action": "dry_run", "params": {}}]
        return _travail(f"Parcours « {p.get('nom') or id_} »", etapes, id_, "conception")
    u = _lire()["us"][id_]
    crit = f" (critères d'acceptation : {u['criteres']})" if u.get("criteres") else ""
    etapes = [{"titre": "Concevoir les tests de l'US", "type": "ia",
               "params": {"texte": CONSIGNE_US.format(cle=id_, titre=u.get("titre") or id_, criteres=crit), "attendus": ["atelier_demande_terminee"]}}]
    if automatiser:
        etapes.append({"titre": "Automatiser les tests de l'US", "type": "ia",
                       "params": {"texte": CONSIGNE_AUTOMATISER_SUJET.format(quoi=f"portant le tag @{id_}"), "attendus": ["studio_generer_depuis_bdd"]}})
    return _travail(f"US {id_} « {u.get('titre') or id_} »", etapes, id_, "conception")


def deplacer(id_: str, colonne: str, xray=None) -> dict:
    """Transition d'un ticket vers une colonne : déclenche l'action de cette colonne. Refusée (ValueError, avec la
    raison) si le workflow ne la permet pas depuis l'état réel du ticket, ou si une action est déjà en cours."""
    from atelier.generation import flux, tnr

    if colonne not in ORDRE:
        raise ValueError(f"Colonne inconnue : {colonne}")
    c = _ticket(id_)
    if c["type"] != "test":
        if colonne != "conception":
            raise ValueError("Un sujet se lance vers « En conception » : ses tests apparaissent ensuite dans leurs colonnes.")
        return {"ticket": c, "action": "travail", **lancer_sujet(id_)}
    _deja_en_cours(c)
    reelle, titre, cle = c["colonne_reelle"], c["titre"], c["cle"]
    if colonne == reelle:
        return {"ticket": c, "action": None}
    if colonne in ("conception", "bdd_pret"):
        if reelle != "a_faire":
            raise ValueError("Le scénario a déjà ses étapes : ouvrir le ticket pour les modifier.")
        r = _travail(f"Concevoir « {titre} »", [{"titre": "Concevoir le scénario BDD", "type": "ia",
                                                  "params": {"texte": CONSIGNE_CONCEVOIR.format(cle=cle, titre=titre), "attendus": ["atelier_demande_terminee"]}}],
                     cle, "conception")
    elif colonne == "automatisation":
        if reelle == "a_faire":
            raise ValueError("Scénario sans étapes : le concevoir d'abord (colonne « En conception »).")
        if ORDRE[reelle] >= ORDRE["automatise"]:
            raise ValueError("Déjà automatisé : pour le refaire, demander une maintenance depuis le ticket.")
        r = _travail(f"Automatiser « {titre} »", [
            {"titre": "Écrire le test Robot", "type": "ia", "params": {"texte": CONSIGNE_AUTOMATISER.format(cle=cle, titre=titre),
                                                                       "attendus": ["studio_generer_depuis_bdd"]}},
            {"titre": "Dry-run", "type": "atelier", "action": "dry_run", "params": {"bdd": cle}}], cle, colonne)
    elif colonne == "en_run":
        if ORDRE[reelle] < ORDRE["automatise"]:
            raise ValueError("Pas encore automatisé : passer d'abord par « En automatisation ».")
        r = _travail(f"Exécuter « {titre} »", [{"titre": "Run sur le téléphone", "type": "atelier", "action": "run",
                                                 "params": {"bdd": cle, "tests": c["tests"]}}], cle, colonne)
    elif colonne == "dans_xray":
        if ORDRE[reelle] < ORDRE["automatise"]:
            raise ValueError("Pas encore automatisé : l'automatiser avant de le publier dans Xray.")
        p = (flux.publier if flux.simple() else tnr.publier)([cle], xray=xray)
        if p["erreurs"]:
            raise ValueError("; ".join(f"{e['scenario']} : {e['erreur']}" for e in p["erreurs"]))
        return {"ticket": _ticket(cle), "action": "publie", "publies": p["publies"]}
    elif colonne == "automatise":
        raise ValueError("« Automatisé » se gagne : déplacer le ticket vers « En automatisation » pour que l'agent écrive le test.")
    else:  # a_faire
        raise ValueError("Retour à « À faire » impossible : ouvrir le ticket pour modifier le scénario.")
    return {"ticket": _ticket(cle), "action": "travail", **r}


def ajouter_parcours(nom: str, point_depart: str = "", resultat_attendu: str = "", objectif: str = "", lancer: bool = True,
                     automatiser: bool = True) -> dict:
    """Nouveau parcours métier dans le backlog ; lancer=True l'explore tout de suite (et automatise son test)."""
    from atelier.discovery import parcours_utilisateur as pu

    champs = {"nom": nom, **({"point_depart": point_depart} if point_depart else {}),
              **({"resultat_attendu": resultat_attendu} if resultat_attendu else {}), **({"objectif": objectif} if objectif else {})}
    p = pu.enregistrer("", champs)
    return {"sujet": p["id"], **(lancer_sujet(p["id"], automatiser) if lancer else {})}


def ticket(id_: str) -> dict:
    """Le détail d'un ticket. Test : scénario Gherkin, tests Robot, dernier run, Xray, historique. Sujet : ses tests par
    colonne et l'historique de ses travaux."""
    from atelier.execution import orchestrateur
    from atelier.generation import bdd

    t = tableau()
    x = next((y for y in t["tickets"] + t["sujets"] if y["id"] == id_), None)
    if not x:
        raise KeyError(f"Ticket inconnu : {id_}")
    historique = [{"id": w["id"], "titre": w["titre"], "statut": w["statut"], "cree": w.get("cree", ""),
                   "etapes": [{"titre": e["titre"], "statut": e["statut"], "resultat": e.get("resultat", ""), "erreur": e.get("erreur", ""),
                               "run_id": e.get("run_id", "")} for e in w["etapes"]]}
                  for w in orchestrateur.lister() if (w.get("origine") or {}).get("kanban") == id_][:10]
    if x["type"] != "test":
        les_tests = [{k: y[k] for k in ("id", "titre", "colonne", "xray")} for y in t["tickets"] if y["type"] == "test" and id_ in y["sujets"]]
        extra = details_parcours(id_) if x["type"] == "parcours" else {}
        return {**x, "tests_du_sujet": les_tests, "historique": historique, **extra}
    m = bdd.charger(id_) or {}
    try:
        gherkin = bdd.serialiser(m) if m else ""
    except Exception:  # noqa: BLE001
        gherkin = ""
    noms = {s["id"]: s["titre"] for s in t["sujets"]}
    return {**x, "gherkin": gherkin, "statut_bdd": m.get("statut", ""), "sujets_noms": [{"id": s, "titre": noms.get(s, s)} for s in x["sujets"]],
            "historique": historique}


# =========================================================================== actions sur un parcours (ticket)
def _parcours(pid: str) -> dict:
    from atelier.discovery import parcours_utilisateur as pu

    if not str(pid).startswith("PU-"):
        raise ValueError("Action réservée à un ticket parcours.")
    return pu._lire(pid)


def enrichir_mbt(pid: str) -> dict:
    """Enrichir par le MBT : construit (ou actualise) le modèle comportemental du parcours et propose les chemins que les
    tests existants ne couvrent pas encore. Ce sont des cartes « à qualifier » : rien n'entre dans le Kanban sans accord."""
    from atelier.intelligence import mbt

    p = _parcours(pid)
    if not p.get("noeud") or not p.get("ecrans"):
        raise ValueError("Parcours pas encore exploré : « Couvrir et automatiser » d'abord (le MBT part des écrans découverts).")
    m = mbt.construire("parcours", p["noeud"], auteur="atelier")
    a = mbt.analyser(m["id"])
    d = _lire()
    rejetes = set((d.get("rejets") or {}).get(pid) or [])
    props = [{"id": c["id"], "titre": c.get("titre") or c["id"], "type": c.get("type", ""), "priorite": c.get("priorite", ""),
              "valeur": c.get("valeur_ajoutee") or "", "justification": c.get("justification") or "", "hypothese": bool(c.get("hypothese")),
              "a_confirmer": len(c.get("manquant") or [])} for c in a.get("chemins") or [] if c["id"] not in rejetes]
    d.setdefault("propositions", {})[pid] = {"modele": m["id"], "date": _maintenant(), "chemins": props}
    _ecrire(d)
    return {"parcours": pid, "modele": m["id"], "propositions": props, "reutilises": len(a.get("reutilises") or [])}


def qualifier(pid: str, accepter: list[str] | None = None, rejeter: list[str] | None = None) -> dict:
    """Qualification des propositions MBT d'un parcours : les acceptées deviennent des scénarios BDD rattachés au parcours
    (cartes « BDD prêt »), les rejetées ne sont plus reproposées."""
    from atelier.generation import mbt_bdd

    _parcours(pid)
    d = _lire()
    prop = (d.get("propositions") or {}).get(pid)
    if not prop:
        raise ValueError("Aucune proposition à qualifier : « Enrichir par le MBT » d'abord.")
    connus = {c["id"] for c in prop["chemins"]}
    accepter = [x for x in accepter or [] if x in connus]
    rejeter = [x for x in rejeter or [] if x in connus and x not in accepter]
    crees = mbt_bdd.generer(prop["modele"], chemins=accepter, origine="MBT")["crees"] if accepter else []
    d = _lire()
    d.setdefault("rejets", {}).setdefault(pid, [])
    d["rejets"][pid] = sorted(set(d["rejets"][pid]) | set(rejeter))
    reste = [c for c in prop["chemins"] if c["id"] not in set(accepter) | set(rejeter)]
    if reste:
        d["propositions"][pid]["chemins"] = reste
    else:
        d["propositions"].pop(pid, None)
    _ecrire(d)
    return {"crees": [{"cle": c["cle"], "titre": c["titre"]} for c in crees], "rejetes": rejeter, "restantes": len(reste)}


def changer_jdd(pid: str, profil: str, relancer: bool = True) -> dict:
    """Change le profil de données du parcours et, si relancer, redéroule sa Discovery : d'autres données ouvrent d'autres
    écrans, donc d'autres scénarios. Les nouveaux tests rejoignent le Kanban (« BDD prêt ») ; l'existant n'est pas recréé."""
    from atelier.discovery import parcours_utilisateur as pu

    _parcours(pid)
    pu.enregistrer(pid, {"profil_donnees": profil})
    return {"parcours": pid, "profil_donnees": profil, **(lancer_sujet(pid, automatiser=False) if relancer else {})}


def rejouer(pid: str, xray: bool = False) -> dict:
    """Rejoue les tests automatisés du sujet : en local (run sur le téléphone, rien dans Xray), ou en exécution TNR (une
    Test Execution dans le plan TNR, statuts et preuves remontés dans Xray ; tests publiés seulement)."""
    from atelier.execution import centre
    from atelier.generation import tnr

    x = _ticket(pid)
    if x["type"] == "test":
        raise ValueError("Rejouer s'applique à un parcours ou une User Story.")
    _deja_en_cours(x)
    t = tableau()
    les_tests = [y for y in t["tickets"] if y["type"] == "test" and pid in y["sujets"] and y["tests"]]
    if xray:
        les_tests = [y for y in les_tests if y["xray"]]
    ids = sorted({i for y in les_tests for i in y["tests"]})
    if not ids:
        raise ValueError("Aucun test publié dans Xray pour ce sujet." if xray else "Aucun test automatisé pour ce sujet : l'automatiser d'abord.")
    params = {"tests": ids}
    if xray:
        conv = tnr.conventions()
        if not conv.get("campagne"):
            raise ValueError("Pas encore de campagne TNR : publier d'abord des tests dans Xray.")
        c = centre.campagne(conv["campagne"])
        base = centre.params_campagne(c, (c.get("plateformes") or ["android"])[0])
        jira = {"jira_transition_start": conv.get("transition_debut"), "jira_transition_end": conv.get("transition_fin"),
                "jira_champs_execution": tnr.payload_champs(conv.get("champs_execution") or {})}
        gardes = ("xray_ticket", "jdd_env", "jira_transition_start", "jira_transition_end", "jira_champs_execution")
        params["run_params"] = {**{k: v for k, v in base.items() if k in gardes}, **{k: v for k, v in jira.items() if v}}
    titre = f"Rejouer « {x['titre']} » ({'exécution TNR, Xray' if xray else 'en local'})"
    etape = {"titre": "Run TNR (Xray)" if xray else "Run sur le téléphone", "type": "atelier", "action": "run", "params": params}
    return {"tests": ids, **_travail(titre, [etape], pid, "")}


def details_parcours(pid: str) -> dict:
    """Ce que le ticket parcours affiche en plus : profil de données et profils disponibles, propositions MBT à qualifier,
    exécution TNR possible."""
    from atelier.discovery import parcours_utilisateur as pu
    from atelier.generation import tnr

    p = _parcours(pid)
    try:
        profils = [x["nom"] for x in pu.options().get("profils") or []]
    except Exception:  # noqa: BLE001
        profils = []
    prop = (_lire().get("propositions") or {}).get(pid) or {}
    try:
        campagne = bool(tnr.conventions().get("campagne"))
    except Exception:  # noqa: BLE001
        campagne = False
    return {"profil_donnees": p.get("profil_donnees", ""), "profils": profils, "explore": bool(p.get("ecrans")),
            "propositions": prop.get("chemins") or [], "propositions_date": prop.get("date", ""), "tnr_xray": campagne}
