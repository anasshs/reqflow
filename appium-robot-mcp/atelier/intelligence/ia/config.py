"""Réglages de l'IA : entreprise → projet → opération ; le plus spécifique l'emporte, sans dépasser les plafonds de
l'entreprise (tokens, budgets).

- Entreprise : fichier désigné par ATELIER_IA_CONFIG (facultatif, posé par l'entreprise sur le poste).
- Projet : <projet de tests>/atelier_ia.yaml, versionné avec le projet (donc partagé par l'équipe et historisé par git),
  modifiable depuis Paramètres › IA ; chaque modification est aussi historisée dans le journal du poste.
- Opération : section `operations.<opération>` du projet.

Sans aucun réglage, le comportement est celui d'avant : un seul modèle (IA_INTERNE_MODELE ou CLAUDE_MODEL), les limites
fixées par chaque appel. Le fournisseur reste choisi par l'entreprise (IA_FOURNISSEUR) : un modèle déclaré pour un
autre fournisseur est ignoré, jamais appelé.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path

NIVEAUX = ("economique", "avance", "secours")
CHOIX_NIVEAU = ("auto", "economique", "avance")
DETAILS = ("minimal", "standard", "complet")
SEUILS = ("information", "avertissement", "restriction", "blocage")

DEFAUT = {
    "modeles": {},          # niveau -> {modele, fournisseur?, max_entree, max_sortie, temperature, timeout, tentatives, actif}
    "operations": {},       # opération -> {niveau, max_sortie, cache_heures, contexte: {...}}
    "routage": {"seuil_avance_tokens": 12000, "sante_min_appels": 4, "sante_taux_echec": 0.5},
    "contexte": {"max_tests": 400, "max_exigences": 50, "max_elements": 400, "max_ecrans": 30, "detail": "standard"},
    "optimisation": {"compacter": True, "alleger_mcp": True, "cache_prompt": False},
    "cache": {"actif": True, "duree_heures": 168},
    "budgets": {"global": 0, "projets": {}, "modules": {}, "postes": {},
                "seuils": {"information": 50, "avertissement": 80, "restriction": 90, "blocage": 100}},
    "simulateur": {"conserver_entrees": True, "max_entrees": 200},
    "perimetre": {"max_indirects": 40, "max_qualification": 30},  # modèle applicatif : plafonds du périmètre d'un build
}
PLAFONDS = (("modeles", "*", "max_entree"), ("modeles", "*", "max_sortie"), ("operations", "*", "max_sortie"), ("budgets", "global"))


def _lire_yaml(f: Path) -> dict:
    import yaml

    try:
        d = yaml.safe_load(f.read_text("utf-8")) if f.exists() else {}
    except (OSError, yaml.YAMLError):
        return {}
    return d if isinstance(d, dict) else {}


def fichier_projet() -> Path:
    from atelier.domain import projet

    return projet.PROJECT_DIR / "atelier_ia.yaml"


def fichier_entreprise() -> Path | None:
    v = os.environ.get("ATELIER_IA_CONFIG", "").strip()
    return Path(v).expanduser() if v else None


def _fusion(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for k, v in (b or {}).items():
        out[k] = _fusion(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def _plafonner(eff: dict, ent: dict) -> dict:
    """Une valeur du projet ne dépasse jamais le plafond fixé par l'entreprise (0 ou absent : pas de plafond)."""
    def borne(v, p):
        return min(v, p) if isinstance(v, (int, float)) and isinstance(p, (int, float)) and p > 0 and v > 0 else (p if not v and p else v)
    for chemin in PLAFONDS:
        if chemin[1] == "*":
            for nom, entree in (eff.get(chemin[0]) or {}).items():
                p = ((ent.get(chemin[0]) or {}).get(nom) or {}).get(chemin[2]) or ((ent.get(chemin[0]) or {}).get("*") or {}).get(chemin[2])
                if p and isinstance(entree, dict):
                    entree[chemin[2]] = borne(entree.get(chemin[2]), p)
        else:
            p = (ent.get(chemin[0]) or {}).get(chemin[1])
            if p:
                eff[chemin[0]][chemin[1]] = borne(eff[chemin[0]].get(chemin[1]), p)
    return eff


def projet_brut() -> dict:
    return _lire_yaml(fichier_projet())


def entreprise_brut() -> dict:
    f = fichier_entreprise()
    return _lire_yaml(f) if f else {}


def effective() -> dict:
    """Réglages appliqués : défauts ← entreprise ← projet, plafonnés par l'entreprise."""
    ent = entreprise_brut()
    return _plafonner(_fusion(_fusion(DEFAUT, ent), projet_brut()), ent)


def modele_par_defaut() -> str:
    from atelier.intelligence import fournisseur_ia

    f = fournisseur_ia.fournisseur()
    if f == "interne":
        return os.environ.get("IA_INTERNE_MODELE", "")
    if f == "anthropic":
        from atelier.intelligence import assistant

        return assistant.MODELE
    return ""


def modeles(cfg: dict | None = None) -> dict:
    """{niveau: entrée} utilisables avec le fournisseur actif ; un niveau non réglé prend le modèle par défaut."""
    from atelier.intelligence import fournisseur_ia

    cfg = cfg or effective()
    actif = fournisseur_ia.fournisseur()
    defaut = {"modele": modele_par_defaut(), "actif": True}
    out = {}
    for n in NIVEAUX:
        e = {**defaut, **((cfg.get("modeles") or {}).get(n) or {})}
        if e.get("fournisseur") and e["fournisseur"] != actif:
            e = {**defaut, "ignore": f"déclaré pour « {e['fournisseur']} », fournisseur actif « {actif} »"}
        out[n] = e
    return out


def pour_operation(operation: str, cfg: dict | None = None) -> dict:
    """Réglages d'une opération : niveau, limites, contexte et cache, avec ceux du projet et de l'entreprise en repli."""
    from atelier.intelligence.ia import operations

    cfg = cfg or effective()
    o = (cfg.get("operations") or {}).get(operation) or {}
    return {"operation": operation, "niveau": o.get("niveau") or operations.niveau_defaut(operation), "max_sortie": o.get("max_sortie"),
            "contexte": {**cfg["contexte"], **(o.get("contexte") or {})},
            "cache": {**cfg["cache"], **({"duree_heures": o["cache_heures"]} if o.get("cache_heures") is not None else {}),
                      **({"actif": o["cache"]} if isinstance(o.get("cache"), bool) else {})},
            "optimisation": cfg["optimisation"], "routage": cfg["routage"], "modeles": modeles(cfg)}


def contexte(operation: str) -> dict:
    """Plafonds du contexte transmis pour une opération (nombre de tests, d'exigences, d'éléments, niveau de détail)."""
    try:
        return pour_operation(operation)["contexte"]
    except Exception:  # noqa: BLE001 — sans réglage lisible, les plafonds par défaut
        return dict(DEFAUT["contexte"])


def plafond(operation: str, cle: str, demande: int) -> int:
    """La valeur demandée par l'appelant, sans dépasser le plafond réglé pour l'opération."""
    p = contexte(operation).get(cle)
    return min(int(demande), int(p)) if isinstance(p, (int, float)) and p > 0 else int(demande)


# =========================================================================== écriture depuis l'atelier
def valider(d: dict) -> list[str]:
    """Erreurs de forme d'un réglage de projet (liste vide : valide)."""
    err = []
    if not isinstance(d, dict):
        return ["Réglage attendu : un objet."]
    for n, e in (d.get("modeles") or {}).items():
        if n not in NIVEAUX:
            err.append(f"Niveau de modèle inconnu : {n} ({', '.join(NIVEAUX)}).")
        elif not isinstance(e, dict) or not str(e.get("modele") or "").strip():
            err.append(f"Modèle {n} : nom du modèle obligatoire.")
        else:
            for k in ("max_entree", "max_sortie", "timeout", "tentatives"):
                if k in e and (not isinstance(e[k], int) or e[k] < 0):
                    err.append(f"Modèle {n} : {k} doit être un entier positif.")
            if "temperature" in e and e["temperature"] is not None and not (isinstance(e["temperature"], (int, float)) and 0 <= e["temperature"] <= 2):
                err.append(f"Modèle {n} : température entre 0 et 2.")
    for op, o in (d.get("operations") or {}).items():
        if not isinstance(o, dict):
            err.append(f"Opération {op} : réglage attendu.")
        elif o.get("niveau") and o["niveau"] not in CHOIX_NIVEAU:
            err.append(f"Opération {op} : niveau {', '.join(CHOIX_NIVEAU)}.")
    for k, v in (d.get("perimetre") or {}).items():
        if k not in DEFAUT["perimetre"] or not isinstance(v, int) or v < 0:
            err.append(f"Périmètre : {k} doit être un entier positif ou nul ({', '.join(DEFAUT['perimetre'])}).")
    c = d.get("contexte") or {}
    if c.get("detail") and c["detail"] not in DETAILS:
        err.append(f"Contexte : niveau de détail {', '.join(DETAILS)}.")
    s = (d.get("budgets") or {}).get("seuils") or {}
    vals = [s.get(k) for k in SEUILS if s.get(k) is not None]
    if vals != sorted(vals):
        err.append("Budgets : seuils croissants (information ≤ avertissement ≤ restriction ≤ blocage).")
    return err


def enregistrer(d: dict) -> dict:
    """Remplace le réglage du projet (atelier_ia.yaml) après contrôle ; l'ancien et le nouveau sont historisés."""
    import yaml

    from atelier.intelligence.ia import journal

    err = valider(d)
    if err:
        raise ValueError(" ".join(err))
    avant = projet_brut()
    propre = {k: v for k, v in d.items() if k in DEFAUT and v not in (None, {}, [])}
    fichier_projet().write_text("# Réglages IA du projet (Paramètres › IA). Versionné avec le projet.\n"
                                + yaml.safe_dump(propre, allow_unicode=True, sort_keys=False), encoding="utf-8")
    journal.historiser_reglage("projet", avant, propre)
    return etat()


def historique(limite: int = 30) -> list[dict]:
    from atelier.intelligence.ia import journal

    return journal.lire("SELECT * FROM reglages ORDER BY date DESC LIMIT ?", (limite,))


def etat() -> dict:
    from atelier.intelligence import fournisseur_ia
    from atelier.intelligence.ia import operations

    eff = effective()
    return {"fournisseur": fournisseur_ia.etat(), "projet": projet_brut(), "entreprise": entreprise_brut(),
            "fichier_entreprise": str(fichier_entreprise() or ""), "effective": eff, "modeles": modeles(eff),
            "operations": {op: {**v, **{k: x for k, x in pour_operation(op, eff).items() if k in ("niveau", "max_sortie", "contexte", "cache")}}
                           for op, v in operations.connues().items()},
            "niveaux": NIVEAUX, "choix_niveau": CHOIX_NIVEAU, "details": DETAILS, "seuils": SEUILS}
