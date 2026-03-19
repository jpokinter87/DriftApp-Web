# DriftApp - Système de Suivi Automatique de Coupole Astronomique

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Django 5.0+](https://img.shields.io/badge/django-5.0+-green.svg)](https://www.djangoproject.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-red.svg)](https://www.raspberrypi.org)

**Système intelligent de suivi de coupole d'observatoire** avec modes adaptatifs automatiques et feedback temps réel. Interface web responsive pour contrôle local et distant.

> **Version actuelle** : 5.3.0 - Pilotage RP2040 + Interface Tailwind/Alpine.js (Mars 2026)

---

## Table des Matières

- [Vue d'ensemble](#vue-densemble)
- [Architecture](#architecture)
- [Installation](#installation)
  - [Installation des Services Systemd](#installation-des-services-systemd-production)
- [Configuration](#configuration)
- [Utilisation](#utilisation)
- [Système Adaptatif](#système-adaptatif)
- [Interface Web](#interface-web)
- [Mode Simulation](#mode-simulation)
- [Dépannage](#dépannage)

---

## Vue d'ensemble

DriftApp est un système de suivi automatique de coupole astronomique conçu pour compenser automatiquement la rotation de la Terre et maintenir l'alignement entre le télescope et la fente de la coupole.

### Problématique

Lors d'observations astronomiques prolongées, le télescope suit l'objet céleste grâce à sa monture équatoriale, mais la coupole reste fixe. Au fil du temps, la fente de la coupole se désaligne du télescope, bloquant la vue.

### Solution DriftApp

DriftApp calcule en permanence la position optimale de la coupole en utilisant :
- **Methode Abaque** : Interpolation a partir de ~275 mesures terrain reelles
- **Modes adaptatifs** : Ajustement automatique des parametres selon l'altitude
- **Feedback encodeur** : Boucle fermee avec encodeur magnetique EMS22A
- **Calibration automatique** : Recalage via microswitch a 45° azimut
- **Pilotage RP2040** (v5.3) : Delegation optionnelle au Pi Pico pour precision PIO 8 ns

---

## Méthode de Calcul - Abaque

DriftApp utilise exclusivement une **méthode abaque** basée sur des mesures réelles du site.

### Interpolation à partir de mesures terrain

Le fichier `data/Loi_coupole.xlsx` contient ~275 points de mesure :
```
(Altitude, Azimut) → Position_Coupole
```

Pour une position (Alt, Az) donnée :
1. Recherche des 4 points voisins dans l'abaque
2. Interpolation bilinéaire 2D
3. Calcul de la position optimale de la coupole

**Avantages** :
- Tient compte de la réalité mécanique du site
- Compense les déformations structurelles
- Intègre les jeux mécaniques réels
- Validé par tests terrain

---

## Architecture

### Architecture Trois Processus

```

```

### Structure des Repertoires

```
DriftApp/
├── ems22d_calibrated.py           # Demon encodeur
├── start_web.sh                   # Demarrage production (sudo)
├── start_dev.sh                   # Demarrage developpement (simulation)
│
├── core/                          # Logique metier
│   ├── config/
│   │   ├── config.py              # Constantes, get_motor_config()
│   │   └── config_loader.py       # ConfigLoader, dataclasses (DriftAppConfig...)
│   ├── hardware/
│   │   ├── moteur.py              # MoteurCoupole (GPIO lgpio/RPi.GPIO)
│   │   ├── moteur_rp2040.py       # MoteurRP2040 (serie USB vers Pi Pico) — v5.3
│   │   ├── serial_simulator.py    # Simulateur serie pour dev sans Pico — v5.3
│   │   ├── moteur_simule.py       # Simulation realiste
│   │   ├── feedback_controller.py # Boucle fermee iterative
│   │   ├── acceleration_ramp.py   # Rampe S-curve
│   │   └── daemon_encoder_reader.py # Lecteur encodeur IPC
│   ├── tracking/
│   │   ├── tracker.py             # TrackingSession (classe principale)
│   │   ├── adaptive_tracking.py   # 3 modes adaptatifs
│   │   └── abaque_manager.py      # Interpolation 2D (Loi_coupole.xlsx)
│   └── observatoire/              # Calculs astronomiques
│
├── firmware/                      # Firmware RP2040 (v5.3)
│   ├── main.py                    # Boucle serie MOVE/STOP/STATUS
│   ├── step_generator.py          # Programme PIO assembleur
│   ├── ramp.py                    # Rampe S-curve cote firmware
│   └── README.md                  # Guide flash MicroPython
│
├── services/                      # Motor Service
│   ├── motor_service.py           # Service principal, watchdog systemd
│   ├── command_handlers.py        # Handlers GOTO/JOG/TRACKING
│   ├── ipc_manager.py             # Communication inter-processus
│   └── simulation.py              # SimulatedDaemonReader
│
├── web/                           # Application Django + Tailwind + Alpine.js
│   ├── driftapp_web/              # Config Django (settings.py, urls.py)
│   ├── hardware/                  # API controle moteur
│   ├── tracking/                  # API suivi astronomique
│   ├── health/                    # API diagnostic systeme
│   ├── session/                   # API sessions
│   ├── templates/                 # 3 pages HTML (dashboard, system, session)
│   └── static/                    # Tailwind CSS, Alpine.js, boussole canvas
│
├── data/
│   ├── config.json                # Configuration centralisee
│   └── Loi_coupole.xlsx           # Abaque 275 mesures terrain
│
├── tests/                         # 820+ tests (pytest)
├── RP2040_UPGRADE.md              # Guide migration GPIO → RP2040
└── CLAUDE.md                      # Guide developpeur
```

---

## Installation

### Prérequis

- **Raspberry Pi** 4 ou 5 (Ubuntu 24.04 ou Raspberry Pi OS)
  - Pi 5 : utilise lgpio (détection automatique)
  - Pi 4 et antérieurs : utilise RPi.GPIO
- **Python** 3.11+
- **SPI activé** pour encodeur (production)

### Installation avec `uv`

```bash
# 1. Cloner le repository
git clone https://github.com/jpokinter87/DriftApp-Web.git
cd DriftApp-Web

# ou bien en choisissant le répertoire par exemple /home/slenk/Dome_Web
git clone https://github.com/jpokinter87/DriftApp-Web.git /home/slenk/Dome_Web
cd /home/slenk/Dome_Web
 

# 2. Installation des dépendances
uv sync

# 3. Configuration (déjà fait, tu peux sauter cette étape)
cp data/config.example.json data/config.json
nano data/config.json

# 4. Migrations Django (uniquement la première fois pour l'installation)
uv run python manage.py migrate

# 5. (Production) Activer SPI (pas obligatoire, tu peux aussi sauté cette étape)
sudo raspi-config
# → Interface Options → SPI → Enable
```

### Installation des Services Systemd (Production)

Pour un fonctionnement automatique au démarrage du Raspberry Pi, installez les deux services systemd.

#### 1. Adapter les fichiers de service

Éditez les chemins dans les fichiers `.service` pour correspondre à votre installation :

```bash
# Lance ces différentes commandes dans un terminal
# Remplace le chemin par défaut par votre répertoire d'installation
INSTALL_DIR="/home/slenk/DriftApp-Web"

# Édite ems22d.service
sed -i "s|/home/slenk/Dome_v4_5|$INSTALL_DIR|g" ems22d.service

# Édite motor_service.service
sed -i "s|/home/slenk/Dome_v4_5|$INSTALL_DIR|g" motor_service.service
```

#### 2. Copier les fichiers vers systemd

```bash
sudo cp ems22d.service /etc/systemd/system/
sudo cp motor_service.service /etc/systemd/system/
sudo systemctl daemon-reload
```

#### 3. Activer les services au démarrage

```bash
# Activer les services
sudo systemctl enable ems22d.service
sudo systemctl enable motor_service.service

# Démarrer les services
sudo systemctl start ems22d.service
sudo systemctl start motor_service.service
```

#### 4. Vérifier l'état des services

```bash
# État des services
sudo systemctl status ems22d.service
sudo systemctl status motor_service.service

# Logs en temps réel
sudo journalctl -u ems22d.service -f
sudo journalctl -u motor_service.service -f
```

#### 5. Commandes utiles

```bash
# Redémarrer un service
sudo systemctl restart motor_service.service

# Arrêter les services
sudo systemctl stop motor_service.service
sudo systemctl stop ems22d.service

# Désactiver un service (ne démarre plus au boot)
sudo systemctl disable motor_service.service
```

#### Notes importantes

| Service | Utilisateur | Raison |
|---------|-------------|--------|
| `ems22d.service` | Utilisateur normal | Accès SPI (groupe `spi`) |
| `motor_service.service` | root | Accès GPIO direct |

- **Ordre de démarrage** : `motor_service` dépend de `ems22d` (défini dans le fichier service)
- **Watchdog** : `motor_service` envoie un heartbeat toutes les 10s ; systemd le redémarre s'il ne répond plus pendant 30s
- **Redémarrage auto** : Les deux services redémarrent automatiquement en cas d'échec

---

## Configuration

### Configuration Matérielle

Fichier : `data/config.json`

```json
{
  "site": {
    "latitude": 44.15,
    "longitude": 5.23,
    "altitude": 800,
    "nom": "Observatoire Ubik"
  },
  "motor_driver": {
    "type": "gpio",
    "serial": { "port": "/dev/ttyACM0", "baudrate": 115200, "timeout": 2.0 }
  },
  "moteur": {
    "microsteps": 4,
    "steps_per_revolution": 200,
    "gear_ratio": 2230,
    "steps_correction_factor": 1.08849
  },
  "adaptive_tracking": {
    "altitudes": { "critical": 68.0, "zenith": 75.0 },
    "modes": {
      "normal": { "interval_sec": 60, "motor_delay": 0.002 },
      "critical": { "interval_sec": 30, "motor_delay": 0.001 },
      "continuous": { "interval_sec": 30, "motor_delay": 0.00014 }
    }
  }
}
```

**Notes** :
- `microsteps: 4` DOIT correspondre a la configuration du driver DM556T
- `motor_driver.type` : `"gpio"` (defaut) ou `"rp2040"` (Pi Pico) — voir [RP2040_UPGRADE.md](RP2040_UPGRADE.md)

---

## Utilisation

### Scripts de Démarrage (Recommandé)

```bash
# Mode Production (Raspberry Pi) - nécessite sudo
sudo ./start_web.sh          # Démarre tous les services
sudo ./start_web.sh stop     # Arrête tous les services
./start_web.sh status        # Vérifie l'état

# Mode Développement (PC) - simulation automatique
./start_dev.sh               # Démarre Motor Service + Django
./start_dev.sh stop          # Arrête les services
./start_dev.sh status        # Vérifie l'état
```

### Mode Développement Manuel (Simulation)

```bash
# Terminal 1: Lancer Django
uv run python manage.py runserver 0.0.0.0:8000

# Terminal 2: Lancer Motor Service (simulation automatique)
uv run python services/motor_service.py

# Ouvrir dans le navigateur
http://localhost:8000
```

En mode développement (sans Raspberry Pi), le système détecte automatiquement l'absence de GPIO et active le **mode simulation** avec :
- Timing réaliste des mouvements (~41°/min)
- Simulation du switch de calibration à 45°
- Position interpolée en temps réel

### Mode Production Manuel (Raspberry Pi)

```bash
# Terminal 1: Démon encodeur (sudo requis)
sudo python3 ems22d_calibrated.py &

# Terminal 2: Motor Service (sudo requis pour GPIO)
sudo python3 services/motor_service.py &

# Terminal 3: Django
uv run python manage.py runserver 0.0.0.0:8000
```

---

## Système Adaptatif

### 3 Modes Automatiques

| Mode | Declencheur | Intervalle | Seuil | Delai moteur |
|------|-------------|------------|-------|--------------|
| NORMAL | Altitude < 68° | 60s | 0.5° | 2.0 ms |
| CRITICAL | 68° ≤ Alt < 75° | 30s | 0.35° | 1.0 ms |
| CONTINUOUS | Alt ≥ 75° ou Δ > 30° | 30s | 0.3° | 0.14 ms |

### Logique de Sélection

```python
if altitude >= 75° or predicted_movement > 30°:
    mode = CONTINUOUS  # Corrections très fréquentes
elif altitude >= 68°:
    mode = CRITICAL    # Surveillance rapprochée
else:
    mode = NORMAL      # Suivi standard
```

---

## Interface Web

### Dashboard Principal

L'interface web affiche en temps réel :
- **Position encodeur** : Angle actuel de la coupole
- **État du système** : idle, moving, tracking, initializing
- **Mode adaptatif** : NORMAL / CRITICAL / CONTINUOUS
- **Objet suivi** : Nom et position (Alt/Az)
- **Statistiques** : Corrections, temps moteur

### Contrôles Disponibles

- **GOTO** : Déplacement vers une position absolue
- **JOG** : Déplacements relatifs (±1°, ±5°, ±10°)
- **CONTINUOUS** : Mouvement continu CW/CCW
- **TRACKING** : Suivi automatique d'objet céleste
- **STOP** : Arrêt d'urgence

### Popup GOTO Initial

Lors du démarrage d'un tracking, un popup affiche :
- Position actuelle et cible
- Delta avec direction (CW/CCW)
- Barre de progression
- Temps restant estimé

### Page Session

Accessible via l'onglet **"Session"** (ou `/session/`), cette page affiche :
- **Graphiques temps réel** : Évolution altitude/azimut avec zones de modes
- **Statistiques** : Corrections effectuées, mouvements CW/CCW, moyenne
- **Distribution modes** : Temps passé en NORMAL/CRITICAL/CONTINUOUS
- **Historique** : Liste des sessions passées avec détails

### Page Diagnostic Système

Accessible via l'onglet **"Système"** dans le header (ou `/api/health/system/`), cette page affiche en temps réel :

- **État des composants** : Motor Service et Encoder Daemon avec indicateurs couleur (vert/orange/rouge)
- **Fichiers IPC** : Contenu JSON de `/dev/shm/motor_status.json`, `ems22_position.json`, `motor_command.json`
- **Configuration** : Site, paramètres moteur, seuils, modes adaptatifs
- **Rafraîchissement** : Automatique toutes les 2 secondes (désactivable)

### API Health Check

Endpoints pour monitoring externe (scripts, Nagios, etc.) :

| Endpoint | Description |
|----------|-------------|
| `GET /api/health/` | État global (healthy/unhealthy) |
| `GET /api/health/diagnostic/` | Diagnostic complet en JSON |
| `GET /api/health/system/` | Page web diagnostic |

```bash
# Exemple: vérifier l'état du système
curl -s http://localhost:8000/api/health/ | python3 -m json.tool
```

---

## Mode Simulation

### Fonctionnement

Le `MovementSimulator` fournit une simulation réaliste :
- **Timing réel** : Les mouvements prennent le temps qu'ils prendraient en production
- **Interpolation** : Position calculée en fonction du temps écoulé
- **Switch calibration** : Simulation du microswitch à 45°
- **Valeurs raw** : Simulation des valeurs brutes encodeur (0-1023)

### Configuration

Le mode simulation est activé automatiquement en l'absence de GPIO (développement sur PC).

Pour forcer le mode simulation sur Raspberry Pi :
```json
{
  "simulation": true
}
```

### Vitesses Simulées

| Mode | Vitesse | Temps pour 90° |
|------|---------|----------------|
| CONTINUOUS | ~1.2°/s | ~75s |
| CRITICAL | ~0.3°/s | ~5min |
| NORMAL | ~0.15°/s | ~10min |

---

## Calibration Automatique

### Switch de Calibration (45°)

Un microswitch SS-5GL monté à 45° azimut permet le recalage automatique :

1. Coupole passe à 45° → Switch activé
2. Démon détecte transition GPIO 27 (1→0)
3. Recalage automatique : `total_counts` ajusté pour afficher 45.0°
4. Dérive éliminée

### Simulation du Switch

En mode simulation, le passage par 45° est détecté automatiquement :
- Le flag `calibrated` passe à `True`
- Un callback peut être défini pour réagir à l'événement

---

## Dépannage

### Motor Service ne démarre pas

```bash
# Vérifier les logs
tail -f logs/motor_service.log

# Vérifier les permissions GPIO (production)
groups  # Doit inclure gpio, spi
```

### Encodeur non disponible

```bash
# Vérifier le démon
ps aux | grep ems22d

# Vérifier le fichier JSON
cat /dev/shm/ems22_position.json

# Relancer le démon
sudo python3 ems22d_calibrated.py
```

### Position figée en simulation

Le singleton `MovementSimulator` peut garder l'état entre les tests.
Redémarrer le Motor Service pour réinitialiser.

---

## Tests

```bash
# Tests complets (820+)
uv run pytest tests/ -v

# Tests rapides (sans astropy)
uv run pytest tests/ -k "not astropy" -v

# Tests moteur GPIO et RP2040
uv run pytest tests/test_moteur.py tests/test_moteur_rp2040.py -v

# Tests integration RP2040
uv run pytest tests/test_integration_rp2040.py -v
```

---

## Documentation

- **CLAUDE.md** : Guide developpeur, instructions Claude Code
- **RP2040_UPGRADE.md** : Guide migration GPIO → RP2040 (terrain)
- **firmware/README.md** : Guide flash MicroPython + branchements Pi Pico
- **data/config.json** : Configuration complete avec commentaires
- **docs/IPC_API.md** : Documentation API IPC inter-processus

---

## Protection Moteur (v4.5+)

### Rampe d'Accélération S-Curve

Le moteur est protégé par une rampe d'accélération/décélération automatique :
- **Warm-up** : 10 pas à 10ms pour l'alignement rotor à froid
- **Accélération** : 500 pas avec courbe sigmoïde (départ 3ms)
- **Croisière** : Vitesse nominale constante
- **Décélération** : 500 pas avec courbe sigmoïde (arrêt progressif)

Cette protection est activée par défaut et réduit considérablement le stress mécanique.

---

## Performance

| Métrique | Valeur |
|----------|--------|
| Précision avec encodeur | ±0.3-0.5° |
| Fréquence lecture encodeur | 50 Hz |
| Latence commande web | < 100ms |
| Réduction temps moteur (adaptatif) | 85% |

---

## Changelog

| Version | Date | Description |
|---------|------|-------------|
| **5.3** | Mars 2026 | Pilotage RP2040 : firmware PIO 8 ns, MoteurRP2040 serie, fallback GPIO/RP2040 |
| **5.2** | Mars 2026 | Watchdog thread meridien, logging structure cle=valeur, tests terrain |
| **5.1** | Mars 2026 | Sync production, audit code, refactoring, 746 tests |
| **5.0** | Fev 2026 | Interface moderne Tailwind CSS v4 + Alpine.js, responsive |
| **4.6** | Dec 2025 | DaemonEncoderReader, warm-up phase, support Pi 5 |
| **4.5** | Dec 2025 | Rampe S-curve acceleration/deceleration |
| **4.4** | Dec 2025 | GOTO fluide, architecture 3 processus IPC |

---

**Version** : 5.3.0
**Date** : Mars 2026
**Licence** : MIT
