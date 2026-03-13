# Summary — 01-03: Review Services & Web

**Phase:** 01 - Code Review & Audit
**Plan:** 03 - Services & Web
**Status:** Complete
**Date:** 2026-03-13

## Ce qui a été fait
- Review de 8 fichiers : motor_service.py, hardware/views.py, tracking/views.py, urls.py (×2), settings.py, wsgi.py, urls.py principal
- 20 findings (2 critiques, 5 hauts, 8 moyens, 5 bas)

## Findings clés

### Critiques
1. **SECRET_KEY en dur + DEBUG=True + ALLOWED_HOSTS=['*']** — triple vulnérabilité
2. **MotorServiceClient dupliqué** dans hardware/ et tracking/ — risque de divergence

### Haut impact
- Config parking ignorée (accès à `raw_config` inexistant)
- `calculate_sunset()` approximation incorrecte (~30-60min d'erreur)
- `calculate_sunrise()` timezone en dur pour la France
- Motor_service.py est un God Class (~900 lignes)
- Aucune validation de `speed` dans les API views

## Prochain
Plan 01-04: Review scripts, GUI, intégration globale + synthèse
