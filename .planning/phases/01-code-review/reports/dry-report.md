# DRY Violations Report

## Summary

- **Total duplicate patterns found:** 6
- **Critical patterns (exact duplicates):** 2
- **Medium patterns (repeated logic):** 2
- **Acceptable patterns (intentional):** 2
- **Effort estimation:** 4-6 hours total

## Patterns Found

### Critical (exact duplicates, should be factored)

| Pattern | Occurrences | Files | Effort | Recommendation |
|---------|-------------|-------|--------|----------------|
| IPC file paths hardcoded | 6 | core/hardware/daemon_encoder_reader.py (L16), core/hardware/encoder_reader.py (L8), core/hardware/hardware_detector.py (L120), services/ipc_manager.py (L25-27), scripts/diagnostics/*.py, web/driftapp_web/settings.py | 1-2h | Extract to single `core/config/ipc_paths.py` constant module |
| `% 360` angle normalization inline | 25+ | core/hardware/*.py, core/tracking/*.py, core/observatoire/*.py, services/command_handlers.py | 2h | Use existing `normalize_angle_360()` from `core/utils/angle_utils.py` consistently |

**Pattern 1 Details - IPC Paths:**
```python
# core/hardware/daemon_encoder_reader.py:16
DAEMON_JSON = Path("/dev/shm/ems22_position.json")

# core/hardware/encoder_reader.py:8
SHARED_FILE = Path("/dev/shm/ems22_position.json")

# core/hardware/hardware_detector.py:120
daemon_json = Path("/dev/shm/ems22_position.json")

# services/ipc_manager.py:25-27
COMMAND_FILE = Path("/dev/shm/motor_command.json")
STATUS_FILE = Path("/dev/shm/motor_status.json")
ENCODER_FILE = Path("/dev/shm/ems22_position.json")
```

**Recommendation:** Create `core/config/ipc_paths.py`:
```python
from pathlib import Path

IPC_BASE = Path("/dev/shm")
ENCODER_FILE = IPC_BASE / "ems22_position.json"
COMMAND_FILE = IPC_BASE / "motor_command.json"
STATUS_FILE = IPC_BASE / "motor_status.json"
```

---

**Pattern 2 Details - Inline `% 360`:**

The codebase has `normalize_angle_360()` in `core/utils/angle_utils.py` but many files use raw `% 360` inline:

```python
# core/hardware/moteur.py:330-331
position_cible = position_cible_deg % 360
position_actuelle = position_actuelle_deg % 360

# core/hardware/feedback_controller.py:532
angle_cible = (position_actuelle + delta_deg) % 360

# core/tracking/tracking_corrections_mixin.py:188-189
position_cible_logique = (self.position_relative + delta_deg) % 360
angle_cible_encodeur = (position_cible_logique - self.encoder_offset) % 360

# services/command_handlers.py:286
current_status['position'] = (current + delta) % 360
```

**25+ occurrences** across 12 files. The utility function exists but isn't consistently used.

---

### Medium (repeated logic 3+ times)

| Pattern | Occurrences | Files | Effort | Recommendation |
|---------|-------------|-------|--------|----------------|
| JSON file reading with error handling | 9 | core/config/*.py, core/hardware/*.py, core/observatoire/catalogue.py, services/ipc_manager.py | 1-2h | Create `safe_json_load()` utility |
| Configuration dict access patterns | 5+ | Multiple tracking/hardware modules | 1h | Use config_loader dataclasses consistently |

**Pattern 3 Details - JSON Loading:**

Multiple variations of try/except JSON loading:

```python
# core/config/config.py:54
return json.load(f)

# core/hardware/daemon_encoder_reader.py:69-70
return json.loads(text)
except (FileNotFoundError, json.JSONDecodeError):

# services/ipc_manager.py:94
command = json.loads(text)
```

**Recommendation:** Create `core/utils/file_utils.py`:
```python
def safe_json_load(path: Path, default: Any = None) -> Any:
    """Load JSON with error handling and default fallback."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default
```

---

**Pattern 4 Details - Config Access:**

Some modules access config dict directly instead of using typed dataclasses:

```python
# Direct dict access (old pattern)
c.get("gear_ratio", 2230.0)

# Typed dataclass (new pattern via config_loader.py)
config.moteur.gear_ratio
```

The `config_loader.py` provides typed `DriftAppConfig` dataclass but not all modules use it.

---

### Acceptable (intentional duplication)

| Pattern | Reason |
|---------|--------|
| `logging.getLogger(__name__)` | Standard Python convention (16 occurrences). Each module should have its own logger. |
| `try/except Exception as e` with `logger.error()` | Standard error handling pattern. Exception types differ by context. |

---

## Refactoring Recommendations

Prioritized by effort/impact ratio:

### Priority 1: IPC Paths Centralization (Trivial - 1h)

**Impact:** High - eliminates 6+ hardcoded path definitions
**Risk:** Low - purely mechanical change
**Files to modify:**
- Create: `core/config/ipc_paths.py`
- Update: `core/hardware/daemon_encoder_reader.py`
- Update: `core/hardware/encoder_reader.py`
- Update: `core/hardware/hardware_detector.py`
- Update: `services/ipc_manager.py`

### Priority 2: Consistent Angle Normalization (Easy - 2h)

**Impact:** High - improves code clarity, reduces bug risk
**Risk:** Low - existing function is well-tested
**Files to update:** 12 files with `% 360` inline usage
**Action:** Replace inline `x % 360` with `normalize_angle_360(x)` import

### Priority 3: Safe JSON Loading Utility (Easy - 1h)

**Impact:** Medium - reduces boilerplate in 9 locations
**Risk:** Low - simple wrapper function
**Action:** Create utility and update callers

### Priority 4: Config Dataclass Migration (Medium - 2h)

**Impact:** Medium - type safety improvement
**Risk:** Medium - requires testing existing config consumers
**Action:** Audit config dict usage, migrate to typed access

---

## Not Recommended for Refactoring

| Pattern | Reason |
|---------|--------|
| Test duplication (tests/) | Test isolation is valuable; some duplication acceptable |
| Error message strings | Context-specific, not worth abstracting |
| Import statements | Standard Python practice |

---

## Metrics

| Metric | Value |
|--------|-------|
| Files analyzed | core/, services/ (~40 Python files) |
| Critical violations | 2 patterns |
| Total refactoring effort | 4-6 hours |
| Highest impact | IPC paths (6 violations) |
| Most widespread | `% 360` inline (25+ occurrences) |

---

*Generated: 2026-01-25*
*Scope: core/, services/ directories*
