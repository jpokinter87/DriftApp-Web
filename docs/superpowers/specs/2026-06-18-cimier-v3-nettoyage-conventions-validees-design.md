# Cimier V3 — nettoyage des scories + intégration des conventions validées terrain

**Date** : 2026-06-18
**Branche** : `feat/cimier-script-manuel`
**Statut** : design validé, prêt pour plan d'implémentation

## Contexte

L'essai terrain du standalone `scripts/diagnostics/cimier_manual.py` (Serge,
17-18/06) a réussi **du premier coup, aux valeurs par défaut**, sans avoir à
modifier le réglage on/off moteur ni le réglage du sens de déplacement. Le
standalone encode la vérité du synoptique V3 ; cet essai grandeur nature la
**valide** définitivement.

Il faut maintenant :
1. **Intégrer la convention validée** dans le code applicatif (`MotorShelly` +
   `data/config.json`).
2. **Nettoyer les scories** accumulées lors des tentatives précédentes (fantômes
   Pico W, prose contradictoire, « à valider au banc », narration de débogage).

## Ce que l'essai valide (traduction standalone → applicatif)

Le standalone a tourné aux **défauts** de son dict `CONV` :

| Convention | Standalone (validé) | Applicatif équivalent | État actuel |
|---|---|---|---|
| Moteur tourne | `mot_run="off"` → relais MOT `turn=off` fait **tourner** | `motor_on_relay_state` | `true` ❌ → doit être `false` |
| Sens montée/ouverture | `dir_up="on"` → relais UPDN `turn=on` | `open_dir_state` | `true` ✅ |
| Butée atteinte | `switch_closed="false"` → `state=false` = atteinte | `switch_reader.invert` | `true` ✅ |

**Une seule valeur de comportement est fausse : `motor_on_relay_state`.** C'est la
cause racine la plus probable du « mouvement erratique / sens aléatoire » des
sessions du 14/06 : `turn_on()` envoyait `turn=on`, qui **arrête** le moteur dans
le câblage réel (logique inversée), au lieu de `turn=off` qui le fait tourner.

## Mapping de référence (à ne pas se tromper à l'implémentation)

`MotorShelly` en API `legacy` (Shelly Gen 1) :
- `turn_on()` → `_set_relay(host_motor, relay_motor, on=motor_on_relay_state)` →
  URL `…/relay/0?turn=("on" if on else "off")`.
- Donc pour que `turn_on()` **fasse tourner** le moteur (≡ standalone `motor run`,
  qui envoie `turn=off`), il faut `motor_on_relay_state = False`.
- `turn_off()` envoie alors `turn=on` (≡ standalone `motor stop`). ✅

`set_direction(open_direction=True)` avec `open_dir_state=True` → `turn=on` (≡
standalone `dir up`). ✅ Aucun changement.

`ShellySwitchReader.read()` avec `invert=True` → `open_switch = not haut_state`,
donc butée HAUT atteinte quand `state=False` (≡ standalone `switch_closed=false`).
✅ Aucun changement.

## Décisions de cadrage

- **1A — convention validée = nouveau défaut partout.** Flip du défaut de
  `MotorShelly` (code) ET de `data/config.json`. L'observatoire a une vérité
  hardware unique ; un déploiement terrain neuf doit être correct d'emblée.
- **2B — réévaluation active des rustines 6.7.x** (cf. §4). Critère : *pansement
  sur le symptôme de la convention inversée, ou besoin légitime du service ?*

## Périmètre

### 1. Correction de la convention moteur (1A)

- `core/hardware/motor_shelly.py` : signature `motor_on_relay_state: bool = False`
  (défaut). Re-documenter le docstring : la valeur `False` n'est plus « cas terrain
  Serge à valider » mais **la convention validée** (moteur tourne contact ouvert,
  relais `turn=off`).
- `data/config.json` → `cimier.motor_shelly.motor_on_relay_state: false` +
  commentaire corrigé (le commentaire actuel affirme l'inverse : « moteur tourne
  quand relais turn=on »).
- `_apply_dev_mode_overrides` (`services/cimier_service.py`) met déjà
  `motor_on_relay_state = True` **explicitement** pour le simulateur (conventions
  naturelles, relais ON = actif) → flipper le défaut ne casse pas le dev.
- `open_dir_state` et `switch_reader.invert` : **inchangés** (déjà conformes).

### 2. Nettoyage documentaire des scories (0 logique modifiée)

- **Fantômes Pico W** retirés des docstrings/commentaires de :
  `core/hardware/motor_shelly.py` (« fins de course câblées sur le Pico W », «
  Shelly 1 Gen 3 » → Gen 1 legacy), `services/cimier_service.py` (« Shelly **220V**
  cascade » → 24V ; « pas de pico_state legacy » → formulation V3 neutre ;
  commentaire dev-mode), `core/hardware/power_switch.py`,
  `core/hardware/shelly_switch_reader.py`, `core/hardware/weather_provider.py`,
  `core/config/config_loader.py`, `web/cimier/views.py`.
- **Prose des butées unifiée** sur la formulation du standalone : « `state=false`
  = butée atteinte ». Fin de la contradiction entre `shelly_switch_reader.py` /
  `config.json` (« state=true=contact fermé=repos ») et le standalone (« contact
  fermé = atteinte »). La **logique** est identique ; seule la prose est corrigée.
- **`data/config.json`** : suppression de toutes les mentions « à VALIDER AU BANC »
  (c'est validé terrain).
- **Non touché** : les 3 simulateurs (`cimier_simulator.py`,
  `cimier_mechanism_sim.py`, `sim_motor_shelly.py`) = infra de test/dev active.

### 3. Allègement du traçage de débogage

- `services/cimier_service.py` : retirer/condenser l'instrumentation de chasse au
  « stop fantôme » (`stop_command_received id=… ts=…`, distinction verbeuse
  `source=signal|stop_command`). Garder un log de stop concis et utile en
  opération ; retirer le commentaire de narration de débogage.

### 4. Réévaluation des rustines 6.7.x (2B) — verdicts

| Rustine | Verdict | Justification |
|---|---|---|
| **mode Drop** (6.7.3) | **GARDER** | Pas un pansement : corrige un vrai bug de buffer-replay confirmé par Serge. Comportement correct du pilotage manuel (une commande à la fois). Le retirer réintroduirait le bug. |
| **`timer_safety_sec` / `timer=`** | **GARDER, documenter** | Sécurité réelle du service autonome (moteur coupé si Pi/WiFi tombe en plein cycle). Absente du standalone car outil manuel supervisé. **Vérifier** : avec `run=off`, `turn=off&timer=90` bascule sur `on` à 90 s = moteur **stoppé** ✓. |
| **`dir_settle_s` (0,3 s)** | **GARDER, re-documenter** | Équivalent explicite du délai que le standalone obtient implicitement (la lecture pré-check HTTP entre `set_direction` et `motor run`). Le service ne fait pas cette lecture intermédiaire → il lui faut le settle pour la bascule mécanique du DPDT. Le « sens erroné persiste malgré dir_settle » du 14/06 venait de la convention moteur fausse, pas du timing. Retirer seulement la narration « mystère 8 ms ». |
| **Traçage stop fantôme** | **ALLÉGER** | cf. §3. |

**Conclusion 2B** : la cause racine unique était la convention moteur (§1). Les
rustines se révèlent en grande majorité légitimes ; le nettoyage de code réel se
limite à alléger le traçage stop (§3) et re-documenter `dir_settle`/`timer_safety`
sans narration de débogage. Le gros du nettoyage est documentaire (§2).

## Hors périmètre

- Pas de refonte du flow `_run_cycle` (l'ordre des phases est conforme au
  standalone ; le preflight avant `power_on` est valide car le Shelly Uni+ est
  alimenté indépendamment — le standalone lit les butées avant tout `power on`).
- Pas de consolidation des simulateurs.
- Pas de configuration des IPs/hosts terrain dans le template (reste `noop` /
  vides ; règle « pas de valeurs terrain en dur dans le dépôt »).
- Pas de capteur pluie (backlog séparé).

## Tests & critères de succès

1. Mettre à jour les tests qui supposaient l'ancien défaut
   `motor_on_relay_state=True` : `tests/test_motor_shelly.py`,
   `tests/test_cimier_service.py`, `tests/test_config_loader.py`.
2. Ajouter un test verrouillant la convention validée :
   - `MotorShelly(api="legacy")` par défaut → `turn_on()` émet `…/relay/0?turn=off` ;
     `turn_off()` émet `…/relay/0?turn=on`.
   - `data/config.json` chargé → `motor_on_relay_state is False`.
3. **Vert** : `uv run --extra dev pytest` ciblé sur le périmètre cimier
   (`test_motor_shelly`, `test_cimier_service`, `test_config_loader`,
   `test_shelly_switch_reader`, `test_power_switch`).
4. **Grep de propreté** : 0 occurrence de `Pico W` / `220V` / `Gen 3` / `à valider`
   dans les sources cimier de `core/`, `services/`, `web/cimier/`.
5. `ruff format` + `ruff check` propres.
6. **Pas de bump de `pyproject.toml`** (chantier cimier en cours).

## Risques

- **Faible** : flipper le défaut `motor_on_relay_state` casse des tests existants
  qui l'assument implicitement → repérables et corrigeables (critère 1).
- **Très faible** : nettoyage documentaire sans impact runtime.
- **À re-valider terrain** (déjà fait via standalone, mais le *service* applicatif
  n'a pas encore tourné avec la convention corrigée) : un cycle open/close réel via
  l'UI après merge, pour confirmer que le service reproduit le succès du standalone.
