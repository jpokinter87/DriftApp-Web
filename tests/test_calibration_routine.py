"""Tests pour core/hardware/calibration_routine.py (v6.6.0).

Couvre les chemins de la routine simplifiée :
- Mode simulation → skip propre.
- Sweep court calibre (1ère ou 2ème branche).
- Sweep complet sans calibration → degraded.
- Timeout de sécurité → request_stop + degraded.
- Callback non bloquant + tolérance exception.

Pas de hardware réel (lgpio, pyserial) : tout est mocké via FakeDaemonReader +
ResponsiveMoteur synchronisés par threading.Event pour des tests déterministes.
"""

from __future__ import annotations

import threading
import time
from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock

import pytest

from core.config.config_loader import BootCalibrationConfig
from core.hardware.calibration_routine import (
    SWITCH_CALIB_ANGLE,
    CalibrationResult,
    CalibrationRoutine,
)


# =============================================================================
# FAKES
# =============================================================================

class FakeDaemonReader:
    """Daemon reader stub thread-safe pour tests routine."""

    def __init__(self, calib_at=None):
        self._lock = threading.Lock()
        self._calib_at = calib_at

    def set_calib(self, ts):
        with self._lock:
            self._calib_at = ts

    def read_status(self):
        with self._lock:
            return {"last_calibration_at": self._calib_at}


class ResponsiveMoteur:
    """Mock moteur dont rotation() bloque jusqu'à request_stop() ou timeout interne."""

    def __init__(self, max_block_sec: float = 0.5):
        self._stop_event = threading.Event()
        self.max_block_sec = max_block_sec
        self.rotation = MagicMock(side_effect=self._rotate)
        self.request_stop = MagicMock(side_effect=self._stop)

    def _rotate(self, *args, **kwargs):
        self._stop_event.wait(timeout=self.max_block_sec)
        self._stop_event.clear()

    def _stop(self):
        self._stop_event.set()


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def default_config():
    return BootCalibrationConfig(
        fallback_sweep_deg=7.0,
        timeout_sec=2.0,
        poll_interval_sec=0.005,
    )


@pytest.fixture
def fast_config():
    """Timeout court pour tester les chemins dégradés."""
    return BootCalibrationConfig(
        fallback_sweep_deg=7.0,
        timeout_sec=0.2,
        poll_interval_sec=0.005,
    )


@pytest.fixture
def callback_recorder():
    return MagicMock()


# =============================================================================
# HELPERS
# =============================================================================

def _trigger_calib_after(
    daemon: FakeDaemonReader,
    delay_sec: float,
    ts: str = "2026-05-04T12:00:00+00:00",
) -> threading.Thread:
    """Programme un changement de last_calibration_at après `delay_sec`."""

    def fire():
        time.sleep(delay_sec)
        daemon.set_calib(ts)

    t = threading.Thread(target=fire, daemon=True)
    t.start()
    return t


def _build_routine(
    *,
    config,
    callback,
    moteur,
    daemon,
    simulation_mode: bool = False,
) -> CalibrationRoutine:
    return CalibrationRoutine(
        moteur=moteur,
        daemon_reader=daemon,
        config=config,
        simulation_mode=simulation_mode,
        status_callback=callback,
    )


# =============================================================================
# TestCalibrationResult
# =============================================================================

class TestCalibrationResult:

    def test_dataclass_frozen(self):
        result = CalibrationResult(
            status="ok",
            method="sweep",
            last_calibration_at="2026-05-04T12:00:00+00:00",
            duration_sec=1.0,
        )
        with pytest.raises(FrozenInstanceError):
            result.status = "degraded"  # type: ignore[misc]

    def test_dataclass_default_error_msg(self):
        result = CalibrationResult(
            status="ok",
            method="sweep",
            last_calibration_at="ts",
            duration_sec=1.0,
        )
        assert result.error_msg is None


# =============================================================================
# TestSimulationMode
# =============================================================================

class TestSimulationMode:

    def test_simulation_mode_returns_simulated(self, default_config, callback_recorder):
        moteur = ResponsiveMoteur()
        daemon = FakeDaemonReader()
        routine = _build_routine(
            config=default_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon, simulation_mode=True,
        )
        result = routine.run()
        assert result.status == "simulated"
        assert result.method == "skipped_simulation"
        assert moteur.rotation.call_count == 0
        assert moteur.request_stop.call_count == 0


# =============================================================================
# TestSweep
# =============================================================================

class TestSweep:

    def test_first_branch_calibrates(self, default_config, callback_recorder):
        """Sweep -7° calibre dès la 1ère branche."""
        moteur = ResponsiveMoteur(max_block_sec=0.5)
        daemon = FakeDaemonReader(calib_at=None)
        _trigger_calib_after(daemon, 0.05)

        routine = _build_routine(
            config=default_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon,
        )
        result = routine.run()

        assert result.status == "ok"
        assert result.method == "sweep"
        # Seule la 1ère branche du sweep est appelée
        assert moteur.rotation.call_count == 1
        called_delta = moteur.rotation.call_args.args[0]
        assert called_delta < 0  # première branche = -sweep
        assert abs(called_delta + default_config.fallback_sweep_deg) < 0.01

    def test_second_branch_calibrates(self, default_config, callback_recorder):
        """1ère branche n'arrive pas à calibrer, 2ème branche y arrive."""
        moteur = ResponsiveMoteur(max_block_sec=0.05)
        daemon = FakeDaemonReader(calib_at=None)

        def fire_during_second_branch():
            time.sleep(0.07)
            daemon.set_calib("2026-05-04T12:00:00+00:00")

        t = threading.Thread(target=fire_during_second_branch, daemon=True)
        t.start()

        routine = _build_routine(
            config=default_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon,
        )
        result = routine.run()

        assert result.status == "ok"
        assert result.method == "sweep"
        assert moteur.rotation.call_count == 2
        # 2ème branche est +2*sweep
        second_delta = moteur.rotation.call_args_list[1].args[0]
        assert second_delta > 0
        assert abs(second_delta - 2.0 * default_config.fallback_sweep_deg) < 0.01

    def test_sweep_complete_failure(self, default_config, callback_recorder):
        """Sweep complet sans calibration → degraded."""
        moteur = ResponsiveMoteur(max_block_sec=0.05)
        daemon = FakeDaemonReader(calib_at=None)

        routine = _build_routine(
            config=default_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon,
        )
        result = routine.run()

        assert result.status == "degraded"
        assert result.method == "sweep"
        assert result.error_msg is not None
        assert moteur.rotation.call_count == 2

    def test_sweep_stops_motor_on_calibration(self, default_config, callback_recorder):
        """Détection transition → request_stop appelé."""
        moteur = ResponsiveMoteur(max_block_sec=0.5)
        daemon = FakeDaemonReader(calib_at=None)
        _trigger_calib_after(daemon, 0.05)

        routine = _build_routine(
            config=default_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon,
        )
        result = routine.run()

        assert result.status == "ok"
        assert moteur.request_stop.call_count >= 1


# =============================================================================
# TestTimeout
# =============================================================================

class TestTimeout:

    def test_timeout_triggers_stop(self, fast_config, callback_recorder):
        """timeout_sec=0.2, rotation block 1s → watcher détecte timeout, request_stop appelé."""
        moteur = ResponsiveMoteur(max_block_sec=1.0)
        daemon = FakeDaemonReader(calib_at="BASELINE")

        routine = _build_routine(
            config=fast_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon,
        )
        t0 = time.monotonic()
        result = routine.run()
        elapsed = time.monotonic() - t0

        assert result.status == "degraded"
        assert "timeout" in (result.error_msg or "").lower()
        assert moteur.request_stop.call_count >= 1
        assert elapsed < fast_config.timeout_sec * 4

    def test_timeout_does_not_overshoot(self, fast_config, callback_recorder):
        """Durée totale bornée même si rotation simule un mouvement très long."""
        moteur = ResponsiveMoteur(max_block_sec=2.0)
        daemon = FakeDaemonReader(calib_at="BASELINE")

        routine = _build_routine(
            config=fast_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon,
        )
        t0 = time.monotonic()
        routine.run()
        elapsed = time.monotonic() - t0

        assert elapsed < fast_config.timeout_sec * 4


# =============================================================================
# TestCallback
# =============================================================================

class TestCallback:

    def test_status_callback_invoked(self, default_config, callback_recorder):
        """Le callback reçoit step=sweep."""
        moteur = ResponsiveMoteur(max_block_sec=0.05)
        daemon = FakeDaemonReader(calib_at=None)

        routine = _build_routine(
            config=default_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon,
        )
        routine.run()

        states = [c.args[0] for c in callback_recorder.call_args_list]
        steps = [c.args[1].get("step") for c in callback_recorder.call_args_list]
        assert all(s == "calibrating" for s in states)
        assert "sweep" in steps

    def test_callback_exception_does_not_crash_routine(self, default_config):
        """Une exception du callback ne casse pas la routine."""
        moteur = ResponsiveMoteur(max_block_sec=0.05)
        daemon = FakeDaemonReader(calib_at=None)
        bad_cb = MagicMock(side_effect=RuntimeError("boom"))

        routine = _build_routine(
            config=default_config, callback=bad_cb,
            moteur=moteur, daemon=daemon,
        )
        result = routine.run()

        assert result.status in ("ok", "degraded")


# =============================================================================
# TestModuleConstants
# =============================================================================

class TestModuleConstants:

    def test_switch_calib_angle_is_45(self):
        assert SWITCH_CALIB_ANGLE == 45.0
