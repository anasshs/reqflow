"""Automation Studio, compléments du cahier : tendance dans le temps, exécution d'une étape isolée, locators de
secours réellement utilisés et correction assistée, factorisation des keywords.

Règles : rien n'est inventé (tendance = relevés réels datés, jamais reconstitués) ; aucune modification de fichier
sans validation explicite (correction et factorisation : proposition, puis application par l'automaticien, avec
historique de l'éditeur) ; une correction n'est jamais déclarée fiable : le script modifié repasse en revue et doit
tenir 3 exécutions stables (invariant 5).
"""
from __future__ import annotations

import html
import json
import re
from datetime import date, datetime

from atelier.domain import projet


def _dossier():
    d = projet.PROJECT_DIR / "studio"
    d.mkdir(parents=True, exist_ok=True)
    return d


# =========================================================================== tendance dans le temps
def relever_tendance(vue: dict) -> None:
    """Un relevé par jour des indicateurs du tableau de bord (appelé à l'affichage) : courbes sans reconstitution."""
    f = _dossier() / "tendance.jsonl"
    jour = date.today().isoformat()
    lignes = f.read_text("utf-8").splitlines() if f.exists() else []
    if lignes and json.loads(lignes[-1]).get("jour") == jour:
        lignes = lignes[:-1]  # le relevé du jour est remplacé par le plus récent
    k = vue["kpi"]
    lignes.append(json.dumps({"jour": jour, "tests_automatises": k["tests_automatises"], "couverture_automatisee": k["couverture_automatisee"],
                              "candidats": k["candidats"], "en_revue": k["en_revue"], "approuves": k["approuves"],
                              "locators_a_corriger": k["locators_a_corriger"], "keywords": k["keywords"]}, ensure_ascii=False))
    f.write_text("\n".join(lignes[-400:]) + "\n", "utf-8")


def tendance() -> list[dict]:
    f = _dossier() / "tendance.jsonl"
    return [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()] if f.exists() else []


# =========================================================================== étape isolée
def preparer_etape(keyword: str, jdd: str, arguments: list[str] | None = None) -> dict:
    """Suite temporaire (dans results/, jamais dans le dépôt) : INITIALISATION + JDD, puis le seul keyword choisi,
    et « Terminer Le Test » s'il existe. Renvoie la cible à lancer via la file de l'Execution Center."""
    from atelier.domain import roles
    from atelier.execution.depot_robot import lire_depot, normaliser

    roles.exiger("executer_etape")
    inv = lire_depot()
    par_nom = {normaliser(k["nom"]): k for k in inv["keywords"].values()}
    k = par_nom.get(normaliser(keyword or ""))
    if not k:
        raise ValueError(f"Keyword absent du socle : {keyword}")
    if not re.fullmatch(r"[A-Z0-9_]+", jdd or ""):
        raise ValueError("Jeu de données obligatoire (INITIALISATION + &{JDD_<NOM>}).")
    for a in arguments or []:
        if re.search(r"[\r\n\t]", str(a)):
            raise ValueError("Argument sur une seule ligne.")
    init, fin = par_nom.get(normaliser("Initialiser Le Test")), par_nom.get(normaliser("Terminer Le Test"))
    ressources = sorted({k["fichier"]} | ({init["fichier"]} if init else set()) | ({fin["fichier"]} if fin else set()))
    dossier = f"results/builder/{datetime.now():%Y%m%d-%H%M%S}"
    profondeur = dossier.count("/") + 1
    lignes = ["*** Settings ***", f"Documentation    Étape isolée « {k['nom']} » (Automation Studio › Construire). Fichier temporaire.",
              *[f"Resource    {'../' * profondeur}{r}" for r in ressources], *([f"Test Teardown    {fin['nom']}"] if fin else []),
              "", "*** Test Cases ***", f"Étape isolée · {k['nom']}", "    [Tags]    etape_isolee"]
    if init:
        lignes.append(f"    {init['nom']}    &{{JDD_{jdd}}}")
    lignes.append(f"    {k['nom']}" + "".join(f"    {a}" for a in arguments or [] if str(a).strip()))
    cible = f"{dossier}/etape.robot"
    projet.ecrire_fichier(cible, "\n".join(lignes) + "\n", False)
    return {"cible": cible, "keyword": k["nom"], "jdd": jdd}


# =========================================================================== locators de secours utilisés
RE_SECOURS = re.compile(r"(?:Locator|Sélecteur) de secours utilisé : (.+?) \(principal introuvable : (.+?)\)")


def secours_utilises(limite_runs: int = 50) -> dict:
    """Recours aux secours lus dans les output.xml des derniers runs (message WARN du keyword « Localiser » du socle) :
    {valeur principale: [{run, date, secours}]}, du plus récent au plus ancien."""
    base = projet.PROJECT_DIR / "results" / "runs"
    out: dict = {}
    for d in sorted(base.glob("RUN-*"), reverse=True)[:limite_runs] if base.exists() else []:
        f = d / "output.xml"
        if not f.exists():
            continue
        try:
            texte = f.read_text("utf-8", errors="replace")
        except OSError:
            continue
        for m in RE_SECOURS.finditer(texte):
            secours, principal = html.unescape(m.group(1)), html.unescape(m.group(2))
            out.setdefault(principal, []).append({"run": d.name, "secours": secours})
    return out


def propositions_correction() -> list[dict]:
    """Locators à corriger (fragiles, obsolètes, ou dont un secours a servi) et la valeur proposée :
    1) le secours qui a réellement fonctionné à l'exécution ; 2) sinon une valeur stable observée sur l'écran
    cartographié pour la même clé. Aucune proposition sans source vérifiable."""
    from atelier.discovery import carte
    from atelier.generation import studio

    utilises = secours_utilises()
    observes: dict = {}
    try:
        for e in carte.ecrans():
            for cle, el in (e.get("elements") or {}).items():
                for plat, vals in (el.get("locators") or {}).items():
                    observes[((e.get("nom") or e["id"]).lower(), cle, plat)] = vals or []
    except Exception:  # noqa: BLE001 — carte absente : seuls les secours servent de source
        pass
    out = []
    for l in studio.locators():
        if not l.get("valeur") or not l.get("fichier"):
            continue
        usages = utilises.get(l["valeur"], [])
        if l["etat"] not in ("Fragile", "Obsolete") and not usages:
            continue
        prop, source = "", ""
        if usages:
            prop, source = usages[0]["secours"], f"secours utilisé à l'exécution ({len(usages)} fois, dernier : {usages[0]['run']})"
        else:
            stables = [v for v in observes.get((l["ecran"], l["cle"], l["plateforme"]), []) if v != l["valeur"] and studio.fiabilite(v)[1] == "Stable"]
            if stables:
                prop, source = stables[0], "valeur stable observée sur l'écran cartographié"
        out.append({"id": l["id"], "ecran": l["ecran"], "cle": l["cle"], "plateforme": l["plateforme"], "fichier": l["fichier"], "etat": l["etat"],
                    "valeur": l["valeur"], "proposition": prop, "source": source, "secours_utilises": len(usages),
                    "fiabilite_proposee": studio.fiabilite(prop)[1] if prop else ""})
    return out


def appliquer_correction(locator_id: str, nouvelle_valeur: str, version_lue: str | None = None) -> dict:
    """Remplace la valeur principale du locator dans son fichier (éditeur : historisé, protection contre l'écrasement).
    Les suites qui l'utilisent repassent en revue (empreinte) ; la correction n'est pas déclarée fiable ici."""
    from atelier.domain import roles
    from atelier.generation import editeur, studio

    roles.exiger("corriger_locator")
    nouvelle_valeur = (nouvelle_valeur or "").strip()
    if not nouvelle_valeur or re.search(r"\s{2,}|[\r\n\t]", nouvelle_valeur):
        raise ValueError("Nouvelle valeur sur une ligne, sans double espace (séparateur Robot).")
    l = next((x for x in studio.locators() if x["id"] == locator_id), None)
    if not l or not l.get("fichier"):
        raise KeyError(f"Locator inconnu : {locator_id}")
    chemin = projet.safe_path(l["fichier"])
    avant = chemin.read_text("utf-8")
    entete = f"&{{LOC_{l['ecran'].upper()}_{l['plateforme'].upper()}}}"
    lignes, dans, remplace = avant.splitlines(), False, 0
    for i, ligne in enumerate(lignes):
        if ligne.startswith("&{"):
            dans = ligne.split()[0] == entete
        elif not ligne.startswith("..."):
            dans = False
        if dans:
            nouvelle = re.sub(rf"(?<![\w.]){re.escape(l['cle'])}={re.escape(l['valeur'])}(?=\s{{2,}}|$)", f"{l['cle']}={nouvelle_valeur}", ligne)
            if nouvelle != ligne:
                lignes[i], remplace = nouvelle, remplace + 1
    if remplace != 1:
        raise ValueError(f"Valeur introuvable de façon unique dans {l['fichier']} ({remplace} occurrence(s)) : corriger dans l'éditeur.")
    contenu = "\n".join(lignes) + ("\n" if avant.endswith("\n") else "")
    r = editeur.enregistrer(l["fichier"], contenu, version_lue if version_lue is not None else avant)
    studio._journaliser("correction_locator", locator=locator_id, de=l["valeur"], vers=nouvelle_valeur, fichier=l["fichier"])
    return {**r, "locator": locator_id, "avant": l["valeur"], "apres": nouvelle_valeur,
            "suite": "Les suites qui utilisent ce locator repassent en revue ; fiabilité confirmée après 3 exécutions stables."}


# =========================================================================== factorisation des keywords
def _normaliser_corps(corps: str) -> str:
    lignes = [re.sub(r"\s{2,}", "  ", l.strip()) for l in corps.splitlines()]
    return "\n".join(l for l in lignes if l and not l.startswith("[Documentation]") and not l.startswith("..."))


def propositions_factorisation(avec_ia: bool = False) -> list[dict]:
    """Groupes de keywords au corps identique (même suite d'appels, aux espaces près) ou au même nom dans plusieurs
    fichiers : proposition de garder un seul keyword (le plus utilisé) et de remplacer les appels des autres.
    avec_ia : explication rédigée par l'IA configurée (facultatif, jamais appliquée sans validation)."""
    from atelier.execution.depot_robot import normaliser
    from atelier.generation import studio

    inv = studio._inv()
    kws = {k["id"]: k for k in studio.keywords()}
    groupes: dict = {}
    for kid, k in inv["keywords"].items():
        try:
            corps = _normaliser_corps(studio._corps(k))
        except (OSError, ValueError):
            continue
        if len(corps.splitlines()) < 1 or kid not in kws:
            continue
        groupes.setdefault(("corps", corps), []).append(kid)
        groupes.setdefault(("nom", normaliser(k["nom"])), []).append(kid)
    vus, out = set(), []
    for (genre, _), ids in groupes.items():
        ids = sorted(set(ids))
        if len(ids) < 2 or tuple(ids) in vus:
            continue
        vus.add(tuple(ids))
        garder = max(ids, key=lambda i: (kws[i]["utilisations"], -len(kws[i]["fichier"])))
        out.append({"id": "|".join(ids), "raison": "corps identique" if genre == "corps" else "même nom dans plusieurs fichiers",
                    "garder": {"id": garder, "nom": kws[garder]["nom"], "fichier": kws[garder]["fichier"]},
                    "remplacer": [{"id": i, "nom": kws[i]["nom"], "fichier": kws[i]["fichier"], "ligne": kws[i]["ligne"], "utilisations": kws[i]["utilisations"]}
                                  for i in ids if i != garder],
                    "applicable": genre == "corps"})  # même nom, corps différents : décision humaine, pas d'application automatique
    if avec_ia and out:
        from atelier.intelligence import fournisseur_ia

        try:
            texte = fournisseur_ia.completer("Tu es relecteur Robot Framework. Réponds en français, en 3 phrases maximum par groupe.",
                                             "Explique pour chaque groupe s'il faut factoriser et le risque :\n" + json.dumps(out, ensure_ascii=False)[:6000], 800)
            for g in out:
                g["avis_ia"] = texte
        except Exception as e:  # noqa: BLE001 — IA indisponible : la proposition reste utilisable
            for g in out:
                g["avis_ia"] = f"IA indisponible : {e}"
    return out


def appliquer_factorisation(groupe_id: str) -> dict:
    """Pour un groupe « corps identique » : remplace dans tout le dépôt les appels aux keywords doublons par le keyword
    gardé, puis retire leurs définitions. Chaque fichier passe par l'éditeur (historique + diff) ; les suites modifiées
    repassent en revue. Refusé si un fichier a besoin d'une ressource qu'il n'importe pas."""
    from atelier.domain import roles
    from atelier.generation import editeur, studio

    roles.exiger("factoriser_keyword")
    g = next((x for x in propositions_factorisation() if x["id"] == groupe_id), None)
    if not g:
        raise KeyError("Groupe introuvable (le dépôt a changé) : recharger les propositions.")
    if not g["applicable"]:
        raise ValueError("Même nom mais corps différents : à trancher dans l'éditeur, pas de factorisation automatique.")
    inv = studio._inv()
    garde = g["garder"]
    modifs: dict = {}
    for r in g["remplacer"]:
        if r["nom"].lower() != garde["nom"].lower():  # appels renommés partout où le doublon est utilisé
            motif = re.compile(rf"(?im)^([ \t]+(?:(?:Given|When|Then|And|But)[ \t]+)?(?:\$\{{[^}}]+\}}=?[ \t]{{2,}})?){re.escape(r['nom'])}(?=[ \t]{{2,}}|[ \t]*$)")
            for fichier in inv["fichiers"]:
                txt = modifs.get(fichier) or projet.safe_path(fichier).read_text("utf-8")
                nouveau = motif.sub(lambda m: m.group(1) + garde["nom"], txt)
                if nouveau != txt:
                    modifs[fichier] = nouveau
        # définition du doublon retirée (du nom jusqu'au prochain keyword ou section)
        txt = modifs.get(r["fichier"]) or projet.safe_path(r["fichier"]).read_text("utf-8")
        lignes = txt.splitlines()
        debut = next((i for i, l in enumerate(lignes) if l.rstrip() == r["nom"]), None)
        if debut is None:
            raise ValueError(f"Définition de « {r['nom']} » introuvable dans {r['fichier']}.")
        fin = debut + 1
        while fin < len(lignes) and (not lignes[fin] or lignes[fin][0].isspace()):
            fin += 1
        modifs[r["fichier"]] = "\n".join(lignes[:debut] + lignes[fin:]) + "\n"
    def accessibles(f: str) -> set:  # ressources importées, directement ou en cascade
        vus, pile = set(), [f]
        while pile:
            x = pile.pop()
            for r in (inv["fichiers"].get(x) or {}).get("resources") or []:
                if r not in vus:
                    vus.add(r)
                    pile.append(r)
        return vus

    for fichier in modifs:  # un fichier qui appellera le keyword gardé doit pouvoir le résoudre
        appelle = any(r["nom"].lower() != garde["nom"].lower() and re.search(rf"(?im)^[ \t]+.*{re.escape(r['nom'])}", projet.safe_path(fichier).read_text("utf-8"))
                      for r in g["remplacer"])
        if appelle and fichier != garde["fichier"] and garde["fichier"] not in accessibles(fichier):
            raise ValueError(f"{fichier} n'importe pas {garde['fichier']} : ajouter la ressource avant de factoriser.")
    resultats = [editeur.enregistrer(f, c) for f, c in modifs.items()]
    studio._journaliser("factorisation_keywords", nom=garde["nom"], garde=garde["id"], retires=[r["id"] for r in g["remplacer"]],
                        fichiers=sorted(modifs))
    return {"garde": garde, "retires": g["remplacer"], "fichiers": resultats}
