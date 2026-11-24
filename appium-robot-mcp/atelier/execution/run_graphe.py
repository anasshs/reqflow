"""Graphe du run en direct : les actions d'un run Robot projetées sur les écrans de l'application.

Chaque keyword du run (fil tenu par direct.py, depuis le listener) est rattaché à un écran de la carte :
  - par ses arguments : une variable de locator du dépôt (${IDOUBLIE_CHAMP_TELEPHONE}) reliée à un élément de la carte
    (même valeur, même resource-id : connaissance._depuis_depot) ;
  - sinon par le keyword lui-même (keyword → utilise → locator de la carte), s'il ne touche qu'un ou deux écrans.
et classé en action lisible : ouverture, toucher, saisie, vérification, assertion, défilement, retour, attente, capture.

État d'un écran pendant le run : à venir (un test du run y passera), en cours (l'action courante y est), réussi / échec
(résultat des tests du run qui y sont passés), visité (pendant un test encore en cours). La partie fixe (écrans prévus,
index des locators) est calculée une fois par run ; seule la partie vivante est recalculée à chaque appel.
"""
from __future__ import annotations

import re
import threading

_CACHE: dict = {}
_VERROU = threading.Lock()

ACTIONS = [  # (motif du nom de keyword, action, libellé), le premier qui correspond
    (r"open application|initialiser le test|launch app|ouvrir l.application|new page|open browser", "ouverture", "Ouverture de l'application"),
    (r"input password|fill secret", "saisie", "Saisie (secret)"),
    (r"input text|fill text|type text|saisi|renseign|press keys", "saisie", "Saisie"),
    (r"expect element|should be (enabled|disabled)|should (be|not be) equal|should contain|should match|assert|résultat attendu|est (actif|inactif)",
     "assertion", "Assertion"),
    (r"wait until|element should|page should|vérifier|est affiché|get text|get element", "verification", "Vérification"),
    (r"click|tap|toucher|touche|press element", "toucher", "Toucher"),
    (r"swipe|scroll|défiler", "defilement", "Défilement"),
    (r"go back|press back|retour|revien", "retour", "Retour"),
    (r"sleep|wait for", "attente", "Attente"),
    (r"capture|screenshot", "capture", "Capture d'écran"),
    (r"close application|terminer le test|close browser", "fermeture", "Fermeture"),
]
_ACTIONS = [(re.compile(m, re.I), a, l) for m, a, l in ACTIONS]
VAR = re.compile(r"\$\{([A-Za-z_]\w*)\}")


def action(nom: str) -> tuple[str, str]:
    court = nom.split(".", 1)[1] if "." in nom and not nom.startswith("$") else nom
    for rx, a, lib in _ACTIONS:
        if rx.search(court):
            return a, lib
    return "etape", "Étape"


def _statique(run_id: str) -> dict:
    """Partie fixe d'un run : écrans de l'application (nom, module), écrans prévus par test, index variable → écrans et
    keyword → écrans. Calculée une fois par run."""
    with _VERROU:
        if run_id in _CACHE:
            return _CACHE[run_id]
    from atelier.discovery import connaissance
    from atelier.execution.depot_robot import normaliser
    from atelier.intelligence import couverture_avancee as ca

    g = connaissance.construire()
    N = g.noeuds
    c = ca.carte(g)
    ecrans = {e["id"]: {k: e[k] for k in ("id", "nom", "module", "etat", "tests_xray")} for e in c["ecrans"]}
    prevus = {t["nom"]: [e["id"] for e in c["ecrans"] if t["id"] in e["tests"]] for t in c["tests"]}
    cles = {t["nom"]: t["cle_xray"] for t in c["tests"]}
    ecran_de = {}  # locator de la carte -> écran
    for r in g.relations.values():
        if r.type == "contient" and r.de in ecrans and r.vers.startswith("locator:"):
            ecran_de[r.vers] = r.de
    par_variable: dict = {}
    for i, n in N.items():
        if n.type == "locator" and n.proprietes.get("correspond_a"):
            cibles = {ecran_de[x] for x in n.proprietes["correspond_a"] if x in ecran_de}
            if cibles:
                par_variable.setdefault(n.libelle.lower(), set()).update(cibles)
    par_keyword: dict = {}
    for i, n in N.items():
        if n.type == "keyword":
            cibles = {ecran_de[r.vers] for r in g.sortants(i) if r.type == "utilise" and r.vers in ecran_de}
            if len(cibles) == 1:  # un keyword qui touche plusieurs écrans (socle, navigation, attente du 1er écran) ne situe rien
                par_keyword[normaliser(n.libelle)] = cibles
    transitions = {(r.de, r.vers) for r in g.relations.values() if r.type == "navigue_vers" and r.de in ecrans and r.vers in ecrans}
    s = {"ecrans": ecrans, "prevus": prevus, "cles": cles, "par_variable": par_variable, "par_keyword": par_keyword,
         "transitions": transitions}
    with _VERROU:
        _CACHE.clear()
        _CACHE[run_id] = s
    return s


def _ecran_du_pas(s: dict, p: dict) -> str:
    from atelier.execution.depot_robot import normaliser

    for a in p["args"]:
        for v in VAR.findall(a):
            cibles = s["par_variable"].get(v.lower())
            if cibles and len(cibles) <= 2:
                return sorted(cibles)[0]
    if p["niveau"] <= 1:  # étape BDD : ses sous-actions situent l'écran
        return ""
    court = p["nom"].split(".", 1)[1] if "." in p["nom"] else p["nom"]
    cibles = s["par_keyword"].get(normaliser(court))
    return sorted(cibles)[0] if cibles else ""


def _libelle(p: dict, lib: str) -> str:
    """« Saisie · je saisis le numéro de téléphone du jeu de données » : l'étape BDD en cours dit le pourquoi."""
    court = lambda n: n.split(".", 1)[1] if "." in n and not n.startswith("$") else n  # noqa: E731 (sans le fichier .resource)
    return f"{lib} · {court(p['etape'] or p['nom'])}"[:160]


def vue(depuis: int = 0) -> dict:
    """Run en cours (ou dernier run suivi) projeté sur les écrans : écrans (état, tests, dernière action), chemin parcouru,
    action courante, tests du run, fil des actions récentes."""
    from atelier.execution import direct

    d = direct.pas(0)
    run = d["run"]
    if not run:
        return {"run": None, "ecrans": [], "chemin": [], "courant": None, "pas": [], "n": 0}
    s = _statique(run["id"])
    tests = run["tests"]
    statut_test = {t["nom"]: t["statut"] for t in tests}
    etat: dict = {}
    for t in tests:  # à venir : écrans prévus des tests du run
        for e in s["prevus"].get(t["nom"], []):
            etat.setdefault(e, {"etat": "a_venir", "tests": [], "actions": 0, "derniere": ""})
            if t["nom"] not in etat[e]["tests"]:
                etat[e]["tests"].append(t["nom"])
    chemin, fil, courant, precedent = [], [], None, {}
    for p in d["pas"]:
        a, lib = action(p["nom"])
        a_etape = action(p["etape"])[0] if p["etape"] else ""
        if a_etape in ("ouverture", "fermeture"):  # dans l'initialisation ou la fin du test : l'étape porte l'action
            a, lib = a_etape, action(p["etape"])[1]
        e = _ecran_du_pas(s, p)
        # sonde : une vérification qui échoue alors que le test continue (« suis-je déjà connecté ? ») ne visite pas l'écran
        sonde = p["statut"] == "FAIL" and statut_test.get(p["test"]) != "échec" and a in ("verification", "assertion")
        if sonde:
            a, lib, e = "sonde", "Sonde (absent, le test continue)", ""
        if a in ("ouverture", "fermeture"):
            e = ""
        elif not e:  # locator propre au test (${BOUTON_VALIDER}) ou keyword du socle : sur l'écran où en est le test
            e = precedent.get(p["test"], "")
        x = {"n": p["n"], "t": p["t"][11:19], "test": p["test"], "ecran": e, "action": a, "libelle": _libelle(p, lib),
             "statut": "" if sonde else p["statut"], "niveau": p["niveau"]}
        if fil and fil[-1]["test"] == x["test"] and (fil[-1]["libelle"] == x["libelle"] or fil[-1]["action"] == "etape"):
            garde = x["action"] not in ("ouverture", "fermeture", "sonde")
            fil[-1] = {**x, "ecran": x["ecran"] or (fil[-1]["ecran"] if garde else "")}  # l'étape BDD et son keyword : une seule ligne
        else:
            fil.append(x)
        if e:
            info = etat.setdefault(e, {"etat": "a_venir", "tests": [], "actions": 0, "derniere": ""})
            info["actions"] += 1
            info["derniere"] = x["libelle"]
            if p["test"] and p["test"] not in info["tests"]:
                info["tests"].append(p["test"])
            info.setdefault("parcouru_par", set()).add(p["test"])
            if not chemin or chemin[-1]["ecran"] != e:
                chemin.append({"ecran": e, "test": p["test"], "n": p["n"]})
            precedent[p["test"]] = e
    # état de chaque écran : en cours, résultat des tests du run qui y sont passés, à venir
    en_cours = run.get("courant") or ""
    for e, info in etat.items():
        par = info.pop("parcouru_par", set())
        res = [statut_test.get(t, "") for t in par]
        if "échec" in res:
            info["etat"] = "echec"
        elif en_cours in par:
            info["etat"] = "visite"
        elif res and all(r == "réussi" for r in res):
            info["etat"] = "reussi"
        elif par:
            info["etat"] = "visite"
    actifs = [x for x in fil if x["test"] == en_cours and x["ecran"]] if run.get("statut") == "en cours" else []
    if actifs:
        dernier = actifs[-1]
        etat[dernier["ecran"]]["etat"] = "en_cours"
        courant = {**dernier, "action_courante": next((x for x in reversed(fil) if x["test"] == en_cours and x["action"] != "etape"),
                                                      next((x for x in reversed(fil) if x["test"] == en_cours), dernier))}
    ecrans = [{**s["ecrans"].get(e, {"id": e, "nom": e.split(":", 1)[-1], "module": "", "tests_xray": []}), **info,
               "connu": e in s["ecrans"]} for e, info in etat.items()]
    liens = []
    for a, b in zip(chemin, chemin[1:]):
        if a["test"] == b["test"] and (a["ecran"], b["ecran"]) not in [(x["de"], x["vers"]) for x in liens]:
            liens.append({"de": a["ecran"], "vers": b["ecran"], "test": a["test"]})
    return {"run": {k: run.get(k) for k in ("id", "nom", "suite", "statut", "debut", "fin", "courant", "etape", "keyword", "compte",
                                              "total", "termines")},
            "tests": [{**t, "cle_xray": s["cles"].get(t["nom"], "")} for t in tests],
            "ecrans": ecrans, "liens": liens, "chemin": chemin[-60:], "courant": courant,
            "pas": [x for x in fil if x["n"] > depuis][-80:], "n": d["n"]}
