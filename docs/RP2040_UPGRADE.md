# Upgrade RP2040 — Elimination du jitter moteur

> **Date** : Mars 2026
> **Statut** : Planifié
> **Objectif** : Remplacer le pilotage GPIO bit-bang Python par un microcontrôleur RP2040 dédié à la génération d'impulsions STEP/DIR avec timing matériel.

---

## Problème constaté

L'utilisateur observe un **manque de souplesse du régime moteur** qui "souffre" par moments.

### Cause racine

Le pilotage actuel repose sur `time.sleep()` en Python userspace (`moteur.py:292-323`) :

```python
self._lgpio_write(self.gpio_handle, self.STEP, 1)
time.sleep(delai / 2)      # ← jitter 0.5 à 2 ms
self._lgpio_write(self.gpio_handle, self.STEP, 0)
time.sleep(delai / 2)      # ← jitter 0.5 à 2 ms
```

Sur Linux non-RT, le jitter typique de `time.sleep()` est de **0.5 à 2 ms** (scheduler, GIL, garbage collection, interruptions système). En mode CONTINUOUS, le délai cible est **0.15 ms** — le jitter est donc potentiellement **10x supérieur au signal utile**.

La rampe S-curve (`acceleration_ramp.py`) calcule des délais élégants, mais `time.sleep()` ne les respecte pas avec la précision nécessaire.

### Alternative pigpio écartée

La bibliothèque `pigpio` utilise le DMA du BCM283x pour un timing matériel (~5 µs de précision), mais elle est **incompatible avec le Raspberry Pi 5** (nouveau southbridge RP1, accès `/dev/mem` différent). Le projet pigpio est en sommeil sans plan de support Pi 5.

---

## Solution retenue : microcontrôleur RP2040

Insérer un **Raspberry Pi Pico (RP2040)** entre le Raspberry Pi 5 et le driver DM556T. Le Pi envoie des commandes série de haut niveau, le RP2040 génère les impulsions STEP/DIR via ses **PIO state machines** avec une résolution de **8 ns** (125 MHz).

### Pourquoi ça s'intègre bien

L'architecture 3 processus existante est déjà découplée :

```
Django ──► IPC ──► Motor Service ──► GPIO        (aujourd'hui)
Django ──► IPC ──► Motor Service ──► UART/USB ──► RP2040 ──► DM556T  (demain)
```

Le changement se concentre sur `moteur.py`. Tout le reste (feedback controller, tracking, IPC, Django) reste intact.

---

## Matériel à acquérir

### Essentiel (~10€)

| Composant | Prix approx. | Référence |
|-----------|-------------|-----------|
| **Raspberry Pi Pico** (sans Wi-Fi suffit) | ~4€ | RP2040, micro-USB |
| **Câble micro-USB → USB-A** | ~3€ | Données (pas juste alimentation) |
| **Fils Dupont femelle-femelle** | ~2€ | 3 fils (STEP, DIR, GND) |

> Le Pi Pico **W** (Wi-Fi) fonctionne aussi (même pinout, ~2€ de plus) mais le Wi-Fi n'est pas nécessaire.

### Optionnel

| Composant | Utilité |
|-----------|--------|
| Breadboard | Prototypage initial |
| Connecteur à vis 3 bornes | Montage définitif propre |
| Boîtier imprimé 3D pour Pico | Protection dans la coupole |
| Level-shifter 3.3V→5V (~1€) | Si le DM556T ne déclenche pas en 3.3V (rare) |

---

## Branchements

### Schéma actuel (à déconnecter)

```
Raspberry Pi 5          DM556T
  GPIO DIR ──────────► DIR+
  GPIO STEP ─────────► PUL+
  GND ───────────────► DIR- / PUL-
```

### Nouveau schéma

```
Raspberry Pi 5              Pi Pico (RP2040)                DM556T
                        ┌─────────────────────┐
  USB ════════════════► │ USB (alimentation    │
  (données + 5V)        │      + série)        │
                        │                      │
                        │ GP2 ─────────────────────► PUL+
                        │ GP3 ─────────────────────► DIR+
                        │ GND (pin 38) ────────────► PUL- / DIR-
                        └─────────────────────┘
```

### Détail des connexions

**1. Raspberry Pi 5 → Pi Pico** : un seul câble USB

Le câble micro-USB fournit à la fois l'alimentation (5V) et la communication série. Le Pico apparaît comme `/dev/ttyACM0` sur le Pi — aucun driver à installer.

**2. Pi Pico → DM556T** : 3 fils

| Pi Pico | DM556T | Rôle |
|---------|--------|------|
| **GP2** | **PUL+** | Signal STEP |
| **GP3** | **DIR+** | Signal Direction |
| **GND** (pin 38) | **PUL-** et **DIR-** | Masse commune |

Les GPIO du Pico sont en 3.3V, ce qui est suffisant pour les entrées optoisolées du DM556T (seuil typique ~3V). Si le DM556T ne déclenche pas de façon fiable, un level-shifter 3.3V→5V à ~1€ réglerait ça, mais en pratique les DM556T fonctionnent en 3.3V.

**3. GPIO du Pi 5 libérés** : les broches DIR et STEP ne sont plus utilisées pour le moteur et peuvent être réaffectées ou laissées libres.

### Précautions

- **Masse commune obligatoire** : le GND du Pico doit être relié au GND du DM556T. Sans ça, les signaux ne sont pas référencés et le moteur aura un comportement erratique.
- **Longueur des fils STEP/DIR** : garder court (<30 cm). Le DM556T a des entrées optoisolées donc c'est tolérant, mais au-delà d'1 m, préférer du câble blindé ou torsadé.
- **Ne pas alimenter le Pico par le 5V du DM556T** — utiliser uniquement l'USB du Pi. Ça isole proprement les deux alimentations (logique vs puissance).

---

## Protocole série (Pi ↔ Pico)

### Commandes (Pi → Pico)

```
MOVE <steps> <direction> <target_delay_us> <ramp_type>\n
```

| Champ | Type | Description |
|-------|------|-------------|
| `steps` | int | Nombre de pas à exécuter |
| `direction` | 0/1 | 0 = anti-horaire, 1 = horaire |
| `target_delay_us` | int | Délai cible entre pas en microsecondes |
| `ramp_type` | string | `SCURVE`, `LINEAR`, `NONE` |

Exemples :
```
MOVE 5000 1 150 SCURVE\n     # GOTO rapide, 5000 pas CW, 150µs, rampe S
MOVE 200 0 2000 NONE\n       # Petit ajustement, 200 pas CCW, 2ms, pas de rampe
STOP\n                        # Arrêt immédiat
STATUS\n                      # Interrogation état
```

### Réponses (Pico → Pi)

```
OK <steps_executed>\n         # Mouvement terminé
STOPPED <steps_done>\n        # Arrêt avant fin
ERROR <message>\n             # Erreur
BUSY\n                        # Mouvement en cours (si nouvelle commande reçue)
IDLE\n                        # Réponse à STATUS quand inactif
MOVING <steps_remaining>\n    # Réponse à STATUS pendant mouvement
```

---

## Impact sur le code DriftApp

### Fichiers à modifier

| Fichier | Nature du changement |
|---------|---------------------|
| `core/hardware/moteur.py` | `faire_un_pas()` et `rotation()` → commandes série au RP2040 |
| `core/hardware/acceleration_ramp.py` | Logique déplacée côté firmware RP2040 (ou envoyée comme profil) |
| `core/config/config.py` | Ajouter paramètre port série RP2040 (`/dev/ttyACM0`) |
| `data/config.json` | Ajouter section `rp2040` (port, baudrate) |

### Fichiers inchangés

Tout le reste de l'architecture reste intact :
- `services/motor_service.py` — boucle principale, handlers
- `services/command_handlers.py` — GOTO, JOG, Continuous, Tracking
- `core/hardware/feedback_controller.py` — boucle fermée
- `core/hardware/daemon_encoder_reader.py` — lecture encodeur
- `core/tracking/` — suivi astronomique complet
- `web/` — interface Django complète

### Nouveau répertoire

```
firmware/
├── main.py              # Firmware MicroPython pour Pi Pico
├── step_generator.py    # Module PIO pour génération d'impulsions
├── ramp.py              # Rampe S-curve côté RP2040
└── README.md            # Instructions flash du firmware
```

---

## Gains attendus

| Aspect | Avant (Python bit-bang) | Après (RP2040 PIO) |
|--------|------------------------|---------------------|
| Précision timing | ±0.5-2 ms | ±8 ns |
| Mode CONTINUOUS (0.15 ms) | Jitter > signal | Parfait |
| Mode CRITICAL (1 ms) | Jitter ~50-200% | Négligeable |
| Mode NORMAL (2 ms) | Jitter ~25-100% | Négligeable |
| Rampe S-curve | Théoriquement juste, mal exécutée | Fidèle au calcul |
| Charge CPU Pi 5 | Boucle `time.sleep()` intensive | Quasi nulle (série) |
| Protection anti-stall | Impossible | Possible (monitoring RP2040) |
