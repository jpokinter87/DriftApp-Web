# Firmware Pico W — Cimier coupole (capteur-only)

Firmware MicroPython pour Raspberry Pi Pico W (RP2040 + WiFi).

**Rôle depuis le pivot Shelly (v0.2.0, protocole 2)** : le Pico W est un
**pur serveur de capteurs**. Il expose l'état des 2 fins de course
(ouverte / fermée) via HTTP REST. **L'orchestration moteur est faite côté
Pi principal**, par `services/cimier_service.py`, via 2 relais Shelly
(MOT + UPDN cascadés sur SHELLY-1-24).

Voir spec d'orchestration :
[`docs/superpowers/specs/2026-05-23-cinematique-shelly-cimier-garde-fou-design.md`](../../docs/superpowers/specs/2026-05-23-cinematique-shelly-cimier-garde-fou-design.md).

---

## Aucune dépendance externe

Le mini-serveur HTTP est embarqué dans le firmware (socket pur). Pas de
`mip install`, pas de microdot. Tu n'as besoin que de MicroPython +
3 fichiers (`main.py`, `cimier_controller.py`, `secrets.py`).

---

## Pré-requis hardware

| Élément | Détail |
|---|---|
| Pico W | Modèle avec WiFi (pas la version Pico standard) |
| MicroPython | 1.20+ (UF2 téléchargé depuis micropython.org) |
| Câble USB | Micro-USB **données** (pas seulement charge) pour flasher |
| Fins de course | 2 contacts NC sur GP14 (ouvert) / GP15 (fermé), GND switches |
| Alim Pico W | 12 V permanente (pas coupée en fin de session) |

> ⚠️ Le Pico W reste vivant en permanence (alim 12 V indépendante), même
> quand la cascade Shelly 220 V est coupée en fin de session
> astrophotographique. C'est nécessaire pour que le pré-vol garde-fou du
> `cimier_service` puisse lire `/status` avant de remettre le 24 V moteur
> (cf. spec §3.0).

---

## Procédure complète (première installation)

### Étape 1 : Flasher MicroPython

1. Télécharger le firmware MicroPython pour **Pico W** :
   <https://micropython.org/download/RPI_PICO_W/> → version 1.20+ requise.
2. Mettre le Pico W en bootloader : maintenir **BOOTSEL** + brancher USB.
3. Le Pico apparaît comme `RPI-RP2`. Glisser-déposer le `.uf2` dessus.
4. Le Pico redémarre, `/dev/ttyACM0` apparaît côté hôte.

### Étape 2 : Créer `secrets.py` local

Sur la machine où est branché le Pico W, créer le fichier `secrets.py` :

```python
WIFI_SSID = "TonReseauWiFi"
WIFI_PASSWORD = "MotDePasse"
```

L'IP du Pico W est attribuée **par DHCP routeur** (réservation MAC). Pas
d'IP statique dans `secrets.py`. L'IP réelle assignée est ensuite reportée
dans `data/config.json → cimier.host` côté Pi principal.

### Étape 3 : Flasher les 3 fichiers source

Depuis le repo, à la racine `firmware/cimier/` :

```bash
mpremote cp main.py :
mpremote cp cimier_controller.py :
mpremote cp secrets.py :
mpremote reset
```

Le Pico W redémarre, se connecte au WiFi, et démarre le serveur HTTP sur
port 80. Un message banner s'affiche sur la console série pendant 3 s
(fenêtre de safe-boot, permet `Ctrl-C` pour reprendre la main en REPL si
le firmware bloque).

### Étape 4 : Vérification rapide

Depuis n'importe quelle machine du réseau local (remplacer `<IP-DU-PICO>`
par l'adresse assignée — visible sur la console série au démarrage) :

```bash
curl http://<IP-DU-PICO>/status
curl http://<IP-DU-PICO>/info
```

Réponses attendues décrites ci-dessous.

---

## Endpoints REST (2 GET seuls)

Port 80, JSON.

| Méthode | Endpoint | Réponse |
|---|---|---|
| `GET` | `/status` | `{state, open_switch, closed_switch, error_message}` |
| `GET` | `/info` | `{firmware_version, protocol_version, role, wifi_rssi, ...}` |

**Valeurs de `state`** :
- `closed` — cimier fermé (fin de course closed déclenché)
- `open` — cimier ouvert (fin de course open déclenché)
- `unknown` — entre les deux (au démarrage si aucun switch n'est encore
  fait, ou pendant un cycle en cours côté Shelly)
- `error` — both_switches_triggered (incident hardware, à investiguer)

> 🚫 **Endpoints supprimés depuis v0.2.0** : `POST /open`, `POST /close`,
> `POST /stop`, `POST /config`, `GET /diag/*`. L'orchestration moteur est
> désormais 100 % côté Pi (`cimier_service` + 2 Shelly). Tenter un POST
> sur ces endpoints retourne `405 Method Not Allowed` ou `404 Not Found`.

---

## Débogage terrain

### Lire l'état courant

```bash
curl http://<IP-DU-PICO>/status
# {"state":"closed","open_switch":false,"closed_switch":true,"error_message":""}
```

### Simuler une fin de course (banc Pico isolé)

Sur le Pico W avant montage dans la coupole :

```text
Pico GP14 ----- jumper ----- GND switches   (simule "fin de course OPEN déclenchée")
Pico GP15 ----- jumper ----- GND switches   (simule "fin de course CLOSED déclenchée")
```

`GET /status` doit refléter immédiatement le changement. La convention
NC vs NO exacte (pull-up interne, contact vers GND) est documentée dans
`cimier_controller.py` selon le câblage réel des switches en production.

### Vérifier la version firmware

```bash
curl http://<IP-DU-PICO>/info
# {"firmware_version":"0.2.0","protocol_version":2,"role":"sensor_only",...}
```

`protocol_version: 2` confirme que c'est le firmware capteur-only Bloc 1.
Si tu vois `protocol_version: 1`, c'est l'ancien firmware (à reflasher
avec la procédure Étape 3).

---

## Câblage Shelly externe (résumé)

Le moteur cimier est piloté par 2 Shelly 1 Gen 3 cascadés sur un Shelly
220 V → 24 V :

```
SHELLY-1-24 (220V) -- ON --> alim DC 24V
                                   |
                                   v
                           SHELLY-1-MOT (24V) -- ON --> alim moteur
                                                              |
                                                              v
                                                      SHELLY-1-UPDN (24V) -- relais SPDT --> DM556T DIR
                                                                                                |
                                                                                                v
                                                                                            moteur cimier
```

Détails complets (timings, gardes-fous, IPs DHCP, conventions DIR) dans la
spec :
[`docs/superpowers/specs/2026-05-23-cinematique-shelly-cimier-garde-fou-design.md`](../../docs/superpowers/specs/2026-05-23-cinematique-shelly-cimier-garde-fou-design.md).

Le Pico W n'a **aucune ligne STEP/DIR** vers le driver — son seul rôle
est de lire les 2 fins de course et de répondre à `GET /status`.

---

## Watchdog

Watchdog hardware RP2040 armé à **8000 ms** (`WDT_TIMEOUT_MS = 8000`,
`main.py` ligne 53). Si la boucle principale ne fait pas `wdt.feed()`
pendant 8 s, le Pico reset automatiquement.

Fenêtre de **safe-boot 3 s** au démarrage (`safe_boot_window()`) :
permet de reprendre la main en REPL via `mpremote` ou minicom si le
firmware bug juste après boot. Pendant cette fenêtre, le WDT n'est PAS
encore armé.

---

## Versions

| Version | Date | Notes |
|---|---|---|
| 0.2.0 | 2026-05-23 | Pivot Shelly — firmware capteur-only, endpoints `/open`/`/close`/`/stop`/`/config`/`/diag` supprimés, WDT 8000 ms |
| 0.1.0 | Avril 2026 | Firmware initial (orchestration moteur côté Pico — déprécié) |
