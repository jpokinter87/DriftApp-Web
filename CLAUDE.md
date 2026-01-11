# CLAUDE.md

Guide pour Claude Code (claude.ai/code) sur le projet DriftApp Web.

## Apercu du Projet

**DriftApp Web** est un systeme de controle de coupole astronomique pour l'Observatoire Ubik (France). Architecture trois processus avec interface web Django.

**Materiel**: Raspberry Pi 4/5, moteur pas-a-pas NEMA (200 pas/rev), driver DM556T (4 microsteps), encodeur magnetique EMS22A (10-bit), reduction 2230:1.

**Version actuelle**: 4.6 (Janvier 2025)

---

## Commandes de Developpement

```bash
# Installation
uv sync

# Demarrage complet (Raspberry Pi)
sudo ./start_web.sh

# Mode developpement (simulation auto-detectee)
cd web && python manage.py runserver 0.0.0.0:8000

# Tests
uv run pytest -v                                    # Tous les tests (315+)
uv run pytest tests/test_moteur.py -v              # Tests moteur
uv run pytest tests/ -k "not astropy" -v           # Sans astropy

# Diagnostics manuels (Raspberry Pi)
sudo python3 scripts/diagnostics/diagnostic_moteur_complet.py
```

---

## Architecture Trois Processus (IPC)

```
Django (port 8000) ──► /dev/shm/motor_command.json ──► Motor Service
       ▲                                                    │
       │              ◄── /dev/shm/motor_status.json ◄──────┘
       │                                                    │
       └──────────────── /dev/shm/ems22_position.json ◄─────┘
                                  ▲
                         Encoder Daemon (ems22d_calibrated.py)
```

**Fichiers IPC**:
- `motor_command.json`: Commandes Django → Motor (GOTO, JOG, TRACKING)
- `motor_status.json`: Etat Motor → Django (position, mode, logs)
- `ems22_position.json`: Position encodeur temps reel (50 Hz)

---

## Structure du Code

### core/ - Logique Metier

```
core/
├── config/
│   └── config.py               # Constantes, get_motor_config(), get_site_config()
│
├── hardware/
│   ├── moteur.py               # MoteurCoupole (GPIO lgpio/RPi.GPIO)
│   ├── acceleration_ramp.py    # Rampe S-curve + warm-up (10 pas @ 10ms)
│   ├── daemon_encoder_reader.py # Lecteur encodeur IPC (v4.6)
│   ├── feedback_controller.py  # Boucle fermee iterative
│   ├── motor_config_parser.py  # Parser config dict → dataclass
│   ├── hardware_detector.py    # Detection auto Pi 4/5
│   └── moteur_simule.py        # Simulation realiste
│
├── tracking/
│   ├── tracker.py              # TrackingSession (classe principale)
│   ├── tracking_state_mixin.py # Etat & statistiques
│   ├── tracking_goto_mixin.py  # GOTO initial & sync
│   ├── tracking_corrections_mixin.py # Corrections periodiques
│   ├── adaptive_tracking.py    # 3 modes adaptatifs
│   └── abaque_manager.py       # Interpolation 2D (Loi_coupole.xlsx)
│
├── observatoire/
│   ├── calculations.py         # Conversions J2000→JNow, coords horizontales
│   ├── ephemerides.py          # Positions planetes (astropy)
│   └── catalogue.py            # Recherche objets celestes
│
└── utils/
    └── angle_utils.py          # normalize_360(), shortest_angular_distance()
```

### services/ - Motor Service

```
services/
├── motor_service.py      # Service principal, boucle 20 Hz, watchdog systemd
├── command_handlers.py   # 4 handlers: GOTO, JOG, Continuous, Tracking
├── ipc_manager.py        # Lecture/ecriture JSON avec verrous fcntl
└── simulation.py         # SimulatedDaemonReader pour dev
```

### web/ - Interface Django

```
web/
├── driftapp_web/         # Config Django (settings.py, urls.py)
├── hardware/             # API: /api/hardware/{goto,jog,stop,continuous,encoder,status}
├── tracking/             # API: /api/tracking/{start,stop,status,objects,search}
├── health/               # API: /api/health/{diagnostic,system,update/check,update/apply}
├── session/              # API: /api/session/{current,history,save,delete}
├── common/               # MotorServiceClient (singleton IPC)
├── templates/            # 3 pages HTML (dashboard, system, session)
└── static/               # CSS, JS (boussole canvas, Chart.js)
```

---

## Modes Adaptatifs

| Mode | Declencheur | Delai Moteur | Intervalle | Usage |
|------|-------------|--------------|------------|-------|
| NORMAL | altitude < 68° | 2.0 ms | 60s | Suivi standard |
| CRITICAL | 68° ≤ alt < 75° | 1.0 ms | 15s | Proche zenith |
| CONTINUOUS | alt ≥ 75° ou Δ > 30° | 0.15 ms | 5s | Zenith + GOTO |

---

## Optimisations Cles

### GOTO (v4.4)
- **Grands mouvements (> 3°)**: Rotation directe fluide + correction finale feedback
- **Petits mouvements (≤ 3°)**: Boucle feedback pour precision
- **JOG (boutons)**: Toujours rotation directe (fluidite maximale)

### Rampe d'Acceleration (v4.5)
```python
# Activation: moteur.rotation(angle, use_ramp=True)  # defaut
# Phases: warm-up (10 pas) → acceleration (500 pas) → croisiere → deceleration (500 pas)
# Courbe: Sigmoide (pas lineaire) pour fluidite
```

### DaemonEncoderReader (v4.6)
```python
from core.hardware.daemon_encoder_reader import get_daemon_reader
reader = get_daemon_reader()  # Singleton global
angle = reader.read_angle()   # Lecture avec timeout
```

---

## Fichiers de Configuration

| Fichier | Description |
|---------|-------------|
| `data/config.json` | Config centralisee (site, moteur, GPIO, seuils, modes) |
| `data/Loi_coupole.xlsx` | Abaque 275 points mesures (interpolation 2D) |
| `ems22d.service` | Service systemd encodeur |
| `motor_service.service` | Service systemd moteur (watchdog 30s) |

---

## Patterns de Design

### Mixins (Composition)
```python
class TrackingSession(TrackingStateMixin, TrackingGotoMixin, TrackingCorrectionsMixin):
    # Separe responsabilites: etat, GOTO, corrections
```

### Singleton Lazy (Daemon Reader)
```python
_daemon_reader = None
def get_daemon_reader():
    global _daemon_reader
    if _daemon_reader is None:
        _daemon_reader = DaemonEncoderReader()
    return _daemon_reader
```

### Strategy Pattern (Tracking Adaptatif)
```python
params = adaptive_manager.evaluate_tracking_zone(altitude, azimut, delta)
# Retourne TrackingParameters avec mode, delay, seuil
```

---

## Pages Web

| Page | URL | Fonctionnalites |
|------|-----|-----------------|
| **Dashboard** | `/` | Boussole interactive, controles, logs temps reel, modal GOTO |
| **Systeme** | `/api/health/system/` | Etat IPC, config, composants (refresh 2s) |
| **Session** | `/session/` | Graphiques altitude/azimut, stats, historique |

---

## Tests

```bash
# Tests rapides (sans astropy)
uv run pytest tests/test_angle_utils.py tests/test_config.py tests/test_moteur.py \
    tests/test_feedback_controller.py tests/test_ipc_manager.py tests/test_simulation.py \
    tests/test_acceleration_ramp.py -v

# Tests avec astropy
uv run pytest tests/test_calculations.py tests/test_command_handlers.py -v

# Test specifique
uv run pytest tests/test_moteur.py::TestMoteurCoupoleControl -v
```

**Notes**:
- Mocks GPIO/hardware (fonctionne sans Raspberry Pi)
- Scripts diagnostics dans `scripts/diagnostics/` (non collectes par pytest)

---

## Debugging Courant

### Encodeur indisponible
```bash
cat /dev/shm/ems22_position.json  # Verifier fichier
sudo systemctl status ems22d      # Verifier service
```

### Motor Service ne repond pas
```bash
cat /dev/shm/motor_status.json    # Verifier status
sudo journalctl -u motor_service -f  # Logs temps reel
```

### Mode simulation force
```json
// data/config.json
{ "simulation": true }
```

---

## Skills Claude Disponibles

### Diagnostic et Debug
| Skill | Description |
|-------|-------------|
| `/diagnose` | Diagnostic complet systeme (IPC, services, logs) |
| `/test-motor` | Tests moteur, feedback, rampe, precision |
| `/tracking-debug` | Debug suivi astronomique (calculs, abaque, modes) |
| `/logs` | Analyse des logs (patterns, erreurs, anomalies) |

### Operations
| Skill | Description |
|-------|-------------|
| `/calibrate` | Calibration encodeur via microswitch 45° |
| `/config` | Validation et modification de configuration |
| `/catalogue` | Recherche objets celestes, visibilite |
| `/session-report` | Rapport detaille de session de suivi |

### Maintenance
| Skill | Description |
|-------|-------------|
| `/deploy` | Deploiement complet sur Raspberry Pi |
| `/update` | Mise a jour du systeme (git pull + restart) |
| `/backup` | Sauvegarde/restauration config et sessions |
| `/refactor-code` | Refactoring de code assiste |

---

## Changelog Resume

| Version | Date | Changements |
|---------|------|-------------|
| **4.6** | Dec 2025 | DaemonEncoderReader extrait, warm-up phase, support Pi 5 |
| **4.5** | Dec 2025 | Rampe S-curve acceleration/deceleration |
| **4.4** | Dec 2025 | GOTO fluide (direct + correction finale), suppression FAST_TRACK |
| **4.3** | Dec 2025 | Architecture 3 processus IPC |
