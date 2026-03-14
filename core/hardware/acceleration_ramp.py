"""
Rampe d'accélération/décélération pour moteur pas-à-pas.

Ce module fournit une gestion douce des transitions de vitesse pour
protéger le moteur et la mécanique de la coupole.

IMPORTANT: Ce module n'affecte PAS la configuration moteur existante.
Il modifie uniquement le timing des pas pendant les phases de transition.

VERSION 4.5 : Implémentation initiale
Date: 24 décembre 2025
"""

import math
from dataclasses import dataclass
from typing import Optional


# =============================================================================
# PARAMÈTRES DE RAMPE (HARDCODÉS - NE PAS MODIFIER LA CONFIG MOTEUR)
# =============================================================================

# Délai de démarrage lent (3ms) - protège le moteur au démarrage
RAMP_START_DELAY = 0.003

# Nombre de pas pour atteindre la vitesse nominale
RAMP_STEPS = 500

# Seuil minimum de pas pour appliquer la rampe (évite overhead sur petits mouvements)
MIN_STEPS_FOR_RAMP = 200

# Facteur pour rampe proportionnelle sur mouvements courts
# Si total_steps < 2 * RAMP_STEPS, on utilise total_steps / 4 pour chaque rampe
SHORT_MOVEMENT_RAMP_RATIO = 4


@dataclass
class RampConfig:
    """Configuration de rampe (optionnelle pour surcharge)."""
    start_delay: float = RAMP_START_DELAY
    ramp_steps: int = RAMP_STEPS
    min_steps: int = MIN_STEPS_FOR_RAMP
    use_s_curve: bool = True  # True = S-curve, False = linéaire


class AccelerationRamp:
    """
    Gestionnaire de rampe d'accélération/décélération.

    Calcule le délai optimal pour chaque pas en fonction de sa position
    dans le mouvement total, avec des transitions douces au démarrage
    et à l'arrêt.

    Exemple d'utilisation:
        ramp = AccelerationRamp(total_steps=10000, target_delay=0.00015)
        for step_index in range(10000):
            delay = ramp.get_delay(step_index)
            motor.faire_un_pas(delay)
    """

    def __init__(
        self,
        total_steps: int,
        target_delay: float,
        config: Optional[RampConfig] = None
    ):
        """
        Initialise la rampe pour un mouvement.

        Args:
            total_steps: Nombre total de pas du mouvement
            target_delay: Délai cible (vitesse nominale) en secondes
            config: Configuration optionnelle de la rampe
        """
        self.total_steps = total_steps
        self.target_delay = target_delay
        self.config = config or RampConfig()

        # Calcul des phases de rampe
        self._calculate_ramp_phases()

    def _calculate_ramp_phases(self):
        """Calcule les limites des phases d'accélération et décélération."""
        # Pas assez de pas pour la rampe → pas de rampe
        if self.total_steps < self.config.min_steps:
            self.accel_end = 0
            self.decel_start = self.total_steps
            self.ramp_enabled = False
            return

        self.ramp_enabled = True

        # Mouvement court: rampe proportionnelle
        if self.total_steps < 2 * self.config.ramp_steps:
            ramp_length = max(1, self.total_steps // SHORT_MOVEMENT_RAMP_RATIO)
            self.accel_end = ramp_length
            self.decel_start = self.total_steps - ramp_length
        else:
            # Mouvement normal: rampe complète
            self.accel_end = self.config.ramp_steps
            self.decel_start = self.total_steps - self.config.ramp_steps

        # Sécurité: s'assurer que decel_start >= accel_end
        if self.decel_start < self.accel_end:
            mid = self.total_steps // 2
            self.accel_end = mid
            self.decel_start = mid

    def _s_curve(self, t: float) -> float:
        """
        Fonction S-curve (sigmoïde) pour transition douce.

        Args:
            t: Valeur normalisée entre 0 et 1

        Returns:
            Valeur interpolée avec courbe en S (0 à 1)
        """
        # Sigmoïde: 1 / (1 + e^(-k*(t-0.5))) normalisée
        # k=10 donne une courbe en S prononcée mais pas trop abrupte
        k = 10
        sigmoid = 1 / (1 + math.exp(-k * (t - 0.5)))
        # Normaliser pour que sigmoid(0) = 0 et sigmoid(1) = 1
        sigmoid_0 = 1 / (1 + math.exp(-k * (-0.5)))
        sigmoid_1 = 1 / (1 + math.exp(-k * (0.5)))
        return (sigmoid - sigmoid_0) / (sigmoid_1 - sigmoid_0)

    def _linear(self, t: float) -> float:
        """
        Interpolation linéaire simple.

        Args:
            t: Valeur normalisée entre 0 et 1

        Returns:
            Même valeur (linéaire)
        """
        return t

    def _interpolate(self, t: float) -> float:
        """
        Interpole entre 0 et 1 selon la méthode configurée.

        Args:
            t: Progression normalisée (0 = début, 1 = fin)

        Returns:
            Valeur interpolée entre 0 et 1
        """
        if self.config.use_s_curve:
            return self._s_curve(t)
        return self._linear(t)

    def get_delay(self, step_index: int) -> float:
        """
        Calcule le délai pour un pas donné.

        Args:
            step_index: Index du pas actuel (0 à total_steps-1)

        Returns:
            Délai en secondes pour ce pas
        """
        # Rampe désactivée ou hors limites
        if not self.ramp_enabled:
            return self.target_delay

        if step_index < 0:
            step_index = 0
        elif step_index >= self.total_steps:
            step_index = self.total_steps - 1

        start_delay = self.config.start_delay

        # Phase d'accélération (départ lent → vitesse nominale)
        if step_index < self.accel_end:
            t = step_index / self.accel_end
            progress = self._interpolate(t)
            # Interpoler de start_delay vers target_delay
            return start_delay + (self.target_delay - start_delay) * progress

        # Phase de décélération (vitesse nominale → arrêt lent)
        if step_index >= self.decel_start:
            steps_in_decel = step_index - self.decel_start
            decel_length = self.total_steps - self.decel_start
            t = steps_in_decel / decel_length if decel_length > 0 else 1
            progress = self._interpolate(t)
            # Interpoler de target_delay vers start_delay
            return self.target_delay + (start_delay - self.target_delay) * progress

        # Phase de croisière (vitesse nominale constante)
        return self.target_delay

    def get_phase(self, step_index: int) -> str:
        """
        Retourne la phase actuelle du mouvement.

        Args:
            step_index: Index du pas actuel

        Returns:
            'acceleration', 'cruise', ou 'deceleration'
        """
        if not self.ramp_enabled:
            return 'cruise'

        if step_index < self.accel_end:
            return 'acceleration'
        elif step_index >= self.decel_start:
            return 'deceleration'
        return 'cruise'

    @property
    def stats(self) -> dict:
        """
        Retourne les statistiques de la rampe.

        Returns:
            dict avec les paramètres calculés
        """
        return {
            'total_steps': self.total_steps,
            'target_delay': self.target_delay,
            'start_delay': self.config.start_delay,
            'ramp_enabled': self.ramp_enabled,
            'accel_steps': self.accel_end if self.ramp_enabled else 0,
            'cruise_steps': (self.decel_start - self.accel_end) if self.ramp_enabled else self.total_steps,
            'decel_steps': (self.total_steps - self.decel_start) if self.ramp_enabled else 0,
            'use_s_curve': self.config.use_s_curve
        }


def create_ramp_for_rotation(
    angle_deg: float,
    steps_per_dome_revolution: int,
    target_delay: float,
    config: Optional[RampConfig] = None
) -> AccelerationRamp:
    """
    Crée une rampe pour une rotation donnée.

    Fonction utilitaire pour créer une rampe à partir d'un angle
    plutôt que d'un nombre de pas.

    Args:
        angle_deg: Angle de rotation en degrés (valeur absolue utilisée)
        steps_per_dome_revolution: Nombre de pas par tour de coupole
        target_delay: Délai cible en secondes
        config: Configuration optionnelle

    Returns:
        AccelerationRamp configurée pour le mouvement
    """
    deg_per_step = 360.0 / steps_per_dome_revolution
    total_steps = int(abs(angle_deg) / deg_per_step)
    return AccelerationRamp(total_steps, target_delay, config)
