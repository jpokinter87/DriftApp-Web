"""
Tests exhaustifs pour core/tracking/adaptive_tracking.py

Couvre :
- TrackingMode enum
- TrackingParameters dataclass
- AdaptiveTrackingManager :
  - Évaluation des zones (normal, critical, continuous)
  - Seuils d'altitude et de mouvement
  - Zones critiques définies
  - Changements de mode
  - verify_shortest_path
  - Diagnostic info
"""

import pytest

from core.tracking.adaptive_tracking import (
    AdaptiveTrackingManager,
    TrackingMode,
    TrackingParameters,
)


@pytest.fixture
def manager():
    """Manager avec valeurs par défaut (sans config)."""
    return AdaptiveTrackingManager(base_interval=60, base_threshold=0.5)


@pytest.fixture
def manager_with_config(sample_config_dict):
    """Manager avec config complète."""
    from core.config.config_loader import ConfigLoader
    import json
    from pathlib import Path
    import tempfile

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(sample_config_dict, f)
        tmp_path = Path(f.name)

    config = ConfigLoader(tmp_path).load()
    tmp_path.unlink()

    return AdaptiveTrackingManager(
        base_interval=config.tracking.intervalle_verification_sec,
        base_threshold=config.tracking.seuil_correction_deg,
        adaptive_config=config.adaptive,
    )


# =============================================================================
# Enums et Dataclasses
# =============================================================================

class TestTrackingMode:
    def test_values(self):
        assert TrackingMode.NORMAL.value == "normal"
        assert TrackingMode.CRITICAL.value == "critical"
        assert TrackingMode.CONTINUOUS.value == "continuous"

    def test_no_fast_track(self):
        """FAST_TRACK supprimé en v4.4."""
        modes = [m.value for m in TrackingMode]
        assert "fast_track" not in modes


class TestTrackingParameters:
    def test_construction(self):
        params = TrackingParameters(
            mode=TrackingMode.NORMAL,
            check_interval=60,
            correction_threshold=0.5,
            motor_delay=0.002,
            description="Test"
        )
        assert params.mode == TrackingMode.NORMAL
        assert params.check_interval == 60


# =============================================================================
# Évaluation des zones — sans config
# =============================================================================

class TestEvaluateTrackingZoneDefaults:
    def test_normal_zone(self, manager):
        params = manager.evaluate_tracking_zone(altitude=45.0, azimut=120.0, delta_required=2.0)
        assert params.mode == TrackingMode.NORMAL

    def test_critical_altitude(self, manager):
        """Altitude >= 68° → CRITICAL."""
        params = manager.evaluate_tracking_zone(altitude=70.0, azimut=120.0, delta_required=2.0)
        assert params.mode == TrackingMode.CRITICAL

    def test_continuous_extreme_movement(self, manager):
        """Mouvement >= 50° → CONTINUOUS."""
        params = manager.evaluate_tracking_zone(altitude=45.0, azimut=120.0, delta_required=55.0)
        assert params.mode == TrackingMode.CONTINUOUS

    def test_continuous_zenith_with_movement(self, manager):
        """Altitude >= 75° + mouvement >= 1° → CONTINUOUS."""
        params = manager.evaluate_tracking_zone(altitude=76.0, azimut=120.0, delta_required=5.0)
        assert params.mode == TrackingMode.CONTINUOUS

    def test_critical_zenith_without_movement(self, manager):
        """Altitude >= 75° mais mouvement < 1° → CRITICAL (pas CONTINUOUS)."""
        params = manager.evaluate_tracking_zone(altitude=76.0, azimut=120.0, delta_required=0.5)
        assert params.mode == TrackingMode.CRITICAL

    def test_critical_movement(self, manager):
        """Mouvement >= 30° mais < 50° → CRITICAL."""
        params = manager.evaluate_tracking_zone(altitude=45.0, azimut=120.0, delta_required=35.0)
        assert params.mode == TrackingMode.CRITICAL


# =============================================================================
# Évaluation des zones — avec config
# =============================================================================

class TestEvaluateTrackingZoneWithConfig:
    def test_normal_returns_config_values(self, manager_with_config):
        params = manager_with_config.evaluate_tracking_zone(45.0, 120.0, 2.0)
        assert params.mode == TrackingMode.NORMAL
        assert params.motor_delay == 0.002
        assert params.check_interval == 60

    def test_critical_returns_config_values(self, manager_with_config):
        params = manager_with_config.evaluate_tracking_zone(70.0, 120.0, 2.0)
        assert params.mode == TrackingMode.CRITICAL
        assert params.motor_delay == 0.001
        assert params.check_interval == 30

    def test_continuous_returns_config_values(self, manager_with_config):
        params = manager_with_config.evaluate_tracking_zone(76.0, 120.0, 5.0)
        assert params.mode == TrackingMode.CONTINUOUS
        assert params.motor_delay == 0.00015

    def test_critical_zone_defined(self, manager_with_config):
        """Zone critique définie (alt 68-73, az 50-70) → CRITICAL."""
        params = manager_with_config.evaluate_tracking_zone(70.0, 60.0, 2.0)
        assert params.mode == TrackingMode.CRITICAL


# =============================================================================
# Changements de mode
# =============================================================================

class TestModeChanges:
    def test_mode_change_logged(self, manager):
        """Premier appel en normal, puis passage en critical."""
        manager.evaluate_tracking_zone(45.0, 120.0, 2.0)
        assert manager.current_mode == TrackingMode.NORMAL

        manager.evaluate_tracking_zone(70.0, 120.0, 2.0)
        assert manager.current_mode == TrackingMode.CRITICAL

    def test_mode_stable_no_log(self, manager):
        """Même mode consécutif → pas de changement."""
        manager.evaluate_tracking_zone(45.0, 120.0, 2.0)
        mode1 = manager.current_mode
        manager.evaluate_tracking_zone(50.0, 130.0, 3.0)
        mode2 = manager.current_mode
        assert mode1 == mode2 == TrackingMode.NORMAL

    def test_return_to_normal(self, manager):
        """Critical → Normal quand altitude redescend."""
        manager.evaluate_tracking_zone(70.0, 120.0, 2.0)
        assert manager.current_mode == TrackingMode.CRITICAL

        manager.evaluate_tracking_zone(45.0, 120.0, 2.0)
        assert manager.current_mode == TrackingMode.NORMAL


# =============================================================================
# verify_shortest_path
# =============================================================================

class TestVerifyShortestPath:
    def test_small_positive(self, manager):
        delta, desc = manager.verify_shortest_path(10.0, 20.0)
        assert delta == pytest.approx(10.0)

    def test_small_negative(self, manager):
        delta, desc = manager.verify_shortest_path(20.0, 10.0)
        assert delta == pytest.approx(-10.0)

    def test_crossing_zero_clockwise(self, manager):
        """350° → 10° = +20° (plus court)."""
        delta, desc = manager.verify_shortest_path(350.0, 10.0)
        assert delta == pytest.approx(20.0)

    def test_crossing_zero_counterclockwise(self, manager):
        """10° → 350° = -20° (plus court)."""
        delta, desc = manager.verify_shortest_path(10.0, 350.0)
        assert delta == pytest.approx(-20.0)

    def test_half_circle(self, manager):
        delta, desc = manager.verify_shortest_path(0.0, 180.0)
        assert abs(delta) == pytest.approx(180.0)

    def test_same_position(self, manager):
        delta, desc = manager.verify_shortest_path(45.0, 45.0)
        assert delta == pytest.approx(0.0)

    def test_returns_description(self, manager):
        _, desc = manager.verify_shortest_path(10.0, 20.0)
        assert isinstance(desc, str)
        assert "Chemin" in desc


# =============================================================================
# Diagnostic info
# =============================================================================

class TestDiagnosticInfo:
    def test_returns_dict(self, manager):
        manager.evaluate_tracking_zone(45.0, 120.0, 2.0)
        info = manager.get_diagnostic_info(45.0, 120.0, 2.0)
        assert isinstance(info, dict)

    def test_keys_present(self, manager):
        manager.evaluate_tracking_zone(45.0, 120.0, 2.0)
        info = manager.get_diagnostic_info(45.0, 120.0, 2.0)
        expected_keys = [
            'mode', 'mode_description', 'check_interval',
            'correction_threshold', 'motor_delay',
            'in_critical_zone', 'is_high_altitude', 'is_large_movement',
            'altitude_level', 'movement_level',
        ]
        for key in expected_keys:
            assert key in info, f"Clé manquante : {key}"

    def test_altitude_levels(self, manager):
        manager.evaluate_tracking_zone(45.0, 120.0, 2.0)
        info = manager.get_diagnostic_info(45.0, 120.0, 2.0)
        assert info['altitude_level'] == 'normal'

        info = manager.get_diagnostic_info(70.0, 120.0, 2.0)
        assert info['altitude_level'] == 'critical'

        info = manager.get_diagnostic_info(80.0, 120.0, 2.0)
        assert info['altitude_level'] == 'zenith'

    def test_movement_levels(self, manager):
        manager.evaluate_tracking_zone(45.0, 120.0, 2.0)
        info = manager.get_diagnostic_info(45.0, 120.0, 2.0)
        assert info['movement_level'] == 'normal'

        info = manager.get_diagnostic_info(45.0, 120.0, 35.0)
        assert info['movement_level'] == 'critical'

        info = manager.get_diagnostic_info(45.0, 120.0, 55.0)
        assert info['movement_level'] == 'extreme'


# =============================================================================
# Prédicats internes
# =============================================================================

class TestPredicates:
    def test_altitude_level_normal(self, manager):
        assert manager._get_altitude_level(45.0) == "normal"

    def test_altitude_level_critical(self, manager):
        assert manager._get_altitude_level(70.0) == "critical"

    def test_altitude_level_zenith(self, manager):
        assert manager._get_altitude_level(80.0) == "zenith"

    def test_movement_level_normal(self, manager):
        assert manager._get_movement_level(5.0) == "normal"

    def test_movement_level_critical(self, manager):
        assert manager._get_movement_level(35.0) == "critical"

    def test_movement_level_extreme(self, manager):
        assert manager._get_movement_level(55.0) == "extreme"

    def test_critical_zone_without_config(self, manager):
        """Sans config, pas de zone critique."""
        assert manager._is_in_critical_zone(70.0, 60.0) is False

    def test_critical_zone_with_config(self, manager_with_config):
        """Zone définie : alt 68-73, az 50-70."""
        assert manager_with_config._is_in_critical_zone(70.0, 60.0) is True
        assert manager_with_config._is_in_critical_zone(70.0, 120.0) is False
        assert manager_with_config._is_in_critical_zone(45.0, 60.0) is False
