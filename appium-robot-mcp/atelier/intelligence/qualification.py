"""Accueil de l'application : parcours de qualification en six étapes, parcours fonctionnels, informations clés, activités.

Trois vues complémentaires, jamais fondues en un pourcentage global :
- statut des étapes : où en est l'activité de qualification ? (Validé / En cours / À compléter / Non démarré / À la demande) ;
- parcours fonctionnels : sur quels parcours travaille-t-on ? ;
- livrables (atelier/intelligence/livrables.py) : qu'est-ce qui a réellement été produit et validé ?

Lecture seule ; chaque statut se déduit des objets existants (carte, parcours utilisateur, modèles comportementaux, scénarios
BDD, suites Robot et leur revue, runs, releases). Une source illisible rend son étape « indisponible » sans bloquer les autres.
Discovery, modèles et parcours : l'application active ; BDD, scripts, runs, releases : le projet.
"""
from __future__ import annotations

from datetime import datetime, timezone

STATUTS = {"valide": "Validé", "en_cours": "En cours", "a_completer": "À compléter", "non_demarre": "Non démarré",
           "a_la_demande": "À la demande", "indisponible": "Indisponible"}

# id, numéro, titre, module, icône, lien
ETAPES = (("comprendre", 1, "Comprendre l'application", "Discovery", "recherche", "#discovery/cadrage"),
          ("comportement", 2, "Comprendre le comportement", "MBT & Analyse", "branche", "#comportement"),
          ("concevoir", 3, "Concevoir les tests", "BDD & Scénarios", "bdd", "#bdd"),
          ("automatiser", 4, "Automatiser les tests", "Lots TNR", "editeur", "#lots"),
          ("executer", 5, "Exécuter et qualifier", "Execution Center", "execution", "#centre"),
          ("evoluer", 6, "Évolutions & non-régression", "Impact & Maintenance", "branche", "#releases"))
REVUES = {"Generated": "généré", "Technical Review": "en revue technique", "Changes Requested": "corrections demandées",
          "Approved": "validé", "Published": "publié", "Rejected": "écarté"}
# étape de chemin.py (prochaine action) → étape de qualification
DU_CHEMIN = {"decouvrir": "comprendre", "concevoir": "concevoir", "automatiser": "automatiser", "executer": "executer"}


def _dt(s) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.astimezone()  # date sans fuseau : heure locale


def _iso(d: datetime | None) -> str:
    return d.isoformat(timespec="seconds") if d else ""


def _plus_recent(*dates) -> str:
    l = [d for d in (_dt(x) for x in dates if x) if d]
    return _iso(max(l)) if l else ""


def _app() -> tuple[str, str]:
    from atelier.intelligence import mbt

    return mbt._app_courante()


def _d(texte: str, ton: str = "") -> dict:
    return {"texte": texte, "ton": ton}


# =========================================================================== les six étapes
def _comprendre() -> dict:
    from atelier.discovery import carte, parcours_utilisateur as pu

    slug, _ = _app()
    ecrans = carte.ecrans(slug or None)
    l = [p for p in pu._tous(slug or None) if not p.get("archive")]
    statuts = [pu.statut(p) for p in l]
    valides = sum(1 for p in l if p.get("valide"))
    if not ecrans and not l:
        st = "non_demarre"
    elif "En cours" in statuts:
        st = "en_cours"
    elif l and valides == len(l):
        st = "valide"
    else:
        st = "a_completer"
    det = [_d(f"{len(ecrans)} écran(s) découvert(s)")]
    if l:
        det.append(_d(f"{valides} parcours validé(s)", "ok"))
    if len(l) - valides:
        det.append(_d(f"{len(l) - valides} parcours à valider", "warn"))
    if not l and ecrans:
        det.append(_d("Aucun parcours cadré pour cette application", "warn"))
    return {"statut": st, "details": det, "maj": _plus_recent(*(e.get("maj") for e in ecrans), *(p.get("modifie") for p in l))}


def _comportement() -> dict:
    from atelier.domain import comportement as cm
    from atelier.intelligence import mbt

    modeles = [cm.charger(x["id"]) or {} for x in mbt.modeles()]
    confirmer = sum(1 for m in modeles for col in ("etats", "transitions") for el in (m.get(col) or {}).values()
                    if el.get("validation") == "à valider" or cm.niveau(el) == "À confirmer")
    vides = sum(1 for m in modeles if not m.get("etats"))
    if not modeles:
        st = "non_demarre"
    elif confirmer or vides:
        st = "a_completer"
    elif all(m.get("statut") == "Validated" for m in modeles):
        st = "valide"
    else:
        st = "en_cours"
    det = [_d(f"{len(modeles)} modèle(s)")] if modeles else []
    if confirmer:
        det.append(_d(f"{confirmer} comportement(s) à confirmer", "warn"))
    if vides:
        det.append(_d(f"{vides} modèle(s) sans état : à actualiser", "warn"))
    return {"statut": st, "details": det, "maj": _plus_recent(*(m.get("maj") for m in modeles))}


def _concevoir() -> dict:
    from atelier.generation import bdd

    l = bdd.lister()
    valides = [b for b in l if b.get("statut") == "validé"]
    sc_valides, sc_attente = sum(b["scenarios"] for b in valides), sum(b["scenarios"] for b in l if b not in valides)
    st = "non_demarre" if not l else "valide" if len(valides) == len(l) else "a_completer"
    det = [_d(f"{sc_valides} scénario(s) validé(s)", "ok")] if l else []
    if sc_attente:
        det.append(_d(f"{sc_attente} à examiner", "warn"))
    return {"statut": st, "details": det, "maj": _plus_recent(*(b.get("maj") for b in l))}


def _automatiser() -> dict:
    from atelier.generation import bdd, maintenance

    v = maintenance.vue()
    tests = [(s, t) for s in v["suites"] for t in s["tests"] if s["etat"] != "Écarté"]
    valides = sum(1 for s, _ in tests if s["etat"] == "Validé")
    a_valider = sum(1 for s, _ in tests if s["etat"] == "À valider")
    non_verifies = sum(1 for _, t in tests if not t.get("verifie"))
    cyc = maintenance.cycle_bdd(v)
    prets = sum(1 for b in bdd.lister() if b.get("statut") == "validé" and b["cle"] not in cyc)
    if not tests:
        st = "non_demarre"
    elif a_valider or non_verifies:
        st = "en_cours"
    elif prets:
        st = "a_completer"
    else:
        st = "valide"
    det = [_d(f"{len(tests)} script(s) créé(s)", "ok"), _d(f"{valides} script(s) validé(s)", "ok")] if tests else []
    if a_valider:
        det.append(_d(f"{a_valider} à valider", "warn"))
    if prets:
        det.append(_d(f"{prets} scénario(s) prêt(s) à automatiser", "warn"))
    from pathlib import Path

    from atelier.domain import projet
    from atelier.intelligence.livrables import _mtime

    d = Path(projet.PROJECT_DIR) / "tests"
    return {"statut": st, "details": det, "maj": _plus_recent(*(_mtime(f) for f in d.rglob("*.robot"))) if d.exists() else ""}


def _executer() -> dict:
    from atelier.execution import centre, historique

    runs = historique.lister(200)
    reels = [r for r in runs if r.get("passes") is not None and not r.get("dry_run")]
    if any(r["statut"] == "en cours" for r in runs) or centre.FILE.en_cours:
        st = "en_cours"
    elif not reels:
        st = "non_demarre"
    elif reels[0].get("echecs"):
        st = "a_completer"
    else:
        st = "valide"
    det = []
    if reels:
        d = reels[0]
        det.append(_d(f"{len(reels)} run(s) · {sum(1 for r in reels if not r.get('echecs'))} réussi(s)"))
        det.append(_d(f"Dernier run : {d['echecs']} échec(s)", "ko") if d.get("echecs") else _d(f"Dernier run : {d['passes']} test(s) réussi(s)", "ok"))
    else:
        det.append(_d("Aucun run réel pour l'instant."))
    return {"statut": st, "details": det, "maj": reels[0].get("fin") or reels[0].get("debut") if reels else ""}


def _evoluer() -> dict:
    from atelier.intelligence import releases

    l = releases.lister()
    if not l:
        return {"statut": "a_la_demande", "details": [_d("Aucune release analysée.")], "maj": ""}
    r = l[0]
    st = "en_cours" if r.get("qualification") == "En cours" and r.get("builds") else "a_la_demande"
    det = [_d(f"Dernière release analysée : {r.get('version') or r.get('nom')}")]
    if r.get("a_trancher"):
        det.append(_d(f"{r['a_trancher']} évolution(s) à rattacher", "warn"))
    return {"statut": st, "details": det, "maj": r.get("modifie") or r.get("cree")}


CALCULS = {"comprendre": _comprendre, "comportement": _comportement, "concevoir": _concevoir,
           "automatiser": _automatiser, "executer": _executer, "evoluer": _evoluer}


def etapes() -> list[dict]:
    out = []
    for id_, num, titre, module, icone, lien in ETAPES:
        e = {"id": id_, "num": num, "titre": titre, "module": module, "icone": icone, "lien": lien, "details": [], "maj": ""}
        try:
            e.update(CALCULS[id_]())
        except Exception as ex:  # noqa: BLE001 — une source illisible n'empêche pas les autres étapes
            e.update(statut="indisponible", details=[_d(str(ex) or ex.__class__.__name__, "ko")])
        e["statut_libelle"] = STATUTS[e["statut"]]
        out.append(e)
    return out


# =========================================================================== parcours fonctionnels
def parcours_fonctionnels() -> list[dict]:
    """Parcours utilisateur de l'application active : où en est chacun (Discovery, puis son test), sa dernière activité."""
    from atelier.discovery import parcours_utilisateur as pu
    from atelier.generation import bdd, maintenance

    slug, _ = _app()
    l = [p for p in pu._tous(slug or None) if not p.get("archive")]
    if not l:
        return []
    bdds = bdd.lister()
    try:
        cyc = maintenance.cycle_bdd()
    except Exception:  # noqa: BLE001 — dépôt illisible : l'avancement du test reste inconnu
        cyc = {}
    try:
        from atelier.discovery import carte

        modules = {e.get("id"): e.get("module") for e in carte.ecrans(slug or None)}
    except Exception:  # noqa: BLE001 — carte illisible : module inconnu
        modules = {}
    out = []
    for p in l:
        sp = pu.statut(p)
        p2 = {**p, "sessions_ids": p.get("sessions") or []}
        tests = [b for b in bdds if maintenance.du_parcours(b, p2)]
        etapes_t = [maintenance.etape_bdd(b, cyc.get(b["cle"])) for b in tests]
        if tests and all(e["etape"] == "fait" for e in etapes_t):
            st, etape = "valide", "Test automatisé, vérifié et validé"
        elif sp == "En cours":
            st, etape = "en_cours", "Discovery en cours"
        elif tests:
            st, etape = "en_cours", next(e["libelle"] for e in etapes_t if e["etape"] != "fait")
        elif sp == "Exploré":
            st, etape = "a_completer", "Écrans traversés à valider"
        elif sp == "Validé":
            st, etape = "a_completer", "Créer le test BDD"
        else:
            st, etape = "non_demarre", "Dérouler le parcours"
        module = next((modules[e] for e in p.get("ecrans") or [] if modules.get(e)), "")
        out.append({"id": p["id"], "nom": p.get("nom") or p["id"], "module": module, "plateforme": p.get("plateforme", ""),
                    "statut": st, "statut_libelle": STATUTS[st], "etape": etape, "lien": f"#discovery/cadrage/{p['id']}",
                    "tests": [{"cle": b["cle"], "titre": b.get("titre") or b["cle"]} for b in tests],
                    "derniere_activite": _plus_recent(p.get("modifie"), p.get("cree"), *(b.get("maj") for b in tests))})
    return sorted(out, key=lambda x: _dt(x["derniere_activite"]) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


# =========================================================================== activités récentes
def activites(limite: int = 6) -> list[dict]:
    """Ce qui s'est passé récemment dans le projet, le plus récent d'abord (scénarios, scripts, modèles, Discovery, runs,
    releases). Chaque activité : date, type, titre, détail, lien."""
    slug, _ = _app()
    ev: list[dict] = []

    def ajouter(date, type_, titre, detail, lien):
        d = _dt(date)
        if d:
            ev.append({"date": _iso(d), "type": type_, "titre": titre, "detail": detail, "lien": lien})

    sources = []

    def bdds():
        from atelier.generation import bdd

        for b in bdd.lister():
            ajouter(b.get("maj"), "bdd", "Scénario BDD validé" if b.get("statut") == "validé" else "Scénario BDD modifié",
                    b.get("titre") or b["cle"], f"#bdd/{b['cle']}")

    def scripts():
        from atelier.generation import studio

        for f, r in studio.revues_scripts().items():
            for h in (r.get("historique") or [])[-2:]:
                vers = h.get("vers", "")
                titre = "Script automatisé validé" if vers in ("Approved", "Published") else f"Script : {REVUES.get(vers, vers or 'en revue')}"
                ajouter(h.get("date"), "script", titre, f.rsplit("/", 1)[-1], "#tests")

    def modeles():
        from atelier.intelligence import mbt

        for m in mbt.modeles():
            ajouter(m.get("maj"), "modele", "Modèle comportemental mis à jour", m.get("nom") or m["id"], f"#comportement/{m['id']}")

    def discovery():
        from atelier.discovery import sessions_discovery

        for s in sessions_discovery.lister():
            c = s.get("config") or {}
            if slug and c.get("app") not in (slug, None):
                continue
            if s.get("statut") == "Terminée":
                ajouter(s.get("fin") or s.get("cree"), "discovery", "Discovery terminée", s["id"], "#discovery")
            elif s.get("statut") == "En cours":
                ajouter(s.get("debut") or s.get("cree"), "discovery", "Discovery en cours", s["id"], "#discovery")

    def runs():
        from atelier.execution import historique

        for r in historique.lister(30):
            if r.get("dry_run") or r["statut"] == "en cours":
                continue
            ajouter(r.get("fin") or r.get("debut"), "run", f"Run {r['statut']}",
                    f"{(r.get('suite') or '').rsplit('/', 1)[-1]} · {r.get('passes') or 0} réussi(s), {r.get('echecs') or 0} échec(s)",
                    f"#centre/historique/{r['id']}")

    def rel():
        from atelier.intelligence import releases

        for r in releases.lister():
            ajouter(r.get("modifie") or r.get("cree"), "release", f"Release {r.get('version') or r.get('nom')}",
                    f"{r.get('builds', 0)} build(s) · {r.get('evolutions', 0)} évolution(s)", f"#releases/{r['id']}")

    sources = (bdds, scripts, modeles, discovery, runs, rel)
    for s in sources:
        try:
            s()
        except Exception:  # noqa: BLE001 — une source illisible : ses activités manquent, les autres restent
            continue
    ev.sort(key=lambda x: x["date"] and _dt(x["date"]), reverse=True)
    return ev[:limite]


# =========================================================================== informations clés et vue complète
def informations() -> dict:
    from atelier.discovery import carte

    slug, nom = _app()
    c = carte.config_app(slug) if slug else {}
    return {"slug": slug, "nom": nom or slug, "type": c.get("type", ""), "plateformes": c.get("plateformes") or [],
            "url": (c.get("web") or {}).get("url", ""), "build": c.get("build", ""), "langue": c.get("langue", ""),
            "responsable": c.get("responsable", ""), "cree": c.get("cree", "")}


def accueil() -> dict:
    """Tout l'Accueil d'une application, sauf les livrables (appel séparé : ils se chargent à part)."""
    from atelier.intelligence import chemin

    try:
        s = chemin.etat()
        suivante = {**s["suivante"], "etape": DU_CHEMIN.get(s["suivante"]["etape"], s["suivante"]["etape"])}
        integ = s["integrations"]
    except Exception:  # noqa: BLE001
        suivante, integ = None, {}
    try:
        info = informations()
    except Exception:  # noqa: BLE001
        info = {}
    try:
        parcours = parcours_fonctionnels()
    except Exception:  # noqa: BLE001
        parcours = []
    act = activites()
    info["derniere_activite"] = act[0]["date"] if act else ""
    return {"application": info, "etapes": etapes(), "suivante": suivante, "parcours": parcours, "activites": act,
            "integrations": integ}
