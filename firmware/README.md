# Firmware RP2040 — Pilotage moteur DM860T

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
# Installer mpremote (une seule fois). Sur Raspberry Pi OS, "pip install"
# est refuse (environnement Python gere par le systeme) : passer par pipx.
sudo apt install pipx
pipx install mpremote

# OBLIGATOIRE : arreter motor_service, qui garde le port du Pico ouvert.
# mpremote interrompt le firmware (Ctrl-C) : les deux se disputeraient le port.
sudo systemctl stop motor_service

# Copier les 3 fichiers depuis le dossier firmware/
cd ~/DriftApp/firmware/
mpremote cp main.py :main.py
mpremote cp step_generator.py :step_generator.py
mpremote cp ramp.py :ramp.py

# Debrancher/rebrancher le Pico (il execute main.py au demarrage),
# puis relancer le service
sudo systemctl start motor_service
```

**Ne jamais lancer `sudo mpremote`** : sudo ne trouve pas la commande
(installee par pipx dans `~/.local/bin`, hors du PATH de sudo), et les
fichiers copies appartiendraient a root. Un « Permission denied » se regle
autrement — voir [Depannage](#permission-denied-avec-mpremote).

### Option B : avec Thonny IDE

1. Installer Thonny : `sudo apt install thonny`
2. Ouvrir Thonny, selectionner **MicroPython (Raspberry Pi Pico)** en bas
3. Ouvrir chaque fichier (`main.py`, `step_generator.py`, `ramp.py`)
4. **Fichier → Enregistrer sous → Raspberry Pi Pico** pour chaque fichier
5. Redemarrer le Pico (debrancher/rebrancher USB)

## Mise a jour v6.19.1 : rampe douce aussi pour les mouvements lents

Retour terrain 27/09 apres le flash v6.19 : la fin d'un JOG de 1° (260 us)
restait brutale — l'ancienne rampe y perdait la moitie de la vitesse en
48 ms. **Tous les mouvements** utilisent desormais la rampe a acceleration
constante (meme acceleration que les mouvements rapides : 260 us atteints en
~0,9 s). Ils sont d'ailleurs un peu plus courts (JOG 1° : 2,8 s → 2,2 s).

Le **STOP reste immediat a 260 us et plus lent** : la calibration envoie un
STOP au microswitch 45° puis avance de 0,5° au plus (contacts de charge des
batteries) ; un STOP doux y ajouterait ~0,34°.

L'ancienne rampe est retiree du firmware. Flash : meme procedure que v6.19
(sauvegarde dans un nouveau dossier, par ex. `~/firmware_backup_v619`).

## Mise a jour v6.19 : rampe douce des mouvements rapides

### Ce qui change

Terrain 27/09/2026 : a 110 us, demarrages et arrets brutaux, et un STOP
coupait le moteur net. La rampe v4.5 interpole le *delai* sur 500 pas : la
vitesse gagnait la moitie de sa valeur en 14 ms, a pleine vitesse.

Pour tout mouvement **plus rapide que 260 us** (`fast_delay_us`) :

- **acceleration constante** : la vitesse monte regulierement jusqu'a la
  vitesse rapide en `motor_driver.ramp_time_s` (defaut 2 s, reglable depuis
  la page Configuration → Avance), et redescend de meme ;
- **STOP doux** : un STOP (bouton, relache du mode continu, parking)
  decelere depuis la vitesse du moment au lieu de couper net. Depuis la
  pleine vitesse, la coupole glisse encore ~1,7° (110 us, 2 s) ;
- la rampe est emise en paliers de 20 ms que le PIO enchaine seul : aucun
  travail Python par pas, train d'impulsions continu.

**A 260 us et plus lent, rien ne change** (corrections de suivi, calibration,
petits mouvements) : rampe historique et arret immediat. *(Remplace en
v6.19.1 : rampe douce pour tous, STOP immediat conserve a 260 us.)*

### Ordre de mise a jour indifferent

Le Pi envoie l'acceleration en 6e argument de `MOVE`. L'ancien firmware
l'ignore (il reste sur l'ancienne rampe), le nouveau l'applique. La mise a
jour OTA et le flash du Pico peuvent donc se faire dans n'importe quel ordre.

### Flash

Meme procedure qu'a l'etape 2 (`motor_service` arrete, sans sudo), en
sauvegardant d'abord la version en place (voir « Retour arriere » ci-dessous) :
seuls `main.py`, `ramp.py` et `step_generator.py` changent.

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

Garder une copie des trois fichiers avant le flash (`motor_service` arrete,
et **sans sudo**, ni pour `mkdir` ni pour `mpremote`) :

```bash
sudo systemctl stop motor_service
mkdir -p ~/firmware_backup
mpremote cp :main.py ~/firmware_backup/main.py
mpremote cp :step_generator.py ~/firmware_backup/step_generator.py
mpremote cp :ramp.py ~/firmware_backup/ramp.py
ls -l ~/firmware_backup   # les 3 fichiers doivent etre presents, taille non nulle
```

Pour revenir en arriere, recopier ces trois fichiers vers le Pico (meme
commande dans l'autre sens), debrancher/rebrancher le Pico, puis
`sudo systemctl start motor_service`.

### Changer la vitesse

La vitesse n'est plus en dur dans le code. Depuis la v6.18, deux cles de
`data/config.json` → `motor_driver` (microsecondes par pas), editables depuis
la page **Configuration → Avance** de l'interface web :

- `fast_delay_us` : grands deplacements (≥ 3°) — GOTO, bascule meridien,
  parking, JOG ±10°, mode continu. C'est celle qu'on accelere.
- `delay_us` : petits deplacements (< 3°) — corrections de suivi, fin des
  GOTO, JOG ±1°. Laisser a 260 : sous 1° la rampe occupe presque toute la
  duree du mouvement, et c'est la que le firmware la raccourcit.

Un redemarrage des services est necessaire pour qu'elle soit prise en compte
(bouton « Redemarrer les services » de la meme page).

**Ne pas descendre au juge.** Mesurer d'abord la vitesse reellement atteinte,
palier par palier, avec :

```bash
python3 scripts/diagnostics/calibration_vitesse_encodeur.py --dry-run  # plan
python3 scripts/diagnostics/calibration_vitesse_encodeur.py            # mesure
python3 scripts/diagnostics/calibration_vitesse_encodeur.py --depuis 130
# mesure complementaire : 260 µs de reference, puis 130 µs et plus rapide
```

Le script lit la position sur l'encodeur EMS22A et compare la vitesse obtenue
a la vitesse demandee : il s'arrete au premier palier ou la coupole ne suit
plus, et recommande une valeur avec 15 % de marge. Il ne modifie ni la
configuration ni les services.

## Etape 3 : Branchements

```
Raspberry Pi 5              Pi Pico (RP2040)                DM860T
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

| Pi Pico         | DM860T  | Role          |
|-----------------|---------|---------------|
| **GP2** (pin 4) | **PUL+** | Signal STEP   |
| **GP3** (pin 5) | **DIR+** | Direction     |
| **GND** (pin 38)| **PUL-** et **DIR-** | Masse commune |

### Precautions

- ⚠️ **DEUX drivers sont montes en parallele sur le meme moteur** : le **DM860T**
  (36 V) pilote par notre Pi Pico, et le **DM556T** du boitier UPAN. Verifier
  l'etiquette avant de brancher PUL+/DIR+ : c'est le **DM860T** qui nous concerne.
  (Modele et tension confirmes sur site le 20/09/2026.)

- **Masse commune obligatoire** : le GND du Pico doit etre relie au GND du DM860T
- **Fils courts** : garder < 30 cm entre Pico et DM860T
- **Ne PAS alimenter le Pico par le DM860T** — utiliser uniquement l'USB du Pi 5
- **Deconnecter les fils GPIO** du Pi 5 vers le DM860T (ils ne sont plus utilises)

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

### "Permission denied" avec mpremote

Trois causes possibles, a verifier dans cet ordre :

```bash
# 1. motor_service tient le port du Pico -> l'arreter
sudo systemctl stop motor_service

# 2. Dossier de destination cree avec sudo (proprietaire root)
ls -ld ~/firmware_backup
sudo chown slenk:slenk ~/firmware_backup   # si le proprietaire est root

# 3. Utilisateur absent du groupe dialout (acces a /dev/ttyACM0)
groups                                     # doit contenir "dialout"
sudo usermod -a -G dialout $USER           # $USER, pas $slenk
# Se deconnecter et reconnecter pour appliquer
```

Si mpremote affiche `cp <source> <destination>` avant l'erreur, il s'est
bien connecte au Pico : le port n'est pas en cause, regarder la cause 2.

### Le moteur ne tourne pas

1. Verifier que le DM860T est sous tension
2. Verifier les fils GP2→PUL+, GP3→DIR+, GND→PUL-/DIR-
3. Tester avec un mouvement lent : `MOVE 200 1 5000 NONE`
4. Si toujours rien : verifier que le DM860T declenche en 3.3V
   (si non, ajouter un level-shifter 3.3V→5V)

### Reset du Pico

Pour reflasher ou repartir de zero :
1. Maintenir BOOTSEL + brancher USB
2. Le Pico redevient une cle USB (RPI-RP2)
3. Recommencer depuis l'Etape 1

## Protocole serie (reference)

| Commande | Format | Reponse |
|----------|--------|---------|
| Mouvement | `MOVE <steps> <dir> <delay_us> <ramp> [accel]\n` | `OK <steps>\n` |
| Arret | `STOP\n` | `STOPPED <steps>\n` |
| Statut | `STATUS\n` | `IDLE\n` ou `MOVING <remaining>\n` |

- `dir` : 0 = anti-horaire, 1 = horaire
- `delay_us` : delai entre pas en microsecondes (ex: 150 pour CONTINUOUS)
- `ramp` : SCURVE, LINEAR, ou NONE
- `accel` (v6.19, optionnel) : acceleration en pas/s² de la rampe douce
  (tous les mouvements depuis v6.19.1) ; absente → 4545 (110 us atteints en 2 s)
