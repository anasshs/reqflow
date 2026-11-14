# Décisions

Une ligne datée par décision d'architecture ou de conception.

- 2026-11-14 : MCP et interface web deviennent des façades ; logique dans quatre moteurs (découverte, intelligence, génération, exécution).
- 2026-11-14 : YAML versionné reste la source de vérité de la connaissance ; base relationnelle seulement si multi-utilisateurs.
- 2026-11-14 : `mcp` épinglé en `<2` : mcp 2.x supprime `mcp.server.fastmcp` et le serveur ne démarrait plus sur une installation neuve ; migration vers `MCPServer` à planifier séparément (risque sur la rétrocompatibilité des outils).
- 2026-11-14 : outils partagés dans `atelier/adapters/facade.py` (mêmes noms, signatures et docstrings que les outils MCP) ; le MCP les enregistre, l'interface web et l'agent intégré les appellent. Aucune des deux façades n'importe plus `server.py`.
- 2026-11-14 : chemin du projet de tests lu au moment de l'appel dans `atelier.domain.projet` (un seul point de réglage) ; plus de constantes `PROJECT_DIR` recopiées dans chaque module.
- 2026-11-14 : les anciens modules racine (`server.py`, `app_map.py`, `jdd.py`, `xray_client.py`, `web_backend.py`, listeners, `web/app.py`) restent des points d'entrée qui désignent les nouveaux modules (`sys.modules`) : configurations Cursor / Claude Desktop et commandes CI inchangées.
- 2026-11-14 : bus d'événements `atelier/domain/evenements.py` ; le surlignage n'est calculé que si un abonné l'écoute (même comportement qu'avec `WEB_EVENTS_URL` / `EVENT_HOOK`). `WEB_EVENTS_URL` reste le réglage du relais MCP → interface.
- 2026-11-14 : délai des appels Oracle plafonné (`DB_TIMEOUT_MS`, 30 s par défaut) : l'invariant 2 l'exigeait, le prototype ne l'appliquait pas.
- 2026-11-14 : interface web protégée par un middleware ASGI unique (`atelier/adapters/web/securite.py`) qui couvre HTTP et WebSocket : Host, Origin, Sec-Fetch-Site, jeton de session en cookie HttpOnly SameSite=Strict, taille plafonnée. Documentation OpenAPI (/docs) désactivée.
- 2026-11-14 : jeton des processus locaux (listener Robot, MCP de Cursor) distinct du jeton de session, seul accepté sur `/api/events` et `/api/externe/*`. Source : `ATELIER_JETON_EVENEMENTS`, sinon généré au démarrage et écrit dans `~/.atelier-automatisation.jeton` (droits 600) pour que le MCP lancé par Cursor le trouve sans configuration. Ce n'est pas un secret métier (valable pour une seule exécution de l'interface, local), d'où l'exception à la règle « jamais sur disque ».
- 2026-11-14 : journal Xray par run dans `results/<dossier>/xray/<horodatage>/` (un nouveau run n'écrase jamais les événements non envoyés du précédent) ; `python -m atelier xray-sync <dossier>` rejoue un run ou tous les runs sous un dossier.
- 2026-11-14 : la préparation de la cible Xray (plan, exécution, ajout au plan) est mémorisée étape par étape dans `xray_outbox.etat.json` : une reprise ne recrée jamais un plan ou une exécution. Limite connue : si Xray crée l'objet mais que la réponse se perd, la reprise le recrée (pas de clé d'idempotence côté Xray).
- 2026-11-14 : synchronisation strictement dans l'ordre du journal ; arrêt au premier événement en échec après tous les essais (les suivants dépendent de la préparation). Erreurs définitives (ticket cible qui est un Test, test absent de l'exécution) marquées « ignoré » pour ne pas bloquer le rejeu.
- 2026-11-14 : le client Xray distingue les erreurs GraphQL (clé inconnue) des erreurs de transport (`ErreurGraphQL`) : une coupure n'est plus jamais prise pour « ticket autre » ou « test inconnu » (défaut du prototype : résultats perdus en silence).
- 2026-11-14 : en fin de run, le listener attend au plus `XRAY_SYNC_DELAI_FIN` (30 s) puis rend la main ; le reste part au rejeu.
