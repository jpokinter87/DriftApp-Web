"""Tests pour services/cimier_service.py et services/cimier_ipc_manager.py.

Couvre :
  - Configuration & instantiation (factory power_switch, switch_reader, enabled flag)
  - Cinématique Shelly Bloc 2 (preflight + ordre d'appels + invariant 220V)
  - Anti-bounce post_off_quiet_s (FakeSwitchReader + MockClock)
  - Erreurs et timeouts (cycle_timeout, both_switches, power_on_failure)
  - Commande "stop" (pendant cycle, idle)
  - IPC manager : dédup, écriture atomique, création fichier
  - T7 : cycles bout-en-bout via FakeSwitchReader + CimierMechanismSim (sans HTTP)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

import pytest

from core.config.config_loader import CimierConfig, MotorShellyConfig, PowerSwitchConfig
from core.hardware.cimier_mechanism_sim import CimierMechanismSim
from core.hardware.motor_shelly import MotorShelly, NoopMotorShelly
from core.hardware.shelly_switch_reader import SwitchReaderError, SwitchState
from core.hardware.sim_motor_shelly import SimMotorShelly
from core.hardware.power_switch import (
    NoopPowerSwitch,
    PowerSwitchError,
    ShellyPowerSwitch,
)
from services.cimier_ipc_manager import CimierIpcManager
from services.cimier_service import (
    ACTION_CLOSE,
    ACTION_STOP,
    CIMIER_STATE_CLOSED,
    CIMIER_STATE_OPEN,
    STATE_COOLDOWN,
    STATE_DISABLED,
    STATE_ERROR,
    STATE_IDLE,
    CimierService,
    make_motor_shelly,
    make_power_switch,
    make_switch_reader,
)


# ======================================================================
# Helpers — FakeSwitchReader
# ======================================================================


class FakeSwitchReader:
    """Reader programmable pour tester cimier_service sans HTTP.

    ``script`` : liste de tuples (open_switch, closed_switch) consommée à
    chaque ``read()``. Le dernier tuple est répété une fois la liste épuisée.
    ``raise_error`` : si fourni, ``read()`` lève cette exception.
    """

    def __init__(self, script=None, raise_error=None):
        self._script = list(script or [(False, False)])
        self._raise_error = raise_error
        self.read_count = 0

    def read(self) -> SwitchState:
        self.read_count += 1
        if self._raise_error is not None:
            raise self._raise_error
        idx = min(self.read_count - 1, len(self._script) - 1)
        op, cl = self._script[idx]
        return SwitchState(
            open_switch=op,
            closed_switch=cl,
            both_switches=op and cl,
            raw={},
        )


class MechanismFakeSwitchReader:
    """Reader branché sur un CimierMechanismSim : lit l'état réel du mécanisme.

    Permet de tester les cycles bout-en-bout sans HTTP. Chaque ``read()``
    retourne un SwitchState dérivé de l'état courant du mécanisme.
    """

    def __init__(self, mechanism: CimierMechanismSim) -> None:
        self._m = mechanism
        self.read_count = 0

    def read(self) -> SwitchState:
        self.read_count += 1
        op = bool(self._m.open_switch)
        cl = bool(self._m.closed_switch)
        return SwitchState(
            open_switch=op,
            closed_switch=cl,
            both_switches=op and cl,
            raw={},
        )


# ======================================================================
# Helpers / fakes
# ======================================================================


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


class FailingOffPowerSwitch(CountingPowerSwitch):
    """Power switch qui lève PowerSwitchError sur turn_off (turn_on réussit)."""

    def turn_off(self) -> None:
        self.off_count += 1
        raise PowerSwitchError("simulated turn_off failure")


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


class MechanismDrivingSleep:
    """Sleep qui fait avancer un CimierMechanismSim + une MockClock de la durée.

    Permet de tester un cycle bout-en-bout sans démarrer de thread d'avancement :
    chaque ``_sleep(dt)`` côté service avance le mécanisme déterministe de dt
    secondes ET la clock injectée.
    """

    def __init__(self, mechanism: CimierMechanismSim, clock: MockClock) -> None:
        self._m = mechanism
        self._clock = clock
        self.total_slept_s: float = 0.0

    def __call__(self, seconds: float) -> None:
        seconds = float(seconds)
        if seconds > 0:
            self._m.advance(seconds)
            self._clock.advance(seconds)
            self.total_slept_s += seconds


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
    """Config par défaut pour les tests : enabled=True, timeouts courts."""
    return CimierConfig(
        enabled=True,
        cycle_timeout_s=2.0,
        boot_poll_timeout_s=2.0,
        post_off_quiet_s=10.0,
        power_switch=PowerSwitchConfig(type="noop"),
    )


@pytest.fixture
def service_with_fake_reader(
    cimier_config_default: CimierConfig,
    ipc_manager: RecordingIpcManager,
) -> Tuple[CimierService, CountingPowerSwitch, FakeSwitchReader, MockClock]:
    """Service avec FakeSwitchReader + MockClock — déterministe, pas de wall-clock."""
    ps = CountingPowerSwitch()
    # Script par défaut : switches toujours à False → cycle timeout ou ok selon les tests
    # Pour les tests d'anti-bounce, on veut un open_switch=True après preflight proceed.
    # Le script : preflight lit (False, False), puis poll lit immédiatement (True, False)
    reader = FakeSwitchReader(
        script=[
            (False, False),  # preflight → proceed (open=False, closed=False)
            (True, False),  # poll 1er tick → ok (open_switch=True)
        ]
    )
    clock = MockClock()
    service = CimierService(
        cimier_config=cimier_config_default,
        power_switch=ps,
        switch_reader=reader,
        ipc_manager=ipc_manager,
        clock=clock,
        sleep=clock.sleep,
        cycle_poll_interval_s=0.05,
        run_loop_interval_s=0.05,
    )
    return service, ps, reader, clock


# ======================================================================
# Section 1 : Configuration & instantiation
# ======================================================================


class TestConfigurationAndInstantiation:
    def test_service_disabled_when_cimier_enabled_false(
        self, ipc_manager: RecordingIpcManager
    ) -> None:
        cfg = CimierConfig(enabled=False)
        ps = CountingPowerSwitch()
        service = CimierService(cimier_config=cfg, power_switch=ps, ipc_manager=ipc_manager)
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
        sw = make_power_switch(PowerSwitchConfig(type="shelly_gen2", host="10.0.0.1", switch_id=0))
        assert isinstance(sw, ShellyPowerSwitch)
        assert sw.api == "rpc"
        assert sw.host == "10.0.0.1"

    def test_make_power_switch_factory_shelly_gen1(self) -> None:
        sw = make_power_switch(PowerSwitchConfig(type="shelly_gen1", host="10.0.0.2"))
        assert isinstance(sw, ShellyPowerSwitch)
        assert sw.api == "legacy"

    def test_make_power_switch_factory_unknown_type(self) -> None:
        with pytest.raises(ValueError):
            make_power_switch(PowerSwitchConfig(type="totally_bogus"))

    def test_make_power_switch_shelly_requires_host(self) -> None:
        with pytest.raises(ValueError):
            make_power_switch(PowerSwitchConfig(type="shelly_gen2", host=""))

    def test_make_switch_reader_factory_noop(self) -> None:
        from core.hardware.shelly_switch_reader import NoopSwitchReader
        from core.config.config_loader import SwitchReaderConfig

        r = make_switch_reader(SwitchReaderConfig(type="noop"))
        assert isinstance(r, NoopSwitchReader)

    def test_make_switch_reader_factory_shelly_uni(self) -> None:
        from core.hardware.shelly_switch_reader import ShellySwitchReader
        from core.config.config_loader import SwitchReaderConfig

        r = make_switch_reader(SwitchReaderConfig(type="shelly_uni", host="10.0.0.3", api="rpc"))
        assert isinstance(r, ShellySwitchReader)

    def test_make_switch_reader_shelly_uni_requires_host(self) -> None:
        from core.config.config_loader import SwitchReaderConfig

        with pytest.raises(ValueError):
            make_switch_reader(SwitchReaderConfig(type="shelly_uni", host=""))

    def test_make_switch_reader_unknown_type_raises(self) -> None:
        from core.config.config_loader import SwitchReaderConfig

        with pytest.raises(ValueError):
            make_switch_reader(SwitchReaderConfig(type="bogus_type"))

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
            switch_reader=FakeSwitchReader(),
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
# Section 2 : Cycle complet via simulator — SUPPRIMÉ (Bloc 2 T4)
#
# La classe TestFullCycleViaSimulator legacy testait la pipeline HTTP Pico
# (POST /open, polling pico_state, push /config) qui n'existe plus dans
# l'archi Shelly. Les invariants équivalents pour la nouvelle cinématique
# sont couverts par TestShellyCinematique (ordre d'appels + invariant
# power_off) et TestPreflightGuard.
# ======================================================================


# ======================================================================
# Section 3 : Anti-bounce (cooldown post_off_quiet_s)
# ======================================================================


class TestAntiBounceCooldown:
    def test_cooldown_window_blocks_new_command(
        self,
        service_with_fake_reader: Tuple[
            CimierService, CountingPowerSwitch, FakeSwitchReader, MockClock
        ],
        ipc_manager: RecordingIpcManager,
    ) -> None:
        service, ps, _reader, _clock = service_with_fake_reader

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
        service_with_fake_reader: Tuple[
            CimierService, CountingPowerSwitch, FakeSwitchReader, MockClock
        ],
        ipc_manager: RecordingIpcManager,
    ) -> None:
        service, ps, _reader, clock = service_with_fake_reader

        ipc_manager.write_command({"id": "c1", "action": "open"})
        service.tick()
        assert ps.on_count == 1

        # Avancer la clock au-delà de post_off_quiet_s (10s) → cooldown libéré.
        clock.advance(15.0)
        # Re-arm reader pour le 2e cycle
        service._switch_reader = FakeSwitchReader(
            script=[(False, False), (False, True)]  # preflight proceed, poll close→ok
        )
        ipc_manager.write_command({"id": "c2", "action": "close"})
        service.tick()
        assert ps.on_count == 2
        assert ps.off_count == 2

    def test_cooldown_drops_command_no_replay(
        self,
        service_with_fake_reader: Tuple[
            CimierService, CountingPowerSwitch, FakeSwitchReader, MockClock
        ],
        ipc_manager: RecordingIpcManager,
    ) -> None:
        """Mode drop (retour terrain 14/06) : une commande reçue pendant le cooldown
        est consommée puis ignorée (jamais rejouée). Seule une commande FRAÎCHE émise
        après le cooldown s'exécute — pas de file d'ordres périmés en pilotage manuel."""
        service, ps, _reader, clock = service_with_fake_reader

        ipc_manager.write_command({"id": "c1", "action": "open"})
        service.tick()
        assert ps.on_count == 1

        # Commande arrivée PENDANT le cooldown → consommée + droppée (pas de file).
        ipc_manager.write_command({"id": "c2", "action": "close"})
        service.tick()
        assert ps.on_count == 1  # pas exécutée

        # Après cooldown : AUCUN rejeu de c2 → reste idle, pas de 2e cycle.
        clock.advance(15.0)
        service.tick()
        assert ps.on_count == 1, "c2 droppée pendant cooldown → jamais rejouée"

        # Une commande FRAÎCHE émise après le cooldown est bien exécutée.
        service._switch_reader = FakeSwitchReader(
            script=[(False, False), (False, True)]  # preflight proceed, poll closed→ok
        )
        ipc_manager.write_command({"id": "c3", "action": "close"})
        service.tick()
        assert ps.on_count == 2
        last = ipc_manager.history[-1]
        assert last["last_action"] == ACTION_CLOSE
        assert last["command_id"] == "c3"


# ======================================================================
# Section 4 : Erreurs & timeouts
# ======================================================================


class TestErrorsAndTimeouts:
    """Erreurs et timeouts — archi Shelly (T4)."""

    def test_cycle_timeout_sets_error_state(
        self,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        """poll_target_switch ne voit jamais open_switch=True → cycle_timeout."""
        # Preflight : switches au repos → proceed.
        # poll_target_switch : renvoie indéfiniment (False, False) → timeout.
        reader = FakeSwitchReader(
            script=[(False, False)]  # répété indéfiniment (dernier tuple réutilisé)
        )

        cfg = CimierConfig(
            enabled=True,
            cycle_timeout_s=0.2,
            post_off_quiet_s=0.0,
            shelly_settle_s=0.0,
            power_switch=PowerSwitchConfig(type="noop"),
        )
        ps = CountingPowerSwitch()
        clock = MockClock()
        service = CimierService(
            cimier_config=cfg,
            power_switch=ps,
            switch_reader=reader,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=clock.sleep,
            cycle_poll_interval_s=0.05,
        )
        service.execute_command({"id": "cycle-fail", "action": "open"})
        # Invariant 220V : power_off appelé en cleanup.
        assert ps.off_count == 1
        last = ipc_manager.history[-1]
        assert last["state"] == STATE_ERROR
        assert last["error_message"] == "cycle_timeout"

    def test_error_state_preserved_during_cooldown_ticks(
        self,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        """L'état ERROR survit aux ticks de cooldown (diagnostic terrain).

        Avant fix : le tick suivant republiait STATE_COOLDOWN avec
        error_message="" → l'erreur disparaissait de l'UI après ~0.5 s.
        """
        reader = FakeSwitchReader(script=[(False, False)])  # poll → timeout
        cfg = CimierConfig(
            enabled=True,
            cycle_timeout_s=0.2,
            post_off_quiet_s=10.0,
            shelly_settle_s=0.0,
            power_switch=PowerSwitchConfig(type="noop"),
        )
        ps = CountingPowerSwitch()
        clock = MockClock()
        service = CimierService(
            cimier_config=cfg,
            power_switch=ps,
            switch_reader=reader,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=clock.sleep,
            cycle_poll_interval_s=0.05,
        )
        service.execute_command({"id": "cooldown-err", "action": "open"})
        assert ipc_manager.history[-1]["state"] == STATE_ERROR

        # Tick pendant le cooldown : l'erreur doit rester visible.
        clock.advance(1.0)
        service.tick()
        last = ipc_manager.history[-1]
        assert last["state"] == STATE_ERROR
        assert last["error_message"] == "cycle_timeout"

        # Cooldown expiré : retour idle, erreur effacée.
        clock.advance(10.0)
        service.tick()
        last = ipc_manager.history[-1]
        assert last["state"] == STATE_IDLE
        assert last["error_message"] == ""

    def test_both_switches_during_poll_sets_error(
        self,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        """Si reader retourne both_switches=True pendant le poll → error."""
        # Preflight : repos → proceed.
        # poll_target_switch : 1er état anormal → both_switches_triggered.
        reader = FakeSwitchReader(
            script=[
                (False, False),  # preflight → proceed
                (True, True),  # poll 1er tick → both_switches
            ]
        )

        cfg = CimierConfig(
            enabled=True,
            cycle_timeout_s=2.0,
            post_off_quiet_s=0.0,
            shelly_settle_s=0.0,
            power_switch=PowerSwitchConfig(type="noop"),
        )
        ps = CountingPowerSwitch()
        clock = MockClock()
        service = CimierService(
            cimier_config=cfg,
            power_switch=ps,
            switch_reader=reader,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=clock.sleep,
            cycle_poll_interval_s=0.05,
        )
        service.execute_command({"id": "both", "action": "open"})
        assert ps.off_count == 1
        last = ipc_manager.history[-1]
        assert last["state"] == STATE_ERROR
        assert last["error_message"] == "both_switches_triggered"

    def test_turn_off_called_even_on_power_on_failure(
        self,
        cimier_config_default: CimierConfig,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        """Invariant 220V : turn_off appelé en cleanup même si turn_on raise."""
        ps = FailingPowerSwitch()
        # Preflight : OK → proceed (sans switches).
        reader = FakeSwitchReader(script=[(False, False)])
        clock = MockClock()
        service = CimierService(
            cimier_config=cimier_config_default,
            power_switch=ps,
            switch_reader=reader,
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
        service_with_fake_reader: Tuple[
            CimierService, CountingPowerSwitch, FakeSwitchReader, MockClock
        ],
        ipc_manager: RecordingIpcManager,
    ) -> None:
        service, ps, _reader, _clock = service_with_fake_reader
        ipc_manager.write_command({"id": "stop-idle", "action": "stop"})
        service.tick()
        assert ps.on_count == 0
        assert ps.off_count == 0
        last = ipc_manager.history[-1]
        assert last["last_action"] == ACTION_STOP
        assert last["state"] == STATE_IDLE

    def test_stop_during_poll_switch_releases_power_and_motor(
        self,
        cimier_config_default: CimierConfig,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        """Pendant poll_switch, une commande "stop" doit interrompre + cleanup.

        Archi Shelly (T4) : pas de POST /stop vers le Pico (capteur-only).
        L'interruption coupe le moteur (motor_shelly.turn_off cleanup) puis
        le power_switch (invariant 220V).
        """
        # Preflight : repos → proceed.
        # poll_target_switch : (False, False) répété indéfiniment → jamais ok.
        reader = FakeSwitchReader(script=[(False, False)])

        mech = CimierMechanismSim()
        sim_motor = SimMotorShelly(mech)
        ps = CountingPowerSwitch()
        clock = MockClock()
        service = CimierService(
            cimier_config=cimier_config_default,
            power_switch=ps,
            motor_shelly=sim_motor,
            switch_reader=reader,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=clock.sleep,
            cycle_poll_interval_s=0.01,
        )

        # Patch read_command pour renvoyer une commande stop dès qu'elle est
        # interrogée (le 1er appel viendra de _check_for_stop_command pendant
        # poll_target_switch).
        def patched_read():
            return {"id": "stop-during", "action": "stop"}

        service._ipc.read_command = patched_read  # type: ignore[assignment]
        service.execute_command({"id": "open-1", "action": "open"})

        # Invariant 220V + moteur OFF : cleanup garanti.
        assert ps.off_count == 1
        # SimMotorShelly enregistre turn_off au moins 2 fois (défensif + cleanup).
        turn_off_calls = [c for c in sim_motor.calls if c[0] == "turn_off"]
        assert len(turn_off_calls) >= 2


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

    def test_ipc_command_file_created_if_missing(self, tmp_path: Path) -> None:
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

    def test_write_command_returns_true_on_success(self, tmp_ipc: Tuple[Path, Path]) -> None:
        """Le booléen alimente la télémétrie de `session_close_sequence` : sur la
        branche automatique non supervisée, un `cimier_close_sent` toujours vrai
        masquerait une écriture IPC perdue."""
        cmd_file, status_file = tmp_ipc
        ipc = CimierIpcManager(command_file=cmd_file, status_file=status_file)
        assert ipc.write_command({"id": "ok-1", "action": "close"}) is True

    def test_write_command_returns_false_on_ioerror(self, tmp_ipc: Tuple[Path, Path]) -> None:
        """Patch open pour lever OSError → False, pas d'exception remontée."""
        cmd_file, status_file = tmp_ipc
        ipc = CimierIpcManager(command_file=cmd_file, status_file=status_file)
        with patch("builtins.open", side_effect=OSError("disk full")):
            ok = ipc.write_command({"id": "ko-1", "action": "close"})
        assert ok is False

    def test_ipc_status_last_update_is_utc_aware(self, tmp_ipc: Tuple[Path, Path]) -> None:
        """`last_update` doit être ISO 8601 tz-aware UTC (cohérent avec le
        reste du cimier — scheduler/service publient en UTC). Un timestamp
        naïf local était ambigu pour les consommateurs (Django, JS Date.parse
        côté navigateur dans une autre timezone)."""
        from datetime import datetime, timezone

        cmd_file, status_file = tmp_ipc
        ipc = CimierIpcManager(command_file=cmd_file, status_file=status_file)
        ipc.write_status({"state": "idle", "phase": "idle"})
        with open(status_file) as f:
            payload = json.loads(f.read())
        dt = datetime.fromisoformat(payload["last_update"])
        assert dt.tzinfo is not None
        assert dt.utcoffset() == timezone.utc.utcoffset(None)


# ======================================================================
# Section 7 : AC-8 — pas d'IP en dur dans le code livré
# ======================================================================


class TestNoHardcodedIps:
    def test_no_hardcoded_ips_in_delivered_python_code(self) -> None:
        """AC-8 : aucune IP 192.168.1.X ne doit être en dur dans les fichiers
        livrés par ce sub-plan (CimierConfig, services cimier, ce test)."""
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

    def test_cimier_config_default_switch_reader_host_is_empty_string(self) -> None:
        """Garantie CimierConfig.switch_reader.host par défaut = '' (pas d'IP en dur)."""
        cfg = CimierConfig()
        assert cfg.switch_reader.host == ""
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
        # preflight → proceed ; poll → ok (open_switch=True immédiatement)
        reader = FakeSwitchReader(script=[(False, False), (True, False)])
        clock = MockClock()
        service = CimierService(
            cimier_config=cimier_config_default,
            power_switch=ps,
            switch_reader=reader,
            ipc_manager=ipc_manager,
            weather_provider=FakeWeatherProvider(),
            clock=clock,
            sleep=clock.sleep,
            cycle_poll_interval_s=0.05,
        )
        with caplog.at_level("INFO", logger="services.cimier_service"):
            ipc_manager.write_command({"id": "fake-weather-1", "action": "open"})
            service.tick()

        starts = [rec for rec in caplog.records if "cimier_event=cycle_start" in rec.getMessage()]
        assert len(starts) == 1
        msg = starts[0].getMessage()
        # JSON sort_keys=True → "provider" avant "wind"
        assert '"provider":"fake"' in msg
        assert '"wind":42' in msg

    def test_build_service_from_config_uses_factory(self, tmp_path: Path) -> None:
        """`_build_service_from_config` doit instancier le provider via la factory.

        Cas par defaut (config.json sans section weather_provider) → Noop.
        """
        from core.hardware.weather_provider import NoopWeatherProvider
        from services.cimier_service import _build_service_from_config

        config_path = tmp_path / "config.json"
        # Config minimale qui passe le loader sans erreur.
        config_path.write_text(
            json.dumps(
                {
                    "site": {
                        "latitude": 0,
                        "longitude": 0,
                        "altitude": 0,
                        "nom": "Test",
                        "fuseau": "Europe/Paris",
                    },
                    "moteur": {},
                    "motor_driver": {"type": "rp2040", "serial": {}},
                    "suivi": {},
                    "encodeur": {"enabled": False, "spi": {}, "mecanique": {}},
                    "thresholds": {},
                    "simulation": True,
                    "cimier": {
                        "enabled": False,
                    },
                }
            )
        )
        service = _build_service_from_config(config_path=config_path)
        assert isinstance(service._weather_provider, NoopWeatherProvider)


# ======================================================================
# Section 9 : v6.0 Phase 3 — câblage scheduler astropy
# ======================================================================


class TestSchedulerWiring:
    """Sub-plan v6.0-03-01 : scheduler astropy intégré à tick()."""

    def _make_config_with_automation(
        self,
        mode: str = "full",
        scheduler_interval_seconds: int = 60,
    ) -> CimierConfig:
        from core.config.config_loader import CimierAutomationConfig

        return CimierConfig(
            enabled=True,
            cycle_timeout_s=2.0,
            boot_poll_timeout_s=2.0,
            post_off_quiet_s=10.0,
            power_switch=PowerSwitchConfig(type="noop"),
            automation=CimierAutomationConfig(
                mode=mode,
                scheduler_interval_seconds=scheduler_interval_seconds,
            ),
        )

    def test_scheduler_disabled_when_automation_off(self, ipc_manager: RecordingIpcManager) -> None:
        cfg = self._make_config_with_automation(mode="manual")
        service = CimierService(
            cimier_config=cfg,
            power_switch=NoopPowerSwitch(),
            ipc_manager=ipc_manager,
        )
        assert service._scheduler is None
        # tick() ne doit pas crash sans scheduler
        service.tick()  # juste un tick safe

    def test_scheduler_built_when_automation_on_with_site_config(
        self,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        from core.config.config_loader import SiteConfig
        from services.cimier_scheduler import CimierScheduler

        site = SiteConfig(
            latitude=44.15, longitude=5.23, altitude=800.0, nom="Test", fuseau="Europe/Paris"
        )
        cfg = self._make_config_with_automation(mode="full")
        service = CimierService(
            cimier_config=cfg,
            power_switch=NoopPowerSwitch(),
            ipc_manager=ipc_manager,
            site_config=site,
        )
        assert isinstance(service._scheduler, CimierScheduler)

    def test_scheduler_skipped_when_automation_on_without_site_config(
        self, ipc_manager: RecordingIpcManager
    ) -> None:
        """Sans site_config, on log un warning et on n'instancie pas le scheduler."""
        cfg = self._make_config_with_automation(mode="full")
        service = CimierService(
            cimier_config=cfg,
            power_switch=NoopPowerSwitch(),
            ipc_manager=ipc_manager,
            site_config=None,  # explicite
        )
        assert service._scheduler is None

    def test_scheduler_called_once_per_interval_window(
        self, ipc_manager: RecordingIpcManager
    ) -> None:
        """Avec interval=60s, scheduler.maybe_trigger appelé 1× par fenêtre 60s, pas chaque tick."""
        from services.cimier_scheduler import SchedulerDecision

        class CountingScheduler:
            def __init__(self) -> None:
                self.call_count = 0

            def maybe_trigger(self, current_state: str) -> SchedulerDecision:
                self.call_count += 1
                from datetime import datetime, timezone

                return SchedulerDecision(
                    "skip:state", float("nan"), "flat", datetime.now(timezone.utc)
                )

        cfg = self._make_config_with_automation(mode="full", scheduler_interval_seconds=60)
        clock = MockClock(start=1000.0)
        scheduler = CountingScheduler()
        service = CimierService(
            cimier_config=cfg,
            power_switch=NoopPowerSwitch(),
            ipc_manager=ipc_manager,
            scheduler=scheduler,  # type: ignore[arg-type]
            clock=clock,
            sleep=clock.sleep,
        )

        # 5 ticks rapides (delta < interval) → 1 seul appel scheduler
        for _ in range(5):
            service.tick()
            clock.advance(0.5)
        assert scheduler.call_count == 1

        # Avancer > interval → prochain tick → 2e appel
        clock.advance(70.0)
        service.tick()
        assert scheduler.call_count == 2

    def test_scheduler_exception_does_not_crash_tick(
        self, ipc_manager: RecordingIpcManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Si scheduler.maybe_trigger lève → log error, tick continue."""

        class BrokenScheduler:
            def maybe_trigger(self, current_state: str):
                raise RuntimeError("boom")

        cfg = self._make_config_with_automation(mode="full")
        service = CimierService(
            cimier_config=cfg,
            power_switch=NoopPowerSwitch(),
            ipc_manager=ipc_manager,
            scheduler=BrokenScheduler(),  # type: ignore[arg-type]
        )

        with caplog.at_level("ERROR", logger="services.cimier_service"):
            service.tick()  # ne doit pas remonter l'exception

        assert any("scheduler_exception" in r.getMessage() for r in caplog.records)

    def test_derive_current_cimier_state_mappings(self, ipc_manager: RecordingIpcManager) -> None:
        """Vérifie le mapping switches capteur → CIMIER_STATE_* (archi Shelly Bloc 2)."""
        from services.cimier_scheduler import (
            CIMIER_STATE_CLOSED,
            CIMIER_STATE_COOLDOWN,
            CIMIER_STATE_ERROR,
            CIMIER_STATE_OPEN,
        )

        cfg = self._make_config_with_automation(mode="manual")  # pas besoin du scheduler
        service = CimierService(
            cimier_config=cfg,
            power_switch=NoopPowerSwitch(),
            ipc_manager=ipc_manager,
        )

        # Aucun switch (mouvement / boot) → "unknown" (default-safe : pas de trigger)
        service._last_open_switch = False
        service._last_closed_switch = False
        assert service._derive_current_cimier_state() == "unknown"

        # closed_switch True → CIMIER_STATE_CLOSED
        service._last_open_switch = False
        service._last_closed_switch = True
        assert service._derive_current_cimier_state() == CIMIER_STATE_CLOSED

        # open_switch True → CIMIER_STATE_OPEN
        service._last_open_switch = True
        service._last_closed_switch = False
        assert service._derive_current_cimier_state() == CIMIER_STATE_OPEN

        # both switches True → CIMIER_STATE_ERROR (anomalie capteur)
        service._last_open_switch = True
        service._last_closed_switch = True
        assert service._derive_current_cimier_state() == CIMIER_STATE_ERROR

        # cooldown actif → CIMIER_STATE_COOLDOWN (priorité absolue)
        service._last_open_switch = True
        service._last_closed_switch = False
        service._cooldown_end_ts = 999999.0
        assert service._derive_current_cimier_state() == CIMIER_STATE_COOLDOWN


# ======================================================================
# Section 10 : v6.0 Phase 4 sub-plan 04-01 — IPC enrichi (mode + next_*)
# ======================================================================


class TestSchedulerIpcEnrichmentPhase4:
    """AC-3 du sub-plan v6.0-04-01 : cimier_status.json contient mode +
    next_open_at + next_close_at (ISO 8601 UTC ou null) après un tick scheduler.
    """

    def _make_config(self, mode: str) -> CimierConfig:
        from core.config.config_loader import CimierAutomationConfig

        return CimierConfig(
            enabled=True,
            cycle_timeout_s=2.0,
            boot_poll_timeout_s=2.0,
            post_off_quiet_s=10.0,
            power_switch=PowerSwitchConfig(type="noop"),
            automation=CimierAutomationConfig(
                mode=mode,
                scheduler_interval_seconds=60,
            ),
        )

    def _make_scheduler_stub(self, next_open=None, next_close=None):
        from datetime import datetime, timezone
        from services.cimier_scheduler import SchedulerDecision

        class StubScheduler:
            def __init__(self):
                self.compute_calls = 0

            def maybe_trigger(self, current_state):
                return SchedulerDecision(
                    "skip:state", float("nan"), "flat", datetime.now(timezone.utc)
                )

            def compute_next_triggers(self, now):
                self.compute_calls += 1
                return (next_open, next_close)

        return StubScheduler()

    def test_status_payload_contains_mode_and_next_triggers_iso(
        self, ipc_manager: RecordingIpcManager
    ) -> None:
        """Mode != manual + scheduler retourne datetime → ISO 8601 dans cimier_status.json."""
        from datetime import datetime, timezone

        next_open = datetime(2026, 5, 15, 21, 30, tzinfo=timezone.utc)
        next_close = datetime(2026, 5, 16, 4, 45, tzinfo=timezone.utc)
        cfg = self._make_config(mode="full")
        scheduler = self._make_scheduler_stub(next_open=next_open, next_close=next_close)
        clock = MockClock(start=1000.0)
        service = CimierService(
            cimier_config=cfg,
            power_switch=NoopPowerSwitch(),
            ipc_manager=ipc_manager,
            scheduler=scheduler,  # type: ignore[arg-type]
            clock=clock,
            sleep=clock.sleep,
        )

        # 1er tick → scheduler appelé (1ère fenêtre, gating ouvert)
        service.tick()
        # IPC publiée
        assert len(ipc_manager.history) >= 1
        last_status = ipc_manager.history[-1]
        assert last_status["mode"] == "full"
        assert last_status["next_open_at"] == next_open.isoformat()
        assert last_status["next_close_at"] == next_close.isoformat()
        assert scheduler.compute_calls == 1

    def test_status_payload_next_triggers_null_when_mode_manual(
        self, ipc_manager: RecordingIpcManager
    ) -> None:
        """mode=manual → scheduler None côté service → mode='manual' + next_*=null."""
        cfg = self._make_config(mode="manual")
        # Aucun scheduler injecté, automation.mode == "manual" → service._scheduler reste None
        service = CimierService(
            cimier_config=cfg,
            power_switch=NoopPowerSwitch(),
            ipc_manager=ipc_manager,
        )
        assert service._scheduler is None  # sanity
        # tick() force une publication idle (pas de scheduler appelé)
        service.tick()
        assert len(ipc_manager.history) >= 1
        last_status = ipc_manager.history[-1]
        assert last_status["mode"] == "manual"
        assert last_status["next_open_at"] is None
        assert last_status["next_close_at"] is None


class TestDevModeOverrides:
    """v6.3.2 / V3 — CIMIER_DEV_MODE=1 patche la config cimier en mémoire pour
    pointer le simulateur localhost:8001, sans toucher data/config.json.
    """

    def test_dev_mode_off_no_override(self, monkeypatch):
        """Sans env var, _is_dev_mode_enabled retourne False."""
        from services.cimier_service import _is_dev_mode_enabled

        monkeypatch.delenv("CIMIER_DEV_MODE", raising=False)
        assert _is_dev_mode_enabled() is False

    def test_dev_mode_on_truthy_values(self, monkeypatch):
        """Valeurs truthy : 1, true, yes, on (case-insensitive)."""
        from services.cimier_service import _is_dev_mode_enabled

        for val in ("1", "true", "TRUE", "yes", "on", "On"):
            monkeypatch.setenv("CIMIER_DEV_MODE", val)
            assert _is_dev_mode_enabled() is True, f"Failed for {val!r}"

    def test_dev_mode_on_falsy_values(self, monkeypatch):
        """Valeurs non-truthy → False."""
        from services.cimier_service import _is_dev_mode_enabled

        for val in ("0", "false", "no", "off", ""):
            monkeypatch.setenv("CIMIER_DEV_MODE", val)
            assert _is_dev_mode_enabled() is False, f"Failed for {val!r}"

    def test_apply_dev_mode_overrides_patches_switch_reader_and_power_switch(self):
        """L'override V3 patche switch_reader.* / power_switch.* / motor_shelly.*."""
        from services.cimier_service import _apply_dev_mode_overrides

        cfg = CimierConfig(enabled=False)
        cfg.power_switch.type = "shelly_gen1"

        _apply_dev_mode_overrides(cfg)

        assert cfg.enabled is True
        assert cfg.switch_reader.type == "shelly_uni"
        assert cfg.switch_reader.host == "127.0.0.1:8001"
        assert cfg.switch_reader.api == "rpc"
        assert cfg.power_switch.type == "shelly_gen1"
        assert cfg.power_switch.host == "127.0.0.1:8001"
        assert cfg.motor_shelly.host_motor == "127.0.0.1:8001"
        assert cfg.motor_shelly.host_dir == "127.0.0.1:8001"

    def test_apply_dev_mode_overrides_preserves_other_fields(self):
        """Les champs hors scope (timeouts, automation) ne bougent pas."""
        from services.cimier_service import _apply_dev_mode_overrides

        cfg = CimierConfig(
            enabled=False,
            cycle_timeout_s=120.0,
            boot_poll_timeout_s=45.0,
        )
        original_automation_mode = cfg.automation.mode

        _apply_dev_mode_overrides(cfg)

        assert cfg.cycle_timeout_s == 120.0
        assert cfg.boot_poll_timeout_s == 45.0
        assert cfg.automation.mode == original_automation_mode


# ======================================================================
# Section T2 Bloc 2 : Garde-fou pré-vol (spec §3.0 + §4)
# ======================================================================


class TestPreflightGuard:
    """Garde-fou « déjà en butée » : 0 action électrique si fin de course cible atteinte."""

    def _make_service(
        self,
        ipc_manager: RecordingIpcManager,
        script: list,
        raise_error: Optional[Exception] = None,
    ):
        ps = CountingPowerSwitch()
        reader = FakeSwitchReader(script=script, raise_error=raise_error)

        mech = CimierMechanismSim()
        sim_motor = SimMotorShelly(mech)
        cfg = CimierConfig(
            enabled=True,
            cycle_timeout_s=2.0,
            post_off_quiet_s=0.0,
            shelly_settle_s=0.0,
        )
        clock = MockClock()
        service = CimierService(
            cimier_config=cfg,
            power_switch=ps,
            motor_shelly=sim_motor,
            switch_reader=reader,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=clock.sleep,
        )
        return service, ps, sim_motor

    def test_open_when_already_open_is_noop(self, ipc_manager: RecordingIpcManager) -> None:
        # Préflight « déjà ouvert » → open_switch=True, closed_switch=False
        service, ps, sim_motor = self._make_service(
            ipc_manager,
            script=[(True, False)],
        )
        service.execute_command({"id": "1", "action": "open"})
        assert ps.on_count == 0
        assert ps.off_count == 0
        assert sim_motor.calls == []
        last = ipc_manager.history[-1]
        assert last["state"] == CIMIER_STATE_OPEN
        assert last.get("error_message", "") in ("", None)

    def test_close_when_already_closed_is_noop(self, ipc_manager: RecordingIpcManager) -> None:
        # Préflight « déjà fermé » → open_switch=False, closed_switch=True
        service, ps, sim_motor = self._make_service(
            ipc_manager,
            script=[(False, True)],
        )
        service.execute_command({"id": "2", "action": "close"})
        assert ps.on_count == 0
        assert ps.off_count == 0
        assert sim_motor.calls == []
        last = ipc_manager.history[-1]
        assert last["state"] == CIMIER_STATE_CLOSED

    def test_both_switches_true_blocks_with_error(self, ipc_manager: RecordingIpcManager) -> None:
        # Préflight « both switches » → error
        service, ps, sim_motor = self._make_service(
            ipc_manager,
            script=[(True, True)],
        )
        service.execute_command({"id": "3", "action": "open"})
        assert ps.on_count == 0
        assert sim_motor.calls == []
        last = ipc_manager.history[-1]
        assert last["state"] == STATE_ERROR
        assert last["error_message"] == "both_switches_triggered"

    def test_status_unreachable_blocks_with_error(self, ipc_manager: RecordingIpcManager) -> None:
        # Capteur injoignable → SwitchReaderError lors du preflight
        service, ps, sim_motor = self._make_service(
            ipc_manager,
            script=[],
            raise_error=SwitchReaderError("nope"),
        )
        service.execute_command({"id": "4", "action": "open"})
        assert ps.on_count == 0
        assert sim_motor.calls == []
        last = ipc_manager.history[-1]
        assert last["state"] == STATE_ERROR
        assert last["error_message"] == "precheck_unreachable"


# ======================================================================
# Section T1 Bloc 2 : MotorShelly factory + injection
# ======================================================================


class TestMotorShellyFactory:
    def test_factory_returns_motor_shelly_when_hosts_configured(self) -> None:
        # IPs fictives non-routables (TEST-NET RFC 5737) — jamais en prod.
        cfg = MotorShellyConfig(
            host_motor="203.0.113.85",
            host_dir="203.0.113.86",
            relay_motor=0,
            relay_dir=0,
            open_dir_state=True,
            motor_on_relay_state=False,
            api="rpc",
            timer_safety_sec=90.0,
        )
        m = make_motor_shelly(cfg)
        assert isinstance(m, MotorShelly)
        assert m.host_motor == "203.0.113.85"
        assert m.host_dir == "203.0.113.86"
        assert m.motor_on_relay_state is False

    def test_factory_returns_noop_when_hosts_empty(self) -> None:
        cfg = MotorShellyConfig(host_motor="", host_dir="")
        m = make_motor_shelly(cfg)
        assert isinstance(m, NoopMotorShelly)

    def test_factory_returns_noop_when_only_one_host(self) -> None:
        cfg = MotorShellyConfig(host_motor="203.0.113.85", host_dir="")
        m = make_motor_shelly(cfg)
        assert isinstance(m, NoopMotorShelly)


class TestMotorShellyInjection:
    def test_constructor_accepts_motor_shelly(
        self,
        cimier_config_default: CimierConfig,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        mech = CimierMechanismSim()
        sim_motor = SimMotorShelly(mech)
        ps = CountingPowerSwitch()
        service = CimierService(
            cimier_config=cimier_config_default,
            power_switch=ps,
            motor_shelly=sim_motor,
            ipc_manager=ipc_manager,
        )
        assert service._motor_shelly is sim_motor

    def test_constructor_defaults_motor_shelly_to_factory(
        self,
        ipc_manager: RecordingIpcManager,
    ) -> None:
        cfg = CimierConfig(enabled=True)
        ps = CountingPowerSwitch()
        service = CimierService(cimier_config=cfg, power_switch=ps, ipc_manager=ipc_manager)
        assert isinstance(service._motor_shelly, NoopMotorShelly)


# ======================================================================
# Section T3 Bloc 2 : Cinématique Shelly nominale (spec §3.1 / §3.2)
# ======================================================================


class TestShellyCinematique:
    """Cinématique cible (spec §3.1 / §3.2) : ordre d'appels Shelly."""

    def _build_service_for_action(self, ipc_manager: RecordingIpcManager, action_target: str):
        initial = "closed" if action_target == "open" else "open"
        mech = CimierMechanismSim(initial_state=initial, full_travel_s=0.5)
        sim_motor = SimMotorShelly(mech)
        ps = CountingPowerSwitch()
        clock = MockClock()
        advancing_sleep = MechanismDrivingSleep(mech, clock)

        # FakeSwitchReader branché sur le mécanisme réel
        reader = MechanismFakeSwitchReader(mech)

        cfg = CimierConfig(
            enabled=True,
            cycle_timeout_s=5.0,
            post_off_quiet_s=0.0,
            shelly_settle_s=0.5,
            motor_shelly=MotorShellyConfig(
                host_motor="203.0.113.85",
                host_dir="203.0.113.86",
                timer_safety_sec=90.0,
            ),
        )
        service = CimierService(
            cimier_config=cfg,
            power_switch=ps,
            motor_shelly=sim_motor,
            switch_reader=reader,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=advancing_sleep,
            cycle_poll_interval_s=0.05,
        )
        return service, ps, sim_motor

    def test_open_cycle_calls_in_order(self, ipc_manager: RecordingIpcManager) -> None:
        service, ps, sim_motor = self._build_service_for_action(ipc_manager, action_target="open")
        service.execute_command({"id": "10", "action": "open"})

        assert ps.on_count == 1, "power_switch.turn_on appelé exactement 1 fois"
        assert ps.off_count == 1, "power_switch.turn_off appelé exactement 1 fois"
        kinds = [c[0] for c in sim_motor.calls]
        assert kinds[0] == "turn_off", "1er appel moteur = turn_off défensif"
        assert kinds[1] == "set_direction", "puis set_direction"
        assert sim_motor.calls[1][1] is True, "set_direction(open=True)"
        assert kinds[2] == "turn_on", "puis turn_on"
        assert sim_motor.calls[2][1] == 90.0, "turn_on(timer_s=90.0)"
        assert kinds[-1] == "turn_off", "dernier appel moteur = turn_off final"

    def test_close_cycle_calls_in_order(self, ipc_manager: RecordingIpcManager) -> None:
        service, ps, sim_motor = self._build_service_for_action(ipc_manager, action_target="close")
        service.execute_command({"id": "11", "action": "close"})

        kinds = [c[0] for c in sim_motor.calls]
        assert kinds[0] == "turn_off"
        assert kinds[1] == "set_direction"
        assert sim_motor.calls[1][1] is False, "set_direction(open=False) pour fermeture"
        assert kinds[2] == "turn_on"
        assert kinds[-1] == "turn_off"

    def test_dir_settle_inserted_between_set_direction_and_turn_on(
        self, ipc_manager: RecordingIpcManager
    ) -> None:
        """Le settle DPDT doit survenir APRÈS set_direction et AVANT turn_on.

        Régression terrain 14/06 : sans ce délai, le moteur s'énergisait ~8 ms
        après l'ordre de sens → DPDT pas encore commuté → sens aléatoire.
        """
        mech = CimierMechanismSim(initial_state="closed", full_travel_s=0.5)
        sim_motor = SimMotorShelly(mech)
        ps = CountingPowerSwitch()
        clock = MockClock()
        base_sleep = MechanismDrivingSleep(mech, clock)

        # Sleep instrumenté : capture (durée, snapshot des appels moteur déjà faits).
        records: list[tuple[float, list[str]]] = []

        def recording_sleep(dt: float) -> None:
            records.append((dt, [c[0] for c in sim_motor.calls]))
            base_sleep(dt)

        reader = MechanismFakeSwitchReader(mech)
        cfg = CimierConfig(
            enabled=True,
            cycle_timeout_s=5.0,
            post_off_quiet_s=0.0,
            shelly_settle_s=0.0,  # isolé : seul dir_settle produit un sleep de 0.3
            dir_settle_s=0.3,
            motor_shelly=MotorShellyConfig(
                host_motor="203.0.113.85",
                host_dir="203.0.113.86",
                timer_safety_sec=90.0,
            ),
        )
        service = CimierService(
            cimier_config=cfg,
            power_switch=ps,
            motor_shelly=sim_motor,
            switch_reader=reader,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=recording_sleep,
            cycle_poll_interval_s=0.05,
        )
        service.execute_command({"id": "20", "action": "open"})

        dir_settle_snaps = [snap for dt, snap in records if dt == 0.3]
        assert dir_settle_snaps, "un _sleep(dir_settle_s=0.3) doit être émis pendant le cycle"
        snap = dir_settle_snaps[0]
        assert "set_direction" in snap, "le settle DPDT vient APRÈS set_direction"
        assert "turn_on" not in snap, "le settle DPDT vient AVANT turn_on"

    def test_dir_settle_zero_emits_no_extra_sleep(self, ipc_manager: RecordingIpcManager) -> None:
        """dir_settle_s=0 → aucun sleep intercalé (rétro-compat / opt-out)."""
        mech = CimierMechanismSim(initial_state="closed", full_travel_s=0.5)
        sim_motor = SimMotorShelly(mech)
        ps = CountingPowerSwitch()
        clock = MockClock()
        base_sleep = MechanismDrivingSleep(mech, clock)
        durations: list[float] = []

        def recording_sleep(dt: float) -> None:
            durations.append(dt)
            base_sleep(dt)

        reader = MechanismFakeSwitchReader(mech)
        cfg = CimierConfig(
            enabled=True,
            cycle_timeout_s=5.0,
            post_off_quiet_s=0.0,
            shelly_settle_s=0.0,
            dir_settle_s=0.0,
            motor_shelly=MotorShellyConfig(
                host_motor="203.0.113.85",
                host_dir="203.0.113.86",
                timer_safety_sec=90.0,
            ),
        )
        service = CimierService(
            cimier_config=cfg,
            power_switch=ps,
            motor_shelly=sim_motor,
            switch_reader=reader,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=recording_sleep,
            cycle_poll_interval_s=0.05,
        )
        service.execute_command({"id": "21", "action": "open"})

        assert 0.3 not in durations, "dir_settle_s=0 ne doit émettre aucun sleep DPDT"

    def test_power_off_always_called_even_on_motor_exception(
        self, ipc_manager: RecordingIpcManager
    ) -> None:
        from core.hardware.motor_shelly import MotorShellyError

        class CrashingMotor:
            def __init__(self):
                self.turn_off_count = 0

            def set_direction(self, open_direction):
                raise MotorShellyError("nope")

            def turn_on(self, timer_s: float = 0.0):
                pass

            def turn_off(self):
                self.turn_off_count += 1

        crashing = CrashingMotor()
        ps = CountingPowerSwitch()
        # Preflight → proceed ; set_direction va crasher → cycle error
        reader = FakeSwitchReader(script=[(False, False)])
        cfg = CimierConfig(
            enabled=True,
            cycle_timeout_s=5.0,
            post_off_quiet_s=0.0,
            shelly_settle_s=0.0,
            motor_shelly=MotorShellyConfig(
                host_motor="203.0.113.85",
                host_dir="203.0.113.86",
                timer_safety_sec=90.0,
            ),
        )
        clock = MockClock()
        service = CimierService(
            cimier_config=cfg,
            power_switch=ps,
            motor_shelly=crashing,
            switch_reader=reader,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=clock.sleep,
            cycle_poll_interval_s=0.05,
        )

        service.execute_command({"id": "12", "action": "open"})

        # Invariant : power_off appelé même si moteur crash
        assert ps.off_count == 1
        # Et turn_off moteur tenté en cleanup
        assert crashing.turn_off_count >= 1


# ======================================================================
# Section T5 Bloc 2 : verrouillage format events orchestration (spec §7)
# ======================================================================


class TestOrchestrationLogging:
    """Verrouille le format des events d'orchestration (spec §7).

    Critique pour debug à distance : la timeline d'un cycle doit être
    entièrement reconstructible depuis logs/cimier_service.log. Cassure
    de format = bug de production silencieux.
    """

    def test_full_open_cycle_publishes_expected_events(
        self, ipc_manager: RecordingIpcManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging as _logging

        caplog.set_level(_logging.INFO, logger="services.cimier_service")

        mech = CimierMechanismSim(initial_state="closed", full_travel_s=0.5)
        sim_motor = SimMotorShelly(mech)
        ps = CountingPowerSwitch()
        clock = MockClock()
        advancing_sleep = MechanismDrivingSleep(mech, clock)
        reader = MechanismFakeSwitchReader(mech)

        cfg = CimierConfig(
            enabled=True,
            cycle_timeout_s=5.0,
            post_off_quiet_s=0.0,
            shelly_settle_s=0.0,
            motor_shelly=MotorShellyConfig(
                host_motor="203.0.113.85",
                host_dir="203.0.113.86",
                timer_safety_sec=90.0,
            ),
        )
        service = CimierService(
            cimier_config=cfg,
            power_switch=ps,
            motor_shelly=sim_motor,
            switch_reader=reader,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=advancing_sleep,
            cycle_poll_interval_s=0.05,
        )
        service.execute_command({"id": "ev1", "action": "open"})

        events = [r.message for r in caplog.records if "cimier_event=" in r.message]

        # 1. cycle_start
        assert any("cimier_event=cycle_start" in m and "action=open" in m for m in events), (
            "cycle_start missing"
        )

        # 2. preflight decision=proceed (mécanisme démarre "closed" → closed_switch=true)
        assert any(
            "cimier_event=preflight" in m
            and "decision=proceed" in m
            and "open_switch=false" in m
            and "closed_switch=true" in m
            for m in events
        ), "preflight proceed missing"

        # 3. shelly_call x3 : turn_off, set_direction, turn_on
        shelly_calls = [m for m in events if "cimier_event=shelly_call" in m]
        assert len(shelly_calls) >= 3, "expected >=3 shelly_call events"
        assert any("call=turn_off" in m for m in shelly_calls), "missing call=turn_off"
        assert any("call=set_direction" in m and "open=True" in m for m in shelly_calls), (
            "missing call=set_direction open=True"
        )
        assert any("call=turn_on" in m and "timer_s=90.0" in m for m in shelly_calls), (
            "missing call=turn_on timer_s=90.0"
        )

        # 4. latency_ms présent sur chaque shelly_call
        for m in shelly_calls:
            assert "latency_ms=" in m, "latency_ms missing on shelly_call: " + m

        # 5. switch_transition
        assert any(
            "cimier_event=switch_transition" in m
            and "switch=open_switch" in m
            and "from=false" in m
            and "to=true" in m
            for m in events
        ), "switch_transition missing"

        # 6. phase events pour chaque phase majeure (avec elapsed_ms)
        for phase in (
            "power_on",
            "settle",
            "motor_off",
            "set_dir",
            "motor_on",
            "poll_switch",
            "power_off",
        ):
            assert any(
                "cimier_event=phase" in m and ("phase=" + phase) in m and "elapsed_ms=" in m
                for m in events
            ), "phase event missing: phase=" + phase

        # 7. cycle_end result=ok
        assert any(
            "cimier_event=cycle_end" in m
            and "action=open" in m
            and "result=ok" in m
            and "duration_ms=" in m
            for m in events
        ), "cycle_end result=ok missing"


# ======================================================================
# Section T6 Bloc 2 : Logging verbeux dev (spec §7)
# ======================================================================


class TestVerboseLogging:
    """Mode verbeux dev (spec §7) : DEBUG par itération de polling.

    Câble les deux switches livrés Bloc 1 sans consommateur (commit 50f52d8) :
    - cimier.verbose_logging=True (config persistante)
    - env-var CIMIER_DEV_MODE=1 (toggle dev, exporté par start_dev.sh)
    """

    def test_verbose_logging_true_emits_poll_status_per_iteration(
        self,
        ipc_manager: RecordingIpcManager,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import logging as _logging

        # Garantir que CIMIER_DEV_MODE n'interfère pas — on veut tester le flag config
        monkeypatch.delenv("CIMIER_DEV_MODE", raising=False)
        caplog.set_level(_logging.DEBUG, logger="services.cimier_service")

        mech = CimierMechanismSim(initial_state="closed", full_travel_s=0.3)
        sim_motor = SimMotorShelly(mech)
        ps = CountingPowerSwitch()
        clock = MockClock()
        advancing_sleep = MechanismDrivingSleep(mech, clock)
        # Reader branché mécanisme → va observer la progression vers open_switch=True
        reader = MechanismFakeSwitchReader(mech)

        cfg = CimierConfig(
            enabled=True,
            verbose_logging=True,
            cycle_timeout_s=5.0,
            post_off_quiet_s=0.0,
            shelly_settle_s=0.0,
            motor_shelly=MotorShellyConfig(
                host_motor="203.0.113.85",
                host_dir="203.0.113.86",
                timer_safety_sec=90.0,
            ),
        )
        service = CimierService(
            cimier_config=cfg,
            power_switch=ps,
            motor_shelly=sim_motor,
            switch_reader=reader,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=advancing_sleep,
            cycle_poll_interval_s=0.05,
        )
        service.execute_command({"id": "verb1", "action": "open"})

        debug_polls = [r.message for r in caplog.records if "cimier_event=poll_status" in r.message]
        assert len(debug_polls) >= 2, "verbose : au moins 2 polls DEBUG attendus, got " + str(
            len(debug_polls)
        )

    def test_non_verbose_does_not_emit_poll_status(
        self,
        ipc_manager: RecordingIpcManager,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import logging as _logging

        # Forcer CIMIER_DEV_MODE absent pendant ce test
        monkeypatch.delenv("CIMIER_DEV_MODE", raising=False)
        caplog.set_level(_logging.DEBUG, logger="services.cimier_service")

        mech = CimierMechanismSim(initial_state="closed", full_travel_s=0.3)
        sim_motor = SimMotorShelly(mech)
        ps = CountingPowerSwitch()
        clock = MockClock()
        advancing_sleep = MechanismDrivingSleep(mech, clock)
        reader = MechanismFakeSwitchReader(mech)

        cfg = CimierConfig(
            enabled=True,
            verbose_logging=False,  # default
            cycle_timeout_s=5.0,
            post_off_quiet_s=0.0,
            shelly_settle_s=0.0,
            motor_shelly=MotorShellyConfig(
                host_motor="203.0.113.85",
                host_dir="203.0.113.86",
                timer_safety_sec=90.0,
            ),
        )
        service = CimierService(
            cimier_config=cfg,
            power_switch=ps,
            motor_shelly=sim_motor,
            switch_reader=reader,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=advancing_sleep,
            cycle_poll_interval_s=0.05,
        )
        service.execute_command({"id": "verb2", "action": "open"})

        debug_polls = [r.message for r in caplog.records if "cimier_event=poll_status" in r.message]
        assert len(debug_polls) == 0, "non-verbose : aucun poll_status attendu, got " + str(
            len(debug_polls)
        )

    def test_cimier_dev_mode_env_var_emits_poll_status_per_iteration(
        self,
        ipc_manager: RecordingIpcManager,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """CIMIER_DEV_MODE=1 sans verbose_logging dans config → DEBUG actif."""
        import logging as _logging

        monkeypatch.setenv("CIMIER_DEV_MODE", "1")
        caplog.set_level(_logging.DEBUG, logger="services.cimier_service")

        mech = CimierMechanismSim(initial_state="closed", full_travel_s=0.3)
        sim_motor = SimMotorShelly(mech)
        ps = CountingPowerSwitch()
        clock = MockClock()
        advancing_sleep = MechanismDrivingSleep(mech, clock)
        reader = MechanismFakeSwitchReader(mech)

        cfg = CimierConfig(
            enabled=True,
            verbose_logging=False,
            cycle_timeout_s=5.0,
            post_off_quiet_s=0.0,
            shelly_settle_s=0.0,
            motor_shelly=MotorShellyConfig(
                host_motor="203.0.113.85",
                host_dir="203.0.113.86",
                timer_safety_sec=90.0,
            ),
        )
        service = CimierService(
            cimier_config=cfg,
            power_switch=ps,
            motor_shelly=sim_motor,
            switch_reader=reader,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=advancing_sleep,
            cycle_poll_interval_s=0.05,
        )
        service.execute_command({"id": "verb3", "action": "open"})

        debug_polls = [r.message for r in caplog.records if "cimier_event=poll_status" in r.message]
        assert len(debug_polls) >= 2, (
            "CIMIER_DEV_MODE : au moins 2 polls DEBUG attendus, got " + str(len(debug_polls))
        )


# ======================================================================
# Section T7 Bloc 2 : Cycles bout-en-bout via FakeSwitchReader + mécanisme
#
# Remplace les tests T7 legacy (CimierSimulator HTTP réel) par une approche
# sans HTTP : MechanismFakeSwitchReader lit l'état de CimierMechanismSim
# directement. MechanismDrivingSleep avance le mécanisme + la clock virtuelle
# à chaque _sleep() côté service — comportement identique à l'ancien setup
# MechanismDrivingSleep + FakeSwitchReader, sans la couche réseau.
# ======================================================================


def _build_e2e_service(
    *,
    initial_state: str,
    ipc_manager: RecordingIpcManager,
    cycle_timeout_s: float = 5.0,
    post_off_quiet_s: float = 0.0,
    full_travel_s: float = 0.5,
    force_both_switches: bool = False,
    weather_provider: Optional[Any] = None,
    cycle_poll_interval_s: float = 0.05,
) -> Tuple[
    CimierService,
    CountingPowerSwitch,
    CimierMechanismSim,
    SimMotorShelly,
]:
    """Assemble le stack T7 : MechanismFakeSwitchReader + SimMotorShelly partageant
    un seul CimierMechanismSim. Retourne (service, ps, mech, sim_motor).

    MechanismDrivingSleep avance le mécanisme à chaque _sleep() côté service,
    ce qui permet au MechanismFakeSwitchReader de détecter la transition de fin
    de course de façon déterministe.

    Si ``force_both_switches=True``, instancie le mécanisme avec ce flag
    (utilisé pour le test "both switches bloque preflight").
    """
    mech = CimierMechanismSim(
        initial_state=initial_state,
        full_travel_s=full_travel_s,
        force_both_switches=force_both_switches,
    )
    sim_motor = SimMotorShelly(mech)
    reader = MechanismFakeSwitchReader(mech)
    clock = MockClock()
    advancing_sleep = MechanismDrivingSleep(mech, clock)

    cfg = CimierConfig(
        enabled=True,
        cycle_timeout_s=cycle_timeout_s,
        post_off_quiet_s=post_off_quiet_s,
        shelly_settle_s=0.0,
        power_switch=PowerSwitchConfig(type="noop"),
        motor_shelly=MotorShellyConfig(
            host_motor="203.0.113.85",
            host_dir="203.0.113.86",
            timer_safety_sec=90.0,
        ),
    )
    ps = CountingPowerSwitch()
    service = CimierService(
        cimier_config=cfg,
        power_switch=ps,
        motor_shelly=sim_motor,
        switch_reader=reader,
        ipc_manager=ipc_manager,
        clock=clock,
        sleep=advancing_sleep,
        weather_provider=weather_provider,
        cycle_poll_interval_s=cycle_poll_interval_s,
    )
    return service, ps, mech, sim_motor


class TestFullCycleViaMechanism:
    """Cycles bout-en-bout via FakeSwitchReader + CimierMechanismSim.

    Le mécanisme virtuel est partagé entre SimMotorShelly (pilote) et
    MechanismFakeSwitchReader (capteur) — ferme la boucle physique sans
    hardware ni couche HTTP.
    """

    def test_open_cycle_completes_state_open(self, ipc_manager: RecordingIpcManager) -> None:
        service, ps, mech, sim_motor = _build_e2e_service(
            initial_state="closed",
            ipc_manager=ipc_manager,
        )
        service.execute_command({"id": "s1", "action": "open"})

        # Mécanisme en butée ouverte.
        assert mech.open_switch is True, "mécanisme doit être en butée open"
        # power_on + power_off appelés une fois chacun.
        assert ps.on_count == 1
        assert ps.off_count == 1
        # Ordre Shelly : turn_off (défensif) / set_direction(True) / turn_on / ... / turn_off
        kinds = [c[0] for c in sim_motor.calls]
        assert kinds[0] == "turn_off"
        assert kinds[1] == "set_direction" and sim_motor.calls[1][1] is True
        assert kinds[2] == "turn_on"
        assert kinds[-1] == "turn_off"

    def test_close_cycle_completes_state_closed(self, ipc_manager: RecordingIpcManager) -> None:
        """Init open → cycle close → switch closed devient True."""
        service, ps, mech, sim_motor = _build_e2e_service(
            initial_state="open",
            ipc_manager=ipc_manager,
        )
        service.execute_command({"id": "s2", "action": "close"})

        assert mech.closed_switch is True
        assert ps.on_count == 1 and ps.off_count == 1
        kinds = [c[0] for c in sim_motor.calls]
        assert kinds[1] == "set_direction" and sim_motor.calls[1][1] is False

    def test_open_when_already_open_no_op(self, ipc_manager: RecordingIpcManager) -> None:
        """Garde-fou : init open → cycle open → preflight noop, 0 power_on."""
        service, ps, mech, sim_motor = _build_e2e_service(
            initial_state="open",
            ipc_manager=ipc_manager,
        )
        service.execute_command({"id": "s3", "action": "open"})

        # Garde-fou pré-vol : aucune action électrique.
        assert ps.on_count == 0
        assert ps.off_count == 0
        assert sim_motor.calls == []

    def test_close_when_already_closed_no_op(self, ipc_manager: RecordingIpcManager) -> None:
        """Symétrique : init closed → cycle close → noop preflight."""
        service, ps, mech, sim_motor = _build_e2e_service(
            initial_state="closed",
            ipc_manager=ipc_manager,
        )
        service.execute_command({"id": "s4", "action": "close"})

        assert ps.on_count == 0
        assert sim_motor.calls == []

    def test_cycle_timeout_publishes_error(self, ipc_manager: RecordingIpcManager) -> None:
        """Mécanisme ultra-lent (course 999s) + cycle_timeout_s=0.5 → cycle_timeout."""
        service, ps, mech, _sim_motor = _build_e2e_service(
            initial_state="closed",
            ipc_manager=ipc_manager,
            cycle_timeout_s=0.5,
            full_travel_s=999.0,
        )
        service.execute_command({"id": "s5", "action": "open"})

        # Invariant 220V : power_off appelé même sur timeout.
        assert ps.off_count == 1
        last = ipc_manager.history[-1]
        assert last["error_message"] == "cycle_timeout"
        assert last["state"] == STATE_ERROR

    def test_stop_command_during_polling_aborts_cycle(
        self, ipc_manager: RecordingIpcManager
    ) -> None:
        """Stop injecté pendant le polling → motor_off + power_off appelés."""
        service, ps, mech, sim_motor = _build_e2e_service(
            initial_state="closed",
            ipc_manager=ipc_manager,
            cycle_timeout_s=10.0,
            full_travel_s=5.0,  # Mouvement lent pour laisser le temps d'injecter le stop.
        )
        # Patcher _check_for_stop_command pour renvoyer un stop après N appels.
        call_count = {"n": 0}

        def stop_after_some_polls():
            call_count["n"] += 1
            if call_count["n"] >= 3:
                return {"id": "stop-during", "action": "stop"}
            return None

        service._check_for_stop_command = stop_after_some_polls

        service.execute_command({"id": "s6", "action": "open"})

        # power_off invariant.
        assert ps.off_count == 1
        # motor.turn_off appelé en cleanup (au moins 2 fois : défensif + cleanup).
        turn_off_calls = [c for c in sim_motor.calls if c[0] == "turn_off"]
        assert len(turn_off_calls) >= 2

    def test_cycle_end_logs_result_stopped_when_stop_during_polling(
        self, ipc_manager: RecordingIpcManager, caplog
    ) -> None:
        """Stop pendant polling → log cycle_end avec result=stopped (Bloc 3 dette T4)."""
        import logging as _logging

        service, ps, mech, _ = _build_e2e_service(
            initial_state="closed",
            ipc_manager=ipc_manager,
            cycle_timeout_s=10.0,
            full_travel_s=5.0,
        )
        call_count = {"n": 0}

        def stop_after_some_polls():
            call_count["n"] += 1
            if call_count["n"] >= 3:
                return {"id": "stop-during", "action": "stop"}
            return None

        service._check_for_stop_command = stop_after_some_polls

        with caplog.at_level(_logging.INFO, logger="services.cimier_service"):
            service.execute_command({"id": "s8", "action": "open"})

        # Cycle terminé par stop → log final result=stopped.
        cycle_end_records = [
            r for r in caplog.records if "cimier_event=cycle_end" in r.getMessage()
        ]
        assert len(cycle_end_records) == 1, (
            f"attendu 1 cycle_end, vu {len(cycle_end_records)} : "
            f"{[r.getMessage() for r in cycle_end_records]}"
        )
        assert "result=stopped" in cycle_end_records[0].getMessage(), (
            f"cycle_end devrait contenir result=stopped, vu : {cycle_end_records[0].getMessage()}"
        )

    def test_both_switches_blocks_preflight(self, ipc_manager: RecordingIpcManager) -> None:
        """CimierMechanismSim(force_both_switches=True) → preflight error."""
        service, ps, mech, sim_motor = _build_e2e_service(
            initial_state="closed",
            ipc_manager=ipc_manager,
            force_both_switches=True,
        )
        service.execute_command({"id": "s7", "action": "open"})

        # Garde-fou : 0 action électrique.
        assert ps.on_count == 0
        assert sim_motor.calls == []
        last = ipc_manager.history[-1]
        assert last["error_message"] == "both_switches_triggered"
        assert last["state"] == STATE_ERROR


# ======================================================================
# Section T7 Bloc 2 : WeatherProvider (via mécanisme)
# ======================================================================


class TestWeatherProviderViaMechanism:
    """Verrouille le log weather=... émis au démarrage d'un cycle."""

    def test_cycle_logs_weather_on_start(
        self,
        ipc_manager: RecordingIpcManager,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Le payload du WeatherProvider injecté doit apparaître dans le log
        cimier_event=cycle_start au format JSON."""
        import logging as _logging

        caplog.set_level(_logging.INFO, logger="services.cimier_service")

        class CustomWeatherProvider:
            def is_safe_to_open(self) -> bool:
                return True

            def is_safe_to_keep_open(self) -> bool:
                return True

            def describe(self) -> Dict[str, Any]:
                return {"source": "test", "wind_kph": 12, "rain": False}

        service, _ps, mech, _sim_motor = _build_e2e_service(
            initial_state="closed",
            ipc_manager=ipc_manager,
            weather_provider=CustomWeatherProvider(),
        )
        service.execute_command({"id": "w1", "action": "open"})

        cycle_starts = [
            r.message for r in caplog.records if "cimier_event=cycle_start" in r.message
        ]
        assert len(cycle_starts) == 1
        msg = cycle_starts[0]
        # JSON sort_keys=True → "rain" < "source" < "wind_kph" alphabétique
        assert '"source":"test"' in msg, (
            "weather payload should be serialized into cycle_start log: " + msg
        )
        assert '"wind_kph":12' in msg


# ======================================================================
# Veille pluie (2026-08)
# ======================================================================


class StubRainProtection:
    """Double de RainProtection : état pilotable, appels comptés."""

    def __init__(self, state="dry", armed=False):
        self.state = state
        self.armed = armed
        self.latched = False
        self.read_calls = 0

    def read_now(self):
        self.read_calls += 1
        return self.state

    def latch(self):
        self.latched = True

    def release(self):
        self.latched = False

    def is_safe_to_open(self):
        if not self.armed:
            return True
        return (not self.latched) and self.state == "dry"

    def is_safe_to_keep_open(self):
        if not self.armed:
            return True
        return self.state != "wet"

    def describe(self):
        return {
            "provider": "stub",
            "state": self.state,
            "armed": self.armed,
            "latched": self.latched,
        }


class RecordingCloser:
    """Capture les appels à la séquence de fermeture."""

    def __init__(self):
        self.calls = []

    def __call__(self, reason):
        self.calls.append(reason)
        return {"cimier_close_sent": True}


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
    """Service prêt pour la veille, avec un cimier observé ouvert ou fermé.

    ``config_path`` pointe par défaut sur un fichier absent : le rafraîchissement
    de l'armement depuis la config est alors inerte, et les tests ne dépendent
    pas du `data/config.json` de la machine.

    ``switch_reader`` remplace le reader par défaut (butées cohérentes avec
    ``cimier_open``) ; ``last_switches`` fixe les *dernières* butées observées,
    qui peuvent différer de ce que le reader répondra — c'est exactement la
    situation d'un service qui vient de redémarrer.
    """
    from core.config.config_loader import WeatherProviderConfig

    cfg = CimierConfig(
        enabled=True,
        weather_provider=WeatherProviderConfig(
            type="shelly_rain", host="1.2.3.4", watch_interval_s=watch_interval_s
        ),
    )
    ipc = CimierIpcManager(command_file=tmp_path / "cmd.json", status_file=tmp_path / "status.json")
    clock = MockClock()
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
    last_open, last_closed = (
        last_switches if last_switches is not None else (cimier_open, not cimier_open)
    )
    service._last_open_switch = last_open
    service._last_closed_switch = last_closed
    return service


class TestRainWatch:
    @pytest.fixture(autouse=True)
    def _isolate_night_journal(self, tmp_path, monkeypatch):
        """Le journal de nuit écrit dans tmp_path, jamais dans data/nights du dépôt."""
        from services import night_journal

        monkeypatch.setattr(night_journal, "DEFAULT_NIGHTS_DIR", tmp_path / "nights")

    def test_reads_the_sensor_on_each_tick(self, tmp_path):
        rain = StubRainProtection(state="dry")
        service = make_rain_service(tmp_path, rain)
        service.tick()
        assert rain.read_calls == 1

    def test_armed_rain_on_open_cimier_triggers_close(self, tmp_path):
        rain = StubRainProtection(state="wet", armed=True)
        service = make_rain_service(tmp_path, rain, cimier_open=True)
        closer = RecordingCloser()
        service._close_session_fn = closer
        service.tick()
        assert closer.calls == ["rain"]

    def test_armed_rain_latches_against_reopening(self, tmp_path):
        rain = StubRainProtection(state="wet", armed=True)
        service = make_rain_service(tmp_path, rain, cimier_open=True)
        service._close_session_fn = RecordingCloser()
        service.tick()
        assert rain.latched is True

    def test_disarmed_rain_does_not_close(self, tmp_path):
        rain = StubRainProtection(state="wet", armed=False)
        service = make_rain_service(tmp_path, rain, cimier_open=True)
        closer = RecordingCloser()
        service._close_session_fn = closer
        service.tick()
        assert closer.calls == []

    def test_disarmed_rain_logs_would_close(self, tmp_path, caplog):
        import logging

        rain = StubRainProtection(state="wet", armed=False)
        service = make_rain_service(tmp_path, rain, cimier_open=True)
        service._close_session_fn = RecordingCloser()
        with caplog.at_level(logging.INFO, logger="services.cimier_service"):
            service.tick()
        assert "rain_would_close" in caplog.text

    def test_closed_cimier_is_not_closed_again(self, tmp_path):
        rain = StubRainProtection(state="wet", armed=True)
        service = make_rain_service(tmp_path, rain, cimier_open=False)
        closer = RecordingCloser()
        service._close_session_fn = closer
        service.tick()
        assert closer.calls == []

    def test_unreachable_sensor_never_closes(self, tmp_path):
        rain = StubRainProtection(state="unreachable", armed=True)
        service = make_rain_service(tmp_path, rain, cimier_open=True)
        closer = RecordingCloser()
        service._close_session_fn = closer
        service.tick()
        assert closer.calls == []

    def test_partially_open_cimier_is_closed(self, tmp_path):
        """Terrain 20/08/2026, 15h47 : protection armée, pluie détectée, rien
        ne s'est fermé — Serge a fermé à la main.

        Le cimier était **entrouvert** (un cycle de fermeture stoppé à 15h08 —
        `close result=stopped`), donc aucune butée active, donc un état dérivé
        « unknown ». La garde exigeait « open » : l'état où il faut le plus
        fermer était précisément celui qui ne fermait pas.
        """
        rain = StubRainProtection(state="wet", armed=True)
        service = make_rain_service(
            tmp_path,
            rain,
            switch_reader=FakeSwitchReader([(False, False)]),
            last_switches=(False, False),
        )
        closer = RecordingCloser()
        service._close_session_fn = closer
        service.tick()
        assert closer.calls == ["rain"]

    def test_stale_switches_do_not_block_the_close(self, tmp_path):
        """Les butées ne sont lues qu'au cours d'un cycle : au repos elles
        datent du dernier cycle, et valent False/False au démarrage du service
        (que l'OTA redémarre désormais). Un cimier réellement ouvert ne doit
        pas être protégé par une connaissance périmée — on relit avant de
        décider."""
        rain = StubRainProtection(state="wet", armed=True)
        service = make_rain_service(
            tmp_path,
            rain,
            switch_reader=FakeSwitchReader([(True, False)]),
            last_switches=(False, False),
        )
        closer = RecordingCloser()
        service._close_session_fn = closer
        service.tick()
        assert closer.calls == ["rain"]

    def test_fresh_switch_read_avoids_a_useless_close(self, tmp_path):
        """Symétrique du précédent : le cimier est en réalité fermé, la
        dernière observation dit « ouvert ». Fermer coûterait un GOTO parking
        (la séquence de fermeture bouge la coupole) pour rien."""
        rain = StubRainProtection(state="wet", armed=True)
        service = make_rain_service(
            tmp_path,
            rain,
            switch_reader=FakeSwitchReader([(False, True)]),
            last_switches=(True, False),
        )
        closer = RecordingCloser()
        service._close_session_fn = closer
        service.tick()
        assert closer.calls == []

    def test_both_switches_anomaly_still_closes(self, tmp_path):
        """Deux butées actives = anomalie capteur. Sous la pluie, une anomalie
        ne vaut pas une autorisation à rester ouvert."""
        rain = StubRainProtection(state="wet", armed=True)
        service = make_rain_service(
            tmp_path,
            rain,
            switch_reader=FakeSwitchReader([(True, True)]),
            last_switches=(True, True),
        )
        closer = RecordingCloser()
        service._close_session_fn = closer
        service.tick()
        assert closer.calls == ["rain"]

    def test_unreadable_switches_still_close(self, tmp_path):
        """Butées injoignables : on ne sait pas, donc on ferme. (Le capteur de
        *pluie* injoignable, lui, ne ferme jamais — c'est l'autre bout du
        fail-safe, couvert par test_unreachable_sensor_never_closes.)"""
        rain = StubRainProtection(state="wet", armed=True)
        service = make_rain_service(
            tmp_path,
            rain,
            switch_reader=FakeSwitchReader(raise_error=SwitchReaderError("timeout")),
            last_switches=(False, False),
        )
        closer = RecordingCloser()
        service._close_session_fn = closer
        service.tick()
        assert closer.calls == ["rain"]

    def test_cooldown_defers_the_close_then_retries(self, tmp_path):
        """Mode Drop : une commande écrite pendant le cooldown serait consommée
        puis jetée. On ne ferme donc pas — mais on repasse au tour suivant."""
        rain = StubRainProtection(state="wet", armed=True)
        service = make_rain_service(
            tmp_path,
            rain,
            switch_reader=FakeSwitchReader([(True, False)]),
            last_switches=(True, False),
        )
        closer = RecordingCloser()
        service._close_session_fn = closer
        service._cooldown_end_ts = service._clock() + 10.0
        service.tick()
        assert closer.calls == []

        service._clock.advance(11.0)
        service.tick()
        assert closer.calls == ["rain"]

    def test_an_unclosed_cimier_is_retried(self, tmp_path):
        """La fermeture est best-effort : si le cimier n'est pas confirmé fermé
        et qu'il pleut toujours, la veille réessaie."""
        rain = StubRainProtection(state="wet", armed=True)
        service = make_rain_service(
            tmp_path,
            rain,
            switch_reader=FakeSwitchReader([(True, False)]),
            last_switches=(True, False),
        )
        closer = RecordingCloser()
        service._close_session_fn = closer
        service.tick()
        service.tick()
        assert closer.calls == ["rain", "rain"]

    def test_rain_that_commands_nothing_is_logged(self, tmp_path, caplog):
        """L'angle mort du 20/08 : la veille a vu la pluie, n'a rien fermé, et
        n'a écrit aucune ligne. Sur le log, « rien à fermer » et « la veille est
        morte » s'écrivaient identiquement — c'est-à-dire pas du tout."""
        import logging

        rain = StubRainProtection(state="wet", armed=True)
        service = make_rain_service(tmp_path, rain, cimier_open=False)
        service._close_session_fn = RecordingCloser()
        with caplog.at_level(logging.INFO, logger="services.cimier_service"):
            service.tick()
            service.tick()
        assert caplog.text.count("rain_close_skipped") == 1
        assert "already_closed" in caplog.text

    def test_rain_state_is_published_in_status(self, tmp_path):
        rain = StubRainProtection(state="wet", armed=False)
        service = make_rain_service(tmp_path, rain, cimier_open=True)
        service._close_session_fn = RecordingCloser()
        service.tick()
        payload = json.loads((tmp_path / "status.json").read_text())
        assert payload["rain"]["state"] == "wet"
        assert payload["rain"]["armed"] is False

    def test_rain_transition_is_written_to_night_journal(self, tmp_path, monkeypatch):
        from services import night_journal

        recorded = []
        monkeypatch.setattr(
            night_journal,
            "append_event",
            lambda event, **kw: recorded.append((event, kw)) or True,
        )
        rain = StubRainProtection(state="wet", armed=False)
        service = make_rain_service(tmp_path, rain, cimier_open=True)
        service._close_session_fn = RecordingCloser()
        service.tick()
        assert any(e == "rain" and kw.get("state") == "wet" for e, kw in recorded)

    def test_stable_state_is_not_journaled_twice(self, tmp_path, monkeypatch):
        from services import night_journal

        recorded = []
        monkeypatch.setattr(
            night_journal,
            "append_event",
            lambda event, **kw: recorded.append((event, kw)) or True,
        )
        rain = StubRainProtection(state="dry", armed=False)
        service = make_rain_service(tmp_path, rain, cimier_open=True)
        service.tick()
        service.tick()
        assert len([e for e, _ in recorded if e == "rain"]) == 1

    def test_would_close_is_journaled_once_per_episode(self, tmp_path, monkeypatch):
        # Le journal enregistre des transitions, pas des échantillons : une
        # averse de 6 h en mode observation ne doit pas écrire une ligne par
        # tour de veille (2 160 lignes en prod), sinon la frise est illisible.
        from services import night_journal

        recorded = []
        monkeypatch.setattr(
            night_journal,
            "append_event",
            lambda event, **kw: recorded.append((event, kw)) or True,
        )
        rain = StubRainProtection(state="wet", armed=False)
        service = make_rain_service(tmp_path, rain, cimier_open=True)
        service._close_session_fn = RecordingCloser()
        service.tick()
        service.tick()
        service.tick()
        assert len([e for e, _ in recorded if e == "decision"]) == 1

    def test_a_new_episode_is_journaled_again(self, tmp_path, monkeypatch):
        # Une éclaircie puis une reprise de pluie sont bien deux épisodes.
        from services import night_journal

        recorded = []
        monkeypatch.setattr(
            night_journal,
            "append_event",
            lambda event, **kw: recorded.append((event, kw)) or True,
        )
        rain = StubRainProtection(state="wet", armed=False)
        service = make_rain_service(tmp_path, rain, cimier_open=True)
        service._close_session_fn = RecordingCloser()
        service.tick()
        rain.state = "dry"
        service.tick()
        rain.state = "wet"
        service.tick()
        assert len([e for e, _ in recorded if e == "decision"]) == 2

    def test_would_close_is_logged_once_per_episode(self, tmp_path, caplog):
        import logging

        rain = StubRainProtection(state="wet", armed=False)
        service = make_rain_service(tmp_path, rain, cimier_open=True)
        service._close_session_fn = RecordingCloser()
        with caplog.at_level(logging.INFO, logger="services.cimier_service"):
            service.tick()
            service.tick()
        assert caplog.text.count("rain_would_close") == 1

    def test_noop_provider_disables_the_watch_entirely(self, tmp_path):
        # Rétro-compat : une config non migrée ne doit rien changer.
        from core.hardware.weather_provider import NoopWeatherProvider

        cfg = CimierConfig(enabled=True)
        ipc = CimierIpcManager(
            command_file=tmp_path / "cmd.json", status_file=tmp_path / "status.json"
        )
        service = CimierService(
            cimier_config=cfg,
            power_switch=NoopPowerSwitch(),
            motor_shelly=NoopMotorShelly(),
            switch_reader=FakeSwitchReader([(False, True)]),
            ipc_manager=ipc,
            weather_provider=NoopWeatherProvider(),
        )
        service.tick()
        payload = json.loads((tmp_path / "status.json").read_text())
        assert payload.get("rain") is None

    def test_manual_open_command_releases_the_latch(self, tmp_path):
        rain = StubRainProtection(state="dry", armed=True)
        service = make_rain_service(tmp_path, rain, cimier_open=False)
        rain.latch()
        service.execute_command({"id": "x1", "action": "open"})
        assert rain.latched is False

    def test_armed_flag_is_refreshed_from_config(self, tmp_path):
        """La case « Protection pluie » prend effet sans redémarrer le service."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"cimier": {"weather_provider": {"protection_enabled": True}}})
        )
        rain = StubRainProtection(state="dry", armed=False)
        service = make_rain_service(tmp_path, rain, config_path=config_file)
        service.tick()
        assert rain.armed is True

    def test_unreadable_config_leaves_the_armed_flag_untouched(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{ pas du json")
        rain = StubRainProtection(state="dry", armed=True)
        service = make_rain_service(tmp_path, rain, config_path=config_file)
        service._close_session_fn = RecordingCloser()
        service.tick()
        assert rain.armed is True

    def test_structurally_unexpected_config_does_not_break_the_watch(self, tmp_path):
        """Un config.json valide en JSON mais inattendu en structure.

        Le refresh est la première instruction du tour de veille : s'il levait,
        la lecture du capteur et la publication seraient perdues à chaque
        itération. On vérifie donc que le tour va jusqu'au bout.
        """
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"cimier": "pas un objet"}))
        rain = StubRainProtection(state="dry", armed=True)
        service = make_rain_service(tmp_path, rain, config_path=config_file)
        service._rain_watch_tick()
        assert rain.armed is True
        assert rain.read_calls == 1

    def test_config_root_not_an_object_does_not_break_the_watch(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(["pas", "un", "objet"]))
        rain = StubRainProtection(state="dry", armed=True)
        service = make_rain_service(tmp_path, rain, config_path=config_file)
        service._rain_watch_tick()
        assert rain.armed is True
        assert rain.read_calls == 1


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
        # La construction applique déjà l'état initial (armed=False → turn_off,
        # cf. test_initial_state_applied_at_construction_when_already_armed) :
        # on repart de zéro pour isoler la seule transition déclenchée par tick().
        heater.on_count = 0
        heater.off_count = 0
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
        # Idem : la construction a déjà appliqué armed=True → turn_on().
        heater.on_count = 0
        heater.off_count = 0
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

    def test_disarm_failure_does_not_block_disarming(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"cimier": {"weather_provider": {"protection_enabled": False}}})
        )
        heater = FailingOffPowerSwitch()
        rain = StubRainProtection(state="dry", armed=True)
        service = make_rain_service(
            tmp_path, rain, config_path=config_file, rain_heater_switch=heater
        )
        service.tick()
        assert rain.armed is False
        assert service._rain_heater_status["last_command_ok"] is False

    def test_noop_heater_switch_is_not_configured(self, tmp_path):
        rain = StubRainProtection(state="dry", armed=True)
        service = make_rain_service(tmp_path, rain)  # rain_heater_switch=None → noop
        assert service._rain_heater_configured is False
        assert service._rain_heater_status == {}

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

    def test_heater_status_published_even_without_rain_sensor(self, tmp_path):
        """Chauffage configuré mais AUCUN capteur de pluie réel (_rain_enabled=False,
        ex. NoopWeatherProvider en bring-up matériel partiel) : ``payload["rain"]``
        n'existe pas avant la ligne testée, elle doit être créée fraîche par le
        ``setdefault`` — pas planter en KeyError avec un index direct.
        """
        from core.hardware.weather_provider import NoopWeatherProvider

        heater = CountingPowerSwitch()
        cfg = CimierConfig(enabled=True, power_switch=PowerSwitchConfig(type="noop"))
        ipc = CimierIpcManager(
            command_file=tmp_path / "cmd.json", status_file=tmp_path / "status.json"
        )
        service = CimierService(
            cimier_config=cfg,
            power_switch=NoopPowerSwitch(),
            motor_shelly=NoopMotorShelly(),
            switch_reader=FakeSwitchReader([(False, False)]),
            rain_heater_switch=heater,
            ipc_manager=ipc,
            weather_provider=NoopWeatherProvider(),
            config_path=tmp_path / "absent.json",
        )
        assert service._rain_enabled is False
        service.tick()
        payload = json.loads((tmp_path / "status.json").read_text())
        assert payload["rain"] == {
            "heater": {
                "configured": True,
                "on": False,
                "last_command_ok": True,
                "error": None,
            }
        }


# ----------------------------------------------------------------------
# Intégration : veille câblée sur le vrai provider (pas de stub)
# ----------------------------------------------------------------------


class FakeRainShelly:
    """urlopen programmable — copié de tests/test_weather_provider.py.

    ``script`` = liste de bool (state renvoyé par Input.GetStatus) ; le dernier
    élément est répété une fois la liste épuisée.
    """

    def __init__(self, script):
        self._script = list(script)
        self.calls = []

    def __call__(self, url, timeout=None):
        self.calls.append(url)
        idx = min(len(self.calls) - 1, len(self._script) - 1)
        item = self._script[idx]
        return _FakeRainResp(('{"id":0,"state":%s}' % ("true" if item else "false")).encode())


class _FakeRainResp:
    def __init__(self, body, status=200):
        self._body = body
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestRainWatchWithRealProvider:
    @pytest.fixture(autouse=True)
    def _isolate_night_journal(self, tmp_path, monkeypatch):
        from services import night_journal

        monkeypatch.setattr(night_journal, "DEFAULT_NIGHTS_DIR", tmp_path / "nights")

    def test_real_provider_closes_on_first_wet_read(self, tmp_path):
        """La fermeture d'urgence part dès la première lecture mouillée.

        L'anti-rebond retardait auparavant la fermeture d'un tour de veille
        (``confirm_reads`` lectures concordantes exigées dans les deux sens).
        Terrain 16/08/2026 : sous une averse réelle, ce retard n'était pas
        d'un tour mais de plusieurs minutes, le capteur oscillant autour de son
        seuil sans jamais aligner deux lectures identiques. Entrer en « pluie »
        est désormais immédiat. Ce test rend la latence visible pour qu'elle ne
        change pas en silence.
        """
        from core.hardware.weather_provider import (
            RainProtection,
            ShellyRainWeatherProvider,
        )

        rain = RainProtection(
            ShellyRainWeatherProvider(host="1.2.3.4", urlopen=FakeRainShelly([True])),
            armed=True,
        )
        service = make_rain_service(tmp_path, rain, cimier_open=True)
        closer = RecordingCloser()
        service._close_session_fn = closer

        service.tick()
        assert closer.calls == ["rain"], "1er tour : pluie lue → fermeture d'urgence"
        assert rain.latched is True

    def test_flapping_sensor_does_not_delay_closing(self, tmp_path):
        """Le scénario terrain : lectures alternées à l'amorce de l'averse.

        L'ancien anti-rebond ne fermait jamais dans ce cas — le compteur de
        lectures concordantes repartait de zéro à chaque oscillation.
        """
        from core.hardware.weather_provider import (
            RainProtection,
            ShellyRainWeatherProvider,
        )

        rain = RainProtection(
            ShellyRainWeatherProvider(
                host="1.2.3.4", urlopen=FakeRainShelly([False, True, False, True])
            ),
            armed=True,
        )
        service = make_rain_service(tmp_path, rain, cimier_open=True)
        closer = RecordingCloser()
        service._close_session_fn = closer

        service.tick()
        assert closer.calls == [], "capteur sec : rien ne bouge"
        service.tick()
        assert closer.calls == ["rain"], "1re lecture mouillée → fermeture, sans attendre"


class TestCimierCycleJournaling:
    def test_preflight_noop_is_written_to_night_journal(self, tmp_path, monkeypatch):
        from services import night_journal

        recorded = []
        monkeypatch.setattr(
            night_journal,
            "append_event",
            lambda event, **kw: recorded.append((event, kw)) or True,
        )
        cfg = CimierConfig(enabled=True)
        ipc = CimierIpcManager(
            command_file=tmp_path / "cmd.json", status_file=tmp_path / "status.json"
        )
        service = CimierService(
            cimier_config=cfg,
            power_switch=NoopPowerSwitch(),
            motor_shelly=NoopMotorShelly(),
            # Déjà fermé → preflight noop, cycle court sans matériel.
            switch_reader=FakeSwitchReader([(False, True)]),
            ipc_manager=ipc,
        )
        service.execute_command({"id": "c1", "action": "close"})
        cimier_events = [kw for e, kw in recorded if e == "cimier"]
        assert cimier_events
        assert cimier_events[-1]["action"] == "close"
        assert cimier_events[-1]["result"] == "noop"

    def test_nominal_cycle_end_is_written_to_night_journal(
        self, ipc_manager: RecordingIpcManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Le chemin réellement emprunté à chaque ouverture/fermeture (branche
        ``finally``) : c'est celui-là, pas le préflight ``noop`` ci-dessus, qui
        alimente la frise de restitution (Tasks 13-14) avec l'état du cimier.

        Montage identique à
        ``TestOrchestrationLogging.test_full_open_cycle_publishes_expected_events``
        (mécanisme simulé + horloge simulée) — seul le point de vérification
        change : ici on observe le journal de nuit, pas les logs.
        """
        from services import night_journal

        recorded = []
        monkeypatch.setattr(
            night_journal,
            "append_event",
            lambda event, **kw: recorded.append((event, kw)) or True,
        )

        mech = CimierMechanismSim(initial_state="closed", full_travel_s=0.5)
        sim_motor = SimMotorShelly(mech)
        ps = CountingPowerSwitch()
        clock = MockClock()
        advancing_sleep = MechanismDrivingSleep(mech, clock)
        reader = MechanismFakeSwitchReader(mech)

        cfg = CimierConfig(
            enabled=True,
            cycle_timeout_s=5.0,
            post_off_quiet_s=0.0,
            shelly_settle_s=0.0,
            motor_shelly=MotorShellyConfig(
                host_motor="203.0.113.85",
                host_dir="203.0.113.86",
                timer_safety_sec=90.0,
            ),
        )
        service = CimierService(
            cimier_config=cfg,
            power_switch=ps,
            motor_shelly=sim_motor,
            switch_reader=reader,
            ipc_manager=ipc_manager,
            clock=clock,
            sleep=advancing_sleep,
            cycle_poll_interval_s=0.05,
        )
        service.execute_command({"id": "ev1", "action": "open"})

        cimier_events = [kw for e, kw in recorded if e == "cimier"]
        assert cimier_events
        assert cimier_events[-1]["action"] == "open"
        assert cimier_events[-1]["result"] == "ok"


class TestServiceLogHandlers:
    """Traces pluie accessibles sans SSH (retour terrain 16/08/2026).

    En production `cimier_service` est un service systemd sans FileHandler :
    tout partait dans journald, donc rien dans `logs/` — l'opérateur qui zippe
    ce répertoire ne trouvait aucune trace du capteur de pluie.
    """

    def test_prod_adds_rotating_file_handler_in_logs_dir(self, tmp_path, monkeypatch):
        import logging.handlers

        from services import cimier_service

        monkeypatch.delenv("CIMIER_DEV_MODE", raising=False)
        monkeypatch.setattr(cimier_service, "LOG_DIR", tmp_path / "logs")

        handlers = cimier_service._build_log_handlers()

        file_handlers = [h for h in handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(file_handlers) == 1
        assert Path(file_handlers[0].baseFilename).name == "cimier_service.log"
        for h in handlers:
            h.close()

    def test_dev_mode_keeps_stdout_only(self, tmp_path, monkeypatch):
        """start_dev.sh redirige déjà stdout vers logs/cimier_service.log :
        un FileHandler y écrirait chaque ligne en double."""
        import logging.handlers

        from services import cimier_service

        monkeypatch.setenv("CIMIER_DEV_MODE", "1")
        monkeypatch.setattr(cimier_service, "LOG_DIR", tmp_path / "logs")

        handlers = cimier_service._build_log_handlers()

        assert not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in handlers)
        assert len(handlers) == 1

    def test_unwritable_log_dir_does_not_prevent_startup(self, tmp_path, monkeypatch):
        """Un `logs/` non écrivable ne doit jamais empêcher la protection
        pluie de tourner : on perd la trace, pas le service."""
        from services import cimier_service

        monkeypatch.delenv("CIMIER_DEV_MODE", raising=False)
        blocker = tmp_path / "blocker"
        blocker.write_text("je ne suis pas un répertoire")
        monkeypatch.setattr(cimier_service, "LOG_DIR", blocker / "logs")

        handlers = cimier_service._build_log_handlers()

        assert len(handlers) == 1
