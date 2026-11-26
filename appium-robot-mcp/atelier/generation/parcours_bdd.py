"""Du parcours découvert au test : brouillon de scénario BDD construit depuis la carte de l'application.

Sources d'un parcours (une seule à la fois) :
- une suite ordonnée d'écrans (ex. le chemin calculé dans Navigation Explorer) ;
- un nœud « parcours » du Knowledge Graph (proposé par Cursor / Claude ou déclaré), dont les écrans sont ordonnés
  par la navigation connue ;
- une session Discovery : les ACTIONS réellement faites, dans l'ordre (toucher, saisir, revenir, défiler), et l'écran
  d'arrivée vérifié après chaque changement d'écran ; seuls les champs réellement saisis deviennent des étapes de données
  (etapes_de_session). Sans action enregistrée, comme pour les autres sources : le chemin de la carte entre les écrans.

Entre deux écrans consécutifs, les transitions viennent de la carte (chemin le plus fiable) : chaque action devient
une étape « Quand » reliée à son écran et à son locator connu, chaque arrivée une étape « Alors » ; les champs d'un
écran deviennent « Et je renseigne … avec le jeu de données » (aucune donnée littérale) ; quand une variable du référentiel
de données Discovery a servi pour ce champ pendant l'exploration, l'étape la cite (« avec la donnée Adresse e-mail ») et
la garde (variable). Une action sensible ou
interdite sur le chemin est signalée et le scénario reçoit le tag action_sensible : elle ne sera exécutée que si le
scénario l'autorise explicitement (invariant 6).

Le brouillon arrive dans Test Design (bdd/<clé>.feature + .yaml), étapes non validées : la suite (revue, génération
Robot, exécutions stables, merge request, publication Xray) est la chaîne habituelle.
"""
from __future__ import annotations

import json
import re

from atelier.generation import bdd
from atelier.generation.etapes_sms import TEXTES as ETAPES_SMS


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


def etapes_parcours(nid: str, plateforme: str = "") -> dict:
    """Parcours ordonné pour l'affichage : écrans dans l'ordre et actions entre eux (chemin le plus fiable)."""
    from atelier.discovery import carte

    ids = ecrans_du_parcours(nid)
    plat = plateforme or (carte.config_app().get("plateformes") or ["web"])[0]
    seq = [carte.ecran(i) for i in ids]
    etapes = [{"ecran": _ref(seq[0]), "libelle": _lisible(seq[0]), "action": ""}]
    for a, b in zip(seq, seq[1:]):
        trajet = carte.chemin(a["id"], b["id"], plat)
        if trajet is None:
            etapes.append({"ecran": _ref(b), "libelle": _lisible(b), "action": "", "inconnu": True})
            continue
        for t in trajet:
            act = t.get("action") or {}
            v = carte.ecran(t["vers"])
            etapes.append({"ecran": _ref(v), "libelle": _lisible(v), "action": act.get("libelle") or act.get("cle") or act.get("type", "")})
    return {"parcours": nid, "etapes": etapes}


def m_jdd_connu(nom: str) -> bool:
    """Un jeu de données de ce nom existe-t-il dans au moins un environnement (data/jdd) ?"""
    from atelier.execution import jdd

    try:
        return any(nom.upper() == j["jeu"] for e in jdd.environnements() for j in jdd.lister(e))
    except Exception:  # noqa: BLE001
        return False


def cadrage_source(parcours: str = "", session: str = "") -> dict:
    """Cadrage du parcours utilisateur d'où vient le brouillon (nœud « parcours:… », ou session rattachée à un parcours) ;
    {} si aucun. Sert à reprendre l'objectif, le point de départ et le résultat attendu saisis par l'automaticien."""
    from atelier.discovery import parcours_utilisateur as pu

    try:
        if session and not parcours:
            from atelier.discovery import sessions_discovery

            pid = (sessions_discovery._lire(session).get("config") or {}).get("parcours", "")
            return pu._lire(pid) if pid else {}
        for p in pu._tous():
            if parcours and p.get("noeud") == parcours:
                return p
    except (KeyError, ValueError, OSError):
        pass
    return {}


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


def _evenements_session(sid: str) -> list[dict]:
    """Journal de la session sans doublons (deux façades peuvent écrire le même événement), dans l'ordre : à horodatage
    égal, l'action avant la transition qu'elle a provoquée."""
    from atelier.discovery import sessions_discovery

    vus, out = set(), []
    for i, e in enumerate(sessions_discovery.timeline(sid, 5000)):
        k = (e.get("date"), e.get("type"), e.get("detail"), e.get("de"), e.get("vers"), e.get("ecran"))
        if k not in vus:
            vus.add(k)
            out.append((e.get("date") or "", 0 if e.get("type") == "action" else 1, i, e))
    return [x[3] for x in sorted(out, key=lambda x: x[:3])]


def _element(ecran_id: str, locator: str, plateforme: str) -> tuple[str, dict]:
    """(clé, élément) de l'écran que vise le locator : locator identique, sinon même identité (resource-id,
    accessibility id) — « //*[@resource-id="x"]//EditText » vise le conteneur « x ». (« », {}) si aucun."""
    from atelier.discovery import carte
    from atelier.discovery.connaissance import identifiant_locator

    try:
        elements = carte.ecran(ecran_id).get("elements") or {}
    except (KeyError, ValueError, RuntimeError):
        return "", {}
    for k, x in elements.items():
        if locator in ((x.get("locators") or {}).get(plateforme) or []):
            return k, x
    ident = identifiant_locator(locator)
    if ident:
        for k, x in elements.items():
            if any(identifiant_locator(l) == ident for l in ((x.get("locators") or {}).get(plateforme) or [])):
                return k, x
    return "", {}


def _remettre_actions_en_ordre(evts: list[dict], plateforme: str) -> list[dict]:
    """Un agent (MCP) journalise son action APRÈS l'écran qu'elle a ouvert (écran puis transition, puis l'action). Une
    action dont l'élément est sur l'écran de départ de la transition qui la précède est remise avant cette transition :
    les étapes suivent alors l'ordre réel (toucher, puis l'écran affiché)."""
    out = list(evts)
    i = 0
    while i < len(out):
        e = out[i]
        if e.get("type") == "action":
            # la transition que l'action a provoquée : la dernière juste avant elle (et son écho « écran » éventuel)
            j = i - 1
            while j >= 0 and out[j].get("type") == "ecran":
                j -= 1
            trans = out[j] if j >= 0 and out[j].get("type") == "transition" and out[j].get("de") else None
            if trans and j > 0 and out[j - 1].get("type") == "ecran" and out[j - 1].get("ecran") == trans.get("vers"):
                j -= 1
            if trans:
                nom, a = _action(e.get("detail", ""))
                sur_depart = nom == "press_back" or (a.get("locator") and _element(trans["de"], a["locator"], plateforme)[0]
                                                      and not _element(trans["vers"], a["locator"], plateforme)[0])
                if sur_depart:
                    out.insert(j, out.pop(i))
        i += 1
    return out


def _action(detail: str) -> tuple[str, dict]:
    """« tap {json} » → (« tap », {locator…}) ; détail illisible → (type, {})."""
    nom, _, reste = str(detail or "").partition(" ")
    try:
        return nom, json.loads(reste) if reste.strip().startswith("{") else {}
    except ValueError:
        return nom, {}


def etapes_de_session(sid: str, plateforme: str, noms_variables: dict | None = None) -> tuple[list, list]:
    """Étapes BDD fidèles au déroulé d'une session : chaque action réellement faite (toucher, saisir, revenir,
    défiler), dans l'ordre, et l'écran d'arrivée vérifié après chaque changement d'écran. Seuls les champs réellement
    saisis deviennent des étapes de données ; une saisie par référence {{var:CLE}} garde sa variable.
    Rend (étapes, avertissements)."""
    from atelier.discovery import carte, classement

    noms_variables = noms_variables or {}
    regles = classement.regles()
    etapes, avertissements, courant = [], [], None
    evts = _evenements_session(sid)
    if any(x.get("type") == "transition" for x in evts):  # les transitions disent l'ordre ; « nouvel écran » n'en est que l'écho
        evts = [x for x in evts if x.get("type") != "ecran"]
    evts = _remettre_actions_en_ordre(evts, plateforme)
    try:  # vérifications consignées : la version corrigée fait foi, une vérification retirée ne donne pas d'étape
        from atelier.discovery import sessions_discovery

        consignees = {(a.get("date"), a.get("locator")): a for a in sessions_discovery._lire(sid).get("assertions") or []}
    except (KeyError, ValueError, OSError):
        consignees = {}
    dernier_sms = 0  # index après la dernière étape SMS : le repère suivant se cherche au-delà
    depart = next((x["de"] for x in evts if x.get("type") == "transition" and x.get("de")), None) \
        or next((x["ecran"] for x in evts if x.get("type") == "ecran" and x.get("ecran")), None)
    if depart and evts and next((x for x in evts if x.get("type") in ("transition", "ecran", "action")), {}).get("type") == "action":
        courant = depart  # la session commence par une action sur l'écran de départ
        etapes.append(bdd._etape("Étant donné", f"que je suis sur l'écran {_lisible(carte.ecran(courant))}", ecran=courant))
    for e in evts:
        t = e.get("type")
        if t == "transition" and e.get("vers"):
            if courant is None and e.get("de"):
                courant = e["de"]
                etapes.append(bdd._etape("Étant donné", f"que je suis sur l'écran {_lisible(carte.ecran(courant))}", ecran=courant))
            if e["vers"] != courant:
                courant = e["vers"]
                etapes.append(bdd._etape("Alors", f"l'écran {_lisible(carte.ecran(courant))} est affiché", ecran=courant))
            continue
        if t == "ecran" and e.get("ecran") and courant is None:
            courant = e["ecran"]
            etapes.append(bdd._etape("Étant donné", f"que je suis sur l'écran {_lisible(carte.ecran(courant))}", ecran=courant))
            continue
        if t == "predefinie" and e.get("etape") in ETAPES_SMS:
            nom = e["etape"]
            if nom != "preparer_sms" and not any(x.get("predefinie") == "preparer_sms" for x in etapes[dernier_sms:]):
                # le test doit poser le repère AVANT l'action qui envoie le SMS : juste avant la dernière action faite
                i = max((k for k, x in enumerate(etapes) if k >= dernier_sms and x["type"] in ("when", "and") and x.get("locator")),
                        default=len(etapes))
                etapes.insert(i, bdd._etape("Et", ETAPES_SMS["preparer_sms"], ecran=etapes[i - 1].get("ecran", "") if i else courant or "",
                                            predefinie="preparer_sms"))
            etapes.append(bdd._etape("Et", ETAPES_SMS[nom], ecran=courant or e.get("ecran") or "", locator=e.get("locator") or "",
                                     predefinie=nom))
            if nom != "preparer_sms":
                dernier_sms = len(etapes)
            continue
        if t == "assertion" and e.get("locator"):
            a = consignees.get((e.get("date"), e.get("locator")))
            if a is None:
                continue  # retirée après la session
            lib = (a.get("element") or "l'élément").strip()
            ecran_a = courant or a.get("ecran") or ""
            if a.get("mode") == "texte" and a.get("variable"):
                var = a["variable"]
                nom_var = noms_variables.get(var, var)
                etapes.append(bdd._etape("Alors", f"{lib.lower()} affiche la donnée {nom_var}", ecran=ecran_a, locator=a["locator"],
                                         jdd=var.lower(), variable=var, assertion=True))
            else:
                etapes.append(bdd._etape("Alors", f"{lib.lower()} est affiché", ecran=ecran_a, locator=a["locator"], assertion=True))
            continue
        if t != "action":
            continue
        nom, a = _action(e.get("detail", ""))
        el_cle, el = _element(courant, a["locator"], plateforme) if courant and a.get("locator") else ("", {})
        lib = (el.get("libelle") or el_cle or "l'élément").strip()
        technique = "_" in lib and " " not in lib  # libellé = identifiant technique : pas un texte lisible
        if nom == "press_back":
            etapes.append(bdd._etape("Quand", "je reviens en arrière", ecran=courant or ""))
        elif nom == "swipe":
            etapes.append(bdd._etape("Et", "je fais défiler l'écran", ecran=courant or ""))
        elif nom == "tap" and a.get("locator"):
            c = classement.classer({"key": el_cle, "libelle": lib, "type": el.get("type") or "bouton"}, r=regles)
            if c["classe"] in ("sensitive", "forbidden"):
                avertissements.append(f"Action {classement.LIBELLES[c['classe']]} « {lib} » : à autoriser explicitement dans le scénario.")
            etapes.append(bdd._etape("Quand", f"je touche {lib.lower()}", ecran=courant or "", locator=a["locator"]))
        elif nom == "type_text" and str(a.get("text") or "").strip() == "{{otp}}":
            continue  # saisie du code OTP : c'est l'étape prédéfinie « je saisis le code OTP reçu par SMS »
        elif nom == "type_text" and a.get("locator"):
            m = re.fullmatch(r"\{\{\s*var\s*:\s*([A-Z0-9_]+)\s*\}\}", str(a.get("text") or "").strip())
            var = m.group(1) if m else ""
            champ = (el_cle or "champ").lower()
            if etapes and etapes[-1]["type"] in ("when", "and") and etapes[-1].get("locator") and etapes[-1]["texte"].startswith("je touche") \
                    and _element(courant, etapes[-1]["locator"], plateforme)[0] == el_cle and el_cle:
                etapes.pop()  # toucher le champ pour y mettre le curseur : pas une étape
            nom_var = noms_variables.get(var, var)
            if technique or lib == "l'élément":
                lib = re.sub(r"\s*\(fictif\)\s*$", "", nom_var) if var else "le champ"
            texte = f"je renseigne {lib.lower()} avec " + (f"la donnée {nom_var}" if var else "le jeu de données")
            etapes.append(bdd._etape("Et", texte, ecran=courant or "", locator=a["locator"], jdd=var.lower() or champ, variable=var))
    # une même étape répétée à la suite (double toucher enregistré) n'apparaît qu'une fois
    propres = [x for i, x in enumerate(etapes) if not i or (x["texte"], x["type"]) != (etapes[i - 1]["texte"], etapes[i - 1]["type"])]
    # retour en arrière final (on range l'application en fin de session) : pas une étape du test
    while len(propres) > 2 and propres[-1]["type"] == "then" and propres[-2]["texte"] == "je reviens en arrière":
        propres = propres[:-2]
    return propres, avertissements


class DejaCouvert(ValueError):
    """Le brouillon referait un test BDD existant (mêmes actions sur les mêmes écrans)."""

    def __init__(self, existant: dict, inclus: bool):
        self.existant = existant
        quoi = "est déjà contenu dans" if inclus else "refait exactement"
        super().__init__(f"Déjà couvert : ce déroulé {quoi} le test BDD « {existant['titre']} » ({existant['cle']}, "
                         f"{existant['statut']}). Rien n'a été créé ; ouvrir ce test, ou forcer pour créer une variante.")


def signature(etapes: list[dict]) -> tuple:
    """Ce que fait un scénario, indépendamment du libellé : actions (locator touché ou saisi, retour, défilement) et
    écrans vérifiés, dans l'ordre. Deux scénarios de même signature font le même test."""
    sig = []
    for e in etapes:
        if e.get("type") == "given":
            continue
        if e.get("locator"):
            x = ("action", e.get("ecran", ""), e["locator"])
        elif e.get("resultat_attendu"):  # une assertion métier en plus fait un test plus fort, pas un doublon
            x = ("attendu", e["resultat_attendu"])
        elif e.get("type") == "then" and e.get("ecran"):
            x = ("ecran", e["ecran"])
        elif e["texte"] in ("je reviens en arrière", "je fais défiler l'écran"):
            x = ("geste", e.get("ecran", ""), e["texte"])
        else:
            continue
        if not sig or sig[-1] != x:
            sig.append(x)
    return tuple(sig)


def _contient(grand: tuple, petit: tuple) -> bool:
    n = len(petit)
    return any(grand[i:i + n] == petit for i in range(len(grand) - n + 1))


def deja_couvert(etapes: list[dict], application: str = "", profil: str = "") -> dict | None:
    """Test BDD existant (de la même application, même profil de données) qui fait déjà ce déroulé, tel quel ou en plus
    long ; None sinon. Un déroulé qui PROLONGE un test existant, ou le rejoue avec un autre profil de données, n'est pas
    un doublon (variante plus complète, ou variante de données)."""
    sig = signature(etapes)
    if not any(x[0] in ("action", "geste") for x in sig):  # aucune action : rien à comparer (trajet générique)
        return None
    for b in bdd.lister():
        m = bdd.charger(b["cle"]) or {}
        if application and m.get("application") and m["application"] != application:
            continue
        if (m.get("profil_donnees") or "").upper() != (profil or "").upper():
            continue
        for s in m.get("scenarios", []):
            autre = signature(s.get("etapes", []))
            if autre and _contient(autre, sig):
                return {"cle": b["cle"], "titre": b.get("titre") or b["cle"], "statut": b.get("statut", ""),
                        "scenario": s.get("nom", ""), "inclus": autre != sig}
    return None


def brouillon(ecrans: list[str] | None = None, parcours: str = "", session: str = "", titre: str = "",
              plateforme: str = "", cle: str = "", forcer: bool = False) -> dict:
    """Crée le brouillon BDD dans Test Design et renvoie {cle, gherkin, etapes, locators, donnees, avertissements}.
    Refuse (DejaCouvert) un déroulé qu'un test BDD existant fait déjà, sauf forcer=True (variante voulue)."""
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
    variables, profil_donnees = {}, ""
    try:  # variables réellement utilisées sur chaque champ : celles de la session source d'abord, sinon toutes les sessions
        from atelier.discovery import donnees as ref_donnees

        noms = {v["cle"]: v["nom"] for v in ref_donnees.variables()}
        utilisees = {}
        for l in ref_donnees.liens_carte() + (ref_donnees.liens_carte(session) if session else []):
            if l["element"] and l["cle"] in noms:
                utilisees[(l["ecran"], l["element"])] = l["cle"]
        if session:
            profil_donnees = ref_donnees.contexte(session).get("profil", "")
    except Exception:  # noqa: BLE001 — référentiel illisible : le brouillon reste générique
        noms, utilisees = {}, {}
    fideles = []
    if session:  # le déroulé réel de la session plutôt que le chemin de la carte
        fideles, av = etapes_de_session(session, plat, noms)
        if any(e["type"] in ("when", "and") for e in fideles):  # au moins une action enregistrée
            avertissements += av
            sensible = any("autoriser explicitement" in a for a in av)
        else:
            fideles = []
    if fideles:
        etapes.extend(fideles)
        for e in fideles:
            if e.get("locator"):
                locators["connus"] += 1
            if e.get("jdd") and (e["texte"].startswith("je renseigne") or (e["type"] == "then" and e.get("variable"))):
                donnees.append(e["jdd"])
                if e.get("variable"):
                    variables[e["jdd"]] = e["variable"]
        seq_trajet = []
    else:
        etapes.append(bdd._etape("Étant donné", f"que je suis sur l'écran {_lisible(seq[0])}", ecran=_ref(seq[0])))
        seq_trajet = list(zip(seq, seq[1:]))
    renseignes = set()

    def champs(e):
        if e["id"] in renseignes:
            return
        renseignes.add(e["id"])
        for k, el in (e.get("elements") or {}).items():
            if el.get("type") == "champ":
                loc = ((el.get("locators") or {}).get(plat) or [""])[0]
                var = utilisees.get((_ref(e), k), "")
                etapes.append(bdd._etape("Et", f"je renseigne {(el.get('libelle') or k).lower()} avec "
                                         + (f"la donnée {noms[var]}" if var else "le jeu de données"),
                                         ecran=_ref(e), locator=loc, jdd=k, variable=var))
                donnees.append(k)
                if var:
                    variables[k] = var

    for a, b in seq_trajet:
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
    if profil_donnees and not m_jdd_connu(profil_donnees):
        avertissements.append(f"Profil de données {profil_donnees} : créer son jeu de données des tests (Discovery › Données › "
                              "profil › « Jeu de données des tests »), sinon le script échouera (${JDD} absent).")
    cadre = cadrage_source(parcours, session)
    attendu = str(cadre.get("resultat_attendu") or "").strip()
    if attendu:  # le résultat attendu saisi au cadrage devient l'assertion finale du scénario
        etapes.append(bdd._etape("Alors", f"le résultat attendu est obtenu : {attendu}", ecran=_ref(seq[-1]), resultat_attendu=attendu))
    description = [f"Brouillon généré depuis la Discovery ({source}) : à relire et valider."]
    for lib, cle_c in (("Objectif", "objectif"), ("Point de départ", "point_depart"), ("Résultat attendu", "resultat_attendu")):
        if str(cadre.get(cle_c) or "").strip():
            description.append(f"{lib} : {str(cadre[cle_c]).strip()}")
    tags = ["discovery"] + (["action_sensible"] if sensible else [])
    from atelier.generation import rangement

    m = {"langue": "fr", "feature": titre, "module": rangement.module_des_ecrans([e["id"] for e in seq]), "description": description,
         "application": carte.app_courante() or "",
         "contexte": [], "tags": [], "source": f"discovery ({source})", "parcours": parcours, "session": session, "titre": titre, "jdd": profil_donnees.upper() if profil_donnees and m_jdd_connu(profil_donnees) else "", "statut": "brouillon",
         **({"profil_donnees": profil_donnees} if profil_donnees else {}),
         "scenarios": [{"id": bdd._id(), "nom": titre, "type": "principal", "tags": tags, "depuis": "", "etapes": etapes}]}
    existant = deja_couvert(etapes, m["application"], profil_donnees)
    if existant and not forcer:
        raise DejaCouvert(existant, existant["inclus"])
    if existant:
        avertissements.append(f"Variante créée à la demande : le test BDD {existant['cle']} fait déjà ce déroulé.")
    base = bdd._slug(cle or f"parcours_{titre}")
    cle, n = base, 2
    while bdd.charger(cle):
        cle, n = f"{base}_{n}", n + 1
    m["cle"] = cle
    m = bdd.sauver(m, auteur="discovery")
    return {"cle": cle, "titre": titre, "module": m.get("module", ""), "chemin_robot": rangement.chemin_robot(m),
            "dossier_xray": rangement.dossier_xray(m), "gherkin": bdd.serialiser(m), "etapes": len(etapes), "ecrans": [_ref(e) for e in seq],
            "locators": locators, "donnees": donnees, "variables": variables, "profil_donnees": profil_donnees,
            "avertissements": avertissements, "controles": bdd.controles(m)}
