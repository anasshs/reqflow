"""Point de passage unique de tout appel à un modèle par l'atelier.

Pour chaque appel : opération QA (déduite de l'appelant) → budget (blocage : refus, l'atelier reste sur ses règles) →
réglages de l'opération → demande compactée sans perte et plafond d'entrée vérifié → routage (économique, avancé,
secours) → cache → appel avec délai, tentatives et repli → usage mesuré (tokens du fournisseur, sinon estimés) → journal
en arrière-plan → cache et entrée rejouable pour le simulateur.

Les fournisseurs restent ceux de `fournisseur_ia` : « interne » (API compatible OpenAI) et « anthropic » (API Claude).
Avec « cursor » ou « aucun », l'atelier n'appelle aucun modèle : rien ne passe ici.
"""
from __future__ import annotations

import json
import os
import time

from atelier.intelligence.ia import budget, cache, config, journal, operations, optimiseur, routeur


def _usage_anthropic(msg) -> dict:
    u = getattr(msg, "usage", None)
    if u is None:
        return {}
    g = (lambda k: int(getattr(u, k, 0) or 0))  # noqa: E731
    return {"tokens_entree": g("input_tokens") + g("cache_creation_input_tokens") + g("cache_read_input_tokens"),
            "tokens_sortie": g("output_tokens"), "tokens_cache_lus": g("cache_read_input_tokens"), "tokens_cache_crees": g("cache_creation_input_tokens")}


def _usage_openai(r: dict) -> dict:
    u = r.get("usage") or {}
    if not u:
        return {}
    return {"tokens_entree": int(u.get("prompt_tokens") or 0), "tokens_sortie": int(u.get("completion_tokens") or 0),
            "tokens_cache_lus": int(((u.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0), "tokens_cache_crees": 0}


def _appeler_fournisseur(fournisseur: str, m: dict, systeme: str, demande: str, max_tokens: int, client=None, cache_prompt=False) -> tuple[str, dict]:
    """(texte, usage) ; usage vide quand le fournisseur ne le rend pas."""
    if fournisseur == "interne":
        from atelier.integrations.http import http, variable_secrete

        url = os.environ["IA_INTERNE_URL"].rstrip("/") + "/chat/completions"
        corps = {"model": m["modele"], "max_tokens": max_tokens, "temperature": m.get("temperature", 0.2) if m.get("temperature") is not None else 0.2,
                 "messages": [{"role": "system", "content": systeme}, {"role": "user", "content": demande}]}
        entetes = {"Content-Type": "application/json"}
        jeton = variable_secrete("IA_INTERNE_JETON")
        if jeton:
            entetes["Authorization"] = f"Bearer {jeton}"
        r = json.loads(http("POST", url, json.dumps(corps).encode(), entetes, timeout=int(m.get("timeout") or 180),
                            cafile=os.environ.get("IA_INTERNE_CA_BUNDLE") or None))
        return ((r.get("choices") or [{}])[0].get("message") or {}).get("content") or "", _usage_openai(r)
    from atelier.intelligence import assistant

    client = client or assistant._client()
    sys_ = [{"type": "text", "text": systeme, "cache_control": {"type": "ephemeral"}}] if cache_prompt else systeme
    kw = {"model": m["modele"], "max_tokens": max_tokens, "system": sys_, "messages": [{"role": "user", "content": demande}]}
    if m.get("temperature") is not None:
        kw["temperature"] = m["temperature"]
    if m.get("timeout"):
        kw["timeout"] = int(m["timeout"])
    msg = client.messages.create(**kw)
    return "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "text") == "text"), _usage_anthropic(msg)


def executer(systeme: str, demande: str, max_tokens: int = 1500, operation: str = "", client=None, forcer: dict | None = None,
             sans_cache: bool = False, garder_entree: bool = True, source: str = "direct") -> dict:
    """Appel complet ; rend {texte, modele, niveau, usage, estime, cache, repli, duree_ms, appel, correlation, raison}.
    forcer : {modele?, niveau?, max_sortie?, compacter?} pour le simulateur (réglage imposé, sans cache)."""
    from atelier.intelligence import fournisseur_ia

    f = fournisseur_ia.fournisseur()
    if not fournisseur_ia.configure_brut():
        raise RuntimeError(f"IA « {f} » : pas d'appel direct possible (configuration absente ou fournisseur sans appel).")
    op, module = (operation, operations.module_de(operation)) if operation else operations.appelante()
    niveau_budget = budget.verifier(module)
    reg = config.pour_operation(op)
    forcer = forcer or {}
    if "compacter" in forcer:
        reg["optimisation"] = {**reg["optimisation"], "compacter": forcer["compacter"]}
    max_sortie = int(forcer.get("max_sortie") or reg.get("max_sortie") or max_tokens)
    estimes = optimiseur.estimer(systeme) + optimiseur.estimer(demande)
    if forcer.get("modele"):
        liste = [{"modele": forcer["modele"], "niveau": forcer.get("niveau") or "force", "raison": "imposé par le simulateur"}]
    else:
        if forcer.get("niveau"):
            reg["niveau"] = forcer["niveau"]
        liste = routeur.candidats(reg, estimes, niveau_budget)
    principal = liste[0]
    max_sortie = min(max_sortie, int(principal["max_sortie"])) if principal.get("max_sortie") else max_sortie
    envoyee, avant, apres = optimiseur.preparer(systeme, demande, reg, principal.get("max_entree"))
    cid = journal.correlation()
    base = {"correlation": cid, "source": source, "fournisseur": f, "operation": op, "module": module, "tokens_avant": avant, "tokens_apres": apres}

    utilise_cache = reg["cache"].get("actif", True) and not sans_cache and not forcer
    courantes = cache.versions() if utilise_cache else {}
    if utilise_cache:
        k = cache.cle(op, systeme, principal["modele"], envoyee)
        e = cache.lire(k, courantes)
        if e is not None:
            aid = journal.enregistrer_appel(**base, modele=principal["modele"], niveau=principal["niveau"], statut="ok", cache=True,
                                            tokens_entree=0, tokens_sortie=0, duree_ms=0)
            return {"texte": e["valeur"], "modele": principal["modele"], "niveau": principal["niveau"], "usage": {}, "estime": False, "cache": True,
                    "repli": False, "duree_ms": 0, "appel": aid, "correlation": cid, "raison": "réponse en cache (sources inchangées)",
                    "tokens_evites": e["tokens_evites"]}

    derniere = None
    for rang, m in enumerate(liste):
        for _ in range(max(1, int(m.get("tentatives") or 1))):
            t0 = time.time()
            try:
                texte, usage = _appeler_fournisseur(f, m, systeme, envoyee, max_sortie, client,
                                                    bool(reg["optimisation"].get("cache_prompt")))
            except Exception as ex:  # noqa: BLE001 — erreur journalisée, puis nouvelle tentative ou repli
                derniere = ex
                journal.enregistrer_appel(**base, modele=m["modele"], niveau=m["niveau"], statut="erreur", erreur=str(ex)[:500],
                                          duree_ms=int(1000 * (time.time() - t0)), repli=rang > 0, estime=True, tokens_entree=apres)
                continue
            duree = int(1000 * (time.time() - t0))
            estime = not usage
            usage = usage or {"tokens_entree": apres, "tokens_sortie": optimiseur.estimer(texte), "tokens_cache_lus": 0, "tokens_cache_crees": 0}
            aid = journal.enregistrer_appel(**base, modele=m["modele"], niveau=m["niveau"], statut="ok", duree_ms=duree, repli=rang > 0,
                                            estime=estime, **usage)
            if utilise_cache and texte.strip():
                cache.ecrire(cache.cle(op, systeme, principal["modele"], envoyee), op, module, m["modele"], texte,
                             usage["tokens_entree"] + usage["tokens_sortie"], reg["cache"].get("duree_heures") or 0, courantes)
            sim = config.effective().get("simulateur") or {}
            if garder_entree and sim.get("conserver_entrees", True):
                journal.enregistrer_entree(aid, op, module, m["modele"], systeme, envoyee, texte, max_sortie, int(sim.get("max_entrees") or 200))
            return {"texte": texte, "modele": m["modele"], "niveau": m["niveau"], "usage": usage, "estime": estime, "cache": False,
                    "repli": rang > 0, "duree_ms": duree, "appel": aid, "correlation": cid, "raison": m.get("raison", "")}
    raise RuntimeError(f"IA : échec de l'appel ({', '.join(x['modele'] for x in liste)}) : {derniere}") from derniere


def appeler(systeme: str, demande: str, max_tokens: int = 1500, operation: str = "", client=None) -> str:
    """Texte de la réponse (interface de `fournisseur_ia.completer`)."""
    return executer(systeme, demande, max_tokens, operation, client)["texte"]


def mesurer_reponse_agent(resp, operation: str, modele: str, duree_ms: int, correlation_: str) -> None:
    """Agent intégré (boucle avec outils, API Claude) : chaque réponse du modèle est journalisée avec son usage."""
    from atelier.intelligence import fournisseur_ia

    u = _usage_anthropic(resp)
    journal.enregistrer_appel(correlation=correlation_, source="agent", fournisseur=fournisseur_ia.fournisseur(), modele=modele, niveau="avance",
                              operation=operation, module=operations.module_de(operation), statut="ok", duree_ms=duree_ms, estime=not u,
                              **(u or {"tokens_entree": 0, "tokens_sortie": 0}))


def mesurer_mcp(outil: str, resultat, duree_s: float, demande: str = ""):
    """Réponse d'un outil MCP (ce que reçoit Cursor) : allégée sans perte si le réglage le prévoit, taille estimée en tokens,
    journalisée en source « mcp » (estimation, jamais additionnée aux appels directs). Rend le résultat (allégé ou non)."""
    try:
        if not isinstance(resultat, (dict, list)):
            return resultat
        brut = optimiseur.estimer(resultat)
        allege = (config.effective().get("optimisation") or {}).get("alleger_mcp", True)
        r = optimiseur.alleger(resultat) if allege else resultat
        apres = optimiseur.estimer(r) if allege else brut
        journal.enregistrer_appel(correlation=demande or journal.correlation(), source="mcp", fournisseur="cursor", modele="",
                                  operation=f"mcp.{outil}", module=operations.module_mcp(outil), statut="ok", estime=True,
                                  tokens_entree=apres, tokens_sortie=0, duree_ms=int(duree_s * 1000), tokens_avant=brut, tokens_apres=apres)
        return r
    except Exception:  # noqa: BLE001 — la mesure ne fait jamais échouer un outil
        return resultat
