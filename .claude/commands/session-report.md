---
description: Rapport de session de suivi DriftApp
category: utilities-debugging
argument-hint: [optionnel] ID session ou 'current' pour session active
---

# Rapport de Session DriftApp

Genere un rapport detaille d'une session de suivi astronomique.

## Instructions

Tu vas analyser une session de suivi : **$ARGUMENTS**

### 1. Identification de la Session

```bash
# Si 'current' ou pas d'argument, utiliser session active
if [ "$ARGUMENTS" = "current" ] || [ -z "$ARGUMENTS" ]; then
    echo "=== SESSION ACTIVE ==="
    SESSION_DATA=$(cat /dev/shm/motor_status.json)
    echo "$SESSION_DATA" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if d.get('status') == 'tracking':
    print(f'Objet: {d.get(\"tracking_object\")}')
    print(f'Mode: {d.get(\"mode\", \"N/A\").upper()}')
    info = d.get('tracking_info', {})
    print(f'Corrections: {info.get(\"total_corrections\", 0)}')
    print(f'Mouvement total: {info.get(\"total_correction_degrees\", 0):.1f}°')
else:
    print('Aucune session active')
"
else
    # Chercher session dans l'historique
    SESSION_FILE="data/sessions/$ARGUMENTS.json"
    if [ -f "$SESSION_FILE" ]; then
        echo "=== SESSION: $ARGUMENTS ==="
        SESSION_DATA=$(cat "$SESSION_FILE")
    else
        echo "Session '$ARGUMENTS' non trouvee"
        echo "Sessions disponibles:"
        ls -1 data/sessions/*.json 2>/dev/null | head -10
        exit 1
    fi
fi
```

### 2. Liste des Sessions Disponibles

```python
import os
import json
from datetime import datetime

sessions_dir = 'data/sessions'
sessions = []

if os.path.exists(sessions_dir):
    for f in sorted(os.listdir(sessions_dir), reverse=True)[:20]:
        if f.endswith('.json'):
            path = os.path.join(sessions_dir, f)
            try:
                with open(path) as file:
                    data = json.load(file)
                    sessions.append({
                        'id': f.replace('.json', ''),
                        'object': data.get('object', 'N/A'),
                        'start': data.get('start_time', 'N/A'),
                        'duration': data.get('duration_minutes', 0),
                        'corrections': data.get('total_corrections', 0)
                    })
            except:
                pass

print(f"{'ID':<30} {'Objet':<10} {'Debut':<12} {'Duree':<8} {'Corr':<5}")
print("-" * 70)
for s in sessions:
    print(f"{s['id']:<30} {s['object']:<10} {s['start'][-8:]:<12} {s['duration']:<8.0f}min {s['corrections']:<5}")
```

### 3. Analyse Detaillee de la Session

```python
import json
import sys
sys.path.insert(0, '.')

# Charger la session (active ou fichier)
# session_data = ... (depuis etape 1)

session = json.loads('''$SESSION_DATA''') if '$SESSION_DATA' else {}

# Si session active
if 'tracking_info' in session:
    info = session['tracking_info']
    logs = session.get('tracking_logs', [])

    print("\n=== STATISTIQUES ===")
    print(f"Objet suivi: {session.get('tracking_object', 'N/A')}")
    print(f"Position actuelle: {session.get('position', 0):.1f}°")
    print(f"Position cible: {info.get('position_cible', 0):.1f}°")
    print(f"Mode adaptatif: {session.get('mode', 'N/A').upper()}")

    print(f"\nAzimut: {info.get('azimut', 0):.1f}°")
    print(f"Altitude: {info.get('altitude', 0):.1f}°")

    print(f"\n=== CORRECTIONS ===")
    print(f"Nombre total: {info.get('total_corrections', 0)}")
    print(f"Mouvement total: {info.get('total_correction_degrees', 0):.2f}°")

    # Calculer correction moyenne
    n = info.get('total_corrections', 0)
    total = info.get('total_correction_degrees', 0)
    if n > 0:
        print(f"Correction moyenne: {total/n:.2f}°")

    print(f"\n=== HISTORIQUE DES LOGS ===")
    for log in logs[-15:]:
        time = log.get('time', '')[-8:]
        msg = log.get('message', '')
        typ = log.get('type', 'info')
        icon = {'info': ' ', 'success': '+', 'correction': '>', 'warning': '!', 'error': 'X'}.get(typ, '?')
        print(f"[{icon}] {time} {msg}")
```

### 4. Graphique ASCII des Corrections

```python
# Extraire les corrections des logs
corrections = []
for log in logs:
    if log.get('type') == 'correction':
        msg = log.get('message', '')
        # Extraire le delta (ex: "Correction +0.5°")
        import re
        match = re.search(r'([+-]?\d+\.?\d*)°', msg)
        if match:
            corrections.append(float(match.group(1)))

if corrections:
    print("\n=== GRAPHIQUE DES CORRECTIONS ===")
    max_val = max(abs(c) for c in corrections)
    scale = 20 / max_val if max_val > 0 else 1

    for i, c in enumerate(corrections[-20:]):  # 20 dernieres
        bar_len = int(abs(c) * scale)
        if c >= 0:
            bar = ' ' * 20 + '|' + '>' * bar_len
        else:
            bar = ' ' * (20 - bar_len) + '<' * bar_len + '|'
        print(f"{i+1:2d}. {bar} {c:+.2f}°")

    print(f"\nMin: {min(corrections):+.2f}° | Max: {max(corrections):+.2f}° | Moy: {sum(corrections)/len(corrections):+.2f}°")
```

### 5. Distribution des Modes

```python
# Analyser la distribution des modes depuis les logs
mode_times = {'NORMAL': 0, 'CRITICAL': 0, 'CONTINUOUS': 0}
current_mode = 'NORMAL'

for log in logs:
    msg = log.get('message', '').upper()
    if 'NORMAL' in msg:
        current_mode = 'NORMAL'
    elif 'CRITICAL' in msg:
        current_mode = 'CRITICAL'
    elif 'CONTINUOUS' in msg:
        current_mode = 'CONTINUOUS'
    # Incrementer (approximation)
    mode_times[current_mode] += 1

total = sum(mode_times.values()) or 1
print("\n=== DISTRIBUTION DES MODES ===")
for mode, count in mode_times.items():
    pct = count / total * 100
    bar = '#' * int(pct / 5)
    icon = {'NORMAL': '🟢', 'CRITICAL': '🟠', 'CONTINUOUS': '🔴'}.get(mode, '')
    print(f"{icon} {mode:<12} {bar:<20} {pct:5.1f}%")
```

### 6. Analyse de la Derive

```python
# Calculer la derive moyenne par heure
if corrections and len(logs) > 1:
    # Temps total approximatif
    first_time = logs[0].get('time', '')
    last_time = logs[-1].get('time', '')

    # Si timestamps disponibles
    try:
        from datetime import datetime
        t1 = datetime.fromisoformat(first_time.replace('Z', '+00:00'))
        t2 = datetime.fromisoformat(last_time.replace('Z', '+00:00'))
        duration_hours = (t2 - t1).total_seconds() / 3600

        if duration_hours > 0:
            total_movement = sum(abs(c) for c in corrections)
            drift_per_hour = total_movement / duration_hours
            print(f"\n=== ANALYSE DE DERIVE ===")
            print(f"Duree session: {duration_hours:.1f}h")
            print(f"Mouvement total: {total_movement:.1f}°")
            print(f"Derive moyenne: {drift_per_hour:.1f}°/h")

            # Interpretation
            if drift_per_hour < 5:
                print("Derive FAIBLE - Excellent suivi")
            elif drift_per_hour < 15:
                print("Derive NORMALE - Suivi correct")
            else:
                print("Derive ELEVEE - Verifier mecanique/calibration")
    except:
        pass
```

### 7. Export du Rapport

```python
import json

rapport = {
    'session_id': '$ARGUMENTS' or 'current',
    'object': session.get('tracking_object'),
    'position_finale': session.get('position'),
    'mode_final': session.get('mode'),
    'stats': {
        'total_corrections': info.get('total_corrections', 0),
        'total_degrees': info.get('total_correction_degrees', 0),
        'azimut': info.get('azimut'),
        'altitude': info.get('altitude')
    },
    'corrections': corrections if 'corrections' in dir() else [],
    'mode_distribution': mode_times if 'mode_times' in dir() else {}
}

# Sauvegarder
output_file = f"logs/rapport_session_{rapport['session_id']}.json"
with open(output_file, 'w') as f:
    json.dump(rapport, f, indent=2)
print(f"\nRapport sauvegarde: {output_file}")
```

### 8. Resume Final

```
=== RAPPORT SESSION ===

Session: [ID]
Objet: [nom]
Duree: [X]h [Y]min

Position:
  Initiale: X°
  Finale: X°
  Cible: X°

Corrections:
  Nombre: N
  Total: X°
  Moyenne: X°

Modes:
  NORMAL: X%
  CRITICAL: X%
  CONTINUOUS: X%

Derive: X°/h

Qualite: [EXCELLENT/BON/MOYEN/FAIBLE]

Recommandations:
  - ...
```

### Comparaison avec Sessions Precedentes

Si plusieurs sessions disponibles pour le meme objet :

```python
# Comparer avec sessions precedentes du meme objet
same_object_sessions = [s for s in sessions if s['object'] == session.get('tracking_object')]
if len(same_object_sessions) > 1:
    print("\n=== COMPARAISON HISTORIQUE ===")
    print(f"Sessions pour {session.get('tracking_object')}: {len(same_object_sessions)}")

    avg_corrections = sum(s['corrections'] for s in same_object_sessions) / len(same_object_sessions)
    current_corrections = info.get('total_corrections', 0)

    if current_corrections < avg_corrections * 0.8:
        print(f"Cette session: MEILLEURE que la moyenne ({current_corrections} vs {avg_corrections:.0f})")
    elif current_corrections > avg_corrections * 1.2:
        print(f"Cette session: MOINS BONNE que la moyenne ({current_corrections} vs {avg_corrections:.0f})")
    else:
        print(f"Cette session: DANS LA MOYENNE ({current_corrections} vs {avg_corrections:.0f})")
```
