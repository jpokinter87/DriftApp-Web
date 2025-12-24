"""
Motor Config Parser - Parsing centralisé de la configuration moteur.

Élimine la duplication entre moteur.py et moteur_simule.py pour
le parsing de configuration (dict vs dataclass).

Date: Décembre 2025
Version: 1.0
"""

from dataclasses import dataclass
from typing import Union, Any


@dataclass
class MotorParams:
    """
    Paramètres moteur extraits de la configuration.

    Unifie l'accès aux paramètres que la source soit un dict ou une dataclass.
    """
    steps_per_revolution: int
    microsteps: int
    gear_ratio: float
    steps_correction_factor: float
    dir_pin: int = 17
    step_pin: int = 18

    @property
    def steps_per_dome_revolution(self) -> int:
        """Calcule le nombre total de pas pour un tour de coupole."""
        return int(
            self.steps_per_revolution *
            self.microsteps *
            self.gear_ratio *
            self.steps_correction_factor
        )


def parse_motor_config(config: Any) -> MotorParams:
    """
    Parse une configuration moteur (dict ou dataclass) en MotorParams.

    Args:
        config: Configuration moteur (MotorConfig dataclass ou dict)

    Returns:
        MotorParams: Paramètres extraits et normalisés

    Raises:
        ValueError: Si le type de configuration n'est pas reconnu
        KeyError: Si des clés requises sont manquantes (mode dict)

    Examples:
        # Depuis dataclass MotorConfig
        params = parse_motor_config(config.motor)
        print(params.steps_per_dome_revolution)

        # Depuis dict legacy
        params = parse_motor_config({'steps_per_revolution': 200, ...})
    """
    if hasattr(config, 'gpio_pins'):
        # MotorConfig dataclass (core/config/config_loader.py)
        return MotorParams(
            steps_per_revolution=config.steps_per_revolution,
            microsteps=config.microsteps,
            gear_ratio=config.gear_ratio,
            steps_correction_factor=config.steps_correction_factor,
            dir_pin=config.gpio_pins.dir,
            step_pin=config.gpio_pins.step
        )
    elif isinstance(config, dict):
        # Ancien format dict (compatibilité)
        gpio_pins = config.get('gpio_pins', {})
        return MotorParams(
            steps_per_revolution=config['steps_per_revolution'],
            microsteps=config['microsteps'],
            gear_ratio=config['gear_ratio'],
            steps_correction_factor=config['steps_correction_factor'],
            dir_pin=gpio_pins.get('dir', 17),
            step_pin=gpio_pins.get('step', 18)
        )
    else:
        raise ValueError(
            f"Type de configuration moteur non reconnu: {type(config)}. "
            "Attendu: MotorConfig dataclass ou dict."
        )


def validate_motor_params(params: MotorParams) -> None:
    """
    Valide les paramètres moteur.

    Args:
        params: Paramètres à valider

    Raises:
        ValueError: Si un paramètre est invalide
    """
    if params.steps_per_revolution <= 0:
        raise ValueError(
            f"steps_per_revolution doit être > 0 (reçu: {params.steps_per_revolution})"
        )

    if params.microsteps not in [1, 2, 4, 8, 16, 32]:
        raise ValueError(
            f"microsteps invalide: {params.microsteps}. "
            "Valeurs possibles: 1, 2, 4, 8, 16, 32"
        )

    if params.gear_ratio <= 0:
        raise ValueError(
            f"gear_ratio doit être > 0 (reçu: {params.gear_ratio})"
        )

    if params.steps_correction_factor <= 0:
        raise ValueError(
            f"steps_correction_factor doit être > 0 (reçu: {params.steps_correction_factor})"
        )
