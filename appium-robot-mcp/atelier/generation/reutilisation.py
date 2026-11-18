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
