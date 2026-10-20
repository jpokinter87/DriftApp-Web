# Plan — import des coordonnées ASIAIR

Spec : `docs/superpowers/specs/2026-10-20-import-coordonnees-asiair.md`

1. **Config** — section `asiair` dans `data/config.template.json`,
   `AsiairConfig` + `_parse_asiair` dans `config_loader.py`.
   → vérifier : tests `test_config_loader.py` (section présente / absente),
   test de complétude de l'aide de la page Configuration vert.
2. **Client** — `core/hardware/asiair_client.py` (`lire_coordonnees`,
   `AsiairError`), TDD contre un serveur TCP local dans
   `tests/test_asiair_client.py`.
   → vérifier : nominal, événements parasites, erreur JSON-RPC, champs
   manquants, délai, connexion refusée.
3. **API** — `AsiairCoordsView` + route `asiair/` dans `web/tracking/`.
   → vérifier : tests vue (succès avec infos méridien, host vide 400, échec 502).
4. **Dashboard** — bouton `#btn-asiair`, `importAsiair()`, paramètre de libellé
   sur `applyManualCoords`.
   → vérifier : stack dev + faux serveur ASIAIR local, rendu 1280×720, suivi
   démarré avec les coordonnées importées.
5. **Livraison** — CLAUDE.md (changelog), bump 6.23.0, ruff, suite complète,
   commit + push ; note pour Serge (test M31 + réponse complète).
