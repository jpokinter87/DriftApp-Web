---
phase: 02-refactoring
plan: 02
subsystem: config, hardware, tracking, observatoire
tags: [DRY, IPC, angle-normalization, refactoring]

# Dependency graph
requires:
  - phase: 01-code-review
    provides: DRY analysis identifying 6 IPC path duplications and 25+ inline % 360
provides:
  - Centralized IPC paths in core/config/config.py
  - Consistent angle normalization via normalize_angle_360()
  - Single source of truth for IPC file locations
affects: [02-04, 02-05, 02-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Centralized constants for cross-module configuration"
    - "Utility function reuse instead of inline operations"

key-files:
  created: []
  modified:
    - core/config/config.py
    - core/hardware/daemon_encoder_reader.py
    - core/hardware/encoder_reader.py
    - core/hardware/hardware_detector.py
    - core/hardware/moteur.py
    - core/hardware/feedback_controller.py
    - core/hardware/moteur_simule.py
    - core/tracking/abaque_manager.py
    - core/tracking/tracker.py
    - core/tracking/tracking_state_mixin.py
    - core/tracking/tracking_corrections_mixin.py
    - core/tracking/adaptive_tracking.py
    - core/observatoire/calculations.py
    - core/observatoire/ephemerides.py
    - services/ipc_manager.py
    - services/command_handlers.py

key-decisions:
  - "Backward-compatible aliases preserved (DAEMON_JSON, SHARED_FILE, etc.)"
  - "Documentation strings with paths left unchanged (not functional code)"
  - "All 516 tests verified passing after changes"

patterns-established:
  - "IPC paths: import from core.config.config (IPC_MOTOR_COMMAND, etc.)"
  - "Angle normalization: use normalize_angle_360() from core.utils.angle_utils"

# Metrics
duration: 5min
completed: 2026-01-25
---

# Phase 2 Plan 2: DRY - IPC Paths and Angle Normalization Summary

**Centralized IPC file paths and replaced 25+ inline % 360 with normalize_angle_360() utility**

## Performance

- **Duration:** 5 min
- **Started:** 2026-01-25T20:20:58Z
- **Completed:** 2026-01-25T20:25:48Z
- **Tasks:** 3
- **Files modified:** 17

## Accomplishments
- IPC paths defined once in core/config/config.py (IPC_BASE, IPC_MOTOR_COMMAND, IPC_MOTOR_STATUS, IPC_ENCODER_POSITION)
- 4 files updated to import centralized IPC constants
- 25+ inline `% 360` operations replaced with normalize_angle_360() in 12 files
- All 516 tests pass after refactoring

## Task Commits

Each task was committed atomically:

1. **Task 1: Centralize IPC paths** - `ad1028d` (refactor)
2. **Task 2: Replace % 360 with normalize_angle_360()** - `1c5b69b` (refactor)
3. **Task 3: Update CHANGELOG** - `6bf03b3` (docs)

## Files Created/Modified

### IPC Centralization
- `core/config/config.py` - Added IPC_BASE, IPC_MOTOR_COMMAND, IPC_MOTOR_STATUS, IPC_ENCODER_POSITION
- `core/hardware/daemon_encoder_reader.py` - Import IPC_ENCODER_POSITION, alias DAEMON_JSON
- `core/hardware/encoder_reader.py` - Import IPC_ENCODER_POSITION, alias SHARED_FILE
- `core/hardware/hardware_detector.py` - Use IPC_ENCODER_POSITION constant
- `services/ipc_manager.py` - Import all 3 IPC constants, preserve aliases

### Angle Normalization
- `core/hardware/daemon_encoder_reader.py` - 1 occurrence
- `core/hardware/moteur.py` - 2 occurrences
- `core/hardware/feedback_controller.py` - 1 occurrence
- `core/hardware/moteur_simule.py` - 6 occurrences
- `core/tracking/abaque_manager.py` - 2 occurrences
- `core/tracking/tracker.py` - 3 occurrences
- `core/tracking/tracking_state_mixin.py` - 2 occurrences
- `core/tracking/tracking_corrections_mixin.py` - 2 occurrences
- `core/tracking/adaptive_tracking.py` - 2 occurrences
- `core/observatoire/calculations.py` - 3 occurrences
- `core/observatoire/ephemerides.py` - 3 occurrences
- `services/command_handlers.py` - 3 occurrences

## Decisions Made
- Preserved backward-compatible aliases (DAEMON_JSON, SHARED_FILE, COMMAND_FILE, etc.) to avoid breaking existing imports
- Left documentation strings containing paths unchanged since they're informational, not functional
- Did not modify scripts/diagnostics/ or ems22d_calibrated.py as they are intentionally standalone

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all changes were straightforward search-and-replace operations.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- DRY improvements complete for IPC and angle normalization
- Codebase now uses consistent patterns for:
  - IPC file paths (single source in config.py)
  - Angle normalization (utility function)
- Ready for remaining refactoring plans (02-04 through 02-06)

---
*Phase: 02-refactoring*
*Completed: 2026-01-25*
