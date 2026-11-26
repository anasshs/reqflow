"""Adopter un dépôt Robot existant (application déjà automatisée) sans repartir de zéro.

Le dépôt a déjà ses tests, en Page Object Model, avec leur tag Xray. Plutôt qu'une Discovery, l'atelier en tire la
connaissance et la conception :
1. Analyse (lecture seule) : suites, tests, ceux écrits en Gherkin (Given / When / Then, ou Étant donné / Quand /
   Alors), leur clé Xray, leur jeu de données (&{JDD_<jeu>}) ; une proposition de parcours par suite, marquée
   « technique » quand la suite n'est pas un parcours métier (connexion, smoke, commun…) ou n'a aucun test Gherkin.
2. Import des scénarios : chaque test Gherkin devient un scénario BDD de Test Design (clé = clé Xray si le test en a
   une : le scénario, le test Robot et le test Xray sont alors reliés d'office), étapes reprises telles quelles,
   jeu de données associé, rattaché à l'application. Un scénario qui existe déjà n'est jamais écrasé.
3. Parcours : les suites gardées par l'automaticien (renommées, fusionnées) deviennent des parcours utilisateur ;
   leurs scénarios y sont rattachés (Kanban : un couloir par parcours).
4. Run cartographié : les tests existants, joués sur le téléphone avec la cartographie, remplissent la carte
   (écrans, captures, transitions, tests Xray qui passent par chaque écran) ; les écrans qu'un parcours traverse
   lui sont alors donnés. C'est la Discovery faite par les tests.
Ensuite : MBT sur ces parcours pour voir ce qui manque, et une Discovery seulement là où la carte a des trous.
"""
from __future__ import annotations

import re
from pathlib import Path

from atelier.domain import projet

PREFIXES = {"given": "given", "when": "when", "then": "then", "and": "and", "but": "but",
            "étant donné": "given", "etant donne": "given", "soit": "given", "quand": "when", "lorsque": "when", "alors": "then",
            "et": "and", "mais": "but"}
_RE_PREFIXE = re.compile(r"^(" + "|".join(sorted(map(re.escape, PREFIXES), key=len, reverse=True)) + r")\s+(.+)$", re.IGNORECASE)
TECHNIQUE = re.compile(r"(?i)^(login|logout|connexion|deconnexion|smoke|sanity|setup|teardown|commun|common|utils?|outils|init|"
                       r"healthcheck|exemple)([_\-\s.]|$)")  # début du nom de la suite : « …avant_connexion » reste un parcours
EN = {"given": "Given", "when": "When", "then": "Then", "and": "And", "but": "But"}
FR = {"given": "Étant donné", "when": "Quand", "then": "Alors", "and": "Et", "but": "Mais"}


def _cle_xray():
    from atelier.integrations.xray import KEY_RE

    return KEY_RE


def _cellules(ligne: str) -> list[str]:
    return [c for c in re.split(r"\s{2,}|\t", ligne.strip()) if c]


def lire_suite(fichier: str, racine: Path | None = None) -> dict:
    """Titre, documentation et tests d'une suite : pour chaque test, ses étapes Gherkin, ses tags, son jeu de données.
    racine : dossier d'un autre projet (aperçu avant activation), sinon le projet actif."""
    chemin = (racine / fichier) if racine else projet.safe_path(fichier)
    texte = chemin.read_text("utf-8", errors="replace")
    section, tests, courant, doc_suite = "", [], None, ""
    for brute in texte.splitlines():
        if brute.strip().startswith("***"):
            section = brute.strip("* \t").lower()
            courant = None
            continue
        if not brute.strip() or brute.lstrip().startswith("#"):
            continue
        if section.startswith("setting") and brute.lower().startswith("documentation"):
            doc_suite = " ".join(_cellules(brute)[1:])
        if not section.startswith("test case"):
            continue
        if not brute[:1].isspace():
            courant = {"nom": brute.strip(), "etapes": [], "tags": [], "doc": "", "jdd": "", "langue": ""}
            tests.append(courant)
            continue
        if courant is None:
            continue
        c = _cellules(brute)
        if not c:
            continue
        if c[0].lower() == "[tags]":
            courant["tags"] += c[1:]
        elif c[0].lower() == "[documentation]":
            courant["doc"] = " ".join(c[1:])
        elif c[0].startswith("[") or c[0] == "...":
            continue
        else:
            m = _RE_PREFIXE.match(c[0])
            if m:
                mot = m.group(1).lower()
                # arguments du mot-clé (cellules suivantes) gardés dans l'étape : « Le Compte De Connexion Est ${COMPTE} »
                courant["etapes"].append((PREFIXES[mot], " ".join([m.group(2).strip(), *c[1:]]).strip()))
                courant["langue"] = courant["langue"] or ("en" if mot in EN else "fr")
            j = re.search(r"&\{JDD_([A-Za-z0-9_]+)\}", brute)
            if j and not courant["jdd"]:
                courant["jdd"] = j.group(1)
    stem = Path(fichier).stem
    titre = re.split(r"\s+[—–]\s+|\s+-\s+|\.\s", doc_suite)[0].strip() if doc_suite else ""  # sans la note qui suit le tiret
    return {"fichier": fichier, "titre": titre[:120] or stem.replace("_", " ").strip().capitalize(),
            "doc": doc_suite, "tests": tests}


def _cle_bdd(t: dict, suite: str) -> str:
    from atelier.generation import bdd

    x = next((g for g in t["tags"] if _cle_xray().match(g)), "")
    return x or bdd._slug(f"{Path(suite).stem}_{t['nom']}")[:80]


def analyser() -> dict:
    """Ce que le dépôt apporte, et ce que l'atelier propose d'en faire (aucune écriture)."""
    from atelier.discovery import carte, parcours_utilisateur as pu
    from atelier.execution.depot_robot import lire_depot
    from atelier.generation import bdd, lots

    inv = lire_depot()
    par_bdd, _ = lots._index_tests()
    lie = {t["id"]: cle for cle, ts in par_bdd.items() for t in ts}  # test déjà relié à un scénario (par son tag)
    app = carte.app_courante() or ""
    suites = sorted({t["fichier"] for t in inv["tests"].values() if t["fichier"].startswith("tests/")})
    if app:  # application active : ses suites seulement quand le dépôt range ses tests par application (tests/<app>/)
        propres = [s for s in suites if s.startswith(f"tests/{app}/")]
        suites = propres or suites
    existants = {b["cle"] for b in bdd.lister()}
    parcours = {p["nom"].lower(): p["id"] for p in pu.lister()}
    out, n_gherkin, n_xray = [], 0, 0
    for s in suites:
        try:
            x = lire_suite(s)
        except (OSError, ValueError):
            continue
        tests = []
        for t in x["tests"]:
            tid = f"{s}::{t['nom']}"
            cle = lie.get(tid) or _cle_bdd(t, s)
            g = bool(t["etapes"])
            xray = next((g2 for g2 in t["tags"] if _cle_xray().match(g2)), "")
            n_gherkin += g
            n_xray += bool(xray)
            tests.append({"id": tid, "nom": t["nom"], "gherkin": g, "etapes": len(t["etapes"]), "xray": xray, "jdd": t["jdd"],
                          "cle_bdd": cle, "deja": tid in lie or cle in existants})
        technique = bool(TECHNIQUE.search(Path(s).stem)) or not any(t["gherkin"] for t in tests)
        out.append({"suite": s, "nom": x["titre"], "doc": x["doc"], "tests": tests, "type": "technique" if technique else "parcours",
                    "raison": ("nom de suite technique" if TECHNIQUE.search(Path(s).stem) else "aucun test Gherkin") if technique else "",
                    "parcours_existant": parcours.get(x["titre"].lower(), "")})
    return {"application": app, "suites": out, "tests": sum(len(s["tests"]) for s in out), "gherkin": n_gherkin, "avec_xray": n_xray,
            "keywords": len(inv.get("keywords") or {}), "locators": len(inv.get("locators") or {}),
            "pages": len({k["fichier"] for k in (inv.get("keywords") or {}).values()}),
            "carte": {"ecrans": len(carte.ecrans()) if app else 0}}


def apercu(dossier: str | Path) -> dict:
    """Ce qu'un dossier de projet apporte à l'adoption, sans l'activer (ajout ou modification d'un projet) : suites et
    tests Robot du dépôt, tests Gherkin, clés Xray ; et la connaissance de l'atelier déjà présente (carte, parcours,
    scénarios BDD), que l'adoption complète sans jamais l'écraser."""
    from atelier.domain import synchro

    d = Path(dossier).expanduser()
    out = {"dossier": str(d), "suites": 0, "tests": 0, "gherkin": 0, "avec_xray": 0, "connaissance": {}, "a_adopter": False}
    if not d.is_dir():
        return out
    for f in sorted((d / "tests").rglob("*.robot")) if (d / "tests").is_dir() else []:
        try:
            s = lire_suite(f.relative_to(d).as_posix(), d)
        except (OSError, ValueError):
            continue
        if not s["tests"]:
            continue
        out["suites"] += 1
        out["tests"] += len(s["tests"])
        out["gherkin"] += sum(bool(t["etapes"]) for t in s["tests"])
        out["avec_xray"] += sum(any(_cle_xray().match(g) for g in t["tags"]) for t in s["tests"])
    for p in synchro.CONNAISSANCE + ("conception/",):
        r = d / p.rstrip("/")
        n = sum(1 for f in r.rglob("*") if f.is_file()) if r.is_dir() else 0
        if n:
            out["connaissance"][p.rstrip("/")] = n
    out["a_adopter"] = out["tests"] > 0
    return out


def _gherkin(suite: dict, t: dict) -> str:
    mots = EN if t["langue"] == "en" else FR
    lignes = [f"# language: {t['langue'] or 'fr'}"]
    tags = [g for g in t["tags"] if not _cle_xray().match(g)]
    if tags:
        lignes.append(" ".join("@" + re.sub(r"\s+", "_", g) for g in tags))
    lignes.append(f"{'Feature' if t['langue'] == 'en' else 'Fonctionnalité'}: {suite['titre']}")
    if t["doc"]:
        lignes.append(f"  {t['doc']}")
    lignes.append(f"  {'Scenario' if t['langue'] == 'en' else 'Scénario'}: {t['nom']}")
    lignes += [f"    {mots[m]} {texte}" for m, texte in t["etapes"]]
    return "\n".join(lignes) + "\n"


def importer_scenarios(tests: list[str] | None = None) -> dict:
    """Les tests Gherkin du dépôt (tous, ou ceux donnés « fichier::nom ») deviennent des scénarios BDD validés (ils
    tournent déjà) ; un scénario existant n'est jamais touché. Décision de l'automaticien (bouton de l'écran)."""
    from atelier.discovery import carte
    from atelier.generation import bdd

    a = analyser()
    choisis = set(tests or [])
    crees, deja, refus = [], [], []
    for s in a["suites"]:
        suite = None
        for t in s["tests"]:
            if not t["gherkin"] or (choisis and t["id"] not in choisis):
                continue
            if t["deja"] or bdd.charger(t["cle_bdd"]):
                deja.append(t["cle_bdd"])
                continue
            suite = suite or lire_suite(s["suite"])
            brut = next(x for x in suite["tests"] if x["nom"] == t["nom"])
            try:
                bdd.creer(t["cle_bdd"], t["nom"], jdd=t["jdd"])
                bdd.depuis_texte(t["cle_bdd"], _gherkin(suite, brut))
                m = bdd.charger(t["cle_bdd"])
                m.update(application=carte.app_courante() or "", origine={"type": "depot", "suite": s["suite"], "test": t["id"]})
                if t["jdd"]:
                    m["jdd"] = t["jdd"]
                bdd.sauver(m)
                try:
                    bdd.valider(t["cle_bdd"])  # le test tourne déjà : ses étapes sont les bonnes
                except ValueError:
                    pass  # contrôle de gravité haute : reste en brouillon, à relire dans Test Design
                crees.append(t["cle_bdd"])
            except Exception as e:  # noqa: BLE001 — un test illisible n'empêche pas les autres
                refus.append({"test": t["id"], "erreur": str(e)[:200]})
    return {"crees": crees, "deja": deja, "refus": refus}


def creer_parcours(choix: list[dict]) -> dict:
    """choix : [{suite, nom, garder}] (plusieurs suites au même nom = un seul parcours). Chaque suite gardée devient un
    parcours (ou rejoint celui qui porte déjà ce nom) ; les scénarios de ses tests y sont rattachés."""
    from atelier.discovery import parcours_utilisateur as pu
    from atelier.generation import bdd

    a = {s["suite"]: s for s in analyser()["suites"]}
    par_nom = {p["nom"].lower(): p["id"] for p in pu.lister()}
    crees, rattaches = [], 0
    for c in choix:
        if not c.get("garder") or c.get("suite") not in a:
            continue
        nom = str(c.get("nom") or a[c["suite"]]["nom"]).strip()
        if not nom:
            continue
        pid = par_nom.get(nom.lower())
        if not pid:
            p = pu.enregistrer("", {"nom": nom, "objectif": a[c["suite"]]["doc"][:500] or f"Parcours repris de la suite {c['suite']}"})
            pid = par_nom[nom.lower()] = p["id"]
            crees.append(pid)
        for t in a[c["suite"]]["tests"]:
            m = bdd.charger(t["cle_bdd"])
            if m and not m.get("parcours"):
                m["parcours"] = pid
                bdd.sauver(m)
                rattaches += 1
    return {"parcours_crees": crees, "scenarios_rattaches": rattaches}


def _ecrans_par_tests_du_depot() -> dict[str, set]:
    """Écran de la carte -> clés Xray des tests Robot dont les keywords utilisent un de ses locators (même valeur ou même
    resource-id ; composants communs et keywords du socle exclus : couverture_avancee)."""
    from atelier.discovery import connaissance
    from atelier.intelligence import couverture_avancee

    g = connaissance.construire()
    out: dict[str, set] = {}
    for e in couverture_avancee.calculer(g)["ecrans"]:
        if e.get("tests_xray") and g.noeuds.get(e["id"]) and g.noeuds[e["id"]].source == "carte":
            out[e["id"]] = set(e["tests_xray"])
    return out


def ecrans_des_parcours(depuis_depot: bool = True) -> dict:
    """À chaque parcours, les écrans que ses tests traversent, dans l'ordre où la carte les a découverts :
    - run cartographié (la carte retient les tests Xray qui passent par chaque écran) : fait observé, lien validé ;
    - depuis_depot : écrans dont les locators sont utilisés par les keywords de ses tests Robot (dépôt relié à la carte)
      : lien déduit, proposé « à valider ». Les écrans de passage (chargement, erreur) ne sont jamais déduits.
    Un lien retiré ou rejeté n'est jamais repris."""
    from atelier.discovery import carte, connaissance, parcours_utilisateur as pu
    from atelier.domain import declarations
    from atelier.generation import bdd

    ecrans = sorted(carte.ecrans(), key=lambda e: e.get("cree") or "")
    statiques = _ecrans_par_tests_du_depot() if depuis_depot else {}
    bilan, deduits_total = {}, 0
    for p in pu.lister():
        cles = {b["cle"] for b in bdd.lister() if (bdd.charger(b["cle"]) or {}).get("parcours") == p["id"]}
        if not cles:
            continue
        # clés que la carte retient par écran : la clé Xray du test (scénarios repris du dépôt : clé BDD = clé Xray)
        traverses = [e["id"] for e in ecrans if cles & set(e.get("utilise_par") or [])]
        deduits = [e["id"] for e in ecrans if e["id"] not in traverses and not pu.ecran_transitoire(e)
                   and cles & statiques.get(f"ecran:{e.get('nom') or e['id']}", set())]
        if not traverses and not deduits:
            continue
        with pu._verrou:
            q = pu._lire(p["id"])
            ajoutes = proposes = 0
            for eid, observe in [(e, True) for e in traverses] + [(e, False) for e in deduits]:
                if eid in q.get("ecrans_retires", []) or eid in q["ecrans"]:
                    continue
                try:
                    nid = pu._noeud_ecran(eid)
                except KeyError:
                    continue
                rid = f"{q['noeud']}|contient|{nid}"
                if declarations.est_rejete(rid):
                    continue
                q["ecrans"].append(eid)
                if rid not in declarations.charger()["relations"]:
                    if observe:
                        declarations.ajouter_relation(q["noeud"], nid, "contient", auteur="automaticien",
                                                      source=f"run cartographié des tests du parcours « {q['nom']} »")
                    else:
                        declarations.ajouter_relation(q["noeud"], nid, "contient", auteur="ia",
                                                      source=f"tests du parcours « {q['nom']} » : leurs keywords utilisent les locators de l'écran")
                ajoutes += observe
                proposes += not observe
            if ajoutes or proposes:
                pu._journal(q, "écrans des tests du parcours",
                            detail=f"{ajoutes} écran(s) traversé(s) au run cartographié, {proposes} déduit(s) du dépôt (à valider)")
                q["modifie"] = pu._maintenant()
                pu._ecrire(q)
        bilan[p["id"]] = ajoutes + proposes
        deduits_total += proposes
    connaissance.vider_cache()
    return {"parcours": bilan, "deduits_du_depot": deduits_total}


def importer_locators() -> dict:
    """Amorce la carte avec les locators des pages du dépôt (Page Object Model : une page ≈ un écran)."""
    from atelier.discovery import carte_outils

    # pages en .resource, ou fichiers de locators en .robot sous resources/locators (convention de nombreux dépôts)
    total = {"ecrans_crees": 0, "locators_importes": 0}
    for motif in ("**/*.resource", "resources/locators/**/*.robot"):
        r = carte_outils.map_import_existing(motif)
        total = {k: total[k] + r.get(k, 0) for k in total}
    return total
