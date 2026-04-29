# Firmware Pico W — Cimier coupole

Firmware MicroPython pour Raspberry Pi Pico W (RP2040 + WiFi).
Pilotage WiFi REST du cimier motorise (moteur pas-a-pas + driver DM560T).

## Pre-requis

- **Raspberry Pi Pico W** (modele avec WiFi, pas la version sans)
- Cable micro-USB **donnees** pour flasher
- 7 fils Dupont (STEP, DIR, GND, +alim Pico, 2 switches NC, 1 GND switches)
- Driver DM560T configure pour 16 microsteps (3200 steps/rev)

## Etape 1 : Flasher MicroPython

1. Telecharger le firmware MicroPython pour **Pico W** (pas Pico standard) :
   https://micropython.org/download/RPI_PICO_W/ — version 1.20+ requise (asyncio)
2. Mettre le Pico W en bootloader (BOOTSEL + USB)
3. Copier le `.uf2` dans `RPI-RP2`

## Etape 2 : Installer Microdot

```bash
# Sur le Pi 5 (apres flash MicroPython)
mpremote run -c "import mip; mip.install('microdot')"
```

Microdot est le mini-serveur HTTP asyncio utilise pour exposer les endpoints REST.

## Etape 3 : Creer secrets.py local

**Ne jamais versionner ce fichier.** Sur le Pico W :

```python
# secrets.py
WIFI_SSID = "TonReseauWiFi"
WIFI_PASSWORD = "MotDePasse"
```

```bash
mpremote cp secrets.py :secrets.py
```

## Etape 4 : Copier les 3 fichiers firmware

```bash
cd /chemin/vers/Dome_web_v4_6/firmware/cimier/
mpremote cp cimier_controller.py :cimier_controller.py
mpremote cp step_generator.py :step_generator.py
mpremote cp main.py :main.py

# Le Pico W redemarre et execute main.py automatiquement
```

## Etape 5 : Branchements

```
Pi Pico W (RP2040 + WiFi)        DM560T              Switches NC
+---------------------+
| GP2  (pin 4) ---------------> PUL+
| GP3  (pin 5) ---------------> DIR+
| GND  (pin 38) --------------> PUL- + DIR-          GND switches
| GP14 (pin 19) ----------------------------------> SW OPEN  (autre borne -> GND)
| GP15 (pin 20) ----------------------------------> SW CLOSED (autre borne -> GND)
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
Le firmware lit `Pin.value() == 1` pour detecter une butee declenchee.

**Failsafe par construction** : fil coupe ou connecteur debranche -> GPIO lit 1
-> moteur bloque par le firmware. Aucun risque mecanique en cas de panne cable.

## Etape 6 : Verification

### Tester le WiFi

```bash
# Apres copie de main.py, le Pico W demarre, se connecte au WiFi,
# affiche son IP sur la console serie :
mpremote
> # Reset le Pico W
> ^X  # Quitter
> mpremote
# Relancer :
> import main  # Affiche "WiFi connected: 192.168.x.y"
```

Note ton IP ; tu en as besoin pour la prochaine etape.

### Tester les endpoints REST

```bash
# Status
curl http://192.168.x.y/status
# {"state": "closed", "open_switch": false, ...}

# Lancer une ouverture
curl -X POST http://192.168.x.y/open

# Stop
curl -X POST http://192.168.x.y/stop

# Info
curl http://192.168.x.y/info
# {"firmware_version": "0.1.0", "wifi_rssi": -45, ...}

# Inverser direction (si ouverture/fermeture inversees au 1er test)
curl -X POST http://192.168.x.y/config -H "Content-Type: application/json" \
     -d '{"invert_direction": true}'
```

## Etape 7 : Donner une IP fixe au Pico W

Sur la box/routeur du reseau local : reservation DHCP statique de la MAC du Pico W
vers une IP fixe (ex. 192.168.1.42). Cette IP sera mise dans `data/config.json`
de DriftApp (cle `cimier.host`).

## Depannage

### Le Pico W ne se connecte pas au WiFi

- Verifier `secrets.py` : SSID exact, pas d'espaces, mot de passe correct
- Le reseau WiFi doit etre 2.4 GHz (le Pico W ne supporte pas le 5 GHz)
- Distance/obstacles : tester avec un AP plus proche

### Le moteur tourne dans le mauvais sens (ouverture <-> fermeture)

```bash
curl -X POST http://192.168.x.y/config -H "Content-Type: application/json" \
     -d '{"invert_direction": true}'
```

Le changement est runtime, pas besoin de reflasher. Pour le rendre permanent, le
service Pi devra renvoyer `{invert_direction: true}` au boot du Pico W.

### Les switches ne fonctionnent pas

1. Multimetre : `Pico GP14 vs GND` lit 0 Ohm au repos (NC ferme), infini en butee
2. Verifier `Pin.PULL_UP` dans le code (deja en place par defaut)
3. Tester via REPL :
   ```python
   from machine import Pin
   sw = Pin(14, Pin.IN, Pin.PULL_UP)
   print(sw.value())  # 0 au repos, 1 en butee ou cable coupe
   ```

### Le Pico W reboote pendant un cycle moteur

Cause probable : pics de courant moteur sur l'alim 12V partagee.
Solution : ajouter une capa 220 uF + 100 nF sur l'entree 12V du module
QC3.0 USB-C alimentant le Pico W. Cf. discussion technique terrain.

### Reset firmware complet

```bash
mpremote rm :main.py :cimier_controller.py :step_generator.py :secrets.py
mpremote reset
```

## Protocole REST (reference)

| Methode | Path | Body | Reponse |
|---------|------|------|---------|
| GET | `/status` | - | `{state, open_switch, closed_switch, cycle_steps_done, last_action_ts, error_message}` |
| POST | `/open` | - | idem `/status` |
| POST | `/close` | - | idem `/status` |
| POST | `/stop` | - | idem `/status` |
| GET | `/info` | - | `{firmware_version, protocol_version, steps_per_cycle, cycle_timeout_s, invert_direction, wifi_rssi, wifi_ip, free_memory}` |
| POST | `/config` | `{invert_direction: bool}` | idem `/info` |

Tous les endpoints retournent JSON.

`state` est l'un de :
- `closed` — cimier ferme (switch closed declenche)
- `opening` — cycle d'ouverture en cours
- `open` — cimier ouvert (switch open declenche)
- `closing` — cycle de fermeture en cours
- `error` — anomalie (timeout cycle, deux switches simultanes, etc.)
- `unknown` — etat indetermine (ni l'un ni l'autre des switches declenches)
