# CONTEXTE COMPLET - Système de Suivi de Coupole Astronomique

**Projet** : DriftApp - Système de suivi automatique de coupole
**Date de mise à jour** : 17 décembre 2025
**Version** : 4.4 - Interface Web + Correction saccades GOTO
**Statut** : Production-ready

---

## RESUME EXECUTIF

Système de suivi automatique pour coupole d'observatoire astronomique permettant de suivre les objets célestes en compensant :
- La rotation de la Terre
- La parallaxe instrumentale via méthode abaque (mesures terrain)
- Les discontinuités dans les zones critiques du ciel

**Caracteristiques principales** :
- Architecture 3 processus (Daemon encodeur, Motor Service, Django Web)
- Suivi adaptatif avec 3 modes automatiques (NORMAL, CRITICAL, CONTINUOUS)
- Boucle fermee avec encodeur magnetique EMS22A
- Methode abaque (275 mesures terrain) pour correction de parallaxe
- Interface Web Django (principale) + TUI Textual + GUI Kivy
- Communication IPC via fichiers JSON en memoire partagee (/dev/shm/)

---

## ARCHITECTURE DU SYSTEME

### Architecture 3 Processus (v4.4)

```
+-----------------+     +-----------------+     +-----------------+
|  Daemon EMS22A  |     |  Motor Service  |     |  Django Web     |
|  (ems22d.py)    |     |  (motor_svc.py) |     |  (manage.py)    |
|                 |     |                 |     |                 |
|  Lit encodeur   |---->|  Controle       |<----|  Interface      |
|  SPI @ 50Hz     | JSON|  moteur + suivi | IPC |  utilisateur    |
|                 |     |                 |     |                 |
+-----------------+     +-----------------+     +-----------------+
        |                       |                       |
        v                       v                       v
/dev/shm/ems22_position.json   GPIO 17/18            Port 8000
```

### Flux de Communication

```
1. Django Web envoie commande -> /dev/shm/motor_command.json
2. Motor Service lit la commande et execute
3. Motor Service ecrit statut -> /dev/shm/motor_status.json
4. Django Web lit le statut et met a jour l'interface
5. Daemon Encodeur ecrit position -> /dev/shm/ems22_position.json
6. Motor Service lit position pour feedback boucle fermee
```

### Structure des Repertoires

```
DriftApp v4.4/
├── core/
│   ├── config/
│   │   └── config_loader.py      # Chargement configuration centralisee
│   ├── hardware/
│   │   ├── moteur.py             # Controle moteur pas-a-pas
│   │   ├── moteur_simule.py      # Simulation pour developpement
│   │   ├── feedback_controller.py # Boucle fermee encodeur
│   │   └── hardware_detector.py  # Detection auto Raspberry Pi
│   ├── tracking/
│   │   ├── tracker.py            # Session de suivi principal
│   │   ├── adaptive_tracking.py  # Modes adaptatifs (3 modes)
│   │   ├── abaque_manager.py     # Interpolation loi de coupole
│   │   └── tracking_logger.py    # Logs de suivi
│   ├── observatoire/
│   │   ├── calculations.py       # Coordonnees astronomiques
│   │   ├── ephemerides.py        # Positions planetaires
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
│   ├── config.json               # Configuration centralisee
│   └── Loi_coupole.xlsx          # Abaque 275 points mesures
├── logs/                         # Fichiers de log
├── tests/                        # Scripts de test et diagnostic
└── ems22d_calibrated.py          # Daemon encodeur avec auto-calibration
```

---

## CONFIGURATION MATERIELLE

### Moteur Pas-a-Pas
- **Driver** : DM556T (Leadshine)
- **Configuration** : SW5-8 tous ON = 200 pulses/rev
- **MICROSTEPS** : 4 (CRITIQUE - doit correspondre au driver)
- **Reduction** : 2230:1 (gear_ratio)
- **Facteur de correction** : 1.08849 (calibré)
- **Steps/tour coupole** : ~1,942,968 pas

### Encodeur Magnetique
- **Modele** : EMS22A (10 bits, 1024 counts/rev)
- **Communication** : SPI (bus 0, device 0)
- **Resolution** : ~0.35 deg/count
- **Montage** : Roue 50mm sur couronne 2303mm
- **Usage** : Position absolue + feedback temps reel

### Switch de Calibration (Dec 2025)
- **Modele** : SS-5GL microswitch
- **Position** : 45 deg azimut
- **GPIO** : 27 (avec pull-up interne)
- **Fonction** : Auto-recalage a 45 deg au passage

### Raspberry Pi
- **Modele** : Raspberry Pi 4 ou 5 (auto-detecte)
- **OS** : Ubuntu 24.04 ou Raspberry Pi OS
- **GPIO** : lgpio (Pi 5) ou RPi.GPIO (Pi 4)
- **Localisation** : Sud de la France (44.15 N, 5.23 E, 800m)

---

## SYSTEME DE SUIVI ADAPTATIF

### 3 Modes Automatiques (v4.4)

| Mode | Declencheur | Intervalle | Seuil | Vitesse |
|------|-------------|------------|-------|---------|
| NORMAL | Altitude < 68 deg | 60s | 0.5 deg | ~5 deg/min |
| CRITICAL | 68 deg <= Alt < 75 deg | 15s | 0.25 deg | ~9 deg/min |
| CONTINUOUS | Alt >= 75 deg ou Delta > 30 deg | 5s | 0.1 deg | ~41 deg/min |

### Logique de Selection

```python
if altitude >= 75 or abs(delta) > 30:
    mode = CONTINUOUS  # Corrections tres frequentes
elif altitude >= 68:
    mode = CRITICAL    # Surveillance rapprochee
else:
    mode = NORMAL      # Suivi standard
```

### Optimisation GOTO (v4.4)

**Probleme resolu** : Les GOTO etaient saccades a cause des pauses du feedback (~130ms entre chaque iteration).

**Solution** :
- **Grands deplacements (> 3 deg)** : Rotation directe fluide + correction finale feedback
- **Petits deplacements (<= 3 deg)** : Feedback classique pour precision
- **JOG (boutons manuels)** : Rotation directe sans feedback (fluidite maximale)

---

## METHODE DE CALCUL : ABAQUE

### Principe

La methode abaque utilise 275 mesures terrain reelles pour calculer la position optimale de la coupole. Elle remplace le calcul geometrique de parallaxe (obsolete depuis v4.4).

**Fichier** : `data/Loi_coupole.xlsx`

**Donnees** :
- 275 points mesures (altitude, azimut, position coupole)
- Mesures avec encodeur magnetique
- Couvre ensemble du ciel visible

**Algorithme** :
1. Trouve points voisins dans l'abaque
2. Interpolation bilineaire
3. Retourne position coupole directe

**Avantages** :
- Prend en compte realite mecanique
- Tres precis aux points mesures
- Pas de calculs complexes
- Compense automatiquement les deformations

---

## INTERFACES UTILISATEUR

### 1. Interface Web Django (Recommandee)

**URL** : `http://localhost:8000` (dev) ou `http://raspberry-pi:8000` (prod)

**Fonctionnalites** :
- Boussole interactive avec position coupole
- Recherche d'objets (catalogue local + SIMBAD)
- Demarrage/arret du suivi
- Controle manuel (JOG +1 deg, +10 deg, CCW, CW)
- GOTO vers position absolue
- Indicateurs temps reel (mode, corrections, countdown)
- Logs de suivi en direct

**Avantages** :
- Accessible depuis n'importe quel appareil (tablette, telephone)
- Pas d'installation sur le client
- Interface responsive

### 2. Interface TUI (Terminal)

```bash
uv run main.py
```

**Fonctionnalites** :
- Interface texte complete
- Raccourcis clavier
- Fonctionne via SSH

### 3. Interface GUI Kivy (Optionnelle)

```bash
uv sync --extra gui
uv run main_gui.py
```

**Fonctionnalites** :
- Interface graphique tactile
- Timer circulaire
- Adapte ecran tactile

---

## INSTALLATION ET DEMARRAGE

### Prerequisites

- **Raspberry Pi** 4 ou 5 (Ubuntu 24.04 ou Raspberry Pi OS)
- **Python** 3.11+
- **SPI active** pour encodeur
- **Acces GPIO** pour moteur

### Installation

```bash
# 1. Cloner le repository
git clone https://github.com/jpokinter87/DriftApp.git
cd DriftApp

# 2. Installation automatique des dependances
uv sync

# 3. Configuration
cp data/config.example.json data/config.json
nano data/config.json
# Ajuster : site (lat/lon), microsteps (DOIT etre 4)

# 4. Activer SPI (pour encodeur)
sudo raspi-config
# -> Interface Options -> SPI -> Enable
# Redemarrer : sudo reboot
```

### Demarrage Production (Raspberry Pi)

```bash
# 1. Demarrer tous les services
sudo ./start_web.sh start

# 2. Ouvrir l'interface web
# http://raspberry-pi:8000

# 3. Arreter les services
sudo ./start_web.sh stop
```

### Demarrage Developpement (PC)

```bash
# Mode simulation automatique
./start_dev.sh start

# Interface web
# http://localhost:8000

# Logs temps reel
tail -f logs/motor_service.log
```

---

## CONFIGURATION

### Fichier Principal : data/config.json

```json
{
  "site": {
    "latitude": 44.15,
    "longitude": 5.23,
    "altitude": 800,
    "tz_offset": 1
  },
  "moteur": {
    "microsteps": 4,
    "steps_per_revolution": 200,
    "gear_ratio": 2230,
    "steps_correction_factor": 1.08849
  },
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
  },
  "encodeur": {
    "enabled": true
  }
}
```

### ATTENTION - Configuration MICROSTEPS

**Le parametre `microsteps` DOIT correspondre a la configuration physique du driver DM556T.**

- Driver : SW5-8 tous ON = 200 pulses/rev
- Code : `"microsteps": 4`
- **Si mismatch** : Dome tourne 4x trop loin ou trop lent

---

## COMMUNICATION IPC

### Fichiers JSON en Memoire Partagee

**Position Encodeur** : `/dev/shm/ems22_position.json`
```json
{
  "position": 125.3,
  "raw": 512,
  "calibrated": true,
  "timestamp": "2025-12-17T20:30:00.000000"
}
```

**Statut Moteur** : `/dev/shm/motor_status.json`
```json
{
  "status": "tracking",
  "position": 125.3,
  "target": 130.5,
  "progress": 75,
  "mode": "NORMAL",
  "tracking_object": "M 13",
  "simulation": false,
  "tracking_info": {
    "azimut": 45.2,
    "altitude": 62.5,
    "remaining_seconds": 42,
    "interval_sec": 60
  }
}
```

**Commande Moteur** : `/dev/shm/motor_command.json`
```json
{
  "command": "start_tracking",
  "object_name": "M 13",
  "timestamp": "2025-12-17T20:30:00.000000"
}
```

---

## PERFORMANCE

### Precision

| Configuration | Precision | Derive 1h |
|---------------|-----------|-----------|
| Sans encodeur | +/- 2-5 deg | +5-10 deg |
| Avec encodeur | +/- 0.3-0.5 deg | ~0 deg |
| Avec switch calibration | +/- 0.2-0.3 deg | 0 deg |

### Vitesses GOTO

| Deplacement | Temps estime |
|-------------|--------------|
| 10 deg | ~15s |
| 45 deg | ~1min |
| 90 deg | ~2min |
| 180 deg (meridien) | ~4min |

---

## DEPANNAGE

### Probleme : Motor Service ne demarre pas

```bash
# Verifier les logs
tail -f logs/motor_service.log

# Verifier les permissions GPIO (Pi)
sudo ./start_web.sh start
```

### Probleme : Encodeur non disponible

```bash
# Verifier que le daemon tourne
ps aux | grep ems22d

# Verifier le fichier JSON
cat /dev/shm/ems22_position.json

# Relancer le daemon
sudo python3 ems22d_calibrated.py &
```

### Probleme : Moteur tourne 4x trop vite/lent

```bash
# Verifier microsteps
grep microsteps data/config.json
# Doit afficher : "microsteps": 4
```

### Probleme : Interface web ne se met pas a jour

```bash
# Forcer rechargement sans cache
Ctrl+Shift+R (ou Cmd+Shift+R sur Mac)
```

---

## HISTORIQUE DES VERSIONS

### Version 4.4 (Decembre 2025)
- Correction des saccades GOTO (rotation directe + correction finale)
- Simplification a 3 modes (suppression FAST_TRACK redondant)
- Nettoyage code geometrie parallaxe obsolete
- Mise a jour documentation

### Version 4.3 (Decembre 2025)
- Interface Web Django
- Architecture 3 processus (Daemon, Motor Service, Django)
- Communication IPC via /dev/shm/

### Version 4.2 (Novembre 2025)
- Simplification a 3 modes (suppression CAUTIOUS)

### Version 4.0 (Novembre 2025)
- Architecture daemon encodeur
- Methode incrementale pour l'encodeur
- Switch de calibration automatique a 45 deg

### Version 2.1 (Novembre 2025)
- Boucle fermee avec encodeur (optionnel)
- Resolution probleme MICROSTEPS=16
- Reorganisation arborescence

### Version 2.0 (Novembre 2025)
- Systeme adaptatif 4 modes
- Anticipation predictive
- Resolution probleme Eltanin
- Methode abaque

### Version 1.0 (Initiale)
- Suivi basique
- Methode vectorielle
- Interface Textual
- Controle moteur

---

## LIMITATIONS CONNUES

1. **Objets tres rapides** : Lune, ISS non supportes (mouvement propre important)
2. **Pres du zenith** (>85 deg altitude) : Tests limites, comportement non garanti
3. **Discontinuites abaque** : Interpolation depend de la densite de mesures
4. **Encodeur daemon crash** : Systeme continue en boucle ouverte (pas de feedback)

---

## DOCUMENTATION COMPLEMENTAIRE

- **README.md** : Guide d'installation et utilisation
- **CLAUDE.md** : Guide developpeur complet
- **TRACKING_LOGIC.md** : Logique complete du systeme de tracking
- **CHANGELOG.md** : Historique des versions
- **MODIFICATIONS_V4.4.md** : Details des corrections v4.4

---

**Auteur** : Jean-Pascal
**Licence** : MIT
**Repository** : https://github.com/jpokinter87/DriftApp

---

*Derniere mise a jour : 17 decembre 2025*
*Version 4.4 - Interface Web + Correction saccades GOTO*