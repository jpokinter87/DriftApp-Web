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
| VBUS (pin 40) <-- 5V depuis boitier QC3.0 USB-C
+---------------------+
```

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

Probleme classique sur Raspberry Pi 5 Bookworm : `brltty` ou `ModemManager`
intercepte `/dev/ttyACM0`. Diagnostic et fix :

```bash
# Verifier
sudo lsof /dev/ttyACM0
ps aux | grep -E 'mpremote|brltty|ModemManager|tio|screen|minicom' | grep -v grep

# Desactiver les coupables (si presents)
sudo systemctl stop ModemManager
sudo systemctl disable ModemManager
sudo apt purge -y brltty 2>/dev/null   # si installe

# Debrancher le Pico, attendre 3 s, rebrancher
sudo lsof /dev/ttyACM0   # doit etre vide

# Retester
mpremote ls
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
