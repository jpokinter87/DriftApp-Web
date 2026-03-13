#!/usr/bin/env python3
"""
Motor Service - Processus dédié pour le contrôle moteur GPIO.

Ce service tourne dans un processus séparé avec son propre GIL,
garantissant un timing optimal pour les pulses GPIO sans interférence
avec l'interface web Django.

Communication:
- Reçoit commandes via /dev/shm/motor_command.json
- Publie état via /dev/shm/motor_status.json
- Lit position encodeur via /dev/shm/ems22_position.json (daemon existant)

Usage:
    sudo python3 services/motor_service.py

Date: Décembre 2025
"""

import json
import logging
import os
import signal
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config.config_loader import ConfigLoader
from core.hardware.moteur import MoteurCoupole, DaemonEncoderReader
from core.hardware.moteur_simule import MoteurSimule, set_simulated_position
from core.hardware.hardware_detector import HardwareDetector
from core.hardware.feedback_controller import FeedbackController
from core.tracking.adaptive_tracking import AdaptiveTrackingManager, TrackingMode
from core.tracking.tracker import TrackingSession
from core.observatoire import AstronomicalCalculations
from core.tracking.tracking_logger import TrackingLogger
from core.utils.angle_utils import shortest_angular_distance

# Chemins des fichiers IPC
COMMAND_FILE = Path("/dev/shm/motor_command.json")
STATUS_FILE = Path("/dev/shm/motor_status.json")
ENCODER_FILE = Path("/dev/shm/ems22_position.json")


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
        from core.hardware.moteur_simule import _simulated_position
        return {
            'angle': _simulated_position,
            'calibrated': True,
            'status': 'OK (simulation)',
            'raw': 0
        }

    def read_angle(self, timeout_ms: int = 200) -> float:
        """Retourne la position simulée."""
        from core.hardware.moteur_simule import _simulated_position
        return _simulated_position

    def read_status(self) -> dict:
        """Retourne le statut complet simulé."""
        return self.read_raw()

    def read_stable(self, num_samples: int = 3, delay_ms: int = 10,
                    stabilization_ms: int = 50) -> float:
        """Retourne la position simulée (pas de moyennage nécessaire)."""
        return self.read_angle()

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            Path(__file__).parent.parent / 'logs' / 'motor_service.log',
            mode='a'
        )
    ]
)
logger = logging.getLogger("MotorService")


class MotorService:
    """
    Service de contrôle moteur avec boucle de suivi intégrée.

    Ce service gère:
    - Les commandes GOTO manuelles
    - Les rotations relatives (jog)
    - Le suivi automatique d'objets célestes
    - Le feedback encodeur en boucle fermée
    """

    def __init__(self):
        """Initialise le service moteur."""
        self.running = False
        self.tracking_active = False
        self.tracking_session: Optional[TrackingSession] = None

        # Charger la configuration
        self.config = ConfigLoader().load()

        # Détection automatique du matériel (comme dans l'app Kivy)
        is_production, hw_info = HardwareDetector.detect_hardware()
        self.simulation_mode = not is_production

        # Afficher le résumé de détection
        logger.info(HardwareDetector.get_hardware_summary(hw_info))

        # Initialiser le moteur (réel ou simulé)
        if self.simulation_mode:
            logger.info("MODE SIMULATION ACTIVÉ (Raspberry Pi non détecté)")
            self.moteur = MoteurSimule(self.config.motor)
            self.daemon_reader = SimulatedDaemonReader()
            self.feedback_controller = self.moteur  # MoteurSimule implémente l'interface
        else:
            logger.info("MODE PRODUCTION - GPIO actif")
            self.moteur = MoteurCoupole(self.config.motor)
            self.daemon_reader = DaemonEncoderReader()
            self.feedback_controller = FeedbackController(self.moteur, self.daemon_reader)

        # Gestionnaire adaptatif
        self.adaptive_manager = AdaptiveTrackingManager(
            base_interval=self.config.tracking.intervalle_verification_sec,
            base_threshold=self.config.tracking.seuil_correction_deg,
            adaptive_config=self.config.adaptive
        )

        # État actuel
        self.current_status = {
            'status': 'idle',
            'position': 0.0,
            'target': None,
            'progress': 0,
            'mode': 'idle',
            'tracking_object': None,
            'error': None,
            'simulation': self.simulation_mode,
            'last_update': datetime.now().isoformat(),
            'tracking_logs': []  # Correction 3: Logs de suivi pour l'interface web
        }

        # Liste des logs récents (max 20)
        self.recent_tracking_logs = []
        self.max_tracking_logs = 20

        # Dernière commande traitée (pour éviter les doublons)
        self.last_command_id = None

        # Thread pour mouvement continu (simulation)
        self.continuous_thread: Optional[threading.Thread] = None
        self.continuous_stop_flag = threading.Event()

        mode_str = "SIMULATION" if self.simulation_mode else "PRODUCTION"
        logger.info(f"Motor Service initialisé en mode {mode_str}")

    def add_tracking_log(self, message: str, log_type: str = 'info'):
        """
        Ajoute un log de suivi pour l'interface web.

        Args:
            message: Message à afficher
            log_type: Type de log (info, correction, warning, error)
        """
        log_entry = {
            'time': datetime.now().isoformat(),
            'message': message,
            'type': log_type
        }
        self.recent_tracking_logs.append(log_entry)

        # Limiter le nombre de logs
        if len(self.recent_tracking_logs) > self.max_tracking_logs:
            self.recent_tracking_logs = self.recent_tracking_logs[-self.max_tracking_logs:]

        # Mettre à jour le status (10 derniers logs)
        self.current_status['tracking_logs'] = self.recent_tracking_logs[-10:]

    # =========================================================================
    # GESTION DES FICHIERS IPC
    # =========================================================================

    def read_command(self) -> Optional[Dict[str, Any]]:
        """
        Lit une commande depuis le fichier IPC.

        Returns:
            dict: Commande à exécuter ou None si aucune nouvelle commande
        """
        if not COMMAND_FILE.exists():
            return None

        try:
            text = COMMAND_FILE.read_text()
            if not text.strip():
                return None

            command = json.loads(text)

            # Vérifier si c'est une nouvelle commande
            cmd_id = command.get('id')
            if cmd_id == self.last_command_id:
                return None

            self.last_command_id = cmd_id
            return command

        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Erreur lecture commande: {e}")
            return None

    def write_status(self):
        """Écrit l'état actuel dans le fichier IPC."""
        self.current_status['last_update'] = datetime.now().isoformat()

        try:
            # Écriture atomique avec fichier temporaire
            tmp_file = STATUS_FILE.with_suffix('.tmp')
            tmp_file.write_text(json.dumps(self.current_status, indent=2))
            tmp_file.rename(STATUS_FILE)
        except IOError as e:
            logger.error(f"Erreur écriture status: {e}")

    def clear_command(self):
        """Efface le fichier de commande après traitement."""
        try:
            if COMMAND_FILE.exists():
                COMMAND_FILE.write_text('')
        except IOError:
            pass

    def read_encoder_position(self) -> Optional[float]:
        """
        Lit la position de l'encodeur depuis le daemon existant.

        Returns:
            float: Position en degrés ou None si non disponible
        """
        try:
            return self.daemon_reader.read_angle(timeout_ms=100)
        except RuntimeError:
            return None

    # =========================================================================
    # COMMANDES MOTEUR
    # =========================================================================

    def handle_goto(self, angle: float, speed: Optional[float] = None):
        """
        Exécute un GOTO vers une position absolue.

        Args:
            angle: Angle cible (0-360°)
            speed: Vitesse moteur (delay en secondes), None = config fast_track
        """
        logger.info(f"GOTO vers {angle:.1f}°")

        # Vitesse par défaut = fast_track
        if speed is None:
            fast_track = self.config.adaptive.modes.get('fast_track')
            speed = fast_track.motor_delay if fast_track else 0.00015

        self.current_status['status'] = 'moving'
        self.current_status['target'] = angle
        self.current_status['progress'] = 0
        self.write_status()

        try:
            # En mode simulation, synchroniser _simulated_position avant le goto
            if self.simulation_mode:
                current_pos = self.current_status.get('position', 0)
                set_simulated_position(current_pos)
                logger.debug(f"Sync position simulée avant goto: {current_pos:.2f}°")

            # Utiliser le feedback si disponible
            if self.daemon_reader.is_available():
                result = self.feedback_controller.rotation_avec_feedback(
                    angle_cible=angle,
                    vitesse=speed,
                    tolerance=0.5,
                    max_iterations=10,
                    max_correction_par_iteration=180.0
                )

                self.current_status['status'] = 'idle' if result['success'] else 'error'
                self.current_status['position'] = result['position_finale']
                self.current_status['progress'] = 100

                if not result['success']:
                    self.current_status['error'] = f"Erreur finale: {result['erreur_finale']:.2f}°"

                logger.info(
                    f"GOTO terminé: {result['position_initiale']:.1f}° -> "
                    f"{result['position_finale']:.1f}° ({result['iterations']} iter)"
                )
            else:
                # Sans feedback - rotation simple
                current_pos = self.current_status.get('position', 0)
                delta = shortest_angular_distance(current_pos, angle)
                self.moteur.rotation(delta, speed)

                self.current_status['status'] = 'idle'
                self.current_status['position'] = angle
                self.current_status['progress'] = 100

                logger.info(f"GOTO (sans feedback) terminé: delta={delta:.1f}°")

        except Exception as e:
            logger.error(f"Erreur GOTO: {e}")
            self.current_status['status'] = 'error'
            self.current_status['error'] = str(e)

        self.current_status['target'] = None
        self.write_status()

    def handle_jog(self, delta: float, speed: Optional[float] = None):
        """
        Exécute une rotation relative (jog).

        Args:
            delta: Déplacement relatif en degrés (+ = horaire)
            speed: Vitesse moteur (delay en secondes)
        """
        logger.info(f"JOG de {delta:+.1f}°")

        if speed is None:
            fast_track = self.config.adaptive.modes.get('fast_track')
            speed = fast_track.motor_delay if fast_track else 0.00015

        self.current_status['status'] = 'moving'
        self.write_status()

        try:
            # En mode simulation, synchroniser _simulated_position avant le jog
            # pour que le FeedbackController lise la bonne position de départ
            if self.simulation_mode:
                current_pos = self.current_status.get('position', 0)
                set_simulated_position(current_pos)
                logger.debug(f"Sync position simulée avant jog: {current_pos:.2f}°")

            if self.daemon_reader.is_available():
                result = self.feedback_controller.rotation_relative_avec_feedback(
                    delta_deg=delta,
                    vitesse=speed,
                    tolerance=0.5,
                    max_iterations=5
                )
                self.current_status['position'] = result['position_finale']
            else:
                self.moteur.rotation(delta, speed)
                current = self.current_status.get('position', 0)
                self.current_status['position'] = (current + delta) % 360

            self.current_status['status'] = 'idle'

        except Exception as e:
            logger.error(f"Erreur JOG: {e}")
            self.current_status['status'] = 'error'
            self.current_status['error'] = str(e)

        self.write_status()

    def handle_stop(self):
        """Arrête immédiatement tout mouvement."""
        logger.info("STOP demandé")

        # Arrêter le thread de mouvement continu
        self._stop_continuous_thread()

        # Arrêter le feedback en cours
        self.feedback_controller.request_stop()
        self.moteur.request_stop()

        # Arrêter le suivi si actif
        if self.tracking_active and self.tracking_session:
            self.tracking_session.stop()
            self.tracking_active = False
            self.tracking_session = None

        self.current_status['status'] = 'idle'
        self.current_status['tracking_object'] = None
        self.write_status()

    def handle_test_speed(self, angle: float, motor_delay: float) -> dict:
        """
        Teste une vitesse spécifique et retourne les métriques.
        
        COMMANDE TEMPORAIRE pour calibration de la vitesse maximale.
        
        Args:
            angle: Angle de rotation en degrés (positif ou négatif)
            motor_delay: Délai entre les pas en secondes
            
        Returns:
            dict avec duration_sec, vitesse_deg_min, success
        """
        import time as time_module
        
        logger.info(f"TEST_SPEED: angle={angle}°, delay={motor_delay*1000:.3f}ms")
        
        try:
            # Mettre à jour le statut
            self.current_status['status'] = 'moving'
            self.current_status['target'] = None
            self.write_status()
            
            # Clear stop request pour permettre le mouvement
            self.moteur.clear_stop_request()
            
            # Effectuer la rotation avec mesure du temps
            t_start = time_module.perf_counter()
            self.moteur.rotation(angle, vitesse=motor_delay)
            duration = time_module.perf_counter() - t_start
            
            # Calculer la vitesse effective
            vitesse_deg_min = abs(angle) / duration * 60 if duration > 0 else 0
            
            # Mettre à jour la position depuis l'encodeur
            if self.daemon_reader and self.daemon_reader.is_available():
                pos = self.daemon_reader.read_angle()
                self.current_status['position'] = pos
            
            self.current_status['status'] = 'idle'
            
            result = {
                'success': True,
                'angle': angle,
                'motor_delay_ms': motor_delay * 1000,
                'duration_sec': round(duration, 3),
                'vitesse_deg_min': round(vitesse_deg_min, 1)
            }
            
            # Stocker le résultat dans le status pour que le client puisse le lire
            self.current_status['last_test_result'] = result
            self.write_status()
            
            logger.info(f"TEST_SPEED terminé: {duration:.2f}s, {vitesse_deg_min:.1f}°/min")
            
            return result
            
        except Exception as e:
            logger.error(f"TEST_SPEED erreur: {e}")
            self.current_status['status'] = 'error'
            self.current_status['error'] = str(e)
            self.current_status['last_test_result'] = {'success': False, 'error': str(e)}
            self.write_status()
            return {'success': False, 'error': str(e)}

    def handle_continuous(self, direction: str):
        """
        Démarre un mouvement continu dans une direction.

        Args:
            direction: 'cw' pour horaire, 'ccw' pour anti-horaire
        """
        logger.info(f"Mouvement continu {direction.upper()}")

        # Arrêter tout mouvement/suivi en cours
        if self.tracking_active:
            self.handle_stop()

        # Arrêter tout mouvement continu précédent
        self._stop_continuous_thread()

        self.current_status['status'] = 'moving'
        self.current_status['target'] = None  # Pas de cible fixe
        self.write_status()

        # En mode simulation, synchroniser _simulated_position
        if self.simulation_mode:
            current_pos = self.current_status.get('position', 0)
            set_simulated_position(current_pos)

        # Démarrer le thread de mouvement continu
        self.continuous_stop_flag.clear()
        self.continuous_thread = threading.Thread(
            target=self._continuous_movement_loop,
            args=(direction,),
            daemon=True
        )
        self.continuous_thread.start()

    def _stop_continuous_thread(self):
        """Arrête le thread de mouvement continu s'il est actif."""
        if self.continuous_thread and self.continuous_thread.is_alive():
            # Signaler l'arrêt au thread ET au moteur
            self.continuous_stop_flag.set()
            self.moteur.request_stop()

            # Attendre que le thread se termine
            self.continuous_thread.join(timeout=2.0)

            # Si le thread ne s'est pas terminé, forcer l'arrêt
            if self.continuous_thread.is_alive():
                logger.warning("Thread continu n'a pas répondu, forçage arrêt moteur")
                self.moteur.request_stop()

            self.continuous_thread = None

    def _continuous_movement_loop(self, direction: str):
        """
        Boucle de mouvement continu exécutée dans un thread.

        En mode simulation: incrémente la position de 1° toutes les 100ms.
        En mode production: fait des pas moteur réels.

        AMÉLIORATION: Propage stop_requested au moteur pour arrêt réactif.
        """
        delta_per_step = 1.0 if direction == 'cw' else -1.0
        step_interval = 0.1  # 100ms entre chaque incrément (= 10°/sec en simulation)

        logger.debug(f"Thread mouvement continu démarré: {direction}")

        while not self.continuous_stop_flag.is_set():
            try:
                # Propager le stop_flag au moteur pour arrêt réactif pendant rotation
                if self.continuous_stop_flag.is_set():
                    self.moteur.request_stop()
                    break

                if self.simulation_mode:
                    # Mode simulation: incrémenter la position globale
                    from core.hardware.moteur_simule import get_simulated_position
                    current = get_simulated_position()
                    new_pos = (current + delta_per_step) % 360
                    set_simulated_position(new_pos)
                    self.current_status['position'] = new_pos
                else:
                    # Mode production: faire un petit déplacement réel
                    # Clear stop avant chaque rotation pour permettre le mouvement
                    self.moteur.clear_stop_request()
                    # Utiliser la vitesse FAST_TRACK pour les mouvements manuels rapides
                    fast_track = self.config.adaptive.modes.get('fast_track')
                    speed = fast_track.motor_delay if fast_track else 0.00015
                    self.moteur.rotation(delta_per_step, vitesse=speed)

                    # Vérifier arrêt après rotation
                    if self.continuous_stop_flag.is_set():
                        break

                    pos = self.read_encoder_position()
                    if pos is not None:
                        self.current_status['position'] = pos

                self.write_status()
                time.sleep(step_interval)

            except Exception as e:
                logger.error(f"Erreur dans boucle continue: {e}")
                break

        # Fin du mouvement - s'assurer que le moteur est arrêté
        self.moteur.request_stop()
        self.current_status['status'] = 'idle'
        self.write_status()
        logger.debug("Thread mouvement continu terminé")

    # =========================================================================
    # SUIVI D'OBJETS
    # =========================================================================

    def handle_tracking_start(self, object_name: str):
        """
        Démarre le suivi d'un objet céleste.

        Args:
            object_name: Nom de l'objet (M31, Vega, Jupiter, etc.)
        """
        logger.info(f"Démarrage suivi de {object_name}")

        try:
            # Créer les calculateurs (mêmes paramètres que le GUI de référence)
            calc = AstronomicalCalculations(
                self.config.site.latitude,
                self.config.site.longitude,
                self.config.site.tz_offset
            )
            tracking_logger = TrackingLogger()

            # Créer la session de suivi
            self.tracking_session = TrackingSession(
                moteur=self.moteur,
                calc=calc,
                logger=tracking_logger,
                seuil=self.config.tracking.seuil_correction_deg,
                intervalle=self.config.tracking.intervalle_verification_sec,
                abaque_file=self.config.tracking.abaque_file,
                adaptive_config=self.config.adaptive,
                motor_config=self.config.motor,
                encoder_config=self.config.encoder
            )

            # Démarrer le suivi
            success, message = self.tracking_session.start(object_name)

            if success:
                self.tracking_active = True
                self.current_status['status'] = 'tracking'
                self.current_status['tracking_object'] = object_name
                self.current_status['mode'] = 'normal'
                logger.info(f"Suivi démarré: {message}")
                # Correction 3: Log de démarrage pour l'interface web
                self.add_tracking_log(f"Suivi de {object_name} démarré", 'tracking')
            else:
                self.current_status['status'] = 'error'
                self.current_status['error'] = message
                logger.error(f"Échec démarrage suivi: {message}")

        except Exception as e:
            logger.error(f"Erreur démarrage suivi: {e}")
            self.current_status['status'] = 'error'
            self.current_status['error'] = str(e)

        self.write_status()

    def handle_tracking_stop(self):
        """Arrête le suivi en cours."""
        logger.info("Arrêt du suivi")

        if self.tracking_session:
            # En mode simulation, synchroniser _simulated_position avec la position finale du tracking
            if self.simulation_mode:
                status = self.tracking_session.get_status()
                final_pos = status.get('position_relative', 0) % 360
                set_simulated_position(final_pos)
                self.current_status['position'] = final_pos
                logger.debug(f"Sync position simulée après tracking: {final_pos:.2f}°")

            self.tracking_session.stop()
            self.tracking_session = None

        self.tracking_active = False
        self.current_status['status'] = 'idle'
        self.current_status['tracking_object'] = None
        self.current_status['mode'] = 'idle'
        self.write_status()

    def update_tracking(self):
        """
        Met à jour le suivi (appelé périodiquement).

        Cette méthode vérifie si une correction est nécessaire
        et l'applique le cas échéant.
        """
        if not self.tracking_active or not self.tracking_session:
            return

        try:
            # Vérifier et corriger si nécessaire
            correction_applied, message = self.tracking_session.check_and_correct()

            if correction_applied:
                logger.info(message)
                # Correction 3: Ajouter le log pour l'interface web
                # Utiliser directement le message de check_and_correct() qui contient les vraies valeurs
                # Format: "[HH:MM:SS] Correction: X.XX° | Az=... | AzCoupole=... | Mode: ..."
                # On retire le timestamp du début car le frontend l'ajoute
                log_msg = message
                if message.startswith('[') and '] ' in message:
                    log_msg = message.split('] ', 1)[1]  # Retirer "[HH:MM:SS] "
                self.add_tracking_log(log_msg, 'correction')

            # Mettre à jour le status
            status = self.tracking_session.get_status()
            if status.get('running'):
                self.current_status['position'] = status.get('position_relative', 0)
                self.current_status['mode'] = status.get('adaptive_mode', 'normal')

                # Infos supplémentaires pour l'interface
                self.current_status['tracking_info'] = {
                    'azimut': status.get('obj_az_raw', 0),
                    'altitude': status.get('obj_alt', 0),
                    'position_cible': status.get('position_cible', 0),
                    'remaining_seconds': status.get('remaining_seconds', 0),
                    'interval_sec': status.get('adaptive_interval', 60),  # Intervalle du mode actuel
                    'total_corrections': status.get('total_corrections', 0),
                    'total_correction_degrees': status.get('total_movement', 0.0),
                    'mode_icon': status.get('mode_icon', '')
                }
            else:
                # Le suivi s'est arrêté (erreur ou fin)
                self.tracking_active = False
                self.current_status['status'] = 'idle'
                self.current_status['tracking_object'] = None

        except Exception as e:
            logger.error(f"Erreur mise à jour suivi: {e}")

    # =========================================================================
    # TRAITEMENT DES COMMANDES
    # =========================================================================

    def process_command(self, command: Dict[str, Any]):
        """
        Traite une commande reçue.

        Args:
            command: Dictionnaire de commande avec 'type' et paramètres
        """
        cmd_type = command.get('command', command.get('type'))

        if not cmd_type:
            logger.warning(f"Commande invalide: {command}")
            return

        logger.info(f"Traitement commande: {cmd_type}")

        if cmd_type == 'goto':
            angle = command.get('angle', 0)
            speed = command.get('speed')
            self.handle_goto(angle, speed)

        elif cmd_type == 'jog':
            delta = command.get('delta', 0)
            speed = command.get('speed')
            self.handle_jog(delta, speed)

        elif cmd_type == 'stop':
            self.handle_stop()

        elif cmd_type == 'continuous':
            direction = command.get('direction', 'cw')
            self.handle_continuous(direction)

        elif cmd_type == 'tracking_start':
            object_name = command.get('object', command.get('name'))
            if object_name:
                self.handle_tracking_start(object_name)
            else:
                logger.warning("tracking_start sans nom d'objet")

        elif cmd_type == 'tracking_stop':
            self.handle_tracking_stop()

        elif cmd_type == 'test_speed':
            # Commande temporaire pour calibration vitesse maximale
            angle = command.get('angle', 5.0)
            motor_delay = command.get('motor_delay', 0.001)
            self.handle_test_speed(angle, motor_delay)

        elif cmd_type == 'status':
            # Commande de statut - juste mettre à jour
            pass

        else:
            logger.warning(f"Commande inconnue: {cmd_type}")

        # Effacer la commande après traitement
        self.clear_command()

    # =========================================================================
    # BOUCLE PRINCIPALE
    # =========================================================================

    def run(self):
        """Boucle principale du service."""
        self.running = True
        logger.info("Motor Service démarré - En attente de commandes...")

        # Lire la position initiale
        pos = self.read_encoder_position()
        if pos is not None:
            self.current_status['position'] = pos
            logger.info(f"Position initiale: {pos:.1f}°")

        self.write_status()

        last_tracking_update = time.time()
        tracking_interval = 1.0  # Vérification suivi chaque seconde

        while self.running:
            try:
                # Lire et traiter les commandes
                command = self.read_command()
                if command:
                    self.process_command(command)

                # Mettre à jour le suivi si actif
                now = time.time()
                if self.tracking_active and (now - last_tracking_update) >= tracking_interval:
                    self.update_tracking()
                    last_tracking_update = now
                    self.write_status()

                # Mettre à jour la position depuis l'encodeur
                pos = self.read_encoder_position()
                if pos is not None and not self.tracking_active:
                    self.current_status['position'] = pos

                # Pause courte pour ne pas saturer le CPU
                time.sleep(0.05)  # 50ms = 20Hz de polling

            except KeyboardInterrupt:
                logger.info("Interruption clavier - Arrêt du service")
                break
            except Exception as e:
                logger.error(f"Erreur boucle principale: {e}")
                time.sleep(1)

        self.cleanup()

    def cleanup(self):
        """Nettoie les ressources à l'arrêt."""
        logger.info("Nettoyage des ressources...")

        # Arrêter le suivi
        if self.tracking_session:
            self.tracking_session.stop()

        # Nettoyer le moteur
        if self.moteur:
            self.moteur.nettoyer()

        # Mettre à jour le status final
        self.current_status['status'] = 'stopped'
        self.write_status()

        logger.info("Motor Service arrêté proprement")

    def signal_handler(self, signum, frame):
        """Gestionnaire de signaux pour arrêt propre."""
        logger.info(f"Signal {signum} reçu - Arrêt en cours...")
        self.running = False


def main():
    """Point d'entrée principal."""
    # Créer le répertoire de logs si nécessaire
    logs_dir = Path(__file__).parent.parent / 'logs'
    logs_dir.mkdir(exist_ok=True)

    # Détection automatique du matériel
    is_production, _ = HardwareDetector.detect_hardware()

    # En production (Raspberry Pi), vérifier les permissions (nécessite sudo pour GPIO)
    if is_production and os.geteuid() != 0:
        print("ERREUR: Ce service nécessite les privilèges root (sudo) sur Raspberry Pi")
        print("Usage: sudo python3 services/motor_service.py")
        sys.exit(1)

    # Créer et lancer le service
    service = MotorService()

    # Installer les gestionnaires de signaux
    signal.signal(signal.SIGTERM, service.signal_handler)
    signal.signal(signal.SIGINT, service.signal_handler)

    # Lancer la boucle principale
    service.run()


if __name__ == '__main__':
    main()
