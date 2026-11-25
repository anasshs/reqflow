"""Points d'entrée de l'automatisation : l'automaticien désigne un PARCOURS, une USER STORY ou un TEST PLAN Xray ; l'atelier
le résout en tests Xray, puis dépose une demande que le MCP (Claude Code ou Cursor) déroule test par test
(docs/AUTOMATISATION_MULTI_CIBLES.md § 4.6).

Pour chaque test : scénario BDD présent (clé BDD = clé Xray pour un dépôt adopté, sinon clé Xray retenue à la publication),
implémentations existantes par technologie (Robot : clé Xray en tag ; Kotlin : @Xray("CLE") ou méthode tam_<n>_… dans le
projet Kotlin), et « à concevoir » s'il n'a ni scénario BDD ni Gherkin.
"""
from __future__ import annotations

import re

ENTREES = {"parcours": "Parcours", "us": "User Story", "plan": "Test Plan Xray"}
CLE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")

CONSIGNE = ("Automatise avec le MCP de l'atelier, technologie « {techno} », les tests suivants ({entree} {reference}) : {tests}. "
            "Pour chaque test, dans l'ordre : 1) scénario BDD : s'il manque, crée-le depuis Xray (Gherkin, ou étapes du test "
            "manuel) ; s'il n'y a rien à reprendre, propose les cas (test_design_proposer) et arrête-toi pour ce test ; "
            "2) check_jdd, studio_socle(), studio_plan_automatisation(cle) ; une étape formulée autrement qu'un keyword "
            "existant se lie sans réécrire Xray (décision de l'automaticien : la proposer, ne pas la prendre) ; "
            "3) studio_generer_depuis_bdd(cle, ecrire=True, technologie=\"{techno}\") ; complète ce qui reste « à implémenter » "
            "dans les pages / Page Objects existants, sans wrapper 1:1 ; 4) contrôle (dry-run Robot, ou compilation Kotlin) ; "
            "5) vérifie par un vrai run (run_tests) ; un échec de l'application est qualifié, jamais masqué ; 6) ne publie rien "
            "dans Xray (publication par l'automaticien). Termine par atelier_demande_terminee : pour chaque test, automatisé et "
            "vérifié / à concevoir / bloqué (raison).")


def _bdd_par_cle_xray() -> dict[str, str]:
    """Clé Xray -> clé du scénario BDD (identiques pour un dépôt adopté ; sinon clé Xray retenue à la publication)."""
    from atelier.generation import bdd, conception

    out = {}
    for b in bdd.lister():
        x = conception.cle_xray_du_scenario(b["cle"]) or (b["cle"] if CLE.match(b["cle"]) else "")
        if x:
            out.setdefault(x, b["cle"])
    return out


def _implementations() -> dict[str, dict]:
    """Clé Xray -> {technologie: [fichiers]} : Robot (tag), Kotlin (@Xray ou méthode tam_<n>_ du projet Kotlin)."""
    from atelier.domain import projet
    from atelier.execution import depot_robot

    out: dict[str, dict] = {}
    try:
        for t in depot_robot.lire_depot()["tests"].values():
            for k in t.get("cles_xray") or []:
                out.setdefault(k, {}).setdefault("robot", []).append(f"{t['fichier']}::{t['nom']}")
    except Exception:  # noqa: BLE001  (dépôt illisible : pas d'implémentation Robot connue)
        pass
    racine = projet.PROJECT_DIR / dossier_kotlin()
    if racine.exists():
        for f in racine.rglob("*.kt"):
            try:
                texte = f.read_text("utf-8", errors="replace")
            except OSError:
                continue
            rel = f.relative_to(projet.PROJECT_DIR).as_posix()
            cles = set(re.findall(r'@Xray\("([A-Z][A-Z0-9_]+-\d+)"\)', texte))
            cles |= {f"{p.upper()}-{n}" for p, n in re.findall(r"\bfun\s+([a-z][a-z0-9]*)_(\d+)_\w*\(", texte)}
            for k in cles:
                techno = "espresso" if "espresso" in texte.lower() else "uiautomator"
                out.setdefault(k, {}).setdefault(techno, []).append(rel)
    return out


def dossier_kotlin() -> str:
    """Projet Kotlin du dépôt de tests (fiche de l'application : automatisation.projet_kotlin ; défaut « uiautomator »)."""
    from atelier.discovery import carte

    try:
        cfg = carte.config_app() if carte.app_courante() else {}
    except Exception:  # noqa: BLE001
        cfg = {}
    return ((cfg or {}).get("automatisation") or {}).get("projet_kotlin") or "uiautomator"


def _cles_parcours(reference: str) -> list[str]:
    from atelier.generation import bdd, conception

    return [conception.cle_xray_du_scenario(b["cle"]) or b["cle"] for b in bdd.lister() if b.get("parcours") == reference]


def _cles_us(reference: str) -> list[str]:
    """Tests de l'US : scénarios BDD qui portent son tag, et tests Xray reliés à l'US dans le Knowledge Graph."""
    from atelier.generation import bdd, conception

    cles = []
    for b in bdd.lister():
        m = bdd.charger(b["cle"]) or {}
        tags = set(m.get("tags") or []) | {t for s in m.get("scenarios") or [] for t in s.get("tags") or []}
        if reference in tags or f"@{reference}" in tags:
            cles.append(conception.cle_xray_du_scenario(b["cle"]) or b["cle"])
    try:
        from atelier.discovery import connaissance

        g = connaissance.construire()
        nid = f"user_story:{reference}"
        if nid in g.noeuds:
            cles += [r.vers.split(":", 1)[1] for r in g.sortants(nid) if r.type == "teste_par"]
    except Exception:  # noqa: BLE001
        pass
    return list(dict.fromkeys(cles))


def _cles_plan(reference: str, xray=None) -> list[dict]:
    """Tests d'un Test Plan Xray (clé, résumé, type), par pages de 100."""
    from atelier.integrations.xray import XrayClient

    x = xray or XrayClient()
    out, debut = [], 0
    while True:
        d = x.gql('query($j:String!,$s:Int){getTestPlans(jql:$j,limit:1){results{tests(limit:100,start:$s){total '
                  'results{jira(fields:["key","summary"]) testType{name}}}}}}', {"j": f'key = "{reference}"', "s": debut})
        res = d["getTestPlans"]["results"]
        if not res:
            raise KeyError(f"Test Plan Xray introuvable : {reference}")
        page = res[0]["tests"]
        out += [{"cle": t["jira"]["key"], "titre": t["jira"].get("summary", ""), "type": (t.get("testType") or {}).get("name", "")}
                for t in page["results"]]
        debut += 100
        if debut >= page["total"]:
            return out


def resoudre(entree: str, reference: str, xray=None) -> dict:
    """{entree, reference, tests: [{cle, titre, type, bdd, implementations, a_concevoir}], bilan}."""
    entree, reference = (entree or "").strip().lower(), (reference or "").strip()
    if entree not in ENTREES:
        raise ValueError(f"Point d'entrée : {', '.join(ENTREES)}.")
    if not reference:
        raise ValueError("Référence obligatoire (identifiant du parcours, clé de l'US ou du Test Plan).")
    if entree == "plan":
        bruts = _cles_plan(reference.upper(), xray)
    else:
        bruts = [{"cle": c, "titre": "", "type": ""} for c in (_cles_parcours(reference) if entree == "parcours" else _cles_us(reference.upper()))]
    from atelier.generation import bdd

    par_xray, impl = _bdd_par_cle_xray(), _implementations()
    tests = []
    for t in bruts:
        cle_bdd = par_xray.get(t["cle"]) or (t["cle"] if bdd.charger(t["cle"]) else "")
        m = bdd.charger(cle_bdd) if cle_bdd else None
        tests.append({"cle": t["cle"], "titre": t["titre"] or (m or {}).get("titre", ""), "type": t["type"],
                      "bdd": cle_bdd, "implementations": impl.get(t["cle"], {}),
                      "a_concevoir": not cle_bdd and t["type"] not in ("Cucumber", "Gherkin")})
    return {"entree": entree, "libelle": ENTREES[entree], "reference": reference, "tests": tests,
            "bilan": {"tests": len(tests), "avec_bdd": sum(1 for t in tests if t["bdd"]),
                      "a_concevoir": sum(1 for t in tests if t["a_concevoir"]),
                      "robot": sum(1 for t in tests if "robot" in t["implementations"]),
                      "kotlin": sum(1 for t in tests if {"uiautomator", "espresso"} & set(t["implementations"]))}}


def automatiser(entree: str, reference: str, technologie: str = "", tests: list[str] | None = None, xray=None,
                mode: str = "") -> dict:
    """Dépose la demande d'automatisation dans la boîte de l'atelier : le MCP la prend (atelier_demande_suivante).
    tests : sélection parmi le périmètre (vide = tous). mode : boite / cli (vide = réglage du projet)."""
    from atelier.generation import technologies
    from atelier.integrations import boite_cursor

    techno = technologie or technologies.par_defaut()
    technologies.obtenir(techno)  # inconnue ou indisponible : refus avant de déposer
    p = resoudre(entree, reference, xray)
    choisis = [t for t in p["tests"] if not tests or t["cle"] in tests]
    if not choisis:
        raise ValueError("Aucun test à automatiser dans ce périmètre.")
    cles = [t["cle"] for t in choisis]
    texte = CONSIGNE.format(techno=techno, entree=p["libelle"].lower(), reference=reference, tests=", ".join(cles))
    d = boite_cursor.deposer(f"Automatiser ({techno}) : {p['libelle']} {reference} — {len(cles)} test(s)", texte,
                             attendus=["studio_generer_depuis_bdd", "run_tests"], mode=mode)
    return {"demande": d.get("id", ""), "mode": d.get("mode", ""), "technologie": techno, "tests": cles,
            "a_concevoir": [t["cle"] for t in choisis if t["a_concevoir"]]}
