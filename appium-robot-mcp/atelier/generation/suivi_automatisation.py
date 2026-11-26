"""Suivi d'une demande d'automatisation (QAFlow, écran « Automatisation en cours / terminée »).

La demande part au MCP (boîte de l'atelier : Claude Code ou Cursor) ; ce module garde ce qu'elle visait (point d'entrée,
référence, technologie, tests) et, à chaque lecture, recalcule où en est chaque test d'après l'état RÉEL de l'atelier :
  1. demande prise par l'agent            (boîte : prise, terminée ou échouée)
  2. scénario BDD                          (présent dans Test Design ; « validé » à part)
  3. script généré                         (Robot : un test du dépôt porte la clé ; Kotlin : @Xray dans le projet)
  4. exécuté                               (run réel postérieur à la dernière modification : « Vérifié »)
  5. validé par la QA                      (suite validée par l'automaticien)
Aucune étape n'est cochée sur la parole de l'agent : son compte rendu est affiché à part. Une génération réussie n'est
jamais présentée comme validée. Stockage : <projet>/studio/automatisations/<demande>.json.
"""
from __future__ import annotations

import json
from datetime import datetime

from atelier.domain import projet

ETAPES = (("prise", "Demande prise par l'agent"), ("bdd", "Scénario BDD"), ("genere", "Script généré"),
          ("execute", "Exécuté (run réel)"), ("valide_qa", "Validé par la QA"))
_AGENT = {"en attente": "en_attente", "prise": "en_cours", "terminée": "termine", "échouée": "echec", "annulée": "annule"}


def _d():
    return projet.PROJECT_DIR / "studio" / "automatisations"


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def enregistrer(did: str, entree: str, reference: str, technologie: str, tests: list[str], executer: bool = True) -> dict:
    if not did:
        return {}
    s = {"id": did, "entree": entree, "reference": reference, "technologie": technologie, "tests": list(tests),
         "executer": executer, "cree": _maintenant()}
    _d().mkdir(parents=True, exist_ok=True)
    (_d() / f"{did}.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), "utf-8")
    return s


def _lire(did: str) -> dict:
    f = _d() / f"{did}.json"
    if not did.startswith("DC-") or not f.exists():
        raise KeyError(f"Automatisation inconnue : {did}")
    return json.loads(f.read_text("utf-8"))


def _demande(did: str) -> dict:
    from atelier.integrations import boite_cursor

    return next((d for d in boite_cursor.etat(limite=500)["demandes"] if d["id"] == did), {})


def _date(x: str) -> float:
    try:
        return datetime.fromisoformat(str(x)).timestamp()
    except (TypeError, ValueError):
        return 0.0


def suivi(did: str) -> dict:
    """Où en est la demande, test par test, d'après l'état réel de l'atelier."""
    from atelier.generation import bdd, conception, maintenance, perimetre

    s = _lire(did)
    d = _demande(did)
    statut = d.get("statut", "en attente")
    prise = statut in ("prise", "terminée", "échouée")
    try:
        cycles = maintenance.cycle_bdd()
    except Exception:  # noqa: BLE001 — dépôt illisible : l'avancement des scripts reste inconnu
        cycles = {}
    par_xray, impl = perimetre._bdd_par_cle_xray(), perimetre._implementations()
    cles = list(s["tests"])
    if s["entree"] == "libre" and not cles:  # conçu depuis la demande en clair : les scénarios BDD créés depuis
        t0 = _date(s["cree"])
        cles = [conception.cle_xray_du_scenario(b["cle"]) or b["cle"] for b in bdd.lister() if _date(b.get("maj")) >= t0 > 0]
    titres = {t["cle"]: t["titre"] for t in perimetre._tests_connus()}
    tests = []
    for cle in cles:
        cle_bdd = par_xray.get(cle) or (cle if bdd.charger(cle) else "")
        m = bdd.charger(cle_bdd) if cle_bdd else None
        c = cycles.get(cle_bdd) or {}
        techno = s["technologie"]
        genere = bool(c.get("script")) if techno.startswith("robot") else techno in (impl.get(cle) or {})
        fait = {"prise": prise, "bdd": bool(m), "genere": genere, "execute": bool(c.get("verifie")) and genere,
                "valide_qa": c.get("etat") == "Validé" and genere}
        # prochaine étape réelle du test : un test déjà généré attend son run, pas que l'agent prenne la demande
        suivante = next((lib for k, lib in ETAPES if k != "prise" and not fait[k]), "")
        if not fait["prise"] and not fait["bdd"]:
            suivante = ETAPES[0][1]
        tests.append({"cle": cle, "titre": titres.get(cle) or (m or {}).get("titre", ""), "bdd": cle_bdd,
                      "bdd_statut": (m or {}).get("statut", ""), "suites": c.get("suites", []),
                      "etapes": [{"id": k, "libelle": lib if k != "genere" else f"{lib} ({techno})", "fait": fait[k]} for k, lib in ETAPES],
                      "notions": {"genere": genere, "execute": fait["execute"], "valide_qa": fait["valide_qa"]},
                      "en_attente_de": suivante})
    return {**{k: s.get(k) for k in ("id", "entree", "reference", "technologie", "executer", "cree")},
            "libelle": perimetre.ENTREES.get(s["entree"], s["entree"]), "titre": d.get("titre", ""),
            "agent": {"statut": statut, "etat": _AGENT.get(statut, "en_attente"), "pris": d.get("pris", ""), "fini": d.get("fini", ""),
                      "compte_rendu": d.get("resultat") or d.get("erreur") or "", "mode": d.get("mode", "")},
            "tests": tests, "termine": statut in ("terminée", "échouée", "annulée")}


def lister(limite: int = 20) -> list[dict]:
    """Automatisations récentes (les plus récentes d'abord), avec l'état de l'agent et le nombre de tests générés."""
    d = _d()
    out = []
    for f in sorted(d.glob("DC-*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limite] if d.exists() else []:
        try:
            x = suivi(f.stem)
        except Exception:  # noqa: BLE001 — fichier illisible : ignoré, jamais bloquant
            continue
        out.append({k: x[k] for k in ("id", "libelle", "reference", "technologie", "cree", "termine")} |
                   {"agent": x["agent"]["etat"], "tests": len(x["tests"]), "generes": sum(t["notions"]["genere"] for t in x["tests"])})
    return out
