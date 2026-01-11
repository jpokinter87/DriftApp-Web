---
description: Validation et modification de la configuration DriftApp
category: utilities-debugging
argument-hint: [optionnel] section (site, motor, adaptive, thresholds, all)
---

# Configuration DriftApp

Valide et aide a modifier la configuration du systeme.

## Instructions

Tu vas analyser et modifier la configuration : **$ARGUMENTS**

### 1. Lecture de la Configuration Actuelle

```bash
echo "=== CONFIGURATION ACTUELLE ==="
cat data/config.json | python3 -m json.tool
```

### 2. Validation Complete

```python
import sys
import json
sys.path.insert(0, '.')

# Charger la config
with open('data/config.json', 'r') as f:
    config = json.load(f)

errors = []
warnings = []

# === VALIDATION SITE ===
print("=== SITE ===")
site = config.get('site', {})

lat = site.get('latitude', 0)
lon = site.get('longitude', 0)
print(f"Latitude: {lat}°")
print(f"Longitude: {lon}°")

if not (-90 <= lat <= 90):
    errors.append(f"Latitude invalide: {lat} (doit etre entre -90 et 90)")
if not (-180 <= lon <= 180):
    errors.append(f"Longitude invalide: {lon} (doit etre entre -180 et 180)")

# Verifier si c'est bien l'Observatoire Ubik (France)
if not (40 <= lat <= 52 and -5 <= lon <= 10):
    warnings.append(f"Coordonnees hors de France: {lat}, {lon}")

# === VALIDATION MOTEUR ===
print("\n=== MOTEUR ===")
moteur = config.get('moteur', {})

steps = moteur.get('steps_per_revolution', 200)
microsteps = moteur.get('microsteps', 4)
gear_ratio = moteur.get('gear_ratio', 2230)
correction = moteur.get('steps_correction_factor', 1.0)

print(f"Steps/rev: {steps}")
print(f"Microsteps: {microsteps}")
print(f"Gear ratio: {gear_ratio}")
print(f"Correction factor: {correction}")

# Calcul steps par tour de coupole
steps_per_dome = steps * microsteps * gear_ratio * correction
print(f"Steps/tour coupole: {steps_per_dome:.0f}")

if steps not in [200, 400]:
    warnings.append(f"Steps/rev inhabituel: {steps} (standard: 200 ou 400)")
if microsteps not in [1, 2, 4, 8, 16, 32]:
    errors.append(f"Microsteps invalide: {microsteps}")
if gear_ratio < 100 or gear_ratio > 10000:
    warnings.append(f"Gear ratio inhabituel: {gear_ratio}")

# === VALIDATION GPIO ===
print("\n=== GPIO ===")
gpio = config.get('gpio', moteur.get('gpio', {}))
dir_pin = gpio.get('dir', gpio.get('dir_pin', 17))
step_pin = gpio.get('step', gpio.get('step_pin', 18))
print(f"DIR pin: GPIO {dir_pin}")
print(f"STEP pin: GPIO {step_pin}")

if dir_pin == step_pin:
    errors.append("DIR et STEP utilisent le meme GPIO!")
if dir_pin not in range(2, 28) or step_pin not in range(2, 28):
    errors.append("GPIO hors plage valide (2-27)")

# === VALIDATION TRACKING ADAPTATIF ===
print("\n=== TRACKING ADAPTATIF ===")
adaptive = config.get('adaptive_tracking', {})

altitudes = adaptive.get('altitudes', {})
critical_alt = altitudes.get('critical', 68)
zenith_alt = altitudes.get('zenith', 75)
print(f"Altitude critique: {critical_alt}°")
print(f"Altitude zenith: {zenith_alt}°")

if critical_alt >= zenith_alt:
    errors.append(f"Altitude critique ({critical_alt}) >= zenith ({zenith_alt})")
if critical_alt < 60 or critical_alt > 80:
    warnings.append(f"Altitude critique inhabituelle: {critical_alt}° (standard: 65-70°)")

modes = adaptive.get('modes', {})
for mode_name in ['normal', 'critical', 'continuous']:
    mode = modes.get(mode_name, {})
    interval = mode.get('interval_sec', 60)
    delay = mode.get('motor_delay', 0.002)
    threshold = mode.get('threshold_deg', 0.5)

    print(f"\n  {mode_name.upper()}:")
    print(f"    Intervalle: {interval}s")
    print(f"    Delai moteur: {delay*1000:.2f}ms")
    print(f"    Seuil: {threshold}°")

    if delay < 0.0001:
        warnings.append(f"Mode {mode_name}: delai tres court ({delay*1000:.3f}ms)")
    if delay > 0.01:
        warnings.append(f"Mode {mode_name}: delai tres long ({delay*1000:.1f}ms)")

# === VALIDATION SEUILS ===
print("\n=== SEUILS ===")
thresholds = config.get('thresholds', {})
feedback_min = thresholds.get('feedback_min_deg', 3.0)
large_movement = thresholds.get('large_movement_deg', 30.0)
protection = thresholds.get('feedback_protection_deg', 20.0)
tolerance = thresholds.get('default_tolerance_deg', 0.5)

print(f"Feedback min: {feedback_min}°")
print(f"Grand mouvement: {large_movement}°")
print(f"Protection feedback: {protection}°")
print(f"Tolerance par defaut: {tolerance}°")

if feedback_min > 10:
    warnings.append(f"Seuil feedback_min eleve: {feedback_min}°")
if tolerance > 2:
    warnings.append(f"Tolerance elevee: {tolerance}°")

# === MODE SIMULATION ===
print("\n=== MODE ===")
simulation = config.get('simulation', False)
print(f"Simulation: {'ACTIVE' if simulation else 'DESACTIVE'}")

if simulation:
    warnings.append("Mode simulation actif - pas de controle hardware reel")

# === RESUME ===
print("\n" + "="*50)
print("=== RESUME VALIDATION ===")

if errors:
    print(f"\nERREURS ({len(errors)}):")
    for e in errors:
        print(f"  [X] {e}")

if warnings:
    print(f"\nAVERTISSEMENTS ({len(warnings)}):")
    for w in warnings:
        print(f"  [!] {w}")

if not errors and not warnings:
    print("\n[OK] Configuration valide!")
elif not errors:
    print(f"\n[OK] Configuration valide avec {len(warnings)} avertissement(s)")
else:
    print(f"\n[ERREUR] Configuration invalide - {len(errors)} erreur(s) a corriger")
```

### 3. Modification Interactive

Pour modifier un parametre :

```python
import json

# Charger
with open('data/config.json', 'r') as f:
    config = json.load(f)

# Exemples de modifications courantes:

# 1. Changer les coordonnees du site
# config['site']['latitude'] = 49.01
# config['site']['longitude'] = 2.10

# 2. Ajuster le facteur de correction moteur
# config['moteur']['steps_correction_factor'] = 1.08849

# 3. Modifier les seuils adaptatifs
# config['adaptive_tracking']['altitudes']['critical'] = 68.0
# config['adaptive_tracking']['modes']['normal']['interval_sec'] = 60

# 4. Activer/desactiver simulation
# config['simulation'] = False

# Sauvegarder
with open('data/config.json', 'w') as f:
    json.dump(config, f, indent=2)

print("Configuration sauvegardee!")
```

### 4. Configurations Recommandees

#### Site Observatoire Ubik (France)
```json
{
  "site": {
    "latitude": 49.01,
    "longitude": 2.10,
    "altitude": 100,
    "nom": "Observatoire Ubik"
  }
}
```

#### Moteur DM556T Standard
```json
{
  "moteur": {
    "steps_per_revolution": 200,
    "microsteps": 4,
    "gear_ratio": 2230,
    "steps_correction_factor": 1.08849
  }
}
```

#### Tracking Adaptatif Equilibre
```json
{
  "adaptive_tracking": {
    "altitudes": {
      "critical": 68.0,
      "zenith": 75.0
    },
    "modes": {
      "normal": {
        "interval_sec": 60,
        "threshold_deg": 0.5,
        "motor_delay": 0.002
      },
      "critical": {
        "interval_sec": 15,
        "threshold_deg": 0.35,
        "motor_delay": 0.001
      },
      "continuous": {
        "interval_sec": 5,
        "threshold_deg": 0.25,
        "motor_delay": 0.00015
      }
    }
  }
}
```

### 5. Backup et Restauration

```bash
# Sauvegarder la config actuelle
cp data/config.json data/config.backup.$(date +%Y%m%d_%H%M%S).json

# Lister les backups
ls -la data/config.backup.*.json

# Restaurer un backup
# cp data/config.backup.XXXXXXXX.json data/config.json
```

### 6. Verification Apres Modification

Apres modification, toujours :

1. **Valider** : Relancer ce skill pour verifier
2. **Redemarrer** : Les services pour appliquer

```bash
# Redemarrer les services
sudo systemctl restart motor_service
sudo systemctl restart ems22d

# Verifier
curl -s http://localhost:8000/api/health/ | python3 -m json.tool
```

### 7. Parametres Critiques

| Parametre | Impact | Risque si incorrect |
|-----------|--------|---------------------|
| `microsteps` | Precision mouvement | Derive x2, x4, etc. |
| `gear_ratio` | Calcul position | Mouvement incorrect |
| `motor_delay` | Vitesse max | Perte de pas si trop rapide |
| `latitude/longitude` | Calculs astro | Suivi decale |
| `steps_correction_factor` | Precision finale | Erreur systematique |

### 8. Reset Configuration

Pour revenir a la configuration par defaut :

```bash
# Si config.example.json existe
cp data/config.example.json data/config.json

# Sinon, recreer manuellement
# (utiliser les valeurs recommandees ci-dessus)
```
