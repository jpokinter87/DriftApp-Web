"""
Command Handlers - Gestionnaires de commandes moteur.

Ce module contient les handlers pour les différentes commandes:
- GOTO: Déplacement vers une position absolue
- JOG: Déplacement relatif (boutons manuels)
- STOP: Arrêt d'urgence
- CONTINUOUS: Mouvement continu
- TRACKING: Suivi d'objets célestes

Date: Décembre 2025
Version: 4.4 - Optimisation GOTO/JOG sans feedback pour fluidité
"""

import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Dict, Any

from core.hardware.moteur_simule import set_simulated_position, get_simulated_position
from core.tracking.tracker import TrackingSession
from core.tracking.tracking_logger import TrackingLogger
from core.observatoire import AstronomicalCalculations
from core.utils.angle_utils import shortest_angular_distance

logger = logging.getLogger("CommandHandlers")


class GotoHandler:
    """Handler pour les commandes GOTO (déplacement absolu)."""

    def __init__(self, moteur, daemon_reader, feedback_controller,
                 config, simulation_mode: bool, status_callback: Callable):
        """
        Args:
            moteur: Instance du moteur (réel ou simulé)
            daemon_reader: Lecteur de position encodeur
            feedback_controller: Contrôleur de feedback
            config: Configuration chargée
            simulation_mode: True si en mode simulation
            status_callback: Callback pour mettre à jour le statut
        """
        self.moteur = moteur
        self.daemon_reader = daemon_reader
        self.feedback_controller = feedback_controller
        self.config = config
        self.simulation_mode = simulation_mode
        self.status_callback = status_callback

    def _get_goto_speed(self, speed: Optional[float] = None) -> float:
        """Retourne la vitesse optimale pour les GOTO."""
        if speed is not None:
            return speed
        continuous = self.config.adaptive.modes.get('continuous')
        if continuous:
            return continuous.motor_delay
        return 0.00015

    def execute(self, angle: float, current_status: Dict[str, Any],
                speed: Optional[float] = None) -> Dict[str, Any]:
        """
        Exécute un GOTO vers une position absolue.

        OPTIMISATION v4.4:
        - Grands déplacements (> 3°): Rotation directe FLUIDE, puis correction finale
        - Petits déplacements (≤ 3°): Feedback classique pour précision
        """
        speed = self._get_goto_speed(speed)
        logger.info(f"GOTO vers {angle:.1f}° (vitesse={speed*1000:.3f}ms)")

        current_status['status'] = 'moving'
        current_status['target'] = angle
        current_status['progress'] = 0
        self.status_callback(current_status)

        try:
            # En mode simulation, synchroniser _simulated_position
            if self.simulation_mode:
                current_pos = current_status.get('position', 0)
                set_simulated_position(current_pos)

            # Lire position actuelle
            if self.daemon_reader.is_available():
                current_pos = self.daemon_reader.read_angle(timeout_ms=200)
            else:
                current_pos = current_status.get('position', 0)

            delta = shortest_angular_distance(current_pos, angle)

            # Seuil depuis config centralisée (feedback_min_deg)
            seuil_feedback = self.config.thresholds.feedback_min_deg

            if abs(delta) > seuil_feedback:
                # GRAND DÉPLACEMENT: Rotation directe + correction finale
                current_status = self._execute_large_goto(
                    angle, delta, speed, current_status
                )
            else:
                # PETIT DÉPLACEMENT: Feedback classique
                current_status = self._execute_small_goto(
                    angle, delta, speed, current_status
                )

        except Exception as e:
            logger.error(f"Erreur GOTO: {e}")
            current_status['status'] = 'error'
            current_status['error'] = str(e)
            current_status['error_timestamp'] = time.time()

        current_status['target'] = None
        self.status_callback(current_status)
        return current_status

    def _execute_large_goto(self, angle: float, delta: float, speed: float,
                            status: Dict[str, Any]) -> Dict[str, Any]:
        """Exécute un grand déplacement (> 3°)."""
        logger.info(f"GOTO optimisé: rotation directe de {delta:+.1f}°")

        # 1. Rotation directe (fluide)
        self.moteur.clear_stop_request()
        self.moteur.rotation(delta, vitesse=speed)

        # 2. Correction finale avec feedback
        tolerance = self.config.thresholds.default_tolerance_deg
        if self.daemon_reader.is_available():
            pos_apres_rotation = self.daemon_reader.read_angle(timeout_ms=200)
            erreur = shortest_angular_distance(pos_apres_rotation, angle)

            if abs(erreur) > tolerance:
                logger.info(f"Correction finale: erreur={erreur:+.2f}°")
                result = self.feedback_controller.rotation_avec_feedback(
                    angle_cible=angle,
                    vitesse=speed,
                    tolerance=tolerance,
                    max_iterations=3
                )
                status['position'] = result['position_finale']

                if result['success']:
                    logger.info(f"GOTO terminé: erreur finale={result['erreur_finale']:.2f}°")
                else:
                    logger.warning(f"GOTO: correction imparfaite, erreur={result['erreur_finale']:.2f}°")
            else:
                logger.info(f"GOTO précis du premier coup: erreur={erreur:+.2f}°")
                status['position'] = pos_apres_rotation
        else:
            status['position'] = angle

        status['status'] = 'idle'
        status['progress'] = 100
        return status

    def _execute_small_goto(self, angle: float, delta: float, speed: float,
                            status: Dict[str, Any]) -> Dict[str, Any]:
        """Exécute un petit déplacement (≤ seuil feedback)."""
        tolerance = self.config.thresholds.default_tolerance_deg
        if self.daemon_reader.is_available():
            result = self.feedback_controller.rotation_avec_feedback(
                angle_cible=angle,
                vitesse=speed,
                tolerance=tolerance,
                max_iterations=10,
                max_correction_par_iteration=180.0
            )

            status['status'] = 'idle' if result['success'] else 'error'
            status['position'] = result['position_finale']
            status['progress'] = 100

            if not result['success']:
                status['error'] = f"Erreur finale: {result['erreur_finale']:.2f}°"

            logger.info(
                f"GOTO terminé: {result['position_initiale']:.1f}° -> "
                f"{result['position_finale']:.1f}° ({result['iterations']} iter)"
            )
        else:
            self.moteur.rotation(delta, speed)
            status['status'] = 'idle'
            status['position'] = angle
            status['progress'] = 100
            logger.info(f"GOTO (sans feedback) terminé: delta={delta:.1f}°")

        return status


class JogHandler:
    """Handler pour les commandes JOG (déplacement relatif)."""

    def __init__(self, moteur, daemon_reader, config,
                 simulation_mode: bool, status_callback: Callable):
        self.moteur = moteur
        self.daemon_reader = daemon_reader
        self.config = config
        self.simulation_mode = simulation_mode
        self.status_callback = status_callback

    def _get_jog_speed(self, speed: Optional[float] = None) -> float:
        """Retourne la vitesse optimale pour les JOG."""
        if speed is not None:
            return speed
        continuous = self.config.adaptive.modes.get('continuous')
        if continuous:
            return continuous.motor_delay
        return 0.00015

    def execute(self, delta: float, current_status: Dict[str, Any],
                speed: Optional[float] = None) -> Dict[str, Any]:
        """
        Exécute une rotation relative (jog).

        OPTIMISATION v4.4: Rotation directe SANS feedback (fluidité maximale).
        """
        logger.info(f"JOG de {delta:+.1f}° (sans feedback)")
        speed = self._get_jog_speed(speed)

        current_status['status'] = 'moving'
        self.status_callback(current_status)

        try:
            if self.simulation_mode:
                current_pos = current_status.get('position', 0)
                set_simulated_position(current_pos)

            # Rotation directe (fluide, sans feedback)
            self.moteur.clear_stop_request()
            self.moteur.rotation(delta, vitesse=speed)

            # Lire la position réelle après rotation
            if self.daemon_reader.is_available():
                pos_finale = self.daemon_reader.read_angle(timeout_ms=200)
                current_status['position'] = pos_finale
            else:
                current = current_status.get('position', 0)
                current_status['position'] = (current + delta) % 360

            current_status['status'] = 'idle'
            logger.info(f"JOG terminé: position={current_status['position']:.1f}°")

        except Exception as e:
            logger.error(f"Erreur JOG: {e}")
            current_status['status'] = 'error'
            current_status['error'] = str(e)
            current_status['error_timestamp'] = time.time()

        self.status_callback(current_status)
        return current_status


class ContinuousHandler:
    """Handler pour les mouvements continus."""

    def __init__(self, moteur, daemon_reader, config,
                 simulation_mode: bool, status_callback: Callable):
        self.moteur = moteur
        self.daemon_reader = daemon_reader
        self.config = config
        self.simulation_mode = simulation_mode
        self.status_callback = status_callback
        self.thread: Optional[threading.Thread] = None
        self.stop_flag = threading.Event()

    def _get_continuous_speed(self) -> float:
        """Retourne la vitesse pour les mouvements continus."""
        continuous = self.config.adaptive.modes.get('continuous')
        if continuous:
            return continuous.motor_delay
        return 0.00015

    def start(self, direction: str, current_status: Dict[str, Any]):
        """Démarre un mouvement continu dans une direction."""
        logger.info(f"Mouvement continu {direction.upper()}")

        self.stop()  # Arrêter tout mouvement précédent

        current_status['status'] = 'moving'
        current_status['target'] = None
        self.status_callback(current_status)

        if self.simulation_mode:
            current_pos = current_status.get('position', 0)
            set_simulated_position(current_pos)

        self.stop_flag.clear()
        self.thread = threading.Thread(
            target=self._movement_loop,
            args=(direction, current_status),
            daemon=True
        )
        self.thread.start()

    def stop(self):
        """Arrête le mouvement continu."""
        if self.thread and self.thread.is_alive():
            self.stop_flag.set()
            self.moteur.request_stop()
            self.thread.join(timeout=2.0)

            if self.thread.is_alive():
                logger.warning("Thread continu n'a pas répondu, forçage arrêt moteur")
                self.moteur.request_stop()

            self.thread = None

    def _movement_loop(self, direction: str, current_status: Dict[str, Any]):
        """Boucle de mouvement continu."""
        delta_per_step = 1.0 if direction == 'cw' else -1.0
        step_interval = 0.1
        speed = self._get_continuous_speed()

        logger.debug(f"Thread mouvement continu démarré: {direction}")

        while not self.stop_flag.is_set():
            try:
                if self.stop_flag.is_set():
                    self.moteur.request_stop()
                    break

                if self.simulation_mode:
                    current = get_simulated_position()
                    new_pos = (current + delta_per_step) % 360
                    set_simulated_position(new_pos)
                    current_status['position'] = new_pos
                else:
                    self.moteur.clear_stop_request()
                    self.moteur.rotation(delta_per_step, vitesse=speed)

                    if self.stop_flag.is_set():
                        break

                    pos = self.daemon_reader.read_angle(timeout_ms=100)
                    if pos is not None:
                        current_status['position'] = pos

                self.status_callback(current_status)
                time.sleep(step_interval)

            except Exception as e:
                logger.error(f"Erreur mouvement continu: {e}")
                break

        logger.debug("Thread mouvement continu terminé")
        current_status['status'] = 'idle'
        self.status_callback(current_status)


class TrackingHandler:
    """Handler pour le suivi d'objets célestes."""

    def __init__(self, feedback_controller, config,
                 simulation_mode: bool, status_callback: Callable,
                 log_callback: Callable):
        self.feedback_controller = feedback_controller
        self.config = config
        self.simulation_mode = simulation_mode
        self.status_callback = status_callback
        self.log_callback = log_callback
        self.session: Optional[TrackingSession] = None
        self.active = False

    def start(self, object_name: str, current_status: Dict[str, Any]):
        """Démarre le suivi d'un objet céleste."""
        logger.info(f"Démarrage suivi de: {object_name}")

        if self.active:
            self.stop(current_status)

        # IMPORTANT: Signaler immédiatement que le tracking est en cours d'initialisation
        # Cela permet à l'UI d'afficher un message pendant le GOTO initial
        current_status['status'] = 'initializing'
        current_status['tracking_object'] = object_name
        current_status['tracking_pending'] = True
        current_status['goto_info'] = None  # Sera rempli par le callback
        self.status_callback(current_status)
        self.log_callback(f"Initialisation du suivi de {object_name}...", 'info')

        # Callback pour recevoir les infos du GOTO initial
        def on_goto_info(goto_info: Dict[str, Any]):
            """Callback appelé avec les infos du GOTO initial."""
            current_status['goto_info'] = goto_info
            self.status_callback(current_status)
            self.log_callback(
                f"GOTO: {goto_info['current_position']:.1f}° → "
                f"{goto_info['target_position']:.1f}° (delta={goto_info['delta']:+.1f}°)",
                'info'
            )

        try:
            calc = AstronomicalCalculations(
                latitude=self.config.site.latitude,
                longitude=self.config.site.longitude,
                tz_offset=self.config.site.tz_offset
            )

            tracking_logger = TrackingLogger()

            self.session = TrackingSession(
                moteur=self.feedback_controller,
                calc=calc,
                logger=tracking_logger,
                seuil=self.config.tracking.seuil_correction_deg,
                intervalle=self.config.tracking.intervalle_verification_sec,
                abaque_file=str(Path(__file__).parent.parent / self.config.tracking.abaque_file),
                adaptive_config=self.config.adaptive,
                motor_config=self.config.motor,
                encoder_config=self.config.encoder,
                goto_callback=on_goto_info
            )

            success = self.session.start(object_name)

            if success:
                self.active = True
                current_status['status'] = 'tracking'
                current_status['tracking_object'] = object_name
                current_status['tracking_pending'] = False  # GOTO initial terminé
                current_status['goto_info'] = None  # GOTO terminé
                current_status['mode'] = 'normal'

                status = self.session.get_status()
                encoder_offset = status.get('encoder_offset', 0)
                logger.info(f"Suivi démarré - Offset encodeur: {encoder_offset:.2f}°")

                self.log_callback(f"Suivi actif: {object_name}", 'success')
            else:
                logger.error(f"Échec démarrage suivi de {object_name}")
                current_status['status'] = 'idle'
                current_status['tracking_object'] = None
                current_status['tracking_pending'] = False
                current_status['goto_info'] = None
                current_status['error'] = "Échec démarrage suivi"

        except Exception as e:
            logger.error(f"Erreur démarrage suivi: {e}")
            current_status['status'] = 'error'
            current_status['tracking_object'] = None
            current_status['tracking_pending'] = False
            current_status['goto_info'] = None
            current_status['error'] = str(e)

        self.status_callback(current_status)

    def stop(self, current_status: Dict[str, Any]):
        """Arrête le suivi en cours."""
        logger.info("Arrêt du suivi")

        if self.session:
            if self.simulation_mode:
                status = self.session.get_status()
                final_pos = status.get('position_relative', 0) % 360
                set_simulated_position(final_pos)
                current_status['position'] = final_pos

            self.session.stop()
            self.session = None

        self.active = False
        current_status['status'] = 'idle'
        current_status['tracking_object'] = None
        current_status['tracking_pending'] = False
        current_status['goto_info'] = None
        current_status['mode'] = 'idle'
        self.status_callback(current_status)

    def update(self, current_status: Dict[str, Any]):
        """Met à jour le suivi (appelé périodiquement)."""
        if not self.active or not self.session:
            return

        try:
            correction_applied, message = self.session.check_and_correct()

            if correction_applied:
                logger.info(message)
                log_msg = message
                if message.startswith('[') and '] ' in message:
                    log_msg = message.split('] ', 1)[1]
                self.log_callback(log_msg, 'correction')

            status = self.session.get_status()
            if status.get('running'):
                current_status['position'] = status.get('position_relative', 0)
                current_status['mode'] = status.get('adaptive_mode', 'normal')

                current_status['tracking_info'] = {
                    'azimut': status.get('obj_az_raw', 0),
                    'altitude': status.get('obj_alt', 0),
                    'position_cible': status.get('position_cible', 0),
                    'remaining_seconds': status.get('remaining_seconds', 0),
                    'interval_sec': status.get('adaptive_interval', 60),
                    'total_corrections': status.get('total_corrections', 0),
                    'total_correction_degrees': status.get('total_movement', 0.0),
                    'mode_icon': status.get('mode_icon', '')
                }
            else:
                self.active = False
                current_status['status'] = 'idle'
                current_status['tracking_object'] = None

        except Exception as e:
            logger.error(f"Erreur mise à jour suivi: {e}")

    @property
    def is_active(self) -> bool:
        """Retourne True si le suivi est actif."""
        return self.active
