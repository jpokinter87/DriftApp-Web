"""
Tests pour core/tracking/tracking_logger.py

Couvre toutes les méthodes de logging du suivi.
"""

import logging

import pytest

from core.tracking.tracking_logger import TrackingLogger


@pytest.fixture
def tracker_logger():
    return TrackingLogger()


class TestTrackingLogger:
    def test_construction(self, tracker_logger):
        assert tracker_logger.logger is not None
        assert tracker_logger.session_start is not None

    def test_start_tracking(self, tracker_logger, caplog):
        with caplog.at_level(logging.INFO, logger="core.tracking.tracking_logger"):
            tracker_logger.start_tracking("M42", "5h35m", "-5°23'")
        assert "M42" in caplog.text

    def test_stop_tracking(self, tracker_logger, caplog):
        with caplog.at_level(logging.INFO, logger="core.tracking.tracking_logger"):
            tracker_logger.stop_tracking("Manuel")
        assert "Manuel" in caplog.text

    def test_log_drift_check_significant(self, tracker_logger, caplog):
        with caplog.at_level(logging.INFO, logger="core.tracking.tracking_logger"):
            tracker_logger.log_drift_check(0.4, 0.5)
        assert "DÉRIVE" in caplog.text

    def test_log_drift_check_insignificant(self, tracker_logger, caplog):
        with caplog.at_level(logging.DEBUG, logger="core.tracking.tracking_logger"):
            tracker_logger.log_drift_check(0.1, 0.5)
        # Drift < threshold * 0.5 → pas de log
        assert "DÉRIVE" not in caplog.text

    def test_log_correction_start(self, tracker_logger, caplog):
        with caplog.at_level(logging.WARNING, logger="core.tracking.tracking_logger"):
            tracker_logger.log_correction_start(1.5, "horaire")
        assert "CORRECTION" in caplog.text

    def test_log_correction_result_success(self, tracker_logger, caplog):
        with caplog.at_level(logging.INFO, logger="core.tracking.tracking_logger"):
            tracker_logger.log_correction_result(True, duration=1.5, steps=500)
        assert "réussie" in caplog.text

    def test_log_correction_result_failure(self, tracker_logger, caplog):
        with caplog.at_level(logging.ERROR, logger="core.tracking.tracking_logger"):
            tracker_logger.log_correction_result(False, duration=5.0)
        assert "échouée" in caplog.text

    def test_log_meridian_close(self, tracker_logger, caplog):
        with caplog.at_level(logging.WARNING, logger="core.tracking.tracking_logger"):
            tracker_logger.log_meridian(120.0)
        assert "MÉRIDIEN" in caplog.text

    def test_log_meridian_far(self, tracker_logger, caplog):
        with caplog.at_level(logging.WARNING, logger="core.tracking.tracking_logger"):
            tracker_logger.log_meridian(600.0)
        # > 300s → pas de log
        assert "MÉRIDIEN" not in caplog.text

    def test_log_zenith(self, tracker_logger, caplog):
        with caplog.at_level(logging.WARNING, logger="core.tracking.tracking_logger"):
            tracker_logger.log_zenith(86.0)
        assert "ZÉNITH" in caplog.text

    def test_log_zenith_not_close(self, tracker_logger, caplog):
        with caplog.at_level(logging.WARNING, logger="core.tracking.tracking_logger"):
            tracker_logger.log_zenith(80.0)
        # < 85° → pas de log (seuil hardcodé - finding M-21)
        assert "ZÉNITH" not in caplog.text

    def test_log_motor_activity_debug(self, tracker_logger, caplog):
        with caplog.at_level(logging.DEBUG, logger="core.tracking.tracking_logger"):
            tracker_logger.log_motor_activity("Test moteur")
        assert "MOTEUR" in caplog.text

    def test_log_position(self, tracker_logger, caplog):
        with caplog.at_level(logging.DEBUG, logger="core.tracking.tracking_logger"):
            tracker_logger.log_position(180.0, 45.0, 0.002, "horaire")
        assert "POS" in caplog.text
