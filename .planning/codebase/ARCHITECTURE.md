# Architecture

**Analysis Date:** 2026-01-22

## Pattern Overview

**Overall:** Three-process architecture with inter-process communication (IPC) via shared JSON files in `/dev/shm/`

**Key Characteristics:**
- Decoupled processes with independent GILs (no threading contention)
- Separate Motor Service process for GPIO timing without interference
- Encoder daemon runs as independent systemd service
- Django web server communicates via atomic file-based IPC
- Event-driven design with command-status polling pattern

## Layers

**Presentation Layer (Django Web):**
- Purpose: REST API endpoints and HTML interface for user interaction
- Location: `web/`
- Contains: View classes, URL routing, static assets, templates
- Depends on: IPC client (`web/common/ipc_client.py`), session storage
- Used by: Web browsers, JavaScript frontend

**IPC Communication Layer:**
- Purpose: Thread-safe, atomic inter-process message passing
- Location: `services/ipc_manager.py` (Motor Service), `web/common/ipc_client.py` (Django)
- Contains: File locking (fcntl), JSON serialization, command dispatch
- Depends on: Filesystem (`/dev/shm/`), standard library
- Used by: Motor Service and Django for state synchronization

**Motor Service Layer:**
- Purpose: GPIO control with real-time timing (20 Hz polling loop)
- Location: `services/motor_service.py`
- Contains: Command routing, watchdog (systemd sdnotify), log rotation
- Depends on: Core hardware, command handlers, IPC manager
- Used by: Hardware controllers, tracking handlers

**Hardware Control Layer:**
- Purpose: Low-level stepper motor and encoder abstraction
- Location: `core/hardware/`
- Contains:
  - `moteur.py`: GPIO pulse control (lgpio for RPi5)
  - `moteur_simule.py`: Simulation mode for development
  - `feedback_controller.py`: Closed-loop correction
  - `acceleration_ramp.py`: S-curve acceleration/deceleration
  - `daemon_encoder_reader.py`: Singleton reader for encoder position
  - `hardware_detector.py`: RPi4/5 auto-detection
- Depends on: lgpio (RPi5) or fallback simulation
- Used by: Motor Service handlers, command executors

**Tracking/Astronomy Layer:**
- Purpose: Astronomical calculations and object tracking logic
- Location: `core/tracking/`, `core/observatoire/`
- Contains:
  - `tracker.py`: TrackingSession (main composition via mixins)
  - `tracking_state_mixin.py`: State management and statistics
  - `tracking_goto_mixin.py`: Initial GOTO and encoder sync
  - `tracking_corrections_mixin.py`: Periodic correction loop
  - `adaptive_tracking.py`: Zone-based parameter adaptation (NORMAL/CRITICAL/CONTINUOUS)
  - `calculations.py`: J2000→JNOW conversion, horizontal coordinates
  - `ephemerides.py`: Planetary positions (astropy)
  - `catalogue.py`: Celestial object search
  - `abaque_manager.py`: 2D interpolation from Loi_coupole.xlsx measurements
- Depends on: astropy, openpyxl, hardware abstraction
- Used by: Tracking command handler, web tracking API

**Configuration Layer:**
- Purpose: Centralized, immutable configuration from `data/config.json`
- Location: `core/config/`
- Contains:
  - `config.py`: Defaults and runtime values (no side effects)
  - `config_loader.py`: Loading and merging logic
  - `logging_config.py`: Logging initialization
- Depends on: JSON file I/O, standard library only
- Used by: All layers for site/motor/gpio/dome parameters

**Utilities Layer:**
- Purpose: Reusable mathematical and helper functions
- Location: `core/utils/`
- Contains: `angle_utils.py` (normalization, conversion, Julian date calculations)
- Depends on: Standard library only
- Used by: All astronomical/geometric calculations

## Data Flow

**Command Execution (GOTO):**

1. Web browser sends POST `/api/hardware/goto/?angle=45.0`
2. `GotoView` in `web/hardware/views.py` validates and calls `motor_client.send_command('goto', angle=45.0)`
3. `motor_client` (singleton in `web/common/ipc_client.py`) writes atomic JSON to `/dev/shm/motor_command.json` with fcntl lock
4. Motor Service polling loop in `services/motor_service.py` reads command via `ipc_manager.read_command()`
5. `GotoHandler` in `services/command_handlers.py` extracts angle, calculates delta, executes via `moteur.rotation_absolue()`
6. Motor Service writes updated status to `/dev/shm/motor_status.json`
7. Django reads status periodically via `motor_client.get_motor_status()`
8. Web UI updates via JSON API response

**Tracking Session Flow:**

1. Web requests `/api/tracking/start/` with object name and parameters
2. `TrackingHandler` creates `TrackingSession` instance
3. Session performs initial GOTO to object position (using feedback for precision)
4. Enters correction loop with periodic checks every 60s (NORMAL) or 15s (CRITICAL)
5. For each correction:
   - Calculate target azimuth/altitude via `AstronomicalCalculations`
   - Read current position from `/dev/shm/ems22_position.json` (daemon updates at 50 Hz)
   - Apply abaque interpolation for parallax correction
   - If delta > threshold: apply correction via `feedback_controller` or direct rotation
   - Log session data to file
6. Motor Service publishes tracking status to `/dev/shm/motor_status.json`
7. Web UI reads and displays real-time tracking state

**State Management:**

- **Motor position:** Encoder daemon publishes to `/dev/shm/ems22_position.json` (absolute, 50 Hz)
- **Motor status:** Motor Service publishes to `/dev/shm/motor_status.json` (mode, logs, history)
- **Commands:** Django writes to `/dev/shm/motor_command.json` (atomic, command ID prevents duplicates)
- **Sessions:** Stored in `data/sessions/` as JSON files with altitude/azimuth time series

## Key Abstractions

**MotorServiceClient (Singleton):**
- Purpose: Encapsulate IPC communication for Django
- Implementation: `web/common/ipc_client.py`
- Pattern: Lazy singleton with thread-safe JSON read/write
- Usage: All hardware/tracking views call `motor_client.send_command()` or `.get_motor_status()`

**TrackingSession (Composition via Mixins):**
- Purpose: Orchestrate multi-phase tracking lifecycle
- Implementation: `core/tracking/tracker.py`
- Pattern: Mixin composition (TrackingStateMixin, TrackingGotoMixin, TrackingCorrectionsMixin)
- Why: Separation of concerns (state/GOTO/corrections in separate files)

**DaemonEncoderReader (Singleton):**
- Purpose: Lazy-load and cache encoder daemon file reader
- Implementation: `core/hardware/daemon_encoder_reader.py`
- Pattern: Global singleton with explicit `get_daemon_reader()`, `set_daemon_reader()`, `reset_daemon_reader()`
- Why: Avoid repeated file I/O, support test mocking

**AdaptiveTrackingManager (Strategy):**
- Purpose: Adapt motor speed/check interval based on altitude zone
- Implementation: `core/tracking/adaptive_tracking.py`
- Pattern: Strategy pattern with three modes (NORMAL, CRITICAL, CONTINUOUS)
- Modes:
  - NORMAL: Alt < 68°, delay 2.0ms, interval 60s
  - CRITICAL: 68° ≤ Alt < 75°, delay 1.0ms, interval 15s
  - CONTINUOUS: Alt ≥ 75°, delay 0.15ms, interval 5s

**AstronomicalCalculations:**
- Purpose: Convert celestial to horizontal coordinates
- Implementation: `core/observatoire/calculations.py`
- Pattern: Stateless utility class with astropy integration
- Key methods: `get_horizontal_coords()` (J2000→JNOW→horizontal)

**MoteurCoupole (Hardware Abstraction):**
- Purpose: Abstract motor control (GPIO/simulation)
- Implementation: `core/hardware/moteur.py` + `core/hardware/moteur_simule.py`
- Pattern: Polymorphism via `is_simulated()` check or isinstance
- Why: Single codebase works on RPi and dev machine

## Entry Points

**Motor Service Startup:**
- Location: `services/motor_service.py` line 1 (execute as `sudo python3 services/motor_service.py`)
- Triggers: Manual execution or systemd service (motor_service.service)
- Responsibilities:
  - Initialize hardware (real or simulated)
  - Load configuration
  - Enter 20 Hz polling loop reading IPC commands
  - Dispatch to handlers (GOTO, JOG, Tracking, etc.)
  - Write status back to IPC
  - Handle SIGTERM gracefully (systemd watchdog)

**Encoder Daemon:**
- Location: `ems22d_calibrated.py` line 1 (execute as `sudo python3 ems22d_calibrated.py`)
- Triggers: Systemd service (ems22d.service) or manual execution
- Responsibilities:
  - Read SPI (EMS22A encoder) at 50 Hz
  - Apply calibration via 45° switch
  - Filter jitter (median window)
  - Publish absolute angle to `/dev/shm/ems22_position.json`
  - Maintain TCP server for legacy clients (port 5556)

**Django Web Server:**
- Location: `web/manage.py` (execute as `python manage.py runserver 0.0.0.0:8000`)
- Triggers: Manual execution or systemd service (driftapp_web.service)
- Responsibilities:
  - Serve REST API endpoints (`/api/hardware/`, `/api/tracking/`, etc.)
  - Serve HTML templates (dashboard, session, system pages)
  - Dispatch user commands via IPC to Motor Service
  - Read and display Motor Service status

**Startup Script:**
- Location: `start_web.sh`
- Triggers: `sudo ./start_web.sh {start|stop|restart|status}`
- Responsibilities:
  - Check systemd or manual encoder daemon status
  - Start Motor Service (root required for GPIO)
  - Start Django (user permissions for logs/data)
  - Manage permission delegation (SUDO_USER)
  - Rotate old logs

## Error Handling

**Strategy:** Exception specificity with context logging

**Patterns:**

**IPC Failures:**
```python
# web/common/ipc_client.py: Non-blocking lock with timeout fallback
try:
    fcntl.flock(f.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
    return json.load(f)
except BlockingIOError:  # Motor Service writing, skip this read
    return None
except FileNotFoundError:  # IPC file not created yet
    return None
except json.JSONDecodeError:  # Corrupted JSON from crash
    return None
```

**Hardware Failures:**
```python
# services/command_handlers.py: Graceful motor fallback
if moteur.is_simulated():
    # Use simulation position instead of feedback
    set_simulated_position(...)
else:
    # Real hardware: use feedback_controller
    feedback_controller.correct_position(...)
```

**Tracking Failures:**
```python
# core/tracking/tracker.py: Tracking with exception context
try:
    current_position = encoder_reader.read_angle(timeout=1.0)
except TimeoutError:
    logger.error(f"Encoder timeout for {self.object_name}")
    return False  # Don't correct on bad data
except json.JSONDecodeError:
    logger.error("Encoder file corrupted, skipping correction")
    return False
```

**Configuration Errors:**
```python
# core/config/config.py: Deep merge with defaults
if not path.exists():
    return {}  # Use defaults
try:
    return json.load(f)
except Exception:
    return {}  # Silent fallback to defaults
```

**Logging Strategy:**
- Motor Service: Horodated files in `logs/motor_service_YYYYMMDD_HHMMSS.log`
- Tracking: Session-specific logs in `logs/tracking_[object]_[timestamp].log`
- Django: File and console output
- All: Rotate old logs, keep 20 most recent

## Cross-Cutting Concerns

**Logging:**
- Framework: Python `logging` module
- Per-layer loggers: `__name__` passed to `getLogger()`
- Rotating file handlers for Motor Service (cleanup_old_logs)
- Tracking logger: `TrackingLogger` class for session-specific output

**Validation:**
- Input validation in Django views before IPC dispatch
- Config validation in `config_loader.py` with defaults fallback
- Angle normalization via `angle_utils.normalize_360()` or `normalize_angle_180()`
- Object name validation in tracking (search catalog first)

**Authentication:**
- None (local network only, running on Raspberry Pi at observatory)
- Django DEBUG mode configurable via DJANGO_DEBUG env var
- File permissions managed by `start_web.sh` setup_permissions()

**Concurrency:**
- No multithreading within Motor Service (single loop, no GIL contention)
- IPC: fcntl locks prevent race conditions (shared file reads/writes)
- Django: WSGI handles concurrent requests, reads Motor status atomically
- Encoder daemon: Single-threaded at 50 Hz with median filter

**Testing:**
- Mocking via `core/hardware/moteur_simule.py` (MoteurSimule)
- Simulated encoder reader via `services/simulation.py` (SimulatedDaemonReader)
- No hardware dependencies in unit tests
- Mock GPIO via lgpio unavailable → automatic fallback to simulation

---

*Architecture analysis: 2026-01-22*
