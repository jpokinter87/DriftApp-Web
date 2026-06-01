# Spec — Capteur de pluie cimier (V1 météo)

**Date** : 2026-05-31 (rév. 2026-06-01 : matériel arrêté)
**Auteur** : JP (cadrage) + Claude
**Statut** : design validé, matériel arrêté, à planifier
**Périmètre** : adjonction d'un capteur de pluie pour parfaire l'automatisation du cimier (refus d'ouverture + fermeture d'urgence). Première brique du milestone « capteurs météo » (v6.4+ pressenti dans `core/hardware/weather_provider.py`).

> **Rév. 2026-06-01** — Serge dispose déjà d'un **module AZDelivery « raindrops »** (sérigraphie MH-RD, famille FC-37/YL-83, comparateur LM393). Datasheet : `docs/AZdelivery raindrops module.pdf`. Vérifié **compatible** avec l'approche A retenue (sortie numérique TOR sur GPIO du Pi). La section 2 ci-dessous est mise à jour avec ce matériel concret et son câblage exact ; l'architecture software (§3-4) est **inchangée**.

***

## 1. Contexte & objectif

Le cimier (toit ouvrant de la coupole) est désormais piloté par cascade Shelly + sécurité butées hardware 74HC00 (cf. `project_cimier_shelly_pivot_definitive_spec`). L'automatisation début/fin de session repose sur les éphémérides (`cimier_scheduler`). Le software anticipe déjà une abstraction météo (`WeatherProvider` : `is_safe_to_open` / `is_safe_to_keep_open` / `describe`), mais seul `NoopWeatherProvider` (toujours OK) existe.

**Objectif V1** : brancher un **capteur de pluie réel** pour :

1. **interdire l'ouverture auto** quand il pleut ;
2. **fermer le cimier en urgence** si la pluie survient alors qu'il est ouvert (protection optique).

**Hors V1** : nuages (IR), vent, humidité/luminosité ; repli hardware pluie ; retrait du Pico W.

### Décisions d'architecture actées (cadrage 2026-05-31)

* **Hôte du capteur = le Raspberry Pi directement** (GPIO), PAS le RP2040. Le Pi + RP2040 sont **fixes au bâti** ; le capteur de pluie (fixé au bâti) se câble donc directement au Pi, sans interface de rotation. Le RP2040 reste dédié à la génération de pas temps-réel (PIO) — on ne mêle pas une tâche temps-réel critique à de la lecture capteur lente.
* **Approche A retenue** (capteur sur GPIO du Pi) plutôt que B (Pico W WiFi recyclé) ou C (entrée Shelly) : le moins de pièces, latence pluie→fermeture minimale, zéro hop WiFi, entièrement testable en dev. Aligné avec la volonté de **simplifier** (et de pouvoir retirer le Pico W ultérieurement).

***

## 2. Matériel & câblage

### Matériel retenu (V1) : module AZDelivery « raindrops » (MH-RD / FC-37)

Serge dispose déjà de ce module → **coût nul, disponible immédiatement, valide tout le pipeline software**. Datasheet : `docs/AZdelivery raindrops module.pdf`.

| Caractéristique            | Valeur (datasheet)                                                                                                 |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Composition                | carte de détection (grille résistive, sans polarité) + carte de contrôle (comparateur **LM393** + trimpot + 2 LED) |
| Alimentation               | 3,3 V à 5 V — **on alimente en 3,3 V** (voir câblage)                                                              |
| Consommation               | 8 mA                                                                                                               |
| Sorties                    | **D0** (numérique TOR) + **A0** (analogique 0-1023)                                                                |
| Réglage du seuil pluie/sec | **matériel**, par le trimpot embarqué (sens horaire = plus sensible)                                               |

* **On n'utilise que la sortie numérique** **`D0`.** La sortie analogique `A0` est **inexploitable directement** (le Raspberry Pi n'a pas d'ADC ; il faudrait un MCP3008 — hors périmètre). C'est cohérent avec l'approche A (lecture TOR sur GPIO).
* Le **seuil de déclenchement est réglé en hardware** (trimpot du LM393), pas en software. Le provider (§3) ne fait que lire l'état TOR déjà comparé.

### Câblage Pi (confirmé datasheet, §« Connexion au Raspberry Pi »)

| Broche module | Pi                                               | Remarque                                                                                                                                  |
| ------------- | ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **VCC**       | **3V3** (broche physique 1 ou 17)                | ⚠️ **Surtout pas 5V** : le GPIO du Pi n'est **pas** 5V-tolérant. Alimenté en 3,3 V, `D0` ne sort que du 0-3,3 V → sûr pour l'entrée GPIO. |
| **GND**       | **GND**                                          | masse commune                                                                                                                             |
| **D0**        | **un GPIO d'entrée libre** (BCM à fixer terrain) | pull-up interne activé par sécurité (sortie LM393 généralement push-pull)                                                                 |
| A0            | *non connecté*                                   | Pi sans ADC                                                                                                                               |

* **Polarité confirmée par la datasheet** : code d'exemple `if GPIO.input(pin) == 0: print('Raining!')` → **`D0 = niveau BAS quand il pleut`**. La convention `active_low = true` de la spec est donc **validée par le matériel** (rien à changer côté §3).
* **Choix du GPIO — conflit à éviter** : la datasheet propose BCM18, **à NE PAS retenir**. En mode driver moteur `gpio`, le projet utilise `dir_pin = BCM17` et `step_pin = BCM18` (`core/config/config.py`, `core/hardware/motor_config_parser.py`). La prod tourne en `rp2040` (série USB) donc BCM17/18 sont libres *aujourd'hui*, mais les choisir créerait un **conflit latent** en cas de retour au mode `gpio`. → **Retenir un autre BCM d'entrée libre** (p. ex. BCM5/6/13/16/26), distinct des broches moteur, de l'encodeur EMS22A (SPI) et de l'I2C/SPI. À fixer avec Serge.
* **Backend logiciel** : la datasheet illustre `RPi.GPIO`, mais notre stack lit via **`lgpio`** (déjà utilisé, support Pi 5) ; sémantique identique. Aucune adhérence à `RPi.GPIO`.
* Capteur fixé au bâti (partie immobile), câble tiré jusqu'au Pi. Seul `cimier_service` réclame cette ligne d'entrée.

### Longévité (à surveiller)

La grille résistive FC-37 **vieillit mal en extérieur** (corrosion électrolytique des pistes sous tension continue permanente). Acceptable pour la V1 (validation + protection réelle immédiate), mais à surveiller. Pistes d'atténuation, **hors V1** : (a) alimentation **intermittente** de la carte via une broche GPIO + MOSFET (réduit la corrosion — la datasheet évoque une broche `SENSOR_POWER`, mais nécessite un transistor) ; (b) bascule vers un capteur optique extérieur robuste **Hydreon RG-9/RG-11** (sortie contact sec → **même provider, même câblage TOR**, migration triviale). Le contrat `WeatherProvider` rend ce remplacement transparent.

***

## 3. Brique logicielle `GpioRainWeatherProvider`

Nouveau provider dans `core/hardware/weather_provider.py`, implémentant le **contrat existant** `WeatherProvider` (aucun changement pour les consommateurs).

### Interface (inchangée)

* `is_safe_to_open() -> bool`
* `is_safe_to_keep_open() -> bool`
* `describe() -> dict`

### Comportement

* **Lecture GPIO** via `lgpio` (déjà dépendance `aarch64`), avec **import paresseux** + **backend injectable** : en dev x86 / simulation, on injecte un faux lecteur → pas de dépendance dure, testable hors Pi. (Copie du pattern `power_switch.py` / `SerialSimulator`.)
* **`is_safe_to_keep_open()`** : repasse `False` **immédiatement** dès détection pluie (réaction rapide pour fermeture d'urgence).
* **`is_safe_to_open()`** : ne revient `True` qu'après un **délai sec** `clear_delay_s` écoulé depuis la dernière détection pluie (le capteur reste humide un moment — on évite de rouvrir juste après une averse).
* **Anti-rebond** : une lecture stable sur N échantillons (ou debounce temporel) avant de considérer un changement d'état, pour ignorer les transitoires.
* **`describe()`** : dict opaque pour logs/UI, ex. `{"provider": "rain_gpio", "raining": bool, "last_rain_ts": iso|null, "dry_since_s": float|null}`.
* **Robustesse** : une erreur de lecture GPIO ne doit jamais lever vers les consommateurs en faisant « ouvrir par défaut » — en cas d'incertitude, le provider considère **non sûr** (fail-safe : on protège l'optique). À tracer dans `describe()`.

### Configuration (`data/config.json`, section `weather_provider` étendue)

```JSON
{
  "weather_provider": {
    "type": "rain_gpio",
    "gpio_pin": 0,
    "active_low": true,
    "clear_delay_s": 600.0,
    "debounce_samples": 3
  }
}
```

* `type` : `"noop"` (défaut actuel) | `"rain_gpio"` (nouveau). Factory `make_weather_provider` enrichie ; type inconnu → erreur explicite (déjà le cas).
* `gpio_pin` : BCM, défaut neutre `0` (à renseigner terrain). **Aucune valeur en dur dans le code** (conforme `feedback_no_hardcoded_ips`). **Éviter BCM17/18** (réservés `dir_pin`/`step_pin` du mode driver moteur `gpio` — cf. §2).
* `active_low` : défaut `true` — **confirmé par le matériel** (le module MH-RD sort `D0 = BAS` quand il pleut).
* `clear_delay_s`, `debounce_samples` : defaults rétro-compatibles. **Purement software** : le *seuil* pluie/sec, lui, est réglé en **matériel** (trimpot LM393) et n'apparaît pas en config — `debounce_samples` ne fait que filtrer les transitoires du TOR déjà comparé.
* `WeatherProviderConfig` (dans `core/config/config_loader.py`) étendu + parser des nouveaux champs.

***

## 4. Flux de contrôle

### 4.1 Blocage de l'ouverture auto — *déjà câblé*

`services/cimier_scheduler.py` consulte déjà `is_safe_to_open()` avant l'ouverture au crépuscule (renvoie `SchedulerDecision("skip:weather", …)` + log `reason=weather_unsafe`). Avec le provider pluie actif, l'ouverture auto est refusée tant qu'il pleut / que le délai sec n'est pas écoulé. **Aucun recâblage** — seule l'activation du provider via config suffit.

### 4.2 Fermeture d'urgence sur pluie — *à ajouter*

Point clé de protection. **Veille dédiée à intervalle court** dans `cimier_service`, séparée du tick scheduler 60 s (trop lent pour la pluie) :

* nouvelle unité (thread/loop) interrogeant `is_safe_to_keep_open()` toutes les `rain_watch_interval_s` (≈ 5–10 s, **nouvelle clé dans la section** **`cimier`** **de** **`config.json`** — c'est une cadence de surveillance propre à `cimier_service`, pas un paramètre du provider) ;
* si `False` **et** cimier ouvert (ou en cours d'ouverture) → déclenche **la séquence de fermeture existante** (identique au close du lever de soleil) : `tracking_stop` → `goto 45°` (parking) → `close` ;
* log structuré `cimier_event=rain_emergency_close …` ;
* unité isolée, une seule responsabilité, testable indépendamment ;
* garde-fou anti-répétition : ne pas re-déclencher la fermeture si déjà fermé / en cours de fermeture.

**Latence pire cas** : `rain_watch_interval_s` (≤ 10 s) + durée fermeture (\~47 s) ≈ < 1 min après début de pluie. Acceptable pour la protection optique.

***

## 5. Simulation & tests

### Simulation dev (priorité : limiter les allers-retours terrain — `feedback_simulation_dev`)

* Faux capteur injectable + **toggle dev** pour forcer « pluie » sans matériel : env-var `CIMIER_DEV_RAIN=1` (cohérent avec `CIMIER_DEV_MODE`) et/ou un petit endpoint debug. Permet d'exercer **tout le pipeline** en dev : refus d'ouverture, fermeture d'urgence, état UI.

### Tests pytest (TDD, périmètre cimier)

* `GpioRainWeatherProvider` (fake GPIO injecté) : transitions sec↔pluie, `clear_delay_s`, anti-rebond, fail-safe sur erreur de lecture.
* Factory `make_weather_provider` : `type="rain_gpio"` instancie le bon provider ; type inconnu → `ValueError`.
* `config_loader` : parsing de la section `weather_provider` étendue + defaults rétro-compatibles.
* Intégration : « pluie pendant cimier ouvert → séquence de fermeture appelée » (via simulator, caplog `services.cimier_service`).
* Régression : suite cimier verte (`tests/test_weather_provider.py`, `tests/test_cimier_scheduler.py`, `tests/test_cimier_service.py`, `tests/test_config_loader.py`).

***

## 6. Limites de périmètre (V1)

* **Pas de repli hardware pluie** : la protection est software. Acceptable car la pluie est à l'échelle de la minute, et le risque mécanique grave (pousser dans la butée) est déjà couvert par le 74HC00. Un interlock matériel pluie reste un éventuel futur.
* **Retrait du Pico W = chantier séparé**, indépendant de ce travail. ⚠️ Si le Pico W est retiré plus tard, les 2 fins de course (lues aujourd'hui par lui pour l'UI) devront être recâblées sur le Pi pour conserver l'affichage — à traiter dans ce chantier-là, pas ici.
* **Nuages (IR MLX90614), vent (anémomètre), humidité/luminosité** : hors V1 (approche B ou capteurs I2C sur le Pi, plus tard). Le contrat `WeatherProvider` et la config sont conçus pour les accueillir sans casser l'existant.

***

## 7. UI (optionnel V1, à confirmer)

Exposer l'état pluie dans `cimier_status.json` (via `describe()`) et un indicateur dashboard « météo : pluie / sec ». Peu coûteux mais non bloquant ; peut être différé.

***

## 8. Fichiers impactés (prévision)

* `core/hardware/weather_provider.py` — ajout `GpioRainWeatherProvider` + enrichissement factory.
* `core/config/config_loader.py` — `WeatherProviderConfig` étendu + parser.
* `services/cimier_service.py` — veille fermeture d'urgence (unité dédiée) + activation provider.
* `data/config.json` — section `weather_provider` (type `rain_gpio` + champs), défauts neutres.
* `tests/test_weather_provider.py`, `tests/test_config_loader.py`, `tests/test_cimier_service.py` — couverture.
* Doc : `firmware/cimier/README.md` ou `CLAUDE.md` (note câblage capteur AZDelivery MH-RD : VCC→3V3, GND→GND, D0→BCM libre ≠ 17/18 ; renvoi vers `docs/AZdelivery raindrops module.pdf`) — mineur.

## 9. Critères de succès

* En dev (toggle pluie) : ouverture auto refusée pendant « pluie » ; cimier ouvert → fermeture d'urgence déclenchée < 1 min ; réouverture seulement après `clear_delay_s` sec.
* Suite pytest cimier verte (nouveaux tests + régression).
* Aucune valeur terrain en dur (pin/seuils en config).
* Provider `noop` reste le défaut (rétro-compat stricte tant que `type` non basculé).
* Validation terrain Serge :
  * câblage **VCC sur 3V3** (jamais 5V) + D0 sur un BCM libre ≠ 17/18 ;
  * polarité réelle vérifiée au multimètre/log : grille sèche → `D0` HAUT, grille mouillée → `D0` BAS (sinon ajuster `active_low`) ;
  * réglage du **trimpot** pour que quelques gouttes franchissent le seuil ;
  * test averse simulée (arrosoir) → fermeture d'urgence effective < 1 min.

