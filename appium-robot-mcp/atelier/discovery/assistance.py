"""AI Assisted Discovery : suggestions de prochaines actions pendant une session (phase 4 du cahier).

Base explicable (toujours calculée) : actions jamais essayées depuis l'écran courant, classées par le classement
des actions (seules les actions « safe » sont proposées ; contrôlées, sensibles et interdites sont écartées et
comptées), puis pistes globales de la carte (impasses, écrans à nommer, transitions instables).

Avec un fournisseur d'IA à appel direct (IA_FOURNISSEUR = interne ou anthropic), le modèle reçoit les libellés
masqués des candidates et les noms des écrans connus, et ne fait que les **ordonner et justifier** : une clé
qu'il inventerait est ignorée ; aucune action n'est exécutée sans clic de l'automaticien.
"""
from __future__ import annotations

import json

from atelier.discovery import carte, classement

SYSTEME = ("Tu aides un automaticien à explorer une application (découverte). On te donne l'écran courant, les écrans déjà "
           "connus et des actions candidates jamais essayées. Classe au plus 5 candidates par intérêt pour découvrir de "
           "nouveaux écrans ou parcours métier. Réponds uniquement en JSON : [{\"cle\": \"...\", \"raison\": \"...\"}]. "
           "N'utilise que les clés fournies.")


def candidates(elements: list[dict], ecran_id: str, plateforme: str) -> dict:
    """Actions jamais essayées depuis l'écran, avec leur classe ; seules les « safe » sont proposables."""
    deja = carte.actions_depuis(ecran_id, plateforme) if ecran_id else set()
    r = classement.regles()
    env = classement.environnement_session()
    libre = classement.exploration_libre(env, r)
    out, ecartees = [], {"controlled": 0, "sensitive": 0, "forbidden": 0}
    for el in elements or []:
        if el.get("type") not in ("bouton", "lien", "element", "liste", "champ", "case"):
            continue
        if el.get("key") in deja or (el.get("locators") or [""])[0] in deja:
            continue
        c = classement.classer(el, r=r, environnement=env if libre else "")
        if c["classe"] != "safe" and not (libre and c["classe"] != "forbidden"):
            ecartees[c["classe"]] += 1
            continue
        out.append({"cle": el["key"], "libelle": el.get("libelle") or "", "type": el.get("type"),
                    "locator": (el.get("locators") or [""])[0], "classe": c["classe"],
                    "raison": "jamais essayée depuis cet écran"})
    return {"candidates": out, "ecartees": ecartees}


def pistes(perimetre: dict | None = None) -> list[dict]:
    """Pistes globales de la carte : impasses, écrans isolés, écrans à nommer, transitions instables. Avec un
    périmètre, seules les impasses et les écrans isolés du périmètre sont proposés."""
    from atelier.discovery import sessions_discovery

    if not carte.app_courante():
        return []
    n = sessions_discovery.navigation()
    dedans = lambda x: not perimetre or x["id"] in perimetre["ecrans"]  # noqa: E731
    p = [{"type": "impasse", "ecran": x["id"], "texte": f"« {x['nom']} » n'a aucune sortie connue : y retourner et essayer ses actions."}
         for x in [x for x in n["impasses"] if dedans(x)][:5]]
    p += [{"type": "isole", "ecran": x["id"], "texte": f"« {x['nom']} » n'a aucune entrée connue : retrouver comment on y arrive."}
          for x in [x for x in n["isoles"] if dedans(x)][:5]]
    p += [{"type": "instable", "transition": t, "texte": f"Transition {t} instable : la rejouer pour confirmer."} for t in n["instables"][:5]]
    a_nommer = sum(1 for e in carte.ecrans() if not e.get("nom"))
    if a_nommer:
        p.append({"type": "nommer", "texte": f"{a_nommer} écran(s) à nommer (Discovery Validation)."})
    return p


def suggerer(elements: list[dict], ecran: dict | None, plateforme: str, ia: bool = True) -> dict:
    from atelier.intelligence import fournisseur_ia

    from atelier.discovery import sessions_discovery

    eid = (ecran or {}).get("id", "")
    perimetre = sessions_discovery.perimetre_actif()
    sorti = sessions_discovery.hors_perimetre(eid, perimetre)
    # hors du périmètre de la session : rien à essayer ici, on revient (les actions de cet écran restent « jamais essayées »)
    c = candidates(elements, eid, plateforme) if ecran and not sorti else {"candidates": [], "ecartees": {}}
    res = {"ecran": ecran, "suggestions": c["candidates"][:10], "ecartees": c["ecartees"], "pistes": pistes(perimetre),
           "ia": fournisseur_ia.etat(),
           "perimetre": {"noeud": perimetre["noeud"], "libelle": perimetre["libelle"], "dans_le_perimetre": not sorti} if perimetre else None}
    if not (ia and c["candidates"] and fournisseur_ia.configure()):
        return res
    from atelier.execution.echecs import masquer_texte

    connus = [e.get("nom") or e.get("titre") or e["id"] for e in carte.ecrans()][:80]
    demande = json.dumps({"ecran_courant": masquer_texte((ecran or {}).get("nom") or (ecran or {}).get("titre") or eid),
                          "ecrans_connus": [masquer_texte(x) for x in connus],
                          "candidates": [{"cle": x["cle"], "libelle": masquer_texte(x["libelle"]), "type": x["type"]}
                                         for x in c["candidates"][:40]]}, ensure_ascii=False)
    try:
        rep = fournisseur_ia.extraire_json(fournisseur_ia.completer(SYSTEME, demande, 800))
        par_cle = {x["cle"]: x for x in c["candidates"]}
        ordre = [(par_cle[r["cle"]], str(r.get("raison") or "")[:200]) for r in rep if isinstance(r, dict) and r.get("cle") in par_cle]
        if ordre:
            vues = {x["cle"] for x, _ in ordre}
            res["suggestions"] = [{**x, "raison": raison or x["raison"], "par_ia": True} for x, raison in ordre] + \
                                 [x for x in c["candidates"] if x["cle"] not in vues][:5]
        res["ia"] = {**res["ia"], "modele": fournisseur_ia.modele()}
    except Exception as e:  # noqa: BLE001 - l'IA est un plus : les suggestions explicables restent
        res["ia"] = {**res["ia"], "erreur": str(e)[:200]}
    return res


def suggerer_courant(ia: bool = True) -> dict:
    """Suggestions pour l'écran affiché sur le device / navigateur connecté (pistes globales seules sinon)."""
    from atelier.discovery import session
    from atelier.discovery.observation import carte_active, observer

    if not session.plateforme() or not carte_active():
        return {**suggerer([], None, "", ia=False), "device": False}
    els = session.current_elements(150)
    return {**suggerer(els, observer(els), session.etat["platform"], ia), "device": True}
