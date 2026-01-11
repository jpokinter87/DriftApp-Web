"""
Tests pour le module core/tracking/tracker.py

Ce module teste le gestionnaire de session de suivi.
Ces tests fonctionnent SANS astropy grâce au mocking des dépendances.
"""

import sys
import pytest
from datetime import datetime, timezone
from collections import deque
from unittest.mock import MagicMock, patch, PropertyMock


# =============================================================================
# SETUP: Mock des dépendances astropy AVANT tout import
# =============================================================================

# Créer les mocks pour les modules qui dépendent d'astropy
_mock_astropy = MagicMock()
_mock_astropy_time = MagicMock()
_mock_astropy_coords = MagicMock()

# Mock pour AstronomicalCalculations
class MockAstronomicalCalculations:
    """Mock de AstronomicalCalculations sans astropy."""
    def __init__(self, latitude=44.15, longitude=5.23, tz_offset=1):
        self.latitude = latitude
        self.longitude = longitude
        self.tz_offset = tz_offset

    def calculer_coords_horizontales(self, ra, dec, dt):
        return (120.0, 45.0)

    def calculer_coords_horizontales_coupole(self, ra, dec, dt):
        return (122.0, 45.0, 2.0)

    def convertir_j2000_vers_jnow(self, ra, dec, dt):
        return (ra, dec)


# Mock pour PlanetaryEphemerides
class MockPlanetaryEphemerides:
    """Mock de PlanetaryEphemerides sans astropy."""
    def get_planet_position(self, planet_name, dt, lat, lon):
        return (250.0, 36.0)


# Mock du module observatoire
_mock_observatoire = MagicMock()
_mock_observatoire.AstronomicalCalculations = MockAstronomicalCalculations
_mock_observatoire.PlanetaryEphemerides = MockPlanetaryEphemerides


@pytest.fixture(autouse=True)
def mock_astropy_modules():
    """
    Injecte les mocks dans sys.modules AVANT que les tests n'importent les modules.
    Cela permet aux tests de fonctionner sans astropy installé.
    """
    # Sauvegarder les modules existants
    saved_modules = {}
    modules_to_mock = [
        'astropy',
        'astropy.time',
        'astropy.coordinates',
        'astropy.units',
    ]

    for mod in modules_to_mock:
        if mod in sys.modules:
            saved_modules[mod] = sys.modules[mod]

    # Injecter les mocks
    sys.modules['astropy'] = _mock_astropy
    sys.modules['astropy.time'] = _mock_astropy_time
    sys.modules['astropy.coordinates'] = _mock_astropy_coords
    sys.modules['astropy.units'] = MagicMock()

    # Aussi patcher le module observatoire pour utiliser nos mocks
    with patch.dict('sys.modules', {
        'lgpio': MagicMock(),
        'RPi': MagicMock(),
        'RPi.GPIO': MagicMock(),
        'spidev': MagicMock(),
    }):
        yield

    # Restaurer les modules originaux
    for mod in modules_to_mock:
        if mod in saved_modules:
            sys.modules[mod] = saved_modules[mod]
        elif mod in sys.modules:
            del sys.modules[mod]


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_moteur():
    """Mock pour MoteurCoupole."""
    moteur = MagicMock()
    moteur.steps_per_dome_revolution = 1942968
    moteur.stop_requested = False
    moteur.rotation = MagicMock()
    moteur.rotation_avec_feedback = MagicMock(return_value={
        'success': True,
        'position_finale': 90.0,
        'erreur_finale': 0.1,
        'position_initiale': 85.0,
        'position_cible': 90.0,
        'iterations': 1,
        'corrections': []
    })
    moteur.request_stop = MagicMock()
    moteur.clear_stop_request = MagicMock()
    return moteur


@pytest.fixture
def mock_calc():
    """Mock pour AstronomicalCalculations."""
    return MockAstronomicalCalculations()


@pytest.fixture
def mock_tracking_logger():
    """Mock pour TrackingLogger."""
    logger = MagicMock()
    logger.log_correction = MagicMock()
    logger.log_session_start = MagicMock()
    logger.log_session_end = MagicMock()
    logger.start_tracking = MagicMock()
    logger.stop_tracking = MagicMock()
    return logger


@pytest.fixture
def mock_abaque_manager():
    """Mock pour AbaqueManager."""
    manager = MagicMock()
    manager.load_abaque.return_value = True
    manager.is_loaded = True
    manager.get_dome_position.return_value = (125.0, {
        'method': 'interpolation',
        'in_bounds': True
    })
    return manager


@pytest.fixture
def mock_encoder_config():
    """Mock pour encoder config."""
    config = MagicMock()
    config.enabled = False
    return config


@pytest.fixture
def mock_motor_config():
    """Mock pour motor config."""
    config = MagicMock()
    config.steps_correction_factor = 1.08849
    return config


@pytest.fixture
def tracking_session(
    mock_moteur, mock_calc, mock_tracking_logger,
    mock_encoder_config, mock_motor_config, mock_abaque_manager
):
    """Crée une TrackingSession avec toutes les dépendances mockées."""
    # Créer les mocks des modules qui dépendent de numpy/pandas
    mock_abaque_module = MagicMock()
    mock_abaque_module.AbaqueManager = MagicMock(return_value=mock_abaque_manager)

    # Mock du AdaptiveTrackingManager
    mock_adaptive = MagicMock()
    mock_adaptive.current_mode = MagicMock()
    mock_adaptive.current_mode.value = 'normal'
    mock_adaptive.evaluate_tracking_zone.return_value = MagicMock(
        mode=MagicMock(value='normal'),
        check_interval=60,
        correction_threshold=0.5,
        motor_delay=0.002,
        description="Test mode"
    )
    mock_adaptive.verify_shortest_path.return_value = (5.0, "horaire (5.0°)")
    mock_adaptive.get_diagnostic_info.return_value = {
        'mode': 'normal',
        'mode_description': 'Normal',
        'check_interval': 60,
        'correction_threshold': 0.5,
        'motor_delay': 0.002,
        'in_critical_zone': False,
        'is_high_altitude': False,
        'is_large_movement': False
    }

    mock_adaptive_module = MagicMock()
    mock_adaptive_module.AdaptiveTrackingManager = MagicMock(return_value=mock_adaptive)

    # Nettoyer le cache d'imports pour forcer le rechargement
    mods_to_remove = [m for m in sys.modules if m.startswith('core.tracking.tracker')]
    for m in mods_to_remove:
        del sys.modules[m]

    # Injecter les mocks dans sys.modules AVANT l'import
    with patch.dict('sys.modules', {
        'numpy': MagicMock(),
        'pandas': MagicMock(),
        'core.tracking.abaque_manager': mock_abaque_module,
    }):
        # Patcher les imports au niveau du module tracker
        with patch('core.tracking.tracker.AdaptiveTrackingManager', MagicMock(return_value=mock_adaptive)):
            with patch('core.hardware.moteur.MoteurCoupole'):
                with patch('core.hardware.hardware_detector.HardwareDetector'):
                    # Import après le patching
                    from core.tracking.tracker import TrackingSession

                    session = TrackingSession(
                        moteur=mock_moteur,
                        calc=mock_calc,
                        logger=mock_tracking_logger,
                        seuil=0.5,
                        intervalle=60,
                        abaque_file="data/Loi_coupole.xlsx",
                        encoder_config=mock_encoder_config,
                        motor_config=mock_motor_config
                    )

                    return session


# =============================================================================
# TESTS INITIALISATION
# =============================================================================

class TestTrackingSessionInit:
    """Tests pour l'initialisation de TrackingSession."""

    def test_init_sans_abaque_leve_erreur(
        self, mock_moteur, mock_calc, mock_tracking_logger,
        mock_encoder_config, mock_motor_config
    ):
        """Lève ValueError si abaque_file non fourni."""
        from core.tracking.tracker import TrackingSession

        with pytest.raises(ValueError, match="abaque_file requis"):
            TrackingSession(
                moteur=mock_moteur,
                calc=mock_calc,
                logger=mock_tracking_logger,
                abaque_file=None,
                encoder_config=mock_encoder_config,
                motor_config=mock_motor_config
            )

    def test_init_avec_abaque_valide(self, tracking_session):
        """Initialisation réussie avec abaque valide."""
        assert tracking_session.seuil == 0.5
        assert tracking_session.intervalle == 60
        assert tracking_session.running is False

    def test_init_etat_initial(self, tracking_session):
        """Vérifie l'état initial après initialisation."""
        assert tracking_session.objet is None
        assert tracking_session.ra_deg is None
        assert tracking_session.dec_deg is None
        assert tracking_session.is_planet is False
        assert tracking_session.position_relative == 0.0
        assert tracking_session.total_corrections == 0
        assert tracking_session.total_movement == 0.0


# =============================================================================
# TESTS ENCODEUR
# =============================================================================

class TestTrackingSessionEncoder:
    """Tests pour la gestion de l'encodeur."""

    def test_encoder_desactive(
        self, mock_moteur, mock_calc, mock_tracking_logger,
        mock_motor_config, mock_abaque_manager
    ):
        """Encodeur désactivé dans la config."""
        encoder_config = MagicMock()
        encoder_config.enabled = False

        # Créer mock module pour abaque_manager
        mock_abaque_module = MagicMock()
        mock_abaque_module.AbaqueManager = MagicMock(return_value=mock_abaque_manager)

        with patch.dict('sys.modules', {
            'numpy': MagicMock(),
            'pandas': MagicMock(),
            'core.tracking.abaque_manager': mock_abaque_module,
        }):
            with patch('core.tracking.tracker.AdaptiveTrackingManager'):
                from core.tracking.tracker import TrackingSession

                session = TrackingSession(
                    moteur=mock_moteur,
                    calc=mock_calc,
                    logger=mock_tracking_logger,
                    abaque_file="data/Loi_coupole.xlsx",
                    encoder_config=encoder_config,
                    motor_config=mock_motor_config
                )

                assert session.encoder_available is False

    def test_encoder_active_et_disponible(
        self, mock_moteur, mock_calc, mock_tracking_logger,
        mock_motor_config, mock_abaque_manager
    ):
        """Encodeur activé et daemon disponible."""
        encoder_config = MagicMock()
        encoder_config.enabled = True

        # Créer mock module pour abaque_manager
        mock_abaque_module = MagicMock()
        mock_abaque_module.AbaqueManager = MagicMock(return_value=mock_abaque_manager)

        with patch.dict('sys.modules', {
            'numpy': MagicMock(),
            'pandas': MagicMock(),
            'core.tracking.abaque_manager': mock_abaque_module,
        }):
            with patch('core.tracking.tracker.AdaptiveTrackingManager'):
                with patch('core.hardware.hardware_detector.HardwareDetector') as mock_hw:
                    # Patcher MoteurCoupole au niveau du module moteur (utilisé par _get_encoder_angle)
                    with patch('core.hardware.moteur.MoteurCoupole') as mock_moteur_cls:
                        mock_hw.check_encoder_daemon.return_value = (True, None, 45.0)
                        mock_moteur_cls.get_daemon_angle.return_value = 45.0

                        from core.tracking.tracker import TrackingSession

                        session = TrackingSession(
                            moteur=mock_moteur,
                            calc=mock_calc,
                            logger=mock_tracking_logger,
                            abaque_file="data/Loi_coupole.xlsx",
                            encoder_config=encoder_config,
                            motor_config=mock_motor_config
                        )

                        assert session.encoder_available is True


# =============================================================================
# TESTS CALCUL COORDONNÉES
# =============================================================================

class TestCalculateCurrentCoords:
    """Tests pour _calculate_current_coords."""

    def test_calculate_coords_etoile(self, tracking_session, mock_calc):
        """Calcul pour une étoile (coordonnées fixes)."""
        tracking_session.is_planet = False
        tracking_session.ra_deg = 250.0
        tracking_session.dec_deg = 36.0

        now = datetime(2025, 6, 21, 22, 0, 0)
        az, alt = tracking_session._calculate_current_coords(now)

        # MockAstronomicalCalculations retourne toujours (120.0, 45.0)
        assert az == 120.0
        assert alt == 45.0


# =============================================================================
# TESTS STATISTIQUES ET ÉTAT
# =============================================================================

class TestTrackingSessionState:
    """Tests pour la gestion de l'état."""

    def test_correction_history_deque(self, tracking_session):
        """L'historique des corrections est une deque limitée."""
        assert isinstance(tracking_session.correction_history, deque)
        assert tracking_session.correction_history.maxlen == 10

    def test_position_cible_history_deque(self, tracking_session):
        """L'historique des positions cibles est une deque limitée."""
        assert isinstance(tracking_session._position_cible_history, deque)
        assert tracking_session._position_cible_history.maxlen == 5

    def test_drift_tracking_structure(self, tracking_session):
        """Structure du suivi de dérive."""
        assert 'start_time' in tracking_session.drift_tracking
        assert 'corrections_log' in tracking_session.drift_tracking
        assert isinstance(tracking_session.drift_tracking['corrections_log'], list)


# =============================================================================
# TESTS PROTECTION OSCILLATIONS
# =============================================================================

class TestOscillationProtection:
    """Tests pour la protection contre les oscillations."""

    def test_oscillation_count_initial(self, tracking_session):
        """Compteur d'oscillations initialisé à 0."""
        assert tracking_session.oscillation_count == 0

    def test_consecutive_errors_initial(self, tracking_session):
        """Compteur d'erreurs consécutives initialisé à 0."""
        assert tracking_session.consecutive_errors == 0

    def test_max_consecutive_errors(self, tracking_session):
        """Limite max d'erreurs consécutives."""
        assert tracking_session.max_consecutive_errors == 5

    def test_failed_feedback_count_initial(self, tracking_session):
        """Compteur de feedback échoués initialisé à 0."""
        assert tracking_session.failed_feedback_count == 0


# =============================================================================
# TESTS INTÉGRATION ABAQUE
# =============================================================================

class TestAbaqueIntegration:
    """Tests pour l'intégration avec l'abaque."""

    def test_abaque_manager_cree(self, tracking_session):
        """AbaqueManager est créé et chargé."""
        assert tracking_session.abaque_manager is not None
        assert tracking_session.abaque_manager.is_loaded is True

    def test_calculate_target_position_utilise_abaque(self, tracking_session):
        """_calculate_target_position utilise l'abaque."""
        tracking_session.abaque_manager.get_dome_position.return_value = (130.0, {
            'method': 'interpolation',
            'in_bounds': True
        })

        result, infos = tracking_session._calculate_target_position(120.0, 45.0)
        tracking_session.abaque_manager.get_dome_position.assert_called()
        assert result == 130.0


# =============================================================================
# TESTS INTÉGRATION ADAPTIVE
# =============================================================================

class TestAdaptiveIntegration:
    """Tests pour l'intégration avec le système adaptatif."""

    def test_adaptive_manager_cree(self, tracking_session):
        """AdaptiveTrackingManager est créé."""
        assert tracking_session.adaptive_manager is not None


# =============================================================================
# TESTS GET STATUS
# =============================================================================

class TestGetStatus:
    """Tests pour get_status."""

    def test_get_status_quand_non_running(self, tracking_session):
        """get_status quand la session n'est pas active."""
        tracking_session.running = False

        status = tracking_session.get_status()
        assert isinstance(status, dict)
        assert status.get('running') is False


# =============================================================================
# TESTS PARAMÈTRES CORRECTIONS
# =============================================================================

class TestCorrectionParameters:
    """Tests pour les paramètres de correction."""

    def test_seuil_configure(self, tracking_session):
        """Le seuil est correctement configuré."""
        assert tracking_session.seuil == 0.5

    def test_intervalle_configure(self, tracking_session):
        """L'intervalle est correctement configuré."""
        assert tracking_session.intervalle == 60

    def test_steps_correction_factor(self, tracking_session):
        """Le facteur de correction des pas est configuré."""
        assert tracking_session.steps_correction_factor == 1.08849


# =============================================================================
# TESTS LISSAGE POSITION
# =============================================================================

class TestSmoothPositionCible:
    """Tests pour _smooth_position_cible."""

    def test_premiere_valeur_retournee_directement(self, tracking_session):
        """La première valeur est retournée sans lissage."""
        result = tracking_session._smooth_position_cible(45.0)
        assert result == 45.0

    def test_valeurs_proches_sont_lissees(self, tracking_session):
        """Les valeurs proches sont moyennées."""
        tracking_session._smooth_position_cible(45.0)
        tracking_session._smooth_position_cible(45.5)
        result = tracking_session._smooth_position_cible(44.5)

        # La moyenne devrait être proche de 45.0
        assert 44.0 <= result <= 46.0

    def test_grand_saut_reset_historique(self, tracking_session):
        """Un grand saut (>10°) réinitialise l'historique."""
        tracking_session._smooth_position_cible(45.0)
        tracking_session._smooth_position_cible(46.0)

        # Grand saut
        result = tracking_session._smooth_position_cible(180.0)

        # Devrait retourner 180.0 directement (reset)
        assert result == 180.0

    def test_normalisation_360(self, tracking_session):
        """Les angles sont normalisés dans [0, 360)."""
        result = tracking_session._smooth_position_cible(400.0)
        assert 0 <= result < 360


# =============================================================================
# TESTS CORRECTIONS
# =============================================================================

class TestCheckAndCorrect:
    """Tests pour check_and_correct."""

    def test_retourne_false_si_non_running(self, tracking_session):
        """Retourne (False, message) si le suivi n'est pas actif."""
        tracking_session.running = False
        applied, message = tracking_session.check_and_correct()
        assert applied is False
        assert "non actif" in message.lower()

    def test_retourne_false_si_pas_encore_temps(self, tracking_session):
        """Retourne (False, '') si next_correction_time n'est pas atteint."""
        from datetime import datetime, timedelta
        tracking_session.running = True
        tracking_session.next_correction_time = datetime.now() + timedelta(seconds=60)

        applied, message = tracking_session.check_and_correct()
        assert applied is False
        assert message == ""

    def test_retourne_false_si_delta_sous_seuil(self, tracking_session):
        """Retourne (False, message) si delta < seuil."""
        from datetime import datetime
        tracking_session.running = True
        tracking_session.next_correction_time = None
        tracking_session.ra_deg = 250.0
        tracking_session.dec_deg = 36.0
        tracking_session.is_planet = False
        tracking_session.position_relative = 125.0  # Proche de la position cible (125.0)

        # Mock adaptive_manager pour retourner delta = 0
        tracking_session.adaptive_manager.verify_shortest_path.return_value = (0.1, "direct")

        applied, message = tracking_session.check_and_correct()
        assert applied is False
        assert "seuil" in message.lower()

    def test_applique_correction_si_delta_depasse_seuil(self, tracking_session):
        """Applique une correction si delta > seuil."""
        from datetime import datetime
        tracking_session.running = True
        tracking_session.next_correction_time = None
        tracking_session.ra_deg = 250.0
        tracking_session.dec_deg = 36.0
        tracking_session.is_planet = False
        tracking_session.position_relative = 120.0  # 5° de delta

        # Mock adaptive_manager pour retourner delta = 5.0
        tracking_session.adaptive_manager.verify_shortest_path.return_value = (5.0, "horaire (5.0°)")

        applied, message = tracking_session.check_and_correct()
        assert applied is True
        assert "Correction" in message


class TestApplyCorrection:
    """Tests pour _apply_correction."""

    def test_utilise_feedback_si_encoder_disponible(self, tracking_session):
        """Utilise feedback si encoder_available est True."""
        tracking_session.encoder_available = True
        tracking_session.encoder_offset = 0.0
        tracking_session.position_relative = 100.0

        # Mock rotation_avec_feedback
        tracking_session.moteur.rotation_avec_feedback.return_value = {
            'success': True,
            'position_initiale': 100.0,
            'position_finale': 105.0,
            'erreur_finale': 0.1,
            'position_cible': 105.0,
            'iterations': 1,
            'corrections': []
        }

        tracking_session._apply_correction(5.0, 0.002)

        tracking_session.moteur.rotation_avec_feedback.assert_called_once()

    def test_utilise_rotation_simple_sans_encoder(self, tracking_session):
        """Utilise rotation simple si encoder_available est False."""
        tracking_session.encoder_available = False
        tracking_session.position_relative = 100.0

        tracking_session._apply_correction(5.0, 0.002)

        # Vérifie que definir_direction a été appelé
        tracking_session.moteur.definir_direction.assert_called()


class TestCalculerCibles:
    """Tests pour _calculer_cibles."""

    def test_calcul_position_cible_logique(self, tracking_session):
        """Calcule correctement la position cible logique."""
        tracking_session.position_relative = 100.0
        tracking_session.encoder_offset = 0.0

        pos_logique, angle_encodeur = tracking_session._calculer_cibles(5.0)

        assert pos_logique == 105.0
        assert angle_encodeur == 105.0

    def test_calcul_avec_offset_encodeur(self, tracking_session):
        """Prend en compte l'offset encodeur."""
        tracking_session.position_relative = 100.0
        tracking_session.encoder_offset = 10.0  # Offset de 10°

        pos_logique, angle_encodeur = tracking_session._calculer_cibles(5.0)

        assert pos_logique == 105.0
        assert angle_encodeur == 95.0  # 105 - 10

    def test_normalisation_360(self, tracking_session):
        """Les angles sont normalisés dans [0, 360)."""
        tracking_session.position_relative = 355.0
        tracking_session.encoder_offset = 0.0

        pos_logique, angle_encodeur = tracking_session._calculer_cibles(10.0)

        assert pos_logique == 5.0  # 365 % 360
        assert angle_encodeur == 5.0


class TestVerifierEchecsConsecutifs:
    """Tests pour _verifier_echecs_consecutifs."""

    def test_retourne_false_si_sous_limite(self, tracking_session):
        """Retourne False si échecs < max_failed_feedback."""
        tracking_session.running = True  # Initialiser à True
        tracking_session.failed_feedback_count = 2
        tracking_session.max_failed_feedback = 3

        result = tracking_session._verifier_echecs_consecutifs()
        assert result is False
        assert tracking_session.running is True  # Pas modifié, toujours True

    def test_arrete_suivi_si_limite_atteinte(self, tracking_session):
        """Arrête le suivi et retourne True si limite atteinte."""
        tracking_session.running = True
        tracking_session.failed_feedback_count = 3
        tracking_session.max_failed_feedback = 3

        result = tracking_session._verifier_echecs_consecutifs()
        assert result is True


class TestNotifyDegradedMode:
    """Tests pour _notify_degraded_mode."""

    def test_notifie_une_seule_fois(self, tracking_session):
        """La notification n'est envoyée qu'une seule fois."""
        # Première notification
        tracking_session._notify_degraded_mode()
        assert tracking_session._degraded_mode_notified is True

        # Deuxième appel - le flag devrait déjà être True
        tracking_session._notify_degraded_mode()

        # Le flag est toujours True (pas de double notification)
        assert tracking_session._degraded_mode_notified is True

    def test_initialise_attribut_si_absent(self, tracking_session):
        """Initialise _degraded_mode_notified s'il n'existe pas."""
        # S'assurer que l'attribut n'existe pas
        if hasattr(tracking_session, '_degraded_mode_notified'):
            delattr(tracking_session, '_degraded_mode_notified')

        tracking_session._notify_degraded_mode()
        assert hasattr(tracking_session, '_degraded_mode_notified')
        assert tracking_session._degraded_mode_notified is True


class TestTraiterResultatFeedback:
    """Tests pour _traiter_resultat_feedback."""

    def test_succes_reinitialise_compteur_echecs(self, tracking_session):
        """Un succès réinitialise le compteur d'échecs."""
        tracking_session.failed_feedback_count = 2

        result = {
            'success': True,
            'position_initiale': 100.0,
            'position_finale': 105.0,
            'erreur_finale': 0.1,
            'position_cible': 105.0,
            'iterations': 1,
            'corrections': []
        }

        tracking_session._traiter_resultat_feedback(result, 1.0)
        assert tracking_session.failed_feedback_count == 0

    def test_echec_incremente_compteur(self, tracking_session):
        """Un échec incrémente le compteur d'échecs."""
        tracking_session.failed_feedback_count = 0
        tracking_session.running = True

        result = {
            'success': False,
            'position_initiale': 100.0,
            'position_finale': 103.0,
            'erreur_finale': 5.0,  # Erreur > ACCEPTABLE_ERROR_THRESHOLD
            'position_cible': 105.0,
            'iterations': 10,
            'corrections': [],
            'timeout': False
        }

        tracking_session._traiter_resultat_feedback(result, 1.0)
        assert tracking_session.failed_feedback_count == 1

    def test_timeout_avec_erreur_acceptable_pas_echec(self, tracking_session):
        """Timeout avec erreur acceptable n'est pas compté comme échec."""
        tracking_session.failed_feedback_count = 0

        result = {
            'success': False,
            'position_initiale': 100.0,
            'position_finale': 104.5,
            'erreur_finale': 0.5,  # < ACCEPTABLE_ERROR_THRESHOLD (2.0)
            'position_cible': 105.0,
            'iterations': 10,
            'corrections': [],
            'timeout': True
        }

        tracking_session._traiter_resultat_feedback(result, 1.0)
        assert tracking_session.failed_feedback_count == 0


class TestApplyCorrectionSansFeedback:
    """Tests pour _apply_correction_sans_feedback."""

    def test_met_a_jour_position_relative(self, tracking_session):
        """Met à jour position_relative après correction."""
        tracking_session.position_relative = 100.0
        tracking_session._apply_correction_sans_feedback(5.0, 0.002)

        assert tracking_session.position_relative == 105.0

    def test_incremente_statistiques(self, tracking_session):
        """Incrémente total_corrections et total_movement."""
        tracking_session.position_relative = 100.0
        tracking_session.total_corrections = 0
        tracking_session.total_movement = 0.0

        tracking_session._apply_correction_sans_feedback(5.0, 0.002)

        assert tracking_session.total_corrections == 1
        assert tracking_session.total_movement == 5.0

    def test_ne_fait_rien_si_zero_pas(self, tracking_session):
        """Ne fait rien si le nombre de pas calculé est 0."""
        tracking_session.position_relative = 100.0
        tracking_session.total_corrections = 0

        # Très petit delta qui donne 0 pas
        tracking_session._apply_correction_sans_feedback(0.0001, 0.002)

        # Rien n'a changé
        assert tracking_session.total_corrections == 0
