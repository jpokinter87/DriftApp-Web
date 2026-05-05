"""Tests pour core/hardware/calibration_routine.py (v6.4 Phase 2).

Couvre AC-1 à AC-6 du plan v6.4-02-01 :
- Mode simulation → skip propre.
- Hint présent → trajet court vers 45° + overshoot dans la même direction.
- Hint absent ou divergent → fallback sweep ±15°.
- Timeout de sécurité → request_stop + degraded.
- Wraparound 0/360 (hint=359° et hint=5°).
- Callback non bloquant.

Pas de hardware réel (lgpio, pyserial) : tout est mocké via FakeDaemonReader +
ResponsiveMoteur synchronisés par threading.Event pour des tests déterministes.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import FrozenInstanceError
from pathlib import Path
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

    def __init__(self, angle: float = 50.0, calib_at=None):
        self._lock = threading.Lock()
        self._angle = angle
        self._calib_at = calib_at
        self._read_angle_raises = False

    def set_calib(self, ts):
        with self._lock:
            self._calib_at = ts

    def fail_read_angle(self) -> None:
        self._read_angle_raises = True

    def read_angle(self, timeout_ms: int = 200, **kwargs) -> float:
        if self._read_angle_raises:
            raise RuntimeError("daemon stale")
        with self._lock:
            return self._angle

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
        overshoot_deg=5.0,
        fallback_sweep_deg=15.0,
        timeout_sec=2.0,
        poll_interval_sec=0.005,
    )


@pytest.fixture
def fast_config():
    """Timeout court pour tester les chemins dégradés."""
    return BootCalibrationConfig(
        overshoot_deg=5.0,
        fallback_sweep_deg=15.0,
        timeout_sec=0.2,
        poll_interval_sec=0.005,
    )


@pytest.fixture
def callback_recorder():
    return MagicMock()


# =============================================================================
# HELPERS
# =============================================================================

def _persist_path(tmp_path: Path) -> Path:
    return tmp_path / "last_known_position.json"


def _write_hint(tmp_path: Path, azimut: float,
                saved_at: str = "2026-05-04T11:00:00+00:00") -> Path:
    p = _persist_path(tmp_path)
    p.write_text(json.dumps({"azimut_deg": azimut, "saved_at": saved_at}))
    return p


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
    tmp_path: Path,
    config,
    callback,
    moteur,
    daemon,
    simulation_mode: bool = False,
) -> CalibrationRoutine:
    return CalibrationRoutine(
        moteur=moteur,
        daemon_reader=daemon,
        persist_path=_persist_path(tmp_path),
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
            method="hint_trip",
            last_calibration_at="2026-05-04T12:00:00+00:00",
            duration_sec=1.0,
        )
        with pytest.raises(FrozenInstanceError):
            result.status = "degraded"  # type: ignore[misc]

    def test_dataclass_default_error_msg(self):
        result = CalibrationResult(
            status="ok",
            method="hint_trip",
            last_calibration_at="ts",
            duration_sec=1.0,
        )
        assert result.error_msg is None


# =============================================================================
# TestSimulationMode
# =============================================================================

class TestSimulationMode:

    def test_simulation_mode_returns_simulated(self, tmp_path, default_config, callback_recorder):
        moteur = ResponsiveMoteur()
        daemon = FakeDaemonReader()
        routine = _build_routine(
            tmp_path=tmp_path,
            config=default_config,
            callback=callback_recorder,
            moteur=moteur,
            daemon=daemon,
            simulation_mode=True,
        )
        result = routine.run()
        assert result.status == "simulated"
        assert result.method == "skipped_simulation"
        assert moteur.rotation.call_count == 0
        assert moteur.request_stop.call_count == 0


# =============================================================================
# TestHintTripHappyPath
# =============================================================================

class TestHintTripHappyPath:

    def test_hint_present_trip_calibrates(self, tmp_path, default_config, callback_recorder):
        """Hint=50.0, current=50.2 → delta≈-5.2 + overshoot -5 ≈ -10.2°."""
        moteur = ResponsiveMoteur(max_block_sec=0.5)
        daemon = FakeDaemonReader(angle=50.2, calib_at="BASELINE")
        _write_hint(tmp_path, 50.0)
        _trigger_calib_after(daemon, 0.05, ts="2026-05-04T12:00:00+00:00")

        routine = _build_routine(
            tmp_path=tmp_path, config=default_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon,
        )
        result = routine.run()

        assert result.status == "ok"
        assert result.method == "hint_trip"
        assert result.last_calibration_at == "2026-05-04T12:00:00+00:00"
        assert moteur.rotation.call_count == 1
        called_delta = moteur.rotation.call_args.args[0]
        assert called_delta < 0
        assert -11.0 < called_delta < -10.0

    def test_hint_trip_overshoot_direction(self, tmp_path, default_config, callback_recorder):
        """Hint=40°, current=40 → delta=+5° + overshoot +5 ≈ +10°."""
        moteur = ResponsiveMoteur(max_block_sec=0.5)
        daemon = FakeDaemonReader(angle=40.0, calib_at="BASELINE")
        _write_hint(tmp_path, 40.0)
        _trigger_calib_after(daemon, 0.05)

        routine = _build_routine(
            tmp_path=tmp_path, config=default_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon,
        )
        result = routine.run()

        assert result.status == "ok"
        called_delta = moteur.rotation.call_args.args[0]
        assert called_delta > 0
        assert 9.5 < called_delta < 10.5

    def test_hint_trip_calibration_stops_motor(self, tmp_path, default_config, callback_recorder):
        moteur = ResponsiveMoteur(max_block_sec=0.5)
        daemon = FakeDaemonReader(angle=50.0, calib_at="BASELINE")
        _write_hint(tmp_path, 50.0)
        _trigger_calib_after(daemon, 0.05)

        routine = _build_routine(
            tmp_path=tmp_path, config=default_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon,
        )
        result = routine.run()

        assert result.status == "ok"
        assert moteur.request_stop.call_count >= 1


# =============================================================================
# TestFallbackSweep
# =============================================================================

class TestFallbackSweep:

    def test_no_hint_triggers_fallback(self, tmp_path, default_config, callback_recorder):
        """Pas de fichier hint → skip phase 1 → fallback exécuté."""
        moteur = ResponsiveMoteur(max_block_sec=0.05)
        daemon = FakeDaemonReader(angle=50.0, calib_at="BASELINE")

        routine = _build_routine(
            tmp_path=tmp_path, config=default_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon,
        )
        result = routine.run()

        assert result.status == "degraded"
        assert result.method == "fallback_sweep"
        # 2 branches sweep tentées
        assert moteur.rotation.call_count == 2

    def test_hint_trip_failure_triggers_fallback(self, tmp_path, default_config, callback_recorder):
        """Trip hint sans calibration → fallback exécuté."""
        moteur = ResponsiveMoteur(max_block_sec=0.05)
        daemon = FakeDaemonReader(angle=50.0, calib_at="BASELINE")
        _write_hint(tmp_path, 50.0)

        routine = _build_routine(
            tmp_path=tmp_path, config=default_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon,
        )
        result = routine.run()

        assert result.status == "degraded"
        assert result.method == "fallback_sweep"
        # 1 trip + 2 sweep branches = 3 rotations
        assert moteur.rotation.call_count == 3

    def test_fallback_first_branch_calibrates(self, tmp_path, default_config, callback_recorder):
        """Sans hint, sweep -15° calibre dès la 1ère branche."""
        moteur = ResponsiveMoteur(max_block_sec=0.5)
        daemon = FakeDaemonReader(angle=50.0, calib_at=None)
        _trigger_calib_after(daemon, 0.05)

        routine = _build_routine(
            tmp_path=tmp_path, config=default_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon,
        )
        result = routine.run()

        assert result.status == "ok"
        assert result.method == "fallback_sweep"
        # Seule la 1ère branche du sweep est appelée
        assert moteur.rotation.call_count == 1
        called_delta = moteur.rotation.call_args.args[0]
        assert called_delta < 0  # première branche = -sweep

    def test_fallback_complete_failure(self, tmp_path, default_config, callback_recorder):
        """Sweep complet sans calibration → degraded."""
        moteur = ResponsiveMoteur(max_block_sec=0.05)
        daemon = FakeDaemonReader(angle=50.0, calib_at=None)

        routine = _build_routine(
            tmp_path=tmp_path, config=default_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon,
        )
        result = routine.run()

        assert result.status == "degraded"
        assert result.method == "fallback_sweep"
        assert result.error_msg is not None
        assert moteur.rotation.call_count == 2


# =============================================================================
# TestTimeout
# =============================================================================

class TestTimeout:

    def test_timeout_triggers_stop(self, tmp_path, fast_config, callback_recorder):
        """timeout_sec=0.2, rotation block 1s → watcher détecte timeout, request_stop appelé."""
        moteur = ResponsiveMoteur(max_block_sec=1.0)
        daemon = FakeDaemonReader(angle=50.0, calib_at="BASELINE")
        _write_hint(tmp_path, 50.0)

        routine = _build_routine(
            tmp_path=tmp_path, config=fast_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon,
        )
        t0 = time.monotonic()
        result = routine.run()
        elapsed = time.monotonic() - t0

        assert result.status == "degraded"
        assert "timeout" in (result.error_msg or "").lower()
        assert moteur.request_stop.call_count >= 1
        assert elapsed < fast_config.timeout_sec * 4

    def test_timeout_does_not_overshoot(self, tmp_path, fast_config, callback_recorder):
        """Durée totale bornée même si rotation simule un mouvement très long."""
        moteur = ResponsiveMoteur(max_block_sec=2.0)
        daemon = FakeDaemonReader(angle=50.0, calib_at="BASELINE")
        _write_hint(tmp_path, 50.0)

        routine = _build_routine(
            tmp_path=tmp_path, config=fast_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon,
        )
        t0 = time.monotonic()
        routine.run()
        elapsed = time.monotonic() - t0

        assert elapsed < fast_config.timeout_sec * 4


# =============================================================================
# TestEdgeCases
# =============================================================================

class TestEdgeCases:

    def test_daemon_reader_unavailable_falls_back(self, tmp_path, default_config, callback_recorder):
        """read_angle raise → _attempt_hint_trip skip → fallback exécuté."""
        moteur = ResponsiveMoteur(max_block_sec=0.05)
        daemon = FakeDaemonReader(angle=50.0, calib_at="BASELINE")
        daemon.fail_read_angle()
        _write_hint(tmp_path, 50.0)

        routine = _build_routine(
            tmp_path=tmp_path, config=default_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon,
        )
        result = routine.run()

        assert result.method == "fallback_sweep"

    def test_persistor_load_corrupt_returns_none(self, tmp_path, default_config, callback_recorder):
        """Hint file corrompu → load_last_position retourne None → fallback direct."""
        moteur = ResponsiveMoteur(max_block_sec=0.05)
        daemon = FakeDaemonReader(angle=50.0, calib_at="BASELINE")
        _persist_path(tmp_path).write_text("{not json")

        routine = _build_routine(
            tmp_path=tmp_path, config=default_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon,
        )
        result = routine.run()

        assert result.method == "fallback_sweep"

    def test_status_callback_invoked(self, tmp_path, default_config, callback_recorder):
        """Le callback reçoit step=loading_hint au minimum."""
        moteur = ResponsiveMoteur(max_block_sec=0.05)
        daemon = FakeDaemonReader(angle=50.0, calib_at="BASELINE")

        routine = _build_routine(
            tmp_path=tmp_path, config=default_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon,
        )
        routine.run()

        states = [c.args[0] for c in callback_recorder.call_args_list]
        steps = [c.args[1].get("step") for c in callback_recorder.call_args_list]
        assert all(s == "calibrating" for s in states)
        assert "loading_hint" in steps
        assert "fallback_sweep" in steps

    def test_callback_exception_does_not_crash_routine(self, tmp_path, default_config):
        """Une exception du callback ne casse pas la routine."""
        moteur = ResponsiveMoteur(max_block_sec=0.05)
        daemon = FakeDaemonReader(angle=50.0, calib_at="BASELINE")
        bad_cb = MagicMock(side_effect=RuntimeError("boom"))

        routine = _build_routine(
            tmp_path=tmp_path, config=default_config, callback=bad_cb,
            moteur=moteur, daemon=daemon,
        )
        result = routine.run()

        assert result.status in ("ok", "degraded")


# =============================================================================
# TestAngleWrap
# =============================================================================

class TestAngleWrap:

    def test_wrap_around_359_to_45(self, tmp_path, default_config, callback_recorder):
        """hint=359° → shortest_angular_distance(359, 45) = +46° → trip_total ≈ +51°."""
        moteur = ResponsiveMoteur(max_block_sec=0.5)
        daemon = FakeDaemonReader(angle=359.0, calib_at="BASELINE")
        _write_hint(tmp_path, 359.0)
        _trigger_calib_after(daemon, 0.05)

        routine = _build_routine(
            tmp_path=tmp_path, config=default_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon,
        )
        result = routine.run()

        assert result.status == "ok"
        called_delta = moteur.rotation.call_args.args[0]
        assert called_delta > 0
        assert 50.5 < called_delta < 51.5

    def test_wrap_around_5_to_45(self, tmp_path, default_config, callback_recorder):
        """hint=5° → shortest_angular_distance(5, 45) = +40° → trip_total ≈ +45°."""
        moteur = ResponsiveMoteur(max_block_sec=0.5)
        daemon = FakeDaemonReader(angle=5.0, calib_at="BASELINE")
        _write_hint(tmp_path, 5.0)
        _trigger_calib_after(daemon, 0.05)

        routine = _build_routine(
            tmp_path=tmp_path, config=default_config, callback=callback_recorder,
            moteur=moteur, daemon=daemon,
        )
        result = routine.run()

        assert result.status == "ok"
        called_delta = moteur.rotation.call_args.args[0]
        assert 44.5 < called_delta < 45.5


# =============================================================================
# TestModuleConstants
# =============================================================================

class TestModuleConstants:

    def test_switch_calib_angle_is_45(self):
        assert SWITCH_CALIB_ANGLE == 45.0
