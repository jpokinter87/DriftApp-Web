# Cinématique Shelly cimier + garde-fou « déjà en butée » — Design

- **Date** : 2026-05-23
- **Statut** : Design validé pour relecture — **implémentation différée** (Serge attend son contrôleur ; les 2 Shelly 1 Gen 3 ne sont pas encore commandés/adressés).
- **Périmètre** : (1) orchestration de la cinématique Shelly dans `cimier_service` en **remplacement définitif** du flux piloté Pico ; (2) garde-fou de sécurité symétrique ; (3) **élagage du firmware Pico W** en serveur de capteurs ; (4) refonte du simulateur ; (5) logging de développement.
- **Origine** : synoptique `docs/synoptique electronique cimier.docx` (Serge) + historique `.paul/HANDOFF-2026-05-{06,08,12,15}*.md`.

---

## 1. Contexte & origine du pivot

Architecture **originale** : Pico W → STEP/DIR → driver DM556T (calquée sur le RP2040 de la coupole qui tourne en prod). Le moteur cimier **n'a jamais tourné** malgré ~2 semaines de bring-up terrain (Darlington ULN2803, réhausseur 3,3→5 V, commun anode puis commun cathode direct). Le firmware émet pourtant des pulses STEP corrects (1772 mesurés le 07/05). Détail dans les handoffs Paul.

**Pivot validé le 15/05, désormais définitif** : automatiser le **circuit de commande manuel de Serge** (oscillateur + interrupteurs ON/OFF + DPDT direction) — qui fait tourner le moteur de façon reproductible — via **2 Shelly 1 Gen 3** (contacts secs). Le Pico W est **rétrogradé en serveur HTTP de capteurs** : il ne lit plus que les fins de course haut/bas et expose `/status`. **Aucune rétro-compatibilité avec le flux Pico n'est conservée** : le pilotage STEP/DIR est abandonné, code et firmware correspondants sont supprimés.

Le cimier est un **mécanisme binaire ouvert/fermé** : 2 fins de course, vitesse fixe (potard de l'oscillateur), aucune précision pas-à-pas requise. La position vient des butées mécaniques, pas du comptage de pas.

**Déjà livré** (commit `012b494`) : le driver bas-niveau `core/hardware/motor_shelly.py` (`MotorShelly`) + `MotorShellyConfig` + tests + section `data/config.json → cimier.motor_shelly`. **Cette spec** couvre la couche au-dessus + l'élagage firmware.

---

## 2. Cartographie synoptique ↔ code

| Élément synoptique Serge | IP (provisoire) | Logique | Modèle code | Convention config actuelle |
|---|---|---|---|---|
| SHELLY-1-24 — alim module cimier | 192.168.1.83 | turn=on → module sous tension | `cimier.power_switch` (Shelly Gen 1) | `type:"noop"` (dev) / `shelly_gen1` (prod), host .83 |
| SHELLY-1-MOT — moteur On/Off | 192.168.1.85 | **inversée** : turn=off → moteur ON | `cimier.motor_shelly.host_motor` | `motor_on_relay_state:false` ✓ |
| SHELLY-1-UPDN — sens Up/Down (+ DPDT externe) | 192.168.1.86 | UP : turn=on / DN : turn=off | `cimier.motor_shelly.host_dir` | `open_dir_state:false` ⚠️ (voir §9) |
| SHELLY-1-12 — 12 V + Konyks 3 — 220 V | 192.168.1.82 / — | alim logique / secteur | **hors scope logiciel** | gérés hardware (toujours-on) |
| Fins de course haut / bas | — | NC + pull-up | Pico W `/status` → `open_switch` / `closed_switch` | — |

**IPs** : les adresses du synoptique sont **provisoires**. Les IPs définitives des 2 Shelly moteur seront attribuées en DHCP statique quand Serge les aura commandés ; `host_motor` / `host_dir` restent vides dans `data/config.json` jusque-là (cf. règle `feedback_no_hardcoded_ips` : aucune IP terrain en dur dans le code).

---

## 3. Cinématique cible

`cimier_service._run_cycle` est **réécrit** pour la séquence Shelly (l'ancien pipeline `push_config` + `_post_action /open|/close` + `_poll_cycle_complete` vs `pico_state` est supprimé). La direction n'est plus poussée au Pico (`/config invert_direction` disparaît) : elle est portée par le relais Shelly DIR + la convention `open_dir_state`.

### 3.0 Pré-vol — garde-fou (voir §4)

En **tout début de cycle**, avant toute action électrique, lecture des fins de course via le `/status` du Pico W (supposé **toujours alimenté**) :

- `open` demandé **et** `open_switch=True` → **no-op immédiat** : aucune alim, aucun moteur ; publication `state=open`, `phase=idle`. Fin de cycle.
- `close` demandé **et** `closed_switch=True` → no-op immédiat symétrique ; `state=closed`.
- **les deux switches True** → `state=error` (`both_switches_triggered`), aucun mouvement.
- `/status` injoignable au pré-vol → **abort prudent** (`error_message="precheck_unreachable"`), aucun mouvement (on refuse d'énergiser le moteur sans connaître l'état des butées).

### 3.1 Ouverture (cas nominal, cible pas encore atteinte)

1. `power_switch.turn_on()` → SHELLY-1-24/ON (alim module).
2. **Attente `shelly_settle_s`** (~2 s, « à mesurer » synoptique) → appairage WiFi des Shelly.
3. `motor_shelly.set_direction(open_direction=True)` → SHELLY-1-UPDN/UP.
4. `motor_shelly.turn_on(timer_s=timer_safety_sec)` → SHELLY-1-MOT/OFF (démarrage moteur + filet hardware Shelly `toggle_after`, indépendant du Pi en cas de WiFi-drop).
5. **Surveillance** `/status` jusqu'à `open_switch=True` (ou `cycle_timeout_s`, ou commande `stop`).
6. `motor_shelly.turn_off()` → SHELLY-1-MOT/ON (arrêt moteur).
7. `power_switch.turn_off()` → SHELLY-1-24/OFF.

### 3.2 Fermeture

Symétrique : `set_direction(open_direction=False)` (SHELLY-1-UPDN/DN), surveillance `closed_switch`.

### 3.3 Stop

`motor_shelly.turn_off()` + `power_switch.turn_off()`. Reçu pendant la surveillance (étape 5) ou hors cycle (no-op métier, comme aujourd'hui `_handle_stop`).

### 3.4 Invariant de sécurité 220 V

`power_switch.turn_off()` reste appelé **dans le `finally`** quelle que soit l'issue (timeout, erreur, stop) — invariant déjà en place dans `_run_cycle`, conservé. En cas d'échec en cours de cycle, on tente aussi `motor_shelly.turn_off()` avant de couper l'alim, pour ne jamais laisser le relais moteur dans l'état « tourne ».

---

## 4. Le garde-fou « déjà en butée »

### Objectif

Ne jamais énergiser le moteur si la fin de course de la **cible** est déjà atteinte → évite que le moteur force contre la butée. En archi Shelly il n'y a **plus de garde-fou firmware** (le Pico ne pilote plus le moteur), donc ce contrôle est **indispensable côté `cimier_service`**.

### Approche retenue : A — pré-vol avant énergisation

Lecture des fins de course **avant** d'armer la direction et d'allumer le relais moteur. Puisque le Pico W est **toujours alimenté**, le pré-vol se fait en **tête de cycle** (§3.0), avant même le power_on du module 24 V → un cycle « déjà en butée » ne consomme aucune action électrique.

> **Repli** : si le terrain montre que le Pico W est alimenté par le 24 V (et non en permanence), le pré-vol se déplace juste après le power_on + settle — toujours **avant** l'énergisation moteur. Le garde-fou reste effectif ; seul le no-op « zéro action électrique » est perdu.

### Symétrie

Couvre les **deux sens** (décision validée) : `open`+`open_switch` et `close`+`closed_switch`.

### Approches écartées

- **B — se reposer sur la surveillance (étape 5)** : ❌ le moteur est énergisé une fraction de seconde contre la butée le temps que le polling détecte la cible.
- **C — garde-fou firmware** : ❌ inopérant en archi Shelly (le firmware ne commande plus le relais).

### Défense en profondeur

1. Pré-vol `cimier_service` (primaire, cette spec).
2. `timer_safety_sec` Shelly (`toggle_after`) : coupe le moteur après N s même si le Pi décroche.
3. `cycle_timeout_s` côté `cimier_service`.
4. Résidu : état dérivé des switches côté Pico (`both_switches_triggered` → `error`).

---

## 5. Élagage du firmware Pico W

Le Pico W devient un **pur serveur de capteurs**. Suppression de tout le pilotage moteur.

| Fichier | Action |
|---|---|
| `firmware/cimier/step_generator.py` | **supprimé** (génération STEP/DIR : sans objet). |
| `firmware/cimier/cimier_controller.py` | **réduit** (~248 → ~80 LOC). **Garde** : lecture switches via adapter, `_refresh_state_from_switches` (→ `closed`/`open`/`error`/`unknown`), `to_status_dict`, `to_info_dict`. **Supprime** : `start_open`/`start_close`/`stop`/`tick`, `_begin/_abort/_end_cycle`, `set_invert_direction`/`invert_direction`, `_direction_for`, `steps_per_cycle`/`cycle_timeout_s`. |
| `firmware/cimier/main.py` | **allégé** (~400 → ~250 LOC). **Retire** : `PIN_STEP`/`PIN_DIR`, `SoftwareStepGenerator`, endpoints `/open` `/close` `/stop` `/config` `/diag/*`, le stepping `controller.tick()` dans `run_server`. **Garde** : WiFi (`pm=0xa11140`), WDT 8 s + `feed()`, serveur HTTP (`settimeout(0.05)`), `/status`, `/info`, lecture GP14/GP15, heartbeat. |
| `PicoHardwareAdapter` | garde `read_open_switch`/`read_closed_switch` ; retire `set_direction`/`pulse_step`. |
| `tests/test_cimier_controller.py` | refonte (~12 KB → ~5 KB) : ne teste plus que la dérivation d'état depuis les switches + sérialisation. |

**Correctifs HTTP/WDT validés terrain à conserver** (durement acquis, cf. handoffs) : `sock.settimeout(0.05)`, `wlan.config(pm=0xa11140)`, WDT 8000 ms feed à chaque tour de boucle. La boucle principale conserve son rythme (`run_server`) mais sans appel de stepping.

**Endpoints Pico après élagage** : `GET /status`, `GET /info` uniquement.

---

## 6. Configuration (`data/config.json → cimier`)

```json
{
  "shelly_settle_s": 2.0,          // attente appairage WiFi Shelly (synoptique "à mesurer")
  "verbose_logging": false,        // true → logs DEBUG par itération (voir §7)
  "motor_shelly": { /* déjà livré commit 012b494 — host_motor/host_dir/timer_safety_sec/... */ }
}
```

- **Pas** de commutateur `motor_driver` : la cinématique Shelly est l'unique orchestration.
- Clés Pico devenues sans objet à retirer/ignorer : `invert_direction` (la direction est portée par `motor_shelly.open_dir_state`). `cycle_timeout_s`, `boot_poll_timeout_s`, `post_off_quiet_s` restent pertinents (timeouts orchestration côté Pi).
- Factory `make_motor_shelly(cfg)` sur le pattern existant `make_power_switch(cfg)`.
- Aucune IP en dur (cf. `feedback_no_hardcoded_ips`).

---

## 7. Logging de développement (debug à distance)

Le site est à 800 km : les logs sont **le seul canal de diagnostic** quand un cycle se comporte mal. On rend la timeline d'un cycle entièrement reconstructible depuis `logs/cimier_service.log`.

**Convention** : réutilise le pattern existant `cimier_event=<event> clé=valeur …` (déjà en place dans `cimier_service.py`), logger Python standard, sortie `logs/cimier_service.log`.

**Niveaux**
- **INFO (toujours, prod incluse)** : décision pré-vol, transitions de phase avec durée, **chaque appel Shelly** (host, relais, état demandé, timer, status HTTP, **latence ms**), bascule de fin de course, début/fin de cycle avec durée totale et résultat, toutes les erreurs.
- **DEBUG (mode verbeux dev)** : chaque itération de polling (`open_switch`, `closed_switch`, position simulée si dispo, elapsed), décompte du settle, payload `/status` brut.

**Toggle verbeux** : actif si `cimier.verbose_logging=true` **ou** env-var `CIMIER_DEV_MODE=1` (déjà exportée par `start_dev.sh`). En dev → niveau DEBUG + log par itération ; en prod → INFO. (Réutilise l'infra dev-mode existante, pas de nouveau système.)

**Événements clés tracés**
- `cimier_event=preflight action=open open_switch=.. closed_switch=.. decision=noop|proceed|error reason=..`
- `cimier_event=shelly_call host=.. relay=.. on=.. timer_s=.. http_status=.. latency_ms=..` — **maillon nouveau et le plus à risque à distance** : un relais lent ou muet doit sauter aux yeux (émis pour chaque `set_direction`/`turn_on`/`turn_off`, chronométré par `cimier_service`).
- `cimier_event=switch_transition switch=open from=false to=true elapsed_ms=..`
- `cimier_event=phase phase=.. action=.. id=.. elapsed_ms=..`
- `cimier_event=cycle_end action=.. id=.. duration_ms=.. result=ok|timeout|error|noop|stopped error=..`

**Côté simulateur** (§8) : `cimier_sim=progress position=.. pct=.. moteur_on=.. sens=..` à intervalle régulier → la « course » du moteur virtuel est observable en dev exactement comme on voudrait l'observer sur le terrain.

`MotorShelly` reste pur (pas de logging interne lourd) ; c'est `cimier_service` qui chronomètre et journalise chaque appel (responsabilité d'orchestration).

---

## 8. Simulation précise (simulation-first, site à 800 km)

Calquée sur le pattern éprouvé du moteur coupole (`core/hardware/moteur_simule` ↔ `services/simulation.SimulatedDaemonReader`). Le simulateur cimier actuel fait avancer la position via `controller.tick()` (stepping firmware) — **caduc** (le firmware n'a plus de stepping, §5). Refonte :

```
        pilote (turn_on/dir)          lit (open/closed switch)
SimMotorShelly ───────────────▶  CimierMechanismSim  ◀─────────────── CimierSimulator (Pico capteurs)
   (relais moteur + dir)         (position, moteur_on,                 GET /status → switches
                                  sens ; avance dans le temps          dérivés de la position
                                  quand moteur_on)
```

- **`CimierMechanismSim`** (nouveau, analogue à `moteur_simule`) : état partagé — `position ∈ [0, course]`, `moteur_on`, `sens`. Boucle de progression : avance la position quand `moteur_on` (vitesse fixe paramétrable, latence réaliste). Fins de course dérivées : `open_switch = position >= course`, `closed_switch = position <= 0`. Logue `cimier_sim=progress …` (§7).
- **Shelly moteur simulé** : `MotorShelly` réel avec `urlopen` mocké pointant sur le mécanisme, **ou** `SimMotorShelly` léger qui écrit `moteur_on`/`sens`. (`MotorShelly(urlopen=…)` déjà injectable.)
- **`CimierSimulator`** (Pico capteurs) : lit les switches depuis le `CimierMechanismSim` au lieu de son `_VirtualHardwareAdapter` tick-driven. S'aligne sur le firmware élagué (`/status` + `/info` seulement).
- **États initiaux paramétrables** pour les tests : `closed` / `open` / `mid` / `both_switches` → rend **observables en dev** tous les cas du garde-fou (rejoint le backlog `project_v64_simulation_calibration_testable`).
- Conserve la latence boot (port non lié → ConnectionRefused).

---

## 9. Stratégie de tests (TDD)

Tout testable sans hardware (`MotorShelly.urlopen` et `cimier_service.http_client` déjà injectables) :

**Garde-fou (cœur de la demande)**
- `open` + `open_switch=True` → no-op, `state=open`, **0 appel** `set_direction`/`turn_on`, **0** `power_switch.turn_on`.
- `close` + `closed_switch=True` → no-op symétrique, `state=closed`.
- both switches True → `state=error`, aucun mouvement.
- `/status` injoignable au pré-vol → abort, aucun mouvement.

**Cinématique nominale**
- Ouverture complète : ordre d'appels `power_on → settle → set_direction(open) → turn_on(timer) → poll → turn_off → power_off`.
- Fermeture complète symétrique.
- `turn_off` + `power_off` toujours appelés (timeout, erreur, stop).
- `stop` pendant surveillance → `turn_off` immédiat.

**Refonte (suppression flux Pico)**
- `tests/test_cimier_service.py` **réécrit** pour le flux Shelly (les tests `push_config` / `_post_action /open|/close` / `pico_state` disparaissent).
- `tests/test_cimier_controller.py` **réduit** au capteur-only (§5).

**Simulation**
- Cycle bout-en-bout contre le `CimierMechanismSim` (position évolue, switch bascule, garde-fou déclenche sur état initial).

Périmètre pytest restreint aux modules touchés (cf. `feedback_tests_scope`) : `test_motor_shelly`, `test_cimier_service`, `test_cimier_simulator`, `test_cimier_controller`, `test_config_loader`, `test_power_switch`.

---

## 10. Points à confirmer avec Serge (avant implémentation/câblage)

1. **⚠️ Inversion sens `open_dir_state`** : le synoptique dit `UP (ouverture) = turn=on` (relais DIR **ON**), mais `config.json` a `open_dir_state:false` → `set_direction(open=True)` met le relais **OFF**. Contradiction apparente (sauf si le DPDT externe inverse). À lever **avant câblage** — type d'inversion qui force le moteur dans le mauvais sens contre une butée.
2. **Alim du Pico W** : permanente (hypothèse retenue → pré-vol en tête de cycle) ou via le 24 V du module (→ repli pré-vol après power_on) ? Détermine le placement exact du garde-fou.
3. **Latence stop HTTP** : mesurable seulement Shellys en main. Si elle dépasse la marge mécanique, ajouter un seuil d'anticipation côté `cimier_service` (le `timer_safety_sec=90` Shelly reste le filet).
4. **IPs définitives** des 2 Shelly moteur (DHCP statique) → remplir `host_motor`/`host_dir`.

---

## 11. Hors scope / différé

- **Déploiement terrain & bump version** : après implémentation + arrivée Shellys + test latence stop. Version pressentie 6.5.0 (ou 6.0.5 selon arbitrage milestone).
- **Modifs firmware héritées non commitées** (`firmware/cimier/main.py`, `step_generator.py`, datant du 14/05) : seront **écrasées** par l'élagage §5 ; à traiter dans le même commit firmware.

---

## 12. Critères de succès

- Garde-fou symétrique testé : aucun cas où le moteur est énergisé alors que la fin de course cible est déjà atteinte.
- Cinématique Shelly complète et conforme au synoptique, **unique** orchestration (plus de flux Pico).
- Firmware Pico W réduit au capteur-only (`/status` + `/info`), correctifs HTTP/WDT conservés, tests refondus verts.
- Logs : timeline d'un cycle entièrement reconstructible depuis `logs/cimier_service.log` (pré-vol, appels Shelly chronométrés, transitions switch, résultat) ; mode verbeux dev par itération.
- Simulation : cycle ouverture/fermeture + tous les cas du garde-fou observables en dev sans hardware.
- `ruff check` propre, IPs hors code, 0 régression sur les suites non liées.
