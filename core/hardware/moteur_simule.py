"""
Moteur simulé pour tests sans matériel.

Cette classe simule l'interface du MoteurCoupole pour permettre
le développement et les tests sans accès au matériel réel.

VERSION 4.0 : Intègre les méthodes de feedback simulées.
VERSION 4.3 : Ajout get_feedback_controller, get_daemon_angle, rotation_absolue
              pour compatibilité avec MoteurCoupole refactorisé.
VERSION 4.4 : Simulation réaliste du déplacement (faire_un_pas, get_daemon_angle)
VERSION 4.5 : Compatibilité paramètre use_ramp (ignoré en simulation)
VERSION 4.6 : Timing réaliste pour GOTO (délai proportionnel au mouvement)
"""

import logging
import time
from typing import Dict, Any, Optional


# Position simulée par instance (isolation des tests)
# Le module maintient un registre des positions par ID d'instance
_instance_positions: dict[int, float] = {}

# Position "globale" pour compatibilité avec set_simulated_position/get_simulated_position
_global_position = 0.0

# Multiplicateur de vitesse pour la simulation (1.0 = temps réel, 10.0 = 10x plus rapide)
# En mode dev, on accélère pour ne pas attendre des minutes
SIMULATION_SPEED_MULTIPLIER = 20.0  # 20x plus rapide (un GOTO de 2 min = 6 secondes)


def set_simulated_position(position: float):
    """
    Définit la position simulée globale.

    Utilisé par les handlers (command_handlers.py) pour synchroniser
    la position avant une commande en mode simulation.
    """
    global _global_position
    _global_position = position % 360


def get_simulated_position() -> float:
    """
    Retourne la position simulée globale.

    Utilisé par les handlers pour lire la position après une commande.
    """
    return _global_position


def _get_instance_position(instance_id: int) -> float:
    """Retourne la position d'une instance spécifique."""
    return _instance_positions.get(instance_id, 0.0)


def _set_instance_position(instance_id: int, position: float):
    """Définit la position d'une instance spécifique."""
    _instance_positions[instance_id] = position % 360


def reset_all_simulated_positions():
    """
    Remet toutes les positions à zéro.

    À appeler dans conftest.py pour garantir l'isolation des tests.
    """
    global _global_position
    _global_position = 0.0
    _instance_positions.clear()


class MoteurSimule:
    """Moteur simulé pour tests."""

    def __init__(self, config_moteur=None):
        self.logger = logging.getLogger(__name__)
        self._instance_id = id(self)

        if config_moteur:
            if hasattr(config_moteur, 'steps_per_dome_revolution'):
                # Déjà un MotorParams ou objet avec propriété calculée
                self.steps_per_dome_revolution = config_moteur.steps_per_dome_revolution
            else:
                # Utiliser le parser centralisé (dict ou dataclass)
                from core.hardware.motor_config_parser import parse_motor_config
                params = parse_motor_config(config_moteur)
                self.steps_per_dome_revolution = params.steps_per_dome_revolution
        else:
            self.steps_per_dome_revolution = 1941866  # Valeur par défaut

        # Initialiser la position de cette instance à la position globale actuelle
        # (pour compatibilité avec les handlers qui utilisent set_simulated_position)
        _set_instance_position(self._instance_id, _global_position)
        self.position_actuelle = _global_position

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

        Met à jour la position de cette instance ET la position globale
        pour compatibilité avec les handlers.
        """
        global _global_position

        # Calculer le déplacement en degrés
        delta = self.degrees_per_step * self.direction

        # Mettre à jour la position de cette instance
        new_pos = (_get_instance_position(self._instance_id) + delta) % 360
        _set_instance_position(self._instance_id, new_pos)

        # Synchroniser la position globale pour les handlers
        _global_position = new_pos
        self.position_actuelle = new_pos

    def _calculer_delai_rampe(self, step_index: int, total_steps: int,
                               vitesse_nominale: float) -> float:
        """Calcule le délai pour un pas (retourne toujours la vitesse nominale en simulation)."""
        return vitesse_nominale

    def _calculate_movement_time(self, angle_deg: float, vitesse: float) -> float:
        """
        Calcule le temps de mouvement simulé.

        Args:
            angle_deg: Angle en degrés (absolu)
            vitesse: Délai par pas en secondes

        Returns:
            Temps de mouvement en secondes (divisé par SIMULATION_SPEED_MULTIPLIER)
        """
        # Nombre de pas pour ce mouvement
        steps = abs(angle_deg) / 360.0 * self.steps_per_dome_revolution

        # Temps réel = steps * délai par pas
        real_time = steps * vitesse

        # Temps simulé (accéléré)
        simulated_time = real_time / SIMULATION_SPEED_MULTIPLIER

        return simulated_time

    def rotation(self, angle_deg: float, vitesse: float = 0.0015, use_ramp: bool = True):
        """
        Simule une rotation avec timing réaliste.

        Args:
            angle_deg: Angle en degrés
            vitesse: Délai nominal par pas (utilisé pour calculer le temps simulé)
            use_ramp: Rampe d'accélération (ignoré en simulation, pour compatibilité)
        """
        global _global_position

        # Calculer le temps de mouvement simulé
        movement_time = self._calculate_movement_time(angle_deg, vitesse)

        # Log du mouvement prévu
        if abs(angle_deg) > 1.0:
            self.logger.info(
                f"Rotation simulée: {angle_deg:+.1f}° "
                f"(~{movement_time:.1f}s simulé, {movement_time * SIMULATION_SPEED_MULTIPLIER:.0f}s réel)"
            )

        # Simuler le délai (permet au popup GOTO d'apparaître)
        if movement_time > 0.1:
            time.sleep(movement_time)

        # Mettre à jour la position de cette instance
        new_pos = (_get_instance_position(self._instance_id) + angle_deg) % 360
        _set_instance_position(self._instance_id, new_pos)

        # Synchroniser la position globale pour les handlers
        _global_position = new_pos
        self.position_actuelle = new_pos

    def rotation_absolue(self, position_cible_deg: float, position_actuelle_deg: float,
                        vitesse: float = 0.0015, use_ramp: bool = True):
        """
        Rotation vers une position absolue.

        Args:
            position_cible_deg: Position cible en degrés
            position_actuelle_deg: Position actuelle en degrés
            vitesse: Délai nominal (ignoré en simulation)
            use_ramp: Rampe d'accélération (ignoré en simulation, pour compatibilité)
        """
        position_cible = position_cible_deg % 360
        position_actuelle = position_actuelle_deg % 360

        diff = position_cible - position_actuelle
        if diff > 180:
            diff -= 360
        elif diff < -180:
            diff += 360

        self.rotation(diff, vitesse, use_ramp=use_ramp)

    # =========================================================================
    # MÉTHODES DÉMON (simulées)
    # =========================================================================

    @staticmethod
    def get_daemon_angle(timeout_ms: int = 200) -> float:
        """Retourne la position simulée globale."""
        return _global_position

    @staticmethod
    def get_daemon_status() -> Optional[dict]:
        """Retourne un statut simulé."""
        return {
            'angle': _global_position,
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
        max_correction_par_iteration: float = 45.0,
        allow_large_movement: bool = False
    ) -> Dict[str, Any]:
        """
        Simule une rotation avec feedback et timing réaliste.

        En mode simulation, le mouvement est toujours parfait mais
        prend un temps proportionnel au déplacement.
        """
        start_time = time.time()

        # Utiliser la position de cette instance
        position_initiale = _get_instance_position(self._instance_id)

        # Calculer le delta
        delta = angle_cible - position_initiale
        while delta > 180:
            delta -= 360
        while delta < -180:
            delta += 360

        # Appliquer le mouvement (inclut le délai simulé)
        self.rotation(delta, vitesse)

        temps_total = time.time() - start_time

        return {
            'success': True,
            'position_initiale': position_initiale,
            'position_finale': angle_cible,
            'position_cible': angle_cible,
            'erreur_finale': 0.0,
            'iterations': 1,
            'corrections': [],
            'temps_total': temps_total,
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
        # Utiliser la position de cette instance
        current_pos = _get_instance_position(self._instance_id)
        angle_cible = (current_pos + delta_deg) % 360
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