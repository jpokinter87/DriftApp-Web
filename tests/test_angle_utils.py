"""
Tests exhaustifs pour core/utils/angle_utils.py

Couvre les 6 fonctions :
- normalize_angle_360
- normalize_angle_180
- shortest_angular_distance
- angles_are_close
- calculate_rotation_direction
- calculate_steps_for_rotation

Chaque fonction est testée avec :
- Cas normaux
- Edge cases (0°, 360°, frontière 0°/360°)
- Valeurs négatives
- Valeurs très grandes
- Limites mathématiques (180°, -180°)
"""

import pytest

from core.utils.angle_utils import (
    angles_are_close,
    calculate_rotation_direction,
    calculate_steps_for_rotation,
    normalize_angle_180,
    normalize_angle_360,
    shortest_angular_distance,
)


# =============================================================================
# normalize_angle_360
# =============================================================================

class TestNormalizeAngle360:
    """Tests pour normalize_angle_360()."""

    def test_zero(self):
        assert normalize_angle_360(0.0) == 0.0

    def test_normal_angle(self):
        assert normalize_angle_360(45.0) == 45.0

    def test_exact_360(self):
        assert normalize_angle_360(360.0) == 0.0

    def test_over_360(self):
        assert normalize_angle_360(370.0) == 10.0

    def test_negative(self):
        assert normalize_angle_360(-10.0) == 350.0

    def test_large_negative(self):
        assert normalize_angle_360(-370.0) == 350.0

    def test_very_large_positive(self):
        assert normalize_angle_360(720.0) == 0.0

    def test_very_large_positive_with_offset(self):
        assert normalize_angle_360(725.0) == 5.0

    def test_just_below_360(self):
        result = normalize_angle_360(359.999)
        assert 359.0 < result < 360.0

    def test_small_positive(self):
        assert normalize_angle_360(0.001) == pytest.approx(0.001)

    def test_small_negative(self):
        result = normalize_angle_360(-0.001)
        assert result == pytest.approx(359.999)

    def test_180(self):
        assert normalize_angle_360(180.0) == 180.0

    def test_negative_180(self):
        assert normalize_angle_360(-180.0) == 180.0

    def test_multiple_rotations(self):
        assert normalize_angle_360(1080.0) == 0.0  # 3 tours

    def test_negative_multiple_rotations(self):
        assert normalize_angle_360(-720.0) == 0.0  # -2 tours


# =============================================================================
# normalize_angle_180
# =============================================================================

class TestNormalizeAngle180:
    """Tests pour normalize_angle_180()."""

    def test_zero(self):
        assert normalize_angle_180(0.0) == 0.0

    def test_positive_90(self):
        assert normalize_angle_180(90.0) == 90.0

    def test_negative_90(self):
        assert normalize_angle_180(-90.0) == -90.0

    def test_180(self):
        assert normalize_angle_180(180.0) == 180.0

    def test_270_wraps_to_negative(self):
        assert normalize_angle_180(270.0) == -90.0

    def test_negative_270_wraps_to_positive(self):
        assert normalize_angle_180(-270.0) == 90.0

    def test_360_wraps_to_zero(self):
        assert normalize_angle_180(360.0) == 0.0

    def test_over_360(self):
        assert normalize_angle_180(450.0) == 90.0

    def test_large_negative(self):
        assert normalize_angle_180(-450.0) == -90.0

    def test_just_over_180(self):
        result = normalize_angle_180(181.0)
        assert result == -179.0

    def test_just_under_negative_180(self):
        result = normalize_angle_180(-181.0)
        assert result == 179.0


# =============================================================================
# shortest_angular_distance
# =============================================================================

class TestShortestAngularDistance:
    """Tests pour shortest_angular_distance()."""

    def test_same_angle(self):
        assert shortest_angular_distance(45.0, 45.0) == 0.0

    def test_small_positive(self):
        assert shortest_angular_distance(10.0, 15.0) == 5.0

    def test_small_negative(self):
        assert shortest_angular_distance(15.0, 10.0) == -5.0

    def test_crossing_zero_clockwise(self):
        """350° → 10° devrait être +20° (plus court par 0°)."""
        result = shortest_angular_distance(350.0, 10.0)
        assert result == pytest.approx(20.0)

    def test_crossing_zero_counterclockwise(self):
        """10° → 350° devrait être -20° (plus court par 0°)."""
        result = shortest_angular_distance(10.0, 350.0)
        assert result == pytest.approx(-20.0)

    def test_opposite_180(self):
        """0° → 180° devrait être 180° (ambigu, mais convention positive)."""
        result = shortest_angular_distance(0.0, 180.0)
        assert result == 180.0

    def test_opposite_from_90(self):
        """90° → 270° devrait être 180° ou -180°."""
        result = shortest_angular_distance(90.0, 270.0)
        assert abs(result) == 180.0

    def test_large_gap_takes_short_path(self):
        """0° → 350° devrait être -10°, pas +350°."""
        result = shortest_angular_distance(0.0, 350.0)
        assert result == pytest.approx(-10.0)

    def test_zero_to_zero(self):
        assert shortest_angular_distance(0.0, 0.0) == 0.0

    def test_360_to_zero(self):
        """360° est identique à 0°."""
        result = shortest_angular_distance(360.0, 0.0)
        assert result == pytest.approx(0.0)

    def test_negative_input(self):
        """Les entrées négatives devraient être gérées."""
        result = shortest_angular_distance(-10.0, 10.0)
        assert result == pytest.approx(20.0)

    def test_both_large(self):
        result = shortest_angular_distance(710.0, 720.0)
        assert result == pytest.approx(10.0)

    def test_nearly_opposite(self):
        """179° de décalage → +179°."""
        result = shortest_angular_distance(0.0, 179.0)
        assert result == pytest.approx(179.0)

    def test_just_over_opposite(self):
        """181° de décalage → -179° (chemin court par l'autre côté)."""
        result = shortest_angular_distance(0.0, 181.0)
        assert result == pytest.approx(-179.0)

    def test_typical_tracking_correction(self):
        """Correction de suivi typique : petit delta."""
        result = shortest_angular_distance(123.5, 124.2)
        assert result == pytest.approx(0.7)

    def test_typical_goto(self):
        """GOTO typique : grand déplacement."""
        result = shortest_angular_distance(44.0, 180.0)
        assert result == pytest.approx(136.0)


# =============================================================================
# angles_are_close
# =============================================================================

class TestAnglesAreClose:
    """Tests pour angles_are_close()."""

    def test_identical(self):
        assert angles_are_close(45.0, 45.0) is True

    def test_within_tolerance(self):
        assert angles_are_close(45.0, 45.3, tolerance=0.5) is True

    def test_outside_tolerance(self):
        assert angles_are_close(45.0, 46.0, tolerance=0.5) is False

    def test_crossing_zero_within_tolerance(self):
        """359.8° et 0.1° sont à 0.3° de distance."""
        assert angles_are_close(359.8, 0.1, tolerance=0.5) is True

    def test_crossing_zero_outside_tolerance(self):
        """359.0° et 0.5° sont à 1.5° de distance."""
        assert angles_are_close(359.0, 0.5, tolerance=0.5) is False

    def test_default_tolerance(self):
        """Tolérance par défaut = 0.5°."""
        assert angles_are_close(10.0, 10.3) is True
        assert angles_are_close(10.0, 11.0) is False

    def test_exact_tolerance_boundary(self):
        """Note: la fonction utilise < (strict), pas <=.
        Donc 0.5° avec tolérance 0.5° retourne False.
        C'est le comportement actuel documenté (finding L-07)."""
        assert angles_are_close(10.0, 10.5, tolerance=0.5) is False

    def test_zero_tolerance(self):
        assert angles_are_close(45.0, 45.0, tolerance=0.0) is False  # 0 < 0 est False

    def test_large_tolerance(self):
        assert angles_are_close(0.0, 350.0, tolerance=15.0) is True


# =============================================================================
# calculate_rotation_direction
# =============================================================================

class TestCalculateRotationDirection:
    """Tests pour calculate_rotation_direction()."""

    def test_clockwise(self):
        assert calculate_rotation_direction(10.0, 20.0) == 1

    def test_counterclockwise(self):
        assert calculate_rotation_direction(20.0, 10.0) == -1

    def test_same_angle(self):
        assert calculate_rotation_direction(45.0, 45.0) == 0

    def test_crossing_zero_clockwise(self):
        """350° → 10° devrait être horaire (+1)."""
        assert calculate_rotation_direction(350.0, 10.0) == 1

    def test_crossing_zero_counterclockwise(self):
        """10° → 350° devrait être anti-horaire (-1)."""
        assert calculate_rotation_direction(10.0, 350.0) == -1

    def test_nearly_identical(self):
        """Angles très proches (< 0.001°) = identiques."""
        assert calculate_rotation_direction(45.0, 45.0005) == 0


# =============================================================================
# calculate_steps_for_rotation
# =============================================================================

class TestCalculateStepsForRotation:
    """Tests pour calculate_steps_for_rotation()."""

    def test_full_revolution(self):
        """360° avec 1000 steps/rev = 1000 steps."""
        assert calculate_steps_for_rotation(360.0, 1000) == 1000

    def test_half_revolution(self):
        assert calculate_steps_for_rotation(180.0, 1000) == 500

    def test_one_degree(self):
        """1° avec 360 steps/rev = 1 step."""
        assert calculate_steps_for_rotation(1.0, 360) == 1

    def test_negative_angle(self):
        """Angle négatif → même nombre de steps (abs)."""
        assert calculate_steps_for_rotation(-90.0, 1000) == 250

    def test_zero_angle(self):
        assert calculate_steps_for_rotation(0.0, 1000) == 0

    def test_small_angle(self):
        """Angle trop petit pour un pas → 0 steps."""
        result = calculate_steps_for_rotation(0.001, 360)
        assert result == 0

    def test_realistic_dome_values(self):
        """Valeurs réalistes : ~1.94M steps/tour, correction de 1°."""
        steps_per_rev = 1941866  # Valeur réelle du projet
        result = calculate_steps_for_rotation(1.0, steps_per_rev)
        expected = int(1.0 / (360.0 / steps_per_rev))
        assert result == expected

    def test_realistic_small_correction(self):
        """Correction de 0.5° avec les valeurs réelles."""
        steps_per_rev = 1941866
        result = calculate_steps_for_rotation(0.5, steps_per_rev)
        assert result > 0
        assert result == int(0.5 / (360.0 / steps_per_rev))
