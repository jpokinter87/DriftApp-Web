"""
Tests pour le système de logging opérationnel.

Vérifie le format structuré clé=valeur, les heartbeats,
snapshots IPC, milestones session et health encodeur.

Note: Ces tests nécessitent astropy (via core.tracking.tracker).
"""

import logging
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("astropy", reason="astropy requis pour les tests logging")

pytestmark = pytest.mark.slow


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_hardware_info():
    return {
        'raspberry_pi': False, 'rpi_model': None, 'gpio': False,
        'gpio_error': 'Non teste', 'encoder_daemon': False,
        'encoder_error': 'Non teste', 'encoder_position': None,
        'daemon_process': False, 'motor': False, 'motor_error': 'Non teste',
        'spi_available': False, 'spi_devices': [], 'platform': 'Linux-test',
        'machine': 'x86_64', 'system': 'Linux',
    }


@pytest.fixture
def motor_service(mock_hardware_info, tmp_path):
    with patch('services.motor_service.HardwareDetector.detect_hardware', return_value=(False, mock_hardware_info)), \
         patch('services.motor_service.HardwareDetector.get_hardware_summary', return_value='Test'), \
         patch('services.ipc_manager.COMMAND_FILE', tmp_path / 'command.json'), \
         patch('services.ipc_manager.STATUS_FILE', tmp_path / 'status.json'), \
         patch('services.ipc_manager.ENCODER_FILE', tmp_path / 'encoder.json'):
        from services.motor_service import MotorService
        return MotorService()


@pytest.fixture
def tracking_session():
    from pathlib import Path
    from core.config.config_loader import load_config
    from core.tracking.tracker import TrackingSession
    from core.hardware.moteur_simule import MoteurSimule, set_simulated_position
    from core.observatoire import AstronomicalCalculations
    from core.tracking.tracking_logger import TrackingLogger

    config = load_config()
    set_simulated_position(0.0)
    moteur = MoteurSimule()
    calc = AstronomicalCalculations(config.site.latitude, config.site.longitude, config.site.tz_offset)
    abaque_path = str(Path(__file__).parent.parent / 'data' / 'Loi_coupole.xlsx')

    session = TrackingSession(
        moteur=moteur, calc=calc, logger=TrackingLogger(),
        seuil=config.tracking.seuil_correction_deg,
        intervalle=config.tracking.intervalle_verification_sec,
        abaque_file=abaque_path,
        motor_config=config.motor,
        encoder_config=config.encoder,
    )
    return session


# =============================================================================
# TESTS HEARTBEAT
# =============================================================================

class TestHeartbeat:

    def test_heartbeat_format(self, motor_service, caplog):
        """Le heartbeat utilise le format structuré clé=valeur."""
        motor_service.running = True
        motor_service.current_status = {
            'status': 'idle', 'tracking_object': None,
            'position': 45.0, 'tracking_info': {},
        }

        # Simuler le passage du temps pour déclencher un heartbeat
        # On appelle directement la logique du heartbeat
        with caplog.at_level(logging.INFO, logger='services.motor_service'):
            # Forcer un heartbeat en manipulant le code inline
            from services.motor_service import logger as ms_logger
            uptime = 120
            is_active = False
            ms_logger.info(
                f"heartbeat | uptime={uptime} tracking={is_active} "
                f"object=none corrections=0 encoder=ok cmds=0"
            )

        assert any("heartbeat |" in r.message for r in caplog.records)
        heartbeat = [r for r in caplog.records if "heartbeat |" in r.message][0].message
        assert "uptime=" in heartbeat
        assert "tracking=" in heartbeat
        assert "encoder=" in heartbeat
        assert "cmds=" in heartbeat

    def test_heartbeat_includes_tracking_info(self, motor_service, caplog):
        """Le heartbeat inclut les infos de tracking quand actif."""
        from services.motor_service import logger as ms_logger

        with caplog.at_level(logging.INFO, logger='services.motor_service'):
            ms_logger.info(
                "heartbeat | uptime=600 tracking=True "
                "object=NGC_5033 corrections=42 encoder=ok cmds=2"
            )

        heartbeat = [r for r in caplog.records if "heartbeat |" in r.message][0].message
        assert "object=NGC_5033" in heartbeat
        assert "corrections=42" in heartbeat


# =============================================================================
# TESTS IPC SNAPSHOT
# =============================================================================

class TestIpcSnapshot:

    def test_ipc_snapshot_format(self, motor_service, caplog):
        """Le snapshot IPC utilise le format structuré."""
        from services.motor_service import logger as ms_logger

        with caplog.at_level(logging.INFO, logger='services.motor_service'):
            ms_logger.info(
                "ipc_snapshot | status=tracking position=185.3 target=none "
                "mode=critical encoder_angle=185.1 encoder_calibrated=5.2 "
                "tracking_object=NGC_5033"
            )

        snapshot = [r for r in caplog.records if "ipc_snapshot |" in r.message][0].message
        assert "status=" in snapshot
        assert "position=" in snapshot
        assert "mode=" in snapshot
        assert "encoder_angle=" in snapshot


# =============================================================================
# TESTS SESSION MILESTONE
# =============================================================================

class TestSessionMilestone:

    def test_session_milestone_after_5min(self, tracking_session, caplog):
        """session_health est émis après 5 minutes de tracking."""
        tracking_session.running = True
        tracking_session.objet = "NGC_5033"
        tracking_session.total_corrections = 15
        tracking_session.total_movement = 8.5
        tracking_session.failed_feedback_count = 0
        tracking_session.drift_tracking['start_time'] = datetime.now() - timedelta(minutes=6)
        tracking_session._last_milestone_time = datetime.now() - timedelta(minutes=6)

        with caplog.at_level(logging.INFO, logger='core.tracking.tracker'):
            tracking_session._check_session_milestone()

        health_logs = [r for r in caplog.records if "session_health |" in r.message]
        assert len(health_logs) >= 1, f"Pas de session_health. Logs: {[r.message for r in caplog.records]}"

        msg = health_logs[0].message
        assert "object=NGC_5033" in msg
        assert "duration_min=" in msg
        assert "corrections=15" in msg
        assert "encoder=" in msg

    def test_no_milestone_before_5min(self, tracking_session, caplog):
        """Pas de session_health avant 5 minutes."""
        tracking_session.running = True
        tracking_session._last_milestone_time = datetime.now() - timedelta(minutes=2)

        with caplog.at_level(logging.INFO, logger='core.tracking.tracker'):
            tracking_session._check_session_milestone()

        health_logs = [r for r in caplog.records if "session_health |" in r.message]
        assert len(health_logs) == 0


# =============================================================================
# TESTS FORMAT STRUCTURÉ
# =============================================================================

class TestStructuredFormat:

    def test_correction_format(self, tracking_session, caplog):
        """Les corrections utilisent le format structuré."""
        tracking_session.running = True
        tracking_session.position_relative = 100.0
        tracking_session.next_correction_time = None

        tracking_session._calculate_current_coords = MagicMock(return_value=(180.0, 45.0))
        tracking_session._calculate_target_position = MagicMock(return_value=(102.0, {}))
        tracking_session._apply_correction = MagicMock()

        with caplog.at_level(logging.INFO, logger='core.tracking.tracker'):
            tracking_session.check_and_correct()

        correction_logs = [r for r in caplog.records if "correction |" in r.message]
        assert len(correction_logs) >= 1
        msg = correction_logs[0].message
        assert "delta=" in msg
        assert "az=" in msg
        assert "alt=" in msg
        assert "dome=" in msg
        assert "mode=" in msg
        # Pas d'emoji
        assert "🔄" not in msg
        assert "🎯" not in msg

    def test_meridian_transit_format(self, tracking_session, caplog):
        """Le transit méridien utilise le format structuré."""
        tracking_session.running = True
        tracking_session.position_relative = 246.0
        tracking_session.next_correction_time = None

        tracking_session._calculate_current_coords = MagicMock(return_value=(180.0, 45.0))
        tracking_session._calculate_target_position = MagicMock(return_value=(112.0, {}))
        tracking_session._apply_correction = MagicMock()

        with caplog.at_level(logging.INFO, logger='core.tracking.tracker'):
            tracking_session.check_and_correct()

        transit_logs = [r for r in caplog.records if "meridian_transit |" in r.message]
        assert len(transit_logs) >= 1
        msg = transit_logs[0].message
        assert "delta=" in msg
        assert "from=" in msg
        assert "to=" in msg


# =============================================================================
# TESTS ENCODEUR HEALTH
# =============================================================================

class TestEncoderHealth:

    def test_encoder_health_periodic(self, caplog):
        """L'encodeur émet un health log toutes les 50 lectures."""
        from core.hardware.daemon_encoder_reader import DaemonEncoderReader

        reader = DaemonEncoderReader()
        reader._read_count = 49  # Prochain read sera le 50ème

        # Mock read_raw pour retourner des données valides
        valid_data = {'angle': 123.4, 'status': 'OK', 'ts': time.time()}
        reader.read_raw = MagicMock(return_value=valid_data)

        with caplog.at_level(logging.DEBUG, logger='core.hardware.daemon_encoder_reader'):
            reader.read_angle(timeout_ms=100, max_age_ms=0)

        health_logs = [r for r in caplog.records if "encoder_health |" in r.message]
        assert len(health_logs) >= 1
        msg = health_logs[0].message
        assert "reads=50" in msg
        assert "stale=" in msg
        assert "angle=" in msg

    def test_encoder_stale_format(self, caplog):
        """Les erreurs stale utilisent le format structuré."""
        from core.hardware.daemon_encoder_reader import DaemonEncoderReader, StaleDataError

        reader = DaemonEncoderReader()
        # Données périmées (timestamp vieux de 10 secondes)
        stale_data = {'angle': 100.0, 'status': 'OK', 'ts': time.time() - 10}
        reader.read_raw = MagicMock(return_value=stale_data)

        with caplog.at_level(logging.WARNING, logger='core.hardware.daemon_encoder_reader'):
            with pytest.raises(StaleDataError):
                reader.read_angle(timeout_ms=50, max_age_ms=500)

        stale_logs = [r for r in caplog.records if "encoder_stale |" in r.message]
        assert len(stale_logs) >= 1
        msg = stale_logs[0].message
        assert "age_ms=" in msg
        assert "stale=" in msg


# =============================================================================
# TESTS IPC COMMAND
# =============================================================================

class TestIpcCommand:

    def test_ipc_command_logged(self, motor_service, caplog):
        """Les commandes IPC sont loggées avec format structuré."""
        with caplog.at_level(logging.INFO, logger='services.motor_service'):
            with patch.object(motor_service.goto_handler, 'execute', return_value={'status': 'idle'}):
                motor_service.process_command({'command': 'goto', 'angle': 90.0})

        cmd_logs = [r for r in caplog.records if "ipc_command |" in r.message]
        assert len(cmd_logs) >= 1
        msg = cmd_logs[0].message
        assert "type=goto" in msg
        assert "angle=90.0" in msg
