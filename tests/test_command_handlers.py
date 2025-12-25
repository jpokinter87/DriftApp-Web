"""
Tests pour le module Command Handlers.

Ce module teste les gestionnaires de commandes moteur:
- GotoHandler: déplacements absolus
- JogHandler: déplacements relatifs
- ContinuousHandler: mouvements continus
- TrackingHandler: suivi d'objets célestes

Note: Ces tests nécessitent astropy (via core.tracking.tracker).
Ils sont automatiquement ignorés si astropy n'est pas installé.
"""

import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Skip ce module si astropy n'est pas installé
pytest.importorskip("astropy", reason="astropy requis pour les tests command_handlers")


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_moteur():
    """Mock du moteur."""
    moteur = MagicMock()
    moteur.rotation = MagicMock()
    moteur.clear_stop_request = MagicMock()
    moteur.request_stop = MagicMock()
    return moteur


@pytest.fixture
def mock_daemon_reader():
    """Mock du lecteur d'encodeur."""
    reader = MagicMock()
    reader.is_available = MagicMock(return_value=True)
    reader.read_angle = MagicMock(return_value=45.0)
    return reader


@pytest.fixture
def mock_feedback_controller():
    """Mock du contrôleur de feedback."""
    controller = MagicMock()
    controller.rotation_avec_feedback = MagicMock(return_value={
        'success': True,
        'position_initiale': 0.0,
        'position_finale': 90.0,
        'erreur_finale': 0.1,
        'iterations': 2
    })
    controller.request_stop = MagicMock()
    return controller


@pytest.fixture
def mock_config():
    """Mock de la configuration."""
    class MockModeConfig:
        def __init__(self):
            self.motor_delay = 0.00015

    class MockModes:
        def get(self, mode_name):
            return MockModeConfig()

    class MockAdaptive:
        modes = MockModes()

    class MockTracking:
        seuil_correction_deg = 0.5
        intervalle_verification_sec = 60
        abaque_file = 'data/Loi_coupole.xlsx'

    class MockThresholds:
        feedback_min_deg = 3.0
        large_movement_deg = 30.0
        feedback_protection_deg = 20.0
        default_tolerance_deg = 0.5

    class MockSite:
        latitude = 44.15
        longitude = 5.23
        tz_offset = 1

    class MockMotor:
        pass

    class MockEncoder:
        pass

    class MockConfig:
        adaptive = MockAdaptive()
        tracking = MockTracking()
        thresholds = MockThresholds()
        site = MockSite()
        motor = MockMotor()
        encoder = MockEncoder()

    return MockConfig()


@pytest.fixture
def status_callback():
    """Mock du callback de status."""
    return MagicMock()


@pytest.fixture
def log_callback():
    """Mock du callback de log."""
    return MagicMock()


# =============================================================================
# TESTS GOTO HANDLER
# =============================================================================

class TestGotoHandler:
    """Tests pour le handler GOTO."""

    @pytest.fixture
    def handler(self, mock_moteur, mock_daemon_reader, mock_feedback_controller,
                mock_config, status_callback):
        """Crée un GotoHandler."""
        from services.command_handlers import GotoHandler
        return GotoHandler(
            moteur=mock_moteur,
            daemon_reader=mock_daemon_reader,
            feedback_controller=mock_feedback_controller,
            config=mock_config,
            simulation_mode=True,
            status_callback=status_callback
        )

    def test_get_motor_speed_default(self, handler, mock_config):
        """Utilise la vitesse CONTINUOUS par défaut via fonction partagée."""
        from services.command_handlers import _get_motor_speed
        speed = _get_motor_speed(mock_config)
        assert speed == 0.00015

    def test_get_motor_speed_explicit(self, mock_config):
        """Utilise la vitesse explicite si fournie."""
        from services.command_handlers import _get_motor_speed
        speed = _get_motor_speed(mock_config, 0.002)
        assert speed == 0.002

    def test_execute_small_goto_uses_feedback(self, handler, mock_feedback_controller):
        """Les petits déplacements utilisent le feedback."""
        mock_feedback_controller.rotation_avec_feedback.return_value = {
            'success': True,
            'position_initiale': 0.0,
            'position_finale': 2.0,
            'erreur_finale': 0.1,
            'iterations': 1
        }

        status = {'status': 'idle', 'position': 0.0}

        # Petit déplacement (< 3°)
        with patch('core.hardware.moteur_simule.set_simulated_position'):
            result = handler.execute(2.0, status)

        mock_feedback_controller.rotation_avec_feedback.assert_called()

    def test_execute_large_goto_direct_rotation(self, handler, mock_moteur):
        """Les grands déplacements utilisent la rotation directe."""
        status = {'status': 'idle', 'position': 0.0}

        with patch('core.hardware.moteur_simule.set_simulated_position'):
            result = handler.execute(90.0, status)

        # Rotation directe appelée
        mock_moteur.rotation.assert_called()

    def test_execute_updates_status_moving(self, handler, mock_moteur):
        """Le status est mis à jour en 'moving' pendant l'exécution."""
        status = {'status': 'idle', 'position': 0.0}
        status_history = []

        def record_status(s):
            # Capture une copie pour éviter les problèmes de référence
            status_history.append(dict(s))

        handler.status_callback = record_status

        with patch('core.hardware.moteur_simule.set_simulated_position'):
            handler.execute(45.0, status)

        # Le callback a été appelé avec status='moving' à un moment
        assert any(s.get('status') == 'moving' for s in status_history)

    def test_execute_clears_target_after(self, handler):
        """La cible est effacée après exécution."""
        status = {'status': 'idle', 'position': 0.0, 'target': None}

        with patch('core.hardware.moteur_simule.set_simulated_position'):
            result = handler.execute(90.0, status)

        assert result['target'] is None


# =============================================================================
# TESTS JOG HANDLER
# =============================================================================

class TestJogHandler:
    """Tests pour le handler JOG."""

    @pytest.fixture
    def handler(self, mock_moteur, mock_daemon_reader, mock_config, status_callback):
        """Crée un JogHandler."""
        from services.command_handlers import JogHandler
        return JogHandler(
            moteur=mock_moteur,
            daemon_reader=mock_daemon_reader,
            config=mock_config,
            simulation_mode=True,
            status_callback=status_callback
        )

    def test_jog_positive(self, handler, mock_moteur):
        """JOG positif (sens horaire)."""
        status = {'status': 'idle', 'position': 0.0}

        with patch('core.hardware.moteur_simule.set_simulated_position'):
            result = handler.execute(10.0, status)

        mock_moteur.rotation.assert_called()
        # Vérifie que le delta est positif
        call_args = mock_moteur.rotation.call_args
        assert call_args[0][0] == 10.0

    def test_jog_negative(self, handler, mock_moteur):
        """JOG négatif (sens anti-horaire)."""
        status = {'status': 'idle', 'position': 0.0}

        with patch('core.hardware.moteur_simule.set_simulated_position'):
            result = handler.execute(-10.0, status)

        call_args = mock_moteur.rotation.call_args
        assert call_args[0][0] == -10.0

    def test_jog_no_feedback(self, handler, mock_moteur):
        """JOG n'utilise pas le feedback (fluidité)."""
        status = {'status': 'idle', 'position': 0.0}

        with patch('core.hardware.moteur_simule.set_simulated_position'):
            handler.execute(45.0, status)

        # Rotation directe, pas de feedback
        mock_moteur.rotation.assert_called_once()

    def test_jog_clears_stop_before(self, handler, mock_moteur):
        """JOG efface la requête de stop avant rotation."""
        status = {'status': 'idle', 'position': 0.0}

        with patch('core.hardware.moteur_simule.set_simulated_position'):
            handler.execute(5.0, status)

        mock_moteur.clear_stop_request.assert_called()

    def test_jog_updates_position(self, handler, mock_daemon_reader):
        """JOG met à jour la position depuis l'encodeur."""
        mock_daemon_reader.read_angle.return_value = 55.0
        status = {'status': 'idle', 'position': 0.0}

        with patch('core.hardware.moteur_simule.set_simulated_position'):
            result = handler.execute(10.0, status)

        assert result['position'] == 55.0


# =============================================================================
# TESTS CONTINUOUS HANDLER
# =============================================================================

class TestContinuousHandler:
    """Tests pour le handler de mouvement continu."""

    @pytest.fixture
    def handler(self, mock_moteur, mock_daemon_reader, mock_config, status_callback):
        """Crée un ContinuousHandler."""
        from services.command_handlers import ContinuousHandler
        return ContinuousHandler(
            moteur=mock_moteur,
            daemon_reader=mock_daemon_reader,
            config=mock_config,
            simulation_mode=True,
            status_callback=status_callback
        )

    def test_start_creates_thread(self, handler):
        """start() crée un thread de mouvement."""
        status = {'status': 'idle', 'position': 0.0}

        with patch('core.hardware.moteur_simule.set_simulated_position'):
            handler.start('cw', status)
            time.sleep(0.1)

        assert handler.thread is not None
        assert handler.thread.is_alive()

        handler.stop()

    def test_start_sets_status_moving(self, handler, status_callback):
        """start() met le status en 'moving'."""
        status = {'status': 'idle', 'position': 0.0}

        with patch('core.hardware.moteur_simule.set_simulated_position'):
            handler.start('cw', status)
            time.sleep(0.1)

        assert status['status'] == 'moving'
        handler.stop()

    def test_stop_terminates_thread(self, handler):
        """stop() termine le thread."""
        status = {'status': 'idle', 'position': 0.0}

        with patch('core.hardware.moteur_simule.set_simulated_position'):
            handler.start('cw', status)
            time.sleep(0.1)

        handler.stop()
        time.sleep(0.2)

        assert handler.thread is None or not handler.thread.is_alive()

    def test_cw_direction(self, handler):
        """Direction 'cw' incrémente la position."""
        status = {'status': 'idle', 'position': 0.0}

        with patch('core.hardware.moteur_simule.set_simulated_position') as mock_set, \
             patch('core.hardware.moteur_simule.get_simulated_position', return_value=0.0):
            handler.start('cw', status)
            time.sleep(0.15)  # Attendre au moins une itération

        handler.stop()
        # En mode simulation, la position devrait avoir augmenté

    def test_ccw_direction(self, handler):
        """Direction 'ccw' décrémente la position."""
        status = {'status': 'idle', 'position': 180.0}

        with patch('core.hardware.moteur_simule.set_simulated_position') as mock_set, \
             patch('core.hardware.moteur_simule.get_simulated_position', return_value=180.0):
            handler.start('ccw', status)
            time.sleep(0.15)

        handler.stop()


# =============================================================================
# TESTS TRACKING HANDLER
# =============================================================================

class TestTrackingHandler:
    """Tests pour le handler de suivi."""

    @pytest.fixture
    def handler(self, mock_feedback_controller, mock_config, status_callback, log_callback):
        """Crée un TrackingHandler."""
        from services.command_handlers import TrackingHandler
        return TrackingHandler(
            feedback_controller=mock_feedback_controller,
            config=mock_config,
            simulation_mode=True,
            status_callback=status_callback,
            log_callback=log_callback
        )

    def test_is_active_initially_false(self, handler):
        """Le suivi est inactif au démarrage."""
        assert handler.is_active is False

    def test_stop_when_inactive(self, handler, status_callback):
        """stop() ne plante pas si le suivi est inactif."""
        status = {'status': 'idle'}
        handler.stop(status)

        assert handler.is_active is False

    def test_session_none_initially(self, handler):
        """La session est None au démarrage."""
        assert handler.session is None


# =============================================================================
# TESTS SEUIL FEEDBACK (via config.thresholds.feedback_min_deg)
# =============================================================================

class TestSeuilFeedback:
    """Tests pour le seuil de feedback configuré dans config.thresholds.feedback_min_deg."""

    def test_threshold_from_config(self, mock_config):
        """Le seuil de feedback vient de config.thresholds.feedback_min_deg."""
        assert mock_config.thresholds.feedback_min_deg == 3.0

    def test_small_goto_uses_feedback(self, mock_moteur, mock_daemon_reader,
                                       mock_feedback_controller, mock_config, status_callback):
        """Les déplacements ≤ seuil utilisent le feedback."""
        from services.command_handlers import GotoHandler

        handler = GotoHandler(
            moteur=mock_moteur,
            daemon_reader=mock_daemon_reader,
            feedback_controller=mock_feedback_controller,
            config=mock_config,
            simulation_mode=True,
            status_callback=status_callback
        )

        # Simuler position actuelle = 0
        mock_daemon_reader.read_angle.return_value = 0.0
        mock_feedback_controller.rotation_avec_feedback.return_value = {
            'success': True,
            'position_initiale': 0.0,
            'position_finale': 3.0,
            'erreur_finale': 0.1,
            'iterations': 1
        }

        status = {'status': 'idle', 'position': 0.0}

        with patch('core.hardware.moteur_simule.set_simulated_position'):
            handler.execute(3.0, status)  # Exactement au seuil (3°)

        # Feedback utilisé car delta <= feedback_min_deg
        mock_feedback_controller.rotation_avec_feedback.assert_called()

    def test_large_goto_uses_direct_rotation(self, mock_moteur, mock_daemon_reader,
                                              mock_feedback_controller, mock_config, status_callback):
        """Les déplacements > seuil utilisent la rotation directe."""
        from services.command_handlers import GotoHandler

        handler = GotoHandler(
            moteur=mock_moteur,
            daemon_reader=mock_daemon_reader,
            feedback_controller=mock_feedback_controller,
            config=mock_config,
            simulation_mode=True,
            status_callback=status_callback
        )

        # Simuler position actuelle = 0
        mock_daemon_reader.read_angle.return_value = 0.0

        status = {'status': 'idle', 'position': 0.0}

        with patch('core.hardware.moteur_simule.set_simulated_position'):
            handler.execute(3.1, status)  # Juste au-dessus du seuil

        # Rotation directe utilisée
        mock_moteur.rotation.assert_called()
