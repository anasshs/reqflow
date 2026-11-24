"""Lots TNR : la vue de travail du chemin « parcours → scénarios → automatisation vérifiée → TNR ».

Un lot regroupe des scénarios BDD (un parcours cadré, une fonctionnalité…) et vit dans le temps : on y ajoute des
scénarios, ils suivent le même chemin et rejoignent le même plan TNR de l'application. Les lots sont décrits dans
conception/lots.yaml ; l'appartenance d'un scénario à un lot est le champ « lot » de son BDD.

Un seul statut par scénario, lu dans l'ordre du chemin (le plus avancé atteint) :
  Brouillon → Validé → Automatisé → Vérifié → Au TNR
« Automatisé » : un test Robot porte la clé du scénario (ou sa clé Xray) ; « Vérifié » : tous ses tests ont passé en
run réel depuis leur dernière modification ; « Au TNR » : sa clé Xray fait partie de la campagne TNR de l'application.
Les étapes sautées restent visibles (« à revoir ») : un scénario jamais validé mais déjà au TNR le dit.
Les exigences Jira liées (champ « exigences » du BDD) sont affichées si elles existent ; elles ne bloquent rien.
"""
from __future__ import annotations

from datetime import datetime

import yaml

from atelier.domain import projet
from atelier.domain.yaml_rapide import charger as charger_yaml

from atelier.domain.cycle import STATUTS_SCENARIO as STATUTS  # définition unique du cycle
SANS_LOT = "sans-lot"
STATUTS_SIMPLES = ("Brouillon", "Automatisé", "Dans Xray")  # flux simple (generation/flux.py) : générer → automatiser → publier


def statuts() -> tuple:
    from atelier.generation import flux

    return STATUTS_SIMPLES if flux.simple() else STATUTS


def _fichier():
    return projet.PROJECT_DIR / "conception" / "lots.yaml"


def _lire() -> dict:
    f = _fichier()
    return (charger_yaml(f.read_text("utf-8")) or {}) if f.exists() else {}


def _ecrire(d: dict):
    f = _fichier()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False, width=120), "utf-8")


def creer(nom: str, parcours: str = "", description: str = "") -> dict:
    """Crée un lot (nom obligatoire) ; parcours : identifiant d'un parcours utilisateur cadré (« PU-… »), facultatif."""
    nom = (nom or "").strip()
    if not nom:
        raise ValueError("Nom du lot obligatoire.")
    d = _lire()
    lid = projet.slug(nom, 50, "lot")
    if lid in d:
        raise ValueError(f"Le lot « {nom} » existe déjà.")
    d[lid] = {"nom": nom, "parcours": (parcours or "").strip(), "description": (description or "").strip(),
              "cree": datetime.now().astimezone().isoformat(timespec="seconds")}
    _ecrire(d)
    return {"id": lid, **d[lid]}


def rattacher(lot: str, cles: list[str]) -> list[str]:
    """Met des scénarios BDD dans un lot (« sans-lot » pour les en retirer)."""
    from atelier.generation import bdd

    if lot != SANS_LOT and lot not in _lire():
        raise KeyError(f"Lot inconnu : {lot}")
    faits = []
    for cle in cles:
        m = bdd._exiger(cle)
        m["lot"] = "" if lot == SANS_LOT else lot
        bdd.sauver(m, auteur="lot")
        faits.append(cle)
    return faits


def _index_tests() -> tuple[dict, dict]:
    """Tests Robot par clé de scénario BDD, et correspondance clé Xray → clé BDD."""
    from atelier.generation import conception, maintenance

    xray_vers_bdd = {v.get("xray"): k for k, v in conception._publications_xray().items() if v.get("xray")}
    par_bdd: dict = {}
    for s in maintenance.vue()["suites"]:
        for t in s["tests"]:
            cles = set(t.get("bdd") or []) | {xray_vers_bdd[k] for k in t.get("cles") or [] if k in xray_vers_bdd}
            for c in cles:
                par_bdd.setdefault(c, []).append({**t, "suite": s["fichier"], "etat_suite": s["etat"]})
    return par_bdd, xray_vers_bdd


def scenarios_des_tests(ids_tests: list[str]) -> list[str]:
    """Clés des scénarios BDD des tests Robot choisis (« fichier::nom », ou un fichier de suite entier)."""
    par_bdd, _ = _index_tests()
    choisis = set(ids_tests)
    return sorted({c for c, tests in par_bdd.items() for t in tests if t["id"] in choisis or t["suite"] in choisis})


def _ligne(m: dict, tests: list[dict], au_tnr: set, cle_xray: str) -> dict:
    valide = m.get("statut") == "valide" or m.get("statut") == "validé"
    automatise = bool(tests)
    verifie = automatise and all(t["verifie"] for t in tests)
    tnr = bool(cle_xray) and cle_xray in au_tnr
    atteint = [valide, automatise, verifie, tnr]
    from atelier.generation import flux

    if flux.simple():  # aucune approbation : le scénario généré s'automatise, puis se publie ; le run est une information
        statut = STATUTS_SIMPLES[2 if tnr else 1 if automatise else 0]
        action = None if tnr else {"id": "publier", "libelle": "Publier dans Xray"} if automatise else {"id": "automatiser", "libelle": "Automatiser"}
        echec = next((t["dernier"] for t in tests if t.get("dernier") and t["dernier"]["statut"] != "PASS"), None)
        return {"cle": m["cle"], "titre": m.get("titre") or m["cle"], "module": m.get("module", ""), "jdd": m.get("jdd", ""),
                "lot": m.get("lot") or SANS_LOT, "exigences": m.get("exigences") or [], "xray": cle_xray, "statut": statut,
                "a_revoir": [], "etapes": {"automatise": automatise, "au_tnr": tnr}, "verifie": verifie,
                "tests": [{"id": t["id"], "nom": t["nom"], "verifie": t["verifie"], "dernier": t.get("dernier"), "suite": t["suite"]} for t in tests],
                "echec": echec, "action": action}
    statut = STATUTS[max([0] + [i + 1 for i, ok in enumerate(atteint) if ok])]
    a_revoir = [STATUTS[i + 1] for i in range(STATUTS.index(statut) - 1) if not atteint[i]]
    echec = next((t["dernier"] for t in tests if t.get("dernier") and t["dernier"]["statut"] != "PASS"), None)
    if not automatise:
        action = {"id": "automatiser", "libelle": "Automatiser"} if valide else {"id": "valider", "libelle": "Relire et valider"}
    elif not verifie:
        action = {"id": "verifier", "libelle": "Vérifier"}
    elif not tnr:
        action = {"id": "publier", "libelle": "Publier au TNR"}
    else:
        action = None
    return {"cle": m["cle"], "titre": m.get("titre") or m["cle"], "module": m.get("module", ""), "jdd": m.get("jdd", ""),
            "lot": m.get("lot") or SANS_LOT, "exigences": m.get("exigences") or [], "xray": cle_xray, "statut": statut,
            "a_revoir": a_revoir, "etapes": dict(zip(("valide", "automatise", "verifie", "au_tnr"), atteint)),
            "tests": [{"id": t["id"], "nom": t["nom"], "verifie": t["verifie"], "dernier": t.get("dernier"), "suite": t["suite"]} for t in tests],
            "echec": echec, "action": action}


def vue(lot: str = "") -> dict:
    """Lots et, pour le lot demandé (ou tous), une ligne par scénario : statut unique, étapes, prochaine action."""
    from atelier.execution import centre
    from atelier.generation import bdd, conception, flux, tnr

    conv = tnr.conventions()
    camp = next((c for c in centre.campagnes() if c["id"] == conv["campagne"]), None) if conv["campagne"] else None
    au_tnr = set((camp or {}).get("tests") or [])
    par_bdd, _ = _index_tests()
    lots = _lire()
    lignes = []
    slug = conv["slug"]
    for b in bdd.lister():
        m = bdd.charger(b["cle"]) or {}
        if not m.get("scenarios") or not any(s.get("etapes") for s in m["scenarios"]):
            continue  # scénario vide : rien à suivre
        tests = par_bdd.get(b["cle"], [])
        # application active seulement : rattaché à un lot, déclaré pour elle, ou automatisé dans tests/<application>/
        if not (m.get("lot") in lots or (m.get("application") or "") == slug
                or any(t["suite"].startswith(f"tests/{slug}/") for t in tests)):
            continue
        lignes.append(_ligne({**m, "cle": b["cle"]}, tests, au_tnr, conception.cle_xray_du_scenario(b["cle"])))
    resume = {}
    for x in lignes:
        r = resume.setdefault(x["lot"], {s: 0 for s in statuts()})
        r[x["statut"]] += 1
    liste = [{"id": k, **v, "compte": resume.get(k, {s: 0 for s in statuts()})} for k, v in lots.items()]
    if SANS_LOT in resume:
        liste.append({"id": SANS_LOT, "nom": "Sans lot", "parcours": "", "description": "", "compte": resume[SANS_LOT]})
    return {"lots": liste, "conventions": conv, "campagne": camp and {k: camp.get(k) for k in ("id", "nom", "plan_xray", "derniere_execution", "dernier_statut", "taux_reussite")},
            "scenarios": [x for x in lignes if not lot or x["lot"] == lot], "statuts": list(statuts()), "flux": flux.etat()}

