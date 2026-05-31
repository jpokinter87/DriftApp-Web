# CLAUDE.md

Guide pour Claude Code (claude.ai/code) sur le projet DriftApp Web.

## Apercu du Projet

**DriftApp Web** est un systeme de controle de coupole astronomique pour l'Observatoire Ubik (France). Architecture trois processus avec interface web Django.

**Materiel**: Raspberry Pi 4/5, moteur pas-a-pas NEMA (200 pas/rev), driver DM556T (4 microsteps), encodeur magnetique EMS22A (10-bit), reduction 2230:1.

**Version actuelle**: 6.4.0 (Mai 2026)

---

## Commandes de Developpement

```bash
# Installation
uv sync

# Demarrage complet (Raspberry Pi)
sudo ./start_web.sh

# Démarrage dev complet (recommandé) — 4 processus en parallèle :
#   - cimier_simulator.py  (Pico W simulé, port localhost:8001)
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

**Fix v6.3.2** : `start_dev.sh` exporte `CIMIER_DEV_MODE=1` automatiquement →
`cimier_service` patche en mémoire enabled=True + host=127.0.0.1:8001
(simulateur) + power_switch=noop. `data/config.json` reste intact (template
repo respecté pour la prod). Si l'UI reste vide après `./start_dev.sh restart`,
vérifier `cat /dev/shm/cimier_status.json` (présent + state non-null) et
`logs/cimier_service.log` (ligne `cimier_dev_mode=on host=127.0.0.1:8001`).

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

## Déploiement v6.4 sur le Pi terrain (Calibration robuste)

**Contexte** : la prod tourne sur **5.10.0** (déployé 2026-04-24). Le saut vers **6.4.0** traverse 8 milestones intermédiaires (v5.11 → v5.12 → v6.0 → v6.1 → v6.2 → v6.3 → v6.3.x → v6.4). **Une simple MAJ via le bouton « Mettre à jour » de l'UI ne suffit pas** — interventions admin SSH requises selon les milestones franchis.

### Script automatisé : `scripts/migrate_to_v6.4.sh`

Le script `scripts/migrate_to_v6.4.sh` automatise les étapes 1 à 7 ci-dessous (idempotent, peut être relancé sans dommage). Usage :

```bash
ssh slenk@<pi-host>
cd ~/DriftApp
git fetch origin
git checkout origin/main
./scripts/migrate_to_v6.4.sh
# Modes optionnels :
#   DRY_RUN=1 ./scripts/migrate_to_v6.4.sh        # simule sans modifier
#   SKIP_HARDWARE=1 ./scripts/migrate_to_v6.4.sh  # ignore checks Pico W/Shelly
#   TARGET_REF=v6.4.0 ./scripts/migrate_to_v6.4.sh  # pin sur un tag/commit
```

Le script demande sudo une seule fois (1ère MAJ), puis les MAJ suivantes passent par OTA UI (sudoers v5.12 déployé). Backup automatique de `data/config.json` + sessions dans `data/backups/pre_v6.4_<timestamp>/`. Logs détaillés dans `logs/migrate_to_v6.4_<timestamp>.log`.

**Limites du script** :
- NON TESTÉ par CI (machine dev à 800 km du Pi). À valider terrain par Serge sur une session test avant utilisation pour une vraie MAJ.
- NE FLASHE PAS le firmware Pico W (manuel — cf. `firmware/cimier/README.md`).
- NE CONFIGURE PAS le Shelly (manuel — cf. mémoire S. 30/04 cascade 220V/12V).
- Si Pico W ne répond pas, le script propose de continuer en mode dégradé (cimier désactivé) — utile si court-circuit install non levé.

### Détail des 7 étapes (manuelles si on choisit de ne pas utiliser le script)

### Étape 1 — Pré-requis sudoers (pour OTA fonctionnel ≥ v5.12)

Sans ce déploiement, `update_driftapp.sh` ne peut pas `systemctl restart` sans password → MAJ via UI échouera.

```bash
# Sur le Pi, en SSH :
ssh slenk@<pi-host>
cd ~/DriftApp
git fetch origin
git checkout <hash-v5.12>     # ou directement HEAD si on veut tout

sudo cp setup/driftapp-updater.sudoers /etc/sudoers.d/driftapp-updater
sudo chmod 0440 /etc/sudoers.d/driftapp-updater
sudo visudo -cf /etc/sudoers.d/driftapp-updater   # vérifie syntaxe
```

Une fois fait, les MAJ ultérieures via UI auto-redéploieront ce fichier (pattern v5.12).

### Étape 2 — Installation `cimier_service` (nouveau v6.0)

Le service systemd n'existe pas en 5.10. À installer **une seule fois** :

```bash
sudo cp cimier_service.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cimier_service
# Ne PAS encore start — il faut d'abord configurer cimier.host dans data/config.json
```

### Étape 3 — Hardware Pico W cimier (v6.0)

Pré-requis pour v6.0+ qui consomme `cimier_service`. Procédure dans `firmware/cimier/README.md` :
1. Flash MicroPython sur Pico W (`mpremote` + `firmware/cimier/main.py + cimier_controller.py + step_generator.py`).
2. Configuration WiFi + IP statique DHCP (mémoire `feedback_no_hardcoded_ips.md` : Pico W = `192.168.1.84`, Shelly = `192.168.1.83`).
3. Cascade alimentation 220V/12V via 2 Shellys (S. 30/04).

**État actuel terrain (2026-05-02)** : court-circuit install définitive Pico W bloque déploiement v6.0+. Mémoire `project_v60_picow_install_short_circuit_20260502.md`. Tant que ça n'est pas levé, **rester en 5.10.0** pour les sessions opérationnelles.

### Étape 4 — Configuration `data/config.json` (rétro-compat partielle)

Sections à ajouter ou compléter (les sections `calibration` et `boot_calibration` ont des defaults rétro-compatibles, les autres sont **requises** pour activer leurs fonctionnalités) :

```json
{
  "cimier": {
    "enabled": true,
    "host": "192.168.1.84",
    "port": 80,
    "automation": { "mode": "manual" },
    "power_switch": { "type": "shelly", "host": "192.168.1.83" }
  },
  "calibration": {
    "persist_path": "data/last_known_position.json",
    "delta_threshold_deg": 1.0,
    "interval_sec": 30
  },
  "boot_calibration": {
    "overshoot_deg": 5.0,
    "sweep_deg": 15.0,
    "timeout_sec": 180.0,
    "poll_interval_sec": 0.1
  }
}
```

**Permissions** : `data/last_known_position.json` est créé par `ems22d.service` (User=slenk). S'assurer que `data/` est writable par slenk :

```bash
sudo chown -R slenk:slenk /home/slenk/DriftApp/data
sudo chmod -R u+rw /home/slenk/DriftApp/data
```

### Étape 5 — Pull + restart cascade

Une fois étapes 1–4 faites, la MAJ peut s'enclencher via l'UI **OU** manuellement :

```bash
ssh slenk@<pi-host>
cd ~/DriftApp
git pull origin main
uv sync                                # met à jour dépendances Python

sudo systemctl restart ems22d.service          # encoder daemon (Phase 1)
sudo systemctl restart motor_service.service   # routine boot + dispatch calibrate (Phase 2+3)
sudo systemctl restart cimier_service.service  # cimier autonome (v6.0+)
sudo systemctl restart driftapp_web.service    # Django (Phase 3 frontend)
```

Vérification post-restart :

```bash
sudo systemctl status ems22d motor_service cimier_service driftapp_web
cat /dev/shm/motor_status.json | python3 -m json.tool | head -30
# → doit contenir 'calibration': {'status': 'ok'|'running'|'degraded'|...}
```

### Étape 6 — Comportement attendu au premier boot post-MAJ v6.4

1. `ems22d.service` démarre → publie IPC encoder + `last_calibration_at` (Phase 1).
2. `motor_service.service` démarre → watchdog thread, puis exécute `_run_boot_calibration` (Phase 2). Durée 5–180 s pendant laquelle :
   - `current_status["status"] == "calibrating"`
   - `calibration.status == "running"`
   - **Watchdog systemd 30 s NE tuera PAS le service** car le thread daemon maintient le heartbeat indépendamment (vérifié pytest, à confirmer terrain).
3. Routine cherche le microswitch 45° via `PositionPersistor.load_last_position` (hint) puis fallback sweep ±15° si nécessaire.
4. À la fin :
   - **Cas nominal (95 %)** : `calibration.status == "ok"`, `method == "hint_trip"` ou `"fallback_sweep"`. UI affiche badge ✓ vert, bannière masquée, boutons mouvement actifs.
   - **Cas dégradé** : `calibration.status == "degraded"` ou `"exception"`, `error_msg` renseigné. UI affiche bannière rouge, badge ✕, **7 boutons mouvement grisés** (GOTO + 4 JOG + 2 Continu), STOPs et cimier toujours actifs (sécurité). L'utilisateur clique « Calibrer maintenant » pour relancer un cycle.

### Étape 7 — Validation terrain (post-MAJ)

À observer sur une session d'astrophotographie :
- Boot motor_service : routine se termine en `ok`, durée et méthode loggés.
- Mouvement nominal : badge ✓, bannière masquée, GOTO/JOG/tracking fonctionnels.
- Test arrêt brutal (kill -9 motor_service + redémarrage) : la position chargée depuis `data/last_known_position.json` doit conduire la routine au switch en quelques secondes (pas un sweep complet).
- Test dégradé simulé (déplacer la coupole off-power avant restart) : bannière rouge, bouton manuel fonctionnel.

### Si quelque chose tourne mal

- **`calibration.status` reste `running` >180 s** : timeout dépassé sans transition → coupole bloquée mécaniquement, ou switch HS, ou daemon ems22d ne publie pas `last_calibration_at`. Vérifier `journalctl -u motor_service -f` et `cat /dev/shm/ems22_position.json`.
- **`motor_service` redémarre en boucle** : le watchdog tue avant la fin → le thread daemon heartbeat n'est pas effectif. Augmenter temporairement `WatchdogSec` dans `motor_service.service` (à reverter ensuite).
- **`data/last_known_position.json` jamais créé** : permissions `data/` insuffisantes pour slenk. Cf. étape 4.
- **Bannière reste affichée même après calibration ok** : cache navigateur (recharger Ctrl+F5), ou `motor_status.json` non rafraîchi (vérifier polling Django).

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
| **6.6.0** | Mai 2026 | Simplification calibration boot (retour terrain 31/05) : (1) `fallback_sweep_deg` default 15° → 7° (séquence `-sweep`/`+2×sweep` = -7°/+14°, soit ≈10s/20s à 40°/min single-speed) — la coupole est toujours parquée près du switch 45°, sweep court suffit pour franchir le capteur. (2) Suppression complète du `PositionPersistor` et de toute la persistance disque de la position absolue : la coupole revient calibrée près de 45° en fin de session, donc inutile de stocker une position qu'on va recalibrer d'emblée au prochain boot — c'est précisément ce que fait le sweep court. Fichiers supprimés : `core/hardware/position_persistor.py` (135 LOC) + `tests/test_position_persistor.py` (~22 tests). Refactor : `core/hardware/calibration_routine.py` (suppression `_attempt_hint_trip` / `_safe_load_hint` / param `persist_path`, `run()` enchaîne directement vers `_attempt_sweep`), `services/motor_service.py` (suppression `PROJECT_ROOT` + param `persist_path` au constructor), `ems22d_calibrated.py` (suppression instanciation + hook `maybe_write`), `core/config/config_loader.py` (suppression dataclass `CalibrationConfig` + parser `_parse_calibration` + champ legacy `overshoot_deg` du `BootCalibrationConfig`), `data/config.json` (section `calibration` supprimée, section `boot_calibration` réduite à 3 clés). Tests refondus : `tests/test_calibration_routine.py` (~150 LOC nettes vs 506 avant), `tests/test_config_loader.py` (`TestCalibrationConfig` supprimé, `TestBootCalibrationConfig` adapté), `tests/test_motor_service.py` + `tests/test_web_views.py` (`method="hint_trip"` → `"sweep"`). Net : ~200 LOC supprimées, plus de bug d'amorçage initial possible (rien à amorcer). |
| **6.4.0** | Mai 2026 | Calibration robuste session-start (4 phases) : (Phase 1) `core/hardware/position_persistor.py` persistance atomique de la position absolue (throttling 1°/30s avec mouvement, jamais immobile, atomic write tmp+rename, jamais raise sur OSError) + IPC `last_calibration_at` ISO 8601 UTC + section `calibration` data/config.json. (Phase 2) `core/hardware/calibration_routine.py` `CalibrationRoutine` exécutée au boot du `motor_service` après watchdog mais avant la boucle principale : hint trip via `PositionPersistor.load_last_position` + overshoot signé, fallback sweep ±15°, watcher thread daemon poll IPC `last_calibration_at` 100 ms → `moteur.request_stop()` immédiat sur transition non-null, timeout 180 s, sous-dict `current_status["calibration"]` propagé (5 clés : status / method / last_calibration_at / error_msg / duration_sec). (Phase 3 backend) Refactor `_execute_calibration_routine(trigger_label)` réutilisé par boot ET runtime, dispatch `cmd_type="calibrate"` dans `process_command`, POST `/api/hardware/calibrate/` → 202 Accepted (ex-stub 501). (Phase 3 frontend) Bannière persistante dashboard si `calibration.status` ∉ {ok, simulated} + désactivation préventive boutons GOTO / JOG / Continu / « Démarrer le suivi » (STOP toujours actif, sécurité) + badge header cliquable (✓/⚠/✕/◯, scroll vers bannière) + bouton « Calibrer maintenant » + carte dédiée page Système (état / méthode / last formaté local / durée + bouton manuel). Cas nominal 95 % sessions sans intervention utilisateur (parking 45° = position connue, routine boot trouve le switch en quelques secondes) ; cas dégradé verrouillé UI. 1100/1100 tests verts (baseline 1093 + 7 net Plan 01 backend, Plan 02 frontend pur sans nouveau test pytest). |
| **6.3.4** | Mai 2026 | UX cosmétique dashboard : (1) logo DriftApp original SVG (`web/static/img/logo.svg`) + favicon (`favicon.svg`) — couleurs ambre `#d4a055` raccord thème observatory, motif coupole + télescope redessiné from scratch (l'image source `coupole.jpg` était une iStock sous licence, non utilisable brute) ; (2) marqueur parking sur couronne extérieure de la boussole à 45° (NE) — fonction `drawParkingMarker()` dans `dashboard.js` rendue dans Canvas, carré arrondi ambre 16×16 + lettre `P` sombre mimant la forme « squared P » de l'emoji 🅿 du bouton ; (3) bouton « Parking » harmonisé sur le rouge des STOPs manuel/cimier (`btn-stop` + override inline `flex:none; padding:0.5rem` pour neutraliser le sizing emphase `flex-1`/`py-3` réservé aux STOPs d'urgence) ; (4) gradient ambré `section-title-fire` désormais visible sur tous les titres de section (`SUIVI D'OBJET`, `CONTRÔLE MANUEL`, `CIMIER`, `JOURNAL`) — fix `display:inline-block + width:fit-content` sur la classe : auparavant le linear-gradient s'étirait sur la largeur du panel parent, et dans les panneaux larges (~1100 px) le texte (~150 px) ne montrait que les ~14 % gauche du gradient (orange uniforme) tandis que `POSITION COUPOLE` dans son panneau étroit (350 px) montrait bien la transition orange→ambre. Frontend pur, 0 backend, 0 nouveau test, recompile Tailwind nécessaire (`./scripts/build_css.sh`). |
| **6.3.3** | Mai 2026 | UX cimier dashboard : (1) parking watcher utilise `displayedCimierState()` (correction phase 3/3 bloquée 2 min sur timeout après cycle de fermeture réussi) ; (2) modale Parking alignée sur Fermer cimier (icon ⚠, btn-danger rouge, message « interrompra la session » explicite) ; (3) cartouches CIMIER sous boussole fusionnés en cartouche unifié col-span-2 (« CIMIER : 192.73° / OUVERT ») — supprime la redondance du label CIMIER ; (4) helper `displayedCimierState()` étendu pour mapper `state=cycle + pico_state ∈ {opening, closing}` → libellés OUVERTURE / FERMETURE / CYCLE OUVERTURE / CYCLE FERMETURE selon le cartouche, avec effet shimmer ambre sur les 3 phases de mouvement ; (5) header icon : flèches ↑/↓ pour opening/closing. Frontend pur, 0 backend touché. |
| **6.3.2** | Mai 2026 | Dev-mode cimier : env-var `CIMIER_DEV_MODE=1` (exportée par `start_dev.sh`) patche en mémoire `cimier.{enabled, host, port, power_switch.type}` pour pointer le simulateur localhost:8001 (au lieu du Pico W 192.168.1.84). Permet aux indicateurs UI cimier (cartouche position OUVERT/FERMÉ sous boussole + cartouche bas ÉTAT/PHASE + timeline activité) d'être vivants en dev sans modifier `data/config.json`. **Aucune incidence prod** : sans env var, comportement strictement inchangé. `start_web.sh` PROD intact (gating config strict). +5 tests pytest TestDevModeOverrides. |
| **6.3.1** | Mai 2026 | Patch UI : countdown cartouche méridien tick local 1 s — corrige le compteur figé côté client quand le polling `/status/` ne renvoie plus `meridian_seconds` (issue ouverte pré-existante terrain NGC 4151 16-17/04). Pattern réutilisé du countdown automation cimier (v6.0 P4 04-02). Frontend pur (`web/static/js/dashboard.js` ~40 LOC), 0 backend, 0 nouveau test pytest, **1032/1032 tests régression verts**. Ferme l'issue Deferred « Countdown méridien fige côté client quand suivi arrêté ». |
| **6.3** | Mai 2026 | Phase 4 cimier autonome — UI session lifecycle complète. Sélecteur 3 modes auto (`manual` / `semi` / `full`) sur dashboard avec persistance via `POST /api/cimier/automation/`, bouton « Parking session » (modale de confirmation conditionnelle si tracking actif → POST `/api/cimier/parking-session/`), countdown contextualisé tick local 1 s (4 cas : manuel inactif / semi fermeture / full ouverture+fermeture / hors-fenêtre), timeline notifications cimier (buffer 50 entrées en mémoire client, FIFO, panneau repliable INFO/WARNING/ERROR), carte « Cimier — Automatisation » sur la page Système (mode courant, prochaine ouverture/fermeture HH:MM + restant). Frontend pur (4 fichiers UI). Régression baseline backend 1021/1021 maintenue. Clôture milestone v6.0 côté code. |
| **6.2** | Mai 2026 | Phase 3 cimier autonome — scheduler astropy intégré à `cimier_service` (polling 60 s, opt-in `cimier.automation.enabled`). Trigger ouverture sun_alt = -12° descendant + déparking +1° (microswitch calibration 45°) + consultation `WeatherProvider.is_safe_to_open()` (1er consommateur effectif). Trigger fermeture ~15 min avant sun_alt = -6° montant : `tracking_stop` + `goto 45°` (parking) + `close` cimier en parallèle. Helper `core/observatoire/sun_altitude.py` + writer Python neutre `services/motor_ipc_writer.py`. Préalable Phase 4 (UI lifecycle session) |
| **6.1** | Mai 2026 | Phase 2 cimier autonome — garde-fous UI (modale anti-clic-fantôme + cascade auto tracking↔cimier livrées sub-plan 02-01) + interface logique `WeatherProvider` (Strategy + `NoopWeatherProvider`) câblée dans `cimier_service` (log structuré au démarrage de cycle, pas de blocage runtime). Préalable à Phase 3 (scheduler éphémérides) et milestone capteurs ultérieur (v6.4+) |
| **6.0** | Mai 2026 | Cimier autonome v1 — firmware Pico W (Phase 0) + cascade Shelly 220V/12V + `cimier_service` autonome + IPC `/dev/shm/cimier_*.json` + endpoints Django `/api/cimier/{open,close,stop,status}/` + panel UI dashboard cimier (Alpine.js + Tailwind). Phase 1 du milestone v6.0 |
| **5.12** | Avril 2026 | OTA robuste : diff config UI + choix utilisateur, redéploiement sudoers auto (5.12.0). Garde-fou UI anti-GOTO involontaire pendant tracking actif — JOG/Continu/GOTO grisés (5.12.1) |
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
