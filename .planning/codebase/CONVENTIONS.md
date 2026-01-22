# Coding Conventions

**Analysis Date:** 2026-01-22

## Naming Patterns

**Files:**
- Snake case for all Python files: `angle_utils.py`, `motor_service.py`, `feedback_controller.py`
- Test files follow pattern: `test_*.py` (e.g., `test_moteur.py`, `test_angle_utils.py`)
- Config files use underscores: `motor_config_parser.py`, `daemon_encoder_reader.py`

**Functions:**
- Snake case: `normalize_angle_360()`, `get_daemon_reader()`, `rotation_avec_feedback()`
- Private functions prefixed with `_`: `_init_gpio()`, `_charger_config()`, `_verify_gpio_available()`
- Static methods in classes: `@staticmethod def get_daemon_angle()`
- Getter functions prefixed with `get_`: `get_motor_config()`, `get_daemon_reader()`

**Variables:**
- Snake case for local variables: `current_pos`, `delta_deg`, `feedback_controller`
- Constants in UPPER_CASE: `MOTOR_STEPS_PER_REV`, `SIMULATION`, `DAEMON_JSON`
- Private attributes prefixed with `_`: `self._config`, `self.stop_requested`
- Global module-level singletons: `_daemon_reader = None`

**Types:**
- Type hints on function signatures: `def read_angle(timeout_ms: int = 200) -> float:`
- Use `Optional[]` from typing for optional returns: `Optional[Dict[str, Any]]`
- Use `Tuple[]` for multiple returns: `Tuple[float, float]` (e.g., in `_calculate_current_coords()`)
- Union types for multiple accepted types: `moteur: Optional[MoteurCoupole | MoteurSimule]`
- Dataclass use: See `motor_config_parser.py` for structured config objects

**Classes:**
- PascalCase: `MoteurCoupole`, `TrackingSession`, `DaemonEncoderReader`
- Mixin classes: `TrackingStateMixin`, `TrackingGotoMixin`, `TrackingCorrectionsMixin`
- Handler classes: `GotoHandler`, `JogHandler`, `ContinuousHandler`, `TrackingHandler`

## Code Style

**Formatting:**
- Black formatter configured with 100 character line length: `line-length = 100`
- Target Python 3.11+: `target-version = "py311"`
- No trailing whitespace
- Two blank lines between top-level definitions
- One blank line between method definitions in classes

**Linting:**
- Ruff with 100 character line length
- Configuration in `pyproject.toml`: `[tool.ruff]` and `[tool.black]`
- Run formatting: `black core/ services/ web/`
- Run linting: `ruff check core/ services/ web/`

**Line Length:**
- Maximum 100 characters (enforced by Black and Ruff)
- Indent continuation lines with 4 spaces
- Example from `services/motor_service.py`:
```python
self.logger.info(
    f"Moteur initialisé (lgpio) - "
    f"Steps/tour coupole: {self.steps_per_dome_revolution}"
)
```

## Import Organization

**Order:**
1. Future imports: `from __future__ import annotations`
2. Standard library: `import json`, `from pathlib import Path`, `from typing import Dict, Any`
3. Third-party: `from rest_framework import status`, `import numpy`, `import astropy`
4. Local imports: `from core.config.config import get_motor_config`, `from services.ipc_manager import IpcManager`

**Path Aliases:**
- No aliases configured
- Use full relative imports from project root: `from core.utils.angle_utils import normalize_angle_360`
- Module re-exports for compatibility: See `core/hardware/moteur.py` re-exporting from `daemon_encoder_reader.py`

**Path Patterns:**
```python
# Correct: Full import from project root
from core.config.config import get_site_config
from core.hardware.moteur import MoteurCoupole
from services.ipc_manager import IpcManager

# Correct: Re-export in __init__.py
from core.hardware.daemon_encoder_reader import (
    DAEMON_JSON,
    DaemonEncoderReader,
    get_daemon_reader,
)
```

## Error Handling

**Patterns:**
- Catch specific exceptions, not generic `Exception`
- Recent pattern (v4.6+): Replace `except Exception:` with specific types like `except (RuntimeError, ValueError, OSError):`
- Example from `services/command_handlers.py`:
```python
try:
    # Operation code
except (RuntimeError, ValueError, OSError) as e:
    logger.error(f"Erreur GOTO: {e}")
    current_status['status'] = 'error'
    current_status['error'] = str(e)
```

**Raise Usage:**
- Raise with descriptive messages: `raise ValueError("abaque_file requis")`
- Include context: `raise RuntimeError("lgpio non disponible. Installez: ...")`
- Static methods may raise for invalid states: `get_daemon_angle()` raises `RuntimeError` if daemon unavailable

**Graceful Degradation:**
- Silent fallback for missing files: `_load_json()` returns `{}` if file missing
- Fallback GPIO chip selection: Try chip 4 (Pi 5), fall back to chip 0 (Pi 4)
```python
try:
    self.gpio_handle = lgpio.gpiochip_open(4)  # Pi 5
except lgpio.error:
    self.gpio_handle = lgpio.gpiochip_open(0)  # Fallback Pi 4
```

## Logging

**Framework:** Standard Python `logging` module

**Pattern:**
- One logger per module: `logger = logging.getLogger(__name__)`
- Named loggers in classes: `self.logger = logging.getLogger(__name__)`
- Use f-strings for messages: `logger.info(f"Position: {pos:.1f}°")`

**Levels:**
- `logger.info()`: Operational events (init complete, mode change, GOTO started)
- `logger.warning()`: Recoverable issues (timeout, degraded mode, calibration warning)
- `logger.error()`: Errors that affect operation (GPIO failure, IPC unavailable)
- No `debug()` used in regular code (too verbose)

**Examples from `core/hardware/moteur.py`:**
```python
self.logger.info(f"Moteur initialisé (lgpio) - Steps/tour coupole: {self.steps_per_dome_revolution}")
self.logger.warning(f"Délai {delai:.6f}s < minimum {delai_min:.6f}s")
self.logger.error(f"Erreur init lgpio: {e}")
```

**Session Logging:**
- TrackingLogger class (`core/tracking/tracking_logger.py`) wraps standard logging for tracking UI
- Separate log file per tracking session with timestamp and object name
- Log rotation in `services/motor_service.py` via `rotate_log_for_tracking()`

## Comments

**When to Comment:**
- Comment complex algorithms: e.g., S-curve acceleration math in `acceleration_ramp.py`
- Comment non-obvious design decisions: e.g., why DaemonEncoderReader is external in moteur.py
- Do NOT comment obvious code: `x = x + 1  # increment x` is bad
- Comment integration points: IPC file locations, daemon expectations

**Style:**
- Use full sentences with capital letter: `# Ouvrir le chip GPIO`
- French comments for code following French docstrings
- Inline comments after code: `if delta > 0:  # Sens horaire`
- Block comments above code sections:
```python
# =========================================================================
# INITIALISATION (méthodes privées)
# =========================================================================
```

**Docstrings (French):**
- Module docstring at top: Describes purpose, version, usage
- Function docstrings: Args, Returns, Raises, Examples (using Google style with French text)
- Class docstrings: Brief purpose, key characteristics
- Type annotations in docstrings included alongside code type hints

**Example from `core/utils/angle_utils.py`:**
```python
def normalize_angle_360(angle: float) -> float:
    """
    Normalise un angle dans l'intervalle [0, 360[.

    Args:
        angle: Angle en degrés (peut être négatif ou > 360)

    Returns:
        Angle normalisé entre 0 et 360 (exclus)

    Examples:
        >>> normalize_angle_360(370)
        10.0
        >>> normalize_angle_360(-10)
        350.0
    """
    return angle % 360
```

## Function Design

**Size:**
- Methods under 50 lines typical
- Private helper methods extract complex logic
- Example: `_execute_large_goto()` in `GotoHandler` separates large movement optimization

**Parameters:**
- Use dataclasses or dicts for multiple config parameters
- Callbacks passed as `Callable` type hints: `status_callback: Callable`
- Timeout parameters in milliseconds: `timeout_ms: int = 200`
- Speed parameters as floats (seconds): `vitesse: float`

**Return Values:**
- Single return preferred, tuple for related values: `Tuple[float, float]` for (azimuth, altitude)
- Dicts for complex status: `Dict[str, Any]` with keys like `'status'`, `'position'`, `'error'`
- None for operations with side effects: `_init_gpio()` returns `None`
- Boolean for success/failure: `ipc.read_command()` returns dict or `None`

**Example from `services/command_handlers.py`:**
```python
def execute(self, angle: float, current_status: Dict[str, Any],
            speed: Optional[float] = None) -> Dict[str, Any]:
    """Returns updated status dict."""
    try:
        # Logic
    except (RuntimeError, ValueError, OSError) as e:
        current_status['status'] = 'error'
        current_status['error'] = str(e)
    return current_status
```

## Module Design

**Exports:**
- Core classes exported from main module: `from core.hardware.moteur import MoteurCoupole, DaemonEncoderReader`
- Re-exports in docstrings: `from core.hardware.daemon_encoder_reader import ...`
- Private modules with `_` prefix: `core/hardware/moteur_simule.py`, `services/simulation.py`

**Barrel Files:**
- No barrel `__init__.py` for most modules
- Explicit imports preferred: `from core.hardware.moteur import MoteurCoupole`
- Re-export pattern used only for compatibility (e.g., moteur.py re-exports daemon_encoder_reader)

**Mixins:**
- Used for composition in `TrackingSession`: `TrackingStateMixin`, `TrackingGotoMixin`, `TrackingCorrectionsMixin`
- Each mixin in separate file: `tracking_state_mixin.py`, `tracking_goto_mixin.py`, `tracking_corrections_mixin.py`
- Centralizes related functionality without deep inheritance

## Configuration Patterns

**Config Loading:**
- Centralized in `core/config/config_loader.py`
- JSON-based: `data/config.json`
- Fallback to defaults in code constants: `DEFAULTS` dict in `config.py`
- Deep merge for overrides: `_deep_update(base, override)`

**Conditional Imports:**
- Platform detection: Try import, set availability flag
```python
try:
    import lgpio
    LGPIO_AVAILABLE = True
except ImportError:
    LGPIO_AVAILABLE = False
    lgpio = None
```

## Singleton Pattern

**Daemon Reader Singleton:**
- Location: `core/hardware/daemon_encoder_reader.py`
- Lazy initialization: `get_daemon_reader()` returns global `_daemon_reader`
- Manual reset for testing: `reset_daemon_reader()`
- Example usage:
```python
reader = get_daemon_reader()
angle = reader.read_angle()
```

---

*Convention analysis: 2026-01-22*
