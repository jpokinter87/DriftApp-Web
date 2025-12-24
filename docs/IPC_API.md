# API IPC - Communication Inter-Processus DriftApp

**Version**: 4.5
**Date**: Décembre 2025

---

## Vue d'ensemble

DriftApp utilise une architecture 3-processus communiquant via fichiers JSON dans `/dev/shm/` (RAM partagée Linux).

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Encoder Daemon │     │   Motor Service  │     │     Django      │
│  (ems22d_*.py)  │     │ (motor_service)  │     │   (port 8000)   │
└────────┬────────┘     └────────┬─────────┘     └────────┬────────┘
         │                       │                        │
         │ ÉCRIT                 │ LIT                    │
         ▼                       ▼                        │
┌──────────────────────────────────────┐                  │
│   /dev/shm/ems22_position.json       │                  │
│   Position encodeur calibrée         │                  │
└──────────────────────────────────────┘                  │
                                                          │
                        ┌─────────────────────────────────┘
                        │ ÉCRIT
                        ▼
         ┌──────────────────────────────┐
         │ /dev/shm/motor_command.json  │
         │ Commandes Django → Motor     │
         └──────────────────────────────┘
                        │
                        │ LIT
                        ▼
         ┌──────────────────────────────┐
         │   Motor Service traite       │
         └──────────────────────────────┘
                        │
                        │ ÉCRIT
                        ▼
         ┌──────────────────────────────┐
         │ /dev/shm/motor_status.json   │
         │ État Motor → Django          │
         └──────────────────────────────┘
                        │
                        │ LIT
                        ▼
         ┌──────────────────────────────┐
         │   Django affiche à l'UI      │
         └──────────────────────────────┘
```

---

## Fichiers IPC

| Fichier | Producteur | Consommateur | Fréquence |
|---------|------------|--------------|-----------|
| `ems22_position.json` | Encoder Daemon | Motor Service | 50 Hz |
| `motor_command.json` | Django | Motor Service | À la demande |
| `motor_status.json` | Motor Service | Django | 20 Hz |

---

## 1. Fichier Encodeur (`ems22_position.json`)

### Format

```json
{
  "ts": 1735056000.123,
  "angle": 127.45,
  "raw": 512,
  "status": "OK",
  "calibrated": true
}
```

### Champs

| Champ | Type | Description |
|-------|------|-------------|
| `ts` | float | Timestamp Unix (secondes.millisecondes) |
| `angle` | float | Angle de la coupole en degrés [0, 360) |
| `raw` | int | Valeur brute du capteur (0-1023 pour 10 bits) |
| `status` | string | "OK", "INIT", "SPI ERROR", etc. |
| `calibrated` | bool | `true` si le capteur a été recalé via microswitch |

### Statuts possibles

| Statut | Description |
|--------|-------------|
| `OK` | Lecture normale |
| `INIT` | Démarrage, pas encore calibré |
| `CALIBRATING` | Recalage en cours |
| `SPI ERROR` | Erreur de communication SPI |
| `JUMP FILTERED` | Saut de position anormal ignoré |

---

## 2. Fichier Commande (`motor_command.json`)

### Format général

```json
{
  "id": "uuid-unique",
  "command": "type_commande",
  ...paramètres spécifiques...
}
```

Le champ `id` est un UUID généré par Django pour éviter le retraitement.

### Commandes disponibles

#### GOTO - Déplacement absolu

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "command": "goto",
  "angle": 180.0,
  "speed": 0.002
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `angle` | float | Oui | Position cible en degrés [0, 360) |
| `speed` | float | Non | Délai moteur (secondes). Défaut: 0.00015 |

**Comportement**:
- `|delta| > 3°`: Rotation directe fluide + correction finale
- `|delta| ≤ 3°`: Feedback précis avec boucle fermée

#### JOG - Déplacement relatif

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "command": "jog",
  "delta": -5.0,
  "speed": 0.002
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `delta` | float | Oui | Déplacement relatif en degrés (+/- = sens) |
| `speed` | float | Non | Délai moteur (secondes). Défaut: 0.00015 |

**Comportement**: Rotation directe SANS feedback (fluidité maximale).

#### STOP - Arrêt d'urgence

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440002",
  "command": "stop"
}
```

**Comportement**: Arrête immédiatement tout mouvement et le suivi.

#### CONTINUOUS - Mouvement continu

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440003",
  "command": "continuous",
  "direction": "cw"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `direction` | string | Oui | `"cw"` (horaire) ou `"ccw"` (anti-horaire) |

**Comportement**: Mouvement continu jusqu'à `stop`.

#### TRACKING_START - Démarrer le suivi

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440004",
  "command": "tracking_start",
  "object": "M13"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `object` | string | Oui | Nom de l'objet céleste (M13, Vega, Mars, etc.) |

**Comportement**:
1. Recherche l'objet dans le catalogue
2. Calcule les coordonnées horizontales (Az/Alt)
3. Effectue un GOTO initial vers la position cible
4. Active le suivi adaptatif

#### TRACKING_STOP - Arrêter le suivi

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440005",
  "command": "tracking_stop"
}
```

#### STATUS - Demande d'état

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440006",
  "command": "status"
}
```

**Comportement**: Force une mise à jour immédiate du fichier status.

---

## 3. Fichier Status (`motor_status.json`)

### Format

```json
{
  "status": "tracking",
  "position": 127.45,
  "target": null,
  "progress": 0,
  "mode": "normal",
  "tracking_object": "M13",
  "tracking_pending": false,
  "goto_info": null,
  "tracking_info": {
    "azimut": 180.5,
    "altitude": 45.2,
    "position_cible": 185.3,
    "remaining_seconds": 45,
    "interval_sec": 60,
    "total_corrections": 12,
    "total_correction_degrees": 3.5,
    "mode_icon": "🟢"
  },
  "tracking_logs": [
    {
      "time": "2025-12-24T22:30:00",
      "message": "Correction +0.5°",
      "type": "correction"
    }
  ],
  "error": null,
  "error_timestamp": null,
  "simulation": false,
  "last_update": "2025-12-24T22:30:00.123456"
}
```

### Champs principaux

| Champ | Type | Description |
|-------|------|-------------|
| `status` | string | État actuel du service (voir tableau) |
| `position` | float | Position actuelle en degrés [0, 360) |
| `target` | float/null | Position cible si en mouvement |
| `progress` | int | Progression en % (0-100) |
| `mode` | string | Mode adaptatif (normal/critical/continuous) |
| `tracking_object` | string/null | Nom de l'objet suivi |
| `error` | string/null | Message d'erreur si applicable |
| `simulation` | bool | `true` si en mode simulation |
| `last_update` | string | Timestamp ISO 8601 |

### Valeurs de `status`

| Statut | Description |
|--------|-------------|
| `idle` | En attente de commandes |
| `moving` | Mouvement en cours (GOTO/JOG/Continu) |
| `initializing` | GOTO initial du tracking en cours |
| `tracking` | Suivi actif d'un objet céleste |
| `error` | Erreur (recovery auto après 10s) |
| `stopped` | Service arrêté |

### Champs de suivi (`tracking_info`)

| Champ | Type | Description |
|-------|------|-------------|
| `azimut` | float | Azimut calculé de l'objet |
| `altitude` | float | Altitude calculée de l'objet |
| `position_cible` | float | Position coupole calculée via abaque |
| `remaining_seconds` | int | Secondes avant prochaine vérification |
| `interval_sec` | int | Intervalle de vérification (mode adaptatif) |
| `total_corrections` | int | Nombre de corrections depuis le début |
| `total_correction_degrees` | float | Cumul des mouvements en degrés |
| `mode_icon` | string | Emoji du mode (🟢/🟠/🔴) |

### Logs de suivi (`tracking_logs`)

| Champ | Type | Description |
|-------|------|-------------|
| `time` | string | Timestamp ISO 8601 |
| `message` | string | Message du log |
| `type` | string | `info`, `success`, `correction`, `warning`, `error` |

---

## Sécurité et Synchronisation

### Verrous fcntl

Tous les accès fichiers utilisent des verrous `fcntl` pour éviter les race conditions:

```python
# Lecture (verrou partagé - plusieurs lecteurs OK)
fcntl.flock(f.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)

# Écriture (verrou exclusif - bloque tout accès)
fcntl.flock(f.fileno(), fcntl.LOCK_EX)
```

### Écriture atomique

L'écriture utilise un pattern atomique:
1. Écrire dans fichier `.tmp`
2. `fsync()` pour forcer sur disque
3. `rename()` atomique (POSIX)

```python
tmp_file = STATUS_FILE.with_suffix('.tmp')
with open(tmp_file, 'w') as f:
    f.write(json.dumps(data))
    f.flush()
    os.fsync(f.fileno())
tmp_file.rename(STATUS_FILE)  # Atomique
```

---

## Exemples d'utilisation

### Python - Envoyer une commande

```python
import json
import uuid
from pathlib import Path

COMMAND_FILE = Path("/dev/shm/motor_command.json")

def send_command(cmd_type: str, **params):
    command = {
        "id": str(uuid.uuid4()),
        "command": cmd_type,
        **params
    }
    COMMAND_FILE.write_text(json.dumps(command))

# Exemples
send_command("goto", angle=180.0)
send_command("jog", delta=-10.0)
send_command("tracking_start", object="M13")
send_command("stop")
```

### Python - Lire le status

```python
import json
from pathlib import Path

STATUS_FILE = Path("/dev/shm/motor_status.json")

def read_status():
    if not STATUS_FILE.exists():
        return None
    try:
        return json.loads(STATUS_FILE.read_text())
    except json.JSONDecodeError:
        return None

# Exemple
status = read_status()
if status:
    print(f"Position: {status['position']:.1f}°")
    print(f"Status: {status['status']}")
```

### Bash - Commandes rapides

```bash
# GOTO vers 90°
echo '{"id":"1","command":"goto","angle":90}' > /dev/shm/motor_command.json

# Lire la position
jq .position /dev/shm/motor_status.json

# Lire l'angle encodeur
jq .angle /dev/shm/ems22_position.json
```

---

## Codes d'erreur et Recovery

### Erreurs courantes

| Code | Description | Recovery |
|------|-------------|----------|
| `JSONDecodeError` | Fichier corrompu | Ignoré, relecture suivante |
| `BlockingIOError` | Fichier verrouillé | Réessayer au cycle suivant |
| `FileNotFoundError` | Fichier absent | Créé au prochain write |

### Recovery automatique

Le Motor Service remet automatiquement le status à `idle` après 10 secondes en état `error`:

```python
ERROR_RECOVERY_TIMEOUT = 10.0  # secondes
```

---

## Diagramme de séquence - GOTO

```
Django                Motor Service              Encoder Daemon
  │                        │                           │
  │ write command.json     │                           │
  │──────────────────────>│                            │
  │                        │                           │
  │                        │ read command.json         │
  │                        │<─────────────────────────>│
  │                        │                           │
  │                        │ set status='moving'       │
  │                        │─────────┐                 │
  │                        │<────────┘                 │
  │                        │                           │
  │                        │ rotation moteur           │
  │                        │═══════════════════════>   │
  │                        │                           │
  │                        │ read position.json        │
  │                        │<─────────────────────────│
  │                        │                           │
  │                        │ set status='idle'         │
  │                        │─────────┐                 │
  │                        │<────────┘                 │
  │                        │                           │
  │ read status.json       │                           │
  │<──────────────────────│                            │
  │                        │                           │
```

---

*Document généré par Claude Code - Décembre 2025*
