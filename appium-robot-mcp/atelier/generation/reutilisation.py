"""Réutilisation des keywords du dépôt dès la rédaction des étapes BDD (sans IA, vérifiable).

Une étape BDD devient un appel de keyword Robot. Pour ne pas créer de doublon, chaque étape est rapprochée des
keywords déjà définis dans le dépôt (.robot et .resource) :

  existant   le texte désigne un keyword du dépôt : même nom (casse, espaces et _ ignorés, préfixe BDD et « que »
             retirés) ou keyword à arguments intégrés (« Saisir Le Montant ${montant} ») ;
  proche     aucun keyword de ce nom, mais un keyword existant emploie les mêmes mots (« je valide le virement » /
             « Valider Le Virement ») : reprendre son libellé évite un doublon ;
  à créer    rien d'approchant : un keyword sera à implémenter.

« proche » ne compare que des mots (présélection) : la décision reste humaine — reprendre le keyword proposé, ou
confirmer que l'étape demande bien un nouveau keyword.
"""
from __future__ import annotations

import re
import unicodedata

from atelier.execution.depot_robot import EXCLUS, cle_appel, lire_depot, normaliser

SEUIL_PROCHE = 0.6
VARIABLE = re.compile(r"[$@&]\{[^}]*\}")
# Mots sans portée métier. Les négations (ne, pas, non, sans, aucun) sont gardées : elles changent le sens.
MOTS_VIDES = frozenset("""a au aux avec ce ces cet cette dans de des du elle en est et il je la le les leur lui ma mes
mon nous on ou par pour qu que qui sa se ses son sont suis sur un une vous y the an and i is are of on to in my that""".split())
_cache: dict = {}


def mots(texte: str) -> frozenset:
    """Mots significatifs d'un libellé : sans variable, accent ni mot vide, ramenés à leur radical (5 lettres)."""
    t = unicodedata.normalize("NFD", VARIABLE.sub(" ", texte).replace("_", " ").casefold())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return frozenset(m[:5] for m in re.findall(r"[a-z0-9]+", t) if len(m) > 1 and m not in MOTS_VIDES)


def _variantes(texte: str) -> list[str]:
    t = " ".join(texte.split())
    return list(dict.fromkeys([t, re.sub(r"(?i)^(que\s+|qu')\s*", "", t)]))


def _motif(nom: str):
    """Keyword à arguments intégrés -> expression qui reconnaît ses appels (comme le fait Robot)."""
    morceaux = VARIABLE.split(" ".join(nom.split()))
    if len(morceaux) < 2 or not "".join(morceaux).strip():
        return None
    return re.compile(r"(.+?)".join(re.escape(x).replace(r"\ ", r"\s+") for x in morceaux), re.IGNORECASE)


def inventaire() -> dict:
    """Inventaire du dépôt, relu seulement si un fichier .robot / .resource a changé."""
    from atelier.domain import projet

    racine = projet.PROJECT_DIR.resolve()
    empreinte = tuple(sorted((p.as_posix(), p.stat().st_mtime_ns, p.stat().st_size)
                             for ext in ("*.robot", "*.resource") for p in racine.rglob(ext)
                             if not (set(p.relative_to(racine).parts) & EXCLUS)))
    if _cache.get("cle") != (racine, empreinte):
        _cache.update(cle=(racine, empreinte), inv=lire_depot(racine))
    return _cache["inv"]


class Rapprocheur:
    """Rapproche des textes d'étape des keywords d'un inventaire (lire_depot)."""

    def __init__(self, inv: dict | None = None):
        self.kws = (inv if inv is not None else inventaire())["keywords"]
        self.exact, self.motifs, self.mots = {}, [], {}
        for kid, k in self.kws.items():
            for c in (kid, normaliser(k["nom"]), cle_appel(k["nom"])):
                self.exact.setdefault(c, kid)
            motif = _motif(k["nom"])
            if motif:
                self.motifs.append((motif, kid))
            self.mots[kid] = mots(k["nom"])

    def _fiche(self, kid: str, score: float | None = None) -> dict:
        k = self.kws[kid]
        f = {"keyword": k["nom"], "id": kid, "fichier": f"{k['fichier']}:{k['ligne']}", "documentation": k.get("doc", "")}
        return f if score is None else {**f, "score": round(score, 2)}

    def proches(self, texte: str, limite: int = 3, seuil: float = SEUIL_PROCHE) -> list[dict]:
        """Keywords existants qui emploient les mêmes mots que le texte, du plus ressemblant au moins ressemblant."""
        m = mots(texte)
        if not m:
            return []
        scores = [(len(m & km) / len(m | km), kid) for kid, km in self.mots.items() if km and m & km]
        return [self._fiche(kid, s) for s, kid in sorted(scores, key=lambda x: (-x[0], x[1])) if s >= seuil][:limite]

    def etape(self, texte: str) -> dict:
        """Statut d'une étape : existant (keyword réutilisé), proche (keyword à reprendre) ou à créer."""
        vide = {"keyword": "", "id": "", "fichier": "", "documentation": "", "correspondance": ""}
        for t in _variantes(texte):
            kid = self.exact.get(normaliser(t)) or self.exact.get(cle_appel(t))
            if kid:
                return {"statut": "existant", **self._fiche(kid), "correspondance": "nom", "proches": []}
        for t in _variantes(texte):
            for motif, kid in self.motifs:
                if motif.fullmatch(t):
                    return {"statut": "existant", **self._fiche(kid), "correspondance": "arguments intégrés", "proches": []}
        p = self.proches(texte)
        return {"statut": "proche" if p else "à créer", **vide, "proches": p}

    def catalogue(self) -> list[dict]:
        """Keywords du dépôt proposés à la saisie d'une étape (nom, documentation, fichier)."""
        return sorted((self._fiche(kid) for kid in self.kws), key=lambda x: x["keyword"].casefold())


def rapprocher_etapes(textes: list[str], inv: dict | None = None) -> dict:
    """Rapprochement d'une liste d'étapes (avec ou sans mot Gherkin) et bilan : à faire AVANT de rédiger un scénario."""
    r = Rapprocheur(inv)
    etapes = [{"texte": t, **r.etape(t)} for t in textes if str(t).strip()]
    bilan = {s: sum(e["statut"] == s for e in etapes) for s in ("existant", "proche", "à créer")}
    return {"etapes": etapes, "existants": bilan["existant"], "proches": bilan["proche"], "a_creer": bilan["à créer"],
            "consigne": "Étape « proche » : reprendre le libellé exact du keyword proposé (ou justifier un nouveau keyword). "
                        "Étape « à créer » : vérifier d'abord studio_socle ; ne créer un keyword que si aucun ne convient."}


# =========================================================================== jugement délégué à une IA (Cursor / LLM)
# Les mots ne voient pas un synonyme (« confirmer le virement » / « Valider Le Virement »). Même partage que les autres
# jugements (atelier/intelligence/jugement_ia.py) : l'atelier présélectionne, l'IA juge le sens et justifie, le serveur
# contrôle, l'automaticien décide. Un verdict « réutiliser » rend l'étape « proche » : il bloque l'écriture de la suite
# comme un doublon vu par les mots ; un verdict « créer » ne lève jamais un doublon vu par les mots.
VERDICTS_KEYWORD = {"reutiliser": "réutiliser", "creer": "créer"}
CONSIGNE_KEYWORDS = (
    "Pour chaque étape, dire si un keyword existant du dépôt fait déjà la même action ou la même vérification : « reutiliser » "
    "en citant son nom exact, « creer » sinon. Juger le sens, pas les mots : un synonyme ou une reformulation de la même action "
    "est le même keyword (« confirmer le virement » / « Valider Le Virement ») ; une action opposée, un autre écran, un autre "
    "objet ou un autre résultat attendu (accepté / refusé) ne l'est pas. Les candidats sont une présélection par ressemblance "
    "des mots, avec leur corps : le bon keyword peut se trouver seulement dans « socle » (tous les keywords du dépôt), et aucun "
    "peut ne convenir. En cas de doute : « creer », en disant ce qui diffère. Justification obligatoire.")
SYSTEME_KEYWORDS = ("Tu es un automaticien Robot Framework. On te donne les étapes d'un scénario BDD sans keyword et les keywords "
                    "existants du dépôt. " + CONSIGNE_KEYWORDS + ' Réponds uniquement en JSON : {"jugements": [{"etape": "id", '
                    '"verdict": "reutiliser|creer", "keyword": "nom exact du keyword existant ou vide", "justification": "..."}]}. '
                    "En français.")


def _etapes(m: dict) -> list[dict]:
    return m.get("contexte", []) + [e for s in m.get("scenarios", []) for e in s["etapes"]]


def _jugeables(m: dict, r: Rapprocheur) -> dict:
    """Étapes sans keyword existant et sans décision humaine, une par texte : {id: étape}."""
    confirmes = {e["texte"] for e in _etapes(m) if e.get("keyword_nouveau")}
    out, vus = {}, set()
    for e in _etapes(m):
        if e["texte"] not in vus and e["texte"] not in confirmes and r.etape(e["texte"])["statut"] != "existant":
            vus.add(e["texte"])
            out[e["id"]] = e
    return out


def _verdict(v) -> str:
    v = str(v or "").strip().lower().replace("é", "e").replace(" ", "_").replace("-", "_")
    return {"reutiliser": "reutiliser", "reprendre": "reutiliser", "creer": "creer"}.get(v, v)


def keywords_pour_agent(cle: str, limite: int = 6, socle: int = 200) -> dict:
    """Pour une IA : chaque étape du scénario BDD sans keyword existant (texte masqué), les keywords PRÉSÉLECTIONNÉS par
    les mots (avec documentation et corps) et le nom de tous les keywords du dépôt."""
    from atelier.generation import bdd, studio
    from atelier.intelligence.jugement_ia import SECOURS, court

    m, r = bdd._exiger(cle), Rapprocheur()
    etapes = []
    for eid, e in _jugeables(m, r).items():
        cands = [{"keyword": p["keyword"], "fichier": p["fichier"], "documentation": court(p["documentation"], 200),
                  "corps": court(studio._corps(r.kws[p["id"]]), 500), "proximite_mots": p["score"]}
                 for p in r.proches(e["texte"], limite, seuil=0.01)]
        etapes.append({"etape": eid, "mot": e.get("mot", ""), "texte": court(e["texte"], 300), "candidats": cands,
                       "jugement": e.get("jugement_keyword")})
    cat = r.catalogue()
    return {"cle": cle, "titre": m.get("titre", ""), "consigne": CONSIGNE_KEYWORDS, "verdicts": list(VERDICTS_KEYWORD),
            "candidats_par": SECOURS, "etapes": etapes, "socle_tronque": len(cat) > socle,
            "socle": [{"keyword": k["keyword"], "documentation": court(k["documentation"], 120)} for k in cat[:socle]]}


def deposer_jugements_keywords(cle: str, jugements: list[dict], source: str = "Cursor (MCP)") -> dict:
    """Jugements d'une IA, contrôlés (étape jugeable, verdict connu, keyword cité présent dans le dépôt, justification),
    puis gardés sur l'étape. Aucun texte d'étape n'est modifié : l'automaticien reprend le keyword ou confirme le nouveau."""
    from atelier.intelligence import jugement_ia as _jia

    _jia.exiger_ia()
    from atelier.generation import bdd
    from atelier.intelligence.jugement_ia import justification as _j, maintenant

    m, r = bdd._exiger(cle), Rapprocheur()
    jug = _jugeables(m, r)
    retenus, refuses, vus = [], [], set()
    for n, j in enumerate(jugements or [], 1):
        j = j if isinstance(j, dict) else {}
        eid, v, nom, just = str(j.get("etape") or ""), _verdict(j.get("verdict")), str(j.get("keyword") or "").strip(), _j(j.get("justification"))
        kid = (r.exact.get(normaliser(nom)) or r.exact.get(cle_appel(nom))) if nom else None
        raison = ("étape inconnue ou non jugeable (keyword existant, ou nouveau keyword déjà confirmé)" if eid not in jug
                  else "étape déjà jugée dans cet envoi" if eid in vus
                  else "verdict inconnu (reutiliser ou creer)" if v not in VERDICTS_KEYWORD
                  else "citer le keyword existant à réutiliser" if v == "reutiliser" and not nom
                  else "keyword inconnu dans le dépôt (reprendre un nom de « candidats » ou de « socle »)" if v == "reutiliser" and not kid
                  else "justification manquante" if not just else "")
        if raison:
            refuses.append({"index": n, "etape": eid, "raison": raison})
            continue
        vus.add(eid)
        fiche = r._fiche(kid) if v == "reutiliser" else {"keyword": "", "fichier": ""}
        jugement = {"verdict": VERDICTS_KEYWORD[v], "keyword": fiche["keyword"], "fichier": fiche["fichier"], "justification": just,
                    "source": source, "date": maintenant()}
        for e in _etapes(m):  # une branche reprend les étapes communes : même texte, même jugement
            if e["texte"] == jug[eid]["texte"]:
                e["jugement_keyword"] = jugement
        retenus.append(VERDICTS_KEYWORD[v])
    if retenus:
        bdd.sauver(m, auteur=source)
    return {"cle": cle, "retenus": len(retenus), "refuses": refuses, **{k: retenus.count(k) for k in VERDICTS_KEYWORD.values()}}


def juger_keywords_ia(cle: str) -> dict:
    """Keywords jugés par le LLM interne ou Claude (appel direct, texte masqué), mêmes contrôles que pour Cursor."""
    from atelier.intelligence import jugement_ia

    vue = keywords_pour_agent(cle)
    if not vue["etapes"]:
        return {"disponible": False, "raison": "Aucune étape à juger : chaque étape a un keyword existant ou une décision."}
    return jugement_ia.appel_direct({k: vue[k] for k in ("cle", "titre", "etapes", "socle")}, SYSTEME_KEYWORDS, "jugements",
                                    lambda l, s: deposer_jugements_keywords(cle, l, s), "studio_keywords_a_juger puis studio_juger_keywords")
