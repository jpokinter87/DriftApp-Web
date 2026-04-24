# CLAUDE.md

Guide pour Claude Code (claude.ai/code) sur le projet DriftApp Web.

## Apercu du Projet

**DriftApp Web** est un systeme de controle de coupole astronomique pour l'Observatoire Ubik (France). Architecture trois processus avec interface web Django.

**Materiel**: Raspberry Pi 4/5, moteur pas-a-pas NEMA (200 pas/rev), driver DM556T (4 microsteps), encodeur magnetique EMS22A (10-bit), reduction 2230:1.

**Version actuelle**: 5.11.0 (Avril 2026)

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
uv run pytest -v                                    # Tous les tests (820+)
uv run pytest tests/test_moteur.py -v              # Tests moteur GPIO
uv run pytest tests/test_moteur_rp2040.py -v       # Tests moteur RP2040
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

**Pilotage moteur** (configurable dans `data/config.json` → `motor_driver.type`):
- `"gpio"` (defaut): Motor Service pilote directement via GPIO (lgpio/RPi.GPIO)
- `"rp2040"`: Motor Service envoie des commandes serie au Pi Pico (RP2040) via USB CDC

```
Mode GPIO:    Motor Service ──► GPIO ──► DM556T
Mode RP2040:  Motor Service ──► USB serie ──► Pi Pico (PIO 8ns) ──► DM556T
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
│   ├── config.py               # Constantes, get_motor_config(), get_site_config()
│   └── config_loader.py        # ConfigLoader, dataclasses (DriftAppConfig, MotorDriverConfig...)
│
├── hardware/
│   ├── moteur.py               # MoteurCoupole (GPIO lgpio/RPi.GPIO)
│   ├── moteur_rp2040.py        # MoteurRP2040 (serie USB vers Pi Pico) — v5.3
│   ├── serial_simulator.py     # Simulateur serie pour dev sans Pico — v5.3
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
│   ├── tracking_corrections_mixin.py # Corrections periodiques (vitesse unique v5.10)
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

### firmware/ - Firmware RP2040 (v5.3)

```
firmware/
├── main.py              # Boucle serie MOVE/STOP/STATUS via USB CDC
├── step_generator.py    # Programme PIO assembleur + classe StepGenerator
├── ramp.py              # Rampe S-curve portee depuis acceleration_ramp.py
└── README.md            # Guide flash MicroPython + branchements
```

---

## Vitesse Unique (v5.10)

| Paramètre | Valeur | Constante |
|-----------|--------|-----------|
| Délai moteur | 260 µs/pas (~40°/min) | `SINGLE_SPEED_MOTOR_DELAY` |
| Intervalle correction | 30 s | `SINGLE_SPEED_CHECK_INTERVAL_S` |
| Seuil correction | 0.3° | `SINGLE_SPEED_CORRECTION_THRESHOLD_DEG` |

Définies dans `core/config/config.py`. Retour terrain v5.7.0 (23/04/2026) :
la vitesse max convient pour tout → suppression des 3 modes adaptatifs
(NORMAL/CRITICAL/CONTINUOUS) + flag `force_continuous_tracking` (v5.7) +
rattrapage méridien (`_meridian_catchup_active`, v5.6.5) + gel méridien
GEM (`gem_delay_minutes`, v5.6.2).

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

### Pilotage RP2040 (v5.3)
```python
# MoteurRP2040 a la meme interface que MoteurCoupole
from core.hardware.moteur_rp2040 import MoteurRP2040
from core.hardware.serial_simulator import SerialSimulator

# En dev (simulation) :
moteur = MoteurRP2040(config_moteur, SerialSimulator())

# En production (Pi Pico branche) :
import serial
moteur = MoteurRP2040(config_moteur, serial.Serial("/dev/ttyACM0", 115200))

# Memes methodes que MoteurCoupole :
moteur.rotation(45.0, vitesse=0.002, use_ramp=True)  # → MOVE serie
moteur.request_stop()                                  # → STOP serie
```

---

## Fichiers de Configuration

| Fichier | Description |
|---------|-------------|
| `data/config.json` | Config centralisee (site, moteur, motor_driver, GPIO, seuils, modes) |
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

### Vitesse Unique (v5.10)
```python
from core.config.config import (
    SINGLE_SPEED_MOTOR_DELAY,           # 0.00026 s/pas
    SINGLE_SPEED_CHECK_INTERVAL_S,      # 30 s
    SINGLE_SPEED_CORRECTION_THRESHOLD_DEG,  # 0.3°
)
# Plus de mode adaptatif : toutes les corrections utilisent ces constantes.
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
# Tous les tests (820+)
uv run pytest -v

# Tests rapides (sans astropy)
uv run pytest tests/test_angle_utils.py tests/test_config.py tests/test_moteur.py \
    tests/test_moteur_rp2040.py tests/test_config_loader.py \
    tests/test_feedback_controller.py tests/test_ipc_manager.py tests/test_simulation.py \
    tests/test_acceleration_ramp.py -v

# Tests RP2040 (unitaires + integration)
uv run pytest tests/test_moteur_rp2040.py tests/test_integration_rp2040.py -v

# Tests avec astropy
uv run pytest tests/test_calculations.py tests/test_command_handlers.py -v

# Test specifique
uv run pytest tests/test_moteur.py::TestMoteurCoupoleControl -v
```

**Notes**:
- Mocks GPIO/hardware (fonctionne sans Raspberry Pi)
- SerialSimulator pour tests RP2040 sans Pi Pico physique
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

### Changer de driver moteur (GPIO ↔ RP2040)
```json
// data/config.json → section motor_driver
{ "motor_driver": { "type": "rp2040" } }   // Pi Pico
{ "motor_driver": { "type": "gpio" } }      // GPIO direct (defaut)
```
Voir [RP2040_UPGRADE.md](RP2040_UPGRADE.md) pour le guide complet de migration.

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

### Qualite de Code
| Skill | Description |
|-------|-------------|
| `/code-review` | Review complete + refactoring (SOLID, DRY, Clean Code) |
| `/refactor-code` | Refactoring de code assiste |

---

## Changelog Resume

| Version | Date | Changements |
|---------|------|-------------|
| **5.11** | Avril 2026 | v5.9 Phase 2 : intégration runtime anticipation méridien (flag opt-in + force_direction moteur + mixin + hook `check_and_correct`). Rétro-compat stricte (flag default false = v5.10 identique). Validation terrain à suivre |
| **5.10** | Avril 2026 | Vitesse unique 260 µs : suppression mode adaptatif, gel méridien GEM, flag force_continuous, rattrapage meridian_catchup |
| **5.9** | Avril 2026 | Prédiction méridien Phase 1 (module pur `meridian_anticipation.py`) |
| **5.8** | Avril 2026 | Refactor mise à jour UI (script 5 étapes, sudoers whitelist) |
| **5.7** | Avril 2026 | Flag `force_continuous_tracking` (bypass adaptatif, validé terrain) — retiré en v5.10 |
| **5.6** | Avril 2026 | Fiabilité méridien (anti-saut abaque, correction angle horaire précession) + polish UI |
| **5.5** | Avril 2026 | Correctifs encodeur FROZEN + fallback sans feedback sécurisé |
| **5.4** | Mars 2026 | — |
| **5.3** | Mars 2026 | Pilotage RP2040 : firmware PIO, MoteurRP2040 serie, fallback GPIO/RP2040, guide terrain |
| **5.2** | Mars 2026 | Watchdog thread meridien, logging structure cle=valeur, tests terrain |
| **5.1** | Mars 2026 | Sync production, audit code, refactoring, 746 tests |
| **5.0** | Fev 2026 | Interface moderne Tailwind + Alpine.js |
| **4.6** | Dec 2025 | DaemonEncoderReader extrait, warm-up phase, support Pi 5 |
| **4.5** | Dec 2025 | Rampe S-curve acceleration/deceleration |
| **4.4** | Dec 2025 | GOTO fluide (direct + correction finale), suppression FAST_TRACK |
| **4.3** | Dec 2025 | Architecture 3 processus IPC |

---

## Versionnement

La version est definie dans `pyproject.toml` (champ `version`) et affichee dynamiquement dans le footer de l'interface web via le context processor Django `driftapp_web.context_processors.app_version`.

**Regle** : Mettre a jour la version dans `pyproject.toml` a **chaque commit pousse**, meme mineur :
- Milestone complet : incrementer le mineur (ex: 5.5.0 → 5.6.0)
- Correction/fix/amelioration : incrementer le patch (ex: 5.6.0 → 5.6.1 → 5.6.2...)

Le systeme de mise a jour OTA compare les versions pour proposer les updates.
Sans bump de version, la mise a jour n'est pas proposee a l'utilisateur.
