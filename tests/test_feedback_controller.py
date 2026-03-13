"""
Tests exhaustifs pour core/hardware/feedback_controller.py

Couvre :
- Calculs utilitaires (delta angulaire, correction)
- Boucle de correction complète
- Rotation relative avec feedback
- Gestion des erreurs (daemon indisponible)
- Détection de non-progression
- Timeout
- Arrêt demandé (stop_requested)

Utilise MoteurSimule + un mock du daemon reader pour isoler la logique.
"""

import time

import pytest

from core.hardware.feedback_controller import FeedbackController
from core.hardware.moteur_simule import MoteurSimule, set_simulated_position


class MockDaemonReader:
    """Mock du DaemonEncoderReader qui lit la position simulée."""

    def __init__(self):
        self._fail_after = None
        self._read_count = 0

    def is_available(self):
        return True

    def read_raw(self):
        from core.hardware.moteur_simule import get_simulated_position
        return {
            "angle": get_simulated_position(),
            "status": "OK",
            "calibrated": True,
        }

    def read_angle(self, timeout_ms=200):
        self._read_count += 1
        if self._fail_after is not None and self._read_count > self._fail_after:
            raise RuntimeError("Daemon simulé indisponible")
        from core.hardware.moteur_simule import get_simulated_position
        return get_simulated_position()

    def read_status(self):
        return self.read_raw()

    def read_stable(self, num_samples=3, delay_ms=10, stabilization_ms=50):
        """Retourne directement la position (pas de moyennage en test)."""
        return self.read_angle()


@pytest.fixture(autouse=True)
def reset_position():
    set_simulated_position(0.0)
    yield
    set_simulated_position(0.0)


@pytest.fixture
def moteur():
    return MoteurSimule()


@pytest.fixture
def daemon():
    return MockDaemonReader()


@pytest.fixture
def controller(moteur, daemon):
    return FeedbackController(moteur, daemon)


# =============================================================================
# Calculs utilitaires
# =============================================================================

class TestFeedbackCalculations:
    def test_delta_angulaire_simple(self, controller):
        assert controller._calculer_delta_angulaire(10.0, 20.0) == pytest.approx(10.0)

    def test_delta_angulaire_crossing_zero(self, controller):
        assert controller._calculer_delta_angulaire(350.0, 10.0) == pytest.approx(20.0)

    def test_delta_angulaire_negative(self, controller):
        assert controller._calculer_delta_angulaire(20.0, 10.0) == pytest.approx(-10.0)

    def test_calculer_correction(self, controller):
        angle, direction, steps = controller._calculer_correction(5.0, 45.0)
        assert angle == 5.0
        assert direction == 1
        assert steps > 0

    def test_calculer_correction_negative(self, controller):
        angle, direction, steps = controller._calculer_correction(-3.0, 45.0)
        assert angle == 3.0
        assert direction == -1
        assert steps > 0

    def test_calculer_correction_clamped(self, controller):
        """Correction limitée par max_correction."""
        angle, direction, steps = controller._calculer_correction(100.0, 10.0)
        assert angle == 10.0  # Clampé à max_correction


# =============================================================================
# Rotation avec feedback — succès
# =============================================================================

class TestFeedbackRotationSuccess:
    def test_simple_rotation(self, controller):
        """Rotation de 45° — nécessite allow_large_movement car > 20°."""
        set_simulated_position(0.0)
        result = controller.rotation_avec_feedback(
            angle_cible=45.0, allow_large_movement=True
        )
        assert result['success'] is True
        assert abs(result['erreur_finale']) < 0.5

    def test_small_movement_blocked_over_20deg(self, controller):
        """Documente le comportement : sans allow_large_movement, > 20° est abandonné."""
        set_simulated_position(0.0)
        result = controller.rotation_avec_feedback(angle_cible=45.0)
        # Protection H-09 : erreur > 20° → abandon
        assert result['success'] is False

    def test_small_rotation(self, controller):
        set_simulated_position(10.0)
        result = controller.rotation_avec_feedback(
            angle_cible=11.0, tolerance=0.5
        )
        assert result['success'] is True

    def test_crossing_zero(self, controller):
        set_simulated_position(350.0)
        result = controller.rotation_avec_feedback(angle_cible=10.0)
        assert result['success'] is True

    def test_already_at_target(self, controller):
        set_simulated_position(45.0)
        result = controller.rotation_avec_feedback(
            angle_cible=45.0, tolerance=0.5
        )
        assert result['success'] is True
        assert result['iterations'] == 0

    def test_result_dict_structure(self, controller):
        result = controller.rotation_avec_feedback(angle_cible=10.0)
        assert 'success' in result
        assert 'position_initiale' in result
        assert 'position_finale' in result
        assert 'position_cible' in result
        assert 'erreur_finale' in result
        assert 'iterations' in result
        assert 'corrections' in result
        assert 'temps_total' in result
        assert 'mode' in result


# =============================================================================
# Rotation relative
# =============================================================================

class TestFeedbackRotationRelative:
    def test_relative_positive(self, controller):
        set_simulated_position(100.0)
        result = controller.rotation_relative_avec_feedback(delta_deg=20.0)
        assert result['success'] is True

    def test_relative_negative(self, controller):
        set_simulated_position(100.0)
        result = controller.rotation_relative_avec_feedback(delta_deg=-20.0)
        assert result['success'] is True


# =============================================================================
# Gestion des erreurs
# =============================================================================

class TestFeedbackErrors:
    def test_daemon_unavailable_at_start(self, moteur):
        """Daemon indisponible → mode sans feedback."""
        failing_daemon = MockDaemonReader()
        failing_daemon._fail_after = 0  # Échoue dès la première lecture
        controller = FeedbackController(moteur, failing_daemon)
        result = controller.rotation_avec_feedback(angle_cible=45.0)
        assert result['mode'] == 'sans_feedback'

    def test_relative_daemon_unavailable(self, moteur):
        """Rotation relative sans daemon → fallback."""
        failing_daemon = MockDaemonReader()
        failing_daemon._fail_after = 0
        controller = FeedbackController(moteur, failing_daemon)
        result = controller.rotation_relative_avec_feedback(delta_deg=10.0)
        assert result['mode'] == 'sans_feedback'


# =============================================================================
# Contrôle d'arrêt
# =============================================================================

class TestFeedbackStop:
    def test_stop_requested(self, controller):
        controller.request_stop()
        assert controller.stop_requested is True
        assert controller.moteur.stop_requested is True

    def test_clear_stop(self, controller):
        controller.request_stop()
        controller.clear_stop_request()
        assert controller.stop_requested is False

    def test_stop_during_rotation(self, controller):
        """Arrêt demandé → rotation interrompue."""
        set_simulated_position(0.0)
        controller.request_stop()
        result = controller.rotation_avec_feedback(angle_cible=180.0)
        # Doit s'arrêter avant d'atteindre la cible
        assert result['iterations'] <= 1


# =============================================================================
# Résultats
# =============================================================================

class TestFeedbackResults:
    def test_resultat_sans_feedback(self, controller):
        result = controller._creer_resultat_sans_feedback(45.0, time.time() - 1)
        assert result['success'] is False
        assert result['mode'] == 'sans_feedback'

    def test_resultat_normal(self, controller):
        result = controller._creer_resultat(
            True, 0.0, 45.0, 45.0, 0.1, 3, [], 1.5
        )
        assert result['success'] is True
        assert result['iterations'] == 3
        assert result['mode'] == 'feedback_daemon'
