---
phase: 01-sync-production
plan: 01
subsystem: core
tags: [sync, production, core, services, hardware, tracking]

requires:
  - phase: none
    provides: first plan in milestone
provides:
  - 22 core/ and services/ files synced from production DriftApp_v4_6
affects: [01-02-sync-web-tests, 02-audit-code]

tech-stack:
  added: []
  patterns: []

key-files:
  modified:
    - core/hardware/moteur.py
    - core/tracking/tracker.py
    - services/motor_service.py

key-decisions:
  - "Byte-for-byte copy from production — no modifications"
  - "Preserved core/exceptions.py (Dome_web_v4_6 only)"

patterns-established: []

duration: 2min
completed: 2026-03-14
---

# Phase 1 Plan 01: Sync core/ & services/ Summary

**22 Python files in core/ and services/ replaced with production code from DriftApp_v4_6**

## Performance

| Metric | Value |
|--------|-------|
| Duration | ~2 min |
| Completed | 2026-03-14 |
| Tasks | 3 completed |
| Files modified | 22 |

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: Core files match production | Pass | 19/19 files verified byte-for-byte |
| AC-2: Services files match production | Pass | 3/3 files verified byte-for-byte |
| AC-3: No other files modified | Pass | git diff shows only core/, services/, .paul/ |

## Accomplishments

- 19 core/ files synced (moteur.py, tracker.py, config.py, acceleration_ramp.py, etc.)
- 3 services/ files synced (motor_service.py, command_handlers.py, ipc_manager.py)
- Zero collateral damage — no web, data, or template files touched

## Files Modified

| File | Change | Purpose |
|------|--------|---------|
| core/config/config.py | Replaced | Production version |
| core/hardware/acceleration_ramp.py | Replaced | Production version |
| core/hardware/daemon_encoder_reader.py | Replaced | Production version |
| core/hardware/encoder_reader.py | Replaced | Production version |
| core/hardware/feedback_controller.py | Replaced | Production version |
| core/hardware/hardware_detector.py | Replaced | Production version |
| core/hardware/moteur.py | Replaced | Production version (304 lines diff) |
| core/hardware/moteur_simule.py | Replaced | Production version |
| core/observatoire/calculations.py | Replaced | Production version |
| core/observatoire/catalogue.py | Replaced | Production version |
| core/observatoire/ephemerides.py | Replaced | Production version |
| core/tracking/abaque_manager.py | Replaced | Production version |
| core/tracking/adaptive_tracking.py | Replaced | Production version |
| core/tracking/tracker.py | Replaced | Production version |
| core/tracking/tracking_corrections_mixin.py | Replaced | Production version |
| core/tracking/tracking_goto_mixin.py | Replaced | Production version |
| core/tracking/tracking_state_mixin.py | Replaced | Production version |
| core/utils/__init__.py | Replaced | Production version |
| core/utils/angle_utils.py | Replaced | Production version |
| services/command_handlers.py | Replaced | Production version |
| services/ipc_manager.py | Replaced | Production version |
| services/motor_service.py | Replaced | Production version (148 lines diff) |

## Decisions Made

| Decision | Rationale | Impact |
|----------|-----------|--------|
| Byte-for-byte copy | Ensures exact production parity | No room for error |
| Preserve core/exceptions.py | Only exists in Dome_web_v4_6 | Will be reviewed in Phase 2 audit |

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## Next Phase Readiness

**Ready:**
- core/ and services/ aligned with production
- Plan 01-02 ready for web/, tests/, data/ sync

**Concerns:**
- None

**Blockers:**
- None

---
*Phase: 01-sync-production, Plan: 01*
*Completed: 2026-03-14*
