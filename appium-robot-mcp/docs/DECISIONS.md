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
