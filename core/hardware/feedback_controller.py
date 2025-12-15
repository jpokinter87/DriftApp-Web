"""
Contrôleur de feedback encodeur pour la coupole.

Gère la boucle de correction en boucle fermée utilisant le démon encodeur.
Extrait de moteur.py pour respecter le principe de responsabilité unique.

Date: 9 décembre 2025
"""

import logging
import time
from typing import Dict, Any, Optional, TYPE_CHECKING

from core.utils.angle_utils import shortest_angular_distance

if TYPE_CHECKING:
    from core.hardware.moteur import MoteurCoupole, DaemonEncoderReader


class FeedbackController:
    """
    Contrôleur de feedback pour rotation avec correction en boucle fermée.

    Utilise le démon encodeur pour mesurer la position réelle et
    corrige itérativement jusqu'à atteindre la tolérance souhaitée.

    Usage:
        moteur = MoteurCoupole(config)
        feedback = FeedbackController(moteur, daemon_reader)
        result = feedback.rotation_avec_feedback(angle_cible=45.0)
    """

    def __init__(self, moteur: 'MoteurCoupole', daemon_reader: 'DaemonEncoderReader'):
        """
        Initialise le contrôleur de feedback.

        Args:
            moteur: Instance de MoteurCoupole pour le contrôle moteur
            daemon_reader: Instance de DaemonEncoderReader pour la lecture position
        """
        self.moteur = moteur
        self.daemon_reader = daemon_reader
        self.logger = logging.getLogger("FeedbackController")
        self.stop_requested = False

    # =========================================================================
    # CONTRÔLE D'ARRÊT
    # =========================================================================

    def request_stop(self):
        """Demande l'arrêt de la boucle de feedback en cours."""
        self.stop_requested = True
        self.moteur.stop_requested = True
        self.logger.info("Arrêt de la boucle feedback demandé")

    def clear_stop_request(self):
        """Efface le flag d'arrêt pour permettre de nouvelles corrections."""
        self.stop_requested = False
        self.moteur.stop_requested = False

    # =========================================================================
    # CALCULS UTILITAIRES
    # =========================================================================

    def _calculer_delta_angulaire(self, angle_actuel: float, angle_cible: float) -> float:
        """
        Calcule le delta angulaire le plus court entre deux angles.

        Args:
            angle_actuel: Angle actuel (0-360°)
            angle_cible: Angle cible (0-360°)

        Returns:
            Delta angulaire avec signe (-180 à +180°)
        """
        return shortest_angular_distance(angle_actuel, angle_cible)

    def _lire_position_stable(self) -> float:
        """
        Lecture position via démon avec moyenne pour stabilité.

        Returns:
            Position moyenne en degrés
        """
        return self.daemon_reader.read_stable(num_samples=3, delay_ms=10, stabilization_ms=50)

    def _calculer_correction(self, erreur: float,
                             max_correction: float) -> tuple:
        """
        Calcule les paramètres de correction.

        Returns:
            tuple: (angle_correction, direction, steps)
        """
        angle_correction = min(abs(erreur), max_correction)
        direction = 1 if erreur > 0 else -1
        deg_per_step = 360.0 / self.moteur.steps_per_dome_revolution
        steps = int(angle_correction / deg_per_step)
        return angle_correction, direction, steps

    # =========================================================================
    # RÉSULTATS
    # =========================================================================

    def _creer_resultat_sans_feedback(self, angle_cible: float,
                                       start_time: float) -> Dict[str, Any]:
        """Crée un résultat pour le mode sans feedback."""
        return {
            'success': False,
            'position_initiale': 0,
            'position_finale': angle_cible,
            'position_cible': angle_cible,
            'erreur_finale': 0,
            'iterations': 0,
            'temps_total': time.time() - start_time,
            'corrections': [],
            'mode': 'sans_feedback'
        }

    def _creer_resultat(self, success: bool, position_initiale: float,
                        position_finale: float, angle_cible: float,
                        erreur_finale: float, iterations: int,
                        corrections: list, temps_total: float) -> Dict[str, Any]:
        """Crée le résultat final de la rotation."""
        return {
            'success': success,
            'position_initiale': position_initiale,
            'position_finale': position_finale,
            'position_cible': angle_cible,
            'erreur_finale': erreur_finale,
            'iterations': iterations,
            'corrections': corrections,
            'temps_total': temps_total,
            'mode': 'feedback_daemon'
        }

    # =========================================================================
    # EXÉCUTION DES PAS
    # =========================================================================

    def _executer_pas_avec_verification(self, steps: int, vitesse: float,
                                         angle_cible: float,
                                         tolerance: float) -> None:
        """
        Exécute les pas - VERSION OPTIMISÉE alignée sur calibration_moteur.py.

        CHANGEMENT CRITIQUE : Plus de vérification pendant le mouvement !
        - Le feedback se fait APRÈS le mouvement complet, pas pendant
        - Cela garantit un flux de pulses continu sans interruption
        - Identique au comportement de calibration_moteur.py qui fonctionne

        AJOUT : Vérification stop_requested tous les 1000 pas pour permettre
        l'arrêt via bouton STOPPER (overhead négligeable : 1 check / 1000 pas).
        """
        # Boucle avec vérification arrêt périodique (tous les 1000 pas)
        for i in range(steps):
            if i % 1000 == 0 and self.stop_requested:
                self.logger.info(f"Arrêt demandé à {i}/{steps} pas")
                break
            self.moteur.faire_un_pas(delai=vitesse)

    def _verifier_arret_anticipe(self, angle_cible: float, tolerance: float,
                                  step_index: int, total_steps: int) -> bool:
        """Vérifie si on peut arrêter les pas plus tôt."""
        try:
            pos_courante = self.daemon_reader.read_angle(timeout_ms=50)
            delta_actuel = self._calculer_delta_angulaire(pos_courante, angle_cible)
            if abs(delta_actuel) < tolerance:
                self.logger.debug(f"Arrêt anticipé à {step_index+1}/{total_steps} pas")
                return True
        except RuntimeError:
            pass
        return False

    # =========================================================================
    # ENREGISTREMENT
    # =========================================================================

    def _enregistrer_correction(self, iteration: int, position_avant: float,
                                 erreur_avant: float, angle_correction: float,
                                 direction: int, steps: int,
                                 correction_start: float,
                                 angle_cible: float) -> dict:
        """Enregistre les statistiques d'une correction."""
        correction_duration = time.time() - correction_start

        try:
            position_apres = self._lire_position_stable()
            erreur_apres = self._calculer_delta_angulaire(position_apres, angle_cible)
        except RuntimeError:
            position_apres = position_avant + (angle_correction * direction)
            erreur_apres = erreur_avant - (angle_correction * direction)

        return {
            'iteration': iteration + 1,
            'position_avant': position_avant,
            'erreur_avant': erreur_avant,
            'correction_demandee': angle_correction * direction,
            'steps': steps,
            'duration': correction_duration,
            'erreur_apres': erreur_apres
        }

    def _log_resultat_final(self, success: bool, position_initiale: float,
                            position_finale: float, erreur_finale: float,
                            iteration: int, max_iterations: int,
                            temps_total: float) -> None:
        """Log le résultat final de la rotation."""
        if success:
            self.logger.info(
                f"Rotation feedback réussie: {position_initiale:.1f}° -> "
                f"{position_finale:.1f}° (erreur: {erreur_finale:+.2f}°, "
                f"{iteration} iter, {temps_total:.1f}s)"
            )
        else:
            self.logger.warning(
                f"Rotation feedback imprécise: {position_initiale:.1f}° -> "
                f"{position_finale:.1f}° (erreur: {erreur_finale:+.2f}°, "
                f"{iteration}/{max_iterations} iter)"
            )

    # =========================================================================
    # BOUCLE DE CORRECTION
    # =========================================================================

    def _executer_iteration(self, angle_cible: float, vitesse: float,
                            tolerance: float, max_correction: float,
                            iteration: int, position_initiale: float = None,
                            allow_large_movement: bool = False) -> Optional[dict]:
        """
        Exécute une itération de la boucle de correction.

        Args:
            position_initiale: Position de départ (pour détecter recalibration switch)
            allow_large_movement: Si True, désactive la protection contre les grands mouvements
                                  (utilisé pour GOTO initial)

        Returns:
            dict avec les stats de correction, ou None si objectif atteint/erreur
        """
        # Lecture position et calcul erreur
        try:
            position_actuelle = self._lire_position_stable()
        except RuntimeError:
            self.logger.warning(f"Erreur lecture démon à l'itération {iteration}")
            return None

        # PROTECTION SWITCH: Détecter si la position a sauté (recalibration switch)
        # Si la position a changé de plus de 10° sans mouvement, c'est une recalibration
        if position_initiale is not None and iteration > 0:
            saut = abs(self._calculer_delta_angulaire(position_actuelle, position_initiale))
            if saut > 10.0:
                self.logger.warning(
                    f"  ⚠️ Saut de position détecté ({saut:.1f}°) - probable recalibration switch"
                )
                self.logger.warning(f"  → Abandon de la correction pour éviter mouvement erratique")
                return None

        erreur = self._calculer_delta_angulaire(position_actuelle, angle_cible)
        self.logger.debug(
            f"  Iter {iteration+1}: Pos={position_actuelle:.1f}° Erreur={erreur:+.2f}°"
        )

        # Objectif atteint ?
        if abs(erreur) < tolerance:
            self.logger.debug(f"  Objectif atteint ! Erreur={erreur:+.2f}°")
            return None

        # PROTECTION: Si l'erreur est trop grande (> 20°), quelque chose ne va pas
        # Sauf si allow_large_movement=True (GOTO initial)
        if abs(erreur) > 20.0 and not allow_large_movement:
            self.logger.warning(
                f"  ⚠️ Erreur anormalement grande ({erreur:+.1f}°) - abandon correction"
            )
            return None

        # Calcul de la correction
        angle_correction, direction, steps = self._calculer_correction(
            erreur, max_correction
        )

        if steps == 0:
            self.logger.debug("  Erreur trop petite pour un pas")
            return None

        self.logger.debug(
            f"  Correction: {angle_correction * direction:+.2f}° ({steps} pas)"
        )

        # Exécution de la correction
        self.moteur.definir_direction(direction)
        correction_start = time.time()
        self._executer_pas_avec_verification(steps, vitesse, angle_cible, tolerance)

        # Enregistrer la correction
        return self._enregistrer_correction(
            iteration, position_actuelle, erreur, angle_correction,
            direction, steps, correction_start, angle_cible
        )

    # =========================================================================
    # MÉTHODES PUBLIQUES
    # =========================================================================

    def rotation_avec_feedback(
        self,
        angle_cible: float,
        vitesse: float = 0.001,
        tolerance: float = 0.5,
        max_iterations: int = 10,
        max_correction_par_iteration: float = 180.0,
        allow_large_movement: bool = False
    ) -> Dict[str, Any]:
        """
        Rotation avec feedback via démon encodeur.

        Args:
            angle_cible: Angle cible absolu (0-360°)
            vitesse: Délai moteur (secondes/pas), défaut 0.001s
            tolerance: Tolérance acceptable (°), défaut 0.5°
            max_iterations: Nombre max d'itérations, défaut 10
            max_correction_par_iteration: Correction max par itération (°)
                                          180° = mouvement continu sans interruption
            allow_large_movement: Si True, autorise les grands mouvements (> 20°)
                                  Utilisé pour GOTO initial après calibration

        Returns:
            dict: Statistiques du mouvement (success, positions, erreur, etc.)
        """
        start_time = time.time()
        self.clear_stop_request()

        # Lecture position initiale
        try:
            position_initiale = self._lire_position_stable()
        except RuntimeError as e:
            self.logger.error(f"Démon encodeur non disponible: {e}")
            self.logger.warning("Passage en mode sans feedback")
            delta = self._calculer_delta_angulaire(0, angle_cible)
            self.moteur.rotation(delta, vitesse)
            return self._creer_resultat_sans_feedback(angle_cible, start_time)

        self.logger.info(
            f"Rotation avec feedback: {position_initiale:.1f}° -> {angle_cible:.1f}°"
        )

        # Boucle de correction
        corrections = []
        iteration = 0

        while iteration < max_iterations:
            if self.stop_requested:
                self.logger.info("Arrêt demandé, abandon de la correction")
                break

            correction = self._executer_iteration(
                angle_cible, vitesse, tolerance,
                max_correction_par_iteration, iteration,
                position_initiale=position_initiale,  # Pour détecter recalibration switch
                allow_large_movement=allow_large_movement  # Pour GOTO initial
            )

            if correction is None:
                break

            corrections.append(correction)
            iteration += 1
            time.sleep(0.05)  # Pause stabilisation

        # Mesure finale
        try:
            position_finale = self._lire_position_stable()
        except RuntimeError:
            position_finale = angle_cible
            self.logger.warning("Impossible de lire position finale")

        erreur_finale = self._calculer_delta_angulaire(position_finale, angle_cible)
        temps_total = time.time() - start_time
        success = abs(erreur_finale) < tolerance

        self._log_resultat_final(
            success, position_initiale, position_finale,
            erreur_finale, iteration, max_iterations, temps_total
        )

        return self._creer_resultat(
            success, position_initiale, position_finale, angle_cible,
            erreur_finale, iteration, corrections, temps_total
        )

    def rotation_relative_avec_feedback(
        self,
        delta_deg: float,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Rotation relative avec feedback via démon.

        Args:
            delta_deg: Déplacement relatif (°), positif = horaire
            **kwargs: Paramètres passés à rotation_avec_feedback()

        Returns:
            dict: Résultat de rotation_avec_feedback()
        """
        try:
            position_actuelle = self.daemon_reader.read_angle()
        except RuntimeError:
            self.logger.warning("Démon non disponible, rotation relative sans feedback")
            self.moteur.rotation(delta_deg, kwargs.get('vitesse', 0.001))
            return {
                'success': False,
                'position_initiale': 0,
                'position_finale': delta_deg,
                'position_cible': delta_deg,
                'erreur_finale': 0,
                'iterations': 0,
                'corrections': [],
                'mode': 'sans_feedback'
            }

        angle_cible = (position_actuelle + delta_deg) % 360

        self.logger.info(
            f"Rotation relative: {delta_deg:+.1f}° "
            f"({position_actuelle:.1f}° -> {angle_cible:.1f}°)"
        )

        return self.rotation_avec_feedback(angle_cible=angle_cible, **kwargs)