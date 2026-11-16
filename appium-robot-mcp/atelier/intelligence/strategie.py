"""Référentiel de pilotage du projet (ex-module Test Strategy : plus d'écran dédié depuis le 2026-11-15).

Ses éléments s'éditent là où ils servent (composant web window.Pilotage) : périmètre (Paramètres),
environnements (Execution Center), objectifs et critères d'entrée / sortie (Quality Governance), décisions
du plan d'automatisation (Automation Studio) ; le document de stratégie s'exporte depuis Quality Governance › Rapports.

Une stratégie par projet de tests, une seule source de données :
  strategie/strategie.yaml        version de travail (sauvegardée à chaque modification)
  strategie/versions/v<N>.yaml    instantané d'une version publiée, jamais réécrit
  strategie/versions/index.json   statut des versions (publiée, archivée…)
  strategie/journal.jsonl         journal d'audit (qui, quand, quoi)

Règles appliquées :
- RG03 une seule version publiée active ; RG12 une version publiée n'est jamais modifiée :
  la première modification ouvre une nouvelle version de travail (Draft).
- RG04 / RG10 les objectifs et critères automatiques se mesurent avec des indicateurs CALCULÉS
  depuis les sources réelles (patrimoine Xray, graphe, historique des runs), jamais saisis.
- RG11 aucune recommandation n'est inventée : le plan d'automatisation part des candidats calculés
  (couverture.candidats) et chaque décision est humaine et journalisée.
- Les secrets ne sont jamais stockés : un accès d'environnement est une RÉFÉRENCE (env:VAR, coffre:chemin).
Droits et rôles : non gérés (interface locale mono-utilisateur, sans authentification) ; l'auteur
journalisé est le compte du poste.
"""
from __future__ import annotations

import getpass
import json
import os
import re
import secrets
import urllib.request
from datetime import date, datetime
from pathlib import Path

import yaml

from atelier.domain import projet

STATUTS = ["Draft", "In Review", "Approved", "Published", "Archived"]
LIBELLES_STATUT = {"Draft": "Brouillon", "In Review": "En revue", "Approved": "Approuvée",
                   "Published": "Publiée", "Archived": "Archivée"}
TRANSITIONS = {"soumettre": ("Draft", "In Review"), "demander_modifications": ("In Review", "Draft"),
               "approuver": ("In Review", "Approved"), "publier": ("Approved", "Published"),
               "archiver": ("Published", "Archived")}
STATUTS_PLAN = ["À analyser", "Recommandé par IA", "À valider", "Approuvé", "En construction", "Automatisé", "Rejeté"]
DECISIONS_PLAN = ["À analyser", "À valider", "Approuvé", "En construction", "Rejeté"]  # « Recommandé par IA » : réservé à l'IA
REF_SECRET = re.compile(r"^(env|coffre):[A-Za-z0-9_./-]+$")


# =========================================================================== schéma des rubriques
def _c(nom, libelle, type_="texte", options=None, obligatoire=False, aide="", cible=""):
    return {"nom": nom, "libelle": libelle, "type": type_, "options": options or [], "obligatoire": obligatoire,
            "aide": aide, "cible": cible}


PRIORITES = ["Haute", "Moyenne", "Basse"]
NIVEAUX_TEST = ["Unitaires", "Composants", "API", "Intégration", "Système", "End-to-End", "Acceptation métier"]

RUBRIQUES = [
    {"id": "objectifs", "titre": "Objectifs", "numero": 2, "champs": [
        _c("nom", "Nom de l'objectif", obligatoire=True), _c("description", "Description", "long"),
        _c("categorie", "Catégorie", "choix", ["Couverture", "Automatisation", "Délai", "Stabilité", "Qualité"]),
        _c("priorite", "Priorité", "choix", PRIORITES),
        _c("indicateur", "Indicateur de mesure", "indicateur", obligatoire=True,
           aide="Indicateur calculé depuis les sources réelles (RG04 : objectif mesurable)."),
        _c("comparateur", "Sens", "choix", [">=", "<="], aide=">= : atteindre au moins la cible ; <= : rester sous la cible."),
        _c("cible", "Valeur cible", "nombre", obligatoire=True), _c("responsable", "Responsable"),
        _c("echeance", "Échéance", "date"),
        _c("modules", "Modules associés", "refs", cible="perimetre"),
        _c("types", "Types de test associés", "refs", cible="types_tests")]},
    # Les squads (projets Jira des équipes) ne se déclarent plus ici : Politique des US (Paramètres › Configuration).
    {"id": "perimetre", "titre": "Exclusions et criticité", "numero": 3, "champs": [
        _c("nom", "Nom", obligatoire=True),
        _c("niveau", "Niveau", "choix", ["domaine", "module", "fonctionnalite", "exigence", "interface"], obligatoire=True),
        _c("parent", "Élément parent", "ref", cible="perimetre"), _c("description", "Description", "long"),
        _c("criticite", "Criticité métier", "choix", ["Critique", "Haute", "Moyenne", "Basse"]),
        _c("priorite", "Priorité", "choix", PRIORITES), _c("inclus", "Inclus dans le périmètre", "bool"),
        _c("justification", "Justification (exclusion)", "long"), _c("responsable", "Responsable"),
        _c("jira", "Exigences Jira", "liste"), _c("xray", "Tests Xray", "liste")]},
    {"id": "types_tests", "titre": "Types de tests", "numero": 4, "champs": [
        _c("nom", "Type", "choix", ["Fonctionnel", "Régression", "API", "Intégration", "Performance", "Sécurité",
                                    "Compatibilité", "Accessibilité", "Exploratoire", "Autre"], obligatoire=True),
        _c("description", "Description", "long"), _c("objectif", "Objectif"), _c("priorite", "Priorité", "choix", PRIORITES),
        _c("actif", "Actif", "bool"), _c("niveau", "Niveau de test", "ref", cible="niveaux"),
        _c("methode", "Méthode d'exécution", "choix", ["Manuelle", "Automatisée", "Mixte"], obligatoire=True),
        _c("automatisation_autorisee", "Automatisation autorisée", "bool"),
        _c("cible_auto", "Taux d'automatisation cible (%)", "nombre"), _c("responsable", "Responsable"),
        _c("outils", "Outils", "liste"), _c("modules", "Modules", "refs", cible="perimetre")]},
    {"id": "niveaux", "titre": "Niveaux de tests", "numero": 5, "champs": [
        _c("nom", "Niveau", "choix", NIVEAUX_TEST, obligatoire=True), _c("objectif", "Objectif", "long"),
        _c("perimetre", "Périmètre"), _c("responsable", "Responsable"),
        _c("types", "Types de test associés", "refs", cible="types_tests"),
        _c("environnement", "Environnement", "ref", cible="environnements"), _c("outil", "Outil"),
        _c("automatisation", "Automatisation", "choix", ["Aucune", "Partielle", "Complète"]),
        _c("part_cible", "Part cible des tests (%)", "nombre", obligatoire=True,
           aide="Répartition visée (pyramide) : évite une stratégie uniquement E2E."),
        _c("criteres_validation", "Critères de validation", "long")]},
    {"id": "environnements", "titre": "Environnements", "numero": 6, "champs": [
        _c("nom", "Nom", obligatoire=True), _c("type", "Type", "choix", ["DEV", "TEST", "PREPROD", "PROD", "AUTRE"], obligatoire=True),
        _c("usage", "Usage"), _c("url", "URL / endpoint"),
        _c("plateforme", "Plateforme", "choix", ["Web", "Android", "iOS", "API"]),
        _c("application", "Application"), _c("version", "Version"),
        _c("os_version", "Version OS (mobile)"), _c("terminal", "Modèle de terminal (mobile)"),
        _c("navigateur", "Navigateur et version (web)"), _c("resolution", "Résolution"),
        _c("jdd_env", "Environnement de JDD", aide="Nom du fichier data/jdd/<nom>.yaml."),
        _c("acces", "Accès (référence au secret)", aide="env:NOM_VARIABLE ou coffre:chemin. Jamais le secret lui-même."),
        _c("services", "Services dépendants", "liste"), _c("par_defaut", "Environnement par défaut", "bool")]},
    {"id": "criteres", "titre": "Critères d'entrée et de sortie", "numero": 7, "champs": [
        _c("description", "Critère", obligatoire=True), _c("type", "Type", "choix", ["entrée", "sortie"], obligatoire=True),
        _c("obligatoire", "Obligatoire", "bool"),
        _c("verification", "Mode de vérification", "choix", ["automatique", "manuelle"], obligatoire=True),
        _c("indicateur", "Indicateur (vérification automatique)", "indicateur"),
        _c("comparateur", "Sens", "choix", [">=", "<="]), _c("seuil", "Seuil", "nombre"),
        _c("responsable", "Responsable"), _c("preuve", "Preuve / commentaire (vérification manuelle)", "long")]},
    {"id": "risques", "titre": "Risques et contraintes", "numero": 8, "champs": [
        _c("nom", "Risque", obligatoire=True), _c("description", "Description", "long"),
        _c("categorie", "Catégorie", "choix", ["Technique", "Données", "Environnement", "Organisation", "Métier", "Automatisation"]),
        _c("probabilite", "Probabilité (1 à 4)", "choix", ["1", "2", "3", "4"], obligatoire=True),
        _c("impact", "Impact (1 à 4)", "choix", ["1", "2", "3", "4"], obligatoire=True),
        _c("mitigation", "Plan de mitigation", "long"), _c("responsable", "Responsable"),
        _c("elements", "Modules / fonctionnalités concernés", "refs", cible="perimetre"),
        _c("statut", "Statut", "choix", ["Ouvert", "Maîtrisé", "Clos"])]},
    {"id": "donnees", "titre": "Données de test", "numero": 9, "champs": [
        _c("nom", "Besoin de données", obligatoire=True),
        _c("type", "Type", "choix", ["Statique", "Dynamique", "Synthétique", "API", "Base de données", "Fichier"]),
        _c("jdd", "Jeu de données (JDD)", aide="Nom du jeu dans data/jdd/<environnement>.yaml."),
        _c("environnement", "Environnement", "ref", cible="environnements"), _c("source", "Source"),
        _c("prerequis", "Prérequis", "long"),
        _c("sensibilite", "Sensibilité", "choix", ["Publique", "Interne", "Confidentielle", "Secrète"]),
        _c("nature", "Nature", "choix", ["Synthétiques", "Anonymisées"], aide="Données réelles de production interdites."),
        _c("preparation", "Mode de préparation", "long"), _c("nettoyage", "Mode de nettoyage", "long")]},
    {"id": "outils", "titre": "Outils et intégrations", "numero": 10, "champs": [
        _c("nom", "Outil", "choix", ["Jira", "Xray Cloud", "GitLab", "CI/CD", "Robot Framework", "Playwright", "Appium",
                                     "Browser Library", "API", "Oracle", "Grafana", "Autre"], obligatoire=True),
        _c("usage", "Usage dans la stratégie", obligatoire=True), _c("projet", "Projet associé"),
        _c("url", "URL"), _c("responsable", "Responsable")]},
]
PAR_ID = {r["id"]: r for r in RUBRIQUES}
CONNECTEURS = {"Jira": "jira", "Xray Cloud": "xray", "Robot Framework": "robot", "Playwright": "playwright",
               "Appium": "appium", "Oracle": "oracle"}  # clés de /api/sante


# =========================================================================== indicateurs réels
INDICATEURS = {
    "couverture_fonctionnelle": ("Couverture fonctionnelle", "%", "Exigences Jira ayant au moins un test Xray / exigences de l'instantané Xray."),
    "couverture_automatisee": ("Couverture automatisée", "%", "Tests Xray portés en tag par au moins un test Robot du dépôt / tests Xray."),
    "taux_reussite": ("Taux de réussite", "%", "Tests réussis / tests exécutés, sur les 10 derniers runs réels (hors dry run)."),
    "taux_instables": ("Taux de tests instables", "%", "Tests exécutés au moins 2 fois sur les 10 derniers runs réels, ayant été tantôt PASS tantôt FAIL / ces tests."),
    "duree_moyenne_run": ("Temps moyen d'exécution d'un run", "s", "Durée moyenne (fin - début) des 10 derniers runs réels terminés."),
    "exigences_non_couvertes": ("Exigences sans test", "", "Exigences de l'instantané Xray sans aucun test associé."),
    "tests_en_echec": ("Tests automatisés en échec", "", "Tests Xray automatisés dont le dernier résultat Robot est FAIL."),
    "scenarios_bdd_valides": ("Scénarios BDD validés", "%", "Scénarios BDD au statut « validé » / scénarios BDD du projet."),
}


def _graphe():
    from atelier.discovery import connaissance

    return connaissance.construire()


def _runs_reels(limite: int = 10) -> list[dict]:
    from atelier.execution import historique

    return [r for r in historique.lister(50) if not r["dry_run"] and r["passes"] is not None and r.get("fin")][:limite]


def mesures() -> dict:
    """Valeur actuelle de chaque indicateur, depuis les sources réelles ; None si non mesurable."""
    from atelier.execution import historique
    from atelier.generation import bdd
    from atelier.intelligence import patrimoine_xray

    out = {k: {"id": k, "libelle": v[0], "unite": v[1], "definition": v[2], "valeur": None, "detail": ""}
           for k, v in INDICATEURS.items()}
    pat = patrimoine_xray.charger_vue()
    g = None
    if pat:
        g = _graphe()
        exig = pat.get("exigences") or []
        par_exig = {}
        for t in pat["tests"]:
            for e in t.get("exigences") or []:
                par_exig.setdefault(e, []).append(t["cle"])
        couvertes = [e for e in exig if par_exig.get(e["cle"])]
        cx = _couverture_exigences()
        if cx:  # périmètre des exigences importé (JQL) : les exigences sans aucun test comptent aussi
            g_ = cx["global"]
            out["couverture_fonctionnelle"].update(valeur=g_["existence"], detail=f"{g_['couvertes']}/{g_['exigences']} (périmètre Jira)")
            out["exigences_non_couvertes"].update(valeur=g_["sans_test"])
        elif exig:
            out["couverture_fonctionnelle"].update(valeur=round(100 * len(couvertes) / len(exig), 1), detail=f"{len(couvertes)}/{len(exig)}")
            out["exigences_non_couvertes"].update(valeur=len(exig) - len(couvertes))
        auto = [t for t in pat["tests"] if (n := g.noeuds.get(f"test:{t['cle']}")) and n.proprietes.get("automatise")]
        if pat["tests"]:
            out["couverture_automatisee"].update(valeur=round(100 * len(auto) / len(pat["tests"]), 1), detail=f"{len(auto)}/{len(pat['tests'])}")
        echec = [t for t in auto if g.noeuds[f"test:{t['cle']}"].proprietes.get("dernier_resultat") == "FAIL"]
        out["tests_en_echec"].update(valeur=len(echec), detail=", ".join(t["cle"] for t in echec))
    runs = _runs_reels()
    if runs:
        p, e = sum(r["passes"] for r in runs), sum(r["echecs"] for r in runs)
        if p + e:
            out["taux_reussite"].update(valeur=round(100 * p / (p + e), 1), detail=f"{p}/{p + e} sur {len(runs)} run(s)")
        durees = [(datetime.fromisoformat(r["fin"]) - datetime.fromisoformat(r["debut"])).total_seconds()
                  for r in runs if r.get("debut") and r.get("fin")]
        if durees:
            out["duree_moyenne_run"].update(valeur=round(sum(durees) / len(durees), 1), detail=f"{len(durees)} run(s)")
        vus: dict = {}
        for r in runs:
            try:
                for t in historique.detail(r["id"]).get("tests", []):
                    vus.setdefault(t["nom"], []).append(t["statut"])
            except Exception:
                continue
        multi = [k for k, v in vus.items() if len(v) >= 2]
        instables = [k for k in multi if {"PASS", "FAIL"} <= set(vus[k])]
        if multi:
            out["taux_instables"].update(valeur=round(100 * len(instables) / len(multi), 1),
                                         detail=f"{len(instables)}/{len(multi)} test(s)" + (" : " + ", ".join(instables) if instables else ""))
    liste = bdd.lister()
    if liste:
        v = [x for x in liste if x.get("statut") == "validé"]
        out["scenarios_bdd_valides"].update(valeur=round(100 * len(v) / len(liste), 1), detail=f"{len(v)}/{len(liste)}")
    return out


def _evaluer(valeur, comparateur: str, cible) -> str | None:
    if valeur is None or cible in (None, ""):
        return None
    return valeur >= float(cible) if comparateur != "<=" else valeur <= float(cible)


# =========================================================================== stockage
def _dossier() -> Path:
    return projet.PROJECT_DIR / "strategie"


def _fichier() -> Path:
    return _dossier() / "strategie.yaml"


def _auteur() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "inconnu"


def _maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _ecrire_atomique(f: Path, texte: str):
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(f.suffix + ".tmp")
    tmp.write_text(texte, "utf-8")
    os.replace(tmp, f)


def charger() -> dict | None:
    f = _fichier()
    if not f.exists():
        return None
    s = yaml.safe_load(f.read_text("utf-8")) or {}
    s.setdefault("rubriques", {})
    for r in RUBRIQUES:
        s["rubriques"].setdefault(r["id"], [])
    s.setdefault("plan_automatisation", {})
    s.setdefault("commentaires", [])
    # suivi opérationnel (validations de critères, vérifications d'environnement) : hors du document versionné,
    # superposé en lecture uniquement ; jamais écrit dans la stratégie ni dans une version publiée.
    suivi = _suivi()
    for c in s["rubriques"].get("criteres", []):
        c.pop("validation", None)
        if c.get("id") in suivi["criteres"]:
            c["validation"] = suivi["criteres"][c["id"]]
    for e in s["rubriques"].get("environnements", []):
        e.pop("derniere_verification", None)
        if e.get("id") in suivi["environnements"]:
            e["derniere_verification"] = suivi["environnements"][e["id"]]
    return s


def _suivi() -> dict:
    f = _dossier() / "suivi.json"
    d = json.loads(f.read_text("utf-8")) if f.exists() else {}
    d.setdefault("criteres", {})
    d.setdefault("environnements", {})
    return d


def _sauver_suivi(groupe: str, eid: str, valeur: dict):
    d = _suivi()
    d[groupe][eid] = valeur
    _ecrire_atomique(_dossier() / "suivi.json", json.dumps(d, ensure_ascii=False, indent=1))


def _sans_suivi(s: dict) -> dict:
    """Copie du document sans les champs de suivi superposés par charger()."""
    s = json.loads(json.dumps(s, ensure_ascii=False, default=str))
    for c in s.get("rubriques", {}).get("criteres", []):
        c.pop("validation", None)
    for e in s.get("rubriques", {}).get("environnements", []):
        e.pop("derniere_verification", None)
    return s


def _exiger() -> dict:
    s = charger()
    if s is None:
        raise FileNotFoundError("Aucune stratégie : la créer d'abord (RG01 : associée à une application ou un projet).")
    return s


def _journaliser(op: str, s: dict | None = None, **details):
    f = _dossier() / "journal.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    e = {"date": _maintenant(), "auteur": _auteur(), "op": op, "version": (s or {}).get("version"), **details}
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(e, ensure_ascii=False) + "\n")


def journal(limite: int = 200) -> list[dict]:
    f = _dossier() / "journal.jsonl"
    if not f.exists():
        return []
    lignes = [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()]
    return list(reversed(lignes))[:limite]


def _sauver(s: dict):
    s["infos"]["modifie_le"] = _maintenant()
    _ecrire_atomique(_fichier(), yaml.safe_dump(_sans_suivi(s), allow_unicode=True, sort_keys=False))


def _index() -> list[dict]:
    f = _dossier() / "versions" / "index.json"
    return json.loads(f.read_text("utf-8")) if f.exists() else []


def _ecrire_index(ix: list[dict]):
    _ecrire_atomique(_dossier() / "versions" / "index.json", json.dumps(ix, ensure_ascii=False, indent=1))


def creer(nom: str, application: str, version_application: str = "", responsable: str = "") -> dict:
    if not (nom or "").strip() or not (application or "").strip():
        raise ValueError("Nom de la stratégie et application / projet obligatoires (RG01).")
    if _fichier().exists():
        raise FileExistsError("Une stratégie existe déjà pour ce projet.")
    s = {"version": 1, "statut": "Draft",
         "infos": {"nom": nom.strip(), "application": application.strip(), "version_application": version_application.strip(),
                   "responsable": responsable.strip() or _auteur(), "cree_le": _maintenant(), "modifie_le": _maintenant()},
         "rubriques": {r["id"]: [] for r in RUBRIQUES}, "plan_automatisation": {}, "commentaires": []}
    _sauver(s)
    _journaliser("creation", s, nom=nom)
    return etat()


def _avant_modification(s: dict, op: str):
    """RG12 : une version publiée n'est jamais modifiée ; une stratégie en revue ou approuvée revient en brouillon."""
    if s["statut"] in ("Published", "Archived"):  # archivée : reprise possible, toujours dans une nouvelle version
        s["version"] += 1
        s["statut"] = "Draft"
        s.pop("approbation", None)
        _journaliser("nouvelle_version", s, raison=op, depuis=s["version"] - 1)
    elif s["statut"] in ("In Review", "Approved"):
        ancien = s["statut"]
        s["statut"] = "Draft"
        s.pop("approbation", None)
        _journaliser("retour_brouillon", s, raison=op, ancien_statut=ancien)


# =========================================================================== édition
def _coercer(champ: dict, v):
    t = champ["type"]
    if v in (None, ""):
        return [] if t in ("liste", "refs") else False if t == "bool" else ""
    if t == "nombre":
        try:
            return float(str(v).replace(",", ".").replace("%", "").strip())
        except ValueError:
            raise ValueError(f"« {champ['libelle']} » : nombre attendu.") from None
    if t == "bool":
        return v in (True, "true", "1", "oui", 1)
    if t in ("liste", "refs"):
        items = v if isinstance(v, list) else str(v).split(",")
        return [str(x).strip() for x in items if str(x).strip()]
    if t == "choix" and champ["options"] and str(v) not in champ["options"]:
        raise ValueError(f"« {champ['libelle']} » : valeur hors liste ({', '.join(champ['options'])}).")
    if t == "indicateur" and v not in INDICATEURS:
        raise ValueError(f"Indicateur inconnu : {v}.")
    if t == "date":
        date.fromisoformat(str(v))
    return str(v).strip()


def enregistrer_element(rubrique: str, element: dict) -> dict:
    """Crée (sans « id ») ou met à jour (avec « id ») un élément d'une rubrique ; sauvegarde immédiate."""
    if rubrique not in PAR_ID:
        raise KeyError(f"Rubrique inconnue : {rubrique}")
    s = _exiger()
    schema = PAR_ID[rubrique]["champs"]
    propre = {c["nom"]: _coercer(c, element.get(c["nom"])) for c in schema}
    manquants = [c["libelle"] for c in schema if c["obligatoire"] and propre[c["nom"]] in ("", [], None)]
    if manquants:
        raise ValueError("Champs obligatoires : " + ", ".join(manquants) + ".")
    if rubrique == "environnements" and propre["acces"] and not REF_SECRET.match(propre["acces"]):
        raise ValueError("Accès : référence au secret attendue (env:NOM_VARIABLE ou coffre:chemin), jamais le secret.")
    liste = s["rubriques"][rubrique]
    eid = element.get("id")
    existant = next((x for x in liste if x["id"] == eid), None) if eid else None
    if eid and not existant:
        raise KeyError(f"Élément inconnu : {eid}")
    _avant_modification(s, f"{rubrique}:{eid or 'ajout'}")
    if existant:
        for k in ("derniere_verification", "validation"):  # mesures et validations conservées
            if k in existant:
                propre[k] = existant[k]
        existant.clear()
        existant.update({"id": eid, **propre})
    else:
        eid = f"{rubrique[:3]}_{secrets.token_hex(3)}"
        liste.append({"id": eid, **propre})
    if rubrique == "environnements" and propre["par_defaut"]:  # un seul environnement par défaut
        for x in liste:
            x["par_defaut"] = x["id"] == eid
    _sauver(s)
    _journaliser("modification" if existant else "ajout", s, rubrique=rubrique, element=eid)
    return etat()


# valeurs proposées par défaut lors d'un ajout en lot (champs obligatoires non choisis dans la liste)
DEFAUTS_LOT = {
    "types_tests": {"methode": "Mixte", "actif": True, "automatisation_autorisee": True, "priorite": "Moyenne"},
    "niveaux": {"automatisation": "Partielle"},
    "outils": {},
    "environnements": {"type": "TEST"},
}
USAGES_OUTILS = {"Jira": "Exigences, User Stories et anomalies", "Xray Cloud": "Référentiel des tests, plans et exécutions",
                 "GitLab": "Versionnement des scripts et merge requests", "CI/CD": "Exécution planifiée des campagnes",
                 "Robot Framework": "Moteur d'exécution des tests automatisés", "Playwright": "Pilotage du navigateur (web)",
                 "Appium": "Pilotage des applications mobiles", "Browser Library": "Tests web Robot Framework",
                 "API": "Tests d'API", "Oracle": "Données de test (lecture seule)", "Grafana": "Suivi des indicateurs"}


def options_lot(rubrique: str) -> dict:
    """Valeurs proposées pour un ajout en lot : options du champ principal, celles déjà présentes signalées."""
    if rubrique not in ("types_tests", "niveaux", "outils"):
        raise ValueError("Ajout en lot disponible pour Types de tests, Niveaux de tests et Outils.")
    champ = next(c for c in PAR_ID[rubrique]["champs"] if c["nom"] == "nom")
    presents = {x.get("nom") for x in (charger() or {"rubriques": {}}).get("rubriques", {}).get(rubrique, [])}
    return {"rubrique": rubrique, "options": [{"valeur": o, "present": o in presents} for o in champ["options"]],
            "defauts": DEFAUTS_LOT.get(rubrique, {}), "champs_communs": [c for c in PAR_ID[rubrique]["champs"]
                                                                       if c["obligatoire"] and c["nom"] != "nom"]}


def ajouter_en_lot(rubrique: str, valeurs: list[str], communs: dict | None = None, parts: dict | None = None) -> dict:
    """Ajoute plusieurs éléments d'un coup (ex. 5 types de tests cochés). Les valeurs déjà présentes sont ignorées ;
    communs : valeurs appliquées à tous (ex. méthode) ; parts : niveau -> part cible (%) pour les niveaux.
    Une seule nouvelle version si la stratégie était publiée (RG12), chaque ajout journalisé."""
    o = options_lot(rubrique)
    connues = {x["valeur"] for x in o["options"]}
    a_ajouter = [v for v in dict.fromkeys(valeurs) if v in connues and not next(x for x in o["options"] if x["valeur"] == v)["present"]]
    if not a_ajouter:
        raise ValueError("Aucune nouvelle valeur à ajouter (déjà présentes ou inconnues).")
    for v in a_ajouter:
        el = {"nom": v, **o["defauts"], **{k: x for k, x in (communs or {}).items() if x not in ("", None)}}
        if rubrique == "outils":
            el.setdefault("usage", USAGES_OUTILS.get(v, "À préciser"))
        if rubrique == "niveaux":
            el["part_cible"] = (parts or {}).get(v, el.get("part_cible"))
        enregistrer_element(rubrique, el)
    _journaliser("ajout_en_lot", charger(), rubrique=rubrique, valeurs=", ".join(a_ajouter))
    return {**etat(), "ajoutes": a_ajouter}


def squads_a_reprendre(s: dict | None = None) -> list[dict]:
    """Squads déclarées dans le périmètre avant le 2026-11-16 (niveau « squad », supprimé) : à reprendre dans la
    politique des US. Depuis, les squads ne se déclarent qu'à un endroit : Paramètres › Configuration › Politique des US
    (espaces Jira, par application). dans_politique : déjà suivie par la politique (toutes applications confondues)."""
    from atelier.intelligence import testabilite_us

    s = s if s is not None else charger()
    if not s:
        return []
    suivies = {e["projet_jira"]: e.get("application", "") for e in testabilite_us.tous_espaces()}
    return [{"id": x["id"], "nom": x.get("nom", ""), "projet_jira": (x.get("projet_jira") or "").upper(),
             "dans_politique": (x.get("projet_jira") or "").upper() in suivies,
             "application": suivies.get((x.get("projet_jira") or "").upper(), "")}
            for x in s["rubriques"].get("perimetre", []) if x.get("niveau") == "squad"]


def reprendre_squads() -> dict:
    """Reprend les squads du périmètre dans la politique des US (rattachées à l'application active si elles n'y sont pas
    encore), puis les retire du périmètre. Action explicite, journalisée des deux côtés."""
    from atelier.intelligence import testabilite_us

    s = _exiger()
    a_reprendre = squads_a_reprendre(s)
    if not a_reprendre:
        raise ValueError("Aucune squad à reprendre : le périmètre n'en contient plus.")
    ajoutees, deja, refusees = [], [], []
    for q in a_reprendre:
        if q["dans_politique"]:
            deja.append(q["projet_jira"])
            continue
        try:
            testabilite_us.enregistrer_espace({"projet_jira": q["projet_jira"], "nom": q["nom"] or q["projet_jira"]})
            ajoutees.append(q["projet_jira"])
        except ValueError as e:  # clé invalide, projet Xray absent… : la squad reste dans le périmètre
            refusees.append({"projet_jira": q["projet_jira"], "raison": str(e)})
    retirer = {q["id"] for q in a_reprendre if q["projet_jira"] not in {r["projet_jira"] for r in refusees}}
    if retirer:
        _avant_modification(s, "squads reprises dans la politique des US")
        s["rubriques"]["perimetre"] = [x for x in s["rubriques"]["perimetre"] if x["id"] not in retirer]
        for x in s["rubriques"]["perimetre"]:  # un enfant d'une squad retirée remonte à la racine
            if x.get("parent") in retirer:
                x["parent"] = ""
        _sauver(s)
    _journaliser("squads_reprises_dans_politique", s, ajoutees=", ".join(ajoutees), deja=", ".join(deja),
                 refusees=", ".join(r["projet_jira"] for r in refusees))
    return {**etat(), "ajoutees_politique": ajoutees, "deja_dans_politique": deja, "refusees": refusees}


def supprimer_element(rubrique: str, eid: str) -> dict:
    s = _exiger()
    liste = s["rubriques"].get(rubrique)
    if liste is None or not any(x["id"] == eid for x in liste):
        raise KeyError(f"Élément inconnu : {rubrique}/{eid}")
    _avant_modification(s, f"suppression {rubrique}:{eid}")
    s["rubriques"][rubrique] = [x for x in liste if x["id"] != eid]
    _sauver(s)
    _journaliser("suppression", s, rubrique=rubrique, element=eid)
    return etat()


def modifier_infos(champs: dict) -> dict:
    s = _exiger()
    autorises = {"nom", "application", "version_application", "responsable"}
    nouveaux = {k: str(v).strip() for k, v in champs.items() if k in autorises}
    if "nom" in nouveaux and not nouveaux["nom"] or "application" in nouveaux and not nouveaux["application"]:
        raise ValueError("Nom et application obligatoires (RG01).")
    _avant_modification(s, "informations")
    s["infos"].update(nouveaux)
    _sauver(s)
    _journaliser("informations", s, champs=sorted(nouveaux))
    return etat()


def commenter(texte: str) -> dict:
    s = _exiger()
    if not texte.strip():
        raise ValueError("Commentaire vide.")
    s["commentaires"].append({"date": _maintenant(), "auteur": _auteur(), "texte": texte.strip(), "version": s["version"]})
    _sauver(s)  # un commentaire ne modifie pas le contenu : pas de nouvelle version
    _journaliser("commentaire", s)
    return etat()


def valider_critere(eid: str, preuve: str) -> dict:
    """Validation manuelle d'un critère (mode « manuelle »), avec preuve ; journalisée."""
    s = _exiger()
    c = next((x for x in s["rubriques"]["criteres"] if x["id"] == eid), None)
    if not c:
        raise KeyError(f"Critère inconnu : {eid}")
    if c["verification"] != "manuelle":
        raise ValueError("Critère à vérification automatique : il se mesure, il ne se valide pas à la main (RG10).")
    if not preuve.strip():
        raise ValueError("Preuve obligatoire.")
    _sauver_suivi("criteres", eid, {"par": _auteur(), "date": _maintenant(), "preuve": preuve.strip(), "version": s["version"]})
    _journaliser("validation_critere", s, element=eid)  # suivi : la stratégie (et sa version publiée) n'est pas modifiée
    return etat()


def verifier_environnement(eid: str) -> dict:
    """Vérification de disponibilité (à la demande) : requête HTTP(S) ou présence du fichier local."""
    s = _exiger()
    env = next((x for x in s["rubriques"]["environnements"] if x["id"] == eid), None)
    if not env:
        raise KeyError(f"Environnement inconnu : {eid}")
    url = env.get("url") or ""
    if not url:
        r = {"resultat": "inconnu", "detail": "Aucune URL déclarée."}
    elif url.startswith(("http://", "https://")):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=5) as rep:
                r = {"resultat": "disponible", "detail": f"HTTP {rep.status}"}
        except Exception as e:  # noqa: BLE001 - toute erreur réseau = indisponible
            r = {"resultat": "indisponible", "detail": str(e)[:200]}
    else:
        chemin = url[7:] if url.startswith("file://") else url
        try:
            ok = projet.safe_path(chemin).exists()
        except Exception:
            ok = Path(chemin).exists()
        r = {"resultat": "disponible" if ok else "indisponible", "detail": "fichier local " + ("présent" if ok else "absent")}
    _sauver_suivi("environnements", eid, {**r, "date": _maintenant()})
    _journaliser("verification_environnement", s, element=eid, resultat=r["resultat"])
    return etat()


def importer_perimetre() -> dict:
    """Modules et exigences depuis l'instantané Xray / Jira (identifiants externes conservés, sans doublon)."""
    from atelier.intelligence import patrimoine_xray

    pat = patrimoine_xray.charger_vue()
    if not pat:
        raise FileNotFoundError("Aucun instantané Xray : l'importer d'abord (Rapports › Patrimoine Xray).")
    s = _exiger()
    _avant_modification(s, "import du périmètre")
    p = s["rubriques"]["perimetre"]
    modules = {x["nom"]: x for x in p if x["niveau"] == "module"}
    par_cle = {k: x for x in p for k in x.get("jira") or []}
    tests_par_exig: dict = {}
    for t in pat["tests"]:
        for e in t.get("exigences") or []:
            tests_par_exig.setdefault(e, []).append(t["cle"])
    vide = {c["nom"]: ([] if c["type"] in ("liste", "refs") else "") for c in PAR_ID["perimetre"]["champs"]}
    ajoutes = 0
    for nom in sorted({x.get("module") for x in pat["exigences"] + pat["tests"] if x.get("module")}):
        if nom not in modules:
            modules[nom] = {**vide, "id": f"per_{secrets.token_hex(3)}", "nom": nom, "niveau": "module", "inclus": True}
            p.append(modules[nom])
            ajoutes += 1
    for e in pat["exigences"]:
        x = par_cle.get(e["cle"])
        if x is None:
            x = {**vide, "id": f"per_{secrets.token_hex(3)}", "nom": f"{e['cle']} {e.get('resume') or ''}".strip(),
                 "niveau": "exigence", "inclus": True, "jira": [e["cle"]]}
            p.append(x)
            ajoutes += 1
        x["parent"] = modules[e["module"]]["id"] if e.get("module") in modules else x.get("parent", "")
        x["xray"] = sorted(set(x.get("xray") or []) | set(tests_par_exig.get(e["cle"], [])))
    _sauver(s)
    _journaliser("import_perimetre", s, ajoutes=ajoutes, source=pat.get("source", ""))
    return etat()


# =========================================================================== plan d'automatisation
def plan_automatisation() -> list[dict]:
    """Candidats calculés (couverture.candidats) + décision humaine enregistrée dans la stratégie."""
    from atelier.intelligence import couverture, patrimoine_xray

    pat = patrimoine_xray.charger_vue()
    if not pat:
        return []
    s = charger() or {"plan_automatisation": {}}
    out = []
    for c in couverture.candidats(_graphe(), pat):
        d = s["plan_automatisation"].get(c["cle"], {})
        statut = "Automatisé" if c["automatise"] else d.get("statut") or "À analyser"
        out.append({**c, "statut_plan": statut, "decision": d})
    return out


def decider_candidat(cle: str, statut: str, framework: str = "", effort: str = "", commentaire: str = "") -> dict:
    if statut not in DECISIONS_PLAN:
        raise ValueError(f"Statut de décision : {', '.join(DECISIONS_PLAN)} (« Recommandé par IA » est réservé à l'IA).")
    if statut == "Rejeté" and not commentaire.strip():
        raise ValueError("Un rejet doit être justifié.")
    s = _exiger()
    _avant_modification(s, f"plan d'automatisation {cle}")
    s["plan_automatisation"][cle] = {"statut": statut, "framework": framework, "effort": effort,
                                     "commentaire": commentaire.strip(), "par": _auteur(), "date": _maintenant()}
    _sauver(s)
    _journaliser("decision_plan", s, cle=cle, statut=statut)
    return etat()


# =========================================================================== contrôles et synthèse
def niveau_risque(r: dict) -> tuple[int, str]:
    try:
        score = int(r.get("probabilite") or 0) * int(r.get("impact") or 0)
    except ValueError:
        score = 0
    return score, "critique" if score >= 12 else "élevé" if score >= 8 else "moyen" if score >= 4 else "faible"


def completude(s: dict) -> dict:
    out = {}
    for r in RUBRIQUES:
        items = s["rubriques"][r["id"]]
        obl = [c["nom"] for c in r["champs"] if c["obligatoire"]]
        if not items:
            out[r["id"]] = 0
            continue
        ratio = sum(sum(1 for k in obl if x.get(k) not in ("", None, [])) / max(1, len(obl)) for x in items) / len(items)
        if r["id"] == "criteres" and {x["type"] for x in items} != {"entrée", "sortie"}:
            ratio = min(ratio, 0.5)  # il faut des critères d'entrée ET de sortie
        out[r["id"]] = round(100 * ratio)
    return out


def controles(s: dict) -> list[dict]:
    """Complétude, incohérences et liens cassés (gravité erreur = bloque la publication)."""
    ctl = []
    ids = {r["id"]: {x["id"] for x in s["rubriques"][r["id"]]} for r in RUBRIQUES}
    add = lambda g, rub, el, msg: ctl.append({"gravite": g, "rubrique": rub, "element": el, "message": msg})  # noqa: E731
    for r in RUBRIQUES:
        if not s["rubriques"][r["id"]]:
            add("avertissement", r["id"], "", f"Rubrique « {r['titre']} » vide.")
        for x in s["rubriques"][r["id"]]:
            for c in r["champs"]:
                vals = x.get(c["nom"]) if c["type"] == "refs" else [x.get(c["nom"])] if c["type"] == "ref" else []
                for v in vals or []:
                    if v and v not in ids.get(c["cible"], set()):
                        add("erreur", r["id"], x["id"], f"Lien cassé : « {c['libelle']} » vers un élément supprimé ({v}).")
    for o in s["rubriques"]["objectifs"]:
        if not o.get("indicateur") or o.get("cible") in ("", None):
            add("erreur", "objectifs", o["id"], f"Objectif « {o['nom']} » non mesurable (RG04).")
    for t in s["rubriques"]["types_tests"]:
        if t.get("actif") and t.get("automatisation_autorisee") and t.get("cible_auto") in ("", None):
            add("avertissement", "types_tests", t["id"], f"Type « {t['nom']} » : cible d'automatisation non définie.")
        if t.get("cible_auto") not in ("", None) and not t.get("automatisation_autorisee") and t["cible_auto"] > 0:
            add("erreur", "types_tests", t["id"], f"Type « {t['nom']} » : cible d'automatisation alors que l'automatisation n'est pas autorisée.")
    parts = [n.get("part_cible") or 0 for n in s["rubriques"]["niveaux"]]
    if parts and abs(sum(parts) - 100) > 0.5:
        add("avertissement", "niveaux", "", f"Parts cibles des niveaux : total {sum(parts):g} % (100 % attendu).")
    e2e = sum(n.get("part_cible") or 0 for n in s["rubriques"]["niveaux"] if n["nom"] == "End-to-End")
    if parts and sum(parts) and e2e / sum(parts) > 0.5:
        add("avertissement", "niveaux", "", "Stratégie trop centrée sur les tests End-to-End (plus de 50 %).")
    envs = s["rubriques"]["environnements"]
    if envs and not any(e.get("par_defaut") for e in envs):
        add("avertissement", "environnements", "", "Aucun environnement par défaut.")
    for e in envs:
        if e.get("type") == "PROD" and not e.get("usage"):
            add("avertissement", "environnements", e["id"], f"« {e['nom']} » (PROD) : préciser les vérifications autorisées.")
    types_crit = {c["type"] for c in s["rubriques"]["criteres"]}
    for t in ("entrée", "sortie"):
        if t not in types_crit:
            add("erreur", "criteres", "", f"Aucun critère de {t}.")
    for c in s["rubriques"]["criteres"]:
        if c["verification"] == "automatique" and (not c.get("indicateur") or c.get("seuil") in ("", None)):
            add("erreur", "criteres", c["id"], f"Critère « {c['description']} » : indicateur et seuil requis en vérification automatique.")
    for r in s["rubriques"]["risques"]:
        if niveau_risque(r)[1] in ("critique", "élevé") and not r.get("mitigation"):
            add("erreur", "risques", r["id"], f"Risque « {r['nom']} » ({niveau_risque(r)[1]}) sans plan de mitigation.")
    for p in s["rubriques"]["perimetre"]:
        if p.get("inclus") is False and not p.get("justification"):
            add("avertissement", "perimetre", p["id"], f"Exclusion de « {p['nom']} » non justifiée.")
    return ctl


def _statut_objectif(o: dict, m: dict) -> tuple:
    v = (m.get(o.get("indicateur")) or {}).get("valeur")
    ok = _evaluer(v, o.get("comparateur") or ">=", o.get("cible"))
    if ok is None:
        return v, "non mesurable"
    if ok:
        return v, "atteint"
    if o.get("echeance") and date.fromisoformat(o["echeance"]) < date.today():
        return v, "non atteint"
    return v, "en cours"


def criteres_evalues(s: dict, m: dict) -> list[dict]:
    out = []
    for c in s["rubriques"]["criteres"]:
        if c["verification"] == "automatique":
            v = (m.get(c.get("indicateur")) or {}).get("valeur")
            ok = _evaluer(v, c.get("comparateur") or ">=", c.get("seuil"))
            etat_c = "non mesurable" if ok is None else "satisfait" if ok else "non satisfait"
        else:
            v, etat_c = None, "satisfait" if c.get("validation") else "à valider"
        out.append({**c, "valeur": v, "etat": etat_c})
    return out


def criteres_entree_non_satisfaits() -> list[dict]:
    """Pour Execution Center : critères d'entrée obligatoires non satisfaits (avertissement avant un run)."""
    s = charger()
    if not s:
        return []
    return [c for c in criteres_evalues(s, mesures()) if c["type"] == "entrée" and c.get("obligatoire") and c["etat"] != "satisfait"]


def _couverture_exigences() -> dict | None:
    """Couverture du périmètre des exigences importé (couverture_exigences), ou None s'il n'a jamais été importé."""
    from atelier.intelligence import couverture_exigences

    try:
        c = couverture_exigences.calculer()
    except Exception:  # noqa: BLE001 — indicateur indisponible : repli sur l'instantané Xray
        return None
    return c if c["import"].get("date") and c["global"]["exigences"] else None


def synthese(s: dict, m: dict) -> dict:
    ru = s["rubriques"]
    objs = [{**o, "valeur": v, "etat": e} for o in ru["objectifs"] for v, e in [_statut_objectif(o, m)]]
    per = ru["perimetre"]
    inclus = [p for p in per if p.get("inclus") is not False]
    types = [t for t in ru["types_tests"] if t.get("actif")]
    cibles = [t["cible_auto"] for t in types if t.get("cible_auto") not in ("", None)]
    risques = {"critique": 0, "élevé": 0, "moyen": 0, "faible": 0}
    for r in ru["risques"]:
        if r.get("statut") != "Clos":
            risques[niveau_risque(r)[1]] += 1
    couverture = {"couvertes": None, "partielles": None, "non_couvertes": None, "definition":
                  "couverte : au moins un test lié ; partielle : des tests, mais un critère d'acceptation sans test ; non couverte : aucun test. "
                  "L'automatisation est un indicateur à part (Couverture et traçabilité)."}
    from atelier.intelligence import patrimoine_xray

    pat = patrimoine_xray.charger_vue()
    cx = _couverture_exigences()
    if cx:
        couverture.update(couvertes=cx["global"]["couvertes"] - cx["global"]["partielles"], partielles=cx["global"]["partielles"],
                          non_couvertes=cx["global"]["sans_test"])
    elif pat and pat.get("exigences"):
        g = _graphe()
        auto = {t["cle"] for t in pat["tests"] if (n := g.noeuds.get(f"test:{t['cle']}")) and n.proprietes.get("automatise")}
        par_exig: dict = {}
        for t in pat["tests"]:
            for e in t.get("exigences") or []:
                par_exig.setdefault(e, []).append(t["cle"])
        c = {"couvertes": 0, "partielles": 0, "non_couvertes": 0}
        for e in pat["exigences"]:
            ts = par_exig.get(e["cle"], [])
            c["non_couvertes" if not ts else "couvertes"] += 1  # existence ; l'automatisation n'est pas la couverture
        couverture.update(c)
    return {
        "objectifs": {"total": len(objs), **{k: sum(1 for o in objs if o["etat"] == k) for k in ("atteint", "en cours", "non atteint", "non mesurable")},
                      "liste": objs},
        "perimetre": {"modules": sum(1 for p in inclus if p["niveau"] == "module"),
                      "fonctionnalites": sum(1 for p in inclus if p["niveau"] == "fonctionnalite"),
                      "exigences": sum(1 for p in inclus if p["niveau"] == "exigence"),
                      "interfaces": sum(1 for p in inclus if p["niveau"] == "interface"),
                      "exclus": len(per) - len(inclus)},
        "types": {"total": len(types), "manuels": sum(1 for t in types if t["methode"] == "Manuelle"),
                  "automatises": sum(1 for t in types if t["methode"] == "Automatisée"),
                  "mixtes": sum(1 for t in types if t["methode"] == "Mixte"),
                  "cible_auto_moyenne": round(sum(cibles) / len(cibles), 1) if cibles else None},
        "couverture": couverture, "risques": risques,
        "indicateurs": {k: m[k] for k in ("couverture_fonctionnelle", "couverture_automatisee", "taux_reussite", "taux_instables", "duree_moyenne_run")},
    }


def etat() -> dict:
    """Tout ce qu'affiche l'écran Test Strategy (une seule source de données)."""
    s = charger()
    base = {"schema": RUBRIQUES, "indicateurs_disponibles": {k: v[0] for k, v in INDICATEURS.items()},
            "statuts": STATUTS, "libelles_statut": LIBELLES_STATUT, "decisions_plan": DECISIONS_PLAN, "statuts_plan": STATUTS_PLAN}
    if s is None:
        return {**base, "existe": False}
    m = mesures()
    for e in s["rubriques"]["risques"]:
        e["score"], e["niveau"] = niveau_risque(e)
    ctl = controles(s)
    return {**base, "existe": True, "strategie": s, "squads_a_reprendre": squads_a_reprendre(s), "completude": completude(s), "controles": ctl,
            "publiable": not any(c["gravite"] == "erreur" for c in ctl), "mesures": m,
            "synthese": synthese(s, m), "criteres": criteres_evalues(s, m), "versions": _index()}


# =========================================================================== workflow et versions
def transition(action: str, commentaire: str = "") -> dict:
    if action not in TRANSITIONS:
        raise ValueError(f"Action inconnue : {action}")
    s = _exiger()
    depart, arrivee = TRANSITIONS[action]
    if s["statut"] != depart:
        raise ValueError(f"« {action} » impossible depuis le statut {LIBELLES_STATUT[s['statut']]}.")
    if action in ("soumettre", "approuver", "publier"):
        bloquants = [c["message"] for c in controles(s) if c["gravite"] == "erreur"]
        if bloquants:
            raise ValueError("Contrôles bloquants : " + " ; ".join(bloquants[:6]))
    if action == "demander_modifications" and not commentaire.strip():
        raise ValueError("Préciser les modifications demandées.")
    if action == "approuver":
        s["approbation"] = {"par": _auteur(), "date": _maintenant(), "commentaire": commentaire.strip()}
    if action == "publier":
        f = _dossier() / "versions" / f"v{s['version']}.yaml"
        if f.exists():
            raise FileExistsError(f"La version {s['version']} est déjà publiée (jamais réécrite).")
        ix = _index()
        for v in ix:  # RG03 : une seule version publiée active
            if v["statut"] == "Published":
                v["statut"] = "Archived"
                v["remplacee_par"] = s["version"]
        instantane = {k: v for k, v in _sans_suivi(s).items() if k != "commentaires"}
        instantane["statut"] = "Published"
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("x", encoding="utf-8") as fh:  # création exclusive : jamais d'écrasement
            fh.write(yaml.safe_dump(instantane, allow_unicode=True, sort_keys=False))
        precedente = max((v["version"] for v in ix), default=None)
        ix.append({"version": s["version"], "statut": "Published", "date": _maintenant(), "auteur": _auteur(),
                   "approbateur": (s.get("approbation") or {}).get("par", ""), "commentaire": commentaire.strip(),
                   "modifications": _resume_diff(comparer(precedente, "courante")) if precedente else "Première version publiée."})
        _ecrire_index(ix)
    if action == "archiver":
        ix = _index()
        for v in ix:
            if v["version"] == s["version"]:
                v["statut"] = "Archived"
        _ecrire_index(ix)
    s["statut"] = arrivee
    if commentaire.strip():
        s["commentaires"].append({"date": _maintenant(), "auteur": _auteur(), "texte": f"[{action}] {commentaire.strip()}", "version": s["version"]})
    _sauver(s)
    _journaliser(action, s, commentaire=commentaire.strip())
    return etat()


def version(n: int) -> dict:
    f = _dossier() / "versions" / f"v{int(n)}.yaml"
    if not f.exists():
        raise KeyError(f"Version {n} inconnue.")
    return yaml.safe_load(f.read_text("utf-8"))


def _contenu(ref) -> dict:
    s = _exiger() if ref in (None, "", "courante") else version(int(ref))
    return {"infos": s["infos"], "rubriques": s["rubriques"], "plan_automatisation": s.get("plan_automatisation", {})}


def comparer(a, b="courante") -> dict:
    """Différences entre deux versions (numéro ou « courante ») : ajouts, suppressions, champs modifiés."""
    x, y = _contenu(a), _contenu(b)
    out = {"a": a, "b": b, "infos": {k: [x["infos"].get(k), y["infos"].get(k)] for k in set(x["infos"]) | set(y["infos"])
                                     if k != "modifie_le" and x["infos"].get(k) != y["infos"].get(k)}, "rubriques": {}}
    for r in RUBRIQUES:
        ax = {e["id"]: e for e in x["rubriques"].get(r["id"], [])}
        by = {e["id"]: e for e in y["rubriques"].get(r["id"], [])}
        titre = lambda e: e.get("nom") or e.get("description") or e["id"]  # noqa: E731
        d = {"ajoutes": [titre(by[i]) for i in by if i not in ax], "supprimes": [titre(ax[i]) for i in ax if i not in by],
             "modifies": [{"element": titre(by[i]), "champs": {k: [ax[i].get(k), by[i].get(k)] for k in set(ax[i]) | set(by[i])
                                                               if ax[i].get(k) != by[i].get(k)}}
                          for i in by if i in ax and ax[i] != by[i]]}
        if any(d.values()):
            out["rubriques"][r["id"]] = d
    pa, pb = x["plan_automatisation"], y["plan_automatisation"]
    plan = {k: [pa.get(k, {}).get("statut"), pb.get(k, {}).get("statut")] for k in set(pa) | set(pb)
            if pa.get(k, {}).get("statut") != pb.get(k, {}).get("statut")}
    if plan:
        out["plan_automatisation"] = plan
    return out


def _resume_diff(d: dict) -> str:
    parts = [f"{PAR_ID[r]['titre']} : +{len(v['ajoutes'])} / -{len(v['supprimes'])} / ~{len(v['modifies'])}" for r, v in d["rubriques"].items()]
    if d.get("plan_automatisation"):
        parts.append(f"plan d'automatisation : {len(d['plan_automatisation'])} décision(s)")
    if d["infos"]:
        parts.append("informations générales")
    return " ; ".join(parts) or "Aucune différence de contenu."


def restaurer(n: int) -> dict:
    """Recopie le contenu d'une version publiée dans la version de travail (historisé, rien n'est supprimé)."""
    v = version(n)
    s = _exiger()
    _avant_modification(s, f"restauration v{n}")
    s["rubriques"] = v["rubriques"]
    s["plan_automatisation"] = v.get("plan_automatisation", {})
    s["infos"].update({k: v["infos"][k] for k in ("nom", "application", "version_application", "responsable") if k in v["infos"]})
    _sauver(s)
    _journaliser("restauration", s, depuis_version=n)
    return etat()
