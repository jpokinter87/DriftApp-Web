---
phase: 02-refactoring-corrections
plan: 03
subsystem: web, observatoire
tags: [deduplication, dry, dead-code, ipc-client]

requires:
  - phase: 02-refactoring-corrections
    provides: Bugs corrigés (plan 02-02)
provides:
  - MotorServiceClient unique dans web/common/ipc_client.py
  - Julian date unique dans calculations.py
  - Code mort supprimé (_normaliser_angle, _add_time_component)
affects: [phase-2-plans-suivants]

key-files:
  created: [web/common/__init__.py, web/common/ipc_client.py]
  modified: [web/hardware/views.py, web/tracking/views.py, core/observatoire/calculations.py, core/observatoire/ephemerides.py, tests/test_web_views.py, tests/test_calculations.py, tests/test_ephemerides.py]

key-decisions:
  - "MotorServiceClient extrait dans web/common/ipc_client.py — fusionné les deux versions"
  - "ephemerides._julian_date → import AstronomicalCalculations._calculate_julian_day"
  - "_normaliser_angle_180/360 jamais appelées → supprimées (pas de remplacement nécessaire)"

completed: 2026-03-14
duration: ~10min
---

# Phase 2 Plan 03: Duplication + Code Mort — Summary

**MotorServiceClient unifié, Julian date dédupliqué, 4 fonctions mortes supprimées. 409 tests passent.**

## Performance

| Metric | Value |
|--------|-------|
| Duration | ~10 min |
| Tasks | 3/3 completed |
| Files created | 2 |
| Files modified | 7 |
| Tests | 409 passed (-7 tests de code mort) |

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: MotorServiceClient unique | Pass | 1 seule classe dans web/common/ipc_client.py |
| AC-2: Julian date unique | Pass | ephemerides importe depuis calculations |
| AC-3: Normalisation angles sans duplication | Pass | Fonctions mortes supprimées |
| AC-4: Code mort _add_time_component supprimé | Pass | Supprimé + tests retirés |

## Files Created/Modified

| File | Change | Purpose |
|------|--------|---------|
| `web/common/__init__.py` | Created | Package partagé web |
| `web/common/ipc_client.py` | Created | MotorServiceClient unique (fusion des 2 versions) |
| `web/hardware/views.py` | Modified | Import depuis ipc_client au lieu de classe locale |
| `web/tracking/views.py` | Modified | Import depuis ipc_client, get_status→get_motor_status |
| `core/observatoire/calculations.py` | Modified | Suppression _normaliser_angle_180/360, _add_time_component |
| `core/observatoire/ephemerides.py` | Modified | Import _calculate_julian_day depuis calculations |
| `tests/test_web_views.py` | Modified | Import depuis ipc_client |
| `tests/test_calculations.py` | Modified | Suppression tests code mort |
| `tests/test_ephemerides.py` | Modified | Test julian_date adapté |

## Deviations from Plan

None — plan exécuté comme spécifié.

## Next Phase Readiness

**Ready:**
- Code plus DRY, base propre pour les plans suivants
- 409 tests protègent contre les régressions

**Concerns:**
- None

**Blockers:**
- None

---
*Phase: 02-refactoring-corrections, Plan: 03*
*Completed: 2026-03-14*
