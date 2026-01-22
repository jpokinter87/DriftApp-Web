# External Integrations

**Analysis Date:** 2026-01-22

## APIs & External Services

**Astronomical Data (Optional):**
- SIMBAD (Centre de Données Astronomiques de Strasbourg)
  - What it's used for: Celestial object search and coordinate lookup
  - SDK/Client: astroquery.simbad.Simbad
  - Implementation: `core/observatoire/catalogue.py` (GestionnaireCatalogue.rechercher_simbad)
  - Auth: None (public API, optional usage)
  - Fallback: Local JSON cache in `data/objets_cache.json`
  - Network: HTTP/HTTPS, requires internet connection

**IERS (International Earth Rotation Service):**
- What it's used for: Polar motion and UT1-UTC corrections for accurate celestial coordinates
- SDK/Client: astropy.iers via astropy-iers-data
- Implementation: `core/observatoire/calculations.py` (coordinate transformations)
- Auth: None (public data, auto-downloaded)
- Caching: Cached locally by astropy (~300 MB initial download)

## Data Storage

**Databases:**
- SQLite (django.db.backends.sqlite3)
  - Purpose: Django ORM metadata, sessions, user data
  - Location: `web/db.sqlite3` (auto-created by Django)
  - Usage: Django admin, session management (minimal, no domain models)
  - No custom migrations (application uses default Django tables only)

**File Storage:**
- Local filesystem (no cloud storage)
  - Configuration: `data/config.json` (JSON, read on startup)
  - Excel abaque: `data/Loi_coupole.xlsx` (optical correction table, 275 points)
  - Cache: `data/objets_cache.json` (celestial object cache from SIMBAD)
  - Session logs: `logs/` directory (timestamped per session/startup)

**Shared Memory (IPC):**
- /dev/shm filesystem (Linux shared memory)
  - Purpose: Real-time communication between Django, Motor Service, Encoder daemon
  - Files:
    - `/dev/shm/motor_command.json` - Command queue
    - `/dev/shm/motor_status.json` - Status updates (50+ times/sec)
    - `/dev/shm/ems22_position.json` - Encoder position (50 Hz)
  - Access: fcntl file locking for atomicity
  - Persistence: None (volatile, cleared on reboot)

**Caching:**
- None (no Redis, Memcached, or similar)
- In-memory Python objects:
  - GestionnaireCatalogue.objets (loaded once at startup)
  - Motor state in MoteurCoupole instance
  - Encoder reader singleton in daemon_encoder_reader.get_daemon_reader()

## Authentication & Identity

**Auth Provider:**
- None (disabled/custom)
  - Django auth: Disabled (AUTH_PASSWORD_VALIDATORS = [])
  - ALLOWED_HOSTS: '*' (permissive, local network only)
  - SECRET_KEY: Hardcoded development key (must change in production per settings.py comment)
  - Permission classes: rest_framework.permissions.AllowAny

**Access Control:**
- No HTTP authentication
- Network isolation: Intended for local Raspberry Pi network only
- Security model: Trust network, no per-user accounts

## Hardware Integration

**GPIO Control (Raspberry Pi 4/5):**
- lgpio library (GPIO Line-based I/O)
  - Purpose: Motor stepper driver pulse/direction control
  - Implementation: `core/hardware/moteur.py` (MoteurCoupole class)
  - Pins (BCM numbering): DIR=17, STEP=18
  - Driver: DM556T stepper driver (4-microstep capable)

**SPI Encoder Interface:**
- spidev library
  - Purpose: EMS22A magnetic rotary encoder position reading
  - Implementation: `core/hardware/daemon_encoder_reader.py` (DaemonEncoderReader)
  - Bus/Device: SPI0/CE0 (configurable in data/config.json)
  - Speed: 1 MHz (spi.speed_hz)
  - Resolution: 1024 positions per revolution (10-bit)
  - Update rate: 50 Hz (20ms sampling in daemon)

**systemd Integration (Raspberry Pi):**
- sdnotify library
  - Purpose: Watchdog notifications for Motor Service health
  - Implementation: `services/motor_service.py` (sends WATCHDOG=1 heartbeat)
  - Service files: `ems22d.service`, `motor_service.service`
  - Watchdog timeout: 30 seconds (motor_service.service)

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry, Rollbar, or similar)
- Local logging only

**Logs:**
- Python logging module (stdlib)
- File-based logging to `logs/` directory
  - Format: Rotating file handlers (10 MB per file, 5 backups for motor service, 20 for Django)
  - Timestamps: Session-based (datetime format: YYYYMMDD_HHMMSS)
  - Log files:
    - `logs/motor_service_YYYYMMDD_HHMMSS.log` - Motor Service process
    - `logs/django_YYYYMMDD_HHMMSS.log` - Django web process
    - `logs/diagnostic_moteur_*.txt` - Manual diagnostic runs
  - Log level: INFO (configurable in data/config.json)

**Performance Monitoring:**
- No APM (Application Performance Monitoring)
- Manual diagnostics via scripts in `scripts/diagnostics/`

**Health Checks:**
- Web endpoint: `web/health/` app (API: `/api/health/diagnostic`, `/api/health/system`)
- Motor Service watchdog: systemd Type=notify with 30s timeout

## CI/CD & Deployment

**Hosting:**
- Raspberry Pi 4 or 5 (on-premise, not cloud)
- Single machine deployment (no distributed system)

**CI Pipeline:**
- None detected (no GitHub Actions, GitLab CI, Jenkins)
- Manual deployment via `start_web.sh` script

**Deployment:**
- `start_web.sh` - Shell script to start all services (systemd services + Django)
- Service management: systemd units
  - `ems22d.service` - Encoder daemon
  - `motor_service.service` - Motor control service
  - Django: Managed separately (runserver or gunicorn)

**Version Control:**
- Git (tracked in `.git/`)
- Branch: main (current branch per git status)

## Environment Configuration

**Required env vars:**
- `DJANGO_DEBUG` - Controls debug mode (default: true)
  - Production: Set to 'false', '0', or 'no'

**Secrets location:**
- Hardcoded in `web/driftapp_web/settings.py`:
  - SECRET_KEY: 'django-insecure-driftapp-dev-key-change-in-production' (MUST change)
- No .env file detected
- Production: Use environment-based SECRET_KEY injection

**Configuration files (non-secret):**
- `data/config.json` - All operational parameters (no passwords)
- Committed to git (safe to store)

## Webhooks & Callbacks

**Incoming:**
- None (API is pull/request-response only)

**Outgoing:**
- None (no external system notifications)

**Real-time Updates:**
- Django REST API polling from frontend (every 2 seconds for system page)
- No WebSocket (polling only)

## Network Stack

**Protocol:**
- HTTP/REST (no HTTPS in development, should add in production)
- Port: 8000 (Django development server)
- Binding: 0.0.0.0 (all interfaces, suitable for local network)

**API Design:**
- RESTful JSON API via Django REST Framework
- Endpoints structure:
  - `/api/hardware/*` - Motor commands (goto, jog, stop, continuous)
  - `/api/tracking/*` - Astronomical tracking (start, stop, search, objects)
  - `/api/health/*` - System health and diagnostics
  - `/api/session/*` - Session history and data

---

*Integration audit: 2026-01-22*
