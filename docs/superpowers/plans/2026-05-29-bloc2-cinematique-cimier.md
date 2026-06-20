# Bloc 2 — Cinématique Shelly Cimier (orchestration + garde-fou + logging)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refondre `services/cimier_service._run_cycle` pour piloter le moteur cimier via 2 relais Shelly (au lieu d'envoyer `/open` `/close` au Pico W), avec un garde-fou symétrique « déjà en butée » exécuté en pré-vol et un logging d'orchestration qui rende chaque cycle entièrement reconstructible à 800 km du site.

**Architecture :** Le `cimier_service` reçoit une instance `MotorShelly` (réelle ou `SimMotorShelly`) en plus du `power_switch` existant. Un cycle nominal devient : pré-vol switches → power_on (Shelly 24 V) → settle (~2 s appairage WiFi) → `motor.turn_off()` défensif → `motor.set_direction(open=...)` → `motor.turn_on(timer_s=timer_safety_sec)` → polling `/status` jusqu'à la butée cible → `motor.turn_off()` → `power_off`. L'invariant 220 V (`power_switch.turn_off()` dans `finally`) est préservé. Toutes les requêtes Shelly sont chronométrées et journalisées en INFO ; le mode DEBUG (`cimier.verbose_logging=true` ou `CIMIER_DEV_MODE=1`) ajoute la trace par itération de polling.

**Tech Stack :** Python 3.11+, `urllib.request`, `logging` (events `cimier_event=clé=valeur`), pytest, `MotorShelly` (commit `012b494`), `CimierMechanismSim` + `SimMotorShelly` (Bloc 1, commits `ca7884a` / `8ddb21f`), `CimierSimulator` capteur-only (Bloc 1, commit `828e229`).

**Décisions de cadre (rappel des mémoires) :**
- **Pas de bump `pyproject.toml`** pendant le chantier cimier — un seul bump en fin de chantier (décision JP 2026-05-23, exception ciblée à `feedback_version_bump`).
- **Pas de push `origin/main`** pendant le chantier (Bloc 1 mergé en local, non poussé) — chaque tâche se termine par un `git commit` local, pas de `git push`.
- **Aucune IP en dur** : tout passe par `data/config.json → cimier.motor_shelly.host_motor` / `host_dir` (cf. `feedback_no_hardcoded_ips`).
- **Périmètre pytest restreint** aux modules touchés (`feedback_tests_scope`) : `test_cimier_service`, `test_motor_shelly`, `test_cimier_simulator`, `test_cimier_controller`, `test_config_loader`, `test_power_switch`.

---

## File Structure

**Modifié :**
- `services/cimier_service.py` (~826 LOC actuels) : refonte `_run_cycle`, ajout pré-vol, refonte phases, ajout factory `make_motor_shelly`, helper `_call_shelly_logged`, helper `_poll_target_switch`. Suppression de `_push_invert_config`, `_post_action`, `_poll_cycle_complete`, `_try_post_stop_silent` (HTTP Pico /open|/close|/config — caducs en archi Shelly).
- `tests/test_cimier_service.py` (~1417 LOC actuels) : refonte de la fixture `simulator` (ne passe plus `steps_per_cycle`/`tick_period_ms`/`cycle_timeout_s` au `CimierSimulator`), réécriture de `TestFullCycleViaSimulator` (7 tests `@pytest.mark.skip`) + `TestWeatherProviderWiring::test_cycle_logs_weather_on_start` (1 test `@pytest.mark.skip`), nouvelles sections garde-fou + cinématique + logging.

**Inchangés (référence) :**
- `core/hardware/motor_shelly.py` (commit `012b494`) — `MotorShelly` est consommé tel quel.
- `core/hardware/sim_motor_shelly.py` + `core/hardware/cimier_mechanism_sim.py` (Bloc 1) — utilisés via fixture sim.
- `core/config/config_loader.py` — `MotorShellyConfig` déjà câblé (commit `012b494`), `CimierConfig.motor_shelly` déjà chargé.
- `firmware/cimier/*` — pas touché par Bloc 2 (la doc firmware on-device est dans le backlog item 3, hors scope).

**Nouvelles constantes (dans `services/cimier_service.py`) :**
- `PHASE_PREFLIGHT = "preflight"`
- `PHASE_SETTLE = "settle"`
- `PHASE_SET_DIR = "set_dir"`
- `PHASE_MOTOR_ON = "motor_on"`
- `PHASE_POLL_SWITCH = "poll_switch"`
- `PHASE_MOTOR_OFF = "motor_off"`

Les constantes obsolètes (`PHASE_BOOT_POLL`, `PHASE_PUSH_CONFIG`, `PHASE_COMMAND_PICO`, `PHASE_CYCLE_POLL`) sont supprimées.

---

## Stratégie d'exécution

Strict TDD, granularité fine, **un commit par tâche** (sans push). Une tâche = une étape logique de la cinématique. Les sub-steps suivent le rituel RED → GREEN → REFACTOR → COMMIT.

Avant de commencer, **création d'une branche de travail** :

```bash
git checkout -b feat/bloc2-cinematique-cimier
```

Toutes les tâches commitent sur cette branche. À la fin du Bloc 2 (après T8), merge fast-forward dans `main` local **sans push** (cf. décision 23/05).

---

## Task 1 : Squelette — phases, factory, injection MotorShelly

**Files:**
- Modify: `services/cimier_service.py:65-90` (constantes phases)
- Modify: `services/cimier_service.py:130-160` (factory + import)
- Modify: `services/cimier_service.py:270-370` (constructeur CimierService)
- Test: `tests/test_cimier_service.py` (nouvelle section `TestMotorShellyInjection`)

**Objectif** : préparer le squelette sans toucher la logique de `_run_cycle`. Tous les tests existants doivent rester verts. Les nouveaux tests vérifient juste que le constructeur accepte `motor_shelly` et que la factory câble bien `MotorShelly` ou un `NoopMotorShelly` selon la config.

- [ ] **Step 1.1 : Écrire le test RED — factory `make_motor_shelly` retourne `MotorShelly` quand `host_motor` et `host_dir` sont renseignés**

Ajouter dans `tests/test_cimier_service.py` à la fin de la section `TestConfigurationAndInstantiation` (~ligne 325) :

```python
from core.config.config_loader import MotorShellyConfig
from core.hardware.motor_shelly import MotorShelly
from services.cimier_service import (
    NoopMotorShelly,
    make_motor_shelly,
)


class TestMotorShellyFactory:
    def test_factory_returns_motor_shelly_when_hosts_configured(self) -> None:
        cfg = MotorShellyConfig(
            host_motor="192.168.1.85",
            host_dir="192.168.1.86",
            relay_motor=0,
            relay_dir=0,
            open_dir_state=True,
            motor_on_relay_state=False,
            api="rpc",
            timer_safety_sec=90.0,
        )
        m = make_motor_shelly(cfg)
        assert isinstance(m, MotorShelly)
        assert m.host_motor == "192.168.1.85"
        assert m.host_dir == "192.168.1.86"
        assert m.motor_on_relay_state is False

    def test_factory_returns_noop_when_hosts_empty(self) -> None:
        cfg = MotorShellyConfig(host_motor="", host_dir="")
        m = make_motor_shelly(cfg)
        assert isinstance(m, NoopMotorShelly)

    def test_factory_returns_noop_when_only_one_host(self) -> None:
        cfg = MotorShellyConfig(host_motor="192.168.1.85", host_dir="")
        m = make_motor_shelly(cfg)
        assert isinstance(m, NoopMotorShelly)
```

- [ ] **Step 1.2 : Vérifier que le test échoue**

```bash
uv run pytest tests/test_cimier_service.py::TestMotorShellyFactory -v
```

Expected: `ImportError` ou `AttributeError` sur `NoopMotorShelly` / `make_motor_shelly`.

- [ ] **Step 1.3 : Implémenter `NoopMotorShelly` + `make_motor_shelly` dans `services/cimier_service.py`**

Ajouter après la définition `ACTION_STOP = "stop"` (~ligne 87) :

```python
# Phases publiées dans cimier_status.json["phase"] (Bloc 2 — archi Shelly)
PHASE_PREFLIGHT = "preflight"
PHASE_SETTLE = "settle"
PHASE_SET_DIR = "set_dir"
PHASE_MOTOR_ON = "motor_on"
PHASE_POLL_SWITCH = "poll_switch"
PHASE_MOTOR_OFF = "motor_off"
```

Supprimer les lignes :

```python
PHASE_BOOT_POLL = "boot_poll"
PHASE_PUSH_CONFIG = "push_config"
PHASE_COMMAND_PICO = "command_pico"
PHASE_CYCLE_POLL = "cycle_poll"
```

Ajouter en haut du fichier l'import :

```python
from core.config.config_loader import MotorShellyConfig  # ajout à l'import existant
from core.hardware.motor_shelly import MotorShelly
```

Puis ajouter, juste après le bloc `make_power_switch` (ligne ~141) :

```python
class NoopMotorShelly:
    """Double inerte de MotorShelly : aucune requête réseau.

    Utilisé quand la config motor_shelly est incomplète (host_motor ou
    host_dir vide) — typiquement install terrain pas encore câblée, ou en
    tests qui veulent juste un placeholder. Toutes les méthodes sont des
    no-ops loggées pour la traçabilité.
    """

    def set_direction(self, open_direction: bool) -> None:
        logger.info("cimier_event=noop_motor call=set_direction open=%s", open_direction)

    def turn_on(self, timer_s: float = 0.0) -> None:
        logger.info("cimier_event=noop_motor call=turn_on timer_s=%.1f", timer_s)

    def turn_off(self) -> None:
        logger.info("cimier_event=noop_motor call=turn_off")


def make_motor_shelly(cfg: MotorShellyConfig):
    """Factory MotorShelly. Retourne NoopMotorShelly si hosts incomplets."""
    if not cfg.host_motor or not cfg.host_dir:
        return NoopMotorShelly()
    return MotorShelly(
        host_motor=cfg.host_motor,
        host_dir=cfg.host_dir,
        relay_motor=cfg.relay_motor,
        relay_dir=cfg.relay_dir,
        open_dir_state=cfg.open_dir_state,
        motor_on_relay_state=cfg.motor_on_relay_state,
        api=cfg.api,
        timeout_s=cfg.timeout_s,
    )
```

- [ ] **Step 1.4 : Vérifier les tests passent**

```bash
uv run pytest tests/test_cimier_service.py::TestMotorShellyFactory -v
```

Expected: 3 PASS.

- [ ] **Step 1.5 : Test RED — `CimierService.__init__` accepte `motor_shelly`**

Ajouter dans la même classe `TestMotorShellyFactory` (ou nouvelle classe `TestMotorShellyInjection`) :

```python
class TestMotorShellyInjection:
    def test_constructor_accepts_motor_shelly(
        self,
        cimier_config_default: CimierConfig,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        from core.hardware.cimier_mechanism_sim import CimierMechanismSim
        from core.hardware.sim_motor_shelly import SimMotorShelly

        mech = CimierMechanismSim()
        sim_motor = SimMotorShelly(mech)
        ps = CountingPowerSwitch()
        service = CimierService(
            cimier_config=cimier_config_default,
            power_switch=ps,
            motor_shelly=sim_motor,
            ipc_manager=ipc_manager,
        )
        assert service.motor_shelly is sim_motor

    def test_constructor_defaults_motor_shelly_to_factory(
        self,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        # CimierConfig avec motor_shelly.host vides → NoopMotorShelly
        cfg = CimierConfig(enabled=True, host="127.0.0.1", port=80)
        ps = CountingPowerSwitch()
        service = CimierService(
            cimier_config=cfg, power_switch=ps, ipc_manager=ipc_manager
        )
        assert isinstance(service.motor_shelly, NoopMotorShelly)
```

- [ ] **Step 1.6 : Vérifier que le test échoue**

```bash
uv run pytest tests/test_cimier_service.py::TestMotorShellyInjection -v
```

Expected: FAIL (`motor_shelly` n'est ni attribut ni paramètre).

- [ ] **Step 1.7 : Implémenter l'injection dans `CimierService.__init__`**

Localiser la signature du constructeur (~ligne 273) et ajouter le paramètre `motor_shelly` après `power_switch` :

```python
def __init__(
    self,
    cimier_config: CimierConfig,
    power_switch: PowerSwitchProtocol,
    *,
    motor_shelly=None,           # NOUVEAU — None → factory depuis cimier_config.motor_shelly
    http_client: Optional[HttpClient] = None,
    # ... reste inchangé
):
    # ... corps existant ...
    self._power_switch = power_switch
    self.motor_shelly = (
        motor_shelly
        if motor_shelly is not None
        else make_motor_shelly(cimier_config.motor_shelly)
    )
```

- [ ] **Step 1.8 : Vérifier que tous les tests passent**

```bash
uv run pytest tests/test_cimier_service.py -v
```

Expected: les tests existants (non-skip) restent verts, les 5 nouveaux passent.

- [ ] **Step 1.9 : Commit**

```bash
git add services/cimier_service.py tests/test_cimier_service.py
git commit -m "feat(cimier-bloc2): squelette MotorShelly injecté + factory + nouvelles phases

T1 — Préparation cinématique Shelly :
- NoopMotorShelly (placeholder inert pour config incomplète)
- make_motor_shelly() factory (hosts vides → Noop, sinon MotorShelly réel)
- CimierService.__init__ accepte motor_shelly kwarg (défaut: factory)
- Constantes PHASE_PREFLIGHT/SETTLE/SET_DIR/MOTOR_ON/POLL_SWITCH/MOTOR_OFF
- Suppression PHASE_BOOT_POLL/PUSH_CONFIG/COMMAND_PICO/CYCLE_POLL
- 5 tests TestMotorShellyFactory + TestMotorShellyInjection

Logique _run_cycle inchangée à cette étape — refonte en T3+."
```

---

## Task 2 : Garde-fou pré-vol — RED puis GREEN

**Files:**
- Modify: `services/cimier_service.py` (nouvelle méthode `_preflight_switches` + branchement en tête de `_run_cycle`)
- Test: `tests/test_cimier_service.py` (nouvelle section `TestPreflightGuard`)

**Objectif** : avant toute action électrique, lire `/status` du Pico W et décider `noop` / `proceed` / `error` / `unreachable`. Aucune alimentation tant que le garde-fou n'a pas validé.

- [ ] **Step 2.1 : Test RED — open + open_switch=True → no-op**

Ajouter dans `tests/test_cimier_service.py` une nouvelle section `TestPreflightGuard` :

```python
class TestPreflightGuard:
    """Garde-fou « déjà en butée » : 0 action électrique si fin de course cible atteinte."""

    def _make_service(
        self,
        ipc_manager,
        switches_payload: dict,
        unreachable: bool = False,
    ):
        ps = CountingPowerSwitch()
        fake = AutoFakeHttpClient()
        if unreachable:
            fake.set_status_response_error(urllib.error.URLError("nope"))
        else:
            fake.set_status_response(switches_payload)
        from core.hardware.cimier_mechanism_sim import CimierMechanismSim
        from core.hardware.sim_motor_shelly import SimMotorShelly

        mech = CimierMechanismSim()
        sim_motor = SimMotorShelly(mech)
        cfg = CimierConfig(
            enabled=True,
            host="127.0.0.1",
            port=80,
            cycle_timeout_s=2.0,
            post_off_quiet_s=0.0,
            shelly_settle_s=0.0,
        )
        clock = MockClock()
        service = CimierService(
            cimier_config=cfg,
            power_switch=ps,
            motor_shelly=sim_motor,
            http_client=fake,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=clock.sleep,
        )
        return service, ps, sim_motor, ipc_manager

    def test_open_when_already_open_is_noop(
        self, ipc_manager: RecordingIpcManager
    ) -> None:
        service, ps, sim_motor, _ = self._make_service(
            ipc_manager,
            switches_payload={"state": "open", "open_switch": True, "closed_switch": False},
        )
        service._dispatch_command({"id": "1", "action": "open"})
        # Aucun appel électrique
        assert ps.on_count == 0
        assert ps.off_count == 0
        assert sim_motor.calls == []
        # État publié = open, phase = idle (no-op)
        last = ipc_manager.history[-1]
        assert last["state"] == CIMIER_STATE_OPEN
        assert last["error_message"] in ("", None)

    def test_close_when_already_closed_is_noop(
        self, ipc_manager: RecordingIpcManager
    ) -> None:
        service, ps, sim_motor, _ = self._make_service(
            ipc_manager,
            switches_payload={"state": "closed", "open_switch": False, "closed_switch": True},
        )
        service._dispatch_command({"id": "2", "action": "close"})
        assert ps.on_count == 0
        assert sim_motor.calls == []
        last = ipc_manager.history[-1]
        assert last["state"] == CIMIER_STATE_CLOSED

    def test_both_switches_true_blocks_with_error(
        self, ipc_manager: RecordingIpcManager
    ) -> None:
        service, ps, sim_motor, _ = self._make_service(
            ipc_manager,
            switches_payload={"state": "error", "open_switch": True, "closed_switch": True},
        )
        service._dispatch_command({"id": "3", "action": "open"})
        assert ps.on_count == 0
        assert sim_motor.calls == []
        last = ipc_manager.history[-1]
        assert last["state"] == STATE_ERROR
        assert last["error_message"] == "both_switches_triggered"

    def test_status_unreachable_blocks_with_error(
        self, ipc_manager: RecordingIpcManager
    ) -> None:
        service, ps, sim_motor, _ = self._make_service(
            ipc_manager,
            switches_payload={},
            unreachable=True,
        )
        service._dispatch_command({"id": "4", "action": "open"})
        assert ps.on_count == 0
        assert sim_motor.calls == []
        last = ipc_manager.history[-1]
        assert last["state"] == STATE_ERROR
        assert last["error_message"] == "precheck_unreachable"
```

Ajouter dans `AutoFakeHttpClient` (au-dessus, ~ligne où il est défini) si les helpers `set_status_response` / `set_status_response_error` n'existent pas, des méthodes minimales :

```python
def set_status_response(self, payload: dict) -> None:
    """Force le prochain GET /status à renvoyer ce payload (status 200)."""
    self._status_override = (200, payload)

def set_status_response_error(self, exc: Exception) -> None:
    """Force le prochain GET /status à lever cette exception."""
    self._status_exc = exc
```

Et adapter la méthode `request` de `AutoFakeHttpClient` pour consommer ces overrides en priorité (si nécessaire — examiner la classe existante à la lecture).

- [ ] **Step 2.2 : Vérifier que les tests échouent**

```bash
uv run pytest tests/test_cimier_service.py::TestPreflightGuard -v
```

Expected: 4 FAIL (le pré-vol n'existe pas, le cycle s'exécute normalement → power_on est appelé).

- [ ] **Step 2.3 : Implémenter `_preflight_switches` dans `services/cimier_service.py`**

Ajouter juste avant `_run_cycle` (~ligne 397) :

```python
def _preflight_switches(self, action: str, cmd_id: str) -> tuple:
    """Lit /status du Pico W avant toute action électrique.

    Retourne un tuple (decision, reason, payload) :
      - decision: "noop"|"proceed"|"error"|"unreachable"
      - reason: chaîne lisible (vide si proceed)
      - payload: dict /status si lu, {} sinon
    """
    url = self._base_url() + "/status"
    t0 = self._clock()
    try:
        status, payload = self._http.request("GET", url)
    except (urllib.error.URLError, OSError, ConnectionError) as exc:
        latency_ms = int((self._clock() - t0) * 1000)
        logger.info(
            "cimier_event=preflight action=%s id=%s decision=unreachable "
            "latency_ms=%d exc=%s",
            action, cmd_id, latency_ms, exc,
        )
        return ("unreachable", "precheck_unreachable", {})

    latency_ms = int((self._clock() - t0) * 1000)
    if status != 200 or not isinstance(payload, dict):
        logger.info(
            "cimier_event=preflight action=%s id=%s decision=unreachable "
            "latency_ms=%d http_status=%s",
            action, cmd_id, latency_ms, status,
        )
        return ("unreachable", "precheck_unreachable", {})

    open_sw = bool(payload.get("open_switch", False))
    closed_sw = bool(payload.get("closed_switch", False))

    if open_sw and closed_sw:
        logger.info(
            "cimier_event=preflight action=%s id=%s decision=error "
            "reason=both_switches_triggered open_switch=true closed_switch=true "
            "latency_ms=%d",
            action, cmd_id, latency_ms,
        )
        return ("error", "both_switches_triggered", payload)

    if action == ACTION_OPEN and open_sw:
        logger.info(
            "cimier_event=preflight action=open id=%s decision=noop "
            "reason=already_open latency_ms=%d", cmd_id, latency_ms,
        )
        return ("noop", "already_open", payload)

    if action == ACTION_CLOSE and closed_sw:
        logger.info(
            "cimier_event=preflight action=close id=%s decision=noop "
            "reason=already_closed latency_ms=%d", cmd_id, latency_ms,
        )
        return ("noop", "already_closed", payload)

    logger.info(
        "cimier_event=preflight action=%s id=%s decision=proceed "
        "open_switch=%s closed_switch=%s latency_ms=%d",
        action, cmd_id, str(open_sw).lower(), str(closed_sw).lower(), latency_ms,
    )
    return ("proceed", "", payload)
```

- [ ] **Step 2.4 : Brancher `_preflight_switches` en tête de `_run_cycle`**

Modifier le début de `_run_cycle` (~ligne 399) avant la phase power_on :

```python
def _run_cycle(self, action: str, cmd_id: str) -> None:
    cycle_start = self._clock()
    error_message = ""

    weather_desc = self._weather_provider.describe()
    logger.info(
        "cimier_event=cycle_start action=%s id=%s weather=%s",
        action, cmd_id,
        json.dumps(weather_desc, separators=(",", ":"), sort_keys=True),
    )

    # ----- Pré-vol garde-fou (avant toute alim) -----
    self._publish_phase(PHASE_PREFLIGHT, action, cmd_id, error_message="")
    decision, reason, _ = self._preflight_switches(action, cmd_id)
    if decision == "noop":
        target_state = (
            CIMIER_STATE_OPEN if action == ACTION_OPEN else CIMIER_STATE_CLOSED
        )
        self._publish_status(
            state=target_state,
            phase=PHASE_IDLE,
            last_action=action,
            command_id=cmd_id,
            error_message="",
        )
        duration_ms = int((self._clock() - cycle_start) * 1000)
        logger.info(
            "cimier_event=cycle_end action=%s id=%s duration_ms=%d result=noop reason=%s",
            action, cmd_id, duration_ms, reason,
        )
        return
    if decision in ("error", "unreachable"):
        self._publish_status(
            state=STATE_ERROR,
            phase=PHASE_IDLE,
            last_action=action,
            command_id=cmd_id,
            error_message=reason,
        )
        duration_ms = int((self._clock() - cycle_start) * 1000)
        logger.info(
            "cimier_event=cycle_end action=%s id=%s duration_ms=%d result=%s error=%s",
            action, cmd_id, duration_ms, decision, reason,
        )
        return

    # decision == "proceed" → continuer vers la cinématique
    try:
        # Phase 1 : power_on (inchangé pour l'instant)
        # ... reste de l'ancien _run_cycle inchangé ...
```

> **Note** : à cette étape on garde le reste de l'ancien `_run_cycle` (BOOT_POLL / PUSH_CONFIG / COMMAND_PICO / CYCLE_POLL). Il sera refondu en T3+. Cette étape ne change que le pré-vol. Les anciens tests qui couvrent le pipeline HTTP Pico restent verts si le pré-vol passe `proceed` (cas où `/status` répond avec `open_switch=False` et `closed_switch=False`, ce qui est l'état nominal pour les tests de cinématique existants).

> **Important** : adapter `AutoFakeHttpClient` pour que par défaut, `GET /status` retourne `{"state": "closed", "open_switch": false, "closed_switch": false}` — sinon **tous** les tests de cycle existants commenceraient à échouer en pré-vol. Examiner sa configuration actuelle et ajouter ce default si nécessaire.

- [ ] **Step 2.5 : Vérifier que les 4 tests garde-fou passent ET que les anciens tests ne régressent pas**

```bash
uv run pytest tests/test_cimier_service.py::TestPreflightGuard -v
uv run pytest tests/test_cimier_service.py -v
```

Expected: 4 nouveaux PASS + suite existante verte (hors `@pytest.mark.skip`).

- [ ] **Step 2.6 : Commit**

```bash
git add services/cimier_service.py tests/test_cimier_service.py
git commit -m "feat(cimier-bloc2): garde-fou pré-vol symétrique (spec §3.0 + §4)

T2 — Lit /status Pico W avant toute action électrique :
- open+open_switch=True → no-op (0 alim), state=open
- close+closed_switch=True → no-op symétrique, state=closed
- both_switches=True → state=error, reason=both_switches_triggered
- /status injoignable → state=error, reason=precheck_unreachable

Log cimier_event=preflight action=.. decision=.. latency_ms=..
Log cimier_event=cycle_end result=noop|error|unreachable

4 tests TestPreflightGuard. Logique cinématique HTTP Pico inchangée
(refonte T3+). AutoFakeHttpClient default /status = closed switches off."
```

---

## Task 3 : Cinématique nominale Shelly — RED

**Files:**
- Test: `tests/test_cimier_service.py` (nouvelle section `TestShellyCinematique`)

**Objectif** : écrire les tests qui décrivent l'ordre exact d'appels Shelly attendu pour un cycle ouverture et un cycle fermeture nominaux. L'implémentation arrive en T4. **À cette étape les tests doivent échouer** parce que `_run_cycle` envoie encore des POST `/open` au Pico au lieu de piloter MotorShelly.

- [ ] **Step 3.1 : Test RED — cycle ouverture nominal**

Ajouter dans `tests/test_cimier_service.py` :

```python
class TestShellyCinematique:
    """Cinématique cible (spec §3.1 / §3.2) : ordre d'appels Shelly."""

    def _build_open_then_open_switch(self):
        """Mécanisme qui démarre fermé, bascule open_switch=True après N polls."""
        from core.hardware.cimier_mechanism_sim import CimierMechanismSim
        from core.hardware.sim_motor_shelly import SimMotorShelly

        mech = CimierMechanismSim(initial_state="closed", full_travel_s=1.0)
        sim_motor = SimMotorShelly(mech)
        return mech, sim_motor

    def _make_service(self, ipc_manager, mech, sim_motor, action_target="open"):
        ps = CountingPowerSwitch()
        fake = AutoFakeHttpClient()
        # Pré-vol : pas en butée
        fake.set_status_response({
            "state": "closed" if action_target == "open" else "open",
            "open_switch": False,
            "closed_switch": False,
        })
        cfg = CimierConfig(
            enabled=True,
            host="127.0.0.1",
            port=80,
            cycle_timeout_s=5.0,
            post_off_quiet_s=0.0,
            shelly_settle_s=0.5,
            motor_shelly=MotorShellyConfig(
                host_motor="10.0.0.85",
                host_dir="10.0.0.86",
                timer_safety_sec=90.0,
            ),
        )
        clock = MockClock()
        # Patch : après le pré-vol, /status renvoie l'évolution du mécanisme
        fake.bind_mechanism(mech)
        service = CimierService(
            cimier_config=cfg,
            power_switch=ps,
            motor_shelly=sim_motor,
            http_client=fake,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=clock.sleep,
            cycle_poll_interval_s=0.05,
        )
        return service, ps, fake, clock

    def test_open_cycle_calls_in_order(
        self, ipc_manager: RecordingIpcManager
    ) -> None:
        mech, sim_motor = self._build_open_then_open_switch()
        service, ps, fake, clock = self._make_service(ipc_manager, mech, sim_motor)

        service._dispatch_command({"id": "10", "action": "open"})

        # Ordre attendu : turn_off défensif → set_direction(True) → turn_on(timer=90)
        # → ... → turn_off → power_off
        assert ps.on_count == 1, "power_switch.turn_on appelé exactement 1 fois"
        assert ps.off_count == 1, "power_switch.turn_off appelé exactement 1 fois"
        # SimMotorShelly.calls trace l'ordre
        kinds = [c[0] for c in sim_motor.calls]
        assert kinds[0] == "turn_off", "1er appel moteur = turn_off défensif"
        assert kinds[1] == "set_direction", "puis set_direction"
        assert sim_motor.calls[1][1] is True, "set_direction(open=True)"
        assert kinds[2] == "turn_on", "puis turn_on"
        assert sim_motor.calls[2][1] == 90.0, "turn_on(timer_s=90.0)"
        assert kinds[-1] == "turn_off", "dernier appel moteur = turn_off final"

    def test_close_cycle_calls_in_order(
        self, ipc_manager: RecordingIpcManager
    ) -> None:
        from core.hardware.cimier_mechanism_sim import CimierMechanismSim
        from core.hardware.sim_motor_shelly import SimMotorShelly

        mech = CimierMechanismSim(initial_state="open", full_travel_s=1.0)
        sim_motor = SimMotorShelly(mech)
        service, ps, fake, clock = self._make_service(
            ipc_manager, mech, sim_motor, action_target="close"
        )
        service._dispatch_command({"id": "11", "action": "close"})

        kinds = [c[0] for c in sim_motor.calls]
        assert kinds[0] == "turn_off"
        assert kinds[1] == "set_direction"
        assert sim_motor.calls[1][1] is False, "set_direction(open=False) pour fermeture"
        assert kinds[2] == "turn_on"
        assert kinds[-1] == "turn_off"

    def test_power_off_always_called_even_on_motor_exception(
        self, ipc_manager: RecordingIpcManager
    ) -> None:
        from core.hardware.motor_shelly import MotorShellyError

        mech, _ = self._build_open_then_open_switch()

        class CrashingMotor:
            def __init__(self):
                self.turn_off_count = 0

            def set_direction(self, open_direction): raise MotorShellyError("nope")
            def turn_on(self, timer_s=0.0): pass
            def turn_off(self): self.turn_off_count += 1

        crashing = CrashingMotor()
        service, ps, fake, clock = self._make_service(ipc_manager, mech, crashing)
        service._dispatch_command({"id": "12", "action": "open"})

        # Invariant : power_off appelé même si moteur crash
        assert ps.off_count == 1
        # Et turn_off moteur tenté en cleanup
        assert crashing.turn_off_count >= 1
```

> **Note pytest** : `AutoFakeHttpClient.bind_mechanism(mech)` est un helper à ajouter — il fait que les prochains GET `/status` renvoient un payload dérivé du `CimierMechanismSim`. À implémenter en T3.3 si la classe ne l'a pas encore.

- [ ] **Step 3.2 : Vérifier que les 3 tests échouent**

```bash
uv run pytest tests/test_cimier_service.py::TestShellyCinematique -v
```

Expected: 3 FAIL — `_run_cycle` envoie encore des POST `/open` au lieu d'appeler `motor_shelly`.

- [ ] **Step 3.3 : Pas de commit ici — RED reste local**

On enchaîne directement T4 pour passer GREEN.

---

## Task 4 : Cinématique nominale Shelly — GREEN

**Files:**
- Modify: `services/cimier_service.py` (refonte `_run_cycle`, ajout `_poll_target_switch`, suppression `_push_invert_config`, `_post_action`, `_poll_cycle_complete`, `_try_post_stop_silent`)
- Modify: `tests/test_cimier_service.py` (helper `bind_mechanism` sur `AutoFakeHttpClient`)

**Objectif** : remplacer les phases `BOOT_POLL / PUSH_CONFIG / COMMAND_PICO / CYCLE_POLL` par `SETTLE / SET_DIR / MOTOR_ON / POLL_SWITCH / MOTOR_OFF`.

- [ ] **Step 4.1 : Ajouter helper `bind_mechanism` à `AutoFakeHttpClient`**

Localiser la classe `AutoFakeHttpClient` (~ligne où elle est définie dans `tests/test_cimier_service.py`) et ajouter :

```python
def bind_mechanism(self, mechanism) -> None:
    """Branche un CimierMechanismSim : /status reflète son état temps réel."""
    self._mechanism = mechanism

# Dans la méthode request(), avant le default :
if method == "GET" and url.endswith("/status") and getattr(self, "_mechanism", None):
    m = self._mechanism
    # Advance simulé : 50 ms par appel (cohérent avec cycle_poll_interval_s)
    m.advance(0.05)
    return 200, {
        "state": "open" if m.open_switch else ("closed" if m.closed_switch else "moving"),
        "open_switch": bool(m.open_switch),
        "closed_switch": bool(m.closed_switch),
    }
```

- [ ] **Step 4.2 : Implémenter `_poll_target_switch` dans `services/cimier_service.py`**

Ajouter juste après `_preflight_switches` :

```python
def _poll_target_switch(self, action: str, cmd_id: str) -> str:
    """Boucle GET /status jusqu'à fin de course cible atteinte.

    Retourne :
      - "ok"       : switch cible atteint
      - "timeout"  : cycle_timeout_s dépassé
      - "stopped"  : commande stop reçue
      - "error"    : both_switches_triggered ou /status systématiquement KO
    """
    target_key = "open_switch" if action == ACTION_OPEN else "closed_switch"
    other_key = "closed_switch" if action == ACTION_OPEN else "open_switch"
    deadline = self._clock() + self._config.cycle_timeout_s
    url = self._base_url() + "/status"
    last_target_state = False

    while self._clock() < deadline:
        if self._stop_requested:
            return "stopped"
        stop_seen = self._check_for_stop_command()
        if stop_seen is not None:
            return "stopped"
        try:
            t0 = self._clock()
            status, payload = self._http.request("GET", url)
            latency_ms = int((self._clock() - t0) * 1000)
            if status == 200 and isinstance(payload, dict):
                target_now = bool(payload.get(target_key, False))
                other_now = bool(payload.get(other_key, False))
                if target_now and other_now:
                    logger.error(
                        "cimier_event=poll_both_switches id=%s", cmd_id
                    )
                    return "error"
                if target_now and not last_target_state:
                    logger.info(
                        "cimier_event=switch_transition switch=%s from=false to=true "
                        "elapsed_ms=%d id=%s",
                        target_key, latency_ms, cmd_id,
                    )
                    return "ok"
                last_target_state = target_now
                if self._config.verbose_logging or os.environ.get("CIMIER_DEV_MODE"):
                    logger.debug(
                        "cimier_event=poll_status id=%s open_switch=%s closed_switch=%s",
                        cmd_id,
                        str(payload.get("open_switch", False)).lower(),
                        str(payload.get("closed_switch", False)).lower(),
                    )
        except (urllib.error.URLError, OSError, ConnectionError) as exc:
            logger.debug("cimier_event=poll_exception id=%s exc=%s", cmd_id, exc)
        self._sleep(self._cycle_poll_interval_s)
    return "timeout"
```

- [ ] **Step 4.3 : Refondre `_run_cycle` (corps complet)**

Remplacer **tout** le contenu de `_run_cycle` (à partir du `try:` après le pré-vol jusqu'au `finally:` inclus). Code complet :

```python
    try:
        # Phase A : power_on
        self._publish_phase(PHASE_POWER_ON, action, cmd_id, error_message="")
        t0 = self._clock()
        try:
            self._power_switch.turn_on()
        except PowerSwitchError as exc:
            logger.error("cimier_event=power_on_failed id=%s exc=%s", cmd_id, exc)
            error_message = "power_on_failed"
            return
        logger.info(
            "cimier_event=phase phase=%s action=%s id=%s elapsed_ms=%d",
            PHASE_POWER_ON, action, cmd_id,
            int((self._clock() - cycle_start) * 1000),
        )

        # Phase B : settle (appairage WiFi des Shelly aval — 24V montant)
        self._publish_phase(PHASE_SETTLE, action, cmd_id, error_message="")
        settle = float(self._config.shelly_settle_s)
        if settle > 0:
            self._sleep(settle)

        # Phase C : turn_off moteur défensif (avant toute énergisation)
        self._publish_phase(PHASE_MOTOR_OFF, action, cmd_id, error_message="")
        self._call_motor_logged("turn_off", lambda: self.motor_shelly.turn_off())

        # Phase D : set_direction selon action
        self._publish_phase(PHASE_SET_DIR, action, cmd_id, error_message="")
        open_direction = (action == ACTION_OPEN)
        self._call_motor_logged(
            "set_direction",
            lambda: self.motor_shelly.set_direction(open_direction=open_direction),
            open=open_direction,
        )

        # Phase E : turn_on moteur (avec timer_safety hardware Shelly)
        self._publish_phase(PHASE_MOTOR_ON, action, cmd_id, error_message="")
        timer_safety = float(self._config.motor_shelly.timer_safety_sec)
        self._call_motor_logged(
            "turn_on",
            lambda: self.motor_shelly.turn_on(timer_s=timer_safety),
            timer_s=timer_safety,
        )

        # Phase F : poll target switch
        self._publish_phase(PHASE_POLL_SWITCH, action, cmd_id, error_message="")
        outcome = self._poll_target_switch(action, cmd_id)
        if outcome == "timeout":
            logger.error("cimier_event=poll_timeout id=%s", cmd_id)
            error_message = "cycle_timeout"
            return
        if outcome == "error":
            error_message = "both_switches_triggered"
            return
        if outcome == "stopped":
            error_message = ""
            return

    except Exception as exc:
        logger.exception("cimier_event=cycle_exception id=%s exc=%s", cmd_id, exc)
        error_message = "cycle_exception:" + type(exc).__name__

    finally:
        # Cleanup garanti : motor off + power off
        try:
            self.motor_shelly.turn_off()
        except Exception as exc:
            logger.error("cimier_event=motor_off_cleanup_failed id=%s exc=%s", cmd_id, exc)

        self._publish_phase(
            PHASE_POWER_OFF, action, cmd_id, error_message=error_message
        )
        try:
            self._power_switch.turn_off()
        except PowerSwitchError as exc:
            logger.error("cimier_event=power_off_failed exc=%s", exc)

        duration_ms = int((self._clock() - cycle_start) * 1000)
        result = "ok" if not error_message else (
            "timeout" if error_message == "cycle_timeout"
            else "stopped" if error_message == "" else "error"
        )
        logger.info(
            "cimier_event=cycle_end action=%s id=%s duration_ms=%d result=%s error=%s",
            action, cmd_id, duration_ms, result, error_message or "none",
        )

        # Cooldown
        self._cooldown_end_ts = self._clock() + self._config.post_off_quiet_s
        state = STATE_ERROR if (error_message and error_message != "") else STATE_COOLDOWN
        self._publish_status(
            state=state,
            phase=PHASE_COOLDOWN,
            last_action=action,
            command_id=cmd_id,
            error_message=error_message,
            remaining_quiet_s=self._config.post_off_quiet_s,
        )
```

- [ ] **Step 4.4 : Ajouter helper `_call_motor_logged`**

Ajouter dans `CimierService` (regrouper avec les autres helpers privés) :

```python
def _call_motor_logged(self, call_name: str, fn, **ctx) -> None:
    """Appelle une méthode de motor_shelly en chronométrant et journalisant.

    Le motor_shelly réel est un MotorShelly (host_motor + host_dir).
    Log INFO toujours, expose la latence ms.
    """
    host = getattr(self.motor_shelly, "host_motor", "noop")
    t0 = self._clock()
    try:
        fn()
        latency_ms = int((self._clock() - t0) * 1000)
        extras = " ".join("%s=%s" % (k, v) for k, v in ctx.items())
        logger.info(
            "cimier_event=shelly_call call=%s host=%s latency_ms=%d %s",
            call_name, host, latency_ms, extras,
        )
    except Exception as exc:
        latency_ms = int((self._clock() - t0) * 1000)
        logger.error(
            "cimier_event=shelly_call_failed call=%s host=%s latency_ms=%d exc=%s",
            call_name, host, latency_ms, exc,
        )
        raise
```

- [ ] **Step 4.5 : Supprimer le code mort**

Supprimer ces 4 méthodes (HTTP Pico /open|/close|/config — caducs) :
- `_poll_pico_ready` (lignes ~522-543)
- `_push_invert_config` (lignes ~545-555)
- `_post_action` (lignes ~557-567)
- `_poll_cycle_complete` (lignes ~569-603)
- `_try_post_stop_silent` (lignes ~605-...)

Supprimer aussi l'attribut `self._last_pico_state` (initialisation et usages).

- [ ] **Step 4.6 : Vérifier que la cinématique passe**

```bash
uv run pytest tests/test_cimier_service.py::TestShellyCinematique -v
uv run pytest tests/test_cimier_service.py::TestPreflightGuard -v
```

Expected: 3 + 4 = 7 PASS.

- [ ] **Step 4.7 : Vérifier que les anciens tests cinématique (non-skip) sont adaptés ou supprimés**

```bash
uv run pytest tests/test_cimier_service.py -v 2>&1 | grep -E "PASS|FAIL|ERROR" | head -40
```

Les tests qui dépendaient des phases BOOT_POLL / PUSH_CONFIG / COMMAND_PICO / CYCLE_POLL ou des méthodes supprimées vont **régresser**. Les supprimer (ils sont remplacés par les nouveaux Sections garde-fou + cinématique). Conserver les tests Configuration / Cooldown / Status publishing qui ne touchent pas au pipeline interne.

> **Critère d'adaptation** : si un test utilise `PHASE_BOOT_POLL` / `PHASE_PUSH_CONFIG` / `PHASE_COMMAND_PICO` / `PHASE_CYCLE_POLL` / `_post_action` / `_push_invert_config` / `_poll_cycle_complete` / `_try_post_stop_silent` → **suppression** (couvert par les nouvelles classes `TestPreflightGuard` + `TestShellyCinematique`).

- [ ] **Step 4.8 : Commit**

```bash
git add services/cimier_service.py tests/test_cimier_service.py
git commit -m "feat(cimier-bloc2): cinématique Shelly complète (spec §3.1-§3.4)

T3+T4 — _run_cycle refondu :
- Phases : preflight → power_on → settle → motor_off défensif → set_direction
  → motor_on(timer_safety) → poll_switch → motor_off → power_off → cooldown
- _poll_target_switch détecte open_switch/closed_switch via /status Pico
- _call_motor_logged chronométer + log INFO chaque appel Shelly
- Invariant 220V : power_switch.turn_off() dans finally (préservé)
- Filet hardware Shelly : turn_on(timer_s=timer_safety_sec) → toggle_after
- Suppression _post_action / _push_invert_config / _poll_cycle_complete /
  _try_post_stop_silent / _poll_pico_ready / self._last_pico_state
- AutoFakeHttpClient.bind_mechanism(mech) pour tests cycle bout-en-bout

3 tests TestShellyCinematique (open / close / power_off invariant)."
```

---

## Task 5 : Logging orchestration — affinage events

**Files:**
- Modify: `services/cimier_service.py`
- Test: `tests/test_cimier_service.py` (nouvelle section `TestOrchestrationLogging`)

**Objectif** : compléter le logging spec §7 avec les events précis et tester leur format.

- [ ] **Step 5.1 : Test RED — chaque cycle publie tous les events attendus**

```python
class TestOrchestrationLogging:
    def test_full_open_cycle_publishes_expected_events(
        self, ipc_manager, caplog
    ) -> None:
        import logging as _logging
        caplog.set_level(_logging.INFO, logger="services.cimier_service")
        from core.hardware.cimier_mechanism_sim import CimierMechanismSim
        from core.hardware.sim_motor_shelly import SimMotorShelly

        mech = CimierMechanismSim(initial_state="closed", full_travel_s=0.5)
        sim_motor = SimMotorShelly(mech)
        ps = CountingPowerSwitch()
        fake = AutoFakeHttpClient()
        fake.set_status_response({
            "state": "closed", "open_switch": False, "closed_switch": False,
        })
        fake.bind_mechanism(mech)
        cfg = CimierConfig(
            enabled=True, host="127.0.0.1", port=80,
            cycle_timeout_s=5.0, post_off_quiet_s=0.0,
            shelly_settle_s=0.0,
            motor_shelly=MotorShellyConfig(
                host_motor="10.0.0.85", host_dir="10.0.0.86", timer_safety_sec=90.0,
            ),
        )
        clock = MockClock()
        service = CimierService(
            cimier_config=cfg, power_switch=ps, motor_shelly=sim_motor,
            http_client=fake, ipc_manager=ipc_manager,
            clock=clock, sleep=clock.sleep, cycle_poll_interval_s=0.05,
        )
        service._dispatch_command({"id": "ev1", "action": "open"})

        events = [r.message for r in caplog.records if "cimier_event=" in r.message]
        # 1 cycle_start
        assert any("cimier_event=cycle_start" in m for m in events)
        # 1 preflight decision=proceed
        assert any("cimier_event=preflight" in m and "decision=proceed" in m for m in events)
        # 3 shelly_call (turn_off, set_direction, turn_on)
        shelly_calls = [m for m in events if "cimier_event=shelly_call" in m]
        assert len(shelly_calls) >= 3
        assert any("call=turn_off" in m for m in shelly_calls)
        assert any("call=set_direction" in m for m in shelly_calls)
        assert any("call=turn_on" in m and "timer_s=90.0" in m for m in shelly_calls)
        # latency_ms présent sur chaque shelly_call
        for m in shelly_calls:
            assert "latency_ms=" in m
        # switch_transition
        assert any("cimier_event=switch_transition" in m and "switch=open_switch" in m for m in events)
        # phase events
        assert any("cimier_event=phase" in m and "phase=power_on" in m for m in events)
        # cycle_end result=ok
        assert any("cimier_event=cycle_end" in m and "result=ok" in m for m in events)
```

- [ ] **Step 5.2 : Vérifier que le test passe**

```bash
uv run pytest tests/test_cimier_service.py::TestOrchestrationLogging -v
```

Expected: PASS (la majorité des events sont déjà émis depuis T2/T4 ; ce test verrouille leur présence). En cas d'absence d'un event, l'ajouter dans le code aux endroits manquants.

- [ ] **Step 5.3 : Commit**

```bash
git add tests/test_cimier_service.py services/cimier_service.py
git commit -m "test(cimier-bloc2): verrouille format events orchestration (spec §7)

T5 — TestOrchestrationLogging valide chaque cycle :
- cycle_start avec weather
- preflight avec decision
- 3+ shelly_call chronométrés (turn_off / set_direction / turn_on(timer))
- switch_transition à la bascule fin de course
- phase events à chaque transition
- cycle_end avec result=ok|timeout|error|noop|stopped

Reconstruction complète d'une timeline cycle depuis logs/cimier_service.log
(debug à distance 800 km, contrainte centrale du chantier)."
```

---

## Task 6 : Mode verbeux dev — `CIMIER_DEV_MODE` + `verbose_logging`

**Files:**
- Modify: `services/cimier_service.py` (consommation effective des 2 flags)
- Test: `tests/test_cimier_service.py` (nouvelle section `TestVerboseLogging`)

**Objectif** : câbler les 2 flags ajoutés en Bloc 1 (commit `50f52d8`) qui n'ont aucun consommateur. En verbeux, chaque itération de polling est loguée en DEBUG ; sinon seule la transition de switch est loguée en INFO.

- [ ] **Step 6.1 : Test RED — `verbose_logging=True` produit des events `poll_status` par itération**

```python
class TestVerboseLogging:
    def test_verbose_logging_emits_poll_status_per_iteration(
        self, ipc_manager, caplog
    ) -> None:
        import logging as _logging
        caplog.set_level(_logging.DEBUG, logger="services.cimier_service")
        from core.hardware.cimier_mechanism_sim import CimierMechanismSim
        from core.hardware.sim_motor_shelly import SimMotorShelly

        mech = CimierMechanismSim(initial_state="closed", full_travel_s=0.3)
        sim_motor = SimMotorShelly(mech)
        ps = CountingPowerSwitch()
        fake = AutoFakeHttpClient()
        fake.set_status_response({
            "state": "closed", "open_switch": False, "closed_switch": False,
        })
        fake.bind_mechanism(mech)
        cfg = CimierConfig(
            enabled=True, host="127.0.0.1", port=80,
            verbose_logging=True,
            cycle_timeout_s=5.0, post_off_quiet_s=0.0, shelly_settle_s=0.0,
            motor_shelly=MotorShellyConfig(host_motor="x", host_dir="y", timer_safety_sec=90.0),
        )
        clock = MockClock()
        service = CimierService(
            cimier_config=cfg, power_switch=ps, motor_shelly=sim_motor,
            http_client=fake, ipc_manager=ipc_manager,
            clock=clock, sleep=clock.sleep, cycle_poll_interval_s=0.05,
        )
        service._dispatch_command({"id": "ev2", "action": "open"})

        debug_polls = [
            r.message for r in caplog.records
            if "cimier_event=poll_status" in r.message
        ]
        assert len(debug_polls) >= 2, "verbose : au moins 2 polls DEBUG"

    def test_non_verbose_does_not_emit_poll_status(
        self, ipc_manager, caplog
    ) -> None:
        import logging as _logging
        caplog.set_level(_logging.DEBUG, logger="services.cimier_service")
        # Idem que ci-dessus mais verbose_logging=False (default)
        from core.hardware.cimier_mechanism_sim import CimierMechanismSim
        from core.hardware.sim_motor_shelly import SimMotorShelly

        mech = CimierMechanismSim(initial_state="closed", full_travel_s=0.3)
        sim_motor = SimMotorShelly(mech)
        ps = CountingPowerSwitch()
        fake = AutoFakeHttpClient()
        fake.set_status_response({
            "state": "closed", "open_switch": False, "closed_switch": False,
        })
        fake.bind_mechanism(mech)
        cfg = CimierConfig(
            enabled=True, host="127.0.0.1", port=80,
            verbose_logging=False,
            cycle_timeout_s=5.0, post_off_quiet_s=0.0, shelly_settle_s=0.0,
            motor_shelly=MotorShellyConfig(host_motor="x", host_dir="y", timer_safety_sec=90.0),
        )
        clock = MockClock()
        service = CimierService(
            cimier_config=cfg, power_switch=ps, motor_shelly=sim_motor,
            http_client=fake, ipc_manager=ipc_manager,
            clock=clock, sleep=clock.sleep, cycle_poll_interval_s=0.05,
        )
        # S'assurer que CIMIER_DEV_MODE n'est pas set pour ce test
        import os
        os.environ.pop("CIMIER_DEV_MODE", None)
        service._dispatch_command({"id": "ev3", "action": "open"})

        debug_polls = [
            r.message for r in caplog.records
            if "cimier_event=poll_status" in r.message
        ]
        assert len(debug_polls) == 0, "non-verbose : pas de poll_status"
```

- [ ] **Step 6.2 : Vérifier que le test passe (le code de T4 a déjà branché la condition `verbose_logging or CIMIER_DEV_MODE`)**

```bash
uv run pytest tests/test_cimier_service.py::TestVerboseLogging -v
```

Expected: 2 PASS si le code de T4.2 a bien posé le `if self._config.verbose_logging or os.environ.get("CIMIER_DEV_MODE"):` autour du `logger.debug("cimier_event=poll_status ...")`. Sinon ajuster.

- [ ] **Step 6.3 : Commit**

```bash
git add services/cimier_service.py tests/test_cimier_service.py
git commit -m "feat(cimier-bloc2): consommation verbose_logging + CIMIER_DEV_MODE

T6 — Câble les 2 flags livrés Bloc 1 (commit 50f52d8) :
- verbose_logging=True OU CIMIER_DEV_MODE=1 → debug par itération polling
- sinon : seule transition switch loguée en INFO (mode prod)

Aligne logging dev sur l'infra existante (start_dev.sh exporte déjà
CIMIER_DEV_MODE=1, cf. v6.3.2). Pas de nouveau système.

2 tests TestVerboseLogging."
```

---

## Task 7 : Refonte des 8 tests `@pytest.mark.skip` (`TestFullCycleViaSimulator` + `test_cycle_logs_weather_on_start`)

**Files:**
- Modify: `tests/test_cimier_service.py` (lignes ~370 et ~977)

**Objectif** : déskip et adapter ces tests à la nouvelle archi. La fixture `simulator` reçoit désormais juste `port=...` + `boot_delay_s=...` (le `CimierSimulator` Bloc 1 ne prend plus `steps_per_cycle` / `tick_period_ms` / `cycle_timeout_s`).

- [ ] **Step 7.1 : Refonte fixture `simulator`**

Localiser la fixture (~ligne 212) et remplacer par :

```python
@pytest.fixture
def simulator():
    """CimierSimulator capteur-only sur port libre, boot rapide."""
    from core.hardware.cimier_mechanism_sim import CimierMechanismSim
    port = _find_free_port()
    mechanism = CimierMechanismSim(initial_state="closed", full_travel_s=0.5)
    sim = CimierSimulator(
        port=port,
        boot_delay_s=0.05,
        mechanism=mechanism,
    )
    sim.start()
    assert sim.wait_ready(timeout=3.0), "simulator did not boot"
    yield sim
    sim.stop()
```

> **À vérifier au passage** : la signature actuelle de `CimierSimulator` (élaguée Bloc 1) — si elle ne prend pas `mechanism=`, adapter (la spec §8 indique `CimierSimulator` lit les switches depuis le mécanisme, donc le param `mechanism=` doit exister Bloc 1). Sinon mettre à jour `services/cimier_simulator.py` minimalement pour accepter ce param.

- [ ] **Step 7.2 : Refonte `service_with_simulator`**

```python
@pytest.fixture
def service_with_simulator(
    simulator: CimierSimulator,
    ipc_manager: RecordingIpcManager,
):
    from core.hardware.sim_motor_shelly import SimMotorShelly
    sim_motor = SimMotorShelly(simulator.mechanism)
    cfg = CimierConfig(
        enabled=True,
        host="127.0.0.1",
        port=simulator.port,
        cycle_timeout_s=5.0,
        post_off_quiet_s=0.1,
        shelly_settle_s=0.0,
        power_switch=PowerSwitchConfig(type="noop"),
        motor_shelly=MotorShellyConfig(
            host_motor="10.0.0.85", host_dir="10.0.0.86", timer_safety_sec=90.0,
        ),
    )
    ps = CountingPowerSwitch()
    service = CimierService(
        cimier_config=cfg,
        power_switch=ps,
        motor_shelly=sim_motor,
        http_client=HttpClient(timeout_s=2.0),
        ipc_manager=ipc_manager,
        cycle_poll_interval_s=0.05,
    )
    return service, ps, simulator, sim_motor
```

- [ ] **Step 7.3 : Réécrire `TestFullCycleViaSimulator` (7 tests)**

Supprimer `@pytest.mark.skip` ligne ~370 et réécrire les tests pour la cinématique Shelly. La signature du tuple change (4 éléments). Liste des cas à couvrir (tirés du périmètre original) :

1. `test_open_cycle_completes_state_open` : init closed → cycle open → switch open passe True → state=`open`
2. `test_close_cycle_completes_state_closed` : init open → cycle close → switch closed passe True → state=`closed`
3. `test_open_when_already_open_no_op_via_simulator` : init open → cycle open → no-op preflight, 0 appel power_switch
4. `test_close_when_already_closed_no_op_via_simulator` : init closed → cycle close → no-op preflight
5. `test_cycle_timeout_publishes_error` : `full_travel_s` très long + `cycle_timeout_s` court → state=`error`, error=`cycle_timeout`
6. `test_stop_command_during_polling_aborts_cycle` : pendant le poll, écrire un cmd_stop → cycle s'arrête, motor.turn_off + power_off appelés
7. `test_both_switches_via_simulator_blocks` : `CimierMechanismSim(force_both_switches=True)` → preflight error

Implémentation à coller (extrait représentatif, à compléter pour les 7) :

```python
class TestFullCycleViaSimulator:
    def test_open_cycle_completes_state_open(
        self, service_with_simulator
    ) -> None:
        service, ps, sim, sim_motor = service_with_simulator
        # initial state closed (par défaut fixture)
        service._dispatch_command({"id": "s1", "action": "open"})

        # Le mécanisme doit avoir atteint open_switch=True
        assert sim.mechanism.open_switch is True
        # power_on + power_off appelés une fois
        assert ps.on_count == 1 and ps.off_count == 1
        # Ordre Shelly : turn_off / set_direction(True) / turn_on / ... / turn_off
        kinds = [c[0] for c in sim_motor.calls]
        assert kinds[0] == "turn_off"
        assert kinds[1] == "set_direction" and sim_motor.calls[1][1] is True
        assert kinds[2] == "turn_on"
        assert kinds[-1] == "turn_off"
```

Compléter les 6 autres sur le même modèle. Pour `test_cycle_timeout_publishes_error`, créer un mécanisme avec `full_travel_s=999.0` (très lent) et un `CimierConfig(cycle_timeout_s=0.1)` — le polling dépasse, error_message=`cycle_timeout`.

Pour `test_stop_command_during_polling_aborts_cycle`, utiliser `ipc_manager.next_command_payload = {"action": "stop"}` (à adapter au mécanisme du fake IPC manager existant).

- [ ] **Step 7.4 : Réécrire `TestWeatherProviderWiring::test_cycle_logs_weather_on_start` (1 test)**

Localiser ligne ~977, supprimer `@pytest.mark.skip`. Le test vérifie que `cimier_event=cycle_start` log un `weather=` JSON depuis le `WeatherProvider` injecté. La structure du test reste valide ; juste s'assurer que la fixture passe maintenant un `motor_shelly` (SimMotorShelly) — sinon il reste sur Noop, ce qui est OK pour ce test précis.

- [ ] **Step 7.5 : Vérifier que tous les ex-skip passent**

```bash
uv run pytest tests/test_cimier_service.py::TestFullCycleViaSimulator -v
uv run pytest tests/test_cimier_service.py::TestWeatherProviderWiring::test_cycle_logs_weather_on_start -v
```

Expected: 7 + 1 = 8 PASS (les 8 ex-skip).

- [ ] **Step 7.6 : Commit**

```bash
git add tests/test_cimier_service.py
git commit -m "test(cimier-bloc2): refonte 8 tests skip Bloc 1 → cinématique Shelly

T7 — Backlog Bloc 2 item 1 :
- Fixture simulator : CimierSimulator(mechanism=...) + SimMotorShelly
- TestFullCycleViaSimulator : 7 tests réécrits (open/close, no-op, timeout,
  stop, both_switches via simulator) sur la nouvelle archi
- TestWeatherProviderWiring::test_cycle_logs_weather_on_start déskippé

Suite cimier_service : 0 skip restant."
```

---

## Task 8 : Lint, vérification finale, merge local

**Files:**
- Lint sur tous les fichiers modifiés

- [ ] **Step 8.1 : Format + lint**

```bash
uv run ruff format core/hardware/ services/cimier_service.py tests/test_cimier_service.py
uv run ruff check core/hardware/ services/cimier_service.py tests/test_cimier_service.py
```

Expected: 0 erreur.

- [ ] **Step 8.2 : Suite ciblée verte**

```bash
uv run pytest \
    tests/test_cimier_service.py \
    tests/test_motor_shelly.py \
    tests/test_cimier_controller.py \
    tests/test_cimier_simulator.py \
    tests/test_config_loader.py \
    tests/test_power_switch.py \
    -v
```

Expected: 100% PASS, **0 skip** (les 8 skip Bloc 1 ont été réécrits en T7).

- [ ] **Step 8.3 : Suite complète (vérification non-régression hors cimier)**

```bash
uv run pytest -q 2>&1 | tail -10
```

Expected: PASS count ≥ baseline Bloc 1 (1111 passed) **+ delta tests Bloc 2 ajoutés - 8 skip levés** ; 0 failed ; 0 ou très peu de skip restants.

- [ ] **Step 8.4 : Si lint ou tests ont nécessité une correction, commit final**

```bash
git add -A
git commit -m "chore(cimier-bloc2): lint + ajustements finaux

T8 — Format ruff + corrections lint + vérif non-régression suite globale.
Pas de bump pyproject.toml (chantier cimier en cours, cf. décision JP 23/05).
Pas de push (Bloc 1+2 restent locaux jusqu'à fin chantier)."
```

- [ ] **Step 8.5 : Merge fast-forward dans `main` local (sans push)**

```bash
git checkout main
git merge --ff-only feat/bloc2-cinematique-cimier
git branch -d feat/bloc2-cinematique-cimier
git log --oneline main | head -15  # vérification cosmétique
```

Expected: branche cimier-bloc2 absorbée dans `main` local sans merge commit, comme Bloc 1.

> **NE PAS** lancer `git push origin main`. La décision 23/05 est de **n'envoyer le tout que quand le chantier cimier est complètement bouclé** (Bloc 2 + items backlog 2/3 le cas échéant + validation terrain Serge).

---

## Hors scope Bloc 2 (backlog item 3 — différé)

- Doc/firmware on-device : `firmware/cimier/README.md` périmé, `firmware/cimier/ramp.py` orphelin, commentaires `main.py` WDT 200 → 8000, scripts `firmware/cimier/tests/*.sh` (non committés) à mettre à jour.
- Bump `pyproject.toml` 6.4.0 → 6.5.0.
- Validation terrain (test sous tension à valider par Serge) :
  - `open_dir_state` (calibration true/false)
  - `default_state=ON` Shelly MOT côté UI Shelly
  - Confirmation alim permanente Pico W (`/status` répond avec 24 V coupé)
  - Mesure latence stop Shelly réelle
  - Renseignement des IPs DHCP de `host_motor` / `host_dir` dans `data/config.json`
- Push `origin/main` (en une seule fois, fin de chantier).

---

## Critères de succès Bloc 2

- 4 tests garde-fou pré-vol verts (open/close/both/unreachable)
- 3 tests cinématique nominale verts (open/close/power_off invariant)
- 1 test logging verrouille format events
- 2 tests verbose_logging verrouille comportement DEBUG
- 8 ex-skip Bloc 1 réécrits verts (`TestFullCycleViaSimulator` × 7 + `test_cycle_logs_weather_on_start`)
- Suite ciblée 0 fail / 0 skip restant côté cimier
- Suite globale ≥ baseline Bloc 1 sans régression
- `ruff format` + `ruff check` propres sur fichiers touchés
- 0 IP en dur dans le code (tout via `data/config.json → cimier.motor_shelly`)
- 7-8 commits atomiques sur branche `feat/bloc2-cinematique-cimier`, mergés fast-forward dans `main` local, **non poussés**
- Aucun bump `pyproject.toml` (cf. décision 23/05)
