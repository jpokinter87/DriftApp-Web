# Code Review Report — 01-01: Core Modules

**Date:** 2026-03-13
**Scope:** config/, hardware/, utils/, data/config.json
**Files reviewed:** 10/10

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 2 |
| HIGH | 8 |
| MEDIUM | 12 |
| LOW | 9 |
| **Total** | **31** |

---

## CRITICAL

### C-01: Dual config system — risk of divergence
- **Files:** `core/config/config_loader.py`, `core/config/config.py`
- **Lines:** Both files load `data/config.json` independently
- **Type:** architecture, bug-risk
- **Description:** Two completely independent config systems coexist:
  - `config_loader.py` (v2.3): Full dataclass-based system with `load_config()` — used by motor_service, tracker, etc.
  - `config.py`: Module-level globals (`SITE_LATITUDE`, `MOTOR_GEAR_RATIO`, etc.) loaded at import time — used by older modules (catalogue, TUI).

  They parse different keys from the same JSON (e.g., `config.py` reads `"microstepping"` while `config_loader.py` reads `"microsteps"`). If one module uses `config.py` and another uses `config_loader.py`, they could disagree on values.

  `config.py` also has its own `DEFAULTS` dict (lat=49.01, lon=2.10) that differs from `config_loader.py` defaults (lat=0.0, lon=0.0) and from actual config.json (lat=44.15, lon=5.23). If config.json is missing, the two systems give completely different values.

  Additionally, `config.py:save_config()` would overwrite `config.json` with only its subset of keys, destroying the adaptive_tracking, parking, encoder, and logging sections.
- **Recommendation:** Deprecate `config.py` and migrate all consumers to `config_loader.py`. If `config.py` must remain temporarily, make it a thin wrapper around `load_config()`.

### C-02: `_parse_modes()` still parses dead "fast_track" mode
- **File:** `core/config/config_loader.py:339`
- **Type:** bug, dead-code
- **Description:** `_parse_modes()` iterates over `["normal", "critical", "continuous", "fast_track"]` but FAST_TRACK was removed in v4.4 (per CLAUDE.md and config.json). This creates a phantom `fast_track` entry in `AdaptiveConfig.modes` with default values (interval=60s, threshold=0.5, delay=0.002) that don't match any real mode. If any code ever accesses `config.adaptive.modes["fast_track"]`, it will get silently incorrect values instead of failing.
- **Recommendation:** Remove `"fast_track"` from the mode list. Parse mode names dynamically from `modes_cfg.keys()` instead of hardcoding.

---

## HIGH

### H-01: `read_stable()` averages angles near 0°/360° incorrectly
- **File:** `core/hardware/moteur.py:153`
- **Type:** bug
- **Description:** `read_stable()` computes `sum(positions) / len(positions)` but this fails for angles near 0°/360°. Example: readings [359.5, 0.2, 0.5] → average = 120.07° instead of expected ~0.07°. This directly affects feedback controller precision at the 0°/360° boundary.
- **Recommendation:** Use circular mean (atan2 of sin/cos components) or normalize relative to first reading before averaging.

### H-02: `rotation_avec_feedback` double-reads position in loop
- **File:** `core/hardware/feedback_controller.py:368-393`
- **Type:** performance, bug-risk
- **Description:** In the main `while` loop of `rotation_avec_feedback()`, `_lire_position_stable()` is called TWICE per iteration:
  1. Line 369: to check progression
  2. Inside `_executer_iteration()` line 243: to compute error

  Each `_lire_position_stable()` costs ~80ms (50ms stabilization + 3×10ms). So each iteration spends ~160ms just reading, when ~80ms would suffice. This doubles the pause time between corrections, contributing to the saccade issue for small movements.
- **Recommendation:** Read position once at the top of the loop and pass it to `_executer_iteration()`.

### H-03: No JSON atomicity for daemon file reads
- **File:** `core/hardware/moteur.py:62` (DaemonEncoderReader.read_raw)
- **Type:** bug-risk, race-condition
- **Description:** `read_raw()` reads `/dev/shm/ems22_position.json` with `self.daemon_path.read_text()`. The daemon writes this file concurrently. If a read happens mid-write, `json.loads()` will get a truncated/corrupt JSON string. The `JSONDecodeError` catch handles this, but `read_angle()` retries silently which can cause timing jitter.
- **Recommendation:** Use a try-read-parse pattern with explicit retry count limit, or have the daemon write to a temp file then rename (atomic on /dev/shm). At minimum, add a `max_retries` parameter to prevent infinite retry loops.

### H-04: `read_angle()` can loop forever if daemon returns non-OK, non-SPI status
- **File:** `core/hardware/moteur.py:80-107`
- **Type:** bug
- **Description:** The `while True` loop in `read_angle()` only returns for `status.startswith("OK")` or `status.startswith("SPI")`. Any other status (e.g., "ERROR", "INIT", "CALIBRATING") causes an infinite loop that never times out, because the `elapsed_ms > timeout_ms` check only triggers when `data is None`.
- **Recommendation:** Add timeout check after the status check, or return angle with warning for any non-None data.

### H-05: Global mutable state in `moteur_simule.py`
- **File:** `core/hardware/moteur_simule.py:19`
- **Type:** bug-risk
- **Description:** `_simulated_position` is a module-level global shared across all instances. In a multi-process architecture (motor_service + Django), each process gets its own copy of this global. The simulated position won't stay synchronized between processes, making simulation unreliable for IPC testing.
- **Recommendation:** For true cross-process simulation, store position in `/dev/shm/` (mimicking the real daemon file). For single-process testing, the current approach is acceptable but should be documented.

### H-06: `config.py:save_config()` would destroy config.json
- **File:** `core/config/config.py:112-128`
- **Type:** security, data-loss
- **Description:** `save_config()` writes only `site`, `motor`, `gpio`, and `dome_offsets` to `config.json`, but the actual file contains many more sections (parking, adaptive_tracking, encodeur, logging, suivi, geometrie). Calling `save_config()` would silently destroy all these sections.
- **Recommendation:** Either remove `save_config()` or implement a merge-save that preserves unmanaged sections.

### H-07: Bare `except:` clauses in hardware code
- **Files:** `core/hardware/moteur.py:347-348,650-651`, `core/hardware/hardware_detector.py:177,198`
- **Type:** style, bug-risk
- **Description:** Multiple bare `except:` clauses swallow all exceptions including `KeyboardInterrupt` and `SystemExit`. In GPIO cleanup code (`nettoyer()`), this could prevent clean shutdown. In hardware_detector, it masks unexpected errors during subprocess calls.
- **Recommendation:** Replace with `except Exception:` at minimum, or catch specific exceptions.

### H-08: `MoteurSimule` API differs from `MoteurCoupole`
- **File:** `core/hardware/moteur_simule.py:165-202`
- **Type:** bug-risk, api-mismatch
- **Description:** `MoteurSimule.rotation_avec_feedback()` signature lacks `allow_large_movement` and `timeout_seconds` parameters that `FeedbackController.rotation_avec_feedback()` supports. If `motor_service.py` passes these kwargs in simulation mode, they would be silently ignored (no `**kwargs`), potentially causing `TypeError` if the signature doesn't accept them.
- **Recommendation:** Align signatures exactly. Either accept `**kwargs` to absorb extra params, or mirror the full parameter list.

---

## MEDIUM

### M-01: `load_site_config()` compatibility layer returns 9 values, not 12
- **File:** `core/config/config_loader.py:420-516`
- **Type:** dead-code, misleading
- **Description:** The docstring says "Tuple de 12 valeurs" but actually returns 9 values. The function exists "for compatibility" but it's unclear if anything still calls it. If not, it's 100 lines of dead code.
- **Recommendation:** Search for usages. If none, remove entirely. If used, fix the docstring.

### M-02: `to_dict()` raises `NotImplementedError`
- **File:** `core/config/config_loader.py:219-223`
- **Type:** dead-code
- **Description:** `DriftAppConfig.to_dict()` is declared but not implemented. This is a trap — any caller gets a runtime error.
- **Recommendation:** Either implement it (using `dataclasses.asdict()`) or remove it entirely.

### M-03: Config validation is silent — uses defaults for missing keys
- **File:** `core/config/config_loader.py:271-383`
- **Type:** bug-risk
- **Description:** All `_parse_*` methods use `.get(key, default)` which silently substitutes defaults for missing or misspelled keys. For example, if someone typos `"latitude"` as `"latitdue"` in config.json, the site would silently default to 0.0° latitude. No warning is logged.
- **Recommendation:** Log a warning when using a default value for critical keys (at minimum: latitude, longitude, gpio_pins, gear_ratio).

### M-04: `logging_config.py` creates new log file on every call
- **File:** `core/config/logging_config.py:47-48`
- **Type:** design
- **Description:** `setup_logging()` creates a timestamped file `driftapp_{timestamp}.log` on every call. If called multiple times (e.g., during testing or service restart), this creates many small log files. The `RotatingFileHandler` rotation only applies within a single filename.
- **Recommendation:** Consider using a fixed filename with date-based rotation (`TimedRotatingFileHandler`), or at least document that `setup_logging()` should be called exactly once per process lifetime.

### M-05: Redundant logger level setting
- **File:** `core/config/logging_config.py:93-111`
- **Type:** dead-code
- **Description:** Setting level on individual loggers (`motor_logger`, `tracker_logger`, etc.) is unnecessary when the root logger already has the same level set. Child loggers inherit from root. These lines have no effect.
- **Recommendation:** Remove individual logger level settings unless specific loggers need different levels.

### M-06: `get_log_file_path()` return type annotation is wrong
- **File:** `core/config/logging_config.py:130`
- **Type:** style
- **Description:** `Optional[Path|None]` is redundant — `Optional[Path]` already means `Path | None`. The `|` syntax within `Optional` is doubly redundant.
- **Recommendation:** Change to `Optional[Path]` or `Path | None`.

### M-07: `encoder_reader.py` duplicates `DaemonEncoderReader` functionality
- **File:** `core/hardware/encoder_reader.py`
- **Type:** dead-code, duplication
- **Description:** This 38-line module provides `read_encoder_daemon()` which does the same thing as `DaemonEncoderReader.read_raw()` + freshness check. Since `DaemonEncoderReader` in `moteur.py` is the canonical reader (used by motor_service and feedback_controller), this file appears unused or redundant.
- **Recommendation:** Search for usages. If unused, remove. If used, refactor to delegate to `DaemonEncoderReader`.

### M-08: `encoder_reader.py` checks `"ts"` key but daemon may write `"timestamp"`
- **File:** `core/hardware/encoder_reader.py:27`
- **Type:** bug-risk
- **Description:** Uses `data.get("ts", 0)` but the daemon JSON format should be verified. If the daemon writes `"timestamp"` instead of `"ts"`, the freshness check always fails (age = current_time - 0 = huge).
- **Recommendation:** Verify the actual daemon output format and use consistent key names.

### M-09: `hardware_detector.py` `is_raspberry_pi()` false positive on non-Pi ARM
- **File:** `core/hardware/hardware_detector.py:47-51`
- **Type:** bug-risk
- **Description:** Method 3 treats ANY ARM Linux machine (aarch64 + Linux) as Raspberry Pi. This would false-positive on Apple Silicon running Linux, AWS Graviton instances, etc.
- **Recommendation:** Make method 3 a fallback only when methods 1-2 fail AND additional indicators exist (e.g., `/sys/firmware/devicetree/` present).

### M-10: `check_gpio_available()` has side effects
- **File:** `core/hardware/hardware_detector.py:64-72`
- **Type:** bug-risk
- **Description:** `check_gpio_available()` calls `GPIO.setmode(GPIO.BCM)` which globally configures GPIO mode. If called before the motor is initialized, this is fine. But if called after (e.g., for status checking), it could conflict with an already-configured mode.
- **Recommendation:** Either avoid setting mode in the check, or document that this function should only be called before motor init.

### M-11: `moteur.py` re-imports `lgpio` on every `faire_un_pas()` call
- **File:** `core/hardware/moteur.py:472-473`
- **Type:** performance
- **Description:** `import lgpio` is inside the hot loop of `faire_un_pas()`. While Python caches imports after the first call, the import lookup still has overhead on every step pulse. For a 90° GOTO (~480k steps), this is ~480k unnecessary dictionary lookups.
- **Recommendation:** Store `lgpio` reference as `self._lgpio` during `_init_gpio()` and use it directly.

### M-12: `_init_parametres_rampe()` is a no-op
- **File:** `core/hardware/moteur.py:264-277`
- **Type:** dead-code
- **Description:** Method body is `pass` with commented-out code. Same for `_calculer_delai_rampe()` which always returns `vitesse_nominale`. Both could be removed.
- **Recommendation:** Remove both methods and the call in `__init__`. If ramp might be re-enabled in the future, keep a comment explaining why it was removed (already present in `_calculer_delai_rampe` docstring, which is good).

---

## LOW

### L-01: Emoji in log messages
- **File:** `core/config/logging_config.py:120-124`
- **Type:** style
- **Description:** Log messages contain emoji (🚀, 📝, 📊, 🔄, 🛑). While visually nice in terminal, emoji can cause issues with log parsing tools, grep, and older terminals on the Raspberry Pi.
- **Recommendation:** Use plain text markers (`[INFO]`, `[START]`, `[STOP]`) or keep emoji but be aware of Pi terminal compatibility.

### L-02: Inconsistent `_comment` keys in config.json
- **File:** `data/config.json` (throughout)
- **Type:** style
- **Description:** Comment keys are inconsistent: `"_comment"`, `"_steps_comment"`, `"_enabled_comment"`, `"_speed"`, `"_usage"`, `"_changes"`. No standard naming convention.
- **Recommendation:** Use a consistent pattern like `"_comment_<field>"` or just `"_comment"` per section.

### L-03: `config.py` hardcodes different default coordinates
- **File:** `core/config/config.py:25-26`
- **Type:** misleading
- **Description:** Default coordinates (49.01, 2.10) point to Île-de-France, while the actual observatory is in Drôme (44.15, 5.23). If config.json is missing, the application would calculate ephemeris for the wrong location.
- **Recommendation:** Either use the real coordinates as defaults or remove defaults entirely (fail fast).

### L-04: Unused `Tuple` import in `moteur.py`
- **File:** `core/hardware/moteur.py:23`
- **Type:** dead-code
- **Description:** `Dict, Any, Optional` are imported from `typing` but `Dict` and `Any` are only used in type hints of `rotation_avec_feedback()` which delegates to FeedbackController. The return type could use the same imports.
- **Recommendation:** Minor — verify which imports are actually needed. Consider using `dict` and `Any` from builtins (Python 3.9+).

### L-05: `moteur_simule.py` has unused `ramp_*` attributes
- **File:** `core/hardware/moteur_simule.py:72-74`
- **Type:** dead-code
- **Description:** `ramp_start_delay`, `ramp_steps`, `ramp_enabled` are set but never used. The ramp was disabled in the real motor too.
- **Recommendation:** Remove these attributes.

### L-06: `shortest_angular_distance()` uses while loop instead of modulo
- **File:** `core/utils/angle_utils.py:86-89`
- **Type:** performance (minor)
- **Description:** Uses `while delta > 180: delta -= 360` which works but is O(n) for very large deltas. The modulo approach in `normalize_angle_180()` is O(1).
- **Recommendation:** Use modulo: `delta = (delta + 180) % 360 - 180`. This also handles edge cases more consistently.

### L-07: `angles_are_close()` uses `<` instead of `<=`
- **File:** `core/utils/angle_utils.py:115`
- **Type:** style
- **Description:** `delta < tolerance` means exactly-on-tolerance returns False. While 0.5° is unlikely to be hit exactly with float arithmetic, `<=` is more intuitive for a "close enough" check.
- **Recommendation:** Use `<=` for consistency with mathematical definition of tolerance.

### L-08: `hardware_detector.py` `check_daemon_process()` uses `ps aux`
- **File:** `core/hardware/hardware_detector.py:190-198`
- **Type:** performance, fragility
- **Description:** Spawns a subprocess to run `ps aux` and greps the output. This is fragile (process name could change) and slow compared to checking `/proc` directly or using `pidof`.
- **Recommendation:** Use `subprocess.run(["pgrep", "-f", "ems22d_calibrated"], ...)` which is more robust and lighter.

### L-09: `DriftAppConfig.__str__` doesn't show all fields
- **File:** `core/config/config_loader.py:203-212`
- **Type:** style
- **Description:** `__str__` omits tracking config details, critical zones count, and simulation mode description. Not a bug but reduces diagnostic usefulness.
- **Recommendation:** Include tracking seuil and adaptive mode count in the string representation.

---

## Cross-Cutting Observations

### Error Handling Pattern
Most modules follow a reasonable pattern (catch specific exceptions, log, re-raise or return None). The main gaps are:
- Bare `except:` in GPIO cleanup (H-07)
- Silent defaults in config parsing (M-03)
- Infinite loop risk in daemon reader (H-04)

### Logging
Consistent use of Python `logging` module throughout. Logger names are mostly consistent but not namespaced (`"MoteurCoupole"` vs `"core.tracking.tracker"`).

### Config Architecture
The dual-config system (C-01) is the most impactful finding. Resolving this would eliminate several downstream risks and simplify the codebase significantly.

### Simulation Fidelity
`MoteurSimule` provides a reasonable simulation but has API mismatches (H-08) and doesn't simulate cross-process IPC (H-05), limiting confidence in simulation testing.

---

*Report generated: 2026-03-13*
*Reviewer: Claude (automated code review)*
