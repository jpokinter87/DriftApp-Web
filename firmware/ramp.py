"""
Rampe d'acceleration/deceleration S-curve pour RP2040.

Port de core/hardware/acceleration_ramp.py adapte a MicroPython.
Memes parametres et meme comportement que la version Pi.

Usage:
    ramp = Ramp(total_steps=5000, target_delay_us=150, ramp_type="SCURVE")
    delays = ramp.compute_delays()  # liste de delais par pas
"""

import math


# Parametres de rampe (identiques a acceleration_ramp.py)
RAMP_START_DELAY_US = 3000   # 3 ms — delai de demarrage lent
RAMP_STEPS = 500             # Nombre de pas pour atteindre la vitesse nominale
MIN_STEPS_FOR_RAMP = 200     # Seuil minimum pour appliquer la rampe
SHORT_MOVEMENT_RATIO = 4     # Diviseur pour rampe proportionnelle


class Ramp:
    """
    Gestionnaire de rampe d'acceleration/deceleration.

    Calcule le delai optimal pour chaque pas en fonction de sa position
    dans le mouvement total.
    """

    def __init__(self, total_steps, target_delay_us, ramp_type="SCURVE"):
        """
        Args:
            total_steps: Nombre total de pas du mouvement
            target_delay_us: Delai cible (vitesse nominale) en microsecondes
            ramp_type: "SCURVE", "LINEAR", ou "NONE"
        """
        self.total_steps = total_steps
        self.target_delay_us = target_delay_us
        self.ramp_type = ramp_type.upper() if ramp_type else "NONE"

        self.ramp_enabled = False
        self.accel_end = 0
        self.decel_start = total_steps

        if self.ramp_type != "NONE":
            self._calculate_phases()

    def _calculate_phases(self):
        """Calcule les limites des phases d'acceleration et deceleration."""
        if self.total_steps < MIN_STEPS_FOR_RAMP:
            self.ramp_enabled = False
            return

        self.ramp_enabled = True

        if self.total_steps < 2 * RAMP_STEPS:
            # Mouvement court : rampe proportionnelle
            ramp_length = max(1, self.total_steps // SHORT_MOVEMENT_RATIO)
            self.accel_end = ramp_length
            self.decel_start = self.total_steps - ramp_length
        else:
            # Mouvement normal : rampe complete
            self.accel_end = RAMP_STEPS
            self.decel_start = self.total_steps - RAMP_STEPS

        # Securite
        if self.decel_start < self.accel_end:
            mid = self.total_steps // 2
            self.accel_end = mid
            self.decel_start = mid

    def _s_curve(self, t):
        """
        Fonction S-curve (sigmoide) pour transition douce.

        Args:
            t: Valeur normalisee entre 0 et 1

        Returns:
            Valeur interpolee avec courbe en S (0 a 1)
        """
        k = 10
        sigmoid = 1.0 / (1.0 + math.exp(-k * (t - 0.5)))
        sigmoid_0 = 1.0 / (1.0 + math.exp(-k * (-0.5)))
        sigmoid_1 = 1.0 / (1.0 + math.exp(-k * 0.5))
        return (sigmoid - sigmoid_0) / (sigmoid_1 - sigmoid_0)

    def _interpolate(self, t):
        """Interpole entre 0 et 1 selon le type de rampe."""
        if self.ramp_type == "SCURVE":
            return self._s_curve(t)
        # LINEAR
        return t

    def get_delay(self, step_index):
        """
        Calcule le delai pour un pas donne.

        Args:
            step_index: Index du pas actuel (0 a total_steps-1)

        Returns:
            int: Delai en microsecondes pour ce pas
        """
        if not self.ramp_enabled:
            return self.target_delay_us

        start = RAMP_START_DELAY_US
        target = self.target_delay_us

        # Phase d'acceleration
        if step_index < self.accel_end:
            if self.accel_end == 0:
                return target
            t = step_index / self.accel_end
            progress = self._interpolate(t)
            return int(start + (target - start) * progress)

        # Phase de deceleration
        if step_index >= self.decel_start:
            steps_in_decel = step_index - self.decel_start
            decel_length = self.total_steps - self.decel_start
            t = steps_in_decel / decel_length if decel_length > 0 else 1.0
            progress = self._interpolate(t)
            return int(target + (start - target) * progress)

        # Phase de croisiere
        return target

    def compute_delays(self):
        """
        Indique si la rampe est active (delais variables).

        Returns:
            True si rampe active (utiliser get_delay() par pas),
            None si delai uniforme
        """
        if not self.ramp_enabled:
            return None
        # Retourner True au lieu d'une liste pour eviter OOM sur RP2040
        # (53940 floats = ~430 KB > RAM disponible)
        # L'appelant utilise get_delay(i) pour chaque pas
        return True
