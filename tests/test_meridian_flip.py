"""
Tests pour le comportement au retournement méridien.

Ce module teste:
- Watchdog thread survit aux opérations bloquantes
- Tuple unpacking dans TrackingHandler.start()
- Normalisation position_relative (avec et sans feedback)
- Re-synchronisation encodeur après grand mouvement
- Détection et logging du transit méridien
- Lifecycle du flag is_large_movement_in_progress
- Timeout acceptable post-méridien (non compté comme échec)

Note: Ces tests nécessitent astropy (via core.tracking.tracker).
"""

import logging
import time
from unittest.mock import MagicMock, patch

import pytest

# Skip ce module si astropy n'est pas installé
pytest.importorskip("astropy", reason="astropy requis pour les tests meridian_flip")

pytestmark = pytest.mark.slow


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
    """Crée un MotorService en mode simulation."""
    with patch('services.motor_service.HardwareDetector.detect_hardware', return_value=(False, mock_hardware_info)), \
         patch('services.motor_service.HardwareDetector.get_hardware_summary', return_value='Test'), \
         patch('services.ipc_manager.COMMAND_FILE', tmp_path / 'command.json'), \
         patch('services.ipc_manager.STATUS_FILE', tmp_path / 'status.json'), \
         patch('services.ipc_manager.ENCODER_FILE', tmp_path / 'encoder.json'):
        from services.motor_service import MotorService
        return MotorService()


@pytest.fixture
def mock_config():
    """Mock de la configuration."""
    class MockModeConfig:
        def __init__(self):
            self.motor_delay = 0.00012

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
        steps_correction_factor = 1.0

    class MockEncoder:
        enabled = False

    class MockConfig:
        adaptive = MockAdaptive()
        tracking = MockTracking()
        thresholds = MockThresholds()
        site = MockSite()
        motor = MockMotor()
        encoder = MockEncoder()

    return MockConfig()


@pytest.fixture
def tracking_session():
    """Crée une TrackingSession avec la vraie config (pattern test_tracker_unit)."""
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
    logger = TrackingLogger()
    abaque_path = str(Path(__file__).parent.parent / 'data' / 'Loi_coupole.xlsx')

    session = TrackingSession(
        moteur=moteur,
        calc=calc,
        logger=logger,
        seuil=config.tracking.seuil_correction_deg,
        intervalle=config.tracking.intervalle_verification_sec,
        abaque_file=abaque_path,
        adaptive_config=config.adaptive,
        motor_config=config.motor,
        encoder_config=config.encoder,
    )
    return session


# =============================================================================
# TESTS WATCHDOG THREAD
# =============================================================================

class TestWatchdogThread:
    """Tests pour le thread watchdog dédié."""

    def test_watchdog_thread_starts(self, motor_service):
        """Le thread watchdog démarre quand le service démarre."""
        motor_service.running = True
        motor_service._start_watchdog_thread()

        if motor_service._watchdog_enabled:
            assert motor_service._watchdog_thread is not None
            assert motor_service._watchdog_thread.is_alive()
            assert motor_service._watchdog_thread.daemon is True
            assert motor_service._watchdog_thread.name == "watchdog-heartbeat"

        # Cleanup
        motor_service.running = False
        if motor_service._watchdog_thread:
            motor_service._watchdog_thread.join(timeout=2)

    def test_watchdog_thread_survives_blocking(self, motor_service):
        """Le thread watchdog continue pendant une opération bloquante."""
        motor_service.running = True
        motor_service._watchdog_enabled = True

        # Mock le notifier pour compter les appels
        call_count = []
        original_notify = motor_service._notify_systemd

        def counting_notify(msg):
            if msg == "WATCHDOG=1":
                call_count.append(1)
            original_notify(msg)

        motor_service._notify_systemd = counting_notify
        motor_service.WATCHDOG_INTERVAL = 0.1  # Rapide pour le test

        motor_service._start_watchdog_thread()

        # Simuler une opération bloquante de 0.5s sur le thread principal
        time.sleep(0.5)

        # Le watchdog devrait avoir envoyé plusieurs heartbeats
        assert len(call_count) >= 3, f"Watchdog n'a envoyé que {len(call_count)} heartbeats pendant le blocage"

        # Cleanup
        motor_service.running = False
        motor_service._watchdog_thread.join(timeout=2)

    def test_watchdog_thread_stops_when_running_false(self, motor_service):
        """Le thread watchdog s'arrête quand running=False."""
        motor_service.running = True
        motor_service._watchdog_enabled = True
        motor_service.WATCHDOG_INTERVAL = 0.05

        motor_service._start_watchdog_thread()
        assert motor_service._watchdog_thread.is_alive()

        motor_service.running = False
        motor_service._watchdog_thread.join(timeout=2)
        assert not motor_service._watchdog_thread.is_alive()

    def test_no_watchdog_in_main_loop(self, motor_service):
        """La boucle principale n'envoie plus de heartbeat (délégué au thread)."""
        import inspect
        from services.motor_service import MotorService
        source = inspect.getsource(MotorService.run)
        assert "last_watchdog_ping" not in source, \
            "La boucle principale ne devrait plus gérer le watchdog"


# =============================================================================
# TESTS TUPLE UNPACKING
# =============================================================================

class TestTrackingStartUnpacking:
    """Tests pour le décompactage du tuple retourné par session.start()."""

    @pytest.fixture
    def tracking_handler(self, mock_config):
        """Crée un TrackingHandler avec mocks."""
        from services.command_handlers import TrackingHandler
        return TrackingHandler(
            feedback_controller=MagicMock(),
            config=mock_config,
            simulation_mode=True,
            status_callback=MagicMock(),
            log_callback=MagicMock(),
        )

    def test_start_unpacks_tuple_success(self, tracking_handler):
        """TrackingHandler.start() détecte le succès via le tuple."""
        mock_session = MagicMock()
        mock_session.start.return_value = (True, "Suivi démarré: NGC 5033")
        mock_session.get_status.return_value = {
            "running": True, "encoder_offset": 0.5
        }

        with patch('services.command_handlers.TrackingSession', return_value=mock_session), \
             patch('services.command_handlers._get_rotate_log_func', return_value=MagicMock()):
            status = {"status": "idle", "tracking_object": None}
            tracking_handler.start("NGC 5033", status)

            assert status["status"] == "tracking"
            assert status["tracking_object"] == "NGC 5033"

    def test_start_unpacks_tuple_failure(self, tracking_handler):
        """TrackingHandler.start() détecte l'échec via le tuple."""
        mock_session = MagicMock()
        mock_session.start.return_value = (False, "Objet introuvable")

        with patch('services.command_handlers.TrackingSession', return_value=mock_session), \
             patch('services.command_handlers._get_rotate_log_func', return_value=MagicMock()):
            status = {"status": "idle", "tracking_object": None}
            tracking_handler.start("FAUX_OBJET", status)

            assert status["status"] == "idle"
            assert "introuvable" in status.get("error", "")


# =============================================================================
# TESTS NORMALISATION POSITION
# =============================================================================

class TestPositionNormalization:
    """Tests pour la normalisation de position_relative."""

    def test_sans_feedback_normalise_wraparound_positif(self, tracking_session):
        """position_relative normalisée après correction positive dépassant 360°."""
        tracking_session.position_relative = 350.0
        tracking_session.encoder_available = False

        tracking_session._apply_correction_sans_feedback(15.0, 0.002)

        assert abs(tracking_session.position_relative - 5.0) < 0.01, \
            f"Attendu 5.0°, obtenu {tracking_session.position_relative}°"

    def test_sans_feedback_normalise_wraparound_negatif(self, tracking_session):
        """position_relative normalisée après correction négative sous 0°."""
        tracking_session.position_relative = 10.0
        tracking_session.encoder_available = False

        tracking_session._apply_correction_sans_feedback(-15.0, 0.002)

        assert abs(tracking_session.position_relative - 355.0) < 0.01, \
            f"Attendu 355.0°, obtenu {tracking_session.position_relative}°"

    def test_avec_feedback_normalise(self, tracking_session):
        """_finaliser_correction normalise via % 360."""
        tracking_session.position_relative = 350.0

        tracking_session._finaliser_correction(15.0, 5.0)

        assert abs(tracking_session.position_relative - 5.0) < 0.01


# =============================================================================
# TESTS RE-SYNC ENCODEUR
# =============================================================================

class TestEncoderResync:
    """Tests pour la re-synchronisation de l'offset encodeur."""

    def test_resync_after_large_movement(self, tracking_session):
        """encoder_offset est recalculé après un grand mouvement."""
        tracking_session.encoder_available = True
        tracking_session.encoder_offset = 5.0
        tracking_session.position_relative = 100.0

        # Mock le moteur pour simuler une rotation feedback réussie
        mock_result = {
            'success': True,
            'position_initiale': 95.0,
            'position_finale': 135.0,
            'erreur_finale': 0.2,
            'iterations': 1,
            'corrections': [],
            'position_cible': 135.0,
        }
        tracking_session.moteur = MagicMock()
        tracking_session.moteur.rotation_avec_feedback = MagicMock(return_value=mock_result)

        # Mock get_daemon_angle pour la re-sync
        mock_reader = MagicMock()
        mock_reader.read_angle.return_value = 130.0

        with patch('core.hardware.daemon_encoder_reader.get_daemon_reader',
                   return_value=mock_reader):
            tracking_session._apply_correction_avec_feedback(35.0, 0.001)

            # Vérifier que encoder_offset a été recalculé
            # position_cible_logique = (100 + 35) % 360 = 135°
            # real_position = 130°
            # new_offset = 135 - 130 = 5°
            expected_offset = 135.0 - 130.0
            assert abs(tracking_session.encoder_offset - expected_offset) < 0.1, \
                f"Attendu offset={expected_offset}, obtenu {tracking_session.encoder_offset}"

    def test_no_resync_for_small_movement(self, tracking_session):
        """encoder_offset n'est PAS recalculé pour les petits mouvements."""
        tracking_session.encoder_available = True
        tracking_session.encoder_offset = 5.0
        tracking_session.position_relative = 100.0

        mock_result = {
            'success': True,
            'position_initiale': 95.0,
            'position_finale': 103.0,
            'erreur_finale': 0.1,
            'iterations': 1,
            'corrections': [],
            'position_cible': 103.0,
        }
        tracking_session.moteur = MagicMock()
        tracking_session.moteur.rotation_avec_feedback = MagicMock(return_value=mock_result)

        mock_reader = MagicMock()

        with patch('core.hardware.daemon_encoder_reader.get_daemon_reader',
                   return_value=mock_reader):
            tracking_session._apply_correction_avec_feedback(3.0, 0.001)

            # read_angle ne devrait PAS avoir été appelé (pas de re-sync)
            mock_reader.read_angle.assert_not_called()
            assert tracking_session.encoder_offset == 5.0


# =============================================================================
# TESTS DÉTECTION TRANSIT MÉRIDIEN
# =============================================================================

class TestMeridianTransitDetection:
    """Tests pour la détection et le logging du transit méridien."""

    def test_transit_logged_in_goto_log(self, tracking_session):
        """Un transit méridien est enregistré dans le goto_log."""
        tracking_session.position_relative = 246.0

        # Simuler un check_and_correct avec un grand delta
        # On appelle directement _log_goto pour vérifier le mécanisme
        tracking_session._log_goto(246.0, 112.0, -134.0, 'meridian_transit')

        assert len(tracking_session.drift_tracking['goto_log']) == 1
        entry = tracking_session.drift_tracking['goto_log'][0]
        assert entry['reason'] == 'meridian_transit'
        assert entry['delta'] == -134.0

    def test_transit_detection_log_message(self, tracking_session, caplog):
        """Le log TRANSIT MÉRIDIEN est émis quand delta > 30°."""
        tracking_session.running = True
        tracking_session.position_relative = 246.0
        tracking_session.next_correction_time = None

        # Mock les calculs pour forcer un grand delta
        tracking_session._calculate_current_coords = MagicMock(return_value=(180.0, 45.0))
        tracking_session._calculate_target_position = MagicMock(return_value=(112.0, {}))
        tracking_session.adaptive_manager.verify_shortest_path = MagicMock(
            return_value=(-134.0, {'direction': 'ccw'})
        )

        # Mock l'application de la correction pour ne rien faire
        tracking_session._apply_correction = MagicMock()
        tracking_session.adaptive_manager.evaluate_tracking_zone = MagicMock(
            return_value=MagicMock(
                correction_threshold=0.35,
                check_interval=5,
                motor_delay=0.00012,
                mode=MagicMock(value='continuous'),
            )
        )

        with caplog.at_level(logging.INFO, logger='core.tracking.tracker'):
            tracking_session.check_and_correct()

        transit_logs = [r for r in caplog.records if "meridian_transit |" in r.message]
        assert len(transit_logs) >= 1, \
            f"Aucun log 'meridian_transit' trouvé. Logs: {[r.message for r in caplog.records]}"

    def test_no_transit_for_small_delta(self, tracking_session):
        """Pas de log transit pour les petits deltas."""
        tracking_session.running = True
        tracking_session.position_relative = 100.0
        tracking_session.next_correction_time = None

        tracking_session._calculate_current_coords = MagicMock(return_value=(180.0, 45.0))
        tracking_session._calculate_target_position = MagicMock(return_value=(102.0, {}))
        tracking_session.adaptive_manager.verify_shortest_path = MagicMock(
            return_value=(2.0, {'direction': 'cw'})
        )
        tracking_session._apply_correction = MagicMock()
        tracking_session.adaptive_manager.evaluate_tracking_zone = MagicMock(
            return_value=MagicMock(
                correction_threshold=0.35,
                check_interval=60,
                motor_delay=0.002,
                mode=MagicMock(value='normal'),
            )
        )

        initial_goto_count = len(tracking_session.drift_tracking['goto_log'])
        tracking_session.check_and_correct()

        # Pas de nouvel entry meridian_transit
        meridian_entries = [
            e for e in tracking_session.drift_tracking['goto_log'][initial_goto_count:]
            if e.get('reason') == 'meridian_transit'
        ]
        assert len(meridian_entries) == 0


# =============================================================================
# TESTS FLAG LARGE MOVEMENT
# =============================================================================

class TestLargeMovementFlag:
    """Tests pour le lifecycle de is_large_movement_in_progress."""

    def test_flag_set_during_large_correction(self, tracking_session):
        """is_large_movement_in_progress est True pendant un grand mouvement."""
        tracking_session.encoder_available = True
        tracking_session.position_relative = 100.0

        flag_during_rotation = []

        original_rotation = MagicMock(return_value={
            'success': True,
            'position_initiale': 65.0,
            'position_finale': 100.0,
            'erreur_finale': 0.2,
            'iterations': 1,
            'corrections': [],
            'position_cible': 100.0,
        })

        def capture_flag(*args, **kwargs):
            flag_during_rotation.append(tracking_session.is_large_movement_in_progress)
            return original_rotation(*args, **kwargs)

        tracking_session.moteur = MagicMock()
        tracking_session.moteur.rotation_avec_feedback = capture_flag

        mock_reader = MagicMock()
        mock_reader.read_angle.return_value = 135.0

        with patch('core.hardware.daemon_encoder_reader.get_daemon_reader',
                   return_value=mock_reader):
            tracking_session._apply_correction_avec_feedback(35.0, 0.001)

        assert flag_during_rotation[0] is True, "Flag devrait être True pendant la rotation"
        assert tracking_session.is_large_movement_in_progress is False, \
            "Flag devrait être False après la rotation"

    def test_flag_not_set_for_small_correction(self, tracking_session):
        """is_large_movement_in_progress reste False pour les petites corrections."""
        tracking_session.encoder_available = True
        tracking_session.position_relative = 100.0

        mock_result = {
            'success': True,
            'position_initiale': 95.0,
            'position_finale': 103.0,
            'erreur_finale': 0.1,
            'iterations': 1,
            'corrections': [],
            'position_cible': 103.0,
        }
        tracking_session.moteur = MagicMock()
        tracking_session.moteur.rotation_avec_feedback = MagicMock(return_value=mock_result)

        tracking_session._apply_correction_avec_feedback(3.0, 0.001)

        assert tracking_session.is_large_movement_in_progress is False


# =============================================================================
# TESTS TIMEOUT ACCEPTABLE
# =============================================================================

class TestTimeoutAcceptable:
    """Tests pour le timeout acceptable post-méridien."""

    def test_timeout_with_small_error_not_counted(self, tracking_session):
        """Timeout avec erreur < 2° ne compte pas comme échec."""
        tracking_session.failed_feedback_count = 0

        result = {
            'success': False,
            'timeout': True,
            'erreur_finale': 1.5,
            'position_initiale': 100.0,
            'position_finale': 234.0,
            'position_cible': 235.0,
            'iterations': 10,
            'corrections': [],
        }

        tracking_session._traiter_resultat_feedback(result, 95.0)

        assert tracking_session.failed_feedback_count == 0, \
            "Un timeout avec erreur < 2° ne devrait pas incrémenter le compteur"

    def test_timeout_with_large_error_counted(self, tracking_session):
        """Timeout avec erreur >= 2° compte comme échec."""
        tracking_session.failed_feedback_count = 0

        result = {
            'success': False,
            'timeout': True,
            'erreur_finale': 3.5,
            'position_initiale': 100.0,
            'position_finale': 231.0,
            'position_cible': 235.0,
            'iterations': 10,
            'corrections': [],
        }

        tracking_session._traiter_resultat_feedback(result, 95.0)

        assert tracking_session.failed_feedback_count == 1, \
            "Un timeout avec erreur >= 2° devrait incrémenter le compteur"
