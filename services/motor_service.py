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
Version: 4.4 - Refactoring en modules
"""

from collections import deque
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config.config_loader import ConfigLoader
from core.hardware.moteur import MoteurCoupole, DaemonEncoderReader, get_daemon_reader, set_daemon_reader
from core.hardware.moteur_simule import MoteurSimule
from core.hardware.hardware_detector import HardwareDetector
from core.hardware.feedback_controller import FeedbackController
from core.tracking.adaptive_tracking import AdaptiveTrackingManager

from services.ipc_manager import IpcManager
from services.simulation import SimulatedDaemonReader
from services.command_handlers import (
    GotoHandler, JogHandler, ContinuousHandler, TrackingHandler
)

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
logger = logging.getLogger(__name__)


class MotorService:
    """
    Service de contrôle moteur avec boucle de suivi intégrée.

    Ce service gère:
    - Les commandes GOTO manuelles
    - Les rotations relatives (jog)
    - Le suivi automatique d'objets célestes
    - Le feedback encodeur en boucle fermée
    """

    # Durée après laquelle un état 'error' est automatiquement remis à 'idle'
    ERROR_RECOVERY_TIMEOUT = 10.0  # secondes

    def __init__(self):
        """Initialise le service moteur."""
        self.running = False

        # Charger la configuration
        self.config = ConfigLoader().load()

        # Détection automatique du matériel
        is_production, hw_info = HardwareDetector.detect_hardware()
        self.simulation_mode = not is_production

        logger.info(HardwareDetector.get_hardware_summary(hw_info))

        # Initialiser le matériel
        self._init_hardware()

        # Initialiser les gestionnaires
        self._init_managers()

        # Initialiser les handlers de commandes
        self._init_handlers()

        # État actuel
        self.current_status = self._create_initial_status()

        # Logs de suivi pour l'interface web (deque avec taille max automatique)
        self.recent_tracking_logs = deque(maxlen=20)

        mode_str = "SIMULATION" if self.simulation_mode else "PRODUCTION"
        logger.info(f"Motor Service initialisé en mode {mode_str}")

    def _init_hardware(self):
        """Initialise le matériel (moteur et encodeur)."""
        if self.simulation_mode:
            logger.info("MODE SIMULATION ACTIVÉ")
            self.moteur = MoteurSimule(self.config.motor)
            # Injecter le lecteur simulé comme instance globale
            self.daemon_reader = SimulatedDaemonReader()
            set_daemon_reader(self.daemon_reader)
            self.feedback_controller = self.moteur
        else:
            logger.info("MODE PRODUCTION - GPIO actif")
            self.moteur = MoteurCoupole(self.config.motor)
            # Réutiliser l'instance globale du lecteur daemon
            self.daemon_reader = get_daemon_reader()
            self.feedback_controller = FeedbackController(
                self.moteur, self.daemon_reader,
                protection_threshold=self.config.thresholds.feedback_protection_deg
            )

    def _init_managers(self):
        """Initialise les gestionnaires."""
        self.ipc = IpcManager()
        self.adaptive_manager = AdaptiveTrackingManager(
            base_interval=self.config.tracking.intervalle_verification_sec,
            base_threshold=self.config.tracking.seuil_correction_deg,
            adaptive_config=self.config.adaptive
        )

    def _init_handlers(self):
        """Initialise les handlers de commandes."""
        self.goto_handler = GotoHandler(
            self.moteur, self.daemon_reader, self.feedback_controller,
            self.config, self.simulation_mode, self._write_status
        )
        self.jog_handler = JogHandler(
            self.moteur, self.daemon_reader, self.config,
            self.simulation_mode, self._write_status
        )
        self.continuous_handler = ContinuousHandler(
            self.moteur, self.daemon_reader, self.config,
            self.simulation_mode, self._write_status
        )
        self.tracking_handler = TrackingHandler(
            self.feedback_controller, self.config,
            self.simulation_mode, self._write_status, self._add_tracking_log
        )

    def _create_initial_status(self) -> Dict[str, Any]:
        """Crée l'état initial."""
        return {
            'status': 'idle',
            'position': 0.0,
            'target': None,
            'progress': 0,
            'mode': 'idle',
            'tracking_object': None,
            'error': None,
            'simulation': self.simulation_mode,
            'last_update': datetime.now().isoformat(),
            'tracking_logs': []
        }

    def _write_status(self, status: Optional[Dict[str, Any]] = None):
        """Écrit l'état via IPC."""
        if status is None:
            status = self.current_status
        self.ipc.write_status(status)

    def _add_tracking_log(self, message: str, log_type: str = 'info'):
        """Ajoute un log de suivi pour l'interface web."""
        log_entry = {
            'time': datetime.now().isoformat(),
            'message': message,
            'type': log_type
        }
        self.recent_tracking_logs.append(log_entry)
        # deque avec maxlen gère automatiquement la taille
        self.current_status['tracking_logs'] = list(self.recent_tracking_logs)[-10:]

    def read_encoder_position(self) -> Optional[float]:
        """Lit la position de l'encodeur."""
        try:
            return self.daemon_reader.read_angle(timeout_ms=100)
        except RuntimeError:
            return None

    def _check_error_recovery(self):
        """
        Vérifie si un état 'error' doit être remis à 'idle'.

        Si le statut est 'error' depuis plus de ERROR_RECOVERY_TIMEOUT secondes,
        remet automatiquement le statut à 'idle' pour permettre de nouvelles commandes.
        """
        if self.current_status.get('status') != 'error':
            return

        error_timestamp = self.current_status.get('error_timestamp')
        if error_timestamp is None:
            return

        elapsed = time.time() - error_timestamp
        if elapsed > self.ERROR_RECOVERY_TIMEOUT:
            logger.info(
                f"Recovery automatique après erreur "
                f"({elapsed:.1f}s > {self.ERROR_RECOVERY_TIMEOUT}s)"
            )
            self.current_status['status'] = 'idle'
            self.current_status['error'] = None
            self.current_status['error_timestamp'] = None
            self._write_status()

    # =========================================================================
    # COMMANDES
    # =========================================================================

    def handle_stop(self):
        """Arrête immédiatement tout mouvement."""
        logger.info("STOP demandé")

        self.continuous_handler.stop()
        self.feedback_controller.request_stop()
        self.moteur.request_stop()

        if self.tracking_handler.is_active:
            self.tracking_handler.stop(self.current_status)

        self.current_status['status'] = 'idle'
        self.current_status['tracking_object'] = None
        self._write_status()

    def process_command(self, command: Dict[str, Any]):
        """Traite une commande reçue."""
        cmd_type = command.get('command', command.get('type'))

        if not cmd_type:
            logger.warning(f"Commande invalide: {command}")
            return

        logger.info(f"Traitement commande: {cmd_type}")

        if cmd_type == 'goto':
            angle = command.get('angle', 0)
            speed = command.get('speed')
            self.current_status = self.goto_handler.execute(
                angle, self.current_status, speed
            )

        elif cmd_type == 'jog':
            delta = command.get('delta', 0)
            speed = command.get('speed')
            self.current_status = self.jog_handler.execute(
                delta, self.current_status, speed
            )

        elif cmd_type == 'stop':
            self.handle_stop()

        elif cmd_type == 'continuous':
            direction = command.get('direction', 'cw')
            if self.tracking_handler.is_active:
                self.handle_stop()
            self.continuous_handler.start(direction, self.current_status)

        elif cmd_type == 'tracking_start':
            object_name = command.get('object', command.get('name'))
            if object_name:
                self.tracking_handler.start(object_name, self.current_status)
            else:
                logger.warning("tracking_start sans nom d'objet")

        elif cmd_type == 'tracking_stop':
            self.tracking_handler.stop(self.current_status)

        elif cmd_type == 'status':
            pass  # Juste mettre à jour

        else:
            logger.warning(f"Commande inconnue: {cmd_type}")

        self.ipc.clear_command()

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

        self._write_status()

        last_tracking_update = time.time()
        tracking_interval = 1.0

        while self.running:
            try:
                # Vérifier si recovery automatique d'erreur nécessaire
                self._check_error_recovery()

                # Lire et traiter les commandes
                command = self.ipc.read_command()
                if command:
                    self.process_command(command)

                # Mettre à jour le suivi si actif
                now = time.time()
                if self.tracking_handler.is_active and (now - last_tracking_update) >= tracking_interval:
                    self.tracking_handler.update(self.current_status)
                    last_tracking_update = now
                    self._write_status()

                # Mettre à jour la position depuis l'encodeur
                pos = self.read_encoder_position()
                if pos is not None and not self.tracking_handler.is_active:
                    self.current_status['position'] = pos

                time.sleep(0.05)  # 20Hz de polling

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

        if self.tracking_handler.session:
            self.tracking_handler.session.stop()

        if self.moteur:
            self.moteur.nettoyer()

        self.current_status['status'] = 'stopped'
        self._write_status()

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

    # En production, vérifier les permissions
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
