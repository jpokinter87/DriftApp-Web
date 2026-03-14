---
phase: 04-refactoring-services
plan: 01
subsystem: services
tags: [thread-safety, validation, ipc, error-recovery, motor-service]

requires:
  - phase: 03-refactoring-core
    provides: core/ stabilisé, angle_utils centralisé
provides:
  - Thread safety sur current_status (status_lock)
  - Validation angles GOTO/JOG (_validate_angle)
  - IPC simplifié (fsync supprimé, clear_command nettoyé)
  - Error recovery uniforme (error_timestamp sur tous les chemins)
affects: [phase-04-plan-02, phase-05-tests]

tech-stack:
  added: []
  patterns:
    - "threading.Lock partagé entre motor_service et ContinuousHandler"
    - "_validate_angle() pour validation entrées commandes"

key-files:
  created: []
  modified:
    - services/command_handlers.py
    - services/motor_service.py
    - services/ipc_manager.py

key-decisions:
  - "Pas de threading pour GOTO/JOG — trop risqué pour un refactoring, à évaluer dans un milestone futur"
  - "Lock uniquement sur ContinuousHandler (seul handler multi-thread)"
  - "fsync supprimé sur tmpfs — no-op coûteux"

patterns-established:
  - "Validation d'entrées via _validate_angle() avant tout mouvement moteur"
  - "status_lock pour accès concurrent au dict current_status"

duration: ~15min
started: 2026-03-14T00:00:00Z
completed: 2026-03-14T00:15:00Z
---

# Phase 4 Plan 01: Issues Critical+High dans services/ — Summary

**Correction de 7 issues Critical+High : thread safety, validation entrées, IPC simplifié, error recovery uniforme.**

## Performance

| Metric | Value |
|--------|-------|
| Duration | ~15 min |
| Tasks | 2 complétées |
| Files modified | 3 (production) |

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: Thread safety current_status | Pass | status_lock dans ContinuousHandler, 3 points with lock |
| AC-2: Validation GOTO/JOG | Pass | _validate_angle rejette NaN, infini, types invalides |
| AC-3: Thread join fiable | Pass | Warning si alive après timeout, refus démarrage si thread actif |
| AC-4: IPC locking simplifié | Pass | fsync supprimé, write('') redondant supprimé |
| AC-5: Error recovery uniforme | Pass | error_timestamp ajouté dans boucle principale |
| AC-6: Pas de régression | Pass | 465 tests verts, ruff check + format clean |

## Accomplishments

- threading.Lock partagé entre motor_service et ContinuousHandler pour protéger current_status [S-01/S-07]
- _validate_angle() rejette NaN, infini, types non-numériques avant tout mouvement [S-09]
- ContinuousHandler.stop() logge warning si thread ne s'arrête pas, start() refuse si thread précédent actif [S-08]
- fsync() supprimé sur tmpfs /dev/shm (no-op coûteux) [S-16]
- error_timestamp ajouté dans le catch de la boucle principale pour recovery automatique [S-04]
- cleanup() met running=False pour cohérence d'état [S-06]
- Watchdog interval documenté (10s vs WatchdogSec=30) [S-03]
- Imports inutilisés supprimés (datetime, DaemonEncoderReader)

## Files Created/Modified

| File | Change | Purpose |
|------|--------|---------|
| `services/command_handlers.py` | Modified | _validate_angle, status_lock dans ContinuousHandler, thread join fiable |
| `services/motor_service.py` | Modified | threading.Lock, error_timestamp boucle principale, cleanup running=False, watchdog doc |
| `services/ipc_manager.py` | Modified | fsync supprimé, write('') redondant supprimé |

## Decisions Made

| Decision | Rationale | Impact |
|----------|-----------|--------|
| Pas de threading GOTO/JOG | Changement architectural risqué pour un refactoring — GOTO/JOG bloquent la boucle mais restent dans la marge watchdog 30s | À évaluer dans un milestone dédié si nécessaire |
| Lock sur ContinuousHandler uniquement | Seul handler avec daemon thread — GOTO/JOG et TrackingHandler opèrent dans le main thread | Minimal et ciblé |
| Validation sans contrainte 0-360 | Un JOG peut être négatif (-10°), seuls NaN/infini/types invalides sont rejetés | Accepte les deltas négatifs légitimes |

## Deviations from Plan

### Summary

| Type | Count | Impact |
|------|-------|--------|
| Auto-fixed | 2 | Imports inutilisés supprimés (ruff F401) |
| Deferred | 0 | — |

**Total impact:** Minimal — nettoyage lint uniquement.

### Skill Audit

| Expected | Invoked | Notes |
|----------|---------|-------|
| /code-review | ○ | Phase non complète (Plan 02 reste) |
| /refactor-code | ○ | Idem — à invoquer après Plan 02 |

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| 18 tests test_motor_service.py échouent | Tests "extra" mal alignés (réfèrent _command_registry, _handle_goto qui n'existent pas) — connu, Phase 5 |
| 2 tests extra (test_moteur_simule, test_tracker_unit) erreurs import | Connu, Phase 5 |

## Next Phase Readiness

**Ready:**
- Issues Critical+High services/ corrigées
- Prêt pour Plan 02 (Medium/Low : session_data trimming, tracking zombie, simulation delays)

**Concerns:**
- 18+2 fichiers tests "extra" avec erreurs → Phase 5

**Blockers:**
- None

---
*Phase: 04-refactoring-services, Plan: 01*
*Completed: 2026-03-14*
