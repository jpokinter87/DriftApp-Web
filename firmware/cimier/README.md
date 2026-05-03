# Firmware Pico W — Cimier coupole

Firmware MicroPython pour Raspberry Pi Pico W (RP2040 + WiFi).
Pilotage WiFi REST du cimier motorise (moteur pas-a-pas + driver DM560T).

**Aucune dependance externe a installer** : le mini-serveur HTTP est embarque
dans le firmware (socket pur). Pas de `mip install`, pas de microdot.

## Pre-requis

- **Raspberry Pi Pico W** (modele avec WiFi, pas la version Pico standard)
- **MicroPython 1.20+** (UF2 telecharge depuis micropython.org)
- Cable micro-USB **donnees** pour flasher
- 7 fils Dupont (STEP, DIR, GND, +alim Pico, 2 switches NC, 1 GND switches)
- Driver DM560T configure pour 16 microsteps (3200 steps/rev)

## Procedure complete (premiere installation)

### Etape 1 : Flasher MicroPython

1. Telecharger le firmware MicroPython pour **Pico W** :
   <https://micropython.org/download/RPI_PICO_W/> -> version 1.20+ requise
2. Mettre le Pico W en bootloader : maintenir **BOOTSEL** + brancher USB
3. Le Pico apparait comme `RPI-RP2`. Glisser-deposer le `.uf2` dessus
4. Le Pico redemarre, `/dev/ttyACM0` apparait

### Etape 2 : Creer secrets.py local

Sur la machine ou est branche le Pico W, creer le fichier :

```python
# /tmp/secrets.py
WIFI_SSID = "TonReseauWiFi"
WIFI_PASSWORD = "MotDePasse"
```

**Important** : le reseau WiFi doit etre en **2.4 GHz** (le Pico W ne supporte
pas le 5 GHz).

### Etape 2bis : Stopper motor_service (Pi prod uniquement)

Sur le Pi de production, `motor_service.service` est lance au boot et **squatte
`/dev/ttyACM0`** pour parler au Pi Pico moteur (RP2040 v5.3). Tant qu'il
tourne, `mpremote` echoue avec `could not enter raw repl` ou bloque
indefiniment, meme si ModemManager/brltty sont neutralises.

**Avant l'Etape 3, executer le helper drop-in** (depuis le repo) :

```bash
sudo bash scripts/diagnostics/pico_bringup_prepare.sh prepare
```

Ce helper :
1. Cree un drop-in systemd `Restart=no` (motor_service ne redemarrera pas
   tout seul si tu fais un `mpremote reset` qui le perturbe).
2. Stoppe + disable motor_service.
3. Verifie que le service est bien arrete.

Tu peux maintenant utiliser `mpremote` librement.

**A la fin du bringup**, restaurer motor_service :

```bash
sudo bash scripts/diagnostics/pico_bringup_prepare.sh restore
```

Le drop-in est supprime et motor_service est re-enable + start.

> **Note dev distant** : si tu n'as pas la main directe sur le Pi (ex. machine
> de dev distante), c'est l'utilisateur sur site qui doit lancer ces deux
> commandes au debut et a la fin du bringup.

### Etape 3 : Copier les 4 fichiers sur le Pico

```bash
cd /chemin/vers/Dome_web_v4_6/firmware/cimier/

# Modules dans l'ordre (main.py en dernier !)
mpremote cp cimier_controller.py :cimier_controller.py
mpremote cp step_generator.py :step_generator.py
mpremote cp /tmp/secrets.py :secrets.py
mpremote cp main.py :main.py

# Reset et console serie pour voir le boot
mpremote reset
mpremote
# Tu dois voir le banner "DriftApp Cimier Firmware" puis "WiFi connected: ..."
```

**Pourquoi main.py en dernier** : si un crash survient pendant la copie d'un
autre fichier, tu peux toujours reprendre la main. Avec main.py absent, le
Pico tombe au REPL au boot, jamais bloque.

### Etape 4 : Verification

Apres le reset, sur la console serie tu dois voir :

```
============================================================
DriftApp Cimier Firmware
============================================================
Boot dans 3 secondes...
(Ctrl-C dans mpremote pour interrompre et acceder au REPL)
  3 s
  2 s
  1 s
Boot demarre.

Hardware initialise. Etat: error
Connexion WiFi a TonReseauWiFi ...

>>> WiFi connected: 192.168.1.X <<<
>>> Test rapide : curl http://192.168.1.X/status <<<

HTTP server listening on port 80
```

L'IP affichee (`192.168.1.X`) est celle attribuee dynamiquement par DHCP. Note-la
pour les tests.

L'**etat initial** sera `error` (les deux switches "declenches" car GP14/GP15
non cables) ou `unknown` (si tu mets les cavaliers - cf. ci-dessous).

## Branchements

```
Pi Pico W (RP2040 + WiFi)        DM560T              Switches NC
+---------------------+
| GP2  (pin 4)  ---------------> PUL+
| GP3  (pin 5)  ---------------> DIR+
| GND  (pin 38) ---------------> PUL- + DIR-          GND switches
| GP14 (pin 19) ---------------------------------> SW OPEN  (autre borne -> GND)
| GP15 (pin 20) ---------------------------------> SW CLOSED (autre borne -> GND)
| Connecteur USB <-- cable USB-C depuis boitier QC3.0 (alim 5V)
| VBUS (pin 40) <-- FLOTTANTE, aucun fil
+---------------------+
```

> **Alim** : le 5V vient du **connecteur USB micro/USB-C de la carte** Pico W,
> pas d'un fil sur la pin 40. La pin 40 (VBUS) reste flottante dans l'install
> cimier standard. La regle « USB OU VBUS jamais les deux » s'applique
> uniquement si quelqu'un cable la pin 40 vers une autre source 5V externe
> par erreur — ce qui ne doit pas arriver ici.

> **Note GND** : pin 38 utilisee par convention dans ce schema. N'importe
> quelle pin GND du Pico W marche (3, 8, 13, 18, 23, 28, 33, 38).

### Variante avec Darlington ULN2803A (install avec switch Robot/Manuel)

Le schema ci-dessus suppose un cablage direct Pico W -> DM560T. Si l'install
utilise un Darlington ULN2803A intermediaire (ex. pour multiplexer entre une
commande manuelle Arduino et la commande robotisee Pico W via un switch
Robot/Manuel), la topologie est :

```
            +24V (alim moteur DM560T, V+ du driver)
                 |
                 +---> PUL+ -+
                 +---> DIR+ -+ relies ensemble sur bornier DM560T
                 +---> ENA+ -+

Pico W GP2  --------> ULN2803A IN1 ---> OUT1 ---> DM560T PUL-
Pico W GP3  --------> ULN2803A IN2 ---> OUT2 ---> DM560T DIR-
Pico W GND  --------- ULN2803A pin 9 --- GND DM560T   (masse commune)
DM560T ENA-                                            (flottant = driver actif)
```

**Tension d'entree des opto** : sur les drivers Leadshine type DM556T/DM560T,
un DIP switch ou cavalier (souvent marque « 5V/24V ») selectionne la tension
d'entree des opto :

- Position **5V** : pas de resistance interne. Il faut fournir un +5V
  separe pour le commun des +.
- Position **24V** : resistance interne integree (~1,8 kohm) qui limite le
  courant a ~13 mA quand on attaque les + en 24V. **Configuration standard
  quand le boitier cimier n'a qu'un rail 24V** (cas le plus frequent).

Dans la topologie ci-dessus, le switch est en position **24V** et le commun
PUL+/DIR+/ENA+ est tire au meme +24V que celui qui alimente le DM560T (V+).

Logique : le Darlington est un **sink open-collector**. Quand le GPIO Pico
est HIGH, l'output Darlington tire le PUL-/DIR- a GND. Le courant ~13 mA
traverse la LED interne de l'opto DM560T (anode +24V -> resistance interne
1,8 kohm -> LED opto -> cathode GND via Darlington). Le ULN2803A supporte
50V de blocage max, donc 24V est largement dans la marge.

**Points cles** :

- Le **+** des PUL+/DIR+/ENA+ vient de **l'alim driver (24V) ou d'un rail
  5V separe selon la position du switch DM560T**, jamais du Pico W (ni
  VBUS, ni 3V3 OUT).
- La **masse est commune** entre Pico W (pin 38), Darlington (pin 9) et
  DM560T (GND logique). C'est la seule connexion entre Pico W et le reste
  cote masse.
- **ENA+** est relie au commun avec PUL+/DIR+ ; **ENA-** reste flottant
  (driver actif par defaut sur Leadshine, configurable via DIP du DM560T).
  Le firmware n'utilise pas ENA — l'enable/disable du driver pour economie
  batterie est gere au niveau alim par la cascade Shelly 220V/12V.
- Le harnais Pico W a 5 fils seulement : GND + GP2 + GP3 + GP14 + GP15.
  **Aucun fil sur la pin 40 (VBUS).**

### Switches : cablage NC + pull-up interne

Les fins de course sont **NC (Normally Closed)** : au repos contact ferme,
declenches contact ouvert.

```
Switch FIN OUVERT (NC) :
  borne 1 -> Pico W GP14
  borne 2 -> Pico W GND

Switch FIN FERME (NC) :
  borne 1 -> Pico W GP15
  borne 2 -> Pico W GND
```

Le pull-up interne du RP2040 (~50 kOhm) rend les composants externes inutiles.

**Failsafe par construction** : fil coupe ou connecteur debranche -> GPIO lit 1
-> moteur bloque par le firmware. Aucun risque mecanique en cas de panne cable.

## Install definitive (cablage hardware)

Les Etapes 1-4 valident le firmware via USB seul, broches du Pico W en l'air.
Le passage a l'install definitive (soudage du harnais vers Darlington/DM560T)
est l'etape la plus risquee : un Pico W neuf a deja ete grille a ce stade
(2026-05-02) par confusion d'identification de pin cote module Darlington.

**Cette procedure est obligatoire avant la premiere mise sous tension de
l'install definitive.**

### Regles d'or non negociables

1. **Le Pico W est alimente uniquement par son connecteur micro-USB de la
   carte** (USB Pi pour le bringup, QC3.0 USB-C pour la prod). La pin 40
   (VBUS) **reste flottante**, aucun fil externe ne s'y connecte.
   Consequence : aucun risque de back-feed tant que cette regle est
   respectee.
2. **Si la pin 40 (VBUS) doit etre cablee** (cas avance, alim 5V externe),
   alors l'USB **ne doit pas etre branche en parallele**. La regle simple
   est : *une seule source 5V a la fois sur le Pico W*. Dans l'install
   cimier standard, la pin 40 n'est PAS dans le harnais — donc cette regle
   est satisfaite par construction.
3. **Avant toute soudure, verifier au multimetre l'identite de chaque pin
   de destination** cote module externe (Darlington/DM560T). La serigraphie
   ne suffit pas : un GND mal identifie cote Darlington = court 3,3V<->GND
   du Pico W = composant grille instantanement.
4. **Souder un connecteur header femelle (Dupont 2x20) sur le Pico W, pas
   les fils en direct.** Permet de debrancher integralement le Pico W du
   harnais pour diagnostic ou remplacement sans dessouder.

### Preparation du Pico W neuf

Imprimer le pinout officiel : <https://datasheets.raspberrypi.com/picow/PicoW-A4-Pinout.pdf>

Marquer au feutre indelebile les 5 pins critiques de la zone coin USB :

| Pin | Nom | Role |
|-----|-----|------|
| 36 | 3V3 OUT | Sortie 3,3 V — NE PAS y connecter d'alim externe |
| 37 | 3V3 EN | Enable regulateur — laisser flottant |
| 38 | GND | Masse (une parmi 8 disponibles) |
| 39 | VSYS | Alim systeme 1,8-5,5 V — danger si confondu avec GND |
| 40 | VBUS | 5V USB — pas d'alim externe en parallele de l'USB Pi |

**Note GND** : 8 pins GND sont disponibles (3, 8, 13, 18, 23, 28, 33, 38).
N'importe laquelle marche, la pin 38 n'a aucune particularite. Le schema
Branchements ci-dessus utilise la 38 par convention, pas par necessite.

### Preparation et verification du harnais (Pico W debranche)

**Etape A — Identifier les pins cote Darlington/DM560T au multimetre :**

Pour chaque pin de destination, mode continuite :

- **Test GND** : pin candidate « GND » du Darlington <-> borne « - » de
  l'alim externe (eteinte) -> doit biper.
- **Test isolation VCC** : pin candidate « GND » <-> tout rail VCC / 3,3V
  / 5V / 12V / 24V -> doit etre **OUVERT**. Si bip = c'est le VCC, pas
  le GND. *C'est l'erreur qui a fait griller le premier Pico W en
  2026-05-02 (fil destine a la masse soude sur le 3,3V Darlington).*

**Etape B — Verifier le harnais cote connecteur Pico W :**

Multimetre continuite, deux a deux entre tous les fils du connecteur,
Pico W toujours debranche :

- Tous les fils **OUVERTS** entre eux deux a deux (sauf factorisation
  volontaire de plusieurs GND sur un meme fil).
- En particulier : « fil GND » contre tous les autres fils -> **OUVERT**.

**Etape C — Verifier les masses externes :**

Harnais branche sur Darlington/DM560T, Pico W toujours debranche :

- « Fil GND » du connecteur Pico W <-> borne GND alim externe
  -> **CONTINU** (bip).
- « Fil GND » du connecteur Pico W <-> tout VCC / 3,3V / 5V / 12V / 24V
  -> **OUVERT**.

Si A+B+C passent, le harnais est sain. Aucun fil ne court-circuite VCC
a GND. Sinon, identifier le coupable avant de brancher le Pico W.

### Connexion progressive (un fil a la fois)

A chaque etape, USB debranche, on connecte UN fil, puis on rebranche USB
et on verifie :

- Ecran du Pi reste allume.
- Aucun message « USB current exceeds » a l'ecran.
- Pico W repond toujours a `/status` sur le reseau.

Ordre recommande :

1. **GND seul** (n'importe quelle pin GND) -> re-test USB.
2. **PUL+** (GP2 -> entree Darlington) -> re-test.
3. **DIR+** (GP3 -> entree Darlington) -> re-test.
4. **Switch open** (GP14 -> GND switches) -> re-test.
5. **Switch closed** (GP15 -> GND switches) -> re-test.

Le fil qui declenche un defaut = a diagnostiquer immediatement (pin de
destination mal identifiee, court harnais, ou GPIO en sortie HIGH boucle
sur GND par solder bridge).

### Validation avant mise sous tension definitive

USB debranche, harnais complet branche, multimetre continuite. Ces tests
sont des **assurances** que personne n'a connecte la pin 40 par megarde :

- Pin 40 (VBUS) <-> tout rail 5V externe -> **OUVERT** (la pin 40 doit
  etre flottante dans l'install cimier standard).
- Pin 38 (GND) <-> Pin 36 (3V3 OUT) -> **OUVERT**.
- Pin 38 (GND) <-> Pin 39 (VSYS) -> **OUVERT**.
- Pin 38 (GND) <-> Pin 40 (VBUS) -> **OUVERT**.

Si tout passe : brancher l'alim definitive via le **connecteur USB de la
carte** Pico W (cable QC3.0 USB-C branche directement sur le Pico W).
Le Pico W doit booter, se connecter au WiFi, repondre a `/status`. Cycle
complet open/close validable via curl ou helper.

> **Pourquoi alim via le connecteur USB et pas via la pin 40 ?** Le
> connecteur USB integre une protection contre les inversions et un
> filtrage. La pin 40 (VBUS) est un acces direct au rail 5V interne, sans
> protection. En install cimier standard, on alimente toujours via le
> connecteur USB de la carte.

## Tests manuels (avant que les vrais switches soient cables)

⚠️ Sans switches cables, GP14/GP15 sont flottants -> pull-up interne -> les
deux entrees lisent 1 -> le controller croit que les deux butees sont
declenchees simultanement -> etat `error`, le moteur ne bougera pas.

**Solution simple pour bringup** : 2 cavaliers (jumpers) :

```
Pico GP14 ----- jumper ----- GND   (simule "switch open au repos")
Pico GP15 ----- jumper ----- GND   (simule "switch closed au repos")
```

Avec les 2 cavaliers, les GPIOs lisent 0 -> etat `unknown` -> cycles autorises.

### Tests via curl (depuis n'importe quel PC sur le LAN)

```bash
# Etat
curl http://192.168.1.X/status

# Lancer ouverture (le moteur demarre)
curl -X POST http://192.168.1.X/open

# Pour ARRETER le cycle (simuler butee open atteinte) :
# DEBRANCHER le cavalier GP14 ↔ GND
# -> GPIO14 flotte sur pull-up -> 1 -> "switch open declenche"
# -> moteur s'arrete, etat devient "open"

# Re-brancher le cavalier GP14, puis tester fermeture (sens inverse)
curl -X POST http://192.168.1.X/close

# Stop d'urgence
curl -X POST http://192.168.1.X/stop

# Info firmware (RSSI WiFi, memoire libre, etc.)
curl http://192.168.1.X/info
```

### Test interactif via le helper Python

Plus pratique que `curl` repete a la main :

```bash
uv run python scripts/diagnostics/test_pico_cimier.py 192.168.1.X
```

Menu interactif avec status / open / close / stop / info / invert direction.

### Validation direction moteur

Au premier `/open`, observer le sens de rotation :

- **Si le moteur ouvre dans le bon sens** -> direction nominale OK, rien a faire
- **Si le moteur ferme alors qu'on a demande open** -> direction inversee :

```bash
curl -X POST http://192.168.1.X/config \
     -H "Content-Type: application/json" \
     -d '{"invert_direction": true}'
```

Pas de reflash necessaire. L'inversion est runtime : elle se perd au reboot du
Pico W. Pour la rendre permanente, deux options :

- **Phase 0** : modifier `cimier_controller.py` constantes `_DIR_OPEN_NOMINAL` /
  `_DIR_CLOSE_NOMINAL` et reflasher
- **Phase 1+** : le service Pi renverra `{invert_direction: true}` au boot du
  Pico W, valeur persistee dans `data/config.json`

## Depannage

### Le Pico W ne se connecte pas au WiFi

Verifie sur la console serie. Trois causes classiques :

1. **secrets.py incorrect** : retape SSID exact, pas d'espaces, mot de passe correct
2. **Reseau en 5 GHz** : le Pico W ne supporte que 2.4 GHz. Utilise un AP/repeteur
   dual-band ou cree un reseau 2.4 GHz dedie
3. **Reseau eteint ou hors portee** : tester avec un AP plus proche

Pour tester manuellement la connexion WiFi sans lancer main.py :

```bash
mpremote rm :main.py    # casse la boucle de boot
mpremote                # REPL accessible
>>> import network
>>> wlan = network.WLAN(network.STA_IF)
>>> wlan.active(True)
>>> from secrets import WIFI_SSID, WIFI_PASSWORD
>>> wlan.connect(WIFI_SSID, WIFI_PASSWORD)
>>> import time; time.sleep(5)
>>> wlan.isconnected()       # doit afficher True
>>> wlan.ifconfig()          # IP du Pico
>>> # Ctrl-]  pour quitter
```

Une fois valide, recopie main.py.

### `could not enter raw repl` ou la console mpremote est figee

`/dev/ttyACM0` est tenu par un autre processus. Trois coupables possibles
sur le Pi prod :

1. **`motor_service`** (DriftApp) — service systemd auto-start, parle au
   Pi Pico moteur RP2040 v5.3. **C'est le coupable n°1 sur le Pi prod**.
   Solution : helper drop-in (cf. Etape 2bis) :

   ```bash
   sudo bash scripts/diagnostics/pico_bringup_prepare.sh prepare
   ```

2. **`ModemManager`** ou **`brltty`** (Raspberry Pi 5 Bookworm) :

   ```bash
   sudo systemctl stop ModemManager
   sudo systemctl disable ModemManager
   sudo apt purge -y brltty 2>/dev/null   # si installe
   ```

3. **Une console serie laissee ouverte** (`tio`, `screen`, `minicom`,
   ancien `mpremote` zombie) :

   ```bash
   ps aux | grep -E 'mpremote|tio|screen|minicom' | grep -v grep
   ```

Diagnostic generique :

```bash
sudo lsof /dev/ttyACM0
# Doit etre vide. Si un PID apparait, c'est ton coupable.

# Debrancher le Pico, attendre 3 s, rebrancher, retester :
sudo lsof /dev/ttyACM0   # vide
mpremote ls              # OK
```

A la fin du bringup, n'oublie pas :

```bash
sudo bash scripts/diagnostics/pico_bringup_prepare.sh restore
```

### Le Pico repond "STATS / TATUS / TAT" en boucle

Ce ne sont pas des fragments emis par le firmware. Si tu tapes `STATUS` au REPL
MicroPython, tu obtiens `NameError: name 'STATUS' isn't defined` — c'est correct.
Le firmware utilise **WiFi REST**, pas un protocole texte sur la console serie.

Pour tester le firmware, **utilise curl ou le script helper**, pas le REPL.

### Le firmware boucle au boot, je n'ai plus la main

Le mode safe-boot du firmware donne **3 secondes** au demarrage avec un banner.
Pendant ces 3 secondes, fais **Ctrl-C** dans `mpremote` -> tu recuperes le REPL.

Si ca ne suffit pas, supprime main.py :

```bash
mpremote rm :main.py
mpremote reset
```

Si meme ca ne marche pas, **flash nuke** complet :

```bash
# Telecharger l'utilitaire et MicroPython
wget https://datasheets.raspberrypi.com/soft/flash_nuke.uf2 -O ~/flash_nuke.uf2
wget https://micropython.org/resources/firmware/RPI_PICO_W-LATEST.uf2 -O ~/micropython.uf2

# 1ere passe : nuke (BOOTSEL + USB) -> deposer flash_nuke.uf2 sur RPI-RP2
# 2eme passe : MicroPython (BOOTSEL + USB) -> deposer micropython.uf2 sur RPI-RP2
```

### Le moteur tourne dans le mauvais sens

Voir « Validation direction moteur » plus haut.

### Les switches ne fonctionnent pas

1. Multimetre : `Pico GP14 vs GND` lit ~0 Ohm au repos (NC ferme), infini en butee
2. Au REPL, tester directement :
   ```python
   from machine import Pin
   sw = Pin(14, Pin.IN, Pin.PULL_UP)
   print(sw.value())   # 0 au repos, 1 en butee ou cable coupe
   ```

### « USB current exceeds » sur l'ecran du Pi

Surconsommation detectee sur le port USB ou le Pico W est branche. Causes
classiques apres soudage du harnais :

1. **VBUS Pico W (pin 40) connecte a une alim externe en parallele de
   l'USB Pi** -> back-feed entre deux sources 5V -> debrancher l'une
   des deux. **Regle d'or : USB OU VBUS, jamais les deux.**
2. **Court-circuit dans le harnais** : fil GND touche un VCC quelque
   part. Diagnostic : multimetre continuite GND<->VCC sur tous les
   rails Darlington/DM560T, doit etre OUVERT.
3. **Solder bridge sur le Pico W** : pont entre 2 pins adjacentes,
   surtout zone 36-40 (3V3 OUT / 3V3 EN / GND / VSYS / VBUS).

Voir « Install definitive » plus haut pour la procedure de diagnostic
complete.

### L'ecran du Pi s'eteint au branchement du Pico W

Symptome plus brutal que « USB current exceeds » : court-circuit majeur
qui depasse la protection de l'ecran ou du hub USB.

Cause typique : un fil intentionnellement « GND » a ete soude cote
destination sur un rail VCC du module Darlington par confusion (3,3V
serigraphie similaire au GND, ou comptage de pin errone). Au branchement
USB, court direct entre VCC externe et masse Pico W -> regulateur interne
grille instantanement.

**Action immediate** :

1. Debrancher le Pico W. Ne pas insister.
2. Multimetre : verifier que la pin choisie comme « GND » cote module
   externe est bien continue avec une masse connue ET ouverte vis-a-vis
   de tout VCC (procedure « Install definitive » Etape A).
3. Si le Pico W ne reapparait plus sur le reseau apres re-cablage
   correct -> probablement mort. Commander un remplacement et reprendre
   la procedure « Install definitive » integralement avec le Pico W neuf.

### Le Pico W reboote pendant un cycle moteur

Cause probable : pics de courant moteur sur l'alim 12V partagee.
Solution : ajouter une capa 220 uF + 100 nF sur l'entree 12V du module
QC3.0 USB-C alimentant le Pico W.

## Protocole REST (reference)

Tous les endpoints retournent JSON.

| Methode | Path | Body | Reponse |
|---------|------|------|---------|
| GET | `/status` | - | `{state, open_switch, closed_switch, cycle_steps_done, last_action_ts, error_message}` |
| POST | `/open` | - | idem `/status` |
| POST | `/close` | - | idem `/status` |
| POST | `/stop` | - | idem `/status` |
| GET | `/info` | - | `{firmware_version, protocol_version, steps_per_cycle, cycle_timeout_s, invert_direction, wifi_rssi, wifi_ip, free_memory}` |
| POST | `/config` | `{invert_direction: bool}` | idem `/info` |

`state` est l'un de :
- `closed` — cimier ferme (switch closed declenche)
- `opening` — cycle d'ouverture en cours
- `open` — cimier ouvert (switch open declenche)
- `closing` — cycle de fermeture en cours
- `error` — anomalie (timeout cycle, deux switches simultanes, etc.)
- `unknown` — etat indetermine (ni l'un ni l'autre des switches declenches,
  c'est le cas au boot quand les cavaliers sont en place ou quand le cimier
  est en mouvement entre les butees)
