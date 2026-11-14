"""Observation des comportements et des appels réseau pendant une session Discovery (phase 5 du cahier).

- Comportements : après une action déclenchée depuis le Studio, l'écran avant / après est comparé : messages
  apparus (erreur, validation, champ obligatoire…), éléments apparus ou disparus. Chaque message observé devient
  une **proposition de règle** dans le Knowledge Graph (déduite, à valider : jamais une règle validée d'office).
- Réseau (web) : le navigateur de l'atelier note les appels XHR / fetch (méthode, chemin, noms des paramètres,
  statut) ; les valeurs, corps et en-têtes (jetons, cookies) ne sont jamais conservés et les identifiants dans les
  chemins sont normalisés ({id}). En fin de session, les endpoints observés sont proposés au Knowledge Graph.
  Mobile : nécessite un proxy de test (non branché) ; rien n'est simulé.
"""
from __future__ import annotations

import hashlib
import re

MESSAGE_RE = re.compile(
    r"erreur|error|invalide|invalid|incorrect|obligatoire|requis|required|[ée]chec|impossible|refus|expir|"
    r"format|doit |au moins|minimum|maximum|d[ée]pass|insuffisant|non autoris|bloqu|succ[eè]s|confirm[ée]|enregistr[ée]",
    re.I)
INTERACTIFS = ("champ", "bouton", "case", "lien", "liste")
_SEGMENT_ID = re.compile(r"^(\d+|[0-9a-f]{8,}|[0-9a-f-]{32,36}|[A-Za-z0-9_-]*\d[A-Za-z0-9_-]{7,})$", re.I)


# =========================================================================== comportements
def messages(elements: list[dict]) -> list[str]:
    """Textes affichés qui ressemblent à un message de l'application (erreur, validation, confirmation)."""
    from atelier.execution.echecs import masquer_texte

    out = []
    for e in elements or []:
        t = (e.get("libelle") or "").strip()
        if t and e.get("type") not in INTERACTIFS and MESSAGE_RE.search(t) and len(t) <= 300:
            out.append(masquer_texte(t, []))
    return list(dict.fromkeys(out))


def comparer(avant: list[dict], apres: list[dict], action: str = "") -> list[dict]:
    """Comportements observés entre deux états de l'écran, suite à une action."""
    ma, mb = set(messages(avant)), messages(apres)
    cles_a = {e.get("key"): e for e in avant or [] if e.get("type") in INTERACTIFS}
    cles_b = {e.get("key"): e for e in apres or [] if e.get("type") in INTERACTIFS}
    out = [{"type": "message", "detail": m, "action": action} for m in mb if m not in ma]
    out += [{"type": "element_apparu", "detail": cles_b[k].get("libelle") or k, "cle": k, "action": action}
            for k in cles_b if k not in cles_a]
    out += [{"type": "element_disparu", "detail": cles_a[k].get("libelle") or k, "cle": k, "action": action}
            for k in cles_a if k not in cles_b]
    return out


def proposer_regles(comportements: list[dict], ecran: str = "") -> list[str]:
    """Chaque message observé devient une règle proposée (déduite, à valider) ; une règle rejetée n'est jamais
    reproposée. Renvoie les identifiants créés."""
    from atelier.domain import declarations

    crees = []
    for c in comportements:
        if c["type"] != "message":
            continue
        rid = "regle:obs_" + hashlib.sha1(f"{ecran}|{c['detail']}".encode()).hexdigest()[:10]
        try:
            declarations.ajouter_noeud(rid, "regle", c["detail"][:120],
                                       description=f"Message observé pendant une session Discovery après « {c.get('action') or 'action'} ».",
                                       proprietes={"origine": "discovery", "ecran": ecran, "action": c.get("action", "")},
                                       auteur="ia")
            crees.append(rid)
        except (FileExistsError, PermissionError):
            pass
    return crees


def etat_ecran() -> list[dict]:
    """Éléments de l'écran courant + textes affichés (web : lus à part, l'empreinte d'écran n'en dépend pas)."""
    from atelier.discovery import session

    els = session.current_elements(150)
    if session.is_web():
        try:
            els = els + [{"key": "", "type": "texte", "libelle": t} for t in session.webb().textes()]
        except Exception:  # noqa: BLE001
            pass
    return els


# =========================================================================== réseau
def normaliser_chemin(chemin: str) -> str:
    segs = [("{id}" if _SEGMENT_ID.match(s) else s) for s in (chemin or "/").split("/")]
    return "/".join(segs) or "/"


def endpoints(journal: list[dict]) -> list[dict]:
    """Appels réseau regroupés par méthode + chemin normalisé : nombre d'appels, statuts, paramètres."""
    agr: dict = {}
    for x in journal or []:
        k = (x["methode"], x.get("hote", ""), normaliser_chemin(x["chemin"]))
        a = agr.setdefault(k, {"methode": k[0], "hote": k[1], "chemin": k[2], "appels": 0, "statuts": set(), "parametres": set()})
        a["appels"] += 1
        a["statuts"].add(x.get("statut"))
        a["parametres"] |= set(x.get("parametres") or [])
    return [{**a, "statuts": sorted(s for s in a["statuts"] if s is not None), "parametres": sorted(a["parametres"]),
             "erreurs": sum(1 for s in a["statuts"] if s and s >= 400)} for a in sorted(agr.values(), key=lambda a: (a["chemin"], a["methode"]))]


def proposer_endpoints(liste: list[dict]) -> list[str]:
    """Endpoints observés proposés au Knowledge Graph (même identifiant que les contrats OpenAPI : pas de doublon)."""
    from atelier.discovery import connaissance
    from atelier.domain import declarations

    connus = endpoints_connus(connaissance)
    crees = []
    for e in liste:
        nid = f"endpoint:{e['methode'].upper()} {e['chemin']}"
        if _cle(nid) in connus:
            continue
        try:
            declarations.ajouter_noeud(nid, "endpoint", f"{e['methode'].upper()} {e['chemin']}",
                                       description="Appel observé pendant une session Discovery (web).",
                                       proprietes={"origine": "discovery", "hote": e["hote"], "statuts": e["statuts"],
                                                   "parametres": e["parametres"]}, auteur="ia")
            crees.append(nid)
        except (FileExistsError, PermissionError):
            pass
    return crees


def _cle(nid: str) -> str:
    """endpoint:GET /comptes/{compteId} et endpoint:GET /comptes/{id} désignent le même endpoint."""
    return re.sub(r"\{[^}]+\}", "{id}", nid)


def endpoints_connus(connaissance=None) -> dict:
    """Endpoints déjà dans le Knowledge Graph (OpenAPI, déclarations), par clé normalisée → source."""
    if connaissance is None:
        from atelier.discovery import connaissance
    try:
        return {_cle(n.id): n.source for n in connaissance.construire().noeuds.values() if n.type == "endpoint"}
    except Exception:  # noqa: BLE001
        return {}


def rapprocher(liste: list[dict]) -> list[dict]:
    """Endpoints observés, marqués documentés (contrat OpenAPI / KG) ou non documentés."""
    connus = endpoints_connus()
    return [{**e, "connu": connus.get(_cle(f"endpoint:{e['methode'].upper()} {e['chemin']}"))} for e in liste]


def journal_reseau(depuis: float = 0) -> list[dict]:
    """Journal réseau du navigateur de l'atelier (web) ; vide en mobile ou sans navigateur."""
    from atelier.discovery import session

    try:
        return session.webb().journal_reseau(depuis) if session.webb().active else []
    except Exception:  # noqa: BLE001
        return []
