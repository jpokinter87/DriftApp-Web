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

## Mise a jour v6.16 : rampe pre-calculee

### Ce qui change

Les delais des phases d'acceleration et de deceleration sont desormais
calcules **avant** le mouvement, au lieu d'etre evalues a chaque pas
(`Ramp.get_delay()` fait trois `exp()`, ce qui coutait plusieurs dizaines de
microsecondes par pas en MicroPython). La boucle d'emission ne fait plus que
remplir le FIFO du PIO.

Consequence : la rampe peut atteindre la meme cadence que la croisiere. Tant
que ce n'etait pas le cas, demander une vitesse de croisiere elevee creait une
marche de vitesse a la sortie de la rampe — le moteur decrochait, ce qui a
longtemps ete pris pour une limite du driver.

### Le flash est neutre a 260 us

La sequence d'impulsions envoyee au PIO est **strictement identique** a celle
de la version precedente (verifie sur les phases accel et decel, pour des
mouvements de 250 a 20000 pas, de 124 a 260 us — voir
`tests/test_firmware_ramp.py::TestEquivalenceAncienneRampe`). Seul le moment
du calcul change, pas les valeurs.

Autrement dit : apres le flash, la coupole se comporte exactement comme avant
tant que `motor_driver.delay_us` reste a 260. La vitesse ne bouge que si on la
change explicitement.

### Retour arriere

Garder une copie des trois fichiers avant le flash :

```bash
mkdir -p ~/firmware_backup
mpremote cp :main.py ~/firmware_backup/main.py
mpremote cp :step_generator.py ~/firmware_backup/step_generator.py
mpremote cp :ramp.py ~/firmware_backup/ramp.py
```

Pour revenir en arriere, recopier ces trois fichiers vers le Pico (meme
commande dans l'autre sens) et redemarrer le Pico.

### Changer la vitesse

La vitesse n'est plus en dur dans le code : elle vit dans
`data/config.json` → `motor_driver.delay_us` (microsecondes par pas),
editable depuis la page **Configuration → Avance** de l'interface web.
Un redemarrage des services est necessaire pour qu'elle soit prise en compte
(bouton « Redemarrer les services » de la meme page).

**Ne pas descendre au juge.** Mesurer d'abord la vitesse reellement atteinte,
palier par palier, avec :

```bash
python3 scripts/diagnostics/calibration_vitesse_encodeur.py --dry-run  # plan
python3 scripts/diagnostics/calibration_vitesse_encodeur.py            # mesure
```

Le script lit la position sur l'encodeur EMS22A et compare la vitesse obtenue
a la vitesse demandee : il s'arrete au premier palier ou la coupole ne suit
plus, et recommande une valeur avec 15 % de marge. Il ne modifie ni la
configuration ni les services.

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
