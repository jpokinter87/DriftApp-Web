"""Calibration forcée côté démon encodeur (v6.20).

Le démon importe ``lgpio`` au chargement : on le remplace par un stub le temps
du test pour pouvoir instancier ``EMS22Daemon`` hors Raspberry Pi.
"""

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def daemon_module():
    lgpio_stub = MagicMock()
    lgpio_stub.gpio_read.return_value = 1  # switch relâché
    with patch.dict(sys.modules, {"lgpio": lgpio_stub}):
        sys.modules.pop("ems22d_calibrated", None)
        module = importlib.import_module("ems22d_calibrated")
        yield module
        sys.modules.pop("ems22d_calibrated", None)


def test_calib_request_is_acknowledged_without_touching_position(daemon_module):
    """La requête CALIB est acquittée par OK ; le recalage attend la boucle principale."""
    daemon = daemon_module.EMS22Daemon()
    counts_before = daemon.total_counts

    assert daemon.handle_request("CALIB") == b"OK\n"
    assert daemon.total_counts == counts_before
    assert daemon.calibrated is False


def test_forced_recalibration_sets_45_and_publishes_timestamp(daemon_module):
    """Appliqué par la boucle : angle recalé à 45°, calibré, horodaté."""
    daemon = daemon_module.EMS22Daemon()
    daemon.handle_request("CALIB")

    angle = daemon.apply_pending_forced_calibration(123.0)

    assert angle == daemon_module.SWITCH_CALIB_ANGLE
    assert daemon.calibrated is True
    assert daemon.last_calibration_at is not None
    # total_counts cohérent : la lecture suivante sans mouvement redonne 45°.
    daemon.prev_raw = 500
    assert daemon.raw_to_calibrated(500) == pytest.approx(45.0, abs=0.5)


def test_no_pending_request_leaves_angle_untouched(daemon_module):
    daemon = daemon_module.EMS22Daemon()
    assert daemon.apply_pending_forced_calibration(123.0) == 123.0
    assert daemon.calibrated is False


def test_request_is_applied_once(daemon_module):
    daemon = daemon_module.EMS22Daemon()
    daemon.handle_request("CALIB")
    daemon.apply_pending_forced_calibration(123.0)
    assert daemon.apply_pending_forced_calibration(200.0) == 200.0
