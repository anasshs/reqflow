"""Modèle de graphe commun aux espaces de travail (Knowledge Graph, Coverage Graph, Automation Flow).

Chaque nœud représente un objet métier ou technique identifiable ; chaque relation a un type
précis. Tout élément porte sa provenance :
  - « observé »  : lu dans une source (carte, dépôt Robot, instantané Xray) ;
  - « déclaré »  : saisi par l'automaticien ;
  - « déduit »   : proposé par un calcul ou par l'IA — jamais utilisé pour une décision
                   (impact, couverture, TNR) tant qu'il n'est pas validé.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field

# type de nœud -> catégorie (légende et filtres)
TYPES_NOEUDS = {
    "application": "APPLICATION", "plateforme": "APPLICATION", "environnement": "APPLICATION",
    "version": "APPLICATION",
    "module": "FONCTIONNEL", "fonctionnalite": "FONCTIONNEL", "parcours": "FONCTIONNEL",
    "ecran": "FONCTIONNEL", "action": "FONCTIONNEL", "regle": "FONCTIONNEL", "role": "FONCTIONNEL",
    "composant": "TECHNIQUE", "locator": "TECHNIQUE", "keyword": "TECHNIQUE", "endpoint": "TECHNIQUE",
    "entite": "TECHNIQUE", "resource": "TECHNIQUE", "bibliotheque": "TECHNIQUE",
    "epic": "JIRA", "user_story": "JIRA", "bug": "JIRA",
    "test": "XRAY", "test_plan": "XRAY", "test_set": "XRAY", "test_execution": "XRAY",
    "feature": "BDD", "scenario": "BDD", "step": "BDD",
    "suite": "AUTOMATION", "test_robot": "AUTOMATION", "jdd": "AUTOMATION", "requete": "AUTOMATION",
    "variable": "AUTOMATION",  # variable du référentiel de données Discovery (définition, jamais de valeur)
    "resultat": "AUTOMATION",
    # Model-Based Testing : le modèle comportemental et ses chemins (distincts des écrans et des tests)
    "modele_comportement": "FONCTIONNEL", "etat": "FONCTIONNEL", "transition": "FONCTIONNEL", "condition": "FONCTIONNEL",
    "chemin": "BDD",
}
CATEGORIES = ["APPLICATION", "FONCTIONNEL", "TECHNIQUE", "JIRA", "XRAY", "BDD", "AUTOMATION"]

TYPES_RELATIONS = {
    "contient": "Contient", "navigue_vers": "Navigue vers", "depend_de": "Dépend de",
    "appelle": "Appelle", "verifie": "Vérifie", "couvre": "Couvre",
    "implemente_par": "Est implémenté par", "teste_par": "Est testé par",
    "execute_par": "Est exécuté par", "impacte": "Impacte", "utilise": "Utilise",
    # V2, phase 5 : champs et anomalies
    "possede": "Possède", "concerne": "Concerne", "detecte_par": "Est détectée par", "associe_a": "Est associée à",
    # corrélation exigence ↔ écran : preuve issue des tests (jamais déclarée à la main, jamais une couverture)
    "verifiee_sur": "Est vérifiée sur",
    # vue fonctionnelle déduite de la Discovery (agrégats de faits observés, preuve gardée en propriétés)
    "mene_a": "Mène à", "traverse": "Traverse", "enchaine_avec": "S'enchaîne avec",
    # projection d'une vue filtrée : deux éléments affichés reliés par des éléments masqués (jamais stockée)
    "lie_via": "Lié via",
    # perspective utilisateur : l'action est un nœud (écran → permet → action → aboutit à → écran)
    "permet": "Permet", "aboutit_a": "Aboutit à", "declenche": "Déclenche",
    # ponts Tests & Qualité : test Xray formalisé par un scénario BDD
    "formalise_par": "Est formalisé par",
    # Model-Based Testing
    "contient_etat": "Contient l'état", "contient_transition": "Contient la transition", "part_de": "Part de",
    "conduit_a": "Conduit à", "declenchee_par": "Déclenchée par", "gardee_par": "Gardée par", "parcourt": "Parcourt",
    "derive_de": "Dérivé de",
}
PROVENANCES = ("observé", "déclaré", "déduit")


@dataclass
class Noeud:
    id: str
    type: str
    libelle: str
    proprietes: dict = field(default_factory=dict)
    provenance: str = "observé"
    source: str = ""
    statut: str = "validé"            # validé | à valider
    confiance: float = 1.0
    plateformes: list = field(default_factory=list)

    @property
    def categorie(self) -> str:
        return TYPES_NOEUDS.get(self.type, "TECHNIQUE")

    def vers_dict(self) -> dict:
        return {**asdict(self), "categorie": self.categorie}


@dataclass
class Relation:
    de: str
    vers: str
    type: str
    provenance: str = "observé"
    source: str = ""
    statut: str = "validé"
    proprietes: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.de}|{self.type}|{self.vers}"

    @property
    def fiable(self) -> bool:
        """Utilisable pour une décision : un lien déduit non validé ne l'est jamais."""
        return not (self.provenance == "déduit" and self.statut != "validé")

    @property
    def confiance_niveau(self) -> str:
        """Distinct de la provenance : « confirmée » (lue dans une source, déclarée, ou validée par un humain),
        « probable » (calculée de façon déterministe à partir de faits observés, preuves gardées), « non vérifiée »
        (proposition à valider, IA comprise). Seules les relations confirmées alimentent couverture, impact et TNR
        officiels ; les probables restent visibles (vues exploratoires)."""
        if self.statut != "validé":
            return "non vérifiée"
        if self.provenance == "déduit" and self.proprietes.get("calcul"):
            return "probable"
        return "confirmée"

    @property
    def confirmee(self) -> bool:
        return self.confiance_niveau == "confirmée"

    def vers_dict(self) -> dict:
        return {**asdict(self), "id": self.id, "libelle": TYPES_RELATIONS.get(self.type, self.type),
                "confiance_niveau": self.confiance_niveau}


def verifier_type_noeud(t: str):
    if t not in TYPES_NOEUDS:
        raise ValueError(f"Type de nœud inconnu : {t} (types : {', '.join(sorted(TYPES_NOEUDS))})")


def verifier_type_relation(t: str):
    if t not in TYPES_RELATIONS:
        raise ValueError(f"Type de relation inconnu : {t} (types : {', '.join(TYPES_RELATIONS)})")


class _Relations(dict):
    """Relations d'un graphe, avec un numéro de version qui change à chaque modification : l'index des relations par
    nœud (sortants / entrants) n'est recalculé que si les relations ont changé."""
    version = 0

    def _touche(self):
        self.version = self.version + 1

    def __setitem__(self, k, v):
        self._touche()
        super().__setitem__(k, v)

    def __delitem__(self, k):
        self._touche()
        super().__delitem__(k)

    def pop(self, *a):
        self._touche()
        return super().pop(*a)

    def popitem(self):
        self._touche()
        return super().popitem()

    def setdefault(self, k, v=None):
        if k not in self:
            self._touche()
        return super().setdefault(k, v)

    def update(self, *a, **kw):
        self._touche()
        super().update(*a, **kw)

    def clear(self):
        self._touche()
        super().clear()

    def __reduce__(self):  # pickle : un dict ordinaire suffit (l'index se reconstruit)
        return (_Relations, (dict(self),))


class Graphe:
    def __init__(self, nom: str = ""):
        self.nom = nom
        self.noeuds: dict[str, Noeud] = {}
        self.relations: dict[str, Relation] = _Relations()

    # ------------------------------------------------------------------ construction
    def noeud(self, id: str, type: str, libelle: str, **kw) -> Noeud:
        """Ajoute un nœud ou complète celui qui existe (propriétés fusionnées, plateformes unies)."""
        verifier_type_noeud(type)
        n = self.noeuds.get(id)
        if n is None:
            n = self.noeuds[id] = Noeud(id, type, libelle, **kw)
        else:
            n.proprietes.update(kw.get("proprietes") or {})
            for p in kw.get("plateformes") or []:
                if p not in n.plateformes:
                    n.plateformes.append(p)
        return n

    def relier(self, de: str, vers: str, type: str, **kw) -> Relation | None:
        verifier_type_relation(type)
        if de == vers or de not in self.noeuds or vers not in self.noeuds:
            return None
        r = Relation(de, vers, type, **kw)
        return self.relations.setdefault(r.id, r)

    def retirer_noeud(self, id: str):
        self.noeuds.pop(id, None)
        for rid in [r for r, x in self.relations.items() if id in (x.de, x.vers)]:
            del self.relations[rid]

    def fusionner(self, source: str, cible: str):
        """Les relations de source sont reportées sur cible, puis source disparaît."""
        if source not in self.noeuds or cible not in self.noeuds:
            raise KeyError("Nœud inconnu pour la fusion.")
        s, c = self.noeuds[source], self.noeuds[cible]
        c.proprietes = {**s.proprietes, **c.proprietes, "fusionne_depuis": source}
        for p in s.plateformes:
            if p not in c.plateformes:
                c.plateformes.append(p)
        for r in [r for r in self.relations.values() if source in (r.de, r.vers)]:
            de, vers = (cible if r.de == source else r.de), (cible if r.vers == source else r.vers)
            self.relier(de, vers, r.type, provenance=r.provenance, source=r.source, statut=r.statut,
                        proprietes=r.proprietes)
        self.retirer_noeud(source)

    # ------------------------------------------------------------------ lecture
    def _index(self) -> tuple[dict, dict]:
        """Relations par nœud de départ et d'arrivée, recalculées seulement si les relations ont changé (graphe de
        plusieurs milliers de nœuds : un parcours de toutes les relations à chaque appel coûtait des dizaines de
        secondes)."""
        rels = self.relations
        if type(rels) is not _Relations:  # relations remplacées par un dict ordinaire (filtre, sous-graphe…)
            rels = self.relations = _Relations(rels)
        cle = (id(rels), rels.version, len(rels))
        idx = getattr(self, "_idx", None)
        if not idx or idx[0] != cle:
            de, vers = {}, {}
            for r in rels.values():
                de.setdefault(r.de, []).append(r)
                vers.setdefault(r.vers, []).append(r)
            idx = self._idx = (cle, de, vers)
        return idx[1], idx[2]

    def __getstate__(self):  # l'index n'est pas conservé (cache disque du graphe)
        return {k: v for k, v in self.__dict__.items() if k != "_idx"}

    def sortants(self, id: str, fiables: bool = False) -> list[Relation]:
        return [r for r in self._index()[0].get(id, ()) if r.fiable or not fiables]

    def entrants(self, id: str, fiables: bool = False) -> list[Relation]:
        return [r for r in self._index()[1].get(id, ()) if r.fiable or not fiables]

    def voisinage(self, ids: list[str], profondeur: int = 1) -> "Graphe":
        """Sous-graphe des nœuds à moins de `profondeur` relations (dans les deux sens)."""
        garde, file = set(i for i in ids if i in self.noeuds), deque((i, 0) for i in ids if i in self.noeuds)
        while file:
            n, d = file.popleft()
            if d >= profondeur:
                continue
            for r in self.relations.values():
                autre = r.vers if r.de == n else r.de if r.vers == n else None
                if autre and autre not in garde:
                    garde.add(autre)
                    file.append((autre, d + 1))
        return self.sous_graphe(garde)

    def sous_graphe(self, ids) -> "Graphe":
        g = Graphe(self.nom)
        ids = set(ids)
        g.noeuds = {i: n for i, n in self.noeuds.items() if i in ids}
        g.relations = {k: r for k, r in self.relations.items() if r.de in ids and r.vers in ids}
        return g

    def filtrer(self, types: list[str] | None = None, categories: list[str] | None = None,
                plateforme: str = "", recherche: str = "", version: str = "") -> "Graphe":
        """version : garde les éléments vus dans ce build (et ceux qui ne dépendent d'aucun build) ;
        plateforme : de même pour une plateforme."""
        q = recherche.strip().casefold()

        def garde(n: Noeud) -> bool:
            if types and n.type not in types:
                return False
            if categories and n.categorie not in categories:
                return False
            if plateforme and n.plateformes and plateforme not in n.plateformes:
                return False
            if version and (n.proprietes.get("versions") and version not in n.proprietes["versions"]
                            or n.type == "version" and n.id != f"version:{version}"):
                return False
            if q and q not in n.libelle.casefold() and q not in n.id.casefold():
                return False
            return True
        return self.sous_graphe(i for i, n in self.noeuds.items() if garde(n))

    def confirme(self) -> "Graphe":
        """Copie sans les liens qui ne sont pas confirmés (probables et non vérifiés) : base des calculs officiels."""
        g = Graphe(self.nom)
        g.noeuds = dict(self.noeuds)
        g.relations = {i: r for i, r in self.relations.items() if r.confirmee}
        return g

    def atteignables(self, depart: str, sens: str, types_relations: set[str] | None = None,
                     fiables: bool = True) -> set[str]:
        """Nœuds atteignables depuis `depart` en suivant les relations (sens « aval » ou « amont »)."""
        vus, file = {depart}, deque([depart])
        while file:
            n = file.popleft()
            rels = self.sortants(n, fiables) if sens == "aval" else self.entrants(n, fiables)
            for r in rels:
                if types_relations and r.type not in types_relations:
                    continue
                autre = r.vers if sens == "aval" else r.de
                if autre not in vus:
                    vus.add(autre)
                    file.append(autre)
        vus.discard(depart)
        return vus

    def vers_dict(self) -> dict:
        types = sorted({n.type for n in self.noeuds.values()})
        return {"nom": self.nom,
                "noeuds": [n.vers_dict() for n in self.noeuds.values()],
                "relations": [r.vers_dict() for r in self.relations.values()],
                "legende": {"categories": CATEGORIES, "types": {t: TYPES_NOEUDS[t] for t in types},
                            "relations": TYPES_RELATIONS},
                "stats": {"noeuds": len(self.noeuds), "relations": len(self.relations)}}
