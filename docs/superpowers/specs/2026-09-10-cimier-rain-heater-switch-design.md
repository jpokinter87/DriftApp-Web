# Résistance chauffante du capteur de pluie — pilotage Shelly

**Date** : 2026-09-10
**Statut** : design validé, prêt pour plan d'implémentation
**Périmètre** : allumer/éteindre par relais Shelly la résistance chauffante anti-rosée du capteur
de pluie, asservie à l'armement de la protection pluie. Aucun changement à la logique de détection
pluie ou de fermeture d'urgence existante ([[project_cimier_weather_rain_backlog]]).

---

## 1. Contexte

Serge a installé une résistance chauffante sous le capteur de pluie (MH-RD) pour éviter que la
rosée matinale ne fausse la lecture — un problème distinct des défauts de bavardage/lecture D0
déjà traités en v6.15.0/6.15.1. La résistance est câblée sur un Shelly Gen 1 dédié, pilotable en
legacy : `http://192.168.1.78/relay/0?turn=on|off`.

Rien à construire côté hardware : `core/hardware/power_switch.py::ShellyPowerSwitch` parle déjà
exactement ce protocole (`api="legacy"`) — c'est la classe qui pilote le Shelly d'alimentation
24V du cimier (`.83`) depuis la v6.7. Le sujet est entièrement de la configuration et de
l'orchestration.

---

## 2. Décision produit

**Déclencheur : l'armement de la protection pluie, pas la pluie détectée.** La case « Protection
pluie » du dashboard (`weather_provider.protection_enabled`) commande la résistance ON quand
cochée, OFF quand décochée — indépendamment de l'état `wet`/`dry`/`unreachable` du capteur et du
`latched` de `RainProtection`. Choix délibéré (confirmé) : la résistance sert à fiabiliser la
lecture *pendant qu'on surveille*, pas seulement pendant une averse — la rosée qui fausserait une
lecture peut précéder la pluie de plusieurs heures.

**Panne réseau du Shelly chauffage** (confirmé) : ne bloque jamais l'armement/désarmement de la
protection pluie elle-même (fail-safe, cohérent avec le reste du cimier). L'échec est journalisé
**et** remonté en temps réel dans le statut publié, pour que l'opérateur le voie sur le dashboard
sans avoir à consulter les logs — pas de New Relic de la panne trois jours plus tard.

**Pas de retry en boucle.** Une seule tentative de commande par transition d'armement. Une panne
transitoire au moment précis du clic reste possible ; elle est visible (badge ⚠) et se résout au
prochain changement d'armement, ou par une intervention manuelle sur le Shelly. Un retry cadencé
ajouterait un état à suivre (cible vs réel) pour un bénéfice marginal sur un équipement de confort
(anti-rosée), pas de sécurité — asymétrie inverse de la fermeture pluie elle-même.

---

## 3. Conception

### 3.1 Configuration : `cimier.rain_heater_switch`

Nouvelle section sœur de `power_switch`, même schéma — `PowerSwitchConfig` est réutilisée telle
quelle (`type` ∈ `{noop, shelly_gen1, shelly_gen2}`, `host`, `switch_id`) :

```json
"rain_heater_switch": {
  "_comment": "Résistance chauffante anti-rosée du capteur de pluie, Shelly Gen 1 legacy dédié. type=noop dans le template repo.",
  "type": "noop",
  "host": "",
  "switch_id": 0
}
```

- `CimierConfig.rain_heater_switch: PowerSwitchConfig = field(default_factory=PowerSwitchConfig)`
  (`core/config/config_loader.py`, à côté de `power_switch`).
- `ConfigLoader._parse_cimier()` : même bloc de parsing que `power_switch` (lignes ~632-664),
  dupliqué pour la nouvelle clé — il n'existe pas de factorisation générique de sous-section, et en
  créer une pour deux appelants serait une abstraction prématurée (§ simplicité, CLAUDE.md).
- Ajoutée à `data/config.template.json` avec `type: "noop"` : apparaît automatiquement dans la
  page `/configuration/` (formulaire auto-généré depuis le template, v6.10) — aucun code UI de
  configuration à écrire.
- Valeur terrain réelle (`type: "shelly_gen1", host: "192.168.1.78"`) à saisir par Serge via cette
  page ou directement dans `data/config.json` (dé-tracké, chantier config-resilience) — jamais en
  dur dans le code.
- Défaut `noop` → un `config.json` non migré se comporte exactement comme aujourd'hui (pas de
  Shelly configuré, `NoopPowerSwitch`, aucun effet).

### 3.2 Construction : réutilisation directe de `make_power_switch`

`services/cimier_service.py::make_power_switch(cfg: PowerSwitchConfig)` est déjà générique — elle
ne sait rien du cimier, seulement construire un `ShellyPowerSwitch`/`NoopPowerSwitch` depuis une
config. Appelée une seconde fois dans `main()`, à côté de la construction du `power_switch`
existant :

```python
rain_heater_switch = make_power_switch(cfg.cimier.rain_heater_switch)
...
CimierService(..., rain_heater_switch=rain_heater_switch, ...)
```

Stocké en `self._rain_heater_switch` dans `__init__`, au même titre que `self._power_switch`.

### 3.3 Pilotage : extension de `_rain_watch_tick()`

La veille pluie (`services/cimier_service.py`, `_rain_watch_tick()`, appelée à la cadence
`weather_provider.watch_interval_s`) connaît déjà l'armement via `_refresh_rain_armed_from_config()`.
On y ajoute, juste après ce rafraîchissement, l'application de l'état à la résistance :

```python
def _refresh_rain_armed_from_config(self) -> None:
    ...
    if armed != provider.armed:
        logger.info("cimier_event=rain_protection_changed ...")
        provider.armed = armed
        self._apply_rain_heater_state(armed)
```

```python
def _apply_rain_heater_state(self, armed: bool) -> None:
    """Commande la résistance chauffante sur transition d'armement.

    Une seule tentative : un échec ne doit jamais bloquer l'armement de la
    protection pluie elle-même (fail-safe), et se voit dans le statut publié
    plutôt que de nécessiter une lecture de log. Rien n'est publié si aucun
    Shelly n'est configuré (`type=noop`) — appeler turn_on/turn_off sur le
    NoopPowerSwitch reste inoffensif, mais un badge « OFF » sans matériel
    réel derrière induirait en erreur.
    """
    if not self._rain_heater_configured:
        return
    try:
        if armed:
            self._rain_heater_switch.turn_on()
        else:
            self._rain_heater_switch.turn_off()
    except PowerSwitchError as exc:
        logger.error("cimier_event=rain_heater_command_failed armed=%s exc=%s", armed, exc)
        self._rain_heater_status = {"configured": True, "on": None, "last_command_ok": False, "error": str(exc)}
    else:
        self._rain_heater_status = {"configured": True, "on": armed, "last_command_ok": True, "error": None}
```

`self._rain_heater_configured = not isinstance(self._rain_heater_switch, NoopPowerSwitch)`,
calculé une fois à la construction du service (même test que celui déjà utilisé implicitement par
`make_power_switch` pour choisir la classe).

**État initial au démarrage** : `provider.armed` vaut déjà la valeur de config au moment de la
construction (voir `make_weather_provider`), donc la toute première comparaison
`armed != provider.armed` dans `_refresh_rain_armed_from_config()` serait toujours fausse et ne
déclencherait jamais l'application initiale. On initialise donc `self._rain_heater_status` et on
appelle `_apply_rain_heater_state(provider.armed)` une fois explicitement à la construction du
service (`CimierService.__init__`, juste après l'instanciation de `self._rain_heater_switch`),
pour que l'état de la résistance corresponde à l'armement dès le premier tick, y compris après un
redémarrage (OTA notamment, cf. v6.14.0 — un restart ne doit pas laisser la résistance dans un
état qui ne correspond plus à la case cochée).

**`PowerSwitchError` importée** depuis `core/hardware/power_switch.py`, déjà le type levé par
`ShellyPowerSwitch`.

### 3.4 Statut publié : `cimier_status.json` → `rain.heater`

`_publish_status()` (ligne 974) construit déjà `payload["rain"] = self._weather_provider.describe()`
quand `self._rain_enabled`. La résistance n'est pas couplée à la présence d'un capteur pluie réel
côté code (elle a sa propre config `type`), donc son statut est ajouté indépendamment :

```python
if self._rain_enabled:
    payload["rain"] = self._weather_provider.describe()
if self._rain_heater_status.get("configured"):
    payload.setdefault("rain", {})["heater"] = self._rain_heater_status
```

`RainProtection`/`weather_provider.py` ne sont pas touchés — la composition se fait au niveau de
l'orchestration (`cimier_service`), pas dans le module météo, qui n'a pas à savoir qu'une
résistance existe.

### 3.5 UI — badge chauffage

Dashboard, à côté de la pastille `SEC`/`PLUIE`/`CAPTEUR ?` existante (v6.12) : un badge textuel
lisant `cimier_status.rain.heater` (déjà forwardé par `/api/cimier/status/`, aucune route
nouvelle) :

- absent si `rain.heater` absent (résistance non configurée — dev, ou terrain avant saisie) ;
- **Chauffage : ON** (vert) si `on === true` ;
- **Chauffage : OFF** (gris) si `on === false` ;
- **⚠ Chauffage injoignable** (ambre) si `last_command_ok === false`.

Frontend pur (`dashboard.html`/`dashboard.css`/`dashboard.js`), aucune dépendance au survol
(écran tactile, contrainte verrouillée [[feedback_touchscreen_no_hover]]).

### 3.6 Simulation dev

`core/hardware/cimier_simulator.py` émule déjà 4 Shelly legacy/RPC. La résistance chauffante étant
un 5ᵉ relais du même type que l'alimentation 24V, elle est ajoutée au simulateur unifié sur un
port/host dev dédié (même mécanique que les 4 existants), pour que le cycle armement→ON,
désarmement→OFF soit vérifiable de bout en bout sur la stack dev sans matériel. Pas de nouveau
concept de simulation à inventer.

---

## 4. Hors périmètre

- **Asservissement à une sonde d'humidité/température** (thermostat) : la résistance est pilotée
  en tout-ou-rien par l'armement, pas par une mesure. Non demandé.
- **Minuterie de sécurité** (coupure après N heures) : le Shelly légal reste sous tension tant que
  la protection est armée ; pas de risque de surchauffe signalé par Serge, non traité ici.
- **Retry automatique en cas d'échec de commande** — §2, décision explicite.
- **Historique/journal de nuit dédié au chauffage** : le `night_journal` existant reste centré sur
  pluie/décision/cimier ; un ON/OFF de confort n'y ajoute pas de valeur diagnostique. Le statut
  temps réel (§3.4) suffit au besoin exprimé.

---

## 5. Tests

TDD, périmètre cimier.

**`tests/test_config_loader.py`** — parsing de `cimier.rain_heater_switch` : defaults (`noop`,
config absente → comportement inchangé), valeurs explicites, types invalides ignorés comme pour
`power_switch`.

**`tests/test_cimier_service.py`** (pattern `TestRainWatch` / `make_rain_service`) :
- armement → `turn_on()` appelé une fois, statut `on=True, last_command_ok=True` ;
- désarmement → `turn_off()` appelé une fois ;
- aucun changement d'armement entre deux tours → pas de nouvel appel (idempotence) ;
- état initial appliqué à la construction du service, cohérent avec `protection_enabled` de la
  config au démarrage (cas redémarrage OTA avec protection déjà armée) ;
- `PowerSwitchError` à la commande → statut `last_command_ok=False`, armement de la protection
  non affecté, log `rain_heater_command_failed` ;
- `type=noop` → `rain.heater` absent du statut publié.

**`tests/test_power_switch.py`** : aucun test nouveau nécessaire, `ShellyPowerSwitch` est déjà
couvert (URL legacy exacte, erreurs réseau) — seule sa réutilisation est testée côté cimier.

**Web** — `GET /api/cimier/status/` : `rain.heater` bien forwardé quand présent.

**Régression** — suite complète verte.

---

## 6. Critères de succès

- Case « Protection pluie » cochée → résistance ON en ≤ `watch_interval_s` (5-10 s) ; décochée →
  OFF dans le même délai.
- Redémarrage du service (OTA) avec protection déjà armée → résistance réappliquée ON au premier
  tick, pas d'attente d'un changement d'armement qui ne viendra pas.
- Shelly chauffage injoignable → protection pluie s'arme/se désarme normalement, badge ⚠ visible
  sur le dashboard sans consultation de logs.
- `type=noop` (config non migrée ou dev sans matériel) → aucun effet, badge absent, suite de tests
  inchangée par ailleurs.
- Suite pytest verte, aucune IP terrain dans le code Python.

---

## Références

- Réutilisé tel quel : `core/hardware/power_switch.py` (`ShellyPowerSwitch`, `PowerSwitchConfig`,
  `PowerSwitchError`), `services/cimier_service.py::make_power_switch`.
- Point d'ancrage : `services/cimier_service.py::_rain_watch_tick` /
  `_refresh_rain_armed_from_config` / `_publish_status`.
- Design pluie de référence : `2026-08-14-capteur-pluie-integration-design.md`.
- Backlog : mémoire [[project_cimier_weather_rain_backlog]].
