---
description: Analyse des logs DriftApp
category: utilities-debugging
argument-hint: [optionnel] source (motor, encoder, django, all) ou periode (today, 1h, 24h)
---

# Analyse des Logs DriftApp

Analyse les logs pour detecter problemes et patterns.

## Instructions

Tu vas analyser les logs du systeme : **$ARGUMENTS**

### 1. Vue d'Ensemble des Logs

```bash
echo "=== SOURCES DE LOGS ==="

# Logs systemd
echo -e "\nServices systemd:"
echo -n "  ems22d: "
sudo journalctl -u ems22d --no-pager -n 1 2>/dev/null && echo "disponible" || echo "non disponible"
echo -n "  motor_service: "
sudo journalctl -u motor_service --no-pager -n 1 2>/dev/null && echo "disponible" || echo "non disponible"

# Logs fichiers
echo -e "\nFichiers logs:"
ls -la logs/*.log 2>/dev/null | tail -5 || echo "  Aucun fichier log"

# Taille totale
echo -e "\nEspace utilise:"
du -sh logs/ 2>/dev/null || echo "  N/A"
```

### 2. Logs Motor Service (Recents)

```bash
echo "=== LOGS MOTOR SERVICE (derniere heure) ==="

sudo journalctl -u motor_service --since "1 hour ago" --no-pager 2>/dev/null | tail -50 || \
  tail -50 logs/motor_service*.log 2>/dev/null || \
  echo "Aucun log disponible"
```

### 3. Logs Encoder Daemon

```bash
echo "=== LOGS ENCODER DAEMON ==="

sudo journalctl -u ems22d --since "1 hour ago" --no-pager 2>/dev/null | tail -30 || \
  echo "Logs encoder non disponibles via systemd"
```

### 4. Analyse des Erreurs

```bash
echo "=== ERREURS DETECTEES ==="

# Erreurs Motor Service
echo -e "\nMotor Service:"
sudo journalctl -u motor_service --since "24 hours ago" --no-pager 2>/dev/null | \
  grep -iE "error|exception|fail|critical" | tail -20 || echo "  Aucune erreur"

# Erreurs Encoder
echo -e "\nEncoder Daemon:"
sudo journalctl -u ems22d --since "24 hours ago" --no-pager 2>/dev/null | \
  grep -iE "error|exception|fail|spi" | tail -10 || echo "  Aucune erreur"

# Erreurs Django
echo -e "\nDjango:"
grep -iE "error|exception|traceback" logs/django*.log 2>/dev/null | tail -10 || echo "  Aucune erreur"
```

### 5. Analyse des Patterns

```python
import sys
import re
from collections import Counter
from datetime import datetime

# Lire les logs motor_service
logs = []
try:
    import subprocess
    result = subprocess.run(
        ['sudo', 'journalctl', '-u', 'motor_service', '--since', '24 hours ago', '--no-pager'],
        capture_output=True, text=True, timeout=10
    )
    logs = result.stdout.split('\n')
except:
    pass

if not logs:
    print("Impossible de lire les logs")
    sys.exit(0)

# Analyser les patterns
patterns = {
    'corrections': r'correction|correcting',
    'goto': r'goto|going to',
    'jog': r'jog',
    'tracking': r'tracking|track',
    'errors': r'error|exception|fail',
    'encoder': r'encoder|position',
    'calibration': r'calibrat'
}

counts = {k: 0 for k in patterns}
for line in logs:
    line_lower = line.lower()
    for name, pattern in patterns.items():
        if re.search(pattern, line_lower):
            counts[name] += 1

print("=== ANALYSE DES PATTERNS (24h) ===")
print()
for name, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
    bar = '#' * min(count // 5, 30)
    print(f"{name:<15} {count:>5} {bar}")
```

### 6. Timeline des Evenements

```python
import subprocess
import re
from datetime import datetime

# Lire les logs
result = subprocess.run(
    ['sudo', 'journalctl', '-u', 'motor_service', '--since', '6 hours ago', '--no-pager', '-o', 'short-iso'],
    capture_output=True, text=True, timeout=10
)

print("=== TIMELINE EVENEMENTS (6h) ===")
print()

events = []
for line in result.stdout.split('\n'):
    # Detecter les evenements importants
    if any(kw in line.lower() for kw in ['start', 'stop', 'error', 'tracking', 'goto', 'calibrat']):
        # Extraire timestamp
        match = re.match(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', line)
        if match:
            ts = match.group(1)
            # Simplifier le message
            msg = line[match.end():].strip()[:60]
            events.append(f"{ts[-8:]} | {msg}")

for event in events[-30:]:
    print(event)
```

### 7. Statistiques de Suivi

```python
import subprocess
import re
from collections import defaultdict

result = subprocess.run(
    ['sudo', 'journalctl', '-u', 'motor_service', '--since', '24 hours ago', '--no-pager'],
    capture_output=True, text=True, timeout=10
)

print("=== STATISTIQUES SUIVI (24h) ===")
print()

# Compter les corrections
corrections = []
for line in result.stdout.split('\n'):
    # Chercher les corrections (ex: "Correction +0.5°")
    match = re.search(r'correction\s+([+-]?\d+\.?\d*)°?', line.lower())
    if match:
        corrections.append(float(match.group(1)))

if corrections:
    print(f"Corrections effectuees: {len(corrections)}")
    print(f"Correction moyenne: {sum(corrections)/len(corrections):.2f}°")
    print(f"Correction min: {min(corrections):.2f}°")
    print(f"Correction max: {max(corrections):.2f}°")
    print(f"Mouvement total: {sum(abs(c) for c in corrections):.1f}°")

    # Distribution
    print("\nDistribution:")
    small = sum(1 for c in corrections if abs(c) < 0.5)
    medium = sum(1 for c in corrections if 0.5 <= abs(c) < 2)
    large = sum(1 for c in corrections if abs(c) >= 2)
    print(f"  < 0.5°:  {small} ({small*100/len(corrections):.0f}%)")
    print(f"  0.5-2°:  {medium} ({medium*100/len(corrections):.0f}%)")
    print(f"  > 2°:    {large} ({large*100/len(corrections):.0f}%)")
else:
    print("Aucune correction trouvee dans les logs")
```

### 8. Detection d'Anomalies

```python
import subprocess
import re
from datetime import datetime, timedelta

result = subprocess.run(
    ['sudo', 'journalctl', '-u', 'motor_service', '--since', '24 hours ago', '--no-pager', '-o', 'short-iso'],
    capture_output=True, text=True, timeout=10
)

print("=== DETECTION D'ANOMALIES ===")
print()

anomalies = []

lines = result.stdout.split('\n')
prev_time = None

for line in lines:
    # Extraire timestamp
    match = re.match(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', line)
    if not match:
        continue

    try:
        current_time = datetime.fromisoformat(match.group(1))
    except:
        continue

    # Detecter les gaps (> 5 min sans log)
    if prev_time and (current_time - prev_time).total_seconds() > 300:
        gap_minutes = (current_time - prev_time).total_seconds() / 60
        anomalies.append(f"Gap de {gap_minutes:.0f} min a {current_time.strftime('%H:%M')}")

    prev_time = current_time

    # Detecter les erreurs
    if 'error' in line.lower() or 'exception' in line.lower():
        anomalies.append(f"Erreur a {current_time.strftime('%H:%M')}: {line[-50:]}")

    # Detecter les redemarrages
    if 'started' in line.lower() or 'starting' in line.lower():
        anomalies.append(f"Redemarrage a {current_time.strftime('%H:%M')}")

if anomalies:
    print(f"Anomalies detectees: {len(anomalies)}")
    print()
    for a in anomalies[:20]:
        print(f"  - {a}")
else:
    print("Aucune anomalie detectee")
```

### 9. Logs en Temps Reel

```bash
echo "=== LOGS TEMPS REEL ==="
echo "Appuyer Ctrl+C pour arreter"
echo ""

# Suivre les logs motor_service
sudo journalctl -u motor_service -f --no-pager
```

### 10. Export des Logs

```bash
echo "=== EXPORT LOGS ==="

# Creer archive
DATE=$(date +%Y%m%d_%H%M%S)
EXPORT_DIR="logs/export_$DATE"
mkdir -p "$EXPORT_DIR"

# Exporter Motor Service (24h)
sudo journalctl -u motor_service --since "24 hours ago" --no-pager > "$EXPORT_DIR/motor_service.log" 2>/dev/null

# Exporter Encoder Daemon (24h)
sudo journalctl -u ems22d --since "24 hours ago" --no-pager > "$EXPORT_DIR/ems22d.log" 2>/dev/null

# Copier logs Django
cp logs/django*.log "$EXPORT_DIR/" 2>/dev/null

# Compresser
tar -czf "logs/export_$DATE.tar.gz" -C logs "export_$DATE"
rm -rf "$EXPORT_DIR"

echo "Logs exportes: logs/export_$DATE.tar.gz"
ls -lh "logs/export_$DATE.tar.gz"
```

### 11. Nettoyage des Logs

```bash
echo "=== NETTOYAGE LOGS ==="

# Taille avant
echo "Espace avant:"
du -sh logs/

# Supprimer logs > 7 jours
find logs/ -name "*.log" -mtime +7 -delete 2>/dev/null
find logs/ -name "*.tar.gz" -mtime +30 -delete 2>/dev/null

# Rotation journalctl
sudo journalctl --vacuum-time=7d 2>/dev/null

# Taille apres
echo "Espace apres:"
du -sh logs/
```

### Resume

```
=== COMMANDES LOGS ===

Vue rapide:
  /logs              # Erreurs recentes
  /logs motor        # Logs Motor Service
  /logs encoder      # Logs Encoder Daemon
  /logs django       # Logs Django

Analyse:
  /logs errors       # Toutes les erreurs
  /logs patterns     # Analyse des patterns
  /logs stats        # Statistiques suivi
  /logs anomalies    # Detection anomalies

Temps reel:
  /logs live         # Suivi en direct

Maintenance:
  /logs export       # Exporter les logs
  /logs clean        # Nettoyer les anciens logs
```
