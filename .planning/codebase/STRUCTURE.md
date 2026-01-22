# Codebase Structure

**Analysis Date:** 2026-01-22

## Directory Layout

```
Dome_web_v4_6/
├── core/                       # Business logic (astronomy, hardware, tracking)
│   ├── config/                 # Configuration management
│   ├── hardware/               # GPIO control, motor, encoder abstraction
│   ├── observatoire/           # Astronomical calculations, ephemerides
│   ├── tracking/               # Tracking logic (mixins composition)
│   └── utils/                  # Utility functions (angle math)
├── services/                   # Motor Service process
│   ├── motor_service.py        # Main service loop (20 Hz polling)
│   ├── command_handlers.py     # GOTO, JOG, Tracking, Continuous handlers
│   ├── ipc_manager.py          # File-based IPC read/write with fcntl locks
│   └── simulation.py           # Simulated encoder reader for dev
├── web/                        # Django web server and REST API
│   ├── driftapp_web/           # Django project settings
│   ├── hardware/               # API endpoints: /api/hardware/
│   ├── tracking/               # API endpoints: /api/tracking/
│   ├── health/                 # API endpoints: /api/health/
│   ├── session/                # API endpoints: /api/session/
│   ├── common/                 # IPC client (Motor Service communication)
│   ├── templates/              # HTML pages (dashboard, session, system)
│   └── static/                 # CSS, JavaScript (boussole, charts)
├── data/                       # Configuration and runtime data
│   ├── config.json             # Main configuration (site, motor, GPIO)
│   ├── Loi_coupole.xlsx        # Abaque (275 measurement points)
│   ├── objets_cache.json       # Cached celestial objects
│   └── sessions/               # Session recordings (JSON time series)
├── logs/                       # Runtime logs
│   ├── motor_service_*.log     # Motor Service horodated logs
│   ├── django.log              # Django output
│   └── tracking_*.log          # Tracking session logs
├── tests/                      # Test suite (pytest)
│   ├── test_*.py               # Unit tests (no hardware dependencies)
│   ├── conftest.py             # pytest fixtures and mocking
│   └── test_e2e.py             # End-to-end integration tests
├── scripts/                    # Diagnostic and calibration scripts
│   └── diagnostics/            # Manual testing utilities
├── docs/                       # Documentation and history
│   └── history/                # Version history
├── ems22d_calibrated.py        # Encoder daemon (independent process)
├── calibration_moteur.py       # Motor calibration utility
├── start_web.sh                # Multi-process startup script
├── start_dev.sh                # Development mode startup
└── pyproject.toml              # Project metadata (uv)
```

## Directory Purposes

**`core/` - Business Logic Core:**
- Purpose: Pure Python logic (no Django, no IPC)
- Contains: Astronomy, hardware abstraction, tracking algorithms
- Reused by: Motor Service, Web API, diagnostic scripts
- Key property: Testable in isolation (mocked GPIO/encoder)

**`core/config/` - Configuration Management:**
- Purpose: Load and provide application configuration
- Contains: Default values, JSON loading, config dataclasses
- Key files:
  - `config.py`: Constants and defaults (no side effects)
  - `config_loader.py`: Loading logic with deep merge
  - `logging_config.py`: Logging setup for processes
- Access pattern: Import and call functions, never modify globally

**`core/hardware/` - Hardware Abstraction:**
- Purpose: Abstract GPIO, motor control, encoder reading
- Contains:
  - `moteur.py`: MoteurCoupole (GPIO control via lgpio)
  - `moteur_simule.py`: MoteurSimule (realistic simulation)
  - `feedback_controller.py`: Closed-loop correction logic
  - `acceleration_ramp.py`: S-curve acceleration/deceleration
  - `daemon_encoder_reader.py`: Singleton wrapper for encoder file
  - `hardware_detector.py`: RPi version detection
  - `encoder_reader.py`: (Legacy, use daemon_encoder_reader)
  - `motor_config_parser.py`: Config dict → MotorConfig dataclass
- Key property: Works on RPi5 (lgpio) and dev machine (simulation)

**`core/observatoire/` - Astronomy:**
- Purpose: Celestial coordinate transformations
- Contains:
  - `calculations.py`: AstronomicalCalculations (J2000→JNOW→horizontal)
  - `ephemerides.py`: Planetary positions via astropy
  - `catalogue.py`: Celestial object search and visibility
- Key property: Thin wrapper over astropy, pure math

**`core/tracking/` - Tracking Logic:**
- Purpose: Multi-phase object tracking with feedback
- Contains:
  - `tracker.py`: TrackingSession (main class, composition via mixins)
  - `tracking_state_mixin.py`: State, statistics, logging
  - `tracking_goto_mixin.py`: Initial GOTO, encoder sync
  - `tracking_corrections_mixin.py`: Periodic correction loop
  - `adaptive_tracking.py`: Mode selection (NORMAL/CRITICAL/CONTINUOUS)
  - `abaque_manager.py`: 2D interpolation (Loi_coupole.xlsx)
  - `tracking_logger.py`: Session logging
- Key property: Mixin pattern for readability (each file ~100-150 lines)

**`core/utils/` - Utilities:**
- Purpose: Reusable math functions
- Contains: `angle_utils.py` (normalize, convert, Julian date)
- Key property: Pure functions, no side effects, fully tested

**`services/` - Motor Service Process:**
- Purpose: Real-time GPIO control in separate process
- Contains:
  - `motor_service.py`: Main 20 Hz loop, command dispatch
  - `command_handlers.py`: Handlers for GOTO, JOG, Tracking, Continuous
  - `ipc_manager.py`: Read/write `/dev/shm/` files with locks
  - `simulation.py`: Mock encoder reader for dev
- Key property: Runs as root, talks only to `core/` (no Django imports)

**`web/` - Django REST API:**
- Purpose: HTTP interface for user control
- Contains:
  - `driftapp_web/`: Django project config (settings, URLs)
  - `hardware/`: Endpoints for GOTO, JOG, encoder status
  - `tracking/`: Endpoints for start/stop/status tracking
  - `health/`: System diagnostics, update checks
  - `session/`: Session history, save/delete
  - `common/`: MotorServiceClient (IPC communication)
  - `templates/`: HTML pages (Jinja2)
  - `static/`: CSS and JavaScript assets
- Key property: Stateless (all state in Motor Service), uses IPC

**`web/driftapp_web/` - Django Settings:**
- Purpose: Django configuration
- Key files:
  - `settings.py`: DEBUG, INSTALLED_APPS, middleware
  - `urls.py`: Route mapping (api/* and static pages)
  - `wsgi.py`: WSGI application
- Access: `python manage.py` (from web/ directory)

**`web/hardware/` - Hardware Control API:**
- Purpose: Endpoints for manual motor control
- Endpoints:
  - `POST /api/hardware/goto/` → GotoView
  - `POST /api/hardware/jog/` → JogView
  - `POST /api/hardware/stop/` → StopView
  - `GET /api/hardware/encoder/` → EncoderView
  - `GET /api/hardware/status/` → StatusView
- Pattern: Each endpoint is an APIView subclass with validation

**`web/tracking/` - Tracking API:**
- Purpose: Endpoints for astronomical object tracking
- Endpoints:
  - `POST /api/tracking/start/` → Start tracking
  - `POST /api/tracking/stop/` → Stop tracking
  - `GET /api/tracking/status/` → Current tracking state
  - `GET /api/tracking/objects/` → Search catalog
  - `GET /api/tracking/search/` → Search by name/coords
- Pattern: Each endpoint creates/queries TrackingSession

**`web/health/` - System Health API:**
- Purpose: Diagnostics and update management
- Endpoints:
  - `GET /api/health/diagnostic/` → IPC, process, config status
  - `GET /api/health/system/` → RPi temperature, uptime, disk
  - `GET /api/health/update/check/` → Check git updates available
  - `POST /api/health/update/apply/` → Apply git pull
- Pattern: Read-only system inspection

**`web/session/` - Session History API:**
- Purpose: Manage tracking session recordings
- Endpoints:
  - `GET /api/session/current/` → Current recording
  - `GET /api/session/history/` → List past sessions
  - `POST /api/session/save/` → Save current to file
  - `DELETE /api/session/delete/` → Delete by ID
- Pattern: File I/O with JSON serialization

**`web/common/` - Shared Web Utilities:**
- Purpose: IPC client and common helpers
- Contains:
  - `ipc_client.py`: MotorServiceClient (singleton)
  - Initialization in `__init__.py` for eager loading
- Key property: Singleton instantiation at import time

**`web/templates/` - HTML Pages:**
- Purpose: User interface
- Pages:
  - `dashboard.html`: Main page (compass, controls, logs)
  - `session.html`: Tracking history and statistics
  - `system.html`: System information and config
  - Base template with CSS framework

**`web/static/` - Frontend Assets:**
- Purpose: Client-side functionality
- Contains:
  - `css/`: Styling
  - `js/`: Canvas compass, Chart.js graphs, API calls
- Key libraries: Chart.js (altitude/azimuth graphs), Canvas API

**`data/` - Runtime Configuration and Data:**
- Purpose: Persistent configuration and session recordings
- Files:
  - `config.json`: Site location, motor params, GPIO pins
  - `Loi_coupole.xlsx`: Abaque with 275 measurement points (2D lookup table)
  - `objets_cache.json`: Cached celestial object catalog
  - `sessions/`: JSON files with session time series
- Committed: config.json and Loi_coupole.xlsx
- Generated: objets_cache.json, sessions/

**`logs/` - Runtime Logs:**
- Purpose: Debugging and audit trail
- Files:
  - `motor_service_*.log`: Service output (horodated, max 20 files)
  - `django.log`: Web server output
  - `tracking_*.log`: Object-specific tracking logs
- Not committed: All logs are .gitignored

**`tests/` - Test Suite:**
- Purpose: Unit and integration tests
- Files:
  - `test_*.py`: Test modules (one per core module)
  - `conftest.py`: pytest fixtures, mocking setup
  - `test_e2e.py`: End-to-end scenarios
- Key property: No hardware dependencies (mocked via simulation)
- Run: `uv run pytest -v` or `uv run pytest tests/test_moteur.py -v`

**`scripts/` - Diagnostic Scripts:**
- Purpose: Manual testing and calibration
- Location: `scripts/diagnostics/`
- Not collected by pytest (not in `tests/`)
- Examples: Motor speed calibration, GPIO voltage testing, manual motor tests

**Root-Level Scripts:**
- `ems22d_calibrated.py`: Encoder daemon (run as `sudo python3`)
- `calibration_moteur.py`: Motor calibration utility
- `start_web.sh`: Main startup script (handles all 3 processes)
- `start_dev.sh`: Development shortcut (Django only)

## Key File Locations

**Entry Points:**
- `services/motor_service.py`: Motor Service main loop
- `ems22d_calibrated.py`: Encoder daemon main
- `web/manage.py`: Django management (from web/ directory)
- `start_web.sh`: Multi-process startup orchestration

**Configuration:**
- `data/config.json`: Main config (site, motor, GPIO, thresholds)
- `data/Loi_coupole.xlsx`: Measurement abaque for parallax correction
- `web/driftapp_web/settings.py`: Django settings
- `core/config/config.py`: Config constants and defaults

**Core Logic:**
- `core/tracking/tracker.py`: TrackingSession (main tracking class)
- `core/hardware/moteur.py`: MoteurCoupole (motor control)
- `core/observatoire/calculations.py`: AstronomicalCalculations
- `core/tracking/adaptive_tracking.py`: Mode selection logic
- `core/tracking/abaque_manager.py`: 2D interpolation

**IPC Communication:**
- `services/ipc_manager.py`: Motor Service side (read/write)
- `web/common/ipc_client.py`: Django side (singleton client)
- Files: `/dev/shm/motor_command.json`, `/dev/shm/motor_status.json`, `/dev/shm/ems22_position.json`

**REST API Endpoints:**
- Hardware: `web/hardware/views.py` (GOTO, JOG, encoder)
- Tracking: `web/tracking/views.py` (start/stop/status)
- Health: `web/health/views.py` (diagnostics)
- Session: `web/session/views.py` (history)

**Testing:**
- `tests/conftest.py`: pytest fixtures and mocking setup
- `tests/test_moteur.py`: Motor control tests
- `tests/test_tracker.py`: Tracking session tests
- `tests/test_calculations.py`: Astronomy calculations tests

## Naming Conventions

**Files:**
- `service_name.py`: Service main entry (motor_service.py, ems22d_calibrated.py)
- `handler_name.py`: Request handlers (command_handlers.py)
- `module_manager.py`: Manager classes (abaque_manager.py, ipc_manager.py)
- `test_module.py`: Test files for core/module.py
- `*_mixin.py`: Mixin classes (tracking_*_mixin.py)
- `*_simule.py`: Simulation versions (moteur_simule.py)

**Directories:**
- Lowercase with underscores (core, services, web, tests)
- Feature-based grouping under `web/` (hardware, tracking, health, session)
- By layer under `core/` (config, hardware, observatoire, tracking, utils)

**Python Classes:**
- PascalCase: MoteurCoupole, TrackingSession, AstronomicalCalculations
- Mixins in name: TrackingStateMixin
- Managers: AdaptiveTrackingManager, AbaqueManager
- Handlers: GotoHandler, JogHandler
- Views: GotoView, TrackingStartView
- Exceptions: Specific (TimeoutError, JSONDecodeError) or CustomError subclasses

**Functions:**
- snake_case: get_motor_config(), normalize_angle_360()
- Private: _prefix for internal helpers (_load_json, _deep_update)
- Dunder: __init__, __enter__, __exit__ (standard Python)

**Variables:**
- snake_case: motor_delay, check_interval, current_position
- Constants: UPPERCASE (MOTOR_GEAR_RATIO, MAX_LOG_FILES)
- Private instance: _prefix (self._daemon_reader)

## Where to Add New Code

**New Hardware Feature (e.g., temperature sensor):**
1. Add sensor class to `core/hardware/temperature_sensor.py`
2. Integrate into Motor Service: `services/motor_service.py` initialization
3. Add IPC field to `/dev/shm/motor_status.json` schema
4. Create endpoint in `web/health/views.py` (e.g., `GET /api/health/temperature/`)
5. Add tests: `tests/test_temperature_sensor.py` (mock sensor in conftest.py)

**New REST API Endpoint (e.g., calibration):**
1. Create app if needed: `web/calibration/` (mkdir, create __init__.py, urls.py, views.py)
2. Add endpoint view: `web/calibration/views.py` extending APIView
3. Register URLs: Add to `web/calibration/urls.py`, include in `web/driftapp_web/urls.py`
4. If needs Motor Service: Use `motor_client.send_command()` in view
5. Tests: Create `tests/test_calibration_views.py` with mock motor_client

**New Tracking Algorithm:**
1. Create mixin: `core/tracking/tracking_new_feature_mixin.py`
2. Add to TrackingSession parents: `class TrackingSession(existing, NewFeatureMixin)`
3. Add configuration to `data/config.json` if needed
4. Tests: `tests/test_tracking_new_feature.py` with mock moteur and encoder

**New Utility Function:**
1. Add to `core/utils/angle_utils.py` or create `core/utils/new_util.py`
2. Keep pure (no side effects, no I/O)
3. Include docstring and type hints
4. Tests: `tests/test_new_util.py`

**New Diagnostic Script:**
1. Create in `scripts/diagnostics/my_diagnostic.py`
2. Must be standalone (can import core/)
3. Document usage in comment header
4. Do NOT put in `tests/` (won't be collected by pytest)

## Special Directories

**`/dev/shm/` (Shared Memory, not in repo):**
- Purpose: Fast inter-process communication via memory-mapped files
- Files:
  - `motor_command.json`: Django → Motor Service (command queue)
  - `motor_status.json`: Motor Service → Django (state publishing)
  - `ems22_position.json`: Encoder daemon → all processes (encoder angle)
- Generated: Created at runtime by first process to write
- Committed: No (ephemeral)

**`.venv/` (Virtual Environment, not in repo):**
- Purpose: Isolated Python dependencies
- Generated: Yes, by `uv sync`
- Committed: No (.gitignored)

**`logs/` (Runtime Logs, not in repo):**
- Purpose: Audit trail and debugging
- Generated: Yes, by Motor Service, Django, and tracking handlers
- Committed: No (.gitignored)
- Cleanup: Motor Service keeps 20 most recent horodated files

**`data/sessions/` (Tracking Recordings, committed to git):**
- Purpose: Persistent storage of tracking sessions
- Generated: Yes, by web/session/views.py on save
- Committed: Yes (time series data for analysis)
- Format: JSON with timestamp, altitude, azimuth, status per correction

---

*Structure analysis: 2026-01-22*
