# Plan — surveillance permanente de l'ASIAIR

Spec : `docs/superpowers/specs/2026-10-23-surveillance-asiair-permanente.md`

1. **Config** — `monitor_enabled` (true) dans la section `asiair` du template,
   champ d'`AsiairConfig` + `_parse_asiair`, aide dans `HELP_REGISTRY`.
   → vérifier : `test_config_loader.py`, test de complétude de l'aide.
2. **Service** — `services/asiair_monitor.py` : `Etat` et la boucle repris de la
   sonde ; journal par nuit (`night_key`), purge 14 j (`purge_old`), coupure
   journalisée une fois, lignes INDI ; `main()` avec handlers de log, inactif si
   désactivé ou sans host. Tests de la sonde déplacés vers
   `tests/test_asiair_monitor.py` et complétés (TDD).
   → vérifier : `pytest tests/test_asiair_monitor.py`.
3. **Unité et scripts** — `asiair_monitor.service` (User=slenk) ;
   `update_driftapp.sh` (arrêt, installation, démarrage),
   `restart_services.sh`, `start_web.sh` (démarrage/arrêt/état) ;
   `asiair_sonde.sh` réduit à `etat` ; sonde supprimée.
   → vérifier : `pytest tests/test_ota_restart.py tests/test_health_views.py`.
4. **Vérification locale** — service lancé contre un faux ASIAIR, coupure puis
   retour.
5. **Docs et livraison** — CLAUDE.md (architecture, changelog), skill
   `diag-terrain` (où lire les journaux ASIAIR), ruff, bump 6.25.0, commit + push.
