"""Construction BDD : scénario Gherkin représenté en graphe d'étapes, synchronisé avec le fichier .feature.

Stockage dans le projet de tests (versionné, relu en MR) :
  bdd/<clé>.feature   texte Gherkin (source de vérité textuelle, éditable à la main)
  bdd/<clé>.yaml      modèle : étapes, branches, liens (écran, locator, JDD, API), validations

Synchronisation dans les deux sens : toute modification du modèle réécrit le .feature ; un .feature
modifié à la main (plus récent que le .yaml) est relu et les liens sont conservés pour les étapes
dont le texte n'a pas changé.

Contrôles qualité (sans IA, vérifiables) : assertion manquante, donnée littérale dans un step (la
convention impose le JDD), étape non reliée à un écran, absence de branche négative, jeu de données
absent, étapes non validées, étape proche d'un keyword existant (réutiliser plutôt que créer un doublon).
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from pathlib import Path

import yaml

from atelier.domain import projet

MOTS = {
    "given": "given", "when": "when", "then": "then", "and": "and", "but": "but", "*": "and",
    "soit": "given", "étant donné": "given", "étant donnée": "given", "étant donnés": "given",
    "étant données": "given", "etant donne": "given", "sachant que": "given", "quand": "when",
    "lorsque": "when", "lorsqu'": "when", "alors": "then", "et": "and", "et que": "and", "mais": "but",
    "mais que": "but",
}
MOTS_EN = {"given": "Given", "when": "When", "then": "Then", "and": "And", "but": "But"}
MOTS_FR = {"given": "Étant donné", "when": "Quand", "then": "Alors", "and": "Et", "but": "Mais"}
TYPES_SCENARIO = ("principal", "alternatif", "negatif")
# Données littérales : nombres et texte entre guillemets doubles ou « ». Les apostrophes du français
# (« d'erreur », « s'affiche ») ne sont pas des délimiteurs.
LITTERAL = re.compile(r"\d[\d\s.,]*\d|\b\d+\b|\"[^\"]+\"|«[^»]+»")
_RE_ETAPE = re.compile(r"^\s*(" + "|".join(sorted((re.escape(m) for m in MOTS), key=len, reverse=True))
                       + r")\s+(.*)$", re.IGNORECASE)


def _dossier() -> Path:
    return projet.PROJECT_DIR / os.environ.get("BDD_DIR", "bdd")


def _slug(cle: str) -> str:
    return cle if re.match(r"^[A-Z][A-Z0-9_]+-\d+$", cle) else projet.slug(cle, 80, "scenario")


def _id() -> str:
    return "s" + uuid.uuid4().hex[:7]


def _etape(mot: str, texte: str, **kw) -> dict:
    t = MOTS.get(mot.strip().lower(), "and")
    return {"id": kw.get("id") or _id(), "mot": mot.strip(), "type": t, "texte": texte.strip(),
            "ecran": kw.get("ecran", ""), "locator": kw.get("locator", ""), "jdd": kw.get("jdd", ""),
            "api": kw.get("api", ""), "assertion": bool(kw.get("assertion", t == "then")),
            "valide": bool(kw.get("valide", False)), "resultat_attendu": kw.get("resultat_attendu", ""),
            **({"variable": kw["variable"]} if kw.get("variable") else {})}  # variable du référentiel Discovery utilisée pour ce champ


# =========================================================================== Gherkin <-> modèle
def parser(texte: str) -> dict:
    """Texte Gherkin -> modèle (Feature, Contexte, Scénarios, étapes)."""
    m = {"langue": "en", "feature": "", "description": [], "contexte": [], "scenarios": [], "tags": []}
    courant, tags_attente, exemples = None, [], None
    for brut in texte.splitlines():
        ligne = brut.strip()
        if not ligne:
            continue
        if exemples is not None and ligne.startswith("|"):  # lignes du tableau Examples, conservées telles quelles
            exemples.append(ligne)
            continue
        if ligne.startswith("#"):
            lg = re.match(r"#\s*language\s*:\s*(\w+)", ligne)
            if lg:
                m["langue"] = lg.group(1).lower()
            continue
        if ligne.startswith("@"):
            tags_attente += [t[1:] for t in ligne.split() if t.startswith("@")]
            continue
        cle, _, reste = ligne.partition(":")
        mot_cle = cle.strip().lower()
        if mot_cle in ("examples", "scenarios", "exemples") and _ and m["scenarios"]:
            exemples = m["scenarios"][-1].setdefault("exemples", [])
            courant = None
            continue
        exemples = None
        if mot_cle in ("feature", "fonctionnalité", "fonctionnalite") and _:
            m["feature"], m["tags"], tags_attente = reste.strip(), tags_attente, []
            courant = None
            continue
        if mot_cle in ("background", "contexte") and _:
            courant = m["contexte"]
            continue
        if mot_cle in ("scenario", "scénario", "scenario outline", "plan du scénario", "example", "exemple") and _:
            typ = "negatif" if "negatif" in tags_attente else "alternatif" if "alternatif" in tags_attente else (
                "principal" if not m["scenarios"] else "alternatif")
            sc = {"id": _id(), "nom": reste.strip(), "type": typ,
                  "tags": [t for t in tags_attente if t not in TYPES_SCENARIO], "etapes": [], "depuis": ""}
            if mot_cle in ("scenario outline", "plan du scénario"):
                sc["plan"] = True
            for t in tags_attente:
                if t.startswith("depuis:"):
                    sc["depuis"] = t.split(":", 1)[1]
            sc["tags"] = [t for t in sc["tags"] if not t.startswith("depuis:")]
            m["scenarios"].append(sc)
            courant, tags_attente = sc["etapes"], []
            continue
        e = _RE_ETAPE.match(ligne)
        if e and courant is not None:
            courant.append(_etape(e.group(1), e.group(2)))
        elif courant is None and m["feature"]:
            m["description"].append(ligne)
    _marquer_assertions(m)
    return m


def _marquer_assertions(m: dict):
    for bloc in [m["contexte"]] + [s["etapes"] for s in m["scenarios"]]:
        dernier = ""
        for e in bloc:
            if e["type"] in ("given", "when", "then"):
                dernier = e["type"]
            e["type_effectif"] = dernier or e["type"]
            if e["type_effectif"] == "then" and "assertion_auto" not in e:
                e["assertion"] = True


def serialiser(m: dict) -> str:
    """Modèle -> texte Gherkin (mots-clés dans la langue du scénario)."""
    mots = MOTS_FR if m.get("langue") == "fr" else MOTS_EN
    kw = {"feature": "Fonctionnalité", "contexte": "Contexte", "scenario": "Scénario"} if m.get("langue") == "fr" \
        else {"feature": "Feature", "contexte": "Background", "scenario": "Scenario"}
    out = []
    if m.get("langue") == "fr":
        out.append("# language: fr")
    if m.get("tags"):
        out.append(" ".join("@" + t for t in m["tags"]))
    out.append(f"{kw['feature']}: {m.get('feature') or m.get('titre') or ''}".rstrip())
    out += ["  " + d for d in m.get("description", [])]
    if m.get("contexte"):
        out += ["", f"  {kw['contexte']}:"] + [f"    {mots[e['type']]} {e['texte']}" for e in m["contexte"]]
    for sc in m.get("scenarios", []):
        tags = list(sc.get("tags", []))
        if sc.get("type") in ("negatif", "alternatif"):
            tags.append(sc["type"])
        if sc.get("depuis"):
            tags.append(f"depuis:{sc['depuis']}")
        out.append("")
        if tags:
            out.append("  " + " ".join("@" + t for t in tags))
        plan = sc.get("plan") or bool(sc.get("exemples"))
        titre = ("Plan du scénario" if m.get("langue") == "fr" else "Scenario Outline") if plan else kw["scenario"]
        out.append(f"  {titre}: {sc['nom']}")
        out += [f"    {mots[e['type']]} {e['texte']}" for e in sc["etapes"]]
        if sc.get("exemples"):
            out += ["", f"    {'Exemples' if m.get('langue') == 'fr' else 'Examples'}:"] + [f"      {l}" for l in sc["exemples"]]
    return "\n".join(out) + "\n"


def _fusionner_liens(nouveau: dict, ancien: dict) -> dict:
    """Conserve les liens et validations des étapes dont le texte est inchangé."""
    par_texte = {(e["type"], e["texte"]): e for s in ancien.get("scenarios", []) for e in s["etapes"]}
    par_texte.update({(e["type"], e["texte"]): e for e in ancien.get("contexte", [])})
    for e in nouveau["contexte"] + [x for s in nouveau["scenarios"] for x in s["etapes"]]:
        a = par_texte.get((e["type"], e["texte"]))
        if a:
            for k in ("id", "ecran", "locator", "jdd", "api", "valide", "resultat_attendu", "assertion"):
                e[k] = a.get(k, e[k])
            for k in ("keyword_nouveau", "jugement_keyword", "variable"):
                if a.get(k):
                    e[k] = a[k]
    for k in ("cle", "titre", "jdd", "source", "statut", "test_robot"):
        if k in ancien and k not in nouveau:
            nouveau[k] = ancien[k]
    return nouveau


# =========================================================================== stockage
def _fichiers(cle: str) -> tuple[Path, Path]:
    d = _dossier()
    s = _slug(cle)
    return d / f"{s}.feature", d / f"{s}.yaml"


def lister() -> list[dict]:
    d = _dossier()
    out = []
    for f in sorted(d.glob("*.yaml")) if d.exists() else []:
        m = yaml.safe_load(f.read_text("utf-8")) or {}
        out.append({"cle": m.get("cle", f.stem), "titre": m.get("titre", ""), "statut": m.get("statut", "brouillon"),
                    "scenarios": len(m.get("scenarios", [])), "maj": m.get("maj", "")})
    return out


def charger(cle: str) -> dict | None:
    feat, meta = _fichiers(cle)
    if not meta.exists() and not feat.exists():
        return None
    m = yaml.safe_load(meta.read_text("utf-8")) if meta.exists() else {}
    if feat.exists() and (not meta.exists() or feat.stat().st_mtime > meta.stat().st_mtime + 0.5):
        m = _fusionner_liens(parser(feat.read_text("utf-8")), m or {})  # .feature édité à la main
        m.setdefault("cle", cle)
        sauver(m, auteur="fichier .feature")
    return m


def sauver(m: dict, auteur: str = "automaticien") -> dict:
    if not m.get("cle"):
        raise ValueError("Clé du scénario obligatoire.")
    _marquer_assertions(m)
    for sc in m.get("scenarios", []):
        if sc.get("type") not in TYPES_SCENARIO:
            raise ValueError(f"Type de scénario inconnu : {sc.get('type')}")
    m["maj"] = datetime.now().astimezone().isoformat(timespec="seconds")
    if any(not e.get("valide") for s in m.get("scenarios", []) for e in s["etapes"]):
        m["statut"] = "brouillon"
    feat, meta = _fichiers(m["cle"])
    feat.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(yaml.safe_dump(m, allow_unicode=True, sort_keys=False, width=120), "utf-8")
    feat.write_text(serialiser(m), "utf-8")
    os.utime(meta)  # le modèle est la version la plus récente
    from atelier.domain import declarations

    declarations._historiser("bdd_sauvegarde", auteur, f"bdd:{m['cle']}", apres={"statut": m.get("statut")})
    return m


def depuis_texte(cle: str, texte: str) -> dict:
    """Gherkin saisi dans la prévisualisation -> modèle (liens conservés)."""
    m = _fusionner_liens(parser(texte), charger(cle) or {})
    m["cle"] = cle
    return sauver(m)


def creer(cle: str, titre: str = "", depuis_xray: dict | None = None, jdd: str = "") -> dict:
    """Nouveau scénario : depuis le Gherkin Xray (test Cucumber), depuis les étapes manuelles Xray
    (action -> Quand, résultat attendu -> Alors), ou vide."""
    if charger(cle):
        raise FileExistsError(f"Le scénario {cle} existe déjà.")
    x = depuis_xray or {}
    if x.get("gherkin"):
        m = parser(x["gherkin"] if re.search(r"(?im)^\s*(feature|fonctionnalit)", x["gherkin"])
                   else f"Feature: {titre or x.get('resume', cle)}\n  Scenario: {titre or x.get('resume', cle)}\n"
                   + x["gherkin"])
        m["source"] = "xray (gherkin)"
    elif x.get("etapes"):
        m = {"langue": "fr", "feature": titre or x.get("resume") or cle, "description": [], "contexte": [], "tags": [],
             "scenarios": [{"id": _id(), "nom": titre or x.get("resume") or cle, "type": "principal", "tags": [],
                            "depuis": "", "etapes": []}], "source": "xray (étapes manuelles)"}
        et = m["scenarios"][0]["etapes"]
        for i, s in enumerate(x["etapes"]):
            if s.get("action"):
                et.append(_etape("Quand" if i else "Étant donné", s["action"].strip()))
            if s.get("result"):
                et.append(_etape("Alors", s["result"].strip(), resultat_attendu=s["result"].strip()))
    else:
        m = {"langue": "fr", "feature": titre or cle, "description": [], "contexte": [], "tags": [], "source": "nouveau",
             "scenarios": [{"id": _id(), "nom": titre or cle, "type": "principal", "tags": [], "depuis": "", "etapes": []}]}
    m.update(cle=cle, titre=titre or x.get("resume") or m.get("feature") or cle, jdd=jdd, statut="brouillon")
    return sauver(m)


# =========================================================================== édition
def _trouver(m: dict, etape_id: str) -> tuple[list, int]:
    for bloc in [m["contexte"]] + [s["etapes"] for s in m["scenarios"]]:
        for i, e in enumerate(bloc):
            if e["id"] == etape_id:
                return bloc, i
    raise KeyError(f"Étape inconnue : {etape_id}")


def _scenario(m: dict, sid: str) -> dict:
    for s in m["scenarios"]:
        if s["id"] == sid:
            return s
    raise KeyError(f"Scénario inconnu : {sid}")


def ajouter_etape(cle: str, scenario: str, mot: str, texte: str, apres: str = "") -> dict:
    m = _exiger(cle)
    et = _scenario(m, scenario)["etapes"]
    e = _etape(mot, texte)
    pos = next((i + 1 for i, x in enumerate(et) if x["id"] == apres), len(et))
    et.insert(pos, e)
    return sauver(m)


def modifier_etape(cle: str, etape_id: str, **champs) -> dict:
    m = _exiger(cle)
    bloc, i = _trouver(m, etape_id)
    e = bloc[i]
    if "mot" in champs:
        e["mot"] = champs["mot"]
        e["type"] = MOTS.get(champs["mot"].strip().lower(), e["type"])
    if champs.get("texte") is not None and champs["texte"].strip() != e["texte"]:
        e.pop("keyword_nouveau", None)  # nouveau texte : le rapprochement avec le socle est à refaire
        e.pop("jugement_keyword", None)
        if champs.get("valide") is None:
            e["valide"] = False  # texte modifié : à revalider
    for k in ("texte", "ecran", "locator", "jdd", "api", "resultat_attendu"):
        if k in champs and champs[k] is not None:
            e[k] = str(champs[k]).strip()
    for k in ("assertion", "valide"):
        if k in champs and champs[k] is not None:
            e[k] = bool(champs[k])
    if "assertion" in champs:
        e["assertion_auto"] = False
    if champs.get("keyword_nouveau") is not None:  # décision humaine : cette étape demande bien un nouveau keyword
        if champs["keyword_nouveau"]:
            e["keyword_nouveau"] = True
        else:
            e.pop("keyword_nouveau", None)
    return sauver(m)


def supprimer_etape(cle: str, etape_id: str) -> dict:
    m = _exiger(cle)
    bloc, i = _trouver(m, etape_id)
    bloc.pop(i)
    return sauver(m)


def deplacer_etape(cle: str, etape_id: str, sens: int) -> dict:
    m = _exiger(cle)
    bloc, i = _trouver(m, etape_id)
    j = max(0, min(len(bloc) - 1, i + (1 if sens > 0 else -1)))
    bloc.insert(j, bloc.pop(i))
    return sauver(m)


def ajouter_branche(cle: str, depuis: str, nom: str, type_branche: str = "negatif", etapes: list | None = None) -> dict:
    """Branche alternative ou négative qui part d'une étape du scénario principal : elle reprend les
    étapes précédentes (contexte commun) puis ses propres étapes."""
    if type_branche not in ("alternatif", "negatif"):
        raise ValueError("Une branche est « alternatif » ou « negatif ».")
    m = _exiger(cle)
    bloc, i = _trouver(m, depuis)
    communes = [_etape(e["mot"], e["texte"], ecran=e["ecran"], locator=e["locator"], jdd=e["jdd"],
                       valide=e["valide"]) for e in bloc[: i + 1]]
    propres = [_etape(x.get("mot", "Et"), x["texte"]) for x in (etapes or [])]
    m["scenarios"].append({"id": _id(), "nom": nom, "type": type_branche, "tags": [], "depuis": depuis,
                           "etapes": communes + propres})
    return sauver(m)


def supprimer_scenario(cle: str, sid: str) -> dict:
    m = _exiger(cle)
    sc = _scenario(m, sid)
    if sc["type"] == "principal":
        raise ValueError("Le scénario principal ne se supprime pas.")
    m["scenarios"].remove(sc)
    return sauver(m)


def valider(cle: str) -> dict:
    """Validation humaine du scénario : refusée si un contrôle de gravité haute subsiste."""
    m = _exiger(cle)
    bloquants = [c for c in controles(m) if c["gravite"] == "haute"]
    if bloquants:
        raise ValueError("Validation impossible : " + " ; ".join(c["message"] for c in bloquants))
    for s in m["scenarios"]:
        for e in s["etapes"]:
            e["valide"] = True
    m["statut"] = "validé"
    return sauver(m)


def _exiger(cle: str) -> dict:
    m = charger(cle)
    if not m:
        raise KeyError(f"Scénario {cle} introuvable : le créer d'abord.")
    return m


# =========================================================================== réutilisation du socle
def reutilisation(m: dict, inventaire: dict | None = None) -> dict:
    """Rapprochement de chaque étape avec les keywords du dépôt : {id d'étape: existant | proche | à créer, keyword,
    keywords proches, jugement}. Une étape est « proche » quand les mots, ou le jugement d'une IA (verdict « réutiliser »),
    désignent un keyword existant ; elle redevient « à créer » quand l'automaticien confirme un nouveau keyword. Décisions
    et jugements valent pour toutes les étapes de même texte (une branche reprend les étapes communes)."""
    from atelier.execution.depot_robot import normaliser
    from atelier.generation.reutilisation import Rapprocheur

    etapes = m.get("contexte", []) + [x for s in m.get("scenarios", []) for x in s["etapes"]]
    confirmes = {e["texte"] for e in etapes if e.get("keyword_nouveau")}
    juges = {e["texte"]: e["jugement_keyword"] for e in etapes if e.get("jugement_keyword")}
    r, out = Rapprocheur(inventaire), {}
    for e in etapes:
        x = r.etape(e["texte"])
        j = juges.get(e["texte"])
        if j and x["statut"] != "existant":
            x["jugement"] = j
            kid = r.exact.get(normaliser(j.get("keyword") or "")) if j.get("verdict") == "réutiliser" else None
            if kid:  # le keyword jugé équivalent passe en tête des propositions
                x.update(statut="proche", proches=[{**r._fiche(kid), "juge": True}] + [p for p in x["proches"] if p["id"] != kid])
        if x["statut"] == "proche" and e["texte"] in confirmes:
            x.update(statut="à créer", confirme=True)
        out[e["id"]] = x
    return out


def _doublons_possibles(m: dict, inventaire: dict | None = None) -> list[dict]:
    """Étapes proches d'un keyword existant, sans décision : générer leur keyword créerait un doublon probable."""
    r = reutilisation(m, inventaire)
    vus, out = set(), []
    for e in m.get("contexte", []) + [x for s in m.get("scenarios", []) for x in s["etapes"]]:
        x = r[e["id"]]
        if x["statut"] == "proche" and e["texte"] not in vus:
            vus.add(e["texte"])
            out.append({"etape": e["id"], "texte": e["texte"], "keyword": x["proches"][0]["keyword"],
                        "fichier": x["proches"][0]["fichier"], "proches": x["proches"],
                        "jugement": x["jugement"] if x["proches"][0].get("juge") else None})
    return out


def refuser_doublons(m: dict, inventaire: dict | None = None) -> None:
    """Garde avant d'écrire la suite Robot : refuse tant qu'une étape proche d'un keyword existant n'est pas tranchée
    (reprendre le keyword, ou confirmer le nouveau keyword dans Test Design)."""
    d = _doublons_possibles(m, inventaire)
    if d:
        raise ValueError("Écriture refusée : " + " ; ".join(
            f"« {x['texte']} » " + (f"fait la même action que le keyword existant « {x['keyword']} » selon {x['jugement']['source']} "
                                    if x["jugement"] else f"ressemble au keyword existant « {x['keyword']} » ") + f"({x['fichier']})"
            for x in d[:5])
                         + ". Dans Test Design, reprendre le keyword existant ou confirmer qu'un nouveau keyword est nécessaire.")


# =========================================================================== contrôles et statistiques
def controles(m: dict) -> list[dict]:
    out = []

    def c(gravite, code, message, etape=""):
        out.append({"gravite": gravite, "code": code, "message": message, "etape": etape})
    if not m.get("scenarios"):
        c("haute", "vide", "Aucun scénario.")
    for s in m.get("scenarios", []):
        if not s["etapes"]:
            c("haute", "scenario_vide", f"Scénario « {s['nom']} » sans étape.")
            continue
        if not any(e.get("assertion") for e in s["etapes"]):
            c("haute", "assertion_manquante", f"Scénario « {s['nom']} » : aucun résultat vérifié (étape Alors / assertion).")
        for e in s["etapes"]:
            if LITTERAL.search(e["texte"]):
                c("moyenne", "donnee_litterale", f"Donnée littérale dans « {e['texte']} » : la passer par le jeu de données.",
                  e["id"])
            if e.get("type_effectif", e["type"]) == "when" and not e.get("ecran"):
                c("basse", "ecran_non_relie", f"« {e['texte']} » n'est reliée à aucun écran de la carte.", e["id"])
    try:  # rapprochement avec le socle : un dépôt illisible ne masque pas les autres contrôles
        for d in _doublons_possibles(m):
            if d["jugement"]:
                c("moyenne", "keyword_proche", f"« {d['texte']} » fait la même action que le keyword existant « {d['keyword']} » "
                  f"({d['fichier']}) selon {d['jugement']['source']} : {d['jugement']['justification']} — le reprendre, ou "
                  "confirmer un nouveau keyword.", d["etape"])
            else:
                c("moyenne", "keyword_proche", f"« {d['texte']} » ressemble au keyword existant « {d['keyword']} » "
                  f"({d['fichier']}) : reprendre son libellé pour le réutiliser, ou confirmer un nouveau keyword.", d["etape"])
        rap = reutilisation(m)
        nj = len({e["texte"] for s in m.get("scenarios", []) for e in s["etapes"]
                  if rap[e["id"]]["statut"] == "à créer" and not rap[e["id"]].get("confirme") and not rap[e["id"]].get("jugement")})
        if nj:
            c("info", "keywords_a_juger", f"{nj} étape(s) sans keyword existant d'après les mots : faire vérifier par l'IA "
              "qu'aucun keyword du socle ne fait déjà la même action (synonyme, reformulation).")
    except Exception:  # noqa: BLE001
        pass
    if m.get("scenarios") and not any(s["type"] == "negatif" for s in m["scenarios"]):
        c("info", "branche_negative", "Aucune branche négative : en ajouter une pour couvrir les cas d'erreur.")
    if not m.get("jdd"):
        c("moyenne", "jdd_absent", "Aucun jeu de données associé (bloc INITIALISATION).")
    nv = sum(1 for s in m.get("scenarios", []) for e in s["etapes"] if not e.get("valide"))
    if nv:
        c("info", "non_valide", f"{nv} étape(s) non validée(s).")
    ordre = {"haute": 0, "moyenne": 1, "basse": 2, "info": 3}
    return sorted(out, key=lambda x: ordre[x["gravite"]])


def statistiques(m: dict) -> dict:
    principal = next((s for s in m.get("scenarios", []) if s["type"] == "principal"), None)
    etapes = [e for s in m.get("scenarios", []) for e in s["etapes"]]
    return {"etapes": len(principal["etapes"]) if principal else 0,
            "branches": sum(1 for s in m.get("scenarios", []) if s["type"] != "principal"),
            "assertions": sum(1 for e in etapes if e.get("assertion")),
            "etapes_validees": sum(1 for e in etapes if e.get("valide")), "etapes_total": len(etapes),
            "ecrans_relies": sum(1 for e in etapes if e.get("ecran"))}


# =========================================================================== génération Robot
def generer_robot(m: dict, inventaire: dict | None = None, cible: str = "") -> dict:
    """Suite Robot qui suit les conventions : INITIALISATION (Initialiser Le Test + &{JDD_<NOM>}) puis
    les étapes BDD. Chaque étape est rapprochée d'un keyword existant du dépôt (réutilisation) ;
    sinon un keyword à implémenter est déclaré (il échoue explicitement, jamais en silence).
    Une suite par parcours métier (suites_parcours.py) : si le test appartient à un parcours qui a déjà sa suite,
    « ajout » est vrai et « contenu » est la suite existante complétée (rien n'y est réécrit) ; « ajoute » porte la
    partie nouvelle. cible : chemin imposé par l'appelant (aucun ajout : le fichier ne doit pas exister)."""
    from atelier.execution import depot_robot

    inv = inventaire if inventaire is not None else depot_robot.lire_depot()
    kws = inv["keywords"]
    rapprochement, confirmes = reutilisation(m, inv), set()  # mots, jugement d'une IA et décisions de l'automaticien
    a_creer, reutilises, resources, proches, ecran_de = [], [], set(), {}, {}
    lignes_tests = []
    from atelier.generation import conception

    # le tag est la clé du test Xray : celle créée à la publication du scénario, sinon la clé du scénario
    cle_xray = conception.cle_xray_du_scenario(m["cle"])
    for s in m["scenarios"]:
        tags = [cle_xray or m["cle"]] + (["negatif"] if s["type"] == "negatif" else [])
        lignes_tests += ["", s["nom"], f"    [Tags]    {'    '.join(tags)}"]
        if m.get("jdd"):
            lignes_tests.append(f"    Initialiser Le Test    &{{JDD_{m['jdd'].upper()}}}")
        for e in s["etapes"]:
            prefixe = MOTS_EN[e["type"]]
            x = rapprochement[e["id"]]
            if x["statut"] == "existant":  # même nom, ou keyword à arguments intégrés : Robot résout l'appel tel quel
                reutilises.append(x["keyword"])
                resources.add(kws[x["id"]]["fichier"])
            elif e["texte"] not in a_creer:
                a_creer.append(e["texte"])
                ecran_de[e["texte"]] = e.get("ecran") or ""
                if x["proches"]:
                    proches[e["texte"]] = x["proches"]
            if x.get("confirme"):
                confirmes.add(e["texte"])
            lignes_tests.append(f"    {prefixe} {e['texte']}")
    if m.get("jdd"):
        if "initialiserletest" in kws:
            resources.add(kws["initialiserletest"]["fichier"])
        else:
            a_creer.insert(0, "Initialiser Le Test")
    from atelier.generation import suites_parcours

    # la suite du parcours métier du test (existante : ajout), sinon tests/{application}/{module}/{scenario}.robot (réglable)
    choix = ({"chemin": cible.replace("\\", "/"), "ajout": False, "parcours": "", "raison": "Chemin choisi par l'appelant."} if cible
             else suites_parcours.cible(m, inv))
    cible = choix["chemin"]
    # Page Object Model, toujours : les keywords à implémenter vont dans la page de leur écran, jamais dans la suite
    from atelier.generation import pom

    a_ecrire = []
    for k in a_creer:
        doc = "À implémenter : aucun keyword du dépôt ne correspond."
        if k in proches:
            doc = (f"À implémenter (nouveau keyword confirmé ; proche de « {proches[k][0]['keyword']} »)." if k in confirmes
                   else f"Doublon probable de « {proches[k][0]['keyword']} » ({proches[k][0]['fichier']}) : le réutiliser.")
        a_ecrire.append({"nom": k, "doc": doc, "ecran": ecran_de.get(k, ""),
                         "args": ["    [Arguments]    &{jdd}"] if k == "Initialiser Le Test" else []})
    fin = next((kws[k] for k in ("terminerletest", "finaliserletest", "cloturerletest", "fermerletest") if k in kws), None)
    if fin:  # Test Teardown du socle : capture si échec, fermeture propre (style professionnel)
        resources.add(fin["fichier"])
    socle = (kws.get("initialiserletest") or kws.get("localiser") or {}).get("fichier", "")
    prep = pom.preparer(a_ecrire, inv, cible, socle if str(socle).endswith(".resource") else "",
                        projet.slug(m.get("module") or m.get("titre") or m["cle"], 50, "general"))
    imports = [f"Resource    {Path(os.path.relpath(projet.PROJECT_DIR / r, (projet.PROJECT_DIR / cible).parent)).as_posix()}"
               for r in sorted(resources | set(prep["imports"])) if r.endswith(".resource")]
    texte = ["*** Settings ***",
             f"Documentation    {m.get('titre') or m['cle']} — généré depuis le scénario BDD {m['cle']} le "
             f"{datetime.now():%d/%m/%Y} (à relire). Page Object Model : les keywords sont dans les pages importées.",
             *imports, *([f"Test Teardown    {fin['nom']}"] if fin else []), "", "*** Test Cases ***", *lignes_tests[1:]]
    out = {"chemin": cible, "contenu": "\n".join(texte).rstrip() + "\n", "keywords_reutilises": sorted(set(reutilises)),
           "keywords_a_creer": a_creer,
           "keywords_proches": [{"etape": k, "keyword": p[0]["keyword"], "fichier": p[0]["fichier"], "confirme": k in confirmes}
                                for k, p in proches.items()],
           "pages": prep["pages"], "pom": True,
           "parcours": choix["parcours"], "ajout": False, "raison_suite": choix["raison"], "cle_xray": cle_xray,
           "tag": cle_xray or m["cle"]}
    if choix["ajout"]:  # la suite du parcours existe : on y ajoute le test, sans rien réécrire
        try:
            a = suites_parcours.ajouter(projet.lire_fichier(cible), out["contenu"])
            out.update(ajout=True, ajoute=out["contenu"], contenu=a["contenu"], tests_ajoutes=a["tests"])
        except (FileExistsError, ValueError, RuntimeError) as e:
            out["ajout_refuse"] = str(e)
    return out


def ecrire_generation(m: dict, g: dict, remplacer: bool = False, origine: str = "cursor") -> dict:
    """Écrit ce que generer_robot a préparé : la suite (création, ajout à la suite du parcours, ou remplacement) et
    les pages (Page Object Model), puis met la suite en revue.

    Une suite existante n'est jamais écrasée implicitement. Elle n'est remplacée que si l'appelant le demande
    (remplacer=True) ET qu'elle ne contient que ce test (régénération, ex. passage en Page Object Model) ; l'ancienne
    version est alors sauvegardée dans studio/remplaces/. Si elle contient d'autres tests, elle n'est jamais remplacée."""
    from atelier.execution import depot_robot
    from atelier.generation import pom, studio

    refuser_doublons(m)  # étape proche d'un keyword existant : à trancher avant d'écrire
    cible = g["chemin"]
    if g.get("ajout_refuse"):
        raise FileExistsError(g["ajout_refuse"])
    existe = projet.safe_path(cible).exists()
    g["sauvegarde"] = ""
    if existe and not g.get("ajout"):
        inv = depot_robot.lire_depot()
        cles = {m["cle"], g.get("cle_xray") or ""} - {""}
        autres = [t["nom"] for t in inv["tests"].values() if t["fichier"] == cible and not cles & set(t.get("tags") or [])]
        if autres:
            raise FileExistsError(f"{cible} existe et contient d'autres tests ({', '.join(autres[:4])}) : elle n'est pas remplacée. "
                                  "Choisir un autre chemin, ou rattacher le test au parcours métier de cette suite pour l'y ajouter.")
        if not remplacer:
            raise FileExistsError(f"Le test {m['cle']} existe déjà dans {cible} (généré avant). Pour le régénérer (Page Object "
                                  "Model compris) : remplacer=True (studio_generer_depuis_bdd), ou « Remplacer s'il existe » dans "
                                  "l'atelier ; l'ancienne version est sauvegardée.")
        dossier = studio._dossier() / "remplaces"
        dossier.mkdir(parents=True, exist_ok=True)
        copie = dossier / f"{datetime.now():%Y%m%d-%H%M%S}__{cible.replace('/', '__')}"
        copie.write_text(projet.lire_fichier(cible), "utf-8")
        g["sauvegarde"] = copie.relative_to(projet.PROJECT_DIR).as_posix()
    projet.ecrire_fichier(cible, g["contenu"], existe)  # ajout (contenu complété) ou remplacement autorisé ci-dessus
    g["pages_ecrites"] = pom.ecrire(g.get("pages") or [])
    studio.entrer_en_revue(cible, origine)  # validation humaine avant exécution
    g["ecrit"] = cible
    return g


def associer_module(cle: str, module: str) -> dict:
    """Module du scénario : range le test Robot (tests/{application}/{module}/) et le test Xray (dossier du module)."""
    m = _exiger(cle)
    m["module"] = module.strip()
    return sauver(m)


def associer_jdd(cle: str, jdd: str) -> dict:
    m = _exiger(cle)
    m["jdd"] = jdd.strip()
    return sauver(m)
