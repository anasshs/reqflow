"""« Que faire ici ? » : quelques suggestions de tests sur un écran, un module ou un parcours, au clic dans le graphe.

Une version simple du MBT : rien à modéliser, tout se lit dans le Knowledge Graph et la carte.
  - Concevoir  : un chemin observé vers un écran sans test ; un retour arrière observé ; une saisie invalide sur un
                 formulaire (le résultat attendu est alors une hypothèse, dite comme telle).
  - Dérouler   : un élément sûr de l'écran jamais essayé (Discovery).
  - Automatiser: un scénario BDD de l'écran sans script.
  - Stabiliser : un test qui passe par l'écran et dont le dernier run a échoué.
Chaque suggestion dit pourquoi (preuve), si son résultat attendu est observé ou une hypothèse, et ce que « Lancer » fait :
le brouillon BDD quand il se déduit de la carte, puis une demande à l'agent (Claude Code, Cursor) qui conçoit ou
complète le BDD, l'automatise en réutilisant le socle, le vérifie et l'exécute, et en rend compte.

Les écrans en double (même titre, même structure) sont regroupés : une suggestion n'est jamais répétée pour chacun.

Actions sensibles (payer, valider, effectuer un virement…) : suggérées seulement sur un environnement où l'application les
autorise (Discovery › réglages de classement : classes par environnement, décision humaine journalisée), et marquées
« sensible » ; l'agent les exécute alors avec des données de test appartenant à l'équipe et tague le test consomme_donnee.
"""
from __future__ import annotations

import re

MAX = 5
TECHNIQUE = re.compile(r"^[a-z0-9_]+$")
BOUTON_VALIDATION = re.compile(r"(?i)valider|continuer|confirmer|connecter|envoyer|suivant|enregistrer|rechercher|appliquer")
SENSIBLE = re.compile(r"(?i)\b(payer|valider|confirmer|supprimer|otp|activer|autoriser|signer|souscrire)\b")  # verbes d.engagement, pas un lien de navigation
GENERIQUE = re.compile(r"(?i)^(ok|annuler|fermer|retour|non|oui|plus tard)$")  # boutons de fermeture : rien à découvrir derrière


def _lisible(lib: str) -> bool:
    return bool(lib) and not (TECHNIQUE.match(lib) and "_" in lib) and lib.lower() not in ("content", "retour")


def _contexte():
    from atelier.discovery import carte, connaissance
    from atelier.intelligence import couverture_avancee as ca

    g = connaissance.construire()
    c = ca.carte(g)
    par_carte = {}  # id de carte -> nœud du graphe
    for i, n in g.noeuds.items():
        if n.type == "ecran" and n.proprietes.get("id_carte"):
            par_carte[n.proprietes["id_carte"]] = i
    return g, c, {e["id"]: e for e in c["ecrans"]}, par_carte, carte


def _scenarios_de(g, eid: str) -> list[dict]:
    out = []
    for r in g.entrants(eid):
        if r.type == "couvre" and r.de.startswith("scenario:"):
            n = g.noeuds[r.de]
            out.append({"cle": r.de.split(":", 1)[1], "titre": n.libelle,
                        "automatise": any(x.type == "implemente_par" for x in g.sortants(r.de)), "statut": n.proprietes.get("statut_bdd", "")})
    return out


def _a_explorer() -> dict:
    """Éléments sûrs jamais essayés, par écran de la carte (calcul coûteux : une fois par demande, gardé une minute)."""
    import time

    from atelier.discovery import reste

    from atelier.discovery import carte
    from atelier.domain import projet

    cle = (str(projet.PROJECT_DIR), carte.app_courante())
    if _MEMO.get("cle") == cle and _MEMO.get("t", 0) > time.time() - 60:
        return _MEMO["v"]
    try:
        v = {x["id"]: x for x in reste.a_explorer()["ecrans"]}
    except Exception:  # noqa: BLE001
        v = {}
    _MEMO.update(t=time.time(), v=v, cle=cle)
    return v


_MEMO: dict = {}


def _retour_verifie(g, eid: str, id_carte: str) -> bool:
    """Un scénario BDD de l'écran fait-il déjà un retour arrière depuis lui ?"""
    from atelier.generation import bdd

    for s in _scenarios_de(g, eid):
        m = bdd.charger(s["cle"]) or {}
        for sc in m.get("scenarios", []):
            if any("arrière" in e.get("texte", "") and e.get("ecran") in (id_carte, eid.split(":", 1)[1]) for e in sc.get("etapes", [])):
                return True
    return False


def sensibles_autorises(env: str) -> bool:
    """L'application autorise-t-elle les actions sensibles sur cet environnement (réglage de classement) ?"""
    from atelier.discovery import classement

    return bool(env) and "sensitive" in classement.regles()["environnements"].get(env.strip().lower(), [])


def _pour_ecran(eid: str, g, c, ecrans, par_carte, carte, sens_ok: bool = False) -> list[dict]:
    e = ecrans.get(eid)
    n = g.noeuds.get(eid)
    if not e or not n:
        return []
    id_carte = n.proprietes.get("id_carte", "")
    try:
        ec = carte.ecran(id_carte) if id_carte else {}
    except KeyError:
        ec = {}
    nom = e["nom"]
    out = []
    from atelier.discovery.parcours_utilisateur import ecran_transitoire

    if ec and ecran_transitoire(ec):  # fenêtre système, chargement, erreur : rien à y concevoir ni à explorer
        return []
    # mots du titre (« Hello iOS ! ») : un élément qui les reprend est le nom du client affiché, jamais une suggestion
    mots_titre = {m.lower() for m in re.findall(r"\w{3,}", ec.get("titre") or "")}
    cibles_vues = set()
    # concevoir : chemins observés vers un écran sans test
    for t in carte.transitions():
        if t["de"] != id_carte or t.get("interdite"):
            continue
        cible = par_carte.get(t["vers"])
        ce = ecrans.get(cible or "")
        act = t.get("action") or {}
        if act.get("type") == "press_back":
            if e["etat"] != "non_couvert" and ce and not _retour_verifie(g, eid, id_carte):
                out.append({"famille": "concevoir", "titre": f"Retour arrière depuis « {nom} »", "cible": cible,
                            "pourquoi": f"Le retour vers « {ce['nom']} » a été observé ; aucun test ne le vérifie.",
                            "oracle": "observé", "attendu": f"l'écran « {ce['nom']} » est affiché", "valeur": 2,
                            "lancer": {"type": "chemin", "ecrans": [id_carte, t["vers"]], "titre": f"Retour arrière depuis {nom}"}})
            continue
        lib = act.get("libelle") or ""
        sensible = bool(SENSIBLE.search(lib))
        if ce and ce["etat"] == "non_couvert" and _lisible(lib) and (sens_ok or not sensible) and cible not in cibles_vues \
                and not re.search(r"(?i)fermer|annuler", lib):
            cibles_vues.add(cible)
            out.append({"famille": "concevoir", "titre": f"Aller à « {ce['nom']} » par « {lib} »", "cible": cible,
                        "pourquoi": f"Navigation observée vers un écran qu'aucun test ne couvre ({ce['module'] or 'sans module'}).",
                        "oracle": "observé", "attendu": f"l'écran « {ce['nom']} » est affiché", "valeur": 4,
                        "lancer": {"type": "chemin", "ecrans": [id_carte, t["vers"]], "titre": f"{nom} vers {ce['nom']}"}})
    # concevoir : saisie invalide sur un formulaire (hypothèse : le résultat attendu n'a jamais été observé)
    elements = ec.get("elements") or {}
    champs = [el.get("libelle") or k for k, el in elements.items() if el.get("type") == "champ"]
    boutons = [el.get("libelle") for el in elements.values() if el.get("libelle") and BOUTON_VALIDATION.search(el.get("libelle"))]
    if champs and boutons:
        out.append({"famille": "concevoir", "titre": f"Saisie invalide dans « {nom} »",
                    "pourquoi": f"Formulaire ({', '.join(dict.fromkeys(champs))[:80]}) validé par « {boutons[0]} » : valeur au mauvais format, trop courte ou vide.",
                    "oracle": "hypothèse", "attendu": f"« {boutons[0]} » reste inactif, ou un message d'erreur s'affiche (à confirmer au premier run)",
                    "valeur": 3, "lancer": {"type": "agent", "consigne": "variante_invalide"}})
    if champs and boutons and sens_ok and SENSIBLE.search(boutons[0]):
        out.append({"famille": "derouler", "titre": f"Aller au bout : « {boutons[0]} » dans « {nom} »",
                    "pourquoi": f"Actions sensibles autorisées sur cet environnement : le formulaire n'a jamais été soumis, l'écran qui suit est inconnu.",
                    "oracle": "à découvrir", "attendu": "l'écran qui suit la soumission est découvert puis vérifié", "valeur": 3,
                    "lancer": {"type": "agent", "consigne": "aller_au_bout", "bouton": boutons[0]}})
    # dérouler : éléments sûrs jamais essayés
    ligne = _a_explorer().get(id_carte)
    essais = [x["libelle"] for x in (ligne or {}).get("a_essayer_exemples", []) if _lisible(x.get("libelle", ""))
              and not GENERIQUE.match(x["libelle"].strip()) and not re.search(r"_item_|_list", x.get("cle", ""))  # pas une ligne de liste
              and (sens_ok or not SENSIBLE.search(x["libelle"]))
              and not ({m.lower() for m in re.findall(r"\w{3,}", x["libelle"])} & mots_titre)]
    if essais:
        out.append({"famille": "derouler", "titre": f"Explorer « {essais[0]} »" + (f" (+{len(essais) - 1})" if len(essais) > 1 else ""),
                    "pourquoi": f"Élément(s) sûr(s) de « {nom} » jamais touché(s) : {', '.join(essais[:4])}.",
                    "oracle": "à découvrir", "attendu": "l'écran atteint est ajouté à la carte", "valeur": 2,
                    "lancer": {"type": "agent", "consigne": "derouler", "elements": essais[:4]}})
    # automatiser : scénarios BDD de l'écran sans script
    for s in _scenarios_de(g, eid):
        if not s["automatise"] and s["statut"] in ("valide", "validé"):  # un brouillon n'est pas une décision d'automatiser
            out.append({"famille": "automatiser", "titre": f"Automatiser « {s['titre'][:60]} »",
                        "pourquoi": f"Scénario BDD {s['cle']} ({s['statut'] or 'brouillon'}) qui passe par « {nom} », sans script Robot.",
                        "oracle": "observé", "attendu": "le scénario passe en recette", "valeur": 5,
                        "lancer": {"type": "bdd", "cle": s["cle"]}})
    # stabiliser : test en échec qui passe par l'écran
    if e["etat"] == "echec":
        echecs = [t for t in c["tests"] if t["id"] in e["tests"] and t["statut"] == "FAIL"]
        for t in echecs[:1]:
            out.append({"famille": "stabiliser", "titre": f"Comprendre l'échec de {t['cle_xray'] or t['nom'][:40]}",
                        "pourquoi": f"« {t['nom']} » passe par « {nom} » et son dernier run a échoué.",
                        "oracle": "observé", "attendu": "cause qualifiée (défaut, environnement, script) et test corrigé si besoin",
                        "valeur": 4, "lancer": {"type": "agent", "consigne": "stabiliser", "test": t["nom"]}})
    for x in out:
        x.setdefault("ecran", eid)
        x["ecran_nom"] = nom
        x["sensible"] = bool(SENSIBLE.search(x["titre"]) or x["lancer"].get("consigne") == "aller_au_bout")
    return out


def _cle(s: dict) -> tuple:
    rang_famille = {"automatiser": 0, "concevoir": 1, "stabiliser": 2, "derouler": 3}
    return (s["oracle"] != "observé", -s["valeur"], rang_famille.get(s["famille"], 9))


def suggestions(noeud: str, env: str = "") -> dict:
    """Au plus MAX suggestions pour un écran, un module ou un parcours, les plus utiles d'abord (résultat attendu
    observé avant hypothèse, écran sans test d'abord)."""
    g, c, ecrans, par_carte, carte = _contexte()
    sens_ok = sensibles_autorises(env)
    n = g.noeuds.get(noeud)
    if not n or n.type not in ("ecran", "module", "parcours"):
        raise ValueError("Choisir un écran, un module ou un parcours.")
    if n.type == "ecran":
        cibles = [noeud]
    else:
        cibles = [r.vers for r in g.sortants(noeud) if r.type == "contient" and r.vers in ecrans]
    out, vus = [], set()
    for e in cibles:
        for s in _pour_ecran(e, g, c, ecrans, par_carte, carte, sens_ok):
            cle = (s["famille"], s["titre"].replace(s["ecran_nom"], "∗"), s.get("cible", ""))  # écrans en double : une seule fois
            if cle in vus:
                continue
            vus.add(cle)
            out.append(s)
    if n.type == "parcours":
        ct = n.proprietes.get("couverture_tests") or {}
        if ct.get("etat") != "couvert" and not any(_scenarios_de(g, e) for e in cibles):
            out.append({"famille": "concevoir", "titre": f"Du parcours « {n.libelle} » au test", "ecran": "", "ecran_nom": "",
                        "pourquoi": f"{ct.get('etapes_couvertes', 0)}/{ct.get('etapes', len(cibles))} écran(s) couvert(s) ; aucun scénario BDD.",
                        "oracle": "observé", "attendu": "le parcours déroulé est vérifié de bout en bout", "valeur": 6,
                        "lancer": {"type": "parcours", "parcours": noeud, "titre": n.libelle}})
    out.sort(key=_cle)
    for i, s in enumerate(out):
        s["id"] = f"S{i + 1}"
    return {"noeud": noeud, "type": n.type, "libelle": n.libelle, "suggestions": out[:MAX], "autres": max(0, len(out) - MAX),
            "ecrans": cibles, "environnement": env, "sensibles_autorises": sens_ok}


# --------------------------------------------------------------------------- lancer : BDD -> automatisation -> exécution
CONSIGNES = {
    "variante_invalide": "Conçois une variante négative : sur l'écran « {ecran} », saisir une valeur invalide (mauvais format, trop "
                         "courte, vide) puis vérifier le comportement. Le résultat attendu est une hypothèse ({attendu}) : "
                         "observe-le au premier run et écris l'assertion d'après ce que l'application fait réellement.",
    "derouler": "Déroule une Discovery courte sur l'écran « {ecran} » en touchant {elements} (éléments sûrs uniquement), "
                "propose les écrans atteints, puis crée le scénario BDD du chemin observé.",
    "stabiliser": "Analyse l'échec du test « {test} » (dernier run) : qualifie la cause (défaut applicatif, environnement, "
                  "script ou locator), corrige le script seulement si c'est lui.",
    "aller_au_bout": "Sur l'écran « {ecran} », remplis le formulaire avec les données de test de l'équipe puis touche « {bouton} » "
                     "(action réelle, autorisée sur cet environnement) ; découvre et nomme l'écran qui suit, puis crée le "
                     "scénario BDD du chemin complet avec l'assertion de ce que l'application affiche.",
}
SUITE = ("Ensuite, sans attendre d'autre instruction : 1) le scénario BDD (Test Design) avec le jeu de données des tests, "
         "données fictives uniquement ; 2) l'automatisation en Page Object Model en réutilisant le socle (keywords et "
         "locators existants), sans doublon ; 3) un dry-run puis un run réel du seul nouveau test (run_tests) ; "
         "4) atelier_demande_terminee avec le résultat (clé BDD, fichier, statut du run). Règles : jamais d'action "
         "sensible (paiement, virement, validation définitive, OTP), arrêt avant ; jamais de secret écrit ; "
         "aucune publication Xray sans décision de l'automaticien.")


REGLES_SENSIBLES = ("Règles : actions sensibles AUTORISÉES sur l'environnement {env} (décision de l'automaticien, journalisée) : "
                    "les exécuter avec des données de test appartenant à l'équipe (numéro, e-mail, compte de recette ; jamais "
                    "un numéro inventé qui pourrait être celui de quelqu'un), taguer le test consomme_donnee ; jamais de secret "
                    "écrit ; aucune publication Xray sans décision de l'automaticien.")


SUITE_TRAVAIL = ("Ensuite, sans attendre d'autre instruction : 1) le scénario BDD (Test Design) avec le jeu de données des "
                 "tests, données fictives uniquement ; 2) l'automatisation en Page Object Model en réutilisant le socle (keywords "
                 "et locators existants), sans doublon, le test portant en [Tags] la clé du scénario BDD et « {travail} » ; "
                 "3) un dry-run si tu veux, mais PAS le run réel : l'atelier l'enchaîne lui-même sur un téléphone libre ; "
                 "4) atelier_demande_terminee avec la clé BDD, le fichier et le nom du test. ")
REGLES = ("Règles : jamais d'action sensible (paiement, virement, validation définitive, OTP), arrêt avant ; jamais de secret "
          "écrit ; aucune publication Xray sans décision de l'automaticien.")


def lancer(noeud: str, suggestion: str, env: str = "") -> dict:
    """Lance une suggestion choisie : un travail de l'orchestrateur, qui avance seul en arrière-plan.
    Étapes : brouillon BDD (atelier, si la carte le permet) → conception et automatisation (agent du projet) → dry-run et
    run réel (atelier, sur un téléphone libre) → validation du BDD et revue du script (automaticien). Rend {travail}."""
    from atelier.execution import orchestrateur
    from atelier.integrations import boite_cursor

    s = next((x for x in suggestions(noeud, env)["suggestions"] if x["id"] == suggestion), None)
    if not s:
        raise KeyError("Suggestion inconnue (la liste a peut-être changé : rouvrir le panneau).")
    l = s["lancer"]
    etapes = []
    if l["type"] in ("chemin", "parcours"):
        etapes.append({"titre": "Brouillon BDD", "type": "atelier", "action": "brouillon_bdd",
                       "params": {"ecrans": l.get("ecrans"), "parcours": l.get("parcours"), "titre": l["titre"]}})
        objet = (f"Le scénario BDD « {{bdd}} » ({s['titre']}) est prêt dans Test Design. Relis-le, complète les données et les "
                 f"assertions (résultat attendu : {s['attendu']}).")
    elif l["type"] == "bdd":
        objet = f"Le scénario BDD « {l['cle']} » ({s['titre']}) est validé, sans script : automatise-le."
    else:
        objet = CONSIGNES[l["consigne"]].format(ecran=s["ecran_nom"], attendu=s["attendu"], elements=", ".join(f"« {x} »" for x in l.get("elements", [])),
                                                test=l.get("test", ""), bouton=l.get("bouton", ""))
    regles = REGLES_SENSIBLES.format(env=env) if s.get("sensible") and sensibles_autorises(env) else REGLES
    stabiliser = l.get("consigne") == "stabiliser"
    texte = f"{objet}\nPourquoi : {s['pourquoi']}\n" + ("" if stabiliser else SUITE_TRAVAIL) + regles
    agent = boite_cursor.agent()  # agent du projet (Claude Code ou Cursor), réglé dans Paramètres › Cursor / Claude
    etapes.append({"titre": "Analyser et corriger" if stabiliser else "Concevoir et automatiser", "type": "ia", "agent": agent,
                   "params": {"texte": texte, "attendus": ["atelier_demande_terminee"]}})
    if not stabiliser:
        etapes += [{"titre": "Dry-run", "type": "atelier", "action": "dry_run", "params": {"bdd": l.get("cle", "")}},
                   {"titre": "Run réel", "type": "atelier", "action": "run", "params": {"bdd": l.get("cle", "")}}]
    etapes.append({"titre": "Valider le BDD et approuver le script", "type": "humain"})
    tr = orchestrateur.creer(s["titre"], etapes, origine={"type": "suggestion", "noeud": noeud, "ecran": s.get("ecran", ""),
                                                          "suggestion": s["titre"], "famille": s["famille"]}, env=env)
    return {"suggestion": s, "travail": {k: tr[k] for k in ("id", "titre", "statut")}, "etapes": [e["titre"] for e in tr["etapes"]]}
