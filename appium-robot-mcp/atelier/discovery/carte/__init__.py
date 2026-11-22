"""
Carte de l'application : un graphe d'écrans (nœuds) et de transitions (liens), par application.

Stockage dans le projet de tests (versionné, relu en MR) :
  app_map/<app>/app.yaml            identité, plateformes, build, langue, liste rouge, comptes
  app_map/<app>/ecrans/<id>.yaml    un fichier par écran : empreintes, états, éléments, locators
  app_map/<app>/transitions.yaml    actions qui mènent d'un écran à un autre, avec leur fiabilité
  app_map/<app>/vignettes/*.png     miniatures des écrans
  app_map/.app_courante             application active

Reconnaissance d'un écran (« empreinte ») :
  - éléments avec identifiant stable (resource-id, accessibility id, data-testid) ;
  - à défaut (Jetpack Compose sans testTag, SwiftUI sans identifier) : textes FIXES de l'interface
    (titres, libellés, boutons) et types d'éléments — montants, dates, numéros sont ignorés ;
  - activité Android ou motif d'URL web en complément.
La correspondance est approximative (similarité >= MAP_SEUIL_SIMILARITE) : un même écran avec un
message d'erreur reste reconnu, la variante est rangée dans ses « états ».
"""
from __future__ import annotations

from atelier.domain import yaml_rapide

import hashlib
import heapq
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import yaml

from atelier.discovery.parsing import UIA_ID
from atelier.domain import projet

SEUIL = float(os.environ.get("MAP_SEUIL_SIMILARITE", "0.72"))
SEUIL_LIBELLES = 0.85  # reconnaissance par les seuls libellés (identifiants tous renommés) : plus exigeante
ID_PREFIX = ("id=", "accessibility_id=", "data-testid=", UIA_ID)  # UIA_ID : testTag Jetpack Compose
INTERACTIFS = ("champ", "bouton", "case", "lien", "liste", "element")

# Actions jamais touchées par l'exploration automatique (app bancaire) — ajustable par application.
LISTE_ROUGE_DEFAUT = [
    r"confirm", r"\bvalid", r"\bpayer\b", r"\bpaie", r"envoyer", r"\bsign", r"supprim", r"cl[oô]tur",
    r"r[ée]sili", r"d[ée]connex", r"d[ée]connecter", r"logout", r"transf[ée]r", r"acheter", r"souscri",
    r"accepter", r"effectuer", r"[ée]mettre", r"bloquer", r"opposition", r"commander", r"recharger",
]
DYN_RE = re.compile(r"\d[\d\s.,]*\d|•|\*{3}|@|\b(dh|mad|eur|usd)\b|€|\$|\d{1,2}[/:]\d{1,2}", re.I)


# =========================================================================== utilitaires
def _racine() -> Path:
    """Dossier de la carte dans le projet de tests (lu à l'appel)."""
    return projet.PROJECT_DIR / os.environ.get("APP_MAP_DIR", "app_map")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def slug(text: str, max_len: int = 40) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text[:max_len] or "ecran"


def _load(p: Path, defaut):
    return yaml_rapide.lire(p, defaut)  # relu seulement s'il a changé : la carte est lue des centaines de fois par écran


def _dump(p: Path, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120), "utf-8")
    yaml_rapide.oublier(p)


def est_dynamique(t: str) -> bool:
    return not t or len(t) > 40 or bool(DYN_RE.search(t))


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", str(t)).strip().casefold()


def motif_url(url: str) -> str:
    p = urlparse(url)
    path = re.sub(r"/(\d+|[0-9a-f]{8,}|[0-9a-f-]{36})(?=/|$)", "/:id", p.path or "/")
    return f"{p.netloc}{path}"


def similarite(a, b) -> float:
    A, B = set(a or []), set(b or [])
    return len(A & B) / len(A | B) if (A | B) else 0.0


def valeur_id(locator: str) -> str:
    """L'identifiant porté par un locator d'identifiant (« id=x », testTag Compose…)."""
    if locator.startswith(UIA_ID):
        return locator[len(UIA_ID):].rsplit('"', 1)[0]
    return locator.split("=", 1)[1]


def robustesse(locator: str) -> str:
    if locator.startswith(ID_PREFIX):
        return "robuste"
    if locator.startswith(("xpath=//*[@text", "text=", "css=body", "xpath=//hierarchy", "xpath=//")):
        return "fragile"
    return "correct"


# =========================================================================== applications
TYPES_APP = ("mobile", "web", "api")


def type_app(cfg: dict) -> str:
    """Type déclaré, sinon déduit des plateformes (applications créées avant l'existence du type)."""
    if cfg.get("type") in TYPES_APP:
        return cfg["type"]
    p = set(cfg.get("plateformes") or [])
    return "mobile" if p & {"android", "ios"} else "api" if p == {"api"} else "web"


def apps() -> list[dict]:
    if not _racine().exists():
        return []
    out = []
    for d in sorted(_racine().iterdir()):
        if (d / "app.yaml").exists():
            cfg = _load(d / "app.yaml", {})
            out.append({**cfg, "type": type_app(cfg), "slug": d.name, "nb_ecrans": len(list((d / "ecrans").glob("*.yaml")))})
    return out


def dupliquer_app(source: str, nom: str, avec_carte: bool = False) -> dict:
    """Nouvelle application à partir d'une autre : configuration complète (type, plateformes, packages / URL, liste
    rouge, classement des actions, rattachement Xray…) ; avec_carte : écrans et transitions copiés aussi (sinon la
    carte part vide). Les comptes de test ne sont jamais copiés."""
    import shutil

    d = _racine() / source
    if not source or "/" in source or source.startswith(".") or not (d / "app.yaml").exists():
        raise KeyError(f"Application « {source} » inconnue.")
    nom = (nom or "").strip()
    if not nom:
        raise ValueError("Nom de la nouvelle application obligatoire.")
    s = slug(nom)
    cible = _racine() / s
    if cible.exists():
        raise FileExistsError(f"L'application « {nom} » existe déjà.")
    if avec_carte:
        shutil.copytree(d, cible, ignore=shutil.ignore_patterns("comptes*", ".app_courante"))
    else:
        cible.mkdir(parents=True)
    cfg = _load(d / "app.yaml", {})
    cfg.update(nom=nom, cree=_now(), comptes=[], ecran_depart=cfg.get("ecran_depart", "") if avec_carte else "", etape_assistant=1,
               duplique_de=source)
    _dump(cible / "app.yaml", cfg)
    return {**cfg, "slug": s}


def archiver_app(s: str) -> dict:
    """« Suppression » d'une application : son dossier local (carte, écrans, comptes, liste rouge) est déplacé dans
    app_map/.archives/<slug>-<date>, restaurable. Rien n'est supprimé dans Xray ni Jira, ni dans le dépôt de tests."""
    import shutil
    from datetime import datetime as _dt

    d = _racine() / s
    if not s or "/" in s or s.startswith(".") or not (d / "app.yaml").exists():
        raise KeyError(f"Application « {s} » inconnue.")
    cible = _racine() / ".archives" / f"{s}-{_dt.now():%Y%m%d-%H%M%S}"
    cible.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(d), str(cible))
    courante = _racine() / ".app_courante"
    if courante.exists() and courante.read_text("utf-8").strip() == s:
        courante.unlink()
    return {"archive": cible.name, "active": app_courante()}


def archives_apps() -> list[dict]:
    a = _racine() / ".archives"
    return [{"archive": d.name, "nom": _load(d / "app.yaml", {}).get("nom", d.name)}
            for d in sorted(a.iterdir(), reverse=True) if (d / "app.yaml").exists()] if a.exists() else []


def restaurer_app(archive: str) -> dict:
    """Restaure une application archivée sous son slug d'origine (refus si une application de même slug existe)."""
    import re as _re
    import shutil

    src = _racine() / ".archives" / archive
    if "/" in archive or not (src / "app.yaml").exists():
        raise KeyError(f"Archive inconnue : {archive}")
    s = _re.sub(r"-\d{8}-\d{6}$", "", archive)
    if (_racine() / s).exists():
        raise FileExistsError(f"Une application « {s} » existe déjà : la renommer ou l'archiver d'abord.")
    shutil.move(str(src), str(_racine() / s))
    return config_app(s)


def app_courante() -> str | None:
    f = _racine() / ".app_courante"
    if f.exists() and (_racine() / f.read_text("utf-8").strip() / "app.yaml").exists():
        return f.read_text("utf-8").strip()
    lst = apps()
    return lst[0]["slug"] if lst else None


def choisir_app(s: str) -> dict:
    if not (_racine() / s / "app.yaml").exists():
        raise KeyError(f"Application « {s} » inconnue.")
    _racine().mkdir(parents=True, exist_ok=True)
    (_racine() / ".app_courante").write_text(s, "utf-8")
    return config_app(s)


def normaliser_dossier(d: str) -> str:
    """Chemin d'un dossier du Test Repository Xray : « /A/B » (racine « / »)."""
    d = "/" + "/".join(x.strip() for x in str(d or "").replace("\\", "/").split("/") if x.strip())
    return d


def normaliser_tests_xray(tx: dict | None) -> dict:
    """Comment reconnaître les tests de l'application dans le projet Xray : dossiers du Test Repository
    (« dossiers », sous-dossiers compris), valeurs du champ Jira du mapping (« valeurs »), ou ancien format
    composant / libellé. Vide = tout le projet (repository dédié à une seule application)."""
    tx = tx or {}
    out = {}
    if "dossiers" in tx:
        out["dossiers"] = sorted({normaliser_dossier(d) for d in tx["dossiers"] or [] if str(d).strip()})
    if "valeurs" in tx:
        out["valeurs"] = [str(v).strip() for v in tx["valeurs"] or [] if str(v).strip()]
    if not out:
        out = {k: str(v).strip() for k, v in tx.items() if k in ("composant", "libelle") and str(v).strip()}
    return {k: v for k, v in out.items() if v}


def creer_app(nom: str, plateformes: list[str], android: dict | None = None, ios: dict | None = None,
              web: dict | None = None, build: str = "", langue: str = "fr",
              liste_rouge: list[str] | None = None, comptes: list[str] | None = None,
              projet_xray: str = "", tests_xray: dict | None = None, type_: str = "", api: dict | None = None) -> dict:
    """Application du projet de tests (un projet Xray peut en contenir plusieurs). projet_xray : clé du projet Xray
    de rattachement ; tests_xray : comment reconnaître ses tests dans ce projet ({"composant": ..., "libelle": ...})."""
    s = slug(nom)
    if (_racine() / s / "app.yaml").exists():
        raise FileExistsError(f"L'application « {nom} » existe déjà.")
    type_ = type_ or type_app({"plateformes": plateformes})
    if type_ not in TYPES_APP:
        raise ValueError("Type d'application : mobile, web ou api.")
    if type_ == "mobile":
        plateformes = [p for p in plateformes if p in ("android", "ios")]
        if not plateformes:
            raise ValueError("Application mobile : choisir Android et / ou iOS.")
        web = {}
    elif type_ == "web":
        plateformes, android, ios = ["web"], {}, {}
    else:
        plateformes, android, ios, web = ["api"], {}, {}, {}
        if not (api or {}).get("url"):
            raise ValueError("Application API : URL de base obligatoire.")
    cfg = {"nom": nom, "type": type_, "plateformes": plateformes, "android": android or {}, "ios": ios or {},
           "web": web or {}, "api": {k: v for k, v in (api or {}).items() if k in ("url", "openapi") and v}, "build": build, "langue": langue,
           "liste_rouge": {"textes": liste_rouge or LISTE_ROUGE_DEFAUT, "cles": []},
           "comptes": comptes or [], "ecran_depart": "", "etape_assistant": 1, "cree": _now(),
           "projet_xray": (projet_xray or "").strip().upper(),
           "tests_xray": normaliser_tests_xray(tests_xray)}
    _dump(_racine() / s / "app.yaml", cfg)
    choisir_app(s)
    return {**cfg, "slug": s}


def _dir(s: str | None = None) -> Path:
    s = s or app_courante()
    if not s:
        raise RuntimeError("Aucune application : crée-en une avec l'assistant « Nouvelle application ».")
    return _racine() / s


def config_app(s: str | None = None) -> dict:
    d = _dir(s)
    return {**_load(d / "app.yaml", {}), "slug": d.name}


def maj_app(s: str | None = None, **champs) -> dict:
    d = _dir(s)
    cfg = _load(d / "app.yaml", {})
    for k, v in champs.items():
        if v is not None:
            cfg[k] = v
    _dump(d / "app.yaml", cfg)
    return {**cfg, "slug": d.name}


# =========================================================================== écrans
def ecrans(s: str | None = None) -> list[dict]:
    return [_load(f, {}) for f in sorted((_dir(s) / "ecrans").glob("*.yaml"))]


def ecran(ref: str, s: str | None = None) -> dict:
    if not str(ref or "").strip():  # une référence vide ne désigne pas « le premier écran sans nom »
        raise KeyError("Écran non précisé.")
    ref_n = _norm(ref)
    for e in ecrans(s):
        if ref in (e.get("id"), e.get("nom")) or ref_n in [_norm(a) for a in e.get("alias", [])] \
                or (e.get("nom") and _norm(e["nom"]) == ref_n):
            return e
    raise KeyError(f"Écran « {ref} » inconnu dans la carte.")


def _save_ecran(e: dict, s: str | None = None):
    e["maj"] = _now()
    _dump(_dir(s) / "ecrans" / f"{e['id']}.yaml", e)


def transitions(s: str | None = None) -> list[dict]:
    return _load(_dir(s) / "transitions.yaml", []) or []


def _save_transitions(ts: list, s: str | None = None):
    _dump(_dir(s) / "transitions.yaml", ts)


def signature(elements: list[dict], sans_ids: bool = False) -> list[str]:
    """Empreinte d'un écran : identifiants stables, à défaut libellés fixes. sans_ids : l'empreinte que l'écran avait
    AVANT d'avoir des identifiants de test (libellés seuls), pour le reconnaître quand ses testTag arrivent."""
    toks = set()
    for e in elements:
        locs = e.get("locators") or []
        idl = next((l for l in locs if l.startswith(ID_PREFIX)), None)
        ident = valeur_id(idl) if idl else ""
        if ident and not sans_ids and not est_dynamique(ident):
            toks.add("id:" + ident)
        elif e.get("libelle") and not est_dynamique(e["libelle"]):
            if sans_ids and ident and e["libelle"] == ident.split("/")[-1]:
                continue  # élément sans texte : son « libellé » n'est que son identifiant
            toks.add(f"{e.get('type', '?')}:{_norm(e['libelle'])}")
    return sorted(toks)


def titre_probable(elements: list[dict]) -> str:
    textes = [e for e in elements if e.get("libelle") and not est_dynamique(e["libelle"])
              and len(e["libelle"]) >= 3 and e.get("type") in ("texte", "element")]
    avec_pos = [e for e in textes if e.get("rect")]
    if avec_pos:
        return min(avec_pos, key=lambda e: (e["rect"][1], e["rect"][0]))["libelle"]
    return textes[0]["libelle"] if textes else ""


def _libelles_connus(e: dict, platform: str) -> list[str]:
    """Empreinte par libellés de l'écran cartographié : le reconnaître quand ses identifiants ont TOUS été renommés
    (vues classiques « package:id/x » remplacées par des testTag, ou testTag renommés par les développeurs)."""
    toks = set()
    for el in (e.get("elements") or {}).values():
        locs = (el.get("locators") or {}).get(platform) or []
        lib = el.get("libelle") or ""
        if not locs or not lib or est_dynamique(lib):
            continue
        if lib in {valeur_id(l).split("/")[-1] for l in locs if l.startswith(ID_PREFIX)}:
            continue  # élément sans texte : son « libellé » n'est que son identifiant
        toks.add(f"{el.get('type', '?')}:{_norm(lib)}")
    return sorted(toks)


def _sans_texte_porte(toks: list[str]) -> list[str]:
    """En Compose, le libellé d'un bouton est un nœud texte enfant : il apparaît deux fois (« bouton:valider » et
    « texte:valider »), une seule fois dans une vue classique. On ne garde que l'élément qui le porte."""
    portes = {t.split(":", 1)[1] for t in toks if not t.startswith("texte:")}
    return [t for t in toks if not (t.startswith("texte:") and t.split(":", 1)[1] in portes)]


def reconnaitre(sig: list[str], platform: str, contexte: str = "", elements: list | None = None,
                s: str | None = None):
    best, score = None, 0.0
    obs_locs = {l for e in (elements or []) for l in (e.get("locators") or [])}
    libelles = signature(elements, sans_ids=True) if elements else sig  # l'écran tel qu'il était sans identifiants
    portes, titre = _sans_texte_porte(libelles), titre_probable(elements or [])
    for e in ecrans(s):
        p = (e.get("plateformes") or {}).get(platform)
        if p and p.get("signature"):
            if platform == "web" and contexte and p.get("contexte") and p["contexte"] != contexte:
                continue
            connues = [p["signature"]] + [st["signature"] for st in e.get("etats", []) if st.get("plateforme") == platform]
            sc = max(similarite(x, c) for x in (sig, libelles) for c in connues)
            if sc < SEUIL and len(libelles) >= 3:  # identifiants renommés : mêmes libellés et même titre
                meme_titre = not titre or not e.get("titre") or _norm(titre) == _norm(e["titre"])
                sl = similarite(portes, _sans_texte_porte(_libelles_connus(e, platform))) if meme_titre else 0.0
                if meme_titre and sl >= SEUIL_LIBELLES:
                    sc = sl
        else:  # écran importé sans empreinte : on compare les locators connus
            connus = {l for el in (e.get("elements") or {}).values() for l in (el.get("locators", {}).get(platform) or [])}
            sc = (len(connus & obs_locs) / len(connus)) * 0.9 if connus else 0.0
        if sc > score:
            best, score = e, sc
    return (best, score) if score >= SEUIL else (None, score)


def _cle_connue(els: dict, x: dict, platform: str, pris: set, unique: bool = True) -> str | None:
    """Clé de l'élément déjà cartographié que cet élément observé désigne, quand son identifiant de test vient d'arriver
    (ou a changé de nom) : même type et un locator en commun (texte, position relative au libellé…). Les scénarios, les
    keywords et les liens du Knowledge Graph passent par la clé : elle ne doit pas changer avec le locator."""
    locs = set(x.get("locators") or [])
    ids = [valeur_id(l).split("/")[-1] for l in locs if l.startswith(ID_PREFIX)]
    if not ids:
        return None
    libres = {k: el for k, el in els.items() if k not in pris and el.get("type") == x.get("type")
              and (el.get("locators") or {}).get(platform)}
    for k, el in libres.items():
        if locs & set(el["locators"][platform]):
            return k
    # rien en commun (vue classique devenue composant Compose : le texte n'est plus porté par le même nœud) : le même
    # libellé visible, s'il ne désigne qu'un seul élément de ce type de part et d'autre
    lib = x.get("libelle") or ""
    if unique and lib and not est_dynamique(lib) and lib not in ids:
        memes = [k for k, el in libres.items() if _norm(el.get("libelle") or "") == _norm(lib)]
        if len(memes) == 1:
            return memes[0]
    return None


def _fusion_elements(e: dict, elements: list[dict], platform: str, s: str | None = None):
    els = e.setdefault("elements", {})
    gardes = [x for x in elements if x.get("type") in INTERACTIFS
              or (x.get("libelle") and not est_dynamique(x["libelle"]))][:80]
    pris = {x["key"] for x in gardes if x["key"] in els}
    nb: dict = {}
    for x in gardes:
        c = (x.get("type"), _norm(x.get("libelle") or ""))
        nb[c] = nb.get(c, 0) + 1
    for x in gardes:
        k = x["key"]
        retrouve = None
        if k not in els:  # identifiant de test arrivé ou renommé : l'élément déjà connu garde sa clé métier
            retrouve = _cle_connue(els, x, platform, pris, nb[(x.get("type"), _norm(x.get("libelle") or ""))] == 1)
            k = x["key"] = retrouve or k
        pris.add(k)
        entry = els.setdefault(k, {"type": x.get("type"), "libelle": "" if est_dynamique(x.get("libelle", "")) else x.get("libelle", ""),
                                   "locators": {}})
        anciens = entry["locators"].get(platform) or []
        nouveaux = [l for l in x.get("locators", []) if l not in anciens]
        a_id = any(l.startswith(ID_PREFIX) for l in anciens)
        ids_nouveaux = [l for l in nouveaux if l.startswith(ID_PREFIX)]
        disparus = [l for l in anciens if l.startswith(ID_PREFIX) and l not in x.get("locators", [])] if retrouve and ids_nouveaux else []
        if disparus:  # l'identifiant a été renommé : l'ancien n'existe plus dans l'application, il ne reste pas en secours
            anciens = [l for l in anciens if l not in disparus]
            e.setdefault("changements", []).append({"type": "identifiant_remplace", "plateforme": platform, "cle": k,
                                                    "ancien": disparus[0], "locator": ids_nouveaux[0],
                                                    "build": config_app(s).get("build", ""), "date": _now()})
        if ids_nouveaux and anciens and not a_id:  # un tag est apparu : on monte en gamme
            e.setdefault("changements", []).append({"type": "amelioration", "plateforme": platform, "cle": k,
                                                    "locator": ids_nouveaux[0], "build": config_app(s).get("build", ""),
                                                    "date": _now()})
        fusion = ids_nouveaux + [l for l in anciens if l.startswith(ID_PREFIX)] + \
            [l for l in anciens if not l.startswith(ID_PREFIX)] + [l for l in nouveaux if not l.startswith(ID_PREFIX)]
        entry["locators"][platform] = list(dict.fromkeys(fusion))[:4]


def observer(elements: list[dict], platform: str, contexte: str = "", build: str = "",
             vignette_cb=None, test_key: str | None = None, s: str | None = None) -> dict:
    """Reconnaît (ou crée) l'écran correspondant aux éléments observés et met la carte à jour."""
    sig = signature(elements)
    e, score = reconnaitre(sig, platform, contexte, elements, s)
    nouveau = e is None
    if nouveau:
        eid = "e_" + hashlib.sha1(("|".join(sig) + platform + contexte).encode()).hexdigest()[:8]
        e = {"id": eid, "nom": "", "module": "", "alias": [], "titre": titre_probable(elements),
             "plateformes": {}, "elements": {}, "etats": [], "changements": [], "utilise_par": [],
             "essayes": {}, "cree": _now()}
        score = 1.0
    p = e.setdefault("plateformes", {}).setdefault(platform, {})
    arrives = sorted(t for t in set(sig) - set(p.get("signature") or []) if t.startswith("id:"))
    if not p.get("signature"):
        p["signature"] = sig
    elif arrives and max(similarite(sig, c) for c in [p["signature"]] + [
            st["signature"] for st in e.get("etats", []) if st.get("plateforme") == platform]) < SEUIL:
        # des identifiants de test sont arrivés ou ont été renommés (testTag, accessibilityIdentifier, data-testid) :
        # même écran, reconnu par ses libellés ; son empreinte passe aux nouveaux identifiants, sans doublon ni état parasite
        e.setdefault("changements", []).append({"type": "identifiants", "plateforme": platform, "ajoutes": arrives[:30],
                                                "build": build, "date": _now()})
        p["signature"] = sig
    elif score < 0.999:
        ajoutes = sorted(set(sig) - set(p["signature"]))
        retires = sorted(set(p["signature"]) - set(sig))
        if build and p.get("vu_build") and build != p["vu_build"] and (ajoutes or retires):
            e.setdefault("changements", []).append({"type": "build", "build": build, "plateforme": platform,
                                                    "ajoutes": ajoutes[:30], "retires": retires[:30], "date": _now()})
            e["a_revoir"] = True
            p["signature"] = sig
        elif score < 0.9 and len(e.get("etats", [])) < 6 and not any(
                similarite(sig, st["signature"]) > 0.9 for st in e.get("etats", []) if st.get("plateforme") == platform):
            e.setdefault("etats", []).append({"nom": f"etat_{len(e.get('etats', [])) + 1}", "plateforme": platform,
                                              "signature": sig})
    p["contexte"] = contexte or p.get("contexte", "")
    p["vu_build"] = build or p.get("vu_build", "")
    p["vu_le"] = _now()
    if not e.get("titre"):
        e["titre"] = titre_probable(elements)
    _fusion_elements(e, elements, platform, s)
    if test_key and test_key not in e.setdefault("utilise_par", []):
        e["utilise_par"].append(test_key)
    if vignette_cb and not p.get("vignette"):
        try:
            png = vignette_cb()
            if png:
                nom = f"{e['id']}_{platform}.png"
                (_dir(s) / "vignettes").mkdir(parents=True, exist_ok=True)
                (_dir(s) / "vignettes" / nom).write_bytes(png)
                p["vignette"] = nom
        except Exception:
            pass
    _save_ecran(e, s)
    return {"id": e["id"], "nom": e.get("nom", ""), "titre": e.get("titre", ""), "nouveau": nouveau,
            "score": round(score, 2), "plateforme": platform}


def cle_pour_locator(eid: str, locator: str, platform: str, s: str | None = None) -> str:
    try:
        for k, el in (ecran(eid, s).get("elements") or {}).items():
            if locator in (el.get("locators", {}).get(platform) or []):
                return k
    except KeyError:
        pass
    return ""


# =========================================================================== transitions
def _tid(de, vers, platform, action) -> str:
    base = f"{de}|{vers}|{platform}|{action.get('type')}|{action.get('cle') or action.get('locator') or action.get('url', '')}"
    return "t_" + hashlib.sha1(base.encode()).hexdigest()[:8]


def enregistrer_transition(de: str, vers: str, platform: str, action: dict, ok: bool = True,
                           duree_ms: int | None = None, source: str = "observation", s: str | None = None):
    if de == vers:
        return None
    action = {k: v for k, v in action.items() if k in ("type", "cle", "locator", "libelle", "direction", "url")}
    tid = _tid(de, vers, platform, action)
    ts = transitions(s)
    t = next((x for x in ts if x["id"] == tid), None)
    if not t:
        t = {"id": tid, "de": de, "vers": vers, "plateforme": platform, "action": action, "essais": 0,
             "reussites": 0, "duree_ms": 0, "interdite": False, "source": source, "cree": _now()}
        ts.append(t)
    t["essais"] += 1
    t["reussites"] += 1 if ok else 0
    if duree_ms:
        t["duree_ms"] = int((t["duree_ms"] * (t["essais"] - 1) + duree_ms) / t["essais"])
    _save_transitions(ts, s)
    return t


def noter(tid: str, ok: bool, s: str | None = None):
    ts = transitions(s)
    for t in ts:
        if t["id"] == tid:
            t["essais"] += 1
            t["reussites"] += 1 if ok else 0
    _save_transitions(ts, s)


def marquer_essaye(eid: str, platform: str, cle: str, s: str | None = None):
    e = ecran(eid, s)
    lst = e.setdefault("essayes", {}).setdefault(platform, [])
    if cle not in lst:
        lst.append(cle)
        _save_ecran(e, s)


def actions_depuis(eid: str, platform: str, s: str | None = None) -> set:
    faits = {t["action"].get("cle") or t["action"].get("locator") for t in transitions(s)
             if t["de"] == eid and t["plateforme"] == platform}
    try:
        faits |= set((ecran(eid, s).get("essayes") or {}).get(platform, []))
    except KeyError:
        pass
    return faits


def chemin(depuis: str, vers: str, platform: str, s: str | None = None) -> list[dict] | None:
    """Chemin le plus fiable (Dijkstra pondéré par le taux d'échec des transitions)."""
    if depuis == vers:
        return []
    adj: dict = {}
    for t in transitions(s):
        if t["plateforme"] != platform or t.get("interdite") or t["action"].get("type") == "type_text":
            continue
        fiab = t["reussites"] / max(t["essais"], 1)
        adj.setdefault(t["de"], []).append((1 + 4 * (1 - fiab), t))
    dist, pile, prec = {depuis: 0.0}, [(0.0, depuis)], {}
    while pile:
        d, n = heapq.heappop(pile)
        if n == vers:
            break
        if d > dist.get(n, 1e9):
            continue
        for w, t in adj.get(n, []):
            nd = d + w
            if nd < dist.get(t["vers"], 1e9):
                dist[t["vers"]], prec[t["vers"]] = nd, t
                heapq.heappush(pile, (nd, t["vers"]))
    if vers not in prec:
        return None
    out, n = [], vers
    while n != depuis:
        out.append(prec[n])
        n = prec[n]["de"]
    return list(reversed(out))


# =========================================================================== édition
def ecran_nomme(nom: str, sauf: str = "", s: str | None = None) -> dict | None:
    """Autre écran portant déjà ce nom métier (renommer vers ce nom fusionnerait les deux)."""
    n = slug(nom)
    try:
        exclu = ecran(sauf, s)["id"] if sauf else ""
    except Exception:  # noqa: BLE001 — écran inconnu : aucun à exclure
        exclu = ""
    return next((x for x in ecrans(s) if x.get("nom") == n and x["id"] != exclu), None)


def renommer(eid: str, nom: str, module: str | None = None, alias: list | None = None, s: str | None = None) -> dict:
    """Donne un nom métier. Si le nom existe déjà (ex. même écran vu sur iOS), les deux sont fusionnés."""
    nom = slug(nom)
    e = ecran(eid, s)
    autre = next((x for x in ecrans(s) if x.get("nom") == nom and x["id"] != e["id"]), None)
    if autre:
        return fusionner(e["id"], autre["id"], s)
    ancien = e.get("nom") or e["id"]
    e["nom"] = nom
    if module is not None:
        e["module"] = module
    if alias is not None:
        e["alias"] = alias
    _save_ecran(e, s)
    _suivre_renommage(ancien, nom, s)
    return e


def _suivre_renommage(ancien: str, nouveau: str, s: str | None = None, fusion: tuple | None = None):
    """Les liens déclarés dans le Knowledge Graph (exigence « réalisé par » écran, règles…) et les décisions de corrélation
    suivent l'écran renommé ou fusionné : l'identifiant de la carte est stable, celui du graphe porte le nom."""
    if s is not None and s != app_courante():
        return
    try:
        from atelier.domain import declarations

        declarations.renommer_ecran(ancien, nouveau)
        if fusion:
            from atelier.discovery import correlation

            correlation.migrer_ecran(*fusion)
    except Exception as ex:  # noqa: BLE001 — la carte reste utilisable ; l'écart est signalé, pas masqué
        import warnings

        warnings.warn(f"Liens de l'écran « {ancien} » non reportés sur « {nouveau} » : {ex}", stacklevel=2)


def fusionner(source: str, cible: str, s: str | None = None) -> dict:
    a, b = ecran(source, s), ecran(cible, s)
    for plat, p in (a.get("plateformes") or {}).items():
        if plat not in b.setdefault("plateformes", {}):
            b["plateformes"][plat] = p
        elif p.get("signature"):
            b.setdefault("etats", []).append({"nom": f"etat_{len(b.get('etats', [])) + 1}", "plateforme": plat,
                                              "signature": p["signature"]})
    for k, el in (a.get("elements") or {}).items():
        dest = b.setdefault("elements", {}).setdefault(k, {"type": el.get("type"), "libelle": el.get("libelle"), "locators": {}})
        for plat, locs in (el.get("locators") or {}).items():
            dest["locators"][plat] = list(dict.fromkeys((dest["locators"].get(plat) or []) + locs))[:4]
    for champ in ("etats", "changements"):
        b.setdefault(champ, []).extend(a.get(champ, []))
    b["utilise_par"] = sorted(set(b.get("utilise_par", [])) | set(a.get("utilise_par", [])))
    b["alias"] = sorted(set(b.get("alias", [])) | set(a.get("alias", [])) | ({a["nom"]} if a.get("nom") else set()))
    _save_ecran(b, s)
    ts = []
    for t in transitions(s):
        t["de"] = cible if t["de"] == source else t["de"]
        t["vers"] = cible if t["vers"] == source else t["vers"]
        if t["de"] != t["vers"] and not any(x["id"] == t["id"] for x in ts):
            ts.append(t)
    _save_transitions(ts, s)
    (_dir(s) / "ecrans" / f"{a['id']}.yaml").unlink(missing_ok=True)
    _suivre_renommage(a.get("nom") or a["id"], b.get("nom") or b["id"], s, fusion=(a["id"], b["id"]))
    return b


def supprimer_ecran(eid: str, s: str | None = None):
    e = ecran(eid, s)
    (_dir(s) / "ecrans" / f"{e['id']}.yaml").unlink(missing_ok=True)
    _save_transitions([t for t in transitions(s) if e["id"] not in (t["de"], t["vers"])], s)


def maj_transition(tid: str, interdite: bool | None = None, supprimer: bool = False, s: str | None = None):
    ts = transitions(s)
    if supprimer:
        ts = [t for t in ts if t["id"] != tid]
    else:
        for t in ts:
            if t["id"] == tid and interdite is not None:
                t["interdite"] = interdite
    _save_transitions(ts, s)


def definir_locators(eid: str, cle: str, platform: str, locators: list[str], s: str | None = None) -> dict:
    e = ecran(eid, s)
    el = e.setdefault("elements", {}).setdefault(cle, {"type": "element", "libelle": "", "locators": {}})
    el["locators"][platform] = locators[:4]
    _save_ecran(e, s)
    return el


def marquer_revu(eid: str, s: str | None = None):
    e = ecran(eid, s)
    e["a_revoir"] = False
    _save_ecran(e, s)


def interdit(element: dict, s: str | None = None) -> bool:
    lr = config_app(s).get("liste_rouge") or {}
    txt = f"{element.get('key', '')} {element.get('libelle', '')}"
    return element.get("key") in (lr.get("cles") or []) or \
        any(re.search(m, txt, re.I) for m in (lr.get("textes") or LISTE_ROUGE_DEFAUT))


def proposer_noms(s: str | None = None) -> list[dict]:
    noms = {e.get("nom") for e in ecrans(s) if e.get("nom")}
    out = []
    for e in ecrans(s):
        if e.get("nom"):
            continue
        base = slug(e.get("titre") or "") if e.get("titre") else ""
        if not base:
            ctx = next((p.get("contexte") for p in (e.get("plateformes") or {}).values() if p.get("contexte")), "")
            dernier = re.split(r"[/.]", ctx.rstrip("/").split("/")[-1].rsplit(".", 1)[0] if "/" in ctx else ctx.split(".")[-1])[-1]
            base = slug(dernier) if ctx else e["id"]
        prop, n = base, 2
        while prop in noms:
            prop, n = f"{base}_{n}", n + 1
        noms.add(prop)
        out.append({"id": e["id"], "titre": e.get("titre", ""), "proposition": prop})
    return out


# =========================================================================== vues et rapports
def graphe(s: str | None = None) -> dict:
    cfg = config_app(s)
    nodes = []
    for e in ecrans(s):
        sans_id = sum(1 for el in (e.get("elements") or {}).values() if el.get("type") in INTERACTIFS and any(
            locs and not locs[0].startswith(ID_PREFIX) for locs in (el.get("locators") or {}).values()))
        nodes.append({"id": e["id"], "nom": e.get("nom", ""), "titre": e.get("titre", ""), "module": e.get("module", ""),
                      "plateformes": sorted((e.get("plateformes") or {}).keys()),
                      "vignettes": {p: v.get("vignette") for p, v in (e.get("plateformes") or {}).items() if v.get("vignette")},
                      "couvert": bool(e.get("utilise_par")), "a_revoir": bool(e.get("a_revoir")),
                      "nb_elements": len(e.get("elements") or {}), "sans_id": sans_id, "etats": len(e.get("etats", [])),
                      "cree": e.get("cree", "")})
    libelles = {(e["id"], k): el.get("libelle") for e in ecrans(s) for k, el in (e.get("elements") or {}).items()}
    edges = [{"id": t["id"], "de": t["de"], "vers": t["vers"], "plateforme": t["plateforme"],
              "type": t["action"].get("type"), "label": t["action"].get("libelle")
              or libelles.get((t["de"], t["action"].get("cle"))) or t["action"].get("cle")
              or {"press_back": "retour", "swipe": f"défilement {t['action'].get('direction', '')}",
                  "open_url": "ouverture URL"}.get(t["action"].get("type"), t["action"].get("type")),
              "fiabilite": round(t["reussites"] / max(t["essais"], 1), 2), "essais": t["essais"],
              "interdite": t.get("interdite", False), "source": t.get("source", "")} for t in transitions(s)]
    depart = cfg.get("ecran_depart") or ""
    if nodes and not depart:
        cible = {e["vers"] for e in edges if e["type"] != "press_back"}
        sortants = {e["de"] for e in edges}
        sources = [n for n in nodes if n["id"] in sortants and n["id"] not in cible]
        observes = sorted((n for n in nodes if n["plateformes"]), key=lambda n: n["cree"])
        depart = (sources or observes or nodes)[0]["id"]
    return {"app": cfg, "nodes": nodes, "edges": edges, "depart": depart}


def rapport_tags(s: str | None = None) -> list[dict]:
    """Éléments sans identifiant stable, classés par nombre de tests qui passent par leur écran."""
    lignes = []
    for e in ecrans(s):
        for k, el in (e.get("elements") or {}).items():
            if el.get("type") not in INTERACTIFS:
                continue
            for plat, locs in (el.get("locators") or {}).items():
                if locs and not locs[0].startswith(ID_PREFIX):
                    lignes.append({"ecran": e.get("nom") or e.get("titre") or e["id"], "ecran_id": e["id"],
                                   "cle": k, "libelle": el.get("libelle", ""), "plateforme": plat,
                                   "locator_actuel": locs[0], "usage": len(e.get("utilise_par", [])),
                                   "tag_propose": k if plat != "ios" else k.replace("_", "-")})
    return sorted(lignes, key=lambda x: (-x["usage"], x["ecran"], x["cle"]))


def texte_rapport_tags(lignes: list[dict], app: str) -> str:
    out = [f"Identifiants de test à ajouter — application {app}", "",
           "Android (Jetpack Compose) : activer une fois à la racine",
           "  Modifier.semantics { testTagsAsResourceId = true }",
           "puis ajouter Modifier.testTag(\"<tag>\") sur chaque élément ci-dessous (option active aussi dans le build de recette).",
           "Reprendre le tag proposé tel quel : c'est la clé déjà utilisée par les tests, rien n'est à renommer.",
           "iOS (SwiftUI) : .accessibilityIdentifier(\"<tag>\"). Web : attribut data-testid.", ""]
    for x in lignes:
        out.append(f"- [{x['plateforme']}] écran {x['ecran']} — {x['libelle'] or x['cle']} → tag « {x['tag_propose']} »"
                   f" (utilisé par {x['usage']} test(s), locator actuel : {x['locator_actuel']})")
    return "\n".join(out)


def importer_resources(pattern: str = "**/*.resource", s: str | None = None) -> dict:
    """Amorce la carte avec les locators existants des fichiers .resource du projet."""
    crees, elements_total = 0, 0
    for f in projet.PROJECT_DIR.glob(pattern):
        if "app_map" in f.parts:
            continue
        groupes: dict = {}
        section, courant = "", None
        for brut in f.read_text("utf-8", errors="ignore").splitlines():
            if brut.startswith("***"):
                section = brut.strip("* ").lower()
                courant = None
                continue
            if section not in ("variables", "variable"):
                continue
            toks = [t for t in re.split(r"\t+| {2,}", brut.strip()) if t]
            if not toks or toks[0].startswith("#"):
                continue
            if toks[0] == "..." and courant:
                courant[1].extend(toks[1:])
                continue
            m = re.match(r"^([&$])\{(.+?)\}", toks[0])
            if m:
                courant = (m.group(1) + m.group(2), toks[1:])
                groupes.setdefault(f.stem, []).append(courant)
        for nom_fichier, variables in groupes.items():
            par_ecran: dict = {}
            for nom, valeurs in variables:
                plat = "ios" if nom.upper().endswith("_IOS") else "web" if nom.upper().endswith("_WEB") else \
                    "android" if nom.upper().endswith("_ANDROID") else ""
                ecran_nom = re.sub(r"^[&$](LOC_)?|_(ANDROID|IOS|WEB|SECOURS)$", "", nom, flags=re.I)
                ecran_nom = slug(ecran_nom if nom.startswith("&") else nom_fichier)
                paires = [v.split("=", 1) for v in valeurs if "=" in v] if nom.startswith("&") else \
                    [(slug(nom[1:]), valeurs[0])] if valeurs else []
                for cle, loc in paires:
                    if not re.match(r"^(id|accessibility_id|xpath|css|data-testid|role|text|android|nsp|chain|class|name)=|^//", loc):
                        continue
                    p = plat or ("ios" if loc.startswith(("nsp=", "chain=")) else
                                 "web" if loc.startswith(("css=", "data-testid=", "role=", "text=")) else "android")
                    par_ecran.setdefault(ecran_nom, {}).setdefault(cle, {})[p] = loc
            for ecran_nom, els in par_ecran.items():
                try:
                    e = ecran(ecran_nom, s)
                except KeyError:
                    e = {"id": "e_" + hashlib.sha1(ecran_nom.encode()).hexdigest()[:8], "nom": ecran_nom, "module": "",
                         "alias": [], "titre": "", "plateformes": {}, "elements": {}, "etats": [], "changements": [],
                         "utilise_par": [], "essayes": {}, "importe_de": f.relative_to(projet.PROJECT_DIR).as_posix(), "cree": _now()}
                    crees += 1
                for cle, locs in els.items():
                    el = e["elements"].setdefault(cle, {"type": cle.split("_")[0], "libelle": "", "locators": {}})
                    for p, loc in locs.items():
                        el["locators"][p] = list(dict.fromkeys([loc] + (el["locators"].get(p) or [])))[:4]
                        elements_total += 1
                _save_ecran(e, s)
    return {"ecrans_crees": crees, "locators_importes": elements_total}


def exporter_resource(eid: str, chemin_sortie: Path, s: str | None = None) -> Path:
    """Fichier .resource Robot depuis la carte : locator principal + locators de secours (séparés par ||)."""
    e = ecran(eid, s)
    nom = (e.get("nom") or e["id"]).upper()
    lignes = ["*** Settings ***", f"Documentation    Locators de l'écran « {e.get('nom') or e['id']} », générés depuis la carte "
              f"de l'application le {datetime.now():%d/%m/%Y}.",
              "...              Les dictionnaires _SECOURS listent les alternatives (keyword « Localiser » du socle).",
              "", "*** Variables ***"]

    def esc(v):
        v = v.replace("\\", "\\\\")
        return re.sub(r" {2,}", lambda m: " " + "\\ " * (len(m.group()) - 1), v)

    for plat in ("android", "ios", "web"):
        principal, secours = [], []
        for k, el in (e.get("elements") or {}).items():
            locs = (el.get("locators") or {}).get(plat)
            if locs and el.get("type") in INTERACTIFS:
                principal.append(f"{k}={esc(locs[0])}")
                if len(locs) > 1:
                    secours.append(f"{k}={esc(' || '.join(locs[1:]))}")
        for suffixe, items in (("", principal), ("_SECOURS", secours)):
            if items:
                lignes.append(f"&{{LOC_{nom}_{plat.upper()}{suffixe}}}    {items[0]}")
                lignes += [f"...    {i}" for i in items[1:]]
                lignes.append("")
    chemin_sortie.parent.mkdir(parents=True, exist_ok=True)
    chemin_sortie.write_text("\n".join(lignes), "utf-8")
    return chemin_sortie


def resume_ecran(e: dict) -> dict:
    """Vue résumée d'un écran (outils where_am_i, screen_info, name_screen, onglet Carte)."""
    return {"id": e["id"], "nom": e.get("nom", ""), "titre": e.get("titre", ""), "module": e.get("module", ""),
            "plateformes": sorted((e.get("plateformes") or {}).keys()), "etats": [s["nom"] for s in e.get("etats", [])],
            "elements": {k: {"type": v.get("type"), "libelle": v.get("libelle"), "locators": v.get("locators")}
                         for k, v in (e.get("elements") or {}).items()},
            "utilise_par": e.get("utilise_par", []), "a_revoir": e.get("a_revoir", False)}
