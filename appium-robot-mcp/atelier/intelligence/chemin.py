"""Le chemin de l'utilisateur dans l'atelier : Découvrir → Concevoir le test → Automatiser → Exécuter.

Lecture seule : l'état de chaque étape et la PROCHAINE action utile se déduisent des objets existants (parcours
utilisateur de Discovery, scénarios BDD, suites Robot du dépôt et leur revue, derniers résultats). Rien n'est saisi ici.
Sert l'Accueil (bandeau « Ton chemin ») et le repère d'étape affiché en haut des écrans du chemin.

La prochaine action suit le test le plus avancé d'abord : finir un test de bout en bout avant d'en commencer un autre.
Jira et Xray ne sont jamais requis ; « integrations » dit s'ils sont utilisés (configurés, ou des données en ont été
importées), pour que l'interface ne propose leurs options que dans ce cas.
"""
from __future__ import annotations

import os

ETAPES = [("decouvrir", "Découvrir", "#discovery/cadrage"), ("concevoir", "Concevoir le test", "#bdd"),
          ("automatiser", "Automatiser", "#studio/direct"), ("executer", "Exécuter", "#centre/lancer")]
MARQUE_A_IMPLEMENTER = "Keyword à implémenter"


def integrations() -> dict:
    """Xray / Jira utilisés : configurés (variables d'environnement) ou des données en ont été importées."""
    xc, jc = bool(os.environ.get("XRAY_CLIENT_ID")), bool(os.environ.get("JIRA_BASE_URL"))
    tests = exigences = 0
    try:
        from atelier.intelligence import patrimoine_xray

        pat = patrimoine_xray.charger_vue() or {}
        tests, exigences = len(pat.get("tests") or []), len(pat.get("exigences") or [])
    except Exception:  # noqa: BLE001 — patrimoine illisible : seules les variables comptent
        pass
    return {"xray": xc or tests > 0, "jira": jc or exigences > 0, "xray_configure": xc, "jira_configure": jc}


def _parcours() -> list[dict]:
    try:
        from atelier.discovery import carte, parcours_utilisateur as pu

        app = carte.app_courante()
        if not app:
            return []
        out = []
        for p in pu._tous(app):
            if p.get("archive"):
                continue
            out.append({"id": p["id"], "nom": p.get("nom") or p["id"], "noeud": p.get("noeud", ""), "sessions": list(p.get("sessions", [])),
                        "ecrans": len(p.get("ecrans", [])), "valide": bool(p.get("valide")), "statut": pu.statut(p), "modifie": p.get("modifie", "")})
        return sorted(out, key=lambda x: x["modifie"], reverse=True)
    except Exception:  # noqa: BLE001 — pas d'application, carte illisible : aucun parcours
        return []


def _scripts(bdds: list[dict]) -> dict:
    """Pour chaque scénario BDD : la suite du dépôt qui porte sa clé en tag, son statut de revue, s'il reste des
    keywords à implémenter et son dernier résultat."""
    from atelier.domain import projet
    from atelier.execution import depot_robot

    try:
        inv = depot_robot.lire_depot()
    except Exception:  # noqa: BLE001
        return {}
    try:
        from atelier.generation import studio

        revues = studio.revues_scripts()
    except Exception:  # noqa: BLE001
        revues = {}
    try:
        from atelier.execution.robot import derniers_resultats

        res = derniers_resultats()
    except Exception:  # noqa: BLE001
        res = {}
    cles = {b["cle"] for b in bdds} | {b.get("cle_xray") for b in bdds if b.get("cle_xray")}
    out = {}
    for f, s in inv.get("suites", {}).items():
        for t in s.get("tests", []):
            tags = set((inv.get("tests", {}).get(t) or {}).get("tags") or [])
            for c in cles & tags:
                if c in out:
                    continue
                a_faire = False
                for fichier in [f, *((inv.get("fichiers", {}).get(f) or {}).get("resources") or [])]:  # suite + pages (POM)
                    try:
                        a_faire = a_faire or MARQUE_A_IMPLEMENTER in projet.safe_path(fichier).read_text("utf-8")
                    except (OSError, ValueError):
                        continue
                out[c] = {"fichier": f, "test": t, "revue": (revues.get(f) or {}).get("statut", "Generated"),
                          "a_implementer": a_faire, "resultat": (res.get(t) or {}).get("statut")}
    return out


def _bdds() -> list[dict]:
    from atelier.generation import bdd

    out = []
    for b in bdd.lister():
        m = bdd.charger(b["cle"]) or {}
        out.append({**b, "parcours": m.get("parcours", ""), "session": m.get("session", ""), "cle_xray": m.get("cle_xray", ""),
                    "sans_jdd": bool(not m.get("jdd") and bdd.etapes_avec_donnees(m)),
                    "discovery": str(m.get("source", "")).startswith("discovery")})
    return sorted(out, key=lambda x: x.get("maj") or "", reverse=True)


def etat() -> dict:
    """Les 4 étapes avec leurs compteurs, l'étape courante et la prochaine action (texte, bouton, lien)."""
    integ = integrations()
    try:
        from atelier.discovery import carte

        app = carte.app_courante()
        nb_ecrans = len(carte.ecrans()) if app else 0
    except Exception:  # noqa: BLE001
        app, nb_ecrans = "", 0
    parcours, bdds = _parcours(), _bdds()
    scripts = _scripts(bdds)
    sc = lambda b: scripts.get(b["cle"]) or scripts.get(b.get("cle_xray") or "")  # noqa: E731
    avec_script = [b for b in bdds if sc(b)]
    executes = [b for b in avec_script if sc(b)["resultat"]]
    reussis = [b for b in executes if sc(b)["resultat"] == "PASS"]
    en_revue = [b for b in avec_script if sc(b)["revue"] not in ("Approved", "Published")]
    a_construire = [b for b in avec_script if sc(b)["a_implementer"]]
    brouillons = [b for b in bdds if b["statut"] != "validé"]

    etapes = [
        {"id": "decouvrir", "num": 1, "titre": "Découvrir", "lien": "#discovery/cadrage", "fait": bool(parcours or nb_ecrans),
         "detail": f"{len(parcours)} parcours · {nb_ecrans} écran(s)"},
        {"id": "concevoir", "num": 2, "titre": "Concevoir le test", "lien": "#bdd", "fait": bool(bdds),
         "detail": f"{len(bdds)} test(s) BDD" + (f" · {len(brouillons)} à valider" if brouillons else "")},
        {"id": "automatiser", "num": 3, "titre": "Automatiser", "lien": "#studio/direct", "fait": bool(avec_script),
         "detail": f"{len(avec_script)} script(s)" + (f" · {len(a_construire)} à construire" if a_construire else "")
                   + (f" · {len(en_revue)} en revue" if en_revue else "")},
        {"id": "executer", "num": 4, "titre": "Exécuter", "lien": "#centre/lancer", "fait": bool(executes),
         "detail": f"{len(executes)} exécuté(s) · {len(reussis)} réussi(s)"},
    ]

    def action(etape, texte, bouton, lien):
        return {"etape": etape, "texte": texte, "bouton": bouton, "lien": lien}

    suivante = None
    # le plus avancé d'abord : un test commencé est mené au bout
    for b in avec_script:
        s = sc(b)
        if s["a_implementer"]:
            suivante = action("automatiser", f"« {b['titre']} » : le script a des keywords à implémenter. Cursor les écrit en réutilisant le socle.",
                              "Construire avec Cursor", f"#studio/direct/{b['cle']}")
        elif s["revue"] not in ("Approved", "Published"):
            suivante = action("automatiser", f"« {b['titre']} » : relire le script, l'exécuter 3 fois de suite sans échec, puis l'approuver.",
                              "Relire le script", "#studio/revue")
        elif not s["resultat"]:
            suivante = action("executer", f"« {b['titre']} » est prêt : le lancer.", "Exécuter", "#centre/lancer")
        if suivante:
            break
    if not suivante:
        for b in bdds:
            if sc(b):
                continue
            if b.get("sans_jdd"):  # sinon le script échoue au run : « Variable '${JDD}' not found »
                suivante = action("concevoir", f"« {b['titre']} » utilise des données : lui associer un jeu de données (identifiants…).",
                                  "Associer un jeu de données", f"#bdd/{b['cle']}")
            elif b["statut"] != "validé":
                suivante = action("concevoir", f"« {b['titre']} » : relire les étapes du test BDD, puis le valider.", "Relire le test BDD", f"#bdd/{b['cle']}")
            else:
                suivante = action("concevoir", f"« {b['titre']} » est validé : générer son script Robot.", "Générer le script Robot", f"#bdd/{b['cle']}")
            break
    if not suivante:
        for p in parcours:
            a_un_test = any(b["parcours"] and b["parcours"] == p["noeud"] or b["session"] in p["sessions"] for b in bdds)
            if a_un_test:
                continue
            if p["ecrans"] and not p["valide"]:
                suivante = action("decouvrir", f"Parcours « {p['nom']} » exploré : garder ou retirer les écrans traversés.",
                                  "Valider les écrans", f"#discovery/cadrage/{p['id']}")
            elif p["ecrans"]:
                suivante = action("concevoir", f"Parcours « {p['nom']} » validé : créer son test BDD (écrit par l'atelier).",
                                  "Créer le test BDD", f"#discovery/cadrage/{p['id']}")
            else:
                suivante = action("decouvrir", f"Parcours « {p['nom']} » préparé : le dérouler pour enregistrer ses écrans.",
                                  "Dérouler le parcours", f"#discovery/cadrage/{p['id']}")
            break
    if not suivante:
        if not app:
            suivante = action("decouvrir", "Déclarer l'application à tester (web ou mobile).", "Déclarer l'application", "#parametres/applications")
        elif bdds or parcours:
            suivante = action("decouvrir", "Tout est à jour. Découvrir un autre parcours de l'application.", "Découvrir un parcours", "#discovery/cadrage/nouveau")
        else:
            suivante = action("decouvrir", "Commencer par un parcours : le nommer, puis naviguer dans l'application ; l'atelier enregistre les écrans.",
                              "Découvrir un parcours", "#discovery/cadrage/nouveau")
    courante = suivante["etape"]
    for e in etapes:
        e["courante"] = e["id"] == courante
    return {"etapes": etapes, "suivante": suivante, "integrations": integ}
