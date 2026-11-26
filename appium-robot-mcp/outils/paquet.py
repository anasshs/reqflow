"""Paquet installable de l'atelier : dist/atelier-<version>.zip (docs/BASE_ATELIER.md, phase 5).

    python outils/paquet.py            # construit le paquet à partir des fichiers du dépôt (suivis et nouveaux)

Contenu : le code de l'atelier, ses lanceurs (lancer-atelier.cmd / .sh, lancer-serveur-donnees.cmd), la documentation
et requirements.txt ; jamais les tests, les environnements (.venv), les caches, ni un fichier ignoré par Git (.env…).
Installation sur un poste : dézipper, double-cliquer lancer-atelier.cmd ; le lanceur prépare le poste (Python, .venv,
dépendances, navigateur), propose les raccourcis, puis l'assistant du premier lancement règle base, compte et espace.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
EXCLUS = ("tests/", "dist/", ".venv/", "outils/paquet.py")
SUFFIXES_EXCLUS = (".pyc", ".env", ".db", ".sqlite", ".log")

LISEZMOI = """AI Test Platform {version}

Installer sur un poste (Windows) :
  1. Dézipper ce dossier (par exemple dans Documents\atelier).
  2. Double-cliquer lancer-atelier.cmd : il installe ce qui manque (Python, environnement, dépendances, navigateur),
     propose les raccourcis « AI Test Platform » (Bureau, menu Démarrer), puis ouvre l'atelier.
  3. L'assistant du premier lancement règle la base (locale, ou l'adresse du serveur de l'équipe), le compte,
     l'espace de travail (clone du dépôt GitLab des tests) et les connexions.
Linux / macOS : ./lancer-atelier.sh

Serveur de données de l'équipe (une machine joignable par tous les postes) :
  lancer-serveur-donnees.cmd --base D:\atelier\atelier.db --hote 0.0.0.0 --port 8443 --cert serveur.pem --cle serveur.key
  (HTTPS obligatoire hors de la machine ; voir docs/BASE_ATELIER.md)
"""


def fichiers() -> list[str]:
    r = subprocess.run(["git", "-C", str(RACINE), "ls-files", "--cached", "--others", "--exclude-standard"],
                       capture_output=True, text=True, encoding="utf-8", check=True)
    return sorted(f for f in r.stdout.splitlines()
                  if f and not f.startswith(EXCLUS) and not f.endswith(SUFFIXES_EXCLUS) and "__pycache__" not in f and (RACINE / f).is_file())


def construire(sortie: Path | None = None) -> dict:
    version = (RACINE / "VERSION").read_text("utf-8").strip()
    sortie = sortie or RACINE / "dist" / f"atelier-{version}.zip"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    liste = fichiers()
    with zipfile.ZipFile(sortie, "w", zipfile.ZIP_DEFLATED) as z:
        for f in liste:
            z.write(RACINE / f, f"atelier/{f}")
        z.writestr("atelier/LISEZMOI-INSTALLATION.txt", LISEZMOI.format(version=version))
    empreinte = hashlib.sha256(sortie.read_bytes()).hexdigest()
    (sortie.parent / (sortie.name + ".sha256")).write_text(f"{empreinte}  {sortie.name}\n", "utf-8")
    return {"paquet": str(sortie), "version": version, "fichiers": len(liste), "sha256": empreinte}


if __name__ == "__main__":
    r = construire(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
    print(f"Paquet {r['version']} : {r['paquet']} ({r['fichiers']} fichiers)\nSHA-256 {r['sha256']}")
