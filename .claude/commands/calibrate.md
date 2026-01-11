---
description: Calibration de l'encodeur EMS22A via microswitch
category: utilities-debugging
argument-hint: [optionnel] mode (check, guide, force)
---

# Calibration Encodeur DriftApp

Guide la calibration de l'encodeur magnetique EMS22A via le microswitch a 45°.

## Instructions

Tu vas aider a calibrer l'encodeur : **$ARGUMENTS**

### Comprendre la Calibration

L'encodeur EMS22A est un encodeur relatif qui accumule les impulsions. Sans calibration :
- La position affichee derive au fil du temps
- Les erreurs s'accumulent
- Le suivi devient imprecis

**Solution** : Un microswitch place a 45° azimut permet de recaler automatiquement la position.

### 1. Verification de l'Etat Actuel

```bash
echo "=== ETAT CALIBRATION ==="

# Lire l'etat de l'encodeur
cat /dev/shm/ems22_position.json | python3 -c "
import sys, json
d = json.load(sys.stdin)
angle = d.get('angle', 0)
calibrated = d.get('calibrated', False)
status = d.get('status', 'inconnu')
raw = d.get('raw', 0)

print(f'Position actuelle: {angle:.2f}°')
print(f'Valeur brute: {raw}')
print(f'Status: {status}')
print(f'Calibre: {\"OUI\" if calibrated else \"NON\"}')

if not calibrated:
    print()
    print('ATTENTION: Encodeur non calibre!')
    print('La position affichee peut etre incorrecte.')
    print('Effectuer une calibration en passant par 45°.')
"
```

### 2. Position du Microswitch

Le microswitch SS-5GL est monte a **45° azimut** (Nord-Est).

```
        N (0°)
         |
    NW   |   NE
         |     * SWITCH (45°)
   ------+------
         |
    SW   |   SE
         |
        S (180°)
```

**Caracteristiques** :
- GPIO 27 (BCM)
- Actif bas (0 = appuye, 1 = relache)
- Detection sur transition 1→0

### 3. Procedure de Calibration Manuelle

#### Etape 1 : Positionner la coupole

```bash
# Option A: Via interface web
# Utiliser les boutons JOG pour approcher 45°

# Option B: Via commande directe
# Mouvement continu vers l'Est (sens horaire)
echo '{"id":"cal-1","command":"continuous","direction":"cw"}' > /dev/shm/motor_command.json

# Observer la position
watch -n 0.5 'cat /dev/shm/ems22_position.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"Position: {d.get(\"angle\",0):.1f}° Calibre: {d.get(\"calibrated\")}\")"'

# Arreter quand proche de 45°
echo '{"id":"cal-2","command":"stop"}' > /dev/shm/motor_command.json
```

#### Etape 2 : Passer sur le switch

```bash
# Mouvement lent vers 45°
# Si position < 45° : mouvement CW
# Si position > 45° : mouvement CCW

# JOG de 1° pour approche fine
echo '{"id":"cal-3","command":"jog","delta":1.0}' > /dev/shm/motor_command.json
```

#### Etape 3 : Verifier la calibration

```bash
# Verifier que calibrated = true
cat /dev/shm/ems22_position.json | python3 -c "
import sys, json
d = json.load(sys.stdin)
if d.get('calibrated'):
    print('CALIBRATION REUSSIE!')
    print(f'Position recalee a: {d.get(\"angle\"):.2f}°')
else:
    print('Calibration non detectee')
    print('Verifier le passage sur le switch')
"
```

### 4. Calibration Automatique (GOTO 45°)

```bash
echo "=== CALIBRATION AUTOMATIQUE ==="

# Lire position actuelle
POS=$(cat /dev/shm/ems22_position.json | python3 -c "import sys,json; print(json.load(sys.stdin).get('angle',0))")
echo "Position actuelle: $POS°"

# GOTO vers 45°
echo "Deplacement vers 45°..."
echo '{"id":"auto-cal","command":"goto","angle":45.0}' > /dev/shm/motor_command.json

# Attendre fin du mouvement
for i in {1..60}; do
    sleep 1
    STATUS=$(cat /dev/shm/motor_status.json | python3 -c "import sys,json; print(json.load(sys.stdin).get('status'))")
    CAL=$(cat /dev/shm/ems22_position.json | python3 -c "import sys,json; print(json.load(sys.stdin).get('calibrated'))")

    if [ "$CAL" = "True" ]; then
        echo "CALIBRATION REUSSIE!"
        break
    fi

    if [ "$STATUS" = "idle" ]; then
        echo "Mouvement termine, verification..."
        break
    fi

    echo "En cours... ($i/60)"
done

# Resultat final
cat /dev/shm/ems22_position.json | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'Position finale: {d.get(\"angle\"):.2f}°')
print(f'Calibre: {d.get(\"calibrated\")}')
"
```

### 5. Diagnostic du Switch

Si la calibration ne fonctionne pas :

```bash
echo "=== DIAGNOSTIC SWITCH ==="

# Verifier GPIO 27 (si sur Raspberry Pi)
if command -v raspi-gpio &> /dev/null; then
    echo "Etat GPIO 27:"
    raspi-gpio get 27
fi

# Verifier les logs du daemon encodeur
echo "Logs daemon encodeur:"
sudo journalctl -u ems22d -n 20 --no-pager 2>/dev/null | grep -i "switch\|calib" || echo "Pas de logs switch"

# Test manuel du switch
echo ""
echo "Pour tester manuellement:"
echo "1. Ouvrir un terminal sur le Pi"
echo "2. Executer: python3 -c \"import RPi.GPIO as GPIO; GPIO.setmode(GPIO.BCM); GPIO.setup(27, GPIO.IN, pull_up_down=GPIO.PUD_UP); print('Switch:', 'APPUYE' if GPIO.input(27)==0 else 'RELACHE')\""
echo "3. Appuyer sur le switch et relancer"
```

### 6. Problemes Courants

| Symptome | Cause | Solution |
|----------|-------|----------|
| Calibration jamais detectee | Switch defaillant | Verifier cablage GPIO 27 |
| Position incorrecte apres calibration | Offset config | Ajuster dans config.json |
| Calibration perdue au redemarrage | Normal | Recalibrer apres chaque demarrage |
| Position saute de 360° | Passage par 0° | Normal, continuer |

### 7. Configuration du Point de Calibration

Le point de calibration est configure dans le daemon encodeur :

```python
# ems22d_calibrated.py
CALIBRATION_ANGLE = 45.0  # Angle de calibration en degres
SWITCH_GPIO = 27          # GPIO du microswitch
```

Pour modifier (si switch deplace) :

```bash
# Editer le daemon
nano ems22d_calibrated.py

# Chercher CALIBRATION_ANGLE et modifier
# Redemarrer le daemon
sudo systemctl restart ems22d
```

### 8. Resume

```
=== RESUME CALIBRATION ===

Etat actuel:
  Position: X°
  Calibre: OUI/NON

Procedure:
  1. Deplacer la coupole vers 45° (NE)
  2. Le switch est active automatiquement
  3. Position recalee a 45.00°

Verification:
  - cat /dev/shm/ems22_position.json
  - Champ "calibrated" doit etre true

En cas de probleme:
  - Verifier GPIO 27
  - Verifier logs: journalctl -u ems22d
  - Tester switch manuellement
```

### Mode Simulation

En mode simulation, la calibration est simulee :
- Passage par 45° detecte automatiquement
- Flag `calibrated` mis a `true`
- Fonctionne sans hardware reel
