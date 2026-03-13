# DriftApp - Système de Suivi Automatique de Coupole Astronomique

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-red.svg)](https://www.raspberrypi.org)
[![Status](https://img.shields.io/badge/status-Production--ready-brightgreen.svg)](https://github.com)

**Système intelligent de suivi de coupole d'observatoire** avec compensation de parallaxe via méthode abaque, modes adaptatifs automatiques et feedback encodeur temps réel. Optimisé pour Raspberry Pi avec interface Web Django.

> **Version actuelle** : 4.4 - Interface Web + Correction saccades GOTO (Décembre 2025)

---

## Table des Matières

- [Vue d'ensemble](#vue-densemble)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Utilisation](#utilisation)
- [Interfaces Disponibles](#interfaces-disponibles)
- [Système Adaptatif](#système-adaptatif)
- [Performance](#performance)
- [Dépannage](#dépannage)

---

## Vue d'ensemble

DriftApp est un système de suivi automatique de coupole astronomique conçu pour compenser automatiquement la rotation de la Terre et maintenir l'alignement entre le télescope et la fente de la coupole.

### Problématique

Lors d'observations astronomiques prolongées, le télescope suit l'objet céleste grâce à sa monture équatoriale, mais la coupole reste fixe. Au fil du temps, la fente de la coupole se désaligne du télescope, bloquant la vue.

### Solution DriftApp

DriftApp calcule en permanence la position optimale de la coupole en tenant compte de :
- **Rotation terrestre** : Déplacement apparent des objets célestes
- **Parallaxe instrumentale** : Décalage entre l'axe du télescope et le centre de la coupole (40 cm de déport, 120 cm de rayon)
- **Méthode Abaque** : Interpolation depuis 275 mesures terrain réelles
- **Zones critiques du ciel** : Ajustement automatique des paramètres selon l'altitude (zenith, horizon)
- **Dérive mécanique** : Compensation via feedback encodeur magnétique

---

## Architecture

### Architecture 3 Processus (v4.4)

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Daemon EMS22A  │     │  Motor Service  │     │  Django Web     │
│  (ems22d.py)    │     │  (motor_svc.py) │     │  (manage.py)    │
│                 │     │                 │     │                 │
│  Lit encodeur   │────▶│  Contrôle       │◀────│  Interface      │
│  SPI @ 50Hz     │ JSON│  moteur + suivi │ IPC │  utilisateur    │
│                 │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        ▼                       ▼                       ▼
/dev/shm/ems22_position.json   GPIO 17/18            Port 8000
```

### Structure des Répertoires

```
DriftApp v4.4/
├── core/
│   ├── config/
│   │   └── config_loader.py      # Chargement configuration centralisée
│   ├── hardware/
│   │   ├── moteur.py             # Contrôle moteur pas-à-pas
│   │   ├── moteur_simule.py      # Simulation pour développement
│   │   ├── feedback_controller.py # Boucle fermée encodeur
│   │   └── hardware_detector.py  # Détection auto Raspberry Pi
│   ├── tracking/
│   │   ├── tracker.py            # Session de suivi principal
│   │   ├── adaptive_tracking.py  # Modes adaptatifs (3 modes)
│   │   ├── abaque_manager.py     # Interpolation loi de coupole
│   │   └── tracking_logger.py    # Logs de suivi
│   ├── observatoire/
│   │   ├── calculations.py       # Coordonnées astronomiques
│   │   ├── ephemerides.py        # Positions planétaires
│   │   └── catalogue.py          # Catalogue objets + SIMBAD
│   └── ui/
│       └── main_screen.py        # Interface TUI (Textual)
├── services/
│   └── motor_service.py          # Service IPC pour Django (v4.4)
├── web/                          # Interface Django
│   ├── templates/dashboard.html  # Interface utilisateur
│   ├── static/                   # CSS, JavaScript
│   ├── hardware/                 # API REST moteur
│   └── tracking/                 # API REST suivi
├── data/
│   ├── config.json               # Configuration centralisée (v2.2)
│   └── Loi_coupole.xlsx          # Abaque 275 points mesurés
├── logs/                         # Fichiers de log
├── tests/                        # Scripts de test et diagnostic
└── ems22d_calibrated.py          # Daemon encodeur avec auto-calibration
```

---

## Installation

### Prérequis

- **Raspberry Pi** 4 ou 5 (Ubuntu 24.04 ou Raspberry Pi OS)
- **Python** 3.11+
- **SPI activé** pour encodeur
- **Accès GPIO** pour moteur

### Installation avec `uv` (Recommandé)

```bash
# 1. Cloner le repository
git clone https://github.com/jpokinter87/DriftApp.git
cd DriftApp

# 2. Installation automatique des dépendances
uv sync

# 3. Configuration
cp data/config.example.json data/config.json
nano data/config.json
# Ajuster : site (lat/lon), microsteps (DOIT être 4)

# 4. Activer SPI (pour encodeur)
sudo raspi-config
# → Interface Options → SPI → Enable
# Redémarrer : sudo reboot
```

### Installation sur PC (Développement)

```bash
# Mode simulation automatique (pas de GPIO)
uv sync
./start_dev.sh start
# Ouvrir http://localhost:8000
```

---

## Configuration

### Configuration Matérielle (CRITIQUE)

Fichier : `data/config.json`

#### Microstepping (TRÈS IMPORTANT)

```json
{
  "moteur": {
    "microsteps": 4,
    "steps_per_revolution": 200,
    "gear_ratio": 2230,
    "steps_correction_factor": 1.08849
  }
}
```

**ATTENTION** : Le paramètre `microsteps` DOIT correspondre à la configuration physique du driver DM556T (SW5-8 tous ON = 200 pulses/rev).

#### Modes Adaptatifs (v4.4)

```json
{
  "adaptive_tracking": {
    "altitudes": {
      "critical": 68.0,
      "zenith": 75.0
    },
    "modes": {
      "normal": { "interval_sec": 60, "motor_delay": 0.002 },
      "critical": { "interval_sec": 15, "motor_delay": 0.001 },
      "continuous": { "interval_sec": 5, "motor_delay": 0.00015 }
    }
  }
}
```

---

## Utilisation

### Démarrage Production (Raspberry Pi)

```bash
# 1. Démarrer tous les services
sudo ./start_web.sh start

# 2. Ouvrir l'interface web
# http://raspberry-pi:8000

# 3. Arrêter les services
sudo ./start_web.sh stop
```

### Démarrage Développement (PC)

```bash
# Mode simulation automatique
./start_dev.sh start

# Interface web
# http://localhost:8000

# Logs temps réel
tail -f logs/motor_service.log
```

---

## Interfaces Disponibles

### 1. Interface Web Django (Recommandée)

**URL** : `http://localhost:8000`

**Fonctionnalités** :
- Boussole interactive avec position coupole
- Recherche d'objets (catalogue local + SIMBAD)
- Démarrage/arrêt du suivi
- Contrôle manuel (JOG +1°, +10°, CCW, CW)
- GOTO vers position absolue
- Indicateurs temps réel (mode, corrections, countdown)
- Logs de suivi en direct

**Avantages** :
- Accessible depuis n'importe quel appareil (tablette, téléphone)
- Pas d'installation sur le client
- Interface responsive

### 2. Interface TUI (Terminal)

```bash
uv run main.py
```

**Fonctionnalités** :
- Interface texte complète
- Raccourcis clavier
- Fonctionne via SSH

### 3. Interface GUI Kivy (Optionnelle)

```bash
uv sync --extra gui
uv run main_gui.py
```

**Fonctionnalités** :
- Interface graphique tactile
- Timer circulaire
- Adapté écran tactile

---

## Système Adaptatif

### 3 Modes Automatiques (v4.4)

| Mode | Déclencheur | Intervalle | Seuil | Vitesse |
|------|-------------|------------|-------|---------|
| NORMAL | Altitude < 68° | 60s | 0.5° | ~5°/min |
| CRITICAL | 68° ≤ Alt < 75° | 15s | 0.25° | ~9°/min |
| CONTINUOUS | Alt ≥ 75° ou Δ > 30° | 5s | 0.1° | ~41°/min |

### Logique de Sélection

```python
if altitude >= 75° or abs(delta) > 30°:
    mode = CONTINUOUS  # Corrections très fréquentes
elif altitude >= 68°:
    mode = CRITICAL    # Surveillance rapprochée
else:
    mode = NORMAL      # Suivi standard
```

### Optimisation GOTO (v4.4)

**Problème résolu** : Les GOTO étaient saccadés à cause des pauses du feedback (~130ms entre chaque itération).

**Solution** :
- **Grands déplacements (> 3°)** : Rotation directe fluide + correction finale feedback
- **Petits déplacements (≤ 3°)** : Feedback classique pour précision
- **JOG (boutons manuels)** : Rotation directe sans feedback (fluidité maximale)

---

## Performance

### Précision

| Configuration | Précision | Dérive 1h |
|---------------|-----------|-----------|
| Sans encodeur | ±2-5° | +5-10° |
| Avec encodeur | ±0.3-0.5° | ~0° |
| Avec switch calibration | ±0.2-0.3° | 0° |

### Vitesses GOTO

| Déplacement | Temps estimé |
|-------------|--------------|
| 10° | ~15s |
| 45° | ~1min |
| 90° | ~2min |
| 180° (méridien) | ~4min |

---

## Dépannage

### Problème : Motor Service ne démarre pas

```bash
# Vérifier les logs
tail -f logs/motor_service.log

# Vérifier les permissions GPIO (Pi)
sudo ./start_web.sh start
```

### Problème : Encodeur non disponible

```bash
# Vérifier que le daemon tourne
ps aux | grep ems22d

# Vérifier le fichier JSON
cat /dev/shm/ems22_position.json

# Relancer le daemon
sudo python3 ems22d_calibrated.py &
```

### Problème : Interface web ne se met pas à jour

```bash
# Forcer rechargement sans cache
Ctrl+Shift+R (ou Cmd+Shift+R sur Mac)
```

### Problème : Moteur tourne 4× trop vite/lent

```bash
# Vérifier microsteps
grep microsteps data/config.json
# Doit afficher : "microsteps": 4
```

---

## Documentation

- **CLAUDE.md** : Guide développeur complet
- **TRACKING_LOGIC.md** : Logique complète du système de tracking
- **CHANGELOG.md** : Historique des versions
- **MODIFICATIONS_V4.4.md** : Détails des corrections v4.4

---

## Historique des Versions

### Version 4.4 (Décembre 2025)
- Correction des saccades GOTO (rotation directe + correction finale)
- Suppression du mode FAST_TRACK (redondant avec CONTINUOUS)
- Nettoyage du code (suppression géométrie parallaxe obsolète)

### Version 4.3 (Décembre 2025)
- Interface Web Django
- Architecture 3 processus (Daemon, Motor Service, Django)
- Communication IPC via /dev/shm/

### Version 4.2 (Novembre 2025)
- Simplification à 3 modes (suppression CAUTIOUS)

### Version 4.0 (Novembre 2025)
- Architecture daemon encodeur
- Méthode incrémentale pour l'encodeur
- Switch de calibration automatique à 45°

---

## Support

**Auteur** : Jean-Pascal
**Licence** : MIT
**Repository** : https://github.com/jpokinter87/DriftApp

---

*Dernière mise à jour : 17 décembre 2025*
*Version 4.4 - Interface Web + Correction saccades GOTO*