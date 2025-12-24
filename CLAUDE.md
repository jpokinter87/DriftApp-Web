# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**DriftApp Web** is an astronomical observatory dome control application for Observatoire Ubik (France). This web-only version uses Django exclusively for remote control.

**Hardware**: Raspberry Pi 4, stepper motor (NEMA 200 steps/rev), DM556T driver (4 microsteps), EMS22A magnetic encoder (10-bit), 2230:1 gear ratio.

## Build & Development Commands

```bash
# Install dependencies
uv sync

# Start complete system (encoder daemon + motor service + Django)
sudo ./start_web.sh

# Development mode (Django only, simulation mode auto-detected)
cd web && python manage.py runserver 0.0.0.0:8000

# Run all tests
uv run pytest -v

# Quick tests (no astropy dependency)
uv run pytest tests/test_angle_utils.py tests/test_config.py tests/test_moteur.py tests/test_feedback_controller.py tests/test_ipc_manager.py tests/test_simulation.py tests/test_acceleration_ramp.py -v

# Run single test file or class
uv run pytest tests/test_moteur.py::TestMoteurCoupoleControl -v

# Manual hardware diagnostics (Raspberry Pi only)
sudo python3 scripts/diagnostics/diagnostic_moteur_complet.py
```

## Architecture

### Three-Process IPC Architecture

```
Django (port 8000) ──► /dev/shm/motor_command.json ──► Motor Service
                                                            │
                   ◄── /dev/shm/motor_status.json ◄─────────┘
                                                            │
Encoder Daemon ────► /dev/shm/ems22_position.json ──────────┘
```

### Key Directories

- `core/` - Business logic (hardware control, tracking, astronomical calculations)
- `services/` - Motor Service IPC process (refactored into 4 modules)
- `web/` - Django web interface
- `tests/` - Pytest unit tests (315+ tests)
- `scripts/diagnostics/` - Manual hardware test scripts

### Motor Service Modules (services/)

| Module | Purpose |
|--------|---------|
| `motor_service.py` | Main service class, event loop |
| `command_handlers.py` | GOTO, JOG, Continuous, Tracking handlers |
| `ipc_manager.py` | JSON file read/write for IPC |
| `simulation.py` | SimulatedDaemonReader for dev mode |

### Adaptive Tracking Modes

| Mode | Trigger | Motor Delay | Use Case |
|------|---------|-------------|----------|
| NORMAL | altitude < 68° | 2.0 ms | Standard tracking |
| CRITICAL | 68° ≤ alt < 75° | 1.0 ms | Near-zenith |
| CONTINUOUS | alt ≥ 75° or Δ > 30° | 0.15 ms | Zenith + GOTO |

### GOTO Optimization (v4.4)

- **Large movements (> 3°)**: Direct rotation (fluid) + final feedback correction
- **Small movements (≤ 3°)**: Feedback loop for precision
- **JOG (manual buttons)**: Always direct rotation (maximum fluidity)
- **UX Feedback**: Initial GOTO during tracking shows position details: `44.9° → 258.6° (+146.2°)`

### Acceleration Ramp (v4.5)

Motor protection via S-curve acceleration/deceleration (`core/hardware/acceleration_ramp.py`):
- **Start delay**: 3ms (slow start to reduce motor stress)
- **Ramp steps**: 500 steps for acceleration, 500 for deceleration
- **S-curve**: Smooth sigmoid transition (not linear)
- **Automatic**: Enabled by default via `use_ramp=True` in `rotation()`

## Key Files

- `data/config.json` - Centralized configuration (site, motor, GPIO, tracking)
- `data/Loi_coupole.xlsx` - Dome correction lookup table (275 measured points)
- `ems22d_calibrated.py` - Encoder daemon with auto-calibration

## Testing Notes

- Tests use mocks for GPIO/hardware (no Raspberry Pi required)
- `test_command_handlers.py` and `test_calculations.py` require astropy
- Manual hardware tests are in `scripts/diagnostics/`, not collected by pytest
