---
description: Debug du suivi astronomique DriftApp
category: utilities-debugging
argument-hint: [optionnel] objet celeste a analyser (ex: M31, Vega, Jupiter)
---

# Debug Suivi Astronomique DriftApp

Analyse et debug du systeme de suivi d'objets celestes.

## Instructions

Tu vas analyser le systeme de suivi astronomique : **$ARGUMENTS**

### 1. Etat du Suivi Actuel

Verifie si un suivi est en cours :

```bash
cat /dev/shm/motor_status.json | python3 -c "
import sys, json
d = json.load(sys.stdin)
status = d.get('status')
obj = d.get('tracking_object')
info = d.get('tracking_info', {})

print(f'Status: {status}')
if obj:
    print(f'Objet suivi: {obj}')
    print(f'Azimut: {info.get(\"azimut\", \"N/A\")}°')
    print(f'Altitude: {info.get(\"altitude\", \"N/A\")}°')
    print(f'Position cible: {info.get(\"position_cible\", \"N/A\")}°')
    print(f'Mode adaptatif: {info.get(\"mode_icon\", \"\")} {d.get(\"mode\", \"N/A\").upper()}')
    print(f'Corrections: {info.get(\"total_corrections\", 0)}')
    print(f'Prochain check: {info.get(\"remaining_seconds\", \"N/A\")}s')
else:
    print('Aucun suivi actif')
"
```

### 2. Calcul des Coordonnees

Si un objet est specifie, calcule ses coordonnees :

```python
import sys
sys.path.insert(0, '.')
from datetime import datetime, timezone
from core.observatoire.calculations import AstronomicalCalculations
from core.observatoire.catalogue import GestionnaireCatalogue
from core.config.config import get_site_config

# Configuration site
lat, lon, tz_offset, _, _ = get_site_config()
print(f"Site: {lat}°N, {lon}°E")

# Rechercher l'objet
catalogue = GestionnaireCatalogue()
objet = "$ARGUMENTS" or "M31"  # Objet par defaut

result = catalogue.rechercher(objet)
if result:
    print(f"\nObjet: {result['nom']}")
    print(f"RA (J2000): {result['ra_deg']:.4f}°")
    print(f"DEC (J2000): {result['dec_deg']:.4f}°")

    # Calcul coords horizontales
    calc = AstronomicalCalculations(lat, lon)
    now = datetime.now(timezone.utc)
    az, alt = calc.calculer_coords_horizontales(
        result['ra_deg'], result['dec_deg'], now
    )

    print(f"\nCoordonnees actuelles:")
    print(f"Azimut: {az:.2f}°")
    print(f"Altitude: {alt:.2f}°")

    # Determiner mode adaptatif
    if alt >= 75:
        mode = "CONTINUOUS"
    elif alt >= 68:
        mode = "CRITICAL"
    else:
        mode = "NORMAL"
    print(f"Mode adaptatif: {mode}")

    # Visibilite
    if alt < 0:
        print("ATTENTION: Objet sous l'horizon!")
    elif alt < 15:
        print("ATTENTION: Objet tres bas (< 15°)")
else:
    print(f"Objet '{objet}' non trouve dans le catalogue")
```

### 3. Interpolation Abaque

Calcule la position coupole via l'abaque :

```python
import sys
sys.path.insert(0, '.')
from core.tracking.abaque_manager import AbaqueManager

# Charger l'abaque
abaque = AbaqueManager()
if not abaque.load_abaque():
    print("ERREUR: Impossible de charger l'abaque (data/Loi_coupole.xlsx)")
else:
    # Test avec coordonnees calculees precedemment
    az = 180.0  # Remplacer par azimut calcule
    alt = 45.0  # Remplacer par altitude calculee

    position_coupole, details = abaque.get_dome_position(alt, az)

    print(f"\nInterpolation Abaque:")
    print(f"Entree: Alt={alt}°, Az={az}°")
    print(f"Position coupole: {position_coupole:.2f}°")
    print(f"Details: {details}")
```

### 4. Comparaison Position Reelle vs Calculee

```bash
# Position encodeur
ENCODER=$(cat /dev/shm/ems22_position.json | python3 -c "import sys,json; print(json.load(sys.stdin).get('angle',0))")

# Position cible (si suivi actif)
TARGET=$(cat /dev/shm/motor_status.json | python3 -c "import sys,json; print(json.load(sys.stdin).get('tracking_info',{}).get('position_cible','N/A'))")

echo "Position encodeur: $ENCODER°"
echo "Position cible: $TARGET°"

# Calcul ecart
python3 -c "
enc = $ENCODER
try:
    target = float('$TARGET')
    diff = abs(enc - target)
    if diff > 180:
        diff = 360 - diff
    print(f'Ecart: {diff:.2f}°')
    if diff < 0.5:
        print('OK: Dans la tolerance')
    elif diff < 2.0:
        print('ATTENTION: Correction necessaire bientot')
    else:
        print('ALERTE: Ecart important!')
except:
    print('Pas de suivi actif')
"
```

### 5. Analyse des Logs de Suivi

```bash
# Logs recents du suivi
cat /dev/shm/motor_status.json | python3 -c "
import sys, json
d = json.load(sys.stdin)
logs = d.get('tracking_logs', [])
print(f'=== {len(logs)} derniers logs ===')
for log in logs[-10:]:
    time = log.get('time', 'N/A')[-8:]  # HH:MM:SS
    msg = log.get('message', '')
    typ = log.get('type', 'info')
    icon = {'info': 'i', 'success': '+', 'correction': '>', 'warning': '!', 'error': 'X'}.get(typ, '?')
    print(f'[{icon}] {time} {msg}')
"
```

### 6. Simulation de Suivi

Teste le demarrage d'un suivi sans executer :

```python
import sys
sys.path.insert(0, '.')
from datetime import datetime, timezone
from core.observatoire.calculations import AstronomicalCalculations
from core.observatoire.catalogue import GestionnaireCatalogue
from core.tracking.abaque_manager import AbaqueManager
from core.tracking.adaptive_tracking import AdaptiveTrackingManager
from core.config.config import get_site_config, get_motor_config

# Config
lat, lon, _, _, _ = get_site_config()
motor_config = get_motor_config()

# Charger composants
catalogue = GestionnaireCatalogue()
calc = AstronomicalCalculations(lat, lon)
abaque = AbaqueManager()
abaque.load_abaque()
adaptive = AdaptiveTrackingManager(motor_config.get('adaptive_tracking', {}))

# Objet
objet = "$ARGUMENTS" or "M31"
result = catalogue.rechercher(objet)

if result:
    now = datetime.now(timezone.utc)
    az, alt = calc.calculer_coords_horizontales(result['ra_deg'], result['dec_deg'], now)
    pos_coupole, _ = abaque.get_dome_position(alt, az)

    # Mode adaptatif
    params = adaptive.evaluate_tracking_zone(alt, az, 0)

    print(f"\n=== SIMULATION SUIVI: {objet} ===")
    print(f"Coordonnees: Az={az:.1f}° Alt={alt:.1f}°")
    print(f"Position coupole cible: {pos_coupole:.1f}°")
    print(f"Mode: {params.mode.name}")
    print(f"Intervalle: {params.check_interval}s")
    print(f"Seuil correction: {params.correction_threshold}°")
    print(f"Delai moteur: {params.motor_delay*1000:.2f}ms")

    if alt < 0:
        print("\nALERTE: Objet sous l'horizon - suivi impossible")
    elif alt < 15:
        print("\nATTENTION: Objet tres bas - suivi difficile")
    else:
        print("\nPret pour le suivi")
else:
    print(f"Objet '{objet}' non trouve")
```

### 7. Diagnostic des Problemes Courants

| Symptome | Cause Probable | Solution |
|----------|---------------|----------|
| "Objet non trouve" | Nom incorrect ou planete | Verifier catalogue ou utiliser nom exact |
| "Sous l'horizon" | Objet non visible | Attendre ou choisir autre objet |
| Ecart > 5° | Encodeur non calibre | Recalibrer via passage a 45° |
| Mode CONTINUOUS permanent | Proche zenith ou gros delta | Normal, vitesse max necessaire |
| Corrections frequentes | Seuil trop bas ou derive mecanique | Ajuster config ou verifier mecanique |

### 8. Resume

Presente un diagnostic complet :

```
=== DIAGNOSTIC SUIVI ===

Objet: [nom]
Visibilite: [OK/BAS/INVISIBLE]
Coords: Az=X° Alt=X°

Position:
  Encodeur: X°
  Cible: X°
  Ecart: X°

Mode adaptatif: [NORMAL/CRITICAL/CONTINUOUS]
Intervalle: Xs
Corrections effectuees: N

Problemes detectes:
  - ...

Recommandations:
  - ...
```
