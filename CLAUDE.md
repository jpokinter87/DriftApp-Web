# CLAUDE.md

Guide pour Claude Code (claude.ai/code) sur le projet DriftApp Web.

## Apercu du Projet

**DriftApp Web** est un systeme de controle de coupole astronomique pour l'Observatoire Ubik (France). Architecture trois processus avec interface web Django.

**Materiel**: Raspberry Pi 4/5, moteur pas-a-pas NEMA (200 pas/rev), driver DM860T 36 V (4 microsteps), encodeur magnetique EMS22A (10-bit), reduction 2230:1.

**Version actuelle**: 6.26.1 (Octobre 2026)

---

## Commandes de Developpement

```bash
# Installation
uv sync

# Demarrage complet (Raspberry Pi)
sudo ./start_web.sh

# Démarrage dev complet (recommandé) — 4 processus en parallèle :
#   - cimier_simulator.py  (simulateur Shelly unifié V3 — Uni+ RPC + relais 24V/MOT/UPDN)
#   - motor_service.py     (mode SIMULATION auto-détecté)
#   - cimier_service.py    (skip silencieux si cimier.enabled=false dans config.json)
#   - Django runserver     (port 0.0.0.0:8000 par défaut, configurable)
./start_dev.sh start            # Port Django par défaut 8000
./start_dev.sh start 8080       # Port Django alternatif (utile si 8000 occupé)
DJANGO_PORT=8080 ./start_dev.sh start   # Équivalent via env var
./start_dev.sh status           # État des 4 processus + URL Django
./start_dev.sh stop             # Arrêt propre

# Démarrage Django seul (debug minimal — tracking ET cimier inactifs)
cd web && uv run python manage.py runserver 0.0.0.0:8000

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
Mode GPIO:    Motor Service ──► GPIO ──► DM860T
Mode RP2040:  Motor Service ──► USB serie ──► Pi Pico (PIO 8ns) ──► DM860T
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
├── asiair_monitor.py     # Journal permanent de l'ASIAIR (service asiair_monitor, v6.25)
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

**Note V3** : `firmware/cimier/` supprimé (pivot tout-Shelly v6.7). Le cimier n'utilise plus de Pico W — Contrôleur autonome STEP+DM556T piloté par 4 Shellys (24V/Uni+/MOT/UPDN). Voir section « Architecture cimier V3 » ci-dessous.

---

## Architecture cimier V3 (tout-Shelly, v6.7)

Suppression totale du Pico W. Le cimier est désormais piloté par 4 Shellys Gen 1 :

| Shelly | IP terrain | Rôle |
|--------|-----------|------|
| SHELLY-1-24V | 192.168.1.83 | Alimentation module cimier (power_switch) |
| SHELLY-UNI+  | 192.168.1.84 | Lecture microswitches HAUT/BAS (switch_reader) |
| SHELLY-1-MOT | 192.168.1.85 | ON/OFF moteur cimier (motor_shelly.host_motor) |
| SHELLY-1-UPDN| 192.168.1.86 | Sens moteur via DPDT externe (motor_shelly.host_dir) |

**Cinématique** : `cimier_service` → Shelly 24V (alim ON) → Shelly MOT (moteur ON) + Shelly UPDN (sens) → Shelly Uni+ (poll microswitches) → Shelly MOT OFF → Shelly 24V OFF.

**Lecture butées** : `core/hardware/shelly_switch_reader.py` (`ShellySwitchReader`) via API RPC `Input.GetStatus`. Config `switch_reader` dans `data/config.json` (`type="shelly_uni"` en prod, `"noop"` dans le template repo).

**Simulateur dev** : `core/hardware/cimier_simulator.py` — émule les 4 Shellys (Uni+ RPC + 3 relais legacy). Activé via `CIMIER_DEV_MODE=1` (exporté par `start_dev.sh`).

**Conventions validées terrain (17-18/06, figées dans `data/config.json`)** : `motor_on_relay_state=false` (le moteur tourne quand le relais MOT est sur `turn=off`), `open_dir_state=true`, `switch_reader.invert=true` (section `motor_shelly` / `switch_reader`).

---

## Vitesse Unique (v5.10)

| Paramètre | Valeur | Constante |
|-----------|--------|-----------|
| Délai moteur | 260 µs/pas (~40°/min) | `SINGLE_SPEED_MOTOR_DELAY` |
| Intervalle correction | 30 s | `SINGLE_SPEED_CHECK_INTERVAL_S` |
| Seuil correction | 0.3° | `SINGLE_SPEED_CORRECTION_THRESHOLD_DEG` |
| Délai grands déplacements (≥ 3°, v6.18) | `motor_driver.fast_delay_us` | `FAST_MOTOR_DELAY`, `motor_delay_for()` |

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

### Tracking ne démarre pas en dev
**Symptôme** : clic « Démarrer le suivi » → bouton STOPPER s'allume brièvement, le cartouche
vert « Suivi Actif » n'apparaît jamais. La timeline cimier peut afficher
`WARNING Service silencieux — cascade ouverture bypassée`.

**Cause** : `motor_service.py` ne tourne pas → `motor_status.json` figé en `idle` →
les commandes écrites dans `motor_command.json` ne sont jamais consommées.

**Fix** :
```bash
./start_dev.sh stop && ./start_dev.sh start
./start_dev.sh status   # Vérifier les 4 processus EN COURS
```
Puis recharger le dashboard (Ctrl+F5).

### Indicateurs cimier vides en dev (UNKNOWN / --)
**Symptôme** : cartouche « CIMIER : INCONNU » sous la boussole + cartouche bas
« ÉTAT : UNKNOWN | PHASE : -- » + activité cimier vide. Le mode auto et le
countdown ouverture/fermeture s'affichent (alimentés par fallback Django).

**Cause** : avant v6.3.2, `cimier_service` skip silencieusement quand
`cimier.enabled=false` dans `data/config.json` (template repo).

**Fix v6.3.2 / V3** : `start_dev.sh` exporte `CIMIER_DEV_MODE=1` automatiquement →
`cimier_service` patche en mémoire enabled=True et pointe le simulateur Shelly unifié
`core.hardware.cimier_simulator` (Uni+ RPC + relais 24V/MOT/UPDN). `data/config.json`
reste intact (template repo respecté pour la prod). Si l'UI reste vide après
`./start_dev.sh restart`, vérifier `cat /dev/shm/cimier_status.json` (présent + state
non-null) et `logs/cimier/cimier_service.log`.

### Simuler une averse en dev

Le simulateur cimier expose une entrée pluie basculable à la main — inutile
d'attendre un orage pour exercer toute la chaîne :

```bash
./start_dev.sh start
curl "http://127.0.0.1:8001/dev/rain?on=1"   # il pleut
curl "http://127.0.0.1:8001/dev/rain?on=0"   # retour au sec
```

En dev le capteur est sur l'entrée `id=2` du Shelly simulé et la veille tourne
toutes les 2 s (`_apply_dev_mode_overrides`) ; en prod c'est l'entrée `id=0`
d'un Shelly dédié (.87) à la cadence `watch_interval_s`. Ce qu'on observe :

```bash
python3 -c "import json;print(json.load(open('/dev/shm/cimier_status.json'))['rain'])"
grep -E "rain_read|rain_transition|rain_emergency" logs/cimier/cimier_service.log
tail data/nights/$(date +%Y-%m-%d).jsonl     # journal de nuit (dé-tracké)
```

La protection doit être **armée** (case « Protection pluie » du dashboard, ou
`POST /api/cimier/automation/ {"rain_protection": true}`) pour que la pluie
commande une fermeture ; désarmée, elle est seulement lue et journalisée.

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

## Migrations terrain ponctuelles

Les procédures one-shot (saut 5.10 → 6.4, dé-tracking de `config.json` en 6.9) sont dans
[docs/deploiement_migrations_terrain.md](docs/deploiement_migrations_terrain.md).
Rappel durable : **ne jamais `git stash`** autour de `data/config.json` sur le Pi, et ne jamais
committer `data/config.template.json` depuis le Pi.

---

## Skills Claude Disponibles

| Skill | Description |
|-------|-------------|
| `/diag-terrain` | Protocole de diagnostic à transmettre à Serge pour un incident terrain, puis interprétation de ses retours |
| `/analyse-nuit` | Relire une nuit terrain : zip de Serge rangé dans `logs/terrain/`, chronologie fusionnée (`scripts/diagnostics/chronologie_nuit.py`), tri logiciel/terrain/monture, compte rendu WhatsApp |
| `/pre-push` | Hygiène avant push : tests ciblés, ruff, valeurs en dur, bump, commit + push |

Les anciennes commandes projet (`/diagnose`, `/logs`, `/calibrate`, `/deploy`…) ont été
retirées en 6.21.13 : écrites en janvier 2026, elles décrivaient des modes supprimés en
v5.10. La revue de code passe par la commande intégrée `/code-review`.

---

## Changelog

Historique complet dans [CHANGELOG.md](CHANGELOG.md) (tableau par version, plus récente en haut).
À chaque version poussée, **ajouter la ligne en tête du tableau de `CHANGELOG.md`** (pas ici).

---

## Versionnement

La version est definie dans `pyproject.toml` (champ `version`) et affichee dynamiquement dans le footer de l'interface web via le context processor Django `driftapp_web.context_processors.app_version`.

**Regle** : Mettre a jour la version dans `pyproject.toml` a **chaque commit pousse**, meme mineur :
- Milestone complet : incrementer le mineur (ex: 5.5.0 → 5.6.0)
- Correction/fix/amelioration : incrementer le patch (ex: 5.6.0 → 5.6.1 → 5.6.2...)

Le systeme de mise a jour OTA compare les versions pour proposer les updates.
Sans bump de version, la mise a jour n'est pas proposee a l'utilisateur.
