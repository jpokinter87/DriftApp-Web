# Résistance chauffante capteur de pluie — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Piloter par Shelly legacy (192.168.1.78, `/relay/0?turn=on|off`) la résistance chauffante anti-rosée du capteur de pluie, asservie à l'armement de la case « Protection pluie », avec statut temps réel remonté au dashboard en cas de panne réseau.

**Architecture:** Réutilisation intégrale de `core/hardware/power_switch.py::ShellyPowerSwitch` (déjà utilisé pour le Shelly d'alimentation 24V du cimier) via une nouvelle config `cimier.rain_heater_switch` au même schéma que `power_switch`. `services/cimier_service.py` commande ON/OFF sur transition d'armement (détectée par le hot-reload de config déjà existant), publie le résultat dans `cimier_status.json` sous `rain.heater`, sans jamais bloquer l'armement lui-même en cas d'échec réseau.

**Tech Stack:** Python 3, dataclasses, Django REST Framework (passthrough existant, aucune modification), Alpine.js/vanilla JS (dashboard), pytest.

**Spec de référence :** `docs/superpowers/specs/2026-09-10-cimier-rain-heater-switch-design.md`

---

## Task 1 : Configuration — `PowerSwitchConfig` réutilisée pour `rain_heater_switch`

**Files:**
- Modify: `core/config/config_loader.py:343` (ajout du champ `CimierConfig.rain_heater_switch`)
- Modify: `core/config/config_loader.py:624-712` (`_parse_cimier`)
- Test: `tests/test_config_loader.py` (nouvelle classe `TestCimierRainHeaterSwitchConfig`, à ajouter juste après `class TestCimierConfig` — chercher `test_cimier_power_switch_shelly_gen2` pour repérer l'endroit)

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter dans `tests/test_config_loader.py`, juste après le dernier test de `TestCimierConfig` portant sur `power_switch` (`test_cimier_power_switch_shelly_gen2`, dans la même classe `TestCimierConfig` — ce ne sont pas des tests séparés, ils suivent le même style que les tests `power_switch` déjà présents) :

```python
    def test_cimier_rain_heater_switch_default_when_missing(self, tmp_path, sample_config_dict):
        """Section cimier sans rain_heater_switch imbriqué → PowerSwitchConfig() par défaut."""
        cfg = dict(sample_config_dict)
        cfg["cimier"] = {"enabled": True}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(cfg))
        config = ConfigLoader(config_file).load()
        assert isinstance(config.cimier.rain_heater_switch, PowerSwitchConfig)
        assert config.cimier.rain_heater_switch.type == "noop"
        assert config.cimier.rain_heater_switch.host == ""
        assert config.cimier.rain_heater_switch.switch_id == 0

    def test_cimier_rain_heater_switch_shelly_gen1(self, tmp_path, sample_config_dict):
        """type=shelly_gen1 + host renseigné → reflété dans la dataclass."""
        cfg = dict(sample_config_dict)
        cfg["cimier"] = {
            "enabled": False,
            "rain_heater_switch": {
                "type": "shelly_gen1",
                "host": "192.168.1.78",
                "switch_id": 0,
            },
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(cfg))
        config = ConfigLoader(config_file).load()
        assert config.cimier.rain_heater_switch.type == "shelly_gen1"
        assert config.cimier.rain_heater_switch.host == "192.168.1.78"
        assert config.cimier.rain_heater_switch.switch_id == 0

    def test_cimier_rain_heater_switch_independent_of_power_switch(
        self, tmp_path, sample_config_dict
    ):
        """Les deux sections coexistent sans se piétiner (schéma identique, clés distinctes)."""
        cfg = dict(sample_config_dict)
        cfg["cimier"] = {
            "power_switch": {"type": "shelly_gen1", "host": "192.168.1.83", "switch_id": 0},
            "rain_heater_switch": {"type": "shelly_gen1", "host": "192.168.1.78", "switch_id": 0},
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(cfg))
        config = ConfigLoader(config_file).load()
        assert config.cimier.power_switch.host == "192.168.1.83"
        assert config.cimier.rain_heater_switch.host == "192.168.1.78"
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `uv run --extra dev pytest tests/test_config_loader.py -k RainHeaterSwitch -v`
Expected: FAIL — `AttributeError: 'CimierConfig' object has no attribute 'rain_heater_switch'`

- [ ] **Step 3: Ajouter le champ à `CimierConfig`**

Dans `core/config/config_loader.py`, section `CimierConfig` (repérer la ligne `power_switch: PowerSwitchConfig = field(default_factory=PowerSwitchConfig)`) :

```python
    switch_reader: SwitchReaderConfig = field(default_factory=SwitchReaderConfig)
    power_switch: PowerSwitchConfig = field(default_factory=PowerSwitchConfig)
    rain_heater_switch: PowerSwitchConfig = field(default_factory=PowerSwitchConfig)
    weather_provider: WeatherProviderConfig = field(default_factory=WeatherProviderConfig)
```

(insérer la ligne `rain_heater_switch: ...` entre `power_switch` et `weather_provider` — même dataclass `PowerSwitchConfig` que `power_switch`, section distincte pour la résistance chauffante anti-rosée du capteur de pluie, cf. spec 2026-09-10.)

- [ ] **Step 4: Parser la section dans `_parse_cimier`**

Dans `core/config/config_loader.py`, méthode `_parse_cimier` :

Remplacer :
```python
        ps = c.get("power_switch", {}) if isinstance(c, dict) else {}
        wp = c.get("weather_provider", {}) if isinstance(c, dict) else {}
```
par :
```python
        ps = c.get("power_switch", {}) if isinstance(c, dict) else {}
        rh = c.get("rain_heater_switch", {}) if isinstance(c, dict) else {}
        wp = c.get("weather_provider", {}) if isinstance(c, dict) else {}
```

Puis remplacer :
```python
            power_switch=PowerSwitchConfig(
                type=str(ps.get("type", ps_defaults.type)),
                host=str(ps.get("host", ps_defaults.host)),
                switch_id=int(ps.get("switch_id", ps_defaults.switch_id)),
            ),
            weather_provider=WeatherProviderConfig(
```
par :
```python
            power_switch=PowerSwitchConfig(
                type=str(ps.get("type", ps_defaults.type)),
                host=str(ps.get("host", ps_defaults.host)),
                switch_id=int(ps.get("switch_id", ps_defaults.switch_id)),
            ),
            rain_heater_switch=PowerSwitchConfig(
                type=str(rh.get("type", ps_defaults.type)),
                host=str(rh.get("host", ps_defaults.host)),
                switch_id=int(rh.get("switch_id", ps_defaults.switch_id)),
            ),
            weather_provider=WeatherProviderConfig(
```

(`ps_defaults` est réutilisé tel quel — même dataclass `PowerSwitchConfig()`, mêmes defaults pour les deux sections, pas besoin d'un second jeu de defaults.)

- [ ] **Step 5: Lancer les tests, vérifier qu'ils passent**

Run: `uv run --extra dev pytest tests/test_config_loader.py -k "RainHeaterSwitch or CimierConfig" -v`
Expected: PASS (tous les tests `TestCimierConfig`, anciens et nouveaux)

- [ ] **Step 6: Commit**

```bash
git add core/config/config_loader.py tests/test_config_loader.py
git commit -m "$(cat <<'EOF'
feat(cimier): config rain_heater_switch pour la résistance chauffante pluie

Réutilise PowerSwitchConfig (même schéma que power_switch) pour la
future commande Shelly de la résistance anti-rosée du capteur de
pluie. Défaut noop, rétro-compatible.
EOF
)"
```

---

## Task 2 : Template config + page `/configuration/`

**Files:**
- Modify: `data/config.template.json:108-113` (nouvelle section)
- Modify: `core/config/config_resilience.py` (`HELP_REGISTRY`, `ENUM_REGISTRY`)
- Test: `tests/test_config_resilience.py::test_chaque_champ_du_template_reel_a_une_aide` (existant, sert de garde-fou — pas de nouveau test)

- [ ] **Step 1: Vérifier que le garde-fou existant échouerait sans l'aide**

Run: `uv run --extra dev pytest tests/test_config_resilience.py::TestBuildConfigSchema::test_chaque_champ_du_template_reel_a_une_aide -v`
Expected: PASS pour l'instant (le champ n'existe pas encore dans le template — ce test ne peut échouer qu'une fois la Step 2 faite sans la Step 3).

- [ ] **Step 2: Ajouter la section au template**

Dans `data/config.template.json`, entre `power_switch` et `weather_provider` (repérer `"power_switch": { ... }` ligne 108-113) :

```json
    "power_switch": {
      "_comment": "SHELLY-1-24V (.83) — alim module cimier, coupé hors cycle. type ∈ {shelly_gen1, shelly_gen2, noop}. Gen 1 → legacy /relay/0.",
      "type": "noop",
      "host": "192.168.1.83",
      "switch_id": 0
    },
    "rain_heater_switch": {
      "_comment": "Résistance chauffante anti-rosée du capteur de pluie, Shelly Gen 1 dédié. type ∈ {shelly_gen1, shelly_gen2, noop}. ON quand la protection pluie est armée, OFF sinon — indépendant de l'état wet/dry du capteur.",
      "type": "noop",
      "host": "192.168.1.78",
      "switch_id": 0
    },
    "weather_provider": {
```

- [ ] **Step 3: Lancer le garde-fou, vérifier qu'il échoue**

Run: `uv run --extra dev pytest tests/test_config_resilience.py::TestBuildConfigSchema::test_chaque_champ_du_template_reel_a_une_aide -v`
Expected: FAIL — `Champs sans info-bulle : ['cimier.rain_heater_switch.type', 'cimier.rain_heater_switch.host', 'cimier.rain_heater_switch.switch_id']`

- [ ] **Step 4: Ajouter les entrées `HELP_REGISTRY` et `ENUM_REGISTRY`**

Dans `core/config/config_resilience.py`, `ENUM_REGISTRY` (repérer la ligne `"cimier.power_switch.switch_id": [0, 1],`) :

```python
    "cimier.power_switch.type": ["shelly_gen1", "shelly_gen2", "noop"],
    "cimier.rain_heater_switch.type": ["shelly_gen1", "shelly_gen2", "noop"],
    "cimier.weather_provider.type": ["noop", "shelly_rain"],
```
et
```python
    "cimier.power_switch.switch_id": [0, 1],
    "cimier.rain_heater_switch.switch_id": [0, 1],
    "cimier.switch_reader.open_input_id": [0, 1],
```

Puis dans `HELP_REGISTRY`, juste après le bloc `# cimier.power_switch` (repérer `"cimier.power_switch.switch_id": (...)`) :

```python
    # cimier.power_switch (alim 24V du module cimier)
    "cimier.power_switch.type": (
        "Type du Shelly d'alimentation 24V du module cimier. « shelly_gen1 » "
        "(legacy /relay), « shelly_gen2 » (RPC) ou « noop » (factice)."
    ),
    "cimier.power_switch.host": (
        "Hôte/IP du Shelly alimentant le module cimier (coupé hors cycle)."
    ),
    "cimier.power_switch.switch_id": (
        "Index du relais d'alimentation 24V sur le Shelly power : 0 ou 1."
    ),
    # cimier.rain_heater_switch (résistance chauffante anti-rosée du capteur de pluie)
    "cimier.rain_heater_switch.type": (
        "Type du Shelly pilotant la résistance chauffante du capteur de pluie. "
        "« shelly_gen1 » (legacy /relay), « shelly_gen2 » (RPC) ou « noop » (factice)."
    ),
    "cimier.rain_heater_switch.host": (
        "Hôte/IP du Shelly de la résistance chauffante. ON quand la protection "
        "pluie est armée, OFF sinon."
    ),
    "cimier.rain_heater_switch.switch_id": (
        "Index du relais de la résistance chauffante sur son Shelly : 0 ou 1."
    ),
```

- [ ] **Step 5: Lancer le garde-fou, vérifier qu'il passe**

Run: `uv run --extra dev pytest tests/test_config_resilience.py -v`
Expected: PASS (tous les tests, y compris `test_chaque_champ_du_template_reel_a_une_aide`)

- [ ] **Step 6: Vérifier que la page Configuration rend toujours 200**

Run: `uv run --extra dev pytest tests/test_configuration_views.py -v`
Expected: PASS (schéma auto-généré depuis le template, aucune modification de code nécessaire côté vue)

- [ ] **Step 7: Commit**

```bash
git add data/config.template.json core/config/config_resilience.py
git commit -m "$(cat <<'EOF'
feat(cimier): template + aide UI pour rain_heater_switch

Ajoute la section au template repo (type=noop par défaut) et les
entrées HELP_REGISTRY/ENUM_REGISTRY correspondantes — le champ
apparaît automatiquement dans /configuration/ sans code UI dédié.
EOF
)"
```

---

## Task 3 : `cimier_service` — construction du switch + branchement usine

**Files:**
- Modify: `services/cimier_service.py` (constructeur `CimierService.__init__`, `_build_service_from_config`, `_apply_dev_mode_overrides`)
- Test: `tests/test_cimier_service.py` (extension de `make_rain_service`, nouveaux tests dans une classe `TestRainHeaterSwitch`)

- [ ] **Step 1: Écrire le test qui échoue (switch par défaut construit depuis la config)**

Ajouter dans `tests/test_cimier_service.py`, juste après la classe `TestRainWatch` (avant `# Intégration : veille câblée sur le vrai provider`) :

```python
# ======================================================================
# Résistance chauffante capteur de pluie (2026-09)
# ======================================================================


class TestRainHeaterSwitch:
    @pytest.fixture(autouse=True)
    def _isolate_night_journal(self, tmp_path, monkeypatch):
        from services import night_journal

        monkeypatch.setattr(night_journal, "DEFAULT_NIGHTS_DIR", tmp_path / "nights")

    def test_default_heater_switch_is_built_from_config(self, tmp_path):
        """Sans injection explicite, le switch est construit via make_power_switch."""
        from core.config.config_loader import PowerSwitchConfig, WeatherProviderConfig

        cfg = CimierConfig(
            enabled=True,
            weather_provider=WeatherProviderConfig(type="shelly_rain", host="1.2.3.4"),
            rain_heater_switch=PowerSwitchConfig(type="noop"),
        )
        ipc = CimierIpcManager(
            command_file=tmp_path / "cmd.json", status_file=tmp_path / "status.json"
        )
        service = CimierService(
            cimier_config=cfg,
            power_switch=NoopPowerSwitch(),
            motor_shelly=NoopMotorShelly(),
            switch_reader=FakeSwitchReader([(True, False)]),
            ipc_manager=ipc,
            weather_provider=StubRainProtection(state="dry", armed=False),
            config_path=tmp_path / "absent.json",
        )
        assert isinstance(service._rain_heater_switch, NoopPowerSwitch)
        assert service._rain_heater_configured is False
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `uv run --extra dev pytest tests/test_cimier_service.py -k test_default_heater_switch_is_built_from_config -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument` ou `AttributeError: 'CimierService' object has no attribute '_rain_heater_switch'`

- [ ] **Step 3: Ajouter le paramètre et la construction par défaut**

Dans `services/cimier_service.py`, signature de `CimierService.__init__` (repérer `switch_reader: Optional[SwitchReaderProtocol] = None,`) :

```python
    def __init__(
        self,
        cimier_config: CimierConfig,
        power_switch: PowerSwitchProtocol,
        motor_shelly: Optional[MotorShellyProtocol] = None,
        switch_reader: Optional[SwitchReaderProtocol] = None,
        rain_heater_switch: Optional[PowerSwitchProtocol] = None,
        ipc_manager: Optional[CimierIpcManager] = None,
```

Puis, juste après `self._power_switch = power_switch` :

```python
        self._power_switch = power_switch
        self._rain_heater_switch = (
            rain_heater_switch
            if rain_heater_switch is not None
            else make_power_switch(cimier_config.rain_heater_switch)
        )
        self._rain_heater_configured = not isinstance(self._rain_heater_switch, NoopPowerSwitch)
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

Run: `uv run --extra dev pytest tests/test_cimier_service.py -k test_default_heater_switch_is_built_from_config -v`
Expected: PASS

- [ ] **Step 5: Brancher `_build_service_from_config` (entry-point réel)**

Dans `services/cimier_service.py`, fonction `_build_service_from_config` :

Remplacer :
```python
    power_switch = make_power_switch(cfg.cimier.power_switch)
    switch_reader = make_switch_reader(cfg.cimier.switch_reader)
    weather_provider = make_weather_provider(cfg.cimier.weather_provider)
    return CimierService(
        cimier_config=cfg.cimier,
        power_switch=power_switch,
        switch_reader=switch_reader,
        weather_provider=weather_provider,
        site_config=cfg.site,
        config_path=config_path,
        cycle_poll_interval_s=cfg.cimier.cycle_poll_interval_s,
    )
```
par :
```python
    power_switch = make_power_switch(cfg.cimier.power_switch)
    switch_reader = make_switch_reader(cfg.cimier.switch_reader)
    weather_provider = make_weather_provider(cfg.cimier.weather_provider)
    rain_heater_switch = make_power_switch(cfg.cimier.rain_heater_switch)
    return CimierService(
        cimier_config=cfg.cimier,
        power_switch=power_switch,
        switch_reader=switch_reader,
        weather_provider=weather_provider,
        rain_heater_switch=rain_heater_switch,
        site_config=cfg.site,
        config_path=config_path,
        cycle_poll_interval_s=cfg.cimier.cycle_poll_interval_s,
    )
```

- [ ] **Step 6: Brancher le simulateur dev-mode**

Dans `services/cimier_service.py`, fonction `_apply_dev_mode_overrides`, juste après `cimier_cfg.power_switch.switch_id = 0` :

```python
    cimier_cfg.power_switch.type = "shelly_gen1"
    cimier_cfg.power_switch.host = "127.0.0.1:8001"
    cimier_cfg.power_switch.switch_id = 0
    # Résistance chauffante simulée : 4e relais legacy du Shelly unifié (id=3).
    cimier_cfg.rain_heater_switch.type = "shelly_gen1"
    cimier_cfg.rain_heater_switch.host = "127.0.0.1:8001"
    cimier_cfg.rain_heater_switch.switch_id = 3
```

- [ ] **Step 7: Lancer toute la suite cimier_service, vérifier qu'elle passe toujours**

Run: `uv run --extra dev pytest tests/test_cimier_service.py -v`
Expected: PASS (aucune régression — tous les appels `CimierService(...)` existants omettent `rain_heater_switch`, qui retombe sur `noop` par défaut)

- [ ] **Step 8: Commit**

```bash
git add services/cimier_service.py tests/test_cimier_service.py
git commit -m "$(cat <<'EOF'
feat(cimier): construit le switch de la résistance chauffante pluie

CimierService accepte rain_heater_switch (optionnel, noop par défaut),
construit via make_power_switch comme power_switch. Branché dans
_build_service_from_config (entry-point réel) et le dev-mode override
(4e relais du simulateur unifié, id=3).
EOF
)"
```

---

## Task 4 : Pilotage — armement/désarmement commande la résistance

**Files:**
- Modify: `services/cimier_service.py` (`_apply_rain_heater_state`, `_refresh_rain_armed_from_config`, `__init__` — application initiale)
- Test: `tests/test_cimier_service.py` (classe `TestRainHeaterSwitch`)

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter dans `TestRainHeaterSwitch` (créée au Task 3), et étendre `make_rain_service` :

D'abord, dans `make_rain_service` (fonction déjà existante, définie avant `class TestRainWatch`), ajouter un paramètre optionnel :

```python
def make_rain_service(
    tmp_path,
    rain,
    cimier_open=True,
    watch_interval_s=0.0,
    config_path=None,
    switch_reader=None,
    last_switches=None,
    rain_heater_switch=None,
):
    ...
    service = CimierService(
        cimier_config=cfg,
        power_switch=NoopPowerSwitch(),
        motor_shelly=NoopMotorShelly(),
        switch_reader=switch_reader
        if switch_reader is not None
        else FakeSwitchReader([(cimier_open, not cimier_open)]),
        rain_heater_switch=rain_heater_switch,
        ipc_manager=ipc,
        weather_provider=rain,
        config_path=config_path if config_path is not None else tmp_path / "absent.json",
        clock=clock,
        sleep=clock.sleep,
    )
```

(seul changement : nouveau paramètre `rain_heater_switch=None` propagé tel quel au constructeur — `None` retombe sur le `noop` par défaut de la config `CimierConfig()` utilisée par `make_rain_service`, donc tous les appels existants restent inchangés.)

Puis, dans `TestRainHeaterSwitch` :

```python
    def test_arming_turns_heater_on(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"cimier": {"weather_provider": {"protection_enabled": True}}})
        )
        heater = CountingPowerSwitch()
        rain = StubRainProtection(state="dry", armed=False)
        service = make_rain_service(
            tmp_path, rain, config_path=config_file, rain_heater_switch=heater
        )
        service.tick()
        assert heater.on_count == 1
        assert heater.off_count == 0

    def test_disarming_turns_heater_off(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"cimier": {"weather_provider": {"protection_enabled": False}}})
        )
        heater = CountingPowerSwitch()
        rain = StubRainProtection(state="dry", armed=True)
        service = make_rain_service(
            tmp_path, rain, config_path=config_file, rain_heater_switch=heater
        )
        service.tick()
        assert heater.off_count == 1
        assert heater.on_count == 0

    def test_unchanged_armed_state_does_not_recommand(self, tmp_path):
        """Idempotence : pas de re-commande tant que l'armement ne change pas."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"cimier": {"weather_provider": {"protection_enabled": True}}})
        )
        heater = CountingPowerSwitch()
        rain = StubRainProtection(state="dry", armed=False)
        service = make_rain_service(
            tmp_path, rain, config_path=config_file, rain_heater_switch=heater
        )
        service.tick()
        service.tick()
        assert heater.on_count == 1

    def test_initial_state_applied_at_construction_when_already_armed(self, tmp_path):
        """Redémarrage (OTA) avec la case déjà cochée : le chauffage suit dès le 1er tick."""
        heater = CountingPowerSwitch()
        rain = StubRainProtection(state="dry", armed=True)
        make_rain_service(tmp_path, rain, rain_heater_switch=heater)
        assert heater.on_count == 1

    def test_command_failure_does_not_block_arming(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"cimier": {"weather_provider": {"protection_enabled": True}}})
        )
        heater = FailingPowerSwitch()
        rain = StubRainProtection(state="dry", armed=False)
        service = make_rain_service(
            tmp_path, rain, config_path=config_file, rain_heater_switch=heater
        )
        service.tick()
        assert rain.armed is True
        assert service._rain_heater_status["last_command_ok"] is False

    def test_noop_heater_switch_is_not_configured(self, tmp_path):
        rain = StubRainProtection(state="dry", armed=True)
        service = make_rain_service(tmp_path, rain)  # rain_heater_switch=None → noop
        assert service._rain_heater_configured is False
        assert service._rain_heater_status == {}
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `uv run --extra dev pytest tests/test_cimier_service.py -k TestRainHeaterSwitch -v`
Expected: FAIL — `test_arming_turns_heater_on` etc. échouent avec `assert 0 == 1` (aucune commande envoyée), `test_command_failure_does_not_block_arming` échoue avec `AttributeError: '_rain_heater_status'`.

- [ ] **Step 3: Écrire `_apply_rain_heater_state`**

Dans `services/cimier_service.py`, juste avant `_close_session_for_rain` (repérer le commentaire `# Veille pluie` et la méthode `_refresh_rain_armed_from_config`), ajouter la nouvelle méthode juste après `_refresh_rain_armed_from_config` :

```python
    def _apply_rain_heater_state(self, armed: bool) -> None:
        """Commande la résistance chauffante sur transition d'armement.

        Une seule tentative : un échec ne doit jamais bloquer l'armement de la
        protection pluie elle-même (fail-safe), et se voit dans le statut
        publié plutôt que de nécessiter une lecture de log. Rien n'est publié
        si aucun Shelly n'est configuré (`type=noop`) — appeler turn_on/off
        sur le NoopPowerSwitch reste inoffensif, mais un badge sans matériel
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
            logger.error(
                "cimier_event=rain_heater_command_failed armed=%s exc=%s", armed, exc
            )
            self._rain_heater_status = {
                "configured": True,
                "on": None,
                "last_command_ok": False,
                "error": str(exc),
            }
        else:
            self._rain_heater_status = {
                "configured": True,
                "on": armed,
                "last_command_ok": True,
                "error": None,
            }
```

- [ ] **Step 4: Brancher l'application initiale dans `__init__`**

Dans `services/cimier_service.py`, `CimierService.__init__`, repérer :

```python
        self._close_session_fn: Optional[Callable[[str], Dict[str, Any]]] = None
        self._motor_ipc = motor_ipc

        self._publish_status(
```

Remplacer par :

```python
        self._close_session_fn: Optional[Callable[[str], Dict[str, Any]]] = None
        self._motor_ipc = motor_ipc

        # Résistance chauffante (2026-09) : appliquée une fois ici pour que
        # l'état corresponde à l'armement dès le premier tick, y compris
        # après un redémarrage (OTA) avec la case déjà cochée — sans cela,
        # _refresh_rain_armed_from_config ne détecterait jamais de
        # transition puisque provider.armed vaut déjà cette valeur.
        self._rain_heater_status: Dict[str, Any] = {}
        self._apply_rain_heater_state(bool(getattr(self._weather_provider, "armed", False)))

        self._publish_status(
```

- [ ] **Step 5: Brancher la transition dans `_refresh_rain_armed_from_config`**

Dans `services/cimier_service.py`, méthode `_refresh_rain_armed_from_config`, repérer :

```python
        armed = bool(section.get("protection_enabled"))
        if armed != provider.armed:
            logger.info(
                "cimier_event=rain_protection_changed from=%s to=%s source=config_hot_reload",
                provider.armed,
                armed,
            )
            provider.armed = armed
```

Remplacer par :

```python
        armed = bool(section.get("protection_enabled"))
        if armed != provider.armed:
            logger.info(
                "cimier_event=rain_protection_changed from=%s to=%s source=config_hot_reload",
                provider.armed,
                armed,
            )
            provider.armed = armed
            self._apply_rain_heater_state(armed)
```

- [ ] **Step 6: Lancer les tests, vérifier qu'ils passent**

Run: `uv run --extra dev pytest tests/test_cimier_service.py -k "TestRainHeaterSwitch or TestRainWatch" -v`
Expected: PASS (tous les tests, nouveaux et existants)

- [ ] **Step 7: Lancer toute la suite cimier_service**

Run: `uv run --extra dev pytest tests/test_cimier_service.py -v`
Expected: PASS intégral, aucune régression

- [ ] **Step 8: Commit**

```bash
git add services/cimier_service.py tests/test_cimier_service.py
git commit -m "$(cat <<'EOF'
feat(cimier): asservit la résistance chauffante à l'armement pluie

_apply_rain_heater_state commande ON/OFF sur transition d'armement
(hot-reload config existant) + une fois à la construction pour
survivre à un redémarrage OTA. Échec réseau loggé et exposé dans
_rain_heater_status, n'empêche jamais l'armement (fail-safe).
EOF
)"
```

---

## Task 5 : Statut publié — `cimier_status.json` → `rain.heater`

**Files:**
- Modify: `services/cimier_service.py:974-1009` (`_publish_status`)
- Test: `tests/test_cimier_service.py` (classe `TestRainHeaterSwitch`)

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter dans `TestRainHeaterSwitch` :

```python
    def test_heater_status_is_published_when_configured(self, tmp_path):
        heater = CountingPowerSwitch()
        rain = StubRainProtection(state="dry", armed=True)
        service = make_rain_service(tmp_path, rain, rain_heater_switch=heater)
        service.tick()
        payload = json.loads((tmp_path / "status.json").read_text())
        assert payload["rain"]["heater"] == {
            "configured": True,
            "on": True,
            "last_command_ok": True,
            "error": None,
        }

    def test_heater_status_absent_when_not_configured(self, tmp_path):
        rain = StubRainProtection(state="dry", armed=True)
        service = make_rain_service(tmp_path, rain)  # noop par défaut
        service.tick()
        payload = json.loads((tmp_path / "status.json").read_text())
        assert "heater" not in payload.get("rain", {})
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `uv run --extra dev pytest tests/test_cimier_service.py -k "test_heater_status" -v`
Expected: FAIL — `KeyError: 'heater'` sur le premier test (clé absente du payload publié)

- [ ] **Step 3: Étendre `_publish_status`**

Dans `services/cimier_service.py`, méthode `_publish_status`, repérer :

```python
        if self._rain_enabled:
            payload["rain"] = self._weather_provider.describe()
        if remaining_quiet_s is not None:
```

Remplacer par :

```python
        if self._rain_enabled:
            payload["rain"] = self._weather_provider.describe()
        if self._rain_heater_status.get("configured"):
            payload.setdefault("rain", {})["heater"] = self._rain_heater_status
        if remaining_quiet_s is not None:
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `uv run --extra dev pytest tests/test_cimier_service.py -k "test_heater_status" -v`
Expected: PASS

- [ ] **Step 5: Suite complète cimier_service**

Run: `uv run --extra dev pytest tests/test_cimier_service.py -v`
Expected: PASS intégral

- [ ] **Step 6: Commit**

```bash
git add services/cimier_service.py tests/test_cimier_service.py
git commit -m "$(cat <<'EOF'
feat(cimier): publie le statut de la résistance chauffante

cimier_status.json expose rain.heater (configured/on/last_command_ok/
error) dès que rain_heater_switch n'est pas noop, indépendamment de
la présence d'un capteur pluie réel — forwardé tel quel par
/api/cimier/status/, aucun changement Django nécessaire.
EOF
)"
```

---

## Task 6 : Simulateur dev — 4e relais legacy (résistance chauffante)

**Files:**
- Modify: `core/hardware/cimier_simulator.py`
- Test: `tests/test_cimier_simulator.py`

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `tests/test_cimier_simulator.py`, modifier `test_relay_endpoints_return_200` :

```python
def test_relay_endpoints_return_200(sim):
    for relay in (0, 1, 2, 3):
        payload = _get_json(sim.url + "/relay/{}?turn=on".format(relay))
        assert "ison" in payload
```

Puis ajouter, à la fin du fichier :

```python
def test_heater_relay_toggles_independently_of_motion(sim):
    """Relais 3 (résistance chauffante) : ON/OFF simple, sans lien avec le mécanisme."""
    payload_on = _get_json(sim.url + "/relay/3?turn=on")
    assert payload_on["ison"] is True
    payload_off = _get_json(sim.url + "/relay/3?turn=off")
    assert payload_off["ison"] is False
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `uv run --extra dev pytest tests/test_cimier_simulator.py -v`
Expected: FAIL — `test_relay_endpoints_return_200` échoue sur `relay=3` (`{"error": "unknown_relay", "id": 3}`, pas de clé `ison`) ; `test_heater_relay_toggles_independently_of_motion` échoue de même.

- [ ] **Step 3: Ajouter le relais au simulateur**

Dans `core/hardware/cimier_simulator.py`, repérer :

```python
RELAY_24V = 0
RELAY_MOT = 1
RELAY_UPDN = 2
```

Remplacer par :

```python
RELAY_24V = 0
RELAY_MOT = 1
RELAY_UPDN = 2
RELAY_HEATER = 3  # résistance chauffante anti-rosée du capteur de pluie (2026-09)
```

Dans `CimierSimulator.__init__`, repérer :

```python
        self._power_on = False  # relais 24V
        self._raining = False  # entrée pluie simulée (bascule via /dev/rain)
```

Remplacer par :

```python
        self._power_on = False  # relais 24V
        self._heater_on = False  # relais résistance chauffante (id=3)
        self._raining = False  # entrée pluie simulée (bascule via /dev/rain)
```

Dans `CimierSimulator.set_relay`, repérer :

```python
            if relay_id == RELAY_UPDN:
                self._mechanism.set_direction(open_direction=on)
                return on
            return None
```

Remplacer par :

```python
            if relay_id == RELAY_UPDN:
                self._mechanism.set_direction(open_direction=on)
                return on
            if relay_id == RELAY_HEATER:
                self._heater_on = on
                return on
            return None
```

- [ ] **Step 4: Mettre à jour le docstring du module**

Dans `core/hardware/cimier_simulator.py`, en tête de fichier, repérer :

```
  - 3 relais legacy (Gen 1) : ``GET /relay/<n>?turn=on|off`` →
    ``{"ison": <bool>}``. n=0 → 24V (alim), n=1 → MOT (moteur), n=2 → UPDN
    (sens : ON = ouverture).
```

Remplacer par :

```
  - 4 relais legacy (Gen 1) : ``GET /relay/<n>?turn=on|off`` →
    ``{"ison": <bool>}``. n=0 → 24V (alim), n=1 → MOT (moteur), n=2 → UPDN
    (sens : ON = ouverture), n=3 → résistance chauffante du capteur de pluie
    (2026-09, sans lien avec le mécanisme).
```

- [ ] **Step 5: Lancer les tests, vérifier qu'ils passent**

Run: `uv run --extra dev pytest tests/test_cimier_simulator.py -v`
Expected: PASS intégral

- [ ] **Step 6: Commit**

```bash
git add core/hardware/cimier_simulator.py tests/test_cimier_simulator.py
git commit -m "$(cat <<'EOF'
feat(cimier): simule le relais de la résistance chauffante (id=3)

4e relais legacy du Shelly unifié dev, indépendant du mécanisme —
permet d'exercer armement→ON / désarmement→OFF de bout en bout sur
la stack dev sans matériel.
EOF
)"
```

---

## Task 7 : Badge dashboard — chauffage ON/OFF/injoignable

**Files:**
- Modify: `web/templates/dashboard.html:404-409`
- Modify: `web/static/js/dashboard.js` (après `rainStateClass`, ligne ~1305)
- Modify: `web/static/css/dashboard.css` (après `.rain-pill-unknown`, ligne ~1202)

Pas de test pytest (frontend pur, aucune logique serveur ajoutée — `cimier_status.json` est déjà forwardé tel quel par `StatusView`, vérifié Task 5). Vérification par étape manuelle en fin de tâche.

- [ ] **Step 1: Ajouter les fonctions JS de libellé/classe**

Dans `web/static/js/dashboard.js`, juste après `window.rainStateClass = rainStateClass;` (repérer le bloc `rainStateLabel`/`rainStateClass`) :

```javascript
// Badge résistance chauffante anti-rosée (2026-09). Source : cimier_status.json,
// clé `rain.heater` — absente si aucun Shelly n'est configuré (type=noop).
function heaterStateLabel() {
    const heater = Alpine.store('dashboard').cimier?.rain?.heater;
    if (!heater) return '';
    if (heater.last_command_ok === false) return '⚠ Chauffage injoignable';
    if (heater.on === true) return 'Chauffage : ON';
    if (heater.on === false) return 'Chauffage : OFF';
    return '';
}
window.heaterStateLabel = heaterStateLabel;

function heaterStateClass() {
    const heater = Alpine.store('dashboard').cimier?.rain?.heater;
    if (!heater) return '';
    if (heater.last_command_ok === false) return 'rain-pill heater-pill-error';
    if (heater.on === true) return 'rain-pill heater-pill-on';
    return 'rain-pill heater-pill-off';
}
window.heaterStateClass = heaterStateClass;
```

- [ ] **Step 2: Ajouter le markup HTML**

Dans `web/templates/dashboard.html`, juste après le `<span id="cimier-rain-state" ...>` (avant le bouton de toggle timeline « Activité cimier ») :

```html
                    <span id="cimier-rain-state" class="font-mono"
                          :class="window.rainStateClass ? window.rainStateClass() : ''"
                          x-text="window.rainStateLabel ? window.rainStateLabel() : ''"
                          x-show="$store.dashboard.cimier?.rain" x-cloak
                          role="status" aria-live="polite"
                          aria-label="État du capteur de pluie"></span>
                    <span id="cimier-heater-state" class="font-mono"
                          :class="window.heaterStateClass ? window.heaterStateClass() : ''"
                          x-text="window.heaterStateLabel ? window.heaterStateLabel() : ''"
                          x-show="$store.dashboard.cimier?.rain?.heater" x-cloak
                          role="status" aria-live="polite"
                          aria-label="État de la résistance chauffante du capteur de pluie"></span>
```

(le nouveau `<span>` s'ajoute après celui existant, sans le modifier — même structure, même style tactile sans survol.)

- [ ] **Step 3: Ajouter les classes CSS**

Dans `web/static/css/dashboard.css`, juste après `.rain-pill-unknown { ... }` :

```css
.heater-pill-on {
    color: #00d26a;
    border-color: rgba(0, 210, 106, 0.4);
    background: rgba(0, 210, 106, 0.08);
}
.heater-pill-off {
    color: #9aa4b2;
    border-color: rgba(154, 164, 178, 0.4);
    background: rgba(154, 164, 178, 0.08);
}
.heater-pill-error {
    color: #ffa502;
    border-color: rgba(255, 165, 2, 0.4);
    background: rgba(255, 165, 2, 0.08);
}
```

- [ ] **Step 4: Vérification manuelle sur la stack dev**

Run (si pas déjà démarré) : `./start_dev.sh start`

Armer la protection pluie et vérifier le badge :
```bash
curl -s -X POST http://127.0.0.1:8000/api/cimier/automation/ \
     -H "Content-Type: application/json" \
     -d '{"rain_protection": true}'
sleep 3
cat /dev/shm/cimier_status.json | python3 -m json.tool | grep -A5 '"heater"'
```
Expected (une fois `rain_heater_switch` pointé sur le simulateur dev — cf. Task 3 Step 6, actif automatiquement via `CIMIER_DEV_MODE=1`) : bloc `"heater": {"configured": true, "on": true, "last_command_ok": true, "error": null}`.

Ouvrir `http://127.0.0.1:8000/` dans un navigateur, cocher/décocher « Protection pluie », observer le badge « Chauffage : ON »/« Chauffage : OFF » apparaître à côté de la pastille SEC/PLUIE sans rechargement de page (polling existant).

- [ ] **Step 5: Commit**

```bash
git add web/templates/dashboard.html web/static/js/dashboard.js web/static/css/dashboard.css
git commit -m "$(cat <<'EOF'
feat(cimier): badge dashboard pour la résistance chauffante pluie

Affiche ON/OFF/injoignable à côté de la pastille SEC/PLUIE, lu
depuis cimier_status.json (rain.heater) déjà pollé — aucune requête
supplémentaire, aucune dépendance au survol (écran tactile).
EOF
)"
```

---

## Task 8 : Version, suite complète, vérification finale

**Files:**
- Modify: `pyproject.toml:3`

- [ ] **Step 1: Bump de version**

Dans `pyproject.toml`, remplacer :
```toml
version = "6.15.2"
```
par :
```toml
version = "6.15.3"
```

- [ ] **Step 2: Suite complète pytest**

Run: `uv run --extra dev pytest -v`
Expected: PASS intégral (aucune régression sur les ~1341 tests existants + les nouveaux de ce plan)

- [ ] **Step 3: Lint**

Run: `uv run --extra dev ruff format --check core/ services/ tests/test_config_loader.py tests/test_cimier_service.py tests/test_cimier_simulator.py`
Run: `uv run --extra dev ruff check core/ services/`
Expected: aucune erreur (corriger si le formatage diffère : `uv run --extra dev ruff format core/ services/ tests/test_config_loader.py tests/test_cimier_service.py tests/test_cimier_simulator.py`)

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "$(cat <<'EOF'
chore: bump version 6.15.2 → 6.15.3

Résistance chauffante capteur de pluie asservie à l'armement de la
protection pluie (config rain_heater_switch, statut temps réel
dashboard).
EOF
)"
```

---

## Hors périmètre (rappel spec)

- Pas de retry automatique en cas d'échec de commande (une seule tentative par transition, décision produit).
- Pas d'asservissement à une sonde de température/humidité — tout-ou-rien sur l'armement.
- `data/config.json` terrain (dé-tracké, hors dépôt) : valeur réelle (`type=shelly_gen1, host=192.168.1.78`) à saisir par Serge via `/configuration/` ou SSH, pas dans ce plan.
