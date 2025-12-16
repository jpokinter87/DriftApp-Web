# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## RÈGLE OBLIGATOIRE : Git Commit après modifications

**Après chaque session de modifications de fichiers, tu DOIS :**

1. Vérifier les fichiers modifiés : `git status`
2. Ajouter les fichiers : `git add .`
3. Créer un commit descriptif : `git commit -m "Description concise des changements"`
4. Pousser vers GitHub : `git push`

**Format du message de commit :**
- Fix: pour les corrections de bugs
- Feat: pour les nouvelles fonctionnalités
- Config: pour les changements de configuration
- Refactor: pour les refactorisations

Exemple : `git commit -m "Fix: correction bug GOTO demi-tour dans tracker.py"`

---

## Project Overview

**DriftApp** - Intelligent astronomical observatory dome tracking system with parallax compensation, adaptive modes, and real-time feedback. Designed for Raspberry Pi with Terminal UI (TUI).

The system automatically tracks celestial objects by compensating for:
- Earth's rotation
- Instrumental parallax (40cm tube offset, 120cm dome radius)
- Sky discontinuities in critical zones (high altitude tracking)

**Documentation complète de la logique de tracking : voir `TRACKING_LOGIC.md`**

## Development Commands

### Running the Application

```bash
# Activate virtual environment (if using standard venv)
source .venv/bin/activate

# Or with uv (package manager used in this project)
uv sync  # Install/update dependencies
uv run main.py  # Run the application

# Standard Python execution
python main.py
```

### Starting the Encoder Daemon (Production)

The encoder daemon must run independently to provide position feedback without SPI interference:

**Standard daemon** (without calibration switch):
```bash
# Make executable and run with sudo (requires SPI access)
sudo python3 ems22d_calibrated.py &

# Check daemon output
cat /dev/shm/ems22_position.json

# Monitor daemon logs (writes to logs/ems22d.log)
tail -f logs/ems22d.log
```

**Daemon with calibration switch** (Dec 2025 upgrade):
```bash
# Stop old daemon first to avoid port conflict
sudo pkill -f ems22d_calibrated

# Run daemon (includes switch support as of Dec 6, 2025)
sudo python3 ems22d_calibrated.py &

# Monitor logs in real-time
tail -f logs/ems22d.log

# The daemon will auto-calibrate to 45° when dome passes the switch position
# Switch: SS-5GL on GPIO 27, normally open (NO)
# Expected log: "🔄 Microswitch activé → recalage à 45°"
```

### Testing

```bash
# Test motor speeds and microstepping configuration
python tests/test_motor_speeds.py

# Simulate tracking trajectory (Eltanin example)
python tests/simulate_eltanin_adaptive.py

# Visual encoder angle gauge (real-time monitoring)
python tests_sur_site/ems22a_ring_gauge4_V2.py

# Test direct du switch de calibration (GPIO 27)
sudo python3 tests_sur_site/test_switch_direct.py
```

### Field Tests

The `tests_sur_site/` directory contains real field test logs and tools:
- **ems22a_ring_gauge4_V2.py**: Tkinter GUI showing real-time encoder angle with compass-style display
- **Log files**: Timestamped logs from on-site tests (driftapp_*.log, textual_*.log)
- **Screenshots**: TUI interface captures during live tracking sessions
- **Photos**: Hardware setup documentation

## Architecture Overview

### Key Architectural Principles

1. **Daemon-Based Encoder Architecture**: The encoder (EMS22A) runs in a separate daemon process (`ems22d_calibrated.py`) that publishes position data to `/dev/shm/ems22_position.json`. This isolates SPI communication from motor control, eliminating interference.

2. **Adaptive Tracking System**: Three automatic modes adjust tracking parameters based on sky position:
   - **NORMAL** (Alt < 68°): Standard tracking, 60s intervals
   - **CRITICAL** (68° ≤ Alt < 75°): Increased frequency, 15s intervals
   - **CONTINUOUS** (Alt ≥ 75° or large movements): Very frequent corrections, 5s intervals

3. **Dual Calculation Methods**:
   - **Vectorielle**: Geometric 3D calculation with parallax correction (theoretical)
   - **Abaque**: Interpolation from real site measurements in `data/Loi_coupole.xlsx` (preferred, accounts for mechanical reality)

4. **Modular Hardware Abstraction**: `core/hardware/` supports both Raspberry Pi 4 (RPi.GPIO) and Pi 5 (lgpio) with automatic detection via `hardware_detector.py`.

### Directory Structure

```
core/
├── config/              # Configuration loading and logging setup
│   ├── config.py       # Main config with MICROSTEPS, gear_ratio, site location
│   ├── config_loader.py # JSON config parser
│   └── logging_config.py

├── hardware/           # Motor control and encoder feedback
│   ├── moteur.py      # Stepper motor control (CRITICAL: MICROSTEPS=4)
│   ├── moteur_feedback.py  # Closed-loop feedback using daemon encoder
│   └── hardware_detector.py # Auto-detect Pi model and GPIO library

├── tracking/           # Tracking logic and adaptive algorithms
│   ├── tracker.py     # Main tracking session manager
│   ├── adaptive_tracking.py  # 3-mode adaptive system
│   ├── predictive_anticipation.py  # Future movement prediction
│   ├── abaque_manager.py  # Interpolation from measurement data
│   └── tracking_logger.py # Structured logging

├── observatoire/       # Astronomical calculations
│   ├── calculations.py # Coordinate conversions, parallax
│   ├── ephemerides.py # Planetary positions (Astropy)
│   └── catalogue.py   # Deep sky object catalog

└── ui/                 # Terminal user interface (Textual)
    ├── main_screen.py # Main TUI application
    ├── modals.py      # Configuration dialogs
    └── styles.py      # Visual theme
```

### Critical Files and Their Interactions

**Flow: Tracking an Object**

1. **User Input** (`core/ui/main_screen.py`):
   - User selects object from catalog or enters coordinates
   - Configures threshold, interval, method (vectorielle/abaque)

2. **Tracking Session** (`core/tracking/tracker.py`):
   - Creates `TrackingSession` with selected parameters
   - Calculates target position using either:
     - `AstronomicalCalculations` (vectorielle method), OR
     - `AbaqueManager` (interpolation from `data/Loi_coupole.xlsx`)

3. **Adaptive Decision** (`core/tracking/adaptive_tracking.py`):
   - `AdaptiveTrackingManager` analyzes current altitude/azimuth
   - Selects mode (NORMAL/CRITICAL/CONTINUOUS)
   - Adjusts interval, threshold, motor_delay accordingly

4. **Motor Control** (`core/hardware/moteur.py`):
   - Calculates steps needed (MUST use MICROSTEPS=4, not 16!)
   - Sends GPIO pulses to stepper driver (DM556T)
   - Uses `gear_ratio=2230` and `steps_correction_factor=1.08849`

5. **Position Feedback** (`core/hardware/moteur_feedback.py` + daemon):
   - Reads current angle from `/dev/shm/ems22_position.json`
   - Daemon (`ems22d_calibrated.py`) polls EMS22A encoder at 50Hz via SPI
   - Applies correction if error > tolerance (closed-loop control)

**Configuration Flow** (`data/config.json`):

```json
{
  "site": { "latitude": 44.15, "longitude": 5.23 },
  "moteur": {
    "microsteps": 4,  // CRITICAL: Must match driver configuration
    "gear_ratio": 2230,
    "steps_correction_factor": 1.08849
  },
  "adaptive_tracking": {
    "altitudes": { "critical": 68.0, "zenith": 75.0 },
    "modes": {
      "normal": { "interval_sec": 60, "motor_delay": 0.0011 },
      "critical": { "interval_sec": 15, "motor_delay": 0.00055 },
      "continuous": { "interval_sec": 5, "motor_delay": 0.00012 }
    }
  }
}
```

## Critical Implementation Details

### MICROSTEPS Configuration (EXTREMELY IMPORTANT)

**The `microsteps` value in `data/config.json` MUST match the driver (DM556T) configuration.**

- Driver: SW5-8 all ON = 200 pulses/revolution
- Code: `moteur.microsteps = 4` in config.json
- **If mismatched**: Dome will move 4× too far or too slow
- **Check with**: `grep microsteps data/config.json`
- **Expected**: `"microsteps": 4`

When modifying motor code:
```python
# In core/hardware/moteur.py, steps are calculated as:
steps_per_dome_revolution = (
    config.steps_per_revolution
    * config.microsteps
    * config.gear_ratio
    * config.steps_correction_factor
)
# = 200 * 4 * 2230 * 1.08849 ≈ 1,942,968 steps/360°
```

### Encoder Daemon Architecture

The system uses a daemon-based architecture where:

- **Daemon** (`ems22d_calibrated.py`): Independent process reading EMS22A encoder via SPI at 50Hz
- **Shared Memory**: Position published to `/dev/shm/ems22_position.json` (JSON in RAM)
- **Logs**: Written to `logs/ems22d.log` with automatic rotation (10 MB max, 3 backups)
- **Main Application**: Reads position from shared memory file (no direct SPI access)
- **Benefit**: Complete SPI/GPIO isolation prevents interference between encoder reads and motor pulses

**Monitoring daemon logs**:
```bash
# Real-time log monitoring
tail -f logs/ems22d.log

# Search for switch calibrations
grep "Microswitch activé" logs/ems22d.log

# Check startup configuration
grep "Switch GPIO" logs/ems22d.log
```

See `tests_sur_site/GUIDE_LOGS_DAEMON.md` for complete log monitoring guide.

**CRITICAL ARCHITECTURE** (corrected Dec 5, 2025):

The daemon MUST use **INCREMENTAL method** (accumulate changes), not absolute conversion:

```python
# CORRECT - Incremental method (like working direct SPI script)
def update_counts(self, raw):
    diff = raw - self.prev_raw
    if diff > 512: diff -= 1024
    elif diff < -512: diff += 1024
    self.total_counts += diff  # ACCUMULATION
    self.prev_raw = raw
    return self.total_counts

# Calculate angle from accumulated counts (NOT from raw directly)
def raw_to_calibrated(self, raw):
    counts = self.update_counts(raw)
    wheel_degrees = (counts / 1024) * 360.0
    ring_deg = wheel_degrees * CALIBRATION_FACTOR * ROTATION_SIGN
    return ring_deg % 360.0
```

**Why**: The raw encoder value (0-1023) gives the wheel position, but the wheel makes ~92 turns per dome rotation. Without accumulating changes, the daemon cannot track which "turn" we're on → completely wrong dome position.

**Calibration factor**:
```python
CALIBRATION_FACTOR = 0.01077 / 0.9925  # = 0.010851
```

When working with encoder code:
- Daemon runs independently with sudo (requires SPI access)
- `moteur_feedback.py` reads from `/dev/shm/ems22_position.json`
- Fallback: If daemon file missing, system continues in open-loop mode (no feedback)
- **CRITICAL Validation**: Daemon-based compass (`boussole.py`) must match direct SPI compass (`tests_sur_site/ems22a_ring_gauge4_V2.py`) within ±0.5° AND follow dome movements

### Adaptive Tracking Mode Selection Logic

The system automatically switches modes based on:

```python
# In core/tracking/adaptive_tracking.py
if altitude >= ALTITUDE_ZENITH or abs(predicted_movement) > MOVEMENT_EXTREME:
    mode = TrackingMode.CONTINUOUS  # 5s interval, 0.1° threshold
elif altitude >= ALTITUDE_CRITICAL:
    mode = TrackingMode.CRITICAL     # 15s interval, 0.25° threshold
else:
    mode = TrackingMode.NORMAL       # 60s interval, 0.5° threshold
```

**When adding new zones or modifying thresholds:**
- Update `data/config.json` → `adaptive_tracking.altitudes`
- Add entries to `critical_zones` array for specific sky regions
- Test with simulation first: `python tests/simulate_eltanin_adaptive.py`

### Abaque (Lookup Table) System

`data/Loi_coupole.xlsx` contains ~130 measured points:
- Columns: Altitude, Azimut, Position_Coupole
- `AbaqueManager` performs bilinear interpolation
- **Preferred over vectorielle** because it accounts for mechanical deformations

When updating abaque:
1. Add new measurements to Excel file
2. No code changes needed (reads dynamically)
3. Consider gaps: interpolation degrades if points too sparse
4. Check discontinuities in logs: "⚠️ Large correction jump detected"

## Common Development Tasks

### Adding a New Celestial Object to Catalog

Edit `core/observatoire/catalogue.py`:

```python
def get_objets_disponibles(self) -> List[Dict]:
    return [
        # ... existing objects ...
        {
            "nom": "M51",
            "type": "Galaxie",
            "coord": {
                "ra_h": 13, "ra_m": 29, "ra_s": 52.7,
                "dec_d": 47, "dec_m": 11, "dec_s": 43
            }
        }
    ]
```

### Adjusting Adaptive Mode Thresholds

1. Edit `data/config.json` → `adaptive_tracking.modes.<mode_name>`
2. Change `interval_sec`, `threshold_deg`, or `motor_delay`
3. Lower `motor_delay` = faster motor speed
4. Test with: `uv run main.py` and monitor mode transitions

### Debugging Motor Movement Issues

Check in order:
1. **Microstepping**: `grep microsteps data/config.json` (must be 4)
2. **Driver wiring**: DIR pin=17, STEP pin=18 (BCM numbering)
3. **Gear ratio**: `grep gear_ratio data/config.json` (should be ~2230)
4. **Logs**: Check `logs/` directory for GPIO errors or step miscalculations
5. **Field test logs**: Review `tests_sur_site/` for real-world behavior examples

Enable verbose logging:
```python
# In main.py, change:
setup_logging(log_level="DEBUG")  # Instead of "INFO"
```

### Debugging Feedback Loop Issues

If encoder feedback causes excessive iterations or wrong-direction movement:

1. **Check encoder daemon**: `cat /dev/shm/ems22_position.json` should update at 50Hz
2. **Monitor with visual gauge**: `python tests_sur_site/ems22a_ring_gauge4_V2.py`
3. **Check wrapping logic**: `core/hardware/moteur_feedback.py` handles 0°/360° transitions
4. **Disable feedback temporarily**: Set `"encodeur": {"enabled": false}` in config.json
5. **Review field test**: See `tests_sur_site/driftapp_20251203_173150.log` for known 0°/360° crossing issue

### Testing Without Hardware (Simulation Mode)

Set in `data/config.json`:
```json
{
  "simulation": true
}
```

This disables GPIO initialization but allows testing:
- UI flow
- Calculation methods
- Adaptive mode logic
- Abaque interpolation

## Calibration Switch Feature (Dec 2025)

The observatory has been upgraded with an automatic calibration system:

**Hardware**:
- SS-5GL microswitch mounted at 45° azimuth position
- Connected to GPIO 27 with internal pull-up
- Normally open (NO) - closes when dome passes calibration point

**Operation**:
- When dome passes 45° azimuth, switch closes (GPIO 27 goes LOW)
- Daemon detects falling edge (1→0 transition)
- Automatically recalibrates: `total_counts` adjusted so displayed angle = 45°
- Eliminates drift accumulation over long tracking sessions

**Daemon with switch support**: Use `ems22d_calibrated.py` (includes switch logic as of Dec 6, 2025)

**Important**:
- The daemon auto-detects switch state at startup to avoid false calibration triggers
- Logs show "Switch GPIO 27 configuré - état initial : X" at startup (X=0 if on switch, 1 if not)
- Expected log when switch activates: "🔄 Microswitch activé → recalage à 45°"

**Troubleshooting switch not working**:
```bash
# 1. Test GPIO 27 directly (daemon must be stopped first)
sudo pkill -f ems22d_calibrated
sudo python3 tests_sur_site/test_switch_direct.py
# Move dome to 45° - should show "Transition #001 : 1→0 | 🔴 PRESSÉ"

# 2. If no transition detected → Check wiring:
#    - GPIO 27 connected to switch signal
#    - GND common between switch and Pi
#    - Switch continuity with multimeter

# 3. If transition OK → Restart daemon and monitor logs:
# Terminal 1: Monitor logs
tail -f logs/ems22d.log

# Terminal 2: Start daemon
sudo python3 ems22d_calibrated.py

# Watch for "Switch GPIO 27 configuré" at startup in logs
# Move dome to 45° and watch for "🔄 Microswitch activé" message

# 4. Complete diagnostic:
#    See tests_sur_site/ANALYSE_SWITCH_NON_FONCTIONNEL.md
#    See tests_sur_site/GUIDE_LOGS_DAEMON.md for log monitoring details
```

---

## 🔴 PROBLÈME EN COURS : Saccades moteur (Décembre 2025)

### Symptôme

Le moteur fonctionne de manière **fluide** avec `calibration_moteur.py` mais présente des **saccades/claquements** réguliers (2-3 Hz) dans l'application DriftApp complète via `motor_service.py`.

- Le mouvement atteint la position cible correctement
- Mais le son est saccadé/brusque au lieu d'être fluide
- Paramètres identiques (motor_delay, microsteps) entre les deux contextes

### Analyse effectuée

#### Comparaison script calibration vs application

| Aspect | `calibration_moteur.py` (FLUIDE) | `motor_service.py` (SACCADÉ) |
|--------|----------------------------------|------------------------------|
| Boucle moteur | `for` pure sans interruption | Vérifications périodiques |
| Logging | Aucun pendant mouvement | FileHandler actif |
| I/O fichiers | Aucun pendant mouvement | Lecture/écriture IPC |
| Garbage Collector | Non contrôlé | Non contrôlé |
| Contexte | Script standalone | Service multi-thread |

#### Causes identifiées et corrigées

1. **Vérification `stop_requested` à chaque pas** → Corrigé : tous les 500 pas seulement
2. **Lecture daemon tous les 500 pas** dans `_verifier_arret_anticipe()` → Supprimé
3. **Overhead `faire_un_pas()`** avec appels de méthodes → Corrigé : code GPIO inline

#### Code optimisé actuel (`moteur.py`)

```python
def faire_un_pas(self, delai: float = 0.0015):
    """VERSION OPTIMISÉE INLINE (alignée sur Dome_v4)"""
    if self.gpio_handle is None:
        raise RuntimeError("GPIO non initialisé")

    # Validation inline
    delai_min = 0.00001  # 10µs
    if delai < delai_min:
        delai = delai_min

    # GPIO inline - PAS d'appels de méthodes
    if self.gpio_lib == "lgpio":
        import lgpio
        lgpio.gpio_write(self.gpio_handle, self.STEP, 1)
        time.sleep(delai / 2)
        lgpio.gpio_write(self.gpio_handle, self.STEP, 0)
        time.sleep(delai / 2)
    # ... (RPi.GPIO similaire)

def rotation(self, angle_deg: float, vitesse: float = 0.0015):
    # Boucle avec vérification stop_requested tous les 500 pas seulement
    for i in range(steps):
        if i % 500 == 0 and self.stop_requested:
            break
        self.faire_un_pas(vitesse)
```

#### Causes potentielles restantes (non confirmées)

1. **Garbage Collector Python** : Peut interrompre à tout moment pour libérer mémoire
2. **FileHandler logging** : Écritures disque synchrones dans `motor_service.py`
3. **Contexte Motor Service** : Boucle principale avec polling 50ms, threads

### Diagnostic à effectuer

Un script de diagnostic complet a été créé : `diagnostic_moteur_complet.py`

**Exécution** :
```bash
sudo python3 diagnostic_moteur_complet.py
```

**Ce que le diagnostic mesure** :
- **TEST A** : Timing de chaque impulsion en mode isolé (comme `calibration_moteur.py`)
- **TEST B** : Comportement via Motor Service (contexte production)

**Métriques clés** :
- **Outliers** : % de pas avec délai > 2× la moyenne
- **Max delay** : Délai max observé (si > 5× moyenne = interruption significative)
- **Overhead** : Temps total vs temps attendu

**Interprétation** :

| Résultat Test A | Résultat Test B | Conclusion |
|-----------------|-----------------|------------|
| ✅ Peu d'outliers | ✅ Peu d'outliers | Problème ailleurs (FeedbackController ?) |
| ✅ Peu d'outliers | ❌ Beaucoup d'outliers | Contexte Motor Service cause les saccades |
| ❌ Beaucoup d'outliers | ❌ Beaucoup d'outliers | Problème dans `rotation()` ou hardware |

### Pistes de résolution (à tester selon résultats diagnostic)

#### Si problème dans Motor Service (Test A OK, Test B KO)

1. **Désactiver FileHandler logging** (`motor_service.py` lignes 91-101) :
```python
logging.basicConfig(
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        # logging.FileHandler(...)  # COMMENTER
    ]
)
```

2. **Désactiver GC pendant mouvement** (`moteur.py`) :
```python
import gc
gc.disable()
try:
    for i in range(steps):
        self.faire_un_pas(vitesse)
finally:
    gc.enable()
```

#### Si problème dans boucle moteur (Test A KO)

1. **Vérifier processus concurrents** sur le Pi
2. **Vérifier alimentation** du driver DM556T
3. **Comparer avec `calibration_moteur.py`** directement

#### Si problème dans FeedbackController

Les pauses dans `read_stable()` (`moteur.py`) :
```python
def read_stable(self, num_samples=3, delay_ms=10, stabilization_ms=50):
    time.sleep(stabilization_ms / 1000.0)  # 50ms pause !
    for _ in range(num_samples):
        pos = self.read_angle()
        time.sleep(delay_ms / 1000.0)  # 10ms × 3
```

**Impact** : ~80ms de pause entre chaque itération de feedback

**Solution potentielle** : Réduire `stabilization_ms` à 20ms et `delay_ms` à 5ms

### Architecture multi-processus (rappel)

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Daemon EMS22A  │     │  Motor Service  │     │  Django Web     │
│  (processus 1)  │     │  (processus 2)  │     │  (processus 3)  │
│                 │     │                 │     │                 │
│  GIL isolé      │────▶│  GIL isolé      │◀────│  GIL isolé      │
│  SPI @ 50Hz     │ JSON│  GPIO moteur    │ IPC │  Interface      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

**Point clé** : Chaque processus a son propre GIL Python, donc les threads Django n'impactent PAS le Motor Service. Le problème est **interne** au Motor Service.

### Fichiers de diagnostic disponibles

- `diagnostic_moteur_complet.py` : Script de test complet (à placer à la racine)
- `README_DIAGNOSTIC.md` : Instructions pour l'utilisateur sur site

---

## Known Issues and Limitations

1. **Very fast objects**: Moon, ISS not supported (significant proper motion)
2. **Near zenith** (>85° altitude): Limited testing, may have discontinuities
3. **Abaque gaps**: Interpolation quality depends on measurement density
4. **Encoder daemon crash**: System continues in open-loop (no feedback)
5. **CRITICAL BUG RESOLVED (Dec 5, 2025)**: Encoder daemon used ABSOLUTE calculation method instead of INCREMENTAL. This caused:
   - Daemon unable to track dome movements (stuck at 356-359° while dome moved 45°→55°)
   - Compass based on daemon showing completely wrong position
   - Anti-jump filter (5° threshold) blocking all real movements
   - Feedback loop failing with continuous movements
   - **ROOT CAUSE**: Daemon converted raw encoder value (0-1023) directly to angle without accumulating changes
   - **FIXED** in `ems22d_calibrated.py`: Added incremental method like the working direct SPI script
   - **ALSO FIXED**: Increased anti-jump threshold from 5° to 30° (lines 69-71, 110-138, 231-233)
   - See `tests_sur_site/ANALYSE_BUG_DAEMON_METHODE_CALCUL.md` for complete analysis

6. **CRITICAL BUG RESOLVED (Dec 6, 2025)**: Compass GUI (`boussole.py`) frozen despite daemon working perfectly. This caused:
   - Needle stuck/frozen even though JSON data from daemon was correct
   - Visual validation tool unusable
   - **ROOT CAUSE**: `FuncAnimation` created BEFORE canvas integrated into Tkinter → animation running "phantom" without display refresh
   - **FIXED** in `boussole.py` lines 130-147: Moved `FuncAnimation` creation AFTER `FigureCanvasTkAgg` and `.pack()`
   - **CRITICAL ORDER**: Canvas → Pack → Animation → Mainloop (same as working direct compass)
   - See `tests_sur_site/ANALYSE_BUG_BOUSSOLE_DAEMON.md` for complete analysis

7. **EN COURS (Dec 2025)** : Saccades moteur via Motor Service alors que `calibration_moteur.py` fonctionne parfaitement. Voir section "PROBLÈME EN COURS : Saccades moteur" ci-dessus.

## Hardware Context

- **Raspberry Pi**: 4 or 5 (auto-detected)
- **Stepper Driver**: DM556T (Leadshine) configured for 200 pulse/rev
- **Encoder**: EMS22A magnetic, 10-bit (1024 counts/rev), SPI bus 0 device 0
- **Gear Ratio**: 2230:1 (50mm encoder wheel on 2303mm dome ring)
- **Calibration Switch** (Dec 2025): SS-5GL microswitch on GPIO 27, triggers at 45° azimuth for auto-calibration
- **Location**: Southern France (44.15°N, 5.23°E, 800m altitude)

## Important Performance Metrics

- **Tracking precision** with closed-loop feedback: ±0.3-0.5° (vs ±2-5° open-loop)
- **Encoder daemon frequency**: 50Hz constant reading
- **Adaptive system**: 85% reduction in motor time for critical sky zones
- **SPI isolation**: Zero interference between encoder and motor control

### Field Test Results (Dec 3, 2025)

**Open-loop test** (M13, 16:34):
- Duration: 17 minutes
- Corrections: 3
- Mode: NORMAL
- Result: Successful tracking

**Closed-loop test BEFORE FIX** (M15, 17:31):
- Duration: 6+ minutes
- Encoder: Active at 358.7°
- Issue: Multiple iterations (up to 6) when crossing 0°/360° boundary
- Symptom: Wrong direction correction (moved to 357.5° when target was 1.3° from 360.0°)
- **Root cause**: CALIBRATION_FACTOR ×2.89 too large → feedback saw 41° error instead of 1.3°

**Visual proof** (Dec 5, 2025):
- Video comparison shows daemon-based compass displaying ×2.89 incorrect values
- Direct SPI compass working perfectly
- See `tests_sur_site/WhatsApp Video 2025-12-05 at 12.19.31.mp4`

## References to Original Documentation

For detailed installation and troubleshooting:
- `CONTEXT.md`: Complete project context
- `README_v4_3.md`: Daemon architecture details
- `README.md`: Architecture overview
- `GUIDE_MIGRATION_DAEMON.md`: Daemon migration guide
- `TRACKING_LOGIC.md`: Complete tracking logic documentation
