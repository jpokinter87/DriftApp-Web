# Technology Stack

**Analysis Date:** 2026-01-22

## Languages

**Primary:**
- Python 3.11+ - Backend service, motor control, astronomical calculations, web interface
- HTML5 - Web templates in `web/templates/`
- CSS3 - Styling in `web/static/`
- JavaScript (ES6+) - Interactive UI (canvas boussole, Chart.js charts) in `web/static/`

## Runtime

**Environment:**
- Python 3.11 (minimum requirement per `pyproject.toml`)
- Target: Raspberry Pi 4/5 (aarch64 architecture)
- Linux (Debian-based on RPi)

**Package Manager:**
- uv (modern Python package manager)
- Lockfile: `uv.lock` (present, ensures reproducible builds)

## Frameworks

**Core Web:**
- Django 4.2.0+ - REST API and web interface in `web/` directory
- Django REST Framework 3.14.0+ - API endpoints in `web/hardware/`, `web/tracking/`, `web/health/`, `web/session/`

**Testing:**
- pytest 7.0.0+ - Test runner configured in `pytest.ini`
- pytest-cov 4.0.0+ - Coverage reporting

**Build/Dev:**
- Hatchling - Build backend (`[build-system]` in `pyproject.toml`)
- Black 23.0.0+ - Code formatter (line-length: 100)
- Ruff 0.1.0+ - Linter (line-length: 100, target-version: py311)

## Key Dependencies

**Astronomy & Calculations:**
- astropy 6.0.0+ - Coordinate transformations (J2000→JNow), time calculations in `core/observatoire/calculations.py`
- astroquery 0.4.7+ - SIMBAD API client for celestial object search in `core/observatoire/catalogue.py`
- pyerfa 2.0.0+ - Fundamental astronomy library (required by astropy)

**Scientific Computing:**
- numpy 1.24.0+ - Array operations for optical calculations, numerical methods
- scipy 1.10.0+ - Interpolation (scipy.interpolate for abaque manager)
- pandas 2.0.0+ - Data manipulation for session analysis and logging

**Data Handling:**
- openpyxl 3.1.0+ - Excel file parsing for astronomical abaque (`data/Loi_coupole.xlsx`) in `core/tracking/abaque_manager.py`
- PyYAML 6.0.0+ - Configuration file handling

**Hardware Control (Raspberry Pi only):**
- lgpio 0.2.2.0+ - GPIO control for motor stepper driver via lgpio library in `core/hardware/moteur.py` (replaces deprecated RPi.GPIO)
- spidev 3.5+ - SPI interface for EMS22A magnetic encoder in `core/hardware/daemon_encoder_reader.py`

**System Integration (Raspberry Pi only):**
- sdnotify 0.3.2+ - systemd watchdog notification in `services/motor_service.py` (Type=notify)

**HTTP & Network:**
- requests 2.31.0+ - HTTP library for astroquery SIMBAD lookups
- urllib3 2.0.0+ - HTTP client pooling (dependency of requests)

**Utilities:**
- packaging 23.0+ - Version parsing for compatibility checks

## Configuration

**Environment:**
- Settings via `web/driftapp_web/settings.py` (Django settings module)
- Core configuration: `data/config.json` (centralized config with motor, site, tracking, encoder parameters)
- Environment variables:
  - `DJANGO_DEBUG` - Controls DEBUG flag (default: true, set DJANGO_DEBUG=0 for production)
  - `DJANGO_SETTINGS_MODULE` - Not explicitly set (defaults to driftapp_web.settings)

**Build:**
- `pyproject.toml` - Project metadata, dependencies, build configuration
- `uv.lock` - Locked dependency versions for reproducibility
- `pytest.ini` - Test runner configuration
- Setup files: `web/manage.py` (Django management script)

**Runtime Configuration Files:**
- `data/config.json` - Motor, encoder, site, adaptive tracking parameters (version 2.3)
- `data/Loi_coupole.xlsx` - Optical correction abaque (275 measured points)
- `data/sync_config.json` - Configuration sync metadata

## Platform Requirements

**Development:**
- Python 3.11+ with pip/uv
- For hardware testing: mock GPIO (no Raspberry Pi needed)
- Optional: astropy data cache directory (~300 MB for IERS data)

**Production:**
- Raspberry Pi 4 or 5 (aarch64)
- Debian-based Linux (Raspberry Pi OS)
- GPIO access (must run motor_service as root via systemd)
- /dev/shm filesystem for IPC (shared memory for JSON files)
- systemd for service management (ems22d.service, motor_service.service)

## IPC & Process Communication

**Inter-Process Communication:**
- JSON files in `/dev/shm/` (shared memory, survives reboot):
  - `/dev/shm/motor_command.json` - Commands from Django → Motor Service
  - `/dev/shm/motor_status.json` - Status from Motor Service → Django
  - `/dev/shm/ems22_position.json` - Encoder position from daemon (50 Hz updates)
- File locking: `fcntl` locks for atomic reads/writes

**Three-Process Architecture:**
1. Django web process (port 8000) - HTTP API, UI
2. Motor Service process (systemd service) - GPIO/hardware control, 20 Hz loop
3. Encoder Daemon process (systemd service) - SPI encoder reader, 50 Hz updates

---

*Stack analysis: 2026-01-22*
