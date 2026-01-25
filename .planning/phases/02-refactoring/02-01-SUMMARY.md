---
phase: 02-refactoring
plan: 01
subsystem: core
tags: [exceptions, error-handling, debugging, python]

# Dependency graph
requires:
  - phase: 01-code-review
    provides: exceptions-report.md identifying 15 bare exceptions to fix
provides:
  - core/exceptions.py with DriftAppError hierarchy (6 exception classes)
  - EncoderError, MotorError, AbaqueError, IPCError, ConfigError
  - Exception chaining (from e) for better debugging
affects: [02-02, 02-03, 02-04, 02-05, 02-06]

# Tech tracking
tech-stack:
  added: []
  patterns: [custom-exception-hierarchy, exception-chaining]

key-files:
  created:
    - core/exceptions.py
    - tests/test_exceptions.py
    - .planning/phases/02-refactoring/CHANGELOG.md
  modified:
    - core/config/config.py
    - core/observatoire/catalogue.py
    - core/tracking/abaque_manager.py
    - core/tracking/tracker.py
    - core/tracking/tracking_goto_mixin.py
    - core/hardware/daemon_encoder_reader.py
    - tests/test_abaque_manager.py

key-decisions:
  - "Keep RuntimeError as fallback in except clauses alongside EncoderError for compatibility"
  - "Use built-in exceptions (ConnectionError, TimeoutError) for SIMBAD queries instead of requests.exceptions"
  - "8 remaining BLE001 violations in hardware_detector.py and moteur.py are intentional"

patterns-established:
  - "Exception hierarchy: DriftAppError as base for all DriftApp-specific errors"
  - "Exception attributes: keyword-only args with None defaults for context"
  - "Exception chaining: always use 'from e' when re-raising"

# Metrics
duration: 5min
completed: 2026-01-25
---

# Phase 2 Plan 01: Exception Hierarchy Summary

**Custom exception hierarchy with DriftAppError base, 5 specific exception classes, and 15 bare exceptions replaced with typed catching**

## Performance

- **Duration:** 5 min
- **Started:** 2026-01-25T20:13:42Z
- **Completed:** 2026-01-25T20:18:02Z
- **Tasks:** 3
- **Files modified:** 10

## Accomplishments

- Created core/exceptions.py with 6 exception classes (DriftAppError + 5 specific types)
- Replaced 15 bare `except Exception:` in core/ with specific exception types
- Fixed B904 violation by adding `from e` exception chaining in daemon_encoder_reader.py
- Added 39 tests for exception hierarchy, attributes, and chaining

## Task Commits

Each task was committed atomically:

1. **Task 1: Create exception hierarchy module** - `614d85e` (feat)
2. **Task 2: Replace 15 bare exceptions** - `a39d2e6` (fix)
3. **Task 3: Document changes** - `157f0cd` (docs)

## Files Created/Modified

- `core/exceptions.py` - DriftAppError, MotorError, EncoderError, AbaqueError, IPCError, ConfigError
- `tests/test_exceptions.py` - 39 tests for hierarchy, attributes, chaining
- `core/config/config.py` - except (JSONDecodeError, OSError)
- `core/observatoire/catalogue.py` - 3 specific exception handlers
- `core/tracking/abaque_manager.py` - 3 specific exception handlers
- `core/tracking/tracker.py` - EncoderError import + 3 handlers
- `core/tracking/tracking_goto_mixin.py` - EncoderError/MotorError imports + 4 handlers
- `core/hardware/daemon_encoder_reader.py` - EncoderError with `from e` chaining
- `tests/test_abaque_manager.py` - Updated mock to use ValueError
- `.planning/phases/02-refactoring/CHANGELOG.md` - Change documentation

## Decisions Made

1. **Keep RuntimeError alongside EncoderError** - DaemonEncoderReader may still raise RuntimeError, so we catch both to maintain compatibility
2. **Use built-in exceptions for network errors** - ConnectionError, TimeoutError, OSError are sufficient for SIMBAD queries without importing requests.exceptions
3. **Leave hardware exceptions intentional** - 8 BLE001 violations in hardware_detector.py and moteur.py are intentional for graceful hardware probing

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test mock raised generic Exception**
- **Found during:** Task 2 (test verification)
- **Issue:** test_abaque_manager.py test_load_erreur_lecture raised generic Exception which was no longer caught by specific handler
- **Fix:** Changed mock to raise ValueError instead
- **Files modified:** tests/test_abaque_manager.py
- **Verification:** Test passes with ValueError
- **Committed in:** a39d2e6 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 bug fix)
**Impact on plan:** Test needed update to match new exception handling. No scope creep.

## Issues Encountered

None - plan executed as specified.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Exception hierarchy complete and tested
- All 494 tests pass (excluding pre-existing test_motor_service.py issues)
- Ready for plan 02-02 (IPC path centralization) and subsequent refactoring plans
- Future code can use `from core.exceptions import EncoderError, MotorError` for typed exception handling

---
*Phase: 02-refactoring*
*Completed: 2026-01-25*
