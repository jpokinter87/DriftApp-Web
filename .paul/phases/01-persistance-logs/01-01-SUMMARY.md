---
phase: 01-persistance-logs
plan: 01
subsystem: logging
tags: [retention, logs, session-storage, robustness]

requires:
  - phase: none
    provides: first plan in milestone v5.2
provides:
  - Rétention temporelle 7 jours sur logs moteur, Django et sessions
  - Sauvegarde session robuste (fallback si stop() échoue)
affects: [02-bug-retournement-meridien, 04-programme-tests-terrain]

tech-stack:
  added: []
  patterns:
    - "Rétention par âge (MAX_*_AGE_DAYS) au lieu de par nombre de fichiers"
    - "Fallback sauvegarde dans TrackingHandler.stop()"

key-files:
  created:
    - tests/test_log_retention.py
  modified:
    - services/motor_service.py
    - web/session/session_storage.py
    - web/driftapp_web/settings.py
    - core/tracking/tracker.py
    - services/command_handlers.py
    - tests/test_session_storage.py

key-decisions:
  - "Rétention 7 jours avec fallback de sécurité (200/500 fichiers max)"
  - "try/except autour de _log_session_summary pour garantir la sauvegarde"
  - "Fallback _save_session_to_file si session.stop() échoue"

patterns-established:
  - "Cleanup par âge : cutoff = time.time() - (MAX_AGE_DAYS * 86400)"
  - "Sauvegarde session toujours exécutée même si étapes précédentes échouent"

duration: ~15min
completed: 2026-03-15
---

# Phase 1 Plan 01: Persistance Logs — Summary

**Rétention temporelle 7 jours sur 3 types de fichiers + sauvegarde session robuste — 754 tests verts.**

## Performance

| Metric | Value |
|--------|-------|
| Duration | ~15 min |
| Completed | 2026-03-15 |
| Tasks | 3 completed |
| Files modified | 6 (5 production + 1 test adapté) |
| Files created | 1 (tests) |
| Tests | 746 → 754 (+8 nouveaux) |

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: Rétention temporelle 7 jours | Pass | 3 cleanups convertis (motor_service, session_storage, Django settings) |
| AC-2: Sauvegarde session robuste | Pass | try/except dans tracker.stop(), fallback dans TrackingHandler.stop() |
| AC-3: Pas de régression | Pass | 754 tests verts, 0 échecs |

## Accomplishments

- Rétention par âge (7 jours) au lieu de par nombre de fichiers sur logs moteur (MAX_LOG_FILES=20 → MAX_LOG_AGE_DAYS=7), sessions (MAX_SESSIONS=100 → MAX_SESSION_AGE_DAYS=7) et logs Django (MAX_DJANGO_LOG_FILES=20 → MAX_DJANGO_LOG_AGE_DAYS=7)
- Fallback de sécurité sur nombre absolu (200 logs, 500 sessions) pour éviter accumulation extrême
- tracker.stop() protégé : _save_session_to_file() s'exécute même si _log_session_summary() lève une exception
- TrackingHandler.stop() avec fallback : si session.stop() échoue, tente quand même _save_session_to_file()
- Log explicite quand une session précédente est arrêtée pour démarrer une nouvelle cible

## Files Created/Modified

| File | Change | Purpose |
|------|--------|---------|
| `services/motor_service.py` | Modified | cleanup_old_logs : rétention 7j + fallback 200 fichiers |
| `web/session/session_storage.py` | Modified | _cleanup_old_sessions : rétention 7j + fallback 500 fichiers |
| `web/driftapp_web/settings.py` | Modified | _cleanup_old_django_logs : rétention 7j + fallback 200 fichiers |
| `core/tracking/tracker.py` | Modified | stop() robuste : try/except autour de _log_session_summary |
| `services/command_handlers.py` | Modified | TrackingHandler.stop() fallback + log changement cible |
| `tests/test_log_retention.py` | Created | 8 tests : rétention par âge (3) + fallback (2) + robustesse (3) |
| `tests/test_session_storage.py` | Modified | 2 tests adaptés pour rétention par âge (au lieu de par nombre) |

## Decisions Made

| Decision | Rationale | Impact |
|----------|-----------|--------|
| Rétention 7j + fallback nombre | Évite suppression de logs utiles tout en prévenant accumulation extrême | Fichiers préservés plus longtemps sur terrain |
| try/except _log_session_summary | La perte de logs est plus grave que la perte du résumé | Session toujours sauvegardée |
| Fallback _save_session_to_file | Si stop() échoue (exception tracking), les données sont quand même persistées | Zéro perte silencieuse |

## Deviations from Plan

### Summary

| Type | Count | Impact |
|------|-------|--------|
| Auto-fixed | 1 | Tests existants adaptés (MAX_SESSIONS renommé) |
| Deferred | 0 | — |

**Total impact:** Minimal — adaptation tests uniquement.

### Auto-fixed Issues

**1. Tests test_session_storage.py cassés par renommage**
- **Found during:** Task 3 (vérification suite complète)
- **Issue:** 2 tests référençaient MAX_SESSIONS (supprimé, remplacé par MAX_SESSION_AGE_DAYS)
- **Fix:** Tests réécrits pour vérifier la rétention par âge
- **Verification:** 754 tests verts

## Issues Encountered

None.

## Next Phase Readiness

**Ready:**
- Logs persistés par cible avec rétention 7 jours
- Sauvegarde session robuste (aucune perte silencieuse possible)
- Phase 2 (Bug Retournement Méridien) peut bénéficier des logs persistés pour diagnostic

**Concerns:**
- None

**Blockers:**
- None

---
*Phase: 01-persistance-logs, Plan: 01*
*Completed: 2026-03-15*
