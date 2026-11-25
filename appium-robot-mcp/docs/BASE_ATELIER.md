# Base de l'atelier, comptes et assistant du premier lancement

Décision de l'utilisateur (2026-11-25) : l'atelier devient un outil installable, avec un assistant au lancement qui
règle la base, les comptes et l'espace de travail ; projets, connaissance et configuration doivent être accessibles
depuis plusieurs postes ayant l'atelier ; les accès se donnent par comptes.

## Ce qui va où

| Données | Où | Pourquoi |
|---|---|---|
| Code des tests : suites Robot, ressources, keywords, locators, jeux de données, scénarios BDD | dépôt GitLab des tests (clone = dossier du projet) | revue, merge request, historique |
| Projets, réglages, comptes (phase 1) ; travail en cours (phase 2) ; connaissance (phase 3) | base de l'atelier | partagé entre postes |
| Dossier local de chaque projet, projet actif, emplacement de la base | ~/.atelier/poste.json | propre à la machine |
| Runs et leurs journaux (results/), session du téléphone | poste | lourds, locaux |
| Jetons Xray / Jira / GitLab, clés d'IA | coffre du système du poste | jamais dans la base ni dans un fichier |

## La base

`atelier/domain/magasin.py` : magasin de documents (style NoSQL) — chaque document est un objet JSON rangé par
(collection, clé), avec une version et un journal (qui, quand). Une écriture qui donne la version lue est refusée si
le document a changé entre-temps (`Conflit`) : deux postes ne s'écrasent jamais.

Moteur local : SQLite (bibliothèque standard), un seul fichier `~/.atelier/atelier.db`, mode WAL, aucun service qui
tourne. Emplacement : `ATELIER_BASE`, sinon `~/.atelier/poste.json`, sinon le défaut. Déplacer la base : `exporter()`
(une ligne JSON par document, versions comprises) puis `importer()` (un document n'est remplacé que par une version
plus récente) ; l'assistant le fait en un clic (« copier le contenu »).

## Comptes

`atelier/domain/utilisateurs.py` : comptes dans la base (collection `utilisateurs`). Mot de passe : empreinte
PBKDF2-SHA256 seulement (sel aléatoire, 310 000 itérations, comparaison en temps constant), 12 caractères au moins.
Rôles de `domain/roles.py` (lecteur, automaticien, relecteur, responsable) et projets autorisés (« * » : tous). Le
premier compte est responsable ; il reste toujours un responsable actif. Sessions en mémoire (12 h), cookie HttpOnly
SameSite=Strict ; un compte désactivé ou un mot de passe changé ferme ses sessions.

Tant qu'aucun compte n'existe : mode ouvert (comme avant). Dès qu'un compte existe, toute route `/api/` exige la
connexion (middleware `adapters/web/securite.py`), sauf la connexion et l'état de l'assistant. L'agent (MCP) et les
processus sans compte connecté ont le rôle automaticien : jamais une décision de relecteur.

## Assistant du premier lancement (/assistant)

1. Base : emplacement, copie éventuelle du contenu.
2. Premier compte (responsable), ou « plus tard » (mode ouvert).
3. Espace de travail : projet (nom, dépôt Git des tests, Xray, GitLab) et son dossier sur ce poste — dossier existant
   ou clone du dépôt (Git demande lui-même les identifiants ; une adresse avec identifiant est refusée). Un projet
   créé sur un autre poste apparaît « sans dossier sur ce poste » : il suffit de le cloner ou de choisir son dossier.
4. Connexions : renvoi vers Paramètres › Connexions (jetons dans le coffre du système).

La page de l'atelier y renvoie tant que la base, l'espace de travail ou (sauf « plus tard ») le compte manquent.
Comptes et base ensuite : Paramètres › Comptes et base.

## Travail et connaissance : synchronisation (phases 2 et 3)

`atelier/domain/synchro.py`. La base est la référence partagée ; le dossier du projet en est la copie de travail
locale, celle que les moteurs lisent et écrivent (aucun des moteurs n'a eu à changer). La tâche de fond de l'atelier
fait un passage toutes les 10 s (`ATELIER_SYNCHRO_SECONDES`) sur le projet actif :
- modifié ici → envoyé ; modifié par un autre poste → reçu, et l'écran ouvert se rafraîchit (événement « synchro ») ;
- modifié des deux côtés → la version de la base s'applique, la version locale est gardée à côté
  (`<fichier>.conflit-<poste>-<date>`), le conflit est signalé : rien ne se perd ;
- suppression propagée ; au-delà de 25 fichiers d'un coup, rien n'est supprimé sans confirmation (Paramètres ›
  Comptes et base).

Règles de l'agent : leurs versions (atelier_regles/) sont partagées comme le travail ; leur installation, là où
Cursor et Claude Code les lisent (.cursor/rules/, CLAUDE.md, .claude/skills/, .mcp.json vers le MCP local
http://localhost:8000/mcp), reste propre à chaque poste et se régénère depuis la version active.

Partagés : le travail (conception/ — Kanban, US, lots —, orchestration/, studio/ — revues, demandes à l'agent —,
executions/, gouvernance/, pilotage/, strategie/, testabilite/, validations/, analyses/, atelier_*.yaml) et la
connaissance (app_map/ — carte et captures —, discovery/, parcours/, comportement/ — MBT —, patrimoine/ — instantané
Xray —, couverture/, connaissance/). Non partagés : le code des tests (Git), results/, studio/sessions_agent/,
fichiers temporaires, fichiers de plus de 20 Mo. Collection « fichiers:<projet> » ; état du dernier passage dans
`~/.atelier/synchro/<projet>.json`.

## Serveur de données partagé (phase 4)

`atelier/serveur_donnees.py` (entrée `serveur_donnees.py`, `lancer-serveur-donnees.cmd`) : la même base de documents,
servie en HTTPS à tous les ateliers ; bibliothèque standard (http.server, ssl).

    lancer-serveur-donnees.cmd --base D:teliertelier.db --hote 0.0.0.0 --port 8443 --cert serveur.pem --cle serveur.key

C'est le seul composant qui écoute au-delà de la machine (décision de l'utilisateur, 2026-11-25) : HTTPS obligatoire
hors de la machine, chaque appel authentifié. Droits vérifiés par le serveur : lecture pour tout compte actif
(« fichiers:<projet> » seulement pour les projets ouverts au compte), écriture à partir d'automaticien, comptes par un
responsable (ou soi-même pour son mot de passe), export / import par un responsable. Les empreintes des mots de passe
ne quittent jamais le serveur.

Côté poste (`magasin.BaseDistante`) : la base est l'adresse du serveur (assistant › Base, certificat de l'autorité
facultatif, `ATELIER_SERVEUR_CA`). La connexion à l'atelier est vérifiée par le serveur ; l'atelier garde, par
compte, le jeton du serveur (jamais montré à la page) ; la synchronisation de fond utilise celui du dernier compte
connecté sur le poste, avec ses droits.

Déplacer la base d'un poste vers le serveur : assistant › Base, adresse du serveur, « copier le contenu » — possible
tant que le serveur n'a aucun compte (amorçage : comptes et contenu arrivent ensemble) ; ensuite chacun se connecte avec
son compte du serveur.

### Mettre en place le serveur (SQLite sur une machine de l'équipe)

1. Sur la machine serveur : Python 3.10+, le paquet de l'atelier dézippé (le serveur n'utilise que la bibliothèque
   standard : pas de .venv nécessaire), un certificat HTTPS de l'entreprise pour son nom (serveur.pem + serveur.key).
2. Lancer : `lancer-serveur-donnees.cmd --base D:teliertelier.db --hote 0.0.0.0 --port 8443 --cert serveur.pem --cle serveur.key`.
3. Ouvrir le port 8443 en entrée dans le pare-feu de la machine (réseau de l'entreprise seulement).
4. Démarrage automatique : tâche planifiée Windows « au démarrage » sur la même commande (compte de service).
5. Premier poste : assistant › Base, `https://serveur:8443`, cocher « copier le contenu » (amorçage : la base et les
   comptes de ce poste partent sur le serveur). Autres postes : la même adresse, sans copier, puis se connecter.
6. Sauvegarde : copier le fichier .db du serveur (ou « Exporter la base » dans Paramètres › Comptes et base).

Jamais de fichier .db sur un partage réseau ouvert directement par les postes : SQLite n'y supporte pas les écritures
de plusieurs postes (verrous non fiables, base corrompue) ; l'assistant le refuse.

## Paquet installable (phase 5)

`python outils/paquet.py` → `dist/atelier-<VERSION>.zip` (+ `.sha256`) : le code, les lanceurs, la documentation et
requirements.txt (fichiers suivis et nouveaux du dépôt) ; jamais les tests, .venv, caches, bases ni fichiers ignorés
(.env). Installation : dézipper, double-cliquer `lancer-atelier.cmd` ; le lanceur prépare le poste, propose une fois les
raccourcis « AI Test Platform » (Bureau, menu Démarrer ; `--raccourcis` pour les recréer), puis l'assistant du premier
lancement s'ouvre.

## Phases

1. **Socle** (fait) : base locale, comptes et connexion, droits par projet, projets et réglages dans la base (reprise
   de `~/.atelier-projets.json`), assistant, Paramètres › Comptes et base.
2. **Travail en cours** (fait) : synchronisé par la base (Kanban, US, maintenances, demandes à l'agent, travaux,
   revues, campagnes, gouvernance).
3. **Connaissance** (fait) : synchronisée par la base (carte et captures, Discovery, parcours, MBT, instantané Xray,
   couverture ; le Knowledge Graph se recalcule sur chaque poste).
4. **Serveur partagé** (fait) : serveur de données HTTPS, base distante, déplacement de la base, rafraîchissement en
   direct entre postes.
5. **Paquet installable** (fait) : paquet zip, raccourcis, version affichée par le lanceur.

Restent à décider ou à faire : l'auteur des journaux de certains moteurs est encore le compte Windows (à aligner sur le
compte connecté) ; mise à jour automatique du paquet ; sauvegarde planifiée de la base du serveur.
