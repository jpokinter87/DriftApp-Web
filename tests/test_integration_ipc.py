"""
Tests d'intégration IPC — MotorService en mode simulation.

Vérifie le cycle complet :
  commande JSON → process_command → handler → write_status → status JSON

N'utilise PAS la boucle événementielle (run()) — appelle les méthodes directement.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


@pytest.fixture
def ipc_files(tmp_path):
    """Crée les fichiers IPC temporaires."""
    cmd_file = tmp_path / "motor_command.json"
    status_file = tmp_path / "motor_status.json"
    encoder_file = tmp_path / "ems22_position.json"
    (PROJECT_ROOT / "logs").mkdir(parents=True, exist_ok=True)
    return cmd_file, status_file, encoder_file


@pytest.fixture
def motor_service(ipc_files):
    """MotorService patchée avec fichiers IPC temporaires."""
    cmd_file, status_file, encoder_file = ipc_files

    import services.ipc_manager as ipc_module
    with patch.object(ipc_module, 'COMMAND_FILE', cmd_file), \
         patch.object(ipc_module, 'STATUS_FILE', status_file), \
         patch.object(ipc_module, 'ENCODER_FILE', encoder_file):
        from services.motor_service import MotorService
        service = MotorService()
        yield service


# =============================================================================
# Initialisation
# =============================================================================

class TestMotorServiceInit:
    def test_init_simulation_mode(self, motor_service):
        """MotorService s'initialise en mode simulation sur machine de dev."""
        assert motor_service.simulation_mode is True

    def test_init_status_idle(self, motor_service):
        """Status initial = idle."""
        assert motor_service.current_status['status'] == 'idle'
        assert motor_service.current_status['simulation'] is True

    def test_handlers_initialized(self, motor_service):
        """Les handlers de commandes sont initialisés."""
        assert motor_service.goto_handler is not None
        assert motor_service.jog_handler is not None
        assert motor_service.continuous_handler is not None
        assert motor_service.tracking_handler is not None


# =============================================================================
# Lecture/écriture IPC
# =============================================================================

class TestIpcReadWrite:
    def test_read_command_empty(self, motor_service):
        """Pas de fichier commande → None."""
        assert motor_service.ipc.read_command() is None

    def test_read_command_valid(self, motor_service, ipc_files):
        """Commande JSON valide → dict."""
        cmd_file = ipc_files[0]
        cmd = {'id': 'test-1', 'command': 'stop'}
        cmd_file.write_text(json.dumps(cmd))
        result = motor_service.ipc.read_command()
        assert result is not None
        assert result['command'] == 'stop'

    def test_read_command_dedup(self, motor_service, ipc_files):
        """Même commande lue 2× → None la 2e fois."""
        cmd_file = ipc_files[0]
        cmd = {'id': 'test-dedup', 'command': 'stop'}
        cmd_file.write_text(json.dumps(cmd))
        assert motor_service.ipc.read_command() is not None
        assert motor_service.ipc.read_command() is None

    def test_write_status(self, motor_service, ipc_files):
        """_write_status écrit un JSON lisible."""
        status_file = ipc_files[1]
        motor_service._write_status()
        assert status_file.exists()
        data = json.loads(status_file.read_text())
        assert data['status'] == 'idle'
        assert 'last_update' in data


# =============================================================================
# Commandes GOTO / JOG / STOP
# =============================================================================

class TestMotorServiceCommands:
    def test_goto_updates_position(self, motor_service):
        """GOTO change la position simulée."""
        motor_service.process_command({'command': 'goto', 'angle': 90.0})
        assert motor_service.current_status['status'] == 'idle'
        from core.hardware.moteur_simule import get_simulated_position
        pos = get_simulated_position()
        assert abs(pos - 90.0) < 1.0

    def test_goto_with_speed(self, motor_service):
        """GOTO avec vitesse spécifique."""
        motor_service.process_command({'command': 'goto', 'angle': 180.0, 'speed': 0.001})
        from core.hardware.moteur_simule import get_simulated_position
        pos = get_simulated_position()
        assert abs(pos - 180.0) < 1.0

    def test_jog_relative(self, motor_service):
        """JOG déplace relativement."""
        from core.hardware.moteur_simule import get_simulated_position
        # Position initiale 0, JOG de +10
        motor_service.process_command({'command': 'jog', 'delta': 10.0})
        pos = get_simulated_position()
        assert abs(pos - 10.0) < 1.0

    def test_stop_sets_idle(self, motor_service):
        """STOP met le status à idle."""
        motor_service.handle_stop()
        assert motor_service.current_status['status'] == 'idle'

    def test_process_command_goto(self, motor_service):
        """process_command route correctement un goto."""
        motor_service.process_command({'command': 'goto', 'angle': 45.0})
        from core.hardware.moteur_simule import get_simulated_position
        pos = get_simulated_position()
        assert abs(pos - 45.0) < 1.0

    def test_process_command_stop(self, motor_service):
        """process_command route correctement un stop."""
        motor_service.process_command({'command': 'stop'})
        assert motor_service.current_status['status'] == 'idle'

    def test_process_command_invalid(self, motor_service):
        """Commande sans type → warning, pas de crash."""
        motor_service.process_command({})


# =============================================================================
# Tracking logs
# =============================================================================

class TestTrackingLogs:
    def test_add_log(self, motor_service):
        """Ajouter un log de suivi."""
        motor_service._add_tracking_log("Test message", "info")
        assert len(motor_service.recent_tracking_logs) == 1
        assert motor_service.recent_tracking_logs[0]['message'] == "Test message"

    def test_log_limit(self, motor_service):
        """Les logs sont limités à maxlen=20."""
        for i in range(25):
            motor_service._add_tracking_log(f"Log {i}")
        assert len(motor_service.recent_tracking_logs) == 20
