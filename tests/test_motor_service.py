"""
Tests pour le module Motor Service.

Ce module teste le service principal de controle moteur:
- Dispatch via process_command (if/elif)
- Handler delegation
- Error handling

Note: Ces tests necessitent astropy (via core.tracking.tracker).
Ils sont automatiquement ignores si astropy n'est pas installe.
"""

import logging
from unittest.mock import patch

import pytest

# Skip ce module si astropy n'est pas installe
pytest.importorskip("astropy", reason="astropy requis pour les tests motor_service")


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_hardware_info():
    """Hardware info dict for simulation mode."""
    return {
        'raspberry_pi': False,
        'rpi_model': None,
        'gpio': False,
        'gpio_error': 'Non teste',
        'encoder_daemon': False,
        'encoder_error': 'Non teste',
        'encoder_position': None,
        'daemon_process': False,
        'motor': False,
        'motor_error': 'Non teste',
        'spi_available': False,
        'spi_devices': [],
        'platform': 'Linux-test',
        'machine': 'x86_64',
        'system': 'Linux',
    }


@pytest.fixture
def motor_service(mock_hardware_info, tmp_path):
    """
    Cree un MotorService en mode simulation avec la vraie config.

    Utilise des fichiers temporaires pour l'IPC.
    """
    with patch('services.motor_service.HardwareDetector.detect_hardware', return_value=(False, mock_hardware_info)), \
         patch('services.motor_service.HardwareDetector.get_hardware_summary', return_value='Test Hardware Summary'), \
         patch('services.ipc_manager.COMMAND_FILE', tmp_path / 'command.json'), \
         patch('services.ipc_manager.STATUS_FILE', tmp_path / 'status.json'), \
         patch('services.ipc_manager.ENCODER_FILE', tmp_path / 'encoder.json'):
        from services.motor_service import MotorService
        return MotorService()


# =============================================================================
# TESTS PROCESS COMMAND DISPATCH
# =============================================================================

class TestProcessCommand:
    """Tests pour la methode process_command dispatch."""

    def test_process_command_goto(self, motor_service):
        """process_command handles GOTO correctly."""
        with patch.object(motor_service.goto_handler, 'execute') as mock_execute:
            mock_execute.return_value = {'status': 'idle', 'position': 90.0}
            motor_service.process_command({'command': 'goto', 'angle': 90.0})
            mock_execute.assert_called_once()
            assert mock_execute.call_args[0][0] == 90.0

    def test_process_command_goto_with_speed(self, motor_service):
        """process_command passes speed to GOTO handler."""
        with patch.object(motor_service.goto_handler, 'execute') as mock_execute:
            mock_execute.return_value = {'status': 'idle', 'position': 90.0}
            motor_service.process_command({'command': 'goto', 'angle': 90.0, 'speed': 0.001})
            mock_execute.assert_called_once()
            assert mock_execute.call_args[0][0] == 90.0
            assert mock_execute.call_args[0][2] == 0.001

    def test_process_command_jog(self, motor_service):
        """process_command handles JOG correctly."""
        with patch.object(motor_service.jog_handler, 'execute') as mock_execute:
            mock_execute.return_value = {'status': 'idle', 'position': 10.0}
            motor_service.process_command({'command': 'jog', 'delta': 10.0})
            mock_execute.assert_called_once()
            assert mock_execute.call_args[0][0] == 10.0

    def test_process_command_stop(self, motor_service):
        """process_command handles STOP correctly."""
        with patch.object(motor_service.continuous_handler, 'stop'), \
             patch.object(motor_service.moteur, 'request_stop'):
            motor_service.process_command({'command': 'stop'})
            assert motor_service.current_status['status'] == 'idle'

    def test_process_command_type_alternative_key(self, motor_service):
        """process_command supports 'type' as alternative to 'command' key."""
        motor_service.process_command({'type': 'status'})  # Should not raise

    def test_process_command_clears_after(self, motor_service):
        """process_command clears the command after processing."""
        with patch.object(motor_service.ipc, 'clear_command') as mock_clear:
            motor_service.process_command({'command': 'status'})
            mock_clear.assert_called_once()

    def test_unknown_command_logs_warning(self, motor_service, caplog):
        """Verify unknown commands are handled gracefully with warning."""
        with caplog.at_level(logging.WARNING):
            motor_service.process_command({'command': 'unknown_command_xyz'})
        assert "Commande inconnue: unknown_command_xyz" in caplog.text

    def test_invalid_command_missing_type(self, motor_service, caplog):
        """Verify commands without type are logged as invalid."""
        with caplog.at_level(logging.WARNING):
            motor_service.process_command({'angle': 90})
        assert "Commande invalide" in caplog.text

    def test_empty_command_handled(self, motor_service, caplog):
        """Verify empty commands are handled gracefully."""
        with caplog.at_level(logging.WARNING):
            motor_service.process_command({})
        assert "Commande invalide" in caplog.text


# =============================================================================
# TESTS HANDLER DELEGATION
# =============================================================================

class TestHandlerDelegation:
    """Tests pour la délégation aux handlers via process_command."""

    def test_continuous_stops_tracking_first(self, motor_service):
        """continuous stops tracking if active before starting."""
        motor_service.tracking_handler.active = True

        with patch.object(motor_service, 'handle_stop') as mock_stop, \
             patch.object(motor_service.continuous_handler, 'start'):
            motor_service.process_command({'command': 'continuous', 'direction': 'cw'})
            mock_stop.assert_called_once()

    def test_tracking_start_with_name(self, motor_service):
        """tracking_start starts tracking with object name."""
        with patch.object(motor_service.tracking_handler, 'start') as mock_start:
            motor_service.process_command({'command': 'tracking_start', 'object': 'M31', 'skip_goto': True})
            mock_start.assert_called_once()
            call_args = mock_start.call_args
            assert call_args[0][0] == 'M31'
            assert call_args[1]['skip_goto'] is True

    def test_tracking_start_alternative_key(self, motor_service):
        """tracking_start supports 'name' as alternative to 'object'."""
        with patch.object(motor_service.tracking_handler, 'start') as mock_start:
            motor_service.process_command({'command': 'tracking_start', 'name': 'NGC 3079'})
            call_args = mock_start.call_args
            assert call_args[0][0] == 'NGC 3079'

    def test_tracking_start_no_name_warns(self, motor_service, caplog):
        """tracking_start warns if no object name provided."""
        with caplog.at_level(logging.WARNING):
            motor_service.process_command({'command': 'tracking_start'})
        assert "tracking_start sans nom d'objet" in caplog.text

    def test_tracking_stop_delegates(self, motor_service):
        """tracking_stop delegates to tracking_handler.stop."""
        with patch.object(motor_service.tracking_handler, 'stop') as mock_stop:
            motor_service.process_command({'command': 'tracking_stop'})
            mock_stop.assert_called_once()

    def test_status_is_noop(self, motor_service):
        """status command is a no-op."""
        motor_service.process_command({'command': 'status'})  # Should not raise


# =============================================================================
# TESTS HANDLE_STOP
# =============================================================================

class TestHandleStop:
    """Tests pour handle_stop() public method."""

    def test_handle_stop_sets_idle(self, motor_service):
        """handle_stop() sets status to idle."""
        motor_service.handle_stop()
        assert motor_service.current_status['status'] == 'idle'

    def test_handle_stop_stops_continuous(self, motor_service):
        """handle_stop() stops continuous handler."""
        with patch.object(motor_service.continuous_handler, 'stop') as mock_cont:
            motor_service.handle_stop()
            mock_cont.assert_called_once()

    def test_handle_stop_clears_tracking_object(self, motor_service):
        """handle_stop() clears tracking_object."""
        motor_service.current_status['tracking_object'] = 'M42'
        motor_service.handle_stop()
        assert motor_service.current_status['tracking_object'] is None
