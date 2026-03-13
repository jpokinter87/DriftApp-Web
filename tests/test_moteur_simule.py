"""
Tests exhaustifs pour core/hardware/moteur_simule.py

Couvre :
- Construction avec différents types de config (dataclass, dict, None)
- Position simulée (variable globale partagée)
- Rotation (relative et absolue)
- Feedback simulé (toujours succès)
- API compatible avec MoteurCoupole
- Contrôle d'arrêt (stop_requested)
"""

import pytest

from core.hardware.moteur_simule import (
    MoteurSimule,
    get_simulated_position,
    set_simulated_position,
    _simulated_position,
)


@pytest.fixture(autouse=True)
def reset_simulated_position():
    """Réinitialise la position simulée avant chaque test."""
    set_simulated_position(0.0)
    yield
    set_simulated_position(0.0)


# =============================================================================
# Position simulée globale
# =============================================================================

class TestSimulatedPosition:
    def test_set_and_get(self):
        set_simulated_position(45.0)
        assert get_simulated_position() == 45.0

    def test_normalizes_over_360(self):
        set_simulated_position(370.0)
        assert get_simulated_position() == 10.0

    def test_normalizes_negative(self):
        set_simulated_position(-10.0)
        assert get_simulated_position() == 350.0

    def test_zero(self):
        set_simulated_position(0.0)
        assert get_simulated_position() == 0.0


# =============================================================================
# Construction
# =============================================================================

class TestMoteurSimuleConstruction:
    def test_no_config(self):
        m = MoteurSimule()
        assert m.steps_per_dome_revolution == 1941866

    def test_with_dataclass_config(self):
        from core.config.config_loader import MotorConfig, GPIOPins
        config = MotorConfig(
            gpio_pins=GPIOPins(dir=17, step=18),
            steps_per_revolution=200, microsteps=4,
            gear_ratio=2230.0, steps_correction_factor=1.08849,
            motor_delay_base=0.002, motor_delay_min=0.00001,
            motor_delay_max=0.01, max_speed_steps_per_sec=1000,
            acceleration_steps_per_sec2=500,
        )
        m = MoteurSimule(config)
        expected = int(200 * 4 * 2230.0 * 1.08849)
        assert m.steps_per_dome_revolution == expected

    def test_with_dict_config(self):
        config = {
            'steps_per_revolution': 200,
            'microsteps': 4,
            'gear_ratio': 2230.0,
            'steps_correction_factor': 1.0,
        }
        m = MoteurSimule(config)
        assert m.steps_per_dome_revolution == int(200 * 4 * 2230.0 * 1.0)

    def test_initial_position_from_global(self):
        set_simulated_position(90.0)
        m = MoteurSimule()
        assert m.position_actuelle == 90.0


# =============================================================================
# Rotation
# =============================================================================

class TestMoteurSimuleRotation:
    def test_rotation_positive(self):
        m = MoteurSimule()
        m.rotation(45.0)
        assert get_simulated_position() == pytest.approx(45.0)

    def test_rotation_negative(self):
        set_simulated_position(90.0)
        m = MoteurSimule()
        m.rotation(-45.0)
        assert get_simulated_position() == pytest.approx(45.0)

    def test_rotation_wraps_around(self):
        set_simulated_position(350.0)
        m = MoteurSimule()
        m.rotation(20.0)
        assert get_simulated_position() == pytest.approx(10.0)

    def test_rotation_full_circle(self):
        m = MoteurSimule()
        m.rotation(360.0)
        assert get_simulated_position() == pytest.approx(0.0)

    def test_rotation_absolue(self):
        set_simulated_position(45.0)
        m = MoteurSimule()
        m.rotation_absolue(90.0, 45.0)
        assert get_simulated_position() == pytest.approx(90.0)

    def test_rotation_absolue_shortest_path(self):
        """350° → 10° devrait aller par le chemin court (+20°)."""
        set_simulated_position(350.0)
        m = MoteurSimule()
        m.rotation_absolue(10.0, 350.0)
        assert get_simulated_position() == pytest.approx(10.0)


# =============================================================================
# Faire un pas
# =============================================================================

class TestMoteurSimuleFaireUnPas:
    def test_un_pas_direction_positive(self):
        m = MoteurSimule()
        m.direction = 1
        pos_avant = get_simulated_position()
        m.faire_un_pas()
        pos_apres = get_simulated_position()
        assert pos_apres > pos_avant or (pos_avant > 359 and pos_apres < 1)

    def test_un_pas_direction_negative(self):
        set_simulated_position(10.0)
        m = MoteurSimule()
        m.direction = -1
        m.faire_un_pas()
        pos = get_simulated_position()
        assert pos < 10.0 or pos > 359.0


# =============================================================================
# Daemon encodeur simulé
# =============================================================================

class TestMoteurSimuleDaemon:
    def test_get_daemon_angle(self):
        set_simulated_position(123.4)
        assert MoteurSimule.get_daemon_angle() == 123.4

    def test_get_daemon_status(self):
        set_simulated_position(45.0)
        status = MoteurSimule.get_daemon_status()
        assert status['angle'] == 45.0
        assert status['calibrated'] is True
        assert 'simulation' in status['status']


# =============================================================================
# Feedback simulé
# =============================================================================

class TestMoteurSimuleFeedback:
    def test_rotation_avec_feedback_success(self):
        set_simulated_position(0.0)
        m = MoteurSimule()
        result = m.rotation_avec_feedback(angle_cible=45.0)
        assert result['success'] is True
        assert result['erreur_finale'] == 0.0
        assert result['mode'] == 'simulation'
        assert get_simulated_position() == pytest.approx(45.0)

    def test_rotation_avec_feedback_crossing_zero(self):
        set_simulated_position(350.0)
        m = MoteurSimule()
        result = m.rotation_avec_feedback(angle_cible=10.0)
        assert result['success'] is True
        assert get_simulated_position() == pytest.approx(10.0)

    def test_rotation_relative_avec_feedback(self):
        set_simulated_position(100.0)
        m = MoteurSimule()
        result = m.rotation_relative_avec_feedback(delta_deg=30.0)
        assert result['success'] is True
        assert get_simulated_position() == pytest.approx(130.0)

    def test_get_feedback_controller_returns_self(self):
        m = MoteurSimule()
        fc = m.get_feedback_controller()
        assert fc is m


# =============================================================================
# Contrôle d'arrêt
# =============================================================================

class TestMoteurSimuleStop:
    def test_request_stop(self):
        m = MoteurSimule()
        assert m.stop_requested is False
        m.request_stop()
        assert m.stop_requested is True

    def test_clear_stop_request(self):
        m = MoteurSimule()
        m.request_stop()
        m.clear_stop_request()
        assert m.stop_requested is False

    def test_nettoyer(self):
        m = MoteurSimule()
        m.nettoyer()  # Ne doit pas lever d'exception
