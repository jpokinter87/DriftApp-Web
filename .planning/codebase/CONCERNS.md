# Codebase Concerns

**Analysis Date:** 2026-01-22

## Tech Debt

### 1. Encoder Calibration Not Validated at Startup

**Files:** `core/tracking/tracker.py`, `services/command_handlers.py`

**Issue:** System can start tracking with an uncalibrated encoder, leading to:
- Encoders returning fixed/stale values (e.g., 0.1°)
- Feedback loop unable to detect actual dome position
- Infinite correction cycles
- Unresponsive STOP button

**Impact:** CRITICAL - User forced to kill process manually. Risk of mechanical damage from continuous motor rotation.

**Fix approach:**
- Add calibration check in `TrackingSession.start()` before allowing tracking
- Reject track start if `encoder_data['calibrated'] == false`
- Display user-friendly error message with calibration instructions (pass through 45° switch)

**Related document:** `/docs/history/BUG_CRITIQUE_ENCODEUR_NON_CALIBRE.md` (Déc 7, 2025)

---

### 2. Feedback Loop Without Escape Condition on Encoder Failure

**Files:** `core/hardware/feedback_controller.py` (lines 150-250)

**Issue:**
- Loop runs max 10 iterations with 0.5s sleep each (5s+ per correction)
- If encoder is frozen/stale, error never drops below tolerance
- Loop logs warning but continues silently
- No limit on consecutive failed corrections in tracking session

**Impact:** HIGH - Leads to repeated slow corrections, system hung in degraded state.

**Fix approach:**
- Count consecutive failed corrections (already in code as `MAX_STAGNANT_CORRECTIONS = 3`)
- Stop tracking automatically after 3 consecutive correction failures
- Raise exception with details about encoder health

---

### 3. Blocking Sleep Calls in Correction Loop

**Files:** `core/hardware/feedback_controller.py` (lines ~180-220), `services/command_handlers.py`

**Issue:**
- `time.sleep(0.5)` in iteration loop blocks request handling
- STOP button becomes unresponsive during long feedback corrections
- Thread cannot check for stop requests during sleep

**Impact:** HIGH - User cannot interrupt tracking smoothly.

**Fix approach:**
- Use `self.stop_requested` flag checked after each sleep
- Break loop immediately when flag set
- Implement non-blocking timeout pattern (check elapsed time vs sleep duration)

---

### 4. Unspecific Exception Handling

**Files:** Multiple across codebase
- `core/config/config.py:55` - bare `except Exception`
- `core/hardware/hardware_detector.py:37-102` - multiple `except Exception`
- `core/observatoire/catalogue.py:74,91,181` - `except Exception`
- `core/tracking/abaque_manager.py:127,251,351` - generic catches

**Issue:**
- Masks actual errors (file not found vs permission denied vs corrupt data)
- Makes debugging difficult (swallows stack traces)
- Prevents proper error propagation to caller

**Impact:** MEDIUM - Difficult to diagnose real failures in production.

**Fix approach:**
- Replace with specific exceptions: `FileNotFoundError`, `JSONDecodeError`, `ValueError`, etc.
- Log full traceback before returning None/default value
- Only catch exceptions you can actually handle

---

## Known Bugs

### 1. Matplotlib Animation Initialization Order

**Files:** `boussole.py` (FIXED in v4.6)

**Symptoms:**
- Compass needle frozen despite correct JSON data from daemon
- Daemon working correctly, direct sensor read works

**Cause:** `FuncAnimation` created before Tkinter canvas integration (requires canvas parent)

**Workaround:** N/A - Fixed. Correct order is: Figure → Configure → Canvas → Animation → Mainloop

**Status:** RESOLVED (Dec 6, 2025)

**Related document:** `/docs/history/ANALYSE_BUG_BOUSSOLE_DAEMON.md`

---

### 2. Infinite Corrections with Uncalibrated Encoder

**Files:** `core/tracking/tracker.py`, `core/hardware/feedback_controller.py`

**Symptoms:**
- Tracking starts but dome never stops rotating
- Each correction attempt fails (encodeur stuck at 0.1°)
- 10 iterations per failed correction takes 30-76 seconds
- Immediately retries without break

**Cause:** Root cause documented in encoder non-calibrated bug - feedback loop has no detection for frozen encoder state.

**Status:** CRITICAL - Identified but requires calibration check before start (see Tech Debt #1)

**Related document:** `/docs/history/BUG_CRITIQUE_ENCODEUR_NON_CALIBRE.md`

---

## Security Considerations

### 1. Django DEBUG Mode and Secret Key

**Files:** `web/driftapp_web/settings.py` (lines 20, 24)

**Risk:**
```python
DEBUG = os.environ.get('DJANGO_DEBUG', 'true').lower() in ('true', '1', 'yes')
SECRET_KEY = 'django-insecure-driftapp-dev-key-change-in-production'
```

- Defaults to DEBUG=true (reveals sensitive info in error pages)
- Hardcoded dev secret key (predictable)
- `ALLOWED_HOSTS = ['*']` (accepts any hostname)

**Current mitigation:** Settings file warns about production requirements.

**Recommendations:**
- Generate unique SECRET_KEY at deployment
- Default DEBUG to False or require explicit environment variable
- Restrict ALLOWED_HOSTS to known observatory domain/IP
- Use Django's `django.core.management.utils.get_random_secret_key()` on first run

**Priority:** HIGH - Applies to production deployment only.

---

### 2. Subprocess Calls Without Input Validation

**Files:**
- `core/hardware/hardware_detector.py` - uses `subprocess.run()` for `lsmod`
- `web/health/views.py` - subprocess calls for systemctl, journalctl
- `web/health/update_checker.py` - git subprocess calls

**Risk:** While subprocess calls use list arguments (safe from injection), they timeout at 2-5s. Long-running git operations could fail silently.

**Current mitigation:** Timeouts and explicit error handling present.

**Recommendations:**
- Add logging of subprocess failures with stderr output
- Increase timeout for slow operations (git fetch over slow network)
- Consider caching results to avoid repeated syscalls

**Priority:** LOW - No direct command injection possible with current code.

---

### 3. IPC Files World-Readable/Writable

**Files:** `services/ipc_manager.py` (line 64)

**Risk:**
```python
os.chmod(COMMAND_FILE, 0o666)  # World writable!
```

**Issue:** Motor commands in `/dev/shm/motor_command.json` can be modified by any user.

**Impact:** Unauthorized users could rotate dome. CRITICAL if observatory accessible to public.

**Current mitigation:** `/dev/shm` is typically root-only on hardened systems, but files created world-writable.

**Recommendations:**
- Use 0o660 (owner+group writable only)
- Create group 'driftapp' and assign Django + Motor Service to it
- Document required group setup in deployment guide

**Priority:** MEDIUM - Depends on network security posture.

---

## Performance Bottlenecks

### 1. Synchronous IPC Reads with No Caching

**Files:** `web/common/ipc_client.py`, `core/hardware/daemon_encoder_reader.py`

**Problem:**
- Every web request does blocking JSON read from `/dev/shm/motor_status.json`
- No connection pooling or caching
- Stale data checks add overhead (timestamp comparison)

**Current solution:** Timeout-based retries (200ms default), but inefficient for dashboard refreshes.

**Improvement path:**
- Cache status for 100ms with timestamp-based invalidation
- Implement reader pattern: single daemon reader instance
- Consider shared memory (mmap) instead of JSON re-parsing

**Priority:** LOW-MEDIUM - Not critical unless dashboard has 100+ concurrent users.

---

### 2. Excel File Parsing on Every Start

**Files:** `core/tracking/abaque_manager.py` (lines 60-120)

**Problem:**
- `Loi_coupole.xlsx` (275-point abaque) parsed with openpyxl at TrackingSession init
- No caching of interpolator
- Happens once per tracking session but slow (~500-1000ms)

**Improvement path:**
- Cache interpolator object after first load
- Serialize interpolator to JSON for faster startup
- Load abaque in background thread during Django startup

**Priority:** LOW - One-time cost per session, acceptable for observatory operations.

---

### 3. Repeated Motor Config Lookups

**Files:** `core/config/config_loader.py` (lines ~50-200)

**Problem:** 537-line file with complex nested dictionary access patterns. Accessed on every motor command.

**Improvement path:**
- Cache parsed ConfigDataclass instance as singleton
- Use type-safe dataclass access instead of dict
- Profile actual hot paths (likely motor_delay calculation)

**Priority:** LOW - Config changes rare during operation.

---

## Fragile Areas

### 1. Adaptive Tracking Mode Selection

**Files:** `core/tracking/adaptive_tracking.py` (500+ lines), `core/tracking/tracking_corrections_mixin.py` (lines 27-35)

**Why fragile:**
- 3 hardcoded mode thresholds: NORMAL (alt<68°), CRITICAL (68-75°), CONTINUOUS (≥75°)
- Each mode has distinct correction interval and motor delay
- Logic split across multiple mixins + adaptive manager
- Post-meridian handling (alt>75°) with 30° delta bypass has implicit assumptions

**Safe modification:**
1. **Don't change thresholds** without re-verifying tracking quality across entire sky
2. **Test all altitude ranges** (low elevation, high elevation, meridian crossing)
3. **Log mode transitions** to diagnose issues
4. **Parameter coupling**: CRITICAL mode delay=1.0ms tied to correction interval=15s

**Test coverage:** `tests/test_adaptive_tracking.py` (493 lines) covers zones but not all edge cases (e.g., near-zenith fast azimuth slews).

**Priority:** MEDIUM - Works well for typical usage but edge cases not fully tested.

---

### 2. Feedback Controller Iteration Limits

**Files:** `core/hardware/feedback_controller.py` (lines 40-42)

**Why fragile:**
```python
MAX_STAGNANT_CORRECTIONS = 3
MIN_MOVEMENT_THRESHOLD = 0.1  # degrees
```

- Hardcoded limits - no configuration option
- `0.1°` movement threshold chosen empirically, not from encoder spec
- 3 failures = automatic stop may be too strict on noisy encoders

**Safe modification:**
1. **Make configurable** in `data/config.json` under new `feedback` section
2. **Document encoder specification** (EMS22A 10-bit = 0.35° resolution)
3. **Test with different encoder conditions**: normal, noisy, slow-responding

**Test coverage:** `tests/test_feedback_controller.py` (635 lines) - good coverage of stagnation detection

**Priority:** MEDIUM - Currently works but should be config-driven.

---

### 3. Multi-File Synchronization for Session State

**Files:**
- `services/motor_service.py` - maintains state in `/dev/shm/motor_status.json`
- `web/session/session_storage.py` - saves session state to disk
- `ems22d_calibrated.py` - daemon writes encoder state

**Why fragile:**
- 3 separate processes writing different state files
- No coordination: what if daemon updates at same moment Django saves session?
- Race conditions on `/dev/shm/motor_status.json` mitigated by fcntl locks, but session files not locked

**Safe modification:**
1. **Document synchronization expectations**
2. **Add atomic rename operations** for session file writes (write temp, rename atomic)
3. **Consider single source of truth** (Motor Service owns state, others read-only)

**Test coverage:** `tests/test_integration.py` (697 lines) - integration tests exist but race conditions hard to trigger

**Priority:** MEDIUM-HIGH - Could cause data loss or inconsistency under load.

---

## Scaling Limits

### 1. 50 Hz Encoder Sampling Rate vs Command Processing

**Files:** `ems22d_calibrated.py`, `services/motor_service.py` (20 Hz main loop)

**Current capacity:**
- Daemon reads SPI at 50 Hz (20ms intervals)
- Motor Service processes at 20 Hz (50ms)
- Web requests handled by Django (async possible but not implemented)

**Limit:** If tracking altitude changes faster than 20 Hz correction loop can follow, system lags. Problem near zenith with rapid azimuth slews.

**Scaling path:**
- Increase motor service frequency to 30-40 Hz (requires GPIO optimization)
- Implement predictive tracking (extrapolate next position)
- Use exponential moving average for encoder readings

**Priority:** LOW - Current 20 Hz adequate for astronomical tracking (object motion ~0.1°/min).

---

### 2. Django Session Storage on SQLite

**Files:** `web/driftapp_web/settings.py` (lines 77-82)

**Current capacity:**
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
```

**Limit:** SQLite has poor concurrent write performance. If multiple users access dashboard simultaneously, locks could block requests.

**Scaling path:**
- For >5 concurrent users: migrate to PostgreSQL
- Session storage already in `/dev/shm` via IPC, not critical
- Only used for Django session tokens (not real-time data)

**Priority:** LOW - Observatory typically has 1-2 concurrent operators.

---

### 3. JSON File I/O for Real-Time Motor Status

**Files:** `services/ipc_manager.py`, `core/hardware/daemon_encoder_reader.py`

**Current capacity:**
- Each motor command = 2 JSON writes (command + clear)
- Each status poll = 1 JSON read
- Daemon writes position at 50 Hz = 50 writes/sec max

**Limit:** `/dev/shm` is in-memory FS with typical size 256MB-512MB. Not a practical limit for years of operation. JSON parsing adds ~1-5ms overhead per read.

**Scaling path:**
- If status updates >100 Hz needed: switch to memory-mapped structures
- Current approach scales fine to 10 kHz

**Priority:** LOW - Not a practical concern.

---

## Dependencies at Risk

### 1. Astropy (Astronomical Calculations)

**Files:** `core/observatoire/calculations.py`, `core/observatoire/ephemerides.py`

**Risk:**
- Heavy dependency (pulls numpy, scipy, etc.)
- Only used for GOTO initial sync + ephemeris calculations
- Tests can be skipped with `-k "not astropy"`

**Current mitigation:** Graceful degradation - if astropy unavailable, use fallback catalog + abaque method.

**Migration plan:**
1. Consider lighter alternative: `skyfield` (smaller, focused)
2. Or wrap astropy calls in try/except for fallback
3. Current approach acceptable for v4.6

**Priority:** LOW - Dependency stable and well-maintained.

---

### 2. openpyxl (Excel Parsing)

**Files:** `core/tracking/abaque_manager.py`

**Risk:**
- Only used to load `Loi_coupole.xlsx` at startup
- Single point of failure: corrupted Excel file breaks abaque system

**Current mitigation:** Exception handling returns `False` if load fails.

**Migration plan:**
- Export `Loi_coupole.xlsx` → CSV for robustness
- Fallback to CSV if Excel unavailable
- Validate abaque data on load (check monotonicity, ranges)

**Priority:** MEDIUM - Should add CSV export as backup.

---

## Missing Critical Features

### 1. Encoder Offline Detection

**Problem:** No mechanism to detect when daemon stops updating encoder position.

**Impact:** Tracking continues with stale position data, dome diverges from target.

**Files affected:**
- `core/hardware/daemon_encoder_reader.py` - only checks max_age_ms for freshness
- `core/tracking/tracker.py` - no daemon health check

**Blocks:** Cannot reliably track in absence of encoder feedback.

**Implementation:**
- Monitor `/dev/shm/ems22_position.json` timestamp
- If no update for 2 seconds, raise `DaemonOfflineError`
- Stop tracking and display alert

---

### 2. Watchdog Recovery for Motor Service Crash

**Problem:** If motor service dies, Django keeps queueing commands silently. Commands lost.

**Files:** `services/motor_service.py` (has systemd watchdog), `web/common/ipc_client.py`

**Current mitigation:** systemd watchdog (30s) restarts service, but commands in transit are lost.

**Implementation:**
- Add command persistence (write failed commands to disk before restart)
- Retry logic in Django IPC client
- Expose Motor Service health status via `/api/health/motor-service`

---

### 3. Configuration Hot-Reload Without Restart

**Problem:** All config changes require restarting Motor Service. Breaks active tracking.

**Files:** `core/config/config_loader.py`, `services/motor_service.py`

**Implementation:**
- Monitor `data/config.json` for changes (file watcher)
- Reload config on change if no active tracking
- Queue reload request for after tracking stops

**Priority:** LOW - Config rarely changes during operation.

---

## Test Coverage Gaps

### 1. Web API Security & Validation

**What's not tested:**
- SQL injection protection (Django handles via ORM, but custom queries?)
- CSRF token validation (middleware configured but not tested)
- Rate limiting (no limits implemented)
- Input bounds (angle validation exists but not comprehensive)

**Files:** `web/hardware/views.py`, `web/tracking/views.py`

**Risk:** Open APIs with no rate limiting - could be DoS target

**Implementation:**
- Add test cases for invalid input: negative angles, NaN, infinity
- Test CSRF protection disabled endpoints
- Consider adding rate limiting (Django Ratelimit package)

**Priority:** MEDIUM - Depends on network exposure.

---

### 2. Daemon Encoder Reader Error Conditions

**What's not tested:**
- File locked by another process (fcntl lock fails)
- Truncated/partial JSON in file
- Daemon crash + file stale data
- Multiple rapid encoder reads (contention)

**Files:** `core/hardware/daemon_encoder_reader.py`, `tests/test_daemon_encoder_reader.py` (312 lines)

**Test coverage exists for:**
- Stale data detection ✓
- Timeout handling ✓
- Averaging ✓

**Missing:**
- Concurrent read contention
- Partial read recovery
- Daemon offline scenarios

**Priority:** MEDIUM - Edge cases under stress.

---

### 3. Motor Service Command Ordering

**What's not tested:**
- Rapid fire GOTO → JOG → GOTO sequence (queue handling)
- STOP received mid-rotation (halt behavior)
- IPC file corruption + recovery
- Command timeout (command file locked >5 seconds)

**Files:** `services/command_handlers.py`, `services/motor_service.py`

**Test coverage exists for:**
- Individual handlers (GOTO, JOG, STOP) ✓
- Command parsing ✓

**Missing:**
- Command queue ordering under rapid input
- State transition edge cases

**Priority:** MEDIUM-HIGH - Could lead to unexpected dome movements.

---

### 4. Session Historical Data Export

**What's not tested:**
- Large session files (>100MB of position log)
- Concurrent session creation (race condition)
- Session data corruption recovery
- Export format validation (JSON structure)

**Files:** `web/session/session_storage.py`, `web/session/views.py`

**Test coverage exists for:**
- Basic save/load ✓
- Historical retrieval ✓

**Missing:**
- Stress tests with large datasets
- Concurrent access patterns

**Priority:** LOW - Data loss possible but rare under normal use.

---

## Numerical Stability

### 1. Angular Arithmetic Edge Cases

**Files:** `core/utils/angle_utils.py`

**Known issues:**
- `shortest_angular_distance()` handles ±180° wrapping, but tests needed for:
  - Values very close to 0° vs 360° boundary
  - Negative angles (should be normalized first)
  - Results very close to ±180°

**Impact:** MEDIUM - Affects post-meridian corrections which use large deltas.

**Test coverage:** `tests/test_angle_utils.py` (214 lines) - comprehensive but consider boundary cases.

---

### 2. Interpolation Near Abaque Boundary

**Files:** `core/tracking/abaque_manager.py` (lines ~140-200)

**Known issues:**
```python
# Interpolation outside measured ranges uses edge values
# E.g., if altitude > max in abaque, returns value at max_altitude
# May not be physically accurate
```

**Risk:** Tracking near zenith or low horizon relies on extrapolation from nearest measured point.

**Improvement:** Log warning when extrapolating outside measured region.

**Priority:** LOW - Measured abaque covers typical range (alt 0-85°).

---

---

*Concerns audit: 2026-01-22*
