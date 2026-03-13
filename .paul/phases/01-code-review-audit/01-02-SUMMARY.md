# Summary — 01-02: Review Tracking & Observatoire

**Phase:** 01 - Code Review & Audit
**Plan:** 02 - Tracking & Observatoire
**Status:** Complete
**Date:** 2026-03-13

## Ce qui a été fait
- Review de 8 fichiers : tracker.py, adaptive_tracking.py, abaque_manager.py, tracking_logger.py, calculations.py, ephemerides.py, catalogue.py, __init__.py
- 25 findings identifiés (2 critiques, 6 hauts, 10 moyens, 7 bas)

## Findings clés

### Critiques
1. **Référence morte à FAST_TRACK** dans tracker.py (MODE_ICONS, LARGE_MOVEMENT_THRESHOLD)
2. **Chemin relatif** dans catalogue.py pour charger config.json — échoue selon le working directory

### Haut impact
- Tracker appelle `MoteurCoupole` statiquement → simulation cassée pour GOTO initial
- `verify_shortest_path()` duplique `shortest_angular_distance()`
- Résultat incohérent entre planètes et objets SIMBAD (clés `name` vs `nom`, `is_planet` manquant)
- Abaque extrapole silencieusement hors bornes

## Patterns transversaux
- Duplication de code significative (fonctions angulaires, jour Julien)
- Dépendance sur config.py deprecated (catalogue)
- Simulation incomplète (tracker dépend de MoteurCoupole statique)

## Prochain
Plan 01-03: Review Services & Web
