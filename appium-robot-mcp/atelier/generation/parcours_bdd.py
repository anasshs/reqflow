"""Du parcours découvert au test : brouillon de scénario BDD construit depuis la carte de l'application.

Sources d'un parcours (une seule à la fois) :
- une suite ordonnée d'écrans (ex. le chemin calculé dans Navigation Explorer) ;
- un nœud « parcours » du Knowledge Graph (proposé par Cursor / Claude ou déclaré), dont les écrans sont ordonnés
  par la navigation connue ;
- une session Discovery (écrans dans l'ordre où ils ont été parcourus).

Entre deux écrans consécutifs, les transitions viennent de la carte (chemin le plus fiable) : chaque action devient
une étape « Quand » reliée à son écran et à son locator connu, chaque arrivée une étape « Alors » ; les champs d'un
écran deviennent « Et je renseigne … avec le jeu de données » (aucune donnée littérale). Une action sensible ou
interdite sur le chemin est signalée et le scénario reçoit le tag action_sensible : elle ne sera exécutée que si le
scénario l'autorise explicitement (invariant 6).

Le brouillon arrive dans Test Design (bdd/<clé>.feature + .yaml), étapes non validées : la suite (revue, génération
Robot, exécutions stables, merge request, publication Xray) est la chaîne habituelle.
"""
from __future__ import annotations

from atelier.generation import bdd


def _lisible(e: dict) -> str:
    return (e.get("nom") or e.get("titre") or e["id"]).replace("_", " ")


def _ref(e: dict) -> str:
    return e.get("nom") or e["id"]


def ecrans_du_parcours(nid: str) -> list[str]:
    """Écrans reliés au nœud parcours (relation « contient »), ordonnés par la navigation de la carte."""
    from atelier.discovery import carte, connaissance

    g = connaissance.construire()
    if nid not in g.noeuds:
        raise KeyError(f"Parcours inconnu : {nid}")
    refs = [r.vers.split(":", 1)[1] for r in g.sortants(nid) if r.type == "contient" and r.vers.startswith("ecran:")]
    if not refs:
        raise ValueError(f"Le parcours {g.noeuds[nid].libelle} n'est relié à aucun écran.")
    ids = []
    for ref in refs:
        try:
            ids.append(carte.ecran(ref)["id"])
        except KeyError:
            continue
    return ordonner(ids)


def ordonner(ids: list[str], plateforme: str = "") -> list[str]:
    """Ordre de visite : départ = l'écran le plus proche de l'écran de départ de la carte, puis à chaque pas l'écran
    restant le plus proche par la navigation connue (non joignables placés à la fin)."""
    from atelier.discovery import carte

    if len(ids) < 2:
        return list(ids)
    plat = plateforme or (carte.config_app().get("plateformes") or ["web"])[0]
    depart = carte.graphe().get("depart")

    def dist(a, b):
        c = carte.chemin(a, b, plat) if a and a != b else []
        return len(c) if c is not None else 10 ** 6

    reste = list(dict.fromkeys(ids))
    courant = min(reste, key=lambda i: dist(depart, i)) if depart else reste[0]
    ordre = [courant]
    reste.remove(courant)
    while reste:
        suivant = min(reste, key=lambda i: dist(courant, i))
        ordre.append(suivant)
        reste.remove(suivant)
        courant = suivant
    return ordre


def ecrans_de_session(sid: str) -> list[str]:
    from atelier.discovery import sessions_discovery

    seq = []
    for e in sessions_discovery.timeline(sid, 2000):
        for x in ((e.get("de"), e.get("vers")) if e.get("type") == "transition" else (e.get("ecran"),)):
            if x and (not seq or seq[-1] != x):
                seq.append(x)
    if len(seq) < 2:
        raise ValueError(f"La session {sid} n'a pas parcouru au moins deux écrans.")
    return seq


def brouillon(ecrans: list[str] | None = None, parcours: str = "", session: str = "", titre: str = "",
              plateforme: str = "", cle: str = "") -> dict:
    """Crée le brouillon BDD dans Test Design et renvoie {cle, gherkin, etapes, locators, donnees, avertissements}."""
    from atelier.discovery import carte, classement

    if sum(bool(x) for x in (ecrans, parcours, session)) != 1:
        raise ValueError("Une seule source : écrans, parcours ou session.")
    source = f"parcours {parcours}" if parcours else f"session {session}" if session else "chemin de la carte"
    ids = ecrans_du_parcours(parcours) if parcours else ecrans_de_session(session) if session else [carte.ecran(x)["id"] for x in ecrans]
    if len(ids) < 2:
        raise ValueError("Un parcours relie au moins deux écrans.")
    plat = plateforme or (carte.config_app().get("plateformes") or ["web"])[0]
    seq = [carte.ecran(i) for i in ids]
    titre = (titre or f"Parcours {_lisible(seq[0])} vers {_lisible(seq[-1])}").strip()
    regles = classement.regles()
    etapes, avertissements, donnees, locators, sensible = [], [], [], {"connus": 0, "manquants": 0}, False
    etapes.append(bdd._etape("Étant donné", f"que je suis sur l'écran {_lisible(seq[0])}", ecran=_ref(seq[0])))
    renseignes = set()

    def champs(e):
        if e["id"] in renseignes:
            return
        renseignes.add(e["id"])
        for k, el in (e.get("elements") or {}).items():
            if el.get("type") == "champ":
                loc = ((el.get("locators") or {}).get(plat) or [""])[0]
                etapes.append(bdd._etape("Et", f"je renseigne {(el.get('libelle') or k).lower()} avec le jeu de données",
                                         ecran=_ref(e), locator=loc, jdd=k))
                donnees.append(k)

    for a, b in zip(seq, seq[1:]):
        if a["id"] == b["id"]:
            continue
        trajet = carte.chemin(a["id"], b["id"], plat)
        if trajet is None:
            avertissements.append(f"Aucun chemin connu de {_lisible(a)} vers {_lisible(b)} ({plat}) : à découvrir.")
            etapes.append(bdd._etape("Quand", f"je vais sur l'écran {_lisible(b)}", ecran=_ref(b)))
            etapes.append(bdd._etape("Alors", f"l'écran {_lisible(b)} est affiché", ecran=_ref(b)))
            continue
        for t in trajet:
            de, vers = carte.ecran(t["de"]), carte.ecran(t["vers"])
            act = t.get("action") or {}
            champs(de)
            if act.get("type") == "press_back":
                texte, loc = "je reviens en arrière", ""
            elif act.get("type") == "swipe":
                texte, loc = "je fais défiler l'écran", ""
            elif act.get("type") == "open_url":
                texte, loc = "j'ouvre l'adresse de l'application", ""
            else:
                el = (de.get("elements") or {}).get(act.get("cle") or "", {})
                lib = act.get("libelle") or el.get("libelle") or act.get("cle") or "l'élément"
                loc = ((el.get("locators") or {}).get(plat) or [act.get("locator") or ""])[0]
                c = classement.classer({"key": act.get("cle") or "", "libelle": lib, "type": el.get("type") or "bouton"}, r=regles)
                if c["classe"] in ("sensitive", "forbidden"):
                    sensible = True
                    avertissements.append(f"Action {classement.LIBELLES[c['classe']]} « {lib} » ({c['raison']}) : à autoriser explicitement "
                                          "dans le scénario, sur un environnement autorisé.")
                texte = f"je touche {lib.lower()}"
            locators["connus" if loc else "manquants"] += 1
            etapes.append(bdd._etape("Quand", texte, ecran=_ref(de), locator=loc))
            etapes.append(bdd._etape("Alors", f"l'écran {_lisible(vers)} est affiché", ecran=_ref(vers)))
    tags = ["discovery"] + (["action_sensible"] if sensible else [])
    m = {"langue": "fr", "feature": titre, "description": [f"Brouillon généré depuis la Discovery ({source}) : à relire et valider."],
         "contexte": [], "tags": [], "source": f"discovery ({source})", "titre": titre, "jdd": "", "statut": "brouillon",
         "scenarios": [{"id": bdd._id(), "nom": titre, "type": "principal", "tags": tags, "depuis": "", "etapes": etapes}]}
    base = bdd._slug(cle or f"parcours_{titre}")
    cle, n = base, 2
    while bdd.charger(cle):
        cle, n = f"{base}_{n}", n + 1
    m["cle"] = cle
    m = bdd.sauver(m, auteur="discovery")
    return {"cle": cle, "titre": titre, "gherkin": bdd.serialiser(m), "etapes": len(etapes), "ecrans": [_ref(e) for e in seq],
            "locators": locators, "donnees": donnees, "avertissements": avertissements, "controles": bdd.controles(m)}
