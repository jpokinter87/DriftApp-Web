# Cimier tout-Shelly (suppression Pico W) — Design V3

**Date :** 2026-06-08
**Statut :** validé (brainstorming)
**Source matérielle :** `docs/synoptique electronique cimier V3.pdf` (4 pages : synoptique, plan d'adressage IP, cinématique, dynamique d'alimentation)
**Chantier :** cimier en cours → **pas de bump de version**

---

## 1. Contexte et motivation

L'architecture cimier précédente (pivot Shelly v6.x) reposait sur un **Pico W** servant de
serveur de capteurs HTTP (`GET /status` → `open_switch` / `closed_switch`), plus 2 Shelly
moteur (MOT + DIR) et 1 Shelly d'alimentation. Le Pico W a été une source de problèmes
récurrents (firmware, câblage, court-circuit ayant grillé un module, fiabilité).

Serge a conçu une **nouvelle architecture (V3) plus simple qui supprime totalement le Pico W**.
Le mouvement est désormais généré par un **Contrôleur autonome** (carte générateur d'impulsions
STEP à potentiomètre) pilotant le driver DM556T. Le Raspberry Pi se borne à **piloter ce
contrôleur à distance via des Shelly** : marche/arrêt moteur, sens, et lecture des fins de course.

### Ce qui disparaît
- **Pico W** et tout son firmware (`firmware/cimier/`).
- Le client HTTP Pico (`HttpClient`, appels `/status` et `/info`) dans `cimier_service`.
- La sécurité butées hardware **74HC00** (abandonnée — remplacée par une coupure directe des
  microswitches sur le contrôleur, cf. §6).

### Ce qui le remplace
- Un **Shelly Uni+** lit les 2 microswitches (Haut/Bas) via RPC `Input.GetStatus`.
- Le Contrôleur autonome + DM556T génèrent le mouvement (vitesse réglée au potentiomètre — le
  Pi ne contrôle ni vitesse ni nombre de pas).

---

## 2. Plan d'adressage IP (valeurs terrain → `data/config.json`, jamais en dur)

| Shelly | IP | API | Rôle |
|--------|------|--------|------|
| SHELLY-1-12V | 192.168.1.82 | legacy `/relay/0?turn=on\|off` | Alim 12V — **permanent** (réveillé par cascade, jamais coupé par DriftApp) |
| SHELLY-1-24V | 192.168.1.83 | legacy | **Alim module cimier — manœuvré à chaque cycle (ON début / OFF fin)** |
| SHELLY-UNI+ | 192.168.1.84 | **rpc** `/rpc/Input.GetStatus?id=N` | Lecture butées : `id=0` → BAS, `id=1` → HAUT |
| SHELLY-1-MOT | 192.168.1.85 | legacy | Marche/arrêt moteur |
| SHELLY-1-UPDN | 192.168.1.86 | legacy | Sens (UP / DN) |

### Conventions relais (documentées V3 — **à valider au banc**, restent configurables)
- **SHELLY-1-MOT** : logique « moteur tourne = relais `turn=on` ; moteur arrêté = relais `turn=off` ».
  → `motor_on_relay_state=true`. ⚠️ **Inverse** la valeur pré-positionnée actuelle (`false`) :
  le synoptique V3 porte une note « ATTENTION logique inversée » + une formulation ambiguë
  (« contact fermé → switch à ON »). On ne fige pas l'hypothèse : paramètre configurable,
  convention tranchée par Serge au banc.
- **SHELLY-1-UPDN** : UP (ouverture) = `turn=on` ; DN (fermeture) = `turn=off`.
  → `open_dir_state=true`. ⚠️ **Inverse** aussi la valeur actuelle (`false`). Idem : validé au banc.

### Sémantique capteurs Uni+ (documentée V3 — **à valider au banc**, configurable)
- `Input.GetStatus → state=True` = « Ouvert » = contact ouvert = **PAS en butée**.
- `state=False` = « fermé » = **butée atteinte**.
- Donc : `open_switch = NOT input(HAUT id=1)` ; `closed_switch = NOT input(BAS id=0)`.
- Le synoptique contient une note potentiellement contradictoire ; l'inversion (`invert`) et le
  mapping d'ids sont donc **des paramètres**, pas des constantes. Convention par défaut = celle
  ci-dessus ; Serge confirme au banc.

---

## 3. Cinématique (V3) — déjà couverte par `_run_cycle`

La cinématique documentée correspond **quasi exactement** au flux 9-phases existant de
`services/cimier_service.py:_run_cycle`. Aucune refonte de la machine d'états : on vérifie le
mapping des conventions et on change la **source de lecture des capteurs**.

**Ouverture** (fermeture symétrique avec UPDN/DN et butée BAS) :
1. `SHELLY-1-24V/ON` — alimentation du module cimier.
2. Attente `shelly_settle_s` (~2 s) — appairage WiFi des Shelly du boîtier.
3. `SHELLY-1-MOT` à l'état « moteur arrêté » (défensif, état connu).
4. `SHELLY-1-UPDN/UP` — sens montée.
5. **Préflight** : lire HAUT. Si déjà en butée (fermé) → fin (no-op). Sinon → suite.
6. `SHELLY-1-MOT` → démarrage moteur.
7. **Poll HAUT toutes les 100 ms** (`ShellySwitchReader`).
8. `SHELLY-1-MOT` → arrêt moteur dès butée HAUT atteinte.
9. `SHELLY-1-24V/OFF` — coupure alimentation (toujours, cf. §6).

**Stop** : arrêt moteur immédiat (+ coupure 24V garantie via `finally`).

---

## 4. Composants logiciels

### 4.1 Fichiers touchés

| Fichier | Action | Détail |
|---------|--------|--------|
| `core/hardware/shelly_switch_reader.py` | **créer** | `ShellySwitchReader` + `NoopSwitchReader` |
| `core/config/config_loader.py` | modifier | `SwitchReaderConfig` ; `CimierConfig.switch_reader` ; retrait `host`/`port` Pico |
| `services/cimier_service.py` | modifier | injecter le reader à la place de `HttpClient` dans préflight + poll ; retrait `/status`/`/info` Pico |
| `cimier_simulator.py` | modifier | simuler Uni+ (RPC) + relais MOT/UPDN/24V au lieu du Pico W |
| `firmware/cimier/` | **supprimer** | firmware MicroPython mort (`main.py`, `cimier_controller.py`, `step_generator.py`, `README.md`, `secrets.py`) |
| `data/config.json` | modifier | section `cimier` à la nouvelle forme (template repo, `enabled=false`) |
| `tests/` | maj | cf. §7 |
| `CLAUDE.md` | maj | archi cimier, plan IP, cinématique ; retrait références Pico ; commit PDF V3 |

### 4.2 Réutilisés tels quels (zéro modif fonctionnelle)
`core/hardware/motor_shelly.py` (MOT + UPDN), `core/hardware/power_switch.py` (24V),
`services/cimier_scheduler.py`, `core/observatoire/sun_altitude.py`,
`services/motor_ipc_writer.py`, `services/cimier_ipc_manager.py`,
endpoints Django `web/cimier/`, UI dashboard, IPC `/dev/shm/cimier_*.json`.

### 4.3 `ShellySwitchReader` — interface

```
ShellySwitchReader(
    host: str,
    api: str = "rpc",
    open_input_id: int = 1,      # HAUT
    closed_input_id: int = 0,    # BAS
    invert: bool = True,         # True : input False = butée atteinte
    timeout: float = 3.0,
)

read() -> SwitchState        # {open_switch, closed_switch, both_switches, raw}
```

- Émet `GET http://<host>/rpc/Input.GetStatus?id=<open_input_id>` et `<closed_input_id>`.
- Applique `invert` pour dériver `open_switch` / `closed_switch`.
- `both_switches = open_switch and closed_switch` (anomalie → §6).
- Lève `SwitchReaderError` sur erreur réseau / HTTP ≠ 200 / JSON invalide.
- `NoopSwitchReader` : doublure inerte (dev/tests), `read()` renvoie un état configurable.
- Patron calqué sur `ShellyPowerSwitch` / `MotorShelly` (mêmes conventions, mêmes erreurs).

### 4.4 Nouvelle forme de `cimier` dans `config.json`

- **Ajout** `switch_reader` : `{ type: "shelly_uni"|"noop", host, api: "rpc", open_input_id, closed_input_id, invert, timeout }`.
- **`power_switch`** repointé sur SHELLY-1-24V (.83, `api: "legacy"`).
- **`motor_shelly`** : `host_motor` .85, `host_dir` .86, `api: "legacy"`,
  `motor_on_relay_state` et `open_dir_state` selon §2 (à valider banc).
- **Retrait** des clés Pico `host` / `port` (et `invert_direction` legacy si inutilisé).
- Template repo : `enabled=false`, hôtes vides / `noop` → aucune incidence prod/dev par défaut.
- Valeurs terrain réelles documentées dans `CLAUDE.md` (section migration), pas dans le template.

---

## 5. Flux de données (inchangé hors transport capteur)

```
Django POST /api/cimier/{open,close,stop}
   → /dev/shm/cimier_command.json
       → cimier_service.tick() → _run_cycle()
            ├─ ShellyPowerSwitch(24V .83)      ON/OFF
            ├─ MotorShelly(MOT .85 / UPDN .86) marche/arrêt + sens
            └─ ShellySwitchReader(Uni+ .84)    préflight + poll 100 ms
       → /dev/shm/cimier_status.json
   → Django GET /api/cimier/status/ → UI dashboard
```

Scheduler astropy (modes manual/semi/full), countdown UI, parking-session, cascade
tracking↔cimier : **inchangés**.

---

## 6. Sécurité

- **Invariants `finally`** : `SHELLY-1-24V/OFF` **et** moteur arrêté garantis sur fin nominale,
  `stop`, erreur ou `cycle_timeout_s`.
- **Backstop hardware** : les microswitches coupent **directement** le Contrôleur/DM556T
  (réponse terrain Serge). Le stop logiciel (poll 100 ms) reste **primaire** (arrêt propre) ; le
  hardware est le filet de sécurité. Le module 74HC00 est **abandonné** (sort du projet).
- **`both_switches`** (deux butées « fermées » simultanément) → erreur, abort, coupure 24V.
- **`SwitchReaderError`** pendant préflight/poll → abort + coupure 24V garantie.
- `cycle_timeout_s` conservé.

---

## 7. Tests

- **Créer** `tests/test_shelly_switch_reader.py` : parsing RPC, inversion (`invert` true/false),
  mapping d'ids, `both_switches`, erreurs réseau/HTTP/JSON, `NoopSwitchReader`. (`urlopen` mocké.)
- **Adapter** `tests/test_cimier_service.py` : injecter un faux reader (au lieu du `HttpClient`
  Pico) ; préflight, poll, transitions, timeout, both_switches, invariants `finally`.
- **Adapter** `tests/test_config_loader.py` : `SwitchReaderConfig`, nouvelle forme `cimier`,
  rétro-compat (clés Pico ignorées).
- **Adapter** `tests/test_cimier_simulator.py` + `tests/test_cimier_mechanism_sim.py` : Uni+ RPC
  + relais simulés ; cycle ouverture/fermeture jouable en `CIMIER_DEV_MODE=1`.
- **Retirer** les tests propres au firmware/Pico devenus sans objet.
- **Inchangés** : `tests/test_cimier_scheduler.py`, `tests/test_web_cimier_views.py`.
- Critère de succès : suite cimier verte + cycle complet jouable en dev sans hardware.

---

## 8. Hors périmètre (YAGNI)

- **Cascade 220V→12V** : la Konyks 3 (manuelle, allumée par Serge) amène le 220V ; SHELLY-1-220V
  réveille SHELLY-1-12V (permanent sur batterie) qui alimente SHELLY-1-24V en cascade. DriftApp ne
  manœuvre **que** le 24V par cycle. Le réveil 220V→12V est manuel + Shelly-natif.
- **Capteur de pluie** cimier (backlog séparé `project_cimier_weather_rain_backlog`).
- **Modes d'automation** (scheduler) : inchangés.
- **Bump de version** : non (chantier cimier en cours).

---

## 9. Critères de succès

1. `firmware/cimier/` et tout le code/transport Pico supprimés ; aucune référence résiduelle.
2. `ShellySwitchReader` lit l'Uni+ (RPC), inversion + mapping configurables, couvert par tests.
3. `_run_cycle` exécute la cinématique V3 (ouverture/fermeture/stop) via 24V + MOT + UPDN + Uni+,
   invariants de sécurité préservés.
4. Cycle complet jouable en `CIMIER_DEV_MODE=1` (simulateur Uni+/relais), sans hardware.
5. Suite de tests cimier verte ; conventions terrain (`invert`, `motor_on_relay_state`,
   `open_dir_state`) restées configurables et documentées pour validation banc par Serge.
