"""Livrables : ce qui a réellement été produit dans l'atelier (découvert, modélisé, conçu, automatisé, exécuté, anomalies).

Vue indépendante des étapes de qualification : des volumes réels (jamais un pourcentage, jamais un volume cible), qui
distinguent le créé, le validé et l'en attente, avec la date de dernière mise à jour. Le nombre de livrables n'est pas une
mesure de qualité. Discovery et modèles comportementaux : l'application active (un projet peut en avoir plusieurs) ;
scénarios BDD, automatisations, campagnes et anomalies : tout le projet. Une source illisible rend sa carte indisponible
avec la raison, sans bloquer les autres.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


def _ind(cle: str, libelle: str, valeur: int, lien: str, definition: str, ton: str = "") -> dict:
    return {"cle": cle, "libelle": libelle, "valeur": int(valeur), "lien": lien, "definition": definition, "ton": ton}


def _max(*dates) -> str:
    l = [str(d) for d in dates if d]
    return max(l) if l else ""


def _mtime(p: Path) -> str:
    try:
        return datetime.fromtimestamp(p.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    except OSError:
        return ""


def _app() -> tuple[str, str]:
    from atelier.intelligence import mbt

    return mbt._app_courante()


# =========================================================================== les six livrables
def discovery() -> dict:
    from atelier.discovery import carte, parcours_utilisateur

    slug, _nom = _app()
    ecrans = carte.ecrans(slug or None)
    composants = sum(len(e.get("elements") or {}) for e in ecrans)
    pu = [p for p in parcours_utilisateur._tous(slug or None) if not p.get("archive")]
    valides = sum(1 for p in pu if p.get("valide"))
    return {"indicateurs": [
        _ind("ecrans", "Écrans", len(ecrans), "#graphe", "Écrans de l'application enregistrés dans la carte par la Discovery."),
        _ind("composants", "Composants", composants, "#graphe", "Éléments (champs, boutons, liens…) identifiés sur ces écrans."),
        _ind("parcours", "Parcours", len(pu), "#discovery/cadrage", "Parcours utilisateur cadrés pour l'application (archivés exclus)."),
        _ind("parcours_valides", "Parcours validés", valides, "#discovery/cadrage", "Parcours dont le QA a validé l'exploration.", "ok")],
        "maj": _max(*(e.get("maj") for e in ecrans), *(p.get("maj") or p.get("cree") for p in pu))}


def modele() -> dict:
    from atelier.domain import comportement as cm
    from atelier.intelligence import mbt

    etats = transitions = confirmer = 0
    maj = []
    liste = mbt.modeles()
    for x in liste:
        m = cm.charger(x["id"]) or {}
        etats += len(m.get("etats") or {})
        transitions += len(m.get("transitions") or {})
        for col in ("etats", "transitions"):
            confirmer += sum(1 for el in (m.get(col) or {}).values()
                             if el.get("validation") == "à valider" or cm.niveau(el) == "À confirmer")
        maj.append(m.get("maj"))
    return {"indicateurs": [
        _ind("modeles", "Modèles", len(liste), "#comportement", "Modèles comportementaux de l'application active."),
        _ind("etats", "États", etats, "#comportement", "États identifiés dans ces modèles."),
        _ind("transitions", "Transitions", transitions, "#comportement", "Transitions identifiées entre ces états."),
        _ind("a_confirmer", "À confirmer", confirmer, "#comportement",
             "États et transitions déduits ou incomplets, en attente de la confirmation du QA.", "warn")],
        "maj": _max(*maj)}


def scenarios_bdd() -> dict:
    from atelier.generation import bdd

    l = bdd.lister()
    total = sum(b["scenarios"] for b in l)
    valides = sum(b["scenarios"] for b in l if b.get("statut") == "validé")
    return {"indicateurs": [
        _ind("total", "Total", total, "#bdd", f"Scénarios Gherkin écrits, répartis dans {len(l)} test(s) BDD."),
        _ind("valides", "Validés", valides, "#bdd", "Scénarios des tests BDD validés par le QA.", "ok"),
        _ind("en_attente", "En attente", total - valides, "#bdd", "Scénarios des tests BDD encore en brouillon : à relire et valider.", "warn")],
        "maj": _max(*(b.get("maj") for b in l)), "note": f"{len(l)} test(s) BDD"}


def automatisations() -> dict:
    from atelier.domain import projet
    from atelier.generation import maintenance

    v = maintenance.vue()
    tests = [(s, t) for s in v["suites"] for t in s["tests"] if s["etat"] != "Écarté"]
    d = Path(projet.PROJECT_DIR) / "tests"
    maj = _max(*(_mtime(f) for f in d.rglob("*.robot"))) if d.exists() else ""
    return {"indicateurs": [
        _ind("crees", "Créés", len(tests), "#tests", "Tests Robot du dépôt (hors tests écartés)."),
        _ind("valides", "Validés", sum(1 for s, _ in tests if s["etat"] == "Validé"), "#tests", "Tests dont la suite est validée.", "ok"),
        _ind("en_attente", "À valider", sum(1 for s, _ in tests if s["etat"] == "À valider"), "#tests",
             "Tests générés ou modifiés depuis la dernière validation, en attente de revue.", "warn"),
        _ind("verifies", "Vérifiés", sum(1 for _, t in tests if t.get("verifie")), "#tests",
             "Tests passés lors d'un run réel postérieur à leur dernière modification.")],
        "maj": maj}


def campagnes() -> dict:
    from atelier.execution import centre, historique

    l = centre.campagnes()
    runs = [r for r in historique.lister(500) if r.get("passes") is not None and not r.get("dry_run")]
    return {"indicateurs": [
        _ind("campagnes", "Campagnes", len(l), "#centre/campagnes", "Campagnes enregistrées dans l'Execution Center."),
        _ind("executions", "Runs", len(runs), "#centre/historique", "Runs réels terminés avec un résultat (essais à blanc exclus)."),
        _ind("reussies", "Runs réussis", sum(1 for r in runs if not r.get("echecs")), "#centre/historique", "Runs sans test en échec.", "ok"),
        _ind("echecs", "Runs en échec", sum(1 for r in runs if r.get("echecs")), "#centre/resultats", "Runs avec au moins un test en échec.", "ko")],
        "maj": _max(*(r.get("fin") or r.get("debut") for r in runs), *(c.get("derniere_execution") for c in l))}


_FERME = re.compile(r"clos|ferm|résolu|resolu|corrig|done|termin|rejet|closed|fixed", re.I)
_EN_COURS = re.compile(r"en cours|progress|analyse", re.I)


def anomalies() -> dict:
    from atelier.discovery import entites
    from atelier.intelligence import pilotage

    etats: dict[str, str] = {}
    dates = []
    try:
        for b in pilotage._bugs():  # bugs Jira liés aux exécutions Xray (copie locale)
            e = pilotage._etat_bug(b)
            etats[b["cle"]] = "ferme" if e not in ("ouvert", "en_cours", "reouvert") else "en_cours" if e == "en_cours" else "ouvert"
    except Exception:  # noqa: BLE001 — sans copie Xray : les anomalies du Knowledge Graph suffisent
        pass
    for a in entites.anomalies():  # anomalies déclarées dans l'atelier (Failure Analysis, Jira)
        cle = a.get("id_jira") or a["id"]
        if cle in etats:
            continue
        s = str(a.get("statut") or "")
        etats[cle] = "ferme" if _FERME.search(s) else "en_cours" if _EN_COURS.search(s) else "ouvert"
        dates.append(a.get("date_detection"))
    n = lambda x: sum(1 for v in etats.values() if v == x)  # noqa: E731
    return {"indicateurs": [
        _ind("ouvertes", "Ouvertes", n("ouvert"), "#echecs/jira", "Anomalies ouvertes (ou rouvertes), pas encore prises en charge.", "ko"),
        _ind("en_cours", "En cours", n("en_cours"), "#echecs/jira", "Anomalies en cours d'analyse ou de correction.", "warn"),
        _ind("cloturees", "Clôturées", n("ferme"), "#echecs/retest", "Anomalies résolues, corrigées ou rejetées.", "ok")],
        "maj": _max(*dates)}


CARTES = (("discovery", "Discovery", "recherche", "#discovery", "application", discovery),
          ("modele", "Modèle MBT", "branche", "#comportement", "application", modele),
          ("bdd", "Scénarios BDD", "bdd", "#bdd", "projet", scenarios_bdd),
          ("automatisations", "Automatisations", "editeur", "#tests", "projet", automatisations),
          ("campagnes", "Campagnes", "execution", "#centre/campagnes", "projet", campagnes),
          ("anomalies", "Anomalies", "alerte", "#echecs", "projet", anomalies))


def livrables() -> dict:
    slug, nom = _app()
    out = []
    for id_, titre, icone, lien, portee, fn in CARTES:
        c = {"id": id_, "titre": titre, "icone": icone, "lien": lien, "portee": portee, "indicateurs": [], "maj": "", "note": ""}
        try:
            c.update(fn(), disponible=True)
        except Exception as e:  # noqa: BLE001 — une source illisible n'empêche pas les autres cartes
            c.update(disponible=False, raison=str(e) or e.__class__.__name__)
        out.append(c)
    return {"application": {"slug": slug, "nom": nom}, "cartes": out}
