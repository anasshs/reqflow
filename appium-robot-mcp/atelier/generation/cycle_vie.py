"""Cycle de vie d'un test, aligné sur le workflow Jira de l'équipe :

  Brouillon → Rédigé → À automatiser → En cours d'automatisation → Automatisé

Gardes (vérifiées par l'atelier avant toute transition) :
- Brouillon → Rédigé : aucun contrôle bloquant de la revue (étapes, résultat attendu…) ;
- Rédigé → À automatiser : le test est candidat à l'automatisation : le champ Jira « candidat auto » (configuré dans
  Xray Mapping) est mis à la valeur vraie AVANT la transition (le workflow Jira l'exige) ;
- À automatiser → En cours d'automatisation : libre (quelqu'un prend l'automatisation) ; proposé dès qu'un script
  Robot porte la clé ;
- En cours d'automatisation → Automatisé : invariant 5 : un script Robot porte la clé, sa suite a 3 exécutions réelles
  stables ET son script est approuvé en revue technique (Automation Studio).
Retours possibles : Rédigé → Brouillon, À automatiser → Rédigé, Automatisé → En cours d'automatisation (régression).

Jira est la référence : chaque transition est d'abord appliquée dans Jira (statut configuré pour l'étape dans Xray
Mapping) ; en cas d'échec rien n'est changé localement. Sans Jira configuré, l'étape locale avance et un avertissement
rappelle de la reporter. Historique local : conception/cycle_vie.json.
"""
from __future__ import annotations

import json

from atelier.domain import projet
from atelier.intelligence.strategie import _auteur, _ecrire_atomique, _maintenant

ETAPES = ["brouillon", "redige", "a_automatiser", "en_automatisation", "automatise"]
LIBELLES = {"brouillon": "Brouillon", "redige": "Rédigé", "a_automatiser": "À automatiser",
            "en_automatisation": "En cours d'automatisation", "automatise": "Automatisé"}
TRANSITIONS = {("brouillon", "redige"), ("redige", "a_automatiser"), ("a_automatiser", "en_automatisation"),
               ("en_automatisation", "automatise"),
               ("redige", "brouillon"), ("a_automatiser", "redige"), ("automatise", "en_automatisation")}
DEFAUT_CONFIG = {"statuts": {e: "" for e in ETAPES}, "champ_candidat": "", "valeur_candidat": "true"}


def _fichier():
    return projet.PROJECT_DIR / "conception" / "cycle_vie.json"


def _etats() -> dict:
    f = _fichier()
    return json.loads(f.read_text("utf-8")) if f.exists() else {}


def config() -> dict:
    from atelier.generation import conception

    c = conception.mapping().get("cycle_vie") or {}
    return {"statuts": {**DEFAUT_CONFIG["statuts"], **(c.get("statuts") or {})},
            "champ_candidat": c.get("champ_candidat", ""), "valeur_candidat": c.get("valeur_candidat") or "true"}


def maj_config(statuts: dict | None = None, champ_candidat: str | None = None, valeur_candidat: str | None = None) -> dict:
    from atelier.generation import conception

    c = config()
    if statuts is not None:
        inconnues = set(statuts) - set(ETAPES)
        if inconnues:
            raise ValueError(f"Étape inconnue : {', '.join(sorted(inconnues))}.")
        c["statuts"].update({k: str(v or "").strip() for k, v in statuts.items()})
    if champ_candidat is not None:
        c["champ_candidat"] = champ_candidat.strip()
    if valeur_candidat is not None:
        c["valeur_candidat"] = valeur_candidat.strip() or "true"
    conception.enregistrer_mapping({"cycle_vie": c})
    return c


def _valeur_jira(v: str):
    """« true » / « false » → booléen (case à cocher) ; « Oui » → option ({"value": "Oui"}) ; sinon texte."""
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    if v.startswith("option:"):
        return {"value": v.split(":", 1)[1]}
    if v.startswith("options:"):
        return [{"value": v.split(":", 1)[1]}]
    return v


def _scripts(cle: str) -> list[str]:
    from atelier.execution import depot_robot

    return sorted({t["fichier"] for t in depot_robot.lire_depot()["tests"].values() if cle in (t.get("cles_xray") or [])})


def gardes(cle: str, vers: str) -> list[dict]:
    """Conditions de la transition vers « vers » : [{ok, message}] ; une seule non remplie suffit à bloquer."""
    out = []
    if vers == "redige":
        from atelier.generation import conception

        bloquants = [c["message"] for c in conception.controles_revue(cle) if c["gravite"] == "haute"]
        out.append({"ok": not bloquants, "message": "Contrôles de rédaction : " + ("aucun blocage" if not bloquants else " ; ".join(bloquants))})
    elif vers == "a_automatiser":
        c = config()
        out.append({"ok": bool(c["champ_candidat"]), "message": f"Champ « candidat auto » {'configuré : ' + c['champ_candidat'] if c['champ_candidat'] else 'à configurer dans Xray Mapping'} "
                                                                 f"(mis à {c['valeur_candidat']} avant la transition)"})
    elif vers == "automatise":
        from atelier.generation import studio

        scripts = _scripts(cle)
        out.append({"ok": bool(scripts), "message": f"Script Robot portant la clé : {', '.join(scripts) or 'aucun'}"})
        if scripts:
            stab = studio._stabilite_suites(scripts)
            revues = studio.revues_scripts()
            for f in scripts:
                out.append({"ok": stab[f]["stable"], "message": f"{f} : {studio.EXECUTIONS_STABLES} exécutions réelles stables"
                            + ("" if stab[f]["stable"] else " (pas encore)")})
                st = (revues.get(f) or {}).get("statut", "Generated")
                out.append({"ok": st in ("Approved", "Published"), "message": f"{f} : revue du script ({st})"})
    return out


def etat(cle: str) -> dict:
    e = _etats().get(cle) or {"etape": "brouillon", "historique": []}
    i = ETAPES.index(e["etape"])
    possibles = [v for (d, v) in TRANSITIONS if d == e["etape"]]
    suivante = ETAPES[i + 1] if i + 1 < len(ETAPES) else ""
    conseil = ""
    if e["etape"] == "a_automatiser" and _scripts(cle):
        conseil = "Un script Robot porte déjà la clé : passer en « En cours d'automatisation »."
    return {"cle": cle, **e, "libelle": LIBELLES[e["etape"]], "suivante": suivante,
            "gardes_suivante": gardes(cle, suivante) if suivante else [],
            "possibles": sorted(possibles, key=ETAPES.index), "conseil": conseil, "statuts_jira": config()["statuts"]}


def avancer(cle: str, vers: str, commentaire: str = "", jira=None) -> dict:
    """Transition vers « vers » : gardes, puis Jira (champ candidat puis statut), puis état local et historique."""
    if vers not in ETAPES:
        raise ValueError(f"Étape inconnue : {vers}.")
    etats = _etats()
    e = etats.get(cle) or {"etape": "brouillon", "historique": []}
    if (e["etape"], vers) not in TRANSITIONS:
        raise ValueError(f"Transition impossible : {LIBELLES[e['etape']]} → {LIBELLES[vers]}.")
    if ETAPES.index(vers) > ETAPES.index(e["etape"]):  # gardes en avançant seulement
        ko = [g["message"] for g in gardes(cle, vers) if not g["ok"]]
        if ko:
            raise PermissionError("Conditions non remplies : " + " ; ".join(ko))
    c = config()
    avertissement = ""
    if jira is None:
        from atelier.integrations.jira import JiraClient

        jira = JiraClient()
    if getattr(jira, "enabled", False):
        if vers == "a_automatiser":
            jira.maj_champs(cle, {c["champ_candidat"]: _valeur_jira(c["valeur_candidat"])})
        if c["statuts"].get(vers):
            jira.transition(cle, c["statuts"][vers])
        else:
            avertissement = f"Statut Jira de l'étape « {LIBELLES[vers]} » non configuré (Xray Mapping) : statut Jira inchangé."
    else:
        avertissement = "Jira non configuré : étape locale seulement, à reporter dans Jira."
    e["historique"].append({"date": _maintenant(), "auteur": _auteur(), "de": e["etape"], "vers": vers,
                            "commentaire": commentaire.strip(), "jira": c["statuts"].get(vers, "") if not avertissement else ""})
    e["etape"] = vers
    etats[cle] = e
    _fichier().parent.mkdir(parents=True, exist_ok=True)
    _ecrire_atomique(_fichier(), json.dumps(etats, ensure_ascii=False, indent=1))
    return {**etat(cle), "avertissement": avertissement}


def synthese() -> dict:
    """Nombre de tests par étape (tests suivis par l'atelier)."""
    n = {k: 0 for k in ETAPES}
    for e in _etats().values():
        n[e["etape"]] = n.get(e["etape"], 0) + 1
    return {"etapes": [{"etape": k, "libelle": LIBELLES[k], "tests": n[k]} for k in ETAPES]}
