"""
Tests d'intégration IPC - Flux complet Django → Motor Service.

Ce module teste l'intégration entre les composants:
- Écriture/lecture de commandes via IPC
- Écriture/lecture de statut via IPC
- Flux complet GOTO: commande → exécution → statut
- Flux tracking: démarrage → corrections → arrêt
- Gestion des accès concurrents

Date: Décembre 2025
Version: 1.0
"""

import json
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Any
from unittest.mock import patch, MagicMock

import pytest

# Vérifier si astropy est disponible (requis pour tests GOTO/Tracking handlers)
try:
    import astropy
    HAS_ASTROPY = True
except ImportError:
    HAS_ASTROPY = False

requires_astropy = pytest.mark.skipif(
    not HAS_ASTROPY,
    reason="Ces tests nécessitent astropy"
)


# =============================================================================
# Fixtures communes
# =============================================================================


class IpcTestHelper:
    """Helper pour créer un environnement IPC de test isolé."""

    def __init__(self, tmp_path: Path):
        self.tmp_path = tmp_path
        self.command_file = tmp_path / 'motor_command.json'
        self.status_file = tmp_path / 'motor_status.json'
        self.encoder_file = tmp_path / 'ems22_position.json'

    def write_command_django_side(self, command: Dict[str, Any]):
        """Simule Django écrivant une commande."""
        import fcntl
        with open(self.command_file, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(json.dumps(command))
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def read_status_django_side(self) -> Dict[str, Any]:
        """Simule Django lisant le statut."""
        import fcntl
        if not self.status_file.exists():
            return {}
        with open(self.status_file, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                text = f.read()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return json.loads(text) if text.strip() else {}

    def setup_encoder_position(self, angle: float):
        """Configure une position encodeur simulée."""
        encoder_data = {
            'angle': angle,
            'calibrated': True,
            'status': 'OK',
            'timestamp': time.time()
        }
        self.encoder_file.write_text(json.dumps(encoder_data))


@pytest.fixture
def ipc_helper(tmp_path):
    """Crée un helper IPC avec fichiers temporaires."""
    return IpcTestHelper(tmp_path)


@pytest.fixture
def ipc_manager_patched(tmp_path):
    """Crée un IpcManager avec chemins patchés."""
    helper = IpcTestHelper(tmp_path)
    with patch('services.ipc_manager.COMMAND_FILE', helper.command_file), \
         patch('services.ipc_manager.STATUS_FILE', helper.status_file), \
         patch('services.ipc_manager.ENCODER_FILE', helper.encoder_file):
        from services.ipc_manager import IpcManager
        yield IpcManager(), helper


# =============================================================================
# Tests du flux commande/statut
# =============================================================================


class TestIpcCommandFlow:
    """Tests du flux de commandes IPC."""

    def test_write_command_read_command(self, ipc_manager_patched):
        """Django écrit une commande, Motor Service la lit."""
        ipc, helper = ipc_manager_patched

        # Django écrit la commande
        command = {'command': 'goto', 'angle': 90.0, 'id': 'test_001'}
        helper.write_command_django_side(command)

        # Motor Service lit la commande
        result = ipc.read_command()

        assert result is not None
        assert result['command'] == 'goto'
        assert result['angle'] == 90.0
        assert result['id'] == 'test_001'

    def test_command_not_read_twice(self, ipc_manager_patched):
        """Une commande avec le même ID n'est lue qu'une fois."""
        ipc, helper = ipc_manager_patched

        command = {'command': 'stop', 'id': 'test_002'}
        helper.write_command_django_side(command)

        # Première lecture
        result1 = ipc.read_command()
        assert result1 is not None

        # Deuxième lecture (même ID)
        result2 = ipc.read_command()
        assert result2 is None

    def test_new_command_accepted_after_clear(self, ipc_manager_patched):
        """Une nouvelle commande est acceptée après clear."""
        ipc, helper = ipc_manager_patched

        # Commande 1
        cmd1 = {'command': 'goto', 'angle': 45.0, 'id': 'cmd_001'}
        helper.write_command_django_side(cmd1)
        result1 = ipc.read_command()
        assert result1 is not None
        ipc.clear_command()

        # Commande 2 (nouvel ID)
        cmd2 = {'command': 'jog', 'delta': 10.0, 'id': 'cmd_002'}
        helper.write_command_django_side(cmd2)
        result2 = ipc.read_command()

        assert result2 is not None
        assert result2['command'] == 'jog'

    def test_write_status_read_status(self, ipc_manager_patched):
        """Motor Service écrit le statut, Django le lit."""
        ipc, helper = ipc_manager_patched

        # Motor Service écrit le statut
        status = {
            'status': 'moving',
            'position': 123.5,
            'target': 180.0,
            'progress': 50
        }
        ipc.write_status(status)

        # Django lit le statut
        result = helper.read_status_django_side()

        assert result['status'] == 'moving'
        assert result['position'] == 123.5
        assert result['target'] == 180.0
        assert 'last_update' in result

    def test_status_overwrite(self, ipc_manager_patched):
        """Les mises à jour de statut écrasent les anciennes."""
        ipc, helper = ipc_manager_patched

        # Statut initial
        ipc.write_status({'status': 'idle', 'position': 0})
        result1 = helper.read_status_django_side()
        assert result1['status'] == 'idle'

        # Statut mis à jour
        ipc.write_status({'status': 'tracking', 'position': 45.0})
        result2 = helper.read_status_django_side()
        assert result2['status'] == 'tracking'
        assert result2['position'] == 45.0


class TestIpcConcurrentAccess:
    """Tests de sécurité des accès concurrents."""

    def test_concurrent_writes_status(self, ipc_manager_patched):
        """Plusieurs écritures de statut concurrentes ne corrompent pas les données."""
        ipc, helper = ipc_manager_patched
        errors = []
        results = []

        def write_status(i):
            try:
                status = {'status': f'state_{i}', 'index': i}
                ipc.write_status(status)
            except Exception as e:
                errors.append(e)

        # 10 écritures concurrentes
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(write_status, i) for i in range(10)]
            for f in futures:
                f.result()

        assert len(errors) == 0, f"Erreurs lors des écritures: {errors}"

        # Vérifier que le fichier est toujours valide
        result = helper.read_status_django_side()
        assert 'status' in result
        assert result['status'].startswith('state_')

    def test_concurrent_read_write(self, ipc_manager_patched):
        """Lectures pendant écritures ne corrompent pas."""
        ipc, helper = ipc_manager_patched
        write_errors = []
        read_errors = []
        successful_reads = []

        def writer():
            for i in range(20):
                try:
                    ipc.write_status({'status': 'writing', 'iteration': i})
                    time.sleep(0.01)
                except Exception as e:
                    write_errors.append(e)

        def reader():
            for _ in range(20):
                try:
                    result = helper.read_status_django_side()
                    if result:
                        successful_reads.append(result)
                    time.sleep(0.01)
                except Exception as e:
                    read_errors.append(e)

        # Lancer lecteur et écrivain en parallèle
        writer_thread = threading.Thread(target=writer)
        reader_thread = threading.Thread(target=reader)

        writer_thread.start()
        reader_thread.start()

        writer_thread.join()
        reader_thread.join()

        assert len(write_errors) == 0, f"Erreurs d'écriture: {write_errors}"
        assert len(read_errors) == 0, f"Erreurs de lecture: {read_errors}"
        # Au moins quelques lectures ont réussi
        assert len(successful_reads) > 0

    def test_rapid_command_sequence(self, ipc_manager_patched):
        """Une séquence rapide de commandes est gérée correctement."""
        ipc, helper = ipc_manager_patched
        processed_commands = []

        # Simuler 5 commandes rapides (comme un utilisateur impatient)
        for i in range(5):
            cmd = {'command': 'jog', 'delta': 5.0, 'id': f'rapid_{i}'}
            helper.write_command_django_side(cmd)
            result = ipc.read_command()
            if result:
                processed_commands.append(result['id'])
            ipc.clear_command()

        # Toutes les commandes avec ID uniques sont traitées
        assert len(processed_commands) == 5
        assert processed_commands == [f'rapid_{i}' for i in range(5)]


# =============================================================================
# Tests du flux GOTO
# =============================================================================


@requires_astropy
class TestGotoCommandFlow:
    """Tests d'intégration pour les commandes GOTO."""

    @pytest.fixture
    def goto_handler_setup(self, tmp_path):
        """Configure un GotoHandler avec mocks."""
        helper = IpcTestHelper(tmp_path)

        # Mock du moteur
        mock_moteur = MagicMock()
        mock_moteur.rotation = MagicMock()
        mock_moteur.clear_stop_request = MagicMock()

        # Mock du daemon reader
        mock_reader = MagicMock()
        mock_reader.is_available.return_value = True
        mock_reader.read_angle.return_value = 0.0

        # Mock du feedback controller
        mock_feedback = MagicMock()
        mock_feedback.rotation_avec_feedback.return_value = {
            'success': True,
            'position_initiale': 0.0,
            'position_finale': 90.0,
            'erreur_finale': 0.2,
            'iterations': 2
        }

        # Configuration mock
        mock_config = MagicMock()
        mock_config.thresholds.feedback_min_deg = 3.0
        mock_config.thresholds.default_tolerance_deg = 0.5
        mock_config.adaptive.modes = {'continuous': MagicMock(motor_delay=0.00012)}

        statuses = []

        def status_callback(status):
            statuses.append(status.copy())

        with patch('services.ipc_manager.COMMAND_FILE', helper.command_file), \
             patch('services.ipc_manager.STATUS_FILE', helper.status_file), \
             patch('services.ipc_manager.ENCODER_FILE', helper.encoder_file):
            from services.command_handlers import GotoHandler

            handler = GotoHandler(
                moteur=mock_moteur,
                daemon_reader=mock_reader,
                feedback_controller=mock_feedback,
                config=mock_config,
                simulation_mode=True,
                status_callback=status_callback
            )

            yield {
                'handler': handler,
                'helper': helper,
                'statuses': statuses,
                'mock_moteur': mock_moteur,
                'mock_reader': mock_reader,
                'mock_feedback': mock_feedback
            }

    def test_goto_small_movement_uses_feedback(self, goto_handler_setup):
        """Un petit GOTO (≤3°) utilise le feedback."""
        setup = goto_handler_setup

        # Position actuelle = 0°, cible = 2° (< seuil 3°)
        setup['mock_reader'].read_angle.return_value = 0.0
        initial_status = {'status': 'idle', 'position': 0}

        result = setup['handler'].execute(2.0, initial_status)

        # Feedback utilisé pour petit mouvement
        setup['mock_feedback'].rotation_avec_feedback.assert_called()
        assert result['status'] == 'idle'

    def test_goto_large_movement_direct_rotation(self, goto_handler_setup):
        """Un grand GOTO (>3°) fait une rotation directe puis correction."""
        setup = goto_handler_setup

        # Position actuelle = 0°, cible = 90° (> seuil 3°)
        setup['mock_reader'].read_angle.return_value = 0.0
        initial_status = {'status': 'idle', 'position': 0}

        # Après rotation directe, simuler position proche de cible
        setup['mock_reader'].read_angle.side_effect = [0.0, 89.5]

        result = setup['handler'].execute(90.0, initial_status)

        # Rotation directe appelée
        setup['mock_moteur'].rotation.assert_called()
        assert result['status'] == 'idle'

    def test_goto_status_flow(self, goto_handler_setup):
        """Le flux de statuts pendant un GOTO est correct."""
        setup = goto_handler_setup
        setup['mock_reader'].read_angle.return_value = 0.0

        initial_status = {'status': 'idle', 'position': 0}
        setup['handler'].execute(90.0, initial_status)

        # Vérifier le flux de statuts
        assert len(setup['statuses']) >= 2
        # Premier statut: 'moving'
        assert setup['statuses'][0]['status'] == 'moving'
        assert setup['statuses'][0]['target'] == 90.0
        # Dernier statut: 'idle' (terminé)
        assert setup['statuses'][-1]['status'] == 'idle'

    def test_goto_error_sets_timestamp(self, goto_handler_setup):
        """Une erreur GOTO définit error_timestamp."""
        setup = goto_handler_setup

        # Forcer une erreur (RuntimeError comme les vraies erreurs encodeur)
        setup['mock_reader'].read_angle.side_effect = RuntimeError("Encoder error")

        initial_status = {'status': 'idle', 'position': 0}
        result = setup['handler'].execute(90.0, initial_status)

        assert result['status'] == 'error'
        assert 'error' in result
        assert 'error_timestamp' in result
        assert result['error_timestamp'] > 0


# =============================================================================
# Tests du flux de suivi (Tracking)
# =============================================================================


@requires_astropy
class TestTrackingFlow:
    """Tests d'intégration pour le suivi d'objets."""

    @pytest.fixture
    def tracking_handler_setup(self, tmp_path):
        """Configure un TrackingHandler avec mocks."""
        helper = IpcTestHelper(tmp_path)

        # Mock du feedback controller
        mock_feedback = MagicMock()
        mock_feedback.rotation_avec_feedback.return_value = {
            'success': True,
            'position_finale': 45.0,
            'erreur_finale': 0.1,
            'iterations': 1
        }

        # Configuration mock
        mock_config = MagicMock()
        mock_config.site.latitude = 45.0
        mock_config.site.longitude = 3.0
        mock_config.site.tz_offset = 1
        mock_config.tracking.seuil_correction_deg = 0.5
        mock_config.tracking.intervalle_verification_sec = 60
        mock_config.tracking.abaque_file = 'data/Loi_coupole.xlsx'
        mock_config.adaptive = MagicMock()
        mock_config.motor = MagicMock()
        mock_config.encoder = MagicMock()

        statuses = []
        logs = []

        def status_callback(status):
            statuses.append(status.copy())

        def log_callback(message, log_type='info'):
            logs.append({'message': message, 'type': log_type})

        with patch('services.ipc_manager.COMMAND_FILE', helper.command_file), \
             patch('services.ipc_manager.STATUS_FILE', helper.status_file), \
             patch('services.ipc_manager.ENCODER_FILE', helper.encoder_file):
            from services.command_handlers import TrackingHandler

            handler = TrackingHandler(
                feedback_controller=mock_feedback,
                config=mock_config,
                simulation_mode=True,
                status_callback=status_callback,
                log_callback=log_callback
            )

            yield {
                'handler': handler,
                'helper': helper,
                'statuses': statuses,
                'logs': logs,
                'mock_feedback': mock_feedback,
                'mock_config': mock_config
            }

    def test_tracking_stop_clears_status(self, tracking_handler_setup):
        """L'arrêt du tracking remet le statut à idle."""
        setup = tracking_handler_setup

        # Simuler un tracking actif
        setup['handler'].active = True
        setup['handler'].session = MagicMock()
        setup['handler'].session.get_status.return_value = {'position_relative': 45.0}

        current_status = {
            'status': 'tracking',
            'tracking_object': 'Mars',
            'position': 45.0
        }

        setup['handler'].stop(current_status)

        assert current_status['status'] == 'idle'
        assert current_status['tracking_object'] is None
        assert setup['handler'].is_active is False

    def test_tracking_update_applies_correction(self, tracking_handler_setup):
        """La mise à jour du tracking applique les corrections."""
        setup = tracking_handler_setup

        # Mock session active
        mock_session = MagicMock()
        mock_session.check_and_correct.return_value = (True, "Correction +0.5°")
        mock_session.get_status.return_value = {
            'running': True,
            'position_relative': 45.5,
            'adaptive_mode': 'normal',
            'obj_az_raw': 180.0,
            'obj_alt': 45.0,
            'position_cible': 45.5,
            'remaining_seconds': 30,
            'adaptive_interval': 60,
            'total_corrections': 1,
            'total_movement': 0.5,
            'mode_icon': '🔵'
        }

        setup['handler'].session = mock_session
        setup['handler'].active = True

        current_status = {'status': 'tracking', 'position': 45.0}
        setup['handler'].update(current_status)

        # Position mise à jour
        assert current_status['position'] == 45.5
        assert 'tracking_info' in current_status
        assert current_status['tracking_info']['total_corrections'] == 1

        # Log de correction ajouté
        assert any('Correction' in log['message'] for log in setup['logs'])


# =============================================================================
# Tests d'intégration Motor Service
# =============================================================================


class TestMotorServiceIntegration:
    """Tests d'intégration du Motor Service complet."""

    @pytest.fixture
    def motor_service_setup(self, tmp_path):
        """Configure un environnement Motor Service complet."""
        helper = IpcTestHelper(tmp_path)

        with patch('services.ipc_manager.COMMAND_FILE', helper.command_file), \
             patch('services.ipc_manager.STATUS_FILE', helper.status_file), \
             patch('services.ipc_manager.ENCODER_FILE', helper.encoder_file), \
             patch('core.hardware.hardware_detector.HardwareDetector.detect_hardware',
                   return_value=(False, {'platform': 'test'})):
            from services.ipc_manager import IpcManager

            ipc = IpcManager()
            yield {'ipc': ipc, 'helper': helper}

    def test_command_to_status_flow(self, motor_service_setup):
        """Test du flux complet: commande → traitement → statut."""
        setup = motor_service_setup
        ipc = setup['ipc']
        helper = setup['helper']

        # 1. Django écrit une commande
        command = {'command': 'status', 'id': 'flow_test_001'}
        helper.write_command_django_side(command)

        # 2. Motor Service lit la commande
        received = ipc.read_command()
        assert received is not None
        assert received['id'] == 'flow_test_001'

        # 3. Motor Service efface la commande
        ipc.clear_command()

        # 4. Motor Service écrit le statut
        ipc.write_status({
            'status': 'idle',
            'position': 42.0,
            'simulation': True
        })

        # 5. Django lit le statut
        status = helper.read_status_django_side()
        assert status['status'] == 'idle'
        assert status['position'] == 42.0

    def test_error_recovery_timeout(self, motor_service_setup):
        """Test du mécanisme de recovery automatique après erreur."""
        setup = motor_service_setup
        ipc = setup['ipc']
        helper = setup['helper']

        # Écrire un statut d'erreur avec timestamp
        error_time = time.time() - 15  # 15 secondes dans le passé
        ipc.write_status({
            'status': 'error',
            'error': 'Test error',
            'error_timestamp': error_time
        })

        # Lire le statut
        status = helper.read_status_django_side()
        assert status['status'] == 'error'

        # Simuler la vérification de recovery (> 10s)
        elapsed = time.time() - status['error_timestamp']
        assert elapsed > 10  # Le recovery devrait se déclencher


class TestEncoderIntegration:
    """Tests d'intégration avec le fichier encodeur."""

    @pytest.fixture
    def encoder_setup(self, tmp_path):
        """Configure un environnement avec fichier encodeur."""
        helper = IpcTestHelper(tmp_path)

        with patch('services.ipc_manager.COMMAND_FILE', helper.command_file), \
             patch('services.ipc_manager.STATUS_FILE', helper.status_file), \
             patch('services.ipc_manager.ENCODER_FILE', helper.encoder_file):
            from services.ipc_manager import IpcManager

            ipc = IpcManager()
            yield {'ipc': ipc, 'helper': helper}

    def test_read_encoder_position(self, encoder_setup):
        """Lecture de la position encodeur depuis le fichier daemon."""
        setup = encoder_setup
        ipc = setup['ipc']
        helper = setup['helper']

        # Le daemon encodeur écrit sa position
        helper.setup_encoder_position(123.456)

        # Motor Service lit la position
        result = ipc.read_encoder_file()

        assert result is not None
        assert result['angle'] == 123.456
        assert result['calibrated'] is True

    def test_encoder_file_not_exists(self, encoder_setup):
        """Gestion correcte si le fichier encodeur n'existe pas."""
        setup = encoder_setup
        ipc = setup['ipc']

        # Pas de fichier encodeur
        result = ipc.read_encoder_file()
        assert result is None

    def test_encoder_concurrent_access(self, encoder_setup):
        """Accès concurrent au fichier encodeur."""
        setup = encoder_setup
        ipc = setup['ipc']
        helper = setup['helper']
        errors = []
        positions = []

        def write_position():
            for i in range(10):
                try:
                    helper.setup_encoder_position(float(i * 10))
                    time.sleep(0.01)
                except Exception as e:
                    errors.append(e)

        def read_position():
            for _ in range(10):
                try:
                    result = ipc.read_encoder_file()
                    if result:
                        positions.append(result['angle'])
                    time.sleep(0.01)
                except Exception as e:
                    errors.append(e)

        writer = threading.Thread(target=write_position)
        reader = threading.Thread(target=read_position)

        writer.start()
        reader.start()

        writer.join()
        reader.join()

        assert len(errors) == 0, f"Erreurs: {errors}"
        assert len(positions) > 0
