"""Environnements de test d'une application : ce que l'on choisit dans le header (Environnement) et à la création d'une
application, à la place de la plateforme (décision de l'utilisateur du 2026-11-23 : la plateforme fait partie de
l'environnement).

Un environnement est celui de l'Execution Center (référentiel de pilotage, rubrique « environnements » : nom, type, URL,
plateforme, application, jeu de données). Il est rattaché à une application (champ « application » = son identifiant) ;
sans application, il vaut pour toutes. Le header propose une entrée par environnement ET par plateforme quand
l'environnement ne fixe pas la sienne et que l'application en a plusieurs (« recette · Android », « recette · iOS ») ;
une application web n'en a qu'une (« prod »). Sans environnement déclaré, les noms connus (Xray, fichiers de jeux de
données) servent d'environnements, combinés aux plateformes de l'application, pour que rien ne disparaisse.
"""
from __future__ import annotations

PLATEFORMES = {"web": "Web", "android": "Android", "ios": "iOS", "api": "API"}
DU_CHAMP = {v: k for k, v in PLATEFORMES.items()}  # « Android » (champ du référentiel) → « android » (atelier, PLATFORM)
COMPATIBLES = {"web": ("web",), "mobile": ("android", "ios"), "api": ("api",)}  # type d'application → plateformes


def _plateforme(e: dict) -> str:
    p = str(e.get("plateforme") or "").strip()
    return DU_CHAMP.get(p, p.lower())


def lister() -> list[dict]:
    """Environnements de l'Execution Center (vide sans référentiel de pilotage)."""
    from atelier.intelligence import strategie

    s = strategie.charger()
    return [{**e, "plateforme_id": _plateforme(e)} for e in ((s or {}).get("rubriques") or {}).get("environnements", [])]


def _de_l_app(e: dict, slug: str, nom: str = "") -> bool:
    a = str(e.get("application") or "").strip()
    return not a or a.casefold() in {x.casefold() for x in (slug, nom) if x}


def ajouter(env: dict, application: str = "") -> dict:
    """Déclare un environnement (référentiel créé s'il n'existe pas encore) ; renvoie l'environnement créé."""
    from atelier.intelligence import strategie

    if strategie.charger() is None:  # premier environnement du projet : le référentiel de pilotage naît avec lui
        from atelier.domain import projet

        strategie.creer("Référentiel de test", application or projet.PROJECT_DIR.name)
    avant = {e["id"] for e in lister()}
    p = _plateforme(env)
    champ = {**{k: env.get(k, "") for k in ("nom", "type", "url", "jdd_env", "usage")}, "plateforme": PLATEFORMES.get(p, env.get("plateforme", "")),
             "application": env.get("application", application), "type": env.get("type") or "TEST", "par_defaut": bool(env.get("par_defaut"))}
    strategie.enregistrer_element("environnements", champ)
    return next(e for e in lister() if e["id"] not in avant)


def rattacher(slug: str, ids: list[str]) -> list[dict]:
    """Rattache ces environnements à l'application ; ceux qui lui étaient rattachés et ne sont plus choisis sont détachés."""
    from atelier.intelligence import strategie

    ids = set(ids or [])
    for e in lister():
        a = str(e.get("application") or "")
        voulu = slug if e["id"] in ids else ("" if a == slug else a)
        if voulu != a:
            strategie.enregistrer_element("environnements", {**{k: v for k, v in e.items() if k != "plateforme_id"}, "application": voulu})
    return [e for e in lister() if e.get("application") == slug]


def pour_application(slug: str = "", nom: str = "", plateformes: list[str] | None = None, noms_connus: list[str] | None = None) -> list[dict]:
    """Entrées du sélecteur « Environnement » du header pour l'application : id, libellé, environnement, plateforme,
    URL, jeu de données (Atelier.env), défaut."""
    plateformes = [p for p in (plateformes or []) if p] or ["web"]
    out: list[dict] = []

    def entree(eid, env_nom, p, url="", jdd="", type_="", defaut=False, declare=True, plusieurs=False):
        out.append({"id": f"{eid}:{p}", "environnement": env_nom, "plateforme": p, "libelle": f"{env_nom} · {PLATEFORMES.get(p, p)}" if plusieurs else env_nom,
                    "url": url, "jdd": jdd or env_nom, "type": type_, "par_defaut": defaut, "declare": declare})

    declares = [e for e in lister() if _de_l_app(e, slug, nom)] if slug else []
    for e in declares:
        p = e["plateforme_id"]
        plats = [p] if p else plateformes
        for x in plats:
            entree(e["id"], e.get("nom") or e["id"], x, e.get("url", ""), e.get("jdd_env", ""), e.get("type", ""), bool(e.get("par_defaut")),
                   plusieurs=len(plats) > 1 or len({(d.get("nom") or "").casefold() for d in declares}) < len(declares))
    if not out:  # rien de déclaré : les noms connus, sur chaque plateforme de l'application
        for n in noms_connus or []:
            for p in plateformes:
                entree(n, n, p, declare=False, plusieurs=len(plateformes) > 1)
    return out
