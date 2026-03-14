"""
Tests d'intégration IPC — MotorService en mode simulation.

Vérifie le cycle complet :
  commande JSON → process_command → handle_xxx → write_status → status JSON

N'utilise PAS la boucle événementielle (run()) — appelle les méthodes directement.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Setup path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def ipc_files(tmp_path):
    """Crée les fichiers IPC temporaires."""
    cmd_file = tmp_path / "motor_command.json"
    status_file = tmp_path / "motor_status.json"
    encoder_file = tmp_path / "ems22_position.json"
    # Créer le fichier logs pour éviter l'erreur au logging
    (PROJECT_ROOT / "logs").mkdir(parents=True, exist_ok=True)
    return cmd_file, status_file, encoder_file


@pytest.fixture
def motor_service(ipc_files):
    """MotorService patchée avec fichiers IPC temporaires."""
    cmd_file, status_file, encoder_file = ipc_files

    import services.motor_service as ms_module
    with patch.object(ms_module, 'COMMAND_FILE', cmd_file), \
         patch.object(ms_module, 'STATUS_FILE', status_file), \
         patch.object(ms_module, 'ENCODER_FILE', encoder_file):
        service = ms_module.MotorService()
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

    def test_parking_config_loaded(self, motor_service):
        """Config parking chargée (défaut ou depuis config.json)."""
        assert 'enabled' in motor_service.parking_config
        assert 'park_position' in motor_service.parking_config


# =============================================================================
# Lecture/écriture IPC
# =============================================================================

class TestIpcReadWrite:
    def test_read_command_empty(self, motor_service):
        """Pas de fichier commande → None."""
        assert motor_service.read_command() is None

    def test_read_command_valid(self, motor_service, ipc_files):
        """Commande JSON valide → dict."""
        cmd_file = ipc_files[0]
        cmd = {'id': 'test-1', 'command': 'stop'}
        cmd_file.write_text(json.dumps(cmd))
        result = motor_service.read_command()
        assert result is not None
        assert result['command'] == 'stop'

    def test_read_command_dedup(self, motor_service, ipc_files):
        """Même commande lue 2× → None la 2e fois."""
        cmd_file = ipc_files[0]
        cmd = {'id': 'test-dedup', 'command': 'stop'}
        cmd_file.write_text(json.dumps(cmd))
        assert motor_service.read_command() is not None
        assert motor_service.read_command() is None  # Déjà traitée

    def test_write_status(self, motor_service, ipc_files):
        """write_status écrit un JSON lisible."""
        status_file = ipc_files[1]
        motor_service.write_status()
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
        motor_service.handle_goto(90.0)
        assert motor_service.current_status['status'] == 'idle'
        # En simulation, la position est mise à jour
        from core.hardware.moteur_simule import get_simulated_position
        pos = get_simulated_position()
        assert abs(pos - 90.0) < 1.0  # Tolérance simulation

    def test_goto_with_speed(self, motor_service):
        """GOTO avec vitesse spécifique."""
        motor_service.handle_goto(180.0, speed=0.001)
        from core.hardware.moteur_simule import get_simulated_position
        pos = get_simulated_position()
        assert abs(pos - 180.0) < 1.0

    def test_jog_relative(self, motor_service):
        """JOG déplace relativement."""
        from core.hardware.moteur_simule import get_simulated_position, set_simulated_position
        set_simulated_position(100.0)
        motor_service.current_status['position'] = 100.0  # Sync status
        motor_service.handle_jog(10.0)
        pos = get_simulated_position()
        assert abs(pos - 110.0) < 1.0

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
        motor_service.process_command({})  # Pas de crash


# =============================================================================
# Parking
# =============================================================================

class TestMotorServiceParking:
    def test_park_moves_to_position(self, motor_service):
        """Park déplace vers la position configurée."""
        motor_service.handle_park()
        assert motor_service.current_status['status'] == 'idle'

    def test_end_session(self, motor_service):
        """End session arrête le tracking et parque."""
        motor_service.handle_end_session()
        assert motor_service.current_status['status'] == 'idle'
        assert motor_service.tracking_active is False


# =============================================================================
# Tracking logs
# =============================================================================

class TestTrackingLogs:
    def test_add_log(self, motor_service):
        """Ajouter un log de suivi."""
        motor_service.add_tracking_log("Test message", "info")
        assert len(motor_service.recent_tracking_logs) == 1
        assert motor_service.recent_tracking_logs[0]['message'] == "Test message"

    def test_log_limit(self, motor_service):
        """Les logs sont limités à max_tracking_logs."""
        for i in range(25):
            motor_service.add_tracking_log(f"Log {i}")
        assert len(motor_service.recent_tracking_logs) == 20
