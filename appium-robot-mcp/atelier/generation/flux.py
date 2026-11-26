"""Flux de passage d'un test : « simple » (par défaut) ou « complet ».

simple   : générer le BDD → automatiser → publier dans Xray. Aucune approbation intermédiaire : la seule décision de
           l'utilisateur est « Publier dans Xray ». Elle valide le scénario BDD et approuve ses scripts (tracés à son nom,
           « à la publication »), puis publie au TNR (tests Xray, plan, campagne). Un run réel n'est pas exigé : son
           résultat s'affiche (vérifié / pas encore exécuté) sans bloquer.
complet  : le cycle détaillé (Relire et valider → Automatiser → Vérifier → Publier, revue technique, quatre yeux,
           runs bloqués tant qu'un script généré n'est pas approuvé).

Ce qui ne change pas, quel que soit le flux : les contrôles de gravité haute (scénario ou script) empêchent la
publication de ce scénario ; un test qui crée une donnée réelle (consomme_donnee) ne s'exécute pas sans validation ou
dérogation ; une correction de test n'est pas déclarée fiable sans 3 runs stables et revue humaine (maintenance).

Réglage par projet (Lots TNR › réglage du flux), fichier conception/flux.json ; ATELIER_FLUX l'impose (tests, poste)."""
from __future__ import annotations

import json
import os

from atelier.domain import projet

MODES = ("simple", "complet")


def _fichier():
    return projet.PROJECT_DIR / "conception" / "flux.json"


def mode() -> str:
    impose = os.environ.get("ATELIER_FLUX", "").strip().lower()
    if impose in MODES:
        return impose
    try:
        m = json.loads(_fichier().read_text("utf-8")).get("mode")
    except (OSError, ValueError, AttributeError):
        m = None
    return m if m in MODES else "simple"


def simple() -> bool:
    return mode() == "simple"


def regler(m: str) -> dict:
    if m not in MODES:
        raise ValueError("Flux : simple ou complet.")
    f = _fichier()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"mode": m}, ensure_ascii=False), "utf-8")
    return etat()


def etat() -> dict:
    return {"mode": mode(), "impose": os.environ.get("ATELIER_FLUX", "").strip().lower() in MODES,
            "etapes": ["Générer le BDD", "Automatiser", "Publier dans Xray"] if simple()
            else ["Relire et valider", "Automatiser", "Vérifier", "Publier au TNR"]}


def publier(cles_bdd: list[str], xray=None) -> dict:
    """Publier dans Xray (flux simple) : décision de l'utilisateur, à n'appeler que depuis son clic (ou une demande
    validée). Pour chaque scénario : validation du BDD, approbation de ses scripts, puis publication au TNR. Un scénario
    bloqué par un contrôle de gravité haute n'est pas publié ; les autres le sont."""
    from atelier.generation import bdd, lots, studio, tnr

    if not cles_bdd:
        raise ValueError("Choisir au moins un scénario.")
    par_bdd, _ = lots._index_tests()
    prets, refus = [], []
    for cle in cles_bdd:
        try:
            m = bdd._exiger(cle)
            tests = par_bdd.get(cle) or []
            if not tests:
                raise ValueError("pas encore automatisé : l'automatiser d'abord")
            if m.get("statut") not in ("validé", "valide"):
                bdd.valider(cle)
            for suite in sorted({t["suite"] for t in tests}):
                studio.approuver_a_la_publication(suite)
            prets.append(cle)
        except Exception as e:  # noqa: BLE001 - un scénario refusé n'empêche pas les autres
            refus.append({"scenario": cle, "erreur": str(e)[:300]})
    r = tnr.publier(prets, xray=xray) if prets else {"publies": [], "erreurs": [], "plan": None, "campagne": None}
    publies = [p["scenario"] for p in r.get("publies") or [] if p.get("scenario")]
    git = None
    if publies:  # le code des tests publiés va dans le dépôt, prêt pour la merge request ; Git indisponible : publication gardée
        from atelier.generation import versionnement

        try:
            git = versionnement.committer(publies, xray={p["scenario"]: p.get("xray") or "" for p in r["publies"]})
        except Exception as e:  # noqa: BLE001
            git = {"erreur": str(e)[:300]}
    return {**r, "erreurs": refus + list(r.get("erreurs") or []), "git": git}
