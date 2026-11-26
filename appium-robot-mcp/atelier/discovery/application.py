"""Isolation des applications d'un même projet : à quelle application appartient un élément.

Un projet de tests peut porter plusieurs applications (ex. deux apps bancaires). Chaque écran de l'atelier (Kanban,
Lots TNR, Données des tests, Knowledge Graph, couverture) ne montre que l'application active. Règle unique :
  scénario BDD   son application déclarée, sinon celle de son parcours utilisateur (PU-…), de sa session Discovery,
                 ou du dossier de ses tests Robot (tests/<application>/…) ;
  fichier        le dossier d'application dans son chemin (tests/<app>/…, resources/locators/<app>/…) ;
  modèle MBT     application_du_modele (ses écrans, son parcours, ce qu'il porte).
Un élément sans application est partagé seulement si le projet n'a qu'une application ; sinon il n'est montré nulle
part (isolation stricte : mieux vaut un élément à rattacher qu'un élément d'une autre application)."""
from __future__ import annotations


def slugs() -> set[str]:
    from atelier.discovery import carte

    try:
        return {a["slug"] for a in carte.apps()}
    except Exception:  # noqa: BLE001
        return set()


def du_chemin(chemin: str, connus: set[str] | None = None) -> str:
    """Application d'un fichier du projet : le premier dossier de son chemin qui porte le nom d'une application."""
    connus = slugs() if connus is None else connus
    for partie in str(chemin or "").replace("\\", "/").split("::")[0].split("/")[:-1]:
        if partie in connus:
            return partie
    return ""


def du_scenario(m: dict, suites: list[str] | tuple = (), connus: set[str] | None = None) -> str:
    from atelier.discovery import carte

    connus = slugs() if connus is None else connus
    a = str(m.get("application") or "").strip()
    if a:
        return a if a in connus else carte.slug(a)
    p = str(m.get("parcours") or "")
    if p.startswith("PU-"):
        try:
            from atelier.discovery import parcours_utilisateur as pu

            app = pu._lire(p).get("app") or ""
            if app:
                return app
        except Exception:  # noqa: BLE001 — parcours supprimé : on regarde le reste
            pass
    sid = str(m.get("session") or "")
    if sid:
        try:
            from atelier.discovery import sessions_discovery

            app = (sessions_discovery._lire(sid).get("config") or {}).get("app") or ""
            if app:
                return app
        except Exception:  # noqa: BLE001
            pass
    for f in suites or ():
        app = du_chemin(f, connus)
        if app:
            return app
    return ""


def visible(proprietaire: str, app: str, connus: set[str] | None = None) -> bool:
    """L'élément de cette application (ou sans application) est-il montré quand « app » est active ?"""
    if proprietaire:
        return proprietaire == app
    connus = slugs() if connus is None else connus
    return len(connus) <= 1


def filtrer_graphe(g, app: str) -> int:
    """Retire du graphe ce qui appartient à une autre application du projet (fichiers du dépôt, scénarios, modèles MBT
    et leurs états / transitions / conditions), puis les nœuds de données et keywords qui n'étaient reliés qu'à eux.
    Rend le nombre de nœuds retirés."""
    connus = slugs()
    if not app or len(connus) <= 1:
        return 0
    autres = connus - {app}
    retirer: set[str] = set()
    for i, n in g.noeuds.items():
        p = n.proprietes or {}
        if n.type in ("suite", "test_robot", "resource", "keyword", "locator") and du_chemin(p.get("fichier") or i.split(":", 1)[-1], connus) in autres:
            retirer.add(i)
        elif n.type == "modele_comportement" and _app_du_modele(i, p, connus) in autres:
            retirer.add(i)
        elif n.type in ("etat", "transition", "condition") and any(i.split(":", 1)[-1].startswith(f"application-{a}/") for a in autres):
            retirer.add(i)
    try:  # scénarios d'une autre application (règle du Kanban)
        from atelier.generation import bdd, lots

        par_bdd, _ = lots._index_tests()
        for b in bdd.lister():
            nid = f"scenario:{b['cle']}"
            if nid in g.noeuds:
                m = bdd.charger(b["cle"]) or {}
                if not visible(du_scenario(m, [t["suite"] for t in par_bdd.get(b["cle"], [])], connus), app, connus):
                    retirer.add(nid)
    except Exception:  # noqa: BLE001 — sans scénarios lisibles : on garde le reste du filtrage
        pass
    for i, proprio in _donnees(connus).items():  # jeux de données et variables : l'application de ceux qui les utilisent
        if i in g.noeuds and proprio and proprio <= autres:
            retirer.add(i)
    voisins: dict[str, set] = {}
    for r in list(g.relations.values()):
        voisins.setdefault(r.de, set()).add(r.vers)
        voisins.setdefault(r.vers, set()).add(r.de)
    for i in retirer:
        g.retirer_noeud(i)
    # données, variables, keywords, locators qui ne servaient qu'aux éléments retirés
    for i in [i for i, n in g.noeuds.items() if n.type in ("jdd", "variable", "keyword", "locator", "etat", "transition", "condition")]:
        v = voisins.get(i, set())
        if v and v <= retirer:
            g.retirer_noeud(i)
            retirer.add(i)
    return len(retirer)


def _app_du_modele(nid: str, props: dict, connus: set[str]) -> str:
    """Application d'un modèle MBT du graphe, comparée exactement (« simple » n'est pas « simple_one »)."""
    per = props.get("perimetre")
    per = str(per.get("id", "")) if isinstance(per, dict) else ""
    if per.startswith("application:"):
        return per.split(":", 1)[1]
    try:
        from atelier.domain import comportement as cm
        from atelier.intelligence import mbt

        m = cm.charger(nid.split(":", 1)[1])
        return mbt.application_du_modele(m) if m else ""
    except Exception:  # noqa: BLE001
        return ""


def _donnees(connus: set[str]) -> dict:
    """{nœud jdd:/variable: : applications qui l'utilisent}. Jeu de données : applications des tests qui l'initialisent
    (une variante suit son jeu de base). Variable du référentiel Discovery : applications des parcours dont le profil
    la contient. Vide : non utilisé, donc partagé."""
    out: dict = {}
    try:
        from atelier.execution import donnees_tests, jdd

        par_jeu: dict = {}
        for tst in donnees_tests._jeux_par_test():
            if tst["jeu"]:
                par_jeu.setdefault(tst["jeu"], set()).add(du_chemin(tst["suite"], connus))
        for base, vs in jdd.variantes(donnees_tests._env()).items():
            for v in vs:
                par_jeu.setdefault(v["jeu"], set()).update(par_jeu.get(base, set()))
        out.update({f"jdd:{k}": {a for a in v if a} for k, v in par_jeu.items()})
    except Exception:  # noqa: BLE001
        pass
    try:
        from atelier.discovery import donnees, parcours_utilisateur as pu

        profils = donnees.profils_dict()
        for a in connus:
            for p in pu._tous(a):
                for var in (profils.get(p.get("profil_donnees") or "") or {}).get("variables") or []:
                    out.setdefault(f"variable:{var}", set()).add(a)
    except Exception:  # noqa: BLE001
        pass
    return {k: v for k, v in out.items() if v}
