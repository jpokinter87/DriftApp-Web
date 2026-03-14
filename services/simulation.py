"""
Simulation - Composants pour le mode simulation (développement PC).

Ce module fournit les classes de simulation pour exécuter
Motor Service sans matériel réel (pas de Raspberry Pi).

Les délais simulés reproduisent les latences réelles du matériel
pour minimiser les surprises lors des tests terrain.

Date: Décembre 2025
Version: 4.6 - Délais réalistes pour simulation fidèle
"""

import logging
import time


logger = logging.getLogger(__name__)

# Latence I2C typique de l'encodeur EMS22A (~1ms)
_I2C_LATENCY_S = 0.001


class SimulatedDaemonReader:
    """
    Lecteur simulé pour le daemon encodeur.

    En mode simulation, lit la position depuis MoteurSimule
    au lieu du fichier /dev/shm/ems22_position.json.

    Les délais sont calibrés pour reproduire le comportement
    réel de l'encodeur EMS22A sur bus I2C.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def is_available(self) -> bool:
        """Toujours disponible en simulation."""
        return True

    def read_raw(self) -> dict:
        """Retourne un statut simulé (pas de délai — utilisé pour le statut, pas la position)."""
        from core.hardware.moteur_simule import get_simulated_position

        return {
            "angle": get_simulated_position(),
            "calibrated": True,
            "status": "OK (simulation)",
            "raw": 0,
        }

    def read_angle(self, timeout_ms: int = 200) -> float:
        """
        Retourne la position simulée avec latence I2C réaliste.

        Args:
            timeout_ms: Timeout en ms (respecté : le délai simulé est toujours < timeout)
        """
        from core.hardware.moteur_simule import get_simulated_position

        # Simuler la latence I2C réelle (~1ms), sans dépasser le timeout
        delay = min(_I2C_LATENCY_S, timeout_ms / 1000.0)
        time.sleep(delay)
        return get_simulated_position()

    def read_status(self) -> dict:
        """Retourne le statut complet simulé."""
        return self.read_raw()

    def read_stable(
        self, num_samples: int = 3, delay_ms: int = 10, stabilization_ms: int = 50
    ) -> float:
        """
        Retourne la position simulée avec temps de stabilisation réaliste.

        En production, le daemon attend la stabilisation du signal encodeur
        avant de retourner une position fiable. Ce délai est reproduit ici.

        Args:
            num_samples: Nombre d'échantillons (non utilisé en simulation)
            delay_ms: Délai entre échantillons en ms (non utilisé en simulation)
            stabilization_ms: Temps de stabilisation en ms (simulé)
        """
        time.sleep(stabilization_ms / 1000.0)
        return self.read_angle()
