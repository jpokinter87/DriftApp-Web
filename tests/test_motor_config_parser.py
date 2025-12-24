"""
Tests pour motor_config_parser.

Teste le parsing centralisé de configuration moteur (dict et dataclass).
"""

import pytest

from core.hardware.motor_config_parser import (
    MotorParams,
    parse_motor_config,
    validate_motor_params
)


class TestMotorParams:
    """Tests pour la dataclass MotorParams."""

    def test_creation_basique(self):
        """Création avec valeurs valides."""
        params = MotorParams(
            steps_per_revolution=200,
            microsteps=4,
            gear_ratio=2230.0,
            steps_correction_factor=1.08849
        )

        assert params.steps_per_revolution == 200
        assert params.microsteps == 4
        assert params.gear_ratio == 2230.0
        assert params.steps_correction_factor == 1.08849

    def test_valeurs_par_defaut_gpio(self):
        """Les pins GPIO ont des valeurs par défaut."""
        params = MotorParams(
            steps_per_revolution=200,
            microsteps=4,
            gear_ratio=2230.0,
            steps_correction_factor=1.0
        )

        assert params.dir_pin == 17
        assert params.step_pin == 18

    def test_steps_per_dome_revolution(self):
        """Calcul correct du nombre de pas par tour de coupole."""
        params = MotorParams(
            steps_per_revolution=200,
            microsteps=4,
            gear_ratio=2230.0,
            steps_correction_factor=1.08849
        )

        expected = int(200 * 4 * 2230.0 * 1.08849)
        assert params.steps_per_dome_revolution == expected


class TestParseMotorConfig:
    """Tests pour parse_motor_config."""

    def test_parse_dict_legacy(self):
        """Parse un dict au format legacy."""
        config = {
            'steps_per_revolution': 200,
            'microsteps': 8,
            'gear_ratio': 1000.0,
            'steps_correction_factor': 1.05,
            'gpio_pins': {'dir': 27, 'step': 22}
        }

        params = parse_motor_config(config)

        assert params.steps_per_revolution == 200
        assert params.microsteps == 8
        assert params.gear_ratio == 1000.0
        assert params.steps_correction_factor == 1.05
        assert params.dir_pin == 27
        assert params.step_pin == 22

    def test_parse_dict_sans_gpio(self):
        """Parse un dict sans gpio_pins (utilise valeurs par défaut)."""
        config = {
            'steps_per_revolution': 200,
            'microsteps': 4,
            'gear_ratio': 2230.0,
            'steps_correction_factor': 1.0
        }

        params = parse_motor_config(config)

        assert params.dir_pin == 17  # Défaut
        assert params.step_pin == 18  # Défaut

    def test_parse_dataclass(self):
        """Parse une dataclass MotorConfig."""
        # Simuler une dataclass MotorConfig
        class MockGPIOPins:
            dir = 5
            step = 6

        class MockMotorConfig:
            gpio_pins = MockGPIOPins()
            steps_per_revolution = 400
            microsteps = 16
            gear_ratio = 1500.0
            steps_correction_factor = 1.1

        params = parse_motor_config(MockMotorConfig())

        assert params.steps_per_revolution == 400
        assert params.microsteps == 16
        assert params.gear_ratio == 1500.0
        assert params.steps_correction_factor == 1.1
        assert params.dir_pin == 5
        assert params.step_pin == 6

    def test_parse_type_invalide(self):
        """Lève une erreur pour un type non reconnu."""
        with pytest.raises(ValueError, match="non reconnu"):
            parse_motor_config("invalid")

    def test_parse_dict_cle_manquante(self):
        """Lève une erreur si une clé requise manque."""
        config = {
            'steps_per_revolution': 200,
            # microsteps manquant
            'gear_ratio': 2230.0,
            'steps_correction_factor': 1.0
        }

        with pytest.raises(KeyError):
            parse_motor_config(config)


class TestValidateMotorParams:
    """Tests pour validate_motor_params."""

    def test_params_valides(self):
        """Aucune erreur pour des paramètres valides."""
        params = MotorParams(
            steps_per_revolution=200,
            microsteps=4,
            gear_ratio=2230.0,
            steps_correction_factor=1.08849
        )

        # Ne doit pas lever d'exception
        validate_motor_params(params)

    def test_steps_negatif(self):
        """Erreur si steps_per_revolution <= 0."""
        params = MotorParams(
            steps_per_revolution=-1,
            microsteps=4,
            gear_ratio=2230.0,
            steps_correction_factor=1.0
        )

        with pytest.raises(ValueError, match="steps_per_revolution"):
            validate_motor_params(params)

    def test_steps_zero(self):
        """Erreur si steps_per_revolution == 0."""
        params = MotorParams(
            steps_per_revolution=0,
            microsteps=4,
            gear_ratio=2230.0,
            steps_correction_factor=1.0
        )

        with pytest.raises(ValueError, match="steps_per_revolution"):
            validate_motor_params(params)

    @pytest.mark.parametrize("invalid_microsteps", [0, 3, 5, 7, 9, 64])
    def test_microsteps_invalide(self, invalid_microsteps):
        """Erreur si microsteps n'est pas dans [1, 2, 4, 8, 16, 32]."""
        params = MotorParams(
            steps_per_revolution=200,
            microsteps=invalid_microsteps,
            gear_ratio=2230.0,
            steps_correction_factor=1.0
        )

        with pytest.raises(ValueError, match="microsteps"):
            validate_motor_params(params)

    @pytest.mark.parametrize("valid_microsteps", [1, 2, 4, 8, 16, 32])
    def test_microsteps_valide(self, valid_microsteps):
        """Pas d'erreur pour microsteps valides."""
        params = MotorParams(
            steps_per_revolution=200,
            microsteps=valid_microsteps,
            gear_ratio=2230.0,
            steps_correction_factor=1.0
        )

        validate_motor_params(params)  # Ne doit pas lever d'exception

    def test_gear_ratio_negatif(self):
        """Erreur si gear_ratio <= 0."""
        params = MotorParams(
            steps_per_revolution=200,
            microsteps=4,
            gear_ratio=-1.0,
            steps_correction_factor=1.0
        )

        with pytest.raises(ValueError, match="gear_ratio"):
            validate_motor_params(params)

    def test_correction_factor_zero(self):
        """Erreur si steps_correction_factor <= 0."""
        params = MotorParams(
            steps_per_revolution=200,
            microsteps=4,
            gear_ratio=2230.0,
            steps_correction_factor=0
        )

        with pytest.raises(ValueError, match="steps_correction_factor"):
            validate_motor_params(params)
