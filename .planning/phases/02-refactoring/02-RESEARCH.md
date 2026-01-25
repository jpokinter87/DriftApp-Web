# Phase 2: Refactoring - Research

**Researched:** 2026-01-25
**Domain:** Python refactoring patterns (exceptions, DRY, OCP/command registry)
**Confidence:** HIGH

## Summary

This research investigates the technical patterns needed to implement the refactoring phase without regressions. The phase involves three main areas: (1) creating a custom exception hierarchy for 15 exceptions in core/, (2) centralizing IPC paths and angle normalization for DRY compliance, and (3) implementing a command registry pattern for OCP compliance in motor service command dispatch.

The codebase already has good foundations: `normalize_angle_360()` exists in `core/utils/angle_utils.py`, the `DaemonEncoderReader` already defines `StaleDataError` and `FrozenEncoderError` as custom exceptions, and the command handlers are already factored into separate classes (`GotoHandler`, `JogHandler`, etc.). The refactoring extends these patterns consistently.

**Primary recommendation:** Create `core/exceptions.py` with component-specific exception classes, centralize IPC paths in `core/config/config.py`, replace inline `% 360` with `normalize_angle_360()`, and add a command registry dict in `MotorService.process_command()`.

## Standard Stack

### Core (No New Dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib | 3.11+ | Exception hierarchy, typing | Built-in exception chaining, `add_note()` |
| pytest | existing | Test custom exceptions | Already used for 315+ tests |

### Supporting (Already in Project)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| logging | stdlib | Exception context logging | Log exception attributes on catch |
| pathlib | stdlib | IPC path constants | Already used in config.py |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Single exceptions.py | Per-module exceptions | More files, less cohesion for small project |
| Dict registry | Decorator registry | Decorator magic harder to debug, overkill for 6 commands |
| normalize_angle_360() | Keep inline % 360 | Inconsistency, potential for bugs with negative angles |

**No new dependencies required.**

## Architecture Patterns

### Recommended Exception Module Structure

```python
# core/exceptions.py

class DriftAppError(Exception):
    """Base exception for all DriftApp errors.

    Allows catching all application errors with:
        except DriftAppError as e:
            ...
    """
    pass


class MotorError(DriftAppError):
    """Motor control failure.

    Attributes:
        pin: GPIO pin involved (optional)
        delay: Motor delay in seconds (optional)
        operation: Operation that failed (optional)
    """
    def __init__(self, message: str, *, pin: int = None, delay: float = None, operation: str = None):
        super().__init__(message)
        self.pin = pin
        self.delay = delay
        self.operation = operation


class EncoderError(DriftAppError):
    """Encoder communication failure.

    Attributes:
        daemon_path: Path to daemon JSON file (optional)
        timeout_ms: Timeout that was exceeded (optional)
    """
    def __init__(self, message: str, *, daemon_path: str = None, timeout_ms: int = None):
        super().__init__(message)
        self.daemon_path = daemon_path
        self.timeout_ms = timeout_ms


class AbaqueError(DriftAppError):
    """Abaque loading or interpolation failure.

    Attributes:
        file_path: Path to abaque file (optional)
        altitude: Altitude that caused error (optional)
        azimut: Azimut that caused error (optional)
    """
    def __init__(self, message: str, *, file_path: str = None, altitude: float = None, azimut: float = None):
        super().__init__(message)
        self.file_path = file_path
        self.altitude = altitude
        self.azimut = azimut


class IPCError(DriftAppError):
    """IPC communication failure.

    Attributes:
        file_path: IPC file path (optional)
        operation: read/write (optional)
    """
    def __init__(self, message: str, *, file_path: str = None, operation: str = None):
        super().__init__(message)
        self.file_path = file_path
        self.operation = operation


class ConfigError(DriftAppError):
    """Configuration loading or validation failure.

    Attributes:
        config_path: Path to config file (optional)
        key: Config key that caused error (optional)
    """
    def __init__(self, message: str, *, config_path: str = None, key: str = None):
        super().__init__(message)
        self.config_path = config_path
        self.key = key
```

### IPC Path Centralization Pattern

```python
# In core/config/config.py (add to existing file)
from pathlib import Path

# IPC file paths (centralized)
IPC_BASE = Path("/dev/shm")
IPC_MOTOR_COMMAND = IPC_BASE / "motor_command.json"
IPC_MOTOR_STATUS = IPC_BASE / "motor_status.json"
IPC_ENCODER_POSITION = IPC_BASE / "ems22_position.json"
```

### Command Registry Pattern

```python
# In services/motor_service.py - MotorService class

def _init_handlers(self):
    """Initialise les handlers de commandes."""
    self.goto_handler = GotoHandler(...)
    self.jog_handler = JogHandler(...)
    self.continuous_handler = ContinuousHandler(...)
    self.tracking_handler = TrackingHandler(...)

    # Command registry for OCP compliance
    self._command_registry = {
        'goto': self._handle_goto,
        'jog': self._handle_jog,
        'stop': self.handle_stop,
        'continuous': self._handle_continuous,
        'tracking_start': self._handle_tracking_start,
        'tracking_stop': self._handle_tracking_stop,
        'status': self._handle_status,
    }

def _handle_goto(self, command: Dict[str, Any]):
    angle = command.get('angle', 0)
    speed = command.get('speed')
    self.current_status = self.goto_handler.execute(angle, self.current_status, speed)

def _handle_jog(self, command: Dict[str, Any]):
    delta = command.get('delta', 0)
    speed = command.get('speed')
    self.current_status = self.jog_handler.execute(delta, self.current_status, speed)

# ... other _handle_* methods ...

def process_command(self, command: Dict[str, Any]):
    """Traite une commande recue (OCP compliant)."""
    cmd_type = command.get('command', command.get('type'))

    if not cmd_type:
        logger.warning(f"Commande invalide: {command}")
        return

    logger.info(f"Traitement commande: {cmd_type}")

    handler = self._command_registry.get(cmd_type)
    if handler:
        handler(command)
    else:
        logger.warning(f"Commande inconnue: {cmd_type}")

    self.ipc.clear_command()
```

### Anti-Patterns to Avoid

- **Catching Exception without re-raising:** In daemon code this is intentional, but in core/ business logic it hides bugs
- **Inline `% 360` instead of `normalize_angle_360()`:** Inconsistent, harder to test, edge case handling differs
- **Hardcoded paths in multiple files:** Changes require editing multiple files, easy to miss one
- **Switch-case in process_command:** Violates OCP, requires modifying function to add new commands

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Angle normalization | `x % 360` inline | `normalize_angle_360(x)` | Already exists, handles edge cases, tested |
| Exception hierarchy | Individual RuntimeError | `core/exceptions.py` classes | Consistency, better debugging, typed catching |
| IPC paths | Hardcoded strings | `core/config/config.py` constants | Single source of truth, easy to change |
| Command dispatch | if/elif chain | Dict registry | OCP compliant, O(1) lookup |

**Key insight:** The codebase already has most building blocks (`normalize_angle_360()`, handler classes, config module). The refactoring is about consistent usage, not creating new abstractions.

## Common Pitfalls

### Pitfall 1: Breaking existing exception catches

**What goes wrong:** After renaming `RuntimeError` to `EncoderError`, callers still catching `RuntimeError` miss the new exception.
**Why it happens:** Callers weren't updated when exception type changed.
**How to avoid:**
1. Make new exceptions inherit from `RuntimeError` temporarily (optional, not recommended for clean design)
2. OR grep for all `except RuntimeError` and `except Exception` in calling code
3. Run full test suite after each file change
**Warning signs:** Tests that catch exceptions start failing.

### Pitfall 2: normalize_angle_360 behavior with negative angles

**What goes wrong:** `(-10) % 360` gives `350`, which is correct. But developers might expect `-10`.
**Why it happens:** Python's modulo preserves sign of divisor, which is correct for angles.
**How to avoid:** The existing `normalize_angle_360()` already handles this correctly. Just use it consistently.
**Warning signs:** Position calculations around 0/360 boundary giving unexpected results.

### Pitfall 3: IPC path import order

**What goes wrong:** Circular imports when `config.py` imports from modules that import from `config.py`.
**Why it happens:** IPC paths currently defined in multiple places, changing import structure.
**How to avoid:**
1. Keep IPC constants as simple Path assignments (no function calls)
2. Add constants at module level, not inside functions
3. Test imports work: `python -c "from core.config.config import IPC_MOTOR_COMMAND"`
**Warning signs:** ImportError on startup.

### Pitfall 4: Forgetting exception chaining

**What goes wrong:** Exception traceback loses original cause after `raise NewException(...)`.
**Why it happens:** Missing `from e` in raise statement.
**How to avoid:** Always use `raise NewException(...) from e` when converting exceptions.
**Warning signs:** Incomplete tracebacks in error logs.

### Pitfall 5: Breaking intentional bare exceptions

**What goes wrong:** Changing bare `except:` in daemon code to specific exceptions causes daemon crash.
**Why it happens:** Phase 1 identified 52 intentional exceptions in daemon/hardware code.
**How to avoid:**
1. Only modify the 15 exceptions in core/ identified in exceptions-report.md
2. Do NOT touch ems22d_calibrated.py, scripts/diagnostics/*, or hardware_detector.py
**Warning signs:** Service crashes when hardware fails.

## Code Examples

### Exception with Context Attributes

```python
# Source: Python 3.11+ documentation + project conventions
# File: core/tracking/tracker.py (example replacement)

# BEFORE
try:
    pos = self._get_encoder_angle(timeout_ms=200)
except Exception as e:
    self.logger.warning(f"Encodeur inaccessible: {e}")

# AFTER
from core.exceptions import EncoderError

try:
    pos = self._get_encoder_angle(timeout_ms=200)
except EncoderError as e:
    self.logger.warning(f"Encodeur inaccessible: {e} (timeout={e.timeout_ms}ms)")
```

### Exception Chaining (B904 fix)

```python
# Source: Python docs - Exception Chaining
# File: core/hardware/daemon_encoder_reader.py:142

# BEFORE (B904 violation)
except json.JSONDecodeError as e:
    raise RuntimeError(f"Erreur lecture demon: {e}")

# AFTER
from core.exceptions import EncoderError

except json.JSONDecodeError as e:
    raise EncoderError(
        f"Erreur lecture demon: {e}",
        daemon_path=str(self.daemon_path)
    ) from e
```

### Angle Normalization Replacement

```python
# Source: core/utils/angle_utils.py (existing)
# File: core/hardware/moteur.py:330-331

# BEFORE
position_cible = position_cible_deg % 360
position_actuelle = position_actuelle_deg % 360

# AFTER
from core.utils.angle_utils import normalize_angle_360

position_cible = normalize_angle_360(position_cible_deg)
position_actuelle = normalize_angle_360(position_actuelle_deg)
```

### IPC Path Usage

```python
# Source: Centralized config pattern
# File: services/ipc_manager.py

# BEFORE
COMMAND_FILE = Path("/dev/shm/motor_command.json")
STATUS_FILE = Path("/dev/shm/motor_status.json")
ENCODER_FILE = Path("/dev/shm/ems22_position.json")

# AFTER
from core.config.config import (
    IPC_MOTOR_COMMAND,
    IPC_MOTOR_STATUS,
    IPC_ENCODER_POSITION,
)

COMMAND_FILE = IPC_MOTOR_COMMAND
STATUS_FILE = IPC_MOTOR_STATUS
ENCODER_FILE = IPC_ENCODER_POSITION
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Bare `except:` | Specific exceptions | Python 2.5+ | Better debugging |
| `raise Ex` without `from` | `raise Ex from e` | Python 3.0 | Exception chaining |
| Manual switch-case | Registry dict | Always best practice | OCP compliance |
| Inline `% 360` | `normalize_angle_360()` | Project v4.0 | Consistency |

**Deprecated/outdated:**
- Using `Exception` without attributes: Modern Python favors exception classes with contextual attributes
- Switch-case command dispatch: Registry pattern is cleaner and OCP-compliant

## Open Questions

1. **StaleDataError and FrozenEncoderError placement**
   - What we know: Already defined in `daemon_encoder_reader.py`
   - What's unclear: Should they move to `core/exceptions.py` or stay local?
   - Recommendation: Keep them local since they're specific to that module. They can inherit from `EncoderError` if we want unified catching.

2. **Test coverage for new exceptions**
   - What we know: Need tests for exception attributes and chaining
   - What's unclear: Exact test patterns for contextual attributes
   - Recommendation: Add parametrized tests like `test_encoder_error_attributes()` checking attribute access.

## Sources

### Primary (HIGH confidence)

- [Python 3.14 Built-in Exceptions Documentation](https://docs.python.org/3/library/exceptions.html) - Exception inheritance, chaining, attributes
- Project code review reports (`.planning/phases/01-code-review/reports/`) - Exception locations, DRY patterns

### Secondary (MEDIUM confidence)

- [DEV.to - Python Registry Pattern](https://dev.to/dentedlogic/stop-writing-giant-if-else-chains-master-the-python-registry-pattern-ldm) - Command registry implementation
- [Real Python - Raising Exceptions](https://realpython.com/python-raise-exception/) - Exception best practices
- [Python Custom Exceptions](https://jacobpadilla.com/articles/custom-python-exceptions) - Exception hierarchy patterns

### Tertiary (LOW confidence)

- WebSearch results on Python exception patterns 2025 - General community consensus

## Metadata

**Confidence breakdown:**
- Exception hierarchy: HIGH - Based on Python official docs and existing project patterns
- IPC centralization: HIGH - Mechanical change, low risk
- Command registry: HIGH - Standard pattern, existing handler classes
- Angle normalization: HIGH - Utility already exists, just usage consistency

**Research date:** 2026-01-25
**Valid until:** 2026-02-25 (30 days - stable patterns)

---

## Appendix: Files to Modify

### Exception Changes (15 locations in core/)

| File | Line | Current | Target Exception |
|------|------|---------|------------------|
| `core/config/config.py` | 55 | `except Exception:` | `except (json.JSONDecodeError, OSError):` |
| `core/observatoire/catalogue.py` | 74 | `except Exception:` | `except (json.JSONDecodeError, OSError):` |
| `core/observatoire/catalogue.py` | 91 | `except Exception:` | `except OSError:` |
| `core/observatoire/catalogue.py` | 181 | `except Exception:` | `except (ConnectionError, Timeout, HTTPError):` |
| `core/tracking/abaque_manager.py` | 127 | `except Exception:` | `except (FileNotFoundError, ValueError, KeyError):` |
| `core/tracking/abaque_manager.py` | 251 | `except Exception:` | `except (ValueError, IndexError):` |
| `core/tracking/abaque_manager.py` | 351 | `except Exception:` | `except OSError:` |
| `core/tracking/tracker.py` | 120 | `except Exception:` | `except EncoderError:` |
| `core/tracking/tracker.py` | 258 | `except Exception:` | `except EncoderError:` |
| `core/tracking/tracker.py` | 432 | `except Exception:` | `except (ImportError, OSError):` |
| `core/tracking/tracking_goto_mixin.py` | 99 | `except Exception:` | `except EncoderError:` |
| `core/tracking/tracking_goto_mixin.py` | 160 | `except Exception:` | `except EncoderError:` |
| `core/tracking/tracking_goto_mixin.py` | 218 | `except Exception:` | `except EncoderError:` |
| `core/tracking/tracking_goto_mixin.py` | 232 | `except Exception:` | `except (EncoderError, MotorError):` |
| `core/hardware/daemon_encoder_reader.py` | 142 | B904 missing `from e` | Add `from e` |

### IPC Path Changes (6 locations)

| File | Current | New Import |
|------|---------|------------|
| `core/hardware/daemon_encoder_reader.py` | `DAEMON_JSON = Path("/dev/shm/...")` | `from core.config.config import IPC_ENCODER_POSITION` |
| `core/hardware/encoder_reader.py` | `SHARED_FILE = Path("/dev/shm/...")` | `from core.config.config import IPC_ENCODER_POSITION` |
| `core/hardware/hardware_detector.py` | `daemon_json = Path("/dev/shm/...")` | `from core.config.config import IPC_ENCODER_POSITION` |
| `services/ipc_manager.py` | 3 hardcoded paths | Import from `core.config.config` |

### Angle Normalization Changes (25+ locations)

Files with inline `% 360`:
- `core/hardware/moteur.py` (2)
- `core/hardware/feedback_controller.py` (1)
- `core/hardware/moteur_simule.py` (5)
- `core/hardware/daemon_encoder_reader.py` (1)
- `core/tracking/abaque_manager.py` (2)
- `core/tracking/tracker.py` (3)
- `core/tracking/tracking_state_mixin.py` (2)
- `core/tracking/tracking_corrections_mixin.py` (2)
- `core/tracking/adaptive_tracking.py` (2)
- `core/observatoire/calculations.py` (2)
- `core/observatoire/ephemerides.py` (3)
- `services/command_handlers.py` (3)

### Command Registry Changes (1 location)

- `services/motor_service.py`: Refactor `process_command()` method
