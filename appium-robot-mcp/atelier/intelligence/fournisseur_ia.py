"""Fournisseur d'IA de l'atelier, choisi par l'entreprise (IA_FOURNISSEUR) ou, à défaut, réglé pour le projet :

- « aucun »    : uniquement des règles explicables (défaut sûr) ;
- « cursor »   : l'agent de Cursor lit les données via le MCP et dépose ses propositions dans l'atelier (outils
                 testabilite_*) ; l'atelier n'appelle lui-même aucun modèle ;
- « interne »  : LLM hébergé par l'entreprise, API compatible OpenAI (POST <IA_INTERNE_URL>/chat/completions),
                 modèle IA_INTERNE_MODELE, jeton dans la variable IA_INTERNE_JETON (ou le coffre) ;
- « anthropic » : API Claude (ANTHROPIC_API_KEY), seulement si l'entreprise l'autorise.

La variable IA_FOURNISSEUR, quand elle est définie, s'impose (choix de l'entreprise). Sans elle, le projet peut choisir
« cursor » dans Paramètres › Cursor / Claude (fichier atelier_cursor.yaml) : c'est le seul choix possible sans variable,
parce qu'avec Cursor l'atelier n'appelle lui-même aucun modèle. « interne » et « anthropic » demandent une URL ou une
clé : ils restent réglés par variables d'environnement.

Quel que soit le fournisseur : les textes sont masqués avant envoi (e-mails, IBAN, cartes, secrets, longs nombres),
une proposition d'IA n'est jamais appliquée sans validation humaine, et le fournisseur / modèle est historisé.
"""
from __future__ import annotations

import json
import os

FOURNISSEURS = ("aucun", "cursor", "interne", "anthropic")


REGLABLES_SANS_VARIABLE = ("aucun", "cursor")


def impose() -> str:
    """Fournisseur imposé par la variable d'environnement IA_FOURNISSEUR ; « » si elle n'est pas définie."""
    f = (os.environ.get("IA_FOURNISSEUR") or "").strip().lower()
    return f if f in FOURNISSEURS else ""


def du_projet() -> str:
    """Fournisseur réglé pour le projet (atelier_cursor.yaml) ; « » s'il n'y en a pas ou si le fichier est illisible."""
    import yaml

    from atelier.domain import projet

    f = projet.PROJECT_DIR / "atelier_cursor.yaml"
    try:
        v = str(((yaml.safe_load(f.read_text("utf-8")) or {}) if f.exists() else {}).get("ia") or "").strip().lower()
    except (OSError, yaml.YAMLError, AttributeError):
        v = ""
    return v if v in REGLABLES_SANS_VARIABLE else ""


def fournisseur() -> str:
    return impose() or du_projet() or "aucun"


def etat() -> dict:
    f = fournisseur()
    detail = {"aucun": "règles explicables uniquement",
              "cursor": "propositions déposées par l'agent Cursor via le MCP (outils testabilite_*)",
              "interne": f"LLM interne {os.environ.get('IA_INTERNE_MODELE', '?')} — {os.environ.get('IA_INTERNE_URL', 'URL non configurée')}",
              "anthropic": "API Claude" + ("" if os.environ.get("ANTHROPIC_API_KEY") else " (ANTHROPIC_API_KEY absente)")}[f]
    return {"fournisseur": f, "detail": detail, "appel_direct": f in ("interne", "anthropic") and configure()}


def configure() -> bool:
    f = fournisseur()
    if f == "interne":
        return bool(os.environ.get("IA_INTERNE_URL") and os.environ.get("IA_INTERNE_MODELE"))
    if f == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    return False


def modele() -> str:
    f = fournisseur()
    if f == "interne":
        return os.environ.get("IA_INTERNE_MODELE", "")
    if f == "anthropic":
        from atelier.intelligence import assistant

        return assistant.MODELE
    return f


def completer(systeme: str, demande: str, max_tokens: int = 1500) -> str:
    """Appel direct (fournisseurs « interne » et « anthropic » seulement). Le texte doit déjà être masqué."""
    f = fournisseur()
    if not configure():
        raise RuntimeError(f"IA « {f} » : pas d'appel direct possible (configuration absente ou fournisseur sans appel).")
    if f == "interne":
        from atelier.integrations.http import http, variable_secrete

        url = os.environ["IA_INTERNE_URL"].rstrip("/") + "/chat/completions"
        corps = {"model": os.environ["IA_INTERNE_MODELE"], "max_tokens": max_tokens, "temperature": 0.2,
                 "messages": [{"role": "system", "content": systeme}, {"role": "user", "content": demande}]}
        entetes = {"Content-Type": "application/json"}
        jeton = variable_secrete("IA_INTERNE_JETON")
        if jeton:
            entetes["Authorization"] = f"Bearer {jeton}"
        r = json.loads(http("POST", url, json.dumps(corps).encode(), entetes, timeout=180,
                            cafile=os.environ.get("IA_INTERNE_CA_BUNDLE") or None))
        return ((r.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    from atelier.intelligence import assistant

    msg = assistant._client().messages.create(model=assistant.MODELE, max_tokens=max_tokens, system=systeme,
                                              messages=[{"role": "user", "content": demande}])
    return "".join(getattr(b, "text", "") for b in msg.content)


def extraire_json(texte: str):
    """Premier objet JSON d'une réponse de modèle (bloc ```json``` toléré)."""
    t = texte.strip()
    if "```" in t:
        t = t.split("```")[1]
        t = t[4:] if t.lower().startswith("json") else t
    debut = min([i for i in (t.find("{"), t.find("[")) if i >= 0] or [0])
    return json.JSONDecoder().raw_decode(t[debut:])[0]
