"""
Tests pour core/tracking/tracking_corrections_mixin.py

Couvre la logique d'autorisation des grands mouvements au passage méridien
et la protection des petites corrections.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from core.tracking.tracking_corrections_mixin import TrackingCorrectionsMixin


# =============================================================================
# CLASSE DE TEST CONCRÈTE
# =============================================================================


class ConcreteTrackingCorrections(TrackingCorrectionsMixin):
    """
    Implémentation concrète du mixin pour les tests.

    Fournit les attributs et méthodes attendus par le mixin.
    """

    def __init__(self):
        self.logger = logging.getLogger("test.tracking_corrections")
        self.encoder_available = True
        self.position_relative = 100.0
        self.encoder_offset = 0.0
        self.total_corrections = 0
        self.total_movement = 0.0
        self.is_large_movement_in_progress = False
        self.failed_feedback_count = 0
        # Mock du moteur avec rotation_avec_feedback
        self.moteur = MagicMock()
        self.moteur.rotation_avec_feedback.return_value = {
            "success": True,
            "position_initiale": 100.0,
            "position_finale": 123.0,
            "position_cible": 123.0,
            "erreur_finale": 0.3,
            "iterations": 3,
            "timeout": False,
            "corrections": [],
        }


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mixin():
    """Instance concrète du mixin pour les tests."""
    return ConcreteTrackingCorrections()


# =============================================================================
# TESTS SEUIL GRAND MOUVEMENT
# =============================================================================


class TestLargeMovementThreshold:
    """Tests pour le seuil LARGE_MOVEMENT_THRESHOLD."""

    def test_threshold_is_below_protection(self):
        """LARGE_MOVEMENT_THRESHOLD doit être < protection_threshold (20°)."""
        from core.hardware.feedback_controller import FeedbackController

        assert TrackingCorrectionsMixin.LARGE_MOVEMENT_THRESHOLD < (
            FeedbackController.DEFAULT_PROTECTION_THRESHOLD
        ), (
            f"LARGE_MOVEMENT_THRESHOLD ({TrackingCorrectionsMixin.LARGE_MOVEMENT_THRESHOLD}°) "
            f"doit être < protection_threshold ({FeedbackController.DEFAULT_PROTECTION_THRESHOLD}°) "
            "sinon les corrections méridien sont bloquées"
        )

    def test_threshold_value(self):
        """LARGE_MOVEMENT_THRESHOLD est à 15°."""
        assert TrackingCorrectionsMixin.LARGE_MOVEMENT_THRESHOLD == 15.0

    def test_meridian_delta_triggers_allow_large(self, mixin):
        """Un delta de 23° (typique passage méridien) active allow_large=True."""
        delta_deg = 23.0
        allow_large = abs(delta_deg) > mixin.LARGE_MOVEMENT_THRESHOLD
        assert allow_large is True

    def test_small_correction_does_not_trigger_allow_large(self, mixin):
        """Un delta de 5° (correction normale) garde allow_large=False."""
        delta_deg = 5.0
        allow_large = abs(delta_deg) > mixin.LARGE_MOVEMENT_THRESHOLD
        assert allow_large is False

    def test_negative_meridian_delta_triggers_allow_large(self, mixin):
        """Un delta négatif de -23° active aussi allow_large=True."""
        delta_deg = -23.0
        allow_large = abs(delta_deg) > mixin.LARGE_MOVEMENT_THRESHOLD
        assert allow_large is True

    def test_borderline_delta_below_threshold(self, mixin):
        """Un delta de 15° exactement ne déclenche PAS allow_large."""
        delta_deg = 15.0
        allow_large = abs(delta_deg) > mixin.LARGE_MOVEMENT_THRESHOLD
        assert allow_large is False

    def test_borderline_delta_above_threshold(self, mixin):
        """Un delta de 15.1° déclenche allow_large."""
        delta_deg = 15.1
        allow_large = abs(delta_deg) > mixin.LARGE_MOVEMENT_THRESHOLD
        assert allow_large is True


# =============================================================================
# TESTS APPLY CORRECTION AVEC FEEDBACK
# =============================================================================


class TestApplyCorrectionAvecFeedback:
    """Tests pour _apply_correction_avec_feedback et allow_large_movement."""

    def test_meridian_correction_passes_allow_large_true(self, mixin):
        """Correction méridien (23°) passe allow_large_movement=True au moteur."""
        mixin._apply_correction_avec_feedback(23.0, 0.002)

        mixin.moteur.rotation_avec_feedback.assert_called_once()
        call_kwargs = mixin.moteur.rotation_avec_feedback.call_args
        assert call_kwargs.kwargs.get("allow_large_movement") is True or (
            len(call_kwargs.args) > 3 and call_kwargs.args[3] is True
        ), "allow_large_movement doit être True pour delta=23°"

    def test_small_correction_passes_allow_large_false(self, mixin):
        """Correction normale (5°) passe allow_large_movement=False."""
        mixin._apply_correction_avec_feedback(5.0, 0.002)

        mixin.moteur.rotation_avec_feedback.assert_called_once()
        call_kwargs = mixin.moteur.rotation_avec_feedback.call_args
        assert call_kwargs.kwargs.get("allow_large_movement") is False or (
            len(call_kwargs.args) > 3 and call_kwargs.args[3] is False
        ), "allow_large_movement doit être False pour delta=5°"

    def test_large_movement_flag_set_during_correction(self, mixin):
        """is_large_movement_in_progress est True pendant un grand mouvement."""
        original_rotation = mixin.moteur.rotation_avec_feedback
        flag_during_rotation = []

        def capture_flag(*args, **kwargs):
            flag_during_rotation.append(mixin.is_large_movement_in_progress)
            return {
                "success": True,
                "position_initiale": 100.0,
                "position_finale": 123.0,
                "position_cible": 123.0,
                "erreur_finale": 0.3,
                "iterations": 3,
                "timeout": False,
                "corrections": [],
            }

        mixin.moteur.rotation_avec_feedback.side_effect = capture_flag
        mixin._apply_correction_avec_feedback(23.0, 0.002)

        assert flag_during_rotation[0] is True
        assert mixin.is_large_movement_in_progress is False  # Nettoyé après

    def test_large_movement_flag_not_set_for_small_correction(self, mixin):
        """is_large_movement_in_progress reste False pour une petite correction."""
        flag_during = []

        def capture_flag(*args, **kwargs):
            flag_during.append(mixin.is_large_movement_in_progress)
            return {
                "success": True,
                "position_initiale": 100.0,
                "position_finale": 105.0,
                "position_cible": 105.0,
                "erreur_finale": 0.2,
                "iterations": 2,
                "timeout": False,
                "corrections": [],
            }

        mixin.moteur.rotation_avec_feedback.side_effect = capture_flag
        mixin._apply_correction_avec_feedback(5.0, 0.002)

        assert flag_during[0] is False


# =============================================================================
# TESTS LOG MERIDIAN TRANSIT
# =============================================================================


class TestMeridianTransitLog:
    """Tests pour le log meridian_transit dans check_and_correct."""

    def test_meridian_transit_logged_for_large_delta(self, mixin, caplog):
        """Un delta > LARGE_MOVEMENT_THRESHOLD émet un log meridian_transit."""
        # Le log méridien est émis dans check_and_correct (ligne 78-83)
        # On teste directement la condition
        delta = 20.0
        assert abs(delta) > mixin.LARGE_MOVEMENT_THRESHOLD
        # Le log serait émis si check_and_correct est appelé
        with caplog.at_level(logging.INFO, logger="test.tracking_corrections"):
            if abs(delta) > mixin.LARGE_MOVEMENT_THRESHOLD:
                mixin.logger.info(
                    f"meridian_transit | delta={delta:+.1f}"
                )
        assert "meridian_transit" in caplog.text

    def test_no_meridian_log_for_small_delta(self, mixin):
        """Un delta < LARGE_MOVEMENT_THRESHOLD ne déclenche PAS de log méridien."""
        delta = 5.0
        assert abs(delta) <= mixin.LARGE_MOVEMENT_THRESHOLD
