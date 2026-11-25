"""Serveur de données de l'atelier : la base partagée entre postes (docs/BASE_ATELIER.md, phase 4).

    python serveur_donnees.py --base D:\\atelier\\atelier.db --hote 0.0.0.0 --port 8443 --cert serveur.pem --cle serveur.key

La même base de documents que sur un poste (magasin SQLite), servie en HTTPS à tous les ateliers de l'équipe. C'est
le seul composant de l'atelier qui écoute au-delà de la machine (décision de l'utilisateur, 2026-11-25) : HTTPS
obligatoire dès que l'hôte n'est pas la machine elle-même, et chaque appel est authentifié par un compte.

Droits (vérifiés ici, jamais confiés au poste) :
- connexion : identifiant + mot de passe (empreinte PBKDF2 sur le serveur) → jeton de session (12 h) ;
- lecture : tout compte actif ; « fichiers:<projet> » seulement pour les projets ouverts au compte ;
- écriture : automaticien ou plus (un lecteur ne modifie rien) ; comptes : responsable (ou soi-même pour son mot de
  passe) ; la collection des comptes ne se lit ni ne s'écrit par l'accès générique (empreintes jamais rendues) ;
- export et import de toute la base : responsable — sauf l'import d'amorçage d'un serveur encore sans compte (déplacer
  la base d'un poste vers le serveur : les comptes viennent avec, mots de passe compris sous forme d'empreinte).
Bibliothèque standard seulement (http.server, ssl).
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROUTES_LIBRES = ("connexion", "comptes/actifs", "sante")


def _roles():
    from atelier.domain import roles

    return roles


class Gestionnaire(BaseHTTPRequestHandler):
    server_version = "AtelierDonnees/1"
    TAILLE_MAX = 64 * 1024 * 1024

    def log_message(self, fmt, *args):  # jamais d'en-tête (jetons) dans le journal : la ligne de requête suffit
        if os.environ.get("ATELIER_SERVEUR_JOURNAL"):
            sys.stderr.write(f"{self.address_string()} {fmt % args}\n")

    def _repondre(self, code: int, corps: dict):
        donnees = json.dumps(corps, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(donnees)))
        self.end_headers()
        self.wfile.write(donnees)

    def do_GET(self):
        if self.path.rstrip("/") == "/v1/sante":
            return self._repondre(200, {"ok": True, "service": "atelier-donnees"})
        return self._repondre(404, {"detail": "Route inconnue."})

    def do_POST(self):
        from atelier.domain import magasin, utilisateurs

        route = self.path.split("?", 1)[0].removeprefix("/v1/").strip("/")
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > self.TAILLE_MAX:
                return self._repondre(413, {"detail": "Requête trop volumineuse."})
            b = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return self._repondre(400, {"detail": "Corps JSON invalide."})
        jeton = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        u = utilisateurs.session(jeton) if jeton else None
        if route not in ROUTES_LIBRES and not u and not self._amorcage(route):
            return self._repondre(401, {"detail": "Connexion au serveur de données requise."})
        marque = utilisateurs.COURANT.set(u)
        try:
            return self._repondre(200, self._traiter(route, b, u))
        except magasin.Conflit as e:
            return self._repondre(409, {"detail": str(e)})
        except PermissionError as e:
            return self._repondre(403, {"detail": str(e)})
        except KeyError as e:
            return self._repondre(404, {"detail": str(e).strip("'\"")})
        except (ValueError, TypeError) as e:
            return self._repondre(400, {"detail": str(e)})
        except Exception as e:  # noqa: BLE001
            return self._repondre(500, {"detail": f"Erreur du serveur : {str(e)[:200]}"})
        finally:
            utilisateurs.COURANT.reset(marque)

    @staticmethod
    def _amorcage(route: str) -> bool:
        """Serveur encore sans compte : on peut y importer une base (avec ses comptes) ou créer le premier responsable."""
        from atelier.domain import utilisateurs

        return route in ("importer", "comptes/creer") and not utilisateurs.actifs()

    # ------------------------------------------------------------------ droits
    @staticmethod
    def _exiger(u: dict | None, role: str):
        roles = _roles()
        if not u or roles.ORDRE.index(u.get("role", "lecteur")) < roles.ORDRE.index(role):
            raise PermissionError(f"Rôle {role} ou plus requis.")

    @staticmethod
    def _collection(u: dict | None, collection: str, ecriture: bool):
        from atelier.domain import utilisateurs

        if collection == utilisateurs.COLLECTION:
            raise PermissionError("Les comptes se gèrent par les routes comptes/*.")
        if collection.startswith("fichiers:") and not utilisateurs.projet_permis(collection.split(":", 1)[1], u):
            raise PermissionError(f"Projet {collection.split(':', 1)[1]} non ouvert à ce compte.")
        if ecriture:
            Gestionnaire._exiger(u, "automaticien")

    # ------------------------------------------------------------------ routes
    def _traiter(self, route: str, b: dict, u: dict | None) -> dict:
        from atelier.domain import magasin, utilisateurs

        base = magasin.base()
        par = (u or {}).get("identifiant") or str(b.get("par") or "")
        if route == "connexion":
            jeton, compte = utilisateurs.connecter(str(b.get("identifiant", "")), str(b.get("mot_de_passe", "")))
            return {"jeton": jeton, "compte": compte}
        if route == "comptes/actifs":
            return {"actifs": utilisateurs.actifs()}
        if route == "comptes/obtenir":
            ident = str(b.get("identifiant", "")).lower()
            if ident != (u or {}).get("identifiant"):
                self._exiger(u, "responsable")
            return {"compte": utilisateurs.obtenir(ident)}
        if route == "comptes/lister":
            self._exiger(u, "responsable")
            return {"comptes": utilisateurs.lister()}
        if route == "comptes/creer":
            if utilisateurs.actifs():
                self._exiger(u, "responsable")
            return {"compte": utilisateurs.creer(str(b.get("identifiant", "")), str(b.get("mot_de_passe", "")), str(b.get("role", "automaticien")),
                                                 str(b.get("nom", "")), b.get("projets") or ["*"], par)}
        if route == "comptes/modifier":
            self._exiger(u, "responsable")
            return {"compte": utilisateurs.modifier(str(b.get("identifiant", "")), b.get("role"), b.get("projets"), b.get("actif"), b.get("nom"), par=par)}
        if route == "comptes/mot-de-passe":
            ident = str(b.get("identifiant", "")).lower()
            if ident == (u or {}).get("identifiant"):
                if not b.get("ancien"):
                    raise PermissionError("Mot de passe actuel requis.")
                ancien = str(b["ancien"])
            else:
                self._exiger(u, "responsable")
                ancien = None
            return {"compte": utilisateurs.changer_mot_de_passe(ident, str(b.get("nouveau", "")), ancien, par)}
        if route in ("lire", "lister", "versions", "historique"):
            coll = str(b.get("collection", ""))
            self._collection(u, coll, ecriture=False)
            if route == "lire":
                return {"doc": base.lire(coll, str(b.get("cle", "")))}
            if route == "lister":
                return {"docs": base.lister(coll, str(b.get("prefixe", "")))}
            if route == "versions":
                return {"versions": base.versions(coll)}
            return {"historique": base.historique(coll, str(b.get("cle", "")), int(b.get("limite") or 50))}
        if route in ("ecrire", "supprimer"):
            coll = str(b.get("collection", ""))
            self._collection(u, coll, ecriture=True)
            v = b.get("version")
            if route == "ecrire":
                return {"version": base.ecrire(coll, str(b.get("cle", "")), b.get("doc") or {}, None if v is None else int(v), par)}
            return {"supprime": base.supprimer(coll, str(b.get("cle", "")), None if v is None else int(v), par)}
        if route == "info":
            i = base.info()
            return {k: v for k, v in i.items() if k != "chemin"}  # l'emplacement sur le serveur ne regarde pas les postes
        if route == "exporter":
            self._exiger(u, "responsable")
            lignes = []
            cx = base._cx()
            for c, k, doc, v, mod, p in cx.execute("SELECT collection, cle, doc, version, modifie, par FROM documents ORDER BY collection, cle"):
                lignes.append({"collection": c, "cle": k, "doc": json.loads(doc), "version": v, "modifie": mod, "par": p})
            return {"lignes": lignes}
        if route == "importer":
            if utilisateurs.actifs() and not self._amorcage(route):
                self._exiger(u, "responsable")
            f = magasin.dossier_poste() / "imports" / "lot.jsonl"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in b.get("lignes") or []), "utf-8")
            try:
                return base.importer(f, par=par or "import")
            finally:
                f.unlink(missing_ok=True)
        raise KeyError(f"Route inconnue : {route}")


def creer_serveur(hote: str, port: int, cert: str = "", cle: str = "") -> ThreadingHTTPServer:
    locale = hote in ("127.0.0.1", "localhost", "::1")
    if not locale and not (cert and cle):
        raise SystemExit("HTTPS obligatoire hors de la machine : donner --cert et --cle (certificat du serveur).")
    srv = ThreadingHTTPServer((hote, port), Gestionnaire)
    srv.daemon_threads = True
    if cert and cle:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(cert, cle)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    return srv


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Serveur de données de l'atelier (base partagée entre postes).")
    p.add_argument("--base", required=True, help="fichier de la base sur ce serveur (ex. D:\\atelier\\atelier.db)")
    p.add_argument("--hote", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8443)
    p.add_argument("--cert", default="", help="certificat du serveur (PEM)")
    p.add_argument("--cle", default="", help="clé privée du certificat (PEM)")
    a = p.parse_args(argv)
    os.environ["ATELIER_BASE"] = str(Path(a.base).expanduser())
    os.environ.setdefault("ATELIER_DOSSIER", str(Path(a.base).expanduser().parent / ".serveur"))
    srv = creer_serveur(a.hote, a.port, a.cert, a.cle)
    schema = "https" if a.cert else "http"
    print(f"Serveur de données de l'atelier : {schema}://{a.hote}:{a.port} · base {os.environ['ATELIER_BASE']}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
