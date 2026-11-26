"""Point d'entrée du serveur de données de l'atelier (base partagée entre postes) : atelier/serveur_donnees.py.

    python serveur_donnees.py --base D:\atelier\atelier.db --hote 0.0.0.0 --port 8443 --cert serveur.pem --cle serveur.key
"""
from atelier.serveur_donnees import main

if __name__ == "__main__":
    raise SystemExit(main())
