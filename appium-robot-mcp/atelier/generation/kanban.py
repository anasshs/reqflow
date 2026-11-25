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
l'utilisateur (flux simple, generation/flux.py).

Règles (décision de l'utilisateur, 2026-11-24)
  - Un test présent dans un scénario BDD est à automatiser, sauf s'il est marqué « ne pas automatiser » (décision
    actée) : il sort alors de l'écart. L'écart d'un sujet = ses tests BDD sans script Robot et non marqués.
  - « Automatiser » = l'agent écrit le script (MCP), puis dry-run, puis run local sur le téléphone.
  - « Dans Xray » = publication, puis exécution TNR du test (Test Execution dans le plan TNR).
  - Le jeu de données se change à tout moment : pour la Discovery et le MBT (profil du parcours), ou pour un run
    (ce run seulement) ; le jeu du dépôt ne change que si l'utilisateur valide le remplacement."""
from __future__ import annotations

from datetime import datetime

COLONNES = [("a_faire", "À faire"), ("conception", "En conception"), ("bdd_pret", "BDD prêt"), ("automatisation", "En automatisation"),
            ("automatise", "Automatisé"), ("en_run", "En run"), ("dans_xray", "Dans Xray"), ("maintenance", "À maintenir")]
ORDRE = {c: i for i, (c, _) in enumerate(COLONNES)}
TYPES = {"parcours": "Parcours", "us": "User Story", "test": "Test"}

CONSIGNE_CONCEVOIR = ("Conçois le scénario BDD {cle} (« {titre} ») avec le MCP de l'atelier : lis le parcours et les écrans connus "
                      "(studio_scenario_bdd, discovery_parcours_cadre si le scénario vient d'un parcours), écris des étapes Gherkin en "
                      "français, sans donnée littérale (jeu de données), avec au moins un résultat vérifié (Alors). Ne publie rien.")
CONSIGNE_AUTOMATISER = ("Automatise le scénario BDD {cle} (« {titre} ») avec le MCP de l'atelier : studio_socle, "
                        "studio_scenario_bdd(\"{cle}\"), studio_generer_depuis_bdd(\"{cle}\", ecrire=True{techno_arg}) ; complète les keywords "
                        "restés « À implémenter » dans le socle sans wrapper 1:1, range chaque fichier dans la structure du dépôt, "
                        "garde le tag {cle} sur le test, puis vérifie en dry_run. Ne publie rien dans Xray.")
CONSIGNE_US = ("Couvre la User Story {cle} « {titre} »{criteres} avec le MCP de l'atelier. Regarde d'abord ce qui la couvre déjà "
               "(test_design_cas_us(\"{cle}\") si Jira est relié, scénarios BDD et tests existants) : ne crée que les scénarios BDD "
               "qui manquent, un par comportement à vérifier, avec le tag @{cle} sur la fonctionnalité, des étapes en français "
               "sans donnée littérale et au moins un résultat vérifié (Alors). Ne publie rien.")
CONSIGNE_RATTRAPAGE = ("Couvre et automatise le sujet « {nom} » ({sid}) avec le MCP de l'atelier, sans aide humaine. {quoi} "
                       "Pour chacun : 1) vérifie qu'il n'est pas un doublon d'un test déjà automatisé ({couverts}) ; s'il l'est, "
                       "dis-le et ne l'automatise pas ; 2) si ses étapes sont brutes (issues de la Discovery : « je touche l'élément », "
                       "identifiants techniques), réécris-les en étapes métier qui reprennent les keywords existants "
                       "(studio_keywords_a_juger puis studio_juger_keywords), et associe un jeu de données ; 3) automatise-le : "
                       "studio_socle, studio_generer_depuis_bdd(cle, ecrire=True), keywords manquants dans les pages existantes "
                       "sans wrapper 1:1, fichiers rangés selon la structure du dépôt, clé du scénario gardée en tag ; 4) dry_run. "
                       "Ne publie rien dans Xray. Les actions sensibles et les données réelles sont permises en recette. "
                       "Termine par atelier_demande_terminee avec, pour chaque scénario, automatisé / doublon / impossible (raison).")
CONSIGNE_AUTOMATISER_SUJET = ("Automatise chaque scénario BDD {quoi} qui n'a pas encore de test Robot, avec le MCP de l'atelier : "
                              "studio_socle, puis pour chacun studio_generer_depuis_bdd(cle, ecrire=True) ; complète les keywords restés "
                              "« À implémenter » sans wrapper 1:1, range les fichiers dans la structure du dépôt, garde la clé du scénario "
                              "en tag, vérifie en dry_run. Ne publie rien dans Xray.")


def _techno_arg() -> str:
    """Technologie d'automatisation de l'application (fiche : automatisation.technologie_defaut) dans la consigne de
    l'agent ; rien pour les technologies Robot (comportement historique, déduit de l'application)."""
    from atelier.generation import technologies

    t = technologies.par_defaut()
    return "" if t.startswith("robot-") else f', technologie="{t}"'


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
    from atelier.discovery import carte

    d["us"][cle] = {**avant, "app": avant.get("app") or carte.app_courante() or "",
                    "titre": (titre or connu.get("titre") or avant.get("titre") or cle).strip(),
                    "criteres": (criteres or connu.get("criteres") or avant.get("criteres") or "").strip(),
                    "ajoute": avant.get("ajoute") or _maintenant()}
    _ecrire(d)
    return {"sujet": cle, **(lancer_sujet(cle, automatiser) if lancer else {})}


def marquer_manuel(cle: str, manuel: bool = True) -> dict:
    """« Ne pas automatiser » (décision actée) : le test sort de l'écart de son sujet et n'est plus proposé à
    l'automatisation ; manuel=False le remet dans l'écart."""
    from atelier.generation import bdd

    if not bdd.charger(cle):
        raise KeyError(f"Scénario inconnu : {cle}")
    d = _lire()
    l = set(d.get("manuels") or [])
    (l.add if manuel else l.discard)(cle)
    d["manuels"] = sorted(l)
    _ecrire(d)
    return {"cle": cle, "manuel": manuel}


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


def _ticket_test(m: dict, tests: list[dict], cle_xray: str, travail: dict | None, sujets: list[str], manuel: bool = False) -> dict:
    etapes = sum(len(s.get("etapes") or []) for s in m.get("scenarios") or [])
    reelle = "dans_xray" if cle_xray and tests else "automatise" if tests else "bdd_pret" if etapes else "a_faire"
    ind = _indicateur(travail)
    col = ind["colonne"] if ind and ind["etat"] != "echec" and ind["colonne"] in ORDRE else reelle
    dernier = next((t.get("dernier") for t in tests if t.get("dernier")), None)
    from atelier.generation import maintenir

    try:
        maint = maintenir.etat(m, dernier) if tests else None
    except Exception:  # noqa: BLE001 — état illisible : le ticket garde sa colonne
        maint = None
    flux_reelle = reelle
    if maint and maint.get("colonne"):
        reelle = "maintenance"  # dernier run réel en échec, ou maintenance pas encore confirmée
        col = ind["colonne"] if ind and ind["etat"] != "echec" and ind["colonne"] in ORDRE else reelle
    hist = m.get("maintenances") or []
    return {"type": "test", "id": m["cle"], "cle": m["cle"], "titre": m.get("titre") or m["cle"], "colonne": col, "colonne_reelle": reelle,
            "xray": cle_xray, "etapes": etapes, "tests": [t["id"] for t in tests], "sujets": sujets, "manuel": manuel,
            "jdd": m.get("jdd", ""), "colonne_flux": flux_reelle, "maintenance": maint,
            "maintenu": {"n": len(hist), "date": hist[-1].get("date", ""), "bdd_modifie": any(h.get("bdd_modifie") for h in hist)} if hist else None,
            "dernier_run": dernier and {"statut": dernier.get("statut"), "fin": dernier.get("fin"), "message": (dernier.get("message") or "")[:200],
                                        "output": dernier.get("output", "")},
            "indicateur": ind}


def _ticket_sujet(type_: str, id_: str, nom: str, detail: str, tests: list[dict], travail: dict | None, explore: bool = False) -> dict:
    ind = _indicateur(travail)
    en_cours = bool(ind and ind["etat"] in ("en_cours", "decision")) or explore
    ecart = [t["id"] for t in tests if t["colonne_reelle"] in ("a_faire", "bdd_pret") and not t.get("manuel")]
    etat = "conception" if en_cours else "a_faire" if not tests or ecart else "couvert"  # un écart le garde dans le backlog
    par_col = {c: sum(t["colonne"] == c for t in tests) for c, _ in COLONNES}
    return {"type": type_, "id": id_, "cle": id_, "titre": nom, "detail": detail, "etat": etat,
            "colonne": None if etat == "couvert" else etat, "indicateur": ind, "tests": len(tests), "par_colonne": par_col,
            "a_automatiser": ecart, "manuels": sum(bool(t.get("manuel")) for t in tests),
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
    from atelier.discovery import application

    connus = application.slugs()
    backlog = {k: u for k, u in _lire()["us"].items() if application.visible(u.get("app") or slug, slug, connus)}  # US de cette application
    modeles = []
    for b in bdd.lister():
        m = bdd.charger(b["cle"]) or {}
        tests = par_bdd.get(b["cle"], [])
        if not application.visible(application.du_scenario(m, [t["suite"] for t in tests], connus), slug, connus):
            continue  # scénario d'une autre application du projet
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

    manuels = set(_lire().get("manuels") or [])
    tests = [_ticket_test(m, t, conception.cle_xray_du_scenario(m["cle"]), travaux.get(m["cle"]), sujets_de[m["cle"]], m["cle"] in manuels)
             for m, t in modeles]
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
def _env() -> str:
    """Environnement des runs lancés depuis le Kanban : celui de la campagne TNR (recette), sinon aucun."""
    try:
        from atelier.execution import centre
        from atelier.generation import tnr

        conv = tnr.conventions()
        return (centre.campagne(conv["campagne"]).get("environnement") or "") if conv.get("campagne") else ""
    except Exception:  # noqa: BLE001
        return ""


def _params_xray() -> dict:
    """Paramètres d'une exécution TNR (Test Execution dans le plan TNR, transitions Jira, environnement)."""
    from atelier.execution import centre
    from atelier.generation import tnr

    conv = tnr.conventions()
    if not conv.get("campagne"):
        raise ValueError("Pas encore de campagne TNR : publier d'abord des tests dans Xray.")
    c = centre.campagne(conv["campagne"])
    base = centre.params_campagne(c, (c.get("plateformes") or ["android"])[0])
    jira = {"jira_transition_start": conv.get("transition_debut"), "jira_transition_end": conv.get("transition_fin"),
            "jira_champs_execution": tnr.payload_champs(conv.get("champs_execution") or {})}
    gardes = ("xray_ticket", "jdd_env", "jira_transition_start", "jira_transition_end", "jira_champs_execution")
    return {**{k: v for k, v in base.items() if k in gardes}, **{k: v for k, v in jira.items() if v}}


def _variante(cle: str, jdd: str) -> dict:
    """Jeu de données choisi pour un run seulement : {jeu du test: jeu choisi} (le dépôt ne change pas)."""
    from atelier.generation import bdd

    if not jdd:
        return {}
    base = (bdd.charger(cle) or {}).get("jdd") or ""
    if not base:
        raise ValueError("Ce scénario n'a pas de jeu de données : l'associer d'abord (ticket › jeu de données).")
    return {base: jdd} if jdd != base else {}


def tests_du_sujet(sid: str) -> list[str]:
    """Tests Robot automatisés du sujet (hors « ne pas automatiser »), pour ses runs."""
    t = tableau()
    return sorted({i for y in t["tickets"] if y["type"] == "test" and sid in y["sujets"] and not y.get("manuel") for i in y["tests"]})


def _travail(titre: str, etapes: list[dict], kanban: str, colonne: str) -> dict:
    from atelier.execution import orchestrateur
    from atelier.integrations import boite_cursor

    agent = boite_cursor.agent()
    for e in etapes:
        if e["type"] == "ia":
            e.setdefault("agent", agent)
    t = orchestrateur.creer(titre, etapes, origine={"type": "kanban", "kanban": kanban, "colonne": colonne, "ecran": f"#atelier/{kanban}"},
                            env=_env())
    return {"travail": t["id"], "etapes": [e["titre"] for e in t["etapes"]]}


def _deja_en_cours(x: dict):
    if x.get("indicateur") and x["indicateur"]["etat"] in ("en_cours", "decision"):
        raise ValueError(f"Une action est déjà en cours sur ce ticket ({x['indicateur']['texte']}) : la suivre dans Mes demandes.")


def _etapes_rattrapage(sid: str, nom: str, en_plus: str = "") -> list[dict]:
    """Étapes qui automatisent tout l'écart d'un sujet par le MCP : l'agent (doublons, étapes métier, script), puis
    dry-run et run local des tests du sujet."""
    t = tableau()
    x = next((y for y in t["sujets"] if y["id"] == sid), None) or {"a_automatiser": []}
    titres = {y["id"]: y["titre"] for y in t["tickets"] if y["type"] == "test"}
    ecart = ", ".join(f"{c} (« {titres.get(c, c)} »)" for c in x["a_automatiser"]) or "aucun pour l'instant"
    manuels = [y["id"] for y in t["tickets"] if y["type"] == "test" and sid in y["sujets"] and y.get("manuel")]
    couverts = ", ".join(sorted({y["xray"] or y["id"] for y in t["tickets"] if y["type"] == "test" and y["tests"]})) or "aucun"
    quoi = (f"Scénarios à automatiser : {en_plus}les scénarios BDD du sujet sans test Robot : {ecart}."
            + (f" Ne touche pas à ceux marqués « ne pas automatiser » : {', '.join(manuels)}." if manuels else ""))
    return [{"titre": "Compléter et automatiser (agent)", "type": "ia",
             "params": {"texte": CONSIGNE_RATTRAPAGE.format(nom=nom, sid=sid, quoi=quoi, couverts=couverts), "attendus": ["studio_generer_depuis_bdd"]}},
            {"titre": "Dry-run", "type": "atelier", "action": "dry_run", "params": {"sujet": sid}},
            {"titre": "Run local (téléphone)", "type": "atelier", "action": "run", "params": {"sujet": sid}}]


def rattraper(sid: str) -> dict:
    """« Automatiser ce qui manque » : tout l'écart du sujet passe par l'agent (MCP), puis dry-run et run local."""
    x = _ticket(sid)
    if x["type"] == "test":
        raise ValueError("Le rattrapage s'applique à un parcours ou une User Story.")
    _deja_en_cours(x)
    if not x["a_automatiser"]:
        raise ValueError("Rien à automatiser : tous les tests BDD du sujet ont un script (ou sont marqués « ne pas automatiser »).")
    return {"a_automatiser": x["a_automatiser"], **_travail(f"Rattrapage « {x['titre']} »", _etapes_rattrapage(sid, x["titre"]), sid, "")}


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
        if not p.get("environnement") and _env():  # sans environnement, la session appliquerait la liste rouge complète
            pu.enregistrer(id_, {"environnement": _env()})
            p = pu._lire(id_)
        cadrage = "" if (p.get("objectif") or p.get("point_depart") or p.get("resultat_attendu")) else (
            f" Le cadrage est vide : déduis l'objectif du nom du parcours (« {p.get('nom') or id_} »), pars de l'écran d'accueil "
            "de l'application connectée, déroule tous les cas que le nom annonce (ajout, consultation, modification, "
            "suppression…), et propose le point de départ et le résultat attendu (discovery_proposer).")
        donnees = (" Données : avant chaque formulaire, discovery_donnees_pour_champs. Si une donnée manque au référentiel, "
                   "propose-la avec discovery_donnee_proposer (valeur de test plausible au format du champ : nom fictif, RIB, "
                   "montant…) et saisis-la avec {{var:CLE}} : ne t'arrête pas faute de données. À la fin, discovery_profil_vers_jdd"
                   f"(profil du parcours, « {_env() or 'recette'} ») crée le jeu de données du test ; l'automaticien confirmera ou "
                   "changera ces valeurs.")
        etapes = [{"titre": "Dérouler le parcours", "type": "ia",
                   "params": {"texte": pu.demande_cursor(p) + cadrage + donnees + " Termine par atelier_demande_terminee avec les écrans traversés.",
                              "attendus": ["discovery_terminer"]}},
                  {"titre": "Extraire le test", "type": "atelier", "action": "brouillon_bdd", "params": {"parcours": id_, "titre": p.get("nom") or ""}}]
        if automatiser:
            etapes += _etapes_rattrapage(id_, p.get("nom") or id_, "le scénario {bdd} que l'atelier vient d'extraire, et ")
        return _travail(f"Parcours « {p.get('nom') or id_} »", etapes, id_, "conception")
    u = _lire()["us"][id_]
    crit = f" (critères d'acceptation : {u['criteres']})" if u.get("criteres") else ""
    etapes = [{"titre": "Concevoir les tests de l'US", "type": "ia",
               "params": {"texte": CONSIGNE_US.format(cle=id_, titre=u.get("titre") or id_, criteres=crit), "attendus": ["atelier_demande_terminee"]}}]
    if automatiser:
        etapes += _etapes_rattrapage(id_, u.get("titre") or id_, f"les scénarios portant le tag @{id_}, et ")
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
    if colonne == "maintenance":  # glisser vers « À maintenir » (ou dans la colonne, test à qualifier) : maintenance par le MCP
        from atelier.generation import maintenir

        if (c.get("maintenance") or {}).get("etat") not in (None, "a_qualifier", "echec_correction"):
            raise ValueError(f"Déjà en maintenance ({c['maintenance']['libelle']}) : ouvrir le ticket.")
        return {"ticket": c, "action": "travail", **maintenir.maintenir(cle, "")}
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
        if c.get("manuel"):
            raise ValueError("Marqué « ne pas automatiser » : retirer la marque dans le ticket pour l'automatiser.")
        r = _travail(f"Automatiser « {titre} »", [
            {"titre": "Écrire le test Robot", "type": "ia", "params": {"texte": CONSIGNE_AUTOMATISER.format(cle=cle, titre=titre, techno_arg=_techno_arg()),
                                                                       "attendus": ["studio_generer_depuis_bdd"]}},
            {"titre": "Dry-run", "type": "atelier", "action": "dry_run", "params": {"bdd": cle}},
            {"titre": "Run local (téléphone)", "type": "atelier", "action": "run", "params": {"bdd": cle}}], cle, colonne)
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
        execution = {}
        try:  # publié : une exécution TNR du test (Test Execution dans le plan TNR) remonte son résultat dans Xray
            execution = _travail(f"Exécution TNR « {titre} »", [{"titre": "Run TNR (Xray)", "type": "atelier", "action": "run",
                                                                  "params": {"bdd": cle, "run_params": _params_xray()}}], cle, "")
        except ValueError as e:
            execution = {"erreur": str(e)}
        return {"ticket": _ticket(cle), "action": "publie", "publies": p["publies"], "execution": execution}
    elif colonne == "automatise":
        raise ValueError("« Automatisé » se gagne : déplacer le ticket vers « En automatisation » pour que l'agent écrive le test.")
    else:  # a_faire
        raise ValueError("Retour à « À faire » impossible : ouvrir le ticket pour modifier le scénario.")
    return {"ticket": _ticket(cle), "action": "travail", **r}


def executer(cle: str, jdd: str = "", xray: bool = False) -> dict:
    """Run d'un test, avec un autre jeu de données si jdd (pour ce run seulement, le dépôt ne change pas), en local ou en
    exécution TNR (xray)."""
    c = _ticket(cle)
    if c["type"] != "test" or not c["tests"]:
        raise ValueError("Pas encore automatisé : passer d'abord par « En automatisation ».")
    _deja_en_cours(c)
    run_params = {**(_params_xray() if xray else {}), **({"jdd_variantes": _variante(cle, jdd)} if _variante(cle, jdd) else {})}
    titre = f"Exécuter « {c['titre']} »" + (f" avec {jdd}" if jdd else "") + (" (TNR, Xray)" if xray else "")
    return _travail(titre, [{"titre": "Run TNR (Xray)" if xray else "Run local (téléphone)", "type": "atelier", "action": "run",
                             "params": {"bdd": cle, "tests": c["tests"], "run_params": run_params}}], cle, "en_run")


def corriger(cle: str, consigne: str = "") -> dict:
    """Run en échec : maintenance par le MCP (generation/maintenir) avec l'indication de l'automaticien."""
    from atelier.generation import maintenir

    return maintenir.maintenir(cle, consigne)


def remplacer_jdd(cle: str, jdd: str) -> dict:
    """Remplacement validé par l'utilisateur : le jeu de données devient celui du scénario et de ses tests Robot
    (&{JDD_<ANCIEN>} → &{JDD_<NOUVEAU>}) pour les prochaines exécutions."""
    import re

    from atelier.domain import projet
    from atelier.generation import bdd

    c = _ticket(cle)
    m = bdd.charger(cle) or {}
    ancien = m.get("jdd") or ""
    if not jdd or jdd == ancien:
        raise ValueError("Choisir un autre jeu de données que celui du scénario.")
    bdd.associer_jdd(cle, jdd)
    modifies = []
    for tid in c.get("tests") or []:
        fichier, _, nom = tid.partition("::")
        f = projet.safe_path(fichier)
        lignes, dedans = f.read_text("utf-8").splitlines(keepends=True), False
        for i, l in enumerate(lignes):
            if l.strip() and not l[:1].isspace():
                dedans = l.strip() == nom
            elif dedans and "Initialiser Le Test" in l:
                nouvelle = re.sub(r"&\{JDD_[A-Za-z0-9_]+\}", "&{JDD_" + jdd + "}", l)
                if nouvelle != l:
                    lignes[i] = nouvelle
                    modifies.append(tid)
        f.write_text("".join(lignes), "utf-8")
    return {"cle": cle, "ancien": ancien, "jdd": jdd, "tests_modifies": modifies}


def ajouter_parcours(nom: str, point_depart: str = "", resultat_attendu: str = "", objectif: str = "", lancer: bool = True,
                     automatiser: bool = True) -> dict:
    """Nouveau parcours métier dans le backlog ; lancer=True l'explore tout de suite (et automatise son test)."""
    from atelier.discovery import parcours_utilisateur as pu

    champs = {"nom": nom, **({"environnement": _env()} if _env() else {}), **({"point_depart": point_depart} if point_depart else {}),
              **({"resultat_attendu": resultat_attendu} if resultat_attendu else {}), **({"objectif": objectif} if objectif else {})}
    p = pu.enregistrer("", champs)
    return {"sujet": p["id"], **(lancer_sujet(p["id"], automatiser) if lancer else {})}


def _resolveur_ecrans():
    """Trouve un écran de la carte par identifiant, nom, ancien identifiant ou alias — la carte lue une seule fois
    (carte.ecran relit toute la carte à chaque appel)."""
    from atelier.discovery import carte

    tous = carte.ecrans()

    def trouver(ref):
        if not str(ref or "").strip():
            return None
        ref_n = carte._norm(ref)
        for e in tous:
            if ref in (e.get("id"), e.get("nom")) or ref in (e.get("ids_fusionnes") or []) or ref_n in [carte._norm(a) for a in e.get("alias", [])] \
                    or (e.get("nom") and carte._norm(e["nom"]) == ref_n):
                return e
        return None
    return trouver


def ecrans_du_test(m: dict, tests: list[str], avec_robot: bool = False) -> list[dict]:
    """Écrans que le test traverse, dans l'ordre, avec leur vignette (capture de la Discovery) : écrans liés à ses étapes,
    sinon ceux de sa session Discovery, sinon ceux de son parcours. avec_robot : seulement les écrans que son test Robot
    couvre en plus (couverture des tests : graphe complet, calcul lent, demandé à l'ouverture de la section). Chaque
    écran dit d'où vient le lien."""
    from atelier.discovery import carte

    vus, out = set(), []
    try:
        trouver = _resolveur_ecrans()
        dossier_vignettes = carte._dir() / "vignettes"
    except Exception:  # noqa: BLE001 — pas d'application cartographiée
        return []

    def ajouter(ref, source, etape=""):
        try:
            e = trouver(ref)
        except (KeyError, ValueError, TypeError):
            return
        if not e or e["id"] in vus:
            return
        vus.add(e["id"])
        plats = list((e.get("plateformes") or {}).keys())
        vignette = next((f"{e['id']}_{p}.png" for p in plats if (dossier_vignettes / f"{e['id']}_{p}.png").exists()), "")
        out.append({"id": e["id"], "nom": e.get("nom") or "", "titre": e.get("titre") or "", "module": e.get("module") or "",
                    "vignette": vignette, "source": source, "etape": etape})

    if avec_robot:
        return _ecrans_robot(tests, ajouter, out)
    for s in m.get("scenarios") or []:
        for et in s.get("etapes") or []:
            if et.get("ecran"):
                ajouter(et["ecran"], "étape", f"{et.get('mot', '')} {et.get('texte', '')}".strip())
    if not out and m.get("session"):
        try:
            from atelier.generation import parcours_bdd

            for eid in parcours_bdd.ecrans_de_session(m["session"]):
                ajouter(eid, "session Discovery")
        except Exception:  # noqa: BLE001 — session illisible : on passe au parcours
            pass
    if not out and str(m.get("parcours") or "").startswith("PU-"):
        try:
            from atelier.discovery import parcours_utilisateur as pu

            for e in pu.obtenir(m["parcours"]).get("ecrans") or []:
                ajouter(e.get("id") or e.get("ecran") or "", "parcours")
        except Exception:  # noqa: BLE001
            pass
    return out


def _ecrans_robot(tests: list[str], ajouter, out: list) -> list[dict]:
    if tests:  # écrans couverts par le test Robot (graphe de couverture)
        try:
            from atelier.discovery import connaissance
            from atelier.intelligence import couverture_avancee as ca

            noms = {x.split("::", 1)[-1] for x in tests}
            g = connaissance.construire()
            for e in ca.calculer(g)["ecrans"]:
                if noms & set(e.get("tests_robot") or []):
                    cid = (g.noeuds.get(e.get("id")) or type("n", (), {"proprietes": {}})).proprietes.get("id_carte") or e.get("id_carte") or e.get("nom") or ""
                    ajouter(cid, "test Robot")
        except Exception:  # noqa: BLE001 — couverture indisponible : les écrans de la conception suffisent
            pass
    return out


def jeux_du_test(m: dict, tests: list[str], dernier_run: dict | None, historique: list[dict]) -> dict:
    """Jeux de données d'un test : celui du scénario, celui que ses tests Robot chargent maintenant (&{JDD_<jeu>} de
    « Initialiser Le Test » : le jeu branché), celui qu'a utilisé le dernier run (environnement, jeu choisi pour ce run
    seulement s'il y en a un, autres jeux chargés : connexion…), et celui d'un run lancé à l'instant depuis le ticket."""
    import json
    import re

    from atelier.domain import projet

    branches = []
    for tid in tests:
        fichier, _, nom = tid.partition("::")
        try:
            lignes, dedans = projet.safe_path(fichier).read_text("utf-8").splitlines(), False
        except (OSError, ValueError):
            continue
        for l in lignes:
            if l.strip() and not l[:1].isspace():
                dedans = l.strip() == nom
            elif dedans and "Initialiser Le Test" in l:
                branches += [j for j in re.findall(r"&\{JDD_([A-Za-z0-9_]+)\}", l) if j not in branches]
    out = {"scenario": m.get("jdd", ""), "branches": branches, "dernier": None, "lance": None}
    sortie = (dernier_run or {}).get("output") or ""
    if sortie:
        try:
            d = json.loads((projet.safe_path(sortie).parent / "bilan.json").read_text("utf-8"))
            p, j = d.get("params") or {}, (d.get("bilan") or {}).get("jdd") or {}
            variantes = p.get("jdd_variantes") or (p.get("contexte") or {}).get("profils_donnees") or {}
            charges = list(j.get("valeurs") or [])
            utilises = [variantes.get(b, b) for b in branches if b in charges or not charges] or [variantes.get(b, b) for b in branches]
            out["dernier"] = {"run": d.get("id", ""), "fin": d.get("fin") or (dernier_run or {}).get("fin", ""), "env": j.get("env") or p.get("jdd_env", ""),
                              "jeux": utilises, "variante": bool(set(variantes) & set(branches)),
                              "autres": [c for c in charges if c not in branches and c not in variantes.values()]}
        except (OSError, ValueError):  # run sans bilan (lancé par l'agent avec l'outil MCP) : le jeu branché, sans détail
            out["dernier"] = {"run": "", "fin": (dernier_run or {}).get("fin", ""), "env": "",
                              "jeux": branches, "variante": False, "autres": [], "sans_bilan": True}
    for w in historique:  # run lancé depuis le ticket, pas encore terminé : le jeu qu'il charge
        if w["statut"] not in ("a_faire", "en_cours"):
            continue
        for e in w.get("etapes_params") or []:
            v = ((e.get("params") or {}).get("run_params") or {}).get("jdd_variantes") or {}
            if e.get("action") == "run" and e.get("statut") not in ("fait", "annule"):
                out["lance"] = {"travail": w["id"], "jeux": [v.get(b, b) for b in branches] or list(v.values()), "variante": bool(v)}
                break
        if out["lance"]:
            break
    return out


def valeurs_jeux(noms, env: str) -> dict:
    """Valeurs de chaque jeu (pour les voir au survol) : un secret n'est jamais rendu, seule sa référence {{env:NOM}}
    ou « •••• » apparaît."""
    from atelier.execution import jdd as jdd_mod

    out = {}
    for n in sorted({x for x in noms if x}):
        try:
            brut = jdd_mod.lire(env, n)
        except (KeyError, OSError, ValueError):
            continue
        d = brut.get("donnees") if isinstance(brut, dict) and isinstance(brut.get("donnees"), dict) else brut if isinstance(brut, dict) else {}
        vals = {}
        for k, v in d.items():
            s = v if isinstance(v, str) else str(v)
            vals[str(k)] = s if s.startswith("{{") else "••••" if jdd_mod.CLE_SENSIBLE.search(str(k)) else s[:120]
        out[n] = {"env": env, "description": str((brut or {}).get("description") or "")[:200] if isinstance(brut, dict) else "", "valeurs": vals}
    return out


def committer(cle: str) -> dict:
    """Commit du code du test (suite, pages, locators, scénario, jeux) depuis le ticket, pour la merge request."""
    from atelier.generation import versionnement

    c = _ticket(cle)
    if c["type"] != "test":
        raise ValueError("Seul un ticket test se commite.")
    r = versionnement.committer([cle], xray={cle: c.get("xray") or ""})
    if not r.get("depot"):
        raise ValueError("Le projet de tests n'est pas un dépôt Git.")
    return r


def ecrans_robot(cle: str) -> list[dict]:
    """Écrans que le test Robot du ticket couvre en plus de son scénario (section repliée du ticket, calculée à la demande)."""
    from atelier.domain import memo
    from atelier.generation import bdd

    with memo.portee():
        c = _ticket(cle)
        return ecrans_du_test(bdd.charger(cle) or {}, c.get("tests") or [], avec_robot=True) if c["type"] == "test" else []


def ticket(id_: str) -> dict:
    from atelier.domain import memo

    with memo.portee():  # index des tests, inventaire du dépôt : une seule lecture pour tout le ticket
        return _ticket_detail(id_)


def _ticket_detail(id_: str) -> dict:
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
                               "run_id": e.get("run_id", "")} for e in w["etapes"]],
                   "etapes_params": [{"action": e.get("action", ""), "statut": e["statut"], "params": e.get("params") or {}} for e in w["etapes"]]}
                  for w in orchestrateur.lister() if (w.get("origine") or {}).get("kanban") == id_][:10]
    if x["type"] != "test":
        les_tests = [{k: y[k] for k in ("id", "titre", "colonne", "xray")} for y in t["tickets"] if y["type"] == "test" and id_ in y["sujets"]]
        extra = details_parcours(id_) if x["type"] == "parcours" else {}
        for w in historique:
            w.pop("etapes_params", None)
        return {**x, "tests_du_sujet": les_tests, "historique": historique, **extra}
    m = bdd.charger(id_) or {}
    try:
        gherkin = bdd.serialiser(m) if m else ""
    except Exception:  # noqa: BLE001
        gherkin = ""
    noms = {s["id"]: s["titre"] for s in t["sujets"]}
    try:
        from atelier.execution import jdd as jdd_mod

        jeux = [j["jeu"] for j in jdd_mod.lister(_env() or "recette")]
    except Exception:  # noqa: BLE001
        jeux = []
    jeux_test = jeux_du_test(m, x.get("tests") or [], x.get("dernier_run"), historique)
    jeux_test["valeurs"] = valeurs_jeux({*jeux_test["branches"], jeux_test["scenario"], *((jeux_test["dernier"] or {}).get("jeux") or []),
                                         *((jeux_test["dernier"] or {}).get("autres") or []), *((jeux_test["lance"] or {}).get("jeux") or []), *jeux},
                                        (jeux_test["dernier"] or {}).get("env") or _env() or "recette")
    try:
        from atelier.generation import versionnement

        git = versionnement.etat(id_)
    except Exception as e:  # noqa: BLE001 — Git illisible : le ticket s'affiche quand même
        git = {"depot": False, "erreur": str(e)[:200]}
    for w in historique:
        w.pop("etapes_params", None)
    from atelier.generation import maintenir

    return {**x, "gherkin": gherkin, "jeux": jeux, "jeux_test": jeux_test, "git": git, "maintenances": m.get("maintenances") or [],
            "causes": maintenir.CAUSES, "gherkin_avant": (m.get("maintenance") or {}).get("gherkin_avant", "") if (x.get("maintenance") or {}).get("bdd_modifie") else "",
            "ecrans": ecrans_du_test(m, x.get("tests") or []), "statut_bdd": m.get("statut", ""), "sujets_noms": [{"id": s, "titre": noms.get(s, s)} for s in x["sujets"]],
            "historique": historique}


# =========================================================================== actions sur un parcours (ticket)
def _parcours(pid: str) -> dict:
    from atelier.discovery import parcours_utilisateur as pu

    if not str(pid).startswith("PU-"):
        raise ValueError("Action réservée à un ticket parcours.")
    return pu._lire(pid)


def enrichir_mbt(pid: str, profil: str = "") -> dict:
    """Enrichir par le MBT : construit (ou actualise) le modèle comportemental du parcours et propose les chemins que les
    tests existants ne couvrent pas encore. Ce sont des cartes « à qualifier » : rien n'entre dans le Kanban sans accord."""
    from atelier.intelligence import mbt

    if profil:  # autre jeu de données : la Discovery est redéroulée avec lui, puis le MBT propose (travail en arrière-plan)
        from atelier.discovery import parcours_utilisateur as pu

        x = _ticket(pid)
        _deja_en_cours(x)
        pu.enregistrer(pid, {"profil_donnees": profil})
        p = pu._lire(pid)
        return {"parcours": pid, "profil_donnees": profil, "propositions": [], "a_automatiser": x.get("a_automatiser") or [], **_travail(
            f"MBT « {p.get('nom') or pid} » avec {profil}", [
                {"titre": "Dérouler le parcours", "type": "ia",
                 "params": {"texte": pu.demande_cursor(p) + " Termine par atelier_demande_terminee avec les écrans traversés.",
                            "attendus": ["discovery_terminer"]}},
                {"titre": "Extraire le test", "type": "atelier", "action": "brouillon_bdd", "params": {"parcours": pid, "titre": p.get("nom") or ""}},
                {"titre": "Enrichir par le MBT", "type": "atelier", "action": "enrichir_mbt", "params": {"parcours": pid}}], pid, "conception")}
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
    ecart = next((s.get("a_automatiser") or [] for s in tableau()["sujets"] if s["id"] == pid), [])
    # un chemin « réutilisé » par un scénario BDD sans script n'est pas couvert : il reste dans l'écart à automatiser
    return {"parcours": pid, "modele": m["id"], "propositions": props, "reutilises": len(a.get("reutilises") or []), "a_automatiser": ecart}


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


def rejouer(pid: str, xray: bool = False, jdd: str = "") -> dict:
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
    params = {"tests": ids, "run_params": dict(_params_xray()) if xray else {}}
    titre = f"Rejouer « {x['titre']} » ({'exécution TNR, Xray' if xray else 'en local'})"
    if jdd:  # même jeu pour les tests du sujet qui ont un jeu : ce run seulement
        from atelier.generation import bdd

        bases = {(bdd.charger(y["id"]) or {}).get("jdd") for y in les_tests} - {"", None}
        params["run_params"]["jdd_variantes"] = {b: jdd for b in bases if b != jdd}
        titre += f" avec {jdd}"
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
    try:
        from atelier.discovery import donnees as ref

        proposees = ref.propositions(pid)
    except Exception:  # noqa: BLE001
        proposees = []
    return {"profil_donnees": p.get("profil_donnees", ""), "profils": profils, "explore": bool(p.get("ecrans")), "donnees_proposees": proposees,
            "propositions": prop.get("chemins") or [], "propositions_date": prop.get("date", ""), "tnr_xray": campagne}
