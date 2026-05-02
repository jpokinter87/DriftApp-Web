"""Tests pour services/cimier_service.py et services/cimier_ipc_manager.py.

Couvre :
  - Configuration & instantiation (factory power_switch, enabled flag)
  - Cycle complet bout-en-bout via CimierSimulator + NoopPowerSwitch
  - Anti-bounce post_off_quiet_s (FakeHttpClient + MockClock)
  - Erreurs et timeouts (boot, cycle, http, pico_error)
  - Commande "stop" (pendant cycle, idle, pendant boot)
  - IPC manager : dédup, écriture atomique, création fichier

v6.0 Phase 1 sub-plan 02.
"""

from __future__ import annotations

import json
import re
import socket
import time
import urllib.error
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

from core.config.config_loader import CimierConfig, PowerSwitchConfig
from core.hardware.cimier_simulator import CimierSimulator
from core.hardware.power_switch import (
    NoopPowerSwitch,
    PowerSwitchError,
    ShellyPowerSwitch,
)
from services.cimier_ipc_manager import CimierIpcManager
from services.cimier_service import (
    ACTION_CLOSE,
    ACTION_OPEN,
    ACTION_STOP,
    HttpClient,
    PHASE_BOOT_POLL,
    PHASE_COMMAND_PICO,
    PHASE_COOLDOWN,
    PHASE_CYCLE_POLL,
    PHASE_POWER_OFF,
    PHASE_POWER_ON,
    STATE_COOLDOWN,
    STATE_DISABLED,
    STATE_ERROR,
    STATE_IDLE,
    CimierService,
    make_power_switch,
)


# ======================================================================
# Helpers / fakes
# ======================================================================

def _find_free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class CountingPowerSwitch:
    """Power switch qui compte les calls turn_on/turn_off (fake hardware)."""

    def __init__(self) -> None:
        self.on_count = 0
        self.off_count = 0
        self._state = False

    def turn_on(self) -> None:
        self.on_count += 1
        self._state = True

    def turn_off(self) -> None:
        self.off_count += 1
        self._state = False

    def is_on(self) -> bool:
        return self._state


class FailingPowerSwitch(CountingPowerSwitch):
    """Power switch qui lève PowerSwitchError sur turn_on."""

    def turn_on(self) -> None:
        self.on_count += 1
        raise PowerSwitchError("simulated turn_on failure")


class AutoFakeHttpClient:
    """FakeHttpClient minimaliste qui simule un Pico fidèle au contrat REST.

    Maintient un état (open/closed) progressé immédiatement par les POST.
    Permet d'override le comportement par URL via `responses_by_url` (file
    de réponses consommée dans l'ordre, ou Exception levée).
    """

    def __init__(self, initial_state: str = "closed"):
        self.calls: List[Tuple[str, str, Optional[Dict[str, Any]]]] = []
        self.state = initial_state
        self.invert = False
        self.responses_by_url: Dict[str, List[Any]] = {}

    def queue(self, url_suffix: str, status: int, payload: Dict[str, Any]) -> None:
        self.responses_by_url.setdefault(url_suffix, []).append((status, payload))

    def queue_exception(self, url_suffix: str, exc: BaseException) -> None:
        self.responses_by_url.setdefault(url_suffix, []).append(exc)

    def request(
        self,
        method: str,
        url: str,
        body: Optional[Dict[str, Any]] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        self.calls.append((method, url, body))

        for suffix, queue in self.responses_by_url.items():
            if url.endswith(suffix) and queue:
                resp = queue.pop(0)
                if isinstance(resp, BaseException):
                    raise resp
                return resp

        if url.endswith("/status"):
            return 200, {"state": self.state}
        if url.endswith("/open"):
            self.state = "open"
            return 200, {"state": "open"}
        if url.endswith("/close"):
            self.state = "closed"
            return 200, {"state": "closed"}
        if url.endswith("/stop"):
            return 200, {"state": self.state}
        if url.endswith("/config"):
            if isinstance(body, dict) and "invert_direction" in body:
                self.invert = bool(body["invert_direction"])
            return 200, {}
        return 404, {}

    def count_calls(self, url_suffix: str, method: Optional[str] = None) -> int:
        return sum(
            1
            for (m, u, _b) in self.calls
            if u.endswith(url_suffix) and (method is None or m == method)
        )


class MockClock:
    """Horloge mockée + sleep qui avance le clock virtuel (pas de wall-clock)."""

    def __init__(self, start: float = 0.0):
        self.t = float(start)

    def __call__(self) -> float:
        return self.t

    def advance(self, delta: float) -> None:
        self.t += float(delta)

    def sleep(self, seconds: float) -> None:
        self.t += float(seconds)


class RecordingIpcManager(CimierIpcManager):
    """IPC manager qui enregistre l'historique des status publiés."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.history: List[Dict[str, Any]] = []

    def write_status(self, status: Dict[str, Any]) -> None:  # type: ignore[override]
        self.history.append(dict(status))
        super().write_status(status)


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def tmp_ipc(tmp_path: Path) -> Tuple[Path, Path]:
    return tmp_path / "cimier_command.json", tmp_path / "cimier_status.json"


@pytest.fixture
def ipc_manager(tmp_ipc: Tuple[Path, Path]) -> RecordingIpcManager:
    cmd_file, status_file = tmp_ipc
    return RecordingIpcManager(command_file=cmd_file, status_file=status_file)


@pytest.fixture
def cimier_config_default() -> CimierConfig:
    """Config par défaut pour les tests : enabled=True, host=127.0.0.1, timeouts courts."""
    return CimierConfig(
        enabled=True,
        host="127.0.0.1",
        port=80,
        invert_direction=False,
        cycle_timeout_s=2.0,
        boot_poll_timeout_s=2.0,
        post_off_quiet_s=10.0,
        power_switch=PowerSwitchConfig(type="noop"),
    )


@pytest.fixture
def simulator():
    """CimierSimulator sur port libre, boot rapide (50ms), cycle court."""
    port = _find_free_port()
    sim = CimierSimulator(
        port=port,
        boot_delay_s=0.05,
        steps_per_cycle=20,
        tick_period_ms=5,
        cycle_timeout_s=2.0,
    )
    sim.start()
    assert sim.wait_ready(timeout=3.0), "simulator did not boot"
    yield sim
    sim.stop()


@pytest.fixture
def service_with_simulator(
    simulator: CimierSimulator,
    ipc_manager: RecordingIpcManager,
) -> Tuple[CimierService, CountingPowerSwitch, CimierSimulator]:
    """Service connecté au simulator HTTP réel."""
    cfg = CimierConfig(
        enabled=True,
        host="127.0.0.1",
        port=simulator.port,
        invert_direction=False,
        cycle_timeout_s=2.0,
        boot_poll_timeout_s=2.0,
        post_off_quiet_s=0.1,
        power_switch=PowerSwitchConfig(type="noop"),
    )
    ps = CountingPowerSwitch()
    service = CimierService(
        cimier_config=cfg,
        power_switch=ps,
        http_client=HttpClient(timeout_s=2.0),
        ipc_manager=ipc_manager,
        boot_poll_interval_s=0.05,
        cycle_poll_interval_s=0.02,
    )
    return service, ps, simulator


@pytest.fixture
def service_with_fake_http(
    cimier_config_default: CimierConfig,
    ipc_manager: RecordingIpcManager,
) -> Tuple[CimierService, CountingPowerSwitch, AutoFakeHttpClient, MockClock]:
    """Service avec FakeHttpClient + MockClock — déterministe, pas de wall-clock."""
    ps = CountingPowerSwitch()
    fake = AutoFakeHttpClient()
    clock = MockClock()
    service = CimierService(
        cimier_config=cimier_config_default,
        power_switch=ps,
        http_client=fake,
        ipc_manager=ipc_manager,
        clock=clock,
        sleep=clock.sleep,
        boot_poll_interval_s=0.05,
        cycle_poll_interval_s=0.05,
        run_loop_interval_s=0.05,
    )
    return service, ps, fake, clock


# ======================================================================
# Section 1 : Configuration & instantiation
# ======================================================================

class TestConfigurationAndInstantiation:
    def test_service_disabled_when_cimier_enabled_false(
        self, ipc_manager: RecordingIpcManager
    ) -> None:
        cfg = CimierConfig(enabled=False, host="127.0.0.1")
        ps = CountingPowerSwitch()
        service = CimierService(
            cimier_config=cfg, power_switch=ps, ipc_manager=ipc_manager
        )
        service.run_forever()
        assert ps.on_count == 0
        assert ps.off_count == 0
        # Status final = disabled
        last = ipc_manager.history[-1]
        assert last["state"] == STATE_DISABLED

    def test_make_power_switch_factory_noop(self) -> None:
        sw = make_power_switch(PowerSwitchConfig(type="noop"))
        assert isinstance(sw, NoopPowerSwitch)

    def test_make_power_switch_factory_shelly_gen2(self) -> None:
        sw = make_power_switch(
            PowerSwitchConfig(type="shelly_gen2", host="10.0.0.1", switch_id=0)
        )
        assert isinstance(sw, ShellyPowerSwitch)
        assert sw.api == "rpc"
        assert sw.host == "10.0.0.1"

    def test_make_power_switch_factory_shelly_gen1(self) -> None:
        sw = make_power_switch(
            PowerSwitchConfig(type="shelly_gen1", host="10.0.0.2")
        )
        assert isinstance(sw, ShellyPowerSwitch)
        assert sw.api == "legacy"

    def test_make_power_switch_factory_unknown_type(self) -> None:
        with pytest.raises(ValueError):
            make_power_switch(PowerSwitchConfig(type="totally_bogus"))

    def test_make_power_switch_shelly_requires_host(self) -> None:
        with pytest.raises(ValueError):
            make_power_switch(PowerSwitchConfig(type="shelly_gen2", host=""))

    def test_service_constructor_accepts_injected_clock_and_sleep(
        self,
        cimier_config_default: CimierConfig,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        clock = MockClock(start=42.0)
        sleeps: List[float] = []
        service = CimierService(
            cimier_config=cimier_config_default,
            power_switch=NoopPowerSwitch(),
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=sleeps.append,
        )
        # Le constructeur publie un status initial → utilise le clock injecté.
        assert ipc_manager.history[-1]["last_action_ts"] == 42.0
        assert isinstance(service, CimierService)

    def test_run_forever_exits_on_request_stop(
        self,
        cimier_config_default: CimierConfig,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        ps = CountingPowerSwitch()
        clock = MockClock()
        service = CimierService(
            cimier_config=cimier_config_default,
            power_switch=ps,
            http_client=AutoFakeHttpClient(),
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=clock.sleep,
            run_loop_interval_s=0.01,
        )
        # request_stop avant run_forever → la boucle quitte au premier tick.
        service.request_stop()
        service.run_forever()
        assert ps.on_count == 0


# ======================================================================
# Section 2 : Cycle complet via simulator
# ======================================================================

class TestFullCycleViaSimulator:
    def test_open_cycle_full_pipeline(
        self,
        service_with_simulator: Tuple[CimierService, CountingPowerSwitch, CimierSimulator],
        ipc_manager: RecordingIpcManager,
    ) -> None:
        service, ps, simulator = service_with_simulator
        ipc_manager.write_command({"id": "cmd-open-1", "action": "open"})
        service.tick()
        assert ps.on_count == 1
        assert ps.off_count == 1
        assert simulator.controller.state == "open"
        # Status final = cooldown (cycle vient de finir)
        last = ipc_manager.history[-1]
        assert last["state"] in (STATE_COOLDOWN, STATE_IDLE)
        assert last["last_action"] == ACTION_OPEN
        assert last["command_id"] == "cmd-open-1"
        assert last["error_message"] == ""

    def test_close_cycle_full_pipeline(
        self,
        service_with_simulator: Tuple[CimierService, CountingPowerSwitch, CimierSimulator],
        ipc_manager: RecordingIpcManager,
    ) -> None:
        service, ps, simulator = service_with_simulator
        # Forcer position open au boot.
        simulator.stop()
        simulator._initial_position = simulator._steps_per_cycle
        simulator.start()
        assert simulator.wait_ready(timeout=2.0)

        ipc_manager.write_command({"id": "cmd-close-1", "action": "close"})
        service.tick()
        assert ps.on_count == 1
        assert ps.off_count == 1
        assert simulator.controller.state == "closed"

    def test_invert_not_pushed_when_default(
        self,
        service_with_simulator: Tuple[CimierService, CountingPowerSwitch, CimierSimulator],
        ipc_manager: RecordingIpcManager,
    ) -> None:
        service, _, simulator = service_with_simulator
        # invert_direction défaut = False → pas de POST /config attendu.
        ipc_manager.write_command({"id": "cmd-1", "action": "open"})
        service.tick()
        assert simulator.controller.invert_direction is False

    def test_invert_pushed_when_true(
        self,
        simulator: CimierSimulator,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        cfg = CimierConfig(
            enabled=True,
            host="127.0.0.1",
            port=simulator.port,
            invert_direction=True,
            cycle_timeout_s=2.0,
            boot_poll_timeout_s=2.0,
            post_off_quiet_s=0.05,
            power_switch=PowerSwitchConfig(type="noop"),
        )
        ps = CountingPowerSwitch()
        service = CimierService(
            cimier_config=cfg,
            power_switch=ps,
            http_client=HttpClient(timeout_s=2.0),
            ipc_manager=ipc_manager,
            boot_poll_interval_s=0.05,
            cycle_poll_interval_s=0.02,
        )
        ipc_manager.write_command({"id": "cmd-1", "action": "open"})
        service.tick()
        # Le simulateur a reçu POST /config → invert mémorisée.
        assert simulator.controller.invert_direction is True

    def test_invert_re_pushed_after_reset_boot(
        self,
        simulator: CimierSimulator,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        cfg = CimierConfig(
            enabled=True,
            host="127.0.0.1",
            port=simulator.port,
            invert_direction=True,
            cycle_timeout_s=2.0,
            boot_poll_timeout_s=2.0,
            post_off_quiet_s=0.05,
            power_switch=PowerSwitchConfig(type="noop"),
        )
        ps = CountingPowerSwitch()
        service = CimierService(
            cimier_config=cfg,
            power_switch=ps,
            http_client=HttpClient(timeout_s=2.0),
            ipc_manager=ipc_manager,
            boot_poll_interval_s=0.05,
            cycle_poll_interval_s=0.02,
        )
        # Cycle 1
        ipc_manager.write_command({"id": "cycle-1", "action": "open"})
        service.tick()
        assert simulator.controller.invert_direction is True

        # reset_boot simule la coupure Shelly → Pico oublie l'invert.
        simulator.reset_boot()
        assert simulator.wait_ready(timeout=2.0)
        assert simulator.controller.invert_direction is False  # perdu au reboot

        # Cycle 2 — le service doit re-pousser l'invert.
        # Avancer après cooldown : on attend 0.1s qui couvre les 0.05s post_off_quiet_s.
        time.sleep(0.15)
        ipc_manager.write_command({"id": "cycle-2", "action": "close"})
        service.tick()  # consomme cooldown s'il reste
        # Si encore en cooldown, faire un autre tick après attente
        if not simulator.controller.invert_direction:
            time.sleep(0.1)
            service.tick()
        assert simulator.controller.invert_direction is True

    def test_command_id_dedup(
        self,
        service_with_simulator: Tuple[CimierService, CountingPowerSwitch, CimierSimulator],
        ipc_manager: RecordingIpcManager,
    ) -> None:
        service, ps, _ = service_with_simulator
        # Même id soumis 2x → 1 seul cycle exécuté.
        ipc_manager.write_command({"id": "cmd-x", "action": "open"})
        service.tick()
        assert ps.on_count == 1
        # Re-soumettre la même commande (même id)
        ipc_manager.write_command({"id": "cmd-x", "action": "open"})
        # Après cooldown
        time.sleep(0.15)
        service.tick()
        assert ps.on_count == 1  # pas de 2e cycle

    def test_status_published_each_phase_transition(
        self,
        service_with_simulator: Tuple[CimierService, CountingPowerSwitch, CimierSimulator],
        ipc_manager: RecordingIpcManager,
    ) -> None:
        service, _, _ = service_with_simulator
        ipc_manager.history.clear()
        ipc_manager.write_command({"id": "phase-test", "action": "open"})
        service.tick()
        phases_seen = [h["phase"] for h in ipc_manager.history]
        # Au moins ces phases doivent apparaître pendant le cycle (invert=False
        # → push_config absent).
        for required in (
            PHASE_POWER_ON,
            PHASE_BOOT_POLL,
            PHASE_COMMAND_PICO,
            PHASE_CYCLE_POLL,
            PHASE_POWER_OFF,
            PHASE_COOLDOWN,
        ):
            assert required in phases_seen, (required, phases_seen)


# ======================================================================
# Section 3 : Anti-bounce (cooldown post_off_quiet_s)
# ======================================================================

class TestAntiBounceCooldown:
    def test_cooldown_window_blocks_new_command(
        self,
        service_with_fake_http: Tuple[CimierService, CountingPowerSwitch, AutoFakeHttpClient, MockClock],
        ipc_manager: RecordingIpcManager,
    ) -> None:
        service, ps, _fake, _clock = service_with_fake_http

        # Cycle 1
        ipc_manager.write_command({"id": "c1", "action": "open"})
        service.tick()
        assert ps.on_count == 1
        assert ps.off_count == 1

        # Nouvelle commande pendant cooldown
        ipc_manager.write_command({"id": "c2", "action": "close"})
        service.tick()
        # Pas de 2e turn_on pendant la fenêtre.
        assert ps.on_count == 1
        last = ipc_manager.history[-1]
        assert last["state"] == STATE_COOLDOWN
        assert "remaining_quiet_s" in last
        assert last["remaining_quiet_s"] > 0

    def test_cooldown_releases_after_quiet_window(
        self,
        service_with_fake_http: Tuple[CimierService, CountingPowerSwitch, AutoFakeHttpClient, MockClock],
        ipc_manager: RecordingIpcManager,
    ) -> None:
        service, ps, _fake, clock = service_with_fake_http

        ipc_manager.write_command({"id": "c1", "action": "open"})
        service.tick()
        assert ps.on_count == 1

        # Avancer la clock au-delà de post_off_quiet_s (10s) → cooldown libéré.
        clock.advance(15.0)
        ipc_manager.write_command({"id": "c2", "action": "close"})
        service.tick()
        assert ps.on_count == 2
        assert ps.off_count == 2

    def test_cooldown_preserves_command_for_later_dispatch(
        self,
        service_with_fake_http: Tuple[CimierService, CountingPowerSwitch, AutoFakeHttpClient, MockClock],
        ipc_manager: RecordingIpcManager,
    ) -> None:
        service, ps, _fake, clock = service_with_fake_http

        ipc_manager.write_command({"id": "c1", "action": "open"})
        service.tick()
        assert ps.on_count == 1

        # Commande arrivée pendant cooldown
        ipc_manager.write_command({"id": "c2", "action": "close"})
        service.tick()
        assert ps.on_count == 1  # pas exécutée

        # Avancer après cooldown — la commande pending doit être dispatched.
        clock.advance(15.0)
        service.tick()
        assert ps.on_count == 2
        last = ipc_manager.history[-1]
        assert last["last_action"] == ACTION_CLOSE
        assert last["command_id"] == "c2"


# ======================================================================
# Section 4 : Erreurs & timeouts
# ======================================================================

class TestErrorsAndTimeouts:
    def test_boot_timeout_sets_error_state(
        self,
        cimier_config_default: CimierConfig,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        # FakeHttp qui lève toujours une URLError sur /status → timeout boot.
        fake = AutoFakeHttpClient()
        # Saturer la queue avec 100 exceptions sur /status pour couvrir tout le timeout.
        for _ in range(100):
            fake.queue_exception("/status", urllib.error.URLError("connection refused"))

        cfg = CimierConfig(
            enabled=True,
            host="127.0.0.1",
            port=80,
            cycle_timeout_s=2.0,
            boot_poll_timeout_s=0.2,  # court
            post_off_quiet_s=0.0,
            power_switch=PowerSwitchConfig(type="noop"),
        )
        ps = CountingPowerSwitch()
        clock = MockClock()
        service = CimierService(
            cimier_config=cfg,
            power_switch=ps,
            http_client=fake,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=clock.sleep,
            boot_poll_interval_s=0.05,
            cycle_poll_interval_s=0.05,
        )
        service.execute_command({"id": "boot-fail", "action": "open"})
        # turn_off DOIT être appelé même en boot timeout (sécurité)
        assert ps.off_count == 1
        last = ipc_manager.history[-1]
        assert last["state"] == STATE_ERROR
        assert last["error_message"] == "boot_timeout"

    def test_cycle_timeout_sets_error_state(
        self,
        cimier_config_default: CimierConfig,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        # FakeHttp : /status retourne toujours "opening" (jamais "open") → cycle_timeout.
        fake = AutoFakeHttpClient(initial_state="opening")
        # /status renvoie immédiatement 200 mais avec state="opening" indéfiniment
        cfg = CimierConfig(
            enabled=True,
            host="127.0.0.1",
            port=80,
            cycle_timeout_s=0.2,
            boot_poll_timeout_s=2.0,
            post_off_quiet_s=0.0,
            power_switch=PowerSwitchConfig(type="noop"),
        )
        ps = CountingPowerSwitch()
        clock = MockClock()
        service = CimierService(
            cimier_config=cfg,
            power_switch=ps,
            http_client=fake,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=clock.sleep,
            boot_poll_interval_s=0.05,
            cycle_poll_interval_s=0.05,
        )
        # Pour ce test, /open passe le pico en "opening" mais on force /status à
        # garder cet état (le AutoFake passe en "open" sur POST /open par défaut).
        # Solution : on neutralise le passage automatique en queueant 100 status="opening".
        for _ in range(100):
            fake.queue("/status", 200, {"state": "opening"})

        service.execute_command({"id": "cycle-fail", "action": "open"})
        assert ps.off_count == 1
        last = ipc_manager.history[-1]
        assert last["state"] == STATE_ERROR
        assert last["error_message"] == "cycle_timeout"

    def test_pico_returns_error_state_propagated(
        self,
        cimier_config_default: CimierConfig,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        fake = AutoFakeHttpClient()
        # Pico passe en "error" pendant le cycle_poll.
        fake.queue("/status", 200, {"state": "opening"})
        fake.queue("/status", 200, {"state": "error"})

        ps = CountingPowerSwitch()
        clock = MockClock()
        service = CimierService(
            cimier_config=cimier_config_default,
            power_switch=ps,
            http_client=fake,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=clock.sleep,
            boot_poll_interval_s=0.05,
            cycle_poll_interval_s=0.05,
        )
        service.execute_command({"id": "err", "action": "open"})
        assert ps.off_count == 1
        last = ipc_manager.history[-1]
        assert last["state"] == STATE_ERROR
        assert last["error_message"] == "pico_error"

    def test_http_exception_during_post_action_recovered(
        self,
        cimier_config_default: CimierConfig,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        fake = AutoFakeHttpClient()
        # Boot OK, mais POST /open lève une URLError.
        fake.queue_exception("/open", urllib.error.URLError("bad"))

        ps = CountingPowerSwitch()
        clock = MockClock()
        service = CimierService(
            cimier_config=cimier_config_default,
            power_switch=ps,
            http_client=fake,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=clock.sleep,
            boot_poll_interval_s=0.05,
            cycle_poll_interval_s=0.05,
        )
        service.execute_command({"id": "http-fail", "action": "open"})
        assert ps.off_count == 1
        last = ipc_manager.history[-1]
        assert last["state"] == STATE_ERROR
        assert last["error_message"] == "command_failed"

    def test_turn_off_called_even_on_power_on_failure(
        self,
        cimier_config_default: CimierConfig,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        ps = FailingPowerSwitch()
        clock = MockClock()
        service = CimierService(
            cimier_config=cimier_config_default,
            power_switch=ps,
            http_client=AutoFakeHttpClient(),
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=clock.sleep,
        )
        service.execute_command({"id": "panic", "action": "open"})
        # turn_on a levé, mais on doit quand même tenter turn_off pour sécurité.
        assert ps.on_count == 1
        assert ps.off_count == 1


# ======================================================================
# Section 5 : Stop
# ======================================================================

class TestStop:
    def test_stop_when_idle_is_noop(
        self,
        service_with_fake_http: Tuple[CimierService, CountingPowerSwitch, AutoFakeHttpClient, MockClock],
        ipc_manager: RecordingIpcManager,
    ) -> None:
        service, ps, _fake, _clock = service_with_fake_http
        ipc_manager.write_command({"id": "stop-idle", "action": "stop"})
        service.tick()
        assert ps.on_count == 0
        assert ps.off_count == 0
        last = ipc_manager.history[-1]
        assert last["last_action"] == ACTION_STOP
        assert last["state"] == STATE_IDLE

    def test_stop_during_cycle_poll_interrupts(
        self,
        cimier_config_default: CimierConfig,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        """Pendant cycle_poll, une commande "stop" doit être détectée et propagée."""
        fake = AutoFakeHttpClient()
        # /open → state=opening (pas "open" → cycle_poll attend)
        fake.queue("/open", 200, {"state": "opening"})
        # /status renvoie "opening" indéfiniment (jamais "open") jusqu'à stop.
        for _ in range(100):
            fake.queue("/status", 200, {"state": "opening"})

        ps = CountingPowerSwitch()
        clock = MockClock()
        service = CimierService(
            cimier_config=cimier_config_default,
            power_switch=ps,
            http_client=fake,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=clock.sleep,
            boot_poll_interval_s=0.01,
            cycle_poll_interval_s=0.01,
        )

        # Pré-écrire la commande stop AVANT execute_command pour qu'elle soit
        # détectée pendant cycle_poll. Mais l'IPC manager dédup par id : on doit
        # écrire open puis remplacer par stop avec un id différent.
        # Simulation : appeler manuellement pour reproduire la séquence.
        # On exécute open dans un setup où la 1ère lecture IPC interne ramène stop.
        # Plus simple : patch read_command pour renvoyer stop au 2e appel.

        original_read = service._ipc.read_command
        call_count = {"n": 0}

        def patched_read():
            call_count["n"] += 1
            # 1er appel (par check_for_stop_command pendant boot/cycle) → stop
            if call_count["n"] >= 1:
                return {"id": "stop-during", "action": "stop"}
            return original_read()

        service._ipc.read_command = patched_read  # type: ignore[assignment]
        service.execute_command({"id": "open-1", "action": "open"})
        # Le service a tenté un POST /stop suite à la détection.
        assert fake.count_calls("/stop", method="POST") >= 1
        # Et turn_off a bien été appelé en cleanup.
        assert ps.off_count == 1

    def test_stop_during_boot_poll_releases_power(
        self,
        cimier_config_default: CimierConfig,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        fake = AutoFakeHttpClient()
        # /status échoue → boot pas terminé, on reste en boot_poll
        for _ in range(100):
            fake.queue_exception("/status", urllib.error.URLError("nope"))

        ps = CountingPowerSwitch()
        clock = MockClock()
        service = CimierService(
            cimier_config=cimier_config_default,
            power_switch=ps,
            http_client=fake,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=clock.sleep,
            boot_poll_interval_s=0.01,
        )

        call_count = {"n": 0}

        def patched_read():
            call_count["n"] += 1
            if call_count["n"] >= 1:
                return {"id": "stop-boot", "action": "stop"}
            return None

        service._ipc.read_command = patched_read  # type: ignore[assignment]
        service.execute_command({"id": "open-boot", "action": "open"})
        # Cleanup → turn_off appelé
        assert ps.off_count == 1


# ======================================================================
# Section 6 : IPC manager
# ======================================================================

class TestIpcManager:
    def test_ipc_command_dedup_by_id(self, tmp_ipc: Tuple[Path, Path]) -> None:
        cmd_file, status_file = tmp_ipc
        ipc = CimierIpcManager(command_file=cmd_file, status_file=status_file)
        ipc.write_command({"id": "x", "action": "open"})
        first = ipc.read_command()
        second = ipc.read_command()
        assert first is not None
        assert first["id"] == "x"
        assert second is None  # même id → ignoré

    def test_ipc_command_new_id_returns(self, tmp_ipc: Tuple[Path, Path]) -> None:
        cmd_file, status_file = tmp_ipc
        ipc = CimierIpcManager(command_file=cmd_file, status_file=status_file)
        ipc.write_command({"id": "a", "action": "open"})
        assert ipc.read_command() is not None
        ipc.write_command({"id": "b", "action": "close"})
        cmd = ipc.read_command()
        assert cmd is not None
        assert cmd["id"] == "b"

    def test_ipc_status_atomic_write(self, tmp_ipc: Tuple[Path, Path]) -> None:
        cmd_file, status_file = tmp_ipc
        ipc = CimierIpcManager(command_file=cmd_file, status_file=status_file)
        for i in range(50):
            ipc.write_status({"state": "idle", "phase": "idle", "iter": i})
            # Lecture intermédiaire — JSON toujours parsable
            with open(status_file) as f:
                payload = json.loads(f.read())
            assert payload["iter"] == i

    def test_ipc_command_file_created_if_missing(
        self, tmp_path: Path
    ) -> None:
        cmd_file = tmp_path / "cimier_command.json"
        status_file = tmp_path / "cimier_status.json"
        assert not cmd_file.exists()
        CimierIpcManager(command_file=cmd_file, status_file=status_file)
        assert cmd_file.exists()

    def test_ipc_command_without_id_ignored(self, tmp_ipc: Tuple[Path, Path]) -> None:
        cmd_file, status_file = tmp_ipc
        ipc = CimierIpcManager(command_file=cmd_file, status_file=status_file)
        ipc.write_command({"action": "open"})  # pas d'id
        assert ipc.read_command() is None


# ======================================================================
# Section 7 : AC-8 — pas d'IP en dur dans le code livré
# ======================================================================

class TestNoHardcodedIps:
    def test_no_hardcoded_ips_in_delivered_python_code(self) -> None:
        """AC-8 : aucune IP 192.168.1.X ne doit être en dur dans les fichiers
        livrés par ce sub-plan (CimierConfig.host, services cimier, ce test)."""
        repo_root = Path(__file__).resolve().parent.parent
        delivered = [
            repo_root / "core" / "config" / "config_loader.py",
            repo_root / "services" / "cimier_service.py",
            repo_root / "services" / "cimier_ipc_manager.py",
            repo_root / "tests" / "test_cimier_service.py",
        ]
        pattern = re.compile(r"192\.168\.1\.\d+")
        for path in delivered:
            text = path.read_text(encoding="utf-8")
            assert not pattern.search(text), (
                f"IP 192.168.1.X en dur trouvée dans {path} — AC-8 violé. "
                "Les IPs réelles vivent UNIQUEMENT dans data/config.json."
            )

    def test_cimier_config_default_host_is_empty_string(self) -> None:
        """Garantie CimierConfig.host par défaut = '' (pas d'IP en dur)."""
        cfg = CimierConfig()
        assert cfg.host == ""
        assert cfg.power_switch.host == ""


# ======================================================================
# Section 8 : v6.0 Phase 2 — câblage WeatherProvider
# ======================================================================

class TestWeatherProviderWiring:
    """Sub-plan v6.0-02-02 : provider injecte + log au demarrage de cycle."""

    def test_default_constructor_uses_noop_weather_provider(
        self,
        cimier_config_default: CimierConfig,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        """Sans provider explicite, le service doit retomber sur NoopWeatherProvider.

        Garantie de retro-compat pour tous les tests existants qui n'ont pas
        l'argument weather_provider=.
        """
        from core.hardware.weather_provider import NoopWeatherProvider
        ps = CountingPowerSwitch()
        service = CimierService(
            cimier_config=cimier_config_default,
            power_switch=ps,
            ipc_manager=ipc_manager,
        )
        assert isinstance(service._weather_provider, NoopWeatherProvider)

    def test_cycle_logs_weather_on_start(
        self,
        service_with_simulator: Tuple[CimierService, CountingPowerSwitch, CimierSimulator],
        ipc_manager: RecordingIpcManager,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """`_run_cycle` doit emettre `cimier_event=cycle_start ... weather=<json>`."""
        service, _, _ = service_with_simulator
        with caplog.at_level("INFO", logger="services.cimier_service"):
            ipc_manager.write_command({"id": "weather-test-1", "action": "open"})
            service.tick()

        starts = [
            rec for rec in caplog.records
            if "cimier_event=cycle_start" in rec.getMessage()
        ]
        assert len(starts) == 1
        msg = starts[0].getMessage()
        assert "weather=" in msg
        assert '{"provider":"noop"}' in msg
        assert "action=open" in msg
        assert "id=weather-test-1" in msg

    def test_cycle_logs_describe_from_custom_provider(
        self,
        cimier_config_default: CimierConfig,
        ipc_manager: RecordingIpcManager,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Un provider custom voit son describe() serialise dans le log cycle_start."""

        class FakeWeatherProvider:
            def is_safe_to_open(self) -> bool:
                return True

            def is_safe_to_keep_open(self) -> bool:
                return True

            def describe(self) -> Dict[str, Any]:
                return {"provider": "fake", "wind": 42}

        ps = CountingPowerSwitch()
        fake_http = AutoFakeHttpClient()
        clock = MockClock()
        service = CimierService(
            cimier_config=cimier_config_default,
            power_switch=ps,
            http_client=fake_http,
            ipc_manager=ipc_manager,
            weather_provider=FakeWeatherProvider(),
            clock=clock,
            sleep=clock.sleep,
            boot_poll_interval_s=0.05,
            cycle_poll_interval_s=0.05,
        )
        with caplog.at_level("INFO", logger="services.cimier_service"):
            ipc_manager.write_command({"id": "fake-weather-1", "action": "open"})
            service.tick()

        starts = [
            rec for rec in caplog.records
            if "cimier_event=cycle_start" in rec.getMessage()
        ]
        assert len(starts) == 1
        msg = starts[0].getMessage()
        # JSON sort_keys=True → "provider" avant "wind"
        assert '"provider":"fake"' in msg
        assert '"wind":42' in msg

    def test_build_service_from_config_uses_factory(
        self, tmp_path: Path
    ) -> None:
        """`_build_service_from_config` doit instancier le provider via la factory.

        Cas par defaut (config.json sans section weather_provider) → Noop.
        """
        from core.hardware.weather_provider import NoopWeatherProvider
        from services.cimier_service import _build_service_from_config

        config_path = tmp_path / "config.json"
        # Config minimale qui passe le loader sans erreur.
        config_path.write_text(json.dumps({
            "site": {"latitude": 0, "longitude": 0, "altitude": 0,
                     "nom": "Test", "fuseau": "Europe/Paris"},
            "moteur": {},
            "motor_driver": {"type": "rp2040", "serial": {}},
            "suivi": {},
            "encodeur": {"enabled": False, "spi": {}, "mecanique": {}},
            "thresholds": {},
            "simulation": True,
            "cimier": {
                "enabled": False,
                "host": "127.0.0.1",
                "port": 80,
            },
        }))
        service = _build_service_from_config(config_path=config_path)
        assert isinstance(service._weather_provider, NoopWeatherProvider)
