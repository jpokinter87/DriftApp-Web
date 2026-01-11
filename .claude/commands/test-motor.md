---
description: Tests moteur et boucle feedback DriftApp
category: utilities-debugging
argument-hint: [optionnel] test specifique (rotation, feedback, ramp, all)
---

# Tests Moteur DriftApp

Execute une serie de tests pour valider le fonctionnement du moteur et de la boucle feedback.

## Instructions

Tu vas executer des tests sur le systeme moteur DriftApp : **$ARGUMENTS**

### Prerequis

Avant de commencer, verifie :

```bash
# Verifier que le Motor Service est actif
cat /dev/shm/motor_status.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Status: {d.get(\"status\", \"inconnu\")}')"
```

Si le service n'est pas actif, propose de le demarrer.

### Test 1: Lecture Position Encodeur

```bash
# Lire la position actuelle
cat /dev/shm/ems22_position.json | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'Position: {d.get(\"angle\", \"N/A\")}°')
print(f'Calibre: {d.get(\"calibrated\", False)}')
print(f'Status: {d.get(\"status\", \"inconnu\")}')
"
```

### Test 2: Rotation Simple (JOG)

Envoie une commande JOG pour verifier la rotation :

```python
# Via l'API Django
import requests

# JOG +5 degres
response = requests.post('http://localhost:8000/api/hardware/jog/',
                         json={'delta': 5.0})
print(f"JOG +5°: {response.status_code}")

# Attendre et lire position
import time
time.sleep(3)

response = requests.get('http://localhost:8000/api/hardware/status/')
status = response.json()
print(f"Nouvelle position: {status.get('position')}°")
```

Ou via commande directe IPC :

```bash
# Envoyer commande JOG
echo '{"id":"test-jog","command":"jog","delta":5.0}' > /dev/shm/motor_command.json

# Attendre et verifier
sleep 3
cat /dev/shm/motor_status.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Position: {d.get(\"position\")}°')"
```

### Test 3: GOTO avec Feedback

Teste la boucle fermee avec GOTO :

```bash
# Lire position actuelle
POS_INIT=$(cat /dev/shm/ems22_position.json | python3 -c "import sys,json; print(json.load(sys.stdin).get('angle',0))")
echo "Position initiale: $POS_INIT°"

# Calculer cible (+30°)
TARGET=$(python3 -c "print(($POS_INIT + 30) % 360)")
echo "Cible: $TARGET°"

# Envoyer GOTO
echo "{\"id\":\"test-goto\",\"command\":\"goto\",\"angle\":$TARGET}" > /dev/shm/motor_command.json

# Surveiller progression
for i in {1..20}; do
  sleep 1
  STATUS=$(cat /dev/shm/motor_status.json 2>/dev/null)
  echo "$STATUS" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'[{d.get(\"progress\",0):3d}%] Pos: {d.get(\"position\",0):.1f}° Status: {d.get(\"status\")}')
"
  # Arreter si idle
  echo "$STATUS" | grep -q '"status": "idle"' && break
done

# Position finale
echo "Position finale: $(cat /dev/shm/ems22_position.json | python3 -c 'import sys,json; print(json.load(sys.stdin).get(\"angle\",0))')°"
```

### Test 4: Rampe d'Acceleration

Verifie que la rampe S-curve fonctionne :

```python
# Test unitaire de la rampe
import sys
sys.path.insert(0, '.')
from core.hardware.acceleration_ramp import AccelerationRamp

# Creer une rampe pour 2000 pas
ramp = AccelerationRamp(
    total_steps=2000,
    start_delay=0.003,
    target_delay=0.00015,
    ramp_steps=500
)

# Afficher les phases
print(f"Warm-up: {ramp.warmup_steps} pas")
print(f"Acceleration: {ramp.ramp_steps} pas")
print(f"Croisiere: {ramp.cruise_steps} pas")
print(f"Deceleration: {ramp.ramp_steps} pas")

# Echantillons de delais
for step in [0, 10, 100, 500, 1000, 1500, 1900, 1999]:
    delay = ramp.get_delay(step)
    phase = ramp.get_phase(step)
    print(f"Pas {step:4d}: {delay*1000:.2f}ms ({phase})")
```

### Test 5: Test de Precision

Effectue plusieurs GOTO et mesure l'erreur :

```python
import requests
import time

errors = []
for i, target in enumerate([45, 90, 180, 270, 0]):
    print(f"\nTest {i+1}: GOTO {target}°")

    # Envoyer GOTO
    requests.post('http://localhost:8000/api/hardware/goto/',
                  json={'angle': target})

    # Attendre fin
    for _ in range(30):
        time.sleep(1)
        status = requests.get('http://localhost:8000/api/hardware/status/').json()
        if status.get('status') == 'idle':
            break

    # Lire position finale
    pos = status.get('position', 0)
    error = abs(pos - target)
    if error > 180:
        error = 360 - error
    errors.append(error)
    print(f"Position: {pos:.2f}° | Erreur: {error:.2f}°")

# Resume
print(f"\n=== RESUME ===")
print(f"Erreur moyenne: {sum(errors)/len(errors):.2f}°")
print(f"Erreur max: {max(errors):.2f}°")
print(f"Precision OK: {'OUI' if max(errors) < 1.0 else 'NON'}")
```

### Test 6: Test Arret d'Urgence

```bash
# Demarrer mouvement continu
echo '{"id":"test-cont","command":"continuous","direction":"cw"}' > /dev/shm/motor_command.json

# Attendre 2 secondes
sleep 2

# Envoyer STOP
echo '{"id":"test-stop","command":"stop"}' > /dev/shm/motor_command.json

# Verifier arret
sleep 0.5
cat /dev/shm/motor_status.json | python3 -c "
import sys,json
d=json.load(sys.stdin)
status = d.get('status')
print(f'Status apres STOP: {status}')
print('STOP OK' if status == 'idle' else 'ERREUR: Moteur non arrete')
"
```

### Resume des Tests

Presente un resume :

```
=== RESULTATS TESTS MOTEUR ===

1. Lecture encodeur:     [OK/ERREUR]
2. Rotation JOG:         [OK/ERREUR]
3. GOTO feedback:        [OK/ERREUR] (erreur: X.X°)
4. Rampe acceleration:   [OK/ERREUR]
5. Precision multi-GOTO: [OK/ERREUR] (erreur moy: X.X°)
6. Arret urgence:        [OK/ERREUR]

Diagnostic:
  - ...
```

## Mode Simulation

En mode simulation, tous les tests fonctionnent mais avec timing simule. Les resultats sont representatifs mais pas identiques a la production.
