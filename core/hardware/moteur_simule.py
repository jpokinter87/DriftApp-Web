"""
Moteur simulé pour tests sans matériel.

Cette classe simule l'interface du MoteurCoupole pour permettre
le développement et les tests sans accès au matériel réel.

VERSION 4.0 : Intègre les méthodes de feedback simulées.
VERSION 4.3 : Ajout get_feedback_controller, get_daemon_angle, rotation_absolue
              pour compatibilité avec MoteurCoupole refactorisé.
VERSION 4.4 : Simulation réaliste du déplacement (faire_un_pas, get_daemon_angle)
"""

import logging
from typing import Dict, Any, Optional


# Variable globale pour partager la position entre instances (singleton pattern)
_simulated_position = 0.0


def set_simulated_position(position: float):
    """Permet de synchroniser la position simulée depuis l'extérieur."""
    global _simulated_position
    _simulated_position = position % 360


def get_simulated_position() -> float:
    """Retourne la position simulée actuelle."""
    return _simulated_position


class MoteurSimule:
    """Moteur simulé pour tests."""

    def __init__(self, config_moteur=None):
        self.logger = logging.getLogger("MoteurSimule")

        if config_moteur:
            if hasattr(config_moteur, 'steps_per_dome_revolution'):
                self.steps_per_dome_revolution = config_moteur.steps_per_dome_revolution
            elif hasattr(config_moteur, 'steps_per_revolution'):
                # Dataclass
                self.steps_per_dome_revolution = int(
                    config_moteur.steps_per_revolution *
                    config_moteur.microsteps *
                    config_moteur.gear_ratio *
                    config_moteur.steps_correction_factor
                )
            else:
                # Dict
                self.steps_per_dome_revolution = int(
                    config_moteur['steps_per_revolution'] *
                    config_moteur['microsteps'] *
                    config_moteur['gear_ratio'] *
                    config_moteur['steps_correction_factor']
                )
        else:
            self.steps_per_dome_revolution = 1941866  # Valeur calculée

        global _simulated_position

        # Position simulée (partagée via variable globale)
        self.position_actuelle = _simulated_position

        # Direction actuelle (1 = horaire, -1 = anti-horaire)
        self.direction = 1

        # Flag pour arrêt non bloquant de la boucle feedback
        self.stop_requested = False

        # Paramètres rampe (pour compatibilité)
        self.ramp_start_delay = 0.003
        self.ramp_steps = 400  # Aligné avec moteur.py
        self.ramp_enabled = True

        # Degrés par pas (pour simulation réaliste)
        self.degrees_per_step = 360.0 / self.steps_per_dome_revolution

        self.logger.info(f"Moteur SIMULÉ initialisé - Steps/tour: {self.steps_per_dome_revolution}")

    def definir_direction(self, direction: int):
        """Définit la direction de rotation."""
        self.direction = direction

    def faire_un_pas(self, delai: float = 0.0):
        """
        Simule un pas moteur.

        En mode simulation, met à jour la position globale.
        """
        global _simulated_position

        # Calculer le déplacement en degrés
        delta = self.degrees_per_step * self.direction

        # Mettre à jour la position
        _simulated_position = (_simulated_position + delta) % 360
        self.position_actuelle = _simulated_position

    def _calculer_delai_rampe(self, step_index: int, total_steps: int,
                               vitesse_nominale: float) -> float:
        """Calcule le délai pour un pas (retourne toujours la vitesse nominale en simulation)."""
        return vitesse_nominale

    def rotation(self, angle_deg: float, vitesse: float = 0.0015):
        """Simule une rotation."""
        global _simulated_position
        # Utiliser la position globale synchronisée
        _simulated_position = (_simulated_position + angle_deg) % 360
        self.position_actuelle = _simulated_position  # Synchroniser aussi l'attribut local

    def rotation_absolue(self, position_cible_deg: float, position_actuelle_deg: float,
                        vitesse: float = 0.0015):
        """Rotation vers une position absolue."""
        position_cible = position_cible_deg % 360
        position_actuelle = position_actuelle_deg % 360

        diff = position_cible - position_actuelle
        if diff > 180:
            diff -= 360
        elif diff < -180:
            diff += 360

        self.rotation(diff, vitesse)

    # =========================================================================
    # MÉTHODES DÉMON (simulées)
    # =========================================================================

    @staticmethod
    def get_daemon_angle(timeout_ms: int = 200) -> float:
        """Retourne la position simulée."""
        global _simulated_position
        return _simulated_position

    @staticmethod
    def get_daemon_status() -> Optional[dict]:
        """Retourne un statut simulé."""
        global _simulated_position
        return {
            'angle': _simulated_position,
            'calibrated': True,
            'status': 'OK (simulation)',
            'timestamp': 0
        }

    # =========================================================================
    # CONTRÔLE D'ARRÊT
    # =========================================================================

    def request_stop(self):
        """
        Demande l'arrêt de la boucle de feedback en cours.
        Cette méthode est non bloquante et permet d'arrêter
        la correction en cours sans attendre la fin de toutes les itérations.
        """
        self.stop_requested = True

    def clear_stop_request(self):
        """
        Efface le flag d'arrêt pour permettre de nouvelles corrections.
        """
        self.stop_requested = False

    def rotation_avec_feedback(
        self,
        angle_cible: float,
        vitesse: float = 0.001,
        tolerance: float = 0.5,
        max_iterations: int = 10,
        max_correction_par_iteration: float = 45.0
    ) -> Dict[str, Any]:
        """
        Simule une rotation avec feedback.

        En mode simulation, le mouvement est toujours parfait.
        """
        global _simulated_position
        # Utiliser la position globale synchronisée, pas self.position_actuelle
        position_initiale = _simulated_position

        # Calculer le delta
        delta = angle_cible - _simulated_position
        while delta > 180:
            delta -= 360
        while delta < -180:
            delta += 360

        # Appliquer le mouvement
        self.rotation(delta, vitesse)

        return {
            'success': True,
            'position_initiale': position_initiale,
            'position_finale': angle_cible,
            'position_cible': angle_cible,
            'erreur_finale': 0.0,
            'iterations': 1,
            'corrections': [],
            'temps_total': 0.1,
            'mode': 'simulation'
        }

    def rotation_relative_avec_feedback(
        self,
        delta_deg: float,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Simule une rotation relative avec feedback.
        """
        global _simulated_position
        # Utiliser la position globale synchronisée
        angle_cible = (_simulated_position + delta_deg) % 360
        return self.rotation_avec_feedback(angle_cible=angle_cible, **kwargs)

    # =========================================================================
    # FEEDBACK CONTROLLER (simulé)
    # =========================================================================

    def get_feedback_controller(self):
        """
        Retourne un contrôleur de feedback simulé.

        En simulation, retourne self car les méthodes de feedback
        sont déjà implémentées dans cette classe.
        """
        return self

    def nettoyer(self):
        pass