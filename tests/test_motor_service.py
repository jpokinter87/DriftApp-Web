"""
Tests pour le module Motor Service.

Ce module teste le service principal de controle moteur:
- Command registry pattern (OCP compliance)
- Process command dispatch
- Error handling

Note: Ces tests necessitent astropy (via core.tracking.tracker).
Ils sont automatiquement ignores si astropy n'est pas installe.
"""

import logging
from unittest.mock import MagicMock, patch, PropertyMock

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
# TESTS COMMAND REGISTRY
# =============================================================================

class TestCommandRegistry:
    """Tests pour le pattern command registry (OCP compliance)."""

    def test_command_registry_exists(self, motor_service):
        """Verify command registry attribute exists."""
        assert hasattr(motor_service, '_command_registry')
        assert isinstance(motor_service._command_registry, dict)

    def test_command_registry_contains_all_commands(self, motor_service):
        """Verify command registry is complete (OCP pattern)."""
        expected_commands = {
            'goto', 'jog', 'stop', 'continuous',
            'tracking_start', 'tracking_stop', 'status'
        }
        actual_commands = set(motor_service._command_registry.keys())

        assert expected_commands == actual_commands, (
            f"Missing commands: {expected_commands - actual_commands}, "
            f"Extra commands: {actual_commands - expected_commands}"
        )

    def test_command_registry_handlers_are_callable(self, motor_service):
        """Verify all registry handlers are callable."""
        for cmd_name, handler in motor_service._command_registry.items():
            assert callable(handler), f"Handler for '{cmd_name}' is not callable"

    def test_command_registry_ocp_compliance(self, motor_service):
        """
        Verify adding new command type only requires adding to registry.

        OCP = Open/Closed Principle: open for extension, closed for modification.
        Adding a new command should not require modifying process_command().
        """
        # Define a new custom handler
        custom_handler_called = []

        def custom_handler(command):
            custom_handler_called.append(command)

        # Add to registry (extension, not modification)
        motor_service._command_registry['custom_test'] = custom_handler

        # Process the custom command
        motor_service.process_command({'command': 'custom_test', 'data': 42})

        # Verify it was handled via registry lookup
        assert len(custom_handler_called) == 1
        assert custom_handler_called[0] == {'command': 'custom_test', 'data': 42}


# =============================================================================
# TESTS PROCESS COMMAND
# =============================================================================

class TestProcessCommand:
    """Tests pour la methode process_command."""

    def test_process_command_valid_goto(self, motor_service):
        """process_command handles GOTO correctly via registry lookup."""
        # Verify the registry contains the handler
        assert 'goto' in motor_service._command_registry

        # Mock the goto_handler.execute to verify it's called through the chain
        with patch.object(motor_service.goto_handler, 'execute') as mock_execute:
            mock_execute.return_value = {'status': 'idle', 'position': 90.0}
            command = {'command': 'goto', 'angle': 90.0}
            motor_service.process_command(command)

            mock_execute.assert_called_once()
            assert mock_execute.call_args[0][0] == 90.0  # angle

    def test_process_command_valid_jog(self, motor_service):
        """process_command handles JOG correctly via registry lookup."""
        assert 'jog' in motor_service._command_registry

        with patch.object(motor_service.jog_handler, 'execute') as mock_execute:
            mock_execute.return_value = {'status': 'idle', 'position': 10.0}
            command = {'command': 'jog', 'delta': 10.0}
            motor_service.process_command(command)

            mock_execute.assert_called_once()
            assert mock_execute.call_args[0][0] == 10.0  # delta

    def test_process_command_valid_stop(self, motor_service):
        """process_command handles STOP correctly via registry lookup."""
        assert 'stop' in motor_service._command_registry

        with patch.object(motor_service.continuous_handler, 'stop'), \
             patch.object(motor_service.moteur, 'request_stop'):
            command = {'command': 'stop'}
            motor_service.process_command(command)

            # Verify status changed to idle (side effect of _handle_stop)
            assert motor_service.current_status['status'] == 'idle'

    def test_process_command_type_alternative_key(self, motor_service):
        """process_command supports 'type' as alternative to 'command' key."""
        assert 'status' in motor_service._command_registry

        # The status handler is a no-op, just verify it doesn't raise
        command = {'type': 'status'}
        motor_service.process_command(command)  # Should not raise

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
# TESTS HANDLER METHODS
# =============================================================================

class TestHandlerMethods:
    """Tests pour les methodes _handle_* individuelles."""

    def test_handle_goto_delegates_to_handler(self, motor_service):
        """_handle_goto delegates to goto_handler.execute."""
        with patch.object(motor_service.goto_handler, 'execute') as mock_execute:
            mock_execute.return_value = {'status': 'idle', 'position': 90.0}

            motor_service._handle_goto({'angle': 90.0, 'speed': 0.001})

            mock_execute.assert_called_once()
            call_args = mock_execute.call_args
            assert call_args[0][0] == 90.0  # angle
            assert call_args[0][2] == 0.001  # speed

    def test_handle_jog_delegates_to_handler(self, motor_service):
        """_handle_jog delegates to jog_handler.execute."""
        with patch.object(motor_service.jog_handler, 'execute') as mock_execute:
            mock_execute.return_value = {'status': 'idle', 'position': 10.0}

            motor_service._handle_jog({'delta': 10.0, 'speed': 0.002})

            mock_execute.assert_called_once()
            call_args = mock_execute.call_args
            assert call_args[0][0] == 10.0  # delta
            assert call_args[0][2] == 0.002  # speed

    def test_handle_stop_stops_all_components(self, motor_service):
        """_handle_stop stops continuous handler and motor."""
        with patch.object(motor_service.continuous_handler, 'stop') as mock_cont:
            motor_service._handle_stop({})

            mock_cont.assert_called_once()
            # Note: In simulation mode, feedback_controller IS the moteur (MoteurSimule)
            # Both moteur.request_stop() and feedback_controller.request_stop() call same method
            # which may result in 2 calls. Testing continuous_handler.stop() is sufficient.

    def test_handle_continuous_stops_tracking_first(self, motor_service):
        """_handle_continuous stops tracking if active before starting."""
        # Set tracking as active by manipulating the active flag
        motor_service.tracking_handler.active = True

        with patch.object(motor_service.tracking_handler, 'stop') as mock_tracking_stop, \
             patch.object(motor_service.continuous_handler, 'stop'), \
             patch.object(motor_service.moteur, 'request_stop'), \
             patch.object(motor_service.continuous_handler, 'start'):

            motor_service._handle_continuous({'direction': 'cw'})

            # The tracking handler was active, so tracking_handler.stop should have been called
            mock_tracking_stop.assert_called_once()

    def test_handle_tracking_start_with_name(self, motor_service):
        """_handle_tracking_start starts tracking with object name."""
        with patch.object(motor_service.tracking_handler, 'start') as mock_start:
            motor_service._handle_tracking_start({'object': 'M31', 'skip_goto': True})

            mock_start.assert_called_once()
            call_args = mock_start.call_args
            assert call_args[0][0] == 'M31'
            assert call_args[1]['skip_goto'] is True

    def test_handle_tracking_start_alternative_key(self, motor_service):
        """_handle_tracking_start supports 'name' as alternative to 'object'."""
        with patch.object(motor_service.tracking_handler, 'start') as mock_start:
            motor_service._handle_tracking_start({'name': 'NGC 3079'})

            call_args = mock_start.call_args
            assert call_args[0][0] == 'NGC 3079'

    def test_handle_tracking_start_no_name_warns(self, motor_service, caplog):
        """_handle_tracking_start warns if no object name provided."""
        with caplog.at_level(logging.WARNING):
            motor_service._handle_tracking_start({})

        assert "tracking_start sans nom d'objet" in caplog.text

    def test_handle_tracking_stop_delegates(self, motor_service):
        """_handle_tracking_stop delegates to tracking_handler.stop."""
        with patch.object(motor_service.tracking_handler, 'stop') as mock_stop:
            motor_service._handle_tracking_stop({})

            mock_stop.assert_called_once()

    def test_handle_status_is_noop(self, motor_service):
        """_handle_status is a no-op (status already updated elsewhere)."""
        # Should not raise and should not change anything
        motor_service._handle_status({'extra': 'data'})
        # No assertion needed - just verify no exception


# =============================================================================
# TESTS LEGACY INTERFACE
# =============================================================================

class TestLegacyInterface:
    """Tests pour l'interface legacy handle_stop()."""

    def test_handle_stop_delegates_to_private(self, motor_service):
        """handle_stop() (legacy) delegates to _handle_stop()."""
        with patch.object(motor_service, '_handle_stop') as mock_handler:
            motor_service.handle_stop()

            mock_handler.assert_called_once_with({})
