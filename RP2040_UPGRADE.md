# Migration GPIO → RP2040

Guide pour passer du pilotage GPIO direct au pilotage via Pi Pico (RP2040).

## Pourquoi migrer

- **Precision** : PIO genere les impulsions avec precision 8 ns (vs timing Python variable)
- **Rampe firmware** : S-curve calculee sur le Pico, plus fluide
- **Arret immediat** : STOP interrompt le mouvement en cours instantanement
- **Libere le GPIO** : le Pi n'a plus besoin d'acces GPIO root pour le moteur

## Pre-requis

- Raspberry Pi Pico (RP2040) — avec ou sans Wi-Fi (~4€)
- Cable micro-USB **donnees** (pas juste alimentation)
- 3 fils Dupont femelle-femelle

## Etape 1 : Flasher le Pico

Suivre le guide complet : [firmware/README.md](firmware/README.md)

Resume rapide :
```bash
# 1. Telecharger MicroPython UF2 depuis micropython.org
# 2. BOOTSEL + brancher USB → copier le .uf2
# 3. Copier le firmware DriftApp :
cd firmware/
mpremote cp main.py :main.py
mpremote cp step_generator.py :step_generator.py
mpremote cp ramp.py :ramp.py
```

## Etape 2 : Brancher les fils

```
Pi Pico GP2  →  DM556T PUL+
Pi Pico GP3  →  DM556T DIR+
Pi Pico GND  →  DM556T PUL- et DIR-
```

**Deconnecter les fils GPIO du Raspberry Pi vers le DM556T** (ils ne sont plus utilises).

Detail complet : [firmware/README.md](firmware/README.md) section Branchements.

## Etape 3 : Modifier la configuration

```bash
# Verifier que le Pico est detecte
ls /dev/ttyACM*
# Doit afficher : /dev/ttyACM0
```

Editer `data/config.json` — trouver la section `motor_driver` et changer `"type"` :

```json
"motor_driver": {
    "type": "rp2040",
    "serial": {
        "port": "/dev/ttyACM0",
        "baudrate": 115200,
        "timeout": 2.0
    }
}
```

Si le port est different de `/dev/ttyACM0`, modifier `"port"` en consequence.

## Etape 4 : Redemarrer les services

```bash
sudo ./start_web.sh restart
```

Verifier dans les logs :
```bash
tail -f logs/motor_service_*.log
```

Chercher la ligne :
```
MoteurRP2040 initialise - Steps/tour coupole: 1941866
```

Si vous voyez `Fallback vers GPIO direct`, le port serie n'est pas accessible — verifier l'Etape 1.

## Verification

1. Ouvrir l'interface web : `http://raspberrypi:8000`
2. Faire un GOTO manuel (ex: 90°)
3. Verifier que le moteur tourne
4. Dans les logs, les commandes `MOVE` doivent apparaitre

## Retour arriere

Pour revenir au pilotage GPIO direct :

1. Editer `data/config.json`
2. Changer `"type": "rp2040"` en `"type": "gpio"`
3. Rebrancher les fils GPIO du Pi vers le DM556T
4. Redemarrer : `sudo ./start_web.sh restart`

Le fallback est instantane — pas besoin de reflasher quoi que ce soit.

## Depannage

Voir [firmware/README.md](firmware/README.md) section Depannage pour :
- Pico non detecte (`/dev/ttyACM0` absent)
- Permission denied sur `/dev/ttyACM0`
- Moteur ne tourne pas
- Reset complet du Pico
