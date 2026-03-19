# Firmware RP2040 — Pilotage moteur DM556T

Firmware MicroPython pour Raspberry Pi Pico (RP2040).
Genere les impulsions STEP/DIR via PIO state machines avec precision 8 ns.

## Pre-requis

- Raspberry Pi Pico (RP2040) — avec ou sans Wi-Fi
- Cable micro-USB **donnees** (pas juste alimentation)
- 3 fils Dupont femelle-femelle (STEP, DIR, GND)

## Etape 1 : Flasher MicroPython sur le Pico

1. **Telecharger le firmware MicroPython** :
   - Aller sur https://micropython.org/download/RPI_PICO/
   - Telecharger le fichier `.uf2` le plus recent (ex: `RPI_PICO-20241025-v1.24.1.uf2`)
   - Pour Pi Pico W : https://micropython.org/download/RPI_PICO_W/

2. **Mettre le Pico en mode bootloader** :
   - Maintenir le bouton **BOOTSEL** (sur le Pico) enfonce
   - Brancher le cable USB au Raspberry Pi 5 en maintenant BOOTSEL
   - Relacher BOOTSEL apres 2 secondes
   - Le Pico apparait comme une cle USB nommee **RPI-RP2**

3. **Copier le firmware** :
   ```bash
   # Sur le Raspberry Pi 5
   cp RPI_PICO-*.uf2 /media/pi/RPI-RP2/
   ```
   Le Pico redemarre automatiquement. La cle USB disparait.

4. **Verifier** :
   ```bash
   ls /dev/ttyACM*
   # Doit afficher : /dev/ttyACM0
   ```

## Etape 2 : Copier le firmware DriftApp

### Option A : avec mpremote (recommande)

```bash
# Installer mpremote
pip install mpremote

# Copier les 3 fichiers depuis le dossier firmware/
cd /chemin/vers/Dome_web_v4_6/firmware/
mpremote cp main.py :main.py
mpremote cp step_generator.py :step_generator.py
mpremote cp ramp.py :ramp.py

# Le Pico redemarre et execute main.py automatiquement
```

### Option B : avec Thonny IDE

1. Installer Thonny : `sudo apt install thonny`
2. Ouvrir Thonny, selectionner **MicroPython (Raspberry Pi Pico)** en bas
3. Ouvrir chaque fichier (`main.py`, `step_generator.py`, `ramp.py`)
4. **Fichier → Enregistrer sous → Raspberry Pi Pico** pour chaque fichier
5. Redemarrer le Pico (debrancher/rebrancher USB)

## Etape 3 : Branchements

```
Raspberry Pi 5              Pi Pico (RP2040)                DM556T
                        +---------------------+
  USB =================>| USB (alimentation   |
  (donnees + 5V)        |      + serie)       |
                        |                     |
                        | GP2 ---------------------------> PUL+
                        | GP3 ---------------------------> DIR+
                        | GND (pin 38) ---------------------> PUL- / DIR-
                        +---------------------+
```

### Connexions (3 fils)

| Pi Pico         | DM556T  | Role          |
|-----------------|---------|---------------|
| **GP2** (pin 4) | **PUL+** | Signal STEP   |
| **GP3** (pin 5) | **DIR+** | Direction     |
| **GND** (pin 38)| **PUL-** et **DIR-** | Masse commune |

### Precautions

- **Masse commune obligatoire** : le GND du Pico doit etre relie au GND du DM556T
- **Fils courts** : garder < 30 cm entre Pico et DM556T
- **Ne PAS alimenter le Pico par le DM556T** — utiliser uniquement l'USB du Pi 5
- **Deconnecter les fils GPIO** du Pi 5 vers le DM556T (ils ne sont plus utilises)

## Etape 4 : Verification

### Test rapide via terminal

```bash
# Ouvrir un terminal serie
screen /dev/ttyACM0 115200

# Taper (suivi de Entree) :
STATUS
# Reponse attendue : IDLE

# Test mouvement (100 pas, direction CW, 2000 us, sans rampe) :
MOVE 100 1 2000 NONE
# Reponse attendue : OK 100

# Quitter screen : Ctrl-A puis K puis Y
```

### Test via mpremote

```bash
# Verifier que le Pico repond
echo "STATUS" | mpremote exec "import sys; sys.stdout.write(sys.stdin.readline())"
```

## Depannage

### Le Pico n'apparait pas comme /dev/ttyACM0

- Verifier le cable : doit etre un cable **donnees** (pas juste charge)
- Essayer un autre port USB sur le Pi 5
- Verifier les permissions : `sudo usermod -a -G dialout $USER` puis re-login

### "Permission denied" sur /dev/ttyACM0

```bash
sudo usermod -a -G dialout $USER
# Se deconnecter et reconnecter pour appliquer
```

### Le moteur ne tourne pas

1. Verifier que le DM556T est sous tension
2. Verifier les fils GP2→PUL+, GP3→DIR+, GND→PUL-/DIR-
3. Tester avec un mouvement lent : `MOVE 200 1 5000 NONE`
4. Si toujours rien : verifier que le DM556T declenche en 3.3V
   (si non, ajouter un level-shifter 3.3V→5V)

### Reset du Pico

Pour reflasher ou repartir de zero :
1. Maintenir BOOTSEL + brancher USB
2. Le Pico redevient une cle USB (RPI-RP2)
3. Recommencer depuis l'Etape 1

## Protocole serie (reference)

| Commande | Format | Reponse |
|----------|--------|---------|
| Mouvement | `MOVE <steps> <dir> <delay_us> <ramp>\n` | `OK <steps>\n` |
| Arret | `STOP\n` | `STOPPED <steps>\n` |
| Statut | `STATUS\n` | `IDLE\n` ou `MOVING <remaining>\n` |

- `dir` : 0 = anti-horaire, 1 = horaire
- `delay_us` : delai entre pas en microsecondes (ex: 150 pour CONTINUOUS)
- `ramp` : SCURVE, LINEAR, ou NONE
