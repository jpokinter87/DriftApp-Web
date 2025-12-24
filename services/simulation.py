"""
Simulation - Composants pour le mode simulation (développement PC).

Ce module fournit les classes de simulation pour exécuter
Motor Service sans matériel réel (pas de Raspberry Pi).

Date: Décembre 2025
Version: 4.4
"""

import logging


logger = logging.getLogger("Simulation")


class SimulatedDaemonReader:
    """
    Lecteur simulé pour le daemon encodeur.

    En mode simulation, lit la position depuis MoteurSimule
    au lieu du fichier /dev/shm/ems22_position.json.
    """

    def __init__(self):
        self.logger = logging.getLogger("SimulatedDaemonReader")

    def is_available(self) -> bool:
        """Toujours disponible en simulation."""
        return True

    def read_raw(self) -> dict:
        """Retourne un statut simulé."""
        from core.hardware.moteur_simule import get_simulated_position
        return {
            'angle': get_simulated_position(),
            'calibrated': True,
            'status': 'OK (simulation)',
            'raw': 0
        }

    def read_angle(self, timeout_ms: int = 200) -> float:
        """Retourne la position simulée."""
        from core.hardware.moteur_simule import get_simulated_position
        return get_simulated_position()

    def read_status(self) -> dict:
        """Retourne le statut complet simulé."""
        return self.read_raw()

    def read_stable(self, num_samples: int = 3, delay_ms: int = 10,
                    stabilization_ms: int = 50) -> float:
        """Retourne la position simulée (pas de moyennage nécessaire)."""
        return self.read_angle()
